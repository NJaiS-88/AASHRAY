import json

import pytest
from fastapi.testclient import TestClient

from resource_services.app import app
from resource_services.routes import agent_assignment_routes, mission_routes
from resource_services.schemas.agent_assignment import AgentAssignmentRequest
from resource_services.schemas.mission import MissionCreationRequest
from resource_services.schemas.orchestration import OrchestrationRequest
from resource_services.services.agent_assignment_service import (
    AgentAssignmentService,
    ResponderStatusError,
)
from resource_services.services.mission_creation_service import (
    MissionCreationService,
)
from resource_services.services.mission_lifecycle_service import (
    MissionLifecycleService,
)
from resource_services.services.mission_store import (
    MissionStateError,
    MissionStore,
)
from resource_services.services.orchestration_service import (
    OrchestrationService,
)
from resource_services.services.route_engine_client import RouteEngineClient


# Responder lifecycle:
#   assign   -> responder AVAILABLE -> BUSY, mission ASSIGNED
#   complete -> responder BUSY -> AVAILABLE, mission COMPLETED
#   cancel   -> responder BUSY -> AVAILABLE, mission CANCELLED
# Every test uses temporary responders/missions files.


RULES_PATH = "resource_services/config/resource_rules.json"
WAREHOUSES_PATH = "resource_services/database/warehouses.json"

# WH001 and WH002 in database/warehouses.json.
WH001_LOCATION = {"latitude": 19.0760, "longitude": 72.8777}
WH002_LOCATION = {"latitude": 19.1100, "longitude": 72.8500}


client = TestClient(app)


def build_responder(responder_id, vehicle_type, location, status="AVAILABLE"):
    return {
        "responder_id": responder_id,
        "name": f"Test Responder {responder_id}",
        "vehicle_type": vehicle_type,
        "location": dict(location),
        "status": status,
    }


@pytest.fixture
def responders_file(tmp_path):
    # T-1 sits on WH001 and T-2 on WH002, so a mission whose first pickup
    # is WH001 gets T-1 and one starting at WH002 gets T-2.
    path = tmp_path / "responders.json"
    path.write_text(
        json.dumps(
            [
                build_responder("T-1", "RESCUE_TRUCK", WH001_LOCATION),
                build_responder("T-2", "RESCUE_TRUCK", WH002_LOCATION),
                build_responder("T-3", "AMBULANCE", WH001_LOCATION),
            ]
        ),
        encoding="utf-8",
    )
    return path


@pytest.fixture(autouse=True)
def routes_use_temporary_files(responders_file, monkeypatch):
    # Both routes must point at the same responders file (missions.json is
    # derived next to it), never at the real database.
    monkeypatch.setattr(
        agent_assignment_routes, "RESPONDERS_PATH", str(responders_file)
    )
    monkeypatch.setattr(mission_routes, "RESPONDERS_PATH", str(responders_file))


def read_records(responders_path):
    with open(responders_path, encoding="utf-8") as file:
        return {record["responder_id"]: record for record in json.load(file)}


def statuses(responders_path):
    return {
        responder_id: record["status"]
        for responder_id, record in read_records(responders_path).items()
    }


def missions_path(responders_path):
    return responders_path.with_name("missions.json")


def read_missions(responders_path):
    path = missions_path(responders_path)
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as file:
        return {record["mission_id"]: record for record in json.load(file)}


def assign(responders_path, mission_id, location=WH001_LOCATION, types=None):
    return AgentAssignmentService(responders_path).assign(
        AgentAssignmentRequest(
            mission_id=mission_id,
            required_responder_types=types or ["RESCUE_TRUCK"],
            first_warehouse_location=location,
        )
    )


def lifecycle(responders_path):
    return MissionLifecycleService(responders_path)


def assign_payload(mission_id, location=WH001_LOCATION):
    return {
        "mission_id": mission_id,
        "required_responder_types": ["RESCUE_TRUCK"],
        "first_warehouse_location": location,
    }


# --------------------------------------------------
# Assignment: responder BUSY, mission ASSIGNED
# --------------------------------------------------


def test_assignment_makes_responder_busy_and_records_the_mission(
    responders_file,
):
    result = assign(responders_file, "MIS-A")

    assert result.responder_id == "T-1"
    assert statuses(responders_file)["T-1"] == "BUSY"

    mission = read_missions(responders_file)["MIS-A"]
    assert mission["status"] == "ASSIGNED"
    assert [item["responder_id"] for item in mission["assignments"]] == ["T-1"]
    assert mission["assignments"][0]["assignment_id"] == result.assignment_id
    assert mission["closed_at"] is None


def test_api_assignment_records_the_mission(responders_file):
    response = client.post("/agent/assign", json=assign_payload("MIS-API"))

    assert response.status_code == 200
    assert response.json()["responder_id"] == "T-1"
    assert statuses(responders_file)["T-1"] == "BUSY"
    assert read_missions(responders_file)["MIS-API"]["status"] == "ASSIGNED"


def test_responder_stays_busy_while_mission_is_active(responders_file):
    assign(responders_file, "MIS-A")

    # Other lifecycle activity does not touch an active mission's responder.
    assign(responders_file, "MIS-B", location=WH002_LOCATION)
    lifecycle(responders_file).complete("MIS-B")

    with pytest.raises(MissionStateError):
        lifecycle(responders_file).complete("MIS-UNKNOWN")

    assert statuses(responders_file)["T-1"] == "BUSY"
    assert read_missions(responders_file)["MIS-A"]["status"] == "ASSIGNED"


# --------------------------------------------------
# Completion and cancellation release the same responder
# --------------------------------------------------


def test_completion_releases_the_assigned_responder(responders_file):
    assign(responders_file, "MIS-A")

    result = lifecycle(responders_file).complete("MIS-A")

    assert result.status == "COMPLETED"
    assert result.previous_status == "ASSIGNED"
    assert result.responder_ids == ["T-1"]
    assert [r.responder_id for r in result.released_responders] == ["T-1"]
    assert result.released_responders[0].status == "AVAILABLE"

    assert statuses(responders_file)["T-1"] == "AVAILABLE"

    mission = read_missions(responders_file)["MIS-A"]
    assert mission["status"] == "COMPLETED"
    assert mission["closed_at"] is not None


def test_cancellation_releases_the_assigned_responder(responders_file):
    assign(responders_file, "MIS-A")

    result = lifecycle(responders_file).cancel("MIS-A")

    assert result.status == "CANCELLED"
    assert result.previous_status == "ASSIGNED"
    assert [r.responder_id for r in result.released_responders] == ["T-1"]

    assert statuses(responders_file)["T-1"] == "AVAILABLE"
    assert read_missions(responders_file)["MIS-A"]["status"] == "CANCELLED"


@pytest.mark.parametrize("operation", ["complete", "cancel"])
def test_release_preserves_location(responders_file, operation):
    original = read_records(responders_file)["T-1"]

    assign(responders_file, "MIS-A")
    assert read_records(responders_file)["T-1"]["location"] == original["location"]

    result = getattr(lifecycle(responders_file), operation)("MIS-A")

    released = read_records(responders_file)["T-1"]
    assert released["location"] == original["location"]
    assert result.released_responders[0].location.model_dump() == original["location"]

    # Only status changed over the whole lifecycle.
    assert released == original


def test_released_responder_can_be_assigned_again(responders_file):
    assign(responders_file, "MIS-A")
    lifecycle(responders_file).complete("MIS-A")

    assert assign(responders_file, "MIS-B").responder_id == "T-1"
    assert statuses(responders_file)["T-1"] == "BUSY"


# --------------------------------------------------
# The correct responder, never another mission's
# --------------------------------------------------


def test_two_missions_release_their_own_responders(responders_file):
    assert assign(responders_file, "MIS-A").responder_id == "T-1"
    assert assign(responders_file, "MIS-B", location=WH002_LOCATION).responder_id == "T-2"

    result = lifecycle(responders_file).complete("MIS-A")

    assert [r.responder_id for r in result.released_responders] == ["T-1"]
    assert statuses(responders_file) == {
        "T-1": "AVAILABLE",
        "T-2": "BUSY",
        "T-3": "AVAILABLE",
    }

    result = lifecycle(responders_file).cancel("MIS-B")

    assert [r.responder_id for r in result.released_responders] == ["T-2"]
    assert statuses(responders_file)["T-2"] == "AVAILABLE"


def test_completing_a_closed_mission_again_never_releases_its_former_responder(
    responders_file,
):
    # T-1 serves MIS-A, is released, then serves MIS-B. Completing MIS-A
    # again must not free T-1 from MIS-B.
    assign(responders_file, "MIS-A")
    lifecycle(responders_file).complete("MIS-A")

    assert assign(responders_file, "MIS-B").responder_id == "T-1"

    result = lifecycle(responders_file).complete("MIS-A")

    assert result.released_responders == []
    assert statuses(responders_file)["T-1"] == "BUSY"
    assert read_missions(responders_file)["MIS-B"]["status"] == "ASSIGNED"


def test_responder_of_another_active_mission_is_never_released(responders_file):
    # Inconsistent state: T-1 was released outside the lifecycle and then
    # assigned to MIS-B while MIS-A still lists it. Completing MIS-A must
    # leave T-1 BUSY for MIS-B.
    assign(responders_file, "MIS-A")
    AgentAssignmentService(responders_file).release_responder("T-1")
    assign(responders_file, "MIS-B")

    result = lifecycle(responders_file).complete("MIS-A")

    assert result.status == "COMPLETED"
    assert result.released_responders == []
    assert statuses(responders_file)["T-1"] == "BUSY"

    # MIS-B still releases it.
    result = lifecycle(responders_file).complete("MIS-B")
    assert [r.responder_id for r in result.released_responders] == ["T-1"]


def test_busy_responder_without_a_mission_record_is_never_released(
    responders_copy,
):
    # The real data has R005 BUSY with no mission recorded for it. BUSY
    # alone says nothing about which mission a responder serves, so
    # completing an unrelated mission must leave R005 BUSY.
    assert statuses(responders_copy)["R005"] == "BUSY"

    assert assign(responders_copy, "MIS-A").responder_id == "R001"

    result = MissionLifecycleService(responders_copy).complete("MIS-A")

    assert [r.responder_id for r in result.released_responders] == ["R001"]
    assert statuses(responders_copy)["R005"] == "BUSY"
    assert statuses(responders_copy)["R001"] == "AVAILABLE"


def test_every_responder_assigned_to_the_mission_is_released(responders_file):
    # /agent/assign may be called again for the same mission (existing
    # behaviour); each responder it assigns is recorded and released.
    assign(responders_file, "MIS-A")
    assign(responders_file, "MIS-A")
    assign(responders_file, "MIS-OTHER", types=["AMBULANCE"])

    mission = read_missions(responders_file)["MIS-A"]
    assert [item["responder_id"] for item in mission["assignments"]] == ["T-1", "T-2"]

    result = lifecycle(responders_file).complete("MIS-A")

    assert sorted(r.responder_id for r in result.released_responders) == ["T-1", "T-2"]
    assert statuses(responders_file) == {
        "T-1": "AVAILABLE",
        "T-2": "AVAILABLE",
        "T-3": "BUSY",
    }


# --------------------------------------------------
# Idempotency and final states
# --------------------------------------------------


@pytest.mark.parametrize(
    "operation, final_status",
    [("complete", "COMPLETED"), ("cancel", "CANCELLED")],
)
def test_closing_a_mission_twice_is_safe(responders_file, operation, final_status):
    assign(responders_file, "MIS-A")
    getattr(lifecycle(responders_file), operation)("MIS-A")

    responders_before = responders_file.read_bytes()
    missions_before = missions_path(responders_file).read_bytes()

    result = getattr(lifecycle(responders_file), operation)("MIS-A")

    assert result.status == final_status
    assert result.previous_status == final_status
    assert result.responder_ids == ["T-1"]
    assert result.released_responders == []

    assert responders_file.read_bytes() == responders_before
    assert missions_path(responders_file).read_bytes() == missions_before


@pytest.mark.parametrize(
    "first, second, closed_status",
    [("complete", "cancel", "COMPLETED"), ("cancel", "complete", "CANCELLED")],
)
def test_closed_mission_cannot_be_closed_the_other_way(
    responders_file,
    first,
    second,
    closed_status,
):
    assign(responders_file, "MIS-A")
    getattr(lifecycle(responders_file), first)("MIS-A")
    assign(responders_file, "MIS-B")

    responders_before = responders_file.read_bytes()
    missions_before = missions_path(responders_file).read_bytes()

    with pytest.raises(MissionStateError) as raised:
        getattr(lifecycle(responders_file), second)("MIS-A")

    assert raised.value.error_code == "MISSION_ALREADY_CLOSED"
    assert closed_status in str(raised.value)

    assert responders_file.read_bytes() == responders_before
    assert missions_path(responders_file).read_bytes() == missions_before


@pytest.mark.parametrize("operation", ["complete", "cancel"])
def test_closed_mission_cannot_be_assigned_again(responders_file, operation):
    assign(responders_file, "MIS-A")
    getattr(lifecycle(responders_file), operation)("MIS-A")

    responders_before = responders_file.read_bytes()

    with pytest.raises(MissionStateError) as raised:
        assign(responders_file, "MIS-A")

    assert raised.value.error_code == "MISSION_ALREADY_CLOSED"
    assert responders_file.read_bytes() == responders_before

    response = client.post("/agent/assign", json=assign_payload("MIS-A"))

    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "MISSION_ALREADY_CLOSED"
    assert responders_file.read_bytes() == responders_before


# --------------------------------------------------
# Missions without an assigned responder release nothing
# --------------------------------------------------


@pytest.mark.parametrize("operation", ["complete", "cancel"])
def test_mission_without_assignment_releases_nothing(
    responders_file,
    operation,
):
    # A real CREATED mission that never got a responder, while another
    # mission's responder is BUSY.
    assign(responders_file, "MIS-OTHER")

    created = MissionCreationService().create_mission(
        MissionCreationRequest(
            incident_id="INC-1",
            destination={"latitude": 19.0596, "longitude": 72.8295},
            risk_score=0.5,
            patient_present=False,
            resources={"water": 10},
            warehouse_pickups=[
                {"warehouse_id": "WH001", "location": WH001_LOCATION, "supplies": {"water": 10}}
            ],
        )
    )
    assert created.status == "CREATED"

    responders_before = responders_file.read_bytes()
    missions_before = missions_path(responders_file).read_bytes()

    with pytest.raises(MissionStateError) as raised:
        getattr(lifecycle(responders_file), operation)(created.mission_id)

    assert raised.value.error_code == "MISSION_NOT_ASSIGNED"
    assert responders_file.read_bytes() == responders_before
    assert missions_path(responders_file).read_bytes() == missions_before


def test_mission_without_assignment_and_no_missions_file(responders_file):
    responders_before = responders_file.read_bytes()

    with pytest.raises(MissionStateError) as raised:
        lifecycle(responders_file).complete("MIS-NEVER-ASSIGNED")

    assert raised.value.error_code == "MISSION_NOT_ASSIGNED"
    assert responders_file.read_bytes() == responders_before
    assert not missions_path(responders_file).exists()


def test_orchestrator_without_responder_records_no_mission(tmp_path):
    # NO_RESPONDER_AVAILABLE: the mission stays CREATED, so completing it
    # releases nothing.
    responders_path = tmp_path / "responders.json"
    responders_path.write_text(
        json.dumps([build_responder("T-BUSY", "RESCUE_TRUCK", WH001_LOCATION, "BUSY")]),
        encoding="utf-8",
    )

    result = OrchestrationService(
        RULES_PATH, WAREHOUSES_PATH, responders_path
    ).run(build_orchestration_request())

    assert result.status == "NO_RESPONDER_AVAILABLE"
    assert read_missions(responders_path) == {}

    with pytest.raises(MissionStateError) as raised:
        MissionLifecycleService(responders_path).complete(result.mission.mission_id)

    assert raised.value.error_code == "MISSION_NOT_ASSIGNED"
    assert statuses(responders_path) == {"T-BUSY": "BUSY"}


# --------------------------------------------------
# Route Engine outcomes do not release the responder
# --------------------------------------------------


def build_orchestration_request():
    return OrchestrationRequest(
        incident_id="INC-LIFECYCLE",
        incident_type="FLOOD",
        location={"latitude": 19.0596, "longitude": 72.8295},
        locality={
            "name": "Test Locality",
            "population": 20000,
            "population_density": 12000,
            "affected_population": 200,
        },
        severity=0.8,
        estimated_duration_hours=12,
        urgency=0.9,
        priority="HIGH",
    )


class FailingRouteEngineClient(RouteEngineClient):
    def plan_route(self, routing_inputs):
        raise RuntimeError("route engine exploded")


@pytest.mark.parametrize(
    "route_engine_client, orchestration_status",
    [
        (RouteEngineClient(base_url=""), "ROUTE_ENGINE_NOT_CONNECTED"),
        (FailingRouteEngineClient(base_url="http://unused"), "FAILED"),
    ],
)
def test_route_engine_outcome_keeps_mission_assigned_until_closed(
    responders_file,
    route_engine_client,
    orchestration_status,
):
    result = OrchestrationService(
        RULES_PATH,
        WAREHOUSES_PATH,
        responders_file,
        route_engine_client=route_engine_client,
    ).run(build_orchestration_request())

    assert result.status == orchestration_status

    mission_id = result.mission.mission_id
    responder_id = result.agent_assignment.responder_id

    # Routing did not release the responder or close the mission.
    assert statuses(responders_file)[responder_id] == "BUSY"
    mission = read_missions(responders_file)[mission_id]
    assert mission["status"] == "ASSIGNED"
    assert [item["responder_id"] for item in mission["assignments"]] == [responder_id]

    # Only the lifecycle operation releases it.
    closed = lifecycle(responders_file).cancel(mission_id)

    assert [r.responder_id for r in closed.released_responders] == [responder_id]
    assert statuses(responders_file)[responder_id] == "AVAILABLE"


# --------------------------------------------------
# Failure to record the assignment
# --------------------------------------------------


def test_unrecorded_assignment_is_rolled_back(responders_file, monkeypatch):
    def failing_save(self, record):
        raise OSError("disk is read-only")

    monkeypatch.setattr(MissionStore, "save", failing_save)

    with pytest.raises(ResponderStatusError) as raised:
        assign(responders_file, "MIS-A")

    assert "returned to AVAILABLE" in str(raised.value)
    assert statuses(responders_file)["T-1"] == "AVAILABLE"
    assert read_missions(responders_file) == {}

    response = client.post("/agent/assign", json=assign_payload("MIS-A"))

    assert response.status_code == 500
    assert response.json()["detail"].startswith("Agent assignment failed:")
    assert statuses(responders_file)["T-1"] == "AVAILABLE"


# --------------------------------------------------
# API: POST /mission/{mission_id}/complete | /cancel
# --------------------------------------------------


@pytest.mark.parametrize(
    "operation, final_status",
    [("complete", "COMPLETED"), ("cancel", "CANCELLED")],
)
def test_api_closes_mission_and_releases_responder(
    responders_file,
    operation,
    final_status,
):
    assert client.post("/agent/assign", json=assign_payload("MIS-API")).status_code == 200
    location = read_records(responders_file)["T-1"]["location"]

    response = client.post(f"/mission/MIS-API/{operation}")

    assert response.status_code == 200
    body = response.json()
    assert body["mission_id"] == "MIS-API"
    assert body["status"] == final_status
    assert body["previous_status"] == "ASSIGNED"
    assert body["responder_ids"] == ["T-1"]
    assert body["released_responders"][0]["responder_id"] == "T-1"
    assert body["released_responders"][0]["status"] == "AVAILABLE"
    assert body["released_responders"][0]["location"] == location

    assert statuses(responders_file)["T-1"] == "AVAILABLE"

    # Repeating it is a safe no-op.
    again = client.post(f"/mission/MIS-API/{operation}")

    assert again.status_code == 200
    assert again.json()["previous_status"] == final_status
    assert again.json()["released_responders"] == []


def test_api_returns_409_for_lifecycle_conflicts(responders_file):
    unassigned = client.post("/mission/MIS-NONE/complete")

    assert unassigned.status_code == 409
    assert unassigned.json()["detail"]["error"] == "MISSION_NOT_ASSIGNED"

    client.post("/agent/assign", json=assign_payload("MIS-API"))
    client.post("/mission/MIS-API/cancel")

    conflict = client.post("/mission/MIS-API/complete")

    assert conflict.status_code == 409
    assert conflict.json()["detail"]["error"] == "MISSION_ALREADY_CLOSED"
    assert statuses(responders_file)["T-1"] == "AVAILABLE"


def test_api_returns_500_for_malformed_missions_file(responders_file):
    missions_path(responders_file).write_text("{not json", encoding="utf-8")

    response = client.post("/mission/MIS-A/complete")

    assert response.status_code == 500
    assert response.json()["detail"].startswith("Mission completion failed:")


def test_lifecycle_routes_are_registered_with_existing_routes():
    paths = app.openapi()["paths"]

    for path, method in [
        ("/mission/{mission_id}/complete", "post"),
        ("/mission/{mission_id}/cancel", "post"),
        ("/mission/create", "post"),
        ("/agent/assign", "post"),
        ("/orchestrate", "post"),
    ]:
        assert method in paths[path]
