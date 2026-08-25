#!/usr/bin/env python3
"""Two zero-call gates on input channels that `NORMALIZED_INPUT_PROBE` §4 left open.

Both are separate from the (closed) symptom-cluster line and are scored
separately; neither may be folded into a cluster narrative.

`extraction` -- §4.1. `VignetteParser` recovers 0.8354 of vignette content tokens
    against the C1 fact ledger's 0.6095. The surplus cannot be cited by any
    candidate (it is, by construction, absent from the ledger), so "does it
    support complete candidates" has to be asked counterfactually. Three angles:

      demand    do candidates' own `support_spans` ever quote material outside
                the ledger? If the generator never reaches past C1, C1's
                compression is not starving it.
      gold      of the gold-label content tokens that actually occur in the
                vignette, how many does each extractor keep?
      ceiling   are the above worse on cases where no complete label was
                produced at all? That is where dropped evidence would have to
                bite if it bites anywhere.

`negative` -- §4.2. Normalization turns 96 normal lab values into explicit
    rule-outs. Before asking whether that helps, ask whether it is new: the
    generator already emits `contradict_spans`. If normal values are already
    quoted there, the channel is redundant -- the same "already absorbed by the
    generator" pattern that closed the cluster line.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
for _p in (ROOT, ROOT / "analysis" / "mechanism_v2"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from clinical_endpoint import COMPLETE, ClinicalEndpoint  # noqa: E402

OUT = ROOT / "analysis/mechanism_v2/results/INPUT_CHANNEL_GATES"
CACHE = ROOT / "analysis/mechanism_v2/results/NORMALIZED_INPUT_PROBE/normalized_cache.json"

SLICES = {
    "mcr_v1": ("medcasereasoning", "mcr_val_seq100_v1"),
    "mcr_v2": ("medcasereasoning_v2", "mcr_val_seq100_v2"),
}
ARM = "aphhm_c_multistance_v1"

# Deliberately small: only forms that carry no clinical content on their own.
STOP = {
    "with",
    "without",
    "from",
    "that",
    "this",
    "were",
    "been",
    "have",
    "has",
    "had",
    "and",
    "the",
    "for",
    "was",
    "his",
    "her",
    "she",
    "they",
    "them",
    "which",
    "after",
    "before",
    "into",
    "onto",
    "over",
    "under",
    "also",
    "than",
    "then",
    "there",
    "their",
    "patient",
    "history",
    "finding",
    "findings",
    "showed",
    "revealed",
    "presented",
    "noted",
    "left",
    "right",
    "year",
    "years",
    "old",
    "male",
    "female",
    "woman",
    "man",
}


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", (text or "").lower())).strip()


# The parser emits "Field: content". The field label is its own formatting, not
# vignette content, so leaving it in would mark items orphaned purely because the
# ledger never says the word "Demographics".
FIELD_PREFIX = re.compile(r"^[A-Z][A-Za-z /()-]{2,40}:\s*")


def strip_field(text: str) -> tuple[str, str]:
    m = FIELD_PREFIX.match(text or "")
    if not m:
        return "", text or ""
    return m.group(0).rstrip(": ").strip().lower(), (text or "")[m.end() :]


def content_tokens(text: str) -> set[str]:
    return {t for t in norm(text).split() if len(t) >= 4 and t not in STOP}


def load_subset() -> dict[str, dict[str, dict[str, str]]]:
    """`{slice: {case_id: {gold, case_text}}}` from the frozen subset manifests.

    The vignette has to come from here: `case_stages` records only
    `vignette_chars`, not the text itself.
    """
    out: dict[str, dict[str, dict[str, str]]] = {}
    for sl, (_, subset) in SLICES.items():
        path = (
            ROOT
            / "data/benchmarks/medcasereasoning/subsets"
            / subset
            / "normalized_cases.json"
        )
        doc = json.loads(path.read_text())
        out[sl] = {
            str(c["id"]): {
                "gold": str(c.get("gold") or ""),
                "case_text": str(c.get("case_text") or ""),
            }
            for c in doc["cases"]
        }
    return out


def load_cases() -> list[dict[str, Any]]:
    """Per-case join of frozen ledger, frozen parse, gold, and clinical verdicts."""
    cache = json.loads(CACHE.read_text())["cases"]
    subset = load_subset()
    endpoint = ClinicalEndpoint()
    endpoint.drop_conflicts()

    cases: list[dict[str, Any]] = []
    for sl, (dataset, _) in SLICES.items():
        pattern = f"logs/backbone_v1/{dataset}/{ARM}/case_stages/*.json"
        for path in sorted(ROOT.glob(pattern)):
            cid = path.stem
            key = f"{sl}/{cid}"
            if key not in cache:
                continue
            doc = json.loads(path.read_text())
            stages = doc.get("stages") or {}
            registry = stages.get("registry") or []
            candidates = []
            for cand in registry:
                label = str(cand.get("preferred_label") or "")
                candidates.append(
                    {
                        "label": label,
                        "relation": endpoint.relation(
                            "mcr", sl, cid, label
                        ),
                        "support_spans": [
                            str(x) for x in (cand.get("support_spans") or [])
                        ],
                        "contradict_spans": [
                            str(x) for x in (cand.get("contradict_spans") or [])
                        ],
                    }
                )
            cases.append(
                {
                    "slice": sl,
                    "case_id": cid,
                    "vignette": subset[sl].get(cid, {}).get("case_text", ""),
                    "gold": subset[sl].get(cid, {}).get("gold", ""),
                    "champion_complete": endpoint.relation(
                        "mcr", sl, cid, str(doc.get("champion") or "")
                    )
                    == COMPLETE,
                    "facts": [
                        {
                            "raw_span": str(f.get("raw_span") or ""),
                            "modality": str(f.get("modality") or ""),
                            "polarity": str(f.get("polarity") or ""),
                        }
                        for f in (stages.get("facts") or [])
                    ],
                    "parser_items": cache[key]["items"],
                    "candidates": candidates,
                    "has_complete": any(
                        c["relation"] == COMPLETE for c in candidates
                    ),
                    "any_judged": any(c["relation"] is not None for c in candidates),
                }
            )
    return cases


# --------------------------------------------------------------------------
# stage: extraction
# --------------------------------------------------------------------------


def stage_extraction(_: argparse.Namespace) -> int:
    cases = load_cases()

    demand_in = demand_out = 0
    demand_out_in_orphan = 0
    orphan_items = 0
    parser_items = 0
    empty_body_items = 0
    orphan_fields: Counter[str] = Counter()
    orphan_examples: list[str] = []
    gold_rows: list[dict[str, Any]] = []

    for case in cases:
        ledger_blob = " || ".join(norm(f["raw_span"]) for f in case["facts"])
        ledger_tokens = set()
        for f in case["facts"]:
            ledger_tokens |= content_tokens(f["raw_span"])

        # An orphan is a parser item whose content tokens the ledger does not carry,
        # judged on the body only (see `strip_field`).
        orphan_tokens: set[str] = set()
        parser_tokens: set[str] = set()
        for item in case["parser_items"]:
            parser_items += 1
            field, body = strip_field(item["text"])
            toks = content_tokens(body)
            parser_tokens |= toks
            if toks and not (toks & ledger_tokens):
                orphan_items += 1
                orphan_tokens |= toks
                orphan_fields[field or "(no field label)"] += 1
                if len(orphan_examples) < 30:
                    orphan_examples.append(item["text"][:110])
            elif not toks:
                empty_body_items += 1

        for cand in case["candidates"]:
            for span in cand["support_spans"]:
                n = norm(span)
                if not n:
                    continue
                if n in ledger_blob:
                    demand_in += 1
                else:
                    demand_out += 1
                    if content_tokens(span) & orphan_tokens:
                        demand_out_in_orphan += 1

        # Gold tokens are only fair game if the vignette actually contains them.
        gold_toks = content_tokens(case["gold"])
        vig_toks = content_tokens(case["vignette"]) if case["vignette"] else set()
        present = gold_toks & vig_toks if vig_toks else set()
        if present:
            gold_rows.append(
                {
                    "has_complete": case["has_complete"],
                    "n_present": len(present),
                    "ledger": len(present & ledger_tokens) / len(present),
                    "parser": len(present & parser_tokens) / len(present),
                }
            )

    def gold_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
        if not rows:
            return {"cases": 0}
        return {
            "cases": len(rows),
            "mean_gold_tokens_in_vignette": round(
                mean(r["n_present"] for r in rows), 4
            ),
            "ledger_recall": round(mean(r["ledger"] for r in rows), 4),
            "parser_recall": round(mean(r["parser"] for r in rows), 4),
            "delta": round(
                mean(r["parser"] for r in rows) - mean(r["ledger"] for r in rows), 4
            ),
        }

    judged = [c for c in cases if c["any_judged"]]
    ceiling = [c for c in judged if not c["has_complete"]]
    result = {
        "experiment": "EXTRACTION_COMPLETENESS_GATE",
        "created_at": utcnow(),
        "calls": 0,
        "population": {
            "cases": len(cases),
            "cases_with_any_clinical_verdict": len(judged),
            "ceiling_cases_no_complete_in_pool": len(ceiling),
        },
        # Does the generator ever reach past the ledger?
        "demand_for_out_of_ledger_evidence": {
            "support_spans_total": demand_in + demand_out,
            "inside_ledger": demand_in,
            "outside_ledger": demand_out,
            "outside_share": round(demand_out / max(demand_in + demand_out, 1), 4),
            "outside_and_matched_by_parser_orphan": demand_out_in_orphan,
        },
        "parser_surplus": {
            "parser_items": parser_items,
            "items_with_no_content_token_after_field_strip": empty_body_items,
            "orphan_items_no_token_overlap_with_ledger": orphan_items,
            "orphan_share": round(orphan_items / max(parser_items, 1), 4),
            "orphan_field_labels_top15": dict(orphan_fields.most_common(15)),
            "orphan_examples": orphan_examples,
        },
        "gold_token_recovery": {
            "all_cases": gold_summary(gold_rows),
            "ceiling_cases": gold_summary(
                [r for r in gold_rows if not r["has_complete"]]
            ),
            "reached_cases": gold_summary(
                [r for r in gold_rows if r["has_complete"]]
            ),
        },
    }
    write_json(OUT / "extraction.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=2)[:4000])
    return 0


# --------------------------------------------------------------------------
# stage: negative
# --------------------------------------------------------------------------


def stage_negative(_: argparse.Namespace) -> int:
    cases = load_cases()

    ruleout_items = 0
    only_contradict = only_support = both_polarities = uncited = 0
    flippable_cases = flippable_ruleouts = flippable_uncited = 0
    ruleout_examples: list[dict[str, Any]] = []
    # Is the existing contradiction channel discriminative at all?
    contra: dict[str, list[int]] = {"complete": [], "incomplete": []}
    absent_facts = absent_cited = 0

    for case in cases:
        contra_blob = " || ".join(
            norm(s) for c in case["candidates"] for s in c["contradict_spans"]
        )
        support_blob = " || ".join(
            norm(s) for c in case["candidates"] for s in c["support_spans"]
        )
        # Only cases where the intervention could act: the frozen champion is not
        # complete, yet a complete rival sits in the pool.
        flippable = case["has_complete"] and not case["champion_complete"]
        if flippable:
            flippable_cases += 1

        for item in case["parser_items"]:
            if not any(n["negated_hpo_terms"] for n in item["normalized"]):
                continue
            ruleout_items += 1
            _, body = strip_field(item["text"])
            toks = content_tokens(body)
            in_contra = bool(toks) and bool(toks & content_tokens(contra_blob))
            in_support = bool(toks) and bool(toks & content_tokens(support_blob))
            if in_contra and in_support:
                both_polarities += 1
            elif in_contra:
                only_contradict += 1
            elif in_support:
                only_support += 1
            else:
                uncited += 1
            if flippable:
                flippable_ruleouts += 1
                flippable_uncited += int(not in_contra and not in_support)
            if len(ruleout_examples) < 25:
                ruleout_examples.append(
                    {
                        "text": item["text"][:100],
                        "negated": [
                            t
                            for n in item["normalized"]
                            for t in n["negated_hpo_terms"]
                        ][:3],
                        "in_contradict_spans": in_contra,
                        "in_support_spans": in_support,
                    }
                )

        for cand in case["candidates"]:
            if cand["relation"] is None:
                continue
            bucket = "complete" if cand["relation"] == COMPLETE else "incomplete"
            contra[bucket].append(len(cand["contradict_spans"]))

        # The ledger already marks negatives; are those facts used?
        for fact in case["facts"]:
            if fact["polarity"] != "absent":
                continue
            absent_facts += 1
            if content_tokens(fact["raw_span"]) & content_tokens(contra_blob):
                absent_cited += 1

    result = {
        "experiment": "NEGATIVE_EVIDENCE_CHANNEL_GATE",
        "created_at": utcnow(),
        "calls": 0,
        "normalization_derived_ruleouts": {
            "items": ruleout_items,
            "only_contradict_spans": only_contradict,
            "only_support_spans": only_support,
            "both_polarities_same_case": both_polarities,
            "never_quoted_anywhere": uncited,
            "already_used_as_negative_rate": round(
                (only_contradict + both_polarities) / max(ruleout_items, 1), 4
            ),
            "headroom_rate_never_quoted": round(uncited / max(ruleout_items, 1), 4),
            "examples": ruleout_examples,
        },
        # An intervention can only pay off where the champion is wrong but a
        # complete rival is present; everything else is out of reach by
        # construction.
        "reach_on_flippable_cases": {
            "flippable_cases": flippable_cases,
            "ruleouts_available": flippable_ruleouts,
            "of_which_never_quoted": flippable_uncited,
            "uncited_ruleouts_per_flippable_case": round(
                flippable_uncited / max(flippable_cases, 1), 4
            ),
        },
        "existing_contradiction_channel": {
            k: {
                "n_candidates": len(v),
                "mean_contradict_spans": round(mean(v), 4) if v else None,
                "share_with_any": round(sum(1 for x in v if x) / len(v), 4) if v else None,
            }
            for k, v in contra.items()
        },
        "ledger_absent_polarity_facts": {
            "n": absent_facts,
            "quoted_in_contradict_spans": absent_cited,
            "rate": round(absent_cited / max(absent_facts, 1), 4),
        },
    }
    write_json(OUT / "negative.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=2)[:4000])
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="stage", required=True)
    sub.add_parser("extraction").set_defaults(fn=stage_extraction)
    sub.add_parser("negative").set_defaults(fn=stage_negative)
    args = ap.parse_args()
    return int(args.fn(args))


if __name__ == "__main__":
    raise SystemExit(main())
