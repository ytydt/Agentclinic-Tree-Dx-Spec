#!/usr/bin/env python3
"""Heterogeneous clinical-equivalence screen for RCR-3.

The DeepSeek-family reviewer is method-blind and acts only as a queue-expansion
subcontractor.  Root-owned adjudication determines final clinical endpoints.
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

_ROOT_FOR_IMPORT = Path(__file__).resolve().parents[2]
if __package__ in {None, ""}:
    sys.path.insert(0, str(_ROOT_FOR_IMPORT))
sys.path.insert(0, str(_ROOT_FOR_IMPORT / "src"))

from analysis.mechanism_v2.common import file_sha256  # noqa: E402
from analysis.mechanism_v2.online_runner import (  # noqa: E402
    OnlineJSONCaller,
    read_jsonl,
    write_jsonl,
)
from analysis.mechanism_v2.rcr3_end_to_end import (  # noqa: E402
    ARMS,
    DEFAULT_OUT,
)
from analysis.mechanism_v2.runtime_contract import (  # noqa: E402
    aggregate_telemetry,
    atomic_json,
    dependency_capabilities,
    sha256_text,
    validate_workers,
)


DEFAULT_MODEL = "deepseek/deepseek-v4-flash-0731"
RELATIONS = frozenset({
    "complete_equivalent",
    "partial_parent_or_component",
    "conflicting_subtype_or_scope",
    "manifestation_or_related",
    "not_equivalent",
    "uncertain",
})
IDENTIFIABILITY = frozenset({
    "unique_full_reference",
    "family_only_not_full_specificity",
    "multiple_complete_answers",
    "unsupported_reference_specificity",
    "insufficient_case_information",
    "uncertain",
})

PROMPT = r"""You are an independent clinical adjudication subcontractor.
You do not know which system produced a candidate. Judge the benchmark
reference and every candidate using the complete case text. Do not use string
containment as clinical equivalence.

Perform two separate tasks.

A. Reference identifiability: decide whether this text uniquely supports the
full specificity and scope of the reference diagnosis. Separate a recognizable
disease family from unsupported subtype, anatomy, etiology, stage, complication
or composite components. A direct author diagnostic assertion is evidence that
the text identifies the reference, but flag it rather than treating it as
independent diagnostic reasoning. Missing tests are unknown, not negative.

B. Candidate completeness relative to the reference in this case:
- complete_equivalent: the same final diagnostic object with every
  case-defining component; harmless wording variation only;
- partial_parent_or_component: correct family, parent, component, cause or
  manifestation but missing a required component/specificity;
- conflicting_subtype_or_scope: related entity but asserts a conflicting
  subtype, anatomy, cause, time, stage or composite scope;
- manifestation_or_related: manifestation, complication, association or
  differential rather than the requested final object;
- not_equivalent: different diagnostic entity;
- uncertain: the supplied text genuinely cannot resolve the relation.

Return JSON only and cover every candidate ID exactly once:
{
  "reference_identifiability": {
    "judgment":"unique_full_reference|family_only_not_full_specificity|multiple_complete_answers|unsupported_reference_specificity|insufficient_case_information|uncertain",
    "reference_object_kind":"disease|etiology|subtype|manifestation|syndrome|composite|other",
    "direct_author_assertion":false,
    "decisive_spans":["up to three exact short quotes"],
    "unsupported_components":["component not uniquely supported"],
    "rationale":"brief case-grounded reason"
  },
  "candidate_relations":[
    {"candidate_id":"J001","relation":"complete_equivalent|partial_parent_or_component|conflicting_subtype_or_scope|manifestation_or_related|not_equivalent|uncertain",
     "decisive_span":"one short exact quote or empty",
     "missing_or_conflicting_component":"brief or empty",
     "reason":"brief relation-specific reason"}
  ],
  "case_quality_flags":["optional short flag"]
}
"""


def screen_payload(document: Mapping[str, Any]) -> dict[str, Any]:
    """Return the method-blind payload; arm provenance is deliberately absent."""
    return {
        "case_id": str(document["case_key"]),
        "clinical_record": str(document["vignette"]),
        "reference_diagnosis": str(document["reference_diagnosis"]),
        "candidate_registry": [
            {
                "candidate_id": str(row["candidate_id"]),
                "label": str(row["label"]),
                "surface_labels": [str(value) for value in row.get("surface_labels") or []],
            }
            for row in document["candidate_registry"]
        ],
    }


def validate_screen(response: Mapping[str, Any], allowed: set[str]) -> str | None:
    identifiability = response.get("reference_identifiability")
    if not isinstance(identifiability, Mapping):
        return "reference_identifiability is required"
    if str(identifiability.get("judgment") or "") not in IDENTIFIABILITY:
        return "invalid identifiability judgment"
    if not isinstance(identifiability.get("decisive_spans"), list):
        return "decisive_spans must be a list"
    if not isinstance(identifiability.get("unsupported_components"), list):
        return "unsupported_components must be a list"
    rows = response.get("candidate_relations")
    if not isinstance(rows, list):
        return "candidate_relations must be a list"
    seen = [
        str(row.get("candidate_id") or "")
        for row in rows if isinstance(row, Mapping)
    ]
    if len(seen) != len(allowed) or set(seen) != allowed:
        return "candidate_relations must cover every candidate exactly once"
    for row in rows:
        if not isinstance(row, Mapping):
            return "candidate relation row must be an object"
        if str(row.get("relation") or "") not in RELATIONS:
            return "invalid candidate relation"
    if not isinstance(response.get("case_quality_flags"), list):
        return "case_quality_flags must be a list"
    return None


def _archive(out: Path) -> tuple[Path, Path]:
    archive = out / "RCR3_SEMANTIC_SCREEN_RAW.tar.gz"
    sha = out / f"{archive.name}.sha256"
    with tarfile.open(archive, "w:gz") as bundle:
        for path in sorted((out / "semantic_screen").rglob("*")):
            if not path.is_file() or "cache" in path.parts:
                continue
            bundle.add(path, arcname=str(path.relative_to(out)))
    sha.write_text(f"{file_sha256(archive)}  {archive.name}\n", encoding="utf-8")
    return archive, sha


def _proxy_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    endpoints: dict[str, Counter[str]] = {arm: Counter() for arm in ARMS}
    discord_top1 = discord_top2 = 0
    for row in rows:
        response = dict(row.get("screen_response") or {})
        relation = {
            str(item.get("candidate_id")): str(item.get("relation"))
            for item in response.get("candidate_relations") or []
        }
        case_top1: list[bool] = []
        case_top2: list[bool] = []
        for arm in ARMS:
            outcome = row["arm_outcomes"][arm]
            if not row["success"] or not outcome["success"]:
                top1 = top2 = partial1 = partial2 = False
            else:
                champion = str(outcome.get("champion_candidate_id") or "")
                runner = str(outcome.get("runner_up_candidate_id") or "")
                top1 = relation.get(champion) == "complete_equivalent"
                top2 = top1 or relation.get(runner) == "complete_equivalent"
                accepted = {"complete_equivalent", "partial_parent_or_component"}
                partial1 = relation.get(champion) in accepted
                partial2 = partial1 or relation.get(runner) in accepted
            endpoints[arm]["complete_top1"] += int(top1)
            endpoints[arm]["complete_top2"] += int(top2)
            endpoints[arm]["complete_or_partial_top1"] += int(partial1)
            endpoints[arm]["complete_or_partial_top2"] += int(partial2)
            case_top1.append(top1)
            case_top2.append(top2)
        discord_top1 += int(len(set(case_top1)) > 1)
        discord_top2 += int(len(set(case_top2)) > 1)
    return {
        "arm_endpoints": {arm: dict(counts) for arm, counts in endpoints.items()},
        "proxy_complete_top1_discordant_case_n": discord_top1,
        "proxy_complete_top2_discordant_case_n": discord_top2,
    }


def _clinical_queue(out: Path, rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    base = {
        str(row["case_key"]): row
        for row in read_jsonl(out / "root_audit_queue.jsonl")
    }
    queue: list[dict[str, Any]] = []
    for screen in rows:
        key = str(screen["case_key"])
        reasons = set((base.get(key) or {}).get("queue_reasons") or [])
        if not screen["success"]:
            reasons.add("heterogeneous_screen_failure")
        else:
            judgment = str(
                (screen["screen_response"].get("reference_identifiability") or {}).get("judgment")
            )
            if judgment != "unique_full_reference":
                reasons.add(f"reference_identifiability:{judgment}")
            relation = {
                str(item.get("candidate_id")): str(item.get("relation"))
                for item in screen["screen_response"].get("candidate_relations") or []
            }
            top1 = []
            top2 = []
            for arm in ARMS:
                outcome = screen["arm_outcomes"][arm]
                champion = str(outcome.get("champion_candidate_id") or "")
                runner = str(outcome.get("runner_up_candidate_id") or "")
                hit1 = bool(outcome["success"] and relation.get(champion) == "complete_equivalent")
                hit2 = bool(hit1 or (outcome["success"] and relation.get(runner) == "complete_equivalent"))
                top1.append(hit1)
                top2.append(hit2)
            if len(set(top1)) > 1:
                reasons.add("proxy_complete_top1_discordance")
            if len(set(top2)) > 1:
                reasons.add("proxy_complete_top2_discordance")
        queue.append({
            **dict(screen),
            "strict_queue_context": base.get(key),
            "queue_reasons": sorted(reasons),
        })
    queue.sort(key=lambda row: str(row["case_key"]))
    write_jsonl(out / "clinical_audit_queue.jsonl", queue)
    return queue


def run_screen(out: Path, model: str, workers: int) -> list[dict[str, Any]]:
    documents = read_jsonl(out / "semantic_screen_inputs.jsonl")
    if len(documents) != 300:
        raise AssertionError("RCR3 semantic screen requires 300 frozen inputs")
    screen_dir = out / "semantic_screen"
    screen_dir.mkdir(parents=True, exist_ok=True)
    result_path = screen_dir / "screen_results.jsonl"
    if result_path.is_file():
        rows = read_jsonl(result_path)
        if len(rows) != len(documents):
            raise AssertionError("partial semantic screen results require manual audit")
        _clinical_queue(out, rows)
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
        call_timeout=240,
        max_retries=2,
    )

    def one(document: Mapping[str, Any]) -> dict[str, Any]:
        payload = screen_payload(document)
        allowed = {str(row["candidate_id"]) for row in payload["candidate_registry"]}
        outcome = caller.call(
            module="RCR3HeterogeneousClinicalScreen",
            prompt=PROMPT,
            payload=payload,
            validator=lambda response: validate_screen(response, allowed),
        )
        return {
            **dict(document),
            "success": outcome.success,
            "error": outcome.error,
            "screen_response": outcome.response,
            "cache_hit": outcome.cache_hit,
            "cache_key": outcome.cache_key,
            "payload_sha256": outcome.payload_sha256,
        }

    rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(one, document): document for document in documents}
        for done, future in enumerate(as_completed(futures), 1):
            document = futures[future]
            try:
                row = future.result()
            except Exception as exc:
                row = {
                    **dict(document),
                    "success": False,
                    "error": f"{type(exc).__name__}: {exc}",
                    "screen_response": {},
                    "cache_hit": False,
                    "cache_key": "",
                    "payload_sha256": "",
                }
            rows.append(row)
            if done % 20 == 0 or done == len(documents):
                line = f"completed={done}/{len(documents)} failures={sum(not row['success'] for row in rows)}"
                print(line, flush=True)
                with log_path.open("a", encoding="utf-8") as stream:
                    stream.write(line + "\n")
    rows.sort(key=lambda row: str(row["case_key"]))
    write_jsonl(result_path, rows)
    relation_counts = Counter(
        str(item.get("relation"))
        for row in rows
        for item in (row.get("screen_response") or {}).get("candidate_relations") or []
    )
    identifiability_counts = Counter(
        str(((row.get("screen_response") or {}).get("reference_identifiability") or {}).get("judgment") or "screen_failure")
        for row in rows
    )
    telemetry = read_jsonl(telemetry_path)
    atomic_json(screen_dir / "telemetry_summary.json", aggregate_telemetry(telemetry))
    atomic_json(screen_dir / "summary.json", {
        "experiment_id": "RCR3-semantic-screen",
        "role": "heterogeneous queue-expansion subcontractor; root owns final adjudication",
        "model": model,
        "n_cases": len(rows),
        "n_success": sum(bool(row["success"]) for row in rows),
        "n_failure": sum(not bool(row["success"]) for row in rows),
        "candidate_relation_counts": dict(sorted(relation_counts.items())),
        "reference_identifiability_counts": dict(sorted(identifiability_counts.items())),
        "proxy_endpoints": _proxy_summary(rows),
        "prompt_sha256": sha256_text(PROMPT),
        "capabilities": dependency_capabilities(),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
    })
    queue = _clinical_queue(out, rows)
    with log_path.open("a", encoding="utf-8") as stream:
        stream.write(f"completed_at_utc={datetime.now(timezone.utc).isoformat()}\n")
        stream.write(f"clinical_audit_queue_n={len(queue)}\n")
    _archive(out)
    return rows


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--workers", type=int, default=50)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    workers = validate_workers(args.workers, rag=False)
    rows = run_screen(args.out.resolve(), args.model, workers)
    print(json.dumps({
        "n": len(rows),
        "success": sum(bool(row["success"]) for row in rows),
        "failure": sum(not bool(row["success"]) for row in rows),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
