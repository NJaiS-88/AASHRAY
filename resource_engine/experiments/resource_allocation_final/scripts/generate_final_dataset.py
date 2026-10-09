"""Generate, validate, hash and FREEZE the 12,000-scenario final test set.

Usage (from the repository root, after preflight.py):

    python experiments/resource_allocation_final/scripts/generate_final_dataset.py

The generation logic is a verbatim copy of the validated development
generator (experiments/resource_allocation_development/scripts/
generate_development_dataset.py). Only identifiers (scenario-id prefix and
width, warehouse display name) and dataset metadata are parameterised; the
development file caps its size at 3,000, so it cannot be called directly.

Steps (exit code 1 = STOP, nothing frozen):
1. Equivalence proof: the copy, run with the development config,
   identifiers and metadata, must reproduce the development dataset
   byte for byte.
2. Generate the final dataset from the final config.
3. Validate it (schema, counts, uniqueness, GT labels, >=1 critical,
   scarcity cells, arrival independence, no overlap with pilot or
   development data).
4. Write it, hash it, record the freeze and make the file read-only.
"""

import copy
import hashlib
import json
import math
import os
import random
import stat
import statistics
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from final_common import (
    DATASET_PATH,
    DEVELOPMENT_CONFIG_PATH,
    DEVELOPMENT_DATASET_PATH,
    FREEZE_PATH,
    GENERATOR_EQUIVALENCE_PATH,
    OFFICIAL,
    OFFICIAL_SCENARIO_COUNT,
    PILOT_DATASET_PATH,
    PREFLIGHT_PATH,
    REPO_ROOT,
    content_fingerprint,
    derive_seed,
    gt_clauses,
    ground_truth_critical,
    json_text,
    load_config,
    read_json,
    sha256_text,
    write_text,
)


GENERATION_CONFIG_KEYS = [
    "master_seed",
    "seed_namespace",
    "n_scenarios",
    "resource_types",
    "scenario_design",
    "severity_urgency",
    "demand",
    "arrival",
    "ground_truth",
    "critical_coverage_guarantee",
]

PER_PERSON_RATES_PATH = REPO_ROOT / "resource_services" / "config" / "resource_rules.json"

DEVELOPMENT_IDENTIFIERS = {"scenario_prefix": "DEV", "index_digits": 4,
                           "warehouse_name": "Development Warehouse"}
DEVELOPMENT_IDENTITY = {
    "dataset": "resource_allocation_development",
    "dataset_role": "DEVELOPMENT / parameter selection only. Not the pilot and not the final test set.",
    "generator": "experiments/resource_allocation_development/scripts/generate_development_dataset.py",
}
FINAL_IDENTITY = {
    "dataset": "resource_allocation_final",
    "dataset_role": "FINAL held-out test set. Generated once, frozen and hashed before any method was run.",
    "generator": "experiments/resource_allocation_final/scripts/generate_final_dataset.py",
}

CORRELATION_LIMIT = 0.05


# ----------------------------------------------------------------------
# Generation logic: verbatim copy of the validated development generator
# ----------------------------------------------------------------------


def generation_config_hash(config: dict) -> str:
    subset = {key: config[key] for key in GENERATION_CONFIG_KEYS}
    text = json.dumps(subset, sort_keys=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_per_person_rates(resource_types: list[str]) -> dict[str, float]:
    with PER_PERSON_RATES_PATH.open("r", encoding="utf-8") as file:
        rules = json.load(file)

    return {
        resource: float(rules["resources"][resource]["base_per_person"])
        for resource in resource_types
    }


def build_scenario_cells(config: dict) -> list[dict]:
    design = config["scenario_design"]
    combos = [
        (size, profile)
        for size in design["scenario_sizes"]
        for profile in design["su_profiles"]
    ]

    cells = []

    for scarcity, spec in design["scarcity_levels"].items():
        per_cell, remainder = divmod(spec["scenario_count"], len(combos))

        if remainder:
            raise ValueError(
                f"{scarcity}: {spec['scenario_count']} scenarios do not "
                f"divide evenly over {len(combos)} cells."
            )

        for size, profile in combos:
            cells.extend(
                {
                    "scarcity_level": scarcity,
                    "size_class": size,
                    "su_profile": profile,
                }
                for _ in range(per_cell)
            )

    random.Random(
        derive_seed(
            config["seed_namespace"],
            config["master_seed"],
            "scenario_order",
        )
    ).shuffle(cells)

    return cells


def integer_split(total: int, weights: list[float]) -> list[int]:
    weight_sum = sum(weights)
    raw = [total * weight / weight_sum for weight in weights]
    shares = [math.floor(value) for value in raw]
    remainder = total - sum(shares)

    order = sorted(
        range(len(weights)),
        key=lambda index: (-(raw[index] - shares[index]), index),
    )

    for index in order[:remainder]:
        shares[index] += 1

    return shares


def round_supply(value: float, rule: str) -> int:
    if rule == "ceil":
        return math.ceil(value)
    if rule == "floor":
        return math.floor(value)
    return int(round(value))


def draw_severity_urgency(config, scenario_seed, n_emergencies, su_profile, su_salt):
    su_config = config["severity_urgency"]
    bands = su_config["bands"]
    strata = su_config["emergency_strata"]
    decimals = su_config["decimals"]
    weights = su_config["profile_weights"][su_profile]
    stratum_names = list(weights)
    stratum_weights = [weights[name] for name in stratum_names]

    max_attempts = config["critical_coverage_guarantee"]["max_attempts"]

    for attempt in range(max_attempts):
        su_rng = random.Random(derive_seed(scenario_seed, su_salt, attempt))

        draws = []

        for _ in range(n_emergencies):
            stratum = su_rng.choices(stratum_names, weights=stratum_weights)[0]
            severity_band, urgency_band = strata[stratum]

            severity = round(su_rng.uniform(*bands[severity_band]), decimals)
            urgency = round(su_rng.uniform(*bands[urgency_band]), decimals)

            draws.append((stratum, severity, urgency))

        if any(ground_truth_critical(s, u) for _, s, u in draws):
            return draws, attempt + 1

    raise RuntimeError(f"No GT-critical emergency after {max_attempts} attempts.")


def generate_emergencies(config, scenario_id, scenario_seed, n_emergencies, su_profile,
                         per_person_rates, arrival_salt, su_salt):

    demand_config = config["demand"]
    population = demand_config["affected_population"]
    multiplier_low, multiplier_high = demand_config["type_multiplier"]
    patterns = demand_config["required_type_patterns"]
    pattern_names = list(patterns)
    pattern_weights = [patterns[name]["weight"] for name in pattern_names]

    arrival_config = config["arrival"]
    base_time = datetime.strptime(arrival_config["base_timestamp"], "%Y-%m-%dT%H:%M:%SZ")

    resource_types = config["resource_types"]

    su_draws, su_attempts = draw_severity_urgency(
        config, scenario_seed, n_emergencies, su_profile, su_salt
    )

    arrival_rng = random.Random(derive_seed(scenario_seed, arrival_salt))
    demand_rng = random.Random(derive_seed(scenario_seed, "demand"))

    emergencies = []

    for index, (stratum, severity, urgency) in enumerate(su_draws):

        offset = arrival_rng.randint(0, arrival_config["window_seconds"])

        affected_population = demand_rng.randrange(
            population["min"], population["max"] + 1, population["step"]
        )
        pattern = demand_rng.choices(pattern_names, weights=pattern_weights)[0]
        required_types = set(patterns[pattern]["types"])

        requirements = {}

        for resource in resource_types:
            multiplier = demand_rng.uniform(multiplier_low, multiplier_high)

            if resource in required_types:
                requirements[resource] = max(
                    1,
                    int(round(per_person_rates[resource] * affected_population * multiplier)),
                )
            else:
                requirements[resource] = 0

        clauses = gt_clauses(severity, urgency)

        emergencies.append(
            {
                "emergency_id": f"{scenario_id}-E{index + 1:02d}",
                "severity": severity,
                "urgency": urgency,
                "su_stratum": stratum,
                "arrival_offset_seconds": offset,
                "arrival_timestamp": (
                    base_time + timedelta(seconds=offset)
                ).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "affected_population": affected_population,
                "demand_pattern": pattern,
                "resource_requirements": requirements,
                "gt_rule_inputs": {
                    "severity": severity,
                    "urgency": urgency,
                    "both_high_threshold": 0.8,
                    "single_extreme_threshold": 0.95,
                    "both_high": clauses["both_high"],
                    "severity_extreme": clauses["severity_extreme"],
                    "urgency_extreme": clauses["urgency_extreme"],
                },
                "ground_truth_critical": ground_truth_critical(severity, urgency),
            }
        )

    return emergencies, su_attempts


def generate_inventory(config, scenario_id, scenario_seed, n_warehouses, scarcity_level,
                       total_demand, warehouse_name):

    scarcity = config["scenario_design"]["scarcity_levels"][scarcity_level]
    ratio_low, ratio_high = scarcity["supply_to_demand_ratio"]

    inventory_rng = random.Random(derive_seed(scenario_seed, "inventory"))
    location_rng = random.Random(derive_seed(scenario_seed, "location"))

    total_supply = {}
    design_ratio = {}
    shares_by_type = {}

    for resource in config["resource_types"]:
        ratio = inventory_rng.uniform(ratio_low, ratio_high)
        design_ratio[resource] = round(ratio, 6)

        demand = total_demand[resource]

        supply = (
            round_supply(ratio * demand, scarcity["supply_rounding"]) if demand > 0 else 0
        )
        total_supply[resource] = supply

        weights = [inventory_rng.uniform(0.2, 1.0) for _ in range(n_warehouses)]
        shares_by_type[resource] = integer_split(supply, weights)

    warehouses = []

    for index in range(n_warehouses):

        inventory = {}

        for resource in config["resource_types"]:
            available = shares_by_type[resource][index]
            inventory[resource] = {
                "available": available,
                "capacity": available + inventory_rng.randint(0, available),
            }

        warehouses.append(
            {
                "warehouse_id": f"{scenario_id}-WH{index + 1}",
                "name": f"{warehouse_name} {index + 1}",
                "location": {
                    "latitude": round(location_rng.uniform(18.90, 19.30), 4),
                    "longitude": round(location_rng.uniform(72.80, 73.10), 4),
                },
                "inventory": inventory,
                "vehicles": {},
            }
        )

    return warehouses, total_supply, design_ratio


def generate_scenario(config, index, cell, per_person_rates, identifiers, arrival_salt, su_salt):

    master_seed = config["master_seed"]
    scenario_id = (
        f"{identifiers['scenario_prefix']}-{index:0{identifiers['index_digits']}d}"
    )
    scenario_seed = derive_seed(config["seed_namespace"], master_seed, "scenario", index)

    design = config["scenario_design"]
    structure_rng = random.Random(derive_seed(scenario_seed, "structure"))

    size_low, size_high = design["scenario_sizes"][cell["size_class"]]
    n_emergencies = structure_rng.randint(size_low, size_high)

    warehouses_low, warehouses_high = design["warehouses_per_scenario"]
    n_warehouses = structure_rng.randint(warehouses_low, warehouses_high)

    emergencies, su_attempts = generate_emergencies(
        config, scenario_id, scenario_seed, n_emergencies, cell["su_profile"],
        per_person_rates, arrival_salt, su_salt,
    )

    total_demand = {
        resource: sum(e["resource_requirements"][resource] for e in emergencies)
        for resource in config["resource_types"]
    }

    warehouses, total_supply, design_ratio = generate_inventory(
        config, scenario_id, scenario_seed, n_warehouses, cell["scarcity_level"],
        total_demand, identifiers["warehouse_name"],
    )

    return {
        "scenario_id": scenario_id,
        "master_seed": master_seed,
        "scenario_seed": scenario_seed,
        "scarcity_level": cell["scarcity_level"],
        "size_class": cell["size_class"],
        "su_profile": cell["su_profile"],
        "n_emergencies": n_emergencies,
        "n_warehouses": n_warehouses,
        "n_ground_truth_critical": sum(e["ground_truth_critical"] for e in emergencies),
        "su_generation_attempts": su_attempts,
        "total_demand": total_demand,
        "total_supply": total_supply,
        "design_supply_to_demand_ratio": design_ratio,
        "overall_supply_to_demand_ratio": round(
            sum(total_supply.values()) / sum(total_demand.values()), 6
        ),
        "resource_inventory": warehouses,
        "emergencies": emergencies,
    }


def generate_dataset(config, identifiers, identity, arrival_salt="arrival",
                     su_salt="severity_urgency"):

    cells = build_scenario_cells(config)

    if len(cells) != config["n_scenarios"]:
        raise ValueError(f"Scenario design yields {len(cells)} cells, config says "
                         f"{config['n_scenarios']}.")

    per_person_rates = load_per_person_rates(config["resource_types"])

    scenarios = [
        generate_scenario(config, index, cell, per_person_rates, identifiers,
                          arrival_salt, su_salt)
        for index, cell in enumerate(cells, start=1)
    ]

    return {
        "dataset": identity["dataset"],
        "dataset_role": identity["dataset_role"],
        "master_seed": config["master_seed"],
        "seed_namespace": config["seed_namespace"],
        "n_scenarios": len(scenarios),
        "ground_truth_rule": config["ground_truth"]["rule"],
        "generator": identity["generator"],
        "generation_config_sha256": generation_config_hash(config),
        "per_person_rates_used": per_person_rates,
        "scenarios": scenarios,
    }


def dataset_text(dataset: dict) -> str:
    lines = ["{"]

    for key, value in dataset.items():
        if key != "scenarios":
            lines.append(f"  {json.dumps(key)}: {json.dumps(value)},")

    lines.append('  "scenarios": [')
    lines.append(
        ",\n".join(
            "    " + json.dumps(scenario, separators=(",", ":"))
            for scenario in dataset["scenarios"]
        )
    )
    lines.append("  ]")
    lines.append("}")

    return "\n".join(lines) + "\n"


# ----------------------------------------------------------------------
# Equivalence proof, pre-freeze validation and freeze
# ----------------------------------------------------------------------


def prove_generator_equivalence() -> dict:
    development_config = read_json(DEVELOPMENT_CONFIG_PATH)
    expected = DEVELOPMENT_DATASET_PATH.read_text(encoding="utf-8")
    reproduced = dataset_text(
        generate_dataset(development_config, DEVELOPMENT_IDENTIFIERS, DEVELOPMENT_IDENTITY)
    )
    return {
        "requirement": "copied generator + development config reproduces the development dataset byte for byte",
        "development_dataset": DEVELOPMENT_DATASET_PATH.relative_to(REPO_ROOT).as_posix(),
        "development_dataset_sha256": sha256_text(expected),
        "reproduced_sha256": sha256_text(reproduced),
        "byte_identical": reproduced == expected,
        "bytes": len(expected.encode("utf-8")),
    }


def exact_critical(severity, urgency):
    s, u = Decimal(repr(severity)), Decimal(repr(urgency))
    return 1 if (s >= Decimal("0.8") and u >= Decimal("0.8")) or s >= Decimal("0.95") \
        or u >= Decimal("0.95") else 0


def validate_dataset(dataset, config, identifiers, identity) -> dict:
    scenarios = dataset["scenarios"]
    emergencies = [e for s in scenarios for e in s["emergencies"]]
    checks = {}

    expected_counts = {level: spec["scenario_count"]
                       for level, spec in config["scenario_design"]["scarcity_levels"].items()}
    per_cell = Counter((s["scarcity_level"], s["size_class"], s["su_profile"]) for s in scenarios)
    expected_cells = {(level, size, profile): count // 15
                      for level, count in expected_counts.items()
                      for size in config["scenario_design"]["scenario_sizes"]
                      for profile in config["scenario_design"]["su_profiles"]}

    checks["scenario_count"] = {
        "passed": len(scenarios) == config["n_scenarios"] == dataset["n_scenarios"]
        and (not OFFICIAL or len(scenarios) == OFFICIAL_SCENARIO_COUNT),
        "value": len(scenarios)}

    required_scenario = {"scenario_id", "scenario_seed", "scarcity_level", "resource_inventory",
                         "emergencies", "n_emergencies", "n_warehouses"}
    required_emergency = {"emergency_id", "severity", "urgency", "arrival_timestamp",
                          "resource_requirements", "ground_truth_critical", "gt_rule_inputs"}
    schema_errors = sum(
        not required_scenario <= set(s) or len(s["emergencies"]) != s["n_emergencies"]
        or len(s["resource_inventory"]) != s["n_warehouses"]
        or any(not required_emergency <= set(e)
               or set(e["resource_requirements"]) != set(config["resource_types"])
               or any(not isinstance(v, int) or v < 0 for v in e["resource_requirements"].values())
               or sum(e["resource_requirements"].values()) == 0
               for e in s["emergencies"])
        or any(any(w["inventory"][r]["available"] < 0 for r in config["resource_types"])
               for w in s["resource_inventory"])
        for s in scenarios)
    checks["schema"] = {"passed": schema_errors == 0, "invalid_scenarios": schema_errors}

    checks["scarcity_cells"] = {
        "passed": dict(Counter(s["scarcity_level"] for s in scenarios)) == expected_counts
        and dict(per_cell) == expected_cells,
        "scarcity_counts": dict(Counter(s["scarcity_level"] for s in scenarios)),
        "per_cell": sorted({v for v in per_cell.values()})}

    ids = [s["scenario_id"] for s in scenarios]
    emergency_ids = [e["emergency_id"] for e in emergencies]
    fingerprints = [content_fingerprint(s) for s in scenarios]
    checks["uniqueness"] = {
        "passed": len(set(ids)) == len(ids) and len(set(emergency_ids)) == len(emergency_ids)
        and len(set(fingerprints)) == len(fingerprints)
        and all(i.startswith(identifiers["scenario_prefix"] + "-") for i in ids),
        "unique_ids": len(set(ids)), "unique_content": len(set(fingerprints))}

    seeds_ok = all(
        s["scenario_seed"] == derive_seed(config["seed_namespace"], config["master_seed"],
                                          "scenario", int(s["scenario_id"].split("-")[1]))
        for s in scenarios)
    checks["seeds"] = {
        "passed": seeds_ok and config["master_seed"] not in config["excluded_seeds"].values()
        and config["seed_namespace"] not in config["excluded_namespaces"],
        "master_seed": config["master_seed"], "namespace": config["seed_namespace"]}

    label_errors = sum(e["ground_truth_critical"] != exact_critical(e["severity"], e["urgency"])
                       for e in emergencies)
    su_range = all(0 < e["severity"] <= 1 and 0 < e["urgency"] <= 1 for e in emergencies)
    checks["gt_labels"] = {
        "passed": label_errors == 0 and su_range
        and all(s["n_ground_truth_critical"] >= 1 for s in scenarios),
        "label_mismatches": label_errors,
        "scenarios_without_critical": sum(s["n_ground_truth_critical"] == 0 for s in scenarios),
        "rule": config["ground_truth"]["rule"]}

    positions, severity, urgency, critical = [], [], [], []
    for s in scenarios:
        order = sorted(s["emergencies"], key=lambda e: (e["arrival_timestamp"], e["emergency_id"]))
        for p, e in enumerate(order):
            positions.append(p / (len(order) - 1))
            severity.append(e["severity"])
            urgency.append(e["urgency"])
            critical.append(e["ground_truth_critical"])
    correlations = {
        "fcfs_position_vs_severity": statistics.correlation(positions, severity),
        "fcfs_position_vs_urgency": statistics.correlation(positions, urgency),
        "fcfs_position_vs_gt_critical": statistics.correlation(positions, critical),
    }

    def values(ds, fields):
        return [tuple(e[f] for f in fields) for s in ds["scenarios"] for e in s["emergencies"]]

    def without_arrival(ds):
        clone = copy.deepcopy(ds["scenarios"])
        for s in clone:
            for e in s["emergencies"]:
                e.pop("arrival_offset_seconds")
                e.pop("arrival_timestamp")
        return clone

    arrival_perturbed = generate_dataset(config, identifiers, identity,
                                         arrival_salt="arrival::validation")
    su_perturbed = generate_dataset(config, identifiers, identity,
                                    su_salt="severity_urgency::validation")
    checks["arrival_independence"] = {
        "passed": all(abs(r) < CORRELATION_LIMIT for r in correlations.values())
        and without_arrival(arrival_perturbed) == without_arrival(dataset)
        and values(su_perturbed, ["arrival_offset_seconds"]) == values(dataset, ["arrival_offset_seconds"]),
        "pearson": correlations, "limit_abs": CORRELATION_LIMIT}

    checks["s_u_independence"] = {
        "passed": True, "informational": True,
        "pearson_severity_vs_urgency": statistics.correlation(severity, urgency)}

    development = read_json(DEVELOPMENT_DATASET_PATH)["scenarios"]
    pilot = read_json(PILOT_DATASET_PATH)["scenarios"]
    overlap_dev = set(fingerprints) & {content_fingerprint(s) for s in development}
    overlap_pilot = set(fingerprints) & {content_fingerprint(s) for s in pilot}
    checks["no_overlap_with_development_or_pilot"] = {
        "passed": not overlap_dev and not overlap_pilot,
        "identical_to_development": len(overlap_dev), "identical_to_pilot": len(overlap_pilot)}

    checks["distribution"] = {
        "passed": True, "informational": True,
        "emergencies_total": len(emergencies),
        "emergencies_per_scenario": {"min": min(s["n_emergencies"] for s in scenarios),
                                     "mean": len(emergencies) / len(scenarios),
                                     "max": max(s["n_emergencies"] for s in scenarios)},
        "size_classes": dict(Counter(s["size_class"] for s in scenarios)),
        "su_profiles": dict(Counter(s["su_profile"] for s in scenarios)),
        "gt_critical_emergencies": sum(critical),
        "scenarios_needing_su_redraw": sum(s["su_generation_attempts"] > 1 for s in scenarios),
    }

    return checks


def main() -> None:
    config = load_config()

    if not PREFLIGHT_PATH.exists() or not read_json(PREFLIGHT_PATH)["passed"]:
        sys.exit("STOP: run preflight.py first.")
    if DATASET_PATH.exists():
        sys.exit(f"STOP: {DATASET_PATH} already exists; the final dataset is generated once.")

    equivalence = prove_generator_equivalence()
    write_text(GENERATOR_EQUIVALENCE_PATH, json_text(equivalence))
    print(f"Generator equivalence (development reproduced byte for byte): "
          f"{equivalence['byte_identical']}", flush=True)
    if not equivalence["byte_identical"]:
        sys.exit("STOP: the copied generator does not reproduce the development dataset.")

    identifiers = {k: config["identifiers"][k]
                   for k in ("scenario_prefix", "index_digits", "warehouse_name")}
    dataset = generate_dataset(config, identifiers, FINAL_IDENTITY)
    print(f"Generated {len(dataset['scenarios'])} scenarios; validating ...", flush=True)

    checks = validate_dataset(dataset, config, identifiers, FINAL_IDENTITY)
    failed = [name for name, check in checks.items() if not check["passed"]]
    for name, check in checks.items():
        print(f"  [{'PASS' if check['passed'] else 'FAIL'}] {name}")
    if failed:
        write_text(FREEZE_PATH, json_text({"frozen": False, "failed_checks": failed, "checks": checks}))
        sys.exit(f"STOP: dataset validation failed ({failed}); nothing frozen.")

    text = dataset_text(dataset)
    write_text(DATASET_PATH, text)
    digest = hashlib.sha256(DATASET_PATH.read_bytes()).hexdigest()

    # Freeze: record the hash, then make the file read-only.
    os.chmod(DATASET_PATH, stat.S_IREAD | stat.S_IRGRP | stat.S_IROTH)

    write_text(FREEZE_PATH, json_text({
        "frozen": True,
        "dataset_file": DATASET_PATH.name,
        "sha256": digest,
        "bytes": DATASET_PATH.stat().st_size,
        "n_scenarios": len(dataset["scenarios"]),
        "master_seed": config["master_seed"],
        "seed_namespace": config["seed_namespace"],
        "generation_config_sha256": dataset["generation_config_sha256"],
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "read_only": not os.access(DATASET_PATH, os.W_OK),
        "pre_freeze_checks": checks,
        "statement": "Frozen before any allocation method was run. Not modified afterwards.",
    }))
    print(f"FROZEN {DATASET_PATH.name}  sha256 {digest}")


if __name__ == "__main__":
    main()
