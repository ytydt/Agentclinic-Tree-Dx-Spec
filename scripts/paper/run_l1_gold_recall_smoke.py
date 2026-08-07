#!/usr/bin/env python3
"""Offline L1 gold-recall smoke (Track B): R0 / R1 / R2.

Reads frozen annotate case_results + mapper projections + shared_trees.
Does NOT re-run tree / L1 BFS / L2 / LLM. Production mapper default stays off.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "paper"))

import audit_l1_rank_gap as audit  # noqa: E402
import mapper_bind_repair as mbr  # noqa: E402

PILOT_CASE = audit.PILOT_CASE
PILOT_MAP = audit.PILOT_MAP
PILOT_TREE = ROOT / "logs/diagnosisarena_d2_m01_v1/downstream_top2_w12_v1/shared_trees"
REMAIN_CASE = audit.REMAIN_CASE
REMAIN_MAP = audit.REMAIN_MAP
REMAIN_TREE = (
    ROOT / "logs/diagnosisarena_d2_m01_v1/pipeline_remaining76_v1/annotate/shared_trees"
)
ANALYSIS = ROOT / "analysis" / "l1_gold_recall_v1"
SMOKE_OUT = ANALYSIS / "smoke"
ARMS = ("R0", "R1", "R2")


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def load_packs(cohort: str) -> list[dict[str, Any]]:
    packs: list[dict[str, Any]] = []
    for name, case_dir, map_dir, tree_dir in (
        ("pilot24", PILOT_CASE, PILOT_MAP, PILOT_TREE),
        ("remain76", REMAIN_CASE, REMAIN_MAP, REMAIN_TREE),
    ):
        if cohort == "pilot24" and name != "pilot24":
            continue
        if cohort == "remain76" and name != "remain76":
            continue
        # all100: both
        for mp in sorted(map_dir.glob("*.json")):
            cid = mp.stem
            mapper = json.loads(mp.read_text(encoding="utf-8"))
            cp = case_dir / ("%s.json" % cid)
            case = json.loads(cp.read_text(encoding="utf-8")) if cp.is_file() else {}
            tp = tree_dir / ("%s.json" % cid)
            tree_doc = json.loads(tp.read_text(encoding="utf-8")) if tp.is_file() else {}
            tree_state = tree_doc.get("state") if isinstance(tree_doc, dict) else {}
            if not isinstance(tree_state, dict):
                tree_state = {}
            packs.append({
                "case_id": cid,
                "cohort": name,
                "case": case,
                "mapper": mapper,
                "tree_state": tree_state,
            })
    return packs


def eval_case(pack: Mapping[str, Any], arm: str) -> dict[str, Any]:
    case = pack["case"]
    mapper0 = pack["mapper"]
    tree_state = pack["tree_state"]
    leaves = mbr.collect_tree_leaves(case, tree_state)
    l1_rows = list((case.get("l1") or {}).get("l1_posteriors") or ())
    l1_ids = [str(r.get("id") or "") for r in l1_rows if r.get("id")]
    tree_l1 = mbr.l1_ids_on_tree(case, tree_state)

    if arm == "R2":
        mapper = mbr.apply_bind_repair_to_mapper(mapper0, leaves)
    else:
        mapper = mapper0

    # Independent TreeParentPresent proxy (v2 leaf→parent), used for funnel split
    ap_v2 = mbr.acceptable_parents_v2(case, mapper0, leaves)
    v2_parents = set(ap_v2["acceptable_parent_ids"])
    tree_parent_present = bool(v2_parents & tree_l1) if v2_parents else bool(v2_parents)

    if arm == "R1":
        ap = ap_v2
    else:
        ap = mbr.acceptable_parents_v1(case, mapper, leaves)

    fam = audit.family_metrics(l1_rows, ap["acceptable_parent_ids"])
    auto_cov = bool(fam["family_coverage"])
    acc = set(ap["acceptable_parent_ids"])
    parent_in_l1_set = bool(acc & set(l1_ids)) if acc else False
    # Candidate recall vs tree-present parents (v2), independent of arm protocol
    l1_candidate_recall = bool(v2_parents & set(l1_ids)) if v2_parents else False

    funnel = mbr.recall_funnel_bucket(
        auto_coverage=auto_cov,
        tree_parent_present=tree_parent_present,
        parent_in_l1_set=l1_candidate_recall,
        parent_source=str(ap["parent_source"]),
    )

    gold_leaves = ap["gold_leaf_ids"]
    joint_ids = [
        str(r.get("id"))
        for r in ((case.get("l2") or {}).get("final_ranking_labels") or ())
        if r.get("id")
    ]
    # Official stored mapper option (R0/R1 baseline); R2 rematch with repaired leaves
    if arm == "R2":
        opt = audit.option_metrics_for_leaf_ranking(joint_ids, gold_leaves)
        mapper_opt1 = int(opt["option_top1"])
        mapper_opt2 = int(opt["option_top2"])
        mapper_rr = float(opt["option_rr"])
    else:
        mapper_opt1 = int(bool(mapper0.get("option_top1")))
        mapper_opt2 = int(bool(mapper0.get("option_top2")))
        mapper_rr = float(mapper0.get("option_rr") or 0.0)

    bind_applied = 0
    if arm == "R2":
        letter = str(mapper.get("gold_letter") or "").upper()
        om = ((mapper.get("projection") or {}).get("option_maps") or {}).get(letter) or {}
        bind_applied = int(bool(om.get("bind_repair_applied")))

    return {
        "case_id": pack["case_id"],
        "cohort": pack["cohort"],
        "arm": arm,
        "protocol": ap["protocol"],
        "parent_source": ap["parent_source"],
        "acceptable_parents": "|".join(ap["acceptable_parent_ids"]),
        "gold_leaf_ids": "|".join(gold_leaves),
        "family_coverage": int(auto_cov),
        "tree_parent_present": int(tree_parent_present),
        "l1_candidate_recall": int(l1_candidate_recall),
        "family_top1": int(fam["family_top1"]),
        "family_top2": int(fam["family_top2"]),
        "family_rr": round(float(fam["family_rr"]), 6),
        "mapper_opt1": mapper_opt1,
        "mapper_opt2": mapper_opt2,
        "mapper_rr": round(mapper_rr, 6),
        "funnel_bucket": funnel,
        "bind_repair_applied": bind_applied,
        "n_leaves": len(leaves),
    }


def summarize(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    if not n:
        return {"n": 0}
    return {
        "n": n,
        "auto_coverage": mean([float(r["family_coverage"]) for r in rows]),
        "tree_parent_present": mean([float(r["tree_parent_present"]) for r in rows]),
        "l1_candidate_recall": mean([float(r["l1_candidate_recall"]) for r in rows]),
        "family_top1": mean([float(r["family_top1"]) for r in rows]),
        "family_top2": mean([float(r["family_top2"]) for r in rows]),
        "mapper_opt1": mean([float(r["mapper_opt1"]) for r in rows]),
        "mapper_opt2": mean([float(r["mapper_opt2"]) for r in rows]),
        "mapper_mrr": mean([float(r["mapper_rr"]) for r in rows]),
        "bind_repair_rate": mean([float(r["bind_repair_applied"]) for r in rows]),
        "funnel_buckets": dict(Counter(str(r["funnel_bucket"]) for r in rows)),
        "parent_sources": dict(Counter(str(r["parent_source"]) for r in rows)),
    }


def gate_decision(
    by_arm: Mapping[str, Mapping[str, Any]],
    *,
    miss_ids: Optional[set[str]] = None,
    case_rows: Optional[Sequence[Mapping[str, Any]]] = None,
) -> dict[str, Any]:
    """Gate: R1 or R2 coverage/unbind; R2 additionally needs option @2 guard."""
    del miss_ids  # reserved; funnel uses R0 MAPPER_UNBIND labels
    r0 = by_arm.get("R0") or {}
    r1 = by_arm.get("R1") or {}
    r2 = by_arm.get("R2") or {}
    cov0 = float(r0.get("auto_coverage") or 0.0)
    reasons: list[str] = []
    r1_primary = False
    r2_primary = False

    for name, arm in (("R1", r1), ("R2", r2)):
        delta = float(arm.get("auto_coverage") or 0.0) - cov0
        if delta >= 0.08 - 1e-12:
            reasons.append("%s auto_coverage %+0.3f (>=+0.08)" % (name, delta))
            if name == "R1":
                r1_primary = True
            else:
                r2_primary = True

    if case_rows:
        r0_unbind = [
            r for r in case_rows
            if r["arm"] == "R0" and r["funnel_bucket"] == "MAPPER_UNBIND"
        ]
        if not r0_unbind:
            r0_unbind = [
                r for r in case_rows
                if r["arm"] == "R0" and int(r["family_coverage"]) == 0
            ]
        n0 = len(r0_unbind)
        if n0:
            ids0 = {r["case_id"] for r in r0_unbind}
            for name in ("R1", "R2"):
                still = [
                    r for r in case_rows
                    if r["arm"] == name
                    and r["case_id"] in ids0
                    and (
                        r["funnel_bucket"] == "MAPPER_UNBIND"
                        or int(r["family_coverage"]) == 0
                    )
                ]
                drop = 1.0 - (len(still) / n0)
                if drop >= 0.5 - 1e-12:
                    reasons.append(
                        "%s MAPPER_UNBIND/miss drop %.1f%% (n0=%d→%d)"
                        % (name, 100 * drop, n0, len(still))
                    )
                    if name == "R1":
                        r1_primary = True
                    else:
                        r2_primary = True

    opt0 = float(r0.get("mapper_opt2") or 0.0)
    opt2 = float(r2.get("mapper_opt2") or 0.0)
    opt_drop = opt0 - opt2
    opt_guard = opt_drop <= 0.02 + 1e-12
    if not opt_guard:
        reasons.append("R2 mapper_opt2 drop %.3f > 0.02 (R2 integration blocked)" % opt_drop)
    else:
        reasons.append("R2 mapper_opt2 drop %.3f <= 0.02 (guard OK)" % opt_drop)

    # R1 is metric-only → PASS alone. R2 needs opt guard for integration PASS.
    r1_pass = r1_primary
    r2_pass = r2_primary and opt_guard
    passed = r1_pass or r2_pass
    if r1_pass and not r2_pass:
        reasons.append("PASS via R1 only; R2 not cleared for default integration")
    recommend = "none"
    if r2_pass:
        recommend = "R2_bind_repair"
    elif r1_pass:
        recommend = "R1_v2_leaf_parent_audit"
    return {
        "passed": passed,
        "primary_ok": r1_primary or r2_primary,
        "r1_pass": r1_pass,
        "r2_pass": r2_pass,
        "opt_guard_ok": opt_guard,
        "r0_auto_coverage": cov0,
        "r1_auto_coverage": float(r1.get("auto_coverage") or 0.0),
        "r2_auto_coverage": float(r2.get("auto_coverage") or 0.0),
        "r0_mapper_opt2": opt0,
        "r2_mapper_opt2": opt2,
        "reasons": reasons,
        "decision": "PASS" if passed else "REJECT",
        "recommend_default": recommend,
    }


def write_report(
    *,
    cohort: str,
    by_arm: Mapping[str, Mapping[str, Any]],
    gate: Mapping[str, Any],
    out_dir: Path,
) -> Path:
    lines = [
        "# L1 金标召回烟测报告（Track B）",
        "",
        "**队列**：`%s`  " % cohort,
        "**生成**：`%s`  " % _utc(),
        "**机制**：R0=`v1_auto_parent`；R1=`v2_leaf_parent`；R2=bind-repair→`v1_auto_parent`",
        "**生产默认**：仍 **off**（仅离线后处理 / 评测协议）",
        "",
        "## 主表",
        "",
        "| 臂 | n | AutoCoverage | TreeParentPresent | L1CandidateRecall | mapper @1 | mapper @2 | bind率 |",
        "|----|--:|-------------:|------------------:|------------------:|----------|--------:|--------:|-------:|",
    ]
    for arm in ARMS:
        s = by_arm[arm]
        lines.append(
            "| %s | %d | %.3f | %.3f | %.3f | %.3f | %.3f | %.3f |"
            % (
                arm,
                int(s.get("n") or 0),
                float(s.get("auto_coverage") or 0),
                float(s.get("tree_parent_present") or 0),
                float(s.get("l1_candidate_recall") or 0),
                float(s.get("mapper_opt1") or 0),
                float(s.get("mapper_opt2") or 0),
                float(s.get("bind_repair_rate") or 0),
            )
        )
    lines.extend([
        "",
        "## 漏斗桶",
        "",
    ])
    for arm in ARMS:
        lines.append("- **%s**：`%s`" % (arm, by_arm[arm].get("funnel_buckets")))
    lines.extend([
        "",
        "## 门控",
        "",
        "- **决策**：`%s`" % gate.get("decision"),
        "- **推荐默认整合**：`%s`（生产 mapper 仍 off）" % gate.get("recommend_default"),
        "- **R1/R2 pass**：`%s` / `%s`" % (gate.get("r1_pass"), gate.get("r2_pass")),
        "- **理由**：",
    ])
    for r in gate.get("reasons") or []:
        lines.append("  - %s" % r)
    lines.extend([
        "",
        "## 说明",
        "",
        "- R1 的 AutoCoverage 列使用 `v2_leaf_parent` 定义的 coverage（叶反推父 ∈ `l1_posteriors`）。",
        "- R2 的 mapper @k 为修复金标叶后相对 joint 叶序的重匹配，与 R0 官方落盘 @k 对照作护栏。",
        "- Track C / gap-fill / 生产 mapper 默认未改。",
        "",
    ])
    path = out_dir / "l1_gold_recall_smoke_report.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def run_cohort(cohort: str, out_dir: Path) -> dict[str, Any]:
    packs = load_packs(cohort)
    rows: list[dict[str, Any]] = []
    for pack in packs:
        for arm in ARMS:
            rows.append(eval_case(pack, arm))

    tsv = out_dir / ("metrics_by_arm_%s.tsv" % cohort)
    fields = list(rows[0].keys()) if rows else []
    with tsv.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, delimiter="\t")
        w.writeheader()
        w.writerows(rows)

    by_arm = {arm: summarize([r for r in rows if r["arm"] == arm]) for arm in ARMS}
    # historical auto MISS ids (optional context)
    miss_path = ANALYSIS / "l1_gold_recall_summary.json"
    miss_ids: set[str] = set()
    if miss_path.is_file():
        doc = json.loads(miss_path.read_text(encoding="utf-8"))
        for lst in (doc.get("case_ids_by_bucket") or {}).values():
            miss_ids.update(str(x) for x in lst)

    gate = gate_decision(by_arm, miss_ids=miss_ids, case_rows=rows)
    summary = {
        "generated_at": _utc(),
        "cohort": cohort,
        "arms": by_arm,
        "gate": gate,
        "production_default": "off",
        "tsv": str(tsv.relative_to(ROOT)),
    }
    (out_dir / ("summary_%s.json" % cohort)).write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    write_report(cohort=cohort, by_arm=by_arm, gate=gate, out_dir=out_dir)
    # also write canonical names for latest run
    (out_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    with (out_dir / "metrics_by_arm.tsv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, delimiter="\t")
        w.writeheader()
        w.writerows(rows)
    return summary


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--cohort",
        choices=("pilot24", "all100", "remain76"),
        default="pilot24",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=SMOKE_OUT,
        help="output directory under analysis/l1_gold_recall_v1/smoke",
    )
    ap.add_argument(
        "--auto-escalate",
        action="store_true",
        help="If pilot24 PASS, also run all100",
    )
    args = ap.parse_args()
    out_dir = args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    summary = run_cohort(args.cohort, out_dir)
    print(json.dumps({
        "cohort": summary["cohort"],
        "gate": summary["gate"]["decision"],
        "arms": {
            k: {
                "auto_coverage": v.get("auto_coverage"),
                "mapper_opt2": v.get("mapper_opt2"),
                "funnel": v.get("funnel_buckets"),
            }
            for k, v in summary["arms"].items()
        },
        "reasons": summary["gate"]["reasons"],
    }, indent=2, ensure_ascii=False))

    if (
        args.auto_escalate
        and args.cohort == "pilot24"
        and summary["gate"]["decision"] == "PASS"
    ):
        print("Pilot PASS → running all100 …", flush=True)
        summary100 = run_cohort("all100", out_dir)
        print(json.dumps({
            "cohort": summary100["cohort"],
            "gate": summary100["gate"]["decision"],
            "arms": {
                k: {
                    "auto_coverage": v.get("auto_coverage"),
                    "mapper_opt2": v.get("mapper_opt2"),
                }
                for k, v in summary100["arms"].items()
            },
            "reasons": summary100["gate"]["reasons"],
        }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
