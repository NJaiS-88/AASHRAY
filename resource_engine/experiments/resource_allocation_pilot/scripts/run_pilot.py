"""Run every allocation-order condition on the pilot dataset.

Usage (from the repository root):

    python experiments/resource_allocation_pilot/scripts/run_pilot.py

For each scenario the SAME inventory and the SAME emergency demands are
passed to the existing allocator once per order condition. Only the order in
which emergencies are presented changes.

Outputs (results/):
    pilot_results.csv       one row per scenario x order condition
    order_sensitivity.csv   one row per scenario (TDC / CDC across orders)
    pilot_summary.json      distributions, aggregated metrics, sensitivity
"""

import csv
import hashlib
import io
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from tempfile import TemporaryDirectory

from allocator_adapter import ExistingAllocatorAdapter
from metrics import (
    RESOURCE_TYPES,
    mean,
    scenario_metrics,
    spread,
    summarize_condition,
    summarize_sensitivity,
)
from orderings import (
    aashray_order,
    aashray_parameters_status,
    arrival_view,
    fcfs_order,
    random_order,
    reverse_fcfs_order,
)
from pilot_common import (
    DATASET_PATH,
    ORDER_SENSITIVITY_PATH,
    PILOT_RESULTS_PATH,
    SUMMARY_PATH,
    derive_seed,
    json_text,
    load_config,
)


CONDITION_COLUMN = {
    "FCFS": "FCFS",
    "AASHRAY": "AASHRAY",
    "REVERSE_FCFS": "reverse_FCFS",
    "RANDOM_1": "random_1",
    "RANDOM_2": "random_2",
    "RANDOM_3": "random_3",
}

SCENARIO_FIELDS = [
    "scenario_id",
    "scenario_seed",
    "scarcity_level",
    "size_class",
    "su_profile",
    "n_emergencies",
    "n_warehouses",
    "n_ground_truth_critical",
]

RESULT_FIELDS = SCENARIO_FIELDS + [
    "order_condition",
    "order_seed",
    "total_required",
    "total_fulfilled",
    "total_unmet",
    "tdc",
    "critical_required",
    "critical_fulfilled",
    "critical_unmet",
    "cdc",
    "total_available",
    "resource_utilization",
    "n_emergencies_fully_fulfilled",
    "n_critical_fully_fulfilled",
    "per_type_fulfilled_equals_min_supply_demand",
    "total_unmet_reported_by_allocator",
] + [
    f"{resource}_{kind}"
    for resource in RESOURCE_TYPES
    for kind in ("required", "fulfilled", "available")
] + [
    "allocation_order",
]


def sensitivity_fields() -> list[str]:
    fields = [
        "scenario_id",
        "scarcity_level",
        "size_class",
        "su_profile",
        "n_emergencies",
        "n_ground_truth_critical",
        "n_valid_orders",
        "valid_order_conditions",
    ]

    for metric in ("TDC", "CDC"):
        fields += [f"{metric}_{column}" for column in CONDITION_COLUMN.values()]
        fields += [
            f"{metric}_range",
            f"{metric}_std",
            f"{metric}_changes_with_order",
        ]

    return fields


def condition_orders(
    scenario: dict,
    config: dict,
    aashray_available: bool,
) -> dict[str, tuple[list[str], int | None]]:

    emergencies = scenario["emergencies"]
    arrivals = arrival_view(emergencies)
    emergency_ids = [emergency["emergency_id"] for emergency in emergencies]

    orders = {}

    for condition in config["order_conditions"]:

        if condition == "FCFS":
            orders[condition] = (fcfs_order(arrivals), None)

        elif condition == "REVERSE_FCFS":
            orders[condition] = (reverse_fcfs_order(arrivals), None)

        elif condition.startswith("RANDOM_"):
            seed = derive_seed(
                config["master_seed"],
                scenario["scenario_seed"],
                "random_order",
                condition.split("_")[1],
            )
            orders[condition] = (random_order(emergency_ids, seed), seed)

        elif condition == "AASHRAY":
            if aashray_available:
                orders[condition] = (
                    aashray_order(emergencies, config["aashray_parameters"]),
                    None,
                )

        else:
            raise ValueError(f"Unknown order condition: {condition}")

    return orders


def sensitivity_row(
    scenario: dict,
    per_condition: dict[str, dict],
    tolerance: float,
) -> dict:

    row = {
        "scenario_id": scenario["scenario_id"],
        "scarcity_level": scenario["scarcity_level"],
        "size_class": scenario["size_class"],
        "su_profile": scenario["su_profile"],
        "n_emergencies": scenario["n_emergencies"],
        "n_ground_truth_critical": scenario["n_ground_truth_critical"],
        "n_valid_orders": len(per_condition),
        "valid_order_conditions": ";".join(per_condition),
    }

    for metric, key in (("TDC", "tdc"), ("CDC", "cdc")):

        values = []

        for condition, column in CONDITION_COLUMN.items():
            value = (
                per_condition[condition][key]
                if condition in per_condition
                else None
            )
            row[f"{metric}_{column}"] = value

            if value is not None:
                values.append(value)

        result = spread(values, tolerance)
        row[f"{metric}_range"] = result["range"]
        row[f"{metric}_std"] = result["std"]
        row[f"{metric}_changes_with_order"] = result["changes"]

    return row


def stats(values: list[float]) -> dict:
    return {
        "min": min(values),
        "mean": statistics.fmean(values),
        "max": max(values),
    }


def arrival_rank_correlations(dataset: dict) -> dict:
    # Pearson correlation between within-scenario FCFS position (0..1) and
    # S, U, P_GT over all emergencies. Near zero means arrival order carries
    # no severity/urgency information.
    positions, severity, urgency, reference = [], [], [], []

    for scenario in dataset["scenarios"]:
        emergencies = {
            emergency["emergency_id"]: emergency
            for emergency in scenario["emergencies"]
        }
        order = fcfs_order(arrival_view(scenario["emergencies"]))
        last = len(order) - 1

        for position, emergency_id in enumerate(order):
            emergency = emergencies[emergency_id]
            positions.append(position / last)
            severity.append(emergency["severity"])
            urgency.append(emergency["urgency"])
            reference.append(emergency["ground_truth_reference_score"])

    return {
        "arrival_position_vs_severity": statistics.correlation(
            positions, severity
        ),
        "arrival_position_vs_urgency": statistics.correlation(
            positions, urgency
        ),
        "arrival_position_vs_P_GT": statistics.correlation(
            positions, reference
        ),
    }


def dataset_distribution(dataset: dict) -> dict:
    scenarios = dataset["scenarios"]
    emergencies = [
        emergency
        for scenario in scenarios
        for emergency in scenario["emergencies"]
    ]

    def band(value: float) -> str:
        if value <= 0.35:
            return "LOW"
        if value <= 0.65:
            return "MODERATE"
        return "HIGH"

    realized_grid = Counter(
        f"S_{band(e['severity'])}/U_{band(e['urgency'])}" for e in emergencies
    )

    sizes_by_class = defaultdict(list)
    for scenario in scenarios:
        sizes_by_class[scenario["size_class"]].append(
            scenario["n_emergencies"]
        )

    ratio_by_scarcity = defaultdict(list)
    for scenario in scenarios:
        ratio_by_scarcity[scenario["scarcity_level"]].append(
            scenario["overall_supply_to_demand_ratio"]
        )

    critical_by_scarcity = Counter()
    zero_critical_by_scarcity = Counter()
    for scenario in scenarios:
        critical_by_scarcity[scenario["scarcity_level"]] += scenario[
            "n_ground_truth_critical"
        ]
        if scenario["n_ground_truth_critical"] == 0:
            zero_critical_by_scarcity[scenario["scarcity_level"]] += 1

    tied_scenarios = 0
    tied_emergencies = 0
    for scenario in scenarios:
        offsets = Counter(
            e["arrival_offset_seconds"] for e in scenario["emergencies"]
        )
        tied = sum(count for count in offsets.values() if count > 1)
        tied_emergencies += tied
        tied_scenarios += tied > 0

    n_critical = sum(e["ground_truth_critical"] for e in emergencies)

    return {
        "n_scenarios": len(scenarios),
        "n_emergencies": len(emergencies),
        "scenarios_by_scarcity": dict(
            Counter(s["scarcity_level"] for s in scenarios)
        ),
        "scenarios_by_size_class": dict(
            Counter(s["size_class"] for s in scenarios)
        ),
        "scenarios_by_su_profile": dict(
            Counter(s["su_profile"] for s in scenarios)
        ),
        "scenarios_by_scarcity_and_size": dict(
            Counter(
                f"{s['scarcity_level']}/{s['size_class']}" for s in scenarios
            )
        ),
        "scenarios_by_scarcity_and_su_profile": dict(
            Counter(
                f"{s['scarcity_level']}/{s['su_profile']}" for s in scenarios
            )
        ),
        "emergencies_per_scenario_by_size_class": {
            size: stats(values) for size, values in sizes_by_class.items()
        },
        "emergencies_per_scenario_histogram": dict(
            sorted(Counter(s["n_emergencies"] for s in scenarios).items())
        ),
        "warehouses_per_scenario": dict(
            sorted(Counter(s["n_warehouses"] for s in scenarios).items())
        ),
        "emergencies_by_su_stratum": dict(
            Counter(e["su_stratum"] for e in emergencies)
        ),
        "emergencies_by_realized_su_band_grid": dict(sorted(
            realized_grid.items()
        )),
        "emergencies_by_demand_pattern": dict(
            Counter(e["demand_pattern"] for e in emergencies)
        ),
        "severity": stats([e["severity"] for e in emergencies]),
        "urgency": stats([e["urgency"] for e in emergencies]),
        "pearson_severity_vs_urgency": statistics.correlation(
            [e["severity"] for e in emergencies],
            [e["urgency"] for e in emergencies],
        ),
        "arrival_independence": arrival_rank_correlations(dataset),
        "arrival_timestamp_ties": {
            "scenarios_with_tied_timestamps": tied_scenarios,
            "emergencies_sharing_a_timestamp": tied_emergencies,
            "tie_breaker": "ascending (arrival_offset_seconds, emergency_id)",
        },
        "ground_truth_critical": {
            "rule": "P_GT = 0.5*S + 0.5*U; critical if P_GT > 0.8",
            "n_critical_emergencies": n_critical,
            "pct_critical_emergencies": 100.0 * n_critical / len(emergencies),
            "critical_emergencies_by_scarcity": dict(critical_by_scarcity),
            "critical_emergencies_by_su_stratum": dict(
                Counter(
                    e["su_stratum"]
                    for e in emergencies
                    if e["ground_truth_critical"]
                )
            ),
            "scenarios_with_zero_critical_emergencies": sum(
                zero_critical_by_scarcity.values()
            ),
            "scenarios_with_zero_critical_by_scarcity": dict(
                zero_critical_by_scarcity
            ),
        },
        "overall_supply_to_demand_ratio_by_scarcity": {
            level: stats(values) for level, values in ratio_by_scarcity.items()
        },
    }


def group_rows(rows: list[dict], key: str) -> dict[str, list[dict]]:
    groups = defaultdict(list)
    for row in rows:
        groups[row[key]].append(row)
    return dict(sorted(groups.items()))


def metrics_by_condition(result_rows: list[dict], conditions: list[str]):

    def by_condition(rows):
        grouped = group_rows(rows, "order_condition")
        return {
            condition: summarize_condition(grouped[condition])
            for condition in conditions
            if condition in grouped
        }

    return {
        "overall": by_condition(result_rows),
        "by_scarcity": {
            level: by_condition(rows)
            for level, rows in group_rows(
                result_rows, "scarcity_level"
            ).items()
        },
        "by_size_class": {
            size: by_condition(rows)
            for size, rows in group_rows(result_rows, "size_class").items()
        },
    }


def order_sensitivity_summary(sensitivity_rows: list[dict]) -> dict:
    summary = {}

    for metric in ("TDC", "CDC"):
        summary[metric] = {
            "overall": summarize_sensitivity(sensitivity_rows, metric),
            "by_scarcity": {
                level: summarize_sensitivity(rows, metric)
                for level, rows in group_rows(
                    sensitivity_rows, "scarcity_level"
                ).items()
            },
            "by_size_class": {
                size: summarize_sensitivity(rows, metric)
                for size, rows in group_rows(
                    sensitivity_rows, "size_class"
                ).items()
            },
        }

    return summary


def fcfs_vs_aashray(sensitivity_rows: list[dict], tolerance: float):
    # Descriptive paired comparison only. Not a hypothesis test.

    def compare(rows, metric):
        pairs = [
            (row[f"{metric}_FCFS"], row[f"{metric}_AASHRAY"])
            for row in rows
            if row[f"{metric}_FCFS"] is not None
            and row[f"{metric}_AASHRAY"] is not None
        ]
        differences = [aashray - fcfs for fcfs, aashray in pairs]

        return {
            "n_scenarios_compared": len(pairs),
            "mean_difference_aashray_minus_fcfs": mean(differences),
            "n_aashray_higher": sum(d > tolerance for d in differences),
            "n_aashray_lower": sum(d < -tolerance for d in differences),
            "n_equal": sum(abs(d) <= tolerance for d in differences),
        }

    def block(rows):
        return {"TDC": compare(rows, "TDC"), "CDC": compare(rows, "CDC")}

    return {
        "note": "Descriptive pilot comparison. Not a hypothesis test.",
        "overall": block(sensitivity_rows),
        "by_scarcity": {
            level: block(rows)
            for level, rows in group_rows(
                sensitivity_rows, "scarcity_level"
            ).items()
        },
    }


def run_pilot(dataset: dict, config: dict, dataset_sha256: str) -> dict:

    parameters = config["aashray_parameters"]
    aashray_available, aashray_reason = aashray_parameters_status(parameters)

    placeholders = config["existing_allocator"]["placeholder_inputs"]
    tolerance = config["tdc_invariance_tolerance"]

    result_rows = []
    sensitivity_rows = []
    calls_order_verified = 0

    with TemporaryDirectory(prefix="aashray_pilot_") as work_dir:

        for scenario in dataset["scenarios"]:

            adapter = ExistingAllocatorAdapter(
                scenario=scenario,
                placeholder_inputs=placeholders,
                work_dir=Path(work_dir),
            )

            per_condition = {}

            orders = condition_orders(scenario, config, aashray_available)

            for condition, (order, order_seed) in orders.items():

                records = adapter.allocate_in_order(order)
                metrics = scenario_metrics(scenario, records)
                per_condition[condition] = metrics

                row = {field: scenario[field] for field in SCENARIO_FIELDS}
                row.update(
                    {
                        "order_condition": condition,
                        "order_seed": order_seed,
                        **metrics,
                        "allocation_order": ";".join(order),
                    }
                )
                result_rows.append(row)

            calls_order_verified += adapter.calls_order_verified

            sensitivity_rows.append(
                sensitivity_row(scenario, per_condition, tolerance)
            )

    evaluated = [
        condition
        for condition in config["order_conditions"]
        if condition != "AASHRAY" or aashray_available
    ]

    summary = {
        "experiment": config["experiment"],
        "dataset_role": dataset["dataset_role"],
        "master_seed": config["master_seed"],
        "dataset_file": "data/pilot_500_scenarios.json",
        "dataset_sha256": dataset_sha256,
        "generation_config_sha256": dataset["generation_config_sha256"],
        "allocator": config["existing_allocator"],
        "allocator_calls_with_verified_order": calls_order_verified,
        "aashray_condition": {
            "status": "RUN" if aashray_available else "NOT_RUN",
            "reason": aashray_reason,
            "parameters": parameters,
        },
        "order_conditions_evaluated": evaluated,
        "order_conditions_not_evaluated": {
            condition: aashray_reason
            for condition in config["order_conditions"]
            if condition not in evaluated
        },
        "tdc_invariance_tolerance": tolerance,
        "dataset_distribution": dataset_distribution(dataset),
        "metrics_by_condition": metrics_by_condition(result_rows, evaluated),
        "order_sensitivity": order_sensitivity_summary(sensitivity_rows),
        "fcfs_vs_aashray": (
            fcfs_vs_aashray(sensitivity_rows, tolerance)
            if aashray_available
            else None
        ),
        "notes": [
            "TDC and CDC sum water, food and medical_kits in their native "
            "units, as specified. Water dominates the totals.",
            "CDC is undefined for scenarios with no GT-critical demand; "
            "those scenarios are excluded from CDC means and counted "
            "separately.",
            "resource_utilization is not reported by the existing allocator; "
            "it is derived from its output as total fulfilled / total "
            "available.",
            "per_type_fulfilled_equals_min_supply_demand counts scenario x "
            "order runs where every resource type ended at "
            "min(total supply, total demand).",
        ],
    }

    return {
        "results": result_rows,
        "sensitivity": sensitivity_rows,
        "summary": summary,
    }


def format_value(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return repr(value) if isinstance(value, float) else str(value)


def csv_text(rows: list[dict], fields: list[str]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(fields)

    for row in rows:
        writer.writerow([format_value(row[field]) for field in fields])

    return buffer.getvalue()


def render_outputs(run: dict) -> dict[Path, str]:
    return {
        PILOT_RESULTS_PATH: csv_text(run["results"], RESULT_FIELDS),
        ORDER_SENSITIVITY_PATH: csv_text(
            run["sensitivity"], sensitivity_fields()
        ),
        SUMMARY_PATH: json_text(run["summary"]),
    }


def load_dataset() -> tuple[dict, str]:
    text = DATASET_PATH.read_text(encoding="utf-8")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()

    return json.loads(text), digest


def main() -> None:
    config = load_config()
    dataset, dataset_sha256 = load_dataset()

    run = run_pilot(dataset, config, dataset_sha256)

    for path, text in render_outputs(run).items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        print(f"Wrote {path}")

    summary = run["summary"]
    aashray = summary["aashray_condition"]

    print(f"\nAASHRAY condition : {aashray['status']}")
    if aashray["status"] != "RUN":
        print(f"  reason          : {aashray['reason']}")

    print(f"Order conditions  : {summary['order_conditions_evaluated']}")
    print(
        "Allocator calls with verified order: "
        f"{summary['allocator_calls_with_verified_order']}"
    )

    tdc = summary["order_sensitivity"]["TDC"]["overall"]
    print(
        f"TDC changed with order in {tdc['n_scenarios_changed_with_order']}"
        f"/{tdc['n_scenarios_evaluated']} scenarios; "
        f"max range {tdc['range_max']}"
    )


if __name__ == "__main__":
    main()
