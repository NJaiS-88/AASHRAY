import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stage1_classifier import classify, get_last_classification_meta

scenario = "Flash floods in sector 4. 20 families stranded without clean drinking water and several individuals injured needing immediate medical attention and bandages."
print("Testing Stage 1 Classifier on Groq...")
print("Scenario:", scenario)
resources = classify(scenario)
meta = get_last_classification_meta()
print("\nRequired resources returned:", resources)
print("Classification Latency (ms):", round(meta.get("latency_ms", 0), 2))
print("Prompt tokens:", meta.get("prompt_tokens"))
print("Completion tokens:", meta.get("completion_tokens"))
print("Probabilities:")
for r, p in meta.get("probabilities", {}).items():
    print(f"  {r:18s}: {p:.2f}")
