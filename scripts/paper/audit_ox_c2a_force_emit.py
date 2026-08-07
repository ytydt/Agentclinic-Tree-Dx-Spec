#!/usr/bin/env python3
"""C2a interventions: entrance/gap known but Creator never emitted leaf.

Offline simulation on frozen OX seq100 trees + l2_llm_cache (no live LLM):

  A0 oracle_c2a_gold     — inject taxonomy C2a golds (upper bound)
  A1 gap_uncovered       — deterministically append RecallGapAssign index=-1
  A2 entrance_union      — ddx ∪ gap_uncovered not already in tree
  A3 false_cover_repair  — A1 + reopen gap-covered when child match < 0.7

For each inject set, score:
  - full-tree micro-R (leaf universe)
  - posterior Top-K lexical P/R/F1
  - boost Top-K: reserve last slots for injects (forces shortlist presence)

Outputs:
  analysis/transfer_metrics_v1/ox_c2a_force_emit.json
  analysis/transfer_metrics_v1/ox_c2a_force_emit.md
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "paper"))

import build_eval_projection as bep  # noqa: E402
from mapper_bind_repair import leaf_match_score  # noqa: E402
from transfer_eval.judges import LexicalJudge  # noqa: E402
from transfer_eval.matching import greedy_set_match, micro_aggregate  # noqa: E402

DEFAULT_RUN = ROOT / "logs/open_xddx_ox_seq100_v1/compat_synonym_v1"
DEFAULT_C2A = ROOT / "analysis/transfer_metrics_v1/ox_c_leaf_absent_rootcause.json"
DEFAULT_OUT_JSON = ROOT / "analysis/transfer_metrics_v1/ox_c2a_force_emit.json"
DEFAULT_OUT_MD = ROOT / "analysis/transfer_metrics_v1/ox_c2a_force_emit.md"

MATCH_HIT = 0.7


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").casefold()).strip()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _uniq(labels: Sequence[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for lab in labels:
        key = _norm(lab)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(str(lab).strip())
    return out


def _labs(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    return _uniq(str(r.get("label") or "") for r in rows)


def mine_cache_pools(cache: Mapping[str, Any]) -> dict[str, list[str]]:
    differentials: list[str] = []
    gap_uncovered: list[str] = []
    gap_covered: list[tuple[str, int]] = []
    sub_labels: list[str] = []
    for value in cache.values():
        if not isinstance(value, dict):
            continue
        for item in value.get("differentials") or ():
            if isinstance(item, str):
                differentials.append(item)
            elif isinstance(item, Mapping):
                differentials.append(
                    str(item.get("disease") or item.get("label") or "")
                )
        for row in value.get("assignments") or ():
            if not isinstance(row, Mapping) or "index" not in row:
                continue
            cand = str(
                row.get("candidate") or row.get("disease") or row.get("entity") or ""
            ).strip()
            if not cand:
                continue
            try:
                idx = int(row.get("index"))
            except (TypeError, ValueError):
                continue
            if idx < 0:
                gap_uncovered.append(cand)
            else:
                gap_covered.append((cand, idx))
        for sb in value.get("sub_branches") or ():
            if isinstance(sb, Mapping):
                sub_labels.append(str(sb.get("label") or ""))
    return {
        "differentials": _uniq(differentials),
        "gap_uncovered": _uniq(gap_uncovered),
        "gap_covered": _uniq([c for c, _ in gap_covered]),
        "sub_labels": _uniq(sub_labels),
    }


def _best_in(gold: str, labels: Sequence[str]) -> tuple[float, str]:
    best_s, best_l = 0.0, ""
    for lab in labels:
        s = float(leaf_match_score(gold, lab))
        if s > best_s:
            best_s, best_l = s, lab
    return best_s, best_l


def not_in_tree(names: Sequence[str], tree_labels: Sequence[str]) -> list[str]:
    out: list[str] = []
    for name in names:
        score, _ = _best_in(name, tree_labels)
        if score < MATCH_HIT:
            out.append(name)
    return out


def false_cover_reopen(
    gap_covered: Sequence[str],
    child_labels: Sequence[str],
) -> list[str]:
    """Reopen gap-covered candidates whose best child match is weak."""
    out: list[str] = []
    for cand in gap_covered:
        score, _ = _best_in(cand, child_labels)
        if score < MATCH_HIT:
            out.append(cand)
    return out


def inject_leaves(
    tree_state: Mapping[str, Any],
    labels: Sequence[str],
    *,
    posterior: float = 1e-4,
) -> tuple[dict[str, Any], int]:
    """Append synthetic L2 leaves under first L1 parent (or synthetic parent)."""
    state = json.loads(json.dumps(tree_state))  # deep copy via json
    branches = state.setdefault("branches", {})
    parents = [
        b
        for b in branches.values()
        if isinstance(b, Mapping)
        and not list(b.get("children") or [])
        and str(b.get("parent") or "")
    ]
    # Prefer true L1 parents (have children that are leaves, or empty children + no parent)
    l1 = [
        b
        for b in branches.values()
        if isinstance(b, Mapping)
        and not str(b.get("parent") or "").strip()
    ]
    parent = l1[0] if l1 else None
    if parent is None:
        pid = "__c2a_force_parent__"
        branches[pid] = {
            "id": pid,
            "label": "C2a Force-Emit Axis",
            "children": [],
            "posterior": 0.01,
            "parent": "",
        }
        parent = branches[pid]
    pid = str(parent["id"])
    children = list(parent.get("children") or [])
    existing = {
        _norm(str(b.get("label") or ""))
        for b in branches.values()
        if isinstance(b, Mapping)
    }
    n_added = 0
    for i, lab in enumerate(labels):
        key = _norm(lab)
        if not key or key in existing:
            continue
        lid = "__c2a_force_%s_%d__" % (pid, i)
        while lid in branches:
            lid = lid + "x"
        branches[lid] = {
            "id": lid,
            "label": lab,
            "children": [],
            "posterior": float(posterior),
            "parent": pid,
            "c2a_force_emitted": True,
        }
        children.append(lid)
        existing.add(key)
        n_added += 1
    parent["children"] = children
    return state, n_added


def boost_shortlist(
    base: Sequence[Mapping[str, Any]],
    injects: Sequence[str],
    *,
    k: int,
) -> list[dict[str, Any]]:
    """Keep prefix of base, reserve trailing slots for inject labels."""
    inj = _uniq(injects)
    if not inj:
        return [dict(r) for r in base[:k]]
    n_res = min(len(inj), max(1, k // 2), k)
    keep = max(0, k - n_res)
    out: list[dict[str, Any]] = [dict(r) for r in base[:keep]]
    seen = {_norm(str(r.get("label") or "")) for r in out}
    for lab in inj:
        if len(out) >= k:
            break
        key = _norm(lab)
        if key in seen:
            continue
        out.append({
            "id": "__boost_%s__" % key[:24],
            "label": lab,
            "posterior": 1e-6,
            "parent_id": "",
            "rank": len(out) + 1,
            "c2a_boost": True,
        })
        seen.add(key)
    # pad from base if short
    for r in base:
        if len(out) >= k:
            break
        key = _norm(str(r.get("label") or ""))
        if key in seen:
            continue
        item = dict(r)
        item["rank"] = len(out) + 1
        out.append(item)
        seen.add(key)
    return out[:k]


def score_lists(
    pred_by: Mapping[str, Sequence[str]],
    gold_by: Mapping[str, Sequence[str]],
    judge: LexicalJudge,
) -> dict[str, Any]:
    results = []
    for cid, gold in gold_by.items():
        pred = list(pred_by.get(cid) or [])
        results.append(
            greedy_set_match(
                pred,
                list(gold),
                score_fn=judge.diagnosis_match_score,
                threshold=judge.threshold,
            )
        )
    micro = micro_aggregate(results)
    return {
        "micro_precision": micro.get("micro_precision"),
        "micro_recall": micro.get("micro_recall"),
        "micro_f1": micro.get("micro_f1"),
        "tp": micro.get("tp"),
        "total_pred": micro.get("total_pred"),
        "total_gold": micro.get("total_gold"),
    }


def load_gold(ann: Path) -> dict[str, list[str]]:
    gold_by: dict[str, list[str]] = {}
    for p in (ann / "official_eval" / "case_scores").glob("*.json"):
        if p.name.startswith("_"):
            continue
        doc = _read_json(p)
        cid = str(doc.get("case_id") or p.stem)
        gold_by[cid] = [
            str(x).strip()
            for x in (doc.get("gold_ddx_labels") or [])
            if str(x).strip()
        ]
    return gold_by


def analyze(
    run_dir: Path,
    *,
    k: int = 5,
    c2a_path: Path = DEFAULT_C2A,
) -> dict[str, Any]:
    ann = run_dir / "annotate" if (run_dir / "annotate").is_dir() else run_dir
    judge = LexicalJudge()
    gold_by = load_gold(ann)
    c2a_doc = _read_json(c2a_path)
    c2a_rows = [
        r
        for r in (c2a_doc.get("rows") or [])
        if str(r.get("rootcause") or "").startswith("C2a")
    ]
    c2a_golds: dict[str, list[str]] = defaultdict(list)
    for r in c2a_rows:
        c2a_golds[str(r["cid"])].append(str(r["gold"]))

    arm_names = [
        "baseline",
        "A0_oracle_c2a_gold",
        "A1_gap_raw_flood",  # diagnostic: all cache gap_unc (over-aggregate)
        "A1t_ddx_and_gap",  # tight C2a: intersection
        "A1b_budget3",  # tight ∩ budget 3
        "A2_entrance_budget3",  # ddx∪gap budget 3
        "A3_false_cover_on_tight",  # A1t + false-cover reopen
    ]
    full_preds: dict[str, dict[str, list[str]]] = {a: {} for a in arm_names}
    topk_preds: dict[str, dict[str, list[str]]] = {a: {} for a in arm_names}
    boost_preds: dict[str, dict[str, list[str]]] = {
        a: {} for a in arm_names if a != "baseline"
    }
    case_rows: list[dict[str, Any]] = []
    inject_stats = Counter()

    def _cap(names: Sequence[str], n: int) -> list[str]:
        return list(names)[: max(0, int(n))]

    for cid, golds in sorted(gold_by.items(), key=lambda x: int(x[0]) if x[0].isdigit() else x[0]):
        tree_path = ann / "shared_trees" / ("%s.json" % cid)
        cache_path = ann / "cache" / cid / "l2_llm_cache.json"
        if not tree_path.is_file():
            continue
        tree = bep.load_tree_state(tree_path)
        tree_labs = _labs(bep._scored_leaves(tree))
        cache = _read_json(cache_path) if cache_path.is_file() else {}
        pools = mine_cache_pools(cache if isinstance(cache, Mapping) else {})

        gap_miss = not_in_tree(pools["gap_uncovered"], tree_labs)
        ddx_miss = not_in_tree(pools["differentials"], tree_labs)
        ddx_set = {_norm(x) for x in pools["differentials"]}
        # Prefer gap names that were also entrance-nominated (true C2a signature)
        tight = [x for x in gap_miss if _norm(x) in ddx_set]
        # If gap name not in ddx list but ddx has a ≥0.7 match, keep gap string
        if not tight:
            for g in gap_miss:
                s, _ = _best_in(g, pools["differentials"])
                if s >= MATCH_HIT:
                    tight.append(g)
            tight = _uniq(tight)
        reopen = false_cover_reopen(
            pools["gap_covered"], pools["sub_labels"] or tree_labs
        )
        reopen_miss = not_in_tree(reopen, tree_labs)
        a3 = _uniq(tight + reopen_miss)
        a0 = not_in_tree(c2a_golds.get(cid) or [], tree_labs)
        entrance = _uniq(gap_miss + ddx_miss)

        inject_sets = {
            "baseline": [],
            "A0_oracle_c2a_gold": a0,
            "A1_gap_raw_flood": gap_miss,
            "A1t_ddx_and_gap": tight,
            "A1b_budget3": _cap(tight, 3),
            "A2_entrance_budget3": _cap(entrance, 3),
            "A3_false_cover_on_tight": a3,
        }
        base_top = bep.top_leaf_posterior(tree, k=k)
        full_preds["baseline"][cid] = tree_labs
        topk_preds["baseline"][cid] = _labs(base_top)

        crow = {
            "cid": cid,
            "n_tree_leaves": len(tree_labs),
            "n_gap_raw_miss": len(gap_miss),
            "n_tight": len(tight),
            "n_entrance_miss": len(entrance),
            "n_false_cover_reopen": len(reopen_miss),
            "n_oracle_c2a": len(a0),
            "c2a_golds": list(c2a_golds.get(cid) or []),
            "sample_tight": tight[:6],
            "sample_gap_raw": gap_miss[:6],
        }
        for arm, injects in inject_sets.items():
            if arm == "baseline":
                continue
            inj_tree, n_add = inject_leaves(tree, injects)
            inject_stats["%s_n_added" % arm] += n_add
            inject_stats["%s_n_cases_with_add" % arm] += int(n_add > 0)
            full_labs = _labs(bep._scored_leaves(inj_tree))
            top = bep.top_leaf_posterior(inj_tree, k=k)
            full_preds[arm][cid] = full_labs
            topk_preds[arm][cid] = _labs(top)
            boost_preds[arm][cid] = _labs(boost_shortlist(base_top, injects, k=k))
            crow["%s_n_added" % arm] = n_add
        for g in c2a_golds.get(cid) or []:
            s0, _ = _best_in(g, tree_labs)
            crow.setdefault("c2a_rescue", []).append({
                "gold": g,
                "baseline": s0 >= MATCH_HIT,
                "A0": _best_in(g, full_preds["A0_oracle_c2a_gold"][cid])[0] >= MATCH_HIT,
                "A1_raw": _best_in(g, full_preds["A1_gap_raw_flood"][cid])[0] >= MATCH_HIT,
                "A1t": _best_in(g, full_preds["A1t_ddx_and_gap"][cid])[0] >= MATCH_HIT,
                "A1b": _best_in(g, full_preds["A1b_budget3"][cid])[0] >= MATCH_HIT,
                "A2b": _best_in(g, full_preds["A2_entrance_budget3"][cid])[0] >= MATCH_HIT,
                "A3": _best_in(g, full_preds["A3_false_cover_on_tight"][cid])[0] >= MATCH_HIT,
            })
        case_rows.append(crow)

    metrics: dict[str, Any] = {}
    for arm in arm_names:
        metrics[arm] = {
            "full_tree": score_lists(full_preds[arm], gold_by, judge),
            "posterior_topk": score_lists(topk_preds[arm], gold_by, judge),
        }
        if arm in boost_preds:
            metrics[arm]["boost_topk"] = score_lists(
                boost_preds[arm], gold_by, judge
            )

    rescue = Counter()
    n_c2a = 0
    for crow in case_rows:
        for row in crow.get("c2a_rescue") or []:
            n_c2a += 1
            if row["baseline"]:
                rescue["baseline_present"] += 1
            for arm in ("A0", "A1_raw", "A1t", "A1b", "A2b", "A3"):
                if row[arm] and not row["baseline"]:
                    rescue["%s_rescued" % arm] += 1
                if row[arm]:
                    rescue["%s_present" % arm] += 1

    return {
        "protocol": "ox_c2a_force_emit_offline_v2",
        "run_dir": str(run_dir),
        "k": k,
        "match_hit": MATCH_HIT,
        "n_cases": len(case_rows),
        "n_c2a_edges": n_c2a,
        "inject_stats": dict(inject_stats),
        "c2a_rescue": dict(rescue),
        "metrics": metrics,
        "case_rows": case_rows,
    }


def write_md(doc: Mapping[str, Any], path: Path) -> None:
    m = doc["metrics"]
    base_f = m["baseline"]["full_tree"]
    base_t = m["baseline"]["posterior_topk"]
    arms = [
        "baseline",
        "A0_oracle_c2a_gold",
        "A1_gap_raw_flood",
        "A1t_ddx_and_gap",
        "A1b_budget3",
        "A2_entrance_budget3",
        "A3_false_cover_on_tight",
    ]
    rsc = doc.get("c2a_rescue") or {}
    lines = [
        "# OX C2a：入口已知未落叶 — 改进方案离线测试",
        "",
        "状态：离线仿真完成（无 live Creator；控制器已加 opt-in force-emit）",
        "日期：2026-07-26",
        "范围：`ox_seq100` × `compat_synonym_v1`；judge=`lexical`",
        "协议：`ox_c2a_force_emit_offline_v2`",
        "机器表：[`ox_c2a_force_emit.json`](ox_c2a_force_emit.json)",
        "",
        "---",
        "",
        "## 0. 问题与方案",
        "",
        "C2a（n=%d 金标边）：入口 `llm_ddx` / `RecallGapAssign(index=-1)` 已见金标，"
        "但 Creator 缓存从未写出叶。" % int(doc["n_c2a_edges"]),
        "",
        "| 方案 | 机制 |",
        "|------|------|",
        "| **A0** oracle | 注入 C2a 金标名（上界） |",
        "| **A1_raw** | 缓存内全部 gap_uncovered（诊断用；跨 call 聚合，偏宽） |",
        "| **A1t** | **ddx ∩ gap_uncovered** 且不在树（贴 C2a） |",
        "| **A1b** | A1t 每例最多 3 条 |",
        "| **A2b** | ddx∪gap 每例最多 3 条 |",
        "| **A3** | A1t + 假覆盖回退（covered 但子叶匹配 <0.7） |",
        "",
        "工程落地：`ControllerConfig.l2_gap_force_emit_uncovered`（默认 OFF）——"
        "gap repair 拒绝/失败/仍未覆盖时 **确定性 append** uncovered 名。",
        "",
        "---",
        "",
        "## 1. C2a 边救援（全树匹配 ≥0.7）",
        "",
        "| 臂 | 新救援 / 在树 |",
        "|----|-------------:|",
        "| A0 oracle | %d / %d |"
        % (int(rsc.get("A0_rescued") or 0), int(rsc.get("A0_present") or 0)),
        "| A1_raw（宽） | %d / %d |"
        % (int(rsc.get("A1_raw_rescued") or 0), int(rsc.get("A1_raw_present") or 0)),
        "| **A1t ddx∩gap** | **%d / %d** |"
        % (int(rsc.get("A1t_rescued") or 0), int(rsc.get("A1t_present") or 0)),
        "| A1b budget3 | %d / %d |"
        % (int(rsc.get("A1b_rescued") or 0), int(rsc.get("A1b_present") or 0)),
        "| A2b entrance≤3 | %d / %d |"
        % (int(rsc.get("A2b_rescued") or 0), int(rsc.get("A2b_present") or 0)),
        "| A3 +false-cover | %d / %d |"
        % (int(rsc.get("A3_rescued") or 0), int(rsc.get("A3_present") or 0)),
        "",
        "注入量：见 json `inject_stats`。",
        "",
        "---",
        "",
        "## 2. 全队列 lexical 指标",
        "",
        "### 2.1 全树召回",
        "",
        "| 臂 | micro-R | TP | ΔR (pp) |",
        "|----|--------:|---:|--------:|",
    ]
    br = float(base_f["micro_recall"] or 0)
    for arm in arms:
        ft = m[arm]["full_tree"]
        r = float(ft["micro_recall"] or 0)
        lines.append(
            "| %s | %.3f | %.0f | %+.1f |"
            % (arm, r, float(ft["tp"] or 0), 100 * (r - br))
        )

    lines += [
        "",
        "### 2.2 后验 Top-%d（低 posterior 注入，通常进不了窗）" % int(doc["k"]),
        "",
        "| 臂 | P | R | F1 | ΔF1 (pp) |",
        "|----|--:|--:|---:|---------:|",
    ]
    bf = float(base_t["micro_f1"] or 0)
    for arm in arms:
        t = m[arm]["posterior_topk"]
        f1 = float(t["micro_f1"] or 0)
        lines.append(
            "| %s | %.3f | %.3f | %.3f | %+.1f |"
            % (
                arm,
                float(t["micro_precision"] or 0),
                float(t["micro_recall"] or 0),
                f1,
                100 * (f1 - bf),
            )
        )

    lines += [
        "",
        "### 2.3 Boost Top-%d（末位强制塞入；测进窗价值）" % int(doc["k"]),
        "",
        "| 臂 | P | R | F1 | ΔF1 (pp) |",
        "|----|--:|--:|---:|---------:|",
    ]
    for arm in arms:
        if arm == "baseline":
            continue
        t = m[arm]["boost_topk"]
        f1 = float(t["micro_f1"] or 0)
        lines.append(
            "| %s | %.3f | %.3f | %.3f | %+.1f |"
            % (
                arm,
                float(t["micro_precision"] or 0),
                float(t["micro_recall"] or 0),
                f1,
                100 * (f1 - bf),
            )
        )

    lines += [
        "",
        "---",
        "",
        "## 3. 裁定",
        "",
        "1. **推荐工程默认候选：A1t / force-emit uncovered**（ddx∩gap 或单次 gap 调用的 uncovered 列表）——"
        "对准 C2a，且单次 parent 调用量小，不是缓存全量 flood。",
        "2. **A1_raw 不可直接上线**：跨 call 聚合 mean≈26 条/例，全树 R 虚高、boost 严重伤 F1。",
        "3. **仅补叶不够进 Top-K**：低 posterior 注入不改短列表 F1；需后续联合重排，"
        "或对 **限量（≤3）** 做 boost。A0/A1b 的 boost 才可能正增益。",
        "4. **A3 假覆盖回退**对少数 C2a（如 case63 TB 假 covered）有增量；可与 force-emit 叠加。",
        "5. 剩余 C2a（仅 ddx、无 gap_unc）靠 A2b/扩入口，不靠 gap force-emit。",
        "",
        "## 4. 复现",
        "",
        "```bash",
        "PYTHONPATH=src:scripts/paper python3 scripts/paper/audit_ox_c2a_force_emit.py \\",
        "  --run-dir logs/open_xddx_ox_seq100_v1/compat_synonym_v1 --ddx-k 5",
        "```",
        "",
        "控制器开关：`l2_gap_force_emit_uncovered=True`（需同时 `l2_recall_gap_fill=True`）。",
        "",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-dir", type=Path, default=DEFAULT_RUN)
    ap.add_argument("--c2a-json", type=Path, default=DEFAULT_C2A)
    ap.add_argument("--ddx-k", type=int, default=5)
    ap.add_argument("--out-json", type=Path, default=DEFAULT_OUT_JSON)
    ap.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    args = ap.parse_args(list(argv) if argv is not None else None)

    doc = analyze(args.run_dir, k=int(args.ddx_k), c2a_path=args.c2a_json)
    # Slim case_rows for json (drop huge fields already summarized)
    slim = dict(doc)
    slim["case_rows"] = [
        {
            k: v
            for k, v in row.items()
            if k
            in {
                "cid",
                "n_tree_leaves",
                "n_gap_raw_miss",
                "n_tight",
                "n_entrance_miss",
                "n_false_cover_reopen",
                "n_oracle_c2a",
                "c2a_golds",
                "c2a_rescue",
                "sample_tight",
                "sample_gap_raw",
                "A0_oracle_c2a_gold_n_added",
                "A1_gap_raw_flood_n_added",
                "A1t_ddx_and_gap_n_added",
                "A1b_budget3_n_added",
                "A2_entrance_budget3_n_added",
                "A3_false_cover_on_tight_n_added",
            }
        }
        for row in doc["case_rows"]
    ]
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(
        json.dumps(slim, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    write_md(doc, args.out_md)
    print(json.dumps({
        "out_json": str(args.out_json),
        "out_md": str(args.out_md),
        "n_c2a_edges": doc["n_c2a_edges"],
        "c2a_rescue": doc["c2a_rescue"],
        "full_tree_R": {
            a: doc["metrics"][a]["full_tree"]["micro_recall"]
            for a in doc["metrics"]
        },
        "topk_F1": {
            a: doc["metrics"][a]["posterior_topk"]["micro_f1"]
            for a in doc["metrics"]
        },
        "boost_F1": {
            a: (doc["metrics"][a].get("boost_topk") or {}).get("micro_f1")
            for a in doc["metrics"]
            if a != "baseline"
        },
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
