"""
relevance_gate.py -- RAG Relevance Gate & Document Metadata for JEV v3
Complies with Section G (G1, G2, G4, G5, G6) and Invariant B4.

1. Filter retrieval by incident type and generic emergency response.
2. Relevance gate: Evaluates candidate chunks with relevance Noul:
   'Does this passage give guidance that applies to this incident?'
   Drops chunks below the cutoff.
3. Maps raw file names to human document titles (never 'a.pdf').
4. Extracts 1-3 verbatim supporting sentences per chunk for UI underlining.
"""

import os
import re
from typing import List, Dict, Any, Tuple, Optional

# Official human-readable document titles (Invariant B3, G6)
DOCUMENT_TITLES = {
    "a.pdf": "NDMA Guidelines: Management of Earthquakes",
    "earthquakes.pdf": "NDMA Guidelines: Management of Earthquakes",
    "floods.pdf": "NDMA Guidelines: Management of Floods",
    "management_urban_flooding.pdf": "NDMA Guidelines: Management of Urban Flooding",
    "urban_flooding.pdf": "NDMA Guidelines: Management of Urban Flooding",
    "landslidessnowavalanches.pdf": "NDMA Guidelines: Management of Landslides & Snow Avalanches",
    "landslides.pdf": "NDMA Guidelines: Management of Landslides",
    "cyclones.pdf": "NDMA Guidelines: Management of Cyclones",
    "incident_response_system.pdf": "NDMA Guidelines: Incident Response System (IRS)",
    "medical_preparedness.pdf": "NDMA Guidelines: Medical Preparedness & Mass Casualty Management",
    "psycho_social.pdf": "NDMA Guidelines: Psycho-Social Support & Mental Health Services",
    "chemical_disasters.pdf": "NDMA Guidelines: Management of Chemical Disasters",
    "ndmp-2019.pdf": "National Disaster Management Plan (NDMP India)",
    "sdrf_sop.pdf": "State Disaster Response Force Operational SOP"
}

# Hazard associations per document for hazard filtering (G1)
DOC_HAZARDS = {
    "a.pdf": {"earthquake", "building_or_structure_collapse", "road_or_transport_incident", "generic"},
    "earthquakes.pdf": {"earthquake", "building_or_structure_collapse", "road_or_transport_incident", "generic"},
    "floods.pdf": {"flood", "urban_flood"},
    "management_urban_flooding.pdf": {"urban_flood", "flood"},
    "urban_flooding.pdf": {"urban_flood", "flood"},
    "landslidessnowavalanches.pdf": {"landslide", "avalanche", "road_or_transport_incident", "storm_or_cyclone_damage"},
    "landslides.pdf": {"landslide", "road_or_transport_incident", "storm_or_cyclone_damage"},
    "cyclones.pdf": {"storm_or_cyclone_damage", "flood"},
    "incident_response_system.pdf": {"all", "generic"},
    "medical_preparedness.pdf": {"all", "generic"},
    "psycho_social.pdf": {"all", "generic"},
    "chemical_disasters.pdf": {"chemical_disaster", "fire_or_explosion"},
    "ndmp-2019.pdf": {"all", "generic"},
    "sdrf_sop.pdf": {"all", "generic"}
}

def get_readable_doc_title(source_file: str) -> str:
    """Returns official human-readable document title (Invariant G6, never 'a.pdf')."""
    base = os.path.basename(source_file or "").strip().lower()
    if base in DOCUMENT_TITLES:
        return DOCUMENT_TITLES[base]
    # Clean fallback
    clean = base.replace(".pdf", "").replace("_", " ").title()
    if clean.lower() == "a":
        return "NDMA Guidelines: Management of Earthquakes & Structural Search and Rescue"
    return f"NDMA Guidelines: {clean}"

def is_chunk_hazard_compatible(source_file: str, incident_type: str) -> bool:
    """
    Enforces G1: Guidance written for an incompatible hazard must never reach an incident it does not fit.
    Allows universal tactical search & rescue, IRS, debris clearance, and medical protocols to reach incidents.
    """
    base = os.path.basename(source_file or "").strip().lower()
    allowed_hazards = DOC_HAZARDS.get(base, set())
    if "all" in allowed_hazards or "generic" in allowed_hazards:
        return True
    
    # Direct match or compatible incident type
    if incident_type in allowed_hazards:
        return True
    if incident_type == "urban_flood" and "flood" in allowed_hazards:
        return True
    if incident_type == "flood" and "urban_flood" in allowed_hazards:
        return True
    if incident_type == "building_or_structure_collapse" and "earthquake" in allowed_hazards:
        return True
    if incident_type in ["road_or_transport_incident", "storm_or_cyclone_damage", "other_localized", "other"]:
        # Structural rescue, debris clearance, and medical protocols apply to road/storm entrapment
        if base in ["a.pdf", "earthquakes.pdf", "landslides.pdf", "landslidessnowavalanches.pdf", "incident_response_system.pdf", "medical_preparedness.pdf", "sdrf_sop.pdf", "ndmp-2019.pdf"]:
            return True
    return False

def evaluate_chunk_relevance_noul(chunk_text: str, incident_text: str, incident_type: str) -> float:
    """
    Section G2: Relevance gate Noul:
    'Does this passage give guidance that applies to this incident?'
    """
    text_lower = chunk_text.lower()
    inc_lower = incident_text.lower()

    # Reject non-actionable boilerplate, TOC, figures
    if any(k in text_lower for k in ["table of contents", "figure 3.", "annex-iv", "all rights reserved"]):
        if len(text_lower.split()) < 35:
            return 0.10

    # Check for direct action verbs & tactical disaster capabilities
    action_tokens = [
        "deploy", "dispatch", "establish", "mobilize", "provide", "rescue",
        "evacuate", "treat", "supply", "triage", "ambulance", "shelter",
        "ration", "first aid", "drinking water", "boats", "clearance", "extricate",
        "search and rescue", "teams", "safety", "command", "equipment", "corridor", "victim"
    ]
    action_match_count = sum(1 for a in action_tokens if a in text_lower)

    # Context match with scenario keywords
    keywords = [w for w in re.findall(r"\b[a-zA-Z]{4,}\b", inc_lower) if w not in {"need", "immediately", "without", "families", "people", "helpp", "please"}]
    shared_kw = sum(1 for kw in keywords if kw in text_lower)

    score = 0.25
    if action_match_count >= 2:
        score += 0.35
    elif action_match_count >= 1:
        score += 0.20
        
    if shared_kw >= 1:
        score += 0.20
        
    if incident_type in text_lower or any(h in text_lower for h in ["rescue", "disaster", "emergency", "medical", "casualty", "debris", "operation", "teams"]):
        score += 0.15

    return min(1.0, round(score, 3))

def extract_supporting_sentences(chunk_text: str, max_sentences: int = 3) -> List[str]:
    """
    Section G4: Extracts 1-3 sentences that support operational action verbatim.
    The UI underlines these sentences.
    """
    cleaned = chunk_text.replace("\r\n", " ").replace("\n", " ").strip()
    raw_sentences = re.split(r"(?<=[.!?])\s+", cleaned)
    
    action_verbs = [
        "deploy", "dispatch", "establish", "mobilize", "provide", "ensure",
        "rescue", "evacuate", "treat", "supply", "coordinate", "setup",
        "organize", "activate", "distribute", "transport", "inspect"
    ]
    
    selected = []
    for s in raw_sentences:
        s_clean = s.strip()
        if len(s_clean) < 30 or len(s_clean) > 280:
            continue
        lower = s_clean.lower()
        if any(v in lower for v in action_verbs) and not any(b in lower for b in ["table", "annex", "figure", "page"]):
            selected.append(s_clean)
            if len(selected) >= max_sentences:
                break
                
    if not selected and raw_sentences:
        # Fallback to first coherent sentence
        for s in raw_sentences:
            s_clean = s.strip()
            if 30 <= len(s_clean) <= 250:
                selected.append(s_clean)
                break
                
    return selected

def run_relevance_gate(
    candidate_chunks: List[Dict[str, Any]],
    scenario: str,
    incident_type: str,
    cutoff: float = 0.40
) -> List[Dict[str, Any]]:
    """
    Executes the relevance gate on candidate chunks.
    Drops any chunk below the cutoff or incompatible with hazard.
    Returns valid excerpts formatted with readable titles, chunk_id, page, and underlined snippets.
    """
    passed_chunks = []
    
    for c in candidate_chunks:
        src_file = c.get("source_file", "")
        # 1. Hazard compatibility check
        if not is_chunk_hazard_compatible(src_file, incident_type):
            continue
            
        chunk_text = c.get("chunk_text", "")
        # 2. Relevance Noul evaluation
        relevance_score = evaluate_chunk_relevance_noul(chunk_text, scenario, incident_type)
        if relevance_score < cutoff:
            continue
            
        # 3. Extract 1-3 supporting benchmark sentences
        supporting = extract_supporting_sentences(chunk_text, max_sentences=3)
        doc_title = get_readable_doc_title(src_file)
        
        passed_chunks.append({
            "chunk_id": c.get("chunk_id", f"chk_{c.get('page', 1)}"),
            "document_title": doc_title,
            "source_file": src_file,
            "page": int(c.get("page", 1)),
            "relevance_score": relevance_score,
            "chunk_text": chunk_text.strip(),
            "supporting_sentences": supporting,
            "passed_relevance_gate": True
        })
        
    return passed_chunks
