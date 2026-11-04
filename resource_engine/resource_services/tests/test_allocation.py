import json

from resource_services.schemas.allocation import AllocationRequest
from resource_services.services.resource_allocation_service import (
    ResourceAllocationService,
)


WAREHOUSES_PATH = "resource_services/database/warehouses.json"


DUMMY_SEVERITY = 0.8
DUMMY_URGENCY = 0.7
DUMMY_PRIORITY = "HIGH"


def build_warehouse(warehouse_id, **inventory_items):
    return {
        "warehouse_id": warehouse_id,
        "name": f"Test Warehouse {warehouse_id}",
        "location": {
            "latitude": 19.0760,
            "longitude": 72.8777,
        },
        "inventory": {
            resource: {"available": qty, "capacity": qty}
            for resource, qty in inventory_items.items()
        },
        "vehicles": {},
    }


def build_service_with_inventory(tmp_path, warehouses):
    warehouses_file = tmp_path / "warehouses.json"

    warehouses_file.write_text(
        json.dumps(warehouses),
        encoding="utf-8",
    )

    return ResourceAllocationService(warehouses_file)


def build_request(incident_id, severity, urgency, priority, **resources):
    return AllocationRequest(
        incident_id=incident_id,
        requirements=resources,
        severity=severity,
        urgency=urgency,
        priority=priority,
    )


def print_allocation_result(test_name, result):
    print("\n" + "=" * 70)
    print(f"  {test_name}")
    print("=" * 70)

    print(f"Allocation ID : {result.allocation_id}")
    print(f"Incident ID   : {result.incident_id}")
    print(f"Status        : {result.allocation_status}")

    print("\nEMERGENCY PRIORITY")
    print("-" * 70)
    print(f"Normalized Priority   : {result.normalized_priority}")
    print(f"Overall Priority Score: {result.overall_priority_score}")
    print(f"Final Priority Level  : {result.final_priority_level}")

    print("\nREQUIRED RESOURCES")
    print("-" * 70)
    for res, qty in result.required_resources.items():
        print(f"  {res}: {qty}")

    print("\nWAREHOUSE CONTRIBUTIONS")
    print("-" * 70)

    if not result.warehouse_allocations:
        print("No warehouse contributed resources.")
    else:
        for allocation in result.warehouse_allocations:
            print(f"\nWarehouse: {allocation.warehouse_id}")
            for res, qty in allocation.supplies.items():
                print(f"  {res}: {qty}")

    print("\nTOTAL ALLOCATED")
    print("-" * 70)
    for res, qty in result.allocated_resources.items():
        print(f"  {res}: {qty}")

    print("\nREMAINING SHORTAGE")
    print("-" * 70)
    for res, qty in result.remaining_shortage.items():
        print(f"  {res}: {qty}")

    print("=" * 70)


def test_single_warehouse_fulfills_requirement():

    service = ResourceAllocationService(WAREHOUSES_PATH)

    requirements = {
        "drinking_water": 500,
        "food_dry_rations": 200,
        "medicines_medical_supplies": 50,
    }

    result = service.allocate(
        incident_id="INC-001",
        requirements=requirements,
        severity=DUMMY_SEVERITY,
        urgency=DUMMY_URGENCY,
        priority=DUMMY_PRIORITY,
    )

    print_allocation_result(
        "CASE 1 - SINGLE WAREHOUSE FULFILLS REQUIREMENT",
        result,
    )

    assert result.allocation_status == "FULLY_FULFILLED"

    assert result.allocated_resources["drinking_water"] == 500
    assert result.allocated_resources["food_dry_rations"] == 200
    assert result.allocated_resources["medicines_medical_supplies"] == 50

    assert result.remaining_shortage["drinking_water"] == 0
    assert result.remaining_shortage["food_dry_rations"] == 0
    assert result.remaining_shortage["medicines_medical_supplies"] == 0

    assert len(result.warehouse_allocations) == 1


def test_multiple_warehouses_fulfill_requirement():

    service = ResourceAllocationService(WAREHOUSES_PATH)

    requirements = {
        "drinking_water": 1600,
        "food_dry_rations": 1000,
        "medicines_medical_supplies": 150,
    }

    result = service.allocate(
        incident_id="INC-002",
        requirements=requirements,
        severity=DUMMY_SEVERITY,
        urgency=DUMMY_URGENCY,
        priority=DUMMY_PRIORITY,
    )

    print_allocation_result(
        "CASE 2 - MULTIPLE WAREHOUSES REQUIRED",
        result,
    )

    assert result.allocation_status == "FULLY_FULFILLED"

    assert result.allocated_resources["drinking_water"] == 1600
    assert result.allocated_resources["food_dry_rations"] == 1000
    assert result.allocated_resources["medicines_medical_supplies"] == 150

    assert result.remaining_shortage["drinking_water"] == 0
    assert result.remaining_shortage["food_dry_rations"] == 0
    assert result.remaining_shortage["medicines_medical_supplies"] == 0

    assert len(result.warehouse_allocations) >= 2


def test_partial_fulfillment_when_inventory_is_insufficient():

    service = ResourceAllocationService(WAREHOUSES_PATH)

    requirements = {
        "drinking_water": 10000,
        "food_dry_rations": 10000,
        "medicines_medical_supplies": 10000,
    }

    result = service.allocate(
        incident_id="INC-003",
        requirements=requirements,
        severity=DUMMY_SEVERITY,
        urgency=DUMMY_URGENCY,
        priority=DUMMY_PRIORITY,
    )

    print_allocation_result(
        "CASE 3 - INSUFFICIENT INVENTORY / PARTIAL FULFILLMENT",
        result,
    )

    assert result.allocation_status == "PARTIALLY_FULFILLED"

    assert result.allocated_resources["drinking_water"] < 10000
    assert result.allocated_resources["food_dry_rations"] < 10000
    assert result.allocated_resources["medicines_medical_supplies"] < 10000

    assert result.remaining_shortage["drinking_water"] > 0
    assert result.remaining_shortage["food_dry_rations"] > 0
    assert result.remaining_shortage["medicines_medical_supplies"] > 0


def test_normalized_priority_values():

    service = ResourceAllocationService(WAREHOUSES_PATH)

    assert service.normalize_priority("LOW") == 0.25
    assert service.normalize_priority("MODERATE") == 0.50
    assert service.normalize_priority("HIGH") == 0.75
    assert service.normalize_priority("CRITICAL") == 1.00


def test_overall_priority_score_formula():

    service = ResourceAllocationService(WAREHOUSES_PATH)

    cases = [
        (0.90, 0.60, "HIGH", 0.75),
        (0.50, 0.25, "LOW", 0.35),
        (0.50, 0.50, "CRITICAL", 0.60),
        (0.00, 0.00, "LOW", 0.05),
        (1.00, 1.00, "CRITICAL", 1.00),
    ]

    for severity, urgency, priority, expected in cases:

        normalized_priority = service.normalize_priority(priority)

        score = service.calculate_overall_priority_score(
            severity=severity,
            urgency=urgency,
            normalized_priority=normalized_priority,
        )

        manual_score = round(
            0.4 * severity + 0.4 * urgency + 0.2 * normalized_priority,
            4,
        )

        assert score == expected
        assert score == manual_score


def test_priority_level_boundaries_are_inclusive():

    service = ResourceAllocationService(WAREHOUSES_PATH)

    assert service.determine_priority_level(0.35) == "LOW"
    assert service.determine_priority_level(0.60) == "MODERATE"
    assert service.determine_priority_level(0.80) == "HIGH"
    assert service.determine_priority_level(0.81) == "CRITICAL"

    assert service.determine_priority_level(0.00) == "LOW"
    assert service.determine_priority_level(0.3501) == "MODERATE"
    assert service.determine_priority_level(0.6001) == "HIGH"
    assert service.determine_priority_level(1.00) == "CRITICAL"


def test_priority_level_boundaries_through_allocation():

    service = ResourceAllocationService(WAREHOUSES_PATH)

    requirements = {
        "drinking_water": 10,
        "food_dry_rations": 10,
        "medicines_medical_supplies": 1,
    }

    cases = [
        (0.50, 0.25, "LOW", 0.35, "LOW"),
        (0.50, 0.50, "CRITICAL", 0.60, "MODERATE"),
        (0.75, 0.75, "CRITICAL", 0.80, "HIGH"),
        (0.80, 0.80, "CRITICAL", 0.84, "CRITICAL"),
    ]

    for severity, urgency, priority, expected_score, expected_level in cases:

        result = service.allocate(
            incident_id="INC-BOUNDARY",
            requirements=requirements,
            severity=severity,
            urgency=urgency,
            priority=priority,
        )

        assert result.overall_priority_score == expected_score
        assert result.final_priority_level == expected_level


def test_single_emergency_allocates_normally_and_reports_priority():

    service = ResourceAllocationService(WAREHOUSES_PATH)

    requirements = {
        "drinking_water": 500,
        "food_dry_rations": 200,
        "medicines_medical_supplies": 50,
    }

    result = service.allocate(
        incident_id="INC-SINGLE",
        requirements=requirements,
        severity=0.9,
        urgency=0.8,
        priority="CRITICAL",
    )

    print_allocation_result(
        "CASE 4 - SINGLE EMERGENCY WITH PRIORITY DATA",
        result,
    )

    assert result.allocation_status == "FULLY_FULFILLED"

    assert result.allocated_resources["drinking_water"] == 500
    assert result.allocated_resources["food_dry_rations"] == 200
    assert result.allocated_resources["medicines_medical_supplies"] == 50

    assert len(result.warehouse_allocations) == 1
    assert result.warehouse_allocations[0].warehouse_id == "WH001"

    assert result.normalized_priority == 1.00
    assert result.overall_priority_score == 0.88
    assert result.final_priority_level == "CRITICAL"


def test_multiple_emergencies_are_ranked_by_overall_priority_score():

    service = ResourceAllocationService(WAREHOUSES_PATH)

    requests = [
        build_request(
            "INC-LOW", 0.0, 0.0, "LOW",
            drinking_water=10, food_dry_rations=10,
        ),
        build_request(
            "INC-CRITICAL", 0.9, 0.9, "CRITICAL",
            drinking_water=10, food_dry_rations=10,
        ),
        build_request(
            "INC-MODERATE", 0.5, 0.5, "MODERATE",
            drinking_water=10, food_dry_rations=10,
        ),
    ]

    results = service.allocate_batch(requests)

    assert [result.incident_id for result in results] == [
        "INC-CRITICAL",
        "INC-MODERATE",
        "INC-LOW",
    ]

    scores = [result.overall_priority_score for result in results]

    assert scores == sorted(scores, reverse=True)

    assert [result.final_priority_level for result in results] == [
        "CRITICAL",
        "MODERATE",
        "LOW",
    ]

    assert all(
        result.allocation_status == "FULLY_FULFILLED" for result in results
    )


def test_higher_priority_emergency_takes_contested_inventory_first(tmp_path):

    service = build_service_with_inventory(
        tmp_path,
        [
            build_warehouse(
                "WH-SHARED",
                drinking_water=1000,
                food_dry_rations=500,
                medicines_medical_supplies=100,
            )
        ],
    )

    low_priority = build_request(
        "INC-LOW",
        severity=0.1,
        urgency=0.1,
        priority="LOW",
        drinking_water=800,
        food_dry_rations=400,
        medicines_medical_supplies=80,
    )

    critical_priority = build_request(
        "INC-CRITICAL",
        severity=0.9,
        urgency=0.9,
        priority="CRITICAL",
        drinking_water=800,
        food_dry_rations=400,
        medicines_medical_supplies=80,
    )

    results = service.allocate_batch([low_priority, critical_priority])

    print_allocation_result(
        "CASE 5 - CONTESTED INVENTORY / FIRST ALLOCATION",
        results[0],
    )
    print_allocation_result(
        "CASE 5 - CONTESTED INVENTORY / SECOND ALLOCATION",
        results[1],
    )

    first, second = results

    assert first.incident_id == "INC-CRITICAL"
    assert first.overall_priority_score == 0.92
    assert first.final_priority_level == "CRITICAL"

    assert first.allocation_status == "FULLY_FULFILLED"
    assert first.allocated_resources["drinking_water"] == 800
    assert first.allocated_resources["food_dry_rations"] == 400
    assert first.allocated_resources["medicines_medical_supplies"] == 80

    assert second.incident_id == "INC-LOW"
    assert second.overall_priority_score == 0.13
    assert second.final_priority_level == "LOW"

    assert second.allocated_resources["drinking_water"] == 200
    assert second.allocated_resources["food_dry_rations"] == 100
    assert second.allocated_resources["medicines_medical_supplies"] == 20

    assert second.allocation_status == "PARTIALLY_FULFILLED"
    assert second.remaining_shortage["drinking_water"] == 600
    assert second.remaining_shortage["food_dry_rations"] == 300
    assert second.remaining_shortage["medicines_medical_supplies"] == 60


def test_batch_allocation_does_not_mutate_loaded_warehouse_inventory(tmp_path):

    service = build_service_with_inventory(
        tmp_path,
        [
            build_warehouse(
                "WH-SHARED",
                drinking_water=1000,
                food_dry_rations=500,
                medicines_medical_supplies=100,
            )
        ],
    )

    service.allocate_batch(
        [
            build_request(
                "INC-001",
                severity=0.9,
                urgency=0.9,
                priority="CRITICAL",
                drinking_water=1000,
                food_dry_rations=500,
                medicines_medical_supplies=100,
            )
        ]
    )

    warehouse = service.warehouses[0]

    assert warehouse.inventory["drinking_water"].available == 1000
    assert warehouse.inventory["food_dry_rations"].available == 500
    assert warehouse.inventory["medicines_medical_supplies"].available == 100
