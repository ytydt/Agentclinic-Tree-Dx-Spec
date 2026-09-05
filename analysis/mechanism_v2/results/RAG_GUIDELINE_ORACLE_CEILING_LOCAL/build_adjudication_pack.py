#!/usr/bin/env python3
"""Assemble the human-readable D0-D3 adjudication pack.

Evidence comes from two views produced earlier:

* the best-scoring served-size chunks per source (`expanded_oracle_scan_48`);
* the best un-sliced window per source (`unsliced_window_capacity_48`).

Case-report hits are printed under an explicit contamination header and are
never eligible as guideline evidence.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
LEDGER_DIR = ROOT / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"
UPSTREAM_LEDGER = ROOT / "RAG_GUIDELINE_SOURCE_CAPACITY_AUDIT"

GUIDELINE_SOURCES = ["merck", "manifest_cpg", "wikem", "pmc_oa", "statpearls", "textbooks"]
SNIPPET = 1100


def squash(text: str, limit: int = SNIPPET) -> str:
    return re.sub(r"\s+", " ", text or "").strip()[:limit]


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=LEDGER_DIR / "adjudication_pack.md")
    parser.add_argument("--only", default="", help="comma-separated upstream grades, e.g. D0,D1")
    args = parser.parse_args()

    scan = {r["case_key"]: r for r in read_jsonl(LEDGER_DIR / "expanded_oracle_scan_48.jsonl")}
    unsliced = {
        r["case_key"]: r for r in read_jsonl(LEDGER_DIR / "unsliced_window_capacity_48.jsonl")
    }
    upstream = {
        r["case_key"]: r
        for r in read_jsonl(UPSTREAM_LEDGER / "manual_source_coverage_48.jsonl")
    }
    grades = {g.strip() for g in args.only.split(",") if g.strip()}

    lines: list[str] = [
        "# D0-D3 adjudication pack -- expanded local corpus",
        "",
        "Rubric (identical to the upstream audit):",
        "D0 no valid disease anchor; D1 parent/component/sibling/list/name-only;",
        "D2 direct disease discussion missing a gold-defining qualifier;",
        "D3 source explains the vignette's decisive clues (bridges allowed if audited).",
        "",
    ]
    for case_key in sorted(scan):
        up = upstream[case_key]
        grade = up["diagnostic_support"].split("_", 1)[0]
        if grades and grade not in grades:
            continue
        row = scan[case_key]
        uw = unsliced[case_key]
        lines.append(f"\n\n{'=' * 100}")
        lines.append(f"## {case_key} | {row['gold']}")
        lines.append(f"UPSTREAM: {up['diagnostic_support']} (best={up['best_source']})")
        lines.append(f"UPSTREAM NOTE: {up['review_notes']}")
        lines.append(f"DECISIVE CLUES ({len(up['matched_vignette_clues'])}): "
                     + "; ".join(up["matched_vignette_clues"]))
        lines.append("MISSING QUALIFIERS: " + "; ".join(up["missing_qualifiers"]))

        for source in GUIDELINE_SOURCES:
            payload = row["by_source"].get(source)
            if not payload:
                continue
            top = sorted(
                payload["top_chunks"],
                key=lambda c: (-len(c["clues_matched"]), -c["score"]),
            )[:2]
            lines.append(f"\n--- [{source}] docs={payload['documents_with_entity_hit']} "
                         f"anchors={payload['best_entity_kinds']} "
                         f"clues={payload['clues_reached']}")
            for chunk in top:
                lines.append(
                    f"  * CHUNK {chunk['publisher']} :: {squash(chunk['title'], 120)}"
                    f" [clues={chunk['clues_matched']}]"
                )
                lines.append("    " + squash(chunk["content"]))
            window = uw["best_windows"].get(source)
            if window:
                meta = uw["unsliced_window"][source]
                lines.append(
                    f"  * UNSLICED WINDOW {meta['file']} [clues={meta['clues_matched']}]"
                )
                lines.append("    " + squash(window, 1400))

        cr = row["by_source"].get("case_report")
        if cr:
            lines.append(
                f"\n--- [CONTAMINATION PROBE case_report] docs={cr['documents_with_entity_hit']} "
                f"anchors={cr['best_entity_kinds']} titles="
                + "; ".join(squash(d["title"], 90) for d in cr["top_documents"][:3])
            )

    args.out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {args.out} ({args.out.stat().st_size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
