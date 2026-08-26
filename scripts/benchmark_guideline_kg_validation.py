#!/usr/bin/env python3
"""Compare full and incremental validation for one accepted extraction delta."""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from hashlib import sha256
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agentclinic_tree_dx.knowledge.guideline_kg_schema import (  # noqa: E402
    ExtractionActivity,
    GraphValidationIndex,
    assert_valid_graph,
    record_to_dict,
)

DEFAULT_GRAPH = (
    ROOT / "data/knowledge_graph/guideline_diagnostic_kg_v0_1/build/graph.internal.jsonl"
)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    position = max(0, min(len(ordered) - 1, round(
        probability * (len(ordered) - 1)
    )))
    return ordered[position]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--graph", type=Path, default=DEFAULT_GRAPH)
    parser.add_argument(
        "--delta", type=Path,
        help="validated JSONL additions from one or more accepted windows",
    )
    parser.add_argument("--delta-limit", type=int, default=1)
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.iterations < 1 or args.delta_limit < 1:
        parser.error("iterations and delta-limit must be positive")

    base = load_jsonl(args.graph)
    if args.delta:
        delta = load_jsonl(args.delta)[:args.delta_limit]
    else:
        delta = [record_to_dict(ExtractionActivity(
            pipeline_name="guideline-kg-validation-benchmark",
            pipeline_version="1",
            extractor_type="deterministic",
            input_sha256=sha256(b"incremental-benchmark").hexdigest(),
            parameters={"synthetic": True},
        ))]

    # Setup validation is outside timed intervals and establishes the explicit
    # prerequisite for an incremental index.
    assert_valid_graph(base)
    incremental = GraphValidationIndex.from_validated_records(base)
    assert_valid_graph([*base, *delta])
    if errors := incremental.validate_delta(delta):
        raise ValueError("benchmark delta is invalid: " + "; ".join(errors))

    full_seconds: list[float] = []
    delta_seconds: list[float] = []
    for _ in range(args.iterations):
        started = time.perf_counter()
        assert_valid_graph([*base, *delta])
        full_seconds.append(time.perf_counter() - started)

        started = time.perf_counter()
        errors = incremental.validate_delta(delta)
        delta_seconds.append(time.perf_counter() - started)
        if errors:
            raise AssertionError(errors)

    full_median = statistics.median(full_seconds)
    delta_median = statistics.median(delta_seconds)
    result = {
        "base_records": len(base),
        "delta_records": len(delta),
        "iterations": args.iterations,
        "full_validation_seconds": full_seconds,
        "incremental_validation_seconds": delta_seconds,
        "full_median_seconds": full_median,
        "incremental_median_seconds": delta_median,
        "full_p95_seconds": percentile(full_seconds, 0.95),
        "incremental_p95_seconds": percentile(delta_seconds, 0.95),
        "median_speedup": full_median / max(delta_median, 1e-12),
        "semantic_contract": (
            "full-valid immutable base; exact same delta accepted by full and "
            "incremental validators; final full validation remains mandatory"
        ),
    }
    rendered = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
