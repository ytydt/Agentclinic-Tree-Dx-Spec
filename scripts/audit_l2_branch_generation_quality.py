#!/usr/bin/env python3
"""Post-generation clinical quality audit for frozen C/A/B L2 trees.

The audit is deliberately separate from generation and downstream ranking.
Human review is deduplicated by ``case + leaf label + parent label`` and then
projected back onto every frozen leaf occurrence.  Gold diagnoses are not used
to assign quality labels.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import eval_l2_branch_generation_ab as ab  # noqa: E402


SCHEMA_VERSION = 1
PROTOCOL_VERSION = 1
ARMS = ("C", "A", "B")
DEFAULT_AB_OUTPUT = ROOT / "logs" / "l2_branch_generation_ab_v1"
DEFAULT_FIXTURE = ROOT / "eval_fixtures" / "l2_branch_generation_quality_audit_v1.json"
DEFAULT_OUTPUT = ROOT / "logs" / "l2_branch_generation_quality_audit_v1"
DEFAULT_CHUNKS = DEFAULT_OUTPUT / "adjudication_chunks"
DEFAULT_CORRECTIONS = DEFAULT_OUTPUT / "adjudication_corrections_review.json"
DEFAULT_HYBRID_FIXTURE = (
    ROOT / "eval_fixtures" / "l2_targeted_gapfill_hybrid_gold_v1.json"
)
QUALITY_METRICS = (
    "leaf_specific_rate",
    "leaf_parent_invalid_rate",
    "leaf_semantic_duplicate_rate",
    "leaf_clean_rate",
    "semantic_duplicate_excess_rate",
)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _atomic_json(path: Path, payload: Any) -> None:
    ab._atomic_json(path, payload)


def _canonical(value: Any) -> str:
    return " ".join(str(value or "").casefold().split())


def _unit_key(case_id: str, leaf_label: str, parent_label: str) -> str:
    payload = "\x1f".join((
        _canonical(case_id), _canonical(leaf_label), _canonical(parent_label),
    ))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]


def _trace_path(
    ab_output: Path, arm: str, replicate: int, case_id: str,
) -> Path:
    return (
        ab_output / "generation" / "traces" / arm
        / f"r{replicate:02d}__{case_id}.json"
    )


def _manifest(ab_output: Path) -> dict[str, Any]:
    return _read_json(ab_output / "generation" / "manifest.json")


def _manifest_cases(manifest: Mapping[str, Any]) -> list[str]:
    return sorted({
        str(key).rsplit("/", 1)[-1]
        for key in (manifest.get("tree_hashes") or {})
    })


def _leaf_rows(trace: Mapping[str, Any]) -> list[dict[str, Any]]:
    branches = trace["tree"]["branches"]
    rows = []
    for branch_id, branch in sorted(branches.items()):
        if int(branch.get("level") or 0) != 2:
            continue
        parent_id = str(branch.get("parent") or "")
        parent = branches.get(parent_id) or {}
        rows.append({
            "branch_id": str(branch_id),
            "leaf_label": str(branch.get("label") or ""),
            "parent_id": parent_id,
            "parent_label": str(parent.get("label") or ""),
            "level_role": str(branch.get("level_role") or ""),
        })
    return rows


def build_units(ab_output: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest = _manifest(ab_output)
    units: dict[str, dict[str, Any]] = {}
    for arm in ARMS:
        for replicate in range(1, int(manifest["replicates"]) + 1):
            for case_id in _manifest_cases(manifest):
                trace = _read_json(_trace_path(ab_output, arm, replicate, case_id))
                ab.validate_generation_trace(trace)
                for leaf in _leaf_rows(trace):
                    unit_id = _unit_key(
                        case_id, leaf["leaf_label"], leaf["parent_label"],
                    )
                    unit = units.setdefault(unit_id, {
                        "unit_id": unit_id,
                        "case_id": case_id,
                        "leaf_label": leaf["leaf_label"],
                        "parent_label": leaf["parent_label"],
                        "observed_level_roles": [],
                        "occurrences": [],
                        "is_specific_disease": None,
                        "is_parent_valid": None,
                        "semantic_cluster_id": "",
                        "rationale": "",
                    })
                    if (
                        _canonical(unit["leaf_label"]) != _canonical(leaf["leaf_label"])
                        or _canonical(unit["parent_label"])
                        != _canonical(leaf["parent_label"])
                    ):
                        raise ValueError(f"unit hash collision: {unit_id}")
                    unit["observed_level_roles"].append(leaf["level_role"])
                    unit["occurrences"].append({
                        "arm": arm,
                        "replicate": replicate,
                        "branch_id": leaf["branch_id"],
                        "tree_hash": trace["tree_hash"],
                    })
    rows = []
    for unit in units.values():
        unit["observed_level_roles"] = sorted(set(unit["observed_level_roles"]))
        unit["occurrences"] = sorted(
            unit["occurrences"],
            key=lambda row: (
                ARMS.index(str(row["arm"])),
                int(row["replicate"]),
                str(row["branch_id"]),
            ),
        )
        rows.append(unit)
    rows.sort(key=lambda row: (
        str(row["case_id"]),
        _canonical(row["parent_label"]),
        _canonical(row["leaf_label"]),
    ))
    return manifest, rows


def write_adjudication_sheet(args: argparse.Namespace) -> dict[str, Any]:
    manifest, units = build_units(args.ab_output)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "asset_kind": "l2_branch_generation_leaf_quality_adjudication",
        "frozen": False,
        "generation_manifest_hash": manifest["manifest_hash"],
        "instructions": {
            "review_unit": (
                "One case + normalized leaf label + normalized parent label. "
                "Do not use gold diagnosis when assigning quality labels."
            ),
            "is_specific_disease": (
                "True only for a concrete named disease, syndrome, or accepted "
                "clinical disease entity; false for broad families, mechanisms, "
                "symptoms, generic buckets, and fallback prose."
            ),
            "is_parent_valid": (
                "True only when the leaf is clinically coherent under the "
                "assigned parent taxonomy label."
            ),
            "semantic_cluster_id": (
                "Within each case, assign the same non-empty stable ID to labels "
                "that are clinically synonymous or one is merely a naming variant "
                "of the other. Different diseases must have different IDs."
            ),
            "rationale": "Briefly justify false labels and non-trivial merges.",
            "freeze": "Set frozen=true only after every unit is reviewed.",
        },
        "units": units,
    }
    _atomic_json(args.fixture, payload)
    return {
        "fixture": str(args.fixture.relative_to(ROOT)),
        "units": len(units),
        "occurrences": sum(len(row["occurrences"]) for row in units),
        "generation_manifest_hash": manifest["manifest_hash"],
    }


def merge_adjudication_chunks(args: argparse.Namespace) -> dict[str, Any]:
    fixture = _read_json(args.fixture)
    expected = {
        str(row["unit_id"]): row for row in fixture.get("units") or ()
    }
    reviewed: dict[str, dict[str, Any]] = {}
    chunk_paths = sorted(args.chunks.glob("*.json"))
    if not chunk_paths:
        raise ValueError(f"no adjudication chunks found in {args.chunks}")
    for path in chunk_paths:
        payload = _read_json(path)
        rows = payload.get("units") if isinstance(payload, Mapping) else payload
        if not isinstance(rows, list):
            raise ValueError(f"{path}: expected a JSON array or object with units")
        for raw in rows:
            row = dict(raw)
            unit_id = str(row.get("unit_id") or "")
            if unit_id not in expected:
                raise ValueError(f"{path}: unknown unit_id {unit_id}")
            if unit_id in reviewed:
                raise ValueError(f"{path}: duplicate reviewed unit_id {unit_id}")
            reviewed[unit_id] = row
    if set(reviewed) != set(expected):
        missing = sorted(set(expected) - set(reviewed))
        raise ValueError(
            f"adjudication chunks incomplete: {len(missing)} missing; "
            f"first={missing[:10]}"
        )
    allowed = {
        "is_specific_disease", "is_parent_valid",
        "semantic_cluster_id", "rationale",
    }
    for unit_id, generated in expected.items():
        source = reviewed[unit_id]
        unknown = set(source) - allowed - {"unit_id"}
        if unknown:
            raise ValueError(f"{unit_id}: unknown adjudication fields {sorted(unknown)}")
        for field in allowed:
            if field not in source:
                raise ValueError(f"{unit_id}: missing adjudication field {field}")
            generated[field] = source[field]
    fixture.update({
        "frozen": True,
        "adjudication_method": (
            "Independent model-assisted clinical review of leaf and parent labels; "
            "gold diagnosis and acceptable-L2 labels withheld."
        ),
        "adjudication_chunk_files": [
            str(path.relative_to(ROOT)) for path in chunk_paths
        ],
    })
    _atomic_json(args.fixture, fixture)
    validate_fixture(fixture, ab_output=args.ab_output)
    return {
        "fixture": str(args.fixture.relative_to(ROOT)),
        "chunks": len(chunk_paths),
        "units": len(reviewed),
        "frozen": True,
    }


def apply_corrections(args: argparse.Namespace) -> dict[str, Any]:
    fixture = _read_json(args.fixture)
    review = _read_json(args.corrections)
    indexed = {
        str(row["unit_id"]): row for row in fixture.get("units") or ()
    }
    corrections = list(review.get("corrections") or ())
    allowed = {
        "is_specific_disease", "is_parent_valid",
        "semantic_cluster_id", "rationale",
    }
    for correction in corrections:
        unit_id = str(correction.get("unit_id") or "")
        field = str(correction.get("field") or "")
        if unit_id not in indexed:
            raise ValueError(f"correction has unknown unit_id: {unit_id}")
        if field not in allowed:
            raise ValueError(f"{unit_id}: correction field is not allowed: {field}")
        current = indexed[unit_id].get(field)
        if current != correction.get("old"):
            raise ValueError(
                f"{unit_id}/{field}: correction old value drift; "
                f"expected={correction.get('old')!r}, actual={current!r}"
            )
        indexed[unit_id][field] = correction.get("new")
    fixture["consistency_review"] = {
        "path": str(args.corrections.relative_to(ROOT)),
        "correction_count": len(corrections),
        "summary": review.get("review_summary"),
    }
    _atomic_json(args.fixture, fixture)
    validate_fixture(fixture, ab_output=args.ab_output)
    return {
        "fixture": str(args.fixture.relative_to(ROOT)),
        "corrections": len(corrections),
        "review": str(args.corrections.relative_to(ROOT)),
    }


def validate_fixture(
    fixture: Mapping[str, Any],
    *,
    ab_output: Path,
) -> dict[str, dict[str, Any]]:
    manifest, expected_units = build_units(ab_output)
    if fixture.get("frozen") is not True:
        raise ValueError("quality adjudication fixture is not frozen")
    if fixture.get("generation_manifest_hash") != manifest["manifest_hash"]:
        raise ValueError("quality fixture generation manifest mismatch")
    indexed: dict[str, dict[str, Any]] = {}
    for raw in fixture.get("units") or ():
        row = dict(raw)
        unit_id = str(row.get("unit_id") or "")
        if not unit_id or unit_id in indexed:
            raise ValueError(f"missing or duplicate quality unit: {unit_id}")
        if not isinstance(row.get("is_specific_disease"), bool):
            raise ValueError(f"{unit_id}: is_specific_disease must be boolean")
        if not isinstance(row.get("is_parent_valid"), bool):
            raise ValueError(f"{unit_id}: is_parent_valid must be boolean")
        cluster = str(row.get("semantic_cluster_id") or "").strip()
        if not cluster:
            raise ValueError(f"{unit_id}: semantic_cluster_id is required")
        row["semantic_cluster_id"] = cluster
        indexed[unit_id] = row
    expected = {str(row["unit_id"]): row for row in expected_units}
    if set(indexed) != set(expected):
        missing = sorted(set(expected) - set(indexed))
        extra = sorted(set(indexed) - set(expected))
        raise ValueError(f"quality units mismatch; missing={missing}, extra={extra}")
    for unit_id, generated in expected.items():
        reviewed = indexed[unit_id]
        for field in (
            "case_id", "leaf_label", "parent_label",
            "observed_level_roles", "occurrences",
        ):
            if reviewed.get(field) != generated.get(field):
                raise ValueError(f"{unit_id}: frozen source field drift: {field}")
    clusters: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    label_clusters: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in indexed.values():
        clusters[(str(row["case_id"]), str(row["semantic_cluster_id"]))].append(row)
        label_clusters[(
            str(row["case_id"]), _canonical(row["leaf_label"]),
        )].add(str(row["semantic_cluster_id"]))
    for (case_id, label), values in label_clusters.items():
        if len(values) != 1:
            raise ValueError(
                f"{case_id}/{label}: identical labels split across semantic clusters"
            )
    for (case_id, cluster), rows in clusters.items():
        labels = {_canonical(row["leaf_label"]) for row in rows}
        if len(labels) > 1 and not any(str(row.get("rationale") or "").strip() for row in rows):
            raise ValueError(
                f"{case_id}/{cluster}: non-trivial semantic merge needs rationale"
            )
    return indexed


def _occurrence_index(
    units: Mapping[str, Mapping[str, Any]],
) -> dict[tuple[str, int, str, str], Mapping[str, Any]]:
    output = {}
    for row in units.values():
        for occurrence in row["occurrences"]:
            key = (
                str(occurrence["arm"]),
                int(occurrence["replicate"]),
                str(row["case_id"]),
                str(occurrence["branch_id"]),
            )
            if key in output:
                raise ValueError(f"duplicate quality occurrence: {key}")
            output[key] = row
    return output


def _rate(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def score_trace(
    trace: Mapping[str, Any],
    occurrence_index: Mapping[tuple[str, int, str, str], Mapping[str, Any]],
    *,
    c_trace: Mapping[str, Any] | None,
) -> dict[str, Any]:
    arm = str(trace["arm"])
    replicate = int(trace["replicate"])
    case_id = str(trace["case_id"])
    reviewed = []
    for leaf in _leaf_rows(trace):
        key = (arm, replicate, case_id, str(leaf["branch_id"]))
        if key not in occurrence_index:
            raise ValueError(f"unreviewed leaf occurrence: {key}")
        reviewed.append((leaf, occurrence_index[key]))
    auditable = [
        row for row in reviewed
        if str(row[0].get("level_role") or "") != "partial_flow_fallback"
    ]
    cluster_counts = Counter(
        str(unit["semantic_cluster_id"]) for _leaf, unit in auditable
    )
    exact_counts = Counter(
        _canonical(leaf["leaf_label"]) for leaf, _unit in auditable
    )
    c_clusters: set[str] = set()
    if c_trace is not None:
        for leaf in _leaf_rows(c_trace):
            if str(leaf.get("level_role") or "") == "partial_flow_fallback":
                continue
            key = ("C", replicate, case_id, str(leaf["branch_id"]))
            if key not in occurrence_index:
                raise ValueError(f"unreviewed C occurrence: {key}")
            c_clusters.add(str(occurrence_index[key]["semantic_cluster_id"]))

    def metrics(rows: Sequence[tuple[Mapping[str, Any], Mapping[str, Any]]]) -> dict[str, Any]:
        n = len(rows)
        specific = sum(bool(unit["is_specific_disease"]) for _leaf, unit in rows)
        invalid = sum(not bool(unit["is_parent_valid"]) for _leaf, unit in rows)
        duplicate = sum(
            cluster_counts[str(unit["semantic_cluster_id"])] > 1
            for _leaf, unit in rows
        )
        exact_duplicate = sum(
            exact_counts[_canonical(leaf["leaf_label"])] > 1
            for leaf, _unit in rows
        )
        row_clusters = Counter(
            str(unit["semantic_cluster_id"]) for _leaf, unit in rows
        )
        row_exact = Counter(_canonical(leaf["leaf_label"]) for leaf, _unit in rows)
        semantic_excess = sum(count - 1 for count in row_clusters.values())
        exact_excess = sum(count - 1 for count in row_exact.values())
        clean = sum(
            bool(unit["is_specific_disease"])
            and bool(unit["is_parent_valid"])
            and cluster_counts[str(unit["semantic_cluster_id"])] == 1
            for _leaf, unit in rows
        )
        return {
            "leaf_count": n,
            "leaf_specific_count": specific,
            "leaf_specific_rate": _rate(specific, n),
            "leaf_parent_invalid_count": invalid,
            "leaf_parent_invalid_rate": _rate(invalid, n),
            "leaf_semantic_duplicate_count": duplicate,
            "leaf_semantic_duplicate_rate": _rate(duplicate, n),
            "leaf_exact_duplicate_count": exact_duplicate,
            "leaf_exact_duplicate_rate": _rate(exact_duplicate, n),
            "semantic_duplicate_excess_count": semantic_excess,
            "semantic_duplicate_excess_rate": _rate(semantic_excess, n),
            "exact_duplicate_excess_count": exact_excess,
            "exact_duplicate_excess_rate": _rate(exact_excess, n),
            "semantic_vs_exact_excess_gap": _rate(
                semantic_excess - exact_excess, n,
            ),
            "leaf_clean_count": clean,
            "leaf_clean_rate": _rate(clean, n),
        }

    full = metrics(auditable)
    novel = [
        row for row in auditable
        if str(row[1]["semantic_cluster_id"]) not in c_clusters
    ] if c_trace is not None else []
    novel_metrics = {
        f"novel_vs_c_{key}": value for key, value in metrics(novel).items()
    }
    return {
        "arm": arm,
        "replicate": replicate,
        "case_id": case_id,
        "tree_hash": trace["tree_hash"],
        "all_l2_count": len(reviewed),
        "fallback_count": len(reviewed) - len(auditable),
        **full,
        **novel_metrics,
    }


def _weighted_cohort(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    total = sum(int(row["leaf_count"]) for row in rows)
    result: dict[str, Any] = {
        "n": len(rows),
        "all_l2_total": sum(int(row.get("all_l2_count") or 0) for row in rows),
        "fallback_total": sum(int(row.get("fallback_count") or 0) for row in rows),
        "leaf_total": total,
    }
    pairs = (
        ("leaf_specific", "leaf_specific_count"),
        ("leaf_parent_invalid", "leaf_parent_invalid_count"),
        ("leaf_semantic_duplicate", "leaf_semantic_duplicate_count"),
        ("leaf_exact_duplicate", "leaf_exact_duplicate_count"),
        ("semantic_duplicate_excess", "semantic_duplicate_excess_count"),
        ("exact_duplicate_excess", "exact_duplicate_excess_count"),
        ("leaf_clean", "leaf_clean_count"),
    )
    for prefix, count_field in pairs:
        count = sum(int(row[count_field]) for row in rows)
        result[f"{prefix}_count"] = count
        result[f"{prefix}_rate"] = _rate(count, total)
    result["semantic_vs_exact_excess_gap"] = (
        result["semantic_duplicate_excess_rate"]
        - result["exact_duplicate_excess_rate"]
    )
    novel_total = sum(int(row["novel_vs_c_leaf_count"]) for row in rows)
    result["novel_vs_c_leaf_total"] = novel_total
    for prefix, count_field in pairs:
        field = f"novel_vs_c_{count_field}"
        count = sum(int(row[field]) for row in rows)
        result[f"novel_vs_c_{prefix}_count"] = count
        result[f"novel_vs_c_{prefix}_rate"] = _rate(count, novel_total)
    result["novel_vs_c_semantic_vs_exact_excess_gap"] = (
        result["novel_vs_c_semantic_duplicate_excess_rate"]
        - result["novel_vs_c_exact_duplicate_excess_rate"]
    )
    return result


def _hybrid_overlap_validation(
    units: Mapping[str, Mapping[str, Any]],
    hybrid_fixture: Path,
) -> dict[str, Any]:
    if not hybrid_fixture.exists():
        return {"available": False}
    fixture = _read_json(hybrid_fixture)
    decisions: dict[tuple[str, str], set[bool]] = defaultdict(set)
    matched_occurrences = 0
    matched_units: set[str] = set()
    for row in fixture.get("cases") or ():
        case_id = str(row.get("case_id") or "")
        l2 = {
            str(item["id"]): item for item in row.get("l2_candidates") or ()
        }
        added_ids = {
            str(item.get("id") if isinstance(item, Mapping) else item)
            for item in row.get("added_candidates") or ()
        }
        specific = {
            str(item.get("id") if isinstance(item, Mapping) else item)
            for item in row.get("added_specific_ids") or ()
        }
        invalid = {
            str(item.get("id") if isinstance(item, Mapping) else item)
            for item in row.get("added_parent_invalid_ids") or ()
        }
        for branch_id in added_ids:
            candidate = l2.get(branch_id)
            if not candidate:
                continue
            unit_id = _unit_key(
                case_id,
                str(candidate.get("label") or ""),
                str(candidate.get("parent_label") or ""),
            )
            unit = units.get(unit_id)
            if unit is None:
                continue
            matched_occurrences += 1
            matched_units.add(unit_id)
            decisions[(unit_id, "is_specific_disease")].add(branch_id in specific)
            decisions[(unit_id, "is_parent_valid")].add(branch_id not in invalid)
    conflicts = sum(len(values) > 1 for values in decisions.values())
    comparisons = {
        field: [
            bool(units[unit_id][field]) == next(iter(values))
            for (unit_id, decision_field), values in decisions.items()
            if decision_field == field and len(values) == 1
        ]
        for field in ("is_specific_disease", "is_parent_valid")
    }
    return {
        "available": True,
        "matched_occurrences": matched_occurrences,
        "matched_units": len(matched_units),
        "hybrid_decision_conflicts": conflicts,
        **{
            f"{field}_agreement": (
                statistics.fmean(values) if values else None
            )
            for field, values in comparisons.items()
        },
        **{
            f"{field}_comparable_units": len(values)
            for field, values in comparisons.items()
        },
    }


def _paired_case_bootstrap(
    rows: Sequence[Mapping[str, Any]],
    treatment: str,
    *,
    n_boot: int,
) -> dict[str, Any]:
    by_arm_case: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        by_arm_case[(str(row["arm"]), str(row["case_id"]))].append(row)
    cases = sorted({
        case_id for arm, case_id in by_arm_case
        if arm == "C" and (treatment, case_id) in by_arm_case
    })
    deltas = {
        metric: [
            statistics.fmean(float(row[metric]) for row in by_arm_case[(treatment, case_id)])
            - statistics.fmean(float(row[metric]) for row in by_arm_case[("C", case_id)])
            for case_id in cases
        ]
        for metric in QUALITY_METRICS
    }
    rng = random.Random(20260717)
    output = {}
    for metric, values in deltas.items():
        samples = []
        if values:
            for _ in range(n_boot):
                samples.append(statistics.fmean(rng.choice(values) for _case in cases))
            samples.sort()
        output[metric] = {
            "cases": len(cases),
            "delta": statistics.fmean(values) if values else None,
            "ci95": (
                [samples[int(0.025 * (len(samples) - 1))],
                 samples[int(0.975 * (len(samples) - 1))]]
                if samples else [None, None]
            ),
        }
    return output


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0]) if rows else []
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def evaluate(args: argparse.Namespace) -> dict[str, Any]:
    fixture = _read_json(args.fixture)
    units = validate_fixture(fixture, ab_output=args.ab_output)
    occurrence_index = _occurrence_index(units)
    manifest = _manifest(args.ab_output)
    rows = []
    for arm in ARMS:
        for replicate in range(1, int(manifest["replicates"]) + 1):
            for case_id in _manifest_cases(manifest):
                trace = _read_json(
                    _trace_path(args.ab_output, arm, replicate, case_id)
                )
                c_trace = (
                    None if arm == "C" else _read_json(
                        _trace_path(args.ab_output, "C", replicate, case_id)
                    )
                )
                rows.append(score_trace(
                    trace, occurrence_index, c_trace=c_trace,
                ))
    summary = {
        "schema_version": SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "asset_kind": "l2_branch_generation_leaf_quality_audit",
        "generation_manifest_hash": manifest["manifest_hash"],
        "adjudication_hash": ab.stable_hash(fixture),
        "adjudication_units": len(units),
        "reviewed_occurrences": len(occurrence_index),
        "metric_definitions": {
            "leaf_specific_rate": (
                "Concrete named disease/syndrome leaves divided by auditable L2 "
                "leaves; partial-flow fallback leaves are excluded."
            ),
            "leaf_parent_invalid_rate": (
                "Leaves clinically incoherent under their assigned parent "
                "divided by auditable L2 leaves; fallback leaves are excluded."
            ),
            "leaf_semantic_duplicate_rate": (
                "Leaves whose adjudicated semantic cluster occurs more than once "
                "in the same tree divided by auditable L2 leaves."
            ),
            "semantic_duplicate_excess_rate": (
                "Minimum leaves removable to leave one representative per "
                "adjudicated semantic cluster, divided by auditable L2 leaves; directly "
                "comparable to the legacy exact-label duplicate_rate."
            ),
            "leaf_clean_rate": (
                "Leaves that are specific, parent-valid, and semantically unique "
                "within the tree divided by auditable L2 leaves."
            ),
            "novel_vs_c_*": (
                "Same metrics restricted to semantic clusters absent from the "
                "matched C tree for the same case and replicate."
            ),
        },
        "arms": {
            arm: _weighted_cohort([row for row in rows if row["arm"] == arm])
            for arm in ARMS
        },
        "paired_case_cluster_bootstrap": {
            f"C_to_{arm}": _paired_case_bootstrap(
                rows, arm, n_boot=args.bootstrap,
            )
            for arm in ("A", "B")
        },
        "hybrid_overlap_validation": _hybrid_overlap_validation(
            units, args.hybrid_fixture,
        ),
    }
    args.output.mkdir(parents=True, exist_ok=True)
    _atomic_json(args.output / "records.json", {"records": rows})
    _atomic_json(args.output / "summary.json", summary)
    _write_csv(args.output / "records.csv", rows)
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "stage", choices=(
            "write-adjudication-sheet", "merge-adjudication-chunks",
            "apply-corrections", "evaluate",
        ),
    )
    parser.add_argument("--ab-output", type=Path, default=DEFAULT_AB_OUTPUT)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--chunks", type=Path, default=DEFAULT_CHUNKS)
    parser.add_argument("--corrections", type=Path, default=DEFAULT_CORRECTIONS)
    parser.add_argument(
        "--hybrid-fixture", type=Path, default=DEFAULT_HYBRID_FIXTURE,
    )
    parser.add_argument("--bootstrap", type=int, default=10000)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    handlers = {
        "write-adjudication-sheet": write_adjudication_sheet,
        "merge-adjudication-chunks": merge_adjudication_chunks,
        "apply-corrections": apply_corrections,
        "evaluate": evaluate,
    }
    result = handlers[args.stage](args)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
