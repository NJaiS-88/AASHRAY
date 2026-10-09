"""Collect every number used in the hypothesis-testing report.

Reads ONLY the validated final results (experiments/resource_allocation_final)
and writes data/report_data.json plus data/bootstrap_means.npy. Values that
are not stored directly in the result files are derived from the master CSV
with the documented definitions, and cross-checked where possible:

* the paired bootstrap distribution is regenerated with the pre-registered
  procedure (numpy default_rng, seed 20261211, chunks of 500) and must
  reproduce the stored 95% CI exactly;
* the Wilcoxon z-statistic is recomputed (normal approximation, average
  ranks, tie-corrected variance, zeros dropped) and its W+ must equal the
  stored statistic;
* summary means are recomputed from the master CSV and must agree.

Nothing under experiments/ is modified.
"""

import csv
import gzip
import json
import math
import statistics
import subprocess
import sys
from pathlib import Path

import numpy as np
from scipy.stats import norm, rankdata

REPORT_ROOT = Path(__file__).resolve().parents[1]
REPO = REPORT_ROOT.parents[1]
FINAL = REPO / "experiments" / "resource_allocation_final"
RESULTS = FINAL / "results"
DATA_OUT = REPORT_ROOT / "data"

TIE = 1e-9
LEVELS = ("LOW", "MODERATE", "HIGH")
METHODS = ("FCFS", "AASHRAY", "MILP")


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def num(text):
    if text in ("true", "false"):
        return text == "true"
    try:
        return float(text)
    except ValueError:
        return text


def check(condition, message):
    if not condition:
        sys.exit(f"STOP: {message}")


def main() -> None:
    summary = read_json(RESULTS / "final_summary.json")
    tests = read_json(RESULTS / "final_statistical_tests.json")
    validation = read_json(RESULTS / "validation_report.json")
    gate = read_json(RESULTS / "gate_report.json")
    run = read_json(RESULTS / "run_metadata.json")
    environment = read_json(RESULTS / "environment.json")
    freeze = read_json(RESULTS / "dataset_freeze.json")
    equivalence = read_json(RESULTS / "generator_equivalence.json")
    manifest = read_json(RESULTS / "file_hash_manifest.json")
    config = read_json(FINAL / "config" / "final_config.json")

    with open(RESULTS / "final_scenario_results.csv", encoding="utf-8", newline="") as file:
        rows = [{k: num(v) for k, v in r.items()} for r in csv.DictReader(file)]
    check(len(rows) == 12000, "master CSV must have 12,000 rows")

    # ---- CDC / TDC cross-checks ------------------------------------
    cdc = {}
    for m in METHODS:
        values = [r[f"CDC_{m}"] for r in rows]
        mean = statistics.fmean(values)
        check(abs(mean - summary["overall"][m]["CDC"]["mean"]) < 1e-12, f"{m} mean CDC mismatch")
        cdc[m] = {k: summary["overall"][m]["CDC"][k] for k in ("mean", "median", "std", "p10", "min", "max")}

    tdc_equal = all(r["TDC_FCFS"] == r["TDC_AASHRAY"] for r in rows)
    tdc = {
        "FCFS": summary["overall"]["FCFS"]["TDC"]["mean"],
        "AASHRAY": summary["overall"]["AASHRAY"]["TDC"]["mean"],
        "identical_in_every_scenario": tdc_equal,
        "by_scarcity": {lvl: summary["scarcity"][lvl]["TDC"]["FCFS"]["mean"] for lvl in LEVELS},
    }

    # ---- Primary test, CI, Wilcoxon, effect size ---------------------
    delta = np.array([r["CDC_AASHRAY"] - r["CDC_FCFS"] for r in rows])
    check(np.array_equal(delta, np.array([r["aashray_minus_fcfs_CDC"] for r in rows])), "delta column mismatch")

    permutation = tests["primary_permutation_test"]
    boot = tests["paired_bootstrap_ci"]

    # Regenerate the bootstrap distribution with the pre-registered procedure.
    rng = np.random.default_rng(boot["seed"])
    means = np.empty(boot["resamples"])
    for start in range(0, boot["resamples"], boot["chunk_size"]):
        size = min(boot["chunk_size"], boot["resamples"] - start)
        index = rng.integers(0, delta.size, size=(size, delta.size))
        means[start:start + size] = delta[index].mean(axis=1)
    lower, upper = np.percentile(means, boot["percentiles"])
    check([float(lower), float(upper)] == boot["confidence_interval"], "bootstrap regeneration does not reproduce the stored CI")
    DATA_OUT.mkdir(parents=True, exist_ok=True)
    np.save(DATA_OUT / "bootstrap_means.npy", means)

    # Wilcoxon z (normal approximation used by the final analysis).
    nonzero = delta[delta != 0]
    ranks = rankdata(np.abs(nonzero))
    w_plus = float(ranks[nonzero > 0].sum())
    wilcoxon = tests["secondary_wilcoxon_signed_rank"]
    check(w_plus == wilcoxon["statistic"], "recomputed W+ differs from the stored statistic")
    n = nonzero.size
    _, tie_counts = np.unique(ranks, return_counts=True)
    variance = n * (n + 1) * (2 * n + 1) / 24 - (tie_counts ** 3 - tie_counts).sum() / 48
    z = (w_plus - n * (n + 1) / 4) / math.sqrt(variance)
    log10_p = float(norm.logsf(z) / math.log(10))

    effect = tests["effect_size"]

    # ---- Win / tie / loss --------------------------------------------
    with open(RESULTS / "final_win_tie_loss.csv", encoding="utf-8", newline="") as file:
        wtl = {r["scope"]: {k: num(v) for k, v in r.items()} for r in csv.DictReader(file)}
    w = wtl["ALL"]
    check(w["aashray_wins"] + w["ties"] + w["fcfs_wins"] == 12000, "win/tie/loss must sum to 12,000")

    # ---- Scarcity -----------------------------------------------------
    scarcity = {}
    for lvl in LEVELS:
        part = [r for r in rows if r["scarcity"] == lvl]
        block = summary["scarcity"][lvl]
        gaps_rel = [r["aashray_milp_gap_relative"] for r in part]
        gaps_abs = [r["aashray_milp_gap_absolute"] for r in part]
        bins = {
            "exact": sum(g <= TIE for g in gaps_abs),
            "le_1pct": sum(r["aashray_milp_gap_absolute"] > TIE and r["aashray_milp_gap_relative"] <= 0.01 for r in part),
            "1_to_5pct": sum(0.01 < g <= 0.05 for g in gaps_rel),
            "5_to_10pct": sum(0.05 < g <= 0.10 for g in gaps_rel),
            "gt_10pct": sum(g > 0.10 for g in gaps_rel),
        }
        check(sum(bins.values()) == len(part), f"{lvl} gap bins do not sum")
        scarcity[lvl] = {
            "n": len(part),
            "cdc": {m: block["CDC"][m]["mean"] for m in METHODS},
            "cdc_median": {m: block["CDC"][m]["median"] for m in METHODS},
            "diff_mean": block["paired_difference"]["mean"],
            "diff_median": block["paired_difference"]["median"],
            "diff_ci_descriptive": block["paired_difference"]["bootstrap_95_ci_descriptive"],
            "mean_relative_gap": block["optimality"]["mean_gap"],
            "mean_absolute_gap": statistics.fmean(gaps_abs),
            "p95_relative_gap": block["optimality"]["p95_gap"],
            "max_relative_gap": block["optimality"]["max_gap"],
            "exact_pct": block["optimality"]["exact_optimum_pct"],
            "within_10_pct": block["optimality"]["within_10pct_pct"],
            "gap_bins": bins,
            "wins": block["win_tie_loss"]["aashray_wins"],
            "ties": block["win_tie_loss"]["ties"],
            "fcfs_wins": block["win_tie_loss"]["fcfs_wins"],
            "win_pct": block["win_tie_loss"]["aashray_win_pct"],
            "tie_pct": block["win_tie_loss"]["tie_pct"],
            "fcfs_win_pct": block["win_tie_loss"]["fcfs_win_pct"],
            "runtime_ms": {m: {k: block["runtime_ms"][m][k] for k in ("mean", "median", "p95")} for m in METHODS},
            "tdc": block["TDC"]["FCFS"]["mean"],
        }
    check(sum(s["n"] for s in scarcity.values()) == 12000, "scarcity counts must sum to 12,000")

    # ---- Optimality ----------------------------------------------------
    opt = summary["optimality"]
    exact_count = sum(r["aashray_reaches_milp"] for r in rows)
    optimality = {k: opt[k] for k in ("mean_gap", "median_gap", "std_gap", "p90_gap", "p95_gap", "p99_gap", "max_gap",
                                      "exact_optimum_pct", "within_1pct_pct", "within_5pct_pct", "within_10pct_pct",
                                      "scenarios_with_milp_cdc_zero_gap_defined_as_zero")}
    optimality.update({
        "exact_count": exact_count,
        "within_1_count": sum(r["aashray_within_1pct_milp"] for r in rows),
        "within_5_count": sum(r["aashray_within_5pct_milp"] for r in rows),
        "within_10_count": sum(r["aashray_within_10pct_milp"] for r in rows),
        "mean_absolute_gap": opt["mean_absolute_gap_cdc_points"],
    })

    # ---- Runtime (raw = pre-registered measurement; conservative = derived) ----
    def stats(values):
        return {"mean": statistics.fmean(values), "median": statistics.median(values),
                "p95": float(np.percentile(values, 95)), "total_s": math.fsum(values) / 1000.0}

    milp_t = [r["milp_total_time_ms"] for r in rows]
    raw_a = [r["aashray_total_time_ms"] for r in rows]
    conservative = [r["aashray_decision_time_ms"] + r["fcfs_allocation_time_ms"] for r in rows]
    first_slower = sum(r["fcfs_allocation_time_ms"] > r["aashray_allocation_time_ms"] for r in rows)
    runtime = {
        "AASHRAY_raw": stats(raw_a),
        "AASHRAY_conservative": stats(conservative),
        "MILP": stats(milp_t),
        "FCFS_raw": stats([r["fcfs_runtime_ms"] for r in rows]),
        "milp_build_mean": summary["overall"]["MILP"]["runtime_components_ms"]["build"]["mean"],
        "milp_solver_mean": summary["overall"]["MILP"]["runtime_components_ms"]["solver"]["mean"],
        "aashray_decision_mean": summary["overall"]["AASHRAY"]["runtime_components_ms"]["decision"]["mean"],
        "aashray_allocation_mean": summary["overall"]["AASHRAY"]["runtime_components_ms"]["allocation"]["mean"],
        "fcfs_allocation_mean": summary["overall"]["FCFS"]["runtime_components_ms"]["allocation"]["mean"],
        "speedup_raw_total": math.fsum(milp_t) / math.fsum(raw_a),
        "speedup_raw_median": statistics.median(milp_t) / statistics.median(raw_a),
        "speedup_conservative_total": math.fsum(milp_t) / math.fsum(conservative),
        "speedup_conservative_median": statistics.median(milp_t) / statistics.median(conservative),
        "scenarios_milp_slower_raw": sum(m > a for m, a in zip(milp_t, raw_a)),
        "scenarios_milp_slower_conservative": sum(m > c for m, c in zip(milp_t, conservative)),
        "first_position_allocation_slower": first_slower,
        "fcfs_runs_over_140ms": sum(r["fcfs_runtime_ms"] > 140 for r in rows),
        "fcfs_max_ms": max(r["fcfs_runtime_ms"] for r in rows),
        "conservative_definition": "AASHRAY decision time + the first-position (FCFS) allocation time of the same scenario",
    }
    check(abs(runtime["speedup_raw_total"] - summary["runtime"]["speedup"]["milp_over_aashray_total_time"]) < 1e-9,
          "raw speedup mismatch")

    # ---- Worst cases -----------------------------------------------------
    worst = [r for r in rows if r["CDC_AASHRAY"] == 0 and r["CDC_MILP"] > 0]
    example_row = min(worst, key=lambda r: (r["num_emergencies"], r["scenario_id"]))
    example_id = example_row["scenario_id"]

    dataset = json.loads((FINAL / "data" / "final_12000_scenarios.json").read_text(encoding="utf-8"))
    scenario = next(s for s in dataset["scenarios"] if s["scenario_id"] == example_id)
    lookup = {e["emergency_id"]: e for e in scenario["emergencies"]}
    order = []
    with gzip.open(RESULTS / "final_policy_allocations.csv.gz", "rt", encoding="utf-8", newline="") as file:
        for p in csv.DictReader(file):
            if p["scenario_id"] == example_id and p["method"] == "AASHRAY":
                e = lookup[p["emergency_id"]]
                order.append({
                    "rank": int(p["rank"]), "emergency_id": p["emergency_id"],
                    "severity": e["severity"], "urgency": e["urgency"], "score": float(p["aashray_score"]),
                    "gt_critical": int(p["ground_truth_critical"]),
                    "required": sum(int(p[f"required_{t}"]) for t in ("water", "food", "medical_kits")),
                    "allocated": sum(float(p[f"allocated_{t}"]) for t in ("water", "food", "medical_kits")),
                })
    # Mechanism diagnostic over all worst cases, from the frozen dataset inputs only.
    worst_ids = {r["scenario_id"] for r in worst}
    by_id = {s["scenario_id"]: s for s in dataset["scenarios"] if s["scenario_id"] in worst_ids}

    def is_both_high(e):
        return e["severity"] >= 0.8 and e["urgency"] >= 0.8

    top_noncritical = single_extreme_only = 0
    for sid in worst_ids:
        ems = by_id[sid]["emergencies"]
        crit = [e for e in ems if e["ground_truth_critical"] == 1]
        score = lambda e: 0.5 * e["severity"] + 0.5 * e["urgency"]
        top = max(ems, key=score)
        top_noncritical += int(top["ground_truth_critical"] == 0)
        single_extreme_only += int(not any(is_both_high(e) for e in crit))
    mechanism = {
        "top_ranked_emergency_noncritical": top_noncritical,
        "all_critical_via_single_extreme_rule_only": single_extreme_only,
        "gt_critical_emergencies_in_these": sum(
            sum(e["ground_truth_critical"] for e in by_id[sid]["emergencies"]) for sid in worst_ids),
    }

    worst_case = {
        "count": len(worst),
        "mechanism": mechanism,
        "by_scarcity": {lvl: sum(r["scarcity"] == lvl for r in worst) for lvl in LEVELS},
        "fcfs_cdc_mean_in_these": statistics.fmean(r["CDC_FCFS"] for r in worst),
        "milp_cdc_mean_in_these": statistics.fmean(r["CDC_MILP"] for r in worst),
        "example": {"scenario_id": example_id, "scarcity": example_row["scarcity"],
                    "num_emergencies": int(example_row["num_emergencies"]),
                    "supply": scenario["total_supply"], "cdc_fcfs": example_row["CDC_FCFS"],
                    "cdc_milp": example_row["CDC_MILP"], "aashray_order": order},
    }

    # ---- Integrity / environment ------------------------------------------
    tests_run = subprocess.run([sys.executable, "-m", "pytest", "resource_services/tests", "-q"],
                               cwd=REPO, capture_output=True, text=True)
    pytest_line = tests_run.stdout.strip().splitlines()[-1] if tests_run.stdout.strip() else ""

    val_checks = {c["id"]: c for c in validation["checks"]}
    distribution = freeze["pre_freeze_checks"]["distribution"]

    data = {
        "source": "experiments/resource_allocation_final (validated final results)",
        "dataset": {
            "n": summary["dataset"]["total_scenarios"],
            "scarcity_counts": summary["dataset"]["scarcity_counts"],
            "seed": config["master_seed"], "namespace": config["seed_namespace"],
            "sha256": freeze["sha256"], "generation_config_sha256": freeze["generation_config_sha256"],
            "frozen_at_utc": freeze["frozen_at_utc"], "bytes": freeze["bytes"],
            "emergencies_total": distribution["emergencies_total"],
            "emergencies_per_scenario": distribution["emergencies_per_scenario"],
            "gt_critical_emergencies": distribution["gt_critical_emergencies"],
            "scenarios_needing_su_redraw": distribution["scenarios_needing_su_redraw"],
            "scenario_sizes": config["scenario_design"]["scenario_sizes"],
            "warehouses_per_scenario": config["scenario_design"]["warehouses_per_scenario"],
            "scarcity_design": {lvl: {"ratio": v["supply_to_demand_ratio"], "rounding": v["supply_rounding"]}
                                for lvl, v in config["scenario_design"]["scarcity_levels"].items()},
            "su_bands": config["severity_urgency"]["bands"],
            "su_profiles": config["scenario_design"]["su_profiles"],
            "arrival_window_s": config["arrival"]["window_seconds"],
            "undefined_cdc": summary["dataset"]["undefined_cdc_scenarios"],
        },
        "frozen_parameters": config["frozen_aashray"]["expected"],
        "cdc": cdc,
        "tdc": tdc,
        "paired": {
            "n": permutation["n"], "mean": float(delta.mean()), "median": float(np.median(delta)),
            "pp": summary["hypothesis"]["percentage_point_improvement"],
            "relative_improvement": summary["hypothesis"]["relative_improvement_of_means"],
            "fcfs_cdc_zero": summary["paired_difference"]["scenarios_with_fcfs_cdc_zero_relative_improvement_undefined"],
        },
        "permutation": {k: permutation[k] for k in ("statistic", "n", "permutations", "seed", "permuted_means_at_least_observed",
                                                    "p_value", "p_value_formula", "smallest_attainable_p_value", "alpha", "reject_H0")},
        "bootstrap": {k: boot[k] for k in ("resamples", "seed", "level", "confidence_interval", "bootstrap_standard_error")},
        "bootstrap_regenerated_matches_stored_ci": True,
        "wilcoxon": {"statistic": wilcoxon["statistic"], "p_value_file": wilcoxon["p_value"],
                     "n_nonzero": wilcoxon["n_nonzero_differences"], "n_zero": wilcoxon["n_zero_differences"],
                     "z": z, "log10_p_normal_approx": log10_p, "method": wilcoxon["method"]},
        "effect": {k: effect[k] for k in ("cohens_dz", "sd_difference", "aashray_wins", "ties", "fcfs_wins", "win_rate",
                                          "tie_rate", "fcfs_win_rate", "probability_of_superiority",
                                          "probability_of_superiority_definition")},
        "win_tie_loss": wtl,
        "scarcity": scarcity,
        "optimality": optimality,
        "runtime": runtime,
        "worst_case": worst_case,
        "milp": {"proven_optimal": gate["milp_optimal_count"], "analytical_match": gate["analytical_match_count"],
                 "failures": len(gate["failures"]), "solver": "HiGHS " + environment["environment"]["highs_version"]
                 + " via scipy.optimize.milp (SciPy " + environment["environment"]["scipy_version"] + ")",
                 "options": run["milp_options_used"]},
        "integrity": {
            "gate": f'{len(gate["checks"]) - len(gate["failures"])}/{len(gate["checks"])}',
            "validation": f'{validation["n_pass"]}/{validation["n_checks"]}',
            "validation_failures": validation["n_fail"],
            "generator_byte_identical": equivalence["byte_identical"],
            "dev_overlap": val_checks["6"]["details"]["identical_content"],
            "pilot_overlap": val_checks["7"]["details"]["identical_content"],
            "scripts_unchanged_since_preflight": manifest["scripts_unchanged_since_preflight"],
            "protected_unchanged": {k: val_checks[k]["status"] for k in ("28", "29", "30", "E1", "E3", "26", "27")},
            "run_id": run["run_id"], "run_started": run["started_at_utc"], "warm_up": run["warm_up_scenarios"],
            "scenarios_run": run["scenarios_run"],
            "application_tests": pytest_line,
        },
        "environment": {k: environment["environment"][k] for k in ("cpu", "ram_gib", "os", "python_version", "scipy_version",
                                                                   "highs_version", "numpy_version")},
        "git_commit": environment["git_before_final_experiment"]["commit"],
        "statistics_config": config["statistics"],
        "discrepancies_with_request": [
            "Scarcity column requested as 'AASHRAY-MILP' with values 0.0012 / 0.0691: these are the mean relative "
            "optimality gaps (MILP-AASHRAY)/MILP. The difference of means AASHRAY-MILP is "
            f"{scarcity['MODERATE']['cdc']['AASHRAY'] - scarcity['MODERATE']['cdc']['MILP']:+.4f} (MODERATE) and "
            f"{scarcity['HIGH']['cdc']['AASHRAY'] - scarcity['HIGH']['cdc']['MILP']:+.4f} (HIGH). The report labels the column as the mean optimality gap.",
            f"Within-5% rate requested as 90.1%: the exact value is {opt['within_5pct_pct']:.2f}% "
            f"({optimality['within_5_count']:,}/12,000); reported with two decimals.",
            "Runtime figure requested 'conservative' values but quoted AASHRAY mean 0.248 ms, which is the raw "
            f"(order-affected) measurement; the conservative mean is {runtime['AASHRAY_conservative']['mean']:.3f} ms. Both are shown and labelled.",
            "Mean runtimes requested as 0.248 ms (AASHRAY) and 2.473 ms (MILP): the exact values are "
            f"{runtime['AASHRAY_raw']['mean']:.6f} ms and {runtime['MILP']['mean']:.6f} ms, i.e. "
            f"{runtime['AASHRAY_raw']['mean']:.3f} ms and {runtime['MILP']['mean']:.3f} ms to three decimals. "
            "0.248 / 2.473 came from rounding twice (to 4, then 3 decimals) in an earlier summary; the same "
            "rounding appears in experiments/resource_allocation_final/README.md, which was not modified.",
            "Reference PDF requested as 'AASHRAY_Hypothesis_Report(1).pdf'; the file found is "
            "Downloads/AASHRAY_Hypothesis_Report.pdf.",
        ],
    }

    (DATA_OUT / "report_data.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8", newline="\n")
    print("report_data.json written; all cross-checks passed")
    print("application tests:", pytest_line)
    print("Wilcoxon z = %.2f, log10 p = %.1f" % (z, log10_p))
    print("worst-case example:", example_id, "with", len(order), "emergencies")


if __name__ == "__main__":
    main()
