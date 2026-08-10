#!/usr/bin/env python3
"""R5 stability gate from same-config replicates.

Any locus-rate difference smaller than the per-case flip rate between two
identical runs is marked unresolved. Uses multistance_v1/r2 (already done) plus
collapse3c/forest/lite/impc r2 arms when present.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import disagreement_census as dc
import r5_lib as r5
import r5_locus as locus

OUT = r5.OUT / "mosaic_eval" / "r5_stability.json"

# (label, primary_arm_key, replicate_dir_name under logs/backbone_v1/<slice>/)
PAIRS = [
    ("multistance", "multistance", "aphhm_c_multistance_r2"),
    ("collapse3c", "collapse3c", "aphhm_c_collapse3c_r2"),
    ("lite", "lite", "mosaic_lite_r2"),
    ("forest", "forest", "mosaic_forest_r2"),
    ("impc", "impc", "mosaic_impc_r2"),
]

DEV_SLICES = [
    ("diagnosisarena", "da", "d2_seq100"),
    ("diagnosisarena_heldout", "da", "d2_heldout100"),
    ("medcasereasoning", "mcr", "mcr_v1"),
    ("medcasereasoning_v2", "mcr", "mcr_v2"),
]


def load_traj_from_dir(log_ds: str, dir_name: str, cid: str, arm_key: str) -> dict[str, Any]:
    d = r5.LOGS / log_ds / dir_name
    if not d.is_dir():
        return r5._empty_traj(arm_key, r5.FOCUS_ARMS[arm_key]["family"])
    doc = r5.load_case_stages(d, cid)
    if not doc:
        return r5._empty_traj(arm_key, r5.FOCUS_ARMS[arm_key]["family"])
    fam = r5.FOCUS_ARMS[arm_key]["family"]
    if fam == "aphhm_c":
        return r5.adapt_aphhm_c(doc, arm_key)
    if fam == "mosaic":
        return r5.adapt_mosaic(doc, arm_key)
    return r5._empty_traj(arm_key, fam)


def compare_pair(label: str, arm_key: str, r2_dir: str) -> dict[str, Any] | None:
    gold = r5.load_gold()
    # check r2 exists on at least one slice
    if not any((r5.LOGS / ds / r2_dir / "case_stages").is_dir() for ds, _, _ in DEV_SLICES):
        return None
    n = 0
    champ_same = 0
    locus_same = 0
    pool_jacc = []
    locus_flip = Counter()  # (a->b) counts
    locus_a = Counter()
    locus_b = Counter()
    by_ds: dict[str, dict[str, Any]] = {}
    for dkey in ("da", "mcr"):
        n_ds = champ_ds = loc_ds = 0
        for log_ds, dk, sl in DEV_SLICES:
            if dk != dkey:
                continue
            cids = [cid for (dd, ss, cid), _ in gold.items() if dd == dk and ss == sl]
            for cid in cids:
                g = gold[(dk, sl, cid)]
                ta = r5.load_trajectory(log_ds, arm_key, cid)
                tb = load_traj_from_dir(log_ds, r2_dir, cid, arm_key)
                if not ta.get("raw_available") or not tb.get("raw_available"):
                    continue
                n += 1
                n_ds += 1
                pa = set(dc._norm(x) if hasattr(dc, "_norm") else x.lower() for x in r5.pool_labels(ta))
                # use simple lower key
                pa = {x.lower() for x in r5.pool_labels(ta)}
                pb = {x.lower() for x in r5.pool_labels(tb)}
                if pa | pb:
                    pool_jacc.append(len(pa & pb) / len(pa | pb))
                same_c = bool(ta.get("champion") and tb.get("champion") and dc.match(ta["champion"], tb["champion"]))
                champ_same += int(same_c)
                champ_ds += int(same_c)
                la = locus.assign_locus(ta, g, chain_correct=r5.champion_matches(ta, g))
                lb = locus.assign_locus(tb, g, chain_correct=r5.champion_matches(tb, g))
                locus_a[la["locus"]] += 1
                locus_b[lb["locus"]] += 1
                if la["locus"] == lb["locus"]:
                    locus_same += 1
                    loc_ds += 1
                else:
                    locus_flip[f"{la['locus']}->{lb['locus']}"] += 1
        by_ds[dkey] = {
            "n": n_ds,
            "champion_agree": round(champ_ds / n_ds, 4) if n_ds else None,
            "locus_agree": round(loc_ds / n_ds, 4) if n_ds else None,
        }
    if not n:
        return None
    # per-locus flip rate = fraction of cases where this locus was assigned in a
    # but not in b (or vice versa), / n
    flip_rate = {}
    for b in locus.BUCKETS:
        only_a = locus_a[b]  # rough; better use disagreement
        # cases where a had b xor b had b approximated by |count_a - count_b| / n
        # more honest: count flips involving b
        involving = sum(v for k, v in locus_flip.items() if k.startswith(b + "->") or k.endswith("->" + b))
        flip_rate[b] = round(involving / n, 4)
    return {
        "pair": label,
        "primary": arm_key,
        "replicate_dir": r2_dir,
        "n": n,
        "pool_jaccard_mean": round(sum(pool_jacc) / len(pool_jacc), 4) if pool_jacc else None,
        "champion_agree": round(champ_same / n, 4),
        "locus_agree": round(locus_same / n, 4),
        "locus_flip_rate": flip_rate,
        "locus_flips_top": dict(locus_flip.most_common(12)),
        "locus_rate_primary": {b: round(locus_a[b] / n, 4) for b in locus.BUCKETS},
        "locus_rate_replicate": {b: round(locus_b[b] / n, 4) for b in locus.BUCKETS},
        "by_ds": by_ds,
        # gate: a cross-arm locus-rate delta must exceed this to be resolvable
        "noise_floor_locus": {
            b: round(max(flip_rate.get(b, 0), abs(
                (locus_a[b] / n) - (locus_b[b] / n)
            )), 4)
            for b in locus.BUCKETS
        },
    }


def main() -> int:
    report = []
    for label, arm, r2 in PAIRS:
        block = compare_pair(label, arm, r2)
        if block is None:
            print(f"SKIP {label}: replicate not ready")
            continue
        report.append(block)
        print(
            f"{label:12} n={block['n']} champ_agree={block['champion_agree']} "
            f"locus_agree={block['locus_agree']} jaccard={block['pool_jaccard_mean']}"
        )
        print(f"  noise_floor {block['noise_floor_locus']}")
    # aggregate floor = max across pairs for each bucket
    floor: dict[str, float] = {}
    for b in locus.BUCKETS:
        vals = [p["noise_floor_locus"][b] for p in report if b in p["noise_floor_locus"]]
        floor[b] = round(max(vals), 4) if vals else 0.0
    out = {"pairs": report, "aggregate_noise_floor": floor}
    r5.write_json(OUT, out)
    print("aggregate floor", floor)
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
