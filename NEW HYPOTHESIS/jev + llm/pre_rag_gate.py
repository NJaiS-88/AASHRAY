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


def extract_intake_record(
    query: str,
    coordinates: Optional[Dict[str, Any]] = None,
    follow_up_answer: Optional[str] = None,
    follow_up_data: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Context-aware emergency intake extractor.
    Extracts structured intake fields and determines missing requirements:
    - incident_type: known hazard or other_or_unknown
    - incident_location / coordinates: checks if GPS or text location is provided
    - affected_population: exact or estimated count of affected persons
    - missing_required_fields: only genuinely missing fields required for operational step
    - clarifying_questions: targeted questions strictly for missing required fields
    """
    full_text = (query or "").strip()
    if follow_up_answer and follow_up_answer.strip():
        full_text = f"{full_text}\n{follow_up_answer.strip()}"
    text_lower = full_text.lower()

    # 1. Coordinate verification
    lat = None
    lng = None
    has_valid_coords = False
    if coordinates and isinstance(coordinates, dict):
        raw_lat = coordinates.get("lat") or coordinates.get("latitude")
        raw_lng = coordinates.get("lng") or coordinates.get("longitude")
        try:
            if raw_lat is not None and raw_lng is not None:
                lat = float(raw_lat)
                lng = float(raw_lng)
                if -90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0 and not (lat == 0.0 and lng == 0.0):
                    has_valid_coords = True
        except (ValueError, TypeError):
            pass

    # 2. Text-based location detection
    named_locations = [
        "powai", "andheri", "ghatkopar", "bandra", "dadar", "kurla", "thane", "bhandup",
        "malad", "borivali", "colaba", "worli", "chembur", "juhu", "vikhroli", "mulund",
        "kalyan", "navi mumbai", "bengaluru", "delhi", "chennai", "kolkata", "hyderabad",
        "mg road", "metro pillar", "sector", "colony", "nagar", "block", "street", "road"
    ]
    has_named_location = any(re.search(rf"\b{re.escape(loc)}\b", text_lower) for loc in named_locations)
    location_known = has_valid_coords or has_named_location or bool(re.search(r"\b(?:in|at|near|beside)\s+(?:my\s+|our\s+|the\s+)?(?:locality|area|neighborhood|building|street|colony|block|society)\b", text_lower))

    # 3. Incident hazard detection
    incident_type = "other_or_unknown"
    if follow_up_data and follow_up_data.get("incident_type"):
        cand = str(follow_up_data.get("incident_type")).strip().lower()
        if cand in [
            "flooding_waterlogging", "building_collapse", "landslide",
            "fire", "cyclone_storm", "earthquake", "road_accident", "medical_emergency"
        ]:
            incident_type = cand

    if incident_type == "other_or_unknown":
        if re.search(r"\b(?:waterlogg?ing|water\s*log(?:ged)?|flood(?:ing|s)?|water\s*rising|submerged|inundat(?:ed|ion)?|deluge)\b", text_lower):
            incident_type = "flooding_waterlogging"
        elif re.search(r"\b(?:slab\s+fell|slab\s+fall|collapse[ds]?|rubble|building\s+fell|wall\s+collapse|structure\s+collapse|trapped\s+under\s+rubble|debris\s+fell|crushed\s+under)\b", text_lower):
            incident_type = "building_collapse"
        elif re.search(r"\b(?:landslide[s]?|mudslide[s]?|rockfall[s]?|slope\s+failure)\b", text_lower):
            incident_type = "landslide"
        elif re.search(r"\b(?:fire|blaze|burning|flames|smoke\s+filling|explosion)\b", text_lower):
            incident_type = "fire"
        elif re.search(r"\b(?:cyclone|hurricane|typhoon|severe\s+storm|gale)\b", text_lower):
            incident_type = "cyclone_storm"
        elif re.search(r"\b(?:earthquake|tremor[s]?|quake|aftershock)\b", text_lower):
            incident_type = "earthquake"
        elif re.search(r"\b(?:car\s+crash|bus\s+crash|road\s+accident|collision|overturned\s+vehicle)\b", text_lower):
            incident_type = "road_accident"
        elif re.search(r"\b(?:heart\s+attack|cardiac|stroke|unconscious|cpr|severe\s+bleed(?:ing)?|profuse\s+bleed(?:ing)?)\b", text_lower):
            incident_type = "medical_emergency"

    # 4. Population extraction
    affected_population = None
    affected_population_is_estimate = False

    if follow_up_data and follow_up_data.get("affected_population") is not None:
        try:
            val = int(follow_up_data.get("affected_population"))
            if val > 0:
                affected_population = val
        except (ValueError, TypeError):
            pass

    if affected_population is None:
        try:
            from jev_v3_triage import extract_structured_facts
            facts = extract_structured_facts(full_text)
            affected_population = facts.get("people_affected")
            if affected_population is None:
                affected_population = facts.get("people_trapped") or facts.get("people_injured_reported")
        except Exception:
            pass

    if affected_population is not None:
        if re.search(r"\b(?:around|approx(?:imately)?|about|estimated?|nearly)\b", text_lower):
            affected_population_is_estimate = True

    # 5. Determine missing operational fields
    missing_required_fields = []
    if incident_type == "other_or_unknown":
        missing_required_fields.append("hazard_type")
    # Location is satisfied if GPS coordinates are valid OR named location exists
    if not (has_valid_coords or has_named_location):
        missing_required_fields.append("location")
    # Affected population must be known (> 0)
    if affected_population is None or affected_population <= 0:
        missing_required_fields.append("affected_population")

    # 6. Generate precise clarifying questions
    clarifying_questions = []
    if "hazard_type" in missing_required_fields:
        clarifying_questions.append("What type of emergency or hazard is occurring (e.g. flooding, building collapse, fire, landslide)?")
    if "location" in missing_required_fields:
        clarifying_questions.append("What is your exact location or nearby landmark so emergency responders can locate you?")
    if "affected_population" in missing_required_fields:
        if incident_type == "building_collapse":
            clarifying_questions.append("Approximately how many people are affected or trapped under rubble?")
        elif incident_type == "flooding_waterlogging":
            clarifying_questions.append("Approximately how many people are affected or need evacuation assistance?")
        elif incident_type == "fire":
            clarifying_questions.append("Approximately how many people are affected or trapped inside?")
        else:
            clarifying_questions.append("Approximately how many people are affected or in immediate danger?")

    is_ready_for_orchestration = (len(missing_required_fields) == 0)
    clarification_status = "complete" if is_ready_for_orchestration else "needs_clarification"

    return {
        "incident_type": incident_type,
        "incident_location": "GPS Coordinates" if has_valid_coords else (full_text if has_named_location else None),
        "latitude": lat,
        "longitude": lng,
        "has_valid_coordinates": has_valid_coords,
        "has_named_location": has_named_location,
        "location_known": location_known,
        "affected_population": affected_population,
        "affected_population_is_estimate": affected_population_is_estimate,
        "missing_required_fields": missing_required_fields,
        "clarifying_questions": clarifying_questions,
        "clarification_status": clarification_status,
        "is_ready_for_orchestration": is_ready_for_orchestration
    }


def _deterministic_pre_rag_fallback(
    query: str,
    follow_up_answer: Optional[str] = None,
    history: Optional[List[Dict[str, str]]] = None,
    coordinates: Optional[Dict[str, Any]] = None,
    follow_up_data: Optional[Dict[str, Any]] = None
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
    has_non_critical = has_explicit_non_critical

    # Detect leg is stuck specific case
    is_leg_stuck = bool(re.search(r"\b(?:leg|foot|arm|hand)\s+is\s+stuck\b", query.lower()))

    # If re-evaluating:
    if is_re_evaluation:
        has_active_trauma = any(re.search(p, answer_lower) for p in [r"\b(?:active|heavy|severe|profuse)\s+bleed", r"\bcrush", r"\btrapped under", r"\bwater rising", r"\bunconscious", r"\bfracture"])
        if has_explicit_non_critical and not has_active_trauma:
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
            intake_rec = extract_intake_record(query, coordinates, follow_up_answer, follow_up_data)
            return {
                "severity": "Critical",
                "reason": f"Caller provided clarification confirming physical distress and operational details: '{follow_up_answer}'.",
                "is_complete": True,
                "missing_info": [],
                "clarifying_questions": [],
                "action": "allocate_resources",
                "can_proceed_to_rag": True,
                "escalated": True,
                "support_tier": "critical_emergency_dispatch",
                "intake_record": intake_rec
            }

    # Initial classification
    if is_leg_stuck and not has_critical:
        intake_rec = extract_intake_record(query, coordinates, follow_up_answer, follow_up_data)
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
            "support_tier": "clarification_intake",
            "intake_record": intake_rec
        }

    if has_non_critical and not has_critical:
        intake_rec = extract_intake_record(query, coordinates, follow_up_answer, follow_up_data)
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
            "support_tier": "low_tier_support",
            "intake_record": intake_rec
        }

    # Context-aware intake extraction
    intake_record = extract_intake_record(query, coordinates, follow_up_answer, follow_up_data)

    if intake_record["is_ready_for_orchestration"]:
        return {
            "severity": "Critical",
            "reason": f"Complete incident intake: {intake_record['incident_type']} affecting {intake_record['affected_population']} persons at confirmed location.",
            "is_complete": True,
            "missing_info": [],
            "clarifying_questions": [],
            "action": "allocate_resources",
            "can_proceed_to_rag": True,
            "escalated": False,
            "support_tier": "critical_emergency_dispatch",
            "intake_record": intake_record
        }

    return {
        "severity": "Uncertain",
        "reason": f"Emergency report received. Awaiting essential missing details: {', '.join(intake_record['missing_required_fields'])}.",
        "is_complete": False,
        "missing_info": intake_record["missing_required_fields"],
        "clarifying_questions": intake_record["clarifying_questions"],
        "action": "ask_clarifying_questions",
        "can_proceed_to_rag": False,
        "escalated": False,
        "support_tier": "clarification_intake",
        "intake_record": intake_record
    }


def classify_pre_rag(
    query: str,
    history: Optional[List[Dict[str, str]]] = None,
    follow_up_answer: Optional[str] = None,
    coordinates: Optional[Dict[str, Any]] = None,
    follow_up_data: Optional[Dict[str, Any]] = None
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

    # Deterministic fallback check first for context-aware intake readiness
    fallback_res = _deterministic_pre_rag_fallback(
        clean_query,
        clean_answer,
        history,
        coordinates=coordinates,
        follow_up_data=follow_up_data
    )
    # If the intake is already complete and ready for orchestration, return immediately
    if fallback_res.get("can_proceed_to_rag") and fallback_res.get("severity") == "Critical":
        return fallback_res

    # Also for leg stuck or explicit non-critical, deterministic rules are canonical
    if "leg is stuck" in clean_query.lower() or fallback_res.get("severity") == "Non-Critical":
        return fallback_res

    # Format user prompt for LLM
    prompt_parts = [f"Initial User Query: \"{clean_query}\""]
    if coordinates:
        prompt_parts.append(f"Confirmed GPS Coordinates: {coordinates}")
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
            "If Non-Critical or Uncertain, generate 1 to 3 clarifying questions strictly for missing information. "
            "Never ask for location if GPS coordinates or location is already provided. "
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

        # If coordinates or location is known, do not ask for location
        intake_rec = fallback_res.get("intake_record") or extract_intake_record(clean_query, coordinates, clean_answer, follow_up_data)
        if intake_rec.get("has_valid_coordinates") or intake_rec.get("has_named_location"):
            clarifying_qs = [q for q in clarifying_qs if not re.search(r"\b(?:where|location|address|landmark|coordinates)\b", q.lower())]

        missing_info = llm_result.get("missing_info", [])
        if not isinstance(missing_info, list):
            missing_info = [str(missing_info)]
        if intake_rec.get("has_valid_coordinates") or intake_rec.get("has_named_location"):
            missing_info = [m for m in missing_info if "location" not in m.lower()]

        escalated = bool(llm_result.get("escalated", False))
        if clean_answer and severity == "Critical":
            escalated = True

        support_tier = "critical_emergency_dispatch" if can_proceed else ("low_tier_support" if severity == "Non-Critical" else "clarification_intake")

        return {
            "severity": severity,
            "reason": llm_result.get("reason", "Evaluated via Pre-RAG classification model."),
            "is_complete": is_complete,
            "missing_info": missing_info,
            "clarifying_questions": clarifying_qs if clarifying_qs else fallback_res.get("clarifying_questions", []),
            "action": action,
            "can_proceed_to_rag": can_proceed,
            "escalated": escalated,
            "support_tier": support_tier,
            "intake_record": intake_rec
        }

    # Fallback to deterministic rules
    return fallback_res


def re_evaluate_pre_rag(
    initial_query: str,
    follow_up_answer: str,
    history: Optional[List[Dict[str, str]]] = None,
    coordinates: Optional[Dict[str, Any]] = None,
    follow_up_data: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Re-evaluate user request after user has provided follow-up clarification.
    If severity escalates -> allocate resources (can_proceed_to_rag: True).
    If not -> route to low-tier support (can_proceed_to_rag: False).
    """
    return classify_pre_rag(
        query=initial_query,
        history=history,
        follow_up_answer=follow_up_answer,
        coordinates=coordinates,
        follow_up_data=follow_up_data
    )
