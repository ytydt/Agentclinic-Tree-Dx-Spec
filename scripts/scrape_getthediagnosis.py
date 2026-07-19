#!/usr/bin/env python3
"""Scrape GetTheDiagnosis.org to build lr_cache.json.

Fetches all diagnosis pages, parses sensitivity/specificity/LR data,
and writes a structured JSON cache file.

Usage:
    python scripts/scrape_getthediagnosis.py [--output data/knowledge_raw/lr_cache.json]
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import time
from pathlib import Path
from urllib.parse import urljoin

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    raise SystemExit(
        "Required packages: pip install requests beautifulsoup4 lxml"
    )

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

BASE_URL = "https://getthediagnosis.org/"
BROWSE_URL = "https://getthediagnosis.org/browse.php?mode=dx"


def get_all_diagnosis_links(session: requests.Session) -> list[str]:
    """Fetch the browse-by-diagnosis page and extract all diagnosis links."""
    resp = session.get(BROWSE_URL, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "diagnosis/" in href and href.endswith(".htm"):
            full = urljoin(BASE_URL, href)
            if full not in links:
                links.append(full)
    logger.info("Found %d diagnosis pages", len(links))
    return links


def parse_diagnosis_page(session: requests.Session, url: str) -> list[dict]:
    """Parse a single diagnosis page for all finding entries."""
    entries = []
    try:
        resp = session.get(url, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        logger.warning("Failed to fetch %s: %s", url, e)
        return entries

    soup = BeautifulSoup(resp.text, "lxml")

    # Extract disease name from the heading
    h1 = soup.find("h1")
    if not h1:
        return entries
    disease_name = h1.get_text(strip=True)
    disease_name = re.sub(r"^Get The Diagnosis:\s*", "", disease_name, flags=re.IGNORECASE)

    # Each finding is in a table row with sensitivity/specificity
    tables = soup.find_all("table")
    for table in tables:
        rows = table.find_all("tr")
        header_cells = []
        if rows:
            header_cells = [th.get_text(strip=True).lower() for th in rows[0].find_all(["th", "td"])]

        sn_col = sp_col = finding_col = None
        for i, h in enumerate(header_cells):
            if "sensitivity" in h or "sens" in h:
                sn_col = i
            elif "specificity" in h or "spec" in h:
                sp_col = i
            elif "finding" in h or "test" in h or "sign" in h or "symptom" in h:
                finding_col = i

        if sn_col is None or sp_col is None:
            continue

        for row in rows[1:]:
            cells = row.find_all(["td", "th"])
            if len(cells) <= max(sn_col, sp_col):
                continue

            finding = ""
            if finding_col is not None and finding_col < len(cells):
                finding = cells[finding_col].get_text(strip=True)
            elif cells:
                finding = cells[0].get_text(strip=True)

            try:
                sn_text = cells[sn_col].get_text(strip=True).replace("%", "")
                sp_text = cells[sp_col].get_text(strip=True).replace("%", "")
                sn = float(sn_text)
                sp = float(sp_text)
                if sn > 1:
                    sn /= 100
                if sp > 1:
                    sp /= 100
            except (ValueError, IndexError):
                continue

            if not (0 <= sn <= 1 and 0 <= sp <= 1):
                continue

            lr_pos = sn / (1 - sp) if sp < 1.0 else None
            lr_neg = (1 - sn) / sp if sp > 0 else None

            entries.append({
                "finding": finding,
                "disease": disease_name,
                "sensitivity": round(sn, 4),
                "specificity": round(sp, 4),
                "lr_positive": round(lr_pos, 4) if lr_pos is not None else None,
                "lr_negative": round(lr_neg, 4) if lr_neg is not None else None,
                "source": "GetTheDiagnosis.org",
                "reference": url,
            })

    return entries


def main():
    parser = argparse.ArgumentParser(description="Scrape GetTheDiagnosis.org for LR data")
    parser.add_argument(
        "--output", "-o",
        default="data/knowledge_raw/lr_cache.json",
        help="Output path for lr_cache.json",
    )
    parser.add_argument(
        "--delay", type=float, default=1.0,
        help="Delay between requests in seconds",
    )
    args = parser.parse_args()

    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    session = requests.Session()
    session.verify = False
    session.headers["User-Agent"] = (
        "Mozilla/5.0 (compatible; AgentClinic-TreeDx-Spec/1.0; research-only)"
    )
    session.proxies = {
        "http": "http://127.0.0.1:7890",
        "https": "http://127.0.0.1:7890",
    }

    links = get_all_diagnosis_links(session)

    cache = {}
    total_entries = 0
    for i, url in enumerate(links):
        entries = parse_diagnosis_page(session, url)
        for entry in entries:
            key = f"{entry['finding'].strip().lower()}::{entry['disease'].strip().lower()}"
            cache[key] = entry
            total_entries += 1
        if (i + 1) % 50 == 0:
            logger.info("Progress: %d/%d pages, %d entries", i + 1, len(links), total_entries)
        time.sleep(args.delay)

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)

    logger.info("Done: %d entries from %d pages → %s", total_entries, len(links), out)


if __name__ == "__main__":
    main()
