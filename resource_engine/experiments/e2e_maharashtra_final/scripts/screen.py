"""Screen the existing 100-scenario genuine-disaster dataset for the
Maharashtra-local final E2E run.

    python screen.py

Reads (never writes) the previous run's scenarios.json / results.json, the
canonical warehouses.json / responders.json, and the screening road-distance
measurements; writes everything under screening/.

Distance logic (per candidate):
  * The warehouse chain the pipeline produces is location-blind (fixed
    WH001..WH005 order, count set by affected population), so the chain each
    scenario gets is taken from the allocation AASHRAY actually produced for it
    in the previous run, and the chain legs from the road distances measured
    in that run.
  * lower bound  = measured chain + straight-line(last warehouse -> incident).
    Road distance can never be shorter than straight-line, so a lower bound
    above 150 km proves the scenario is out of scope.
  * expected     = measured total route (previous run) if one exists, else
    measured chain + measured final leg (screening probe) if one exists, else
    measured chain + straight-line x detour factor (2.0 <10 km, 1.7 <30 km,
    1.5 <60 km, 1.4 beyond; calibrated on Mumbai legs measured in the
    previous run).
  * A scenario whose lower bound is <=150 km but whose estimate is not
    clearly below 150 km is BORDERLINE_PENDING_MEASUREMENT: it is not run
    until a real road distance confirms it.
"""
import csv
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(r"C:\Users\Harsh\Desktop\AASHRAY Route Integration\aashray dummy")
PREV = ROOT / "experiments" / "e2e_100_previous_invalid_distance_scope"
EXP = ROOT / "experiments" / "e2e_maharashtra_final"
DB = ROOT / "resource_services" / "database"
OUT = EXP / "screening"
LIMIT_KM = 150.0
CLEAR_MARGIN_KM = 120.0  # estimates above this (but lower bound <=150) need a real measurement
MAHARASHTRA_BBOX = (15.6, 22.1, 72.6, 80.9)

# District of each Maharashtra locality in the existing dataset (from the
# locality string; administrative metadata only, coordinates untouched).
DISTRICT = {
    "E2E-001": "Mumbai City", "E2E-002": "Satara", "E2E-009": "Latur", "E2E-022": "Satara",
    "E2E-023": "Mumbai Suburban", "E2E-038": "Thane", "E2E-041": "Pune", "E2E-051": "Mumbai City",
    "E2E-053": "Mumbai City", "E2E-059": "Mumbai City", "E2E-062": "Ratnagiri", "E2E-064": "Pune",
    "E2E-067": "Raigad", "E2E-070": "Raigad", "E2E-071": "Bhandara", "E2E-076": "Mumbai Suburban",
    "E2E-077": "Ratnagiri", "E2E-081": "Mumbai Suburban", "E2E-085": "Buldhana", "E2E-087": "Raigad",
    "E2E-088": "Nagpur", "E2E-092": "Mumbai Suburban", "E2E-093": "Thane",
}


def haversine(a, b):
    (la1, lo1), (la2, lo2) = a, b
    p1, p2 = math.radians(la1), math.radians(la2)
    h = (math.sin(math.radians(la2 - la1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lo2 - lo1) / 2) ** 2)
    return 2 * 6371.0 * math.asin(math.sqrt(min(h, 1.0)))


def factor(km):
    return 2.0 if km < 10 else 1.7 if km < 30 else 1.5 if km < 60 else 1.4


def bucket(km):
    if km is None:
        return None
    for hi, name in ((10, "0-10"), (25, "10-25"), (50, "25-50"), (100, "50-100"), (150, "100-150")):
        if km <= hi:
            return name
    return ">150"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    scenarios = json.loads((PREV / "scenarios.json").read_text(encoding="utf-8"))["scenarios"]
    prev = {r["scenario_id"]: r for r in json.loads((PREV / "results.json").read_text(encoding="utf-8"))["scenarios"]}
    wh = {w["warehouse_id"]: (w["location"]["latitude"], w["location"]["longitude"])
          for w in json.loads((DB / "warehouses.json").read_text(encoding="utf-8"))}
    probes = {m["scenario_id"]: m for m in
              json.loads((OUT / "screening_probes.json").read_text(encoding="utf-8"))["measurements"]
              if m.get("road_km") is not None}

    # Chain legs measured in the previous run (median per source->destination).
    leg_km = defaultdict(list)
    for r in prev.values():
        for leg in ((r.get("route") or {}).get("legs") or []):
            if leg.get("distance_km") is not None and leg["destination"].startswith("WAREHOUSE:"):
                leg_km[(leg["source"], leg["destination"])].append(leg["distance_km"])
    chain_leg = {k: statistics.median(v) for k, v in leg_km.items()}

    rows = []
    for s in scenarios:
        sid, r = s["scenario_id"], prev[s["scenario_id"]]
        loc = (s["latitude"], s["longitude"])
        row = {
            "scenario_id": sid, "disaster": s["event_name"], "type": s["disaster_type"], "date": s["date"],
            "state": s["state"], "district": DISTRICT.get(sid, ""), "location": s["locality"],
            "latitude": s["latitude"], "longitude": s["longitude"], "source": s["source"]["url"],
            "coordinate_source": s["coordinate_source"].get("kind"), "affected_population": s["affected_population"],
        }
        nearest = min(wh, key=lambda w: haversine(wh[w], loc))
        row["nearest_warehouse"] = nearest
        row["approx_distance_km"] = round(haversine(wh[nearest], loc), 1)  # straight-line to nearest warehouse
        warehouses = r["allocation"]["warehouses_used"]
        responder = (r.get("agent_assignment") or {}).get("responder_id")
        row["warehouses"] = "+".join(warehouses)
        row["responder"] = responder
        rt = r.get("route") or {}
        row["existing_route_distance_km"] = rt.get("total_distance_km") if rt.get("route_status") == "ROUTE_PLANNED" else None

        invalid = []
        if s["latitude"] is None or s["longitude"] is None:
            invalid.append("missing coordinates")
        if not s["source"].get("url"):
            invalid.append("missing source")
        if not s["affected_population"] or s["affected_population"] <= 0:
            invalid.append("missing affected population")
        if not responder or not warehouses:
            invalid.append("previous run did not assign a responder/warehouse chain")

        if s["state"] != "Maharashtra":
            row.update(classification="OUT_OF_SCOPE", include=False, exclusion_reason=f"outside Maharashtra ({s['state']})")
            rows.append(row)
            continue
        la0, la1, lo0, lo1 = MAHARASHTRA_BBOX
        if not invalid and not (la0 <= loc[0] <= la1 and lo0 <= loc[1] <= lo1):
            invalid.append("coordinates outside Maharashtra bounding box")
        if invalid:
            row.update(classification="INVALID_DATA", include=False, exclusion_reason="; ".join(invalid))
            rows.append(row)
            continue

        stops = [f"RESPONDER:{responder}"] + [f"WAREHOUSE:{w}" for w in warehouses]
        chain = round(sum(chain_leg[(a, b)] for a, b in zip(stops, stops[1:])), 2)
        last = wh[warehouses[-1]]
        final_straight = round(haversine(last, loc), 2)
        row["chain_km"] = chain
        row["final_leg_straight_km"] = final_straight
        row["lower_bound_km"] = round(chain + final_straight, 1)
        if row["existing_route_distance_km"] is not None:
            row["expected_route_km"] = row["existing_route_distance_km"]
            row["expected_basis"] = "measured: full route in the previous run (same chain)"
        elif sid in probes:
            row["final_leg_road_km"] = probes[sid]["road_km"]
            row["expected_route_km"] = round(chain + probes[sid]["road_km"], 1)
            row["expected_basis"] = "measured chain + measured final leg (screening probe)"
        else:
            row["expected_route_km"] = round(chain + final_straight * factor(final_straight), 1)
            row["expected_basis"] = f"measured chain + straight-line x {factor(final_straight)} (estimate)"
        measured = not row["expected_basis"].endswith("(estimate)")

        if row["lower_bound_km"] > LIMIT_KM:
            row.update(classification="UNREALISTIC_DISTANCE", include=False,
                       exclusion_reason=f"lower bound {row['lower_bound_km']} km > {LIMIT_KM:.0f} km")
        elif measured and row["expected_route_km"] > LIMIT_KM:
            row.update(classification="UNREALISTIC_DISTANCE", include=False,
                       exclusion_reason=f"measured road distance {row['expected_route_km']} km > {LIMIT_KM:.0f} km")
        elif not measured and row["expected_route_km"] > CLEAR_MARGIN_KM:
            row.update(classification="BORDERLINE_PENDING_MEASUREMENT", include=False,
                       exclusion_reason=(f"lower bound {row['lower_bound_km']} km <= {LIMIT_KM:.0f} km but estimate "
                                         f"{row['expected_route_km']} km; not run until a real road distance confirms <= {LIMIT_KM:.0f} km"))
        else:
            row.update(classification="IN_SCOPE", include=True, exclusion_reason="")
        rows.append(row)

    for row in rows:
        row["expected_bucket"] = bucket(row.get("expected_route_km")) if row["state"] == "Maharashtra" else None

    final = [r for r in rows if r["include"]]
    exp = [r["expected_route_km"] for r in final]
    counts = Counter(r["classification"] for r in rows)
    summary = {
        "total_original_scenarios": len(rows),
        "maharashtra_scenarios": sum(r["state"] == "Maharashtra" for r in rows),
        "non_maharashtra_scenarios": counts["OUT_OF_SCOPE"],
        "invalid_or_missing_location": counts["INVALID_DATA"],
        "over_150_km": counts["UNREALISTIC_DISTANCE"],
        "borderline_pending_measurement": counts["BORDERLINE_PENDING_MEASUREMENT"],
        "final_qualifying_scenarios": len(final),
        "classification_counts": dict(counts),
        "non_maharashtra_by_state": dict(Counter(r["state"] for r in rows if r["classification"] == "OUT_OF_SCOPE")),
        "final_expected_distance_km": {
            "min": min(exp), "max": max(exp), "mean": round(statistics.mean(exp), 1),
            "median": round(statistics.median(exp), 1),
            "buckets": {b: sum(1 for r in final if r["expected_bucket"] == b)
                        for b in ("0-10", "10-25", "25-50", "50-100", "100-150", ">150")},
        },
        "maharashtra_expected_distance_buckets_all": {
            b: sum(1 for r in rows if r["state"] == "Maharashtra" and r["expected_bucket"] == b)
            for b in ("0-10", "10-25", "25-50", "50-100", "100-150", ">150")},
        "chain_legs_measured_previous_run_km": {f"{a} -> {b}": v for (a, b), v in sorted(chain_leg.items())},
    }

    # Quota estimate for the final dataset: AASHRAY sends one Route Engine
    # call per leg (N warehouses -> N + 1 legs); the Route Engine sends one
    # Google computeRoutes request per call.
    legs = {r["scenario_id"]: len(r["warehouses"].split("+")) + 1 for r in final}
    pending = [r for r in rows if r["classification"] == "BORDERLINE_PENDING_MEASUREMENT"]
    summary["quota_estimate"] = {
        "scenarios": len(final),
        "warehouses_per_scenario": {sid: n - 1 for sid, n in legs.items()},
        "expected_route_legs": sum(legs.values()),
        "expected_route_engine_http_calls": sum(legs.values()),
        "expected_google_compute_routes_requests": sum(legs.values()),
        "expected_openweb_ninja_requests": sum(legs.values()),
        "borderline_measurement_requests": len(pending),
        "worst_case_if_borderline_qualify": sum(legs.values()) + len(pending)
                                            + sum(len(r["warehouses"].split("+")) + 1 for r in pending),
    }
    (OUT / "screening.json").write_text(json.dumps({"summary": summary, "candidates": rows}, indent=1, ensure_ascii=False),
                                        encoding="utf-8")
    cols = ["scenario_id", "disaster", "type", "date", "state", "district", "location", "latitude", "longitude", "source",
            "affected_population", "warehouses", "responder", "existing_route_distance_km", "nearest_warehouse",
            "approx_distance_km", "chain_km", "final_leg_straight_km", "final_leg_road_km", "lower_bound_km",
            "expected_route_km", "expected_basis", "expected_bucket", "classification", "include", "exclusion_reason"]
    with (OUT / "screening.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    # Execution dataset: the qualifying scenarios exactly as in the existing
    # dataset; only the incident id is new so this run's missions are distinct.
    final_ids = {r["scenario_id"] for r in final}
    chosen = []
    for s in scenarios:
        if s["scenario_id"] in final_ids:
            s = json.loads(json.dumps(s))
            s["original_incident_id"] = s["incident_id"]
            s["incident_id"] = s["incident_id"].replace("E2E100-INC-", "MHF-INC-")
            s["aashray_request"]["incident_id"] = s["incident_id"]
            s["district"] = DISTRICT[s["scenario_id"]]
            chosen.append(s)
    (EXP / "scenarios_final.json").write_text(json.dumps(
        {"dataset": "Maharashtra-local subset of the existing genuine-disaster dataset "
                    "(experiments/e2e_100_previous_invalid_distance_scope/scenarios.json)",
         "selection": "screening/screening.json (IN_SCOPE only)",
         "scenario_count": len(chosen), "scenarios": chosen}, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
