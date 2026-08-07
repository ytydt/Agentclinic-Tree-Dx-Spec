"""Deterministically render the APHHM pipeline figure used by main.tex."""

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch


BLUE = "#24577A"
TEAL = "#2F6F73"
INK = "#111111"
PALE = "#F4F7F9"
GRAY = "#666666"


def box(ax, xy, width, height, title, body, edge=BLUE, fontsize=11):
    x, y = xy
    patch = FancyBboxPatch(
        (x, y), width, height,
        boxstyle="round,pad=0.012,rounding_size=0.015",
        linewidth=1.8, edgecolor=edge, facecolor=PALE,
    )
    ax.add_patch(patch)
    ax.text(x + width / 2, y + height - 0.045, title, ha="center", va="top",
            fontsize=fontsize + 1, fontweight="bold", color=INK)
    ax.text(x + width / 2, y + height * 0.43, body, ha="center", va="center",
            fontsize=fontsize, color=INK, linespacing=1.25)


def arrow(ax, start, end, dashed=False, color=BLUE):
    ax.add_patch(FancyArrowPatch(
        start, end, arrowstyle="-|>", mutation_scale=15,
        linewidth=1.7, color=color,
        linestyle=(0, (4, 4)) if dashed else "solid",
        shrinkA=2, shrinkB=2,
    ))


fig, ax = plt.subplots(figsize=(15.5, 5.8), dpi=180)
ax.set_xlim(0, 1)
ax.set_ylim(0, 1)
ax.axis("off")

box(ax, (0.015, 0.50), 0.12, 0.38, "Inputs",
    "Vignette $V$\nObserved facts $F$\nShared corpus $\\mathcal{K}$",
    edge=GRAY, fontsize=10.5)
box(ax, (0.17, 0.50), 0.205, 0.38, "1. Case-Adaptive Organization",
    "Recall candidates\n$\\rightarrow$ infer case axis\n$\\rightarrow$ select relative evidence\n$\\rightarrow$ expand L2 branches",
    fontsize=10.2)
box(ax, (0.415, 0.50), 0.205, 0.38, "2. Concept-Level Competition",
    "Pairwise predicate $r$\n$\\rightarrow$ component closure $\\sim$\n$\\rightarrow$ retain best representative\n$\\rightarrow$ allocate distinct slots",
    fontsize=10.2)
box(ax, (0.66, 0.50), 0.205, 0.38, "3. State-Consistent Decoding",
    "Local update $B_{t+1}=U(B_t,e_t)$\n$\\rightarrow$ write back leaf scores\n$\\rightarrow$ construct Top-$N$ pool\n$\\rightarrow$ bounded decoding",
    fontsize=10.0)
box(ax, (0.90, 0.50), 0.085, 0.38, "Outputs",
    "$\\leq k_{\\mathrm{out}}$ diseases\nDistinct classes\nInterface binding",
    edge=GRAY, fontsize=9.5)

for a, b in [((0.135, 0.69), (0.17, 0.69)),
             ((0.375, 0.69), (0.415, 0.69)),
             ((0.62, 0.69), (0.66, 0.69)),
             ((0.865, 0.69), (0.90, 0.69))]:
    arrow(ax, a, b)

state = FancyBboxPatch(
    (0.19, 0.30), 0.65, 0.12,
    boxstyle="round,pad=0.012,rounding_size=0.015",
    linewidth=1.8, edgecolor=TEAL, facecolor="#F2F8F8",
)
ax.add_patch(state)
ax.text(0.515, 0.36,
        "Shared belief state  $B_t=(G_t,q_t,s_t,E_t)$:  hierarchy  |  concept identity  |  relative scores  |  evidence",
        ha="center", va="center", fontsize=10.5, color=INK, fontweight="bold")

arrow(ax, (0.275, 0.50), (0.275, 0.42), dashed=True, color=TEAL)
arrow(ax, (0.515, 0.50), (0.515, 0.42), dashed=True, color=TEAL)
arrow(ax, (0.76, 0.42), (0.76, 0.50), dashed=True, color=TEAL)

audit = FancyBboxPatch(
    (0.055, 0.06), 0.89, 0.14,
    boxstyle="round,pad=0.012,rounding_size=0.01",
    linewidth=1.4, edgecolor=GRAY, facecolor="white", linestyle=(0, (4, 4)),
)
ax.add_patch(audit)
ax.text(0.5, 0.15, "Earliest-stage audit", ha="center", va="center",
        fontsize=11.5, fontweight="bold", color=INK)
ax.text(0.5, 0.095,
        "parent absent  $\\rightarrow$  leaf absent  $\\rightarrow$  local elimination  $\\rightarrow$  global misranking  $\\rightarrow$  binding failure",
        ha="center", va="center", fontsize=10.5, color=INK)
arrow(ax, (0.942, 0.50), (0.942, 0.20), dashed=True, color=TEAL)

fig.subplots_adjust(left=0.01, right=0.99, top=0.99, bottom=0.01)
out = Path(__file__).with_name("aphhm_pipeline.png")
fig.savefig(out, bbox_inches="tight", pad_inches=0.03)
plt.close(fig)