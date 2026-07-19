#!/usr/bin/env python3
"""Discover and fetch WikEM syndrome-entry pages (Category:Symptoms).

Writes:
  - data/cpg/api/wikem_syndrome_index_latest.jsonl
  - data/cpg/raw/wikem/{slug}.html
  - data/cpg/text/wikem/wikem-{slug}.txt
  - data/cpg/processed/wikem_ddx_chunks.jsonl
  - data/knowledge_raw/cant_miss_by_syndrome_wikem.json
  - merges data/cpg/manifest_latest.jsonl

License: WikEM CC BY-SA 3.0; site AI/ML terms restrict training/finetuning/eval.
Use for RAG retrieval only with attribution. See OPEN_CPG_DOWNLOADS.md § WikEM.
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
from wikem_common import (
    DISCOVERY_CATEGORIES,
    WIKEM_API,
    build_chunks_from_page,
    canonical_title,
    classify_section,
    is_english_canonical,
    is_index_hub_title,
    page_sections_from_api,
    page_url,
    sha256_text,
    slugify,
    syndrome_id,
)

API_DIR = ROOT / "data" / "cpg" / "api"
RAW_DIR = ROOT / "data" / "cpg" / "raw" / "wikem"
TEXT_DIR = ROOT / "data" / "cpg" / "text" / "wikem"
CHUNKS_OUT = ROOT / "data" / "cpg" / "processed" / "wikem_ddx_chunks.jsonl"
CANT_MISS_OUT = ROOT / "data" / "knowledge_raw" / "cant_miss_by_syndrome_wikem.json"
MANIFEST_LATEST = ROOT / "data" / "cpg" / "manifest_latest.jsonl"


def wikem_api(params: dict, timeout: int = 60) -> dict:
    params = dict(params)
    params["format"] = "json"
    url = WIKEM_API + "?" + urlencode(params)
    return fetch_json(url, timeout=timeout)


def list_category_members(category: str, *, sleep: float) -> list[dict]:
    rows: list[dict] = []
    cmcontinue: str | None = None
    while True:
        params: dict = {
            "action": "query",
            "list": "categorymembers",
            "cmtitle": category,
            "cmlimit": "500",
        }
        if cmcontinue:
            params["cmcontinue"] = cmcontinue
        data = wikem_api(params)
        batch = data.get("query", {}).get("categorymembers", [])
        rows.extend(batch)
        cmcontinue = data.get("continue", {}).get("cmcontinue")
        if not cmcontinue:
            break
        polite_sleep(sleep)
    return rows


def discover_categories(categories: list[str], *, sleep: float) -> list[dict]:
    """List category members; dedupe by canonical syndrome id (drop /en duplicates)."""
    index_rows: dict[str, dict] = {}
    for category in categories:
        members = list_category_members(category, sleep=sleep)
        for member in members:
            title = member.get("title") or ""
            if not title or not is_english_canonical(title):
                continue
            canonical = canonical_title(title)
            if is_index_hub_title(canonical):
                continue
            sid = syndrome_id(canonical)
            row = {
                "id": f"wikem_syndrome__{sid}",
                "source": "WikEM",
                "title": canonical,
                "url": page_url(canonical),
                "category": category.replace("Category:", ""),
                "pageid": member.get("pageid"),
                "entry_type": "syndrome_entry",
                "content_tier": "full_text",
                "license_note": "wikem_cc_by_sa_3.0",
                "syndrome_anchor": canonical,
                "discovery_source": category,
                "indexed_at_utc": datetime.now(timezone.utc).isoformat(),
                "_raw_title": title,
            }
            prev = index_rows.get(sid)
            if prev is None:
                index_rows[sid] = row
                continue
            # Prefer bare title over language-suffixed duplicate (e.g. "X" over "X/en").
            if "/" in prev["_raw_title"] and "/" not in title:
                index_rows[sid] = row
    out = []
    for row in index_rows.values():
        row.pop("_raw_title", None)
        out.append(row)
    return sorted(out, key=lambda r: r["title"].lower())


def parse_page(title: str, *, timeout: int) -> dict:
    return wikem_api(
        {
            "action": "parse",
            "page": title,
            "prop": "text|sections",
            "disablelimitreport": "1",
        },
        timeout=timeout,
    )


def merge_manifest(records: list[dict], run_id: str) -> Path:
    manifest_path = ROOT / "data" / "cpg" / f"manifest_{run_id}.jsonl"
    merged: dict[str, dict] = {}
    if MANIFEST_LATEST.exists():
        for line in MANIFEST_LATEST.read_text(encoding="utf-8").splitlines():
            if line.strip():
                prev = json.loads(line)
                merged[prev["id"]] = prev
    for record in records:
        merged[record["id"]] = record
    lines = "\n".join(json.dumps(v, ensure_ascii=False, sort_keys=True) for v in sorted(merged.values(), key=lambda x: x["id"])) + "\n"
    manifest_path.write_text(lines, encoding="utf-8")
    MANIFEST_LATEST.write_text(lines, encoding="utf-8")
    return manifest_path


def process_page(row: dict, *, timeout: int, skip_existing: bool) -> tuple[dict | None, list[dict], dict | None, str | None]:
    title = row["title"]
    source_id = row["id"]
    slug = slugify(title)
    raw_path = RAW_DIR / f"{slug}.html"
    text_path = TEXT_DIR / f"wikem-{slug}.txt"
    url = row["url"]

    if skip_existing and raw_path.exists() and text_path.exists():
        html = raw_path.read_text(encoding="utf-8")
        sections = json.loads((RAW_DIR / f"{slug}.sections.json").read_text(encoding="utf-8"))
    else:
        try:
            payload = parse_page(title, timeout=timeout)
        except Exception as exc:
            return None, [], None, repr(exc)
        parse = payload.get("parse") or {}
        if not parse:
            return None, [], None, "missing_parse"
        html = parse.get("text", {}).get("*") or ""
        sections = page_sections_from_api(parse.get("sections") or [], title)
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        raw_path.write_text(html, encoding="utf-8")
        (RAW_DIR / f"{slug}.sections.json").write_text(json.dumps(sections, ensure_ascii=False, indent=2), encoding="utf-8")

    full_text, chunks, cant_miss_links = build_chunks_from_page(
        page_title=title,
        html=html,
        sections=sections,
        source_id=source_id,
        url=url,
    )
    TEXT_DIR.mkdir(parents=True, exist_ok=True)
    text_path.write_text(full_text, encoding="utf-8")

    useful = sum(1 for c in chunks if c["chunk_type"] in {"differential", "red_flag", "evaluation"})
    manifest = {
        "id": source_id,
        "parent_id": "wikem_syndrome_index",
        "kind": "primary",
        "source": "WikEM",
        "title": title,
        "url": url,
        "clinical_area": ["wikem", "emergency_medicine", "syndrome_entry", "differential_diagnosis"],
        "access": "mediawiki_api",
        "status": "ok",
        "http_status": 200,
        "content_type": "text/html",
        "bytes": raw_path.stat().st_size,
        "sha256": sha256_text(html),
        "raw_path": str(raw_path.relative_to(ROOT)),
        "text_path": str(text_path.relative_to(ROOT)),
        "license_note": "wikem_cc_by_sa_3.0",
        "entry_type": "syndrome_entry",
        "content_tier": "full_text",
        "chunks": len(chunks),
        "useful_chunks": useful,
        "syndrome_anchor": title,
        "category": row.get("category"),
        "error": None,
    }
    cant_miss_row = {
        "id": syndrome_id(title),
        "title": title,
        "url": url,
        "cant_miss_entities": cant_miss_links,
        "differential_entities": [
            link
            for c in chunks
            if c["chunk_type"] == "differential"
            for link in c.get("wiki_links", [])
        ][:80],
        "useful_chunks": useful,
        "provenance": {
            "source": "WikEM",
            "category": row.get("category"),
            "license_note": "wikem_cc_by_sa_3.0",
            "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        },
    }
    if useful == 0:
        return manifest, chunks, cant_miss_row, "no_useful_chunks"
    return manifest, chunks, cant_miss_row, None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--discover-only", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--sleep", type=float, default=0.35)
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument(
        "--categories",
        nargs="*",
        default=DISCOVERY_CATEGORIES,
        help="MediaWiki categories to harvest (default: Category:Symptoms)",
    )
    args = parser.parse_args()

    print("Discovering WikEM pages …", flush=True)
    index_rows = discover_categories(args.categories, sleep=args.sleep)
    _, latest_index = merge_jsonl_latest(index_rows, API_DIR, "wikem_syndrome_index")
    print(f"Index: {len(index_rows)} pages → {latest_index.relative_to(ROOT)}", flush=True)
    if args.discover_only:
        print(json.dumps({"records": len(index_rows), "latest": str(latest_index.relative_to(ROOT))}, indent=2))
        return 0

    if args.limit > 0:
        index_rows = index_rows[: args.limit]

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    manifest_records: list[dict] = []
    all_chunks: list[dict] = []
    cant_miss_rows: list[dict] = []
    errors: list[dict] = []
    warnings: list[dict] = []

    for i, row in enumerate(index_rows, 1):
        print(f"[{i}/{len(index_rows)}] {row['title']}", flush=True)
        manifest, chunks, cant_miss, err = process_page(row, timeout=args.timeout, skip_existing=args.skip_existing)
        if err == "no_useful_chunks" and manifest:
            warnings.append({"id": row["id"], "title": row["title"], "warning": err})
            manifest_records.append(manifest)
            cant_miss_rows.append(cant_miss)
            print(f"  warn: {err} ({len(chunks)} chunks)", flush=True)
        elif err:
            errors.append({"id": row["id"], "title": row["title"], "error": err})
            print(f"  skip: {err}", flush=True)
        else:
            manifest_records.append(manifest)
            all_chunks.extend(chunks)
            cant_miss_rows.append(cant_miss)
            print(f"  ok: {len(chunks)} chunks, {manifest['useful_chunks']} useful", flush=True)
        if i < len(index_rows):
            polite_sleep(args.sleep)

    CHUNKS_OUT.parent.mkdir(parents=True, exist_ok=True)
    existing_chunks: dict[str, dict] = {}
    if args.skip_existing and CHUNKS_OUT.exists():
        with CHUNKS_OUT.open(encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    c = json.loads(line)
                    existing_chunks[c["id"]] = c
    for chunk in all_chunks:
        existing_chunks[chunk["id"]] = chunk
    with CHUNKS_OUT.open("w", encoding="utf-8") as f:
        for chunk in sorted(existing_chunks.values(), key=lambda x: x["id"]):
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

    CANT_MISS_OUT.parent.mkdir(parents=True, exist_ok=True)
    cant_miss_payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "license_note": "CC BY-SA 3.0 (WikEM); attribution required; not for model training/finetuning/eval per site AI/ML terms",
        "source": "WikEM MediaWiki API",
        "discovery_categories": args.categories,
        "syndromes": sorted(cant_miss_rows, key=lambda x: x["title"].lower()),
    }
    CANT_MISS_OUT.write_text(json.dumps(cant_miss_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    manifest_path = merge_manifest(manifest_records, run_id) if manifest_records else None
    summary = {
        "run_id": run_id,
        "index_records": len(index_rows),
        "ok": len(manifest_records),
        "errors": len(errors),
        "warnings": len(warnings),
        "chunks_written": len(existing_chunks),
        "chunks_out": str(CHUNKS_OUT.relative_to(ROOT)),
        "cant_miss_out": str(CANT_MISS_OUT.relative_to(ROOT)),
        "manifest_run": str(manifest_path.relative_to(ROOT)) if manifest_path else None,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    if errors[:5]:
        summary["error_samples"] = errors[:5]
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if manifest_records else 1


if __name__ == "__main__":
    sys.exit(main())
