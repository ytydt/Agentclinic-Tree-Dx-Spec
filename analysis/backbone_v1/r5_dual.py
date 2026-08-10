#!/usr/bin/env python3
"""R5 dual-metric table for all 13 focus arms.

Writes scored_correct / chain_correct / mapper_rescue per (arm, case), reusing
r4_lib conventions. New arms get chain from champion~gold match and scored from
mapper (DA) or official_eval_llm (MCR).
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path
from typing import Any

import disagreement_census as dc
import r4_lib as r4
import r5_lib as r5

OUT = r5.OUT / "mosaic_eval" / "r5_dual"


def main() -> int:
    gold = r5.load_gold()
    facts = r5.load_r4_facts()
    rows: list[dict[str, Any]] = []
    summary: dict[str, dict[str, Any]] = defaultdict(dict)

    for log_ds, dkey, sl in r5.SLICES:
        for arm in r5.FOCUS_ARMS:
            if arm in r5.DEV_ONLY and sl.endswith("200b"):
                continue
            d = r5.run_dir(log_ds, arm)
            if d is None:
                continue
            family = r5.FOCUS_ARMS[arm]["family"]
            dual_hits: dict[str, bool] = {}
            if dkey == "da":
                for cid, h in dc.load_mapper_hits(d).items():
                    dual_hits[str(cid)] = bool(
                        h.get("correct") or h.get("option_top1")
                    )
            else:
                hits = dc.load_mcr_hits(d, "official_eval_llm") or dc.load_mcr_hits(
                    d, "official_eval_llm_compat"
                )
                for cid, h in hits.items():
                    dual_hits[str(cid)] = bool(
                        h.get("correct") or h.get("diagnostic_hit") or h.get("hit")
                    )

            cids = [cid for (dd, ss, cid), _ in gold.items() if dd == dkey and ss == sl]
            n_sc = n_ch = n_mr = n = 0
            for cid in cids:
                g = gold[(dkey, sl, cid)]
                traj = r5.load_trajectory(log_ds, arm, cid)
                chain = r5.champion_matches(traj, g) if traj.get("raw_available") else None
                scored = dual_hits.get(cid)
                fact = facts.get((dkey, sl, cid), {})
                if scored is None and arm in ("e7", "v0", "B06", "B07", "APHHM"):
                    col = f"{arm}_scored_correct"
                    if fact.get(col) not in (None, ""):
                        scored = r4.truthy(fact[col])
                    ccol = f"{arm}_chain_correct"
                    if chain is None and fact.get(ccol) not in (None, ""):
                        chain = r4.truthy(fact[ccol])
                mr = (scored is True) and (chain is False)
                if scored is not None:
                    n_sc += int(scored)
                if chain is not None:
                    n_ch += int(chain)
                if scored is not None and chain is not None:
                    n_mr += int(mr)
                n += 1
                rows.append(
                    {
                        "dataset": dkey,
                        "slice": sl,
                        "case_id": cid,
                        "arm": arm,
                        "family": family,
                        "scored_correct": "" if scored is None else int(scored),
                        "chain_correct": "" if chain is None else int(chain),
                        "mapper_rescue": ""
                        if scored is None or chain is None
                        else int(mr),
                        "champion": traj.get("champion") or "",
                        "gold": g,
                    }
                )
            key = f"{dkey}:{sl}"
            summary[arm][key] = {
                "n": n,
                "scored": round(n_sc / n, 4) if n else None,
                "chain": round(n_ch / n, 4) if n else None,
                "mapper_rescue": round(n_mr / n, 4) if n else None,
            }
            print(
                f"{log_ds:28} {arm:16} n={n:3} scored={summary[arm][key]['scored']} "
                f"chain={summary[arm][key]['chain']} rescue={summary[arm][key]['mapper_rescue']}"
            )

    # pooled per arm
    pooled = {}
    for arm in r5.FOCUS_ARMS:
        rs = [r for r in rows if r["arm"] == arm and r["scored_correct"] != ""]
        rc = [r for r in rows if r["arm"] == arm and r["chain_correct"] != ""]
        rm = [r for r in rows if r["arm"] == arm and r["mapper_rescue"] != ""]
        pooled[arm] = {
            "n_scored": len(rs),
            "scored": round(sum(int(r["scored_correct"]) for r in rs) / len(rs), 4) if rs else None,
            "n_chain": len(rc),
            "chain": round(sum(int(r["chain_correct"]) for r in rc) / len(rc), 4) if rc else None,
            "mapper_rescue": round(sum(int(r["mapper_rescue"]) for r in rm) / len(rm), 4)
            if rm
            else None,
        }
    OUT.mkdir(parents=True, exist_ok=True)
    r4.write_tsv(OUT / "dual.tsv", rows)
    r5.write_json(OUT / "summary.json", {"by_slice": summary, "pooled": pooled})
    print("\n=== pooled ===")
    for arm, s in pooled.items():
        print(f"  {arm:16} scored={s['scored']} chain={s['chain']} rescue={s['mapper_rescue']} n={s['n_chain']}")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
