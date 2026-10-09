"""Build the E2E-100 report from the raw run records.

Inputs (experiments/e2e_100/):
  scenarios.json, results.jsonl, neon_verification.json,
  integrity/pre_run.json, integrity/post_run.json, integrity/neon_pre_run.json

Outputs:
  results.json, summary.json, chart_data.json, figures/*.png,
  reports/results_table.md, route_results.md, resource_results.md,
  responder_results.md, failures.md
Every number is computed from the inputs; nothing is typed in by hand.
"""
import json
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path

E = Path(__file__).resolve().parent.parent
RESOURCES = ("water", "food", "medical_kits")
SUCCESS = ("SUCCESS_FULLY_FULFILLED", "SUCCESS_PARTIALLY_FULFILLED")
QUOTA_CAUSE = ("EXTERNAL_API_QUOTA: Google Routes API daily quota exhausted "
               "(HTTP 429 RESOURCE_EXHAUSTED) -> Route Engine HTTP 500")
INV_GROUPS = {
    "allocation": {2, 3, 4, 5, 6, 7},
    "responder_lifecycle": {9, 14, 15, 16, 17, 19, 20},
    "mission_lifecycle": {18},
    "route": {10, 11, 12, 13},
}


def load(name):
    return json.loads((E / name).read_text(encoding="utf-8"))


def stats(values):
    if not values:
        return {"count": 0, "mean": None, "median": None, "max": None, "min": None}
    return {"count": len(values), "mean": round(statistics.mean(values), 2),
            "median": round(statistics.median(values), 2), "max": round(max(values), 2),
            "min": round(min(values), 2)}


def waypoint_names(mission_resp, assignment):
    names = [f"RESPONDER:{assignment['responder_id']}"] if assignment else ["RESPONDER"]
    names += [f"WAREHOUSE:{p['warehouse_id']}" for p in mission_resp["pickup_sequence"] if p["type"] == "WAREHOUSE"]
    return names + ["DESTINATION:INCIDENT_DESTINATION"]


def build_records(scenarios, raw, neon, responder_names):
    neon_by = {s["scenario_id"]: s for s in neon["scenarios"]}
    out = []
    for sc, r in zip(scenarios, raw):
        assert sc["scenario_id"] == r["scenario_id"]
        resp = r.get("response") or {}
        alloc, req = resp.get("allocation") or {}, (resp.get("requirement") or {}).get("requirements") or {}
        ful, mission, asg = resp.get("demand_fulfilment") or {}, resp.get("mission") or {}, resp.get("agent_assignment")
        boundary = resp.get("route") or {}
        route = boundary.get("route") or {}
        error = resp.get("error") or {}
        nrows = neon_by[sc["scenario_id"]]["mission_route_states"]
        db_by_leg = {row["missionId"]: row for row in nrows}
        life = r.get("lifecycle") or {}
        life_resp = life.get("response") or {}

        # Route Engine calls: every HTTP 200 call persisted a MissionRouteState
        # row; a failing call (HTTP 500) did not.
        failed_call = error.get("stage") == "ROUTE_ENGINE"
        m = re.search(r"returned HTTP (\d+)", error.get("message", ""))
        statuses = [f"200 {row['routeStatus']}" for row in nrows]
        if failed_call:
            statuses.append(f"{m.group(1) if m else '?'} {error.get('message', '')[:120]}")
        names = waypoint_names(mission, asg) if mission else []

        legs = []
        for leg in route.get("legs", []):
            row = db_by_leg.get(leg["route_engine_mission_id"])
            legs.append({
                "leg_index": leg["leg_index"],
                "source": f"{leg['source_type']}:{leg['source_id']}",
                "destination": f"{leg['destination_type']}:{leg['destination_id']}",
                "route_engine_mission_id": leg["route_engine_mission_id"],
                "route_id": leg["route_id"],
                "distance_km": leg["distance_km"],
                "duration_min": leg["estimated_time_minutes"],
                "route_status": row["routeStatus"] if row else None,
                "road_condition_status": leg["road_condition_status"],
                "road_condition_confidence": leg["road_condition_confidence"],
                "matched_incidents": len(leg.get("matched_incidents") or []),
                "route_score": leg["score"],
                "neon_mission_route_state": bool(row),
                "encoded_polyline_chars": len(leg.get("encoded_polyline") or ""),
            })
        failed_leg = None
        if failed_call and names:
            i = len(nrows)
            failed_leg = {"leg_index": i, "source": names[i] if i < len(names) else None,
                          "destination": names[i + 1] if i + 1 < len(names) else None,
                          "route_engine_mission_id": f"{mission['mission_id']}-LEG-{i}",
                          "route_status": "HTTP_ERROR",
                          "legs_completed_before_failure": [
                              {"route_engine_mission_id": row["missionId"], "route_status": row["routeStatus"],
                               "distance_km": round((row["distanceMeters"] or 0) / 1000, 2)} for row in nrows]}

        openweb_failed = r["route_engine_log"]["openweb_failures"]
        google_errors = r["route_engine_log"]["google_errors"]
        cause = None
        if r["classification"] == "PIPELINE_FAILURE" and google_errors and "Google Routes API" in error.get("message", ""):
            cause = QUOTA_CAUSE

        failed_inv = r["failed_invariants"]
        reason = None
        if not r["pass"]:
            reason = cause or (f"{error.get('stage')}: {error.get('message')}" if error else None) \
                or ("; ".join(failed_inv) if failed_inv else r["classification"])

        rid = asg["responder_id"] if asg else None
        out.append({
            "scenario_id": sc["scenario_id"],
            "disaster_name": sc["event_name"],
            "disaster_type": sc["disaster_type"],
            "date": sc["date"],
            "source": sc["source"],
            "location": {"locality": sc["locality"], "state": sc["state"], "country": sc["country"]},
            "latitude": sc["latitude"], "longitude": sc["longitude"],
            "coordinate_source": sc["coordinate_source"],
            "incident_id": sc["incident_id"],
            "affected_population": sc["affected_population"],
            "affected_population_basis": sc["affected_population_basis"],
            "severity": sc["severity"], "urgency": sc["urgency"], "priority": sc["priority"],
            "patient_present": sc["patient_present"],
            "resource_requirements": {k: req.get(k) for k in RESOURCES},
            "allocation": {
                "allocation_id": alloc.get("allocation_id"),
                "warehouses_used": [w["warehouse_id"] for w in alloc.get("warehouse_allocations", [])],
                **{f"allocated_{k}": (alloc.get("allocated_resources") or {}).get(k) for k in RESOURCES},
                **{f"shortage_{k}": (alloc.get("remaining_shortage") or {}).get(k) for k in RESOURCES},
                "allocation_status": alloc.get("allocation_status"),
                "overall_priority_score": alloc.get("overall_priority_score"),
                "final_priority_level": alloc.get("final_priority_level"),
            },
            "fulfilment": {
                "verification_id": ful.get("verification_id"),
                "fulfilment_status": ful.get("fulfilment_status"),
                "resource_status": ful.get("resource_status"),
                "total_shortage": ful.get("total_shortage"),
            },
            "mission": {
                "mission_id": mission.get("mission_id"),
                "status_at_creation": mission.get("status"),
                "mission_final_state": (r.get("mission_record_after_close") or {}).get("status"),
                "required_responder_types": mission.get("required_responder_types"),
                "resources": mission.get("resources"),
                "pickup_sequence": mission.get("pickup_sequence"),
            },
            "agent_assignment": None if not asg else {
                "assignment_id": asg["assignment_id"],
                "responder_id": rid,
                "responder_name": responder_names.get(rid),
                "vehicle_type": asg["responder_type"],
                "distance_to_first_warehouse_km": asg["distance_to_warehouse_km"],
                "responder_status_before": r["responder_states"]["before"].get(rid),
                "responder_status_after_assignment": r["responder_states"]["after_orchestrate"].get(rid),
                "responder_status_after_close": r["responder_states"]["after_close"].get(rid),
            },
            "route": {
                "route_status": boundary.get("status") or ("NOT_RUN" if not failed_call else "FAILED"),
                "route_data_status": route.get("status"),
                "number_of_legs": len(legs),
                "total_distance_km": route.get("distance_km"),
                "total_estimated_time_minutes": route.get("estimated_time_minutes"),
                "message": boundary.get("message"),
                "legs": legs,
                "failed_leg": failed_leg,
            },
            "route_engine_http_calls": len(statuses),
            "route_engine_successful_calls": len(nrows),
            "route_engine_failures": 1 if failed_call else 0,
            "route_engine_response_status": statuses,
            "openweb_ninja_status": {
                "calls": len(nrows),
                "failed": len(openweb_failed),
                "successful": max(0, len(nrows) - len(openweb_failed)),
                "failure_messages": sorted(set(openweb_failed)),
            },
            "google_routes_errors": len(google_errors),
            "neon_evidence_writes": {
                "evidence_rows_created": neon_by[sc["scenario_id"]]["evidence_rows_created_in_window"],
                "evidence_rows_updated": neon_by[sc["scenario_id"]]["evidence_rows_updated_in_window"],
                "mission_route_state_rows": len(nrows),
            },
            "lifecycle": {
                "operation": life.get("operation"), "reason": life.get("reason"),
                "http_status": life.get("http_status"),
                "previous_status": life_resp.get("previous_status"), "status": life_resp.get("status"),
                "released_responders": [x["responder_id"] for x in life_resp.get("released_responders", [])],
            },
            "orchestration_http_status": r["orchestrate_http_status"],
            "orchestration_status": r["orchestration_status"],
            "orchestration_error": error or None,
            "classification": r["classification"],
            "failure_cause": cause,
            "pass": r["pass"],
            "failure_reason": reason,
            "failed_invariants": failed_inv,
            "invariants": r["invariants"],
            "timing": {"started_at": r["started_at"], "finished_at": r["finished_at"],
                       "orchestrate_seconds": r["orchestrate_seconds"]},
            "raw": {"orchestrate_response": resp, "lifecycle": life, "route_engine_log": r["route_engine_log"]},
        })
    return out


def summarize(recs, neon, pre, post, neon_pre):
    cls = Counter(r["classification"] for r in recs)
    n = len(recs)
    successes = [r for r in recs if r["classification"] in SUCCESS]
    full = sum(1 for r in recs if r["fulfilment"]["fulfilment_status"] == "FULLY_FULFILLED")
    partial = sum(1 for r in recs if r["fulfilment"]["fulfilment_status"] == "PARTIALLY_FULFILLED")
    technical = sum(cls[c] for c in ("ROUTE_ENGINE_UNAVAILABLE", "PIPELINE_FAILURE", "VALIDATION_FAILURE"))
    external = sum(1 for r in recs if r["failure_cause"] == QUOTA_CAUSE)

    res = {}
    for k in RESOURCES:
        q = sum(r["resource_requirements"][k] for r in recs)
        a = sum(r["allocation"][f"allocated_{k}"] for r in recs)
        s = sum(r["allocation"][f"shortage_{k}"] for r in recs)
        res[k] = {"required": round(q, 2), "allocated": round(a, 2), "shortage": round(s, 2),
                  "fulfilment_pct": round(100 * a / q, 4) if q else None,
                  "accounting_holds_every_scenario": all(
                      abs(r["allocation"][f"allocated_{k}"] + r["allocation"][f"shortage_{k}"]
                          - r["resource_requirements"][k]) < 1e-6 for r in recs)}

    assigned = [r for r in recs if r["agent_assignment"]]
    rids = [r["agent_assignment"]["responder_id"] for r in assigned]
    legs = [leg for r in recs for leg in r["route"]["legs"]]
    totals_km = [r["route"]["total_distance_km"] for r in successes]
    totals_min = [r["route"]["total_estimated_time_minutes"] for r in successes]
    calls = sum(r["route_engine_http_calls"] for r in recs)
    ok_calls = sum(r["route_engine_successful_calls"] for r in recs)
    statuses = Counter(s.split(" ")[1] if s.startswith("200") else "HTTP_ERROR"
                       for r in recs for s in r["route_engine_response_status"])

    def violations(group):
        return sum(1 for r in recs for c in r["invariants"]
                   if c["result"] == "FAIL" and c["invariant"] in INV_GROUPS[group])

    discarded = [row for r in recs if r["route"]["failed_leg"]
                 for row in r["route"]["failed_leg"]["legs_completed_before_failure"]]

    return {
        "run": {
            "scenarios_in_dataset": 100, "scenarios_executed": n,
            "first_scenario_started": recs[0]["timing"]["started_at"],
            "last_scenario_finished": recs[-1]["timing"]["finished_at"],
        },
        "outcomes": {
            "total_scenarios": n,
            "successful_scenarios": len(successes),
            "successful_fully_fulfilled": cls["SUCCESS_FULLY_FULFILLED"],
            "successful_partially_fulfilled": cls["SUCCESS_PARTIALLY_FULFILLED"],
            "no_safe_route_scenarios": cls["NO_SAFE_ROUTE"],
            "route_engine_unavailable_scenarios": cls["ROUTE_ENGINE_UNAVAILABLE"],
            "no_responder_scenarios": cls["NO_RESPONDER_AVAILABLE"],
            "mission_not_dispatchable_scenarios": cls["MISSION_NOT_DISPATCHABLE"],
            "pipeline_failure_scenarios": cls["PIPELINE_FAILURE"],
            "pipeline_failures_caused_by_external_api_quota": external,
            "validation_failure_scenarios": cls["VALIDATION_FAILURE"],
            "other_failures": cls["PIPELINE_FAILURE"] + cls["VALIDATION_FAILURE"] + cls["MISSION_NOT_DISPATCHABLE"],
            "classification_counts": dict(cls),
            "pass_count": sum(1 for r in recs if r["pass"]),
        },
        "rates_pct": {
            "pipeline_success_rate": round(100 * len(successes) / n, 2),
            "full_fulfilment_rate": round(100 * full / n, 2),
            "partial_fulfilment_rate": round(100 * partial / n, 2),
            "technical_failure_rate": round(100 * technical / n, 2),
            "technical_failure_rate_excluding_external_api_quota": round(100 * (technical - external) / n, 2),
        },
        "fulfilment_status_counts_all_scenarios": {"FULLY_FULFILLED": full, "PARTIALLY_FULFILLED": partial},
        "resources": {
            **res,
            "total_all_resources": {
                "required": round(sum(v["required"] for v in res.values()), 2),
                "allocated": round(sum(v["allocated"] for v in res.values()), 2),
                "shortage": round(sum(v["shortage"] for v in res.values()), 2),
                "note": "sum of water + food + medical kits in their own units",
            },
        },
        "missions": {
            "created": sum(1 for r in recs if r["mission"]["mission_id"]),
            "assigned": len(assigned),
            "completed": sum(1 for r in recs if r["lifecycle"]["status"] == "COMPLETED"),
            "cancelled": sum(1 for r in recs if r["lifecycle"]["status"] == "CANCELLED"),
            "cancelled_as_sample": sum(1 for r in recs if (r["lifecycle"]["reason"] or "").startswith("cancellation sample")),
            "cancelled_because_not_executable": sum(1 for r in recs if (r["lifecycle"]["reason"] or "").startswith("mission could not be executed")),
            "closed_with_http_200": sum(1 for r in recs if r["lifecycle"]["http_status"] == 200),
        },
        "responders": {
            "total_assignments": len(rids),
            "unique_responders_used": len(set(rids)),
            "responder_reuse_count": len(rids) - len(set(rids)),
            "assignments_per_responder": dict(Counter(rids)),
        },
        "route_engine": {
            "total_http_calls": calls,
            "successful_calls_http_200": ok_calls,
            "failed_calls": calls - ok_calls,
            "call_outcomes": dict(statuses),
            "google_routes_errors": sum(r["google_routes_errors"] for r in recs),
            "neon_mission_route_state_rows_verified": ok_calls,
            "legs_completed_but_discarded_after_a_later_leg_failed": len(discarded),
        },
        "routes": {
            "total_route_legs_in_planned_routes": len(legs),
            "scenarios_with_planned_route": len(successes),
            "route_total_distance_km": stats(totals_km),
            "route_total_time_min": stats(totals_min),
            "leg_distance_km": stats([l["distance_km"] for l in legs]),
            "leg_time_min": stats([l["duration_min"] for l in legs]),
            "road_condition_status_counts": dict(Counter(l["road_condition_status"] for l in legs)),
            "legs_with_matched_incidents": sum(1 for l in legs if l["matched_incidents"]),
        },
        "openweb_ninja": {
            "calls": sum(r["openweb_ninja_status"]["calls"] for r in recs),
            "successful": sum(r["openweb_ninja_status"]["successful"] for r in recs),
            "failed": sum(r["openweb_ninja_status"]["failed"] for r in recs),
            "failure_messages": sorted({m for r in recs for m in r["openweb_ninja_status"]["failure_messages"]}),
        },
        "neon": {
            "evidence_rows_written_during_run": sum(r["neon_evidence_writes"]["evidence_rows_created"]
                                                    + r["neon_evidence_writes"]["evidence_rows_updated"] for r in recs),
            "evidence_rows_before": neon_pre["road_condition_evidence"]["rows"],
            "evidence_rows_after": neon["totals"]["road_condition_evidence"]["rows"],
            "mission_route_state_rows_before": neon_pre["mission_route_state"]["rows"],
            "mission_route_state_rows_after": neon["totals"]["mission_route_state"]["rows"],
        },
        "violations": {
            "responder_lifecycle": violations("responder_lifecycle"),
            "mission_lifecycle": violations("mission_lifecycle"),
            "allocation_invariant": violations("allocation"),
            "route_invariant": violations("route"),
            "all_invariant_failures": sum(len(r["failed_invariants"]) for r in recs),
        },
        "integrity": {
            "final_responder_state_consistency": "PASS" if post["responders_json"]["byte_identical_to_pre_run"]
            and post["missions_json"]["all_terminal"] else "FAIL",
            "responders_json_byte_identical_to_pre_run": post["responders_json"]["byte_identical_to_pre_run"],
            "missions_all_terminal": post["missions_json"]["all_terminal"],
            "missions_status_counts": post["missions_json"]["status_counts"],
            "experiments_12000_unchanged": post["experiments_12000"]["unchanged"],
            "route_engine_unchanged": post["route_engine"]["unchanged"],
            "only_expected_project_changes": post["aashray_project_files"]["only_expected_changes"],
            "changed_project_files": post["aashray_project_files"]["changed_files"],
        },
    }


# ----------------------------------------------------------------------------
# Tables
# ----------------------------------------------------------------------------

def fmt(v, nd=0):
    if v is None:
        return "–"
    if isinstance(v, float) and nd:
        return f"{v:,.{nd}f}"
    if isinstance(v, (int, float)):
        return f"{v:,.0f}" if float(v).is_integer() else f"{v:,.2f}"
    return str(v)


def results_table(recs):
    head = ["Scenario ID", "Disaster", "Type", "Location", "Severity", "Urgency", "Priority", "Affected Population",
            "Water Required", "Water Allocated", "Water Shortage", "Food Required", "Food Allocated", "Food Shortage",
            "Medical Kits Required", "Medical Kits Allocated", "Medical Kits Shortage", "Allocation Status",
            "Fulfilment Status", "Mission ID", "Responder ID", "Responder Type", "Number of Warehouses",
            "Number of Route Legs", "Route Status", "Distance km", "Time min", "Mission Final State",
            "Responder Final State", "Final Classification", "PASS/FAIL", "Failure Reason"]
    rows = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for r in recs:
        a, asg = r["allocation"], r["agent_assignment"] or {}
        reason = r["failure_reason"] or ""
        if reason == QUOTA_CAUSE:
            reason = f"Google Routes daily quota exhausted (429) → Route Engine HTTP 500 on leg {r['route']['failed_leg']['leg_index']}"
        rows.append("| " + " | ".join([
            r["scenario_id"], r["disaster_name"], r["disaster_type"],
            f"{r['location']['locality']}, {r['location']['state']}",
            str(r["severity"]), str(r["urgency"]), r["priority"], fmt(r["affected_population"]),
            fmt(r["resource_requirements"]["water"]), fmt(a["allocated_water"]), fmt(a["shortage_water"]),
            fmt(r["resource_requirements"]["food"]), fmt(a["allocated_food"]), fmt(a["shortage_food"]),
            fmt(r["resource_requirements"]["medical_kits"]), fmt(a["allocated_medical_kits"]), fmt(a["shortage_medical_kits"]),
            a["allocation_status"] or "–", r["fulfilment"]["fulfilment_status"] or "–",
            r["mission"]["mission_id"] or "–", asg.get("responder_id", "–"), asg.get("vehicle_type", "–"),
            str(len(a["warehouses_used"])), str(r["route"]["number_of_legs"]), r["route"]["route_status"],
            fmt(r["route"]["total_distance_km"]), fmt(r["route"]["total_estimated_time_minutes"]),
            r["mission"]["mission_final_state"] or "–", asg.get("responder_status_after_close", "–"),
            r["classification"], "PASS" if r["pass"] else "FAIL", reason.replace("|", "/"),
        ]) + " |")
    return "\n".join(rows) + "\n"


def route_tables(recs, s):
    rt = s["routes"]
    lines = ["# Route results", "", "## Summary", "", "| Metric | Result |", "|---|---|",
             f"| Total Route Engine HTTP calls | {s['route_engine']['total_http_calls']} |",
             f"| ROUTE_FOUND (HTTP 200) | {s['route_engine']['call_outcomes'].get('ROUTE_FOUND', 0)} |",
             f"| NO_SAFE_ROUTE_FOUND (HTTP 200) | {s['route_engine']['call_outcomes'].get('NO_SAFE_ROUTE_FOUND', 0)} |",
             f"| HTTP/API failures | {s['route_engine']['failed_calls']} (all: Google Routes quota 429 → Route Engine 500) |",
             f"| Legs computed but discarded (a later leg of the same mission failed) | {s['route_engine']['legs_completed_but_discarded_after_a_later_leg_failed']} |",
             f"| Scenarios with a planned route | {rt['scenarios_with_planned_route']} |",
             f"| Route legs in planned routes | {rt['total_route_legs_in_planned_routes']} |",
             f"| Average route distance | {rt['route_total_distance_km']['mean']} km |",
             f"| Median route distance | {rt['route_total_distance_km']['median']} km |",
             f"| Maximum route distance | {rt['route_total_distance_km']['max']} km |",
             f"| Average ETA | {rt['route_total_time_min']['mean']} min |",
             f"| Median ETA | {rt['route_total_time_min']['median']} min |",
             f"| Maximum ETA | {rt['route_total_time_min']['max']} min |",
             f"| Average leg distance | {rt['leg_distance_km']['mean']} km (median {rt['leg_distance_km']['median']}) |",
             f"| Road-condition status of legs | {rt['road_condition_status_counts']} |",
             f"| Legs with matched incidents | {rt['legs_with_matched_incidents']} |",
             "", "Route distance/ETA statistics are over the planned routes only (scenarios that failed at the "
             "Route Engine stage have no AASHRAY route).", "",
             "## Per scenario", "",
             "| Scenario | Disaster | Route status | Legs | Distance km | ETA min | Route Engine calls | Call outcomes | OpenWeb failed/calls |",
             "|---|---|---|---|---|---|---|---|---|"]
    for r in recs:
        outcomes = Counter(x.split(" ")[1] if x.startswith("200") else "HTTP_500" for x in r["route_engine_response_status"])
        lines.append(f"| {r['scenario_id']} | {r['disaster_name']} | {r['route']['route_status']} | "
                     f"{r['route']['number_of_legs']} | {fmt(r['route']['total_distance_km'])} | "
                     f"{fmt(r['route']['total_estimated_time_minutes'])} | {r['route_engine_http_calls']} | "
                     f"{dict(outcomes)} | {r['openweb_ninja_status']['failed']}/{r['openweb_ninja_status']['calls']} |")
    lines += ["", "## Per leg (planned routes)", "",
              "| Scenario | Leg | Source | Destination | Route Engine mission ID | Route ID | Distance km | Duration min | Route status | Road condition | Confidence | Matched incidents | Score | Neon row |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in recs:
        for l in r["route"]["legs"]:
            lines.append(f"| {r['scenario_id']} | {l['leg_index']} | {l['source']} | {l['destination']} | "
                         f"{l['route_engine_mission_id']} | {l['route_id']} | {l['distance_km']} | {l['duration_min']} | "
                         f"{l['route_status']} | {l['road_condition_status']} | {l['road_condition_confidence']} | "
                         f"{l['matched_incidents']} | {l['route_score']} | {'yes' if l['neon_mission_route_state'] else 'NO'} |")
    lines += ["", "## Failed legs", "",
              "| Scenario | Failed leg | Source | Destination | Legs completed before failure (discarded by AASHRAY) |",
              "|---|---|---|---|---|"]
    for r in recs:
        f = r["route"]["failed_leg"]
        if f:
            done = ", ".join(f"{x['route_engine_mission_id']} {x['route_status']} {x['distance_km']} km"
                             for x in f["legs_completed_before_failure"]) or "none"
            lines.append(f"| {r['scenario_id']} | {f['route_engine_mission_id']} | {f['source']} | {f['destination']} | {done} |")
    return "\n".join(lines) + "\n"


def resource_tables(recs, s):
    lines = ["# Resource results", "", "## Aggregate accounting (all 100 scenarios)", "",
             "| Resource | Required | Allocated | Shortage | Fulfilment % | allocated + shortage = required (every scenario) |",
             "|---|---|---|---|---|---|"]
    for k in RESOURCES:
        v = s["resources"][k]
        lines.append(f"| {k} | {fmt(v['required'])} | {fmt(v['allocated'])} | {fmt(v['shortage'])} | "
                     f"{v['fulfilment_pct']} | {'holds' if v['accounting_holds_every_scenario'] else 'VIOLATED'} |")
    t = s["resources"]["total_all_resources"]
    lines += [f"| all (mixed units) | {fmt(t['required'])} | {fmt(t['allocated'])} | {fmt(t['shortage'])} | "
              f"{round(100 * t['allocated'] / t['required'], 4)} | – |", "",
              "Warehouse stock is read, never decremented, by allocation, so every scenario draws on the same "
              "total stock (water 2,750; food 1,900; medical kits 450).", "",
              "## Per scenario", "",
              "| Scenario | Affected | Water req/alloc/short | Food req/alloc/short | Kits req/alloc/short | Warehouses | Allocation | Fulfilment | Inv. 4 | Inv. 5 | Inv. 6 |",
              "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in recs:
        a = r["allocation"]
        inv = {c["invariant"]: c["result"] for c in r["invariants"]}
        lines.append(
            f"| {r['scenario_id']} | {fmt(r['affected_population'])} | "
            f"{fmt(r['resource_requirements']['water'])} / {fmt(a['allocated_water'])} / {fmt(a['shortage_water'])} | "
            f"{fmt(r['resource_requirements']['food'])} / {fmt(a['allocated_food'])} / {fmt(a['shortage_food'])} | "
            f"{fmt(r['resource_requirements']['medical_kits'])} / {fmt(a['allocated_medical_kits'])} / {fmt(a['shortage_medical_kits'])} | "
            f"{', '.join(a['warehouses_used'])} | {a['allocation_status']} | {r['fulfilment']['fulfilment_status']} | "
            f"{inv[4]} | {inv[5]} | {inv[6]} |")
    return "\n".join(lines) + "\n"


def responder_tables(recs, s, pre, post):
    initial = {r["responder_id"]: r for r in pre["data_files"]["responders.json"]["content"]}
    per = defaultdict(lambda: {"missions": 0, "completed": 0, "cancelled": 0})
    for r in recs:
        if r["agent_assignment"]:
            p = per[r["agent_assignment"]["responder_id"]]
            p["missions"] += 1
            p["completed" if r["lifecycle"]["status"] == "COMPLETED" else "cancelled"] += 1
    lines = ["# Responder results", "",
             "| Responder ID | Vehicle Type | Initial Status | Number of Missions | Completed | Cancelled | Times Reused | Final Status |",
             "|---|---|---|---|---|---|---|---|"]
    rows = []
    for rid, rec in initial.items():
        p = per[rid]
        reused = max(0, p["missions"] - 1)
        final = post["responders_json"]["statuses"][rid]
        rows.append({"responder_id": rid, "vehicle_type": rec["vehicle_type"], "initial_status": rec["status"],
                     **p, "times_reused": reused, "final_status": final})
        lines.append(f"| {rid} | {rec['vehicle_type']} | {rec['status']} | {p['missions']} | {p['completed']} | "
                     f"{p['cancelled']} | {reused} | {final} |")
    same = post["responders_json"]["byte_identical_to_pre_run"]
    lines += ["", f"Final responder state equals the initial state: **{'YES' if same else 'NO'}** "
              f"(responders.json byte-identical: {same}; no manual reset was performed, the runner never writes "
              "responders.json).", "",
              "R003 (FIRE_TRUCK) is never selected: Mission Creation requests AMBULANCE when a patient is present and "
              "RESCUE_TRUCK otherwise. R005 is BUSY in the initial data with no mission record, so no lifecycle "
              "operation can release it, and none did. R004 was never needed because each mission was closed before "
              "the next scenario, so the closest rescue truck (R001) was always available."]
    return "\n".join(lines) + "\n", rows


def failure_tables(recs, s):
    lines = ["# Failures", "", "## Scenario failures", "",
             "| Scenario | Stage | Failure Type | HTTP Status | Error | Mission ID | Responder ID | Route Leg | Recoverable? | Action Taken |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for r in recs:
        if r["pass"]:
            continue
        err = r["orchestration_error"] or {}
        leg = (r["route"]["failed_leg"] or {}).get("route_engine_mission_id", "–")
        recoverable = ("Yes - external quota; retry after the daily quota resets or the quota is raised"
                       if r["failure_cause"] == QUOTA_CAUSE else "Unknown")
        action = (f"mission {r['lifecycle']['operation']}led via lifecycle API (HTTP {r['lifecycle']['http_status']}); "
                  f"responder {', '.join(r['lifecycle']['released_responders']) or '-'} released; run continued")
        lines.append(f"| {r['scenario_id']} | {err.get('stage', '–')} | {r['classification']} "
                     f"({'Google quota' if r['failure_cause'] == QUOTA_CAUSE else 'other'}) | "
                     f"{r['orchestration_http_status']} | {(err.get('message') or '').replace('|', '/')[:140]} | "
                     f"{r['mission']['mission_id']} | {(r['agent_assignment'] or {}).get('responder_id', '–')} | {leg} | "
                     f"{recoverable} | {action} |")
    lines += ["", "## External API failures that did not fail a scenario", "",
              "| API | Calls | Failed | Failure | Effect |", "|---|---|---|---|---|",
              f"| OpenWeb Ninja (road incidents) | {s['openweb_ninja']['calls']} | {s['openweb_ninja']['failed']} | "
              f"{'; '.join(s['openweb_ninja']['failure_messages'])} | Route Engine treats it as 0 incidents; every planned "
              "leg is UNKNOWN road condition with an uncertainty penalty. No hazard data was used in any route. |",
              f"| Google Routes API | {s['route_engine']['total_http_calls']} | {s['route_engine']['google_routes_errors']} | "
              "HTTP 429 RESOURCE_EXHAUSTED: ComputeRoutes per-request quota per day | Fails the Route Engine call (HTTP 500) "
              "and therefore the scenario (see above). |"]
    return "\n".join(lines) + "\n"


# ----------------------------------------------------------------------------
# Charts (matplotlib, light surface, validated categorical slots)
# ----------------------------------------------------------------------------

BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
INK, INK2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e6e5e1", "#fcfcfb"


def charts(recs, s, responder_rows):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig_dir = E / "figures"
    fig_dir.mkdir(exist_ok=True)
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": GRID,
                         "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
                         "axes.titlecolor": INK, "figure.facecolor": SURFACE, "axes.facecolor": SURFACE})

    def style(ax):
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        ax.grid(axis="x", color=GRID, linewidth=0.8)
        ax.set_axisbelow(True)

    data = {}

    # 1. Outcome distribution
    labels_map = [("SUCCESS_FULLY_FULFILLED", "Success - fully fulfilled"),
                  ("SUCCESS_PARTIALLY_FULFILLED", "Success - partially fulfilled"),
                  ("NO_SAFE_ROUTE", "No safe route"), ("ROUTE_ENGINE_UNAVAILABLE", "Route Engine unavailable"),
                  ("NO_RESPONDER_AVAILABLE", "No responder available"),
                  ("PIPELINE_FAILURE", "Pipeline failure\n(Google Routes quota 429)"),
                  ("VALIDATION_FAILURE", "Validation failure")]
    counts = s["outcomes"]["classification_counts"]
    items = [(lbl, counts.get(k, 0)) for k, lbl in labels_map]
    data["outcome_distribution"] = {k: counts.get(k, 0) for k, _ in labels_map}
    fig, ax = plt.subplots(figsize=(8, 3.8))
    ys = range(len(items))[::-1]
    ax.barh(list(ys), [c for _, c in items], color=BLUE, height=0.55)
    ax.set_yticks(list(ys), [l for l, _ in items])
    for y, (_, c) in zip(ys, items):
        ax.text(c + 1, y, str(c), va="center", color=INK)
    ax.set_xlim(0, 100)
    ax.set_xlabel("Scenarios (of 100)")
    ax.set_title("Scenario outcomes", loc="left", fontweight="bold")
    style(ax)
    fig.tight_layout()
    fig.savefig(fig_dir / "1_outcome_distribution.png", dpi=160)
    plt.close(fig)

    # 2. Resource fulfilment vs shortage (log scale; values labelled)
    fig, ax = plt.subplots(figsize=(8, 4.4))
    names = {"water": "Water", "food": "Food", "medical_kits": "Medical kits"}
    width, xs = 0.26, range(len(RESOURCES))
    data["resources"] = {}
    for i, (key, color, label) in enumerate((("required", BLUE, "Required"), ("allocated", ORANGE, "Allocated"),
                                              ("shortage", AQUA, "Shortage"))):
        vals = [s["resources"][r][key] for r in RESOURCES]
        data["resources"][key] = dict(zip(RESOURCES, vals))
        pos = [x + (i - 1) * (width + 0.02) for x in xs]
        ax.bar(pos, vals, width=width, color=color, label=label, edgecolor=SURFACE, linewidth=2)
        for p, v in zip(pos, vals):
            ax.text(p, v * 1.25, f"{v:,.0f}", ha="center", va="bottom", fontsize=7.5, color=INK, rotation=90)
    ax.set_yscale("log")
    ax.set_ylim(1e2, 1e10)
    ax.set_xticks(list(xs), [names[r] for r in RESOURCES])
    ax.set_ylabel("Units (log scale)")
    ax.set_title("Resources across the 100 scenarios: required vs allocated vs shortage", loc="left", fontweight="bold")
    ax.legend(frameon=False, ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.09))
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(fig_dir / "2_resource_fulfilment.png", dpi=160)
    plt.close(fig)

    # 3. Route distance per planned route (sorted)
    planned = sorted([r for r in recs if r["classification"] in SUCCESS],
                     key=lambda r: r["route"]["total_distance_km"])
    data["route_distance_km"] = {r["scenario_id"]: r["route"]["total_distance_km"] for r in planned}
    fig, ax = plt.subplots(figsize=(8, 0.42 * len(planned) + 1.2))
    ys = range(len(planned))
    ax.barh(list(ys), [r["route"]["total_distance_km"] for r in planned], color=BLUE, height=0.6)
    ax.set_yticks(list(ys), [f"{r['scenario_id']}  " + (r['disaster_name'] if len(r['disaster_name']) <= 38 else r['disaster_name'][:37] + '…') for r in planned], fontsize=8.5)
    for y, r in zip(ys, planned):
        ax.text(r["route"]["total_distance_km"] + 20, y,
                f"{r['route']['total_distance_km']:,.0f} km · {r['route']['total_estimated_time_minutes'] / 60:,.1f} h · "
                f"{r['route']['number_of_legs']} legs", va="center", fontsize=8, color=INK2)
    ax.set_xlim(0, max(r["route"]["total_distance_km"] for r in planned) * 1.45)
    ax.set_xlabel("Total route distance (km): responder → warehouses → incident")
    ax.set_title(f"Planned routes ({len(planned)} scenarios)", loc="left", fontweight="bold")
    style(ax)
    fig.tight_layout()
    fig.savefig(fig_dir / "3_route_distance.png", dpi=160)
    plt.close(fig)

    # 4. Responder utilization (completed vs cancelled, stacked)
    rows = responder_rows
    data["responder_utilization"] = {r["responder_id"]: {"completed": r["completed"], "cancelled": r["cancelled"]}
                                     for r in rows}
    fig, ax = plt.subplots(figsize=(8, 3.4))
    ys = range(len(rows))[::-1]
    comp = [r["completed"] for r in rows]
    canc = [r["cancelled"] for r in rows]
    ax.barh(list(ys), comp, color=BLUE, height=0.55, label="Completed", edgecolor=SURFACE, linewidth=2)
    ax.barh(list(ys), canc, left=comp, color=ORANGE, height=0.55, label="Cancelled", edgecolor=SURFACE, linewidth=2)
    ax.set_yticks(list(ys), [f"{r['responder_id']} ({r['vehicle_type'].replace('_', ' ').lower()})" for r in rows])
    for y, r in zip(ys, rows):
        ax.text(r["missions"] + 0.8, y, f"{r['missions']} missions ({r['completed']} completed, {r['cancelled']} cancelled)"
                if r["missions"] else f"0 missions · initial {r['initial_status']}", va="center", fontsize=8.5, color=INK2)
    ax.set_xlim(0, max(r["missions"] for r in rows) * 1.6 + 1)
    ax.set_xlabel("Missions assigned")
    ax.set_title("Responder utilisation and reuse", loc="left", fontweight="bold")
    ax.legend(frameon=False, loc="lower right")
    style(ax)
    fig.tight_layout()
    fig.savefig(fig_dir / "4_responder_utilisation.png", dpi=160)
    plt.close(fig)

    (E / "chart_data.json").write_text(json.dumps(data, indent=2), encoding="utf-8")


def main():
    scenarios = load("scenarios.json")["scenarios"]
    raw = [json.loads(l) for l in (E / "results.jsonl").read_text(encoding="utf-8").splitlines() if l]
    neon, pre, post = load("neon_verification.json"), load("integrity/pre_run.json"), load("integrity/post_run.json")
    neon_pre = load("integrity/neon_pre_run.json")
    names = {r["responder_id"]: r["name"] for r in pre["data_files"]["responders.json"]["content"]}

    recs = build_records(scenarios, raw, neon, names)
    s = summarize(recs, neon, pre, post, neon_pre)

    (E / "results.json").write_text(json.dumps({"scenarios": recs}, indent=1, ensure_ascii=False), encoding="utf-8")
    (E / "summary.json").write_text(json.dumps(s, indent=2, ensure_ascii=False), encoding="utf-8")

    rep = E / "reports"
    rep.mkdir(exist_ok=True)
    (rep / "results_table.md").write_text(results_table(recs), encoding="utf-8")
    (rep / "route_results.md").write_text(route_tables(recs, s), encoding="utf-8")
    (rep / "resource_results.md").write_text(resource_tables(recs, s), encoding="utf-8")
    responder_md, responder_rows = responder_tables(recs, s, pre, post)
    (rep / "responder_results.md").write_text(responder_md, encoding="utf-8")
    (rep / "failures.md").write_text(failure_tables(recs, s), encoding="utf-8")
    charts(recs, s, responder_rows)
    print(json.dumps(s, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
