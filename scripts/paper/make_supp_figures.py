#!/usr/bin/env python3
"""Generate the supplementary-material figures.

All inputs are literals transcribed from tables already present in
``paper_aaai/SupplementaryMaterial copy.tex`` and ``paper_aaai/main.tex``.
The script recomputes no metric; it renders published numbers so that the
figures cannot drift from the tables they visualise.

Usage:  python3 scripts/paper/make_supp_figures.py
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import FancyArrowPatch

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "paper_aaai" / "figures"

BLUE = "#1F4E79"
TEAL = "#2E6F6B"
WARM = "#9C4A1A"
GRAY = "#555555"
PALE = "#EDF3F8"
MINT = "#EAF3F2"
CREAM = "#FBF1E8"

plt.rcParams.update(
    {
        "font.family": "STIXGeneral",
        "mathtext.fontset": "stix",
        "font.size": 7.2,
        "axes.linewidth": 0.5,
        "axes.edgecolor": GRAY,
        "xtick.major.width": 0.5,
        "ytick.major.width": 0.5,
        "xtick.color": GRAY,
        "ytick.color": GRAY,
        "xtick.labelsize": 6.6,
        "ytick.labelsize": 6.6,
        "legend.fontsize": 6.6,
        "legend.frameon": False,
        "pdf.fonttype": 42,
    }
)


def _despine(ax, keep=("left", "bottom")):
    for side in ("top", "right", "left", "bottom"):
        ax.spines[side].set_visible(side in keep)


# ---------------------------------------------------------------- figure 1
# Earliest-stage attribution (tab:full-cohort) read as a cumulative funnel;
# the intermediate counts agree with the utilisation table (tab:utilisation).
FUNNEL = {
    "DiagnosisArena": {
        "levels": [100, 79, 62, 40],
        "losses": [("coverage or unscorable", 21), ("local elimination", 17), ("global misranking", 22)],
        "dominant": 2,
    },
    "MedCaseReasoning": {
        "levels": [100, 76, 56, 46],
        "losses": [("coverage or unscorable", 24), ("local elimination", 20), ("global misranking", 10)],
        "dominant": 0,
    },
    "Open-XDDx": {
        "levels": [100, 84, 44, 38],
        "losses": [("coverage or unscorable", 16), ("local elimination", 40), ("global misranking", 6)],
        "dominant": 1,
    },
}

STEP_LABELS = ["Evaluated", "Structurally\nreachable", "Retained to\nglobal decoding", "Credited"]


def figure_funnel(path: Path) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(7.0, 2.35), sharey=True)
    for ax, (name, spec) in zip(axes, FUNNEL.items()):
        levels = spec["levels"]
        xs = range(len(levels))
        ax.bar(xs, levels, width=0.56, color=PALE, edgecolor=BLUE, linewidth=0.7, zorder=2)
        for x, v in zip(xs, levels):
            ax.text(x, v + 2.5, str(v), ha="center", va="bottom", color=BLUE, fontsize=6.8)

        for i, (label, drop) in enumerate(spec["losses"]):
            dominant = i == spec["dominant"]
            colour = WARM if dominant else GRAY
            top, bottom = levels[i], levels[i + 1]
            ax.add_patch(
                FancyArrowPatch(
                    (i + 0.30, top),
                    (i + 0.70, bottom),
                    arrowstyle="-|>",
                    mutation_scale=5,
                    linewidth=1.1 if dominant else 0.6,
                    color=colour,
                    zorder=4,
                )
            )
            ax.text(
                i + 0.5,
                max(top, bottom) + 11 if dominant else max(top, bottom) + 6,
                f"$-{drop}$",
                ha="center",
                va="bottom",
                color=colour,
                fontsize=6.8 if not dominant else 7.4,
                fontweight="bold" if dominant else "normal",
                zorder=5,
            )

        dom_label = spec["losses"][spec["dominant"]][0]
        ax.text(
            0.5,
            -0.40,
            f"dominant loss: {dom_label}",
            transform=ax.transAxes,
            ha="center",
            va="top",
            color=WARM,
            fontsize=6.8,
        )
        ax.set_title(name, color=BLUE, fontsize=7.6, pad=4)
        ax.set_xticks(list(xs))
        ax.set_xticklabels(STEP_LABELS, fontsize=6.2)
        ax.set_ylim(0, 122)
        ax.set_yticks([0, 25, 50, 75, 100])
        _despine(ax)
        ax.grid(axis="y", color=GRAY, alpha=0.14, linewidth=0.4, zorder=0)
    axes[0].set_ylabel("cases ($n{=}100$)", fontsize=6.8)
    fig.subplots_adjust(left=0.06, right=0.995, top=0.88, bottom=0.30, wspace=0.12)
    fig.savefig(path, format="pdf")
    plt.close(fig)


# ---------------------------------------------------------------- figure 2
# tab:budget (main paper) plus the full model's own call count and score.
LADDER = {
    "DiagnosisArena (Top-1)": {
        "flat": [(2.0, 0.56), (9.24, 0.48), (92.4, 0.47)],
        "full": (94.3, 0.71),
        "colour": BLUE,
        "marker": "o",
        "dy": 0.0,
    },
    "MedCaseReasoning (accuracy)": {
        "flat": [(2.0, 0.17), (9.32, 0.17), (93.2, 0.15)],
        "full": (81.2, 0.50),
        "colour": TEAL,
        "marker": "s",
        "dy": -0.022,
    },
    "Open-XDDx (micro-F1)": {
        "flat": [(2.0, 0.495), (8.98, 0.479), (89.8, 0.487)],
        "full": (68.6, 0.651),
        "colour": WARM,
        "marker": "^",
        "dy": 0.028,
        "ha": "right",
    },
}


def figure_ladder(path: Path) -> None:
    fig, ax = plt.subplots(figsize=(3.30, 2.62))

    ax.axvspan(64, 100, color=PALE, alpha=0.75, zorder=0)
    ax.text(80, 0.775, "similar call budget", ha="center", va="top", fontsize=6.3, color=GRAY)

    for name, spec in LADDER.items():
        xs = [p[0] for p in spec["flat"]]
        ys = [p[1] for p in spec["flat"]]
        ax.plot(
            xs,
            ys,
            color=spec["colour"],
            linewidth=0.9,
            marker=spec["marker"],
            markersize=3.2,
            markerfacecolor="white",
            markeredgewidth=0.8,
            zorder=3,
        )
        fx, fy = spec["full"]
        base = ys[-1]
        ax.add_patch(
            FancyArrowPatch(
                (fx, base + 0.008),
                (fx, fy - 0.008),
                arrowstyle="-|>",
                mutation_scale=5,
                linewidth=0.8,
                color=spec["colour"],
                zorder=3,
            )
        )
        ax.plot(
            [fx],
            [fy],
            marker=spec["marker"],
            markersize=5.2,
            color=spec["colour"],
            markeredgecolor="white",
            markeredgewidth=0.6,
            linestyle="none",
            zorder=4,
        )
        ha = spec.get("ha", "left")
        ax.text(
            fx * (0.86 if ha == "right" else 1.16),
            fy + spec["dy"],
            f"$+{fy - base:.2f}$",
            color=spec["colour"],
            fontsize=6.5,
            va="center",
            ha=ha,
        )

    ax.set_xscale("log")
    ax.set_xlim(1.5, 460)
    ax.set_ylim(0.08, 0.80)
    ax.set_xticks([2, 9, 90])
    ax.set_xticklabels(["$2$", "$9$", "$90$"])
    ax.set_yticks([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7])
    ax.set_xlabel("mean model calls per case (log scale)", fontsize=6.9)
    ax.set_ylabel("end-task score", fontsize=6.9)
    _despine(ax)
    ax.grid(axis="y", color=GRAY, alpha=0.14, linewidth=0.4, zorder=0)

    handles = [
        Line2D([], [], color=s["colour"], marker=s["marker"], markersize=3.2,
               markerfacecolor="white", markeredgewidth=0.8, linewidth=0.9, label=n)
        for n, s in LADDER.items()
    ]
    handles.append(
        Line2D([], [], color=GRAY, marker="o", markersize=5.2, linestyle="none",
               label="full model (filled marker)")
    )
    ax.legend(handles=handles, loc="lower left", bbox_to_anchor=(-0.025, -0.02),
              handlelength=1.6, labelspacing=0.30)
    fig.subplots_adjust(left=0.135, right=0.975, top=0.97, bottom=0.16)
    fig.savefig(path, format="pdf")
    plt.close(fig)


# ---------------------------------------------------------------- figure 3
# Which evidence exists on which benchmark. Filled = reported in this paper.
EVIDENCE = [
    ("Descriptive and audit evidence", None),
    ("End-task comparison against 14 baselines", (1, 1, 1)),
    ("Similar-call-count flat control", (1, 1, 1)),
    ("Earliest-stage failure attribution", (1, 1, 1)),
    ("Ranking-window redundancy and width", (1, 1, 1)),
    ("Stage hazards and repair value", (0, 1, 1)),
    ("Interface-attributable loss", (1, 0, 0)),
    ("Reasoning-recall endpoint, two judges", (0, 1, 0)),
    ("Confirmatory mechanism contrasts", None),
    ("Case-adaptive comparison axis", (1, 0, 0)),
    ("Equivalence-aware competition", (0, 1, 0)),
    ("Evidence-conditioned score write-back", (0, 0, 1)),
]


def figure_evidence_map(path: Path) -> None:
    rows = list(reversed(EVIDENCE))
    fig, ax = plt.subplots(figsize=(3.30, 2.62))
    cols = ["DA", "MCR", "OX"]
    for y, (label, marks) in enumerate(rows):
        if marks is None:
            ax.text(-0.06, y, label, ha="right", va="center", fontsize=6.9,
                    color=BLUE, style="italic", transform=ax.get_yaxis_transform(which="grid"))
            ax.axhline(y - 0.5, color=GRAY, alpha=0.35, linewidth=0.5)
            continue
        ax.text(-0.06, y, label, ha="right", va="center", fontsize=6.7, color="black",
                transform=ax.get_yaxis_transform(which="grid"))
        for x, m in enumerate(marks):
            if m:
                ax.plot([x], [y], marker="o", markersize=5.4, color=BLUE, linestyle="none")
            else:
                ax.plot([x - 0.13, x + 0.13], [y, y], color=GRAY, alpha=0.45, linewidth=0.9)

    ax.set_xlim(-0.5, 2.5)
    ax.set_ylim(-0.7, len(rows) - 0.3)
    ax.set_xticks(range(3))
    ax.set_xticklabels(cols, fontsize=7.0, color=BLUE)
    ax.xaxis.set_ticks_position("top")
    ax.set_yticks([])
    for side in ("top", "right", "left", "bottom"):
        ax.spines[side].set_visible(False)
    ax.tick_params(axis="x", length=0, pad=2)
    for x in range(3):
        ax.axvline(x, color=GRAY, alpha=0.12, linewidth=0.5, zorder=0)
    fig.subplots_adjust(left=0.615, right=0.985, top=0.93, bottom=0.02)
    fig.savefig(path, format="pdf")
    plt.close(fig)


# ---------------------------------------------------------------- figure 4
# tab:slots-mech (window, before compression) against tab:slots-cross
# (emitted lists, after compression, one predicate for every system).
WINDOW = [("DA", 0.632), ("MCR", 0.593), ("OX", 0.643)]
FLAT_MIN, FLAT_MAX, FLAT_MEAN = 0.033, 0.098, 0.058
EMITTED_FULL = 0.029


def figure_redundancy(path: Path) -> None:
    fig, ax = plt.subplots(figsize=(3.30, 1.85))
    y_window, y_flat, y_emitted = 2.0, 1.0, 0.0
    height = 0.42

    ax.barh(y_window, 0.643, height=height, color=PALE, edgecolor=BLUE, linewidth=0.7, zorder=2)
    ax.text(0.643 + 0.012, y_window, "$0.643$", va="center", fontsize=6.6, color=BLUE)

    ax.barh(
        y_flat,
        FLAT_MAX - FLAT_MIN,
        left=FLAT_MIN,
        height=height,
        color=CREAM,
        edgecolor=WARM,
        linewidth=0.7,
        zorder=2,
    )
    ax.plot([FLAT_MEAN, FLAT_MEAN], [y_flat - height / 2, y_flat + height / 2],
            color=WARM, linewidth=0.9, zorder=3)
    ax.text(FLAT_MAX + 0.012, y_flat, "0.033\u20130.098 (mean 0.058)", va="center",
            fontsize=6.6, color=WARM)

    ax.barh(y_emitted, EMITTED_FULL, height=height, color=BLUE, edgecolor=BLUE,
            linewidth=0.7, zorder=2)
    ax.text(EMITTED_FULL + 0.012, y_emitted, "$0.029$", va="center", fontsize=6.6, color=BLUE)

    corner = y_emitted - 0.40
    ax.add_patch(
        FancyArrowPatch(
            (0.643, y_window - height / 2 - 0.04),
            (0.643, corner),
            arrowstyle="-",
            linewidth=0.7,
            color=BLUE,
            linestyle=(0, (2.5, 2)),
            zorder=1,
        )
    )
    ax.add_patch(
        FancyArrowPatch(
            (0.643, corner),
            (EMITTED_FULL, corner),
            arrowstyle="-|>",
            mutation_scale=6,
            linewidth=0.7,
            color=BLUE,
            linestyle=(0, (2.5, 2)),
            zorder=1,
        )
    )
    ax.text(0.34, corner + 0.06, "equivalence compression", fontsize=6.5, color=BLUE,
            ha="center", va="bottom")

    ax.set_yticks([y_emitted, y_flat, y_window])
    ax.set_yticklabels(
        ["emitted list,\nfull model", "emitted list,\n14 flat systems", "ranking window,\nfull model"],
        fontsize=6.5,
    )
    ax.set_ylim(-0.95, 2.55)
    ax.set_xlim(0, 0.80)
    ax.set_xticks([0.0, 0.2, 0.4, 0.6, 0.8])
    ax.set_xlabel("wasted-slot rate on Open-XDDx", fontsize=6.9)
    _despine(ax)
    ax.grid(axis="x", color=GRAY, alpha=0.14, linewidth=0.4, zorder=0)
    fig.subplots_adjust(left=0.265, right=0.985, top=0.97, bottom=0.235)
    fig.savefig(path, format="pdf")
    plt.close(fig)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    figure_funnel(OUT / "supp_funnel.pdf")
    figure_ladder(OUT / "supp_budget_ladder.pdf")
    figure_evidence_map(OUT / "supp_evidence_map.pdf")
    figure_redundancy(OUT / "supp_redundancy.pdf")
    print(f"wrote 4 figures to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
