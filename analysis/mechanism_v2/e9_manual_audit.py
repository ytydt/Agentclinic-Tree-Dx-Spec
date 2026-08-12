#!/usr/bin/env python3
"""Freeze and materialize the root-owned E9 manual trajectory audit queue."""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

if __package__ in {None, ""}:
    _ROOT_FOR_IMPORT = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(_ROOT_FOR_IMPORT))

from analysis.mechanism_v2.common import ROOT, FrozenExactSynonymBridge, file_sha256
from analysis.mechanism_v2.e9_view_independence import (
    ARMS,
    BRIDGE_PATH,
    DUPLICATE,
    REAL,
    ROTATED,
    SINGLE,
    STAGE_KEYS,
    build_jobs,
    evidence_strings,
)
from analysis.mechanism_v2.online_runner import read_jsonl, write_jsonl
from analysis.mechanism_v2.runtime_contract import atomic_json, stable_seed


OUT = ROOT / "analysis/mechanism_v2/results/E9_view_independence"


def _condition_rows(out: Path) -> dict[str, dict[str, dict[str, Any]]]:
    indexed: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for arm in ARMS:
        for row in read_jsonl(out / "arms" / arm / "case_results.jsonl"):
            indexed[str(row["case_key"])][arm] = row
    return indexed


def _flip(arms: Mapping[str, Mapping[str, Any]], left: str, right: str) -> bool:
    if not arms[left]["success"] or not arms[right]["success"]:
        return False
    return str(arms[left]["champion_label"]).casefold() != str(arms[right]["champion_label"]).casefold()


def _outcome_discord(arms: Mapping[str, Mapping[str, Any]], left: str, right: str) -> bool:
    if not arms[left]["success"] or not arms[right]["success"]:
        return False
    return bool(arms[left]["gold_top1"]) != bool(arms[right]["gold_top1"])


def _sha_take(case_keys: Sequence[str], salt: str, n: int) -> list[str]:
    return sorted(case_keys, key=lambda key: (stable_seed(salt, key), key))[:n]


def freeze_selection(out: Path) -> dict[str, Any]:
    indexed = _condition_rows(out)
    construction = {
        row["case_key"]: row for row in read_jsonl(out / "construction_ledger.jsonl")
    }
    semantic = {
        row["case_key"]: row for row in read_jsonl(out / "semantic_audit/case_results.jsonl")
    }
    categories: dict[str, list[str]] = {}
    categories["reference_unique_capture_all"] = sorted(
        key for key, row in construction.items()
        if row["gold_capture_union"] and not row["gold_capture_anchor"]
    )
    categories["real_vs_single_outcome_discord_all"] = sorted(
        key for key, arms in indexed.items() if _outcome_discord(arms, SINGLE, REAL)
    )
    categories["role_label_outcome_discord_all"] = sorted(
        key for key, arms in indexed.items() if _outcome_discord(arms, REAL, ROTATED)
    )
    categories["repetition_outcome_discord_all"] = sorted(
        key for key, arms in indexed.items() if _outcome_discord(arms, SINGLE, DUPLICATE)
    )
    categories["role_flip_same_outcome_sha12"] = _sha_take(
        [
            key for key, arms in indexed.items()
            if _flip(arms, REAL, ROTATED)
            and not _outcome_discord(arms, REAL, ROTATED)
        ],
        "E9-manual-role-flip-v1", 12,
    )
    categories["repetition_flip_same_outcome_sha12"] = _sha_take(
        [
            key for key, arms in indexed.items()
            if _flip(arms, SINGLE, DUPLICATE)
            and not _outcome_discord(arms, SINGLE, DUPLICATE)
        ],
        "E9-manual-repetition-flip-v1", 12,
    )
    valid_semantic = [
        (key, float(row["metrics"]["compression_ratio"]))
        for key, row in semantic.items() if row["success"]
    ]
    ratios = sorted(value for _, value in valid_semantic)
    low_cut = ratios[len(ratios) // 4]
    high_cut = ratios[(3 * len(ratios)) // 4]
    categories["semantic_high_merge_q1_sha10"] = _sha_take(
        [key for key, ratio in valid_semantic if ratio <= low_cut],
        "E9-manual-semantic-high-merge-v1", 10,
    )
    categories["semantic_low_merge_q4_sha10"] = _sha_take(
        [key for key, ratio in valid_semantic if ratio >= high_cut],
        "E9-manual-semantic-low-merge-v1", 10,
    )
    categories["semantic_partition_failures_all"] = sorted(
        key for key, row in semantic.items() if not row["success"]
    )
    selected = sorted({key for values in categories.values() for key in values})
    candidate = {
        "schema": "E9_root_manual_audit_selection_v1",
        "created_before_root_case_judgments_utc": datetime.now(timezone.utc).isoformat(),
        "selection_uses": [
            "frozen reference exposure", "arm success/top1/champion only",
            "semantic audit success and compression ratio",
        ],
        "categories": categories,
        "category_counts": {key: len(values) for key, values in categories.items()},
        "semantic_quartile_cuts": {"q1": low_cut, "q3": high_cut},
        "selected_case_keys": selected,
        "n_unique_cases": len(selected),
        "judgment_fields": {
            "strict_reference_equivalence": "yes|scope_or_surface_artifact|no|not_exposed",
            "additional_view_content": "decisive|useful_nondecisive|redundant|distracting|not_applicable",
            "role_label_mechanism": "explicit_role_weighting|narrative_only|no_evidence|indeterminate",
            "repetition_mechanism": "explicit_vote_or_repetition_weight|noticed_and_discounted|no_evidence|indeterminate",
            "semantic_cluster_fidelity": "faithful|minor_errors|major_errors|not_served",
            "trajectory_mechanism": "capture_gain|selection_gain|selection_harm|label_instability|repetition_instability|stable|interface_failure|other",
            "root_note": "case-specific evidence-backed explanation",
        },
        "root_responsibility": True,
        "external_llm_is_subcontractor_only": True,
    }
    path = out / "manual_audit_selection.json"
    if path.is_file():
        frozen = json.loads(path.read_text(encoding="utf-8"))
        for key in (
            "schema", "categories", "semantic_quartile_cuts", "selected_case_keys",
            "judgment_fields",
        ):
            if frozen.get(key) != candidate.get(key):
                raise AssertionError(f"manual audit selection mismatch: {key}")
        return frozen
    atomic_json(path, candidate)
    return candidate


def materialize_queue(out: Path, selection: Mapping[str, Any]) -> None:
    bridge = FrozenExactSynonymBridge(BRIDGE_PATH)
    source_jobs, _ = build_jobs(bridge)
    source_index = {job["case_key"]: job for job in source_jobs}
    conditions = _condition_rows(out)
    construction = {
        row["case_key"]: row for row in read_jsonl(out / "construction_ledger.jsonl")
    }
    semantic = {
        row["case_key"]: row for row in read_jsonl(out / "semantic_audit/case_results.jsonl")
    }
    membership: dict[str, list[str]] = defaultdict(list)
    for category, keys in selection["categories"].items():
        for key in keys:
            membership[key].append(category)
    rows: list[dict[str, Any]] = []
    for case_key in selection["selected_case_keys"]:
        job = source_index[case_key]
        raw_views = []
        for index, stage_key in enumerate(STAGE_KEYS, 1):
            raw = job["raw_views"][stage_key]
            raw_views.append(
                {
                    "view_id": f"V{index}", "stage_key": stage_key,
                    "axis": raw.get("axis"),
                    "candidates": raw.get("candidates") or [],
                    "evidence_observations": evidence_strings(raw),
                }
            )
        rows.append(
            {
                "case_key": case_key, "family": job["family"],
                "source_id": job["source_id"], "categories": sorted(membership[case_key]),
                "gold": job["gold"], "vignette": job["vignette"],
                "anchor_key": job["anchor_key"],
                "raw_views": raw_views,
                "construction": construction[case_key],
                "conditions": {arm: conditions[case_key][arm] for arm in ARMS},
                "semantic_audit": semantic[case_key],
                "root_judgment": None,
            }
        )
    write_jsonl(out / "manual_audit_queue.jsonl", rows)
    atomic_json(
        out / "manual_audit_queue_provenance.json",
        {
            "schema": "E9_root_manual_audit_queue_provenance_v1",
            "selection_sha256": file_sha256(out / "manual_audit_selection.json"),
            "queue_sha256": file_sha256(out / "manual_audit_queue.jsonl"),
            "n_rows": len(rows),
            "root_judgment_fields_unfilled": all(row["root_judgment"] is None for row in rows),
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
        },
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--freeze", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.freeze:
        raise SystemExit("select --freeze")
    out = args.out.resolve()
    selection = freeze_selection(out)
    materialize_queue(out, selection)
    print(
        f"frozen={selection['n_unique_cases']} categories="
        f"{json.dumps(selection['category_counts'], sort_keys=True)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
