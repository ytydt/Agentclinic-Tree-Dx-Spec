#!/usr/bin/env python3
"""Build PMC-OA DDx review discovery index (Europe PMC + optional PubMed).

Output: data/cpg/api/pmc_oa_ddx_index_latest.jsonl

See OPEN_CPG_DOWNLOADS.md § PMC-OA 抓取指引.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cpg_api_common import (
    ROOT,
    fetch_json,
    merge_jsonl_latest,
    polite_sleep,
    pubmed_esearch,
    pubmed_esummary,
)
from pmc_oa_ddx_common import (
    EUROPEPMC_DDX_QUERIES,
    PUBMED_DDX_QUERY,
    dedupe_key,
    extract_syndrome_anchor,
    normalize_pmcid,
)

DEFAULT_OUT = ROOT / "data" / "cpg" / "api"
EPMC_BASE = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"


def pubmed_elink_pmc(pmids: list[str], email: str, api_key: str | None) -> dict[str, str]:
    if not pmids:
        return {}
    from urllib.request import Request, urlopen

    params = {
        "dbfrom": "pubmed",
        "db": "pmc",
        "id": ",".join(pmids),
        "retmode": "json",
        "email": email,
    }
    if api_key:
        params["api_key"] = api_key
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/elink.fcgi?" + urlencode(params)
    req = Request(url, headers={"User-Agent": "Agentclinic-Tree-Dx-Spec/0.1"})
    with urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    out: dict[str, str] = {}
    for block in data.get("linksets", []):
        src = str(block.get("ids", [""])[0])
        for linksetdb in block.get("linksetdbs") or []:
            if linksetdb.get("dbto") == "pmc":
                links = linksetdb.get("links") or []
                if links:
                    out[src] = normalize_pmcid(str(links[0])) or ""
    return out


def fetch_europepmc(query: str, *, max_records: int, page_size: int, sleep: float) -> list[dict]:
    rows: list[dict] = []
    cursor = "*"
    seen: set[str] = set()

    while len(rows) < max_records:
        params = {
            "query": query,
            "format": "json",
            "pageSize": str(min(page_size, max_records - len(rows))),
            "cursorMark": cursor,
            "resultType": "core",
        }
        url = EPMC_BASE + "?" + urlencode(params)
        try:
            data = fetch_json(url)
        except Exception as exc:
            print(f"Europe PMC search failed: {exc}", file=sys.stderr)
            break

        results = data.get("resultList", {}).get("result", [])
        if not results:
            break

        for hit in results:
            pmcid = normalize_pmcid(hit.get("pmcid"))
            pmid = hit.get("pmid")
            key = pmcid or pmid or hit.get("id")
            if not key or key in seen:
                continue
            seen.add(key)
            title = hit.get("title") or ""
            rows.append(
                {
                    "source": "Europe PMC",
                    "id": f"pmc_oa_ddx__{pmcid or pmid or key}",
                    "pmid": pmid,
                    "pmcid": pmcid,
                    "doi": hit.get("doi"),
                    "title": title,
                    "journal": hit.get("journalTitle"),
                    "pub_year": hit.get("pubYear"),
                    "pub_type": hit.get("pubType"),
                    "is_open_access": hit.get("isOpenAccess") == "Y",
                    "license": hit.get("license"),
                    "url": f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/" if pmcid else (
                        f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else None
                    ),
                    "epmc_url": f"https://europepmc.org/article/{hit.get('source', 'MED')}/{hit.get('id')}",
                    "query_matched": query,
                    "syndrome_keywords": extract_syndrome_anchor(title),
                    "has_pmc_fulltext": bool(pmcid),
                    "indexed_at_utc": datetime.now(timezone.utc).isoformat(),
                }
            )

        next_cursor = data.get("nextCursorMark")
        print(f"  Europe PMC collected {len(rows)} / {data.get('hitCount', '?')}", flush=True)
        if not next_cursor or next_cursor == cursor:
            break
        cursor = next_cursor
        polite_sleep(sleep)

    return rows


def fetch_pubmed_ddx(*, max_records: int, batch_size: int, sleep: float, email: str, api_key: str | None) -> list[dict]:
    rows: list[dict] = []
    retstart = 0
    while len(rows) < max_records:
        retmax = min(batch_size, max_records - len(rows))
        try:
            data = pubmed_esearch(PUBMED_DDX_QUERY, retstart, retmax, email, api_key)
        except Exception as exc:
            print(f"PubMed esearch failed: {exc}", file=sys.stderr)
            break
        result = data.get("esearchresult", {})
        idlist = result.get("idlist", [])
        if not idlist:
            break
        try:
            summary = pubmed_esummary(idlist, email, api_key)
            elink = pubmed_elink_pmc(idlist, email, api_key)
        except Exception as exc:
            print(f"PubMed esummary/elink failed: {exc}", file=sys.stderr)
            break

        for pmid in idlist:
            item = summary.get("result", {}).get(pmid, {})
            title = item.get("title") or ""
            pmcid = normalize_pmcid(elink.get(pmid))
            rows.append(
                {
                    "source": "PubMed",
                    "id": f"pmc_oa_ddx__{pmcid or pmid}",
                    "pmid": pmid,
                    "pmcid": pmcid,
                    "doi": (item.get("elocationid") or "").replace("doi: ", "")
                    if str(item.get("elocationid", "")).startswith("doi:")
                    else None,
                    "title": title,
                    "journal": item.get("fulljournalname") or item.get("source"),
                    "pub_year": (item.get("pubdate") or "")[:4] or None,
                    "pub_type": item.get("pubtype"),
                    "is_open_access": True,
                    "license": None,
                    "url": f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/" if pmcid else f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                    "epmc_url": None,
                    "query_matched": PUBMED_DDX_QUERY,
                    "syndrome_keywords": extract_syndrome_anchor(title),
                    "has_pmc_fulltext": bool(pmcid),
                    "indexed_at_utc": datetime.now(timezone.utc).isoformat(),
                }
            )

        retstart += len(idlist)
        count = int(result.get("count", 0))
        print(f"  PubMed collected {len(rows)} / {min(max_records, count)}", flush=True)
        if retstart >= count:
            break
        polite_sleep(sleep)

    return rows


def merge_rows(*groups: list[dict]) -> list[dict]:
    merged: dict[str, dict] = {}
    for group in groups:
        for row in group:
            key = dedupe_key(row)
            if key not in merged:
                merged[key] = row
                continue
            prev = merged[key]
            qm = prev.get("query_matched")
            new_q = row.get("query_matched")
            if new_q and new_q not in str(qm):
                prev["query_matched"] = f"{qm}; {new_q}" if qm else new_q
            if not prev.get("pmcid") and row.get("pmcid"):
                prev["pmcid"] = row["pmcid"]
                prev["has_pmc_fulltext"] = True
                prev["url"] = row.get("url")
            if not prev.get("syndrome_keywords") and row.get("syndrome_keywords"):
                prev["syndrome_keywords"] = row["syndrome_keywords"]
    return sorted(merged.values(), key=lambda r: r.get("id", ""))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=str, default=str(DEFAULT_OUT))
    parser.add_argument("--max-per-query", type=int, default=2000, help="max hits per Europe PMC query")
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--sleep", type=float, default=0.25)
    parser.add_argument("--pubmed", action="store_true", help="also query PubMed esearch + elink PMC")
    parser.add_argument("--pubmed-max", type=int, default=2000)
    parser.add_argument("--email", default=os.environ.get("PUBMED_EMAIL", "research@local.invalid"))
    parser.add_argument("--api-key", default=os.environ.get("NCBI_API_KEY"))
    args = parser.parse_args()

    out_dir = Path(args.out) if args.out.startswith("/") else ROOT / args.out
    all_groups: list[list[dict]] = []

    for label, query in EUROPEPMC_DDX_QUERIES:
        print(f"Europe PMC query [{label}] …", flush=True)
        rows = fetch_europepmc(query, max_records=args.max_per_query, page_size=args.page_size, sleep=args.sleep)
        for row in rows:
            row["query_label"] = label
        all_groups.append(rows)

    if args.pubmed:
        print("PubMed DDx query …", flush=True)
        all_groups.append(
            fetch_pubmed_ddx(
                max_records=args.pubmed_max,
                batch_size=min(200, args.page_size),
                sleep=max(args.sleep, 0.34),
                email=args.email,
                api_key=args.api_key,
            )
        )

    merged = merge_rows(*all_groups)
    manifest, latest = merge_jsonl_latest(merged, out_dir, "pmc_oa_ddx_index")
    with_pmc = sum(1 for r in merged if r.get("has_pmc_fulltext"))
    with_anchor = sum(1 for r in merged if r.get("syndrome_keywords"))

    summary = {
        "records": len(merged),
        "with_pmc_fulltext": with_pmc,
        "with_syndrome_anchor": with_anchor,
        "queries": [label for label, _ in EUROPEPMC_DDX_QUERIES],
        "pubmed": args.pubmed,
        "manifest": str(manifest.relative_to(ROOT)),
        "latest": str(latest.relative_to(ROOT)),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
