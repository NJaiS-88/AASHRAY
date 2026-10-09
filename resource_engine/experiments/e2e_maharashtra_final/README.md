# AASHRAY — Maharashtra-local final E2E validation

**Status (2026-10-09 07:06–07:07 UTC): EXECUTED — 11 of 11 scenarios. Overall result: PASS WITH LIMITATIONS.** Deliverables are in `results/`, `figures/` and `report/`. Earlier attempts were blocked by the Google daily quota (see *Execution attempts*).
The run is blocked by the Google Routes daily quota (see *Quota*). Nothing has
been sent to `/orchestrate`; no mission was created; `responders.json`,
`missions.json` and `warehouses.json` are untouched (see `integrity/pre_run.json`).

This folder is new. The previous 100-scenario run is preserved unchanged in
`experiments/e2e_100_previous_invalid_distance_scope/`. It was diagnostic only:
its routes were nationwide, up to 2,143 km, and the quota ran out mid-run.

## What was done

1. **System inspection.** The pipeline is in place: requirement → allocation →
   fulfilment → mission → agent assignment → Route Engine → lifecycle. Assignment
   writes AVAILABLE → BUSY (`agent_assignment_service.py`), and complete/cancel
   writes BUSY → AVAILABLE (`mission_lifecycle_service.py`). Test suite:
   **146 passed, 0 failed**.
2. **Integrity baseline** (`integrity/pre_run.json`):
   - The 12,000-scenario experiment tree matches its recorded hash
     (`377db01a…`, 81 files).
   - The previous run's tree is hashed.
   - The Route Engine is at HEAD `11cc789` with a clean status.
   - Data-file contents are recorded.
3. **Screening** of the existing dataset (`scripts/screen.py`; outputs in
   `screening/`):

   | Stage | Count |
   |---|---|
   | Original scenarios | 100 |
   | Maharashtra | 23 |
   | Outside Maharashtra (OUT_OF_SCOPE) | 77 |
   | Invalid / missing location | 0 |
   | Route > 150 km (UNREALISTIC_DISTANCE) | 10 |
   | Borderline, pending a real road measurement | 2 (E2E-067 Cyclone Nisarga / Alibag, E2E-070 Tariq Garden / Mahad) |
   | **Final qualifying** | **11** |

   Expected route distance of the 11:

   | Bucket | Scenarios |
   |---|---|
   | 0–10 km | 1 |
   | 10–25 km | 4 |
   | 25–50 km | 3 |
   | 50–100 km | 2 |
   | 100–150 km | 1 |
   | >150 km | 0 |

   Min 6.1, max 100.5, mean 37.4, median 30.9 km; 8 of 11 are ≤ 50 km. The
   execution dataset is `scenarios_final.json`. It holds the same scenario
   objects as the existing dataset. Only the incident id differs
   (`E2E100-INC-nnn` → `MHF-INC-nnn`), so this run's missions are distinct.

### How distances were screened

AASHRAY's warehouse chain does not depend on location. It always uses the
fixed order WH001 → WH005, and the number of warehouses is set by the affected
population. Each scenario's chain is therefore taken from the allocation the
pipeline actually produced for it in the previous run. Chain-leg distances are
the road distances measured in that run.

- **Lower bound** = measured chain + straight-line final leg. Road distance
  can never be shorter, so a lower bound above 150 km proves a scenario is out
  of scope.
- **Measured exclusions.** E2E-022 (Wai) has a 213 km final leg and E2E-041
  (Malin) a 224 km final leg, both from screening probes. E2E-002 (399 km) and
  E2E-009 (595 km) were measured in the previous run.
- **Borderline scenarios** have a lower bound ≤ 150 km but an estimate that
  isn't clearly below it. They are excluded until one real measurement of the
  final leg confirms ≤ 150 km.

## Quota

| Item | Value |
|---|---|
| Expected route legs (Σ warehouses + 1) | 28 |
| Route Engine HTTP calls | 28 |
| Google computeRoutes requests | 28 |
| OpenWeb Ninja requests | 28 (that API answers 429 to every request) |
| Borderline measurements | 2 |
| Worst case if both borderline scenarios qualify | 38 |

The binding limit is `Directions - ComputeRoutes per request quota per day`
(project 531208441346). Its value isn't exposed in the error. About 130
requests succeeded on 2026-10-08 before it was exhausted at 16:37 UTC.

Requests this session (2026-10-08 UTC):

| Time | Result |
|---|---|
| 19:51 | 200 |
| 19:56:28 | 200 (E2E-022) |
| 19:56:28 | 200 (E2E-041) |
| 19:56:28 | **429** RESOURCE_EXHAUSTED |
| 19:56:46 | 200 |
| 19:57:55 | **429** RESOURCE_EXHAUSTED (message: "…per request quota per day") |

Capacity is intermittent and cannot cover 28–38 requests. Executing now would
repeat the previous run's failure mode, so the run was stopped before any
`/orchestrate` call. **Scenarios that can safely run now: 0.** Per-day quotas
reset at midnight Pacific (07:00 UTC 2026-10-09, 12:30 IST). Alternatively,
raise the quota in Google Cloud Console: APIs & Services → Routes API → Quotas.

## Run plan (pre-registered; unchanged once started)

1. Send one quota probe request; continue only on HTTP 200.
2. Measure the two borderline final legs, 20 s apart:
   - E2E-067: WH005 → Alibag
   - E2E-070: WH001 → Mahad

   Re-run `scripts/screen.py`. A borderline scenario joins only if the measured
   chain plus the measured leg is ≤ 150 km.
3. Start the unmodified Route Engine (port 3100) and the current AASHRAY code
   (port 8100, real data root). Take a Neon snapshot.
4. Run `python scripts/run_e2e.py --data-root "<aashray dummy>" --scenarios scenarios_final.json --out results.jsonl --cancel-ids E2E-023 E2E-059 E2E-092 --route-engine-log logs/route_engine.log --aashray-log logs/aashray.log`.
   - Scenarios run sequentially, with no responder resets and no retries.
   - The run stops on the first Google quota error.
5. Run the Neon verification and the post-run integrity check, then build
   `results.json`, `results.csv`, `summary.json`, the figures and the PDF report.

Cancellation sample (fixed before execution): E2E-023 (3 warehouses),
E2E-059 and E2E-092. Every other mission that is routed and validated is
closed with `/complete`.

## Execution attempts

| Attempt | Time (UTC) | Step | Request | Result |
|---|---|---|---|---|
| 1 | 2026-10-08 19:51–19:58 | screening | 6 requests | 4 × HTTP 200, 2 × HTTP 429; stopped before execution (see *Quota*) |
| 2 | 2026-10-08 20:17:08 | quota probe (`scripts/quota_probe.py`, WH001 → WH002) | 1 | **HTTP 200**, 10.03 km |
| 2 | 2026-10-08 20:17:28 | borderline measurement, E2E-067 final leg WH005 → Alibag | 1 | **HTTP 429 RESOURCE_EXHAUSTED**: "Quota exceeded for quota metric 'Directions - ComputeRoutes per request quota' and limit 'Directions - ComputeRoutes per request quota per day' of service 'routes.googleapis.com' for consumer 'project_number:531208441346'." |
| 3 | 2026-10-08 20:23:29 | quota probe (`scripts/quota_probe.py`, WH001 → WH002) | 1 | **HTTP 429 RESOURCE_EXHAUSTED**: same per-day limit message; stopped at the probe, nothing else sent |

| 4 | 2026-10-09 04:20:01 | quota probe (`scripts/quota_probe.py`, WH001 → WH002) | 1 | **HTTP 429 RESOURCE_EXHAUSTED**: same per-day limit message; before the 07:00 UTC reset; nothing else sent |
Attempt 2 followed the protocol: one probe, and execution only if it returned 200.
The probe succeeded, but the very next request (20 s later) hit the same
per-day limit. Per the stop rule, the experiment ended there. Nothing was
retried. E2E-070 was not measured. No service was started. No `/orchestrate`
call was made. Successful Google requests before the failure in this attempt: 1.

A single probe returning 200 does not prove the daily quota is available
here. On 2026-10-08 the exhausted per-day limit answered 6 of 9 requests with
200, apparently at random. A reliable gate needs the daily reset to have
passed (midnight Pacific, 07:00 UTC) or a raised quota, as well as a
successful probe.

## Execution record (2026-10-09)

Executed command (sequential, real pipeline, no retries, no resets):

```bash
python scripts/run_e2e.py --aashray http://127.0.0.1:8100 --data-root "<aashray dummy>" --scenarios scenarios_final.json --out results/results.jsonl --route-engine-log logs/route_engine.log --aashray-log logs/aashray.log --cancel-ids E2E-023 E2E-059 E2E-092
```

Sequence:

1. Quota probe: 07:04:39 UTC, HTTP 200 (WH001 → WH002, 10.03 km).
2. Borderline final legs measured by road: E2E-067 WH005 → Alibag 105.39 km (total 76.73 + 105.39 = **182.12 km**, excluded); E2E-070 WH001 → Mahad 163.20 km (total 4.47 + 163.20 = **167.67 km**, excluded). Qualifying set stays at 11; `screen.py` re-run; `scenarios_final.json` regenerated deterministically.
3. Route Engine (unmodified, commit 11cc789) on port 3100 and AASHRAY on port 8100 against the real data root; health checks passed; Neon snapshot taken (129 MissionRouteState rows before).
4. `run_e2e.py`: 11 scenarios, all PASS, 0 invariant failures.
5. Lifecycle checks on closed missions (idempotency and cross-state rejection): 4/4 PASS; responders.json and missions.json unchanged by those calls.
6. Neon verification: 157 rows after (+28 = 28 legs). Post-run integrity: all checks pass.
7. Services stopped; ports 3100 and 8100 freed.

Outputs:

| File | Content |
|---|---|
| `results/results.jsonl` | raw per-scenario record from the runner (encoded polylines included) |
| `results/results.json` | structured record per scenario, all required fields |
| `results/results.csv` | one row per scenario (cross-checked against the JSON) |
| `results/summary.json` | aggregates (classification counts, distances, resources, responders, invariants, integrity) |
| `results/invariants.json` | builder invariant checks per scenario |
| `results/lifecycle_checks.json` | idempotency and cross-state lifecycle checks |
| `integrity/` | pre/post snapshots, Neon pre/post and verification |
| `figures/` | fig1–fig6 (measured data only) |
| `report/AASHRAY_Maharashtra_E2E_Validation_Report.pdf` | 6-page report |
| `logs/` | service logs, runner log, quota-probe log |

Results: executed 11, successful 11 (fully fulfilled 10, partially 1 — E2E-001), technical failures 0, distance violations 0. Route distance min 5.31 km, median 28.02 km, mean 33.82 km, max 99.58 km. Route time median 73.3 min. Route Engine legs 28, successful 28. OpenWeb Ninja 429 on all 28 requests (routing not disaster-aware). Missions completed 8, cancelled 3, ASSIGNED remaining 0. Responders: R002 × 10, R001 × 1; final state identical to initial.

This experiment validates AASHRAY under geographically local Maharashtra emergency-response scenarios.
