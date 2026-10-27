from sentence_transformers import SentenceTransformer, util

# Load once
embedder = SentenceTransformer('all-MiniLM-L6-v2')

# --- Test pairs ---
pairs = [
    (
        "cars are parked in a flooded street",
        "there is water logging on road pls send help"
    ),
    (
        "i think a ceiling has collapsed on upper floor due to continuous rains might need help pls check",
        "too much rains emergency"
    ),
    (
        "a wall has fallen on a man",
        "waterlogging on road"
    ),
    (
        "flooding has destroyed several homes, people need rescue immediately",
        "just had a great cup of coffee this morning"
    ),
]

print(f"{'Text 1':60s} | {'Text 2':45s} | Similarity")
print("-" * 120)

for text1, text2 in pairs:
    embeddings = embedder.encode([text1, text2])
    score = util.cos_sim(embeddings[0], embeddings[1]).item()
    print(f"{text1[:58]:60s} | {text2[:43]:45s} | {score:.4f}")

print("\n--- Interpretation guide (NOT a hard rule, just a rough calibration) ---")
print("0.7+   -> very likely same specific event/topic")
print("0.4-0.7 -> related theme, different specifics/intent")
print("< 0.4  -> likely unrelated")
print("\nSet YOUR threshold based on what these numbers actually look like for your")
print("use case - don't assume 0.75 (near-duplicate detection) is right for general")
print("'are these related' checks.")
