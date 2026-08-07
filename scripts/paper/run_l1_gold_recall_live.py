#!/usr/bin/env python3
"""Live L1 gold-recall smoke: 标注前注入全树叶 + bind-repair + `_rank_and_expand`.

Unlike the offline joint-only rematch, this injects shared_trees leaves into the
mapper leaf catalogue (with joint_rank) before rescoring — the upstream hook
point before annotation metrics. No LLM; production mapper default stays off.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "paper"))
sys.path.insert(0, str(ROOT / "src"))

import audit_l1_rank_gap as audit  # noqa: E402
import mapper_bind_repair as mbr  # noqa: E402

PILOT_CASE = audit.PILOT_CASE
PILOT_MAP = audit.PILOT_MAP
PILOT_TREE = ROOT / "logs/diagnosisarena_d2_m01_v1/downstream_top2_w12_v1/shared_trees"
PILOT_CASES = (
    ROOT / "logs/diagnosisarena_d2_m01_v1/downstream_top2_w12_v1/normalized_cases.json"
)
REMAIN_CASE = audit.REMAIN_CASE
REMAIN_MAP = audit.REMAIN_MAP
REMAIN_TREE = (
    ROOT / "logs/diagnosisarena_d2_m01_v1/pipeline_remaining76_v1/annotate/shared_trees"
)
REMAIN_CASES = (
    ROOT
    / "logs/diagnosisarena_d2_m01_v1/pipeline_remaining76_v1/annotate/normalized_cases.json"
)
FALLBACK_CASES = ROOT / "logs/diagnosisarena_d2_m01_v1/normalized_cases.json"
OUT = ROOT / "analysis" / "l1_gold_recall_v1" / "smoke_live"
ARMS = ("R0", "R1", "R2")


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _load_case_meta(path: Path) -> dict[str, dict[str, Any]]:
    if not path.is_file():
        return {}
    doc = json.loads(path.read_text(encoding="utf-8"))
    rows = doc.get("cases") or ()
    if isinstance(rows, Mapping):
        return {str(k): dict(v) for k, v in rows.items()}
    return {str(c["id"]): dict(c) for c in rows if c.get("id") is not None}


def _options(meta: Mapping[str, Any], mapper: Mapping[str, Any]) -> dict[str, str]:
    raw = ((meta.get("annotation") or {}).get("source_options") or {})
    out = {str(k).upper(): str(v) for k, v in raw.items()}
    if out:
        return out
    # Fallback: reconstruct from projection keys + gold text only
    letter = str(mapper.get("gold_letter") or "").upper()
    maps = ((mapper.get("projection") or {}).get("option_maps") or {})
    for L in maps:
        out[str(L).upper()] = ""
    if letter:
        out[letter] = str(
            mapper.get("gold_option_text") or mapper.get("gold_diagnosis") or ""
        )
    return out


def load_packs(cohort: str) -> list[dict[str, Any]]:
    packs: list[dict[str, Any]] = []
    fallback = _load_case_meta(FALLBACK_CASES)
    for name, case_dir, map_dir, tree_dir, cases_path in (
        ("pilot24", PILOT_CASE, PILOT_MAP, PILOT_TREE, PILOT_CASES),
        ("remain76", REMAIN_CASE, REMAIN_MAP, REMAIN_TREE, REMAIN_CASES),
    ):
        if cohort == "pilot24" and name != "pilot24":
            continue
        if cohort == "remain76" and name != "remain76":
            continue
        meta = _load_case_meta(cases_path)
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
            m = meta.get(cid) or fallback.get(cid) or {}
            packs.append({
                "case_id": cid,
                "cohort": name,
                "case": case,
                "mapper": mapper,
                "tree_state": tree_state,
                "meta": m,
                "options": _options(m, mapper),
            })
    return packs


def eval_case(pack: Mapping[str, Any], arm: str) -> dict[str, Any]:
    case = pack["case"]
    mapper0 = pack["mapper"]
    tree_state = pack["tree_state"]
    options = pack["options"]
    leaves_full = mbr.collect_tree_leaves(case, tree_state)
    injected = mbr.build_injected_leaves(case, tree_state)
    l1_rows = list((case.get("l1") or {}).get("l1_posteriors") or ())
    l1_ids = [str(r.get("id") or "") for r in l1_rows if r.get("id")]
    tree_l1 = mbr.l1_ids_on_tree(case, tree_state)

    ap_v2 = mbr.acceptable_parents_v2(case, mapper0, leaves_full)
    v2_parents = set(ap_v2["acceptable_parent_ids"])
    tree_parent_present = bool(v2_parents & tree_l1) if v2_parents else bool(v2_parents)
    l1_candidate_recall = bool(v2_parents & set(l1_ids)) if v2_parents else False

    n_injected = sum(1 for r in injected if r.get("injected"))
    bind_applied = 0

    if arm == "R0":
        mapper = mapper0
        ap = mbr.acceptable_parents_v1(case, mapper, leaves_full)
        mapper_opt1 = int(bool(mapper0.get("option_top1")))
        mapper_opt2 = int(bool(mapper0.get("option_top2")))
        mapper_rr = float(mapper0.get("option_rr") or 0.0)
    elif arm == "R1":
        # Metric protocol bump (v2) on full tree; option = official (no inject).
        mapper = mapper0
        ap = ap_v2
        mapper_opt1 = int(bool(mapper0.get("option_top1")))
        mapper_opt2 = int(bool(mapper0.get("option_top2")))
        mapper_rr = float(mapper0.get("option_rr") or 0.0)
    else:
        # R2 live: 标注前注入 + bind-repair + production rank_and_expand
        mapper = mbr.rescore_projection_live(
            mapper0, injected, options, apply_repair=True,
        )
        ap = mbr.acceptable_parents_v1(case, mapper, leaves_full)
        mapper_opt1 = int(bool(mapper.get("option_top1")))
        mapper_opt2 = int(bool(mapper.get("option_top2")))
        mapper_rr = float(mapper.get("option_rr") or 0.0)
        bind_applied = int(bool(mapper.get("bind_repair_applied")))

    fam = audit.family_metrics(l1_rows, ap["acceptable_parent_ids"])
    auto_cov = bool(fam["family_coverage"])
    funnel = mbr.recall_funnel_bucket(
        auto_coverage=auto_cov,
        tree_parent_present=tree_parent_present,
        parent_in_l1_set=l1_candidate_recall,
        parent_source=str(ap["parent_source"]),
    )
    return {
        "case_id": pack["case_id"],
        "cohort": pack["cohort"],
        "arm": arm,
        "protocol": ap["protocol"],
        "parent_source": ap["parent_source"],
        "acceptable_parents": "|".join(ap["acceptable_parent_ids"]),
        "gold_leaf_ids": "|".join(ap["gold_leaf_ids"]),
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
        "n_leaves_injected_extra": n_injected if arm == "R2" else 0,
        "n_leaves_catalogue": len(injected) if arm == "R2" else len(leaves_full),
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
        "mean_extra_leaves": mean([float(r["n_leaves_injected_extra"]) for r in rows]),
        "funnel_buckets": dict(Counter(str(r["funnel_bucket"]) for r in rows)),
    }


def gate_decision(by_arm: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    r0, r1, r2 = by_arm["R0"], by_arm["R1"], by_arm["R2"]
    cov0 = float(r0["auto_coverage"])
    reasons: list[str] = []
    r1_ok = float(r1["auto_coverage"]) - cov0 >= 0.08 - 1e-12
    r2_ok = float(r2["auto_coverage"]) - cov0 >= 0.08 - 1e-12
    if r1_ok:
        reasons.append("R1 auto_coverage %+0.3f" % (float(r1["auto_coverage"]) - cov0))
    if r2_ok:
        reasons.append("R2 auto_coverage %+0.3f" % (float(r2["auto_coverage"]) - cov0))
    opt0 = float(r0["mapper_opt2"])
    opt2 = float(r2["mapper_opt2"])
    opt_drop = opt0 - opt2
    opt_guard = opt_drop <= 0.02 + 1e-12
    reasons.append(
        "R2 live mapper_opt2 %+0.3f (guard drop<=0.02: %s)"
        % (opt2 - opt0, "OK" if opt_guard else "FAIL")
    )
    r1_pass = r1_ok  # metric-only
    r2_pass = r2_ok and opt_guard
    passed = r1_pass or r2_pass
    recommend = "none"
    if r2_pass:
        recommend = "R2_live_inject_bind_repair"
    elif r1_pass:
        recommend = "R1_v2_leaf_parent_audit"
    if r1_pass and not r2_pass:
        reasons.append("PASS via R1; R2 live not cleared for default integration")
    return {
        "passed": passed,
        "r1_pass": r1_pass,
        "r2_pass": r2_pass,
        "opt_guard_ok": opt_guard,
        "decision": "PASS" if passed else "REJECT",
        "recommend_default": recommend,
        "reasons": reasons,
        "r0_auto_coverage": cov0,
        "r1_auto_coverage": float(r1["auto_coverage"]),
        "r2_auto_coverage": float(r2["auto_coverage"]),
        "r0_mapper_opt2": opt0,
        "r2_mapper_opt2": opt2,
    }


def write_report(cohort: str, by_arm: Mapping[str, Any], gate: Mapping[str, Any], out_dir: Path) -> None:
    lines = [
        "# L1 金标召回 **Live** 烟测（标注前注入）",
        "",
        "**队列**：`%s`  " % cohort,
        "**生成**：`%s`  " % _utc(),
        "**机制**：R0 官方落盘；R1=`v2_leaf_parent`（度量）；"
        "R2=全树叶注入+bind-repair+`_rank_and_expand`（标注前）",
        "**生产默认**：仍 **off**",
        "",
        "## 主表",
        "",
        "| 臂 | n | AutoCoverage | TreeParentPresent | mapper @1 | mapper @2 | MRR | bind率 | 均增叶 |",
        "|----|--:|-------------:|------------------:|----------|--------:|--------:|----:|-------:|-------:|",
    ]
    for arm in ARMS:
        s = by_arm[arm]
        lines.append(
            "| %s | %d | %.3f | %.3f | %.3f | %.3f | %.3f | %.3f | %.1f |"
            % (
                arm,
                int(s["n"]),
                float(s["auto_coverage"]),
                float(s["tree_parent_present"]),
                float(s["mapper_opt1"]),
                float(s["mapper_opt2"]),
                float(s["mapper_mrr"]),
                float(s["bind_repair_rate"]),
                float(s.get("mean_extra_leaves") or 0),
            )
        )
    lines.extend([
        "",
        "## 漏斗",
        "",
    ])
    for arm in ARMS:
        lines.append("- **%s**：`%s`" % (arm, by_arm[arm].get("funnel_buckets")))
    lines.extend([
        "",
        "## 门控",
        "",
        "- **决策**：`%s`" % gate["decision"],
        "- **推荐**：`%s`" % gate["recommend_default"],
        "- **R1/R2 pass**：`%s` / `%s`" % (gate["r1_pass"], gate["r2_pass"]),
        "- **理由**：",
    ])
    for r in gate["reasons"]:
        lines.append("  - %s" % r)
    lines.extend([
        "",
        "## 与离线 smoke 的区别",
        "",
        "- 离线 R2 仅用 joint `final_ranking` 重匹配 → 树上有叶但未入 joint 时 option 虚假下跌。",
        "- 本 live R2 在标注前把 **shared_trees 叶**注入叶目录并赋 `joint_rank`，再 bind-repair + 生产 `_rank_and_expand`。",
        "",
    ])
    (out_dir / "l1_gold_recall_live_report.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8",
    )


def run_cohort(cohort: str, out_dir: Path) -> dict[str, Any]:
    packs = load_packs(cohort)
    rows = [eval_case(p, arm) for p in packs for arm in ARMS]
    fields = list(rows[0].keys())
    tsv = out_dir / ("metrics_live_%s.tsv" % cohort)
    with tsv.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, delimiter="\t")
        w.writeheader()
        w.writerows(rows)
    by_arm = {a: summarize([r for r in rows if r["arm"] == a]) for a in ARMS}
    gate = gate_decision(by_arm)
    summary = {
        "generated_at": _utc(),
        "mode": "live_inject_pre_annotation",
        "cohort": cohort,
        "arms": by_arm,
        "gate": gate,
        "production_default": "off",
        "tsv": str(tsv.relative_to(ROOT)),
    }
    (out_dir / ("summary_live_%s.json" % cohort)).write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
    )
    (out_dir / "summary_live.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
    )
    with (out_dir / "metrics_live.tsv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, delimiter="\t")
        w.writeheader()
        w.writerows(rows)
    write_report(cohort, by_arm, gate, out_dir)
    return summary


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cohort", choices=("pilot24", "all100", "remain76"), default="pilot24")
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--auto-escalate", action="store_true")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    summary = run_cohort(args.cohort, args.out)
    print(json.dumps({
        "cohort": summary["cohort"],
        "gate": summary["gate"]["decision"],
        "recommend": summary["gate"]["recommend_default"],
        "arms": {
            k: {
                "cov": v["auto_coverage"],
                "opt1": v["mapper_opt1"],
                "opt2": v["mapper_opt2"],
                "funnel": v["funnel_buckets"],
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
        print("Pilot PASS → all100 …", flush=True)
        s100 = run_cohort("all100", args.out)
        print(json.dumps({
            "cohort": s100["cohort"],
            "gate": s100["gate"]["decision"],
            "recommend": s100["gate"]["recommend_default"],
            "arms": {
                k: {
                    "cov": v["auto_coverage"],
                    "opt1": v["mapper_opt1"],
                    "opt2": v["mapper_opt2"],
                }
                for k, v in s100["arms"].items()
            },
            "reasons": s100["gate"]["reasons"],
        }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
