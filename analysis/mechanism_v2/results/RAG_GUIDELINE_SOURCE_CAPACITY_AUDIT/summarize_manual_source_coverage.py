#!/usr/bin/env python3
"""Recompute design-based D0-D3 estimates from the frozen 48-case ledger.

The sampling design is equal allocation (eight cases) within six finite
strata.  This script reports Horvitz-Thompson-equivalent stratified means and
the usual without-replacement variance estimator.  Its normal intervals are
exploratory: the ledger is small and single-reviewed.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable


HERE = Path(__file__).resolve().parent
DEFAULT_LEDGER = HERE / "manual_source_coverage_48.jsonl"
DEFAULT_OUTPUT = HERE / "manual_source_coverage_design_estimates.json"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def wilson(successes: int, n: int, z: float = 1.96) -> list[float]:
    if n == 0:
        return [0.0, 0.0]
    p = successes / n
    denominator = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denominator
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return [max(0.0, center - half), min(1.0, center + half)]


def estimate(
    rows: list[dict[str, Any]], predicate: Callable[[dict[str, Any]], bool]
) -> dict[str, Any]:
    by_stratum: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_stratum[row["sampling_stratum"]].append(row)

    total_population = sum(
        group[0]["sampling_weight"] * len(group) for group in by_stratum.values()
    )
    point = 0.0
    variance = 0.0
    strata: dict[str, Any] = {}
    for stratum, group in sorted(by_stratum.items()):
        n_h = len(group)
        weight = float(group[0]["sampling_weight"])
        n_population = weight * n_h
        observed = [1.0 if predicate(row) else 0.0 for row in group]
        mean_h = sum(observed) / n_h
        sample_variance = (
            sum((value - mean_h) ** 2 for value in observed) / (n_h - 1)
            if n_h > 1
            else 0.0
        )
        share = n_population / total_population
        fpc = 1.0 - n_h / n_population
        point += share * mean_h
        variance += share * share * fpc * sample_variance / n_h
        strata[stratum] = {
            "sample_n": n_h,
            "population_n": n_population,
            "successes": int(sum(observed)),
            "sample_mean": mean_h,
        }

    standard_error = math.sqrt(max(0.0, variance))
    ci = [
        max(0.0, point - 1.96 * standard_error),
        min(1.0, point + 1.96 * standard_error),
    ]
    successes = sum(bool(predicate(row)) for row in rows)
    return {
        "weighted_proportion": point,
        "design_standard_error": standard_error,
        "design_normal_ci95": ci,
        "unweighted_count": successes,
        "unweighted_proportion": successes / len(rows),
        "unweighted_wilson_ci95": wilson(successes, len(rows)),
        "strata": strata,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    rows = read_jsonl(args.ledger)
    if len(rows) != 48:
        raise ValueError(f"expected 48 rows, found {len(rows)}")
    if len({row["case_key"] for row in rows}) != len(rows):
        raise ValueError("duplicate case_key in manual ledger")
    strata = Counter(row["sampling_stratum"] for row in rows)
    if len(strata) != 6 or set(strata.values()) != {8}:
        raise ValueError(f"expected six strata of eight rows, found {strata}")
    for row in rows:
        expected_probability = 1.0 / float(row["sampling_weight"])
        if not math.isclose(
            float(row["sampling_probability"]), expected_probability, rel_tol=0, abs_tol=1e-12
        ):
            raise ValueError(f"weight/probability mismatch: {row['case_key']}")

    grade_names = {
        "D0": "D0_absent",
        "D1": "D1_parent_component_or_list_only",
        "D2": "D2_direct_but_partial_or_general",
        "D3": "D3_direct_vignette_matched",
    }

    def support_prefix(row: dict[str, Any]) -> str:
        return str(row["diagnostic_support"]).split("_", 1)[0]

    output: dict[str, Any] = {
        "schema_version": "manual-source-coverage-design-estimates-v1",
        "ledger": args.ledger.name,
        "n": len(rows),
        "sampling_design": "six-stratum SRSWOR, eight cases per stratum",
        "variance": (
            "sum_h (N_h/N)^2 * (1-n_h/N_h) * s_h^2/n_h; "
            "95% CI is point +/- 1.96 SE, clipped to [0,1]"
        ),
        "warning": (
            "Exploratory design-based normal intervals from a small, single-reviewed ledger; "
            "not a substitute for expanded double clinical review."
        ),
        "overall": {},
        "by_family": {},
    }
    for grade, label in grade_names.items():
        output["overall"][label] = estimate(rows, lambda row, grade=grade: support_prefix(row) == grade)
    output["overall"]["D2_or_D3"] = estimate(
        rows, lambda row: support_prefix(row) in {"D2", "D3"}
    )

    for family in ("DA", "MCR"):
        subset = [row for row in rows if row["family"] == family]
        output["by_family"][family] = {
            label: estimate(subset, lambda row, grade=grade: support_prefix(row) == grade)
            for grade, label in grade_names.items()
        }
        output["by_family"][family]["D2_or_D3"] = estimate(
            subset, lambda row: support_prefix(row) in {"D2", "D3"}
        )

    args.out.write_text(
        json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(output["overall"], ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
