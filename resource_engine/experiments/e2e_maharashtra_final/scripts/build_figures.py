"""Figures for the Maharashtra final E2E run. Every plotted value is read from
results/results.json (measured in this run) or results/summary.json; the
screening estimates are only used in the report table, labelled as expected.

    python build_figures.py
"""
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

EXP = Path(__file__).resolve().parents[1]
RES = EXP / "results"
FIG = EXP / "figures"
LIMIT = 150.0
CLASSES = ["SUCCESS_FULLY_FULFILLED", "SUCCESS_PARTIALLY_FULFILLED", "NO_SAFE_ROUTE", "NO_RESPONDER_AVAILABLE",
           "ROUTE_ENGINE_UNAVAILABLE", "RESOURCE_SHORTAGE", "PIPELINE_FAILURE", "DISTANCE_SCOPE_VIOLATION",
           "VALIDATION_FAILURE"]
BUCKETS = ["0-10", "10-25", "25-50", "50-100", "100-150", ">150"]
NAVY, TEAL, GREY, ORANGE, RED = "#1f3b57", "#2a9d8f", "#9aa5b1", "#e76f51", "#c0392b"

plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.titlesize": 10, "axes.titleweight": "bold", "figure.dpi": 150})


def save(fig, name):
    fig.tight_layout()
    fig.savefig(FIG / name, dpi=200)
    plt.close(fig)
    print("wrote", name)


def main():
    FIG.mkdir(exist_ok=True)
    data = json.loads((RES / "results.json").read_text(encoding="utf-8"))
    rows = data["scenarios"]
    summary = json.loads((RES / "summary.json").read_text(encoding="utf-8"))
    ids = [r["scenario_id"] for r in rows]
    km = [r["route"]["distance_km"] for r in rows]
    mins = [r["route"]["estimated_time_minutes"] for r in rows]

    # 1. distance distribution (measured route totals)
    counts = [summary["distance_buckets"][b] for b in BUCKETS]
    fig, ax = plt.subplots(figsize=(6.4, 3.4))
    bars = ax.bar(BUCKETS, counts, color=[NAVY] * 5 + [RED], edgecolor="white")
    for b, c in zip(bars, counts):
        ax.text(b.get_x() + b.get_width() / 2, c + 0.05, str(c), ha="center", va="bottom")
    ax.set_xlabel("Measured total route distance (km)")
    ax.set_ylabel("Scenarios")
    ax.set_ylim(0, max(counts) + 1)
    ax.set_title(f"Figure 1. Route distance distribution (measured, n = {len(rows)})")
    save(fig, "fig1_route_distance_distribution.png")

    # 2. distance per scenario with 150 km threshold
    fig, ax = plt.subplots(figsize=(7.2, 3.6))
    colors = [TEAL if k <= 50 else NAVY if k <= 100 else ORANGE for k in km]
    bars = ax.bar(ids, km, color=colors)
    for b, k in zip(bars, km):
        ax.text(b.get_x() + b.get_width() / 2, k + 1.5, f"{k:.1f}", ha="center", va="bottom", fontsize=7)
    ax.axhline(LIMIT, color=RED, ls="--", lw=1.2)
    ax.text(len(ids) - 0.5, LIMIT + 3, "150 km hard limit", color=RED, ha="right")
    ax.set_ylim(0, LIMIT + 20)
    ax.set_ylabel("Measured route distance (km)")
    ax.set_xlabel("Scenario")
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right")
    ax.set_title("Figure 2. Measured total route distance by scenario")
    save(fig, "fig2_route_distance_by_scenario.png")

    # 3. required vs allocated vs shortage (aggregate over the 11 executed scenarios)
    fig, axes = plt.subplots(1, 3, figsize=(7.6, 3.4))
    labels = {"water": "Water", "food": "Food", "medical_kits": "Medical kits"}
    totals = summary["resource_totals"]
    for ax, key in zip(axes, ("water", "food", "medical_kits")):
        t = totals[key]
        vals = [t["required"], t["allocated"], t["shortage"]]
        ax.bar(["Required", "Allocated", "Shortage"], vals, color=[GREY, TEAL, ORANGE])
        for i, v in enumerate(vals):
            ax.text(i, v, f"{v:,.0f}", ha="center", va="bottom", fontsize=7)
        ax.set_title(f"{labels[key]}\n{t['fulfilment_pct']:.1f}% allocated", fontsize=9)
        ax.set_ylim(0, max(vals) * 1.18)
        ax.tick_params(axis="x", labelsize=7)
    axes[0].set_ylabel("Units (as defined by resource rules)")
    fig.suptitle("Figure 3. Resource required vs allocated vs shortage (measured, 11 scenarios)", fontsize=10,
                 fontweight="bold")
    save(fig, "fig3_resource_allocation.png")

    # 4. outcome distribution (full taxonomy; zeros shown)
    cls_counts = [summary["classification_counts"].get(c, 0) for c in CLASSES]
    fig, ax = plt.subplots(figsize=(6.6, 3.4))
    bars = ax.barh(CLASSES[::-1], cls_counts[::-1], color=[NAVY if c.startswith("SUCCESS") else GREY
                                                          for c in CLASSES[::-1]])
    for b, c in zip(bars, cls_counts[::-1]):
        ax.text(c + 0.05, b.get_y() + b.get_height() / 2, str(c), va="center")
    ax.set_xlabel("Scenarios")
    ax.set_xlim(0, max(cls_counts) + 2)
    ax.tick_params(axis="y", labelsize=7)
    ax.set_title("Figure 4. Final classification of executed scenarios (measured)")
    save(fig, "fig4_outcome_distribution.png")

    # 5. responder utilization
    resp = summary["responders"]
    final = resp["final_state"]
    order = sorted(final)
    counts = [resp["assignments_per_responder"].get(r, 0) for r in order]
    fig, ax = plt.subplots(figsize=(6.0, 3.0))
    bars = ax.bar(order, counts, color=[NAVY if c else GREY for c in counts])
    for b, c in zip(bars, counts):
        ax.text(b.get_x() + b.get_width() / 2, c + 0.1, str(c), ha="center", va="bottom")
    ax.set_ylabel("Missions assigned")
    ax.set_ylim(0, max(counts) + 2)
    ax.set_title("Figure 5. Responder utilization (missions per responder, measured)")
    save(fig, "fig5_responder_utilization.png")

    # 6. route time per scenario
    fig, ax = plt.subplots(figsize=(7.2, 3.4))
    bars = ax.bar(ids, mins, color=NAVY)
    for b, m in zip(bars, mins):
        ax.text(b.get_x() + b.get_width() / 2, m + 3, f"{m:.0f}", ha="center", va="bottom", fontsize=7)
    med = summary["route_time_minutes"]["median"]
    ax.axhline(med, color=ORANGE, ls=":", lw=1.2)
    ax.text(len(ids) - 0.5, med + 4, f"median {med:.1f} min", color=ORANGE, ha="right")
    ax.set_ylabel("Measured route time (min)")
    ax.set_xlabel("Scenario")
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right")
    ax.set_title("Figure 6. Measured total route time by scenario")
    save(fig, "fig6_route_time_by_scenario.png")


if __name__ == "__main__":
    main()
