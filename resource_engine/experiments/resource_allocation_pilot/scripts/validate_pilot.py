"""Automated validation of the pilot dataset, methodology and results.

Usage (from the repository root, after generate + run):

    python experiments/resource_allocation_pilot/scripts/validate_pilot.py

Writes results/validation_report.json and exits non-zero if any check FAILs.
A check that cannot run yet (e.g. the AASHRAY condition without parameters)
is reported as SKIPPED with the reason, never as PASS.
"""

import copy
import csv
import json
import math
import random
import re
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

from allocator_adapter import ExistingAllocatorAdapter
from generate_pilot_dataset import generate_dataset
from orderings import (
    aashray_order,
    aashray_parameters_status,
    arrival_view,
    fcfs_order,
    overall_priority,
)
from pilot_common import (
    DATASET_PATH,
    PILOT_RESULTS_PATH,
    PILOT_ROOT,
    PILOT_SCENARIO_COUNT,
    VALIDATION_PATH,
    derive_seed,
    dump_json,
    ensure_repo_on_path,
    json_text,
    load_config,
)
from run_pilot import (
    condition_orders,
    load_dataset,
    render_outputs,
    run_pilot,
)

ensure_repo_on_path()

from resource_services.schemas.resource_requirement import (  # noqa: E402
    ResourceRequirement,
)
from resource_services.schemas.warehouse import Warehouse  # noqa: E402


RESOURCE_TYPES = ("water", "food", "medical_kits")
ARRIVAL_FIELDS = {"arrival_offset_seconds", "arrival_timestamp"}
CORRELATION_LIMIT = 0.05


class Report:
    def __init__(self):
        self.checks = []

    def add(self, check_id, name, passed, details, skipped_reason=None):
        if skipped_reason is not None:
            status = "SKIPPED"
            details = {"reason": skipped_reason, **(details or {})}
        else:
            status = "PASS" if passed else "FAIL"

        self.checks.append(
            {
                "id": check_id,
                "name": name,
                "status": status,
                "details": details,
            }
        )

    def failed(self):
        return [check for check in self.checks if check["status"] == "FAIL"]


def all_emergencies(dataset):
    for scenario in dataset["scenarios"]:
        for emergency in scenario["emergencies"]:
            yield scenario, emergency


def exact_reference_score(severity: float, urgency: float) -> Decimal:
    # Exact decimal arithmetic on the stored 4-decimal values.
    value = (Decimal(repr(severity)) + Decimal(repr(urgency))) / 2
    return value.quantize(Decimal("0.000001"))


def load_results_rows():
    with PILOT_RESULTS_PATH.open("r", encoding="utf-8") as file:
        return list(csv.DictReader(file))


def strip_fields(dataset, fields):
    stripped = copy.deepcopy(dataset)
    for _, emergency in all_emergencies(stripped):
        for field in fields:
            emergency.pop(field)
    return stripped


def emergency_values(dataset, fields):
    return [
        tuple(emergency[field] for field in fields)
        for _, emergency in all_emergencies(dataset)
    ]


def pearson(xs, ys):
    return statistics.correlation(xs, ys)


def main() -> None:
    config = load_config()
    dataset, dataset_sha256 = load_dataset()
    scenarios = dataset["scenarios"]
    report = Report()

    # 1. Exactly 500 scenarios ------------------------------------------
    report.add(
        "1",
        "Exactly 500 scenarios exist",
        len(scenarios) == PILOT_SCENARIO_COUNT
        and dataset["n_scenarios"] == PILOT_SCENARIO_COUNT
        and config["n_scenarios"] == PILOT_SCENARIO_COUNT,
        {"scenarios_in_file": len(scenarios)},
    )

    # 2. Unique scenario ids --------------------------------------------
    scenario_ids = [scenario["scenario_id"] for scenario in scenarios]
    emergency_ids = [e["emergency_id"] for _, e in all_emergencies(dataset)]
    report.add(
        "2",
        "Every scenario has a unique scenario_id",
        len(set(scenario_ids)) == len(scenario_ids)
        and len(set(emergency_ids)) == len(emergency_ids),
        {
            "unique_scenario_ids": len(set(scenario_ids)),
            "unique_emergency_ids": len(set(emergency_ids)),
            "emergencies": len(emergency_ids),
        },
    )

    # 3. Deterministic seeds --------------------------------------------
    bad_seeds = [
        scenario["scenario_id"]
        for scenario in scenarios
        if scenario["master_seed"] != config["master_seed"]
        or scenario["scenario_seed"]
        != derive_seed(
            config["master_seed"],
            "scenario",
            int(scenario["scenario_id"].split("-")[1]),
        )
    ]
    report.add(
        "3",
        "Every scenario has a deterministic seed",
        not bad_seeds,
        {
            "rule": "scenario_seed = derive_seed(master_seed, 'scenario', "
            "index) via sha256",
            "master_seed": config["master_seed"],
            "mismatches": bad_seeds[:10],
        },
    )

    # 4 / 5. S and U in (0, 1] ------------------------------------------
    severities = [e["severity"] for _, e in all_emergencies(dataset)]
    urgencies = [e["urgency"] for _, e in all_emergencies(dataset)]
    report.add(
        "4",
        "Every emergency has S in (0, 1]",
        all(0 < value <= 1 for value in severities),
        {"min": min(severities), "max": max(severities)},
    )
    report.add(
        "5",
        "Every emergency has U in (0, 1]",
        all(0 < value <= 1 for value in urgencies),
        {"min": min(urgencies), "max": max(urgencies)},
    )

    # 6. Arrival timestamps present -------------------------------------
    base_time = datetime.strptime(
        config["arrival"]["base_timestamp"],
        "%Y-%m-%dT%H:%M:%SZ",
    )
    window = config["arrival"]["window_seconds"]
    bad_arrivals = [
        e["emergency_id"]
        for _, e in all_emergencies(dataset)
        if not isinstance(e.get("arrival_offset_seconds"), int)
        or not 0 <= e["arrival_offset_seconds"] <= window
        or e.get("arrival_timestamp")
        != (
            base_time + timedelta(seconds=e["arrival_offset_seconds"])
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
    ]
    report.add(
        "6",
        "Arrival timestamps are present",
        not bad_arrivals,
        {"invalid": bad_arrivals[:10]},
    )

    # 7. Arrival independence -------------------------------------------
    # (a) Perturb the arrival stream: everything except arrivals must be
    #     identical, and arrivals must actually change.
    arrival_perturbed = generate_dataset(
        config, arrival_salt="arrival::perturbation-check"
    )
    non_arrival_unchanged = strip_fields(
        arrival_perturbed, ARRIVAL_FIELDS
    ) == strip_fields(dataset, ARRIVAL_FIELDS)
    arrivals_changed = emergency_values(
        arrival_perturbed, ["arrival_offset_seconds"]
    ) != emergency_values(dataset, ["arrival_offset_seconds"])

    # (b) Perturb the severity/urgency stream: arrivals must be identical.
    su_perturbed = generate_dataset(
        config, su_salt="severity_urgency::perturbation-check"
    )
    arrivals_unchanged_by_su = emergency_values(
        su_perturbed, ["arrival_offset_seconds"]
    ) == emergency_values(dataset, ["arrival_offset_seconds"])
    su_changed = emergency_values(
        su_perturbed, ["severity", "urgency"]
    ) != emergency_values(dataset, ["severity", "urgency"])

    # (c) Statistical: FCFS position vs S, U, P_GT.
    positions, s_values, u_values, gt_values = [], [], [], []
    for scenario in scenarios:
        lookup = {e["emergency_id"]: e for e in scenario["emergencies"]}
        order = fcfs_order(arrival_view(scenario["emergencies"]))
        for position, emergency_id in enumerate(order):
            emergency = lookup[emergency_id]
            positions.append(position / (len(order) - 1))
            s_values.append(emergency["severity"])
            u_values.append(emergency["urgency"])
            gt_values.append(emergency["ground_truth_reference_score"])

    correlations = {
        "position_vs_severity": pearson(positions, s_values),
        "position_vs_urgency": pearson(positions, u_values),
        "position_vs_P_GT": pearson(positions, gt_values),
    }

    report.add(
        "7",
        "Arrival timestamps are independent of S/U generation logic",
        non_arrival_unchanged
        and arrivals_changed
        and arrivals_unchanged_by_su
        and su_changed
        and all(abs(r) < CORRELATION_LIMIT for r in correlations.values()),
        {
            "arrival_stream_perturbed__all_other_fields_identical": (
                non_arrival_unchanged
            ),
            "arrival_stream_perturbed__arrivals_changed": arrivals_changed,
            "su_stream_perturbed__arrivals_identical": (
                arrivals_unchanged_by_su
            ),
            "su_stream_perturbed__su_changed": su_changed,
            "pearson_correlations": correlations,
            "correlation_limit_abs": CORRELATION_LIMIT,
        },
    )

    # 8. Valid resource requirements ------------------------------------
    bad_requirements = []
    for _, emergency in all_emergencies(dataset):
        requirement = emergency["resource_requirements"]
        try:
            ResourceRequirement(**requirement)
            valid = (
                set(requirement) == set(RESOURCE_TYPES)
                and all(
                    isinstance(value, int) and value >= 0
                    for value in requirement.values()
                )
                and sum(requirement.values()) > 0
            )
        except Exception:
            valid = False
        if not valid:
            bad_requirements.append(emergency["emergency_id"])
    report.add(
        "8",
        "Every emergency has valid resource requirements",
        not bad_requirements,
        {
            "schema": "resource_services.schemas.resource_requirement."
            "ResourceRequirement",
            "invalid": bad_requirements[:10],
        },
    )

    # 9. Valid inventory ------------------------------------------------
    bad_inventory = []
    for scenario in scenarios:
        try:
            warehouses = [
                Warehouse(**warehouse)
                for warehouse in scenario["resource_inventory"]
            ]
            totals = {
                resource: sum(
                    w.inventory[resource].available for w in warehouses
                )
                for resource in RESOURCE_TYPES
            }
            valid = (
                len(warehouses) == scenario["n_warehouses"] >= 2
                and all(
                    w.inventory[r].capacity >= w.inventory[r].available
                    for w in warehouses
                    for r in RESOURCE_TYPES
                )
                and totals == {
                    r: float(v) for r, v in scenario["total_supply"].items()
                }
            )
        except Exception:
            valid = False
        if not valid:
            bad_inventory.append(scenario["scenario_id"])
    report.add(
        "9",
        "Every scenario has a valid inventory",
        not bad_inventory,
        {
            "schema": "resource_services.schemas.warehouse.Warehouse",
            "invalid": bad_inventory[:10],
        },
    )

    # 10. Scarcity level present and consistent -------------------------
    levels = config["scenario_design"]["scarcity_levels"]
    bad_scarcity = []
    for scenario in scenarios:
        level = scenario.get("scarcity_level")
        if level not in levels:
            bad_scarcity.append(scenario["scenario_id"])
            continue

        low, high = levels[level]["supply_to_demand_ratio"]
        demand = {
            r: sum(
                e["resource_requirements"][r] for e in scenario["emergencies"]
            )
            for r in RESOURCE_TYPES
        }
        if demand != scenario["total_demand"]:
            bad_scarcity.append(scenario["scenario_id"])
            continue

        for resource in RESOURCE_TYPES:
            d = demand[resource]
            s = scenario["total_supply"][resource]
            ratio = scenario["design_supply_to_demand_ratio"][resource]
            if d == 0:
                ok = s == 0
            elif level == "LOW":
                ok = s > d
            elif level == "HIGH":
                ok = s < d
            else:
                # Supply = round(true_ratio * d); the stored ratio is
                # rounded to 6 decimals, so allow that rounding too.
                ok = abs(s - ratio * d) <= 0.5 + 0.5e-6 * d + 1e-9
            ok = ok and low <= ratio <= high
            if not ok:
                bad_scarcity.append(scenario["scenario_id"])
                break
    report.add(
        "10",
        "Scarcity level is present (and matches realized supply/demand)",
        not bad_scarcity,
        {"inconsistent": bad_scarcity[:10]},
    )

    # 11 / 12. P_GT and ground_truth_critical ---------------------------
    bad_gt_score, bad_gt_label, bad_gt_count = [], [], []
    for scenario in scenarios:
        count = 0
        for emergency in scenario["emergencies"]:
            exact = exact_reference_score(
                emergency["severity"], emergency["urgency"]
            )
            if Decimal(repr(emergency["ground_truth_reference_score"])) != exact:
                bad_gt_score.append(emergency["emergency_id"])
            expected = 1 if exact > Decimal("0.8") else 0
            if emergency["ground_truth_critical"] != expected:
                bad_gt_label.append(emergency["emergency_id"])
            count += expected
        if scenario["n_ground_truth_critical"] != count:
            bad_gt_count.append(scenario["scenario_id"])

    boundary = sum(
        exact_reference_score(e["severity"], e["urgency"]) == Decimal("0.8")
        for _, e in all_emergencies(dataset)
    )
    report.add(
        "11",
        "P_GT is correctly calculated",
        not bad_gt_score,
        {
            "rule": "P_GT = 0.5*S + 0.5*U (verified with exact decimals)",
            "mismatches": bad_gt_score[:10],
        },
    )
    report.add(
        "12",
        "ground_truth_critical is correctly calculated",
        not bad_gt_label and not bad_gt_count,
        {
            "rule": "1 if P_GT > 0.8 else 0 (fixed reference rule)",
            "label_mismatches": bad_gt_label[:10],
            "scenario_count_mismatches": bad_gt_count[:10],
            "emergencies_exactly_at_0.8_labelled_not_critical": boundary,
        },
    )

    # 13. FCFS isolation ------------------------------------------------
    # Scramble every non-arrival field. FCFS / REVERSE_FCFS / RANDOM orders
    # must not change.
    scramble_rng = random.Random(derive_seed(config["master_seed"], "scramble"))
    scrambled = copy.deepcopy(dataset)
    for _, emergency in all_emergencies(scrambled):
        emergency["severity"] = round(scramble_rng.uniform(0.01, 1.0), 4)
        emergency["urgency"] = round(scramble_rng.uniform(0.01, 1.0), 4)
        emergency["ground_truth_reference_score"] = scramble_rng.random()
        emergency["ground_truth_critical"] = scramble_rng.randint(0, 1)
        emergency["su_stratum"] = "SCRAMBLED"
        emergency["resource_requirements"] = {
            r: scramble_rng.randint(0, 999) for r in RESOURCE_TYPES
        }

    order_changes = 0
    for original, perturbed in zip(scenarios, scrambled["scenarios"]):
        before = condition_orders(original, config, False)
        after = condition_orders(perturbed, config, False)
        order_changes += before != after

    view_fields = {
        len(item) for item in arrival_view(scenarios[0]["emergencies"])
    }

    fcfs_sorted = all(
        [
            (lookup[i]["arrival_offset_seconds"], i)
            for i in fcfs_order(arrival_view(scenario["emergencies"]))
        ]
        == sorted(
            (e["arrival_offset_seconds"], e["emergency_id"])
            for e in scenario["emergencies"]
        )
        for scenario in scenarios
        for lookup in [{e["emergency_id"]: e for e in scenario["emergencies"]}]
    )

    results_rows = load_results_rows()
    fcfs_rows = {
        row["scenario_id"]: row["allocation_order"].split(";")
        for row in results_rows
        if row["order_condition"] == "FCFS"
    }
    fcfs_used = all(
        fcfs_rows[s["scenario_id"]]
        == fcfs_order(arrival_view(s["emergencies"]))
        for s in scenarios
    )

    report.add(
        "13",
        "FCFS does not use severity/urgency/priority",
        order_changes == 0
        and view_fields == {2}
        and fcfs_sorted
        and fcfs_used,
        {
            "fcfs_input": "arrival_view -> (emergency_id, "
            "arrival_offset_seconds) only",
            "scenarios_whose_FCFS_REVERSE_RANDOM_orders_changed_after_"
            "scrambling_S_U_PGT_labels_demand": order_changes,
            "fcfs_sorted_by_arrival_then_id": fcfs_sorted,
            "results_csv_fcfs_orders_match": fcfs_used,
        },
    )

    # 14. AASHRAY formulation -------------------------------------------
    # (a) Formula wiring, checked against an independent log-space form.
    #     These parameter sets are arbitrary code-check values, NOT a
    #     pilot configuration, and are never used for allocation.
    formula_cases = [
        {"alpha": 0.0, "k": 0.0, "m": 0.0, "n": 1.0},
        {"alpha": 1.0, "k": 0.0, "m": 0.0, "n": 1.0},
        {"alpha": 0.3, "k": 0.2, "m": 0.5, "n": 0.3},
        {"alpha": 0.7, "k": 1.0, "m": 0.0, "n": 0.0},
    ]
    formula_errors = 0
    for parameters in formula_cases:
        for _, emergency in all_emergencies(dataset):
            s, u = emergency["severity"], emergency["urgency"]
            a = parameters["alpha"]
            p_n = math.exp(a * math.log(s) + (1 - a) * math.log(u))
            expected = (
                parameters["k"] * s
                + parameters["m"] * u
                + parameters["n"] * p_n
            )
            if not math.isclose(
                overall_priority(s, u, parameters), expected, abs_tol=1e-12
            ):
                formula_errors += 1

    report.add(
        "14a",
        "AASHRAY formula implementation matches P_n = S^a U^(1-a), "
        "P_o = kS + mU + nP_n",
        formula_errors == 0,
        {
            "note": "Code check with arbitrary parameter sets; these are not "
            "a pilot configuration and are not used for allocation.",
            "mismatches": formula_errors,
        },
    )

    parameters = config["aashray_parameters"]
    aashray_available, aashray_reason = aashray_parameters_status(parameters)

    if aashray_available:
        aashray_rows = {
            row["scenario_id"]: row["allocation_order"].split(";")
            for row in results_rows
            if row["order_condition"] == "AASHRAY"
        }
        bad_orders = []
        for scenario in scenarios:
            used = aashray_rows.get(scenario["scenario_id"])
            lookup = {e["emergency_id"]: e for e in scenario["emergencies"]}
            scores = [
                overall_priority(
                    lookup[i]["severity"], lookup[i]["urgency"], parameters
                )
                for i in used or []
            ]
            if (
                used != aashray_order(scenario["emergencies"], parameters)
                or scores != sorted(scores, reverse=True)
            ):
                bad_orders.append(scenario["scenario_id"])
        report.add(
            "14b",
            "AASHRAY condition ranks by descending P_o with the configured "
            "parameters",
            not bad_orders,
            {"parameters": parameters, "mismatches": bad_orders[:10]},
        )
    else:
        report.add(
            "14b",
            "AASHRAY condition ranks by descending P_o with the configured "
            "parameters",
            False,
            {"parameters": parameters},
            skipped_reason=aashray_reason,
        )

    # 15. CDC uses fixed ground truth -----------------------------------
    rows_by_scenario = defaultdict(list)
    for row in results_rows:
        rows_by_scenario[row["scenario_id"]].append(row)

    critical_required_varies = []
    critical_required_wrong = []
    cdc_wrong = []
    for scenario in scenarios:
        rows = rows_by_scenario[scenario["scenario_id"]]
        expected_required = float(
            sum(
                sum(e["resource_requirements"].values())
                for e in scenario["emergencies"]
                if exact_reference_score(e["severity"], e["urgency"])
                > Decimal("0.8")
            )
        )
        values = {float(row["critical_required"]) for row in rows}
        if len(values) != 1:
            critical_required_varies.append(scenario["scenario_id"])
        if values != {expected_required}:
            critical_required_wrong.append(scenario["scenario_id"])
        for row in rows:
            required = float(row["critical_required"])
            fulfilled = float(row["critical_fulfilled"])
            if required == 0:
                ok = row["cdc"] == ""
            else:
                ok = math.isclose(
                    float(row["cdc"]), fulfilled / required, abs_tol=1e-12
                )
            if not ok:
                cdc_wrong.append(scenario["scenario_id"])
    report.add(
        "15",
        "CDC uses fixed ground-truth criticality",
        not critical_required_varies
        and not critical_required_wrong
        and not cdc_wrong,
        {
            "critical_required_identical_across_all_orders": (
                not critical_required_varies
            ),
            "critical_required_matches_exact_P_GT_labels": (
                not critical_required_wrong
            ),
            "cdc_value_mismatches": cdc_wrong[:10],
        },
    )

    # 16. No priority category thresholds affect allocation -------------
    # Re-run FCFS for every scenario with each categorical placeholder and
    # extreme S/U placeholders: allocated quantities must not change.
    placeholder_variants = [
        {"severity": s, "urgency": u, "priority": p}
        for p in ("LOW", "MODERATE", "HIGH", "CRITICAL")
        for s, u in ((0.01, 0.01), (1.0, 1.0))
    ]
    quantity_changes = 0

    with TemporaryDirectory(prefix="aashray_pilot_check_") as work_dir:
        for scenario in scenarios:
            order = fcfs_order(arrival_view(scenario["emergencies"]))
            baseline = None
            for placeholders in placeholder_variants:
                adapter = ExistingAllocatorAdapter(
                    scenario, placeholders, Path(work_dir)
                )
                allocated = [
                    record["allocated"]
                    for record in adapter.allocate_in_order(order)
                ]
                if baseline is None:
                    baseline = allocated
                elif allocated != baseline:
                    quantity_changes += 1

    script_dir = PILOT_ROOT / "scripts"
    category_reads = []
    for path in sorted(script_dir.glob("*.py")):
        if path.name == "validate_pilot.py":
            continue
        text = path.read_text(encoding="utf-8")
        if re.search(
            r"\.(final_priority_level|overall_priority_score|"
            r"normalized_priority)\b",
            text,
        ):
            category_reads.append(path.name)

    report.add(
        "16",
        "No priority category thresholds affect allocation",
        quantity_changes == 0 and not category_reads,
        {
            "placeholder_variants_tested": len(placeholder_variants),
            "scenario_runs_with_changed_quantities": quantity_changes,
            "experiment_scripts_reading_allocator_priority_outputs": (
                category_reads
            ),
        },
    )

    # 17. No final 12,000 test data -------------------------------------
    data_files = sorted(
        path.relative_to(PILOT_ROOT).as_posix()
        for path in (PILOT_ROOT / "data").rglob("*")
        if path.is_file()
    )
    result_scenarios = {row["scenario_id"] for row in results_rows}

    oversize_refused = False
    oversize_config = copy.deepcopy(config)
    oversize_config["n_scenarios"] = 12000
    try:
        generate_dataset(oversize_config)
    except ValueError:
        oversize_refused = True

    report.add(
        "17",
        "No final 12,000 test data is generated or accessed",
        data_files == ["data/pilot_500_scenarios.json"]
        and len(result_scenarios) == PILOT_SCENARIO_COUNT
        and oversize_refused,
        {
            "data_files": data_files,
            "distinct_scenarios_in_results": len(result_scenarios),
            "generator_refuses_n_scenarios_12000": oversize_refused,
        },
    )

    # 18. Determinism ---------------------------------------------------
    regenerated_a = json_text(generate_dataset(config))
    regenerated_b = json_text(generate_dataset(config))
    on_disk = DATASET_PATH.read_text(encoding="utf-8")

    rerun = render_outputs(run_pilot(dataset, config, dataset_sha256))
    rerun_matches = {
        path.name: path.read_text(encoding="utf-8") == text
        for path, text in rerun.items()
    }

    report.add(
        "18",
        "Running the experiment twice with the same seed produces "
        "identical results",
        regenerated_a == regenerated_b == on_disk
        and all(rerun_matches.values()),
        {
            "dataset_regenerated_twice_identical": regenerated_a
            == regenerated_b,
            "dataset_regenerated_matches_file": regenerated_a == on_disk,
            "rerun_outputs_match_files": rerun_matches,
        },
    )

    # Consistency checks -------------------------------------------------
    summary = json.loads((PILOT_ROOT / "results" / "pilot_summary.json")
                         .read_text(encoding="utf-8"))
    expected_calls = len(scenarios) * len(summary["order_conditions_evaluated"])
    report.add(
        "C1",
        "Existing allocator processed every call in the presented order",
        summary["allocator_calls_with_verified_order"] == expected_calls,
        {
            "verified_calls": summary["allocator_calls_with_verified_order"],
            "expected_calls": expected_calls,
        },
    )

    same_environment = all(
        len({(r["total_required"], r["total_available"]) for r in rows}) == 1
        for rows in rows_by_scenario.values()
    )
    report.add(
        "C2",
        "Same inventory and demand used for every order condition",
        same_environment,
        {},
    )

    quantity_errors = 0
    for row in results_rows:
        if float(row["total_unmet"]) != float(
            row["total_unmet_reported_by_allocator"]
        ):
            quantity_errors += 1
        for resource in RESOURCE_TYPES:
            fulfilled = float(row[f"{resource}_fulfilled"])
            if fulfilled > float(row[f"{resource}_available"]) or (
                fulfilled > float(row[f"{resource}_required"])
            ):
                quantity_errors += 1
    report.add(
        "C3",
        "Fulfilment never exceeds supply or demand; unmet matches the "
        "allocator's reported shortage",
        quantity_errors == 0,
        {"violations": quantity_errors},
    )

    # Output -------------------------------------------------------------
    failed = report.failed()
    output = {
        "dataset_sha256": dataset_sha256,
        "n_checks": len(report.checks),
        "n_pass": sum(c["status"] == "PASS" for c in report.checks),
        "n_fail": len(failed),
        "n_skipped": sum(c["status"] == "SKIPPED" for c in report.checks),
        "checks": report.checks,
    }
    dump_json(output, VALIDATION_PATH)

    for check in report.checks:
        print(f"[{check['status']:7}] {check['id']:>3}  {check['name']}")
    print(
        f"\n{output['n_pass']} PASS, {output['n_fail']} FAIL, "
        f"{output['n_skipped']} SKIPPED -> {VALIDATION_PATH}"
    )

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
