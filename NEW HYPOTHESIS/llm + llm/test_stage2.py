import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stage2_generator import generate_plan

scenario_id = "test_scen_001"
scenario = "Flash floods in sector 4. 20 families stranded without clean drinking water and several individuals injured needing immediate medical attention and bandages."
required_resources = ["water", "medical_help", "medical_products"]

sample_retrieved_map = {
    "water": [
        {
            "chunk_id": "disaster_manual__p4__c0",
            "source_file": "disaster_manual.pdf",
            "page": 4,
            "chunk_text": "Emergency Drinking Water Standard Operating Procedure: Immediately deploy 20L water purification kits and potable water bladders. Ensure a minimum of 3 liters of drinking water per person per day."
        }
    ],
    "medical_help": [
        {
            "chunk_id": "medical_triage_guide__p12__c1",
            "source_file": "medical_triage_guide.pdf",
            "page": 12,
            "chunk_text": "Mass Casualty Incident Triage Protocol: Dispatch rapid mobile medical units (MMUs) equipped with triage tags and certified trauma nurses. Stabilize high-priority wounded victims before transport."
        }
    ],
    "medical_products": [
        # Intentionally empty / insufficient to test rule: "insufficient source material"
    ]
}

print("Testing Stage 2 Generator on Groq...")
plan, is_valid, metrics = generate_plan(
    scenario_id=scenario_id,
    scenario=scenario,
    required_resources=required_resources,
    retrieved_map=sample_retrieved_map,
    pipeline_name="llm_llm"
)

print("\nValidation Succeeded:", is_valid)
print("Generation Metrics:", metrics)
print("\nGenerated Plan JSON:")
print(json.dumps(plan, indent=2))
