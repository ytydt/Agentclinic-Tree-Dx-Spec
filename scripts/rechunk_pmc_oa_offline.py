#!/usr/bin/env python3
"""Re-chunk PMC-OA strictly from the on-disk BioC cache, never the network.

rechunk_pmc_oa.py goes through process_article(), which falls back to an HTTP
fetch whenever the raw or text cache is missing, and it merges its output into
the live chunk file.  This one skips uncached articles and writes to a separate
file, so the corpus the current index was built from is left alone.

  python scripts/rechunk_pmc_oa_offline.py --out data/cpg/processed/pmc_oa_ddx_chunks_v2.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cpg_api_common import ROOT  # noqa: E402
from fetch_pmc_bioc import RAW_DIR  # noqa: E402
from pmc_oa_ddx_common import (  # noqa: E402
    normalize_pmcid,
    parse_bioc_collection,
    passages_to_chunks,
    slugify,
)

DEFAULT_INDEX = ROOT / "data" / "cpg" / "api" / "pmc_oa_ddx_index_latest.jsonl"
DEFAULT_OUT = ROOT / "data" / "cpg" / "processed" / "pmc_oa_ddx_chunks_v2.jsonl"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    rows = [json.loads(l) for l in args.index.read_text(encoding="utf-8").splitlines()
            if l.strip()]
    if args.limit:
        rows = rows[: args.limit]

    stat = Counter()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as fh:
        for row in rows:
            pmcid = normalize_pmcid(row.get("pmcid"))
            if not pmcid:
                stat["no_pmcid"] += 1
                continue
            raw_path = RAW_DIR / f"bioc-{slugify(pmcid)}.json"
            if not raw_path.exists():
                stat["uncached"] += 1
                continue
            try:
                payload = json.loads(raw_path.read_text(encoding="utf-8"))
            except Exception:
                stat["unparsable"] += 1
                continue
            doc_meta, passages = parse_bioc_collection(payload)
            if not passages:
                stat["empty_bioc"] += 1
                continue

            license_note = doc_meta.get("license") or row.get("license") or "pmc_oa"
            syndrome_kw = row.get("syndrome_keywords") or []
            _, chunks = passages_to_chunks(
                passages,
                source_id=row.get("id") or f"pmc_oa_ddx__{pmcid.lower()}",
                title=row.get("title") or doc_meta.get("article-id_pmid") or pmcid,
                pmcid=pmcid,
                pmid=row.get("pmid"),
                license_note=f"pmc_oa:{license_note}",
                url=row.get("url"),
                syndrome_anchor=syndrome_kw[0] if syndrome_kw else None,
            )
            stat["articles"] += 1
            for c in chunks:
                fh.write(json.dumps(c, ensure_ascii=False) + "\n")
                stat["chunks"] += 1
                stat[f"pt:{c['passage_type']}"] += 1

    for k, v in stat.most_common():
        print(f"  {k:<24}{v:>8}")
    print(f"Output: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
