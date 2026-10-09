"""Phases E-F: statistics and summary outputs, computed ONLY from the master
per-scenario CSV, and only after the Phase D gate has passed.

Usage (from the repository root):

    python experiments/resource_allocation_final/scripts/analyze_final.py
"""

import math
import sys

import numpy as np

from final_common import (
    FREEZE_PATH,
    GATE_PATH,
    METHOD_SUMMARY_PATH,
    SCARCITY_LEVELS,
    SCARCITY_SUMMARY_PATH,
    SCENARIO_RESULTS_PATH,
    STATISTICAL_TESTS_PATH,
    SUMMARY_PATH,
    WIN_TIE_LOSS_PATH,
    csv_text,
    json_text,
    load_config,
    parse_bool,
    parse_float,
    read_csv,
    read_json,
    write_text,
)
from final_statistics import bootstrap_ci, effect_sizes, permutation_test, wilcoxon_test


METHODS = ("FCFS", "AASHRAY", "MILP")
RUNTIME_COLUMN = {"FCFS": "fcfs_runtime_ms", "AASHRAY": "aashray_total_time_ms",
                  "MILP": "milp_total_time_ms"}
MILP_TDC_TEXT = "N/A - not an optimization benchmark"


def load_rows():
    rows = read_csv(SCENARIO_RESULTS_PATH)
    for row in rows:
        for key, value in row.items():
            if value in ("true", "false"):
                row[key] = parse_bool(value)
            elif key not in ("scenario_id", "scarcity", "size_class", "su_profile",
                             "scenario_input_sha256", "milp_message"):
                row[key] = parse_float(value)
    return rows


def distribution(values) -> dict:
    a = np.asarray(values, dtype=float)
    if a.size == 0:
        return {}
    return {
        "n": int(a.size),
        "mean": float(a.mean()),
        "median": float(np.median(a)),
        "std": float(a.std(ddof=1)) if a.size > 1 else math.nan,
        "p10": float(np.percentile(a, 10)),
        "p25": float(np.percentile(a, 25)),
        "p75": float(np.percentile(a, 75)),
        "p90": float(np.percentile(a, 90)),
        "p95": float(np.percentile(a, 95)),
        "p99": float(np.percentile(a, 99)),
        "min": float(a.min()),
        "max": float(a.max()),
    }


def runtime_stats(values) -> dict:
    stats = distribution(values)
    stats["total_ms"] = float(np.sum(values))
    stats["total_seconds"] = stats["total_ms"] / 1000.0
    return stats


def subset(rows, scarcity=None):
    return [r for r in rows if scarcity is None or r["scarcity"] == scarcity]


def cdc(rows, method):
    return [r[f"CDC_{method}"] for r in rows if r["cdc_defined"]]


def win_tie_loss(rows):
    valid = [r for r in rows if r["cdc_defined"]]
    n = len(valid)
    wins = sum(r["aashray_beats_fcfs"] for r in valid)
    ties = sum(r["aashray_equals_fcfs"] for r in valid)
    losses = sum(r["fcfs_beats_aashray"] for r in valid)
    return {"n": n, "aashray_wins": wins, "ties": ties, "fcfs_wins": losses,
            "aashray_win_pct": 100 * wins / n, "tie_pct": 100 * ties / n,
            "fcfs_win_pct": 100 * losses / n}


def optimality(rows):
    valid = [r for r in rows if r["cdc_defined"]]
    n = len(valid)
    gaps = [r["aashray_milp_gap_relative"] for r in valid]
    stats = distribution(gaps)
    ratios = [r["aashray_to_milp_cdc_ratio"] for r in valid if not math.isnan(r["aashray_to_milp_cdc_ratio"])]
    return {
        "n": n,
        "mean_gap": stats["mean"], "median_gap": stats["median"], "std_gap": stats["std"],
        "p90_gap": stats["p90"], "p95_gap": stats["p95"], "p99_gap": stats["p99"],
        "max_gap": stats["max"],
        "mean_absolute_gap_cdc_points": float(np.mean([r["aashray_milp_gap_absolute"] for r in valid])),
        "exact_optimum_pct": 100 * sum(r["aashray_reaches_milp"] for r in valid) / n,
        "within_1pct_pct": 100 * sum(r["aashray_within_1pct_milp"] for r in valid) / n,
        "within_5pct_pct": 100 * sum(r["aashray_within_5pct_milp"] for r in valid) / n,
        "within_10pct_pct": 100 * sum(r["aashray_within_10pct_milp"] for r in valid) / n,
        "scenarios_with_milp_cdc_zero_gap_defined_as_zero": sum(r["milp_cdc_zero_gap_defined_as_zero"] for r in valid),
        "aashray_to_milp_cdc_ratio": distribution(ratios),
        "gap_definition": "(CDC_MILP - CDC_AASHRAY) / CDC_MILP; 0 when CDC_MILP = 0",
    }


def fcfs_gap(rows):
    valid = [r for r in rows if r["cdc_defined"]]
    gaps = [0.0 if r["CDC_MILP"] == 0 else (r["CDC_MILP"] - r["CDC_FCFS"]) / r["CDC_MILP"] for r in valid]
    return float(np.mean(gaps)), float(np.median(gaps))


def method_block(rows, method):
    block = {"CDC": distribution(cdc(rows, method)),
             "runtime_ms": runtime_stats([r[RUNTIME_COLUMN[method]] for r in rows])}
    if method == "MILP":
        block["TDC"] = MILP_TDC_TEXT
        block["runtime_components_ms"] = {
            "build": runtime_stats([r["milp_build_time_ms"] for r in rows]),
            "solver": runtime_stats([r["milp_solver_time_ms"] for r in rows]),
        }
        block["tdc_solver_dependent_diagnostic_mean"] = float(np.mean([r["milp_tdc_solver_dependent"] for r in rows]))
    else:
        block["TDC"] = distribution([r[f"TDC_{method}"] for r in rows])
        decision = "fcfs_decision_time_ms" if method == "FCFS" else "aashray_decision_time_ms"
        allocation = "fcfs_allocation_time_ms" if method == "FCFS" else "aashray_allocation_time_ms"
        block["runtime_components_ms"] = {
            "decision": runtime_stats([r[decision] for r in rows]),
            "allocation": runtime_stats([r[allocation] for r in rows]),
        }
    return block


def speedup(rows) -> dict:
    milp = np.array([r["milp_total_time_ms"] for r in rows])
    aashray = np.array([r["aashray_total_time_ms"] for r in rows])
    per_scenario = milp / aashray
    return {
        "milp_over_aashray_total_time": float(milp.sum() / aashray.sum()),
        "milp_over_aashray_mean_time": float(milp.mean() / aashray.mean()),
        "milp_over_aashray_median_time": float(np.median(milp) / np.median(aashray)),
        "aashray_over_milp_total_time": float(aashray.sum() / milp.sum()),
        "per_scenario_ratio_milp_over_aashray": distribution(per_scenario),
        "scenarios_where_aashray_faster": int(np.count_nonzero(aashray < milp)),
        "note": "Ratios of totals/means/medians are primary; the per-scenario ratio distribution is shown, not averaged alone.",
    }


def paired_block(rows, config):
    valid = [r for r in rows if r["cdc_defined"]]
    delta = np.array([r["aashray_minus_fcfs_CDC"] for r in valid])
    relative = [r["aashray_relative_improvement_vs_fcfs"] for r in valid
                if not math.isnan(r["aashray_relative_improvement_vs_fcfs"])]
    mean_f = float(np.mean(cdc(rows, "FCFS")))
    mean_a = float(np.mean(cdc(rows, "AASHRAY")))
    return delta, {
        "n_valid_pairs": int(delta.size),
        "mean_difference": float(delta.mean()),
        "median_difference": float(np.median(delta)),
        "difference_distribution": distribution(delta),
        "percentage_point_improvement": 100 * (mean_a - mean_f),
        "relative_improvement_of_means": (mean_a - mean_f) / mean_f if mean_f else math.nan,
        "per_scenario_relative_improvement": distribution(relative) if relative else {},
        "scenarios_with_fcfs_cdc_zero_relative_improvement_undefined": sum(r["fcfs_cdc_zero"] for r in valid),
    }


def scarcity_rows(rows, level):
    part = subset(rows, level)
    out = []
    for method in METHODS:
        values = cdc(part, method)
        runtime = [r[RUNTIME_COLUMN[method]] for r in part]
        row = {
            "scarcity": level, "method": method, "n": len(values),
            "mean_CDC": float(np.mean(values)), "median_CDC": float(np.median(values)),
            "std_CDC": float(np.std(values, ddof=1)),
            "mean_TDC": MILP_TDC_TEXT if method == "MILP" else float(np.mean([r[f"TDC_{method}"] for r in part])),
            "median_TDC": MILP_TDC_TEXT if method == "MILP" else float(np.median([r[f"TDC_{method}"] for r in part])),
            "mean_runtime_ms": float(np.mean(runtime)), "median_runtime_ms": float(np.median(runtime)),
            "p95_runtime_ms": float(np.percentile(runtime, 95)),
            "mean_optimality_gap": "", "median_optimality_gap": "",
            "mean_aashray_minus_fcfs": "", "median_aashray_minus_fcfs": "",
            "aashray_win_pct": "", "tie_pct": "", "fcfs_win_pct": "",
        }
        if method == "AASHRAY":
            opt = optimality(part)
            wtl = win_tie_loss(part)
            delta = [r["aashray_minus_fcfs_CDC"] for r in part if r["cdc_defined"]]
            row.update({"mean_optimality_gap": opt["mean_gap"], "median_optimality_gap": opt["median_gap"],
                        "mean_aashray_minus_fcfs": float(np.mean(delta)),
                        "median_aashray_minus_fcfs": float(np.median(delta)),
                        "aashray_win_pct": wtl["aashray_win_pct"], "tie_pct": wtl["tie_pct"],
                        "fcfs_win_pct": wtl["fcfs_win_pct"]})
        if method == "FCFS":
            mean_gap, median_gap = fcfs_gap(part)
            row.update({"mean_optimality_gap": mean_gap, "median_optimality_gap": median_gap})
        out.append(row)
    return out


def main() -> None:
    gate = read_json(GATE_PATH) if GATE_PATH.exists() else None
    if not (gate and gate["passed"]):
        sys.exit("STOP: the Phase D gate has not passed; no statistical conclusions.")

    config = load_config()
    stats_config = config["statistics"]
    tie = stats_config["tie_tolerance"]
    alpha = config["hypothesis"]["alpha"]
    rows = load_rows()

    # ---- Primary and secondary tests (valid pairs only) ----
    delta, paired = paired_block(rows, config)
    permutation = permutation_test(delta, stats_config["primary_permutation_test"]["permutations"],
                                   stats_config["primary_permutation_test"]["seed"])
    bootstrap = bootstrap_ci(delta, stats_config["bootstrap_ci"]["resamples"],
                             stats_config["bootstrap_ci"]["seed"], stats_config["bootstrap_ci"]["level"])
    wilcox = wilcoxon_test(delta, tie)
    effect = effect_sizes(delta, tie)

    reject = permutation["p_value"] < alpha
    conclusion = ("Reject H0 at alpha = 0.05: the mean CDC difference (AASHRAY - FCFS) is "
                  "significantly greater than 0 on the held-out set."
                  if reject else
                  "Fail to reject H0 at alpha = 0.05: the held-out data do not show a mean CDC "
                  "difference (AASHRAY - FCFS) significantly greater than 0.")
    for block in (permutation,):
        block.update({"alpha": alpha, "reject_H0": reject, "conclusion": conclusion})
    wilcox.update({"alpha": alpha, "reject_H0_secondary": wilcox["p_value"] < alpha,
                   "role": "secondary; the permutation test is primary"})

    statistical_tests = {
        "hypothesis": config["hypothesis"],
        "valid_pairs": paired["n_valid_pairs"],
        "undefined_cdc_scenarios_excluded": sum(not r["cdc_defined"] for r in rows),
        "primary_permutation_test": permutation,
        "paired_bootstrap_ci": bootstrap,
        "secondary_wilcoxon_signed_rank": wilcox,
        "effect_size": effect,
    }
    write_text(STATISTICAL_TESTS_PATH, json_text(statistical_tests))

    # ---- Descriptive blocks ----
    overall = {method: method_block(rows, method) for method in METHODS}
    opt_all = optimality(rows)
    run = {method: overall[method]["runtime_ms"] for method in METHODS}
    run["speedup"] = speedup(rows)

    scarcity = {}
    scarcity_csv = []
    wtl_rows = []
    for scope in ("ALL",) + SCARCITY_LEVELS:
        part = rows if scope == "ALL" else subset(rows, scope)
        wtl = win_tie_loss(part)
        wtl_rows.append({"scope": scope, **wtl})
        if scope == "ALL":
            continue
        part_delta = np.array([r["aashray_minus_fcfs_CDC"] for r in part if r["cdc_defined"]])
        scarcity[scope] = {
            "n": len(part),
            "CDC": {m: distribution(cdc(part, m)) for m in METHODS},
            "TDC": {"FCFS": distribution([r["TDC_FCFS"] for r in part]),
                    "AASHRAY": distribution([r["TDC_AASHRAY"] for r in part]),
                    "MILP": MILP_TDC_TEXT},
            "paired_difference": {
                "mean": float(part_delta.mean()), "median": float(np.median(part_delta)),
                "percentage_points": 100 * float(part_delta.mean()),
                "bootstrap_95_ci_descriptive": bootstrap_ci(
                    part_delta, stats_config["bootstrap_ci"]["resamples"],
                    stats_config["bootstrap_ci"]["seed"], 0.95)["confidence_interval"],
                "note": "Descriptive per-stratum interval (same procedure and seed); the only hypothesis test is the overall one.",
            },
            "win_tie_loss": wtl,
            "optimality": optimality(part),
            "runtime_ms": {m: runtime_stats([r[RUNTIME_COLUMN[m]] for r in part]) for m in METHODS},
            "speedup": speedup(part),
        }
        scarcity_csv += scarcity_rows(rows, scope)

    by_size = {
        size: {m: runtime_stats([r[RUNTIME_COLUMN[m]] for r in rows if r["size_class"] == size]) for m in METHODS}
        for size in ("SMALL", "MEDIUM", "LARGE")
    }

    # ---- final_method_summary.csv ----
    method_csv = []
    for method in METHODS:
        c = overall[method]["CDC"]
        r = overall[method]["runtime_ms"]
        row = {"method": method, "n": c["n"],
               "mean_CDC": c["mean"], "median_CDC": c["median"], "std_CDC": c["std"],
               "P10_CDC": c["p10"], "P25_CDC": c["p25"], "P75_CDC": c["p75"], "P90_CDC": c["p90"],
               "P95_CDC": c["p95"], "min_CDC": c["min"], "max_CDC": c["max"],
               "mean_TDC": MILP_TDC_TEXT if method == "MILP" else overall[method]["TDC"]["mean"],
               "median_TDC": MILP_TDC_TEXT if method == "MILP" else overall[method]["TDC"]["median"],
               "mean_optimality_gap": "", "median_optimality_gap": "",
               "within_1pct": "", "within_5pct": "", "within_10pct": "", "exact_optimum": "",
               "runtime_mean_ms": r["mean"], "runtime_median_ms": r["median"], "runtime_P90_ms": r["p90"],
               "runtime_P95_ms": r["p95"], "runtime_P99_ms": r["p99"], "runtime_max_ms": r["max"],
               "runtime_total_s": r["total_seconds"]}
        if method == "AASHRAY":
            row.update({"mean_optimality_gap": opt_all["mean_gap"], "median_optimality_gap": opt_all["median_gap"],
                        "within_1pct": opt_all["within_1pct_pct"], "within_5pct": opt_all["within_5pct_pct"],
                        "within_10pct": opt_all["within_10pct_pct"], "exact_optimum": opt_all["exact_optimum_pct"]})
        method_csv.append(row)
    write_text(METHOD_SUMMARY_PATH, csv_text(method_csv, list(method_csv[0])))
    write_text(SCARCITY_SUMMARY_PATH, csv_text(scarcity_csv, list(scarcity_csv[0])))
    write_text(WIN_TIE_LOSS_PATH, csv_text(wtl_rows, list(wtl_rows[0])))

    # ---- final_summary.json ----
    freeze = read_json(FREEZE_PATH)
    summary = {
        "role": "FINAL held-out evaluation (12,000 scenarios). Conclusions here are based only on this set.",
        "dataset": {
            "total_scenarios": len(rows),
            "scarcity_counts": {level: len(subset(rows, level)) for level in SCARCITY_LEVELS},
            "seed": config["master_seed"], "seed_namespace": config["seed_namespace"],
            "generation_config_hash": freeze["generation_config_sha256"],
            "dataset_hash": freeze["sha256"],
            "undefined_cdc_scenarios": sum(not r["cdc_defined"] for r in rows),
        },
        "overall": overall,
        "hypothesis": {
            "H0": config["hypothesis"]["H0"], "H1": config["hypothesis"]["H1"], "alpha": alpha,
            "n_valid_pairs": paired["n_valid_pairs"],
            "mean_difference": paired["mean_difference"],
            "median_difference": paired["median_difference"],
            "percentage_point_improvement": paired["percentage_point_improvement"],
            "relative_improvement_of_means": paired["relative_improvement_of_means"],
            "confidence_interval_95": bootstrap["confidence_interval"],
            "permutation_p": permutation["p_value"],
            "wilcoxon_p": wilcox["p_value"],
            "effect_size": {"cohens_dz": effect["cohens_dz"],
                            "probability_of_superiority": effect["probability_of_superiority"],
                            "win_rate": effect["win_rate"], "tie_rate": effect["tie_rate"],
                            "fcfs_win_rate": effect["fcfs_win_rate"]},
            "conclusion": conclusion,
        },
        "paired_difference": paired,
        "win_tie_loss": wtl_rows,
        "optimality": opt_all,
        "runtime": {**run, "by_size_class": by_size},
        "scarcity": scarcity,
        "validation": {k: gate[k] for k in ("scenario_count", "valid_scenarios", "invalid_scenarios",
                                            "milp_optimal_count", "analytical_match_count", "failures")},
        "paper_tables": {
            "table_1_overall": {
                "columns": ["Metric", "FCFS", "AASHRAY", "MILP"],
                "rows": [
                    ["Mean CDC"] + [overall[m]["CDC"]["mean"] for m in METHODS],
                    ["Median CDC"] + [overall[m]["CDC"]["median"] for m in METHODS],
                    ["Std CDC"] + [overall[m]["CDC"]["std"] for m in METHODS],
                    ["Mean TDC", overall["FCFS"]["TDC"]["mean"], overall["AASHRAY"]["TDC"]["mean"], MILP_TDC_TEXT],
                    ["Median TDC", overall["FCFS"]["TDC"]["median"], overall["AASHRAY"]["TDC"]["median"], MILP_TDC_TEXT],
                    ["Mean runtime (ms)"] + [run[m]["mean"] for m in METHODS],
                    ["Median runtime (ms)"] + [run[m]["median"] for m in METHODS],
                    ["P95 runtime (ms)"] + [run[m]["p95"] for m in METHODS],
                ],
            },
            "table_2_by_scarcity": {
                "columns": ["Scarcity", "FCFS CDC", "AASHRAY CDC", "MILP CDC",
                            "AASHRAY-FCFS difference", "AASHRAY-MILP gap (mean relative)"],
                "rows": [[level, scarcity[level]["CDC"]["FCFS"]["mean"], scarcity[level]["CDC"]["AASHRAY"]["mean"],
                          scarcity[level]["CDC"]["MILP"]["mean"], scarcity[level]["paired_difference"]["mean"],
                          scarcity[level]["optimality"]["mean_gap"]] for level in SCARCITY_LEVELS],
            },
            "table_3_hypothesis_test": {
                "mean_paired_difference": paired["mean_difference"],
                "ci_95": bootstrap["confidence_interval"],
                "permutation_p": permutation["p_value"],
                "wilcoxon_p": wilcox["p_value"],
                "cohens_dz": effect["cohens_dz"],
                "aashray_win_pct": 100 * effect["win_rate"],
                "tie_pct": 100 * effect["tie_rate"],
                "fcfs_win_pct": 100 * effect["fcfs_win_rate"],
            },
            "table_4_optimality": {k: opt_all[k] for k in (
                "mean_gap", "median_gap", "p90_gap", "p95_gap", "max_gap", "within_1pct_pct",
                "within_5pct_pct", "within_10pct_pct", "exact_optimum_pct")},
            "table_5_computational_cost": {
                "AASHRAY_ms": {k: run["AASHRAY"][k] for k in ("mean", "median", "p95", "total_ms")},
                "MILP_ms": {k: run["MILP"][k] for k in ("mean", "median", "p95", "total_ms")},
                "speedup_milp_over_aashray_total": run["speedup"]["milp_over_aashray_total_time"],
                "speedup_milp_over_aashray_median": run["speedup"]["milp_over_aashray_median_time"],
            },
        },
        "graph_index": {
            "1_mean_cdc_by_method": "final_method_summary.csv: method, mean_CDC",
            "2_cdc_by_scarcity": "final_scarcity_summary.csv: scarcity, method, mean_CDC",
            "3_paired_difference_distribution": "final_scenario_results.csv: aashray_minus_fcfs_CDC (rows with cdc_defined = true)",
            "4_optimality_gap_distribution": "final_scenario_results.csv: aashray_milp_gap_relative",
            "5_optimality_gap_by_scarcity": "final_scenario_results.csv: scarcity, aashray_milp_gap_relative; summary in final_scarcity_summary.csv",
            "6_runtime_aashray_vs_milp": "final_scenario_results.csv: aashray_total_time_ms, milp_total_time_ms; summary in final_method_summary.csv",
            "7_runtime_by_scarcity": "final_scarcity_summary.csv: mean/median/p95_runtime_ms",
            "8_win_tie_loss": "final_win_tie_loss.csv",
            "9_cdc_distribution_all_methods": "final_scenario_results.csv: CDC_FCFS, CDC_AASHRAY, CDC_MILP",
            "10_aashray_vs_milp_cdc": "final_scenario_results.csv: CDC_MILP (x), CDC_AASHRAY (y); add a 45-degree line",
            "note": "MILP TDC is not an optimization benchmark and must not be plotted as one.",
        },
    }
    write_text(SUMMARY_PATH, json_text(summary))
    print("Analysis written.")


if __name__ == "__main__":
    main()
