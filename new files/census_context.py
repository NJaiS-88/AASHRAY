"""
census_context.py  --  Query-aware census context for TypeSafe JEV (v2)

Data: Census 2011 Primary Census Abstract (district + sub-district/town/ward rows).
NOTE: PCA has NO 60+ age, disability, housing, water or sanitation columns.
      Those need Census 2011 Table C-14 / C-20 / HLPCA (see plan, section 5.3).
"""
import os, re, difflib, pandas as pd, numpy as np

_DIR = os.path.dirname(os.path.abspath(__file__))
DIST = pd.read_csv(os.path.join(_DIR, "district_profile_2011.csv"), dtype={"State": str, "District": str})
PCT  = pd.read_csv(os.path.join(_DIR, "district_percentiles_2011.csv"), dtype={"State": str, "District": str})
_names = DIST[DIST.TRU == "Total"][["State", "District", "Name"]].drop_duplicates()
_NAMES_LOWER = {n.lower(): (s, d) for s, d, n in _names.itertuples(index=False)}

# Common alternate spellings / post-2011 renames -> 2011 census name
ALIASES = {"poonch": "punch", "baramulla": "baramula", "bengaluru": "bangalore", "bengaluru urban": "bangalore",
           "mumbai": "mumbai", "gurugram": "gurgaon", "prayagraj": "allahabad", "ayodhya": "faizabad",
           "kolkata": "kolkata", "thiruvananthapuram": "thiruvananthapuram", "wayanad": "wayanad",
           "puducherry": "puducherry", "pune": "pune", "dehradun": "dehradun", "chamoli": "chamoli"}

# --- Query signals -> which census "lens" to attend to --------------------------------
SIGNALS = {
 "children":   r"\b(child|children|kid|kids|baby|babies|infant|newborn|toddler|school|bachcha|bacche|shishu)\b",
 "women":      r"\b(woman|women|pregnan|lactat|mother|girl|delivery|labou?r pain|maternal|mahila|garbhvati)\b",
 "elderly":    r"\b(elder|old (man|woman|people)|senior|aged|grand(father|mother|parents)|bujurg|wheelchair|bedridden)\b",
 "livelihood": r"\b(crop|farm|field|cattle|livestock|buffalo|cow|goat|shop|wages|income|harvest|fodder|fasal)\b",
 "tribal_remote": r"\b(tribal|adivasi|remote|hamlet|tola|hill|cut off|no road|helicopter|airdrop)\b",
 "scale":      r"\b(\d{2,}|hundreds|village|colony|slum|basti|whole|entire|many|families)\b",
 "literacy_comm": r"\b(cannot read|can't read|no phone|no network|no signal|illiterate)\b",
}
# lens -> census features that matter for that signal (weights sum to 1 per lens)
LENS = {
 "children":   {"child_0_6_pct": .6, "dependency_pct": .2, "illiterate_pct": .2},
 "women":      {"sex_ratio_inv": .3, "literacy_gender_gap": .3, "female_wpr_pct_inv": .2, "child_0_6_pct": .2},
 "elderly":    {"dependency_pct": .5, "hh_size_inv": .5},     # weak proxy; replace w/ C-14 60+ share
 "livelihood": {"agri_dependence_pct": .4, "ag_labour_pct": .3, "marginal_worker_pct": .3},
 "tribal_remote": {"st_pct": .6, "sc_pct": .2, "illiterate_pct": .2},
 "scale":      {},   # scale drives QUANTITIES (households, litres, rations), not vulnerability
 "literacy_comm": {"illiterate_pct": .6, "literacy_gender_gap": .4},
}
DEFAULT_LENS = {"illiterate_pct": .25, "marginal_worker_pct": .25, "child_0_6_pct": .25, "st_pct": .25}

def extract_signals(text):
    t = text.lower()
    return [k for k, rx in SIGNALS.items() if re.search(rx, t)]

def resolve_district(text=None, district=None, state=None):
    """Return (state_code, district_code, match_conf). Never silently guess: conf<0.85 -> caller must flag."""
    toks = re.findall(r"[A-Za-z&]+", (text or "").lower())
    cands = [district] if district else [" ".join(toks[i:i+n]) for n in (2, 1) for i in range(len(toks)-n+1)]
    best = (None, 0.0)
    for c in cands:
        c = ALIASES.get(c.lower().strip(), c.lower().strip())
        if c in _NAMES_LOWER: return (*_NAMES_LOWER[c], 1.0)
        m = difflib.get_close_matches(c, _NAMES_LOWER.keys(), n=1, cutoff=0.8)
        if m:
            s = difflib.SequenceMatcher(None, c, m[0]).ratio()
            if s > best[1]: best = (_NAMES_LOWER[m[0]], s)
    return (*best[0], best[1]) if best[0] else (None, None, 0.0)

def _prow(sd, dc):
    return PCT[(PCT.State == sd) & (PCT.District == dc)].iloc[0]

def build_context(text, district=None, stratum=None, persons=None):
    """stratum in {'Rural','Urban',None->Total}. Returns a dict the JEV head + Stage-2 prompt both consume."""
    sd, dc, conf = resolve_district(text, district)
    sig = extract_signals(text)
    if sd is None or conf < 0.85:
        return {"census_available": False, "match_confidence": conf, "signals": sig,
                "note": "Location unresolved: JEV must use text-only mode; Stage 2 must ask for location."}
    stratum = stratum or "Total"
    row = DIST[(DIST.State == sd) & (DIST.District == dc) & (DIST.TRU == stratum)].iloc[0]
    pr = _prow(sd, dc)
    inv = lambda c: 1 - pr[c + "_pctile"]
    pct = {"child_0_6_pct": pr.child_0_6_pct_pctile, "dependency_pct": pr.dependency_pct_pctile,
           "illiterate_pct": pr.illiterate_pct_pctile, "literacy_gender_gap": pr.literacy_gender_gap_pctile,
           "female_wpr_pct_inv": inv("female_wpr_pct"), "sex_ratio_inv": np.nan, "st_pct": pr.st_pct_pctile,
           "sc_pct": pr.sc_pct_pctile, "agri_dependence_pct": pr.agri_dependence_pct_pctile,
           "ag_labour_pct": pr.ag_labour_pct_pctile, "marginal_worker_pct": pr.marginal_worker_pct_pctile,
           "hh_size": pr.hh_size_pctile, "hh_size_inv": 1 - pr.hh_size_pctile}
    # sex-ratio percentile (low sex ratio = more female-vulnerable) computed on the fly
    allsr = DIST[DIST.TRU == "Total"].sex_ratio
    pct["sex_ratio_inv"] = 1 - (allsr < row.sex_ratio).mean()
    lenses = sig or ["default"]
    weights = {}
    lenses = [l for l in lenses if l == "default" or LENS.get(l)] or ["default"]
    for l in lenses:
        for f, w in (LENS.get(l) or DEFAULT_LENS).items():
            weights[f] = weights.get(f, 0) + w / len(lenses)
    # query-conditioned vulnerability: weighted percentile of the features the query makes relevant
    vuln = float(sum(pct[f] * w for f, w in weights.items()) / sum(weights.values()))
    hh = persons / row.hh_size if persons and row.hh_size else None
    return {
        "census_available": True, "match_confidence": conf, "stratum": stratum,
        "district": row.Name, "state_code": sd, "signals": sig,
        "attended_features": {f: round(w, 2) for f, w in sorted(weights.items(), key=lambda x: -x[1])},
        "query_conditioned_vulnerability": round(vuln, 3),     # 0..1 percentile scale, India-wide
        "raw": {k: round(float(row[k]), 1) for k in ["pop", "households", "hh_size", "sex_ratio", "child_0_6_pct",
                "st_pct", "sc_pct", "illiterate_pct", "female_literacy_pct", "female_wpr_pct",
                "agri_dependence_pct", "marginal_worker_pct", "dependency_pct"]},
        "percentiles": {k: round(float(v), 2) for k, v in pct.items()},
        "est_households_affected": round(hh) if hh else None,
        "est_children_0_6": round(persons * row.child_0_6_pct / 100) if persons else None,
        "comm_mode_hint": "voice+pictorial+local-language" if pct["illiterate_pct"] > .7 else "sms+text",
        "data_vintage": "Census 2011 (proportions only; absolute counts stale)",
    }

if __name__ == "__main__":
    import json
    for q, d in [("Landslide cut off our hamlet in Chamoli, 3 children and 2 pregnant women need help, no road", "Chamoli"),
                 ("Flood water entered Baramulla village, crops and cattle lost, 200 people", "Baramulla"),
                 ("Water rising in colony near Pune, elderly man bedridden", None)]:
        print(json.dumps(build_context(q, d, persons=200 if "200" in q else None), indent=1)[:1400], "\n")
