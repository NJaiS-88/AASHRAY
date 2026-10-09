"""Sequential E2E-100 runner.

For every scenario, in order, one at a time:
  1. POST /orchestrate with the scenario's incident (the real pipeline:
     requirement -> allocation -> fulfilment -> mission -> agent assignment
     -> Route Engine HTTP calls).
  2. Validate the per-scenario invariants against the response and against
     AASHRAY's own data files (read-only).
  3. finally: if a responder was assigned, close the mission through the
     lifecycle API (complete, or cancel for the cancellation sample and for
     missions that could not be executed) and validate the release.

The runner never writes responders.json or missions.json and never resets a
responder. Each result is appended to a JSONL file as soon as it is known.
"""
import argparse
import hashlib
import json
import re
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import httpx

RESOURCES = ("water", "food", "medical_kits")
TOL = 1e-6


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def read_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def responders(path: Path) -> dict:
    return {r["responder_id"]: r for r in read_json(path)}


def missions(path: Path) -> dict:
    return {m["mission_id"]: m for m in read_json(path)} if path.exists() else {}


def strip_coordinates(body):
    # Decoded coordinate arrays are replaced by their point counts; every
    # leg keeps its encoded polyline, from which they can be re-derived.
    if not isinstance(body, dict):
        return body
    body = json.loads(json.dumps(body))
    route = ((body.get("route") or {}).get("route")) or None
    if route:
        route["coordinates"] = {"omitted_points": len(route.get("coordinates") or [])}
        for leg in route.get("legs", []):
            leg["coordinates"] = {"omitted_points": len(leg.get("coordinates") or [])}
    return body


def log_slice(path: Path | None, start: int) -> str:
    if not path or not path.exists():
        return ""
    with path.open("rb") as f:
        f.seek(start)
        return f.read().decode("utf-8", errors="replace")


def log_size(path: Path | None) -> int:
    return path.stat().st_size if path and path.exists() else 0


class Checks:
    def __init__(self):
        self.items = []

    def add(self, number, name, passed, detail=None):
        # passed: True / False / None (not applicable)
        self.items.append({"invariant": number, "name": name,
                           "result": "PASS" if passed is True else "FAIL" if passed is False else "N/A",
                           "detail": detail})
        return passed

    def failed(self):
        return [c for c in self.items if c["result"] == "FAIL"]


def close_enough(a, b, tol=TOL):
    return abs(float(a) - float(b)) <= tol


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--aashray", default="http://127.0.0.1:8100")
    ap.add_argument("--data-root", required=True, help="AASHRAY working directory (holds resource_services/database)")
    ap.add_argument("--scenarios", required=True)
    ap.add_argument("--out", required=True, help="JSONL file for per-scenario results")
    ap.add_argument("--route-engine-log")
    ap.add_argument("--aashray-log")
    ap.add_argument("--only", nargs="*", help="scenario IDs to run (pilot)")
    ap.add_argument("--cancel-every", type=int, default=10)
    args = ap.parse_args()

    root = Path(args.data_root)
    db = root / "resource_services" / "database"
    responders_path, missions_path = db / "responders.json", db / "missions.json"
    warehouses = {w["warehouse_id"]: w for w in read_json(db / "warehouses.json")}
    rules = read_json(root / "resource_services" / "config" / "resource_rules.json")["resources"]
    re_log = Path(args.route_engine_log) if args.route_engine_log else None
    aa_log = Path(args.aashray_log) if args.aashray_log else None
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    dataset = read_json(Path(args.scenarios))["scenarios"]
    if args.only:
        dataset = [s for s in dataset if s["scenario_id"] in set(args.only)]

    http = httpx.Client(base_url=args.aashray, timeout=httpx.Timeout(900.0, connect=10.0))
    initial_responders = responders(responders_path)
    initial_hash = sha256(responders_path)
    last_post_hash = initial_hash
    consecutive_transport_errors = 0

    print(f"{utc_now()} start: {len(dataset)} scenario(s); responders.json sha256={initial_hash[:16]}", flush=True)

    for index, sc in enumerate(dataset):
        sid = sc["scenario_id"]
        checks = Checks()
        rec = {"scenario_id": sid, "incident_id": sc["incident_id"], "event_name": sc["event_name"],
               "disaster_type": sc["disaster_type"], "started_at": utc_now(), "request": sc["aashray_request"]}

        pre_hash = sha256(responders_path)
        pre_resp = responders(responders_path)
        pre_missions = missions(missions_path)

        # 19 / 20 are verified on every scenario's starting state.
        checks.add(19, "responders back in their initial state, so they can be reused",
                   pre_resp == initial_responders,
                   None if pre_resp == initial_responders else {k: v["status"] for k, v in pre_resp.items()})
        checks.add(20, "no modification of responders.json outside the API since the last scenario",
                   pre_hash == last_post_hash, {"expected": last_post_hash[:16], "found": pre_hash[:16]})

        re_off, aa_off = log_size(re_log), log_size(aa_log)
        body, http_status, transport_error = None, None, None
        t0 = time.perf_counter()
        try:
            response = http.post("/orchestrate", json=sc["aashray_request"])
            http_status = response.status_code
            try:
                body = response.json()
            except ValueError:
                body = {"_non_json_body": response.text[:2000]}
            consecutive_transport_errors = 0
        except httpx.HTTPError as exc:
            transport_error = f"{type(exc).__name__}: {exc}"
            consecutive_transport_errors += 1
        rec["orchestrate_seconds"] = round(time.perf_counter() - t0, 3)
        rec["orchestrate_http_status"] = http_status
        rec["transport_error"] = transport_error

        post_orch_resp = responders(responders_path)
        post_orch_missions = missions(missions_path)
        result = body if isinstance(body, dict) and "status" in body else None

        mission = (result or {}).get("mission") or None
        assignment = (result or {}).get("agent_assignment") or None
        allocation = (result or {}).get("allocation") or None
        requirement = (result or {}).get("requirement") or None
        fulfilment = (result or {}).get("demand_fulfilment") or None
        route_boundary = (result or {}).get("route") or None
        route = (route_boundary or {}).get("route") or None
        mission_id = mission["mission_id"] if mission else None
        responder_id = assignment["responder_id"] if assignment else None

        close = {"operation": None}
        try:
            # ---- 1-13: pipeline invariants --------------------------------
            checks.add(1, "incident accepted by AASHRAY",
                       bool(result) and http_status != 422 and result.get("incident_id") == sc["incident_id"],
                       {"http_status": http_status, "status": (result or {}).get("status")})

            affected = sc["affected_population"]
            if requirement:
                req = requirement["requirements"]
                ok = all(close_enough(req[r], affected * rules[r]["base_per_person"]) for r in RESOURCES)
                checks.add(2, "resource requirements generated (affected x per-person rule)", ok, req)
            else:
                checks.add(2, "resource requirements generated (affected x per-person rule)", False, "missing")

            checks.add(3, "allocation produced", bool(allocation and allocation.get("allocation_id")))

            if allocation:
                over, sums = [], {r: 0.0 for r in RESOURCES}
                for wa in allocation["warehouse_allocations"]:
                    inv = warehouses[wa["warehouse_id"]]["inventory"]
                    for r in RESOURCES:
                        sums[r] += wa["supplies"][r]
                        if wa["supplies"][r] > inv[r]["available"] + TOL:
                            over.append((wa["warehouse_id"], r, wa["supplies"][r], inv[r]["available"]))
                matches = all(close_enough(sums[r], allocation["allocated_resources"][r]) for r in RESOURCES)
                checks.add(4, "allocation never exceeds warehouse inventory", not over and matches,
                           {"over_inventory": over, "warehouse_sum_matches_allocated": matches})
                acct = {r: (allocation["required_resources"][r], allocation["allocated_resources"][r],
                            allocation["remaining_shortage"][r]) for r in RESOURCES}
                checks.add(5, "allocated + shortage = required for each resource",
                           all(close_enough(a + s, q) for q, a, s in acct.values()), acct)
            else:
                checks.add(4, "allocation never exceeds warehouse inventory", None)
                checks.add(5, "allocated + shortage = required for each resource", None)

            if fulfilment and allocation:
                rs = fulfilment["resource_status"]
                agree = all(close_enough(rs[r]["required"], allocation["required_resources"][r])
                            and close_enough(rs[r]["allocated"], allocation["allocated_resources"][r])
                            and close_enough(rs[r]["shortage"], allocation["remaining_shortage"][r])
                            and close_enough(fulfilment["total_shortage"][r], allocation["remaining_shortage"][r])
                            for r in RESOURCES)
                any_short = any(allocation["remaining_shortage"][r] > TOL for r in RESOURCES)
                status_ok = fulfilment["fulfilment_status"] == ("PARTIALLY_FULFILLED" if any_short else "FULLY_FULFILLED")
                checks.add(6, "demand fulfilment agrees with allocation", agree and status_ok,
                           {"fulfilment_status": fulfilment["fulfilment_status"],
                            "allocation_status": allocation["allocation_status"]})
            else:
                checks.add(6, "demand fulfilment agrees with allocation", None if not allocation else False)

            dispatchable = bool(allocation and allocation["warehouse_allocations"])
            if dispatchable:
                order_ok = bool(mission) and [p["warehouse_id"] for p in mission["pickup_sequence"]
                                              if p["type"] == "WAREHOUSE"] == \
                           [w["warehouse_id"] for w in allocation["warehouse_allocations"]]
                checks.add(7, "mission created (pickups in allocation order)", order_ok)
            else:
                checks.add(7, "mission created (pickups in allocation order)", None)

            if assignment:
                checks.add(8, "responder type matches required vehicle type",
                           assignment["responder_type"] in mission["required_responder_types"],
                           {"assigned": assignment["responder_type"],
                            "required": mission["required_responder_types"]})
                rec_m = post_orch_missions.get(mission_id)
                checks.add(9, "assigned responder changed AVAILABLE -> BUSY and is recorded for the mission",
                           pre_resp[responder_id]["status"] == "AVAILABLE"
                           and post_orch_resp[responder_id]["status"] == "BUSY"
                           and bool(rec_m) and rec_m["status"] == "ASSIGNED"
                           and [a["responder_id"] for a in rec_m["assignments"]] == [responder_id],
                           {"before": pre_resp[responder_id]["status"],
                            "after": post_orch_resp[responder_id]["status"],
                            "mission_record": rec_m and rec_m["status"]})
            else:
                checks.add(8, "responder type matches required vehicle type", None)
                checks.add(9, "assigned responder changed AVAILABLE -> BUSY", None)

            if dispatchable and assignment:
                msg = (route_boundary or {}).get("message") or ""
                called = bool(route_boundary) and (route_boundary["status"] in ("ROUTE_PLANNED", "NO_SAFE_ROUTE_FOUND")
                                                   or "leg" in msg.lower())
                failed_route_engine_stage = (result.get("error") or {}).get("stage") == "ROUTE_ENGINE"
                checks.add(10, "Route Engine called for the warehouse pickups", called or failed_route_engine_stage,
                           {"route_status": (route_boundary or {}).get("status"), "message": msg[:200]})
            else:
                checks.add(10, "Route Engine called for the warehouse pickups", None)

            if route and route.get("status") == "AVAILABLE":
                legs = route["legs"]
                ids_ok = all(leg.get("route_engine_mission_id") == f"{mission_id}-LEG-{leg['leg_index']}"
                             for leg in legs)
                checks.add(11, "every AVAILABLE leg has its route_engine_mission_id", ids_ok,
                           [leg.get("route_engine_mission_id") for leg in legs])
                expected = len(allocation["warehouse_allocations"]) + 1
                checks.add(12, "route legs = warehouses + 1", len(legs) == expected,
                           {"legs": len(legs), "expected": expected})
                d_sum = round(sum(l["distance_km"] for l in legs), 2)
                t_sum = round(sum(l["estimated_time_minutes"] for l in legs), 2)
                checks.add(13, "route distance/time equal the sum of the legs",
                           close_enough(route["distance_km"], d_sum, 0.005)
                           and close_enough(route["estimated_time_minutes"], t_sum, 0.005),
                           {"distance_km": route["distance_km"], "sum": d_sum,
                            "minutes": route["estimated_time_minutes"], "sum_minutes": t_sum})
            else:
                checks.add(11, "every AVAILABLE leg has its route_engine_mission_id", None)
                checks.add(12, "route legs = warehouses + 1", None)
                checks.add(13, "route distance/time equal the sum of the legs", None)

        except Exception:
            rec["validation_exception"] = traceback.format_exc()

        finally:
            # ---- close the mission (lifecycle) ------------------------------
            if assignment:
                route_ok = (result or {}).get("status") == "COMPLETED"
                pre_close_failures = [c for c in checks.failed() if c["invariant"] <= 13]
                if int(sid[-3:]) % args.cancel_every == 0:
                    op, reason = "cancel", "cancellation sample (every 10th scenario)"
                elif route_ok and not pre_close_failures and "validation_exception" not in rec:
                    op, reason = "complete", "scenario validated successfully"
                else:
                    op, reason = "cancel", ("mission could not be executed: orchestration status "
                                            f"{(result or {}).get('status')}" if not route_ok
                                            else "scenario failed validation")
                close = {"operation": op, "reason": reason}
                try:
                    cr = http.post(f"/mission/{mission_id}/{op}")
                    close["http_status"] = cr.status_code
                    close["response"] = cr.json()
                except httpx.HTTPError as exc:
                    close["transport_error"] = f"{type(exc).__name__}: {exc}"
            elif result is None:
                # Transport failure: the outcome is unknown. Close any mission
                # this scenario may have created (sequential run: any new
                # ASSIGNED record belongs to it).
                new_assigned = [m for mid, m in missions(missions_path).items()
                                if mid not in pre_missions and m["status"] == "ASSIGNED"]
                close = {"operation": "safety-cancel" if new_assigned else None,
                         "missions": [m["mission_id"] for m in new_assigned]}
                for m in new_assigned:
                    try:
                        cr = http.post(f"/mission/{m['mission_id']}/cancel")
                        close.setdefault("responses", []).append({"http_status": cr.status_code, "body": cr.json()})
                    except httpx.HTTPError as exc:
                        close.setdefault("responses", []).append({"transport_error": str(exc)})

        post_resp = responders(responders_path)
        post_missions = missions(missions_path)
        last_post_hash = sha256(responders_path)

        # ---- 14-18: lifecycle invariants ----------------------------------
        if assignment and close.get("http_status") == 200:
            expected_state = "COMPLETED" if close["operation"] == "complete" else "CANCELLED"
            released = [r["responder_id"] for r in close["response"].get("released_responders", [])]
            others_unchanged = all(post_resp[k] == post_orch_resp[k] for k in post_resp if k != responder_id)
            checks.add(14, "close released only the assigned responder",
                       released == [responder_id] and others_unchanged,
                       {"released": released, "others_unchanged": others_unchanged})
            checks.add(15, "released responder is AVAILABLE", post_resp[responder_id]["status"] == "AVAILABLE")
            checks.add(16, "responder location (and whole record) preserved",
                       post_resp[responder_id] == pre_resp[responder_id],
                       {"location_before": pre_resp[responder_id]["location"],
                        "location_after": post_resp[responder_id]["location"]})
            busy_before = [k for k, v in pre_resp.items() if v["status"] == "BUSY"]
            checks.add(17, "no unrelated BUSY responder released",
                       all(post_resp[k]["status"] == "BUSY" for k in busy_before), {"busy_before": busy_before})
            m_rec = post_missions.get(mission_id) or {}
            no_assigned = [mid for mid, m in post_missions.items() if m["status"] == "ASSIGNED"]
            checks.add(18, "mission closed and no ASSIGNED mission remains",
                       m_rec.get("status") == expected_state and not no_assigned
                       and [a["responder_id"] for a in m_rec.get("assignments", [])] == [responder_id],
                       {"mission_status": m_rec.get("status"), "assigned_missions": no_assigned})
        elif assignment:
            for n, name in ((14, "close released only the assigned responder"), (15, "released responder is AVAILABLE"),
                            (16, "responder location preserved"), (17, "no unrelated BUSY responder released"),
                            (18, "mission closed and no ASSIGNED mission remains")):
                checks.add(n, name, False, {"close": close})
        else:
            unchanged = post_resp == pre_resp and set(post_missions) == set(pre_missions)
            checks.add(14, "no responder or mission changed (nothing was assigned)", unchanged)
            for n in (15, 16, 17):
                checks.add(n, "not applicable (no assignment)", None)
            no_assigned = [mid for mid, m in post_missions.items() if m["status"] == "ASSIGNED"]
            checks.add(18, "no ASSIGNED mission remains", not no_assigned, {"assigned_missions": no_assigned})

        # ---- classification ------------------------------------------------
        status = (result or {}).get("status")
        failed = checks.failed()
        if result is None:
            classification = "PIPELINE_FAILURE"
        elif status == "COMPLETED":
            if failed or "validation_exception" in rec:
                classification = "VALIDATION_FAILURE"
            else:
                classification = ("SUCCESS_FULLY_FULFILLED" if result["fulfilment_status"] == "FULLY_FULFILLED"
                                  else "SUCCESS_PARTIALLY_FULFILLED")
        elif status == "NO_SAFE_ROUTE_FOUND":
            classification = "NO_SAFE_ROUTE"
        elif status == "ROUTE_ENGINE_NOT_CONNECTED":
            classification = "ROUTE_ENGINE_UNAVAILABLE"
        elif status == "NO_RESPONDER_AVAILABLE":
            classification = "NO_RESPONDER_AVAILABLE"
        elif status == "MISSION_NOT_DISPATCHABLE":
            classification = "MISSION_NOT_DISPATCHABLE"
        else:
            classification = "PIPELINE_FAILURE"
        legitimate = classification in ("SUCCESS_FULLY_FULFILLED", "SUCCESS_PARTIALLY_FULFILLED",
                                        "NO_SAFE_ROUTE", "MISSION_NOT_DISPATCHABLE")

        re_text, aa_text = log_slice(re_log, re_off), log_slice(aa_log, aa_off)
        rec.update({
            "finished_at": utc_now(),
            "orchestration_status": status,
            "classification": classification,
            "pass": legitimate and not failed and "validation_exception" not in rec,
            "failed_invariants": [f"{c['invariant']}: {c['name']}" for c in failed],
            "invariants": checks.items,
            "responder_states": {
                "before": {k: v["status"] for k, v in pre_resp.items()},
                "after_orchestrate": {k: v["status"] for k, v in post_orch_resp.items()},
                "after_close": {k: v["status"] for k, v in post_resp.items()},
            },
            "mission_record_after_close": post_missions.get(mission_id) if mission_id else None,
            "lifecycle": close,
            "route_engine_log": {
                "openweb_failures": re.findall(r"OpenWeb Ninja incidents fetch failed[^\n]*", re_text),
                "google_errors": re.findall(r"Error fetching routes from Google Routes API[^\n]*", re_text),
                "evidence_store_errors": re.findall(r"(?:Failed to store road condition evidence|Error saving road condition evidence)[^\n]*", re_text),
                "persist_errors": re.findall(r"Failed to persist mission route state[^\n]*", re_text),
                "other_lines": [l for l in re_text.splitlines()
                                if l.strip() and "OpenWeb Ninja incidents fetch failed" not in l
                                and "SECURITY WARNING" not in l and not l.startswith(("In the next major", "To prepare",
                                "- If you want", "See https://www.postgresql", "(Use `node --trace"))][:20],
            },
            "aashray_log_errors": [l for l in aa_text.splitlines()
                                   if "Traceback" in l or "ERROR" in l or "Exception" in l][:20],
            "response": strip_coordinates(body),
        })

        with out.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

        print(f"{utc_now()} {sid} {classification:28} http={http_status} status={status} "
              f"responder={responder_id} legs={len((route or {}).get('legs', []))} "
              f"km={(route or {}).get('distance_km')} close={close.get('operation')}:{close.get('http_status')} "
              f"{'PASS' if rec['pass'] else 'FAIL ' + ','.join(str(c['invariant']) for c in failed)} "
              f"({rec['orchestrate_seconds']}s)", flush=True)

        # ---- safety stops ---------------------------------------------------
        lifecycle_broken = post_resp != initial_responders or any(
            m["status"] == "ASSIGNED" for m in post_missions.values())
        if lifecycle_broken:
            print(f"{utc_now()} STOP: responder/mission state not back to its initial state after {sid}; "
                  "continuing would affect later scenarios.", flush=True)
            break
        if consecutive_transport_errors >= 3:
            print(f"{utc_now()} STOP: AASHRAY unreachable for 3 consecutive scenarios.", flush=True)
            break

    print(f"{utc_now()} end. responders.json sha256={sha256(responders_path)[:16]} "
          f"(initial {initial_hash[:16]})", flush=True)


if __name__ == "__main__":
    main()
