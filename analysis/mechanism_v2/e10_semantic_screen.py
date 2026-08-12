#!/usr/bin/env python3
"""Heterogeneous semantic recall screen for E10 manual adjudication.

This model is a queue-expansion subcontractor only.  Its labels never replace
the frozen strict endpoint or the root auditor's final clinical adjudication.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

if __package__ in {None, ""}:
    _ROOT_FOR_IMPORT = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(_ROOT_FOR_IMPORT))
    sys.path.insert(0, str(_ROOT_FOR_IMPORT / "src"))

from analysis.mechanism_v2.common import ROOT, clean_vignette, load_normalized_cases  # noqa: E402
from analysis.mechanism_v2.e10_mac_factorial import (  # noqa: E402
    ARMS,
    DEFAULT_OUT,
    DEVELOPMENT_SLICES,
    load_jobs,
)
from analysis.mechanism_v2.online_runner import OnlineJSONCaller, read_jsonl, write_jsonl  # noqa: E402
from analysis.mechanism_v2.runtime_contract import (  # noqa: E402
    aggregate_telemetry,
    atomic_json,
    sha256_text,
    stable_seed,
    validate_workers,
)


DEFAULT_MODEL = "deepseek/deepseek-v4-flash-0731"
RELATIONS = (
    "exact_equivalent",
    "acceptable_clinical_variant",
    "broader_or_narrower_not_equivalent",
    "related_not_equivalent",
    "unrelated",
    "uncertain",
)
SCREEN_PROMPT = """Role: conservative clinical terminology screen for a diagnostic study.

Compare every supplied candidate diagnosis with the reference diagnosis in the
context of the vignette. This is evaluation, not diagnosis generation. Classify
names as:
- exact_equivalent: same disease/entity despite ordinary synonym, spelling or
  expansion differences;
- acceptable_clinical_variant: a wording or specificity variant that would be
  accepted as the same case diagnosis in this vignette;
- broader_or_narrower_not_equivalent: ancestor/descendant but materially loses
  or adds the case-defining subtype;
- related_not_equivalent: related differential but a different entity;
- unrelated; or uncertain.

Be conservative: shared anatomy, syndrome family, organism, symptom, or a mere
substring does not establish equivalence. Evaluate each supplied ID exactly
once. Return JSON only:
{"candidate_relations":[
 {"candidate_id":"I1","relation":"one allowed label","reason":"brief"}
],"screen_note":"brief ambiguity note"}
"""


def _validator(allowed: set[str]):
    def validate(response: Mapping[str, Any]) -> str | None:
        rows = response.get("candidate_relations")
        if not isinstance(rows, list):
            return "candidate_relations must be a list"
        seen: list[str] = []
        for row in rows:
            if not isinstance(row, Mapping):
                return "relation row is not an object"
            candidate_id = str(row.get("candidate_id") or "")
            relation = str(row.get("relation") or "")
            if candidate_id not in allowed:
                return f"unknown candidate ID {candidate_id}"
            if relation not in RELATIONS:
                return f"invalid relation {relation}"
            seen.append(candidate_id)
        if len(seen) != len(set(seen)) or set(seen) != allowed:
            return "candidate IDs must appear exactly once"
        return None
    return validate


def case_documents(out: Path) -> list[dict[str, Any]]:
    jobs, _ = load_jobs()
    job_by_key = {str(row["case_key"]): row for row in jobs}
    arm_rows = {
        arm: {str(row["case_key"]): row for row in read_jsonl(out / "arms" / arm / "case_results.jsonl")}
        for arm in ARMS
    }
    documents: list[dict[str, Any]] = []
    for case_key in sorted(job_by_key):
        job = job_by_key[case_key]
        candidates: list[dict[str, str]] = []
        labels_seen: dict[str, str] = {}
        for prefix, arm in (("I", "isolated_rrf"), ("S", "sequential_rrf")):
            for index, row in enumerate(arm_rows[arm][case_key]["registry"], 1):
                candidate_id = f"{prefix}{index}"
                label = str(row["label"])
                candidates.append({"candidate_id": candidate_id, "label": label, "history": "isolated" if prefix == "I" else "sequential"})
                labels_seen[candidate_id] = label
        documents.append(
            {
                "case_key": case_key,
                "family": job["family"],
                "vignette": job["vignette"],
                "reference_diagnosis": job["gold"],
                "candidates": candidates,
                "candidate_labels": labels_seen,
                "strict": {
                    arm: {
                        "top2_labels": arm_rows[arm][case_key]["top2_labels"],
                        "top1": arm_rows[arm][case_key]["gold_top1"],
                        "top2": arm_rows[arm][case_key]["gold_top2"],
                        "union_exposed": arm_rows[arm][case_key]["gold_union_exposed"],
                    }
                    for arm in ARMS
                },
            }
        )
    return documents


def run_screen(out: Path, model: str, workers: int) -> list[dict[str, Any]]:
    documents = case_documents(out)
    screen_dir = out / "semantic_screen"
    telemetry_path = screen_dir / "telemetry.jsonl"
    caller = OnlineJSONCaller(
        out_dir=screen_dir,
        model=model,
        telemetry_path=telemetry_path,
        temperature=0.0,
        call_timeout=180,
        max_retries=2,
    )

    def worker(document: Mapping[str, Any]) -> dict[str, Any]:
        candidates = list(document["candidates"])
        allowed = {str(row["candidate_id"]) for row in candidates}
        outcome = caller.call(
            module="E10SemanticRecallScreen",
            prompt=SCREEN_PROMPT,
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
            "candidate_labels": document["candidate_labels"],
            "strict": document["strict"],
            "success": outcome.success,
            "error": outcome.error,
            "screen_response": outcome.response,
            "cache_hit": outcome.cache_hit,
            "cache_key": outcome.cache_key,
        }

    rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(worker, document): document["case_key"] for document in documents}
        for future in as_completed(futures):
            rows.append(future.result())
    rows.sort(key=lambda row: row["case_key"])
    write_jsonl(screen_dir / "screen_results.jsonl", rows)
    relation_counts = Counter(
        str(item.get("relation"))
        for row in rows
        for item in (row["screen_response"].get("candidate_relations") or [])
    )
    telemetry = aggregate_telemetry(read_jsonl(telemetry_path))
    atomic_json(
        screen_dir / "summary.json",
        {
            "experiment_id": "E10-semantic-screen",
            "model": model,
            "n_cases": len(rows),
            "n_success": sum(bool(row["success"]) for row in rows),
            "relation_counts": dict(sorted(relation_counts.items())),
            "telemetry": telemetry,
            "role": "queue-expansion subcontractor; not final adjudicator",
            "prompt_sha256": sha256_text(SCREEN_PROMPT),
        },
    )
    return rows


def build_queue(out: Path) -> list[dict[str, Any]]:
    documents = {row["case_key"]: row for row in case_documents(out)}
    screens = read_jsonl(out / "semantic_screen" / "screen_results.jsonl")
    queue: list[dict[str, Any]] = []
    negative_pool: list[str] = []
    positive_relations = {"exact_equivalent", "acceptable_clinical_variant", "uncertain"}
    for screen in screens:
        case_key = str(screen["case_key"])
        strict = screen["strict"]
        strict_values = list(strict.values())
        strict_exposed = any(bool(row["union_exposed"]) for row in strict_values)
        strict_discordance = (
            len({bool(row["top1"]) for row in strict_values}) > 1
            or len({bool(row["top2"]) for row in strict_values}) > 1
            or strict["isolated_rrf"]["union_exposed"] != strict["sequential_rrf"]["union_exposed"]
        )
        relations = list(screen["screen_response"].get("candidate_relations") or [])
        screen_positive = any(str(row.get("relation")) in positive_relations for row in relations)
        reasons: list[str] = []
        if strict_exposed:
            reasons.append("strict_reference_exposure")
        if strict_discordance:
            reasons.append("strict_endpoint_or_exposure_discordance")
        if screen_positive:
            reasons.append("heterogeneous_screen_positive_or_uncertain")
        if not bool(screen.get("success")):
            reasons.append("semantic_screen_failure")
        if not reasons:
            negative_pool.append(case_key)
            continue
        document = documents[case_key]
        queue.append({**document, "queue_reasons": reasons, "semantic_screen": screen})
    # Frozen family-balanced negative-screen audit detects subcontractor misses.
    by_family: dict[str, list[str]] = {"DA": [], "MCR": []}
    for case_key in negative_pool:
        by_family[str(documents[case_key]["family"])].append(case_key)
    for family in ("DA", "MCR"):
        ranked = sorted(by_family[family], key=lambda key: (stable_seed("E10-screen-negative-audit-v1", key), key))[:20]
        for case_key in ranked:
            screen = next(row for row in screens if row["case_key"] == case_key)
            queue.append({**documents[case_key], "queue_reasons": ["frozen_negative_screen_audit"], "semantic_screen": screen})
    queue.sort(key=lambda row: row["case_key"])
    write_jsonl(out / "manual_audit_queue.jsonl", queue)
    atomic_json(
        out / "manual_audit_queue_summary.json",
        {
            "n_queue": len(queue),
            "reason_counts": dict(sorted(Counter(reason for row in queue for reason in row["queue_reasons"]).items())),
            "negative_screen_sample": {family: 20 for family in ("DA", "MCR")},
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
        },
    )
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
        print(f"manual_queue={len(queue)}")
    if not (args.run or args.queue):
        raise SystemExit("select --run and/or --queue")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
