"""Phase 3: Live API integration tests via httpx against running server.

Requires the FastAPI server running on 127.0.0.1:8000.
Run with: python -m pytest resource_services/tests/test_phase3_live_api.py -v -p no:conftest

The /orchestrate endpoint runs the full pipeline (Requirement → Allocation →
Demand Fulfilment → Mission → Agent Assignment → Route Engine). Its HTTP
status depends on the deepest stage reached:
  200 = COMPLETED or ROUTE_ENGINE_NOT_CONNECTED
  409 = NO_SAFE_ROUTE_FOUND, MISSION_NOT_DISPATCHABLE, NO_RESPONDER_AVAILABLE
  500 = FAILED

Since we do not have a running Route Engine, and Agent Assignment mutates
responder state, tests that go through /orchestrate accept 200 or 409 and
verify the requirement/allocation payload.

Tests focused purely on requirement/allocation use /resource/allocate which
does NOT go through Agent Assignment or Route Engine.
"""

import httpx
import pytest

BASE = "http://127.0.0.1:8000"


@pytest.fixture(scope="module")
def http():
    with httpx.Client(base_url=BASE, timeout=10.0) as c:
        yield c


def _orchestrate_payload(
    affected_population=100,
    severity=0.7,
    urgency=0.6,
    priority="HIGH",
    selected_resource_ids=None,
    incident_scope=None,
    incident_id="INC-LIVE-001",
    incident_type="FLOOD",
):
    payload = {
        "incident_id": incident_id,
        "incident_type": incident_type,
        "location": {"latitude": 19.076, "longitude": 72.878},
        "locality": {
            "name": "Test Locality",
            "population": 18000,
            "population_density": 9500,
            "affected_population": affected_population,
        },
        "severity": severity,
        "estimated_duration_hours": 12.0,
        "urgency": urgency,
        "priority": priority,
    }
    if selected_resource_ids is not None:
        payload["selected_resource_ids"] = selected_resource_ids
    if incident_scope is not None:
        payload["incident_scope"] = incident_scope
    return payload


def _jev_payload(
    severity=2,
    urgency=1,
    priority="P2",
    wide_area_status=None,
    selected_resources=None,
    affected_population=200,
    incident_id="JEV-LIVE-001",
    incident_type="FLOOD",
):
    payload = {
        "incident_id": incident_id,
        "location": {"latitude": 19.076, "longitude": 72.878},
        "locality": {
            "name": "Test Area",
            "population": 20000,
            "population_density": 10000,
            "affected_population": affected_population,
        },
        "estimated_duration_hours": 24.0,
        "jev_triage": {
            "incident_type": incident_type,
            "assessment": {
                "severity": {"numeric": severity},
                "urgency": {"numeric": urgency},
                "priority": {"level": priority},
            },
            "selected_resources": [
                {"resource": r} for r in (selected_resources or [])
            ],
        },
    }
    if wide_area_status:
        payload["jev_triage"]["wide_area"] = {"status": wide_area_status}
    return payload


def _assert_pipeline_ok(r):
    """Accept any non-500 response as a successful pipeline run."""
    assert r.status_code in (200, 409), f"Unexpected {r.status_code}: {r.text[:300]}"
    body = r.json()
    assert "REQUIREMENT" in body["completed_stages"]
    assert "ALLOCATION" in body["completed_stages"]
    return body


# -------------------------------------------------------
# Health
# -------------------------------------------------------

def test_health(http):
    r = http.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "healthy"


# -------------------------------------------------------
# POST /orchestrate — valid payloads
# -------------------------------------------------------

class TestOrchestrate:

    def test_successful_orchestration(self, http):
        r = http.post("/orchestrate", json=_orchestrate_payload(
            selected_resource_ids=["drinking_water", "food_dry_rations"],
        ))
        body = _assert_pipeline_ok(r)
        assert body["incident_id"] == "INC-LIVE-001"
        assert body["requirement"]["requirements"]["drinking_water"] > 0
        assert body["requirement"]["requirements"]["food_dry_rations"] > 0
        assert body["allocation"]["allocated_resources"]["drinking_water"] > 0

    def test_all_30_resources(self, http):
        r = http.post("/orchestrate", json=_orchestrate_payload(
            affected_population=50, incident_id="INC-ALL30", incident_type="ALL",
        ))
        body = _assert_pipeline_ok(r)
        assert len(body["requirement"]["requirements"]) == 30

    def test_single_resource(self, http):
        r = http.post("/orchestrate", json=_orchestrate_payload(
            selected_resource_ids=["search_and_rescue"], incident_id="INC-SINGLE",
        ))
        body = _assert_pipeline_ok(r)
        assert list(body["requirement"]["requirements"].keys()) == ["search_and_rescue"]

    def test_ten_resources(self, http):
        ids = [
            "drinking_water", "food_dry_rations", "medicines_medical_supplies",
            "first_aid_trauma", "emergency_shelter_relief_camp",
            "clothing_blankets_warmth", "search_and_rescue",
            "boat_water_rescue", "evacuation_transport", "tools_equipment",
        ]
        r = http.post("/orchestrate", json=_orchestrate_payload(
            selected_resource_ids=ids, incident_id="INC-TEN",
        ))
        body = _assert_pipeline_ok(r)
        assert len(body["requirement"]["requirements"]) == 10

    def test_calculation_details_present(self, http):
        r = http.post("/orchestrate", json=_orchestrate_payload(
            selected_resource_ids=["drinking_water"], incident_id="INC-DETAILS",
        ))
        body = _assert_pipeline_ok(r)
        details = body["requirement"]["calculation_details"]["drinking_water"]
        assert "baseline_quantity" in details
        assert "demand_base" in details
        assert "adjustment_factor" in details

    def test_allocation_has_required_allocated_shortage(self, http):
        r = http.post("/orchestrate", json=_orchestrate_payload(
            selected_resource_ids=["drinking_water"], incident_id="INC-ALLOC",
        ))
        body = _assert_pipeline_ok(r)
        alloc = body["allocation"]
        for key in ["required_resources", "allocated_resources", "remaining_shortage", "allocation_status"]:
            assert key in alloc

    def test_priority_in_allocation_result(self, http):
        r = http.post("/orchestrate", json=_orchestrate_payload(
            priority="CRITICAL", selected_resource_ids=["drinking_water"],
            incident_id="INC-PRIO",
        ))
        body = _assert_pipeline_ok(r)
        alloc = body["allocation"]
        assert alloc["normalized_priority"] == 1.0

    def test_localized_scope(self, http):
        r = http.post("/orchestrate", json=_orchestrate_payload(
            affected_population=3, incident_scope="localized",
            selected_resource_ids=["drinking_water", "first_aid_trauma"],
            incident_id="INC-LOCAL",
        ))
        body = _assert_pipeline_ok(r)
        reqs = body["requirement"]["requirements"]
        assert reqs["drinking_water"] > 0
        assert reqs["first_aid_trauma"] > 0


# -------------------------------------------------------
# POST /orchestrate — validation errors (422)
# -------------------------------------------------------

class TestOrchestrationValidation:

    def test_missing_incident_id(self, http):
        payload = _orchestrate_payload()
        del payload["incident_id"]
        assert http.post("/orchestrate", json=payload).status_code == 422

    def test_invalid_severity_above_one(self, http):
        assert http.post("/orchestrate", json=_orchestrate_payload(severity=1.5)).status_code == 422

    def test_negative_severity(self, http):
        assert http.post("/orchestrate", json=_orchestrate_payload(severity=-0.1)).status_code == 422

    def test_invalid_priority(self, http):
        p = _orchestrate_payload()
        p["priority"] = "INVALID"
        assert http.post("/orchestrate", json=p).status_code == 422

    def test_empty_body(self, http):
        assert http.post("/orchestrate", json={}).status_code == 422

    def test_zero_affected_population(self, http):
        assert http.post("/orchestrate", json=_orchestrate_payload(affected_population=0)).status_code == 422


# -------------------------------------------------------
# POST /resource/allocate — isolated from Agent Assignment
# -------------------------------------------------------

class TestResourceAllocate:

    def test_allocate_single_incident(self, http):
        payload = {
            "incident_id": "INC-ALLOC-01",
            "incident_type": "FLOOD",
            "location": {"latitude": 19.076, "longitude": 72.878},
            "locality": {
                "name": "Test", "population": 10000,
                "population_density": 8000, "affected_population": 50,
            },
            "severity": 0.6, "estimated_duration_hours": 8,
            "urgency": 0.5, "priority": "MODERATE",
            "selected_resource_ids": ["drinking_water", "food_dry_rations"],
        }
        r = http.post("/resource/allocate", json=payload)
        assert r.status_code == 200
        body = r.json()
        assert body["allocated_resources"]["drinking_water"] > 0
        assert body["required_resources"]["drinking_water"] > 0

    def test_allocate_batch_priority_ordering(self, http):
        base = {
            "incident_type": "FLOOD",
            "location": {"latitude": 19.076, "longitude": 72.878},
            "locality": {
                "name": "Test", "population": 10000,
                "population_density": 8000, "affected_population": 30,
            },
            "severity": 0.5, "estimated_duration_hours": 6,
            "selected_resource_ids": ["drinking_water"],
        }
        incidents = [
            {**base, "incident_id": "B-LOW", "urgency": 0.1, "priority": "LOW"},
            {**base, "incident_id": "B-CRIT", "urgency": 0.9, "priority": "CRITICAL"},
        ]
        r = http.post("/resource/allocate/batch", json=incidents)
        assert r.status_code == 200
        results = r.json()
        assert results[0]["incident_id"] == "B-CRIT"

    def test_allocate_all_30_resources(self, http):
        payload = {
            "incident_id": "INC-30-ALLOC",
            "incident_type": "ALL",
            "location": {"latitude": 19.076, "longitude": 72.878},
            "locality": {
                "name": "Test", "population": 18000,
                "population_density": 8000, "affected_population": 50,
            },
            "severity": 0.5, "estimated_duration_hours": 12,
            "urgency": 0.5, "priority": "HIGH",
        }
        r = http.post("/resource/allocate", json=payload)
        assert r.status_code == 200
        body = r.json()
        assert len(body["required_resources"]) == 30
        assert len(body["allocated_resources"]) == 30
        assert len(body["remaining_shortage"]) == 30

    def test_allocate_legacy_ids(self, http):
        payload = {
            "incident_id": "INC-LEGACY",
            "incident_type": "FLOOD",
            "location": {"latitude": 19.076, "longitude": 72.878},
            "locality": {
                "name": "Test", "population": 10000,
                "population_density": 8000, "affected_population": 50,
            },
            "severity": 0.5, "estimated_duration_hours": 8,
            "urgency": 0.5, "priority": "MODERATE",
            "selected_resource_ids": ["water", "food", "medical_kits"],
        }
        r = http.post("/resource/allocate", json=payload)
        assert r.status_code == 200
        reqs = r.json()["required_resources"]
        assert "drinking_water" in reqs
        assert "food_dry_rations" in reqs
        assert "medicines_medical_supplies" in reqs

    def test_allocate_partial_fulfillment(self, http):
        payload = {
            "incident_id": "INC-HUGE",
            "incident_type": "FLOOD",
            "location": {"latitude": 19.076, "longitude": 72.878},
            "locality": {
                "name": "Test", "population": 100000,
                "population_density": 8000, "affected_population": 50000,
            },
            "severity": 0.8, "estimated_duration_hours": 24,
            "urgency": 0.8, "priority": "CRITICAL",
            "selected_resource_ids": ["drinking_water"],
        }
        r = http.post("/resource/allocate", json=payload)
        assert r.status_code == 200
        body = r.json()
        assert body["allocation_status"] == "PARTIALLY_FULFILLED"
        assert body["remaining_shortage"]["drinking_water"] > 0
        assert body["allocated_resources"]["drinking_water"] < body["required_resources"]["drinking_water"]

    def test_allocate_cash_assistance_blocked(self, http):
        payload = {
            "incident_id": "INC-CASH",
            "incident_type": "FLOOD",
            "location": {"latitude": 19.076, "longitude": 72.878},
            "locality": {
                "name": "Test", "population": 10000,
                "population_density": 8000, "affected_population": 50,
            },
            "severity": 0.5, "estimated_duration_hours": 12,
            "urgency": 0.5, "priority": "HIGH",
            "selected_resource_ids": ["cash_assistance"],
        }
        r = http.post("/resource/allocate", json=payload)
        assert r.status_code == 200
        assert r.json()["required_resources"]["cash_assistance"] == 0.0

    def test_allocate_service_resource_no_warehouse_stock(self, http):
        payload = {
            "incident_id": "INC-DBM",
            "incident_type": "FLOOD",
            "location": {"latitude": 19.076, "longitude": 72.878},
            "locality": {
                "name": "Test", "population": 10000,
                "population_density": 8000, "affected_population": 50,
            },
            "severity": 0.5, "estimated_duration_hours": 12,
            "urgency": 0.5, "priority": "HIGH",
            "selected_resource_ids": ["dead_body_management"],
        }
        r = http.post("/resource/allocate", json=payload)
        assert r.status_code == 200
        body = r.json()
        assert body["required_resources"]["dead_body_management"] > 0
        # No warehouse carries this → allocated 0, full shortage
        assert body["allocated_resources"]["dead_body_management"] == 0
        assert body["remaining_shortage"]["dead_body_management"] == body["required_resources"]["dead_body_management"]


# -------------------------------------------------------
# POST /orchestrate/from-jev — JEV adapter
# -------------------------------------------------------

class TestJevAdapterLive:

    def test_localized_building_collapse_3_people(self, http):
        payload = _jev_payload(
            severity=3, urgency=3, priority="P1",
            wide_area_status="localized",
            selected_resources=["search_and_rescue", "first_aid_trauma", "emergency_medical_care"],
            affected_population=3, incident_id="JEV-COLLAPSE",
            incident_type="BUILDING_COLLAPSE",
        )
        r = http.post("/orchestrate/from-jev", json=payload)
        body = _assert_pipeline_ok(r)
        reqs = body["requirement"]["requirements"]
        assert len(reqs) == 3
        assert reqs["search_and_rescue"] == 1.0
        assert reqs["emergency_medical_care"] == 1.0

    def test_wide_area_flood(self, http):
        payload = _jev_payload(
            severity=2, urgency=2, priority="P2",
            wide_area_status="wide",
            selected_resources=["drinking_water", "food_dry_rations", "emergency_shelter_relief_camp"],
            affected_population=500, incident_id="JEV-FLOOD",
        )
        r = http.post("/orchestrate/from-jev", json=payload)
        body = _assert_pipeline_ok(r)
        assert body["requirement"]["requirements"]["drinking_water"] > 0

    def test_multiple_resources(self, http):
        payload = _jev_payload(
            selected_resources=["drinking_water", "food_dry_rations", "medicines_medical_supplies",
                                "first_aid_trauma", "search_and_rescue"],
            incident_id="JEV-MULTI",
        )
        r = http.post("/orchestrate/from-jev", json=payload)
        body = _assert_pipeline_ok(r)
        assert len(body["requirement"]["requirements"]) == 5

    def test_invalid_severity_rejected(self, http):
        assert http.post("/orchestrate/from-jev", json=_jev_payload(severity=5)).status_code == 422

    def test_invalid_urgency_rejected(self, http):
        assert http.post("/orchestrate/from-jev", json=_jev_payload(urgency=-1)).status_code == 422

    def test_unknown_resource_skipped(self, http):
        payload = _jev_payload(
            selected_resources=["drinking_water", "magic_wand"],
            incident_id="JEV-UNKNOWN",
        )
        r = http.post("/orchestrate/from-jev", json=payload)
        body = _assert_pipeline_ok(r)
        reqs = body["requirement"]["requirements"]
        assert "drinking_water" in reqs
        assert "magic_wand" not in reqs

    def test_missing_affected_population(self, http):
        payload = _jev_payload()
        del payload["locality"]["affected_population"]
        assert http.post("/orchestrate/from-jev", json=payload).status_code == 422

    def test_ambiguous_scope(self, http):
        payload = _jev_payload(
            wide_area_status="ambiguous",
            selected_resources=["drinking_water"],
            incident_id="JEV-AMBIG",
        )
        r = http.post("/orchestrate/from-jev", json=payload)
        _assert_pipeline_ok(r)

    def test_cash_assistance_blocked(self, http):
        payload = _jev_payload(
            selected_resources=["cash_assistance"],
            incident_id="JEV-CASH",
        )
        r = http.post("/orchestrate/from-jev", json=payload)
        body = _assert_pipeline_ok(r)
        assert body["requirement"]["requirements"]["cash_assistance"] == 0.0
        assert body["requirement"]["calculation_details"]["cash_assistance"]["blocked"] is True

    def test_empty_resources_all_30(self, http):
        payload = _jev_payload(selected_resources=[], incident_id="JEV-EMPTY", incident_type="ALL")
        r = http.post("/orchestrate/from-jev", json=payload)
        body = _assert_pipeline_ok(r)
        assert len(body["requirement"]["requirements"]) == 30

    def test_severity_s0_to_s3(self, http):
        for s in range(4):
            r = http.post("/orchestrate/from-jev", json=_jev_payload(
                severity=s, selected_resources=["drinking_water"], incident_id=f"JEV-S{s}",
            ))
            _assert_pipeline_ok(r)

    def test_priority_p1_through_p4(self, http):
        for p in ["P1", "P2", "P3", "P4"]:
            r = http.post("/orchestrate/from-jev", json=_jev_payload(
                priority=p, selected_resources=["drinking_water"], incident_id=f"JEV-{p}",
            ))
            _assert_pipeline_ok(r)

    def test_priority_does_not_inflate_quantity(self, http):
        """P1 vs P4 same incident → same required quantity (tested via /resource/allocate)."""
        base = {
            "incident_type": "FLOOD",
            "location": {"latitude": 19.076, "longitude": 72.878},
            "locality": {
                "name": "Test", "population": 10000,
                "population_density": 8000, "affected_population": 100,
            },
            "severity": 0.667, "estimated_duration_hours": 12,
            "urgency": 0.333,
            "selected_resource_ids": ["drinking_water"],
        }
        r_crit = http.post("/resource/allocate", json={**base, "incident_id": "P-CRIT", "priority": "CRITICAL"})
        r_low = http.post("/resource/allocate", json={**base, "incident_id": "P-LOW", "priority": "LOW"})
        assert r_crit.status_code == 200
        assert r_low.status_code == 200
        # Required quantities must be identical — priority only affects allocation order
        assert r_crit.json()["required_resources"]["drinking_water"] == r_low.json()["required_resources"]["drinking_water"]
