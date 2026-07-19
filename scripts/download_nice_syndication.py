#!/usr/bin/env python3
"""Download NICE syndication guidance content (HTML / JSON) into ``data/cpg/raw/nice/``.

Reads ``data/cpg/open_cpg_nice_seed.json`` (or ``open_cpg_seed.json`` NICE rows)
and fetches syndication API resources. Falls back to public ``www.nice.org.uk``
HTML for entries whose ``access`` is not ``nice_syndication_api``.

Requires a live NICE API-Key (see ``nice_credentials.py``).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cpg_api_common import ROOT, fetch_bytes, fetch_text, write_jsonl
from nice_credentials import DEFAULT_CREDENTIALS_PATH, nice_auth_headers, resolve_api_key

DEFAULT_SEED = ROOT / "data" / "cpg" / "open_cpg_nice_seed.json"
RAW = ROOT / "data" / "cpg" / "raw" / "nice"
TEXT = ROOT / "data" / "cpg" / "text" / "nice"
MANIFEST = ROOT / "data" / "cpg" / "manifest_latest.jsonl"

ACCEPT_HTML = "text/html"
ACCEPT_JSON = "application/vnd.nice.syndication.services+json"


def slugify(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "item"


def html_to_text(html: str) -> str:
    html = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
    html = re.sub(r"(?is)<br\s*/?>", "\n", html)
    html = re.sub(r"(?is)</(p|div|h[1-6]|li|tr)>", "\n", html)
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()


def load_seed(path: Path) -> list[dict]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else []


def api_resource_url(public_url: str) -> str | None:
    """Map www.nice.org.uk/guidance/... to api.nice.org.uk/services/guidance/..."""
    m = re.search(r"nice\.org\.uk/guidance/([^/?#]+)(?:/chapter/([^/?#]+))?", public_url, re.I)
    if not m:
        return None
    code, chapter = m.group(1), m.group(2)
    base = f"https://api.nice.org.uk/services/guidance/{code.lower()}"
    if chapter:
        return f"{base}/chapter/{chapter}"
    return base


def download_one(
    item: dict,
    *,
    api_key: str | None,
    timeout: int,
    skip_existing: bool,
) -> dict:
    iid = item["id"]
    public_url = item.get("url", "")
    access = item.get("access", "")
    raw_path = RAW / f"{slugify(iid)}.html"
    text_path = TEXT / f"{slugify(iid)}.txt"

    rec = {
        "id": iid,
        "source": "NICE",
        "title": item.get("title", ""),
        "url": public_url,
        "status": "pending",
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        "license_note": item.get(
            "license_note",
            "NICE syndication licence; API-Key required.",
        ),
    }

    if skip_existing and raw_path.exists() and text_path.exists():
        rec["status"] = "skipped_existing"
        rec["raw_path"] = str(raw_path.relative_to(ROOT))
        rec["text_path"] = str(text_path.relative_to(ROOT))
        return rec

    body: bytes | None = None
    fetch_url = public_url
    headers: dict[str, str] = {}

    if access == "nice_syndication_api" and api_key:
        api_url = api_resource_url(public_url)
        if api_url:
            fetch_url = api_url
            headers = nice_auth_headers(api_key, ACCEPT_HTML)
        else:
            headers = nice_auth_headers(api_key, ACCEPT_HTML)
            fetch_url = public_url

    try:
        if headers:
            body = fetch_bytes(fetch_url, timeout=timeout, headers=headers)
        else:
            body = fetch_bytes(public_url, timeout=timeout)
    except Exception as exc:
        # fallback to public page
        if fetch_url != public_url:
            try:
                body = fetch_bytes(public_url, timeout=timeout)
                fetch_url = public_url
            except Exception as exc2:
                rec["status"] = "error"
                rec["error"] = f"{exc}; fallback: {exc2}"
                return rec
        else:
            rec["status"] = "error"
            rec["error"] = str(exc)
            return rec

    RAW.mkdir(parents=True, exist_ok=True)
    TEXT.mkdir(parents=True, exist_ok=True)
    raw_path.write_bytes(body)
    text = html_to_text(body.decode("utf-8", errors="replace"))
    text_path.write_text(text + "\n", encoding="utf-8")
    rec["status"] = "ok"
    rec["fetch_url"] = fetch_url
    rec["raw_path"] = str(raw_path.relative_to(ROOT))
    rec["text_path"] = str(text_path.relative_to(ROOT))
    rec["sha256"] = hashlib.sha256(body).hexdigest()
    rec["bytes"] = len(body)
    return rec


def merge_manifest(new_rows: list[dict]) -> None:
    existing: dict[str, dict] = {}
    if MANIFEST.exists():
        with MANIFEST.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                if row.get("id"):
                    existing[row["id"]] = row
    for row in new_rows:
        existing[row["id"]] = row
    write_jsonl(MANIFEST, list(existing.values()))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=Path, default=DEFAULT_SEED)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--sleep", type=float, default=0.35)
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument("--api-key", default=os.environ.get("NICE_API_KEY"))
    parser.add_argument(
        "--credentials-json",
        default=os.environ.get("NICE_CREDENTIALS_JSON", str(DEFAULT_CREDENTIALS_PATH)),
    )
    args = parser.parse_args()

    api_key = (args.api_key or "").strip()
    if not api_key:
        api_key, _ = resolve_api_key(credentials_path=args.credentials_json)

    items = load_seed(args.seed)
    if not items:
        print(json.dumps({"error": f"empty seed: {args.seed}"}), file=sys.stderr)
        return 2

    if args.limit > 0:
        items = items[: args.limit]

    results: list[dict] = []
    for item in items:
        rec = download_one(
            item,
            api_key=api_key,
            timeout=args.timeout,
            skip_existing=args.skip_existing,
        )
        results.append(rec)
        print(json.dumps(rec, ensure_ascii=False))
        if args.sleep > 0:
            time.sleep(args.sleep)

    merge_manifest(results)
    ok = sum(1 for r in results if r.get("status") in {"ok", "skipped_existing"})
    print(
        json.dumps(
            {
                "total": len(results),
                "ok": ok,
                "manifest": str(MANIFEST),
                "api_key_used": bool(api_key),
            },
            indent=2,
        )
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
