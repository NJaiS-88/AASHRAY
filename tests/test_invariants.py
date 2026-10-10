"""
test_invariants.py -- Unit tests for Invariants B1 through B9
Enforces the mandatory invariants from Section B of the JEV v3 Robustness Plan.
Fail build if any test fails!
"""

import sys
import os
import json
import re
import pytest

# Ensure import paths
TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(TESTS_DIR, ".."))
JEV_DIR = os.path.join(ROOT_DIR, "NEW HYPOTHESIS", "jev + llm")
NEW_FILES_DIR = os.path.join(ROOT_DIR, "new files")

for p in [JEV_DIR, NEW_FILES_DIR, ROOT_DIR]:
    if os.path.exists(p) and p not in sys.path:
        sys.path.insert(0, p)

from jev_v3_triage import (
    execute_jev_v3_triage,
    evaluate_severity_and_urgency,
    LIFE_CRITICAL_RESOURCES,
    RESOURCE_CRITERIA_QUESTIONS
)
from relevance_gate import (
    run_relevance_gate,
    is_chunk_hazard_compatible,
    get_readable_doc_title
)
from stage2_v3_generator import build_expert_judgment_plan
from agency_directory import get_agencies_for_location, get_allowed_agency_names

# ──────────────────────────────────────────────────────────────────────────────
# Invariant B1: Life-Critical Severity/Urgency Floors
# ──────────────────────────────────────────────────────────────────────────────
def test_invariant_b1_life_critical_floors():
    """
    Any life_critical resource in CONFIRMED or LIKELY forces severity at least S2
    and urgency at least U2.
    """
    # Test with drinking_water (life_critical) in confirmed set
    confirmed_set = {"drinking_water"}
    facts = {"people_affected": None, "people_trapped": None, "people_injured_reported": None}
    assessment = evaluate_severity_and_urgency("Minor leak reported", facts, confirmed_set)
    
    assert assessment["severity"]["numeric"] >= 2, f"Expected S2+ but got {assessment['severity']['level']}"
    assert assessment["urgency"]["numeric"] >= 2, f"Expected U2+ but got {assessment['urgency']['level']}"

def test_invariant_b1_sar_with_trapped_forces_s2_u3_p1():
    """
    search_and_rescue CONFIRMED with a trapped person forces S2 or higher, U3 and priority P1.
    """
    confirmed_set = {"search_and_rescue"}
    facts = {"people_affected": 5, "people_trapped": 2, "people_injured_reported": 0}
    assessment = evaluate_severity_and_urgency("People trapped under fallen slab", facts, confirmed_set)
    
    assert assessment["severity"]["numeric"] >= 2, f"Expected S2+ but got {assessment['severity']['level']}"
    assert assessment["urgency"]["numeric"] == 3, f"Expected U3 but got {assessment['urgency']['level']}"
    assert assessment["priority"]["level"] == "P1", f"Expected P1 but got {assessment['priority']['level']}"

# ──────────────────────────────────────────────────────────────────────────────
# Invariant B2: Unified Single Assessment Object
# ──────────────────────────────────────────────────────────────────────────────
def test_invariant_b2_single_unified_assessment_object():
    """
    Severity, urgency, priority and every time window come from one object.
    The UI and text can never disagree.
    """
    msg = "Flash flood stranded 20 families on high school terrace in Wayanad."
    triage = execute_jev_v3_triage(msg)
    assess = triage["assessment"]
    
    assert "severity" in assess
    assert "urgency" in assess
    assert "priority" in assess
    assert "window" in assess["urgency"]
    assert "driving_cue" in assess
    
    # Verify consistent typing
    assert assess["severity"]["level"].startswith("S")
    assert assess["urgency"]["level"].startswith("U")
    assert assess["priority"]["level"].startswith("P")

# ──────────────────────────────────────────────────────────────────────────────
# Invariant B3: Agency Directory Whitelist & Document Titles
# ──────────────────────────────────────────────────────────────────────────────
def test_invariant_b3_agency_directory_and_doc_titles():
    """
    No agency name appears unless it comes from the agency directory or a retrieved chunk.
    Never show 'a.pdf'.
    """
    agencies = get_agencies_for_location("kerala", "wayanad")
    allowed_names = get_allowed_agency_names("kerala", "wayanad")
    assert len(agencies) > 0
    assert "national emergency helpline (erss)" in allowed_names or any("112" in name for name in allowed_names)

    # Document titles must be human readable, never 'a.pdf'
    title = get_readable_doc_title("a.pdf")
    assert title != "a.pdf"
    assert "Earthquake" in title

# ──────────────────────────────────────────────────────────────────────────────
# Invariant B4: Relevance Gate
# ──────────────────────────────────────────────────────────────────────────────
def test_invariant_b4_relevance_gate_drops_incompatible_hazard():
    """
    Every chunk shown or cited passed the relevance gate.
    Guidance written for a different hazard must never reach an incident it does not fit.
    """
    # Avalanche document on flood incident must be dropped
    assert not is_chunk_hazard_compatible("landslidessnowavalanches.pdf", "fire_or_explosion")

    candidate_chunks = [
        {
            "chunk_id": "c1",
            "source_file": "landslidessnowavalanches.pdf",
            "page": 10,
            "chunk_text": "Snow avalanche artillery control and explosives blasting on mountain pass."
        },
        {
            "chunk_id": "c2",
            "source_file": "floods.pdf",
            "page": 45,
            "chunk_text": "Deploy motorized boats and inflatable rescue craft to evacuate marooned flood victims."
        }
    ]
    passed = run_relevance_gate(candidate_chunks, "Flood stranded villagers", "flood", cutoff=0.40)
    passed_ids = [p["chunk_id"] for p in passed]
    
    assert "c1" not in passed_ids, "Hazard-incompatible avalanche chunk should have been dropped"
    assert "c2" in passed_ids, "Compatible flood rescue chunk should pass"

# ──────────────────────────────────────────────────────────────────────────────
# Invariant B5: Tagged GROUNDED or EXPERT-JUDGMENT
# ──────────────────────────────────────────────────────────────────────────────
def test_invariant_b5_tagged_grounded_or_expert_judgment():
    """
    Every plan statement is tagged GROUNDED (cites a chunk id) or EXPERT-JUDGMENT (no chunk).
    """
    triage = execute_jev_v3_triage("Severe building collapse with trapped workers")
    excerpts = [
        {
            "eid": "E1",
            "chunk_id": "chk_ndma_01",
            "document_title": "NDMA Guidelines: Management of Earthquakes",
            "page": 12,
            "chunk_text": "Search and rescue squads extricate trapped victims from concrete voids."
        }
    ]
    agencies = get_agencies_for_location("maharashtra", "mumbai")
    plan = build_expert_judgment_plan(triage, excerpts, agencies)

    for r in plan["resources"]:
        assert r["source"] in ["GROUNDED", "EXPERT-JUDGMENT"]
        if r["source"] == "GROUNDED":
            assert len(r["excerpt_ids"]) > 0

# ──────────────────────────────────────────────────────────────────────────────
# Invariant B6: Non-Selected Reason Code, Jev Prob & Cutoff
# ──────────────────────────────────────────────────────────────────────────────
def test_invariant_b6_non_selected_resources_have_reasons_and_cutoffs():
    """
    Every non-selected resource shows a reason code, its Jev probability and its cutoff.
    """
    triage = execute_jev_v3_triage("Water bill inquiry for apartment")
    not_sel = triage["not_selected_resources"]
    assert len(not_sel) > 0
    
    for item in not_sel:
        assert "resource" in item
        assert "reason" in item
        assert "reason_code" in item
        assert "jev_probability" in item
        assert "cutoff" in item
        assert isinstance(item["jev_probability"], float)

# ──────────────────────────────────────────────────────────────────────────────
# Invariant B7: No Quantities, Formulas or Norms in Report
# ──────────────────────────────────────────────────────────────────────────────
def test_invariant_b7_no_quantities_or_formulas():
    """
    No quantities, formulas or per-person norms anywhere in the report.
    """
    triage = execute_jev_v3_triage("Severe flood marooned 50 families")
    plan = build_expert_judgment_plan(triage, [], [])

    forbidden_patterns = [
        r"\b15\s*L/person\b",
        r"\b2100\s*kcal\b",
        r"\b3\.5\s*m²\b",
        r"\bformula\b",
        r"per-person norm",
        r"Sphere min"
    ]

    report_str = json.dumps(plan)
    for pat in forbidden_patterns:
        assert not re.search(pat, report_str, re.IGNORECASE), f"Forbidden quantity formula pattern '{pat}' found in report!"

# ──────────────────────────────────────────────────────────────────────────────
# Invariant B8: Census Only for Wide-Area Incidents
# ──────────────────────────────────────────────────────────────────────────────
def test_invariant_b8_census_only_when_wide_area_true():
    """
    Census runs only when wide_area is true, and is never printed as 'people affected'.
    """
    # Localized incident
    local_msg = "One person slipped in their bathroom and needs an ambulance."
    triage_local = execute_jev_v3_triage(local_msg)
    assert not triage_local["wide_area"]["is_wide_area"]
    assert triage_local["census_context"] is None, "Localized incident must NOT run census"

    # Wide-area incident
    wide_msg = "Entire Wayanad district submerged by flash floods affecting 50 villages."
    triage_wide = execute_jev_v3_triage(wide_msg, district_hint="Wayanad")
    assert triage_wide["wide_area"]["is_wide_area"]
    if triage_wide["census_context"]:
        # Verify it is not labeled as people affected (Invariant B8)
        assert "people affected" not in triage_wide["census_context"].get("area_population_context", "").lower()

# ──────────────────────────────────────────────────────────────────────────────
# Invariant B9: Raw JEV Response Logging
# ──────────────────────────────────────────────────────────────────────────────
def test_invariant_b9_raw_jev_logging():
    """
    Every raw Jev response is logged with the model version.
    """
    triage = execute_jev_v3_triage("Test emergency rescue scenario")
    assert "model_version" in triage
    assert triage["model_version"] == "typesafe-jev-v3-prompted"
    assert "raw_log_file" in triage
    assert os.path.exists(triage["raw_log_file"])


def test_animal_veterinary_and_typo_resilience():
    """
    Validates that animal distress calls activate livestock_fodder_veterinary with high score,
    clear the 0.75 confirmed threshold, and do not falsely select human medical emergency resources as CONFIRMED.
    """
    msg = "my dog is injured in rain."
    triage = execute_jev_v3_triage(msg)
    selected = {r["resource"]: r for r in triage["selected_resources"]}

    assert "livestock_fodder_veterinary" in selected, "livestock_fodder_veterinary must be selected for injured pet/dog"
    assert selected["livestock_fodder_veterinary"]["band"] == "CONFIRMED"
    assert selected["livestock_fodder_veterinary"]["jev_probability"] >= 0.75

    # Ensure human emergency medical care is not falsely selected as CONFIRMED for an animal
    assert "emergency_medical_care" not in selected or selected["emergency_medical_care"]["band"] != "CONFIRMED"

