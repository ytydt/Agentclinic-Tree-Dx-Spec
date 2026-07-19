#!/usr/bin/env python3
"""Merge disjoint L1 Evidence-BFS shards and recompute paired statistics."""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HARNESS_PATH = ROOT / "scripts" / "eval_l1_evidence_bfs.py"


def _load_harness():
    spec = importlib.util.spec_from_file_location("l1_bfs_merge_harness", HARNESS_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {HARNESS_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _augment_trace_metrics(records, harness):
    """Derive newly added selection audits from frozen traces without LLM calls."""
    composed = harness._load_module(
        "l1_bfs_merge_composed", harness.COMPOSED_SCRIPT
    )
    partial = harness._load_module(
        "l1_bfs_merge_partial", harness.PARTIAL_SCRIPT
    )
    cases = {case["id"]: case for case in partial.assemble_cases()}
    tree_cache = {}
    facts_cache = {}
    for row in records:
        if row.get("status") != "OK" or not row.get("trace"):
            continue
        case = cases[row["case_id"]]
        projection = harness._manual_projection(case)
        tree = tree_cache.get(row["case_id"])
        if tree is None:
            payload = json.loads(
                (
                    harness.DEFAULT_SHARED_TREE_DIR / f"{row['case_id']}.json"
                ).read_text(encoding="utf-8")
            )
            tree = composed._deserialize_state(payload["state"])
            tree_cache[row["case_id"]] = tree
        deduplicate = harness.ARM_SPECS[row["arm"]].deduplicate
        fact_key = (row["case_id"], deduplicate)
        facts = facts_cache.get(fact_key)
        if facts is None:
            facts = harness._facts_for_case(
                tree,
                case["annotation"],
                composed,
                deduplicate=deduplicate,
            )
            facts_cache[fact_key] = facts
        fact_by_id = {fact.id: fact for fact in facts}
        first_cycle = (row["trace"].get("selection_cycles") or [{}])[0]

        def references(ids):
            return [
                harness._reference_for_fact(
                    fact_by_id[fact_id].text, projection, composed
                )
                for fact_id in ids or ()
                if fact_id in fact_by_id
            ]

        dedicated_refs = references(first_cycle.get("ruleout_ids"))
        displaced_refs = references(first_cycle.get("displaced_global_ids"))
        has_ruleout = any(
            item["role"] == "rule_out_distractor"
            for item in projection["findings"]
        )
        metrics = row.setdefault("metrics", {})
        metrics.update({
            "has_cross_l1_ruleout": has_ruleout,
            "dedicated_ro_select_valid": any(
                reference
                and reference.get("role") == "rule_out_distractor"
                for reference in dedicated_refs
            ),
            "dedicated_ro_correct_abstain": bool(
                not has_ruleout and not first_cycle.get("ruleout_ids")
            ),
            "displacement_count": len(
                first_cycle.get("displaced_global_ids") or ()
            ),
            "displaced_valid_fact": any(
                reference and reference.get("role") in {
                    "rule_in_gold", "rule_out_distractor",
                }
                for reference in displaced_refs
            ),
            "candidate_order_rotation_stability": None,
        })


def merge(run_dirs: list[Path], output_dir: Path, *, n_boot: int = 5000):
    harness = _load_harness()
    records_by_key = {}
    manifests = []
    duplicate_keys = []
    for run_dir in run_dirs:
        manifest = json.loads((run_dir / "manifest.json").read_text())
        manifests.append(manifest)
        allowed_cases = set(manifest.get("cases") or ())
        for path in sorted((run_dir / "traces").glob("*.json")):
            row = json.loads(path.read_text(encoding="utf-8"))
            if allowed_cases and row.get("case_id") not in allowed_cases:
                continue
            key = (
                row.get("track"), row.get("arm"), row.get("profile"),
                row.get("prior_mode"), row.get("case_id"),
            )
            if key in records_by_key:
                duplicate_keys.append(key)
            records_by_key[key] = row
    records = list(records_by_key.values())
    _augment_trace_metrics(records, harness)
    fingerprint = harness.stable_hash({
        "schema_version": 1,
        "source_fingerprints": [
            manifest.get("run_fingerprint") for manifest in manifests
        ],
        "record_keys": sorted(str(key) for key in records_by_key),
    })
    summary = harness._summarize(records, n_boot=n_boot)
    summary["run_fingerprint"] = fingerprint
    summary["source_run_dirs"] = [str(path) for path in run_dirs]
    output_dir.mkdir(parents=True, exist_ok=True)
    harness._atomic_json(output_dir / "manifest.json", {
        "schema_version": 1,
        "run_fingerprint": fingerprint,
        "source_run_dirs": [str(path) for path in run_dirs],
        "duplicate_keys_overridden_by_later_shard": [
            list(key) for key in duplicate_keys
        ],
        "source_fingerprints": [
            manifest.get("run_fingerprint") for manifest in manifests
        ],
        "records": len(records),
    })
    harness._atomic_json(output_dir / "summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dirs", nargs="+", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--n-boot", type=int, default=5000)
    args = parser.parse_args()
    summary = merge(args.run_dirs, args.output_dir, n_boot=args.n_boot)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["errors"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
