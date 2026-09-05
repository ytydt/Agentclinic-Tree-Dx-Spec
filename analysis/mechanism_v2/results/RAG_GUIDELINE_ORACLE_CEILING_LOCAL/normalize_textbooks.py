#!/usr/bin/env python3
"""Input-side normalisation for the textbooks corpus, and what it buys.

§26.2 recommended normalising the OCR noise textbooks inherited from the MedRAG
release without measuring what that recovers for criteria.  Two things have to
be separated:

  character-level  ligatures, end-of-line hyphenation, page references -- these
                   are repairable in place and change what the extractor reads
  structural       the fixed 865-char windows cut criteria lists apart -- only
                   stitching adjacent chunks fixes that, not normalisation

A first pass with a naive `([A-Za-z]{2,})-\\s+([a-z]{2,})` dehyphenation rule
produced "box- shaped" -> "boxshaped" and, where two PDF columns interleave,
"sin- your reasoning. gle-celled" -> "sinyour reasoning. gle-celled".  Merging
therefore has to be licensed by the corpus's own vocabulary rather than by shape
alone, and the rule below is measured for precision on a hand-checked sample.

    python normalize_textbooks.py [--write]
"""
from __future__ import annotations

import argparse
import glob
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
LEDGER = ROOT / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"
CHUNK_DIR = ROOT / "data" / "corpus" / "textbooks" / "chunk"
VOCAB_CACHE = LEDGER / "textbooks_vocab.json"

LIGATURES = {"\ufb00": "ff", "\ufb01": "fi", "\ufb02": "fl",
             "\ufb03": "ffi", "\ufb04": "ffl", "\ufb05": "st", "\ufb06": "st"}
BREAK = re.compile(r"([A-Za-z]{2,})-\s+([a-z]{2,})")
PAGE_REF = re.compile(r"\s*\((?:pp?\.|see p\.)\s*\d+(?:[-–—]\d+)?\)")
CODE_NOISE = re.compile(r"\bP\?PF[^\s]{0,6}\b")
SOFT_HYPHEN = re.compile(r"[\u00ad\u2010]")
WORD = re.compile(r"[A-Za-z][A-Za-z-]{1,}")

# a fragment followed by one of these is column interleaving, not a line break
FUNCTION_WORDS = {
    "the", "your", "and", "but", "for", "with", "that", "this", "these",
    "those", "from", "into", "than", "then", "when", "where", "which", "who",
    "you", "our", "their", "his", "her", "its", "not", "are", "was", "were",
    "has", "have", "had", "can", "may", "will", "would", "should", "could",
    "also", "such", "each", "both", "some", "any", "all", "one", "two",
}

ANNOUNCE = re.compile(
    r"\b(?:requir\w+|includ\w+|consist\w+|compris\w+|defined by|based on|"
    r"following|criteria|criterion)\b[^.]{0,70}:\s*$", re.I)
# "all of these defects produce a left-to-right shunt" is anaphora, not a
# criteria set, so a bare "of these" only counts when a criteria noun follows
QUANT = re.compile(
    r"\b(?:at least\s+)?(two|three|four|five|2|3|4|5|both|all|any|one)\b"
    r"[^.]{0,40}?\bof\s+(?:the\s+)?(?:following\b|above\b|"
    r"(?:\w+\s+){0,2}criteri(?:a|on)\b|"
    r"these\s+(?:\w+\s+){0,1}(?:criteri|feature|finding|sign|symptom|"
    r"element|component|manifestation)\w*)", re.I)
MEMBER_MARK = re.compile(r"(?:^|\s)(?:\(?[1-9a-e][.)]|[•▪▸]\s)")
# a list rendered as running prose: three or more short comma/semicolon items
def looks_enumerated(t: str) -> bool:
    """strict: numbering, bullets, or a short comma/semicolon list."""
    if len(MEMBER_MARK.findall(t)) >= 2:
        return True
    seg = re.split(r"(?<=[.])\s+[A-Z]", t)[0]
    items = [x.strip() for x in re.split(r"[;,]", seg) if x.strip()]
    return len(items) >= 3 and sum(1 for x in items[:4] if 3 <= len(x) <= 80) >= 3


def looks_enumerated_loose(t: str) -> bool:
    """also accept a list the PDF extraction rendered as running prose.

    "obtained in the following ways: ECG/EKG (electrocardiography)-a series of
    electrical traces ... Echocardiography-..." keeps every member but drops the
    item boundaries, so the strict test above misses it.
    """
    if looks_enumerated(t):
        return True
    units = [x.strip() for x in re.split(r"(?<=[.;])\s+|[\u2014\u2013]\s", t)
             if x.strip()]
    return sum(1 for x in units if 10 <= len(x) <= 300) >= 3


def build_vocab(books: dict[str, list[dict]]) -> tuple[Counter, Counter]:
    """plain-word and hyphenated-compound frequencies, from the corpus itself."""
    if VOCAB_CACHE.exists():
        d = json.loads(VOCAB_CACHE.read_text("utf-8"))
        return Counter(d["plain"]), Counter(d["hyphen"])
    plain: Counter = Counter()
    hyph: Counter = Counter()
    for rows in books.values():
        for d in rows:
            for w in WORD.findall((d.get("content") or "").lower()):
                if "-" in w:
                    hyph[w.strip("-")] += 1
                else:
                    plain[w] += 1
    plain = Counter({k: v for k, v in plain.items() if v >= 3})
    hyph = Counter({k: v for k, v in hyph.items() if v >= 3})
    VOCAB_CACHE.write_text(json.dumps({"plain": plain, "hyphen": hyph}), "utf-8")
    return plain, hyph


def make_normaliser(plain: Counter, hyph: Counter):
    def join(m: re.Match) -> str:
        a, b = m.group(1), m.group(2)
        merged, compound = (a + b).lower(), f"{a.lower()}-{b.lower()}"
        # "ribo- some" is a broken word even though "some" is a function word,
        # so a confident vocabulary hit outranks the interleaving guard
        if plain.get(merged, 0) >= 20 and hyph.get(compound, 0) == 0:
            return a + b
        if b.lower() in FUNCTION_WORDS:
            return m.group(0)                      # column interleaving
        if hyph.get(compound, 0) > plain.get(merged, 0):
            return f"{a}-{b}"                      # a real hyphenated compound
        if plain.get(merged, 0) >= 3:
            return a + b                           # a broken word
        return m.group(0)                          # unknown: leave it alone

    def normalise(t: str) -> str:
        for x, y in LIGATURES.items():
            t = t.replace(x, y)
        t = SOFT_HYPHEN.sub("-", t)
        t = PAGE_REF.sub("", t)
        t = CODE_NOISE.sub("", t)
        prev = None
        while prev != t:
            prev = t
            t = BREAK.sub(join, t)
        return re.sub(r"\s{2,}", " ", t).strip()
    return normalise


def load() -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for f in sorted(glob.glob(str(CHUNK_DIR / "*.jsonl"))):
        rows = [json.loads(l) for l in open(f, encoding="utf-8") if l.strip()]
        rows.sort(key=lambda d: int(str(d["id"]).rsplit("_", 1)[-1])
                  if str(d["id"]).rsplit("_", 1)[-1].isdigit() else 0)
        out[Path(f).stem] = rows
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    books = load()
    n = sum(len(v) for v in books.values())
    plain, hyph = build_vocab(books)
    norm = make_normaliser(plain, hyph)
    print(f"textbooks: {len(books)} books, {n} chunks; "
          f"vocab {len(plain)} words, {len(hyph)} hyphenated compounds\n")

    print("=== 1. what the vocabulary-guarded rule does to each break ===")
    verdict = Counter()
    ex: dict[str, list[str]] = {}
    for rows in books.values():
        for d in rows:
            t = d.get("content") or ""
            for m in BREAK.finditer(t):
                a, b = m.group(1), m.group(2)
                merged, compound = (a + b).lower(), f"{a.lower()}-{b.lower()}"
                if b.lower() in FUNCTION_WORDS:
                    v = "left alone: function word (column interleaving)"
                elif hyph.get(compound, 0) > plain.get(merged, 0):
                    v = "kept as a hyphenated compound"
                elif plain.get(merged, 0) >= 3:
                    v = "merged: a broken word"
                else:
                    v = "left alone: neither form is in the vocabulary"
                verdict[v] += 1
                ex.setdefault(v, []).append(f"{a}- {b}")
    tot = sum(verdict.values())
    for k, v in verdict.most_common():
        print(f"  {k:<52}{v:>7}  {v / tot:6.1%}")
        print(f"      e.g. {', '.join(ex[k][:5])}")

    print("\n=== 2. what normalisation changes, corpus-wide ===")
    changed = Counter()
    for rows in books.values():
        for d in rows:
            t = d.get("content") or ""
            if norm(t) != t:
                changed["any"] += 1
    print(f"  chunks changed  {changed['any']:>7}  {changed['any'] / n:6.2%}")

    print("\n=== 3. the criteria-bearing subset ===")
    crit = []
    for book, rows in books.items():
        for i, d in enumerate(rows):
            t = d.get("content") or ""
            if QUANT.search(t) or ANNOUNCE.search(t):
                crit.append((book, i, t))
    nc = len(crit)
    ch = sum(1 for _, _, t in crit if norm(t) != t)
    # compare like with like: norm() also squashes whitespace and strips, which
    # a mid-string slice always trips, so the baseline gets the same treatment
    def squash(s: str) -> str:
        return re.sub(r"\s{2,}", " ", s).strip()
    inside = 0
    for _, _, t in crit:
        m = QUANT.search(t) or ANNOUNCE.search(t)
        span = t[max(0, m.start() - 120):m.end() + 300]
        if norm(span) != squash(span):
            inside += 1
    print(f"  chunks stating a criteria set / announcing a list  {nc:>5}"
          f"  {nc / n:6.2%}")
    print(f"    normalisation changes the chunk                  {ch:>5}"
          f"  {ch / nc:6.1%}")
    print(f"    ... the change sits inside the criteria sentence {inside:>5}"
          f"  {inside / nc:6.1%}")

    print("\n=== 4. the structural axis, which normalisation cannot touch ===")
    stats = {}
    absent_ex = []
    for name, test in (("strict", looks_enumerated),
                       ("loose (accepts prose-rendered lists)",
                        looks_enumerated_loose)):
        same = nxt = absent = 0
        for book, i, t in crit:
            rows = books[book]
            m = QUANT.search(t) or ANNOUNCE.search(t)
            tail = t[m.end():]
            if test(tail):
                same += 1
                continue
            nb = " ".join((rows[j].get("content") or "")
                          for j in range(i + 1, min(i + 3, len(rows))))
            if test(nb):
                nxt += 1
            else:
                absent += 1
                if name.startswith("loose") and len(absent_ex) < 10:
                    absent_ex.append(
                        (book, t[max(0, m.start() - 60):m.end() + 240], nb[:200]))
        stats[name] = (same, nxt, absent)
    for name, (same, nxt, absent) in stats.items():
        print(f"\n  member test: {name}")
        print(f"    members in the same chunk            {same:>5}  {same / nc:6.1%}")
        print(f"    members only in the next 1-2 chunks  {nxt:>5}  {nxt / nc:6.1%}"
              f"   <- stitching, not normalisation")
        print(f"    no enumeration found nearby          {absent:>5}"
              f"  {absent / nc:6.1%}")
    print("\n  the 'no enumeration' bucket under the loose test, for hand checking:")
    for b, a, c in absent_ex:
        print(f"\n    [{b}] ...{a}\n      next: {c}...")

    if args.write:
        # The per-book files under chunk/ carry {id,title,content,contents} but
        # no article_id, while the corpus file the retrieval index is built from
        # carries {id,title,content,article_id,tokens}.  Writing the per-book
        # schema out cost every textbook chunk its article_id, and
        # TrialRetriever.passage() uses "source|article_id" to decide whether a
        # neighbouring chunk is still the same document -- an empty article_id
        # silently turns the +-1 window's document guard off for the whole
        # source.  So emit the canonical file's rows, replacing only content.
        canonical = ROOT / "data/corpus/textbooks/textbooks_chunks.jsonl"
        normalised = {d["id"]: norm(d.get("content") or "")
                      for rows in books.values() for d in rows}
        out = LEDGER / "textbooks_chunks_normalised.jsonl"
        missing = 0
        with canonical.open(encoding="utf-8") as src, \
                out.open("w", encoding="utf-8") as f:
            for line in src:
                d = json.loads(line)
                if d["id"] in normalised:
                    d["content"] = normalised[d["id"]]
                else:
                    missing += 1
                f.write(json.dumps(d, ensure_ascii=False) + "\n")
        print(f"\nwrote {out}"
              + (f"  ({missing} ids absent from chunk/, left unnormalised)"
                 if missing else ""))

    json.dump({"chunks": n, "changed": changed["any"], "break_verdicts": verdict,
               "criteria_chunks": nc, "criteria_changed": ch,
               "criteria_change_in_span": inside,
               "member_location": {k: {"same": v[0], "next": v[1], "absent": v[2]}
                                   for k, v in stats.items()}},
              (LEDGER / "textbooks_normalisation_audit.json").open("w"), indent=2)
    print(f"\nwrote {LEDGER / 'textbooks_normalisation_audit.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
