"""Generate the 3,000-scenario DEVELOPMENT dataset.

Usage (from the repository root):

    python experiments/resource_allocation_development/scripts/generate_development_dataset.py

The design follows the validated pilot generator (same strata, scarcity
bands, demand rules, arrival rule and independent random streams), with:

* the new fixed GT rule:
      critical = (S >= 0.8 and U >= 0.8) or S >= 0.95 or U >= 0.95
* a guarantee that every scenario has at least one GT-critical emergency,
  obtained by rejection sampling of the severity/urgency stream only;
* a new master seed and seed namespace.
"""

import hashlib
import json
import math
import random
from collections import Counter
from datetime import datetime, timedelta

from dev_common import (
    DATASET_PATH,
    DEVELOPMENT_SCENARIO_COUNT,
    REPO_ROOT,
    derive_seed,
    gt_clauses,
    ground_truth_critical,
    load_config,
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

PER_PERSON_RATES_PATH = (
    REPO_ROOT / "resource_services" / "config" / "resource_rules.json"
)


def generation_config_hash(config: dict) -> str:
    subset = {key: config[key] for key in GENERATION_CONFIG_KEYS}
    text = json.dumps(subset, sort_keys=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_per_person_rates(resource_types: list[str]) -> dict[str, float]:
    # Read-only reuse of the existing application's demand rates.
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

    # Shuffle so scenario ids are not grouped by stratum.
    random.Random(
        derive_seed(
            config["seed_namespace"],
            config["master_seed"],
            "scenario_order",
        )
    ).shuffle(cells)

    return cells


def integer_split(total: int, weights: list[float]) -> list[int]:
    # Largest-remainder split of an integer total. Ties resolved by index.
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


def draw_severity_urgency(
    config: dict,
    scenario_seed: int,
    n_emergencies: int,
    su_profile: str,
    su_salt: str,
) -> tuple[list[tuple[str, float, float]], int]:
    # Rejection sampling: repeat the whole S/U draw with a new deterministic
    # stream until at least one emergency is GT-critical under the fixed
    # rule. Only the GT rule is consulted.

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

    raise RuntimeError(
        f"No GT-critical emergency after {max_attempts} attempts."
    )


def generate_emergencies(
    config: dict,
    scenario_id: str,
    scenario_seed: int,
    n_emergencies: int,
    su_profile: str,
    per_person_rates: dict[str, float],
    arrival_salt: str,
    su_salt: str,
) -> tuple[list[dict], int]:

    demand_config = config["demand"]
    population = demand_config["affected_population"]
    multiplier_low, multiplier_high = demand_config["type_multiplier"]
    patterns = demand_config["required_type_patterns"]
    pattern_names = list(patterns)
    pattern_weights = [patterns[name]["weight"] for name in pattern_names]

    arrival_config = config["arrival"]
    base_time = datetime.strptime(
        arrival_config["base_timestamp"],
        "%Y-%m-%dT%H:%M:%SZ",
    )

    resource_types = config["resource_types"]

    su_draws, su_attempts = draw_severity_urgency(
        config,
        scenario_seed,
        n_emergencies,
        su_profile,
        su_salt,
    )

    # Independent streams: changing one never shifts another.
    arrival_rng = random.Random(derive_seed(scenario_seed, arrival_salt))
    demand_rng = random.Random(derive_seed(scenario_seed, "demand"))

    emergencies = []

    for index, (stratum, severity, urgency) in enumerate(su_draws):

        offset = arrival_rng.randint(0, arrival_config["window_seconds"])

        affected_population = demand_rng.randrange(
            population["min"],
            population["max"] + 1,
            population["step"],
        )
        pattern = demand_rng.choices(pattern_names, weights=pattern_weights)[0]
        required_types = set(patterns[pattern]["types"])

        requirements = {}

        for resource in resource_types:
            # Always draw, so the stream stays aligned across patterns.
            multiplier = demand_rng.uniform(multiplier_low, multiplier_high)

            if resource in required_types:
                requirements[resource] = max(
                    1,
                    int(
                        round(
                            per_person_rates[resource]
                            * affected_population
                            * multiplier
                        )
                    ),
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
                "ground_truth_critical": ground_truth_critical(
                    severity, urgency
                ),
            }
        )

    return emergencies, su_attempts


def generate_inventory(
    config: dict,
    scenario_id: str,
    scenario_seed: int,
    n_warehouses: int,
    scarcity_level: str,
    total_demand: dict[str, int],
) -> tuple[list[dict], dict[str, int], dict[str, float]]:

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
            round_supply(ratio * demand, scarcity["supply_rounding"])
            if demand > 0
            else 0
        )
        total_supply[resource] = supply

        weights = [
            inventory_rng.uniform(0.2, 1.0) for _ in range(n_warehouses)
        ]
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
                "name": f"Development Warehouse {index + 1}",
                "location": {
                    "latitude": round(location_rng.uniform(18.90, 19.30), 4),
                    "longitude": round(location_rng.uniform(72.80, 73.10), 4),
                },
                "inventory": inventory,
                # The existing allocator does not use vehicles.
                "vehicles": {},
            }
        )

    return warehouses, total_supply, design_ratio


def generate_scenario(
    config: dict,
    index: int,
    cell: dict,
    per_person_rates: dict[str, float],
    arrival_salt: str,
    su_salt: str,
) -> dict:

    master_seed = config["master_seed"]
    scenario_id = f"DEV-{index:04d}"
    scenario_seed = derive_seed(
        config["seed_namespace"],
        master_seed,
        "scenario",
        index,
    )

    design = config["scenario_design"]
    structure_rng = random.Random(derive_seed(scenario_seed, "structure"))

    size_low, size_high = design["scenario_sizes"][cell["size_class"]]
    n_emergencies = structure_rng.randint(size_low, size_high)

    warehouses_low, warehouses_high = design["warehouses_per_scenario"]
    n_warehouses = structure_rng.randint(warehouses_low, warehouses_high)

    emergencies, su_attempts = generate_emergencies(
        config=config,
        scenario_id=scenario_id,
        scenario_seed=scenario_seed,
        n_emergencies=n_emergencies,
        su_profile=cell["su_profile"],
        per_person_rates=per_person_rates,
        arrival_salt=arrival_salt,
        su_salt=su_salt,
    )

    total_demand = {
        resource: sum(e["resource_requirements"][resource] for e in emergencies)
        for resource in config["resource_types"]
    }

    warehouses, total_supply, design_ratio = generate_inventory(
        config=config,
        scenario_id=scenario_id,
        scenario_seed=scenario_seed,
        n_warehouses=n_warehouses,
        scarcity_level=cell["scarcity_level"],
        total_demand=total_demand,
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
        "n_ground_truth_critical": sum(
            e["ground_truth_critical"] for e in emergencies
        ),
        "su_generation_attempts": su_attempts,
        "total_demand": total_demand,
        "total_supply": total_supply,
        "design_supply_to_demand_ratio": design_ratio,
        "overall_supply_to_demand_ratio": round(
            sum(total_supply.values()) / sum(total_demand.values()),
            6,
        ),
        "resource_inventory": warehouses,
        "emergencies": emergencies,
    }


def generate_dataset(
    config: dict,
    arrival_salt: str = "arrival",
    su_salt: str = "severity_urgency",
) -> dict:
    # The salts exist only so the validator can perturb one stream and
    # confirm the others are unaffected.

    if config["n_scenarios"] != DEVELOPMENT_SCENARIO_COUNT:
        raise ValueError(
            f"The development generator only produces exactly "
            f"{DEVELOPMENT_SCENARIO_COUNT} scenarios; config asks for "
            f"{config['n_scenarios']}."
        )

    if config["master_seed"] == config["pilot_master_seed"]:
        raise ValueError("Development master seed must differ from the pilot.")

    cells = build_scenario_cells(config)

    if len(cells) != DEVELOPMENT_SCENARIO_COUNT:
        raise ValueError(f"Scenario design yields {len(cells)} cells.")

    per_person_rates = load_per_person_rates(config["resource_types"])

    scenarios = [
        generate_scenario(
            config=config,
            index=index,
            cell=cell,
            per_person_rates=per_person_rates,
            arrival_salt=arrival_salt,
            su_salt=su_salt,
        )
        for index, cell in enumerate(cells, start=1)
    ]

    return {
        "dataset": "resource_allocation_development",
        "dataset_role": (
            "DEVELOPMENT / parameter selection only. Not the pilot and not "
            "the final test set."
        ),
        "master_seed": config["master_seed"],
        "seed_namespace": config["seed_namespace"],
        "n_scenarios": len(scenarios),
        "ground_truth_rule": config["ground_truth"]["rule"],
        "generator": (
            "experiments/resource_allocation_development/scripts/"
            "generate_development_dataset.py"
        ),
        "generation_config_sha256": generation_config_hash(config),
        "per_person_rates_used": per_person_rates,
        "scenarios": scenarios,
    }


def dataset_text(dataset: dict) -> str:
    # Metadata pretty-printed, then one compact scenario per line. Valid JSON,
    # deterministic, and about a third of the size of fully indented JSON.
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


def describe(dataset: dict) -> str:
    scenarios = dataset["scenarios"]
    emergencies = [e for s in scenarios for e in s["emergencies"]]
    sizes = [s["n_emergencies"] for s in scenarios]

    return "\n".join(
        [
            f"Scenarios          : {len(scenarios)}",
            f"Scarcity           : {dict(Counter(s['scarcity_level'] for s in scenarios))}",
            f"Size class         : {dict(Counter(s['size_class'] for s in scenarios))}",
            f"Emergencies        : {len(emergencies)} (min {min(sizes)}, "
            f"mean {len(emergencies) / len(scenarios):.2f}, max {max(sizes)})",
            f"GT-critical        : {sum(e['ground_truth_critical'] for e in emergencies)}",
            f"Scenarios >=1 crit : "
            f"{sum(s['n_ground_truth_critical'] >= 1 for s in scenarios)}",
            f"S/U redraws needed : "
            f"{sum(s['su_generation_attempts'] > 1 for s in scenarios)} scenarios",
        ]
    )


def main() -> None:
    config = load_config()
    dataset = generate_dataset(config)
    text = dataset_text(dataset)

    write_text(DATASET_PATH, text)

    print(f"Wrote {DATASET_PATH}")
    print(f"Dataset sha256     : {hashlib.sha256(text.encode('utf-8')).hexdigest()}")
    print(describe(dataset))


if __name__ == "__main__":
    main()
