import json

from resource_services.schemas.allocation import AllocationRequest
from resource_services.schemas.resource_requirement import ResourceRequirement
from resource_services.services.resource_allocation_service import (
    ResourceAllocationService,
)


WAREHOUSES_PATH = "resource_services/database/warehouses.json"


# Severity and urgency will later be produced by upstream services.
# Until those exist, every test feeds the engine dummy values.
DUMMY_SEVERITY = 0.8
DUMMY_URGENCY = 0.7
DUMMY_PRIORITY = "HIGH"


def build_warehouse(warehouse_id, water, food, medical_kits):
    return {
        "warehouse_id": warehouse_id,
        "name": f"Test Warehouse {warehouse_id}",
        "location": {
            "latitude": 19.0760,
            "longitude": 72.8777,
        },
        "inventory": {
            "water": {
                "available": water,
                "capacity": water,
            },
            "food": {
                "available": food,
                "capacity": food,
            },
            "medical_kits": {
                "available": medical_kits,
                "capacity": medical_kits,
            },
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


def build_request(
    incident_id,
    severity,
    urgency,
    priority,
    water=0,
    food=0,
    medical_kits=0,
):
    return AllocationRequest(
        incident_id=incident_id,
        requirements=ResourceRequirement(
            water=water,
            food=food,
            medical_kits=medical_kits,
        ),
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
    print(f"Water         : {result.required_resources.water}")
    print(f"Food          : {result.required_resources.food}")
    print(f"Medical Kits  : {result.required_resources.medical_kits}")

    print("\nWAREHOUSE CONTRIBUTIONS")
    print("-" * 70)

    if not result.warehouse_allocations:
        print("No warehouse contributed resources.")
    else:
        for allocation in result.warehouse_allocations:
            print(f"\nWarehouse: {allocation.warehouse_id}")
            print(f"  Water        : {allocation.supplies.water}")
            print(f"  Food         : {allocation.supplies.food}")
            print(f"  Medical Kits : {allocation.supplies.medical_kits}")

    print("\nTOTAL ALLOCATED")
    print("-" * 70)
    print(f"Water         : {result.allocated_resources.water}")
    print(f"Food          : {result.allocated_resources.food}")
    print(f"Medical Kits  : {result.allocated_resources.medical_kits}")

    print("\nREMAINING SHORTAGE")
    print("-" * 70)
    print(f"Water         : {result.remaining_shortage.water}")
    print(f"Food          : {result.remaining_shortage.food}")
    print(f"Medical Kits  : {result.remaining_shortage.medical_kits}")

    print("=" * 70)


def test_single_warehouse_fulfills_requirement():

    service = ResourceAllocationService(WAREHOUSES_PATH)

    requirements = ResourceRequirement(
        water=500,
        food=200,
        medical_kits=50,
    )

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

    assert result.allocated_resources.water == 500
    assert result.allocated_resources.food == 200
    assert result.allocated_resources.medical_kits == 50

    assert result.remaining_shortage.water == 0
    assert result.remaining_shortage.food == 0
    assert result.remaining_shortage.medical_kits == 0

    assert len(result.warehouse_allocations) == 1


def test_multiple_warehouses_fulfill_requirement():

    service = ResourceAllocationService(WAREHOUSES_PATH)

    requirements = ResourceRequirement(
        water=1600,
        food=1000,
        medical_kits=150,
    )

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

    assert result.allocated_resources.water == 1600
    assert result.allocated_resources.food == 1000
    assert result.allocated_resources.medical_kits == 150

    assert result.remaining_shortage.water == 0
    assert result.remaining_shortage.food == 0
    assert result.remaining_shortage.medical_kits == 0

    assert len(result.warehouse_allocations) >= 2


def test_partial_fulfillment_when_inventory_is_insufficient():

    service = ResourceAllocationService(WAREHOUSES_PATH)

    requirements = ResourceRequirement(
        water=10000,
        food=10000,
        medical_kits=10000,
    )

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

    assert result.allocated_resources.water < requirements.water
    assert result.allocated_resources.food < requirements.food
    assert result.allocated_resources.medical_kits < requirements.medical_kits

    assert result.remaining_shortage.water > 0
    assert result.remaining_shortage.food > 0
    assert result.remaining_shortage.medical_kits > 0


def test_normalized_priority_values():

    service = ResourceAllocationService(WAREHOUSES_PATH)

    assert service.normalize_priority("LOW") == 0.25
    assert service.normalize_priority("MODERATE") == 0.50
    assert service.normalize_priority("HIGH") == 0.75
    assert service.normalize_priority("CRITICAL") == 1.00


def test_overall_priority_score_formula():

    service = ResourceAllocationService(WAREHOUSES_PATH)

    cases = [
        # (severity, urgency, priority, expected score)
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

    # Just past each boundary the next level takes over.
    assert service.determine_priority_level(0.00) == "LOW"
    assert service.determine_priority_level(0.3501) == "MODERATE"
    assert service.determine_priority_level(0.6001) == "HIGH"
    assert service.determine_priority_level(1.00) == "CRITICAL"


def test_priority_level_boundaries_through_allocation():

    service = ResourceAllocationService(WAREHOUSES_PATH)

    requirements = ResourceRequirement(
        water=10,
        food=10,
        medical_kits=1,
    )

    cases = [
        # (severity, urgency, priority, expected score, expected level)
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

    requirements = ResourceRequirement(
        water=500,
        food=200,
        medical_kits=50,
    )

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

    # Existing allocation behaviour is unchanged.
    assert result.allocation_status == "FULLY_FULFILLED"

    assert result.allocated_resources.water == 500
    assert result.allocated_resources.food == 200
    assert result.allocated_resources.medical_kits == 50

    assert len(result.warehouse_allocations) == 1
    assert result.warehouse_allocations[0].warehouse_id == "WH001"

    # Priority data is now part of the allocation decision data.
    assert result.normalized_priority == 1.00
    assert result.overall_priority_score == 0.88
    assert result.final_priority_level == "CRITICAL"


def test_multiple_emergencies_are_ranked_by_overall_priority_score():

    service = ResourceAllocationService(WAREHOUSES_PATH)

    requests = [
        # score 0.05 -> LOW
        build_request("INC-LOW", 0.0, 0.0, "LOW", water=10, food=10),
        # score 0.92 -> CRITICAL
        build_request(
            "INC-CRITICAL", 0.9, 0.9, "CRITICAL", water=10, food=10
        ),
        # score 0.50 -> MODERATE
        build_request(
            "INC-MODERATE", 0.5, 0.5, "MODERATE", water=10, food=10
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

    # Every emergency is still processed.
    assert all(
        result.allocation_status == "FULLY_FULFILLED" for result in results
    )


def test_higher_priority_emergency_takes_contested_inventory_first(tmp_path):

    # One shared warehouse that cannot serve both emergencies in full.
    service = build_service_with_inventory(
        tmp_path,
        [
            build_warehouse(
                "WH-SHARED",
                water=1000,
                food=500,
                medical_kits=100,
            )
        ],
    )

    low_priority = build_request(
        "INC-LOW",
        severity=0.1,
        urgency=0.1,
        priority="LOW",
        water=800,
        food=400,
        medical_kits=80,
    )

    critical_priority = build_request(
        "INC-CRITICAL",
        severity=0.9,
        urgency=0.9,
        priority="CRITICAL",
        water=800,
        food=400,
        medical_kits=80,
    )

    # The lower priority emergency is submitted first on purpose.
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

    # Highest overall priority score is allocated first.
    assert first.incident_id == "INC-CRITICAL"
    assert first.overall_priority_score == 0.92
    assert first.final_priority_level == "CRITICAL"

    assert first.allocation_status == "FULLY_FULFILLED"
    assert first.allocated_resources.water == 800
    assert first.allocated_resources.food == 400
    assert first.allocated_resources.medical_kits == 80

    # The lower priority emergency is processed afterwards and only sees
    # what is left in the shared working inventory.
    assert second.incident_id == "INC-LOW"
    assert second.overall_priority_score == 0.13
    assert second.final_priority_level == "LOW"

    assert second.allocated_resources.water == 200
    assert second.allocated_resources.food == 100
    assert second.allocated_resources.medical_kits == 20

    # Existing shortage / partial fulfilment behaviour is preserved.
    assert second.allocation_status == "PARTIALLY_FULFILLED"
    assert second.remaining_shortage.water == 600
    assert second.remaining_shortage.food == 300
    assert second.remaining_shortage.medical_kits == 60


def test_batch_allocation_does_not_mutate_loaded_warehouse_inventory(tmp_path):

    service = build_service_with_inventory(
        tmp_path,
        [
            build_warehouse(
                "WH-SHARED",
                water=1000,
                food=500,
                medical_kits=100,
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
                water=1000,
                food=500,
                medical_kits=100,
            )
        ]
    )

    warehouse = service.warehouses[0]

    assert warehouse.inventory["water"].available == 1000
    assert warehouse.inventory["food"].available == 500
    assert warehouse.inventory["medical_kits"].available == 100
