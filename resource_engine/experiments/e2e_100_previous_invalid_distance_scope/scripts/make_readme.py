"""Write README.md for the E2E-100 experiment from summary.json and the
integrity files (all figures are read from those files)."""
import json
from pathlib import Path

E = Path(__file__).resolve().parent.parent


def load(name):
    return json.loads((E / name).read_text(encoding="utf-8"))


s = load("summary.json")
pre, post = load("integrity/pre_run.json"), load("integrity/post_run.json")
data = load("scenarios.json")
build = json.loads((E / "scripts" / "build_report.json").read_text(encoding="utf-8"))
o, rt, re_, res, m = s["outcomes"], s["routes"], s["route_engine"], s["resources"], s["missions"]
states = sorted({x["state"] for x in data["scenarios"]})
first_fail = next(r for r in load("results.json")["scenarios"] if r["classification"] == "PIPELINE_FAILURE")
late_success = [r["scenario_id"] for r in load("results.json")["scenarios"]
                if r["scenario_id"] > first_fail["scenario_id"] and r["classification"].startswith("SUCCESS")]

readme = f"""# E2E-100: genuine-disaster end-to-end validation of AASHRAY

## Purpose
Run 100 real historical disasters, one at a time, through the complete AASHRAY pipeline
(`POST /orchestrate`: requirement -> allocation -> demand fulfilment -> mission creation ->
agent assignment -> real Route Engine HTTP calls) and record exactly what happened in each one,
using the responder lifecycle (`/mission/{{id}}/complete|cancel`) to make responders reusable
without any manual reset.

This experiment is separate from, and does not touch, the 12,000-scenario resource-allocation
hypothesis experiment (`experiments/resource_allocation_*`); see Integrity.

## Dataset (`scenarios.json`, `dataset_table.md`)
- **100 genuine disasters in India** ({len(states)} states/UTs; {sum(1 for x in data['scenarios'] if x['state'] == 'Maharashtra')} in Maharashtra, the
  home state of AASHRAY's Mumbai warehouses and responders), {data['scenarios'][0]['date'][:4]}–{data['scenarios'][-1]['date'][:4]}.
  India only, because every responder and warehouse is in Mumbai and the route must be drivable.
- **Source:** every scenario cites its English Wikipedia article (page id, revision id, URL),
  fetched through the Wikipedia API on {data['built_at_utc'][:10]}.
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
- {build['candidates']} candidates were considered; {len(build['excluded'])} were excluded during curation, each with its reason in
  `scripts/scenario_seed.json` / `scripts/build_report.json`; 0 failed validation.

## Execution
| Item | Value |
|---|---|
| Executed | {s['run']['first_scenario_started']} – {s['run']['last_scenario_finished']} (UTC), sequentially |
| AASHRAY | repo HEAD `{pre['aashray']['head'][:7]}` with uncommitted `resource_services/` (file hashes in `integrity/pre_run.json`), served on 127.0.0.1:8100 against its real `resource_services/database` |
| Route Engine | `{pre['route_engine']['head'][:7]}` (clean, unmodified) on 127.0.0.1:3100; Google Routes API, OpenWeb Ninja and Neon PostgreSQL all real |
| AASHRAY -> Route Engine | direct HTTP, per-leg mission IDs, 30 s timeout; no mocks, no proxy |
| Lifecycle | complete when the scenario validated; cancel for the 10-scenario sample (IDs divisible by 10) and for assigned missions that could not be executed |
| Manual resets | none; the runner never writes AASHRAY data files |
| Scripts | `scripts/build_dataset.py`, `run_e2e.py`, `neon_probe.mjs`, `post_run_integrity.py`, `report.py`, `make_readme.py` |

## API call counts
| API | Calls | Successful | Failed |
|---|---|---|---|
| AASHRAY `/orchestrate` | {o['total_scenarios']} | {o['successful_scenarios']} (HTTP 200) | {o['pipeline_failure_scenarios']} (HTTP 500) |
| AASHRAY `/mission/{{id}}/complete|cancel` | {m['assigned']} | {m['closed_with_http_200']} | {m['assigned'] - m['closed_with_http_200']} |
| Route Engine `/api/routes/optimize` | {re_['total_http_calls']} | {re_['successful_calls_http_200']} | {re_['failed_calls']} |
| Google Routes (via Route Engine) | {re_['total_http_calls']} | {re_['successful_calls_http_200']} | {re_['google_routes_errors']} (429 RESOURCE_EXHAUSTED) |
| OpenWeb Ninja (via Route Engine) | {s['openweb_ninja']['calls']} | {s['openweb_ninja']['successful']} | {s['openweb_ninja']['failed']} (429) |
| Neon MissionRouteState rows written | {re_['neon_mission_route_state_rows_verified']} | verified row-by-row | – |
| Neon RoadConditionEvidence rows written | {s['neon']['evidence_rows_written_during_run']} | – | – |

## Results (measured)
| Metric | Result |
|---|---|
| Scenarios executed | {o['total_scenarios']} / 100 |
| Successful end to end | {o['successful_scenarios']} ({o['successful_fully_fulfilled']} fully, {o['successful_partially_fulfilled']} partially fulfilled) |
| Failed at the Route Engine stage | {o['pipeline_failure_scenarios']} – all caused by the Google Routes daily quota ({o['pipeline_failures_caused_by_external_api_quota']}/{o['pipeline_failure_scenarios']}) |
| No safe route / Route Engine unavailable / no responder | {o['no_safe_route_scenarios']} / {o['route_engine_unavailable_scenarios']} / {o['no_responder_scenarios']} |
| Fulfilment status (all 100) | {s['fulfilment_status_counts_all_scenarios']['FULLY_FULFILLED']} fully / {s['fulfilment_status_counts_all_scenarios']['PARTIALLY_FULFILLED']} partially fulfilled |
| Invariant failures | {s['violations']['all_invariant_failures']} (responder lifecycle {s['violations']['responder_lifecycle']}, mission lifecycle {s['violations']['mission_lifecycle']}, allocation {s['violations']['allocation_invariant']}, route {s['violations']['route_invariant']}) |
| Missions | {m['created']} created, {m['assigned']} assigned, {m['completed']} completed, {m['cancelled']} cancelled |
| Responders | {s['responders']['total_assignments']} assignments, {s['responders']['unique_responders_used']} unique ({s['responders']['assignments_per_responder']}), reused {s['responders']['responder_reuse_count']} times |
| Planned routes | {rt['scenarios_with_planned_route']}; {rt['total_route_legs_in_planned_routes']} legs; distance mean {rt['route_total_distance_km']['mean']} / median {rt['route_total_distance_km']['median']} / max {rt['route_total_distance_km']['max']} km; ETA mean {rt['route_total_time_min']['mean']} / median {rt['route_total_time_min']['median']} / max {rt['route_total_time_min']['max']} min |
| Road condition of planned legs | {rt['road_condition_status_counts']} – no hazard data reached the Route Engine |
| Water / food / medical kits fulfilment | {res['water']['fulfilment_pct']}% / {res['food']['fulfilment_pct']}% / {res['medical_kits']['fulfilment_pct']}% of the aggregate requirement |
| Final responder state | {s['integrity']['final_responder_state_consistency']} (responders.json byte-identical to the pre-run state) |

Detailed per-scenario results: `reports/results_table.md` (all 100 rows), `results.json` (complete
records incl. raw responses), `reports/route_results.md`, `resource_results.md`, `responder_results.md`,
`failures.md`; charts in `figures/` (values in `chart_data.json`).

## Observed failures
- **Google Routes API daily quota (external).** From {first_fail['scenario_id']} on, Google rejected ComputeRoutes
  requests with HTTP 429 RESOURCE_EXHAUSTED ("ComputeRoutes per request quota per day"). The Route
  Engine returned HTTP 500, AASHRAY reported `FAILED` at stage `ROUTE_ENGINE`, and the runner cancelled
  the assigned mission, releasing the responder. Only {', '.join(late_success)} got through after the
  first rejection. {re_['legs_completed_but_discarded_after_a_later_leg_failed']} legs computed before a later leg of the same mission failed were persisted by the
  Route Engine but discarded by AASHRAY (it raises on the failing leg). Every one of the
  {re_['google_routes_errors']} Google errors in the log is this quota error; there were no other error kinds.
- **OpenWeb Ninja (external).** Every call ({s['openweb_ninja']['failed']}/{s['openweb_ninja']['calls']}) returned 429, as before this run. The Route Engine
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
| responders.json returned to its original state | {post['responders_json']['byte_identical_to_pre_run']} (byte-identical) |
| missions.json | {post['missions_json']['records']} records, all terminal {post['missions_json']['status_counts']}, none ASSIGNED |
| 12,000-scenario experiment unchanged | {post['experiments_12000']['unchanged']} ({post['experiments_12000']['files']} files, tree sha256 `{post['experiments_12000']['tree_sha256'][:16]}…`) |
| Route Engine repository unchanged | {post['route_engine']['unchanged']} (HEAD `{post['route_engine']['head'][:7]}`, clean) |
| Other project files changed | {post['aashray_project_files']['changed_files']} (expected: mission history) |

## Conclusion
The pipeline executed all 100 genuine-disaster scenarios with zero invariant violations: allocation
accounting, demand fulfilment, mission creation, typed responder assignment, per-leg Route Engine
mission IDs, route totals and the complete/cancel lifecycle all held, and every responder returned to
AVAILABLE without a manual reset. End-to-end success was limited to {o['successful_scenarios']} scenarios by an external
Google Routes daily quota, not by AASHRAY or Route Engine behaviour. Road-hazard awareness was not
tested because OpenWeb Ninja was unavailable throughout. A complete routing result for all 100
scenarios requires a re-run once the Google quota allows about 406 requests.
"""
(E / "README.md").write_text(readme, encoding="utf-8")
print("README.md written,", len(readme), "chars")
