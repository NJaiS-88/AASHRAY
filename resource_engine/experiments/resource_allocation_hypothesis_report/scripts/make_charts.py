"""Generate the report figures from the validated final results.

Every plotted value is read from experiments/resource_allocation_final/
results/final_scenario_results.csv or from data/report_data.json (itself
derived from the result files). Nothing is typed in by hand.

Figures are drawn at their printed size so fonts print at true size.
Palette (validated with the dataviz validator, light mode, all checks pass):
FCFS #d26b12, AASHRAY #2f6fd6, MILP #0d9488.
"""

import csv
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.ticker import FuncFormatter, PercentFormatter  # noqa: E402

REPORT_ROOT = Path(__file__).resolve().parents[1]
REPO = REPORT_ROOT.parents[1]
CSV_PATH = REPO / "experiments" / "resource_allocation_final" / "results" / "final_scenario_results.csv"
DATA = json.loads((REPORT_ROOT / "data" / "report_data.json").read_text(encoding="utf-8"))
OUT = REPORT_ROOT / "charts"
OUT.mkdir(exist_ok=True)

COLOR = {"FCFS": "#d26b12", "AASHRAY": "#2f6fd6", "MILP": "#0d9488"}
INK, INK_2, MUTED, GRID, EDGE, TIE_GREY = "#0f172a", "#334155", "#64748b", "#e5e7eb", "#cbd5e1", "#94a3b8"
GAP_RAMP = ["#dbeafe", "#93c5fd", "#4f8fe8", "#2556b8", "#132f6b"]
FULL_W, HALF_W = 6.6, 3.25
LEVELS = ("LOW", "MODERATE", "HIGH")

plt.rcParams.update({
    "font.family": "Arial", "font.size": 8.5, "axes.titlesize": 9.5, "axes.titleweight": "bold",
    "axes.titlecolor": INK, "axes.labelsize": 8.5, "axes.labelcolor": INK_2, "xtick.labelsize": 8,
    "ytick.labelsize": 8, "xtick.color": INK_2, "ytick.color": INK_2, "legend.fontsize": 7.8,
    "legend.frameon": False, "axes.edgecolor": EDGE, "axes.linewidth": 0.8, "axes.spines.top": False,
    "axes.spines.right": False, "axes.grid": True, "axes.grid.axis": "y", "grid.color": GRID,
    "grid.linewidth": 0.6, "axes.axisbelow": True, "figure.facecolor": "white", "savefig.dpi": 220,
    "savefig.bbox": "tight", "savefig.pad_inches": 0.04,
})


def load_rows():
    with open(CSV_PATH, encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


ROWS = load_rows()


def column(name, rows=ROWS):
    return np.array([float(r[name]) for r in rows])


def save(fig, name):
    fig.savefig(OUT / name)
    plt.close(fig)


def bar_labels(ax, bars, fmt, pad=0.012, size=7.8):
    top = ax.get_ylim()[1]
    for bar in bars:
        h = bar.get_height()
        ax.text(bar.get_x() + bar.get_width() / 2, h + top * pad, fmt(h),
                ha="center", va="bottom", fontsize=size, color=INK)


def break_marks(top_ax, bottom_ax):
    d = 0.012
    kw = dict(color=EDGE, clip_on=False, linewidth=0.9)
    top_ax.plot((-d, +d), (-d * 3, +d * 3), transform=top_ax.transAxes, **kw)
    bottom_ax.plot((-d, +d), (1 - d * 3, 1 + d * 3), transform=bottom_ax.transAxes, **kw)


# ---------------------------------------------------------------- Figure 1
def fig_mean_cdc():
    fig, ax = plt.subplots(figsize=(HALF_W, 2.45))
    methods = ("FCFS", "AASHRAY", "MILP")
    means = [column(f"CDC_{m}").mean() for m in methods]
    bars = ax.bar(methods, means, width=0.56, color=[COLOR[m] for m in methods], edgecolor="white", linewidth=1)
    ax.set_ylim(0, 1.1)
    ax.set_yticks(np.arange(0, 1.01, 0.2))
    ax.set_ylabel("Mean CDC")
    ax.set_title("Mean Critical Demand Coverage")
    bar_labels(ax, bars, lambda v: f"{v:.4f}")
    save(fig, "fig01_mean_cdc.png")


# ---------------------------------------------------------------- Figure 2
def fig_win_tie_loss():
    w = DATA["win_tie_loss"]["ALL"]
    labels = ["AASHRAY wins", "Ties", "FCFS wins"]
    counts = [int(w["aashray_wins"]), int(w["ties"]), int(w["fcfs_wins"])]
    pct = [w["aashray_win_pct"], w["tie_pct"], w["fcfs_win_pct"]]
    fig, ax = plt.subplots(figsize=(HALF_W, 2.45))
    bars = ax.bar(labels, pct, width=0.56, color=[COLOR["AASHRAY"], TIE_GREY, COLOR["FCFS"]],
                  edgecolor="white", linewidth=1)
    ax.set_ylim(0, 60)
    ax.yaxis.set_major_formatter(PercentFormatter(decimals=0))
    ax.set_ylabel("Share of scenarios")
    ax.set_title("Paired Outcome: AASHRAY vs FCFS")
    for bar, c, p in zip(bars, counts, pct):
        ax.text(bar.get_x() + bar.get_width() / 2, p + 1.2, f"{p:.2f}%\n({c:,})", ha="center",
                va="bottom", fontsize=7.6, color=INK)
    ax.text(0.99, 0.93, "tie: |Δ| ≤ 1e-9", transform=ax.transAxes, ha="right", fontsize=7, color=MUTED)
    save(fig, "fig02_win_tie_loss.png")


# ---------------------------------------------------------------- Figure 3
def fig_cdc_by_scarcity():
    fig, ax = plt.subplots(figsize=(FULL_W, 2.4))
    x = np.arange(len(LEVELS))
    width = 0.25
    for i, m in enumerate(("FCFS", "AASHRAY", "MILP")):
        vals = [column(f"CDC_{m}", [r for r in ROWS if r["scarcity"] == lvl]).mean() for lvl in LEVELS]
        bars = ax.bar(x + (i - 1) * width, vals, width=width * 0.94, color=COLOR[m], label=m,
                      edgecolor="white", linewidth=1)
        for bar, v in zip(bars, vals):
            ax.text(bar.get_x() + bar.get_width() / 2, v + 0.015, f"{v:.4f}", ha="center", va="bottom",
                    fontsize=7.2, color=INK)
    counts = DATA["dataset"]["scarcity_counts"]
    ax.set_xticks(x, [f"{lvl}\n(n = {counts[lvl]:,})" for lvl in LEVELS])
    ax.set_ylim(0, 1.26)
    ax.set_yticks(np.arange(0, 1.01, 0.2))
    ax.set_ylabel("Mean CDC")
    ax.set_title("Critical Demand Coverage by Resource Scarcity")
    ax.legend(loc="upper left", ncol=3, bbox_to_anchor=(0.0, 1.0))
    # Bracket from the FCFS bar to the AASHRAY bar in the HIGH group.
    high = DATA["scarcity"]["HIGH"]
    x_f, x_a = 2 - width, 2
    y_f, y_a, y_top = high["cdc"]["FCFS"] + 0.115, high["cdc"]["AASHRAY"] + 0.115, 1.085
    ax.plot([x_f, x_f, x_a, x_a], [y_f, y_top, y_top, y_a], color=INK, linewidth=0.9)
    ax.text((x_f + x_a) / 2, y_top + 0.012, f"AASHRAY − FCFS = +{high['diff_mean']:.4f}", ha="center",
            va="bottom", fontsize=8, fontweight="bold", color=INK)
    save(fig, "fig03_cdc_by_scarcity.png")


# ---------------------------------------------------------------- Figure 4
def fig_delta_distribution():
    delta = column("aashray_minus_fcfs_CDC")
    ties = np.abs(delta) <= 1e-9
    nonzero = delta[~ties]
    edges = np.arange(-1.0, 1.0001, 0.05)
    counts, _ = np.histogram(nonzero, bins=edges)
    centers = (edges[:-1] + edges[1:]) / 2
    tie_count = int(ties.sum())

    fig, (top, bottom) = plt.subplots(2, 1, figsize=(FULL_W, 2.5), sharex=True,
                                      gridspec_kw={"height_ratios": [1, 3.2], "hspace": 0.08})
    for ax in (top, bottom):
        colors = [COLOR["AASHRAY"] if c > 0 else COLOR["FCFS"] for c in centers]
        ax.bar(centers, counts, width=0.05 * 0.92, color=colors, edgecolor="white", linewidth=0.4)
        ax.bar([0], [tie_count], width=0.035, color=TIE_GREY, edgecolor="white", linewidth=0.4)
        ax.axvline(0, color=INK_2, linewidth=0.8)
    bottom.axvline(delta.mean(), color=INK, linewidth=1.1, linestyle="--")
    top.set_ylim(tie_count - 400, tie_count + 250)
    bottom.set_ylim(0, counts.max() * 1.22)
    top.spines["bottom"].set_visible(False)
    top.tick_params(axis="x", length=0)
    break_marks(top, bottom)
    top.text(0.05, tie_count - 120, f"← Ties at Δ = 0: {tie_count:,} ({100 * tie_count / delta.size:.2f}%)",
             fontsize=7.6, color=INK, va="center", zorder=5,
             bbox=dict(boxstyle="square,pad=0.15", facecolor="white", edgecolor="none"))
    top.text(-0.04, tie_count - 120, "median Δ = 0", fontsize=7.6, color=INK_2, ha="right", va="center")
    bottom.text(delta.mean() + 0.02, counts.max() * 1.1, f"mean Δ = {delta.mean():.4f}", fontsize=7.6,
                color=INK, va="center")
    bottom.set_xlim(-1.05, 1.05)
    bottom.set_xlabel("Paired difference Δ = CDC(AASHRAY) − CDC(FCFS)")
    bottom.set_ylabel("Scenarios")
    top.set_title("Distribution of Paired CDC Differences (n = 12,000)")
    from matplotlib.patches import Patch
    bottom.legend(handles=[Patch(color=COLOR["AASHRAY"], label=f"AASHRAY better (Δ > 0): {int((delta > 1e-9).sum()):,}"),
                           Patch(color=TIE_GREY, label=f"Tie: {tie_count:,}"),
                           Patch(color=COLOR["FCFS"], label=f"FCFS better (Δ < 0): {int((delta < -1e-9).sum()):,}")],
                  loc="upper left", bbox_to_anchor=(0.0, 0.86))
    save(fig, "fig04_delta_distribution.png")


# ---------------------------------------------------------------- Figure 5
def fig_bootstrap():
    means = np.load(REPORT_ROOT / "data" / "bootstrap_means.npy")
    lower, upper = DATA["bootstrap"]["confidence_interval"]
    observed = DATA["permutation"]["statistic"]
    fig, (full, zoom) = plt.subplots(1, 2, figsize=(FULL_W, 2.15), gridspec_kw={"width_ratios": [1, 1.25], "wspace": 0.28})

    full.hist(means, bins=60, color=COLOR["AASHRAY"], linewidth=0)
    full.axvline(0, color=INK_2, linewidth=0.9)
    full.text(0.004, full.get_ylim()[1] * 0.92, "H0 boundary\n(μΔ = 0)", fontsize=7.2, color=INK_2, va="top")
    full.set_xlim(-0.01, 0.24)
    full.set_title("Full scale, including 0")
    full.set_xlabel("Bootstrap mean of Δ")
    full.set_ylabel("Resamples")

    zoom.hist(means, bins=60, color=COLOR["AASHRAY"], edgecolor="white", linewidth=0.2, alpha=0.9)
    for value, style, label in ((lower, ":", f"2.5%: {lower:.4f}"), (upper, ":", f"97.5%: {upper:.4f}"),
                                (observed, "--", f"observed: {observed:.4f}")):
        zoom.axvline(value, color=INK, linewidth=1.0, linestyle=style)
    ymax = zoom.get_ylim()[1]
    zoom.text(lower, ymax * 1.01, f"{lower:.4f}", ha="center", va="bottom", fontsize=7.2, color=INK)
    zoom.text(upper, ymax * 1.01, f"{upper:.4f}", ha="center", va="bottom", fontsize=7.2, color=INK)
    zoom.text(upper + 0.0012, ymax * 0.62, f"observed mean\n{observed:.4f}\n(dashed line)", ha="left",
              va="center", fontsize=7.2, color=INK)
    zoom.set_title("Zoom: 95% percentile interval", pad=12)
    zoom.set_xlabel("Bootstrap mean of Δ (10,000 paired resamples)")
    save(fig, "fig05_bootstrap.png")


# ---------------------------------------------------------------- Figure 6
def fig_gap_distribution():
    gap = column("aashray_milp_gap_relative")
    exact = column("aashray_milp_gap_absolute") <= 1e-9
    positive = gap[~exact]
    edges = np.arange(0, 1.0001, 0.025)
    counts, _ = np.histogram(positive, bins=edges)
    centers = (edges[:-1] + edges[1:]) / 2
    exact_count = int(exact.sum())
    opt = DATA["optimality"]

    fig, (top, bottom) = plt.subplots(2, 1, figsize=(FULL_W, 2.4), sharex=True,
                                      gridspec_kw={"height_ratios": [1, 3.0], "hspace": 0.08})
    for ax in (top, bottom):
        ax.bar(centers, counts, width=0.025 * 0.9, color=COLOR["AASHRAY"], edgecolor="white", linewidth=0.3)
        ax.bar([-0.0125], [exact_count], width=0.02, color=TIE_GREY, edgecolor="white", linewidth=0.3)
        ax.axvline(0, color=INK_2, linewidth=0.8)
        ax.axvline(opt["mean_gap"], color=INK, linewidth=1.1, linestyle="--")
        ax.axvline(opt["p95_gap"], color=INK, linewidth=1.0, linestyle=":")
    top.set_ylim(exact_count - 500, exact_count + 300)
    bottom.set_ylim(0, counts.max() * 1.3)
    top.spines["bottom"].set_visible(False)
    top.tick_params(axis="x", length=0)
    break_marks(top, bottom)
    top.text(opt["p95_gap"] + 0.03, exact_count - 150,
             f"← Exact optimum (gap = 0): {exact_count:,} ({opt['exact_optimum_pct']:.2f}%);  median gap = 0",
             fontsize=7.6, color=INK, va="center")
    bottom.text(opt["mean_gap"] + 0.008, counts.max() * 1.18, f"mean = {opt['mean_gap']:.4f}", fontsize=7.4, color=INK)
    bottom.text(opt["p95_gap"] + 0.008, counts.max() * 1.18, f"P95 = {opt['p95_gap']:.4f}", fontsize=7.4, color=INK)
    bottom.set_xlim(-0.04, 1.02)
    bottom.set_xlabel("Relative optimality gap = (CDC(MILP) − CDC(AASHRAY)) / CDC(MILP)")
    bottom.set_ylabel("Scenarios")
    top.set_title(f"AASHRAY Optimality Gap (n = 12,000; {12000 - exact_count:,} scenarios with a gap > 0)")
    save(fig, "fig06_gap_distribution.png")


# ---------------------------------------------------------------- Figure 7
def fig_gap_by_scarcity():
    labels = ["Exact optimum", "> 0 to 1%", "1–5%", "5–10%", "> 10%"]
    keys = ["exact", "le_1pct", "1_to_5pct", "5_to_10pct", "gt_10pct"]
    fig, ax = plt.subplots(figsize=(FULL_W, 1.95))
    y = np.arange(len(LEVELS))[::-1]
    left = np.zeros(len(LEVELS))
    for key, label, color in zip(keys, labels, GAP_RAMP):
        shares = np.array([100 * DATA["scarcity"][lvl]["gap_bins"][key] / DATA["scarcity"][lvl]["n"] for lvl in LEVELS])
        ax.barh(y, shares, left=left, height=0.58, color=color, edgecolor="white", linewidth=1.2, label=label)
        for yi, l, s in zip(y, left, shares):
            if s >= 4:
                ax.text(l + s / 2, yi, f"{s:.1f}%", ha="center", va="center", fontsize=7.4,
                        color=INK if color in GAP_RAMP[:2] else "white")
        left += shares
    ax.set_yticks(y, [f"{lvl}  (mean gap {DATA['scarcity'][lvl]['mean_relative_gap']:.4f})" for lvl in LEVELS])
    ax.set_xlim(0, 100)
    ax.xaxis.set_major_formatter(PercentFormatter(decimals=0))
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", color=GRID, linewidth=0.6)
    ax.set_xlabel("Share of scenarios by relative optimality gap")
    ax.set_title("AASHRAY Optimality Gap by Scarcity Level")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.3), ncol=5, handlelength=1.2, columnspacing=1.0)
    save(fig, "fig07_gap_by_scarcity.png")


# ---------------------------------------------------------------- Figure 8
def fig_optimality_rates():
    opt = DATA["optimality"]
    labels = ["Exact\noptimum", "Within\n1%", "Within\n5%", "Within\n10%"]
    values = [opt["exact_optimum_pct"], opt["within_1pct_pct"], opt["within_5pct_pct"], opt["within_10pct_pct"]]
    counts = [opt["exact_count"], opt["within_1_count"], opt["within_5_count"], opt["within_10_count"]]
    fig, ax = plt.subplots(figsize=(HALF_W, 2.5))
    bars = ax.bar(labels, values, width=0.56, color=COLOR["AASHRAY"], edgecolor="white", linewidth=1)
    ax.set_ylim(0, 110)
    ax.yaxis.set_major_formatter(PercentFormatter(decimals=0))
    ax.set_ylabel("Share of scenarios")
    ax.set_title("AASHRAY Reaching the MILP Optimum")
    for bar, v, c in zip(bars, values, counts):
        ax.text(bar.get_x() + bar.get_width() / 2, v + 1.5, f"{v:.2f}%\n({c:,})", ha="center", va="bottom",
                fontsize=7.2, color=INK)
    save(fig, "fig08_optimality_rates.png")


# ---------------------------------------------------------------- Figure 9
def fig_scatter():
    milp = column("CDC_MILP")
    aashray = column("CDC_AASHRAY")
    exact = column("aashray_milp_gap_absolute") <= 1e-9
    fig, ax = plt.subplots(figsize=(HALF_W, 2.75))
    ax.scatter(milp[~exact], aashray[~exact], s=5, color=COLOR["AASHRAY"], alpha=0.35, linewidths=0,
               label=f"Below optimum: {int((~exact).sum()):,}")
    ax.scatter(milp[exact], aashray[exact], s=5, color=COLOR["MILP"], alpha=0.35, linewidths=0,
               label=f"Exact optimum: {int(exact.sum()):,}")
    ax.plot([0, 1], [0, 1], color=INK_2, linewidth=0.9, linestyle="--")
    # The region above the diagonal is always empty (AASHRAY cannot exceed the optimum),
    # so annotations go there.
    at_one = int(((milp == 1) & (aashray == 1)).sum())
    ax.text(0.05, 0.76, f"{at_one:,} of them at (1, 1),\nthe top-right corner", fontsize=7.2, color=INK,
            ha="left", va="top")
    ax.text(0.22, 0.30, "y = x (AASHRAY = optimum)", rotation=45, rotation_mode="anchor", fontsize=7,
            color=MUTED, ha="left", va="bottom")
    ax.set_xlim(0, 1.03)
    ax.set_ylim(-0.03, 1.03)
    ax.set_aspect("equal")
    ax.grid(axis="both", color=GRID, linewidth=0.6)
    ax.set_xlabel("CDC (MILP)")
    ax.set_ylabel("CDC (AASHRAY)")
    ax.set_title("AASHRAY vs MILP CDC per Scenario")
    ax.legend(loc="upper left", markerscale=2.2, handletextpad=0.2)
    save(fig, "fig09_aashray_vs_milp.png")


# ---------------------------------------------------------------- Figure 10
def fig_runtime():
    rt = DATA["runtime"]
    series = [("AASHRAY (raw, order-affected)", rt["AASHRAY_raw"], COLOR["AASHRAY"], None),
              ("AASHRAY (conservative)", rt["AASHRAY_conservative"], "white", "////"),
              ("MILP (build + solve)", rt["MILP"], COLOR["MILP"], None)]
    stats = [("mean", "Mean"), ("median", "Median"), ("p95", "P95")]
    fig, ax = plt.subplots(figsize=(FULL_W, 2.4))
    x = np.arange(len(stats))
    width = 0.26
    for i, (label, values, face, hatch) in enumerate(series):
        vals = [values[k] for k, _ in stats]
        bars = ax.bar(x + (i - 1) * width, vals, width=width * 0.94, color=face, hatch=hatch,
                      edgecolor=COLOR["AASHRAY"] if hatch else "white", linewidth=0.9, label=label)
        for bar, v in zip(bars, vals):
            ax.text(bar.get_x() + bar.get_width() / 2, v + 0.1, f"{v:.3f}", ha="center", va="bottom",
                    fontsize=7.2, color=INK)
    ax.set_xticks(x, [name for _, name in stats])
    ax.set_ylim(0, max(rt["MILP"]["p95"], 1) * 1.25)
    ax.set_ylabel("Runtime per scenario (ms)")
    ax.set_title("Per-Scenario Runtime: AASHRAY vs MILP (12,000 scenarios)")
    ax.legend(loc="upper left")
    note = (f"Conservative speedup (MILP ÷ AASHRAY): {rt['speedup_conservative_total']:.1f}× by total, "
            f"{rt['speedup_conservative_median']:.1f}× by median\n"
            f"Raw speedup {rt['speedup_raw_total']:.2f}× / {rt['speedup_raw_median']:.2f}× is inflated by execution order "
            f"(FCFS → AASHRAY → MILP)")
    ax.text(0.015, 0.62, note, transform=ax.transAxes, ha="left", va="top", fontsize=7.3, color=INK,
            bbox=dict(boxstyle="round,pad=0.4", facecolor="#fef9c3", edgecolor="#eab308", linewidth=0.6))
    save(fig, "fig10_runtime.png")


def main():
    for make in (fig_mean_cdc, fig_win_tie_loss, fig_cdc_by_scarcity, fig_delta_distribution, fig_bootstrap,
                 fig_gap_distribution, fig_gap_by_scarcity, fig_optimality_rates, fig_scatter, fig_runtime):
        make()
    print("charts written:", sorted(p.name for p in OUT.glob("*.png")))


if __name__ == "__main__":
    main()
