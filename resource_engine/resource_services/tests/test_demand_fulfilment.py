from resource_services.schemas.demand_fulfilment import (
    DemandFulfilmentRequest,
)
from resource_services.services.demand_fulfilment_service import (
    DemandFulfilmentService,
)


def test_full_fulfilment():

    request = DemandFulfilmentRequest(
        allocation_id="ALLOC-001",
        incident_id="INC-001",
        required_resources={
            "water": 2000,
            "food": 1000,
            "medical_kits": 500,
        },
        allocated_resources={
            "water": 2000,
            "food": 1000,
            "medical_kits": 500,
        },
    )

    service = DemandFulfilmentService()

    result = service.verify(request)

    assert result.fulfilment_status == "FULLY_FULFILLED"

    assert result.total_shortage == {
        "water": 0,
        "food": 0,
        "medical_kits": 0,
    }


def test_partial_fulfilment():

    request = DemandFulfilmentRequest(
        allocation_id="ALLOC-002",
        incident_id="INC-002",
        required_resources={
            "water": 2000,
            "food": 1000,
            "medical_kits": 500,
        },
        allocated_resources={
            "water": 2000,
            "food": 1000,
            "medical_kits": 350,
        },
    )

    service = DemandFulfilmentService()

    result = service.verify(request)

    assert result.fulfilment_status == "PARTIALLY_FULFILLED"

    assert result.total_shortage == {
        "water": 0,
        "food": 0,
        "medical_kits": 150,
    }


def test_multiple_resource_shortages():

    request = DemandFulfilmentRequest(
        allocation_id="ALLOC-003",
        incident_id="INC-003",
        required_resources={
            "water": 2000,
            "food": 1000,
            "medical_kits": 500,
        },
        allocated_resources={
            "water": 1500,
            "food": 700,
            "medical_kits": 500,
        },
    )

    service = DemandFulfilmentService()

    result = service.verify(request)

    assert result.fulfilment_status == "PARTIALLY_FULFILLED"

    assert result.total_shortage == {
        "water": 500,
        "food": 300,
        "medical_kits": 0,
    }


def test_missing_resource_is_treated_as_zero():

    request = DemandFulfilmentRequest(
        allocation_id="ALLOC-004",
        incident_id="INC-004",
        required_resources={
            "water": 2000,
            "food": 1000,
        },
        allocated_resources={
            "water": 2000,
        },
    )

    service = DemandFulfilmentService()

    result = service.verify(request)

    assert result.fulfilment_status == "PARTIALLY_FULFILLED"

    assert result.resource_status["food"].allocated == 0

    assert result.resource_status["food"].shortage == 1000