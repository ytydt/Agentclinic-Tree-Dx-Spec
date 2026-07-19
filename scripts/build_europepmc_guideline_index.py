#!/usr/bin/env python3
"""Build Europe PMC REST index for practice guidelines (metadata + PMC links).

Output: data/cpg/api/europepmc_guideline_index_latest.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cpg_api_common import ROOT, fetch_json, merge_jsonl_latest, polite_sleep

DEFAULT_OUT = ROOT / "data" / "cpg" / "api"
BASE = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
DEFAULT_QUERY = 'PRACTICE GUIDELINE[PT] OR "practice guideline"[PT]'


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=str, default=str(DEFAULT_OUT))
    parser.add_argument("--query", default=DEFAULT_QUERY)
    parser.add_argument("--max-records", type=int, default=2000)
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--sleep", type=float, default=0.25)
    args = parser.parse_args()

    out_dir = ROOT / args.out if not args.out.startswith("/") else __import__("pathlib").Path(args.out)
    rows: list[dict] = []
    cursor = "*"
    seen: set[str] = set()

    while len(rows) < args.max_records:
        params = {
            "query": args.query,
            "format": "json",
            "pageSize": str(min(args.page_size, args.max_records - len(rows))),
            "cursorMark": cursor,
            "resultType": "core",
        }
        url = BASE + "?" + urlencode(params)
        try:
            data = fetch_json(url)
        except Exception as exc:
            print(f"search failed: {exc}", file=sys.stderr)
            break
        results = data.get("resultList", {}).get("result", [])
        if not results:
            break
        for hit in results:
            key = hit.get("pmid") or hit.get("pmcid") or hit.get("id")
            if not key or key in seen:
                continue
            seen.add(key)
            url_out = None
            if hit.get("pmcid"):
                url_out = f"https://pmc.ncbi.nlm.nih.gov/articles/{hit['pmcid']}/"
            elif hit.get("pmid"):
                url_out = f"https://pubmed.ncbi.nlm.nih.gov/{hit['pmid']}/"
            rows.append(
                {
                    "source": "Europe PMC",
                    "id": f"epmc_{key}",
                    "pmid": hit.get("pmid"),
                    "pmcid": hit.get("pmcid"),
                    "doi": hit.get("doi"),
                    "title": hit.get("title"),
                    "journal": hit.get("journalTitle"),
                    "pub_year": hit.get("pubYear"),
                    "pub_type": hit.get("pubType"),
                    "is_open_access": hit.get("isOpenAccess"),
                    "url": url_out,
                    "epmc_url": f"https://europepmc.org/article/{hit.get('source','MED')}/{hit.get('id')}",
                    "indexed_at_utc": datetime.now(timezone.utc).isoformat(),
                }
            )
        next_cursor = data.get("nextCursorMark")
        print(f"collected {len(rows)} / {data.get('hitCount', '?')} hits", flush=True)
        if not next_cursor or next_cursor == cursor:
            break
        cursor = next_cursor
        polite_sleep(args.sleep)

    manifest, latest = merge_jsonl_latest(rows, out_dir, "europepmc_guideline_index")
    summary = {
        "records": len(rows),
        "query": args.query,
        "manifest": str(manifest.relative_to(ROOT)),
        "latest": str(latest.relative_to(ROOT)),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
