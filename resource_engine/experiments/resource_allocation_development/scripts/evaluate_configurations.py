"""Evaluate FCFS, LINEAR and every AASHRAY ranking-equivalence class on the
3,000 development scenarios, then select the winner with the predefined rule.

Usage (from the repository root, after generating the dataset and grid):

    python experiments/resource_allocation_development/scripts/evaluate_configurations.py

This writes every result file EXCEPT frozen_parameters.json, which
validate_development.py writes only after all validation checks pass.
"""

import csv
import gzip
import io
import json
import statistics
import sys
import time
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory

from allocator_adapter import ExistingAllocatorAdapter
from dev_common import (
    BASELINE_PATH,
    CONFIGURATION_RESULTS_PATH,
    DATASET_PATH,
    EQUIVALENCE_PATH,
    GRID_PATH,
    MANIFEST_PATH,
    PER_SCENARIO_PATH,
    SCARCITY_PATH,
    SUMMARY_PATH,
    TOP_10_PATH,
    application_manifest,
    json_text,
    load_config,
    sha256_file,
    sha256_text,
    write_text,
)
from generate_parameter_grid import build_grid, read_grid
from metrics import (
    distribution,
    paired,
    rank_by_selection_rule,
    scenario_outcome,
    select_winner,
)
from policies import SCORE_TIE_TOLERANCE, arrival_view, fcfs_order, linear_order
from ranking_equivalence import compute_rankings


SCARCITY_LEVELS = ("LOW", "MODERATE", "HIGH")

PER_SCENARIO_FIELDS = [
    "scenario_id",
    "scarcity_level",
    "policy",
    "critical_required",
    "critical_fulfilled",
    "critical_unmet",
    "cdc",
    "total_required",
    "total_fulfilled",
    "total_unmet",
    "tdc",
]

DISTRIBUTION_KEYS = ["mean", "median", "std", "p10", "p25", "p75", "p90", "min", "max"]


def log(message: str) -> None:
    print(message, flush=True)


def load_dataset() -> tuple[dict, str]:
    text = DATASET_PATH.read_text(encoding="utf-8")
    return json.loads(text), sha256_text(text)


def evaluate_orders(dataset: dict, rankings: dict, placeholders: dict):
    """Run the existing allocator once per distinct order in each scenario,
    plus FCFS and LINEAR. The allocator is deterministic for a given order,
    so a repeated order reuses the earlier result."""

    per_scenario = []
    allocator_calls = 0

    with TemporaryDirectory(prefix="aashray_dev_") as work_dir:

        for index, scenario in enumerate(dataset["scenarios"]):

            adapter = ExistingAllocatorAdapter(scenario, placeholders, Path(work_dir))
            cache = {}

            def outcome(order):
                if order not in cache:
                    cache[order] = scenario_outcome(
                        scenario,
                        adapter.allocate_in_order(order),
                    )
                return cache[order]

            emergencies = scenario["emergencies"]

            per_scenario.append(
                {
                    "FCFS": outcome(tuple(fcfs_order(arrival_view(emergencies)))),
                    "LINEAR": outcome(tuple(linear_order(emergencies))),
                    "orders": [
                        outcome(order)
                        for order in rankings["scenario_orders"][index]
                    ],
                    "distinct_orders_evaluated": len(cache),
                }
            )

            allocator_calls += adapter.calls_order_verified

            if (index + 1) % 250 == 0:
                log(f"  allocated {index + 1}/{len(dataset['scenarios'])} scenarios "
                    f"({allocator_calls} allocator calls so far)")

    return per_scenario, allocator_calls


def by_scarcity(values: list[float], levels: list[str]) -> dict:
    return {
        level: [v for v, l in zip(values, levels) if l == level]
        for level in SCARCITY_LEVELS
    }


def class_metrics(cdc, tdc, fcfs_cdc, linear_cdc, levels, tolerance) -> dict:
    stats = distribution(cdc)
    row = {f"{key}_cdc": stats[key] for key in DISTRIBUTION_KEYS}
    row["mean_tdc"] = statistics.fmean(tdc)
    row["median_tdc"] = statistics.median(tdc)

    for level, values in by_scarcity(cdc, levels).items():
        row[f"mean_cdc_{level}"] = statistics.fmean(values)
        row[f"median_cdc_{level}"] = statistics.median(values)

    for name, baseline in (("fcfs", fcfs_cdc), ("linear", linear_cdc)):
        difference = paired(cdc, baseline, tolerance)
        row[f"mean_diff_vs_{name}"] = difference["mean"]
        row[f"n_higher_vs_{name}"] = difference["n_higher"]
        row[f"n_lower_vs_{name}"] = difference["n_lower"]

    return row


def csv_text(rows: list[dict], fields: list[str]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({field: row[field] for field in fields})
    return buffer.getvalue()


def write_per_scenario(per_scenario, dataset, classes) -> None:
    # gzip with mtime=0 so the file is byte-reproducible.
    PER_SCENARIO_PATH.parent.mkdir(parents=True, exist_ok=True)

    with open(PER_SCENARIO_PATH, "wb") as raw:
        with gzip.GzipFile(filename="per_scenario_results.csv", fileobj=raw,
                           mode="wb", mtime=0) as compressed:
            with io.TextIOWrapper(compressed, encoding="utf-8", newline="\n") as text:
                writer = csv.writer(text, lineterminator="\n")
                writer.writerow(PER_SCENARIO_FIELDS)

                for index, scenario in enumerate(dataset["scenarios"]):
                    entry = per_scenario[index]
                    policies = [("FCFS", entry["FCFS"]), ("LINEAR", entry["LINEAR"])]
                    policies += [
                        (cls["class_id"], entry["orders"][cls["order_ids"][index]])
                        for cls in classes
                    ]

                    for policy, outcome in policies:
                        writer.writerow(
                            [scenario["scenario_id"], scenario["scarcity_level"], policy]
                            + [repr(outcome[field]) for field in PER_SCENARIO_FIELDS[3:]]
                        )


def dataset_distribution(dataset: dict) -> dict:
    scenarios = dataset["scenarios"]
    emergencies = [e for s in scenarios for e in s["emergencies"]]
    sizes = [s["n_emergencies"] for s in scenarios]

    positions, severity, urgency, critical = [], [], [], []

    for scenario in scenarios:
        lookup = {e["emergency_id"]: e for e in scenario["emergencies"]}
        order = fcfs_order(arrival_view(scenario["emergencies"]))
        for position, emergency_id in enumerate(order):
            emergency = lookup[emergency_id]
            positions.append(position / (len(order) - 1))
            severity.append(emergency["severity"])
            urgency.append(emergency["urgency"])
            critical.append(emergency["ground_truth_critical"])

    per_size = {}
    for size in ("SMALL", "MEDIUM", "LARGE"):
        values = [s["n_emergencies"] for s in scenarios if s["size_class"] == size]
        per_size[size] = {
            "scenarios": len(values),
            "min": min(values),
            "mean": statistics.fmean(values),
            "max": max(values),
        }

    critical_counts = [s["n_ground_truth_critical"] for s in scenarios]
    attempts = [s["su_generation_attempts"] for s in scenarios]

    ratio = {}
    for level in SCARCITY_LEVELS:
        values = [s["overall_supply_to_demand_ratio"] for s in scenarios
                  if s["scarcity_level"] == level]
        ratio[level] = {"min": min(values), "mean": statistics.fmean(values),
                        "max": max(values)}

    return {
        "n_scenarios": len(scenarios),
        "scenarios_by_scarcity": dict(Counter(s["scarcity_level"] for s in scenarios)),
        "scenarios_by_size_class": dict(Counter(s["size_class"] for s in scenarios)),
        "scenarios_by_su_profile": dict(Counter(s["su_profile"] for s in scenarios)),
        "emergencies": {
            "total": len(emergencies),
            "mean_per_scenario": len(emergencies) / len(scenarios),
            "min_per_scenario": min(sizes),
            "max_per_scenario": max(sizes),
            "by_size_class": per_size,
        },
        "emergencies_by_su_stratum": dict(Counter(e["su_stratum"] for e in emergencies)),
        "emergencies_by_demand_pattern": dict(Counter(e["demand_pattern"] for e in emergencies)),
        "pearson_severity_vs_urgency": statistics.correlation(severity, urgency),
        "arrival_independence": {
            "pearson_fcfs_position_vs_severity": statistics.correlation(positions, severity),
            "pearson_fcfs_position_vs_urgency": statistics.correlation(positions, urgency),
            "pearson_fcfs_position_vs_gt_critical": statistics.correlation(positions, critical),
        },
        "ground_truth": {
            "rule": dataset["ground_truth_rule"],
            "n_critical_emergencies": sum(critical_counts),
            "pct_critical_emergencies": 100 * sum(critical_counts) / len(emergencies),
            "scenarios_with_at_least_one_critical": sum(c >= 1 for c in critical_counts),
            "critical_per_scenario": {
                "min": min(critical_counts),
                "mean": statistics.fmean(critical_counts),
                "median": statistics.median(critical_counts),
                "max": max(critical_counts),
                "histogram": dict(sorted(Counter(critical_counts).items())),
            },
            "critical_by_clause": {
                "both_high": sum(e["gt_rule_inputs"]["both_high"] for e in emergencies),
                "severity_extreme": sum(e["gt_rule_inputs"]["severity_extreme"] for e in emergencies),
                "urgency_extreme": sum(e["gt_rule_inputs"]["urgency_extreme"] for e in emergencies),
            },
            "critical_by_su_stratum": dict(Counter(
                e["su_stratum"] for e in emergencies if e["ground_truth_critical"]
            )),
            "critical_by_scarcity": {
                level: sum(s["n_ground_truth_critical"] for s in scenarios
                           if s["scarcity_level"] == level)
                for level in SCARCITY_LEVELS
            },
        },
        "critical_coverage_guarantee": {
            "scenarios_needing_su_redraw": sum(a > 1 for a in attempts),
            "max_attempts_used": max(attempts),
            "mean_attempts": statistics.fmean(attempts),
            "redraws_by_su_profile": dict(Counter(
                s["su_profile"] for s in scenarios if s["su_generation_attempts"] > 1
            )),
        },
        "overall_supply_to_demand_ratio_by_scarcity": ratio,
    }


def main() -> None:
    started = time.perf_counter()
    config = load_config()
    tolerance = config["metrics"]["paired_difference_tolerance"]
    selection_tolerance = config["selection_rule"]["tie_tolerance"]

    # Record the application files before evaluating anything.
    write_text(MANIFEST_PATH, json_text(application_manifest()))
    log(f"Recorded application manifest -> {MANIFEST_PATH.name}")

    dataset, dataset_sha256 = load_dataset()
    scenarios = dataset["scenarios"]
    levels = [s["scarcity_level"] for s in scenarios]

    grid = read_grid()
    if grid != build_grid():
        sys.exit("STOP: candidate_grid.csv differs from the fixed grid.")
    grid_sha256 = sha256_file(GRID_PATH)
    log(f"Loaded {len(scenarios)} scenarios and {len(grid)} candidate configurations")

    log("Computing ranking signatures for all 726 configurations ...")
    rankings = compute_rankings(dataset, grid)
    classes = rankings["classes"]
    distinct_orders = sum(len(orders) for orders in rankings["scenario_orders"])
    log(f"  {len(classes)} empirical ranking-equivalence classes; "
        f"{distinct_orders} distinct (scenario, order) pairs")

    log("Running the existing allocator ...")
    per_scenario, allocator_calls = evaluate_orders(
        dataset, rankings, config["existing_allocator"]["placeholder_inputs"]
    )
    log(f"  {allocator_calls} allocator calls, order verified on every call")

    fcfs_cdc = [entry["FCFS"]["cdc"] for entry in per_scenario]
    linear_cdc = [entry["LINEAR"]["cdc"] for entry in per_scenario]

    class_cdc = {}
    class_rows = {}

    for cls in classes:
        outcomes = [per_scenario[s]["orders"][cls["order_ids"][s]] for s in range(len(scenarios))]
        cdc = [o["cdc"] for o in outcomes]
        tdc = [o["tdc"] for o in outcomes]
        class_cdc[cls["class_id"]] = cdc
        class_rows[cls["class_id"]] = class_metrics(cdc, tdc, fcfs_cdc, linear_cdc, levels, tolerance)

    class_of = {}
    for cls in classes:
        for member in cls["members"]:
            class_of[member] = cls

    config_rows = []
    for index, candidate in enumerate(grid):
        cls = class_of[index]
        config_rows.append(
            {
                **candidate,
                "equivalence_class_id": cls["class_id"],
                "is_class_representative": cls["representative"] == index,
                **class_rows[cls["class_id"]],
            }
        )

    # ---- Winner: the predefined rule, applied mechanically ----
    winner, trace = select_winner(config_rows, selection_tolerance)
    top_10 = rank_by_selection_rule(config_rows, selection_tolerance, 10)
    log(f"Winner: {winner['config_id']} alpha={winner['alpha']} k={winner['k']} "
        f"m={winner['m']} n={winner['n']} mean CDC={winner['mean_cdc']:.6f}")

    winner_index = next(i for i, g in enumerate(grid) if g["config_id"] == winner["config_id"])
    winner_cls = class_of[winner_index]
    winner_class = winner_cls["class_id"]
    winner_outcomes = [
        per_scenario[s]["orders"][winner_cls["order_ids"][s]] for s in range(len(scenarios))
    ]
    winner_cdc = class_cdc[winner_class]
    other_classes = [row for row in config_rows if row["equivalence_class_id"] != winner_class]
    best_other, _ = select_winner(other_classes, selection_tolerance)

    # LINEAR is also a point of the grid (k = m = 0.5, n = 0).
    linear_order_ids = [
        rankings["scenario_orders"][s].index(tuple(linear_order(scenarios[s]["emergencies"])))
        for s in range(len(scenarios))
    ]
    linear_class = next((c["class_id"] for c in classes if c["order_ids"] == linear_order_ids), None)

    # ---- Baseline comparison and scarcity analysis ----
    policy_cdc = {"FCFS": fcfs_cdc, "LINEAR": linear_cdc, "AASHRAY": winner_cdc}
    policy_tdc = {
        "FCFS": [e["FCFS"]["tdc"] for e in per_scenario],
        "LINEAR": [e["LINEAR"]["tdc"] for e in per_scenario],
        "AASHRAY": [o["tdc"] for o in winner_outcomes],
    }

    comparison_fields = ["scope", "item"] + DISTRIBUTION_KEYS + ["mean_tdc", "n_higher", "n_lower", "n_equal"]

    def comparison_rows(scope, indices):
        rows = []
        for name in ("FCFS", "LINEAR", "AASHRAY"):
            values = [policy_cdc[name][i] for i in indices]
            stats = distribution(values)
            rows.append({"scope": scope, "item": f"{name}_CDC", **stats,
                         "mean_tdc": statistics.fmean(policy_tdc[name][i] for i in indices),
                         "n_higher": "", "n_lower": "", "n_equal": ""})
        for name in ("FCFS", "LINEAR"):
            difference = paired([winner_cdc[i] for i in indices],
                                [policy_cdc[name][i] for i in indices], tolerance)
            rows.append({"scope": scope, "item": f"AASHRAY_minus_{name}_CDC",
                         **{k: difference[k] for k in DISTRIBUTION_KEYS},
                         "mean_tdc": "", "n_higher": difference["n_higher"],
                         "n_lower": difference["n_lower"], "n_equal": difference["n_equal"]})
        return rows

    all_indices = list(range(len(scenarios)))
    baseline_rows = comparison_rows("ALL", all_indices)
    scarcity_rows = []
    for level in SCARCITY_LEVELS:
        scarcity_rows += comparison_rows(level, [i for i in all_indices if levels[i] == level])

    # ---- TDC (descriptive) ----
    tdc_range = [
        max(o["tdc"] for o in [e["FCFS"], e["LINEAR"], *e["orders"]])
        - min(o["tdc"] for o in [e["FCFS"], e["LINEAR"], *e["orders"]])
        for e in per_scenario
    ]
    tdc_summary = {
        "note": "Descriptive only; not used for selection.",
        "by_policy": {
            name: {
                "mean_tdc": statistics.fmean(policy_tdc[name]),
                "median_tdc": statistics.median(policy_tdc[name]),
            }
            for name in policy_tdc
        },
        "total_required": sum(e["FCFS"]["total_required"] for e in per_scenario),
        "total_fulfilled_fcfs": sum(e["FCFS"]["total_fulfilled"] for e in per_scenario),
        "total_unmet_fcfs": sum(e["FCFS"]["total_unmet"] for e in per_scenario),
        "scenarios_where_tdc_varies_across_any_evaluated_order": sum(r > 1e-12 for r in tdc_range),
        "max_tdc_range_across_orders": max(tdc_range),
    }

    # ---- Write result files ----
    config_fields = list(config_rows[0])
    write_text(CONFIGURATION_RESULTS_PATH, csv_text(config_rows, config_fields))

    top_rows = [
        {"rank": rank, **{k: row[k] for k in ("config_id", "alpha", "k", "m", "n",
         "mean_cdc", "median_cdc", "p10_cdc", "equivalence_class_id")}}
        for rank, row in enumerate(top_10, start=1)
    ]
    write_text(TOP_10_PATH, csv_text(top_rows, list(top_rows[0])))

    equivalence_rows = []
    for cls in classes:
        representative = grid[cls["representative"]]
        equivalence_rows.append({
            "equivalence_class_id": cls["class_id"],
            "representative_config_id": representative["config_id"],
            "alpha": representative["alpha"],
            "k": representative["k"],
            "m": representative["m"],
            "n": representative["n"],
            "number_of_equivalent_configurations": len(cls["members"]),
            "mean_cdc": class_rows[cls["class_id"]]["mean_cdc"],
            "member_config_ids": ";".join(grid[i]["config_id"] for i in cls["members"]),
        })
    write_text(EQUIVALENCE_PATH, csv_text(equivalence_rows, list(equivalence_rows[0])))

    write_text(BASELINE_PATH, csv_text(baseline_rows, comparison_fields))
    write_text(SCARCITY_PATH, csv_text(scarcity_rows, comparison_fields))
    write_per_scenario(per_scenario, dataset, classes)

    class_sizes = Counter(len(c["members"]) for c in classes)
    # One row per class (its representative), ranked by the same rule.
    class_representative_rows = [
        {
            **grid[cls["representative"]],
            "equivalence_class_id": cls["class_id"],
            **class_rows[cls["class_id"]],
        }
        for cls in classes
    ]
    top_classes = rank_by_selection_rule(
        class_representative_rows, selection_tolerance, 10
    )

    summary = {
        "experiment": config["experiment"],
        "stage": "DEVELOPMENT / parameter selection (not the final hypothesis test)",
        "master_seed": config["master_seed"],
        "dataset_file": "data/development_3000_scenarios.json",
        "dataset_sha256": dataset_sha256,
        "generation_config_sha256": dataset["generation_config_sha256"],
        "candidate_grid_sha256": grid_sha256,
        "application_manifest_sha256": sha256_file(MANIFEST_PATH),
        "dataset_distribution": dataset_distribution(dataset),
        "parameter_search": {
            "candidate_configurations": len(grid),
            "ranking_equivalence_classes": len(classes),
            "configurations_evaluated_after_deduplication": len(classes),
            "class_size_histogram": dict(sorted(class_sizes.items())),
            "distinct_scenario_order_pairs": distinct_orders,
            "allocator_calls": allocator_calls,
            "allocator_calls_order_verified": allocator_calls,
            "linear_baseline_equivalent_class": linear_class,
            "score_tie_tolerance": SCORE_TIE_TOLERANCE,
        },
        "winner": {
            **{k: winner[k] for k in ("config_id", "alpha", "k", "m", "n",
                                      "equivalence_class_id")},
            **{f"{key}_cdc": winner[f"{key}_cdc"] for key in DISTRIBUTION_KEYS},
            "mean_tdc": winner["mean_tdc"],
            "members_of_winning_class": len(winner_cls["members"]),
            "member_config_ids_of_winning_class": [grid[i]["config_id"] for i in winner_cls["members"]],
            "selection_trace": trace,
        },
        "stability": {
            "second_ranked_configuration": {k: top_10[1][k] for k in ("config_id", "alpha", "k", "m", "n", "mean_cdc", "equivalence_class_id")},
            "winner_minus_second_configuration_mean_cdc": winner["mean_cdc"] - top_10[1]["mean_cdc"],
            "best_configuration_in_another_class": {k: best_other[k] for k in ("config_id", "alpha", "k", "m", "n", "mean_cdc", "equivalence_class_id")},
            "winner_minus_best_other_class_mean_cdc": winner["mean_cdc"] - best_other["mean_cdc"],
            "configurations_within_1e-6_of_best_mean": sum(r["mean_cdc"] >= winner["mean_cdc"] - 1e-6 for r in config_rows),
            "classes_within_0.001_of_best_mean": sum(class_rows[c["class_id"]]["mean_cdc"] >= winner["mean_cdc"] - 0.001 for c in classes),
            "classes_within_0.01_of_best_mean": sum(class_rows[c["class_id"]]["mean_cdc"] >= winner["mean_cdc"] - 0.01 for c in classes),
            "top_10_classes": [
                {k: row[k] for k in ("equivalence_class_id", "config_id", "alpha", "k", "m", "n", "mean_cdc", "median_cdc", "p10_cdc")}
                for row in top_classes
            ],
        },
        "baseline_comparison": baseline_rows,
        "scarcity_analysis": scarcity_rows,
        "tdc": tdc_summary,
        "notes": [
            "Development results are in-sample: the winner is chosen on these scenarios, so its performance here is optimistic.",
            "LINEAR (0.5*S + 0.5*U) is itself a grid point (k = m = 0.5, n = 0), so the winner's development mean CDC cannot be below LINEAR's by construction.",
            "No hypothesis test is performed at this stage.",
        ],
    }
    write_text(SUMMARY_PATH, json_text(summary))

    log(f"Done in {time.perf_counter() - started:.1f}s; results in {SUMMARY_PATH.parent}")


if __name__ == "__main__":
    main()
