"""Solve the MILP benchmark on the development scenarios.

Usage (from the repository root, after hand_check_tests.py has passed):

    python experiments/resource_allocation_milp/scripts/solve_milp.py

1. Refuses to run unless every hand check passed.
2. Records hashes of all protected files (application, pilot, development).
3. Solves a deterministic 50-scenario subset (every 60th scenario). STOPS
   unless every one is a proven optimum equal to the analytical optimum.
4. Solves all 3,000 development scenarios.

The development dataset is only read. Nothing here touches AASHRAY
parameters. Exit code 1 means STOP.
"""

import csv
import ctypes
import gzip
import io
import json
import math
import os
import platform
import statistics
import sys
import time
from collections import Counter

import numpy
import scipy

from analytical_optimum import analytical_optimum
from milp_common import (
    ALLOCATIONS_PATH,
    DEVELOPMENT_DATASET_PATH,
    DEVELOPMENT_SCENARIO_COUNT,
    ENVIRONMENT_PATH,
    HAND_CHECK_PATH,
    MANIFEST_PATH,
    RESULTS_CSV_PATH,
    SUMMARY_PATH,
    json_text,
    load_config,
    protected_manifest,
    sha256_file,
    write_text,
)
from milp_model import run_scenario


SUBSET_STEP = 60

RESULT_FIELDS = [
    "scenario_id", "scarcity_level", "size_class", "n_emergencies", "n_warehouses",
    "n_ground_truth_critical", "solver_status", "solver_message", "is_proven_optimum",
    "objective_value", "best_bound", "mip_gap", "mip_node_count",
    "critical_required", "critical_fulfilled", "critical_unmet", "cdc",
    "analytical_optimum", "matches_analytical_optimum", "max_integrality_deviation",
    "total_required", "total_fulfilled_solver_dependent", "tdc_solver_dependent",
    "number_variables", "number_constraints",
    "model_build_time_seconds", "solver_time_seconds", "total_milp_time_seconds",
]


def log(message: str) -> None:
    print(message, flush=True)


def solver_environment(options: dict) -> dict:
    try:
        from scipy.optimize._highspy import _core
        highs = f"{_core.HIGHS_VERSION_MAJOR}.{_core.HIGHS_VERSION_MINOR}.{_core.HIGHS_VERSION_PATCH}"
    except Exception:
        highs = None

    cpu_name = platform.processor()
    if sys.platform == "win32":
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                 r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
            cpu_name = winreg.QueryValueEx(key, "ProcessorNameString")[0].strip()
        except OSError:
            pass

    try:
        import psutil
        ram = psutil.virtual_memory().total
        physical_cores = psutil.cpu_count(logical=False)
    except ImportError:
        ram, physical_cores = None, None

    return {
        "cpu": cpu_name,
        "physical_cores": physical_cores,
        "logical_cpus": os.cpu_count(),
        "ram_bytes": ram,
        "ram_gib": round(ram / 2**30, 2) if ram else None,
        "os": platform.platform(),
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "solver_name": "HiGHS (via scipy.optimize.milp)",
        "solver_version": highs,
        "scipy_version": scipy.__version__,
        "numpy_version": numpy.__version__,
        "solver_options": options,
        "timer": "time.perf_counter",
        "note": "The later AASHRAY-vs-MILP timing comparison must run on this same machine and environment.",
    }


def solve_with_oracle(scenario: dict, options: dict) -> dict:
    outcome = run_scenario(scenario, options)
    oracle = analytical_optimum(scenario)

    outcome["analytical_optimum"] = oracle["analytical_optimum"]
    outcome["matches_analytical_optimum"] = (
        outcome["is_proven_optimum"]
        and outcome["critical_fulfilled"] == oracle["analytical_optimum"]
    )

    outcome["scarcity_level"] = scenario["scarcity_level"]
    outcome["size_class"] = scenario["size_class"]
    outcome["n_emergencies"] = scenario["n_emergencies"]
    outcome["n_warehouses"] = scenario["n_warehouses"]
    outcome["n_ground_truth_critical"] = scenario["n_ground_truth_critical"]

    return outcome


def stats(values: list[float]) -> dict:
    cuts = statistics.quantiles(values, n=100, method="inclusive")
    return {
        "mean": statistics.fmean(values),
        "median": statistics.median(values),
        "p95": cuts[94],
        "min": min(values),
        "max": max(values),
    }


def format_value(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return "NaN" if math.isnan(value) else repr(value)
    return str(value)


def results_csv(rows: list[dict]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(RESULT_FIELDS)
    for row in rows:
        writer.writerow([format_value(row[field]) for field in RESULT_FIELDS])
    return buffer.getvalue()


def write_allocations(rows: list[dict]) -> None:
    # Non-zero allocations only; gzip with mtime=0 for byte-reproducibility.
    ALLOCATIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(ALLOCATIONS_PATH, "wb") as raw:
        with gzip.GzipFile(filename="development_milp_allocations.csv", fileobj=raw,
                           mode="wb", mtime=0) as compressed:
            with io.TextIOWrapper(compressed, encoding="utf-8", newline="\n") as text:
                writer = csv.writer(text, lineterminator="\n")
                writer.writerow(["scenario_id", "emergency_id", "resource_type",
                                 "warehouse_id", "allocated_quantity"])
                for row in rows:
                    for a in row["allocations"]:
                        writer.writerow([row["scenario_id"], a["emergency_id"],
                                         a["resource_type"], a["warehouse_id"],
                                         a["allocated_quantity"]])


def main() -> None:
    config = load_config()
    options = config["solver"]["options"]

    hand_checks = json.loads(HAND_CHECK_PATH.read_text(encoding="utf-8")) if HAND_CHECK_PATH.exists() else None
    if not hand_checks or not hand_checks["all_passed"]:
        sys.exit("STOP: run hand_check_tests.py first; all hand checks must pass.")

    write_text(MANIFEST_PATH, json_text(protected_manifest()))
    log("Recorded protected-file hashes")

    dataset = json.loads(DEVELOPMENT_DATASET_PATH.read_text(encoding="utf-8"))
    scenarios = dataset["scenarios"]
    if len(scenarios) != DEVELOPMENT_SCENARIO_COUNT:
        sys.exit(f"STOP: expected {DEVELOPMENT_SCENARIO_COUNT} development scenarios.")

    write_text(ENVIRONMENT_PATH, json_text(solver_environment(options)))

    # Warm-up (not recorded) so library loading is not timed.
    run_scenario(scenarios[0], options)

    # ---- Stage 1: 50-scenario subset ----
    subset = scenarios[::SUBSET_STEP]
    subset_rows = [solve_with_oracle(s, options) for s in subset]
    subset_ok = all(r["is_proven_optimum"] and r["matches_analytical_optimum"] for r in subset_rows)
    log(f"Subset: {len(subset_rows)} solved, "
        f"{sum(r['is_proven_optimum'] for r in subset_rows)} proven optimal, "
        f"{sum(r['matches_analytical_optimum'] for r in subset_rows)} equal the analytical optimum")
    if not subset_ok:
        bad = [r["scenario_id"] for r in subset_rows
               if not (r["is_proven_optimum"] and r["matches_analytical_optimum"])]
        sys.exit(f"STOP: subset validation failed for {bad[:10]}; full run not started.")

    # ---- Stage 2: all 3,000 scenarios ----
    rows = []
    for index, scenario in enumerate(scenarios, start=1):
        rows.append(solve_with_oracle(scenario, options))
        if index % 500 == 0:
            log(f"  solved {index}/{len(scenarios)}")

    # Same input + same configuration -> same objective (subset solved twice).
    full_by_id = {r["scenario_id"]: r for r in rows}
    determinism_mismatches = [
        r["scenario_id"] for r in subset_rows
        if (r["objective_value"], r["critical_fulfilled"], r["cdc"], r["analytical_optimum"])
        != (full_by_id[r["scenario_id"]]["objective_value"],
            full_by_id[r["scenario_id"]]["critical_fulfilled"],
            full_by_id[r["scenario_id"]]["cdc"],
            full_by_id[r["scenario_id"]]["analytical_optimum"])
    ]

    write_text(RESULTS_CSV_PATH, results_csv(rows))
    write_allocations(rows)

    optimal = [r for r in rows if r["is_proven_optimum"]]
    cdc_values = [r["cdc"] for r in optimal if not math.isnan(r["cdc"])]

    summary = {
        "experiment": config["experiment"],
        "role": config["role"],
        "input_dataset": config["input_dataset"],
        "input_dataset_sha256": sha256_file(DEVELOPMENT_DATASET_PATH),
        "solver": f"HiGHS via scipy.optimize.milp (scipy {scipy.__version__})",
        "solver_options": options,
        "subset_stage": {
            "rule": f"every {SUBSET_STEP}th development scenario",
            "scenario_ids": [r["scenario_id"] for r in subset_rows],
            "solved": len(subset_rows),
            "proven_optimal": sum(r["is_proven_optimum"] for r in subset_rows),
            "equal_to_analytical_optimum": sum(r["matches_analytical_optimum"] for r in subset_rows),
        },
        "full_run": {
            "scenarios_solved": len(rows),
            "proven_optimal": len(optimal),
            "non_optimal_or_failed": len(rows) - len(optimal),
            "solver_status_counts": dict(Counter(r["solver_status"] for r in rows)),
            "equal_to_analytical_optimum": sum(r["matches_analytical_optimum"] for r in rows),
            "not_equal_to_analytical_optimum": sum(not r["matches_analytical_optimum"] for r in rows),
            "scenarios_with_undefined_cdc": sum(math.isnan(r["cdc"]) for r in rows),
            "solved_at_root_node": sum(r["mip_node_count"] in (0, 1) for r in rows),
            "max_integrality_deviation": max(
                (r["max_integrality_deviation"] for r in rows if r["max_integrality_deviation"] is not None),
                default=None),
        },
        "cdc": {
            "all": stats(cdc_values),
            "by_scarcity": {
                level: stats([r["cdc"] for r in optimal if r["scarcity_level"] == level])
                for level in ("LOW", "MODERATE", "HIGH")
            },
        },
        "timing_seconds": {
            "model_build": stats([r["model_build_time_seconds"] for r in rows]),
            "solver": stats([r["solver_time_seconds"] for r in rows]),
            "total_milp": stats([r["total_milp_time_seconds"] for r in rows]),
            "by_size_class_total_milp": {
                size: stats([r["total_milp_time_seconds"] for r in rows if r["size_class"] == size])
                for size in ("SMALL", "MEDIUM", "LARGE")
            },
            "note": "Build + solve only; excludes file loading, start-up and result extraction. Timings vary between runs and machines.",
        },
        "model_size": {
            "variables": stats([r["number_variables"] for r in rows]),
            "constraints": stats([r["number_constraints"] for r in rows]),
        },
        "determinism": {
            "check": "the 50 subset scenarios, solved twice with identical input and configuration",
            "objective_cdc_or_oracle_mismatches": determinism_mismatches,
        },
        "tdc_solver_dependent": {
            "note": config["tdc_note"],
            "mean": statistics.fmean(r["tdc_solver_dependent"] for r in optimal),
        },
        "structural_note": (
            "With fungible stock and no coupling between resource types, the MILP optimum "
            "always equals the analytical optimum sum_r min(critical demand_r, supply_r). The "
            "constraint matrix is a transportation (bipartite network) matrix, which is totally "
            "unimodular, so the LP relaxation already has an integral optimum."
        ),
    }
    write_text(SUMMARY_PATH, json_text(summary))

    log(f"Full run: {len(rows)} solved, {len(optimal)} proven optimal, "
        f"{summary['full_run']['equal_to_analytical_optimum']} equal the analytical optimum")

    if summary["full_run"]["not_equal_to_analytical_optimum"] or len(optimal) != len(rows) or determinism_mismatches:
        sys.exit("STOP: not every scenario is a proven optimum equal to the analytical optimum.")


if __name__ == "__main__":
    main()
