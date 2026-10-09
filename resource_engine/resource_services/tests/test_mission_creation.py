from typing import get_args

import pytest
from pydantic import ValidationError

from resource_services.schemas.allocation import PriorityLevel
from resource_services.schemas.mission import MissionCreationRequest
from resource_services.services.mission_creation_service import (
    MissionCreationService,
)


def create_request(
    priority="MODERATE",
    patient_present=False,
    resources=None,
    warehouse_pickups=None,
):
    if resources is None:
        resources = {
            "water": 500,
            "food": 300,
            "medical_kits": 100,
        }

    if warehouse_pickups is None:
        warehouse_pickups = [
            {
                "warehouse_id": "WH001",
                "location": {
                    "latitude": 19.0760,
                    "longitude": 72.8777,
                },
                "supplies": {
                    "water": 500,
                    "food": 300,
                    "medical_kits": 100,
                },
            }
        ]

    return MissionCreationRequest(
        incident_id="INC-001",
        destination={
            "latitude": 19.0800,
            "longitude": 72.8900,
        },
        risk_score=0.75,
        priority=priority,
        patient_present=patient_present,
        resources=resources,
        warehouse_pickups=warehouse_pickups,
    )


def test_normal_mission_assigns_rescue_truck():

    request = create_request()

    service = MissionCreationService()

    result = service.create_mission(request)

    assert result.required_responder_types == ["RESCUE_TRUCK"]


def test_patient_mission_assigns_ambulance():

    request = create_request(
        patient_present=True,
    )

    service = MissionCreationService()

    result = service.create_mission(request)

    assert result.required_responder_types == ["AMBULANCE"]


def test_high_priority_mission_assigns_rescue_truck():

    request = create_request(
        priority="HIGH",
    )

    service = MissionCreationService()

    result = service.create_mission(request)

    assert result.required_responder_types == ["RESCUE_TRUCK"]


def test_multiple_warehouses_create_correct_pickup_sequence():

    request = create_request(
        resources={
            "water": 2000,
            "food": 1000,
            "medical_kits": 500,
        },
        warehouse_pickups=[
            {
                "warehouse_id": "WH001",
                "location": {
                    "latitude": 19.0760,
                    "longitude": 72.8777,
                },
                "supplies": {
                    "water": 1000,
                    "food": 500,
                    "medical_kits": 100,
                },
            },
            {
                "warehouse_id": "WH003",
                "location": {
                    "latitude": 19.1000,
                    "longitude": 72.8500,
                },
                "supplies": {
                    "water": 1000,
                    "food": 500,
                    "medical_kits": 400,
                },
            },
        ],
    )

    service = MissionCreationService()

    result = service.create_mission(request)

    assert len(result.pickup_sequence) == 3

    assert result.pickup_sequence[0].sequence == 1
    assert result.pickup_sequence[0].warehouse_id == "WH001"

    assert result.pickup_sequence[1].sequence == 2
    assert result.pickup_sequence[1].warehouse_id == "WH003"

    assert result.pickup_sequence[2].sequence == 3
    assert result.pickup_sequence[2].type == "DESTINATION"


def test_new_mission_has_route_unavailable():

    request = create_request()

    service = MissionCreationService()

    result = service.create_mission(request)

    assert result.route.status == "NOT_AVAILABLE"

    assert result.route.coordinates == []

    assert result.route.distance_km is None

    assert result.route.estimated_time_minutes is None


def test_new_mission_status_is_created():

    request = create_request()

    service = MissionCreationService()

    result = service.create_mission(request)

    assert result.status == "CREATED"


def test_priority_accepts_every_resource_allocation_level():

    # Resource Allocation's PriorityLevel is the source of truth.
    levels = get_args(PriorityLevel)

    assert levels == ("LOW", "MODERATE", "HIGH", "CRITICAL")

    for level in levels:
        request = create_request(priority=level)

        assert request.priority == level

    with pytest.raises(ValidationError):
        create_request(priority="MEDIUM")


# ==================================================
# Mission Creation contract: `resources` = actually allocated resources
# ==================================================


# Upstream values for a partially fulfilled incident (2,000 people).
# Resource Allocation keeps required and allocated apart; Mission Creation
# receives only the allocated amounts through `resources`.
REQUIRED_UPSTREAM = {"water": 4000.0, "food": 2000.0, "medical_kits": 100.0}

ALLOCATED_UPSTREAM = {"water": 2750.0, "food": 1900.0, "medical_kits": 100.0}

FULLY_ALLOCATED = {"water": 400.0, "food": 200.0, "medical_kits": 10.0}


def test_mission_accepts_resources():

    request = create_request(resources=ALLOCATED_UPSTREAM)

    assert request.resources == ALLOCATED_UPSTREAM


def test_required_resources_and_fulfilment_status_are_not_required():

    for field in ("required_resources", "allocated_resources", "fulfilment_status"):
        assert field not in MissionCreationRequest.model_fields

    # A request with only `resources` creates a mission.
    result = MissionCreationService().create_mission(
        create_request(resources=ALLOCATED_UPSTREAM)
    )

    assert result.status == "CREATED"


def test_result_resources_are_the_allocated_resources():

    result = MissionCreationService().create_mission(
        create_request(priority="HIGH", resources=ALLOCATED_UPSTREAM)
    )

    assert result.resources == ALLOCATED_UPSTREAM
    assert result.resources != REQUIRED_UPSTREAM
    assert result.priority == "HIGH"

    for field in ("required_resources", "allocated_resources", "fulfilment_status"):
        assert field not in result.model_dump()


# ==================================================
# Mission Creation behaviour scenarios
# ==================================================


def spy_on_responder_type(monkeypatch):
    # Records what reaches the unchanged responder-type rule.
    calls = []
    original = MissionCreationService._determine_responder_type

    def spy(self, priority, resources, patient_present):
        calls.append(
            {
                "priority": priority,
                "resources": resources,
                "patient_present": patient_present,
            }
        )
        return original(self, priority, resources, patient_present)

    monkeypatch.setattr(MissionCreationService, "_determine_responder_type", spy)

    return calls


def test_scenario_1_patient_present_with_normal_resources(monkeypatch):

    calls = spy_on_responder_type(monkeypatch)

    result = MissionCreationService().create_mission(
        create_request(patient_present=True, resources=FULLY_ALLOCATED)
    )

    assert result.status == "CREATED"
    assert calls[0]["patient_present"] is True

    # Existing rule: a patient means an ambulance.
    assert result.required_responder_types == ["AMBULANCE"]
    assert result.resources == FULLY_ALLOCATED


def test_scenario_2_patient_absent_keeps_existing_responder_rule(monkeypatch):

    calls = spy_on_responder_type(monkeypatch)

    service = MissionCreationService()

    for priority in ("LOW", "MODERATE", "HIGH", "CRITICAL", None):

        result = service.create_mission(
            create_request(priority=priority, patient_present=False)
        )

        assert result.status == "CREATED"
        assert result.required_responder_types == ["RESCUE_TRUCK"]

    assert all(call["patient_present"] is False for call in calls)


def test_scenario_3_fully_fulfilled_mission(monkeypatch):

    calls = spy_on_responder_type(monkeypatch)

    # Fully fulfilled upstream: allocated equals required.
    result = MissionCreationService().create_mission(
        create_request(resources=FULLY_ALLOCATED)
    )

    assert result.status == "CREATED"
    assert result.resources == FULLY_ALLOCATED
    assert calls[0]["resources"] == FULLY_ALLOCATED


def test_scenario_4_partially_fulfilled_mission_uses_allocated_amount(
    monkeypatch,
):

    calls = spy_on_responder_type(monkeypatch)

    # Upstream required 4,000 water but only 2,750 was allocated.
    result = MissionCreationService().create_mission(
        create_request(resources=ALLOCATED_UPSTREAM)
    )

    assert result.status == "CREATED"
    assert result.resources["water"] == 2750
    assert result.resources["water"] != REQUIRED_UPSTREAM["water"]
    assert calls[0]["resources"] == ALLOCATED_UPSTREAM
