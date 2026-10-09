"""Exact MILP for maximum GT-critical demand fulfilment.

Variables (full index set, no pre-elimination):

    x[e,r,w] >= 0, integer   quantity of resource r from warehouse w to
                             emergency e

Objective:

    maximize  sum_{e,r,w} GT_critical[e] * x[e,r,w]

Constraints:

    supply:  for every warehouse w, type r:   sum_e x[e,r,w] <= available[w,r]
    demand:  for every emergency e, type r:   sum_w x[e,r,w] <= demand[e,r]

Nothing else. The current allocator has no vehicle, compatibility,
distance, time, route or priority constraints, so none are added.
GT_critical is the stored fixed label; no AASHRAY, FCFS or linear score is
used. scipy.optimize.milp minimises, so the objective vector is
-GT_critical.
"""

import math
import time
from dataclasses import dataclass

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_matrix

from milp_common import RESOURCE_TYPES


OPTIMUM_BOUND_TOLERANCE = 1e-6
INTEGRALITY_TOLERANCE = 1e-6


@dataclass
class MilpModel:
    scenario_id: str
    emergency_ids: list[str]
    warehouse_ids: list[str]
    critical: list[int]
    demand: list[list[int]]       # [e][r]
    available: list[list[int]]    # [w][r]
    objective: np.ndarray
    constraints: LinearConstraint
    bounds: Bounds
    integrality: np.ndarray
    number_variables: int
    number_constraints: int

    def variable_index(self, e: int, r: int, w: int) -> int:
        return (e * len(RESOURCE_TYPES) + r) * len(self.warehouse_ids) + w


def build_model(scenario: dict) -> MilpModel:
    emergencies = scenario["emergencies"]
    warehouses = scenario["resource_inventory"]

    n_e, n_r, n_w = len(emergencies), len(RESOURCE_TYPES), len(warehouses)
    n_variables = n_e * n_r * n_w

    critical = [int(e["ground_truth_critical"]) for e in emergencies]
    demand = [[int(e["resource_requirements"][r]) for r in RESOURCE_TYPES] for e in emergencies]
    available = [
        [int(w["inventory"].get(r, {"available": 0})["available"]) for r in RESOURCE_TYPES]
        for w in warehouses
    ]

    def index(e, r, w):
        return (e * n_r + r) * n_w + w

    # Objective (minimise the negative of critical fulfilment).
    objective = np.zeros(n_variables)
    for e in range(n_e):
        for r in range(n_r):
            for w in range(n_w):
                objective[index(e, r, w)] = -critical[e]

    rows, cols, upper = [], [], []
    row = 0

    # Supply: one row per (warehouse, type).
    for w in range(n_w):
        for r in range(n_r):
            for e in range(n_e):
                rows.append(row)
                cols.append(index(e, r, w))
            upper.append(available[w][r])
            row += 1

    # Demand: one row per (emergency, type).
    for e in range(n_e):
        for r in range(n_r):
            for w in range(n_w):
                rows.append(row)
                cols.append(index(e, r, w))
            upper.append(demand[e][r])
            row += 1

    matrix = coo_matrix(
        (np.ones(len(rows)), (rows, cols)),
        shape=(row, n_variables),
    ).tocsr()

    return MilpModel(
        scenario_id=scenario["scenario_id"],
        emergency_ids=[e["emergency_id"] for e in emergencies],
        warehouse_ids=[w["warehouse_id"] for w in warehouses],
        critical=critical,
        demand=demand,
        available=available,
        objective=objective,
        constraints=LinearConstraint(matrix, -np.inf, np.array(upper, dtype=float)),
        bounds=Bounds(np.zeros(n_variables), np.full(n_variables, np.inf)),
        integrality=np.ones(n_variables),
        number_variables=n_variables,
        number_constraints=row,
    )


def is_proven_optimum(status, success, mip_gap, objective, dual_bound) -> bool:
    # Only an exact, proven optimum qualifies; a time-limited or gapped
    # incumbent never does.
    return (
        status == 0
        and bool(success)
        and mip_gap is not None
        and mip_gap == 0
        and objective is not None
        and dual_bound is not None
        and abs(objective - dual_bound) <= OPTIMUM_BOUND_TOLERANCE
    )


def solve_model(model: MilpModel, options: dict) -> dict:
    started = time.perf_counter()
    result = milp(
        c=model.objective,
        constraints=model.constraints,
        integrality=model.integrality,
        bounds=model.bounds,
        options=options,
    )
    solver_time = time.perf_counter() - started

    objective = -result.fun if result.fun is not None else None
    dual_bound = getattr(result, "mip_dual_bound", None)
    dual_bound = -dual_bound if dual_bound is not None else None
    mip_gap = getattr(result, "mip_gap", None)

    return {
        "result": result,
        "solver_status": int(result.status),
        "solver_message": result.message,
        "solver_success": bool(result.success),
        "objective_value": objective,
        "best_bound": dual_bound,
        "mip_gap": mip_gap,
        "mip_node_count": getattr(result, "mip_node_count", None),
        "is_proven_optimum": is_proven_optimum(
            int(result.status), result.success, mip_gap, objective, dual_bound
        ),
        "solver_time_seconds": solver_time,
    }


def extract_allocation(model: MilpModel, x) -> tuple[list[dict], float]:
    """Round the solution to integers. Returns the non-zero allocations and
    the largest deviation from integrality."""

    allocations = []
    max_deviation = 0.0

    for e, emergency_id in enumerate(model.emergency_ids):
        for r, resource in enumerate(RESOURCE_TYPES):
            for w, warehouse_id in enumerate(model.warehouse_ids):
                value = float(x[model.variable_index(e, r, w)])
                rounded = int(round(value))
                max_deviation = max(max_deviation, abs(value - rounded))

                if rounded != 0:
                    allocations.append(
                        {
                            "emergency_id": emergency_id,
                            "resource_type": resource,
                            "warehouse_id": warehouse_id,
                            "allocated_quantity": rounded,
                        }
                    )

    return allocations, max_deviation


def summarize_allocation(model: MilpModel, allocations: list[dict]) -> dict:
    critical = dict(zip(model.emergency_ids, model.critical))

    critical_required = sum(
        model.critical[e] * sum(model.demand[e]) for e in range(len(model.emergency_ids))
    )
    total_required = sum(sum(row) for row in model.demand)

    critical_fulfilled = sum(
        a["allocated_quantity"] for a in allocations if critical[a["emergency_id"]]
    )
    total_fulfilled = sum(a["allocated_quantity"] for a in allocations)

    return {
        "critical_required": critical_required,
        "critical_fulfilled": critical_fulfilled,
        "critical_unmet": critical_required - critical_fulfilled,
        # Undefined when there is no critical demand; never 0 or 1.
        "cdc": critical_fulfilled / critical_required if critical_required else math.nan,
        "total_required": total_required,
        "total_fulfilled_solver_dependent": total_fulfilled,
        "tdc_solver_dependent": total_fulfilled / total_required if total_required else math.nan,
    }


def run_scenario(scenario: dict, options: dict) -> dict:
    """Build and solve one scenario; timing covers only build + solve."""

    started = time.perf_counter()
    model = build_model(scenario)
    build_time = time.perf_counter() - started

    solved = solve_model(model, options)

    outcome = {
        "scenario_id": scenario["scenario_id"],
        "number_variables": model.number_variables,
        "number_constraints": model.number_constraints,
        "model_build_time_seconds": build_time,
        "solver_time_seconds": solved["solver_time_seconds"],
        "total_milp_time_seconds": build_time + solved["solver_time_seconds"],
        **{k: v for k, v in solved.items() if k not in ("result", "solver_time_seconds")},
    }

    if solved["result"].x is None:
        outcome.update({"allocations": [], "max_integrality_deviation": None,
                        "critical_required": None, "critical_fulfilled": None,
                        "critical_unmet": None, "cdc": math.nan,
                        "total_required": None, "total_fulfilled_solver_dependent": None,
                        "tdc_solver_dependent": math.nan})
        return outcome

    allocations, deviation = extract_allocation(model, solved["result"].x)

    outcome.update(summarize_allocation(model, allocations))
    outcome["allocations"] = allocations
    outcome["max_integrality_deviation"] = deviation

    return outcome
