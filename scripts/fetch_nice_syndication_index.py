#!/usr/bin/env python3
"""Fetch NICE syndication API guidance index.

Docs: https://www.nice.org.uk/corporate/ecd10/chapter/using-your-api-key-to-explore-nice-content

Credentials (API-Key header, **not** OAuth client_secret):
  - ``NICE_API_KEY`` environment variable, or
  - ``api_key`` field in the registration JSON (``--credentials-json`` /
    ``NICE_CREDENTIALS_JSON``).

The registration file's ``client_id`` / ``client_secret`` are application
registration metadata; they are **not** accepted as API-Key until NICE activates
the account and you copy the live key from https://api.nice.org.uk/account .

Output: ``data/cpg/api/nice_syndication_index_latest.jsonl``
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cpg_api_common import ROOT, fetch_json, merge_jsonl_latest
from nice_credentials import DEFAULT_CREDENTIALS_PATH, nice_auth_headers, resolve_api_key

DEFAULT_OUT = ROOT / "data" / "cpg" / "api"
NICE_BASE = "https://api.nice.org.uk/services/"
ACCEPT_JSON = "application/vnd.nice.syndication.services+json"

# ECD10 guidance entry points (Screenshot 6)
DEFAULT_START_URLS = [
    NICE_BASE,
    urljoin(NICE_BASE, "guidance"),
    urljoin(NICE_BASE, "guidance/index"),
    urljoin(NICE_BASE, "guidance/programmes"),
    urljoin(NICE_BASE, "guidance/taxonomy"),
]


def _normalise_href(href: str, base: str) -> str | None:
    if not href:
        return None
    if href.startswith("/"):
        parsed = urlparse(base)
        href = f"{parsed.scheme}://{parsed.netloc}{href}"
    if href.startswith(NICE_BASE.rstrip("/") + "/") or href == NICE_BASE.rstrip("/"):
        return href.split("?", 1)[0]
    if href.startswith("https://api.nice.org.uk/"):
        return href.split("?", 1)[0]
    return None


def crawl(
    start_urls: list[str],
    api_key: str,
    *,
    max_depth: int,
    max_nodes: int,
    sleep: float,
) -> list[dict]:
    headers = nice_auth_headers(api_key, ACCEPT_JSON)
    rows: list[dict] = []
    seen: set[str] = set()
    queue: list[tuple[str, int]] = [(u, 0) for u in dict.fromkeys(start_urls)]

    while queue and len(seen) < max_nodes:
        node_url, depth = queue.pop(0)
        if node_url in seen or depth > max_depth:
            continue
        seen.add(node_url)
        try:
            data = fetch_json(node_url, headers=headers)
        except Exception as exc:
            print(f"skip fetch {node_url}: {exc}", file=sys.stderr)
            continue
        if sleep > 0:
            time.sleep(sleep)

        title = data.get("title") or data.get("name")
        web = data.get("webUrl") or data.get("url")
        if title:
            rows.append(
                {
                    "source": "NICE",
                    "id": f"nice_api_{data.get('id') or data.get('guid') or len(rows)}",
                    "title": title,
                    "url": web or node_url,
                    "api_url": node_url,
                    "nice_id": data.get("id"),
                    "guid": data.get("guid"),
                    "type": data.get("type"),
                    "status": data.get("status"),
                    "indexed_at_utc": datetime.now(timezone.utc).isoformat(),
                }
            )

        if depth >= max_depth:
            continue
        for link in data.get("links", []) or []:
            rel = (link.get("rel") or link.get("relation") or "").lower()
            href = _normalise_href(link.get("href") or "", node_url)
            if not href or rel in {"self", "prev", "next", "alternate"}:
                continue
            if href not in seen:
                queue.append((href, depth + 1))
    return rows


def verify_api_key(api_key: str) -> None:
    headers = nice_auth_headers(api_key, ACCEPT_JSON)
    fetch_json(NICE_BASE, headers=headers)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=str, default=str(DEFAULT_OUT))
    parser.add_argument("--start-url", action="append", dest="start_urls", default=[])
    parser.add_argument("--max-depth", type=int, default=3)
    parser.add_argument("--max-nodes", type=int, default=8000)
    parser.add_argument("--sleep", type=float, default=0.15)
    parser.add_argument("--api-key", default=os.environ.get("NICE_API_KEY"))
    parser.add_argument(
        "--credentials-json",
        default=os.environ.get("NICE_CREDENTIALS_JSON", str(DEFAULT_CREDENTIALS_PATH)),
    )
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()

    api_key = (args.api_key or "").strip()
    cred_meta: dict = {}
    if not api_key:
        api_key, cred_meta = resolve_api_key(credentials_path=args.credentials_json)
    else:
        cred_meta = {"source": "CLI --api-key"}

    if not api_key:
        print(
            json.dumps(
                {
                    "error": "no NICE API key",
                    "hint": (
                        "Set NICE_API_KEY, add api_key to the credentials JSON, or pass --api-key. "
                        "Registration client_id/client_secret are NOT the syndication API-Key. "
                        "After licence approval, activate https://api.nice.org.uk/account and copy the API key."
                    ),
                    "credentials": cred_meta,
                },
                indent=2,
            ),
            file=sys.stderr,
        )
        return 2

    try:
        verify_api_key(api_key)
    except Exception as exc:
        print(
            json.dumps(
                {
                    "error": "NICE API authentication failed",
                    "detail": str(exc),
                    "hint": (
                        "401 usually means the key is missing, wrong, or not yet active. "
                        "Log in to https://api.nice.org.uk/account , accept the licence, "
                        "then set NICE_API_KEY to the key shown on the account page."
                    ),
                    "credentials": cred_meta,
                },
                indent=2,
            ),
            file=sys.stderr,
        )
        return 3

    if args.verify_only:
        print(json.dumps({"ok": True, "credentials": cred_meta}, indent=2))
        return 0

    start_urls = args.start_urls or DEFAULT_START_URLS
    rows = crawl(
        start_urls,
        api_key,
        max_depth=args.max_depth,
        max_nodes=args.max_nodes,
        sleep=args.sleep,
    )

    # de-dupe by url
    deduped: dict[str, dict] = {}
    for row in rows:
        key = (row.get("url") or row.get("api_url") or row.get("id") or "").lower()
        if key:
            deduped[key] = row
    rows = list(deduped.values())

    out_dir = ROOT / args.out if not str(args.out).startswith("/") else Path(args.out)
    manifest, latest = merge_jsonl_latest(rows, out_dir, "nice_syndication_index")
    summary = {
        "records": len(rows),
        "manifest": str(manifest.relative_to(ROOT)),
        "latest": str(latest.relative_to(ROOT)),
        "start_urls": start_urls,
        "credentials": cred_meta,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
