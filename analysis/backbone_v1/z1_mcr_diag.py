#!/usr/bin/env python3
"""Batch 0-Z1: zero-call MCR diagnostics mirroring DA backbone probes.

Read-only over MCR compat_synonym_v1 caches/trees; writes only under
analysis/backbone_v1/.
"""
from __future__ import annotations

import json
import os
import statistics
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "paper"))
from mapper_bind_repair import leaf_match_score  # noqa: E402

OUT = Path(__file__).resolve().parent
ANN = ROOT / "logs/medcasereasoning_mcr_val_seq100_v1/compat_synonym_v1/annotate"
CASES = ROOT / "data/benchmarks/medcasereasoning/subsets/mcr_val_seq100_v1/normalized_cases.json"
CACHE = ANN / "cache"
TREES = ANN / "shared_trees"
PRE = ANN / "pre_compat_joint"


def _norm(s: str) -> str:
    return " ".join(str(s).lower().split())


def _hit(target: str, items: list[str], thr: float = 0.7) -> bool:
    return any(leaf_match_score(target, x) >= thr for x in items)


def main() -> None:
    gold = {
        str(c["id"]): str(c["gold"])
        for c in json.loads(CASES.read_text(encoding="utf-8"))["cases"]
    }
    n_calls: list[int] = []
    cover_first = cover_union = label_from_first = label_from_union = 0
    first_top1 = pipe_lexical = 0
    funnel = Counter()
    rows: list[dict] = []
    n = 0

    for cid, g in gold.items():
        cache_path = CACHE / cid / "l2_llm_cache.json"
        tree_path = TREES / f"{cid}.json"
        pre_path = PRE / f"{cid}.json"
        if not cache_path.is_file() or not tree_path.is_file():
            continue
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
        lists = [
            list(v.get("differentials") or [])
            for v in cache.values()
            if isinstance(v, dict) and "differentials" in v
        ]
        if not lists:
            continue
        n += 1
        n_calls.append(len(lists))
        first, union = lists[0], [x for L in lists for x in L]
        in_first = _hit(g, first)
        in_union = _hit(g, union)
        cover_first += int(in_first)
        cover_union += int(in_union)
        first_top1 += int(bool(first) and leaf_match_score(g, first[0]) >= 0.7)

        # final label from pre_compat or tree level-2 argmax-ish first ranking
        final = None
        if pre_path.is_file():
            pre = json.loads(pre_path.read_text(encoding="utf-8"))
            labs = (pre.get("post_compat_ref") or {}).get("final_ranking_labels") or []
            if labs:
                final = labs[0].get("label")
            if not final:
                labs = (pre.get("pre_compat") or {}).get("final_ranking_labels") or []
                if labs:
                    final = labs[0].get("label")
        br = json.loads(tree_path.read_text(encoding="utf-8"))["state"]["branches"]
        leaves = [
            v["label"]
            for v in (br.values() if isinstance(br, dict) else br)
            if isinstance(v, dict) and v.get("level") == 2
        ]
        if not final and leaves:
            # fall back: highest posterior leaf
            ranked = sorted(
                (
                    v
                    for v in (br.values() if isinstance(br, dict) else br)
                    if isinstance(v, dict) and v.get("level") == 2
                ),
                key=lambda v: float(v.get("posterior") or 0.0),
                reverse=True,
            )
            final = ranked[0]["label"] if ranked else None

        from_first = bool(final) and _hit(final, first)
        from_union = bool(final) and _hit(final, union)
        label_from_first += int(from_first)
        label_from_union += int(from_union)
        final_ok = bool(final) and leaf_match_score(g, final) >= 0.7
        pipe_lexical += int(final_ok)
        in_leaf = _hit(g, leaves)

        if not in_first:
            bucket = "A"
        elif not in_leaf:
            bucket = "B"
        elif not final_ok:
            bucket = "C"
        else:
            bucket = "D"
        funnel[bucket] += 1
        rows.append({
            "case_id": cid,
            "gold": g,
            "n_ddx_calls": len(lists),
            "first_size": len(first),
            "union_size": len(set(_norm(x) for x in union)),
            "gold_in_first": in_first,
            "gold_in_union": in_union,
            "final_label": final,
            "final_from_first": from_first,
            "final_from_union": from_union,
            "final_lexical_ok": final_ok,
            "n_leaves": len(leaves),
            "bucket": bucket,
        })

    summary = {
        "n_cases": n,
        "note": "MCR slice1 compat_synonym_v1; lexical proxy leaf_match_score>=0.7; "
                "not Prompt-7 Acc (0.50 published).",
        "ddx_calls": {
            "mean": round(statistics.mean(n_calls), 2) if n_calls else None,
            "median": statistics.median(n_calls) if n_calls else None,
            "min": min(n_calls) if n_calls else None,
            "max": max(n_calls) if n_calls else None,
            "total": sum(n_calls),
        },
        "coverage": {
            "gold_in_first_list": round(cover_first / max(1, n), 3),
            "gold_in_union": round(cover_union / max(1, n), 3),
            "first_item_lexical": round(first_top1 / max(1, n), 3),
            "pipeline_final_lexical": round(pipe_lexical / max(1, n), 3),
            "final_label_from_first": round(label_from_first / max(1, n), 3),
            "final_label_from_union": round(label_from_union / max(1, n), 3),
        },
        "funnel": dict(funnel),
        "compare_to_da": {
            "da_ddx_calls_mean": 5.63,
            "da_gold_in_first": 0.86,
            "da_first_item_lexical": 0.50,
            "da_pipeline_final_lexical": 0.64,
        },
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    (OUT / "z1_mcr_diag.json").write_text(
        json.dumps({"summary": summary, "rows": rows}, indent=2, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
