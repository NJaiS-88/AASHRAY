import json
import math

import pytest
from fastapi.testclient import TestClient

from resource_services.app import app
from resource_services.routes import agent_assignment_routes
from resource_services.schemas.agent_assignment import (
    AgentAssignmentRequest,
    AgentAssignmentResult,
)
from resource_services.services import agent_assignment_service
from resource_services.services.agent_assignment_service import (
    EARTH_RADIUS_KM,
    AgentAssignmentService,
    NoResponderAvailableError,
    ResponderStatusError,
    haversine_km,
)


# Assignment now persists responder status. Every test works on a
# temporary copy of the real responders.json (conftest.responders_copy);
# the real file is never written.

# WH001 in database/warehouses.json.
WH001_LOCATION = {
    "latitude": 19.0760,
    "longitude": 72.8777,
}


client = TestClient(app)


@pytest.fixture(autouse=True)
def route_uses_responders_copy(responders_copy, monkeypatch):
    # POST /agent/assign writes responder status, so the route must never
    # point at the real responders.json during tests.
    monkeypatch.setattr(
        agent_assignment_routes,
        "RESPONDERS_PATH",
        str(responders_copy),
    )


def read_records(responders_file):
    with open(responders_file, encoding="utf-8") as file:
        return {record["responder_id"]: record for record in json.load(file)}


def build_responder(
    responder_id,
    vehicle_type,
    latitude,
    longitude,
    status="AVAILABLE",
):
    return {
        "responder_id": responder_id,
        "name": f"Test Responder {responder_id}",
        "vehicle_type": vehicle_type,
        "location": {
            "latitude": latitude,
            "longitude": longitude,
        },
        "status": status,
    }


def write_responders(tmp_path, responders):
    responders_file = tmp_path / "responders.json"

    responders_file.write_text(
        json.dumps(responders),
        encoding="utf-8",
    )

    return responders_file


def build_request(
    required_responder_types,
    location=None,
    warehouse_id="WH001",
):
    return AgentAssignmentRequest(
        mission_id="MIS-TEST001",
        required_responder_types=required_responder_types,
        first_warehouse_location=location or WH001_LOCATION,
        first_warehouse_id=warehouse_id,
    )


# TEST 1 - Correct responder type


def test_assigns_closest_rescue_truck_to_first_warehouse(responders_copy):

    service = AgentAssignmentService(responders_copy)

    result = service.assign(build_request(["RESCUE_TRUCK"]))

    assert result.responder_id == "R001"
    assert result.responder_type == "RESCUE_TRUCK"
    assert result.assignment_status == "ASSIGNED"


def test_wrong_vehicle_type_is_never_assigned_even_when_closest(responders_copy):

    service = AgentAssignmentService(responders_copy)

    # Target placed exactly on ambulance R002 (distance 0).
    result = service.assign(
        build_request(
            ["RESCUE_TRUCK"],
            location={"latitude": 19.0600, "longitude": 72.9000},
        )
    )

    assert result.responder_type == "RESCUE_TRUCK"
    assert result.responder_id != "R002"


def test_every_required_type_returns_that_type(responders_copy):

    service = AgentAssignmentService(responders_copy)

    for vehicle_type in ("RESCUE_TRUCK", "AMBULANCE", "FIRE_TRUCK"):

        result = service.assign(build_request([vehicle_type]))

        assert result.responder_type == vehicle_type


def test_multiple_required_types_select_closest_of_any_listed_type(tmp_path):

    responders_file = write_responders(
        tmp_path,
        [
            build_responder("T-RESCUE", "RESCUE_TRUCK", 19.2000, 72.8777),
            build_responder("T-AMBULANCE", "AMBULANCE", 19.0800, 72.8777),
            build_responder("T-FIRE", "FIRE_TRUCK", 19.0761, 72.8777),
        ],
    )

    service = AgentAssignmentService(responders_file)

    result = service.assign(build_request(["RESCUE_TRUCK", "AMBULANCE"]))

    # The fire truck is closest but was not requested.
    assert result.responder_id == "T-AMBULANCE"


# TEST 2 - BUSY responder excluded


def test_busy_responder_is_excluded_even_when_closest(tmp_path):

    responders_file = write_responders(
        tmp_path,
        [
            build_responder(
                "T-NEAR-BUSY", "RESCUE_TRUCK", 19.0760, 72.8777, "BUSY"
            ),
            build_responder("T-FAR-AVAILABLE", "RESCUE_TRUCK", 19.2000, 72.9500),
        ],
    )

    service = AgentAssignmentService(responders_file)

    result = service.assign(build_request(["RESCUE_TRUCK"]))

    assert result.responder_id == "T-FAR-AVAILABLE"


def test_busy_production_ambulance_is_excluded(responders_copy):

    service = AgentAssignmentService(responders_copy)

    # Target placed exactly on R005, the BUSY ambulance.
    result = service.assign(
        build_request(
            ["AMBULANCE"],
            location={"latitude": 19.0300, "longitude": 72.8700},
        )
    )

    assert result.responder_id == "R002"


# TEST 3 - Closest responder selected


def test_closest_available_responder_is_selected(tmp_path):

    responders = [
        build_responder("T-FAR", "RESCUE_TRUCK", 19.3000, 72.8777),
        build_responder("T-NEAR", "RESCUE_TRUCK", 19.0800, 72.8777),
        build_responder("T-MID", "RESCUE_TRUCK", 19.1500, 72.8777),
    ]

    service = AgentAssignmentService(write_responders(tmp_path, responders))

    result = service.assign(build_request(["RESCUE_TRUCK"]))

    assert result.responder_id == "T-NEAR"

    expected_distance = haversine_km(19.0800, 72.8777, 19.0760, 72.8777)

    assert result.distance_to_warehouse_km == round(expected_distance, 3)

    assert result.responder_location.latitude == 19.0800
    assert result.responder_location.longitude == 72.8777


def test_selection_target_is_the_first_warehouse(tmp_path):

    responders_file = write_responders(
        tmp_path,
        [
            build_responder("T-NORTH", "RESCUE_TRUCK", 19.3000, 72.8777),
            build_responder("T-SOUTH", "RESCUE_TRUCK", 18.9000, 72.8777),
        ],
    )

    service = AgentAssignmentService(responders_file)

    north_pickup = service.assign(
        build_request(
            ["RESCUE_TRUCK"],
            location={"latitude": 19.2500, "longitude": 72.8777},
        )
    )
    south_pickup = service.assign(
        build_request(
            ["RESCUE_TRUCK"],
            location={"latitude": 18.9500, "longitude": 72.8777},
        )
    )

    assert north_pickup.responder_id == "T-NORTH"
    assert south_pickup.responder_id == "T-SOUTH"

    assert south_pickup.target_warehouse_location.latitude == 18.9500


# TEST 4 - No suitable responder


def test_no_responder_when_all_matching_responders_are_busy(tmp_path):

    responders_file = write_responders(
        tmp_path,
        [
            build_responder("T-1", "AMBULANCE", 19.0760, 72.8777, "BUSY"),
            build_responder("T-2", "AMBULANCE", 19.1000, 72.8777, "BUSY"),
            build_responder("T-3", "RESCUE_TRUCK", 19.0800, 72.8777),
        ],
    )

    service = AgentAssignmentService(responders_file)

    with pytest.raises(NoResponderAvailableError) as raised:
        service.assign(build_request(["AMBULANCE"]))

    assert raised.value.error_code == "NO_RESPONDER_AVAILABLE"
    assert raised.value.required_responder_types == ["AMBULANCE"]


def test_no_responder_when_no_matching_type_exists(tmp_path):

    responders_file = write_responders(
        tmp_path,
        [
            build_responder("T-1", "RESCUE_TRUCK", 19.0760, 72.8777),
            build_responder("T-2", "AMBULANCE", 19.0800, 72.8777),
        ],
    )

    service = AgentAssignmentService(responders_file)

    with pytest.raises(NoResponderAvailableError):
        service.assign(build_request(["FIRE_TRUCK"]))


def test_no_responder_when_responder_list_is_empty(tmp_path):

    service = AgentAssignmentService(write_responders(tmp_path, []))

    with pytest.raises(NoResponderAvailableError):
        service.assign(build_request(["RESCUE_TRUCK"]))


# TEST 5 - Haversine calculation


def test_haversine_known_distances():

    one_degree = EARTH_RADIUS_KM * math.pi / 180

    assert haversine_km(19.0760, 72.8777, 19.0760, 72.8777) == 0.0

    # One degree along a meridian and along the equator.
    assert haversine_km(0, 0, 1, 0) == pytest.approx(one_degree, abs=1e-9)
    assert haversine_km(0, 0, 0, 1) == pytest.approx(one_degree, abs=1e-9)

    # Quarter and half of a great circle.
    assert haversine_km(0, 0, 90, 0) == pytest.approx(
        EARTH_RADIUS_KM * math.pi / 2, abs=1e-6
    )
    assert haversine_km(0, 0, 0, 180) == pytest.approx(
        EARTH_RADIUS_KM * math.pi, abs=1e-6
    )

    # Mumbai -> Pune is roughly 120 km in a straight line.
    mumbai_to_pune = haversine_km(19.0760, 72.8777, 18.5204, 73.8567)

    assert mumbai_to_pune == pytest.approx(120.15, abs=0.05)


def test_haversine_is_symmetric():

    forward = haversine_km(19.0800, 72.8800, 19.0760, 72.8777)
    backward = haversine_km(19.0760, 72.8777, 19.0800, 72.8800)

    assert forward == pytest.approx(backward, abs=1e-12)


# TEST 6 - Deterministic tie


def test_exact_tie_follows_responder_file_order(tmp_path):

    # Same location -> exactly equal distance. "T-B" is listed first on
    # purpose, so the result follows file order, not id order.
    responders = [
        build_responder("T-B", "RESCUE_TRUCK", 19.0900, 72.8777),
        build_responder("T-A", "RESCUE_TRUCK", 19.0900, 72.8777),
    ]

    # Assignment makes the winner BUSY, so each run starts from the same
    # fresh state; the first-listed responder must win every time.
    for _ in range(3):
        first_order = AgentAssignmentService(
            write_responders(tmp_path, responders)
        )
        result = first_order.assign(build_request(["RESCUE_TRUCK"]))
        assert result.responder_id == "T-B"

    reversed_order = AgentAssignmentService(
        write_responders(tmp_path, list(reversed(responders)))
    )

    result = reversed_order.assign(build_request(["RESCUE_TRUCK"]))

    assert result.responder_id == "T-A"


# Assignment persists AVAILABLE -> BUSY for the selected responder only


def test_assignment_changes_only_the_selected_responder_status(
    responders_copy,
):

    before = read_records(responders_copy)

    service = AgentAssignmentService(responders_copy)

    result = service.assign(build_request(["RESCUE_TRUCK"]))

    after = read_records(responders_copy)

    assert result.responder_id == "R001"

    # Only R001's status changed; order, location and all other records
    # are exactly as before.
    assert list(after) == list(before)
    assert after["R001"] == dict(before["R001"], status="BUSY")

    for responder_id in before:
        if responder_id != "R001":
            assert after[responder_id] == before[responder_id]


def test_first_warehouse_id_is_optional(responders_copy):

    service = AgentAssignmentService(responders_copy)

    result = service.assign(
        build_request(["RESCUE_TRUCK"], warehouse_id=None)
    )

    assert result.target_warehouse_id is None
    assert result.responder_id == "R001"


# Malformed responder data


def test_malformed_responder_data_raises_clear_error(tmp_path):

    valid = build_responder("T-1", "RESCUE_TRUCK", 19.0760, 72.8777)

    missing_location = dict(valid, responder_id="T-2")
    del missing_location["location"]

    malformed_files = [
        [valid, missing_location],
        [valid, dict(valid, responder_id="T-3", status="ON_LEAVE")],
        [valid, dict(valid, responder_id="T-4", vehicle_type="BICYCLE")],
        [valid, valid],
    ]

    for responders in malformed_files:
        with pytest.raises(ValueError):
            AgentAssignmentService(write_responders(tmp_path, responders))

    not_a_list = tmp_path / "not_a_list.json"
    not_a_list.write_text(json.dumps(valid), encoding="utf-8")

    with pytest.raises(ValueError):
        AgentAssignmentService(not_a_list)


# TEST 7 - API endpoint


def test_api_assigns_responder():

    response = client.post(
        "/agent/assign",
        json={
            "mission_id": "MIS-TEST001",
            "required_responder_types": ["RESCUE_TRUCK"],
            "first_warehouse_location": WH001_LOCATION,
            "first_warehouse_id": "WH001",
        },
    )

    assert response.status_code == 200

    body = response.json()

    result = AgentAssignmentResult.model_validate(body)

    assert result.assignment_id.startswith("ASSIGN-")
    assert result.mission_id == "MIS-TEST001"
    assert result.assignment_status == "ASSIGNED"
    assert result.responder_id == "R001"
    assert result.responder_type == "RESCUE_TRUCK"
    assert result.target_warehouse_id == "WH001"

    assert body["responder_location"] == {
        "latitude": 19.08,
        "longitude": 72.88,
    }
    assert body["target_warehouse_location"] == WH001_LOCATION

    assert isinstance(body["distance_to_warehouse_km"], float)
    assert body["distance_to_warehouse_km"] == pytest.approx(0.506, abs=0.001)


def test_api_returns_409_when_no_responder_available(tmp_path, monkeypatch):

    responders_file = write_responders(
        tmp_path,
        [build_responder("T-1", "AMBULANCE", 19.0760, 72.8777, "BUSY")],
    )

    monkeypatch.setattr(
        agent_assignment_routes,
        "RESPONDERS_PATH",
        str(responders_file),
    )

    response = client.post(
        "/agent/assign",
        json={
            "mission_id": "MIS-TEST002",
            "required_responder_types": ["AMBULANCE"],
            "first_warehouse_location": WH001_LOCATION,
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"]["error"] == "NO_RESPONDER_AVAILABLE"


def test_api_returns_500_for_malformed_responder_data(tmp_path, monkeypatch):

    responders_file = tmp_path / "responders.json"
    responders_file.write_text("[{\"responder_id\": \"T-1\"}]", encoding="utf-8")

    monkeypatch.setattr(
        agent_assignment_routes,
        "RESPONDERS_PATH",
        str(responders_file),
    )

    response = client.post(
        "/agent/assign",
        json={
            "mission_id": "MIS-TEST003",
            "required_responder_types": ["RESCUE_TRUCK"],
            "first_warehouse_location": WH001_LOCATION,
        },
    )

    assert response.status_code == 500
    assert response.json()["detail"].startswith("Agent assignment failed")


def test_api_rejects_invalid_requests():

    valid = {
        "mission_id": "MIS-TEST004",
        "required_responder_types": ["RESCUE_TRUCK"],
        "first_warehouse_location": WH001_LOCATION,
    }

    invalid_requests = [
        dict(valid, required_responder_types=[]),
        dict(valid, required_responder_types=["HELICOPTER"]),
        {
            key: value
            for key, value in valid.items()
            if key != "first_warehouse_location"
        },
    ]

    for payload in invalid_requests:
        response = client.post("/agent/assign", json=payload)
        assert response.status_code == 422


def test_agent_route_is_registered_without_disturbing_existing_routes():

    # The OpenAPI schema lists routes from included routers as well.
    paths = app.openapi()["paths"]

    for path, method in [
        ("/agent/assign", "post"),
        ("/resource/allocate", "post"),
        ("/resource/allocate/batch", "post"),
        ("/demand/verify", "post"),
        ("/mission/create", "post"),
        ("/health", "get"),
    ]:
        assert method in paths[path]


# ==================================================
# Persisted status scenarios (AVAILABLE -> BUSY)
# ==================================================


def test_scenario_1_successful_assignment_persists_busy(responders_copy):

    assert read_records(responders_copy)["R001"]["status"] == "AVAILABLE"

    result = AgentAssignmentService(responders_copy).assign(
        build_request(["RESCUE_TRUCK"])
    )

    assert result.assignment_status == "ASSIGNED"
    assert result.responder_id == "R001"

    # Persisted, not only in memory: a new service reads BUSY from disk.
    assert read_records(responders_copy)["R001"]["status"] == "BUSY"

    fresh = AgentAssignmentService(responders_copy)
    statuses = {r.responder_id: r.status for r in fresh.responders}
    assert statuses["R001"] == "BUSY"


def test_scenario_2_busy_responder_is_never_selected(tmp_path):

    responders_file = write_responders(
        tmp_path,
        [
            build_responder("T-BUSY", "RESCUE_TRUCK", 19.0760, 72.8777, "BUSY"),
            build_responder("T-FREE", "RESCUE_TRUCK", 19.1500, 72.8777),
        ],
    )

    result = AgentAssignmentService(responders_file).assign(
        build_request(["RESCUE_TRUCK"])
    )

    records = read_records(responders_file)

    assert result.responder_id == "T-FREE"
    assert records["T-FREE"]["status"] == "BUSY"
    assert records["T-BUSY"]["status"] == "BUSY"


def test_scenario_3_only_closest_of_several_eligible_becomes_busy(tmp_path):

    responders_file = write_responders(
        tmp_path,
        [
            build_responder("T-FAR", "RESCUE_TRUCK", 19.3000, 72.8777),
            build_responder("T-NEAR", "RESCUE_TRUCK", 19.0800, 72.8777),
            build_responder("T-MID", "RESCUE_TRUCK", 19.1500, 72.8777),
        ],
    )

    result = AgentAssignmentService(responders_file).assign(
        build_request(["RESCUE_TRUCK"])
    )

    statuses = {
        responder_id: record["status"]
        for responder_id, record in read_records(responders_file).items()
    }

    assert result.responder_id == "T-NEAR"
    assert statuses == {
        "T-FAR": "AVAILABLE",
        "T-NEAR": "BUSY",
        "T-MID": "AVAILABLE",
    }


def test_scenario_4_only_required_vehicle_types_are_considered(tmp_path):

    responders_file = write_responders(
        tmp_path,
        [
            build_responder("T-RESCUE", "RESCUE_TRUCK", 19.0760, 72.8777),
            build_responder("T-FIRE", "FIRE_TRUCK", 19.0765, 72.8777),
            build_responder("T-AMBULANCE", "AMBULANCE", 19.2000, 72.8777),
        ],
    )

    result = AgentAssignmentService(responders_file).assign(
        build_request(["AMBULANCE"])
    )

    statuses = {
        responder_id: record["status"]
        for responder_id, record in read_records(responders_file).items()
    }

    # The closer rescue and fire trucks are not ambulances.
    assert result.responder_id == "T-AMBULANCE"
    assert statuses == {
        "T-RESCUE": "AVAILABLE",
        "T-FIRE": "AVAILABLE",
        "T-AMBULANCE": "BUSY",
    }


def test_scenario_5_no_available_responder_changes_nothing(tmp_path):

    responders_file = write_responders(
        tmp_path,
        [
            build_responder("T-1", "AMBULANCE", 19.0760, 72.8777, "BUSY"),
            build_responder("T-2", "RESCUE_TRUCK", 19.0800, 72.8777),
        ],
    )

    before = responders_file.read_bytes()

    with pytest.raises(NoResponderAvailableError) as raised:
        AgentAssignmentService(responders_file).assign(
            build_request(["AMBULANCE"])
        )

    assert raised.value.error_code == "NO_RESPONDER_AVAILABLE"
    assert responders_file.read_bytes() == before


def test_scenario_6_location_is_used_and_kept_unchanged(responders_copy):

    before = read_records(responders_copy)["R001"]

    result = AgentAssignmentService(responders_copy).assign(
        build_request(["RESCUE_TRUCK"])
    )

    after = read_records(responders_copy)["R001"]

    # Distance was measured from R001's current location.
    assert result.responder_location.model_dump() == before["location"]
    assert result.distance_to_warehouse_km == round(
        haversine_km(
            before["location"]["latitude"],
            before["location"]["longitude"],
            WH001_LOCATION["latitude"],
            WH001_LOCATION["longitude"],
        ),
        3,
    )

    # Becoming BUSY did not move the responder.
    assert after["status"] == "BUSY"
    assert after["location"] == before["location"]


def test_scenario_7_repeated_assignment_skips_busy_responder(responders_copy):

    service = AgentAssignmentService(responders_copy)

    first = service.assign(build_request(["RESCUE_TRUCK"]))
    second = service.assign(build_request(["RESCUE_TRUCK"]))

    assert first.responder_id == "R001"
    assert second.responder_id == "R004"

    records = read_records(responders_copy)
    assert records["R001"]["status"] == "BUSY"
    assert records["R004"]["status"] == "BUSY"

    # Both rescue trucks are now BUSY.
    with pytest.raises(NoResponderAvailableError):
        service.assign(build_request(["RESCUE_TRUCK"]))


def test_scenario_7_repeated_assignment_through_api(responders_copy):

    payload = {
        "mission_id": "MIS-REPEAT",
        "required_responder_types": ["RESCUE_TRUCK"],
        "first_warehouse_location": WH001_LOCATION,
        "first_warehouse_id": "WH001",
    }

    first = client.post("/agent/assign", json=payload)
    second = client.post("/agent/assign", json=payload)
    third = client.post("/agent/assign", json=payload)

    assert first.status_code == 200
    assert first.json()["responder_id"] == "R001"

    assert second.status_code == 200
    assert second.json()["responder_id"] == "R004"

    assert third.status_code == 409
    assert third.json()["detail"]["error"] == "NO_RESPONDER_AVAILABLE"

    records = read_records(responders_copy)
    assert records["R001"]["status"] == "BUSY"
    assert records["R004"]["status"] == "BUSY"


def test_persist_failure_does_not_report_assignment(
    responders_copy,
    monkeypatch,
):

    before = responders_copy.read_bytes()

    def failing_replace(source, destination):
        raise OSError("disk is read-only")

    monkeypatch.setattr(agent_assignment_service.os, "replace", failing_replace)

    with pytest.raises(ResponderStatusError):
        AgentAssignmentService(responders_copy).assign(
            build_request(["RESCUE_TRUCK"])
        )

    # Nothing was reported, nothing was written, no temp file was left.
    assert responders_copy.read_bytes() == before
    assert not list(responders_copy.parent.glob("*.tmp"))

    response = client.post(
        "/agent/assign",
        json={
            "mission_id": "MIS-FAIL",
            "required_responder_types": ["RESCUE_TRUCK"],
            "first_warehouse_location": WH001_LOCATION,
        },
    )

    assert response.status_code == 500
    assert response.json()["detail"].startswith("Agent assignment failed")
    assert responders_copy.read_bytes() == before


# ==================================================
# State transition: AVAILABLE -> BUSY -> AVAILABLE
# ==================================================


def test_state_transition_assign_then_release(responders_copy):

    service = AgentAssignmentService(responders_copy)

    original = read_records(responders_copy)["R001"]
    assert original["status"] == "AVAILABLE"

    service.assign(build_request(["RESCUE_TRUCK"]))

    busy = read_records(responders_copy)["R001"]
    assert busy["status"] == "BUSY"
    assert busy["location"] == original["location"]

    released = service.release_responder("R001")

    restored = read_records(responders_copy)["R001"]
    assert released.status == "AVAILABLE"
    assert restored["status"] == "AVAILABLE"

    # Location kept throughout; the record is back to its original values.
    assert restored["location"] == original["location"]
    assert restored == original

    # The released responder is eligible again.
    again = service.assign(build_request(["RESCUE_TRUCK"]))
    assert again.responder_id == "R001"


def test_release_rejects_invalid_transitions(responders_copy):

    service = AgentAssignmentService(responders_copy)

    before = responders_copy.read_bytes()

    # R001 is AVAILABLE: only BUSY -> AVAILABLE is allowed.
    with pytest.raises(ResponderStatusError):
        service.release_responder("R001")

    with pytest.raises(ResponderStatusError):
        service.release_responder("R999")

    assert responders_copy.read_bytes() == before
