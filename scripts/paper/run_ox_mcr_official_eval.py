#!/usr/bin/env python3
"""Run OX / MCR official-style metrics on an existing transfer run.

Default ``--judge lexical`` → protocol ``compatible_metrics_lexical_v1``
(not paper-official). ``--judge llm`` → ``paper_aligned_judge_v1`` with
Gemini 2.5 Flash (requires conda ``gnn-llm`` + ``clashon``; default
``--workers 50`` per JUDGE_MODEL_CONTRACT).
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
_PAPER = ROOT / "scripts" / "paper"
sys.path.insert(0, str(_PAPER))
sys.path.insert(0, str(ROOT / "src"))

from build_eval_projection import (  # noqa: E402
    ALL_DDX_SOURCES,
    DEFAULT_DDX_K,
    DEFAULT_POST_N_MCR_POOL,
    DDX_SOURCE_CALIB_ONLY_POST,
    DDX_SOURCE_CLOSED_MAC_TRACE_RRF,
    DDX_SOURCE_CLOSED_LIVE_MAC,
    DDX_SOURCE_CLOSED_POOL_RRF,
    DDX_SOURCE_COMPAT,
    DDX_SOURCE_COMPAT_THEN_PAD,
    DDX_SOURCE_GATE_ON_POST,
    DDX_SOURCE_GATED_HYBRID,
    DDX_SOURCE_GATED_HYBRID_COMPAT,
    DDX_SOURCE_GATED_HYBRID_MCR,
    DDX_SOURCE_L1_TOP2_COMPAT,
    DDX_SOURCE_MULTI_ARM_RRF,
    DDX_SOURCE_POST_N_MCR,
    DDX_SOURCE_POSTERIOR,
    DDX_SOURCE_TREE_MAC_PAD,
    DDX_SOURCE_TREE_MAC_PAD_SELECTIVE,
    _auto_proj_subdir,
    build_eval_projections,
    normalize_ddx_source,
    resolve_annotate_dir,
)
from transfer_eval import io_gold, judges, mcr_metrics, ox_metrics  # noqa: E402


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, doc: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _case_ids_from_projections(proj_dir: Path) -> list[str]:
    return sorted(
        p.stem
        for p in proj_dir.glob("*.json")
        if p.is_file() and not p.name.startswith("_")
    )


def _eval_outdir_name(judge_kind: str, override: str = "") -> str:
    if override:
        return override.strip().strip("/")
    return "official_eval_llm" if judge_kind == "llm" else "official_eval"


def _render_summary_md(summary: Mapping[str, Any]) -> str:
    lines = [
        "# OX/MCR official-style eval summary",
        "",
        "- protocol: `%s`" % summary.get("protocol"),
        "- dataset: `%s`" % summary.get("dataset"),
        "- judge: `%s`" % summary.get("judge"),
        "- ddx_k: `%s`" % summary.get("ddx_k"),
        "",
    ]
    metrics = summary.get("metrics") or {}
    if summary.get("dataset_family") == "open_xddx":
        micro = metrics.get("diagnostic_micro") or {}
        macro = metrics.get("diagnostic_macro") or {}
        lines += [
            "## Diagnostic (must report P/R/F1 separately)",
            "",
            "| agg | precision | recall | f1 |",
            "|-----|-----------|--------|-----|",
            "| micro | %.4f | %.4f | %.4f |" % (
                float(micro.get("micro_precision") or 0),
                float(micro.get("micro_recall") or 0),
                float(micro.get("micro_f1") or 0),
            ),
            "| macro | %.4f | %.4f | %.4f |" % (
                float(macro.get("precision") or 0),
                float(macro.get("recall") or 0),
                float(macro.get("f1") or 0),
            ),
            "",
            "- correct/total_pred (micro P): %.4f" % float(
                micro.get("correct_over_total_pred") or 0
            ),
            "- correct/total_gold (micro R): %.4f" % float(
                micro.get("correct_over_total_gold") or 0
            ),
            "- interpretation_accuracy: %.4f" % float(
                metrics.get("interpretation_accuracy") or 0
            ),
            "",
        ]
    else:
        lines += [
            "## MedCaseReasoning (single trajectory)",
            "",
            "- diagnostic_accuracy_single_trajectory: %.4f" % float(
                metrics.get("diagnostic_accuracy_single_trajectory") or 0
            ),
            "- reasoning_recall_mean: %.4f" % float(
                metrics.get("reasoning_recall_mean") or 0
            ),
            "- sampling_protocol: `%s`" % metrics.get("sampling_protocol"),
            "",
            str(metrics.get("note") or ""),
            "",
        ]
    lines += [
        "## Boundaries",
        "",
    ]
    for b in summary.get("boundaries") or []:
        lines.append("- %s" % b)
    lines.append("")
    return "\n".join(lines)


def _dataset_family(dataset: str) -> str:
    ds = dataset.strip().lower()
    if ds in {"open_xddx", "ox", "open-xddx"}:
        return "open_xddx"
    if ds in {"medcasereasoning", "mcr", "medcase"}:
        return "medcasereasoning"
    if ds in {"rarearena", "ra", "rare_arena", "ra_rdc"}:
        return "rarearena"
    raise ValueError("unknown --dataset: %s" % dataset)


def _projection_subdir(
    ddx_source: str,
    override: str = "",
    *,
    pool_n: int = DEFAULT_POST_N_MCR_POOL,
) -> str:
    if override:
        return override.strip().strip("/")
    src = normalize_ddx_source(ddx_source)
    if src == DDX_SOURCE_POST_N_MCR:
        if int(pool_n) == DEFAULT_POST_N_MCR_POOL:
            return "eval_projection_post7_mcr"
        return "eval_projection_post%d_mcr" % int(pool_n)
    return _auto_proj_subdir(src)


def _load_mac_pred_by_cid(path: Path | None) -> dict[str, list[str]]:
    if path is None or not Path(path).is_file():
        return {}
    import re as _re

    out: dict[str, list[str]] = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        m = _re.search(r"(\d+)$", str(row.get("case_id") or ""))
        cid = str(int(m.group(1))) if m else str(row.get("case_id") or "")
        out[cid] = list(row.get("ordered_diagnoses") or [])
    return out


def _load_mac_doctors_by_cid(
    path: Path | None,
) -> dict[str, list[list[str]]]:
    if path is None or not Path(path).is_file():
        return {}
    import re as _re

    out: dict[str, list[list[str]]] = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        m = _re.search(r"(\d+)$", str(row.get("case_id") or ""))
        cid = str(int(m.group(1))) if m else str(row.get("case_id") or "")
        disc = (
            ((row.get("trace") or {}) if isinstance(row.get("trace"), Mapping) else {})
            .get("discussion")
            or []
        )
        lists: list[list[str]] = []
        for turn in disc:
            if not isinstance(turn, Mapping):
                continue
            ranked = turn.get("ranked_diagnoses") or []
            if isinstance(ranked, list) and ranked:
                lists.append([str(x) for x in ranked])
        if lists:
            out[cid] = lists
    return out


def run_eval(
    *,
    dataset: str,
    run_dir: Path,
    subset_parquet: Path,
    judge_kind: str = "lexical",
    ddx_k: int = DEFAULT_DDX_K,
    build_projection: bool = False,
    resume_projection: bool = False,
    nlg_metrics: bool = False,
    case_ids: Sequence[str] = (),
    write_md: bool = True,
    workers: int = 1,
    out_name: str = "",
    resume_scores: bool = False,
    skip_reasoning_recall: bool = False,
    ddx_source: str = DDX_SOURCE_POSTERIOR,
    projection_subdir: str = "",
    dry_calib: bool = True,
    pool_n: int = DEFAULT_POST_N_MCR_POOL,
    mac_predictions: Path | None = None,
    mac_trace: Path | None = None,
    live_closed_mac: bool = False,
    judge_model: str | None = None,
) -> dict[str, Any]:
    family = _dataset_family(dataset)
    annotate = resolve_annotate_dir(run_dir)
    src = normalize_ddx_source(ddx_source)
    proj_sub = _projection_subdir(src, projection_subdir, pool_n=pool_n)
    mac_map = _load_mac_pred_by_cid(mac_predictions)
    mac_docs = _load_mac_doctors_by_cid(mac_trace)
    judge_model_slug = str(judge_model or judges.JUDGE_MODEL_SLUG).strip() or judges.JUDGE_MODEL_SLUG
    judge_model_short = judge_model_slug.rsplit("/", 1)[-1]
    if build_projection:
        trees = annotate / "shared_trees"
        if not trees.is_dir() and not (run_dir / "shared_trees").is_dir():
            raise FileNotFoundError(
                "--build-projection requires shared_trees (tree-system run). "
                "For baseline predictions.jsonl use "
                "scripts/paper/run_baseline_ox_mcr_eval.py / "
                "build_baseline_eval_projection.py instead."
            )
        if src == DDX_SOURCE_TREE_MAC_PAD and not mac_map:
            raise ValueError(
                "tree_mac_pad requires --mac-predictions pointing to "
                "B06 predictions.jsonl"
            )
        if src == DDX_SOURCE_TREE_MAC_PAD_SELECTIVE and not mac_map:
            raise ValueError(
                "tree_mac_pad_selective requires --mac-predictions"
            )
        if src == DDX_SOURCE_CLOSED_MAC_TRACE_RRF and not mac_docs:
            raise ValueError(
                "closed_mac_trace_rrf requires --mac-trace pointing to "
                "B06 trace.jsonl"
            )
        if src == DDX_SOURCE_CLOSED_LIVE_MAC and not live_closed_mac:
            raise ValueError(
                "closed_live_mac_supervisor requires --live-closed-mac "
                "(otherwise dry fallback is not a fair score)"
            )
        build_eval_projections(
            run_dir,
            ddx_k=ddx_k,
            case_ids=case_ids,
            resume=resume_projection,
            ddx_source=src,
            out_subdir=proj_sub,
            dry_calib=dry_calib,
            pool_n=pool_n,
            mac_pred_by_cid=mac_map,
            mac_doctors_by_cid=mac_docs,
            live_closed_mac=live_closed_mac,
        )
    proj_dir = annotate / proj_sub
    if not proj_dir.is_dir():
        raise FileNotFoundError(
            "missing %s — pass --build-projection" % proj_dir
        )

    ids = list(case_ids) if case_ids else _case_ids_from_projections(proj_dir)
    gold_map = io_gold.load_gold(family, subset_parquet, case_ids=ids)

    # Default out dir tags non-posterior sources
    default_out = out_name
    if not default_out:
        tag = {
            DDX_SOURCE_POSTERIOR: "",
            DDX_SOURCE_COMPAT: "_compat",
            DDX_SOURCE_COMPAT_THEN_PAD: "_compat_then_pad",
            DDX_SOURCE_GATE_ON_POST: "_gate_on_post",
            DDX_SOURCE_CALIB_ONLY_POST: "_calib_only_post",
            DDX_SOURCE_L1_TOP2_COMPAT: "_l1_top2_compat",
            DDX_SOURCE_GATED_HYBRID: "_gated_hybrid_top2",
            DDX_SOURCE_GATED_HYBRID_COMPAT: "_gated_hybrid_top2_compat",
            DDX_SOURCE_GATED_HYBRID_MCR: "_gated_hybrid_top2_mcr",
            DDX_SOURCE_POST_N_MCR: (
                "_post7_mcr"
                if int(pool_n) == DEFAULT_POST_N_MCR_POOL
                else "_post%d_mcr" % int(pool_n)
            ),
            DDX_SOURCE_MULTI_ARM_RRF: "_multi_arm_rrf",
            DDX_SOURCE_CLOSED_POOL_RRF: "_closed_pool_rrf",
            DDX_SOURCE_CLOSED_MAC_TRACE_RRF: "_closed_mac_trace_rrf",
            DDX_SOURCE_CLOSED_LIVE_MAC: "_closed_live_mac",
            DDX_SOURCE_TREE_MAC_PAD: "_tree_mac_pad",
            DDX_SOURCE_TREE_MAC_PAD_SELECTIVE: "_tree_mac_pad_selective",
        }.get(src, "_%s" % src.replace("/", "_")[:32])
        if judge_kind == "llm":
            default_out = "official_eval_llm%s" % tag
        else:
            default_out = "official_eval%s" % tag

    eval_dir = annotate / _eval_outdir_name(judge_kind, default_out)
    scores_dir = eval_dir / "case_scores"
    scores_dir.mkdir(parents=True, exist_ok=True)
    cache_path = eval_dir / "judge_cache.json"
    # Seed from previous posterior LLM cache when present (Prompt7 reuse)
    seed = annotate / "official_eval_llm" / "judge_cache.json"
    if (
        judge_kind == "llm"
        and seed.is_file()
        and (not cache_path.is_file() or cache_path.stat().st_size < 10)
    ):
        cache_path.write_text(seed.read_text(encoding="utf-8"), encoding="utf-8")
    cache = (
        judges.JudgeCache(cache_path, flush_every=25)
        if judge_kind == "llm"
        else None
    )

    # RobustLLMClient is not guaranteed thread-safe — one client per worker thread.
    _tls = threading.local()

    def _thread_judge() -> Any:
        if judge_kind != "llm":
            return judges.LexicalJudge()
        client = getattr(_tls, "client", None)
        if client is None:
            from agentclinic_tree_dx.llm_client import RobustLLMClient

            client = RobustLLMClient(
                model=judge_model_slug,
                temperature=0.0,
            )
            _tls.client = client
        return judges.LLMJudge(client=client, cache=cache, model=judge_model_slug)

    jobs: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
    missing_gold: list[str] = []
    case_scores: list[dict[str, Any]] = []
    resumed = 0
    for cid in ids:
        proj_path = proj_dir / ("%s.json" % cid)
        if not proj_path.is_file():
            continue
        score_path = scores_dir / ("%s.json" % cid)
        if resume_scores and score_path.is_file():
            try:
                sc = _read_json(score_path)
                if isinstance(sc, Mapping) and "case_id" in sc:
                    case_scores.append(dict(sc))
                    resumed += 1
                    continue
            except Exception:  # noqa: BLE001
                pass
        gold = gold_map.get(str(cid))
        if gold is None:
            missing_gold.append(str(cid))
            continue
        proj = _read_json(proj_path)
        jobs.append((str(cid), proj, gold))

    errors: list[dict[str, str]] = []
    n_workers = max(1, int(workers))
    progress_lock = threading.Lock()
    done = [0]

    def _score_one(cid: str, proj: dict[str, Any], gold: dict[str, Any]) -> dict[str, Any]:
        judge = _thread_judge()
        if family == "open_xddx":
            sc = ox_metrics.score_ox_case(
                proj, gold, judge, nlg_metrics=nlg_metrics
            )
        else:
            if skip_reasoning_recall and isinstance(judge, judges.LLMJudge):
                # Fast path: Prompt 7 only
                pred_dx = str(proj.get("pred_diagnosis") or "").strip()
                if not pred_dx:
                    ddx = proj.get("pred_ddx") or []
                    if ddx and isinstance(ddx[0], Mapping):
                        pred_dx = str(ddx[0].get("label") or "").strip()
                gold_dx = str(gold.get("final_diagnosis") or "").strip()
                hit = (
                    judge.mcr_diagnosis_correct(pred_dx, gold_dx)
                    if pred_dx and gold_dx
                    else False
                )
                sc = {
                    "case_id": cid,
                    "pred_diagnosis": pred_dx,
                    "gold_diagnosis": gold_dx,
                    "diagnostic_hit": bool(hit),
                    "reasoning_recall": None,
                    "n_reasoning_points": len(gold.get("reasoning_points") or []),
                    "n_reasoning_points_covered": None,
                    "point_hits": [],
                    "matching_dict": {},
                    "skipped_reasoning_recall": True,
                }
            else:
                sc = mcr_metrics.score_mcr_case(proj, gold, judge)
        _write_json(scores_dir / ("%s.json" % cid), sc)
        with progress_lock:
            done[0] += 1
            if done[0] % 10 == 0 or done[0] == len(jobs):
                print(
                    "[official_eval] scored %d/%d" % (done[0], len(jobs)),
                    flush=True,
                )
        return sc

    if n_workers == 1 or not jobs:
        for cid, proj, gold in jobs:
            try:
                case_scores.append(_score_one(cid, proj, gold))
            except Exception as exc:  # noqa: BLE001
                errors.append({
                    "case_id": cid,
                    "error": "%s: %s" % (type(exc).__name__, exc),
                    "traceback": traceback.format_exc()[-800:],
                })
    else:
        with ThreadPoolExecutor(max_workers=n_workers) as pool:
            futs = {
                pool.submit(_score_one, cid, proj, gold): cid
                for cid, proj, gold in jobs
            }
            for fut in as_completed(futs):
                cid = futs[fut]
                try:
                    case_scores.append(fut.result())
                except Exception as exc:  # noqa: BLE001
                    errors.append({
                        "case_id": cid,
                        "error": "%s: %s" % (type(exc).__name__, exc),
                        "traceback": traceback.format_exc()[-800:],
                    })

    if cache is not None:
        cache.flush()

    # Stable order by case_id
    case_scores.sort(key=lambda r: int(str(r.get("case_id") or "0") or 0))

    if family == "open_xddx":
        metrics = ox_metrics.aggregate_ox_scores(case_scores)
        protocol_judge = judges.LexicalJudge() if judge_kind == "lexical" else judges.LLMJudge(client=None, cache=cache)
    else:
        # If reasoning recall skipped, aggregate Acc only
        if skip_reasoning_recall:
            n = len(case_scores)
            hits = sum(1 for c in case_scores if c.get("diagnostic_hit"))
            metrics = {
                "n_cases": n,
                "diagnostic_accuracy_single_trajectory": (hits / n) if n else 0.0,
                "n_diagnostic_hits": hits,
                "reasoning_recall_mean": None,
                "sampling_protocol": "single_trajectory_v1",
                "skipped_reasoning_recall": True,
                "note": (
                    "Fast official Acc only (Prompt 7). Reasoning Recall not run."
                ),
            }
        else:
            metrics = mcr_metrics.aggregate_mcr_scores(case_scores)
        protocol_judge = judges.LexicalJudge() if judge_kind == "lexical" else judges.LLMJudge(client=None, cache=cache)

    protocol = getattr(protocol_judge, "protocol", "unknown")
    summary: dict[str, Any] = {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "dataset": dataset,
        "dataset_family": family,
        "run_dir": str(Path(run_dir).resolve()),
        "annotate_dir": str(annotate.resolve()),
        "subset_parquet": str(Path(subset_parquet).resolve()),
        "protocol": protocol,
        "judge": judge_kind,
        "ddx_k": int(ddx_k),
        "ddx_source": src,
        "pool_n": int(pool_n) if src == DDX_SOURCE_POST_N_MCR else None,
        "projection_subdir": proj_sub,
        "workers": n_workers,
        "n_cases_scored": len(case_scores),
        "n_resumed_scores": resumed,
        "n_errors": len(errors),
        "errors": errors[:20],
        "missing_gold": missing_gold,
        "metrics": metrics,
        "boundaries": [
            "Not proxy MCQ / mapper option_top1; do not mix into rematch tables.",
            (
                "pred_ddx from compat_parallel l2.final_ranking (post-merge/calib)."
                if src == DDX_SOURCE_COMPAT
                else "pred_ddx from shared_trees global leaf posterior Top-K (not L1 axes)."
            ),
            "Reasoning/interpretation templates use P5 why + selected facts only (no KB chunks).",
        ],
    }
    if judge_kind == "lexical":
        summary["boundaries"].append(
            "protocol compatible_metrics_lexical_v1 is NOT paper-official; "
            "use --judge llm for paper_aligned_judge_v1."
        )
    else:
        summary["judge_model"] = judge_model_short
        summary["judge_model_slug"] = judge_model_slug
        summary["judge_env"] = judges.JUDGE_ENV
        summary["vpn"] = judges.JUDGE_VPN
        summary["boundaries"].append(
            "LLM judge model substituted: Gemini 2.5 Flash replaces "
            "paper gpt-4o-mini / o4-mini / Dual-Inf GPT-4o; prompts unchanged."
        )
        if family == "medcasereasoning":
            summary["boundaries"].append(
                "diagnostic_accuracy_single_trajectory ≠ official 10-shot Acc."
            )

    out_json = eval_dir / "summary.json"
    _write_json(out_json, summary)
    if write_md:
        md_path = eval_dir / "summary.md"
        md_path.write_text(_render_summary_md(summary), encoding="utf-8")
    summary["_paths"] = {
        "summary_json": str(out_json),
        "case_scores_dir": str(scores_dir),
        "eval_dir": str(eval_dir),
    }
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--dataset",
        required=True,
        choices=["open_xddx", "medcasereasoning", "rarearena", "ox", "mcr", "ra"],
    )
    ap.add_argument("--run-dir", type=Path, required=True)
    ap.add_argument("--subset-parquet", type=Path, required=True)
    ap.add_argument("--judge", choices=["lexical", "llm"], default="lexical")
    ap.add_argument("--ddx-k", type=int, default=DEFAULT_DDX_K)
    ap.add_argument("--build-projection", action="store_true")
    ap.add_argument("--resume", action="store_true", help="resume projection build")
    ap.add_argument(
        "--resume-scores",
        action="store_true",
        help="skip cases that already have case_scores/{id}.json",
    )
    ap.add_argument("--nlg-metrics", action="store_true")
    ap.add_argument("--case-id", action="append", default=[])
    ap.add_argument("--no-md", action="store_true")
    ap.add_argument(
        "--workers",
        type=int,
        default=0,
        help=(
            "parallel case scorers (one RobustLLMClient per thread). "
            "0 = contract default: 50 for --judge llm, 1 for lexical "
            "(see analysis/transfer_metrics_v1/judge_prompts/JUDGE_MODEL_CONTRACT.md)"
        ),
    )
    ap.add_argument(
        "--judge-model",
        default="",
        help=(
            "Override LLM judge model slug (default: google/gemini-2.5-flash). "
            "T1-11 second judge: deepseek/deepseek-v4-flash. Always use a "
            "distinct --out-name so caches do not share a directory."
        ),
    )
    ap.add_argument(
        "--out-name",
        default="",
        help="annotate subdir name (default: official_eval or official_eval_llm)",
    )
    ap.add_argument(
        "--skip-reasoning-recall",
        action="store_true",
        help="MCR fast path: Prompt 7 Acc only (skip Prompt 5 Reasoning Recall)",
    )
    ap.add_argument(
        "--ddx-source",
        default=DDX_SOURCE_POSTERIOR,
        choices=list(ALL_DDX_SOURCES) + [
            "compat",
            "compat_final_ranking",
            "final_ranking",
            "posterior",
            "compat_then_pad",
            "gate_on_post",
            "calib_only_post",
            "l1_top2_compat",
            "l1_top2",
            "per_l1_top2_compat",
            "gated_hybrid",
            "gated_hybrid_top2",
            "gated_top2",
            "gated_hybrid_compat",
            "gated_hybrid_top2_compat",
            "gated_top2_compat",
            "gated_hybrid_mcr",
            "gated_hybrid_mcr_compat",
            "gated_top2_mcr",
            "post_n_mcr",
            "posterior_n_mcr",
            "post7_mcr",
            "posterior_n7_mcr",
            "multi_arm_rrf",
            "tree_rrf",
            "closed_pool_rrf",
            "closed_pool_views_rrf",
            "closed_mac_trace_rrf",
            "closed_mac_rrf",
            "mac_supervisor_on_pool",
            "closed_live_mac_supervisor",
            "closed_live_mac",
            "live_closed_mac",
            "tree_mac_pad",
            "mac_pad",
            "tree_mac_pad_selective",
            "mac_pad_selective",
        ],
        help="pred_ddx source for projection/eval (default: global posterior Top-K)",
    )
    ap.add_argument(
        "--pool-n",
        type=int,
        default=DEFAULT_POST_N_MCR_POOL,
        help="for post_n_mcr / post7_mcr: posterior pool size before MCR (default 7)",
    )
    ap.add_argument(
        "--projection-subdir",
        default="",
        help="annotate/<subdir> for projections (auto by --ddx-source)",
    )
    ap.add_argument(
        "--live-calib",
        action="store_true",
        help="for gate/calib projection arms: live both_l1fallback (needs LLM)",
    )
    ap.add_argument(
        "--mac-predictions",
        type=Path,
        default=None,
        help="B06 predictions.jsonl for --ddx-source tree_mac_pad",
    )
    ap.add_argument(
        "--mac-trace",
        type=Path,
        default=None,
        help="B06 trace.jsonl for --ddx-source closed_mac_trace_rrf",
    )
    ap.add_argument(
        "--live-closed-mac",
        action="store_true",
        help="for closed_live_mac_supervisor: live 3-doctor+supervisor LLM calls",
    )
    args = ap.parse_args(list(argv) if argv is not None else None)

    ds = args.dataset
    if ds == "ox":
        ds = "open_xddx"
    elif ds == "mcr":
        ds = "medcasereasoning"
    elif ds == "ra":
        ds = "rarearena"

    ddx_src = normalize_ddx_source(args.ddx_source)

    workers = int(args.workers)
    if workers <= 0:
        workers = (
            int(judges.JUDGE_WORKERS) if args.judge == "llm" else 1
        )

    summary = run_eval(
        dataset=ds,
        run_dir=args.run_dir,
        subset_parquet=args.subset_parquet,
        judge_kind=args.judge,
        ddx_k=int(args.ddx_k),
        build_projection=bool(args.build_projection),
        resume_projection=bool(args.resume),
        nlg_metrics=bool(args.nlg_metrics),
        case_ids=list(args.case_id or []),
        write_md=not args.no_md,
        workers=workers,
        out_name=str(args.out_name or ""),
        resume_scores=bool(args.resume_scores),
        skip_reasoning_recall=bool(args.skip_reasoning_recall),
        ddx_source=str(ddx_src),
        projection_subdir=str(args.projection_subdir or ""),
        dry_calib=not bool(args.live_calib),
        pool_n=int(args.pool_n),
        mac_predictions=args.mac_predictions,
        mac_trace=args.mac_trace,
        live_closed_mac=bool(args.live_closed_mac),
        judge_model=str(args.judge_model or "") or None,
    )
    # Print compact metrics
    printable = {k: v for k, v in summary.items() if not str(k).startswith("_")}
    print(json.dumps(printable, indent=2, ensure_ascii=False))
    return 0 if int(summary.get("n_errors") or 0) == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
