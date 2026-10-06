# =====================================================================
# SHARED RESOURCE DEFINITIONS & PROMPTS ACROSS ALL ARMS
# =====================================================================

RESOURCE_COLUMNS = [
    'water', 'food', 'shelter', 'clothing', 'money',
    'medical_help', 'medical_products', 'search_and_rescue', 'tools'
]

# Single shared canonical description per resource used by both LLM prompt and JEV criteria
RESOURCE_DESCRIPTIONS = {
    "water": "clean drinking water, potable water tanks, hydration aid, water purification",
    "food": "meals, hunger relief, food supplies, rations, groceries, starving people",
    "shelter": "tents, tarpaulins, temporary housing, blankets, sleeping mats, roofing",
    "clothing": "clothes, garments, footwear, shoes, wearable protective gear",
    "money": "financial aid, cash donations, grants, monetary relief, emergency funds",
    "medical_help": "doctors, nurses, paramedics, triage, field hospitals, ambulances, treating wounded/sick",
    "medical_products": "medicines, pharmaceuticals, bandages, first aid supplies, antiseptics",
    "search_and_rescue": "search teams, rescue dogs, evacuation teams, rubble extraction, saving trapped people",
    "tools": "construction tools, shovels, reconstruction gear, heavy machinery, excavation tools, chainsaws"
}

# Single shared definition string used identically in LLM prompt and JEV context
RESOURCE_DESC_TEXT = "\n".join([
    f"- {res}: {desc}" for res, desc in RESOURCE_DESCRIPTIONS.items()
])

# ---------------------------------------------------------------------
# DEFINITION VERSIONS
# ---------------------------------------------------------------------

# OLD DEFINITION: definition_v1 (Strict literal request only, no inference)
DEFINITION_V1_TEXT = (
    "Evaluate each resource independently based strictly on what is explicitly requested or stated in the text. "
    "Do not assume or infer unstated needs."
)

# NEW DEFINITION: definition_v2 (Contextual inference of implied operational needs; excludes offers/deliveries)
DEFINITION_V2_TEXT = (
    "A resource is REQUIRED if the message asks for it, reports a shortage of it, "
    "OR the situation described clearly implies responders would need it, even if the message does not ask for it. "
    "Infer from context and select the most useful resources from the catalogue "
    "(for example: a person trapped -> search_and_rescue; injuries -> medical_help). "
    "Do not select a resource that is only offered, already delivered, or only loosely related. "
    "If no catalogue resource is plausibly useful, return none."
)

# Active definition version
ACTIVE_DEFINITION_VERSION = "definition_v2"
RESOURCE_DEFINITIONS_VERSION = ACTIVE_DEFINITION_VERSION
SHARED_REQUIRED_DEFINITION = DEFINITION_V2_TEXT

# Shared criteria questions for JEV (uses identical wording from SHARED_REQUIRED_DEFINITION)
RESOURCE_CRITERIA_QUESTIONS = {
    res: f"Is {res} ({desc}) REQUIRED? ({SHARED_REQUIRED_DEFINITION})"
    for res, desc in RESOURCE_DESCRIPTIONS.items()
}

# Unified LLM Stage 1 System Prompt (uses identical wording from SHARED_REQUIRED_DEFINITION)
STAGE1_SYSTEM_PROMPT = (
    "You are an expert emergency disaster response dispatcher.\n"
    "Carefully analyze the emergency message and determine which of the following 9 resources are REQUIRED:\n\n"
    f"{RESOURCE_DESC_TEXT}\n\n"
    "DEFINITION OF REQUIRED:\n"
    f"{SHARED_REQUIRED_DEFINITION}\n\n"
    "EVALUATION RULES:\n"
    "1. Follow the definition of REQUIRED strictly based on the text.\n"
    "2. Return ONLY a valid JSON object mapping each of the 9 resources to "
    "{'required': 0 or 1, 'probability': float between 0.0 and 1.0 representing the probability that this resource is required}."
)

GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_GROQ_MODEL = "openai/gpt-oss-120b"
OPENROUTER_DECISIONS_URL = "https://openrouter.ai/api/alpha/decisions"
DEFAULT_JEV_MODEL = "typesafe/jev-1.13"
