#!/usr/bin/env python3
"""Phase 3c: APHHM prune step audit vs e7 S3 prune isomorphism."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import disagreement_census as dc
import r4_lib as r4

OUT = r4.OUT / "r4_internal"


def audit_prune_cases(limit: int = 77) -> dict:
    rows = r4.load_tsv(r4.R4 / "pooled.tsv")
    prune = [
        r
        for r in rows
        if (r.get("APHHM_locus") or "") == "tree_hit_final_drop"
    ]
    details = []
    for r in prune[:limit]:
        ds, sl, cid = r["dataset"], r["slice"], r["case_id"]
        slices = dc.DA_SLICES if ds == "da" else dc.MCR_SLICES
        spec = slices.get(sl) or {}
        ann = spec.get("APHHM")
        if not ann:
            continue
        ann_dir = dc.ROOT / ann
        cr = ann_dir / "case_results" / f"{cid}.json"
        if not cr.is_file():
            continue
        doc = json.loads(cr.read_text(encoding="utf-8"))
        l2 = doc.get("l2") or {}
        fidelity = l2.get("leaf_score_fidelity") or []
        final_ids = l2.get("final_ranking_ids") or []
        final_labels = l2.get("final_ranking_labels") or []
        gran = l2.get("granularity") or {}
        gate = gran.get("gate") or {}
        # gold leaf present?
        gold = r.get("gold") or ""
        gold_leaf = r.get("APHHM_gold_leaf") or ""
        # fidelity: was gold leaf's posterior reduced?
        gold_fid = None
        for leaf in fidelity:
            lab = str(leaf.get("label") or "")
            if gold_leaf and lab.lower() == str(gold_leaf).lower():
                gold_fid = leaf
                break
            if gold and dc.match(lab, gold):
                gold_fid = leaf
                break
        details.append(
            {
                "dataset": ds,
                "slice": sl,
                "case_id": cid,
                "gold": gold,
                "gold_leaf": gold_leaf,
                "tree_n": r.get("APHHM_tree_n"),
                "final_n": len(final_ids),
                "final_top1": (final_labels[0].get("label") if final_labels else None),
                "gate_triggered": gate.get("triggered"),
                "gate_top1_crowd": gate.get("top1_crowd"),
                "gate_n_clusters": gate.get("n_clusters"),
                "gold_pre_posterior": (gold_fid or {}).get("pre_posterior"),
                "gold_post_posterior": (gold_fid or {}).get("post_posterior"),
                "gold_capped_out": (gold_fid or {}).get("capped_out"),
                "e7_locus": r.get("e7_locus") or r.get("tax_e7_locus"),
                "e7_chain_correct": r.get("e7_chain_correct"),
                "e7_scored_correct": r.get("e7_scored_correct"),
            }
        )

    capped = sum(1 for d in details if d.get("gold_capped_out"))
    gate_trig = sum(1 for d in details if d.get("gate_triggered"))
    # isomorphism proxy: e7 also dropped gold at S3 on same cases
    e7_s3_drop = sum(
        1 for d in details if d.get("e7_locus") == "s2_hit_s3_drop"
    )
    e7_s4_miss = sum(
        1 for d in details if d.get("e7_locus") == "s3_hit_s4_miss"
    )
    e7_s2_miss = sum(1 for d in details if d.get("e7_locus") == "s2_miss")
    e7_ok = sum(1 for d in details if d.get("e7_locus") == "ok")

    return {
        "n_prune": len(prune),
        "n_audited": len(details),
        "gold_capped_out_n": capped,
        "granularity_gate_triggered_n": gate_trig,
        "e7_locus_on_prune": {
            "s2_miss": e7_s2_miss,
            "s2_hit_s3_drop": e7_s3_drop,
            "s3_hit_s4_miss": e7_s4_miss,
            "ok": e7_ok,
        },
        "isomorphism_claim": (
            "If e7_locus is dominated by s2_hit_s3_drop / s3_hit_s4_miss on the same "
            "prune cohort, APHHM final prune and e7 S3/S4 share the same near-synonym "
            "ranking disease — hierarchy does not uniquely cause the loss."
        ),
        "details_head": details[:15],
    }, details


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    summary, details = audit_prune_cases()
    r4.write_tsv(OUT / "aphhm_prune_detail.tsv", details)
    (OUT / "aphhm_prune_summary.json").write_text(
        json.dumps({k: v for k, v in summary.items() if k != "details_head"}, indent=2)
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps({k: v for k, v in summary.items() if k != "details_head"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
