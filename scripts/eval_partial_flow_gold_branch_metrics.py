"""Evaluate gold-branch existence and posterior rank on partial-flow traces."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
DEFAULT_RUN = (
    ROOT / "logs" / "partial_flow_talp17" / "talp17_p5_g2ur_partial_20260712"
)
def _make_strict_gold_judge(model: str):
    import requests
    from agentclinic_tree_dx import llm_client

    key = (
        os.environ.get("OPENROUTER_API_KEY")
        or os.environ.get("OPENROUTER_API_KEY2")
        or llm_client._OPENROUTER_KEY2
    )
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY is required for gold-branch judging")
    session = llm_client._openrouter_session
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    system = (
        "Determine whether a specific gold diagnosis is EXPLICITLY represented by "
        "one numbered diagnostic branch. Accept a canonical synonym or a label that "
        "clearly includes that exact diagnosis/subtype. Do NOT map it merely to a "
        "broad same-organ family, a sibling diagnosis, or an 'other' bucket. If no "
        "branch explicitly represents the gold diagnosis, return -1. Return strict "
        'JSON only: {"index": <integer>}.'
    )

    def judge(gold: str, labels: list[str]) -> int:
        numbered = "\n".join(f"{index}: {label}" for index, label in enumerate(labels))
        for attempt in range(4):
            try:
                response = session.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers=headers,
                    json={
                        "model": model,
                        "temperature": 0.0,
                        "messages": [
                            {"role": "system", "content": system},
                            {
                                "role": "user",
                                "content": f"Gold diagnosis: {gold}\nBranches:\n{numbered}",
                            },
                        ],
                    },
                    timeout=90,
                )
                text = response.json()["choices"][0]["message"]["content"]
                if not isinstance(text, str):
                    raise ValueError("judge returned empty content")
                start, end = text.find("{"), text.rfind("}")
                result = json.loads(text[start:end + 1])
                return int(result.get("index", -1))
            except (
                OSError,
                ValueError,
                TypeError,
                KeyError,
                AttributeError,
                requests.RequestException,
            ):
                time.sleep(2 * (attempt + 1))
        return -1

    return judge


def _residual(label: str) -> bool:
    text = (label or "").strip().lower()
    return (
        text in {"other", "miscellaneous", "residual"}
        or "unrefined" in text
        or ("other" in text and any(x in text for x in ("process", "cause", "disease")))
    )


def _rank(branches: list[dict[str, Any]], index: int) -> int | None:
    if not 0 <= index < len(branches):
        return None
    ordered = sorted(
        range(len(branches)),
        key=lambda i: (-float(branches[i].get("posterior") or 0.0), i),
    )
    return ordered.index(index) + 1


def evaluate_record(
    record: dict[str, Any],
    judge: Callable[[str, list[str]], int],
) -> dict[str, Any]:
    trace = record["trace"]
    gold = record["gold_diagnosis"]
    l1 = list(trace.get("l1_tree") or [])
    l2 = list(trace.get("l2_tree") or [])
    l1_index = int(record.get("metrics", {}).get("l1_assigned_index", -1))
    if not 0 <= l1_index < len(l1):
        l1_index = judge(gold, [row.get("label", "") for row in l1])
    l2_index = judge(gold, [row.get("label", "") for row in l2])
    l1_rank = _rank(l1, l1_index)
    l2_rank = _rank(l2, l2_index)
    l1_branch = l1[l1_index] if l1_rank is not None else None
    l2_branch = l2[l2_index] if l2_rank is not None else None
    path_consistent = bool(
        l1_branch and l2_branch and l2_branch.get("parent") == l1_branch.get("id")
    )
    return {
        "profile": record["profile"],
        "case_id": record["case_id"],
        "gold_diagnosis": gold,
        "posterior_checkpoint": "after_turn_1_update_before_turn_2_update",
        "l1": {
            "exists": l1_branch is not None,
            "branch_id": l1_branch.get("id") if l1_branch else None,
            "label": l1_branch.get("label") if l1_branch else None,
            "posterior": l1_branch.get("posterior") if l1_branch else None,
            "rank": l1_rank,
            "top1": l1_rank == 1,
            "residual": _residual(l1_branch.get("label", "")) if l1_branch else None,
            "branch_count": len(l1),
        },
        "l2": {
            "exists": l2_branch is not None,
            "branch_id": l2_branch.get("id") if l2_branch else None,
            "label": l2_branch.get("label") if l2_branch else None,
            "posterior": l2_branch.get("posterior") if l2_branch else None,
            "rank": l2_rank,
            "top1": l2_rank == 1,
            "residual": _residual(l2_branch.get("label", "")) if l2_branch else None,
            "branch_count": len(l2),
            "parent_id": l2_branch.get("parent") if l2_branch else None,
        },
        "gold_path_consistent": path_consistent,
    }


def _aggregate(rows: list[dict[str, Any]], level: str) -> dict[str, Any]:
    metrics = [row[level] for row in rows]
    present = [item for item in metrics if item["exists"]]
    ranks = [int(item["rank"]) for item in present]
    total = len(metrics)
    return {
        "cases": total,
        "existence_rate": len(present) / total if total else None,
        "structured_existence_rate": (
            sum(not item["residual"] for item in present) / total if total else None
        ),
        "posterior_top1_rate": (
            sum(item["top1"] for item in present) / total if total else None
        ),
        "posterior_top3_rate": (
            sum(item["rank"] <= 3 for item in present) / total if total else None
        ),
        "posterior_top5_rate": (
            sum(item["rank"] <= 5 for item in present) / total if total else None
        ),
        "mrr": sum(1.0 / rank for rank in ranks) / total if total else None,
        "mean_rank_when_present": statistics.mean(ranks) if ranks else None,
        "median_rank_when_present": statistics.median(ranks) if ranks else None,
        "rank_distribution": {
            str(rank): sum(value == rank for value in ranks)
            for rank in sorted(set(ranks))
        },
    }


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    def block(items: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "l1": _aggregate(items, "l1"),
            "l2": _aggregate(items, "l2"),
            "gold_path_consistency_rate": (
                sum(row["gold_path_consistent"] for row in items) / len(items)
                if items else None
            ),
        }

    profiles = sorted({row["profile"] for row in rows})
    result = {
        "schema_version": 1,
        "posterior_checkpoint": "after_turn_1_update_before_turn_2_update",
        "overall": block(rows),
        "by_profile": {
            profile: block([row for row in rows if row["profile"] == profile])
            for profile in profiles
        },
    }
    if set(profiles) == {"p5_headline", "g2ur"}:
        paired = {}
        indexed = {
            (row["profile"], row["case_id"]): row
            for row in rows
        }
        case_ids = sorted({
            row["case_id"] for row in rows
            if ("p5_headline", row["case_id"]) in indexed
            and ("g2ur", row["case_id"]) in indexed
        })
        for level in ("l1", "l2"):
            rank_deltas = []
            improved = worse = tied = 0
            top1_gain = top1_loss = top1_tie = 0
            existence_gain = existence_loss = existence_tie = 0
            for case_id in case_ids:
                p5 = indexed[("p5_headline", case_id)][level]
                g2 = indexed[("g2ur", case_id)][level]
                if p5["rank"] is not None and g2["rank"] is not None:
                    delta = int(g2["rank"]) - int(p5["rank"])
                    rank_deltas.append(delta)
                    improved += delta < 0
                    worse += delta > 0
                    tied += delta == 0
                top_delta = int(g2["top1"]) - int(p5["top1"])
                top1_gain += top_delta > 0
                top1_loss += top_delta < 0
                top1_tie += top_delta == 0
                exists_delta = int(g2["exists"]) - int(p5["exists"])
                existence_gain += exists_delta > 0
                existence_loss += exists_delta < 0
                existence_tie += exists_delta == 0
            paired[level] = {
                "paired_cases": len(case_ids),
                "rank_comparable_cases": len(rank_deltas),
                "mean_rank_delta_g2ur_minus_p5": (
                    statistics.mean(rank_deltas) if rank_deltas else None
                ),
                "rank_improved_worse_tied": [improved, worse, tied],
                "top1_gain_loss_tie": [top1_gain, top1_loss, top1_tie],
                "existence_gain_loss_tie": [
                    existence_gain, existence_loss, existence_tie
                ],
            }
        result["paired_descriptive"] = paired
    return result


def run(
    run_dir: Path,
    *,
    model: str,
    judge_factory: Callable[[str], Callable[[str, list[str]], int]] | None = None,
) -> dict[str, Any]:
    records = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((run_dir / "traces").glob("*.json"))
    ]
    records = [row for row in records if row.get("status") == "OK"]
    judge = (judge_factory or _make_strict_gold_judge)(model)
    cache_path = run_dir / "gold_branch_judge_cache.json"
    try:
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        cache = {}

    def save_cache() -> None:
        temp = cache_path.with_suffix(".json.tmp")
        temp.write_text(
            json.dumps(cache, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        temp.replace(cache_path)

    rows = []
    for record in records:
        def cached_judge(gold: str, labels: list[str]) -> int:
            digest = hashlib.sha256(
                json.dumps(labels, ensure_ascii=False).encode()
            ).hexdigest()[:16]
            key = f"strict_l2_v1::{record['profile']}::{record['case_id']}::{digest}"
            if key not in cache:
                cache[key] = int(judge(gold, labels))
                save_cache()
            return int(cache[key])

        rows.append(evaluate_record(record, cached_judge))
    try:
        pipeline_metrics = json.loads(
            (run_dir / "summary.json").read_text(encoding="utf-8")
        )
    except (OSError, ValueError, TypeError):
        pipeline_metrics = None
    payload = {
        **summarize(rows),
        "pipeline_metrics": pipeline_metrics,
        "records": rows,
    }
    output = run_dir / "gold_branch_metrics.json"
    temp = output.with_suffix(".json.tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(output)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN)
    parser.add_argument(
        "--model", default="meta-llama/llama-3.3-70b-instruct"
    )
    args = parser.parse_args()
    payload = run(args.run_dir, model=args.model)
    print(json.dumps(payload["overall"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
