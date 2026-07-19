#!/usr/bin/env python3
"""Download NCCN guidelines only when an official API AccessKey is licensed.

Personal NCCN.org login credentials must NOT be used for bulk mirroring.
Set NCCN_API_ACCESS_KEY in the environment after obtaining authorization from
NCCN (https://www.nccn.org/developer-api).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "data" / "cpg" / "restricted" / "nccn"
API_BASE = "https://www.nccn.org/webservices/Products/api/Guideline/GetAllPublishedGuidelines"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--access-key",
        default=os.environ.get("NCCN_API_ACCESS_KEY"),
        help="NCCN API AccessKey (prefer env NCCN_API_ACCESS_KEY)",
    )
    args = parser.parse_args()

    if not args.access_key:
        print(
            "NCCN bulk download requires an official API AccessKey, not a website login.\n"
            "Request licensing/API access at https://www.nccn.org/developer-api and export\n"
            "NCCN_API_ACCESS_KEY before running this script.",
            file=sys.stderr,
        )
        return 2

    url = f"{API_BASE}/{args.access_key}"
    req = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "Agentclinic-NCCN-licensed/0.1"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            payload = resp.read()
    except urllib.error.HTTPError as exc:
        print(f"NCCN API request failed: {exc}", file=sys.stderr)
        return 3

    args.out.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    raw_path = args.out / f"guidelines_{run_id}.json"
    raw_path.write_bytes(payload)
    meta = {
        "run_id": run_id,
        "source": "NCCN API",
        "endpoint": API_BASE,
        "license_note": "Restricted; requires NCCN API contract and IP allowlist.",
        "bytes": len(payload),
        "raw_path": str(raw_path.relative_to(ROOT)),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    (args.out / f"summary_{run_id}.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
