#!/usr/bin/env python3
"""Offline substrate census for Forest, IMPC, and Collapse3c case stages.

This program never calls a model.  It describes only fields already committed
under ``logs/backbone_v1`` and deliberately avoids inferring unobserved
selector responses or clinical edge truth from rationale text.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Any, Iterable


ARMS = {
    "Forest": "mosaic_forest_v1",
    "IMPC": "mosaic_impc_v1",
    "Collapse3c": "aphhm_c_collapse3c_v1",
}

EXPECTED_DATASETS = {
    "diagnosisarena": 100,
    "diagnosisarena_heldout": 100,
    "diagnosisarena_heldout200b": 200,
    "medcasereasoning": 100,
    "medcasereasoning_200b": 200,
    "medcasereasoning_v2": 100,
}


def _norm(value: str) -> str:
    value = str(value or "").strip().lower()
    value = re.sub(r"[^\w\s]", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _range(values: list[int]) -> dict[str, float | int]:
    return {
        "mean": sum(values) / len(values),
        "min": min(values),
        "max": max(values),
    }


def _stage_paths(root: Path, arm_dir: str) -> list[Path]:
    paths: list[Path] = []
    for dataset, expected in EXPECTED_DATASETS.items():
        case_dir = root / "logs/backbone_v1" / dataset / arm_dir / "case_stages"
        found = sorted(case_dir.glob("*.json"))
        if len(found) != expected:
            raise RuntimeError(
                f"{dataset}/{arm_dir}: expected {expected} stages, found {len(found)}"
            )
        paths.extend(found)
    return paths


def _load(paths: Iterable[Path]) -> list[dict[str, Any]]:
    return [json.loads(path.read_text(encoding="utf-8")) for path in paths]


def _git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _git_blob_sha1(path: Path) -> str:
    data = path.read_bytes()
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def _verify_input_tree(
    root: Path, source_commit: str, paths: list[Path]
) -> tuple[str, list[dict[str, str]]]:
    verified_commit = _git(root, "rev-parse", f"{source_commit}^{{commit}}")
    tree = _git(root, "ls-tree", "-r", "--full-tree", verified_commit, "--", "logs/backbone_v1")
    committed: dict[str, str] = {}
    for line in tree.splitlines():
        metadata, rel = line.split("\t", 1)
        _mode, kind, blob = metadata.split()
        if kind == "blob":
            committed[rel] = blob

    entries: list[dict[str, str]] = []
    local_paths = {str(path.relative_to(root)) for path in paths}
    committed_paths = {
        rel
        for rel in committed
        if any(
            rel.startswith(f"logs/backbone_v1/{dataset}/{arm_dir}/case_stages/")
            and rel.endswith(".json")
            for dataset in EXPECTED_DATASETS
            for arm_dir in ARMS.values()
        )
    }
    if local_paths != committed_paths:
        missing = sorted(committed_paths - local_paths)
        extra = sorted(local_paths - committed_paths)
        raise RuntimeError(
            f"local/source input population differs: missing={missing[:3]} extra={extra[:3]}"
        )

    for path in sorted(paths):
        rel = str(path.relative_to(root))
        local_blob = _git_blob_sha1(path)
        source_blob = committed.get(rel)
        if local_blob != source_blob:
            raise RuntimeError(
                f"input differs from {verified_commit}: {rel} "
                f"local={local_blob} source={source_blob}"
            )
        entries.append({"path": rel, "git_blob_sha1": local_blob})
    return verified_commit, entries


def _mosaic_census(rows: list[dict[str, Any]]) -> dict[str, Any]:
    evidence_per_case: list[int] = []
    candidates_per_case: list[int] = []
    frontier_per_case: list[int] = []
    calls: list[int] = []
    candidate_support = 0
    candidate_against = 0
    support_links = 0
    against_links = 0
    duplicate_cases = 0
    duplicate_excess = 0
    cross_view_duplicate_cases = 0
    aliases = 0
    containment_aliases = 0
    field_values: dict[str, Counter[str]] = {
        "polarity": Counter(),
        "temporality": Counter(),
        "epistemic_status": Counter(),
        "modality": Counter(),
        "reliability": Counter(),
    }

    for row in rows:
        stages = row["stages"]
        evidence = stages.get("evidence", [])
        registry = stages.get("registry", [])
        frontier = stages.get("frontier_final", [])
        evidence_per_case.append(len(evidence))
        candidates_per_case.append(len(registry))
        frontier_per_case.append(len(frontier))
        calls.append(int(row.get("llm_calls") or 0))

        by_norm: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for fact in evidence:
            by_norm[_norm(fact.get("raw_span", ""))].append(fact)
            for field in ("polarity", "epistemic_status", "modality", "reliability"):
                field_values[field][str(fact.get(field))] += 1
            field_values["temporality"][str(fact.get("temporality", "<missing>"))] += 1
        duplicated = [group for key, group in by_norm.items() if key and len(group) > 1]
        if duplicated:
            duplicate_cases += 1
            duplicate_excess += sum(len(group) - 1 for group in duplicated)
        if any(len({str(item.get("source_view")) for item in group}) > 1 for group in duplicated):
            cross_view_duplicate_cases += 1

        for candidate in registry:
            supports = candidate.get("supporting_evidence", [])
            against = candidate.get("contradicting_evidence", [])
            candidate_support += bool(supports)
            candidate_against += bool(against)
            support_links += len(supports)
            against_links += len(against)
            preferred = _norm(candidate.get("preferred_name", ""))
            for alias in candidate.get("aliases", []):
                aliases += 1
                normalized_alias = _norm(alias)
                if (
                    preferred
                    and normalized_alias
                    and preferred != normalized_alias
                    and (preferred in normalized_alias or normalized_alias in preferred)
                ):
                    containment_aliases += 1

    n_candidates = sum(candidates_per_case)
    if not n_candidates:
        raise RuntimeError("Mosaic census has zero candidates")
    return {
        "cases": len(rows),
        "evidence": {"total": sum(evidence_per_case), "per_case": _range(evidence_per_case)},
        "candidates": {
            "total": n_candidates,
            "per_case": _range(candidates_per_case),
            "with_support": candidate_support,
            "with_against": candidate_against,
            "support_links": support_links,
            "against_links": against_links,
            "mean_support_links": support_links / n_candidates,
            "mean_against_links": against_links / n_candidates,
        },
        "frontier_per_case": _range(frontier_per_case),
        "llm_calls_per_case": _range(calls),
        "evidence_field_values": {
            field: dict(sorted(counts.items())) for field, counts in field_values.items()
        },
        "normalized_duplicate_risk": {
            "cases": duplicate_cases,
            "excess_instances": duplicate_excess,
            "cross_view_cases": cross_view_duplicate_cases,
        },
        "identity_containment_risk": {
            "aliases": aliases,
            "unequal_normalized_containment_pairs": containment_aliases,
        },
    }


def _collapse_census(rows: list[dict[str, Any]]) -> dict[str, Any]:
    facts_per_case: list[int] = []
    candidates_per_case: list[int] = []
    frontier_per_case: list[int] = []
    shortlist_per_case: list[int] = []
    calls: list[int] = []
    candidate_support = 0
    candidate_against = 0
    support_links = 0
    against_links = 0
    support_fact_ids = 0
    valid_support_fact_ids = 0
    support_spans_exact_fact = 0
    against_spans_exact_fact = 0
    gap_candidates = 0
    gap_cases = 0
    matrix_enabled_cases = 0
    field_values: dict[str, Counter[str]] = {
        field: Counter()
        for field in (
            "polarity",
            "temporality",
            "epistemic_status",
            "modality",
            "specificity",
            "reliability",
        )
    }

    for row in rows:
        stages = row["stages"]
        facts = stages.get("facts", [])
        registry = stages.get("registry", [])
        fact_ids = {str(fact.get("fact_id")) for fact in facts}
        fact_spans = {_norm(fact.get("raw_span", "")) for fact in facts}
        facts_per_case.append(len(facts))
        candidates_per_case.append(len(registry))
        frontier_per_case.append(len(stages.get("frontier", [])))
        shortlist_per_case.append(int(row.get("metrics", {}).get("selector_shortlist_n") or 0))
        calls.append(int(row.get("llm_calls") or 0))
        matrix = stages.get("c4", {})
        if not (isinstance(matrix, dict) and matrix.get("skipped")):
            matrix_enabled_cases += 1

        for fact in facts:
            for field in field_values:
                field_values[field][str(fact.get(field))] += 1

        case_has_gap = False
        for candidate in registry:
            supports = candidate.get("support_spans", [])
            against = candidate.get("contradict_spans", [])
            support_ids = candidate.get("support_fact_ids", [])
            candidate_support += bool(supports)
            candidate_against += bool(against)
            support_links += len(supports)
            against_links += len(against)
            support_fact_ids += len(support_ids)
            valid_support_fact_ids += sum(str(item) in fact_ids for item in support_ids)
            support_spans_exact_fact += sum(_norm(span) in fact_spans for span in supports)
            against_spans_exact_fact += sum(_norm(span) in fact_spans for span in against)
            if candidate.get("gap_bound_fact_ids"):
                gap_candidates += 1
                case_has_gap = True
        gap_cases += case_has_gap

    n_candidates = sum(candidates_per_case)
    if not n_candidates:
        raise RuntimeError("Collapse3c census has zero candidates")
    return {
        "cases": len(rows),
        "facts": {"total": sum(facts_per_case), "per_case": _range(facts_per_case)},
        "candidates": {
            "total": n_candidates,
            "per_case": _range(candidates_per_case),
            "with_support_spans": candidate_support,
            "with_against_spans": candidate_against,
            "support_span_links": support_links,
            "against_span_links": against_links,
            "mean_support_span_links": support_links / n_candidates,
            "mean_against_span_links": against_links / n_candidates,
        },
        "frontier_per_case": _range(frontier_per_case),
        "selector_shortlist_per_case": _range(shortlist_per_case),
        "llm_calls_per_case": _range(calls),
        "fact_field_values": {
            field: dict(sorted(counts.items())) for field, counts in field_values.items()
        },
        "provenance": {
            "support_fact_ids": support_fact_ids,
            "valid_support_fact_ids": valid_support_fact_ids,
            "support_spans": support_links,
            "support_spans_equal_to_complete_fact": support_spans_exact_fact,
            "against_spans": against_links,
            "against_spans_equal_to_complete_fact": against_spans_exact_fact,
        },
        "gap_lane": {"candidates": gap_candidates, "cases": gap_cases},
        "matrix_enabled_cases": matrix_enabled_cases,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--manifest-output", type=Path)
    args = parser.parse_args()
    args.repo = args.repo.resolve()

    arms: dict[str, Any] = {}
    selected_paths: dict[str, list[Path]] = {
        name: _stage_paths(args.repo, arm_dir) for name, arm_dir in ARMS.items()
    }
    all_paths = [path for paths in selected_paths.values() for path in paths]
    verified_commit, manifest_entries = _verify_input_tree(
        args.repo, args.source_commit, all_paths
    )
    script_sha256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()

    input_paths: dict[str, list[str]] = {}
    for name in ARMS:
        paths = selected_paths[name]
        rows = _load(paths)
        if len(rows) != 800:
            raise RuntimeError(f"{name}: expected 800 stages, found {len(rows)}")
        case_keys = [
            (path.parents[2].name, str(row.get("case_id") or ""))
            for path, row in zip(paths, rows)
        ]
        if any(not case_id for _dataset, case_id in case_keys):
            raise RuntimeError(f"{name}: missing case_id")
        if len(case_keys) != len(set(case_keys)):
            raise RuntimeError(f"{name}: duplicate (dataset, case_id) key")
        arms[name] = _collapse_census(rows) if name == "Collapse3c" else _mosaic_census(rows)
        input_paths[name] = [str(path.relative_to(args.repo)) for path in paths]

    manifest = {
        "schema_version": "counterfactual-log-input-manifest-v1",
        "source_commit": verified_commit,
        "script_sha256": script_sha256,
        "git_object_format": "sha1",
        "expected_datasets": EXPECTED_DATASETS,
        "expected_arms": ARMS,
        "entries": manifest_entries,
    }
    manifest_rendered = json.dumps(
        manifest, ensure_ascii=False, indent=2, sort_keys=True
    ) + "\n"
    manifest_sha256 = hashlib.sha256(manifest_rendered.encode("utf-8")).hexdigest()
    manifest_path = args.manifest_output
    if manifest_path is None and args.output is not None:
        manifest_path = args.output.with_name("input_manifest.json")

    output = {
        "schema_version": "counterfactual-log-census-v1",
        "source_commit": verified_commit,
        "model_calls": 0,
        "provenance": {
            "source_tree_verified": True,
            "script_sha256": script_sha256,
            "input_manifest_entries": len(manifest_entries),
            "input_manifest_sha256": manifest_sha256,
            "input_manifest_file": manifest_path.name if manifest_path else None,
        },
        "scope": {
            "case_stages": sum(len(paths) for paths in input_paths.values()),
            "arms": list(ARMS),
            "case_stages_per_arm": {name: len(paths) for name, paths in input_paths.items()},
            "expected_datasets": EXPECTED_DATASETS,
        },
        "definitions": {
            "normalized_duplicate": "lowercase, remove punctuation, collapse whitespace; same-case only",
            "identity_containment_risk": "unequal normalized preferred/alias substring; high-recall risk marker, not clinical adjudication",
            "support_direction": "observed field assignment only; not independently validated clinical truth",
        },
        "arms": arms,
        "identifiability_boundary": [
            "Observed construction, identity merges, deterministic registry scores and frontiers are identifiable.",
            "Unobserved selector responses after evidence deletion, edge correction or alias splitting are not identifiable.",
            "E2 adjudicates observed champions, not every pool candidate or evidence edge.",
            "Existing E5/E8/E9/E11 contrasts are reusable only for their frozen interventions.",
        ],
    }
    rendered = json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if manifest_path:
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(manifest_rendered, encoding="utf-8")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
