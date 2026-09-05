#!/usr/bin/env python3
"""Check, per case, whether a discriminating finding was extracted and how it was used.

Given a case and a set of keyword patterns naming the finding that separates the
gold diagnosis from the competitor the method actually chose, this reports for
each method whether the finding appears in

* the extracted fact / evidence ledger (``extracted``),
* the support spans of the gold-matching candidate (``supports_gold``),
* the support spans of the champion (``supports_champion``),
* the contradiction spans of any candidate (``used_as_contradiction``),
* the selector rationale (``in_selector``).

The distinction between "extracted" and "used correctly" is the whole point: a
finding can be present in the vignette, present in the guideline corpus, quoted
verbatim by the model, and still be attached to the wrong hypothesis.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
RECALL = ROOT / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL/method_hypothesis_recall_48.jsonl"
METHODS = ("collapse3c", "multistance", "impc", "forest")


def hits(patterns: list[str], texts: list[str]) -> list[str]:
    out = []
    for pat in patterns:
        rx = re.compile(pat, re.I)
        for text in texts:
            if text and rx.search(text):
                out.append(pat)
                break
    return out


def evidence_texts(data: dict[str, Any]) -> list[str]:
    out = []
    for item in data.get("evidence", []) or []:
        if isinstance(item, dict):
            out.append(str(item.get("raw_span", "")))
        else:
            out.append(str(item))
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", required=True)
    parser.add_argument("--patterns", required=True, help="||-separated regexes")
    args = parser.parse_args()

    patterns = [p.strip() for p in args.patterns.split("||") if p.strip()]
    rows = {
        json.loads(l)["case_key"]: json.loads(l)
        for l in RECALL.read_text(encoding="utf-8").splitlines()
        if l.strip()
    }
    row = rows[args.case]
    print(f"{args.case}  gold={row['gold']}  [{row['diagnostic_support_local'][:2]}]")
    print(f"patterns: {patterns}\n")

    for method in METHODS:
        data = row["methods"][method]
        if not data.get("present"):
            print(f"{method}: no trace")
            continue
        gold_entries = data["gold_registry_entries"]
        comp_entries = data["competitor_registry_entries"]
        champ = (data["champion"] or "").lower()

        def spans(entries: list[dict[str, Any]], key: str) -> list[str]:
            return [str(s) for e in entries for s in (e.get(key) or [])]

        gen = data["generator_candidates"]
        gold_gen = [g for g in gen if any(
            e["label"].lower() == g["label"].lower() for e in gold_entries)]
        champ_gen = [g for g in gen if g["label"].lower() == champ]

        report = {
            "extracted": hits(patterns, evidence_texts(data) + spans(gen, "support_spans") + spans(gen, "contradict_spans")),
            "supports_gold": hits(patterns, spans(gold_entries, "support_spans") + spans(gold_gen, "support_spans")),
            "supports_champion": hits(patterns, spans(champ_gen, "support_spans")),
            "as_contradiction": hits(patterns, spans(gold_entries, "contradict_spans") + spans(comp_entries, "contradict_spans") + spans(gen, "contradict_spans")),
            "in_selector": hits(patterns, [data["selector_why"] or ""] + [r.get("why", "") for r in data["selector_rejected"]]),
        }
        print(f"--- {method}  champion={data['champion']}  recall={data['recall_status']}  hit={data['correct'].get('top1')}")
        for key, value in report.items():
            print(f"      {key:18s}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
