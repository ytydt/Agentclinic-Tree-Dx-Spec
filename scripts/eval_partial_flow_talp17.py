"""Bounded TALP partial-flow evaluation over the fixed 17-case corpus.

This harness intentionally runs the production controller only through the
second EvidenceAnnotator checkpoint.  It never invokes termination, final
aggregation, or AnswerMapper.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

BASE_CASES_PATH = PROJECT_ROOT / "data" / "eval" / "talp_discrimination_cases.json"
EXPANSION_CASES_PATH = (
    PROJECT_ROOT / "data" / "eval" / "talp_medxpert_expansion_cases_v2.json"
)
BRANCH_HARNESS_PATH = PROJECT_ROOT / "scripts" / "eval_branch_creation_medbullets.py"
PIPELINE_HARNESS_PATH = PROJECT_ROOT / "scripts" / "eval_pipeline_medbullets.py"
DEFAULT_MODEL = "meta-llama/llama-3.3-70b-instruct"
DEFAULT_PROFILES = ("p5_headline", "g2ur")
BRANCH_MODE = "recall_hints_gap"
TRACE_SCHEMA_VERSION = 1

_MODULE_CACHE: dict[str, Any] = {}


def _load_module(name: str, path: Path):
    cached = _MODULE_CACHE.get(name)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import harness module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _MODULE_CACHE[name] = module
    return module


def _pipeline_module():
    return _load_module("talp17_pipeline_medbullets", PIPELINE_HARNESS_PATH)


def _branch_module():
    return _load_module("talp17_branch_creation_medbullets", BRANCH_HARNESS_PATH)


def _options_text(vignette: str, options: dict[str, str]) -> str:
    lines = "\n".join(f"{key}. {value}" for key, value in sorted(options.items()))
    return f"{vignette.strip()}\n\nOptions:\n{lines}\n"


def assemble_cases(
    *,
    base_path: Path = BASE_CASES_PATH,
    expansion_path: Path = EXPANSION_CASES_PATH,
    medbullets_cases: list[dict] | None = None,
) -> list[dict]:
    """Join the nine MedBullets bases and append eight embedded expansions."""
    base_doc = json.loads(base_path.read_text(encoding="utf-8"))
    expansion_doc = json.loads(expansion_path.read_text(encoding="utf-8"))
    if medbullets_cases is None:
        medbullets_cases = _pipeline_module().load_dx_cases()

    by_answer: dict[str, list[dict]] = {}
    for source_case in medbullets_cases:
        by_answer.setdefault(str(source_case.get("answer", "")).strip(), []).append(
            source_case
        )

    assembled: list[dict] = []
    for annotation in base_doc.get("cases", []):
        matches = by_answer.get(str(annotation.get("gold_option", "")).strip(), [])
        if len(matches) != 1:
            raise ValueError(
                f"{annotation.get('id')}: gold_option join expected one MedBullets "
                f"case, got {len(matches)}"
            )
        source = matches[0]
        assembled.append({
            "id": annotation["id"],
            "corpus": "medbullets",
            "source_case_idx": annotation.get("case_idx"),
            "gold": annotation["gold"],
            "gold_option": annotation["gold_option"],
            "case_text": _pipeline_module().build_case_text(source),
            "annotation": annotation,
        })

    for annotation in expansion_doc.get("cases", []):
        options = annotation.get("source_options")
        vignette = annotation.get("vignette")
        if not isinstance(options, dict) or not options or not vignette:
            raise ValueError(f"{annotation.get('id')}: missing vignette/source_options")
        assembled.append({
            "id": annotation["id"],
            "corpus": annotation.get("corpus", "medxpertqar_hard"),
            "source_case_idx": annotation.get("case_idx"),
            "gold": annotation["gold"],
            "gold_option": annotation["gold_option"],
            "case_text": _options_text(vignette, options),
            "annotation": annotation,
        })

    ids = [case["id"] for case in assembled]
    if len(assembled) != 17 or len(set(ids)) != 17:
        raise ValueError(
            f"TALP17 corpus must contain 17 unique cases, got {len(assembled)}"
        )
    if sum(case["corpus"] == "medbullets" for case in assembled) != 9:
        raise ValueError("TALP17 corpus must contain exactly nine MedBullets bases")
    return assembled


def build_profile_controller(
    model: str,
    profile: str,
    *,
    max_timesteps: int = 2,
    force_expand_all_l1: bool = True,
    controller_builder: Callable[..., Any] | None = None,
):
    """Reuse the production recall-hints-gap builder with harness-only overrides."""
    builder = controller_builder or _branch_module().build_controller
    overrides = {
        "talp_disc_profile": profile,
        "partial_flow": True,
        "max_timesteps": max_timesteps,
        "force_expand_all_l1": force_expand_all_l1,
        "stop_after_evidence": True,
    }
    controller, env, config, provenance = builder(
        model,
        branch_mode=BRANCH_MODE,
        config_overrides=overrides,
    )
    for key, value in overrides.items():
        if getattr(config, key) != value:
            raise AssertionError(f"controller override not applied: {key}")
    return controller, env, config, provenance


def _sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def asset_fingerprints() -> dict[str, dict[str, Any]]:
    paths = {
        "base_cases": BASE_CASES_PATH,
        "expansion_cases": EXPANSION_CASES_PATH,
        "branch_algorithm_source": BRANCH_HARNESS_PATH,
        "p5_manifest": PROJECT_ROOT / "data" / "eval" / "p5_external_asset_manifest.json",
        "g2ur_manifest": (
            PROJECT_ROOT
            / "data"
            / "cceg"
            / "unary_v1"
            / "p5kg_research_asset_manifest_v2.json"
        ),
        "g2ur_claims": (
            PROJECT_ROOT
            / "data"
            / "cceg"
            / "unary_v1"
            / "claims.research_validated.jsonl"
        ),
    }
    return {
        name: {
            "path": str(path.relative_to(PROJECT_ROOT)),
            "sha256": _sha256(path),
            "size": path.stat().st_size if path.is_file() else None,
        }
        for name, path in paths.items()
    }


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temp.open("w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


def _run_with_timeout(fn: Callable[[], dict], timeout: float) -> dict:
    if timeout <= 0:
        return fn()
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(fn)
    try:
        return future.result(timeout=timeout)
    except FutureTimeout:
        future.cancel()
        raise TimeoutError(f"case exceeded {timeout:g}s")
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def _profile_metrics(result: dict, max_timesteps: int) -> dict:
    audits = result.get("discrimination_audit") or []
    annotator = [row for row in audits if row.get("phase") == "evidence_annotator"]
    covered_turns = {row.get("timestep") for row in annotator}
    rules = sum(
        len(row.get("discriminator_rules") or []) + len(row.get("ruleout_rules") or [])
        for row in annotator
    )
    provenance = sum(len(row.get("evidence_provenance") or []) for row in annotator)
    return {
        "evidence_annotator_audited_turns": len(covered_turns),
        "evidence_annotator_coverage": len(covered_turns) / max_timesteps,
        "profile_rule_hits": rules,
        "profile_provenance_hits": provenance,
        "profile_phases": sorted({row.get("phase", "") for row in audits}),
    }


def _make_record(
    *,
    profile: str,
    case: dict,
    result: dict,
    duration: float,
    judge: Callable[[str, list[str]], int],
    run_fingerprint: str,
    max_timesteps: int,
    provenance: dict,
) -> dict:
    if result.get("answer_mapper_called") is not False:
        raise AssertionError("partial flow invoked AnswerMapper")
    expansion = result.get("l1_expansion_audit") or {}
    if expansion.get("l1_expansion_rate") != 1.0:
        raise AssertionError(
            f"L1 expansion rate must be 100%, got "
            f"{expansion.get('l1_expansion_rate')!r}"
        )

    labels = [row.get("label", "") for row in result.get("l1_tree") or []]
    assigned_idx = judge(case["gold"], labels) if labels else -1
    l1_hit = isinstance(assigned_idx, int) and 0 <= assigned_idx < len(labels)
    profile_metrics = _profile_metrics(result, max_timesteps)
    safe_result = dict(result)
    for forbidden in ("final_answer", "answer_mapping", "pred", "prediction"):
        safe_result.pop(forbidden, None)
    return {
        "schema_version": TRACE_SCHEMA_VERSION,
        "status": "OK",
        "profile": profile,
        "case_id": case["id"],
        "corpus": case["corpus"],
        "source_case_idx": case["source_case_idx"],
        "gold_diagnosis": case["gold"],
        "run_fingerprint": run_fingerprint,
        "branch_algorithm": {
            "builder": "scripts/eval_branch_creation_medbullets.py:build_controller",
            "branch_mode": BRANCH_MODE,
        },
        "branch_provenance": dict(provenance.get("last") or {}),
        "metrics": {
            "l1_recall": bool(l1_hit),
            "l1_assigned_index": assigned_idx if l1_hit else -1,
            "l1_assigned_label": labels[assigned_idx] if l1_hit else None,
            "l1_expansion_rate": expansion["l1_expansion_rate"],
            "l2_leaf_count": len(result.get("l2_tree") or []),
            **profile_metrics,
        },
        "duration_seconds": round(duration, 3),
        "trace": safe_result,
    }


def summarize(records: list[dict], *, planned: int) -> dict:
    def aggregate(rows: list[dict]) -> dict:
        ok = [row for row in rows if row.get("status") == "OK"]
        metrics = [row["metrics"] for row in ok]
        return {
            "planned": len(rows),
            "completed": len(ok),
            "errors": sum(row.get("status") == "ERROR" for row in rows),
            "timeouts": sum(row.get("status") == "TIMEOUT" for row in rows),
            "l1_recall": (
                sum(bool(item["l1_recall"]) for item in metrics) / len(metrics)
                if metrics else None
            ),
            "l1_expansion_rate": (
                sum(item["l1_expansion_rate"] for item in metrics) / len(metrics)
                if metrics else None
            ),
            "l2_leaf_count": sum(item["l2_leaf_count"] for item in metrics),
            "evidence_annotator_coverage": (
                sum(item["evidence_annotator_coverage"] for item in metrics)
                / len(metrics)
                if metrics else None
            ),
            "profile_rule_hits": sum(item["profile_rule_hits"] for item in metrics),
            "profile_provenance_hits": sum(
                item["profile_provenance_hits"] for item in metrics
            ),
            "duration_seconds": round(
                sum(float(row.get("duration_seconds", 0.0)) for row in rows), 3
            ),
        }

    profiles = sorted({row.get("profile", "") for row in records})
    summary = {
        "schema_version": TRACE_SCHEMA_VERSION,
        "planned_traces": planned,
        "written_traces": len(records),
        "overall": aggregate(records),
        "by_profile": {
            profile: aggregate(
                [row for row in records if row.get("profile") == profile]
            )
            for profile in profiles
        },
    }
    summary["overall"]["planned"] = planned
    return summary


def _select_cases(cases: list[dict], selector: str, limit: int) -> list[dict]:
    selected = cases
    if selector:
        tokens = {token.strip() for token in selector.split(",") if token.strip()}
        wanted_indices = {int(token) for token in tokens if token.isdigit()}
        wanted_ids = tokens - {str(index) for index in wanted_indices}
        selected = [
            case
            for index, case in enumerate(cases)
            if index in wanted_indices or case["id"] in wanted_ids
        ]
        unresolved = wanted_ids - {case["id"] for case in selected}
        if unresolved:
            raise ValueError(f"unknown case ids: {sorted(unresolved)}")
    if limit > 0:
        selected = selected[:limit]
    return selected


def run_harness(
    *,
    output_dir: Path,
    tag: str,
    profiles: tuple[str, ...] = DEFAULT_PROFILES,
    model: str = DEFAULT_MODEL,
    cases_selector: str = "",
    limit: int = 0,
    max_timesteps: int = 2,
    force_expand_all_l1: bool = True,
    case_timeout: float = 0.0,
    resume: bool = False,
    dry_run: bool = False,
    controller_builder: Callable[..., Any] | None = None,
    judge_factory: Callable[[str], Callable[[str, list[str]], int]] | None = None,
    assembled_cases: list[dict] | None = None,
) -> tuple[dict, dict]:
    if set(profiles) - {"p5_headline", "g2ur"}:
        raise ValueError("profiles must contain only p5_headline and/or g2ur")
    if max_timesteps < 1:
        raise ValueError("max_timesteps must be positive")
    cases = _select_cases(assembled_cases or assemble_cases(), cases_selector, limit)
    run_dir = output_dir / tag
    trace_dir = run_dir / "traces"
    fingerprints = asset_fingerprints()
    identity = {
        "trace_schema_version": TRACE_SCHEMA_VERSION,
        "model": model,
        "profiles": list(profiles),
        "branch_mode": BRANCH_MODE,
        "max_timesteps": max_timesteps,
        "force_expand_all_l1": force_expand_all_l1,
        "asset_fingerprints": fingerprints,
    }
    run_fingerprint = hashlib.sha256(
        json.dumps(identity, sort_keys=True).encode("utf-8")
    ).hexdigest()
    manifest = {
        **identity,
        "run_fingerprint": run_fingerprint,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "tag": tag,
        "case_ids": [case["id"] for case in cases],
        "planned_traces": len(profiles) * len(cases),
        "dry_run": dry_run,
        "branch_algorithm": {
            "builder": "scripts/eval_branch_creation_medbullets.py:build_controller",
            "branch_mode": BRANCH_MODE,
            "reuse_contract": "production config plus profile/partial overrides only",
        },
    }
    _atomic_json(run_dir / "manifest.json", manifest)

    records: list[dict] = []
    if not dry_run:
        make_judge = judge_factory or _branch_module().make_judge
        judge = make_judge(model)
        for profile in profiles:
            def fresh_controller():
                return build_profile_controller(
                    model,
                    profile,
                    max_timesteps=max_timesteps,
                    force_expand_all_l1=force_expand_all_l1,
                    controller_builder=controller_builder,
                )

            controller, env, _config, provenance = fresh_controller()
            for case in cases:
                trace_path = trace_dir / f"{profile}__{case['id']}.json"
                if resume and trace_path.is_file():
                    try:
                        previous = json.loads(trace_path.read_text(encoding="utf-8"))
                    except (OSError, json.JSONDecodeError):
                        previous = {}
                    if (
                        previous.get("status") == "OK"
                        and previous.get("run_fingerprint") == run_fingerprint
                    ):
                        records.append(previous)
                        continue

                started = time.monotonic()
                try:
                    def execute() -> dict:
                        from agentclinic_tree_dx.state import DiagnosticState

                        env.set_case(case["case_text"])
                        return controller.run(
                            DiagnosticState(case_id=f"{profile}::{case['id']}")
                        )

                    result = _run_with_timeout(execute, case_timeout)
                    record = _make_record(
                        profile=profile,
                        case=case,
                        result=result,
                        duration=time.monotonic() - started,
                        judge=judge,
                        run_fingerprint=run_fingerprint,
                        max_timesteps=max_timesteps,
                        provenance=provenance,
                    )
                except Exception as exc:
                    status = "TIMEOUT" if isinstance(exc, TimeoutError) else "ERROR"
                    record = {
                        "schema_version": TRACE_SCHEMA_VERSION,
                        "status": status,
                        "profile": profile,
                        "case_id": case["id"],
                        "corpus": case["corpus"],
                        "source_case_idx": case["source_case_idx"],
                        "run_fingerprint": run_fingerprint,
                        "error": f"{type(exc).__name__}: {exc}",
                        "duration_seconds": round(time.monotonic() - started, 3),
                    }
                    # A timed-out thread cannot be killed safely.  Never share
                    # its controller or thread-local environment with later
                    # cases; construct a clean production instance instead.
                    if status == "TIMEOUT":
                        controller, env, _config, provenance = fresh_controller()
                _atomic_json(trace_path, record)
                records.append(record)

    summary = summarize(records, planned=manifest["planned_traces"])
    summary["dry_run"] = dry_run
    summary["run_fingerprint"] = run_fingerprint
    _atomic_json(run_dir / "summary.json", summary)
    return summary, manifest


def _parse_profiles(value: str) -> tuple[str, ...]:
    profiles = tuple(item.strip() for item in value.split(",") if item.strip())
    if not profiles:
        raise argparse.ArgumentTypeError("at least one profile is required")
    invalid = set(profiles) - {"p5_headline", "g2ur"}
    if invalid:
        raise argparse.ArgumentTypeError(f"unsupported profiles: {sorted(invalid)}")
    return profiles


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profiles", type=_parse_profiles, default=DEFAULT_PROFILES)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument(
        "--branch-mode",
        choices=[BRANCH_MODE],
        default=BRANCH_MODE,
    )
    parser.add_argument("--max-timesteps", type=int, default=2)
    parser.add_argument(
        "--force-expand-all-l1",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "logs" / "partial_flow_talp17",
    )
    parser.add_argument("--tag", default="talp17")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--case-timeout", type=float, default=0.0)
    parser.add_argument("--cases", default="")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    summary, manifest = run_harness(
        output_dir=args.output_dir,
        tag=args.tag,
        profiles=args.profiles,
        model=args.model,
        cases_selector=args.cases,
        limit=args.limit,
        max_timesteps=args.max_timesteps,
        force_expand_all_l1=args.force_expand_all_l1,
        case_timeout=args.case_timeout,
        resume=args.resume,
        dry_run=args.dry_run,
    )
    print(json.dumps(
        {
            "run_dir": str(args.output_dir / args.tag),
            "planned_traces": manifest["planned_traces"],
            "written_traces": summary["written_traces"],
            "dry_run": args.dry_run,
        },
        ensure_ascii=False,
    ))
    sys.stdout.flush()
    if summary["overall"]["timeouts"]:
        # Timed-out controller calls run in non-daemon threads and cannot be
        # killed safely.  All atomic traces and summaries are durable now, so
        # avoid waiting for abandoned remote LLM calls during CLI shutdown.
        os._exit(0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
