import os
import sys
import json
import argparse
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pipeline_b import DisasterRAGPipelineB

def run_scenario(scenario_text: str, scenario_id: str = None):
    if not scenario_id:
        scenario_id = f"JEV-RUN-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    print("\n" + "=" * 70)
    print("PIPELINE B (JEV + LLM) - DISASTER RAG RUNNER")
    print("=" * 70)
    print(f"Scenario ID: {scenario_id}")
    print(f"Scenario:    \"{scenario_text}\"")
    print("-" * 70)

    pipeline = DisasterRAGPipelineB(pipeline_name="jev_llm")

    print("\n[1/3] Running Stage 1 TypeSafe JEV Classifier (OpenRouter Decisions API)...")
    final_output = pipeline.run(scenario_id=scenario_id, scenario=scenario_text)

    print("\n[2/3] & [3/3] Retrieval & Stage 2 Generation Completed!")
    print("\n" + "=" * 70)
    print("FINAL STRICT JSON OUTPUT (PIPELINE B):")
    print("=" * 70)
    print(json.dumps(final_output, indent=2))
    print("=" * 70)
    print("Run saved to runs.jsonl")
    return final_output

def main():
    parser = argparse.ArgumentParser(description="Run Disaster RAG Pipeline B (JEV + LLM)")
    parser.add_argument("scenario", nargs="?", type=str, help="Emergency disaster scenario text to evaluate")
    parser.add_argument("--id", type=str, default=None, help="Optional scenario ID")
    args = parser.parse_args()

    if args.scenario:
        run_scenario(args.scenario, args.id)
    else:
        print("\n=== Disaster RAG Pipeline B (JEV + LLM) Interactive Runner ===")
        print("Type or paste an emergency scenario (or press Enter for default test scenario):")
        try:
            user_input = input("\nScenario > ").strip()
        except (EOFError, KeyboardInterrupt):
            user_input = ""

        if not user_input:
            user_input = "Please, we need tents and water. We are in Silo, Thank you!"
            print(f"Using default test scenario:\n\"{user_input}\"")

        run_scenario(user_input, args.id)

if __name__ == "__main__":
    main()
