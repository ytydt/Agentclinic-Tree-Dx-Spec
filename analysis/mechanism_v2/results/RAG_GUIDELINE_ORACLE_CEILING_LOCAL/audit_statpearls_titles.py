#!/usr/bin/env python3
"""Is the title attached to a StatPearls chunk the title of its own article?

Found while building the corpus lift table: no document in the 861k-chunk index
carries "Long QT Syndrome" in its title, although the StatPearls slice is
367,799 chunks over 9,158 articles and StatPearls certainly has that entry.
Sampling showed chunk `_p0` titled with a TIMI-trial reference while its content
is the Chronic Total Occlusion entry, so the title looks to be lifted from the
article's reference list.

The test is deliberately blunt: an article's own title should share content
words with its own body.  A reference title lifted from the bibliography usually
will not.  Reported alongside the empty `article_id` field, which is what makes
document reassembly and doc-level statistics unavailable on this source.
"""

from __future__ import annotations

import json
import random
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
LEDGER = ROOT / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"
SRC = ROOT / "data/corpus/statpearls/statpearls_chunks.jsonl"
sys.path.insert(0, str(Path(__file__).parent))
import run_mechanical_engine as eng  # noqa: E402

STOP = {"the", "of", "and", "a", "an", "in", "for", "to", "with", "its", "on",
        "case", "review", "report", "study", "clinical", "patients", "patient",
        "analysis", "management", "treatment", "evaluation", "diagnosis"}


def main() -> int:
    by_article: dict[str, list[str]] = defaultdict(list)
    n_chunks = 0
    n_empty_article_id = 0
    for line in SRC.open(encoding="utf-8"):
        row = json.loads(line)
        n_chunks += 1
        if not (row.get("article_id") or "").strip():
            n_empty_article_id += 1
        title = (row.get("title") or "").split(" > ")[0].strip()
        by_article[title].append(row.get("content") or "")

    rnd = random.Random(0)
    sample = rnd.sample(sorted(by_article), 400)
    hits = misses = 0
    examples = []
    for title in sample:
        body = " ".join(by_article[title])[:20000].lower()
        toks = [w for w in re.findall(r"[a-z]{4,}", eng.norm(title)) if w not in STOP]
        if not toks:
            continue
        present = sum(1 for t in toks if t in body)
        ok = present / len(toks) >= 0.6
        hits += ok
        misses += not ok
        if not ok and len(examples) < 12:
            examples.append({"title": title, "coverage": round(present / len(toks), 2),
                             "first_chunk": by_article[title][0][:160]})

    out = {
        "n_chunks": n_chunks,
        "n_articles": len(by_article),
        "n_empty_article_id": n_empty_article_id,
        "sampled": hits + misses,
        "title_matches_body": hits,
        "title_foreign_to_body": misses,
        "rate_foreign": round(misses / max(hits + misses, 1), 3),
        "examples": examples,
    }
    (LEDGER / "statpearls_title_audit.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in out.items() if k != "examples"}, indent=2))
    print("\nexamples of a title foreign to its own body:")
    for e in examples:
        print(f"  cov={e['coverage']}  {e['title'][:90]}")
        print(f"      body: {e['first_chunk'][:110]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
