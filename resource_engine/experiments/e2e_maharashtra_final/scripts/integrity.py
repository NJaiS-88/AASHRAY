"""Integrity snapshot / verification for the Maharashtra final E2E run.

    python integrity.py pre  <out.json>
    python integrity.py post <pre.json> <results.jsonl> <out.json>

pre:  hashes of everything this run must not change (12,000-scenario
      experiment, previous E2E run, Route Engine repository, AASHRAY project
      files, warehouses/responders content) and the missions.json history.
post: re-hashes and compares; missions.json is the only AASHRAY file allowed
      to change, and only by gaining this run's missions in a terminal state.
"""
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(r"C:\Users\Harsh\Desktop\AASHRAY Route Integration")
AASHRAY = ROOT / "aashray dummy"
ROUTE_ENGINE = ROOT / "route_engine"
DB = AASHRAY / "resource_services" / "database"
THIS_EXP = "experiments/e2e_maharashtra_final/"
PREV_EXP = "experiments/e2e_100_previous_invalid_distance_scope/"
EXP_12000 = ("experiments/resource_allocation_development/", "experiments/resource_allocation_final/",
             "experiments/resource_allocation_milp/", "experiments/resource_allocation_pilot/")
EXP_12000_TREE_SHA256 = "377db01a3767715b22dc02cb01e872190e2a230ac64949504fdae9610fca0932"  # recorded 2026-10-08
SKIP = {".git", "node_modules", "__pycache__", ".pytest_cache"}
EXPECTED_CHANGES = {"resource_services/database/missions.json"}


def manifest(base: Path, exclude_prefix: str | None = None) -> dict:
    m = {}
    for dp, dn, fn in os.walk(base):
        dn[:] = [d for d in dn if d not in SKIP]
        for f in fn:
            p = Path(dp, f)
            rel = str(p.relative_to(base)).replace("\\", "/")
            if exclude_prefix and rel.startswith(exclude_prefix):
                continue
            m[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
    return m


def tree(m: dict) -> str:
    return hashlib.sha256("\n".join(f"{k} {v}" for k, v in sorted(m.items())).encode()).hexdigest()


def git(*a) -> str:
    return subprocess.run(["git", "-C", str(ROUTE_ENGINE), *a], capture_output=True, text=True).stdout.strip()


def snapshot() -> dict:
    aashray = manifest(AASHRAY, exclude_prefix=THIS_EXP)
    exp12 = {k: v for k, v in aashray.items() if k.startswith(EXP_12000)}
    prev = {k: v for k, v in aashray.items() if k.startswith(PREV_EXP)}
    route = manifest(ROUTE_ENGINE)
    return {
        "taken_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "experiments_12000": {"files": len(exp12), "tree_sha256": tree(exp12),
                              "matches_recorded_tree": tree(exp12) == EXP_12000_TREE_SHA256},
        "previous_e2e_run": {"files": len(prev), "tree_sha256": tree(prev)},
        "route_engine": {"head": git("rev-parse", "HEAD"), "status_porcelain": git("status", "--porcelain"),
                         "files": len(route), "tree_sha256": tree(route)},
        "aashray": {"files": len(aashray), "tree_sha256": tree(aashray), "manifest": aashray},
        "data_files": {name: {"sha256": hashlib.sha256((DB / name).read_bytes()).hexdigest(),
                              "content": json.loads((DB / name).read_text(encoding="utf-8"))}
                       for name in ("warehouses.json", "responders.json", "missions.json")},
    }


def main():
    mode = sys.argv[1]
    if mode == "pre":
        out = Path(sys.argv[2])
        snap = snapshot()
        out.write_text(json.dumps(snap, indent=1, ensure_ascii=False), encoding="utf-8")
        print(json.dumps({k: v for k, v in snap.items() if k not in ("aashray", "data_files")}, indent=1))
        return

    pre = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    recs = [json.loads(l) for l in Path(sys.argv[3]).read_text(encoding="utf-8").splitlines() if l.strip()]
    out = Path(sys.argv[4])
    now = snapshot()

    changed = sorted(k for k in set(now["aashray"]["manifest"]) | set(pre["aashray"]["manifest"])
                     if now["aashray"]["manifest"].get(k) != pre["aashray"]["manifest"].get(k))
    unexpected_changes = [k for k in changed if k not in EXPECTED_CHANGES]

    missions_now = now["data_files"]["missions.json"]["content"]
    by_id = {m["mission_id"]: m for m in missions_now}
    pre_missions = {m["mission_id"]: m for m in pre["data_files"]["missions.json"]["content"]}
    run_missions = [r["response"]["mission"]["mission_id"] for r in recs
                    if (r.get("response") or {}).get("agent_assignment")]
    history_preserved = all(by_id.get(k) == v for k, v in pre_missions.items())
    new_ids = [k for k in by_id if k not in pre_missions]

    post = {
        "verified_at_utc": now["taken_at_utc"],
        "experiments_12000_unchanged": now["experiments_12000"]["tree_sha256"] == pre["experiments_12000"]["tree_sha256"]
                                        and now["experiments_12000"]["matches_recorded_tree"],
        "experiments_12000": now["experiments_12000"],
        "previous_e2e_run_unchanged": now["previous_e2e_run"]["tree_sha256"] == pre["previous_e2e_run"]["tree_sha256"],
        "route_engine_unchanged": (now["route_engine"]["head"] == pre["route_engine"]["head"]
                                   and now["route_engine"]["status_porcelain"] == pre["route_engine"]["status_porcelain"]
                                   and now["route_engine"]["tree_sha256"] == pre["route_engine"]["tree_sha256"]),
        "route_engine": {k: now["route_engine"][k] for k in ("head", "status_porcelain", "files", "tree_sha256")},
        "warehouses_json_unchanged": now["data_files"]["warehouses.json"]["sha256"] == pre["data_files"]["warehouses.json"]["sha256"],
        "responders_json_byte_identical": now["data_files"]["responders.json"]["sha256"] == pre["data_files"]["responders.json"]["sha256"],
        "responders_json_content_identical": now["data_files"]["responders.json"]["content"] == pre["data_files"]["responders.json"]["content"],
        "missions_json": {
            "pre_run_records": len(pre_missions),
            "post_run_records": len(missions_now),
            "pre_run_history_preserved": history_preserved,
            "new_records": len(new_ids),
            "new_records_are_this_runs_missions": sorted(new_ids) == sorted(run_missions),
            "run_missions_missing": [m for m in run_missions if m not in by_id],
            "assigned_remaining": [m["mission_id"] for m in missions_now if m["status"] == "ASSIGNED"],
            "new_record_statuses": {s: sum(1 for k in new_ids if by_id[k]["status"] == s)
                                    for s in sorted({by_id[k]["status"] for k in new_ids})},
        },
        "aashray_files_changed": changed,
        "aashray_unexpected_changes": unexpected_changes,
    }
    post["all_checks_pass"] = all([
        post["experiments_12000_unchanged"], post["previous_e2e_run_unchanged"], post["route_engine_unchanged"],
        post["warehouses_json_unchanged"], post["responders_json_content_identical"],
        history_preserved, post["missions_json"]["new_records_are_this_runs_missions"],
        not post["missions_json"]["assigned_remaining"], not unexpected_changes,
    ])
    out.write_text(json.dumps(post, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(post, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
