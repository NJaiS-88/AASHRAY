"""Analytical optimum: an independent correctness oracle for the MILP.

Resources are fungible, any warehouse can supply any emergency, and the
resource types are not coupled. So for each type r the most critical demand
that can be met is

    min(critical_demand_r, total_supply_r)

with critical_demand_r = sum_e GT_critical[e] * demand[e,r] and
total_supply_r = sum_w available[w,r]. The optimum is the sum over types.

This module reads the scenario directly and shares no code with
milp_model.py. It validates the MILP; it does not replace it.
"""

RESOURCE_TYPES = ("water", "food", "medical_kits")


def analytical_optimum(scenario: dict) -> dict:
    per_type = {}

    for resource in RESOURCE_TYPES:
        critical_demand = sum(
            e["resource_requirements"][resource]
            for e in scenario["emergencies"]
            if e["ground_truth_critical"] == 1
        )
        total_supply = sum(
            w["inventory"].get(resource, {"available": 0})["available"]
            for w in scenario["resource_inventory"]
        )
        per_type[resource] = {
            "critical_demand": critical_demand,
            "total_supply": total_supply,
            "max_critical_fulfilment": min(critical_demand, total_supply),
        }

    return {
        "per_type": per_type,
        "critical_required": sum(v["critical_demand"] for v in per_type.values()),
        "analytical_optimum": sum(v["max_critical_fulfilment"] for v in per_type.values()),
    }
