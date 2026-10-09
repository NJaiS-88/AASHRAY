"""Allocation-order policies: FCFS, LINEAR and AASHRAY.

* FCFS receives only ``arrival_view``: (emergency_id, arrival_timestamp).
  It cannot read S, U, GT labels, demand or any AASHRAY parameter.
* LINEAR ranks by P_linear = 0.5*S + 0.5*U.
* AASHRAY ranks by P_o = k*S + m*U + n*P_n, with P_n = S^alpha * U^(1-alpha).

LINEAR and AASHRAY break score ties by FCFS order. No priority categories are
used anywhere.

Ties: scores within SCORE_TIE_TOLERANCE of each other are tied. Without
this, two mathematically equal scores (e.g. 0.1*0.9171 + 0.9*0.879 and
0.1*0.8325 + 0.9*0.8884, both 0.88281) can differ in the last floating-point
bit, so the order would follow rounding noise instead of FCFS. S and U have 4
decimals and the weights are tenths, so genuinely different scores differ by
far more than 1e-12; the tolerance only absorbs rounding error (~1e-16).

``normalized_priority`` and ``overall_priority`` are shared with
ranking_equivalence.py so both compute identical floating-point scores.
"""


SCORE_TIE_TOLERANCE = 1e-12


def arrival_view(emergencies: list[dict]) -> list[tuple[str, str]]:
    return [
        (emergency["emergency_id"], emergency["arrival_timestamp"])
        for emergency in emergencies
    ]


def fcfs_order(arrivals: list[tuple[str, str]]) -> list[str]:
    # Ascending (arrival_timestamp, emergency_id). ISO-8601 UTC timestamps
    # of a fixed format sort chronologically as strings.
    return [
        emergency_id
        for emergency_id, _ in sorted(arrivals, key=lambda a: (a[1], a[0]))
    ]


def order_by_scores(fcfs_ids: list[str], scores: dict[str, float]) -> list[str]:
    # Descending score; scores within SCORE_TIE_TOLERANCE form a tie group,
    # and each tie group is put in FCFS order.
    fcfs_rank = {emergency_id: rank for rank, emergency_id in enumerate(fcfs_ids)}
    ranked = sorted(fcfs_ids, key=lambda emergency_id: -scores[emergency_id])

    ordered = []
    group = [ranked[0]]

    for previous, current in zip(ranked, ranked[1:]):
        if scores[previous] - scores[current] <= SCORE_TIE_TOLERANCE:
            group.append(current)
        else:
            ordered.extend(sorted(group, key=fcfs_rank.__getitem__))
            group = [current]

    ordered.extend(sorted(group, key=fcfs_rank.__getitem__))

    return ordered


def linear_priority(severity: float, urgency: float) -> float:
    return 0.5 * severity + 0.5 * urgency


def normalized_priority(severity: float, urgency: float, alpha: float) -> float:
    # P_n = S^alpha * U^(1 - alpha)
    return severity ** alpha * urgency ** (1.0 - alpha)


def overall_priority(
    severity: float,
    urgency: float,
    k: float,
    m: float,
    n: float,
    p_n: float,
) -> float:
    # P_o = k*S + m*U + n*P_n
    return k * severity + m * urgency + n * p_n


def linear_order(emergencies: list[dict]) -> list[str]:
    fcfs = fcfs_order(arrival_view(emergencies))

    scores = {
        e["emergency_id"]: linear_priority(e["severity"], e["urgency"])
        for e in emergencies
    }

    return order_by_scores(fcfs, scores)


def aashray_order(emergencies: list[dict], parameters: dict) -> list[str]:
    fcfs = fcfs_order(arrival_view(emergencies))

    scores = {
        e["emergency_id"]: overall_priority(
            e["severity"],
            e["urgency"],
            parameters["k"],
            parameters["m"],
            parameters["n"],
            normalized_priority(e["severity"], e["urgency"], parameters["alpha"]),
        )
        for e in emergencies
    }

    return order_by_scores(fcfs, scores)
