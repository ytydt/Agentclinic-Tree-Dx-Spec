#!/usr/bin/env python3
"""Deterministic post-run analysis for E9 Forest view independence."""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import statistics
import sys
import tarfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from analysis.mechanism_v2.common import ROOT, file_sha256  # noqa: E402
from analysis.mechanism_v2.e9_manual_adjudication import CONTRAST_EFFECTS  # noqa: E402
from analysis.mechanism_v2.online_runner import read_jsonl  # noqa: E402
from analysis.mechanism_v2.runtime_contract import atomic_json  # noqa: E402


OUT = ROOT / "analysis/mechanism_v2/results/E9_view_independence"
CONTRASTS = (
    ("real_views", "role_rotated"),
    ("single_anchor", "duplicate_anchor"),
    ("single_anchor", "real_views"),
    ("duplicate_anchor", "real_views"),
)
PAIR_KEYS = ("V1__V2", "V1__V3", "V2__V3")


def paired_bootstrap(
    rows: Sequence[Mapping[str, Any]],
    left: str,
    right: str,
    *,
    repetitions: int = 10_000,
) -> list[float]:
    """Case bootstrap for the paired right-minus-left strict-hit difference."""
    indexed: dict[str, dict[str, Mapping[str, Any]]] = defaultdict(dict)
    for row in rows:
        indexed[str(row["case_key"])][str(row["arm"])] = row
    pairs = [
        (int(arms[left]["gold_top1"]), int(arms[right]["gold_top1"]))
        for arms in indexed.values()
        if left in arms
        and right in arms
        and bool(arms[left]["success"])
        and bool(arms[right]["success"])
    ]
    if not pairs:
        raise ValueError(f"no served pairs for {left} vs {right}")
    seed_text = f"E9-bootstrap-v1:{left}:{right}:{len(pairs)}"
    seed = int.from_bytes(hashlib.sha256(seed_text.encode("utf-8")).digest()[:8], "big")
    rng = random.Random(seed)
    values: list[float] = []
    for _ in range(repetitions):
        total = 0
        for _case in pairs:
            a, b = pairs[rng.randrange(len(pairs))]
            total += b - a
        values.append(total / len(pairs))
    values.sort()
    return [
        round(values[int(0.025 * repetitions)], 6),
        round(values[int(0.975 * repetitions)], 6),
    ]


def semantic_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    served = [row for row in rows if bool(row.get("success"))]
    failed = [row for row in rows if not bool(row.get("success"))]
    observations = sum(int(row["metrics"]["observation_n"]) for row in served)
    clusters = sum(int(row["metrics"]["cluster_n"]) for row in served)
    compression = [float(row["metrics"]["compression_ratio"]) for row in served]
    pairwise: dict[str, Any] = {}
    for key in PAIR_KEYS:
        values = [float(row["metrics"]["semantic_jaccard_pairs"][key]) for row in served]
        pairwise[key] = {
            "case_mean": round(statistics.fmean(values), 6),
            "case_median": round(statistics.median(values), 6),
        }
    return {
        "n_intention": len(rows),
        "n_served": len(served),
        "n_failed_contract": len(failed),
        "failure_reasons": dict(sorted(Counter(str(row.get("error") or "") for row in failed).items())),
        "served_observation_n": observations,
        "served_cluster_n": clusters,
        "global_cluster_to_observation_ratio": round(clusters / observations, 6),
        "case_mean_compression_ratio": round(statistics.fmean(compression), 6),
        "case_median_compression_ratio": round(statistics.median(compression), 6),
        "cross_view_cluster_n": sum(int(row["metrics"]["cross_view_cluster_n"]) for row in served),
        "all_three_view_cluster_n": sum(int(row["metrics"]["all_three_cluster_n"]) for row in served),
        "pairwise_semantic_jaccard": pairwise,
        "auditor_role": "heterogeneous LLM subcontractor; root manual audit is authoritative",
    }


def construction_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    def describe(values: Sequence[float]) -> dict[str, float]:
        return {
            "mean": round(statistics.fmean(values), 6),
            "median": round(statistics.median(values), 6),
        }

    pairwise: dict[str, Any] = {}
    for field in ("candidate_jaccard_pairs", "evidence_exact_jaccard_pairs"):
        keys = sorted({key for row in rows for key in row[field]})
        pairwise[field] = {
            key: describe([float(row[field][key]) for row in rows]) for key in keys
        }
    return {
        "anchor_assignment": dict(sorted(Counter(str(row["anchor_key"]) for row in rows).items())),
        "pairwise_exact_overlap": pairwise,
        "view_candidate_count": {
            key: describe([float(row["view_candidate_counts"][key]) for row in rows])
            for key in sorted(rows[0]["view_candidate_counts"])
        },
        "view_evidence_count": {
            key: describe([float(row["view_evidence_counts"][key]) for row in rows])
            for key in sorted(rows[0]["view_evidence_counts"])
        },
    }


def capture_decomposition(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    indexed: dict[str, dict[str, Mapping[str, Any]]] = defaultdict(dict)
    for row in rows:
        indexed[str(row["case_key"])][str(row["arm"])] = row
    output: dict[str, Any] = {}
    for family in ("all", "DA", "MCR"):
        cases = [
            arms
            for arms in indexed.values()
            if family == "all" or str(next(iter(arms.values()))["family"]) == family
        ]
        shared = [
            arms for arms in cases
            if bool(arms["single_anchor"]["gold_exposure_hit"])
            and bool(arms["real_views"]["gold_exposure_hit"])
        ]
        real_only = [
            arms for arms in cases
            if not bool(arms["single_anchor"]["gold_exposure_hit"])
            and bool(arms["real_views"]["gold_exposure_hit"])
        ]
        output[family] = {
            "shared_exposure_n": len(shared),
            "shared_exposure_single_top1_n": sum(bool(arms["single_anchor"]["gold_top1"]) for arms in shared),
            "shared_exposure_real_top1_n": sum(bool(arms["real_views"]["gold_top1"]) for arms in shared),
            "shared_exposure_single_only_top1_n": sum(
                bool(arms["single_anchor"]["gold_top1"])
                and not bool(arms["real_views"]["gold_top1"])
                for arms in shared
            ),
            "shared_exposure_real_only_top1_n": sum(
                not bool(arms["single_anchor"]["gold_top1"])
                and bool(arms["real_views"]["gold_top1"])
                for arms in shared
            ),
            "real_only_exposure_n": len(real_only),
            "real_only_exposure_top1_n": sum(bool(arms["real_views"]["gold_top1"]) for arms in real_only),
        }
    return output


def telemetry_summary(out: Path) -> dict[str, Any]:
    components: dict[str, Any] = {}
    totals = Counter()
    missing = 0
    provider_union: set[str] = set()
    for arm in ("real_views", "role_rotated", "single_anchor", "duplicate_anchor"):
        arm_dir = out / "arms" / arm
        telemetry = json.loads((arm_dir / "telemetry_summary.json").read_text(encoding="utf-8"))
        provenance = json.loads((arm_dir / "provenance.json").read_text(encoding="utf-8"))
        components[arm] = {"telemetry": telemetry, "provenance": provenance}
        for key in ("semantic_calls", "physical_attempts", "input_tokens", "output_tokens"):
            totals[key] += int(telemetry.get(key) or 0)
        totals["latency_seconds_sum"] += float(telemetry.get("latency_seconds_sum") or 0.0)
        provider_union.update(str(value) for value in telemetry.get("providers") or [])
        missing += len(provenance.get("telemetry_missing_result_cases") or [])
    semantic_dir = out / "semantic_audit"
    semantic_telemetry = json.loads((semantic_dir / "telemetry_summary.json").read_text(encoding="utf-8"))
    semantic_provenance = json.loads((semantic_dir / "provenance.json").read_text(encoding="utf-8"))
    components["semantic_audit"] = {
        "telemetry": semantic_telemetry,
        "provenance": semantic_provenance,
    }
    for key in ("semantic_calls", "physical_attempts", "input_tokens", "output_tokens"):
        totals[key] += int(semantic_telemetry.get(key) or 0)
    totals["latency_seconds_sum"] += float(semantic_telemetry.get("latency_seconds_sum") or 0.0)
    provider_union.update(str(value) for value in semantic_telemetry.get("providers") or [])
    missing += len(semantic_provenance.get("telemetry_missing_result_cases") or [])
    return {
        "components": components,
        "recorded_totals_lower_bound": {
            "semantic_calls": totals["semantic_calls"],
            "physical_attempts": totals["physical_attempts"],
            "input_tokens": totals["input_tokens"],
            "output_tokens": totals["output_tokens"],
            "latency_seconds_sum": round(totals["latency_seconds_sum"], 6),
        },
        "missing_per_call_telemetry_n": missing,
        "providers": sorted(provider_union),
        "groq_single_point_route": False,
        "totals_are_lower_bounds": bool(missing),
    }


def migrate_safe_exact_endpoint(groups: Mapping[str, Any]) -> dict[str, Any]:
    """Give every active safe-exact metric a self-describing key path.

    The frozen E9 runner called this endpoint ``accuracy`` under a historical
    ``strict`` source field.  Neither term is safe in a final artifact because
    downstream flattening can discard the parent context.  The source JSON is
    retained as provenance; this function creates the only ingestible view.
    """
    key_map = {
        "accuracy_intention": "safe_exact_rate_intention",
        "accuracy_served": "safe_exact_rate_served",
        "accuracy_delta_right_minus_left": "safe_exact_delta_right_minus_left",
        "gold_exposure_rate_served": "safe_exact_reference_exposure_rate_served",
        "exposure_to_top1": "safe_exact_exposure_to_top1_conversion",
    }

    def migrate(node: Any) -> Any:
        if isinstance(node, Mapping):
            return {
                key_map.get(str(key), str(key)): migrate(value)
                for key, value in node.items()
            }
        if isinstance(node, list):
            return [migrate(value) for value in node]
        return node

    migrated = migrate(groups)
    if not isinstance(migrated, dict):
        raise TypeError("E9 safe-exact groups must be an object")
    return migrated


def analysis(out: Path, *, repetitions: int = 10_000) -> dict[str, Any]:
    rows = read_jsonl(out / "case_conditions.jsonl")
    construction = read_jsonl(out / "construction_ledger.jsonl")
    semantic_rows = read_jsonl(out / "semantic_audit/case_results.jsonl")
    base = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    bootstrap: dict[str, Any] = {}
    for family in ("all", "DA", "MCR"):
        subset = rows if family == "all" else [row for row in rows if row["family"] == family]
        bootstrap[family] = {
            f"{left}__to__{right}": paired_bootstrap(
                subset, left, right, repetitions=repetitions
            )
            for left, right in CONTRASTS
        }
    result = {
        "schema": "E9_final_analysis_v2",
        "experiment_id": "E9",
        "n_cases": base["n_cases"],
        "safe_exact_endpoint": migrate_safe_exact_endpoint(base["groups"]),
        "safe_exact_endpoint_provenance": {
            "historical_source_alias": "strict",
            "historical_generic_metric_name": "accuracy",
            "active_metric": "safe_exact",
            "clinical_capability_interpretation_allowed": False,
        },
        "offline_capture": base["offline_capture"],
        "construction": construction_summary(construction),
        "capture_and_selection_decomposition": capture_decomposition(rows),
        "paired_case_bootstrap_delta_95ci": bootstrap,
        "semantic_overlap": semantic_summary(semantic_rows),
        "manual_legacy_mechanism_reclassification": {
            name: {
                "n": len(effects),
                "effect_counts": dict(sorted(Counter(effects.values()).items())),
                "cases": effects,
            }
            for name, effects in CONTRAST_EFFECTS.items()
        },
        "endpoint_migration_contract": {
            "clinical_complete_measured": False,
            "compatible_partial_measured": False,
            "complete_or_compatible_partial_measured": False,
            "full_blinded_root_census": False,
            "ability_ranking_allowed": False,
        },
        "telemetry": telemetry_summary(out),
        "interpretation_guards": [
            "Development/mechanism sample; no confirmation-performance claim.",
            "Safe-exact is a conservative lower bound; the legacy root scope/surface labels are not a complete/partial clinical endpoint.",
            "Fresh stochastic calls mean flips under label/repetition interventions diagnose perturbation sensitivity but cannot all be assigned uniquely to the intervention.",
            "Semantic clustering is a heterogeneous-LLM subcontractor output and is checked by root manual audit.",
            "Per-call telemetry gaps make token, attempt, provider and latency totals lower bounds.",
        ],
    }
    atomic_json(out / "analysis_summary.json", result)
    return result


def package(out: Path) -> Path:
    names = [
        "PREREGISTRATION.md",
        "INCIDENTS.md",
        "MANUAL_AUDIT_PROTOCOL.md",
        "REPORT.md",
        "BUNDLE_README.md",
        "preregistration.json",
        "environment.json",
        "construction_ledger.jsonl",
        "case_conditions.jsonl",
        "case_summary.csv",
        "summary.json",
        "analysis_summary.json",
        "manifests.json",
        "manual_audit_selection.json",
        "manual_audit_queue.jsonl",
        "manual_audit_queue_provenance.json",
        "manual_audit.jsonl",
        "manual_audit_summary.json",
        "manual_audit_manifest.json",
        "manual_audit_run.log",
        "semantic_audit/preregistration.json",
        "semantic_audit/environment.json",
        "semantic_audit/case_results.jsonl",
        "semantic_audit/provenance.json",
        "semantic_audit/run.log",
        "semantic_audit/telemetry_summary.json",
    ]
    paths = [out / name for name in names]
    missing = [str(path.relative_to(out)) for path in paths if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"final analysis package incomplete: {missing}")
    archive_path = out / "E9_FINAL_ANALYSIS_BUNDLE.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        for path in sorted(paths, key=lambda value: str(value.relative_to(out))):
            archive.add(path, arcname=str(path.relative_to(out)), recursive=False)
    digest = file_sha256(archive_path)
    (out / f"{archive_path.name}.sha256").write_text(
        f"{digest}  {archive_path.name}\n", encoding="utf-8"
    )
    return archive_path


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--bootstrap-repetitions", type=int, default=10_000)
    parser.add_argument("--package", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = analysis(args.out.resolve(), repetitions=args.bootstrap_repetitions)
    if args.package:
        print(package(args.out.resolve()))
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
