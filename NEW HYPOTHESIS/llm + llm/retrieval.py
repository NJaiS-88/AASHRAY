import os
import sys
import json
import hashlib
import yaml
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from embedder import Embedder
from constants import RESOURCE_DESCRIPTIONS

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

def load_config() -> Dict[str, Any]:
    config_path = os.path.join(os.path.dirname(__file__), "config.yaml")
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

RETRIEVAL_RELIEF_TERMS = {
    "water": "drinking water supply, potable water distribution, water purification, water tankers in disaster relief camps and flooded areas",
    "food": "emergency food distribution, rations, cooked meals, community kitchens, food packets, nutrition for disaster victims",
    "shelter": "temporary shelter, emergency tents, tarpaulins, setting up relief camps, prefabricated shelters, shelter materials",
    "clothing": "emergency clothing, garments, blankets, basic amenities, and relief supplies for disaster affected people in relief camps",
    "money": "cash relief, financial assistance, ex-gratia payment, calamity relief fund, monetary aid, compensation to disaster victims",
    "medical_help": "emergency medical teams, doctors, paramedics, field hospital, triage, ambulances, resuscitation, treating injured victims",
    "medical_products": "medicines, first aid kits, bandages, IV fluids, medical supplies, pharmaceuticals, life saving drugs, oxygen cylinders",
    "search_and_rescue": "search and rescue teams, SDRF, NDRF, rescuing trapped survivors from collapsed buildings, boats for flood rescue, rubble extraction",
    "tools": "heavy machinery, earthmovers, excavators, cutting tools, cranes, debris clearance equipment, shovels"
}

import re

def is_toc_or_index(text: str) -> bool:
    """Filter out table of contents, index pages, damage tables, or cover pages."""
    words = text.split()
    if len(words) < 25:
        return True
    lower = text.lower()
    if "table of contents" in lower or "\ncontents" in lower or "\ncontents\n" in lower or "contents" in lower[:50]:
        return True
    num_patterns = re.findall(r'\b\d+(?:\.\d+)*\b', text)
    if len(num_patterns) > 8 and (len(num_patterns) / len(words)) > 0.15:
        return True
    return False

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

    def retrieve_for_resource(self, scenario: str, resource_name: str) -> List[Dict[str, Any]]:
        """
        Query Pinecone with targeted relief terms across full vector DB.
        Retrieves multiple candidates, filters out TOC/index pages, and returns top-k.
        Caches results to disk keyed by query text.
        """
        query = RETRIEVAL_RELIEF_TERMS.get(resource_name, RESOURCE_DESCRIPTIONS.get(resource_name, ""))
        cache_file = self._get_cache_path(query)

        # 1. Check disk cache
        if os.path.exists(cache_file):
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    cached_data = json.load(f)
                    cached_res = cached_data.get("results", [])
                    if len(cached_res) >= self.top_k:
                        return cached_res[:self.top_k]
            except Exception:
                pass

        # If Pinecone index is unavailable, log and return empty
        if self.index is None:
            print(f"[Retriever] PINECONE_API_KEY not configured. Returning empty retrieval list for '{resource_name}'.")
            return []

        # 2. Embed query
        query_vector = self.embedder.embed_query(query)

        # 3. Query Pinecone with candidate pool (top_k * 3) to filter TOC noise
        candidate_k = max(self.top_k * 3, 12)
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
                "chunk_id": match.get("id"),
                "score": float(match.get("score", 0.0)),
                "source_file": metadata.get("source_file", "unknown"),
                "page": int(metadata.get("page", 1)),
                "chunk_text": chunk_text
            })
            if len(results) >= self.top_k:
                break

        # 4. Save to disk cache
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump({"query": query, "results": results}, f, indent=2)
        except Exception as e:
            print(f"Warning: Failed to save retrieval cache: {e}")

        return results

    def retrieve_for_query(self, scenario: str) -> List[Dict[str, Any]]:
        """
        Query Pinecone for overall scenario/query incident guidelines, damage assessment,
        and response protocols across the full vector DB.
        """
        query = f"Disaster response protocols, incident damage assessment, and emergency relief operations: {scenario.strip()}"
        cache_file = self._get_cache_path(query)

        # 1. Check disk cache
        if os.path.exists(cache_file):
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    cached_data = json.load(f)
                    cached_res = cached_data.get("results", [])
                    if len(cached_res) >= min(self.top_k, 3):
                        return cached_res[:min(self.top_k, 3)]
            except Exception:
                pass

        if self.index is None:
            return []

        # 2. Embed query
        query_vector = self.embedder.embed_query(query)

        # 3. Query Pinecone with candidate pool
        candidate_k = max(self.top_k * 3, 12)
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
                "chunk_id": match.get("id"),
                "score": float(match.get("score", 0.0)),
                "source_file": metadata.get("source_file", "unknown"),
                "page": int(metadata.get("page", 1)),
                "chunk_text": chunk_text
            })
            if len(results) >= min(self.top_k, 3):
                break

        # 4. Save to disk cache
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump({"query": query, "results": results}, f, indent=2)
        except Exception:
            pass

        return results

    def retrieve_for_all_resources(self, scenario: str, required_resources: List[str]) -> Dict[str, List[Dict[str, Any]]]:
        """Retrieve top-k chunks for each required resource, plus scenario query context chunks."""
        retrieved_map = {}
        # 1. Retrieve for the scenario query itself
        retrieved_map["_scenario_query"] = self.retrieve_for_query(scenario)

        # 2. Retrieve for each required resource
        for res in required_resources:
            retrieved_map[res] = self.retrieve_for_resource(scenario, res)
        return retrieved_map
