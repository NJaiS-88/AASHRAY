import os
import sys
import json
import argparse
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pipeline import DisasterRAGPipeline

def run_scenario(scenario_text: str, scenario_id: str = None):
    if not scenario_id:
        scenario_id = f"RUN-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    print("\n" + "=" * 70)
    print(f"PIPELINE A (LLM + LLM) - DISASTER RAG RUNNER")
    print("=" * 70)
    print(f"Scenario ID: {scenario_id}")
    print(f"Scenario:    \"{scenario_text}\"")
    print("-" * 70)

    pipeline = DisasterRAGPipeline(pipeline_name="llm_llm")
    
    print("\n[1/3] Running Stage 1 LLM Classifier (Groq / gpt-oss-120b)...")
    final_output = pipeline.run(scenario_id=scenario_id, scenario=scenario_text)

    print("\n[2/3] & [3/3] Retrieval & Stage 2 Generation Completed!")
    print("\n" + "=" * 70)
    print("FINAL STRICT JSON OUTPUT:")
    print("=" * 70)
    print(json.dumps(final_output, indent=2))
    print("=" * 70)
    print(f"Run saved to runs.jsonl")
    return final_output

def main():
    parser = argparse.ArgumentParser(description="Run Disaster RAG Pipeline A (LLM + LLM)")
    parser.add_argument("scenario", nargs="?", type=str, help="Emergency disaster scenario text to evaluate")
    parser.add_argument("--id", type=str, default=None, help="Optional scenario ID")
    args = parser.parse_args()

    if args.scenario:
        run_scenario(args.scenario, args.id)
    else:
        print("\n=== Disaster RAG Interactive Runner ===")
        print("Type or paste an emergency scenario (or press Enter for default test scenario):")
        try:
            user_input = input("\nScenario > ").strip()
        except (EOFError, KeyboardInterrupt):
            user_input = ""

        if not user_input:
            user_input = (
                "Severe earthquake in Port-au-Prince. Buildings collapsed on Rue Capois. "
                "Multiple people trapped under heavy concrete rubble. Hospital near capacity, "
                "urgent need for search teams, heavy equipment, and trauma surgeons."
            )
            print(f"Using default test scenario:\n\"{user_input}\"")

        run_scenario(user_input, args.id)

if __name__ == "__main__":
    main()
