#!/usr/bin/env python3
"""Summarise R6 probes vs baselines; apply preregistered gates."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import disagreement_census as dc
import r4_lib as r4
import r5_lib as r5
import r6_lib as r6

OUT = r5.OUT / "mosaic_eval" / "r6_probes.json"

# probe_arm_dir -> (baseline_arm_key, probe_family)
SPECS = [
    # X1
    ("r6_x1_forest_pool_mosaic_sel", "forest", "x1"),
    ("r6_x1_forest_pool_aphhm_sel", "forest", "x1"),
    ("r6_x1_c3c_pool_mosaic_sel", "collapse3c", "x1"),
    ("r6_x1_c3c_pool_aphhm_sel", "collapse3c", "x1"),
    # X2/X3/X5
    ("r6_x2_forest", "forest", "x2"),
    ("r6_x2_c3c", "collapse3c", "x2"),
    ("r6_x3_forest", "forest", "x3"),
    ("r6_x3_c3c", "collapse3c", "x3"),
    ("r6_x5_forest", "forest", "x5"),
    ("r6_x5_c3c", "collapse3c", "x5"),
    # X4
    ("r6_x4_forest_s0", "forest", "x4"),
    ("r6_x4_forest_s1", "forest", "x4"),
    ("r6_x4_forest_s2", "forest", "x4"),
    ("r6_x4_c3c_s0", "collapse3c", "x4"),
    ("r6_x4_c3c_s1", "collapse3c", "x4"),
    ("r6_x4_c3c_s2", "collapse3c", "x4"),
]


def load_probe_hits(log_ds: str, arm_dir: str) -> dict[str, bool]:
    d = r5.LOGS / log_ds / arm_dir / "case_stages"
    out = {}
    if not d.is_dir():
        return out
    for p in d.glob("*.json"):
        doc = json.loads(p.read_text())
        gold = str(doc.get("gold") or "")
        champ = str(doc.get("champion") or "")
        cid = str(doc.get("source_id") or p.stem)
        out[cid] = bool(gold and champ and dc.match(champ, gold))
    return out


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
    n = a_only + b_only
    p = 1.0
    if n:
        try:
            from scipy.stats import binomtest

            p = float(binomtest(min(a_only, b_only), n, 0.5).pvalue)
        except Exception:
            p = 1.0
    return {
        "n": len(shared),
        "a_only": a_only,
        "b_only": b_only,
        "both": both,
        "neither": neither,
        "acc_baseline": round(sum(a[k] for k in shared) / len(shared), 4) if shared else None,
        "acc_probe": round(sum(b[k] for k in shared) / len(shared), 4) if shared else None,
        "delta": round(
            (sum(b[k] for k in shared) - sum(a[k] for k in shared)) / len(shared), 4
        )
        if shared
        else None,
        "p": round(p, 6),
    }


def main() -> int:
    gold = r5.load_gold()
    # noise floors from winsets if present
    win_sum = {}
    wp = r6.R6_OUT / "summary.json"
    if wp.is_file():
        win_sum = json.loads(wp.read_text())
    floor = win_sum.get("noise_floor_exclusive") or 0.15

    results = []
    for arm_dir, base, fam in SPECS:
        for dkey in ("da", "mcr"):
            base_hits: dict[str, bool] = {}
            probe_hits: dict[str, bool] = {}
            for log_ds, dk, sl in r6.DEV_SLICES:
                if dk != dkey:
                    continue
                for cid in [c for (dd, ss, c), _ in gold.items() if dd == dk and ss == sl]:
                    g = gold[(dk, sl, cid)]
                    traj = r5.load_trajectory(log_ds, base, cid)
                    if traj.get("raw_available"):
                        base_hits[f"{sl}:{cid}"] = r5.champion_matches(traj, g)
                ph = load_probe_hits(log_ds, arm_dir)
                for cid, hit in ph.items():
                    probe_hits[f"{sl}:{cid}"] = hit
            if not probe_hits:
                print(f"skip {arm_dir} {dkey}: missing")
                continue
            a = {k: base_hits[k] for k in probe_hits if k in base_hits}
            b = {k: probe_hits[k] for k in a}
            stats = mcnemar(a, b)
            block = {
                "probe_arm": arm_dir,
                "baseline": base,
                "family": fam,
                "dataset": dkey,
                **stats,
                "significant": bool(stats["p"] is not None and stats["p"] < 0.05),
            }
            results.append(block)
            print(
                f"{fam} {arm_dir:32} {dkey} base={stats['acc_baseline']} "
                f"probe={stats['acc_probe']} Δ={stats['delta']} p={stats['p']}"
            )

    # X1 interpretation
    x1 = [r for r in results if r["family"] == "x1"]
    x1_gate = {}
    for dkey in ("da", "mcr"):
        def get(name):
            return next(
                (r for r in x1 if r["dataset"] == dkey and r["probe_arm"] == name), None
            )

        fm = get("r6_x1_forest_pool_mosaic_sel")
        fa = get("r6_x1_forest_pool_aphhm_sel")
        cm = get("r6_x1_c3c_pool_mosaic_sel")
        ca = get("r6_x1_c3c_pool_aphhm_sel")
        forest_base = (fm or {}).get("acc_baseline")
        c3c_base = (ca or {}).get("acc_baseline")
        # advantage in generator if forest_pool+aphhm_sel ≈ forest_base
        # advantage in selector if forest_pool+aphhm_sel ≈ c3c_base
        fa_acc = (fa or {}).get("acc_probe")
        verdict = "inconclusive"
        if fa_acc is not None and forest_base is not None and c3c_base is not None:
            d_f = abs(fa_acc - forest_base)
            d_c = abs(fa_acc - c3c_base)
            if d_f + 0.03 < d_c and d_f <= floor:
                verdict = "advantage_in_generator"
            elif d_c + 0.03 < d_f and d_c <= floor:
                verdict = "advantage_in_selector"
            elif abs(d_f - d_c) <= 0.03:
                verdict = "mixed_or_interaction"
            else:
                verdict = "partial_both"
        x1_gate[dkey] = {
            "forest_base": forest_base,
            "c3c_base": c3c_base,
            "forest_pool_aphhm_sel": fa_acc,
            "forest_pool_mosaic_sel": (fm or {}).get("acc_probe"),
            "c3c_pool_mosaic_sel": (cm or {}).get("acc_probe"),
            "c3c_pool_aphhm_sel": (ca or {}).get("acc_probe"),
            "verdict": verdict,
            "noise_floor": floor,
        }

    # X3 gate
    x3_gate = {}
    for dkey in ("da", "mcr"):
        for arm_dir, base in (("r6_x3_forest", "forest"), ("r6_x3_c3c", "collapse3c")):
            r = next(
                (x for x in results if x["probe_arm"] == arm_dir and x["dataset"] == dkey),
                None,
            )
            if not r:
                continue
            x3_gate[f"{base}:{dkey}"] = {
                "delta": r["delta"],
                "p": r["p"],
                "sibling_confound_supported": bool(
                    r["delta"] is not None and r["delta"] > 0.02 and r["p"] < 0.05
                ),
            }

    # X4 order sensitivity: variance across seeds
    x4_gate = {}
    for base in ("forest", "collapse3c"):
        for dkey in ("da", "mcr"):
            accs = [
                r["acc_probe"]
                for r in results
                if r["family"] == "x4"
                and r["dataset"] == dkey
                and r["baseline"] == base
                and r["acc_probe"] is not None
            ]
            if len(accs) >= 2:
                spread = max(accs) - min(accs)
                x4_gate[f"{base}:{dkey}"] = {
                    "accs": accs,
                    "spread": round(spread, 4),
                    "order_sensitive": spread > 0.03,
                    "requires_r5_j_correction": spread > 0.03,
                }

    report = {
        "results": results,
        "gates": {
            "x1": x1_gate,
            "x3": x3_gate,
            "x4": x4_gate,
        },
        "noise_floor_exclusive": floor,
    }
    r6.write_json(OUT, report)
    print("X1 gates:", json.dumps(x1_gate, indent=2))
    print("X3 gates:", json.dumps(x3_gate, indent=2))
    print("X4 gates:", json.dumps(x4_gate, indent=2))
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
