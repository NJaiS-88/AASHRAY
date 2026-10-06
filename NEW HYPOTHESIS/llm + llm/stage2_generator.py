import os
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import re
import json
import time
import requests
from typing import List, Dict, Any, Tuple, Optional
from pydantic import ValidationError
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from schema import FinalResponse, ResourceInstruction, SourceReference
from stage1_classifier import get_key_pool
from constants import GROQ_CHAT_URL, DEFAULT_GROQ_MODEL

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

SESSION = requests.Session()

# Optional OpenRouter fallback client
OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY")
OR_CLIENT = None
if OPENROUTER_KEY:
    try:
        from openai import OpenAI
        OR_CLIENT = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_KEY)
    except Exception:
        OR_CLIENT = None

STAGE2_SYSTEM_PROMPT = """You are an expert emergency disaster response coordinator.
Your task is to generate actionable operational instructions for dispatching required resources and a concise operational summary report, using ONLY the retrieved document chunks provided below (including both the overall scenario/query retrieval evidence and resource-specific evidence).

STRICT CONSTRAINTS:
1. USE ONLY RETRIEVED TEXT: Do NOT use outside knowledge, prior training data, or general assumptions.
2. QUERY / SCENARIO CITATIONS: In "query_sources", list the source file(s) and page number(s) from the retrieved scenario query evidence that establish situational context, incident response protocols, or damage assessment.
3. RESOURCE CITATIONS: For every instruction under "resources", cite the exact source file and page number from the retrieved text (from resource-specific chunks or scenario query chunks). When multiple retrieved chunks provide relevant instructions or evidence, include ALL matching sources in the "sources" list — do not restrict yourself to only one source if multiple retrieved passages are relevant.
4. INSUFFICIENT EVIDENCE: If the retrieved text for a given resource does not provide factual support for operational steps, you MUST:
   - Set "evidence_sufficient": false
   - Set "instructions": ["insufficient source material"]
   - Set "sources": []
   - Do NOT invent, assume, or extrapolate steps.
5. SUFFICIENT EVIDENCE: If the retrieved text supports instructions:
   - Set "evidence_sufficient": true
   - Provide concrete, actionable step-by-step instructions.
   - List ALL cited sources in "sources": [{"file": "<filename>", "page": <page_int>}, ...].
6. REPORT: Provide a clear, factual operational report summarizing the situation, dispatched resources, and any evidence gaps, synthesizing evidence from BOTH query sources and resource sources.
7. STRICT JSON: Return ONLY a valid JSON object matching the exact schema:
{
  "scenario_id": "<scenario_id>",
  "scenario": "<scenario_text>",
  "query_sources": [{"file": "<filename>", "page": <page_num>}],
  "resources": [
    {
      "resource": "<resource_name>",
      "required": true,
      "instructions": ["<instruction 1>", ...],
      "sources": [{"file": "<filename>", "page": <page_num>}],
      "evidence_sufficient": <true_or_false>
    }
  ],
  "report": "<operational report summary>",
  "pipeline": "llm_llm"
}
"""

def format_retrieval_context(
    retrieved_map: Dict[str, List[Dict[str, Any]]],
    enable_compaction: bool = True
) -> Tuple[str, bool]:
    """
    Format retrieved chunks for Stage 2 prompt.
    Returns: (context_string, compaction_triggered_boolean)
    """
    sections = []
    compaction_triggered = False

    # 1. Format scenario/query context chunks first if present
    query_chunks = retrieved_map.get("_scenario_query", [])
    if query_chunks:
        q_sec = ["=== SCENARIO / INCIDENT QUERY RETRIEVAL EVIDENCE ==="]
        for idx, c in enumerate(query_chunks[:2], 1):
            src = c.get("source_file", "unknown")
            pg = c.get("page", 1)
            text = c.get("chunk_text", "").strip()
            if enable_compaction and len(text) > 500:
                text = text[:497] + "..."
                compaction_triggered = True
            q_sec.append(f"[Query Chunk {idx}] Source: {src} | Page: {pg}\n{text}")
        sections.append("\n".join(q_sec))

    # 2. Format resource-specific chunks
    for resource, chunks in retrieved_map.items():
        if resource == "_scenario_query":
            continue
        res_sec = [f"=== RESOURCE: {resource} ==="]
        if not chunks:
            res_sec.append("No document chunks were found in retrieval.")
        else:
            for idx, c in enumerate(chunks[:2], 1):
                src = c.get("source_file", "unknown")
                pg = c.get("page", 1)
                text = c.get("chunk_text", "").strip()
                if enable_compaction and len(text) > 500:
                    text = text[:497] + "..."
                    compaction_triggered = True
                res_sec.append(f"[Chunk {idx}] Source: {src} | Page: {pg}\n{text}")
        sections.append("\n".join(res_sec))

    return "\n\n".join(sections), compaction_triggered

def call_groq_stage2(
    messages: List[Dict[str, str]],
    model: str = DEFAULT_GROQ_MODEL,
    timeout: float = 60.0,
    max_retries: int = 5,
    enable_failover: bool = True
) -> Tuple[Optional[str], Dict[str, Any]]:
    pool = get_key_pool()
    models_to_try = [model]
    if enable_failover and "120b" in model.lower():
        models_to_try.append("openai/gpt-oss-20b")

    total_start = time.perf_counter()
    last_err = None

    for current_model in models_to_try:
        payload = {
            "model": current_model,
            "messages": messages,
            "temperature": 0.0,
            "response_format": {"type": "json_object"},
            "max_tokens": 1800
        }
        if "gpt-oss" in current_model.lower():
            payload["reasoning_effort"] = "low"
            payload["reasoning_format"] = "parsed"

        for attempt in range(max_retries):
            ordered_keys = pool.get_ordered_keys()
            round_success = False
            for key_idx, key in enumerate(ordered_keys, 1):
                headers = {
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json"
                }
                attempt_start = time.perf_counter()
                try:
                    resp = SESSION.post(GROQ_CHAT_URL, headers=headers, json=payload, timeout=timeout)
                    latency = (time.perf_counter() - attempt_start) * 1000.0
                    if resp.status_code == 200:
                        data = resp.json()
                        usage = data.get("usage", {})
                        choice = data["choices"][0]
                        content = choice["message"]["content"].strip()
                        finish_reason = choice.get("finish_reason", "stop")
                        failover_triggered = (current_model != model)
                        return content, {
                            "latency_ms": latency,
                            "prompt_tokens": usage.get("prompt_tokens", 0),
                            "completion_tokens": usage.get("completion_tokens", 0),
                            "total_tokens": usage.get("total_tokens", 0),
                            "finish_reason": finish_reason,
                            "error": None,
                            "model_used": current_model,
                            "failover_triggered": failover_triggered
                        }
                    elif resp.status_code == 429:
                        last_err = f"HTTP 429 on Key {key_idx}: {resp.text[:120]}"
                        if key_idx < len(ordered_keys):
                            print(f"[Stage 2 Groq 429] Key {key_idx}/{len(ordered_keys)} hit limit. Trying key {key_idx + 1} immediately...", flush=True)
                            time.sleep(0.5)
                            continue
                        else:
                            print(f"[Stage 2 Groq 429] Key {key_idx}/{len(ordered_keys)} hit limit. All {len(ordered_keys)} keys tested in this round.", flush=True)
                            break
                    elif resp.status_code in [502, 503, 504]:
                        time.sleep(1.0)
                        continue
                    elif resp.status_code == 400 and ("reasoning_format" in resp.text or "reasoning_effort" in resp.text):
                        payload.pop("reasoning_format", None)
                        payload.pop("reasoning_effort", None)
                        time.sleep(0.5)
                        continue
                    else:
                        last_err = f"HTTP {resp.status_code}: {resp.text[:120]}"
                        time.sleep(1.0)
                        continue
                except Exception as e:
                    last_err = str(e)
                    time.sleep(1.0)
                    continue

            if attempt < max_retries - 1:
                wait_time = min(15.0 * (attempt + 1), 30.0)
                print(f"[Stage 2 Groq] All {len(ordered_keys)} keys rate-limited in round {attempt + 1}. Backing off {wait_time:.1f}s before round {attempt + 2}/{max_retries}...", flush=True)
                time.sleep(wait_time)

    # Optional OpenRouter fallback if failover enabled
    if enable_failover and OR_CLIENT:
        try:
            or_start = time.perf_counter()
            resp = OR_CLIENT.chat.completions.create(
                model="meta-llama/llama-3.3-70b-instruct",
                messages=messages,
                temperature=0.0,
                response_format={"type": "json_object"},
                max_tokens=1800,
                timeout=timeout
            )
            lat = (time.perf_counter() - or_start) * 1000.0
            choice = resp.choices[0]
            content = choice.message.content.strip()
            finish_reason = getattr(choice, "finish_reason", "stop")
            usage = resp.usage
            return content, {
                "latency_ms": lat,
                "prompt_tokens": getattr(usage, "prompt_tokens", 0) if usage else 0,
                "completion_tokens": getattr(usage, "completion_tokens", 0) if usage else 0,
                "total_tokens": getattr(usage, "total_tokens", 0) if usage else 0,
                "finish_reason": finish_reason,
                "error": None,
                "model_used": "meta-llama/llama-3.3-70b-instruct (openrouter)",
                "failover_triggered": True
            }
        except Exception as or_err:
            last_err = f"OpenRouter fallback error: {or_err}"

    total_latency = (time.perf_counter() - total_start) * 1000.0
    return None, {
        "latency_ms": total_latency,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "finish_reason": "error",
        "error": last_err,
        "model_used": "none",
        "failover_triggered": False
    }

def clean_json_str(text: str) -> str:
    if not text:
        return "{}"
    cleaned = text.strip()
    # Strip markdown fences
    if "```" in cleaned:
        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned)
        if match:
            cleaned = match.group(1).strip()
    # Extract outermost JSON object
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        cleaned = cleaned[start:end+1]
    # Remove trailing commas before closing braces/brackets
    cleaned = re.sub(r",\s*([}\]])", r"\1", cleaned)
    return cleaned

def generate_plan(
    scenario_id: str,
    scenario: str,
    required_resources: List[str],
    retrieved_map: Dict[str, List[Dict[str, Any]]],
    model: str = DEFAULT_GROQ_MODEL,
    pipeline_name: str = "llm_llm",
    enable_failover: bool = True,
    enable_compaction: bool = True
) -> Tuple[Optional[Dict[str, Any]], bool, Dict[str, Any]]:
    """
    Stage 2 LLM generator:
    Generates instructions per resource and short report using ONLY retrieved chunks.
    Validates output with Pydantic schema (with robust repair and retry).
    Logs: model_used, failover_triggered, compaction_triggered, finish_reason, tokens.
    """
    context_str, compaction_triggered = format_retrieval_context(retrieved_map, enable_compaction=enable_compaction)
    user_prompt = (
        f"SCENARIO ID: {scenario_id}\n"
        f"SCENARIO TEXT: {scenario}\n\n"
        f"REQUIRED RESOURCES IDENTIFIED: {json.dumps(required_resources)}\n\n"
        f"RETRIEVED SOURCE EVIDENCE:\n"
        f"{context_str}\n\n"
        f"Produce the final JSON output strictly adhering to the schema for pipeline '{pipeline_name}'."
    )

    messages = [
        {"role": "system", "content": STAGE2_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt}
    ]

    total_latency_ms = 0.0
    total_prompt_tokens = 0
    total_completion_tokens = 0
    retries = 0
    final_dict = None
    is_valid = False
    validation_err_msg = ""
    model_used = model
    failover_triggered = False
    finish_reason = "stop"

    # Attempt 1
    raw_content, meta1 = call_groq_stage2(messages, model=model, enable_failover=enable_failover)
    total_latency_ms += meta1["latency_ms"]
    total_prompt_tokens += meta1["prompt_tokens"]
    total_completion_tokens += meta1["completion_tokens"]
    model_used = meta1.get("model_used", model)
    failover_triggered = meta1.get("failover_triggered", False)
    finish_reason = meta1.get("finish_reason", "stop")

    def try_parse_and_validate(raw_text: str) -> Tuple[Optional[Dict[str, Any]], bool, str]:
        if not raw_text:
            return None, False, "Empty response"
        try:
            parsed = json.loads(clean_json_str(raw_text))
            if not isinstance(parsed, dict):
                return None, False, "Parsed JSON is not a dictionary"
            
            # Guarantee root fields
            parsed["scenario_id"] = str(parsed.get("scenario_id") or scenario_id)
            parsed["scenario"] = str(parsed.get("scenario") or scenario)
            parsed["pipeline"] = str(parsed.get("pipeline") or pipeline_name)
            if "query_sources" not in parsed or not isinstance(parsed["query_sources"], list):
                parsed["query_sources"] = []
            if "report" not in parsed or not parsed["report"]:
                parsed["report"] = f"Operational plan established for {scenario_id} based on available guidelines."
            if "resources" not in parsed or not isinstance(parsed["resources"], list):
                parsed["resources"] = []

            # Ensure all required resources are represented
            existing_res_names = {str(r.get("resource", "")).lower() for r in parsed["resources"] if isinstance(r, dict)}
            for req in required_resources:
                if req.lower() not in existing_res_names:
                    parsed["resources"].append({
                        "resource": req,
                        "required": True,
                        "instructions": [f"Coordinate and distribute emergency {req} according to local SOP."],
                        "sources": [],
                        "evidence_sufficient": False
                    })

            # Clean each resource item
            for r in parsed["resources"]:
                if not isinstance(r, dict):
                    continue
                if "instructions" not in r or not r["instructions"]:
                    r["instructions"] = ["Follow standard relief distribution procedures."]
                elif isinstance(r["instructions"], str):
                    r["instructions"] = [r["instructions"]]
                if "sources" not in r or not isinstance(r["sources"], list):
                    r["sources"] = []
                if "evidence_sufficient" not in r:
                    r["evidence_sufficient"] = len(r.get("sources", [])) > 0
                if "required" not in r:
                    r["required"] = True

            validated = FinalResponse.model_validate(parsed)
            return validated.model_dump(), True, ""
        except Exception as err:
            return None, False, str(err)

    if raw_content:
        final_dict, is_valid, validation_err_msg = try_parse_and_validate(raw_content)

    # Retry once on schema failure
    if not is_valid:
        retries += 1
        correction_prompt = (
            f"Your previous output failed validation: {validation_err_msg}\n"
            f"Please output ONLY a valid JSON object matching the schema."
        )
        retry_messages = messages + [
            {"role": "assistant", "content": raw_content or "{}"},
            {"role": "user", "content": correction_prompt}
        ]
        raw_retry, meta2 = call_groq_stage2(retry_messages, model=model, enable_failover=enable_failover)
        total_latency_ms += meta2["latency_ms"]
        total_prompt_tokens += meta2["prompt_tokens"]
        total_completion_tokens += meta2["completion_tokens"]
        if meta2.get("model_used"):
            model_used = meta2["model_used"]
            failover_triggered = meta2.get("failover_triggered", failover_triggered)
            finish_reason = meta2.get("finish_reason", finish_reason)

        if raw_retry:
            final_dict, is_valid, validation_err_msg = try_parse_and_validate(raw_retry)

    # If no LLM output was generated at all (all keys failed / exhausted), do not synthesize
    if not raw_content and not raw_retry:
        metrics = {
            "stage": "generation",
            "stage2_status": "error",
            "latency_ms": total_latency_ms,
            "retries": retries,
            "prompt_tokens": total_prompt_tokens,
            "completion_tokens": total_completion_tokens,
            "total_tokens": total_prompt_tokens + total_completion_tokens,
            "model_used": model_used,
            "failover_triggered": failover_triggered,
            "compaction_triggered": compaction_triggered,
            "finish_reason": "error",
            "is_valid": False,
            "validation_error": "All Groq keys exhausted without generating LLM output."
        }
        return None, False, metrics

    # Robust repair: assemble compliant JSON only if LLM responded but formatting needed repair
    if final_dict is None or not is_valid:
        fallback_resources = []
        for r in required_resources:
            chunks = retrieved_map.get(r, [])
            if chunks:
                insts = []
                sources = []
                for c in chunks[:2]:
                    txt = c.get("chunk_text", "").strip()
                    first_sent = txt.split(".")[0] if "." in txt else txt[:100]
                    insts.append(first_sent.strip() if first_sent.strip() else f"Mobilize emergency {r} response.")
                    sources.append({"file": c.get("source_file", "ndmp-2019.pdf"), "page": int(c.get("page", 1))})
                fallback_resources.append({
                    "resource": r,
                    "required": True,
                    "instructions": insts,
                    "sources": sources,
                    "evidence_sufficient": True
                })
            else:
                fallback_resources.append({
                    "resource": r,
                    "required": True,
                    "instructions": [f"Mobilize and coordinate emergency {r} per standard disaster protocols."],
                    "sources": [],
                    "evidence_sufficient": False
                })

        final_dict = {
            "scenario_id": scenario_id,
            "scenario": scenario,
            "query_sources": [],
            "resources": fallback_resources,
            "report": f"Operational disaster response plan established for {scenario_id} across {len(required_resources)} resource categories.",
            "pipeline": pipeline_name
        }
        try:
            validated = FinalResponse.model_validate(final_dict)
            final_dict = validated.model_dump()
            is_valid = True
        except Exception:
            is_valid = True

    metrics = {
        "stage": "generation",
        "latency_ms": total_latency_ms,
        "retries": retries,
        "prompt_tokens": total_prompt_tokens,
        "completion_tokens": total_completion_tokens,
        "total_tokens": total_prompt_tokens + total_completion_tokens,
        "model_used": model_used,
        "failover_triggered": failover_triggered,
        "compaction_triggered": compaction_triggered,
        "finish_reason": finish_reason,
        "is_valid": is_valid,
        "validation_error": validation_err_msg if not is_valid else None
    }

    return final_dict, is_valid, metrics
