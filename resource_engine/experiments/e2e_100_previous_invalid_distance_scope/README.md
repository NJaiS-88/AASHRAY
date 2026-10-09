> ## ⚠ FROZEN EXPLORATORY RUN — NOT THE FINAL E2E VALIDATION
>
> - This was an **exploratory run** (executed 2026-10-08).
> - It used an **incorrect geographic scope**: disasters across India, all served from AASHRAY's
>   Mumbai warehouses and responders.
> - Many routes were **unrealistically long** (mean 1,103 km, maximum 2,143 km), i.e. interstate
>   logistics, which is not the operational scenario AASHRAY is meant to validate.
> - It is **NOT** the final 100-scenario E2E validation, and its results **must not be used as the
>   final AASHRAY E2E results**. The final experiment is the Maharashtra-only local-response run in
>   `experiments/e2e_100_maharashtra/`.
> - The directory was renamed from `experiments/e2e_100/` on 2026-10-08; its contents are otherwise
>   preserved unchanged (paths inside its files still say `e2e_100`).

# E2E-100: genuine-disaster end-to-end validation of AASHRAY

## Purpose
Run 100 real historical disasters, one at a time, through the complete AASHRAY pipeline
(`POST /orchestrate`: requirement -> allocation -> demand fulfilment -> mission creation ->
agent assignment -> real Route Engine HTTP calls) and record exactly what happened in each one,
using the responder lifecycle (`/mission/{id}/complete|cancel`) to make responders reusable
without any manual reset.

This experiment is separate from, and does not touch, the 12,000-scenario resource-allocation
hypothesis experiment (`experiments/resource_allocation_*`); see Integrity.

## Dataset (`scenarios.json`, `dataset_table.md`)
- **100 genuine disasters in India** (24 states/UTs; 23 in Maharashtra, the
  home state of AASHRAY's Mumbai warehouses and responders), 1944–2025.
  India only, because every responder and warehouse is in Mumbai and the route must be drivable.
- **Source:** every scenario cites its English Wikipedia article (page id, revision id, URL),
  fetched through the Wikipedia API on 2026-10-08.
- **Coordinates:** the event article's Wikipedia coordinates when it has them and they lie within
  30 km of the affected locality; otherwise the affected locality's Wikipedia (or its Wikidata P625)
  coordinates. Event coordinates were rejected for 4 events (e.g. the 2004 tsunami epicentre off
  Sumatra). All 100 coordinates were checked to lie inside the stated state.
- **Affected population:** the sum of curated figures, each verified by script to occur in the
  source article next to a keyword of its class (affected / displaced / stranded / injured / deaths /
  on board). The token, keyword and text offset are stored per scenario. Where an article gives only
  a death toll, that toll is used and labelled `deaths_only` (a lower bound).
- **Locality population/density:** Wikidata P1082 / P2046 of the smallest of locality, district,
  state whose population is at least the affected population.
- **AASHRAY inputs** (severity, urgency, priority, duration, patient_present) are *not* historical
  facts. They are derived by documented rules in `scenarios.json -> rules`.
- 112 candidates were considered; 12 were excluded during curation, each with its reason in
  `scripts/scenario_seed.json` / `scripts/build_report.json`; 0 failed validation.

## Execution
| Item | Value |
|---|---|
| Executed | 2026-10-08T16:35:51.447Z – 2026-10-08T16:38:38.177Z (UTC), sequentially |
| AASHRAY | repo HEAD `8b90223` with uncommitted `resource_services/` (file hashes in `integrity/pre_run.json`), served on 127.0.0.1:8100 against its real `resource_services/database` |
| Route Engine | `11cc789` (clean, unmodified) on 127.0.0.1:3100; Google Routes API, OpenWeb Ninja and Neon PostgreSQL all real |
| AASHRAY -> Route Engine | direct HTTP, per-leg mission IDs, 30 s timeout; no mocks, no proxy |
| Lifecycle | complete when the scenario validated; cancel for the 10-scenario sample (IDs divisible by 10) and for assigned missions that could not be executed |
| Manual resets | none; the runner never writes AASHRAY data files |
| Scripts | `scripts/build_dataset.py`, `run_e2e.py`, `neon_probe.mjs`, `post_run_integrity.py`, `report.py`, `make_readme.py` |

## API call counts
| API | Calls | Successful | Failed |
|---|---|---|---|
| AASHRAY `/orchestrate` | 100 | 16 (HTTP 200) | 84 (HTTP 500) |
| AASHRAY `/mission/{id}/complete|cancel` | 100 | 100 | 0 |
| Route Engine `/api/routes/optimize` | 182 | 98 | 84 |
| Google Routes (via Route Engine) | 182 | 98 | 84 (429 RESOURCE_EXHAUSTED) |
| OpenWeb Ninja (via Route Engine) | 98 | 0 | 98 (429) |
| Neon MissionRouteState rows written | 98 | verified row-by-row | – |
| Neon RoadConditionEvidence rows written | 0 | – | – |

## Results (measured)
| Metric | Result |
|---|---|
| Scenarios executed | 100 / 100 |
| Successful end to end | 16 (7 fully, 9 partially fulfilled) |
| Failed at the Route Engine stage | 84 – all caused by the Google Routes daily quota (84/84) |
| No safe route / Route Engine unavailable / no responder | 0 / 0 / 0 |
| Fulfilment status (all 100) | 50 fully / 50 partially fulfilled |
| Invariant failures | 0 (responder lifecycle 0, mission lifecycle 0, allocation 0, route 0) |
| Missions | 100 created, 100 assigned, 15 completed, 85 cancelled |
| Responders | 100 assignments, 2 unique ({'R002': 62, 'R001': 38}), reused 98 times |
| Planned routes | 16; 70 legs; distance mean 1102.81 / median 1186.8 / max 2142.88 km; ETA mean 1259.67 / median 1341.9 / max 2355.42 min |
| Road condition of planned legs | {'UNKNOWN': 70} – no hazard data reached the Route Engine |
| Water / food / medical kits fulfilment | 0.0725% / 0.0958% / 0.3772% of the aggregate requirement |
| Final responder state | PASS (responders.json byte-identical to the pre-run state) |

Detailed per-scenario results: `reports/results_table.md` (all 100 rows), `results.json` (complete
records incl. raw responses), `reports/route_results.md`, `resource_results.md`, `responder_results.md`,
`failures.md`; charts in `figures/` (values in `chart_data.json`).

## Observed failures
- **Google Routes API daily quota (external).** From E2E-014 on, Google rejected ComputeRoutes
  requests with HTTP 429 RESOURCE_EXHAUSTED ("ComputeRoutes per request quota per day"). The Route
  Engine returned HTTP 500, AASHRAY reported `FAILED` at stage `ROUTE_ENGINE`, and the runner cancelled
  the assigned mission, releasing the responder. Only E2E-016, E2E-035, E2E-038 got through after the
  first rejection. 28 legs computed before a later leg of the same mission failed were persisted by the
  Route Engine but discarded by AASHRAY (it raises on the failing leg). Every one of the
  84 Google errors in the log is this quota error; there were no other error kinds.
- **OpenWeb Ninja (external).** Every call (98/98) returned 429, as before this run. The Route Engine
  treats this as "0 incidents": every planned leg is `UNKNOWN` road condition. No route in this run
  used real hazard data.
- **No AASHRAY or Route Engine defect was observed.** All invariants held in every scenario,
  including the 84 failed ones (stages 1–9 and the lifecycle checks ran and passed).

## Limitations
- 84 of 100 scenarios did not get a route because of the external quota, so the route statistics
  describe only 16 routes. The dataset and runner are unchanged and can be re-run after the quota
  resets or is raised (about 406 ComputeRoutes calls are needed).
- Road conditions were never assessed (OpenWeb Ninja 429): the disaster-aware part of routing was
  not exercised, and `NO_SAFE_ROUTE` could not arise from hazards.
- All 100 incidents are served from Mumbai, so most routes are long-distance (hundreds to
  2,000+ km) dispatches that a real responder network would not make.
- Warehouse stock is not decremented by allocation, so every scenario sees the same 2,750 water /
  1,900 food / 450 medical kits; 50 scenarios exhaust it (partial fulfilment is a stock artefact).
- Sequential closing means only R001 (rescue) and R002 (ambulance) are ever selected; R004 and
  R003 are never needed, and R005 starts BUSY with no mission record.
- Affected-population figures are curated from one source per event (Wikipedia), may mix
  event-level and locality-level counts, and `deaths_only` figures are lower bounds. Severity,
  urgency, priority and patient_present are rule-derived AASHRAY inputs.

## Integrity
| Check | Result |
|---|---|
| responders.json returned to its original state | True (byte-identical) |
| missions.json | 100 records, all terminal {'COMPLETED': 15, 'CANCELLED': 85}, none ASSIGNED |
| 12,000-scenario experiment unchanged | True (81 files, tree sha256 `377db01a3767715b…`) |
| Route Engine repository unchanged | True (HEAD `11cc789`, clean) |
| Other project files changed | ['resource_services/database/missions.json'] (expected: mission history) |

## Conclusion
The pipeline executed all 100 genuine-disaster scenarios with zero invariant violations: allocation
accounting, demand fulfilment, mission creation, typed responder assignment, per-leg Route Engine
mission IDs, route totals and the complete/cancel lifecycle all held, and every responder returned to
AVAILABLE without a manual reset. End-to-end success was limited to 16 scenarios by an external
Google Routes daily quota, not by AASHRAY or Route Engine behaviour. Road-hazard awareness was not
tested because OpenWeb Ninja was unavailable throughout. A complete routing result for all 100
scenarios requires a re-run once the Google quota allows about 406 requests.
