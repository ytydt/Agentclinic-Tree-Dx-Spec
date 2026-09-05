#!/usr/bin/env python3
"""Hypothesis-conditioned clue scan: is a decisive clue *exclusive* to the gold?

The previous scans asked "does the corpus state this clue anywhere".  That is
not enough to justify a decision rule.  A clue only discriminates if the corpus
attaches it to the gold diagnosis and *not* to the competing hypotheses the
methods actually proposed.

This builds, per case, a clue x hypothesis co-mention matrix over the six
guideline sources.  Hypotheses are the frozen gold plus every distinct candidate
label produced by Collapse3c, MultiStance, IMPC and MOSAIC Forest on that case.
Clues are the manually curated ``matched_vignette_clues`` from the audit ledger,
so every clue is by construction present in the vignette.

Co-mention is counted at two granularities:

``chunk``     clue and hypothesis in the same retrieved unit -- the strongest
              form, and the only one a chunk-level retriever could ever serve;
``document``  clue and hypothesis anywhere in the same source document, i.e.
              what an oracle reader of the whole article would see.

Absence of co-mention is weak evidence of exclusion (an article can simply be
short), so the output labels each clue with the asymmetry actually observed
rather than asserting exclusivity outright.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(HERE))

from scan_expanded_source_capacity import (  # noqa: E402
    UP,
    CORPUS_TIERS,
    PhraseIndex,
    bag_coverage,
    camel_split,
    chunk_document_key,
    concept_phrases,
    content_tokens,
    informative,
    norm,
    norm_tokens,
)

# Gold labels in these benchmarks carry case-report qualifiers ("Cutaneous
# malakoplakia", "Linagliptin-induced acute pancreatitis") that never appear
# verbatim in a guideline, so matching the raw string leaves most golds with
# zero documents.  Both sides therefore go through the same bridge/variant
# expansion the D0-D3 audit uses.  Only the gold additionally gets the
# adjudicated ``matched_concept``, since no such annotation exists for
# method-proposed competitors; the asymmetry favours the gold and so can only
# make the separability estimate optimistic.
VARIANT_KINDS = ("exact", "aliases", "parenthetical_stripped", "camel_split")

LEDGER_DIR = ROOT / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"
LEDGER = LEDGER_DIR / "manual_source_coverage_48_local_expanded.jsonl"
RECALL = LEDGER_DIR / "method_hypothesis_recall_48.jsonl"
METHODS = ("collapse3c", "multistance", "impc", "forest")

SOURCES = {s: p for group in CORPUS_TIERS.values() for s, p in group.items()}

# A "document" in the textbook source is an entire book, so any two concepts
# co-occur in it vacuously.  Such units are dropped from document-level
# co-mention (their chunk-level evidence is still counted).
DOC_LEVEL_EXCLUDED_SOURCES = {"textbooks"}
MAX_DOC_CHUNKS = 300

# Co-mention is polarity-blind: a passage saying "Michaelis-Gutmann bodies
# distinguish malakoplakia from xanthoma" mentions the finding alongside both
# diagnoses while asserting it of only one.  Counting how much co-mention sits
# in differential or negated context bounds how far raw co-occurrence can be
# read as "feature of".
CONTRAST_RE = re.compile(
    r"\b(differential(?:\s+diagnos\w+)?|distinguish\w*|differentiat\w*|unlike|in contrast|"
    r"rule[sd]?\s+out|ruling out|exclud\w+|mimic\w*|versus|rather than|as opposed to|"
    r"argues against|absence of|without evidence of|not seen in|does not)\b",
    re.I,
)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def hypothesis_labels(row: dict[str, Any]) -> dict[str, dict[str, list[str]]]:
    """Split candidate labels into gold-equivalent, ambiguous and competitor.

    A method that names the gold at concept level often uses a different string
    than the frozen gold label ("Malakoplakia" for "Cutaneous malakoplakia").
    Those were already adjudicated as strong matches by the recall audit, so
    they belong in the gold column; putting them in the competitor column would
    manufacture a competitor that is really the answer.  Near matches are
    neither, and are excluded from scoring rather than assigned arbitrarily.
    """
    buckets: dict[str, dict[str, set[str]]] = {
        b: defaultdict(set) for b in ("gold_equivalent", "ambiguous", "competitor")
    }
    for method in METHODS:
        data = row["methods"][method]
        if not data.get("present"):
            continue
        graded: dict[str, str] = {}
        for entry in data["gold_registry_entries"]:
            graded[norm(entry["label"])] = (
                "gold_equivalent" if entry.get("gold_match") == "strong" else "ambiguous"
            )
        for entry in data["competitor_registry_entries"]:
            graded.setdefault(norm(entry["label"]), "competitor")

        labels = [e["label"] for e in data["gold_registry_entries"] + data["competitor_registry_entries"]]
        labels += [g["label"] for g in data["generator_candidates"]]
        labels += [data["champion"], data["runner_up"]]
        for label in labels:
            label = (label or "").strip()
            if len(label) < 3:
                continue
            buckets[graded.get(norm(label), "competitor")][label].add(method)
    return {b: {k: sorted(v) for k, v in d.items()} for b, d in buckets.items()}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=LEDGER_DIR / "feature_hypothesis_matrix_48.jsonl")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    ledger = {r["case_key"]: r for r in read_jsonl(LEDGER)}
    recall = {r["case_key"]: r for r in read_jsonl(RECALL)}

    aliases, canonicals, known = UP.bridge_tables()

    def forms_of(label: str) -> list[str]:
        variants = UP.label_variants(label, aliases, canonicals, known)
        out = [v for kind in VARIANT_KINDS for v in variants.get(kind, [])]
        camel = camel_split(label)
        if camel:
            out.append(camel)
        return [f for f in out if f and f.strip()]

    index = PhraseIndex()
    cases: list[dict[str, Any]] = []
    for key, row in ledger.items():
        gold = row["gold"]
        buckets = hypothesis_labels(recall[key])
        gold_forms = forms_of(gold)
        gold_forms += concept_phrases(row.get("matched_concept", ""))
        gold_methods: set[str] = set()
        for label, methods in buckets["gold_equivalent"].items():
            gold_forms += forms_of(label)
            gold_methods.update(methods)
        seen: set[str] = set()
        gold_forms = [f for f in gold_forms if f and not (norm(f) in seen or seen.add(norm(f)))]

        hyps: list[dict[str, Any]] = [
            {
                "label": gold,
                "role": "gold",
                "methods": sorted(gold_methods),
                "forms": gold_forms,
                "phrase_ids": [i for i in (index.add(f) for f in gold_forms) if i is not None],
            }
        ]
        gold_norms = {norm(f) for f in gold_forms}
        ambiguous = {norm(f) for label in buckets["ambiguous"] for f in forms_of(label)}
        for label, methods in buckets["competitor"].items():
            forms = forms_of(label)
            norms = {norm(f) for f in forms}
            if norms & gold_norms:
                hyps[0]["methods"] = sorted(set(hyps[0]["methods"]) | set(methods))
                continue
            if norms & ambiguous:
                continue
            hyps.append(
                {
                    "label": label,
                    "role": "competitor",
                    "methods": methods,
                    "forms": forms,
                    "phrase_ids": [i for i in (index.add(f) for f in forms) if i is not None],
                }
            )

        clue_bags = []
        for clue in row.get("matched_vignette_clues", []):
            tokens = informative(norm_tokens(clue))
            if tokens:
                clue_bags.append({"clue": clue, "tokens": tokens})

        cases.append({"case_key": key, "gold": gold, "hypotheses": hyps, "clue_bags": clue_bags,
                      "family": row["family"], "d0d3": row["diagnostic_support"][:2]})

    phrase_to_cases: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for ci, case in enumerate(cases):
        for hi, hyp in enumerate(case["hypotheses"]):
            for pid in hyp["phrase_ids"]:
                phrase_to_cases[pid].append((ci, hi))
    print(f"{len(cases)} cases, {sum(len(c['hypotheses']) for c in cases)} hypotheses, "
          f"{len(index.phrases)} phrases", flush=True)

    # ---- pass 1: which documents mention which hypotheses --------------------
    doc_hyps: dict[tuple[str, str], set[tuple[int, int]]] = defaultdict(set)
    # A hypothesis named in the document *title* makes that document a reference
    # description of it, rather than a document that merely mentions it in
    # passing.  Rates conditioned on topic documents are not diluted by how
    # broad the concept is, which plain mention rates are.
    doc_topic: dict[tuple[str, str], set[tuple[int, int]]] = defaultdict(set)
    chunk_pairs: dict[tuple[int, int, int], int] = defaultdict(int)
    chunk_pairs_contrast: dict[tuple[int, int, int], int] = defaultdict(int)
    chunk_marginal: dict[tuple[int, int], int] = defaultdict(int)
    doc_of_interest: set[tuple[str, str]] = set()
    title_cache: dict[str, set[tuple[int, int]]] = {}

    for source, path in SOURCES.items():
        n = 0
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if args.limit and n >= args.limit:
                    break
                n += 1
                row = json.loads(line)
                text = row.get("text") or row.get("content") or ""
                if not text:
                    continue
                tokens = content_tokens(text)
                normalized = norm(text)
                hits = index.match(tokens, normalized)
                if not hits:
                    continue
                present: set[tuple[int, int]] = set()
                for pid in hits:
                    present.update(phrase_to_cases.get(pid, ()))
                if not present:
                    continue
                doc = (source, chunk_document_key(source, row))
                doc_of_interest.add(doc)
                doc_hyps[doc].update(present)
                for pair in present:
                    chunk_marginal[pair] += 1

                title = str(row.get("title") or "")
                if title and source not in DOC_LEVEL_EXCLUDED_SOURCES:
                    if title not in title_cache:
                        thits = index.match(content_tokens(title), norm(title))
                        tpairs: set[tuple[int, int]] = set()
                        for pid in thits:
                            tpairs.update(phrase_to_cases.get(pid, ()))
                        title_cache[title] = tpairs
                    doc_topic[doc].update(title_cache[title])
                # chunk-level clue co-mention, computed immediately
                by_case: dict[int, list[int]] = defaultdict(list)
                for ci, hi in present:
                    by_case[ci].append(hi)
                contrast = bool(CONTRAST_RE.search(text))
                for ci, his in by_case.items():
                    _, matched = bag_coverage(cases[ci]["clue_bags"], tokens)
                    if not matched:
                        continue
                    clue_ix = {b["clue"]: i for i, b in enumerate(cases[ci]["clue_bags"])}
                    for hi in his:
                        for clue in matched:
                            chunk_pairs[(ci, hi, clue_ix[clue])] += 1
                            if contrast:
                                chunk_pairs_contrast[(ci, hi, clue_ix[clue])] += 1
        print(f"  pass1 {source}: {n} chunks, {len(doc_of_interest)} docs so far", flush=True)

    # ---- pass 2: clues anywhere in those documents ---------------------------
    doc_clues: dict[tuple[str, str], set[tuple[int, int]]] = defaultdict(set)
    doc_size: dict[tuple[str, str], int] = defaultdict(int)
    for source, path in SOURCES.items():
        n = 0
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if args.limit and n >= args.limit:
                    break
                n += 1
                row = json.loads(line)
                doc = (source, chunk_document_key(source, row))
                if doc not in doc_of_interest:
                    continue
                doc_size[doc] += 1
                text = row.get("text") or row.get("content") or ""
                if not text:
                    continue
                tokens = content_tokens(text)
                cand = {ci for ci, _ in doc_hyps[doc]}
                for ci in cand:
                    _, matched = bag_coverage(cases[ci]["clue_bags"], tokens)
                    clue_ix = {b["clue"]: i for i, b in enumerate(cases[ci]["clue_bags"])}
                    for clue in matched:
                        doc_clues[doc].add((ci, clue_ix[clue]))
        print(f"  pass2 {source}: {n} chunks", flush=True)

    doc_pairs: dict[tuple[int, int, int], int] = defaultdict(int)
    doc_marginal: dict[tuple[int, int], int] = defaultdict(int)
    topic_pairs: dict[tuple[int, int, int], int] = defaultdict(int)
    topic_marginal: dict[tuple[int, int], int] = defaultdict(int)
    dropped = 0
    for doc, hyp_set in doc_hyps.items():
        if doc[0] in DOC_LEVEL_EXCLUDED_SOURCES or doc_size.get(doc, 0) > MAX_DOC_CHUNKS:
            dropped += 1
            continue
        topic_set = doc_topic.get(doc, set())
        for pair in hyp_set:
            doc_marginal[pair] += 1
        for pair in topic_set:
            topic_marginal[pair] += 1
        clue_set = doc_clues.get(doc, set())
        if not clue_set:
            continue
        for ci, hi in hyp_set:
            for cj, fi in clue_set:
                if cj == ci:
                    doc_pairs[(ci, hi, fi)] += 1
        for ci, hi in topic_set:
            for cj, fi in clue_set:
                if cj == ci:
                    topic_pairs[(ci, hi, fi)] += 1

    # ---- assemble ------------------------------------------------------------
    out_rows = []
    for ci, case in enumerate(cases):
        clues = [b["clue"] for b in case["clue_bags"]]
        matrix = []
        for fi, clue in enumerate(clues):
            gold_doc = doc_pairs.get((ci, 0, fi), 0)
            gold_chunk = chunk_pairs.get((ci, 0, fi), 0)
            comp = []
            for hi, hyp in enumerate(case["hypotheses"]):
                if hi == 0:
                    continue
                d = doc_pairs.get((ci, hi, fi), 0)
                c = chunk_pairs.get((ci, hi, fi), 0)
                if d or c:
                    comp.append({"label": hyp["label"], "methods": hyp["methods"],
                                 "documents": d, "chunks": c})
            comp.sort(key=lambda x: -x["documents"])
            if gold_doc and not comp:
                verdict = "gold_exclusive"
            elif gold_doc and comp:
                verdict = "shared"
            elif not gold_doc and comp:
                verdict = "competitor_only"
            else:
                verdict = "unreachable"
            matrix.append(
                {
                    "clue": clue,
                    "gold_documents": gold_doc,
                    "gold_chunks": gold_chunk,
                    "competitors_with_clue": comp,
                    "n_competitors_with_clue": len(comp),
                    "verdict": verdict,
                }
            )
        n_excl = sum(1 for m in matrix if m["verdict"] == "gold_exclusive")
        n_shared = sum(1 for m in matrix if m["verdict"] == "shared")
        n_comp = sum(1 for m in matrix if m["verdict"] == "competitor_only")
        n_unreach = sum(1 for m in matrix if m["verdict"] == "unreachable")
        out_rows.append(
            {
                "case_key": case["case_key"],
                "family": case["family"],
                "gold": case["gold"],
                "d0d3_local": case["d0d3"],
                "n_hypotheses": len(case["hypotheses"]),
                "hypotheses": [
                    {
                        "label": h["label"],
                        "role": h["role"],
                        "methods": h["methods"],
                        "forms": h["forms"],
                        "documents": doc_marginal.get((ci, hi), 0),
                        "chunks": chunk_marginal.get((ci, hi), 0),
                        "topic_documents": topic_marginal.get((ci, hi), 0),
                        "clue_documents": {
                            case["clue_bags"][fi]["clue"]: doc_pairs.get((ci, hi, fi), 0)
                            for fi in range(len(case["clue_bags"]))
                        },
                        "clue_topic_documents": {
                            case["clue_bags"][fi]["clue"]: topic_pairs.get((ci, hi, fi), 0)
                            for fi in range(len(case["clue_bags"]))
                        },
                        "clue_chunks": {
                            case["clue_bags"][fi]["clue"]: chunk_pairs.get((ci, hi, fi), 0)
                            for fi in range(len(case["clue_bags"]))
                        },
                        "clue_chunks_in_contrast_context": {
                            case["clue_bags"][fi]["clue"]: chunk_pairs_contrast.get((ci, hi, fi), 0)
                            for fi in range(len(case["clue_bags"]))
                        },
                    }
                    for hi, h in enumerate(case["hypotheses"])
                ],
                "clue_matrix": matrix,
                "n_clues": len(clues),
                "n_gold_exclusive": n_excl,
                "n_shared": n_shared,
                "n_competitor_only": n_comp,
                "n_unreachable": n_unreach,
                "separable_by_exclusive_clue": n_excl > 0,
            }
        )

    args.out.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True) for r in out_rows) + "\n",
        encoding="utf-8",
    )
    sep = sum(1 for r in out_rows if r["separable_by_exclusive_clue"])
    print(json.dumps({"cases": len(out_rows),
                      "separable_by_>=1_exclusive_clue": sep,
                      "docs_dropped_from_doc_level": dropped,
                      "docs_kept": len(doc_hyps) - dropped}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
