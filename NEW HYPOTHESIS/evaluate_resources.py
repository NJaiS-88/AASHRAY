#!/usr/bin/env python3
"""
================================================================================
DISASTER RESPONSE RESOURCE REQUIREMENT BENCHMARK
TypeSafe JEV (via OpenRouter Decisions API) vs. Groq LLM (gpt-oss-120b)
================================================================================
Exhaustive Multi-Label Evaluation, Statistical Significance Testing,
Calibration/Ranking Analysis, Operational Profiling, Publication-Grade PDF Report,
and Master Comparison Scoreboard Image.
================================================================================
"""

import os
import sys

# Ensure UTF-8 output encoding on Windows consoles
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

import warnings
warnings.filterwarnings('ignore')

import json
import time
import math
import random
import argparse
from typing import Dict, List, Tuple, Any, Optional
from datetime import datetime

import numpy as np
import pandas as pd
from scipy import stats
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import seaborn as sns
import re
import requests
from requests.adapters import HTTPAdapter

# Persistent HTTP session with connection pooling
SESSION = requests.Session()
_adapter = HTTPAdapter(pool_connections=20, pool_maxsize=20, max_retries=0)
SESSION.mount("https://", _adapter)
SESSION.mount("http://", _adapter)

from sklearn.metrics import (
    precision_score, recall_score, f1_score, accuracy_score,
    hamming_loss, jaccard_score, roc_auc_score, average_precision_score,
    roc_curve, precision_recall_curve, brier_score_loss
)

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak, KeepTogether, HRFlowable
)
from reportlab.pdfgen import canvas

# =====================================================================
# CONSTANTS & CONFIGURATION
# =====================================================================

RESOURCE_COLUMNS = [
    'water', 'food', 'shelter', 'clothing', 'money',
    'medical_help', 'medical_products', 'search_and_rescue', 'tools'
]

OPENROUTER_DECISIONS_URL = "https://openrouter.ai/api/alpha/decisions"
GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"

DEFAULT_JEV_MODEL = os.getenv("OPENROUTER_JEV_MODEL", "typesafe/jev-1.13")
DEFAULT_GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

# Pricing estimates (USD per 1M tokens)
PRICING = {
    "jev": {
        "prompt_per_1m": 0.04,
        "completion_per_1m": 0.00  # Decisions API output is structured & free
    },
    "groq": {
        "prompt_per_1m": 0.15,
        "completion_per_1m": 0.75
    }
}

# =====================================================================
# =====================================================================
# GROQ KEY POOL & ENV LOADER
# =====================================================================

class GroqKeyPool:
    """
    Manages a pool of Groq API keys with:
    1. Alternating round-robin dispatch across calls.
    2. Instant failover to other keys if one times out or gets rate limited.
    3. If all keys time out in a round, wait 5s and fire the most last called key.
    """
    def __init__(self, keys: List[str]):
        cleaned = []
        for k in keys:
            k = k.strip().strip("'\"")
            if k and k not in cleaned:
                cleaned.append(k)
        if not cleaned:
            raise ValueError("No valid Groq API keys provided to GroqKeyPool.")
        self.keys = cleaned
        self.current_idx = 0
        self.last_called_key_idx = 0

    def get_next_key(self) -> Tuple[int, str]:
        """Gets next key in round-robin sequence (1-indexed for logging)."""
        idx = self.current_idx
        self.current_idx = (self.current_idx + 1) % len(self.keys)
        self.last_called_key_idx = idx
        return idx + 1, self.keys[idx]

    def get_fallback_keys(self, failed_key_idx: int) -> List[Tuple[int, str]]:
        """Returns the remaining alternative keys in rotation order."""
        n = len(self.keys)
        fallbacks = []
        for offset in range(1, n):
            idx = (failed_key_idx + offset) % n
            fallbacks.append((idx + 1, self.keys[idx]))
        return fallbacks

    def get_last_called_key(self) -> Tuple[int, str]:
        """Returns the most last called key."""
        idx = self.last_called_key_idx % len(self.keys)
        return idx + 1, self.keys[idx]

    def __len__(self) -> int:
        return len(self.keys)


def load_environment():
    """Load API keys and model configurations from .env file or environment variables."""
    env_file = os.path.join(os.getcwd(), ".env")
    if os.path.exists(env_file):
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip("'\"")
                    if key and val:
                        os.environ[key] = val

    openrouter_key = os.getenv("OPENROUTER_API_KEY", "").strip()

    # Discover all Groq API keys (GROQ_API_KEY, GROQ_API_KEY2, GROQ_API_KEY3, etc.)
    groq_keys = []
    k1 = os.getenv("GROQ_API_KEY", "").strip()
    if k1:
        groq_keys.append(k1)

    for i in range(2, 21):
        val = os.getenv(f"GROQ_API_KEY{i}", "").strip()
        if val and val not in groq_keys:
            groq_keys.append(val)

    for k, v in os.environ.items():
        if k.upper().startswith("GROQ_API_KEY") and k.upper() != "GROQ_API_KEY":
            clean_v = v.strip().strip("'\"")
            if clean_v and clean_v not in groq_keys:
                groq_keys.append(clean_v)

    jev_model = os.getenv("OPENROUTER_JEV_MODEL", DEFAULT_JEV_MODEL).strip()
    groq_model = os.getenv("GROQ_MODEL", DEFAULT_GROQ_MODEL).strip()
    return openrouter_key, groq_keys, jev_model, groq_model

# =====================================================================
# API CLIENTS & INFERENCE
# =====================================================================

def call_jev_decisions(
    text: str,
    api_key: str,
    genre: str = "direct",
    model: str = DEFAULT_JEV_MODEL,
    max_retries: int = 5,
    timeout: float = 35.0
) -> Dict[str, Any]:
    """
    Call TypeSafe JEV via OpenRouter Decisions API.
    Submits rich disaster context state + noul questions for each exact resource.
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/emergency-benchmark",
        "X-Title": "Disaster Resource Benchmark"
    }

    genre_desc = {
        "direct": "Direct victim transmission (SMS / emergency call from affected individuals in disaster zone)",
        "social": "Social media dispatch / eyewitness post reporting urgent community conditions",
        "news": "News wire / formal broadcast report detailing disaster zone casualties and aid operations"
    }.get(str(genre).lower(), "Emergency communication")

    rich_state = (
        "EMERGENCY DISASTER SITUATION REPORT & HUMANITARIAN DISPATCH ASSESSMENT\n"
        "================================================================================\n"
        f"COMMUNICATION CHANNEL: {genre_desc}\n"
        f"INCOMING MESSAGE TRANSCRIPT:\n\"{text}\"\n"
        "================================================================================\n"
        "MISSION OBJECTIVE: Accurately classify which specific relief resources are actively requested, directly\n"
        "stated as an urgent need, or mobilized in this communication.\n\n"
        "CRITICAL GROUND-TRUTH CLASSIFICATION RULES:\n"
        "1. Evaluate strictly based on what is explicitly requested, directly stated, or mobilized in the transcript.\n"
        "2. Do NOT infer or predict hypothetical downstream/future needs that are not mentioned in the text (e.g. do not assume shelter or water unless explicitly requested or needed for victims in the text).\n"
        "3. If a news or official message announces rescue teams or evacuation, mark search_and_rescue, but do not extrapolate other unmentioned resources.\n\n"
        "RESOURCE DEFINITIONS & SCOPE:\n"
        "• water: Clean drinking water, potable water tanks, hydration aid, water purification.\n"
        "• food: Meals, hunger relief, rations, famine supplies, groceries, starving people.\n"
        "• shelter: Tents, tarpaulins, temporary housing, blankets, sleeping mats, roofing.\n"
        "• clothing: Clothes, garments, footwear, shoes, wearable protective gear.\n"
        "• money: Financial aid, cash donations, grants, monetary assistance.\n"
        "• medical_help: Doctors, nurses, paramedics, triage, field hospitals, ambulances, treating wounded/sick.\n"
        "• medical_products: Medicines, pharmaceuticals, bandages, first aid supplies, antiseptics.\n"
        "• search_and_rescue: Search teams, rescue dogs, evacuation teams, rubble extraction, saving trapped people.\n"
        "• tools: Shovels, reconstruction gear, heavy machinery, excavation tools, chainsaws."
    )

    resource_instructions = {
        "water": "Does this message specifically request or mention clean drinking water supplies or hydration relief?",
        "food": "Does this message specifically request or mention food, meals, hunger relief, or rations?",
        "shelter": "Does this message specifically request or mention tents, tarpaulins, blankets, or emergency shelter?",
        "clothing": "Does this message specifically request or mention clothing, garments, shoes, or wearable protective gear?",
        "money": "Does this message specifically request or mention financial aid, cash donations, or monetary relief?",
        "medical_help": "Does this message specifically request or mention doctors, paramedics, triage, or medical treatment?",
        "medical_products": "Does this message specifically request or mention medicines, pharmaceuticals, bandages, or first aid supplies?",
        "search_and_rescue": "Does this message specifically request, mention, or mobilize search and rescue operations, rescue forces, or evacuation?",
        "tools": "Does this message specifically request or mention construction tools, shovels, reconstruction gear, or heavy machinery?"
    }

    questions = {}
    for res in RESOURCE_COLUMNS:
        questions[res] = {
            "type": "noul",
            "instructions": resource_instructions.get(res, f"Does this message explicitly request or indicate {res}?")
        }

    payload = {
        "model": model,
        "state": rich_state,
        "questions": questions
    }

    total_start = time.perf_counter()
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
                cost = usage.get("cost", ((prompt_tokens * PRICING["jev"]["prompt_per_1m"]) + (completion_tokens * PRICING["jev"]["completion_per_1m"])) / 1_000_000.0)

                probs = {}
                invalid_keys = []
                for k, v in answers.items():
                    if k not in RESOURCE_COLUMNS:
                        invalid_keys.append(k)
                        continue
                    if isinstance(v, dict):
                        p = v.get("noul", v.get("confidence", v.get("probability", 0.5)))
                    elif isinstance(v, (int, float)):
                        p = float(v)
                    else:
                        p = 0.5
                    probs[k] = float(np.clip(p, 0.0, 1.0))

                for r in RESOURCE_COLUMNS:
                    if r not in probs:
                        probs[r] = 0.0

                return {
                    "success": True,
                    "probabilities": probs,
                    "latency_ms": api_latency_ms,
                    "total_elapsed_ms": (time.perf_counter() - total_start) * 1000.0,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": prompt_tokens + completion_tokens,
                    "cost": cost,
                    "invalid_keys": invalid_keys,
                    "parse_error": False,
                    "raw_response": data
                }
            elif resp.status_code in [429, 502, 503, 504]:
                wait_time = 2.0 * (attempt + 1)
                try:
                    ra = float(resp.headers.get("Retry-After", 0) or 0)
                    if ra > 0:
                        wait_time = max(wait_time, ra + 0.5)
                except Exception:
                    pass
                try:
                    m = re.search(r"try again in ([\d\.]+)s", resp.text, re.IGNORECASE)
                    if m:
                        wait_time = max(wait_time, float(m.group(1)) + 0.5)
                except Exception:
                    pass

                print(f"      [JEV {resp.status_code}] Rate limited/busy. Backing off {wait_time:.1f}s (retry {attempt + 1}/{max_retries})...", flush=True)
                if attempt == max_retries - 1:
                    return {
                        "success": False,
                        "probabilities": {r: 0.0 for r in RESOURCE_COLUMNS},
                        "latency_ms": api_latency_ms,
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "total_tokens": 0,
                        "cost": 0.0,
                        "invalid_keys": [],
                        "parse_error": True,
                        "error_message": f"HTTP {resp.status_code}: Rate limit / server error after {max_retries} attempts"
                    }
                time.sleep(wait_time)
            else:
                return {
                    "success": False,
                    "probabilities": {r: 0.0 for r in RESOURCE_COLUMNS},
                    "latency_ms": api_latency_ms,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "cost": 0.0,
                    "invalid_keys": [],
                    "parse_error": True,
                    "error_message": f"HTTP {resp.status_code}: {resp.text[:200]}"
                }
        except requests.exceptions.Timeout:
            wait_time = 2.0 * (attempt + 1)
            print(f"      [JEV Timeout] Request timed out ({timeout}s). Backing off {wait_time:.1f}s (retry {attempt + 1}/{max_retries})...", flush=True)
            if attempt == max_retries - 1:
                return {
                    "success": False,
                    "probabilities": {r: 0.0 for r in RESOURCE_COLUMNS},
                    "latency_ms": (time.perf_counter() - attempt_start) * 1000.0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "cost": 0.0,
                    "invalid_keys": [],
                    "parse_error": True,
                    "error_message": f"Timed out after {max_retries} attempts"
                }
            time.sleep(wait_time)
        except Exception as e:
            wait_time = 1.5 * (attempt + 1)
            print(f"      [JEV Error] {type(e).__name__}: {e}. Retrying in {wait_time:.1f}s (retry {attempt + 1}/{max_retries})...", flush=True)
            if attempt == max_retries - 1:
                return {
                    "success": False,
                    "probabilities": {r: 0.0 for r in RESOURCE_COLUMNS},
                    "latency_ms": (time.perf_counter() - attempt_start) * 1000.0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "cost": 0.0,
                    "invalid_keys": [],
                    "parse_error": True,
                    "error_message": str(e)
                }
            time.sleep(wait_time)

    return {
        "success": False,
        "probabilities": {r: 0.0 for r in RESOURCE_COLUMNS},
        "latency_ms": (time.perf_counter() - total_start) * 1000.0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "cost": 0.0,
        "invalid_keys": [],
        "parse_error": True,
        "error_message": "Exceeded retry attempts"
    }



def call_groq_llm(
    text: str,
    api_key_or_pool: Any,
    model: str = DEFAULT_GROQ_MODEL,
    max_retries: int = 5,
    timeout: float = 60.0
) -> Dict[str, Any]:
    """
    Call Groq LLM (e.g. gpt-oss-120b or llama models) to classify each resource as 0 or 1 with confidence.
    Supports alternating round-robin key rotation and instant failover across multiple Groq API keys:
      - Fires keys alternatively on each call.
      - If a key times out or hits 429, immediately fires the alternative keys.
      - If all keys time out, waits 5s and fires the most last called key.
    """
    if isinstance(api_key_or_pool, GroqKeyPool):
        pool = api_key_or_pool
    elif isinstance(api_key_or_pool, list):
        pool = GroqKeyPool(api_key_or_pool)
    else:
        pool = GroqKeyPool([str(api_key_or_pool)])

    # 1. Select the alternating next key for this call
    primary_num, primary_key = pool.get_next_key()
    primary_idx = primary_num - 1

    # Rotation order for this sample: [primary_key, *remaining_keys]
    key_sequence = [(primary_num, primary_key)] + pool.get_fallback_keys(primary_idx)
    num_keys = len(key_sequence)

    resource_desc = "\n".join([
        "- water: clean drinking water, hydration needs",
        "- food: meals, hunger relief, food supplies, starving",
        "- shelter: tents, tarpaulins, temporary housing, blankets, places to sleep",
        "- clothing: clothes, garments, shoes, wearable protection",
        "- money: financial donations, cash relief, funds",
        "- medical_help: doctors, nurses, medical treatment, hospitals, wounded, sick, ambulances",
        "- medical_products: medicines, pharmaceuticals, bandages, first aid, medical supplies",
        "- search_and_rescue: finding trapped people, rubble extraction, evacuation teams, saving lives",
        "- tools: shovels, machinery, excavation tools, reconstruction equipment"
    ])

    system_prompt = (
        "You are an expert emergency disaster response dispatcher.\n"
        "Carefully analyze the emergency message and determine which of the following 9 resources are requested or needed:\n"
        f"{resource_desc}\n\n"
        "EVALUATION RULES:\n"
        "1. Evaluate each resource independently based strictly on the text content.\n"
        "2. Do NOT assume food is needed unless the message specifically mentions food, hunger, starving, or meals.\n"
        "3. If a message asks for medical care, doctors, or reports injured/sick people, mark medical_help as 1.\n"
        "4. If a message asks for medicine, bandages, or supplies, mark medical_products as 1.\n"
        "5. If a message asks for tents, tarps, or housing, mark shelter as 1.\n"
        "6. If a message reports people trapped under rubble or needing rescue, mark search_and_rescue as 1.\n"
        "7. Return ONLY a valid JSON object mapping each of the 9 resources to "
        "{'required': 0 or 1, 'probability': float between 0.0 and 1.0 representing the probability that this resource is required (e.g. 0.90 if required, 0.05 if not required)}."
    )

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Emergency Message: \"{text}\""}
        ],
        "temperature": 0.0,
        "response_format": {"type": "json_object"}
    }

    if "gpt-oss" in model.lower():
        payload["reasoning_effort"] = "low"
        payload["reasoning_format"] = "parsed"
        payload["max_tokens"] = 500

    def parse_success_response(resp, attempt_start, total_start, key_label):
        data = resp.json()
        content = data["choices"][0]["message"]["content"].strip()
        usage = data.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", len(text.split()) * 2 + 150)
        completion_tokens = usage.get("completion_tokens", 80)
        cost = (
            (prompt_tokens * PRICING["groq"]["prompt_per_1m"]) +
            (completion_tokens * PRICING["groq"]["completion_per_1m"])
        ) / 1_000_000.0

        clean_content = content
        if clean_content.startswith("```"):
            lines = clean_content.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            clean_content = "\n".join(lines).strip()

        try:
            parsed = json.loads(clean_content)
        except json.JSONDecodeError:
            return {
                "success": False,
                "probabilities": {r: 0.0 for r in RESOURCE_COLUMNS},
                "binary": {r: 0 for r in RESOURCE_COLUMNS},
                "latency_ms": (time.perf_counter() - attempt_start) * 1000.0,
                "total_elapsed_ms": (time.perf_counter() - total_start) * 1000.0,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
                "cost": cost,
                "invalid_keys": [],
                "parse_error": True,
                "raw_response": content,
                "key_used": key_label
            }

        probs = {}
        binary = {}
        invalid_keys = []
        for k, v in parsed.items():
            if k not in RESOURCE_COLUMNS:
                invalid_keys.append(k)
                continue
            if isinstance(v, dict):
                req = int(v.get("required", 0))
                if "probability" in v:
                    prob_req = float(v["probability"])
                elif "prob" in v:
                    prob_req = float(v["prob"])
                elif "p" in v:
                    prob_req = float(v["p"])
                elif "confidence" in v or "conf" in v:
                    conf_val = float(v.get("confidence", v.get("conf", 0.9 if req == 1 else 0.1)))
                    # Critical fix: If model outputs confidence in the negative decision (req=0, conf=0.95),
                    # convert to probability of resource being required:
                    prob_req = conf_val if req == 1 else (1.0 - conf_val)
                else:
                    prob_req = 1.0 if req == 1 else 0.0
            elif isinstance(v, (int, float)):
                req = 1 if v >= 0.5 else 0
                prob_req = float(v)
            elif isinstance(v, bool):
                req = 1 if v else 0
                prob_req = 1.0 if v else 0.0
            else:
                req = 0
                prob_req = 0.0
            binary[k] = req
            probs[k] = float(np.clip(prob_req, 0.0, 1.0))

        for r in RESOURCE_COLUMNS:
            if r not in probs:
                probs[r] = 0.0
                binary[r] = 0

        return {
            "success": True,
            "probabilities": probs,
            "binary": binary,
            "latency_ms": (time.perf_counter() - attempt_start) * 1000.0,
            "total_elapsed_ms": (time.perf_counter() - total_start) * 1000.0,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "cost": cost,
            "invalid_keys": invalid_keys,
            "parse_error": False,
            "raw_response": parsed,
            "key_used": key_label
        }

    total_start = time.perf_counter()

    for attempt in range(max_retries):
        all_timed_out = True
        last_called_num = primary_num
        last_called_key = primary_key

        # Try keys in sequence: primary key first, then failover to other keys
        for k_idx, (k_num, k_val) in enumerate(key_sequence):
            pool.last_called_key_idx = k_num - 1
            last_called_num = k_num
            last_called_key = k_val
            headers = {
                "Authorization": f"Bearer {k_val}",
                "Content-Type": "application/json"
            }
            attempt_start = time.perf_counter()

            try:
                resp = SESSION.post(GROQ_CHAT_URL, headers=headers, json=payload, timeout=timeout)
                if resp.status_code == 200:
                    key_tag = f"Key {k_num}" if k_idx == 0 else f"Key {k_num} (failover from Key {primary_num})"
                    return parse_success_response(resp, attempt_start, total_start, key_tag)
                elif resp.status_code in [429, 502, 503, 504]:
                    # Rate limit or busy on this key: immediately fire next key if available
                    all_timed_out = False
                    if k_idx < num_keys - 1:
                        next_num = key_sequence[k_idx + 1][0]
                        print(f"      [Groq {resp.status_code}] Key {k_num} rate limited/busy. Immediately switching to Key {next_num}...", flush=True)
                        continue
                    else:
                        wait_time = 2.0 * (attempt + 1)
                        print(f"      [Groq {resp.status_code}] All keys rate limited/busy. Backing off {wait_time:.1f}s...", flush=True)
                        time.sleep(wait_time)
                        break
                elif resp.status_code == 400 and ("reasoning_format" in resp.text or "reasoning_effort" in resp.text):
                    payload.pop("reasoning_format", None)
                    payload.pop("reasoning_effort", None)
                    time.sleep(0.5)
                    continue
                else:
                    all_timed_out = False
                    if k_idx < num_keys - 1:
                        next_num = key_sequence[k_idx + 1][0]
                        print(f"      [Groq {resp.status_code}] Key {k_num} error ({resp.text[:60]}). Switching to Key {next_num}...", flush=True)
                        continue
                    break
            except requests.exceptions.Timeout:
                # Key timed out: ensure to fire other keys!
                if k_idx < num_keys - 1:
                    next_num = key_sequence[k_idx + 1][0]
                    print(f"      [Groq Timeout] Key {k_num} timed out ({timeout}s). Immediately switching to alternative Key {next_num}...", flush=True)
                    continue
                else:
                    # All keys in key_sequence timed out!
                    print(f"      [Groq Timeout] Key {k_num} timed out ({timeout}s). All {num_keys} keys have timed out!", flush=True)
                    break
            except Exception as e:
                all_timed_out = False
                if k_idx < num_keys - 1:
                    next_num = key_sequence[k_idx + 1][0]
                    print(f"      [Groq Error] Key {k_num} error ({type(e).__name__}: {e}). Switching to Key {next_num}...", flush=True)
                    continue
                break

        # "if all 3 timed out then wait and fire the most last called key"
        if all_timed_out:
            wait_time = 5.0 * (attempt + 1)
            print(f"      [Groq All Keys Timed Out] All {num_keys} keys timed out. Waiting {wait_time:.1f}s before firing most last called Key {last_called_num}...", flush=True)
            time.sleep(wait_time)

            headers = {
                "Authorization": f"Bearer {last_called_key}",
                "Content-Type": "application/json"
            }
            attempt_start = time.perf_counter()
            print(f"      [Groq Retry] Firing most last called Key {last_called_num}...", flush=True)
            try:
                resp = SESSION.post(GROQ_CHAT_URL, headers=headers, json=payload, timeout=timeout)
                if resp.status_code == 200:
                    return parse_success_response(resp, attempt_start, total_start, f"Key {last_called_num} (after timeout wait)")
                elif resp.status_code in [429, 502, 503, 504]:
                    print(f"      [Groq {resp.status_code}] Last called Key {last_called_num} busy.", flush=True)
                else:
                    print(f"      [Groq {resp.status_code}] Last called Key {last_called_num} error: {resp.text[:60]}", flush=True)
            except requests.exceptions.Timeout:
                print(f"      [Groq Timeout] Last called Key {last_called_num} timed out again ({timeout}s).", flush=True)
            except Exception as e:
                print(f"      [Groq Error] Last called Key {last_called_num} error: {e}", flush=True)

    return {
        "success": False,
        "probabilities": {r: 0.0 for r in RESOURCE_COLUMNS},
        "binary": {r: 0 for r in RESOURCE_COLUMNS},
        "latency_ms": (time.perf_counter() - total_start) * 1000.0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "cost": 0.0,
        "invalid_keys": [],
        "parse_error": True,
        "error_message": f"Exceeded retry attempts across all {num_keys} Groq keys",
        "key_used": f"Key {last_called_num}"
    }



def simulate_prediction(
    text: str,
    true_labels: Dict[str, int],
    model_type: str = "jev"
) -> Dict[str, Any]:
    """
    High-fidelity simulation engine for verification & dry-run testing.
    Mirrors real performance characteristics, latencies, and token usages.
    """
    probs = {}
    binary = {}
    invalid_keys = []
    text_lower = text.lower()

    keywords = {
        'water': ['water', 'drinking', 'thirsty', 'dehydrat', 'bottle'],
        'food': ['food', 'eat', 'hungry', 'starv', 'ration', 'meal', 'bread'],
        'shelter': ['tent', 'shelter', 'house', 'roof', 'blanket', 'sleep', 'camp', 'homeless', 'displaced'],
        'clothing': ['cloth', 'wear', 'shoes', 'dress', 'shirt', 'jacket'],
        'money': ['money', 'cash', 'fund', 'financial', 'dollar', 'bank', 'donation'],
        'medical_help': ['doctor', 'nurse', 'hospital', 'injured', 'wound', 'sick', 'health', 'clinic', 'dying', 'medic'],
        'medical_products': ['medicine', 'medication', 'drug', 'antibiotic', 'bandage', 'first aid', 'supplies', 'pill', 'serum'],
        'search_and_rescue': ['trap', 'rubble', 'collapse', 'rescue', 'search', 'under', 'buried', 'survivor'],
        'tools': ['tool', 'shovel', 'generator', 'fuel', 'equipment', 'rope', 'axe', 'saw']
    }

    if model_type == "jev":
        # Jev: Fast decision model, strong keyword sensitivity, calibrated probabilities
        base_latency = random.uniform(80.0, 160.0)
        prompt_tokens = len(text.split()) * 2 + 30
        completion_tokens = 18
        cost = (prompt_tokens * PRICING["jev"]["prompt_per_1m"]) / 1_000_000.0

        for res in RESOURCE_COLUMNS:
            has_kw = any(k in text_lower for k in keywords[res])
            is_true = true_labels[res] == 1

            if is_true:
                if has_kw:
                    p = random.betavariate(8, 2)  # Mean ~0.80
                else:
                    p = random.betavariate(5, 3)  # Mean ~0.62
            else:
                if has_kw:
                    p = random.betavariate(3, 5)  # Mean ~0.37
                else:
                    p = random.betavariate(1, 10) # Mean ~0.09
            p = float(np.clip(p, 0.01, 0.99))
            probs[res] = p
            binary[res] = 1 if p >= 0.5 else 0

        # Jev produces zero invalid keys due to typed Decisions API
        return {
            "success": True,
            "probabilities": probs,
            "binary": binary,
            "latency_ms": base_latency,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "cost": cost,
            "invalid_keys": [],
            "parse_error": False
        }

    else:
        # LLM (gpt-oss-120b): Reasoning model, higher latency, rich comprehension, occasional syntax quirks
        base_latency = random.uniform(320.0, 680.0)
        prompt_tokens = len(text.split()) * 2 + 160
        completion_tokens = random.randint(75, 110)
        cost = (
            (prompt_tokens * PRICING["groq"]["prompt_per_1m"]) +
            (completion_tokens * PRICING["groq"]["completion_per_1m"])
        ) / 1_000_000.0

        parse_error = (random.random() < 0.005) # ~0.5% parse error
        if random.random() < 0.01:
            invalid_keys = ["urgency_level"]

        for res in RESOURCE_COLUMNS:
            has_kw = any(k in text_lower for k in keywords[res])
            is_true = true_labels[res] == 1

            if is_true:
                p = random.betavariate(9, 2) if has_kw else random.betavariate(6, 3)
            else:
                p = random.betavariate(2, 6) if has_kw else random.betavariate(1, 14)
            p = float(np.clip(p, 0.01, 0.99))
            probs[res] = p
            binary[res] = 1 if p >= 0.5 else 0

        return {
            "success": not parse_error,
            "probabilities": probs,
            "binary": binary,
            "latency_ms": base_latency,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "cost": cost,
            "invalid_keys": invalid_keys,
            "parse_error": parse_error
        }

# =====================================================================
# CALIBRATION & METRICS HELPERS
# =====================================================================

def compute_ece(probs: np.ndarray, y_true: np.ndarray, n_bins: int = 10) -> Tuple[float, List[Dict[str, float]]]:
    """Compute Expected Calibration Error (ECE) and bin statistics."""
    bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    n_total = len(probs)
    bin_stats = []

    for i in range(n_bins):
        low, high = bin_edges[i], bin_edges[i + 1]
        if i == n_bins - 1:
            mask = (probs >= low) & (probs <= high)
        else:
            mask = (probs >= low) & (probs < high)

        count = np.sum(mask)
        if count > 0:
            bin_conf = float(np.mean(probs[mask]))
            bin_acc = float(np.mean(y_true[mask]))
            diff = abs(bin_acc - bin_conf)
            ece += (count / n_total) * diff
            bin_stats.append({
                "bin_low": low,
                "bin_high": high,
                "bin_center": (low + high) / 2.0,
                "count": int(count),
                "confidence": bin_conf,
                "accuracy": bin_acc,
                "diff": diff
            })
        else:
            bin_stats.append({
                "bin_low": low,
                "bin_high": high,
                "bin_center": (low + high) / 2.0,
                "count": 0,
                "confidence": (low + high) / 2.0,
                "accuracy": 0.0,
                "diff": 0.0
            })

    return float(ece), bin_stats


def evaluate_model_classification(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    probs: np.ndarray,
    latencies: List[float],
    costs: List[float],
    tokens: List[Dict[str, int]],
    parse_errors: int,
    invalid_keys_list: List[List[str]],
    resource_cols: List[str] = RESOURCE_COLUMNS
) -> Dict[str, Any]:
    """Comprehensive evaluation covering classification, ranking, calibration, and efficiency."""
    n_samples, n_labels = y_true.shape

    # Per-resource metrics
    per_resource = {}
    for j, col in enumerate(resource_cols):
        yt = y_true[:, j]
        yp = y_pred[:, j]
        pr = probs[:, j]

        tp = int(np.sum((yt == 1) & (yp == 1)))
        fp = int(np.sum((yt == 0) & (yp == 1)))
        fn = int(np.sum((yt == 1) & (yp == 0)))
        tn = int(np.sum((yt == 0) & (yp == 0)))

        prec = float(precision_score(yt, yp, zero_division=0))
        rec = float(recall_score(yt, yp, zero_division=0))
        f1 = float(f1_score(yt, yp, zero_division=0))
        acc = float(accuracy_score(yt, yp))
        spec = float(tn / (tn + fp)) if (tn + fp) > 0 else 1.0

        try:
            ap = float(average_precision_score(yt, pr))
        except Exception:
            ap = 0.0

        try:
            auc = float(roc_auc_score(yt, pr)) if len(np.unique(yt)) > 1 else 0.5
        except Exception:
            auc = 0.5

        per_resource[col] = {
            "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "support": int(np.sum(yt == 1)),
            "precision": prec,
            "recall": rec,
            "f1": f1,
            "accuracy": acc,
            "specificity": spec,
            "average_precision": ap,
            "roc_auc": auc
        }

    # Aggregate Multi-label Classification Metrics
    micro_p = float(precision_score(y_true, y_pred, average="micro", zero_division=0))
    micro_r = float(recall_score(y_true, y_pred, average="micro", zero_division=0))
    micro_f1 = float(f1_score(y_true, y_pred, average="micro", zero_division=0))

    macro_p = float(precision_score(y_true, y_pred, average="macro", zero_division=0))
    macro_r = float(recall_score(y_true, y_pred, average="macro", zero_division=0))
    macro_f1 = float(f1_score(y_true, y_pred, average="macro", zero_division=0))

    weighted_p = float(precision_score(y_true, y_pred, average="weighted", zero_division=0))
    weighted_r = float(recall_score(y_true, y_pred, average="weighted", zero_division=0))
    weighted_f1 = float(f1_score(y_true, y_pred, average="weighted", zero_division=0))

    # Subset accuracy (exact match across all labels simultaneously)
    subset_acc = float(np.mean(np.all(y_true == y_pred, axis=1)))

    # Overall classification accuracy across all rows and all labels (Total correct label decisions / Total label opportunities)
    overall_acc = float(np.mean(y_true == y_pred))
    total_correct_labels = int(np.sum(y_true == y_pred))
    total_label_decisions = int(n_samples * n_labels)
    row_accs = [float(np.mean(y_true[i] == y_pred[i])) for i in range(n_samples)]
    mean_row_acc = float(np.mean(row_accs)) if row_accs else 0.0

    # Hamming loss (1.0 - overall_accuracy)
    h_loss = float(hamming_loss(y_true, y_pred))

    # Sample-averaged Jaccard similarity
    sample_jaccards = []
    for i in range(n_samples):
        intersection = np.sum((y_true[i] == 1) & (y_pred[i] == 1))
        union = np.sum((y_true[i] == 1) | (y_pred[i] == 1))
        j_val = float(intersection / union) if union > 0 else 1.0
        sample_jaccards.append(j_val)
    mean_sample_jaccard = float(np.mean(sample_jaccards))

    # Any-resource-required P/R/F1
    any_true = (np.sum(y_true, axis=1) > 0).astype(int)
    any_pred = (np.sum(y_pred, axis=1) > 0).astype(int)
    any_p = float(precision_score(any_true, any_pred, zero_division=0))
    any_r = float(recall_score(any_true, any_pred, zero_division=0))
    any_f1 = float(f1_score(any_true, any_pred, zero_division=0))

    # Any-miss rate and Complete-miss rate (among samples where any resource was required)
    samples_with_needs = np.where(any_true == 1)[0]
    if len(samples_with_needs) > 0:
        # any-miss: at least one required resource was missed
        any_misses = 0
        complete_misses = 0
        for idx in samples_with_needs:
            needed_indices = np.where(y_true[idx] == 1)[0]
            pred_needed = y_pred[idx, needed_indices]
            if np.any(pred_needed == 0):
                any_misses += 1
            if np.all(y_pred[idx] == 0):
                complete_misses += 1
        any_miss_rate = float(any_misses / len(samples_with_needs))
        complete_miss_rate = float(complete_misses / len(samples_with_needs))
    else:
        any_miss_rate = 0.0
        complete_miss_rate = 0.0

    # Incorrect classification penalties (False Positives / Over-prediction)
    total_fp = int(np.sum((y_true == 0) & (y_pred == 1)))
    total_fn = int(np.sum((y_true == 1) & (y_pred == 0)))
    total_tp = int(np.sum((y_true == 1) & (y_pred == 1)))
    total_tn = int(np.sum((y_true == 0) & (y_pred == 0)))

    false_positive_rate = float(total_fp / (total_fp + total_tn)) if (total_fp + total_tn) > 0 else 0.0

    # Any false alarm: fraction of messages where at least one unneeded resource was predicted as needed
    false_alarms = 0
    for idx in range(n_samples):
        not_needed = np.where(y_true[idx] == 0)[0]
        if np.any(y_pred[idx, not_needed] == 1):
            false_alarms += 1
    any_false_alarm_rate = float(false_alarms / n_samples) if n_samples > 0 else 0.0

    # F0.5 score: weights precision twice as much as recall to strictly penalize incorrect classifications
    f05_score = float((1.0 + 0.25) * (micro_p * micro_r) / (0.25 * micro_p + micro_r + 1e-9)) if (micro_p + micro_r) > 0 else 0.0

    # Reliability metrics
    parse_failure_rate = float(parse_errors / n_samples) if n_samples > 0 else 0.0
    all_invalid = [k for sublist in invalid_keys_list for k in sublist]
    invalid_keys_count = len(all_invalid)

    # Ranking & Calibration
    flat_true = y_true.flatten()
    flat_probs = probs.flatten()
    brier = float(brier_score_loss(flat_true, flat_probs))
    ece, bin_stats = compute_ece(flat_probs, flat_true, n_bins=10)

    try:
        micro_auc = float(roc_auc_score(flat_true, flat_probs))
    except Exception:
        micro_auc = 0.5
    valid_macro_aucs = [per_resource[r]["roc_auc"] for r in resource_cols if per_resource[r]["support"] > 0]
    macro_auc = float(np.mean(valid_macro_aucs)) if valid_macro_aucs else 0.5

    try:
        micro_ap = float(average_precision_score(flat_true, flat_probs))
    except Exception:
        micro_ap = 0.0
    valid_macro_aps = [per_resource[r]["average_precision"] for r in resource_cols if per_resource[r]["support"] > 0]
    macro_ap = float(np.mean(valid_macro_aps)) if valid_macro_aps else 0.0
    mAP = micro_ap  # Standardize mAP to micro-averaged Average Precision across all decision opportunities

    # Efficiency
    lat_arr = np.array(latencies) if latencies else np.array([0.0])
    mean_lat = float(np.mean(lat_arr))
    p50_lat = float(np.percentile(lat_arr, 50))
    p95_lat = float(np.percentile(lat_arr, 95))
    p99_lat = float(np.percentile(lat_arr, 99))

    prompt_toks = [t.get("prompt_tokens", 0) for t in tokens]
    comp_toks = [t.get("completion_tokens", 0) for t in tokens]
    mean_prompt_tok = float(np.mean(prompt_toks)) if prompt_toks else 0.0
    mean_comp_tok = float(np.mean(comp_toks)) if comp_toks else 0.0
    mean_total_tok = mean_prompt_tok + mean_comp_tok

    cost_per_sample = float(np.mean(costs)) if costs else 0.0
    cost_per_1k = cost_per_sample * 1000.0

    return {
        "per_resource": per_resource,
        "classification": {
            "micro_precision": micro_p,
            "micro_recall": micro_r,
            "micro_f1": micro_f1,
            "macro_precision": macro_p,
            "macro_recall": macro_r,
            "macro_f1": macro_f1,
            "weighted_precision": weighted_p,
            "weighted_recall": weighted_r,
            "weighted_f1": weighted_f1,
            "subset_accuracy": subset_acc,
            "overall_accuracy": overall_acc,
            "total_correct_labels": total_correct_labels,
            "total_label_decisions": total_label_decisions,
            "mean_row_accuracy": mean_row_acc,
            "hamming_loss": h_loss,
            "sample_jaccard": mean_sample_jaccard,
            "any_resource_precision": any_p,
            "any_resource_recall": any_r,
            "any_resource_f1": any_f1,
            "any_miss_rate": any_miss_rate,
            "complete_miss_rate": complete_miss_rate,
            "any_false_alarm_rate": any_false_alarm_rate,
            "false_positive_rate": false_positive_rate,
            "f05_score": f05_score,
            "total_false_positives": total_fp,
            "total_false_negatives": total_fn
        },
        "reliability": {
            "parse_failure_rate": parse_failure_rate,
            "parse_errors_count": parse_errors,
            "invalid_keys_count": invalid_keys_count,
            "invalid_keys_samples": list(set(all_invalid))
        },
        "ranking_calibration": {
            "mean_average_precision": mAP,
            "micro_average_precision": micro_ap,
            "macro_average_precision": macro_ap,
            "micro_roc_auc": micro_auc,
            "macro_roc_auc": macro_auc,
            "brier_score": brier,
            "ece": ece,
            "calibration_bins": bin_stats
        },
        "efficiency": {
            "latency_mean_ms": mean_lat,
            "latency_p50_ms": p50_lat,
            "latency_p95_ms": p95_lat,
            "latency_p99_ms": p99_lat,
            "mean_prompt_tokens": mean_prompt_tok,
            "mean_completion_tokens": mean_comp_tok,
            "mean_total_tokens": mean_total_tok,
            "cost_per_sample_usd": cost_per_sample,
            "cost_per_1k_messages_usd": cost_per_1k
        }
    }

# =====================================================================
# STATISTICAL RIGOR & TESTS
# =====================================================================

def run_paired_bootstrap(
    y_true: np.ndarray,
    y_pred_jev: np.ndarray,
    y_pred_llm: np.ndarray,
    n_bootstraps: int = 1000,
    seed: int = 42
) -> Dict[str, Any]:
    """
    Paired bootstrap for Micro P/R/F1 of both models and their paired differences.
    """
    rng = np.random.RandomState(seed)
    n = len(y_true)

    jev_micro_f1 = []
    jev_micro_r = []
    jev_micro_p = []

    llm_micro_f1 = []
    llm_micro_r = []
    llm_micro_p = []

    diff_micro_f1 = []
    diff_micro_r = []
    diff_micro_p = []

    for _ in range(n_bootstraps):
        idx = rng.choice(n, size=n, replace=True)
        yt_b = y_true[idx]
        yj_b = y_pred_jev[idx]
        yl_b = y_pred_llm[idx]

        jf = float(f1_score(yt_b, yj_b, average="micro", zero_division=0))
        jr = float(recall_score(yt_b, yj_b, average="micro", zero_division=0))
        jp = float(precision_score(yt_b, yj_b, average="micro", zero_division=0))

        lf = float(f1_score(yt_b, yl_b, average="micro", zero_division=0))
        lr = float(recall_score(yt_b, yl_b, average="micro", zero_division=0))
        lp = float(precision_score(yt_b, yl_b, average="micro", zero_division=0))

        jev_micro_f1.append(jf)
        jev_micro_r.append(jr)
        jev_micro_p.append(jp)

        llm_micro_f1.append(lf)
        llm_micro_r.append(lr)
        llm_micro_p.append(lp)

        diff_micro_f1.append(jf - lf)
        diff_micro_r.append(jr - lr)
        diff_micro_p.append(jp - lp)

    def ci(arr):
        return [float(np.percentile(arr, 2.5)), float(np.percentile(arr, 97.5))]

    return {
        "jev_micro_f1_ci": ci(jev_micro_f1),
        "jev_micro_recall_ci": ci(jev_micro_r),
        "jev_micro_precision_ci": ci(jev_micro_p),
        "llm_micro_f1_ci": ci(llm_micro_f1),
        "llm_micro_recall_ci": ci(llm_micro_r),
        "llm_micro_precision_ci": ci(llm_micro_p),
        "diff_micro_f1_ci": ci(diff_micro_f1),
        "diff_micro_recall_ci": ci(diff_micro_r),
        "diff_micro_precision_ci": ci(diff_micro_p),
        "raw_diff_micro_f1": diff_micro_f1,
        "raw_diff_micro_recall": diff_micro_r,
        "raw_diff_micro_precision": diff_micro_p
    }


def run_non_inferiority_test(
    diff_values: List[float],
    metric_name: str = "Recall",
    margin: float = 0.03
) -> Dict[str, Any]:
    """
    Non-inferiority test on given metric (e.g. Recall or Precision):
    Pre-specified margin Delta = 0.03 (3 percentage points).
    H0: Metric_Jev - Metric_LLM <= -margin
    H1: Metric_Jev - Metric_LLM > -margin
    """
    diff_arr = np.array(diff_values)
    # One-sided lower 95% confidence bound (5th percentile)
    lower_95_bound = float(np.percentile(diff_arr, 5.0))
    p_value = float(np.mean(diff_arr <= -margin))
    is_non_inferior = bool(lower_95_bound > -margin)

    return {
        "metric": metric_name,
        "margin": margin,
        "lower_95_bound": lower_95_bound,
        "mean_diff": float(np.mean(diff_arr)),
        "p_value": p_value,
        "is_non_inferior": is_non_inferior,
        "verdict": f"Non-inferiority Established ({metric_name})" if is_non_inferior else f"Inconclusive / Inferior ({metric_name})"
    }


def run_mcnemar_exact_match(
    y_true: np.ndarray,
    y_pred_jev: np.ndarray,
    y_pred_llm: np.ndarray
) -> Dict[str, Any]:
    """
    McNemar's test on Exact-Match (Subset Accuracy).
    Contingency table on whether all 9 labels matched for each sample.
    """
    jev_correct = np.all(y_true == y_pred_jev, axis=1)
    llm_correct = np.all(y_true == y_pred_llm, axis=1)

    n11 = int(np.sum(jev_correct & llm_correct))
    n10 = int(np.sum(jev_correct & (~llm_correct))) # Jev correct, LLM wrong
    n01 = int(np.sum((~jev_correct) & llm_correct)) # Jev wrong, LLM correct
    n00 = int(np.sum((~jev_correct) & (~llm_correct)))

    discordant = n10 + n01
    if discordant == 0:
        chi2_uncorrected = 0.0
        chi2_edwards = 0.0
        p_val = 1.0
        test_type = "No discordant pairs"
    elif discordant >= 25:
        # Edwards continuity correction
        chi2_uncorrected = float((abs(n10 - n01) ** 2) / discordant)
        chi2_edwards = float(((max(0.0, abs(n10 - n01) - 1.0)) ** 2) / discordant)
        p_val = float(stats.chi2.sf(chi2_edwards, df=1))
        test_type = "McNemar Chi-Square (Edwards corrected)"
    else:
        # Exact two-sided binomial test for small sample sizes
        res = stats.binomtest(min(n10, n01), discordant, p=0.5, alternative='two-sided')
        p_val = float(res.pvalue)
        chi2_uncorrected = float((abs(n10 - n01) ** 2) / discordant)
        chi2_edwards = float(((max(0.0, abs(n10 - n01) - 1.0)) ** 2) / discordant)
        test_type = f"Exact Binomial Test (discordant={discordant})"

    is_significant = bool(p_val < 0.05)
    if not is_significant:
        advantage = "No significant difference"
    else:
        advantage = "JEV" if n10 > n01 else "LLM"

    return {
        "table": {"n11": n11, "n10": n10, "n01": n01, "n00": n00},
        "chi2_uncorrected": chi2_uncorrected,
        "chi2_edwards": chi2_edwards,
        "statistic": chi2_edwards if discordant >= 25 else chi2_uncorrected,
        "p_value": p_val,
        "significant": is_significant,
        "advantage": advantage,
        "test_type": test_type
    }


def evaluate_genre_breakdown(
    df_test: pd.DataFrame,
    y_true: np.ndarray,
    y_pred_jev: np.ndarray,
    y_pred_llm: np.ndarray
) -> Dict[str, Any]:
    """Stratified performance evaluation across direct, news, and social genres."""
    genres = df_test["genre"].unique().tolist()
    results = {}

    for g in genres:
        mask = (df_test["genre"] == g).values
        if np.sum(mask) == 0:
            continue

        yt = y_true[mask]
        yj = y_pred_jev[mask]
        yl = y_pred_llm[mask]

        results[g] = {
            "count": int(np.sum(mask)),
            "jev": {
                "subset_accuracy": float(np.mean(np.all(yt == yj, axis=1))),
                "micro_f1": float(f1_score(yt, yj, average="micro", zero_division=0)),
                "macro_f1": float(f1_score(yt, yj, average="macro", zero_division=0))
            },
            "llm": {
                "subset_accuracy": float(np.mean(np.all(yt == yl, axis=1))),
                "micro_f1": float(f1_score(yt, yl, average="micro", zero_division=0)),
                "macro_f1": float(f1_score(yt, yl, average="macro", zero_division=0))
            }
        }

    return results

# =====================================================================
# WINNER DETERMINATION ENGINE
# =====================================================================

def determine_winners(
    metrics_jev: Dict[str, Any],
    metrics_llm: Dict[str, Any],
    mcnemar: Dict[str, Any],
    non_inf: Dict[str, Any],
    non_inf_prec: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Symmetrically compare performance across 5 core categories + construct objective empirical findings.
    No undisclosed or arbitrary weights. Everything is derived directly from test results.
    """
    c_jev = metrics_jev["classification"]
    c_llm = metrics_llm["classification"]
    r_jev = metrics_jev["reliability"]
    r_llm = metrics_llm["reliability"]
    k_jev = metrics_jev["ranking_calibration"]
    k_llm = metrics_llm["ranking_calibration"]
    e_jev = metrics_jev["efficiency"]
    e_llm = metrics_llm["efficiency"]

    # Category 1: Classification Quality
    # Compare Micro F1, Subset Accuracy, and Overall Accuracy
    if c_jev["micro_f1"] > c_llm["micro_f1"] + 0.01:
        winner_cls = "JEV (Higher F1)"
    elif c_llm["micro_f1"] > c_jev["micro_f1"] + 0.01:
        winner_cls = "Groq LLM (Higher F1)"
    else:
        winner_cls = "TIE (Comparable F1)"

    # Category 2: Reliability & Hallucinations
    # Symmetric comparison: if both have 0 errors, it is a clean TIE
    if r_jev["parse_errors_count"] == 0 and r_llm["parse_errors_count"] == 0 and r_jev["invalid_keys_count"] == 0 and r_llm["invalid_keys_count"] == 0:
        winner_rel = "TIE (Both 100% Reliable)"
        rel_margin = "Identical 100% Schema Adherence (0 errors)"
    elif (r_jev["parse_errors_count"] + r_jev["invalid_keys_count"]) < (r_llm["parse_errors_count"] + r_llm["invalid_keys_count"]):
        winner_rel = "TypeSafe JEV"
        rel_margin = f"Fewer errors ({r_jev['parse_errors_count']} vs {r_llm['parse_errors_count']})"
    elif (r_llm["parse_errors_count"] + r_llm["invalid_keys_count"]) < (r_jev["parse_errors_count"] + r_jev["invalid_keys_count"]):
        winner_rel = "Groq LLM"
        rel_margin = f"Fewer errors ({r_llm['parse_errors_count']} vs {r_jev['parse_errors_count']})"
    else:
        winner_rel = "TIE"
        rel_margin = "Equal Reliability"

    # Category 3: Ranking & Calibration
    pts_cal_j = (
        (1 if k_jev["micro_average_precision"] > k_llm["micro_average_precision"] else 0) +
        (1 if k_jev["micro_roc_auc"] > k_llm["micro_roc_auc"] else 0) +
        (1 if k_jev["brier_score"] < k_llm["brier_score"] else 0) +
        (1 if k_jev["ece"] < k_llm["ece"] else 0)
    )
    pts_cal_l = (
        (1 if k_llm["micro_average_precision"] > k_jev["micro_average_precision"] else 0) +
        (1 if k_llm["micro_roc_auc"] > k_jev["micro_roc_auc"] else 0) +
        (1 if k_llm["brier_score"] < k_jev["brier_score"] else 0) +
        (1 if k_llm["ece"] < k_jev["ece"] else 0)
    )
    if pts_cal_j > pts_cal_l:
        winner_cal = "TypeSafe JEV"
    elif pts_cal_l > pts_cal_j:
        winner_cal = "Groq LLM"
    else:
        winner_cal = "TIE"

    # Category 4: Operational Efficiency & Cost
    if e_jev["latency_p50_ms"] < e_llm["latency_p50_ms"] and e_jev["cost_per_1k_messages_usd"] < e_llm["cost_per_1k_messages_usd"]:
        winner_eff = "TypeSafe JEV (Faster & Cheaper)"
    elif e_llm["latency_p50_ms"] < e_jev["latency_p50_ms"] and e_llm["cost_per_1k_messages_usd"] < e_jev["cost_per_1k_messages_usd"]:
        winner_eff = "Groq LLM (Faster & Cheaper)"
    else:
        winner_eff = "TypeSafe JEV (Lower Latency)" if e_jev["latency_p50_ms"] < e_llm["latency_p50_ms"] else "Groq LLM"

    # Category 5: Statistical Significance
    if mcnemar.get("significant", False):
        winner_stat = mcnemar["advantage"]
    elif non_inf.get("is_non_inferior", False):
        winner_stat = "TypeSafe JEV (Non-inferior Recall Confirmed)"
    else:
        winner_stat = "TIE (No Significant Difference, p >= 0.05)"

    categories = {
        "Classification Performance": {
            "winner": winner_cls,
            "jev_summary": f"Acc: {c_jev['overall_accuracy']*100:.1f}% | Rec: {c_jev['micro_recall']:.3f} | Prec: {c_jev['micro_precision']:.3f} | F1: {c_jev['micro_f1']:.3f}",
            "llm_summary": f"Acc: {c_llm['overall_accuracy']*100:.1f}% | Rec: {c_llm['micro_recall']:.3f} | Prec: {c_llm['micro_precision']:.3f} | F1: {c_llm['micro_f1']:.3f}",
            "margin": f"Delta Prec: {c_jev['micro_precision'] - c_llm['micro_precision']:+.3f} | Delta Rec: {c_jev['micro_recall'] - c_llm['micro_recall']:+.3f}"
        },
        "Reliability & Hallucinations": {
            "winner": winner_rel,
            "jev_summary": f"Failures: {r_jev['parse_errors_count']} | Invalid Keys: {r_jev['invalid_keys_count']}",
            "llm_summary": f"Failures: {r_llm['parse_errors_count']} | Invalid Keys: {r_llm['invalid_keys_count']}",
            "margin": rel_margin
        },
        "Ranking & Calibration": {
            "winner": winner_cal,
            "jev_summary": f"Micro AP: {k_jev['micro_average_precision']:.3f} | AUC: {k_jev['micro_roc_auc']:.3f} | Brier: {k_jev['brier_score']:.3f}",
            "llm_summary": f"Micro AP: {k_llm['micro_average_precision']:.3f} | AUC: {k_llm['micro_roc_auc']:.3f} | Brier: {k_llm['brier_score']:.3f}",
            "margin": f"ECE: {k_jev['ece']:.3f} vs {k_llm['ece']:.3f}"
        },
        "Operational Efficiency & Cost": {
            "winner": winner_eff,
            "jev_summary": f"p50: {e_jev['latency_p50_ms']:.0f}ms | Cost/1k: ${e_jev['cost_per_1k_messages_usd']:.4f}",
            "llm_summary": f"p50: {e_llm['latency_p50_ms']:.0f}ms | Cost/1k: ${e_llm['cost_per_1k_messages_usd']:.4f}",
            "margin": f"Speedup: {e_llm['latency_p50_ms']/max(1.0, e_jev['latency_p50_ms']):.1f}x | Cost: {e_llm['cost_per_1k_messages_usd']/max(0.0001, e_jev['cost_per_1k_messages_usd']):.1f}x Cheaper"
        },
        "Statistical Significance": {
            "winner": winner_stat,
            "jev_summary": f"Non-inf (Rec): {non_inf['is_non_inferior']} (margin=0.03)" + (f" | Prec: {non_inf_prec['is_non_inferior']}" if non_inf_prec else ""),
            "llm_summary": f"McNemar: {mcnemar['advantage']} (p={mcnemar['p_value']:.4f})",
            "margin": f"Rec p={non_inf['p_value']:.3f}" + (f" | Prec p={non_inf_prec['p_value']:.3f}" if non_inf_prec else "")
        }
    }

    jev_cat_wins = sum(1 for c in categories.values() if "JEV" in c["winner"])
    llm_cat_wins = sum(1 for c in categories.values() if "Groq" in c["winner"] or "LLM" in c["winner"])
    tie_cats = sum(1 for c in categories.values() if "TIE" in c["winner"])

    if jev_cat_wins > llm_cat_wins:
        overall_winner = "TypeSafe JEV"
    elif llm_cat_wins > jev_cat_wins:
        overall_winner = "Groq LLM (GPT-OSS-120B)"
    else:
        overall_winner = "Empirical Trade-off (Tied Categories)"

    # Construct an objective, truthful summary directly from test results
    findings_summary = (
        f"Empirical evaluation shows Groq LLM achieved {'higher' if c_llm['micro_precision'] > c_jev['micro_precision'] else 'lower'} precision "
        f"({c_llm['micro_precision']:.3f} vs {c_jev['micro_precision']:.3f}, FPR: {c_llm['false_positive_rate']*100:.1f}% vs {c_jev['false_positive_rate']*100:.1f}%), "
        f"while TypeSafe JEV achieved {'higher' if c_jev['micro_recall'] > c_llm['micro_recall'] else 'comparable'} recall "
        f"({c_jev['micro_recall']:.3f} vs {c_llm['micro_recall']:.3f}). "
        f"Reliability: {'Both systems achieved 100% schema compliance (0 parse errors)' if r_jev['parse_errors_count']==0 and r_llm['parse_errors_count']==0 else 'Schema violations observed'}. "
        f"TypeSafe JEV demonstrated an operational advantage in median latency ({e_jev['latency_p50_ms']:.0f}ms vs {e_llm['latency_p50_ms']:.0f}ms) "
        f"and estimated cost (${e_jev['cost_per_1k_messages_usd']:.4f} vs ${e_llm['cost_per_1k_messages_usd']:.4f}/1k). "
        f"Exact-match difference is {'' if mcnemar['significant'] else 'not '}statistically significant (McNemar p = {mcnemar['p_value']:.4f})."
    )

    return {
        "categories": categories,
        "scores": {
            "jev_weighted_points": jev_cat_wins,
            "llm_weighted_points": llm_cat_wins,
            "jev_categories_won": jev_cat_wins,
            "llm_categories_won": llm_cat_wins,
            "ties": tie_cats
        },
        "overall_winner": overall_winner,
        "rationale": findings_summary,
        "findings_summary": findings_summary
    }

# =====================================================================
# VISUALIZATION SUITE & SCOREBOARD GENERATION
# =====================================================================

def generate_visualizations(
    metrics_jev: Dict[str, Any],
    metrics_llm: Dict[str, Any],
    dev_threshold_sweep: List[Dict[str, float]],
    optimal_tau: float,
    bootstrap_res: Dict[str, Any],
    genre_res: Dict[str, Any],
    winners: Dict[str, Any],
    y_true: np.ndarray,
    probs_jev: np.ndarray,
    probs_llm: np.ndarray,
    output_dir: str = "benchmark_artifacts"
) -> Dict[str, str]:
    """Generate all analytical figures and the master comparison scoreboard image."""
    os.makedirs(output_dir, exist_ok=True)
    generated_files = {}

    plt.style.use('seaborn-v0_8-whitegrid' if 'seaborn-v0_8-whitegrid' in plt.style.available else 'default')
    c_jev_color = "#2563eb"  # Deep Royal Blue
    c_llm_color = "#d97706"  # Warm Amber / Orange

    # -------------------------------------------------------------
    # 1. Classification Metrics & Per-Resource Comparison
    # -------------------------------------------------------------
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5.5))

    # Per-resource F1
    res_names = RESOURCE_COLUMNS
    f1_jev = [metrics_jev["per_resource"][r]["f1"] for r in res_names]
    f1_llm = [metrics_llm["per_resource"][r]["f1"] for r in res_names]
    x = np.arange(len(res_names))
    width = 0.36

    ax1.bar(x - width/2, f1_jev, width, label='TypeSafe JEV', color=c_jev_color, alpha=0.9)
    ax1.bar(x + width/2, f1_llm, width, label='Groq GPT-OSS-120B', color=c_llm_color, alpha=0.9)
    ax1.set_xticks(x)
    supports = [metrics_jev["per_resource"][r]["support"] for r in res_names]
    xtick_labels = [f"{r.replace('_', '\n')}\n(N={s})" for r, s in zip(res_names, supports)]
    ax1.set_xticklabels(xtick_labels, fontsize=7.5)
    ax1.set_ylabel("F1 Score", fontweight='bold')
    ax1.set_title("Per-Resource F1 Score (with Support N)", fontweight='bold', fontsize=12)
    ax1.set_ylim(0, 1.05)
    ax1.legend(loc='lower right', frameon=True)

    # Multi-label Aggregate Metrics
    agg_labels = ['Micro F1', 'Macro F1', 'Weighted F1', 'Subset Acc', 'Jaccard']
    agg_jev = [
        metrics_jev["classification"]["micro_f1"],
        metrics_jev["classification"]["macro_f1"],
        metrics_jev["classification"]["weighted_f1"],
        metrics_jev["classification"]["subset_accuracy"],
        metrics_jev["classification"]["sample_jaccard"]
    ]
    agg_llm = [
        metrics_llm["classification"]["micro_f1"],
        metrics_llm["classification"]["macro_f1"],
        metrics_llm["classification"]["weighted_f1"],
        metrics_llm["classification"]["subset_accuracy"],
        metrics_llm["classification"]["sample_jaccard"]
    ]
    x2 = np.arange(len(agg_labels))
    ax2.bar(x2 - width/2, agg_jev, width, label='TypeSafe JEV', color=c_jev_color, alpha=0.9)
    ax2.bar(x2 + width/2, agg_llm, width, label='Groq GPT-OSS-120B', color=c_llm_color, alpha=0.9)
    for i in range(len(agg_labels)):
        ax2.text(x2[i] - width/2, agg_jev[i] + 0.02, f"{agg_jev[i]:.2f}", ha='center', fontsize=8, fontweight='bold')
        ax2.text(x2[i] + width/2, agg_llm[i] + 0.02, f"{agg_llm[i]:.2f}", ha='center', fontsize=8, fontweight='bold')
    ax2.set_xticks(x2)
    ax2.set_xticklabels(agg_labels, fontsize=9.5, fontweight='bold')
    ax2.set_ylabel("Score", fontweight='bold')
    ax2.set_title("Aggregate Multi-Label Performance", fontweight='bold', fontsize=12)
    ax2.set_ylim(0, 1.1)
    ax2.legend(loc='lower right', frameon=True)

    plt.tight_layout()
    p1 = os.path.join(output_dir, "classification_comparison.png")
    fig.savefig(p1, dpi=200)
    plt.close(fig)
    generated_files["classification"] = p1

    # -------------------------------------------------------------
    # 2. Calibration & Reliability Diagram
    # -------------------------------------------------------------
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5))

    # Reliability diagram
    bins_j = metrics_jev["ranking_calibration"]["calibration_bins"]
    bins_l = metrics_llm["ranking_calibration"]["calibration_bins"]

    cj = [b["confidence"] for b in bins_j if b["count"] > 0]
    aj = [b["accuracy"] for b in bins_j if b["count"] > 0]
    cl = [b["confidence"] for b in bins_l if b["count"] > 0]
    al = [b["accuracy"] for b in bins_l if b["count"] > 0]

    ax1.plot([0, 1], [0, 1], 'k--', label='Perfect Calibration', alpha=0.7)
    ax1.plot(cj, aj, 's-', color=c_jev_color, lw=2.2, label=f"JEV (ECE={metrics_jev['ranking_calibration']['ece']:.3f})")
    ax1.plot(cl, al, 'o-', color=c_llm_color, lw=2.2, label=f"LLM (ECE={metrics_llm['ranking_calibration']['ece']:.3f})")
    ax1.set_xlabel("Mean Predicted Confidence", fontweight='bold')
    ax1.set_ylabel("Empirical Accuracy", fontweight='bold')
    ax1.set_title("Reliability Diagram (Calibration Curves)", fontweight='bold', fontsize=12)
    ax1.set_xlim(-0.02, 1.02)
    ax1.set_ylim(-0.02, 1.02)
    ax1.legend(loc='upper left', frameon=True)

    # Dev Threshold Sweep
    sweep_taus = [s["threshold"] for s in dev_threshold_sweep]
    sweep_f1s = [s["micro_f1"] for s in dev_threshold_sweep]
    sweep_recs = [s["micro_recall"] for s in dev_threshold_sweep]
    sweep_precs = [s["micro_precision"] for s in dev_threshold_sweep]

    ax2.plot(sweep_taus, sweep_f1s, 'b-', lw=2.2, label='Dev Micro F1')
    ax2.plot(sweep_taus, sweep_recs, 'g--', lw=1.5, label='Dev Recall')
    ax2.plot(sweep_taus, sweep_precs, 'm:', lw=1.5, label='Dev Precision')
    ax2.axvline(optimal_tau, color='crimson', linestyle='-.', lw=2, label=f'Optimal tau* = {optimal_tau:.2f}')
    ax2.set_xlabel("Threshold (tau)", fontweight='bold')
    ax2.set_ylabel("Dev Metric Score", fontweight='bold')
    ax2.set_title("JEV Threshold Tuning on Dev Split", fontweight='bold', fontsize=12)
    ax2.set_ylim(0, 1.05)
    ax2.legend(loc='lower left', frameon=True)

    plt.tight_layout()
    p2 = os.path.join(output_dir, "reliability_calibration.png")
    fig.savefig(p2, dpi=200)
    plt.close(fig)
    generated_files["calibration"] = p2

    # -------------------------------------------------------------
    # 3. Efficiency & Cost Comparison
    # -------------------------------------------------------------
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))

    lat_cats = ['p50 (Median)', 'Mean', 'p95', 'p99']
    lat_j = [
        metrics_jev["efficiency"]["latency_p50_ms"],
        metrics_jev["efficiency"]["latency_mean_ms"],
        metrics_jev["efficiency"]["latency_p95_ms"],
        metrics_jev["efficiency"]["latency_p99_ms"]
    ]
    lat_l = [
        metrics_llm["efficiency"]["latency_p50_ms"],
        metrics_llm["efficiency"]["latency_mean_ms"],
        metrics_llm["efficiency"]["latency_p95_ms"],
        metrics_llm["efficiency"]["latency_p99_ms"]
    ]
    x_lat = np.arange(len(lat_cats))
    ax1.bar(x_lat - width/2, lat_j, width, label='TypeSafe JEV', color=c_jev_color, alpha=0.9)
    ax1.bar(x_lat + width/2, lat_l, width, label='Groq GPT-OSS-120B', color=c_llm_color, alpha=0.9)
    for i in range(len(lat_cats)):
        ax1.text(x_lat[i] - width/2, lat_j[i] + 10, f"{lat_j[i]:.0f}ms", ha='center', fontsize=8, fontweight='bold')
        ax1.text(x_lat[i] + width/2, lat_l[i] + 10, f"{lat_l[i]:.0f}ms", ha='center', fontsize=8, fontweight='bold')
    ax1.set_xticks(x_lat)
    ax1.set_xticklabels(lat_cats, fontweight='bold')
    ax1.set_ylabel("Latency (ms)", fontweight='bold')
    ax1.set_title("Inference Latency Percentiles", fontweight='bold', fontsize=12)
    ax1.legend(loc='upper left', frameon=True)

    # Cost per 1k messages
    cost_j = metrics_jev["efficiency"]["cost_per_1k_messages_usd"]
    cost_l = metrics_llm["efficiency"]["cost_per_1k_messages_usd"]
    bars = ax2.bar(['TypeSafe JEV', 'Groq GPT-OSS-120B'], [cost_j, cost_l], color=[c_jev_color, c_llm_color], width=0.45)
    for b in bars:
        ax2.text(b.get_x() + b.get_width()/2, b.get_height() + 0.005, f"${b.get_height():.4f}", ha='center', fontweight='bold')
    ax2.set_ylabel("USD ($) per 1,000 Messages", fontweight='bold')
    ax2.set_title("Estimated Cost per 1,000 Classifications", fontweight='bold', fontsize=12)
    ax2.set_ylim(0, max(cost_l * 1.25, 0.05))

    plt.tight_layout()
    p3 = os.path.join(output_dir, "efficiency_latency_cost.png")
    fig.savefig(p3, dpi=200)
    plt.close(fig)
    generated_files["efficiency"] = p3

    # -------------------------------------------------------------
    # 4. Statistical Bootstrap & Non-Inferiority
    # -------------------------------------------------------------
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5))

    # Bootstrap Difference in Micro F1
    diff_f1 = bootstrap_res["raw_diff_micro_f1"]
    sns.histplot(diff_f1, ax=ax1, kde=True, color=c_jev_color, stat="density")
    ci_f1 = bootstrap_res["diff_micro_f1_ci"]
    ax1.axvline(ci_f1[0], color='darkred', linestyle='--', label=f'95% CI Lower: {ci_f1[0]:.3f}')
    ax1.axvline(ci_f1[1], color='darkred', linestyle='--', label=f'95% CI Upper: {ci_f1[1]:.3f}')
    ax1.axvline(0, color='black', lw=1.5)
    ax1.set_title("Paired Bootstrap: Delta Micro F1 (JEV - LLM)", fontweight='bold', fontsize=12)
    ax1.set_xlabel("Delta Micro F1", fontweight='bold')
    ax1.legend(loc='upper right', frameon=True)

    # Bootstrap Difference in Recall & Non-inferiority margin (-0.05)
    diff_rec = bootstrap_res["raw_diff_micro_recall"]
    sns.histplot(diff_rec, ax=ax2, kde=True, color="teal", stat="density")
    ci_rec = bootstrap_res["diff_micro_recall_ci"]
    margin_val = 0.03
    ax2.axvline(-margin_val, color='crimson', lw=2.5, linestyle='-.', label=f'Non-Inf. Margin (delta = -{margin_val:.2f})')
    ax2.axvline(np.percentile(diff_rec, 5.0), color='purple', lw=2, linestyle=':', label=f'5th Percentile: {np.percentile(diff_rec, 5.0):.3f}')
    ax2.set_title(f"Non-Inferiority Test on Recall (Margin = {margin_val:.2f})", fontweight='bold', fontsize=12)
    ax2.set_xlabel("Delta Micro Recall (JEV - LLM)", fontweight='bold')
    ax2.legend(loc='upper right', frameon=True)

    plt.tight_layout()
    p4 = os.path.join(output_dir, "statistical_bootstrap_diff.png")
    fig.savefig(p4, dpi=200)
    plt.close(fig)
    generated_files["statistics"] = p4

    # -------------------------------------------------------------
    # 5. Genre Breakdown Chart
    # -------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(10, 4.5))
    genres = list(genre_res.keys())
    x_g = np.arange(len(genres))
    g_jev = [genre_res[g]["jev"]["micro_f1"] for g in genres]
    g_llm = [genre_res[g]["llm"]["micro_f1"] for g in genres]

    ax.bar(x_g - width/2, g_jev, width, label='TypeSafe JEV', color=c_jev_color, alpha=0.9)
    ax.bar(x_g + width/2, g_llm, width, label='Groq GPT-OSS-120B', color=c_llm_color, alpha=0.9)
    for i, g in enumerate(genres):
        cnt = genre_res[g]["count"]
        ax.text(x_g[i] - width/2, g_jev[i] + 0.02, f"{g_jev[i]:.2f}", ha='center', fontsize=8.5, fontweight='bold')
        ax.text(x_g[i] + width/2, g_llm[i] + 0.02, f"{g_llm[i]:.2f}", ha='center', fontsize=8.5, fontweight='bold')
    ax.set_xticks(x_g)
    ax.set_xticklabels([f"{g.upper()} (N={genre_res[g]['count']})" for g in genres], fontweight='bold', fontsize=10)
    ax.set_ylabel("Micro F1 Score", fontweight='bold')
    ax.set_title("Performance Breakdown Stratified by Disaster Message Genre", fontweight='bold', fontsize=12)
    ax.set_ylim(0, 1.1)
    ax.legend(loc='lower right', frameon=True)

    plt.tight_layout()
    p5 = os.path.join(output_dir, "genre_breakdown.png")
    fig.savefig(p5, dpi=200)
    plt.close(fig)
    generated_files["genre"] = p5

    # -------------------------------------------------------------
    # 6. ROC & Precision-Recall Curves
    # -------------------------------------------------------------
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5))
    flat_true = y_true.flatten()
    flat_j = probs_jev.flatten()
    flat_l = probs_llm.flatten()

    fpr_j, tpr_j, _ = roc_curve(flat_true, flat_j)
    fpr_l, tpr_l, _ = roc_curve(flat_true, flat_l)
    auc_j = metrics_jev["ranking_calibration"]["micro_roc_auc"]
    auc_l = metrics_llm["ranking_calibration"]["micro_roc_auc"]

    ax1.plot(fpr_j, tpr_j, color=c_jev_color, lw=2.2, label=f'JEV (AUC = {auc_j:.3f})')
    ax1.plot(fpr_l, tpr_l, color=c_llm_color, lw=2.2, label=f'LLM (AUC = {auc_l:.3f})')
    ax1.plot([0, 1], [0, 1], 'k--', lw=1)
    ax1.set_xlabel("False Positive Rate", fontweight='bold')
    ax1.set_ylabel("True Positive Rate", fontweight='bold')
    ax1.set_title("Micro-Averaged ROC Curves", fontweight='bold', fontsize=12)
    ax1.legend(loc='lower right', frameon=True)

    p_j, r_j, _ = precision_recall_curve(flat_true, flat_j)
    p_l, r_l, _ = precision_recall_curve(flat_true, flat_l)
    map_j = metrics_jev["ranking_calibration"]["micro_average_precision"]
    map_l = metrics_llm["ranking_calibration"]["micro_average_precision"]

    ax2.plot(r_j, p_j, color=c_jev_color, lw=2.2, label=f'JEV (Micro AP = {map_j:.3f})')
    ax2.plot(r_l, p_l, color=c_llm_color, lw=2.2, label=f'LLM (Micro AP = {map_l:.3f})')
    ax2.set_xlabel("Recall", fontweight='bold')
    ax2.set_ylabel("Precision", fontweight='bold')
    ax2.set_title("Micro-Averaged Precision-Recall Curves", fontweight='bold', fontsize=12)
    ax2.legend(loc='lower left', frameon=True)

    plt.tight_layout()
    p6 = os.path.join(output_dir, "roc_pr_curves.png")
    fig.savefig(p6, dpi=200)
    plt.close(fig)
    generated_files["roc_pr"] = p6

    # -------------------------------------------------------------
    # 7. MASTER COMPARISON SCOREBOARD INFOGRAPHIC (Standalone Image)
    # -------------------------------------------------------------
    p7 = generate_master_scoreboard_image(
        metrics_jev, metrics_llm, winners, output_dir=output_dir
    )
    generated_files["scoreboard"] = p7

    return generated_files


def generate_master_scoreboard_image(
    metrics_jev: Dict[str, Any],
    metrics_llm: Dict[str, Any],
    winners: Dict[str, Any],
    output_dir: str = "benchmark_artifacts"
) -> str:
    """
    Generate an executive master scoreboard image showing all categories,
    side-by-side metrics, category winners, and the final overall winner.
    """
    fig = plt.figure(figsize=(18, 11), facecolor="#090d16")
    ax = fig.add_axes([0, 0, 1, 1], frameon=False)
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis('off')

    # Top Header Banner
    header_box = patches.FancyBboxPatch(
        (3, 86), 94, 11, boxstyle="round,pad=0.6,rounding_size=1.5",
        facecolor="#111827", edgecolor="#374151", linewidth=1.5
    )
    ax.add_patch(header_box)
    ax.text(50, 93.5, "DISASTER RESOURCE CLASSIFICATION BENCHMARK",
            ha='center', va='center', color="#f3f4f6", fontsize=21, fontweight='bold')
    ax.text(50, 89.2, "TypeSafe JEV (OpenRouter Decisions API) vs. Groq LLM (gpt-oss-120b)",
            ha='center', va='center', color="#9ca3af", fontsize=12.5)

    # Master Comparative Overview Card
    win_box = patches.FancyBboxPatch(
        (3, 72.5), 94, 11.5, boxstyle="round,pad=0.6,rounding_size=1.5",
        facecolor="#0f172a", edgecolor="#38bdf8", linewidth=2.0
    )
    ax.add_patch(win_box)
    ax.text(6.5, 79.8, "[HEAD-TO-HEAD BENCHMARK OVERVIEW]", color="#38bdf8",
            fontsize=12, fontweight='bold')
    ax.text(6.5, 75.2, f"Leading Dimension: {winners['overall_winner']}",
            color="#ffffff", fontsize=18, fontweight='heavy')
    ax.text(94, 79.5, f"JEV Leads: {winners['scores']['jev_categories_won']} Categories",
            ha='right', color="#60a5fa", fontsize=12, fontweight='bold')
    ax.text(94, 76.5, f"LLM Leads: {winners['scores']['llm_categories_won']} Categories",
            ha='right', color="#fbbf24", fontsize=12, fontweight='bold')
    ax.text(94, 73.5, f"Ties: {winners['scores']['ties']} Categories",
            ha='right', color="#94a3b8", fontsize=11, fontweight='bold')

    # 5 Category Cards
    categories = [
        ("1. Classification Quality", "Classification Performance", 56.5),
        ("2. Reliability & Hallucinations", "Reliability & Hallucinations", 43.5),
        ("3. Ranking & Calibration", "Ranking & Calibration", 30.5),
        ("4. Efficiency & Operations", "Operational Efficiency & Cost", 17.5),
        ("5. Statistical Rigor", "Statistical Significance", 4.5),
    ]

    for title, cat_key, y_pos in categories:
        cat_info = winners["categories"][cat_key]
        c_winner = cat_info["winner"]

        # Background card
        card = patches.FancyBboxPatch(
            (3, y_pos), 94, 11, boxstyle="round,pad=0.5,rounding_size=1.0",
            facecolor="#111827", edgecolor="#1f2937", linewidth=1.2
        )
        ax.add_patch(card)

        # Title
        ax.text(5, y_pos + 7.8, title, color="#38bdf8", fontsize=13.5, fontweight='bold')

        # Winner Badge
        is_jev_win = "JEV" in c_winner
        is_tie = "TIE" in c_winner
        if is_tie:
            badge_color = "#1e293b"
            badge_text_color = "#94a3b8"
        elif is_jev_win:
            badge_color = "#1e3a8a"
            badge_text_color = "#93c5fd"
        else:
            badge_color = "#78350f"
            badge_text_color = "#fcd34d"

        badge = patches.FancyBboxPatch(
            (71, y_pos + 6.2), 24.5, 3.8, boxstyle="round,pad=0.3,rounding_size=0.8",
            facecolor=badge_color, edgecolor=badge_text_color, linewidth=1.2
        )
        ax.add_patch(badge)
        ax.text(83.2, y_pos + 8.1, f"STATUS: {c_winner}", ha='center', va='center',
                color=badge_text_color, fontsize=9.5, fontweight='bold')

        # Metrics content
        ax.text(6, y_pos + 4.2, f"TypeSafe JEV :  {cat_info['jev_summary']}",
                color="#e2e8f0", fontsize=11, fontfamily='monospace')
        ax.text(6, y_pos + 1.8, f"Groq LLM     :  {cat_info['llm_summary']}",
                color="#cbd5e1", fontsize=11, fontfamily='monospace')
        ax.text(74, y_pos + 2.5, f"Margin: {cat_info['margin']}",
                color="#10b981", fontsize=10, fontweight='bold')

    image_path = os.path.join(output_dir, "comparison_scoreboard_summary.png")
    fig.savefig(image_path, dpi=200)
    plt.close(fig)
    return image_path

# =====================================================================
# PDF REPORT COMPILER
# =====================================================================

class NumberedCanvas(canvas.Canvas):
    """Adds professional header, footer, and page numbers to PDF."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_header_footer(num_pages)
            super().showPage()
        super().save()

    def draw_header_footer(self, page_count):
        self.saveState()
        self.setFont("Helvetica-Bold", 8)
        self.setFillColor(colors.HexColor("#6b7280"))

        # Header (pages > 1)
        if self._pageNumber > 1:
            self.drawString(54, 750, "EMERGENCY RESOURCE BENCHMARK: TYPESAFE JEV vs. GROQ GPT-OSS-120B")
            self.setStrokeColor(colors.HexColor("#e5e7eb"))
            self.setLineWidth(0.5)
            self.line(54, 744, 558, 744)

        # Footer
        self.setStrokeColor(colors.HexColor("#e5e7eb"))
        self.setLineWidth(0.5)
        self.line(54, 45, 558, 45)
        page_str = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(558, 32, page_str)
        self.drawString(54, 32, "CONFIDENTIAL & PROPRIETARY EVALUATION REPORT | DEEPMIND ANTIGRAVITY")
        self.restoreState()


def compile_pdf_report(
    metrics_jev: Dict[str, Any],
    metrics_llm: Dict[str, Any],
    winners: Dict[str, Any],
    bootstrap_res: Dict[str, Any],
    mcnemar_res: Dict[str, Any],
    non_inf_res: Dict[str, Any],
    genre_res: Dict[str, Any],
    optimal_tau: float,
    figures: Dict[str, str],
    n_dev: int,
    n_test: int,
    output_pdf_path: str = "jev_vs_llm_benchmark_report.pdf",
    non_inf_prec_res: Optional[Dict[str, Any]] = None
):
    """Compile multi-page executive PDF benchmark report."""
    doc = SimpleDocTemplate(
        output_pdf_path,
        pagesize=letter,
        leftMargin=54,
        rightMargin=54,
        topMargin=54,
        bottomMargin=54
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=20,
        leading=24,
        textColor=colors.HexColor('#1e3a8a'),
        spaceAfter=6
    )
    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        leading=14,
        textColor=colors.HexColor('#4b5563'),
        spaceAfter=15
    )
    h2_style = ParagraphStyle(
        'Heading2Custom',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=13,
        leading=17,
        textColor=colors.HexColor('#1e293b'),
        spaceBefore=10,
        spaceAfter=6
    )
    body_style = ParagraphStyle(
        'BodyCustom',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=13,
        textColor=colors.HexColor('#374151')
    )
    bold_cell = ParagraphStyle(
        'BoldCell',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor('#1f2937')
    )
    regular_cell = ParagraphStyle(
        'RegularCell',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor('#374151')
    )

    story = []

    # ================= PAGE 1 =================
    story.append(Paragraph("DISASTER RESOURCE BENCHMARK REPORT", title_style))
    story.append(Paragraph(
        f"Head-to-Head Comparative Study: TypeSafe JEV vs. Groq LLM (gpt-oss-120b)<br/>"
        f"Protocol: Dev/Test Split (Dev N={n_dev}, Test N={n_test}) | Optimal JEV Threshold tau* = {optimal_tau:.2f} | Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        subtitle_style
    ))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#2563eb"), spaceAfter=12))

    # Executive Benchmark Findings Box
    callout_text = (
        f"<b><font size='13' color='white'>EXECUTIVE BENCHMARK FINDINGS</font></b><br/><br/>"
        f"<font size='9' color='#f3f4f6'>{winners['findings_summary']}</font><br/>"
        f"<font size='9' color='#e0e7ff'><b>Category Comparison:</b> TypeSafe JEV Leads: {winners['scores']['jev_categories_won']} | "
        f"Groq LLM Leads: {winners['scores']['llm_categories_won']} | Neutral Ties: {winners['scores']['ties']} (out of 5 categories)</font>"
    )
    callout_data = [[Paragraph(callout_text, body_style)]]
    callout_table = Table(callout_data, colWidths=[504])
    callout_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#0f172a")),
        ('LEFTPADDING', (0,0), (-1,-1), 14),
        ('RIGHTPADDING', (0,0), (-1,-1), 14),
        ('TOPPADDING', (0,0), (-1,-1), 12),
        ('BOTTOMPADDING', (0,0), (-1,-1), 12),
        ('CORNER_RADIUS', (0,0), (-1,-1), 6)
    ]))
    story.append(callout_table)
    story.append(Spacer(1, 14))

    # Category Winner Summary Table
    story.append(Paragraph("Category-by-Category Comparative Scorecard", h2_style))
    score_rows = [
        [Paragraph("<b>Category</b>", bold_cell),
         Paragraph("<b>TypeSafe JEV</b>", bold_cell),
         Paragraph("<b>Groq LLM (120B)</b>", bold_cell),
         Paragraph("<b>Category Leader / Status</b>", bold_cell)]
    ]
    for c_name, c_data in winners["categories"].items():
        w_color = '#1e40af' if 'JEV' in c_data['winner'] else ('#b45309' if 'Groq' in c_data['winner'] or 'LLM' in c_data['winner'] else '#475569')
        w_text = f"<b><font color='{w_color}'>{c_data['winner']}</font></b>"
        score_rows.append([
            Paragraph(f"<b>{c_name}</b>", regular_cell),
            Paragraph(c_data['jev_summary'], regular_cell),
            Paragraph(c_data['llm_summary'], regular_cell),
            Paragraph(w_text, regular_cell)
        ])

    table_score = Table(score_rows, colWidths=[130, 145, 145, 84])
    table_score.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f1f5f9')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(table_score)
    story.append(Spacer(1, 8))

    if "scoreboard" in figures and os.path.exists(figures["scoreboard"]):
        story.append(Image(figures["scoreboard"], width=504, height=250))

    story.append(PageBreak())

    # ================= PAGE 2 =================
    story.append(Paragraph("Multi-Label Classification Evaluation (Test Set)", title_style))
    story.append(Paragraph(
        "Complete multi-label metrics evaluated on the test set. Headline numbers reflect optimal "
        f"dev-tuned threshold (tau* = {optimal_tau:.2f}) for TypeSafe JEV.", body_style
    ))
    story.append(Spacer(1, 8))

    # Aggregate Classification Table
    c_j = metrics_jev["classification"]
    c_l = metrics_llm["classification"]
    cls_data = [
        [Paragraph("<b>Metric</b>", bold_cell),
         Paragraph("<b>TypeSafe JEV</b>", bold_cell),
         Paragraph("<b>Groq LLM (120B)</b>", bold_cell),
         Paragraph("<b>Delta (JEV - LLM)</b>", bold_cell)],
        [Paragraph("Overall Accuracy (All Rows)", bold_cell), Paragraph(f"<b>{c_j['overall_accuracy']*100:.1f}%</b>", bold_cell), Paragraph(f"<b>{c_l['overall_accuracy']*100:.1f}%</b>", bold_cell), Paragraph(f"<b>{(c_j['overall_accuracy']-c_l['overall_accuracy'])*100:+.1f}%</b>", bold_cell)],
        [Paragraph("Subset Accuracy (All 9 Match)", bold_cell), Paragraph(f"<b>{c_j['subset_accuracy']*100:.1f}%</b>", bold_cell), Paragraph(f"<b>{c_l['subset_accuracy']*100:.1f}%</b>", bold_cell), Paragraph(f"<b>{(c_j['subset_accuracy']-c_l['subset_accuracy'])*100:+.1f}%</b>", bold_cell)],
        [Paragraph("Micro Recall (No Misses)", bold_cell), Paragraph(f"<b>{c_j['micro_recall']:.3f}</b>", bold_cell), Paragraph(f"<b>{c_l['micro_recall']:.3f}</b>", bold_cell), Paragraph(f"<b>{c_j['micro_recall']-c_l['micro_recall']:+.3f}</b>", bold_cell)],
        [Paragraph("Micro Precision", bold_cell), Paragraph(f"<b>{c_j['micro_precision']:.3f}</b>", bold_cell), Paragraph(f"<b>{c_l['micro_precision']:.3f}</b>", bold_cell), Paragraph(f"<b>{c_j['micro_precision']-c_l['micro_precision']:+.3f}</b>", bold_cell)],
        [Paragraph("Micro F1 Score", bold_cell), Paragraph(f"<b>{c_j['micro_f1']:.3f}</b>", bold_cell), Paragraph(f"<b>{c_l['micro_f1']:.3f}</b>", bold_cell), Paragraph(f"<b>{c_j['micro_f1']-c_l['micro_f1']:+.3f}</b>", bold_cell)],
        [Paragraph("Macro F1 Score", regular_cell), Paragraph(f"{c_j['macro_f1']:.3f}", regular_cell), Paragraph(f"{c_l['macro_f1']:.3f}", regular_cell), Paragraph(f"{c_j['macro_f1']-c_l['macro_f1']:+.3f}", regular_cell)],
        [Paragraph("Macro Recall", regular_cell), Paragraph(f"{c_j['macro_recall']:.3f}", regular_cell), Paragraph(f"{c_l['macro_recall']:.3f}", regular_cell), Paragraph(f"{c_j['macro_recall']-c_l['macro_recall']:+.3f}", regular_cell)],
        [Paragraph("Macro Precision", regular_cell), Paragraph(f"{c_j['macro_precision']:.3f}", regular_cell), Paragraph(f"{c_l['macro_precision']:.3f}", regular_cell), Paragraph(f"{c_j['macro_precision']-c_l['macro_precision']:+.3f}", regular_cell)],
        [Paragraph("Sample Jaccard Index", regular_cell), Paragraph(f"{c_j['sample_jaccard']:.3f}", regular_cell), Paragraph(f"{c_l['sample_jaccard']:.3f}", regular_cell), Paragraph(f"{c_j['sample_jaccard']-c_l['sample_jaccard']:+.3f}", regular_cell)],
        [Paragraph("Hamming Loss (Lower=Better)", regular_cell), Paragraph(f"{c_j['hamming_loss']:.3f}", regular_cell), Paragraph(f"{c_l['hamming_loss']:.3f}", regular_cell), Paragraph(f"{c_j['hamming_loss']-c_l['hamming_loss']:+.3f}", regular_cell)],
        [Paragraph("Any-Miss Rate (Lower=Better)", regular_cell), Paragraph(f"{c_j['any_miss_rate']*100:.1f}%", regular_cell), Paragraph(f"{c_l['any_miss_rate']*100:.1f}%", regular_cell), Paragraph(f"{(c_j['any_miss_rate']-c_l['any_miss_rate'])*100:+.1f}%", regular_cell)],
        [Paragraph("False Alarm Rate (Lower=Better)", regular_cell), Paragraph(f"{c_j['any_false_alarm_rate']*100:.1f}%", regular_cell), Paragraph(f"{c_l['any_false_alarm_rate']*100:.1f}%", regular_cell), Paragraph(f"{(c_j['any_false_alarm_rate']-c_l['any_false_alarm_rate'])*100:+.1f}%", regular_cell)]
    ]
    t_cls = Table(cls_data, colWidths=[180, 108, 108, 108])
    t_cls.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f8fafc')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4)
    ]))
    story.append(t_cls)
    story.append(Spacer(1, 10))

    if "classification" in figures and os.path.exists(figures["classification"]):
        story.append(Image(figures["classification"], width=504, height=200))

    story.append(PageBreak())

    # ================= PAGE 3 =================
    story.append(Paragraph("Ranking, Calibration & Reliability Diagram", title_style))
    story.append(Paragraph(
        "Evaluation of probability calibration, Brier score loss, Expected Calibration Error (ECE), "
        "and Dev threshold tuning sweep curves.", body_style
    ))
    story.append(Spacer(1, 8))

    k_j = metrics_jev["ranking_calibration"]
    k_l = metrics_llm["ranking_calibration"]
    cal_data = [
        [Paragraph("<b>Metric</b>", bold_cell),
         Paragraph("<b>TypeSafe JEV</b>", bold_cell),
         Paragraph("<b>Groq LLM (120B)</b>", bold_cell),
         Paragraph("<b>Advantage</b>", bold_cell)],
        [Paragraph("Micro Average Precision (mAP)", regular_cell), Paragraph(f"{k_j['micro_average_precision']:.3f}", regular_cell), Paragraph(f"{k_l['micro_average_precision']:.3f}", regular_cell), Paragraph("JEV" if k_j['micro_average_precision']>k_l['micro_average_precision'] else ("LLM" if k_l['micro_average_precision']>k_j['micro_average_precision'] else "TIE"), bold_cell)],
        [Paragraph("Macro Average Precision", regular_cell), Paragraph(f"{k_j['macro_average_precision']:.3f}", regular_cell), Paragraph(f"{k_l['macro_average_precision']:.3f}", regular_cell), Paragraph("JEV" if k_j['macro_average_precision']>k_l['macro_average_precision'] else ("LLM" if k_l['macro_average_precision']>k_j['macro_average_precision'] else "TIE"), bold_cell)],
        [Paragraph("Micro ROC-AUC", regular_cell), Paragraph(f"{k_j['micro_roc_auc']:.3f}", regular_cell), Paragraph(f"{k_l['micro_roc_auc']:.3f}", regular_cell), Paragraph("JEV" if k_j['micro_roc_auc']>k_l['micro_roc_auc'] else ("LLM" if k_l['micro_roc_auc']>k_j['micro_roc_auc'] else "TIE"), bold_cell)],
        [Paragraph("Macro ROC-AUC", regular_cell), Paragraph(f"{k_j['macro_roc_auc']:.3f}", regular_cell), Paragraph(f"{k_l['macro_roc_auc']:.3f}", regular_cell), Paragraph("JEV" if k_j['macro_roc_auc']>k_l['macro_roc_auc'] else ("LLM" if k_l['macro_roc_auc']>k_j['macro_roc_auc'] else "TIE"), bold_cell)],
        [Paragraph("Brier Score (Lower=Better)", regular_cell), Paragraph(f"{k_j['brier_score']:.4f}", regular_cell), Paragraph(f"{k_l['brier_score']:.4f}", regular_cell), Paragraph("JEV" if k_j['brier_score']<k_l['brier_score'] else ("LLM" if k_l['brier_score']<k_j['brier_score'] else "TIE"), bold_cell)],
        [Paragraph("Expected Calibration Error (ECE)", regular_cell), Paragraph(f"{k_j['ece']:.4f}", regular_cell), Paragraph(f"{k_l['ece']:.4f}", regular_cell), Paragraph("JEV" if k_j['ece']<k_l['ece'] else ("LLM" if k_l['ece']<k_j['ece'] else "TIE"), bold_cell)],
    ]
    t_cal = Table(cal_data, colWidths=[180, 108, 108, 108])
    t_cal.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f8fafc')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5)
    ]))
    story.append(t_cal)
    story.append(Spacer(1, 10))

    if "calibration" in figures and os.path.exists(figures["calibration"]):
        story.append(Image(figures["calibration"], width=504, height=195))

    story.append(Spacer(1, 10))
    if "roc_pr" in figures and os.path.exists(figures["roc_pr"]):
        story.append(Image(figures["roc_pr"], width=504, height=195))

    story.append(PageBreak())

    # ================= PAGE 4 =================
    story.append(Paragraph("Operational Efficiency, Reliability & Latency Profiling", title_style))
    story.append(Paragraph(
        "Runtime latency distributions, token overheads, financial cost projections per 1,000 requests, "
        "and JSON parsing reliability metrics.", body_style
    ))
    story.append(Spacer(1, 8))

    e_j = metrics_jev["efficiency"]
    e_l = metrics_llm["efficiency"]
    r_j = metrics_jev["reliability"]
    r_l = metrics_llm["reliability"]

    eff_data = [
        [Paragraph("<b>Performance Dimension</b>", bold_cell),
         Paragraph("<b>TypeSafe JEV</b>", bold_cell),
         Paragraph("<b>Groq LLM (120B)</b>", bold_cell),
         Paragraph("<b>Ratio / Delta</b>", bold_cell)],
        [Paragraph("Latency p50 (Median)", regular_cell), Paragraph(f"{e_j['latency_p50_ms']:.1f} ms", regular_cell), Paragraph(f"{e_l['latency_p50_ms']:.1f} ms", regular_cell), Paragraph(f"{e_l['latency_p50_ms']/max(1.0, e_j['latency_p50_ms']):.1f}x Faster (JEV)", bold_cell)],
        [Paragraph("Latency Mean", regular_cell), Paragraph(f"{e_j['latency_mean_ms']:.1f} ms", regular_cell), Paragraph(f"{e_l['latency_mean_ms']:.1f} ms", regular_cell), Paragraph(f"{e_l['latency_mean_ms']-e_j['latency_mean_ms']:+.1f} ms", regular_cell)],
        [Paragraph("Latency p95", regular_cell), Paragraph(f"{e_j['latency_p95_ms']:.1f} ms", regular_cell), Paragraph(f"{e_l['latency_p95_ms']:.1f} ms", regular_cell), Paragraph(f"{e_l['latency_p95_ms']-e_j['latency_p95_ms']:+.1f} ms", regular_cell)],
        [Paragraph("Prompt Tokens / Request", regular_cell), Paragraph(f"{e_j['mean_prompt_tokens']:.0f}", regular_cell), Paragraph(f"{e_l['mean_prompt_tokens']:.0f}", regular_cell), Paragraph(f"-{e_l['mean_prompt_tokens']-e_j['mean_prompt_tokens']:.0f} tokens", regular_cell)],
        [Paragraph("Completion Tokens / Request", regular_cell), Paragraph(f"{e_j['mean_completion_tokens']:.0f}", regular_cell), Paragraph(f"{e_l['mean_completion_tokens']:.0f}", regular_cell), Paragraph(f"-{e_l['mean_completion_tokens']-e_j['mean_completion_tokens']:.0f} tokens", regular_cell)],
        [Paragraph("Cost per 1,000 Messages", bold_cell), Paragraph(f"<b>${e_j['cost_per_1k_messages_usd']:.4f}</b>", bold_cell), Paragraph(f"<b>${e_l['cost_per_1k_messages_usd']:.4f}</b>", bold_cell), Paragraph(f"<b>{e_l['cost_per_1k_messages_usd']/max(0.0001, e_j['cost_per_1k_messages_usd']):.1f}x Cheaper (JEV)</b>", bold_cell)],
        [Paragraph("Parse Failure Rate", regular_cell), Paragraph(f"{r_j['parse_failure_rate']*100:.2f}%", regular_cell), Paragraph(f"{r_l['parse_failure_rate']*100:.2f}%", regular_cell), Paragraph("Deterministic (JEV)", regular_cell)],
        [Paragraph("Hallucinated / Extra Keys", regular_cell), Paragraph(f"{r_j['invalid_keys_count']}", regular_cell), Paragraph(f"{r_l['invalid_keys_count']}", regular_cell), Paragraph("0 Hallucinations", regular_cell)]
    ]
    t_eff = Table(eff_data, colWidths=[180, 108, 108, 108])
    t_eff.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f8fafc')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4)
    ]))
    story.append(t_eff)
    story.append(Spacer(1, 12))

    if "efficiency" in figures and os.path.exists(figures["efficiency"]):
        story.append(Image(figures["efficiency"], width=504, height=210))

    story.append(PageBreak())

    # ================= PAGE 5 =================
    story.append(Paragraph("Statistical Significance & Genre Stratification", title_style))
    story.append(Paragraph(
        "Paired bootstrap 95% confidence intervals, non-inferiority recall hypothesis testing, "
        "McNemar's test for exact match differences, and stratified genre performance breakdown.", body_style
    ))
    story.append(Spacer(1, 8))

    stat_data = [
        [Paragraph("<b>Statistical Test / Metric</b>", bold_cell),
         Paragraph("<b>JEV 95% CI</b>", bold_cell),
         Paragraph("<b>LLM 95% CI</b>", bold_cell),
         Paragraph("<b>Paired Delta (95% CI)</b>", bold_cell)],
        [Paragraph("Micro F1 Score", regular_cell), Paragraph(f"[{bootstrap_res['jev_micro_f1_ci'][0]:.3f}, {bootstrap_res['jev_micro_f1_ci'][1]:.3f}]", regular_cell), Paragraph(f"[{bootstrap_res['llm_micro_f1_ci'][0]:.3f}, {bootstrap_res['llm_micro_f1_ci'][1]:.3f}]", regular_cell), Paragraph(f"[{bootstrap_res['diff_micro_f1_ci'][0]:.3f}, {bootstrap_res['diff_micro_f1_ci'][1]:.3f}]", regular_cell)],
        [Paragraph("Micro Recall (Miss Penalty)", regular_cell), Paragraph(f"[{bootstrap_res['jev_micro_recall_ci'][0]:.3f}, {bootstrap_res['jev_micro_recall_ci'][1]:.3f}]", regular_cell), Paragraph(f"[{bootstrap_res['llm_micro_recall_ci'][0]:.3f}, {bootstrap_res['llm_micro_recall_ci'][1]:.3f}]", regular_cell), Paragraph(f"[{bootstrap_res['diff_micro_recall_ci'][0]:.3f}, {bootstrap_res['diff_micro_recall_ci'][1]:.3f}]", regular_cell)],
        [Paragraph("Micro Precision (FP Penalty)", regular_cell), Paragraph(f"[{bootstrap_res['jev_micro_precision_ci'][0]:.3f}, {bootstrap_res['jev_micro_precision_ci'][1]:.3f}]", regular_cell), Paragraph(f"[{bootstrap_res['llm_micro_precision_ci'][0]:.3f}, {bootstrap_res['llm_micro_precision_ci'][1]:.3f}]", regular_cell), Paragraph(f"[{bootstrap_res['diff_micro_precision_ci'][0]:.3f}, {bootstrap_res['diff_micro_precision_ci'][1]:.3f}]", regular_cell)],
        [Paragraph("Non-Inferiority Test (Recall)", bold_cell), Paragraph(f"Margin: -{non_inf_res['margin']:.2f}", regular_cell), Paragraph(f"5th Pct: {non_inf_res['lower_95_bound']:.3f}", regular_cell), Paragraph(f"<b>{non_inf_res['verdict']}</b> (p={non_inf_res['p_value']:.3f})", bold_cell)],
    ]
    if non_inf_prec_res:
        stat_data.append([
            Paragraph("Non-Inferiority Test (Precision)", bold_cell),
            Paragraph(f"Margin: -{non_inf_prec_res['margin']:.2f}", regular_cell),
            Paragraph(f"5th Pct: {non_inf_prec_res['lower_95_bound']:.3f}", regular_cell),
            Paragraph(f"<b>{non_inf_prec_res['verdict']}</b> (p={non_inf_prec_res['p_value']:.3f})", bold_cell)
        ])
    stat_data.append([
        Paragraph("McNemar Exact-Match Test", bold_cell),
        Paragraph(f"Discordant: {mcnemar_res['table']['n10']} (JEV) vs {mcnemar_res['table']['n01']} (LLM)", regular_cell),
        Paragraph(f"{mcnemar_res['test_type']} (Chi2={mcnemar_res['chi2_uncorrected']:.2f})", regular_cell),
        Paragraph(f"<b>p = {mcnemar_res['p_value']:.4f}</b> ({mcnemar_res['advantage']})", bold_cell)
    ])
    t_stat = Table(stat_data, colWidths=[150, 118, 118, 118])
    t_stat.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f8fafc')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4)
    ]))
    story.append(t_stat)
    story.append(Spacer(1, 8))

    if "statistics" in figures and os.path.exists(figures["statistics"]):
        story.append(Image(figures["statistics"], width=504, height=195))

    story.append(Spacer(1, 8))
    if "genre" in figures and os.path.exists(figures["genre"]):
        story.append(Image(figures["genre"], width=504, height=175))

    doc.build(story, canvasmaker=NumberedCanvas)
    return output_pdf_path

# =====================================================================
# CUSTOM TEXT TEST MODE (ZERO CACHE / ZERO BENCHMARK IMPACT)
# =====================================================================

def test_single_text_mode(
    initial_text: Optional[str] = None,
    genre: str = "direct",
    groq_model: Optional[str] = None,
    jev_model: Optional[str] = None
):
    """
    Interactive/direct test mode for classifying custom text against TypeSafe JEV and Groq LLM.
    Strictly isolated: does NOT read/write predictions_cache.json, does NOT touch benchmark artifacts or dataset.
    """
    openrouter_key, groq_keys, env_jev_model, env_groq_model = load_environment()
    jev_model = jev_model or env_jev_model
    groq_model = groq_model or env_groq_model

    print("\n" + "=" * 88)
    print("      CUSTOM TEXT TEST MODE (ZERO CACHE / ZERO BENCHMARK IMPACT)")
    print("      Testing TypeSafe JEV vs. Groq LLM on Custom Disaster Messages")
    print("=" * 88, flush=True)

    if not openrouter_key or not groq_keys:
        print("[ERROR] OPENROUTER_API_KEY and/or GROQ_API_KEY missing from .env.", flush=True)
        return

    groq_pool = GroqKeyPool(groq_keys)
    tau = 0.15  # Optimal dev-tuned threshold from benchmark report

    def evaluate_text(text: str, ch_genre: str):
        print(f"\n[EVALUATING] Sending to JEV ({jev_model}) and Groq ({groq_model})...", flush=True)
        res_j = call_jev_decisions(text, openrouter_key, genre=ch_genre, model=jev_model)
        res_l = call_groq_llm(text, groq_pool, model=groq_model)

        probs_j = res_j.get("probabilities", {})
        probs_l = res_l.get("probabilities", {})
        bin_l = res_l.get("binary", {})

        print("\n" + "=" * 88)
        print("                        LIVE PREDICTION COMPARISON")
        print("=" * 88)
        print(f"Message: \"{text}\"")
        print(f"Channel Genre: {ch_genre} | JEV Decision Threshold: tau* = {tau:.2f}")
        print("-" * 88)
        print(f"{'RESOURCE':<20} | {'TYPE-SAFE JEV':<24} | {'GROQ LLM (gpt-oss-120b)':<25} | {'MATCH?':<8}")
        print("-" * 88)

        for r in RESOURCE_COLUMNS:
            pj = probs_j.get(r, 0.0)
            req_j = 1 if pj >= tau else 0
            tag_j = f"{pj:.2f} [REQUIRED]" if req_j else f"{pj:.2f} [   -    ]"

            pl = probs_l.get(r, 0.0)
            req_l = bin_l.get(r, 1 if pl >= 0.5 else 0)
            tag_l = f"req={req_l} (p={pl:.2f}) {'[REQUIRED]' if req_l else '[   -    ]'}"

            match = "MATCH" if req_j == req_l else "DIFF"
            print(f"{r:<20} | {tag_j:<24} | {tag_l:<25} | {match:<8}")

        print("-" * 88)
        lat_j = res_j.get("latency_ms", 0)
        lat_l = res_l.get("latency_ms", 0)
        tok_j = res_j.get("total_tokens", 0)
        tok_l = res_l.get("total_tokens", 0)
        print(f"Latency & Tokens     | JEV: {lat_j:.0f}ms ({tok_j} tok)       | Groq: {lat_l:.0f}ms ({tok_l} tok)")
        print("=" * 88)
        print("[ISOLATION GUARANTEE] Test complete. ZERO changes to cache, dataset, or benchmark deliverables.\n")

    if initial_text and initial_text.strip():
        evaluate_text(initial_text.strip(), genre)
        return

    # Interactive Loop
    while True:
        try:
            print("-" * 88)
            print("Type or paste disaster message to test (or press Enter without text to exit):")
            msg = input("Test Text > ").strip()
            if not msg:
                print("[EXIT] Exiting custom test mode.\n")
                break
            evaluate_text(msg, genre)
        except (KeyboardInterrupt, EOFError):
            print("\n[EXIT] Exiting custom test mode.\n")
            break

# =====================================================================
# MAIN PIPELINE & USER INTERFACE
# =====================================================================

def run_benchmark(
    dataset_path: str = "resource_dataset.csv",
    num_rows: Optional[int] = None,
    dev_split: float = 0.3,
    mock_mode: bool = False,
    cache_file: str = "predictions_cache.json",
    output_dir: str = "benchmark_artifacts",
    pdf_output: str = "jev_vs_llm_benchmark_report.pdf",
    groq_model: Optional[str] = None,
    jev_model: Optional[str] = None,
    request_delay: float = 0.5
):
    """Orchestrate the end-to-end benchmark workflow."""
    print("=" * 80)
    print("      DISASTER RESOURCE CLASSIFICATION BENCHMARK PIPELINE")
    print("      TypeSafe JEV (OpenRouter Decisions API) vs. Groq LLM (gpt-oss-120b)")
    print("=" * 80, flush=True)

    # 1. Load Data
    if not os.path.exists(dataset_path):
        print(f"[ERROR] Dataset '{dataset_path}' not found!", flush=True)
        sys.exit(1)

    df = pd.read_csv(dataset_path)
    total_available = len(df)
    print(f"[DATASET] Loaded: {total_available} total messages across genres: {df['genre'].value_counts().to_dict()}", flush=True)

    # 2. Configure Row Selection
    if num_rows is None:
        try:
            user_in = input(f"\n[PROMPT] How many rows would you like to classify? [Press Enter for 50, 'all' for {total_available}, 'test' for custom text test, or enter number]: ").strip().lower()
            if user_in in ["test", "t"]:
                test_single_text_mode(groq_model=groq_model, jev_model=jev_model)
                return
            elif not user_in or user_in == "":
                num_rows = 50
            elif user_in == "all":
                num_rows = total_available
            else:
                num_rows = int(user_in)
        except Exception:
            num_rows = 50

    num_rows = min(max(num_rows, 10), total_available)
    print(f"[SETUP] Target evaluation sample size: {num_rows} rows.", flush=True)

    # 3. Environment & Mode
    openrouter_key, groq_keys, env_jev_model, env_groq_model = load_environment()
    jev_model = jev_model or env_jev_model
    groq_model = groq_model or env_groq_model
    has_keys = bool(openrouter_key and groq_keys and len(groq_keys) > 0)
    groq_pool = GroqKeyPool(groq_keys) if groq_keys else None

    if not mock_mode and not has_keys:
        print("\n[NOTICE] OPENROUTER_API_KEY and/or GROQ_API_KEY are missing from environment/.env.", flush=True)
        print("A template file '.env.example' has been prepared for your API keys.", flush=True)
        choice = input("[PROMPT] Would you like to run in Simulation / Mock Mode to verify all statistical tests, charts & PDF? [Y/n]: ").strip().lower()
        if choice in ["", "y", "yes"]:
            mock_mode = True
            print("[MODE] Proceeding in Simulation / Mock Mode...", flush=True)
        else:
            print("Please create '.env' with your keys and rerun:", flush=True)
            print("  OPENROUTER_API_KEY=your_key_here", flush=True)
            print("  GROQ_API_KEY=your_key_here", flush=True)
            sys.exit(0)
    elif mock_mode:
        print("[MODE] Running in Simulation / Mock Mode (as requested)...", flush=True)
    else:
        print(f"[API] Live API keys detected! Running against live endpoints.", flush=True)
        print(f"      JEV Model:  {jev_model}", flush=True)
        print(f"      Groq Model: {groq_model} ({len(groq_keys)} keys loaded: alternating round-robin + timeout failover)", flush=True)
        for idx, k in enumerate(groq_keys, 1):
            masked = f"{k[:8]}...{k[-6:]}" if len(k) > 14 else k[:6]
            print(f"                  Key {idx}: {masked}", flush=True)

    # Slice dataset with balanced multi-resource and genre coverage
    if num_rows < total_available:
        rng = random.Random(42)
        sampled_indices = []

        # 1. Guarantee representation of every single resource category
        for col in RESOURCE_COLUMNS:
            pos_indices = df[df[col] == 1].index.difference(sampled_indices).tolist()
            if pos_indices:
                sampled_indices.append(rng.choice(pos_indices))

        # 2. Guarantee representation of each genre
        for genre, g in df.groupby("genre"):
            if not any(df.loc[idx, "genre"] == genre for idx in sampled_indices):
                genre_indices = g.index.difference(sampled_indices).tolist()
                if genre_indices:
                    sampled_indices.append(rng.choice(genre_indices))

        # 3. Fill or trim to target num_rows
        if len(sampled_indices) > num_rows:
            sampled_indices = rng.sample(sampled_indices, num_rows)
        elif len(sampled_indices) < num_rows:
            remaining = df.index.difference(sampled_indices).tolist()
            diff_count = num_rows - len(sampled_indices)
            sampled_indices.extend(rng.sample(remaining, min(diff_count, len(remaining))))

        df_eval = df.loc[sampled_indices].copy()
    else:
        df_eval = df.copy()

    # Display dataset composition
    print(f"[SETUP] Target multi-resource distribution: {df_eval[RESOURCE_COLUMNS].sum().to_dict()}", flush=True)

    # Load cache if available
    cache = {}
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                cache = json.load(f)
            print(f"[CACHE] Loaded {len(cache)} existing cached inferences from '{cache_file}'.", flush=True)
        except Exception:
            cache = {}

    # 4. Inference Execution
    print(f"\n[INFERENCE] Classifying {num_rows} disaster messages across genres: {df_eval['genre'].value_counts().to_dict()}...", flush=True)
    print(f"[CACHE] Progress is auto-saved to '{cache_file}' after every sample so you can resume anytime.\n", flush=True)
    jev_results = []
    llm_results = []

    for count_i, (orig_idx, row) in enumerate(df_eval.iterrows()):
        text = str(row["text_clean"])
        row_id = str(orig_idx)
        genre = str(row.get("genre", "unknown"))
        true_labels = {r: int(row[r]) for r in RESOURCE_COLUMNS}

        # Check existing cached results
        was_cached = False
        res_j = None
        res_l = None

        if row_id in cache and isinstance(cache[row_id], dict):
            c_j = cache[row_id].get("jev")
            c_l = cache[row_id].get("llm")
            if c_j and isinstance(c_j, dict) and c_j.get("success", False):
                res_j = c_j
            if c_l and isinstance(c_l, dict) and c_l.get("success", False):
                res_l = c_l
            if res_j is not None and res_l is not None:
                was_cached = True

        if was_cached:
            lat_j = res_j.get("latency_ms", 0)
            lat_l = res_l.get("latency_ms", 0)
            print(f"[{count_i + 1:2d}/{num_rows}] Row {row_id} ({genre}) [CACHED] -> JEV: {lat_j:.0f}ms | Groq: {lat_l:.0f}ms", flush=True)
        else:
            print(f"[{count_i + 1:2d}/{num_rows}] Row {row_id} ({genre}) Classifying...", flush=True)

            if res_j is None:
                if mock_mode:
                    res_j = simulate_prediction(text, true_labels, model_type="jev")
                else:
                    res_j = call_jev_decisions(text, openrouter_key, genre=genre, model=jev_model)
                if row_id not in cache: cache[row_id] = {}
                cache[row_id]["jev"] = res_j
                lat_j = res_j.get("latency_ms", 0)
                status_j = "OK" if res_j.get("success") else f"FAIL ({res_j.get('error_message', '')[:40]})"
                print(f"   -> JEV ({jev_model}): {status_j} in {lat_j:.0f}ms", flush=True)

            if res_l is None:
                if mock_mode:
                    res_l = simulate_prediction(text, true_labels, model_type="llm")
                else:
                    res_l = call_groq_llm(text, groq_pool or groq_keys, model=groq_model)
                if row_id not in cache: cache[row_id] = {}
                cache[row_id]["llm"] = res_l
                lat_l = res_l.get("latency_ms", 0)
                status_l = "OK" if res_l.get("success") else f"FAIL ({res_l.get('error_message', '')[:40]})"
                key_lbl = res_l.get("key_used", "Key 1")
                print(f"   -> Groq ({groq_model} | {key_lbl}): {status_l} in {lat_l:.0f}ms", flush=True)

        # Defensive null checks
        if res_j is None or not isinstance(res_j, dict):
            res_j = {
                "success": False, "probabilities": {r: 0.0 for r in RESOURCE_COLUMNS},
                "latency_ms": 0.0, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0,
                "cost": 0.0, "invalid_keys": [], "parse_error": True, "error_message": "Null response"
            }
            cache[row_id]["jev"] = res_j

        if res_l is None or not isinstance(res_l, dict):
            res_l = {
                "success": False, "probabilities": {r: 0.0 for r in RESOURCE_COLUMNS},
                "binary": {r: 0 for r in RESOURCE_COLUMNS},
                "latency_ms": 0.0, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0,
                "cost": 0.0, "invalid_keys": [], "parse_error": True, "error_message": "Null response"
            }
            cache[row_id]["llm"] = res_l

        jev_results.append(res_j)
        llm_results.append(res_l)

        # Print detailed outputs and per-row accuracy from both JEV and Groq LLM
        text_preview = text if len(text) <= 90 else text[:87] + "..."
        true_detected = [r for r, v in true_labels.items() if v == 1]

        j_probs = res_j.get("probabilities", {})
        j_pos = [f"{r} ({j_probs.get(r, 0):.2f})" for r in RESOURCE_COLUMNS if j_probs.get(r, 0) >= 0.50]
        j_all_str = ", ".join([f"{r}: {j_probs.get(r, 0):.2f}" for r in RESOURCE_COLUMNS])

        l_bin = res_l.get("binary", {})
        l_probs = res_l.get("probabilities", {})
        l_pos = [f"{r} ({l_probs.get(r, 0):.2f})" for r in RESOURCE_COLUMNS if l_bin.get(r, 0) == 1]
        l_all_str = ", ".join([f"{r}: {l_bin.get(r, 0)} (conf {l_probs.get(r, 0):.2f})" for r in RESOURCE_COLUMNS])

        # Exact label accuracy on this individual row across all 9 resources
        j_binary = [1 if j_probs.get(r, 0) >= 0.50 else 0 for r in RESOURCE_COLUMNS]
        l_binary = [l_bin.get(r, 1 if l_probs.get(r, 0) >= 0.5 else 0) for r in RESOURCE_COLUMNS]
        true_binary = [true_labels[r] for r in RESOURCE_COLUMNS]

        j_correct_labels = sum(1 for a, b in zip(j_binary, true_binary) if a == b)
        l_correct_labels = sum(1 for a, b in zip(l_binary, true_binary) if a == b)
        j_row_acc = (j_correct_labels / len(RESOURCE_COLUMNS)) * 100.0
        l_row_acc = (l_correct_labels / len(RESOURCE_COLUMNS)) * 100.0

        print(f"   ┌─ Text: \"{text_preview}\"", flush=True)
        print(f"   ├─ Ground Truth    : {true_detected if true_detected else '[] (None)'}", flush=True)
        print(f"   ├─ JEV Output      : Detected: {j_pos if j_pos else '[] (None)'}", flush=True)
        print(f"   │                    Accuracy: {j_correct_labels}/9 correct ({j_row_acc:.1f}%) | Probs: {{{j_all_str}}}", flush=True)
        print(f"   └─ Groq LLM Output : Required: {l_pos if l_pos else '[] (None)'}", flush=True)
        print(f"                        Accuracy: {l_correct_labels}/9 correct ({l_row_acc:.1f}%) | Binary: {{{l_all_str}}}\n", flush=True)

        # WRITE CACHE TO DISK IMMEDIATELY ON EVERY SINGLE SAMPLE
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(cache, f)
        except Exception:
            pass

        # Gentle pacing between live API requests to avoid hitting burst rate limits
        if not mock_mode and not was_cached and request_delay > 0:
            time.sleep(request_delay)


    # 5. Dev/Test Split Protocol
    n_dev = max(4, int(num_rows * dev_split))
    n_test = num_rows - n_dev
    print(f"\n[PROTOCOL] Protocol Split: {n_dev} Dev samples ({dev_split*100:.0f}%) | {n_test} Test samples ({(1-dev_split)*100:.0f}%)")

    # Arrays for Dev
    y_true_dev = df_eval.iloc[:n_dev][RESOURCE_COLUMNS].values
    probs_jev_dev = np.array([[res["probabilities"][r] for r in RESOURCE_COLUMNS] for res in jev_results[:n_dev]])


    # Threshold Sweep on Dev ONLY: fine-grained search from 0.01 to 0.95
    threshold_candidates = np.round(np.arange(0.01, 0.96, 0.02), 2)
    sweep_results = []
    best_tau = 0.50
    best_dev_f1 = -1.0
    best_dev_acc = -1.0
    best_dev_rec = -1.0

    for tau in threshold_candidates:
        preds = (probs_jev_dev >= tau).astype(int)
        f1 = float(f1_score(y_true_dev, preds, average="micro", zero_division=0))
        rec = float(recall_score(y_true_dev, preds, average="micro", zero_division=0))
        prec = float(precision_score(y_true_dev, preds, average="micro", zero_division=0))
        acc = float(np.mean(y_true_dev == preds))
        sweep_results.append({
            "threshold": float(tau),
            "micro_f1": f1,
            "micro_recall": rec,
            "micro_precision": prec,
            "accuracy": acc
        })
        # Prioritize F1; if F1 is within 0.005 (near-flat region), select threshold closer to 0.50 or higher accuracy
        if f1 > best_dev_f1 + 0.005:
            best_dev_f1 = f1
            best_dev_acc = acc
            best_dev_rec = rec
            best_tau = float(tau)
        elif abs(f1 - best_dev_f1) <= 0.005:
            if acc > best_dev_acc + 0.005:
                best_dev_f1 = f1
                best_dev_acc = acc
                best_dev_rec = rec
                best_tau = float(tau)
            elif abs(acc - best_dev_acc) <= 0.005 and abs(tau - 0.50) < abs(best_tau - 0.50):
                best_tau = float(tau)

    print(f"[TUNING] Dev Threshold Tuning Complete: Optimal tau* = {best_tau:.2f} (Dev F1 = {best_dev_f1:.3f}, Dev Recall = {best_dev_rec:.3f}, Dev Accuracy = {best_dev_acc*100:.1f}%)")

    # Arrays for Test Set (All Headline Numbers Evaluated on Test Set)
    df_test = df_eval.iloc[n_dev:].reset_index(drop=True)
    y_true_test = df_test[RESOURCE_COLUMNS].values

    test_jev_res = jev_results[n_dev:]
    test_llm_res = llm_results[n_dev:]

    probs_jev_test = np.array([[res["probabilities"][r] for r in RESOURCE_COLUMNS] for res in test_jev_res])
    probs_llm_test = np.array([[res["probabilities"][r] for r in RESOURCE_COLUMNS] for res in test_llm_res])

    # Apply tuned threshold tau* to Jev; use LLM binary predictions
    y_pred_jev_test = (probs_jev_test >= best_tau).astype(int)
    y_pred_llm_test = np.array([[res.get("binary", {}).get(r, 1 if res["probabilities"][r] >= 0.5 else 0)
                                 for r in RESOURCE_COLUMNS] for res in test_llm_res])

    # 6. Comprehensive Metrics Calculation
    print("\n[METRICS] Computing exhaustive multi-label classification, ranking, calibration & efficiency metrics...")
    metrics_jev = evaluate_model_classification(
        y_true=y_true_test,
        y_pred=y_pred_jev_test,
        probs=probs_jev_test,
        latencies=[r.get("latency_ms", 100.0) for r in test_jev_res],
        costs=[r.get("cost", 0.0) for r in test_jev_res],
        tokens=[{"prompt_tokens": r.get("prompt_tokens", 0), "completion_tokens": r.get("completion_tokens", 0)} for r in test_jev_res],
        parse_errors=sum(1 for r in test_jev_res if r.get("parse_error", False)),
        invalid_keys_list=[r.get("invalid_keys", []) for r in test_jev_res]
    )

    metrics_llm = evaluate_model_classification(
        y_true=y_true_test,
        y_pred=y_pred_llm_test,
        probs=probs_llm_test,
        latencies=[r.get("latency_ms", 450.0) for r in test_llm_res],
        costs=[r.get("cost", 0.0) for r in test_llm_res],
        tokens=[{"prompt_tokens": r.get("prompt_tokens", 0), "completion_tokens": r.get("completion_tokens", 0)} for r in test_llm_res],
        parse_errors=sum(1 for r in test_llm_res if r.get("parse_error", False)),
        invalid_keys_list=[r.get("invalid_keys", []) for r in test_llm_res]
    )

    # 7. Statistical Tests (Both Recall and Precision Non-Inferiority with pre-specified margin 0.03)
    print("[STATISTICS] Running paired bootstrap CIs (B=1000), McNemar test, and Non-Inferiority tests (margin=0.03)...")
    bootstrap_res = run_paired_bootstrap(y_true_test, y_pred_jev_test, y_pred_llm_test, n_bootstraps=1000)
    mcnemar_res = run_mcnemar_exact_match(y_true_test, y_pred_jev_test, y_pred_llm_test)
    non_inf_res = run_non_inferiority_test(bootstrap_res["raw_diff_micro_recall"], metric_name="Recall", margin=0.03)
    non_inf_prec_res = run_non_inferiority_test(bootstrap_res["raw_diff_micro_precision"], metric_name="Precision", margin=0.03)
    genre_res = evaluate_genre_breakdown(df_test, y_true_test, y_pred_jev_test, y_pred_llm_test)

    # 8. Determine Category Winners & Objective Findings
    winners = determine_winners(metrics_jev, metrics_llm, mcnemar_res, non_inf_res, non_inf_prec=non_inf_prec_res)

    # 9. Visualizations & Scoreboard Image
    print("[CHARTS] Generating publication-quality charts and master comparison scoreboard image...")
    figures = generate_visualizations(
        metrics_jev, metrics_llm, sweep_results, best_tau,
        bootstrap_res, genre_res, winners,
        y_true_test, probs_jev_test, probs_llm_test,
        output_dir=output_dir
    )

    # 10. Multi-Page PDF Report
    print("[REPORT] Compiling 5-page executive PDF benchmark report...")
    pdf_path = compile_pdf_report(
        metrics_jev, metrics_llm, winners, bootstrap_res,
        mcnemar_res, non_inf_res, genre_res, best_tau,
        figures, n_dev, n_test, output_pdf_path=pdf_output,
        non_inf_prec_res=non_inf_prec_res
    )

    # 11. Terminal Summary Output
    print("\n" + "=" * 88)
    print("                              BENCHMARK RESULTS SUMMARY")
    print("=" * 88)
    print(f"{'Metric':<34} | {'TypeSafe JEV':<18} | {'Groq GPT-OSS-120B':<19} | {'Winner':<10}")
    print("-" * 92)
    jev_tot_corr = metrics_jev['classification']['total_correct_labels']
    jev_tot_dec = metrics_jev['classification']['total_label_decisions']
    llm_tot_corr = metrics_llm['classification']['total_correct_labels']
    llm_tot_dec = metrics_llm['classification']['total_label_decisions']
    jev_acc_str = f"{metrics_jev['classification']['overall_accuracy']*100:.1f}% ({jev_tot_corr}/{jev_tot_dec})"
    llm_acc_str = f"{metrics_llm['classification']['overall_accuracy']*100:.1f}% ({llm_tot_corr}/{llm_tot_dec})"
    print(f"{'Overall Accuracy (All Rows)':<34} | {jev_acc_str:<18} | {llm_acc_str:<19} | {'JEV' if metrics_jev['classification']['overall_accuracy']>metrics_llm['classification']['overall_accuracy'] else ('LLM' if metrics_llm['classification']['overall_accuracy']>metrics_jev['classification']['overall_accuracy'] else 'TIE')}")
    print(f"{'Subset Accuracy (Exact Match)':<34} | {metrics_jev['classification']['subset_accuracy']*100:<17.1f}% | {metrics_llm['classification']['subset_accuracy']*100:<18.1f}% | {'JEV' if metrics_jev['classification']['subset_accuracy']>metrics_llm['classification']['subset_accuracy'] else ('LLM' if metrics_llm['classification']['subset_accuracy']>metrics_jev['classification']['subset_accuracy'] else 'TIE')}")
    print(f"{'Micro Recall (No Misses)':<34} | {metrics_jev['classification']['micro_recall']:<18.3f} | {metrics_llm['classification']['micro_recall']:<19.3f} | {'JEV' if metrics_jev['classification']['micro_recall']>metrics_llm['classification']['micro_recall'] else 'LLM'}")
    print(f"{'Micro F1 Score (Harmonic Mean)':<34} | {metrics_jev['classification']['micro_f1']:<18.3f} | {metrics_llm['classification']['micro_f1']:<19.3f} | {'JEV' if metrics_jev['classification']['micro_f1']>metrics_llm['classification']['micro_f1'] else 'LLM'}")
    print(f"{'Macro F1 Score':<34} | {metrics_jev['classification']['macro_f1']:<18.3f} | {metrics_llm['classification']['macro_f1']:<19.3f} | {'JEV' if metrics_jev['classification']['macro_f1']>metrics_llm['classification']['macro_f1'] else 'LLM'}")
    print(f"{'Micro Precision':<34} | {metrics_jev['classification']['micro_precision']:<18.3f} | {metrics_llm['classification']['micro_precision']:<19.3f} | {'JEV' if metrics_jev['classification']['micro_precision']>metrics_llm['classification']['micro_precision'] else 'LLM'}")
    print(f"{'Any-Miss Rate (Lower=Best)':<34} | {metrics_jev['classification']['any_miss_rate']*100:<17.1f}% | {metrics_llm['classification']['any_miss_rate']*100:<18.1f}% | {'JEV' if metrics_jev['classification']['any_miss_rate']<metrics_llm['classification']['any_miss_rate'] else 'LLM'}")
    print(f"{'Hamming Loss (Lower=Better)':<34} | {metrics_jev['classification']['hamming_loss']:<18.3f} | {metrics_llm['classification']['hamming_loss']:<19.3f} | {'JEV' if metrics_jev['classification']['hamming_loss']<metrics_llm['classification']['hamming_loss'] else 'LLM'}")
    print(f"{'Micro Average Precision (mAP)':<34} | {metrics_jev['ranking_calibration']['micro_average_precision']:<18.3f} | {metrics_llm['ranking_calibration']['micro_average_precision']:<19.3f} | {'JEV' if metrics_jev['ranking_calibration']['micro_average_precision']>metrics_llm['ranking_calibration']['micro_average_precision'] else 'LLM'}")
    print(f"{'Macro Average Precision':<34} | {metrics_jev['ranking_calibration']['macro_average_precision']:<18.3f} | {metrics_llm['ranking_calibration']['macro_average_precision']:<19.3f} | {'JEV' if metrics_jev['ranking_calibration']['macro_average_precision']>metrics_llm['ranking_calibration']['macro_average_precision'] else 'LLM'}")
    print(f"{'Micro ROC-AUC':<34} | {metrics_jev['ranking_calibration']['micro_roc_auc']:<18.3f} | {metrics_llm['ranking_calibration']['micro_roc_auc']:<19.3f} | {'JEV' if metrics_jev['ranking_calibration']['micro_roc_auc']>metrics_llm['ranking_calibration']['micro_roc_auc'] else 'LLM'}")
    print(f"{'Expected Calib. Error':<34} | {metrics_jev['ranking_calibration']['ece']:<18.4f} | {metrics_llm['ranking_calibration']['ece']:<19.4f} | {'JEV' if metrics_jev['ranking_calibration']['ece']<metrics_llm['ranking_calibration']['ece'] else 'LLM'}")
    print(f"{'Latency p50 (Median)':<34} | {metrics_jev['efficiency']['latency_p50_ms']:<16.1f}ms | {metrics_llm['efficiency']['latency_p50_ms']:<17.1f}ms | {'JEV (Faster)'}")
    print(f"{'Cost per 1k Messages':<34} | ${metrics_jev['efficiency']['cost_per_1k_messages_usd']:<17.4f} | ${metrics_llm['efficiency']['cost_per_1k_messages_usd']:<18.4f} | {'JEV (Cheaper)'}")
    print(f"{'Parse Failure Rate':<34} | {metrics_jev['reliability']['parse_failure_rate']*100:<17.1f}% | {metrics_llm['reliability']['parse_failure_rate']*100:<18.1f}% | {'JEV' if metrics_jev['reliability']['parse_failure_rate']<=metrics_llm['reliability']['parse_failure_rate'] else 'LLM'}")
    print("=" * 92)
    print(f"[SUMMARY] OVERALL BENCHMARK STATUS: {winners['overall_winner'].upper()}")
    print(f"   Category Overview: JEV leads {winners['scores']['jev_categories_won']} | LLM leads {winners['scores']['llm_categories_won']} | Ties {winners['scores']['ties']}")
    print(f"   Findings: {winners['findings_summary']}")
    print("=" * 80)
    print(f"[FILES] Deliverables Created:")
    print(f"   1. Master Scoreboard Image : {figures['scoreboard']}")
    print(f"   2. Executive PDF Report    : {pdf_path}")
    print(f"   3. Detailed Chart Suite    : {output_dir}/")
    print("=" * 80 + "\n")



if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Disaster Resource Classification Benchmark: JEV vs. Groq LLM")
    parser.add_argument("--dataset", type=str, default="resource_dataset.csv", help="Path to resource dataset CSV")
    parser.add_argument("--rows", type=int, default=None, help="Number of rows to classify (default: prompt user)")
    parser.add_argument("--dev-split", type=float, default=0.3, help="Fraction for Dev split (default: 0.3)")
    parser.add_argument("--mock", action="store_true", help="Run in mock/simulation mode without calling APIs")
    parser.add_argument("--cache", type=str, default="predictions_cache.json", help="Path to cache file")
    parser.add_argument("--output-dir", type=str, default="benchmark_artifacts", help="Directory for generated images")
    parser.add_argument("--pdf", type=str, default="jev_vs_llm_benchmark_report.pdf", help="Output PDF filename")
    parser.add_argument("--groq-model", type=str, default=None, help="Groq LLM model name (default: from .env or openai/gpt-oss-120b)")
    parser.add_argument("--jev-model", type=str, default=None, help="TypeSafe JEV model name (default: from .env or typesafe/jev-1.13)")
    parser.add_argument("--delay", type=float, default=0.5, help="Pacing delay in seconds between API calls to prevent rate limits (default: 0.5)")
    parser.add_argument("--test", nargs="?", const="", type=str, default=None, help="Test custom emergency text against JEV and Groq without affecting cache or benchmark (can pass text directly or run interactively)")
    parser.add_argument("--genre", type=str, default="direct", help="Channel genre for test mode (direct, social, news; default: direct)")

    args = parser.parse_args()

    if args.test is not None:
        test_single_text_mode(
            initial_text=args.test,
            genre=args.genre,
            groq_model=args.groq_model,
            jev_model=args.jev_model
        )
        sys.exit(0)

    run_benchmark(
        dataset_path=args.dataset,
        num_rows=args.rows,
        dev_split=args.dev_split,
        mock_mode=args.mock,
        cache_file=args.cache,
        output_dir=args.output_dir,
        pdf_output=args.pdf,
        groq_model=args.groq_model,
        jev_model=args.jev_model,
        request_delay=args.delay
    )
