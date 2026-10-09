"""Validate the development experiment; freeze parameters only if all pass.

Usage (from the repository root, after evaluate_configurations.py):

    python experiments/resource_allocation_development/scripts/validate_development.py

Runs the 20 required checks plus consistency checks and writes
results/validation_report.json. If ANY check fails it STOPS: no parameters
are frozen and the exit code is 1. If all pass, results/frozen_parameters.json
is written (or, if it already exists, verified and left unchanged).
"""

import copy
import csv
import gzip
import json
import math
import random
import re
import statistics
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

from allocator_adapter import ExistingAllocatorAdapter
from dev_common import (
    CONFIGURATION_RESULTS_PATH,
    DATASET_PATH,
    DEV_ROOT,
    DEVELOPMENT_SCENARIO_COUNT,
    EQUIVALENCE_PATH,
    FROZEN_PATH,
    GRID_PATH,
    MANIFEST_PATH,
    PER_SCENARIO_PATH,
    PILOT_ROOT,
    REPO_ROOT,
    SUMMARY_PATH,
    TOP_10_PATH,
    VALIDATION_PATH,
    application_manifest,
    derive_seed,
    json_text,
    load_config,
    sha256_file,
    sha256_text,
    write_text,
)
from generate_development_dataset import dataset_text, generate_dataset
from generate_parameter_grid import build_grid, grid_text, read_grid
from metrics import scenario_outcome
from policies import (
    aashray_order,
    arrival_view,
    fcfs_order,
    linear_order,
    overall_priority,
    normalized_priority,
)
from ranking_equivalence import compute_rankings


RESOURCE_TYPES = ("water", "food", "medical_kits")
SAMPLE_STEP = 10  # every 10th scenario for allocator re-runs (300 scenarios)
CORRELATION_LIMIT = 0.05
FREEZE_STATEMENT = (
    "These parameters were selected using the development dataset only. "
    "They must not be changed after the final test dataset is evaluated."
)


class Report:
    def __init__(self):
        self.checks = []

    def add(self, check_id, name, passed, details):
        self.checks.append(
            {
                "id": check_id,
                "name": name,
                "status": "PASS" if passed else "FAIL",
                "details": details,
            }
        )

    def failed(self):
        return [c for c in self.checks if c["status"] == "FAIL"]


def exact_critical(severity: float, urgency: float) -> int:
    s, u = Decimal(repr(severity)), Decimal(repr(urgency))
    both = s >= Decimal("0.8") and u >= Decimal("0.8")
    return 1 if both or s >= Decimal("0.95") or u >= Decimal("0.95") else 0


def emergencies_of(dataset):
    for scenario in dataset["scenarios"]:
        for emergency in scenario["emergencies"]:
            yield scenario, emergency


def read_configuration_rows():
    rows = []
    with CONFIGURATION_RESULTS_PATH.open("r", encoding="utf-8") as file:
        for row in csv.DictReader(file):
            for key in ("alpha", "k", "m", "n", "mean_cdc", "median_cdc", "p10_cdc"):
                row[key] = float(row[key])
            rows.append(row)
    return rows


def pairwise_order(emergencies, score, tolerance=1e-12):
    # Independent ranking: an emergency's position is the number of others
    # that score clearly higher, plus the number tied with it (within the
    # tolerance) that arrived earlier in FCFS order.
    fcfs_index = {i: n for n, i in enumerate(fcfs_order(arrival_view(emergencies)))}
    scores = {e["emergency_id"]: score(e) for e in emergencies}

    def position(a):
        return sum(
            scores[b] - scores[a] > tolerance
            or (abs(scores[b] - scores[a]) <= tolerance and fcfs_index[b] < fcfs_index[a])
            for b in scores if b != a
        )

    return sorted(scores, key=position)


def independent_winner(rows, tolerance):
    # Second, independent implementation of the predefined selection rule.
    pool = rows
    for metric in ("mean_cdc", "median_cdc", "p10_cdc"):
        top = max(r[metric] for r in pool)
        pool = [r for r in pool if top - r[metric] <= tolerance]
    pool.sort(key=lambda r: (r["alpha"], r["k"], r["m"], r["n"]))
    return pool[0]


def git_state():
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT,
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        dirty = bool(subprocess.run(
            ["git", "status", "--porcelain"], cwd=REPO_ROOT,
            capture_output=True, text=True, check=True,
        ).stdout.strip())
        return commit, dirty
    except (OSError, subprocess.CalledProcessError):
        return None, None


def main() -> None:
    config = load_config()
    report = Report()

    text = DATASET_PATH.read_text(encoding="utf-8")
    dataset = json.loads(text)
    scenarios = dataset["scenarios"]
    summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    grid = read_grid()
    config_rows = read_configuration_rows()
    winner_id = summary["winner"]["config_id"]

    # 1 ----------------------------------------------------------------
    report.add("1", "Exactly 3,000 scenarios",
               len(scenarios) == DEVELOPMENT_SCENARIO_COUNT == dataset["n_scenarios"]
               == config["n_scenarios"],
               {"scenarios": len(scenarios)})

    # 2 ----------------------------------------------------------------
    scenario_ids = [s["scenario_id"] for s in scenarios]
    emergency_ids = [e["emergency_id"] for _, e in emergencies_of(dataset)]
    report.add("2", "All scenario IDs unique",
               len(set(scenario_ids)) == len(scenario_ids)
               and len(set(emergency_ids)) == len(emergency_ids),
               {"unique_scenario_ids": len(set(scenario_ids)),
                "unique_emergency_ids": len(set(emergency_ids))})

    # 3 ----------------------------------------------------------------
    bad_seeds = [
        s["scenario_id"] for s in scenarios
        if s["master_seed"] != config["master_seed"]
        or s["scenario_seed"] != derive_seed(
            config["seed_namespace"], config["master_seed"], "scenario",
            int(s["scenario_id"].split("-")[1]))
    ]
    report.add("3", "All scenario seeds deterministic", not bad_seeds,
               {"rule": "derive_seed(namespace, master_seed, 'scenario', index)",
                "mismatches": bad_seeds[:10]})

    # 4 ----------------------------------------------------------------
    pilot_config = json.loads((PILOT_ROOT / "config" / "pilot_config.json").read_text(encoding="utf-8"))
    pilot_data = json.loads((PILOT_ROOT / "data" / "pilot_500_scenarios.json").read_text(encoding="utf-8"))

    def fingerprint(scenario):
        return tuple(sorted(
            (e["severity"], e["urgency"],
             tuple(e["resource_requirements"][r] for r in RESOURCE_TYPES))
            for e in scenario["emergencies"]))

    overlap = {fingerprint(s) for s in scenarios} & {fingerprint(s) for s in pilot_data["scenarios"]}
    report.add("4", "Development master seed differs from pilot seed",
               config["master_seed"] != pilot_config["master_seed"]
               and dataset["master_seed"] != pilot_data["master_seed"]
               and not overlap,
               {"development_master_seed": config["master_seed"],
                "pilot_master_seed": pilot_config["master_seed"],
                "seed_namespace": config["seed_namespace"],
                "scenarios_identical_to_a_pilot_scenario": len(overlap)})

    # 5-8 ---------------------------------------------------------------
    labels = {e["emergency_id"]: exact_critical(e["severity"], e["urgency"])
              for _, e in emergencies_of(dataset)}
    no_critical = [s["scenario_id"] for s in scenarios
                   if not any(labels[e["emergency_id"]] for e in s["emergencies"])]
    report.add("5", "Every scenario has >=1 GT-critical emergency", not no_critical,
               {"scenarios_without_critical": len(no_critical)})

    severities = [e["severity"] for _, e in emergencies_of(dataset)]
    urgencies = [e["urgency"] for _, e in emergencies_of(dataset)]
    report.add("6", "Every S in (0, 1]", all(0 < v <= 1 for v in severities),
               {"min": min(severities), "max": max(severities)})
    report.add("7", "Every U in (0, 1]", all(0 < v <= 1 for v in urgencies),
               {"min": min(urgencies), "max": max(urgencies)})

    label_errors, clause_errors, count_errors = [], [], []
    for scenario in scenarios:
        for e in scenario["emergencies"]:
            s, u = Decimal(repr(e["severity"])), Decimal(repr(e["urgency"]))
            if e["ground_truth_critical"] != labels[e["emergency_id"]]:
                label_errors.append(e["emergency_id"])
            inputs = e["gt_rule_inputs"]
            if (inputs["both_high"] != (s >= Decimal("0.8") and u >= Decimal("0.8"))
                    or inputs["severity_extreme"] != (s >= Decimal("0.95"))
                    or inputs["urgency_extreme"] != (u >= Decimal("0.95"))
                    or inputs["severity"] != e["severity"] or inputs["urgency"] != e["urgency"]):
                clause_errors.append(e["emergency_id"])
        if scenario["n_ground_truth_critical"] != sum(labels[e["emergency_id"]] for e in scenario["emergencies"]):
            count_errors.append(scenario["scenario_id"])
    report.add("8", "GT criticality exactly follows the fixed rule",
               not (label_errors or clause_errors or count_errors),
               {"rule": config["ground_truth"]["rule"],
                "verified_with": "exact decimal arithmetic",
                "label_mismatches": label_errors[:10],
                "clause_mismatches": clause_errors[:10],
                "count_mismatches": count_errors[:10]})

    # 9 ----------------------------------------------------------------
    scramble_rng = random.Random(derive_seed(config["seed_namespace"], "validation-scramble"))
    scrambled = copy.deepcopy(dataset)
    for _, e in emergencies_of(scrambled):
        e["severity"] = round(scramble_rng.uniform(0.01, 1.0), 4)
        e["urgency"] = round(scramble_rng.uniform(0.01, 1.0), 4)
        e["ground_truth_critical"] = scramble_rng.randint(0, 1)
        e["resource_requirements"] = {r: scramble_rng.randint(0, 999) for r in RESOURCE_TYPES}
    fcfs_changed = sum(
        fcfs_order(arrival_view(a["emergencies"])) != fcfs_order(arrival_view(b["emergencies"]))
        for a, b in zip(scenarios, scrambled["scenarios"]))
    fcfs_sorted = all(
        fcfs_order(arrival_view(s["emergencies"])) == [
            e["emergency_id"] for e in sorted(
                s["emergencies"], key=lambda e: (e["arrival_timestamp"], e["emergency_id"]))]
        for s in scenarios)
    view_width = {len(item) for s in scenarios[:50] for item in arrival_view(s["emergencies"])}
    report.add("9", "FCFS uses only arrival order",
               fcfs_changed == 0 and fcfs_sorted and view_width == {2},
               {"fcfs_input": "(emergency_id, arrival_timestamp) only",
                "orders_changed_after_scrambling_S_U_GT_demand": fcfs_changed,
                "sorted_by_timestamp_then_id": fcfs_sorted})

    # 10 ---------------------------------------------------------------
    linear_mismatch = 0
    for s in scenarios:
        expected = pairwise_order(
            s["emergencies"], lambda e: 0.5 * e["severity"] + 0.5 * e["urgency"])
        linear_mismatch += linear_order(s["emergencies"]) != expected
    demand_scrambled = copy.deepcopy(dataset)
    for _, e in emergencies_of(demand_scrambled):
        e["resource_requirements"] = {r: scramble_rng.randint(0, 999) for r in RESOURCE_TYPES}
        e["ground_truth_critical"] = 1 - e["ground_truth_critical"]
    linear_changed = sum(linear_order(a["emergencies"]) != linear_order(b["emergencies"])
                         for a, b in zip(scenarios, demand_scrambled["scenarios"]))
    report.add("10", "Linear baseline uses only 0.5*S + 0.5*U",
               linear_mismatch == 0 and linear_changed == 0,
               {"orders_differing_from_independent_recomputation": linear_mismatch,
                "orders_changed_after_scrambling_demand_and_GT": linear_changed})

    # 11 ---------------------------------------------------------------
    formula_errors = 0
    sample = scenarios[::SAMPLE_STEP]
    for candidate in grid:
        a, k, m, n = candidate["alpha"], candidate["k"], candidate["m"], candidate["n"]
        for s in sample:
            for e in s["emergencies"]:
                sv, uv = e["severity"], e["urgency"]
                expected = k * sv + m * uv + n * math.exp(a * math.log(sv) + (1 - a) * math.log(uv))
                got = overall_priority(sv, uv, k, m, n, normalized_priority(sv, uv, a))
                if not math.isclose(got, expected, rel_tol=1e-12, abs_tol=1e-12):
                    formula_errors += 1

    print("Recomputing ranking signatures for check 11 ...", flush=True)
    rankings = compute_rankings(dataset, grid)
    stored_classes = {}
    with EQUIVALENCE_PATH.open("r", encoding="utf-8") as file:
        for row in csv.DictReader(file):
            stored_classes[row["equivalence_class_id"]] = row["member_config_ids"].split(";")
    recomputed_classes = {c["class_id"]: [grid[i]["config_id"] for i in c["members"]]
                          for c in rankings["classes"]}
    order_mismatch, independent_mismatch = 0, 0
    for config_index, candidate in enumerate(grid):
        for s_index in range(0, len(scenarios), 30):
            emergencies = scenarios[s_index]["emergencies"]
            order = tuple(aashray_order(emergencies, candidate))
            stored = rankings["scenario_orders"][s_index][rankings["config_order_ids"][config_index][s_index]]
            order_mismatch += order != stored
            independent = pairwise_order(emergencies, lambda e, c=candidate: overall_priority(
                e["severity"], e["urgency"], c["k"], c["m"], c["n"],
                normalized_priority(e["severity"], e["urgency"], c["alpha"])))
            independent_mismatch += list(order) != independent
    report.add("11", "AASHRAY uses exactly the specified formula",
               formula_errors == 0 and order_mismatch == 0 and independent_mismatch == 0
               and stored_classes == recomputed_classes,
               {"formula": "P_o = k*S + m*U + n*S^alpha*U^(1-alpha), checked against log-space form",
                "formula_mismatches": formula_errors,
                "ranking_mismatches_vs_aashray_order": order_mismatch,
                "ranking_mismatches_vs_independent_pairwise_ranking": independent_mismatch,
                "equivalence_classes_reproduced": stored_classes == recomputed_classes})

    # 12 ---------------------------------------------------------------
    tenths_ok = all(
        all(abs(v * 10 - round(v * 10)) < 1e-9 for v in (g["alpha"], g["k"], g["m"], g["n"]))
        and round(g["k"] * 10) + round(g["m"] * 10) + round(g["n"] * 10) == 10
        and abs(g["k"] + g["m"] + g["n"] - 1) < 1e-9
        and min(g["k"], g["m"], g["n"]) >= 0 and 0 <= g["alpha"] <= 1
        for g in grid)
    report.add("12", "All 726 candidates satisfy k + m + n = 1",
               len(grid) == 726 and tenths_ok
               and len({g["config_id"] for g in grid}) == 726
               and len({(g["alpha"], g["k"], g["m"], g["n"]) for g in grid}) == 726
               and GRID_PATH.read_text(encoding="utf-8") == grid_text(build_grid())
               and sha256_file(GRID_PATH) == summary["candidate_grid_sha256"],
               {"candidates": len(grid),
                "grid_unchanged_since_evaluation": sha256_file(GRID_PATH) == summary["candidate_grid_sha256"]})

    # 13 / 14 (allocator re-runs on a sample) --------------------------
    print("Re-running the allocator on a 300-scenario sample ...", flush=True)
    stored_rows = {}
    expected_critical_required = {}
    for s in scenarios:
        expected_critical_required[s["scenario_id"]] = float(sum(
            sum(e["resource_requirements"].values())
            for e in s["emergencies"] if labels[e["emergency_id"]]))
    sample_ids = {s["scenario_id"] for s in sample}
    winner_class = summary["winner"]["equivalence_class_id"]
    row_count, critical_required_errors, arithmetic_errors = 0, [], 0
    with gzip.open(PER_SCENARIO_PATH, "rt", encoding="utf-8", newline="") as file:
        for row in csv.DictReader(file):
            row_count += 1
            if float(row["critical_required"]) != expected_critical_required[row["scenario_id"]]:
                critical_required_errors.append((row["scenario_id"], row["policy"]))
            tr, tf, tu = float(row["total_required"]), float(row["total_fulfilled"]), float(row["total_unmet"])
            cr, cf = float(row["critical_required"]), float(row["critical_fulfilled"])
            if (tf + tu != tr or not math.isclose(float(row["tdc"]), tf / tr, abs_tol=1e-12)
                    or not math.isclose(float(row["cdc"]), cf / cr, abs_tol=1e-12)):
                arithmetic_errors += 1
            if row["scenario_id"] in sample_ids and row["policy"] in ("FCFS", "LINEAR", winner_class):
                stored_rows[(row["scenario_id"], row["policy"])] = row

    placeholder_variants = [{"severity": 0.5, "urgency": 0.5, "priority": p}
                            for p in ("LOW", "MODERATE", "HIGH", "CRITICAL")]
    placeholder_variants += [{"severity": 0.01, "urgency": 0.01, "priority": "LOW"},
                             {"severity": 1.0, "urgency": 1.0, "priority": "CRITICAL"}]
    winner_params = next(g for g in grid if g["config_id"] == winner_id)
    placeholder_changes, recompute_mismatch = 0, 0
    with TemporaryDirectory(prefix="aashray_dev_check_") as work_dir:
        for s in sample:
            fcfs = fcfs_order(arrival_view(s["emergencies"]))
            baseline = None
            for variant in placeholder_variants:
                adapter = ExistingAllocatorAdapter(s, variant, Path(work_dir))
                allocated = [r["allocated"] for r in adapter.allocate_in_order(fcfs)]
                if baseline is None:
                    baseline = allocated
                elif allocated != baseline:
                    placeholder_changes += 1
            adapter = ExistingAllocatorAdapter(s, config["existing_allocator"]["placeholder_inputs"], Path(work_dir))
            for policy, order in (("FCFS", fcfs), ("LINEAR", linear_order(s["emergencies"])),
                                  (winner_class, aashray_order(s["emergencies"], winner_params))):
                fresh = scenario_outcome(s, adapter.allocate_in_order(order))
                stored = stored_rows[(s["scenario_id"], policy)]
                for field in ("critical_fulfilled", "total_fulfilled", "cdc", "tdc"):
                    if repr(fresh[field]) != stored[field]:
                        recompute_mismatch += 1

    script_reads = []
    for path in sorted((DEV_ROOT / "scripts").glob("*.py")):
        if path.name == "validate_development.py":
            continue
        if re.search(r"\.(final_priority_level|overall_priority_score|normalized_priority)\b",
                     path.read_text(encoding="utf-8")):
            script_reads.append(path.name)
    report.add("13", "No priority categories affect allocation",
               placeholder_changes == 0 and not script_reads,
               {"scenarios_checked": len(sample),
                "placeholder_variants": len(placeholder_variants),
                "runs_with_changed_quantities": placeholder_changes,
                "scripts_reading_allocator_priority_outputs": script_reads})

    report.add("14", "TDC calculated from actual fulfilled quantities",
               recompute_mismatch == 0 and arithmetic_errors == 0,
               {"fresh_allocator_reruns_compared": len(sample) * 3,
                "mismatches_vs_stored_results": recompute_mismatch,
                "rows_with_arithmetic_inconsistency": arithmetic_errors})

    # 15 ---------------------------------------------------------------
    report.add("15", "CDC uses only fixed GT-critical labels", not critical_required_errors,
               {"critical_required_checked_rows": row_count,
                "rows_not_matching_exact_label_demand": len(critical_required_errors)})

    # 16 ---------------------------------------------------------------
    data_files = sorted(p.relative_to(DEV_ROOT).as_posix() for p in (DEV_ROOT / "data").rglob("*") if p.is_file())
    oversize = copy.deepcopy(config)
    oversize["n_scenarios"] = 12000
    try:
        generate_dataset(oversize)
        refused = False
    except ValueError:
        refused = True
    test_refs = [p.name for p in (DEV_ROOT / "scripts").glob("*.py")
                 if p.name != "validate_development.py"
                 and re.search(r"12[,_]?000|final_test|test_12000", p.read_text(encoding="utf-8"))]
    report.add("16", "No future test data accessed",
               data_files == ["data/development_3000_scenarios.json"] and refused and not test_refs,
               {"data_files": data_files, "generator_refuses_12000": refused,
                "scripts_referencing_a_test_set": test_refs})

    # 17 ---------------------------------------------------------------
    print("Regenerating the dataset for check 17 ...", flush=True)
    first, second = dataset_text(generate_dataset(config)), dataset_text(generate_dataset(config))
    report.add("17", "Dataset reproducible with the stored seed",
               first == second == text and sha256_text(text) == summary["dataset_sha256"],
               {"regenerated_twice_identical": first == second,
                "regenerated_matches_file": first == text,
                "file_matches_evaluated_dataset": sha256_text(text) == summary["dataset_sha256"]})

    # 18 ---------------------------------------------------------------
    tolerance = config["selection_rule"]["tie_tolerance"]
    independent = independent_winner(config_rows, tolerance)
    with TOP_10_PATH.open("r", encoding="utf-8") as file:
        top_1 = next(csv.DictReader(file))["config_id"]
    report.add("18", "Winner selected automatically by the predefined rule",
               independent["config_id"] == winner_id == top_1,
               {"independent_recomputation": independent["config_id"],
                "recorded_winner": winner_id, "top_10_rank_1": top_1})

    # 20 ---------------------------------------------------------------
    stored_manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    current_manifest = application_manifest()
    changed = sorted(k for k in set(stored_manifest) | set(current_manifest)
                     if stored_manifest.get(k) != current_manifest.get(k))
    report.add("20", "Existing AASHRAY application files unchanged",
               not changed and sha256_file(MANIFEST_PATH) == summary["application_manifest_sha256"],
               {"files_in_manifest": len(stored_manifest),
                "includes_pilot_experiment": any(k.startswith("experiments/resource_allocation_pilot/") for k in stored_manifest),
                "changed_since_evaluation": changed[:20]})

    # Additional consistency checks ------------------------------------
    print("Arrival-independence perturbation checks ...", flush=True)
    arrival_fields = ("arrival_offset_seconds", "arrival_timestamp")

    def without(ds, fields):
        clone = copy.deepcopy(ds["scenarios"])
        for s in clone:
            for e in s["emergencies"]:
                for f in fields:
                    e.pop(f)
        return clone

    def values(ds, fields):
        return [tuple(e[f] for f in fields) for s in ds["scenarios"] for e in s["emergencies"]]

    arrival_perturbed = generate_dataset(config, arrival_salt="arrival::validation")
    su_perturbed = generate_dataset(config, su_salt="severity_urgency::validation")
    positions, s_values, u_values, g_values = [], [], [], []
    for s in scenarios:
        lookup = {e["emergency_id"]: e for e in s["emergencies"]}
        order = fcfs_order(arrival_view(s["emergencies"]))
        for p, emergency_id in enumerate(order):
            e = lookup[emergency_id]
            positions.append(p / (len(order) - 1))
            s_values.append(e["severity"])
            u_values.append(e["urgency"])
            g_values.append(e["ground_truth_critical"])
    correlations = {
        "position_vs_severity": statistics.correlation(positions, s_values),
        "position_vs_urgency": statistics.correlation(positions, u_values),
        "position_vs_gt_critical": statistics.correlation(positions, g_values),
    }
    report.add("A1", "Arrival order independent of S, U and GT",
               without(arrival_perturbed, arrival_fields) == without(dataset, arrival_fields)
               and values(arrival_perturbed, ["arrival_offset_seconds"]) != values(dataset, ["arrival_offset_seconds"])
               and values(su_perturbed, ["arrival_offset_seconds"]) == values(dataset, ["arrival_offset_seconds"])
               and all(abs(r) < CORRELATION_LIMIT for r in correlations.values()),
               {"pearson": correlations, "limit_abs": CORRELATION_LIMIT})

    by_class = defaultdict(set)
    for row in config_rows:
        by_class[row["equivalence_class_id"]].add((row["mean_cdc"], row["median_cdc"], row["p10_cdc"]))
    expected_rows = DEVELOPMENT_SCENARIO_COUNT * (len(stored_classes) + 2)
    report.add("A2", "Equivalent configurations share identical metrics; result files complete",
               all(len(v) == 1 for v in by_class.values()) and row_count == expected_rows
               and len(config_rows) == 726,
               {"classes": len(by_class), "per_scenario_rows": row_count,
                "expected_per_scenario_rows": expected_rows})

    search = summary["parameter_search"]
    report.add("A3", "Existing allocator processed every call in the presented order",
               search["allocator_calls"] == search["allocator_calls_order_verified"] > 0,
               {"allocator_calls": search["allocator_calls"]})

    # STOP if anything failed ------------------------------------------
    failed = report.failed()

    if not failed:
        winner_row = next(r for r in config_rows if r["config_id"] == winner_id)
        expected = {k: winner_row[k] for k in ("alpha", "k", "m", "n")}

        if FROZEN_PATH.exists():
            frozen = json.loads(FROZEN_PATH.read_text(encoding="utf-8"))
            freeze_action = "already frozen; verified, not rewritten"
        else:
            commit, dirty = git_state()
            frozen = {
                **expected,
                "config_id": winner_id,
                "equivalence_class_id": summary["winner"]["equivalence_class_id"],
                "equivalent_configurations": summary["winner"]["member_config_ids_of_winning_class"],
                "selection_metric": "mean CDC over the 3,000 development scenarios",
                "selection_rule": config["selection_rule"],
                "selection_trace": summary["winner"]["selection_trace"],
                "development_mean_cdc": summary["winner"]["mean_cdc"],
                "development_median_cdc": summary["winner"]["median_cdc"],
                "development_p10_cdc": summary["winner"]["p10_cdc"],
                "development_scenario_count": DEVELOPMENT_SCENARIO_COUNT,
                "master_seed": config["master_seed"],
                "seed_namespace": config["seed_namespace"],
                "candidate_count": len(grid),
                "ranking_equivalence_class_count": search["ranking_equivalence_classes"],
                "dataset_sha256": summary["dataset_sha256"],
                "candidate_grid_sha256": summary["candidate_grid_sha256"],
                "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "git_commit": commit,
                "git_working_tree_has_uncommitted_or_untracked_files": dirty,
                "statement": FREEZE_STATEMENT,
            }
            write_text(FROZEN_PATH, json_text(frozen))
            freeze_action = "frozen now"

        matches = ({k: frozen[k] for k in ("alpha", "k", "m", "n")} == expected
                   and frozen["config_id"] == winner_id and frozen["statement"] == FREEZE_STATEMENT)
        report.add("19", "Frozen parameters match the recorded winning configuration", matches,
                   {"frozen": {k: frozen[k] for k in ("config_id", "alpha", "k", "m", "n")},
                    "action": freeze_action})
    else:
        report.add("19", "Frozen parameters match the recorded winning configuration", False,
                   {"action": "NOT FROZEN: earlier validation checks failed",
                    "failed_checks": [c["id"] for c in failed]})

    order = [str(i) for i in range(1, 21)] + ["A1", "A2", "A3"]
    report.checks.sort(key=lambda c: order.index(c["id"]))
    output = {
        "n_checks": len(report.checks),
        "n_pass": sum(c["status"] == "PASS" for c in report.checks),
        "n_fail": len(report.failed()),
        "parameters_frozen": not report.failed(),
        "checks": report.checks,
    }
    write_text(VALIDATION_PATH, json_text(output))

    for check in report.checks:
        print(f"[{check['status']}] {check['id']:>3}  {check['name']}")
    print(f"\n{output['n_pass']} PASS, {output['n_fail']} FAIL")

    if report.failed():
        print("STOP: validation failed; parameters were NOT frozen.")
        sys.exit(1)

    print(f"Parameters frozen in {FROZEN_PATH}")


if __name__ == "__main__":
    main()
