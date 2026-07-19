#!/usr/bin/env python3
"""Freeze hydrated P5 evidence chunks for isolated grounded L1 selection."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import eval_l1_evidence_bfs as bfs  # noqa: E402
from agentclinic_tree_dx.grounded_evidence import (  # noqa: E402
    ChunkExcerpt,
    catalog_manifest,
    load_needed_chunk_texts,
)


DEFAULT_AUDIT = bfs.DEFAULT_ARM_OUTPUTS["p5_headline"]
DEFAULT_OUTPUT = (
    ROOT / "eval_fixtures" / "l1_grounded_chunk_catalog_v1.json"
)
DEFAULT_METADATA = (
    ROOT / "data" / "corpus" / "cpg_index" / "metadata.jsonl",
    ROOT / "data" / "corpus" / "case_report_index" / "metadata.jsonl",
)
DEFAULT_MANIFEST = ROOT / "data" / "eval" / "p5_external_asset_manifest.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    temp.replace(path)


def _matched_entries(args: argparse.Namespace) -> tuple[
    list[dict[str, Any]], dict[str, Any],
]:
    composed = bfs._load_module("grounded_freeze_composed", bfs.COMPOSED_SCRIPT)
    partial = bfs._load_module("grounded_freeze_partial", bfs.PARTIAL_SCRIPT)
    cases = partial._select_cases(
        partial.assemble_cases(), args.cases, args.limit,
    )
    audit = json.loads(args.audit.read_text(encoding="utf-8"))
    audit_by_case = dict(audit.get("disc_audit") or {})
    matched_rows: list[dict[str, Any]] = []
    case_audit: dict[str, Any] = {}
    needed: set[str] = set()
    for case in cases:
        case_id = str(case["id"])
        tree_payload = json.loads(
            (args.shared_tree_dir / f"{case_id}.json").read_text(encoding="utf-8")
        )
        frozen_tree = composed._deserialize_state(tree_payload["state"])
        facts = bfs._facts_for_case(
            frozen_tree, case["annotation"], composed, deduplicate=True,
        )
        rules = list(audit_by_case.get(case_id) or ())
        matched_facts = 0
        evidence_rows = 0
        for fact in facts:
            matched = composed._best_reference(fact.text, rules)
            if matched is None:
                continue
            matched_facts += 1
            for evidence in matched.get("evidence") or ():
                if not isinstance(evidence, Mapping):
                    continue
                chunk_id = str(evidence.get("chunk_id") or "")
                ev_id = str(evidence.get("ev_id") or "")
                if not chunk_id or not ev_id:
                    continue
                needed.add(chunk_id)
                evidence_rows += 1
                matched_rows.append({
                    "case_id": case_id,
                    "fact_id": fact.id,
                    "finding_text": fact.text,
                    "matched_compiler_finding": str(
                        matched.get("finding") or ""
                    ),
                    "compiler_verdict": str(
                        matched.get("verdict") or "unmatched"
                    ),
                    "ev_id": ev_id,
                    "chunk_id": chunk_id,
                    "source": str(evidence.get("source") or ""),
                    "candidate": str(evidence.get("candidate") or ""),
                    "has_compare": bool(evidence.get("has_compare")),
                    "has_neg": bool(evidence.get("has_neg")),
                    "has_num": bool(evidence.get("has_num")),
                    "has_highspec": bool(evidence.get("has_highspec")),
                })
        case_audit[case_id] = {
            "facts": len(facts),
            "matched_facts": matched_facts,
            "evidence_rows": evidence_rows,
        }
    return matched_rows, {
        "cases": sorted(case_audit),
        "by_case": case_audit,
        "needed_chunk_ids": sorted(needed),
    }


def freeze(args: argparse.Namespace) -> dict[str, Any]:
    if args.output.exists() and not args.overwrite:
        raise FileExistsError(
            f"{args.output} exists; pass --overwrite to replace it"
        )
    matched_rows, matching = _matched_entries(args)
    texts, hydration = load_needed_chunk_texts(
        args.metadata, matching["needed_chunk_ids"],
    )
    excerpts: list[dict[str, Any]] = []
    for row in matched_rows:
        text = texts.get(row["chunk_id"])
        if not text:
            continue
        bounded = text[: args.max_chunk_chars]
        excerpt = ChunkExcerpt(
            access_id=(
                f"{row['case_id']}::{row['fact_id']}::{row['ev_id']}"
            ),
            fact_id=str(row["fact_id"]),
            finding_text=str(row["finding_text"]),
            ev_id=str(row["ev_id"]),
            chunk_id=str(row["chunk_id"]),
            source=str(row["source"]),
            candidate=str(row["candidate"]),
            text=bounded,
            has_compare=bool(row["has_compare"]),
            has_neg=bool(row["has_neg"]),
            has_num=bool(row["has_num"]),
            has_highspec=bool(row["has_highspec"]),
        ).to_dict()
        excerpt.update({
            "case_id": row["case_id"],
            "matched_compiler_finding": row["matched_compiler_finding"],
            "compiler_verdict": row["compiler_verdict"],
            "source_text_chars": len(text),
            "text_truncated": len(text) > len(bounded),
        })
        excerpts.append(excerpt)
    excerpts.sort(
        key=lambda row: (
            row["case_id"], row["fact_id"], row["ev_id"], row["chunk_id"],
        )
    )
    assets = [args.audit, args.manifest, *args.metadata]
    asset_hashes = {
        str(path.relative_to(ROOT)): _sha256(path)
        for path in assets if path.is_file()
    }
    hydration_summary = {
        **hydration,
        "source_by_id": {},
        "matched_evidence_rows": len(matched_rows),
        "frozen_excerpts": len(excerpts),
        "frozen_fraction": (
            len(excerpts) / len(matched_rows) if matched_rows else 0.0
        ),
    }
    result = {
        "schema_version": 1,
        "purpose": (
            "Read-only hydrated P5 chunks for isolated grounded L1 selection"
        ),
        "max_chunk_chars": args.max_chunk_chars,
        "manifest": catalog_manifest(
            excerpts,
            asset_hashes=asset_hashes,
            hydration_audit=hydration_summary,
        ),
        "matching_audit": matching,
        "excerpts": excerpts,
    }
    _atomic_json(args.output, result)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument(
        "--metadata", type=Path, action="append",
        default=list(DEFAULT_METADATA),
    )
    parser.add_argument(
        "--shared-tree-dir", type=Path, default=bfs.DEFAULT_SHARED_TREE_DIR,
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--max-chunk-chars", type=int, default=1600)
    parser.add_argument("--cases", default="")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    result = freeze(parse_args())
    print(json.dumps({
        "output": str(DEFAULT_OUTPUT),
        "manifest": result["manifest"],
    }, ensure_ascii=False, indent=2))
