#!/usr/bin/env python3
"""DiagnosisArena: full P5 headline compile stress (process pool + thread fallback).

Protocol (artifact-preserving):
  * 24 mutually independent cases (includes signed-off VP set 3,4,5,7,11).
  * Split into two disjoint 12-case cohorts so w=6 and w=12 each keep their
    own frozen ``p5_headline`` / ``p5_audit`` outputs (no overwrite).
  * Executor default: spawn process pool (per-process controller/FAISS/KB,
    OMP≤2). ``--executor thread`` remains as rollback.

Phases:
  build-trees → compile-p5 (per cohort)

Usage:
  PYTHONPATH=src:scripts/paper:scripts python3 -u \\
    scripts/paper/run_diagnosisarena_stress_p5_compile.py \\
    --executor process --start-method spawn
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import multiprocessing as mp
import os
import sys
import time
import traceback
from concurrent.futures import (
    ProcessPoolExecutor,
    ThreadPoolExecutor,
    as_completed,
)
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("MKL_NUM_THREADS", "2")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "2")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "2")
os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "2")
os.environ.setdefault("TREE_DX_USE_PROXY", "1")
os.environ.setdefault("TREE_DX_EMBED_DEVICE", "cpu")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "paper"))

import diagnosisarena_adapter as da  # noqa: E402
import eval_branch_talp_composed as composed  # noqa: E402
from agentclinic_tree_dx.l1_evidence_bfs import stable_hash  # noqa: E402
from agentclinic_tree_dx.llm_client import RobustLLMClient  # noqa: E402

DEFAULT_CASES_JSON = (
    ROOT / "logs" / "diagnosisarena_d2_m01_v1" / "normalized_cases.json"
)
DEFAULT_FREEZE = (
    ROOT / "logs" / "diagnosisarena_d2_m01_v1" / "vignette_parser_probe_v3"
    / "vignette_parser_frozen_v3.json"
)
DEFAULT_OUT = (
    ROOT / "logs" / "diagnosisarena_d2_m01_v1" / "stress_p5_compile_v1"
)
DEFAULT_MODEL = "meta-llama/llama-3.3-70b-instruct"
BRANCH_SCRIPT = ROOT / "scripts" / "eval_branch_creation_medbullets.py"
TALP_SCRIPT = ROOT / "scripts" / "eval_talp_discrimination.py"
P5_STAGE = "p5"

# Disjoint cohorts: w06 keeps the 5 signed VP cases + 7 new; w12 the rest.
COHORT_W06 = [
    "3", "4", "5", "7", "11", "12", "15", "19", "21", "22", "27", "28",
]
COHORT_W12 = [
    "29", "33", "36", "39", "40", "45", "57", "59", "60", "62", "63", "67",
]

_PROC: dict[str, Any] = {}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot import %s" % path)
    module = importlib.util.module_from_spec(spec)
    # Must register before exec_module: dataclasses in the loaded script
    # resolve annotations via sys.modules[cls.__module__] (spawn workers).
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _load_cases(
    cases_json: Path,
    case_ids: Sequence[str],
) -> list[dict[str, Any]]:
    doc = json.loads(cases_json.read_text(encoding="utf-8"))
    wanted = {str(x).strip() for x in case_ids if str(x).strip()}
    cases = [
        case for case in doc.get("cases") or ()
        if str(case["id"]) in wanted
    ]
    missing = sorted(wanted - {str(c["id"]) for c in cases})
    if missing:
        raise ValueError("unknown case ids: %s" % missing)
    # Stable order matching cohort declaration.
    order = {cid: index for index, cid in enumerate(case_ids)}
    cases.sort(key=lambda c: order.get(str(c["id"]), 10**9))
    return cases


def _init_tree_worker(
    model: str,
    freeze_path: str,
    tree_semantic_dedupe: bool = True,
) -> None:
    branch = _load_module("da_p5_stress_branch", BRANCH_SCRIPT)
    controller, env, _, provenance = branch.build_controller(
        model,
        branch_mode="recall_hints_gap",
        config_overrides={
            "talp_disc_profile": "off",
            "force_expand_all_l1": True,
            "tree_semantic_dedupe": bool(tree_semantic_dedupe),
            "l2_recall_gap_fill": True,
        },
    )
    freeze = da.load_vignette_parser_freeze(freeze_path)
    _PROC.clear()
    _PROC.update({
        "kind": "tree",
        "branch": branch,
        "controller": controller,
        "env": env,
        "provenance": provenance,
        "freeze": freeze,
        "model": model,
        "pid": os.getpid(),
    })
    print(
        "[proc-init/tree] pid=%s freeze=%d" % (os.getpid(), len(freeze)),
        flush=True,
    )


def _run_tree_job(payload: Mapping[str, Any]) -> dict[str, Any]:
    started = time.monotonic()
    case = dict(payload["case"])
    tree_path = Path(payload["tree_path"])
    fingerprint = payload["fingerprint"]
    try:
        if payload.get("resume") and tree_path.is_file():
            existing = json.loads(tree_path.read_text(encoding="utf-8"))
            if existing.get("run_fingerprint") == fingerprint:
                n_ev = len(
                    (existing.get("state") or {}).get("static_evidence_items")
                    or ()
                )
                if n_ev > 0:
                    return {
                        "case_id": case["id"],
                        "status": "REUSED",
                        "n_findings": n_ev,
                        "duration_seconds": 0.0,
                        "worker_pid": os.getpid(),
                    }
        controller = _PROC["controller"]
        env = _PROC["env"]
        branch = _PROC["branch"]
        freeze = _PROC["freeze"]
        provenance = _PROC["provenance"]
        case_id = str(case["id"])
        if case_id not in freeze:
            raise RuntimeError("missing freeze for %s" % case_id)

        def _prepare(state) -> None:
            # Align with TALP17: evidence present before create_branches.
            state.case_id = case_id
            da.apply_frozen_vignette_parser_fields(state, case, freeze[case_id])

        state = branch.run_case_branches(
            controller,
            env,
            str(case["case_text"]),
            parse_vignette=False,
            prepare_state=_prepare,
        )
        state.case_id = case_id
        state.max_tree_depth = 2
        n_findings = len(state.static_evidence_items or ())
        expansion = controller.force_expand_all_l1(state)
        if expansion.get("l1_expansion_rate") != 1.0:
            raise RuntimeError("%s incomplete L1 expansion" % case_id)
        out = {
            "run_fingerprint": fingerprint,
            "tree_hash": "",
            "state": composed._serialize_state(
                state, (provenance or {}).get("last") or {},
            ),
            "expansion": expansion,
            "n_static_evidence_items": n_findings,
            "evidence_source": "vignette_parser_freeze_v3",
            "executor": "process_pool",
            "worker_pid": os.getpid(),
            "duration_seconds": round(time.monotonic() - started, 3),
        }
        if not out["state"].get("static_evidence_items"):
            raise RuntimeError("%s: empty static_evidence_items" % case_id)
        out["tree_hash"] = stable_hash(out["state"]["branches"])
        da._atomic_json(tree_path, out)
        return {
            "case_id": case_id,
            "status": "OK",
            "n_findings": n_findings,
            "duration_seconds": out["duration_seconds"],
            "worker_pid": os.getpid(),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "case_id": str(case.get("id")),
            "status": "ERROR",
            "error": "%s: %s" % (type(exc).__name__, exc),
            "traceback": traceback.format_exc()[-2000:],
            "worker_pid": os.getpid(),
            "duration_seconds": round(time.monotonic() - started, 3),
        }


def _init_p5_worker(model: str, call_timeout: float) -> None:
    # DiscriminatorAgentMatrix emits large candidate-effect JSON; 1024 truncates
    # (finish_reason=length) and previously cascaded into a dead Novita fallback.
    os.environ["TREE_DX_DIRECT_POST_OUTPUT_CAP"] = os.environ.get(
        "TREE_DX_DIRECT_POST_OUTPUT_CAP", "8192"
    )
    talp = _load_module("da_p5_stress_talp", TALP_SCRIPT)
    evp_spec = importlib.util.spec_from_file_location(
        "da_p5_stress_evp", ROOT / "scripts" / "eval_evidence_precision.py",
    )
    evp = importlib.util.module_from_spec(evp_spec)
    evp_spec.loader.exec_module(evp)
    kb = evp.FusedKB(rag=True)
    cfg = talp._cfg_for_stage(P5_STAGE)
    cfg.entry_gate = "all_findings"
    cfg.route = True
    normalizer = talp._get_normalizer()
    dxidx = talp._get_dxindex(with_primekg=True)
    llm = RobustLLMClient(
        model=model,
        call_timeout=call_timeout,
        max_retries=5,
        timeout_retry_cap=2,
        temperature=0.0,
    )
    _PROC.clear()
    _PROC.update({
        "kind": "p5",
        "talp": talp,
        "kb": kb,
        "cfg": cfg,
        "normalizer": normalizer,
        "dxidx": dxidx,
        "llm": llm,
        "pid": os.getpid(),
    })
    print("[proc-init/p5] pid=%s" % os.getpid(), flush=True)


def _compile_one_p5_core(
    *,
    case: Mapping[str, Any],
    tree_payload: Mapping[str, Any],
    talp_module,
    llm,
    kb,
    cfg,
    normalizer,
    dxidx,
    cache_dir: Path,
) -> dict[str, Any]:
    case_id = str(case["id"])
    cache_path = cache_dir / ("%s.json" % case_id)
    if cache_path.is_file():
        return json.loads(cache_path.read_text(encoding="utf-8"))
    state = composed._deserialize_state(tree_payload["state"])
    talp_case = da.build_talp_case(case, state)
    compiler_case = da.runtime_compiler_case(talp_case)
    built = talp_module._build_disc_blocks_v2(
        llm,
        kb,
        {"cases": [compiler_case]},
        cfg,
        normalizer=normalizer,
        dxidx=dxidx,
    )
    rules = list((built.get("audit") or {}).get(case_id) or ())
    payload = {
        "case_id": case_id,
        "stage": P5_STAGE,
        "rules": rules,
        "entry_audit": (built.get("entry_audit") or {}).get(case_id),
        "n_candidates": len(compiler_case["candidates"]),
        "n_findings": len(compiler_case["findings"]),
        "compiled_at": _utc_now(),
        "worker_pid": os.getpid(),
    }
    da._atomic_json(cache_path, payload)
    return payload


def _run_p5_job(payload: Mapping[str, Any]) -> dict[str, Any]:
    started = time.monotonic()
    case = dict(payload["case"])
    try:
        tree = json.loads(Path(payload["tree_path"]).read_text(encoding="utf-8"))
        row = _compile_one_p5_core(
            case=case,
            tree_payload=tree,
            talp_module=_PROC["talp"],
            llm=_PROC["llm"],
            kb=_PROC["kb"],
            cfg=_PROC["cfg"],
            normalizer=_PROC["normalizer"],
            dxidx=_PROC["dxidx"],
            cache_dir=Path(payload["cache_dir"]),
        )
        return {
            "case_id": case["id"],
            "status": "OK",
            "n_rules": len(row.get("rules") or ()),
            "duration_seconds": round(time.monotonic() - started, 3),
            "worker_pid": os.getpid(),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "case_id": str(case.get("id")),
            "status": "ERROR",
            "error": "%s: %s" % (type(exc).__name__, exc),
            "traceback": traceback.format_exc()[-2000:],
            "worker_pid": os.getpid(),
            "duration_seconds": round(time.monotonic() - started, 3),
        }


def _map_process(
    payloads: Sequence[Mapping[str, Any]],
    *,
    workers: int,
    initializer,
    initargs: tuple,
    worker_fn,
    label: str,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with ProcessPoolExecutor(
        max_workers=workers,
        initializer=initializer,
        initargs=initargs,
    ) as pool:
        futures = {
            pool.submit(worker_fn, payload): payload
            for payload in payloads
        }
        done = 0
        for future in as_completed(futures):
            payload = futures[future]
            case_id = str(payload["case"]["id"])
            try:
                row = future.result()
            except Exception as exc:  # noqa: BLE001
                row = {
                    "case_id": case_id,
                    "status": "ERROR",
                    "error": "%s: %s" % (type(exc).__name__, exc),
                }
            records.append(row)
            done += 1
            print(
                "[%s] %d/%d %s %s"
                % (label, done, len(payloads), case_id, row.get("status")),
                flush=True,
            )
    return records


def _map_thread_trees(
    cases: Sequence[Mapping[str, Any]],
    *,
    workers: int,
    model: str,
    freeze_path: Path,
    tree_dir: Path,
    fingerprint: str,
    resume: bool,
    tree_semantic_dedupe: bool = True,
) -> list[dict[str, Any]]:
    """Thread-pool rollback path (shared controller; FAISS may serialize)."""
    branch = _load_module("da_p5_stress_branch_thread", BRANCH_SCRIPT)
    controller, env, _, provenance = branch.build_controller(
        model,
        branch_mode="recall_hints_gap",
        config_overrides={
            "talp_disc_profile": "off",
            "force_expand_all_l1": True,
            "tree_semantic_dedupe": bool(tree_semantic_dedupe),
            "l2_recall_gap_fill": True,
        },
    )
    freeze = da.load_vignette_parser_freeze(freeze_path)

    def _one(case: Mapping[str, Any]) -> dict[str, Any]:
        return _run_tree_job({
            "case": dict(case),
            "tree_path": str(tree_dir / ("%s.json" % case["id"])),
            "fingerprint": fingerprint,
            "resume": resume,
        })

    # Seed _PROC for thread workers that call _run_tree_job.
    _PROC.clear()
    _PROC.update({
        "kind": "tree",
        "branch": branch,
        "controller": controller,
        "env": env,
        "provenance": provenance,
        "freeze": freeze,
        "model": model,
        "pid": os.getpid(),
    })
    records: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(_one, case): case for case in cases}
        done = 0
        for future in as_completed(futures):
            case = futures[future]
            try:
                row = future.result()
            except Exception as exc:  # noqa: BLE001
                row = {
                    "case_id": case["id"],
                    "status": "ERROR",
                    "error": "%s: %s" % (type(exc).__name__, exc),
                }
            records.append(row)
            done += 1
            print(
                "[build-trees/thread] %d/%d %s %s"
                % (done, len(cases), case["id"], row.get("status")),
                flush=True,
            )
    return records


def _map_thread_p5(
    cases: Sequence[Mapping[str, Any]],
    *,
    workers: int,
    model: str,
    call_timeout: float,
    tree_dir: Path,
    cache_dir: Path,
) -> list[dict[str, Any]]:
    _init_p5_worker(model, call_timeout)
    payloads = [
        {
            "case": dict(case),
            "tree_path": str(tree_dir / ("%s.json" % case["id"])),
            "cache_dir": str(cache_dir),
        }
        for case in cases
    ]
    records: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {
            pool.submit(_run_p5_job, payload): payload["case"]["id"]
            for payload in payloads
        }
        done = 0
        for future in as_completed(futures):
            case_id = futures[future]
            try:
                row = future.result()
            except Exception as exc:  # noqa: BLE001
                row = {
                    "case_id": case_id,
                    "status": "ERROR",
                    "error": "%s: %s" % (type(exc).__name__, exc),
                }
            records.append(row)
            done += 1
            print(
                "[compile-p5/thread] %d/%d %s %s"
                % (done, len(payloads), case_id, row.get("status")),
                flush=True,
            )
    return records


def _write_p5_arm(
    *,
    cases: Sequence[Mapping[str, Any]],
    cache_dir: Path,
    arm_path: Path,
    workers: int,
    executor: str,
) -> dict[str, Any]:
    disc_audit: dict[str, list] = {}
    for case in cases:
        path = cache_dir / ("%s.json" % case["id"])
        if path.is_file():
            disc_audit[str(case["id"])] = list(
                json.loads(path.read_text()).get("rules") or ()
            )
    arm = {
        "summary": {
            "tag": "diagnosisarena_d2_p5_headline",
            "stage": P5_STAGE,
            "n_cases": len(disc_audit),
            "workers": workers,
            "executor": executor,
            "compiled_at": _utc_now(),
            "retain_artifacts": True,
        },
        "disc_audit": disc_audit,
        "audit_summary": {},
        "case_normalized": {},
        "key_audit": {},
        "entry_audit": {},
        "rows": [],
    }
    da._atomic_json(arm_path, arm)
    return arm


def run_cohort(
    *,
    cases: Sequence[Mapping[str, Any]],
    workers: int,
    executor: str,
    model: str,
    call_timeout: float,
    freeze_path: Path,
    cohort_dir: Path,
    resume: bool,
    skip_trees: bool = False,
) -> dict[str, Any]:
    cohort_dir.mkdir(parents=True, exist_ok=True)
    tree_dir = cohort_dir / "shared_trees"
    cache_dir = cohort_dir / "p5_audit"
    tree_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    fingerprint = stable_hash({
        "phase": "stress-p5-compile",
        "branch_mode": "recall_hints_gap",
        "model": model,
        "vignette_freeze": str(freeze_path.relative_to(ROOT)),
        "cohort_cases": [c["id"] for c in cases],
        "executor": executor,
        "evidence_before_branches": True,
        "align_talp17_order": True,
    })

    # --- build-trees ---
    tree_summary: dict[str, Any]
    if skip_trees:
        missing = [
            str(case["id"]) for case in cases
            if not (tree_dir / ("%s.json" % case["id"])).is_file()
        ]
        if missing:
            raise RuntimeError(
                "skip-trees requested but missing trees: %s" % missing
            )
        print(
            "\n=== build-trees SKIPPED (reuse existing) n=%d ===" % len(cases),
            flush=True,
        )
        tree_summary = {
            "phase": "build-trees",
            "workers": workers,
            "executor": executor,
            "n_cases": len(cases),
            "n_ok": len(cases),
            "n_error": 0,
            "wall_seconds": 0.0,
            "throughput_cases_per_hour": None,
            "skipped": True,
        }
    else:
        print(
            "\n=== build-trees workers=%d executor=%s n=%d ==="
            % (workers, executor, len(cases)),
            flush=True,
        )
        t0 = time.monotonic()
        if executor == "process":
            tree_payloads = [
                {
                    "case": dict(case),
                    "tree_path": str(tree_dir / ("%s.json" % case["id"])),
                    "fingerprint": fingerprint,
                    "resume": resume,
                }
                for case in cases
            ]
            tree_records = _map_process(
                tree_payloads,
                workers=workers,
                initializer=_init_tree_worker,
                initargs=(model, str(freeze_path)),
                worker_fn=_run_tree_job,
                label="build-trees/w%d" % workers,
            )
        else:
            tree_records = _map_thread_trees(
                cases,
                workers=workers,
                model=model,
                freeze_path=freeze_path,
                tree_dir=tree_dir,
                fingerprint=fingerprint,
                resume=resume,
            )
        tree_wall = time.monotonic() - t0
        tree_ok = sum(
            1 for r in tree_records if r.get("status") in {"OK", "REUSED"}
        )
        tree_summary = {
            "phase": "build-trees",
            "workers": workers,
            "executor": executor,
            "n_cases": len(cases),
            "n_ok": tree_ok,
            "n_error": len(tree_records) - tree_ok,
            "wall_seconds": round(tree_wall, 3),
            "throughput_cases_per_hour": (
                round(len(cases) / tree_wall * 3600.0, 3)
                if tree_wall > 0 else None
            ),
            "records": tree_records,
        }
        da._atomic_json(tree_dir / "summary.json", tree_summary)
        if tree_summary["n_error"]:
            return {
                "workers": workers,
                "executor": executor,
                "exit_code": 1,
                "failed_phase": "build-trees",
                "tree_summary": tree_summary,
            }

    # --- compile-p5 ---
    print(
        "\n=== compile-p5 workers=%d executor=%s n=%d ==="
        % (workers, executor, len(cases)),
        flush=True,
    )
    t1 = time.monotonic()
    if executor == "process":
        p5_payloads = [
            {
                "case": dict(case),
                "tree_path": str(tree_dir / ("%s.json" % case["id"])),
                "cache_dir": str(cache_dir),
            }
            for case in cases
        ]
        p5_records = _map_process(
            p5_payloads,
            workers=workers,
            initializer=_init_p5_worker,
            initargs=(model, float(call_timeout)),
            worker_fn=_run_p5_job,
            label="compile-p5/w%d" % workers,
        )
    else:
        p5_records = _map_thread_p5(
            cases,
            workers=workers,
            model=model,
            call_timeout=call_timeout,
            tree_dir=tree_dir,
            cache_dir=cache_dir,
        )
    p5_wall = time.monotonic() - t1
    p5_ok = sum(1 for r in p5_records if r.get("status") == "OK")
    arm_path = cohort_dir / "p5_headline_frozen.json"
    _write_p5_arm(
        cases=cases,
        cache_dir=cache_dir,
        arm_path=arm_path,
        workers=workers,
        executor=executor,
    )
    p5_summary = {
        "phase": "compile-p5",
        "workers": workers,
        "executor": executor,
        "n_cases": len(cases),
        "n_ok": p5_ok,
        "n_error": len(p5_records) - p5_ok,
        "wall_seconds": round(p5_wall, 3),
        "throughput_cases_per_hour": (
            round(len(cases) / p5_wall * 3600.0, 3) if p5_wall > 0 else None
        ),
        "arm_path": str(arm_path.relative_to(ROOT)),
        "p5_audit_dir": str(cache_dir.relative_to(ROOT)),
        "retain_artifacts": True,
        "records": p5_records,
        "errors": [r for r in p5_records if r.get("status") != "OK"],
    }
    da._atomic_json(cohort_dir / "compile_p5_summary.json", p5_summary)
    return {
        "workers": workers,
        "executor": executor,
        "case_ids": [c["id"] for c in cases],
        "exit_code": 0 if p5_summary["n_error"] == 0 else 1,
        "tree_summary": {
            k: tree_summary[k]
            for k in tree_summary
            if k != "records"
        },
        "p5_summary": {
            k: p5_summary[k]
            for k in p5_summary
            if k not in {"records", "errors"}
        },
        "p5_errors": p5_summary["errors"],
        "artifact_paths": {
            "cohort_dir": str(cohort_dir.relative_to(ROOT)),
            "shared_trees": str(tree_dir.relative_to(ROOT)),
            "p5_audit": str(cache_dir.relative_to(ROOT)),
            "p5_headline_frozen": str(arm_path.relative_to(ROOT)),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases-json", type=Path, default=DEFAULT_CASES_JSON)
    parser.add_argument("--vignette-freeze", type=Path, default=DEFAULT_FREEZE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--call-timeout", type=float, default=240.0)
    parser.add_argument(
        "--executor",
        default="process",
        choices=["process", "thread"],
        help="process=spawn pool (default); thread=legacy rollback",
    )
    parser.add_argument(
        "--start-method",
        default="spawn",
        choices=["spawn", "fork", "forkserver"],
    )
    parser.add_argument(
        "--cohorts",
        default="6,12",
        help="Comma list of worker counts to run (each maps to a fixed cohort)",
    )
    parser.add_argument("--resume", action="store_true")
    parser.add_argument(
        "--skip-trees",
        action="store_true",
        help="Skip build-trees when shared_trees already exist (P5-only rerun)",
    )
    parser.add_argument(
        "--cases-w06",
        default=",".join(COHORT_W06),
        help="12 independent cases for the workers=6 cohort",
    )
    parser.add_argument(
        "--cases-w12",
        default=",".join(COHORT_W12),
        help="12 independent cases for the workers=12 cohort",
    )
    args = parser.parse_args()

    if args.executor == "process":
        try:
            mp.set_start_method(args.start_method, force=True)
        except RuntimeError:
            pass

    out_dir = args.output_dir.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    freeze_path = args.vignette_freeze.expanduser().resolve()
    if not freeze_path.is_file():
        raise FileNotFoundError(
            "vignette freeze missing: %s (run VP v3 merge first)" % freeze_path
        )

    cohort_map = {
        6: [t.strip() for t in args.cases_w06.split(",") if t.strip()],
        12: [t.strip() for t in args.cases_w12.split(",") if t.strip()],
    }
    for workers, ids in cohort_map.items():
        if len(ids) != 12:
            raise ValueError(
                "cohort w=%d must have exactly 12 cases, got %d: %s"
                % (workers, len(ids), ids)
            )
    overlap = set(cohort_map[6]) & set(cohort_map[12])
    if overlap:
        raise ValueError("cohorts must be disjoint; overlap=%s" % sorted(overlap))

    grid = [int(t) for t in args.cohorts.split(",") if t.strip()]
    sweep = []
    for workers in grid:
        if workers not in cohort_map:
            raise ValueError(
                "unsupported cohort workers=%d (need mapping in --cases-w06/w12)"
                % workers
            )
        case_ids = cohort_map[workers]
        cases = _load_cases(args.cases_json, case_ids)
        cohort_dir = out_dir / ("cohort_w%02d" % workers)
        print(
            "\n######## cohort workers=%d cases=%s ########"
            % (workers, ",".join(case_ids)),
            flush=True,
        )
        row = run_cohort(
            cases=cases,
            workers=workers,
            executor=args.executor,
            model=args.model,
            call_timeout=args.call_timeout,
            freeze_path=freeze_path,
            cohort_dir=cohort_dir,
            resume=args.resume,
            skip_trees=args.skip_trees,
        )
        sweep.append(row)
        da._atomic_json(out_dir / ("sweep_w%02d.json" % workers), row)
        print(json.dumps({
            k: row[k] for k in row if k not in {"p5_errors"}
        }, indent=2, ensure_ascii=False), flush=True)

    w6 = next((r for r in sweep if r["workers"] == 6), None)
    w12 = next((r for r in sweep if r["workers"] == 12), None)
    ratio = None
    if (
        w6 and w12
        and (w6.get("p5_summary") or {}).get("throughput_cases_per_hour")
        and (w12.get("p5_summary") or {}).get("throughput_cases_per_hour")
    ):
        ratio = (
            float(w12["p5_summary"]["throughput_cases_per_hour"])
            / float(w6["p5_summary"]["throughput_cases_per_hour"])
        )
    manifest = {
        "schema_version": 1,
        "created_at": _utc_now(),
        "asset_kind": "diagnosisarena_stress_p5_compile_v1",
        "executor": args.executor,
        "start_method": args.start_method if args.executor == "process" else None,
        "omp_num_threads": os.environ.get("OMP_NUM_THREADS"),
        "vignette_freeze": str(freeze_path.relative_to(ROOT)),
        "cohort_w06_cases": cohort_map[6],
        "cohort_w12_cases": cohort_map[12],
        "disjoint": True,
        "retain_p5_artifacts": True,
        "p5_stage": P5_STAGE,
        "note": (
            "Full P5 headline compile (stage p5 / p5_headline profile stack "
            "with route=True). Two disjoint 12-case cohorts preserve frozen "
            "p5_audit + p5_headline_frozen.json under separate cohort dirs."
        ),
        "sweep": sweep,
        "comparison": {
            "w6_p5_throughput": (w6 or {}).get("p5_summary", {}).get(
                "throughput_cases_per_hour"
            ),
            "w12_p5_throughput": (w12 or {}).get("p5_summary", {}).get(
                "throughput_cases_per_hour"
            ),
            "w12_over_w6_throughput_ratio": (
                round(ratio, 3) if ratio is not None else None
            ),
            "parallel_efficiency_vs_ideal_2x": (
                round(ratio / 2.0, 3) if ratio is not None else None
            ),
        },
    }
    da._atomic_json(out_dir / "concurrency_manifest_p5_compile.json", manifest)
    print(json.dumps({
        "manifest": str((out_dir / "concurrency_manifest_p5_compile.json").relative_to(ROOT)),
        "comparison": manifest["comparison"],
        "exit_codes": {r["workers"]: r["exit_code"] for r in sweep},
    }, indent=2, ensure_ascii=False), flush=True)
    return 0 if all(r.get("exit_code") == 0 for r in sweep) else 1


if __name__ == "__main__":
    raise SystemExit(main())
