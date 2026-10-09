import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from resource_services.schemas.common import Location
from resource_services.schemas.orchestration import (
    OrchestrationRequest,
    RoutePickup,
    RoutingInputs,
)
from resource_services.services.orchestration_service import (
    OrchestrationService,
)
from resource_services.services.route_engine_client import (
    RouteEngineAPIError,
    RouteEngineClient,
    decode_polyline,
    map_priority,
    map_responder_vehicle_type,
)


RULES_PATH = "resource_services/config/resource_rules.json"
WAREHOUSES_PATH = "resource_services/database/warehouses.json"

SAMPLE_POLYLINE = "_p~iF~ps|U_ulLnnqC_mqNvxq`@"


def make_route_response(
    route_id: str = "google-route-0",
    distance_meters: int = 5000,
    duration_seconds: int = 600,
    encoded_polyline: str = SAMPLE_POLYLINE,
    status: str = "ROUTE_FOUND",
    decision_reasons: list[str] | None = None,
) -> dict[str, Any]:
    if status == "NO_SAFE_ROUTE_FOUND":
        return {
            "success": True,
            "data": {
                "status": "NO_SAFE_ROUTE_FOUND",
                "primaryRoute": None,
                "backupRoutes": [],
                "rejectedRoutes": [],
                "decisionReasons": decision_reasons or ["Route blocked by hazard"],
            },
        }

    return {
        "success": True,
        "data": {
            "status": "ROUTE_FOUND",
            "primaryRoute": {
                "routeId": route_id,
                "distanceMeters": distance_meters,
                "durationSeconds": duration_seconds,
                "encodedPolyline": encoded_polyline,
                "routeLabels": [],
                "description": "via Main Road",
                "matchedIncidents": [],
                "roadConditionAssessment": {
                    "status": "OPEN",
                    "confidence": "HIGH",
                    "reasons": [],
                },
                "status": "VALID",
                "score": 10.0,
                "breakdown": {"travelTimeScore": 0, "roadRiskScore": 0, "uncertaintyScore": 0},
                "reasons": [{"message": "Safe route"}],
            },
            "backupRoutes": [],
            "rejectedRoutes": [],
            "decisionReasons": decision_reasons or ["Route selected"],
        },
    }


# --------------------------------------------------
# Unit Tests: Polyline Decoding
# --------------------------------------------------


def test_decode_polyline_empty():
    assert decode_polyline("") == []
    assert decode_polyline(None) == []


def test_decode_polyline_known_coordinates():
    coords = decode_polyline(SAMPLE_POLYLINE)
    assert len(coords) == 3
    # Known points: ~38.5, -120.2; ~40.7, -120.95; ~43.252, -126.453
    assert abs(coords[0].latitude - 38.5) < 1e-4
    assert abs(coords[0].longitude - (-120.2)) < 1e-4
    assert abs(coords[1].latitude - 40.7) < 1e-4
    assert abs(coords[1].longitude - (-120.95)) < 1e-4


# --------------------------------------------------
# Unit Tests: Priority & Vehicle Mapping
# --------------------------------------------------


def test_map_priority_correction_1():
    # Exactly per CORRECTION 1:
    assert map_priority("LOW") == "LOW"
    assert map_priority("MODERATE") == "MEDIUM"
    assert map_priority("HIGH") == "HIGH"
    assert map_priority("CRITICAL") == "CRITICAL"
    # When None, returns None (omitted, never defaulted to MEDIUM)
    assert map_priority(None) is None
    assert map_priority("") is None


def test_map_responder_vehicle_type():
    assert map_responder_vehicle_type("AMBULANCE") == "AMBULANCE"
    assert map_responder_vehicle_type("RESCUE_TRUCK") == "RESCUE_VEHICLE"
    assert map_responder_vehicle_type("FIRE_TRUCK") == "DEFAULT"
    assert map_responder_vehicle_type(None) is None


# --------------------------------------------------
# Multi-Leg Routing: One Warehouse (2 legs)
# --------------------------------------------------


def test_one_warehouse_two_legs():
    requests_received = []

    def mock_handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        requests_received.append(body)
        idx = len(requests_received)
        return httpx.Response(
            200,
            json=make_route_response(
                route_id=f"leg-{idx}-route",
                distance_meters=4000,
                duration_seconds=300,
            ),
        )

    mock_client = httpx.Client(transport=httpx.MockTransport(mock_handler))
    client = RouteEngineClient(base_url="http://mock-route-engine", http_client=mock_client)

    inputs = RoutingInputs(
        mission_id="MIS-001",
        responder_id="R001",
        responder_location=Location(latitude=19.08, longitude=72.88),
        pickups=[
            RoutePickup(
                warehouse_id="WH-001",
                location=Location(latitude=19.10, longitude=72.89),
            )
        ],
        destination=Location(latitude=19.15, longitude=72.92),
        vehicle_type="RESCUE_TRUCK",
        priority="HIGH",
    )

    result = client.plan_route(inputs)

    assert result.status == "ROUTE_PLANNED"
    assert result.route.status == "AVAILABLE"
    # Exactly 2 calls: Responder -> WH1, WH1 -> Destination
    assert len(requests_received) == 2

    # Leg 0: Responder -> WH1
    assert requests_received[0]["source"]["latitude"] == 19.08
    assert requests_received[0]["destination"]["latitude"] == 19.10
    assert requests_received[0]["resourceType"] == "RESCUE_VEHICLE"
    assert requests_received[0]["priority"] == "HIGH"
    assert requests_received[0]["missionId"] == "MIS-001-LEG-0"

    # Leg 1: WH1 -> Destination
    assert requests_received[1]["source"]["latitude"] == 19.10
    assert requests_received[1]["destination"]["latitude"] == 19.15
    assert requests_received[1]["missionId"] == "MIS-001-LEG-1"

    # One warehouse -> 2 legs, each with its own non-null Route Engine ID,
    # the same one it was sent with. The AASHRAY mission ID is unchanged.
    sent_ids = [body["missionId"] for body in requests_received]
    leg_ids = [leg.route_engine_mission_id for leg in result.route.legs]
    assert leg_ids == ["MIS-001-LEG-0", "MIS-001-LEG-1"]
    assert all(leg_ids) and len(set(leg_ids)) == 2
    assert leg_ids == sent_ids
    assert result.routing_inputs.mission_id == "MIS-001"

    # Route sums
    # 4000m + 4000m = 8.0 km
    assert result.route.distance_km == 8.0
    # 300s + 300s = 10.0 minutes
    assert result.route.estimated_time_minutes == 10.0
    assert len(result.route.legs) == 2
    assert result.route.legs[0].source_id == "R001"
    assert result.route.legs[0].destination_id == "WH-001"
    assert result.route.legs[1].source_id == "WH-001"
    assert result.route.legs[1].destination_id == "INCIDENT_DESTINATION"


# --------------------------------------------------
# Multi-Leg Routing: Two Warehouses (3 legs)
# --------------------------------------------------


def test_two_warehouses_three_legs():
    requests_received = []

    def mock_handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        requests_received.append(body)
        return httpx.Response(
            200,
            json=make_route_response(
                distance_meters=3000,
                duration_seconds=180,
            ),
        )

    mock_client = httpx.Client(transport=httpx.MockTransport(mock_handler))
    client = RouteEngineClient(base_url="http://mock-route-engine", http_client=mock_client)

    inputs = RoutingInputs(
        mission_id="MIS-002",
        responder_id="R002",
        responder_location=Location(latitude=19.06, longitude=72.90),
        pickups=[
            RoutePickup(
                warehouse_id="WH-001",
                location=Location(latitude=19.08, longitude=72.88),
            ),
            RoutePickup(
                warehouse_id="WH-002",
                location=Location(latitude=19.11, longitude=72.86),
            ),
        ],
        destination=Location(latitude=19.14, longitude=72.84),
        vehicle_type="AMBULANCE",
        priority="MODERATE",
    )

    result = client.plan_route(inputs)

    assert result.status == "ROUTE_PLANNED"
    # Exactly N+1 = 3 calls
    assert len(requests_received) == 3

    # Verification of MODERATE mapped to MEDIUM
    assert requests_received[0]["priority"] == "MEDIUM"
    assert requests_received[0]["resourceType"] == "AMBULANCE"

    # Sum of 3 legs: 3km * 3 = 9km; 3min * 3 = 9min
    assert result.route.distance_km == 9.0
    assert result.route.estimated_time_minutes == 9.0
    assert len(result.route.legs) == 3

    # Two warehouses -> 3 legs, all Route Engine IDs non-null and unique,
    # in leg order.
    sent_ids = [body["missionId"] for body in requests_received]
    leg_ids = [leg.route_engine_mission_id for leg in result.route.legs]
    assert leg_ids == ["MIS-002-LEG-0", "MIS-002-LEG-1", "MIS-002-LEG-2"]
    assert all(leg_ids) and len(set(leg_ids)) == 3
    assert leg_ids == sent_ids
    assert [leg.leg_index for leg in result.route.legs] == [0, 1, 2]
    assert result.routing_inputs.mission_id == "MIS-002"


# --------------------------------------------------
# Priority None is omitted
# --------------------------------------------------


def test_none_priority_omitted_from_request():
    requests_received = []

    def mock_handler(request: httpx.Request) -> httpx.Response:
        requests_received.append(json.loads(request.content.decode("utf-8")))
        return httpx.Response(200, json=make_route_response())

    mock_client = httpx.Client(transport=httpx.MockTransport(mock_handler))
    client = RouteEngineClient(base_url="http://mock-route-engine", http_client=mock_client)

    inputs = RoutingInputs(
        mission_id="MIS-003",
        responder_id="R001",
        responder_location=Location(latitude=19.08, longitude=72.88),
        pickups=[RoutePickup(warehouse_id="WH-1", location=Location(latitude=19.1, longitude=72.9))],
        destination=Location(latitude=19.12, longitude=72.91),
        priority=None,
    )

    result = client.plan_route(inputs)
    assert result.status == "ROUTE_PLANNED"
    assert "priority" not in requests_received[0]


# --------------------------------------------------
# Middle Leg Fails: NO_SAFE_ROUTE_FOUND
# --------------------------------------------------


def test_middle_leg_no_safe_route_found_stops_immediately():
    call_count = 0
    sent_ids = []

    def mock_handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        sent_ids.append(json.loads(request.content.decode("utf-8"))["missionId"])
        if call_count == 1:
            # Leg 0 succeeds
            return httpx.Response(200, json=make_route_response())
        elif call_count == 2:
            # Leg 1 fails due to road closures
            return httpx.Response(
                200,
                json=make_route_response(
                    status="NO_SAFE_ROUTE_FOUND",
                    decision_reasons=["Active flood hazard at highway"],
                ),
            )
        else:
            # Leg 2 must NEVER be called
            raise AssertionError("Subsequent leg should not have been called!")

    mock_client = httpx.Client(transport=httpx.MockTransport(mock_handler))
    client = RouteEngineClient(base_url="http://mock-route-engine", http_client=mock_client)

    inputs = RoutingInputs(
        mission_id="MIS-004",
        responder_id="R001",
        responder_location=Location(latitude=19.08, longitude=72.88),
        pickups=[
            RoutePickup(warehouse_id="WH-1", location=Location(latitude=19.1, longitude=72.9)),
            RoutePickup(warehouse_id="WH-2", location=Location(latitude=19.12, longitude=72.91)),
        ],
        destination=Location(latitude=19.15, longitude=72.95),
    )

    result = client.plan_route(inputs)

    assert result.status == "NO_SAFE_ROUTE_FOUND"
    assert result.route.status == "NOT_AVAILABLE"
    # Exactly 2 calls executed, 3rd leg was never called
    assert call_count == 2
    assert sent_ids == ["MIS-004-LEG-0", "MIS-004-LEG-1"]
    assert "WH-1 -> WH-2" in result.message
    assert "Active flood hazard at highway" in result.message
    assert result.routing_inputs.mission_id == "MIS-004"

    # The unavailable route carries no legs, so it claims no Route Engine
    # mission ID, not even for leg 0, which was planned.
    assert result.route.legs == []
    assert "route_engine_mission_id" not in json.dumps(result.model_dump(mode="json"))


# --------------------------------------------------
# HTTP Timeout
# --------------------------------------------------


def test_default_timeout_is_30_seconds():
    assert RouteEngineClient(base_url="http://mock-route-engine").timeout == 30.0


def test_owned_http_client_uses_30_second_timeout(monkeypatch):
    # Without an injected http_client, the client builds its own httpx.Client
    # with the configured timeout.
    created_with = {}
    real_client = httpx.Client

    def recording_client(**kwargs):
        created_with.update(kwargs)
        return real_client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json=make_route_response())
            ),
            **kwargs,
        )

    monkeypatch.setattr(httpx, "Client", recording_client)

    client = RouteEngineClient(base_url="http://mock-route-engine")

    inputs = RoutingInputs(
        mission_id="MIS-TIMEOUT",
        responder_id="R001",
        responder_location=Location(latitude=19.08, longitude=72.88),
        pickups=[RoutePickup(warehouse_id="WH-1", location=Location(latitude=19.1, longitude=72.9))],
        destination=Location(latitude=19.12, longitude=72.91),
    )

    result = client.plan_route(inputs)

    assert result.status == "ROUTE_PLANNED"
    assert created_with == {"timeout": 30.0}


def test_timeout_is_reported_as_not_connected():
    # Error semantics unchanged: a timeout is a RequestError, so it is
    # reported as ROUTE_ENGINE_NOT_CONNECTED, not raised.
    def mock_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    mock_client = httpx.Client(transport=httpx.MockTransport(mock_handler))
    client = RouteEngineClient(base_url="http://slow-engine", http_client=mock_client)

    inputs = RoutingInputs(
        mission_id="MIS-SLOW",
        responder_id="R001",
        responder_location=Location(latitude=19.08, longitude=72.88),
        pickups=[RoutePickup(warehouse_id="WH-1", location=Location(latitude=19.1, longitude=72.9))],
        destination=Location(latitude=19.12, longitude=72.91),
    )

    result = client.plan_route(inputs)

    assert result.status == "ROUTE_ENGINE_NOT_CONNECTED"
    assert result.route is None
    assert "leg 0" in result.message


# --------------------------------------------------
# Connection / Network Failure
# --------------------------------------------------


def test_route_engine_connection_failure():
    def mock_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused by route engine")

    mock_client = httpx.Client(transport=httpx.MockTransport(mock_handler))
    client = RouteEngineClient(base_url="http://offline-engine", http_client=mock_client)

    inputs = RoutingInputs(
        mission_id="MIS-005",
        responder_id="R001",
        responder_location=Location(latitude=19.08, longitude=72.88),
        pickups=[RoutePickup(warehouse_id="WH-1", location=Location(latitude=19.1, longitude=72.9))],
        destination=Location(latitude=19.12, longitude=72.91),
    )

    result = client.plan_route(inputs)

    assert result.status == "ROUTE_ENGINE_NOT_CONNECTED"
    assert result.route is None
    assert "Connection refused" in result.message


def test_unconfigured_route_engine_claims_no_route_engine_mission_id():
    inputs = RoutingInputs(
        mission_id="MIS-UNCONFIGURED",
        responder_id="R001",
        responder_location=Location(latitude=19.08, longitude=72.88),
        pickups=[RoutePickup(warehouse_id="WH-1", location=Location(latitude=19.1, longitude=72.9))],
        destination=Location(latitude=19.12, longitude=72.91),
    )

    result = RouteEngineClient(base_url="").plan_route(inputs)

    assert result.status == "ROUTE_ENGINE_NOT_CONNECTED"
    assert result.route is None
    assert result.routing_inputs.mission_id == "MIS-UNCONFIGURED"
    assert "route_engine_mission_id" not in json.dumps(result.model_dump(mode="json"))


# --------------------------------------------------
# HTTP 400 Validation Error
# --------------------------------------------------


def test_http_400_validation_error_raises_route_engine_api_error():
    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"success": False, "error": "Validation Error"})

    mock_client = httpx.Client(transport=httpx.MockTransport(mock_handler))
    client = RouteEngineClient(base_url="http://mock-route-engine", http_client=mock_client)

    inputs = RoutingInputs(
        mission_id="MIS-006",
        responder_id="R001",
        responder_location=Location(latitude=19.08, longitude=72.88),
        pickups=[RoutePickup(warehouse_id="WH-1", location=Location(latitude=19.1, longitude=72.9))],
        destination=Location(latitude=19.12, longitude=72.91),
    )

    with pytest.raises(RouteEngineAPIError) as exc_info:
        client.plan_route(inputs)

    assert exc_info.value.status_code == 400
    assert "Validation Error" in str(exc_info.value)


# --------------------------------------------------
# HTTP 500 Server Error
# --------------------------------------------------


def test_http_500_server_error_raises_route_engine_api_error():
    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="Internal Server Error in Google Routes service")

    mock_client = httpx.Client(transport=httpx.MockTransport(mock_handler))
    client = RouteEngineClient(base_url="http://mock-route-engine", http_client=mock_client)

    inputs = RoutingInputs(
        mission_id="MIS-007",
        responder_id="R001",
        responder_location=Location(latitude=19.08, longitude=72.88),
        pickups=[RoutePickup(warehouse_id="WH-1", location=Location(latitude=19.1, longitude=72.9))],
        destination=Location(latitude=19.12, longitude=72.91),
    )

    with pytest.raises(RouteEngineAPIError) as exc_info:
        client.plan_route(inputs)

    assert exc_info.value.status_code == 500


# --------------------------------------------------
# Orchestrator Integration: Full Pipeline with Route Engine
# --------------------------------------------------


def test_orchestrator_completes_when_route_engine_returns_routes(responders_copy):
    calls_made = []

    def mock_handler(request: httpx.Request) -> httpx.Response:
        calls_made.append(request)
        return httpx.Response(
            200,
            json=make_route_response(
                distance_meters=4500,
                duration_seconds=360,
            ),
        )

    mock_client = httpx.Client(transport=httpx.MockTransport(mock_handler))
    client = RouteEngineClient(base_url="http://mock-engine", http_client=mock_client)

    orchestrator = OrchestrationService(
        RULES_PATH,
        WAREHOUSES_PATH,
        responders_copy,
        route_engine_client=client,
    )

    request = OrchestrationRequest(
        incident_id="INC-SUCCESS",
        incident_type="FLOOD",
        severity=0.8,
        estimated_duration_hours=24.0,
        location=Location(latitude=19.0800, longitude=72.8900),
        locality={
            "name": "Test Locality",
            "population": 20000,
            "population_density": 12000,
            "affected_population": 500,
        },
        urgency=0.8,
        priority="HIGH",
    )

    result = orchestrator.run(request)

    assert result.status == "COMPLETED"
    assert result.route.status == "ROUTE_PLANNED"
    assert result.route.route.status == "AVAILABLE"
    assert len(calls_made) >= 2
    assert result.route.route.distance_km > 0
    assert len(result.route.route.legs) >= 2


def test_orchestrator_keeps_aashray_mission_id_and_sends_leg_ids(tmp_path):
    # Its own responders file, so the result does not depend on the state
    # of the real dummy database.
    responders_path = tmp_path / "responders.json"
    responders_path.write_text(
        json.dumps(
            [
                {
                    "responder_id": "T-RESCUE",
                    "name": "Test Rescue",
                    "vehicle_type": "RESCUE_TRUCK",
                    "location": {"latitude": 19.08, "longitude": 72.88},
                    "status": "AVAILABLE",
                }
            ]
        ),
        encoding="utf-8",
    )

    sent_ids = []

    def mock_handler(request: httpx.Request) -> httpx.Response:
        sent_ids.append(json.loads(request.content.decode("utf-8"))["missionId"])
        return httpx.Response(200, json=make_route_response())

    mock_client = httpx.Client(transport=httpx.MockTransport(mock_handler))
    client = RouteEngineClient(base_url="http://mock-engine", http_client=mock_client)

    orchestrator = OrchestrationService(
        RULES_PATH,
        WAREHOUSES_PATH,
        responders_path,
        route_engine_client=client,
    )

    # 800 affected people need stock from two warehouses (WH001, WH002).
    request = OrchestrationRequest(
        incident_id="INC-TWO-PICKUPS",
        incident_type="FLOOD",
        severity=0.8,
        estimated_duration_hours=12.0,
        location=Location(latitude=19.0596, longitude=72.8295),
        locality={
            "name": "Test Locality",
            "population": 20000,
            "population_density": 12000,
            "affected_population": 800,
        },
        urgency=0.9,
        priority="HIGH",
    )

    result = orchestrator.run(request)

    assert result.status == "COMPLETED"

    mission_id = result.mission.mission_id
    pickups = [p for p in result.mission.pickup_sequence if p.type == "WAREHOUSE"]
    assert [p.warehouse_id for p in pickups] == ["WH001", "WH002"]

    # Route Engine: one unique ID per leg (2 pickups -> 3 legs).
    assert sent_ids == [
        f"{mission_id}-LEG-0",
        f"{mission_id}-LEG-1",
        f"{mission_id}-LEG-2",
    ]

    # AASHRAY keeps its own mission ID everywhere it already had it.
    assert "-LEG-" not in mission_id
    assert result.agent_assignment.mission_id == mission_id
    assert result.route.routing_inputs.mission_id == mission_id

    # Each leg records which Route Engine ID it was planned under.
    legs = result.route.route.legs
    assert [leg.route_engine_mission_id for leg in legs] == sent_ids
    assert [(leg.source_id, leg.destination_id) for leg in legs] == [
        ("T-RESCUE", "WH001"),
        ("WH001", "WH002"),
        ("WH002", "INCIDENT_DESTINATION"),
    ]

    # The serialized result (what /orchestrate returns) exposes the Route
    # Engine ID on every routed leg, next to the unchanged parent mission ID.
    body = result.model_dump(mode="json")
    assert body["mission"]["mission_id"] == mission_id
    assert body["route"]["routing_inputs"]["mission_id"] == mission_id
    assert [
        leg["route_engine_mission_id"] for leg in body["route"]["route"]["legs"]
    ] == sent_ids


def test_orchestrator_handles_no_safe_route_found(responders_copy):
    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=make_route_response(
                status="NO_SAFE_ROUTE_FOUND",
                decision_reasons=["Major bridge collapse on route"],
            ),
        )

    mock_client = httpx.Client(transport=httpx.MockTransport(mock_handler))
    client = RouteEngineClient(base_url="http://mock-engine", http_client=mock_client)

    orchestrator = OrchestrationService(
        RULES_PATH,
        WAREHOUSES_PATH,
        responders_copy,
        route_engine_client=client,
    )

    request = OrchestrationRequest(
        incident_id="INC-BLOCKED",
        incident_type="FLOOD",
        severity=0.8,
        estimated_duration_hours=24.0,
        location=Location(latitude=19.0800, longitude=72.8900),
        locality={
            "name": "Test Locality",
            "population": 20000,
            "population_density": 12000,
            "affected_population": 500,
        },
        urgency=0.8,
        priority="HIGH",
    )

    result = orchestrator.run(request)

    # Route engine responded with NO_SAFE_ROUTE_FOUND
    assert result.status == "NO_SAFE_ROUTE_FOUND"
    assert result.route.status == "NO_SAFE_ROUTE_FOUND"
    assert result.route.route.status == "NOT_AVAILABLE"
    # Assigned responder remains BUSY
    assert result.agent_assignment.assignment_status == "ASSIGNED"
