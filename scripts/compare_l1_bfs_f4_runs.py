#!/usr/bin/env python3
"""Compare uncached F4 reruns with the frozen F8-derived F4 prefix."""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import statistics
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parent.parent


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    os.replace(temp, path)


def _snapshot(trace: Mapping[str, Any], round_number: int) -> Mapping[str, Any]:
    return next(
        row
        for row in trace.get("posterior_trajectory") or ()
        if int(row.get("round") or 0) == round_number
    )


def _rank(snapshot: Mapping[str, Any], branch_id: str | None) -> int | None:
    if not branch_id:
        return None
    return next(
        (
            index
            for index, row in enumerate(snapshot.get("posteriors") or (), start=1)
            if row.get("id") == branch_id
        ),
        None,
    )


def _view(
    *,
    run: str,
    case_id: str,
    trace: Mapping[str, Any],
    gold_branch_id: str | None,
    round_number: int = 4,
) -> dict[str, Any]:
    snapshot = _snapshot(trace, round_number)
    rows = list(snapshot.get("posteriors") or ())
    rank = _rank(snapshot, gold_branch_id)
    allocation = list(trace.get("rounds") or ())[:round_number]
    selected = list(trace.get("selected_fact_ids") or ())[:round_number]
    return {
        "run": run,
        "case_id": case_id,
        "gold_branch_id": gold_branch_id,
        "gold_rank": rank,
        "gold_top1": rank == 1,
        "gold_top3": rank is not None and rank <= 3,
        "mrr": 1 / rank if rank else 0.0,
        "facts": round_number,
        "leader_id": rows[0].get("id") if rows else None,
        "selected_fact_ids": selected,
        "rule_in": [row.get("rule_in_ranked") or [] for row in allocation],
        "rule_out": [row.get("rule_out_ranked") or [] for row in allocation],
    }


def load_baseline(full_trace_dir: Path) -> list[dict[str, Any]]:
    output = []
    for path in sorted(full_trace_dir.glob("p5_headline__*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("status") != "OK":
            continue
        output.append(_view(
            run="baseline_f8_prefix_f4",
            case_id=record["case_id"],
            trace=record["trace"],
            gold_branch_id=record.get("gold_branch_id"),
        ))
    return output


def load_rerun(run_dir: Path) -> list[dict[str, Any]]:
    output = []
    for path in sorted((run_dir / "traces").glob(
        "B__B1__p5_headline__branch__*.json"
    )):
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("status") != "OK":
            continue
        output.append(_view(
            run=run_dir.name,
            case_id=record["case_id"],
            trace=record["trace"],
            gold_branch_id=record["gold"]["final"].get("branch_id"),
        ))
    return output


def _quorum_round(trace: Mapping[str, Any]) -> int:
    raw = next(
        (
            dict(row) for row in trace.get("stop_snapshots") or ()
            if int(row.get("micro_round") or 0) == 2
        ),
        None,
    )
    if raw is None:
        return 4
    leader_id = str(raw.get("top1_id") or "")
    cycle_rows = list(trace.get("rounds") or ())[:2]
    support = sum(
        leader_id in (row.get("rule_in_ranked") or ()) for row in cycle_rows
    )
    against = sum(
        leader_id in (row.get("rule_out_ranked") or ()) for row in cycle_rows
    )
    return (
        2
        if (
            support >= 2
            and against == 0
            and int(raw.get("top1_stable_cycles") or 0) == 0
            and float(raw.get("margin_z") or 0.0) >= math.log(1.5)
        )
        else 4
    )


def load_rerun_quorum(run_dir: Path) -> list[dict[str, Any]]:
    output = []
    for path in sorted((run_dir / "traces").glob(
        "B__B1__p5_headline__branch__*.json"
    )):
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("status") != "OK":
            continue
        output.append(_view(
            run=f"{run_dir.name}__S5",
            case_id=record["case_id"],
            trace=record["trace"],
            gold_branch_id=record["gold"]["final"].get("branch_id"),
            round_number=_quorum_round(record["trace"]),
        ))
    return output


def load_adaptive_rerun(
    run_dir: Path,
    *,
    quorum: bool = False,
) -> list[dict[str, Any]]:
    output = []
    for path in sorted((run_dir / "full_traces").glob("p5_headline__*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("status") != "OK":
            continue
        round_number = _quorum_round(record["trace"]) if quorum else 4
        output.append(_view(
            run=f"{run_dir.name}{'__S5' if quorum else ''}",
            case_id=record["case_id"],
            trace=record["trace"],
            gold_branch_id=record.get("gold_branch_id"),
            round_number=round_number,
        ))
    return output


def metric_block(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "cases": len(rows),
        "gold_rank_at_1": statistics.mean(
            bool(row["gold_top1"]) for row in rows
        ) if rows else 0.0,
        "top3": statistics.mean(
            bool(row["gold_top3"]) for row in rows
        ) if rows else 0.0,
        "mrr": statistics.mean(float(row["mrr"]) for row in rows) if rows else 0.0,
        "mean_rank": statistics.mean(
            row["gold_rank"] for row in rows if row["gold_rank"] is not None
        ) if any(row["gold_rank"] is not None for row in rows) else None,
        "mean_facts": statistics.mean(
            float(row["facts"]) for row in rows
        ) if rows else None,
    }


def agreement(
    left: Sequence[Mapping[str, Any]],
    right: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    lmap = {row["case_id"]: row for row in left}
    rmap = {row["case_id"]: row for row in right}
    case_ids = sorted(set(lmap) & set(rmap))
    fields = {
        "leader": "leader_id",
        "gold_rank": "gold_rank",
        "selected_order_exact": "selected_fact_ids",
        "rule_in_exact": "rule_in",
        "rule_out_exact": "rule_out",
    }
    output = {"cases": len(case_ids)}
    for label, field in fields.items():
        matches = sum(lmap[case_id][field] == rmap[case_id][field] for case_id in case_ids)
        output[label] = {
            "matches": matches,
            "rate": matches / len(case_ids) if case_ids else None,
        }
    output["selected_jaccard_mean"] = statistics.mean(
        len(set(lmap[case_id]["selected_fact_ids"]) & set(rmap[case_id]["selected_fact_ids"]))
        / max(
            1,
            len(set(lmap[case_id]["selected_fact_ids"]) | set(rmap[case_id]["selected_fact_ids"])),
        )
        for case_id in case_ids
    ) if case_ids else None
    output["disagreement_cases"] = [
        {
            "case_id": case_id,
            "leader_same": lmap[case_id]["leader_id"] == rmap[case_id]["leader_id"],
            "gold_rank_left": lmap[case_id]["gold_rank"],
            "gold_rank_right": rmap[case_id]["gold_rank"],
            "selected_left": lmap[case_id]["selected_fact_ids"],
            "selected_right": rmap[case_id]["selected_fact_ids"],
        }
        for case_id in case_ids
        if (
            lmap[case_id]["leader_id"] != rmap[case_id]["leader_id"]
            or lmap[case_id]["gold_rank"] != rmap[case_id]["gold_rank"]
            or lmap[case_id]["selected_fact_ids"] != rmap[case_id]["selected_fact_ids"]
        )
    ]
    return output


def paired_bootstrap(
    baseline: Sequence[Mapping[str, Any]],
    candidate: Sequence[Mapping[str, Any]],
    *,
    n_boot: int,
) -> dict[str, Any]:
    left = {row["case_id"]: row for row in baseline}
    right = {row["case_id"]: row for row in candidate}
    case_ids = sorted(set(left) & set(right))
    rng = random.Random(0)
    output = {"cases": len(case_ids)}
    for metric in ("gold_top1", "mrr"):
        deltas = [
            float(right[case_id][metric]) - float(left[case_id][metric])
            for case_id in case_ids
        ]
        samples = [
            statistics.mean(
                float(right[case_id][metric]) - float(left[case_id][metric])
                for case_id in (rng.choice(case_ids) for _ in case_ids)
            )
            for _ in range(n_boot)
        ] if case_ids else []
        samples.sort()
        output[metric] = {
            "delta": statistics.mean(deltas) if deltas else 0.0,
            "ci95": [
                samples[int(0.025 * (len(samples) - 1))],
                samples[int(0.975 * (len(samples) - 1))],
            ] if samples else [None, None],
        }
    return output


def compare(
    baseline_dir: Path,
    rerun_dirs: Sequence[Path],
    adaptive_rerun_dirs: Sequence[Path] = (),
    *,
    n_boot: int,
) -> dict[str, Any]:
    baseline = load_baseline(baseline_dir)
    runs = {"baseline_f8_prefix_f4": baseline}
    for run_dir in rerun_dirs:
        runs[run_dir.name] = load_rerun(run_dir)
    for run_dir in adaptive_rerun_dirs:
        runs[run_dir.name] = load_adaptive_rerun(run_dir)
    quorum_runs = {
        f"{run_dir.name}__S5": load_rerun_quorum(run_dir)
        for run_dir in rerun_dirs
    }
    quorum_runs.update({
        f"{run_dir.name}__S5": load_adaptive_rerun(run_dir, quorum=True)
        for run_dir in adaptive_rerun_dirs
    })
    names = list(runs)
    agreements = {}
    for index, left_name in enumerate(names):
        for right_name in names[index + 1:]:
            agreements[f"{right_name}-vs-{left_name}"] = agreement(
                runs[left_name], runs[right_name],
            )
    return {
        "schema_version": 1,
        "temperature": 0.0,
        "cache_policy": "independent empty cache per rerun",
        "by_run": {
            name: metric_block(rows) for name, rows in runs.items()
        },
        "agreement": agreements,
        "paired_vs_baseline": {
            name: paired_bootstrap(baseline, rows, n_boot=n_boot)
            for name, rows in runs.items()
            if name != "baseline_f8_prefix_f4"
        },
        "s5_quorum_on_independent_reruns": {
            name: {
                "metrics": metric_block(rows),
                "agreement_vs_own_f4": agreement(
                    runs[name.removesuffix("__S5")], rows,
                ),
                "paired_vs_own_f4": paired_bootstrap(
                    runs[name.removesuffix("__S5")], rows, n_boot=n_boot,
                ),
            }
            for name, rows in quorum_runs.items()
        },
        "complete": all(len(rows) == len(baseline) == 17 for rows in runs.values()),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--baseline-dir",
        type=Path,
        default=(
            ROOT / "logs" / "l1_bfs_adaptive_stop"
            / "talp17_adaptive_stop_v1" / "full_traces"
        ),
    )
    parser.add_argument("--rerun-dir", type=Path, action="append", required=True)
    parser.add_argument(
        "--adaptive-rerun-dir", type=Path, action="append", default=[],
    )
    parser.add_argument("--n-boot", type=int, default=5000)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "logs" / "l1_evidence_bfs" / "f4_rerun_comparison.json",
    )
    args = parser.parse_args()
    summary = compare(
        args.baseline_dir,
        args.rerun_dir,
        args.adaptive_rerun_dir,
        n_boot=args.n_boot,
    )
    _atomic_json(args.output, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
