import pytest
from pydantic import ValidationError

from resource_services.schemas.incident import Incident
from resource_services.schemas.mission import RouteData, RouteLeg
from resource_services.schemas.warehouse import Warehouse


def build_incident(**overrides):
    payload = {
        "incident_id": "INC-001",
        "incident_type": "FLOOD",
        "location": {"latitude": 19.0760, "longitude": 72.8777},
        "locality": {
            "name": "Test Locality",
            "population": 18000,
            "population_density": 12000,
            "affected_population": 4200,
        },
        "severity": 0.82,
        "estimated_duration_hours": 18,
    }
    payload.update(overrides)
    return Incident(**payload)


def test_valid_incident():
    incident = Incident(
        incident_id="INC-001",
        incident_type="FLOOD",
        location={
            "latitude": 19.0760,
            "longitude": 72.8777
        },
        locality={
            "name": "Test Locality",
            "population": 18000,
            "population_density": 12000,
            "affected_population": 4200
        },
        severity=0.82,
        estimated_duration_hours=18
    )

    assert incident.incident_id == "INC-001"
    assert incident.locality.affected_population == 4200


def test_valid_warehouse():
    warehouse = Warehouse(
        warehouse_id="WH001",
        name="Central Emergency Warehouse",
        location={
            "latitude": 19.0760,
            "longitude": 72.8777
        },
        inventory={
            "water": {
                "available": 1000,
                "capacity": 1500
            },
            "food": {
                "available": 500,
                "capacity": 800
            },
            "medical_kits": {
                "available": 100,
                "capacity": 150
            }
        },
        vehicles={
            "ambulance": {
                "total": 2,
                "available": 1
            },
            "rescue_truck": {
                "total": 3,
                "available": 2
            }
        }
    )

    assert warehouse.warehouse_id == "WH001"
    assert warehouse.inventory["water"].available == 1000


def test_incident_with_patient_present_true():
    assert build_incident(patient_present=True).patient_present is True


def test_incident_with_patient_present_false():
    assert build_incident(patient_present=False).patient_present is False


def test_incident_without_patient_present_defaults_to_false():
    incident = build_incident()

    assert incident.patient_present is False

    # Existing fields keep their meaning and values.
    assert incident.severity == 0.82
    assert incident.locality.affected_population == 4200


def test_incident_rejects_non_boolean_patient_present():
    for value in ("maybe", 2, None, [True], {"present": True}):
        with pytest.raises(ValidationError):
            build_incident(patient_present=value)


def build_leg(leg_index=0, **overrides):
    payload = {
        "leg_index": leg_index,
        "source_type": "RESPONDER",
        "source_id": "R001",
        "destination_type": "DESTINATION",
        "destination_id": "INCIDENT_DESTINATION",
        "source_location": {"latitude": 19.08, "longitude": 72.88},
        "destination_location": {"latitude": 19.0596, "longitude": 72.8295},
        "distance_km": 1.0,
        "estimated_time_minutes": 5.0,
    }
    payload.update(overrides)
    return RouteLeg(**payload)


def test_route_leg_route_engine_mission_id_is_optional():
    # An unplanned leg does not claim a Route Engine mission ID.
    assert build_leg().route_engine_mission_id is None


def test_available_route_requires_route_engine_mission_id_on_every_leg():
    with pytest.raises(ValidationError, match=r"leg_index \[1\]"):
        RouteData(
            status="AVAILABLE",
            legs=[
                build_leg(0, route_engine_mission_id="MIS-1-LEG-0"),
                build_leg(1),
            ],
        )

    with pytest.raises(ValidationError):
        RouteData(
            status="AVAILABLE",
            legs=[build_leg(0, route_engine_mission_id="")],
        )


def test_available_route_with_route_engine_mission_ids_is_valid():
    route = RouteData(
        status="AVAILABLE",
        legs=[
            build_leg(0, route_engine_mission_id="MIS-1-LEG-0"),
            build_leg(1, route_engine_mission_id="MIS-1-LEG-1"),
        ],
    )

    assert [leg.route_engine_mission_id for leg in route.legs] == [
        "MIS-1-LEG-0",
        "MIS-1-LEG-1",
    ]


def test_not_available_route_does_not_require_route_engine_mission_id():
    # Backward compatible: Mission Creation's placeholder route.
    assert RouteData(status="NOT_AVAILABLE").legs == []

    route = RouteData(status="NOT_AVAILABLE", legs=[build_leg(0)])

    assert route.legs[0].route_engine_mission_id is None