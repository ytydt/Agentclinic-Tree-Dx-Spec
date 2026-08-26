#!/usr/bin/env python3
"""Merge validated KG record additions into internal and public graph views."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agentclinic_tree_dx.knowledge.guideline_kg_extraction import RecordAccumulator  # noqa: E402
from agentclinic_tree_dx.knowledge.guideline_kg_schema import assert_valid_graph  # noqa: E402
from build_guideline_diagnostic_kg import _public_projection  # noqa: E402


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: expected object")
            records.append(value)
    return records


def atomic_write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> int:
    temporary = path.with_name(path.name + ".tmp")
    count = 0
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(canonical_json(row) + "\n")
            count += 1
    os.replace(temporary, path)
    return count


def merge_graphs(
    *, base_graph: Path, additions: Sequence[Path], output_dir: Path,
) -> dict[str, Any]:
    base_records = read_jsonl(base_graph)
    assert_valid_graph(base_records)
    accumulator = RecordAccumulator(base_records)
    source_descriptors: list[dict[str, Any]] = []
    for path in additions:
        rows = read_jsonl(path)
        before = len(accumulator.records)
        for row in rows:
            accumulator.add(row)
        source_descriptors.append({
            "path": str(path),
            "sha256": file_sha256(path),
            "input_records": len(rows),
            "new_unique_records": len(accumulator.records) - before,
        })
    records = accumulator.values()
    assert_valid_graph(records)
    public = _public_projection(records)
    output_dir.mkdir(parents=True, exist_ok=True)
    internal_path = output_dir / "graph.hybrid.internal.jsonl"
    public_path = output_dir / "graph.hybrid.public.jsonl"
    atomic_write_jsonl(internal_path, records)
    atomic_write_jsonl(public_path, public)
    manifest = {
        "schema": "guideline_diagnostic_kg_v0.1",
        "pipeline": "validated_record_merge_v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_graph": {
            "path": str(base_graph),
            "sha256": file_sha256(base_graph),
            "records": len(base_records),
        },
        "additions": source_descriptors,
        "record_counts": dict(sorted(Counter(
            row["record_type"] for row in records
        ).items())),
        "full_graph_validation": "passed",
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
        },
    }
    manifest_path = output_dir / "merge_manifest.json"
    temporary = manifest_path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, manifest_path)
    return manifest


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-graph", type=Path, required=True)
    parser.add_argument("--additions", type=Path, action="append", default=[])
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    outputs = (
        args.output_dir / "graph.hybrid.internal.jsonl",
        args.output_dir / "graph.hybrid.public.jsonl",
        args.output_dir / "merge_manifest.json",
    )
    existing = [path for path in outputs if path.exists()]
    if existing and not args.force:
        parser.error(
            "refusing to overwrite existing outputs; pass --force: "
            + ", ".join(str(path) for path in existing)
        )
    manifest = merge_graphs(
        base_graph=args.base_graph,
        additions=args.additions,
        output_dir=args.output_dir,
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
