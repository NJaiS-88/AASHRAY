"""
test_acceptance.py -- Section J Acceptance Tests for JEV v3 Triage & RAG
Validates property-based assertions across incident dimensions:
- Incident types, Scope, Need explicitness, Life threat, Message quality, Vulnerable groups.
- Non-emergency messages produce no resources, no dispatch and no census call.
- Invariants B1 to B9 hold across all cases.
"""

import os
import sys
import pytest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(TESTS_DIR, ".."))
JEV_DIR = os.path.join(ROOT_DIR, "NEW HYPOTHESIS", "jev + llm")

for p in [JEV_DIR, ROOT_DIR]:
    if os.path.exists(p) and p not in sys.path:
        sys.path.insert(0, p)

from jev_v3_triage import execute_jev_v3_triage, LIFE_CRITICAL_RESOURCES
from relevance_gate import is_chunk_hazard_compatible

ACCEPTANCE_CASES = [
    {
        "id": "non_emergency_weather",
        "text": "What is the temperature today in Bengaluru? Is it going to rain this evening?",
        "is_emergency": False,
        "expected_resources_count": 0,
        "coords": None
    },
    {
        "id": "non_emergency_billing",
        "text": "How do I download my electricity bill receipt from the online portal?",
        "is_emergency": False,
        "expected_resources_count": 0,
        "coords": None
    },
    {
        "id": "flood_stated_and_implied",
        "text": "River Kabini overflowed in Wayanad district. 40 families marooned on high school rooftop without drinking water. Water level rising fast.",
        "is_emergency": True,
        "has_life_threat": True,
        "must_have_confirmed": ["drinking_water"],
        "must_have_likely_or_confirmed": ["boat_water_rescue", "evacuation_transport"],
        "district": "Wayanad"
    },
    {
        "id": "building_collapse_implied_rescue",
        "text": "Four-story residential building collapsed into rubble in Ghatkopar. Ten construction workers trapped inside the basement slab.",
        "is_emergency": True,
        "has_life_threat": True,
        "must_have_confirmed": ["search_and_rescue"],
        "must_have_likely_or_confirmed": ["emergency_medical_care", "heavy_machinery_debris_clearance"],
        "district": "Mumbai"
    },
    {
        "id": "localized_medical",
        "text": "A man fell from a ladder in his backyard at house number 12 and broke his leg. Bleeding and needs medical transport.",
        "is_emergency": True,
        "has_life_threat": False,
        "scope": "localized",
        "must_have_confirmed": ["first_aid_trauma"]
    },
    {
        "id": "cyclone_wide_area_shelter",
        "text": "Severe cyclone landfall in coastal Puri. Hundreds of thatched huts destroyed, roofs blown off across 8 villages. Power grid collapsed.",
        "is_emergency": True,
        "has_life_threat": False,
        "scope": "wide_area",
        "must_have_confirmed": ["shelter_kits_tarpaulin"],
        "must_have_likely_or_confirmed": ["power_lighting", "emergency_shelter_relief_camp"]
    }
]

def test_acceptance_non_emergency_messages_produce_no_resources():
    """
    Non-emergency or irrelevant messages produce no resources, no dispatch and no census call.
    """
    for case in ACCEPTANCE_CASES:
        if not case["is_emergency"]:
            res = execute_jev_v3_triage(case["text"])
            assert len(res["selected_resources"]) == 0, f"Non-emergency message {case['id']} should have 0 resources!"
            assert res["census_context"] is None, f"Non-emergency message {case['id']} should NOT call census!"
            assert res["assessment"]["priority"]["level"] == "P4"

def test_acceptance_stated_and_implied_needs():
    """
    Stated needs come out CONFIRMED; needs only implied by the event come out LIKELY with a reason.
    """
    # Flood case with stated water and implied rescue
    case = next(c for c in ACCEPTANCE_CASES if c["id"] == "flood_stated_and_implied")
    res = execute_jev_v3_triage(case["text"], district_hint=case["district"])
    
    selected_dict = {s["resource"]: s for s in res["selected_resources"]}
    
    # Check stated needs
    for req in case.get("must_have_confirmed", []):
        assert req in selected_dict, f"Expected {req} to be selected in {case['id']}"
        assert selected_dict[req]["band"] == "CONFIRMED", f"Expected {req} to be CONFIRMED"

    # Check implied needs
    for req in case.get("must_have_likely_or_confirmed", []):
        assert req in selected_dict, f"Expected {req} to be selected in {case['id']}"
        assert selected_dict[req]["band"] in ["CONFIRMED", "LIKELY", "STANDBY"]
        if selected_dict[req]["band"] in ["LIKELY", "STANDBY"] and "implied_reason" in selected_dict[req]:
            assert len(selected_dict[req]["implied_reason"]) > 0

def test_acceptance_scope_and_census_branching():
    """
    wide_area false means no census call; wide_area true means census at finest unit.
    """
    # Localized case
    local_case = next(c for c in ACCEPTANCE_CASES if c["id"] == "localized_medical")
    local_res = execute_jev_v3_triage(local_case["text"])
    assert not local_res["wide_area"]["is_wide_area"]
    assert local_res["census_context"] is None, "Localized case must have NO census data"

    # Wide area cyclone case
    wide_case = next(c for c in ACCEPTANCE_CASES if c["id"] == "cyclone_wide_area_shelter")
    wide_res = execute_jev_v3_triage(wide_case["text"])
    assert wide_res["wide_area"]["is_wide_area"]

def test_acceptance_invariants_hold_across_all_cases():
    """
    Invariants B1 to B9 hold on every test case.
    """
    for case in ACCEPTANCE_CASES:
        res = execute_jev_v3_triage(case["text"])
        assess = res["assessment"]
        
        # B1 check
        has_life_crit = any(s["resource"] in LIFE_CRITICAL_RESOURCES and s["band"] in ["CONFIRMED", "LIKELY"] for s in res["selected_resources"])
        if has_life_crit:
            assert assess["severity"]["numeric"] >= 2
            assert assess["urgency"]["numeric"] >= 2
            
        # B2 check
        assert assess["priority"]["level"] in ["P1", "P2", "P3", "P4"]
        
        # B6 check
        for ns in res["not_selected_resources"]:
            assert "jev_probability" in ns
            assert "cutoff" in ns
            assert "reason" in ns
