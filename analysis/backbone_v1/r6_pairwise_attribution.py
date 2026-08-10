#!/usr/bin/env python3
"""Pairwise trajectory attribution tree for R6 focus pairs."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import disagreement_census as dc
import r5_lib as r5
import r6_lib as r6

OUT = r5.OUT / "mosaic_eval" / "r6_attribution.json"
PAIRS = list(r6.PAIR_ARMS)


def bootstrap_ci(xs: list[int], n_boot: int = 1000, alpha: float = 0.05) -> dict[str, float]:
    if not xs:
        return {"mean": 0.0, "lo": 0.0, "hi": 0.0, "n": 0}
    arr = np.asarray(xs, float)
    means = []
    rng = np.random.default_rng(0)
    n = len(arr)
    for _ in range(n_boot):
        samp = rng.choice(arr, size=n, replace=True)
        means.append(samp.mean())
    lo, hi = np.quantile(means, [alpha / 2, 1 - alpha / 2])
    return {
        "mean": round(float(arr.mean()), 4),
        "lo": round(float(lo), 4),
        "hi": round(float(hi), 4),
        "n": n,
    }


def leaf_for_loser(
    loser_arm: str,
    log_ds: str,
    cid: str,
    gold: str,
    winner_arm: str,
) -> dict[str, Any]:
    """Attribution leaf explaining why loser_arm failed while winner succeeded."""
    traj_l = r5.load_trajectory(log_ds, loser_arm, cid)
    traj_w = r5.load_trajectory(log_ds, winner_arm, cid)
    doc_l = r6.load_raw_doc(log_ds, loser_arm, cid)
    proposed = r5.ever_proposed_gold(traj_l, gold) or r5.gold_in_pool(traj_l, gold)
    if not proposed:
        # which winner view found gold?
        views = []
        for c in traj_w.get("candidates") or []:
            if gold and dc.match(c["label"], gold):
                views = list(c.get("views") or [])
        return {
            "leaf": "generation_gap",
            "winner_views_for_gold": views,
            "detail": "loser never proposed gold",
        }
    if r5.gold_merged_away(traj_l, gold):
        return {"leaf": "identity_merge", "detail": "gold merged away in loser"}
    in_short = r5.gold_in_shortlist(traj_l, gold)
    if not in_short:
        # prune mechanism
        status = ""
        for c in traj_l.get("candidates") or []:
            if gold and dc.match(c["label"], gold):
                status = str(c.get("status") or "")
        sub = "status_prune" if status and status not in ("live", "active", "protected", "") else "frontier_truncate"
        if loser_arm in ("multistance", "msplit") and doc_l:
            rnd = r6.multistance_loss_round(doc_l, gold)
            if rnd == "group_drop":
                sub = "nominate_group_drop"
            elif rnd == "final_drop":
                sub = "final_drop_but_wait_shortlist"
        return {"leaf": "prune", "sub": sub, "status": status}
    # in decision set — rejected?
    if doc_l and r5.FOCUS_ARMS[loser_arm]["family"] == "mosaic":
        rej = r6.mosaic_selector_reject_gold(doc_l, gold)
        if rej.get("gold_rejected"):
            return {
                "leaf": "explicit_reject",
                "why": rej.get("gold_reject_why") or "",
                "margin": rej.get("margin"),
            }
    # silent drop
    gap = None
    disc = None
    if doc_l:
        info = r6.score_logit_gap(doc_l, gold, traj_l.get("champion") or "")
        gap = info.get("score_gap_champ_minus_gold")
    cands = traj_l.get("candidates") or []
    g_lab = next((c["label"] for c in cands if gold and dc.match(c["label"], gold)), "")
    disc = r6.evidence_discriminability(cands, g_lab) if g_lab else None
    # position in shortlist
    short = traj_l.get("shortlist") or []
    pos = None
    for i, lab in enumerate(short):
        if gold and dc.match(lab, gold):
            pos = i
            break
    return {
        "leaf": "silent_drop",
        "score_gap": gap,
        "gold_disc": disc,
        "shortlist_pos": pos,
        "shortlist_n": len(short),
    }


def analyse_direction(winner: str, loser: str) -> dict[str, Any]:
    gold = r5.load_gold()
    leaves: list[dict] = []
    for log_ds, dkey, sl in r5.SLICES:
        # need both arms present
        if r5.run_dir(log_ds, winner) is None or r5.run_dir(log_ds, loser) is None:
            continue
        if winner in r5.DEV_ONLY and sl.endswith("200b"):
            continue
        if loser in r5.DEV_ONLY and sl.endswith("200b"):
            continue
        for cid in [c for (dd, ss, c), _ in gold.items() if dd == dkey and ss == sl]:
            g = gold[(dkey, sl, cid)]
            tw = r5.load_trajectory(log_ds, winner, cid)
            tl = r5.load_trajectory(log_ds, loser, cid)
            if not tw.get("raw_available") or not tl.get("raw_available"):
                continue
            if not r5.champion_matches(tw, g):
                continue
            if r5.champion_matches(tl, g):
                continue
            leaf = leaf_for_loser(loser, log_ds, cid, g, winner)
            leaf.update(
                {
                    "dataset": dkey,
                    "slice": sl,
                    "case_id": cid,
                    "winner": winner,
                    "loser": loser,
                }
            )
            leaves.append(leaf)
    counts = Counter(x["leaf"] for x in leaves)
    n = len(leaves) or 1
    # bootstrap rates
    rates = {}
    for leaf in counts:
        ind = [1 if x["leaf"] == leaf else 0 for x in leaves]
        rates[leaf] = bootstrap_ci(ind)
    # subcounts
    sub = Counter(
        f"{x['leaf']}:{x.get('sub')}" for x in leaves if x["leaf"] == "prune"
    )
    view_counter = Counter()
    for x in leaves:
        if x["leaf"] == "generation_gap":
            for v in x.get("winner_views_for_gold") or ["unknown"]:
                view_counter[str(v)] += 1
    return {
        "winner": winner,
        "loser": loser,
        "n_exclusive": len(leaves),
        "leaf_counts": dict(counts),
        "leaf_rates": rates,
        "prune_sub": dict(sub),
        "generation_gap_winner_views": dict(view_counter),
        "examples": {
            leaf: [
                f"{x['dataset']}/{x['slice']}/{x['case_id']}"
                for x in leaves
                if x["leaf"] == leaf
            ][:5]
            for leaf in counts
        },
    }


def main() -> int:
    report = {"directions": [], "noise_note": (
        "Exclusive-win counts must be compared to replicate exclusive null "
        "in r6_winsets/summary.json before claiming resolvable differences."
    )}
    for a, b in PAIRS:
        print(f"=== {a} wins, {b} loses ===")
        d1 = analyse_direction(a, b)
        print(d1["leaf_counts"], "n=", d1["n_exclusive"])
        print(f"=== {b} wins, {a} loses ===")
        d2 = analyse_direction(b, a)
        print(d2["leaf_counts"], "n=", d2["n_exclusive"])
        report["directions"].append(d1)
        report["directions"].append(d2)
    r6.write_json(OUT, report)
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
