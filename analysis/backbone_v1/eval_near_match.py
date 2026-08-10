#!/usr/bin/env python3
"""Emit near-match / parent-subtype secondary metrics alongside chain.

Usage:
  PYTHONPATH=analysis/backbone_v1:src \\
    python3 analysis/backbone_v1/eval_near_match.py --arms forest,collapse3c,lite
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "analysis" / "backbone_v1"))
sys.path.insert(0, str(ROOT / "src"))

import disagreement_census as dc
import r3_lib as r3
import r5_lib as r5
import r6_lib as r6


def rel(champ: str, gold: str) -> str:
    if not champ or not gold:
        return "unrelated"
    if dc.match(champ, gold):
        return "chain"
    al, bl = champ.lower(), gold.lower()
    if al in bl or bl in al:
        return "parent_subtype"
    if r3.near_gold(champ, gold):
        return "near_sibling"
    return "unrelated"


def eval_arm(arm: str) -> dict:
    gold = r5.load_gold()
    n = chain = near = parent = 0
    for log_ds, dkey, sl in r5.SLICES:
        if r5.run_dir(log_ds, arm) is None:
            continue
        for cid in [c for (dd, ss, c), _ in gold.items() if dd == dkey and ss == sl]:
            g = gold[(dkey, sl, cid)]
            traj = r5.load_trajectory(log_ds, arm, cid)
            if not traj.get("raw_available"):
                continue
            champ = str(traj.get("champion") or "")
            n += 1
            r = rel(champ, g)
            if r == "chain":
                chain += 1
                near += 1
                parent += 1
            elif r == "parent_subtype":
                near += 1
                parent += 1
            elif r == "near_sibling":
                near += 1
    return {
        "arm": arm,
        "n": n,
        "chain": round(chain / n, 4) if n else None,
        "near_match": round(near / n, 4) if n else None,
        "parent_subtype_or_chain": round(parent / n, 4) if n else None,
        "near_minus_chain": round((near - chain) / n, 4) if n else None,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", default="forest,lite,collapse3c,multistance,e7,impc")
    ap.add_argument(
        "--out",
        type=Path,
        default=r5.OUT / "mosaic_eval" / "r7_offline" / "near_match_baselines.json",
    )
    args = ap.parse_args()
    arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    out = {a: eval_arm(a) for a in arms}
    r6.write_json(args.out, out)
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
