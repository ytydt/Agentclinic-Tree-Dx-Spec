#!/usr/bin/env python3
"""Does the LLM ever form a criterion group across sentence boundaries?

The trial extractor is a single LLM call over the retrieved chunk verbatim
(run_trial_extraction.py:531, `passage = p["text"][:6000]`); no list detection
and no claim-window segmentation stand between the corpus and the model.  So
bullets versus prose should not matter to it -- but the prompt says

    "when ONE SENTENCE lists several findings that together form ONE
     diagnostic criterion set, emit one assertion per member ..."

which is a restriction the model can obey.  If it does, groups will only ever
form inside a single sentence, and every criteria set written as a lead-in plus
separate member lines will be missed no matter how clean the corpus is.

Test: for every emitted group, measure the span its members' quotes cover in
the source passage, and whether that span crosses a sentence or line boundary.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path("/data2/wanghongyi/Agentclinic-Tree-Dx-Spec")
LEDGER = ROOT / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"

SENT_END = re.compile(r"[.!?][\"')\]]?\s")


def spans_sentence(quotes: list[str]) -> str:
    """Classify a group by the shape of its members' quotes."""
    uniq = {q for q in quotes if q}
    if len(uniq) <= 1:
        q = next(iter(uniq), "")
        if "\n" in q:
            return "one_quote_multiline"
        return "one_quote_one_sentence" if not SENT_END.search(q) \
            else "one_quote_multi_sentence"
    joined = " ".join(uniq)
    if any("\n" in q for q in uniq):
        return "many_quotes_multiline"
    if SENT_END.search(joined):
        return "many_quotes_cross_sentence"
    return "many_quotes_same_sentence"


def main() -> int:
    paths = sys.argv[1:] or [
        str(LEDGER / "trial_extraction_pool6k30all4clean_groups.json"),
        str(LEDGER / "trial_extraction_k30all4clean_groups.json"),
    ]
    for p in paths:
        path = Path(p)
        if not path.exists():
            print(f"missing {path.name}")
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        rows = data if isinstance(data, list) else (
            data.get("records") or data.get("results") or data.get("rows") or [])

        # group by (passage hash, group_id)
        groups: dict[tuple, list[dict]] = defaultdict(list)
        n_assert = n_grouped = 0
        logic = Counter()
        def real(v) -> bool:
            # the model frequently emits the literal string "null"
            return isinstance(v, str) and v.strip().lower() not in {"", "null", "none"}

        for rec in rows:
            asserts = rec.get("assertions") if isinstance(rec, dict) else None
            if asserts is None and isinstance(rec, dict) and "subject" in rec:
                asserts = [rec]
            for a in asserts or []:
                n_assert += 1
                cg = a.get("criterion_group")
                if not isinstance(cg, dict) or not real(cg.get("group_id")):
                    continue
                n_grouped += 1
                logic[str(cg.get("logic"))] += 1
                # same key the mechanical engine uses to assemble a group
                key = (a.get("_passage_sha1") or "", a.get("_source"),
                       a.get("_title"), a.get("_section"), a.get("_focus"),
                       cg.get("group_id"))
                groups[key].append(a)

        shapes = Counter()
        sizes = Counter()
        for key, members in groups.items():
            if len(members) < 2:
                sizes["singleton_group"] += 1
                continue
            sizes[f"{min(len(members), 6)}{'+' if len(members) >= 6 else ''}"] += 1
            shapes[spans_sentence([m.get("quote") or "" for m in members])] += 1

        print(f"\n{path.name}")
        print(f"  assertions {n_assert}, in a group {n_grouped} "
              f"({n_grouped/max(n_assert,1):.1%}), distinct groups {len(groups)}")
        print(f"  logic mix: {dict(logic.most_common())}")
        print(f"  group sizes: {dict(sorted(sizes.items()))}")
        tot = sum(shapes.values())
        if tot:
            print("  where a multi-member group's quotes sit:")
            for k, v in shapes.most_common():
                print(f"    {k:<28}{v:>6}  {v/tot:6.1%}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
