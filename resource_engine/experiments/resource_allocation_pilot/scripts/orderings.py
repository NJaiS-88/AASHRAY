"""Allocation-order conditions.

Every order function receives only the information it is allowed to see:

* FCFS / REVERSE_FCFS : ``arrival_view`` -> (emergency_id, arrival_offset_seconds)
* RANDOM_*            : emergency ids and a seed
* AASHRAY             : severity, urgency and the AASHRAY parameters

FCFS therefore cannot read severity, urgency, any priority score,
ground-truth labels or demand: those fields are not in its input.

FCFS tie-breaking rule: ascending (arrival_offset_seconds, emergency_id).
"""

import random


def arrival_view(emergencies: list[dict]) -> list[tuple[str, int]]:
    return [
        (emergency["emergency_id"], emergency["arrival_offset_seconds"])
        for emergency in emergencies
    ]


def fcfs_order(arrivals: list[tuple[str, int]]) -> list[str]:
    return [
        emergency_id
        for emergency_id, _ in sorted(
            arrivals,
            key=lambda arrival: (arrival[1], arrival[0]),
        )
    ]


def reverse_fcfs_order(arrivals: list[tuple[str, int]]) -> list[str]:
    return list(reversed(fcfs_order(arrivals)))


def random_order(emergency_ids: list[str], seed: int) -> list[str]:
    # Sorted first so the result depends only on the id set and the seed.
    ordered = sorted(emergency_ids)
    random.Random(seed).shuffle(ordered)
    return ordered


def aashray_parameters_status(parameters: dict) -> tuple[bool, str]:
    names = ("alpha", "k", "m", "n")

    if any(parameters.get(name) is None for name in names):
        return False, (
            "AASHRAY parameters (alpha, k, m, n) are not provided in "
            "config/pilot_config.json -> aashray_parameters. A provisional "
            "pilot configuration is required before the AASHRAY condition "
            "can run."
        )

    alpha = parameters["alpha"]
    k, m, n = parameters["k"], parameters["m"], parameters["n"]

    if not 0.0 <= alpha <= 1.0:
        return False, f"alpha={alpha} is outside [0, 1]."

    if min(k, m, n) < 0:
        return False, f"k, m, n must be >= 0 (got {k}, {m}, {n})."

    if abs(k + m + n - 1.0) > 1e-9:
        return False, f"k + m + n must equal 1 (got {k + m + n})."

    return True, "OK"


def normalized_priority(severity: float, urgency: float, alpha: float) -> float:
    # P_n = S^alpha * U^(1 - alpha)
    return severity ** alpha * urgency ** (1.0 - alpha)


def overall_priority(
    severity: float,
    urgency: float,
    parameters: dict,
) -> float:
    # P_o = k*S + m*U + n*P_n
    p_n = normalized_priority(severity, urgency, parameters["alpha"])

    return (
        parameters["k"] * severity
        + parameters["m"] * urgency
        + parameters["n"] * p_n
    )


def aashray_order(emergencies: list[dict], parameters: dict) -> list[str]:
    # Descending P_o. Exact ties fall back to FCFS order.
    fcfs_rank = {
        emergency_id: rank
        for rank, emergency_id in enumerate(
            fcfs_order(arrival_view(emergencies))
        )
    }

    scores = {
        emergency["emergency_id"]: overall_priority(
            emergency["severity"],
            emergency["urgency"],
            parameters,
        )
        for emergency in emergencies
    }

    return sorted(
        scores,
        key=lambda emergency_id: (
            -scores[emergency_id],
            fcfs_rank[emergency_id],
        ),
    )
