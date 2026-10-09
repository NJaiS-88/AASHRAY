"""Build results/results.json, results/results.csv and results/summary.json
from the raw run records. Every number is computed from the run's own data:

  results/results.jsonl            raw record per executed scenario (run_e2e.py)
  scenarios_final.json             executed dataset (incident inputs, source)
  screening/screening.json         screening decisions for all 100 candidates
  integrity/pre_run.json           baseline (responders, warehouses, missions)
  integrity/post_run.json          post-run integrity check
  integrity/neon_verification.json Route Engine database check
  results/lifecycle_checks.json    idempotency / cross-state checks

    python build_results.py
"""
import csv
import json
import statistics
from collections import Counter
from pathlib import Path

EXP = Path(__file__).resolve().parents[1]
RES = EXP / "results"
LIMIT_KM = 150.0
RESOURCES = ("water", "food", "medical_kits")
BUCKETS = (("0-10", 10), ("10-25", 25), ("25-50", 50), ("50-100", 100), ("100-150", 150))


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def bucket(km):
    if km is None:
        return None
    for name, hi in BUCKETS:
        if km <= hi:
            return name
    return ">150"


def pct(a, b):
    return round(100.0 * a / b, 2) if b else None


def main():
    final = load(EXP / "scenarios_final.json")["scenarios"]
    by_id = {s["scenario_id"]: s for s in final}
    records = [json.loads(l) for l in (RES / "results.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    pre = load(EXP / "integrity" / "pre_run.json")
    post = load(EXP / "integrity" / "post_run.json")
    neon = load(EXP / "integrity" / "neon_verification.json")
    neon_pre = load(EXP / "integrity" / "neon_pre_run.json")
    lifecycle = load(RES / "lifecycle_checks.json")
    screening = load(EXP / "screening" / "screening.json")
    prev_candidates = screening["candidates"]

    init_resp = {r["responder_id"]: r["status"] for r in pre["data_files"]["responders.json"]["content"]}
    final_resp_list = load(DB_RESPONDERS)  # canonical file, read after the run
    final_resp = {r["responder_id"]: r["status"] for r in final_resp_list}

    rows, invariant_log = [], []
    for rec in records:
        sid = rec["scenario_id"]
        s = by_id[sid]
        resp = rec["response"] or {}
        req = (resp.get("requirement") or {}).get("requirements") or {}
        alloc = resp.get("allocation") or {}
        ful = resp.get("demand_fulfilment") or {}
        mission = resp.get("mission") or {}
        assign = resp.get("agent_assignment") or {}
        route_bd = resp.get("route") or {}
        route = route_bd.get("route") or {}
        legs = route.get("legs") or []
        # One leg per Route Engine call (N warehouses -> N + 1 legs).
        life = rec.get("lifecycle") or {}
        after_close = (rec.get("responder_states") or {}).get("after_close") or {}
        before = (rec.get("responder_states") or {}).get("before") or {}
        mission_id = mission.get("mission_id")
        responder_id = assign.get("responder_id")

        checks = {}
        checks["required_ge_allocated"] = all(req[r] >= alloc["allocated_resources"][r] - 1e-6 for r in RESOURCES)
        checks["shortage_equals_required_minus_allocated"] = all(
            abs(req[r] - alloc["allocated_resources"][r] - alloc["remaining_shortage"][r]) <= 1e-6 for r in RESOURCES)
        wa_sum = {r: sum(w["supplies"][r] for w in alloc.get("warehouse_allocations", [])) for r in RESOURCES}
        checks["allocation_equals_sum_of_warehouse_allocations"] = all(
            abs(wa_sum[r] - alloc["allocated_resources"][r]) <= 1e-6 for r in RESOURCES)
        checks["mission_resources_equal_allocated"] = all(
            abs(mission.get("resources", {}).get(r, -1) - alloc["allocated_resources"][r]) <= 1e-6 for r in RESOURCES)
        if legs:
            checks["route_distance_equals_sum_of_legs"] = abs(
                route["distance_km"] - round(sum(l["distance_km"] for l in legs), 2)) <= 0.005
            checks["route_time_equals_sum_of_legs"] = abs(
                route["estimated_time_minutes"] - round(sum(l["estimated_time_minutes"] for l in legs), 2)) <= 0.005
            checks["leg_count_equals_warehouses_plus_one"] = len(legs) == len(alloc["warehouse_allocations"]) + 1
            checks["every_leg_has_parent_derived_route_engine_id"] = all(
                l.get("route_engine_mission_id") == f"{mission_id}-LEG-{l['leg_index']}" for l in legs)
            checks["route_within_150_km"] = route["distance_km"] <= LIMIT_KM
        checks["scenario_is_maharashtra"] = s["state"] == "Maharashtra"
        if responder_id:
            checks["assigned_responder_was_available_before"] = before.get(responder_id) == "AVAILABLE"
            checks["responder_available_after_close"] = after_close.get(responder_id) == "AVAILABLE"
            others = [k for k in before if k != responder_id]
            checks["no_other_responder_changed"] = all(after_close.get(k) == before[k] for k in others)
            checks["mission_closed_and_no_assigned_left"] = (
                life.get("operation") in ("complete", "cancel") and life.get("http_status") == 200
                and (rec.get("mission_record_after_close") or {}).get("status")
                == ("COMPLETED" if life["operation"] == "complete" else "CANCELLED"))
        failed_builder = [k for k, v in checks.items() if v is False]
        invariant_log.append({"scenario_id": sid, "checks": checks, "failed": failed_builder,
                              "runner_failed_invariants": rec["failed_invariants"]})

        validation_errors = list(rec["failed_invariants"]) + [f"builder check failed: {k}" for k in failed_builder]
        route_km = route.get("distance_km")
        route_status = route_bd.get("status")
        row = {
            "scenario_id": sid,
            "event_name": s["event_name"],
            "disaster_type": s["disaster_type"],
            "date": s["date"],
            "year": s["date"][:4],
            "state": s["state"],
            "district": s.get("district"),
            "location": s["locality"],
            "latitude": s["latitude"],
            "longitude": s["longitude"],
            "source": s["source"]["url"],
            "incident_id": rec["incident_id"],
            "affected_population": s["affected_population"],
            "affected_population_basis": s.get("affected_population_basis"),
            "severity": s["severity"],
            "urgency": s["urgency"],
            "priority": s["priority"],
            "patient_present": s["patient_present"],
            "execution_status": resp.get("status") or "NO_RESPONSE",
            "final_classification": rec["classification"],
            "resource_requirement": req,
            "allocation": {
                "allocation_id": alloc.get("allocation_id"),
                "required": alloc.get("required_resources"),
                "allocated": alloc.get("allocated_resources"),
                "shortage": alloc.get("remaining_shortage"),
                "allocation_status": alloc.get("allocation_status"),
                "warehouses_used": [w["warehouse_id"] for w in alloc.get("warehouse_allocations", [])],
                "warehouse_count": len(alloc.get("warehouse_allocations", [])),
                "final_priority_level": alloc.get("final_priority_level"),
            },
            "fulfilment": {"fulfilment_status": ful.get("fulfilment_status"),
                           "resource_status": ful.get("resource_status")},
            "mission": {"mission_id": mission_id, "creation_status": mission.get("status_at_creation"),
                        "final_state": (rec.get("mission_record_after_close") or {}).get("status"),
                        "required_responder_types": mission.get("required_responder_types"),
                        "resources": mission.get("resources"), "priority": mission.get("priority"),
                        "risk_score": mission.get("risk_score"),
                        "pickup_sequence": [p.get("warehouse_id") for p in mission.get("pickup_sequence", [])
                                            if p.get("type") == "WAREHOUSE"]},
            "agent_assignment": {"responder_id": responder_id, "responder_type": assign.get("responder_type"),
                                 "responder_location": assign.get("responder_location"),
                                 "distance_to_first_warehouse_km": assign.get("distance_to_warehouse_km"),
                                 "responder_status_before": before.get(responder_id) if responder_id else None,
                                 "responder_status_after_close": after_close.get(responder_id) if responder_id else None},
            "route": {"route_status": route_status, "route_data_status": route.get("status"),
                      "leg_count": len(legs), "distance_km": route_km,
                      "estimated_time_minutes": route.get("estimated_time_minutes"),
                      "per_leg": [{"leg_index": l["leg_index"],
                                   "source": f'{l["source_type"]}:{l["source_id"]}',
                                   "destination": f'{l["destination_type"]}:{l["destination_id"]}',
                                   "route_engine_mission_id": l.get("route_engine_mission_id"),
                                   "route_id": l.get("route_id"), "distance_km": l.get("distance_km"),
                                   "duration_minutes": l.get("estimated_time_minutes"),
                                   "road_condition_status": l.get("road_condition_status"),
                                   "matched_incidents": len(l.get("matched_incidents") or []),
                                   "route_score": l.get("score")} for l in legs],
                      "route_engine_mission_ids": [l.get("route_engine_mission_id") for l in legs],
                      "warehouse_sequence": [w["warehouse_id"] for w in alloc.get("warehouse_allocations", [])],
                      },
            "mission_lifecycle": {"operation": life.get("operation"), "reason": life.get("reason"),
                                  "http_status": life.get("http_status"),
                                  "released_responders": [r["responder_id"] for r in
                                                          (life.get("response") or {}).get("released_responders", [])],
                                  "mission_status_after": (rec.get("mission_record_after_close") or {}).get("status")},
            "responder_states": {"before": before, "after_close": after_close},
            "distance_bucket": bucket(route_km),
            "distance_scope": "DISTANCE_SCOPE_VIOLATION" if (route_km or 0) > LIMIT_KM else "WITHIN_150_KM",
            "failure_reason": "" if rec["classification"].startswith("SUCCESS") else (resp.get("error") or {}).get("message", ""),
            "validation_errors": validation_errors,
            "invariants_passed": not validation_errors,
            "timestamps": {"started_at": rec["started_at"], "finished_at": rec["finished_at"]},
            "orchestrate_seconds": rec.get("orchestrate_seconds"),
            "orchestrate_http_status": rec.get("orchestrate_http_status"),
            "orchestration_status": rec.get("orchestration_status"),
            "route_engine_log": {k: len(v) for k, v in rec["route_engine_log"].items()},
            "route_geometry": {"encoded_polylines": "kept in results/results.jsonl per leg; decoded coordinate arrays omitted by runner (re-derivable)"},
        }
        rows.append(row)

    # ----- aggregates -------------------------------------------------------
    executed = len(rows)
    route_rows = [r for r in rows if r["route"]["distance_km"] is not None]
    dists = [r["route"]["distance_km"] for r in route_rows]
    times = [r["route"]["estimated_time_minutes"] for r in route_rows]
    total_legs = sum(r["route"]["leg_count"] for r in rows)
    res_totals = {}
    for k in RESOURCES:
        req = sum(r["allocation"]["required"][k] for r in rows)
        alo = sum(r["allocation"]["allocated"][k] for r in rows)
        sho = sum(r["allocation"]["shortage"][k] for r in rows)
        res_totals[k] = {"required": round(req, 2), "allocated": round(alo, 2), "shortage": round(sho, 2),
                         "fulfilment_pct": pct(alo, req)}
    cls = Counter(r["final_classification"] for r in rows)
    responder_missions = Counter(r["agent_assignment"]["responder_id"] for r in rows if r["agent_assignment"]["responder_id"])
    lifecycle_violations = []
    for r in rows:
        if r["mission_lifecycle"]["operation"] and r["mission_lifecycle"]["http_status"] != 200:
            lifecycle_violations.append(r["scenario_id"])
        if r["mission_lifecycle"]["mission_status_after"] not in ("COMPLETED", "CANCELLED"):
            lifecycle_violations.append(r["scenario_id"])
    invariant_failures = [e for e in invariant_log if e["failed"] or e["runner_failed_invariants"]]

    route_engine_calls = total_legs
    rec_calls_success = sum(1 for r in rows for l in r["route"]["per_leg"] if l.get("distance_km") is not None)
    openweb_failures = sum(r["route_engine_log"]["openweb_failures"] for r in rows)
    google_errors = sum(r["route_engine_log"]["google_errors"] for r in rows)

    summary = {
        "experiment": "AASHRAY Maharashtra local final E2E validation",
        "dataset_source": "experiments/e2e_100_previous_invalid_distance_scope/scenarios.json (filtered; no new scenarios)",
        "total_candidate_scenarios": len(prev_candidates),
        "maharashtra_candidates": sum(1 for c in prev_candidates if c["state"] == "Maharashtra"),
        "qualifying_scenarios": len(final),
        "executed": executed,
        "successful": sum(1 for r in rows if r["final_classification"].startswith("SUCCESS")),
        "fully_fulfilled": cls.get("SUCCESS_FULLY_FULFILLED", 0),
        "partially_fulfilled": cls.get("SUCCESS_PARTIALLY_FULFILLED", 0),
        "no_safe_route": cls.get("NO_SAFE_ROUTE", 0),
        "no_responder": cls.get("NO_RESPONDER_AVAILABLE", 0),
        "route_engine_failures": cls.get("ROUTE_ENGINE_UNAVAILABLE", 0),
        "pipeline_failures": cls.get("PIPELINE_FAILURE", 0),
        "validation_failures": cls.get("VALIDATION_FAILURE", 0),
        "distance_violations": cls.get("DISTANCE_SCOPE_VIOLATION", 0),
        "classification_counts": dict(cls),
        "success_rate_pct": pct(sum(1 for r in rows if r["final_classification"].startswith("SUCCESS")), executed),
        "partial_fulfilment_rate_pct": pct(cls.get("SUCCESS_PARTIALLY_FULFILLED", 0), executed),
        "technical_failure_rate_pct": pct(cls.get("PIPELINE_FAILURE", 0) + cls.get("VALIDATION_FAILURE", 0), executed),
        "route_distance_km": {
            "min": min(dists), "median": round(statistics.median(dists), 2),
            "mean": round(statistics.mean(dists), 2), "max": max(dists),
            "p25": round(statistics.quantiles(dists, n=4, method="inclusive")[0], 2),
            "p75": round(statistics.quantiles(dists, n=4, method="inclusive")[2], 2),
        },
        "route_time_minutes": {
            "min": min(times), "median": round(statistics.median(times), 2),
            "mean": round(statistics.mean(times), 2), "max": max(times),
            "total": round(sum(times), 2),
        },
        "distance_buckets": {name: sum(1 for d in dists if bucket(d) == name) for name, _ in BUCKETS}
                            | {">150": sum(1 for d in dists if d > LIMIT_KM)},
        "total_route_legs": total_legs,
        "average_route_legs": round(total_legs / len(route_rows), 2),
        "route_engine_calls": {"total": route_engine_calls, "successful_legs": rec_calls_success,
                               "failed_legs": route_engine_calls - rec_calls_success,
                               "google_quota_errors": google_errors,
                               "openweb_ninja_failures": openweb_failures},
        "missions": {"created": sum(1 for r in rows if r["mission"]["mission_id"]),
                     "assigned": sum(1 for r in rows if r["agent_assignment"]["responder_id"]),
                     "completed": sum(1 for r in rows if r["mission"]["final_state"] == "COMPLETED"),
                     "cancelled": sum(1 for r in rows if r["mission"]["final_state"] == "CANCELLED"),
                     "assigned_remaining": len(post["missions_json"]["assigned_remaining"]),
                     "lifecycle_violations": sorted(set(lifecycle_violations))},
        "responders": {
            "assignments_per_responder": dict(sorted(responder_missions.items())),
            "responders_used": len(responder_missions),
            "reuse_missions": sum(v - 1 for v in responder_missions.values() if v > 1),
            "initial_state": init_resp,
            "final_state": final_resp,
            "initial_available": sum(1 for v in init_resp.values() if v == "AVAILABLE"),
            "initial_busy": sum(1 for v in init_resp.values() if v == "BUSY"),
            "final_available": sum(1 for v in final_resp.values() if v == "AVAILABLE"),
            "final_busy": sum(1 for v in final_resp.values() if v == "BUSY"),
            "state_identical_initial_vs_final": init_resp == final_resp,
        },
        "resource_totals": res_totals,
        "invariants": {"builder_checks_per_scenario": len(invariant_log),
                       "scenarios_with_invariant_failures": len(invariant_failures),
                       "failures": invariant_failures},
        "lifecycle_checks": {"checks": len(lifecycle["checks"]),
                             "passed": sum(1 for c in lifecycle["checks"] if c["result"] == "PASS"),
                             "responders_json_unchanged": lifecycle["responders_json_unchanged"],
                             "missions_json_unchanged": lifecycle["missions_json_unchanged"]},
        "database": {"mission_route_state_rows_before_run": neon_pre["mission_route_state"]["rows"],
                     "mission_route_state_rows_after_run": neon["totals"]["mission_route_state"]["rows"],
                     "new_rows": neon["totals"]["mission_route_state"]["rows"] - neon_pre["mission_route_state"]["rows"],
                     "legs_expected": total_legs,
                     "road_condition_evidence_rows_before": neon_pre["road_condition_evidence"]["rows"],
                     "road_condition_evidence_rows_after": neon["totals"]["road_condition_evidence"]["rows"]},
        "integrity": {"all_checks_pass": post["all_checks_pass"],
                      "warehouses_json_unchanged": post["warehouses_json_unchanged"],
                      "responders_json_byte_identical": post["responders_json_byte_identical"],
                      "experiments_12000_unchanged": post["experiments_12000_unchanged"],
                      "previous_e2e_run_unchanged": post["previous_e2e_run_unchanged"],
                      "route_engine_unchanged": post["route_engine_unchanged"],
                      "aashray_unexpected_changes": post["aashray_unexpected_changes"],
                      "new_mission_records": post["missions_json"]["new_records"],
                      "new_mission_statuses": post["missions_json"]["new_record_statuses"]},
        "overall_result": None,
    }
    # overall: PASS only if every executed scenario passed, nothing was violated, and integrity holds
    clean = (summary["invariants"]["scenarios_with_invariant_failures"] == 0
             and not summary["missions"]["lifecycle_violations"] and summary["missions"]["assigned_remaining"] == 0
             and summary["distance_violations"] == 0 and summary["integrity"]["all_checks_pass"]
             and summary["lifecycle_checks"]["passed"] == summary["lifecycle_checks"]["checks"])
    limitations = executed < summary["qualifying_scenarios"] or summary["route_engine_calls"]["openweb_ninja_failures"] > 0
    summary["overall_result"] = ("PASS WITH LIMITATIONS" if clean and limitations else "PASS" if clean else "FAIL")

    results = {
        "experiment": summary["experiment"],
        "command": ("python scripts/run_e2e.py --aashray http://127.0.0.1:8100 --data-root \"<aashray dummy>\" "
                    "--scenarios scenarios_final.json --out results/results.jsonl --route-engine-log logs/route_engine.log "
                    "--aashray-log logs/aashray.log --cancel-ids E2E-023 E2E-059 E2E-092"),
        "scenarios": rows,
    }
    (RES / "results.json").write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8")
    (RES / "summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False), encoding="utf-8")
    (RES / "invariants.json").write_text(json.dumps(invariant_log, indent=1, ensure_ascii=False), encoding="utf-8")

    cols = ["Scenario ID", "Disaster", "Type", "Location", "District", "Affected Population", "Severity", "Urgency",
            "Priority", "Water Required", "Water Allocated", "Water Shortage", "Food Required", "Food Allocated",
            "Food Shortage", "Medical Kits Required", "Medical Kits Allocated", "Medical Kits Shortage", "Fulfilment",
            "Mission ID", "Responder ID", "Responder Type", "Warehouses", "Route Legs", "Route Distance KM",
            "ETA Minutes", "Route Status", "Mission Final State", "Responder Final State", "Final Classification",
            "Failure Reason"]
    with (RES / "results.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in rows:
            a = r["allocation"]
            w.writerow([
                r["scenario_id"], r["event_name"], r["disaster_type"], r["location"], r["district"],
                r["affected_population"], r["severity"], r["urgency"], r["priority"],
                a["required"]["water"], a["allocated"]["water"], a["shortage"]["water"],
                a["required"]["food"], a["allocated"]["food"], a["shortage"]["food"],
                a["required"]["medical_kits"], a["allocated"]["medical_kits"], a["shortage"]["medical_kits"],
                r["fulfilment"]["fulfilment_status"], r["mission"]["mission_id"], r["agent_assignment"]["responder_id"],
                r["agent_assignment"]["responder_type"], " > ".join(r["route"]["warehouse_sequence"]),
                r["route"]["leg_count"], r["route"]["distance_km"], r["route"]["estimated_time_minutes"],
                r["route"]["route_status"], r["mission"]["final_state"], r["agent_assignment"]["responder_status_after_close"],
                r["final_classification"], r["failure_reason"]])
    print(json.dumps({k: summary[k] for k in ("executed", "successful", "partially_fulfilled", "fully_fulfilled",
                                              "route_distance_km", "distance_buckets", "overall_result")}, indent=1))


DB_RESPONDERS = EXP.parents[1] / "resource_services" / "database" / "responders.json"

if __name__ == "__main__":
    main()
