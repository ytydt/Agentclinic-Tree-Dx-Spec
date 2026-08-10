#!/usr/bin/env python3
"""R5 mechanism axes that only the new families expose.

1. Identity lifecycle loss — gold proposed then merge-swallowed
2. Evidence asymmetry — gold vs champion for/against span counts
3. View provenance mismatch — which view found gold vs which won
Plus width-conversion residual from the fitted line in diag_width_conversion.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import disagreement_census as dc
import r5_lib as r5

OUT = r5.OUT / "mosaic_eval" / "r5_mechanisms.json"

# Fitted lines from diag_width_conversion.py (DA / MCR)
FIT = {
    "da": (0.7358, -0.04685),
    "mcr": (0.8199, -0.04527),
}

NEW_ARMS = [
    "aphhm_c_v1",
    "collapse3c",
    "multistance",
    "multistance_r2",
    "msplit",
    "lite",
    "forest",
    "impc",
    "adaptive4v2",
]


def analyse_arm(arm: str) -> dict[str, Any]:
    gold = r5.load_gold()
    out: dict[str, Any] = {"arm": arm, "family": r5.FOCUS_ARMS[arm]["family"], "by_ds": {}}
    for dkey in ("da", "mcr"):
        slices = [s for s in r5.SLICES if s[1] == dkey]
        n = 0
        width = 0
        hits = 0
        wins = 0
        identity_loss = 0
        merge_events_gold = 0
        evidence_asym = []  # champion_against - gold_against when decision_loss
        gold_for = []
        champ_for = []
        gold_against = []
        champ_against = []
        view_found = Counter()
        view_won = Counter()
        view_only_gold = Counter()
        mismatch = 0
        decision_n = 0
        evidence_predicts_wrong = 0  # champ has more against than gold, yet won
        for log_ds, dk, sl in slices:
            if arm in r5.DEV_ONLY and sl.endswith("200b"):
                continue
            if r5.run_dir(log_ds, arm) is None:
                continue
            cids = [cid for (dd, ss, cid), _ in gold.items() if dd == dk and ss == sl]
            for cid in cids:
                g = gold[(dk, sl, cid)]
                traj = r5.load_trajectory(log_ds, arm, cid)
                if not traj.get("raw_available"):
                    continue
                n += 1
                cands = traj.get("candidates") or []
                width += len(cands)
                in_pool = r5.gold_in_pool(traj, g)
                champ_ok = r5.champion_matches(traj, g)
                if in_pool:
                    hits += 1
                if champ_ok:
                    wins += 1
                if r5.gold_merged_away(traj, g):
                    identity_loss += 1
                for e in traj.get("events") or []:
                    lab = str(e.get("label") or e.get("from") or "")
                    if lab and dc.match(lab, g) and str(e.get("op") or "") in (
                        "merge",
                        "merge_audit",
                        "same_as",
                    ):
                        merge_events_gold += 1
                        break

                gc = r5.gold_candidates(traj, g)
                cc = next(
                    (c for c in cands if traj.get("champion") and dc.match(c["label"], traj["champion"])),
                    None,
                )
                if gc and cc and in_pool and not champ_ok:
                    decision_n += 1
                    gf = len(gc[0].get("for") or [])
                    ga = len(gc[0].get("against") or [])
                    cf = len(cc.get("for") or [])
                    ca = len(cc.get("against") or [])
                    gold_for.append(gf)
                    gold_against.append(ga)
                    champ_for.append(cf)
                    champ_against.append(ca)
                    evidence_asym.append((ca - ga) - (cf - gf))  # positive => champ looks worse on evidence
                    if ca > ga and gf >= cf:
                        evidence_predicts_wrong += 1

                # view provenance
                if gc:
                    views = set()
                    for c in gc:
                        for v in c.get("views") or []:
                            views.add(str(v))
                    for v in views:
                        view_found[v] += 1
                    # view-only: only one view proposed gold
                    if len(views) == 1:
                        view_only_gold[next(iter(views))] += 1
                    if champ_ok and cc:
                        cv = set(str(v) for v in (cc.get("views") or []))
                        for v in cv:
                            view_won[v] += 1
                        if views and cv and views.isdisjoint(cv):
                            mismatch += 1

        conv = wins / hits if hits else None
        recall = hits / n if n else None
        wmean = width / n if n else None
        a, b = FIT[dkey]
        line = (a + b * wmean) if wmean is not None else None
        residual = (conv - line) if conv is not None and line is not None else None
        out["by_ds"][dkey] = {
            "n": n,
            "width": round(wmean, 3) if wmean is not None else None,
            "pool_recall": round(recall, 4) if recall is not None else None,
            "conv": round(conv, 4) if conv is not None else None,
            "top1_chain": round(wins / n, 4) if n else None,
            "identity_loss_rate": round(identity_loss / n, 4) if n else None,
            "identity_loss_n": identity_loss,
            "merge_events_touching_gold": merge_events_gold,
            "decision_loss_n": decision_n,
            "mean_gold_for": round(sum(gold_for) / len(gold_for), 3) if gold_for else None,
            "mean_gold_against": round(sum(gold_against) / len(gold_against), 3)
            if gold_against
            else None,
            "mean_champ_for": round(sum(champ_for) / len(champ_for), 3) if champ_for else None,
            "mean_champ_against": round(sum(champ_against) / len(champ_against), 3)
            if champ_against
            else None,
            "evidence_asym_mean": round(sum(evidence_asym) / len(evidence_asym), 3)
            if evidence_asym
            else None,
            "evidence_says_champ_worse_frac": round(evidence_predicts_wrong / decision_n, 3)
            if decision_n
            else None,
            "view_found_gold": dict(view_found),
            "view_won": dict(view_won),
            "view_only_gold": dict(view_only_gold),
            "view_champ_mismatch_n": mismatch,
            "fit_line_conv": round(line, 4) if line is not None else None,
            "conv_residual": round(residual, 4) if residual is not None else None,
        }
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", default="")
    args = ap.parse_args()
    arms = [a.strip() for a in args.arms.split(",") if a.strip()] or NEW_ARMS
    report = [analyse_arm(a) for a in arms]
    r5.write_json(Path(OUT), report)
    for block in report:
        print(f"=== {block['arm']} ({block['family']}) ===")
        for ds, b in block["by_ds"].items():
            print(
                f"  {ds}: n={b['n']} width={b['width']} recall={b['pool_recall']} "
                f"conv={b['conv']} id_loss={b['identity_loss_rate']} "
                f"evid_worse_frac={b['evidence_says_champ_worse_frac']} "
                f"resid={b['conv_residual']}"
            )
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
