#!/usr/bin/env python3
"""Quick chain/near-match eval for arbitrary log arm dirs on one or more slices."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "analysis" / "backbone_v1"))

import r5_lib as r5  # noqa: E402
from r7_scale_summarize import cluster_rel, load_champ  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", required=True, help="comma-separated arm dir names")
    ap.add_argument(
        "--slices",
        default="diagnosisarena",
        help="comma-separated log_ds names (default: diagnosisarena=seq100)",
    )
    args = ap.parse_args()
    arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    slices = [s.strip() for s in args.slices.split(",") if s.strip()]
    gold = r5.load_gold()
    out = {}
    for arm in arms:
        n = chain = near = parent = missing = 0
        by = {}
        for log_ds in slices:
            dkey = next((dk for ld, dk, _ in r5.SLICES if ld == log_ds), None)
            sl = next((s for ld, _, s in r5.SLICES if ld == log_ds), None)
            if not dkey or not sl:
                continue
            for cid in [c for (dd, ss, c), _ in gold.items() if dd == dkey and ss == sl]:
                g = gold[(dkey, sl, cid)]
                champ = load_champ(log_ds, arm, cid)
                if champ is None:
                    missing += 1
                    continue
                n += 1
                rel = cluster_rel(champ, g)
                if rel == "chain":
                    chain += 1
                    near += 1
                    parent += 1
                elif rel == "parent_subtype":
                    near += 1
                    parent += 1
                elif rel == "near_sibling":
                    near += 1
        out[arm] = {
            "n": n,
            "missing": missing,
            "chain": round(chain / n, 4) if n else None,
            "near_match": round(near / n, 4) if n else None,
            "parent_or_chain": round(parent / n, 4) if n else None,
        }
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
