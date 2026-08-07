#!/usr/bin/env python3
"""Batch 0-Z2: export DA A/B/C/D funnel case list for S4-c design.

Read-only over AB02 artifacts; writes only under analysis/backbone_v1/.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "paper"))
from mapper_bind_repair import leaf_match_score  # noqa: E402

OUT = Path(__file__).resolve().parent
BASE = ROOT / "logs/diagnosisarena_d2_m01_v1/c3_ab02_v1/annotate"
CACHE = BASE / "cache"
TREES = BASE / "shared_trees"
PRE = BASE / "pre_compat_joint"
CASES = ROOT / "data/benchmarks/diagnosisarena/subsets/d2_seq100_v1/cases.parquet"


def _hit(target: str, items: list[str], thr: float = 0.7) -> bool:
    return any(leaf_match_score(target, x) >= thr for x in items)


def main() -> None:
    df = pd.read_parquet(CASES)
    gold = {str(r["id"]): str(r["Final Diagnosis"]) for _, r in df.iterrows()}
    funnel = Counter()
    rows: list[dict] = []

    for cid, g in gold.items():
        cache_path = CACHE / cid / "l2_llm_cache.json"
        tree_path = TREES / f"{cid}.json"
        pre_path = PRE / f"{cid}.json"
        if not cache_path.is_file() or not tree_path.is_file() or not pre_path.is_file():
            continue
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
        lists = [
            list(v.get("differentials") or [])
            for v in cache.values()
            if isinstance(v, dict) and "differentials" in v
        ]
        if not lists:
            continue
        first = lists[0]
        pre = json.loads(pre_path.read_text(encoding="utf-8"))
        labs = (pre.get("post_compat_ref") or {}).get("final_ranking_labels") or []
        final = labs[0]["label"] if labs else None
        br = json.loads(tree_path.read_text(encoding="utf-8"))["state"]["branches"]
        leaf_rows = [
            v
            for v in (br.values() if isinstance(br, dict) else br)
            if isinstance(v, dict) and v.get("level") == 2
        ]
        leaves = [v["label"] for v in leaf_rows]
        in_first = _hit(g, first)
        in_leaf = _hit(g, leaves)
        final_ok = bool(final) and leaf_match_score(g, final) >= 0.7
        ddx1_ok = bool(first) and leaf_match_score(g, first[0]) >= 0.7

        if not in_first:
            bucket = "A"
            note = "gold not in first DDx list"
        elif not in_leaf:
            bucket = "B"
            note = "recalled but dropped by entity/leaf filter"
        elif not final_ok:
            bucket = "C"
            note = "in leaf set but scoring selected wrong entity"
        else:
            bucket = "D"
            note = "held through pipeline"
        funnel[bucket] += 1

        # gold rank in first list
        gold_rank = None
        for i, x in enumerate(first, 1):
            if leaf_match_score(g, x) >= 0.7:
                gold_rank = i
                break

        rows.append({
            "case_id": cid,
            "bucket": bucket,
            "note": note,
            "gold": g,
            "ddx_first_item": first[0] if first else None,
            "ddx1_lexical_ok": ddx1_ok,
            "gold_rank_in_first": gold_rank,
            "n_first": len(first),
            "leaves": leaves,
            "n_leaves": len(leaves),
            "pipeline_final": final,
            "final_lexical_ok": final_ok,
            "lateral_jump_suspect": (
                bucket == "C"
                and ddx1_ok
                and bool(final)
                and leaf_match_score(first[0], final) < 0.7
            ),
        })

    rows.sort(key=lambda r: (r["bucket"], r["case_id"]))
    summary = {
        "n_cases": len(rows),
        "funnel": dict(funnel),
        "c_bucket_lateral_jumps": sum(1 for r in rows if r["lateral_jump_suspect"]),
        "criterion": "leaf_match_score(gold_free_text, pred) >= 0.7",
        "source": "c3_ab02_v1 annotate",
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    (OUT / "z2_da_funnel.json").write_text(
        json.dumps({"summary": summary, "rows": rows}, indent=2, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )
    # human-readable C-bucket design sheet
    lines = [
        "# DA funnel design sheet (AB02)",
        "",
        f"n={summary['n_cases']}  funnel={summary['funnel']}",
        f"C-bucket lateral jumps (ddx1 correct, final wrong & unrelated): "
        f"{summary['c_bucket_lateral_jumps']}",
        "",
        "## C-bucket cases (scoring errors)",
        "",
    ]
    for r in rows:
        if r["bucket"] != "C":
            continue
        lines.append(
            f"- case {r['case_id']}: gold=`{r['gold']}` | "
            f"ddx1=`{r['ddx_first_item']}` | "
            f"final=`{r['pipeline_final']}` | "
            f"lateral={r['lateral_jump_suspect']} | leaves={r['leaves']}"
        )
    lines.append("")
    lines.append("## B-bucket cases (filter drops)")
    lines.append("")
    for r in rows:
        if r["bucket"] != "B":
            continue
        lines.append(
            f"- case {r['case_id']}: gold=`{r['gold']}` | "
            f"ddx1=`{r['ddx_first_item']}` | leaves={r['leaves']}"
        )
    (OUT / "z2_da_funnel.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
