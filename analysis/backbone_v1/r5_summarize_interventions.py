#!/usr/bin/env python3
"""Summarise R5 J1/J2/J3 oracle arms vs their baselines (McNemar on chain)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import disagreement_census as dc
import r4_lib as r4
import r5_lib as r5

OUT = r5.OUT / "mosaic_eval" / "r5_interventions.json"

# (oracle_arm_dir, baseline_arm_key, intervention, slices)
SPECS = [
    ("r5_j1_collapse3c", "collapse3c", "j1", None),
    ("r5_j1_forest", "forest", "j1", None),
    ("r5_j2_collapse3c", "collapse3c", "j2", ("d2_seq100", "mcr_v1")),
    ("r5_j2_forest", "forest", "j2", ("d2_seq100", "mcr_v1")),
    ("r5_j3_multistance", "multistance", "j3", None),
]


def mcnemar(a: dict[str, bool], b: dict[str, bool]) -> dict[str, Any]:
    shared = sorted(set(a) & set(b))
    a_only = b_only = both = neither = 0
    for k in shared:
        if a[k] and not b[k]:
            a_only += 1
        elif b[k] and not a[k]:
            b_only += 1
        elif a[k] and b[k]:
            both += 1
        else:
            neither += 1
    # exact binomial two-sided on discordant
    from math import comb

    n = a_only + b_only
    if n == 0:
        p = 1.0
    else:
        p = sum(comb(n, k) for k in range(0, n + 1) if comb(n, k) <= comb(n, min(a_only, b_only))) * (
            0.5 ** n
        )
        # simpler: use scipy if available
        try:
            from scipy.stats import binomtest

            p = float(binomtest(min(a_only, b_only), n, 0.5).pvalue)
        except Exception:
            pass
    return {
        "n": len(shared),
        "a_only": a_only,
        "b_only": b_only,
        "both": both,
        "neither": neither,
        "acc_a": round(sum(a[k] for k in shared) / len(shared), 4) if shared else None,
        "acc_b": round(sum(b[k] for k in shared) / len(shared), 4) if shared else None,
        "p": round(p, 6),
    }


def load_oracle_hits(log_ds: str, arm_dir: str) -> dict[str, bool]:
    d = r5.LOGS / log_ds / arm_dir / "case_stages"
    out = {}
    if not d.is_dir():
        return out
    for p in d.glob("*.json"):
        doc = __import__("json").loads(p.read_text())
        gold = str(doc.get("gold") or "")
        champ = str(doc.get("champion") or "")
        cid = str(doc.get("source_id") or p.stem)
        out[cid] = bool(gold and champ and dc.match(champ, gold))
    return out


def main() -> int:
    gold = r5.load_gold()
    report = []
    for arm_dir, base_key, interv, slice_filter in SPECS:
        for dkey in ("da", "mcr"):
            base_hits: dict[str, bool] = {}
            ora_hits: dict[str, bool] = {}
            for log_ds, dk, sl in r5.SLICES:
                if dk != dkey:
                    continue
                if slice_filter and sl not in slice_filter:
                    continue
                if arm_dir.startswith("r5_j2") and sl.endswith("200b"):
                    continue
                # baseline
                for cid in [c for (dd, ss, c), _ in gold.items() if dd == dk and ss == sl]:
                    g = gold[(dk, sl, cid)]
                    traj = r5.load_trajectory(log_ds, base_key, cid)
                    if traj.get("raw_available"):
                        base_hits[f"{sl}:{cid}"] = r5.champion_matches(traj, g)
                oh = load_oracle_hits(log_ds, arm_dir)
                for cid, hit in oh.items():
                    ora_hits[f"{sl}:{cid}"] = hit
            if not ora_hits:
                print(f"skip {arm_dir} {dkey}: no oracle yet")
                continue
            # align keys
            a = {k: base_hits[k] for k in ora_hits if k in base_hits}
            b = {k: ora_hits[k] for k in a}
            stats = mcnemar(a, b)
            # conversion among cases where gold was injected (all of them)
            block = {
                "intervention": interv,
                "oracle_arm": arm_dir,
                "baseline": base_key,
                "dataset": dkey,
                **stats,
                "conversion": stats["acc_b"],
            }
            report.append(block)
            print(
                f"{interv} {arm_dir:22} {dkey} baseline={stats['acc_a']} "
                f"oracle={stats['acc_b']} {stats['a_only']}-{stats['b_only']} p={stats['p']}"
            )
    r5.write_json(OUT, report)
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
