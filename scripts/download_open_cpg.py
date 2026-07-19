#!/usr/bin/env python3
"""Download a small, auditable mirror of public clinical practice guidelines.

The script intentionally uses an explicit seed list instead of broad crawling.
It stores raw responses, best-effort plain text for HTML pages, and a JSONL
manifest that can be reviewed before any downstream indexing.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import io
import json
import re
import ssl
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SEED = ROOT / "data" / "cpg" / "open_cpg_seed.json"
DEFAULT_OUT = ROOT / "data" / "cpg"
USER_AGENT = (
    "Mozilla/5.0 (compatible; Agentclinic-Tree-Dx-Spec/0.2; "
    "+https://github.com/local/research) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


class VisibleTextExtractor(HTMLParser):
    """Tiny HTML-to-text extractor for review/indexing previews."""

    SKIP_TAGS = {"script", "style", "noscript", "svg", "canvas"}
    BLOCK_TAGS = {
        "address",
        "article",
        "aside",
        "blockquote",
        "br",
        "div",
        "dl",
        "fieldset",
        "figcaption",
        "figure",
        "footer",
        "form",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "hr",
        "li",
        "main",
        "nav",
        "ol",
        "p",
        "pre",
        "section",
        "table",
        "td",
        "th",
        "tr",
        "ul",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.SKIP_TAGS:
            self._skip_depth += 1
        if tag in self.BLOCK_TAGS:
            self._chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1
        if tag in self.BLOCK_TAGS:
            self._chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            self._chunks.append(data)

    def text(self) -> str:
        raw = html.unescape(" ".join(self._chunks))
        raw = re.sub(r"[ \t\r\f\v]+", " ", raw)
        raw = re.sub(r"\n\s+", "\n", raw)
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        return raw.strip() + "\n"


@dataclass
class DownloadResult:
    item: dict
    status: str
    http_status: int | None = None
    content_type: str | None = None
    bytes: int = 0
    sha256: str | None = None
    raw_path: str | None = None
    text_path: str | None = None
    error: str | None = None


def slugify(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "untitled"


def extension_for(content_type: str | None, url: str, payload: bytes | None = None) -> str:
    if payload is not None and is_pdf_payload(payload):
        return ".pdf"
    path_suffix = Path(urlparse(url).path).suffix.lower()
    if path_suffix in {".html", ".htm", ".pdf", ".xml", ".json", ".txt"}:
        return path_suffix
    content_type = (content_type or "").split(";", 1)[0].strip().lower()
    if content_type == "application/pdf":
        return ".pdf"
    if content_type in {"application/json", "application/vnd.api+json"}:
        return ".json"
    if content_type in {"application/xml", "text/xml", "application/atom+xml"}:
        return ".xml"
    return ".html"


def is_html(content_type: str | None, ext: str) -> bool:
    content_type = (content_type or "").lower()
    return ext in {".html", ".htm"} or "text/html" in content_type


def is_pdf(content_type: str | None, ext: str) -> bool:
    content_type = (content_type or "").lower()
    return ext == ".pdf" or "application/pdf" in content_type


def is_pdf_payload(payload: bytes) -> bool:
    return payload.startswith(b"%PDF")


def ssl_context(insecure: bool = False) -> ssl.SSLContext:
    if insecure:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    try:
        import certifi  # type: ignore

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def fetch(url: str, timeout: int, *, insecure: bool = False) -> tuple[int, str | None, bytes]:
    req = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/pdf;q=0.8,*/*;q=0.5",
        },
    )
    with urlopen(req, timeout=timeout, context=ssl_context(insecure)) as resp:
        return resp.status, resp.headers.get("Content-Type"), resp.read()


def extract_html_text(payload: bytes) -> str:
    text = payload.decode("utf-8", errors="replace")
    parser = VisibleTextExtractor()
    parser.feed(text)
    parser.close()
    return parser.text()


def extract_pdf_text(payload: bytes) -> str | None:
    try:
        from pypdf import PdfReader  # type: ignore
    except Exception:
        return None

    reader = PdfReader(io.BytesIO(payload))
    pages: list[str] = []
    for idx, page in enumerate(reader.pages, start=1):
        page_text = page.extract_text() or ""
        if page_text.strip():
            pages.append(f"\n\n--- page {idx} ---\n{page_text.strip()}")
    return "\n".join(pages).strip() + "\n" if pages else None


def iter_seed_items(seed_path: Path) -> Iterable[dict]:
    with seed_path.open("r", encoding="utf-8") as f:
        items = json.load(f)
    if not isinstance(items, list):
        raise ValueError(f"seed file must contain a list: {seed_path}")
    for item in items:
        if not item.get("id") or not item.get("url"):
            raise ValueError(f"seed item missing id or url: {item}")
        yield item


def download_one(
    item: dict,
    out_dir: Path,
    timeout: int,
    skip_existing: bool = False,
    insecure: bool = False,
) -> DownloadResult:
    source_dir = slugify(item.get("source", "unknown"))
    slug = slugify(item["id"])
    raw_dir = out_dir / "raw" / source_dir
    text_dir = out_dir / "text" / source_dir
    raw_dir.mkdir(parents=True, exist_ok=True)
    text_dir.mkdir(parents=True, exist_ok=True)

    existing = sorted(raw_dir.glob(f"{slug}.*"))
    if skip_existing and existing:
        raw_path = existing[0]
        ext = raw_path.suffix.lower()
        payload = raw_path.read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        text_path = text_dir / f"{slug}.txt"
        text_path_value = str(text_path.relative_to(ROOT)) if text_path.exists() else None
        return DownloadResult(
            item=item,
            status="ok",
            content_type="cached",
            bytes=len(payload),
            sha256=digest,
            raw_path=str(raw_path.relative_to(ROOT)),
            text_path=text_path_value,
        )

    try:
        status_code, content_type, payload = fetch(item["url"], timeout, insecure=insecure)
        digest = hashlib.sha256(payload).hexdigest()
        expected_pdf = item.get("access") == "public_pdf"
        if expected_pdf and not is_pdf_payload(payload):
            return DownloadResult(
                item=item,
                status="error",
                http_status=status_code,
                content_type=content_type,
                bytes=len(payload),
                sha256=digest,
                error="expected PDF payload but response did not start with %PDF",
            )
        ext = extension_for(content_type, item["url"], payload)

        raw_dir = out_dir / "raw" / source_dir
        text_dir = out_dir / "text" / source_dir
        raw_dir.mkdir(parents=True, exist_ok=True)
        text_dir.mkdir(parents=True, exist_ok=True)

        raw_path = raw_dir / f"{slug}{ext}"
        raw_path.write_bytes(payload)

        text_path: Path | None = None
        if is_html(content_type, ext):
            text_path = text_dir / f"{slug}.txt"
            text_path.write_text(extract_html_text(payload), encoding="utf-8")
        elif is_pdf(content_type, ext):
            pdf_text = extract_pdf_text(payload)
            if pdf_text:
                text_path = text_dir / f"{slug}.txt"
                text_path.write_text(pdf_text, encoding="utf-8")

        return DownloadResult(
            item=item,
            status="ok",
            http_status=status_code,
            content_type=content_type,
            bytes=len(payload),
            sha256=digest,
            raw_path=str(raw_path.relative_to(ROOT)),
            text_path=str(text_path.relative_to(ROOT)) if text_path else None,
        )
    except HTTPError as exc:
        return DownloadResult(item=item, status="error", http_status=exc.code, error=str(exc))
    except (TimeoutError, URLError, OSError) as exc:
        return DownloadResult(item=item, status="error", error=repr(exc))


def result_record(result: DownloadResult) -> dict:
    record = {
        "id": result.item["id"],
        "parent_id": result.item.get("parent_id"),
        "kind": result.item.get("kind", "primary"),
        "source": result.item.get("source"),
        "title": result.item.get("title"),
        "url": result.item.get("url"),
        "clinical_area": result.item.get("clinical_area", []),
        "access": result.item.get("access"),
        "status": result.status,
        "http_status": result.http_status,
        "content_type": result.content_type,
        "bytes": result.bytes,
        "sha256": result.sha256,
        "raw_path": result.raw_path,
        "text_path": result.text_path,
        "error": result.error,
    }
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=Path, default=DEFAULT_SEED)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--timeout", type=int, default=45)
    parser.add_argument("--sleep", type=float, default=1.0, help="delay between requests")
    parser.add_argument("--limit", type=int, default=None, help="download only the first N seed items")
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="reuse raw files already present for an item id without re-fetching",
    )
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="disable TLS certificate verification (for hosts blocked by local CA chain)",
    )
    args = parser.parse_args()

    out_dir = args.out.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    manifest_path = out_dir / f"manifest_{run_id}.jsonl"
    latest_path = out_dir / "manifest_latest.jsonl"
    summary_path = out_dir / f"summary_{run_id}.json"

    seed_items = list(iter_seed_items(args.seed))
    if args.limit is not None:
        seed_items = seed_items[: args.limit]

    items: list[dict] = []
    for item in seed_items:
        primary = dict(item)
        primary["kind"] = "primary"
        items.append(primary)
        for attachment in item.get("attachments", []):
            attach_item = {
                **item,
                **attachment,
                "id": f"{item['id']}__{attachment['id']}",
                "parent_id": item["id"],
                "kind": "attachment",
            }
            attach_item.pop("attachments", None)
            items.append(attach_item)

    records: list[dict] = []
    for idx, item in enumerate(items, start=1):
        print(f"[{idx}/{len(items)}] {item['id']} -> {item['url']}", flush=True)
        result = download_one(
            item, out_dir, args.timeout, skip_existing=args.skip_existing, insecure=args.insecure
        )
        records.append(result_record(result))
        if idx != len(items):
            time.sleep(args.sleep)

    with manifest_path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")

    merged: dict[str, dict] = {}
    if latest_path.exists():
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
        "seed_path": str(args.seed.resolve()),
        "output_dir": str(out_dir),
        "manifest_path": str(manifest_path.relative_to(ROOT)),
        "total": len(records),
        "ok": sum(1 for record in records if record["status"] == "ok"),
        "error": sum(1 for record in records if record["status"] != "ok"),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["error"] == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
