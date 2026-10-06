import os
import sys
import time
import re
import requests
from typing import List, Dict, Any, Tuple, Optional
from dotenv import load_dotenv

# Ensure llm + llm directory is in sys.path to import shared constants
LLM_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "llm + llm"))
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for p in [LLM_DIR, ROOT_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

load_dotenv(os.path.join(ROOT_DIR, ".env"))
load_dotenv(os.path.join(LLM_DIR, ".env"))

from constants import (
    RESOURCE_COLUMNS,
    RESOURCE_DESCRIPTIONS,
    RESOURCE_DESC_TEXT,
    RESOURCE_CRITERIA_QUESTIONS,
    RESOURCE_DEFINITIONS_VERSION,
    SHARED_REQUIRED_DEFINITION,
    ACTIVE_DEFINITION_VERSION,
    OPENROUTER_DECISIONS_URL,
    DEFAULT_JEV_MODEL
)

SESSION = requests.Session()

class Stage1JevError(Exception):
    """Raised when Stage 1 JEV classification encounters an API or parsing error."""
    pass

# Tuned threshold from benchmark dev set (tau* = 0.15)
JEV_THRESHOLD: float = 0.15

# Thread-safe / module storage for execution metrics
_LAST_JEV_META: Dict[str, Any] = {}

def get_last_jev_meta() -> Dict[str, Any]:
    return _LAST_JEV_META

def call_jev_decisions_shared(
    scenario: str,
    api_key: str,
    model: str = DEFAULT_JEV_MODEL,
    max_retries: int = 5,
    timeout: float = 40.0
) -> Dict[str, Any]:
    """
    Call TypeSafe JEV via OpenRouter Decisions API using the exact shared definitions
    and shared required criteria questions from constants.py.
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/emergency-benchmark",
        "X-Title": "Disaster Resource Benchmark"
    }

    rich_state = (
        "EMERGENCY DISASTER SITUATION REPORT & HUMANITARIAN DISPATCH ASSESSMENT\n"
        "================================================================================\n"
        "COMMUNICATION CHANNEL: Emergency disaster dispatch / eyewitness report\n"
        f"INCOMING MESSAGE TRANSCRIPT:\n\"{scenario}\"\n"
        "================================================================================\n"
        "MISSION OBJECTIVE: Accurately classify which specific relief resources are REQUIRED.\n\n"
        "DEFINITION OF REQUIRED:\n"
        f"{SHARED_REQUIRED_DEFINITION}\n\n"
        "RESOURCE DEFINITIONS & SCOPE:\n"
        f"{RESOURCE_DESC_TEXT}"
    )

    questions = {}
    for res in RESOURCE_COLUMNS:
        questions[res] = {
            "type": "noul",
            "instructions": RESOURCE_CRITERIA_QUESTIONS[res]
        }

    payload = {
        "model": model,
        "state": rich_state,
        "questions": questions
    }

    start_total = time.perf_counter()
    retries_used = 0
    last_err = None

    for attempt in range(max_retries):
        attempt_start = time.perf_counter()
        try:
            resp = SESSION.post(OPENROUTER_DECISIONS_URL, headers=headers, json=payload, timeout=timeout)
            api_latency_ms = (time.perf_counter() - attempt_start) * 1000.0

            if resp.status_code == 200:
                data = resp.json()
                answers = data.get("answers", {})
                usage = data.get("usage", {})
                prompt_tokens = usage.get("input_tokens", usage.get("prompt_tokens", len(rich_state.split())))
                completion_tokens = usage.get("output_tokens", usage.get("completion_tokens", len(RESOURCE_COLUMNS) * 3))

                probs = {}
                for k in RESOURCE_COLUMNS:
                    v = answers.get(k, {})
                    if isinstance(v, dict):
                        p = v.get("noul", v.get("confidence", v.get("probability", 0.0)))
                    elif isinstance(v, (int, float)):
                        p = float(v)
                    else:
                        p = 0.0
                    probs[k] = round(float(max(0.0, min(1.0, p))), 4)

                return {
                    "success": True,
                    "stage1_status": "ok",
                    "stage1_error": None,
                    "probabilities": probs,
                    "latency_ms": api_latency_ms,
                    "total_elapsed_ms": (time.perf_counter() - start_total) * 1000.0,
                    "retries": retries_used,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": prompt_tokens + completion_tokens,
                    "raw_response": data
                }

            elif resp.status_code in [429, 502, 503, 504]:
                retries_used += 1
                wait_time = 3.0 * (attempt + 1)
                ra = resp.headers.get("Retry-After")
                if ra:
                    try:
                        wait_time = max(wait_time, float(ra) + 1.0)
                    except Exception:
                        pass
                m = re.search(r"try again in ([\d\.]+)s", resp.text, re.IGNORECASE)
                if m:
                    try:
                        wait_time = max(wait_time, float(m.group(1)) + 1.0)
                    except Exception:
                        pass
                last_err = f"HTTP {resp.status_code}: {resp.text[:120]}"
                print(f"[Stage 1 JEV {resp.status_code}] Backing off {wait_time:.1f}s (retry {attempt + 1}/{max_retries})...", flush=True)
                time.sleep(wait_time)
                continue
            else:
                retries_used += 1
                last_err = f"HTTP {resp.status_code}: {resp.text[:120]}"
                time.sleep(2.0)
        except Exception as e:
            retries_used += 1
            last_err = str(e)
            time.sleep(2.0)

    # If retries exhausted, report error
    total_elapsed = (time.perf_counter() - start_total) * 1000.0
    return {
        "success": False,
        "stage1_status": "error",
        "stage1_error": last_err or "Unknown JEV error after retries",
        "probabilities": {},
        "latency_ms": total_elapsed,
        "total_elapsed_ms": total_elapsed,
        "retries": retries_used,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "raw_response": None
    }

def classify_jev_detailed(
    scenario: str,
    model: str = DEFAULT_JEV_MODEL,
    threshold: float = JEV_THRESHOLD
) -> Tuple[Optional[List[str]], Dict[str, Any]]:
    """
    Execute Stage-1 JEV classification via OpenRouter Decisions API.
    RULE: Never convert an API error into an empty resource list.
    Empty lists must come ONLY from a successful response where all probabilities < threshold.
    Returns:
        (required_resources_list, metrics_dict)
    """
    global _LAST_JEV_META
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY is not set in environment or .env file!")

    res = call_jev_decisions_shared(
        scenario=scenario,
        api_key=api_key,
        model=model
    )

    if not res.get("success", False) or res.get("stage1_status") != "ok":
        meta = {
            "stage": "classification",
            "provider": "jev",
            "model": model,
            "threshold": threshold,
            "stage1_status": "error",
            "stage1_error": res.get("stage1_error", "JEV call failed"),
            "definitions_version": RESOURCE_DEFINITIONS_VERSION,
            "probabilities": {},
            "latency_ms": res.get("latency_ms", 0.0),
            "total_elapsed_ms": res.get("total_elapsed_ms", 0.0),
            "retries": res.get("retries", 0),
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "cost": 0.0,
            "success": False,
            "raw_response": None
        }
        _LAST_JEV_META = meta
        return None, meta

    probs = res.get("probabilities", {})
    # Select required resources where probability >= threshold
    required_resources = [
        r for r in RESOURCE_COLUMNS
        if probs.get(r, 0.0) >= threshold
    ]

    meta = {
        "stage": "classification",
        "provider": "jev",
        "model": model,
        "threshold": threshold,
        "stage1_status": "ok",
        "stage1_error": None,
        "definitions_version": RESOURCE_DEFINITIONS_VERSION,
        "probabilities": probs,
        "latency_ms": res.get("latency_ms", 0.0),
        "total_elapsed_ms": res.get("total_elapsed_ms", 0.0),
        "retries": res.get("retries", 0),
        "prompt_tokens": res.get("prompt_tokens", 0),
        "completion_tokens": res.get("completion_tokens", 0),
        "total_tokens": res.get("total_tokens", 0),
        "cost": (res.get("prompt_tokens", 0) * 0.04) / 1_000_000.0,
        "success": True,
        "raw_response": res.get("raw_response")
    }

    _LAST_JEV_META = meta
    return required_resources, meta

def classify_jev(scenario: str) -> List[str]:
    """
    Swappable Stage 1 signature:
    classify_jev(scenario: str) -> list[str]
    Raises Stage1JevError on failure to ensure errors are never converted to empty lists.
    """
    resources, meta = classify_jev_detailed(scenario)
    if meta.get("stage1_status") != "ok" or resources is None:
        raise Stage1JevError(f"Stage 1 JEV classification failed: {meta.get('stage1_error')}")
    return resources
