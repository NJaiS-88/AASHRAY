import os
import sys
import json
import hashlib

# Paths
LLM_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "llm + llm"))
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
JEV_DIR = os.path.dirname(os.path.abspath(__file__))

for p in [LLM_DIR, ROOT_DIR, JEV_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

# Imports from shared modules
from stage2_generator import STAGE2_SYSTEM_PROMPT
from schema import FinalResponse
from pipeline import DisasterRAGPipeline
from pipeline_b import DisasterRAGPipelineB

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

def verify_shared_integrity():
    print("=" * 70)
    print("STAGE 2 PROMPT & SCHEMA INTEGRITY VERIFICATION")
    print("=" * 70)

    # 1. Verify Stage 2 prompt hash
    p_hash = hashlib.sha256(STAGE2_SYSTEM_PROMPT.strip().encode("utf-8")).hexdigest()
    print(f"Stage-2 Prompt SHA256: {p_hash}")

    # 2. Verify Schema JSON schema hash
    s_schema = json.dumps(FinalResponse.model_json_schema(), sort_keys=True)
    s_hash = hashlib.sha256(s_schema.encode("utf-8")).hexdigest()
    print(f"Pydantic Schema SHA256: {s_hash}")

    # Verify both pipelines import the exact same objects in memory
    from stage2_generator import generate_plan as gen_a
    from pipeline_b import generate_plan as gen_b
    assert gen_a is gen_b, "CRITICAL ERROR: Stage 2 generator function is not identical in memory!"

    from schema import FinalResponse as resp_a
    from pipeline_b import FinalResponse as resp_b
    assert resp_a is resp_b, "CRITICAL ERROR: Pydantic schema is not identical in memory!"

    print("Integrity Check Passed: Both pipelines share 100% identical Stage-2 and Schema modules.")
    print("=" * 70)

def main():
    verify_shared_integrity()

    pipe_a = DisasterRAGPipeline(pipeline_name="llm_llm")
    pipe_b = DisasterRAGPipelineB(pipeline_name="jev_llm")

    comparisons = []

    for item in SCENARIOS:
        scen_id = item["id"]
        scen_text = item["scenario"]

        print(f"\n{'#' * 70}")
        print(f"EVALUATING SCENARIO: {scen_id}")
        print(f"Transcript: \"{scen_text}\"")
        print(f"{'#' * 70}")

        # Run Pipeline A (LLM + LLM)
        print("\n>>> Executing Pipeline A (LLM + LLM)...")
        out_a = pipe_a.run(scenario_id=scen_id, scenario=scen_text)

        # Run Pipeline B (JEV + LLM)
        print(">>> Executing Pipeline B (JEV + LLM)...")
        out_b = pipe_b.run(scenario_id=scen_id, scenario=scen_text)

        res_a = [r["resource"] for r in out_a.get("resources", [])]
        res_b = [r["resource"] for r in out_b.get("resources", [])]

        diff_added = list(set(res_b) - set(res_a))
        diff_removed = list(set(res_a) - set(res_b))

        print(f"\n--- RESOURCE CLASSIFICATION COMPARISON [{scen_id}] ---")
        print(f"Pipeline A (Groq LLM): {sorted(res_a)}")
        print(f"Pipeline B (TypeSafe JEV): {sorted(res_b)}")
        if diff_added or diff_removed:
            print(f"Differences detected:")
            if diff_added:
                print(f"  + Added in Pipeline B (JEV): {diff_added}")
            if diff_removed:
                print(f"  - Omitted in Pipeline B (JEV): {diff_removed}")
        else:
            print("Resource classification is IDENTICAL between A and B.")

        print(f"\n--- FINAL JSON OUTPUT: Pipeline A (llm_llm) ---")
        print(json.dumps(out_a, indent=2))

        print(f"\n--- FINAL JSON OUTPUT: Pipeline B (jev_llm) ---")
        print(json.dumps(out_b, indent=2))

        comparisons.append({
            "scenario_id": scen_id,
            "pipeline_a_resources": sorted(res_a),
            "pipeline_b_resources": sorted(res_b),
            "diff_added_in_b": diff_added,
            "diff_removed_in_b": diff_removed,
            "output_a": out_a,
            "output_b": out_b
        })

    print("\n" + "=" * 70)
    print("ALL 3 SCENARIOS COMPARISON COMPLETE")
    print("=" * 70)

if __name__ == "__main__":
    main()
