#!/usr/bin/env python3
"""Merge per-source CPG chunks into unified cpg_chunks.jsonl (IMP-30).

Inputs (if present):
  - data/cpg/processed/wikem_ddx_chunks.jsonl
  - data/cpg/processed/pmc_oa_ddx_chunks.jsonl
  - data/cpg/processed/manifest_cpg_chunks.jsonl  (NICE + society guidelines from manifest)
  - data/corpus/merck/merck_manual_19e_chunks.jsonl  (purchased 19e, internal RAG only)
  - data/poc/medlineplus/processed/medlineplus_topic_chunks_latest.jsonl  (opt-in only; see eval § harmful)

Output:
  - data/cpg/processed/cpg_chunks.jsonl

Normalises ``title`` to ``section_path`` for RAG / GuidelineBranchSource compatibility.

Do NOT merge by default:
  - MedlinePlus (--include-medlineplus): eval shows Recall@10 −2% on syndrome queries.
  - PubMed abstract_only chunks: excluded via --useful-only; never add abstract layer to index.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cpg_api_common import ROOT
from cpg_manifest_common import is_browser_gate_text

DEFAULT_OUT = ROOT / "data" / "cpg" / "processed" / "cpg_chunks.jsonl"
SOURCES = [
    ROOT / "data" / "cpg" / "processed" / "wikem_ddx_chunks.jsonl",
    ROOT / "data" / "cpg" / "processed" / "pmc_oa_ddx_chunks.jsonl",
    ROOT / "data" / "cpg" / "processed" / "manifest_cpg_chunks.jsonl",
    ROOT / "data" / "corpus" / "merck" / "merck_manual_19e_chunks.jsonl",
]
MEDLINEPLUS = ROOT / "data" / "poc" / "medlineplus" / "processed" / "medlineplus_topic_chunks_latest.jsonl"

USEFUL_TYPES = frozenset({"differential", "red_flag", "evaluation", "recommendation", "diagnostic"})


def normalise_chunk(raw: dict) -> dict:
    section_path = raw.get("section_path") or raw.get("title") or ""
    content = raw.get("content") or raw.get("text") or ""
    out = dict(raw)
    out["title"] = section_path
    out["content"] = content
    out["corpus"] = "cpg"
    out["source_tier"] = raw.get("source_tier") or "guideline"
    if out.get("source") == "MedlinePlus":
        out["source_tier"] = "patient_education"
    if not out.get("article_id"):
        out["article_id"] = raw.get("source_id") or raw.get("parent_manifest_id") or raw.get("manifest_id") or ""
    return out


def normalise_medlineplus(raw: dict) -> dict:
    title = raw.get("title") or ""
    content = raw.get("text") or ""
    mid = raw.get("id") or f"medlineplus_{raw.get('topic_id', '')}"
    section_path = f"{title} > Overview"
    return {
        "id": f"{mid}__chunk_00001",
        "title": section_path,
        "section_path": section_path,
        "content": content,
        "article_id": mid,
        "source_id": mid,
        "source": "MedlinePlus",
        "url": raw.get("url") or "",
        "entry_type": "disease_entry",
        "chunk_type": "evaluation",
        "content_tier": "full_text",
        "license_note": raw.get("license_note") or "NLM MedlinePlus",
    }


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--pmc-require-anchor",
        action="store_true",
        help="only include PMC-OA rows with non-empty syndrome_keywords in manifest index",
    )
    parser.add_argument("--useful-only", action="store_true", help="drop chunk_type=background/other and abstract_only")
    parser.add_argument(
        "--include-medlineplus",
        action="store_true",
        help="merge MedlinePlus (NOT recommended: Recall@10 −2% in eval; patient_education noise)",
    )
    args = parser.parse_args()

    pmc_anchor_ids: set[str] = set()
    if args.pmc_require_anchor:
        index_path = ROOT / "data" / "cpg" / "api" / "pmc_oa_ddx_index_latest.jsonl"
        for row in load_jsonl(index_path):
            if row.get("syndrome_keywords"):
                pmc_anchor_ids.add(row.get("id", ""))

    merged: dict[str, dict] = {}
    stats: dict[str, int] = {}

    for src_path in SOURCES:
        label = src_path.stem
        count = 0
        for raw in load_jsonl(src_path):
            if args.pmc_require_anchor and raw.get("source") == "PMC-OA":
                if raw.get("source_id") not in pmc_anchor_ids:
                    continue
            if args.useful_only and raw.get("chunk_type") not in USEFUL_TYPES:
                if raw.get("entry_type") != "syndrome_entry":
                    continue
            if args.useful_only and raw.get("content_tier") == "abstract_only":
                continue
            content = raw.get("content") or raw.get("text") or ""
            if is_browser_gate_text(content):
                continue
            chunk = normalise_chunk(raw)
            merged[chunk["id"]] = chunk
            count += 1
        stats[label] = count

    if args.include_medlineplus and MEDLINEPLUS.exists():
        label = MEDLINEPLUS.stem
        count = 0
        for raw in load_jsonl(MEDLINEPLUS):
            if args.useful_only and not raw.get("text"):
                continue
            chunk = normalise_chunk(normalise_medlineplus(raw))
            merged[chunk["id"]] = chunk
            count += 1
        stats[label] = count

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as f:
        for chunk in sorted(merged.values(), key=lambda c: c["id"]):
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

    summary = {
        "out": str(args.out.relative_to(ROOT)),
        "total": len(merged),
        "by_source_file": stats,
        "pmc_require_anchor": args.pmc_require_anchor,
        "useful_only": args.useful_only,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
