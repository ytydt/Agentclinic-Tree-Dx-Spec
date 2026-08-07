#!/usr/bin/env python3
"""Four-level oracle funnel for hierarchical diagnosis (diagnostic upper bounds).

Injects gold only at the named interface. Does NOT compete with runnable baselines.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "paper"))

import baseline_common as bc  # noqa: E402
import baseline_mapper_score as mapper_score  # noqa: E402
from agentclinic_tree_dx.answer_projection_mapper import (  # noqa: E402
    RelationAwareAnswerMapper,
    load_offline_resolver,
)


ORACLES = (
    "O01-candidate",
    "O02-parent",
    "O03-local-champion",
    "O04-arbiter",
)


def apply_oracle(
    case: Mapping[str, Any],
    oracle: str,
    *,
    baseline_top2: list[str],
) -> list[str]:
    gold = str(case.get("_gold_text") or "").strip()
    if not gold:
        return baseline_top2
    if oracle == "O01-candidate":
        # Ensure gold is present in the ranked list (coverage oracle).
        if gold.casefold() not in {x.casefold() for x in baseline_top2}:
            return [gold, baseline_top2[0] if baseline_top2 else gold]
        return baseline_top2
    if oracle in {"O02-parent", "O03-local-champion", "O04-arbiter"}:
        # Force gold to rank 1 (parent / champion / arbiter oracles).
        rest = [x for x in baseline_top2 if x.casefold() != gold.casefold()]
        return [gold] + rest[:1]
    return baseline_top2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--subset-dir", type=Path, default=bc.DEFAULT_SUBSET)
    parser.add_argument("--baseline-pred", type=Path, required=True,
                        help="predictions.jsonl from a runnable arm")
    parser.add_argument("--runs-root", type=Path, default=bc.DEFAULT_RUNS)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--oracles", default=",".join(ORACLES))
    args = parser.parse_args()

    cases = {
        c["case_id"]: c
        for c in bc.load_runtime_cases(subset_dir=args.subset_dir, limit=args.limit)
    }
    baseline_rows = [
        json.loads(line)
        for line in args.baseline_pred.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    selected = [x.strip() for x in args.oracles.split(",") if x.strip()]
    resolver = load_offline_resolver(ROOT)
    mapper = RelationAwareAnswerMapper(resolver=resolver)

    for oracle in selected:
        out = bc.run_dir(oracle, 1, runs_root=args.runs_root)
        out.mkdir(parents=True, exist_ok=True)
        pred_path = out / "predictions.jsonl"
        if pred_path.exists():
            pred_path.unlink()
        records = []
        for row in baseline_rows:
            case = cases.get(str(row["case_id"]))
            if case is None:
                continue
            top2 = apply_oracle(
                case, oracle, baseline_top2=list(row.get("top2_diagnoses") or []),
            )
            bc.append_jsonl(
                pred_path,
                bc.prediction_row(
                    case,
                    arm=oracle,
                    replicate=1,
                    top2=top2,
                    cost=bc.empty_cost(),
                ),
            )
            scored = mapper_score.score_case_with_mapper(
                case=case,
                top2=top2,
                mapper=mapper,
                mode="deterministic_gold_blind",
            )
            records.append(scored)
        summary = {
            "oracle": oracle,
            "n": len(records),
            "option_top1": (
                round(sum(r["option_top1"] for r in records) / len(records), 4)
                if records else None
            ),
            "option_top2": (
                round(sum(r["option_top2"] for r in records) / len(records), 4)
                if records else None
            ),
            "note": "diagnostic upper bound; do not mix into runnable leaderboard",
        }
        bc.atomic_json(out / "mapper" / "records.json", {
            "summary": summary, "records": records,
        })
        bc.write_manifest(
            out,
            arm=oracle,
            replicate=1,
            subset=args.subset_dir.name,
            model="oracle",
            budget_mode="native",
            extra={"oracle": True},
        )
        print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
