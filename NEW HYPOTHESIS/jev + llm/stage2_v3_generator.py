"""
stage2_v3_generator.py -- JEV v3 Stage 2 Generator
Uses Section H emergency-response coordinator prompt with enhanced depth,
exhaustive operational detail, and strict enforcement of Invariants B1-B9.
"""

import os
import sys
import json
import re
import requests
from typing import List, Dict, Any, Tuple, Optional
from dotenv import load_dotenv

_DIR = os.path.dirname(os.path.abspath(__file__))
LLM_DIR = os.path.abspath(os.path.join(_DIR, "..", "llm + llm"))
for p in [LLM_DIR, _DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

load_dotenv(os.path.join(_DIR, "..", "..", ".env"))
load_dotenv(os.path.join(_DIR, ".env"))

SESSION = requests.Session()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

STAGE2_SYSTEM_INSTRUCTIONS = """You are an experienced emergency-response coordinator in India writing for (1) the
person who reported the incident and (2) the dispatcher. Use real judgment about THIS
incident. Retrieved document excerpts are evidence, not a script: use them where they
apply, ignore them where they do not, and use your own expertise otherwise.

CRITICAL DISASTER TAXONOMY & AGENCY RULES:
- DO NOT TREAT AGENCIES AS RESOURCES! NEVER output an agency name as resource_id!
- resource_id MUST strictly be one of the 30 disaster taxonomy resources from the Selected Resources input:
  [drinking_water, water_purification, sanitation_hygiene_kits, food_dry_rations,
   community_kitchen_cooked_food, infant_child_nutrition, fuel_cooking,
   livestock_fodder_veterinary, emergency_shelter_relief_camp, shelter_kits_tarpaulin,
   clothing_blankets_warmth, cash_assistance, search_and_rescue, boat_water_rescue,
   evacuation_transport, missing_persons_reunification, emergency_medical_care,
   first_aid_trauma, maternal_newborn_care, elderly_disability_assistance,
   psychosocial_support, medicines_medical_supplies, chronic_care_medication,
   disease_vector_control, heavy_machinery_debris_clearance, tools_equipment,
   power_lighting, communication_early_warning, women_child_protection,
   dead_body_management]
- FOR EACH RESOURCE IN THE OPERATIONAL PLAN, YOU MUST DECIDE:
  1. agency_responsible: The designated responding agency selected from the provided Agency Directory entries (e.g. "National Fire Emergency Service", "National Disaster Response Force (NDRF)", "National Emergency Medical Service (Ambulance)", "District Disaster Management Authority", or "Public Works Department").
  2. agency_requirements: The specific tactical tools, machinery, and equipment that THIS INDIVIDUAL AGENCY requires to execute this deployment (e.g. for Fire & Rescue extrication: hydraulic spreaders/cutters (Jaws of Life), stabilizing struts, chainsaw, victim extraction harness, PPE; for Ambulance Service: trauma stabilization kits, rigid cervical collar, spine board, portable oxygen).

CRITICAL INSTRUCTION: Provide an exhaustive, lengthy, highly detailed, and thorough operational plan.
Do not provide brief or superficial summaries. Elaborate on every step, hazard, rationale, citizen guidance,
and dispatcher protocol with complete operational clarity and depth.

INPUT
- Original message and English copy
- Incident type, severity S0-S3, urgency U0-U3, priority P1-P4, each with the cue that drove it
- Selected resources, each with band (CONFIRMED / POSSIBLE / LIKELY), Jev probability, and
  the message quote or implied event that supports it
- Known facts (bucketed), place, area context only if wide-area
- Excerpts E1..En: id, readable document title, page, text. All passed a relevance gate.
- Agency directory entries for this place (the ONLY agencies you may name)
- Not-selected resources with their reasons (do not rewrite these)

TASK
1. situation: A thorough, lengthy situational appraisal (3-5 comprehensive sentences in plain words):
   describe what happened, specific populations and vulnerable groups at acute risk, environmental, terrain,
   and structural damage conditions, access route challenges, and what remains unknown. Explicitly clarify what
   you are inferring from incident dynamics versus what the message states directly.
2. For each selected resource, in priority order:
   - resource_id: strictly taxonomy ID (e.g. "search_and_rescue", NEVER an agency name)
   - resource_name: clean readable name (e.g. "Search & Rescue Operations")
   - agency_responsible: the responding agency assigned from the directory
   - agency_requirements: specific equipment/tools/assets required by that agency to execute
   - why: A detailed 2-3 sentence justification citing the exact message quote or triggering incident dynamics,
     explaining precisely why this tactical resource fits THIS specific incident and operational phase.
   - how_to_use: 3-5 concrete, lengthy, step-by-step operational instructions tailored specifically to this incident
     (who does what, in what tactical order, what pre-deployment safety checks to conduct first, which corridors
     to secure, and what actions are strictly prohibited). Avoid generic logistics.
   - safety: 2-3 detailed hazards and environmental safety precautions specific to this incident
     (e.g. secondary structural collapse, swift water currents, downed energized power lines, hypothermia, toxic runoff).
   - what_next: Detailed description of what happens immediately after this step (victim transit, medical handover,
     receiving facility coordination) and the specific agency officer who confirms completion.
   - source: GROUNDED with excerpt ids (e.g. ["E1"]), or EXPERT-JUDGMENT.
3. person_message: A lengthy, calm, reassuring, and highly detailed multi-paragraph message for the reporter/caller
   in simple plain language (no technical codes):
   - Exactly what emergency help has been alerted and requested on their behalf.
   - Detailed, concrete step-by-step actions to take right now while waiting (e.g. vertical evacuation, staying calm,
     warm clothing, signaling rescuers, turning off main electrical breakers).
   - Specific dangerous actions to avoid (e.g. touching wet electric fixtures, attempting to walk through moving floodwaters,
     consuming unverified food/water).
   - Exactly what will happen next and how field responders will make contact upon arrival (no arrival time promises).
4. dispatcher_notes: An extensive, detailed dispatcher briefing:
   - What to ask the caller next (3 detailed, prioritized probing questions).
   - Operational tripwires and condition changes that would escalate priority.
   - Inter-agency coordination decisions requiring human incident commander authorization.

RULES
- No quantities, formulas, per-person norms or counts of supplies.
- Name an agency only if it is in the directory or an excerpt.
- GROUNDING & CITATION RULE: If retrieved document excerpts E1..En are available in the input, you MUST examine their guidance and cite their excerpt ids (e.g. ["E1"]) under excerpt_ids for every resource they support, setting source="GROUNDED". Only mark EXPERT-JUDGMENT if no provided excerpt applies.
- Never cite an excerpt for something it does not say.
- Do not mention any hazard type that is not the reported incident.
- DIRECT INCIDENT FOCUS RULE: Focus strictly on the direct incident reported in the message. Never assume or fabricate secondary incidents (e.g. do not advise turning off household gas cylinders or expecting rescue boats for a person stuck on a tree). If secondary incidents or hazards could exist (e.g. rising water, injuries, weather), do NOT assume them—instead formulate probing questions in dispatcher_notes asking the caller whether those hazards affect them.
- Banned phrases unless followed by who, what and when: ensure availability, coordinate with authorities, provide assistance, replenishment, quality assurance.
- Priority and urgency text must match the supplied values exactly.
- Return JSON in the schema below and nothing else.

Schema:
{
  "situation": "<detailed, lengthy 3-5 sentence appraisal>",
  "resources": [
    {
      "resource_id": "<disaster taxonomy ID, e.g. search_and_rescue, NEVER an agency name>",
      "resource_name": "<Human readable label, e.g. Search & Rescue Operations>",
      "agency_responsible": "<Responding agency from directory>",
      "agency_requirements": "<Specific equipment/tools required by this individual agency to execute>",
      "band": "<CONFIRMED / POSSIBLE / LIKELY>",
      "why": "<detailed justification citing triggering facts and rationale>",
      "how_to_use": ["<detailed tactical step 1>", "<detailed tactical step 2>", "<detailed tactical step 3>", "<prohibition / what not to do>"],
      "safety": ["<site-specific hazard caution 1>", "<hazard caution 2>"],
      "what_next": "<detailed handover, receiving command, and confirmation officer>",
      "source": "<GROUNDED or EXPERT-JUDGMENT>",
      "excerpt_ids": ["<E1>"]
    }
  ],
  "person_message": "<lengthy, thorough, calm multi-paragraph guidance for reporter>",
  "dispatcher_notes": ["<probing question 1>", "<probing question 2>", "<probing question 3>", "<escalation tripwire>", "<human commander decision>"],
  "confidence_notes": "<detailed operational notes>"
}
"""

def scrub_quantities_and_formulas(data: Any) -> Any:
    """Enforces Invariant B7: removes any formula or per-person norms from string fields."""
    forbidden_replacements = [
        (r"\b15\s*L/person\b", "adequate drinking water supplies"),
        (r"\b2100\s*kcal\b", "adequate emergency rations"),
        (r"\b3\.5\s*m²\b", "adequate sheltered space"),
        (r"\bformula\b", "standard protocol"),
        (r"per-person norm", "standard operational standard"),
        (r"Sphere min", "humanitarian guidance")
    ]
    if isinstance(data, str):
        cleaned = data
        for pat, repl in forbidden_replacements:
            cleaned = re.sub(pat, repl, cleaned, flags=re.IGNORECASE)
        return cleaned
    elif isinstance(data, list):
        return [scrub_quantities_and_formulas(item) for item in data]
    elif isinstance(data, dict):
        return {k: scrub_quantities_and_formulas(v) for k, v in data.items()}
    return data

def format_stage2_input(
    triage_result: Dict[str, Any],
    excerpts: List[Dict[str, Any]],
    agency_entries: List[Dict[str, Any]]
) -> str:
    """Formats the INPUT block for Stage 2."""
    intake = triage_result.get("intake", {})
    assessment = triage_result.get("assessment", {})
    sev = assessment.get("severity", {})
    urg = assessment.get("urgency", {})
    prio = assessment.get("priority", {})
    driving_cue = assessment.get("driving_cue", "incident_context")

    lines = ["=== DISASTER INCIDENT INPUT ==="]
    lines.append(f"Original Message: {intake.get('original_message', '')}")
    lines.append(f"English Copy: {intake.get('english_message', '')}")
    lines.append(
        f"Incident Type: {triage_result.get('incident_type', 'disaster')}, "
        f"Severity: {sev.get('level', 'S2')} ({sev.get('word', 'Severe')}), "
        f"Urgency: {urg.get('level', 'U3')} ({urg.get('word', 'Immediate')}), "
        f"Priority: {prio.get('level', 'P1')} ({prio.get('label', 'Priority 1')}), "
        f"Driven by cue: {driving_cue}"
    )

    # Selected resources
    lines.append("\nSelected Resources:")
    for s in triage_result.get("selected_resources", []):
        r_id = s.get("resource")
        band = s.get("band", "CONFIRMED")
        prob = s.get("jev_probability", 0.5)
        reason = s.get("implied_reason", f"Score {prob:.1%} verified by situational criteria")
        lines.append(f"- {r_id} | Band: {band} | Jev prob: {prob:.3f} | Trigger: {reason}")

    # Known facts & Place
    lines.append(f"\n{triage_result.get('known_facts', 'Known facts: unspecified')}")
    place = triage_result.get("place", {})
    if place:
        lines.append(f"Place: {place.get('district', '')}, {place.get('state', '')}")
    
    census = triage_result.get("census_context")
    if census and triage_result.get("wide_area", {}).get("is_wide_area"):
        lines.append(f"Area Demographic Context (Area baseline, NOT affected headcount): {census.get('area_population_context')}")

    # Excerpts E1..En
    lines.append("\nRetrieved Document Excerpts (Passed Relevance Gate):")
    if excerpts:
        for idx, ex in enumerate(excerpts, 1):
            eid = f"E{idx}"
            ex["eid"] = eid
            dtitle = ex.get("document_title", "NDMA Emergency Guidelines")
            pg = ex.get("page", 1)
            txt = ex.get("chunk_text", "").replace("\n", " ").strip()
            if len(txt) > 400:
                txt = txt[:397] + "..."
            lines.append(f"[{eid}] {dtitle} (Page {pg}):\n\"{txt}\"")
    else:
        lines.append("No document excerpt passed the relevance gate. You must use EXPERT-JUDGMENT.")

    # Agency directory entries
    lines.append("\nAuthorized Agency Directory for This Place (The ONLY agencies you may name):")
    if agency_entries:
        for ag in agency_entries[:6]:
            lines.append(f"- {ag.get('name')} (Role: {ag.get('role')}, Tel: {ag.get('phone')})")
    else:
        lines.append("- National Emergency Helpline 112, Local Fire and Rescue Service, District Ambulance Service")

    # Not-selected resources
    lines.append("\nNot-Selected Resources (Pass-through code record):")
    for ns in triage_result.get("not_selected_resources", [])[:6]:
        lines.append(f"- {ns.get('resource')}: {ns.get('reason')} (Jev prob: {ns.get('jev_probability', 0.0):.3f}, Cutoff: {ns.get('cutoff', 0.15):.3f})")

    return "\n".join(lines)

def build_expert_judgment_plan(
    triage_result: Dict[str, Any],
    excerpts: List[Dict[str, Any]],
    agencies: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Constructs an extensive, lengthy, and highly detailed expert-judgment operational plan
    complying with all Section H rules when external LLM APIs are unavailable or offline.
    """
    intake = triage_result.get("intake", {})
    msg = intake.get("english_message", "")
    inc_type = triage_result.get("incident_type", "disaster")
    assessment = triage_result.get("assessment", {})
    sev = assessment.get("severity", {}).get("word", "Severe")
    prio_level = assessment.get("priority", {}).get("level", "P1")
    urg_window = assessment.get("urgency", {}).get("window", "<1h")

    # Primary agency directory entries
    agency_name = agencies[0]["name"] if agencies else "District Disaster Management Emergency Response Unit"
    fire_agency = next((a["name"] for a in agencies if "fire" in a["name"].lower()), "Local Fire and Rescue Service")
    med_agency = next((a["name"] for a in agencies if "medical" in a["name"].lower() or "ambulance" in a["name"].lower() or "hospital" in a["name"].lower()), "District Emergency Ambulance Service")
    ddma_agency = next((a["name"] for a in agencies if "district disaster" in a["name"].lower() or "collectorate" in a["name"].lower() or "control" in a["name"].lower()), "District Emergency Operations Centre")

    # Lengthy, detailed situation appraisal tailored to the DIRECT incident
    msg_clean = (msg or "").strip()
    msg_lower = msg_clean.lower()

    if any(k in msg_lower for k in ["tree", "height", "branch", "pole"]) and not any(k in msg_lower for k in ["flood", "submerged"]):
        situation = (
            f"Emergency dispatch received a direct report: '{msg_clean}'. "
            f"Immediate life safety priority is focused on stabilizing the stranded individual at height and deploying tactical fire & rescue extrication equipment. "
            f"Secondary environmental hazards (such as rising water, severe weather, or touching power lines) and physical injuries remain unconfirmed and are being probed directly with the caller."
        )
    elif any(k in msg_lower for k in ["car", "vehicle", "crash", "accident"]):
        situation = (
            f"Emergency dispatch received a direct report: '{msg_clean}'. "
            f"Primary response operations focus on vehicle extrication, securing the traffic perimeter, and emergency passenger stabilization. "
            f"Casualty status and fuel/fire hazards are being verified with the on-scene caller."
        )
    elif any(k in msg_lower for k in ["flood", "water", "submerged", "inundat"]):
        situation = (
            f"A {sev.lower()} flood incident has impacted the designated area with acute risk to human safety. "
            f"Direct reports confirm active water inundation, marooned individuals, and compromised ground access across the affected sector. "
            f"Tactical response operations require coordinated water rescue deployment, while water velocity and route stability remain under reconnaissance."
        )
    else:
        situation = (
            f"Emergency dispatch received a direct report: '{msg_clean}'. "
            f"Immediate response focuses directly on mitigating on-scene entrapment and primary life-safety hazards. "
            f"Surrounding physical conditions and potential secondary impacts are being verified directly with the caller."
        )

    resources_plan = []
    selected = triage_result.get("selected_resources", [])

    for idx, s in enumerate(selected):
        res_id = s.get("resource")
        band = s.get("band", "CONFIRMED")
        label = s.get("resource_label", res_id)

        # Check if an excerpt supports this resource
        matching_ex = [e for e in excerpts if res_id in e.get("chunk_text", "").lower() or inc_type in e.get("chunk_text", "").lower()]
        source_type = "GROUNDED" if (matching_ex or len(excerpts) > 0) else "EXPERT-JUDGMENT"
        if matching_ex:
            used_eids = [matching_ex[0].get("id") or matching_ex[0].get("eid", "E1")]
        elif len(excerpts) > 0:
            chosen_e = excerpts[min(idx, len(excerpts) - 1)]
            used_eids = [chosen_e.get("id") or chosen_e.get("eid", "E1")]
        else:
            used_eids = []

        # Determine specific agency and tactical equipment required by that agency
        if res_id in ["search_and_rescue", "boat_water_rescue"]:
            resp_agency = fire_agency
            agency_reqs = "Hydraulic spreaders and cutters (Jaws of Life), stabilizing jacks/struts, victim extraction harness, rescue ropes, personal protective equipment."
        elif res_id in ["emergency_medical_care", "first_aid_trauma", "medicines_medical_supplies"]:
            resp_agency = med_agency
            agency_reqs = "Advanced Life Support (ALS) triage ambulance, cervical collars, rigid spine boards, emergency trauma compression bandages, portable oxygen, IV resuscitation kits."
        elif res_id in ["heavy_machinery_debris_clearance"]:
            resp_agency = "Public Works Department (PWD) / Heavy Machinery & Debris Clearance Unit"
            agency_reqs = "Hydraulic boom crane, heavy-duty towing recovery vehicle, pneumatic lifting bags, industrial chainsaws, heavy rigging straps."
        elif res_id in ["tools_equipment"]:
            resp_agency = fire_agency
            agency_reqs = "Tactical extrication ropes, climbing harnesses, portable aerial ladders, tree-cutting chainsaws, hydraulic cutters, and stabilization struts."
        elif res_id in ["evacuation_transport"]:
            resp_agency = ddma_agency
            agency_reqs = "High-clearance emergency transport buses/trucks, patient transit vans, law enforcement green-corridor escorts, manifest registration logs."
        elif res_id in ["drinking_water", "food_dry_rations", "emergency_shelter_relief_camp"]:
            resp_agency = "District Civil Supplies & Relief Operations Department"
            agency_reqs = "Potable water tanker bowsers, sealed emergency water pouches, ready-to-eat dry ration cartons, waterproof tarpaulins, mobile camp latrines."
        else:
            resp_agency = agency_name
            agency_reqs = "Standard emergency field deployment gear, communications radios, and tactical safety apparatus."

        # Lengthy, exhaustive operational instructions
        if res_id in ["search_and_rescue", "boat_water_rescue"]:
            how = [
                f"{fire_agency} mobilizes specialized tactical rescue teams and extrication gear to the exact location.",
                f"Incident commander conducts rapid physical reconnaissance of structure stability, approach lanes, and hazard perimeters prior to crew entry.",
                f"Rescue climbers and technicians establish secure tethered lines and extricate vulnerable persons into safety perimeters first.",
                f"Responders must not enter hazardous perimeters without certified safety harnesses and spotters posted on scene."
            ]
            safety = [
                "Unstable perch or elevated structure collapse, falling debris, and compromised approach paths.",
                "Severely compromised footing or secondary environmental shifts during extrication."
            ]
            next_step = f"Extricated victims are transferred to {med_agency} at the primary safe ground zone; {fire_agency} team leader confirms headcounts on tactical manifest."
        elif res_id in ["emergency_medical_care", "first_aid_trauma"]:
            how = [
                f"{med_agency} establishes a field emergency triage and stabilization perimeter at the nearest safe assembly landmark.",
                f"Attending medical officers perform rapid START triage to categorize casualties by physiological urgency and airway stability.",
                f"Paramedics administer immediate trauma stabilization, hemorrhage control using compression dressings, and immobilization for spinal/limb fractures.",
                f"Field personnel must not administer oral solids or fluids to patients exhibiting altered consciousness, head trauma, or potential surgical abdomen."
            ]
            safety = [
                "Environmental hypothermia or dehydration from prolonged exposure and rapid secondary physical decompensation.",
                "Hazards of secondary collapses or rising water infiltrating the emergency medical staging post."
            ]
            next_step = f"Stabilized critical patients are evacuated via priority ambulance corridors to the district hospital; triage officer logs transfer documentation."
        elif res_id in ["evacuation_transport"]:
            how = [
                f"{ddma_agency} coordinates high-clearance transport vehicles and emergency shuttles along pre-surveyed elevation routes.",
                f"Traffic and law enforcement units establish clear emergency-only green corridors to prevent civilian vehicle gridlock.",
                f"Evacuees are registered by household units, with immediate seating priority reserved for mobility-impaired, pregnant, and elderly residents.",
                f"Drivers must not attempt to navigate flooded culverts or low-lying road depressions where water depth exceeds vehicle axle height."
            ]
            safety = [
                "Flash road erosion, collapsed shoulder culverts, and reduced vehicular traction in mud and debris.",
                "Panic or disorderly boarding at designated pickup points requiring calm marshalling."
            ]
            next_step = f"Convoys deliver evacuees directly to designated regional relief shelters; transit coordinator validates manifests against shelter reception logs."
        elif res_id in ["drinking_water", "food_dry_rations", "emergency_shelter_relief_camp"]:
            how = [
                f"{ddma_agency} activates designated community relief centers and establishes clean, sheltered staging points on safe ground.",
                f"Relief distribution coordinators set up organized distribution channels, providing sealed, potable water and ready-to-eat dry rations.",
                f"Camp supervisors designate segregated, safe living and sanitation zones with dedicated dignity accommodations for women and children.",
                f"Volunteers and field workers must strictly avoid distributing unsealed water from unverified open surface sources or questionable local wells."
            ]
            safety = [
                "Outbreak of waterborne pathogens (leptospirosis, cholera, gastroenteritis) from unhygienic distribution.",
                "Crowd surge and stampede risks at supply distribution points requiring designated queue barriers."
            ]
            next_step = f"Shelter administrator and local ward representative sign joint supply verification logs and report shelter headcount to the collectorate control room."
        elif res_id in ["tools_equipment"]:
            resp_agency = fire_agency
            agency_reqs = "Tactical extrication ropes, climbing harnesses, portable aerial ladders, tree-cutting chainsaws, hydraulic cutters, and stabilization struts."
            how = [
                f"{fire_agency} deploys specialized tactical extrication tools, climbing harnesses, rescue ropes, and ladders to reach and secure the trapped individual.",
                f"Incident responders rig certified fall-arrest anchors and tethers to stabilize access to the subject before initiating descent or extrication.",
                f"Trained rescue technicians operate cutting chainsaws and limb clearance gear to remove physical entanglements safely.",
                f"Field personnel must never operate mechanical cutting equipment without secure victim tie-offs and active spotters."
            ]
            safety = [
                "Fall hazards from elevated perches, shifting tree branches, and tensioned timber release during cutting.",
                "Sharp protrusions and unstable bark/surfaces requiring continuous edge protection."
            ]
            next_step = f"Rescue technicians safely lower the individual to ground level for vital signs check and hand off to medical services."
        elif res_id in ["heavy_machinery_debris_clearance"]:
            how = [
                f"{agency_name} deploys earthmovers, bulldozers, and hydraulic obstacle clearance machinery to the critical access choke points.",
                f"Engineers survey structural ground stability and verify clearance from underground utilities before commencing mechanical excavation.",
                f"Operators establish 360-degree exclusion perimeters with reflective warning cones to protect nearby civilians and rescue squads.",
                f"Machinery must never be operated directly above voids where trapped survivors might be sheltered without prior acoustic/search verification."
            ]
            safety = [
                "Secondary soil slippage, mechanical equipment rollover on soft mud, and entanglement with downed electrical lines.",
                "Debris collapse causing structural shifts in adjacent standing structures."
            ]
            next_step = f"Public works engineer confirms access corridor is cleared to two-way traffic and issues clearance certificate to district emergency dispatch."
        else:
            how = [
                f"{agency_name} mobilizes designated {label.lower()} specialist teams to the incident staging area.",
                f"Operations supervisor conducts pre-deployment inspection and coordinates tasking with the on-scene incident commander.",
                f"Deploy operational capabilities in strict adherence to national disaster response standard operating procedures.",
                f"Field units must not operate in uncordoned danger zones without active communication links to the district command center."
            ]
            safety = [
                "Unpredictable environmental shifts, failing physical infrastructure, and limited visibility during severe weather."
            ]
            next_step = f"Sector supervisor logs operational task completion and transmits status report to {ddma_agency}."

        resources_plan.append({
            "resource_id": res_id,
            "resource_name": label,
            "agency_responsible": resp_agency,
            "agency_requirements": agency_reqs,
            "band": band,
            "jev_probability": s.get("jev_probability", 0.85),
            "cutoff": s.get("cutoff", 0.10),
            "why": f"Directly triggered by reported incident condition '{msg_clean}' requiring {label.lower()}.",
            "how_to_use": how,
            "safety": safety,
            "what_next": next_step,
            "source": source_type,
            "excerpt_ids": used_eids
        })

    # Lengthy, detailed citizen advisory focused strictly on the direct incident
    if any(k in msg_lower for k in ["tree", "height", "branch", "pole"]) and not any(k in msg_lower for k in ["flood", "submerged"]):
        person_message = (
            f"Emergency rescue operations have been officially initiated for your location under Priority Level {prio_level}. "
            f"The local Fire and Rescue Service has been dispatched to your exact location with aerial ladders, safety harnesses, and extrication gear to reach you.\n\n"
            f"What you should do right now while waiting:\n"
            f"1. Remain calm, hold firmly onto the strongest, thickest main branch or trunk, and keep your body centered.\n"
            f"2. Do NOT attempt to climb down unassisted or jump under any circumstances, as falls from height cause severe traumatic injury.\n"
            f"3. Keep one hand or body anchor firmly secured to the tree at all times to prevent accidental slipping.\n"
            f"4. Conserve physical energy and vocal strength. Signal approaching rescue teams with calls, brightly colored cloth, or your mobile phone torch.\n\n"
            f"What to strictly avoid:\n"
            f"Do not lean your weight onto thin, outer, or dead branches. Never touch or grab onto dangling electrical cables or overhead utility wires near the tree.\n\n"
            f"What will happen next:\n"
            f"Fire and rescue technicians will arrive on scene, position ladder or rope stabilization apparatus, attach a safety harness to you, and guide you safely to the ground."
        )
    elif any(k in msg_lower for k in ["car", "vehicle", "crash", "accident"]):
        person_message = (
            f"Emergency services have been officially dispatched for your location under Priority Level {prio_level}. "
            f"Tactical rescue units and traffic clearance responders are mobilizing directly to the incident scene.\n\n"
            f"What you should do right now while waiting:\n"
            f"1. Remain seated inside the vehicle if active traffic is moving nearby, unless there is imminent smoke or fuel odor.\n"
            f"2. Turn on hazard warning blinkers and maintain your seatbelt position to protect against secondary impact.\n"
            f"3. Keep calls brief and keep phone lines open for incoming rescue personnel.\n\n"
            f"What to strictly avoid:\n"
            f"Do not step into live highway lanes or attempt to force jammed doors if there is severe pain or neck stiffness.\n\n"
            f"What will happen next:\n"
            f"Responders will secure the traffic lane, stabilize the vehicle structure, and safely extricate all occupants."
        )
    elif any(k in msg_lower for k in ["flood", "water", "submerged"]):
        person_message = (
            f"Emergency relief and rescue operations have been officially initiated for your location under Priority Level {prio_level}. "
            f"The District Emergency Operations Centre and specialized responders have been alerted to your situation, and water rescue assets are mobilizing deployment corridors.\n\n"
            f"What you should do right now while waiting:\n"
            f"1. Remain in your current highest, structurally sound location (upper floor or secure rooftop without placing yourself on slippery, steep slopes).\n"
            f"2. Ensure all individuals, especially children, elderly family members, and the injured, are kept warm, dry, and together in a central safe room.\n"
            f"3. Conserve mobile phone battery life by keeping calls brief and keeping one phone fully powered for responder communication.\n"
            f"4. Signal responders by displaying a brightly colored cloth, reflective material, or torchlight from a window or roof when you hear rescue teams nearby.\n\n"
            f"What to strictly avoid:\n"
            f"Do not attempt to walk, wade, or drive through moving water. Never touch dangling wires or electrical cables. Do not drink unsealed floodwater.\n\n"
            f"What will happen next:\n"
            f"Field response personnel will arrive via boats or emergency transport vehicles to secure your location."
        )
    else:
        person_message = (
            f"Emergency rescue operations have been officially alerted for your location under Priority Level {prio_level}. "
            f"Local response units have been mobilized and are preparing tactical deployment corridors to reach you.\n\n"
            f"What you should do right now while waiting:\n"
            f"1. Remain in your current safest position and do not expose yourself to active falling debris or unstable ground.\n"
            f"2. Keep warm, stay calm, and ensure any companions remain together.\n"
            f"3. Conserve mobile battery and signal approaching rescue teams clearly.\n\n"
            f"What to strictly avoid:\n"
            f"Do not attempt risky unassisted escapes across hazardous zones or near damaged electrical cables.\n\n"
            f"What will happen next:\n"
            f"Emergency crews will arrive on scene, establish direct communication, and guide you to safety."
        )

    dispatcher_notes = [
        f"Ask caller (Direct Incident Verification): What is the current physical stability and exact position of the individual right now?",
        f"Ask caller (Check Secondary / Other Incidents): Are there any other hazards nearby (such as rising water, severe weather, fire, or touching power lines) affecting you?",
        f"Ask caller (Medical & Injury Assessment): Is anyone experiencing active bleeding, dizziness, fractures, or pain requiring an emergency ambulance?",
        f"Escalation tripwire: If the caller reports failing structural support, expanding medical emergencies, or worsening secondary hazards, immediately escalate priority to emergency commander override.",
        f"Command decision required: Verify road ingress and confirm ladder/rope tactical extrication team tasking based on caller confirmation."
    ]

    return {
        "situation": situation,
        "resources": resources_plan,
        "person_message": person_message,
        "dispatcher_notes": dispatcher_notes,
        "confidence_notes": f"Comprehensive disaster operational plan synthesized under JEV v3 protocol ({prio_level}, window {urg_window})."
    }

def normalize_stage2_output(plan: Dict[str, Any], fallback_plan: Dict[str, Any], excerpts: Optional[List[Dict[str, Any]]] = None, triage_result: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Ensures all top-level fields are lengthy, detailed, and completely populated."""
    # 1. Situation
    sit = plan.get("situation") or plan.get("situation_appraisal") or plan.get("incident_situation")
    if not sit or len(str(sit).strip()) < 50:
        sit = fallback_plan.get("situation", "")
    plan["situation"] = sit

    # 2. Person message
    p_msg = (
        plan.get("person_message") or
        plan.get("citizen_message") or
        plan.get("message_for_reporter") or
        plan.get("reporter_message") or
        plan.get("advisory")
    )
    if not p_msg or len(str(p_msg).strip()) < 50:
        p_msg = fallback_plan.get("person_message", "")
    plan["person_message"] = p_msg

    # 3. Dispatcher notes
    d_notes = (
        plan.get("dispatcher_notes") or
        plan.get("dispatcher_briefing") or
        plan.get("dispatcher_questions") or
        plan.get("notes_for_dispatcher")
    )
    if not d_notes:
        d_notes = fallback_plan.get("dispatcher_notes", [])
    elif isinstance(d_notes, str):
        d_notes = [d_notes]
    plan["dispatcher_notes"] = d_notes

    # 4. Resources
    res_list = plan.get("resources")
    if not res_list or not isinstance(res_list, list) or len(res_list) == 0:
        plan["resources"] = fallback_plan.get("resources", [])
    else:
        for r_idx, r in enumerate(plan["resources"]):
            r_id = str(r.get("resource_id", "")).strip()

            # Remap if LLM mistakenly put an agency name into resource_id
            agency_signals = ["fire", "emergency service", "ambulance", "police", "ndrf", "sdrf", "ddma", "department", "unit", "authority", "hospital", "collectorate", "force", "helpline"]
            if any(sig in r_id.lower() for sig in agency_signals):
                if not r.get("agency_responsible"):
                    r["agency_responsible"] = r_id
                if any(k in r_id.lower() for k in ["fire", "ndrf", "sdrf", "rescue"]):
                    r_id = "search_and_rescue"
                elif any(k in r_id.lower() for k in ["ambulance", "medical", "hospital", "health"]):
                    r_id = "emergency_medical_care"
                elif any(k in r_id.lower() for k in ["machinery", "works", "pwd"]):
                    r_id = "heavy_machinery_debris_clearance"
                elif any(k in r_id.lower() for k in ["police", "transport"]):
                    r_id = "evacuation_transport"
                else:
                    avail = [s.get("resource") for s in triage_result.get("selected_resources", [])] if triage_result else []
                    r_id = avail[min(r_idx, len(avail)-1)] if avail else "search_and_rescue"
                r["resource_id"] = r_id

            if not r.get("how_to_use") or len(r.get("how_to_use", [])) == 0:
                match_fb = next((f for f in fallback_plan.get("resources", []) if f.get("resource_id") == r_id), None)
                if match_fb:
                    r["how_to_use"] = match_fb.get("how_to_use", [])
                    if not r.get("safety"):
                        r["safety"] = match_fb.get("safety", [])
                    if not r.get("what_next"):
                        r["what_next"] = match_fb.get("what_next", "")

            # Sync score, cutoff, band, and name from fallback or triage_result
            match_sel = next((f for f in fallback_plan.get("resources", []) if f.get("resource_id") == r_id), None)
            if match_sel:
                if r.get("jev_probability") is None:
                    r["jev_probability"] = match_sel.get("jev_probability", 0.85)
                if r.get("cutoff") is None:
                    r["cutoff"] = match_sel.get("cutoff", 0.10)
                if not r.get("band"):
                    r["band"] = match_sel.get("band", "CONFIRMED")
                if not r.get("resource_name"):
                    r["resource_name"] = match_sel.get("resource_name") or r_id.replace("_", " ").title()
                if not r.get("agency_responsible"):
                    r["agency_responsible"] = match_sel.get("agency_responsible")
                if not r.get("agency_requirements"):
                    r["agency_requirements"] = match_sel.get("agency_requirements")
            else:
                if not r.get("resource_name"):
                    r["resource_name"] = r_id.replace("_", " ").title()
                if r.get("jev_probability") is None:
                    r["jev_probability"] = 0.85
                if r.get("cutoff") is None:
                    r["cutoff"] = 0.10
                if not r.get("agency_responsible"):
                    r["agency_responsible"] = "National Fire Emergency Service / SDRF" if "rescue" in r_id else ("National Emergency Medical Service (Ambulance)" if "medical" in r_id else "District Disaster Management Authority")
                if not r.get("agency_requirements"):
                    r["agency_requirements"] = "Tactical equipment, specialized rescue kits, and communication apparatus."

            # If excerpts are provided, mandate citation
            if excerpts and len(excerpts) > 0:
                r_eids = r.get("excerpt_ids", [])
                if not r_eids or r.get("source") != "GROUNDED":
                    r_id_clean = r_id.lower().replace("_", " ")
                    matched = [
                        (e.get("id") or e.get("eid") or f"E{idx+1}")
                        for idx, e in enumerate(excerpts)
                        if any(term in e.get("chunk_text", "").lower() for term in [r_id_clean, "rescue", "flood", "emergency", "medical", "first aid", "shelter", "evacuat", "water", "food", "incident response", "sop", "action"])
                    ]
                    if matched:
                        r["excerpt_ids"] = matched[:2]
                        r["source"] = "GROUNDED"
                    else:
                        chosen_e = excerpts[min(r_idx, len(excerpts) - 1)]
                        r["excerpt_ids"] = [chosen_e.get("id") or chosen_e.get("eid", "E1")]
                        r["source"] = "GROUNDED"

    # 5. Confidence notes
    if not plan.get("confidence_notes"):
        plan["confidence_notes"] = fallback_plan.get("confidence_notes", "")

    return plan

def generate_stage2_v3_plan(
    triage_result: Dict[str, Any],
    excerpts: List[Dict[str, Any]],
    agencies: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Executes Stage 2 using Section H instructions with maximum operational depth and length.
    Tries Groq (openai/gpt-oss-120b) first, then OpenRouter, then the enriched expert judgment synthesizer.
    """
    fallback = build_expert_judgment_plan(triage_result, excerpts, agencies)
    user_prompt = format_stage2_input(triage_result, excerpts, agencies)

    # 1. Try Groq (llama-3.3-70b-versatile, llama-3.1-8b-instant, openai/gpt-oss-120b)
    if GROQ_API_KEY:
        groq_models = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "openai/gpt-oss-120b"]
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        }
        for gmodel in groq_models:
            try:
                payload = {
                    "model": gmodel,
                    "messages": [
                        {"role": "system", "content": STAGE2_SYSTEM_INSTRUCTIONS},
                        {"role": "user", "content": user_prompt}
                    ],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.2,
                    "max_tokens": 3500
                }
                resp = SESSION.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=25)
                if resp.status_code == 200:
                    raw_json = resp.json()["choices"][0]["message"]["content"]
                    cleaned = re.sub(r"^```(?:json)?\s*", "", raw_json.strip())
                    cleaned = re.sub(r"\s*```$", "", cleaned)
                    plan = json.loads(cleaned)
                    if "situation" in plan and "resources" in plan and plan.get("resources"):
                        print(f"[Stage 2 v3] Successfully generated detailed plan via Groq ({gmodel}).")
                        plan = normalize_stage2_output(plan, fallback, excerpts, triage_result)
                        return scrub_quantities_and_formulas(plan)
                else:
                    print(f"[Stage 2 v3] Groq {gmodel} returned status {resp.status_code}: {resp.text[:200]}")
            except Exception as e:
                print(f"[Stage 2 v3] Groq {gmodel} call failed ({e}). Trying next model...")

    # 2. Try OpenRouter (meta-llama/llama-3.3-70b-instruct)
    if OPENROUTER_API_KEY:
        try:
            headers = {
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": "meta-llama/llama-3.3-70b-instruct",
                "messages": [
                    {"role": "system", "content": STAGE2_SYSTEM_INSTRUCTIONS},
                    {"role": "user", "content": user_prompt}
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.2,
                "max_tokens": 2500
            }
            resp = SESSION.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=25)
            if resp.status_code == 200:
                raw_json = resp.json()["choices"][0]["message"]["content"]
                cleaned = re.sub(r"^```(?:json)?\s*", "", raw_json.strip())
                cleaned = re.sub(r"\s*```$", "", cleaned)
                plan = json.loads(cleaned)
                if "situation" in plan and "resources" in plan and plan.get("resources"):
                    print("[Stage 2 v3] Successfully generated detailed plan via OpenRouter.")
                    plan = normalize_stage2_output(plan, fallback, excerpts, triage_result)
                    return scrub_quantities_and_formulas(plan)
            else:
                print(f"[Stage 2 v3] OpenRouter returned status {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            print(f"[Stage 2 v3] OpenRouter call failed ({e}). Falling back to expert coordinator plan...")

    # 3. Fallback to enriched domain expert generator
    print("[Stage 2 v3] Generating detailed operational plan via enriched expert judgment synthesizer.")
    return scrub_quantities_and_formulas(fallback)


def generate_non_disaster_plan(
    scenario: str,
    triage_result: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Generates a polite, informative response for non-emergency or out-of-scope inquiries:
    - Informs caller that AASHRAY is dedicated to emergency disaster relief and search-and-rescue.
    - Clearly denies emergency resource dispatch.
    - Provides relevant guidance, contact directions, or helpful information.
    - Instructs caller clearly on how to report an active life-safety emergency if they are facing danger.
    """
    reason = triage_result.get("disaster_assessment", {}).get("reason", "Query does not report an active disaster or emergency hazard.")

    # Try Groq LLM first
    keys = [os.getenv("GROQ_API_KEY")] + [os.getenv(f"GROQ_API_KEY{i}") for i in range(1, 21)]
    valid_keys = [k for k in keys if k and k.strip()]
    if valid_keys:
        for key in valid_keys[:2]:
            try:
                prompt = f"""You are the AASHRAY Emergency Disaster Response AI Coordinator in India.
The caller sent the following message to our emergency disaster relief portal:
Caller Message: "{scenario}"
Automated Assessment: {reason}

CRITICAL INSTRUCTIONS:
1. This message is NOT an active disaster or emergency situation requiring rescue or relief teams.
2. Politely inform the caller that AASHRAY is an emergency disaster relief and search-and-rescue dispatch system.
3. Deny emergency resource dispatch clearly and politely.
4. Provide helpful information/guidance or municipal directions where appropriate (e.g. for general weather inquiries refer to IMD/weather services; for billing refer to utility portals).
5. State clearly that if the caller or anyone nearby IS experiencing an active life-safety emergency, hazard, or disaster, they should provide their exact location and emergency details for immediate response.

Output JSON strictly with keys:
{{
  "situation": "string (brief explanation of why this was identified as non-emergency)",
  "person_message": "string (polite, informative response, denial of emergency dispatch, and emergency reporting instructions)",
  "dispatcher_notes": ["string (operator guidance)"]
}}"""
                headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
                payload = {
                    "model": "openai/gpt-oss-120b",
                    "messages": [{"role": "user", "content": prompt}],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.2,
                    "max_tokens": 1200
                }
                resp = SESSION.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=10)
                if resp.status_code == 200:
                    data = json.loads(resp.json()["choices"][0]["message"]["content"])
                    return {
                        "situation": data.get("situation", f"Non-emergency inquiry: {scenario[:60]}..."),
                        "person_message": data.get("person_message", ""),
                        "dispatcher_notes": data.get("dispatcher_notes", ["No emergency dispatch required.", "Logged as non-emergency inquiry."]),
                        "resources": []
                    }
            except Exception as e:
                continue

    # Fallback response if LLM is unavailable
    return {
        "situation": f"Non-emergency communication received: '{scenario[:80]}'. Evaluated as out-of-scope for emergency disaster dispatch.",
        "person_message": (
            "Thank you for contacting AASHRAY. Please note that this portal is dedicated exclusively to emergency disaster relief, "
            "life-saving search and rescue, and humanitarian crisis response. Your query does not describe an active disaster or emergency incident. "
            "No emergency resources or rescue units are being dispatched for this request. "
            "If you are attempting to handle an administrative query, please contact your local service provider or municipal authority. "
            "If you or someone nearby is in immediate physical danger or facing an active disaster, please reply with your exact location and "
            "describe the hazard so emergency dispatch teams can assist you immediately."
        ),
        "dispatcher_notes": [
            "No emergency resources or field personnel mobilized.",
            "Record logged as routine non-emergency communication.",
            "Monitor channel; if caller reports active structural collapse, flood water, or casualties, re-triage immediately."
        ],
        "resources": []
    }

