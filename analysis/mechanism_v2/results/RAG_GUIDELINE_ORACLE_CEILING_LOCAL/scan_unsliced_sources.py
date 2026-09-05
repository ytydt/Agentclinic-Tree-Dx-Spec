#!/usr/bin/env python3
"""Window-level oracle capacity over the *un-sliced* source texts.

`scan_expanded_source_capacity.py` measures what a single RAG chunk can offer.
This script measures what the original, never-chunked document offers, using a
sliding character window so that "the corpus mentions it somewhere" is never
mistaken for "one readable passage states it".

Two views are produced per case and per source:

* `chunk_level`   -- best single served chunk (read back from the chunk scan);
* `unsliced_window` -- best sliding window over the original text file.

The gap between them is the part of source capacity that the current chunker
destroys rather than the part the source never had.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
LEDGER_DIR = ROOT / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"

RAW_ROOTS: dict[str, list[Path]] = {
    "merck": [ROOT / "data/corpus/merck/merck_manual_19e_extracted.txt"],
    "manifest_cpg": sorted(
        p
        for d in (ROOT / "data/cpg/text").iterdir()
        if d.is_dir() and d.name not in {"wikem", "pmc_oa"}
        for p in d.glob("*.txt")
    ),
    "wikem": sorted((ROOT / "data/cpg/text/wikem").glob("*.txt")),
    "pmc_oa": sorted((ROOT / "data/cpg/text/pmc_oa").glob("*.txt")),
}

WINDOW_CHARS = 3000
STRIDE_CHARS = 1500


def load_scan_module() -> Any:
    spec = importlib.util.spec_from_file_location(
        "expanded_scan", HERE / "scan_expanded_source_capacity.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["expanded_scan"] = module
    spec.loader.exec_module(module)
    return module


SC = load_scan_module()


def windows(text: str) -> list[str]:
    if len(text) <= WINDOW_CHARS:
        return [text]
    return [text[i : i + WINDOW_CHARS] for i in range(0, len(text) - STRIDE_CHARS, STRIDE_CHARS)]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=HERE)
    parser.add_argument("--ledger-out", type=Path, default=LEDGER_DIR)
    args = parser.parse_args()

    index = SC.PhraseIndex()
    cases = SC.build_case_terms(index)
    phrase_owner: dict[int, list[tuple[int, str]]] = defaultdict(list)
    for ci, case in enumerate(cases):
        for kind, ids in case["entity_phrase_ids"].items():
            for pid in ids:
                phrase_owner[pid].append((ci, kind))

    best: dict[tuple[int, str], dict[str, Any]] = {}
    files_scanned = 0
    for source, paths in RAW_ROOTS.items():
        for path in paths:
            if not path.exists():
                continue
            files_scanned += 1
            text = path.read_text(encoding="utf-8", errors="replace")
            for window in windows(text):
                normalized = SC.norm(window)
                tokens = set(normalized.split())
                matched = index.match(tokens, normalized)
                if not matched:
                    continue
                per_case: dict[int, set[str]] = defaultdict(set)
                for pid in matched:
                    for ci, kind in phrase_owner.get(pid, ()):
                        per_case[ci].add(kind)
                for ci, kinds in per_case.items():
                    case = cases[ci]
                    n_clues, clue_names = SC.bag_coverage(case["clue_bags"], tokens)
                    n_quals, qual_names = SC.bag_coverage(case["qualifier_bags"], tokens)
                    score = SC.score_chunk(kinds, n_clues, n_quals)
                    key = (ci, source)
                    current = best.get(key)
                    if current is None or score > current["score"]:
                        best[key] = {
                            "score": round(score, 3),
                            "file": str(path.relative_to(ROOT)),
                            "entity_kinds": sorted(kinds),
                            "clues_matched": clue_names,
                            "qualifiers_matched": qual_names,
                            "window": window.strip(),
                        }
        print(f"[unsliced] {source}: {len(paths)} files", flush=True)
    print(f"[unsliced] {files_scanned} files scanned", flush=True)

    chunk_scan = {
        json.loads(line)["case_key"]: json.loads(line)
        for line in (LEDGER_DIR / "expanded_oracle_scan_48.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    }

    rows: list[dict[str, Any]] = []
    for ci, case in enumerate(cases):
        scan_row = chunk_scan[case["case_key"]]
        chunk_best: dict[str, Any] = {}
        for source, payload in scan_row["by_source"].items():
            if source == "case_report":
                continue
            top = payload.get("top_chunks") or []
            if not top:
                continue
            leader = max(top, key=lambda c: (len(c["clues_matched"]), c["score"]))
            chunk_best[source] = {
                "entity_kinds": leader["entity_kinds"],
                "clues_matched": leader["clues_matched"],
                "n_clues": len(leader["clues_matched"]),
            }
        unsliced: dict[str, Any] = {
            source: payload
            for (case_index, source), payload in best.items()
            if case_index == ci
        }
        best_chunk_clues = max((v["n_clues"] for v in chunk_best.values()), default=0)
        best_window_clues = max((len(v["clues_matched"]) for v in unsliced.values()), default=0)
        rows.append(
            {
                "case_key": case["case_key"],
                "family": case["family"],
                "gold": case["gold"],
                "sampling_stratum": case["sampling_stratum"],
                "sampling_weight": case["sampling_weight"],
                "upstream_diagnostic_support": case["upstream_diagnostic_support"],
                "n_decisive_clues": len(case["clue_bags"]),
                "chunk_level": chunk_best,
                "unsliced_window": {
                    source: {k: v for k, v in payload.items() if k != "window"}
                    for source, payload in unsliced.items()
                },
                "best_windows": {
                    source: payload["window"][:2400] for source, payload in unsliced.items()
                },
                "best_single_chunk_clues": best_chunk_clues,
                "best_unsliced_window_clues": best_window_clues,
                "dechunking_clue_gain": best_window_clues - best_chunk_clues,
            }
        )

    (args.ledger_out / "unsliced_window_capacity_48.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows),
        encoding="utf-8",
    )
    summary = {
        "schema_version": "unsliced-window-capacity-v1",
        "window_chars": WINDOW_CHARS,
        "stride_chars": STRIDE_CHARS,
        "files_scanned": files_scanned,
        "cases": len(rows),
        "cases_where_unsliced_window_beats_best_chunk": sum(
            r["dechunking_clue_gain"] > 0 for r in rows
        ),
        "mean_clues_best_chunk": round(
            sum(r["best_single_chunk_clues"] for r in rows) / len(rows), 3
        ),
        "mean_clues_best_unsliced_window": round(
            sum(r["best_unsliced_window_clues"] for r in rows) / len(rows), 3
        ),
        "cases_with_all_clues_in_one_chunk": sum(
            r["n_decisive_clues"] > 0 and r["best_single_chunk_clues"] >= r["n_decisive_clues"]
            for r in rows
        ),
        "cases_with_all_clues_in_one_unsliced_window": sum(
            r["n_decisive_clues"] > 0 and r["best_unsliced_window_clues"] >= r["n_decisive_clues"]
            for r in rows
        ),
        "note": (
            "Only Merck 19e, the manifest CPG texts, WikEM and PMC-OA keep an un-sliced original "
            "in this repository. StatPearls and the textbook corpora ship as chunks only, so their "
            "un-sliced ceiling cannot be measured here."
        ),
    }
    (args.out / "unsliced_window_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
