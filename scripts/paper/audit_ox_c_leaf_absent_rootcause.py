#!/usr/bin/env python3
"""Offline root-cause audit for OX C-class (true L2 leaf absence).

Mines per-case ``annotate/cache/{id}/l2_llm_cache.json`` for whether the gold
label appeared in LLM-DDx differentials / gap-assign candidates / generated
sub_branches, and probes static resolver + case-report/CPG recall (no LLM)
when a controller can be built.

Outputs:
  analysis/transfer_metrics_v1/ox_c_leaf_absent_rootcause.json
  analysis/transfer_metrics_v1/ox_c_leaf_absent_rootcause.md
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "paper"))

from mapper_bind_repair import leaf_match_score  # noqa: E402

DEFAULT_TAX = ROOT / "analysis/transfer_metrics_v1/ox_recall_miss_taxonomy.json"
DEFAULT_RUN = ROOT / "logs/open_xddx_ox_seq100_v1/compat_synonym_v1"
DEFAULT_OUT_JSON = (
    ROOT / "analysis/transfer_metrics_v1/ox_c_leaf_absent_rootcause.json"
)
DEFAULT_OUT_MD = (
    ROOT / "analysis/transfer_metrics_v1/ox_c_leaf_absent_rootcause.md"
)

C_BUCKETS = {
    "C_true_absent_not_in_tree",
    "C_true_absent_false_friend_token",
    "C_true_absent_or_wrong_axis",
}

STOP = {
    "disease", "syndrome", "disorder", "infection", "acute", "chronic",
    "primary", "secondary", "with", "without", "and", "the", "of", "in",
    "due", "to", "or", "a", "an", "type", "stage",
}


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").casefold()).strip()


def _tokens(text: str) -> set[str]:
    return {
        t for t in re.findall(r"[a-z0-9]+", _norm(text))
        if len(t) >= 3 and t not in STOP
    }


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _best_score(gold: str, labels: Sequence[str]) -> tuple[float, str]:
    best_s, best_l = 0.0, ""
    for lab in labels:
        if not lab:
            continue
        s = float(leaf_match_score(gold, lab))
        if s > best_s:
            best_s, best_l = s, lab
    return best_s, best_l


def _mine_cache(cache: Mapping[str, Any], gold: str) -> dict[str, Any]:
    differentials: list[str] = []
    gap_candidates: list[dict[str, Any]] = []
    sub_labels: list[str] = []
    assign_diseases: list[str] = []

    for value in cache.values():
        if not isinstance(value, dict):
            continue
        for item in value.get("differentials") or ():
            if isinstance(item, str):
                differentials.append(item)
            elif isinstance(item, Mapping):
                differentials.append(
                    str(item.get("disease") or item.get("label") or item)
                )
        for row in value.get("assignments") or ():
            if not isinstance(row, Mapping):
                continue
            cand = str(
                row.get("candidate") or row.get("disease") or row.get("entity") or ""
            ).strip()
            if not cand:
                continue
            if "index" in row:
                gap_candidates.append({
                    "candidate": cand,
                    "index": row.get("index"),
                })
            else:
                assign_diseases.append(cand)
        for sb in value.get("sub_branches") or ():
            if isinstance(sb, Mapping):
                sub_labels.append(str(sb.get("label") or ""))

    # unique preserve order
    def uniq(rows: Sequence[str]) -> list[str]:
        out, seen = [], set()
        for row in rows:
            key = _norm(row)
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(row)
        return out

    differentials = uniq(differentials)
    sub_labels = uniq(sub_labels)
    assign_diseases = uniq(assign_diseases)

    ddx_score, ddx_hit = _best_score(gold, differentials)
    sub_score, sub_hit = _best_score(gold, sub_labels)
    assign_score, assign_hit = _best_score(gold, assign_diseases)

    gap_hits = []
    for row in gap_candidates:
        s = float(leaf_match_score(gold, row["candidate"]))
        if s >= 0.7:
            gap_hits.append({**row, "score": round(s, 3)})

    return {
        "n_differentials": len(differentials),
        "n_sub_labels": len(sub_labels),
        "n_parent_assign_diseases": len(assign_diseases),
        "n_gap_assignments": len(gap_candidates),
        "ddx_best_score": round(ddx_score, 3),
        "ddx_best": ddx_hit,
        "ddx_hit": ddx_score >= 0.7,
        "sub_best_score": round(sub_score, 3),
        "sub_best": sub_hit,
        "sub_hit": sub_score >= 0.7,
        "parent_assign_best_score": round(assign_score, 3),
        "parent_assign_best": assign_hit,
        "parent_assign_hit": assign_score >= 0.7,
        "gap_hits": gap_hits,
        "gap_marked_uncovered": any(
            (h.get("index") is not None and int(h.get("index")) < 0)
            for h in gap_hits
        ),
        "gap_marked_covered": any(
            (h.get("index") is not None and int(h.get("index")) >= 0)
            for h in gap_hits
        ),
        "sample_differentials": differentials[:12],
        "sample_sub_labels": sub_labels[:12],
    }


def _axis_overlap(gold: str, l1_labels: Sequence[str]) -> dict[str, Any]:
    gt = _tokens(gold)
    best = 0
    best_lab = ""
    for lab in l1_labels:
        ov = len(gt & _tokens(lab))
        if ov > best:
            best, best_lab = ov, lab
    return {
        "l1_token_overlap": best,
        "best_l1_by_token": best_lab,
        "axis_token_aligned": best > 0,
    }


def _classify(row: Mapping[str, Any]) -> str:
    """ mechanistically exclusive-ish priority order """
    refined = str(row.get("refined_bucket") or "")
    cache = row.get("cache") or {}
    axis = row.get("axis") or {}
    kb = row.get("static_kb") or {}

    if refined == "C_true_absent_false_friend_token":
        # often umbrella/granularity pollution in C
        if (row.get("score_axis") or 0) >= 0.7 or (row.get("score_l1") or 0) >= 0.7:
            return "C0_false_friend_or_umbrella_on_axis"
        if cache.get("sub_hit"):
            return "C0_false_friend_leaf_actually_present_in_cache"
        return "C0_false_friend_token_noise"

    if cache.get("sub_hit"):
        return "CX_cache_leaf_present_taxonomy_mismatch"

    # Gold seen by entrance LLM-DDx or parent-assign pool
    in_entrance = bool(cache.get("ddx_hit") or cache.get("parent_assign_hit"))
    in_gap = bool(cache.get("gap_hits"))
    gap_uncovered = bool(cache.get("gap_marked_uncovered"))
    gap_covered = bool(cache.get("gap_marked_covered"))

    if in_entrance or in_gap:
        if gap_covered and not cache.get("sub_hit"):
            return "C2_llm_gap_assign_false_covered"
        if gap_uncovered or in_entrance:
            return "C2_llm_creator_or_gapfill_drop"
        return "C2_llm_entrance_present_not_emitted"

    # Not in mined LLM pools
    if kb.get("resolver_any") or kb.get("static_recall_hit"):
        if not axis.get("axis_token_aligned") and (row.get("score_axis") or 0) < 0.5:
            return "C3_kb_present_but_wrong_axis_blocks_parent_recall"
        return "C3_kb_present_but_not_in_llm_entrance_pool"

    if not axis.get("axis_token_aligned") and (row.get("score_l1") or 0) < 0.5:
        return "C1_axis_misaligned_and_no_kb_or_entrance_signal"

    return "C1_no_kb_no_entrance_true_coverage_hole"


def _probe_static_kb(gold: str, l1_labels: Sequence[str], controller: Any) -> dict[str, Any]:
    out: dict[str, Any] = {
        "resolver_any": False,
        "resolver_hits": {},
        "static_recall_hit": False,
        "static_recall_best": "",
        "static_recall_score": 0.0,
        "static_recall_source": "",
    }
    try:
        from agentclinic_tree_dx.answer_projection_mapper import (  # noqa: WPS433
            load_offline_resolver,
        )
        resolver = load_offline_resolver(ROOT)
        hits = {}
        if hasattr(resolver, "resolve_all_sources"):
            hits = resolver.resolve_all_sources(gold) or {}
        elif hasattr(resolver, "resolve"):
            for src in ("lr", "dxs", "primekg", "rag", "bridge"):
                try:
                    hits[src] = resolver.resolve(gold, src)
                except Exception:
                    hits[src] = None
        out["resolver_hits"] = {
            k: v for k, v in hits.items() if v
        }
        out["resolver_any"] = bool(out["resolver_hits"])
    except Exception as exc:  # noqa: BLE001
        out["resolver_error"] = type(exc).__name__

    if controller is None:
        return out

    # case_report + CPG only: temporarily disable llm_ddx
    try:
        labels: list[str] = []
        sources_hit: list[str] = []
        cfg = controller.config
        old = bool(getattr(cfg, "enable_llm_ddx_branch_entrance", False))
        cfg.enable_llm_ddx_branch_entrance = False
        try:
            queries = list(l1_labels) + [gold]
            for query in queries:
                if not query:
                    continue
                named = controller._collect_recall_rankings(
                    syndrome=str(query),
                    salient=[],
                    context="",
                    top_k=12,
                )
                for source, ranking in named:
                    for disease in (ranking or {}):
                        labels.append(str(disease))
                        sources_hit.append(source)
        finally:
            cfg.enable_llm_ddx_branch_entrance = old
        score, hit = _best_score(gold, labels)
        out["static_recall_score"] = round(score, 3)
        out["static_recall_best"] = hit
        out["static_recall_hit"] = score >= 0.7
        out["static_recall_n_labels"] = len(set(_norm(x) for x in labels if x))
        out["static_recall_sources"] = sorted(set(sources_hit))
    except Exception as exc:  # noqa: BLE001
        out["static_recall_error"] = type(exc).__name__
    return out


def _load_l1_labels(run_dir: Path, cid: str) -> list[str]:
    cr = run_dir / "annotate" / "case_results" / f"{cid}.json"
    if cr.is_file():
        doc = _read_json(cr)
        rows = (doc.get("l1") or {}).get("l1_posteriors") or []
        labels = [str(r.get("label") or "") for r in rows if r.get("label")]
        if labels:
            return labels
    for rel in (
        f"annotate/shared_trees/{cid}.json",
        f"frozen/shared_trees/{cid}.json",
    ):
        path = run_dir / rel
        if not path.is_file():
            continue
        tree = _read_json(path)
        state = tree.get("state") or tree
        labels = []
        for branch in (state.get("branches") or {}).values():
            if int(branch.get("level") or 0) == 1:
                labels.append(str(branch.get("label") or ""))
        if labels:
            return labels
    return []


def build_report(
    *,
    tax_path: Path,
    run_dir: Path,
    enable_static_recall: bool,
) -> dict[str, Any]:
    tax = _read_json(tax_path)
    misses = [
        m for m in (tax.get("misses") or [])
        if str(m.get("refined_bucket") or "") in C_BUCKETS
    ]

    controller = None
    if enable_static_recall:
        try:
            from types import SimpleNamespace
            from agentclinic_tree_dx.config import ControllerConfig
            from agentclinic_tree_dx.controller import AgentClinicTreeController
            controller = AgentClinicTreeController(
                env=SimpleNamespace(ingest_external_context=lambda _v: None),
                llm=None,
                config=ControllerConfig(
                    talp_disc_profile="off",
                    enable_case_report_branch_source=True,
                    enable_cpg_branch_source=True,
                    enable_llm_ddx_branch_entrance=False,
                    allow_external_knowledge=False,
                    l2_recall_candidate_budget=24,
                    l2_recall_snippet_budget=12,
                ),
            )
        except Exception as exc:  # noqa: BLE001
            controller = None
            static_init_error = type(exc).__name__
        else:
            static_init_error = None
    else:
        static_init_error = "skipped"

    rows = []
    for miss in misses:
        cid = str(miss["cid"])
        gold = str(miss["gold"])
        cache_path = run_dir / "annotate" / "cache" / cid / "l2_llm_cache.json"
        cache_info: dict[str, Any]
        if cache_path.is_file():
            cache_info = _mine_cache(_read_json(cache_path), gold)
            cache_info["cache_present"] = True
        else:
            cache_info = {"cache_present": False}

        l1_labels = _load_l1_labels(run_dir, cid)
        axis = _axis_overlap(gold, l1_labels)
        axis["score_axis"] = miss.get("score_axis")
        axis["best_axis"] = miss.get("best_axis")
        axis["score_l1"] = miss.get("score_l1")
        axis["best_l1"] = miss.get("best_l1")
        axis["l1_labels"] = l1_labels

        static_kb = _probe_static_kb(gold, l1_labels, controller)

        row = {
            "cid": cid,
            "gold": gold,
            "refined_bucket": miss.get("refined_bucket"),
            "score_leaf": miss.get("score_leaf"),
            "best_leaf": miss.get("best_leaf"),
            "score_axis": miss.get("score_axis"),
            "best_axis": miss.get("best_axis"),
            "score_l1": miss.get("score_l1"),
            "best_l1": miss.get("best_l1"),
            "post_top5": miss.get("post_top5"),
            "cache": cache_info,
            "axis": axis,
            "static_kb": static_kb,
        }
        row["rootcause"] = _classify(row)
        rows.append(row)

    counts = Counter(r["rootcause"] for r in rows)
    refined_counts = Counter(r["refined_bucket"] for r in rows)
    cache_present = sum(1 for r in rows if (r.get("cache") or {}).get("cache_present"))
    ddx_hits = sum(1 for r in rows if (r.get("cache") or {}).get("ddx_hit"))
    gap_uncovered = sum(
        1 for r in rows if (r.get("cache") or {}).get("gap_marked_uncovered")
    )
    creator_drop = sum(
        1 for r in rows if str(r.get("rootcause") or "").startswith("C2_")
    )
    kb_or_axis = sum(
        1 for r in rows if str(r.get("rootcause") or "").startswith(("C1_", "C3_"))
    )
    false_friend = sum(
        1 for r in rows if str(r.get("rootcause") or "").startswith("C0_")
    )

    return {
        "schema_version": 1,
        "protocol": "ox_c_leaf_absent_rootcause_v1",
        "n_c_misses": len(rows),
        "n_cache_present": cache_present,
        "static_recall_enabled": bool(enable_static_recall and controller),
        "static_init_error": static_init_error,
        "summary": {
            "rootcause_counts": dict(counts.most_common()),
            "refined_bucket_counts": dict(refined_counts.most_common()),
            "ddx_hit_rate": round(ddx_hits / max(cache_present, 1), 4),
            "gap_marked_uncovered_rate": round(
                gap_uncovered / max(cache_present, 1), 4
            ),
            "share_llm_drop_C2": round(creator_drop / max(len(rows), 1), 4),
            "share_kb_or_axis_C1_C3": round(kb_or_axis / max(len(rows), 1), 4),
            "share_false_friend_C0": round(false_friend / max(len(rows), 1), 4),
        },
        "rows": rows,
    }


def render_md(report: Mapping[str, Any]) -> str:
    s = report.get("summary") or {}
    counts = s.get("rootcause_counts") or {}
    lines = [
        "# OX C 类缺叶根因细化（KB vs LLM vs 其他）",
        "",
        "状态：离线审计（挖 L2 LLM cache + 静态 KB 探针）  ",
        "日期：2026-07-26  ",
        f"范围：taxonomy C 桶 **n={report.get('n_c_misses')}**；"
        f"有 `l2_llm_cache` **{report.get('n_cache_present')}**  ",
        "证据：`ox_c_leaf_absent_rootcause.json`",
        "",
        "---",
        "",
        "## 0. 总判",
        "",
        "| 机制族 | 含义 | 占 C |",
        "|--------|------|-----:|",
        f"| **C2 LLM 认知/生成丢叶** | 入口 differentials / assign / gap 已见金标，但未落成 L2 叶 | **{s.get('share_llm_drop_C2')}** |",
        f"| **C1/C3 KB 或轴问题** | 缓存入口未见金标；或静态 KB 有但轴错/未进入口池 | **{s.get('share_kb_or_axis_C1_C3')}** |",
        f"| **C0 假朋友/伞名噪声** | 原 refined 假朋友或轴级伞名，不宜当「真缺叶」 | **{s.get('share_false_friend_C0')}** |",
        "",
        f"- cache 内 LLM-DDx 命中率（≥0.7）：**{s.get('ddx_hit_rate')}**",
        f"- gap-assign 标成 uncovered（index=-1）率：**{s.get('gap_marked_uncovered_rate')}**",
        f"- 静态 case_report/CPG 探针：`{report.get('static_recall_enabled')}`"
        f"（init_error={report.get('static_init_error')}）",
        "",
        "**一句话**：C 类「真缺叶」里，相当一部分不是「KB 里没有这个病」，而是"
        "**LLM 入口已提名 / gap 已判未覆盖，但 Creator/gap_fill 仍未写成叶**；"
        "另一部分才是轴错位或入口池从未召回。",
        "",
        "## 1. 根因细表计数",
        "",
        "| rootcause | n |",
        "|-----------|--:|",
    ]
    for key, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        lines.append(f"| `{key}` | {n} |")

    # examples per major bucket
    rows = list(report.get("rows") or [])
    by: dict[str, list] = {}
    for row in rows:
        by.setdefault(str(row.get("rootcause")), []).append(row)

    lines += ["", "## 2. 代表性病例", ""]
    priority = [
        "C2_llm_creator_or_gapfill_drop",
        "C2_llm_gap_assign_false_covered",
        "C2_llm_entrance_present_not_emitted",
        "C3_kb_present_but_wrong_axis_blocks_parent_recall",
        "C3_kb_present_but_not_in_llm_entrance_pool",
        "C1_axis_misaligned_and_no_kb_or_entrance_signal",
        "C1_no_kb_no_entrance_true_coverage_hole",
        "C0_false_friend_token_noise",
    ]
    for key in priority:
        examples = by.get(key) or []
        if not examples:
            continue
        lines.append(f"### `{key}` (n={len(examples)})")
        lines.append("")
        lines.append("| case | gold | ddx_hit | gap_uncovered | axis_token | note |")
        lines.append("|------|------|:-------:|:-------------:|:----------:|------|")
        for row in examples[:6]:
            cache = row.get("cache") or {}
            axis = row.get("axis") or {}
            kb = row.get("static_kb") or {}
            note = cache.get("ddx_best") or cache.get("sub_best") or kb.get("static_recall_best") or ""
            lines.append(
                "| {cid} | {gold} | {ddx} | {gap} | {ax} | {note} |".format(
                    cid=row.get("cid"),
                    gold=str(row.get("gold") or "")[:48],
                    ddx="Y" if cache.get("ddx_hit") else "n",
                    gap="Y" if cache.get("gap_marked_uncovered") else "n",
                    ax="Y" if axis.get("axis_token_aligned") else "n",
                    note=str(note)[:40],
                )
            )
        lines.append("")

    lines += [
        "## 3. 机制解释",
        "",
        "### C2 — LLM 认知/生成路径（非 KB 空白）",
        "",
        "Config A 热路径：`per_parent` 召回（case_report ∪ CPG ∪ **llm_ddx**）→ "
        "`L2RecallCreator` → `RecallGapAssign` → 可选 `_gap_fill_l2_result`。",
        "",
        "- cache 里 `differentials` ≈ LLM-DDx 入口提名；",
        "- `assignments` + `index=-1` ≈ gap 判定「子叶未覆盖」；",
        "- `sub_branches` 无金标 ≈ **生成/修补未落叶**。",
        "",
        "典型：case2 `tuberculosis` 多次出现在 differentials，且 gap `index=-1`，"
        "但最终叶集只有真菌/流感等，**无 TB 叶**。",
        "",
        "### C1/C3 — KB / 轴 / 入口池",
        "",
        "- **C3**：静态 resolver 或 case_report/CPG 能命中金标，但本 case 的 LLM 入口池未见 → "
        "入口融合/轴查询未把它捞进 per_parent 候选。",
        "- **C1**：入口与静态信号皆无，且 L1 词重叠差 → 更接近真覆盖洞或轴全错。",
        "",
        "### C0 — 勿与真缺叶混谈",
        "",
        "`C_true_absent_false_friend_token` 常是伞名/弱 token；应回灌 B 粒度或匹配协议，"
        "不要当成「去补一个不存在的特异叶」的主证据。",
        "",
        "## 4. 工程含义",
        "",
        "1. **优先查 Creator / gap_fill 接受率**（C2）：不是先扩 KB。",
        "2. **轴错位**（部分 C1/C3）：补叶脚本叠在错误 L1 上无效（与 seq24 gapfill 几乎 0 加叶一致）。",
        "3. **静态 KB 空白**只解释 C1 子集；需与 C2 分列报告。",
        "4. 假朋友 C0 应从 C 主表剥离后再谈补叶 ROI。",
        "",
        "## 5. 产物",
        "",
        "| 文件 | 内容 |",
        "|------|------|",
        "| `ox_c_leaf_absent_rootcause.json` | 逐条 cache/KB/轴 + rootcause |",
        "| 本文 | 汇总裁定 |",
        "",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--taxonomy", type=Path, default=DEFAULT_TAX)
    ap.add_argument("--run-dir", type=Path, default=DEFAULT_RUN)
    ap.add_argument("--out-json", type=Path, default=DEFAULT_OUT_JSON)
    ap.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    ap.add_argument(
        "--enable-static-recall",
        action="store_true",
        help="Also probe case_report/CPG recall (loads knowledge sources; slower)",
    )
    args = ap.parse_args()

    report = build_report(
        tax_path=Path(args.taxonomy),
        run_dir=Path(args.run_dir),
        enable_static_recall=bool(args.enable_static_recall),
    )
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.out_md.write_text(render_md(report), encoding="utf-8")
    print(json.dumps(report.get("summary"), ensure_ascii=False, indent=2))
    print("wrote", args.out_json)
    print("wrote", args.out_md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
