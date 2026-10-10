"""
AASHRAY ML Classifier Service
Loads best_model.pkl + tfidf_vectorizer.pkl + metadata.json at startup.
Exposes POST /classify → returns disaster probability + label.
"""

import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import pickle
import json
import re
import os
import time
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

# ──────────────────────────────────────────────────────────────────────────────
# Paths — go one level up from ml_service/ to find root artifacts and RAG folder
# ──────────────────────────────────────────────────────────────────────────────
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
load_dotenv(os.path.join(ROOT, ".env"))
load_dotenv(os.path.join(ROOT, "NEW HYPOTHESIS", ".env"))
load_dotenv(os.path.join(ROOT, "NEW HYPOTHESIS", "jev + llm", ".env"))

JEV_LLM_DIR = os.path.join(ROOT, "NEW HYPOTHESIS", "jev + llm")
LLM_DIR = os.path.join(ROOT, "NEW HYPOTHESIS", "llm + llm")
for p in [JEV_LLM_DIR, LLM_DIR, ROOT]:
    if p not in sys.path:
        sys.path.insert(0, p)

MODEL_PATH      = os.path.join(ROOT, "best_model.pkl")
VECTORIZER_PATH = os.path.join(ROOT, "tfidf_vectorizer.pkl")
METADATA_PATH   = os.path.join(ROOT, "metadata.json")

# ──────────────────────────────────────────────────────────────────────────────
# Load once at startup
# ──────────────────────────────────────────────────────────────────────────────
print("Loading ML artifacts…")

with open(MODEL_PATH, "rb") as f:
    model = pickle.load(f)

with open(VECTORIZER_PATH, "rb") as f:
    vectorizer = pickle.load(f)

try:
    with open(METADATA_PATH, "r") as f:
        metadata = json.load(f)
    THRESHOLD = 0.14
    MODEL_NAME = metadata.get("model_name", "Unknown")
except Exception as e:
    print(f"Warning: Could not load metadata.json ({e}), using default threshold 0.14")
    THRESHOLD = 0.14
    MODEL_NAME = "Linear SVM"

print(f"✓ Loaded model: {MODEL_NAME} | threshold: {THRESHOLD:.4f}")

try:
    from sentence_transformers import SentenceTransformer, util
    print("Loading SentenceTransformer ('all-MiniLM-L6-v2')…")
    embedder = SentenceTransformer('all-MiniLM-L6-v2')
    print("✓ SentenceTransformer loaded successfully.")
except Exception as e:
    print(f"Warning: Could not load SentenceTransformer ({e}). /similarity endpoint will be disabled.")
    embedder = None

def semantic_similarity(text1: str, text2: str) -> float:
    if not embedder:
        raise RuntimeError("SentenceTransformer model is not loaded.")
    embeddings = embedder.encode([text1, text2])
    score = util.cos_sim(embeddings[0], embeddings[1]).item()
    return float(score)

try:
    import base64
    import io
    from PIL import Image
    import torch
    from transformers import BlipProcessor, BlipForConditionalGeneration
    print("Loading BLIP image captioning model ('Salesforce/blip-image-captioning-base')…")
    blip_processor = BlipProcessor.from_pretrained("Salesforce/blip-image-captioning-base")
    blip_model = BlipForConditionalGeneration.from_pretrained("Salesforce/blip-image-captioning-base")
    print("✓ BLIP image model loaded successfully.")
except Exception as e:
    print(f"Warning: Could not load BLIP model ({e}). /caption-image endpoint will be disabled.")
    blip_processor = None
    blip_model = None

def caption_image(base64_image_str: str) -> str:
    if not blip_processor or not blip_model:
        raise RuntimeError("BLIP image captioning model is not loaded.")
    
    # Strip data URL prefix if present
    if "," in base64_image_str:
        base64_image_str = base64_image_str.split(",")[1]
    
    image_bytes = base64.b64decode(base64_image_str)
    raw_image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    
    inputs = blip_processor(raw_image, return_tensors="pt")
    out = blip_model.generate(**inputs, max_new_tokens=50)
    caption = blip_processor.decode(out[0], skip_special_tokens=True)
    return caption.strip()

try:
    from pipeline_b import DisasterRAGPipelineB
    print("Loading TypeSafe JEV + LLM Disaster RAG Pipeline…")
    rag_pipeline = DisasterRAGPipelineB(pipeline_name="jev_llm")
    print("✓ Disaster RAG Pipeline loaded successfully.")
except Exception as e:
    print(f"Warning: Could not load Disaster RAG Pipeline ({e}). /rag/plan endpoint will be disabled.")
    rag_pipeline = None

try:
    from pre_rag_gate import classify_pre_rag, re_evaluate_pre_rag
    print("✓ Pre-RAG Gatekeeper module loaded successfully.")
except Exception as e:
    print(f"Warning: Could not load Pre-RAG Gatekeeper ({e}).")
    classify_pre_rag = None
    re_evaluate_pre_rag = None

# ──────────────────────────────────────────────────────────────────────────────
# Text cleaner — must match the logic used during training
# ──────────────────────────────────────────────────────────────────────────────
def clean_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r"http\S+|www\.\S+", " ", text)        # remove URLs
    text = re.sub(r"@\w+", " ", text)                     # remove @mentions
    text = re.sub(r"#(\w+)", r"\1", text)                 # keep hashtag word, drop #
    text = re.sub(r"[^a-z0-9\s]", " ", text)              # keep only alphanumeric
    text = re.sub(r"\s+", " ", text).strip()
    return text


# ──────────────────────────────────────────────────────────────────────────────
# Predict function
# ──────────────────────────────────────────────────────────────────────────────
def predict(text: str) -> dict:
    cleaned   = clean_text(text)
    features  = vectorizer.transform([cleaned])

    # Use predict_proba if available (calibrated SVM or LR), else decision_function
    if hasattr(model, "predict_proba"):
        prob = float(model.predict_proba(features)[0, 1])
    else:
        # LinearSVC — fallback to scaled decision function
        score = model.decision_function(features)[0]
        # Sigmoid scaling so it looks like a probability
        import math
        prob = 1.0 / (1.0 + math.exp(-score))

    label = "disaster" if prob >= THRESHOLD else "non_relevant"
    return {
        "probability": round(prob, 4),
        "label": label,
        "threshold_used": THRESHOLD,
        "model_name": MODEL_NAME,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Flask app
# ──────────────────────────────────────────────────────────────────────────────
app = Flask(__name__)
CORS(app)  # Allow Node.js backend (same host, different port) to call


@app.get("/health")
def health():
    return jsonify({"status": "ok", "model": MODEL_NAME, "threshold": THRESHOLD})


@app.post("/classify")
def classify():
    data = request.get_json(silent=True)
    if not data or "text" not in data:
        return jsonify({"error": "Missing 'text' field in JSON body"}), 400

    text = data["text"]
    if not text or not text.strip():
        return jsonify({"error": "Text is empty"}), 400

    result = predict(text)

    # Optionally run RAG pipeline if disaster detected and requested
    if data.get("include_rag") and result.get("label") == "disaster" and rag_pipeline:
        scenario_id = data.get("scenario_id", f"DISASTER-{int(time.time())}")
        try:
            plan = rag_pipeline.run(scenario_id=scenario_id, scenario=text)
            last_rec = rag_pipeline.last_run_record or {}
            jev_assess = last_rec.get("jev_assessment") or (plan.get("jev_assessment") if isinstance(plan, dict) else None)
            result["ragReport"] = {
                "success": True if plan else False,
                "scenario_id": scenario_id,
                "plan": plan,
                "pipeline": "jev_llm",
                "stage_1_resources": last_rec.get("stage_1_resources", []),
                "stage_1_probabilities": last_rec.get("stage_1_probabilities", {}),
                "jev_assessment": jev_assess,
                "retrieved_chunks": last_rec.get("retrieved_chunks", []),
                "latency": last_rec.get("latency", {}),
                "tokens": last_rec.get("tokens", {})
            }
        except Exception as rag_err:
            result["rag_error"] = str(rag_err)

    return jsonify(result)


@app.post("/pre-rag/classify")
def pre_rag_classify_endpoint():
    """
    Initial Pre-RAG Completeness & Severity Classification.
    Classifies request as Critical, Non-Critical, or Uncertain.
    Generates clarifying questions if Non-Critical or Uncertain.
    """
    if not classify_pre_rag:
        return jsonify({"error": "Pre-RAG classifier module not available"}), 503

    data = request.get_json(silent=True) or {}
    scenario = (data.get("scenario") or data.get("query") or "").strip()
    history = data.get("history")
    follow_up_answer = data.get("clarification_answer") or data.get("follow_up_answer")

    if not scenario:
        return jsonify({"error": "Missing 'scenario' or 'query' field in JSON body"}), 400

    try:
        result = classify_pre_rag(query=scenario, history=history, follow_up_answer=follow_up_answer)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.post("/pre-rag/re-evaluate")
def pre_rag_re_evaluate_endpoint():
    """
    Re-evaluate user request after caller answers clarifying questions.
    If severity escalates -> allocates resources (can_proceed_to_rag = True).
    If not -> routes to low-tier support (can_proceed_to_rag = False).
    """
    if not re_evaluate_pre_rag:
        return jsonify({"error": "Pre-RAG re-evaluation module not available"}), 503

    data = request.get_json(silent=True) or {}
    scenario = (data.get("scenario") or data.get("query") or "").strip()
    follow_up_answer = (data.get("clarification_answer") or data.get("follow_up_answer") or "").strip()
    history = data.get("history")

    if not scenario or not follow_up_answer:
        return jsonify({"error": "Both 'scenario' and 'clarification_answer' fields are required"}), 400

    try:
        result = re_evaluate_pre_rag(initial_query=scenario, follow_up_answer=follow_up_answer, history=history)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.post("/rag/plan")
def rag_plan_endpoint():
    """
    Execute TypeSafe JEV + LLM Disaster RAG Pipeline (Pipeline B).
    Pre-RAG intake gate evaluates completeness and severity first.
    If uncertain -> prompts for clarification questions.
    If critical / escalated -> retrieves authoritative SOPs and synthesizes dispatch plan.
    """
    if not rag_pipeline:
        return jsonify({"error": "Disaster RAG pipeline is not available"}), 503

    data = request.get_json(silent=True)
    if not data or "scenario" not in data:
        return jsonify({"error": "Missing 'scenario' field in JSON body"}), 400

    scenario = data["scenario"]
    if not scenario or not scenario.strip():
        return jsonify({"error": "Scenario text is empty"}), 400

    scenario_id = data.get("scenario_id", f"AASHRAY-{int(time.time())}")
    clarification_answer = data.get("clarification_answer")
    bypass_pre_rag = data.get("bypass_pre_rag", False)

    try:
        plan = rag_pipeline.run(
            scenario_id=scenario_id,
            scenario=scenario,
            clarification_answer=clarification_answer,
            bypass_pre_rag=bypass_pre_rag
        )
        if not plan:
            return jsonify({"error": "Failed to generate RAG plan"}), 500

        return jsonify({
            "success": True,
            "scenario_id": scenario_id,
            "pipeline": "jev_v3_rag",
            "is_disaster_related": plan.get("is_disaster_related", True),
            "can_proceed_to_rag": plan.get("can_proceed_to_rag", True),
            "needs_clarification": plan.get("needs_clarification", False),
            "pre_rag_intake": plan.get("pre_rag_intake"),
            "severity": plan.get("severity"),
            "action": plan.get("action"),
            "clarifying_questions": plan.get("clarifying_questions", []),
            "missing_info": plan.get("missing_info", []),
            "disaster_assessment": plan.get("disaster_assessment"),
            "plan": plan,
            "assessment": plan.get("assessment"),
            "situation": plan.get("situation"),
            "person_message": plan.get("person_message"),
            "dispatcher_notes": plan.get("dispatcher_notes"),
            "resources": plan.get("resources"),
            "selected_resources": plan.get("selected_resources", []),
            "not_selected_resources": plan.get("not_selected_resources", []),
            "non_selected_resources": plan.get("not_selected_resources", []),
            "raw_probabilities": plan.get("raw_probabilities", {}),
            "excerpts": plan.get("excerpts", []),
            "census_context": plan.get("census_context"),
            "place": plan.get("place"),
            "agencies": plan.get("agencies", []),
            "latency": plan.get("latency", {}),
            "telemetry": plan.get("telemetry", {})
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500



@app.post("/similarity")
def similarity():
    data = request.get_json(silent=True)
    if not data or "text1" not in data or "text2" not in data:
        return jsonify({"error": "Missing 'text1' or 'text2' field in JSON body"}), 400

    try:
        score = semantic_similarity(data["text1"], data["text2"])
        return jsonify({"similarity": round(score, 4)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.post("/caption-image")
def caption_image_endpoint():
    data = request.get_json(silent=True)
    if not data or "image" not in data:
        return jsonify({"error": "Missing 'image' base64 string in JSON body"}), 400

    try:
        caption = caption_image(data["image"])
        return jsonify({"caption": caption})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("ML_PORT", 5001))
    print(f"🚀 ML service starting on http://0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
