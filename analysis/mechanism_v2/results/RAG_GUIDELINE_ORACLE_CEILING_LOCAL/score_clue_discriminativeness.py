#!/usr/bin/env python3
"""Can a corpus-derived rule separate the gold from the competitors it faced?

Reads the clue x hypothesis co-mention matrix and answers two questions the
binary "is this clue unique to the gold" test is too blunt to settle:

1.  Per clue, how much does it favour the gold over the *specific* competitors
    the four methods proposed?  Measured as a likelihood ratio between
    P(clue | gold) and the best competing P(clue | h), where the conditional is
    the fraction of that hypothesis's source documents that also state the clue.

2.  Per case, if we hand a naive-Bayes reader exactly these clues and exactly
    this corpus, does the gold come out on top?  This is the mechanical
    equivalent of "build a decision tree per case", and its accuracy bounds how
    much of the discrimination gap is retrievable structure versus judgement
    that only a human reading the guideline can supply.

A hypothesis needs MIN_DOCS documents before its conditionals are trusted;
below that the estimate is noise and the case is reported as under-covered
rather than scored.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
LEDGER_DIR = ROOT / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"
MATRIX = LEDGER_DIR / "feature_hypothesis_matrix_48.jsonl"
RECALL = LEDGER_DIR / "method_hypothesis_recall_48.jsonl"
SCOPE = LEDGER_DIR / "discrimination_scope.csv"
METHODS = ("collapse3c", "multistance", "impc", "forest")

MIN_DOCS = 5
MIN_TOPIC_DOCS = 3
ALPHA = 0.5
SPECIFIC_LIFT = 3.0
LEANING_LIFT = 1.5
SPECIFIC_RATE = 0.20


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def rate(hits: int, total: int) -> float:
    return (hits + ALPHA) / (total + 2 * ALPHA)


def classify(lift: float, p_gold: float, covered: bool) -> str:
    if not covered:
        return "unusable_low_coverage"
    if lift >= SPECIFIC_LIFT and p_gold >= SPECIFIC_RATE:
        return "gold_specific"
    if lift >= LEANING_LIFT:
        return "gold_leaning"
    if lift > 1 / LEANING_LIFT:
        return "non_discriminating"
    return "favours_competitor"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, default=LEDGER_DIR)
    args = parser.parse_args()

    matrix = {r["case_key"]: r for r in read_jsonl(MATRIX)}
    recall = {r["case_key"]: r for r in read_jsonl(RECALL)}
    scope = set()
    if SCOPE.exists():
        with SCOPE.open(encoding="utf-8") as fh:
            scope = {r["case_key"] for r in csv.DictReader(fh)}

    clue_rows: list[dict[str, Any]] = []
    case_rows: list[dict[str, Any]] = []

    for key, row in matrix.items():
        hyps = row["hypotheses"]
        gold = hyps[0]
        clues = list(gold["clue_documents"].keys())

        # Two denominators.  "mention" counts every document that names the
        # hypothesis, which dilutes broad concepts; "topic" counts only
        # documents titled for it, which is the reference description but is
        # sparse for rare entities.  Prefer topic where it is estimable.
        use_topic = gold["topic_documents"] >= MIN_TOPIC_DOCS and sum(
            1 for h in hyps[1:] if h["topic_documents"] >= MIN_TOPIC_DOCS
        ) >= 2
        if use_topic:
            den, num = "topic_documents", "clue_topic_documents"
            floor = MIN_TOPIC_DOCS
        else:
            den, num = "documents", "clue_documents"
            floor = MIN_DOCS

        comps = [h for h in hyps[1:] if h[den] >= floor]
        gold_covered = gold[den] >= floor

        per_clue = []
        for clue in clues:
            p_gold = rate(gold[num][clue], gold[den])
            comp_rates = [(rate(h[num][clue], h[den]), h) for h in comps]
            comp_rates.sort(key=lambda x: -x[0])
            best_p, best_h = comp_rates[0] if comp_rates else (ALPHA / (2 * ALPHA), None)
            lift = p_gold / best_p if best_p > 0 else float("inf")
            covered = gold_covered and bool(comps)
            verdict = classify(lift, p_gold, covered)
            per_clue.append(
                {
                    "clue": clue,
                    "denominator": "topic" if use_topic else "mention",
                    "p_gold": round(p_gold, 4),
                    "gold_hits": gold[num][clue],
                    "gold_docs": gold[den],
                    "best_competitor": best_h["label"] if best_h else "",
                    "best_competitor_methods": best_h["methods"] if best_h else [],
                    "p_best_competitor": round(best_p, 4),
                    "lift": round(lift, 3) if lift != float("inf") else None,
                    "verdict": verdict,
                }
            )
            clue_rows.append({"case_key": key, "gold": row["gold"], **per_clue[-1]})

        # naive-Bayes ranking over exactly these clues and this corpus
        ranking = []
        if gold_covered and comps:
            for h in [gold] + comps:
                score = sum(math.log(rate(h[num][c], h[den])) for c in clues)
                ranking.append((score, h["label"], h["role"]))
            ranking.sort(key=lambda x: -x[0])
        gold_rank = next((i + 1 for i, r in enumerate(ranking) if r[2] == "gold"), None)

        meth = recall[key]["methods"]
        case_rows.append(
            {
                "case_key": key,
                "family": row["family"],
                "gold": row["gold"],
                "d0d3_local": row["d0d3_local"],
                "in_deep_review_scope": key in scope,
                "sampling_weight": recall[key]["sampling_weight"],
                "sampling_stratum": recall[key]["sampling_stratum"],
                "n_competitors_scored": len(comps),
                "denominator": "topic" if use_topic else "mention",
                "gold_documents": gold[den],
                "gold_mention_documents": gold["documents"],
                "gold_topic_documents": gold["topic_documents"],
                "gold_covered": gold_covered,
                "clue_verdicts": Counter(c["verdict"] for c in per_clue),
                "n_gold_specific": sum(1 for c in per_clue if c["verdict"] == "gold_specific"),
                "n_gold_leaning": sum(1 for c in per_clue if c["verdict"] == "gold_leaning"),
                "n_favours_competitor": sum(1 for c in per_clue if c["verdict"] == "favours_competitor"),
                "nb_gold_rank": gold_rank,
                "nb_gold_top1": gold_rank == 1,
                "nb_top1_label": ranking[0][1] if ranking else "",
                "nb_ranking_head": [{"label": l, "role": ro, "score": round(s, 3)}
                                    for s, l, ro in ranking[:5]],
                "per_clue": per_clue,
                "method_recall": {m: meth[m]["recall_status"] for m in METHODS},
                "method_correct": {
                    m: (meth[m].get("correct") or {}).get("top1") if meth[m].get("present") else None
                    for m in METHODS
                },
            }
        )

    (args.out_dir / "clue_discriminativeness_48.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True) for r in case_rows) + "\n",
        encoding="utf-8",
    )
    with (args.out_dir / "clue_discriminativeness_48.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(clue_rows[0].keys()))
        w.writeheader()
        w.writerows(clue_rows)

    scored = [r for r in case_rows if r["gold_covered"] and r["n_competitors_scored"]]
    verdicts = Counter(r["verdict"] for r in clue_rows)
    summary = {
        "cases": len(case_rows),
        "cases_scored": len(scored),
        "cases_gold_under_covered": sum(1 for r in case_rows if not r["gold_covered"]),
        "clue_verdicts": dict(verdicts),
        "clue_verdict_share": {k: round(v / len(clue_rows), 3) for k, v in verdicts.items()},
        "cases_with_>=1_gold_specific_clue": sum(1 for r in scored if r["n_gold_specific"]),
        "cases_with_no_gold_leaning_clue": sum(
            1 for r in scored if not r["n_gold_specific"] and not r["n_gold_leaning"]
        ),
        "naive_bayes_gold_top1": sum(1 for r in scored if r["nb_gold_top1"]),
        "naive_bayes_gold_top1_rate": round(
            sum(1 for r in scored if r["nb_gold_top1"]) / len(scored), 3
        ),
        "naive_bayes_gold_top3_rate": round(
            sum(1 for r in scored if (r["nb_gold_rank"] or 99) <= 3) / len(scored), 3
        ),
        "median_competitors_scored": sorted(r["n_competitors_scored"] for r in scored)[len(scored) // 2],
        "denominator_used": dict(Counter(r["denominator"] for r in scored)),
        "naive_bayes_gold_top1_by_denominator": {
            d: round(
                sum(1 for r in scored if r["denominator"] == d and r["nb_gold_top1"])
                / max(1, sum(1 for r in scored if r["denominator"] == d)),
                3,
            )
            for d in ("topic", "mention")
        },
    }
    deep = [r for r in scored if r["in_deep_review_scope"]]
    if deep:
        summary["deep_review_scope"] = {
            "cases": len(deep),
            "naive_bayes_gold_top1_rate": round(sum(1 for r in deep if r["nb_gold_top1"]) / len(deep), 3),
            "cases_with_>=1_gold_specific_clue": sum(1 for r in deep if r["n_gold_specific"]),
        }
    (args.out_dir / "clue_discriminativeness_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
