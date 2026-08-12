#!/usr/bin/env python3
"""Compact split recovery screen after the combined E11 schema overloaded."""
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

from analysis.mechanism_v2.common import file_sha256, source_commit  # noqa: E402
from analysis.mechanism_v2.e11_b07_factorial import DEFAULT_OUT  # noqa: E402
from analysis.mechanism_v2.e11_semantic_screen import (  # noqa: E402
    BUNDLE_NAMES,
    CANDIDATE_RELATIONS,
    DEFAULT_MODEL,
    SCREEN_DIR_NAME,
    case_documents,
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
    validate_workers,
)


CANDIDATE_PROMPT = """Conservative retrospective terminology screen.
The reference is visible for evaluation. For each candidate ID, assign exactly
one label: exact_equivalent, acceptable_clinical_variant,
broader_or_narrower_not_equivalent, related_not_equivalent, unrelated, or
uncertain. Shared anatomy/symptom/substring is not equivalence. Do not diagnose
anew. Return every ID exactly once, no explanations, JSON only:
{"candidate_relations":[{"candidate_id":"C1","relation":"allowed_label"}]}
"""

RETRIEVAL_PROMPT = """Compact retrospective retrieval-evidence screen.
The reference and each bundle's generated Top-1 are visible for evaluation.
For every chunk return [id,REF,TOP1,FIT]. For every bundle return
[name,REFSUP,TOP1SUP,PRESSURE,MISLEADING]. Do not assume hard_negative is wrong.
A true textbook passage can still have no fit to this vignette.

REF: E=direct same disease; S=supports case-defining subtype; B=broader related;
C=supports competing diagnosis; G=generic/unrelated; U=uncertain.
TOP1: D=direct support; I=indirect support; W=contradicts/weakens; N=not about; U=uncertain.
FIT: F=case-specific fit; P=partial fit; N=no fit; U=uncertain.
REFSUP/TOP1SUP: D=direct; P=partial; A=absent; X=contradictory/misleading; M=mixed; U=uncertain.
PRESSURE: G=supports generated Top-1 more; R=supports reference more; B=balanced/neutral; U=uncertain.
MISLEADING: Y=yes; N=no; U=uncertain.

Return all 18 chunk IDs and all three bundle names exactly once, no prose:
{"chunks":[["R1","E","D","F"]],
 "bundles":[["relevant","D","D","B","N"]]}
"""

REF_CODE = {
    "E": "direct_same_disease",
    "S": "supports_case_defining_subtype",
    "B": "broader_related_context",
    "C": "supports_competing_diagnosis",
    "G": "generic_or_unrelated",
    "U": "uncertain",
}
TOP1_CODE = {
    "D": "directly_supports",
    "I": "indirectly_supports",
    "W": "contradicts_or_weakens",
    "N": "not_about",
    "U": "uncertain",
}
FIT_CODE = {"F": "case_specific_fit", "P": "partial_fit", "N": "no_fit", "U": "uncertain"}
SUPPORT_CODE = {
    "D": "direct",
    "P": "partial",
    "A": "absent",
    "X": "contradictory_or_misleading",
    "M": "mixed",
    "U": "uncertain",
}
PRESSURE_CODE = {
    "G": "supports_generated_top1_more",
    "R": "supports_reference_more",
    "B": "balanced_or_neutral",
    "U": "uncertain",
}
MISLEADING_CODE = {"Y": "yes", "N": "no", "U": "uncertain"}


def candidate_validator(candidate_ids: set[str]):
    def validate(response: Mapping[str, Any]) -> str | None:
        rows = response.get("candidate_relations")
        if not isinstance(rows, list):
            return "candidate_relations must be a list"
        seen: list[str] = []
        for row in rows:
            if not isinstance(row, Mapping):
                return "candidate row must be an object"
            candidate_id = str(row.get("candidate_id") or "")
            relation = str(row.get("relation") or "")
            if candidate_id not in candidate_ids:
                return f"unknown candidate {candidate_id}"
            if relation not in CANDIDATE_RELATIONS:
                return f"invalid relation {relation}"
            seen.append(candidate_id)
        if len(seen) != len(set(seen)) or set(seen) != candidate_ids:
            return "candidate IDs must appear exactly once"
        return None
    return validate


def retrieval_validator(chunk_ids: set[str]):
    def validate(response: Mapping[str, Any]) -> str | None:
        chunks = response.get("chunks")
        if not isinstance(chunks, list):
            return "chunks must be a list"
        seen: list[str] = []
        for row in chunks:
            if not isinstance(row, list) or len(row) != 4:
                return "each chunk row must be [id,REF,TOP1,FIT]"
            chunk_id, ref, top1, fit = map(str, row)
            if chunk_id not in chunk_ids:
                return f"unknown chunk {chunk_id}"
            if ref not in REF_CODE or top1 not in TOP1_CODE or fit not in FIT_CODE:
                return f"invalid chunk code for {chunk_id}"
            seen.append(chunk_id)
        if len(seen) != len(set(seen)) or set(seen) != chunk_ids:
            return "chunk IDs must appear exactly once"
        bundles = response.get("bundles")
        if not isinstance(bundles, list):
            return "bundles must be a list"
        bundle_seen: list[str] = []
        for row in bundles:
            if not isinstance(row, list) or len(row) != 5:
                return "each bundle row must have five compact fields"
            name, ref_support, top1_support, pressure, misleading = map(str, row)
            if name not in BUNDLE_NAMES:
                return f"unknown bundle {name}"
            if ref_support not in SUPPORT_CODE or top1_support not in SUPPORT_CODE:
                return f"invalid support code for {name}"
            if pressure not in PRESSURE_CODE or misleading not in MISLEADING_CODE:
                return f"invalid pressure/misleading code for {name}"
            bundle_seen.append(name)
        if len(bundle_seen) != len(set(bundle_seen)) or set(bundle_seen) != set(BUNDLE_NAMES):
            return "bundle names must appear exactly once"
        return None
    return validate


def freeze(out: Path, documents: Sequence[Mapping[str, Any]], model: str, workers: int) -> dict[str, Any]:
    screen_dir = out / SCREEN_DIR_NAME
    screen_dir.mkdir(parents=True, exist_ok=True)
    path = screen_dir / "split_preregistration.json"
    expected = {
        "schema": "e11_split_compact_screen_v1",
        "experiment_id": "E11-split-semantic-screen",
        "created_before_split_calls_utc": datetime.now(timezone.utc).isoformat(),
        "source_commit": source_commit(),
        "model": model,
        "workers": workers,
        "rag_worker_ceiling": 25,
        "n_cases": len(documents),
        "document_sha256": canonical_sha256(documents),
        "candidate_prompt_sha256": sha256_text(CANDIDATE_PROMPT),
        "retrieval_prompt_sha256": sha256_text(RETRIEVAL_PROMPT),
        "candidate_schema": "one enum relation per candidate ID; no reasons",
        "retrieval_schema": "18 compact chunk rows plus three compact bundle rows",
        "scientific_fields_preserved_from_aborted_combined": [
            "candidate equivalence", "chunk-reference relation",
            "chunk-generated-top1 relation", "vignette applicability",
            "bundle reference/top1 support", "confirmation pressure", "misleading flag",
        ],
        "reason_for_split": "combined verbose schema caused concurrent length retries and 180-second timeouts",
        "role": "heterogeneous queue-expansion subcontractor; root retains final responsibility",
        "failure_policy": "component failure forces root queue; no screen-derived imputation",
    }
    if path.is_file():
        current = json.loads(path.read_text(encoding="utf-8"))
        for key in (
            "schema", "model", "workers", "n_cases", "document_sha256",
            "candidate_prompt_sha256", "retrieval_prompt_sha256",
        ):
            if current.get(key) != expected.get(key):
                raise AssertionError(f"frozen split screen mismatch: {key}")
        return current
    atomic_json(path, expected)
    atomic_json(
        screen_dir / "split_environment.json",
        {
            "capabilities": dependency_capabilities(),
            "recommended_output_cap": 4096,
            "combined_screen_status": "aborted_on_process_storm",
            "source_commit": expected["source_commit"],
        },
    )
    return expected


def _archive_component(component_dir: Path) -> None:
    archive = component_dir / "RUN_ARTIFACTS.tar.gz"
    with tarfile.open(archive, "w:gz") as bundle:
        for name in ("case_results.jsonl", "summary.json", "telemetry.jsonl"):
            bundle.add(component_dir / name, arcname=name)
    digest = file_sha256(archive)
    (component_dir / f"{archive.name}.sha256").write_text(f"{digest}  {archive.name}\n", encoding="utf-8")


def run_candidate_screen(out: Path, model: str, workers: int) -> list[dict[str, Any]]:
    workers = validate_workers(workers, rag=True)
    documents = case_documents(out)
    freeze(out, documents, model, workers)
    component_dir = out / SCREEN_DIR_NAME / "candidate"
    telemetry_path = component_dir / "telemetry.jsonl"
    caller = OnlineJSONCaller(
        out_dir=component_dir, model=model, telemetry_path=telemetry_path,
        temperature=0.0, call_timeout=180, max_retries=2,
    )

    def worker(document: Mapping[str, Any]) -> dict[str, Any]:
        ids = {str(row["candidate_id"]) for row in document["candidate_registry"]}
        outcome = caller.call(
            module="E11CandidateEquivalenceScreen",
            prompt=CANDIDATE_PROMPT,
            payload={
                "vignette": str(document["vignette"]),
                "reference_diagnosis": str(document["reference_diagnosis"]),
                "candidate_registry": list(document["candidate_registry"]),
            },
            validator=candidate_validator(ids),
        )
        return {
            "case_key": document["case_key"], "family": document["family"],
            "success": outcome.success, "error": outcome.error,
            "response": outcome.response, "cache_hit": outcome.cache_hit,
            "cache_key": outcome.cache_key, "payload_sha256": outcome.payload_sha256,
        }

    rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(worker, document) for document in documents]
        for future in as_completed(futures):
            rows.append(future.result())
    rows.sort(key=lambda row: row["case_key"])
    write_jsonl(component_dir / "case_results.jsonl", rows)
    counts = Counter(
        str(item.get("relation"))
        for row in rows for item in (row["response"].get("candidate_relations") or [])
    )
    atomic_json(component_dir / "summary.json", {
        "component": "candidate_equivalence", "model": model,
        "n_cases": len(rows), "n_success": sum(bool(row["success"]) for row in rows),
        "relation_counts": dict(sorted(counts.items())),
        "telemetry": aggregate_telemetry(read_jsonl(telemetry_path)),
    })
    _archive_component(component_dir)
    return rows


def run_retrieval_screen(out: Path, model: str, workers: int) -> list[dict[str, Any]]:
    workers = validate_workers(workers, rag=True)
    documents = case_documents(out)
    freeze(out, documents, model, workers)
    component_dir = out / SCREEN_DIR_NAME / "retrieval"
    telemetry_path = component_dir / "telemetry.jsonl"
    caller = OnlineJSONCaller(
        out_dir=component_dir, model=model, telemetry_path=telemetry_path,
        temperature=0.0, call_timeout=180, max_retries=2,
    )

    def worker(document: Mapping[str, Any]) -> dict[str, Any]:
        ids = {str(row["chunk_id"]) for row in document["chunks"]}
        outcome = caller.call(
            module="E11CompactRetrievalScreen",
            prompt=RETRIEVAL_PROMPT,
            payload={
                "vignette": str(document["vignette"]),
                "reference_diagnosis": str(document["reference_diagnosis"]),
                "retrieval_bundles": list(document["bundles"]),
                "retrieved_chunks": list(document["chunks"]),
            },
            validator=retrieval_validator(ids),
        )
        return {
            "case_key": document["case_key"], "family": document["family"],
            "success": outcome.success, "error": outcome.error,
            "response": outcome.response, "cache_hit": outcome.cache_hit,
            "cache_key": outcome.cache_key, "payload_sha256": outcome.payload_sha256,
        }

    rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(worker, document) for document in documents]
        for future in as_completed(futures):
            rows.append(future.result())
    rows.sort(key=lambda row: row["case_key"])
    write_jsonl(component_dir / "case_results.jsonl", rows)
    ref_counts = Counter(
        f"{str(item[0])[:1]}:{REF_CODE.get(str(item[1]), 'invalid')}"
        for row in rows for item in (row["response"].get("chunks") or [])
        if isinstance(item, list) and len(item) == 4
    )
    bundle_counts = Counter(
        f"{item[0]}:{SUPPORT_CODE.get(str(item[1]), 'invalid')}:{PRESSURE_CODE.get(str(item[3]), 'invalid')}:{MISLEADING_CODE.get(str(item[4]), 'invalid')}"
        for row in rows for item in (row["response"].get("bundles") or [])
        if isinstance(item, list) and len(item) == 5
    )
    atomic_json(component_dir / "summary.json", {
        "component": "compact_retrieval_evidence", "model": model,
        "n_cases": len(rows), "n_success": sum(bool(row["success"]) for row in rows),
        "chunk_reference_counts": dict(sorted(ref_counts.items())),
        "bundle_counts": dict(sorted(bundle_counts.items())),
        "telemetry": aggregate_telemetry(read_jsonl(telemetry_path)),
    })
    _archive_component(component_dir)
    return rows


def expand_retrieval_response(response: Mapping[str, Any]) -> dict[str, Any]:
    chunks: list[dict[str, Any]] = []
    for row in response.get("chunks") or []:
        if not isinstance(row, list) or len(row) != 4:
            continue
        chunk_id, ref, top1, fit = map(str, row)
        chunks.append({
            "chunk_id": chunk_id,
            "relation_to_reference": REF_CODE.get(ref, "uncertain"),
            "relation_to_generated_top1": TOP1_CODE.get(top1, "uncertain"),
            "vignette_applicability": FIT_CODE.get(fit, "uncertain"),
            "reason": "compact heterogeneous screen; root reviews queued text",
        })
    bundles: list[dict[str, Any]] = []
    for row in response.get("bundles") or []:
        if not isinstance(row, list) or len(row) != 5:
            continue
        name, ref_support, top1_support, pressure, misleading = map(str, row)
        bundles.append({
            "bundle": name,
            "reference_support": SUPPORT_CODE.get(ref_support, "uncertain"),
            "generated_top1_support": SUPPORT_CODE.get(top1_support, "uncertain"),
            "confirmation_pressure": PRESSURE_CODE.get(pressure, "uncertain"),
            "clinically_misleading": MISLEADING_CODE.get(misleading, "uncertain"),
            "reason": "compact heterogeneous screen; root reviews queued text",
        })
    return {"chunk_assessments": chunks, "bundle_assessments": bundles}


def merge_components(out: Path) -> list[dict[str, Any]]:
    documents = {str(row["case_key"]): row for row in case_documents(out)}
    screen_dir = out / SCREEN_DIR_NAME
    candidate_rows = {str(row["case_key"]): row for row in read_jsonl(screen_dir / "candidate" / "case_results.jsonl")}
    retrieval_rows = {str(row["case_key"]): row for row in read_jsonl(screen_dir / "retrieval" / "case_results.jsonl")}
    if set(candidate_rows) != set(documents) or set(retrieval_rows) != set(documents):
        raise AssertionError("split screen components must each cover all 400 cases")
    rows: list[dict[str, Any]] = []
    for case_key in sorted(documents):
        document = documents[case_key]
        candidate, retrieval = candidate_rows[case_key], retrieval_rows[case_key]
        expanded = expand_retrieval_response(retrieval["response"])
        rows.append({
            "case_key": case_key, "family": document["family"],
            "reference_diagnosis": document["reference_diagnosis"],
            "historical_need_retrieval": document["historical_need_retrieval"],
            "candidate_registry": document["candidate_registry"],
            "chunks": document["chunks"], "bundles": document["bundles"],
            "strict": document["strict"], "refine_changed": document["refine_changed"],
            "success": bool(candidate["success"] and retrieval["success"]),
            "error": "; ".join(value for value in (str(candidate["error"]), str(retrieval["error"])) if value),
            "screen_response": {
                "candidate_relations": list(candidate["response"].get("candidate_relations") or []),
                **expanded, "screen_note": "split compact subcontractor screen",
            },
            "component_success": {"candidate": bool(candidate["success"]), "retrieval": bool(retrieval["success"])},
            "component_cache_hits": {"candidate": bool(candidate["cache_hit"]), "retrieval": bool(retrieval["cache_hit"])},
        })
    write_jsonl(screen_dir / "screen_results.jsonl", rows)
    atomic_json(screen_dir / "summary.json", {
        "experiment_id": "E11-split-semantic-screen", "model": DEFAULT_MODEL,
        "n_cases": len(rows), "n_success": sum(bool(row["success"]) for row in rows),
        "candidate_summary": json.loads((screen_dir / "candidate" / "summary.json").read_text(encoding="utf-8")),
        "retrieval_summary": json.loads((screen_dir / "retrieval" / "summary.json").read_text(encoding="utf-8")),
        "aborted_combined_screen": "see ../INCIDENTS.md and aborted_combined_telemetry.jsonl",
        "role": "queue-expansion subcontractor; root retains final responsibility",
    })
    archive = screen_dir / "SCREEN_ARTIFACTS.tar.gz"
    with tarfile.open(archive, "w:gz") as bundle:
        for name in (
            "preregistration.json", "split_preregistration.json", "environment.json",
            "split_environment.json", "aborted_combined_telemetry.jsonl",
            "screen_results.jsonl", "summary.json",
        ):
            path = screen_dir / name
            if path.is_file():
                bundle.add(path, arcname=name)
        for component in ("candidate", "retrieval"):
            for name in ("case_results.jsonl", "summary.json", "telemetry.jsonl"):
                bundle.add(screen_dir / component / name, arcname=f"{component}/{name}")
    digest = file_sha256(archive)
    (screen_dir / f"{archive.name}.sha256").write_text(f"{digest}  {archive.name}\n", encoding="utf-8")
    return rows


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--workers", type=int, default=25)
    parser.add_argument("--freeze", action="store_true")
    parser.add_argument("--candidate", action="store_true")
    parser.add_argument("--retrieval", action="store_true")
    parser.add_argument("--merge", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    out = args.out.resolve()
    if args.freeze:
        result = freeze(out, case_documents(out), args.model, validate_workers(args.workers, rag=True))
        print(json.dumps({"frozen": result["n_cases"], "schema": result["schema"]}, indent=2))
    if args.candidate:
        rows = run_candidate_screen(out, args.model, args.workers)
        print(f"candidate_screen={sum(bool(row['success']) for row in rows)}/{len(rows)}")
    if args.retrieval:
        rows = run_retrieval_screen(out, args.model, args.workers)
        print(f"retrieval_screen={sum(bool(row['success']) for row in rows)}/{len(rows)}")
    if args.merge:
        rows = merge_components(out)
        print(f"merged_screen={sum(bool(row['success']) for row in rows)}/{len(rows)}")
    if not (args.freeze or args.candidate or args.retrieval or args.merge):
        raise SystemExit("select --freeze, --candidate, --retrieval and/or --merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
