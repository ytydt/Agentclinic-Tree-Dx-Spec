#!/usr/bin/env python3
"""Parse MedlinePlus bulk topics XML into structured JSONL chunks.

Input: data/poc/medlineplus/raw/mplus_topics_*.xml (latest)
Output: data/poc/medlineplus/processed/medlineplus_topic_chunks_latest.jsonl

Attribution: Information from MedlinePlus.gov
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cpg_api_common import ROOT, merge_jsonl_latest

DEFAULT_RAW = ROOT / "data" / "poc" / "medlineplus" / "raw"
DEFAULT_OUT = ROOT / "data" / "poc" / "medlineplus" / "processed"


def strip_html(text: str) -> str:
    text = html.unescape(text or "")
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def latest_topics_xml(raw_dir: Path) -> Path:
    candidates = sorted(raw_dir.glob("mplus_topics_*.xml"))
    if not candidates:
        raise FileNotFoundError(f"no mplus_topics_*.xml under {raw_dir}")
    return candidates[-1]


def parse_topics(path: Path) -> list[dict]:
    tree = ET.parse(path)
    root = tree.getroot()
    rows: list[dict] = []
    for topic in root.findall("health-topic"):
        topic_id = topic.get("id", "")
        title = topic.get("title", "")
        url = topic.get("url", "")
        also_called = [el.text.strip() for el in topic.findall("also-called") if el.text]
        summary_el = topic.find("full-summary")
        summary_html = summary_el.text if summary_el is not None and summary_el.text else ""
        summary_text = strip_html(summary_html)
        if not summary_text:
            continue
        rows.append(
            {
                "source": "MedlinePlus",
                "id": f"medlineplus_topic_{topic_id}",
                "topic_id": topic_id,
                "title": title,
                "url": url,
                "also_called": also_called,
                "text": summary_text,
                "attribution": "Information from MedlinePlus.gov",
                "license_note": "NLM MedlinePlus open XML; attribution required",
                "parsed_at_utc": datetime.now(timezone.utc).isoformat(),
            }
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--xml", type=Path, default=None)
    args = parser.parse_args()

    xml_path = args.xml or latest_topics_xml(args.raw_dir)
    rows = parse_topics(xml_path)
    manifest, latest = merge_jsonl_latest(rows, args.out, "medlineplus_topic_chunks")
    summary = {
        "xml_path": str(xml_path.relative_to(ROOT)),
        "records": len(rows),
        "manifest": str(manifest.relative_to(ROOT)),
        "latest": str(latest.relative_to(ROOT)),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
