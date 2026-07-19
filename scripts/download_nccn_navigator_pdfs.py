#!/usr/bin/env python3
"""Download NCCN Guidelines PDFs (Navigator list or full category catalog).

Requires a registered NCCN.org account via environment variables:

  export NCCN_USERNAME='you@example.org'
  export NCCN_PASSWORD='...'

Output: data/cpg/restricted/nccn/ (gitignored). NCCN EULA applies; do not redistribute.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "data" / "cpg" / "restricted" / "nccn"
NAVIGATOR_URL = "https://www.nccn.org/guidelines/nccn-guidelines-navigator"
LOGIN_INDEX = "https://www.nccn.org/login/Index/"
PDF_BASE = "https://www.nccn.org/professionals/physician_gls/pdf/"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
PDF_SUFFIX_SKIP = ("_blocks", "_basic", "_core", "_enhanced", "_patient", "_blocks_spanish")
DETAIL_RE = re.compile(
    r'href="/guidelines/nccn-guidelines/guidelines-detail\?category=(\d+)&amp;id=(\d+)">([^<]+)</a>'
)


def slugify(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "untitled"


def login(session: requests.Session, username: str, password: str) -> None:
    page = session.get(LOGIN_INDEX, timeout=45)
    page.raise_for_status()
    inputs: dict[str, str] = {}
    for name, val in re.findall(r'<input[^>]*name="([^"]*)"[^>]*value="([^"]*)"', page.text, re.I):
        inputs[name] = val
    for name in re.findall(r'<input[^>]*name="([^"]*)"[^>]*>', page.text, re.I):
        inputs.setdefault(name, "")
    payload = {
        "Username": username,
        "Password": password,
        "RememberMe": "true",
        **{k: v for k, v in inputs.items() if k not in {"Username", "Password"}},
    }
    resp = session.post(LOGIN_INDEX, data=payload, timeout=45, allow_redirects=True)
    resp.raise_for_status()
    if "IsNCCNUser" not in session.cookies:
        raise RuntimeError("NCCN login did not set expected session cookies")


def build_detail_map(html: str) -> dict[str, tuple[str, str]]:
    detail_map: dict[str, tuple[str, str]] = {}
    for m in DETAIL_RE.finditer(html):
        detail_map[m.group(3).strip()] = (m.group(1), m.group(2))
    return detail_map


def attach_detail_urls(items: list[dict], detail_map: dict[str, tuple[str, str]]) -> None:
    for item in items:
        cat_id = detail_map.get(item["title"])
        if not cat_id:
            item["status"] = "missing_detail_link"
            continue
        category, detail_id = cat_id
        item["detail_url"] = (
            f"https://www.nccn.org/guidelines/nccn-guidelines/guidelines-detail"
            f"?category={category}&id={detail_id}"
        )


def parse_navigator_items(html: str, detail_map: dict[str, tuple[str, str]]) -> list[dict]:
    items: list[dict] = []
    for m in re.finditer(
        r'<a[^>]+href="(https://guidelines\.nccn\.org/guidelines/[^"]+)"[^>]*>([^<]+)</a>\s*'
        r'<span class="p-0">(Version [^<]+)</span>',
        html,
    ):
        items.append(
            {
                "title": m.group(2).strip(),
                "version": m.group(3).strip(),
                "navigator_url": m.group(1),
                "catalog_scope": "navigator",
            }
        )
    attach_detail_urls(items, detail_map)
    return items


def parse_full_catalog(session: requests.Session, timeout: int) -> list[dict]:
    detail_map: dict[str, tuple[str, str]] = {}
    for cat in range(1, 5):
        html = session.get(f"https://www.nccn.org/guidelines/category_{cat}", timeout=timeout).text
        detail_map.update(build_detail_map(html))
        nav_html = session.get(NAVIGATOR_URL, timeout=timeout).text if cat == 1 else ""
        if cat == 1:
            detail_map.update(build_detail_map(nav_html))
    items: list[dict] = []
    for title, (category, detail_id) in sorted(detail_map.items()):
        items.append(
            {
                "title": title,
                "version": None,
                "navigator_url": None,
                "catalog_scope": "full",
                "detail_url": (
                    f"https://www.nccn.org/guidelines/nccn-guidelines/guidelines-detail"
                    f"?category={category}&id={detail_id}"
                ),
            }
        )
    return items


def extract_version_from_detail(html: str) -> str | None:
    m = re.search(r"Version\s+\d+\.\d{4}", html)
    return m.group(0) if m else None


def choose_main_pdf_slug(page_html: str, title: str) -> str | None:
    slugs = re.findall(r"/professionals/physician_gls/pdf/([^\"']+\.pdf)", page_html, re.I)
    candidates: list[str] = []
    for slug in slugs:
        lower = slug.lower()
        if any(part in lower for part in PDF_SUFFIX_SKIP):
            continue
        if lower.startswith("framework"):
            continue
        candidates.append(slug)
    if not candidates:
        return None
    title_slug = slugify(title).replace("-", "")
    scored: list[tuple[int, int, str]] = []
    for slug in dict.fromkeys(candidates):
        stem = slug.lower()[:-4] if slug.lower().endswith(".pdf") else slug.lower()
        score = 0
        if stem in title_slug or title_slug.startswith(stem.replace("_", "")):
            score += 10
        score -= len(stem)
        scored.append((score, len(stem), slug))
    scored.sort(key=lambda row: (-row[0], row[1]))
    return scored[0][2]


def extract_pdf_text(payload: bytes) -> str | None:
    try:
        from pypdf import PdfReader  # type: ignore
    except Exception:
        return None
    reader = PdfReader(io.BytesIO(payload))
    pages: list[str] = []
    for idx, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        if text.strip():
            pages.append(f"\n\n--- page {idx} ---\n{text.strip()}")
    return "\n".join(pages).strip() + "\n" if pages else None


def load_existing_ids(raw_dir: Path) -> set[str]:
    return {p.stem for p in raw_dir.glob("*.pdf")}


def download_item(
    session: requests.Session,
    item: dict,
    raw_dir: Path,
    text_dir: Path,
    timeout: int,
    skip_existing: bool,
) -> dict:
    record = {
        "id": slugify(item["title"]),
        "source": "NCCN",
        "title": item["title"],
        "version": item.get("version"),
        "navigator_url": item.get("navigator_url"),
        "detail_url": item.get("detail_url"),
        "catalog_scope": item.get("catalog_scope"),
        "clinical_area": ["oncology"],
        "access": "restricted_login_pdf",
        "license_note": "NCCN EULA; personal registered account; do not redistribute.",
    }
    raw_path = raw_dir / f"{record['id']}.pdf"
    text_path = text_dir / f"{record['id']}.txt"
    if skip_existing and raw_path.exists():
        payload = raw_path.read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        record.update(
            {
                "status": "ok",
                "bytes": len(payload),
                "sha256": digest,
                "raw_path": str(raw_path.relative_to(ROOT)),
                "text_path": str(text_path.relative_to(ROOT)) if text_path.exists() else None,
                "content_type": "cached",
            }
        )
        return record
    if not item.get("detail_url"):
        record.update({"status": "error", "error": item.get("status", "missing_detail_link")})
        return record
    try:
        detail_html = session.get(item["detail_url"], timeout=timeout).text
        if not record.get("version"):
            record["version"] = extract_version_from_detail(detail_html)
        pdf_slug = choose_main_pdf_slug(detail_html, item["title"])
        if not pdf_slug:
            record.update({"status": "error", "error": "main pdf slug not found on detail page"})
            return record
        pdf_url = urljoin(PDF_BASE, pdf_slug)
        resp = session.get(pdf_url, timeout=timeout)
        resp.raise_for_status()
        payload = resp.content
        if not payload.startswith(b"%PDF"):
            record.update(
                {
                    "status": "error",
                    "url": pdf_url,
                    "error": "response is not a PDF payload",
                    "http_status": resp.status_code,
                    "content_type": resp.headers.get("Content-Type"),
                }
            )
            return record
        digest = hashlib.sha256(payload).hexdigest()
        raw_path.write_bytes(payload)
        pdf_text = extract_pdf_text(payload)
        if pdf_text:
            text_path.write_text(pdf_text, encoding="utf-8")
        record.update(
            {
                "status": "ok",
                "url": pdf_url,
                "http_status": resp.status_code,
                "content_type": resp.headers.get("Content-Type"),
                "bytes": len(payload),
                "sha256": digest,
                "raw_path": str(raw_path.relative_to(ROOT)),
                "text_path": str(text_path.relative_to(ROOT)) if pdf_text else None,
            }
        )
    except requests.RequestException as exc:
        record.update({"status": "error", "error": repr(exc)})
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--sleep", type=float, default=1.0)
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument(
        "--scope",
        choices=("navigator", "full", "missing-full"),
        default="navigator",
        help="navigator=41 Navigator PDFs; full=all category guidelines; missing-full=full minus existing raw",
    )
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument("--username", default=os.environ.get("NCCN_USERNAME"))
    parser.add_argument("--password", default=os.environ.get("NCCN_PASSWORD"))
    args = parser.parse_args()

    if not args.username or not args.password:
        print("Set NCCN_USERNAME and NCCN_PASSWORD in the environment.", file=sys.stderr)
        return 2

    out_dir = args.out.resolve()
    raw_dir = out_dir / "raw"
    text_dir = out_dir / "text"
    raw_dir.mkdir(parents=True, exist_ok=True)
    text_dir.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    login(session, args.username, args.password)

    nav_html = session.get(NAVIGATOR_URL, timeout=args.timeout).text
    detail_map = build_detail_map(nav_html)
    for cat in range(1, 5):
        detail_map.update(build_detail_map(session.get(f"https://www.nccn.org/guidelines/category_{cat}", timeout=args.timeout).text))

    if args.scope == "navigator":
        items = parse_navigator_items(nav_html, detail_map)
    else:
        items = parse_full_catalog(session, args.timeout)
        if args.scope == "missing-full":
            existing = load_existing_ids(raw_dir)
            items = [item for item in items if slugify(item["title"]) not in existing]

    if not items:
        print("No items to download.", file=sys.stderr)
        return 0

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    manifest_path = out_dir / f"manifest_{run_id}.jsonl"
    latest_path = out_dir / "manifest_latest.jsonl"
    summary_path = out_dir / f"summary_{run_id}.json"
    records: list[dict] = []

    for idx, item in enumerate(items, start=1):
        label = item["title"]
        if item.get("version"):
            label = f"{label} ({item['version']})"
        print(f"[{idx}/{len(items)}] {label}", flush=True)
        records.append(
            download_item(session, item, raw_dir, text_dir, args.timeout, args.skip_existing)
        )
        if idx != len(items):
            time.sleep(args.sleep)

    with manifest_path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")

    merged: dict[str, dict] = {}
    if latest_path.exists() and args.skip_existing:
        for line in latest_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                prev = json.loads(line)
                merged[prev["id"]] = prev
    for record in records:
        merged[record["id"]] = record
    merged_lines = "\n".join(
        json.dumps(rec, ensure_ascii=False, sort_keys=True) for rec in merged.values()
    ) + "\n"
    latest_path.write_text(merged_lines, encoding="utf-8")

    summary = {
        "run_id": run_id,
        "scope": args.scope,
        "navigator_url": NAVIGATOR_URL,
        "output_dir": str(out_dir),
        "manifest_path": str(manifest_path.relative_to(ROOT)),
        "total": len(records),
        "ok": sum(1 for r in records if r["status"] == "ok"),
        "error": sum(1 for r in records if r["status"] != "ok"),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "license_note": "Restricted NCCN content; personal account download only.",
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["error"] == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
