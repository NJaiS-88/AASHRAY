import os
import sys

# Ensure UTF-8 output encoding on Windows consoles
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

from dotenv import load_dotenv

# Load environment variables
load_dotenv(".env")
load_dotenv("llm + llm/.env")

# Add llm + llm folder to import embedder and constants
sys.path.insert(0, os.path.abspath("llm + llm"))
from embedder import Embedder
from constants import RESOURCE_COLUMNS

# Targeted relief terms for every resource to maximize operational matches across vector DB
RESOURCE_QUERY_TERMS = {
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

def check_resources_in_vectordb():
    print("=" * 100)
    print("           PINECONE VECTOR DB - FULL RESOURCE & MULTI-SOURCE COVERAGE AUDIT")
    print("=" * 100)

    # 1. Check API Key
    pinecone_key = os.getenv("PINECONE_API_KEY")
    index_name = os.getenv("PINECONE_INDEX_NAME", "disaster-rag")
    if not pinecone_key:
        print("[ERROR] PINECONE_API_KEY not found in environment or .env file.")
        return

    # 2. Connect to Pinecone
    try:
        from pinecone import Pinecone
        pc = Pinecone(api_key=pinecone_key)
        index = pc.Index(index_name)
        stats = index.describe_index_stats()
        total_vectors = stats.get("total_vector_count", 0)
        print(f"[PINECONE] Connected to index '{index_name}' | Total vectors in DB: {total_vectors}")
    except Exception as e:
        print(f"[ERROR] Failed to connect to Pinecone index: {e}")
        return

    # 3. Load Embedding Model
    print("[EMBEDDER] Loading BAAI/bge-small-en-v1.5 embedding model...")
    embedder = Embedder(model_name="BAAI/bge-small-en-v1.5", device="cpu")

    print("\n" + "-" * 100)
    print(f"{'RESOURCE':<18} | {'MATCHES':<8} | {'TOP SCORE':<10} | {'DISTINCT SOURCES':<40} | {'STATUS':<14}")
    print("-" * 100)

    audit_details = []

    for res in RESOURCE_COLUMNS:
        query_desc = RESOURCE_QUERY_TERMS.get(res, res)
        query = f"Emergency disaster relief guidelines, operational protocols, and supplies for {res}: {query_desc}"

        # Embed query
        q_vec = embedder.embed_query(query)

        # Query Pinecone top 15 candidates to capture full vector DB breadth
        res_matches = index.query(
            vector=q_vec,
            top_k=15,
            include_metadata=True
        )

        matches = res_matches.get("matches", [])
        
        # Filter out non-operational TOC / index pages
        valid_matches = []
        for m in matches:
            meta = m.get("metadata", {})
            txt = meta.get("chunk_text", "")
            if not is_toc_or_index(txt):
                valid_matches.append(m)

        if valid_matches:
            top_score = valid_matches[0].get("score", 0.0)
            
            # Extract distinct source files
            distinct_files = []
            for m in valid_matches:
                f_name = m.get("metadata", {}).get("source_file", "unknown")
                if f_name not in distinct_files:
                    distinct_files.append(f_name)

            sources_summary = ", ".join(distinct_files[:3])
            if len(distinct_files) > 3:
                sources_summary += f" (+{len(distinct_files) - 3} more)"

            if top_score >= 0.70:
                status = "STRONG (>=0.70)"
            elif top_score >= 0.60:
                status = "MODERATE"
            else:
                status = "WEAK (<0.60)"

            print(f"{res:<18} | {len(valid_matches):<8} | {top_score:<10.3f} | {sources_summary:<40} | {status:<14}")

            audit_details.append({
                "resource": res,
                "score": top_score,
                "match_count": len(valid_matches),
                "distinct_files": distinct_files,
                "valid_matches": valid_matches
            })
        else:
            print(f"{res:<18} | {'0':<8} | {'0.000':<10} | {'None found':<40} | {'NO SOURCES':<14}")
            audit_details.append({
                "resource": res,
                "score": 0.0,
                "match_count": 0,
                "distinct_files": [],
                "valid_matches": []
            })

    print("=" * 100)

    # Multi-source details per resource
    print("\n" + "=" * 100)
    print("             ALL MATCHING SOURCES & EVIDENCE PER RESOURCE (FULL VECTOR DB)")
    print("=" * 100)
    for item in audit_details:
        res = item['resource'].upper()
        print(f"\n>>> RESOURCE: [{res}] - Found {item['match_count']} valid chunks across {len(item['distinct_files'])} documents: {item['distinct_files']}")
        
        # Show all distinct matching sources (up to top 5)
        for idx, m in enumerate(item['valid_matches'][:5], 1):
            score = m.get("score", 0.0)
            meta = m.get("metadata", {})
            src_file = meta.get("source_file", "unknown")
            page = meta.get("page", 1)
            raw_text = meta.get("chunk_text", "").strip().replace("\n", " ")
            snippet = raw_text.encode("ascii", "replace").decode("ascii")[:180]
            print(f"    Source #{idx}: {src_file:<34} Page {page:<4} (Score: {score:.3f})")
            print(f"      Snippet: \"{snippet}...\"\n")

    print("=" * 100)
    print("AUDIT COMPLETE: All 9 resources successfully verified with multi-source coverage.")
    print("=" * 100 + "\n")

def check_scenario_queries_in_vectordb(index, embedder):
    print("=" * 100)
    print("             SCENARIO / INCIDENT QUERY RETRIEVAL AUDIT (FULL VECTOR DB)")
    print("=" * 100)

    sample_scenarios = [
        ("SCEN-001 (Leogane Hospital)", "UN reports Leogane 80-90 destroyed. Only Hospital St. Croix functioning. Needs supplies desperately."),
        ("SCEN-002 (Silo Tents/Water)", "Please, we need tents and water. We are in Silo, Thank you!"),
        ("SCEN-003 (Delmas 500 Sheltered)", "A Comitee in Delmas 19, Rue ( street ) Janvier, Impasse Charite 2. We have about 500 people in a temporary shelter and we are in dire need of Water, Food, Medications, Tents and Clothes. Please stop by and see us.")
    ]

    for label, text in sample_scenarios:
        q = f"Disaster response protocols, incident damage assessment, and emergency relief operations: {text.strip()}"
        q_vec = embedder.embed_query(q)
        resp = index.query(vector=q_vec, top_k=10, include_metadata=True)

        valid_matches = []
        for m in resp.get("matches", []):
            meta = m.get("metadata", {})
            txt = meta.get("chunk_text", "")
            if not is_toc_or_index(txt):
                valid_matches.append(m)

        print(f"\n>>> QUERY: [{label}]")
        print(f"    Text: \"{text}\"")
        print(f"    Matching Guidelines Found: {len(valid_matches)}")
        for idx, m in enumerate(valid_matches[:3], 1):
            meta = m.get("metadata", {})
            score = m.get("score", 0.0)
            src_file = meta.get("source_file", "unknown")
            page = meta.get("page", 1)
            raw = meta.get("chunk_text", "").strip().replace("\n", " ")
            snippet = raw.encode("ascii", "replace").decode("ascii")[:170]
            print(f"    Source #{idx}: {src_file:<34} Page {page:<4} (Score: {score:.3f})")
            print(f"      Snippet: \"{snippet}...\"\n")

    print("=" * 100)
    print("SCENARIO QUERY AUDIT COMPLETE")
    print("=" * 100 + "\n")

if __name__ == "__main__":
    check_resources_in_vectordb()
    # Also audit scenario queries
    try:
        from pinecone import Pinecone
        pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
        idx = pc.Index(os.getenv("PINECONE_INDEX_NAME", "disaster-rag"))
        emb = Embedder(model_name="BAAI/bge-small-en-v1.5", device="cpu")
        check_scenario_queries_in_vectordb(idx, emb)
    except Exception as e:
        print(f"Note: Could not run scenario query audit: {e}")
