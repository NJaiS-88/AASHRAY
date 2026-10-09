"""Pilot metrics computed from the existing allocator's actual quantities.

TDC = total fulfilled demand / total required demand
CDC = fulfilled demand of GT-critical emergencies
      / required demand of GT-critical emergencies

"Demand" is summed over the existing resource types (water, food,
medical_kits) in their native units, exactly as specified. CDC membership
comes ONLY from the fixed ``ground_truth_critical`` label stored in the
dataset (P_GT = 0.5*S + 0.5*U > 0.8), never from an AASHRAY score.

CDC is undefined (None) for a scenario with no GT-critical demand.

Resource utilization is not reported by the existing allocator. It is
derived here from the allocator's own output as
total fulfilled / total available stock.
"""

import statistics


RESOURCE_TYPES = ("water", "food", "medical_kits")


def scenario_metrics(scenario: dict, allocation_records: list[dict]) -> dict:

    critical = {
        emergency["emergency_id"]: emergency["ground_truth_critical"] == 1
        for emergency in scenario["emergencies"]
    }

    required_by_type = {resource: 0.0 for resource in RESOURCE_TYPES}
    fulfilled_by_type = {resource: 0.0 for resource in RESOURCE_TYPES}

    critical_required = 0.0
    critical_fulfilled = 0.0
    total_unmet_reported = 0.0

    n_fully_fulfilled = 0
    n_critical_fully_fulfilled = 0

    for record in allocation_records:

        required = sum(record["required"].values())
        fulfilled = sum(record["allocated"].values())

        for resource in RESOURCE_TYPES:
            required_by_type[resource] += record["required"][resource]
            fulfilled_by_type[resource] += record["allocated"][resource]

        total_unmet_reported += sum(record["shortage"].values())

        is_fully_fulfilled = record["allocation_status"] == "FULLY_FULFILLED"
        n_fully_fulfilled += is_fully_fulfilled

        if critical[record["emergency_id"]]:
            critical_required += required
            critical_fulfilled += fulfilled
            n_critical_fully_fulfilled += is_fully_fulfilled

    total_required = sum(required_by_type.values())
    total_fulfilled = sum(fulfilled_by_type.values())

    available_by_type = {
        resource: float(scenario["total_supply"][resource])
        for resource in RESOURCE_TYPES
    }
    total_available = sum(available_by_type.values())

    # Diagnostic: does each resource type end at min(supply, demand)?
    saturated = all(
        fulfilled_by_type[resource]
        == min(available_by_type[resource], required_by_type[resource])
        for resource in RESOURCE_TYPES
    )

    metrics = {
        "total_required": total_required,
        "total_fulfilled": total_fulfilled,
        "total_unmet": total_required - total_fulfilled,
        "total_unmet_reported_by_allocator": total_unmet_reported,
        "tdc": total_fulfilled / total_required,
        "critical_required": critical_required,
        "critical_fulfilled": critical_fulfilled,
        "critical_unmet": critical_required - critical_fulfilled,
        "cdc": (
            critical_fulfilled / critical_required
            if critical_required > 0
            else None
        ),
        "total_available": total_available,
        "resource_utilization": (
            total_fulfilled / total_available if total_available > 0 else None
        ),
        "n_emergencies_fully_fulfilled": n_fully_fulfilled,
        "n_critical_fully_fulfilled": n_critical_fully_fulfilled,
        "per_type_fulfilled_equals_min_supply_demand": saturated,
    }

    for resource in RESOURCE_TYPES:
        metrics[f"{resource}_required"] = required_by_type[resource]
        metrics[f"{resource}_fulfilled"] = fulfilled_by_type[resource]
        metrics[f"{resource}_available"] = available_by_type[resource]

    return metrics


def spread(values: list[float], tolerance: float) -> dict:
    # Range and population standard deviation across order conditions.
    if not values:
        return {"range": None, "std": None, "changes": None}

    value_range = max(values) - min(values)

    return {
        "range": value_range,
        "std": statistics.pstdev(values) if len(values) > 1 else 0.0,
        "changes": value_range > tolerance,
    }


def mean(values: list[float]):
    return statistics.fmean(values) if values else None


def summarize_condition(rows: list[dict]) -> dict:
    # Aggregate one order condition over a group of scenarios.
    tdc_values = [row["tdc"] for row in rows]
    cdc_values = [row["cdc"] for row in rows if row["cdc"] is not None]
    utilization = [
        row["resource_utilization"]
        for row in rows
        if row["resource_utilization"] is not None
    ]

    total_required = sum(row["total_required"] for row in rows)
    total_fulfilled = sum(row["total_fulfilled"] for row in rows)
    critical_required = sum(row["critical_required"] for row in rows)
    critical_fulfilled = sum(row["critical_fulfilled"] for row in rows)

    return {
        "n_scenarios": len(rows),
        "tdc_mean": mean(tdc_values),
        "tdc_min": min(tdc_values) if tdc_values else None,
        "tdc_max": max(tdc_values) if tdc_values else None,
        "tdc_pooled": (
            total_fulfilled / total_required if total_required else None
        ),
        "cdc_mean_over_defined": mean(cdc_values),
        "cdc_min": min(cdc_values) if cdc_values else None,
        "cdc_max": max(cdc_values) if cdc_values else None,
        "n_scenarios_cdc_defined": len(cdc_values),
        "n_scenarios_cdc_undefined_no_critical_demand": (
            len(rows) - len(cdc_values)
        ),
        "cdc_pooled": (
            critical_fulfilled / critical_required
            if critical_required
            else None
        ),
        "total_required": total_required,
        "total_fulfilled": total_fulfilled,
        "total_unmet": total_required - total_fulfilled,
        "critical_required": critical_required,
        "critical_fulfilled": critical_fulfilled,
        "critical_unmet": critical_required - critical_fulfilled,
        "resource_utilization_mean": mean(utilization),
        "n_scenarios_per_type_fulfilled_equals_min_supply_demand": sum(
            row["per_type_fulfilled_equals_min_supply_demand"] for row in rows
        ),
    }


def summarize_sensitivity(rows: list[dict], prefix: str) -> dict:
    # Aggregate per-scenario order sensitivity of TDC or CDC.
    defined = [row for row in rows if row[f"{prefix}_range"] is not None]
    ranges = [row[f"{prefix}_range"] for row in defined]
    stds = [row[f"{prefix}_std"] for row in defined]
    changed = sum(row[f"{prefix}_changes_with_order"] for row in defined)

    return {
        "n_scenarios_evaluated": len(defined),
        "n_scenarios_changed_with_order": changed,
        "n_scenarios_invariant_across_orders": len(defined) - changed,
        "pct_scenarios_changed_with_order": (
            100.0 * changed / len(defined) if defined else None
        ),
        "range_mean": mean(ranges),
        "range_max": max(ranges) if ranges else None,
        "std_mean": mean(stds),
        "std_max": max(stds) if stds else None,
    }
