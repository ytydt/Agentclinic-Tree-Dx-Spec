#!/usr/bin/env python3
"""Run the lightweight diagnostic backbone (logs/backbone_v1/ only).

Examples:
  PYTHONPATH=src:scripts:scripts/paper python3 scripts/paper/run_backbone_v1.py \\
    --dataset diagnosisarena --arm v0_s4b_k5 --select b --max-k 5 --workers 25

  # Reuse S1-S3 from a prior arm, only re-run S4-c:
  ... --reuse-from logs/backbone_v1/diagnosisarena/v0_s4b_k5 --select c --arm v0_s4c_k5
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional

os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("MKL_NUM_THREADS", "2")
os.environ.setdefault("TREE_DX_EMBED_DEVICE", "cpu")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "paper"))

import baseline_common as bc  # noqa: E402
from agentclinic_tree_dx.backbone import BackbonePipeline, KBRecallBridge  # noqa: E402
from agentclinic_tree_dx.llm_client import RobustLLMClient  # noqa: E402

DEFAULT_MODEL = "meta-llama/llama-3.3-70b-instruct"
PIPELINE_TREES = {
    "diagnosisarena": ROOT / "logs/diagnosisarena_d2_m01_v1/c3_ab02_v1/annotate/shared_trees",
    "medcasereasoning": ROOT / "logs/medcasereasoning_mcr_val_seq100_v1/c3_ab02_v1/annotate/shared_trees",
    "medcasereasoning_v2": ROOT / "logs/medcasereasoning_mcr_val_seq100_v2/c3_ab02_v1/annotate/shared_trees",
}

OUT_ROOT = ROOT / "logs" / "backbone_v1"

SUBSETS = {
    "diagnosisarena": ROOT / "data/benchmarks/diagnosisarena/subsets/d2_seq100_v1",
    "diagnosisarena_heldout": ROOT
    / "data/benchmarks/diagnosisarena/subsets/d2_heldout100_v1",
    "diagnosisarena_heldout200b": ROOT
    / "data/benchmarks/diagnosisarena/subsets/d2_heldout200b_v1",
    "medcasereasoning": ROOT
    / "data/benchmarks/medcasereasoning/subsets/mcr_val_seq100_v1",
    "medcasereasoning_v2": ROOT
    / "data/benchmarks/medcasereasoning/subsets/mcr_val_seq100_v2",
    "medcasereasoning_200b": ROOT
    / "data/benchmarks/medcasereasoning/subsets/mcr_val_seq200b_v1",
}


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_json(path: Path, doc: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def _load_reuse(
    reuse_dir: Optional[Path],
    case_id: str,
    *,
    drop_s2: bool = False,
) -> dict[str, Any]:
    if reuse_dir is None:
        return {}
    path = reuse_dir / "case_stages" / f"{case_id}.json"
    if not path.is_file():
        return {}
    doc = json.loads(path.read_text(encoding="utf-8"))
    stages = dict(doc.get("stages") or {})
    # drop S4 so caller can re-run selection; keep S1-S3
    stages.pop("s4", None)
    stages.pop("s4_variant", None)
    if drop_s2:
        stages.pop("s2", None)
    return stages


def _run_one(
    case: Mapping[str, Any],
    *,
    pipe: BackbonePipeline,
    arm: str,
    reuse_dir: Optional[Path],
    out_dir: Path,
    force_s3: bool,
    drop_s2: bool = False,
) -> dict[str, Any]:
    cid = str(case["case_id"])
    source_id = str(case.get("source_id") or cid)
    stage_path = out_dir / "case_stages" / f"{source_id}.json"
    if stage_path.is_file() and not force_s3:
        # resume: already completed
        prior = json.loads(stage_path.read_text(encoding="utf-8"))
        return prior.get("prediction") or {
            "arm": arm,
            "case_id": cid,
            "source_id": source_id,
            "ordered_diagnoses": [prior.get("champion")] if prior.get("champion") else [],
            "top2_diagnoses": [prior.get("champion")] if prior.get("champion") else [],
            "cost": {"llm_calls": 0},
        }

    reuse = _load_reuse(reuse_dir, source_id, drop_s2=drop_s2)
    if not reuse:
        reuse = _load_reuse(reuse_dir, cid, drop_s2=drop_s2)
    if force_s3:
        reuse.pop("s3", None)
        reuse.pop("s3_max_k", None)

    t0 = time.time()
    result = pipe.run(
        case_id=cid,
        vignette=str(case["vignette"]),
        question=str(case.get("question") or "What is the most likely diagnosis?"),
        reuse_stages=reuse or None,
    )
    pred = result.as_prediction(
        arm=arm,
        source_id=source_id,
        dataset=str(case.get("dataset") or ""),
    )
    pred["runtime_hash"] = case.get("runtime_hash")
    pred["wall_s"] = round(time.time() - t0, 3)
    doc = {
        "case_id": cid,
        "source_id": source_id,
        "champion": result.champion,
        "ordered_diagnoses": result.ordered_diagnoses,
        "llm_calls": result.llm_calls,
        "stages": result.stages,
        "config": result.config,
        "prediction": pred,
        "created_at": _utc(),
    }
    _atomic_json(stage_path, doc)
    return pred


def run_arm(
    *,
    dataset_key: str,
    arm: str,
    select: str,
    max_k: int,
    entrance: str,
    model: str,
    workers: int,
    limit: int,
    reuse_from: Optional[Path],
    force_s3: bool,
    dry_run: bool,
    case_ids: list[str],
    drop_s2: bool = False,
    s2_k: int = 1,
    s2_mode: str = "complement",
    skip_s1: bool = False,
    s3_strict: bool = False,
    s4_facts: int = 4,
    s4_fact_source: str = "salient_then_key",
    context_source: str = "body",
    keep_s2: bool = False,
) -> Path:
    if dataset_key in (
        "medcasereasoning_v2",
        "medcasereasoning_200b",
        "mcr",
        "medcasereasoning",
    ):
        key = (
            "medcasereasoning"
            if dataset_key == "mcr"
            else (
                dataset_key
                if dataset_key.startswith("medcasereasoning")
                else "medcasereasoning"
            )
        )
        subset = SUBSETS[key]
        ds_name = "medcasereasoning"
        out_ds = key
    elif dataset_key in ("diagnosisarena_heldout", "diagnosisarena_heldout200b"):
        subset = SUBSETS[dataset_key]
        ds_name = "diagnosisarena"
        out_ds = dataset_key
    else:
        subset = SUBSETS["diagnosisarena"]
        ds_name = "diagnosisarena"
        out_ds = "diagnosisarena"

    out_dir = OUT_ROOT / out_ds / arm
    out_dir.mkdir(parents=True, exist_ok=True)
    cache_path = out_dir / "cache" / "backbone_llm.json"

    cases = bc.load_runtime_cases(
        dataset=ds_name,
        subset_dir=subset,
        case_ids=case_ids,
        limit=int(limit or 0),
    )
    if context_source == "pipeline_summary":
        # Same input the M00 / AB02 arms actually receive: env.get_case_summary()
        # = vignette + Question + Options. Used only to quantify the leak.
        trees = PIPELINE_TREES.get(out_ds)
        if trees is None or not trees.is_dir():
            raise SystemExit(f"no pipeline trees for {out_ds}")
        n_sub = 0
        for case in cases:
            f = trees / f"{case['source_id']}.json"
            if f.is_file():
                cs = str((json.loads(f.read_text(encoding="utf-8")).get("state") or {}).get("case_summary") or "")
                if cs:
                    case["vignette"] = cs
                    n_sub += 1
        print(f"  [leak probe] substituted pipeline case_summary for {n_sub}/{len(cases)} cases", flush=True)

    client = None
    if not dry_run:
        client = RobustLLMClient(
            model=model,
            call_timeout=240,
            max_retries=5,
            timeout_retry_cap=2,
            temperature=0.0,
        )
    cached = bc.SimpleCachedLLM(client, cache_path, model)

    kb = None
    if entrance == "kb_only":
        kb = KBRecallBridge(ROOT)
        kb.ensure()
        drop_s2 = True

    # Historically s2_k>1 always dropped reused S2 (to avoid mismatched width).
    # R4 interventions freeze S1–S3 via --reuse-from and need --keep-s2.
    if skip_s1:
        drop_s2 = True
    elif s2_k > 1 and not keep_s2:
        drop_s2 = True

    pipe = BackbonePipeline(
        cached,
        select_variant=select,
        max_k=max_k,
        entrance=entrance,
        kb_retriever=kb,
        s2_k=s2_k,
        s2_mode=s2_mode,
        skip_s1=skip_s1,
        s3_strict=s3_strict,
        s4_facts=s4_facts,
        s4_fact_source=s4_fact_source,
    )

    manifest = {
        "arm": arm,
        "dataset": out_ds,
        "subset": str(subset),
        "model": model,
        "select_variant": select,
        "max_k": max_k,
        "entrance": entrance,
        "s2_k": s2_k,
        "s2_mode": s2_mode,
        "skip_s1": skip_s1,
        "s3_strict": s3_strict,
        "context_source": context_source,
        "reuse_from": str(reuse_from) if reuse_from else None,
        "n_cases": len(cases),
        "workers": workers,
        "created_at": _utc(),
        "schema_version": "backbone_v1",
    }
    _atomic_json(out_dir / "manifest.json", manifest)

    preds: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    def _task(case: Mapping[str, Any]) -> dict[str, Any]:
        return _run_one(
            case,
            pipe=pipe,
            arm=arm,
            reuse_dir=reuse_from,
            out_dir=out_dir,
            force_s3=force_s3,
            drop_s2=drop_s2,
        )

    if workers <= 1:
        for case in cases:
            try:
                preds.append(_task(case))
                print(
                    f"  [{len(preds)}/{len(cases)}] {case['case_id']} "
                    f"-> {(preds[-1].get('ordered_diagnoses') or [''])[0][:60]}",
                    flush=True,
                )
            except Exception as exc:
                errors.append({
                    "case_id": case["case_id"],
                    "error": f"{type(exc).__name__}: {exc}",
                    "trace": traceback.format_exc(),
                })
                print(f"  ERROR {case['case_id']}: {exc}", flush=True)
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = {pool.submit(_task, c): c for c in cases}
            done = 0
            for fut in as_completed(futs):
                case = futs[fut]
                done += 1
                try:
                    pred = fut.result()
                    preds.append(pred)
                    print(
                        f"  [{done}/{len(cases)}] {case['case_id']} "
                        f"-> {(pred.get('ordered_diagnoses') or [''])[0][:60]}",
                        flush=True,
                    )
                except Exception as exc:
                    errors.append({
                        "case_id": case["case_id"],
                        "error": f"{type(exc).__name__}: {exc}",
                        "trace": traceback.format_exc(),
                    })
                    print(f"  ERROR {case['case_id']}: {exc}", flush=True)

    preds.sort(key=lambda r: str(r.get("source_id") or r.get("case_id")))
    pred_path = out_dir / "predictions.jsonl"
    pred_path.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in preds),
        encoding="utf-8",
    )
    total_calls = sum(int((r.get("cost") or {}).get("llm_calls") or 0) for r in preds)
    summary = {
        "arm": arm,
        "dataset": out_ds,
        "n_predictions": len(preds),
        "n_errors": len(errors),
        "llm_calls_total": total_calls,
        "llm_calls_mean": round(total_calls / max(1, len(preds)), 2),
        "cache_new_calls": getattr(cached, "calls", 0),
        "select_variant": select,
        "max_k": max_k,
        "entrance": entrance,
        "errors": errors,
        "finished_at": _utc(),
    }
    _atomic_json(out_dir / "summary.json", summary)
    print(json.dumps(summary, indent=2, ensure_ascii=False), flush=True)
    return out_dir


def score_da(pred_dir: Path, subset: Path, model: str) -> dict[str, Any]:
    import baseline_mapper_score as mapper_score

    cases = bc.load_runtime_cases(dataset="diagnosisarena", subset_dir=subset)
    # lexical quick score without mapper LLM: use leaf_match against gold text
    sys.path.insert(0, str(ROOT / "scripts" / "paper"))
    from mapper_bind_repair import leaf_match_score

    rows = [
        json.loads(line)
        for line in (pred_dir / "predictions.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    by_src = {str(c["source_id"]): c for c in cases}
    lex_hits = 0
    n = 0
    for r in rows:
        c = by_src.get(str(r.get("source_id")))
        if c is None:
            continue
        gold = str(c.get("_gold_text") or "")
        pred = (r.get("ordered_diagnoses") or [""])[0]
        n += 1
        if gold and pred and leaf_match_score(gold, pred) >= 0.7:
            lex_hits += 1
    lex = {
        "n": n,
        "lexical_top1": round(lex_hits / max(1, n), 4),
        "criterion": "leaf_match_score(gold, pred)>=0.7",
    }
    _atomic_json(pred_dir / "lexical_score.json", lex)

    scored = mapper_score.score_predictions_dir(
        pred_dir,
        cases,
        mode="typed_llm_disagreement_rag",
        model=model,
        dry_run=False,
    )
    _atomic_json(pred_dir / "mapper" / "summary.json", scored)
    print(
        f"[DA score] lexical={lex['lexical_top1']} "
        f"option@1={scored.get('option_top1')}",
        flush=True,
    )
    return {"lexical": lex, "mapper": scored}


def score_mcr(pred_dir: Path, subset_parquet: Path, workers: int = 25) -> dict[str, Any]:
    from build_baseline_eval_projection import build_baseline_eval_projections
    from run_ox_mcr_official_eval import run_eval
    from transfer_eval import judges

    build_baseline_eval_projections(
        pred_dir,
        dataset="medcasereasoning",
        list_k=2,
        resume=True,
    )
    summary = run_eval(
        dataset="medcasereasoning",
        run_dir=pred_dir,
        subset_parquet=subset_parquet,
        judge_kind="llm",
        build_projection=False,
        resume_scores=True,
        skip_reasoning_recall=True,
        workers=workers or int(judges.JUDGE_WORKERS),
        out_name="official_eval_llm",
    )
    _atomic_json(pred_dir / "mcr_eval_summary.json", summary)
    acc = (summary.get("metrics") or {}).get("diagnostic_accuracy_single_trajectory")
    if acc is None:
        acc = summary.get("diagnostic_accuracy_single_trajectory")
    print(f"[MCR score] Acc@1={acc}", flush=True)
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--dataset",
        default="diagnosisarena",
        choices=(
            "diagnosisarena",
            "diagnosisarena_heldout",
            "diagnosisarena_heldout200b",
            "medcasereasoning",
            "mcr",
            "medcasereasoning_v2",
            "medcasereasoning_200b",
        ),
    )
    ap.add_argument("--arm", required=True)
    ap.add_argument("--select", default="b", choices=("a", "b", "c", "d", "e", "f", "g", "h"))
    ap.add_argument(
        "--s4-facts",
        type=int,
        default=4,
        help="number of facts for the sequential evidence update (select e/f)",
    )
    ap.add_argument(
        "--s4-fact-source",
        default="salient_then_key",
        choices=("salient_then_key", "key", "atomised"),
    )
    ap.add_argument(
        "--context-source",
        default="body",
        choices=("body", "pipeline_summary"),
        help="pipeline_summary replays the MCQ-option leak present in M00/AB02",
    )
    ap.add_argument("--max-k", type=int, default=5)
    ap.add_argument("--entrance", default="llm_ddx", choices=("llm_ddx", "kb_only"))
    ap.add_argument("--s2-k", type=int, default=1, help="number of S2 DDx calls")
    ap.add_argument(
        "--s2-mode",
        default="complement",
        choices=("single", "complement", "partition"),
        help="how calls 2..k of S2 are conditioned",
    )
    ap.add_argument("--skip-s1", action="store_true", help="drop the parse call")
    ap.add_argument(
        "--s3-strict",
        action="store_true",
        help="S3 must return indices into the pool (no renaming/invention)",
    )
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--workers", type=int, default=25)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--case-id", action="append", default=[])
    ap.add_argument("--reuse-from", type=Path, default=None)
    ap.add_argument(
        "--force-s3",
        action="store_true",
        help="ignore cached S3 even when --reuse-from is set (for k ablation)",
    )
    ap.add_argument(
        "--keep-s2",
        action="store_true",
        help="keep reused S2 even when --s2-k > 1 (R4 freeze S1-S3)",
    )
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--score", action="store_true")
    ap.add_argument("--score-only", action="store_true")
    ap.add_argument("--mcr-judge-workers", type=int, default=25)
    args = ap.parse_args()

    ds_key = args.dataset
    if ds_key == "mcr":
        ds_key = "medcasereasoning"

    if args.score_only:
        if ds_key.startswith("medcasereasoning"):
            out_ds = ds_key
        elif ds_key.startswith("diagnosisarena_heldout"):
            out_ds = ds_key
        elif ds_key == "medcasereasoning" or ds_key == "mcr":
            out_ds = "medcasereasoning"
        else:
            out_ds = "diagnosisarena"
        pred_dir = OUT_ROOT / out_ds / args.arm
        if out_ds.startswith("medcasereasoning"):
            score_mcr(
                pred_dir,
                SUBSETS[out_ds] / "cases.parquet",
                workers=args.mcr_judge_workers,
            )
        else:
            score_da(
                pred_dir,
                SUBSETS[
                    out_ds
                    if out_ds.startswith("diagnosisarena_heldout")
                    else "diagnosisarena"
                ],
                args.model,
            )
        return 0

    out_dir = run_arm(
        dataset_key=ds_key,
        arm=args.arm,
        select=args.select,
        max_k=args.max_k,
        entrance=args.entrance,
        model=args.model,
        workers=args.workers,
        limit=args.limit,
        reuse_from=args.reuse_from,
        force_s3=args.force_s3,
        dry_run=args.dry_run,
        case_ids=list(args.case_id or []),
        s2_k=args.s2_k,
        s2_mode=args.s2_mode,
        skip_s1=args.skip_s1,
        s3_strict=args.s3_strict,
        s4_facts=args.s4_facts,
        s4_fact_source=args.s4_fact_source,
        context_source=args.context_source,
        keep_s2=args.keep_s2,
    )

    if args.score and not args.dry_run:
        if ds_key.startswith("medcasereasoning"):
            score_mcr(
                out_dir,
                SUBSETS[ds_key] / "cases.parquet",
                workers=args.mcr_judge_workers,
            )
        else:
            score_da(out_dir, SUBSETS[ds_key], args.model)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
