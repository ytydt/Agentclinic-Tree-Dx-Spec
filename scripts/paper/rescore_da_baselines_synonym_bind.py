#!/usr/bin/env python3
"""Re-score DA baseline mapper records with synonym_bind repair (offline).

Applies Approach A ``rescore_after_synonym_bind`` on existing
``mapper/records.json`` projections (no typed-LLM re-map). Writes
``mapper_synonym_bind/`` beside each pred_dir for strict comparison with
Ours (compat + synonym_bind).

Usage:
  PYTHONPATH=src:scripts:scripts/paper python3 scripts/paper/rescore_da_baselines_synonym_bind.py
  PYTHONPATH=src:scripts:scripts/paper python3 scripts/paper/rescore_da_baselines_synonym_bind.py \\
    --pred-dir runs/paper_v1/diagnosisarena_remaining_v1/B07-meddxagent-complete/replicate_01
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "paper"))

import baseline_common as bc  # noqa: E402
import mapper_bind_repair as mbr  # noqa: E402
from baseline_mapper_score import top2_to_synthetic_leaves  # noqa: E402

# Main-table DA d2_seq100 arms (matches diagnosisarena_d2_seq100_baselines_summary.md)
DEFAULT_PRED_DIRS = [
    ROOT / "runs/paper_v1/diagnosisarena_remaining_v1/B00-direct-cot/replicate_01",
    ROOT / "runs/paper_v1/diagnosisarena_rag_smoke_live/B01-cot-rag/replicate_01",
    ROOT / "runs/paper_v1/diagnosisarena_fixed_v1/B02-flat-matched-rerank/replicate_01",
    ROOT / "runs/paper_v1/diagnosisarena_b02_compute_matched_v1/B02-flat-compute-matched/replicate_01",
    ROOT / "runs/paper_v1/diagnosisarena_b02_compute_matched_sc10_v1/B02-flat-compute-matched-sc10/replicate_01",
    ROOT / "runs/paper_v1/diagnosisarena_remaining_v1/B03-flat-beam/replicate_01",
    ROOT / "runs/paper_v1/diagnosisarena_fixed_v1/B04-dual-inf/replicate_01",
    ROOT / "runs/paper_v1/diagnosisarena_fixed_v1/B05-mdagents/replicate_01",
    ROOT / "runs/paper_v1/diagnosisarena_fixed_v1/B06-mac-single-vendor/replicate_01",
    ROOT / "runs/paper_v1/diagnosisarena_remaining_v1/B07-meddxagent-complete/replicate_01",
    ROOT / "runs/paper_v1/diagnosisarena_b11a_smoke/B11a-official-diagnosisgpt/replicate_01",
    ROOT / "runs/paper_v1/diagnosisarena_rag_smoke_live/B11b-cod-prompt-shared-kb/replicate_01",
    ROOT / "runs/paper_v1/diagnosisarena_remaining_v1/B12-sc-cot-5/replicate_01",
    ROOT / "runs/paper_v1/diagnosisarena_remaining_v1/B13-self-refine-1/replicate_01",
    ROOT / "runs/paper_v1/diagnosisarena_fixed_v1/B15-medprompt-style/replicate_01",
    ROOT / "runs/paper_v1/diagnosisarena_fixed_v1/B16-medrag-kg/replicate_01",
    ROOT / "runs/paper_v1/diagnosisarena_imedrag_v1/B17-imedrag/replicate_01",
]


def _load_records(path: Path) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    doc = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(doc, dict) and "records" in doc:
        return dict(doc.get("summary") or {}), list(doc.get("records") or [])
    if isinstance(doc, list):
        return None, list(doc)
    raise ValueError(f"unexpected mapper records schema: {path}")


def rescore_pred_dir(
    pred_dir: Path,
    cases_by_id: dict[str, dict[str, Any]],
    *,
    min_score: float,
    bridge: Path,
    out_name: str = "mapper_synonym_bind",
) -> dict[str, Any]:
    src = pred_dir / "mapper" / "records.json"
    if not src.is_file():
        return {"pred_dir": str(pred_dir), "status": "SKIP_NO_MAPPER"}

    base_summary, records = _load_records(src)
    out_records: list[dict[str, Any]] = []
    n_repaired = 0
    for row in records:
        cid = str(row.get("case_id") or "")
        case = cases_by_id.get(cid)
        if case is None:
            out_records.append({**row, "status": "SKIP_NO_CASE"})
            continue
        options = dict(case.get("options") or {})
        gold_letter = str(
            row.get("gold_letter") or case.get("_gold_letter") or ""
        ).upper()
        top2 = row.get("top2_diagnoses") or []
        leaves = top2_to_synthetic_leaves(top2)
        projection = row.get("projection") or {}
        scored = mbr.rescore_after_synonym_bind(
            {
                "case_id": cid,
                "gold_letter": gold_letter,
                "gold_option_text": options.get(gold_letter),
                "projection": projection,
            },
            leaves,
            options,
            min_score=min_score,
            bridge_path=bridge,
        )
        repaired = bool(scored.get("bind_repair_applied")) or int(
            scored.get("n_options_bind_repaired") or 0
        ) > 0
        if repaired:
            n_repaired += 1
        out_records.append(
            {
                "case_id": cid,
                "source_id": row.get("source_id") or case.get("source_id"),
                "gold_letter": gold_letter,
                "top2_diagnoses": list(top2),
                "option_top1": bool(scored.get("option_top1")),
                "option_top2": bool(scored.get("option_top2")),
                "option_rr": float(scored.get("option_rr") or 0.0),
                "option_rank": scored.get("gold_option_rank"),
                "synonym_bind_repair": {
                    "enabled": True,
                    "bind_repair_applied": repaired,
                    "n_options_bind_repaired": int(
                        scored.get("n_options_bind_repaired") or 0
                    ),
                    "min_score": float(min_score),
                },
                "projection": scored.get("projection") or projection,
                "baseline_mapper_before_bind": {
                    "option_top1": row.get("option_top1"),
                    "option_top2": row.get("option_top2"),
                    "option_rr": row.get("option_rr"),
                    "option_rank": row.get("option_rank"),
                },
            }
        )

    n = len(out_records)
    scored_ok = [
        r
        for r in out_records
        if r.get("status") != "SKIP_NO_CASE" and "option_top1" in r
    ]
    summary = {
        "n": len(scored_ok),
        "mapper_mode": (
            f"{(base_summary or {}).get('mapper_mode') or 'typed_llm_disagreement_rag'}"
            "+synonym_bind_repair"
        ),
        "synonym_bind_repair": True,
        "synonym_bind_min_score": float(min_score),
        "synonym_bind_bridge": str(bridge),
        "n_cases_bind_repaired": n_repaired,
        "option_top1": (
            round(sum(bool(r["option_top1"]) for r in scored_ok) / len(scored_ok), 4)
            if scored_ok
            else None
        ),
        "option_top2": (
            round(sum(bool(r["option_top2"]) for r in scored_ok) / len(scored_ok), 4)
            if scored_ok
            else None
        ),
        "mrr2": (
            round(sum(float(r["option_rr"]) for r in scored_ok) / len(scored_ok), 4)
            if scored_ok
            else None
        ),
        "baseline_without_bind": base_summary,
        "source_mapper_records": str(src),
    }
    out_dir = pred_dir / out_name
    out_dir.mkdir(parents=True, exist_ok=True)
    bc.atomic_json(out_dir / "records.json", {"summary": summary, "records": out_records})
    (out_dir / "summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    return {"pred_dir": str(pred_dir), "status": "OK", "summary": summary}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pred-dir", type=Path, action="append", default=[])
    ap.add_argument(
        "--subset-dir",
        type=Path,
        default=ROOT / "data/benchmarks/diagnosisarena/subsets/d2_seq100_v1",
    )
    ap.add_argument("--min-score", type=float, default=0.70)
    ap.add_argument(
        "--bridge",
        type=Path,
        default=Path(mbr.DEFAULT_BRIDGE_PATH),
    )
    ap.add_argument(
        "--out-tsv",
        type=Path,
        default=ROOT
        / "runs/paper_v1/diagnosisarena_d2_seq100_baselines_synonym_bind.tsv",
    )
    ap.add_argument(
        "--out-md",
        type=Path,
        default=ROOT
        / "runs/paper_v1/diagnosisarena_d2_seq100_baselines_synonym_bind.md",
    )
    args = ap.parse_args()

    pred_dirs = [Path(p) for p in args.pred_dir] if args.pred_dir else list(DEFAULT_PRED_DIRS)
    cases = bc.load_runtime_cases(subset_dir=args.subset_dir, dataset="diagnosisarena")
    by_id = {c["case_id"]: c for c in cases}

    rows: list[dict[str, Any]] = []
    for pred_dir in pred_dirs:
        print(f"=== {pred_dir} ===", flush=True)
        result = rescore_pred_dir(
            pred_dir,
            by_id,
            min_score=float(args.min_score),
            bridge=Path(args.bridge),
        )
        rows.append(result)
        if result.get("status") == "OK":
            s = result["summary"]
            print(
                f"  @1={s['option_top1']} @2={s['option_top2']} mrr={s['mrr2']} "
                f"(was {(s.get('baseline_without_bind') or {}).get('option_top1')}) "
                f"repaired_cases={s['n_cases_bind_repaired']}",
                flush=True,
            )
        else:
            print(f"  {result.get('status')}", flush=True)

    # TSV + MD
    lines = [
        "arm\tn\toption_top1\toption_top2\tmrr2\toption_top1_nobind\toption_top2_nobind\tmrr2_nobind\tn_bind_repaired\tpred_dir"
    ]
    md = [
        "# DiagnosisArena d2_seq100：基线 + synonym_bind mapper",
        "",
        "在已有 `typed_llm_disagreement_rag` 投影上离线施加 Approach A "
        "`synonym_bind_repair`（`min_score=0.70`，**pair_match_score 修后**；"
        "不再误用 syn:leaf 自 chunk=1.0），写入各臂 "
        "`mapper_synonym_bind/`，便于与本方法 **compat + synonym_bind** 对照。",
        "",
        "> 说明：基线仍是「合成 Top-2 叶 + typed map」；本方法是「树叶短列表 + "
        "compat rematch + bind」。协议仍有结构差，但 **同义修绑步骤已对齐**。"
        "2026-07-27 修复：桥接加分仅用 option↔leaf pair 分。",
        "",
        "| 臂 | n | @1 (bind) | @2 (bind) | MRR@2 | @1 (原) | @2 (原) | 修绑病例数 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    table_rows = []
    for r in rows:
        if r.get("status") != "OK":
            continue
        s = r["summary"]
        base = s.get("baseline_without_bind") or {}
        arm = Path(r["pred_dir"]).parent.name
        lines.append(
            "\t".join(
                [
                    arm,
                    str(s.get("n")),
                    str(s.get("option_top1")),
                    str(s.get("option_top2")),
                    str(s.get("mrr2")),
                    str(base.get("option_top1")),
                    str(base.get("option_top2")),
                    str(base.get("mrr2")),
                    str(s.get("n_cases_bind_repaired")),
                    r["pred_dir"],
                ]
            )
        )
        table_rows.append((arm, s, base, r["pred_dir"]))

    table_rows.sort(key=lambda x: (-(x[1].get("option_top1") or 0), x[0]))
    for arm, s, base, _ in table_rows:
        md.append(
            f"| `{arm}` | {s.get('n')} | **{s.get('option_top1')}** | {s.get('option_top2')} | "
            f"{s.get('mrr2')} | {base.get('option_top1')} | {base.get('option_top2')} | "
            f"{s.get('n_cases_bind_repaired')} |"
        )
    md += [
        "",
        "本方法锚点：`analysis/l1_recall_failure_v1/smoke_synonym_bind_live/` "
        "R_compat_synonym_bind_live **@1=0.81 / @2=0.93**。",
        "",
        f"TSV：[`{args.out_tsv.name}`]({args.out_tsv.name})",
        "",
    ]
    args.out_tsv.write_text("\n".join(lines) + "\n", encoding="utf-8")
    args.out_md.write_text("\n".join(md), encoding="utf-8")
    print("WROTE", args.out_tsv)
    print("WROTE", args.out_md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
