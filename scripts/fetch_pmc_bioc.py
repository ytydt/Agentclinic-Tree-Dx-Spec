#!/usr/bin/env python3
"""Fetch PMC-OA full text via BioC API and emit DDx-focused chunks.

Reads: data/cpg/api/pmc_oa_ddx_index_latest.jsonl
Writes:
  - data/cpg/raw/pmc_oa/bioc-{pmcid}.json
  - data/cpg/text/pmc_oa/pmc-oa-ddx-{pmcid}.txt
  - data/cpg/processed/pmc_oa_ddx_chunks.jsonl
  - merges data/cpg/manifest_latest.jsonl (article-level rows)

BioC API: https://www.ncbi.nlm.nih.gov/research/bionlp/APIs/BioC-PMC/
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cpg_api_common import ROOT, fetch_bytes, fetch_json, polite_sleep
from pmc_oa_ddx_common import (
    normalize_pmcid,
    parse_bioc_collection,
    passages_to_chunks,
    sha256_bytes,
    slugify,
)

DEFAULT_INDEX = ROOT / "data" / "cpg" / "api" / "pmc_oa_ddx_index_latest.jsonl"
RAW_DIR = ROOT / "data" / "cpg" / "raw" / "pmc_oa"
TEXT_DIR = ROOT / "data" / "cpg" / "text" / "pmc_oa"
CHUNKS_OUT = ROOT / "data" / "cpg" / "processed" / "pmc_oa_ddx_chunks.jsonl"
MANIFEST_LATEST = ROOT / "data" / "cpg" / "manifest_latest.jsonl"
BIOC_URL = "https://www.ncbi.nlm.nih.gov/research/bionlp/RESTful/pmcoa.cgi/BioC_json/{pmcid}/unicode"


def load_index(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def fetch_bioc(pmcid: str, timeout: int) -> bytes:
    url = BIOC_URL.format(pmcid=pmcid)
    return fetch_bytes(url, timeout=timeout)


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
    merged_rows = sorted(merged.values(), key=lambda r: r.get("id", ""))
    lines = "\n".join(json.dumps(v, ensure_ascii=False, sort_keys=True) for v in merged_rows) + "\n"
    manifest_path.write_text(lines, encoding="utf-8")
    MANIFEST_LATEST.write_text(lines, encoding="utf-8")
    return manifest_path


def process_article(row: dict, *, timeout: int, skip_existing: bool) -> tuple[dict | None, list[dict], str | None]:
    pmcid = normalize_pmcid(row.get("pmcid"))
    if not pmcid:
        return None, [], "missing_pmcid"
    if not row.get("has_pmc_fulltext") and not row.get("is_open_access"):
        return None, [], "not_oa_fulltext"

    source_id = row.get("id") or f"pmc_oa_ddx__{pmcid.lower()}"
    slug = slugify(pmcid)
    raw_path = RAW_DIR / f"bioc-{slug}.json"
    text_path = TEXT_DIR / f"pmc-oa-ddx-{slug}.txt"

    if skip_existing and raw_path.exists() and text_path.exists():
        payload = json.loads(raw_path.read_text(encoding="utf-8"))
    else:
        try:
            payload_bytes = fetch_bioc(pmcid, timeout=timeout)
            payload = json.loads(payload_bytes.decode("utf-8", errors="replace"))
        except HTTPError as exc:
            return None, [], f"http_{exc.code}"
        except Exception as exc:
            return None, [], repr(exc)
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        raw_path.write_bytes(json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"))

    doc_meta, passages = parse_bioc_collection(payload)
    if not passages:
        return None, [], "empty_bioc"

    license_note = doc_meta.get("license") or row.get("license") or "pmc_oa"
    title = row.get("title") or doc_meta.get("article-id_pmid") or pmcid
    syndrome_kw = row.get("syndrome_keywords") or []
    syndrome_anchor = syndrome_kw[0] if syndrome_kw else None
    full_text, chunks = passages_to_chunks(
        passages,
        source_id=source_id,
        title=title,
        pmcid=pmcid,
        pmid=row.get("pmid"),
        license_note=f"pmc_oa:{license_note}",
        url=row.get("url"),
        syndrome_anchor=syndrome_anchor,
    )

    TEXT_DIR.mkdir(parents=True, exist_ok=True)
    text_path.write_text(full_text, encoding="utf-8")

    manifest = {
        "id": source_id,
        "parent_id": "pmc_oa_ddx_index",
        "kind": "primary",
        "source": "PMC-OA",
        "title": title,
        "url": row.get("url"),
        "clinical_area": ["pmc_oa", "syndrome_entry", "differential_diagnosis"],
        "access": "pmc_bioc_oa",
        "status": "ok",
        "http_status": 200,
        "content_type": "application/json",
        "bytes": raw_path.stat().st_size,
        "sha256": sha256_bytes(raw_path.read_bytes()),
        "raw_path": str(raw_path.relative_to(ROOT)),
        "text_path": str(text_path.relative_to(ROOT)),
        "pmcid": pmcid,
        "pmid": row.get("pmid"),
        "license_note": f"pmc_oa:{license_note}",
        "entry_type": "syndrome_entry",
        "content_tier": "full_text",
        "chunks": len(chunks),
        "syndrome_keywords": row.get("syndrome_keywords") or [],
        "error": None,
    }
    return manifest, chunks, None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--limit", type=int, default=0, help="max articles to fetch (0=all eligible)")
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--sleep", type=float, default=0.35)
    parser.add_argument("--skip-existing", action="store_true")
    args = parser.parse_args()

    if not args.index.exists():
        print(f"Index not found: {args.index}. Run build_pmc_oa_ddx_index.py first.", file=sys.stderr)
        return 1

    rows = load_index(args.index)
    eligible = [r for r in rows if normalize_pmcid(r.get("pmcid"))]
    if args.limit > 0:
        eligible = eligible[: args.limit]

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    manifest_records: list[dict] = []
    all_chunks: list[dict] = []
    errors: list[dict] = []

    for i, row in enumerate(eligible, 1):
        pmcid = normalize_pmcid(row.get("pmcid"))
        print(f"[{i}/{len(eligible)}] {pmcid} {row.get('title', '')[:70]}…", flush=True)
        manifest, chunks, err = process_article(row, timeout=args.timeout, skip_existing=args.skip_existing)
        if err:
            errors.append({"pmcid": pmcid, "id": row.get("id"), "error": err})
            print(f"  skip: {err}", flush=True)
        else:
            manifest_records.append(manifest)
            all_chunks.extend(chunks)
            print(f"  ok: {len(chunks)} chunks, {manifest['bytes']} bytes bioc", flush=True)
        if i < len(eligible):
            polite_sleep(args.sleep)

    CHUNKS_OUT.parent.mkdir(parents=True, exist_ok=True)
    existing_chunks: dict[str, dict] = {}
    if args.skip_existing and CHUNKS_OUT.exists():
        for line in CHUNKS_OUT.read_text(encoding="utf-8").splitlines():
            if line.strip():
                c = json.loads(line)
                existing_chunks[c["id"]] = c
    for chunk in all_chunks:
        existing_chunks[chunk["id"]] = chunk
    with CHUNKS_OUT.open("w", encoding="utf-8") as f:
        for chunk in sorted(existing_chunks.values(), key=lambda x: x["id"]):
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

    manifest_path = merge_manifest(manifest_records, run_id) if manifest_records else None
    summary = {
        "run_id": run_id,
        "index": str(args.index.relative_to(ROOT)),
        "eligible": len(eligible),
        "ok": len(manifest_records),
        "errors": len(errors),
        "chunks_written": len(existing_chunks),
        "chunks_out": str(CHUNKS_OUT.relative_to(ROOT)),
        "manifest_run": str(manifest_path.relative_to(ROOT)) if manifest_path else None,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    if errors[:5]:
        summary["error_samples"] = errors[:5]
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not errors or manifest_records else 2


if __name__ == "__main__":
    sys.exit(main())
