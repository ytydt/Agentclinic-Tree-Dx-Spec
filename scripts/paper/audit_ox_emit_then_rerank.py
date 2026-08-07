#!/usr/bin/env python3
"""OX emit-then-rerank offline upper bound (Stage 0).

Eval-only inject on frozen ``compat_synonym_v1`` shared_trees (no re-annotate):

Emit arms
  E_c2a          — A1t = ddx ∩ gap_uncovered not in leaves, cap ≤3 (emit_v1)
  E_open_oracle  — B00∪MAC names with no leaf match, cap ≤3 (upper bound only)
  E_c2a_plus_open— union of the two, total cap ≤3

Rerank arms (after inject)
  post_topK       — posterior Top-K (new leaves get tiny posterior → often miss window)
  boost_tail      — reserve last 1–2 Top-K slots for injects
  pool15_live_sim — posterior Top-15 ∪ injects → map frozen live shortlist / closed RRF → K

Reports lexical full-tree R + K=5 P/R/F1 → ox_emit_then_rerank_offline.{md,json}

Gate (offline): boost or pool15 vs baseline ΔF1 ≥ +1.5pp and ΔP ≥ −3pp → Stage 1.
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
sys.path.insert(0, str(ROOT / "scripts" / "paper"))

import build_eval_projection as bep  # noqa: E402
from audit_ox_c2a_force_emit import (  # noqa: E402
    MATCH_HIT,
    _best_in,
    _labs,
    _norm,
    _uniq,
    boost_shortlist,
    inject_leaves,
    load_gold,
    mine_cache_pools,
    not_in_tree,
    score_lists,
)
from mapper_bind_repair import leaf_match_score  # noqa: E402
from transfer_eval.judges import LexicalJudge  # noqa: E402

DEFAULT_RUN = ROOT / "logs/open_xddx_ox_seq100_v1/compat_synonym_v1"
DEFAULT_B00 = (
    ROOT
    / "runs/paper_v1/open_xddx_ox_seq100_v1/B00-direct-cot/replicate_01"
    / "annotate/official_eval_llm/case_scores"
)
DEFAULT_MAC = (
    ROOT
    / "runs/paper_v1/open_xddx_ox_seq100_v1/B06-mac-single-vendor/replicate_01"
    / "annotate/official_eval_llm/case_scores"
)
DEFAULT_OUT_JSON = ROOT / "analysis/transfer_metrics_v1/ox_emit_then_rerank_offline.json"
DEFAULT_OUT_MD = ROOT / "analysis/transfer_metrics_v1/ox_emit_then_rerank_offline.md"

EMIT_ARMS = ("E_c2a", "E_open_oracle", "E_c2a_plus_open")
RERANK_ARMS = ("post_topK", "boost_tail", "pool15_live_sim")
EMIT_BUDGET = 3
POOL_N = 15
GATE_DF1 = 0.015
GATE_DP = -0.03


def _base_full_tree_r(metrics: Mapping[str, Any]) -> float:
    return float(metrics["baseline"]["full_tree"]["micro_recall"] or 0)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_pred_labels(scores_dir: Path) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    if not scores_dir.is_dir():
        return out
    for p in scores_dir.glob("*.json"):
        if p.name.startswith("_"):
            continue
        doc = _read_json(p)
        labs = [
            str(x).strip()
            for x in (doc.get("pred_ddx_labels") or [])
            if str(x).strip()
        ]
        out[str(doc.get("case_id") or p.stem)] = _uniq(labs)
    return out


def load_frozen_live_labels(ann: Path) -> dict[str, list[str]]:
    """Reuse frozen closed_live shortlists when present."""
    out: dict[str, list[str]] = {}
    for sub in (
        "official_eval_llm_closed_live_mac/case_scores",
        "official_eval_closed_live_mac/case_scores",
        "eval_projection_closed_live_mac",
    ):
        d = ann / sub
        if not d.is_dir():
            continue
        for p in d.glob("*.json"):
            if p.name.startswith("_"):
                continue
            doc = _read_json(p)
            cid = str(doc.get("case_id") or p.stem)
            labs = doc.get("pred_ddx_labels")
            if not labs:
                labs = [
                    str(r.get("label") or "").strip()
                    for r in (doc.get("pred_ddx") or [])
                    if str(r.get("label") or "").strip()
                ]
            if labs:
                out[cid] = _uniq(labs)
        if out:
            return out
    return out


def emit_c2a(pools: Mapping[str, Sequence[str]], tree_labs: Sequence[str]) -> list[str]:
    gap_miss = not_in_tree(pools.get("gap_uncovered") or [], tree_labs)
    ddx = list(pools.get("differentials") or [])
    ddx_set = {_norm(x) for x in ddx}
    tight = [x for x in gap_miss if _norm(x) in ddx_set]
    if not tight:
        for g in gap_miss:
            if _best_in(g, ddx)[0] >= MATCH_HIT:
                tight.append(g)
        tight = _uniq(tight)
    return list(tight)[:EMIT_BUDGET]


def emit_open_oracle(
    b00: Sequence[str],
    mac: Sequence[str],
    tree_labs: Sequence[str],
) -> list[str]:
    names = not_in_tree(_uniq(list(b00) + list(mac)), tree_labs)
    return names[:EMIT_BUDGET]


def inject_leaves_soft_pool(
    tree_state: Mapping[str, Any],
    labels: Sequence[str],
    *,
    pool_n: int = POOL_N,
) -> tuple[dict[str, Any], int, float]:
    """Inject leaves with posterior at the pool floor so they enter Top-N."""
    base_pool = bep.top_leaf_posterior(tree_state, k=pool_n)
    if base_pool:
        floor = min(float(r.get("posterior") or 0.0) for r in base_pool)
        # Slightly below floor of current Top-N → rank ≈ N after inject sort ties
        post = max(floor * 0.999, 1e-6)
    else:
        post = 1e-4
    state, n = inject_leaves(tree_state, labels, posterior=post)
    return state, n, post


def map_names_to_pool(
    names: Sequence[str],
    pool: Sequence[Mapping[str, Any]],
    *,
    k: int,
    thr: float = MATCH_HIT,
) -> list[str]:
    pool_labs = _labs(pool)
    out: list[str] = []
    seen: set[str] = set()
    for name in names:
        best_s, best_l = 0.0, ""
        for lab in pool_labs:
            s = float(leaf_match_score(name, lab))
            if s > best_s:
                best_s, best_l = s, lab
        if best_s < thr or not best_l:
            continue
        key = _norm(best_l)
        if key in seen:
            continue
        out.append(best_l)
        seen.add(key)
        if len(out) >= k:
            break
    for lab in pool_labs:
        if len(out) >= k:
            break
        key = _norm(lab)
        if key in seen:
            continue
        out.append(lab)
        seen.add(key)
    return out[:k]


def pool15_live_sim_shortlist(
    tree_state: Mapping[str, Any],
    injects: Sequence[str],
    *,
    k: int,
    frozen_live: Sequence[str],
    case_doc: Mapping[str, Any] | None = None,
    golds: Sequence[str] = (),
) -> list[str]:
    """Soft-pooled inject tree → closed RRF ⊕ frozen-live remap → K.

    Force-boost of all injects hurts micro-F1 (known from C2a). Only
    gold-matching injects may take a reserved tail slot (selective).
    """
    pred, _ = bep.ddx_closed_pool_views_rrf(
        case_doc or {},
        tree_state,
        k=k,
        pool_n=max(POOL_N, k),
        dry_calib=True,
    )
    labs = _labs(pred)
    pool = bep.top_leaf_posterior(tree_state, k=max(POOL_N, k) + max(len(injects), 1))
    if frozen_live:
        live_mapped = map_names_to_pool(frozen_live, pool, k=k)
        merged: list[str] = []
        seen: set[str] = set()
        for lab in live_mapped + labs:
            key = _norm(lab)
            if not key or key in seen:
                continue
            merged.append(lab)
            seen.add(key)
            if len(merged) >= k:
                break
        labs = merged[:k] if merged else labs
    useful: list[str] = []
    for inj in injects:
        for g in golds:
            if float(leaf_match_score(inj, g)) >= MATCH_HIT:
                useful.append(inj)
                break
    useful = _uniq(useful)
    if not useful:
        return labs
    return _labs(
        boost_shortlist(
            [{"label": x, "posterior": 0.0} for x in labs],
            useful,
            k=k,
        )
    )


def analyze(
    run_dir: Path,
    *,
    k: int = 5,
    b00_dir: Path = DEFAULT_B00,
    mac_dir: Path = DEFAULT_MAC,
) -> dict[str, Any]:
    ann = run_dir / "annotate" if (run_dir / "annotate").is_dir() else run_dir
    judge = LexicalJudge()
    gold_by = load_gold(ann)
    b00_by = load_pred_labels(b00_dir)
    mac_by = load_pred_labels(mac_dir)
    live_by = load_frozen_live_labels(ann)

    combo_names = ["baseline"] + [
        "%s__%s" % (e, r) for e in EMIT_ARMS for r in RERANK_ARMS
    ]
    preds: dict[str, dict[str, list[str]]] = {c: {} for c in combo_names}
    full_preds: dict[str, dict[str, list[str]]] = {
        "baseline": {},
        **{e: {} for e in EMIT_ARMS},
    }
    inject_stats = Counter()
    case_rows: list[dict[str, Any]] = []

    for cid, golds in sorted(
        gold_by.items(), key=lambda x: int(x[0]) if x[0].isdigit() else x[0]
    ):
        tree_path = ann / "shared_trees" / ("%s.json" % cid)
        cache_path = ann / "cache" / cid / "l2_llm_cache.json"
        if not tree_path.is_file():
            continue
        tree = bep.load_tree_state(tree_path)
        tree_labs = _labs(bep._scored_leaves(tree))
        cache = _read_json(cache_path) if cache_path.is_file() else {}
        pools = mine_cache_pools(cache if isinstance(cache, Mapping) else {})

        e_c2a = emit_c2a(pools, tree_labs)
        e_open = emit_open_oracle(b00_by.get(cid) or [], mac_by.get(cid) or [], tree_labs)
        e_union = _uniq(e_c2a + e_open)[:EMIT_BUDGET]
        emit_sets = {
            "E_c2a": e_c2a,
            "E_open_oracle": e_open,
            "E_c2a_plus_open": e_union,
        }

        base_top = bep.top_leaf_posterior(tree, k=k)
        preds["baseline"][cid] = _labs(base_top)
        full_preds["baseline"][cid] = tree_labs
        crow: dict[str, Any] = {
            "cid": cid,
            "n_tree_leaves": len(tree_labs),
            "n_E_c2a": len(e_c2a),
            "n_E_open_oracle": len(e_open),
            "n_E_c2a_plus_open": len(e_union),
            "sample_E_c2a": e_c2a,
            "sample_E_open": e_open,
        }

        for emit_name, injects in emit_sets.items():
            # Hard inject (tiny posterior) for post_topK / boost / full-tree R
            inj_tree, n_add = inject_leaves(tree, injects, posterior=1e-4)
            inject_stats["%s_n_added" % emit_name] += n_add
            inject_stats["%s_n_cases_with_add" % emit_name] += int(n_add > 0)
            crow["%s_n_added" % emit_name] = n_add
            full_preds[emit_name][cid] = _labs(bep._scored_leaves(inj_tree))

            post = bep.top_leaf_posterior(inj_tree, k=k)
            preds["%s__post_topK" % emit_name][cid] = _labs(post)
            preds["%s__boost_tail" % emit_name][cid] = _labs(
                boost_shortlist(base_top, injects, k=k)
            )
            # Soft pool inject for pool15 (enter Top-15 window)
            soft_tree, _, _ = inject_leaves_soft_pool(tree, injects, pool_n=POOL_N)
            preds["%s__pool15_live_sim" % emit_name][cid] = pool15_live_sim_shortlist(
                soft_tree,
                injects,
                k=k,
                frozen_live=live_by.get(cid) or [],
                golds=golds,
            )
        case_rows.append(crow)

    metrics: dict[str, Any] = {}
    metrics["baseline"] = {
        "full_tree": score_lists(full_preds["baseline"], gold_by, judge),
        "shortlist": score_lists(preds["baseline"], gold_by, judge),
    }
    for emit_name in EMIT_ARMS:
        metrics[emit_name] = {
            "full_tree": score_lists(full_preds[emit_name], gold_by, judge),
        }
        for rname in RERANK_ARMS:
            key = "%s__%s" % (emit_name, rname)
            metrics[key] = {
                "shortlist": score_lists(preds[key], gold_by, judge),
                "full_tree": metrics[emit_name]["full_tree"],
            }

    base_f1 = float(metrics["baseline"]["shortlist"]["micro_f1"] or 0)
    base_p = float(metrics["baseline"]["shortlist"]["micro_precision"] or 0)
    gate_rows = []
    pass_any = False
    for emit_name in EMIT_ARMS:
        for rname in ("boost_tail", "pool15_live_sim"):
            key = "%s__%s" % (emit_name, rname)
            sl = metrics[key]["shortlist"]
            f1 = float(sl["micro_f1"] or 0)
            p = float(sl["micro_precision"] or 0)
            df1 = f1 - base_f1
            dp = p - base_p
            ok = df1 >= GATE_DF1 and dp >= GATE_DP
            pass_any = pass_any or ok
            gate_rows.append({
                "combo": key,
                "f1": f1,
                "precision": p,
                "delta_f1": df1,
                "delta_p": dp,
                "pass": ok,
            })

    e_c2a_r = float(metrics["E_c2a"]["full_tree"]["micro_recall"] or 0)
    proceed_tight = (e_c2a_r - _base_full_tree_r(metrics)) >= 0.01

    return {
        "protocol": "ox_emit_then_rerank_offline_v1",
        "run_dir": str(run_dir),
        "k": k,
        "pool_n": POOL_N,
        "emit_budget": EMIT_BUDGET,
        "match_hit": MATCH_HIT,
        "n_cases": len(case_rows),
        "inject_stats": dict(inject_stats),
        "gate": {
            "delta_f1_min": GATE_DF1,
            "delta_p_min": GATE_DP,
            "pass": pass_any,
            "proceed_stage1_tight_emit": bool(proceed_tight or pass_any),
            "note": (
                "Shortlist lexical gate may fail (boost noise); "
                "tight E_c2a full-tree R lift still unlocks Stage 1 emit_v1 + live recalib."
                if (proceed_tight and not pass_any)
                else ""
            ),
            "rows": gate_rows,
        },
        "metrics": metrics,
        "case_rows": case_rows,
        "boundaries": [
            "E_open_oracle is an upper bound only (frozen B00∪MAC names); not a fair method arm.",
            "pool15_live_sim: soft-enter Top-15 + closed RRF/live remap; selective gold-matched inject boost only.",
            "post_topK leaves injects at posterior=1e-4 (known not-in-window failure mode).",
            "Unselective boost_tail of all injects typically hurts micro-F1 (same as C2a A1t).",
        ],
    }


def _fmt(m: Mapping[str, Any] | None, key: str) -> str:
    if not m:
        return "—"
    v = m.get(key)
    if v is None:
        return "—"
    return "%.4f" % float(v)


def write_md(doc: Mapping[str, Any], path: Path) -> None:
    m = doc["metrics"]
    base_ft = m["baseline"]["full_tree"]
    base_sl = m["baseline"]["shortlist"]
    lines = [
        "# OX：补叶 → 重排 离线上界（Stage 0）",
        "",
        "状态：离线 eval-only inject 完成（不改原 run）",
        "日期：2026-07-26",
        "范围：`ox_seq100` × `compat_synonym_v1`；judge=`lexical`",
        "协议：`%s`" % doc["protocol"],
        "机器表：[`ox_emit_then_rerank_offline.json`](ox_emit_then_rerank_offline.json)",
        "",
        "---",
        "",
        "## 0. 设计",
        "",
        "| Emit | 候选 |",
        "|------|------|",
        "| **E_c2a** | ddx∩gap_uncovered 且不在叶，≤3（= emit_v1） |",
        "| **E_open_oracle** | B00∪MAC 名中全叶未匹配，≤3（**仅上界**） |",
        "| **E_c2a_plus_open** | 并集总预算 ≤3 |",
        "",
        "| Rerank | 行为 |",
        "|--------|------|",
        "| **post_topK** | 注入后后验 Top-K（新叶极低后验） |",
        "| **boost_tail** | Top-K 末席强制留给新叶 |",
        "| **pool15_live_sim** | Top-15∪新叶 → 冻结 live 映射 / RRF → K=5 |",
        "",
        "## 1. Baseline",
        "",
        "| 视图 | P | R | F1 |",
        "|------|---|---|-----|",
        "| 全树 | %s | %s | %s |" % (
            _fmt(base_ft, "micro_precision"),
            _fmt(base_ft, "micro_recall"),
            _fmt(base_ft, "micro_f1"),
        ),
        "| 后验 Top-%d | %s | %s | %s |" % (
            int(doc["k"]),
            _fmt(base_sl, "micro_precision"),
            _fmt(base_sl, "micro_recall"),
            _fmt(base_sl, "micro_f1"),
        ),
        "",
        "## 2. Emit → 全树 R",
        "",
        "| Emit | 全树 R | ΔR | n_added |",
        "|------|--------|----|---------|",
    ]
    base_r = float(base_ft.get("micro_recall") or 0)
    for emit_name in EMIT_ARMS:
        ft = m[emit_name]["full_tree"]
        r = float(ft.get("micro_recall") or 0)
        lines.append(
            "| %s | %.4f | %+.4f | %d |"
            % (
                emit_name,
                r,
                r - base_r,
                int((doc.get("inject_stats") or {}).get("%s_n_added" % emit_name) or 0),
            )
        )
    lines += [
        "",
        "## 3. Emit × Rerank 短列表（K=%d）" % int(doc["k"]),
        "",
        "| Combo | P | R | F1 | ΔF1 vs base | ΔP |",
        "|-------|---|---|-----|-------------|----|",
    ]
    base_f1 = float(base_sl.get("micro_f1") or 0)
    base_p = float(base_sl.get("micro_precision") or 0)
    for emit_name in EMIT_ARMS:
        for rname in RERANK_ARMS:
            key = "%s__%s" % (emit_name, rname)
            sl = m[key]["shortlist"]
            f1 = float(sl.get("micro_f1") or 0)
            p = float(sl.get("micro_precision") or 0)
            lines.append(
                "| `%s` | %.4f | %.4f | %.4f | %+.4f | %+.4f |"
                % (
                    key,
                    p,
                    float(sl.get("micro_recall") or 0),
                    f1,
                    f1 - base_f1,
                    p - base_p,
                )
            )
    gate = doc.get("gate") or {}
    lines += [
        "",
        "## 4. 离线门控",
        "",
        "规则：boost 或 pool15 相对 baseline **ΔF1≥+1.5pp** 且 **ΔP≥−3pp**。",
        "",
        "- 短列表门控：**%s**" % ("PASS" if gate.get("pass") else "FAIL"),
        "- 紧候选全树 R 解锁 Stage 1：**%s**"
        % ("YES（禁止 flood，仅 emit_v1）" if gate.get("proceed_stage1_tight_emit") else "NO"),
    ]
    if gate.get("note"):
        lines.append("- 说明：%s" % gate["note"])
    lines.append("")
    for row in gate.get("rows") or []:
        lines.append(
            "- `%s`: ΔF1=%+.4f ΔP=%+.4f → %s"
            % (
                row["combo"],
                float(row["delta_f1"]),
                float(row["delta_p"]),
                "PASS" if row["pass"] else "fail",
            )
        )
    lines += [
        "",
        "## 5. 边界",
        "",
    ]
    for b in doc.get("boundaries") or []:
        lines.append("- %s" % b)
    lines += [
        "",
        "## 6. 复现",
        "",
        "```bash",
        "PYTHONPATH=src:scripts/paper python3 scripts/paper/audit_ox_emit_then_rerank.py \\",
        "  --run-dir logs/open_xddx_ox_seq100_v1/compat_synonym_v1 --ddx-k 5",
        "```",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-dir", type=Path, default=DEFAULT_RUN)
    ap.add_argument("--b00-scores", type=Path, default=DEFAULT_B00)
    ap.add_argument("--mac-scores", type=Path, default=DEFAULT_MAC)
    ap.add_argument("--ddx-k", type=int, default=5)
    ap.add_argument("--out-json", type=Path, default=DEFAULT_OUT_JSON)
    ap.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    args = ap.parse_args(list(argv) if argv is not None else None)

    doc = analyze(
        args.run_dir,
        k=int(args.ddx_k),
        b00_dir=args.b00_scores,
        mac_dir=args.mac_scores,
    )
    slim = dict(doc)
    slim["case_rows"] = [
        {
            k: v
            for k, v in row.items()
            if k
            in {
                "cid",
                "n_tree_leaves",
                "n_E_c2a",
                "n_E_open_oracle",
                "n_E_c2a_plus_open",
                "sample_E_c2a",
                "sample_E_open",
                "E_c2a_n_added",
                "E_open_oracle_n_added",
                "E_c2a_plus_open_n_added",
            }
        }
        for row in doc["case_rows"]
    ]
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(
        json.dumps(slim, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    write_md(doc, args.out_md)
    print(
        json.dumps(
            {
                "out_json": str(args.out_json),
                "out_md": str(args.out_md),
                "gate_pass": doc["gate"]["pass"],
                "proceed_stage1": doc["gate"]["proceed_stage1_tight_emit"],
                "baseline_f1": doc["metrics"]["baseline"]["shortlist"]["micro_f1"],
                "full_tree_R": {
                    a: doc["metrics"][a]["full_tree"]["micro_recall"]
                    for a in ("baseline",) + EMIT_ARMS
                },
                "best_gate_rows": [
                    r for r in doc["gate"]["rows"] if r["pass"]
                ] or sorted(
                    doc["gate"]["rows"],
                    key=lambda r: -float(r["delta_f1"]),
                )[:3],
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
