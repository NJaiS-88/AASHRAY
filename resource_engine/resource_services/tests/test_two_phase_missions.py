import json
import shutil
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from resource_services.schemas.common import Location
from resource_services.schemas.incident import Locality
from resource_services.schemas.orchestration import (
    OrchestrationRequest,
    RouteBoundaryResult,
    RoutingInputs,
)
from resource_services.schemas.mission import RouteData, RouteLeg
from resource_services.services.orchestration_service import OrchestrationService

ROOT = Path(__file__).resolve().parent.parent
RULES_PATH = ROOT / "config" / "resource_rules_v2.json"
WAREHOUSES_PATH = ROOT / "database" / "warehouses.json"
RESPONDERS_PATH = ROOT / "database" / "responders.json"


@pytest.fixture
def temp_environment(tmp_path):
    tmp_rules = tmp_path / "rules.json"
    tmp_warehouses = tmp_path / "warehouses.json"
    tmp_responders = tmp_path / "responders.json"
    tmp_missions = tmp_path / "missions.json"

    shutil.copyfile(RULES_PATH, tmp_rules)
    shutil.copyfile(WAREHOUSES_PATH, tmp_warehouses)
    shutil.copyfile(RESPONDERS_PATH, tmp_responders)
    tmp_missions.write_text("[]", encoding="utf-8")

    # Set all responders to AVAILABLE in temp responders
    with open(tmp_responders, "r", encoding="utf-8") as f:
        resp = json.load(f)
    for r in resp:
        r["status"] = "AVAILABLE"
    with open(tmp_responders, "w", encoding="utf-8") as f:
        json.dump(resp, f, indent=2)

    return {
        "rules": tmp_rules,
        "warehouses": tmp_warehouses,
        "responders": tmp_responders,
        "missions": tmp_missions,
    }


def _mock_route_engine(eta_minutes: float = 35.0):
    client = MagicMock()
    def plan_route_side_effect(inputs: RoutingInputs):
        legs = [
            RouteLeg(
                leg_index=0,
                route_engine_mission_id=f"{inputs.mission_id}-LEG-0",
                source_type="RESPONDER",
                source_id=inputs.responder_id,
                destination_type="WAREHOUSE",
                destination_id=inputs.pickups[0].warehouse_id if inputs.pickups else "WH001",
                source_location=inputs.responder_location,
                destination_location=inputs.pickups[0].location if inputs.pickups else inputs.destination,
                distance_km=4.5,
                estimated_time_minutes=eta_minutes * 0.4,
                coordinates=[inputs.responder_location, inputs.destination],
            ),
            RouteLeg(
                leg_index=1,
                route_engine_mission_id=f"{inputs.mission_id}-LEG-1",
                source_type="WAREHOUSE",
                source_id=inputs.pickups[0].warehouse_id if inputs.pickups else "WH001",
                destination_type="DESTINATION",
                destination_id="DISASTER_SITE",
                source_location=inputs.pickups[0].location if inputs.pickups else inputs.responder_location,
                destination_location=inputs.destination,
                distance_km=8.2,
                estimated_time_minutes=eta_minutes * 0.6,
                coordinates=[inputs.responder_location, inputs.destination],
            ),
        ]
        return RouteBoundaryResult(
            status="ROUTE_PLANNED",
            routing_inputs=inputs,
            route=RouteData(
                status="AVAILABLE",
                coordinates=[inputs.responder_location, inputs.destination],
                distance_km=12.7,
                estimated_time_minutes=eta_minutes,
                legs=legs,
            ),
        )
    client.plan_route.side_effect = plan_route_side_effect
    return client


def test_two_phase_triggered_on_structural_collapse(temp_environment):
    service = OrchestrationService(
        requirement_rules_path=temp_environment["rules"],
        warehouses_path=temp_environment["warehouses"],
        responders_path=temp_environment["responders"],
        route_engine_client=_mock_route_engine(eta_minutes=25.0),
    )

    request = OrchestrationRequest(
        incident_id="INC-COLLAPSE-01",
        incident_type="STRUCTURAL_COLLAPSE",
        severity=0.9,
        urgency=0.95,
        priority="CRITICAL",
        location=Location(latitude=19.0760, longitude=72.8777),
        locality=Locality(
            name="Kurla Slab Collapse Site",
            population=12000,
            population_density=9000.0,
            affected_population=15,
        ),
        patient_present=True,
        estimated_duration_hours=12.0,
        hazard_details=["People trapped under fallen concrete slab", "Severe structural trauma"],
    )

    result = service.run(request)

    assert result.status == "COMPLETED"
    assert result.phase == "TWO_PHASE_COORDINATED"
    assert len(result.sub_missions) == 2

    phase_a = result.sub_missions[0]
    phase_b = result.sub_missions[1]

    # Verify Phase A (Immediate Response)
    assert phase_a.phase == "IMMEDIATE_RESPONSE"
    assert phase_a.mission.mission_id.endswith("-A")
    assert phase_a.status == "COMPLETED"
    assert phase_a.agent_assignment is not None
    # Immediate life-saving resources
    for r_k in phase_a.allocation.allocated_resources:
        assert r_k in {
            "search_and_rescue",
            "first_aid_trauma",
            "emergency_medical_care",
            "tools_equipment",
            "heavy_machinery_debris_clearance",
        }

    # Verify Phase B (Follow-Up Logistics)
    assert phase_b.phase == "FOLLOW_UP_LOGISTICS"
    assert phase_b.mission.mission_id.endswith("-B")
    assert phase_b.status == "COMPLETED"
    assert phase_b.agent_assignment is not None
    # Follow-up supplies (food, water, shelter, etc.)
    for r_k in phase_b.allocation.allocated_resources:
        assert r_k not in {
            "search_and_rescue",
            "first_aid_trauma",
            "emergency_medical_care",
            "tools_equipment",
            "heavy_machinery_debris_clearance",
        }


def test_shared_inventory_sequential_deduction_no_double_allocation(temp_environment):
    service = OrchestrationService(
        requirement_rules_path=temp_environment["rules"],
        warehouses_path=temp_environment["warehouses"],
        responders_path=temp_environment["responders"],
        route_engine_client=_mock_route_engine(),
    )

    request = OrchestrationRequest(
        incident_id="INC-LANDSLIDE-02",
        incident_type="LANDSLIDE",
        severity=0.85,
        urgency=0.9,
        priority="CRITICAL",
        location=Location(latitude=19.1290, longitude=72.9090),
        locality=Locality(
            name="Ghatkopar Hillside",
            population=15000,
            population_density=8000.0,
            affected_population=30,
        ),
        patient_present=True,
        estimated_duration_hours=24.0,
        hazard_details=["Debris flow blocking road", "Residences buried under mud"],
    )

    result = service.run(request)

    phase_a = result.sub_missions[0]
    phase_b = result.sub_missions[1]

    # Check zero overlap in allocated resource keys
    keys_a = set(phase_a.allocation.allocated_resources.keys())
    keys_b = set(phase_b.allocation.allocated_resources.keys())
    assert keys_a.isdisjoint(keys_b)

    # Check combined allocation matches sum of phase a and phase b
    for k, v in phase_a.allocation.allocated_resources.items():
        assert result.allocation.allocated_resources[k] == v
    for k, v in phase_b.allocation.allocated_resources.items():
        assert result.allocation.allocated_resources[k] == v


def test_single_phase_preserved_on_non_time_critical(temp_environment):
    service = OrchestrationService(
        requirement_rules_path=temp_environment["rules"],
        warehouses_path=temp_environment["warehouses"],
        responders_path=temp_environment["responders"],
        route_engine_client=_mock_route_engine(),
    )

    request = OrchestrationRequest(
        incident_id="INC-FLOOD-03",
        incident_type="FLOOD",
        severity=0.7,
        urgency=0.6,
        priority="HIGH",
        location=Location(latitude=19.0176, longitude=72.8561),
        locality=Locality(
            name="Dadar Lowlands",
            population=25000,
            population_density=10000.0,
            affected_population=50,
        ),
        patient_present=False,
        estimated_duration_hours=8.0,
        hazard_details=["Waterlogging 2 feet", "Low lying ground floor inundation"],
    )

    result = service.run(request)

    assert result.status == "COMPLETED"
    assert result.phase == "SINGLE_PHASE"
    assert len(result.sub_missions) == 0
    assert result.mission.mission_id.startswith("MIS-")
    assert not result.mission.mission_id.endswith("-A")


def test_independent_responder_assignments_for_each_phase(temp_environment):
    service = OrchestrationService(
        requirement_rules_path=temp_environment["rules"],
        warehouses_path=temp_environment["warehouses"],
        responders_path=temp_environment["responders"],
        route_engine_client=_mock_route_engine(),
    )

    request = OrchestrationRequest(
        incident_id="INC-COLLAPSE-04",
        incident_type="BUILDING_COLLAPSE",
        severity=0.95,
        urgency=0.95,
        priority="CRITICAL",
        location=Location(latitude=19.0760, longitude=72.8777),
        locality=Locality(
            name="Bhiwandi Industrial Area",
            population=8000,
            population_density=5000.0,
            affected_population=20,
        ),
        patient_present=True,
        estimated_duration_hours=18.0,
        hazard_details=["Two-story structure completely collapsed"],
    )

    result = service.run(request)

    phase_a = result.sub_missions[0]
    phase_b = result.sub_missions[1]

    # Responders must be distinct
    resp_a_id = phase_a.agent_assignment.responder_id
    resp_b_id = phase_b.agent_assignment.responder_id
    assert resp_a_id != resp_b_id
    # Both routes must be independent
    assert phase_a.route.routing_inputs.responder_id == resp_a_id
    assert phase_b.route.routing_inputs.responder_id == resp_b_id


def test_emergency_eta_threshold_escalation_warning(temp_environment):
    # Route with 105 mins ETA exceeds the 90 min threshold
    service = OrchestrationService(
        requirement_rules_path=temp_environment["rules"],
        warehouses_path=temp_environment["warehouses"],
        responders_path=temp_environment["responders"],
        route_engine_client=_mock_route_engine(eta_minutes=105.0),
    )

    request = OrchestrationRequest(
        incident_id="INC-COLLAPSE-05",
        incident_type="STRUCTURAL_COLLAPSE",
        severity=0.95,
        urgency=0.95,
        priority="CRITICAL",
        location=Location(latitude=19.0760, longitude=72.8777),
        locality=Locality(
            name="Dharavi Sector 4",
            population=50000,
            population_density=20000.0,
            affected_population=12,
        ),
        patient_present=True,
        estimated_duration_hours=12.0,
        hazard_details=["Severe structural wall collapse"],
    )

    result = service.run(request)

    phase_a = result.sub_missions[0]
    assert phase_a.route.route.emergency_threshold_exceeded is True
    assert phase_a.route.route.eta_review_escalation is True
    assert "EMERGENCY ETA ESCALATION" in phase_a.route.route.emergency_threshold_warning
