"""Post-run integrity verification (Phase 9).

Compares the state after the run with integrity/pre_run.json:
  * responders.json must equal its pre-run content (byte-identical expected)
  * missions.json may contain history, but every record must be terminal
    (COMPLETED / CANCELLED), none ASSIGNED, and every run mission present
  * the 12,000-scenario experiment folders must be unchanged
  * the Route Engine repository must be unchanged (HEAD, status, file hashes)
  * no other AASHRAY project file may have changed
"""
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(r"C:\Users\Harsh\Desktop\AASHRAY Route Integration")
EXP = ROOT / "aashray dummy" / "experiments" / "e2e_100"
SKIP = {".git", "node_modules", "__pycache__", ".pytest_cache"}
EXPECTED_CHANGES = {"resource_services/database/missions.json"}


def manifest(base, exclude_prefix=None):
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


def tree(m):
    return hashlib.sha256("\n".join(f"{k} {v}" for k, v in sorted(m.items())).encode()).hexdigest()


def git(d, *a):
    return subprocess.run(["git", "-C", str(d), *a], capture_output=True, text=True).stdout.strip()


def main():
    pre = json.loads((EXP / "integrity" / "pre_run.json").read_text(encoding="utf-8"))
    recs = [json.loads(l) for l in (EXP / "results.jsonl").read_text(encoding="utf-8").splitlines() if l]
    db = ROOT / "aashray dummy" / "resource_services" / "database"

    responders_bytes = (db / "responders.json").read_bytes()
    responders_ok = hashlib.sha256(responders_bytes).hexdigest() == pre["data_files"]["responders.json"]["sha256"]
    responders_content_ok = json.loads(responders_bytes) == pre["data_files"]["responders.json"]["content"]

    mission_records = json.loads((db / "missions.json").read_text(encoding="utf-8"))
    by_id = {m["mission_id"]: m for m in mission_records}
    assigned = [m["mission_id"] for m in mission_records if m["status"] == "ASSIGNED"]
    pre_ids = {m["mission_id"] for m in pre["data_files"]["missions.json"]["content"]}
    run_missions = [r["response"]["mission"]["mission_id"] for r in recs
                    if (r.get("response") or {}).get("agent_assignment")]
    missing = [m for m in run_missions if m not in by_id]
    unexpected = [m for m in by_id if m not in pre_ids and m not in set(run_missions)]
    status_counts = {}
    for m in mission_records:
        status_counts[m["status"]] = status_counts.get(m["status"], 0) + 1

    aashray_now = manifest(ROOT / "aashray dummy", exclude_prefix="experiments/e2e_100/")
    exp_now = {k: v for k, v in aashray_now.items() if k.startswith("experiments/")}
    exp_pre = pre["experiments_12000_frozen"]["manifest"]
    route_now = manifest(ROOT / "route_engine")

    changed = sorted(k for k in set(aashray_now) | set(pre["aashray"]["manifest"])
                     if aashray_now.get(k) != pre["aashray"]["manifest"].get(k))

    post = {
        "verified_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "responders_json": {
            "byte_identical_to_pre_run": responders_ok,
            "content_identical_to_pre_run": responders_content_ok,
            "sha256": hashlib.sha256(responders_bytes).hexdigest(),
            "statuses": {r["responder_id"]: r["status"] for r in json.loads(responders_bytes)},
        },
        "missions_json": {
            "records": len(mission_records), "status_counts": status_counts,
            "assigned_remaining": assigned,
            "run_missions": len(run_missions), "run_missions_missing": missing,
            "records_not_from_this_run": unexpected,
            "all_terminal": not assigned,
        },
        "experiments_12000": {
            "unchanged": exp_now == exp_pre,
            "files": len(exp_now), "tree_sha256": tree(exp_now),
            "pre_tree_sha256": pre["experiments_12000_frozen"]["tree_sha256"],
        },
        "route_engine": {
            "head": git(ROOT / "route_engine", "rev-parse", "HEAD"),
            "status_porcelain": git(ROOT / "route_engine", "status", "--porcelain"),
            "tree_sha256": tree(route_now),
            "unchanged": (git(ROOT / "route_engine", "rev-parse", "HEAD") == pre["route_engine"]["head"]
                          and git(ROOT / "route_engine", "status", "--porcelain") == pre["route_engine"]["status_porcelain"]
                          and tree(route_now) == pre["route_engine"]["tree_sha256"]),
        },
        "aashray_project_files": {
            "changed_files": changed,
            "expected_changes": sorted(EXPECTED_CHANGES),
            "only_expected_changes": set(changed) <= EXPECTED_CHANGES,
        },
    }
    post["all_checks_pass"] = (responders_ok and not assigned and not missing and not unexpected
                               and post["experiments_12000"]["unchanged"] and post["route_engine"]["unchanged"]
                               and post["aashray_project_files"]["only_expected_changes"])
    (EXP / "integrity" / "post_run.json").write_text(json.dumps(post, indent=2), encoding="utf-8")
    print(json.dumps(post, indent=2))
    sys.exit(0 if post["all_checks_pass"] else 1)


if __name__ == "__main__":
    main()
