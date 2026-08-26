#!/usr/bin/env python3
"""Build the deterministic/template lane of the diagnostic guideline KG.

The internal ledger preserves source text and exact evidence and therefore is
not automatically suitable for redistribution.  A second, pointer-only public
projection contains hashes and source locators but no passage text or quote.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agentclinic_tree_dx.knowledge.guideline_kg_extraction import (  # noqa: E402
    RecordAccumulator,
    diagnostic_passage_reasons,
    extract_template_assertions,
    extract_wikem_differential_memberships,
    load_disease_aliases,
    passage_metadata,
    residual_priority,
    sha256_text,
    template_activity,
)
from agentclinic_tree_dx.knowledge.guideline_kg_schema import (  # noqa: E402
    assert_valid_graph,
    record_to_dict,
)

DEFAULT_PASSAGES = ROOT / "data/knowledge_graph/guideline_diagnostic_kg_v0_1/passages"
DEFAULT_OUTPUT = ROOT / "data/knowledge_graph/guideline_diagnostic_kg_v0_1/build"
DEFAULT_ALIASES = ROOT / "data/knowledge_raw/disease_name_bridge_flat.json"
SOURCE_FILENAMES = (
    "source_works.jsonl",
    "document_versions.jsonl",
    "sections.jsonl",
    "passages.jsonl",
)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_records(path: Path) -> list[dict[str, Any]]:
    files: list[Path]
    if path.is_dir():
        files = [path / name for name in SOURCE_FILENAMES if (path / name).exists()]
        if not files:
            files = sorted(path.glob("*.jsonl"))
    else:
        files = [path]
    records: list[dict[str, Any]] = []
    for source in files:
        with source.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError(f"{source}:{line_number}: expected JSON object")
                records.append(value)
    return records


def atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, sort_keys=True, indent=2)
        handle.write("\n")
    os.replace(temporary, path)


def atomic_write_jsonl(path: Path, records: Iterable[Mapping[str, Any]]) -> int:
    temporary = path.with_name(path.name + ".tmp")
    count = 0
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(
                record, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ))
            handle.write("\n")
            count += 1
    os.replace(temporary, path)
    return count


def _passage_source(passage: Mapping[str, Any]) -> str:
    metadata = passage_metadata(passage)
    return str(metadata.get("source") or metadata.get("source_family") or "unknown")


def _public_projection(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return a quote-free, non-authoritative release view.

    This is intentionally not presented as the authoring-schema ledger: source
    text is needed to validate exact evidence offsets.  Each public assertion
    points to a hashed evidence locator that an authorized internal deployment
    can resolve against ``graph.internal.jsonl``.
    """

    index = {record["id"]: record for record in records}
    public: list[dict[str, Any]] = []
    keep_types = {
        "Concept", "DiagnosisExpression", "FeaturePattern", "LogicExpression",
        "DiagnosticAssertion", "DifferentialAssertion", "ConceptMapping",
    }
    for record in records:
        if record.get("record_type") not in keep_types:
            continue
        output = json.loads(json.dumps(record))
        if output.get("record_type") == "FeaturePattern":
            # The canonical label is the queryable fact surface; the verbatim
            # source mention is internal-only.  Long prose-like labels are
            # replaced by a stable pointer to avoid reconstructable excerpts.
            output["surface"] = None
            label = str(output.get("canonical_label") or "")
            if len(label) > 240:
                output["canonical_label"] = f"long_feature:{sha256_text(label)}"
                output.setdefault("extensions", {})["redacted_label_chars"] = len(label)
        if output.get("record_type") in {"DiagnosticAssertion", "DifferentialAssertion"}:
            # The broad projection is an unreviewed authoring ledger.  Make
            # the safety default explicit so a consumer cannot mistake a
            # missing flag for permission to use candidate edges in ranking.
            output.setdefault("qualifiers", {})["ranking_eligible"] = False
            pointers = []
            for span_id in output.pop("evidence_span_ids", []):
                span = index.get(span_id, {})
                passage = index.get(span.get("passage_id"), {})
                ext = passage.get("extensions") or {}
                metadata = passage_metadata(passage)
                quote = str(span.get("quote") or "")
                pointers.append({
                    "evidence_span_id": span_id,
                    "passage_id": span.get("passage_id"),
                    "source": metadata.get("source"),
                    "source_record_ids": ext.get("source_record_ids", []),
                    "section_path": ext.get("section_path", []),
                    "quote_sha256": sha256_text(quote),
                    "quote_length_chars": len(quote),
                })
            output["evidence_pointers"] = pointers
            output["release_profile"] = (
                "pointer_only_unreviewed_nonranking_v2"
            )
        public.append(output)
    return public


def build(args: argparse.Namespace) -> dict[str, Any]:
    source_records = read_records(args.passages)
    source_errors = []
    if not args.skip_input_validation:
        from agentclinic_tree_dx.knowledge.guideline_kg_schema import validate_graph
        source_errors = validate_graph(source_records)
        if source_errors:
            preview = "\n".join(source_errors[:30])
            raise ValueError(f"passage graph failed validation ({len(source_errors)}):\n{preview}")
    all_passages = [
        record for record in source_records if record.get("record_type") == "Passage"
    ]
    passages = list(all_passages)
    if args.source:
        wanted = {value.casefold() for value in args.source}
        passages = [p for p in passages if _passage_source(p).casefold() in wanted]
    passages.sort(key=lambda item: item["id"])
    if not args.include_unadmitted:
        passages = [p for p in passages if diagnostic_passage_reasons(p)]
    if args.limit is not None:
        passages = passages[:args.limit]

    selected_ids = {p["id"] for p in passages}
    # Claim-aware windows may cite a context Passage that is not itself a
    # diagnostic seed.  The internal authoring graph must therefore retain the
    # complete audited-clean source ledger; the gate controls extraction, not
    # whether exact provenance exists.  A compact pilot can explicitly opt out.
    if args.source_context == "all":
        selected_source_records = source_records
    else:
        selected_source_records = [
            record for record in source_records
            if record.get("record_type") != "Passage" or record.get("id") in selected_ids
        ]
    input_fingerprint = hashlib.sha256("\n".join(
        f"{p['id']}:{sha256_text(str(p.get('text') or ''))}" for p in passages
    ).encode("utf-8")).hexdigest()
    activity = template_activity(input_fingerprint)
    accumulator = RecordAccumulator([
        *selected_source_records, record_to_dict(activity),
    ])
    aliases = load_disease_aliases(args.disease_aliases)

    stats = Counter()
    residual_rows: list[dict[str, Any]] = []
    for passage in passages:
        template_ids = extract_template_assertions(
            passage, aliases=aliases, activity_id=activity.id,
            accumulator=accumulator,
        )
        structural_ids = extract_wikem_differential_memberships(
            passage, aliases=aliases, activity_id=activity.id,
            accumulator=accumulator,
        )
        stats["template_assertions"] += len(template_ids)
        stats["structural_memberships"] += len(structural_ids)
        stats["passages_processed"] += 1
        priority = residual_priority(
            passage, template_count=len(template_ids) + len(structural_ids),
        )
        if priority >= args.residual_priority:
            residual_rows.append({
                "passage_id": passage["id"],
                "priority": priority,
                "source": _passage_source(passage),
                "reasons": diagnostic_passage_reasons(passage),
                "template_assertion_ids": template_ids,
                "structural_assertion_ids": structural_ids,
                "text_sha256": sha256_text(str(passage.get("text") or "")),
                "text_chars": len(str(passage.get("text") or "")),
            })

    records = accumulator.values()
    assert_valid_graph(records)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    internal_path = args.output_dir / "graph.internal.jsonl"
    public_path = args.output_dir / "graph.public.jsonl"
    queue_path = args.output_dir / "residual_queue.jsonl"
    atomic_write_jsonl(internal_path, records)
    atomic_write_jsonl(public_path, _public_projection(records))
    residual_rows.sort(key=lambda item: (-item["priority"], item["passage_id"]))
    atomic_write_jsonl(queue_path, residual_rows)

    type_counts = Counter(record["record_type"] for record in records)
    source_counts = Counter(_passage_source(passage) for passage in passages)
    manifest = {
        "schema": "guideline_diagnostic_kg_v0.1",
        "pipeline": "deterministic_template_plus_residual_queue",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_path": str(args.passages),
        "input_fingerprint_sha256": input_fingerprint,
        "disease_alias_path": str(args.disease_aliases),
        "disease_alias_sha256": (
            file_sha256(args.disease_aliases) if args.disease_aliases.exists() else None
        ),
        "source_filter": args.source,
        "include_unadmitted": args.include_unadmitted,
        "source_context": args.source_context,
        "source_passages_available": len(all_passages),
        "source_passages_preserved": sum(
            record.get("record_type") == "Passage"
            for record in selected_source_records
        ),
        "limit": args.limit,
        "residual_priority_threshold": args.residual_priority,
        "record_counts": dict(sorted(type_counts.items())),
        "source_passage_counts": dict(sorted(source_counts.items())),
        "statistics": dict(sorted(stats.items())),
        "residual_queue_count": len(residual_rows),
        "outputs": {
            "internal": {
                "path": str(internal_path),
                "sha256": file_sha256(internal_path),
                "bytes": internal_path.stat().st_size,
                "contains_source_text": True,
                "redistribution_review_required": True,
            },
            "public": {
                "path": str(public_path),
                "sha256": file_sha256(public_path),
                "bytes": public_path.stat().st_size,
                "contains_passages_or_exact_quotes": False,
                "authoritative": False,
            },
            "residual_queue": {
                "path": str(queue_path),
                "sha256": file_sha256(queue_path),
                "bytes": queue_path.stat().st_size,
                "contains_source_text": False,
            },
        },
    }
    atomic_write_json(args.output_dir / "manifest.json", manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--passages", type=Path, default=DEFAULT_PASSAGES)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--disease-aliases", type=Path, default=DEFAULT_ALIASES)
    parser.add_argument("--source", action="append", help="exact source value; repeatable")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--include-unadmitted", action="store_true")
    parser.add_argument(
        "--source-context",
        choices=("all", "selected"),
        default="all",
        help=(
            "all (default) retains every audited-clean Passage for claim-window "
            "offset projection; selected creates a compact pilot ledger only"
        ),
    )
    parser.add_argument("--residual-priority", type=int, default=4)
    parser.add_argument("--skip-input-validation", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    if not 0 <= args.residual_priority <= 10:
        parser.error("--residual-priority must be between 0 and 10")
    outputs = (
        args.output_dir / "graph.internal.jsonl",
        args.output_dir / "graph.public.jsonl",
        args.output_dir / "residual_queue.jsonl",
        args.output_dir / "manifest.json",
    )
    existing = [path for path in outputs if path.exists()]
    if existing and not args.force:
        parser.error(
            "refusing to overwrite existing output(s): "
            + ", ".join(str(path) for path in existing)
            + "; pass --force"
        )
    manifest = build(args)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
