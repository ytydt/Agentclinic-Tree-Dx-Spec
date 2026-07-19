#!/usr/bin/env python3
"""CPG oracle upper-bound recall: does the source CONTAIN the gold DDx info,
reachable from the syndrome/symptom-group entry?  (CPG §18, IMP-54)

This answers "with retrieval quality maxed out, what is the ceiling recall?" by
NOT ranking — instead, for each case's presenting syndrome we:
  1. ENTRY MATCH  : find every chunk whose syndrome_anchor / section_path /
                    title contains a syndrome anchor term (multi-source aware:
                    PMC anchor=title, WikEM anchor=complaint, NICE/society =
                    guideline-title prose, Merck = "Approach to" chapter).
  2. ARTICLE CLOSURE : from each entry chunk, pull ALL chunks sharing its
                    source_id (the real DDx body lives in sibling chunks), plus
                    WikEM ``wiki_links`` (an explicit DDx entity list).
  3. GOLD REACHABLE : is the gold family mentioned anywhere in that closure?

Three tiers reported per case:
  - entry-direct   : gold in the entry chunk text itself
  - entry+closure  : gold in entry's article closure (THE realistic ceiling)
  - full-corpus    : gold mentioned anywhere in any CPG chunk (absolute bound;
                     gap vs closure = "present but NOT organised under entry")

Per-source attribution shows which CPG source supplies the reachable gold.

    PYTHONPATH=src python scripts/eval_cpg_oracle_recall.py
"""
from __future__ import annotations

import json
import re
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHUNKS = ROOT / "data" / "cpg" / "processed" / "cpg_chunks.jsonl"
OUT = ROOT / "data" / "cpg" / "eval" / "cpg_oracle_recall.json"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
import eval_branch_creator_isolated as E

# Presenting syndrome / symptom-group ENTRY anchors per case (root node), with
# clinically-plausible synonyms + UK spellings (NICE/society use -aemia/-oedema).
# Deliberately INCLUSIVE (oracle = ceiling): we want every entry that truly is
# about this syndrome; per-source entry counts are reported so noise is visible.
SYNDROME_ENTRY = {
    1:  ["pancoast", "superior sulcus", "apical lung", "horner", "brachial plex",
         "shoulder pain", "arm pain", "hand muscle atrophy"],
    9:  ["leukocytosis", "leukaemoid", "leukemoid", "elevated white blood",
         "raised white cell", "high white cell", "neutrophilia"],
    13: ["necrolytic migratory erythema", "glucagonoma",
         "hyperglycaemia", "hyperglycemia", "rash diabetes", "diabetes rash"],
    17: ["leukocytosis", "elevated white blood", "raised white cell",
         "high white cell", "myeloproliferative", "neutrophilia"],
    18: ["peliosis", "hepatic vascular", "liver lesion", "liver mass",
         "hepatic mass", "hepatomegaly", "hepatic angioma", "abdominal pain"],
    22: ["hypercalcaemia", "hypercalcemia", "high calcium", "elevated calcium",
         "raised calcium"],
    23: ["bowel obstruction", "intestinal obstruction", "small bowel obstruction",
         "ileus", "acute abdomen"],
    24: ["nasal foreign body", "unilateral nasal", "nasal discharge",
         "rhinorrhoea", "rhinorrhea", "foreign body nose", "nasal obstruction"],
}

# US/UK spelling normaliser so gold "tumor/leukemia" also match UK guideline text
_UK = [("tumour", "tumor"), ("leukaemia", "leukemia"), ("oedema", "edema"),
       ("haemo", "hemo"), ("paediatric", "pediatric"), ("oesoph", "esoph"),
       ("anaemia", "anemia"), ("hypercalcaemia", "hypercalcemia"),
       ("hyperglycaemia", "hyperglycemia"), ("leukaemoid", "leukemoid")]


def usuk(t: str) -> str:
    t = (t or "").lower()
    for uk, us in _UK:
        t = t.replace(uk, us)
    return t


def gold_in_text(gold: str, text: str, idx: int | None) -> bool:
    t = usuk(text)
    if not t:
        return False
    gt = [tok for tok in re.findall(r"[a-z0-9]+", usuk(gold)) if len(tok) > 3]
    if gt and all(tok in t for tok in gt):
        return True
    if idx is not None and idx in E.GOLD_FAMILY_TOKENS:
        for acc in E.GOLD_FAMILY_TOKENS[idx]:
            if all(re.search(rf"\b{re.escape(usuk(tok))}", t) for tok in acc if len(tok) > 3):
                return True
    return False


def entry_match(anchor: str, section: str, title: str, terms: list[str]) -> bool:
    hay = usuk(f"{anchor} || {section} || {title}")
    return any(usuk(term) in hay for term in terms)


def main() -> int:
    cases = E.load_cases()
    gnorm = E.load_gold_normaliser()
    case_gold = {c["idx"]: E.norm_gold(c["ans"], gnorm) for c in cases
                 if c["ans"].lower() not in E.SIGN_GOLDS}
    idxs = sorted(case_gold)

    # ---- Pass 1: entry source_ids per case + full-corpus gold mention -------
    entry_sids: dict[int, set[str]] = {i: set() for i in idxs}
    entry_direct: dict[int, bool] = {i: False for i in idxs}
    entry_by_source: dict[int, "Counter"] = {i: defaultdict(int) for i in idxs}
    full_corpus_gold: dict[int, set[str]] = {i: set() for i in idxs}  # sources
    n_lines = 0
    t0 = time.time()
    with CHUNKS.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            n_lines += 1
            d = json.loads(line)
            src = d.get("source", "?")
            sid = d.get("source_id") or d.get("article_id") or ""
            anchor = d.get("syndrome_anchor") or ""
            section = d.get("section_path") or ""
            title = d.get("title") or ""
            content = d.get("content") or ""
            wl = d.get("wiki_links") or []
            wl_txt = " ".join(wl) if isinstance(wl, list) else str(wl)
            body = f"{section} {content} {wl_txt}"
            for i in idxs:
                if entry_match(anchor, section, title, SYNDROME_ENTRY[i]):
                    if sid:
                        entry_sids[i].add(sid)
                    entry_by_source[i][src] += 1
                    if gold_in_text(case_gold[i], body, i):
                        entry_direct[i] = True
                # absolute bound: gold mentioned anywhere
                if gold_in_text(case_gold[i], body, i):
                    full_corpus_gold[i].add(src)
    print(f"Pass1: {n_lines} chunks scanned in {time.time()-t0:.1f}s")

    # ---- Pass 2: article closure of entry source_ids -----------------------
    all_entry_sids = set().union(*entry_sids.values()) if idxs else set()
    closure_text: dict[str, list[str]] = defaultdict(list)  # sid -> texts
    closure_src: dict[str, str] = {}
    with CHUNKS.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            d = json.loads(line)
            sid = d.get("source_id") or d.get("article_id") or ""
            if sid not in all_entry_sids:
                continue
            wl = d.get("wiki_links") or []
            wl_txt = " ".join(wl) if isinstance(wl, list) else str(wl)
            closure_text[sid].append(
                f"{d.get('section_path','')} {d.get('content','')} {wl_txt}")
            closure_src[sid] = d.get("source", "?")

    # ---- Tier evaluation ----------------------------------------------------
    results = {}
    union_entry = union_closure = union_full = 0
    for i in idxs:
        gold = case_gold[i]
        # closure: gold reachable in any entry article's full body
        closure_hit_src = set()
        for sid in entry_sids[i]:
            body = " ".join(closure_text.get(sid, []))
            if gold_in_text(gold, body, i):
                closure_hit_src.add(closure_src.get(sid, "?"))
        in_entry = entry_direct[i]
        in_closure = in_entry or bool(closure_hit_src)
        in_full = bool(full_corpus_gold[i])
        union_entry += in_entry
        union_closure += in_closure
        union_full += in_full
        results[i] = {
            "gold": gold,
            "n_entry_chunks": sum(entry_by_source[i].values()),
            "entry_by_source": dict(entry_by_source[i]),
            "n_entry_articles": len(entry_sids[i]),
            "gold_in_entry_chunk": in_entry,
            "gold_in_entry_closure": in_closure,
            "closure_hit_sources": sorted(closure_hit_src),
            "gold_in_full_corpus": in_full,
            "full_corpus_sources": sorted(full_corpus_gold[i]),
        }
        flag_c = "HIT" if in_closure else "MISS"
        flag_f = "HIT" if in_full else "MISS"
        print(f"  c{i:<2} {gold[:26]:26} entry={results[i]['n_entry_chunks']:>4} "
              f"art={results[i]['n_entry_articles']:>3} | direct={'Y' if in_entry else '-'} "
              f"closure={flag_c}({','.join(sorted(closure_hit_src)) or '-'}) "
              f"full={flag_f}({','.join(sorted(full_corpus_gold[i])) or '-'})")

    n = len(idxs)
    summary = {
        "n_cases": n,
        "oracle_entry_direct": f"{union_entry}/{n}",
        "oracle_entry_closure": f"{union_closure}/{n}",
        "oracle_full_corpus": f"{union_full}/{n}",
    }
    print("\n=== ORACLE CEILING (all CPG sources) ===")
    print(f"  entry-direct (gold in entry chunk):   {union_entry}/{n} = {union_entry/n:.0%}")
    print(f"  entry+closure (gold in entry article): {union_closure}/{n} = {union_closure/n:.0%}  ← realistic ceiling")
    print(f"  full-corpus (gold anywhere in CPG):    {union_full}/{n} = {union_full/n:.0%}  (absolute bound)")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(
        {"generated_at": datetime.now(timezone.utc).isoformat(),
         "summary": summary, "per_case": results}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    print(f"\nWrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
