"""Validation for the final experiment.

    python experiments/resource_allocation_final/scripts/validate_final.py --gate
        Phase D gate (data, method and MILP checks). Must pass before any
        statistics are computed. Writes results/gate_report.json.

    python experiments/resource_allocation_final/scripts/validate_final.py
        Full validation after analysis: the gate checks plus independent
        recomputation of summaries from the master CSV, exact reproduction of
        the statistical tests, and hash / immutability checks.
        Writes results/validation_report.json.

Independent recomputation uses separate code (decimal arithmetic, the
statistics module) wherever possible. Exit code 1 = STOP.
"""

import copy
import json
import math
import os
import re
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal

import numpy as np

from final_common import (
    CONFIG_PATH,
    DATASET_PATH,
    DEVELOPMENT_DATASET_PATH,
    FINAL_ROOT,
    FREEZE_PATH,
    FROZEN_PARAMETERS_PATH,
    GATE_PATH,
    GENERATOR_EQUIVALENCE_PATH,
    METHOD_SUMMARY_PATH,
    MILP_ALLOCATIONS_PATH,
    OFFICIAL,
    OFFICIAL_SCENARIO_COUNT,
    PILOT_DATASET_PATH,
    POLICY_ALLOCATIONS_PATH,
    PREFLIGHT_PATH,
    PROTECTED_MANIFEST_PATH,
    RESOURCE_TYPES,
    RUN_METADATA_PATH,
    SCARCITY_LEVELS,
    SCARCITY_SUMMARY_PATH,
    SCENARIO_RESULTS_PATH,
    STATISTICAL_TESTS_PATH,
    SUMMARY_PATH,
    VALIDATION_PATH,
    WIN_TIE_LOSS_PATH,
    content_fingerprint,
    final_code_hashes,
    json_text,
    load_config,
    load_frozen_parameters,
    parse_bool,
    parse_float,
    protected_manifest,
    read_csv,
    read_gzip_csv,
    read_json,
    scenario_fingerprint,
    sha256_file,
    write_text,
)
from final_statistics import bootstrap_ci, effect_sizes, permutation_test, wilcoxon_test

from policies import fcfs_order, arrival_view  # noqa: E402  (validated FCFS, read-only)
from milp_model import build_model  # noqa: E402  (validated MILP, read-only)


SUMMARY_TOLERANCE = 1e-9
CDC_UPPER_TOLERANCE = 1e-12
TIMING_FIELDS = ["fcfs_decision_time_ms", "fcfs_allocation_time_ms", "fcfs_runtime_ms",
                 "aashray_decision_time_ms", "aashray_allocation_time_ms", "aashray_total_time_ms",
                 "milp_build_time_ms", "milp_solver_time_ms", "milp_total_time_ms"]


class Report:
    def __init__(self):
        self.checks = []

    def add(self, check_id, name, passed, details, critical=True):
        self.checks.append({"id": check_id, "name": name, "critical": critical,
                            "status": "PASS" if passed else "FAIL", "details": details})

    def failed(self):
        return [c for c in self.checks if c["status"] == "FAIL" and c["critical"]]


def exact_critical(severity, urgency):
    s, u = Decimal(repr(severity)), Decimal(repr(urgency))
    return 1 if (s >= Decimal("0.8") and u >= Decimal("0.8")) or s >= Decimal("0.95") \
        or u >= Decimal("0.95") else 0


def pairwise_linear_order(emergencies, tolerance=1e-12):
    # Independent ranking by 0.5*S + 0.5*U, ties (within 1e-12) in FCFS order.
    fcfs_index = {i: n for n, i in enumerate(fcfs_order(arrival_view(emergencies)))}
    scores = {e["emergency_id"]: 0.5 * e["severity"] + 0.5 * e["urgency"] for e in emergencies}

    def position(a):
        return sum(scores[b] - scores[a] > tolerance
                   or (abs(scores[b] - scores[a]) <= tolerance and fcfs_index[b] < fcfs_index[a])
                   for b in scores if b != a)

    return sorted(scores, key=position)


def load_context():
    config = load_config()
    dataset = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    raw_rows = read_csv(SCENARIO_RESULTS_PATH)
    rows = []
    for raw in raw_rows:
        row = {}
        for key, value in raw.items():
            if value in ("true", "false"):
                row[key] = parse_bool(value)
            elif key in ("scenario_id", "scarcity", "size_class", "su_profile",
                         "scenario_input_sha256", "milp_message"):
                row[key] = value
            else:
                row[key] = parse_float(value)
        rows.append(row)
    return {"config": config, "dataset": dataset, "raw_rows": raw_rows, "rows": rows,
            "freeze": read_json(FREEZE_PATH), "preflight": read_json(PREFLIGHT_PATH),
            "run": read_json(RUN_METADATA_PATH), "equivalence": read_json(GENERATOR_EQUIVALENCE_PATH),
            "manifest": read_json(PROTECTED_MANIFEST_PATH)}


def gate_checks(ctx, report):
    config, dataset, rows = ctx["config"], ctx["dataset"], ctx["rows"]
    scenarios = dataset["scenarios"]
    by_id = {s["scenario_id"]: s for s in scenarios}
    expected_n = OFFICIAL_SCENARIO_COUNT if OFFICIAL else config["n_scenarios"]

    # 1 / 2 / 3 / 27 ----------------------------------------------------
    report.add("1", "Exactly 12,000 final scenarios generated" if OFFICIAL else "Expected scenario count",
               len(scenarios) == expected_n == config["n_scenarios"] and len(rows) == expected_n,
               {"dataset": len(scenarios), "rows": len(rows), "expected": expected_n})
    ids = [s["scenario_id"] for s in scenarios]
    row_ids = [r["scenario_id"] for r in rows]
    report.add("2", "Scenario IDs unique", len(set(ids)) == len(ids) and len(set(row_ids)) == len(row_ids),
               {"unique_dataset_ids": len(set(ids)), "unique_row_ids": len(set(row_ids))})
    fingerprints = [content_fingerprint(s) for s in scenarios]
    report.add("3", "No duplicate scenarios", len(set(fingerprints)) == len(fingerprints),
               {"unique_content": len(set(fingerprints))})
    report.add("27", "No scenarios discarded based on outcome", row_ids == ids,
               {"rows_equal_dataset_in_order": row_ids == ids})

    # 4 / 5 -------------------------------------------------------------
    current_hash = sha256_file(DATASET_PATH)
    report.add("4", "Final dataset hash recorded",
               ctx["freeze"]["frozen"] and ctx["freeze"]["sha256"] == current_hash,
               {"recorded": ctx["freeze"]["sha256"], "current": current_hash})
    frozen_at = datetime.fromisoformat(ctx["freeze"]["frozen_at_utc"])
    run_started = datetime.fromisoformat(ctx["run"]["started_at_utc"])
    report.add("5", "Final dataset frozen before allocation execution",
               frozen_at <= run_started and ctx["run"]["dataset_sha256_verified"] == ctx["freeze"]["sha256"]
               and not os.access(DATASET_PATH, os.W_OK),
               {"frozen_at": ctx["freeze"]["frozen_at_utc"], "run_started": ctx["run"]["started_at_utc"],
                "read_only": not os.access(DATASET_PATH, os.W_OK)})

    # 6 / 7 -------------------------------------------------------------
    development = read_json(DEVELOPMENT_DATASET_PATH)["scenarios"]
    pilot = read_json(PILOT_DATASET_PATH)["scenarios"]
    dev_overlap = set(fingerprints) & {content_fingerprint(s) for s in development}
    pilot_overlap = set(fingerprints) & {content_fingerprint(s) for s in pilot}
    report.add("6", "Development data not mixed with final data",
               not dev_overlap and not any(i.startswith("DEV-") for i in ids)
               and config["master_seed"] != 20261108,
               {"identical_content": len(dev_overlap)})
    report.add("7", "Pilot data not mixed with final data",
               not pilot_overlap and not any(i.startswith("PILOT-") for i in ids)
               and config["master_seed"] != 20261007,
               {"identical_content": len(pilot_overlap)})

    # 8 / 9 -------------------------------------------------------------
    frozen = load_frozen_parameters()
    frozen_key = FROZEN_PARAMETERS_PATH.relative_to(FINAL_ROOT.parents[1]).as_posix()
    report.add("8", "Frozen AASHRAY parameters unchanged",
               frozen == config["frozen_aashray"]["expected"] == ctx["run"]["frozen_parameters_used"]
               and sha256_file(FROZEN_PARAMETERS_PATH) == ctx["preflight"]["frozen_parameters_sha256"]
               == ctx["manifest"]["development"][frozen_key],
               {"frozen": frozen})
    label_errors = sum(e["ground_truth_critical"] != exact_critical(e["severity"], e["urgency"])
                       for s in scenarios for e in s["emergencies"])
    report.add("9", "GT-criticality formula unchanged",
               label_errors == 0 and ctx["equivalence"]["byte_identical"]
               and ctx["preflight"]["checks"]["gt_rule_is_frozen_development_rule"],
               {"label_mismatches_vs_exact_rule": label_errors, "rule": config["ground_truth"]["rule"]})

    # Policy allocation file ------------------------------------------
    policy = defaultdict(lambda: defaultdict(list))
    for p in read_gzip_csv(POLICY_ALLOCATIONS_PATH):
        policy[p["scenario_id"]][p["method"]].append(p)

    # 10 ----------------------------------------------------------------
    fcfs_mismatch, aashray_mismatch, rank_errors = 0, 0, 0
    for s in scenarios:
        independent_fcfs = [e["emergency_id"] for e in sorted(
            s["emergencies"], key=lambda e: (e["arrival_timestamp"], e["emergency_id"]))]
        for method in ("FCFS", "AASHRAY"):
            records = policy[s["scenario_id"]][method]
            if [int(r["rank"]) for r in records] != list(range(1, len(s["emergencies"]) + 1)):
                rank_errors += 1
        fcfs_mismatch += [r["emergency_id"] for r in policy[s["scenario_id"]]["FCFS"]] != independent_fcfs
        aashray_mismatch += [r["emergency_id"] for r in policy[s["scenario_id"]]["AASHRAY"]] \
            != pairwise_linear_order(s["emergencies"])
    scrambled = copy.deepcopy(scenarios[:500])
    for s in scrambled:
        for e in s["emergencies"]:
            e["severity"], e["urgency"] = 0.5, 0.5
            e["ground_truth_critical"] = 1 - e["ground_truth_critical"]
            e["resource_requirements"] = {r: 1 for r in RESOURCE_TYPES}
    scramble_changes = sum(fcfs_order(arrival_view(a["emergencies"])) != fcfs_order(arrival_view(b["emergencies"]))
                           for a, b in zip(scenarios[:500], scrambled))
    report.add("10", "FCFS implementation unchanged",
               fcfs_mismatch == 0 and scramble_changes == 0 and rank_errors == 0,
               {"fcfs_orders_differing_from_independent_arrival_sort": fcfs_mismatch,
                "fcfs_orders_changed_by_scrambling_S_U_GT_demand": scramble_changes,
                "policy_rank_sequence_errors": rank_errors,
                "implementation": "experiments/resource_allocation_development/scripts/policies.py (hash-protected)"})
    report.add("E5", "AASHRAY orders equal the frozen ranking 0.5*S + 0.5*U (independent pairwise ranking)",
               aashray_mismatch == 0, {"mismatching_scenarios": aashray_mismatch})

    # 11 ----------------------------------------------------------------
    size_errors = 0
    for s in scenarios[::100]:
        model = build_model(s)
        n_e, n_w = len(s["emergencies"]), len(s["resource_inventory"])
        if (model.number_variables, model.number_constraints) != (n_e * 3 * n_w, 3 * n_w + 3 * n_e) \
                or not (model.constraints.A.getnnz(axis=0) == 2).all():
            size_errors += 1
    milp_changed = [k for k in set(ctx["manifest"]["milp"]) | set(protected_manifest()["milp"])
                    if ctx["manifest"]["milp"].get(k) != protected_manifest()["milp"].get(k)]
    report.add("11", "MILP formulation unchanged",
               size_errors == 0 and not milp_changed
               and ctx["run"]["milp_options_used"] == {"mip_rel_gap": 0.0, "time_limit": 60.0,
                                                       "presolve": True, "disp": False},
               {"model_structure_errors": size_errors, "milp_files_changed": milp_changed,
                "options": ctx["run"]["milp_options_used"]})

    # 12 ----------------------------------------------------------------
    input_errors = 0
    for r in rows:
        s = by_id[r["scenario_id"]]
        if r["scenario_input_sha256"] != scenario_fingerprint(s):
            input_errors += 1
        for method in ("FCFS", "AASHRAY"):
            recorded = {p["emergency_id"]: [int(p[f"required_{t}"]) for t in RESOURCE_TYPES]
                        for p in policy[r["scenario_id"]][method]}
            if recorded != {e["emergency_id"]: [e["resource_requirements"][t] for t in RESOURCE_TYPES]
                            for e in s["emergencies"]}:
                input_errors += 1
    report.add("12", "All methods receive identical scenario inputs", input_errors == 0,
               {"rows_with_input_mismatch": input_errors,
                "method": "per-row scenario fingerprint + per-emergency demand recorded for each method"})

    # 13 / 14 -----------------------------------------------------------
    optimal = [r for r in rows if r["milp_proven_optimal"] and r["milp_status"] == 0
               and r["milp_success"] and r["milp_mip_gap"] == 0
               and abs(r["milp_objective"] - r["milp_dual_bound"]) <= 1e-6]
    optimal_ids = {r["scenario_id"] for r in optimal}
    report.add("13", "All MILP scenarios proven optimal", len(optimal) == len(rows),
               {"proven_optimal": len(optimal), "rows": len(rows),
                "not_optimal": [r["scenario_id"] for r in rows if r["scenario_id"] not in optimal_ids][:20]})

    analytical_errors = []
    for r in rows:
        s = by_id[r["scenario_id"]]
        oracle = sum(min(sum(e["resource_requirements"][t] for e in s["emergencies"] if e["ground_truth_critical"]),
                         sum(w["inventory"][t]["available"] for w in s["resource_inventory"]))
                     for t in RESOURCE_TYPES)
        if not (r["analytical_optimum"] == oracle == r["critical_fulfilled_MILP"] and r["analytical_optimum_match"]):
            analytical_errors.append(r["scenario_id"])
    report.add("14", "All MILP solutions match the analytical optimum", not analytical_errors,
               {"matching": len(rows) - len(analytical_errors), "mismatching": analytical_errors[:20]})

    # 15-18 -------------------------------------------------------------
    warehouse_use, emergency_use = defaultdict(int), defaultdict(int)
    milp_critical, milp_bad_values = defaultdict(int), 0
    critical_of = {(s["scenario_id"], e["emergency_id"]): e["ground_truth_critical"]
                   for s in scenarios for e in s["emergencies"]}
    for a in read_gzip_csv(MILP_ALLOCATIONS_PATH):
        if not re.fullmatch(r"\d+", a["allocated_quantity"]) or int(a["allocated_quantity"]) <= 0:
            milp_bad_values += 1
            continue
        q = int(a["allocated_quantity"])
        warehouse_use[(a["scenario_id"], a["warehouse_id"], a["resource_type"])] += q
        emergency_use[(a["scenario_id"], a["emergency_id"], a["resource_type"])] += q
        if critical_of[(a["scenario_id"], a["emergency_id"])]:
            milp_critical[a["scenario_id"]] += q
    available = {(s["scenario_id"], w["warehouse_id"], t): w["inventory"][t]["available"]
                 for s in scenarios for w in s["resource_inventory"] for t in RESOURCE_TYPES}
    demand = {(s["scenario_id"], e["emergency_id"], t): e["resource_requirements"][t]
              for s in scenarios for e in s["emergencies"] for t in RESOURCE_TYPES}
    supply_violations = [k for k, v in warehouse_use.items() if v > available[k]]
    demand_violations = [k for k, v in emergency_use.items() if v > demand[k]]
    report.add("15", "No MILP supply constraint violations", not supply_violations,
               {"pairs_checked": len(warehouse_use), "violations": supply_violations[:10]})
    report.add("16", "No MILP demand constraint violations", not demand_violations,
               {"pairs_checked": len(emergency_use), "violations": demand_violations[:10]})

    policy_negative, policy_non_integer, policy_over_demand = 0, 0, 0
    policy_totals = defaultdict(lambda: [0, 0])
    for s in scenarios:
        for method in ("FCFS", "AASHRAY"):
            for p in policy[s["scenario_id"]][method]:
                for t in RESOURCE_TYPES:
                    value = float(p[f"allocated_{t}"])
                    if value < 0:
                        policy_negative += 1
                    if not value.is_integer():
                        policy_non_integer += 1
                    if value > int(p[f"required_{t}"]):
                        policy_over_demand += 1
                    policy_totals[(s["scenario_id"], method)][0] += value
                    if int(p["ground_truth_critical"]) == 1:
                        policy_totals[(s["scenario_id"], method)][1] += value
    report.add("17", "No negative allocations", policy_negative == 0 and milp_bad_values == 0,
               {"policy_negative_values": policy_negative, "milp_invalid_or_non_positive_rows": milp_bad_values})
    max_deviation = max(r["milp_max_integrality_deviation"] for r in rows)
    report.add("18", "All allocations integral",
               policy_non_integer == 0 and milp_bad_values == 0 and max_deviation <= 1e-6,
               {"policy_non_integer_values": policy_non_integer,
                "milp_max_solver_deviation": max_deviation})

    # 19 / 20 / 21 / 22 / 23 --------------------------------------------
    cdc_errors, tdc_errors = [], []
    for r in rows:
        s = by_id[r["scenario_id"]]
        required = sum(sum(e["resource_requirements"].values()) for e in s["emergencies"] if e["ground_truth_critical"])
        total = sum(sum(e["resource_requirements"].values()) for e in s["emergencies"])
        expected = {
            "FCFS": policy_totals[(r["scenario_id"], "FCFS")][1],
            "AASHRAY": policy_totals[(r["scenario_id"], "AASHRAY")][1],
            "MILP": milp_critical[r["scenario_id"]],
        }
        for method, fulfilled in expected.items():
            value = fulfilled / required if required else math.nan
            if r[f"critical_fulfilled_{method}"] != fulfilled or not (
                    (math.isnan(value) and math.isnan(r[f"CDC_{method}"])) or r[f"CDC_{method}"] == value):
                cdc_errors.append((r["scenario_id"], method))
        if required != r["critical_required"] or total != r["total_demand"]:
            cdc_errors.append((r["scenario_id"], "required"))
        for method in ("FCFS", "AASHRAY"):
            fulfilled = policy_totals[(r["scenario_id"], method)][0]
            if r[f"total_fulfilled_{method}"] != fulfilled or r[f"TDC_{method}"] != fulfilled / total:
                tdc_errors.append((r["scenario_id"], method))
    report.add("19", "CDC values correctly recomputed independently", not cdc_errors,
               {"mismatches": cdc_errors[:10], "source": "allocation files + dataset GT labels"})
    report.add("20", "TDC values correctly recomputed independently", not tdc_errors,
               {"mismatches": tdc_errors[:10]})

    defined = [r for r in rows if r["cdc_defined"]]
    report.add("21", "No CDC > 1 + tolerance",
               all(0 <= r[f"CDC_{m}"] <= 1 + CDC_UPPER_TOLERANCE for r in defined for m in ("FCFS", "AASHRAY", "MILP")),
               {"tolerance": CDC_UPPER_TOLERANCE, "undefined_cdc_rows": len(rows) - len(defined)})
    report.add("22", "No TDC > 1 + tolerance",
               all(0 <= r[f"TDC_{m}"] <= 1 + CDC_UPPER_TOLERANCE for r in rows for m in ("FCFS", "AASHRAY")),
               {"tolerance": CDC_UPPER_TOLERANCE})
    above = [r["scenario_id"] for r in defined
             if r["CDC_AASHRAY"] > r["CDC_MILP"] + CDC_UPPER_TOLERANCE
             or r["CDC_FCFS"] > r["CDC_MILP"] + CDC_UPPER_TOLERANCE]
    report.add("23", "AASHRAY (and FCFS) CDC never exceed MILP CDC beyond tolerance", not above,
               {"violations": above[:10], "tolerance": CDC_UPPER_TOLERANCE})

    # 24 / 25 -----------------------------------------------------------
    bad_times = sum(not (math.isfinite(r[f]) and r[f] > 0) for r in rows for f in TIMING_FIELDS)
    sums_ok = all(
        math.isclose(r["fcfs_runtime_ms"], r["fcfs_decision_time_ms"] + r["fcfs_allocation_time_ms"], rel_tol=1e-9)
        and math.isclose(r["aashray_total_time_ms"], r["aashray_decision_time_ms"] + r["aashray_allocation_time_ms"], rel_tol=1e-9)
        and math.isclose(r["milp_total_time_ms"], r["milp_build_time_ms"] + r["milp_solver_time_ms"], rel_tol=1e-9)
        for r in rows)
    report.add("24", "All runtime values positive and finite", bad_times == 0,
               {"non_positive_or_non_finite": bad_times, "fields": TIMING_FIELDS})
    report.add("25", "Runtime methodology identical across runs",
               sums_ok and ctx["run"]["timing_methodology"] == config["timing"]
               and ctx["run"]["scenarios_run"] == len(rows) and len(ctx["run"]["warm_up_scenarios"]) == 3,
               {"single_run_id": ctx["run"]["run_id"], "process_id": ctx["run"]["process_id"],
                "totals_equal_component_sums": sums_ok, "warm_up": ctx["run"]["warm_up_scenarios"]})

    # E6 required outputs present ------------------------------------
    allowed_empty = {"milp_message"}
    missing = sum(1 for raw in ctx["raw_rows"] for k, v in raw.items() if v == "" and k not in allowed_empty)
    report.add("E6", "No missing required outputs", missing == 0, {"empty_fields": missing})

    return {
        "scenario_count": len(rows),
        "valid_scenarios": len(defined),
        "invalid_scenarios": len(rows) - len(defined),
        "milp_optimal_count": len(optimal),
        "analytical_match_count": len(rows) - len(analytical_errors),
    }


def protection_checks(ctx, report):
    stored, current = ctx["manifest"], protected_manifest()

    def changed(group):
        return sorted(k for k in set(stored[group]) | set(current[group]) if stored[group].get(k) != current[group].get(k))

    report.add("28", "No existing application files modified", not changed("application"),
               {"files": len(stored["application"]), "changed": changed("application")[:20]})
    report.add("29", "No development files modified", not changed("development"),
               {"files": len(stored["development"]), "changed": changed("development")[:20]})
    report.add("30", "No pilot files modified", not changed("pilot"),
               {"files": len(stored["pilot"]), "changed": changed("pilot")[:20]})
    report.add("E1", "No MILP files modified", not changed("milp"),
               {"files": len(stored["milp"]), "changed": changed("milp")[:20]})
    report.add("E2", "Copied generator reproduces the development dataset byte for byte",
               ctx["equivalence"]["byte_identical"], ctx["equivalence"])

    code_now = final_code_hashes()
    code_changed = sorted(k for k in set(code_now) | set(ctx["preflight"]["final_code_hashes"])
                          if code_now.get(k) != ctx["preflight"]["final_code_hashes"].get(k))
    tuning_terms = [p.name for p in (FINAL_ROOT / "scripts").glob("*.py")
                    if p.name != "validate_final.py"
                    and re.search(r"candidate_grid|select_winner|rank_by_selection_rule|compute_rankings",
                                  p.read_text(encoding="utf-8"))]
    report.add("26", "No final-test result used for tuning",
               not code_changed and not tuning_terms
               and load_frozen_parameters() == ctx["config"]["frozen_aashray"]["expected"],
               {"config_or_scripts_changed_since_preflight": code_changed,
                "scripts_containing_selection_code": tuning_terms,
                "aashray_configurations_evaluated": 1})
    report.add("E3", "Final dataset untouched after freeze",
               sha256_file(DATASET_PATH) == ctx["freeze"]["sha256"], {"sha256": ctx["freeze"]["sha256"]})


def post_analysis_checks(ctx, report):
    rows, config = ctx["rows"], ctx["config"]
    summary = read_json(SUMMARY_PATH)
    tests = read_json(STATISTICAL_TESTS_PATH)
    stats_config = config["statistics"]
    defined = [r for r in rows if r["cdc_defined"]]

    # P1: summaries recomputed independently (statistics module) ------
    def close(a, b):
        return math.isclose(a, b, rel_tol=SUMMARY_TOLERANCE, abs_tol=SUMMARY_TOLERANCE)

    mismatches = []
    for method in ("FCFS", "AASHRAY", "MILP"):
        values = [r[f"CDC_{method}"] for r in defined]
        for key, value in (("mean", statistics.fmean(values)), ("median", statistics.median(values)),
                           ("std", statistics.stdev(values))):
            if not close(summary["overall"][method]["CDC"][key], value):
                mismatches.append(f"{method} CDC {key}")
        runtime_field = {"FCFS": "fcfs_runtime_ms", "AASHRAY": "aashray_total_time_ms", "MILP": "milp_total_time_ms"}[method]
        times = [r[runtime_field] for r in rows]
        if not close(summary["overall"][method]["runtime_ms"]["mean"], statistics.fmean(times)) \
                or not close(summary["overall"][method]["runtime_ms"]["median"], statistics.median(times)) \
                or not close(summary["overall"][method]["runtime_ms"]["total_ms"], math.fsum(times)):
            mismatches.append(f"{method} runtime")
    for method in ("FCFS", "AASHRAY"):
        if not close(summary["overall"][method]["TDC"]["mean"], statistics.fmean(r[f"TDC_{method}"] for r in rows)):
            mismatches.append(f"{method} TDC mean")
    gaps = [r["aashray_milp_gap_relative"] for r in defined]
    if not close(summary["optimality"]["mean_gap"], statistics.fmean(gaps)) \
            or not close(summary["optimality"]["median_gap"], statistics.median(gaps)) \
            or not close(summary["optimality"]["max_gap"], max(gaps)) \
            or not close(summary["optimality"]["within_5pct_pct"], 100 * sum(g <= 0.05 for g in gaps) / len(gaps)) \
            or not close(summary["optimality"]["exact_optimum_pct"],
                         100 * sum(r["aashray_milp_gap_absolute"] <= stats_config["tie_tolerance"] for r in defined) / len(defined)):
        mismatches.append("optimality")
    wins = sum(r["CDC_AASHRAY"] - r["CDC_FCFS"] > stats_config["tie_tolerance"] for r in defined)
    losses = sum(r["CDC_AASHRAY"] - r["CDC_FCFS"] < -stats_config["tie_tolerance"] for r in defined)
    wtl_all = next(w for w in read_csv(WIN_TIE_LOSS_PATH) if w["scope"] == "ALL")
    if int(wtl_all["aashray_wins"]) != wins or int(wtl_all["fcfs_wins"]) != losses \
            or int(wtl_all["ties"]) != len(defined) - wins - losses:
        mismatches.append("win/tie/loss")
    for level in SCARCITY_LEVELS:
        part = [r for r in defined if r["scarcity"] == level]
        for method in ("FCFS", "AASHRAY", "MILP"):
            if not close(summary["scarcity"][level]["CDC"][method]["mean"],
                         statistics.fmean(r[f"CDC_{method}"] for r in part)):
                mismatches.append(f"{level} {method} CDC")
        csv_row = next(x for x in read_csv(SCARCITY_SUMMARY_PATH) if x["scarcity"] == level and x["method"] == "AASHRAY")
        if not close(float(csv_row["mean_CDC"]), statistics.fmean(r["CDC_AASHRAY"] for r in part)) \
                or not close(float(csv_row["mean_optimality_gap"]),
                             statistics.fmean(r["aashray_milp_gap_relative"] for r in part)):
            mismatches.append(f"{level} scarcity csv")
    method_rows = {x["method"]: x for x in read_csv(METHOD_SUMMARY_PATH)}
    for method in ("FCFS", "AASHRAY", "MILP"):
        if not close(float(method_rows[method]["mean_CDC"]), statistics.fmean(r[f"CDC_{method}"] for r in defined)):
            mismatches.append(f"{method} method csv")
    report.add("P1", "Summary values match the raw scenario table (independent recomputation)",
               not mismatches, {"tolerance": SUMMARY_TOLERANCE, "mismatches": mismatches})

    # P2: statistics reproduced exactly from raw differences ----------
    delta = np.array([r["CDC_AASHRAY"] - r["CDC_FCFS"] for r in defined])
    stored_delta = np.array([r["aashray_minus_fcfs_CDC"] for r in defined])
    permutation = permutation_test(delta, stats_config["primary_permutation_test"]["permutations"],
                                   stats_config["primary_permutation_test"]["seed"])
    bootstrap = bootstrap_ci(delta, stats_config["bootstrap_ci"]["resamples"],
                             stats_config["bootstrap_ci"]["seed"], stats_config["bootstrap_ci"]["level"])
    wilcox = wilcoxon_test(delta, stats_config["tie_tolerance"])
    effect = effect_sizes(delta, stats_config["tie_tolerance"])
    reproduced = {
        "delta_column_equals_recomputed_difference": bool(np.array_equal(delta, stored_delta)),
        "permutation_p": permutation["p_value"] == tests["primary_permutation_test"]["p_value"],
        "permutation_statistic": permutation["statistic"] == tests["primary_permutation_test"]["statistic"],
        "bootstrap_ci": bootstrap["confidence_interval"] == tests["paired_bootstrap_ci"]["confidence_interval"],
        "wilcoxon": (wilcox["statistic"], wilcox["p_value"]) == (
            tests["secondary_wilcoxon_signed_rank"]["statistic"], tests["secondary_wilcoxon_signed_rank"]["p_value"]),
        "cohens_dz": (math.isnan(effect["cohens_dz"]) and math.isnan(tests["effect_size"]["cohens_dz"]))
        or effect["cohens_dz"] == tests["effect_size"]["cohens_dz"],
        "conclusion_follows_rule": tests["primary_permutation_test"]["reject_H0"]
        == (tests["primary_permutation_test"]["p_value"] < config["hypothesis"]["alpha"]),
        "summary_matches_tests": summary["hypothesis"]["permutation_p"] == tests["primary_permutation_test"]["p_value"]
        and summary["hypothesis"]["confidence_interval_95"] == tests["paired_bootstrap_ci"]["confidence_interval"],
    }
    report.add("P2", "Statistical values reproduce exactly from raw differences", all(reproduced.values()),
               reproduced)


def main() -> None:
    gate_only = "--gate" in sys.argv
    ctx = load_context()
    report = Report()

    counts = gate_checks(ctx, report)
    protection_checks(ctx, report)

    if gate_only:
        failed = report.failed()
        write_text(GATE_PATH, json_text({
            "passed": not failed, **counts,
            "failures": [{"id": c["id"], "name": c["name"], "details": c["details"]} for c in failed],
            "checks": report.checks,
        }))
        label = "GATE"
    else:
        post_analysis_checks(ctx, report)
        failed = report.failed()
        write_text(VALIDATION_PATH, json_text({
            "n_checks": len(report.checks), "n_pass": len(report.checks) - len(failed),
            "n_fail": len(failed), **counts,
            "failures": [{"id": c["id"], "name": c["name"]} for c in failed],
            "checks": report.checks,
        }))
        label = "VALIDATION"

    for c in report.checks:
        print(f"[{c['status']}] {c['id']:>3}  {c['name']}")
    print(f"\n{label}: {len(report.checks) - len(failed)} PASS, {len(failed)} FAIL")
    if failed:
        print("STOP: critical validation failed; no statistical conclusions.")
        sys.exit(1)


if __name__ == "__main__":
    main()
