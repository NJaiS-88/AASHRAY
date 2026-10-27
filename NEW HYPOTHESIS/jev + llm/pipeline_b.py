"""
pipeline_b.py -- TypeSafe JEV v3 + Advanced RAG Disaster Pipeline (Pipeline B)
Implements Sections B through J of the JEV v3 Robustness Plan (Oct 10, 2026).
"""

import os
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import json
import time
import re
from datetime import datetime
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

_DIR = os.path.dirname(os.path.abspath(__file__))
LLM_DIR = os.path.abspath(os.path.join(_DIR, "..", "llm + llm"))
ROOT_DIR = os.path.abspath(os.path.join(_DIR, ".."))
WORKSPACE_ROOT = os.path.abspath(os.path.join(_DIR, "..", ".."))

for p in [
    os.path.join(WORKSPACE_ROOT, ".env"),
    os.path.join(ROOT_DIR, ".env"),
    os.path.join(LLM_DIR, ".env"),
    os.path.join(_DIR, ".env")
]:
    load_dotenv(p)

for path in [LLM_DIR, ROOT_DIR, _DIR, WORKSPACE_ROOT]:
    if path not in sys.path:
        sys.path.insert(0, path)

from retrieval import Retriever
from jev_v3_triage import execute_jev_v3_triage, JEV_MODEL_VERSION, RESOURCE_LABELS
from relevance_gate import run_relevance_gate, get_readable_doc_title
from stage2_v3_generator import generate_stage2_v3_plan, generate_non_disaster_plan
from pre_rag_gate import classify_pre_rag, re_evaluate_pre_rag
import agency_directory

class DisasterRAGPipelineB:
    def __init__(self, config: Optional[Dict[str, Any]] = None, pipeline_name: str = "jev_v3_rag"):
        self.config = config or {}
        self.pipeline_name = pipeline_name
        self.retriever = Retriever(self.config)
        self.runs_file = os.path.join(_DIR, "runs_v3.jsonl")
        self.shared_runs_file = os.path.join(ROOT_DIR, "runs_v3.jsonl")
        self.last_run_record = None

    def run(
        self,
        scenario_id: str,
        scenario: str,
        coordinates: Optional[Dict[str, float]] = None,
        district_hint: Optional[str] = None,
        clarification_answer: Optional[str] = None,
        bypass_pre_rag: bool = False
    ) -> Optional[Dict[str, Any]]:
        total_start = time.perf_counter()

        # ─────────────────────────────────────────────────────────────────────
        # STAGE 0: PRE-RAG INTAKE GATING & COMPLETENESS CHECK
        # ─────────────────────────────────────────────────────────────────────
        intake_eval = None
        effective_scenario = scenario
        pre_rag_latency = 0.0

        if not bypass_pre_rag:
            pre_start = time.perf_counter()
            intake_eval = classify_pre_rag(
                query=scenario,
                follow_up_answer=clarification_answer
            )
            pre_rag_latency = (time.perf_counter() - pre_start) * 1000.0

            can_proceed = intake_eval.get("can_proceed_to_rag", True)
            severity = intake_eval.get("severity", "Uncertain")
            action = intake_eval.get("action", "ask_clarifying_questions")
            missing_info = intake_eval.get("missing_info", [])
            clarifying_qs = intake_eval.get("clarifying_questions", [])

            if not can_proceed:
                total_latency = (time.perf_counter() - total_start) * 1000.0
                if severity == "Uncertain":
                    person_msg = (
                        "We need a little more information before emergency teams can be dispatched:\n"
                        + "\n".join([f"• {q}" for q in clarifying_qs])
                    )
                    dispatcher_notes = [
                        "Pre-RAG Gating: Information incomplete / severity uncertain.",
                        f"Missing info items: {', '.join(missing_info) if missing_info else 'vital details'}.",
                        "Awaiting caller clarification before running RAG or allocating emergency resources."
                    ]
                else:  # Non-Critical
                    person_msg = (
                        "Thank you for contacting AASHRAY. Your inquiry has been routed to low-tier general support: "
                        + intake_eval.get("reason", "Routine or non-life-threatening matter.")
                        + "\nNo high-tier emergency disaster relief resources or rescue teams are dispatched for this request."
                    )
                    dispatcher_notes = [
                        "Pre-RAG Gating: Request classified as Non-Critical.",
                        "Routed to low-tier support / general desk. Emergency RAG pipeline bypassed."
                    ]

                pre_rag_assessment = {
                    "severity": {"level": "S0" if severity == "Non-Critical" else "S1", "numeric": 0 if severity == "Non-Critical" else 1, "word": severity, "reason": intake_eval.get("reason", "")},
                    "urgency": {"level": "U0" if severity == "Non-Critical" else "U1", "numeric": 0 if severity == "Non-Critical" else 1, "word": "Standard", "window": "Pending clarification", "reason": "Pre-RAG intake gate active"},
                    "priority": {"level": "P4" if severity == "Non-Critical" else "P3", "label": "Low-Tier Support" if severity == "Non-Critical" else "Clarification Intake", "reason": intake_eval.get("reason", "")}
                }

                gating_output = {
                    "scenario_id": scenario_id,
                    "scenario": scenario,
                    "pipeline": self.pipeline_name,
                    "model_version": JEV_MODEL_VERSION,
                    "can_proceed_to_rag": False,
                    "needs_clarification": (severity == "Uncertain"),
                    "pre_rag_intake": intake_eval,
                    "severity": severity,
                    "action": action,
                    "is_disaster_related": False,
                    "incident_type": "uncertain" if severity == "Uncertain" else "non_emergency",
                    "assessment": pre_rag_assessment,
                    "unified_assessment": pre_rag_assessment,
                    "situation": intake_eval.get("reason", ""),
                    "person_message": person_msg,
                    "dispatcher_notes": dispatcher_notes,
                    "clarifying_questions": clarifying_qs,
                    "missing_info": missing_info,
                    "resources": [],
                    "selected_resources": [],
                    "not_selected_resources": [],
                    "non_selected_resources": [],
                    "census_context": None,
                    "is_wide_area": False,
                    "place": {"detected": False, "address": None, "district": district_hint},
                    "agencies": [],
                    "excerpts": [],
                    "raw_probabilities": {},
                    "latency": {
                        "pre_rag_ms": round(pre_rag_latency, 1),
                        "triage_ms": 0.0,
                        "retrieval_ms": 0.0,
                        "relevance_gate_ms": 0.0,
                        "generation_ms": 0.0,
                        "total_ms": round(total_latency, 1)
                    },
                    "telemetry": {
                        "total_pipeline_time_ms": round(total_latency, 1),
                        "jev_model_version": JEV_MODEL_VERSION
                    }
                }
                self._log(gating_output)
                self.last_run_record = gating_output
                return gating_output

            if clarification_answer and clarification_answer.strip():
                effective_scenario = f"{scenario}\nCaller Clarification: {clarification_answer.strip()}"

        # ─────────────────────────────────────────────────────────────────────
        # STAGE 1: JEV v3 INTAKE & NATIVE TRIAGE (Sections C, D, E, F)
        # ─────────────────────────────────────────────────────────────────────
        t1_start = time.perf_counter()
        
        triage_result = execute_jev_v3_triage(
            message=effective_scenario,
            coordinates=coordinates,
            district_hint=district_hint
        )
        t1_latency = (time.perf_counter() - t1_start) * 1000.0

        assessment = triage_result.get("assessment", {})
        incident_type = triage_result.get("incident_type", "disaster")
        selected_resources = triage_result.get("selected_resources", [])
        not_selected_resources = triage_result.get("not_selected_resources", [])
        place = triage_result.get("place", {})
        agencies = triage_result.get("nearby_agencies", [])
        census_context = triage_result.get("census_context")
        is_disaster = triage_result.get("is_disaster_related", True)

        selected_ids = [s["resource"] for s in selected_resources]
        print(f"[Pipeline B] JEV v3 Triage: is_disaster={is_disaster}, {len(selected_ids)} chosen, {len(not_selected_resources)} excluded. Priority: {assessment.get('priority', {}).get('level')}")

        # ─────────────────────────────────────────────────────────────────────
        # NON-DISASTER BYPASS: If NOT related to disaster, skip normal RAG and trigger guidance/denial LLM
        # ─────────────────────────────────────────────────────────────────────
        if not is_disaster:
            print(f"[Pipeline B] Input is NOT disaster-related. Skipping normal RAG SOP retrieval & dispatch.")
            non_disaster_plan = generate_non_disaster_plan(
                scenario=scenario,
                triage_result=triage_result
            )
            total_latency = (time.perf_counter() - total_start) * 1000.0
            final_output = {
                "scenario_id": scenario_id,
                "scenario": scenario,
                "pipeline": self.pipeline_name,
                "model_version": JEV_MODEL_VERSION,
                "is_disaster_related": False,
                "can_proceed_to_rag": False,
                "needs_clarification": False,
                "pre_rag_intake": intake_eval,
                "incident_type": "non_emergency",
                "assessment": assessment,
                "unified_assessment": assessment,
                "situation": non_disaster_plan.get("situation", ""),
                "person_message": non_disaster_plan.get("person_message", ""),
                "dispatcher_notes": non_disaster_plan.get("dispatcher_notes", []),
                "resources": [],
                "selected_resources": [],
                "not_selected_resources": not_selected_resources,
                "non_selected_resources": not_selected_resources,
                "census_context": None,
                "is_wide_area": False,
                "place": place,
                "agencies": [],
                "excerpts": [],
                "raw_probabilities": triage_result.get("raw_probabilities", {}),
                "latency": {
                    "pre_rag_ms": round(pre_rag_latency, 1),
                    "triage_ms": round(t1_latency, 1),
                    "retrieval_ms": 0.0,
                    "relevance_gate_ms": 0.0,
                    "generation_ms": round(total_latency - t1_latency, 1),
                    "total_ms": round(total_latency, 1)
                },
                "telemetry": {
                    "total_pipeline_time_ms": round(total_latency, 1),
                    "jev_model_version": JEV_MODEL_VERSION
                }
            }
            self._log(final_output)
            self.last_run_record = final_output
            return final_output

        # ─────────────────────────────────────────────────────────────────────
        # STAGE 2: RAG RETRIEVAL & RELEVANCE GATE (Section G)
        # ─────────────────────────────────────────────────────────────────────
        r_start = time.perf_counter()

        # Build targeted query terms per selected resource
        raw_retrieved_map = self.retriever.retrieve_for_all_resources(scenario, selected_ids)
        r_latency = (time.perf_counter() - r_start) * 1000.0

        # Flatten candidate chunks
        candidate_chunks = []
        for res_name, chunks in raw_retrieved_map.items():
            for c in chunks:
                candidate_chunks.append({
                    "resource": res_name,
                    "chunk_id": c.get("chunk_id"),
                    "source_file": c.get("source_file"),
                    "page": c.get("page"),
                    "chunk_text": c.get("chunk_text")
                })

        # Run Relevance Gate (Section G2, G4, G6)
        # Drops hazard-incompatible chunks & below cutoff, extracts 1-3 supporting benchmark sentences
        gate_start = time.perf_counter()
        passed_excerpts = run_relevance_gate(
            candidate_chunks=candidate_chunks,
            scenario=scenario,
            incident_type=incident_type,
            cutoff=0.40
        )
        gate_latency = (time.perf_counter() - gate_start) * 1000.0
        print(f"[Pipeline B] Relevance Gate: {len(passed_excerpts)} / {len(candidate_chunks)} excerpts passed gate.")

        # Ensure all passed excerpts have clean IDs, title, and text
        for idx, ex in enumerate(passed_excerpts, 1):
            eid = f"E{idx}"
            ex["id"] = eid
            ex["eid"] = eid
            doc_title = ex.get("document_title") or get_readable_doc_title(ex.get("source_file", ""))
            ex["title"] = doc_title
            ex["document_title"] = doc_title
            ex["text"] = ex.get("chunk_text", "")

        # ─────────────────────────────────────────────────────────────────────
        # STAGE 3: STAGE 2 OPERATIONAL PLAN GENERATION (Section H)
        # ─────────────────────────────────────────────────────────────────────
        g_start = time.perf_counter()

        stage2_plan = generate_stage2_v3_plan(
            triage_result=triage_result,
            excerpts=passed_excerpts,
            agencies=agencies
        )
        g_latency = (time.perf_counter() - g_start) * 1000.0
        total_latency = (time.perf_counter() - total_start) * 1000.0

        # Cross-reference cited excerpt_ids to action_used
        for r in stage2_plan.get("resources", []):
            r_name = r.get("resource_name") or r.get("resource_id", "").replace("_", " ").title()
            for eid in r.get("excerpt_ids", []):
                for ex in passed_excerpts:
                    if ex.get("id") == eid or ex.get("eid") == eid:
                        ex["action_used"] = r_name

        for idx, ex in enumerate(passed_excerpts):
            if not ex.get("action_used") and selected_resources:
                res_fallback = selected_resources[min(idx, len(selected_resources) - 1)]
                ex["action_used"] = res_fallback.get("resource_label") or res_fallback.get("resource", "").replace("_", " ").title()

        # ─────────────────────────────────────────────────────────────────────
        # ASSEMBLE FINAL UNIFIED RESPONSE (Invariant B2, I)
        # ─────────────────────────────────────────────────────────────────────
        final_output = {
            "scenario_id": scenario_id,
            "scenario": scenario,
            "pipeline": self.pipeline_name,
            "model_version": JEV_MODEL_VERSION,
            "is_disaster_related": True,
            "can_proceed_to_rag": True,
            "needs_clarification": False,
            "pre_rag_intake": intake_eval,
            "severity": intake_eval.get("severity") if intake_eval else assessment.get("severity", {}).get("word"),
            "action": "allocate_resources",
            "disaster_assessment": triage_result.get("disaster_assessment", {}),
            "incident_type": incident_type,
            "assessment": assessment,  # Single unified object for priority, severity, urgency
            "unified_assessment": assessment,
            "situation": stage2_plan.get("situation", ""),
            "person_message": stage2_plan.get("person_message", ""),
            "dispatcher_notes": stage2_plan.get("dispatcher_notes", []),
            "resources": stage2_plan.get("resources", []),
            "selected_resources": selected_resources,
            "not_selected_resources": not_selected_resources,
            "non_selected_resources": not_selected_resources,
            "census_context": census_context,
            "is_wide_area": triage_result.get("wide_area", {}).get("is_wide_area", False),
            "place": place,
            "agencies": agencies[:6],
            "excerpts": passed_excerpts,
            "raw_probabilities": triage_result.get("raw_probabilities", {}),
            "latency": {
                "pre_rag_ms": round(pre_rag_latency, 1),
                "triage_ms": round(t1_latency, 1),
                "retrieval_ms": round(r_latency, 1),
                "relevance_gate_ms": round(gate_latency, 1),
                "generation_ms": round(g_latency, 1),
                "total_ms": round(total_latency, 1)
            },
            "telemetry": {
                "total_pipeline_time_ms": round(total_latency, 1),
                "jev_model_version": JEV_MODEL_VERSION
            }
        }

        # Log run
        self._log(final_output)
        self.last_run_record = final_output
        return final_output

    def _log(self, record: Dict[str, Any]):
        for path in [self.runs_file, self.shared_runs_file]:
            try:
                with open(path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(record) + "\n")
            except Exception as log_err:
                print(f"Warning logging run: {log_err}")

if __name__ == "__main__":
    pipe = DisasterRAGPipelineB()
    test_scenario = "Severe flash flood in Wayanad district. 50 families stranded on rooftops without clean drinking water and food. Need emergency boats and rescue teams immediately."
    out = pipe.run("TEST-001", test_scenario, coordinates={"lat": 11.685, "lng": 76.132}, district_hint="Wayanad")
    print(json.dumps(out, indent=2))
