#!/usr/bin/env python3
"""Build NICE CPG seed entries from ``nice_syndication_index_latest.jsonl``.

Reads the syndication index produced by ``fetch_nice_syndication_index.py`` and
writes ``data/cpg/open_cpg_nice_seed.json`` for merge into ``open_cpg_seed.json``.

Only rows with a usable ``webUrl`` / ``url`` are emitted. Chapter-level resources
are kept when they look like recommendation / evaluation sections.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cpg_api_common import ROOT

DEFAULT_INDEX = ROOT / "data" / "cpg" / "api" / "nice_syndication_index_latest.jsonl"
DEFAULT_OUT = ROOT / "data" / "cpg" / "open_cpg_nice_seed.json"

_CHAPTER_HINT = re.compile(
    r"recommendation|evaluation|diagnosis|differential|overview|management|"
    r"investigation|referral|summary",
    re.I,
)
_GUIDANCE_CODE = re.compile(r"/guidance/((?:ng|cg|ta|qs|ipg|dg|mtg|sc)\d+)", re.I)


def slugify(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "untitled"


def load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if isinstance(row, dict):
                rows.append(row)
    return rows


def clinical_area_from_url(url: str, title: str) -> list[str]:
    blob = f"{url} {title}".lower()
    areas: list[str] = ["nice", "guideline"]
    mapping = [
        (["cancer", "oncolog", "ng12", "suspected cancer"], "oncology"),
        (["sepsis", "ng51"], "critical care"),
        (["stroke", "ng128"], "neurology"),
        (["chest pain", "cg95"], "cardiology"),
        (["pneumonia", "ng138", "respiratory"], "pulmonary"),
        (["headache", "cg150"], "neurology"),
        (["diabetes", "ng28"], "endocrine"),
        (["hypertension", "ng136"], "cardiology"),
        (["heart failure"], "cardiology"),
        (["mental", "depression", "psych"], "psychiatry"),
        (["maternity", "pregnancy", "intrapartum"], "obstetrics"),
        (["child", "paediatric", "pediatric"], "pediatrics"),
    ]
    for keys, area in mapping:
        if any(k in blob for k in keys):
            areas.append(area)
    return sorted(set(areas))


def should_include(row: dict, *, chapters_only: bool) -> bool:
    url = (row.get("url") or row.get("webUrl") or "").strip()
    if not url or "nice.org.uk" not in url:
        return False
    title = (row.get("title") or "").strip()
    if chapters_only:
        if "/chapter/" not in url.lower():
            return False
        return bool(_CHAPTER_HINT.search(f"{url} {title}"))
    # Top-level guidance pages + high-value chapters
    if "/chapter/" in url.lower():
        return bool(_CHAPTER_HINT.search(f"{url} {title}"))
    return bool(_GUIDANCE_CODE.search(url))


def row_to_seed(row: dict, idx: int) -> dict | None:
    url = (row.get("url") or row.get("webUrl") or "").strip()
    title = (row.get("title") or "NICE guidance").strip()
    if not url:
        return None
    m = _GUIDANCE_CODE.search(url)
    code = m.group(1).lower() if m else slugify(title)[:40]
    chapter = ""
    if "/chapter/" in url.lower():
        chapter = slugify(url.rsplit("/chapter/", 1)[-1])[:50]
    sid = f"nice_api__{code}"
    if chapter:
        sid = f"{sid}__{chapter}"[:120]
    elif row.get("nice_id"):
        sid = f"nice_api__{slugify(str(row['nice_id']))[:80]}"
    else:
        sid = f"nice_api__{slugify(title)[:80]}"
    sid = re.sub(r"-+", "-", sid).strip("-")
    parent = f"nice_guidance_{code}" if m else "nice_syndication_index"
    return {
        "id": sid if sid != f"nice_api__" else f"nice_api__item-{idx}",
        "parent_id": parent,
        "source": "NICE",
        "title": title[:500],
        "url": url,
        "clinical_area": clinical_area_from_url(url, title),
        "access": "nice_syndication_api",
        "license_note": "NICE syndication licence; API-Key required; do not redistribute outside licence terms.",
        "nice_id": row.get("nice_id"),
        "resource_type": row.get("type"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--chapters-only",
        action="store_true",
        help="Only emit chapter URLs (recommendations / evaluation / etc.)",
    )
    args = parser.parse_args()

    if not args.index.exists():
        print(json.dumps({"error": f"index not found: {args.index}"}), file=sys.stderr)
        return 2

    rows = load_jsonl(args.index)
    seen_urls: set[str] = set()
    items: list[dict] = []
    for i, row in enumerate(rows):
        if not should_include(row, chapters_only=args.chapters_only):
            continue
        url = (row.get("url") or row.get("webUrl") or "").strip().rstrip("/")
        if url in seen_urls:
            continue
        seen_urls.add(url)
        item = row_to_seed(row, i)
        if item:
            items.append(item)

    items.sort(key=lambda x: x["id"])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "index": str(args.index),
                "out": str(args.out),
                "index_rows": len(rows),
                "seed_entries": len(items),
                "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
