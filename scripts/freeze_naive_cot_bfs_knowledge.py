#!/usr/bin/env python3
"""Freeze arm-blind case bundles from the BFS grounded chunk catalogue."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from agentclinic_tree_dx.l1_evidence_bfs import stable_hash  # noqa: E402

DEFAULT_CATALOG = (
    ROOT / "eval_fixtures" / "l1_grounded_chunk_catalog_v1.json"
)
DEFAULT_OUTPUT = (
    ROOT / "eval_fixtures" / "naive_cot_bfs_knowledge_v1.json"
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    temp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp.replace(path)


def select_arm_blind_bundle(
    excerpts: Sequence[Mapping[str, Any]],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    """Round-robin facts, preferring comparative/high-specificity excerpts."""
    by_fact: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for excerpt in excerpts:
        row = dict(excerpt)
        by_fact[str(row.get("fact_id") or "")].append(row)
    for rows in by_fact.values():
        rows.sort(key=lambda row: (
            not bool(row.get("has_compare")),
            not bool(row.get("has_highspec")),
            not bool(row.get("has_neg")),
            not bool(row.get("has_num")),
            str(row.get("candidate") or ""),
            str(row.get("access_id") or ""),
        ))
    selected: list[dict[str, Any]] = []
    seen_access: set[str] = set()
    depth = 0
    fact_ids = sorted(by_fact)
    while len(selected) < limit:
        added = False
        for fact_id in fact_ids:
            rows = by_fact[fact_id]
            if depth >= len(rows):
                continue
            row = rows[depth]
            access_id = str(row.get("access_id") or "")
            if access_id and access_id not in seen_access:
                selected.append(row)
                seen_access.add(access_id)
                added = True
                if len(selected) >= limit:
                    break
        if not added:
            break
        depth += 1
    return selected


def freeze(
    catalog_path: Path,
    output_path: Path,
    *,
    max_chunks: int = 12,
) -> dict[str, Any]:
    source = json.loads(catalog_path.read_text(encoding="utf-8"))
    expected_catalog_hash = str(
        (source.get("manifest") or {}).get("catalog_hash") or ""
    )
    excerpts = list(source.get("excerpts") or ())
    if stable_hash(excerpts) != expected_catalog_hash:
        raise ValueError("BFS grounded catalogue hash mismatch")
    case_ids = list(
        (source.get("matching_audit") or {}).get("cases") or ()
    )
    excerpts_by_case: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for excerpt in excerpts:
        excerpts_by_case[str(excerpt.get("case_id") or "")].append(
            dict(excerpt)
        )
    cases = []
    for case_id in case_ids:
        available = excerpts_by_case.get(str(case_id), [])
        bundle = select_arm_blind_bundle(
            available, limit=max_chunks,
        )
        cases.append({
            "case_id": str(case_id),
            "available_excerpt_count": len(available),
            "served_count": len(bundle),
            "served_access_ids": [
                str(row["access_id"]) for row in bundle
            ],
            "served_bundle_hash": stable_hash(bundle),
            "knowledge_chunks": bundle,
        })
    payload = {
        "schema_version": 1,
        "asset_kind": "naive_cot_shared_bfs_knowledge",
        "selection_policy": (
            "arm_blind_fact_round_robin_compare_highspec_neg_num"
        ),
        "max_requested_chunks": max_chunks,
        "source_catalog_path": str(catalog_path.relative_to(ROOT)),
        "source_catalog_sha256": _sha256(catalog_path),
        "source_catalog_hash": expected_catalog_hash,
        "source_asset_hashes": dict(
            (source.get("manifest") or {}).get("asset_hashes") or {}
        ),
        "cases": cases,
        "coverage_audit": {
            "case_count": len(cases),
            "cases_with_chunks": sum(
                bool(row["served_count"]) for row in cases
            ),
            "cases_without_chunks": [
                row["case_id"] for row in cases
                if not row["served_count"]
            ],
            "served_chunks": sum(row["served_count"] for row in cases),
            "available_excerpts": sum(
                row["available_excerpt_count"] for row in cases
            ),
        },
    }
    payload["fixture_hash"] = stable_hash(payload)
    _atomic_json(output_path, payload)
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--max-chunks", type=int, default=12)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = freeze(
        args.catalog, args.output, max_chunks=args.max_chunks,
    )
    print(json.dumps({
        "output": str(args.output),
        "fixture_hash": result["fixture_hash"],
        "coverage_audit": result["coverage_audit"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
