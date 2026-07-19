#!/usr/bin/env python3
"""Build RAG chunks from open CPG manifest HTML/text (IMP-30 / CPG §1.5.3).

Reads data/cpg/manifest_latest.jsonl and writes per-source chunks for:
  - NICE nice_ddx__* / nice_pub__* chapters
  - Society guidelines (IDSA, ACOG, ACR, ACC/AHA PMC, ESC, …)
  - PubMed abstract mirrors (content_tier=abstract_only)

Skips: WikEM, PMC-OA (separate pipelines), Merck/MSD online, index/hub pages.

Output: data/cpg/processed/manifest_cpg_chunks.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cpg_api_common import ROOT
from cpg_manifest_common import (
    USEFUL_CHUNK_TYPES,
    chunk_manifest_row,
    iter_manifest_rows,
    manifest_has_bot_gate,
    should_skip_manifest_row,
)

DEFAULT_MANIFEST = ROOT / "data" / "cpg" / "manifest_latest.jsonl"
DEFAULT_OUT = ROOT / "data" / "cpg" / "processed" / "manifest_cpg_chunks.jsonl"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--max-tokens", type=int, default=320)
    parser.add_argument("--source", action="append", help="only process manifest source label(s)")
    parser.add_argument("--id-prefix", action="append", help="only manifest ids starting with prefix")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--useful-only", action="store_true", help="drop background/other and abstract_only")
    args = parser.parse_args()

    if not args.manifest.exists():
        print(f"Manifest not found: {args.manifest}", file=sys.stderr)
        return 1

    stats: Counter = Counter()
    skip_reasons: Counter = Counter()
    by_source: Counter = Counter()
    all_chunks: list[dict] = []
    processed = 0

    for row in iter_manifest_rows(args.manifest):
        skip, reason = should_skip_manifest_row(row)
        if skip:
            skip_reasons[reason] += 1
            continue
        source = row.get("source") or "unknown"
        if args.source and source not in args.source:
            continue
        mid = row.get("id") or ""
        if args.id_prefix and not any(mid.startswith(p) for p in args.id_prefix):
            continue

        if manifest_has_bot_gate(row, ROOT):
            skip_reasons["bot_gate"] += 1
            continue

        chunks = chunk_manifest_row(row, ROOT, max_tokens=args.max_tokens)
        processed += 1
        if not chunks:
            skip_reasons["empty_after_parse"] += 1
            continue

        kept = 0
        for c in chunks:
            if args.useful_only:
                if c.get("content_tier") == "abstract_only":
                    continue
                if c.get("chunk_type") not in USEFUL_CHUNK_TYPES:
                    if c.get("entry_type") != "syndrome_entry":
                        continue
            all_chunks.append(c)
            kept += 1
            by_source[source] += 1

        stats["articles_with_chunks"] += 1
        stats["raw_chunks"] += len(chunks)
        stats["kept_chunks"] += kept

        if args.limit and processed >= args.limit:
            break

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as f:
        for c in sorted(all_chunks, key=lambda x: x["id"]):
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    summary = {
        "out": str(args.out.relative_to(ROOT)),
        "manifest": str(args.manifest.relative_to(ROOT)),
        "articles_processed": processed,
        "articles_with_chunks": stats["articles_with_chunks"],
        "raw_chunks": stats["raw_chunks"],
        "kept_chunks": stats["kept_chunks"],
        "written": len(all_chunks),
        "by_source": dict(by_source.most_common()),
        "skip_reasons": dict(skip_reasons.most_common()),
        "useful_only": args.useful_only,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
