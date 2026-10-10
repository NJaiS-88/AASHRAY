"""
pre_rag_gate.py -- Pre-RAG Intake, Completeness Check & Severity Classification Gate
Evaluates queries BEFORE passing them into the RAG pipeline.

Requirements:
1. Completeness & Missing Info Check
   - Checks whether the query is complete or missing vital operational info.
2. Initial Severity Classification:
   - Critical: life-threatening or urgent emergency -> proceed to RAG & resource allocation.
   - Non-Critical: inconvenience, financial request, minor issue -> route to low-tier support / polite guidance.
   - Uncertain: unclear, needs more info -> generate follow-up clarifying questions.
3. Follow-Up Question Generation:
   - For Non-Critical or Uncertain, instruct LLM to generate targeted clarifying questions.
   - E.g. User: "My leg is stuck." -> LLM: "Can you tell me if your leg is bleeding, swollen, or losing sensation?"
4. Re-Evaluation:
   - When the user answers, re-run classification.
   - If severity escalates -> allocate resources (proceed to full RAG).
   - If not -> route to low-tier support.
"""

import os
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
import json
import re
import requests
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(_DIR, ".."))
WORKSPACE_ROOT = os.path.abspath(os.path.join(_DIR, "..", ".."))

for p in [
    os.path.join(WORKSPACE_ROOT, ".env"),
    os.path.join(ROOT_DIR, ".env"),
    os.path.join(_DIR, ".env")
]:
    load_dotenv(p)

SESSION = requests.Session()

SYSTEM_INSTRUCTION = """Classify the user's request as Critical, Non-Critical, or Uncertain.
Critical = life-threatening or urgent emergency.
Non-Critical = inconvenience, financial request, minor issue.
Uncertain = unclear, needs more info.

You are the Pre-RAG Triage Gatekeeper and Completeness Evaluator for AASHRAY Emergency Response.
Your job is to assess the caller's message BEFORE it enters the Retrieval-Augmented Generation (RAG) pipeline and emergency resource dispatch.

TASK RULES:
1. COMPLETENESS & MISSING INFORMATION:
   - Check if the caller provided enough information to dispatch life-saving relief:
     a) Specific injury/medical symptoms (e.g. bleeding, fractures, breathing distress, sensation loss)
     b) Physical entrapment or hazard details (e.g. trapped under concrete, rising water, fire, live wire)
     c) Exact location or landmark
     d) Number of persons affected or trapped
   - Identify missing fields in `missing_info` (e.g. ["injury_details", "exact_location", "entrapment_mechanism"]).
   - Set `is_complete` to true if sufficient details exist to respond immediately, false otherwise.

2. SEVERITY CLASSIFICATION:
   - "Critical": Life-threatening or urgent emergency. Immediate threat to human/animal life, acute trauma, structural collapse, rapid flood entrapment, severe fire.
     -> Proceed directly to RAG & allocate resources.
   - "Non-Critical": Inconvenience, financial request, minor issue, administrative inquiry, routine non-life-threatening situation.
     -> Route to low-tier support / polite guidance.
   - "Uncertain": Unclear, vague, brief, or needs more vital info (e.g. "My leg is stuck.", "Help me please", "Water entering room", "I heard a crash"). Life-threat cannot be confirmed nor ruled out without clarification.
     -> Generate clarifying questions.

3. FOLLOW-UP QUESTION GENERATION:
   - If classification is "Uncertain" or "Non-Critical", generate 1 to 3 targeted, highly practical clarifying questions.
   - Example:
     User: "My leg is stuck."
     LLM: "Can you tell me if your leg is bleeding, swollen, or losing sensation? What is pinning your leg, and where are you located?"

4. RE-EVALUATION LOGIC:
   - When caller answers previous clarifying questions:
     Evaluate accumulated context (initial message + caller response).
     - If severity escalates to life-threatening/urgent emergency -> "Critical", action: "allocate_resources", can_proceed_to_rag: true, escalated: true.
     - If situation remains minor/inconvenience -> "Non-Critical", action: "route_to_low_tier_support", can_proceed_to_rag: false, escalated: false.
     - If still ambiguous -> "Uncertain", action: "ask_clarifying_questions", can_proceed_to_rag: false.

OUTPUT FORMAT:
Return strictly a valid JSON object with the following schema:
{
  "severity": "Critical" | "Non-Critical" | "Uncertain",
  "reason": "Detailed rationale explaining why this severity level was assigned",
  "is_complete": true | false,
  "missing_info": ["string"],
  "clarifying_questions": ["string"],
  "action": "allocate_resources" | "ask_clarifying_questions" | "route_to_low_tier_support",
  "can_proceed_to_rag": true | false,
  "escalated": true | false,
  "support_tier": "critical_emergency_dispatch" | "clarification_intake" | "low_tier_support"
}
"""

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

def _get_groq_api_keys() -> List[str]:
    keys = [os.getenv("GROQ_API_KEY")]
    for i in range(1, 21):
        k = os.getenv(f"GROQ_API_KEY{i}")
        if k:
            keys.append(k)
    return [k.strip() for k in keys if k and k.strip()]


def _call_llm(prompt: str) -> Optional[Dict[str, Any]]:
    # 1. Try Groq with all available keys
    keys = _get_groq_api_keys()
    for key in keys:
        try:
            headers = {
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": "openai/gpt-oss-120b",
                "messages": [
                    {"role": "system", "content": SYSTEM_INSTRUCTION},
                    {"role": "user", "content": prompt}
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.1,
                "max_tokens": 800
            }
            resp = SESSION.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=6
            )
            if resp.status_code == 200:
                raw_content = resp.json()["choices"][0]["message"]["content"]
                cleaned = re.sub(r"^```(?:json)?\s*", "", raw_content.strip())
                cleaned = re.sub(r"\s*```$", "", cleaned)
                return json.loads(cleaned)
            elif resp.status_code == 429:
                continue
        except Exception:
            continue

    # 2. Try OpenRouter as immediate fallback
    if OPENROUTER_API_KEY:
        try:
            headers = {
                "Authorization": f"Bearer {OPENROUTER_API_KEY.strip()}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": "meta-llama/llama-3.3-70b-instruct",
                "messages": [
                    {"role": "system", "content": SYSTEM_INSTRUCTION},
                    {"role": "user", "content": prompt}
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.1,
                "max_tokens": 800
            }
            resp = SESSION.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=8
            )
            if resp.status_code == 200:
                raw_content = resp.json()["choices"][0]["message"]["content"]
                cleaned = re.sub(r"^```(?:json)?\s*", "", raw_content.strip())
                cleaned = re.sub(r"\s*```$", "", cleaned)
                return json.loads(cleaned)
        except Exception as e:
            print(f"[Pre-RAG Gate] OpenRouter fallback error: {e}")

    return None


def _deterministic_pre_rag_fallback(
    query: str,
    follow_up_answer: Optional[str] = None,
    history: Optional[List[Dict[str, str]]] = None
) -> Dict[str, Any]:
    """
    Robust rule-based fallback when external LLM API is unavailable.
    Guarantees reliable classification, question generation, and escalation logic.
    """
    full_text = query
    is_re_evaluation = bool(follow_up_answer and follow_up_answer.strip())
    if is_re_evaluation:
        full_text = f"{query}\nCaller clarification: {follow_up_answer}"

    text_lower = full_text.lower().strip()
    answer_lower = (follow_up_answer or "").lower().strip()

    # Explicit critical indicators
    critical_patterns = [
        r"\bbleed(?:ing)?\b", r"\bswollen\b", r"\bsensation\b", r"\bnumb(?:ness)?\b",
        r"\bunconscious\b", r"\bcpr\b", r"\bcollapsed\b", r"\brubble\b", r"\btrapped\b",
        r"\bdrowning\b", r"\bsuffocat(?:ing|ion)\b", r"\bheart attack\b", r"\bstroke\b",
        r"\bcrushed\b", r"\bfire\b", r"\belectrocute\b", r"\bconcrete\b", r"\bheavy slab\b",
        r"\bwater rising\b", r"\bchest pain\b", r"\bseverely injured\b", r"\bfracture\b",
        r"\bbone broken\b", r"\bamputat\b", r"\bhead injury\b", r"\bhurt(?:s|ing)?\b",
        r"\bpain\b", r"\bheavy\b", r"\bcan'?t\s+(?:move|walk|get\s+out)\b", r"\bhelp\b",
        r"\balone\b", r"\bflood\b", r"\bbeam\b", r"\bpillar\b", r"\bwall\b", r"\bunder\b",
        r"\bpin(?:ned)?\b"
    ]

    # Explicit non-critical indicators
    non_critical_patterns = [
        r"\bno\s+bleeding\b", r"\bnot\s+bleeding\b", r"\bno\s+pain\b", r"\bnot\s+hurt\b",
        r"\bjust\s+(?:my\s+)?shoe\b", r"\bbicycle\b", r"\bpedal\b", r"\bminor\b",
        r"\bfine\s+now\b", r"\bno\s+danger\b", r"\bfalse\s+alarm\b", r"\bfinancial\b",
        r"\bcompensation\b", r"\bsubsidy\b", r"\bclaim\b", r"\btax\b", r"\brefund\b",
        r"\bbill\b", r"\bdelay\b", r"\binconvenience\b", r"\bleaking tap\b",
        r"\blost wallet\b", r"\blost key\b", r"\bwifi\b", r"\binternet down\b"
    ]

    has_critical = any(re.search(p, text_lower) for p in critical_patterns)
    has_explicit_non_critical = any(re.search(p, answer_lower) for p in non_critical_patterns) or any(re.search(p, text_lower) for p in non_critical_patterns)

    # Detect leg is stuck specific case
    is_leg_stuck = bool(re.search(r"\b(?:leg|foot|arm|hand)\s+is\s+stuck\b", query.lower()))

    missing_info = []
    if not re.search(r"\b(at|near|road|street|nagar|colony|floor|building|sector|block|pillar|room)\b", text_lower):
        missing_info.append("exact_location")
    if not any(re.search(p, text_lower) for p in [r"\bbleed", r"\bpain", r"\binjur", r"\bswoll", r"\bsensation", r"\bhurt"]):
        missing_info.append("physical_injury_and_sensation")
    if not any(re.search(p, text_lower) for p in [r"\bunder\b", r"\bbetween\b", r"\bpin", r"\bconcrete", r"\bdoor", r"\bdebris", r"\bbeam", r"\bwall"]):
        missing_info.append("entrapment_hazard_mechanism")

    # If re-evaluating:
    if is_re_evaluation:
        # If caller explicitly confirmed non-critical/no injury
        if has_explicit_non_critical and not re.search(r"\bbleed|\bcrush|\btrapped|\bwater rising", answer_lower):
            return {
                "severity": "Non-Critical",
                "reason": f"Clarification indicates non-life-threatening situation ({follow_up_answer}).",
                "is_complete": True,
                "missing_info": [],
                "clarifying_questions": [],
                "action": "route_to_low_tier_support",
                "can_proceed_to_rag": False,
                "escalated": False,
                "support_tier": "low_tier_support"
            }
        else:
            # Caller provided additional query to an entrapment/distress scenario -> escalate!
            return {
                "severity": "Critical",
                "reason": f"Caller provided clarification confirming physical distress and operational details: '{follow_up_answer}'.",
                "is_complete": True,
                "missing_info": [],
                "clarifying_questions": [],
                "action": "allocate_resources",
                "can_proceed_to_rag": True,
                "escalated": True,
                "support_tier": "critical_emergency_dispatch"
            }

    # Initial classification
    if is_leg_stuck and not has_critical:
        return {
            "severity": "Uncertain",
            "reason": "Request reports an entrapment ('leg is stuck') without vital physiological or hazard context.",
            "is_complete": False,
            "missing_info": ["injury_severity_bleeding_sensation", "entrapment_mechanism", "exact_location"],
            "clarifying_questions": [
                "Can you tell me if your leg is bleeding, swollen, or losing sensation?",
                "What is pinning or trapping your leg (e.g., concrete slab, vehicle, furniture)?",
                "What is your exact location or nearby landmark so emergency responders can locate you?"
            ],
            "action": "ask_clarifying_questions",
            "can_proceed_to_rag": False,
            "escalated": False,
            "support_tier": "clarification_intake"
        }

    if has_critical and len(text_lower.split()) >= 6:
        return {
            "severity": "Critical",
            "reason": "Request describes an urgent, life-threatening emergency with active physical peril.",
            "is_complete": len(missing_info) == 0,
            "missing_info": missing_info,
            "clarifying_questions": [],
            "action": "allocate_resources",
            "can_proceed_to_rag": True,
            "escalated": False,
            "support_tier": "critical_emergency_dispatch"
        }
    elif has_non_critical:
        return {
            "severity": "Non-Critical",
            "reason": "Request describes an inconvenience, financial query, or minor non-life-threatening issue.",
            "is_complete": True,
            "missing_info": [],
            "clarifying_questions": [
                "Could you provide more context or account reference for your request?"
            ],
            "action": "route_to_low_tier_support",
            "can_proceed_to_rag": False,
            "escalated": False,
            "support_tier": "low_tier_support"
        }
    else:
        # Uncertain / incomplete
        return {
            "severity": "Uncertain",
            "reason": "Request is unclear, terse, or missing critical situational context to assess severity.",
            "is_complete": False,
            "missing_info": missing_info or ["situation_details", "exact_location"],
            "clarifying_questions": [
                "Can you tell us more about what happened and if anyone is injured or in immediate danger?",
                "What is your current location?"
            ],
            "action": "ask_clarifying_questions",
            "can_proceed_to_rag": False,
            "escalated": False,
            "support_tier": "clarification_intake"
        }


def classify_pre_rag(
    query: str,
    history: Optional[List[Dict[str, str]]] = None,
    follow_up_answer: Optional[str] = None
) -> Dict[str, Any]:
    """
    Main Pre-RAG classification & intake evaluation.
    Evaluates whether the query is complete, missing info, and classifies severity.
    """
    clean_query = (query or "").strip()
    clean_answer = (follow_up_answer or "").strip()

    if not clean_query and not clean_answer:
        return {
            "severity": "Uncertain",
            "reason": "Empty query received.",
            "is_complete": False,
            "missing_info": ["all_details"],
            "clarifying_questions": ["Please describe your emergency or inquiry."],
            "action": "ask_clarifying_questions",
            "can_proceed_to_rag": False,
            "escalated": False,
            "support_tier": "clarification_intake"
        }

    # Format user prompt for LLM
    prompt_parts = [f"Initial User Query: \"{clean_query}\""]
    if history:
        history_str = "\n".join([f"{h.get('role', 'caller')}: {h.get('content', '')}" for h in history])
        prompt_parts.append(f"Conversation History:\n{history_str}")
    if clean_answer:
        prompt_parts.append(f"Caller Follow-Up Answer: \"{clean_answer}\"")
        prompt_parts.append(
            "Instruction: Re-evaluate severity with this follow-up answer. "
            "If severity escalates to life-threatening emergency, set severity='Critical', action='allocate_resources', can_proceed_to_rag=true, escalated=true. "
            "If not life-threatening, set severity='Non-Critical', action='route_to_low_tier_support', can_proceed_to_rag=false."
        )
    else:
        prompt_parts.append(
            "Instruction: Classify as Critical, Non-Critical, or Uncertain. "
            "If Non-Critical or Uncertain, generate 1 to 3 clarifying questions. "
            "If Critical, set can_proceed_to_rag=true and action='allocate_resources'."
        )

    llm_prompt = "\n\n".join(prompt_parts)

    llm_result = _call_llm(llm_prompt)

    if llm_result and isinstance(llm_result, dict) and "severity" in llm_result:
        severity = str(llm_result.get("severity", "Uncertain")).capitalize()
        if severity not in ["Critical", "Non-critical", "Uncertain"]:
            if "crit" in severity.lower():
                severity = "Critical"
            elif "non" in severity.lower():
                severity = "Non-Critical"
            else:
                severity = "Uncertain"
        else:
            if severity == "Non-critical":
                severity = "Non-Critical"

        can_proceed = (severity == "Critical")
        action = llm_result.get("action")
        if not action:
            if severity == "Critical":
                action = "allocate_resources"
            elif severity == "Non-Critical":
                action = "route_to_low_tier_support"
            else:
                action = "ask_clarifying_questions"

        is_complete = bool(llm_result.get("is_complete", severity == "Critical"))
        clarifying_qs = llm_result.get("clarifying_questions", [])
        if not isinstance(clarifying_qs, list):
            clarifying_qs = [str(clarifying_qs)]

        # Specific user requirement:
        # User: "My leg is stuck." -> LLM: "Can you tell me if your leg is bleeding, swollen, or losing sensation?"
        if "leg is stuck" in clean_query.lower() and not clean_answer:
            has_sensation_q = any("bleeding" in q.lower() or "swollen" in q.lower() or "sensation" in q.lower() for q in clarifying_qs)
            if not has_sensation_q:
                clarifying_qs.insert(0, "Can you tell me if your leg is bleeding, swollen, or losing sensation?")

        missing_info = llm_result.get("missing_info", [])
        if not isinstance(missing_info, list):
            missing_info = [str(missing_info)]

        escalated = bool(llm_result.get("escalated", False))
        if clean_answer and severity == "Critical":
            escalated = True

        support_tier = "critical_emergency_dispatch" if can_proceed else ("low_tier_support" if severity == "Non-Critical" else "clarification_intake")

        return {
            "severity": severity,
            "reason": llm_result.get("reason", "Evaluated via Pre-RAG classification model."),
            "is_complete": is_complete,
            "missing_info": missing_info,
            "clarifying_questions": clarifying_qs,
            "action": action,
            "can_proceed_to_rag": can_proceed,
            "escalated": escalated,
            "support_tier": support_tier
        }

    # Fallback to deterministic rules
    return _deterministic_pre_rag_fallback(clean_query, clean_answer, history)


def re_evaluate_pre_rag(
    initial_query: str,
    follow_up_answer: str,
    history: Optional[List[Dict[str, str]]] = None
) -> Dict[str, Any]:
    """
    Re-evaluate user request after user has provided follow-up clarification.
    If severity escalates -> allocate resources (can_proceed_to_rag: True).
    If not -> route to low-tier support (can_proceed_to_rag: False).
    """
    return classify_pre_rag(
        query=initial_query,
        history=history,
        follow_up_answer=follow_up_answer
    )
