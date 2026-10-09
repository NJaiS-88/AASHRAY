import json
import shutil

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from resource_services.app import app
from resource_services.routes import agent_assignment_routes
from resource_services.schemas.agent_assignment import AgentAssignmentRequest
from resource_services.schemas.demand_fulfilment import DemandFulfilmentRequest
from resource_services.schemas.incident import Incident
from resource_services.schemas.mission import MissionCreationRequest
from resource_services.services.agent_assignment_service import (
    AgentAssignmentService,
)
from resource_services.services.demand_fulfilment_service import (
    DemandFulfilmentService,
)
from resource_services.services.mission_creation_service import (
    MissionCreationService,
)
from resource_services.services.resource_allocation_service import (
    ResourceAllocationService,
)
from resource_services.services.resource_requirement_service import (
    ResourceRequirementService,
)


# Scenario tests that run the existing services in sequence:
# Incident -> Requirement -> Allocation -> Demand Fulfilment
#          -> Mission Creation -> Agent Assignment
#
# The wiring below is test code only. It follows the mappings in
# docs/orchestration_contract.md and is not an orchestrator.


RULES_PATH = "resource_services/config/resource_rules.json"
WAREHOUSES_PATH = "resource_services/database/warehouses.json"

# Upstream urgency and categorical priority services do not exist yet;
# allocation receives dummy values, as in the allocation tests.
DUMMY_URGENCY = 0.7
DUMMY_PRIORITY = "HIGH"


def build_incident(affected_population, patient_present=False):
    return Incident(
        incident_id="INC-PIPE",
        incident_type="FLOOD",
        location={"latitude": 19.0800, "longitude": 72.8900},
        locality={
            "name": "Test Locality",
            "population": 20000,
            "population_density": 12000,
            "affected_population": affected_population,
        },
        severity=0.8,
        estimated_duration_hours=12,
        patient_present=patient_present,
    )


def run_to_mission_request(incident, warehouses_path=WAREHOUSES_PATH):

    requirement = ResourceRequirementService(RULES_PATH).calculate(incident)

    allocation_service = ResourceAllocationService(warehouses_path)

    allocation = allocation_service.allocate(
        incident_id=incident.incident_id,
        requirements=requirement.requirements,
        severity=incident.severity,
        urgency=DUMMY_URGENCY,
        priority=DUMMY_PRIORITY,
    )

    verification = DemandFulfilmentService().verify(
        DemandFulfilmentRequest(
            allocation_id=allocation.allocation_id,
            incident_id=allocation.incident_id,
            required_resources=allocation.required_resources.model_dump(),
            allocated_resources=allocation.allocated_resources.model_dump(),
        )
    )

    # Pickup locations come from the existing warehouse database.
    locations = {
        warehouse.warehouse_id: warehouse.location
        for warehouse in allocation_service.warehouses
    }

    mission_request = MissionCreationRequest(
        incident_id=incident.incident_id,
        destination=incident.location,
        risk_score=incident.severity,
        priority=allocation.final_priority_level,
        patient_present=incident.patient_present,
        # MVP contract: `resources` = the actually allocated resources.
        resources=allocation.allocated_resources.model_dump(),
        warehouse_pickups=[
            {
                "warehouse_id": pickup.warehouse_id,
                "location": locations[pickup.warehouse_id],
                "supplies": pickup.supplies.model_dump(),
            }
            for pickup in allocation.warehouse_allocations
        ],
    )

    return requirement, allocation, verification, mission_request


def assign_first_pickup(mission, mission_request, responders_file):
    first_pickup = mission_request.warehouse_pickups[0]

    return AgentAssignmentService(responders_file).assign(
        AgentAssignmentRequest(
            mission_id=mission.mission_id,
            required_responder_types=mission.required_responder_types,
            first_warehouse_location=first_pickup.location,
            first_warehouse_id=first_pickup.warehouse_id,
        )
    )


def read_statuses(responders_file):
    with open(responders_file, encoding="utf-8") as file:
        return {
            record["responder_id"]: record["status"]
            for record in json.load(file)
        }


def test_scenario_a_fully_fulfilled_mission(responders_copy):

    incident = build_incident(affected_population=200)

    requirement, allocation, verification, mission_request = (
        run_to_mission_request(incident)
    )

    mission = MissionCreationService().create_mission(mission_request)

    # Required and fulfilment status stay upstream; the mission receives
    # the allocated resources.
    assert allocation.required_resources == requirement.requirements
    assert verification.fulfilment_status == "FULLY_FULFILLED"
    assert mission.resources == allocation.allocated_resources.model_dump()

    assert mission.status == "CREATED"
    assert mission.risk_score == incident.severity
    assert mission.priority == allocation.final_priority_level

    assignment = assign_first_pickup(mission, mission_request, responders_copy)

    assert assignment.assignment_status == "ASSIGNED"
    assert assignment.responder_type in mission.required_responder_types
    assert assignment.target_warehouse_id == "WH001"
    assert assignment.responder_id == "R001"

    assert read_statuses(responders_copy)["R001"] == "BUSY"


def test_scenario_b_partially_fulfilled_mission_is_still_dispatched(
    responders_copy,
):

    # 2,000 people need 4,000 water and 2,000 food; the warehouses hold
    # 2,750 water and 1,900 food in total.
    incident = build_incident(affected_population=2000, patient_present=True)

    requirement, allocation, verification, mission_request = (
        run_to_mission_request(incident)
    )

    assert allocation.allocation_status == "PARTIALLY_FULFILLED"

    mission = MissionCreationService().create_mission(mission_request)

    # Partial fulfilment does not cancel the mission.
    assert mission.status == "CREATED"
    assert verification.fulfilment_status == "PARTIALLY_FULFILLED"

    # The mission carries the actual allocation, not the requirement.
    assert allocation.required_resources.water == 4000
    assert mission.resources == allocation.allocated_resources.model_dump()
    assert mission.resources["water"] == 2750
    assert mission.resources["food"] == 1900

    # Shortage information is still available upstream.
    assert allocation.remaining_shortage.water == 1250
    assert verification.total_shortage["water"] == 1250

    # Patient present -> ambulance; R005 is BUSY, so R002 is assigned.
    assert mission.required_responder_types == ["AMBULANCE"]

    assignment = assign_first_pickup(mission, mission_request, responders_copy)

    assert assignment.responder_id == "R002"
    assert assignment.target_warehouse_id == "WH001"

    statuses = read_statuses(responders_copy)
    assert statuses["R002"] == "BUSY"
    assert statuses["R005"] == "BUSY"


def test_scenario_c_no_warehouse_pickup_is_not_dispatchable(
    tmp_path,
    responders_copy,
    monkeypatch,
):

    # Same warehouses, but with no stock at all.
    empty_warehouses = tmp_path / "warehouses.json"
    shutil.copyfile(WAREHOUSES_PATH, empty_warehouses)

    warehouses = json.loads(empty_warehouses.read_text(encoding="utf-8"))
    for warehouse in warehouses:
        for item in warehouse["inventory"].values():
            item["available"] = 0
    empty_warehouses.write_text(json.dumps(warehouses), encoding="utf-8")

    incident = build_incident(affected_population=200)

    _, allocation, verification, mission_request = run_to_mission_request(
        incident,
        warehouses_path=empty_warehouses,
    )

    responders_before = responders_copy.read_bytes()

    # NO_WAREHOUSE_PICKUP: allocation produced no pickup, and no warehouse
    # was invented.
    assert allocation.warehouse_allocations == []
    assert mission_request.warehouse_pickups == []
    assert verification.fulfilment_status == "PARTIALLY_FULFILLED"

    mission = MissionCreationService().create_mission(mission_request)
    assert [step.type for step in mission.pickup_sequence] == ["DESTINATION"]

    # MISSION_NOT_DISPATCHABLE: there is no pickup location to target, and
    # Agent Assignment refuses a request without one.
    with pytest.raises(ValidationError):
        AgentAssignmentRequest(
            mission_id=mission.mission_id,
            required_responder_types=mission.required_responder_types,
        )

    monkeypatch.setattr(
        agent_assignment_routes,
        "RESPONDERS_PATH",
        str(responders_copy),
    )

    response = TestClient(app).post(
        "/agent/assign",
        json={
            "mission_id": mission.mission_id,
            "required_responder_types": mission.required_responder_types,
        },
    )

    assert response.status_code == 422

    # No responder was selected or made BUSY.
    assert responders_copy.read_bytes() == responders_before
