#!/usr/bin/env python3
"""Heterogeneous clinical-relation screen for E12.

The screen is a queue-expansion subcontractor.  It never replaces the strict
endpoint or root-owned adjudication.  Candidate IDs come from the frozen E12
registry; historical S3-only creations receive isolated ``S3X`` IDs.
"""
from __future__ import annotations

import argparse
import json
import sys
import tarfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

if __package__ in {None, ""}:
    _ROOT_FOR_IMPORT = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(_ROOT_FOR_IMPORT))
    sys.path.insert(0, str(_ROOT_FOR_IMPORT / "src"))

from analysis.mechanism_v2.common import file_sha256  # noqa: E402
from analysis.mechanism_v2.e12_e7_factorial import ARMS, DEFAULT_OUT  # noqa: E402
from analysis.mechanism_v2.online_runner import OnlineJSONCaller, read_jsonl, write_jsonl  # noqa: E402
from analysis.mechanism_v2.runtime_contract import (  # noqa: E402
    aggregate_telemetry,
    atomic_json,
    dependency_capabilities,
    sha256_text,
    stable_seed,
    validate_workers,
)


DEFAULT_MODEL = "google/gemini-2.5-flash"
RELATIONS = (
    "exact_equivalent",
    "acceptable_clinical_variant",
    "broader_or_narrower_not_equivalent",
    "related_not_equivalent",
    "unrelated",
    "uncertain",
)
PROMPT = """Role: conservative independent clinical terminology auditor.

For every candidate ID, compare the candidate diagnosis with the reference
diagnosis in the vignette. This is evaluation, not diagnosis generation.
Choose exactly one relation:
- exact_equivalent: same entity despite ordinary synonym/abbreviation;
- acceptable_clinical_variant: clinically acceptable wording/specificity for
  this case without losing its defining disease, anatomy, cause, or subtype;
- broader_or_narrower_not_equivalent: same family but materially wrong scope;
- related_not_equivalent: plausible related diagnosis but a different entity;
- unrelated; or uncertain.

Shared words, anatomy, manifestation, syndrome family, organism, or causal
association alone do not establish equivalence. Evaluate each supplied ID
exactly once. Return JSON only:
{"candidate_relations":[{"candidate_id":"D1","relation":"one allowed label","reason":"brief case-specific reason"}],"screen_note":"brief ambiguity note"}
"""


def _validator(allowed: set[str]):
    def validate(response: Mapping[str, Any]) -> str | None:
        rows = response.get("candidate_relations")
        if not isinstance(rows, list):
            return "candidate_relations must be a list"
        seen: list[str] = []
        for row in rows:
            if not isinstance(row, Mapping):
                return "candidate relation is not an object"
            candidate_id = str(row.get("candidate_id") or "")
            relation = str(row.get("relation") or "")
            if candidate_id not in allowed:
                return f"unknown candidate ID {candidate_id!r}"
            if relation not in RELATIONS:
                return f"invalid relation {relation!r}"
            if not str(row.get("reason") or "").strip():
                return f"missing reason for {candidate_id}"
            seen.append(candidate_id)
        if len(seen) != len(set(seen)) or set(seen) != allowed:
            return "candidate IDs must appear exactly once"
        return None
    return validate


def case_documents(out: Path) -> list[dict[str, Any]]:
    fixed = read_jsonl(out / "fixed_inputs.jsonl")
    arm_rows = {
        arm: {
            str(row["case_key"]): row
            for row in read_jsonl(out / "arms" / arm / "case_results.jsonl")
        }
        for arm in ARMS
    }
    documents: list[dict[str, Any]] = []
    for job in fixed:
        case_key = str(job["case_key"])
        used_ids = {
            str(candidate_id)
            for pool in job["pools"].values()
            for candidate_id in pool["candidate_ids_by_priority"]
        }
        registry = {str(row["candidate_id"]): row for row in job["registry"]}
        candidates = [
            {
                "candidate_id": candidate_id,
                "label": str(registry[candidate_id]["label"]),
                "origin": "frozen_s2_pool",
            }
            for candidate_id in sorted(used_ids)
        ]
        for index, label in enumerate(job["s3_unmatched_labels"], 1):
            candidates.append({
                "candidate_id": f"S3X{index}",
                "label": str(label),
                "origin": "historical_s3_only_excluded_from_e12",
            })
        documents.append({
            "case_key": case_key,
            "family": job["family"],
            "vignette": job["representations"]["raw"]["content"],
            "reference_diagnosis": arm_rows["raw_k5_first"][case_key]["gold"],
            "candidates": candidates,
            "arm_outcomes": {
                arm: {
                    "success": arm_rows[arm][case_key]["success"],
                    "champion_id": arm_rows[arm][case_key]["champion_id"],
                    "runner_up_label": arm_rows[arm][case_key]["runner_up_label"],
                    "gold_top1": arm_rows[arm][case_key]["gold_top1"],
                    "gold_exposure_hit": arm_rows[arm][case_key]["gold_exposure_hit"],
                }
                for arm in ARMS
            },
        })
    return sorted(documents, key=lambda row: str(row["case_key"]))


def _archive(out: Path) -> tuple[Path, Path]:
    archive = out / "E12_SEMANTIC_SCREEN_RAW.tar.gz"
    sha = out / "E12_SEMANTIC_SCREEN_RAW.tar.gz.sha256"
    with tarfile.open(archive, "w:gz") as bundle:
        bundle.add(out / "semantic_screen", arcname="semantic_screen")
    sha.write_text(f"{file_sha256(archive)}  {archive.name}\n", encoding="utf-8")
    return archive, sha


def run_screen(out: Path, model: str, workers: int) -> list[dict[str, Any]]:
    documents = case_documents(out)
    screen_dir = out / "semantic_screen"
    screen_dir.mkdir(parents=True, exist_ok=True)
    result_path = screen_dir / "screen_results.jsonl"
    if result_path.is_file():
        rows = read_jsonl(result_path)
        if len(rows) != len(documents):
            raise AssertionError("partial semantic screen requires cache resume, not result reuse")
        _archive(out)
        return rows
    log_path = screen_dir / "run.log"
    log_path.write_text(
        f"started_at_utc={datetime.now(timezone.utc).isoformat()}\n"
        f"model={model}\nworkers={workers}\njobs={len(documents)}\n",
        encoding="utf-8",
    )
    telemetry_path = screen_dir / "telemetry.jsonl"
    caller = OnlineJSONCaller(
        out_dir=screen_dir,
        model=model,
        telemetry_path=telemetry_path,
        temperature=0.0,
        call_timeout=180,
        max_retries=2,
    )

    def one(document: Mapping[str, Any]) -> dict[str, Any]:
        candidates = list(document["candidates"])
        allowed = {str(row["candidate_id"]) for row in candidates}
        outcome = caller.call(
            module="E12ClinicalRelationScreen",
            prompt=PROMPT,
            payload={
                "vignette": str(document["vignette"]),
                "reference_diagnosis": str(document["reference_diagnosis"]),
                "candidate_registry": candidates,
            },
            validator=_validator(allowed),
        )
        return {
            "case_key": document["case_key"],
            "family": document["family"],
            "reference_diagnosis": document["reference_diagnosis"],
            "candidate_registry": candidates,
            "arm_outcomes": document["arm_outcomes"],
            "success": outcome.success,
            "error": outcome.error,
            "screen_response": outcome.response,
            "cache_hit": outcome.cache_hit,
            "cache_key": outcome.cache_key,
            "payload_sha256": outcome.payload_sha256,
        }

    rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(one, document): document["case_key"] for document in documents}
        for done, future in enumerate(as_completed(futures), 1):
            rows.append(future.result())
            if done % 25 == 0 or done == len(documents):
                line = f"completed={done}/{len(documents)} failures={sum(not row['success'] for row in rows)}"
                print(line, flush=True)
                with log_path.open("a", encoding="utf-8") as stream:
                    stream.write(line + "\n")
    rows.sort(key=lambda row: str(row["case_key"]))
    write_jsonl(result_path, rows)
    relation_counts = Counter(
        str(item.get("relation"))
        for row in rows
        for item in (row["screen_response"].get("candidate_relations") or [])
    )
    atomic_json(screen_dir / "telemetry_summary.json", aggregate_telemetry(read_jsonl(telemetry_path)))
    atomic_json(screen_dir / "summary.json", {
        "experiment_id": "E12-semantic-screen",
        "role": "heterogeneous queue-expansion subcontractor; root remains final auditor",
        "model": model,
        "n_cases": len(rows),
        "n_success": sum(bool(row["success"]) for row in rows),
        "relation_counts": dict(sorted(relation_counts.items())),
        "prompt_sha256": sha256_text(PROMPT),
        "capabilities": dependency_capabilities(),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
    })
    with log_path.open("a", encoding="utf-8") as stream:
        stream.write(f"completed_at_utc={datetime.now(timezone.utc).isoformat()}\n")
    _archive(out)
    return rows


def build_queue(out: Path) -> list[dict[str, Any]]:
    base = {str(row["case_key"]): row for row in read_jsonl(out / "root_audit_queue.jsonl")}
    documents = {str(row["case_key"]): row for row in case_documents(out)}
    screens = {str(row["case_key"]): row for row in read_jsonl(out / "semantic_screen" / "screen_results.jsonl")}
    reasons: dict[str, set[str]] = {
        key: set(row["queue_reasons"]) for key, row in base.items()
    }
    negative_by_family: dict[str, list[str]] = {"DA": [], "MCR": []}
    accepted_or_ambiguous = {
        "exact_equivalent", "acceptable_clinical_variant",
        "broader_or_narrower_not_equivalent", "uncertain",
    }
    for key, screen in screens.items():
        relation_by_id = {
            str(row.get("candidate_id")): str(row.get("relation"))
            for row in screen["screen_response"].get("candidate_relations") or []
        }
        selected_ids = {
            str(view.get("champion_id") or "")
            for view in screen["arm_outcomes"].values()
            if view.get("success")
        }
        selected_positive = any(
            relation_by_id.get(candidate_id) in accepted_or_ambiguous
            for candidate_id in selected_ids
        )
        any_s3_positive = any(
            candidate_id.startswith("S3X") and relation in accepted_or_ambiguous
            for candidate_id, relation in relation_by_id.items()
        )
        if selected_positive:
            reasons.setdefault(key, set()).add("screen_selected_clinical_positive_or_scope_ambiguous")
        if any_s3_positive:
            reasons.setdefault(key, set()).add("screen_s3_only_candidate_positive_or_scope_ambiguous")
        if not screen["success"]:
            reasons.setdefault(key, set()).add("semantic_screen_failure")
        if not selected_positive and not any_s3_positive and screen["success"]:
            negative_by_family[str(screen["family"])].append(key)
    for family in ("DA", "MCR"):
        selected = sorted(
            negative_by_family[family],
            key=lambda key: (stable_seed("E12-negative-screen-root-sample-v1", key), key),
        )[:15]
        for key in selected:
            reasons.setdefault(key, set()).add("frozen_negative_screen_audit")
    queue: list[dict[str, Any]] = []
    for key in sorted(reasons):
        base_row = base.get(key)
        document = documents[key]
        queue.append({
            "case_key": key,
            "family": document["family"],
            "gold": document["reference_diagnosis"],
            "vignette": document["vignette"],
            "candidate_registry": document["candidates"],
            "arm_outcomes": document["arm_outcomes"],
            "queue_reasons": sorted(reasons[key]),
            "strict_audit_context": base_row,
            "semantic_screen": screens[key],
        })
    write_jsonl(out / "clinical_audit_queue.jsonl", queue)
    atomic_json(out / "clinical_audit_queue_summary.json", {
        "n": len(queue),
        "reason_counts": dict(sorted(Counter(reason for row in queue for reason in row["queue_reasons"]).items())),
        "negative_screen_sample_per_family": 15,
        "queue_sha256": file_sha256(out / "clinical_audit_queue.jsonl"),
    })
    return queue


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--workers", type=int, default=50)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--queue", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    workers = validate_workers(args.workers, rag=False)
    out = args.out.resolve()
    if args.run:
        rows = run_screen(out, args.model, workers)
        print(f"semantic_screen={sum(row['success'] for row in rows)}/{len(rows)}")
    if args.queue:
        queue = build_queue(out)
        print(f"clinical_audit_queue={len(queue)}")
    if not (args.run or args.queue):
        raise SystemExit("select --run and/or --queue")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
