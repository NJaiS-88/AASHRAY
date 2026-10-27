"""
test_pre_rag_gate.py -- Tests for Pre-RAG Intake, Completeness Check & Severity Classification Gate
Validates:
1. Initial classification into Critical, Non-Critical, Uncertain
2. Completeness & missing information detection
3. Clarifying question generation for Uncertain / Non-Critical
4. Re-evaluation when caller provides follow-up answer
5. Escalation: Critical -> allocate resources -> triggers RAG
6. De-escalation / Low-tier routing: Non-Critical -> route to low-tier support -> bypasses RAG
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

from pre_rag_gate import classify_pre_rag, re_evaluate_pre_rag
from pipeline_b import DisasterRAGPipelineB


def test_initial_classification_uncertain_leg_stuck():
    """
    User: 'My leg is stuck.'
    Must be classified as Uncertain, is_complete=False, can_proceed_to_rag=False,
    and generate clarifying questions including bleeding/swelling/sensation.
    """
    res = classify_pre_rag("My leg is stuck.")
    
    assert res["severity"] == "Uncertain"
    assert res["can_proceed_to_rag"] is False
    assert res["action"] == "ask_clarifying_questions"
    assert res["is_complete"] is False
    assert len(res["clarifying_questions"]) >= 1
    
    # Verify user's specific requested follow-up question is covered
    questions_combined = " ".join(res["clarifying_questions"]).lower()
    assert any(term in questions_combined for term in ["bleeding", "swollen", "sensation", "trapping", "pinning"])


def test_re_evaluation_escalation_to_critical():
    """
    Caller: 'My leg is stuck.'
    Clarification: 'It is bleeding heavily and crushed under concrete slab'
    Must escalate to Critical, action='allocate_resources', can_proceed_to_rag=True.
    """
    initial = "My leg is stuck."
    clarification = "It is bleeding heavily and crushed under a concrete slab at MG Road metro pillar 12."
    
    res = re_evaluate_pre_rag(initial_query=initial, follow_up_answer=clarification)
    
    assert res["severity"] == "Critical"
    assert res["can_proceed_to_rag"] is True
    assert res["action"] == "allocate_resources"
    assert res["escalated"] is True
    assert res["support_tier"] == "critical_emergency_dispatch"


def test_re_evaluation_remains_non_critical():
    """
    Caller: 'My leg is stuck.'
    Clarification: 'No bleeding, just shoe stuck in bicycle pedal in room'
    Must route to Non-Critical / low-tier support, can_proceed_to_rag=False.
    """
    initial = "My leg is stuck."
    clarification = "No bleeding, no pain, just my sneaker shoe is caught in my bicycle pedal in the living room."
    
    res = re_evaluate_pre_rag(initial_query=initial, follow_up_answer=clarification)
    
    assert res["severity"] == "Non-Critical"
    assert res["can_proceed_to_rag"] is False
    assert res["action"] == "route_to_low_tier_support"
    assert res["escalated"] is False
    assert res["support_tier"] == "low_tier_support"


def test_obvious_critical_emergency_bypasses_questions():
    """
    A clearly severe life-threatening disaster is classified as Critical immediately.
    """
    query = "Four-story residential building collapsed into rubble in Ghatkopar. Ten construction workers trapped inside the basement slab screaming for help."
    res = classify_pre_rag(query)
    
    assert res["severity"] == "Critical"
    assert res["can_proceed_to_rag"] is True
    assert res["action"] == "allocate_resources"


def test_obvious_non_critical_routes_to_low_tier():
    """
    A routine municipal inquiry is classified as Non-Critical and routed to low-tier support.
    """
    query = "How do I download my electricity bill receipt from the online municipal portal?"
    res = classify_pre_rag(query)
    
    assert res["severity"] == "Non-Critical"
    assert res["can_proceed_to_rag"] is False
    assert res["action"] == "route_to_low_tier_support"


def test_pipeline_b_pre_rag_integration_uncertain():
    """
    Pipeline B stops BEFORE RAG when query is uncertain, returning clarifying questions.
    """
    pipe = DisasterRAGPipelineB()
    out = pipe.run(
        scenario_id="TEST-PRE-RAG-UNCERTAIN",
        scenario="My leg is stuck."
    )
    
    assert out is not None
    assert out["can_proceed_to_rag"] is False
    assert out["needs_clarification"] is True
    assert out["action"] == "ask_clarifying_questions"
    assert len(out["clarifying_questions"]) >= 1
    assert len(out["resources"]) == 0
    assert out["latency"]["retrieval_ms"] == 0.0  # Proves RAG retrieval was NOT called!


def test_pipeline_b_pre_rag_integration_escalation():
    """
    Pipeline B with clarification answer escalates to Critical and proceeds to full RAG.
    """
    pipe = DisasterRAGPipelineB()
    out = pipe.run(
        scenario_id="TEST-PRE-RAG-ESCALATE",
        scenario="My leg is stuck.",
        clarification_answer="It is bleeding heavily and crushed under concrete slab with water rising.",
        district_hint="Bengaluru"
    )
    
    assert out is not None
    assert out["can_proceed_to_rag"] is True
    assert out["needs_clarification"] is False
    assert out["action"] == "allocate_resources"
    assert len(out["selected_resources"]) > 0
    assert out["latency"]["retrieval_ms"] >= 0.0
