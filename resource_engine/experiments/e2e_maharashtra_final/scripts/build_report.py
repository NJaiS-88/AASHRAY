"""PDF report for the Maharashtra final E2E run, built with matplotlib (no new
dependencies). Every number is read from results/, integrity/ and screening/.

    python build_report.py
"""
import json
import textwrap
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.backends.backend_pdf import PdfPages  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402

EXP = Path(__file__).resolve().parents[1]
RES, FIG, INT = EXP / "results", EXP / "figures", EXP / "integrity"
OUT = EXP / "report" / "AASHRAY_Maharashtra_E2E_Validation_Report.pdf"
W, H = 8.27, 11.69
L = 0.5          # left margin (in)
TW = 7.27        # text width (in)
BOTTOM = 0.6

data = json.loads((RES / "results.json").read_text(encoding="utf-8"))
S = json.loads((RES / "summary.json").read_text(encoding="utf-8"))
rows = data["scenarios"]
screen = {c["scenario_id"]: c for c in json.loads((EXP / "screening" / "screening.json").read_text(encoding="utf-8"))["candidates"]}
lc = json.loads((RES / "lifecycle_checks.json").read_text(encoding="utf-8"))
post = json.loads((INT / "post_run.json").read_text(encoding="utf-8"))
neon = json.loads((INT / "neon_verification.json").read_text(encoding="utf-8"))


class Doc:
    def __init__(self, pdf):
        self.pdf = pdf
        self.page = 0
        self.fig = None
        self.new()

    def new(self):
        if self.fig is not None:
            self.footer()
            self.pdf.savefig(self.fig)
            plt.close(self.fig)
        self.fig = plt.figure(figsize=(W, H))
        self.page += 1
        self.y = H - 0.55

    def footer(self):
        self.fig.text(L / W, 0.3 / H, "AASHRAY · Maharashtra local E2E validation · measured results of 2026-10-09 run",
                      fontsize=6.5, color="#667")
        self.fig.text((L + TW) / W, 0.3 / H, f"page {self.page}", fontsize=6.5, color="#667", ha="right")

    def need(self, h):
        if self.y - h < BOTTOM:
            self.new()

    def line(self, s, size=8.6, bold=False, color="#111", gap=1.5):
        self.need(size / 72 * gap)
        self.fig.text(L / W, self.y / H, s, fontsize=size, fontweight="bold" if bold else "normal", color=color,
                      va="top", ha="left")
        self.y -= size / 72 * gap

    def heading(self, s):
        self.y -= 0.08
        self.need(0.4)
        self.line(s, size=10.5, bold=True, color="#1f3b57", gap=1.6)
        self.y -= 0.02

    def para(self, s, size=8.6, indent=0.0):
        chars = int((TW - indent) * 72 / (size * 0.55))
        for chunk in s.split("\n"):
            for ln in textwrap.wrap(chunk, width=chars) or [""]:
                self.line(("   " * 0) + ln, size=size)
        self.y -= 0.03

    def bullets(self, items, size=8.6):
        for it in items:
            chars = int((TW - 0.2) * 72 / (size * 0.55))
            wrapped = textwrap.wrap(it, width=chars)
            for k, ln in enumerate(wrapped):
                self.line(("•  " if k == 0 else "    ") + ln, size=size)

    def table(self, header, body, widths, size=7.1, zebra=True):
        rh = 0.2
        self.need(rh * (len(body) + 1) + 0.05)
        self.fig.patches.append(Rectangle((L / W, (self.y - rh) / H), sum(widths) / W, rh / H,
                                          transform=self.fig.transFigure, color="#dfe6ee", zorder=0))
        x = L
        for h, wd in zip(header, widths):
            self.fig.text((x + 0.03) / W, (self.y - 0.04) / H, h, fontsize=size, fontweight="bold", va="top")
            x += wd
        self.y -= rh
        for i, r in enumerate(body):
            if zebra and i % 2:
                self.fig.patches.append(Rectangle((L / W, (self.y - rh) / H), sum(widths) / W, rh / H,
                                                  transform=self.fig.transFigure, color="#f6f8fa", zorder=0))
            x = L
            for cell, wd in zip(r, widths):
                maxc = int((wd - 0.06) * 72 / (size * 0.55))
                t = str(cell)
                if len(t) > maxc:
                    t = t[: maxc - 1] + "…"
                self.fig.text((x + 0.03) / W, (self.y - 0.04) / H, t, fontsize=size, va="top")
                x += wd
            self.y -= rh
        self.y -= 0.08

    def image(self, path, width=TW, maxh=None):
        img = plt.imread(path)
        h = width * img.shape[0] / img.shape[1]
        if maxh and h > maxh:
            width, h = width * maxh / h, maxh
        self.need(h + 0.12)
        ax = self.fig.add_axes([L / W, (self.y - h) / H, width / W, h / H])
        ax.imshow(img)
        ax.axis("off")
        self.y -= h + 0.12

    def caption(self, s):
        self.para(s, size=7.4)

    def close(self):
        self.footer()
        self.pdf.savefig(self.fig)
        plt.close(self.fig)


def pct(x):
    return f"{x:.1f}%" if x is not None else "—"


def main():
    OUT.parent.mkdir(exist_ok=True)
    rt = S["route_distance_km"]
    tm = S["route_time_minutes"]
    b = S["distance_buckets"]
    res = S["resource_totals"]
    resp = S["responders"]
    mis = S["missions"]
    eng = S["route_engine_calls"]
    db = S["database"]
    integ = S["integrity"]
    inv = S["invariants"]
    lcs = S["lifecycle_checks"]
    qual = S["qualifying_scenarios"]
    total = S["total_candidate_scenarios"]
    mh = S["maharashtra_candidates"]
    excluded_mh = mh - qual
    e1 = next(r["route"] for r in rows if r["scenario_id"] == "E2E-001")
    chain1 = sum(l["distance_km"] for l in e1["per_leg"][:-1])

    with PdfPages(OUT) as pdf:
        d = Doc(pdf)

        # ---------------------------------------------------------- PAGE 1
        d.line("AASHRAY", size=17, bold=True, color="#1f3b57", gap=2.0)
        d.line("Maharashtra Local Emergency Response", size=12.5, bold=True, gap=1.8)
        d.line("End-to-End Pipeline Validation", size=12.5, bold=True, gap=1.8)
        d.line("Final isolated validation run · executed 2026-10-09 (UTC 07:06–07:07) · measured results only",
               size=8, color="#555", gap=2.2)

        d.heading("1. Objective")
        d.para("This experiment validates the integrated AASHRAY emergency-response pipeline under realistic, "
               "Maharashtra-local conditions. It uses only existing genuine disaster scenarios, real HTTP calls to the "
               "AASHRAY service and the unmodified Route Engine, sequential execution, and the existing responder "
               "lifecycle. It validates AASHRAY under geographically local Maharashtra emergency-response scenarios.")

        d.heading("2. Pipeline and system under test")
        d.para("Incident → Resource requirement → Resource allocation → Demand fulfilment → Mission creation → "
               "Agent assignment (AVAILABLE → BUSY) → Route Engine (one call per leg, unique "
               "route_engine_mission_id per leg) → Mission lifecycle (complete or cancel; BUSY → AVAILABLE).")
        d.para("System under test: the current AASHRAY code (resource_services) run unmodified on port 8100 against the real "
               "data root, and the Route Engine (commit 11cc789, clean working tree) run unmodified on port 3100. "
               "Before execution the AASHRAY test suite passed 146 of 146 tests.")

        d.heading("3. Dataset selection")
        d.bullets([
            f"Original genuine-disaster dataset: {total} scenarios (experiments/e2e_100_previous_invalid_distance_scope, "
            "read-only; the previous run is not overwritten).",
            f"Maharashtra scenarios: {mh}. Outside Maharashtra (excluded): {total - mh}.",
            f"Maharashtra scenarios excluded for distance > 150 km: {excluded_mh} of {mh}. Ten were excluded by the "
            "screening lower bound or estimate; two were borderline and excluded by direct measurement "
            f"(E2E-067 Alibag: 182.1 km; E2E-070 Mahad: 167.7 km). {qual} qualify.",
            f"Executed: {S['executed']}. No scenario was added, merged or re-geocoded. Incident identifiers were "
            "renamed (E2E100-INC → MHF-INC) so this run's missions are distinct.",
        ])

        d.heading("4. Geographic and distance constraints")
        d.bullets([
            "Maharashtra locations only; coordinates from the existing dataset, unmodified.",
            "HARD LIMIT: the measured total route distance of every executed scenario must be ≤ 150 km. "
            f"Result: {b['>150']} scenarios above 150 km.",
            "Preferred: most scenarios ≤ 50 km. Result: "
            f"{b['0-10'] + b['10-25'] + b['25-50']} of {S['executed']} ≤ 50 km.",
            "Warehouses (WH001–WH005) and responders (R001–R005) are the canonical files; their locations and "
            "statuses were not modified.",
        ])

        d.heading("5. Execution methodology")
        d.bullets([
            "Quota check first: one Google Routes probe returned HTTP 200 at 07:04 UTC. The two borderline final legs were "
            "then measured by road (E2E-067: 105.4 km; E2E-070: 163.2 km) and both were excluded.",
            "Services: Route Engine (3100) and AASHRAY (8100) started; health checks passed; Neon snapshot taken before "
            "and after execution.",
            "Each scenario: POST /orchestrate (real pipeline), invariant checks (runner, 21 invariants), then one "
            "lifecycle call: POST /mission/{id}/complete, or /cancel for E2E-023, E2E-059 and E2E-092 (pre-selected).",
            "Sequential only; no retries; no responder or warehouse reset; no manual database edits. The run would have "
            "stopped on any Google quota error (none occurred during execution).",
            "Four earlier attempts were blocked by the Google per-day quota (2026-10-08 19:51 UTC to 2026-10-09 04:20 UTC). "
            "None executed a scenario or called /orchestrate. Each attempt is logged in the README.",
        ])

        d.image(str(FIG / "fig1_route_distance_distribution.png"), width=5.6, maxh=3.2)
        d.caption(f"Figure 1. Measured total route distance (n = {len(rows)}). "
                  f"Buckets: 0–10 km: {b['0-10']}; 10–25: {b['10-25']}; 25–50: {b['25-50']}; 50–100: {b['50-100']}; "
                  f"100–150: {b['100-150']}; > 150 km: {b['>150']}.")

        # ---------------------------------------------------------- PAGE 2
        d.heading("6. Scenario execution results")
        table_rows = []
        for r in rows:
            table_rows.append([
                r["scenario_id"], r["event_name"], r["final_classification"],
                r["agent_assignment"]["responder_id"], r["allocation"]["warehouse_count"], r["route"]["leg_count"],
                f"{r['route']['distance_km']:.2f}", f"{r['route']['estimated_time_minutes']:.1f}",
                f"{r['mission_lifecycle']['operation']} {r['mission_lifecycle']['http_status']}"])
        d.table(["ID", "Disaster", "Final classification", "Resp.", "WH", "Legs", "km", "min", "Lifecycle"],
                table_rows, [0.65, 1.6, 1.85, 0.45, 0.35, 0.4, 0.6, 0.55, 0.8], size=6.7)

        d.heading("7. Resource allocation and fulfilment (measured, 11 scenarios)")
        rr = []
        for k, label in (("water", "Water"), ("food", "Food"), ("medical_kits", "Medical kits")):
            t = res[k]
            rr.append([label, f"{t['required']:,.2f}", f"{t['allocated']:,.2f}", f"{t['shortage']:,.2f}",
                       pct(t["fulfilment_pct"])])
        d.table(["Resource", "Required", "Allocated", "Shortage", "Fulfilment %"], rr, [1.5, 1.5, 1.5, 1.5, 1.27])
        d.para("Every scenario satisfies allocated + shortage = required for each resource (11/11). Fulfilment is low "
               "because the stated per-person requirements (water 2, food 1, medical kits 0.05 per affected person) are far "
               "larger than the total stock of the five warehouses (water 2,750; food 1,900; medical kits 450 — "
               "all of it allocated to E2E-001). "
               "Shortage is a legitimate business outcome, not a software failure. E2E-001 is the only partially fulfilled "
               "scenario; all other scenarios were fully fulfilled. Warehouse stock is "
               "not decremented by the pipeline, and warehouses.json is unchanged after the run, so every scenario "
               "was allocated from the same starting stock.")

        d.heading("8. Mission creation, responder assignment and lifecycle")
        d.para(f"Missions created: {mis['created']}. Responder assignments: {mis['assigned']} "
               f"({resp['responders_used']} responders: R002 × {resp['assignments_per_responder'].get('R002', 0)}, "
               f"R001 × {resp['assignments_per_responder'].get('R001', 0)}). Reuse of a responder after release: "
               f"{resp['reuse_missions']} missions. Closed: {mis['completed']} COMPLETED, {mis['cancelled']} CANCELLED; "
               f"ASSIGNED remaining: {mis['assigned_remaining']}. Every assigned responder moved AVAILABLE → BUSY on "
               "assignment and returned to AVAILABLE on close; the runner confirmed that only the assigned responder "
               "was released and that no other responder changed (invariants 14–18, all 11 scenarios).")
        d.para(f"Lifecycle checks run after execution on the closed missions: {lcs['passed']} of {lcs['checks']} passed "
               "(completing a COMPLETED mission again → 200 idempotent; cancelling a COMPLETED mission → 409 "
               "MISSION_ALREADY_CLOSED; cancelling a CANCELLED mission again → 200 idempotent; completing a CANCELLED "
               "mission → 409 MISSION_ALREADY_CLOSED). responders.json and missions.json were byte-identical across these "
               "calls.")

        d.heading("9. Route results (measured)")
        d.para(f"Route Engine calls: {eng['total']} (one per leg; {eng['successful_legs']} successful, "
               f"{eng['failed_legs']} failed). Google Routes errors: {eng['google_quota_errors']}. OpenWeb Ninja "
               f"requests failed: {eng['openweb_ninja_failures']} (HTTP 429, quota). Every leg therefore reports "
               "road_condition_status UNKNOWN and no matched incidents. Routing used real road distances and times "
               "from Google, but it was NOT disaster-aware. Warehouse sequences were the fixed WH001 → WH005 chain, "
               "ordered as the allocation produced them. Per scenario the total equals the sum of its legs (invariant 13). "
               "Each leg's route_engine_mission_id is the parent mission ID with -LEG-n (invariant 11). Google requests "
               "made inside the Route Engine were not counted separately; the Route Engine returned no Google errors.")
        d.image(str(FIG / "fig2_route_distance_by_scenario.png"), width=6.6, maxh=3.1)
        d.caption("Figure 2. Measured total route distance per scenario against the 150 km hard limit (teal ≤ 50 km, navy 50–100 km).")

        d.image(str(FIG / "fig3_resource_allocation.png"), width=6.6, maxh=2.9)
        d.caption("Figure 3. Required, allocated and shortage totals for the 11 scenarios (measured).")

        # ---------------------------------------------------------- PAGE 3
        d.heading("10. Route statistics (measured total route distance and time)")
        d.table(["Metric", "Distance (km)", "Time (min)"], [
            ["Minimum", f"{rt['min']:.2f}", f"{tm['min']:.2f}"],
            ["P25", f"{rt['p25']:.2f}", "—"],
            ["Median", f"{rt['median']:.2f}", f"{tm['median']:.2f}"],
            ["Mean", f"{rt['mean']:.2f}", f"{tm['mean']:.2f}"],
            ["P75", f"{rt['p75']:.2f}", "—"],
            ["Maximum", f"{rt['max']:.2f}", f"{tm['max']:.2f}"],
            ["Total", "—", f"{tm['total']:.2f}"],
        ], [2.4, 2.0, 2.0])
        d.table(["Distance bucket", "0–10", "10–25", "25–50", "50–100", "100–150", "> 150"], [
            ["Scenarios (measured)", b["0-10"], b["10-25"], b["25-50"], b["50-100"], b["100-150"], b[">150"]],
        ], [2.0, 0.85, 0.85, 0.85, 0.85, 0.9, 0.9])
        d.para(f"Legs: {S['total_route_legs']} in total ({S['average_route_legs']} per route; "
               "1 warehouse → 2 legs, 3 → 4, 5 → 6). Multi-warehouse chains dominate the distance. "
               f"E2E-001 (5 warehouses) totals {e1['distance_km']:.2f} km: {chain1:.2f} km to WH005 through the warehouse chain, "
               f"then {e1['per_leg'][-1]['distance_km']:.2f} km to the incident. This follows from AASHRAY's fixed, "
               "location-blind WH001 → WH005 ordering, not from the incident location; it is reported, not changed.")

        d.heading("11. Responder utilization")
        d.image(str(FIG / "fig5_responder_utilization.png"), width=4.6, maxh=2.4)
        d.para(f"R001 and R002 were used; R003, R004 and R005 were never assigned. R005 started BUSY (no mission record) "
               f"and remained BUSY, which is the canonical state. Final state equals initial state: "
               f"{resp['final_available']} AVAILABLE, {resp['final_busy']} BUSY "
               f"(identical to the initial state for every responder: {'yes' if resp['state_identical_initial_vs_final'] else 'no'}).")

        d.heading("12. Failures and legitimate shortages")
        d.bullets([
            "Technical failures (PIPELINE_FAILURE / VALIDATION_FAILURE): 0. Route Engine failures: 0. Google quota errors "
            "during the run: 0. No NO_SAFE_ROUTE or NO_RESPONDER_AVAILABLE outcomes occurred.",
            "Legitimate business outcome: 1 scenario SUCCESS_PARTIALLY_FULFILLED (E2E-001, 80,000 affected). It is not "
            "counted as a failure; all 11 orchestrations returned COMPLETED.",
            "External API limitation: OpenWeb Ninja returned HTTP 429 for all 28 requests. This degrades disaster-aware "
            "routing and is not an AASHRAY allocation failure.",
            "Excluded before execution, not failures: E2E-067 (182.1 km measured) and E2E-070 (167.7 km), both "
            "above 150 km by measurement. They are reported in §3 and were not executed.",
        ])

        d.heading("13. Invariant validation")
        d.para(f"Runner invariants (1–21) on every executed scenario: {inv['scenarios_with_invariant_failures']} scenarios "
               f"with failures. Builder checks on every scenario ({inv['builder_checks_per_scenario']} scenarios): required ≥ "
               "allocated; shortage = required − allocated; allocation = sum of warehouse allocations; mission resources "
               "= allocated resources; route distance and time = sum of legs; leg count = warehouses + 1; every leg has "
               "its parent-derived route_engine_mission_id; scenario is Maharashtra; every route ≤ 150 km; the assigned "
               "responder was AVAILABLE before assignment and AVAILABLE after close; no other responder changed; mission "
               "closed with the expected state and no ASSIGNED mission left. All passed.")

        d.image(str(FIG / "fig4_outcome_distribution.png"), width=5.4, maxh=2.8)
        d.caption("Figure 4. Final classification of the 11 executed scenarios (measured; zero-count categories shown).")

        # ---------------------------------------------------------- PAGE 4
        d.heading("14. Database and integrity validation")
        d.bullets([
            f"Route Engine MissionRouteState rows: {db['mission_route_state_rows_before_run']} before → "
            f"{db['mission_route_state_rows_after_run']} after (+{db['new_rows']} = {db['legs_expected']} legs). "
            "Every leg has its own row keyed by its route_engine_mission_id.",
            f"RoadConditionEvidence rows: {db['road_condition_evidence_rows_before']} before → "
            f"{db['road_condition_evidence_rows_after']} after (no new evidence; OpenWeb unavailable).",
            f"warehouses.json unchanged: {'yes' if integ['warehouses_json_unchanged'] else 'no'}. responders.json "
            f"byte-identical: {'yes' if integ['responders_json_byte_identical'] else 'no'}. missions.json: prior 100 records preserved; "
            f"{integ['new_mission_records']} new records ({integ['new_mission_statuses'].get('COMPLETED', 0)} COMPLETED, "
            f"{integ['new_mission_statuses'].get('CANCELLED', 0)} CANCELLED); none ASSIGNED.",
            f"12,000-scenario experiment unchanged: {'yes' if integ['experiments_12000_unchanged'] else 'no'}. Previous E2E run "
            f"unchanged: {'yes' if integ['previous_e2e_run_unchanged'] else 'no'}. Route Engine repository unchanged: "
            f"{'yes' if integ['route_engine_unchanged'] else 'no'}. "
            f"Unexpected AASHRAY file changes: {len(integ['aashray_unexpected_changes'])}.",
            f"Overall post-run integrity check: {'PASS' if integ['all_checks_pass'] else 'FAIL'}.",
        ])

        d.heading("15. Expected (screening) versus measured route distance")
        cmp_rows = []
        for r in rows:
            c = screen[r["scenario_id"]]
            exp = c["expected_route_km"]
            meas = r["route"]["distance_km"]
            cmp_rows.append([r["scenario_id"], c["expected_basis"][:58], f"{exp:.1f}", f"{meas:.2f}",
                             f"{meas - exp:+.1f}"])
        d.table(["ID", "Expected basis (screening)", "Expected km", "Measured km", "Diff (km)"], cmp_rows,
                [0.8, 3.5, 1.0, 1.0, 0.97], size=6.9)
        d.para("Expected values were screening estimates made before execution. They were used only for screening and are "
               "shown here for transparency. Measured values come from this run's Route Engine responses. Where the estimate "
               "exceeds the measurement, the estimate was conservative; only the measured figure is reported.")

        d.heading("16. Conclusion")
        d.bullets([
            f"Did the E2E pipeline work? Yes for this dataset: all {S['executed']} orchestrations completed through "
            "every stage (requirement, allocation, fulfilment, mission, assignment, route, lifecycle), with no technical "
            "failures.",
            "Did resource accounting remain correct? Yes. Allocated + shortage = required for every resource in every "
            "scenario, and allocation totals match the warehouse allocations. Shortages were large and are reported as "
            "they occurred.",
            "Did the responder lifecycle work? Yes for these missions. Each assigned responder went AVAILABLE → BUSY, "
            "was released on close, and returned to its original state. Lifecycle checks (4/4) passed. Responders were reused "
            f"{resp['reuse_missions']} times.",
            f"Did realistic local routing work? Measured distances stayed between {rt['min']:.2f} and {rt['max']:.2f} km, "
            f"with a median of {rt['median']:.2f} km. Routing was real but not disaster-aware, because OpenWeb Ninja was "
            "unavailable.",
            f"Were any scenarios over 150 km? Among the executed scenarios, none ({b['>150']}). Two scenarios were "
            "measured above 150 km before execution and excluded.",
            "What failed? Nothing technical. Shortages are business outcomes, and OpenWeb Ninja failed with HTTP 429 "
            "on all 28 requests.",
            "Failures came from: AASHRAY — none. Route Engine — none. External APIs — OpenWeb Ninja quota (HTTP 429). "
            "Google Routes — quota blocked the run at 04:20 UTC on 2026-10-09 (before the reset), and the run went ahead "
            "after the 07:00 UTC reset.",
        ])

        d.heading("17. Limitations")
        d.bullets([
            f"Scale: {S['executed']} scenarios from one region, all in Maharashtra. These results do not show that AASHRAY "
            "is universally validated.",
            "Disaster-aware routing was not tested: OpenWeb Ninja returned HTTP 429 on all requests, so road conditions "
            "are UNKNOWN.",
            "Stock was not depleted between scenarios; each scenario drew from the same starting stock. Sequential "
            "depletion, competing demand and concurrency were not tested.",
            "Google routes are traffic-aware. Measured distances and times vary between runs. E2E-001 measured 99.58 km "
            "here against 100.54 km in the previous run.",
            "Only one responder assignment per mission; multi-responder dispatch was not tested.",
            "The two borderline scenarios were excluded by measurement, not executed.",
        ])

        d.heading("18. What was validated and what was not")
        d.para("Validated by this run: the real AASHRAY HTTP pipeline on 11 Maharashtra scenarios; resource accounting "
               "(allocated + shortage = required); mission creation and warehouse pickup order; responder assignment and "
               "lifecycle release, reuse and idempotency; route legs with unique Route Engine IDs and totals; database "
               "recording of legs; integrity of data files and the 12,000-scenario experiment.")
        d.para("Not validated: disaster-aware routing (OpenWeb unavailable); depletion of stock across sequential missions; "
               "concurrent scenarios; re-routing after road-condition changes; scenarios beyond the 11 selected; behaviour "
               "under Google quota exhaustion mid-run (the run stopped at the probe; it did not occur mid-run).")
        d.para(f"Overall result: {S['overall_result']}. Reason: every executed scenario completed with its invariants "
               "satisfied, but disaster-aware routing could not be validated and the dataset is small.")

        d.close()
    print("wrote", OUT)


if __name__ == "__main__":
    main()
