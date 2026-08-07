#!/usr/bin/env python3
"""Unified DiagnosisArena paper baseline runner.

Example:
  PYTHONPATH=src:scripts:scripts/paper python scripts/paper/run_baseline.py \\
    --arms B00-direct-cot,B01-cot-rag --limit 5 --dry-run --score

RAG arms (B01/B02/B11b/B16) default to spawn process pool concurrency:
each worker owns independent FAISS/retriever state, with OMP≤2.
"""
from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

# Cap native thread fan-out inside each process (CPU-path OpenMP explosion).
os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("MKL_NUM_THREADS", "2")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "2")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "2")
os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "2")
os.environ.setdefault("TREE_DX_EMBED_DEVICE", "cpu")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "paper"))

import baseline_arms as arms  # noqa: E402
import baseline_common as bc  # noqa: E402
import baseline_mapper_score as mapper_score  # noqa: E402

RAG_ARMS = frozenset({
    "B01-cot-rag",
    "B02-flat-matched-rerank",
    "B02-flat-compute-matched",
    "B02-flat-compute-matched-sc10",
    "B03-flat-beam",
    "B07-meddxagent-complete",
    "B11b-cod-prompt-shared-kb",
    "B14-candidate-flat-union",
    "A13-emulation-full-matrix",
    "B15-medprompt-style",
    "B16-medrag-kg",
    "B17-imedrag",
})


def _arm_sc_temperature(arm: str) -> float:
    """Self-consistency arms need T>0 so trajectories are not identical."""
    a = str(arm or "")
    if "sc-cot" in a or "sc10" in a or "-sc" in a:
        return 0.7
    return 0.0


DEFAULT_BUDGET_SCHEDULES = {
    "diagnosisarena": ROOT
    / "configs"
    / "paper_experiments"
    / "paper_v1_budget_schedule_diagnosisarena.jsonl",
    "open_xddx": ROOT
    / "configs"
    / "paper_experiments"
    / "paper_v1_budget_schedule_open_xddx.jsonl",
    "medcasereasoning": ROOT
    / "configs"
    / "paper_experiments"
    / "paper_v1_budget_schedule_medcasereasoning.jsonl",
}
DEFAULT_BUDGET_SCHEDULE = DEFAULT_BUDGET_SCHEDULES["diagnosisarena"]

GPU_ARMS = frozenset({
    "B11a-official-diagnosisgpt",
})

# Shared 17-case pipeline KB assets.
DEFAULT_RAG_INDEX = ROOT / "data" / "corpus" / "rag_index"
DEFAULT_CPG_INDEX = ROOT / "data" / "corpus" / "cpg_index"
DEFAULT_B11A_MODEL = (
    ROOT / "baselines" / "chain_of_diagnosis" / "models" / "DiagnosisGPT-6B"
)

# Per-process state for spawn workers.
_PROC: dict[str, Any] = {}


def _set_omp_threads(n: int) -> None:
    for key in (
        "OMP_NUM_THREADS",
        "MKL_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
    ):
        os.environ[key] = str(n)


def _build_cache(
    *,
    model: str,
    call_timeout: int,
    dry_run: bool,
    cache_path: Path,
    temperature: float = 0.0,
) -> bc.SimpleCachedLLM:
    client = None
    if not dry_run:
        from agentclinic_tree_dx.llm_client import RobustLLMClient

        client = RobustLLMClient(
            model=model,
            call_timeout=call_timeout,
            max_retries=5,
            timeout_retry_cap=2,
            temperature=temperature,
        )
    return bc.SimpleCachedLLM(client, cache_path, model)


def _build_retrievers(
    *,
    need_rag: bool,
    rag_index: Path,
    cpg_index: Path,
) -> dict[str, Any] | None:
    if not need_rag:
        return None
    from agentclinic_tree_dx.knowledge.rag_retriever import RAGRetriever

    retrievers: dict[str, Any] = {}
    if rag_index.is_dir():
        retrievers["rag_index"] = RAGRetriever(str(rag_index), device="cpu")
    if cpg_index.is_dir():
        retrievers["cpg_index"] = RAGRetriever(str(cpg_index), device="cpu")
    if not retrievers:
        raise FileNotFoundError(
            f"RAG required but no index found at {rag_index} or {cpg_index}"
        )
    return retrievers


def _load_candidate_pool(path: Path | None) -> dict[str, list[str]]:
    if path is None or not path.is_file():
        return {}
    doc = json.loads(path.read_text(encoding="utf-8"))
    pools: dict[str, list[str]] = {}
    if isinstance(doc, dict):
        if "cases" in doc and isinstance(doc["cases"], list):
            for row in doc["cases"]:
                pools[str(row["case_id"])] = [str(x) for x in (row.get("candidates") or [])]
        else:
            for key, value in doc.items():
                if isinstance(value, list):
                    pools[str(key)] = [str(x) for x in value]
    return pools


def _init_process_worker(
    model: str,
    call_timeout: int,
    dry_run: bool,
    need_rag: bool,
    cache_dir: str,
    rag_index: str,
    cpg_index: str,
    omp_threads: int,
    gpu_ids: list[int] | None = None,
    gpu_counter: Any = None,
    b11a_model_dir: str | None = None,
    preload_b11a: bool = False,
    temperature: float = 0.0,
) -> None:
    """Spawn initializer: each worker owns FAISS/retrievers + LLM client.

    For GPU arms, assign one physical GPU via CUDA_VISIBLE_DEVICES before any
    CUDA init, then preload DiagnosisGPT once per process.
    """
    _set_omp_threads(omp_threads)
    for path in (ROOT / "src", ROOT / "scripts", ROOT / "scripts" / "paper"):
        text = str(path)
        if text not in sys.path:
            sys.path.insert(0, text)

    gpu_id = None
    if gpu_ids and gpu_counter is not None:
        with gpu_counter.get_lock():
            idx = int(gpu_counter.value)
            gpu_counter.value = idx + 1
        gpu_id = int(gpu_ids[idx % len(gpu_ids)])
        os.environ["CUDA_VISIBLE_DEVICES"] = str(gpu_id)

    # Avoid inherited invalid allocator conf (must be >20 if set).
    # Accepts both max_split_size_mb:4 and max_split_size_mb=4 forms.
    conf = os.environ.get("PYTORCH_CUDA_ALLOC_CONF", "")
    if "max_split_size_mb" in conf:
        parts = []
        for item in conf.replace(":", "=").split(","):
            item = item.strip()
            if not item:
                continue
            if item.startswith("max_split_size_mb"):
                try:
                    val = int(item.split("=", 1)[1])
                except Exception:  # noqa: BLE001
                    val = 0
                if val <= 20:
                    continue
            parts.append(item)
        if parts:
            os.environ["PYTORCH_CUDA_ALLOC_CONF"] = ",".join(parts)
        else:
            os.environ.pop("PYTORCH_CUDA_ALLOC_CONF", None)

    cache_path = Path(cache_dir) / f"llm_worker_{os.getpid()}.json"
    # GPU arms do not need the API LLM client.
    _PROC["cache"] = _build_cache(
        model=model,
        call_timeout=call_timeout,
        dry_run=dry_run or preload_b11a,
        cache_path=cache_path,
        temperature=float(temperature or 0.0),
    )
    _PROC["retrievers"] = None
    if need_rag and not dry_run:
        _PROC["retrievers"] = _build_retrievers(
            need_rag=True,
            rag_index=Path(rag_index),
            cpg_index=Path(cpg_index),
        )
    _PROC["dry_run"] = dry_run
    _PROC["pid"] = os.getpid()
    _PROC["gpu_id"] = gpu_id
    _PROC["b11a_model_dir"] = b11a_model_dir
    if preload_b11a and not dry_run:
        vendor = ROOT / "baselines" / "chain_of_diagnosis"
        if str(vendor) not in sys.path:
            sys.path.insert(0, str(vendor))
        import adapter as cod_adapter  # noqa: WPS433

        cod_adapter.load_bot(b11a_model_dir)
        _PROC["b11a_ready"] = True


def _run_case_job(payload: dict[str, Any]) -> dict[str, Any]:
    """Picklable worker entrypoint for process pool."""
    import baseline_arms as arms_mod
    import baseline_common as bc_mod

    arm = payload["arm"]
    case = payload["case"]
    list_k = int(payload.get("list_k") or 2)
    runner = arms_mod.ARM_RUNNERS[arm]
    t0 = time.time()
    top2, trace, cost = runner(
        case,
        _PROC["cache"],
        dry_run=_PROC["dry_run"],
        retrievers=_PROC.get("retrievers"),
        candidate_pool=payload.get("candidate_pool"),
        sc_samples=payload.get("sc_samples", 5),
        model_dir=_PROC.get("b11a_model_dir"),
        list_k=list_k,
        budget_mode=payload.get("budget_mode") or "native",
        budget_schedule=payload.get("budget_schedule") or {},
        sc_seed_top=payload.get("sc_seed_top"),
        sc_seed_cost=payload.get("sc_seed_cost"),
    )
    wall_s = time.time() - t0
    if isinstance(cost, dict):
        cost = dict(cost)
        cost.setdefault("wall_s", wall_s)
    row = bc_mod.prediction_row(
        case,
        arm=arm,
        replicate=payload["replicate"],
        top2=top2,
        cost=cost,
        trace=trace,
        list_k=list_k,
    )
    return {
        "case_id": case["case_id"],
        "row": row,
        "trace": {
            "case_id": case["case_id"],
            "arm": arm,
            "trace": trace,
            "worker_pid": _PROC.get("pid"),
            "gpu_id": _PROC.get("gpu_id"),
            "wall_s": wall_s,
        },
        "cost": dict(cost) if isinstance(cost, dict) else cost,
        "worker_pid": _PROC.get("pid"),
        "gpu_id": _PROC.get("gpu_id"),
        "wall_s": wall_s,
    }


def _resolve_executor(arm: str, workers: int, requested: str) -> str:
    if requested != "auto":
        return requested
    if workers > 1 and arm in RAG_ARMS | GPU_ARMS:
        return "process"
    if arm in GPU_ARMS:
        # Single-worker GPU still benefits from process isolation.
        return "process"
    return "thread"


def run_arm(
    arm: str,
    cases: list[dict],
    args: argparse.Namespace,
) -> Path:
    out = bc.run_dir(arm, args.replicate, runs_root=args.runs_root)
    out.mkdir(parents=True, exist_ok=True)
    pred_path = out / "predictions.jsonl"
    trace_path = out / "trace.jsonl"
    if not args.resume:
        for path in (pred_path, trace_path):
            if path.exists():
                path.unlink()
    done = set()
    if args.resume and pred_path.is_file():
        for line in pred_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                done.add(json.loads(line)["case_id"])

    need_rag = arm in RAG_ARMS
    need_gpu = arm in GPU_ARMS
    pools = _load_candidate_pool(args.candidate_pool)
    pending = [case for case in cases if case["case_id"] not in done]
    workers = max(1, len(pending) if args.workers <= 0 else int(args.workers))
    list_k = int(getattr(args, "list_k", 2) or 2)
    budget_mode = str(getattr(args, "budget_mode", "native") or "native")
    if arm in ("B02-flat-compute-matched", "B02-flat-compute-matched-sc10"):
        budget_mode = "matched"
    sc_temp = _arm_sc_temperature(arm)
    sc_samples = int(getattr(args, "sc_samples", 5) or 5)
    if arm == "B02-flat-compute-matched-sc10":
        # CLI default is 5 (for B12); for this arm interpret default as 10.
        if not bool(getattr(args, "sc_samples_set", False)):
            sc_samples = 10
        sc_samples = max(1, sc_samples)

    seed_map: dict[str, dict[str, Any]] = {}
    seed_dir = getattr(args, "sc_seed_pred_dir", None)
    if seed_dir and arm == "B02-flat-compute-matched-sc10":
        seed_path = Path(seed_dir) / "predictions.jsonl"
        if seed_path.is_file():
            for line in seed_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                cid = str(row.get("case_id") or "")
                top = row.get("ordered_diagnoses") or row.get("top2_diagnoses") or []
                names: list[str] = []
                for item in top:
                    if isinstance(item, dict):
                        names.append(str(item.get("diagnosis") or "").strip())
                    else:
                        names.append(str(item).strip())
                names = [n for n in names if n]
                if cid and names:
                    seed_map[cid] = {
                        "top": names,
                        "cost": dict(row.get("cost") or {}),
                    }
            print(
                f"{arm}: sc_seed_pred_dir={seed_dir} n_seed={len(seed_map)} "
                f"sc_samples={sc_samples} temperature={sc_temp}",
                flush=True,
            )
    schedule_map: dict[str, dict] = {}
    schedule_path = getattr(args, "budget_schedule", None)
    if budget_mode == "matched":
        if schedule_path is None:
            ds_key = str(getattr(args, "dataset", "diagnosisarena") or "diagnosisarena")
            # normalize aliases
            if ds_key in ("ox",):
                ds_key = "open_xddx"
            elif ds_key in ("mcr",):
                ds_key = "medcasereasoning"
            elif ds_key in ("da",):
                ds_key = "diagnosisarena"
            schedule_path = DEFAULT_BUDGET_SCHEDULES.get(ds_key, DEFAULT_BUDGET_SCHEDULE)
        schedule_path = Path(schedule_path)
        if not schedule_path.is_file():
            raise FileNotFoundError(
                f"budget_mode=matched requires schedule file: {schedule_path}"
            )
        from build_budget_schedule import load_budget_schedule

        schedule_map = load_budget_schedule(schedule_path)
        print(
            f"{arm}: budget_mode=matched schedule={schedule_path} "
            f"n_keys={len(schedule_map)}",
            flush=True,
        )
    if need_gpu and args.gpu_ids:
        # Cap concurrency at available GPUs unless user forces more.
        workers = min(workers, len(args.gpu_ids)) if workers > 1 else workers
    executor = _resolve_executor(arm, workers, args.executor)
    costs: list[dict] = []
    errors: list[dict[str, str]] = []
    wall_started = time.time()

    print(
        f"{arm}: running {len(pending)} cases with workers={workers} "
        f"executor={executor} need_rag={need_rag} need_gpu={need_gpu} list_k={list_k}",
        flush=True,
    )
    if not pending:
        pass
    elif executor == "process":
        if workers > 1 and arm not in RAG_ARMS | GPU_ARMS:
            print(
                f"[warn] {arm}: process executor on non-RAG/non-GPU arm",
                flush=True,
            )
        cache_dir = out / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        ctx = mp.get_context(args.start_method)
        gpu_counter = ctx.Value("i", 0) if need_gpu else None
        gpu_ids = list(args.gpu_ids) if need_gpu else None
        payloads = [
            {
                "arm": arm,
                "case": case,
                "replicate": args.replicate,
                "candidate_pool": pools.get(case["case_id"])
                or pools.get(case["source_id"]),
                "sc_samples": sc_samples,
                "list_k": list_k,
                "budget_mode": budget_mode,
                "budget_schedule": schedule_map.get(case["case_id"])
                or schedule_map.get(case["source_id"])
                or {},
                "sc_seed_top": (seed_map.get(case["case_id"]) or {}).get("top"),
                "sc_seed_cost": (seed_map.get(case["case_id"]) or {}).get("cost"),
            }
            for case in pending
        ]
        if budget_mode == "matched":
            missing = [
                p["case"]["case_id"]
                for p in payloads
                if not p.get("budget_schedule")
            ]
            if missing:
                raise SystemExit(
                    f"{arm}: missing budget schedule for {len(missing)} cases "
                    f"(e.g. {missing[:5]})"
                )
        with ProcessPoolExecutor(
            max_workers=workers,
            mp_context=ctx,
            initializer=_init_process_worker,
            initargs=(
                args.model,
                args.call_timeout,
                args.dry_run,
                need_rag,
                str(cache_dir),
                str(args.rag_index),
                str(args.cpg_index),
                args.omp_threads,
                gpu_ids,
                gpu_counter,
                str(args.b11a_model_dir),
                need_gpu,
                sc_temp,
            ),
        ) as pool:
            futures = {
                pool.submit(_run_case_job, payload): payload["case"]["case_id"]
                for payload in payloads
            }
            for fut in as_completed(futures):
                case_id = futures[fut]
                try:
                    result = fut.result()
                    bc.append_jsonl(pred_path, result["row"])
                    bc.append_jsonl(trace_path, result["trace"])
                    costs.append(result["cost"])
                    print(
                        f"[ok] {arm} {case_id} pid={result.get('worker_pid')} "
                        f"gpu={result.get('gpu_id')} wall_s={result.get('wall_s'):.2f}",
                        flush=True,
                    )
                except Exception as exc:  # noqa: BLE001
                    errors.append(
                        {
                            "case_id": case_id,
                            "error": f"{type(exc).__name__}: {exc}",
                            "traceback": traceback.format_exc(),
                        }
                    )
                    print(f"[ERROR] {arm} {case_id}: {exc}", flush=True)
    else:
        cache = _build_cache(
            model=args.model,
            call_timeout=args.call_timeout,
            dry_run=args.dry_run,
            cache_path=out / "cache" / "llm.json",
            temperature=sc_temp,
        )
        retrievers = None
        if need_rag and not args.dry_run:
            retrievers = _build_retrievers(
                need_rag=True,
                rag_index=args.rag_index,
                cpg_index=args.cpg_index,
            )
        runner = arms.ARM_RUNNERS[arm]

        def _one(case: dict) -> dict:
            budget_row = (
                schedule_map.get(case["case_id"])
                or schedule_map.get(case["source_id"])
                or {}
            )
            if budget_mode == "matched" and not budget_row:
                raise KeyError(f"missing budget schedule for {case['case_id']}")
            seed = seed_map.get(case["case_id"]) or {}
            top2, trace, cost = runner(
                case,
                cache,
                dry_run=args.dry_run,
                retrievers=retrievers,
                candidate_pool=pools.get(case["case_id"]) or pools.get(case["source_id"]),
                sc_samples=sc_samples,
                list_k=list_k,
                budget_mode=budget_mode,
                budget_schedule=budget_row,
                sc_seed_top=seed.get("top"),
                sc_seed_cost=seed.get("cost"),
            )
            row = bc.prediction_row(
                case,
                arm=arm,
                replicate=args.replicate,
                top2=top2,
                cost=cost,
                trace=trace,
                list_k=list_k,
            )
            bc.append_jsonl(pred_path, row)
            bc.append_jsonl(
                trace_path,
                {
                    "case_id": case["case_id"],
                    "arm": arm,
                    "trace": trace,
                },
            )
            return dict(cost)

        if workers == 1:
            for case in pending:
                try:
                    costs.append(_one(case))
                    print(f"[ok] {arm} {case['case_id']}", flush=True)
                except Exception as exc:  # noqa: BLE001
                    errors.append(
                        {
                            "case_id": case["case_id"],
                            "error": f"{type(exc).__name__}: {exc}",
                            "traceback": traceback.format_exc(),
                        }
                    )
                    print(f"[ERROR] {arm} {case['case_id']}: {exc}", flush=True)
        else:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {pool.submit(_one, case): case for case in pending}
                for fut in as_completed(futures):
                    case = futures[fut]
                    try:
                        costs.append(fut.result())
                        print(f"[ok] {arm} {case['case_id']}", flush=True)
                    except Exception as exc:  # noqa: BLE001
                        errors.append(
                            {
                                "case_id": case["case_id"],
                                "error": f"{type(exc).__name__}: {exc}",
                                "traceback": traceback.format_exc(),
                            }
                        )
                        print(f"[ERROR] {arm} {case['case_id']}: {exc}", flush=True)

    wall_total = time.time() - wall_started
    if errors:
        bc.atomic_json(out / "errors.json", errors)
        print(f"{arm}: {len(errors)}/{len(pending)} cases failed", flush=True)

    all_pred_rows: list[dict] = []
    if pred_path.is_file():
        all_pred_rows = [
            json.loads(line)
            for line in pred_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    total_cost = bc.empty_cost()
    case_latencies: list[float] = []
    for row in all_pred_rows:
        cost = row.get("cost") or {}
        for key in total_cost:
            if key == "latency_s":
                total_cost[key] += float(cost.get(key) or 0.0)
            else:
                total_cost[key] += int(cost.get(key) or 0)
        if cost.get("latency_s") is not None:
            case_latencies.append(float(cost["latency_s"]))
        elif cost.get("wall_s") is not None:
            case_latencies.append(float(cost["wall_s"]))
    total_cost["wall_s"] = wall_total
    if case_latencies:
        total_cost["mean_case_latency_s"] = round(
            sum(case_latencies) / len(case_latencies), 3
        )
        total_cost["max_case_latency_s"] = round(max(case_latencies), 3)
        total_cost["min_case_latency_s"] = round(min(case_latencies), 3)
    bc.atomic_json(out / "cost.json", total_cost)
    worker_pids = sorted({
        int(json.loads(line).get("worker_pid"))
        for line in (trace_path.read_text(encoding="utf-8").splitlines() if trace_path.is_file() else [])
        if line.strip() and json.loads(line).get("worker_pid") is not None
    })
    gpu_ids_used = sorted({
        int(json.loads(line)["gpu_id"])
        for line in (trace_path.read_text(encoding="utf-8").splitlines() if trace_path.is_file() else [])
        if line.strip() and json.loads(line).get("gpu_id") is not None
    })
    dataset = str(getattr(args, "dataset", "diagnosisarena") or "diagnosisarena")
    list_k = int(getattr(args, "list_k", 2) or 2)
    if dataset == bc.DATASET_OPEN_XDDX:
        output_contract = "ordered_topk_diagnoses"
        scoring = "ox_mcr_official_eval"
    elif dataset in {bc.DATASET_MCR, bc.DATASET_RAREARENA}:
        output_contract = "ordered_top2_diagnoses"
        scoring = "ox_mcr_official_eval"
    else:
        output_contract = "ordered_top2_diagnoses"
        scoring = "RelationAwareAnswerMapper"
    bc.write_manifest(
        out,
        arm=arm,
        replicate=args.replicate,
        subset=args.subset_dir.name,
        model=args.model if not need_gpu else str(args.b11a_model_dir),
        budget_mode=budget_mode,
        extra={
            "dataset": dataset,
            "list_k": list_k,
            "output_contract": output_contract,
            "scoring": scoring,
            "pred_source": (
                "baseline_ordered_topk_v1"
                if dataset == bc.DATASET_OPEN_XDDX
                else "baseline_top2_v1"
            ),
            "budget_schedule": str(schedule_path) if budget_mode == "matched" else None,
            "matching_policy": "structural_proxy_v1" if budget_mode == "matched" else None,
            "dry_run": args.dry_run,
            "n_cases": len(cases),
            "n_ok": len(all_pred_rows),
            "n_error": len(errors),
            "n_ran_this_invocation": len(costs),
            "workers": workers,
            "executor": executor,
            "start_method": args.start_method if executor == "process" else None,
            "omp_num_threads": args.omp_threads if executor == "process" else None,
            "rag_index": str(args.rag_index) if need_rag else None,
            "cpg_index": str(args.cpg_index) if need_rag else None,
            "b11a_model_dir": str(args.b11a_model_dir) if need_gpu else None,
            "gpu_ids": gpu_ids_used,
            "worker_pids": worker_pids,
            "n_distinct_pids": len(worker_pids),
            "wall_s": round(wall_total, 3),
            "mean_case_latency_s": total_cost.get("mean_case_latency_s"),
            "max_case_latency_s": total_cost.get("max_case_latency_s"),
            "min_case_latency_s": total_cost.get("min_case_latency_s"),
        },
    )
    print(
        f"{arm}: wall_s={wall_total:.2f} "
        f"mean_case_s={total_cost.get('mean_case_latency_s')} "
        f"max_case_s={total_cost.get('max_case_latency_s')}",
        flush=True,
    )
    if args.score and dataset != bc.DATASET_DIAGNOSISARENA:
        print(
            f"{arm}: skip Mapper --score on dataset={dataset}; "
            "use scripts/paper/run_baseline_ox_mcr_eval.py",
            flush=True,
        )
    elif args.score and (out / "predictions.jsonl").is_file():
        summary = mapper_score.score_predictions_dir(
            out,
            cases,
            mode=args.mapper_mode,
            model=args.model,
            dry_run=args.dry_run or args.mapper_mode == "deterministic_gold_blind",
        )
        print(arm, json.dumps(summary))
    elif args.score:
        print(f"{arm}: skip scoring (no predictions.jsonl)", flush=True)
    return out


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--arms",
        default="B00-direct-cot",
        help="comma-separated arm ids",
    )
    parser.add_argument(
        "--dataset",
        default="diagnosisarena",
        choices=(
            "diagnosisarena", "open_xddx", "medcasereasoning", "rarearena",
            "ox", "mcr", "ra", "da",
        ),
    )
    parser.add_argument("--subset-dir", type=Path, default=None)
    parser.add_argument("--runs-root", type=Path, default=None)
    parser.add_argument("--replicate", type=int, default=1)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--case-ids", default="", help="comma-separated source ids")
    parser.add_argument(
        "--list-k",
        type=int,
        default=0,
        help="ordered diagnosis list length (0=dataset default: DA/MCR=2, OX=5)",
    )
    parser.add_argument("--model", default="meta-llama/llama-3.3-70b-instruct")
    parser.add_argument("--call-timeout", type=int, default=240)
    parser.add_argument("--budget-mode", default="native", choices=("native", "matched"))
    parser.add_argument(
        "--budget-schedule",
        type=Path,
        default=None,
        help="jsonl from build_budget_schedule.py (required for matched / B02-flat-compute-matched)",
    )
    parser.add_argument(
        "--mapper-mode",
        default="deterministic_gold_blind",
        choices=(
            "deterministic_gold_blind",
            "typed_llm",
            "typed_llm_disagreement_rag",
        ),
    )
    parser.add_argument("--sc-samples", type=int, default=5)
    parser.add_argument(
        "--sc-seed-pred-dir",
        type=Path,
        default=None,
        help="Reuse ordered diagnoses from an existing B02 matched replicate as SC sample 0",
    )
    parser.add_argument("--candidate-pool", type=Path, default=None)
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="parallel case workers; <=0 means one worker per pending case",
    )
    parser.add_argument(
        "--executor",
        default="auto",
        choices=("auto", "thread", "process"),
        help="auto: spawn process pool for RAG arms when workers>1",
    )
    parser.add_argument(
        "--start-method",
        default="spawn",
        choices=("spawn", "fork", "forkserver"),
    )
    parser.add_argument(
        "--omp-threads",
        type=int,
        default=2,
        help="OMP/MKL/OpenBLAS threads per process (default 2)",
    )
    parser.add_argument("--rag-index", type=Path, default=DEFAULT_RAG_INDEX)
    parser.add_argument("--cpg-index", type=Path, default=DEFAULT_CPG_INDEX)
    parser.add_argument(
        "--b11a-model-dir",
        type=Path,
        default=DEFAULT_B11A_MODEL,
        help="local DiagnosisGPT weights for B11a",
    )
    parser.add_argument(
        "--gpu-ids",
        default="0,1,2",
        help="comma-separated physical GPU ids for GPU arms (default 0,1,2)",
    )
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--score", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    args.sc_samples_set = any(
        a == "--sc-samples" or a.startswith("--sc-samples=") for a in sys.argv[1:]
    )
    args.gpu_ids = [int(x.strip()) for x in str(args.gpu_ids).split(",") if x.strip()]
    args.dataset = bc.normalize_dataset(args.dataset)
    if args.subset_dir is None:
        args.subset_dir = bc.default_subset_for(args.dataset)
    if args.runs_root is None:
        args.runs_root = bc.default_runs_root_for(args.dataset)
    list_k = int(args.list_k or 0)
    if list_k <= 0:
        list_k = bc.default_list_k_for(args.dataset)
    args.list_k = bc.validate_list_k(args.dataset, list_k)
    if args.score and args.dataset != bc.DATASET_DIAGNOSISARENA:
        raise SystemExit(
            "--score (Mapper) is only for diagnosisarena; "
            "use run_baseline_ox_mcr_eval.py for OX/MCR"
        )
    return args


def main() -> int:
    args = parse_args()
    _set_omp_threads(args.omp_threads)
    selected = [item.strip() for item in args.arms.split(",") if item.strip()]
    unknown = [arm for arm in selected if arm not in arms.ARM_RUNNERS]
    if unknown:
        raise SystemExit(f"unknown arms: {unknown}; known={sorted(arms.ARM_RUNNERS)}")
    case_ids = [x.strip() for x in args.case_ids.split(",") if x.strip()]
    cases = bc.load_runtime_cases(
        subset_dir=args.subset_dir,
        case_ids=case_ids,
        limit=args.limit,
        dataset=args.dataset,
    )
    print(
        f"loaded {len(cases)} cases from {args.subset_dir} "
        f"dataset={args.dataset} list_k={args.list_k}"
    )
    for arm in selected:
        if arm in RAG_ARMS:
            print(
                f"[kb] {arm} uses shared indices: "
                f"rag={args.rag_index} cpg={args.cpg_index}",
                flush=True,
            )
        if arm in GPU_ARMS:
            print(
                f"[gpu] {arm} model={args.b11a_model_dir} gpus={args.gpu_ids}",
                flush=True,
            )
        print(f"=== {arm} ===")
        run_arm(arm, cases, args)
    return 0


if __name__ == "__main__":
    # Required for spawn on some platforms.
    mp.freeze_support()
    raise SystemExit(main())
