"""
AASHRAY ML Classifier Service
Loads best_model.pkl + tfidf_vectorizer.pkl + metadata.json at startup.
Exposes POST /classify → returns disaster probability + label.
"""

import pickle
import json
import re
import os
from flask import Flask, request, jsonify
from flask_cors import CORS

# ──────────────────────────────────────────────────────────────────────────────
# Paths — go one level up from ml_service/ to find the root artifacts
# ──────────────────────────────────────────────────────────────────────────────
ROOT = os.path.join(os.path.dirname(__file__), "..")

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
    return jsonify(result)


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
