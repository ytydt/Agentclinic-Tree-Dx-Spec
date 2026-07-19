#!/usr/bin/env python3
"""Build a PubMed E-utilities index of practice guidelines (metadata only).

Output: data/cpg/api/pubmed_guideline_index_latest.jsonl
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cpg_api_common import (
    ROOT,
    merge_jsonl_latest,
    polite_sleep,
    pubmed_esearch,
    pubmed_esummary,
)

DEFAULT_OUT = ROOT / "data" / "cpg" / "api"
DEFAULT_TERMS = [
    "Practice Guideline[PT]",
    "Guideline[PT]",
    "Consensus Development Conference[PT]",
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=str, default=str(DEFAULT_OUT))
    parser.add_argument("--max-per-term", type=int, default=500, help="max PMIDs per query term")
    parser.add_argument("--batch-size", type=int, default=200)
    parser.add_argument("--sleep", type=float, default=0.34)
    parser.add_argument("--email", default=os.environ.get("PUBMED_EMAIL", "research@local.invalid"))
    parser.add_argument("--api-key", default=os.environ.get("NCBI_API_KEY"))
    args = parser.parse_args()

    out_dir = ROOT / args.out if not args.out.startswith("/") else __import__("pathlib").Path(args.out)
    rows: list[dict] = []
    seen: set[str] = set()

    for term in DEFAULT_TERMS:
        retstart = 0
        fetched = 0
        while fetched < args.max_per_term:
            retmax = min(args.batch_size, args.max_per_term - fetched)
            try:
                data = pubmed_esearch(term, retstart, retmax, args.email, args.api_key)
            except Exception as exc:
                print(f"esearch failed for {term!r}: {exc}", file=sys.stderr)
                break
            result = data.get("esearchresult", {})
            idlist = result.get("idlist", [])
            if not idlist:
                break
            try:
                summary = pubmed_esummary(idlist, args.email, args.api_key)
            except Exception as exc:
                print(f"esummary failed: {exc}", file=sys.stderr)
                break
            for pmid in idlist:
                if pmid in seen:
                    continue
                seen.add(pmid)
                item = summary.get("result", {}).get(pmid, {})
                rows.append(
                    {
                        "source": "PubMed",
                        "id": f"pubmed_{pmid}",
                        "pmid": pmid,
                        "title": item.get("title"),
                        "journal": item.get("fulljournalname") or item.get("source"),
                        "pubdate": item.get("pubdate"),
                        "authors": item.get("authors", []),
                        "doi": (item.get("elocationid") or "").replace("doi: ", "") if item.get("elocationid", "").startswith("doi:") else None,
                        "pub_types": item.get("pubtype", []),
                        "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                        "query_term": term,
                        "indexed_at_utc": datetime.now(timezone.utc).isoformat(),
                    }
                )
            fetched += len(idlist)
            retstart += len(idlist)
            count = int(result.get("count", 0))
            print(f"{term}: {fetched}/{min(args.max_per_term, count)}", flush=True)
            if retstart >= count:
                break
            polite_sleep(args.sleep)

    manifest, latest = merge_jsonl_latest(rows, out_dir, "pubmed_guideline_index")
    summary = {
        "records": len(rows),
        "unique_pmids": len(seen),
        "terms": DEFAULT_TERMS,
        "manifest": str(manifest.relative_to(ROOT)),
        "latest": str(latest.relative_to(ROOT)),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
