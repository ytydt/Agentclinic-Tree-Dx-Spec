#!/usr/bin/env python3
"""MCR open Acc@1 Wave-1 ablation: B0/B1/R1–R4 (+ R5 any-hit@K secondary).

Main metric: diagnostic_accuracy_single_trajectory (Prompt7 LLM Acc).
Does not mix mapper option_top1 into the primary table.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
_PAPER = ROOT / "scripts" / "paper"
sys.path.insert(0, str(_PAPER))
sys.path.insert(0, str(ROOT / "src"))

from build_eval_projection import (  # noqa: E402
    DEFAULT_DDX_K,
    DDX_SOURCE_CALIB_ONLY_POST,
    DDX_SOURCE_COMPAT,
    DDX_SOURCE_COMPAT_THEN_PAD,
    DDX_SOURCE_GATE_ON_POST,
    DDX_SOURCE_POSTERIOR,
    build_eval_projections,
    normalize_ddx_source,
    resolve_annotate_dir,
)
from mapper_bind_repair import leaf_match_score  # noqa: E402
from run_ox_mcr_official_eval import run_eval  # noqa: E402
from transfer_eval import io_gold  # noqa: E402
from transfer_eval.matching import DEFAULT_LEXICAL_THRESHOLD  # noqa: E402

DEFAULT_RUN = ROOT / "logs/medcasereasoning_mcr_val_seq100_v1/compat_synonym_v1"
DEFAULT_PARQUET = (
    ROOT / "data/benchmarks/medcasereasoning/subsets/mcr_val_seq100_v1/cases.parquet"
)
DEFAULT_REPORT_DIR = ROOT / "analysis/transfer_metrics_v1"

# Gates from plan
G1_ABS = 0.55
G1_DELTA = 0.03
G2_ABS = 0.60
G3_DROP = -0.02

ARMS: list[dict[str, Any]] = [
    {
        "arm_id": "B0",
        "ddx_source": DDX_SOURCE_COMPAT,
        "ddx_k": 5,
        "role": "anchor_compat",
        "reuse_eval_subdir": "official_eval_llm_compat",
        "out_name_llm": "official_eval_llm_compat",
        "out_name_lex": "official_eval_compat",
    },
    {
        "arm_id": "B1",
        "ddx_source": DDX_SOURCE_POSTERIOR,
        "ddx_k": 5,
        "role": "anchor_posterior",
        "reuse_eval_subdir": "official_eval_llm",
        "out_name_llm": "official_eval_llm",
        "out_name_lex": "official_eval",
    },
    {
        "arm_id": "R1",
        "ddx_source": DDX_SOURCE_POSTERIOR,
        "ddx_k": 5,
        "role": "pool_upper_bound_topk1",
        "note": "Same projection as B1; Acc@1 identical to B1 (Top-1 of posterior).",
        "out_name_llm": "official_eval_llm_r1_post_k5",
        "out_name_lex": "official_eval_r1_post_k5",
        "projection_subdir": "eval_projection",
        "skip_rebuild_if_exists": True,
        "alias_acc_of": "B1",
    },
    {
        "arm_id": "R1k7",
        "ddx_source": DDX_SOURCE_POSTERIOR,
        "ddx_k": 7,
        "role": "pool_coverage_k7",
        "note": "Posterior Top-7 list; Acc@1 still posterior Top-1 (same as B1).",
        "out_name_llm": "official_eval_llm_r1_post_k7",
        "out_name_lex": "official_eval_r1_post_k7",
        "projection_subdir": "eval_projection_k7",
        "alias_acc_of": "B1",
    },
    {
        "arm_id": "R2",
        "ddx_source": DDX_SOURCE_COMPAT_THEN_PAD,
        "ddx_k": 5,
        "role": "compat_then_pad",
        "out_name_llm": "official_eval_llm_compat_then_pad",
        "out_name_lex": "official_eval_compat_then_pad",
    },
    {
        "arm_id": "R3",
        "ddx_source": DDX_SOURCE_GATE_ON_POST,
        "ddx_k": 5,
        "role": "gate_on_post_pool",
        "out_name_llm": "official_eval_llm_gate_on_post",
        "out_name_lex": "official_eval_gate_on_post",
        "projection_subdir": "eval_projection_gate_on_post",
    },
    {
        "arm_id": "R3live",
        "ddx_source": DDX_SOURCE_GATE_ON_POST,
        "ddx_k": 5,
        "role": "gate_on_post_pool_live",
        "live_calib": True,
        "out_name_llm": "official_eval_llm_gate_on_post_live",
        "out_name_lex": "official_eval_gate_on_post_live",
        "projection_subdir": "eval_projection_gate_on_post_live",
    },
    {
        "arm_id": "R4",
        "ddx_source": DDX_SOURCE_CALIB_ONLY_POST,
        "ddx_k": 5,
        "role": "calib_only_on_post",
        "note": "Dry calib ≈ prior/posterior order; see R4live.",
        "out_name_llm": "official_eval_llm_calib_only_post",
        "out_name_lex": "official_eval_calib_only_post",
        "projection_subdir": "eval_projection_calib_only_post",
    },
    {
        "arm_id": "R4live",
        "ddx_source": DDX_SOURCE_CALIB_ONLY_POST,
        "ddx_k": 5,
        "role": "calib_only_on_post_live",
        "live_calib": True,
        "out_name_llm": "official_eval_llm_calib_only_post_live",
        "out_name_lex": "official_eval_calib_only_post_live",
        "projection_subdir": "eval_projection_calib_only_post_live",
    },
]


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, doc: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def lexical_any_hit_topk(
    proj_dir: Path,
    gold_map: Mapping[str, Mapping[str, Any]],
    *,
    k: int = 5,
    threshold: float = DEFAULT_LEXICAL_THRESHOLD,
) -> dict[str, Any]:
    hits = 0
    hit1 = 0
    n = 0
    empty = 0
    for cid, gold in gold_map.items():
        path = proj_dir / ("%s.json" % cid)
        if not path.is_file():
            continue
        proj = _read_json(path)
        gold_dx = str(gold.get("final_diagnosis") or "").strip()
        ddx = list(proj.get("pred_ddx") or [])[:k]
        if not ddx:
            empty += 1
        n += 1
        labels = [str(r.get("label") or "").strip() for r in ddx]
        labels = [x for x in labels if x]
        if not gold_dx or not labels:
            continue
        scores = [leaf_match_score(lab, gold_dx) for lab in labels]
        if scores and scores[0] >= threshold:
            hit1 += 1
        if any(s >= threshold for s in scores):
            hits += 1
    return {
        "n_cases": n,
        "n_empty_ddx": empty,
        "lexical_hit_at_1": (hit1 / n) if n else 0.0,
        "lexical_any_hit_at_k": (hits / n) if n else 0.0,
        "k": int(k),
        "threshold": float(threshold),
        "protocol": "any_hit_compat_list_v1" if "compat" in str(proj_dir) else (
            "any_hit_topk_posterior_v1"
        ),
    }


def classify_miss_bucket(row: Mapping[str, Any]) -> str:
    if int(row.get("fr_len") or 0) == 0 or not row.get("fr"):
        return "A"
    if row.get("gold_in_compat_list") and int(row.get("gold_rank_compat") or 0) > 1:
        return "C"
    if int(row.get("n_soft_leaves") or 0) > 0 and not row.get("gold_in_compat_list"):
        return "D"
    if int(row.get("n_soft_leaves") or 0) == 0 and not row.get("gold_in_compat_list"):
        return "E"
    if (
        int(row.get("gold_rank_compat") or 0) == 1
        or row.get("soft_top1")
        or row.get("lex_top1")
    ):
        return "B"
    return "other"


def load_baseline_taxonomy(annotate: Path) -> dict[str, Any] | None:
    path = annotate / "official_eval_llm_compat" / "acc_miss_taxonomy.json"
    if not path.is_file():
        return None
    return _read_json(path)


def apply_gates(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    by_id = {str(r["arm_id"]): r for r in rows}
    b0 = float(by_id.get("B0", {}).get("llm_acc") or 0.0)
    promotions: list[str] = []
    rejects: list[str] = []
    g2: list[str] = []
    for r in rows:
        aid = str(r["arm_id"])
        if aid in {"B0", "B1", "R1", "R1k7"}:
            continue
        acc = r.get("llm_acc")
        if acc is None:
            continue
        acc_f = float(acc)
        delta = acc_f - b0
        if delta <= G3_DROP:
            rejects.append(aid)
            continue
        if acc_f >= G1_ABS and delta >= G1_DELTA:
            promotions.append(aid)
        if acc_f >= G2_ABS:
            g2.append(aid)
    # G4: any-hit@5 must not drop vs B0 (or annotate pool shrink)
    b0_any = by_id.get("B0", {}).get("lexical_any_hit_at_k")
    g4_ok: list[str] = []
    g4_warn: list[str] = []
    if b0_any is not None:
        for r in rows:
            aid = str(r["arm_id"])
            if aid in {"B0", "B1"}:
                continue
            ah = r.get("lexical_any_hit_at_k")
            if ah is None:
                continue
            if float(ah) + 1e-9 >= float(b0_any):
                g4_ok.append(aid)
            else:
                g4_warn.append(aid)
    return {
        "b0_llm_acc": b0,
        "g1_promote_candidates": promotions,
        "g2_transfer_recommend": g2,
        "g3_reject": rejects,
        "g4_anyhit_ok": g4_ok,
        "g4_anyhit_drop_warn": g4_warn,
        "thresholds": {
            "G1_abs": G1_ABS,
            "G1_delta": G1_DELTA,
            "G2_abs": G2_ABS,
            "G3_drop": G3_DROP,
        },
    }


def _reuse_llm_acc(annotate: Path, subdir: str) -> float | None:
    path = annotate / subdir / "summary.json"
    if not path.is_file():
        return None
    doc = _read_json(path)
    m = doc.get("metrics") or {}
    v = m.get("diagnostic_accuracy_single_trajectory")
    return float(v) if v is not None else None


def run_arm_eval(
    *,
    arm: Mapping[str, Any],
    run_dir: Path,
    subset_parquet: Path,
    judge: str,
    workers: int,
    resume_scores: bool,
    dry_calib: bool,
    force_rebuild: bool,
) -> dict[str, Any]:
    annotate = resolve_annotate_dir(run_dir)
    src = normalize_ddx_source(str(arm["ddx_source"]))
    ddx_k = int(arm.get("ddx_k") or DEFAULT_DDX_K)
    proj_sub = str(arm.get("projection_subdir") or "")
    out_llm = str(arm.get("out_name_llm") or "")
    out_lex = str(arm.get("out_name_lex") or "")
    arm_dry = not bool(arm.get("live_calib")) if "live_calib" in arm else dry_calib

    # Build / refresh projection unless aliased to existing
    if not arm.get("skip_rebuild_if_exists") or force_rebuild:
        build_eval_projections(
            run_dir,
            ddx_k=ddx_k,
            resume=not force_rebuild and bool(arm.get("skip_rebuild_if_exists")),
            ddx_source=src,
            out_subdir=proj_sub,
            dry_calib=arm_dry,
        )
    elif proj_sub:
        pdir = annotate / proj_sub
        if not pdir.is_dir() or not any(pdir.glob("*.json")):
            build_eval_projections(
                run_dir,
                ddx_k=ddx_k,
                resume=False,
                ddx_source=src,
                out_subdir=proj_sub,
                dry_calib=arm_dry,
            )

    # Resolve actual projection dir
    from build_eval_projection import _auto_proj_subdir

    actual_proj = proj_sub or _auto_proj_subdir(src)
    proj_dir = annotate / actual_proj

    row: dict[str, Any] = {
        "arm_id": arm["arm_id"],
        "ddx_source": src,
        "ddx_k": ddx_k,
        "role": arm.get("role"),
        "note": arm.get("note"),
        "projection_subdir": actual_proj,
        "n_empty_compat_fallback": None,
    }
    # Count empty fallbacks from projections
    n_fb = 0
    n_proj = 0
    for p in proj_dir.glob("*.json"):
        n_proj += 1
        try:
            doc = _read_json(p)
            if (doc.get("sources") or {}).get("fallback") == "empty_compat":
                n_fb += 1
        except Exception:  # noqa: BLE001
            pass
    row["n_projections"] = n_proj
    row["n_empty_compat_fallback"] = n_fb

    # Lexical Acc (+ cheap any-hit)
    lex_summary = run_eval(
        dataset="medcasereasoning",
        run_dir=run_dir,
        subset_parquet=subset_parquet,
        judge_kind="lexical",
        ddx_k=ddx_k,
        build_projection=False,
        skip_reasoning_recall=True,
        ddx_source=src,
        projection_subdir=actual_proj,
        out_name=out_lex,
        resume_scores=resume_scores,
        workers=1,
        dry_calib=arm_dry,
    )
    row["lexical_acc"] = float(
        (lex_summary.get("metrics") or {}).get(
            "diagnostic_accuracy_single_trajectory"
        )
        or 0.0
    )
    row["lexical_eval_dir"] = out_lex
    row["dry_calib"] = arm_dry

    gold_map = io_gold.load_gold("medcasereasoning", subset_parquet)
    anyhit = lexical_any_hit_topk(proj_dir, gold_map, k=ddx_k)
    row["lexical_hit_at_1"] = anyhit["lexical_hit_at_1"]
    row["lexical_any_hit_at_k"] = anyhit["lexical_any_hit_at_k"]
    row["any_hit_protocol"] = anyhit["protocol"]

    # Acc@1 alias (R1 / R1k7 → B1)
    if arm.get("alias_acc_of") and judge == "llm":
        alias = str(arm["alias_acc_of"])
        row["llm_acc_alias_of"] = alias

    if judge != "llm":
        row["llm_acc"] = None
        return row

    reuse = arm.get("reuse_eval_subdir")
    if reuse and not force_rebuild:
        reused = _reuse_llm_acc(annotate, str(reuse))
        if reused is not None:
            row["llm_acc"] = reused
            row["llm_eval_dir"] = str(reuse)
            row["llm_reused"] = True
            return row

    if arm.get("alias_acc_of"):
        row["llm_acc"] = None
        row["llm_eval_dir"] = out_llm
        row["llm_reused"] = False
        row["defer_alias"] = True
        return row

    llm_summary = run_eval(
        dataset="medcasereasoning",
        run_dir=run_dir,
        subset_parquet=subset_parquet,
        judge_kind="llm",
        ddx_k=ddx_k,
        build_projection=False,
        skip_reasoning_recall=True,
        ddx_source=src,
        projection_subdir=actual_proj,
        out_name=out_llm,
        resume_scores=resume_scores,
        workers=workers,
        dry_calib=arm_dry,
    )
    row["llm_acc"] = float(
        (llm_summary.get("metrics") or {}).get(
            "diagnostic_accuracy_single_trajectory"
        )
        or 0.0
    )
    row["llm_eval_dir"] = out_llm
    row["llm_reused"] = False
    row["n_llm_errors"] = int(llm_summary.get("n_errors") or 0)
    return row


def render_report(
    *,
    summary: Mapping[str, Any],
) -> str:
    rows = list(summary.get("arms") or [])
    gates = summary.get("gates") or {}
    lines = [
        "# MCR Open Acc@1 Ablation Report",
        "",
        "- created_at: `%s`" % summary.get("created_at"),
        "- run_dir: `%s`" % summary.get("run_dir"),
        "- primary_metric: `diagnostic_accuracy_single_trajectory` (Prompt7 / Gemini 2.5 Flash)",
        "- dry_calib: `%s`" % summary.get("dry_calib"),
        "",
        "## Primary table (LLM Acc@1)",
        "",
        "| arm | source | K | LLM Acc@1 | Δ vs B0 | lex Acc@1 | lex any-hit@K | empty_fb |",
        "|-----|--------|---|-----------|---------|-----------|---------------|----------|",
    ]
    b0 = float(gates.get("b0_llm_acc") or 0.0)
    for r in rows:
        acc = r.get("llm_acc")
        acc_s = "%.4f" % float(acc) if acc is not None else "—"
        delta = ""
        if acc is not None:
            delta = "%+.4f" % (float(acc) - b0)
        lines.append(
            "| %s | `%s` | %s | %s | %s | %.4f | %.4f | %s |"
            % (
                r.get("arm_id"),
                r.get("ddx_source"),
                r.get("ddx_k"),
                acc_s,
                delta,
                float(r.get("lexical_acc") or 0.0),
                float(r.get("lexical_any_hit_at_k") or 0.0),
                r.get("n_empty_compat_fallback"),
            )
        )
    lines += [
        "",
        "## Gates",
        "",
        "- G1 promote (≥%.2f and ≥B0+%.2f): **%s**"
        % (G1_ABS, G1_DELTA, ", ".join(gates.get("g1_promote_candidates") or []) or "none"),
        "- G2 transfer (≥%.2f): **%s**"
        % (G2_ABS, ", ".join(gates.get("g2_transfer_recommend") or []) or "none"),
        "- G3 reject (Δ≤%.2f): **%s**"
        % (G3_DROP, ", ".join(gates.get("g3_reject") or []) or "none"),
        "- G4 any-hit@K ok: %s"
        % (", ".join(gates.get("g4_anyhit_ok") or []) or "n/a"),
        "- G4 any-hit drop warn: %s"
        % (", ".join(gates.get("g4_anyhit_drop_warn") or []) or "none"),
        "",
        "## R5 (secondary any-hit@K, not Acc main table)",
        "",
    ]
    r5 = summary.get("r5") or {}
    lines.append(
        "- best pool arm for any-hit: **%s** (lex any-hit@K=%.4f)"
        % (r5.get("best_arm"), float(r5.get("best_any_hit") or 0.0))
    )
    lines.append("- protocol: `%s`" % r5.get("protocol"))
    lines += [
        "",
        "## Boundaries",
        "",
    ]
    for b in summary.get("boundaries") or []:
        lines.append("- %s" % b)
    tax = summary.get("baseline_taxonomy") or {}
    if tax:
        lines += [
            "",
            "## Baseline miss taxonomy (B0 compat LLM, n=%s)"
            % tax.get("n_miss", "?"),
            "",
        ]
        for k, v in (tax.get("tax") or {}).items():
            lines.append("- %s: %s" % (k, v))
    e_audit = summary.get("e_audit")
    if e_audit:
        lines += [
            "",
            "## Wave-2 E-class coverage audit",
            "",
            "- n_E: %s" % e_audit.get("n_e"),
            "- axis_in_leaf_out: %s" % e_audit.get("n_axis_in_leaf_out"),
            "- axis_absent: %s" % e_audit.get("n_axis_absent"),
            "- decision: **%s**" % e_audit.get("decision"),
            "- detail: `%s`" % e_audit.get("artifact"),
        ]
    lines.append("")
    return "\n".join(lines)


def audit_e_class(
    *,
    annotate: Path,
    taxonomy: Mapping[str, Any] | None,
    report_dir: Path,
) -> dict[str, Any]:
    """Offline audit: gold on axis / non-leaf vs leaf-absent for E misses."""
    from build_eval_projection import load_tree_state
    from mapper_bind_repair import leaves_from_tree_state

    if not taxonomy:
        return {"skipped": True, "reason": "no taxonomy"}
    e_rows = []
    for row in taxonomy.get("miss") or []:
        if classify_miss_bucket(row) != "E":
            continue
        e_rows.append(row)

    axis_in_leaf_out = 0
    axis_absent = 0
    details: list[dict[str, Any]] = []
    for row in e_rows:
        cid = str(row.get("cid"))
        gold = str(row.get("gold") or "").strip()
        tree_path = annotate / "shared_trees" / ("%s.json" % cid)
        case_path = annotate / "case_results" / ("%s.json" % cid)
        p5_path = annotate / "p5_audit" / ("%s.json" % cid)
        tree = load_tree_state(tree_path) if tree_path.is_file() else {}
        branches = tree.get("branches") or {}
        leaves = leaves_from_tree_state(tree) if tree else []
        leaf_labels = [str(x.get("leaf_label") or "") for x in leaves]
        leaf_hit = any(
            leaf_match_score(lab, gold) >= DEFAULT_LEXICAL_THRESHOLD
            for lab in leaf_labels
            if lab
        )
        # Axis / non-leaf: any non-leaf branch label soft-match gold
        nonleaf_hits: list[str] = []
        for bid, node in branches.items():
            if not isinstance(node, Mapping):
                continue
            children = node.get("children") or []
            if not children:
                continue  # leaf
            lab = str(node.get("label") or "").strip()
            if lab and leaf_match_score(lab, gold) >= DEFAULT_LEXICAL_THRESHOLD:
                nonleaf_hits.append("%s:%s" % (bid, lab))
        # Also L1 posteriors / representative_diseases / P5 candidates
        case_doc = _read_json(case_path) if case_path.is_file() else {}
        l1_hits: list[str] = []
        for r in (case_doc.get("l1") or {}).get("l1_posteriors") or []:
            if not isinstance(r, Mapping):
                continue
            lab = str(r.get("label") or r.get("name") or "").strip()
            if lab and leaf_match_score(lab, gold) >= DEFAULT_LEXICAL_THRESHOLD:
                l1_hits.append(lab)
        gran = (case_doc.get("l2") or {}).get("granularity") or {}
        reps = list(gran.get("representative_diseases") or [])
        rep_hits = [
            str(x)
            for x in reps
            if leaf_match_score(str(x), gold) >= DEFAULT_LEXICAL_THRESHOLD
        ]
        p5_cands: list[str] = []
        if p5_path.is_file():
            p5 = _read_json(p5_path)
            for rule in p5.get("rules") or []:
                for eff in (rule.get("effects") or []) if isinstance(rule, Mapping) else []:
                    if not isinstance(eff, Mapping):
                        continue
                    c = str(eff.get("candidate") or "").strip()
                    if c and leaf_match_score(c, gold) >= DEFAULT_LEXICAL_THRESHOLD:
                        p5_cands.append(c)
        axis_like = bool(nonleaf_hits or l1_hits or rep_hits or p5_cands)
        if leaf_hit:
            bucket = "leaf_present_reclass"  # should not be E
        elif axis_like:
            bucket = "axis_in_leaf_out"
            axis_in_leaf_out += 1
        else:
            bucket = "axis_absent"
            axis_absent += 1
        details.append({
            "cid": cid,
            "gold": gold,
            "bucket": bucket,
            "nonleaf_hits": nonleaf_hits[:5],
            "l1_hits": l1_hits[:5],
            "rep_hits": rep_hits[:5],
            "p5_candidate_hits": sorted(set(p5_cands))[:8],
            "n_leaves": len(leaves),
        })

    n_e = len(e_rows)
    # Gate: if ≥8/15 axis_in_leaf_out → limited L2 leaf expand experiment
    if axis_in_leaf_out >= 8:
        decision = "run_limited_l2_leaf_expand"
    elif axis_absent >= (n_e - axis_in_leaf_out) and axis_in_leaf_out < 8:
        decision = "deferred_generation"
    else:
        decision = "deferred_generation"

    out = {
        "n_e": n_e,
        "n_axis_in_leaf_out": axis_in_leaf_out,
        "n_axis_absent": axis_absent,
        "n_leaf_present_reclass": sum(
            1 for d in details if d["bucket"] == "leaf_present_reclass"
        ),
        "decision": decision,
        "threshold_axis_in_for_expand": 8,
        "details": details,
    }
    art = report_dir / "mcr_e_class_coverage_audit.json"
    _write_json(art, out)
    out["artifact"] = str(art)
    return out


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-dir", type=Path, default=DEFAULT_RUN)
    ap.add_argument("--subset-parquet", type=Path, default=DEFAULT_PARQUET)
    ap.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    ap.add_argument("--judge", choices=["lexical", "llm"], default="llm")
    ap.add_argument("--workers", type=int, default=50)
    ap.add_argument("--resume-scores", action="store_true")
    ap.add_argument("--force-rebuild", action="store_true")
    ap.add_argument("--live-calib", action="store_true")
    ap.add_argument(
        "--arms",
        default="",
        help="comma arm ids (default: all). e.g. B0,B1,R2,R3",
    )
    ap.add_argument("--skip-e-audit", action="store_true")
    args = ap.parse_args(list(argv) if argv is not None else None)

    run_dir = Path(args.run_dir)
    annotate = resolve_annotate_dir(run_dir)
    want = {
        x.strip()
        for x in str(args.arms or "").split(",")
        if x.strip()
    }
    arms = [a for a in ARMS if not want or a["arm_id"] in want]

    results: list[dict[str, Any]] = []
    for arm in arms:
        print("[ablation] arm %s ..." % arm["arm_id"], flush=True)
        row = run_arm_eval(
            arm=arm,
            run_dir=run_dir,
            subset_parquet=Path(args.subset_parquet),
            judge=str(args.judge),
            workers=int(args.workers),
            resume_scores=bool(args.resume_scores),
            dry_calib=not bool(args.live_calib),
            force_rebuild=bool(args.force_rebuild),
        )
        results.append(row)
        print(
            "[ablation] %s lex=%.4f llm=%s anyhit=%.4f"
            % (
                row["arm_id"],
                float(row.get("lexical_acc") or 0),
                row.get("llm_acc"),
                float(row.get("lexical_any_hit_at_k") or 0),
            ),
            flush=True,
        )

    # Resolve Acc@1 aliases (R1 / R1k7 → B1)
    by_id = {r["arm_id"]: r for r in results}
    for r in results:
        alias = r.get("llm_acc_alias_of") or (
            "B1" if r.get("defer_alias") else None
        )
        if alias and r.get("llm_acc") is None and alias in by_id:
            r["llm_acc"] = by_id[alias].get("llm_acc")
            r["llm_reused"] = True
            r["note"] = (r.get("note") or "") + " Acc@1 aliased from %s." % alias

    gates = apply_gates(results)
    # R5: pick best any-hit among R2/R3 (or R1k7)
    cand = [
        r for r in results
        if r["arm_id"] in {"R2", "R3", "R1", "R1k7", "B0"}
    ]
    best = max(cand, key=lambda r: float(r.get("lexical_any_hit_at_k") or 0.0)) if cand else {}
    r5 = {
        "best_arm": best.get("arm_id"),
        "best_any_hit": best.get("lexical_any_hit_at_k"),
        "protocol": "any_hit_topk_posterior_v1 / any_hit_compat_list_v1 (lexical)",
        "note": "Secondary coverage bound; not primary Acc.",
    }

    tax_doc = load_baseline_taxonomy(annotate)
    tax_summary = None
    if tax_doc:
        tax_summary = {
            "n_miss": len(tax_doc.get("miss") or []),
            "tax": tax_doc.get("tax"),
        }

    e_audit = None
    if not args.skip_e_audit:
        e_audit = audit_e_class(
            annotate=annotate,
            taxonomy=tax_doc,
            report_dir=Path(args.report_dir),
        )

    summary: dict[str, Any] = {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "run_dir": str(run_dir.resolve()),
        "subset_parquet": str(Path(args.subset_parquet).resolve()),
        "judge": args.judge,
        "workers": int(args.workers),
        "dry_calib": not bool(args.live_calib),
        "arms": results,
        "gates": gates,
        "r5": r5,
        "baseline_taxonomy": tax_summary,
        "e_audit": (
            {k: v for k, v in e_audit.items() if k != "details"}
            if e_audit
            else None
        ),
        "boundaries": [
            "Primary metric is Prompt7 LLM Acc@1; mapper option_top1 must not be mixed in.",
            "single_trajectory_v1 ≠ paper 10-shot Acc.",
            "Wave-1 offline rerank; trees not rebuilt.",
            "R4 default dry_calib is near-identity prior order; use --live-calib for true calib.",
            "E-class requires generation / limited L2 expand; see e_audit.decision.",
        ],
    }

    report_dir = Path(args.report_dir)
    json_path = report_dir / "mcr_open_acc_ablation_summary.json"
    md_path = report_dir / "mcr_open_acc_ablation_report.md"
    _write_json(json_path, summary)
    _write_text(md_path, render_report(summary=summary))
    print(json.dumps({
        "summary_json": str(json_path),
        "report_md": str(md_path),
        "gates": gates,
        "arms": [
            {
                "arm_id": r["arm_id"],
                "llm_acc": r.get("llm_acc"),
                "lexical_acc": r.get("lexical_acc"),
                "lexical_any_hit_at_k": r.get("lexical_any_hit_at_k"),
            }
            for r in results
        ],
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
