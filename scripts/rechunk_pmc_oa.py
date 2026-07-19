#!/usr/bin/env python3
"""Re-chunk PMC-OA articles from on-disk BioC JSON (no network)."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cpg_api_common import ROOT
from fetch_pmc_bioc import CHUNKS_OUT, merge_manifest, process_article

DEFAULT_INDEX = ROOT / "data" / "cpg" / "api" / "pmc_oa_ddx_index_latest.jsonl"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    rows = [json.loads(l) for l in args.index.read_text().splitlines() if l.strip()]
    if args.limit > 0:
        rows = rows[: args.limit]

    existing: dict[str, dict] = {}
    if CHUNKS_OUT.exists():
        with CHUNKS_OUT.open(encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    c = json.loads(line)
                    existing[c["id"]] = c

    manifests, new_chunks, ok = [], [], 0
    for row in rows:
        manifest, chunks, err = process_article(row, timeout=90, skip_existing=True)
        if err and err != "no_useful_chunks":
            print(f"skip {row.get('pmcid')}: {err}")
            continue
        if manifest:
            manifests.append(manifest)
            new_chunks.extend(chunks)
            ok += 1

    for c in new_chunks:
        existing[c["id"]] = c
    with CHUNKS_OUT.open("w", encoding="utf-8") as f:
        for c in sorted(existing.values(), key=lambda x: x["id"]):
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    if manifests:
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        merge_manifest(manifests, run_id)

    print(json.dumps({"rechunked": ok, "total_chunks": len(existing)}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
