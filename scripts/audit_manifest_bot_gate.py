#!/usr/bin/env python3
"""Audit manifest mirrors for NCBI/PubMed browser-check interstitial pages.

Scans data/cpg/manifest_latest.jsonl text_path / raw_path for bot-gate HTML
saved during batch download (``Checking your browser before accessing pubmed…``).

Output: data/cpg/eval/manifest_bot_gate_report.json

Optional:
  --annotate-manifest  write ``download_quality: bot_blocked`` on affected rows
                       to manifest_latest.jsonl (creates .bak backup first)
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cpg_api_common import ROOT
from cpg_manifest_common import iter_manifest_rows, manifest_has_bot_gate

DEFAULT_MANIFEST = ROOT / "data" / "cpg" / "manifest_latest.jsonl"
DEFAULT_REPORT = ROOT / "data" / "cpg" / "eval" / "manifest_bot_gate_report.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument(
        "--annotate-manifest",
        action="store_true",
        help="set download_quality=bot_blocked on affected manifest rows",
    )
    args = parser.parse_args()

    if not args.manifest.exists():
        print(f"Manifest not found: {args.manifest}", file=sys.stderr)
        return 1

    by_source = Counter()
    by_prefix = Counter()
    by_access = Counter()
    blocked: list[dict] = []
    total_ok_with_file = 0

    rows_out: list[dict] = []
    for row in iter_manifest_rows(args.manifest):
        rec = dict(row)
        if row.get("status") == "ok" and (row.get("text_path") or row.get("raw_path")):
            tp = row.get("text_path")
            rp = row.get("raw_path")
            has_file = (tp and (ROOT / tp).exists()) or (rp and (ROOT / rp).exists())
            if has_file:
                total_ok_with_file += 1
                if manifest_has_bot_gate(row, ROOT):
                    mid = row.get("id", "")
                    prefix = mid.split("__")[0] if "__" in mid else mid.split("_")[0]
                    src = row.get("source") or "unknown"
                    access = row.get("access") or "unknown"
                    by_source[src] += 1
                    by_prefix[prefix] += 1
                    by_access[access] += 1
                    blocked.append(
                        {
                            "id": mid,
                            "source": src,
                            "prefix": prefix,
                            "access": access,
                            "url": row.get("url"),
                            "text_path": tp,
                        }
                    )
                    if args.annotate_manifest:
                        rec["download_quality"] = "bot_blocked"
        rows_out.append(rec)

    report = {
        "manifest": str(args.manifest.relative_to(ROOT)),
        "total_ok_with_file": total_ok_with_file,
        "bot_blocked": len(blocked),
        "bot_blocked_pct": round(100 * len(blocked) / total_ok_with_file, 3) if total_ok_with_file else 0,
        "by_source": dict(by_source.most_common()),
        "by_prefix": dict(by_prefix.most_common()),
        "by_access": dict(by_access.most_common()),
        "entries": blocked,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if args.annotate_manifest and blocked:
        bak = args.manifest.with_suffix(args.manifest.suffix + ".bak")
        shutil.copy2(args.manifest, bak)
        with args.manifest.open("w", encoding="utf-8") as f:
            for rec in rows_out:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        report["manifest_backup"] = str(bak.relative_to(ROOT))

    print(json.dumps({k: report[k] for k in report if k != "entries"}, ensure_ascii=False, indent=2))
    print(f"Full entry list: {args.report.relative_to(ROOT)} ({len(blocked)} rows)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
