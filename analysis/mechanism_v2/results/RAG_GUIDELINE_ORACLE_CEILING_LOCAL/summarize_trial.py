#!/usr/bin/env python3
"""Collect every arm of the end-to-end trial into one table."""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
LEDGER = ROOT / "RAG_GUIDELINE_ORACLE_CEILING_LOCAL"

ARMS = [
    ("k30clean", "retrieved k=30, sum scoring, strict join"),
    ("k30clean_loose", "retrieved k=30, sum scoring, loose join"),
    ("k30clean_disc", "retrieved k=30, exclusive-feature scoring, strict join"),
    ("k30clean_loose_disc", "retrieved k=30, exclusive-feature scoring, loose join"),
    ("k30oracleclean", "oracle-injected, sum scoring, strict join"),
    ("k30oracleclean_loose", "oracle-injected, sum scoring, loose join"),
    ("k30oracleclean_disc", "oracle-injected, exclusive-feature scoring, strict join"),
    ("k30oracleclean_loose_disc", "oracle-injected, exclusive-feature scoring, loose join"),
]

STAGE_ORDER = ["S0_candidate", "S1_retrieval", "S2_extraction", "S3_relation",
               "S4_subject_bind", "S5a_vignette_lacks_finding",
               "S5b_case_extractor_missed", "S6_join", "S7_engine"]


def main() -> int:
    tasks = {t["case_key"]: t for t in json.loads((LEDGER / "trial_tasks_11.json").read_text("utf-8"))}
    trace = json.loads((LEDGER / "trial_failure_trace_k30oracleclean.json").read_text("utf-8"))
    by_case: dict[str, list[dict]] = {}
    for r in trace:
        by_case.setdefault(r["case"], []).append(r)

    engines = {}
    for arm, _ in ARMS:
        engines[arm] = {e["case_key"]: e for e in
                        json.loads((LEDGER / f"trial_engine_{arm}.json").read_text("utf-8"))}

    rows = []
    for key, task in tasks.items():
        stages = [r["stage_lost"] for r in by_case[key]]
        worst = min(stages, key=lambda s: STAGE_ORDER.index(s))
        row = {
            "case": key,
            "gold": task["gold"],
            "n_candidates": task["n_candidates"],
            "gold_in_candidate_set": task["gold_in_candidate_set"],
            "gold_labels_in_set": "; ".join(task["gold_labels_in_set"]),
            "n_assertions": len(task["assertions"]),
            "earliest_stage_lost": worst,
            "stages": " ".join(f"{s}={c}" for s, c in
                               sorted(Counter(stages).items(), key=lambda x: STAGE_ORDER.index(x[0]))),
            "reached_engine": sum(1 for s in stages if s == "S7_engine"),
            "methods_correct_of_4": task["methods_correct_of_4"],
        }
        for arm, _ in ARMS:
            e = engines[arm][key]
            row[f"{arm}__top1"] = e["top1"]
            row[f"{arm}__gold_rank"] = e["gold_rank"]
            row[f"{arm}__ok"] = int(e["top1_is_gold"])
        rows.append(row)

    out_csv = LEDGER / "trial_summary_11.csv"
    with out_csv.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    summary = {
        "arms": {arm: {
            "desc": desc,
            "top1_gold": sum(r[f"{arm}__ok"] for r in rows),
            "gold_top3": sum(1 for r in rows if (r[f"{arm}__gold_rank"] or 99) <= 3),
            "median_gold_rank": sorted(r[f"{arm}__gold_rank"] or 99 for r in rows)[len(rows) // 2],
        } for arm, desc in ARMS},
        "stage_census_oracle_arm": dict(Counter(r["stage_lost"] for r in trace)),
        "n_cases": len(rows),
        "n_assertions": len(trace),
    }
    (LEDGER / "trial_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False),
                                               encoding="utf-8")

    print(f"{'arm':32s} {'top1':>5s} {'gold<=3':>8s} {'med rank':>9s}   description")
    for arm, desc in ARMS:
        s = summary["arms"][arm]
        print(f"{arm:32s} {s['top1_gold']:2d}/11 {s['gold_top3']:6d}/11 {s['median_gold_rank']:9d}   {desc}")
    print("\nstage at which the 26 hand-audited assertions are lost (oracle-injected arm):")
    for s in STAGE_ORDER:
        n = summary["stage_census_oracle_arm"].get(s, 0)
        if n:
            print(f"  {s:28s} {n:2d}")
    print(f"\nwrote {out_csv} and trial_summary.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
