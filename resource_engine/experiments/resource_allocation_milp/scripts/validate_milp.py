"""Validate the MILP benchmark (25 required checks plus determinism).

Usage (from the repository root, after solve_milp.py):

    python experiments/resource_allocation_milp/scripts/validate_milp.py

Wherever possible the checks are independent of the solver: constraints are
re-checked from the saved allocations against the original dataset, and the
analytical optimum and CDC are recomputed here with separate code.
Exit code 1 means STOP.
"""

import copy
import csv
import gzip
import json
import math
import re
import sys
from collections import defaultdict

from milp_common import (
    ALLOCATIONS_PATH,
    DEVELOPMENT_DATASET_PATH,
    DEVELOPMENT_SCENARIO_COUNT,
    FROZEN_PARAMETERS_PATH,
    HAND_CHECK_PATH,
    MANIFEST_PATH,
    MILP_ROOT,
    REPO_ROOT,
    RESOURCE_TYPES,
    RESULTS_CSV_PATH,
    SUMMARY_PATH,
    VALIDATION_PATH,
    json_text,
    load_config,
    protected_manifest,
    write_text,
)
from milp_model import build_model, is_proven_optimum, run_scenario
from hand_check_tests import run_tests


EXPECTED_FROZEN = {"config_id": "C045", "alpha": 0.0, "k": 0.5, "m": 0.0, "n": 0.5}


class Report:
    def __init__(self):
        self.checks = []

    def add(self, check_id, name, passed, details):
        self.checks.append({"id": check_id, "name": name,
                            "status": "PASS" if passed else "FAIL", "details": details})

    def failed(self):
        return [c for c in self.checks if c["status"] == "FAIL"]


def read_results():
    rows = []
    with RESULTS_CSV_PATH.open("r", encoding="utf-8") as file:
        for row in csv.DictReader(file):
            rows.append(row)
    return rows


def number(text):
    return math.nan if text in ("", "NaN") else float(text)


def main() -> None:
    config = load_config()
    options = config["solver"]["options"]
    report = Report()

    dataset = json.loads(DEVELOPMENT_DATASET_PATH.read_text(encoding="utf-8"))
    scenarios = {s["scenario_id"]: s for s in dataset["scenarios"]}
    rows = read_results()
    by_id = {r["scenario_id"]: r for r in rows}

    # 1 ---------------------------------------------------------------
    shape_errors = []
    for scenario in list(scenarios.values())[::100]:
        model = build_model(scenario)
        n_e, n_w = len(scenario["emergencies"]), len(scenario["resource_inventory"])
        matrix = model.constraints.A
        column_counts = matrix.getnnz(axis=0)
        ok = (
            model.number_variables == n_e * 3 * n_w
            and model.number_constraints == 3 * n_w + 3 * n_e
            and matrix.shape == (3 * n_w + 3 * n_e, n_e * 3 * n_w)
            and (column_counts == 2).all()          # one supply row + one demand row
            and set(matrix.data) == {1.0}
            and (model.bounds.lb == 0).all() and math.isinf(model.bounds.ub.max())
            and (model.integrality == 1).all()
            and [-v for v in model.objective] == [
                float(model.critical[e]) for e in range(n_e) for _ in range(3) for _ in range(n_w)]
        )
        if not ok:
            shape_errors.append(scenario["scenario_id"])
    report.add("1", "MILP model constructs successfully", not shape_errors,
               {"scenarios_checked": len(list(scenarios.values())[::100]),
                "structure": "E*3*W integer variables >= 0; 3W supply + 3E demand rows; "
                             "each variable in exactly one supply and one demand row; "
                             "objective = GT_critical; no other constraints",
                "malformed": shape_errors})

    # 2-9 -------------------------------------------------------------
    rerun = {t["id"]: t for t in run_tests(options)}
    stored = {t["id"]: t for t in json.loads(HAND_CHECK_PATH.read_text(encoding="utf-8"))["tests"]}
    for number_, test_id in enumerate([f"TEST-0{i}" for i in range(1, 9)], start=2):
        report.add(str(number_), f"Hand-check {test_id} passes",
                   rerun[test_id]["passed"] and stored[test_id]["passed"],
                   {"description": rerun[test_id]["description"],
                    "expected": rerun[test_id]["expected"],
                    "got_critical_fulfilled": rerun[test_id]["got"]["critical_fulfilled"],
                    "got_cdc": rerun[test_id]["got"]["cdc"],
                    "checks": rerun[test_id]["checks"]})

    # 10-13 (from the saved allocations, against the original dataset) --
    warehouse_use = defaultdict(int)
    emergency_use = defaultdict(int)
    critical_fulfilled = defaultdict(int)
    non_integer, negative_or_zero, allocation_rows = 0, 0, 0
    critical_label = {(sid, e["emergency_id"]): e["ground_truth_critical"]
                      for sid, s in scenarios.items() for e in s["emergencies"]}

    with gzip.open(ALLOCATIONS_PATH, "rt", encoding="utf-8", newline="") as file:
        for a in csv.DictReader(file):
            allocation_rows += 1
            if not re.fullmatch(r"-?\d+", a["allocated_quantity"]):
                non_integer += 1
                continue
            quantity = int(a["allocated_quantity"])
            if quantity <= 0:
                negative_or_zero += 1
            warehouse_use[(a["scenario_id"], a["warehouse_id"], a["resource_type"])] += quantity
            emergency_use[(a["scenario_id"], a["emergency_id"], a["resource_type"])] += quantity
            if critical_label[(a["scenario_id"], a["emergency_id"])]:
                critical_fulfilled[a["scenario_id"]] += quantity

    supply_violations = [
        key for key, used in warehouse_use.items()
        if used > next(w for w in scenarios[key[0]]["resource_inventory"]
                       if w["warehouse_id"] == key[1])["inventory"][key[2]]["available"]
    ]
    demand_violations = [
        key for key, used in emergency_use.items()
        if used > next(e for e in scenarios[key[0]]["emergencies"]
                       if e["emergency_id"] == key[1])["resource_requirements"][key[2]]
    ]
    max_deviation = max(number(r["max_integrality_deviation"]) for r in rows)

    report.add("10", "Supply constraints are never violated", not supply_violations,
               {"warehouse_type_pairs_checked": len(warehouse_use), "violations": supply_violations[:10]})
    report.add("11", "Demand constraints are never violated", not demand_violations,
               {"emergency_type_pairs_checked": len(emergency_use), "violations": demand_violations[:10]})
    report.add("12", "x variables are integer",
               non_integer == 0 and max_deviation <= config["solver"]["integrality_tolerance"],
               {"non_integer_allocation_rows": non_integer,
                "max_solver_deviation_from_integer": max_deviation,
                "tolerance": config["solver"]["integrality_tolerance"]})
    report.add("13", "No allocation is negative", negative_or_zero == 0,
               {"allocation_rows": allocation_rows, "negative_or_zero_rows": negative_or_zero,
                "note": "only non-zero allocations are stored"})

    # 14-16 (independent analytical optimum and CDC) -------------------
    exceeds, mismatches, cdc_errors, fulfilled_errors = [], [], [], []
    for sid, scenario in scenarios.items():
        row = by_id[sid]
        critical_demand = {r: sum(e["resource_requirements"][r] for e in scenario["emergencies"]
                                  if e["ground_truth_critical"] == 1) for r in RESOURCE_TYPES}
        supply = {r: sum(w["inventory"][r]["available"] for w in scenario["resource_inventory"])
                  for r in RESOURCE_TYPES}
        oracle = sum(min(critical_demand[r], supply[r]) for r in RESOURCE_TYPES)
        required = sum(critical_demand.values())
        got = int(row["critical_fulfilled"])

        if got > oracle:
            exceeds.append(sid)
        if row["is_proven_optimum"] == "True" and got != oracle:
            mismatches.append(sid)
        if int(row["analytical_optimum"]) != oracle:
            mismatches.append(sid)
        if critical_fulfilled[sid] != got:
            fulfilled_errors.append(sid)
        expected_cdc = got / required if required else math.nan
        if int(row["critical_required"]) != required or not (
                (math.isnan(expected_cdc) and math.isnan(number(row["cdc"])))
                or number(row["cdc"]) == expected_cdc):
            cdc_errors.append(sid)

    optimal_rows = [r for r in rows if r["is_proven_optimum"] == "True"]
    report.add("14", "MILP critical fulfilment never exceeds the analytical optimum", not exceeds,
               {"scenarios": len(rows), "exceeding": exceeds[:10]})
    report.add("15", "MILP critical fulfilment equals the analytical optimum on every solved scenario",
               not mismatches and len(optimal_rows) == len(rows),
               {"proven_optimal_scenarios": len(optimal_rows),
                "matching": len(optimal_rows) - len(set(mismatches)),
                "mismatching": sorted(set(mismatches))[:10]})
    report.add("16", "CDC is calculated correctly", not cdc_errors and not fulfilled_errors,
               {"cdc_mismatches": cdc_errors[:10],
                "critical_fulfilled_vs_allocations_mismatches": fulfilled_errors[:10]})

    # 17 --------------------------------------------------------------
    zero_scenario = copy.deepcopy(next(iter(scenarios.values())))
    zero_scenario["scenario_id"] = "ZERO-CRITICAL"
    for e in zero_scenario["emergencies"]:
        e["ground_truth_critical"] = 0
    zero = run_scenario(zero_scenario, options)
    zero_rows_with_number = [r["scenario_id"] for r in rows
                             if int(r["critical_required"]) == 0 and r["cdc"] != "NaN"]
    report.add("17", "Zero-critical-demand handling is correct",
               math.isnan(zero["cdc"]) and zero["critical_required"] == 0
               and zero["objective_value"] == 0 and zero["is_proven_optimum"]
               and rerun["TEST-08"]["got"]["cdc_undefined"] and not zero_rows_with_number,
               {"modified_development_scenario_cdc": "NaN" if math.isnan(zero["cdc"]) else zero["cdc"],
                "hand_check_TEST_08_cdc_undefined": rerun["TEST-08"]["got"]["cdc_undefined"],
                "development_rows_with_zero_critical_demand_but_numeric_cdc": zero_rows_with_number})

    # 18 --------------------------------------------------------------
    report.add("18", "Solver status is recorded",
               all(r["solver_status"] != "" and r["solver_message"] for r in rows),
               {"status_values": sorted({r["solver_status"] for r in rows})})

    # 19 --------------------------------------------------------------
    labelling_cases = {
        "time_limit_incumbent": (is_proven_optimum(1, False, 0.0, 10.0, 10.0), False),
        "optimal_status_with_gap": (is_proven_optimum(0, True, 1e-4, 10.0, 11.0), False),
        "bound_not_closed": (is_proven_optimum(0, True, 0.0, 10.0, 11.0), False),
        "not_successful": (is_proven_optimum(0, False, 0.0, 10.0, 10.0), False),
        "missing_gap": (is_proven_optimum(0, True, None, 10.0, 10.0), False),
        "proven_optimum": (is_proven_optimum(0, True, 0.0, 10.0, 10.0), True),
    }
    labelling_ok = all(got == expected for got, expected in labelling_cases.values())
    largest = max(scenarios.values(), key=lambda s: s["n_emergencies"] * s["n_warehouses"])
    limited = run_scenario(largest, {**options, "time_limit": 1e-9})
    limited_ok = limited["solver_status"] == 0 or not limited["is_proven_optimum"]
    labelled_rows_ok = all(
        r["solver_status"] == "0" and number(r["mip_gap"]) == 0
        and abs(number(r["objective_value"]) - number(r["best_bound"])) <= 1e-6
        for r in optimal_rows)
    report.add("19", "Non-optimal solutions are not labelled optimum",
               labelling_ok and limited_ok and labelled_rows_ok,
               {"labelling_unit_cases": {k: v[0] for k, v in labelling_cases.items()},
                "real_time_limited_solve": {
                    "scenario": largest["scenario_id"],
                    "solver_status": limited["solver_status"],
                    "solver_message": limited["solver_message"],
                    "labelled_proven_optimum": limited["is_proven_optimum"]},
                "every_labelled_optimum_has_status_0_gap_0_closed_bound": labelled_rows_ok})

    # 20 --------------------------------------------------------------
    timing_ok = all(
        number(r["model_build_time_seconds"]) > 0 and number(r["solver_time_seconds"]) > 0
        and math.isclose(number(r["total_milp_time_seconds"]),
                         number(r["model_build_time_seconds"]) + number(r["solver_time_seconds"]),
                         rel_tol=1e-9)
        for r in rows)
    report.add("20", "Timing measurements are recorded", timing_ok,
               {"rows": len(rows), "fields": ["model_build_time_seconds", "solver_time_seconds",
                                              "total_milp_time_seconds"]})

    # 21-24 -----------------------------------------------------------
    stored_manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    current_manifest = protected_manifest()

    def changed(group):
        a, b = stored_manifest[group], current_manifest[group]
        return sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))

    for check_id, group, name in (("21", "application", "Existing application files are unchanged"),
                                  ("22", "pilot", "Pilot files are unchanged"),
                                  ("23", "development", "Development files are unchanged")):
        diff = changed(group)
        report.add(check_id, name, not diff and len(stored_manifest[group]) > 0,
                   {"files": len(stored_manifest[group]), "changed": diff[:20]})

    frozen = json.loads(FROZEN_PARAMETERS_PATH.read_text(encoding="utf-8"))
    frozen_key = FROZEN_PARAMETERS_PATH.relative_to(REPO_ROOT).as_posix()
    report.add("24", "Frozen AASHRAY parameters are unchanged",
               {k: frozen[k] for k in EXPECTED_FROZEN} == EXPECTED_FROZEN
               and stored_manifest["development"][frozen_key] == current_manifest["development"][frozen_key],
               {"frozen": {k: frozen[k] for k in EXPECTED_FROZEN},
                "file_hash_unchanged": stored_manifest["development"][frozen_key]
                == current_manifest["development"][frozen_key]})

    # 25 --------------------------------------------------------------
    def is_scenario_dataset(path):
        # A scenario dataset is a JSON object with a top-level "scenarios" list.
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            return False
        return isinstance(data, dict) and isinstance(data.get("scenarios"), list)

    milp_data = [p.relative_to(MILP_ROOT).as_posix() for p in MILP_ROOT.rglob("*.json")
                 if p.is_file() and is_scenario_dataset(p)]
    script_refs = [p.name for p in (MILP_ROOT / "scripts").glob("*.py")
                   if p.name != "validate_milp.py"
                   and re.search(r"12[,_]?000|final_test|test_12000", p.read_text(encoding="utf-8"))]
    report.add("25", "No 12,000 test data is accessed",
               len(rows) == DEVELOPMENT_SCENARIO_COUNT == len(scenarios)
               and all(r["scenario_id"].startswith("DEV-") for r in rows)
               and not milp_data and not script_refs,
               {"input": config["input_dataset"], "scenarios_solved": len(rows),
                "scenario_datasets_inside_milp_folder": milp_data,
                "scripts_referencing_a_test_set": script_refs})

    # D1 Determinism --------------------------------------------------
    summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    resolve_mismatch = []
    for sid in summary["subset_stage"]["scenario_ids"]:
        again = run_scenario(scenarios[sid], options)
        row = by_id[sid]
        if (again["objective_value"] != number(row["objective_value"])
                or again["critical_fulfilled"] != int(row["critical_fulfilled"])
                or repr(again["cdc"]) != row["cdc"]):
            resolve_mismatch.append(sid)
    report.add("D1", "Identical input and configuration give identical objective and CDC",
               not resolve_mismatch and not summary["determinism"]["objective_cdc_or_oracle_mismatches"],
               {"subset_solved_in_run_twice": summary["subset_stage"]["solved"],
                "resolved_again_in_validation": len(summary["subset_stage"]["scenario_ids"]),
                "mismatches": resolve_mismatch})

    # Output ----------------------------------------------------------
    failed = report.failed()
    output = {"n_checks": len(report.checks), "n_pass": len(report.checks) - len(failed),
              "n_fail": len(failed), "checks": report.checks}
    write_text(VALIDATION_PATH, json_text(output))

    for c in report.checks:
        print(f"[{c['status']}] {c['id']:>3}  {c['name']}")
    print(f"\n{output['n_pass']} PASS, {output['n_fail']} FAIL")

    if failed:
        print("STOP: MILP validation failed.")
        sys.exit(1)


if __name__ == "__main__":
    main()
