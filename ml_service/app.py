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

JEV_LLM_DIR = os.path.join(ROOT, "NEW HYPOTHESIS", "jev + llm")
if JEV_LLM_DIR not in sys.path:
    sys.path.insert(0, JEV_LLM_DIR)

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

# ──────────────────────────────────────────────────────────────────────────────
# Load TypeSafe JEV + LLM Disaster RAG Pipeline (Pipeline B)
# ──────────────────────────────────────────────────────────────────────────────
try:
    from pipeline_b import DisasterRAGPipelineB
    print("Loading TypeSafe JEV + LLM Disaster RAG Pipeline…")
    rag_pipeline = DisasterRAGPipelineB(pipeline_name="jev_llm")
    print("✓ Disaster RAG Pipeline loaded successfully.")
except Exception as e:
    print(f"Warning: Could not load Disaster RAG Pipeline ({e}). /rag/plan endpoint will be disabled.")
    rag_pipeline = None

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
            result["ragReport"] = {
                "success": True if plan else False,
                "scenario_id": scenario_id,
                "plan": plan,
                "pipeline": "jev_llm",
                "stage_1_resources": last_rec.get("stage_1_resources", []),
                "stage_1_probabilities": last_rec.get("stage_1_probabilities", {}),
                "retrieved_chunks": last_rec.get("retrieved_chunks", []),
                "latency": last_rec.get("latency", {}),
                "tokens": last_rec.get("tokens", {})
            }
        except Exception as rag_err:
            result["rag_error"] = str(rag_err)

    return jsonify(result)


@app.post("/rag/plan")
def rag_plan_endpoint():
    """
    Execute TypeSafe JEV + LLM Disaster RAG Pipeline (Pipeline B).
    Evaluates scenario, identifies required resources from the 9 relief categories,
    retrieves authoritative SOPs from VectorDB/cache, and synthesizes dispatch plan.
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

    try:
        plan = rag_pipeline.run(scenario_id=scenario_id, scenario=scenario)
        last_rec = rag_pipeline.last_run_record or {}

        return jsonify({
            "success": True if plan else False,
            "scenario_id": scenario_id,
            "pipeline": "jev_llm",
            "plan": plan,
            "stage_1_resources": last_rec.get("stage_1_resources", []),
            "stage_1_probabilities": last_rec.get("stage_1_probabilities", {}),
            "retrieved_chunks": last_rec.get("retrieved_chunks", []),
            "latency": last_rec.get("latency", {}),
            "tokens": last_rec.get("tokens", {})
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
    app.run(host="0.0.0.0", port=port, debug=False)
