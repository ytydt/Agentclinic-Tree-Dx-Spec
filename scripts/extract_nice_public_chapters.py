#!/usr/bin/env python3
"""Expand NICE public HTML recommendation chapters (no API-Key required).

Writes ``data/cpg/open_cpg_nice_public_seed.json`` from a curated list of
official chapter URLs (no network probe — run ``download_open_cpg.py`` to fetch).

Syndication bulk (full catalogue) remains in ``fetch_nice_syndication_index.py``
once ``NICE_API_KEY`` is active.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "cpg" / "open_cpg_nice_public_seed.json"

# Curated high-value chapters (verified public HTML; extend after syndication index)
CURATED: list[tuple[str, str, str]] = [
    ("ng12", "Suspected cancer", "Recommendations-organised-by-site-of-cancer"),
    ("ng51", "Sepsis", "Recommendations"),
    ("ng128", "Stroke", "Recommendations"),
    ("ng138", "Pneumonia", "Recommendations"),
    ("ng194", "Glaucoma", "Recommendations"),
    ("ng235", "Heart valve disease", "Recommendations"),
    ("cg95", "Chest pain of recent onset", "Recommendations"),
    ("cg150", "Headaches", "Recommendations"),
    ("cg177", "Osteoarthritis", "Recommendations"),
    ("cg182", "Dementia", "Recommendations"),
    ("ng28", "Type 2 diabetes", "Recommendations"),
    ("ng136", "Hypertension", "Recommendations"),
    ("ng18", "Diabetes (type 1 and 2)", "Recommendations"),
    ("ng145", "Chronic kidney disease", "Recommendations"),
    ("ng59", "Chronic heart failure", "Recommendations"),
    ("ng74", "Intrapartum care", "Recommendations"),
    ("ng84", "Asthma", "Recommendations"),
    ("ng109", "Chronic heart failure (update)", "Recommendations"),
    ("ng130", "Depression in adults", "Recommendations"),
    ("ng157", "Acute coronary syndromes", "Recommendations"),
    ("ng163", "Jaundice in newborn", "Recommendations"),
    ("ng167", "Renal and ureteric stones", "Recommendations"),
    ("ng193", "Heavy menstrual bleeding", "Recommendations"),
    ("qs93", "Sepsis quality standard", "Quality-statements"),
    ("qs181", "Asthma quality standard", "Quality-statements"),
]


def slugify(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "chapter"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()

    items: list[dict] = []
    seen: set[str] = set()
    for code, title_hint, chapter in CURATED:
        code_l = code.lower()
        parent = f"nice_guidance_{code_l}"
        landing = f"https://www.nice.org.uk/guidance/{code_l}"
        if landing not in seen:
            seen.add(landing)
            items.append(
                {
                    "id": f"nice_pub__{code_l}",
                    "parent_id": parent,
                    "source": "NICE",
                    "title": f"NICE {code.upper()}: {title_hint} (landing)",
                    "url": landing,
                    "clinical_area": ["nice", "guideline"],
                    "access": "public_html",
                    "license_note": "NICE UK Open Content Licence; verify attribution.",
                }
            )
        url = f"https://www.nice.org.uk/guidance/{code_l}/chapter/{chapter}"
        if url in seen:
            continue
        seen.add(url)
        items.append(
            {
                "id": f"nice_pub__{code_l}__{slugify(chapter)}"[:120],
                "parent_id": parent,
                "source": "NICE",
                "title": f"NICE {code.upper()}: {title_hint} — {chapter.replace('-', ' ')}",
                "url": url,
                "clinical_area": ["nice", "guideline"],
                "access": "public_html",
                "license_note": "NICE UK Open Content Licence; verify attribution.",
            }
        )

    items.sort(key=lambda x: x["id"])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "out": str(args.out),
                "entries": len(items),
                "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
