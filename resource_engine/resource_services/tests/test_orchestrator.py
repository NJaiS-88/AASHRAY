import json

import pytest
from fastapi.testclient import TestClient

from resource_services.app import app
from resource_services.routes import orchestration_routes
from resource_services.schemas.mission import RouteData
from resource_services.schemas.orchestration import (
    OrchestrationRequest,
    RouteBoundaryResult,
)
from resource_services.services import agent_assignment_service
from resource_services.services.agent_assignment_service import (
    AgentAssignmentService,
)
from resource_services.services.demand_fulfilment_service import (
    DemandFulfilmentService,
)
from resource_services.services.mission_creation_service import (
    MissionCreationService,
)
from resource_services.services.orchestration_service import (
    OrchestrationService,
)
from resource_services.services.resource_allocation_service import (
    ResourceAllocationService,
)
from resource_services.services.resource_requirement_service import (
    ResourceRequirementService,
)
from resource_services.services.route_engine_client import RouteEngineClient


RULES_PATH = "resource_services/config/resource_rules.json"
WAREHOUSES_PATH = "resource_services/database/warehouses.json"

# Allocation requires urgency and a categorical priority. No upstream
# service produces them yet, so tests pass dummy values explicitly.
DUMMY_URGENCY = 0.7
DUMMY_PRIORITY = "HIGH"

INCIDENT_LOCATION = {"latitude": 19.0800, "longitude": 72.8900}

STAGE_METHODS = [
    ("REQUIREMENT", ResourceRequirementService, "calculate"),
    ("ALLOCATION", ResourceAllocationService, "allocate"),
    ("DEMAND_FULFILMENT", DemandFulfilmentService, "verify"),
    ("MISSION_CREATION", MissionCreationService, "create_mission"),
    ("AGENT_ASSIGNMENT", AgentAssignmentService, "assign"),
    ("ROUTE_ENGINE", RouteEngineClient, "plan_route"),
]

ALL_STAGES = [stage for stage, _, _ in STAGE_METHODS]


client = TestClient(app)


# --------------------------------------------------
# Fixtures and helpers
# --------------------------------------------------


@pytest.fixture(autouse=True)
def route_uses_responders_copy(responders_copy, monkeypatch):
    # POST /orchestrate assigns responders; never let it touch the real
    # responders.json.
    monkeypatch.setattr(
        orchestration_routes,
        "RESPONDERS_PATH",
        str(responders_copy),
    )


@pytest.fixture
def orchestrator(responders_copy):
    return OrchestrationService(RULES_PATH, WAREHOUSES_PATH, responders_copy)


@pytest.fixture
def call_log(monkeypatch):
    # Records every call to the real stage methods, in order, then lets the
    # real method run.
    calls = []

    for stage, cls, name in STAGE_METHODS:
        original = getattr(cls, name)

        def recorder(self, *args, _stage=stage, _original=original, **kwargs):
            calls.append((_stage, args, kwargs))
            return _original(self, *args, **kwargs)

        monkeypatch.setattr(cls, name, recorder)

    return calls


def stages_called(calls):
    return [stage for stage, _, _ in calls]


def first_argument(calls, stage):
    for called_stage, args, kwargs in calls:
        if called_stage == stage:
            return args[0] if args else kwargs
    raise AssertionError(f"{stage} was not called")


def build_payload(affected_population=200, patient_present=None):
    payload = {
        "incident_id": "INC-ORCH",
        "incident_type": "FLOOD",
        "location": INCIDENT_LOCATION,
        "locality": {
            "name": "Test Locality",
            "population": 20000,
            "population_density": 12000,
            "affected_population": affected_population,
        },
        "severity": 0.8,
        "estimated_duration_hours": 12,
        "urgency": DUMMY_URGENCY,
        "priority": DUMMY_PRIORITY,
    }

    # Omitted unless given, so the Incident default is exercised.
    if patient_present is not None:
        payload["patient_present"] = patient_present

    return payload


def build_request(**kwargs):
    return OrchestrationRequest(**build_payload(**kwargs))


def read_records(responders_file):
    with open(responders_file, encoding="utf-8") as file:
        return {record["responder_id"]: record for record in json.load(file)}


def warehouse_locations():
    with open(WAREHOUSES_PATH, encoding="utf-8") as file:
        return {w["warehouse_id"]: w["location"] for w in json.load(file)}


def write_empty_warehouses(tmp_path):
    # The real warehouses, with no stock at all.
    with open(WAREHOUSES_PATH, encoding="utf-8") as file:
        warehouses = json.load(file)

    for warehouse in warehouses:
        for item in warehouse["inventory"].values():
            item["available"] = 0

    path = tmp_path / "empty_warehouses.json"
    path.write_text(json.dumps(warehouses), encoding="utf-8")
    return path


def write_all_rescue_trucks_busy(tmp_path, responders_copy):
    records = list(read_records(responders_copy).values())

    for record in records:
        if record["vehicle_type"] == "RESCUE_TRUCK":
            record["status"] = "BUSY"

    path = tmp_path / "rescue_trucks_busy.json"
    path.write_text(json.dumps(records), encoding="utf-8")
    return path


def inject_failure(monkeypatch, cls, name):
    def fail(self, *args, **kwargs):
        raise RuntimeError("injected failure")

    monkeypatch.setattr(cls, name, fail)


def stage_outputs(result):
    return {
        "REQUIREMENT": result.requirement,
        "ALLOCATION": result.allocation,
        "DEMAND_FULFILMENT": result.demand_fulfilment,
        "MISSION_CREATION": result.mission,
        "AGENT_ASSIGNMENT": result.agent_assignment,
        "ROUTE_ENGINE": result.route,
    }


# --------------------------------------------------
# Scenario A - fully fulfilled
# --------------------------------------------------


def test_scenario_a_fully_fulfilled(orchestrator, call_log, responders_copy):

    request = build_request(affected_population=200)

    result = orchestrator.run(request)

    # Every stage ran, in order.
    assert stages_called(call_log) == ALL_STAGES
    assert result.completed_stages == ALL_STAGES

    assert result.status == "ROUTE_ENGINE_NOT_CONNECTED"
    assert result.fulfilment_status == "FULLY_FULFILLED"
    assert result.error is None

    # Requirement -> Allocation: the requirement result is the allocation input.
    allocation_call = first_argument(call_log, "ALLOCATION")
    assert allocation_call["requirements"] == result.requirement.requirements
    assert allocation_call["severity"] == 0.8
    assert allocation_call["urgency"] == DUMMY_URGENCY
    assert allocation_call["priority"] == DUMMY_PRIORITY

    # Allocation -> Demand Fulfilment.
    demand_call = first_argument(call_log, "DEMAND_FULFILMENT")
    assert demand_call.required_resources == (
        result.allocation.required_resources.model_dump()
    )
    assert demand_call.allocated_resources == (
        result.allocation.allocated_resources.model_dump()
    )
    assert result.demand_fulfilment.fulfilment_status == "FULLY_FULFILLED"

    # Allocated resources reach Mission Creation, with the agreed mappings.
    mission_call = first_argument(call_log, "MISSION_CREATION")
    allocated = result.allocation.allocated_resources.model_dump()
    assert mission_call.resources == allocated
    assert mission_call.risk_score == request.severity
    assert mission_call.patient_present is False
    assert mission_call.priority == result.allocation.final_priority_level
    assert mission_call.destination.model_dump() == INCIDENT_LOCATION

    mission = result.mission
    assert mission.status == "CREATED"
    assert mission.resources == allocated

    # Agent Assignment targets the first pickup; R001 becomes BUSY.
    assignment_call = first_argument(call_log, "AGENT_ASSIGNMENT")
    assert assignment_call.mission_id == mission.mission_id
    assert assignment_call.first_warehouse_id == "WH001"
    assert assignment_call.first_warehouse_location.model_dump() == (
        warehouse_locations()["WH001"]
    )
    assert assignment_call.required_responder_types == (
        mission.required_responder_types
    )

    assignment = result.agent_assignment
    assert assignment.responder_id == "R001"
    assert assignment.mission_id == mission.mission_id
    assert read_records(responders_copy)["R001"]["status"] == "BUSY"

    # Route boundary: not connected, no invented route.
    assert result.route.status == "ROUTE_ENGINE_NOT_CONNECTED"
    assert result.route.route is None
    assert result.route.routing_inputs.mission_id == mission.mission_id

    # The ids line up across the stages.
    assert {
        result.incident_id,
        result.requirement.incident_id,
        result.allocation.incident_id,
        result.demand_fulfilment.incident_id,
        mission.incident_id,
    } == {"INC-ORCH"}


# --------------------------------------------------
# Scenario B - partially fulfilled
# --------------------------------------------------


def test_scenario_b_partially_fulfilled(orchestrator, call_log, responders_copy):

    # 2,000 people need 4,000 water; the warehouses hold 2,750.
    result = orchestrator.run(build_request(affected_population=2000))

    allocation = result.allocation
    assert allocation.allocation_status == "PARTIALLY_FULFILLED"
    assert allocation.remaining_shortage.water == 1250
    assert allocation.required_resources.water == 4000

    assert result.demand_fulfilment.fulfilment_status == "PARTIALLY_FULFILLED"
    assert result.fulfilment_status == "PARTIALLY_FULFILLED"

    # The mission is still created, carrying what was actually allocated.
    assert result.mission.status == "CREATED"
    assert result.mission.resources == allocation.allocated_resources.model_dump()
    assert result.mission.resources["water"] == 2750
    assert first_argument(call_log, "MISSION_CREATION").resources["water"] == 2750

    # And still assigned, because there is a valid pickup.
    assert result.agent_assignment.responder_id == "R001"
    assert read_records(responders_copy)["R001"]["status"] == "BUSY"

    assert result.status == "ROUTE_ENGINE_NOT_CONNECTED"


# --------------------------------------------------
# Scenario C - no warehouse pickup
# --------------------------------------------------


def test_scenario_c_no_warehouse_pickup(tmp_path, call_log, responders_copy):

    orchestrator = OrchestrationService(
        RULES_PATH,
        write_empty_warehouses(tmp_path),
        responders_copy,
    )

    before = responders_copy.read_bytes()

    result = orchestrator.run(build_request())

    assert result.status == "MISSION_NOT_DISPATCHABLE"
    assert result.error.error_code == "NO_WAREHOUSE_PICKUP"
    assert result.error.stage == "AGENT_ASSIGNMENT"

    # No warehouse invented: the mission has only the destination step.
    assert result.allocation.warehouse_allocations == []
    assert [step.type for step in result.mission.pickup_sequence] == [
        "DESTINATION"
    ]

    # Agent Assignment and the route boundary were never called.
    assert stages_called(call_log) == ALL_STAGES[:4]
    assert result.agent_assignment is None
    assert result.route is None

    assert responders_copy.read_bytes() == before


# --------------------------------------------------
# Scenario D - no responder available
# --------------------------------------------------


def test_scenario_d_no_responder_available(tmp_path, call_log, responders_copy):

    busy_responders = write_all_rescue_trucks_busy(tmp_path, responders_copy)

    orchestrator = OrchestrationService(
        RULES_PATH,
        WAREHOUSES_PATH,
        busy_responders,
    )

    before = busy_responders.read_bytes()

    result = orchestrator.run(build_request())

    # The mission exists, but nobody is assigned.
    assert result.mission.status == "CREATED"
    assert result.mission.required_responder_types == ["RESCUE_TRUCK"]

    assert result.status == "NO_RESPONDER_AVAILABLE"
    assert result.error.error_code == "NO_RESPONDER_AVAILABLE"
    assert result.error.stage == "AGENT_ASSIGNMENT"
    assert result.agent_assignment is None
    assert result.route is None

    assert "ROUTE_ENGINE" not in stages_called(call_log)
    assert "AGENT_ASSIGNMENT" not in result.completed_stages
    assert busy_responders.read_bytes() == before


# --------------------------------------------------
# Scenario E / F - patient present / absent
# --------------------------------------------------


def test_scenario_e_patient_present(orchestrator, call_log, responders_copy):

    result = orchestrator.run(build_request(patient_present=True))

    assert first_argument(call_log, "MISSION_CREATION").patient_present is True

    # Existing responder-type rule: a patient means an ambulance.
    assert result.mission.required_responder_types == ["AMBULANCE"]

    # R005 is BUSY, so R002 is the ambulance assigned.
    assert result.agent_assignment.responder_id == "R002"

    records = read_records(responders_copy)
    assert records["R002"]["status"] == "BUSY"
    assert records["R001"]["status"] == "AVAILABLE"


def test_scenario_f_patient_absent_defaults_to_false(
    orchestrator,
    call_log,
    responders_copy,
):

    payload = build_payload()
    assert "patient_present" not in payload

    request = OrchestrationRequest(**payload)
    assert request.patient_present is False

    result = orchestrator.run(request)

    assert first_argument(call_log, "MISSION_CREATION").patient_present is False
    assert result.mission.required_responder_types == ["RESCUE_TRUCK"]
    assert result.agent_assignment.responder_id == "R001"


# --------------------------------------------------
# Scenario G - a stage fails
# --------------------------------------------------


@pytest.mark.parametrize(
    "failing_stage",
    [
        "REQUIREMENT",
        "ALLOCATION",
        "DEMAND_FULFILMENT",
        "MISSION_CREATION",
        "AGENT_ASSIGNMENT",
    ],
)
def test_scenario_g_stage_failure_stops_the_pipeline(
    failing_stage,
    orchestrator,
    call_log,
    monkeypatch,
    responders_copy,
):

    _, cls, name = next(m for m in STAGE_METHODS if m[0] == failing_stage)
    inject_failure(monkeypatch, cls, name)

    before = responders_copy.read_bytes()

    result = orchestrator.run(build_request())

    assert result.status == "FAILED"
    assert result.error.stage == failing_stage
    assert result.error.error_code == "STAGE_FAILED"
    assert result.error.message == "RuntimeError: injected failure"

    # Earlier stages ran and kept their output; later stages never ran.
    index = ALL_STAGES.index(failing_stage)
    assert stages_called(call_log) == ALL_STAGES[:index]
    assert result.completed_stages == ALL_STAGES[:index]

    for position, (stage, output) in enumerate(stage_outputs(result).items()):
        assert (output is not None) == (position < index), stage

    assert responders_copy.read_bytes() == before


def test_scenario_g_assignment_persist_failure_reports_no_assignment(
    orchestrator,
    monkeypatch,
    responders_copy,
):

    # A real failure inside Agent Assignment: BUSY cannot be saved.
    def failing_replace(source, destination):
        raise OSError("disk is read-only")

    monkeypatch.setattr(agent_assignment_service.os, "replace", failing_replace)

    before = responders_copy.read_bytes()

    result = orchestrator.run(build_request())

    assert result.status == "FAILED"
    assert result.error.stage == "AGENT_ASSIGNMENT"
    assert result.error.message.startswith("ResponderStatusError")

    # The mission exists, but no assignment is reported.
    assert result.mission is not None
    assert result.agent_assignment is None
    assert result.route is None
    assert responders_copy.read_bytes() == before


# --------------------------------------------------
# Scenario H - Route Engine boundary
# --------------------------------------------------


def test_scenario_h_route_engine_not_connected(orchestrator, responders_copy):

    result = orchestrator.run(build_request(affected_population=2000))

    assert result.status == "ROUTE_ENGINE_NOT_CONNECTED"
    assert result.agent_assignment.assignment_status == "ASSIGNED"

    route = result.route
    assert route.status == "ROUTE_ENGINE_NOT_CONNECTED"

    # No route data is invented, and Mission Creation's route is unchanged.
    assert route.route is None
    assert result.mission.route.status == "NOT_AVAILABLE"
    assert result.mission.route.coordinates == []

    # The routing information is prepared for the future integration.
    inputs = route.routing_inputs
    records = read_records(responders_copy)
    locations = warehouse_locations()
    pickup_ids = [
        step.warehouse_id
        for step in result.mission.pickup_sequence
        if step.type == "WAREHOUSE"
    ]

    assert inputs.responder_id == "R001"
    assert inputs.responder_location.model_dump() == records["R001"]["location"]
    assert [pickup.warehouse_id for pickup in inputs.pickups] == pickup_ids
    assert [p.location.model_dump() for p in inputs.pickups] == [
        locations[warehouse_id] for warehouse_id in pickup_ids
    ]
    assert inputs.destination.model_dump() == INCIDENT_LOCATION

    # The responder stays BUSY: not connected does not undo the assignment.
    assert records["R001"]["status"] == "BUSY"


def test_scenario_h_route_engine_error_keeps_the_assignment(
    responders_copy,
):

    class FailingRouteEngineClient(RouteEngineClient):
        def plan_route(self, routing_inputs):
            raise ConnectionError("route engine unreachable")

    orchestrator = OrchestrationService(
        RULES_PATH,
        WAREHOUSES_PATH,
        responders_copy,
        route_engine_client=FailingRouteEngineClient(),
    )

    result = orchestrator.run(build_request())

    assert result.status == "FAILED"
    assert result.error.stage == "ROUTE_ENGINE"
    assert result.error.message == "ConnectionError: route engine unreachable"

    # The assignment stands and the responder stays BUSY.
    assert result.agent_assignment.responder_id == "R001"
    assert read_records(responders_copy)["R001"]["status"] == "BUSY"


def test_route_engine_boundary_is_replaceable(responders_copy):

    # A stand-in for a future connected adapter. It is not the real Route
    # Engine; it only shows that replacing the client yields COMPLETED.
    class PlannedRouteClient(RouteEngineClient):
        def plan_route(self, routing_inputs):
            return RouteBoundaryResult(
                status="ROUTE_PLANNED",
                routing_inputs=routing_inputs,
                route=RouteData(
                    status="AVAILABLE",
                    coordinates=[
                        routing_inputs.responder_location,
                        routing_inputs.destination,
                    ],
                ),
            )

    orchestrator = OrchestrationService(
        RULES_PATH,
        WAREHOUSES_PATH,
        responders_copy,
        route_engine_client=PlannedRouteClient(),
    )

    result = orchestrator.run(build_request())

    assert result.status == "COMPLETED"
    assert result.route.status == "ROUTE_PLANNED"
    assert result.route.route.status == "AVAILABLE"


# --------------------------------------------------
# API: POST /orchestrate
# --------------------------------------------------


def test_api_orchestrates_through_agent_assignment(responders_copy):

    response = client.post("/orchestrate", json=build_payload())

    assert response.status_code == 200

    body = response.json()
    assert body["status"] == "ROUTE_ENGINE_NOT_CONNECTED"
    assert body["completed_stages"] == ALL_STAGES
    assert body["agent_assignment"]["responder_id"] == "R001"
    assert body["route"]["status"] == "ROUTE_ENGINE_NOT_CONNECTED"
    assert body["route"]["route"] is None
    assert body["mission"]["resources"] == body["allocation"]["allocated_resources"]

    assert read_records(responders_copy)["R001"]["status"] == "BUSY"


def test_api_no_warehouse_pickup_returns_409(tmp_path, monkeypatch):

    monkeypatch.setattr(
        orchestration_routes,
        "WAREHOUSES_PATH",
        str(write_empty_warehouses(tmp_path)),
    )

    response = client.post("/orchestrate", json=build_payload())

    assert response.status_code == 409

    body = response.json()
    assert body["status"] == "MISSION_NOT_DISPATCHABLE"
    assert body["error"]["error_code"] == "NO_WAREHOUSE_PICKUP"
    assert body["mission"] is not None
    assert body["agent_assignment"] is None


def test_api_no_responder_returns_409(tmp_path, monkeypatch, responders_copy):

    monkeypatch.setattr(
        orchestration_routes,
        "RESPONDERS_PATH",
        str(write_all_rescue_trucks_busy(tmp_path, responders_copy)),
    )

    response = client.post("/orchestrate", json=build_payload())

    assert response.status_code == 409

    body = response.json()
    assert body["status"] == "NO_RESPONDER_AVAILABLE"
    assert body["error"]["error_code"] == "NO_RESPONDER_AVAILABLE"
    assert body["mission"]["status"] == "CREATED"


def test_api_stage_failure_returns_500_with_partial_result(monkeypatch):

    inject_failure(monkeypatch, ResourceAllocationService, "allocate")

    response = client.post("/orchestrate", json=build_payload())

    assert response.status_code == 500

    body = response.json()
    assert body["status"] == "FAILED"
    assert body["error"]["stage"] == "ALLOCATION"
    assert body["requirement"] is not None
    assert body["mission"] is None


def test_api_rejects_invalid_orchestration_input():

    valid = build_payload()

    missing_urgency = {k: v for k, v in valid.items() if k != "urgency"}
    missing_priority = {k: v for k, v in valid.items() if k != "priority"}

    for payload in [
        missing_urgency,
        missing_priority,
        dict(valid, priority="MEDIUM"),
        dict(valid, urgency=1.5),
        dict(valid, patient_present="maybe"),
    ]:
        assert client.post("/orchestrate", json=payload).status_code == 422


def test_orchestrate_route_registered_with_existing_routes():

    paths = app.openapi()["paths"]

    for path, method in [
        ("/orchestrate", "post"),
        ("/resource/allocate", "post"),
        ("/resource/allocate/batch", "post"),
        ("/demand/verify", "post"),
        ("/mission/create", "post"),
        ("/agent/assign", "post"),
        ("/health", "get"),
    ]:
        assert method in paths[path]
