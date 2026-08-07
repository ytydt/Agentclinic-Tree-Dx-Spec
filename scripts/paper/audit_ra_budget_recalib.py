#!/usr/bin/env python3
"""RareArena budget recalibration grid (Acc-oriented Stage 2).

Mirrors ``audit_ox_budget_recalib.py`` but targets the MCR/RA open-Acc endpoint
instead of OX multi-gold F1:

  - Tree source: annotate/shared_trees (default F6 transfer; no OX emit required)
  - Gold: single-label final_diagnosis from subset parquet
  - Budget proxy: same L1 / L2-local / cand truncation as OX
  - Primary lock key: Acc@1 (posterior top-1 lexical match) → gold-in-leaves hit
    rate → prefer L1=4, cand=6 (OX-style tie preference)
  - Shortlist grid: posterior / post_n_mcr × pool_n × K; Acc@1 + hit@K

Offline proxy only — live F re-annotate is a separate side run.
Writes analysis/transfer_metrics_v1/ra_budget_recalib.{md,json}.
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
from audit_ox_budget_recalib import (  # noqa: E402
    L1_BUDGETS,
    L2_CAND,
    L2_LOCAL,
    POOL_NS,
    KS,
    apply_budget_proxy,
    scored_active_leaves,
)
from audit_ox_c2a_force_emit import _labs  # noqa: E402
from transfer_eval import io_gold  # noqa: E402
from transfer_eval.judges import LexicalJudge  # noqa: E402

DEFAULT_RUN = ROOT / "logs/rarearena_ra_rdc_seq100_v1/compat_synonym_v1"
DEFAULT_PARQUET = (
    ROOT / "data/benchmarks/rarearena/subsets/ra_rdc_seq100_v1/cases.parquet"
)
DEFAULT_OUT_JSON = ROOT / "analysis/transfer_metrics_v1/ra_budget_recalib.json"
DEFAULT_OUT_MD = ROOT / "analysis/transfer_metrics_v1/ra_budget_recalib.md"

RERANKERS = ("posterior", "post_n_mcr")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _gold_map(parquet: Path, case_ids: Sequence[str]) -> dict[str, str]:
    raw = io_gold.load_gold("rarearena", parquet, case_ids=case_ids)
    out: dict[str, str] = {}
    for cid, row in raw.items():
        g = str(row.get("final_diagnosis") or "").strip()
        if g:
            out[str(cid)] = g
    return out


def _case_docs(ann: Path) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    cr = ann / "case_results"
    if not cr.is_dir():
        return out
    for p in cr.glob("*.json"):
        if p.name.startswith("_"):
            continue
        try:
            out[p.stem] = _read_json(p)
        except Exception:  # noqa: BLE001
            continue
    return out


def _hit(judge: LexicalJudge, pred: str, gold: str) -> bool:
    if not pred or not gold:
        return False
    return bool(judge.diagnoses_equivalent(pred, gold))


def _leaf_in_gold(judge: LexicalJudge, labels: Sequence[str], gold: str) -> bool:
    return any(_hit(judge, str(x), gold) for x in labels if str(x).strip())


def score_acc(
    pred_by: Mapping[str, Sequence[str]],
    gold_by: Mapping[str, str],
    judge: LexicalJudge,
    *,
    k: int | None = None,
) -> dict[str, Any]:
    n = 0
    top1 = 0
    hit_k = 0
    leaf_cov = 0
    for cid, gold in gold_by.items():
        labels = [str(x) for x in (pred_by.get(cid) or []) if str(x).strip()]
        if k is not None:
            labels = labels[: max(1, int(k))]
        n += 1
        if labels and _hit(judge, labels[0], gold):
            top1 += 1
        if _leaf_in_gold(judge, labels, gold):
            hit_k += 1
            leaf_cov += 1
    return {
        "n_cases": n,
        "acc_at1": (top1 / n) if n else 0.0,
        "hit_at_k": (hit_k / n) if n else 0.0,
        "n_top1_hits": top1,
        "n_hit_at_k": hit_k,
        "k": k,
    }


def shortlist_for(
    tree_state: Mapping[str, Any],
    *,
    reranker: str,
    pool_n: int,
    k: int,
    case_doc: Mapping[str, Any] | None = None,
) -> list[str]:
    if reranker == "post_n_mcr":
        pred, _ = bep.ddx_posterior_n_mcr_compat(
            case_doc or {},
            tree_state,
            k=k,
            pool_n=pool_n,
            dry_calib=True,
        )
        return _labs(pred)
    return _labs(bep.top_leaf_posterior(tree_state, k=k))


def analyze(
    run_dir: Path,
    *,
    subset_parquet: Path,
    quick: bool = False,
    tree_subdir: str = "shared_trees",
) -> dict[str, Any]:
    ann = run_dir / "annotate" if (run_dir / "annotate").is_dir() else run_dir
    trees = ann / tree_subdir
    if not trees.is_dir():
        raise FileNotFoundError("missing %s" % trees)

    judge = LexicalJudge()
    ids = sorted(
        (p.stem for p in trees.glob("*.json") if not p.name.startswith("_")),
        key=lambda x: int(x) if x.isdigit() else x,
    )
    gold_by = _gold_map(subset_parquet, ids)
    if not gold_by:
        raise RuntimeError("no gold loaded from %s" % subset_parquet)
    case_docs = _case_docs(ann)

    l1_grid = (4, 6) if quick else L1_BUDGETS
    l2_grid = (2, 4) if quick else L2_LOCAL
    cand_grid = (6,) if quick else L2_CAND
    pool_grid = (15,) if quick else POOL_NS
    k_grid = (5,) if quick else KS
    rr_grid = ("posterior", "post_n_mcr") if quick else RERANKERS

    # ---- budget grid: Acc@1 on posterior top-1 after proxy truncation ----
    budget_rows: list[dict[str, Any]] = []
    for l1b in l1_grid:
        for l2l in l2_grid:
            for l2c in cand_grid:
                top1_preds: dict[str, list[str]] = {}
                full_preds: dict[str, list[str]] = {}
                for cid in ids:
                    if cid not in gold_by:
                        continue
                    tree = bep.load_tree_state(trees / ("%s.json" % cid))
                    prox = apply_budget_proxy(
                        tree, l1_budget=l1b, l2_local=l2l, l2_cand_max=l2c
                    )
                    leaves = _labs(scored_active_leaves(prox))
                    full_preds[cid] = leaves
                    top1_preds[cid] = leaves[:1]
                acc = score_acc(top1_preds, gold_by, judge, k=1)
                cov = score_acc(full_preds, gold_by, judge, k=None)
                budget_rows.append({
                    "l1_evidence_budget": l1b,
                    "l2_local_evidence_budget": l2l,
                    "l2_candidate_max_per_live_family": l2c,
                    "acc_at1": acc,
                    "gold_leaf_coverage": {
                        "hit_rate": cov["hit_at_k"],
                        "n_hits": cov["n_hit_at_k"],
                        "n_cases": cov["n_cases"],
                    },
                })

    def _budget_key(r: Mapping[str, Any]) -> tuple:
        return (
            float(r["acc_at1"].get("acc_at1") or 0),
            float(r["gold_leaf_coverage"].get("hit_rate") or 0),
        )

    budget_rows.sort(key=_budget_key, reverse=True)
    best_acc = float(budget_rows[0]["acc_at1"].get("acc_at1") or 0)
    tied = [
        r
        for r in budget_rows
        if abs(float(r["acc_at1"].get("acc_at1") or 0) - best_acc) <= 1e-9
    ]

    def _tie_pref(r: Mapping[str, Any]) -> tuple:
        # Prefer OX-like L1=4 / cand=6 when Acc tied; then higher local; then F6 as fallback.
        return (
            float(r["gold_leaf_coverage"].get("hit_rate") or 0),
            1 if int(r["l1_evidence_budget"]) == 4 else 0,
            1 if int(r["l2_candidate_max_per_live_family"]) == 6 else 0,
            int(r["l2_local_evidence_budget"]),
            1 if int(r["l1_evidence_budget"]) == 6 else 0,
        )

    chosen = sorted(tied, key=_tie_pref, reverse=True)[0]
    locked_budget = {
        "l1_evidence_budget": chosen["l1_evidence_budget"],
        "l2_local_evidence_budget": chosen["l2_local_evidence_budget"],
        "l2_between_evidence_budget": 2,
        "l2_candidate_max_per_live_family": chosen[
            "l2_candidate_max_per_live_family"
        ],
        "acc_at1": chosen["acc_at1"],
        "gold_leaf_coverage": chosen["gold_leaf_coverage"],
        "selection": "max_acc_at1_then_gold_leaf_hit_then_prefer_L1eq4_cand6",
        "proxy_note": (
            "Offline proxy on annotate/shared_trees (F6 transfer source). "
            "Not a live re-annotate of F2/F4/F6 evidence turns. "
            "Primary metric = Acc@1 (posterior top-1 lexical), secondary = "
            "gold-in-active-leaves hit rate."
        ),
    }

    # ---- shortlist grid under locked budget ----
    shortlist_rows: list[dict[str, Any]] = []
    lb = locked_budget
    for pool_n in pool_grid:
        for k in k_grid:
            for rr in rr_grid:
                preds: dict[str, list[str]] = {}
                for cid in ids:
                    if cid not in gold_by:
                        continue
                    tree = bep.load_tree_state(trees / ("%s.json" % cid))
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
                        case_doc=case_docs.get(cid),
                    )
                sl = score_acc(preds, gold_by, judge, k=k)
                shortlist_rows.append({
                    "pool_n": pool_n,
                    "k": k,
                    "reranker": rr,
                    "shortlist": sl,
                })

    def _sl_key(r: Mapping[str, Any]) -> tuple:
        sl = r["shortlist"]
        k_bonus = 0.0001 if int(r["k"]) == 5 else 0.0
        return (
            float(sl.get("acc_at1") or 0) + k_bonus,
            float(sl.get("hit_at_k") or 0),
        )

    shortlist_rows.sort(key=_sl_key, reverse=True)
    best_sl = shortlist_rows[0]
    # Prefer post_n_mcr @15/5 if within 0.5pp Acc of best (RA/MCR paper dialect)
    preferred = None
    for r in shortlist_rows:
        if (
            r["reranker"] == "post_n_mcr"
            and int(r["pool_n"]) == 15
            and int(r["k"]) == 5
        ):
            preferred = r
            break
    locked_shortlist = best_sl
    if preferred is not None:
        gap = float(best_sl["shortlist"]["acc_at1"] or 0) - float(
            preferred["shortlist"]["acc_at1"] or 0
        )
        if gap <= 0.005:
            locked_shortlist = dict(preferred)
            locked_shortlist["preferred_default_applied"] = True
            locked_shortlist["acc_gap_vs_best"] = gap

    # F6 reference under locked shortlist settings
    f6_preds: dict[str, list[str]] = {}
    for cid in ids:
        if cid not in gold_by:
            continue
        tree = bep.load_tree_state(trees / ("%s.json" % cid))
        prox = apply_budget_proxy(tree, l1_budget=6, l2_local=4, l2_cand_max=6)
        f6_preds[cid] = shortlist_for(
            prox,
            reranker=str(locked_shortlist["reranker"]),
            pool_n=int(locked_shortlist["pool_n"]),
            k=int(locked_shortlist["k"]),
            case_doc=case_docs.get(cid),
        )
    f6_ref = score_acc(
        f6_preds, gold_by, judge, k=int(locked_shortlist["k"])
    )

    return {
        "protocol": "ra_budget_recalib_offline_acc_v1",
        "run_dir": str(run_dir),
        "trees": str(trees),
        "subset_parquet": str(subset_parquet),
        "n_cases": len(gold_by),
        "quick": quick,
        "judge": "lexical",
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
            "acc_gap_vs_best": locked_shortlist.get("acc_gap_vs_best"),
        },
        "f6_reference": {
            "l1_evidence_budget": 6,
            "l2_local_evidence_budget": 4,
            "l2_candidate_max_per_live_family": 6,
            "shortlist": f6_ref,
            "note": "DA/MCR default F6 on same trees + locked shortlist settings",
        },
        "formal_combo": {
            "l1_evidence_budget": locked_budget["l1_evidence_budget"],
            "l2_local_evidence_budget": locked_budget["l2_local_evidence_budget"],
            "l2_between_evidence_budget": 2,
            "l2_candidate_max_per_live_family": locked_budget[
                "l2_candidate_max_per_live_family"
            ],
            "pool_n": locked_shortlist["pool_n"],
            "k": locked_shortlist["k"],
            "reranker": locked_shortlist["reranker"],
            "paper_endpoint": "compat_parallel_final_ranking @ ddx_k=5 (live Acc)",
        },
        "boundaries": [
            "Offline family/leaf retention proxy — not live F2/F4/F6 re-annotate.",
            "Acc uses LexicalJudge; paper Acc requires live reann + LLM judge.",
            "Do not copy OX L1=4 without reading locked_budget on this cohort.",
        ],
    }


def write_md(doc: Mapping[str, Any], path: Path) -> None:
    lb = doc["locked_budget"]
    ls = doc["locked_shortlist"]
    fc = doc["formal_combo"]
    f6 = doc["f6_reference"]
    lines = [
        "# RareArena 证据预算重校准（Stage 2，Acc 口径）",
        "",
        "协议：`%s`" % doc["protocol"],
        "树源：`%s`" % doc["trees"],
        "机器表：[`ra_budget_recalib.json`](ra_budget_recalib.json)",
        "",
        "## 锁定组合",
        "",
        "| 旋钮 | 锁定值 |",
        "|------|--------|",
        "| 组间 L1 证据预算 (F) | **%s** |" % fc["l1_evidence_budget"],
        "| 组内 L2 local | **%s** |" % fc["l2_local_evidence_budget"],
        "| 组间 L2 between | **%s** |" % fc["l2_between_evidence_budget"],
        "| 每活家族 L2 候选上限 | **%s** |" % fc["l2_candidate_max_per_live_family"],
        "| 后验池 N | **%s** |" % fc["pool_n"],
        "| 提交 K | **%s** |" % fc["k"],
        "| 离线重排器 | `%s` |" % fc["reranker"],
        "| 正式端点 | `%s` |" % fc["paper_endpoint"],
        "",
        "- 锁定预算 Acc@1=**%.4f**；gold-leaf hit=**%.4f**"
        % (
            float(lb["acc_at1"]["acc_at1"]),
            float(lb["gold_leaf_coverage"]["hit_rate"]),
        ),
        "- 锁定短列表 Acc@1=**%.4f**；hit@K=**%.4f**"
        % (
            float(ls["shortlist"]["acc_at1"]),
            float(ls["shortlist"]["hit_at_k"]),
        ),
        "- F6 对照（同短列表设定）Acc@1=**%.4f**"
        % float(f6["shortlist"]["acc_at1"]),
        "",
        "## 预算网格（按 Acc@1 排序，Top-8）",
        "",
        "| L1 | L2 local | L2 cand | Acc@1 | gold-leaf hit |",
        "|----|----------|---------|-------|---------------|",
    ]
    for r in doc["budget_grid"][:8]:
        lines.append(
            "| %s | %s | %s | %.4f | %.4f |"
            % (
                r["l1_evidence_budget"],
                r["l2_local_evidence_budget"],
                r["l2_candidate_max_per_live_family"],
                float(r["acc_at1"]["acc_at1"]),
                float(r["gold_leaf_coverage"]["hit_rate"]),
            )
        )
    lines += [
        "",
        "## 短列表网格（锁定预算下，Top-8）",
        "",
        "| pool_n | K | reranker | Acc@1 | hit@K |",
        "|--------|---|----------|-------|-------|",
    ]
    for r in doc["shortlist_grid"][:8]:
        lines.append(
            "| %s | %s | `%s` | %.4f | %.4f |"
            % (
                r["pool_n"],
                r["k"],
                r["reranker"],
                float(r["shortlist"]["acc_at1"]),
                float(r["shortlist"]["hit_at_k"]),
            )
        )
    lines += [
        "",
        "## 边界",
        "",
        "- 证据预算为离线家族/叶保留代理，**不是** live F 重 annotate。",
        "- 正式 Acc 需侧跑 live 重标 + LLM judge（`ddx_k=5` / compat）。",
        "- 不得未经本网格把 DA/MCR 的 F6 或 OX 的 F4 直接标为 RA 最优。",
        "",
        "## 复现",
        "",
        "```bash",
        "PYTHONPATH=src:scripts/paper python3 scripts/paper/audit_ra_budget_recalib.py \\",
        "  --run-dir logs/rarearena_ra_rdc_seq100_v1/compat_synonym_v1",
        "```",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-dir", type=Path, default=DEFAULT_RUN)
    ap.add_argument("--subset-parquet", type=Path, default=DEFAULT_PARQUET)
    ap.add_argument("--tree-subdir", default="shared_trees")
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--out-json", type=Path, default=DEFAULT_OUT_JSON)
    ap.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    args = ap.parse_args(list(argv) if argv is not None else None)

    doc = analyze(
        args.run_dir,
        subset_parquet=args.subset_parquet,
        quick=bool(args.quick),
        tree_subdir=str(args.tree_subdir),
    )
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
                "locked_acc": doc["locked_budget"]["acc_at1"]["acc_at1"],
                "locked_gold_leaf_hit": doc["locked_budget"]["gold_leaf_coverage"][
                    "hit_rate"
                ],
                "f6_ref_acc": doc["f6_reference"]["shortlist"]["acc_at1"],
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
