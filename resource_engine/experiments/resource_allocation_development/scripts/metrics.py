"""Development metrics, computed from the existing allocator's quantities.

CDC = fulfilled / required demand of GT-critical emergencies (primary)
TDC = total fulfilled / total required demand (descriptive only)

Demand is summed over water, food and medical_kits in native units, as in
the pilot. GT-critical membership comes only from the stored fixed label.
"""

import statistics


RESOURCE_TYPES = ("water", "food", "medical_kits")


def scenario_outcome(scenario: dict, records: list[dict]) -> dict:

    critical = {
        e["emergency_id"]: e["ground_truth_critical"] == 1
        for e in scenario["emergencies"]
    }

    total_required = 0.0
    total_fulfilled = 0.0
    total_shortage = 0.0
    critical_required = 0.0
    critical_fulfilled = 0.0

    for record in records:
        required = sum(record["required"].values())
        fulfilled = sum(record["allocated"].values())

        total_required += required
        total_fulfilled += fulfilled
        total_shortage += sum(record["shortage"].values())

        if critical[record["emergency_id"]]:
            critical_required += required
            critical_fulfilled += fulfilled

    return {
        "critical_required": critical_required,
        "critical_fulfilled": critical_fulfilled,
        "critical_unmet": critical_required - critical_fulfilled,
        "cdc": critical_fulfilled / critical_required,
        "total_required": total_required,
        "total_fulfilled": total_fulfilled,
        "total_unmet": total_required - total_fulfilled,
        "allocator_reported_shortage": total_shortage,
        "tdc": total_fulfilled / total_required,
    }


def percentile_cuts(values: list[float]) -> list[float]:
    # Linear interpolation between order statistics (numpy's default).
    return statistics.quantiles(values, n=100, method="inclusive")


def distribution(values: list[float]) -> dict:
    cuts = percentile_cuts(values)

    return {
        "mean": statistics.fmean(values),
        "median": statistics.median(values),
        "std": statistics.stdev(values),
        "p10": cuts[9],
        "p25": cuts[24],
        "p75": cuts[74],
        "p90": cuts[89],
        "min": min(values),
        "max": max(values),
    }


def paired(values: list[float], baseline: list[float], tolerance: float) -> dict:
    differences = [a - b for a, b in zip(values, baseline)]

    return {
        **distribution(differences),
        "n_higher": sum(d > tolerance for d in differences),
        "n_lower": sum(d < -tolerance for d in differences),
        "n_equal": sum(abs(d) <= tolerance for d in differences),
    }


def select_winner(rows: list[dict], tolerance: float) -> tuple[dict, dict]:
    """The predefined selection rule, applied mechanically.

    1. Highest mean CDC; every row within ``tolerance`` of the best mean is
       tied.
    2. Among those, highest median CDC (within ``tolerance`` = tied).
    3. Among those, highest 10th-percentile CDC (within ``tolerance``).
    4. Lexicographically smallest (alpha, k, m, n).
    """

    trace = {"candidates": len(rows)}
    tied = rows

    for step, metric in enumerate(("mean_cdc", "median_cdc", "p10_cdc"), start=1):
        best = max(row[metric] for row in tied)
        tied = [row for row in tied if row[metric] >= best - tolerance]
        trace[f"step_{step}_{metric}_best"] = best
        trace[f"step_{step}_{metric}_tied"] = len(tied)

    winner = min(tied, key=lambda row: (row["alpha"], row["k"], row["m"], row["n"]))
    trace["step_4_lexicographic_from"] = len(tied)

    return winner, trace


def rank_by_selection_rule(rows: list[dict], tolerance: float, count: int):
    # Apply the selection rule repeatedly: rank 1 is the winner, rank 2 the
    # winner of the remaining rows, and so on.
    remaining = list(rows)
    ranked = []

    while remaining and len(ranked) < count:
        winner, _ = select_winner(remaining, tolerance)
        ranked.append(winner)
        remaining = [row for row in remaining if row is not winner]

    return ranked
