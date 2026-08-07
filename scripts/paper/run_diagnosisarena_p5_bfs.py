#!/usr/bin/env python3
"""DiagnosisArena D2: 14-step explainer pipeline (L1 P5+BFS + L2 Config A + joint).

Phases:
  prepare          Normalize parquet cases.
  stress           Concurrency sweep; reuses artifacts in run.
  run              Steps 1–14 per case (tree → P5 → BFS → L2 A → joint → L2 metrics).
  mapper           Gold-blind RelationAwareAnswerMapper for MCQ @1/@2.
  adjudication     Blind human relation review sheet.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import os
import statistics
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
os.environ.setdefault("TREE_DX_USE_PROXY", "1")
os.environ.setdefault("TREE_DX_EMBED_DEVICE", "cpu")

import diagnosisarena_adapter as da  # noqa: E402
import diagnosisarena_l2_pipeline as l2pipe  # noqa: E402
import eval_branch_talp_composed as composed  # noqa: E402
import eval_l2_branch_generation_ab as l2_ab  # noqa: E402
import eval_l1_evidence_bfs as bfs_eval  # noqa: E402
from agentclinic_tree_dx.answer_projection_mapper import (  # noqa: E402
    RelationAwareAnswerMapper,
    leaf_rows_from_tree,
    load_offline_resolver,
)
from agentclinic_tree_dx.l1_evidence_bfs import (  # noqa: E402
    L1EvidenceBFSPipeline,
    L1ObservedFact,
    PRESETS,
    assert_no_gold_leak,
    stable_hash,
)
from agentclinic_tree_dx.llm_client import RobustLLMClient  # noqa: E402
from agentclinic_tree_dx.state import DiagnosticState  # noqa: E402

DEFAULT_PARQUET = (
    ROOT / "data" / "benchmarks" / "diagnosisarena" / "subsets"
    / "d2_seq100_v1" / "cases.parquet"
)
DEFAULT_OUT = ROOT / "logs" / "diagnosisarena_d2_p5_bfs_v1"
DEFAULT_MODEL = "meta-llama/llama-3.3-70b-instruct"
P5_STAGE = "p7"
P5_PROFILE = "p5_headline"
BFS_ARM = "B1"
BFS_PRESET = "p5_single_direct"
BRANCH_SCRIPT = ROOT / "scripts" / "eval_branch_creation_medbullets.py"
TALP_SCRIPT = ROOT / "scripts" / "eval_talp_discrimination.py"
PROMPT_DIR = ROOT / "src" / "agentclinic_tree_dx" / "prompts"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot import %s" % path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _atomic_json(path: Path, payload: Any) -> None:
    da._atomic_json(path, payload)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class PerCaseDiscAudit:
    """Route per-case freshly compiled P5 audits to observed-fact IDs."""

    def __init__(self, talp_module, audit_dir: Path, stage: str = P5_STAGE) -> None:
        self.talp = talp_module
        self.audit_dir = audit_dir
        self.cfg = talp_module._cfg_for_stage(stage)

    def rules(self, case_id: str) -> list[dict[str, Any]]:
        path = self.audit_dir / f"{case_id}.json"
        if not path.is_file():
            return []
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            return payload
        return list(payload.get("rules") or payload.get("audit") or ())

    def blocks(
        self,
        profile: str,
        case_id: str,
        facts: tuple[L1ObservedFact, ...],
    ) -> dict[str, dict[str, Any]]:
        del profile  # single frozen P5 profile for this harness
        rules = self.rules(case_id)
        output: dict[str, dict[str, Any]] = {}
        for fact in facts:
            matched = composed._best_reference(fact.text, rules)
            matched_rules = [matched] if matched is not None else []
            routed = self.talp._routed_blocks(matched_rules, self.cfg)
            evidence = list((matched or {}).get("evidence") or ())
            output[fact.id] = {
                **routed,
                "provenance": evidence[:12],
                "matched_compiler_finding": (
                    matched.get("finding") if matched is not None else None
                ),
                "n_evidence": int((matched or {}).get("n_evidence") or 0),
                "verdict": (matched or {}).get("verdict", "unmatched"),
            }
        return output


def _pipeline_identity(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "dataset": "diagnosisarena_d2_seq100_v1",
        "model": args.model,
        "p5_stage": P5_STAGE,
        "p5_profile": P5_PROFILE,
        "bfs_arm": BFS_ARM,
        "bfs_preset": BFS_PRESET,
        "branch_mode": "recall_hints_gap",
        "force_expand_all_l1": True,
        "entry_gate": args.entry_gate,
        "call_timeout": args.call_timeout,
        "temperature": args.temperature,
        "l2_pipeline": "config_a_joint_a3",
        "l2_candidate_budget": args.l2_candidate_budget,
        "l2_snippet_budget": args.l2_snippet_budget,
    }


def _load_cases(args: argparse.Namespace) -> list[dict[str, Any]]:
    manifest = args.output_dir / "normalized_cases.json"
    prepare_manifest = args.output_dir / "prepare_manifest.json"
    expected_n = None
    if args.limit <= 0 and not args.cases:
        import pandas as pd

        expected_n = len(pd.read_parquet(args.parquet))
    if manifest.is_file() and not args.refresh_cases:
        doc = json.loads(manifest.read_text(encoding="utf-8"))
        cases = list(doc.get("cases") or ())
        if (
            expected_n is not None
            and len(cases) < expected_n
            and prepare_manifest.is_file()
        ):
            print(
                "[prepare] normalized_cases has %d/%d rows — refreshing"
                % (len(cases), expected_n),
                flush=True,
            )
            cases = []
        elif cases:
            pass
        else:
            cases = []
    if manifest.is_file() and not args.refresh_cases and cases:
        pass
    else:
        selector = [
            token.strip()
            for token in (args.cases or "").split(",")
            if token.strip()
        ]
        cases = da.load_subset_cases(
            args.parquet,
            case_ids=selector,
            limit=args.limit,
        )
        da.write_normalized_cases(cases, manifest)
    if args.cases and not args.refresh_cases:
        wanted = {
            token.strip()
            for token in args.cases.split(",")
            if token.strip()
        }
        cases = [case for case in cases if case["id"] in wanted]
    if args.limit > 0:
        cases = cases[: args.limit]
    return cases


def _facts_for_case(
    state: DiagnosticState,
    annotation: Mapping[str, Any],
) -> tuple[L1ObservedFact, ...]:
    findings = list(annotation.get("findings") or ())
    texts = [
        str(getattr(item, "content", "") or "").strip()
        for item in (state.static_evidence_items or ())
    ]
    texts.extend(
        str(row.get("finding") or "").strip()
        for row in findings if row.get("in_vignette")
    )
    output: list[L1ObservedFact] = []
    seen: set[str] = set()
    for text in texts:
        if not text:
            continue
        key = " ".join(text.lower().split())
        if key in seen:
            continue
        seen.add(key)
        output.append(L1ObservedFact(f"F{len(output) + 1}", text))
        if len(output) >= 40:
            break
    return tuple(output)


def _serialize_state(state: DiagnosticState) -> dict[str, Any]:
    return composed._serialize_state(state, {})


def _deserialize_state(payload: Mapping[str, Any]) -> DiagnosticState:
    return composed._deserialize_state(payload)


def _build_p5_kb(talp_module, args: argparse.Namespace):
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "evp_pol", ROOT / "scripts" / "eval_evidence_precision.py",
    )
    evp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(evp)
    kb = evp.FusedKB(rag=args.rag)
    cfg = talp_module._cfg_for_stage(P5_STAGE)
    cfg.entry_gate = args.entry_gate
    cfg.evidence_source = args.evidence_source
    cfg.evidence_lane = args.evidence_lane
    if args.p5kg_manifest:
        cfg.p5kg_manifest = str(args.p5kg_manifest)
    return kb, cfg, evp


def _compile_p5_for_case(
    *,
    talp_case: Mapping[str, Any],
    talp_module,
    llm,
    kb,
    cfg,
    normalizer,
    dxidx,
    cache_path: Path,
) -> list[dict[str, Any]]:
    built = talp_module._build_disc_blocks_v2(
        llm,
        kb,
        {"cases": [dict(talp_case)]},
        cfg,
        normalizer=normalizer,
        dxidx=dxidx,
    )
    rules = list((built.get("audit") or {}).get(str(talp_case["id"])) or ())
    _atomic_json(cache_path, {
        "case_id": talp_case["id"],
        "stage": P5_STAGE,
        "entry_gate": cfg.entry_gate,
        "rules": rules,
        "entry_audit": (built.get("entry_audit") or {}).get(str(talp_case["id"])),
        "compiled_at": _utc_now(),
    })
    return rules


def _run_bfs(
    *,
    case: Mapping[str, Any],
    state: DiagnosticState,
    disc_audit: PerCaseDiscAudit,
    cached: bfs_eval.CachedLLM,
    talp_module,
) -> dict[str, Any]:
    spec = bfs_eval.ARM_SPECS[BFS_ARM]
    facts = _facts_for_case(state, case["annotation"])
    blocks = disc_audit.blocks(P5_PROFILE, str(case["id"]), facts)
    global_fn, in_fn, out_fn, ro_fn = bfs_eval._runtime_functions(
        cached,
        spec.preset,
        talp_module,
        branch_proposal=False,
        disable_ruleout=spec.disable_ruleout,
    )
    pipeline = L1EvidenceBFSPipeline(
        preset=spec.preset,
        global_selector=global_fn,
        rule_in_allocator=in_fn,
        rule_out_allocator=out_fn,
        ruleout_selector=(
            ro_fn
            if PRESETS[spec.preset].ruleout_selector == "dedicated"
            else None
        ),
        max_micro_rounds=spec.max_rounds,
        facts_per_cycle=spec.facts_per_cycle,
        enforce_canonical_dedup=spec.deduplicate,
    )
    final_state, trace = pipeline.run(
        copy.deepcopy(state),
        case_context=str(case["case_text"]),
        facts=facts,
        compiler_master_blocks=blocks,
        prior_mode="branch",
    )
    ranking = da.l2_ranking_from_state(final_state)
    return {
        "facts": [fact.to_dict() for fact in facts],
        "blocks": blocks,
        "trace": trace,
        "final_state": _serialize_state(final_state),
        "l2_ranking": ranking,
        "profile_rule_hits": sum(
            int((blocks.get(fact_id) or {}).get("n_evidence") or 0)
            for fact_id in trace.get("selected_fact_ids") or ()
        ),
    }


def _process_one_case(
    *,
    case: Mapping[str, Any],
    args: argparse.Namespace,
    identity: Mapping[str, Any],
    run_fingerprint: str,
    output_path: Path,
    branch_module,
    talp_module,
    llm: RobustLLMClient,
    kb,
    p5_cfg,
    normalizer,
    dxidx,
    disc_audit: PerCaseDiscAudit,
) -> dict[str, Any]:
    if output_path.is_file():
        existing = json.loads(output_path.read_text(encoding="utf-8"))
        if (
            existing.get("status") == "OK"
            and existing.get("run_fingerprint") == run_fingerprint
        ):
            return existing

    case_id = str(case["id"])
    cache_root = args.output_dir / "cache" / case_id
    cache_root.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    record: dict[str, Any] = {
        "schema_version": 1,
        "status": "ERROR",
        "case_id": case_id,
        "run_fingerprint": run_fingerprint,
        "identity": dict(identity),
    }
    controller = env = None
    try:
        controller, env, _config, provenance = branch_module.build_controller(
            args.model,
            branch_mode="recall_hints_gap",
            config_overrides={
                "talp_disc_profile": "off",
                "force_expand_all_l1": True,
            },
        )
        env.set_case(str(case["case_text"]))
        state = branch_module.run_case_branches(
            controller, env, str(case["case_text"]),
        )
        state.case_id = case_id
        state.max_tree_depth = 2
        controller.parse_static_vignette(state)
        expansion = controller.force_expand_all_l1(state)
        if expansion.get("l1_expansion_rate") != 1.0:
            raise RuntimeError(
                "%s: incomplete L1 expansion (%s)"
                % (case_id, expansion.get("l1_expansion_rate"))
            )

        talp_case = da.build_talp_case(case, state)
        case["annotation"]["candidates"] = list(talp_case["candidates"])
        case["annotation"]["findings"] = list(talp_case["findings"])
        compiler_case = da.runtime_compiler_case(talp_case)
        assert_no_gold_leak(compiler_case)

        p5_cache = cache_root / "p5_audit.json"
        if p5_cache.is_file() and args.resume:
            rules = list(json.loads(p5_cache.read_text(encoding="utf-8")).get("rules") or ())
        else:
            rules = _compile_p5_for_case(
                talp_case=compiler_case,
                talp_module=talp_module,
                llm=llm,
                kb=kb,
                cfg=p5_cfg,
                normalizer=normalizer,
                dxidx=dxidx,
                cache_path=p5_cache,
            )
        if not rules and not args.allow_empty_p5:
            raise RuntimeError("%s: P5 compiler returned zero rules" % case_id)

        cached = bfs_eval.CachedLLM(
            llm,
            cache_root / "bfs_llm_cache.json",
            args.model,
        )
        bfs_payload = _run_bfs(
            case=case,
            state=state,
            disc_audit=disc_audit,
            cached=cached,
            talp_module=talp_module,
        )
        bfs_state = _deserialize_state(bfs_payload["final_state"])
        findings = l2pipe.findings_catalog(bfs_state)
        f2_facts = l2pipe.f2_from_bfs_trace(findings, bfs_payload["trace"])

        l2_cached = l2_ab.CachedModuleAdapter(
            bfs_eval.CachedLLM(
                llm,
                cache_root / "l2_llm_cache.json",
                args.model,
            )
        )
        l2_state, l2_gen = l2pipe.run_config_a_l2_generation(
            serialized_state=bfs_payload["final_state"],
            cached_adapter=l2_cached,
            candidate_budget=args.l2_candidate_budget,
            snippet_budget=args.l2_snippet_budget,
        )
        joint_payload = l2pipe.run_joint_primary(
            case_text=str(case["case_text"]),
            state=l2_state,
            findings=findings,
            f2_facts=f2_facts,
            cache=l2_cached.cached,
        )
        resolver = load_offline_resolver(ROOT)
        gold_l2 = l2pipe.build_gold_l2(
            gold_label=str(case["gold"]),
            state=l2_state,
            resolver=resolver,
        )
        l2_metrics = l2pipe.score_l2(
            ranking=joint_payload["final_ranking"],
            gold=gold_l2,
            scope_ids=joint_payload["scope_ids"],
            schema_valid=bool(joint_payload["arbiter"].get("schema_valid")),
            champion_ids=joint_payload["champion_ids"],
        )
        tree_payload = {
            "run_fingerprint": run_fingerprint,
            "tree_hash": stable_hash(_serialize_state(state)["branches"]),
            "state": _serialize_state(state),
            "expansion": expansion,
            "branch_provenance": dict((provenance or {}).get("last") or {}),
        }
        record = {
            "schema_version": 1,
            "status": "OK",
            "case_id": case_id,
            "run_fingerprint": run_fingerprint,
            "identity": dict(identity),
            "duration_seconds": round(time.monotonic() - started, 3),
            "gold": str(case["gold"]),
            "gold_option": str(case.get("gold_option") or ""),
            "tree": tree_payload,
            "talp_case": {
                "n_candidates": len(talp_case["candidates"]),
                "n_findings": len(talp_case["findings"]),
                "n_p5_rules": len(rules),
            },
            "bfs": bfs_payload,
            "l2": {
                "generation": l2_gen,
                "joint": joint_payload,
                "gold_l2": gold_l2,
                "metrics": l2_metrics,
                "final_state": l2pipe.serialize_state(l2_state),
                "final_ranking": joint_payload["final_ranking"],
            },
            "pipeline_steps": list(range(1, 15)),
            "answer_mapper_called": False,
        }
    except Exception as exc:
        record.update({
            "status": "ERROR",
            "error": "%s: %s" % (type(exc).__name__, exc),
            "duration_seconds": round(time.monotonic() - started, 3),
        })
    _atomic_json(output_path, record)
    return record


def _run_pool(
    *,
    cases: Sequence[Mapping[str, Any]],
    args: argparse.Namespace,
    identity: Mapping[str, Any],
    run_fingerprint: str,
    case_dir: Path,
    workers: int,
    progress_label: str,
) -> list[dict[str, Any]]:
    branch_module = _load_module("da_branch", BRANCH_SCRIPT)
    talp_module = _load_module("da_talp", TALP_SCRIPT)
    kb, p5_cfg, _evp = _build_p5_kb(talp_module, args)
    normalizer = talp_module._get_normalizer()
    dxidx = talp_module._get_dxindex(with_primekg=True)
    disc_audit = PerCaseDiscAudit(
        talp_module, args.output_dir / "p5_audit", stage=P5_STAGE,
    )

    llm = RobustLLMClient(
        model=args.model,
        call_timeout=args.call_timeout,
        max_retries=5,
        timeout_retry_cap=2,
        temperature=args.temperature,
    )

    def _task(case: Mapping[str, Any]) -> dict[str, Any]:
        path = case_dir / f"{case['id']}.json"
        return _process_one_case(
            case=case,
            args=args,
            identity=identity,
            run_fingerprint=run_fingerprint,
            output_path=path,
            branch_module=branch_module,
            talp_module=talp_module,
            llm=llm,
            kb=kb,
            p5_cfg=p5_cfg,
            normalizer=normalizer,
            dxidx=dxidx,
            disc_audit=disc_audit,
        )

    records: list[dict[str, Any]] = []
    started = time.monotonic()
    if workers <= 1:
        for index, case in enumerate(cases, start=1):
            record = _task(case)
            records.append(record)
            print(
                "[%s] %d/%d %s %s %.1fs"
                % (
                    progress_label,
                    index,
                    len(cases),
                    case["id"],
                    record.get("status"),
                    float(record.get("duration_seconds") or 0.0),
                ),
                flush=True,
            )
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(_task, case): case for case in cases
            }
            done = 0
            for future in as_completed(futures):
                case = futures[future]
                record = future.result()
                records.append(record)
                done += 1
                print(
                    "[%s] %d/%d %s %s %.1fs"
                    % (
                        progress_label,
                        done,
                        len(cases),
                        case["id"],
                        record.get("status"),
                        float(record.get("duration_seconds") or 0.0),
                    ),
                    flush=True,
                )
    elapsed = time.monotonic() - started
    ok = [row for row in records if row.get("status") == "OK"]
    summary = {
        "label": progress_label,
        "workers": workers,
        "planned": len(cases),
        "completed_ok": len(ok),
        "errors": len(records) - len(ok),
        "wall_seconds": round(elapsed, 3),
        "mean_case_seconds": (
            round(statistics.mean(float(row["duration_seconds"]) for row in ok), 3)
            if ok else None
        ),
        "p95_case_seconds": (
            round(
                sorted(float(row["duration_seconds"]) for row in ok)[
                    max(0, int(round(0.95 * len(ok))) - 1)
                ],
                3,
            )
            if ok else None
        ),
        "throughput_cases_per_hour": (
            round(len(ok) / elapsed * 3600.0, 3) if elapsed > 0 and ok else None
        ),
    }
    return records, summary


def cmd_prepare(args: argparse.Namespace) -> int:
    cases = _load_cases(args)
    manifest = {
        "schema_version": 1,
        "prepared_at": _utc_now(),
        "parquet": str(args.parquet),
        "n_cases": len(cases),
        "case_ids": [case["id"] for case in cases],
    }
    _atomic_json(args.output_dir / "prepare_manifest.json", manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


def _select_optimal_workers(
    sweep_rows: Sequence[Mapping[str, Any]],
    *,
    max_workers: int,
) -> dict[str, Any]:
    viable = [
        row for row in sweep_rows
        if row.get("errors", 0) == 0 and row.get("throughput_cases_per_hour")
    ]
    if not viable:
        viable = list(sweep_rows)
    best = max(
        viable,
        key=lambda row: (
            float(row.get("throughput_cases_per_hour") or 0.0),
            -float(row.get("p95_case_seconds") or 10**9),
            -int(row.get("workers") or 1),
        ),
    )
    # RAG CPU guard: if doubling workers yields <15% gain, prefer lower workers.
    by_workers = {
        int(row["workers"]): row for row in sweep_rows if row.get("workers")
    }
    chosen = int(best.get("workers") or 1)
    for worker in sorted(by_workers):
        if worker >= chosen:
            break
        low = by_workers[worker]
        high = by_workers.get(worker * 2) or low
        low_t = float(low.get("throughput_cases_per_hour") or 0.0)
        high_t = float(high.get("throughput_cases_per_hour") or 0.0)
        if worker * 2 <= max_workers and low_t > 0:
            gain = (high_t - low_t) / low_t
            if gain < 0.15:
                chosen = worker
                best = low
                break
    return {
        "selected_workers": chosen,
        "selection_rule": (
            "max throughput among zero-error sweeps; downgrade when 2x workers "
            "yield <15% throughput gain (RAG CPU contention guard)"
        ),
        "best_row": dict(best),
        "sweep": list(sweep_rows),
    }


def cmd_stress(args: argparse.Namespace) -> int:
    cases = _load_cases(args)
    probe_n = min(args.stress_cases, len(cases))
    probe_cases = cases[:probe_n]
    identity = _pipeline_identity(args)
    run_fingerprint = stable_hash(identity)
    worker_grid = [
        int(token)
        for token in args.stress_workers.split(",")
        if token.strip()
    ]
    if not worker_grid:
        raise ValueError("empty --stress-workers")

    sweep_rows: list[dict[str, Any]] = []
    for workers in worker_grid:
        case_dir = args.output_dir / "stress" / f"w{workers}" / "cases"
        records, summary = _run_pool(
            cases=probe_cases,
            args=args,
            identity=identity,
            run_fingerprint=run_fingerprint,
            case_dir=case_dir,
            workers=workers,
            progress_label="stress/w%d" % workers,
        )
        summary["case_ids"] = [case["id"] for case in probe_cases]
        sweep_rows.append(summary)
        _atomic_json(
            args.output_dir / "stress" / f"w{workers}" / "summary.json",
            {"records": records, **summary},
        )

    decision = _select_optimal_workers(
        sweep_rows, max_workers=max(worker_grid),
    )
    manifest = {
        "schema_version": 1,
        "created_at": _utc_now(),
        "run_fingerprint": run_fingerprint,
        "identity": identity,
        "probe_case_ids": [case["id"] for case in probe_cases],
        "worker_grid": worker_grid,
        **decision,
    }
    _atomic_json(args.output_dir / "concurrency_manifest.json", manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


def _existing_ok_cases(case_roots: Sequence[Path], fingerprint: str) -> set[str]:
    found: set[str] = set()
    for root in case_roots:
        if not root.is_dir():
            continue
        for path in root.glob("*.json"):
            try:
                row = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if row.get("status") == "OK" and row.get("run_fingerprint") == fingerprint:
                found.add(str(row.get("case_id") or path.stem))
    return found


def _summarize_l2_metrics(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    ok = [row for row in records if row.get("status") == "OK" and row.get("l2")]
    if not ok:
        return {"n_cases": 0}
    metrics = [row["l2"]["metrics"] for row in ok]
    present = [row for row in metrics if row.get("gold_present")]
    def _mean(key: str, rows: Sequence[Mapping[str, Any]]) -> float | None:
        values = [row.get(key) for row in rows if row.get(key) is not None]
        if not values:
            return None
        return round(statistics.fmean(float(value) for value in values), 4)
    return {
        "n_cases": len(ok),
        "n_gold_present": len(present),
        "l2_top1_all": _mean("top1", metrics),
        "l2_top2_all": _mean("top2", metrics),
        "l2_mrr_all": _mean("rr", metrics),
        "l2_top1_gold_present": _mean("top1", present),
        "l2_top2_gold_present": _mean("top2", present),
        "l2_mrr_gold_present": _mean("rr", present),
        "structural_reach": _mean("structural_reach", present),
        "local_champion_recall": _mean("local_champion_recall", present),
        "error_attribution": dict(sorted(
            Counter(
                str(row.get("error_attribution") or "unknown") for row in metrics
            ).items()
        )),
    }


def cmd_run(args: argparse.Namespace) -> int:
    cases = _load_cases(args)
    identity = _pipeline_identity(args)
    run_fingerprint = stable_hash(identity)
    workers = args.workers
    manifest_path = args.output_dir / "concurrency_manifest.json"
    if workers <= 0 and manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("run_fingerprint") == run_fingerprint:
            workers = int(manifest.get("selected_workers") or 1)
    if workers <= 0:
        workers = 2

    reuse_roots = [
        args.output_dir / "stress" / f"w{workers}" / "cases",
        args.output_dir / "run" / "cases",
    ]
    done_ids = _existing_ok_cases(reuse_roots, run_fingerprint)
    pending = [case for case in cases if case["id"] not in done_ids]

    # Promote stress artifacts into canonical run dir (no recompute).
    run_case_dir = args.output_dir / "run" / "cases"
    run_case_dir.mkdir(parents=True, exist_ok=True)
    stress_dir = args.output_dir / "stress" / f"w{workers}" / "cases"
    if stress_dir.is_dir():
        for path in stress_dir.glob("*.json"):
            target = run_case_dir / path.name
            if not target.exists():
                target.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")

    records: list[dict[str, Any]] = []
    for path in sorted(run_case_dir.glob("*.json")):
        records.append(json.loads(path.read_text(encoding="utf-8")))

    if pending:
        new_records, summary = _run_pool(
            cases=pending,
            args=args,
            identity=identity,
            run_fingerprint=run_fingerprint,
            case_dir=run_case_dir,
            workers=workers,
            progress_label="run/w%d" % workers,
        )
        records.extend(new_records)
    else:
        summary = {
            "workers": workers,
            "planned": 0,
            "completed_ok": 0,
            "errors": 0,
            "note": "all cases reused from stress/run cache",
        }

    ok = [row for row in records if row.get("status") == "OK"]
    run_summary = {
        "schema_version": 1,
        "created_at": _utc_now(),
        "run_fingerprint": run_fingerprint,
        "workers": workers,
        "n_cases_total": len(cases),
        "n_reused": len(done_ids),
        "n_pending_ran": len(pending),
        "completed_ok": len(ok),
        "errors": len(records) - len(ok),
        "batch_summary": summary,
        "l2_metrics": _summarize_l2_metrics(ok),
        "mcq_note": "Run mapper phase for option-level @1/@2 after L2 joint ranking",
    }
    _atomic_json(args.output_dir / "run" / "summary.json", run_summary)
    print(json.dumps(run_summary, ensure_ascii=False, indent=2))
    return 0 if run_summary["errors"] == 0 else 1


def _split_case_text(case_text: str) -> tuple[str, str]:
    body = str(case_text).split("\nOptions:", 1)[0].strip()
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    if not lines:
        return body, ""
    question_index = None
    for index in range(len(lines) - 1, -1, -1):
        if "?" in lines[index]:
            question_index = index
            break
    if question_index is None:
        return body, lines[-1]
    question = " ".join(lines[question_index:])
    vignette = "\n".join(lines[:question_index]).strip()
    return vignette, question


class _MapperLLM:
    def __init__(self, cached: bfs_eval.CachedLLM) -> None:
        self.cached = cached

    def call_module(self, module: str, prompt: str, payload: Mapping[str, Any]):
        return self.cached.call(module, prompt, dict(payload))


def cmd_mapper(args: argparse.Namespace) -> int:
    cases = {case["id"]: case for case in _load_cases(args)}
    run_dir = args.output_dir / "run" / "cases"
    if not run_dir.is_dir():
        raise FileNotFoundError("missing run cases — execute `run` first")

    resolver = load_offline_resolver(ROOT)
    client = RobustLLMClient(
        model=args.model,
        call_timeout=args.call_timeout,
        max_retries=5,
        timeout_retry_cap=2,
        temperature=args.temperature,
    )
    cached = bfs_eval.CachedLLM(
        client,
        args.output_dir / "cache" / "mapper_llm_cache.json",
        args.model,
    )
    relation_prompt = (
        PROMPT_DIR / "answer_relation_mapper.txt"
    ).read_text(encoding="utf-8")
    critic_prompt = (
        PROMPT_DIR / "answer_relation_rag_critic.txt"
    ).read_text(encoding="utf-8")
    retrievers = {}
    if args.mapper_mode == "typed_llm_disagreement_rag":
        from agentclinic_tree_dx.knowledge.rag_retriever import RAGRetriever

        for name, path in (
            ("rag_index", ROOT / "data" / "corpus" / "rag_index"),
            ("cpg_index", ROOT / "data" / "corpus" / "cpg_index"),
        ):
            retriever = RAGRetriever(path, device="cpu")
            if retriever.is_ready:
                retrievers[name] = retriever
    mapper = RelationAwareAnswerMapper(
        resolver=resolver,
        llm=_MapperLLM(cached),
        relation_prompt=relation_prompt,
        critic_prompt=critic_prompt,
        retrievers=retrievers,
    )
    records: list[dict[str, Any]] = []
    adjudication_rows: list[dict[str, Any]] = []

    for path in sorted(run_dir.glob("*.json")):
        row = json.loads(path.read_text(encoding="utf-8"))
        if row.get("status") != "OK":
            continue
        case = cases.get(str(row["case_id"]))
        if case is None:
            continue
        options = da.normalize_options(case["annotation"]["source_options"])
        l2_block = row.get("l2") or {}
        final_state = _deserialize_state(
            l2_block.get("final_state") or row["bfs"]["final_state"]
        )
        tree = _serialize_state(final_state)
        ranking = list(
            l2_block.get("final_ranking")
            or row["bfs"].get("l2_ranking")
            or ()
        )
        leaves = leaf_rows_from_tree(tree, ranking)
        vignette, question = _split_case_text(str(case["case_text"]))
        projection = mapper.map(
            case_id=str(case["id"]),
            vignette=vignette,
            question=question,
            options=options,
            leaves=leaves,
            mode=args.mapper_mode,
        )
        gold_letter = str(case.get("gold_option") or "").upper()
        option_maps = projection.get("option_maps") or {}
        gold_map = option_maps.get(gold_letter) or {}
        gold_rank = gold_map.get("best_rank")
        gold_option_rank = int(gold_map.get("option_rank") or (len(options) + 1))
        top1 = bool(gold_rank is not None and gold_option_rank <= 1)
        top2 = bool(gold_rank is not None and gold_option_rank <= 2)
        record = {
            "case_id": case["id"],
            "mapper_mode": args.mapper_mode,
            "gold_letter": gold_letter,
            "gold_option_text": options.get(gold_letter),
            "gold_best_rank": gold_rank,
            "gold_option_rank": gold_option_rank,
            "option_top1": top1,
            "option_top2": top2,
            "option_rr": (1.0 / gold_option_rank if gold_rank is not None else 0.0),
            "projection": projection,
            "n_leaves": len(leaves),
        }
        records.append(record)
        _atomic_json(
            args.output_dir / "mapper" / "projections" / f"{case['id']}.json",
            record,
        )
        for letter, text in sorted(options.items()):
            mapped = option_maps.get(letter) or {}
            adjudication_rows.append({
                "case_id": case["id"],
                "option_letter": letter,
                "option_text": text,
                "mapper_mode": args.mapper_mode,
                "relation_type": mapped.get("relation_type", "unknown"),
                "matched_leaf_labels": sorted({
                    str(leaf["leaf_label"])
                    for leaf in leaves
                    if str(leaf["leaf_id"]) in set(mapped.get("clone_leaf_ids") or ())
                }),
                "best_rank": mapped.get("best_rank"),
                "option_rank": mapped.get("option_rank"),
                "confidence": mapped.get("confidence"),
                "rationale": mapped.get("rationale"),
                "review_status": "pending_human",
            })

    summary = {
        "schema_version": 1,
        "created_at": _utc_now(),
        "mapper_mode": args.mapper_mode,
        "n_cases": len(records),
        "option_top1": (
            round(sum(bool(row["option_top1"]) for row in records) / len(records), 4)
            if records else None
        ),
        "option_top2": (
            round(sum(bool(row["option_top2"]) for row in records) / len(records), 4)
            if records else None
        ),
        "note": (
            "option_top1/top2 are mapper-pre-adjudication; finalize after human "
            "relation review in adjudication sheet"
        ),
    }
    _atomic_json(args.output_dir / "mapper" / "records.json", {
        "records": records,
        "summary": summary,
    })
    _atomic_json(
        args.output_dir / "mapper" / "adjudication_blind_v1.json",
        {
            "schema_version": 1,
            "description": (
                "Gold-blind relation adjudication sheet for DiagnosisArena D2. "
                "Gold letters are intentionally absent. After human review, "
                "join gold_option from normalized_cases.json for @1/@2."
            ),
            "human_signed_off": False,
            "rows": adjudication_rows,
        },
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def cmd_adjudication(args: argparse.Namespace) -> int:
    blind_path = args.output_dir / "mapper" / "adjudication_blind_v1.json"
    if not blind_path.is_file():
        raise FileNotFoundError("run `mapper` first to create adjudication sheet")
    cases = {case["id"]: case for case in _load_cases(args)}
    mapper_records = json.loads(
        (args.output_dir / "mapper" / "records.json").read_text(encoding="utf-8"),
    ).get("records") or ()
    by_case = {str(row["case_id"]): row for row in mapper_records}
    blind = json.loads(blind_path.read_text(encoding="utf-8"))
    scored_rows = []
    for row in blind.get("rows") or ():
        case = cases.get(str(row["case_id"]))
        if case is None:
            continue
        scored_rows.append({
            **row,
            "gold_letter_for_scoring_only": str(case.get("gold_option") or ""),
            "mapper_option_top1": (by_case.get(str(row["case_id"])) or {}).get(
                "option_top1",
            ),
            "mapper_option_top2": (by_case.get(str(row["case_id"])) or {}).get(
                "option_top2",
            ),
        })
    out = {
        "schema_version": 1,
        "created_at": _utc_now(),
        "instructions": (
            "1) Review each row relation_type / matched_leaf_labels in the blind "
            "sheet. 2) Mark review_status=accepted|rejected|corrected. 3) Re-run "
            "score with accepted fixture to compute final @1/@2."
        ),
        "blind_sheet": str(blind_path.relative_to(ROOT)),
        "n_rows": len(scored_rows),
        "rows": scored_rows,
    }
    _atomic_json(args.output_dir / "adjudication" / "review_packet_v1.json", out)
    print(json.dumps({
        "n_rows": out["n_rows"],
        "blind_sheet": out["blind_sheet"],
        "next_step": "human edit adjudication_blind_v1.json then score",
    }, ensure_ascii=False, indent=2))
    return 0


def cmd_all(args: argparse.Namespace) -> int:
    steps: list[tuple[str, Callable[[argparse.Namespace], int]]] = [
        ("prepare", cmd_prepare),
        ("stress", cmd_stress),
        ("run", cmd_run),
        ("mapper", cmd_mapper),
        ("adjudication", cmd_adjudication),
    ]
    for name, fn in steps:
        if getattr(args, "skip_stress", False) and name == "stress":
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
        choices=("prepare", "stress", "run", "mapper", "adjudication", "all"),
        help="pipeline phase to execute",
    )
    parser.add_argument("--parquet", type=Path, default=DEFAULT_PARQUET)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--cases", default="", help="comma-separated case ids")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--workers", type=int, default=0)
    parser.add_argument("--call-timeout", type=float, default=240.0)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--refresh-cases", action="store_true")
    parser.add_argument("--rag", action="store_true", default=True)
    parser.add_argument("--entry-gate", default="all_findings")
    parser.add_argument("--evidence-source", default="legacy")
    parser.add_argument("--evidence-lane", default="clinical")
    parser.add_argument(
        "--p5kg-manifest",
        type=Path,
        default=ROOT / "data" / "eval" / "p5_external_asset_manifest.json",
    )
    parser.add_argument("--allow-empty-p5", action="store_true")
    parser.add_argument("--l2-candidate-budget", type=int, default=24)
    parser.add_argument("--l2-snippet-budget", type=int, default=8)
    parser.add_argument("--stress-cases", type=int, default=5)
    parser.add_argument("--stress-workers", default="1,2,3,4")
    parser.add_argument(
        "--mapper-mode",
        default="typed_llm",
        choices=["deterministic_gold_blind", "typed_llm", "typed_llm_disagreement_rag"],
    )
    parser.add_argument("--skip-stress", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    dispatch = {
        "prepare": cmd_prepare,
        "stress": cmd_stress,
        "run": cmd_run,
        "mapper": cmd_mapper,
        "adjudication": cmd_adjudication,
        "all": cmd_all,
    }
    return dispatch[args.phase](args)


if __name__ == "__main__":
    raise SystemExit(main())
