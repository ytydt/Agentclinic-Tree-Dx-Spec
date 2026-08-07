#!/usr/bin/env python3
"""Stage 3: formal LLM gate for emit_v1 + locked OX budget/shortlist.

1) Materialize side run ``compat_synonym_emit_v1`` with emit overlay trees
2) Build closed_live_mac projections (prefer --live-closed-mac; else remap)
3) Score with paper_aligned_judge_v1
4) Compare vs B00 / MAC / no-emit live; bootstrap ΔF1 vs B00

Outputs:
  analysis/transfer_metrics_v1/ox_emit_locked_llm_gate.{md,json}
"""
from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "paper"))

import build_eval_projection as bep  # noqa: E402
from audit_ox_b00_b05_anomaly import (  # noqa: E402
    bootstrap_mean_ci,
    load_arm_scores,
    load_summary_micro,
    load_tree_scores,
    paired_f1,
)
from audit_ox_budget_recalib import apply_budget_proxy, shortlist_for  # noqa: E402
from audit_ox_c2a_force_emit import _labs  # noqa: E402
from audit_ox_emit_then_rerank import load_frozen_live_labels  # noqa: E402

DEFAULT_SRC = ROOT / "logs/open_xddx_ox_seq100_v1/compat_synonym_v1"
DEFAULT_EMIT_RUN = ROOT / "logs/open_xddx_ox_seq100_v1/compat_synonym_emit_v1"
DEFAULT_OX_ROOT = ROOT / "runs/paper_v1/open_xddx_ox_seq100_v1"
DEFAULT_SUBSET = ROOT / "data/benchmarks/open_xddx/subsets/ox_seq100_v1/cases.parquet"
DEFAULT_BUDGET = ROOT / "analysis/transfer_metrics_v1/ox_budget_recalib.json"
DEFAULT_OUT_JSON = ROOT / "analysis/transfer_metrics_v1/ox_emit_locked_llm_gate.json"
DEFAULT_OUT_MD = ROOT / "analysis/transfer_metrics_v1/ox_emit_locked_llm_gate.md"

PROJ_SUB = "eval_projection_emit_v1_locked"
EVAL_SUB = "official_eval_llm_emit_v1_locked"


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, doc: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def materialize_emit_run(src: Path, dst: Path, overlay_name: str = "emit_v1_overlay") -> Path:
    src_ann = src / "annotate"
    overlay_trees = src_ann / overlay_name / "shared_trees"
    if not overlay_trees.is_dir():
        raise FileNotFoundError(overlay_trees)
    dst_ann = dst / "annotate"
    dst_ann.mkdir(parents=True, exist_ok=True)
    # shared_trees from emit overlay
    tree_dst = dst_ann / "shared_trees"
    if tree_dst.exists() or tree_dst.is_symlink():
        if tree_dst.is_symlink() or tree_dst.is_file():
            tree_dst.unlink()
        else:
            shutil.rmtree(tree_dst)
    shutil.copytree(overlay_trees, tree_dst)
    # link reusable artifacts
    for name in (
        "cache",
        "case_results",
        "normalized_cases.json",
        "finding_fixture_v1.json",
        "mapper",
        "adjudication_sheet.json",
        "downstream_summary.json",
    ):
        s = src_ann / name
        d = dst_ann / name
        if not s.exists():
            continue
        if d.exists() or d.is_symlink():
            continue
        os.symlink(s.resolve(), d)
    # frozen
    if (src / "frozen").is_dir() and not (dst / "frozen").exists():
        os.symlink((src / "frozen").resolve(), dst / "frozen")
    _write_json(dst / "emit_v1_run_manifest.json", {
        "source_run": str(src),
        "overlay_trees": str(overlay_trees),
        "note": "Side run for Stage 3; trees = emit_v1 overlay, caches linked",
    })
    return dst_ann


def build_locked_projections(
    emit_ann: Path,
    src_ann: Path,
    combo: Mapping[str, Any],
    *,
    k: int,
) -> dict[str, Any]:
    """Write projections using locked budget proxy + closed_live_remap shortlist."""
    live_by = load_frozen_live_labels(src_ann)
    # Seed projection template from existing closed_live files when present
    template_dir = src_ann / "eval_projection_closed_live_mac"
    out_dir = emit_ann / PROJ_SUB
    out_dir.mkdir(parents=True, exist_ok=True)
    ids = sorted(
        (p.stem for p in (emit_ann / "shared_trees").glob("*.json")),
        key=lambda x: int(x) if x.isdigit() else x,
    )
    n_wrote = 0
    for cid in ids:
        tree = bep.load_tree_state(emit_ann / "shared_trees" / ("%s.json" % cid))
        prox = apply_budget_proxy(
            tree,
            l1_budget=int(combo["l1_evidence_budget"]),
            l2_local=int(combo["l2_local_evidence_budget"]),
            l2_cand_max=int(combo["l2_candidate_max_per_live_family"]),
        )
        labels = shortlist_for(
            prox,
            reranker="closed_live_remap",
            pool_n=int(combo["pool_n"]),
            k=k,
            frozen_live=live_by.get(cid) or [],
        )
        if (template_dir / ("%s.json" % cid)).is_file():
            doc = _read_json(template_dir / ("%s.json" % cid))
        else:
            doc = {"case_id": cid}
        pred_rows = []
        for i, lab in enumerate(labels[:k], start=1):
            pred_rows.append({
                "id": "emit_locked_%d" % i,
                "label": lab,
                "posterior": max(1e-6, 1.0 / i),
                "rank": i,
            })
        doc["case_id"] = cid
        doc["pred_ddx"] = pred_rows
        doc["pred_ddx_labels"] = [r["label"] for r in pred_rows]
        meta = dict(doc.get("projection_meta") or doc.get("meta") or {})
        meta.update({
            "ddx_source": "emit_v1_locked_closed_live_remap",
            "compat_dialect": "emit_v1_locked",
            "pool_n": int(combo["pool_n"]),
            "locked_budget": {
                "l1_evidence_budget": combo["l1_evidence_budget"],
                "l2_local_evidence_budget": combo["l2_local_evidence_budget"],
                "l2_candidate_max_per_live_family": combo[
                    "l2_candidate_max_per_live_family"
                ],
            },
            "live": False,
            "remap_frozen_live": True,
        })
        doc["projection_meta"] = meta
        doc["ddx_source"] = "emit_v1_locked_closed_live_remap"
        _write_json(out_dir / ("%s.json" % cid), doc)
        n_wrote += 1
    return {"n_projections": n_wrote, "proj_dir": str(out_dir)}


def run_llm_eval(
    emit_run: Path,
    subset: Path,
    *,
    workers: int,
    resume: bool,
) -> dict[str, Any]:
    cmd = [
        sys.executable,
        str(ROOT / "scripts/paper/run_ox_mcr_official_eval.py"),
        "--dataset", "open_xddx",
        "--run-dir", str(emit_run),
        "--subset-parquet", str(subset),
        "--judge", "llm",
        "--ddx-k", "5",
        "--workers", str(workers),
        "--projection-subdir", PROJ_SUB,
        "--out-name", EVAL_SUB,
        "--ddx-source", "posterior",
    ]
    if resume:
        cmd.append("--resume-scores")
    env = os.environ.copy()
    env["PYTHONPATH"] = "src:scripts/paper:" + env.get("PYTHONPATH", "")
    print("RUN:", " ".join(cmd), flush=True)
    subprocess.check_call(cmd, cwd=str(ROOT), env=env)
    summary_path = emit_run / "annotate" / EVAL_SUB / "summary.json"
    return _read_json(summary_path) if summary_path.is_file() else {}


def gate_decision(
    emit_micro: Mapping[str, Any],
    live_micro: Mapping[str, Any] | None,
    b00_micro: Mapping[str, Any] | None,
    paired_vs_b00: Mapping[str, Any],
    full_tree_r_ok: bool,
) -> dict[str, Any]:
    f1 = float(emit_micro.get("micro_f1") or 0)
    p = float(emit_micro.get("micro_precision") or 0)
    live_f1 = float((live_micro or {}).get("micro_f1") or 0)
    live_p = float((live_micro or {}).get("micro_precision") or 0)
    df1_live = f1 - live_f1
    dp_live = p - live_p
    ci = paired_vs_b00.get("delta_bootstrap") or {}
    ci_lo = float(ci.get("lo") or -1)
    cond1 = (f1 >= 0.570) or (df1_live >= 0.015 and dp_live >= -0.03)
    cond2 = ci_lo > 0
    cond3 = full_tree_r_ok
    promote = bool(cond1 and cond2 and cond3)
    return {
        "promote": promote,
        "cond_f1_or_delta_live": cond1,
        "cond_b00_ci_lo_gt0": cond2,
        "cond_full_tree_r": cond3,
        "emit_f1": f1,
        "emit_p": p,
        "live_f1": live_f1,
        "delta_f1_vs_live": df1_live,
        "delta_p_vs_live": dp_live,
        "b00_ci": ci,
        "verdict": "PROMOTE" if promote else "REJECT",
    }


def write_md(doc: Mapping[str, Any], path: Path) -> None:
    arms = doc.get("arms") or {}
    g = doc.get("gate") or {}
    lines = [
        "# OX emit_v1 + 锁定组合 — 正式 LLM 门控（Stage 3）",
        "",
        "协议：`paper_aligned_judge_v1`",
        "新臂：`emit_v1` + locked budget + closed_live_remap@pool15/K5",
        "机器表：[`ox_emit_locked_llm_gate.json`](ox_emit_locked_llm_gate.json)",
        "",
        "## 对照表（micro）",
        "",
        "| 臂 | P | R | F1 |",
        "|----|---|---|-----|",
    ]
    for key, name in (
        ("b00", "B00"),
        ("mac", "MAC B06"),
        ("gated", "gated_hybrid_mcr"),
        ("live", "closed_live (no emit)"),
        ("emit_locked", "emit_v1 + locked"),
    ):
        m = arms.get(key) or {}
        if not m:
            lines.append("| %s | — | — | — |" % name)
            continue
        lines.append(
            "| %s | %.4f | %.4f | %.4f |"
            % (
                name,
                float(m.get("micro_precision") or 0),
                float(m.get("micro_recall") or 0),
                float(m.get("micro_f1") or 0),
            )
        )
    pb = doc.get("paired") or {}
    lines += [
        "",
        "## 逐例 ΔF1",
        "",
        "- emit − live：mean=%s CI[%s, %s]"
        % (
            (pb.get("emit_minus_live") or {}).get("delta_bootstrap", {}).get("mean"),
            (pb.get("emit_minus_live") or {}).get("delta_bootstrap", {}).get("lo"),
            (pb.get("emit_minus_live") or {}).get("delta_bootstrap", {}).get("hi"),
        ),
        "- emit − B00：mean=%s CI[%s, %s]"
        % (
            (pb.get("emit_minus_b00") or {}).get("delta_bootstrap", {}).get("mean"),
            (pb.get("emit_minus_b00") or {}).get("delta_bootstrap", {}).get("lo"),
            (pb.get("emit_minus_b00") or {}).get("delta_bootstrap", {}).get("hi"),
        ),
        "",
        "## 门控",
        "",
        "- 结果：**%s**" % g.get("verdict"),
        "- F1≥0.570 或 vs live ΔF1≥+1.5pp 且 P 掉≤3pp：%s" % g.get("cond_f1_or_delta_live"),
        "- vs B00 95%% CI 下界 >0：%s" % g.get("cond_b00_ci_lo_gt0"),
        "- 全树 R 不降：%s" % g.get("cond_full_tree_r"),
        "",
        "## 边界",
        "",
    ]
    for b in doc.get("boundaries") or []:
        lines.append("- %s" % b)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source-run", type=Path, default=DEFAULT_SRC)
    ap.add_argument("--emit-run", type=Path, default=DEFAULT_EMIT_RUN)
    ap.add_argument("--ox-root", type=Path, default=DEFAULT_OX_ROOT)
    ap.add_argument("--subset-parquet", type=Path, default=DEFAULT_SUBSET)
    ap.add_argument("--budget-json", type=Path, default=DEFAULT_BUDGET)
    ap.add_argument("--workers", type=int, default=50)
    ap.add_argument("--skip-llm", action="store_true")
    ap.add_argument("--resume-scores", action="store_true")
    ap.add_argument("--out-json", type=Path, default=DEFAULT_OUT_JSON)
    ap.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    args = ap.parse_args(list(argv) if argv is not None else None)

    combo = _read_json(args.budget_json)["formal_combo"]
    src_ann = args.source_run / "annotate"
    emit_ann = materialize_emit_run(args.source_run, args.emit_run)
    proj_info = build_locked_projections(
        emit_ann, src_ann, combo, k=int(combo.get("k") or 5)
    )

    llm_summary: dict[str, Any] = {}
    if not args.skip_llm:
        try:
            llm_summary = run_llm_eval(
                args.emit_run,
                args.subset_parquet,
                workers=int(args.workers),
                resume=bool(args.resume_scores),
            )
        except Exception as exc:  # noqa: BLE001
            llm_summary = {"error": str(exc)}

    emit_scores = load_tree_scores(emit_ann, EVAL_SUB)
    live_scores = load_tree_scores(src_ann, "official_eval_llm_closed_live_mac")
    gated_scores = load_tree_scores(src_ann, "official_eval_llm_gated_hybrid_top2_mcr")
    b00_scores = load_arm_scores(args.ox_root, "B00-direct-cot")
    mac_scores = load_arm_scores(args.ox_root, "B06-mac-single-vendor")

    emit_micro = load_summary_micro(emit_ann / EVAL_SUB / "summary.json") or (
        (llm_summary.get("metrics") or {}).get("diagnostic_micro")
    )
    # Fallback: if LLM failed, compute lexical on projections for triage
    lexical_fallback = None
    if not emit_micro:
        from audit_ox_c2a_force_emit import load_gold, score_lists
        from transfer_eval.judges import LexicalJudge

        gold = load_gold(src_ann)
        preds = {}
        for p in (emit_ann / PROJ_SUB).glob("*.json"):
            d = _read_json(p)
            preds[p.stem] = list(d.get("pred_ddx_labels") or [])
        lexical_fallback = score_lists(preds, gold, LexicalJudge())
        emit_micro = {
            "micro_precision": lexical_fallback["micro_precision"],
            "micro_recall": lexical_fallback["micro_recall"],
            "micro_f1": lexical_fallback["micro_f1"],
            "judge": "lexical_fallback",
        }

    arms = {
        "b00": load_summary_micro(
            args.ox_root / "B00-direct-cot/replicate_01/annotate/official_eval_llm/summary.json"
        ),
        "mac": load_summary_micro(
            args.ox_root
            / "B06-mac-single-vendor/replicate_01/annotate/official_eval_llm/summary.json"
        ),
        "gated": load_summary_micro(
            src_ann / "official_eval_llm_gated_hybrid_top2_mcr/summary.json"
        ),
        "live": load_summary_micro(
            src_ann / "official_eval_llm_closed_live_mac/summary.json"
        ),
        "emit_locked": emit_micro,
    }

    paired = {}
    if emit_scores and live_scores:
        paired["emit_minus_live"] = paired_f1(emit_scores, live_scores)
    if emit_scores and b00_scores:
        paired["emit_minus_b00"] = paired_f1(emit_scores, b00_scores)
    elif not emit_scores and b00_scores:
        # synthesize per-case from lexical? skip CI
        paired["emit_minus_b00"] = {
            "delta_bootstrap": {"mean": None, "lo": None, "hi": None, "n": 0},
            "note": "no LLM case_scores; CI skipped",
        }

    # Full-tree R from emit validate
    validate = ROOT / "analysis/transfer_metrics_v1/ox_emit_v1_validate.md"
    full_r_ok = True
    emit_val = src_ann / "emit_v1_overlay" / "summary.json"
    if emit_val.is_file():
        full_r_ok = bool((_read_json(emit_val).get("gate") or {}).get("full_tree_r_up", True))

    gate = gate_decision(
        emit_micro or {},
        arms.get("live"),
        arms.get("b00"),
        paired.get("emit_minus_b00") or {},
        full_r_ok,
    )

    doc = {
        "protocol": "ox_emit_locked_llm_gate_v1",
        "formal_combo": combo,
        "emit_run": str(args.emit_run),
        "projection": proj_info,
        "llm_summary_path": str(emit_ann / EVAL_SUB / "summary.json"),
        "llm_error": llm_summary.get("error"),
        "lexical_fallback": lexical_fallback,
        "arms": arms,
        "paired": {
            k: {
                "n": v.get("n"),
                "n_win": v.get("n_win"),
                "n_tie": v.get("n_tie"),
                "n_lose": v.get("n_lose"),
                "delta_bootstrap": v.get("delta_bootstrap"),
                "note": v.get("note"),
            }
            for k, v in paired.items()
        },
        "gate": gate,
        "boundaries": [
            "Primary shortlist uses frozen-live remap on emit+budget trees (fair pool expansion; not a fresh live MAC call).",
            "Fresh --live-closed-mac on emit trees remains optional follow-up if remap CI fails.",
            "E_open_oracle is not used in this formal arm.",
        ],
    }
    _write_json(args.out_json, doc)
    write_md(doc, args.out_md)
    print(json.dumps({
        "out_json": str(args.out_json),
        "out_md": str(args.out_md),
        "verdict": gate.get("verdict"),
        "emit_f1": gate.get("emit_f1"),
        "llm_error": doc.get("llm_error"),
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
