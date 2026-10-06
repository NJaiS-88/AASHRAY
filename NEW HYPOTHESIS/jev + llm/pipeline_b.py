import os
import sys
import json
import time
from datetime import datetime
from typing import List, Dict, Any, Optional

LLM_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "llm + llm"))
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

for path in [LLM_DIR, ROOT_DIR, os.path.dirname(os.path.abspath(__file__))]:
    if path not in sys.path:
        sys.path.insert(0, path)

from retrieval import Retriever
from stage2_generator import generate_plan
from schema import FinalResponse
from stage1_jev import classify_jev_detailed, get_last_jev_meta

class DisasterRAGPipelineB:
    """
    Pipeline B: Jev + LLM
    Flow: classify_jev_detailed -> check stage1_status -> retrieval -> stage 2 -> JSON
    Reuses retrieval, stage 2 generator, and schema from Pipeline A.
    """
    def __init__(
        self,
        retriever: Optional[Retriever] = None,
        pipeline_name: str = "jev_llm",
        runs_file: Optional[str] = None
    ):
        self.pipeline_name = pipeline_name
        self.retriever = retriever or Retriever()
        self.runs_file = os.path.abspath(runs_file) if runs_file else os.path.join(os.path.dirname(__file__), "runs.jsonl")
        self.shared_runs_file = os.path.join(LLM_DIR, "runs.jsonl")
        self.last_run_record = None

    def run(self, scenario_id: str, scenario: str) -> Optional[Dict[str, Any]]:
        total_start = time.perf_counter()

        # -------------------------------------------------------------
        # STAGE 1: JEV CLASSIFICATION
        # -------------------------------------------------------------
        c_start = time.perf_counter()
        required_resources, stage1_meta = classify_jev_detailed(scenario)
        c_latency = (time.perf_counter() - c_start) * 1000.0

        stage1_status = stage1_meta.get("stage1_status", "error")
        stage1_error = stage1_meta.get("stage1_error")
        c_retries = stage1_meta.get("retries", 0)
        c_prompt_tokens = stage1_meta.get("prompt_tokens", 0)
        c_comp_tokens = stage1_meta.get("completion_tokens", 0)
        c_probabilities = stage1_meta.get("probabilities", {})

        # If Stage 1 failed: STOP the run immediately!
        if stage1_status != "ok" or required_resources is None:
            total_latency = (time.perf_counter() - total_start) * 1000.0
            run_record = {
                "timestamp": datetime.now().isoformat(),
                "pipeline": self.pipeline_name,
                "scenario_id": scenario_id,
                "stage1_status": "error",
                "stage1_error": stage1_error,
                "stage_1_resources": [],
                "stage_1_probabilities": c_probabilities,
                "retrieved_chunks": [],
                "final_json": None,
                "json_validity": False,
                "stage2_meta": None,
                "latency": {
                    "classification_ms": round(c_latency, 2),
                    "retrieval_ms": 0.0,
                    "generation_ms": 0.0,
                    "total_ms": round(total_latency, 2)
                },
                "retries": {
                    "classification": c_retries,
                    "generation": 0
                },
                "tokens": {
                    "classification": {
                        "prompt_tokens": c_prompt_tokens,
                        "completion_tokens": c_comp_tokens,
                        "total_tokens": c_prompt_tokens + c_comp_tokens
                    },
                    "generation": {
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "total_tokens": 0
                    },
                    "grand_total": c_prompt_tokens + c_comp_tokens
                }
            }
            for path in [self.runs_file, self.shared_runs_file]:
                try:
                    with open(path, "a", encoding="utf-8") as f:
                        f.write(json.dumps(run_record) + "\n")
                except Exception as log_err:
                    print(f"Warning: Failed to log run record to {path}: {log_err}")
            self.last_run_record = run_record
            print(f"[ERROR] Stage 1 JEV failed for {scenario_id}: {stage1_error}. Run stopped.")
            return None

        # -------------------------------------------------------------
        # STAGE 2: RETRIEVAL (SHARED MODULE & DISK CACHE)
        # -------------------------------------------------------------
        r_start = time.perf_counter()
        retrieved_map = self.retriever.retrieve_for_all_resources(scenario, required_resources)
        r_latency = (time.perf_counter() - r_start) * 1000.0

        flat_retrieved_chunks = []
        for r_name, chunks in retrieved_map.items():
            for c in chunks:
                flat_retrieved_chunks.append({
                    "resource": r_name,
                    "chunk_id": c.get("chunk_id"),
                    "source_file": c.get("source_file"),
                    "page": c.get("page"),
                    "chunk_text": c.get("chunk_text")
                })

        # -------------------------------------------------------------
        # STAGE 3: GENERATION (SHARED MODULE & MODEL)
        # -------------------------------------------------------------
        final_json, is_valid, gen_meta = generate_plan(
            scenario_id=scenario_id,
            scenario=scenario,
            required_resources=required_resources,
            retrieved_map=retrieved_map,
            pipeline_name=self.pipeline_name
        )
        g_latency = gen_meta["latency_ms"]
        g_retries = gen_meta["retries"]
        g_prompt_tokens = gen_meta["prompt_tokens"]
        g_comp_tokens = gen_meta["completion_tokens"]

        total_latency = (time.perf_counter() - total_start) * 1000.0

        # -------------------------------------------------------------
        # LOGGING TO runs.jsonl
        # -------------------------------------------------------------
        run_record = {
            "timestamp": datetime.now().isoformat(),
            "pipeline": self.pipeline_name,
            "scenario_id": scenario_id,
            "definition_version": stage1_meta.get("definitions_version", "definition_v2"),
            "stage1_status": "ok",
            "stage1_error": None,
            "stage_1_resources": required_resources,
            "stage_1_probabilities": c_probabilities,
            "retrieved_chunks": flat_retrieved_chunks,
            "final_json": final_json,
            "json_validity": is_valid,
            "stage2_meta": {
                "model_used": gen_meta.get("model_used", "openai/gpt-oss-120b"),
                "failover_triggered": gen_meta.get("failover_triggered", False),
                "compaction_triggered": gen_meta.get("compaction_triggered", False),
                "finish_reason": gen_meta.get("finish_reason", "stop"),
                "prompt_tokens": g_prompt_tokens,
                "completion_tokens": g_comp_tokens,
                "total_tokens": g_prompt_tokens + g_comp_tokens
            },
            "latency": {
                "classification_ms": round(c_latency, 2),
                "retrieval_ms": round(r_latency, 2),
                "generation_ms": round(g_latency, 2),
                "total_ms": round(total_latency, 2)
            },
            "retries": {
                "classification": c_retries,
                "generation": g_retries
            },
            "tokens": {
                "classification": {
                    "prompt_tokens": c_prompt_tokens,
                    "completion_tokens": c_comp_tokens,
                    "total_tokens": c_prompt_tokens + c_comp_tokens
                },
                "generation": {
                    "prompt_tokens": g_prompt_tokens,
                    "completion_tokens": g_comp_tokens,
                    "total_tokens": g_prompt_tokens + g_comp_tokens
                },
                "grand_total": (c_prompt_tokens + c_comp_tokens) + (g_prompt_tokens + g_comp_tokens)
            }
        }

        # Write to both local runs.jsonl and shared runs.jsonl
        for path in [self.runs_file, self.shared_runs_file]:
            try:
                with open(path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(run_record) + "\n")
            except Exception as log_err:
                print(f"Warning: Failed to log run record to {path}: {log_err}")

        self.last_run_record = run_record
        return final_json
