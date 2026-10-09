"""Hand-checked MILP scenarios. Must all pass before any development run.

Usage (from the repository root):

    python experiments/resource_allocation_milp/scripts/hand_check_tests.py

Every expected value is a literal worked out by hand (the arithmetic is
written next to it), not computed by the MILP or the analytical oracle.
Each test also checks a structural property where one applies.
"""

import math
import sys

from analytical_optimum import analytical_optimum
from milp_common import HAND_CHECK_PATH, json_text, load_config, write_text
from milp_model import run_scenario


def emergency(eid, critical, water=0, food=0, medical_kits=0):
    return {
        "emergency_id": eid,
        "ground_truth_critical": critical,
        "resource_requirements": {"water": water, "food": food, "medical_kits": medical_kits},
    }


def warehouse(wid, water=0, food=0, medical_kits=0):
    return {
        "warehouse_id": wid,
        "inventory": {
            "water": {"available": water, "capacity": water},
            "food": {"available": food, "capacity": food},
            "medical_kits": {"available": medical_kits, "capacity": medical_kits},
        },
    }


def scenario(sid, emergencies, warehouses):
    return {"scenario_id": sid, "emergencies": emergencies, "resource_inventory": warehouses}


def allocated_to(outcome, emergency_id, resource=None):
    return sum(
        a["allocated_quantity"] for a in outcome["allocations"]
        if a["emergency_id"] == emergency_id
        and (resource is None or a["resource_type"] == resource)
    )


TESTS = [
    {
        "id": "TEST-01",
        "description": "One critical emergency, enough resources",
        "scenario": scenario("TEST-01",
                             [emergency("E1", 1, water=100, food=50, medical_kits=5)],
                             [warehouse("W1", water=500, food=200, medical_kits=20)]),
        # required 100 + 50 + 5 = 155; all available
        "expected": {"critical_required": 155, "critical_fulfilled": 155, "cdc": 1.0},
        "property": lambda o: allocated_to(o, "E1") == 155,
        "property_text": "E1 receives all 155 units",
    },
    {
        "id": "TEST-02",
        "description": "One critical emergency, insufficient resources",
        "scenario": scenario("TEST-02",
                             [emergency("E1", 1, water=100)],
                             [warehouse("W1", water=60)]),
        # needs 100 water, only 60 exist -> 60; CDC 60/100
        "expected": {"critical_required": 100, "critical_fulfilled": 60, "cdc": 0.6},
        "property": lambda o: allocated_to(o, "E1", "water") == 60,
        "property_text": "E1 receives exactly the 60 available",
    },
    {
        "id": "TEST-03",
        "description": "Two critical emergencies compete for one resource",
        "scenario": scenario("TEST-03",
                             [emergency("E1", 1, water=80), emergency("E2", 1, water=70)],
                             [warehouse("W1", water=100)]),
        # critical demand 80 + 70 = 150; supply 100 -> 100; CDC 100/150 = 2/3
        "expected": {"critical_required": 150, "critical_fulfilled": 100, "cdc": 100 / 150},
        "property": lambda o: allocated_to(o, "E1") + allocated_to(o, "E2") == 100,
        "property_text": "all 100 units go to the two critical emergencies",
    },
    {
        "id": "TEST-04",
        "description": "Critical and non-critical compete for a scarce resource",
        "scenario": scenario("TEST-04",
                             # non-critical listed first on purpose
                             [emergency("E1", 0, water=80), emergency("E2", 1, water=80)],
                             [warehouse("W1", water=100)]),
        # critical E2 needs 80 of 100 -> fully served; CDC 80/80
        "expected": {"critical_required": 80, "critical_fulfilled": 80, "cdc": 1.0},
        "property": lambda o: allocated_to(o, "E2") == 80 and allocated_to(o, "E1") <= 20,
        "property_text": "critical E2 gets all 80; non-critical E1 gets at most the 20 left",
    },
    {
        "id": "TEST-05",
        "description": "One resource split across multiple warehouses",
        "scenario": scenario("TEST-05",
                             [emergency("E1", 1, water=100)],
                             [warehouse("W1", water=40), warehouse("W2", water=30),
                              warehouse("W3", water=20)]),
        # supply 40 + 30 + 20 = 90 < 100 -> 90; CDC 0.9
        "expected": {"critical_required": 100, "critical_fulfilled": 90, "cdc": 0.9},
        "property": lambda o: sorted(
            (a["warehouse_id"], a["allocated_quantity"]) for a in o["allocations"]
        ) == [("W1", 40), ("W2", 30), ("W3", 20)],
        "property_text": "every warehouse is emptied: W1 40, W2 30, W3 20",
    },
    {
        "id": "TEST-06",
        "description": "Multiple resource types with different shortages",
        "scenario": scenario("TEST-06",
                             [emergency("E1", 1, water=100, food=100, medical_kits=10)],
                             [warehouse("W1", water=150, food=40, medical_kits=10)]),
        # water min(100,150)=100, food min(100,40)=40, kits min(10,10)=10
        # -> 150 of 210; CDC 150/210 = 5/7
        "expected": {"critical_required": 210, "critical_fulfilled": 150, "cdc": 150 / 210},
        "property": lambda o: (allocated_to(o, "E1", "water"), allocated_to(o, "E1", "food"),
                               allocated_to(o, "E1", "medical_kits")) == (100, 40, 10),
        "property_text": "water 100 (surplus), food 40 (short), kits 10 (exact)",
    },
    {
        "id": "TEST-07",
        "description": "Partial fulfilment required",
        "scenario": scenario("TEST-07",
                             [emergency("E1", 1, water=30, food=20)],
                             [warehouse("W1", water=6, food=5), warehouse("W2", water=4)]),
        # water 6 + 4 = 10 of 30, food 5 of 20 -> 15 of 50; CDC 0.3
        "expected": {"critical_required": 50, "critical_fulfilled": 15, "cdc": 0.3},
        "property": lambda o: 0 < allocated_to(o, "E1") < 50,
        "property_text": "E1 is partially (neither fully nor not at all) served",
    },
    {
        "id": "TEST-08",
        "description": "No critical demand: CDC undefined",
        "scenario": scenario("TEST-08",
                             [emergency("E1", 0, water=50)],
                             [warehouse("W1", water=100)]),
        # no GT-critical emergency -> critical_required 0 -> CDC NaN, objective 0
        "expected": {"critical_required": 0, "critical_fulfilled": 0, "cdc": math.nan},
        "property": lambda o: o["objective_value"] == 0,
        "property_text": "objective is 0 and CDC is NaN, not 0 or 1",
    },
]


def same_cdc(got, expected):
    if math.isnan(expected):
        return isinstance(got, float) and math.isnan(got)
    return isinstance(got, float) and math.isclose(got, expected, rel_tol=0, abs_tol=1e-12)


def run_tests(options: dict) -> list[dict]:
    results = []

    for test in TESTS:
        outcome = run_scenario(test["scenario"], options)
        oracle = analytical_optimum(test["scenario"])
        expected = test["expected"]

        checks = {
            "proven_optimum": outcome["is_proven_optimum"],
            "critical_required": outcome["critical_required"] == expected["critical_required"],
            "critical_fulfilled": outcome["critical_fulfilled"] == expected["critical_fulfilled"],
            "cdc": same_cdc(outcome["cdc"], expected["cdc"]),
            "analytical_oracle_agrees": oracle["analytical_optimum"] == expected["critical_fulfilled"],
            "property": bool(test["property"](outcome)),
        }

        results.append(
            {
                "id": test["id"],
                "description": test["description"],
                "expected": {**expected, "cdc": None if math.isnan(expected["cdc"]) else expected["cdc"]},
                "expected_cdc_undefined": math.isnan(expected["cdc"]),
                "got": {
                    "solver_status": outcome["solver_status"],
                    "is_proven_optimum": outcome["is_proven_optimum"],
                    "objective_value": outcome["objective_value"],
                    "critical_required": outcome["critical_required"],
                    "critical_fulfilled": outcome["critical_fulfilled"],
                    "cdc": None if math.isnan(outcome["cdc"]) else outcome["cdc"],
                    "cdc_undefined": math.isnan(outcome["cdc"]),
                    "allocations": outcome["allocations"],
                },
                "analytical_optimum": oracle["analytical_optimum"],
                "property": test["property_text"],
                "checks": checks,
                "passed": all(checks.values()),
            }
        )

    return results


def main() -> None:
    results = run_tests(load_config()["solver"]["options"])

    write_text(HAND_CHECK_PATH, json_text({
        "all_passed": all(r["passed"] for r in results),
        "tests": results,
    }))

    for r in results:
        print(f"[{'PASS' if r['passed'] else 'FAIL'}] {r['id']}  {r['description']}"
              f"  -> fulfilled {r['got']['critical_fulfilled']}/{r['got']['critical_required']}"
              f", CDC {r['got']['cdc']}")

    if not all(r["passed"] for r in results):
        print("STOP: hand checks failed.")
        sys.exit(1)


if __name__ == "__main__":
    main()
