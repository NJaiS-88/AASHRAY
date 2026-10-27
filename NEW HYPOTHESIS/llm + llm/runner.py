import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pipeline import DisasterRAGPipeline
from verify_exact_prompt import verify as verify_prompts

SCENARIOS = [
    {
        "id": "SCEN-001",
        "scenario": "UN reports Leogane 80-90 destroyed. Only Hospital St. Croix functioning. Needs supplies desperately."
    },
    {
        "id": "SCEN-002",
        "scenario": "Please, we need tents and water. We are in Silo, Thank you!"
    },
    {
        "id": "SCEN-003",
        "scenario": "A Comitee in Delmas 19, Rue ( street ) Janvier, Impasse Charite 2. We have about 500 people in a temporary shelter and we are in dire need of Water, Food, Medications, Tents and Clothes. Please stop by and see us."
    }
]

def main():
    print("=" * 70)
    print("STEP 4: RUNNING 3 SAMPLE SCENARIOS END-TO-END (PIPELINE A: LLM + LLM)")
    print("=" * 70)

    # 1. Byte-identical verification check
    print("\n--- Verifying Prompt & Definition Hashes ---")
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from verify_exact_prompt import verify
    is_identical = verify()
    if not is_identical:
        print("ERROR: Byte verification failed! Halting.")
        return

    # 2. Run Pipeline
    pipeline = DisasterRAGPipeline(pipeline_name="llm_llm")
    results = []

    for item in SCENARIOS:
        scen_id = item["id"]
        scen_text = item["scenario"]
        print(f"\n{'='*70}")
        print(f"RUNNING SCENARIO: {scen_id}")
        print(f"Text: \"{scen_text}\"")
        print(f"{'='*70}")

        final_output = pipeline.run(scenario_id=scen_id, scenario=scen_text)
        results.append(final_output)

        print("\nFinal Output JSON:")
        print(json.dumps(final_output, indent=2))

    print("\n" + "=" * 70)
    print("ALL 3 SCENARIOS COMPLETED & LOGGED TO runs.jsonl")
    print("=" * 70)

if __name__ == "__main__":
    main()
