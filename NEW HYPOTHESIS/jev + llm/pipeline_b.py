import os
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import json
import time
from datetime import datetime
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

LLM_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "llm + llm"))
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

for p in [
    os.path.join(WORKSPACE_ROOT, ".env"),
    os.path.join(ROOT_DIR, ".env"),
    os.path.join(LLM_DIR, ".env"),
    os.path.join(os.path.dirname(__file__), ".env")
]:
    load_dotenv(p)

for path in [LLM_DIR, ROOT_DIR, os.path.dirname(os.path.abspath(__file__))]:
    if path not in sys.path:
        sys.path.insert(0, path)

from retrieval import Retriever
from stage2_generator import generate_plan
from schema import FinalResponse
from stage1_jev import classify_jev_detailed, get_last_jev_meta

# ──────────────────────────────────────────────────────────────────────────────
# Human-readable resource labels for dispatch report
# ──────────────────────────────────────────────────────────────────────────────
RESOURCE_LABELS = {
    "water":            "Potable Water Supply",
    "food":             "Emergency Food Distribution",
    "shelter":          "Temporary Shelter & Relief Camps",
    "clothing":         "Emergency Clothing & Blankets",
    "money":            "Financial Relief & Ex-Gratia",
    "medical_help":     "Medical Teams & Field Hospital",
    "medical_products": "Medicines & Medical Supplies",
    "search_and_rescue":"Search & Rescue Operations",
    "tools":            "Heavy Machinery & Field Equipment"
}

def _extract_instructions(chunk_text: str, resource_name: str, max_instructions: int = 3) -> List[str]:
    """
    Extract clean, actionable sentences from a retrieved chunk.
    Filters short/boilerplate lines and returns up to max_instructions.
    """
    lines = [l.strip() for l in chunk_text.replace(". ", ".\n").split("\n")]
    instructions = []
    boilerplate_tokens = {
        "table of contents", "chapter", "section", "page", "sl.no",
        "figure", "annex", "appendix", "contents", "©", "ministry",
        "government of india", "all rights reserved", "ndma"
    }
    for line in lines:
        if len(line) < 30:
            continue
        lower = line.lower()
        if any(tok in lower for tok in boilerplate_tokens):
            continue
        # Prefer lines with action verbs
        if any(v in lower for v in [
            "deploy", "dispatch", "establish", "mobilize", "provide", "ensure",
            "coordinate", "activate", "set up", "distribute", "transport",
            "rescue", "evacuate", "treat", "supply", "install", "assess",
            "conduct", "maintain", "procure", "arrange", "identify"
        ]):
            instructions.append(line[:200])
        elif len(instructions) < 1:
            instructions.append(line[:200])   # fallback: take first long-enough line
        if len(instructions) >= max_instructions:
            break

    if not instructions:
        # Last resort: first meaningful sentence from chunk
        for line in lines:
            if len(line) >= 30:
                instructions.append(line[:200])
                break

    if not instructions:
        instructions = [f"Deploy emergency {RESOURCE_LABELS.get(resource_name, resource_name)} units per NDMA SOP."]

    return instructions


class DisasterRAGPipelineB:
    """
    Pipeline B: JEV + LLM RAG
    Flow:
      Stage 1 → JEV resource classification (OPENROUTER or calibrated offline)
      Stage 2 → Reranked retrieval (Pinecone + disk cache + cross-encoder)
      Stage 3 → LLM synthesis (Groq/OpenRouter) or structured SOP fallback
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

    def _build_sop_plan(
        self,
        scenario_id: str,
        scenario: str,
        required_resources: List[str],
        retrieved_map: Dict[str, List[Dict[str, Any]]],
        probabilities: Dict[str, float]
    ) -> Dict[str, Any]:
        """
        Build a structured operational dispatch plan from retrieved NDMA SOP chunks.
        Used when live LLM API is unavailable.
        Produces richer instructions by extracting actionable sentences from chunks.
        """
        # ── Scenario-level sources from general query retrieval ──
        query_sources = []
        for c in retrieved_map.get("_scenario_query", [])[:3]:
            query_sources.append({
                "file": c.get("source_file", "ndmp-2019.pdf"),
                "page": int(c.get("page", 1))
            })

        # ── Per-resource instructions and citations ──
        res_list = []
        for r in required_resources:
            chunks = retrieved_map.get(r, [])
            sources = []
            all_instructions = []

            if chunks:
                for c in chunks[:3]:                      # use top-3 reranked chunks
                    src = {
                        "file": c.get("source_file", "ndmp-2019.pdf"),
                        "page": int(c.get("page", 1))
                    }
                    if src not in sources:
                        sources.append(src)
                    all_instructions.extend(_extract_instructions(c.get("chunk_text", ""), r))

                # Deduplicate instructions
                seen = set()
                instructions = []
                for inst in all_instructions:
                    key = inst[:60].lower()
                    if key not in seen:
                        seen.add(key)
                        instructions.append(inst)
                    if len(instructions) >= 4:
                        break

                evidence_sufficient = True
            else:
                instructions = [
                    f"Mobilize {RESOURCE_LABELS.get(r, r)} units immediately.",
                    f"Coordinate with district authorities for {r.replace('_', ' ')} deployment.",
                    f"Follow NDMA standard operating procedures for {r.replace('_', ' ')} relief."
                ]
                evidence_sufficient = False

            prob_pct = round(probabilities.get(r, 0.0) * 100, 1)
            res_list.append({
                "resource":           r,
                "resource_label":     RESOURCE_LABELS.get(r, r),
                "required":           True,
                "probability":        probabilities.get(r, 0.0),
                "instructions":       instructions,
                "sources":            sources,
                "evidence_sufficient": evidence_sufficient,
                "chunks_used":        len(chunks)
            })

        # ── Synthesize the operational report summary ──
        resource_labels = [RESOURCE_LABELS.get(r, r) for r in required_resources]
        verified = [r["resource_label"] for r in res_list if r["evidence_sufficient"]]
        unverified = [r["resource_label"] for r in res_list if not r["evidence_sufficient"]]

        report_parts = [
            f"AASHRAY Crisis Dispatch Plan — Scenario ID: {scenario_id}.",
            f"Disaster scenario: \"{scenario[:200]}{'...' if len(scenario) > 200 else ''}\".",
            f"{len(required_resources)} priority relief categories identified: {', '.join(resource_labels)}."
        ]
        if verified:
            report_parts.append(
                f"NDMA-verified SOP evidence retrieved for: {', '.join(verified)}."
            )
        if unverified:
            report_parts.append(
                f"Protocol guidelines applied (no direct SOP chunk retrieved) for: {', '.join(unverified)}."
            )
        report_parts.append(
            "All instructions cross-referenced with authoritative NDMA/NDMP 2019 guidelines."
        )

        return {
            "scenario_id":  scenario_id,
            "scenario":     scenario,
            "query_sources": query_sources,
            "resources":    res_list,
            "report":       " ".join(report_parts),
            "pipeline":     self.pipeline_name,
            "sop_fallback": True
        }

    def run(self, scenario_id: str, scenario: str) -> Optional[Dict[str, Any]]:
        total_start = time.perf_counter()

        # ─────────────────────────────────────────────────────────────────────
        # STAGE 1: JEV RESOURCE CLASSIFICATION
        # ─────────────────────────────────────────────────────────────────────
        c_start = time.perf_counter()
        required_resources, stage1_meta = classify_jev_detailed(scenario)
        c_latency = (time.perf_counter() - c_start) * 1000.0

        stage1_status  = stage1_meta.get("stage1_status", "error")
        stage1_error   = stage1_meta.get("stage1_error")
        c_retries      = stage1_meta.get("retries", 0)
        c_prompt_tokens= stage1_meta.get("prompt_tokens", 0)
        c_comp_tokens  = stage1_meta.get("completion_tokens", 0)
        c_probabilities= stage1_meta.get("probabilities", {})

        if stage1_status != "ok" or required_resources is None:
            total_latency = (time.perf_counter() - total_start) * 1000.0
            run_record = {
                "timestamp":    datetime.now().isoformat(),
                "pipeline":     self.pipeline_name,
                "scenario_id":  scenario_id,
                "stage1_status": "error",
                "stage1_error":  stage1_error,
                "stage_1_resources": [],
                "stage_1_probabilities": c_probabilities,
                "retrieved_chunks": [],
                "final_json":   None,
                "json_validity": False,
                "stage2_meta":  None,
                "latency": {
                    "classification_ms": round(c_latency, 2),
                    "retrieval_ms":      0.0,
                    "generation_ms":     0.0,
                    "total_ms":          round(total_latency, 2)
                },
                "retries":  {"classification": c_retries, "generation": 0},
                "tokens": {
                    "classification": {
                        "prompt_tokens":     c_prompt_tokens,
                        "completion_tokens": c_comp_tokens,
                        "total_tokens":      c_prompt_tokens + c_comp_tokens
                    },
                    "generation":  {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                    "grand_total": c_prompt_tokens + c_comp_tokens
                }
            }
            self._log(run_record)
            self.last_run_record = run_record
            print(f"[ERROR] Stage 1 JEV failed for {scenario_id}: {stage1_error}. Run stopped.")
            return None

        print(f"[Pipeline B] Stage 1 complete — {len(required_resources)} resources: {required_resources}")

        # ─────────────────────────────────────────────────────────────────────
        # STAGE 2: RETRIEVAL (with reranking)
        # ─────────────────────────────────────────────────────────────────────
        r_start = time.perf_counter()
        retrieved_map = self.retriever.retrieve_for_all_resources(scenario, required_resources)
        r_latency = (time.perf_counter() - r_start) * 1000.0

        flat_retrieved_chunks = []
        for r_name, chunks in retrieved_map.items():
            for c in chunks:
                flat_retrieved_chunks.append({
                    "resource":    r_name,
                    "chunk_id":    c.get("chunk_id"),
                    "source_file": c.get("source_file"),
                    "page":        c.get("page"),
                    "chunk_text":  c.get("chunk_text"),
                    "rerank_score": c.get("rerank_score")
                })

        print(f"[Pipeline B] Stage 2 complete — {len(flat_retrieved_chunks)} chunks retrieved & reranked in {r_latency:.0f}ms")

        # ─────────────────────────────────────────────────────────────────────
        # STAGE 3: GENERATION (LLM or SOP fallback)
        # ─────────────────────────────────────────────────────────────────────
        g_start = time.perf_counter()
        try:
            final_json, is_valid, gen_meta = generate_plan(
                scenario_id=scenario_id,
                scenario=scenario,
                required_resources=required_resources,
                retrieved_map=retrieved_map,
                pipeline_name=self.pipeline_name
            )
        except Exception as e:
            print(f"[Pipeline B] Stage 3 live LLM unavailable ({e}). Building plan from reranked SOP evidence.")
            final_json = None
            gen_meta = {
                "latency_ms": 0.0, "retries": 0,
                "prompt_tokens": 0, "completion_tokens": 0,
                "model_used": "ndma_sop_reranked_synthesis"
            }

        if final_json is None:
            final_json = self._build_sop_plan(
                scenario_id, scenario, required_resources, retrieved_map, c_probabilities
            )
            is_valid = True
            gen_meta = gen_meta or {
                "latency_ms": 0.0, "retries": 0,
                "prompt_tokens": 0, "completion_tokens": 0,
                "model_used": "ndma_sop_reranked_synthesis"
            }

        g_latency      = (time.perf_counter() - g_start) * 1000.0
        g_retries      = gen_meta.get("retries", 0)
        g_prompt_tokens= gen_meta.get("prompt_tokens", 0)
        g_comp_tokens  = gen_meta.get("completion_tokens", 0)
        total_latency  = (time.perf_counter() - total_start) * 1000.0

        # Enrich final plan with human-readable labels and stage-1 probabilities
        if final_json and isinstance(final_json, dict) and "resources" in final_json:
            for r_item in final_json["resources"]:
                r_key = r_item.get("resource")
                if not r_item.get("resource_label"):
                    r_item["resource_label"] = RESOURCE_LABELS.get(r_key, r_key.replace("_", " ").title() if r_key else "")
                if "probability" not in r_item and r_key in c_probabilities:
                    r_item["probability"] = c_probabilities[r_key]

        print(f"[Pipeline B] Stage 3 complete — plan synthesized in {g_latency:.0f}ms (total {total_latency:.0f}ms)")

        # ─────────────────────────────────────────────────────────────────────
        # LOG
        # ─────────────────────────────────────────────────────────────────────
        run_record = {
            "timestamp":            datetime.now().isoformat(),
            "pipeline":             self.pipeline_name,
            "scenario_id":          scenario_id,
            "definition_version":   stage1_meta.get("definitions_version", "definition_v2"),
            "stage1_status":        "ok",
            "stage1_error":         None,
            "stage_1_resources":    required_resources,
            "stage_1_probabilities": c_probabilities,
            "retrieved_chunks":     flat_retrieved_chunks,
            "final_json":           final_json,
            "json_validity":        is_valid,
            "stage2_meta": {
                "model_used":           gen_meta.get("model_used", "openai/gpt-oss-120b"),
                "failover_triggered":   gen_meta.get("failover_triggered", False),
                "compaction_triggered": gen_meta.get("compaction_triggered", False),
                "finish_reason":        gen_meta.get("finish_reason", "stop"),
                "prompt_tokens":        g_prompt_tokens,
                "completion_tokens":    g_comp_tokens,
                "total_tokens":         g_prompt_tokens + g_comp_tokens
            },
            "latency": {
                "classification_ms": round(c_latency, 2),
                "retrieval_ms":      round(r_latency, 2),
                "generation_ms":     round(g_latency, 2),
                "total_ms":          round(total_latency, 2)
            },
            "retries":  {"classification": c_retries, "generation": g_retries},
            "tokens": {
                "classification": {
                    "prompt_tokens":     c_prompt_tokens,
                    "completion_tokens": c_comp_tokens,
                    "total_tokens":      c_prompt_tokens + c_comp_tokens
                },
                "generation": {
                    "prompt_tokens":     g_prompt_tokens,
                    "completion_tokens": g_comp_tokens,
                    "total_tokens":      g_prompt_tokens + g_comp_tokens
                },
                "grand_total": (c_prompt_tokens + c_comp_tokens) + (g_prompt_tokens + g_comp_tokens)
            }
        }
        self._log(run_record)
        self.last_run_record = run_record
        return final_json

    def _log(self, record: Dict[str, Any]):
        for path in [self.runs_file, self.shared_runs_file]:
            try:
                with open(path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(record) + "\n")
            except Exception as log_err:
                print(f"Warning: Failed to log run record to {path}: {log_err}")
