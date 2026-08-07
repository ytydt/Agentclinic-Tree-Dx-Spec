#!/usr/bin/env python3
"""DiagnosisArena build-trees stress via process pool (segfault-safe concurrency).

Why process pool (vs thread pool + global FAISS/encode locks):
  * Each worker process owns its own FAISS / encoder / controller state.
  * No cross-thread IndexIVFPQ.search → avoids the §30 segfault class.
  * Controller is built once per process (initializer), not once per job.

Protocol for this feasibility probe:
  * Fixed oversample to 12 jobs from the signed-off 5-case freeze.
  * Grid: workers=6 and workers=12 (same 12 jobs → saturated comparison).
  * Live VignetteParser stays off; evidence from freeze only.

Usage:
  PYTHONPATH=src:scripts/paper:scripts python3 -u \\
    scripts/paper/run_diagnosisarena_stress_process_pool.py \\
    --workers 6,12 --fixed-jobs 12
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

# Cap native thread fan-out inside each process (CPU-path OpenMP explosion).
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

DEFAULT_CASES_JSON = (
    ROOT / "logs" / "diagnosisarena_d2_m01_v1" / "normalized_cases.json"
)
DEFAULT_FREEZE = (
    ROOT / "logs" / "diagnosisarena_d2_m01_v1" / "vignette_parser_probe_v2"
    / "vignette_parser_frozen_v2.json"
)
DEFAULT_OUT = (
    ROOT / "logs" / "diagnosisarena_d2_m01_v1" / "stress_process_pool_v1"
)
DEFAULT_MODEL = "meta-llama/llama-3.3-70b-instruct"
BRANCH_SCRIPT = ROOT / "scripts" / "eval_branch_creation_medbullets.py"

# Per-process state filled by initializer.
_PROC: dict[str, Any] = {}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _base_case_id(case_id: str) -> str:
    text = str(case_id)
    if "__s" in text:
        head, tail = text.rsplit("__s", 1)
        if tail.isdigit():
            return head
    return text


def _oversample_fixed(
    cases: Sequence[Mapping[str, Any]],
    n_jobs: int,
) -> list[dict[str, Any]]:
    base = [dict(case) for case in cases]
    if not base:
        raise ValueError("no probe cases")
    jobs: list[dict[str, Any]] = []
    for index in range(max(1, int(n_jobs))):
        src = base[index % len(base)]
        job = dict(src)
        job["source_case_id"] = str(src["id"])
        job["id"] = "%s__s%02d" % (src["id"], index + 1)
        jobs.append(job)
    return jobs


def _load_branch_module():
    spec = importlib.util.spec_from_file_location(
        "da_stress_proc_branch", BRANCH_SCRIPT,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot import %s" % BRANCH_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _init_worker(model: str, freeze_path: str) -> None:
    """Build one controller + freeze catalog per process (not per job)."""
    branch = _load_branch_module()
    controller, env, _, provenance = branch.build_controller(
        model,
        branch_mode="recall_hints_gap",
        config_overrides={
            "talp_disc_profile": "off",
            "force_expand_all_l1": True,
        },
    )
    freeze = da.load_vignette_parser_freeze(freeze_path)
    _PROC.clear()
    _PROC.update({
        "branch": branch,
        "controller": controller,
        "env": env,
        "provenance": provenance,
        "freeze": freeze,
        "model": model,
        "pid": os.getpid(),
    })
    print(
        "[proc-init] pid=%s freeze_cases=%d" % (os.getpid(), len(freeze)),
        flush=True,
    )


def _run_one_job(job_payload: Mapping[str, Any]) -> dict[str, Any]:
    """Execute a single oversampled build-trees job inside a worker process."""
    started_all = time.monotonic()
    case = dict(job_payload["case"])
    tree_path = Path(job_payload["tree_path"])
    fingerprint = job_payload["fingerprint"]
    try:
        controller = _PROC["controller"]
        env = _PROC["env"]
        branch = _PROC["branch"]
        freeze = _PROC["freeze"]
        provenance = _PROC["provenance"]

        base_id = _base_case_id(str(case.get("source_case_id") or case["id"]))
        if base_id not in freeze:
            raise RuntimeError("missing freeze for %s" % base_id)

        def _prepare(state) -> None:
            state.case_id = base_id
            da.apply_frozen_vignette_parser_fields(state, case, freeze[base_id])

        started = time.monotonic()
        state = branch.run_case_branches(
            controller,
            env,
            str(case["case_text"]),
            parse_vignette=False,
            prepare_state=_prepare,
        )
        state.case_id = base_id
        state.max_tree_depth = 2
        n_findings = len(state.static_evidence_items or ())
        expansion = controller.force_expand_all_l1(state)
        if expansion.get("l1_expansion_rate") != 1.0:
            raise RuntimeError("%s incomplete L1 expansion" % case["id"])
        payload = {
            "run_fingerprint": fingerprint,
            "tree_hash": "",
            "state": composed._serialize_state(
                state, (provenance or {}).get("last") or {},
            ),
            "expansion": expansion,
            "n_static_evidence_items": n_findings,
            "evidence_source": "vignette_parser_freeze_v2",
            "executor": "process_pool",
            "worker_pid": os.getpid(),
            "duration_seconds": round(time.monotonic() - started, 3),
            "wall_including_queue_seconds": round(
                time.monotonic() - started_all, 3
            ),
        }
        if not payload["state"].get("static_evidence_items"):
            raise RuntimeError("%s: empty static_evidence_items" % case["id"])
        payload["tree_hash"] = stable_hash(payload["state"]["branches"])
        da._atomic_json(tree_path, payload)
        return {
            "case_id": case["id"],
            "base_case_id": base_id,
            "status": "OK",
            "n_findings": n_findings,
            "duration_seconds": payload["duration_seconds"],
            "worker_pid": os.getpid(),
        }
    except Exception as exc:  # noqa: BLE001 — surface per-job
        return {
            "case_id": str(case.get("id")),
            "base_case_id": _base_case_id(
                str(case.get("source_case_id") or case.get("id") or "")
            ),
            "status": "ERROR",
            "error": "%s: %s" % (type(exc).__name__, exc),
            "traceback": traceback.format_exc()[-2000:],
            "worker_pid": os.getpid(),
            "duration_seconds": round(time.monotonic() - started_all, 3),
        }


def _load_probe_cases(
    cases_json: Path,
    case_ids: Sequence[str],
) -> list[dict[str, Any]]:
    doc = json.loads(cases_json.read_text(encoding="utf-8"))
    wanted = {str(x).strip() for x in case_ids if str(x).strip()}
    cases = [
        case for case in doc.get("cases") or ()
        if not wanted or str(case["id"]) in wanted
    ]
    if wanted:
        missing = sorted(wanted - {str(c["id"]) for c in cases})
        if missing:
            raise ValueError("unknown case ids: %s" % missing)
    if not cases:
        raise ValueError("no cases selected")
    return cases


def run_one_setting(
    *,
    jobs: Sequence[Mapping[str, Any]],
    workers: int,
    model: str,
    freeze_path: Path,
    tree_dir: Path,
    fingerprint: str,
) -> dict[str, Any]:
    tree_dir.mkdir(parents=True, exist_ok=True)
    for path in tree_dir.glob("*.json"):
        if path.name != "summary.json":
            path.unlink()

    payloads = [
        {
            "case": dict(job),
            "tree_path": str(tree_dir / ("%s.json" % job["id"])),
            "fingerprint": fingerprint,
        }
        for job in jobs
    ]

    records: list[dict[str, Any]] = []
    started = time.monotonic()
    # Processes must be forked/spawned with initializer; 'spawn' is safest
    # across FAISS/torch native state.
    with ProcessPoolExecutor(
        max_workers=workers,
        initializer=_init_worker,
        initargs=(model, str(freeze_path)),
    ) as pool:
        futures = {
            pool.submit(_run_one_job, payload): payload["case"]["id"]
            for payload in payloads
        }
        done = 0
        for future in as_completed(futures):
            job_id = futures[future]
            try:
                row = future.result()
            except Exception as exc:  # noqa: BLE001
                row = {
                    "case_id": job_id,
                    "status": "ERROR",
                    "error": "%s: %s" % (type(exc).__name__, exc),
                }
            records.append(row)
            done += 1
            print(
                "[proc-pool/w%d] %d/%d %s %s"
                % (workers, done, len(jobs), row.get("case_id"), row.get("status")),
                flush=True,
            )
    wall = time.monotonic() - started
    n_ok = sum(1 for row in records if row.get("status") == "OK")
    n_err = len(records) - n_ok
    durs = [
        float(row["duration_seconds"])
        for row in records
        if row.get("status") == "OK" and row.get("duration_seconds") is not None
    ]
    pids = sorted({
        int(row["worker_pid"])
        for row in records
        if row.get("worker_pid") is not None
    })
    return {
        "workers": workers,
        "executor": "process_pool",
        "probe_unique_cases": len({
            _base_case_id(str(job.get("source_case_id") or job["id"]))
            for job in jobs
        }),
        "probe_jobs": len(jobs),
        "oversampled": True,
        "fixed_jobs": len(jobs),
        "wall_seconds": round(wall, 3),
        "exit_code": 0 if n_err == 0 else 1,
        "n_ok": n_ok,
        "n_error": n_err,
        "throughput_jobs_per_hour": (
            round(len(jobs) / wall * 3600.0, 3) if wall > 0 else None
        ),
        "mean_job_seconds": (
            round(sum(durs) / len(durs), 3) if durs else None
        ),
        "max_job_seconds": round(max(durs), 3) if durs else None,
        "worker_pids": pids,
        "n_distinct_pids": len(pids),
        "job_ids": [job["id"] for job in jobs],
        "errors": [row for row in records if row.get("status") != "OK"],
        "records": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases-json", type=Path, default=DEFAULT_CASES_JSON)
    parser.add_argument("--vignette-freeze", type=Path, default=DEFAULT_FREEZE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--cases", default="3,4,5,7,11")
    parser.add_argument("--fixed-jobs", type=int, default=12)
    parser.add_argument("--workers", default="6,12")
    parser.add_argument(
        "--start-method",
        default="spawn",
        choices=["spawn", "fork", "forkserver"],
        help="multiprocessing start method (spawn recommended with FAISS/torch)",
    )
    args = parser.parse_args()

    import multiprocessing as mp
    try:
        mp.set_start_method(args.start_method, force=True)
    except RuntimeError:
        pass

    out_dir = args.output_dir.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    freeze_path = args.vignette_freeze.expanduser().resolve()
    if not freeze_path.is_file():
        raise FileNotFoundError(freeze_path)

    case_ids = [t.strip() for t in args.cases.split(",") if t.strip()]
    probe_cases = _load_probe_cases(args.cases_json, case_ids)
    jobs = _oversample_fixed(probe_cases, args.fixed_jobs)
    grid = [int(t) for t in args.workers.split(",") if t.strip()]

    fingerprint = stable_hash({
        "phase": "stress-process-pool",
        "branch_mode": "recall_hints_gap",
        "model": args.model,
        "fixed_jobs": args.fixed_jobs,
        "vignette_freeze": str(freeze_path.relative_to(ROOT)),
        "executor": "process_pool",
    })

    sweep = []
    for workers in grid:
        print(
            "\n=== process-pool stress workers=%d jobs=%d ==="
            % (workers, len(jobs)),
            flush=True,
        )
        tree_dir = out_dir / ("trees_w%d" % workers)
        row = run_one_setting(
            jobs=jobs,
            workers=workers,
            model=args.model,
            freeze_path=freeze_path,
            tree_dir=tree_dir,
            fingerprint=fingerprint,
        )
        sweep.append(row)
        da._atomic_json(out_dir / ("sweep_w%d.json" % workers), row)
        print(json.dumps({
            k: row[k] for k in row if k not in {"records", "errors", "job_ids"}
        }, indent=2), flush=True)

    viable = [row for row in sweep if row["exit_code"] == 0]
    best = max(
        viable or sweep,
        key=lambda row: (
            float(row.get("throughput_jobs_per_hour") or 0.0),
            -int(row["workers"]),
        ),
    )
    # Feasibility: no errors, and w12 not catastrophically worse than w6
    # (<50% of w6 throughput ⇒ not feasible to raise concurrency).
    w6 = next((r for r in sweep if r["workers"] == 6), None)
    w12 = next((r for r in sweep if r["workers"] == 12), None)
    feasibility = {
        "w6_ok": bool(w6 and w6["exit_code"] == 0),
        "w12_ok": bool(w12 and w12["exit_code"] == 0),
        "w6_throughput": (w6 or {}).get("throughput_jobs_per_hour"),
        "w12_throughput": (w12 or {}).get("throughput_jobs_per_hour"),
    }
    if w6 and w12 and w6.get("throughput_jobs_per_hour") and w12.get(
        "throughput_jobs_per_hour"
    ):
        ratio = (
            float(w12["throughput_jobs_per_hour"])
            / float(w6["throughput_jobs_per_hour"])
        )
        feasibility["w12_over_w6_throughput_ratio"] = round(ratio, 3)
        feasibility["w12_feasible_vs_w6"] = bool(
            w12["exit_code"] == 0 and ratio >= 0.85
        )
        # Ideal linear for same 12 jobs: w12 should be ~2x w6 if perfect
        feasibility["w12_over_w6_ideal_ratio"] = 2.0
        feasibility["parallel_efficiency_w12_vs_w6"] = round(ratio / 2.0, 3)

    # Compare to prior thread-pool saturated sweep if present.
    thread_manifest = (
        ROOT / "logs" / "diagnosisarena_d2_m01_v1" / "concurrency_manifest.json"
    )
    thread_cmp = None
    if thread_manifest.is_file():
        prior = json.loads(thread_manifest.read_text(encoding="utf-8"))
        thread_cmp = {
            "path": str(thread_manifest.relative_to(ROOT)),
            "note": (
                "Prior thread-pool sweep used different job counts per "
                "worker; compare jobs/hour cautiously"
            ),
            "thread_rows": [
                {
                    "workers": row.get("workers"),
                    "probe_jobs": row.get("probe_jobs"),
                    "throughput_jobs_per_hour": row.get(
                        "throughput_jobs_per_hour"
                    ),
                }
                for row in prior.get("sweep") or ()
                if int(row.get("workers") or 0) in {6, 12}
            ],
        }

    manifest = {
        "schema_version": 1,
        "asset_kind": "diagnosisarena_stress_process_pool_v1",
        "created_at": _utc_now(),
        "executor": "process_pool",
        "start_method": args.start_method,
        "segfault_mitigation": (
            "per-process FAISS/encoder/controller; no shared IndexIVFPQ "
            "across threads; OMP/MKL threads capped at 2"
        ),
        "fixed_jobs": args.fixed_jobs,
        "probe_case_ids": [c["id"] for c in probe_cases],
        "job_ids": [j["id"] for j in jobs],
        "worker_grid": grid,
        "selected_workers": int(best["workers"]),
        "feasibility": feasibility,
        "thread_pool_reference": thread_cmp,
        "sweep": [
            {k: v for k, v in row.items() if k != "records"}
            for row in sweep
        ],
        "best_row": {k: v for k, v in best.items() if k != "records"},
    }
    da._atomic_json(out_dir / "concurrency_manifest_process_pool.json", manifest)
    print(json.dumps({
        k: manifest[k]
        for k in (
            "executor", "fixed_jobs", "worker_grid", "selected_workers",
            "feasibility",
        )
    }, indent=2, ensure_ascii=False))
    print(
        "wrote",
        (out_dir / "concurrency_manifest_process_pool.json").relative_to(ROOT),
        flush=True,
    )
    return 0 if all(row["exit_code"] == 0 for row in sweep) else 1


if __name__ == "__main__":
    raise SystemExit(main())
