#!/usr/bin/env python3
"""F6b: split a candidate's broad class into the subtypes the corpus names.

Section 3 of the trial report found that only 4 of 11 cases have a candidate at
the same granularity as the gold.  Five carry a strict superclass: multistance
answers "Abscess" where the gold is a collar-button abscess, "Carcinoma" where
the gold is a spindle-cell squamous cell carcinoma.  Adding methods does not
help -- none of the four ever proposed the subtype -- so the split has to come
from a knowledge source, and the corpus is the one at hand.

The miner is mechanical.  For a broad candidate it takes the head noun of the
label, harvests every modifier + head n-gram the corpus writes ("collar button
abscess", "web space abscess", "perianal abscess"), then ranks those subtypes by
how much of *this* vignette their own corpus text accounts for, weighting a
matched term by its rarity.  Nothing about the answer options or the gold enters:
the ranking signal for 257 is that the collar-button text talks about the web
space and the vignette says "palmar web space".
"""

from __future__ import annotations

import argparse
import json
import math
import pickle
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import scipy.sparse as sp

ROOT = Path(__file__).resolve().parents[4]
LEDGER = ROOT / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"
INDEX = ROOT / "data/corpus/ceiling_trial_index"
sys.path.insert(0, str(Path(__file__).parent))
import run_mechanical_engine as eng  # noqa: E402
from trial_retriever import TrialRetriever  # noqa: E402

BROAD_MIN_MENTIONS = 300     # a label the corpus talks about this much is a class
MAX_LABEL_TOKENS = 2         # ... and that is written this briefly
MIN_SUBTYPE_FREQ = 2         # a phrase seen once is usually a typo or a line break
TOP_PER_CLASS = 5
MAX_SCAN = 40000

MODIFIER_STOP = {
    "the", "a", "an", "of", "and", "or", "with", "without", "this", "that",
    "these", "those", "for", "from", "in", "on", "to", "by", "is", "are", "was",
    "were", "be", "been", "has", "have", "had", "its", "their", "his", "her",
    "such", "any", "all", "some", "no", "not", "as", "at", "into", "than",
    "patient", "patients", "case", "cases", "one", "two", "three", "may",
    "can", "will", "should", "must", "if", "when", "after", "before", "during",
    "other", "another", "each", "both", "same", "most", "more", "less",
}


def phrase_re(head: str) -> re.Pattern:
    # up to four modifiers: "spindle cell squamous cell carcinoma" needs them all
    return re.compile(rf"((?:[A-Za-z][A-Za-z\-]+\s+){{1,4}}){head}\b", re.I)


# The corpus records a subtype in two registers and neither channel covers both.
# Narrative usage ("a collar button abscess tracks from the palmar to the dorsal
# space") is caught by the n-gram channel and is the only trace of the rare
# entities: collar-button abscess exists in 2 chunks of 861k, spindle-cell
# squamous cell carcinoma in 3, and no taxonomic sentence names either.
# Explicit enumeration ("types of dementia include Alzheimer disease, vascular
# dementia, Lewy body dementia") is the only channel that surfaces the common
# subtypes, which the n-gram channel's density ranking buries -- a well
# documented subtype's own passages are long and mostly not about this vignette.
HEARST_NP = r"[A-Za-z][A-Za-z\-]*(?:\s+[a-zA-Z][A-Za-z\-]*){0,4}"


def hearst_patterns(head: str) -> list[tuple[str, re.Pattern]]:
    h = re.escape(head)
    return [
        ("is_a", re.compile(
            rf"({HEARST_NP})\s+is\s+(?:a|an|the)\s+(?:rare\s+|uncommon\s+|common\s+)?"
            rf"(?:type|form|variant|subtype|subset)\s+of\s+\w*\s*{h}", re.I)),
        ("enumerated", re.compile(
            rf"(?:variants|subtypes|types|forms)\s+of\s+{h}\s+(?:include|are)\s+"
            rf"([^.;]{{5,200}})", re.I)),
        ("includes", re.compile(
            rf"{h}\w*\s+(?:include|includes|comprise|comprises)\s+([^.;]{{5,200}})", re.I)),
        ("classified", re.compile(
            rf"{h}\w*\s+(?:is|are)\s+(?:classified|divided|subdivided)\s+into\s+"
            rf"([^.;]{{5,200}})", re.I)),
    ]


LIST_SPLIT = re.compile(r",|\band\b|\bor\b|;|\n", re.I)


def split_enumeration(blob: str, head: str) -> list[str]:
    out = []
    for part in LIST_SPLIT.split(blob):
        p = re.sub(r"\([^)]*\)", " ", part).strip(" \t.:•-")
        p = re.sub(r"^(?:the\s+following|such\s+as|e\.g\.?)\s*", "", p, flags=re.I).strip()
        words = p.split()
        if not 1 <= len(words) <= 5 or len(p) < 4:
            continue
        if not re.match(r"^[A-Za-z]", p):
            continue
        low = p.lower()
        if head not in low and not low.endswith(("disease", "syndrome", "'s")):
            p = f"{p} {head}"
        out.append(p)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default="trial_tasks_11_all4.json")
    ap.add_argument("--out", default="trial_tasks_11_all4_split.json")
    ap.add_argument("--report", default="subtype_mining.json")
    ap.add_argument("--top", type=int, default=TOP_PER_CLASS)
    args = ap.parse_args()

    print("loading index", flush=True)
    with (INDEX / "tfidf_vec.pkl").open("rb") as fh:
        vec = pickle.load(fh)
    mat = sp.load_npz(INDEX / "tfidf_mat.npz").tocsc()
    vocab = vec.vocabulary_
    R = TrialRetriever(use_dense=False)
    n_chunks = mat.shape[0]

    def chunks_with(tok: str) -> np.ndarray:
        col = vocab.get(tok)
        if col is None:
            return np.empty(0, dtype=np.int32)
        return mat.indices[mat.indptr[col]:mat.indptr[col + 1]].astype(np.int32)

    df_cache: dict[str, int] = {}

    def idf(tok: str) -> float:
        if tok not in df_cache:
            df_cache[tok] = int(chunks_with(tok).size)
        return math.log((n_chunks + 1) / (df_cache[tok] + 1))

    def mentions(label: str, aliases: list[str]) -> np.ndarray:
        acc: np.ndarray | None = None
        for name in [label, *aliases]:
            toks = [t for t in eng.norm(name).split() if t in vocab]
            if not toks:
                continue
            hit = chunks_with(toks[0])
            for t in toks[1:]:
                hit = np.intersect1d(hit, chunks_with(t))
                if hit.size == 0:
                    break
            acc = hit if acc is None else np.union1d(acc, hit)
        return acc if acc is not None else np.empty(0, dtype=np.int32)

    tasks = json.loads((LEDGER / args.tasks).read_text(encoding="utf-8"))
    report = []
    for task in tasks:
        vig = task["vignette"]
        cut = re.search(r"\n\s*(what is the most likely diagnosis|options\s*:)", vig, re.I)
        vig_body = vig[: cut.start()] if cut else vig
        vig_tokens = {w for w in eng.norm(vig_body).split() if len(w) >= 4 and w in vocab}

        added: list[dict] = []
        case_rows = []
        for cand in task["candidates"]:
            label = cand["label"]
            toks = [t for t in eng.norm(label).split() if t not in MODIFIER_STOP]
            if len(toks) > MAX_LABEL_TOKENS:
                continue
            mention = mentions(label, cand.get("aliases") or [])
            if mention.size < BROAD_MIN_MENTIONS:
                continue
            head = toks[-1]
            gids = mention[:MAX_SCAN]
            rx = phrase_re(head)
            hpats = hearst_patterns(head)
            freq: Counter = Counter()
            where: dict[str, list[int]] = defaultdict(list)
            taxo: Counter = Counter()
            taxo_where: dict[str, list[int]] = defaultdict(list)
            for gid in gids.tolist():
                text = R.text(gid)
                for pname, prx in hpats:
                    for m in prx.finditer(text):
                        for cand_name in split_enumeration(m.group(1), head):
                            key = eng.norm(cand_name)
                            if key and key != eng.norm(label):
                                taxo[key] += 1
                                if len(taxo_where[key]) < 25:
                                    taxo_where[key].append(gid)
                for m in rx.finditer(text):
                    mods = [w for w in eng.norm(m.group(1)).split() if w not in MODIFIER_STOP]
                    if not mods:
                        continue
                    for start in range(len(mods)):
                        phrase = " ".join(mods[start:] + [head])
                        if len(phrase.split()) < 2:
                            continue
                        freq[phrase] += 1
                        if len(where[phrase]) < 25:
                            where[phrase].append(gid)

            scored = []
            for phrase, f in freq.items():
                if f < MIN_SUBTYPE_FREQ or eng.norm(phrase) == eng.norm(label):
                    continue
                gs = where[phrase][:12]
                blob = " ".join(R.text(g) for g in gs)
                body = eng.norm(blob).split()
                seen = {w for w in body if w in vig_tokens}
                mass = sum(idf(w) for w in seen)
                # Ranking by the raw idf mass repeats the mistake section 6 found
                # in the engine: it rewards whichever subtype has the most text.
                # The collar-button abscess is written up in two chunks of the
                # whole corpus and came 16th that way; per-1000-token density
                # puts it first, because almost every word of those two chunks is
                # about this vignette.
                dens = mass / max(len(body), 1) * 1000
                scored.append({"subtype": phrase, "corpus_freq": f,
                               "vignette_terms_explained": len(seen),
                               "idf_mass": round(mass, 2), "score": round(dens, 2),
                               "gids": gs[:5]})
            scored.sort(key=lambda r: -r["score"])
            # "button abscess" and "collar button abscess" are the same entity
            # seen through different window widths; keep the longest.
            keep, taken = [], []
            for row in scored:
                if any(t.endswith(" " + row["subtype"]) for t in taken):
                    continue
                taken.append(row["subtype"])
                keep.append(row)
                if len(keep) >= args.top:
                    break

            taxo_keep = []
            for phrase, f in sorted(taxo.items(), key=lambda kv: -kv[1]):
                if f < 1 or phrase in {r["subtype"] for r in keep}:
                    continue
                taxo_keep.append({"subtype": phrase, "corpus_freq": f, "channel": "taxonomic",
                                  "gids": taxo_where[phrase][:5]})
                if len(taxo_keep) >= args.top:
                    break

            case_rows.append({"broad_label": label, "n_mentions": int(mention.size),
                              "n_subtypes_found": len(scored), "kept": keep,
                              "n_taxonomic_found": len(taxo), "taxonomic_kept": taxo_keep})
            for k in keep:
                added.append({"label": k["subtype"].title(), "methods": ["subtype_split"],
                              "gold_match": "none", "is_champion_of": [], "aliases": [],
                              "rank": {}, "_mined_from": label, "_channel": "ngram_density",
                              "_mining_score": k["score"]})
            for k in taxo_keep:
                added.append({"label": k["subtype"].title(), "methods": ["subtype_split"],
                              "gold_match": "none", "is_champion_of": [], "aliases": [],
                              "rank": {}, "_mined_from": label, "_channel": "taxonomic",
                              "_mining_score": k["corpus_freq"]})

        have = {eng.norm(c["label"]) for c in task["candidates"]}
        fresh = [a for a in added if eng.norm(a["label"]) not in have]
        task["candidates"] = sorted(task["candidates"] + fresh, key=lambda c: c["label"])
        task["n_candidates"] = len(task["candidates"])
        report.append({"case": task["case_key"], "gold": task["gold"],
                       "n_added": len(fresh), "classes": case_rows})
        print(f"  {task['case_key']:24s} broad classes={len(case_rows)} added={len(fresh)}",
              flush=True)
        for row in case_rows:
            print(f"      {row['broad_label']} ({row['n_mentions']} mentions, "
                  f"{row['n_subtypes_found']} subtypes)")
            for k in row["kept"]:
                print(f"         {k['score']:7.2f}  freq={k['corpus_freq']:4d}  {k['subtype']}")

    (LEDGER / args.out).write_text(json.dumps(tasks, indent=2, ensure_ascii=False), encoding="utf-8")
    (LEDGER / args.report).write_text(json.dumps(report, indent=2, ensure_ascii=False),
                                      encoding="utf-8")
    print(f"\nwrote {LEDGER / args.out} and {LEDGER / args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
