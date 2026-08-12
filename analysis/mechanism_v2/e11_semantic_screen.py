#!/usr/bin/env python3
"""Heterogeneous semantic and retrieval-evidence screen for E11.

DeepSeek is used only as a queue-expansion subcontractor.  Candidate accuracy,
chunk contamination, and mechanism labels remain subject to root review; the
screen never changes the frozen strict endpoint by itself.
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

from analysis.mechanism_v2.common import ROOT, file_sha256, normalize_label, source_commit  # noqa: E402
from analysis.mechanism_v2.e11_analysis import load_arms  # noqa: E402
from analysis.mechanism_v2.e11_b07_factorial import (  # noqa: E402
    ARMS,
    DEFAULT_OUT,
    RETRIEVALS,
    load_jobs,
)
from analysis.mechanism_v2.online_runner import (  # noqa: E402
    OnlineJSONCaller,
    canonical_sha256,
    read_jsonl,
    write_jsonl,
)
from analysis.mechanism_v2.runtime_contract import (  # noqa: E402
    aggregate_telemetry,
    atomic_json,
    dependency_capabilities,
    sha256_text,
    stable_seed,
    validate_workers,
)


DEFAULT_MODEL = "deepseek/deepseek-v4-flash-0731"
SCREEN_DIR_NAME = "semantic_screen"
CANDIDATE_RELATIONS = (
    "exact_equivalent",
    "acceptable_clinical_variant",
    "broader_or_narrower_not_equivalent",
    "related_not_equivalent",
    "unrelated",
    "uncertain",
)
REFERENCE_RELATIONS = (
    "direct_same_disease",
    "supports_case_defining_subtype",
    "broader_related_context",
    "supports_competing_diagnosis",
    "generic_or_unrelated",
    "uncertain",
)
ANCHOR_RELATIONS = (
    "directly_supports",
    "indirectly_supports",
    "contradicts_or_weakens",
    "not_about",
    "uncertain",
)
APPLICABILITY = ("case_specific_fit", "partial_fit", "no_fit", "uncertain")
BUNDLE_SUPPORT = ("direct", "partial", "absent", "contradictory_or_misleading", "mixed", "uncertain")
CONFIRMATION_PRESSURE = (
    "supports_generated_top1_more",
    "supports_reference_more",
    "balanced_or_neutral",
    "uncertain",
)
BUNDLE_NAMES = ("relevant", "random", "hard_negative")

SCREEN_PROMPT = """Role: conservative clinical terminology and retrieval-evidence screen.

This is retrospective evaluation, not diagnosis generation. The reference is
visible only because you are screening study outputs. Do not infer that a chunk
supports the reference merely because it shares an organ, symptom, or disease
family. Do not infer that the bundle named hard_negative is actually wrong.

Candidate relation labels:
- exact_equivalent: same diagnostic entity despite ordinary synonym/spelling;
- acceptable_clinical_variant: wording/specificity accepted as the same case
  diagnosis in this vignette;
- broader_or_narrower_not_equivalent: related ancestor/descendant that loses or
  adds a case-defining subtype;
- related_not_equivalent; unrelated; uncertain.

For every chunk, classify relation_to_reference, relation_to_generated_top1,
and vignette_applicability using only the allowed labels supplied in the JSON
contract. For every bundle, summarize support and confirmation pressure. A
retrieved textbook paragraph can be medically true yet irrelevant to this
case. Keep each reason under 18 words. Evaluate every supplied ID exactly once.

Return JSON only:
{"candidate_relations":[
 {"candidate_id":"C1","relation":"allowed candidate label","reason":"brief"}
],
"chunk_assessments":[
 {"chunk_id":"R1","relation_to_reference":"allowed reference label",
  "relation_to_generated_top1":"allowed anchor label",
  "vignette_applicability":"allowed applicability label","reason":"brief"}
],
"bundle_assessments":[
 {"bundle":"relevant","reference_support":"allowed support label",
  "generated_top1_support":"allowed support label",
  "confirmation_pressure":"allowed pressure label",
  "clinically_misleading":"yes|no|uncertain","reason":"brief"}
],
"screen_note":"brief ambiguity note"}
"""


def _candidate_registry(
    case_key: str,
    arms: Mapping[str, Mapping[str, Mapping[str, Any]]],
) -> list[dict[str, Any]]:
    by_surface: dict[str, dict[str, Any]] = {}
    for arm in ARMS:
        row = arms[arm][case_key]
        for rank, label in enumerate(row.get("top2_labels") or [], 1):
            surface = normalize_label(str(label))
            if not surface:
                continue
            record = by_surface.setdefault(
                surface,
                {"label": str(label), "occurrences": []},
            )
            record["occurrences"].append({"arm": arm, "rank": rank})
    registry: list[dict[str, Any]] = []
    for index, surface in enumerate(sorted(by_surface), 1):
        record = by_surface[surface]
        registry.append(
            {
                "candidate_id": f"C{index}",
                "label": record["label"],
                "occurrences": record["occurrences"],
            }
        )
    return registry


def case_documents(out: Path) -> list[dict[str, Any]]:
    jobs, _ = load_jobs()
    job_by_key = {str(row["case_key"]): row for row in jobs}
    arms = load_arms(out)
    retrieval_rows = {
        str(row["case_key"]): row
        for row in read_jsonl(out / "retrieval_plan.jsonl")
    }
    documents: list[dict[str, Any]] = []
    prefixes = {"relevant": "R", "random": "N", "hard_negative": "H"}
    for case_key in sorted(job_by_key):
        job = job_by_key[case_key]
        plan = retrieval_rows[case_key]
        chunks: list[dict[str, Any]] = []
        bundles: list[dict[str, Any]] = []
        for bundle_name in BUNDLE_NAMES:
            prefix = prefixes[bundle_name]
            generated_top1 = str(
                (arms[f"{bundle_name}_refine_off"][case_key].get("top2_labels") or [""])[0]
            )
            bundle_chunk_ids: list[str] = []
            for index, chunk in enumerate(plan["bundles"][bundle_name], 1):
                chunk_id = f"{prefix}{index}"
                bundle_chunk_ids.append(chunk_id)
                chunks.append(
                    {
                        "chunk_id": chunk_id,
                        "bundle": bundle_name,
                        "source_chunk_id": str(chunk["chunk_id"]),
                        "title": str(chunk.get("title") or ""),
                        "text": str(chunk.get("text") or ""),
                    }
                )
            bundles.append(
                {
                    "bundle": bundle_name,
                    "generated_top1": generated_top1,
                    "chunk_ids": bundle_chunk_ids,
                }
            )
        candidates = _candidate_registry(case_key, arms)
        documents.append(
            {
                "case_key": case_key,
                "family": job["family"],
                "vignette": job["vignette"],
                "reference_diagnosis": job["gold"],
                "historical_need_retrieval": bool(job["historical_need_retrieval"]),
                "candidate_registry": candidates,
                "chunks": chunks,
                "bundles": bundles,
                "strict": {
                    arm: {
                        "top2_labels": list(arms[arm][case_key]["top2_labels"]),
                        "top1": bool(arms[arm][case_key]["gold_top1"]),
                        "top2": bool(arms[arm][case_key]["gold_top2"]),
                    }
                    for arm in ARMS
                },
                "refine_changed": {
                    retrieval: bool(arms[f"{retrieval}_refine_on"][case_key].get("changed_from_draft"))
                    for retrieval in RETRIEVALS
                },
            }
        )
    if len(documents) != 400:
        raise AssertionError(f"semantic screen requires 400 documents, got {len(documents)}")
    return documents


def _validator(candidate_ids: set[str], chunk_ids: set[str]):
    def validate(response: Mapping[str, Any]) -> str | None:
        candidates = response.get("candidate_relations")
        if not isinstance(candidates, list):
            return "candidate_relations must be a list"
        seen_candidates: list[str] = []
        for row in candidates:
            if not isinstance(row, Mapping):
                return "candidate relation row is not an object"
            candidate_id = str(row.get("candidate_id") or "")
            relation = str(row.get("relation") or "")
            if candidate_id not in candidate_ids:
                return f"unknown candidate_id {candidate_id}"
            if relation not in CANDIDATE_RELATIONS:
                return f"invalid candidate relation {relation}"
            seen_candidates.append(candidate_id)
        if len(seen_candidates) != len(set(seen_candidates)) or set(seen_candidates) != candidate_ids:
            return "candidate IDs must appear exactly once"

        chunks = response.get("chunk_assessments")
        if not isinstance(chunks, list):
            return "chunk_assessments must be a list"
        seen_chunks: list[str] = []
        for row in chunks:
            if not isinstance(row, Mapping):
                return "chunk assessment row is not an object"
            chunk_id = str(row.get("chunk_id") or "")
            if chunk_id not in chunk_ids:
                return f"unknown chunk_id {chunk_id}"
            if str(row.get("relation_to_reference") or "") not in REFERENCE_RELATIONS:
                return f"invalid reference relation for {chunk_id}"
            if str(row.get("relation_to_generated_top1") or "") not in ANCHOR_RELATIONS:
                return f"invalid generated-top1 relation for {chunk_id}"
            if str(row.get("vignette_applicability") or "") not in APPLICABILITY:
                return f"invalid applicability for {chunk_id}"
            seen_chunks.append(chunk_id)
        if len(seen_chunks) != len(set(seen_chunks)) or set(seen_chunks) != chunk_ids:
            return "chunk IDs must appear exactly once"

        bundles = response.get("bundle_assessments")
        if not isinstance(bundles, list):
            return "bundle_assessments must be a list"
        seen_bundles: list[str] = []
        for row in bundles:
            if not isinstance(row, Mapping):
                return "bundle assessment row is not an object"
            bundle = str(row.get("bundle") or "")
            if bundle not in BUNDLE_NAMES:
                return f"unknown bundle {bundle}"
            if str(row.get("reference_support") or "") not in BUNDLE_SUPPORT:
                return f"invalid bundle reference support {bundle}"
            if str(row.get("generated_top1_support") or "") not in BUNDLE_SUPPORT:
                return f"invalid generated top1 support {bundle}"
            if str(row.get("confirmation_pressure") or "") not in CONFIRMATION_PRESSURE:
                return f"invalid confirmation pressure {bundle}"
            if str(row.get("clinically_misleading") or "") not in {"yes", "no", "uncertain"}:
                return f"invalid misleading flag {bundle}"
            seen_bundles.append(bundle)
        if len(seen_bundles) != len(set(seen_bundles)) or set(seen_bundles) != set(BUNDLE_NAMES):
            return "bundle names must appear exactly once"
        return None
    return validate


def freeze(out: Path, documents: Sequence[Mapping[str, Any]], model: str, workers: int) -> dict[str, Any]:
    screen_dir = out / SCREEN_DIR_NAME
    screen_dir.mkdir(parents=True, exist_ok=True)
    path = screen_dir / "preregistration.json"
    expected = {
        "schema": "e11_semantic_retrieval_screen_v1",
        "experiment_id": "E11-semantic-screen",
        "created_before_calls_utc": datetime.now(timezone.utc).isoformat(),
        "source_commit": source_commit(),
        "model": model,
        "workers": workers,
        "rag_worker_ceiling": 25,
        "n_cases": len(documents),
        "document_sha256": canonical_sha256(documents),
        "prompt_sha256": sha256_text(SCREEN_PROMPT),
        "role": "heterogeneous queue-expansion subcontractor; root retains final responsibility",
        "candidate_relations": list(CANDIDATE_RELATIONS),
        "reference_relations": list(REFERENCE_RELATIONS),
        "bundle_names": list(BUNDLE_NAMES),
        "payload_contains_reference": True,
        "failure_policy": "failed schema forces root queue; no screen-derived imputation",
    }
    if path.is_file():
        current = json.loads(path.read_text(encoding="utf-8"))
        for key in ("schema", "model", "workers", "n_cases", "document_sha256", "prompt_sha256"):
            if current.get(key) != expected.get(key):
                raise AssertionError(f"frozen E11 semantic screen mismatch: {key}")
        return current
    atomic_json(path, expected)
    atomic_json(
        screen_dir / "environment.json",
        {
            "capabilities": dependency_capabilities(),
            "output_cap_requested": "TREE_DX_DIRECT_POST_OUTPUT_CAP=8192 recommended",
            "source_commit": expected["source_commit"],
        },
    )
    return expected


def run_screen(out: Path, model: str, workers: int) -> list[dict[str, Any]]:
    workers = validate_workers(workers, rag=True)
    documents = case_documents(out)
    prereg = freeze(out, documents, model, workers)
    screen_dir = out / SCREEN_DIR_NAME
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
        candidate_ids = {str(row["candidate_id"]) for row in document["candidate_registry"]}
        chunk_ids = {str(row["chunk_id"]) for row in document["chunks"]}
        payload = {
            "vignette": str(document["vignette"]),
            "reference_diagnosis": str(document["reference_diagnosis"]),
            "candidate_registry": list(document["candidate_registry"]),
            "retrieval_bundles": list(document["bundles"]),
            "retrieved_chunks": list(document["chunks"]),
        }
        outcome = caller.call(
            module="E11SemanticRetrievalScreen",
            prompt=SCREEN_PROMPT,
            payload=payload,
            validator=_validator(candidate_ids, chunk_ids),
        )
        return {
            "case_key": document["case_key"],
            "family": document["family"],
            "reference_diagnosis": document["reference_diagnosis"],
            "historical_need_retrieval": document["historical_need_retrieval"],
            "candidate_registry": document["candidate_registry"],
            "chunks": document["chunks"],
            "bundles": document["bundles"],
            "strict": document["strict"],
            "refine_changed": document["refine_changed"],
            "success": outcome.success,
            "error": outcome.error,
            "screen_response": outcome.response,
            "cache_hit": outcome.cache_hit,
            "cache_key": outcome.cache_key,
            "payload_sha256": outcome.payload_sha256,
        }

    rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(worker, document): str(document["case_key"]) for document in documents}
        for future in as_completed(futures):
            rows.append(future.result())
    rows.sort(key=lambda row: row["case_key"])
    write_jsonl(screen_dir / "screen_results.jsonl", rows)
    candidate_counts = Counter(
        str(item.get("relation"))
        for row in rows for item in (row["screen_response"].get("candidate_relations") or [])
    )
    reference_counts = Counter(
        f"{str(item.get('chunk_id') or '')[:1]}:{item.get('relation_to_reference')}"
        for row in rows for item in (row["screen_response"].get("chunk_assessments") or [])
    )
    bundle_counts = Counter(
        f"{item.get('bundle')}:{item.get('reference_support')}:{item.get('confirmation_pressure')}:{item.get('clinically_misleading')}"
        for row in rows for item in (row["screen_response"].get("bundle_assessments") or [])
    )
    telemetry = aggregate_telemetry(read_jsonl(telemetry_path))
    summary = {
        "experiment_id": "E11-semantic-screen",
        "model": model,
        "n_cases": len(rows),
        "n_success": sum(bool(row["success"]) for row in rows),
        "candidate_relation_counts": dict(sorted(candidate_counts.items())),
        "chunk_reference_relation_counts_by_prefix": dict(sorted(reference_counts.items())),
        "bundle_assessment_counts": dict(sorted(bundle_counts.items())),
        "telemetry": telemetry,
        "role": prereg["role"],
        "prompt_sha256": prereg["prompt_sha256"],
    }
    atomic_json(screen_dir / "summary.json", summary)
    archive = screen_dir / "SCREEN_ARTIFACTS.tar.gz"
    with tarfile.open(archive, "w:gz") as bundle:
        for name in ("preregistration.json", "environment.json", "screen_results.jsonl", "summary.json", "telemetry.jsonl"):
            path = screen_dir / name
            bundle.add(path, arcname=name)
    digest = file_sha256(archive)
    (screen_dir / f"{archive.name}.sha256").write_text(f"{digest}  {archive.name}\n", encoding="utf-8")
    return rows


def build_queue(out: Path) -> list[dict[str, Any]]:
    screens = read_jsonl(out / SCREEN_DIR_NAME / "screen_results.jsonl")
    queue: list[dict[str, Any]] = []
    negative_by_family: dict[str, list[dict[str, Any]]] = {"DA": [], "MCR": []}
    positive_candidate = {"exact_equivalent", "acceptable_clinical_variant", "uncertain"}
    for row in screens:
        response = row["screen_response"]
        candidate_relations = response.get("candidate_relations") or []
        chunks = response.get("chunk_assessments") or []
        bundles = response.get("bundle_assessments") or []
        strict_values = list(row["strict"].values())
        reasons: list[str] = []
        if len({bool(item["top1"]) for item in strict_values}) > 1 or len({bool(item["top2"]) for item in strict_values}) > 1:
            reasons.append("strict_endpoint_discordance")
        if any(bool(value) for value in row["refine_changed"].values()):
            reasons.append("at_least_one_refine_change")
        if any(str(item.get("relation")) in positive_candidate for item in candidate_relations):
            reasons.append("candidate_positive_or_uncertain")
        if any(str(item.get("relation_to_reference")) in {"direct_same_disease", "supports_case_defining_subtype", "uncertain"} for item in chunks):
            reasons.append("chunk_reference_support_or_uncertain")
        if any(str(item.get("clinically_misleading")) in {"yes", "uncertain"} for item in bundles):
            reasons.append("bundle_misleading_or_uncertain")
        hard_rows = [item for item in chunks if str(item.get("chunk_id") or "").startswith("H")]
        if any(str(item.get("relation_to_reference")) in {"direct_same_disease", "supports_case_defining_subtype"} for item in hard_rows):
            reasons.append("hard_negative_reference_contamination")
        relevant_bundle = next((item for item in bundles if item.get("bundle") == "relevant"), {})
        if str(relevant_bundle.get("reference_support")) in {"absent", "contradictory_or_misleading", "uncertain"}:
            reasons.append("relevant_bundle_lacks_clear_reference_support")
        if not bool(row.get("success")):
            reasons.append("semantic_screen_failure")
        if reasons:
            queue.append({**row, "queue_reasons": sorted(set(reasons))})
        else:
            negative_by_family[str(row["family"])].append(row)
    for family in ("DA", "MCR"):
        ranked = sorted(
            negative_by_family[family],
            key=lambda row: (stable_seed("E11-negative-screen-audit-v1", row["case_key"]), row["case_key"]),
        )[:20]
        for row in ranked:
            queue.append({**row, "queue_reasons": ["frozen_negative_screen_audit"]})
    queue.sort(key=lambda row: row["case_key"])
    write_jsonl(out / "manual_audit_queue.jsonl", queue)
    atomic_json(
        out / "manual_audit_queue_summary.json",
        {
            "n_queue": len(queue),
            "reason_counts": dict(sorted(Counter(reason for row in queue for reason in row["queue_reasons"]).items())),
            "negative_screen_sample_requested": {"DA": 20, "MCR": 20},
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
        },
    )
    return queue


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--workers", type=int, default=25)
    parser.add_argument("--freeze", action="store_true")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--queue", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    out = args.out.resolve()
    documents = case_documents(out)
    if args.freeze:
        prereg = freeze(out, documents, args.model, validate_workers(args.workers, rag=True))
        print(json.dumps({"frozen": prereg["n_cases"], "model": prereg["model"]}, indent=2))
    if args.run:
        rows = run_screen(out, args.model, args.workers)
        print(f"semantic_screen={sum(bool(row['success']) for row in rows)}/{len(rows)}")
    if args.queue:
        rows = build_queue(out)
        print(f"manual_queue={len(rows)}")
    if not (args.freeze or args.run or args.queue):
        raise SystemExit("select --freeze, --run and/or --queue")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
