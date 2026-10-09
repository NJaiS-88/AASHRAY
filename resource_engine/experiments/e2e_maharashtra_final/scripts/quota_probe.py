"""Exactly one Google Routes computeRoutes request (WH001 -> WH002) to check
the quota before any E2E execution. Appends the outcome to
logs/quota_probes.jsonl and exits 0 only on HTTP 200. The API key is read
from route_engine/.env and never printed or stored.

    python quota_probe.py
"""
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(r"C:\Users\Harsh\Desktop\AASHRAY Route Integration")
LOG = ROOT / "aashray dummy" / "experiments" / "e2e_maharashtra_final" / "logs" / "quota_probes.jsonl"


def main():
    env = {}
    for line in (ROOT / "route_engine" / ".env").read_text(encoding="utf-8").splitlines():
        m = re.match(r'\s*([A-Z_]+)\s*=\s*"?([^"\n]*)"?', line)
        if m:
            env[m.group(1)] = m.group(2).strip()
    body = {"origin": {"location": {"latLng": {"latitude": 19.0760, "longitude": 72.8777}}},
            "destination": {"location": {"latLng": {"latitude": 19.11, "longitude": 72.85}}},
            "travelMode": "DRIVE"}
    rec = {"probe": "WH001 -> WH002", "requested_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    try:
        r = httpx.post("https://routes.googleapis.com/directions/v2:computeRoutes", json=body, timeout=30,
                       headers={"X-Goog-Api-Key": env["GOOGLE_MAPS_API_KEY"], "X-Goog-FieldMask": "routes.distanceMeters"})
        rec["http_status"] = r.status_code
        j = r.json()
        if r.status_code == 200:
            rec["distance_km"] = round(j["routes"][0]["distanceMeters"] / 1000, 2)
        else:
            err = j.get("error") or {}
            rec["error_status"] = err.get("status")
            rec["error_message"] = err.get("message")
    except Exception as exc:  # transport error: recorded, not retried
        rec["http_status"] = None
        rec["error_message"] = f"{type(exc).__name__}: {exc}"
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")
    print(json.dumps(rec, indent=1))
    sys.exit(0 if rec["http_status"] == 200 else 1)


if __name__ == "__main__":
    main()
