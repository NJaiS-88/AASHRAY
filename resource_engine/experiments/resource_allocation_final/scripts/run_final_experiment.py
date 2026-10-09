"""Phase C: run FCFS, frozen AASHRAY and the MILP on every final scenario.

Usage (from the repository root, after generate_final_dataset.py):

    python experiments/resource_allocation_final/scripts/run_final_experiment.py

Refuses to run unless the pre-flight and generator-equivalence proof passed,
the dataset hash equals the freeze record, and no results exist yet (the
experiment is run once; no scenario is re-run or dropped). No statistics
are computed here.

All three methods receive the same scenario object. FCFS and AASHRAY call
the existing allocator (ResourceAllocationService.allocate_batch, unchanged)
with identical placeholder priority inputs; the allocator's processed order
is verified against the presented order on every call (untimed).
"""

import json
import math
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from final_common import (
    DATASET_PATH,
    FREEZE_PATH,
    GENERATOR_EQUIVALENCE_PATH,
    MILP_ALLOCATIONS_PATH,
    POLICY_ALLOCATIONS_PATH,
    PREFLIGHT_PATH,
    RESOURCE_TYPES,
    RUN_METADATA_PATH,
    SCENARIO_RESULTS_PATH,
    csv_text,
    environment_info,
    json_text,
    load_config,
    load_frozen_parameters,
    milp_options,
    read_json,
    scenario_fingerprint,
    sha256_file,
    write_gzip_csv,
    write_text,
)

# Validated implementations (read-only imports).
from policies import aashray_order, arrival_view, fcfs_order, normalized_priority, overall_priority  # noqa: E402
from milp_model import run_scenario  # noqa: E402
from analytical_optimum import analytical_optimum  # noqa: E402
from resource_services.schemas.allocation import AllocationRequest  # noqa: E402
from resource_services.schemas.resource_requirement import ResourceRequirement  # noqa: E402
from resource_services.services.resource_allocation_service import ResourceAllocationService  # noqa: E402


WARM_UP_SCENARIOS = 3

FIELDS = [
    "scenario_id", "scarcity", "size_class", "su_profile",
    "num_emergencies", "num_warehouses", "num_critical_emergencies", "scenario_input_sha256",
    "total_supply", "total_demand", "critical_required", "cdc_defined",
    "critical_fulfilled_FCFS", "CDC_FCFS", "total_fulfilled_FCFS", "TDC_FCFS",
    "fcfs_decision_time_ms", "fcfs_allocation_time_ms", "fcfs_runtime_ms",
    "critical_fulfilled_AASHRAY", "CDC_AASHRAY", "total_fulfilled_AASHRAY", "TDC_AASHRAY",
    "aashray_decision_time_ms", "aashray_allocation_time_ms", "aashray_total_time_ms",
    "critical_fulfilled_MILP", "CDC_MILP",
    "milp_build_time_ms", "milp_solver_time_ms", "milp_total_time_ms",
    "milp_status", "milp_message", "milp_success", "milp_mip_gap", "milp_objective",
    "milp_dual_bound", "milp_proven_optimal", "milp_max_integrality_deviation",
    "milp_total_fulfilled_solver_dependent", "milp_tdc_solver_dependent",
    "analytical_optimum", "analytical_optimum_match",
    "aashray_minus_fcfs_CDC", "aashray_relative_improvement_vs_fcfs", "fcfs_cdc_zero",
    "aashray_milp_gap_absolute", "aashray_milp_gap_relative",
    "milp_cdc_zero_gap_defined_as_zero", "aashray_to_milp_cdc_ratio",
    "aashray_beats_fcfs", "fcfs_beats_aashray", "aashray_equals_fcfs",
    "aashray_reaches_milp", "aashray_within_1pct_milp", "aashray_within_5pct_milp",
    "aashray_within_10pct_milp",
]

POLICY_HEADER = ["scenario_id", "method", "rank", "emergency_id", "ground_truth_critical",
                 "aashray_score"] + [f"required_{r}" for r in RESOURCE_TYPES] \
                + [f"allocated_{r}" for r in RESOURCE_TYPES]
MILP_HEADER = ["scenario_id", "emergency_id", "resource_type", "warehouse_id", "allocated_quantity"]


class AllocationOrderError(RuntimeError):
    pass


def ms(seconds: float) -> float:
    return seconds * 1000.0


def run_policy(service, scenario, order_function, placeholders):
    """Timed: decision (order) and allocation (requests + allocate_batch).
    Untimed: order verification and result extraction."""

    requirements = {e["emergency_id"]: e["resource_requirements"] for e in scenario["emergencies"]}

    started = time.perf_counter()
    order = order_function()
    decided = time.perf_counter()
    requests = [
        AllocationRequest(
            incident_id=emergency_id,
            requirements=ResourceRequirement(**requirements[emergency_id]),
            severity=placeholders["severity"],
            urgency=placeholders["urgency"],
            priority=placeholders["priority"],
        )
        for emergency_id in order
    ]
    results = service.allocate_batch(requests)
    allocated = time.perf_counter()

    if [r.incident_id for r in results] != order:
        raise AllocationOrderError(f"{scenario['scenario_id']}: allocator changed the order")

    allocations = {
        r.incident_id: {f: getattr(r.allocated_resources, f) for f in RESOURCE_TYPES}
        for r in results
    }
    return order, allocations, decided - started, allocated - decided


def policy_outcome(scenario, allocations):
    critical = {e["emergency_id"]: e["ground_truth_critical"] == 1 for e in scenario["emergencies"]}
    total = sum(sum(a.values()) for a in allocations.values())
    critical_total = sum(sum(a.values()) for eid, a in allocations.items() if critical[eid])
    return critical_total, total


def ratio(numerator, denominator):
    return numerator / denominator if denominator else math.nan


def build_row(scenario, config, fcfs, aashray, milp, oracle, fingerprint):
    tie = config["statistics"]["tie_tolerance"]

    emergencies = scenario["emergencies"]
    critical_required = sum(
        sum(e["resource_requirements"].values()) for e in emergencies if e["ground_truth_critical"] == 1
    )
    total_demand = sum(sum(e["resource_requirements"].values()) for e in emergencies)
    total_supply = sum(w["inventory"][r]["available"]
                       for w in scenario["resource_inventory"] for r in RESOURCE_TYPES)
    defined = critical_required > 0

    cdc_f = ratio(fcfs["critical"], critical_required)
    cdc_a = ratio(aashray["critical"], critical_required)
    cdc_m = ratio(milp["critical_fulfilled"], critical_required) if milp["critical_fulfilled"] is not None else math.nan

    delta = cdc_a - cdc_f if defined else math.nan
    relative = delta / cdc_f if defined and cdc_f > 0 else math.nan

    gap_absolute = cdc_m - cdc_a if defined else math.nan
    milp_zero = defined and cdc_m == 0
    if not defined:
        gap_relative = math.nan
    elif milp_zero:
        gap_relative = 0.0          # AASHRAY is then also 0: the optimum is reached
    else:
        gap_relative = gap_absolute / cdc_m

    return {
        "scenario_id": scenario["scenario_id"],
        "scarcity": scenario["scarcity_level"],
        "size_class": scenario["size_class"],
        "su_profile": scenario["su_profile"],
        "num_emergencies": scenario["n_emergencies"],
        "num_warehouses": scenario["n_warehouses"],
        "num_critical_emergencies": sum(e["ground_truth_critical"] for e in emergencies),
        "scenario_input_sha256": fingerprint,
        "total_supply": total_supply,
        "total_demand": total_demand,
        "critical_required": critical_required,
        "cdc_defined": defined,
        "critical_fulfilled_FCFS": fcfs["critical"],
        "CDC_FCFS": cdc_f,
        "total_fulfilled_FCFS": fcfs["total"],
        "TDC_FCFS": ratio(fcfs["total"], total_demand),
        "fcfs_decision_time_ms": ms(fcfs["decision"]),
        "fcfs_allocation_time_ms": ms(fcfs["allocation"]),
        "fcfs_runtime_ms": ms(fcfs["decision"] + fcfs["allocation"]),
        "critical_fulfilled_AASHRAY": aashray["critical"],
        "CDC_AASHRAY": cdc_a,
        "total_fulfilled_AASHRAY": aashray["total"],
        "TDC_AASHRAY": ratio(aashray["total"], total_demand),
        "aashray_decision_time_ms": ms(aashray["decision"]),
        "aashray_allocation_time_ms": ms(aashray["allocation"]),
        "aashray_total_time_ms": ms(aashray["decision"] + aashray["allocation"]),
        "critical_fulfilled_MILP": milp["critical_fulfilled"],
        "CDC_MILP": cdc_m,
        "milp_build_time_ms": ms(milp["model_build_time_seconds"]),
        "milp_solver_time_ms": ms(milp["solver_time_seconds"]),
        "milp_total_time_ms": ms(milp["total_milp_time_seconds"]),
        "milp_status": milp["solver_status"],
        "milp_message": milp["solver_message"],
        "milp_success": milp["solver_success"],
        "milp_mip_gap": milp["mip_gap"],
        "milp_objective": milp["objective_value"],
        "milp_dual_bound": milp["best_bound"],
        "milp_proven_optimal": milp["is_proven_optimum"],
        "milp_max_integrality_deviation": milp["max_integrality_deviation"],
        "milp_total_fulfilled_solver_dependent": milp["total_fulfilled_solver_dependent"],
        "milp_tdc_solver_dependent": milp["tdc_solver_dependent"],
        "analytical_optimum": oracle["analytical_optimum"],
        "analytical_optimum_match": milp["is_proven_optimum"]
        and milp["critical_fulfilled"] == oracle["analytical_optimum"],
        "aashray_minus_fcfs_CDC": delta,
        "aashray_relative_improvement_vs_fcfs": relative,
        "fcfs_cdc_zero": defined and cdc_f == 0,
        "aashray_milp_gap_absolute": gap_absolute,
        "aashray_milp_gap_relative": gap_relative,
        "milp_cdc_zero_gap_defined_as_zero": milp_zero,
        "aashray_to_milp_cdc_ratio": cdc_a / cdc_m if defined and cdc_m > 0 else math.nan,
        "aashray_beats_fcfs": defined and delta > tie,
        "fcfs_beats_aashray": defined and delta < -tie,
        "aashray_equals_fcfs": defined and abs(delta) <= tie,
        "aashray_reaches_milp": defined and gap_absolute <= tie,
        "aashray_within_1pct_milp": defined and gap_relative <= 0.01,
        "aashray_within_5pct_milp": defined and gap_relative <= 0.05,
        "aashray_within_10pct_milp": defined and gap_relative <= 0.10,
    }


def main() -> None:
    config = load_config()

    preflight = read_json(PREFLIGHT_PATH) if PREFLIGHT_PATH.exists() else None
    equivalence = read_json(GENERATOR_EQUIVALENCE_PATH) if GENERATOR_EQUIVALENCE_PATH.exists() else None
    freeze = read_json(FREEZE_PATH) if FREEZE_PATH.exists() else None
    if not (preflight and preflight["passed"]):
        sys.exit("STOP: pre-flight has not passed.")
    if not (equivalence and equivalence["byte_identical"]):
        sys.exit("STOP: generator equivalence proof has not passed.")
    if not (freeze and freeze["frozen"]):
        sys.exit("STOP: the dataset is not frozen.")
    if SCENARIO_RESULTS_PATH.exists():
        sys.exit("STOP: results already exist; the final experiment is run once.")

    dataset_sha256 = sha256_file(DATASET_PATH)
    if dataset_sha256 != freeze["sha256"]:
        sys.exit("STOP: dataset hash differs from the freeze record.")

    frozen = load_frozen_parameters()
    if frozen != config["frozen_aashray"]["expected"]:
        sys.exit(f"STOP: frozen parameters differ from the pre-registered values: {frozen}")

    options = milp_options()
    placeholders = config["methods"]["placeholder_inputs"]
    dataset = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    scenarios = dataset["scenarios"]

    run_id = uuid.uuid4().hex
    started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    wall_started = time.perf_counter()

    rows, policy_rows, milp_rows = [], [], []

    with TemporaryDirectory(prefix="aashray_final_") as work_dir:

        def prepare(scenario):
            # Untimed: the existing allocator only loads warehouses from a file.
            path = Path(work_dir) / "warehouses.json"
            path.write_text(json.dumps(scenario["resource_inventory"]), encoding="utf-8")
            return ResourceAllocationService(path)

        def run_all(scenario):
            emergencies = scenario["emergencies"]
            service = prepare(scenario)
            fcfs = run_policy(service, scenario,
                              lambda: fcfs_order(arrival_view(emergencies)), placeholders)
            aashray = run_policy(service, scenario,
                                 lambda: aashray_order(emergencies, frozen), placeholders)
            # A fresh copy per solve: scipy.optimize.milp removes "disp" from the
            # options dict it is given, which would otherwise alter the record.
            milp = run_scenario(scenario, dict(options))
            return fcfs, aashray, milp

        # Warm-up: not recorded.
        for scenario in scenarios[:WARM_UP_SCENARIOS]:
            run_all(scenario)

        for index, scenario in enumerate(scenarios, start=1):
            fingerprint = scenario_fingerprint(scenario)
            fcfs, aashray, milp = run_all(scenario)
            oracle = analytical_optimum(scenario)

            outcomes = {}
            for method, (order, allocations, decision, allocation) in (("FCFS", fcfs), ("AASHRAY", aashray)):
                critical, total = policy_outcome(scenario, allocations)
                outcomes[method] = {"critical": critical, "total": total,
                                    "decision": decision, "allocation": allocation}

                lookup = {e["emergency_id"]: e for e in scenario["emergencies"]}
                for rank, emergency_id in enumerate(order, start=1):
                    e = lookup[emergency_id]
                    score = overall_priority(e["severity"], e["urgency"], frozen["k"], frozen["m"],
                                             frozen["n"], normalized_priority(e["severity"], e["urgency"], frozen["alpha"])) \
                        if method == "AASHRAY" else None
                    policy_rows.append(
                        [scenario["scenario_id"], method, rank, emergency_id, e["ground_truth_critical"], score]
                        + [e["resource_requirements"][r] for r in RESOURCE_TYPES]
                        # Raw allocator values, so validation can check integrality.
                        + [allocations[emergency_id][r] for r in RESOURCE_TYPES]
                    )

            for a in milp["allocations"]:
                milp_rows.append([scenario["scenario_id"], a["emergency_id"], a["resource_type"],
                                  a["warehouse_id"], a["allocated_quantity"]])

            rows.append(build_row(scenario, config, outcomes["FCFS"], outcomes["AASHRAY"],
                                  milp, oracle, fingerprint))

            if index % 1000 == 0:
                print(f"  {index}/{len(scenarios)} scenarios", flush=True)

    wall_seconds = time.perf_counter() - wall_started

    write_text(SCENARIO_RESULTS_PATH, csv_text(rows, FIELDS))
    write_gzip_csv(POLICY_ALLOCATIONS_PATH, POLICY_HEADER, policy_rows)
    write_gzip_csv(MILP_ALLOCATIONS_PATH, MILP_HEADER, milp_rows)

    write_text(RUN_METADATA_PATH, json_text({
        "run_id": run_id,
        "started_at_utc": started_at,
        "finished_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "wall_clock_seconds_including_io": wall_seconds,
        "process_id": os.getpid(),
        "dataset_sha256_verified": dataset_sha256,
        "freeze_record_frozen_at_utc": freeze["frozen_at_utc"],
        "scenarios_run": len(rows),
        "scenarios_in_dataset": len(scenarios),
        "frozen_parameters_used": frozen,
        "milp_options_used": options,
        "allocator_placeholders": placeholders,
        "warm_up_scenarios": [s["scenario_id"] for s in scenarios[:WARM_UP_SCENARIOS]],
        "timing_methodology": config["timing"],
        "environment": environment_info(),
    }))
    print(f"Run complete: {len(rows)} scenarios, all three methods, in {wall_seconds:.1f}s")


if __name__ == "__main__":
    main()
