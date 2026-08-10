#!/usr/bin/env python3
"""Summarize R7 large-scale arms: chain/near-match, replicate nulls, vs baselines."""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional

import disagreement_census as dc
import r3_lib as r3
import r5_lib as r5
import r6_lib as r6

OUT = r5.OUT / "mosaic_eval" / "r7_scale"
OUT.mkdir(parents=True, exist_ok=True)

# Map logical arm -> (log_ds naming via r5.SLICES, directory name under logs)
EXTRA_ARMS = {
    "compact_forest": "compact_forest_v0",
    "compact_forest_r2": "compact_forest_v0_r2",
    "collapse3c_nd": "aphhm_c_collapse3c_neardedup",
    "multistance_nd": "aphhm_c_multistance_neardedup",
    "forest": "mosaic_forest_v1",
    "forest_r2": "mosaic_forest_r2",
    "collapse3c": "aphhm_c_collapse3c_v1",
    "collapse3c_r2": "aphhm_c_collapse3c_r2",
    "multistance": "aphhm_c_multistance_v1",
}


def cluster_rel(a: str, b: str) -> str:
    if not a or not b:
        return "unrelated"
    if dc.match(a, b):
        return "chain"
    if a.lower() in b.lower() or b.lower() in a.lower():
        return "parent_subtype"
    if r3.near_gold(a, b):
        return "near_sibling"
    return "unrelated"


def load_champ(log_ds: str, arm_dir: str, cid: str) -> Optional[str]:
    d = r5.ROOT / "logs" / "backbone_v1" / log_ds / arm_dir
    if not d.is_dir():
        return None
    for key in (cid, cid.lstrip("0") or "0"):
        p = d / "case_stages" / f"{key}.json"
        if p.is_file():
            doc = json.loads(p.read_text(encoding="utf-8"))
            return str(doc.get("champion") or (doc.get("ordered_diagnoses") or [""])[0] or "")
        if cid.isdigit():
            p2 = d / "case_stages" / f"{int(cid)}.json"
            if p2.is_file():
                doc = json.loads(p2.read_text(encoding="utf-8"))
                return str(doc.get("champion") or (doc.get("ordered_diagnoses") or [""])[0] or "")
    # predictions.jsonl fallback
    pred = d / "predictions.jsonl"
    if pred.is_file():
        for line in pred.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            sid = str(row.get("source_id") or row.get("case_id") or "")
            if sid == cid or (cid.isdigit() and sid.lstrip("0") == cid.lstrip("0")):
                od = row.get("ordered_diagnoses") or []
                return str(od[0] if od else row.get("champion") or "")
    return None


def eval_arm(arm_key: str) -> dict[str, Any]:
    arm_dir = EXTRA_ARMS[arm_key]
    gold = r5.load_gold()
    n = chain = near = parent = missing = 0
    by_slice: dict[str, dict] = defaultdict(lambda: {"n": 0, "chain": 0, "near": 0})
    for log_ds, dkey, sl in r5.SLICES:
        for cid in [c for (dd, ss, c), _ in gold.items() if dd == dkey and ss == sl]:
            g = gold[(dkey, sl, cid)]
            champ = load_champ(log_ds, arm_dir, cid)
            if champ is None:
                missing += 1
                continue
            n += 1
            by_slice[f"{dkey}/{sl}"]["n"] += 1
            rel = cluster_rel(champ, g)
            if rel == "chain":
                chain += 1
                near += 1
                parent += 1
                by_slice[f"{dkey}/{sl}"]["chain"] += 1
                by_slice[f"{dkey}/{sl}"]["near"] += 1
            elif rel == "parent_subtype":
                near += 1
                parent += 1
                by_slice[f"{dkey}/{sl}"]["near"] += 1
            elif rel == "near_sibling":
                near += 1
                by_slice[f"{dkey}/{sl}"]["near"] += 1
    return {
        "arm_dir": arm_dir,
        "n": n,
        "missing": missing,
        "chain": round(chain / n, 4) if n else None,
        "near_match": round(near / n, 4) if n else None,
        "parent_or_chain": round(parent / n, 4) if n else None,
        "near_minus_chain": round((near - chain) / n, 4) if n else None,
        "by_slice": {
            k: {
                "n": v["n"],
                "chain": round(v["chain"] / v["n"], 4) if v["n"] else None,
                "near": round(v["near"] / v["n"], 4) if v["n"] else None,
            }
            for k, v in sorted(by_slice.items())
        },
    }


def replicate_null(a_key: str, b_key: str, slices: Optional[set[str]] = None) -> dict[str, Any]:
    """Exclusive rate between two arms on overlapping cases."""
    gold = r5.load_gold()
    a_dir, b_dir = EXTRA_ARMS[a_key], EXTRA_ARMS[b_key]
    n = a_only = b_only = both = 0
    for log_ds, dkey, sl in r5.SLICES:
        if slices and f"{dkey}/{sl}" not in slices:
            continue
        for cid in [c for (dd, ss, c), _ in gold.items() if dd == dkey and ss == sl]:
            g = gold[(dkey, sl, cid)]
            ca = load_champ(log_ds, a_dir, cid)
            cb = load_champ(log_ds, b_dir, cid)
            if ca is None or cb is None:
                continue
            ha = bool(dc.match(ca, g))
            hb = bool(dc.match(cb, g))
            n += 1
            if ha and not hb:
                a_only += 1
            elif hb and not ha:
                b_only += 1
            elif ha and hb:
                both += 1
    return {
        "n": n,
        "a_only": a_only,
        "b_only": b_only,
        "both": both,
        "exclusive_either_rate": round((a_only + b_only) / n, 4) if n else None,
        "a_excl_rate": round(a_only / n, 4) if n else None,
        "b_excl_rate": round(b_only / n, 4) if n else None,
        "stable_both_rate": round(both / n, 4) if n else None,
        "jaccard": round(both / (a_only + b_only + both), 4) if (a_only + b_only + both) else None,
    }


def main() -> int:
    arms = list(EXTRA_ARMS)
    report: dict[str, Any] = {"arms": {}, "replicates": {}, "comparisons": {}}
    for a in arms:
        print("eval", a)
        report["arms"][a] = eval_arm(a)
        print(" ", report["arms"][a]["n"], report["arms"][a]["chain"], report["arms"][a]["near_match"])

    report["replicates"]["compact_forest"] = replicate_null("compact_forest", "compact_forest_r2")
    report["replicates"]["forest_200b"] = replicate_null(
        "forest",
        "forest_r2",
        slices={"da/d2_heldout200b", "mcr/mcr_200b"},
    )
    report["replicates"]["collapse3c_200b"] = replicate_null(
        "collapse3c",
        "collapse3c_r2",
        slices={"da/d2_heldout200b", "mcr/mcr_200b"},
    )
    # also full overlap if r2 exists beyond 200b
    report["replicates"]["forest_all_overlap"] = replicate_null("forest", "forest_r2")
    report["replicates"]["collapse3c_all_overlap"] = replicate_null("collapse3c", "collapse3c_r2")

    report["comparisons"]["compact_vs_forest"] = replicate_null("compact_forest", "forest")
    report["comparisons"]["compact_vs_collapse3c"] = replicate_null("compact_forest", "collapse3c")
    report["comparisons"]["c3c_nd_vs_c3c"] = replicate_null("collapse3c_nd", "collapse3c")
    report["comparisons"]["ms_nd_vs_ms"] = replicate_null("multistance_nd", "multistance")

    # load specialty if present
    sp = OUT / "specialty_q6.json"
    if sp.is_file():
        report["specialty_q6"] = json.loads(sp.read_text(encoding="utf-8"))

    noise = 0.113
    report["noise_floor_ref"] = noise
    report["verdict"] = {
        "compact_reaches_forest": (
            (report["arms"]["compact_forest"].get("chain") or 0)
            >= (report["arms"]["forest"].get("chain") or 0) - 0.02
        ),
        "compact_beats_collapse3c": (
            (report["arms"]["compact_forest"].get("chain") or 0)
            > (report["arms"]["collapse3c"].get("chain") or 0) + 0.02
        ),
        "c3c_nd_helps": (
            (report["arms"]["collapse3c_nd"].get("chain") or 0)
            > (report["arms"]["collapse3c"].get("chain") or 0) + 0.01
        ),
        "ms_nd_helps": (
            (report["arms"]["multistance_nd"].get("chain") or 0)
            > (report["arms"]["multistance"].get("chain") or 0) + 0.01
        ),
        "compact_replicate_below_floor": (
            (report["replicates"]["compact_forest"].get("exclusive_either_rate") or 1) < noise
        ),
    }
    r6.write_json(OUT / "summary.json", report)
    print(json.dumps(report["verdict"], indent=2))
    print(json.dumps(report["replicates"], indent=2))
    print(f"wrote {OUT / 'summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
