#!/usr/bin/env python3
"""Offline L1 family-rank audit for analysis/l1_rank_gap_v1 (protocol v1_auto_parent)."""
from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "analysis" / "l1_rank_gap_v1"

PILOT_CASE = ROOT / "logs/diagnosisarena_d2_m01_v1/downstream_top2_w12_v1/case_results"
PILOT_MAP = ROOT / "logs/diagnosisarena_d2_m01_v1/downstream_top2_w12_v1/mapper/projections"
REMAIN_CASE = ROOT / "logs/diagnosisarena_d2_m01_v1/pipeline_remaining76_v1/annotate/case_results"
REMAIN_MAP = ROOT / "logs/diagnosisarena_d2_m01_v1/pipeline_remaining76_v1/annotate/mapper/projections"


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _norm(s: str) -> str:
    s = (s or "").lower().strip()
    s = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", s)
    return " ".join(s.split())


def labels_synonymish(a: str, b: str) -> bool:
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return False
    if na == nb or na in nb or nb in na:
        return True
    ta, tb = set(na.split()), set(nb.split())
    if not ta or not tb:
        return False
    inter = len(ta & tb)
    return inter >= max(2, min(len(ta), len(tb)) // 2)


def load_ours() -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for cohort, case_dir, map_dir in (
        ("pilot24", PILOT_CASE, PILOT_MAP),
        ("remain76", REMAIN_CASE, REMAIN_MAP),
    ):
        for mp in sorted(map_dir.glob("*.json")):
            cid = mp.stem
            m = json.loads(mp.read_text(encoding="utf-8"))
            cp = case_dir / ("%s.json" % cid)
            c = json.loads(cp.read_text(encoding="utf-8")) if cp.is_file() else {}
            rows[cid] = {"case_id": cid, "cohort": cohort, "mapper": m, "case": c}
    return rows


def gold_leaf_ids(mapper_row: Mapping[str, Any]) -> list[str]:
    letter = str(mapper_row.get("gold_letter") or "").upper()
    om = ((mapper_row.get("projection") or {}).get("option_maps") or {}).get(letter) or {}
    ids = list(om.get("matched_leaf_ids") or ()) + list(om.get("clone_leaf_ids") or ())
    return sorted({str(x) for x in ids if str(x).strip()})


def option_metrics_for_leaf_ranking(
    leaf_ranking: Sequence[str],
    gold_leaves: Sequence[str],
) -> dict[str, Any]:
    gold_set = set(gold_leaves)
    pos = None
    for i, lid in enumerate(leaf_ranking, start=1):
        if lid in gold_set:
            pos = i
            break
    if pos is None:
        return {"option_top1": False, "option_top2": False, "option_rr": 0.0, "gold_leaf_rank": None}
    return {
        "option_top1": pos <= 1,
        "option_top2": pos <= 2,
        "option_rr": 1.0 / pos,
        "gold_leaf_rank": pos,
    }


def build_l1_prior_only(case: Mapping[str, Any]) -> list[str]:
    l1_rows = list((case.get("l1") or {}).get("l1_posteriors") or ())
    labels = list((case.get("l2") or {}).get("final_ranking_labels") or ())
    joint_ids = [str(r.get("id")) for r in labels if r.get("id")]
    by_parent: dict[str, list[str]] = defaultdict(list)
    for r in labels:
        lid = str(r.get("id") or "")
        parent = str(r.get("parent") or "")
        if lid:
            by_parent[parent].append(lid)
    l1_sorted = sorted(
        l1_rows,
        key=lambda r: (-float(r.get("posterior") or 0.0), str(r.get("id") or "")),
    )
    out: list[str] = []
    for row in l1_sorted:
        pid = str(row.get("id") or "")
        kids = by_parent.get(pid) or []
        if not kids:
            continue
        joint_pos = {lid: i for i, lid in enumerate(joint_ids)}
        kids_sorted = sorted(kids, key=lambda x: joint_pos.get(x, 10**9))
        out.append(kids_sorted[0])
    return out


def acceptable_parents(case: Mapping[str, Any], mapper: Mapping[str, Any]) -> dict[str, Any]:
    labels = list((case.get("l2") or {}).get("final_ranking_labels") or ())
    by_id = {str(r.get("id")): r for r in labels if r.get("id")}
    leaf_ids = gold_leaf_ids(mapper)
    parents: set[str] = set()
    sources: list[str] = []
    for lid in leaf_ids:
        row = by_id.get(lid)
        if row and row.get("parent"):
            parents.add(str(row["parent"]))
            sources.append("mapper_leaf_parent")
    if not parents:
        gold_text = " ".join(
            [
                str(mapper.get("gold_option_text") or ""),
                str(mapper.get("gold_diagnosis") or ""),
                str(case.get("gold") or ""),
            ]
        )
        l1_rows = list((case.get("l1") or {}).get("l1_posteriors") or ())
        for row in l1_rows:
            if labels_synonymish(str(row.get("label") or ""), gold_text):
                parents.add(str(row.get("id") or ""))
                sources.append("label_synonym")
    return {
        "acceptable_parent_ids": sorted(parents),
        "gold_leaf_ids": leaf_ids,
        "parent_source": ",".join(sorted(set(sources))) if sources else "none",
    }


def family_metrics(
    l1_rows: Sequence[Mapping[str, Any]],
    acceptable: Sequence[str],
) -> dict[str, Any]:
    ordered = sorted(
        l1_rows,
        key=lambda r: (-float(r.get("posterior") or 0.0), str(r.get("id") or "")),
    )
    ids = [str(r.get("id") or "") for r in ordered if r.get("id")]
    acc = set(acceptable)
    coverage = bool(acc & set(ids))
    rank = None
    for i, fid in enumerate(ids, start=1):
        if fid in acc:
            rank = i
            break
    return {
        "n_l1": len(ids),
        "l1_top1_id": ids[0] if ids else "",
        "l1_top2_id": ids[1] if len(ids) > 1 else "",
        "family_coverage": coverage,
        "family_top1": bool(rank == 1),
        "family_top2": bool(rank is not None and rank <= 2),
        "family_rr": (1.0 / rank) if rank else 0.0,
        "gold_family_rank": rank,
        "l1_ordered_ids": ids,
    }


def bucket_row(
    fam: Mapping[str, Any],
    opt_proxy: Mapping[str, Any],
    parent_source: str,
) -> str:
    if parent_source == "none" or not fam.get("family_coverage"):
        return "L1_MISS"
    if not fam.get("family_top2"):
        return "L1_HIT_MISRANK"
    if opt_proxy.get("option_top1"):
        return "L1_OK_OPTION_HIT"
    return "L1_OK_OPTION_MISS"


def mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    ours = load_ours()
    rows_out: list[dict[str, Any]] = []
    for cid, pack in sorted(ours.items(), key=lambda x: (len(x[0]), x[0])):
        case = pack["case"]
        mapper = pack["mapper"]
        l1 = case.get("l1") or {}
        l1_rows = list(l1.get("l1_posteriors") or ())
        ap = acceptable_parents(case, mapper)
        fam = family_metrics(l1_rows, ap["acceptable_parent_ids"])
        gold_leaves = ap["gold_leaf_ids"]
        prior_ids = build_l1_prior_only(case)
        opt_proxy = option_metrics_for_leaf_ranking(prior_ids, gold_leaves)
        joint_ids = [
            str(r.get("id"))
            for r in ((case.get("l2") or {}).get("final_ranking_labels") or ())
            if r.get("id")
        ]
        opt_joint_remap = option_metrics_for_leaf_ranking(joint_ids, gold_leaves)
        bucket = bucket_row(fam, opt_proxy, ap["parent_source"])
        rows_out.append({
            "case_id": cid,
            "cohort": pack["cohort"],
            "preset": l1.get("preset"),
            "compiler_rules_injected": bool(l1.get("compiler_rules_injected")),
            "n_selected": l1.get("n_selected"),
            "selected_budget": l1.get("selected_budget"),
            "stop_reason": l1.get("stop_reason"),
            "parent_source": ap["parent_source"],
            "acceptable_parents": "|".join(ap["acceptable_parent_ids"]),
            "n_acceptable_parents": len(ap["acceptable_parent_ids"]),
            "gold_leaf_ids": "|".join(gold_leaves),
            "family_coverage": int(fam["family_coverage"]),
            "family_top1": int(fam["family_top1"]),
            "family_top2": int(fam["family_top2"]),
            "family_rr": round(float(fam["family_rr"]), 6),
            "gold_family_rank": fam["gold_family_rank"] if fam["gold_family_rank"] is not None else "",
            "l1_top1_id": fam["l1_top1_id"],
            "l1_top2_id": fam["l1_top2_id"],
            "n_l1": fam["n_l1"],
            "l1_prior_opt1": int(opt_proxy["option_top1"]),
            "l1_prior_opt2": int(opt_proxy["option_top2"]),
            "l1_prior_rr": round(float(opt_proxy["option_rr"]), 6),
            "joint_remap_opt1": int(opt_joint_remap["option_top1"]),
            "joint_remap_opt2": int(opt_joint_remap["option_top2"]),
            "mapper_opt1": int(bool(mapper.get("option_top1"))),
            "mapper_opt2": int(bool(mapper.get("option_top2"))),
            "mapper_rr": round(float(mapper.get("option_rr") or 0.0), 6),
            "funnel_bucket": bucket,
        })

    tsv_path = OUT / "l1_family_metrics.tsv"
    fields = list(rows_out[0].keys()) if rows_out else []
    with tsv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, delimiter="\t")
        w.writeheader()
        w.writerows(rows_out)

    def summarize(subset: list[dict[str, Any]]) -> dict[str, Any]:
        n = len(subset)
        if not n:
            return {"n": 0}
        return {
            "n": n,
            "family_top1": mean([r["family_top1"] for r in subset]),
            "family_top2": mean([r["family_top2"] for r in subset]),
            "family_mrr": mean([r["family_rr"] for r in subset]),
            "family_coverage": mean([r["family_coverage"] for r in subset]),
            "l1_prior_opt1": mean([r["l1_prior_opt1"] for r in subset]),
            "l1_prior_opt2": mean([r["l1_prior_opt2"] for r in subset]),
            "l1_prior_mrr": mean([r["l1_prior_rr"] for r in subset]),
            "mapper_opt1": mean([r["mapper_opt1"] for r in subset]),
            "mapper_opt2": mean([r["mapper_opt2"] for r in subset]),
            "joint_remap_opt1": mean([r["joint_remap_opt1"] for r in subset]),
            "joint_remap_opt2": mean([r["joint_remap_opt2"] for r in subset]),
            "funnel_buckets": dict(Counter(r["funnel_bucket"] for r in subset)),
            "stop_reasons": dict(Counter(str(r["stop_reason"]) for r in subset)),
            "parent_sources": dict(Counter(str(r["parent_source"]) for r in subset)),
            "compiler_injected_rate": mean([float(r["compiler_rules_injected"]) for r in subset]),
        }

    summary = {
        "generated_at": _utc(),
        "protocol": "v1_auto_parent",
        "n_cases": len(rows_out),
        "full": summarize(rows_out),
        "pilot24": summarize([r for r in rows_out if r["cohort"] == "pilot24"]),
        "remain76": summarize([r for r in rows_out if r["cohort"] == "remain76"]),
        "set_family_miss": summarize([r for r in rows_out if r["funnel_bucket"] == "L1_MISS"]),
        "set_family_misrank": summarize([r for r in rows_out if r["funnel_bucket"] == "L1_HIT_MISRANK"]),
    }
    (OUT / "l1_family_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary["full"], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
