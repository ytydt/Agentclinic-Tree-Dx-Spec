#!/usr/bin/env python3
"""Why does widening the candidate pool never pay?

MultiStance bought +22pp of DA pool recall with two extra generation calls and
the gain vanished at top-1. This script checks whether that is a property of that
one arm or of the whole paradigm, by putting every arm in the study -- ours and
the MOSAIC baselines alike -- on the same width-versus-conversion plot.

Two quantities per arm, both offline and deterministic:
  recall = the gold concept is somewhere in the candidate pool
  conv   = given that, the champion is the gold concept
so that top1 = recall x conv exactly.

The residual analysis then asks the separate question of whether, at equal width,
our arms convert as well as the baselines do.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import disagreement_census as dc
from diag_slot_efficiency import load_arm, load_gold
from scipy.stats import linregress, mannwhitneyu, pearsonr

ROOT = Path("/data2/wanghongyi/Agentclinic-Tree-Dx-Spec")
OUT = ROOT / "analysis/backbone_v1/mosaic_eval/width_conversion.json"
DA = [
    ("diagnosisarena", "da", "d2_seq100"),
    ("diagnosisarena_heldout", "da", "d2_heldout100"),
    ("diagnosisarena_heldout200b", "da", "d2_heldout200b"),
]
MCR = [
    ("medcasereasoning", "mcr", "mcr_v1"),
    ("medcasereasoning_v2", "mcr", "mcr_v2"),
    ("medcasereasoning_200b", "mcr", "mcr_200b"),
]
OURS = {
    "APHHM-C": "aphhm_c_v1",
    "+clean": "aphhm_c_clean_v1",
    "K10": "aphhm_c_k10_v1",
    "K6": "aphhm_c_k6_v1",
    "K4": "aphhm_c_k4_v1",
    "NoAxis": "aphhm_c_noaxis_v1",
    "CandEv": "aphhm_c_candev_v1",
    "Collapse3": "aphhm_c_collapse3_v1",
    "Collapse3w": "aphhm_c_collapse3w_v1",
    "Collapse3c": "aphhm_c_collapse3c_v1",
    "MultiStance": "aphhm_c_multistance_v1",
}
BASE = {
    "Lite": "mosaic_lite_v1",
    "Forest": "mosaic_forest_v1",
    "IMPC": "mosaic_impc_v1",
    "v0": "mosaic_v0_v1",
}


def measure(specs: list[tuple[str, str, str]], arm: str, gold: dict) -> dict[str, Any] | None:
    n = width = hits = wins = 0
    for ds, dkey, sl in specs:
        for cid, rec in load_arm(ds, arm).items():
            g = gold.get((dkey, sl, cid))
            if not g:
                continue
            n += 1
            width += len(rec["pool"])
            if dc.any_match(rec["pool"], g):
                hits += 1
            if dc.any_match([rec["champion"]], g):
                wins += 1
    if not n or not hits:
        return None
    return {
        "n": n,
        "width": round(width / n, 3),
        "recall": round(hits / n, 4),
        "conv": round(wins / hits, 4),
        "top1": round(wins / n, 4),
    }


def analyse(tag: str, specs: list[tuple[str, str, str]], gold: dict) -> dict[str, Any]:
    points = []
    for family, arms in (("ours", OURS), ("baseline", BASE)):
        for label, arm in arms.items():
            m = measure(specs, arm, gold)
            if m:
                points.append({"family": family, "arm": label, **m})
    points.sort(key=lambda p: p["width"])
    w = [p["width"] for p in points]
    c = [p["conv"] for p in points]
    r = [p["recall"] for p in points]
    t = [p["top1"] for p in points]
    fit = linregress(w, c)
    for p in points:
        p["conv_residual"] = round(p["conv"] - (fit.intercept + fit.slope * p["width"]), 4)
    ours = [p["conv_residual"] for p in points if p["family"] == "ours"]
    base = [p["conv_residual"] for p in points if p["family"] == "baseline"]
    # what relative recall gain an extra candidate must produce to be top-1 neutral
    breakeven = {
        str(width): round(-fit.slope / (fit.intercept + fit.slope * width), 4)
        for width in (4, 5, 6, 9)
    }
    return {
        "group": tag,
        "arms": points,
        "fit_conv_on_width": {
            "intercept": round(fit.intercept, 4),
            "slope": round(fit.slope, 5),
            "r2": round(fit.rvalue**2, 4),
            "p": round(fit.pvalue, 6),
        },
        "corr_width_conv": [round(x, 4) for x in pearsonr(w, c)],
        "corr_recall_top1": [round(x, 4) for x in pearsonr(r, t)],
        "corr_width_top1": [round(x, 4) for x in pearsonr(w, t)],
        "residual_ours_mean": round(sum(ours) / len(ours), 4),
        "residual_baseline_mean": round(sum(base) / len(base), 4),
        "residual_mannwhitney_p": round(float(mannwhitneyu(ours, base).pvalue), 5),
        "breakeven_relative_recall_gain_per_candidate": breakeven,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()
    gold = load_gold()
    report = [analyse("DA", DA, gold), analyse("MCR", MCR, gold)]
    for block in report:
        f = block["fit_conv_on_width"]
        print(f"=== {block['group']} ===")
        print(
            f"  conv = {f['intercept']:.3f} {f['slope']:+.5f} x width"
            f"   R2={f['r2']:.3f} p={f['p']:.4f}"
        )
        print(f"  corr(width,conv)={block['corr_width_conv'][0]:+.3f} "
              f"corr(recall,top1)={block['corr_recall_top1'][0]:+.3f} "
              f"corr(width,top1)={block['corr_width_top1'][0]:+.3f}")
        print(f"  residual ours {block['residual_ours_mean']:+.3f} vs baseline "
              f"{block['residual_baseline_mean']:+.3f}  p={block['residual_mannwhitney_p']}")
        for p in block["arms"]:
            print(f"    {p['family']:8} {p['arm']:12} n={p['n']:4} width={p['width']:5.2f} "
                  f"recall={p['recall']:.3f} conv={p['conv']:.3f} top1={p['top1']:.3f} "
                  f"resid={p['conv_residual']:+.3f}")
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
