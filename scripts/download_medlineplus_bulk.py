#!/usr/bin/env python3
"""Download official MedlinePlus bulk XML (health topics + topic groups).

Source: https://medlineplus.gov/xml.html (NLM open data; attribution required).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "data" / "poc" / "medlineplus"
INDEX_URL = "https://medlineplus.gov/xml.html"
USER_AGENT = "Agentclinic-Tree-Dx-Spec medlineplus-downloader/0.1"


def latest_links(html: str) -> dict[str, str]:
    links: dict[str, str] = {}
    dated = sorted(set(re.findall(r"https://medlineplus.gov/xml/mplus_[^\"']+\.(?:xml|zip)", html)))
    if not dated:
        raise RuntimeError("no MedlinePlus XML links found on index page")
    # pick newest date from compressed topics zip
    compressed = [u for u in dated if "topics_compressed" in u]
    topics = [u for u in dated if u.endswith(".xml") and "topic_groups" not in u and "topics_" in u]
    groups = [u for u in dated if "topic_groups" in u]
    links["topics_compressed"] = compressed[0]
    links["topics_xml"] = topics[0] if topics else ""
    links["topic_groups_xml"] = groups[0] if groups else ""
    return links


def fetch(url: str, dest: Path, timeout: int) -> dict:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=timeout) as resp:
        payload = resp.read()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(payload)
    return {
        "url": url,
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "content_type": resp.headers.get("Content-Type"),
        "path": str(dest.relative_to(ROOT)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()

    out_dir = args.out.resolve()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    index_html = urlopen(Request(INDEX_URL, headers={"User-Agent": USER_AGENT}), timeout=args.timeout).read().decode("utf-8", errors="replace")
    links = latest_links(index_html)

    records = []
    mapping = {
        "topics_compressed": out_dir / "raw" / f"mplus_topics_compressed_{run_id}.zip",
        "topics_xml": out_dir / "raw" / f"mplus_topics_{run_id}.xml",
        "topic_groups_xml": out_dir / "raw" / f"mplus_topic_groups_{run_id}.xml",
    }
    for key, dest in mapping.items():
        url = links.get(key)
        if not url:
            continue
        print(f"Downloading {key} from {url}", flush=True)
        records.append({"id": key, **fetch(url, dest, args.timeout)})
        time.sleep(0.5)

    manifest = out_dir / f"manifest_{run_id}.jsonl"
    latest = out_dir / "manifest_latest.jsonl"
    with manifest.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    latest.write_text(manifest.read_text(encoding="utf-8"), encoding="utf-8")

    summary = {
        "run_id": run_id,
        "source": "MedlinePlus NLM XML",
        "index_url": INDEX_URL,
        "records": len(records),
        "attribution": "Information from MedlinePlus.gov",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    (out_dir / f"summary_{run_id}.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
