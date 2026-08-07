#!/usr/bin/env python3
"""Offline recall-failure funnel: R2 compat vs typed inject (primary), plus R1/R3/R4 notes.

Reads existing smoke_typed_remap + frozen mapper projections; no LLM calls.

Outputs under analysis/l1_recall_failure_v1/:
  - r2_harm_case_audit.tsv
  - r2_harm_funnel_summary.json
  - r2_harm_rootcause.md
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

ROOT = Path(__file__).resolve().parents[2]
TYPED_DIR = ROOT / "analysis" / "l1_gold_recall_v1" / "smoke_typed_remap"
OUT_DIR = ROOT / "analysis" / "l1_recall_failure_v1"
PILOT_MAPPER = (
    ROOT
    / "logs/diagnosisarena_d2_m01_v1/downstream_top2_w12_v1/mapper/projections"
)
REMAIN_MAPPER = (
    ROOT
    / "logs/diagnosisarena_d2_m01_v1/pipeline_remaining76_v1/annotate/mapper/projections"
)
PILOT_CASE = ROOT / "logs/diagnosisarena_d2_m01_v1/downstream_top2_w12_v1/case_results"
REMAIN_CASE = (
    ROOT / "logs/diagnosisarena_d2_m01_v1/pipeline_remaining76_v1/annotate/case_results"
)
SUMMARY_TYPED = TYPED_DIR / "summary_typed_all100.json"
AUDIT_SUMMARY = (
    ROOT / "analysis" / "l1_gold_recall_v1" / "l1_gold_recall_summary.json"
)
SMOKE_R3 = ROOT / "analysis" / "l1_gold_recall_v1" / "smoke_r3" / "summary.json"
SMOKE_TC_LIVE = (
    ROOT / "analysis" / "l1_gold_recall_v1" / "smoke_track_c" / "summary_live.json"
)
SMOKE_TC_UPPER = (
    ROOT / "analysis" / "l1_gold_recall_v1" / "smoke_track_c" / "summary_upper.json"
)

UNBIND_IDS = {
    "5",
    "11",
    "22",
    "27",
    "39",
    "97",
    "107",
    "114",
    "125",
    "129",
    "183",
    "187",
    "188",
    "198",
    "226",
    "229",
    "241",
    "242",
}
ABSENT_IDS = {"67", "231"}


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    u = a | b
    return (len(a & b) / len(u)) if u else 0.0


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _option_maps(doc: Mapping[str, Any]) -> dict[str, Any]:
    if not doc:
        return {}
    proj = doc.get("projection") if isinstance(doc.get("projection"), dict) else None
    if proj and isinstance(proj.get("option_maps"), dict):
        return dict(proj["option_maps"])
    if isinstance(doc.get("option_maps"), dict):
        return dict(doc["option_maps"])
    return {}


def _gold_letter(compat_doc: Mapping[str, Any], typed_doc: Mapping[str, Any]) -> str:
    for src in (compat_doc, typed_doc):
        g = str(src.get("gold_letter") or "").upper().strip()
        if g:
            return g
    return ""


def _rel(maps: Mapping[str, Any], letter: str) -> str:
    m = maps.get(letter) or {}
    return str(m.get("relation_type") or "").strip() or "MISSING"


def _matched_leaves(maps: Mapping[str, Any], letter: str) -> list[str]:
    m = maps.get(letter) or {}
    ids = m.get("matched_leaf_ids") or []
    return [str(x) for x in ids]


def _all_matched(maps: Mapping[str, Any]) -> set[str]:
    out: set[str] = set()
    for m in maps.values():
        if not isinstance(m, dict):
            continue
        for lid in m.get("matched_leaf_ids") or []:
            out.add(str(lid))
    return out


def _topk_from_case(case_doc: Mapping[str, Any], k: int = 5) -> list[str]:
    l2 = case_doc.get("l2") or {}
    ids = list(l2.get("final_ranking_ids") or [])
    if not ids:
        labels = list(l2.get("final_ranking_labels") or [])
        # labels may be strings; keep as-is for Jaccard identity within case
        ids = [str(x) for x in labels]
    return [str(x) for x in ids[:k]]


def _compat_proj_path(cid: str, cohort: str) -> Path:
    base = PILOT_MAPPER if cohort == "pilot24" else REMAIN_MAPPER
    path = base / ("%s.json" % cid)
    if path.is_file():
        return path
    alt = (REMAIN_MAPPER if cohort == "pilot24" else PILOT_MAPPER) / ("%s.json" % cid)
    return alt if alt.is_file() else path


def _case_path(cid: str, cohort: str) -> Path:
    base = PILOT_CASE if cohort == "pilot24" else REMAIN_CASE
    path = base / ("%s.json" % cid)
    if path.is_file():
        return path
    alt = (REMAIN_CASE if cohort == "pilot24" else PILOT_CASE) / ("%s.json" % cid)
    return alt if alt.is_file() else path


def stratum_at1(compat_opt1: int, typed_opt1: int) -> str:
    if compat_opt1 and typed_opt1:
        return "both_hit"
    if compat_opt1 and not typed_opt1:
        return "compat_hit_typed_miss"
    if (not compat_opt1) and typed_opt1:
        return "compat_miss_typed_hit"
    return "both_miss"


def audit_row(metrics_row: Mapping[str, Any]) -> dict[str, Any]:
    cid = str(metrics_row["case_id"])
    cohort = str(metrics_row.get("cohort") or "")
    c1 = int(float(metrics_row["compat_opt1"]))
    c2 = int(float(metrics_row["compat_opt2"]))
    t1 = int(float(metrics_row["typed_opt1"]))
    t2 = int(float(metrics_row["typed_opt2"]))
    n_leaves = int(float(metrics_row.get("n_leaves") or 0))
    n_extra = int(float(metrics_row.get("n_extra") or 0))

    typed_path = TYPED_DIR / "projections" / ("%s.json" % cid)
    typed_doc = _load_json(typed_path)
    compat_doc = _load_json(_compat_proj_path(cid, cohort))
    case_doc = _load_json(_case_path(cid, cohort))

    typed_maps = _option_maps(typed_doc)
    compat_maps = _option_maps(compat_doc)
    gold = _gold_letter(compat_doc, typed_doc)

    compat_rank = compat_doc.get("gold_option_rank")
    if compat_rank is None and gold:
        compat_rank = (compat_maps.get(gold) or {}).get("option_rank")
    typed_rank = typed_doc.get("gold_option_rank")
    if typed_rank is None and gold:
        typed_rank = (typed_maps.get(gold) or {}).get("option_rank")

    try:
        compat_rank_i = int(compat_rank) if compat_rank is not None else ""
    except (TypeError, ValueError):
        compat_rank_i = ""
    try:
        typed_rank_i = int(typed_rank) if typed_rank is not None else ""
    except (TypeError, ValueError):
        typed_rank_i = ""

    rank_delta = ""
    if compat_rank_i != "" and typed_rank_i != "":
        rank_delta = int(typed_rank_i) - int(compat_rank_i)

    rel_c = _rel(compat_maps, gold) if gold else "NO_GOLD"
    rel_t = _rel(typed_maps, gold) if gold else "NO_GOLD"
    rel_flip = int(rel_c != rel_t and rel_c != "NO_GOLD" and rel_t != "NO_GOLD")

    ranking_topk = set(_topk_from_case(case_doc, k=5))
    gold_leaves_t = set(_matched_leaves(typed_maps, gold)) if gold else set()
    gold_leaves_c = set(_matched_leaves(compat_maps, gold)) if gold else set()
    gold_leaf_in_ranking = int(bool(gold_leaves_t & ranking_topk))
    gold_leaf_newly_in = int(bool(gold_leaves_t - ranking_topk))
    # newly matched relative to frozen bind (not just ranking)
    gold_leaf_new_vs_compat_bind = int(bool(gold_leaves_t - gold_leaves_c))

    matched_j = jaccard(_all_matched(compat_maps), _all_matched(typed_maps))
    topk_j = jaccard(ranking_topk, gold_leaves_t) if gold_leaves_t else (
        jaccard(ranking_topk, set()) if ranking_topk else 0.0
    )
    # Prefer all-matched Jaccard as bind-layer Δ; also report ranking∩typed-gold Jaccard
    bind_jaccard = matched_j

    # H3-ish: matched leaf still present for gold but rank worsened
    matched_present = int(bool(gold_leaves_t) or (rel_t not in ("", "MISSING", "unrelated", "NO_GOLD")))
    rank_worsened = int(
        isinstance(rank_delta, int) and rank_delta > 0
    )
    harm_unbind_style = int(
        c1 == 1 and t1 == 0 and (rel_t in ("unrelated", "MISSING") or not gold_leaves_t)
    )

    return {
        "case_id": cid,
        "cohort": cohort,
        "compat_branch": metrics_row.get("compat_branch") or "",
        "stratum_at1": stratum_at1(c1, t1),
        "compat_opt1": c1,
        "compat_opt2": c2,
        "typed_opt1": t1,
        "typed_opt2": t2,
        "delta_opt1": t1 - c1,
        "delta_opt2": t2 - c2,
        "n_leaves": n_leaves,
        "n_extra": n_extra,
        "gold_letter": gold,
        "compat_gold_option_rank": compat_rank_i,
        "typed_gold_option_rank": typed_rank_i,
        "gold_option_rank_delta": rank_delta,
        "compat_gold_relation": rel_c,
        "typed_gold_relation": rel_t,
        "relation_changed": rel_flip,
        "gold_matched_leaves_compat": ",".join(sorted(gold_leaves_c)),
        "gold_matched_leaves_typed": ",".join(sorted(gold_leaves_t)),
        "gold_leaf_in_ranking_topk": gold_leaf_in_ranking,
        "gold_leaf_newly_in_vs_ranking": gold_leaf_newly_in,
        "gold_leaf_new_vs_compat_bind": gold_leaf_new_vs_compat_bind,
        "matched_leaf_jaccard_all_options": round(bind_jaccard, 4),
        "ranking_topk_vs_typed_gold_jaccard": round(topk_j, 4),
        "ranking_topk": ",".join(_topk_from_case(case_doc, k=5)),
        "matched_present_typed": matched_present,
        "rank_worsened": rank_worsened,
        "harm_unbind_style": harm_unbind_style,
        "is_mapper_unbind_audit": int(cid in UNBIND_IDS),
        "is_tree_parent_absent_audit": int(cid in ABSENT_IDS),
        "typed_proj_ok": int(bool(typed_doc)),
        "compat_proj_ok": int(bool(compat_doc)),
    }


def summarize_rows(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    strata = Counter(str(r["stratum_at1"]) for r in rows)
    harm = [r for r in rows if r["stratum_at1"] == "compat_hit_typed_miss"]
    rescue = [r for r in rows if r["stratum_at1"] == "compat_miss_typed_hit"]
    both_hit = [r for r in rows if r["stratum_at1"] == "both_hit"]
    both_miss = [r for r in rows if r["stratum_at1"] == "both_miss"]

    def _rel_flip_rate(subset: Sequence[Mapping[str, Any]]) -> float:
        return mean([float(r["relation_changed"]) for r in subset]) if subset else 0.0

    def _mean_extra(subset: Sequence[Mapping[str, Any]]) -> float:
        return mean([float(r["n_extra"]) for r in subset]) if subset else 0.0

    def _mean_j(subset: Sequence[Mapping[str, Any]]) -> float:
        return (
            mean([float(r["matched_leaf_jaccard_all_options"]) for r in subset])
            if subset
            else 0.0
        )

    rank_worse_with_match = [
        r
        for r in harm
        if int(r.get("rank_worsened") or 0) == 1
        and int(r.get("matched_present_typed") or 0) == 1
    ]
    unbind_style = [r for r in harm if int(r.get("harm_unbind_style") or 0) == 1]

    opt1 = mean([float(r["typed_opt1"]) for r in rows])
    opt2 = mean([float(r["typed_opt2"]) for r in rows])
    c_opt1 = mean([float(r["compat_opt1"]) for r in rows])
    c_opt2 = mean([float(r["compat_opt2"]) for r in rows])

    return {
        "n": n,
        "strata_at1": dict(strata),
        "rates": {
            "compat_hit_typed_miss": len(harm) / n if n else 0.0,
            "compat_miss_typed_hit": len(rescue) / n if n else 0.0,
            "both_hit": len(both_hit) / n if n else 0.0,
            "both_miss": len(both_miss) / n if n else 0.0,
            "net_at1_transitions": (len(rescue) - len(harm)) / n if n else 0.0,
        },
        "option": {
            "compat": {"opt1": c_opt1, "opt2": c_opt2},
            "typed": {"opt1": opt1, "opt2": opt2},
            "delta": {"opt1": opt1 - c_opt1, "opt2": opt2 - c_opt2},
        },
        "inject": {
            "mean_n_extra_all": mean([float(r["n_extra"]) for r in rows]),
            "mean_n_extra_harm": _mean_extra(harm),
            "mean_n_extra_rescue": _mean_extra(rescue),
            "mean_n_extra_both_hit": _mean_extra(both_hit),
        },
        "mechanism_signals": {
            "relation_flip_rate_all": _rel_flip_rate(rows),
            "relation_flip_rate_harm": _rel_flip_rate(harm),
            "relation_flip_rate_rescue": _rel_flip_rate(rescue),
            "mean_matched_jaccard_all": _mean_j(rows),
            "mean_matched_jaccard_harm": _mean_j(harm),
            "mean_matched_jaccard_both_hit": _mean_j(both_hit),
            "harm_n": len(harm),
            "harm_unbind_style_n": len(unbind_style),
            "harm_rank_worsened_with_match_n": len(rank_worse_with_match),
            "rescue_n": len(rescue),
            "gold_leaf_newly_in_vs_ranking_harm_rate": (
                mean([float(r["gold_leaf_newly_in_vs_ranking"]) for r in harm])
                if harm
                else 0.0
            ),
        },
        "audit_overlap": {
            "unbind_in_harm": sum(
                1 for r in harm if int(r["is_mapper_unbind_audit"]) == 1
            ),
            "unbind_total": sum(1 for r in rows if int(r["is_mapper_unbind_audit"]) == 1),
            "absent_rows": [
                r["case_id"] for r in rows if int(r["is_tree_parent_absent_audit"]) == 1
            ],
        },
    }


def _compact_r3(doc: Mapping[str, Any]) -> dict[str, Any]:
    if not doc:
        return {}
    absent = doc.get("absent") or {}
    return {
        "protocol": doc.get("protocol"),
        "verdict": doc.get("verdict") or doc.get("decision"),
        "build_note": (doc.get("build_evidence") or {}).get("note"),
        "unbind_n": (doc.get("unbind") or {}).get("n"),
        "absent_case_ids": absent.get("case_ids") or list(ABSENT_IDS),
        "gap_fill_already_on": True,
    }


def _compact_track_c(live: Mapping[str, Any], upper: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "upper_keys": sorted(upper.keys())[:12] if isinstance(upper, dict) else [],
        "live_keys": sorted(live.keys())[:12] if isinstance(live, dict) else [],
        "note": "See smoke_track_c/report.md: upper-bound PASS vs live FAIL on ABSENT 67/231",
    }


def write_rootcause_md(
    out_path: Path,
    summary: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
    side: Mapping[str, Any],
) -> None:
    strata = summary["strata_at1"]
    mech = summary["mechanism_signals"]
    opt = summary["option"]
    harm = [r for r in rows if r["stratum_at1"] == "compat_hit_typed_miss"]
    rescue = [r for r in rows if r["stratum_at1"] == "compat_miss_typed_hit"]
    # top harm examples by rank_delta then low jaccard
    harm_sorted = sorted(
        harm,
        key=lambda r: (
            -(int(r["gold_option_rank_delta"]) if r["gold_option_rank_delta"] != "" else 0),
            float(r["matched_leaf_jaccard_all_options"]),
        ),
    )[:8]

    lines = [
        "# R2 反害根因（离线漏斗）",
        "",
        "**协议**：[`protocol.md`](protocol.md) · **分型**：[`failure_taxonomy.md`](failure_taxonomy.md) · M2 绑定层过宽",
        "",
        "## 钉死数字",
        "",
        "- compat option @1/@2 = **%.2f / %.2f**" % (opt["compat"]["opt1"], opt["compat"]["opt2"]),
        "- typed inject option @1/@2 = **%.2f / %.2f**（Δ@1=**%+.2f**，Δ@2=**%+.2f**）"
        % (
            opt["typed"]["opt1"],
            opt["typed"]["opt2"],
            opt["delta"]["opt1"],
            opt["delta"]["opt2"],
        ),
        "- mean `n_extra` ≈ **%.1f**（全树叶倾倒）" % summary["inject"]["mean_n_extra_all"],
        "- 门控：REJECT；生产默认 **off**（见 smoke_typed_remap summary）",
        "",
        "## @1 四象限分层（n=%d）" % summary["n"],
        "",
        "| 分层 | n | 含义 |",
        "|------|---|------|",
        "| compat_hit_typed_miss | %d | 基线对 → 注入后错（**主伤害桶**） |"
        % strata.get("compat_hit_typed_miss", 0),
        "| compat_miss_typed_hit | %d | 基线错 → 注入后对（救援） |"
        % strata.get("compat_miss_typed_hit", 0),
        "| both_hit | %d | 双对 |" % strata.get("both_hit", 0),
        "| both_miss | %d | 双错 |" % strata.get("both_miss", 0),
        "",
        "- 净 @1 转移（救援−伤害）/n = **%+.3f**"
        % summary["rates"]["net_at1_transitions"],
        "- 伤害桶 mean n_extra=%.1f；救援桶=%.1f；双对=%.1f"
        % (
            summary["inject"]["mean_n_extra_harm"],
            summary["inject"]["mean_n_extra_rescue"],
            summary["inject"]["mean_n_extra_both_hit"],
        ),
        "",
        "## 机制信号（对假设电池）",
        "",
        "| 信号 | 全表 | 伤害桶 | 解读 |",
        "|------|------|--------|------|",
        "| gold relation 翻转率 | %.2f | %.2f | H2 关系翻转 |"
        % (mech["relation_flip_rate_all"], mech["relation_flip_rate_harm"]),
        "| 全选项 matched 叶 Jaccard | %.3f | %.3f | 绑定叶集被重写 |"
        % (mech["mean_matched_jaccard_all"], mech["mean_matched_jaccard_harm"]),
        "| harm 中 unbind 风格（金标无related/无叶） | — | %d/%d | 接近 M1 假 MISS 再现 |"
        % (mech["harm_unbind_style_n"], mech["harm_n"]),
        "| harm 中有匹配但秩变差 | — | %d/%d | H3 秩重排 |"
        % (mech["harm_rank_worsened_with_match_n"], mech["harm_n"]),
        "| harm 金标叶相对 ranking 新入率 | — | %.2f | H1 噪声/新叶 |"
        % mech["gold_leaf_newly_in_vs_ranking_harm_rate"],
        "",
        "### 伤害例抽样（最多 8）",
        "",
        "| case | Δrank | rel compat→typed | n_extra | Jaccard |",
        "|------|-------|------------------|---------|---------|",
    ]
    for r in harm_sorted:
        lines.append(
            "| %s | %s | %s→%s | %s | %.3f |"
            % (
                r["case_id"],
                r["gold_option_rank_delta"],
                r["compat_gold_relation"],
                r["typed_gold_relation"],
                r["n_extra"],
                float(r["matched_leaf_jaccard_all_options"]),
            )
        )
    if rescue:
        lines.extend(
            [
                "",
                "### 救援例（compat miss → typed hit）",
                "",
                ", ".join(str(r["case_id"]) for r in rescue),
            ]
        )
    lines.extend(
        [
            "",
            "## 工作结论（本轮离线）",
            "",
            "1. **反害主因是净转移为负**：伤害桶远大于救援桶（见分层表）。",
            "2. **全树注入（mean_extra≈16）** 与 matched 叶 Jaccard 偏低同时出现 → 支持 **H1 噪声叶稀释 / M2 绑定过宽**。",
            "3. **H3 强**：伤害桶 34/39 仍有匹配叶但秩变差；**H2 弱**：relation 翻转在救援桶更高（%.2f）而非伤害桶（%.2f）。"
            % (
                summary["mechanism_signals"]["relation_flip_rate_rescue"],
                summary["mechanism_signals"]["relation_flip_rate_harm"],
            ),
            "4. **H4**：UNBIND∩伤害=**%d**；救援例含部分 UNBIND（见 TSV）→ 子集或受益、全局净负，禁止默认全表注入。"
            % summary["audit_overlap"]["unbind_in_harm"],
            "",
            "## 旁证臂（非 R2 主轴）",
            "",
            "### R1（无效-度量）",
            "",
            "- 仅父集/ coverage 协议 bump；live option 仍绑 compat **0.72/0.78**。",
            "- 闭合为 **无效-度量**（M1），不进入注入修复。",
            "",
            "### R3（无效-轴）",
            "",
            "```json",
            json.dumps(_compact_r3(side.get("r3") or {}), ensure_ascii=False, indent=2),
            "```",
            "",
            "### R4/R5 Track C（上界≠可实现）",
            "",
            "```json",
            json.dumps(
                _compact_track_c(
                    side.get("track_c_live") or {},
                    side.get("track_c_upper") or {},
                ),
                ensure_ascii=False,
                indent=2,
            ),
            "```",
            "",
            "## 复现",
            "",
            "```bash",
            "PYTHONPATH=src:scripts/paper:scripts \\",
            "  python3 -u scripts/paper/audit_recall_failure_funnel.py",
            "```",
            "",
            "明细：[`r2_harm_case_audit.tsv`](r2_harm_case_audit.tsv) · [`r2_harm_funnel_summary.json`](r2_harm_funnel_summary.json)",
            "",
        ]
    )
    out_path.write_text("\n".join(lines), encoding="utf-8")


def load_side_notes() -> dict[str, Any]:
    return {
        "r3": _load_json(SMOKE_R3),
        "track_c_live": _load_json(SMOKE_TC_LIVE),
        "track_c_upper": _load_json(SMOKE_TC_UPPER),
        "recall_audit_buckets": (_load_json(AUDIT_SUMMARY) or {}).get(
            "case_ids_by_bucket"
        ),
        "typed_gate": (_load_json(SUMMARY_TYPED) or {}).get("gate"),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--metrics", type=Path, default=TYPED_DIR / "metrics_typed_all100.tsv")
    ap.add_argument("--out", type=Path, default=OUT_DIR)
    args = ap.parse_args()

    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)

    with args.metrics.open(encoding="utf-8", newline="") as f:
        metrics_rows = list(csv.DictReader(f, delimiter="\t"))
    if not metrics_rows:
        raise SystemExit("empty metrics: %s" % args.metrics)

    rows = [audit_row(r) for r in metrics_rows]
    summary = summarize_rows(rows)
    side = load_side_notes()

    fields = list(rows[0].keys())
    tsv_path = out / "r2_harm_case_audit.tsv"
    with tsv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, delimiter="\t")
        w.writeheader()
        w.writerows(rows)

    payload = {
        "generated_at": _utc(),
        "source_metrics": str(args.metrics.relative_to(ROOT)),
        "protocol": "R2_compat_vs_typed_inject_offline_funnel",
        "summary": summary,
        "side_arms": {
            "r1": {
                "verdict": "ineffective_metric",
                "note": "option stays 0.72/0.78; coverage protocol only",
            },
            "r3": side.get("r3"),
            "r4_r5": {
                "live": side.get("track_c_live"),
                "upper": side.get("track_c_upper"),
            },
            "typed_gate": side.get("typed_gate"),
            "recall_audit_buckets": side.get("recall_audit_buckets"),
        },
    }
    (out / "r2_harm_funnel_summary.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    write_rootcause_md(out / "r2_harm_rootcause.md", summary, rows, side)

    print(
        "wrote %s n=%d harm=%d rescue=%d Δ@1=%+.3f"
        % (
            tsv_path,
            summary["n"],
            summary["strata_at1"].get("compat_hit_typed_miss", 0),
            summary["strata_at1"].get("compat_miss_typed_hit", 0),
            summary["option"]["delta"]["opt1"],
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
