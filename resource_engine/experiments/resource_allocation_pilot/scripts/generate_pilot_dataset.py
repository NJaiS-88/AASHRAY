"""Generate the 500-scenario resource allocation PILOT dataset.

Usage (from the repository root):

    python experiments/resource_allocation_pilot/scripts/generate_pilot_dataset.py

Design summary (full details in the README and config/pilot_config.json):

* Every scenario is one complete allocation environment: a warehouse
  inventory in the existing ``Warehouse`` schema and a list of emergencies
  whose demands use the existing ``ResourceRequirement`` resource types.
* Scenarios are stratified: scarcity level x size class x S-U profile.
* Each scenario owns independent random streams (structure, severity/urgency,
  arrival, demand, inventory, location), all derived from the master seed.
  Arrival times come from their own stream, so they cannot depend on S, U,
  P_GT or demand.
* P_GT = 0.5*S + 0.5*U and ground_truth_critical = P_GT > 0.8 are fixed
  reference labels written into every emergency record.
"""

import hashlib
import json
import math
import random
from collections import Counter
from datetime import datetime, timedelta

from pilot_common import (
    DATASET_PATH,
    PILOT_SCENARIO_COUNT,
    REPO_ROOT,
    derive_seed,
    dump_json,
    ground_truth_critical,
    ground_truth_score,
    json_text,
    load_config,
)


# Config sections that determine the generated data. The AASHRAY parameters
# and order conditions are deliberately excluded: the dataset must not depend
# on them.
GENERATION_CONFIG_KEYS = [
    "master_seed",
    "n_scenarios",
    "resource_types",
    "scenario_design",
    "severity_urgency",
    "demand",
    "arrival",
    "ground_truth",
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
    sizes = list(design["scenario_sizes"])
    profiles = design["su_profiles"]

    # LARGE first so any remainder goes to the most contested size class.
    combos = [
        (size, profile)
        for size in reversed(sizes)
        for profile in profiles
    ]

    cells = []

    for scarcity, spec in design["scarcity_levels"].items():
        base, extra = divmod(spec["scenario_count"], len(combos))

        for position, (size, profile) in enumerate(combos):
            count = base + (1 if position < extra else 0)

            cells.extend(
                {
                    "scarcity_level": scarcity,
                    "size_class": size,
                    "su_profile": profile,
                }
                for _ in range(count)
            )

    # Shuffle so scenario ids are not grouped by stratum.
    random.Random(
        derive_seed(config["master_seed"], "scenario_order")
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


def generate_emergencies(
    config: dict,
    scenario_id: str,
    scenario_seed: int,
    n_emergencies: int,
    su_profile: str,
    per_person_rates: dict[str, float],
    arrival_salt: str,
    su_salt: str,
) -> list[dict]:

    su_config = config["severity_urgency"]
    bands = su_config["bands"]
    strata = su_config["emergency_strata"]
    profile_weights = su_config["profile_weights"][su_profile]
    decimals = su_config["decimals"]

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
    stratum_names = list(profile_weights)
    stratum_weights = [profile_weights[name] for name in stratum_names]

    # Independent streams. Changing one never shifts another.
    su_rng = random.Random(derive_seed(scenario_seed, su_salt))
    arrival_rng = random.Random(derive_seed(scenario_seed, arrival_salt))
    demand_rng = random.Random(derive_seed(scenario_seed, "demand"))

    emergencies = []

    for index in range(n_emergencies):

        # Severity / urgency: stratum first, then two independent draws.
        stratum = su_rng.choices(stratum_names, weights=stratum_weights)[0]
        severity_band, urgency_band = strata[stratum]

        severity = round(su_rng.uniform(*bands[severity_band]), decimals)
        urgency = round(su_rng.uniform(*bands[urgency_band]), decimals)

        # Arrival: dedicated stream, sees nothing else.
        offset = arrival_rng.randint(0, arrival_config["window_seconds"])

        # Demand: dedicated stream, independent of S, U and arrival.
        affected_population = demand_rng.randrange(
            population["min"],
            population["max"] + 1,
            population["step"],
        )
        pattern = demand_rng.choices(
            pattern_names,
            weights=pattern_weights,
        )[0]
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

        reference_score = ground_truth_score(severity, urgency)

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
                "ground_truth_reference_score": reference_score,
                "ground_truth_critical": ground_truth_critical(
                    reference_score
                ),
            }
        )

    return emergencies


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
    resource_types = config["resource_types"]

    inventory_rng = random.Random(derive_seed(scenario_seed, "inventory"))
    location_rng = random.Random(derive_seed(scenario_seed, "location"))

    total_supply = {}
    design_ratio = {}
    shares_by_type = {}

    for resource in resource_types:
        ratio = inventory_rng.uniform(ratio_low, ratio_high)
        design_ratio[resource] = round(ratio, 6)

        demand = total_demand[resource]

        # No emergency needs this type -> no stock for it either.
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

        for resource in resource_types:
            available = shares_by_type[resource][index]
            capacity = available + inventory_rng.randint(0, available)

            inventory[resource] = {
                "available": available,
                "capacity": capacity,
            }

        warehouses.append(
            {
                "warehouse_id": f"{scenario_id}-WH{index + 1}",
                "name": f"Pilot Warehouse {index + 1}",
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
    arrival_salt: str = "arrival",
    su_salt: str = "severity_urgency",
) -> dict:

    master_seed = config["master_seed"]
    scenario_id = f"PILOT-{index:04d}"
    scenario_seed = derive_seed(master_seed, "scenario", index)

    design = config["scenario_design"]
    structure_rng = random.Random(derive_seed(scenario_seed, "structure"))

    size_low, size_high = design["scenario_sizes"][cell["size_class"]]
    n_emergencies = structure_rng.randint(size_low, size_high)

    warehouses_low, warehouses_high = design["warehouses_per_scenario"]
    n_warehouses = structure_rng.randint(warehouses_low, warehouses_high)

    emergencies = generate_emergencies(
        config=config,
        scenario_id=scenario_id,
        scenario_seed=scenario_seed,
        n_emergencies=n_emergencies,
        su_profile=cell["su_profile"],
        per_person_rates=per_person_rates,
        arrival_salt=arrival_salt,
        su_salt=su_salt,
    )

    resource_types = config["resource_types"]

    total_demand = {
        resource: sum(
            emergency["resource_requirements"][resource]
            for emergency in emergencies
        )
        for resource in resource_types
    }

    warehouses, total_supply, design_ratio = generate_inventory(
        config=config,
        scenario_id=scenario_id,
        scenario_seed=scenario_seed,
        n_warehouses=n_warehouses,
        scarcity_level=cell["scarcity_level"],
        total_demand=total_demand,
    )

    realized_ratio = {
        resource: (
            round(total_supply[resource] / total_demand[resource], 6)
            if total_demand[resource] > 0
            else None
        )
        for resource in resource_types
    }

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
            emergency["ground_truth_critical"] for emergency in emergencies
        ),
        "total_demand": total_demand,
        "total_supply": total_supply,
        "design_supply_to_demand_ratio": design_ratio,
        "realized_supply_to_demand_ratio": realized_ratio,
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
    # The salts exist only so the validator can perturb one random stream
    # and confirm the others are unaffected.

    if config["n_scenarios"] != PILOT_SCENARIO_COUNT:
        raise ValueError(
            f"The pilot generator only produces exactly "
            f"{PILOT_SCENARIO_COUNT} scenarios; config asks for "
            f"{config['n_scenarios']}."
        )

    cells = build_scenario_cells(config)

    if len(cells) != PILOT_SCENARIO_COUNT:
        raise ValueError(
            f"Scenario design yields {len(cells)} cells, "
            f"expected {PILOT_SCENARIO_COUNT}."
        )

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
        "dataset": "resource_allocation_pilot",
        "dataset_role": (
            "PILOT ONLY. Not a development (tuning) set and not the final "
            "test set."
        ),
        "master_seed": config["master_seed"],
        "n_scenarios": len(scenarios),
        "generator": (
            "experiments/resource_allocation_pilot/scripts/"
            "generate_pilot_dataset.py"
        ),
        "generation_config_sha256": generation_config_hash(config),
        "per_person_rates_used": per_person_rates,
        "scenarios": scenarios,
    }


def describe(dataset: dict) -> str:
    scenarios = dataset["scenarios"]
    emergencies = [
        emergency
        for scenario in scenarios
        for emergency in scenario["emergencies"]
    ]

    lines = [
        f"Scenarios           : {len(scenarios)}",
        f"Emergencies         : {len(emergencies)}",
        f"GT-critical         : "
        f"{sum(e['ground_truth_critical'] for e in emergencies)}",
        f"Scarcity            : "
        f"{dict(Counter(s['scarcity_level'] for s in scenarios))}",
        f"Size class          : "
        f"{dict(Counter(s['size_class'] for s in scenarios))}",
        f"S-U profile         : "
        f"{dict(Counter(s['su_profile'] for s in scenarios))}",
        f"Emergency S-U strata: "
        f"{dict(Counter(e['su_stratum'] for e in emergencies))}",
    ]

    return "\n".join(lines)


def main() -> None:
    config = load_config()
    dataset = generate_dataset(config)

    dump_json(dataset, DATASET_PATH)

    digest = hashlib.sha256(
        json_text(dataset).encode("utf-8")
    ).hexdigest()

    print(f"Wrote {DATASET_PATH}")
    print(f"Dataset sha256      : {digest}")
    print(describe(dataset))


if __name__ == "__main__":
    main()
