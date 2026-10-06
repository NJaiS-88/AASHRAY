import os
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import json
import hashlib
import yaml
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from embedder import Embedder
from constants import RESOURCE_DESCRIPTIONS

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

def load_config() -> Dict[str, Any]:
    config_path = os.path.join(os.path.dirname(__file__), "config.yaml")
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

# ──────────────────────────────────────────────────────────────────────────────
# Resource-specific retrieval terms (used as query for Pinecone + reranker)
# ──────────────────────────────────────────────────────────────────────────────
RETRIEVAL_RELIEF_TERMS = {
    "water":            "drinking water supply, potable water distribution, water purification, water tankers in disaster relief camps and flooded areas",
    "food":             "emergency food distribution, rations, cooked meals, community kitchens, food packets, nutrition for disaster victims",
    "shelter":          "temporary shelter, emergency tents, tarpaulins, setting up relief camps, prefabricated shelters, shelter materials",
    "clothing":         "emergency clothing, garments, blankets, basic amenities, and relief supplies for disaster affected people in relief camps",
    "money":            "cash relief, financial assistance, ex-gratia payment, calamity relief fund, monetary aid, compensation to disaster victims",
    "medical_help":     "emergency medical teams, doctors, paramedics, field hospital, triage, ambulances, resuscitation, treating injured victims",
    "medical_products": "medicines, first aid kits, bandages, IV fluids, medical supplies, pharmaceuticals, life saving drugs, oxygen cylinders",
    "search_and_rescue":"search and rescue teams, SDRF, NDRF, rescuing trapped survivors from collapsed buildings, boats for flood rescue, rubble extraction",
    "tools":            "heavy machinery, earthmovers, excavators, cutting tools, cranes, debris clearance equipment, shovels"
}

# Scenario query augmentation terms — appended to the raw scenario for richer retrieval
DISASTER_AUGMENTATION_TERMS = (
    "disaster response protocol emergency relief operations NDMA NDRF SDRF "
    "incident command resource mobilization damage assessment humanitarian assistance"
)

import re

def is_toc_or_index(text: str) -> bool:
    """Filter out table of contents, index pages, damage tables, or cover pages."""
    words = text.split()
    if len(words) < 25:
        return True
    lower = text.lower()
    if "table of contents" in lower or "\ncontents" in lower or "contents" in lower[:50]:
        return True
    num_patterns = re.findall(r'\b\d+(?:\.\d+)*\b', text)
    if len(num_patterns) > 8 and (len(num_patterns) / len(words)) > 0.15:
        return True
    return False

# ──────────────────────────────────────────────────────────────────────────────
# Lazy-loaded Cross-Encoder reranker
# ──────────────────────────────────────────────────────────────────────────────
_CROSS_ENCODER = None
_CROSS_ENCODER_LOADED = False

def _get_reranker():
    """Lazily load the cross-encoder. Returns None if unavailable."""
    global _CROSS_ENCODER, _CROSS_ENCODER_LOADED
    if _CROSS_ENCODER_LOADED:
        return _CROSS_ENCODER
    try:
        from sentence_transformers import CrossEncoder
        _CROSS_ENCODER = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2", max_length=512)
        print("[Retriever] [OK] Cross-encoder reranker loaded (ms-marco-MiniLM-L-6-v2)")
    except Exception as e:
        print(f"[Retriever] Cross-encoder unavailable ({e}). Using bi-encoder scores only.")
        _CROSS_ENCODER = None
    _CROSS_ENCODER_LOADED = True
    return _CROSS_ENCODER

def rerank_chunks(query: str, chunks: List[Dict[str, Any]], top_k: int) -> List[Dict[str, Any]]:
    """
    Rerank retrieved chunks using a cross-encoder.
    Falls back to original bi-encoder score order if cross-encoder is unavailable.
    Also deduplicates near-identical chunks using text prefix overlap.
    """
    if not chunks:
        return chunks

    # ── Step 1: Deduplicate — remove chunks whose first 80 chars repeat ──
    seen_prefixes: set = set()
    deduped = []
    for c in chunks:
        prefix = c.get("chunk_text", "")[:80].strip().lower()
        if prefix and prefix not in seen_prefixes:
            seen_prefixes.add(prefix)
            deduped.append(c)

    # ── Step 2: Cross-encoder reranking ──
    reranker = _get_reranker()
    if reranker is None or len(deduped) <= 1:
        return deduped[:top_k]

    try:
        pairs = [(query, c.get("chunk_text", "")) for c in deduped]
        scores = reranker.predict(pairs)
        scored = sorted(zip(scores, deduped), key=lambda x: x[0], reverse=True)
        reranked = [c for _, c in scored]
        # Attach rerank score for transparency
        for score, chunk in zip([s for s, _ in scored], reranked):
            chunk["rerank_score"] = round(float(score), 4)
        return reranked[:top_k]
    except Exception as e:
        print(f"[Retriever] Reranking failed ({e}), using original order.")
        return deduped[:top_k]

def augment_query(scenario: str) -> str:
    """Augment a bare scenario with standard disaster response terms for richer retrieval."""
    return f"{scenario.strip()} {DISASTER_AUGMENTATION_TERMS}"


class Retriever:
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or load_config()
        self.top_k = self.config.get("retrieval", {}).get("top_k", 4)

        # Disk cache directory
        cache_subdir = self.config.get("retrieval", {}).get("cache_dir", "retrieval_cache")
        self.cache_dir = os.path.join(os.path.dirname(__file__), cache_subdir)
        os.makedirs(self.cache_dir, exist_ok=True)

        # Embedding model
        emb_cfg = self.config.get("embedding", {})
        self.embedder = Embedder(
            model_name=emb_cfg.get("model_name", "BAAI/bge-small-en-v1.5"),
            device=emb_cfg.get("device", "cpu")
        )

        # Pinecone client
        self.pinecone_api_key = os.getenv("PINECONE_API_KEY")
        self.index_name = os.getenv("PINECONE_INDEX_NAME", self.config.get("pinecone", {}).get("index_name", "disaster-rag"))
        self._index = None

    @property
    def index(self):
        if self._index is None:
            if not self.pinecone_api_key:
                return None
            try:
                from pinecone import Pinecone
                pc = Pinecone(api_key=self.pinecone_api_key)
                self._index = pc.Index(self.index_name)
            except Exception as e:
                print(f"[Retriever Warning] Failed to connect to Pinecone: {e}")
                return None
            return self._index
        return self._index

    def _get_cache_path(self, query: str) -> str:
        query_hash = hashlib.sha256(query.strip().encode("utf-8")).hexdigest()
        return os.path.join(self.cache_dir, f"{query_hash}.json")

    def _fetch_from_pinecone(self, query: str, candidate_k: int) -> List[Dict[str, Any]]:
        """Embed query and fetch raw candidates from Pinecone."""
        query_vector = self.embedder.embed_query(query)
        response = self.index.query(
            vector=query_vector,
            top_k=candidate_k,
            include_metadata=True
        )
        results = []
        for match in response.get("matches", []):
            metadata = match.get("metadata", {})
            chunk_text = metadata.get("chunk_text", "")
            if is_toc_or_index(chunk_text):
                continue
            results.append({
                "chunk_id":   match.get("id"),
                "score":      float(match.get("score", 0.0)),
                "source_file": metadata.get("source_file", "unknown"),
                "page":       int(metadata.get("page", 1)),
                "chunk_text": chunk_text
            })
        return results

    def retrieve_for_resource(self, scenario: str, resource_name: str) -> List[Dict[str, Any]]:
        """
        Retrieve top-k chunks for a specific resource need.
        Pipeline:
          1. Check disk cache (keyed on relief term query)
          2. If cache miss → query Pinecone with candidate pool (top_k × 4)
          3. Rerank with cross-encoder against the original resource term
          4. Cache the reranked results
        """
        base_query = RETRIEVAL_RELIEF_TERMS.get(resource_name, RESOURCE_DESCRIPTIONS.get(resource_name, ""))
        # Augment resource query with the scenario context for better relevance
        rerank_query = f"{scenario.strip()} needs {base_query}"
        cache_file = self._get_cache_path(base_query)

        # 1. Check disk cache (pre-reranked results)
        if os.path.exists(cache_file):
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    cached_data = json.load(f)
                    cached_res = cached_data.get("results", [])
                    if len(cached_res) >= self.top_k:
                        # Still rerank cached chunks against current scenario for better ordering
                        reranked = rerank_chunks(rerank_query, cached_res, self.top_k)
                        return reranked
            except Exception:
                pass

        # If Pinecone index is unavailable, return empty
        if self.index is None:
            print(f"[Retriever] PINECONE_API_KEY not configured. Returning empty list for '{resource_name}'.")
            return []

        # 2. Fetch candidates from Pinecone (large pool for reranker to work on)
        candidate_k = max(self.top_k * 4, 16)
        raw_candidates = self._fetch_from_pinecone(base_query, candidate_k)

        # 3. Rerank candidates
        reranked = rerank_chunks(rerank_query, raw_candidates, self.top_k)

        # 4. Save reranked results to disk cache
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump({"query": base_query, "results": reranked}, f, indent=2)
        except Exception as e:
            print(f"Warning: Failed to save retrieval cache: {e}")

        return reranked

    def retrieve_for_query(self, scenario: str) -> List[Dict[str, Any]]:
        """
        Retrieve top-k chunks for the overall scenario context.
        Uses augmented query for richer recall, then reranks against original scenario.
        """
        augmented = augment_query(scenario)
        cache_file = self._get_cache_path(augmented)
        top_k_q = min(self.top_k, 3)

        # 1. Check disk cache
        if os.path.exists(cache_file):
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    cached_data = json.load(f)
                    cached_res = cached_data.get("results", [])
                    if len(cached_res) >= top_k_q:
                        reranked = rerank_chunks(scenario, cached_res, top_k_q)
                        return reranked
            except Exception:
                pass

        if self.index is None:
            return []

        # 2. Fetch candidates from Pinecone using the augmented query
        candidate_k = max(top_k_q * 4, 12)
        raw_candidates = self._fetch_from_pinecone(augmented, candidate_k)

        # 3. Rerank against the original scenario (not the augmented one)
        reranked = rerank_chunks(scenario, raw_candidates, top_k_q)

        # 4. Save to cache
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump({"query": augmented, "results": reranked}, f, indent=2)
        except Exception:
            pass

        return reranked

    def retrieve_for_all_resources(self, scenario: str, required_resources: List[str]) -> Dict[str, List[Dict[str, Any]]]:
        """Retrieve reranked top-k chunks for each required resource + scenario context."""
        retrieved_map = {}
        # 1. Retrieve + rerank for the overall scenario query context
        retrieved_map["_scenario_query"] = self.retrieve_for_query(scenario)
        # 2. Retrieve + rerank for each required resource
        for res in required_resources:
            retrieved_map[res] = self.retrieve_for_resource(scenario, res)
        return retrieved_map
