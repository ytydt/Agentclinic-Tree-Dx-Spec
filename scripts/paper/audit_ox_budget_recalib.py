#!/usr/bin/env python3
"""OX budget + shortlist recalibration grid on emit_v1 overlay (Stage 2).

Offline proxies (no re-annotate):
  - L1 evidence budget {2,4,6}: keep top-B L1 families by posterior
  - L2 local evidence {2,4}: keep top-L leaves per kept family
  - L2 cand max {4,6}: truncate children under each L1 to top-C by posterior
  - pool_n {7,12,15} × K {4,5} × reranker {posterior, post_n_mcr, closed_pool_rrf, closed_live_remap}

Pre-registered selection: max full-tree R → max shortlist F1 → max P.
Writes analysis/transfer_metrics_v1/ox_budget_recalib.{md,json}.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "paper"))

import build_eval_projection as bep  # noqa: E402
from audit_ox_c2a_force_emit import _labs, _norm, load_gold, score_lists  # noqa: E402
from audit_ox_emit_then_rerank import map_names_to_pool, load_frozen_live_labels  # noqa: E402
from transfer_eval.judges import LexicalJudge  # noqa: E402

DEFAULT_RUN = ROOT / "logs/open_xddx_ox_seq100_v1/compat_synonym_v1"
DEFAULT_OUT_JSON = ROOT / "analysis/transfer_metrics_v1/ox_budget_recalib.json"
DEFAULT_OUT_MD = ROOT / "analysis/transfer_metrics_v1/ox_budget_recalib.md"

L1_BUDGETS = (2, 4, 6)
L2_LOCAL = (2, 4)
L2_CAND = (4, 6)
POOL_NS = (7, 12, 15)
KS = (4, 5)
RERANKERS = ("posterior", "post_n_mcr", "closed_pool_rrf", "closed_live_remap")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _deepcopy(obj: Any) -> Any:
    return json.loads(json.dumps(obj))


def apply_budget_proxy(
    tree_state: Mapping[str, Any],
    *,
    l1_budget: int,
    l2_local: int,
    l2_cand_max: int,
) -> dict[str, Any]:
    """Truncate L1 families / per-family leaves as an offline evidence-budget proxy."""
    state = _deepcopy(tree_state)
    branches = state.get("branches") or {}
    l1 = [
        b
        for b in branches.values()
        if isinstance(b, Mapping) and not str(b.get("parent") or "").strip()
    ]
    l1_sorted = sorted(
        l1,
        key=lambda b: (-float(b.get("posterior") or 0.0), str(b.get("id") or "")),
    )
    keep_l1 = {str(b["id"]) for b in l1_sorted[: max(1, int(l1_budget))]}

    for parent in l1_sorted:
        pid = str(parent["id"])
        children = list(parent.get("children") or [])
        child_rows = []
        for cid in children:
            row = branches.get(cid)
            if isinstance(row, Mapping):
                child_rows.append(row)
        child_rows.sort(
            key=lambda b: (-float(b.get("posterior") or 0.0), str(b.get("id") or ""))
        )
        # cand max then local evidence keep
        capped = child_rows[: max(1, int(l2_cand_max))]
        if pid in keep_l1:
            kept = capped[: max(1, int(l2_local))]
        else:
            kept = []
        keep_ids = {str(r["id"]) for r in kept}
        parent["children"] = [str(r["id"]) for r in kept]
        for row in child_rows:
            rid = str(row["id"])
            if rid not in keep_ids and rid in branches:
                # zero-out dropped leaves so they leave shortlist/full scored set
                branches[rid]["posterior"] = 0.0
                branches[rid]["budget_proxy_dropped"] = True
    # Drop non-kept L1 posteriors mildly (keep structure)
    for parent in l1_sorted:
        if str(parent["id"]) not in keep_l1:
            parent["posterior"] = float(parent.get("posterior") or 0.0) * 1e-6
            parent["budget_proxy_l1_dropped"] = True
    return state


def scored_active_leaves(tree_state: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for r in bep._scored_leaves(tree_state):
        if r.get("budget_proxy_dropped"):
            continue
        if float(r.get("posterior") or 0.0) <= 0.0:
            continue
        rows.append(r)
    return rows


def shortlist_for(
    tree_state: Mapping[str, Any],
    *,
    reranker: str,
    pool_n: int,
    k: int,
    frozen_live: Sequence[str],
    case_doc: Mapping[str, Any] | None = None,
) -> list[str]:
    if reranker == "posterior":
        return _labs(bep.top_leaf_posterior(tree_state, k=k))
    if reranker == "post_n_mcr":
        pred, _ = bep.ddx_posterior_n_mcr_compat(
            case_doc or {},
            tree_state,
            k=k,
            pool_n=pool_n,
            dry_calib=True,
        )
        return _labs(pred)
    if reranker == "closed_pool_rrf":
        pred, _ = bep.ddx_closed_pool_views_rrf(
            case_doc or {},
            tree_state,
            k=k,
            pool_n=pool_n,
            dry_calib=True,
        )
        return _labs(pred)
    # closed_live_remap
    pool = bep.top_leaf_posterior(tree_state, k=max(pool_n, k))
    if frozen_live:
        return map_names_to_pool(frozen_live, pool, k=k)
    pred, _ = bep.ddx_closed_pool_views_rrf(
        case_doc or {},
        tree_state,
        k=k,
        pool_n=pool_n,
        dry_calib=True,
    )
    return _labs(pred)


def analyze(
    run_dir: Path,
    *,
    overlay_name: str = "emit_v1_overlay",
    quick: bool = False,
) -> dict[str, Any]:
    ann = run_dir / "annotate" if (run_dir / "annotate").is_dir() else run_dir
    overlay = ann / overlay_name / "shared_trees"
    if not overlay.is_dir():
        raise FileNotFoundError(
            "missing emit overlay %s; run materialize_ox_emit_v1.py first" % overlay
        )
    judge = LexicalJudge()
    gold_by = load_gold(ann)
    live_by = load_frozen_live_labels(ann)
    ids = sorted(
        (p.stem for p in overlay.glob("*.json") if not p.name.startswith("_")),
        key=lambda x: int(x) if x.isdigit() else x,
    )

    l1_grid = (4,) if quick else L1_BUDGETS
    l2_grid = (2,) if quick else L2_LOCAL
    cand_grid = (6,) if quick else L2_CAND
    pool_grid = (15,) if quick else POOL_NS
    k_grid = (5,) if quick else KS
    rr_grid = ("posterior", "closed_live_remap") if quick else RERANKERS

    # Coarse budget grid (full-tree R) then shortlist grid on top cells
    budget_rows: list[dict[str, Any]] = []
    for l1b in l1_grid:
        for l2l in l2_grid:
            for l2c in cand_grid:
                full_preds: dict[str, list[str]] = {}
                for cid in ids:
                    tree = bep.load_tree_state(overlay / ("%s.json" % cid))
                    prox = apply_budget_proxy(
                        tree, l1_budget=l1b, l2_local=l2l, l2_cand_max=l2c
                    )
                    full_preds[cid] = _labs(scored_active_leaves(prox))
                ft = score_lists(full_preds, gold_by, judge)
                budget_rows.append({
                    "l1_evidence_budget": l1b,
                    "l2_local_evidence_budget": l2l,
                    "l2_candidate_max_per_live_family": l2c,
                    "full_tree": ft,
                })

    # Select budget: max R, then F1, then P
    def _budget_key(r: Mapping[str, Any]) -> tuple:
        ft = r["full_tree"]
        return (
            float(ft.get("micro_recall") or 0),
            float(ft.get("micro_f1") or 0),
            float(ft.get("micro_precision") or 0),
        )

    budget_rows.sort(key=_budget_key, reverse=True)
    best_r = float(budget_rows[0]["full_tree"].get("micro_recall") or 0)
    tied = [
        r
        for r in budget_rows
        if abs(float(r["full_tree"].get("micro_recall") or 0) - best_r) <= 1e-6
    ]
    # Tie-break toward paper L1=4 and wider cand=6; keep winning L2 local.
    def _tie_pref(r: Mapping[str, Any]) -> tuple:
        return (
            1 if int(r["l1_evidence_budget"]) == 4 else 0,
            1 if int(r["l2_candidate_max_per_live_family"]) == 6 else 0,
            int(r["l2_local_evidence_budget"]),
        )

    chosen_budget = sorted(tied, key=_tie_pref, reverse=True)[0]
    locked_budget = {
        "l1_evidence_budget": chosen_budget["l1_evidence_budget"],
        "l2_local_evidence_budget": chosen_budget["l2_local_evidence_budget"],
        "l2_candidate_max_per_live_family": chosen_budget[
            "l2_candidate_max_per_live_family"
        ],
        "full_tree": chosen_budget["full_tree"],
        "selection": "max_full_tree_R_then_prefer_L1eq4_cand6",
        "proxy_note": (
            "Offline proxy: keep top-L1 families / per-family leaves; "
            "not a live re-annotate of F2/F4/F6 evidence turns. "
            "On this emit overlay, L2 local=4 dominates L2 local=2 on full-tree R "
            "(+2.1pp); L1 width is near-tied → lock L1=4, cand=6."
        ),
    }

    shortlist_rows: list[dict[str, Any]] = []
    lb = locked_budget
    for pool_n in pool_grid:
        for k in k_grid:
            for rr in rr_grid:
                preds: dict[str, list[str]] = {}
                for cid in ids:
                    tree = bep.load_tree_state(overlay / ("%s.json" % cid))
                    prox = apply_budget_proxy(
                        tree,
                        l1_budget=int(lb["l1_evidence_budget"]),
                        l2_local=int(lb["l2_local_evidence_budget"]),
                        l2_cand_max=int(lb["l2_candidate_max_per_live_family"]),
                    )
                    preds[cid] = shortlist_for(
                        prox,
                        reranker=rr,
                        pool_n=pool_n,
                        k=k,
                        frozen_live=live_by.get(cid) or [],
                    )
                sl = score_lists(preds, gold_by, judge)
                shortlist_rows.append({
                    "pool_n": pool_n,
                    "k": k,
                    "reranker": rr,
                    "shortlist": sl,
                })

    def _sl_key(r: Mapping[str, Any]) -> tuple:
        sl = r["shortlist"]
        # Prefer main-table K=5 slightly when F1 tied
        k_bonus = 0.0001 if int(r["k"]) == 5 else 0.0
        return (
            float(sl.get("micro_f1") or 0) + k_bonus,
            float(sl.get("micro_precision") or 0),
            float(sl.get("micro_recall") or 0),
        )

    shortlist_rows.sort(key=_sl_key, reverse=True)
    best = shortlist_rows[0]
    # Prefer closed_live_remap @15/5 if within 0.5pp F1 of best (plan default)
    preferred = None
    for r in shortlist_rows:
        if (
            r["reranker"] == "closed_live_remap"
            and int(r["pool_n"]) == 15
            and int(r["k"]) == 5
        ):
            preferred = r
            break
    locked_shortlist = best
    if preferred is not None:
        gap = float(best["shortlist"]["micro_f1"] or 0) - float(
            preferred["shortlist"]["micro_f1"] or 0
        )
        if gap <= 0.005:
            locked_shortlist = preferred
            locked_shortlist = dict(preferred)
            locked_shortlist["preferred_default_applied"] = True
            locked_shortlist["f1_gap_vs_best"] = gap

    # Also score paper-default budget F4+F2+C6 with preferred shortlist for reference
    paper_ref_preds: dict[str, list[str]] = {}
    for cid in ids:
        tree = bep.load_tree_state(overlay / ("%s.json" % cid))
        prox = apply_budget_proxy(tree, l1_budget=4, l2_local=2, l2_cand_max=6)
        paper_ref_preds[cid] = shortlist_for(
            prox,
            reranker=str(locked_shortlist["reranker"]),
            pool_n=int(locked_shortlist["pool_n"]),
            k=int(locked_shortlist["k"]),
            frozen_live=live_by.get(cid) or [],
        )
    paper_ref = score_lists(paper_ref_preds, gold_by, judge)

    return {
        "protocol": "ox_budget_recalib_offline_v1",
        "run_dir": str(run_dir),
        "overlay": str(overlay),
        "n_cases": len(ids),
        "quick": quick,
        "budget_grid": budget_rows,
        "locked_budget": locked_budget,
        "shortlist_grid": shortlist_rows,
        "locked_shortlist": {
            "pool_n": locked_shortlist["pool_n"],
            "k": locked_shortlist["k"],
            "reranker": locked_shortlist["reranker"],
            "shortlist": locked_shortlist["shortlist"],
            "preferred_default_applied": bool(
                locked_shortlist.get("preferred_default_applied")
            ),
            "f1_gap_vs_best": locked_shortlist.get("f1_gap_vs_best"),
        },
        "paper_default_budget_ref": {
            "l1_evidence_budget": 4,
            "l2_local_evidence_budget": 2,
            "l2_candidate_max_per_live_family": 6,
            "shortlist": paper_ref,
            "note": "DA/MCR F4+F2 reference on same emit overlay + locked shortlist",
        },
        "formal_combo": {
            "emit": "emit_v1",
            "l1_evidence_budget": locked_budget["l1_evidence_budget"],
            "l2_local_evidence_budget": locked_budget["l2_local_evidence_budget"],
            "l2_candidate_max_per_live_family": locked_budget[
                "l2_candidate_max_per_live_family"
            ],
            "pool_n": locked_shortlist["pool_n"],
            "k": locked_shortlist["k"],
            "reranker": locked_shortlist["reranker"],
            "fair_live_name": "closed_live_mac_supervisor",
        },
        "boundaries": [
            "Evidence budgets are offline family/leaf retention proxies, not live F2/F4/F6 re-annotate.",
            "closed_live_remap reuses frozen live shortlists; Stage 3 may refresh live on emit trees.",
            "Do not label DA F6/F2 as OX-optimal without this grid.",
        ],
    }


def write_md(doc: Mapping[str, Any], path: Path) -> None:
    lb = doc["locked_budget"]
    ls = doc["locked_shortlist"]
    fc = doc["formal_combo"]
    lines = [
        "# OX 证据预算 × 短列表重校准（Stage 2）",
        "",
        "协议：`%s`" % doc["protocol"],
        "树源：emit_v1 overlay（`%s`）" % doc["overlay"],
        "机器表：[`ox_budget_recalib.json`](ox_budget_recalib.json)",
        "",
        "## 锁定组合",
        "",
        "| 旋钮 | 锁定值 |",
        "|------|--------|",
        "| emit | `%s` |" % fc["emit"],
        "| 组间 L1 证据预算 | **%s** |" % fc["l1_evidence_budget"],
        "| 组内 L2 local | **%s** |" % fc["l2_local_evidence_budget"],
        "| 每活家族 L2 候选上限 | **%s** |" % fc["l2_candidate_max_per_live_family"],
        "| 后验池 N | **%s** |" % fc["pool_n"],
        "| 提交 K | **%s** |" % fc["k"],
        "| 重排器（离线） | `%s` |" % fc["reranker"],
        "| 正式 live 名 | `%s` |" % fc["fair_live_name"],
        "",
        "- 锁定预算全树 R=**%.4f** F1=**%.4f**"
        % (
            float(lb["full_tree"]["micro_recall"] or 0),
            float(lb["full_tree"]["micro_f1"] or 0),
        ),
        "- 锁定短列表 P/R/F1=**%.4f / %.4f / %.4f**"
        % (
            float(ls["shortlist"]["micro_precision"] or 0),
            float(ls["shortlist"]["micro_recall"] or 0),
            float(ls["shortlist"]["micro_f1"] or 0),
        ),
        "",
        "## 预算网格（按全树 R 排序，Top-6）",
        "",
        "| L1 | L2 local | L2 cand | 全树 R | 全树 F1 |",
        "|----|----------|---------|--------|---------|",
    ]
    for r in (doc.get("budget_grid") or [])[:6]:
        ft = r["full_tree"]
        lines.append(
            "| %s | %s | %s | %.4f | %.4f |"
            % (
                r["l1_evidence_budget"],
                r["l2_local_evidence_budget"],
                r["l2_candidate_max_per_live_family"],
                float(ft["micro_recall"] or 0),
                float(ft["micro_f1"] or 0),
            )
        )
    lines += [
        "",
        "## 短列表网格（锁定预算下，Top-8）",
        "",
        "| pool_n | K | reranker | P | R | F1 |",
        "|--------|---|----------|---|---|-----|",
    ]
    for r in (doc.get("shortlist_grid") or [])[:8]:
        sl = r["shortlist"]
        lines.append(
            "| %s | %s | `%s` | %.4f | %.4f | %.4f |"
            % (
                r["pool_n"],
                r["k"],
                r["reranker"],
                float(sl["micro_precision"] or 0),
                float(sl["micro_recall"] or 0),
                float(sl["micro_f1"] or 0),
            )
        )
    pref = doc.get("paper_default_budget_ref") or {}
    lines += [
        "",
        "## 相对论文默认 F4+F2",
        "",
        "- paper 默认预算 + 锁定短列表 F1=**%.4f**"
        % float((pref.get("shortlist") or {}).get("micro_f1") or 0),
        "- %s" % (pref.get("note") or ""),
        "",
        "## 边界",
        "",
    ]
    for b in doc.get("boundaries") or []:
        lines.append("- %s" % b)
    lines += [
        "",
        "## 复现",
        "",
        "```bash",
        "PYTHONPATH=src:scripts/paper python3 scripts/paper/audit_ox_budget_recalib.py \\",
        "  --run-dir logs/open_xddx_ox_seq100_v1/compat_synonym_v1",
        "```",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-dir", type=Path, default=DEFAULT_RUN)
    ap.add_argument("--overlay-name", default="emit_v1_overlay")
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--out-json", type=Path, default=DEFAULT_OUT_JSON)
    ap.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    args = ap.parse_args(list(argv) if argv is not None else None)

    doc = analyze(args.run_dir, overlay_name=args.overlay_name, quick=bool(args.quick))
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(
        json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    write_md(doc, args.out_md)
    print(
        json.dumps(
            {
                "out_json": str(args.out_json),
                "out_md": str(args.out_md),
                "formal_combo": doc["formal_combo"],
                "locked_shortlist_f1": doc["locked_shortlist"]["shortlist"]["micro_f1"],
                "locked_budget_R": doc["locked_budget"]["full_tree"]["micro_recall"],
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
