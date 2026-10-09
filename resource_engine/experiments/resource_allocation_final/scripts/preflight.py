"""Phase A: read-only pre-flight. Run once, before the final dataset exists.

Usage (from the repository root):

    python experiments/resource_allocation_final/scripts/preflight.py

Confirms the pre-registered settings, confirms no final dataset exists, and
records the environment, git state, a protected manifest of every file
outside the final experiment, and the hashes of the final config and
scripts (so later validation can prove none of them changed).
Exit code 1 = STOP.
"""

import sys
from datetime import datetime, timezone

from final_common import (
    CONFIG_PATH,
    DATASET_PATH,
    DEVELOPMENT_CONFIG_PATH,
    FROZEN_PARAMETERS_PATH,
    MILP_CONFIG_PATH,
    OFFICIAL,
    PREFLIGHT_PATH,
    PROTECTED_MANIFEST_PATH,
    environment_info,
    final_code_hashes,
    git_state,
    json_text,
    load_config,
    load_frozen_parameters,
    milp_options,
    protected_manifest,
    read_json,
    sha256_file,
    write_text,
)


CONFIRMED = {
    "master_seed": 20261209,
    "seed_namespace": "aashray-resource-allocation-final",
    "n_scenarios": 12000,
    "scarcity_counts": {"LOW": 1200, "MODERATE": 4800, "HIGH": 6000},
    "frozen": {"config_id": "C045", "alpha": 0.0, "k": 0.5, "m": 0.0, "n": 0.5},
    "gt_rule": "GT_critical = 1 if (S >= 0.8 AND U >= 0.8) OR S >= 0.95 OR U >= 0.95, else 0",
    "permutations": 100000, "permutation_seed": 20261210,
    "bootstrap": 10000, "bootstrap_seed": 20261211,
    "alpha": 0.05, "tie_tolerance": 1e-9,
    "milp_options": {"mip_rel_gap": 0.0, "time_limit": 60.0, "presolve": True, "disp": False},
}


def main() -> None:
    config = load_config()
    development = read_json(DEVELOPMENT_CONFIG_PATH)
    stats = config["statistics"]
    checks = {}

    checks["no_final_dataset_exists"] = not DATASET_PATH.exists()
    checks["frozen_parameters_as_confirmed"] = load_frozen_parameters() == CONFIRMED["frozen"]
    checks["gt_rule_is_frozen_development_rule"] = (
        config["ground_truth"]["rule"] == CONFIRMED["gt_rule"]
        and development["ground_truth"]["rule"] == CONFIRMED["gt_rule"]
    )
    checks["milp_options_as_validated"] = milp_options() == CONFIRMED["milp_options"]
    checks["generation_sections_identical_to_development"] = all(
        config[key] == development[key]
        for key in ("resource_types", "severity_urgency", "demand", "arrival",
                    "critical_coverage_guarantee")
    ) and all(
        config["scenario_design"][key] == development["scenario_design"][key]
        for key in ("scenario_sizes", "su_profiles", "warehouses_per_scenario")
    )
    checks["seed_differs_from_pilot_and_development"] = (
        config["master_seed"] not in (20261007, 20261108)
        and config["seed_namespace"] != development["seed_namespace"]
    )

    if OFFICIAL:
        checks["confirmed_seed_namespace_size"] = (
            config["master_seed"] == CONFIRMED["master_seed"]
            and config["seed_namespace"] == CONFIRMED["seed_namespace"]
            and config["n_scenarios"] == CONFIRMED["n_scenarios"]
            and {k: v["scenario_count"] for k, v in config["scenario_design"]["scarcity_levels"].items()}
            == CONFIRMED["scarcity_counts"]
        )
        checks["confirmed_statistics"] = (
            stats["primary_permutation_test"]["permutations"] == CONFIRMED["permutations"]
            and stats["primary_permutation_test"]["seed"] == CONFIRMED["permutation_seed"]
            and stats["bootstrap_ci"]["resamples"] == CONFIRMED["bootstrap"]
            and stats["bootstrap_ci"]["seed"] == CONFIRMED["bootstrap_seed"]
            and config["hypothesis"]["alpha"] == CONFIRMED["alpha"]
            and stats["tie_tolerance"] == CONFIRMED["tie_tolerance"]
        )

    passed = all(checks.values())

    write_text(PROTECTED_MANIFEST_PATH, json_text(protected_manifest()))

    write_text(PREFLIGHT_PATH, json_text({
        "passed": passed,
        "official_run": OFFICIAL,
        "checks": checks,
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "config_file": CONFIG_PATH.name,
        "final_code_hashes": final_code_hashes(),
        "frozen_parameters": load_frozen_parameters(),
        "frozen_parameters_sha256": sha256_file(FROZEN_PARAMETERS_PATH),
        "milp_config_sha256": sha256_file(MILP_CONFIG_PATH),
        "development_config_sha256": sha256_file(DEVELOPMENT_CONFIG_PATH),
        "protected_manifest_sha256": sha256_file(PROTECTED_MANIFEST_PATH),
        "git_before": git_state(),
        "environment": environment_info(),
    }))

    for name, ok in checks.items():
        print(f"[{'PASS' if ok else 'FAIL'}] {name}")

    if not passed:
        sys.exit("STOP: pre-flight failed.")
    print("Pre-flight passed; protected manifest and code hashes recorded.")


if __name__ == "__main__":
    main()
