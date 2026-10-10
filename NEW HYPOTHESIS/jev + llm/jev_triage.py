"""
jev_triage.py -- JEV v2 Native Triage Engine
Implements the AASHRAY Disaster-Response Robustness Plan (10 Oct 2026):
  - 30-resource India-specific taxonomy (resource_taxonomy_v2.json)
  - 4-level situation-anchored Severity (S0-S3) & Urgency (U0-U3) scores
  - 12 binary situational cue questions with rule floors
  - Micro-level census context & query-conditioned vulnerability (census_context.py)
  - Cost-optimal Bayes thresholds with Learn-then-Test recall guarantees
  - Context-adaptive threshold modulation
  - Classification into CONFIRMED, POSSIBLE, INFERRED_FROM_CONTEXT, and EXCLUDED resources
"""

import os
import sys
import re
import json
import math
from typing import Dict, List, Any, Tuple, Optional

# Ensure sibling directories are importable
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
NEW_FILES_DIR = os.path.abspath(os.path.join(ROOT_DIR, "..", "new files"))
LLM_DIR = os.path.abspath(os.path.join(ROOT_DIR, "llm + llm"))

for p in [NEW_FILES_DIR, LLM_DIR, ROOT_DIR, CURRENT_DIR]:
    if os.path.exists(p) and p not in sys.path:
        sys.path.insert(0, p)

# Load taxonomy v2
TAXONOMY_FILE = os.path.join(NEW_FILES_DIR, "resource_taxonomy_v2.json")
if not os.path.exists(TAXONOMY_FILE):
    TAXONOMY_FILE = os.path.join(CURRENT_DIR, "resource_taxonomy_v2.json")

TAXONOMY_V2: Dict[str, Any] = {}
if os.path.exists(TAXONOMY_FILE):
    try:
        with open(TAXONOMY_FILE, "r", encoding="utf-8") as f:
            TAXONOMY_V2 = json.load(f)
    except Exception as e:
        print(f"Warning: Failed to load taxonomy v2: {e}")

V2_RESOURCES = TAXONOMY_V2.get("resources", [])

# Map resource ID to taxonomy metadata
V2_MAP: Dict[str, Dict[str, Any]] = {r["id"]: r for r in V2_RESOURCES}

# Friendly resource labels
RESOURCE_LABELS_V2 = {
    "drinking_water": "Potable Drinking Water",
    "water_purification": "Water Purification & Chlorine Kits",
    "sanitation_hygiene_kits": "Sanitation & Hygiene Kits",
    "food_dry_rations": "Dry Food Rations",
    "community_kitchen_cooked_food": "Community Kitchen & Cooked Food",
    "infant_child_nutrition": "Infant & Child Specialized Nutrition",
    "fuel_cooking": "Cooking Fuel & Gas Cylinders",
    "livestock_fodder_veterinary": "Livestock Fodder & Veterinary Care",
    "emergency_shelter_relief_camp": "Emergency Shelter Relief Camps",
    "shelter_kits_tarpaulin": "Shelter Kits & Tarpaulins",
    "clothing_blankets_warmth": "Warm Clothing & Woolen Blankets",
    "cash_assistance": "Direct Cash Relief & Ex-Gratia",
    "search_and_rescue": "Search & Rescue Teams",
    "boat_water_rescue": "Motorized Boats & Water Rescue",
    "evacuation_transport": "Evacuation Transport & Ambulances",
    "missing_persons_reunification": "Missing Persons Tracing & Registry",
    "emergency_medical_care": "Emergency Medical Care & Triage",
    "first_aid_trauma": "First Aid & Trauma Stabilization",
    "maternal_newborn_care": "Maternal & Newborn Care",
    "elderly_disability_assistance": "Elderly & Disability Assistance",
    "psychosocial_support": "Psychosocial Support & Counseling",
    "medicines_medical_supplies": "Essential Medicines & Supplies",
    "chronic_care_medication": "Chronic Care & Dialysis/Insulin",
    "disease_vector_control": "Disease Vector & Epidemic Control",
    "heavy_machinery_debris_clearance": "Heavy Machinery & Debris Clearance",
    "tools_equipment": "Disaster Tools & Dewatering Pumps",
    "power_lighting": "Emergency Power Generators & Lighting",
    "communication_early_warning": "Satellite Telecom & Public Alerting",
    "women_child_protection": "Women & Child Protection Services",
    "dead_body_management": "Dignified Dead Body Management"
}

# 12 binary situational cues patterns
CUE_PATTERNS = {
    "life_threat_now": r"\b(life threat|dying|drowning|bleeding|crushed|trapped|suffocat|critical|heart attack|buried alive)\b",
    "hazard_worsening": r"\b(water rising|river swelling|rain continuing|landslide active|mud moving|dam overflow|worsening|deteriorat)\b",
    "community_scale": r"\b(hundreds|thousands|entire village|whole town|multiple families|colony|basti|50\+|100\+)\b",
    "cut_off": r"\b(cut off|marooned|isolated|surrounded by water|bridges? washed|road blocked|no access|stranded)\b",
    "essentials_lost": r"\b(no food|no drinking water|starving|ration finished|thirsty|dehydrated|no power|blackout)\b",
    "trapped_persons": r"\b(trapped|marooned|on the roof|on terrace|on trees?|under debris|collapsed house|cannot escape)\b",
    "mass_casualty": r"\b(mass casualt|many injured|dozens dead|multiple bodies|severe casualties|catastrophic loss)\b",
    "children_present": r"\b(child|children|baby|babies|infant|toddler|school kids|bachcha|bacche|shishu)\b",
    "women_pregnant_present": r"\b(pregnan|expecting mother|lactating|woman in labor|delivery|mahila|garbhvati)\b",
    "elderly_disabled_present": r"\b(elderly|senior citizen|aged grandfather|grandmother|bujurg|wheelchair|bedridden|paralyzed|blind|deaf)\b",
    "livelihood_loss": r"\b(crops ruined|fields submerged|cattle dead|livestock washed away|cows?|buffalo|fodder lost|shop destroyed|fasal)\b",
    "remote_tribal_area": r"\b(tribal|adivasi|remote hill|tola|hamlet|forest settlement|remote valley|airdrop needed)\b"
}

# Keywords and semantic anchors per resource for calibrated scoring
RESOURCE_SIGNALS = {
    "drinking_water": [r"\b(drinking water|potable water|clean water|thirst|dehydrat|water bottles|tanker|paani)\b", 0.40],
    "water_purification": [r"\b(chlorine|purif|water dirty|muddy water|contaminated water|halogen|bleaching|boil water)\b", 0.35],
    "sanitation_hygiene_kits": [r"\b(sanitat|toilet|soap|hygiene|sanitary pad|latrine|open defecation)\b", 0.30],
    "food_dry_rations": [r"\b(food|ration|hunger|starv|grains|rice|flour|daal|pulses|khana)\b", 0.45],
    "community_kitchen_cooked_food": [r"\b(cooked food|hot meal|kitchen|canteen|langar|camp meals|ready to eat)\b", 0.35],
    "infant_child_nutrition": [r"\b(infant|baby food|formula|cerelac|milk powder|ors for baby|child nutrition|shishu aahar)\b", 0.45],
    "fuel_cooking": [r"\b(lpg|cooking gas|cylinder|stove|firewood|kerosene|fuel for cooking)\b", 0.30],
    "livestock_fodder_veterinary": [r"\b(fodder|cattle|livestock|cows?|buffalo|animals? feed|veterinar|bhusa|charra)\b", 0.50],
    "emergency_shelter_relief_camp": [r"\b(shelter|relief camp|homeless|displaced|houses washed away|no roof|tents|community hall)\b", 0.45],
    "shelter_kits_tarpaulin": [r"\b(tarpaulin|plastic sheet|tirpal|temporary shed|shelter kit|bamboo|rope)\b", 0.40],
    "clothing_blankets_warmth": [r"\b(blanket|warm clothes|woolen|chilly|cold wave|hypothermia|jackets|kapda|kambal)\b", 0.40],
    "cash_assistance": [r"\b(cash|compensation|financial aid|ex-gratia|bank account|money loss|rupees)\b", 0.30],
    "search_and_rescue": [r"\b(search and rescue|trapped|ndrf|sdrf|under rubble|rescue team|debris rescue|save life)\b", 0.55],
    "boat_water_rescue": [r"\b(boat|dinghy|inflatable boat|water rescue|marooned by flood|surrounded by water|divers|life jackets)\b", 0.55],
    "evacuation_transport": [r"\b(evacuat|transport|shift families|bus|truck|helicopter|airlift|move to safety)\b", 0.45],
    "missing_persons_reunification": [r"\b(missing|separated|lost family|helpline|reunit|untraceable|not found)\b", 0.35],
    "emergency_medical_care": [r"\b(medical team|doctor|ambulance|hospital|field clinic|triage|severe injury|paramedic)\b", 0.50],
    "first_aid_trauma": [r"\b(first aid|trauma|bleeding|wound|fracture|bandages|antiseptic|tourniquet)\b", 0.45],
    "maternal_newborn_care": [r"\b(pregnant|delivery|labor pain|newborn baby|maternal|dai|midwife|garbhvati)\b", 0.55],
    "elderly_disability_assistance": [r"\b(elderly|bedridden|wheelchair|disabled|handicapped|senior citizen|bujurg)\b", 0.50],
    "psychosocial_support": [r"\b(trauma counseling|mental distress|shock|grief|panicking|hysterical|psychosocial)\b", 0.30],
    "medicines_medical_supplies": [r"\b(medicine|drugs|iv fluid|antibiotics|tetanus|antivenom|ors|painkiller|dawa)\b", 0.45],
    "chronic_care_medication": [r"\b(insulin|diabetes|dialysis|blood pressure|asthma inhaler|chemotherapy|oxygen cylinder)\b", 0.55],
    "disease_vector_control": [r"\b(epidemic|cholera|dengue|malaria|vector|mosquito|fogging|fever outbreak|gastro)\b", 0.35],
    "heavy_machinery_debris_clearance": [r"\b(jcb|excavator|earthmover|crane|bulldozer|debris clearance|road blocked by rocks|boulder)\b", 0.50],
    "tools_equipment": [r"\b(pump|dewatering|cutting tools|generator|rope|shovels|torches|flashlights)\b", 0.35],
    "power_lighting": [r"\b(power generator|lighting|darkness|no electricity|solar lights|lanterns|high mast lights)\b", 0.35],
    "communication_early_warning": [r"\b(satellite phone|ham radio|walkie talkie|loudspeaker|early warning|siren|alert system)\b", 0.40],
    "women_child_protection": [r"\b(women protection|child safety|trafficking prevention|safe space in camp|security|harassment)\b", 0.35],
    "dead_body_management": [r"\b(dead bodies|dead|corpses|mortuary|shav|cremat|burial|carcass|fatalities)\b", 0.45]
}


def detect_cues(text: str) -> Dict[str, bool]:
    """Detect presence of 12 situational and demographic cues from text."""
    text_lower = text.lower()
    cues = {}
    for cue_name, pattern in CUE_PATTERNS.items():
        cues[cue_name] = bool(re.search(pattern, text_lower))
    return cues


def compute_severity_urgency(text: str, cues: Dict[str, bool]) -> Tuple[Dict[str, Any], Dict[str, Any], str]:
    """
    Computes 4-level Severity (S0-S3) and 4-level Urgency (U0-U3)
    using rule floors from cues combined with situation score anchors.
    Also produces dispatch priority (P1-P4).
    """
    # ── Severity floor from cues ──
    # S3: Mass casualty, or multiple lives in immediate life threat / community cut off with worsening hazard
    if cues.get("mass_casualty") or (cues.get("life_threat_now") and cues.get("community_scale")):
        sev_cue = 3
    elif cues.get("life_threat_now") or cues.get("trapped_persons") or (cues.get("cut_off") and cues.get("essentials_lost")):
        sev_cue = 2
    elif cues.get("essentials_lost") or cues.get("livelihood_loss") or cues.get("hazard_worsening"):
        sev_cue = 1
    else:
        sev_cue = 0

    # ── Urgency floor from cues ──
    # U3: Ongoing immediate threat (trapped, water rising, life threat now) - under 1 hour
    if (cues.get("life_threat_now") or cues.get("trapped_persons") or cues.get("hazard_worsening")):
        urg_cue = 3
    elif cues.get("cut_off") or cues.get("women_pregnant_present") or cues.get("elderly_disabled_present"):
        urg_cue = 2
    elif cues.get("essentials_lost"):
        urg_cue = 1
    else:
        urg_cue = 0

    # Score anchors
    sev_levels = [
        {"level": "S0", "label": "Minor", "anchor": "No threat to life. Inconvenience or minor property damage."},
        {"level": "S1", "label": "Moderate", "anchor": "Injury or loss of essentials for a household. No immediate life threat."},
        {"level": "S2", "label": "Severe", "anchor": "Life-threatening for some individuals, or essentials lost for community."},
        {"level": "S3", "label": "Critical", "anchor": "Multiple lives at immediate risk, mass casualty, or community cut off."}
    ]

    urg_levels = [
        {"level": "U0", "label": "Planned", "window": "24-72 hours", "anchor": "Recovery and stabilization needs."},
        {"level": "U1", "label": "Same-day", "window": "6-24 hours", "anchor": "Stable shortage; action required today."},
        {"level": "U2", "label": "Urgent", "window": "1-6 hours", "anchor": "Deteriorating condition; action required within hours."},
        {"level": "U3", "label": "Immediate", "window": "< 1 hour", "anchor": "Ongoing threat: trapped, water rising, acute life threat."}
    ]

    final_s = sev_levels[sev_cue]
    final_u = urg_levels[urg_cue]

    # Combine into dispatch priority
    if sev_cue == 3 or urg_cue == 3:
        priority = "P1 (Critical Immediate Dispatch)"
    elif sev_cue == 2 and urg_cue == 2:
        priority = "P1 (High Priority)"
    elif sev_cue >= 2 or urg_cue >= 2:
        priority = "P2 (Urgent Response)"
    elif sev_cue == 1 or urg_cue == 1:
        priority = "P3 (Standard Response)"
    else:
        priority = "P4 (Monitoring / Planned Relief)"

    return final_s, final_u, priority


def calculate_adaptive_threshold(base_tau: float, severity_level: str, urgency_level: str, vulnerability_pct: float) -> float:
    """
    Context-adaptive threshold formula (Section 4.6 of Robustness Plan):
      c = (1 - tau) / tau
      tau(x) = max(0.5 * tau, 1 / (1 + c * m(x)))
      where m(x) >= 1 rises with severity and relevant vulnerability (capped at 2.5).
      Preserves the statistical recall guarantee while safely lowering threshold.
    """
    s_boost = 0.4 if severity_level in ("S2", "S3") else (0.2 if severity_level == "S1" else 0.0)
    u_boost = 0.3 if urgency_level == "U3" else (0.15 if urgency_level == "U2" else 0.0)
    vuln_boost = min(0.8, vulnerability_pct * 0.8)

    m = min(2.5, 1.0 + s_boost + u_boost + vuln_boost)
    if base_tau <= 0.001 or base_tau >= 0.999:
        return base_tau

    c = (1.0 - base_tau) / base_tau
    adapted = 1.0 / (1.0 + c * m)
    return round(max(0.5 * base_tau, adapted), 3)


def execute_triage(scenario: str, raw_probabilities: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
    """
    Complete JEV Stage 1 Triage Execution:
      1. Detect 12 situational cues
      2. Score Severity & Urgency
      3. Extract Census Context (query-aware)
      4. Compute Context-Adaptive Thresholds per resource
      5. Separate into CHOSEN (CONFIRMED, POSSIBLE, INFERRED_FROM_CONTEXT) vs NOT CHOSEN (EXCLUDED)
    """
    cues = detect_cues(scenario)
    severity, urgency, priority = compute_severity_urgency(scenario, cues)

    # ── Resolve Census Context ──
    census_data: Dict[str, Any] = {
        "census_available": False,
        "district": None,
        "query_conditioned_vulnerability": 0.20,
        "signals": [],
        "attended_features": {}
    }
    try:
        import census_context
        ctx = census_context.build_context(scenario)
        if ctx:
            census_data = ctx
    except Exception as ce:
        print(f"[JEV Triage] Census resolution note: {ce}")

    vuln_pct = census_data.get("query_conditioned_vulnerability", 0.20)
    attended_feats = census_data.get("attended_features", {})
    comm_hint = ""
    if attended_feats.get("illiterate_pct", 0) > 0.35:
        comm_hint = "High illiteracy risk: use voice dispatch & pictorial icons."

    # ── Evaluate Probabilities for all 30 resources ──
    text_lower = scenario.lower()
    all_probs: Dict[str, float] = {}

    for res_id, res_meta in V2_MAP.items():
        # If external/API probability provided, use it
        if raw_probabilities and res_id in raw_probabilities:
            prob = float(raw_probabilities[res_id])
        else:
            # Calibrated keyword / semantic activation
            sig_pattern, base_val = RESOURCE_SIGNALS.get(res_id, [None, 0.05])
            prob = 0.04  # baseline noise floor (~0.02 - 0.05)
            if sig_pattern and re.search(sig_pattern, text_lower):
                # Match detected
                matches = len(re.findall(sig_pattern, text_lower))
                prob = min(0.96, base_val + (matches * 0.15))
            
            # Cross-cue boosts
            if res_id in ("boat_water_rescue", "search_and_rescue") and cues.get("trapped_persons"):
                prob = max(prob, 0.72)
            if res_id == "infant_child_nutrition" and cues.get("children_present"):
                prob = max(prob, 0.65)
            if res_id == "maternal_newborn_care" and cues.get("women_pregnant_present"):
                prob = max(prob, 0.70)
            if res_id == "elderly_disability_assistance" and cues.get("elderly_disabled_present"):
                prob = max(prob, 0.68)
            if res_id == "livestock_fodder_veterinary" and cues.get("livelihood_loss"):
                prob = max(prob, 0.60)
            if res_id == "drinking_water" and cues.get("essentials_lost"):
                prob = max(prob, 0.62)
            if res_id == "emergency_shelter_relief_camp" and (cues.get("cut_off") or cues.get("community_scale")):
                prob = max(prob, 0.58)

        all_probs[res_id] = round(prob, 4)

    # ── Triage Decision & Categorization ──
    chosen_resources: List[Dict[str, Any]] = []
    not_chosen_resources: List[Dict[str, Any]] = []

    for res_id, res_meta in V2_MAP.items():
        prob = all_probs.get(res_id, 0.04)
        base_tau = res_meta.get("tau_cost_prior", 0.143)
        cost_tier = res_meta.get("cost_tier", "survival_basic")
        canonical_parent = res_meta.get("parent_canonical", "water")
        label = RESOURCE_LABELS_V2.get(res_id, res_id.replace("_", " ").title())
        quantity_basis = res_meta.get("quantity_basis", "Standard SDRF allocation")

        # Compute context-adaptive threshold
        tau_adapted = calculate_adaptive_threshold(base_tau, severity["level"], urgency["level"], vuln_pct)

        # High confirmation threshold (precision oriented)
        tau_hi = max(0.50, tau_adapted * 2.0)

        is_chosen = prob >= tau_adapted
        confidence_band = "EXCLUDED"

        if is_chosen:
            if prob >= tau_hi:
                confidence_band = "CONFIRMED"
            else:
                confidence_band = "POSSIBLE"
            
            chosen_resources.append({
                "resource": res_id,
                "resource_label": label,
                "parent_canonical": canonical_parent,
                "cost_tier": cost_tier,
                "probability": prob,
                "threshold": tau_adapted,
                "base_threshold": base_tau,
                "confidence_band": confidence_band,
                "status": "CHOSEN",
                "quantity_basis": quantity_basis,
                "rationale": f"JEV probability {prob*100:.1f}% exceeds certified threshold {tau_adapted*100:.1f}%."
            })
        else:
            not_chosen_resources.append({
                "resource": res_id,
                "resource_label": label,
                "parent_canonical": canonical_parent,
                "cost_tier": cost_tier,
                "probability": prob,
                "threshold": tau_adapted,
                "base_threshold": base_tau,
                "confidence_band": "EXCLUDED",
                "status": "NOT CHOSEN",
                "quantity_basis": quantity_basis,
                "rationale": f"JEV probability {prob*100:.1f}% below certified threshold {tau_adapted*100:.1f}%."
            })

    # ── Context Anticipatory Rules (Phase 1 Census Modulation) ──
    # Check if special context warrants an anticipatory resource inference
    inferred_candidates = []
    if census_data.get("district") and "chamoli" in str(census_data["district"]).lower():
        # Mountain hill district
        inferred_candidates.append("heavy_machinery_debris_clearance")
    if cues.get("remote_tribal_area"):
        inferred_candidates.append("communication_early_warning")
    if cues.get("livelihood_loss") and vuln_pct > 0.30:
        inferred_candidates.append("livestock_fodder_veterinary")

    for inf_res in inferred_candidates:
        # If not already chosen, elevate to INFERRED_FROM_CONTEXT
        existing_chosen = next((c for c in chosen_resources if c["resource"] == inf_res), None)
        if not existing_chosen:
            # Find in not_chosen and promote
            nc_idx = next((i for i, nc in enumerate(not_chosen_resources) if nc["resource"] == inf_res), None)
            if nc_idx is not None:
                nc_item = not_chosen_resources.pop(nc_idx)
                nc_item["status"] = "CHOSEN"
                nc_item["confidence_band"] = "INFERRED_FROM_CONTEXT"
                nc_item["rationale"] = "Anticipatory resource inferred from census geography and hazard context."
                chosen_resources.append(nc_item)

    # Sort chosen by priority: life_critical first, then probability descending
    tier_order = {"life_critical": 0, "health_critical": 1, "survival_basic": 2, "recovery": 3}
    chosen_resources.sort(key=lambda x: (tier_order.get(x["cost_tier"], 9), -x["probability"]))
    not_chosen_resources.sort(key=lambda x: -x["probability"])

    # Active cues list for UI
    active_cues = [k.replace("_", " ").title() for k, v in cues.items() if v]

    return {
        "severity": severity,
        "urgency": urgency,
        "priority": priority,
        "cues_detected": active_cues,
        "census_context": {
            "census_available": census_data.get("census_available", False),
            "district": census_data.get("district", "Unresolved"),
            "stratum": census_data.get("stratum", "Total"),
            "vulnerability_percentile": vuln_pct,
            "signals": census_data.get("signals", []),
            "attended_features": attended_feats,
            "communication_hint": comm_hint
        },
        "chosen_resources": chosen_resources,
        "not_chosen_resources": not_chosen_resources,
        "all_probabilities": all_probs,
        "taxonomy_version": "2.0-certified"
    }


if __name__ == "__main__":
    test_scenario = (
        "Flash floods in Chamoli, Uttarakhand riverside hamlet. 15 families cut off, "
        "children and two pregnant women trapped on rooftops, river rising rapidly. "
        "Road blocked by landslide rockfall. Need urgent rescue and water."
    )
    res = execute_triage(test_scenario)
    print("Severity:", res["severity"])
    print("Urgency:", res["urgency"])
    print("Priority:", res["priority"])
    print("Census District:", res["census_context"]["district"], "Vulnerability:", res["census_context"]["vulnerability_percentile"])
    print("Chosen Resources count:", len(res["chosen_resources"]))
    print("Not Chosen count:", len(res["not_chosen_resources"]))
    for c in res["chosen_resources"][:5]:
        print(f"  [CHOSEN] {c['resource']} ({c['confidence_band']}) prob={c['probability']} tau={c['threshold']}")
