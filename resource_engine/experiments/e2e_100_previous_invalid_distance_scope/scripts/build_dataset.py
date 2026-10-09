"""Build and validate the 100-scenario genuine-disaster dataset.

Every scenario is a real event with an English Wikipedia article. All facts
that can be checked automatically are fetched from Wikipedia / Wikidata at
build time and recorded with their revision / entity IDs:

  * source:       event article (page id, revision id, URL)
  * coordinates:  Wikipedia coordinates of the event article when it has
                  them and they lie within 30 km of the affected locality,
                  otherwise the coordinates of the affected locality's article
  * population:   Wikidata P1082 (population) and P2046 (area) of the
                  locality / district / state, smallest unit that is at least
                  the affected population
  * figures:      the reported deaths and affected-population figures must
                  occur in the article text next to a matching keyword; the
                  numeric token, keyword and revision id are recorded

Usage:
  python build_dataset.py --cache <dir> review      # print figure candidates
  python build_dataset.py --cache <dir> build       # validate + write files
"""
import argparse
import hashlib
import json
import math
import re
import sys
import time
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
EXPERIMENT = HERE.parent
SEED = HERE / "scenario_seed.json"
FIGURES = HERE / "scenario_figures.json"

API = "https://en.wikipedia.org/w/api.php"
WIKIDATA = "https://www.wikidata.org/w/api.php"
UA = "AASHRAY-E2E100-dataset-validation/1.0 (https://github.com/NJaiS-88/AASHRAY; research script)"

INDIA_BBOX = (6.0, 37.6, 68.0, 97.5)  # lat_min, lat_max, lon_min, lon_max
EVENT_COORD_MAX_KM = 30.0

AREA_UNITS_KM2 = {
    "http://www.wikidata.org/entity/Q712226": 1.0,        # square kilometre
    "http://www.wikidata.org/entity/Q35852": 0.01,        # hectare
    "http://www.wikidata.org/entity/Q232291": 2.589988,   # square mile
    "http://www.wikidata.org/entity/Q25343": 1e-6,        # square metre
    "http://www.wikidata.org/entity/Q81292": 0.0040468564,  # acre
}


# --------------------------------------------------------------------------
# Fetching (cached)
# --------------------------------------------------------------------------

class Fetcher:
    def __init__(self, cache: Path):
        self.cache = cache
        self.cache.mkdir(parents=True, exist_ok=True)
        self.http = httpx.Client(headers={"User-Agent": UA}, timeout=60)

    def _cached(self, name: str, fetch):
        path = self.cache / name
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        data = fetch()
        path.write_text(json.dumps(data), encoding="utf-8")
        time.sleep(0.4)
        return data

    def _query_all(self, params: dict) -> dict:
        # Follow API continuation (prop=coordinates is paginated) and merge
        # each page's properties.
        merged = None
        cont = {}
        while True:
            data = self.http.get(API, params={**params, **cont}).json()
            if merged is None:
                merged = data
            else:
                for pid, page in data["query"]["pages"].items():
                    target = merged["query"]["pages"].setdefault(pid, page)
                    for k, v in page.items():
                        if k == "coordinates":
                            target.setdefault("coordinates", []).extend(v)
                        else:
                            target.setdefault(k, v)
            if "continue" not in data:
                return merged
            cont = data["continue"]
            time.sleep(0.3)

    def pages(self, titles: list[str]) -> dict[str, dict]:
        out = {}
        for start in range(0, len(titles), 50):
            batch = titles[start:start + 50]
            key = "pages_" + hashlib.sha1("|".join(batch).encode()).hexdigest()[:16] + ".json"
            data = self._cached(key, lambda: self._query_all({
                "action": "query", "format": "json", "redirects": 1,
                "prop": "info|coordinates|pageprops", "inprop": "url",
                "ppprop": "wikibase_item|disambiguation", "colimit": "max", "titles": "|".join(batch),
            }))
            q = data["query"]
            norm = {n["from"]: n["to"] for n in q.get("normalized", [])}
            redir = {n["from"]: n["to"] for n in q.get("redirects", [])}
            by_title = {p["title"]: p for p in q["pages"].values()}
            for t in batch:
                n = norm.get(t, t)
                final = redir.get(n, n)
                p = by_title.get(final)
                if p is None or "missing" in p:
                    out[t] = None
                    continue
                coords = [c for c in p.get("coordinates", []) if c.get("globe", "earth") == "earth"]
                out[t] = {
                    "title": p["title"],
                    "pageid": p["pageid"],
                    "revision_id": p["lastrevid"],
                    "url": p["fullurl"],
                    "wikidata": p.get("pageprops", {}).get("wikibase_item"),
                    "disambiguation": "disambiguation" in p.get("pageprops", {}),
                    "lat": coords[0]["lat"] if coords else None,
                    "lon": coords[0]["lon"] if coords else None,
                }
        return out

    def text(self, title: str) -> str:
        safe = re.sub(r"[^A-Za-z0-9]+", "_", title)[:120]
        data = self._cached(f"text_{safe}.json", lambda: self.http.get(API, params={
            "action": "query", "format": "json", "redirects": 1, "prop": "extracts",
            "explaintext": 1, "exsectionformat": "plain", "titles": title,
        }).json())
        page = next(iter(data["query"]["pages"].values()))
        return page.get("extract", "")

    def wikidata(self, ids: list[str]) -> dict[str, dict]:
        out = {}
        ids = sorted({i for i in ids if i})
        for start in range(0, len(ids), 50):
            batch = ids[start:start + 50]
            key = "wd_" + hashlib.sha1("|".join(batch).encode()).hexdigest()[:16] + ".json"
            data = self._cached(key, lambda: self.http.get(WIKIDATA, params={
                "action": "wbgetentities", "format": "json", "props": "claims",
                "ids": "|".join(batch),
            }).json())
            for qid, entity in data.get("entities", {}).items():
                out[qid] = entity.get("claims", {})
        return out


def best_statement(statements):
    # Preferred rank first, otherwise the latest point in time (P585).
    if not statements:
        return None
    preferred = [s for s in statements if s.get("rank") == "preferred"]
    pool = preferred or [s for s in statements if s.get("rank") != "deprecated"]

    def when(s):
        q = s.get("qualifiers", {}).get("P585", [])
        try:
            return q[0]["datavalue"]["value"]["time"]
        except (IndexError, KeyError):
            return ""

    pool.sort(key=when, reverse=True)
    return pool[0] if pool else None


def wikidata_coordinates(claims):
    s = best_statement(claims.get("P625", []))
    if s and "datavalue" in s.get("mainsnak", {}):
        v = s["mainsnak"]["datavalue"]["value"]
        if v.get("globe", "").endswith("Q2"):  # Earth
            return v["latitude"], v["longitude"]
    return None


def population_and_area(claims):
    pop = area = None
    s = best_statement(claims.get("P1082", []))
    if s and "datavalue" in s.get("mainsnak", {}):
        pop = float(s["mainsnak"]["datavalue"]["value"]["amount"])
    s = best_statement(claims.get("P2046", []))
    if s and "datavalue" in s.get("mainsnak", {}):
        v = s["mainsnak"]["datavalue"]["value"]
        factor = AREA_UNITS_KM2.get(v.get("unit"))
        if factor:
            area = float(v["amount"]) * factor
    return pop, area


# --------------------------------------------------------------------------
# Figure extraction
# --------------------------------------------------------------------------

NUMBER = re.compile(
    r"(?<![\w.,])(\d{1,3}(?:,\d{2,3})+|\d+(?:\.\d+)?)"
    r"(?:\s*(million|lakh|lakhs|crore|thousand|billion))?(?![\w])",
    re.I,
)
MULTIPLIER = {"million": 1e6, "lakh": 1e5, "lakhs": 1e5, "crore": 1e7, "thousand": 1e3, "billion": 1e9}
CURRENCY_BEFORE = re.compile(r"(₹|rs\.?|inr|us\$|\$|£|€|rupees?)\s*$", re.I)
UNIT_AFTER = re.compile(
    r"^\s*(?:-|–)?\s*(km|kilomet|mi\b|miles|mm|cm|millimet|centimet|metre|meter|m\b|ft|feet|inch|kg|tonne|ton|hectare|"
    r"acre|houses?|homes?|huts?|buildings?|villages?|cattle|livestock|animals|crore|rupee|%|per ?cent|mph|km/h|kmph|"
    r"knots|hours?|hrs|days?|weeks?|months?|years?|mw|cusecs|m3|cubic|sq|square|districts?|taluka|trains?|vehicles?|"
    r"boats?|hpa|mbar|ships?|flights?|storeys?|floors?|kV|degrees?|°)",
    re.I,
)
CLASSES = {
    "deaths": re.compile(r"\b(killed|kill(?:ing)?|dead|deaths?|died|die|death toll|fatalit\w*|lives|perished|bodies|casualt\w*)\b", re.I),
    "injured": re.compile(r"\b(injur\w*|wounded|hurt|hospitali[sz]ed)\b", re.I),
    "affected": re.compile(r"\b(affected|impacted|exposed)\b", re.I),
    "displaced": re.compile(r"\b(displaced|evacuat\w*|homeless|relief camps?|shelters?|relocated|rehabilitat\w*|shifted)\b", re.I),
    "stranded": re.compile(r"\b(stranded|trapped|marooned|rescued|missing|survivors?|survived|unaccounted)\b", re.I),
    "population": re.compile(r"\b(population|inhabitants|residents|villagers|on board|aboard)\b", re.I),
}

WORD_UNITS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
              "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
              "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19}
WORD_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
             "eighty": 80, "ninety": 90}
WORD_NUMBER = re.compile(
    r"(?<![\w-])((?:" + "|".join(WORD_TENS) + r")(?:[- ](?:" + "|".join(k for k in WORD_UNITS if WORD_UNITS[k] < 10)
    + r"))?|" + "|".join(sorted(WORD_UNITS, key=len, reverse=True)) + r")(?:\s+(hundred|thousand))?(?![\w-])",
    re.I,
)


def word_value(token: str, scale: str | None) -> int:
    parts = re.split(r"[- ]", token.lower())
    value = 0
    for part in parts:
        value += WORD_TENS.get(part, 0) + WORD_UNITS.get(part, 0)
    if scale:
        value *= 100 if scale.lower() == "hundred" else 1000
    return value


def _classes_near(text: str, start: int, end: int):
    lo, hi = max(0, start - 70), min(len(text), end + 90)
    window = text[lo:hi]
    pos = start - lo
    found = {}
    for cls, rx in CLASSES.items():
        for k in rx.finditer(window):
            d = abs(k.start() - pos)
            if cls not in found or d < found[cls][0]:
                found[cls] = (d, k.group(0))
    return found


def figures(text: str):
    out = []
    occurrences = []
    for m in NUMBER.finditer(text):
        raw, mult = m.group(1), m.group(2)
        value = float(raw.replace(",", ""))
        if mult:
            value *= MULTIPLIER[mult.lower()]
        before = text[max(0, m.start() - 8):m.start()]
        after = text[m.end():m.end() + 14]
        if CURRENCY_BEFORE.search(before) or (mult and mult.lower() == "crore"):
            continue
        if UNIT_AFTER.match(after):
            continue
        if not mult and "," not in raw and "." not in raw and 1800 <= value <= 2100:
            continue  # a year
        if value < 1 or value != int(value):
            continue
        occurrences.append((int(value), m.group(0).strip(), m.start(), m.end()))
    for m in WORD_NUMBER.finditer(text):
        if UNIT_AFTER.match(text[m.end():m.end() + 14]):
            continue
        occurrences.append((word_value(m.group(1), m.group(2)), m.group(0).strip(), m.start(), m.end()))

    for value, token, start, end in occurrences:
        found = _classes_near(text, start, end)
        if not found:
            continue
        nearest = min(found, key=lambda c: found[c][0])
        out.append({
            "value": value, "token": token, "class": nearest, "keyword": found[nearest][1],
            "classes": {c: kw for c, (d, kw) in found.items()}, "offset": start,
            "context": " ".join(text[max(0, start - 45):end + 45].split()),
        })
    return out


# --------------------------------------------------------------------------
# AASHRAY input mapping (documented in README)
# --------------------------------------------------------------------------

SUDDEN_ONSET = {
    "EARTHQUAKE", "TSUNAMI", "LANDSLIDE", "BUILDING_COLLAPSE", "STRUCTURAL_COLLAPSE", "FIRE",
    "EXPLOSION", "CHEMICAL_LEAK", "STAMPEDE", "RAIL_ACCIDENT", "ROAD_ACCIDENT", "AIR_ACCIDENT",
    "DAM_FAILURE", "FLASH_FLOOD", "MINING_ACCIDENT", "TUNNEL_COLLAPSE",
}
RAPID_ONSET = {"FLOOD", "CYCLONE", "DUST_STORM"}
SLOW_ONSET = {"DROUGHT"}
CASUALTY_INCIDENT = {
    "BUILDING_COLLAPSE", "STRUCTURAL_COLLAPSE", "FIRE", "EXPLOSION", "CHEMICAL_LEAK", "STAMPEDE",
    "RAIL_ACCIDENT", "ROAD_ACCIDENT", "AIR_ACCIDENT", "MINING_ACCIDENT", "TUNNEL_COLLAPSE",
}


def severity_for(deaths: int, affected: int) -> float:
    if deaths >= 1000 or affected >= 1_000_000:
        return 0.95
    if deaths >= 100 or affected >= 100_000:
        return 0.85
    if deaths >= 20 or affected >= 10_000:
        return 0.75
    if deaths >= 1 or affected >= 1_000:
        return 0.65
    return 0.55


def urgency_for(kind: str) -> float:
    if kind in SUDDEN_ONSET:
        return 0.9
    if kind in RAPID_ONSET:
        return 0.8
    return 0.5


def priority_for(severity: float) -> str:
    if severity >= 0.9:
        return "CRITICAL"
    if severity >= 0.8:
        return "HIGH"
    if severity >= 0.7:
        return "MODERATE"
    return "LOW"


def duration_for(kind: str) -> float:
    if kind in CASUALTY_INCIDENT:
        return 24.0
    if kind in {"EARTHQUAKE", "TSUNAMI", "LANDSLIDE", "DAM_FAILURE", "FLASH_FLOOD"}:
        return 72.0
    if kind in RAPID_ONSET:
        return 120.0
    return 720.0


def haversine_km(a_lat, a_lon, b_lat, b_lon):
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp, dl = math.radians(b_lat - a_lat), math.radians(b_lon - a_lon)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(min(h, 1.0)))


# --------------------------------------------------------------------------

def load_all(fetcher: Fetcher, seed: list[dict]):
    titles = sorted({s["wiki"] for s in seed} | {s["coord_page"] for s in seed}
                    | {s["admin_page"] for s in seed} | {s["state"] for s in seed})
    pages = fetcher.pages(titles)
    texts = {s["wiki"]: fetcher.text(pages[s["wiki"]]["title"]) for s in seed if pages.get(s["wiki"])}
    qids = [p["wikidata"] for p in pages.values() if p]
    claims = fetcher.wikidata(qids)
    return pages, texts, claims


def review(seed, pages, texts):
    for s in seed:
        page = pages.get(s["wiki"])
        if not page:
            print(f"\n### {s['wiki']}: SOURCE PAGE MISSING")
            continue
        cand = figures(texts[s["wiki"]])
        print(f"\n### {page['title']}  ({s['type']}, {s['date']})  chars={len(texts[s['wiki']])}")
        for cls in ("deaths", "injured", "affected", "displaced", "stranded"):
            items = sorted({(c["value"], c["token"], c["keyword"]): c for c in cand if c["class"] == cls}.values(),
                           key=lambda c: -c["value"])[:4]
            for c in items:
                print(f"  {cls:9} {c['value']:>11,}  [{c['keyword']}]  …{c['context']}…")


def verify_figure(cands, value, classes):
    # The value must occur in the article with a keyword of the claimed class
    # in the same short window (70 chars before, 90 after).
    for c in cands:
        if c["value"] == value:
            hit = next((cls for cls in classes if cls in c["classes"]), None)
            if hit:
                return {"value": value, "token": c["token"], "class": hit, "keyword": c["classes"][hit],
                        "text_offset": c["offset"]}
    return None


def build(seed, pages, texts, claims, figures_cfg):
    scenarios, problems = [], []

    for s in seed:
        issues = []
        page = pages.get(s["wiki"])
        coord_page = pages.get(s["coord_page"])
        admin_page = pages.get(s["admin_page"])
        state_page = pages.get(s["state"])
        if s.get("excluded"):
            problems.append((s["wiki"], [f"excluded during curation: {s['excluded']}"]))
            continue
        if not page:
            problems.append((s["wiki"], ["source article not found"]))
            continue

        cfg = figures_cfg.get(s["wiki"]) or figures_cfg.get(page["title"])
        if not cfg:
            problems.append((s["wiki"], ["no curated figures"]))
            continue

        text = texts[s["wiki"]]
        cands = figures(text)

        for role, unit_page in (("source", page), ("coordinate", coord_page), ("admin", admin_page)):
            if unit_page and unit_page.get("disambiguation"):
                issues.append(f"{role} page {unit_page['title']!r} is a disambiguation page")

        # -- date: the event year must appear in the article title or text
        year = s["date"][:4]
        if year not in page["title"] and year not in text[:4000]:
            issues.append(f"event year {year} not found in article title/intro")

        # -- coordinates: the locality article's primary coordinates, or the
        # coordinates (P625) of the same article's Wikidata item
        locality_coords = None
        if coord_page and coord_page["lat"] is not None:
            locality_coords = (coord_page["lat"], coord_page["lon"], "Wikipedia article coordinates")
        elif coord_page and coord_page.get("wikidata"):
            wd = wikidata_coordinates(claims.get(coord_page["wikidata"], {}))
            if wd:
                locality_coords = (wd[0], wd[1], f"Wikidata {coord_page['wikidata']} P625")
        if not locality_coords:
            issues.append(f"coordinate page {s['coord_page']!r} has no coordinates")
            lat = lon = None
            coord_basis = None
        else:
            lat, lon = locality_coords[0], locality_coords[1]
            coord_basis = {"kind": "affected locality", "wikipedia_title": coord_page["title"],
                           "url": coord_page["url"], "revision_id": coord_page["revision_id"],
                           "via": locality_coords[2]}
            if page["lat"] is not None:
                d = haversine_km(page["lat"], page["lon"], lat, lon)
                if d <= EVENT_COORD_MAX_KM:
                    lat, lon = page["lat"], page["lon"]
                    coord_basis = {"kind": "event article", "wikipedia_title": page["title"],
                                   "url": page["url"], "revision_id": page["revision_id"],
                                   "distance_to_locality_km": round(d, 1)}
                else:
                    coord_basis["event_article_coordinates_rejected"] = {
                        "lat": page["lat"], "lon": page["lon"], "distance_km": round(d, 1),
                        "reason": f"more than {EVENT_COORD_MAX_KM:.0f} km from the affected locality"}
            if not (INDIA_BBOX[0] <= lat <= INDIA_BBOX[1] and INDIA_BBOX[2] <= lon <= INDIA_BBOX[3]):
                issues.append(f"coordinates {lat},{lon} outside India")

        # -- figures: every summed component must occur in the article text
        # next to a keyword of its class
        raw_deaths = cfg.get("deaths")
        deaths_values = raw_deaths if isinstance(raw_deaths, list) else (
            [raw_deaths] if raw_deaths is not None else [])
        deaths_ev = []
        for value in deaths_values:
            ev = verify_figure(cands, value, {"deaths"})
            if not ev:
                issues.append(f"deaths figure {value} not found next to a deaths keyword")
            deaths_ev.append(ev)
        deaths = sum(deaths_values) if deaths_values else None

        affected_ev = []
        for value, cls in cfg["affected"]:
            ev = verify_figure(cands, value, {cls})
            if not ev:
                issues.append(f"affected component {value} not found next to a {cls} keyword")
            affected_ev.append(ev)
        affected = sum(value for value, _ in cfg["affected"])
        if affected <= 0:
            issues.append("affected population must be positive")

        # -- population / density from Wikidata (smallest unit >= affected)
        pop_basis = None
        for unit_page in (coord_page, admin_page, state_page):
            if not unit_page or not unit_page.get("wikidata"):
                continue
            pop, area = population_and_area(claims.get(unit_page["wikidata"], {}))
            if pop and area and pop >= affected:
                pop_basis = {"wikipedia_title": unit_page["title"], "wikidata": unit_page["wikidata"],
                             "population": int(pop), "area_km2": round(area, 2),
                             "population_density": round(pop / area, 1)}
                break
        if not pop_basis:
            issues.append("no Wikidata population/area >= affected population")

        if issues:
            problems.append((s["wiki"], issues))
            continue

        severity = severity_for(deaths or 0, affected)
        scenarios.append({
            "event_name": page["title"],
            "disaster_type": s["type"],
            "date": s["date"],
            "country": "India",
            "state": s["state"],
            "locality": s["locality"],
            "latitude": round(lat, 5),
            "longitude": round(lon, 5),
            "coordinate_source": coord_basis,
            "source": {"publisher": "Wikipedia", "title": page["title"], "url": page["url"],
                       "pageid": page["pageid"], "revision_id": page["revision_id"],
                       "wikidata": page["wikidata"]},
            "reported_deaths": deaths,
            "reported_deaths_evidence": deaths_ev,
            "affected_population": affected,
            "affected_population_basis": cfg["basis"],
            "affected_population_evidence": affected_ev,
            "locality_population": pop_basis,
            "severity": severity,
            "urgency": urgency_for(s["type"]),
            "priority": priority_for(severity),
            "estimated_duration_hours": duration_for(s["type"]),
            "patient_present": s["type"] in SUDDEN_ONSET,
        })

    return scenarios, problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", required=True)
    ap.add_argument("mode", choices=["review", "build"])
    args = ap.parse_args()

    seed = json.loads(SEED.read_text(encoding="utf-8"))
    fetcher = Fetcher(Path(args.cache))
    pages, texts, claims = load_all(fetcher, seed)

    if args.mode == "review":
        review(seed, pages, texts)
        return

    figures_cfg = json.loads(FIGURES.read_text(encoding="utf-8"))
    scenarios, problems = build(seed, pages, texts, claims, figures_cfg)

    excluded = [(t, i) for t, i in problems if i[0].startswith("excluded during curation")]
    failed = [(t, i) for t, i in problems if not i[0].startswith("excluded during curation")]
    print(f"candidates: {len(seed)}  valid: {len(scenarios)}  excluded: {len(excluded)}  "
          f"failed validation: {len(failed)}")
    for title, issues in failed:
        print(f"  FAILED {title}: {'; '.join(issues)}")

    (HERE / "build_report.json").write_text(json.dumps({
        "candidates": len(seed), "valid": len(scenarios),
        "excluded": [{"title": t, "reason": i[0]} for t, i in excluded],
        "failed_validation": [{"title": t, "issues": i} for t, i in failed],
    }, indent=2, ensure_ascii=False), encoding="utf-8")

    if failed or len(scenarios) != 100:
        print("DATASET NOT VALID: scenarios.json not written")
        sys.exit(1)

    # Chronological order, then stable IDs.
    scenarios.sort(key=lambda s: (s["date"], s["event_name"]))
    for n, s in enumerate(scenarios, start=1):
        s["scenario_id"] = f"E2E-{n:03d}"
        s["incident_id"] = f"E2E100-INC-{n:03d}"
        # Exactly what POST /orchestrate receives.
        s["aashray_request"] = {
            "incident_id": s["incident_id"],
            "incident_type": s["disaster_type"],
            "location": {"latitude": s["latitude"], "longitude": s["longitude"]},
            "locality": {
                "name": s["locality"],
                "population": s["locality_population"]["population"],
                "population_density": s["locality_population"]["population_density"],
                "affected_population": s["affected_population"],
            },
            "severity": s["severity"],
            "estimated_duration_hours": s["estimated_duration_hours"],
            "patient_present": s["patient_present"],
            "urgency": s["urgency"],
            "priority": s["priority"],
        }
    scenarios = [{"scenario_id": s.pop("scenario_id"), **s} for s in scenarios]

    dataset = {
        "dataset": "AASHRAY E2E-100 genuine disaster scenarios",
        "built_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "scenario_count": len(scenarios),
        "candidates_considered": len(seed),
        "rules": {
            "coordinates": f"event article coordinates if within {EVENT_COORD_MAX_KM:.0f} km of the affected "
                           "locality, otherwise the affected locality's Wikipedia coordinates",
            "affected_population": "sum of curated components, each verified to occur in the source text "
                                   "next to a keyword of its class (see affected_population_evidence)",
            "severity": "0.95 if deaths>=1000 or affected>=1e6; 0.85 if deaths>=100 or affected>=1e5; "
                        "0.75 if deaths>=20 or affected>=1e4; 0.65 if deaths>=1 or affected>=1e3; else 0.55",
            "urgency": "0.9 sudden-onset types; 0.8 floods/cyclones/dust storms; 0.5 slow-onset",
            "priority": "CRITICAL if severity>=0.9; HIGH >=0.8; MODERATE >=0.7; else LOW",
            "estimated_duration_hours": "24 casualty incidents; 72 earthquake/tsunami/landslide/dam failure/"
                                        "flash flood; 120 flood/cyclone/dust storm",
            "patient_present": "true for sudden-onset casualty-producing types, false for floods/cyclones/dust storms",
        },
        "scenarios": scenarios,
    }
    (EXPERIMENT / "scenarios.json").write_text(json.dumps(dataset, indent=2, ensure_ascii=False),
                                               encoding="utf-8")

    rows = ["| ID | Disaster | Type | Date | Location | Latitude | Longitude | Affected Population | "
            "Severity | Urgency | Priority | Patient Present | Source |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for s in scenarios:
        rows.append(
            f"| {s['scenario_id']} | {s['event_name']} | {s['disaster_type']} | {s['date']} | "
            f"{s['locality']}, {s['state']} | {s['latitude']} | {s['longitude']} | "
            f"{s['affected_population']:,} | {s['severity']} | {s['urgency']} | {s['priority']} | "
            f"{'yes' if s['patient_present'] else 'no'} | [Wikipedia rev {s['source']['revision_id']}]"
            f"({s['source']['url']}) |")
    (EXPERIMENT / "dataset_table.md").write_text("\n".join(rows) + "\n", encoding="utf-8")
    print("wrote scenarios.json and dataset_table.md")


if __name__ == "__main__":
    main()
