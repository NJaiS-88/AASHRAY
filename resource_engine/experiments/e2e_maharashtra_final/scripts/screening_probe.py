"""Road-distance measurements for screening borderline candidates.

    python screening_probe.py <out.json>

One Google Routes computeRoutes request per pair below (DRIVE, no retries).
This is a pre-execution screening measurement only; it is not part of the
E2E pipeline and writes nothing to the Route Engine or its database. The API
key is read from route_engine/.env and never printed or stored.
"""
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(r"C:\Users\Harsh\Desktop\AASHRAY Route Integration")
URL = "https://routes.googleapis.com/directions/v2:computeRoutes"

# (scenario_id, leg the pipeline would drive last, origin, destination).
# The origin is the last warehouse of the allocation the pipeline produced
# for that scenario in the previous run; the destination is the scenario's
# own coordinates from the existing dataset.
PAIRS = [
    ("E2E-022", "WH001 -> incident", (19.0760, 72.8777), (18.04672, 73.87548)),
    ("E2E-041", "WH001 -> incident", (19.0760, 72.8777), (19.16111, 73.68833)),
    ("E2E-064", "WH005 -> incident", (19.0500, 72.8200), (18.52489, 73.72288)),
    ("E2E-067", "WH005 -> incident", (19.0500, 72.8200), (18.64, 72.88)),
    ("E2E-070", "WH001 -> incident", (19.0760, 72.8777), (18.083, 73.417)),
]


PACING_SECONDS = 20  # spacing between requests; a 429 stops the probe (no retries)


def main():
    out_path = Path(sys.argv[1])
    only = set(sys.argv[2:])
    previous = json.loads(out_path.read_text(encoding="utf-8"))["measurements"] if out_path.exists() else []
    env = {}
    for line in (ROOT / "route_engine" / ".env").read_text(encoding="utf-8").splitlines():
        m = re.match(r'\s*([A-Z_]+)\s*=\s*"?([^"\n]*)"?', line)
        if m:
            env[m.group(1)] = m.group(2).strip()
    headers = {"X-Goog-Api-Key": env["GOOGLE_MAPS_API_KEY"],
               "X-Goog-FieldMask": "routes.distanceMeters,routes.duration"}
    out = list(previous)
    with httpx.Client(timeout=30) as http:
        for i, (sid, leg, (olat, olon), (dlat, dlon)) in enumerate(p for p in PAIRS if not only or p[0] in only):
            if i:
                time.sleep(PACING_SECONDS)
            body = {"origin": {"location": {"latLng": {"latitude": olat, "longitude": olon}}},
                    "destination": {"location": {"latLng": {"latitude": dlat, "longitude": dlon}}},
                    "travelMode": "DRIVE"}
            r = http.post(URL, json=body, headers=headers)
            rec = {"scenario_id": sid, "leg": leg, "origin": [olat, olon], "destination": [dlat, dlon],
                   "http_status": r.status_code, "measured_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
            j = r.json()
            if r.status_code == 200 and j.get("routes"):
                rec["road_km"] = round(j["routes"][0]["distanceMeters"] / 1000, 2)
                rec["duration_s"] = int(j["routes"][0]["duration"].rstrip("s"))
            else:
                err = j.get("error") or {}
                rec["error"] = err.get("status") or "NO_ROUTE"
                rec["error_message"] = err.get("message")
            out.append(rec)
            print(rec, flush=True)
            if r.status_code == 429:
                break  # quota exhausted: stop, no retries
    out_path.write_text(json.dumps({"method": "Google Routes computeRoutes, DRIVE, first route, one request per pair",
                                             "measurements": out}, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
