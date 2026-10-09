"""Build the AASHRAY resource-allocation hypothesis-testing report (DOCX, then PDF via Word).

Every number is read from data/report_data.json (written by prepare_report_data.py from the
validated final results) or, for the integrity counts, from the final validation report.
Nothing in experiments/ is written.

Usage (from the repository root, after prepare_report_data.py and make_charts.py):

    python reports/resource_allocation_hypothesis_report/scripts/build_report.py
"""

import json
import sys
from datetime import datetime
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt

sys.path.insert(0, str(Path(__file__).resolve().parent))
from docx_kit import (  # noqa: E402
    BLUE, BLUE_EDGE, BODY_PT, CONTENT_W, GREEN, GREY, H0_FILL, INK, LBLUE, OBJ_FILL, SLATE, Math, YELLOW,
    YELLOW_EDGE, add_text, bottom_rule, box, bullet, caption, data_table, figure, figure_pair, fmt, footer_text,
    header_text, hypothesis_box, keep_table_with_next, math_para, setup_styles,
)

REPORT_ROOT = Path(__file__).resolve().parents[1]
REPO = REPORT_ROOT.parents[1]
FINAL = REPO / "experiments" / "resource_allocation_final"
CHARTS = REPORT_ROOT / "charts"
STEM = "AASHRAY_Resource_Allocation_Hypothesis_Report"
DOCX_PATH = REPORT_ROOT / f"{STEM}.docx"
PDF_PATH = REPORT_ROOT / f"{STEM}.pdf"

TITLE = "AASHRAY: Hypothesis Testing Report — Impact-Driven Resource Allocation"
SERIES = "AASHRAY: An AI-Based Framework for Cyclone Disaster Response and Impact-Driven Resource Allocation"
POLICY_STATEMENT = ("The parameter search selected a policy mathematically equivalent to a balanced linear "
                    "severity–urgency score, P = 0.5S + 0.5U. The geometric component therefore does not "
                    "contribute to the final experimental policy.")

D = json.loads((REPORT_ROOT / "data" / "report_data.json").read_text(encoding="utf-8"))
VAL = json.loads((FINAL / "results" / "validation_report.json").read_text(encoding="utf-8"))
VCHK = {c["id"]: c for c in VAL["checks"]}
LEVELS = ("LOW", "MODERATE", "HIGH")


# ---------------------------------------------------------------- number formatting
def f4(x):
    return f"{x:.4f}"


def sg4(x):
    return "0.0000" if abs(x) < 5e-5 else f"{x:+.4f}".replace("-", "−")


def pc(x, d=2):
    return f"{x:.{d}f}%"


def n(x):
    return f"{int(round(x)):,}"


def ms(x):
    return f"{x:.3f}"


def sci(x):
    mant, exp = f"{x:.4e}".split("e")
    return f"{mant} × 10^{{{str(int(exp)).replace('-', '−')}}}"


def times(x, d=1):
    return f"{x:.{d}f}×"


CDC = D["cdc"]
PAIR = D["paired"]
PERM = D["permutation"]
BOOT = D["bootstrap"]
WIL = D["wilcoxon"]
EFF = D["effect"]
WTL = D["win_tie_loss"]
SC = D["scarcity"]
OPT = D["optimality"]
RT = D["runtime"]
WC = D["worst_case"]
DS = D["dataset"]
INTEG = D["integrity"]
ENV = D["environment"]
FROZEN = D["frozen_parameters"]
N = DS["n"]

CI = f"[{f4(BOOT['confidence_interval'][0])}, {f4(BOOT['confidence_interval'][1])}]"
P_PERM = sci(PERM["p_value"])
REL = PAIR["relative_improvement"] * 100
NONTIED = EFF["aashray_wins"] + EFF["fcfs_wins"]
LE_ZERO = EFF["ties"] + EFF["fcfs_wins"]
HIGH = SC["HIGH"]
MOD = SC["MODERATE"]
HIGH_CI = f"[{f4(HIGH['diff_ci_descriptive'][0])}, {f4(HIGH['diff_ci_descriptive'][1])}]"
GAP_POS = N - OPT["exact_count"]


def check(condition, message):
    if not condition:
        raise SystemExit(f"CONSISTENCY CHECK FAILED: {message}")


# Arithmetic that the text relies on.
check(EFF["aashray_wins"] + EFF["ties"] + EFF["fcfs_wins"] == N, "win/tie/loss must sum to n")
check(sum(DS["scarcity_counts"].values()) == N, "scarcity counts must sum to n")
check(sum(WTL[l]["ties"] for l in LEVELS) == EFF["ties"], "ties by level must sum")
check(abs((EFF["aashray_wins"] + 0.5 * EFF["ties"]) / N - EFF["probability_of_superiority"]) < 1e-12, "PS")
check(LE_ZERO > N / 2, "median argument needs more than half of differences <= 0")
check(EFF["fcfs_wins"] < N / 2 <= LE_ZERO, "median order statistics must fall in the tie block")
check(PERM["permuted_means_at_least_observed"] == 0, "permutation count")
check(abs(PERM["p_value"] - 1 / (PERM["permutations"] + 1)) < 1e-15, "minimum attainable p")
check(WC["by_scarcity"]["HIGH"] == WC["count"], "all worst cases HIGH")
check(INTEG["validation"] == "37/37" and INTEG["gate"] == "35/35", "integrity counts")
check(D["milp"]["proven_optimal"] == N == D["milp"]["analytical_match"], "MILP validation")


# ---------------------------------------------------------------- document helpers
doc = Document()
setup_styles(doc)
sec = doc.sections[0]
sec.page_width, sec.page_height = Inches(8.27), Inches(11.69)
sec.left_margin = sec.right_margin = Inches(0.7)
sec.top_margin = Inches(0.72)
sec.bottom_margin = Inches(0.68)
sec.header_distance = Inches(0.36)
sec.footer_distance = Inches(0.36)
sec.different_first_page_header_footer = True
footer_text(sec.footer)
footer_text(sec.first_page_footer)
header_text(sec.header, "Hypothesis Testing Report — Impact-Driven Resource Allocation")

FIG = {"n": 0}


def P(text="", before=0, after=5, align=None, keep=False, size=BODY_PT, **kw):
    p = doc.add_paragraph()
    fmt(p, before, after, align=align, keep=keep)
    if text:
        add_text(p, text, size=size, **kw)
    return p


def H1(text):
    p = doc.add_paragraph(style="Heading 1")
    fmt(p, 13, 6, keep=True, line=1.0)
    add_text(p, text, size=15, color=INK, bold=True)
    bottom_rule(p, BLUE, size=8, space=3)
    return p


def H2(text, blue=False, before=8):
    p = doc.add_paragraph(style="Heading 3" if blue else "Heading 2")
    fmt(p, before, 4, keep=True, line=1.0)
    add_text(p, text, size=12 if blue else 11, color=BLUE if blue else "000000", bold=True)
    return p


def fig_caption(text):
    FIG["n"] += 1
    return f"Figure {FIG['n']}. {text}"


def spacer(pt=4):
    p = doc.add_paragraph()
    fmt(p, 0, 0, line=1.0)
    p.paragraph_format.line_spacing = Pt(pt)
    return p


m = Math(10.5)
mi = Math(10)
S_i = m.sub(m.r("S"), m.r("i"))
U_i = m.sub(m.r("U"), m.r("i"))


def cdc_sub(mm, who, idx=True):
    return mm.sub(mm.t("CDC"), mm.t(who + (",") if idx else who) + (mm.r("i") if idx else ""))


def mu_delta(mm):
    return mm.sub(mm.r("μ"), mm.t("Δ"))


# ================================================================= Title block
p = P(after=2)
add_text(p, SERIES, size=10, color=BLUE, bold=True)
p = P(after=3)
fmt(p, 2, 3, line=1.0)
add_text(p, "AASHRAY: Hypothesis Testing Report —\nImpact-Driven Resource Allocation", size=22, color=INK, bold=True)
run_day = datetime.fromisoformat(INTEG["run_started"]).strftime("%d %B %Y").lstrip("0")
P(f"Final pre-registered experiment · {n(N)} held-out synthetic scenarios · official run {run_day}",
  size=9, color=GREY, after=2)

# ================================================================= 1. Hypothesis
H1("1. Hypothesis")
H2("Research question", before=2)
P("*Does severity–urgency-based priority allocation improve critical-demand coverage compared with "
  "arrival-time-based FCFS under constrained resource availability?*")

H2("Primary hypothesis (critical-demand coverage)")
P("The primary metric is **Critical Demand Coverage (CDC)**: the share of the demand of **GT-critical** "
  "(reference-critical) emergencies that a policy fulfils, summed over water, food and medical kits. The "
  "GT-critical label comes from the fixed reference criticality rule defined later in this section. Both "
  "policies are run on every scenario, so the comparison is paired: Δ_{i} is the CDC difference in scenario i "
  "and μ_{Δ} is its mean over scenarios.", after=0, keep=True)
math_para(doc, m.t("CDC") + m.r(" = ") + m.frac(m.words("GT-critical demand fulfilled"),
                                                m.words("total GT-critical demand")) +
          m.t(",          ") + m.sub(m.t("Δ"), m.r("i")) + m.r(" = ") + cdc_sub(m, "AASHRAY") + m.r(" − ") +
          cdc_sub(m, "FCFS"), keep=True, after=8)
mh = Math(13)


def hypothesis(label, fill, statement, relation, keep=False):
    table, txt = hypothesis_box(doc, label, fill, margins=(130, 120, 150, 170))
    add_text(txt.paragraphs[0], statement, size=10.5)
    pm = txt.add_paragraph()
    fmt(pm, 5, 0, line=1.0)
    pm._p.append(Math.display(mu_delta(mh) + mh.r(relation), jc="center"))
    if keep:
        keep_table_with_next(table)
    return table


hypothesis("H0", H0_FILL,
           "Under constrained resource availability, the severity–urgency-based AASHRAY allocation policy does not "
           "improve critical-demand coverage compared with arrival-time-based FCFS allocation. The mean paired "
           f"difference in Critical Demand Coverage (CDC) across the {n(N)} held-out scenarios is non-positive.",
           " ≤ 0", keep=True)
spacer(12).paragraph_format.keep_with_next = True
hypothesis("H1", LBLUE,
           "Under constrained resource availability, the severity–urgency-based AASHRAY allocation policy improves "
           "critical-demand coverage compared with arrival-time-based FCFS allocation. The mean paired difference "
           f"in Critical Demand Coverage (CDC) across the {n(N)} held-out scenarios is positive.",
           " > 0")
P(f"H0 and H1 form the single **primary inferential hypothesis**. It is tested with a one-sided paired "
  f"sign-flip permutation test at α\u00a0=\u00a0{PERM['alpha']:g} (Section 4).", before=7)

H2("Secondary evaluation objectives (descriptive; not significance-tested)")
P("H2 and H3 are secondary evaluation objectives, not primary inferential hypotheses.", after=7, keep=True)


def objective(label, title, statement, measures, keep=False):
    table, txt = hypothesis_box(doc, label, OBJ_FILL, sublabel="secondary\nobjective", label_color=SLATE)
    add_text(txt.paragraphs[0], title, size=10.5, bold=True)
    p2 = txt.add_paragraph()
    fmt(p2, 2, 0, line=1.15)
    add_text(p2, statement, size=10.5)
    p3 = txt.add_paragraph()
    fmt(p3, 5, 0, line=1.1)
    add_text(p3, measures, size=9, color=GREY, italic=True)
    if keep:
        keep_table_with_next(table)
    return table


objective("H2", "Optimality",
          "AASHRAY achieves high critical-demand coverage relative to the MILP optimization benchmark.",
          "Measures: optimality gap; exact-optimum and within-1%, 5% and 10% rates (Section 5). Descriptive: "
          "the MILP is the benchmark, so no AASHRAY-vs-MILP significance test is run.",
          keep=True)
spacer(12).paragraph_format.keep_with_next = True
objective("H3", "Computational efficiency",
          "AASHRAY requires substantially less computation than solving the MILP benchmark.",
          "Measures: mean, median, P95 and total runtime; conservative speedup (Section 7). Descriptive; "
          "hardware and implementation dependent.")

H2("Methods compared", before=10)
P("Each emergency has a severity S, an urgency U, a resource demand and an arrival time; warehouses hold "
  "limited water, food and medical kits, so order matters only when supply cannot meet all demand. Two "
  "allocation policies and one optimization benchmark were run on identical inputs:", after=5, keep=True)
# The application's allocation service has its own built-in score; the official run neutralized it.
APP_W = json.loads((REPO / "resource_services" / "config" / "resource_rules.json").read_text(encoding="utf-8"))[
    "allocation_priority"]["weights"]
PLACEHOLDERS = json.loads((FINAL / "results" / "run_metadata.json").read_text(encoding="utf-8"))["allocator_placeholders"]
data_table(doc, ["Method", "Decision rule", "Role"], [
    ["FCFS", "Arrival order (timestamp, then emergency id); uses no severity or urgency information.",
     "Allocation policy (baseline)"],
    ["AASHRAY", f"Descending P = 0.5S + 0.5U from the experiment's ranking code (frozen {FROZEN['config_id']}; ties "
                f"in FCFS order). The application's allocation service, whose own score is {APP_W['severity']:g}S + "
                f"{APP_W['urgency']:g}U + {APP_W['priority']:g} × categorical priority level, got identical inputs "
                f"(S = {PLACEHOLDERS['severity']:g}, U = {PLACEHOLDERS['urgency']:g}, {PLACEHOLDERS['priority']}) "
                "for every emergency, so it allocated in exactly this order (verified on every call).",
     "Allocation policy under test"],
    ["MILP", "Integer program maximizing the GT-critical demand units fulfilled (Section 5); not a competing "
             "heuristic.", "Optimization benchmark / verification oracle"],
], [0.95, 4.27, 1.65])

H2("AASHRAY priority score and reference criticality")
P("The development parameter search allowed a generalized priority formulation with normalized weights:",
  before=4, after=0, keep=True)
math_para(doc, m.sub(m.r("P"), m.r("n")) + m.r(" = ") + m.sup(m.r("S"), m.r("α")) +
          m.sup(m.r("U"), m.r("1−α")) + m.t(",          ") + m.sub(m.r("P"), m.r("o")) +
          m.r(" = kS + mU + n") + m.sub(m.r("P"), m.r("n")), keep=True)
P(f"It selected configuration {FROZEN['config_id']} (α = {FROZEN['alpha']:g}, k = {FROZEN['k']:g}, "
  f"m = {FROZEN['m']:g}, n = {FROZEN['n']:g}). With α = 0 the geometric term reduces to P_{{n}} = U, so the "
  "frozen AASHRAY priority score is", after=0, keep=True)
math_para(doc, m.sub(m.r("P"), m.r("i")) + m.r(" = 0.5") + S_i + m.r(" + 0.5") + U_i, keep=True)
c = box(doc, fill=LBLUE, edge=BLUE_EDGE)
add_text(c.paragraphs[0], f"**{POLICY_STATEMENT}**", size=BODY_PT, color=INK)
P("The AASHRAY priority score and the reference criticality rule are separate scoring mechanisms. The "
  "reference criticality rule is fixed independently of the AASHRAY configuration and allocation method, but "
  "it is derived from the same severity (S) and urgency (U) variables used by the priority score. It uses no "
  "AASHRAY parameter (α, k, m, n) and no allocation output. An emergency is **GT-critical** "
  "(reference-critical) when GT_{i} = 1:", before=7, after=0, keep=True)
gt_cond = (m.t("if  ") + m.delim(S_i + m.r(" ≥ 0.8 ∧ ") + U_i + m.r(" ≥ 0.8")) + m.r(" ∨ ") + S_i +
           m.r(" ≥ 0.95 ∨ ") + U_i + m.r(" ≥ 0.95"))
gt_cases = m.matrix([[m.r("1,"), gt_cond], [m.r("0,"), m.t("otherwise")]], gap_twips=200)
math_para(doc, m.sub(m.t("GT"), m.r("i")) + m.r(" = ") + m.delim(gt_cases, "{", ""), keep=True)
P("This is a predefined simulation reference criterion for evaluating allocation priority; it is not an "
  "externally validated operational or clinical definition of real-world criticality. Throughout this report, "
  "“critical” refers only to this GT-critical label; the AASHRAY priority score P is a separate quantity and "
  "is never used to define CDC.")

H2("Test design", blue=True, before=10)
sd = DS["scarcity_design"]


def ratio(lvl):
    a, b = sd[lvl]["ratio"]
    return f"{a:.2f}–{b:.2f}"


sizes = DS["scenario_sizes"]
data_table(doc, ["Item", "Specification"], [
    ["Design", "Paired, within-scenario comparison; FCFS, AASHRAY and the MILP benchmark get identical inputs."],
    ["Dataset", f"{n(N)} independently generated held-out synthetic disaster scenarios; seed {DS['seed']}; "
                f"namespace {DS['namespace']}."],
    ["Scarcity strata (pre-registered)",
     f"LOW {n(DS['scarcity_counts']['LOW'])} (supply/demand ratio {ratio('LOW')}) · MODERATE "
     f"{n(DS['scarcity_counts']['MODERATE'])} ({ratio('MODERATE')}) · HIGH {n(DS['scarcity_counts']['HIGH'])} "
     f"({ratio('HIGH')}) · total {n(N)}."],
    ["Scenario composition",
     f"{DS['emergencies_per_scenario']['min']}–{DS['emergencies_per_scenario']['max']} emergencies per scenario "
     f"(size classes {sizes['SMALL'][0]}–{sizes['SMALL'][1]}, {sizes['MEDIUM'][0]}–{sizes['MEDIUM'][1]}, "
     f"{sizes['LARGE'][0]}–{sizes['LARGE'][1]}; mean {DS['emergencies_per_scenario']['mean']:.2f}; "
     f"{n(DS['emergencies_total'])} emergencies, {n(DS['gt_critical_emergencies'])} GT-critical) and "
     f"{DS['warehouses_per_scenario'][0]}–{DS['warehouses_per_scenario'][1]} warehouses; water, food and "
     f"medical kits; {len(DS['su_profiles'])} severity–urgency profiles, each scarcity level spread evenly "
     f"over 15 size × profile cells; arrivals within a {n(DS['arrival_window_s'])} s window; demand drawn "
     "independently of S, U and arrival."],
    ["Primary metric and test",
     f"CDC. One-sided paired sign-flip permutation test of mean Δ; {n(PERM['permutations'])} permutations; "
     f"seed {PERM['seed']}; α = {PERM['alpha']:g}."],
    ["Secondary statistics",
     f"Paired percentile bootstrap 95% CI ({n(BOOT['resamples'])} resamples, seed {BOOT['seed']}); one-sided "
     "Wilcoxon signed-rank test; Cohen's d_{z}; win/tie/loss; probability of superiority. "
     "Tie rule |Δ| ≤ 10^{−9}. Descriptive: optimality gap (H2), runtime (H3), Total Demand Coverage (TDC)."],
], [1.55, 5.32])

H2("Experimental integrity and reproducibility")
redraw = DS["scenarios_needing_su_redraw"]
files_ok = [VCHK[k]["details"]["files"] for k in ("28", "29", "30", "E1")]
integrity_rows = [
    ["Completion", f"{n(INTEG['scenarios_run'])}/{n(N)} scenarios completed by every method; none dropped or "
                   "rerun (single official run)."],
    ["Frozen dataset", f"Frozen {DS['frozen_at_utc'][:10]} {DS['frozen_at_utc'][11:19]} UTC, before execution "
                       f"started ({INTEG['run_started'][11:19]} UTC); read-only and unchanged afterwards. "
                       f"SHA-256 {DS['sha256']}."],
    ["Generator equivalence", "Copied generator reproduced the development dataset byte for byte (development "
                              "settings)."],
    ["No contamination", f"{INTEG['dev_overlap']} scenarios shared with the development data and "
                         f"{INTEG['pilot_overlap']} with the pilot data."],
    ["GT-critical coverage", f"Every scenario has at least one GT-critical emergency (S/U rejection sampling; "
                             f"{n(redraw)} scenarios redrawn; other streams unaffected)."],
    ["Identical inputs", "FCFS, AASHRAY and MILP received identical scenario inputs (0 mismatches)."],
    ["Frozen configuration", f"One AASHRAY configuration ({FROZEN['config_id']}); scripts and configuration frozen "
                             "before the run; no parameter tuning on the final test set."],
    ["Checks", f"{INTEG['gate']} gate checks passed; {INTEG['validation']} final validation checks passed "
               f"({INTEG['validation_failures']} failures)."],
    ["MILP", f"{n(D['milp']['proven_optimal'])}/{n(N)} proven optimal; {n(D['milp']['analytical_match'])}/{n(N)} "
             f"matched the analytical optimum; {D['milp']['failures']} failures."],
    ["Unchanged files", f"No application ({files_ok[0]}), development ({files_ok[1]}), pilot ({files_ok[2]}) or "
                        f"MILP ({files_ok[3]}) files modified; application tests pass "
                        f"({INTEG['application_tests'].split(' in ')[0]})."],
]
data_table(doc, ["Check", "Result"], integrity_rows, [1.55, 5.32], keep_together=False)

# ================================================================= 2. Results at a glance
H1("2. Results at a Glance")
glance = [
    ["Mean CDC (primary)", f4(CDC["FCFS"]["mean"]), f4(CDC["AASHRAY"]["mean"]), f4(CDC["MILP"]["mean"]),
     f"Δ = {sg4(PAIR['mean'])} ({PAIR['pp']:+.2f} pp; {REL:+.1f}% relative); 95% CI {CI}; "
     f"permutation p = {P_PERM}", "**H0 rejected; primary H1 supported**"],
    ["Effect size", "—", "—", "—",
     f"Cohen's d_{{z}} = {EFF['cohens_dz']:.3f}; probability of superiority = "
     f"{EFF['probability_of_superiority']:.3f} (ties weighted ½)", "**Consistent with H1**"],
    ["Median CDC; median Δ", f4(CDC["FCFS"]["median"]), f4(CDC["AASHRAY"]["median"]), f4(CDC["MILP"]["median"]),
     f"Median Δ = 0 because {pc(EFF['tie_rate'] * 100)} of scenarios are exact ties",
     "**Expected given ties (see text)**"],
    ["Paired outcome", f"{n(EFF['fcfs_wins'])} wins ({pc(EFF['fcfs_win_rate'] * 100)})",
     f"{n(EFF['aashray_wins'])} wins ({pc(EFF['win_rate'] * 100)})", "—",
     f"{n(EFF['ties'])} ties ({pc(EFF['tie_rate'] * 100)}); AASHRAY ≥ FCFS in "
     f"{pc((1 - EFF['fcfs_win_rate']) * 100)}", "**Better or equal in most scenarios; not always better**"],
    ["HIGH-scarcity CDC", f4(HIGH["cdc"]["FCFS"]), f4(HIGH["cdc"]["AASHRAY"]), f4(HIGH["cdc"]["MILP"]),
     f"{sg4(HIGH['diff_mean'])} absolute over FCFS (n = {n(HIGH['n'])}; descriptive 95% CI {HIGH_CI})",
     "**Largest benefit under scarcity**"],
    ["Optimality vs MILP (H2)", "—", f"exact {pc(OPT['exact_optimum_pct'])}; within 10% "
     f"{pc(OPT['within_10pct_pct'])}", "benchmark",
     f"Mean relative gap {f4(OPT['mean_gap'])}; median 0; P95 {f4(OPT['p95_gap'])}; no significance test",
     "**Near-optimal in most scenarios; not optimal**"],
    ["Runtime per scenario (H3)", "—", f"{ms(RT['AASHRAY_conservative']['mean'])} ms (conservative mean)",
     f"{ms(RT['MILP']['mean'])} ms",
     f"Conservative {times(RT['speedup_conservative_total'])} by total, "
     f"{times(RT['speedup_conservative_median'])} by median; raw {RT['speedup_raw_total']:.2f}× is "
     "order-affected", "**Supported (descriptive only)**"],
    ["TDC (descriptive)", f4(D["tdc"]["FCFS"]), f4(D["tdc"]["AASHRAY"]), "—",
     "Identical for FCFS and AASHRAY in every scenario (order-invariant)", "**Descriptive only**"],
]
fills = {(0, 5): GREEN, (1, 5): GREEN, (2, 5): YELLOW, (3, 5): YELLOW, (4, 5): GREEN, (5, 5): YELLOW,
         (6, 5): GREEN}
data_table(doc, ["Metric", "FCFS", "AASHRAY", "MILP", "Statistical / interpretation", "Conclusion"], glance,
           [1.12, 0.78, 0.98, 0.72, 2.0, 1.27], align=["left", "center", "center", "center", "left", "left"],
           header_align=["left", "center", "center", "center", "left", "left"], fills=fills, size=8.5)
P(f"**Bottom line: Under the fixed reference criticality rule used in this experiment, AASHRAY substantially "
  f"improves critical-demand coverage compared with FCFS. Mean CDC rose from {f4(CDC['FCFS']['mean'])} to "
  f"{f4(CDC['AASHRAY']['mean'])} ({sg4(PAIR['mean'])}; permutation p = {P_PERM}), so H0 is rejected. The gain "
  f"is largest under HIGH scarcity. AASHRAY reaches the MILP optimum in {pc(OPT['exact_optimum_pct'])} of "
  "scenarios and needs far less computation, but it is not optimal in every scenario and not better than FCFS "
  "in every scenario.**", before=7)

H2("Win / tie / loss")
wtl_rows = []
for scope in ("ALL",) + LEVELS:
    w = WTL[scope]
    wtl_rows.append([scope if scope != "ALL" else "All scenarios", n(w["n"]),
                     f"{n(w['aashray_wins'])} ({pc(w['aashray_win_pct'])})", f"{n(w['ties'])} ({pc(w['tie_pct'])})",
                     f"{n(w['fcfs_wins'])} ({pc(w['fcfs_win_pct'])})"])
data_table(doc, ["Scope", "n", "AASHRAY wins (Δ > 0)", "Ties (|Δ| ≤ 10^{−9})", "FCFS wins (Δ < 0)"], wtl_rows,
           [1.55, 0.8, 1.55, 1.42, 1.55], align=["left", "center", "center", "center", "center"],
           bold_rows=(0,))
check(sum(int(r[1].replace(",", "")) for r in wtl_rows[1:]) == N, "W/T/L scopes")
H2("Reading the paired outcome", before=6)
P(f"**Why the median paired difference is 0.** The median paired difference is 0 because the distribution "
  f"contains {n(EFF['ties'])} exact ties; this does not imply that AASHRAY has no effect. The mean difference is "
  f"{sg4(PAIR['mean'])}. Together with the {n(EFF['fcfs_wins'])} FCFS wins, the ties make up {n(LE_ZERO)} of the "
  f"{n(N)} differences ({pc(LE_ZERO / N * 100)}), so both middle values of the sorted differences (the "
  f"{n(N // 2)}th and {n(N // 2 + 1)}th) are exactly 0. Ties occur at every scarcity level, not only where supply "
  f"is ample: all {n(WTL['LOW']['ties'])} LOW scenarios, {n(WTL['MODERATE']['ties'])} of {n(MOD['n'])} MODERATE "
  f"scenarios and {n(WTL['HIGH']['ties'])} of {n(HIGH['n'])} HIGH scenarios (table above).")
P(f"**Win rate versus probability of superiority.** The win rate ({pc(EFF['win_rate'] * 100)}) counts only "
  "scenarios in which AASHRAY is strictly better. The **probability of superiority** counts each tie as half "
  f"a win: PS = ({n(EFF['aashray_wins'])} + 0.5 × {n(EFF['ties'])}) / {n(N)} = "
  f"{EFF['probability_of_superiority']:.3f}. The two numbers measure different things and do not conflict. "
  f"Among the {n(NONTIED)} non-tied scenarios, AASHRAY is better in {n(EFF['aashray_wins'])} "
  f"({pc(EFF['aashray_wins'] / NONTIED * 100)}).")

spacer(6)
figure_pair(doc,
            (CHARTS / "fig01_mean_cdc.png",
             fig_caption(f"Mean critical-demand coverage across {n(N)} held-out disaster scenarios.")),
            (CHARTS / "fig02_win_tie_loss.png",
             fig_caption("Scenario-level paired outcome between AASHRAY and FCFS.")))
# ================================================================= 3. Scarcity
H1("3. Scarcity-Stratified Results")
P("Scarcity is the pre-registered stratification factor: it sets the ratio of total supply to total demand "
  "in each scenario. The HIGH-scarcity stratum gives the strongest practical result. Stratum-level intervals "
  "are descriptive; the only inferential test is the overall primary test.")
sc_rows = []
for lvl in LEVELS:
    s = SC[lvl]
    sc_rows.append([lvl, n(s["n"]), f4(s["cdc"]["FCFS"]), f4(s["cdc"]["AASHRAY"]), f4(s["cdc"]["MILP"]),
                    sg4(s["diff_mean"]), f4(s["mean_relative_gap"])])
check(sum(SC[l]["n"] for l in LEVELS) == N, "scarcity n")
hfill = {(2, c): LBLUE for c in range(7)}
data_table(doc, ["Scarcity", "n", "FCFS CDC", "AASHRAY CDC", "MILP CDC", "AASHRAY − FCFS",
                 "Mean optimality gap ‡"], sc_rows, [0.95, 0.7, 0.9, 1.05, 0.9, 1.12, 1.25],
           align=["left"] + ["center"] * 6, fills=hfill, bold_rows=(2,))
diff_m = SC["MODERATE"]["cdc"]["AASHRAY"] - SC["MODERATE"]["cdc"]["MILP"]
diff_h = SC["HIGH"]["cdc"]["AASHRAY"] - SC["HIGH"]["cdc"]["MILP"]
P(f"‡ Mean relative gap (CDC_{{MILP}} − CDC_{{AASHRAY}}) / CDC_{{MILP}} (Section 5). The report brief labelled "
  f"this column 'AASHRAY−MILP' with the values {f4(SC['MODERATE']['mean_relative_gap'])} and "
  f"{f4(SC['HIGH']['mean_relative_gap'])}; those are mean relative gaps. The difference of means AASHRAY − MILP "
  f"is {sg4(diff_m)} (MODERATE) and {sg4(diff_h)} (HIGH).", size=8, color=GREY, before=3)
c = box(doc, fill=LBLUE, edge=BLUE_EDGE)
add_text(c.paragraphs[0],
         f"**HIGH scarcity (n = {n(HIGH['n'])}): CDC {f4(HIGH['cdc']['FCFS'])} (FCFS) → "
         f"{f4(HIGH['cdc']['AASHRAY'])} (AASHRAY), an improvement of {sg4(HIGH['diff_mean'])} absolute.**",
         size=11, color=INK)
hp = c.add_paragraph()
fmt(hp, 3, 0, line=1.1)
add_text(hp, f"Descriptive 95% CI {HIGH_CI}. AASHRAY is better in {n(HIGH['wins'])} HIGH scenarios "
             f"({pc(HIGH['win_pct'])}), tied in {n(HIGH['ties'])} ({pc(HIGH['tie_pct'])}) and worse in "
             f"{n(HIGH['fcfs_wins'])} ({pc(HIGH['fcfs_win_pct'])}); the MILP benchmark reaches "
             f"{f4(HIGH['cdc']['MILP'])}.", color=INK)
P(f"Under MODERATE scarcity the gain is small ({sg4(MOD['diff_mean'])}; AASHRAY better in {pc(MOD['win_pct'])}, "
  f"tied in {pc(MOD['tie_pct'])}). Under LOW scarcity all three methods reach full GT-critical coverage "
  f"(CDC = {f4(SC['LOW']['cdc']['AASHRAY'])}), so no improvement is possible and none is claimed. "
  "**The benefit of priority-based allocation becomes most pronounced when resources are scarce.**", before=7)
figure(doc, CHARTS / "fig03_cdc_by_scarcity.png",
       fig_caption("Critical-demand coverage by resource-scarcity level."))
H2("Total Demand Coverage (descriptive only)", before=4)
P(f"TDC is the share of all demand units fulfilled, GT-critical or not. Overall TDC is {f4(D['tdc']['FCFS'])} "
  f"for both FCFS and AASHRAY (LOW {f4(D['tdc']['by_scarcity']['LOW'])}, MODERATE "
  f"{f4(D['tdc']['by_scarcity']['MODERATE'])}, HIGH {f4(D['tdc']['by_scarcity']['HIGH'])}), and the two values are "
  f"identical in every one of the {n(N)} scenarios. Under the current fungible-resource allocation model, with "
  "no vehicle, route or time limits, the serving order changes who receives resources rather than the total "
  "quantity eventually delivered. AASHRAY therefore does not improve total resource utilization, and TDC is "
  "reported descriptively, not as evidence for AASHRAY. CDC is the primary metric because the hypothesis "
  "concerns the prioritization of GT-critical demand. MILP TDC is not reported: the MILP objective counts only "
  "GT-critical demand, so its allocation of other demand is solver-dependent.")

# ================================================================= 4. Statistical testing
H1("4. Statistical Testing")
P(f"Each method is evaluated on exactly the same scenario, so inference uses the per-scenario paired "
  f"differences Δ_{{i}} = CDC_{{AASHRAY,i}} − CDC_{{FCFS,i}} (n = {n(PAIR['n'])}; no scenario had undefined "
  f"CDC). The test statistic is the mean difference, {sg4(PAIR['mean'])} ({PAIR['pp']:+.2f} percentage points; "
  f"{REL:+.1f}% relative to the FCFS mean). Under H0 the sign of each paired difference is exchangeable, so "
  "the permutation test re-evaluates the mean after independent random sign flips:", after=0, keep=True)
dbar = m.bar(m.t("Δ"))
math_para(doc, m.r("p = ") + m.frac(m.r("1 + #") + m.delim(m.r("b : ") + m.sup(dbar, m.delim(m.r("b"))) +
                                                         m.r(" ≥ ") + dbar, "{", "}"), m.r("B + 1")) +
          m.r(" = ") + m.frac(m.r("1"), m.r(f"{PERM['permutations'] + 1:,}")) + m.r(" ≈ 9.9999 × ") +
          m.sup(m.r("10"), m.r("−6")), keep=True)
stat_rows = [
    ["Sign-flip permutation (primary)",
     f"One-sided; statistic mean Δ; {n(PERM['permutations'])} random sign flips; seed {PERM['seed']}; "
     f"α = {PERM['alpha']:g}",
     f"Observed mean Δ = {f4(PERM['statistic'])}; {PERM['permuted_means_at_least_observed']} of "
     f"{n(PERM['permutations'])} permuted means ≥ observed; p = {P_PERM}", "**Reject H0**"],
    ["Paired percentile bootstrap",
     f"{n(BOOT['resamples'])} resamples of scenarios; seed {BOOT['seed']}; 2.5th / 97.5th percentiles",
     f"95% CI {CI}; bootstrap SE {f4(BOOT['bootstrap_standard_error'])}", "**CI excludes 0**"],
    ["Wilcoxon signed-rank (secondary)",
     f"One-sided (AASHRAY > FCFS); {n(WIL['n_zero'])} zero differences dropped, n = {n(WIL['n_nonzero'])}; "
     "normal approximation",
     f"W^{{+}} = {WIL['statistic']:,.1f}; z = {WIL['z']:.2f}; p < 10^{{−300}} (below double precision; "
     f"normal approximation log_{{10}} p ≈ {WIL['log10_p_normal_approx']:.0f})".replace("-", "−"),
     "**Consistent with primary**"],
    ["Effect size",
     "Cohen's d_{z} = mean Δ / SD(Δ), ddof = 1; PS = (wins + 0.5 × ties) / n",
     f"d_{{z}} = {EFF['cohens_dz']:.3f} (SD {f4(EFF['sd_difference'])}); probability of superiority = "
     f"{EFF['probability_of_superiority']:.3f}", "Descriptive"],
]
data_table(doc, ["Test", "Settings", "Result", "Decision"], stat_rows, [1.35, 2.15, 2.27, 1.1],
           fills={(0, 3): GREEN, (1, 3): GREEN, (2, 3): GREEN}, size=8.5)
P(f"None of the B = {n(PERM['permutations'])} sign-flipped means reached the observed value, so p equals the "
  "smallest value attainable with the +1 correction; resolving a smaller p-value would need more permutations. "
  "The Wilcoxon signed-rank test is secondary (the pre-registered primary inference is the permutation test). "
  "Its p-value underflows double-precision floating point (the library returns zero), so it is reported as a "
  "bound rather than as an exact value.", before=6)
figure(doc, CHARTS / "fig04_delta_distribution.png",
       fig_caption("Distribution of paired CDC improvements produced by AASHRAY relative to FCFS."))
figure(doc, CHARTS / "fig05_bootstrap.png",
       fig_caption("Paired bootstrap distribution of the mean CDC improvement (left: full scale including 0; "
                   "right: zoom with the 95% percentile interval)."))

# ================================================================= 5. Optimization benchmark
H1("5. Optimization Benchmark")
P("The MILP is used as an optimization benchmark and correctness oracle for the current allocation "
  "formulation. It is not treated as a competing heuristic. Its integer decision variable x_{e,r,w} is the "
  "number of units of resource type r allocated from warehouse w to emergency e; a_{w,r} is the supply and "
  "d_{e,r} the demand:", after=0, keep=True)
x = m.sub(m.r("x"), m.r("e,r,w"))
obj = (m.func(m.t("max"), m.nary("∑", m.r("e"), m.nary("∑", m.r("r"), m.nary("∑", m.r("w"),
                                                                           m.sub(m.t("GT"), m.r("e")) + x)))))
cons = m.matrix([
    [m.t("subject to"), m.nary("∑", m.r("e"), x) + m.r(" ≤ ") + m.sub(m.r("a"), m.r("w,r")), m.r("∀ w, r"),
     m.t("(warehouse supply)")],
    [m.t(" "), m.nary("∑", m.r("w"), x) + m.r(" ≤ ") + m.sub(m.r("d"), m.r("e,r")), m.r("∀ e, r"),
     m.t("(emergency demand)")],
    [m.t(" "), x + m.r(" ∈ ") + m.sub(m.r("ℤ"), m.r("≥0")), m.r("∀ e, r, w"), m.t("(integral, nonnegative)")],
], gap_twips=280)
math_para(doc, obj, keep=True, after=0)
math_para(doc, cons, keep=True)
P(f"Solved with {D['milp']['solver']}, relative MIP gap {D['milp']['options']['mip_rel_gap']:g} and a "
  f"{D['milp']['options']['time_limit']:g} s time limit. **{n(D['milp']['proven_optimal'])} / {n(N)} solutions "
  f"were proven optimal, {n(D['milp']['analytical_match'])} / {n(N)} matched an independently computed "
  f"analytical optimum, and there were {D['milp']['failures']} failures.**")
c = box(doc, fill=YELLOW, edge=YELLOW_EDGE)
add_text(c.paragraphs[0], "**Methodological caveat.** The current allocation model has no vehicle-capacity, "
         "travel-time, route, resource-compatibility or time-window constraints. Units of one resource type "
         "are interchangeable across warehouses, so the MILP optimum reduces to a closed-form bound on "
         "GT-critical demand fulfilment, where D_{r}^{crit} is the GT-critical demand and A_{r} the total "
         "supply of type r:", color=INK)
mc = Math(10)
closed = (mc.sup(mc.t("CDC"), mc.r("*")) + mc.r(" = ") +
          mc.frac(mc.nary("∑", mc.r("r"), mc.func(mc.t("min"), mc.delim(
              mc.subsup(mc.r("D"), mc.r("r"), mc.t("crit")) + mc.r(", ") + mc.sub(mc.r("A"), mc.r("r"))))),
                  mc.nary("∑", mc.r("r"), mc.subsup(mc.r("D"), mc.r("r"), mc.t("crit")))))
math_para(c, closed, before=3, after=3)
pc_ = c.add_paragraph()
fmt(pc_, 0, 0, line=1.1)
add_text(pc_, "The MILP therefore serves as an optimization benchmark / verification oracle for this "
              "formulation; it is not presented as a hard combinatorial problem or a difficult real-world "
              "optimization baseline.", color=INK)
P("AASHRAY's optimality gap is normalized by the MILP optimum:", before=7, after=0, keep=True)
math_para(doc, m.sub(m.t("gap"), m.r("i")) + m.r(" = ") +
          m.frac(cdc_sub(m, "MILP") + m.r(" − ") + cdc_sub(m, "AASHRAY"), cdc_sub(m, "MILP")) +
          m.t(",    with ") + m.sub(m.t("gap"), m.r("i")) + m.r(" = 0") + m.t("  if  ") + cdc_sub(m, "MILP") +
          m.r(" = 0"), keep=True)
P(f"The edge case CDC_{{MILP}} = 0 did not occur ({D['optimality']['scenarios_with_milp_cdc_zero_gap_defined_as_zero']} "
  f"scenarios): every scenario contains a GT-critical emergency and the lowest MILP CDC was "
  f"{f4(CDC['MILP']['min'])}. A scenario counts as an exact optimum when the two CDC values differ by at most "
  "10^{−9}. No significance test is run between AASHRAY and MILP, because the MILP is the benchmark.")
figure(doc, CHARTS / "fig06_gap_distribution.png",
       fig_caption("Distribution of AASHRAY's optimality gap relative to the MILP benchmark."))
opt_rows = [
    ["Mean relative gap", f4(OPT["mean_gap"]), "Exact optimum", f"{pc(OPT['exact_optimum_pct'])} ({n(OPT['exact_count'])})"],
    ["Median gap", f4(OPT["median_gap"]), "Within 1%", f"{pc(OPT['within_1pct_pct'])} ({n(OPT['within_1_count'])})"],
    ["P95 gap", f4(OPT["p95_gap"]), "Within 5%", f"{pc(OPT['within_5pct_pct'])} ({n(OPT['within_5_count'])})"],
    ["P99 gap", f4(OPT["p99_gap"]), "Within 10%", f"{pc(OPT['within_10pct_pct'])} ({n(OPT['within_10_count'])})"],
    ["Maximum gap", f4(OPT["max_gap"]), "Gap > 0", f"{pc(GAP_POS / N * 100)} ({n(GAP_POS)})"],
]
data_table(doc, ["Gap statistic", "Value", "Rate (n = 12,000)", "Share (count)"], opt_rows,
           [1.9, 1.3, 1.9, 1.77], align=["left", "center", "left", "center"])
P(f"AASHRAY reaches the exact MILP optimum in {n(OPT['exact_count'])} scenarios ({pc(OPT['exact_optimum_pct'])}) and "
  f"is within 10% in {n(OPT['within_10_count'])} ({pc(OPT['within_10pct_pct'])}). The gap distribution is "
  f"strongly skewed: the median is 0 and the mean {f4(OPT['mean_gap'])}, but the P95 is {f4(OPT['p95_gap'])} "
  f"and {n(GAP_POS)} scenarios have a positive gap. The gap grows with scarcity: the exact-optimum rate is "
  f"{pc(SC['LOW']['exact_pct'])} (LOW), {pc(MOD['exact_pct'])} (MODERATE) and {pc(HIGH['exact_pct'])} (HIGH), "
  f"and the mean gap {f4(SC['LOW']['mean_relative_gap'])}, {f4(MOD['mean_relative_gap'])} and "
  f"{f4(HIGH['mean_relative_gap'])}.", before=6)
figure(doc, CHARTS / "fig07_gap_by_scarcity.png",
       fig_caption("AASHRAY's optimality gap to the MILP benchmark by scarcity level (share of scenarios in "
                   "each gap band); the gap grows under HIGH scarcity."))
figure_pair(doc,
            (CHARTS / "fig08_optimality_rates.png",
             fig_caption("Fraction of scenarios in which AASHRAY reaches or approaches the MILP optimum.")),
            (CHARTS / "fig09_aashray_vs_milp.png",
             fig_caption("Scenario-level AASHRAY CDC relative to the MILP optimum (points on y = x are exact "
                         "optima; points below it fall short).")))

# ================================================================= 6. Worst cases
H1("6. Failure / Worst-Case Analysis")
mech = WC["mechanism"]
P(f"In **{WC['count']} of the {n(N)} scenarios AASHRAY covered zero GT-critical demand (CDC = 0) while the "
  f"MILP covered a positive amount.** All {WC['count']} are HIGH-scarcity scenarios ({WC['by_scarcity']['LOW']} LOW, "
  f"{WC['by_scarcity']['MODERATE']} MODERATE). In these scenarios the mean MILP CDC was "
  f"{f4(WC['milp_cdc_mean_in_these'])} and the mean FCFS CDC {f4(WC['fcfs_cdc_mean_in_these'])}.")
P("**Observed mechanism.** AASHRAY ranks by the continuous priority score 0.5S + 0.5U, whereas GT-criticality "
  "is a threshold rule. An emergency can be GT-critical through a single extreme value (S ≥ 0.95 or U ≥ 0.95) "
  "while its other value is low, which gives it only a moderate balanced score; an emergency that is not "
  "GT-critical but has two mid-range values can then score higher and consume the scarce supply first. In all "
  f"{mech['top_ranked_emergency_noncritical']} scenarios the highest-scoring emergency was not GT-critical, and "
  f"in all {mech['all_critical_via_single_extreme_rule_only']} every GT-critical emergency "
  f"({mech['gt_critical_emergencies_in_these']} in total) qualified only through the single-extreme part of "
  "the rule (none had both S ≥ 0.8 and U ≥ 0.8).")
P("This is a diagnostic result, not evidence that the experiment failed. This identifies a limitation of the "
  "balanced continuous priority score when the reference criticality rule allows an emergency to become "
  "critical because of a single extreme severity or urgency value. The AASHRAY score was not modified for this "
  "report; a score term that preserves single extreme values is a possible future direction and would need new "
  "development tuning and a new held-out evaluation.")
ex = WC["example"]
sup = ex["supply"]
supply_total = sum(sup.values())
H2(f"Example: {ex['scenario_id']} ({ex['scarcity']} scarcity, {ex['num_emergencies']} emergencies)", before=6)
P(f"AASHRAY serves the emergencies in the rank order below. Supply: {n(sup['water'])} water, {n(sup['food'])} food, {n(sup['medical_kits'])} medical kit "
  f"({n(supply_total)} units). CDC: FCFS {f4(ex['cdc_fcfs'])}, AASHRAY 0.0000, MILP {f4(ex['cdc_milp'])}.",
  after=4, keep=True)
ex_rows, ex_fill = [], {}
for i, e in enumerate(ex["aashray_order"]):
    crit = e["gt_critical"] == 1
    why = ""
    if crit:
        why = " (U ≥ 0.95)" if e["urgency"] >= 0.95 else " (S ≥ 0.95)" if e["severity"] >= 0.95 else ""
    ex_rows.append([str(e["rank"]), e["emergency_id"].split("-")[-1], f"{e['severity']:.4f}",
                    f"{e['urgency']:.4f}", f"{e['score']:.5f}", ("Yes" + why) if crit else "No",
                    n(e["required"]), n(e["allocated"])])
    if crit:
        ex_fill.update({(i, c): YELLOW for c in range(8)})
check(sum(e["allocated"] for e in ex["aashray_order"]) <= supply_total, "example allocation within supply")
data_table(doc, ["Rank", "Emergency", "S", "U", "P = 0.5S + 0.5U", "GT-critical", "Demand (units)",
                 "Allocated (units)"], ex_rows, [0.72, 0.9, 0.6, 0.6, 1.05, 1.05, 0.95, 1.0],
           align=["center"] * 8, fills=ex_fill, bold_first=False)
first, crit_e = ex["aashray_order"][0], next(e for e in ex["aashray_order"] if e["gt_critical"] == 1)
P(f"Emergency {first['emergency_id'].split('-')[-1]} is not GT-critical but has the highest balanced score, so "
  f"it is served first and absorbs {n(first['allocated'])} of the {n(supply_total)} available units; the "
  f"GT-critical {crit_e['emergency_id'].split('-')[-1]} (U = {crit_e['urgency']:.4f}, "
  f"S = {crit_e['severity']:.4f}) receives nothing. FCFS also covers no GT-critical demand in this scenario.",
  before=6)

# ================================================================= 7. Runtime
H1("7. Computational Efficiency")
P(f"Runtime was measured per scenario in a single process and a single official run (warm-up on "
  f"{len(INTEG['warm_up'])} scenarios) on an {ENV['cpu']} ({ENV['os'].split('-')[0]} "
  f"{ENV['os'].split('-')[1]}, Python {ENV['python_version']}). AASHRAY time is ranking decision plus "
  "allocation; MILP time is model build plus HiGHS solve. **Runtime results are descriptive and "
  "hardware/implementation dependent;** they are not a formal hypothesis test.", keep=True)
aw, ac, mm_ = RT["AASHRAY_raw"], RT["AASHRAY_conservative"], RT["MILP"]
rt_rows = [
    ["Mean (ms)", ms(aw["mean"]), ms(ac["mean"]), ms(mm_["mean"]), times(mm_["mean"] / ac["mean"])],
    ["Median (ms)", ms(aw["median"]), ms(ac["median"]), ms(mm_["median"]), times(RT["speedup_conservative_median"])],
    ["P95 (ms)", ms(aw["p95"]), ms(ac["p95"]), ms(mm_["p95"]), "—"],
    [f"Total, {n(N)} scenarios (s)", f"{aw['total_s']:.2f}", f"{ac['total_s']:.2f}", f"{mm_['total_s']:.2f}",
     times(RT["speedup_conservative_total"])],
]
check(abs(mm_["mean"] / ac["mean"] - RT["speedup_conservative_total"]) < 1e-9, "mean ratio equals total ratio")
data_table(doc, ["Metric", "AASHRAY raw (order-affected)", "AASHRAY conservative", "MILP (build + solve)",
                 "MILP ÷ AASHRAY (conservative)"], rt_rows, [1.55, 1.4, 1.3, 1.25, 1.37],
           align=["left", "center", "center", "center", "center"])
spacer(7)
c = box(doc, fill=YELLOW, edge=YELLOW_EDGE)
add_text(c.paragraphs[0],
         "**Execution-order caveat.** For every scenario the methods ran in the order FCFS → AASHRAY → MILP. "
         "FCFS and AASHRAY call the same allocation service, and the first call in a scenario was slower than "
         f"AASHRAY's second call in {n(RT['first_position_allocation_slower'])} of {n(N)} scenarios, so AASHRAY's "
         "raw allocation time benefits from a warm-cache/order effect. The raw ratios "
         f"({RT['speedup_raw_total']:.2f}× by total, {RT['speedup_raw_median']:.2f}× by median) are therefore not "
         "the main result, and AASHRAY-vs-FCFS timing is not a controlled head-to-head comparison. The "
         "**conservative** estimate charges AASHRAY its own ranking time plus the first-position (FCFS) "
         "allocation time of the same scenario.", color=INK)
P(f"Even under the conservative estimate, the MILP takes about **{times(RT['speedup_conservative_total'])} "
  f"longer in total and {times(RT['speedup_conservative_median'])} longer at the median**, and it is slower "
  f"than conservative AASHRAY in {n(RT['scenarios_milp_slower_conservative'])} of {n(N)} scenarios. AASHRAY's "
  f"mean ranking decision takes {ms(RT['aashray_decision_mean'])} ms; the MILP spends "
  f"{ms(RT['milp_build_mean'])} ms building the model and {ms(RT['milp_solver_mean'])} ms in the solver on "
  "average. No significance test was performed on runtime.", before=7)
figure(doc, CHARTS / "fig10_runtime.png",
       fig_caption("Per-scenario runtime of AASHRAY (raw and conservative) and the MILP benchmark; raw AASHRAY "
                   "timing is affected by execution order."))

# ================================================================= 8. Conclusion
H1("8. Conclusion: What Has Been Shown")
P("The results demonstrate that severity–urgency-based priority allocation substantially improves "
  "critical-demand coverage over arrival-order FCFS under the simulated resource constraints used in this "
  "experiment.", after=6)
for lead, text in (
    ("Primary hypothesis:", f"under the fixed reference criticality rule, AASHRAY mean CDC = "
                            f"{f4(CDC['AASHRAY']['mean'])} vs FCFS = {f4(CDC['FCFS']['mean'])}; H0 is rejected and "
                            "the primary H1 is supported."),
    ("Improvement:", f"{sg4(PAIR['mean'])} absolute / {PAIR['pp']:+.2f} percentage points ({REL:+.1f}% relative)."),
    ("Statistical significance:", f"paired sign-flip permutation p = {P_PERM} (the minimum attainable with "
                                  f"{n(PERM['permutations'])} permutations); the secondary Wilcoxon test agrees."),
    ("95% CI:", f"{CI} (paired bootstrap, {n(BOOT['resamples'])} resamples)."),
    ("Scarcity effect:", f"HIGH scarcity shows the largest benefit: {f4(HIGH['cdc']['AASHRAY'])} vs "
                         f"{f4(HIGH['cdc']['FCFS'])} CDC ({sg4(HIGH['diff_mean'])}); at LOW scarcity all methods "
                         "reach full GT-critical coverage."),
    ("Optimization:", f"AASHRAY reaches the exact MILP optimum in {pc(OPT['exact_optimum_pct'])} of scenarios and is "
                      f"within 10% in {pc(OPT['within_10pct_pct'])}; it is not optimal in every scenario "
                      f"({pc(HIGH['exact_pct'])} exact under HIGH scarcity, and {WC['count']} HIGH-scarcity "
                      "scenarios with CDC = 0)."),
    ("Computational efficiency:", "AASHRAY remains substantially cheaper computationally than MILP under the "
                                  f"conservative runtime comparison (≈{times(RT['speedup_conservative_total'])} by "
                                  f"total, ≈{times(RT['speedup_conservative_median'])} by median; descriptive and "
                                  "hardware/implementation dependent)."),
    ("Important qualification:", "AASHRAY's final policy is exactly 0.5S + 0.5U; the geometric component was not "
                                 "part of the selected final ranking."),
    ("Limitation:", "the current optimization model does not include routing, vehicles, temporal constraints or "
                    "compatibility."),
):
    bullet(doc, f"**{lead}** {text}")

H2("Limitations", before=8)
limitations = [
    "The scenarios are synthetic rather than real operational disaster events.",
    "GT-criticality is a fixed simulation reference rule derived from the same S and U variables as the "
    "priority score, not an externally validated clinical or operational standard.",
    "The current allocator has no vehicle, routing, temporal, compatibility or geographic constraints.",
    "Therefore the MILP benchmark represents an allocation-only optimization problem, whose optimum has a "
    "closed form.",
    "The selected AASHRAY policy is linear: P = 0.5S + 0.5U.",
    "The experiment does not establish that the geometric priority formulation is superior.",
    "The runtime comparison has an execution-order/warm-cache limitation; only the conservative estimate is "
    "used for the main runtime conclusion.",
    f"AASHRAY is not optimal in every scenario, particularly under HIGH scarcity ({pc(HIGH['exact_pct'])} exact; "
    f"{WC['count']} scenarios with CDC = 0).",
    "The result demonstrates resource-allocation performance, not the performance of the entire end-to-end "
    "AASHRAY pipeline.",
]
for i, text in enumerate(limitations, start=1):
    bullet(doc, text, symbol=f"{i}.", indent=0.3).paragraph_format.keep_with_next = i == len(limitations)
OVERALL_1 = (f"Under the fixed reference criticality rule used in this experiment, AASHRAY substantially improves "
             f"critical-demand coverage over arrival-order FCFS. Mean CDC increased from {f4(CDC['FCFS']['mean'])} "
             f"to {f4(CDC['AASHRAY']['mean'])}, an absolute improvement of {f4(PAIR['mean'])}. The improvement is "
             f"especially pronounced under HIGH resource scarcity, where CDC increased from "
             f"{f4(HIGH['cdc']['FCFS'])} to {f4(HIGH['cdc']['AASHRAY'])}. AASHRAY also reaches the MILP optimum in "
             f"{pc(OPT['exact_optimum_pct'])} of scenarios and remains within 10% of the optimum in "
             f"{pc(OPT['within_10pct_pct'])} of scenarios.")
OVERALL_2 = ("These results support the effectiveness of the AASHRAY resource-allocation component under the "
             "simulated allocation model and reference criticality criterion. They should not be interpreted as "
             "validation of real-world disaster-response performance, since the scenarios and reference "
             "criticality rule are synthetic and the current allocation model does not include routing, "
             "vehicle, temporal, geographic, or resource-compatibility constraints.")
overall = P(f"**Overall: {OVERALL_1}**", before=8, after=4)
overall.paragraph_format.keep_together = True
overall.paragraph_format.keep_with_next = True
overall2 = P(OVERALL_2, after=4)
overall2.paragraph_format.keep_together = True

# ================================================================= Appendix
H1("Appendix: Provenance and Notes on Reported Values")
small = 8.5
P("**Source of truth.** experiments/resource_allocation_final/ — results/final_scenario_results.csv, "
  "final_summary.json, final_statistical_tests.json, final_win_tie_loss.csv, validation_report.json, "
  "gate_report.json, run_metadata.json, environment.json, dataset_freeze.json, generator_equivalence.json, "
  "file_hash_manifest.json; config/final_config.json; data/final_12000_scenarios.json. Official run "
  f"{INTEG['run_id']}, started {INTEG['run_started'][:10]} {INTEG['run_started'][11:19]} UTC; repository commit "
  f"{D['git_commit'][:7]} (the experiment folders are untracked; file_hash_manifest.json identifies them).",
  size=small)
P("**Report artefacts.** reports/resource_allocation_hypothesis_report/scripts/ (prepare_report_data.py, "
  "make_charts.py, build_report.py). Charts are drawn from final_scenario_results.csv or from the bootstrap "
  f"regenerated with seed {BOOT['seed']} (reproduces the stored interval exactly).", size=small)
P("**Values that differ from the report brief** (the validated result files were used):", size=small, after=2)
notes = [
    f"Scarcity table, 'AASHRAY−MILP' column: the brief's {f4(MOD['mean_relative_gap'])} / "
    f"{f4(HIGH['mean_relative_gap'])} are mean relative optimality gaps; the difference of means is "
    f"{sg4(diff_m)} / {sg4(diff_h)}. The column is labelled as the mean optimality gap.",
    f"Within-5% rate: the brief's 90.1% is {pc(OPT['within_5pct_pct'])} exactly ({n(OPT['within_5_count'])} / "
    f"{n(N)}); rates are reported to two decimals (86.7%, 88.4% and 91.5% in the brief appear as "
    f"{pc(OPT['exact_optimum_pct'])}, {pc(OPT['within_1pct_pct'])} and {pc(OPT['within_10pct_pct'])}).",
    f"Runtime means: the brief's 0.248 ms (AASHRAY) and 2.473 ms (MILP) are double-rounded; exact values "
    f"{aw['mean']:.6f} and {mm_['mean']:.6f} ms, i.e. {ms(aw['mean'])} and {ms(mm_['mean'])} ms (the experiment "
    f"README, left unchanged, has the same rounding). That AASHRAY value is the raw, order-affected mean; the "
    f"conservative mean is {ms(ac['mean'])} ms. Both are shown and labelled.",
]
for t in notes:
    bullet(doc, t, size=small, after=2)

# ================================================================= Save and export
cp = doc.core_properties
cp.title = TITLE
cp.subject = "Final pre-registered 12,000-scenario resource-allocation experiment: FCFS vs AASHRAY vs MILP"
cp.author = "AASHRAY project"
cp.keywords = "AASHRAY; hypothesis test; resource allocation; critical demand coverage; MILP"
cp.comments = "Generated by reports/resource_allocation_hypothesis_report/scripts/build_report.py"
doc.save(DOCX_PATH)
print(f"wrote {DOCX_PATH.name}")


def export_pdf():
    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()
    word = win32com.client.DispatchEx("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    try:
        d = word.Documents.Open(str(DOCX_PATH), ReadOnly=True, AddToRecentFiles=False, Visible=False)
        d.Fields.Update()
        d.ExportAsFixedFormat(OutputFileName=str(PDF_PATH), ExportFormat=17, OpenAfterExport=False,
                              OptimizeFor=0, Range=0, IncludeDocProps=True, KeepIRM=True,
                              CreateBookmarks=1, DocStructureTags=True, BitmapMissingFonts=True,
                              UseISO19005_1=False)
        pages = d.ComputeStatistics(2)
        d.Close(SaveChanges=0)
    finally:
        word.Quit()
    print(f"wrote {PDF_PATH.name} ({pages} pages)")


if "--no-pdf" not in sys.argv:
    export_pdf()
