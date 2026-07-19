#!/usr/bin/env python3
"""Build ESMO clinical guideline seed entries from the public Nuxt sitemap.

ESMO guidelines are SPA-rendered; the sitemap exposes stable canonical URLs.
Output: data/cpg/open_cpg_api_seed.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cpg_api_common import ROOT, fetch_text

DEFAULT_OUT = ROOT / "data" / "cpg" / "open_cpg_api_seed.json"
SITEMAP_URL = "https://www.esmo.org/__sitemap__/en.xml"
SKIP_PARTS = ("esmo-mcbs", "pocket", "mobile-app", "translated", "guidelines-news", "guidelines-slide-sets")


def slugify(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "untitled"


def title_from_url(url: str) -> str:
    slug = url.rstrip("/").rsplit("/", 1)[-1]
    return slug.replace("-", " ").title()


def extract_esmo_urls(xml_text: str) -> list[str]:
    urls = [m.group(1) for m in re.finditer(r"<loc>(https://www\.esmo\.org/guidelines/[^<]+)</loc>", xml_text)]
    good: list[str] = []
    for url in urls:
        if url.rstrip("/") == "https://www.esmo.org/guidelines":
            continue
        if any(part in url for part in SKIP_PARTS):
            continue
        good.append(url)
    return sorted(set(good))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    xml_text = fetch_text(SITEMAP_URL, timeout=90)
    urls = extract_esmo_urls(xml_text)
    items = []
    for url in urls:
        slug = slugify(url.replace("https://www.esmo.org/guidelines/", ""))
        items.append(
            {
                "id": f"esmo_api__{slug[:90]}",
                "parent_id": "esmo_guidelines_index",
                "source": "ESMO",
                "title": f"ESMO Guideline: {title_from_url(url)}",
                "url": url,
                "clinical_area": ["oncology"],
                "access": "public_html",
            }
        )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "out": str(args.out),
                "sitemap": SITEMAP_URL,
                "entries": len(items),
                "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
