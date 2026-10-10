"""
agency_directory.py -- Agency directory loader and validator for AASHRAY JEV v3
Complies with Invariants B3 and Section F.
"""
import os
import json
from typing import List, Dict, Any, Optional, Set

_DIR = os.path.dirname(os.path.abspath(__file__))
DIRECTORY_FILE = os.path.join(_DIR, "agency_directory.json")
if not os.path.exists(DIRECTORY_FILE):
    DIRECTORY_FILE = os.path.abspath(os.path.join(_DIR, "..", "..", "new files", "agency_directory.json"))

_DIRECTORY_DATA: Dict[str, Any] = {}
if os.path.exists(DIRECTORY_FILE):
    try:
        with open(DIRECTORY_FILE, "r", encoding="utf-8") as f:
            _DIRECTORY_DATA = json.load(f)
    except Exception as e:
        print(f"[Agency Directory] Warning loading directory: {e}")

def get_agencies_for_location(state: Optional[str] = None, district: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Returns curated list of emergency agencies for the given state and district,
    falling back gracefully to national agencies.
    """
    results: List[Dict[str, Any]] = []
    
    # 1. District specific
    st_clean = (state or "").lower().strip()
    dist_clean = (district or "").lower().strip()

    states = _DIRECTORY_DATA.get("states", {})
    if st_clean in states:
        st_data = states[st_clean]
        districts = st_data.get("districts", {})
        if dist_clean in districts:
            results.extend(districts[dist_clean])
        # State-level agencies
        results.extend(st_data.get("state_agencies", []))
    else:
        # Search all states if district matches
        for s_name, s_info in states.items():
            districts = s_info.get("districts", {})
            if dist_clean in districts:
                results.extend(districts[dist_clean])
                results.extend(s_info.get("state_agencies", []))
                break

    # 2. National emergency services (always available)
    national = _DIRECTORY_DATA.get("national", [])
    results.extend(national)

    # Deduplicate by agency name
    seen = set()
    deduped = []
    for ag in results:
        name = ag.get("name")
        if name and name not in seen:
            seen.add(name)
            deduped.append(ag)
            
    return deduped

def get_allowed_agency_names(state: Optional[str] = None, district: Optional[str] = None, chunk_agencies: Optional[List[str]] = None) -> Set[str]:
    """
    Returns the set of all authorized agency names from the directory + any explicitly mentioned in chunks.
    Used to enforce Invariant B3.
    """
    agencies = get_agencies_for_location(state, district)
    allowed = {ag["name"].lower() for ag in agencies}
    if chunk_agencies:
        for ca in chunk_agencies:
            allowed.add(ca.lower())
    return allowed
