#!/usr/bin/env python3
"""DiagnosisArena D2: M01-aligned 17-case pipeline + frozen P5 compiler injection.

Decision (why reuse the 17-case scripts rather than a bespoke end-to-end runner):
  * L2 Config A, F6 freeze, joint A3, and replicate workers already exist and are
    fingerprint-locked; a second runner would drift.
  * The sole intentional delta vs M01 is ``compiler_rules_injected=true`` using a
    freshly frozen per-case ``p5_headline`` disc_audit (stage p5, not p7).
  * Evidence comes from a signed-off VignetteParser freeze (no live parse).
  * Stress grid starts at workers=3 (17-case default), then probes 6/9/12.
  * Main-pipeline LLM ``output_cap`` remains the production default (1024).

Phases:
  prepare | build-trees | build-findings | compile-p5 | stress
  run-l1 | freeze-l1 | generate-l2 | joint | mapper | all
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import statistics
import sys
import time
from concurrent.futures import (
    ProcessPoolExecutor,
    ThreadPoolExecutor,
    as_completed,
)
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
os.environ.setdefault("TREE_DX_USE_PROXY", "1")
os.environ.setdefault("TREE_DX_EMBED_DEVICE", "cpu")
os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("MKL_NUM_THREADS", "2")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "2")

import diagnosisarena_adapter as da  # noqa: E402
import eval_branch_talp_composed as composed  # noqa: E402
import eval_l1_evidence_bfs as bfs_eval  # noqa: E402
import eval_l2_branch_generation_ab as l2_ab  # noqa: E402
import eval_l2_competition_strategies as competition  # noqa: E402
from agentclinic_tree_dx.answer_projection_mapper import (  # noqa: E402
    RelationAwareAnswerMapper,
    leaf_rows_from_tree,
    load_offline_resolver,
)
from agentclinic_tree_dx.l1_evidence_bfs import stable_hash  # noqa: E402
from agentclinic_tree_dx.llm_client import RobustLLMClient  # noqa: E402

DEFAULT_PARQUET = (
    ROOT / "data" / "benchmarks" / "diagnosisarena" / "subsets"
    / "d2_seq100_v1" / "cases.parquet"
)
DEFAULT_OUT = ROOT / "logs" / "diagnosisarena_d2_m01_v1"
DEFAULT_MODEL = "meta-llama/llama-3.3-70b-instruct"
DEFAULT_VIGNETTE_FREEZE = (
    DEFAULT_OUT / "vignette_parser_probe_v3" / "vignette_parser_frozen_v3.json"
)
_LEGACY_VIGNETTE_FREEZE = (
    DEFAULT_OUT / "vignette_parser_probe_v2" / "vignette_parser_frozen_v2.json"
)
BRANCH_SCRIPT = ROOT / "scripts" / "eval_branch_creation_medbullets.py"
TALP_SCRIPT = ROOT / "scripts" / "eval_talp_discrimination.py"
PROMPT_DIR = ROOT / "src" / "agentclinic_tree_dx" / "prompts"
P5_STAGE = "p5"  # matches frozen p5_headline, not p7
FIXED_L1_BUDGET = 6  # M01 F6 freeze without gold-selected n*


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_json(path: Path, payload: Any) -> None:
    da._atomic_json(path, payload)


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot import %s" % path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _out(args: argparse.Namespace) -> Path:
    return Path(args.output_dir).expanduser().resolve()


def _cases_path(args: argparse.Namespace) -> Path:
    return _out(args) / "normalized_cases.json"


def _tree_dir(args: argparse.Namespace) -> Path:
    return _out(args) / "shared_trees"


def _fixture_path(args: argparse.Namespace) -> Path:
    return _out(args) / "finding_fixture_v1.json"


def _vignette_freeze_path(args: argparse.Namespace) -> Path:
    path = getattr(args, "vignette_freeze", None)
    if path:
        return Path(path).expanduser().resolve()
    preferred = Path(DEFAULT_VIGNETTE_FREEZE).expanduser().resolve()
    if preferred.is_file():
        return preferred
    legacy = Path(_LEGACY_VIGNETTE_FREEZE).expanduser().resolve()
    if legacy.is_file():
        return legacy
    return preferred


def _load_vignette_freeze(args: argparse.Namespace) -> dict[str, dict[str, Any]]:
    return da.load_vignette_parser_freeze(_vignette_freeze_path(args))


def _p5_arm_path(args: argparse.Namespace) -> Path:
    return _out(args) / "p5_headline_frozen.json"


def _competition_dir(args: argparse.Namespace) -> Path:
    return _out(args) / "l2_competition"


def _l2_gen_dir(args: argparse.Namespace) -> Path:
    return _out(args) / "l2_branch_generation_a"


def _joint_dir(args: argparse.Namespace) -> Path:
    return _out(args) / "l2_joint_dynamic"


def _load_cases(args: argparse.Namespace) -> list[dict[str, Any]]:
    path = _cases_path(args)
    if not path.is_file() or args.refresh_cases:
        selector = [
            token.strip()
            for token in (args.cases or "").split(",")
            if token.strip()
        ]
        cases = da.load_subset_cases(
            args.parquet, case_ids=selector, limit=args.limit,
        )
        da.write_normalized_cases(cases, path)
    else:
        cases = list(json.loads(path.read_text(encoding="utf-8"))["cases"])
        if args.cases:
            wanted = {
                token.strip()
                for token in args.cases.split(",") if token.strip()
            }
            cases = [case for case in cases if case["id"] in wanted]
        if args.limit > 0:
            cases = cases[: args.limit]
    return cases


def cmd_prepare(args: argparse.Namespace) -> int:
    cases = _load_cases(args)
    manifest = {
        "schema_version": 1,
        "prepared_at": _utc_now(),
        "n_cases": len(cases),
        "case_ids": [case["id"] for case in cases],
        "pipeline": "m01_anti_anchor_plus_p5_compiler",
        "intentional_delta_vs_talp17": "compiler_rules_injected=true",
        "l1_preset": "p5_anti_anchor_direct",
        "l1_freeze_budget": FIXED_L1_BUDGET,
        "p5_stage": P5_STAGE,
        "l2": "config_a + A3-joint-primary",
    }
    _atomic_json(_out(args) / "prepare_manifest.json", manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


def cmd_build_trees(args: argparse.Namespace) -> int:
    executor = getattr(args, "executor", "thread")
    if executor == "process":
        return _cmd_build_trees_process(args)
    stress_jobs = getattr(args, "_stress_jobs", None)
    cases = list(stress_jobs) if stress_jobs else _load_cases(args)
    freeze = _load_vignette_freeze(args)
    missing = sorted({
        _base_case_id(str(case.get("source_case_id") or case["id"]))
        for case in cases
        if _base_case_id(str(case.get("source_case_id") or case["id"])) not in freeze
    })
    if missing:
        raise RuntimeError(
            "vignette freeze missing cases %s (path=%s)"
            % (missing, _vignette_freeze_path(args))
        )
    tree_dir = _tree_dir(args)
    tree_dir.mkdir(parents=True, exist_ok=True)
    branch = _load_module("da_m01_branch", BRANCH_SCRIPT)
    fingerprint = stable_hash({
        "phase": "build-trees",
        "branch_mode": "recall_hints_gap",
        "model": args.model,
        "n_cases": len(cases),
        # Live VignetteParser is disabled; inject signed-off freeze only.
        "evidence_extractor": "diagnosisarena_vignette_parser_freeze_v2",
        "evidence_before_branches": True,
        "align_talp17_order": True,
        "vignette_freeze": str(_vignette_freeze_path(args).relative_to(ROOT)),
        "vignette_freeze_hash": stable_hash({
            cid: freeze[cid].get("evidence_items") for cid in sorted(freeze)
        }),
    })

    def _one(case: Mapping[str, Any]) -> dict[str, Any]:
        path = tree_dir / f"{case['id']}.json"
        if args.resume and path.is_file():
            existing = json.loads(path.read_text(encoding="utf-8"))
            if existing.get("run_fingerprint") == fingerprint:
                n_ev = len(
                    (existing.get("state") or {}).get("static_evidence_items")
                    or ()
                )
                if n_ev > 0:
                    return {"case_id": case["id"], "status": "REUSED"}
        controller, env, _, provenance = branch.build_controller(
            args.model,
            branch_mode="recall_hints_gap",
            config_overrides={
                "talp_disc_profile": "off",
                "force_expand_all_l1": True,
            },
        )
        started = time.monotonic()
        base_id = _base_case_id(str(case.get("source_case_id") or case["id"]))

        def _prepare(state) -> None:
            state.case_id = base_id
            da.apply_frozen_vignette_parser_fields(state, case, freeze[base_id])

        # ``case_text`` still carries the MCQ stem + Options block, i.e. the gold
        # answer verbatim. Baselines and the option mapper both read
        # ``da.vignette_body()`` instead, so leaving it in makes tree building an
        # unequal-input comparison. Default stays False to reproduce prior runs.
        case_text = str(case["case_text"])
        if getattr(args, "strip_mcq_options", False):
            case_text = da.vignette_body(case_text) or case_text
        state = branch.run_case_branches(
            controller,
            env,
            case_text,
            parse_vignette=False,
            prepare_state=_prepare,
        )
        state.case_id = base_id
        state.max_tree_depth = 2
        n_findings = len(state.static_evidence_items or ())
        expansion = controller.force_expand_all_l1(state)
        if expansion.get("l1_expansion_rate") != 1.0:
            raise RuntimeError(
                "%s incomplete L1 expansion" % case["id"]
            )
        payload = {
            "run_fingerprint": fingerprint,
            "tree_hash": "",
            "state": composed._serialize_state(
                state, (provenance or {}).get("last") or {},
            ),
            "expansion": expansion,
            "n_static_evidence_items": n_findings,
            "evidence_source": "vignette_parser_freeze_v2",
            "duration_seconds": round(time.monotonic() - started, 3),
        }
        if not payload["state"].get("static_evidence_items"):
            raise RuntimeError("%s: empty static_evidence_items" % case["id"])
        payload["tree_hash"] = stable_hash(payload["state"]["branches"])
        _atomic_json(path, payload)
        return {
            "case_id": case["id"],
            "status": "OK",
            "n_findings": n_findings,
            "duration_seconds": payload["duration_seconds"],
        }

    records = _map_workers(cases, _one, args.workers, "build-trees")
    summary = {
        "phase": "build-trees",
        "workers": args.workers,
        "evidence_source": "vignette_parser_freeze_v2",
        "vignette_freeze": str(_vignette_freeze_path(args).relative_to(ROOT)),
        "live_vignette_parser": False,
        "ok": sum(row.get("status") in {"OK", "REUSED"} for row in records),
        "errors": [row for row in records if row.get("status") == "ERROR"],
    }
    _atomic_json(tree_dir / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not summary["errors"] else 1


def _cmd_build_trees_process(args: argparse.Namespace) -> int:
    """Spawn process-pool build-trees (independent FAISS per process)."""
    import multiprocessing as mp

    try:
        mp.set_start_method(getattr(args, "start_method", "spawn"), force=True)
    except RuntimeError:
        pass

    stress = _load_module(
        "da_m01_p5_stress",
        ROOT / "scripts" / "paper" / "run_diagnosisarena_stress_p5_compile.py",
    )
    stress_jobs = getattr(args, "_stress_jobs", None)
    cases = list(stress_jobs) if stress_jobs else _load_cases(args)
    freeze_path = _vignette_freeze_path(args)
    freeze = da.load_vignette_parser_freeze(freeze_path)
    missing = sorted({
        _base_case_id(str(case.get("source_case_id") or case["id"]))
        for case in cases
        if _base_case_id(str(case.get("source_case_id") or case["id"])) not in freeze
    })
    if missing:
        raise RuntimeError(
            "vignette freeze missing cases %s (path=%s)"
            % (missing, freeze_path)
        )
    tree_dir = _tree_dir(args)
    tree_dir.mkdir(parents=True, exist_ok=True)
    fingerprint = stable_hash({
        "phase": "build-trees",
        "branch_mode": "recall_hints_gap",
        "model": args.model,
        "n_cases": len(cases),
        "evidence_extractor": "diagnosisarena_vignette_parser_freeze_v3",
        "vignette_freeze": str(freeze_path.relative_to(ROOT)),
        "executor": "process",
    })
    workers = args.workers if args.workers > 0 else min(12, len(cases))
    payloads = [
        {
            "case": dict(case),
            "tree_path": str(tree_dir / ("%s.json" % case["id"])),
            "fingerprint": fingerprint,
            "resume": bool(args.resume),
        }
        for case in cases
    ]
    records = stress._map_process(
        payloads,
        workers=workers,
        initializer=stress._init_tree_worker,
        initargs=(args.model, str(freeze_path)),
        worker_fn=stress._run_tree_job,
        label="build-trees/process",
    )
    summary = {
        "phase": "build-trees",
        "workers": workers,
        "executor": "process",
        "evidence_source": "vignette_parser_freeze_v3",
        "vignette_freeze": str(freeze_path.relative_to(ROOT)),
        "live_vignette_parser": False,
        "ok": sum(row.get("status") in {"OK", "REUSED"} for row in records),
        "errors": [row for row in records if row.get("status") == "ERROR"],
    }
    _atomic_json(tree_dir / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not summary["errors"] else 1


def cmd_build_findings(args: argparse.Namespace) -> int:
    cases = _load_cases(args)
    freeze = _load_vignette_freeze(args)
    rows = []
    for case in cases:
        frozen = freeze.get(str(case["id"]))
        if frozen is None:
            raise RuntimeError(
                "%s: missing from vignette freeze %s"
                % (case["id"], _vignette_freeze_path(args))
            )
        findings = da.findings_catalog_from_frozen_case(frozen)
        if not findings:
            raise RuntimeError("%s: empty finding catalog" % case["id"])
        # Keep tree state aligned with the freeze when a tree already exists.
        tree_path = _tree_dir(args) / f"{case['id']}.json"
        if tree_path.is_file():
            tree = json.loads(tree_path.read_text(encoding="utf-8"))
            state = composed._deserialize_state(tree["state"])
            da.apply_frozen_vignette_parser_fields(state, case, frozen)
            tree["state"] = composed._serialize_state(state, {})
            tree["n_static_evidence_items"] = len(findings)
            tree["evidence_source"] = "vignette_parser_freeze_v2"
            _atomic_json(tree_path, tree)
        rows.append({
            "case_id": str(case["id"]),
            "full_findings": findings,
            "full_catalog_hash": stable_hash(findings),
            "filtered_fact_ids": [row["id"] for row in findings],
            "filter_runs": [],
            "source": "vignette_parser_freeze_v2",
        })
    fixture = {
        "asset_kind": "diagnosisarena_auto_finding_catalogs",
        "schema_version": 1,
        "created_at": _utc_now(),
        "evidence_source": "vignette_parser_freeze_v2",
        "vignette_freeze": str(_vignette_freeze_path(args).relative_to(ROOT)),
        "live_vignette_parser": False,
        "cases": rows,
    }
    _atomic_json(_fixture_path(args), fixture)
    print(json.dumps({
        "n_cases": len(rows),
        "mean_findings": round(
            statistics.mean(len(row["full_findings"]) for row in rows), 2
        ),
        "path": str(_fixture_path(args).relative_to(ROOT)),
        "evidence_source": "vignette_parser_freeze_v2",
        "live_vignette_parser": False,
    }, ensure_ascii=False, indent=2))
    return 0


def _compile_one_p5(
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
    cache_path = cache_dir / f"{case_id}.json"
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
    }
    _atomic_json(cache_path, payload)
    return payload


def cmd_compile_p5(args: argparse.Namespace) -> int:
    executor = getattr(args, "executor", "thread")
    if executor == "process":
        return _cmd_compile_p5_process(args)
    os.environ.setdefault("TREE_DX_DIRECT_POST_OUTPUT_CAP", "8192")
    cases = _load_cases(args)
    tree_dir = _tree_dir(args)
    cache_dir = _out(args) / "p5_audit"
    cache_dir.mkdir(parents=True, exist_ok=True)
    talp = _load_module("da_m01_talp", TALP_SCRIPT)
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "evp_pol", ROOT / "scripts" / "eval_evidence_precision.py",
    )
    evp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(evp)
    kb = evp.FusedKB(rag=True)
    cfg = talp._cfg_for_stage(P5_STAGE)
    cfg.entry_gate = "all_findings"
    cfg.route = True
    normalizer = talp._get_normalizer()
    dxidx = talp._get_dxindex(with_primekg=True)
    llm = RobustLLMClient(
        model=args.model,
        call_timeout=args.call_timeout,
        max_retries=5,
        timeout_retry_cap=2,
        temperature=0.0,
    )

    def _one(case: Mapping[str, Any]) -> dict[str, Any]:
        started = time.monotonic()
        tree = json.loads((tree_dir / f"{case['id']}.json").read_text())
        try:
            row = _compile_one_p5(
                case=case,
                tree_payload=tree,
                talp_module=talp,
                llm=llm,
                kb=kb,
                cfg=cfg,
                normalizer=normalizer,
                dxidx=dxidx,
                cache_dir=cache_dir,
            )
            return {
                "case_id": case["id"],
                "status": "OK",
                "n_rules": len(row.get("rules") or ()),
                "duration_seconds": round(time.monotonic() - started, 3),
            }
        except Exception as exc:
            return {
                "case_id": case["id"],
                "status": "ERROR",
                "error": "%s: %s" % (type(exc).__name__, exc),
                "duration_seconds": round(time.monotonic() - started, 3),
            }

    records = _map_workers(cases, _one, args.workers, "compile-p5")
    disc_audit = {}
    for case in cases:
        path = cache_dir / f"{case['id']}.json"
        if path.is_file():
            disc_audit[str(case["id"])] = list(
                json.loads(path.read_text()).get("rules") or ()
            )
    arm = {
        "summary": {
            "tag": "diagnosisarena_d2_p5_headline",
            "stage": P5_STAGE,
            "n_cases": len(disc_audit),
            "compiled_at": _utc_now(),
        },
        "disc_audit": disc_audit,
        "audit_summary": {},
        "case_normalized": {},
        "key_audit": {},
        "entry_audit": {},
        "rows": [],
    }
    _atomic_json(_p5_arm_path(args), arm)
    summary = {
        "phase": "compile-p5",
        "workers": args.workers,
        "ok": sum(row.get("status") == "OK" for row in records),
        "errors": [row for row in records if row.get("status") == "ERROR"],
        "arm_path": str(_p5_arm_path(args).relative_to(ROOT)),
        "mean_rules": (
            round(statistics.mean(
                len(disc_audit[cid]) for cid in disc_audit
            ), 2) if disc_audit else None
        ),
    }
    _atomic_json(_out(args) / "compile_p5_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not summary["errors"] else 1


def _cmd_compile_p5_process(args: argparse.Namespace) -> int:
    """Spawn process-pool P5 compile (independent KB/LLM per process)."""
    import multiprocessing as mp

    # Long DiscriminatorAgentMatrix JSON — avoid 1024-token truncation storms.
    os.environ.setdefault("TREE_DX_DIRECT_POST_OUTPUT_CAP", "8192")

    try:
        mp.set_start_method(getattr(args, "start_method", "spawn"), force=True)
    except RuntimeError:
        pass

    stress = _load_module(
        "da_m01_p5_stress_compile",
        ROOT / "scripts" / "paper" / "run_diagnosisarena_stress_p5_compile.py",
    )
    cases = _load_cases(args)
    tree_dir = _tree_dir(args)
    cache_dir = _out(args) / "p5_audit"
    cache_dir.mkdir(parents=True, exist_ok=True)
    workers = args.workers if args.workers > 0 else min(12, len(cases))
    payloads = [
        {
            "case": dict(case),
            "tree_path": str(tree_dir / ("%s.json" % case["id"])),
            "cache_dir": str(cache_dir),
        }
        for case in cases
    ]
    records = stress._map_process(
        payloads,
        workers=workers,
        initializer=stress._init_p5_worker,
        initargs=(args.model, float(args.call_timeout)),
        worker_fn=stress._run_p5_job,
        label="compile-p5/process",
    )
    disc_audit = {}
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
            "executor": "process",
            "compiled_at": _utc_now(),
        },
        "disc_audit": disc_audit,
        "audit_summary": {},
        "case_normalized": {},
        "key_audit": {},
        "entry_audit": {},
        "rows": [],
    }
    _atomic_json(_p5_arm_path(args), arm)
    summary = {
        "phase": "compile-p5",
        "workers": workers,
        "executor": "process",
        "ok": sum(row.get("status") == "OK" for row in records),
        "errors": [row for row in records if row.get("status") == "ERROR"],
        "arm_path": str(_p5_arm_path(args).relative_to(ROOT)),
        "mean_rules": (
            round(statistics.mean(
                len(disc_audit[cid]) for cid in disc_audit
            ), 2) if disc_audit else None
        ),
    }
    _atomic_json(_out(args) / "compile_p5_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not summary["errors"] else 1


def _map_workers(
    cases: Sequence[Mapping[str, Any]],
    fn,
    workers: int,
    label: str,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if workers <= 1:
        for index, case in enumerate(cases, start=1):
            row = fn(case)
            records.append(row)
            print(
                "[%s] %d/%d %s %s"
                % (label, index, len(cases), case["id"], row.get("status")),
                flush=True,
            )
        return records
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fn, case): case for case in cases}
        done = 0
        for future in as_completed(futures):
            case = futures[future]
            try:
                row = future.result()
            except Exception as exc:
                row = {
                    "case_id": case["id"],
                    "status": "ERROR",
                    "error": "%s: %s" % (type(exc).__name__, exc),
                }
            records.append(row)
            done += 1
            print(
                "[%s] %d/%d %s %s"
                % (label, done, len(cases), case["id"], row.get("status")),
                flush=True,
            )
    return records


def _base_case_id(case_id: str) -> str:
    """Strip stress oversample suffix ``__sNN`` → original freeze case id."""
    text = str(case_id)
    if "__s" in text:
        head, tail = text.rsplit("__s", 1)
        if tail.isdigit():
            return head
    return text


def _oversample_probe_jobs(
    cases: Sequence[Mapping[str, Any]],
    workers: int,
    *,
    saturate_above: int = 3,
    tasks_per_worker: int = 2,
) -> list[dict[str, Any]]:
    """Expand unique cases into enough jobs to saturate ``workers``.

    With only a handful of frozen cases, workers>3 would otherwise idle after
    the first wave, so throughput vs workers is not comparable. When
    ``workers > saturate_above``, replicate cases to
    ``max(n_cases, workers * tasks_per_worker)`` jobs with distinct ids.
    """
    base = [dict(case) for case in cases]
    if not base:
        return []
    n_unique = len(base)
    if workers <= saturate_above and n_unique >= workers:
        return base
    target = max(n_unique, int(workers) * max(1, int(tasks_per_worker)))
    jobs: list[dict[str, Any]] = []
    for index in range(target):
        src = base[index % n_unique]
        job = dict(src)
        job["source_case_id"] = str(src["id"])
        job["id"] = "%s__s%02d" % (src["id"], index + 1)
        jobs.append(job)
    return jobs


def cmd_stress(args: argparse.Namespace) -> int:
    """Probe workers 3,6,9,12 on build-trees (case-level; RAG/CPU heavy).

    For workers > 3, oversample the frozen case pool so every worker has
    enough tasks for an apples-to-apples throughput comparison.
    """
    grid = [
        int(token) for token in args.stress_workers.split(",") if token.strip()
    ]
    probe_args = argparse.Namespace(**vars(args))
    probe_args.limit = min(args.stress_cases, 100)
    probe_args.refresh_cases = False
    probe_cases = _load_cases(probe_args)
    tasks_per_worker = max(1, int(getattr(args, "stress_tasks_per_worker", 2)))
    saturate_above = int(getattr(args, "stress_saturate_above", 3))

    sweep = []
    for workers in grid:
        jobs = _oversample_probe_jobs(
            probe_cases,
            workers,
            saturate_above=saturate_above,
            tasks_per_worker=tasks_per_worker,
        )
        tree_dir = _tree_dir(probe_args)
        if tree_dir.is_dir():
            for path in tree_dir.glob("*.json"):
                if path.name == "summary.json":
                    continue
                path.unlink()
        probe_args.workers = workers
        probe_args.resume = False
        probe_args.cases = ",".join(sorted({
            str(case.get("source_case_id") or case["id"]) for case in jobs
        }))
        probe_args.limit = 0
        probe_args._stress_jobs = jobs  # noqa: SLF001 — stress-only override
        started = time.monotonic()
        code = cmd_build_trees(probe_args)
        wall = time.monotonic() - started
        n_jobs = len(jobs)
        sweep.append({
            "workers": workers,
            "phase": "build-trees",
            "probe_unique_cases": len(probe_cases),
            "probe_jobs": n_jobs,
            "oversampled": n_jobs > len(probe_cases),
            "tasks_per_worker_target": tasks_per_worker,
            "wall_seconds": round(wall, 3),
            "exit_code": code,
            "throughput_jobs_per_hour": (
                round(n_jobs / wall * 3600.0, 3) if wall > 0 else None
            ),
            "throughput_cases_per_hour": (
                round(n_jobs / wall * 3600.0, 3) if wall > 0 else None
            ),
            "job_ids": [job["id"] for job in jobs],
        })

    viable = [row for row in sweep if row["exit_code"] == 0]
    best = max(
        viable or sweep,
        key=lambda row: (
            float(row.get("throughput_cases_per_hour") or 0.0),
            -int(row["workers"]),
        ),
    )
    selected = int(best["workers"])
    by_w = {int(row["workers"]): row for row in sweep}
    for worker in sorted(by_w):
        if worker >= selected:
            break
        low = by_w[worker]
        high = by_w.get(worker * 2) or low
        low_t = float(low.get("throughput_cases_per_hour") or 0.0)
        high_t = float(high.get("throughput_cases_per_hour") or 0.0)
        if low_t > 0 and (high_t - low_t) / low_t < 0.15:
            selected = worker
            best = low
            break

    manifest = {
        "schema_version": 2,
        "created_at": _utc_now(),
        "probe_case_ids": [case["id"] for case in probe_cases],
        "worker_grid": grid,
        "oversample_rule": (
            "when workers > %d, expand unique cases to "
            "max(n_unique, workers * %d) distinct jobs "
            "(suffix __sNN) so throughput comparisons are saturated"
            % (saturate_above, tasks_per_worker)
        ),
        "tasks_per_worker": tasks_per_worker,
        "saturate_above": saturate_above,
        "selected_workers": selected,
        "selection_rule": (
            "max throughput (jobs/hour) among successful build-trees probes; "
            "downgrade when 2x workers yield <15% gain "
            "(RAG CPU contention guard)"
        ),
        "best_row": best,
        "sweep": sweep,
        "supersedes_unsaturated_v1": True,
        "note_prior_v1_invalid": (
            "schema_version=1 sweeps with workers>unique_cases were "
            "undersaturated and must not be used for worker selection"
        ),
        "recommended_downstream": {
            "l1_joint_replicate_workers": min(selected, args.replicates),
            "case_parallel_stages": selected,
            "note": (
                "L1/joint scripts still parallelize by replicate "
                "(min(workers, replicates)); tree/P5/L2-generate use case pool"
            ),
        },
    }
    _atomic_json(_out(args) / "concurrency_manifest.json", manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0 if all(row["exit_code"] == 0 for row in sweep) else 1


def _selected_workers(args: argparse.Namespace) -> int:
    if args.workers > 0:
        return args.workers
    path = _out(args) / "concurrency_manifest.json"
    if path.is_file():
        return int(json.loads(path.read_text()).get("selected_workers") or 3)
    return 3


def cmd_run_l1(args: argparse.Namespace) -> int:
    workers = _selected_workers(args)
    ns = argparse.Namespace(
        model=args.model,
        temperature=0.0,
        replicates=args.replicates,
        workers=min(workers, args.replicates),
        call_timeout=args.call_timeout,
        max_micro_rounds=30,
        cases="",
        limit=args.limit,
        cases_json=_cases_path(args),
        fixture=_fixture_path(args),
        gold=competition.DEFAULT_GOLD,
        tree_dir=_tree_dir(args),
        output_dir=_competition_dir(args),
        inject_compiler_rules=True,
        p5_arm_output=_p5_arm_path(args),
        fixed_l1_budget=0,
        n_boot=500,
    )
    summary = competition.run_l1_full(ns)
    print(json.dumps({
        "phase": "run-l1",
        "workers": ns.workers,
        "completed": summary.get("completed"),
        "errors": len(summary.get("errors") or ()),
        "compiler_rules_injected": True,
        "preset": "p5_anti_anchor_direct",
    }, ensure_ascii=False, indent=2))
    return 0 if not summary.get("errors") else 1


def cmd_freeze_l1(args: argparse.Namespace) -> int:
    ns = argparse.Namespace(
        model=args.model,
        temperature=0.0,
        replicates=args.replicates,
        workers=3,
        call_timeout=args.call_timeout,
        max_micro_rounds=30,
        cases="",
        limit=0,
        cases_json=_cases_path(args),
        fixture=_fixture_path(args),
        gold=competition.DEFAULT_GOLD,
        tree_dir=_tree_dir(args),
        output_dir=_competition_dir(args),
        inject_compiler_rules=True,
        p5_arm_output=_p5_arm_path(args),
        fixed_l1_budget=FIXED_L1_BUDGET,
        n_boot=500,
    )
    manifest = competition.freeze_l1_prefix(ns)
    print(json.dumps({
        "phase": "freeze-l1",
        "n_star": manifest.get("n_star"),
        "selection_rule": manifest.get("selection_rule"),
        "n_assets": len(manifest.get("assets") or ()),
    }, ensure_ascii=False, indent=2))
    return 0


def cmd_generate_l2(args: argparse.Namespace) -> int:
    workers = _selected_workers(args)
    argv = [
        "generate",
        "--output-dir", str(_l2_gen_dir(args)),
        "--tree-dir", str(_tree_dir(args)),
        "--finding-fixture", str(_fixture_path(args)),
        "--base-output-dir", str(_competition_dir(args)),
        "--cases-json", str(_cases_path(args)),
        "--model", args.model,
        "--replicates", str(args.replicates),
        "--workers", str(workers),
        "--call-timeout", str(args.call_timeout),
        "--candidate-budget", "24",
        "--snippet-budget", "12",
        "--arms", "A",
    ]
    if args.resume:
        argv.append("--resume")
    if args.limit > 0:
        # freeze-inputs / generate use case-filter by id; limit via first N ids
        ids = [case["id"] for case in _load_cases(args)[: args.limit]]
        argv.extend(["--case-filter", ",".join(ids)])
    # freeze-inputs must run first
    freeze_argv = ["freeze-inputs"] + argv[1:]
    freeze_argv[0] = "freeze-inputs"
    code = l2_ab.main(freeze_argv)
    if code != 0:
        return code
    return l2_ab.main(argv)


def cmd_joint(args: argparse.Namespace) -> int:
    import eval_l2_joint_dynamic_pipeline as joint

    workers = _selected_workers(args)
    # Provisional gold from Config A trees for scoring (auto label match).
    gold_path = _out(args) / "provisional_l2_gold_v1.json"
    _write_provisional_gold(args, gold_path)
    ns = argparse.Namespace(
        model=args.model,
        temperature=0.0,
        replicates=args.replicates,
        workers=min(workers, args.replicates),
        call_timeout=args.call_timeout,
        n_boot=500,
        cases="",
        limit=args.limit,
        cases_json=_cases_path(args),
        fixture=_fixture_path(args),
        gold=gold_path,
        tree_dir=_tree_dir(args),
        base_output_dir=_competition_dir(args),
        output_dir=_joint_dir(args),
    )
    # Joint expects L2 trees under competition tree_dir by default — point to
    # Config A generation trees when available.
    gen_traces = _l2_gen_dir(args) / "generation" / "traces" / "A"
    if gen_traces.is_dir():
        # Build a temporary tree dir from Config A replicate-1 trees for joint.
        joint_trees = _out(args) / "joint_trees_from_config_a"
        joint_trees.mkdir(parents=True, exist_ok=True)
        for case in _load_cases(args):
            src = gen_traces / ("r01__%s.json" % case["id"])
            if not src.is_file():
                continue
            doc = json.loads(src.read_text(encoding="utf-8"))
            _atomic_json(joint_trees / f"{case['id']}.json", {
                "tree_hash": doc.get("tree_hash"),
                "state": doc.get("tree"),
            })
        ns.tree_dir = joint_trees
    summary = joint.run(ns)
    print(json.dumps({
        "phase": "joint",
        "arms": list((summary.get("performance") or {}).get("arms") or {}),
    }, ensure_ascii=False, indent=2))
    return 0


def _write_provisional_gold(args: argparse.Namespace, path: Path) -> None:
    import diagnosisarena_l2_pipeline as l2pipe
    from agentclinic_tree_dx.knowledge.disease_name_resolver import (
        DiseaseNameResolver,
    )

    resolver = DiseaseNameResolver()
    knowledge = ROOT / "data" / "knowledge_raw"
    for name in (
        "mechanism_to_disease.json",
        "disease_name_bridge.json",
        "doclogica_cache.json",
    ):
        p = knowledge / name
        if not p.exists():
            continue
        if "mechanism" in name:
            resolver.load_mechanism_map(p)
        elif "bridge" in name:
            resolver.load_bridge(p)
        else:
            resolver.load_umls_from_doclogica(p)

    cases_out = []
    gen_traces = _l2_gen_dir(args) / "generation" / "traces" / "A"
    for case in _load_cases(args):
        src = gen_traces / ("r01__%s.json" % case["id"])
        if not src.is_file():
            cases_out.append({
                "case_id": case["id"],
                "gold_diagnosis": case["gold"],
                "status": "absent",
                "acceptable_l2": [],
                "rationale": "missing config-A tree",
            })
            continue
        doc = json.loads(src.read_text(encoding="utf-8"))
        state = l2pipe.deserialize_state(doc["tree"])
        gold = l2pipe.build_gold_l2(
            gold_label=str(case["gold"]),
            state=state,
            resolver=resolver,
        )
        cases_out.append({
            "case_id": case["id"],
            "gold_diagnosis": case["gold"],
            "status": (
                "unique" if gold["status"] == "present" else "absent"
            ),
            "acceptable_l2": [
                {
                    "id": row["id"],
                    "label": row["label"],
                    "parent_id": str(
                        state.branches[row["id"]].parent
                        if row["id"] in state.branches else ""
                    ),
                    "parent_label": "",
                }
                for row in gold["acceptable_l2"]
            ],
            "rationale": "provisional auto label match; pending human adjudication",
        })
    _atomic_json(path, {
        "asset_kind": "provisional_diagnosisarena_l2_gold",
        "human_signed_off": False,
        "cases": cases_out,
    })


def cmd_mapper(args: argparse.Namespace) -> int:
    cases = {case["id"]: case for case in _load_cases(args)}
    joint_summary = _joint_dir(args) / "summary.json"
    if not joint_summary.is_file():
        raise FileNotFoundError("run joint first")
    # Prefer A3-joint-primary records from joint traces if present.
    records = []
    resolver = load_offline_resolver(ROOT)
    client = RobustLLMClient(
        model=args.model,
        call_timeout=args.call_timeout,
        max_retries=5,
        timeout_retry_cap=2,
        temperature=0.0,
    )
    cached = bfs_eval.CachedLLM(
        client, _out(args) / "cache" / "mapper_llm.json", args.model,
    )

    class _Adapter:
        def call_module(self, module, prompt, payload):
            return cached.call(module, prompt, dict(payload))

    mapper = RelationAwareAnswerMapper(
        resolver=resolver,
        llm=_Adapter(),
        relation_prompt=(
            PROMPT_DIR / "answer_relation_mapper.txt"
        ).read_text(encoding="utf-8"),
        critic_prompt=(
            PROMPT_DIR / "answer_relation_rag_critic.txt"
        ).read_text(encoding="utf-8"),
    )
    gen_traces = _l2_gen_dir(args) / "generation" / "traces" / "A"
    adjudication_rows = []
    for case_id, case in cases.items():
        src = gen_traces / ("r01__%s.json" % case_id)
        if not src.is_file():
            continue
        doc = json.loads(src.read_text(encoding="utf-8"))
        tree = doc["tree"]
        ranking = [
            branch_id
            for branch_id, node in sorted((tree.get("branches") or {}).items())
            if int(node.get("level") or 0) == 2
        ]
        leaves = leaf_rows_from_tree(tree, ranking)
        options = da.normalize_options(case["annotation"]["source_options"])
        body = str(case["case_text"]).split("\nOptions:", 1)[0]
        projection = mapper.map(
            case_id=case_id,
            vignette=body,
            question="What is the most likely diagnosis?",
            options=options,
            leaves=leaves,
            mode=args.mapper_mode,
        )
        gold_letter = str(case.get("gold_option") or "").upper()
        gold_map = (projection.get("option_maps") or {}).get(gold_letter) or {}
        gold_rank = gold_map.get("best_rank")
        option_rank = int(
            gold_map.get("option_rank") or (len(options) + 1)
        )
        records.append({
            "case_id": case_id,
            "gold_letter": gold_letter,
            "option_top1": bool(gold_rank is not None and option_rank <= 1),
            "option_top2": bool(gold_rank is not None and option_rank <= 2),
            "projection": projection,
        })
        for letter, text in sorted(options.items()):
            mapped = (projection.get("option_maps") or {}).get(letter) or {}
            adjudication_rows.append({
                "case_id": case_id,
                "option_letter": letter,
                "option_text": text,
                "relation_type": mapped.get("relation_type", "unknown"),
                "matched_leaf_labels": sorted({
                    str(leaf["leaf_label"])
                    for leaf in leaves
                    if str(leaf["leaf_id"]) in set(
                        mapped.get("clone_leaf_ids") or ()
                    )
                }),
                "review_status": "pending_human",
            })
    summary = {
        "n_cases": len(records),
        "option_top1": (
            round(sum(row["option_top1"] for row in records) / len(records), 4)
            if records else None
        ),
        "option_top2": (
            round(sum(row["option_top2"] for row in records) / len(records), 4)
            if records else None
        ),
        "note": "pre-adjudication; finalize after human relation review",
    }
    _atomic_json(_out(args) / "mapper" / "records.json", {
        "records": records, "summary": summary,
    })
    _atomic_json(
        _out(args) / "mapper" / "adjudication_blind_v1.json",
        {
            "human_signed_off": False,
            "rows": adjudication_rows,
        },
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def cmd_all(args: argparse.Namespace) -> int:
    steps = [
        ("prepare", cmd_prepare),
        ("build-trees", cmd_build_trees),
        ("build-findings", cmd_build_findings),
        ("compile-p5", cmd_compile_p5),
        ("stress", cmd_stress),
        ("run-l1", cmd_run_l1),
        ("freeze-l1", cmd_freeze_l1),
        ("generate-l2", cmd_generate_l2),
        ("joint", cmd_joint),
        ("mapper", cmd_mapper),
    ]
    for name, fn in steps:
        if args.skip_stress and name == "stress":
            continue
        print("\n=== phase: %s ===" % name, flush=True)
        code = fn(args)
        if code != 0:
            return code
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--phase",
        required=True,
        choices=(
            "prepare", "build-trees", "build-findings", "compile-p5", "stress",
            "run-l1", "freeze-l1", "generate-l2", "joint", "mapper", "all",
        ),
    )
    parser.add_argument("--parquet", type=Path, default=DEFAULT_PARQUET)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--cases", default="")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--workers", type=int, default=0)
    parser.add_argument("--replicates", type=int, default=3)
    parser.add_argument("--call-timeout", type=float, default=240.0)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument(
        "--strip-mcq-options",
        action="store_true",
        help=(
            "Build trees from da.vignette_body(case_text) so annotate sees the "
            "same options-stripped input as the baselines and the option mapper. "
            "Off by default to reproduce the existing runs."
        ),
    )
    parser.add_argument("--refresh-cases", action="store_true")
    parser.add_argument("--stress-cases", type=int, default=5)
    parser.add_argument("--stress-workers", default="3,6,9,12")
    parser.add_argument(
        "--stress-tasks-per-worker",
        type=int,
        default=2,
        help=(
            "When workers > --stress-saturate-above, oversample to "
            "workers*this many jobs for saturated throughput comparison"
        ),
    )
    parser.add_argument(
        "--stress-saturate-above",
        type=int,
        default=3,
        help="Oversample probe jobs when workers exceed this threshold",
    )
    parser.add_argument("--skip-stress", action="store_true")
    parser.add_argument(
        "--vignette-freeze",
        type=Path,
        default=DEFAULT_VIGNETTE_FREEZE,
        help=(
            "Signed-off VignetteParser freeze JSON. Live VignetteParser is "
            "never called in this pipeline."
        ),
    )
    parser.add_argument(
        "--executor",
        default="thread",
        choices=["thread", "process"],
        help=(
            "Concurrency backend for build-trees / compile-p5. "
            "thread=legacy default (rollback); process=spawn process pool "
            "(per-process FAISS/KB, OMP≤2). For disjoint 6/12 P5 stress with "
            "retained headlines, prefer "
            "scripts/paper/run_diagnosisarena_stress_p5_compile.py"
        ),
    )
    parser.add_argument(
        "--start-method",
        default="spawn",
        choices=["spawn", "fork", "forkserver"],
        help="multiprocessing start method when --executor process",
    )
    parser.add_argument(
        "--mapper-mode",
        default="typed_llm",
        choices=[
            "deterministic_gold_blind",
            "typed_llm",
            "typed_llm_disagreement_rag",
        ],
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    dispatch = {
        "prepare": cmd_prepare,
        "build-trees": cmd_build_trees,
        "build-findings": cmd_build_findings,
        "compile-p5": cmd_compile_p5,
        "stress": cmd_stress,
        "run-l1": cmd_run_l1,
        "freeze-l1": cmd_freeze_l1,
        "generate-l2": cmd_generate_l2,
        "joint": cmd_joint,
        "mapper": cmd_mapper,
        "all": cmd_all,
    }
    return dispatch[args.phase](args)


if __name__ == "__main__":
    raise SystemExit(main())
