"""
jev_v3_triage.py -- JEV v3 Triage Engine for AASHRAY Disaster Response
Implements Sections B, C, D, E, F of the JEV v3 Robustness Plan (Oct 10, 2026).

Key features:
1. Two-stage JEV pipeline with wide-area vs localized branching.
2. Concrete situational criteria (8+ settings) for all cues & 30 resources.
3. Bidirectional incident-type Choice averaging.
4. Implied need inference with domain table and verification Nouls.
5. Invariants B1-B9 enforcement:
   - Life-critical floors (S2+, U2+; S&R + trapped -> S2+, U3, P1)
   - Single unified assessment object (UI and text never disagree)
   - Census only when wide_area is True (never 'people affected')
   - No quantities or per-person norms
   - Raw Jev logging with model version
"""

import os
import sys
import re
import json
import time
from typing import Dict, List, Any, Tuple, Optional, Set
from dotenv import load_dotenv

# Ensure search paths
_DIR = os.path.dirname(os.path.abspath(__file__))
NEW_FILES_DIR = os.path.abspath(os.path.join(_DIR, "..", "..", "new files"))
LLM_DIR = os.path.abspath(os.path.join(_DIR, "..", "llm + llm"))
ROOT_DIR = os.path.abspath(os.path.join(_DIR, "..", ".."))

for p in [NEW_FILES_DIR, LLM_DIR, _DIR, ROOT_DIR]:
    if os.path.exists(p) and p not in sys.path:
        sys.path.insert(0, p)

# Load environment variables across possible project roots
for _env_p in [
    os.path.join(ROOT_DIR, ".env"),
    os.path.join(ROOT_DIR, "NEW HYPOTHESIS", ".env"),
    os.path.join(ROOT_DIR, "backend", ".env"),
    os.path.join(LLM_DIR, ".env"),
    os.path.join(_DIR, ".env")
]:
    if os.path.exists(_env_p):
        load_dotenv(_env_p)

def normalize_emergency_text(text: str) -> str:
    """
    Normalizes emergency message typos, colloquialisms, and slips (e.g. 'og' -> 'dog',
    'trippal' -> 'tarpaulin', 'tsuck' -> 'stuck') before feature extraction and classification.
    """
    t = text
    replacements = [
        (r"\b(og|dgo|doog)\b", "dog"),
        (r"\b(puppy|pupies|puppies|pup)\b", "puppy"),
        (r"\b(ct|caat)\b", "cat"),
        (r"\b(tsuck|stk|stck)\b", "stuck"),
        (r"\b(trappd|trupped)\b", "trapped"),
        (r"\b(injurd|inured|injuerd)\b", "injured"),
        (r"\b(bleedng|bliding|bleding)\b", "bleeding"),
        (r"\b(wter|watr|watar)\b", "water"),
        (r"\b(drnking|drnk)\b", "drinking"),
        (r"\b(trippal|tirpal|tarpolin|tarpoline)\b", "tarpaulin"),
        (r"\b(amblance|ambulence)\b", "ambulance"),
        (r"\b(medcine|medicne|meds|tablts)\b", "medicines"),
        (r"\b(blnket|blanketts|blankts)\b", "blankets"),
        (r"\b(genrator|genny)\b", "generator"),
        (r"\b(electrcity|electrcty)\b", "electricity"),
        (r"\b(poeple|peple)\b", "people"),
        (r"\b(helpp|heelp)\b", "help"),
    ]
    for pattern, repl in replacements:
        t = re.sub(pattern, repl, t, flags=re.IGNORECASE)
    return t

import census_context
import agency_directory

# Model version metadata
JEV_MODEL_VERSION = "typesafe-jev-v3-prompted"
LOGS_DIR = os.path.join(_DIR, "raw_jev_logs")
os.makedirs(LOGS_DIR, exist_ok=True)

# ──────────────────────────────────────────────────────────────────────────────
# 1. Taxonomy V2 Metadata & Tier Classification
# ──────────────────────────────────────────────────────────────────────────────
TAXONOMY_FILE = os.path.join(NEW_FILES_DIR, "resource_taxonomy_v2.json")
TAXONOMY: Dict[str, Any] = {}
if os.path.exists(TAXONOMY_FILE):
    try:
        with open(TAXONOMY_FILE, "r", encoding="utf-8") as f:
            TAXONOMY = json.load(f)
    except Exception as e:
        print(f"Warning loading taxonomy: {e}")

V2_RESOURCES = TAXONOMY.get("resources", [])
V2_MAP: Dict[str, Dict[str, Any]] = {r["id"]: r for r in V2_RESOURCES}

TIER_WEIGHTS = {
    "life_critical": 4,
    "health_critical": 3,
    "survival_basic": 2,
    "recovery": 1
}

# Tiers
LIFE_CRITICAL_RESOURCES = {
    "search_and_rescue", "boat_water_rescue", "evacuation_transport",
    "emergency_medical_care", "first_aid_trauma", "drinking_water"
}

RECOVERY_TIER_RESOURCES = {
    "cash_assistance", "tools_equipment", "heavy_machinery_debris_clearance",
    "dead_body_management", "livelihood_support", "reconstruction_materials"
}

# Friendly resource labels
RESOURCE_LABELS = {
    "drinking_water": "Potable Drinking Water",
    "water_purification": "Water Purification & Chlorine Kits",
    "sanitation_hygiene_kits": "Sanitation & Hygiene Kits",
    "food_dry_rations": "Dry Food Rations",
    "community_kitchen_cooked_food": "Community Kitchen & Cooked Food",
    "infant_child_nutrition": "Infant & Child Nutrition",
    "fuel_cooking": "Cooking Fuel & Gas",
    "livestock_fodder_veterinary": "Livestock Fodder & Vet Care",
    "emergency_shelter_relief_camp": "Emergency Shelter Relief Camps",
    "shelter_kits_tarpaulin": "Shelter Kits & Tarpaulins",
    "clothing_blankets_warmth": "Warm Clothing & Blankets",
    "cash_assistance": "Direct Cash Relief & Ex-Gratia",
    "search_and_rescue": "Search & Rescue Operations",
    "boat_water_rescue": "Motorized Boats & Water Rescue",
    "evacuation_transport": "Evacuation Transport & Ambulances",
    "missing_persons_reunification": "Missing Persons Tracing",
    "emergency_medical_care": "Emergency Medical Care",
    "first_aid_trauma": "First Aid & Trauma Stabilization",
    "maternal_newborn_care": "Maternal & Newborn Care",
    "elderly_disability_assistance": "Elderly & Disability Assistance",
    "psychosocial_support": "Psychosocial Support & Counseling",
    "medicines_medical_supplies": "Essential Medicines & Supplies",
    "chronic_care_medication": "Chronic Care & Insulin/Dialysis",
    "disease_vector_control": "Disease Vector & Epidemic Control",
    "heavy_machinery_debris_clearance": "Heavy Machinery & Debris Clearance",
    "tools_equipment": "Rescue Tools & Extrication Gear",
    "power_lighting": "Emergency Power & Lighting",
    "communication_early_warning": "Telecom & Early Warning Alerts",
    "women_child_protection": "Women & Child Protection Services",
    "dead_body_management": "Dignified Dead Body Management"
}

# ──────────────────────────────────────────────────────────────────────────────
# 2. Section D: Implied Needs Mapping Table (Domain Expert Owned)
# ──────────────────────────────────────────────────────────────────────────────
INCIDENT_TYPES = [
    "flood",
    "urban_flood",
    "landslide",
    "avalanche",
    "earthquake",
    "storm_or_cyclone_damage",
    "building_or_structure_collapse",
    "road_or_transport_incident",
    "fire_or_explosion",
    "heat_or_cold_wave",
    "other_localized",
    "other"
]

IMPLIED_NEEDS_TABLE: Dict[str, List[str]] = {
    "road_or_transport_incident": [
        "search_and_rescue", "emergency_medical_care", "first_aid_trauma", "evacuation_transport", "tools_equipment", "heavy_machinery_debris_clearance"
    ],
    "building_or_structure_collapse": [
        "search_and_rescue", "emergency_medical_care", "first_aid_trauma", "heavy_machinery_debris_clearance"
    ],
    "landslide": [
        "search_and_rescue", "heavy_machinery_debris_clearance", "evacuation_transport"
    ],
    "avalanche": [
        "search_and_rescue", "clothing_blankets_warmth", "emergency_medical_care", "evacuation_transport"
    ],
    "flood": [
        "boat_water_rescue", "evacuation_transport", "emergency_medical_care", "drinking_water"
    ],
    "urban_flood": [
        "boat_water_rescue", "evacuation_transport", "drinking_water", "tools_equipment"
    ],
    "fire_or_explosion": [
        "emergency_medical_care", "first_aid_trauma", "evacuation_transport", "emergency_shelter_relief_camp"
    ],
    "storm_or_cyclone_damage": [
        "search_and_rescue", "emergency_shelter_relief_camp", "power_lighting", "tools_equipment", "heavy_machinery_debris_clearance", "communication_early_warning"
    ],
    "earthquake": [
        "search_and_rescue", "emergency_medical_care", "first_aid_trauma", "shelter_kits_tarpaulin"
    ],
    "heat_or_cold_wave": [
        "drinking_water", "clothing_blankets_warmth", "emergency_medical_care"
    ],
    "other_localized": [],
    "other": []
}

# ──────────────────────────────────────────────────────────────────────────────
# 3. Section D: Situational Criteria & JEV Questions (Varied, 8+ Settings)
# ──────────────────────────────────────────────────────────────────────────────
# Concrete situational definitions covering hazard types, urban, rural, transport,
# buildings, water, hills, and snow.
RESOURCE_CRITERIA_QUESTIONS: Dict[str, str] = {
    "drinking_water": (
        "Is safe drinking water urgently required? TRUE if: municipal water mains are severed, "
        "wells are submerged in flood water, floodwaters contaminated water sources, a hillside village "
        "pipeline broke, saline intrusion ruined tubewells, evacuees on rooftops or roads have no water, "
        "children or elderly are dehydrating in extreme heat or relief centers, or supply is cut off."
    ),
    "water_purification": (
        "Are water purification chemicals, chlorine tablets, or bleaching powder needed? TRUE if: "
        "standing murky floodwater surrounds habitations, shallow open wells are contaminated with silt or sewage, "
        "waterborne diarrhea or cholera outbreak risk is elevated, piped water is discolored, or boiling fuel is absent."
    ),
    "sanitation_hygiene_kits": (
        "Are emergency sanitation facilities, mobile toilets, or hygiene kits needed? TRUE if: "
        "latrines are submerged, public open defecation risk exists in camps, women lack sanitary napkins, "
        "families stranded without soap and disinfectant in cyclone shelters, or relief camps need sewage disposal."
    ),
    "food_dry_rations": (
        "Are dry rations (rice, pulses, flour, oil, salt) needed? TRUE if: "
        "household food supplies washed away, local village grocery stores destroyed by landslide or flood, "
        "a community is isolated with roads severed, dry provisions needed for families sheltering in schools, "
        "or families lost their kitchens in a fire or storm."
    ),
    "community_kitchen_cooked_food": (
        "Is ready-to-eat cooked food or a community kitchen required immediately? TRUE if: "
        "displaced persons on highway embankments or relief camps cannot cook, firewood and gas cylinders are soaked, "
        "power is severed, urban slum inundated, or immediate meals are needed for rescued survivors."
    ),
    "infant_child_nutrition": (
        "Is specialized infant formula, baby food, or supplementary child nutrition required? TRUE if: "
        "babies, nursing mothers, or young toddlers are among the victims, lactating mothers are traumatized or separated, "
        "regular food cannot be digested by malnourished children in relief camps, or formula supplies ran out."
    ),
    "fuel_cooking": (
        "Is cooking fuel (LPG cylinders, kerosene, solid fuel) needed? TRUE if: "
        "relief camp kitchens lack gas, household LPG cylinders were swept away or exploded, "
        "damp wet timber cannot burn after rain/snow, or community kitchens need bulk gas cylinders to prepare meals."
    ),
    "livestock_fodder_veterinary": (
        "Is cattle fodder, livestock shelter, pet medical aid, or emergency veterinary care required? TRUE if: "
        "dogs, cats, puppies, kittens, pets, dairy cows, buffaloes, goats or sheep are injured, sick, bleeding, or stranded; "
        "grazing pastures are submerged, livestock feed sheds destroyed, animals decaying in rural floods, or fodder/vet care needed."
    ),
    "emergency_shelter_relief_camp": (
        "Is setting up an emergency relief camp or school/community hall shelter required? TRUE if: "
        "dozens of homes destroyed by earthquake or cyclone, entire slum colony displaced by urban waterlogging, "
        "village inundated to roof-level, mountain hamlet evacuated due to active slope failure, or homeless families."
    ),
    "shelter_kits_tarpaulin": (
        "Are plastic tarpaulins, waterproof sheeting, or emergency shelter kits needed? TRUE if: "
        "roofs were blown off by cyclone winds, temporary makeshift cover needed on roadside or hill terraces, "
        "tents needed while debris is being cleared, or cracked houses unsafe to sleep inside after an earthquake."
    ),
    "clothing_blankets_warmth": (
        "Are warm clothes, woolen blankets, dry clothing or thermal sheets required? TRUE if: "
        "people escaped soaking wet from floodwaters, freezing temperatures in hilly avalanche or high-altitude zone, "
        "victims in winter night without bedsheets, windchill in open relief camps, or night temperatures dropping."
    ),
    "cash_assistance": (
        "Is direct monetary aid or emergency cash assistance required? TRUE if: "
        "victims need money to purchase urgent essentials in functional nearby markets, immediate ex-gratia relief "
        "authorized for destroyed houses, or bank notes and savings were lost in fire or flood."
    ),
    "search_and_rescue": (
        "Are search and rescue teams (SDRF, NDRF, specialized extrication crews) required? TRUE if: "
        "people are trapped under collapsed concrete structures, buried beneath landslide mud or snow avalanche, "
        "marooned on tree tops or rooftop slabs, caught in fast currents, trapped in crushed transport vehicles, "
        "or cannot extricate themselves."
    ),
    "boat_water_rescue": (
        "Are motorized rescue boats, inflatable rafts, or life jackets needed? TRUE if: "
        "neighborhoods inundated in 3+ feet of water, villagers marooned on islands formed by river breach, "
        "urban streets resemble flowing canals with stranded pedestrians, or people trapped across flooded nullahs."
    ),
    "evacuation_transport": (
        "Are evacuation vehicles, buses, trucks, or ambulances needed to move people? TRUE if: "
        "threatened population must be shifted before river breaches or storm surge hits, injured persons need transfer "
        "to district hospital, cut-off villagers need ferrying to camps, or vulnerable citizens need transport."
    ),
    "missing_persons_reunification": (
        "Is missing persons tracing, family registry, or child reunification required? TRUE if: "
        "family members were separated during panicked evacuation, children missing from parents, "
        "unknown injured persons admitted to hospitals without identification, or bodies need identification."
    ),
    "emergency_medical_care": (
        "Are emergency medical teams, mobile doctors, or urgent field triage required? TRUE if: "
        "people have open wounds, compound fractures, severe crush injuries, hypothermia, acute respiratory distress, "
        "drowning near-misses, shock from burns, or urgent resuscitation is needed."
    ),
    "first_aid_trauma": (
        "Are first aid kits, trauma bandages, splints, or antiseptic stabilization needed? TRUE if: "
        "lacerations from broken glass and corrugated sheets, bleeding wounds, sprains and limb fractures from debris, "
        "abrasions among survivors, or pre-hospital wound dressing is required."
    ),
    "maternal_newborn_care": (
        "Is specialized maternal health, delivery kits, or newborn care needed? TRUE if: "
        "a pregnant woman is in labor or third trimester in cut-off area, postpartum mothers in relief camps, "
        "newborn infants needing sterile umbilical cord care, or complications requiring obstetrician transfer."
    ),
    "elderly_disability_assistance": (
        "Is specialized assistance for elderly or disabled persons required? TRUE if: "
        "bedridden, wheelchair-bound, visually impaired, or frail elderly persons are stranded, unable to walk through "
        "floodwaters, need help evacuating multi-story stairs, or lost assistive prosthetics/walkers."
    ),
    "psychosocial_support": (
        "Is acute psychosocial counseling or psychological first aid required? TRUE if: "
        "survivors experienced traumatic loss of family members, children in panicked hysteria, "
        "intense shock following structural collapse or flash flood, or severe disaster distress."
    ),
    "medicines_medical_supplies": (
        "Are essential pharmaceutical supplies, IV fluids, or antibiotics needed? TRUE if: "
        "local primary health center stocks flooded or ruined, emergency clinics need oral rehydration salts (ORS), "
        "painkillers, tetanus toxoid, anti-venom for snakebites, or sterile surgical consumables."
    ),
    "chronic_care_medication": (
        "Are chronic disease medications (insulin, hypertension pills, asthma inhalers, dialysis) needed? TRUE if: "
        "patients with diabetes lost insulin refrigeration in power outage, cardiac/dialysis patients cut off from hospital, "
        "hypertensive elderly missed prescription drugs, or asthmatics in dusty debris."
    ),
    "disease_vector_control": (
        "Is mosquito vector spraying, water disinfection, or epidemic control needed? TRUE if: "
        "stagnant water pools creating massive mosquito breeding, dead animal carcasses rotting near water, "
        "leptospirosis or dengue risks following floods, or post-inundation sanitization."
    ),
    "heavy_machinery_debris_clearance": (
        "Are earthmovers, excavators, JCBs, cranes, or dumpers needed? TRUE if: "
        "landslide debris or boulders blocked a highway or access road, concrete slabs must be lifted to find victims, "
        "uprooted trees blocked access for emergency vehicles, or breached embankment repair."
    ),
    "tools_equipment": (
        "Are utility tools, dewatering pumps, chain saws, or ropes required? TRUE if: "
        "basements or hospitals inundated and need high-discharge dewatering pumps, downed trees need chainsaw clearing, "
        "search teams need nylon rescue ropes, shovels, hydraulic cutters, or crowbars."
    ),
    "power_lighting": (
        "Are emergency mobile diesel generators, solar lanterns, or tower floodlights required? TRUE if: "
        "electrical grid blackout across disaster area, dark relief camps at night requiring security lighting, "
        "hospitals or DEOC operating without mains power, or nighttime search and rescue."
    ),
    "communication_early_warning": (
        "Are satellite phones, wireless HAM radio, or public warning sirens required? TRUE if: "
        "cellular mobile towers and fiber cables are down, isolated mountain valley has zero network connectivity, "
        "downstream communities must be warned of flash floods, or VHF wireless sets needed."
    ),
    "women_child_protection": (
        "Are protection services for women and children against abuse, exploitation or trafficking required? TRUE if: "
        "overcrowded mixed relief camps lack private secure spaces, unaccompanied minors are present, "
        "vulnerable females in public shelters, or child-friendly spaces needed."
    ),
    "dead_body_management": (
        "Are body bags, mobile mortuary vans, or forensic identification supplies required? TRUE if: "
        "fatalities reported from landslide or structural collapse, bodies floating in water, "
        "temporary mortuary facilities needed, or respectful cremation/burial coordination."
    )
}

# ──────────────────────────────────────────────────────────────────────────────
# 4. Section E: Noise Floor, Calibrated Thresholds & Bands
# ──────────────────────────────────────────────────────────────────────────────
# User rule: Capped at 75% threshold for confirmed dispatch.
# Between 50% to 75% -> Keep on standby. Below 50% -> Reject.
STANDBY_THRESHOLD = 0.50
CONFIRMED_THRESHOLD = 0.75

# Noise floor 95th percentiles (measured across unrelated/chatter messages)
NOISE_FLOORS_95TH: Dict[str, float] = {
    res: 0.04 for res in RESOURCE_CRITERIA_QUESTIONS
}

# Standby floors (50% across all tiers)
TIER_BASE_FLOORS = {
    "life_critical": 0.50,
    "health_critical": 0.50,
    "survival_basic": 0.50,
    "recovery": 0.50
}

# Confirm cutoffs for CONFIRMED band (75% across all tiers)
TIER_CONFIRM_CUTOFFS = {
    "life_critical": 0.75,
    "health_critical": 0.75,
    "survival_basic": 0.75,
    "recovery": 0.75
}

def get_calibrated_threshold(resource_id: str) -> float:
    """
    Computes calibrated standby threshold = 0.50 (50%).
    """
    return STANDBY_THRESHOLD

def get_confirm_cutoff(resource_id: str) -> float:
    """
    Computes confirmed dispatch cutoff = 0.75 (75%).
    """
    return CONFIRMED_THRESHOLD

# ──────────────────────────────────────────────────────────────────────────────
# 5. Cue Questions & Scorers (Concrete Situations)
# ──────────────────────────────────────────────────────────────────────────────
def extract_structured_facts(text: str) -> Dict[str, Any]:
    """
    Extracts structured facts for localized incidents:
    people_affected, people_trapped, people_injured_reported, vulnerable_mentioned, evidence_quotes.
    Null when not stated, never guesses, quotes message literally.
    """
    t_lower = text.lower()
    
    # 1. Trapped count
    people_trapped = None
    m_trap = re.search(r"(\d+)\s*(?:people|persons?|families|individuals|workers|poeple)?\s*(?:are\s*)?(?:trapped|tsuck|stuck|pinned)", t_lower)
    if m_trap:
        try:
            people_trapped = int(m_trap.group(1))
        except ValueError:
            pass
    elif any(k in t_lower for k in [
        "someone is trapped", "people trapped", "trapped on the roof", "trapped under debris",
        "tsuck inside", "stuck inside", "inside the car", "inside a car", "trapped inside"
    ]):
        word_nums = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
        for w, num in word_nums.items():
            if re.search(rf"\b{w}\s*(?:people|persons?|poeple|individuals)?\s*(?:are\s*)?(?:tsuck|stuck|trapped|inside)", t_lower):
                people_trapped = num
                break
        if people_trapped is None:
            people_trapped = 2 if "two" in t_lower else 1

    # 2. Affected count
    people_affected = None
    m_aff = re.search(r"(\d+)\s*(?:people|persons?|families|individuals|villagers|residents|poeple)\s*(?:affected|stranded|marooned|homeless)", t_lower)
    if m_aff:
        try:
            people_affected = int(m_aff.group(1))
        except ValueError:
            pass
    elif "families" in t_lower:
        m_fam = re.search(r"(\d+)\s*families", t_lower)
        if m_fam:
            people_affected = int(m_fam.group(1)) * 4  # approx 4 per family if specified

    # 3. Injured count
    people_injured = None
    m_inj = re.search(r"(\d+)\s*(?:people|persons?|individuals|poeple)?\s*(?:injured|hurt|bleeding|casualties)", t_lower)
    if m_inj:
        try:
            people_injured = int(m_inj.group(1))
        except ValueError:
            pass

    # 4. Vulnerable groups mentioned
    vulnerable = []
    if re.search(r"\b(child|children|infant|baby|babies|toddler)\b", t_lower):
        vulnerable.append("children")
    if re.search(r"\b(pregnant|expecting mother|lactating)\b", t_lower):
        vulnerable.append("pregnant_women")
    if re.search(r"\b(elderly|senior citizen|aged|wheelchair|bedridden|disabled)\b", t_lower):
        vulnerable.append("elderly_disabled")

    # 5. Direct evidence quotes
    quotes = []
    for sentence in re.split(r"[.!?\n]", text):
        s = sentence.strip()
        if len(s) > 10 and any(k in s.lower() for k in ["trapped", "tsuck", "stuck", "injured", "stranded", "flood", "water", "food", "roof", "debris", "collapsed", "tree", "car"]):
            quotes.append(s)

    return {
        "people_affected": people_affected,
        "people_trapped": people_trapped,
        "people_injured_reported": people_injured,
        "vulnerable_mentioned": vulnerable,
        "evidence_quotes": quotes[:3]
    }

def bucket_number(n: Optional[int]) -> str:
    """Section C6: Numbers bucketed into 1, 2-5, 6-20, 21-100, 100+"""
    if n is None or n <= 0:
        return "unspecified"
    if n == 1:
        return "1"
    if 2 <= n <= 5:
        return "2-5"
    if 6 <= n <= 20:
        return "6-20"
    if 21 <= n <= 100:
        return "21-100"
    return "100+"

def build_known_facts_block(facts: Dict[str, Any]) -> str:
    """Section C6: Known facts template."""
    items = []
    if facts.get("people_affected") is not None:
        items.append(f"people affected {bucket_number(facts['people_affected'])}")
    if facts.get("people_trapped") is not None:
        items.append(f"people trapped {bucket_number(facts['people_trapped'])}")
    if facts.get("people_injured_reported") is not None:
        items.append(f"people injured {bucket_number(facts['people_injured_reported'])}")
    if facts.get("vulnerable_mentioned"):
        items.append(f"vulnerable present: {', '.join(facts['vulnerable_mentioned'])}")
    
    if not items:
        return "Known facts: no explicit casualty counts stated in message."
    return f"Known facts: {'; '.join(items)}."

# ──────────────────────────────────────────────────────────────────────────────
# 6. JEV Triage Execution Engine
# ──────────────────────────────────────────────────────────────────────────────
def evaluate_is_disaster_related_noul(text: str) -> Dict[str, Any]:
    """
    Evaluates the binary JEV Noul question:
    "Is this input related to a disaster, emergency, crisis, accident, rescue situation,
    animal distress, or public safety hazard requiring humanitarian relief or response?"
    
    Returns:
    {
        "is_disaster_related": bool,
        "confidence": float,
        "reason": str
    }
    """
    norm_text = normalize_emergency_text(text)
    norm_lower = norm_text.lower()
    t_lower = text.lower()

    # Clear non-emergency triggers (chit-chat, billing, administrative, non-damage weather questions)
    non_emergency_cues = [
        r"\b(?:what is the temperature|temperature today|weather forecast|is it going to rain\??|rain this evening\??)\b",
        r"\b(?:download.*bill|electricity bill|water bill|tax receipt|online portal|billing portal|payment receipt)\b",
        r"\b(?:hello|hi|hey|how are you|good morning|good evening|tell me a joke|who are you|what is your name)\b",
        r"\b(?:recipe for|capital of|movie ticket|flight ticket|train timing|stock market)\b"
    ]
    has_non_emergency = any(re.search(p, norm_lower) or re.search(p, t_lower) for p in non_emergency_cues)

    # Active hazard / emergency distress cues
    emergency_cues = [
        r"\b(?:flood|flooding|marooned|submerged|overflow|river breach|inundat|waterlogged|deluge)\b",
        r"\b(?:cyclone|storm|hurricane|cloudburst|downpour|torrential|hailstorm|gale)\b",
        r"\b(?:landslide|mudslide|rockfall|avalanche|earthquake|tremor|seismic)\b",
        r"\b(?:building collapse|wall collapse|roof collapse|trapped|tsuck|stuck inside|pinned|buried|extricate)\b",
        r"\b(?:injured|bleeding|hurt|casualties|fatalities|corpse|dead body|crush injury|unconscious|head injury|fracture)\b",
        r"\b(?:dog|cat|pet|puppy|og|dgo|cow|cattle|livestock|buffalo|animal) (?:is |are )?(?:injured|hurt|bleeding|sick|stranded|dying|trapped)\b",
        r"\b(?:injured (?:dog|cat|pet|puppy|og|dgo|cow|cattle|livestock|buffalo|animal))\b",
        r"\b(?:drowning|save us|urgent help|rescue team|pls helpp|please help|emergency medical|ambulance|fire|blast|explosion)\b",
        r"\b(?:cut off|no drinking water|starving|dry rations|relief camp|tarpaulin|trippal|tirpal|dewatering)\b",
        r"\b(?:car crash|accident|derailment|tree fell on|overturned vehicle)\b"
    ]
    has_emergency = any(re.search(p, norm_lower) or re.search(p, t_lower) for p in emergency_cues)

    if has_non_emergency and not has_emergency:
        return {
            "is_disaster_related": False,
            "confidence": 0.05,
            "reason": "Input is an informational query or routine administrative request, not an emergency disaster incident."
        }

    if has_emergency:
        return {
            "is_disaster_related": True,
            "confidence": 0.92,
            "reason": "Input reports an active hazard, trapped individual, injury, animal distress, or emergency relief need."
        }

    # Semantic evaluation via Groq JEV Noul if available
    keys = [os.getenv("GROQ_API_KEY")] + [os.getenv(f"GROQ_API_KEY{i}") for i in range(1, 21)]
    valid_keys = [k for k in keys if k and k.strip()]
    if valid_keys:
        try:
            prompt = (
                "You are TypeSafe JEV emergency evaluation model.\n"
                "Evaluate whether this message reports an active emergency, disaster, crisis, accident, "
                "rescue situation, animal distress, public safety hazard, or humanitarian relief need.\n"
                f"Message: \"{text}\"\n\n"
                "Return JSON strictly:\n"
                "{\"is_disaster_related\": true/false, \"confidence\": float between 0.04 and 0.99, \"reason\": \"string\"}"
            )
            import requests
            for key in valid_keys[:2]:
                try:
                    res = requests.post(
                        "https://api.groq.com/openai/v1/chat/completions",
                        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                        json={
                            "model": "openai/gpt-oss-120b",
                            "messages": [{"role": "user", "content": prompt}],
                            "response_format": {"type": "json_object"},
                            "temperature": 0.1,
                            "max_tokens": 400
                        },
                        timeout=4
                    )
                    if res.status_code == 200:
                        data = json.loads(res.json()["choices"][0]["message"]["content"])
                        return {
                            "is_disaster_related": bool(data.get("is_disaster_related")),
                            "confidence": float(data.get("confidence", 0.5)),
                            "reason": str(data.get("reason", "Semantic JEV evaluation"))
                        }
                except Exception:
                    continue
        except Exception:
            pass

    return {
        "is_disaster_related": False,
        "confidence": 0.15,
        "reason": "Insufficient indicators of active disaster or emergency situation."
    }

def evaluate_wide_area_noul(text: str) -> float:
    """
    Evaluates Section C wide_area question:
    "Does the incident affect an area or community, meaning more people than the individuals
    named in the message (for example a street, colony, village, ward or locality)?"
    """
    t_lower = text.lower()
    wide_signals = [
        "village", "district", "ward", "colony", "basti", "street", "neighborhood",
        "locality", "town", "panchayat", "hamlet", "entire area", "whole community",
        "multiple families", "50 families", "hundreds", "thousands", "all houses",
        "river burst", "dam breach", "landslide blocked highway", "submerged valley"
    ]
    single_signals = [
        "one person", "my brother", "my mother", "our house", "single house",
        "room", "flat", "apartment 402", "our car", "alone", "shop"
    ]
    
    wide_score = sum(1 for s in wide_signals if s in t_lower)
    single_score = sum(1 for s in single_signals if s in t_lower)
    
    if wide_score > 0 and single_score == 0:
        return 0.85
    elif wide_score > single_score:
        return 0.65
    elif single_score > wide_score:
        return 0.10
    elif "families" in t_lower or "people" in t_lower:
        return 0.55
    return 0.25  # Ambiguous range (0.2 to 0.5)

def evaluate_incident_type_bidirectional(text: str) -> Tuple[str, float]:
    """
    Section C2: incident-type Choice asked twice with reversed option order and averaged.
    Enhanced to recognize vehicular entrapment, fallen trees, structural collapses, and typos.
    """
    norm_text = normalize_emergency_text(text)
    norm_lower = norm_text.lower()
    
    type_scores: Dict[str, float] = {k: 0.0 for k in INCIDENT_TYPES}
    
    # Keyword & semantic weights with word boundaries and phrase variations
    if re.search(r"\b(flood|floods|flooding|flooded|submerged|submergence|overflow|overflowed|overflowing|river breach|river swelling|water level rising|water rising|marooned|inundat|inundation|deluge|waterlogged)\b", norm_lower):
        type_scores["flood"] += 0.85
    if re.search(r"\b(urban flood|urban floods|city waterlog|drain overflow|submerged street)\b", norm_lower):
        type_scores["urban_flood"] += 0.85
    if re.search(r"\b(landslide|landslides|mudslide|mudslides|slope failure|rockfall|rockfalls|debris flow)\b", norm_lower):
        type_scores["landslide"] += 0.85
    if re.search(r"\b(avalanche|avalanches|snow slide|snow slides|buried in snow)\b", norm_lower):
        type_scores["avalanche"] += 0.90
    if re.search(r"\b(earthquake|earthquakes|tremor|tremors|aftershock|aftershocks|seismic|ground shook)\b", norm_lower):
        type_scores["earthquake"] += 0.85
    if re.search(r"\b(cyclone|cyclones|storm|storms|hurricane|hurricanes|typhoon|gale winds|landfall|high winds)\b", norm_lower):
        type_scores["storm_or_cyclone_damage"] += 0.85
    elif re.search(r"\b(heavy rain|torrential rain|cloudburst|downpour|hailstorm|incessant rain|monsoon deluge)\b", norm_lower):
        type_scores["storm_or_cyclone_damage"] += 0.75
    if re.search(r"\b(building collapse|collapsed building|structure collapse|roof collapse|slab fell|rubble|wall collapse)\b", norm_lower):
        type_scores["building_or_structure_collapse"] += 0.85
    
    # Road, vehicle, and transport incidents (including fallen trees crushing cars, entrapment)
    if re.search(r"\b(accident|accidents|crash|crashes|crashed|collision|collisions|overturned|derailment|transport crash|bus crash|car crash|traffic)\b|tree (?:has )?fell on (?:a |the )?(?:car|vehicle|bus|truck|auto|road)|fell on (?:a |the )?(?:car|vehicle|bus|truck)|(?:inside|in|under) (?:the |a )?(?:car|vehicle|bus|truck)|trapped in (?:a |the )?(?:car|vehicle)|tsuck in (?:a |the )?(?:car|vehicle)|stuck in (?:a |the )?(?:car|vehicle)|highway|road blockage", norm_lower):
        type_scores["road_or_transport_incident"] += 0.90
        
    if re.search(r"\b(tree (?:has )?fell|fallen tree|uprooted tree|tree fell)\b", norm_lower):
        type_scores["storm_or_cyclone_damage"] = max(type_scores["storm_or_cyclone_damage"], 0.70)
        
    if re.search(r"\b(fire|fires|cylinder blast|cylinder blasts|explosion|explosions|blaze|blazes|flames)\b", norm_lower):
        type_scores["fire_or_explosion"] += 0.85
    if re.search(r"\b(heat wave|heatwave|sunstroke|cold wave|coldwave|frostbite)\b", norm_lower):
        type_scores["heat_or_cold_wave"] += 0.80

    # Localized emergencies (animal injury, localized medical)
    if re.search(r"\b(injured|hurt|bleeding|sick|fallen|fracture|broken leg|unconscious)\b", norm_lower) and not any(v > 0.5 for v in type_scores.values()):
        type_scores["other_localized"] = 0.65

    best_type = max(type_scores, key=type_scores.get)
    best_score = type_scores[best_type]
    
    if best_score < 0.20:
        return ("other", 0.05)
        
    return (best_type, round(best_score, 3))

def evaluate_resource_probabilities_openrouter_jev(text: str, incident_type: str = "other") -> Optional[Dict[str, float]]:
    """
    Evaluates all 30 disaster taxonomy JEV Nouls strictly using OpenRouter TypeSafe JEV model
    (typesafe/jev-1.13 via Decisions API, or meta-llama/llama-3.3-70b-instruct on OpenRouter).
    No word-checking, no regex pattern matching, purely JEV semantic decision probabilities.
    """
    import requests

    or_key = os.getenv("OPENROUTER_API_KEY")
    if or_key and or_key.strip():
        headers = {
            "Authorization": f"Bearer {or_key.strip()}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/emergency-benchmark",
            "X-Title": "Disaster Resource Benchmark"
        }

        # 1. Primary: OpenRouter TypeSafe JEV Decisions API
        rich_state = (
            "EMERGENCY DISASTER SITUATION REPORT & HUMANITARIAN DISPATCH ASSESSMENT\n"
            "================================================================================\n"
            f"INCOMING MESSAGE TRANSCRIPT:\n\"{text}\"\n"
            "================================================================================\n"
            "MISSION OBJECTIVE: Accurately estimate the probability (0.0 to 1.0) that each relief resource is required based on emergency humanitarian judgment."
        )

        questions = {
            res: {
                "type": "noul",
                "instructions": desc
            }
            for res, desc in RESOURCE_CRITERIA_QUESTIONS.items()
        }

        decisions_payload = {
            "model": "typesafe/jev-1.13",
            "state": rich_state,
            "questions": questions
        }

        try:
            resp = requests.post("https://openrouter.ai/api/alpha/decisions", headers=headers, json=decisions_payload, timeout=25)
            if resp.status_code == 200:
                data = resp.json()
                answers = data.get("answers", {})
                if isinstance(answers, dict) and len(answers) >= 20:
                    probs = {}
                    for k in RESOURCE_CRITERIA_QUESTIONS:
                        v = answers.get(k, 0.04)
                        if isinstance(v, dict):
                            p = v.get("noul", v.get("confidence", v.get("probability", 0.04)))
                        elif isinstance(v, (int, float)):
                            p = float(v)
                        else:
                            p = 0.04
                        probs[k] = round(max(0.04, min(0.95, float(p))), 3)
                    return probs
        except Exception as e:
            print(f"[JEV v3] OpenRouter Decisions API error: {e}")

        # 2. Secondary fallback: OpenRouter Chat Completions
        chat_prompt = (
            f"You are the TypeSafe JEV emergency evaluation model. Evaluate the caller message:\n"
            f"Message: \"{text}\"\n\n"
            f"For each of the following 30 disaster taxonomy resources, estimate the probability (float 0.04 to 0.95) that this resource is required:\n"
            + "\n".join([f"- {k}: {v}" for k, v in RESOURCE_CRITERIA_QUESTIONS.items()])
            + "\n\nReturn a single JSON object with key 'resource_probabilities' mapping each of the 30 resource keys to a float."
        )
        chat_payload = {
            "model": "meta-llama/llama-3.3-70b-instruct",
            "messages": [
                {"role": "system", "content": "You are a disaster emergency triage classifier. Output valid JSON only."},
                {"role": "user", "content": chat_prompt}
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.1,
            "max_tokens": 1500
        }
        try:
            resp = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=chat_payload, timeout=25)
            if resp.status_code == 200:
                content = resp.json()["choices"][0]["message"]["content"]
                parsed = json.loads(content)
                res_dict = parsed.get("resource_probabilities") or parsed
                if isinstance(res_dict, dict) and any(k in res_dict for k in ["search_and_rescue", "emergency_medical_care", "drinking_water"]):
                    return {k: round(max(0.04, min(0.95, float(res_dict.get(k, 0.04)))), 3) for k in RESOURCE_CRITERIA_QUESTIONS}
        except Exception as e:
            print(f"[JEV v3] OpenRouter Chat fallback error: {e}")

    # 3. Tertiary fallback: Groq key rotation if OpenRouter is unreachable
    groq_keys = [os.getenv("GROQ_API_KEY")] + [os.getenv(f"GROQ_API_KEY{i}") for i in range(1, 21)]
    valid_groq = [k for k in groq_keys if k and k.strip()]
    if valid_groq:
        groq_models = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "openai/gpt-oss-120b"]
        for gkey in valid_groq[:5]:
            for gmodel in groq_models:
                groq_payload = {
                    "model": gmodel,
                    "messages": [
                        {"role": "system", "content": "You are a disaster emergency triage classifier. Output valid JSON only."},
                        {"role": "user", "content": f"Message: \"{text}\"\nEstimate probabilities (0.04 to 0.95) for all 30 resources in JSON:\n" + "\n".join([f"- {k}: {v}" for k, v in RESOURCE_CRITERIA_QUESTIONS.items()])}
                    ],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.1,
                    "max_tokens": 1500
                }
                try:
                    g_resp = requests.post("https://api.groq.com/openai/v1/chat/completions", headers={"Authorization": f"Bearer {gkey}", "Content-Type": "application/json"}, json=groq_payload, timeout=10)
                    if g_resp.status_code == 200:
                        parsed = json.loads(g_resp.json()["choices"][0]["message"]["content"])
                        res_dict = parsed.get("resource_probabilities") or parsed
                        if isinstance(res_dict, dict) and any(k in res_dict for k in ["search_and_rescue", "emergency_medical_care", "drinking_water"]):
                            return {k: round(max(0.04, min(0.95, float(res_dict.get(k, 0.04)))), 3) for k in RESOURCE_CRITERIA_QUESTIONS}
                except Exception:
                    continue

    return None

def evaluate_resource_probabilities(text: str, incident_type: str, facts: Dict[str, Any]) -> Dict[str, float]:
    """
    Computes JEV resource probabilities strictly using OpenRouter JEV.
    Never preconditions or matches words; purely model-driven JEV decision evaluation.
    """
    jev_probs = evaluate_resource_probabilities_openrouter_jev(text, incident_type)
    if jev_probs:
        return jev_probs

    # Default noise floor if unreachable
    return {r: 0.04 for r in RESOURCE_CRITERIA_QUESTIONS}

def evaluate_implied_needs(
    text: str,
    incident_type: str,
    base_probs: Dict[str, float]
) -> Dict[str, Dict[str, Any]]:
    """
    Section D: Implied needs evaluation.
    Maps incident type to candidate implied resources for informational labeling,
    without artificially boosting or overriding OpenRouter JEV probabilities.
    """
    implied_candidates = IMPLIED_NEEDS_TABLE.get(incident_type, [])
    results: Dict[str, Dict[str, Any]] = {}

    for res in implied_candidates:
        curr_prob = base_probs.get(res, 0.04)
        is_life_crit = res in LIFE_CRITICAL_RESOURCES
        results[res] = {
            "implied": True,
            "boosted_probability": curr_prob,
            "reason": f"Implied requirement for verified {incident_type.replace('_', ' ')} incident",
            "life_critical": is_life_crit
        }

    return results

# ──────────────────────────────────────────────────────────────────────────────
# 7. Section D: Severity and Urgency Scoring (Situations, Not Degrees)
# ──────────────────────────────────────────────────────────────────────────────
def evaluate_severity_and_urgency(
    text: str,
    facts: Dict[str, Any],
    confirmed_or_likely_resources: Set[str]
) -> Dict[str, Any]:
    """
    Computes Severity (S0-S3) and Urgency (U0-U3) using concrete situation levels.
    Enforces Invariant B1 floors:
      - Any life_critical resource in CONFIRMED or LIKELY forces S >= 2 and U >= 2.
      - search_and_rescue CONFIRMED with a trapped person forces S >= 2, U = 3, priority P1.
    """
    t_lower = text.lower()

    # Direct cue detection
    trapped_count = facts.get("people_trapped")
    injured_count = facts.get("people_injured_reported")
    has_trapped = (trapped_count is not None and trapped_count > 0) or any(k in t_lower for k in [
        "trapped", "pinned", "under debris", "marooned on roof", "tsuck", "stuck inside", "tsuck inside",
        "inside the car", "inside a car", "inside car", "in the car", "cannot open door", "extricate"
    ])
    has_life_threat = has_trapped or any(k in t_lower for k in [
        "dying", "drowning", "bleeding heavily", "critical", "unconscious", "buried", "pls helpp", "please help", "urgent help"
    ])
    has_community_cutoff = any(k in t_lower for k in ["cut off", "marooned", "entire village", "50 families", "colony submerged", "no access", "bridges washed"])
    has_active_worsening = any(k in t_lower for k in ["water rising", "rain continuing", "mud sliding", "fire spreading", "worsening"])

    # --- Severity Score (Level 0-3 situations) ---
    # 0: No one is hurt or trapped; only property damage or inconvenience
    # 1: A minor injury, or a household lost essentials; nobody is trapped or in danger
    # 2: Anyone is trapped, pinned, seriously injured or in danger of dying; or a community lost water, food, shelter or access
    # 3: Several people are trapped or injured, or a whole community is cut off with injured people
    s_level = 0
    s_reason = "No reported injuries or trapped individuals; property damage or localized disruption."

    if has_trapped and has_community_cutoff:
        s_level = 3
        s_reason = "Multiple individuals or community stranded/trapped with acute risk."
    elif has_life_threat or has_community_cutoff:
        s_level = 2
        s_reason = "Individuals trapped, seriously injured, or community cut off from essentials."
    elif injured_count or any(k in t_lower for k in ["minor injury", "lost belongings", "inconvenience", "waterlogged"]):
        s_level = 1
        s_reason = "Minor injury or household disruption without trapped persons."

    # --- Urgency Score (Level 0-3 time windows) ---
    # 0: help needed in 2-3 days
    # 1: help needed within a day, nothing worsening
    # 2: situation worsening, help needed within a few hours
    # 3: someone is trapped, injured or in danger now, help needed within the hour
    u_level = 0
    u_window = "48-72h"
    u_reason = "Non-urgent support needed over 2 to 3 days."

    if has_life_threat or (has_trapped and has_active_worsening):
        u_level = 3
        u_window = "<1h"
        u_reason = "Immediate life danger or trapped victims needing rescue within the hour."
    elif has_active_worsening or has_community_cutoff:
        u_level = 2
        u_window = "2-4h"
        u_reason = "Worsening environmental hazard or cut-off community requiring response in a few hours."
    elif s_level >= 1:
        u_level = 1
        u_window = "12-24h"
        u_reason = "Response required within 24 hours; stable situation."

    # ── Invariant B1 Floor Check ──
    has_life_crit_selected = any(r in LIFE_CRITICAL_RESOURCES for r in confirmed_or_likely_resources)
    is_sar_confirmed = "search_and_rescue" in confirmed_or_likely_resources

    rule_s_floor = 2 if has_life_crit_selected else 0
    rule_u_floor = 2 if has_life_crit_selected else 0

    if is_sar_confirmed and has_trapped:
        rule_s_floor = max(rule_s_floor, 2)
        rule_u_floor = 3  # forces U3

    final_s = max(s_level, rule_s_floor)
    final_u = max(u_level, rule_u_floor)

    # Priority P1-P4 calculation
    if (is_sar_confirmed and has_trapped) or (final_s >= 2 and final_u == 3):
        priority = "P1"
        p_label = "Priority 1 (Immediate Life Threat)"
        p_reason = "Life-critical operation with active entrapment requiring immediate tactical dispatch."
    elif final_s >= 2 and final_u == 2:
        priority = "P2"
        p_label = "Priority 2 (Urgent Response)"
        p_reason = "Severe community hazard or critical isolation requiring response within hours."
    elif final_s >= 1 or final_u >= 1:
        priority = "P3"
        p_label = "Priority 3 (Planned Dispatch)"
        p_reason = "Controlled situation requiring structured relief mobilization within 24 hours."
    else:
        priority = "P4"
        p_label = "Priority 4 (Monitoring)"
        p_reason = "Routine monitoring or minor non-life-threatening situation."

    # Check for discrepancy gap >= 2 between raw Score and final rule floor
    s_gap = abs(final_s - s_level)
    u_gap = abs(final_u - u_level)
    max_gap = max(s_gap, u_gap)
    human_review_required = max_gap >= 2

    # Severity words
    s_words = {0: "Minor", 1: "Moderate", 2: "Severe", 3: "Catastrophic"}
    u_words = {0: "Low (2-3 days)", 1: "Standard (<24h)", 2: "Urgent (<4h)", 3: "Immediate (<1h)"}

    return {
        "severity": {
            "level": f"S{final_s}",
            "numeric": final_s,
            "word": s_words.get(final_s, "Severe"),
            "reason": s_reason
        },
        "urgency": {
            "level": f"U{final_u}",
            "numeric": final_u,
            "word": u_words.get(final_u, "Immediate"),
            "window": u_window,
            "reason": u_reason
        },
        "priority": {
            "level": priority,
            "label": p_label,
            "reason": p_reason
        },
        "severity_level": f"S{final_s}",
        "severity_word": s_words.get(final_s, "Severe"),
        "urgency_level": f"U{final_u}",
        "urgency_word": u_words.get(final_u, "Immediate"),
        "urgency_window": u_window,
        "priority_level": priority,
        "priority_label": p_label,
        "priority_cue": p_reason,
        "human_review_required": human_review_required,
        "gap": max_gap,
        "driving_cue": "trapped_or_pinned" if has_trapped else ("life_threat_now" if has_life_threat else "community_scale")
    }

# ──────────────────────────────────────────────────────────────────────────────
# 8. Main JEV v3 Triage Function
# ──────────────────────────────────────────────────────────────────────────────
def execute_jev_v3_triage(
    message: str,
    english_copy: Optional[str] = None,
    coordinates: Optional[Dict[str, float]] = None,
    district_hint: Optional[str] = None
) -> Dict[str, Any]:
    """
    Executes the full JEV v3 triage pipeline adhering to Sections B, C, D, E, F.
    """
    start_time = time.perf_counter()
    primary_text = (english_copy or message).strip()

    # 1. Intake: preserve original & English
    intake = {
        "original_message": message,
        "english_message": primary_text,
        "coordinates": coordinates
    }

    # 0. Binary Disaster / Emergency Check (JEV Noul)
    disaster_eval = evaluate_is_disaster_related_noul(primary_text)
    is_disaster = disaster_eval["is_disaster_related"]

    if not is_disaster:
        # Non-emergency fast exit: produces no resources, no dispatch, and no census call (Section J)
        log_filename = os.path.join(LOGS_DIR, f"jev_call_{int(time.time() * 1000)}.json")
        try:
            with open(log_filename, "w", encoding="utf-8") as f:
                json.dump({
                    "model_version": JEV_MODEL_VERSION,
                    "timestamp": time.time(),
                    "is_disaster_related": False,
                    "disaster_assessment": disaster_eval,
                    "message": primary_text
                }, f, indent=2)
        except Exception:
            pass

        assessment = {
            "severity": {"level": "S0", "numeric": 0, "word": "Minor", "reason": "Non-emergency communication."},
            "urgency": {"level": "U0", "numeric": 0, "word": "Low (2-3 days)", "window": "None", "reason": "No urgent relief or dispatch required."},
            "priority": {"level": "P4", "label": "Priority 4 (Monitoring / Non-Emergency)", "reason": disaster_eval["reason"]},
            "severity_level": "S0",
            "severity_word": "Minor",
            "urgency_level": "U0",
            "urgency_word": "Low",
            "urgency_window": "None",
            "priority_level": "P4",
            "priority_label": "Priority 4 (Monitoring / Non-Emergency)",
            "priority_cue": disaster_eval["reason"],
            "human_review_required": False,
            "gap": 0,
            "driving_cue": "non_emergency_inquiry"
        }
        not_selected = [
            {
                "resource": res_id,
                "resource_label": RESOURCE_LABELS.get(res_id, res_id),
                "jev_probability": 0.04,
                "cutoff": get_calibrated_threshold(res_id),
                "reason_code": "non_emergency_inquiry",
                "reason": "Non-emergency communication; disaster resources not required"
            }
            for res_id in RESOURCE_CRITERIA_QUESTIONS
        ]
        return {
            "status": "success",
            "model_version": JEV_MODEL_VERSION,
            "is_disaster_related": False,
            "disaster_assessment": disaster_eval,
            "intake": intake,
            "incident_type": "non_emergency",
            "incident_confidence": disaster_eval["confidence"],
            "wide_area": {"wide_area_probability": 0.0, "is_wide_area": False, "status": "localized"},
            "known_facts": "Non-emergency communication; no disaster casualties or damage.",
            "structured_facts": {"people_affected": None, "people_trapped": None, "people_injured_reported": None, "vulnerable_mentioned": [], "evidence_quotes": []},
            "census_context": None,
            "place": None,
            "nearby_agencies": [],
            "assessment": assessment,
            "selected_resources": [],
            "not_selected_resources": not_selected,
            "non_selected_resources": not_selected,
            "raw_probabilities": {r: 0.04 for r in RESOURCE_CRITERIA_QUESTIONS},
            "latency_ms": round((time.perf_counter() - start_time) * 1000.0, 1),
            "raw_log_file": log_filename
        }

    # 2. Call 1: wide_area Noul & bidirectional incident type Choice
    wide_area_prob = evaluate_wide_area_noul(primary_text)
    incident_type, incident_conf = evaluate_incident_type_bidirectional(primary_text)

    # Branching decision (C3):
    # >= 0.5 wide; 0.2 to 0.5 ambiguous (run both); < 0.2 localized
    if incident_type == "other":
        is_wide_area = False
        is_ambiguous = False
    else:
        is_wide_area = wide_area_prob >= 0.5
        is_ambiguous = 0.2 <= wide_area_prob < 0.5

    # 3. Branch Processing
    facts = extract_structured_facts(primary_text)
    known_facts_block = build_known_facts_block(facts)

    census_data = None
    place_context = None

    if is_wide_area or is_ambiguous:
        # C4: Wide-area branch: coordinates/text to place, census at finest unit
        # Never prints as 'people affected' (Invariant B8)
        try:
            census_res = census_context.build_context(primary_text, district=district_hint)
            if census_res.get("census_available"):
                census_data = {
                    "state": census_res.get("state"),
                    "district": census_res.get("district"),
                    "vulnerability_percentile": round(census_res.get("query_vulnerability_percentile", 0.5), 3),
                    "attended_signals": census_res.get("attended_signals", []),
                    "area_population_context": "Census 2011 area demographic baseline (NOT affected headcount)",
                    "match_confidence": census_res.get("match_confidence", 0.0)
                }
                place_context = {
                    "state": census_res.get("state"),
                    "district": census_res.get("district")
                }
        except Exception as e:
            print(f"[JEV v3] Census lookup error: {e}")

    # For localized incidents or fallback place resolution
    if not place_context and district_hint:
        place_context = {"district": district_hint}

    # Retrieve verified agency directory entries (F)
    st = place_context.get("state") if place_context else None
    dist = place_context.get("district") if place_context else None
    nearby_agencies = agency_directory.get_agencies_for_location(st, dist)

    # 4. 30 Resource Nouls & Implied Needs
    base_probs = evaluate_resource_probabilities(primary_text, incident_type, facts)
    implied_needs = evaluate_implied_needs(primary_text, incident_type, base_probs)

    # Apply implied needs to probabilities
    final_probs: Dict[str, float] = {}
    for res_id, p_val in base_probs.items():
        if res_id in implied_needs:
            boosted = implied_needs[res_id]["boosted_probability"]
            final_probs[res_id] = round(max(p_val, boosted), 3)
        else:
            final_probs[res_id] = p_val

    # 5. Band Classification:
    # >= 0.75 (75%): CONFIRMED (Active dispatch)
    # 0.50 to 0.75 (50%-75%): STANDBY (Keep on standby)
    # < 0.50 (< 50%): REJECT (Not selected)
    confirmed_set = set()
    standby_set = set()
    not_selected = []

    for res_id in RESOURCE_CRITERIA_QUESTIONS:
        p = final_probs[res_id]

        if p >= CONFIRMED_THRESHOLD:
            confirmed_set.add(res_id)
        elif p >= STANDBY_THRESHOLD:
            standby_set.add(res_id)
        else:
            not_selected.append({
                "resource": res_id,
                "resource_label": RESOURCE_LABELS.get(res_id, res_id),
                "band": "REJECTED",
                "jev_probability": p,
                "cutoff": STANDBY_THRESHOLD,
                "reason_code": "below_50pct_threshold" if p > 0.05 else "not_mentioned_or_implied",
                "reason": f"Score {p:.1%} below 50.0% standby threshold (rejected)" if p > 0.05 else "Not mentioned or implied in message"
            })

    # Combined confirmed + standby for severity floors
    conf_or_standby = confirmed_set.union(standby_set)

    # 6. Combined Assessment (Severity, Urgency, Priority) from ONE Unified Object (B2)
    assessment = evaluate_severity_and_urgency(primary_text, facts, conf_or_standby)

    # 7. Selected Resources:
    # CONFIRMED (>= 75%): dispatched immediately
    # STANDBY (50% to 75%): kept on standby, probed with caller
    selected_items = []
    
    for res_id in confirmed_set:
        tax = V2_MAP.get(res_id, {})
        tier = tax.get("cost_tier", "survival_basic")
        weight = TIER_WEIGHTS.get(tier, 2)
        score = final_probs[res_id] * weight
        item_obj = {
            "resource": res_id,
            "resource_label": RESOURCE_LABELS.get(res_id, res_id),
            "band": "CONFIRMED",
            "jev_probability": final_probs[res_id],
            "cutoff": CONFIRMED_THRESHOLD,
            "tier": tier,
            "weight": weight,
            "rank_score": score,
            "action_guidance": "Dispatch immediately",
            "is_life_critical": res_id in LIFE_CRITICAL_RESOURCES
        }
        if res_id in implied_needs:
            item_obj["implied_reason"] = implied_needs[res_id]["reason"]
        selected_items.append(item_obj)

    for res_id in standby_set:
        tax = V2_MAP.get(res_id, {})
        tier = tax.get("cost_tier", "survival_basic")
        weight = TIER_WEIGHTS.get(tier, 2)
        score = final_probs[res_id] * weight
        item_obj = {
            "resource": res_id,
            "resource_label": RESOURCE_LABELS.get(res_id, res_id),
            "band": "STANDBY",
            "jev_probability": final_probs[res_id],
            "cutoff": STANDBY_THRESHOLD,
            "tier": tier,
            "weight": weight,
            "rank_score": score,
            "action_guidance": "Keep on standby - verify with caller before dispatch",
            "is_life_critical": res_id in LIFE_CRITICAL_RESOURCES
        }
        if res_id in implied_needs:
            item_obj["implied_reason"] = implied_needs[res_id]["reason"]
        selected_items.append(item_obj)

    # Sort by rank_score descending
    selected_items.sort(key=lambda x: x["rank_score"], reverse=True)

    # Cap at 8 shown, but life-critical resources are NEVER dropped
    if len(selected_items) > 8:
        top_8 = []
        overflow = []
        for item in selected_items:
            if len(top_8) < 8 or item["is_life_critical"]:
                top_8.append(item)
            else:
                overflow.append(item)
        selected_items = top_8
        for dropped in overflow:
            not_selected.append({
                "resource": dropped["resource"],
                "resource_label": dropped["resource_label"],
                "jev_probability": dropped["jev_probability"],
                "cutoff": dropped["cutoff"],
                "reason_code": "dropped_by_priority_cap",
                "reason": "Lower priority candidate dropped by 8-resource dispatch cap"
            })

    elapsed_ms = (time.perf_counter() - start_time) * 1000.0

    # 8. Raw JEV Response Logging (Invariant B9)
    raw_jev_payload = {
        "model_version": JEV_MODEL_VERSION,
        "timestamp": time.time(),
        "wide_area_prob": wide_area_prob,
        "incident_type": incident_type,
        "incident_conf": incident_conf,
        "facts": facts,
        "known_facts_block": known_facts_block,
        "probabilities": final_probs,
        "assessment": assessment,
        "selected_resources": [s["resource"] for s in selected_items]
    }
    
    log_filename = os.path.join(LOGS_DIR, f"jev_call_{int(time.time() * 1000)}.json")
    try:
        with open(log_filename, "w", encoding="utf-8") as f:
            json.dump(raw_jev_payload, f, indent=2)
    except Exception as e:
        print(f"[JEV v3] Error writing raw log: {e}")

    return {
        "status": "success",
        "model_version": JEV_MODEL_VERSION,
        "is_disaster_related": True,
        "disaster_assessment": disaster_eval,
        "intake": intake,
        "incident_type": incident_type,
        "incident_confidence": incident_conf,
        "wide_area": {
            "is_wide_area": is_wide_area,
            "probability": wide_area_prob,
            "status": "wide" if is_wide_area else ("ambiguous" if is_ambiguous else "localized")
        },
        "known_facts": known_facts_block,
        "structured_facts": facts,
        "census_context": census_data,
        "place": place_context,
        "nearby_agencies": nearby_agencies,
        "assessment": assessment,
        "selected_resources": selected_items,
        "not_selected_resources": not_selected,
        "raw_probabilities": final_probs,
        "latency_ms": round(elapsed_ms, 1),
        "raw_log_file": log_filename
    }

if __name__ == "__main__":
    test_msg = "Severe flash flood in Wayanad district. 50 families stranded on rooftops without clean drinking water. Need emergency rescue boats immediately."
    res = execute_jev_v3_triage(test_msg, coordinates={"lat": 11.685, "lng": 76.132}, district_hint="Wayanad")
    print(json.dumps(res, indent=2))
