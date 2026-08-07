#!/usr/bin/env python3
"""DiagnosisArena staged pipeline: VP → trees → P5 → annotate → mapper.

Default target: remaining 76 cases from d2_seq100_v1 after the signed 24-case
pilot. Each stage uses workers=12. Stages 1–3 write an authoritative flat freeze
under ``{output}/frozen/`` and reload it on subsequent runs (``--resume`` /
per-stage skip when complete).

Layout:
  {output}/
    case_ids.json
    frozen/
      vignette_parser_frozen.json
      shared_trees/{id}.json
      p5_audit/{id}.json
      p5_headline_frozen.json
      freeze_manifest.json
    annotate/          # stage 4 (downstream Top-2)
    pipeline_summary.json

Usage:
  PYTHONPATH=src:scripts/paper:scripts \\
    TREE_DX_DIRECT_POST_OUTPUT_CAP=8192 \\
    python3 -u scripts/paper/run_diagnosisarena_pipeline_staged.py \\
      --workers 12 --resume
"""
from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "paper"))

os.environ.setdefault("TREE_DX_USE_PROXY", "1")
os.environ.setdefault("TREE_DX_EMBED_DEVICE", "cpu")
os.environ.setdefault("TREE_DX_DIRECT_POST_OUTPUT_CAP", "8192")
os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("MKL_NUM_THREADS", "2")

import diagnosisarena_adapter as da  # noqa: E402
import run_diagnosisarena_downstream_top2 as down  # noqa: E402
import run_diagnosisarena_mapper_w12 as mapper  # noqa: E402
import run_diagnosisarena_stress_p5_compile as p5stress  # noqa: E402
import run_diagnosisarena_vignette_parser_probe as vp  # noqa: E402

# Re-assert after imports: VP probe historically overwrote this to 4096 at
# import time. Trees/P5/annotate require ≥8192 for long JSON modules.
os.environ["TREE_DX_DIRECT_POST_OUTPUT_CAP"] = "8192"


def _ensure_pipeline_output_cap(min_cap: int = 8192) -> None:
    try:
        current = int(os.environ.get("TREE_DX_DIRECT_POST_OUTPUT_CAP") or "0")
    except ValueError:
        current = 0
    if current < min_cap:
        os.environ["TREE_DX_DIRECT_POST_OUTPUT_CAP"] = str(min_cap)

DEFAULT_CASES_JSON = (
    ROOT / "logs" / "diagnosisarena_d2_m01_v1" / "normalized_cases.json"
)
DEFAULT_DONE_FREEZE = (
    ROOT / "logs" / "diagnosisarena_d2_m01_v1" / "vignette_parser_probe_v3"
    / "vignette_parser_frozen_v3.json"
)
DEFAULT_OUT = (
    ROOT / "logs" / "diagnosisarena_d2_m01_v1" / "pipeline_remaining76_v1"
)
DEFAULT_MODEL = "meta-llama/llama-3.3-70b-instruct"
STAGES = ("vp", "trees", "p5", "annotate", "mapper")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_json(path: Path, payload: Any) -> None:
    da._atomic_json(path, payload)


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def remaining_case_ids(
    cases_json: Path,
    done_freeze: Path,
) -> list[str]:
    all_ids = [
        str(case["id"])
        for case in json.loads(cases_json.read_text(encoding="utf-8")).get("cases") or ()
    ]
    done = set()
    if done_freeze.is_file():
        doc = json.loads(done_freeze.read_text(encoding="utf-8"))
        done = {
            str(row.get("case_id") or "").strip()
            for row in doc.get("cases") or ()
            if str(row.get("case_id") or "").strip()
        }
    return [cid for cid in all_ids if cid not in done]


def _parse_cases(raw: str) -> list[str]:
    return [token.strip() for token in raw.split(",") if token.strip()]


_STRIP_MCQ_OPTIONS = False


def _load_cases(cases_json: Path, case_ids: Sequence[str]) -> list[dict[str, Any]]:
    cases = p5stress._load_cases(cases_json, case_ids)
    if not _STRIP_MCQ_OPTIONS:
        return cases
    # ``case_text`` carries the MCQ stem + Options block, i.e. the gold answer
    # verbatim, and every reasoning stage (vp/trees/p5/annotate) reads it. The
    # baselines and the option mapper both go through da.vignette_body(), so
    # leaving it in makes pipeline-vs-baseline an unequal-input comparison. The
    # mapper takes its options from annotation.source_options, not from
    # case_text, so stripping here does not affect scoring.
    for case in cases:
        body = da.vignette_body(str(case.get("case_text") or ""))
        if body:
            case["case_text"] = body
    return cases


def _vp_complete(freeze_path: Path, case_ids: Sequence[str]) -> bool:
    if not freeze_path.is_file():
        return False
    try:
        freeze = da.load_vignette_parser_freeze(freeze_path)
    except ValueError:
        return False
    return all(cid in freeze and freeze[cid].get("evidence_items") for cid in case_ids)


def _trees_complete(tree_dir: Path, case_ids: Sequence[str]) -> bool:
    for cid in case_ids:
        path = tree_dir / ("%s.json" % cid)
        if not path.is_file():
            return False
        doc = json.loads(path.read_text(encoding="utf-8"))
        n_ev = len((doc.get("state") or {}).get("static_evidence_items") or ())
        if n_ev <= 0:
            return False
    return True


def _p5_complete(freeze_root: Path, case_ids: Sequence[str]) -> bool:
    arm = freeze_root / "p5_headline_frozen.json"
    audit = freeze_root / "p5_audit"
    if not arm.is_file() or not audit.is_dir():
        return False
    disc = json.loads(arm.read_text(encoding="utf-8")).get("disc_audit") or {}
    for cid in case_ids:
        if cid not in disc:
            return False
        if not (audit / ("%s.json" % cid)).is_file():
            return False
    return True


def stage_vp(args: argparse.Namespace, case_ids: Sequence[str]) -> dict[str, Any]:
    frozen_dir = Path(args.output_dir) / "frozen"
    freeze_path = frozen_dir / "vignette_parser_frozen.json"
    probe_dir = Path(args.output_dir) / "vp_probe"
    frozen_dir.mkdir(parents=True, exist_ok=True)

    if args.resume and _vp_complete(freeze_path, case_ids):
        print("[pipeline/vp] FREEZE HIT → %s" % freeze_path, flush=True)
        return {
            "stage": "vp",
            "status": "REUSED",
            "n_cases": len(case_ids),
            "freeze": _rel(freeze_path),
        }

    vp_args = argparse.Namespace(
        cases_json=args.cases_json,
        output_dir=probe_dir,
        model=args.model,
        cases=",".join(case_ids),
        limit=0,
        workers=args.workers,
        call_timeout=args.call_timeout,
        merge_with=None,
        merge_output=None,
        force_signed_off=True,
        resume_freeze=freeze_path if freeze_path.is_file() else None,
        freeze_output=freeze_path,
    )
    print(
        "\n######## stage=vp workers=%d n=%d ########" % (args.workers, len(case_ids)),
        flush=True,
    )
    summary = vp.run_probe(vp_args)
    if not summary.get("freeze_ready") or not _vp_complete(freeze_path, case_ids):
        raise RuntimeError("VP freeze incomplete: %s" % summary)
    return {
        "stage": "vp",
        "status": "OK",
        "n_cases": len(case_ids),
        "n_reused": summary.get("n_reused"),
        "wall_seconds": summary.get("wall_seconds"),
        "freeze": _rel(freeze_path),
        "probe_summary": {
            k: summary[k]
            for k in (
                "n_ok", "n_fail", "n_reused", "wall_seconds", "mean_evidence",
            )
            if k in summary
        },
    }


def stage_trees(args: argparse.Namespace, case_ids: Sequence[str]) -> dict[str, Any]:
    _ensure_pipeline_output_cap(8192)
    frozen_dir = Path(args.output_dir) / "frozen"
    freeze_path = frozen_dir / "vignette_parser_frozen.json"
    tree_dir = frozen_dir / "shared_trees"
    tree_dir.mkdir(parents=True, exist_ok=True)

    if args.resume and _trees_complete(tree_dir, case_ids):
        print("[pipeline/trees] FREEZE HIT → %s" % tree_dir, flush=True)
        return {
            "stage": "trees",
            "status": "REUSED",
            "n_cases": len(case_ids),
            "tree_dir": _rel(tree_dir),
        }
    if not _vp_complete(freeze_path, case_ids):
        raise RuntimeError("trees requires complete VP freeze at %s" % freeze_path)

    cases = _load_cases(args.cases_json, case_ids)
    fingerprint = p5stress.stable_hash({
        "phase": "pipeline-staged-trees",
        "branch_mode": "recall_hints_gap",
        "model": args.model,
        "vignette_freeze": _rel(freeze_path),
        "case_ids": list(case_ids),
        "executor": args.executor,
        "evidence_before_branches": True,
        "align_talp17_order": True,
        "l1_axis_mode": str(getattr(args, "l1_axis_mode", "adaptive") or "adaptive"),
        "no_tree_semantic_dedupe": bool(
            getattr(args, "no_tree_semantic_dedupe", False)
        ),
    })
    print(
        "\n######## stage=trees workers=%d executor=%s n=%d ########"
        % (args.workers, args.executor, len(cases)),
        flush=True,
    )
    t0 = time.monotonic()
    if args.executor == "process":
        payloads = [
            {
                "case": dict(case),
                "tree_path": str(tree_dir / ("%s.json" % case["id"])),
                "fingerprint": fingerprint,
                "resume": bool(args.resume),
            }
            for case in cases
        ]
        records = p5stress._map_process(
            payloads,
            workers=args.workers,
            initializer=p5stress._init_tree_worker,
            initargs=(
                args.model,
                str(freeze_path),
                not bool(getattr(args, "no_tree_semantic_dedupe", False)),
            ),
            worker_fn=p5stress._run_tree_job,
            label="trees/w%d" % args.workers,
        )
    else:
        records = p5stress._map_thread_trees(
            cases,
            workers=args.workers,
            model=args.model,
            freeze_path=freeze_path,
            tree_dir=tree_dir,
            fingerprint=fingerprint,
            resume=bool(args.resume),
            tree_semantic_dedupe=not bool(
                getattr(args, "no_tree_semantic_dedupe", False)
            ),
        )
    wall = time.monotonic() - t0
    ok = sum(1 for row in records if row.get("status") in {"OK", "REUSED"})
    summary = {
        "stage": "trees",
        "status": "OK" if ok == len(cases) else "ERROR",
        "workers": args.workers,
        "executor": args.executor,
        "n_cases": len(cases),
        "n_ok": ok,
        "n_error": len(cases) - ok,
        "wall_seconds": round(wall, 3),
        "throughput_cases_per_hour": (
            round(len(cases) / wall * 3600.0, 3) if wall > 0 else None
        ),
        "tree_dir": _rel(tree_dir),
        "errors": [row for row in records if row.get("status") not in {"OK", "REUSED"}],
    }
    _atomic_json(tree_dir / "summary.json", summary)
    if summary["n_error"]:
        raise RuntimeError("trees failed: %s" % summary["errors"][:5])
    return summary


def stage_p5(args: argparse.Namespace, case_ids: Sequence[str]) -> dict[str, Any]:
    _ensure_pipeline_output_cap(8192)
    frozen_dir = Path(args.output_dir) / "frozen"
    tree_dir = frozen_dir / "shared_trees"
    cache_dir = frozen_dir / "p5_audit"
    arm_path = frozen_dir / "p5_headline_frozen.json"
    cache_dir.mkdir(parents=True, exist_ok=True)

    if args.resume and _p5_complete(frozen_dir, case_ids):
        print("[pipeline/p5] FREEZE HIT → %s" % arm_path, flush=True)
        return {
            "stage": "p5",
            "status": "REUSED",
            "n_cases": len(case_ids),
            "p5_arm": _rel(arm_path),
        }
    if not _trees_complete(tree_dir, case_ids):
        raise RuntimeError("p5 requires complete trees under %s" % tree_dir)

    cases = _load_cases(args.cases_json, case_ids)
    print(
        "\n######## stage=p5 workers=%d executor=%s n=%d ########"
        % (args.workers, args.executor, len(cases)),
        flush=True,
    )
    t0 = time.monotonic()
    if args.executor == "process":
        payloads = [
            {
                "case": dict(case),
                "tree_path": str(tree_dir / ("%s.json" % case["id"])),
                "cache_dir": str(cache_dir),
            }
            for case in cases
        ]
        records = p5stress._map_process(
            payloads,
            workers=args.workers,
            initializer=p5stress._init_p5_worker,
            initargs=(args.model, float(args.call_timeout)),
            worker_fn=p5stress._run_p5_job,
            label="p5/w%d" % args.workers,
        )
    else:
        records = p5stress._map_thread_p5(
            cases,
            workers=args.workers,
            model=args.model,
            call_timeout=args.call_timeout,
            tree_dir=tree_dir,
            cache_dir=cache_dir,
        )
    wall = time.monotonic() - t0
    ok = sum(1 for row in records if row.get("status") == "OK")
    # Merge into existing arm so subset regen does not wipe other frozen cases.
    existing_audit: dict[str, list] = {}
    if arm_path.is_file():
        try:
            existing_audit = dict(
                json.loads(arm_path.read_text(encoding="utf-8")).get("disc_audit")
                or {}
            )
        except (OSError, json.JSONDecodeError, TypeError):
            existing_audit = {}
    for path in sorted(cache_dir.glob("*.json")):
        if path.name == "summary.json":
            continue
        try:
            existing_audit[path.stem] = list(
                json.loads(path.read_text(encoding="utf-8")).get("rules") or ()
            )
        except (OSError, json.JSONDecodeError, TypeError):
            continue
    arm = {
        "summary": {
            "tag": "diagnosisarena_d2_p5_headline",
            "stage": "p5",
            "n_cases": len(existing_audit),
            "workers": args.workers,
            "executor": args.executor,
            "compiled_at": _utc_now(),
            "retain_artifacts": True,
        },
        "disc_audit": existing_audit,
        "audit_summary": {},
        "case_normalized": {},
        "key_audit": {},
        "entry_audit": {},
        "rows": [],
    }
    _atomic_json(arm_path, arm)
    summary = {
        "stage": "p5",
        "status": "OK" if ok == len(cases) else "ERROR",
        "workers": args.workers,
        "executor": args.executor,
        "n_cases": len(cases),
        "n_ok": ok,
        "n_error": len(cases) - ok,
        "wall_seconds": round(wall, 3),
        "throughput_cases_per_hour": (
            round(len(cases) / wall * 3600.0, 3) if wall > 0 else None
        ),
        "p5_arm": _rel(arm_path),
        "p5_audit": _rel(cache_dir),
        "arm_n_cases": len(existing_audit),
        "errors": [row for row in records if row.get("status") != "OK"],
    }
    _atomic_json(frozen_dir / "compile_p5_summary.json", summary)
    if summary["n_error"]:
        raise RuntimeError("p5 failed: %s" % summary["errors"][:5])
    return summary


def _write_freeze_manifest(
    *,
    frozen_dir: Path,
    case_ids: Sequence[str],
    stage_rows: Sequence[Mapping[str, Any]],
) -> Path:
    path = frozen_dir / "freeze_manifest.json"
    payload = {
        "schema_version": 1,
        "created_at": _utc_now(),
        "asset_kind": "diagnosisarena_pipeline_frozen_v1",
        "n_cases": len(case_ids),
        "case_ids": list(case_ids),
        "stages_1_to_3": list(stage_rows),
        "paths": {
            "vignette_parser_frozen": _rel(
                frozen_dir / "vignette_parser_frozen.json"
            ),
            "shared_trees": _rel(frozen_dir / "shared_trees"),
            "p5_audit": _rel(frozen_dir / "p5_audit"),
            "p5_headline_frozen": _rel(frozen_dir / "p5_headline_frozen.json"),
        },
        "note": (
            "Authoritative freeze for stages 1–3. Annotate/mapper must load "
            "these artifacts; do not re-run VP/trees/P5 unless intentionally "
            "refreshing the freeze."
        ),
    }
    _atomic_json(path, payload)
    return path


def stage_annotate(args: argparse.Namespace, case_ids: Sequence[str]) -> dict[str, Any]:
    _ensure_pipeline_output_cap(8192)
    frozen_dir = Path(args.output_dir) / "frozen"
    annotate_dir = Path(args.output_dir) / "annotate"
    annotate_dir.mkdir(parents=True, exist_ok=True)
    freeze_path = frozen_dir / "vignette_parser_frozen.json"
    if not _p5_complete(frozen_dir, case_ids):
        # For subset regen, require only requested cases to have P5.
        missing = [
            cid for cid in case_ids
            if not (frozen_dir / "p5_audit" / ("%s.json" % cid)).is_file()
        ]
        if missing:
            raise RuntimeError("annotate requires P5 freeze for %s" % missing)

    # Refresh staged trees/P5 copies for the requested cases from authoritative freeze.
    tree_dst = annotate_dir / "shared_trees"
    tree_dst.mkdir(parents=True, exist_ok=True)
    for cid in case_ids:
        src = frozen_dir / "shared_trees" / ("%s.json" % cid)
        if src.is_file():
            (tree_dst / src.name).write_bytes(src.read_bytes())
    frozen_arm = frozen_dir / "p5_headline_frozen.json"
    if frozen_arm.is_file():
        (annotate_dir / "p5_headline_frozen.json").write_bytes(frozen_arm.read_bytes())
        # Keep per-case audits in sync for routing helpers.
        audit_dst = annotate_dir / "p5_audit"
        audit_dst.mkdir(parents=True, exist_ok=True)
        for cid in case_ids:
            src = frozen_dir / "p5_audit" / ("%s.json" % cid)
            if src.is_file():
                (audit_dst / src.name).write_bytes(src.read_bytes())

    manifest_path = annotate_dir / "stage_manifest.json"
    skip_stage = manifest_path.is_file()
    down_args = argparse.Namespace(
        cases_json=args.cases_json,
        vignette_freeze=freeze_path,
        stress_root=None,
        freeze_root=frozen_dir,
        cases=",".join(case_ids),
        output_dir=annotate_dir,
        model=args.model,
        workers=args.workers,
        call_timeout=args.call_timeout,
        resume=False if not args.resume else bool(args.resume),
        skip_stage=skip_stage,
        calibration_arm=str(
            getattr(args, "calibration_arm", "both_l1fallback")
        ),
        calibration_k=int(getattr(args, "calibration_k", 5) or 5),
        calibration_dry_run=bool(
            getattr(args, "calibration_dry_run", False)
        ),
        granularity_mode=str(
            getattr(args, "granularity_mode", "compat")
        ),
        l1_calib=str(getattr(args, "l1_calib", "off")),
        leaf_inject_bind_repair=bool(
            getattr(args, "leaf_inject_bind_repair", False)
        ),
        targeted_l2_gapfill=bool(
            getattr(args, "targeted_l2_gapfill", False)
        ),
        targeted_l2_gapfill_arm=str(
            getattr(args, "targeted_l2_gapfill_arm", "ALL_B_b1")
        ),
        fixed_l1_budget=int(getattr(args, "fixed_l1_budget", 6) or 6),
        l2_local_evidence_budget=int(
            getattr(args, "l2_local_evidence_budget", 4) or 4
        ),
        l2_between_evidence_budget=int(
            getattr(args, "l2_between_evidence_budget", 2) or 2
        ),
        l2_candidate_max_per_live_family=int(
            getattr(args, "l2_candidate_max_per_live_family", 6) or 6
        ),
        l2_gap_force_emit_uncovered=bool(
            getattr(args, "l2_gap_force_emit_uncovered", False)
        ),
        l2_gap_force_emit_max=int(
            getattr(args, "l2_gap_force_emit_max", 3) or 3
        ),
        write_annotated_trees=bool(
            getattr(args, "write_annotated_trees", True)
        ) and not bool(getattr(args, "no_write_annotated_trees", False)),
        writeback_mode=str(getattr(args, "writeback_mode", "normal") or "normal"),
        writeback_shuffle_seed=int(
            getattr(args, "writeback_shuffle_seed", 20260731) or 20260731
        ),
        score_scope_mode=str(
            getattr(args, "score_scope_mode", "per_family") or "per_family"
        ),
        l1_bfs_preset=str(
            getattr(args, "l1_bfs_preset", None) or "p5_anti_anchor_direct"
        ),
        no_inject_compiler_rules=bool(
            getattr(args, "no_inject_compiler_rules", False)
        ),
        l1_axis_mode=str(getattr(args, "l1_axis_mode", "adaptive") or "adaptive"),
        no_tree_semantic_dedupe=bool(
            getattr(args, "no_tree_semantic_dedupe", False)
        ),
        reuse_l2_leaves=bool(getattr(args, "reuse_l2_leaves", False)),
    )
    print(
        "\n######## stage=annotate workers=%d n=%d skip_stage=%s "
        "targeted_gapfill=%s ########"
        % (
            args.workers,
            len(case_ids),
            skip_stage,
            bool(getattr(args, "targeted_l2_gapfill", False)),
        ),
        flush=True,
    )
    if not skip_stage:
        down.stage_assets(down_args)
    summary = down.run_downstream(down_args)
    return {
        "stage": "annotate",
        "status": "OK" if summary.get("n_error", 1) == 0 else "ERROR",
        "annotate_dir": _rel(annotate_dir),
        "downstream_summary": summary,
    }


def stage_mapper(args: argparse.Namespace, case_ids: Sequence[str]) -> dict[str, Any]:
    annotate_dir = Path(args.output_dir) / "annotate"
    if not (annotate_dir / "case_results").is_dir():
        raise RuntimeError("mapper requires annotate case_results under %s" % annotate_dir)
    # OpenRouter soft rate limits allow ~50 concurrent for non-RAG typed_llm.
    # RAG mode loads indexes + extra critic calls — keep caller workers as-is
    # (typically ≤25) and do not auto-escalate.
    mapper_workers = int(args.workers)
    if str(args.mapper_mode) != "typed_llm_disagreement_rag":
        mapper_workers = max(mapper_workers, 50)
    mapper_args = argparse.Namespace(
        downstream_dir=annotate_dir,
        model=args.model,
        workers=mapper_workers,
        call_timeout=args.call_timeout,
        mapper_mode=args.mapper_mode,
        resume=bool(args.resume),
        synonym_bind_repair=bool(getattr(args, "synonym_bind_repair", False)),
        synonym_bind_min_score=float(
            getattr(args, "synonym_bind_min_score", 0.70)
        ),
        synonym_bind_bridge=getattr(args, "synonym_bind_bridge", None),
    )
    synonym_on = bool(mapper_args.synonym_bind_repair)
    print(
        "\n######## stage=mapper workers=%d n=%d mode=%s synonym_bind=%s ########"
        % (mapper_workers, len(case_ids), args.mapper_mode, synonym_on),
        flush=True,
    )
    # Reuse mapper main body via constructing equivalent CLI invocation.
    old_argv = sys.argv
    try:
        sys.argv = [
            "run_diagnosisarena_mapper_w12.py",
            "--downstream-dir", str(annotate_dir),
            "--model", args.model,
            "--workers", str(mapper_workers),
            "--call-timeout", str(args.call_timeout),
            "--mapper-mode", args.mapper_mode,
            "--synonym-bind-min-score", str(mapper_args.synonym_bind_min_score),
        ]
        if synonym_on:
            sys.argv.append("--synonym-bind-repair")
        bridge = mapper_args.synonym_bind_bridge
        if bridge:
            sys.argv.extend(["--synonym-bind-bridge", str(bridge)])
        if args.resume:
            sys.argv.append("--resume")
        code = mapper.main()
    finally:
        sys.argv = old_argv
    summary_path = annotate_dir / "mapper" / "summary.json"
    summary = (
        json.loads(summary_path.read_text(encoding="utf-8"))
        if summary_path.is_file() else {"status": "MISSING"}
    )
    return {
        "stage": "mapper",
        "status": "OK" if code == 0 else "ERROR",
        "exit_code": code,
        "synonym_bind_repair": synonym_on,
        "mapper_summary": summary,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases-json", type=Path, default=DEFAULT_CASES_JSON)
    parser.add_argument(
        "--done-freeze",
        type=Path,
        default=DEFAULT_DONE_FREEZE,
        help="Signed freeze whose case_ids are excluded from remaining set",
    )
    parser.add_argument(
        "--cases",
        default="",
        help="Override case ids (comma). Default: remaining vs --done-freeze",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--call-timeout", type=float, default=240.0)
    parser.add_argument(
        "--executor",
        default="process",
        choices=["process", "thread"],
        help="Executor for trees/P5 (default process)",
    )
    parser.add_argument("--start-method", default="spawn", choices=["spawn", "fork", "forkserver"])
    parser.add_argument(
        "--mapper-mode",
        default="typed_llm",
        choices=[
            "deterministic_gold_blind",
            "typed_llm",
            "typed_llm_disagreement_rag",
        ],
    )
    parser.add_argument(
        "--calibration-arm",
        default="both_l1fallback",
        choices=[
            "ours",
            "off",
            "none",
            "support_rerank",
            "pair",
            "both",
            "both_l1fallback",
            "l1fallback",
        ],
        help="Passed to annotate/downstream TopKCalibration (default both_l1fallback)",
    )
    parser.add_argument("--calibration-k", type=int, default=5)
    parser.add_argument(
        "--calibration-dry-run",
        action="store_true",
        help="Skip calibration LLM calls in annotate",
    )
    parser.add_argument(
        "--granularity-mode",
        default="compat",
        choices=["off", "merge", "deepen", "compat"],
        help="Passed to annotate (default compat=merge×calib parallel)",
    )
    parser.add_argument(
        "--l1-calib",
        default="off",
        choices=["off", "ours", "support", "pair", "b12"],
        help="Passed to annotate L1 family calib after F6 (default off)",
    )
    parser.add_argument(
        "--leaf-inject-bind-repair",
        action="store_true",
        help=(
            "Passed to annotate: after compat, inject full-tree leaves into "
            "final_ranking before mapper (default off)"
        ),
    )
    parser.add_argument(
        "--targeted-l2-gapfill",
        action="store_true",
        help=(
            "Passed to annotate: after Config A, apply hybrid targeted L2 "
            "gapfill before joint ranking (default off; research_only)"
        ),
    )
    parser.add_argument(
        "--targeted-l2-gapfill-arm",
        default="ALL_B_b1",
        help="Arm for --targeted-l2-gapfill (default ALL_B_b1; B-source only)",
    )
    parser.add_argument(
        "--fixed-l1-budget",
        type=int,
        default=6,
        help="L1 evidence freeze Fn for annotate (default 6; OX locked=4)",
    )
    parser.add_argument(
        "--l2-local-evidence-budget",
        type=int,
        default=4,
        help="Local L2 evidence stop_after (default 4)",
    )
    parser.add_argument(
        "--l2-between-evidence-budget",
        type=int,
        default=2,
        help="Between-family evidence stop_after (default 2)",
    )
    parser.add_argument(
        "--l2-candidate-max-per-live-family",
        type=int,
        default=6,
        help="Max L2 children per L1 after live posterior writeback",
    )
    parser.add_argument(
        "--l2-gap-force-emit-uncovered",
        action="store_true",
        help="emit_v1: force-append uncovered gap leaves during Config A",
    )
    parser.add_argument(
        "--l2-gap-force-emit-max",
        type=int,
        default=3,
        help="Max force-emitted leaves per parent (default 3)",
    )
    parser.add_argument(
        "--no-write-annotated-trees",
        action="store_true",
        help="Do not overwrite annotate/shared_trees with live L2 state",
    )
    parser.add_argument(
        "--writeback-mode",
        default="normal",
        choices=["normal", "placebo_refresh", "shuffled"],
        help="T1-07 writeback control: normal|placebo_refresh|shuffled",
    )
    parser.add_argument(
        "--writeback-shuffle-seed",
        type=int,
        default=20260731,
    )
    parser.add_argument(
        "--score-scope-mode",
        default="per_family",
        choices=["per_family", "global"],
        help="T1-07 AB31 flat recomputation when set to global",
    )
    parser.add_argument(
        "--l1-bfs-preset",
        default="p5_anti_anchor_direct",
        help="L1 BFS preset for annotate (default p5_anti_anchor_direct)",
    )
    parser.add_argument(
        "--no-inject-compiler-rules",
        action="store_true",
        help="Do not inject P5 compiler blocks into L1 BFS (AB22)",
    )
    parser.add_argument(
        "--l1-axis-mode",
        default="adaptive",
        choices=["adaptive", "fixed_icd", "random", "flat"],
        help="C3: L1 axis mode for annotate (and trees fingerprint)",
    )
    parser.add_argument(
        "--no-tree-semantic-dedupe",
        action="store_true",
        help="C3: disable L2 synonym de-dupe guidance (keep exact-string dedupe)",
    )
    parser.add_argument(
        "--reuse-l2-leaves",
        action="store_true",
        help="C3: keep existing L2 leaves when remapping L1 axis",
    )
    parser.add_argument(
        "--synonym-bind-repair",
        action="store_true",
        help=(
            "Passed to mapper: Approach A empty option→leaf synonym/bridge "
            "bind-repair then re-rank (default off; live smoke ~0.81/0.93)"
        ),
    )
    parser.add_argument(
        "--synonym-bind-min-score",
        type=float,
        default=0.70,
        help="Min score for --synonym-bind-repair (default 0.70)",
    )
    parser.add_argument(
        "--synonym-bind-bridge",
        type=Path,
        default=None,
        help="Optional disease_name_bridge.json for --synonym-bind-repair",
    )
    parser.add_argument(
        "--from-stage",
        default="vp",
        choices=STAGES,
        help="First stage to run (inclusive)",
    )
    parser.add_argument(
        "--to-stage",
        default="mapper",
        choices=STAGES,
        help="Last stage to run (inclusive)",
    )
    parser.add_argument(
        "--only-stage",
        default="",
        choices=("",) + STAGES,
        help="Run a single stage (overrides --from/--to)",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Load frozen VP/trees/P5 and per-case annotate/mapper OK rows",
    )
    parser.add_argument(
        "--strip-mcq-options",
        action="store_true",
        help=(
            "Feed vp/trees/p5/annotate the options-stripped vignette, matching "
            "what the baselines and the option mapper read. Off by default to "
            "reproduce the existing runs."
        ),
    )
    args = parser.parse_args()
    global _STRIP_MCQ_OPTIONS
    _STRIP_MCQ_OPTIONS = bool(args.strip_mcq_options)
    args.output_dir = Path(args.output_dir).expanduser().resolve()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.cases_json = Path(args.cases_json).expanduser().resolve()
    args.done_freeze = Path(args.done_freeze).expanduser().resolve()

    if args.executor == "process":
        try:
            mp.set_start_method(args.start_method, force=True)
        except RuntimeError:
            pass

    if args.cases.strip():
        case_ids = _parse_cases(args.cases)
    else:
        case_ids = remaining_case_ids(args.cases_json, args.done_freeze)
    if not case_ids:
        raise RuntimeError("no cases selected")
    _atomic_json(args.output_dir / "case_ids.json", {
        "created_at": _utc_now(),
        "n_cases": len(case_ids),
        "case_ids": case_ids,
        "done_freeze": _rel(args.done_freeze),
    })

    if args.only_stage:
        selected = [args.only_stage]
    else:
        i0 = STAGES.index(args.from_stage)
        i1 = STAGES.index(args.to_stage)
        if i1 < i0:
            raise ValueError("--to-stage before --from-stage")
        selected = list(STAGES[i0:i1 + 1])

    print(
        "=== pipeline remaining cases=%d workers=%d stages=%s resume=%s ==="
        % (len(case_ids), args.workers, ",".join(selected), args.resume),
        flush=True,
    )
    runners = {
        "vp": stage_vp,
        "trees": stage_trees,
        "p5": stage_p5,
        "annotate": stage_annotate,
        "mapper": stage_mapper,
    }
    stage_rows: list[dict[str, Any]] = []
    started = time.monotonic()
    exit_code = 0
    for name in selected:
        try:
            row = runners[name](args, case_ids)
        except Exception as exc:  # noqa: BLE001
            import traceback
            row = {
                "stage": name,
                "status": "ERROR",
                "error": "%s: %s" % (type(exc).__name__, exc),
                "traceback": traceback.format_exc()[-2500:],
            }
            exit_code = 1
            stage_rows.append(row)
            print(json.dumps(row, ensure_ascii=False, indent=2), flush=True)
            break
        stage_rows.append(row)
        compact = {
            k: row[k]
            for k in row
            if k not in {
                "errors", "traceback", "downstream_summary",
                "mapper_summary", "probe_summary",
            }
        }
        print(json.dumps(compact, ensure_ascii=False, indent=2), flush=True)
        if row.get("status") == "ERROR":
            exit_code = 1
            break

    # Always refresh freeze manifest when stages 1–3 are present.
    frozen_dir = args.output_dir / "frozen"
    freeze_rows = [row for row in stage_rows if row.get("stage") in {"vp", "trees", "p5"}]
    if freeze_rows and _vp_complete(frozen_dir / "vignette_parser_frozen.json", case_ids):
        if _trees_complete(frozen_dir / "shared_trees", case_ids) and _p5_complete(
            frozen_dir, case_ids
        ):
            _write_freeze_manifest(
                frozen_dir=frozen_dir,
                case_ids=case_ids,
                stage_rows=freeze_rows,
            )

    pipeline = {
        "schema_version": 1,
        "created_at": _utc_now(),
        "output_dir": _rel(args.output_dir),
        "n_cases": len(case_ids),
        "case_ids": case_ids,
        "workers": args.workers,
        "executor": args.executor,
        "stages_requested": selected,
        "stages": stage_rows,
        "wall_seconds": round(time.monotonic() - started, 3),
        "exit_code": exit_code,
    }
    _atomic_json(args.output_dir / "pipeline_summary.json", pipeline)
    print(json.dumps({
        "exit_code": exit_code,
        "wall_seconds": pipeline["wall_seconds"],
        "stages": [
            {"stage": r.get("stage"), "status": r.get("status")}
            for r in stage_rows
        ],
        "summary": _rel(args.output_dir / "pipeline_summary.json"),
    }, ensure_ascii=False, indent=2), flush=True)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
