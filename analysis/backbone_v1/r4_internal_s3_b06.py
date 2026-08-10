#!/usr/bin/env python3
"""Phase 3a: S3 prune decision table + B06 supervisor turn alignment.

Zero LLM. Writes analysis/backbone_v1/r4_internal/.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

import disagreement_census as dc
import r3_lib as r3
import r4_lib as r4

OUT = r4.OUT / "r4_internal"


def s3_analysis(rows: list[dict]) -> dict:
    """Among e7 s2_hit_s3_drop, is drop driven by rank / near-crowd / k=5?"""
    drop = [r for r in rows if (r.get("e7_locus") or r.get("tax_e7_locus")) == "s2_hit_s3_drop"]
    ok = [r for r in rows if (r.get("e7_locus") or r.get("tax_e7_locus")) == "ok"]
    s4miss = [r for r in rows if (r.get("e7_locus") or r.get("tax_e7_locus")) == "s3_hit_s4_miss"]

    def ranks(rs):
        vals = []
        for r in rs:
            v = r.get("tax_e7_s2_rank_gold")
            try:
                vals.append(int(float(v)))
            except Exception:
                pass
        return vals

    drop_ranks = ranks(drop)
    ok_ranks = ranks(ok)
    s4_ranks = ranks(s4miss)

    # why_kept mentions for drop cases — need stage files
    detail = []
    for r in drop[:200]:  # cap IO
        ds, sl, cid = r["dataset"], r["slice"], r["case_id"]
        slices = dc.DA_SLICES if ds == "da" else dc.MCR_SLICES
        spec = slices.get(sl)
        if not spec:
            continue
        bb = r3.extract_backbone(dc.ROOT / spec["e7"], cid)
        r3.fill_s2_rank(bb, r.get("gold") or "")
        gold_in_s3 = any(dc.match(x, r.get("gold") or "") for x in bb.get("s3") or [])
        detail.append(
            {
                "dataset": ds,
                "slice": sl,
                "case_id": cid,
                "gold": r.get("gold"),
                "s2_rank_gold": bb.get("s2_rank_gold"),
                "s2_n": len(bb.get("s2") or []),
                "s3": bb.get("s3"),
                "s3_why": bb.get("s3_why"),
                "gold_in_s3": gold_in_s3,
                "fail_code": r.get("tax_e7_fail_code"),
            }
        )

    rank_gt5 = sum(1 for x in drop_ranks if x > 5)
    return {
        "n_s2_hit_s3_drop": len(drop),
        "n_ok": len(ok),
        "n_s3_hit_s4_miss": len(s4miss),
        "drop_s2_rank_mean": (sum(drop_ranks) / len(drop_ranks)) if drop_ranks else None,
        "ok_s2_rank_mean": (sum(ok_ranks) / len(ok_ranks)) if ok_ranks else None,
        "s4miss_s2_rank_mean": (sum(s4_ranks) / len(s4_ranks)) if s4_ranks else None,
        "drop_rank_gt5_share": rank_gt5 / len(drop_ranks) if drop_ranks else None,
        "drop_rank_le5_share": (
            sum(1 for x in drop_ranks if x <= 5) / len(drop_ranks) if drop_ranks else None
        ),
        "interpretation": (
            "If drop_rank_le5_share is high, k=5 hard truncate is NOT the main driver "
            "(gold was already in top-5 of S2 but S3 still dropped it). "
            "If drop_rank_gt5_share dominates, hard truncate / low rank explains most drops."
        ),
        "detail_n": len(detail),
    }, detail


def b06_analysis(rows: list[dict]) -> dict:
    """Supervisor turn-level alignment on base_win_rank and mapper-rescue."""
    base_win_rank = [r for r in rows if (r.get("layer_chain") or "") == "base_win_rank"]
    # DA supervisor_miss_but_scored_ok
    rescue_locus = [
        r
        for r in rows
        if r.get("dataset") == "da"
        and (r.get("B06_locus") or "") == "supervisor_miss_but_scored_ok"
    ]
    turns = []
    for r in rows:
        t = r.get("B06_gold_first_discussion_turn")
        try:
            turns.append(int(t))
        except Exception:
            pass
    turn_ct = Counter(turns)
    # among base_win_rank: supervisor hit rate
    bwr_sup = sum(1 for r in base_win_rank if r4.truthy(r.get("B06_supervisor_hit")))
    return {
        "base_win_rank_n": len(base_win_rank),
        "base_win_rank_b06_supervisor_hit": bwr_sup,
        "base_win_rank_b06_supervisor_hit_rate": (
            bwr_sup / len(base_win_rank) if base_win_rank else None
        ),
        "da_supervisor_miss_but_scored_ok_n": len(rescue_locus),
        "da_supervisor_miss_but_scored_ok_share": len(rescue_locus)
        / max(sum(1 for r in rows if r.get("dataset") == "da"), 1),
        "gold_first_discussion_turn_hist": dict(sorted(turn_ct.items())),
        "note": (
            "supervisor_miss_but_scored_ok on DA is the mapper-rescue twin of e7_mapper_rescue; "
            "under chain_correct these should not count as B06 wins."
        ),
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = r4.load_tsv(r4.R4 / "pooled.tsv")
    s3_sum, detail = s3_analysis(rows)
    r4.write_tsv(OUT / "s3_drop_detail.tsv", detail)
    b06 = b06_analysis(rows)
    summary = {"s3": s3_sum, "b06": b06}
    (OUT / "s3_b06_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False)[:2000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
