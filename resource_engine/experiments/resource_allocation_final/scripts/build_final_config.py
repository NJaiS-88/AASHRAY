"""Build config/final_config.json from the validated development config.

Usage (from the repository root), once, before the pre-flight:

    python experiments/resource_allocation_final/scripts/build_final_config.py

Every generation section is copied verbatim from the development config.
Only the confirmed differences are applied: master seed, namespace, scenario
counts and identifier labels. The script asserts that the copied sections
are identical, and refuses to overwrite an existing final config.
"""

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
DEV_CONFIG = REPO / "experiments" / "resource_allocation_development" / "config" / "development_config.json"
FINAL_CONFIG = ROOT / "config" / "final_config.json"


def build() -> dict:
    dev = json.loads(DEV_CONFIG.read_text(encoding="utf-8"))

    design = copy.deepcopy(dev["scenario_design"])
    for level, count in (("LOW", 1200), ("MODERATE", 4800), ("HIGH", 6000)):
        design["scarcity_levels"][level]["scenario_count"] = count
    design["scarcity_note"] = (
        "Pre-registered before generation: LOW 1,200 / MODERATE 4,800 / HIGH 6,000 "
        "(same 10/40/50 proportions as development). Not to be rebalanced after results."
    )
    design["cell_allocation_rule"] = (
        "Each scarcity level is spread evenly over the same 15 size x S-U-profile cells "
        "as development: LOW 80, MODERATE 320, HIGH 400 scenarios per cell."
    )

    config = {
        "experiment": "resource_allocation_final",
        "role": "FINAL held-out hypothesis test with pre-registered settings. "
                "Not development, not tuning, not exploratory.",
        "master_seed": 20261209,
        "seed_namespace": "aashray-resource-allocation-final",
        "excluded_seeds": {"pilot": 20261007, "development": 20261108},
        "excluded_namespaces": [dev["seed_namespace"]],
        "n_scenarios": 12000,
        "resource_types": dev["resource_types"],
        "scenario_design": design,
        "severity_urgency": dev["severity_urgency"],
        "demand": dev["demand"],
        "arrival": dev["arrival"],
        "ground_truth": {
            "rule": "GT_critical = 1 if (S >= 0.8 AND U >= 0.8) OR S >= 0.95 OR U >= 0.95, else 0",
            "both_high_threshold": 0.8,
            "single_extreme_threshold": 0.95,
            "status": "FROZEN development reference rule, applied unchanged. A predefined "
                      "experimental reference rule, not an externally validated truth. "
                      "Independent of alpha, k, m, n, every allocation method and the MILP.",
        },
        "critical_coverage_guarantee": dev["critical_coverage_guarantee"],
        "identifiers": {
            "scenario_prefix": "FIN",
            "index_digits": 5,
            "warehouse_name": "Final Warehouse",
            "note": "Labels only; they feed no random stream. Within a scenario the "
                    "emergency-id order is the same as in development, so FCFS "
                    "tie-breaking is unchanged.",
        },
        "generator_equivalence_requirement": (
            "The copied generator, run with the development config, identifiers and "
            "metadata, must reproduce "
            "experiments/resource_allocation_development/data/development_3000_scenarios.json "
            "byte for byte."
        ),
        "methods": {
            "FCFS": "Validated development implementation "
                    "(experiments/resource_allocation_development/scripts/policies.py: "
                    "fcfs_order): ascending (arrival_timestamp, emergency_id); sees only "
                    "id and arrival.",
            "AASHRAY": "Validated development implementation (policies.py: aashray_order) "
                       "with the frozen parameters read from frozen_parameters.json; "
                       "descending P_o, ties (within 1e-12) in FCFS order.",
            "MILP": "Validated implementation "
                    "experiments/resource_allocation_milp/scripts/milp_model.py "
                    "(run_scenario) with the options in "
                    "experiments/resource_allocation_milp/config/milp_config.json; unmodified.",
            "allocator": "FCFS and AASHRAY orders go to the existing "
                         "ResourceAllocationService.allocate_batch, unchanged, with identical "
                         "placeholder priority inputs so the presented order is kept "
                         "(verified on every call).",
            "placeholder_inputs": dev["existing_allocator"]["placeholder_inputs"],
        },
        "frozen_aashray": {
            "source": "experiments/resource_allocation_development/results/frozen_parameters.json",
            "expected": {"config_id": "C045", "alpha": 0.0, "k": 0.5, "m": 0.0, "n": 0.5},
            "equivalent_ranking": "0.5*S + 0.5*U",
        },
        "hypothesis": {
            "primary_metric": "CDC",
            "difference": "Delta_i = CDC_AASHRAY,i - CDC_FCFS,i",
            "H0": "mean(Delta) <= 0",
            "H1": "mean(Delta) > 0",
            "alpha": 0.05,
            "valid_pairs": "scenarios where both CDC values are defined (critical_required > 0)",
            "decision": "reject H0 if the permutation p-value < 0.05; otherwise fail to "
                        "reject H0 (never accept H0)",
        },
        "statistics": {
            "primary_permutation_test": {
                "type": "one-sided paired sign-flip randomization test",
                "statistic": "mean(Delta)",
                "permutations": 100000,
                "seed": 20261210,
                "rng": "numpy.random.default_rng (PCG64)",
                "p_value": "(1 + number of permuted means >= observed mean) / (permutations + 1)",
            },
            "bootstrap_ci": {
                "type": "paired percentile bootstrap of mean(Delta)",
                "resamples": 10000,
                "seed": 20261211,
                "level": 0.95,
                "percentiles": [2.5, 97.5],
            },
            "secondary_wilcoxon": {
                "type": "one-sided paired Wilcoxon signed-rank (scipy.stats.wilcoxon)",
                "alternative": "greater (AASHRAY > FCFS)",
                "zero_method": "wilcox (zero differences dropped from the test, counted separately)",
            },
            "effect_size": {
                "cohens_dz": "mean(Delta) / sample SD(Delta) (ddof = 1); NaN if SD = 0",
                "also": ["win rate", "tie rate", "FCFS win rate",
                         "probability of superiority = (wins + 0.5 * ties) / n"],
            },
            "tie_tolerance": 1e-9,
            "tie_rule": "|CDC_AASHRAY - CDC_FCFS| <= 1e-9 is a tie; the same tolerance is "
                        "used for wins, losses and the exact-optimum test",
            "percentile_method": "linear interpolation (numpy default)",
        },
        "edge_cases": {
            "cdc_undefined": "critical_required == 0 -> CDC = NaN for every method; excluded "
                             "from the paired test; counted",
            "relative_improvement": "(CDC_AASHRAY - CDC_FCFS) / CDC_FCFS; NaN when "
                                    "CDC_FCFS == 0 (counted separately, never infinity)",
            "optimality_gap": "relative gap = (CDC_MILP - CDC_AASHRAY) / CDC_MILP; if "
                              "critical_required > 0 and CDC_MILP == 0, AASHRAY must also be "
                              "0 and the gap is defined as 0 (flagged); NaN when CDC is undefined",
            "within_x_percent": "relative gap <= x / 100",
            "exact_optimum": "CDC_MILP - CDC_AASHRAY <= 1e-9",
        },
        "tdc": "TDC is computed for FCFS and AASHRAY only. MILP total fulfilment is stored "
               "only as milp_tdc_solver_dependent (diagnostic) and is never a benchmark.",
        "timing": {
            "timer": "time.perf_counter",
            "fcfs": "decision (fcfs_order) + allocation (building the allocator requests + "
                    "allocate_batch)",
            "aashray": "decision (scores + order) + allocation (building the allocator "
                       "requests + allocate_batch)",
            "milp": "model build + solver (the validated run_scenario timing)",
            "excluded": "dataset loading/generation, Python start-up, warm-up, writing and "
                        "loading each scenario's inventory file (the existing allocator only "
                        "loads warehouses from a file), order verification, result "
                        "extraction, file writing",
            "warm_up": "the first 3 scenarios are run once for every method before timing "
                       "starts; those warm-up runs are not recorded",
            "execution": "single process; scenarios in dataset order; within each scenario "
                         "FCFS, then AASHRAY, then MILP",
        },
        "tolerances": {
            "cdc_tdc_upper_bound": 1e-12,
            "aashray_not_above_milp": 1e-12,
        },
    }

    # Every generation section must be an exact copy of the development design.
    for key in ("severity_urgency", "demand", "arrival", "critical_coverage_guarantee",
                "resource_types"):
        assert config[key] == dev[key], key
    for key in ("scenario_sizes", "su_profiles", "warehouses_per_scenario"):
        assert config["scenario_design"][key] == dev["scenario_design"][key], key
    for level in ("LOW", "MODERATE", "HIGH"):
        final_level = config["scenario_design"]["scarcity_levels"][level]
        dev_level = dev["scenario_design"]["scarcity_levels"][level]
        assert final_level["supply_to_demand_ratio"] == dev_level["supply_to_demand_ratio"]
        assert final_level["supply_rounding"] == dev_level["supply_rounding"]

    return config


def main() -> None:
    if FINAL_CONFIG.exists():
        sys.exit(f"STOP: {FINAL_CONFIG} already exists; it is never rebuilt.")

    config = build()
    FINAL_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    FINAL_CONFIG.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n",
                            encoding="utf-8", newline="\n")
    print(f"Wrote {FINAL_CONFIG}; generation sections identical to development (except counts)")


if __name__ == "__main__":
    main()
