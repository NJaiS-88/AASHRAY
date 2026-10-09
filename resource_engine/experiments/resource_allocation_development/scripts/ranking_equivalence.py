"""Empirical ranking-equivalence classes over the development dataset.

Only the induced emergency order affects allocation. For every candidate
configuration and every scenario, the full ordered emergency-id sequence is
computed (descending P_o, ties in FCFS order). A configuration's signature
is its sequence in ALL scenarios. Configurations with identical signatures
form one empirical ranking-equivalence class; they produce identical
allocations and therefore identical metrics.

Scores are computed with the same functions as policies.aashray_order.
"""

from policies import (
    arrival_view,
    fcfs_order,
    normalized_priority,
    order_by_scores,
    overall_priority,
)


def compute_rankings(dataset: dict, grid: list[dict]) -> dict:
    """Return the distinct orders per scenario and the equivalence classes.

    scenario_orders[s]     -> list of distinct orders (tuples of ids) in
                              scenario s, indexed by order id
    config_order_ids[c][s] -> order id used by grid[c] in scenario s
    classes                -> one dict per class: class_id, representative
                              (grid index), members (grid indices),
                              order_ids (per scenario)
    """

    alphas = sorted({config["alpha"] for config in grid})

    scenario_orders = []
    config_order_ids = [[] for _ in grid]

    for scenario in dataset["scenarios"]:

        emergencies = scenario["emergencies"]
        fcfs = fcfs_order(arrival_view(emergencies))

        severity_urgency = {
            e["emergency_id"]: (e["severity"], e["urgency"]) for e in emergencies
        }

        # P_n depends only on alpha, so it is computed once per alpha.
        p_n_by_alpha = {
            alpha: {
                emergency_id: normalized_priority(s, u, alpha)
                for emergency_id, (s, u) in severity_urgency.items()
            }
            for alpha in alphas
        }

        distinct = {}

        for config_index, config in enumerate(grid):

            p_n = p_n_by_alpha[config["alpha"]]

            scores = {
                emergency_id: overall_priority(
                    s,
                    u,
                    config["k"],
                    config["m"],
                    config["n"],
                    p_n[emergency_id],
                )
                for emergency_id, (s, u) in severity_urgency.items()
            }

            order = tuple(order_by_scores(fcfs, scores))
            order_id = distinct.setdefault(order, len(distinct))

            config_order_ids[config_index].append(order_id)

        scenario_orders.append(list(distinct))

    # Group configurations with identical signatures. Grid order is
    # ascending config_id, so the first member is the lowest config_id.
    groups = {}

    for config_index, order_ids in enumerate(config_order_ids):
        groups.setdefault(tuple(order_ids), []).append(config_index)

    classes = [
        {
            "class_id": f"R{class_number:03d}",
            "representative": members[0],
            "members": members,
            "order_ids": list(signature),
        }
        for class_number, (signature, members) in enumerate(
            sorted(groups.items(), key=lambda item: item[1][0]),
            start=1,
        )
    ]

    return {
        "scenario_orders": scenario_orders,
        "config_order_ids": config_order_ids,
        "classes": classes,
    }
