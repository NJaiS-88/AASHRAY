import os
import sys
import json
import time
import re
import requests
from typing import List, Dict, Any, Tuple, Optional
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from constants import (
    RESOURCE_COLUMNS,
    STAGE1_SYSTEM_PROMPT,
    RESOURCE_DEFINITIONS_VERSION,
    GROQ_CHAT_URL,
    DEFAULT_GROQ_MODEL
)

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

SESSION = requests.Session()

class Stage1ClassifierError(Exception):
    """Raised when Stage 1 classification encounters an API or parsing error."""
    pass

class GroqKeyPool:
    def __init__(self, keys: Optional[List[str]] = None):
        if not keys:
            keys = []
            candidates = ["GROQ_API_KEY"] + [f"GROQ_API_KEY{i}" for i in range(1, 21)]
            for var in candidates:
                k = os.getenv(var)
                if k and k.strip() and k.strip() not in keys:
                    keys.append(k.strip())
        self.keys = keys
        self.idx = 0

    def get_key(self) -> str:
        if not self.keys:
            raise ValueError("No Groq API keys found. Please set GROQ_API_KEY in .env.")
        key = self.keys[self.idx % len(self.keys)]
        self.idx += 1
        return key

    def get_ordered_keys(self) -> List[str]:
        if not self.keys:
            raise ValueError("No Groq API keys found. Please set GROQ_API_KEY in .env.")
        start = self.idx % len(self.keys)
        self.idx += 1
        return self.keys[start:] + self.keys[:start]

_KEY_POOL = None

def get_key_pool() -> GroqKeyPool:
    global _KEY_POOL
    if _KEY_POOL is None:
        _KEY_POOL = GroqKeyPool()
    return _KEY_POOL

# Thread-local / module storage for execution metrics
_LAST_CLASSIFICATION_META: Dict[str, Any] = {}

def get_last_classification_meta() -> Dict[str, Any]:
    return _LAST_CLASSIFICATION_META

def clean_json_content(content: str) -> str:
    content = content.strip()
    if content.startswith("```"):
        lines = content.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        content = "\n".join(lines).strip()
    return content

def classify_detailed(
    scenario: str,
    model: str = DEFAULT_GROQ_MODEL,
    max_retries: int = 5,
    timeout: float = 60.0
) -> Tuple[Optional[List[str]], Dict[str, Any]]:
    """
    Execute stage-1 Groq LLM classification.
    RULE: Never convert an API error into an empty resource list.
    Empty lists must come ONLY from a successful model response where all resources are 0.
    Returns:
        (required_resources_list, metrics_dict)
    """
    global _LAST_CLASSIFICATION_META
    pool = get_key_pool()
    start_time = time.perf_counter()

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": STAGE1_SYSTEM_PROMPT},
            {"role": "user", "content": f"Emergency Message: \"{scenario}\""}
        ],
        "temperature": 0.0,
        "response_format": {"type": "json_object"}
    }

    if "gpt-oss" in model.lower():
        payload["reasoning_effort"] = "low"
        payload["reasoning_format"] = "parsed"
        payload["max_tokens"] = 500

    last_err = None
    retries_used = 0
    prompt_tokens = 0
    completion_tokens = 0
    parsed = None
    success = False

    for retry_round in range(max_retries):
        ordered_keys = pool.get_ordered_keys()
        for key_idx, key in enumerate(ordered_keys, 1):
            headers = {
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json"
            }
            try:
                resp = SESSION.post(GROQ_CHAT_URL, headers=headers, json=payload, timeout=timeout)
                if resp.status_code == 200:
                    data = resp.json()
                    usage = data.get("usage", {})
                    prompt_tokens = usage.get("prompt_tokens", 0)
                    completion_tokens = usage.get("completion_tokens", 0)
                    raw_text = data["choices"][0]["message"]["content"]
                    content = clean_json_content(raw_text)

                    try:
                        parsed = json.loads(content)
                        if isinstance(parsed, dict) and len(parsed) > 0:
                            success = True
                            break
                        else:
                            last_err = f"Parsed JSON is empty or not a dict: {content[:100]}"
                    except Exception as je:
                        last_err = f"JSON decode error: {je} from raw text: {content[:100]}"
                    
                    retries_used += 1
                    time.sleep(0.5)
                    continue

                elif resp.status_code in [429, 502, 503, 504]:
                    retries_used += 1
                    last_err = f"HTTP {resp.status_code}: {resp.text[:120]}"
                    if key_idx < len(ordered_keys):
                        print(f"[Stage 1 LLM {resp.status_code}] Key {key_idx}/{len(ordered_keys)} hit limit. Trying key {key_idx + 1} immediately...", flush=True)
                        time.sleep(0.5)
                        continue
                    else:
                        print(f"[Stage 1 LLM {resp.status_code}] Key {key_idx}/{len(ordered_keys)} hit limit. All {len(ordered_keys)} keys tested in this round.", flush=True)
                        break

                elif resp.status_code == 400 and ("reasoning_format" in resp.text or "reasoning_effort" in resp.text):
                    payload.pop("reasoning_format", None)
                    payload.pop("reasoning_effort", None)
                    retries_used += 1
                    time.sleep(0.5)
                    continue
                else:
                    retries_used += 1
                    last_err = f"HTTP {resp.status_code}: {resp.text[:120]}"
                    time.sleep(1.0)
                    continue
            except Exception as e:
                retries_used += 1
                last_err = str(e)
                time.sleep(1.0)
                continue

        if success:
            break

        if retry_round < max_retries - 1:
            wait_time = min(15.0 * (retry_round + 1), 30.0)
            print(f"[Stage 1 LLM] All {len(ordered_keys)} keys rate-limited in round {retry_round + 1}. Backing off {wait_time:.1f}s before round {retry_round + 2}/{max_retries}...", flush=True)
            time.sleep(wait_time)

    latency_ms = (time.perf_counter() - start_time) * 1000.0

    if not success or parsed is None:
        # Failure case: Do NOT convert to empty resource list!
        meta = {
            "stage": "classification",
            "model": model,
            "stage1_status": "error",
            "stage1_error": last_err or "Unknown API failure after retries",
            "definitions_version": RESOURCE_DEFINITIONS_VERSION,
            "latency_ms": latency_ms,
            "retries": retries_used,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "probabilities": {},
            "raw_response": None
        }
        _LAST_CLASSIFICATION_META = meta
        return None, meta

    # Success case: Parse required resources and probabilities
    required_resources: List[str] = []
    probabilities: Dict[str, float] = {}

    for k in RESOURCE_COLUMNS:
        v = parsed.get(k, 0)
        req = 0
        prob_req = 0.0
        if isinstance(v, dict):
            req = int(v.get("required", 0))
            if "probability" in v:
                prob_req = float(v["probability"])
            elif "confidence" in v or "conf" in v:
                conf = float(v.get("confidence", v.get("conf", 0.9 if req == 1 else 0.1)))
                prob_req = conf if req == 1 else (1.0 - conf)
            else:
                prob_req = 1.0 if req == 1 else 0.0
        elif isinstance(v, (int, float)):
            req = 1 if v >= 0.5 else 0
            prob_req = float(v)
        elif isinstance(v, bool):
            req = 1 if v else 0
            prob_req = 1.0 if v else 0.0

        probabilities[k] = round(prob_req, 4)
        if req == 1:
            required_resources.append(k)

    meta = {
        "stage": "classification",
        "model": model,
        "stage1_status": "ok",
        "stage1_error": None,
        "definitions_version": RESOURCE_DEFINITIONS_VERSION,
        "latency_ms": latency_ms,
        "retries": retries_used,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
        "probabilities": probabilities,
        "raw_response": parsed
    }
    _LAST_CLASSIFICATION_META = meta
    return required_resources, meta

def classify(scenario: str) -> List[str]:
    """
    Swappable Stage 1 signature:
    classify(scenario: str) -> list[str]
    Raises Stage1ClassifierError on failure to ensure errors are never converted to empty lists.
    """
    resources, meta = classify_detailed(scenario)
    if meta.get("stage1_status") != "ok" or resources is None:
        raise Stage1ClassifierError(f"Stage 1 LLM classification failed: {meta.get('stage1_error')}")
    return resources
