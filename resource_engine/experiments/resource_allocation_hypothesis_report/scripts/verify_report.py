"""Quality checks for the generated hypothesis-report PDF.

Recomputes the headline numbers directly from the raw scenario table (independently of
report_data.json), then checks that the PDF text contains them, that every page has the
footer, that all ten figure captions appear in order, that the required statements are
present verbatim, and that none of the prohibited claims appear.

Usage (from the repository root):

    python reports/resource_allocation_hypothesis_report/scripts/verify_report.py
"""

import csv
import json
import re
import statistics
import sys
from pathlib import Path

from pypdf import PdfReader

REPORT_ROOT = Path(__file__).resolve().parents[1]
REPO = REPORT_ROOT.parents[1]
RESULTS = REPO / "experiments" / "resource_allocation_final" / "results"
PDF = REPORT_ROOT / "AASHRAY_Resource_Allocation_Hypothesis_Report.pdf"
TITLE = "AASHRAY: Hypothesis Testing Report — Impact-Driven Resource Allocation"
TIE = 1e-9

failures = []
passes = 0


def check(ok, label):
    global passes
    if ok:
        passes += 1
    else:
        failures.append(label)


# ---------------------------------------------------------------- independent recomputation
with (RESULTS / "final_scenario_results.csv").open(encoding="utf-8", newline="") as f:
    rows = list(csv.DictReader(f))
num = lambda r, k: float(r[k])
n = len(rows)
check(n == 12000, "scenario rows = 12,000")
cdc = {m: statistics.fmean(num(r, f"CDC_{m}") for r in rows) for m in ("FCFS", "AASHRAY", "MILP")}
delta = [num(r, "CDC_AASHRAY") - num(r, "CDC_FCFS") for r in rows]
wins = sum(d > TIE for d in delta)
ties = sum(abs(d) <= TIE for d in delta)
losses = sum(d < -TIE for d in delta)
check(wins + ties + losses == n, "wins + ties + losses = n")
check((wins, ties, losses) == (5656, 5996, 348), "W/T/L counts 5,656 / 5,996 / 348")
levels = {lvl: [r for r in rows if r["scarcity"] == lvl] for lvl in ("LOW", "MODERATE", "HIGH")}
check([len(v) for v in levels.values()] == [1200, 4800, 6000], "scarcity counts 1,200 / 4,800 / 6,000")
check(sum(len(v) for v in levels.values()) == n, "scarcity counts sum to n")
exact = sum(abs(num(r, "CDC_MILP") - num(r, "CDC_AASHRAY")) <= TIE for r in rows)
rel_gap = [(num(r, "CDC_MILP") - num(r, "CDC_AASHRAY")) / num(r, "CDC_MILP") for r in rows]
within = {k: sum(g <= k / 100 + TIE for g in rel_gap) for k in (1, 5, 10)}
tdc_f = statistics.fmean(num(r, "TDC_FCFS") for r in rows)
check(all(r["TDC_FCFS"] == r["TDC_AASHRAY"] for r in rows), "TDC identical per scenario")
worst = [r for r in rows if num(r, "CDC_AASHRAY") == 0 and num(r, "CDC_MILP") > 0]
check(len(worst) == 59 and all(r["scarcity"] == "HIGH" for r in worst), "59 worst cases, all HIGH")
aashray_rt = [num(r, "aashray_total_time_ms") for r in rows]
milp_rt = [num(r, "milp_total_time_ms") for r in rows]
conservative_rt = [num(r, "aashray_decision_time_ms") + num(r, "fcfs_allocation_time_ms") for r in rows]
speedup_total = sum(milp_rt) / sum(conservative_rt)
speedup_median = statistics.median(milp_rt) / statistics.median(conservative_rt)
check(round(speedup_total, 1) == 5.6 and round(speedup_median, 1) == 4.8, "conservative speedups 5.6x / 4.8x")
stats = json.loads((RESULTS / "final_statistical_tests.json").read_text(encoding="utf-8"))
perm_p = stats["primary_permutation_test"]["p_value"]
ci = stats["paired_bootstrap_ci"]["confidence_interval"]

pct = lambda c: f"{100 * c / n:.2f}%"
expected = {
    "mean CDC FCFS": f"{cdc['FCFS']:.4f}",
    "mean CDC AASHRAY": f"{cdc['AASHRAY']:.4f}",
    "mean CDC MILP": f"{cdc['MILP']:.4f}",
    "mean delta": f"+{statistics.fmean(delta):.4f}",
    "bootstrap CI": f"[{ci[0]:.4f}, {ci[1]:.4f}]",
    "permutation p": f"{perm_p:.4e}".split("e")[0],
    "win share": pct(wins), "tie share": pct(ties), "loss share": pct(losses),
    "wins": f"{wins:,}", "ties": f"{ties:,}",
    "exact optimum": pct(exact), "within 1%": pct(within[1]),
    "within 5%": pct(within[5]), "within 10%": pct(within[10]),
    "TDC": f"{tdc_f:.4f}",
    "AASHRAY mean runtime": f"{statistics.fmean(aashray_rt):.3f}",
    "MILP mean runtime": f"{statistics.fmean(milp_rt):.3f}",
    "AASHRAY total runtime": f"{sum(aashray_rt) / 1000:.2f}",
    "MILP total runtime": f"{sum(milp_rt) / 1000:.2f}",
    "conservative AASHRAY mean runtime": f"{statistics.fmean(conservative_rt):.3f}",
    "AASHRAY P95 runtime": f"{statistics.quantiles(aashray_rt, n=100, method='inclusive')[94]:.3f}",
    "MILP P95 runtime": f"{statistics.quantiles(milp_rt, n=100, method='inclusive')[94]:.3f}",
    "dataset SHA-256": json.loads((RESULTS / "dataset_freeze.json").read_text(encoding="utf-8"))["sha256"],
}
for lvl, part in levels.items():
    for m in ("FCFS", "AASHRAY", "MILP"):
        expected[f"{lvl} CDC {m}"] = f"{statistics.fmean(num(r, f'CDC_{m}') for r in part):.4f}"
expected["HIGH difference"] = f"+{statistics.fmean(num(r, 'CDC_AASHRAY') - num(r, 'CDC_FCFS') for r in levels['HIGH']):.4f}"

# ---------------------------------------------------------------- PDF text
reader = PdfReader(str(PDF))
pages = [p.extract_text() or "" for p in reader.pages]
flat = re.sub(r"\s+", " ", " ".join(pages))
check(7 <= len(pages) <= 10, f"page count within 7-10 (got {len(pages)})")
for i, text in enumerate(pages, start=1):
    check(f"AASHRAY | Hypothesis Testing Report | Page {i}" in re.sub(r"\s+", " ", text), f"footer on page {i}")
for i, text in enumerate(pages[1:], start=2):
    check(text.lstrip().startswith("AASHRAY"), f"running header on page {i}")
for label, value in expected.items():
    check(value in flat, f"PDF contains {label} = {value}")
for value in ("0.603", "0.721", "Probability of superiority".lower(), "20261209", "20261210", "20261211",
              "35/35", "37/37", "5.6×", "4.8×", "+0.0274", "86.66%", "90.05%", "348 (2.90%)", "0.0350", "74.70%",
              "1,180 (24.58%)", "3,579 (74.56%)", "41 (0.85%)", "4,476 (74.60%)", "1,217 (20.28%)",
              "307 (5.12%)", "1,200 (100.00%)", "0.440", "+0.4009"):
    check(value in flat.lower() if value.islower() else value in flat, f"PDF contains {value}")

required = [
    "The parameter search selected a policy mathematically equivalent to a balanced linear severity–urgency "
    "score, P = 0.5S + 0.5U. The geometric component therefore does not contribute to the final experimental "
    "policy.",
    "The AASHRAY priority score and the reference criticality rule are separate scoring mechanisms. The "
    "reference criticality rule is fixed independently of the AASHRAY configuration and allocation method, but "
    "it is derived from the same severity (S) and urgency (U) variables used by the priority score.",
    "This is a predefined simulation reference criterion for evaluating allocation priority; it is not an "
    "externally validated operational or clinical definition of real-world criticality.",
    "Under the fixed reference criticality rule used in this experiment, AASHRAY substantially improves "
    "critical-demand coverage compared with FCFS.",
    "The results demonstrate that severity–urgency-based priority allocation substantially improves "
    "critical-demand coverage over arrival-order FCFS under the simulated resource constraints used in this "
    "experiment.",
    "The MILP is used as an optimization benchmark and correctness oracle for the current allocation "
    "formulation. It is not treated as a competing heuristic.",
    "The benefit of priority-based allocation becomes most pronounced when resources are scarce.",
    "The median paired difference is 0 because the distribution contains 5,996 exact ties; this does not imply "
    "that AASHRAY has no effect. The mean difference is +0.2114.",
    "This identifies a limitation of the balanced continuous priority score when the reference criticality rule "
    "allows an emergency to become critical because of a single extreme severity or urgency value.",
    "Runtime results are descriptive and hardware/implementation dependent",
    "Under the fixed reference criticality rule used in this experiment, AASHRAY substantially improves "
    "critical-demand coverage over arrival-order FCFS. Mean CDC increased from 0.7363 to 0.9477, an absolute "
    "improvement of 0.2114. The improvement is especially pronounced under HIGH resource scarcity, where CDC "
    "increased from 0.4958 to 0.8968. AASHRAY also reaches the MILP optimum in 86.66% of scenarios and remains "
    "within 10% of the optimum in 91.50% of scenarios.",
    "These results support the effectiveness of the AASHRAY resource-allocation component under the simulated "
    "allocation model and reference criticality criterion. They should not be interpreted as validation of "
    "real-world disaster-response performance, since the scenarios and reference criticality rule are synthetic "
    "and the current allocation model does not include routing, vehicle, temporal, geographic, or "
    "resource-compatibility constraints.",
]
def dashes(s):
    # Text extraction inserts spaces where a line wraps at a hyphen or en dash.
    return re.sub(r"\s*([–-])\s*", r"\1", s)


for text in required:
    check(dashes(text) in dashes(flat), f"required statement present: {text[:60]}...")
for heading in ("1. Hypothesis", "2. Results at a Glance", "3. Scarcity-Stratified Results",
                "4. Statistical Testing", "5. Optimization Benchmark", "6. Failure / Worst-Case Analysis",
                "7. Computational Efficiency", "8. Conclusion: What Has Been Shown", "Limitations"):
    check(heading in flat, f"section present: {heading}")

positions = [flat.find(f"Figure {k}. ") for k in range(1, 11)]
check(all(p >= 0 for p in positions), "captions Figure 1-10 present")
check(positions == sorted(positions), "figure captions appear in numeric order")
check(all(flat.count(f"Figure {k}. ") == 1 for k in range(1, 11)), "each caption appears once")

# A p-value written as zero ("p = 0", "p = 0.0"); a lower-case p not preceded by a letter, so
# subscripted names such as CDC_MILP = 0 do not match.
check(not re.search(r"(?<![A-Za-z])p ?= ?0(?:\.0+)?(?![\d.])", flat), "no p-value reported as zero")
forbidden = ["geometric priority model was superior", "AASHRAY is optimal",
             "AASHRAY is always better", "10× faster", "10x faster", "difficult combinatorial optimization",
             "end-to-end system has been validated", "rule is objectively correct",
             "proves real-world", "strongly supported", "independent of α", "AASHRAY improves total resource"]
for phrase in forbidden:
    check(phrase.lower() not in flat.lower(), f"forbidden phrase absent: {phrase}")

meta = reader.metadata
check(meta is not None and meta.title == TITLE, f"PDF title metadata ({meta.title if meta else None})")
fonts_embedded = True
for page in reader.pages:
    for font in (page.get("/Resources", {}).get("/Font", {}) or {}).values():
        font = font.get_object()
        desc = font.get("/FontDescriptor")
        if desc is None and "/DescendantFonts" in font:
            desc = font["/DescendantFonts"][0].get_object().get("/FontDescriptor")
        if desc is not None:
            desc = desc.get_object()
            if not any(k in desc for k in ("/FontFile", "/FontFile2", "/FontFile3")):
                fonts_embedded = False
check(fonts_embedded, "all fonts embedded")

print(f"{passes} checks passed, {len(failures)} failed")
for label in failures:
    print("  FAIL:", label)
sys.exit(1 if failures else 0)
