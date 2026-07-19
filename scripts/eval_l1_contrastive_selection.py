#!/usr/bin/env python3
"""Isolated observed-evidence selection evaluation.

This intentionally stops before direction allocation or posterior updates.  It
compares stored forced-selector F2 choices with the contrastive, abstention-
capable selector on the same fact catalogues and frozen L1 branches.
"""
from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import eval_l1_evidence_bfs as bfs  # noqa: E402
from agentclinic_tree_dx.l1_evidence_bfs import (  # noqa: E402
    assert_no_gold_leak,
    l1_leaf_exemplars,
)
from agentclinic_tree_dx.llm_client import RobustLLMClient  # noqa: E402


def _block_items(value: Any) -> list[Any]:
    if value is None:
        return []
    return list(value) if isinstance(value, (list, tuple)) else [value]


def _selection_payload(
    case: Mapping[str, Any],
    frozen_tree,
    facts,
    blocks: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    select_rules: list[Any] = []
    provenance: list[Any] = []
    for fact in facts:
        block = blocks.get(fact.id, {})
        select_rules.extend(_block_items(block.get("select")))
        provenance.extend(_block_items(block.get("provenance")))
    branches = sorted(
        (branch for branch in frozen_tree.branches.values() if branch.level == 1),
        key=lambda branch: (-branch.posterior, branch.id),
    )
    exemplars = l1_leaf_exemplars(frozen_tree.branches)
    payload = {
        "case_context": case["case_text"],
        "candidates": [
            {
                "id": branch.id,
                "label": branch.label,
                "score": branch.posterior,
                "leaf_exemplars": exemplars.get(branch.id, []),
            }
            for branch in branches
        ],
        "fact_catalog_core": [fact.to_dict() for fact in facts],
        "selection_status_by_id": {fact.id: "eligible" for fact in facts},
        "eligible_fact_ids": [fact.id for fact in facts],
        "max_selected_facts": 2,
        "accounted_evidence_history": [],
        "discriminator_rules": select_rules[:64],
        "evidence_provenance": provenance[:64],
        "selection_goal": "global_discrimination",
    }
    assert_no_gold_leak(payload)
    return payload


def _reference_audit(
    selected_ids: list[str],
    *,
    facts,
    annotation: Mapping[str, Any],
    composed,
) -> dict[str, Any]:
    by_id = {fact.id: fact for fact in facts}
    findings = list(annotation.get("findings") or ())
    has_observed_decisive = any(
        bool(row.get("decisive") and row.get("in_vignette"))
        for row in findings
    )
    rows = []
    for fact_id in selected_ids:
        fact = by_id.get(fact_id)
        reference = (
            composed._best_reference(fact.text, findings) if fact is not None else None
        )
        rows.append({
            "fact_id": fact_id,
            "text": fact.text if fact is not None else "",
            "reference_finding": (
                str(reference.get("finding") or "") if reference else ""
            ),
            "role": str(reference.get("role") or "") if reference else "",
            "decisive": bool(reference and reference.get("decisive")),
            "in_vignette": bool(reference and reference.get("in_vignette")),
            "parent_child_trap": bool(
                reference and reference.get("parent_child_trap")
            ),
        })
    observed_decisive = [
        bool(row["decisive"] and row["in_vignette"]) for row in rows
    ]
    first_role = str(rows[0]["role"]).lower() if rows else ""
    reference_keys = [
        bfs._norm(row["reference_finding"])
        for row in rows
        if row["reference_finding"]
    ]
    return {
        "selections": rows,
        "select_at_1": bool(observed_decisive[:1] and observed_decisive[0]),
        "select_at_2": any(observed_decisive[:2]),
        "shared_or_trap_at_1": bool(
            rows[:1]
            and (
                first_role.startswith("shared")
                or rows[0]["parent_child_trap"]
            )
        ),
        "prototype_anchor_at_1": bool(
            rows[:1]
            and has_observed_decisive
            and first_role.startswith("rule_in")
            and rows[0]["in_vignette"]
            and not rows[0]["decisive"]
        ),
        "reference_duplicate_at_2": (
            len(reference_keys) >= 2 and len(set(reference_keys[:2])) < 2
        ),
        "abstained": not selected_ids,
        "has_observed_decisive": has_observed_decisive,
    }


def _aggregate(records: list[dict[str, Any]]) -> dict[str, Any]:
    keys = (
        "select_at_1",
        "select_at_2",
        "shared_or_trap_at_1",
        "prototype_anchor_at_1",
        "reference_duplicate_at_2",
        "abstained",
    )
    by_rep: dict[int, list[dict[str, Any]]] = {}
    for record in records:
        by_rep.setdefault(int(record["replicate"]), []).append(record)
    replicate_metrics = []
    for replicate, rows in sorted(by_rep.items()):
        eligible_rows = [
            row for row in rows if row["audit"]["has_observed_decisive"]
        ]
        replicate_metrics.append({
            "replicate": replicate,
            "n": len(rows),
            "n_with_observed_decisive": len(eligible_rows),
            **{
                key: sum(bool(row["audit"][key]) for row in rows) / len(rows)
                for key in keys
            },
            "select_at_1_given_observed_decisive": (
                sum(bool(row["audit"]["select_at_1"]) for row in eligible_rows)
                / len(eligible_rows) if eligible_rows else 0.0
            ),
            "select_at_2_given_observed_decisive": (
                sum(bool(row["audit"]["select_at_2"]) for row in eligible_rows)
                / len(eligible_rows) if eligible_rows else 0.0
            ),
        })
    aggregate_keys = (
        *keys,
        "select_at_1_given_observed_decisive",
        "select_at_2_given_observed_decisive",
    )
    return {
        "n_records": len(records),
        "replicates": len(replicate_metrics),
        "replicate_metrics": replicate_metrics,
        "mean_across_replicates": {
            key: statistics.fmean(row[key] for row in replicate_metrics)
            if replicate_metrics else 0.0
            for key in aggregate_keys
        },
        "sd_across_replicates": {
            key: statistics.stdev(row[key] for row in replicate_metrics)
            if len(replicate_metrics) > 1 else 0.0
            for key in aggregate_keys
        },
    }


def _paired_case_bootstrap(
    baseline: list[dict[str, Any]],
    contrastive: list[dict[str, Any]],
    *,
    n_boot: int = 10000,
    seed: int = 7,
) -> dict[str, Any]:
    def case_means(
        records: list[dict[str, Any]],
        metric: str,
        *,
        eligible_only: bool,
    ) -> dict[str, float]:
        grouped: dict[str, list[float]] = {}
        for record in records:
            if (
                eligible_only
                and not record["audit"]["has_observed_decisive"]
            ):
                continue
            grouped.setdefault(record["case_id"], []).append(
                float(bool(record["audit"][metric]))
            )
        return {
            case_id: statistics.fmean(values)
            for case_id, values in grouped.items()
        }

    rng = random.Random(seed)
    output: dict[str, Any] = {}
    specs = {
        "select_at_1": ("select_at_1", False),
        "select_at_2": ("select_at_2", False),
        "select_at_1_given_observed_decisive": ("select_at_1", True),
        "select_at_2_given_observed_decisive": ("select_at_2", True),
        "reference_duplicate_at_2": ("reference_duplicate_at_2", False),
        "prototype_anchor_at_1": ("prototype_anchor_at_1", True),
        "abstained": ("abstained", False),
    }
    for name, (metric, eligible_only) in specs.items():
        left = case_means(baseline, metric, eligible_only=eligible_only)
        right = case_means(contrastive, metric, eligible_only=eligible_only)
        cases = sorted(set(left) & set(right))
        deltas = [right[case_id] - left[case_id] for case_id in cases]
        samples = []
        for _ in range(n_boot):
            samples.append(statistics.fmean(
                deltas[rng.randrange(len(deltas))] for _ in cases
            ))
        samples.sort()
        output[name] = {
            "n_cases": len(cases),
            "delta": statistics.fmean(deltas),
            "ci95": [
                samples[int(0.025 * (len(samples) - 1))],
                samples[int(0.975 * (len(samples) - 1))],
            ],
            "probability_positive": sum(value > 0 for value in samples) / n_boot,
        }
    return output


def _baseline_records(
    run_dirs: list[Path],
    case_inputs: Mapping[str, dict[str, Any]],
    composed,
) -> list[dict[str, Any]]:
    records = []
    for replicate, run_dir in enumerate(run_dirs, start=1):
        for path in sorted((run_dir / "full_traces").glob("p5_headline__*.json")):
            stored = json.loads(path.read_text(encoding="utf-8"))
            case_id = str(stored["case_id"])
            if case_id not in case_inputs or stored.get("status") != "OK":
                continue
            cycles = stored.get("trace", {}).get("selection_cycles") or []
            selected_ids = list(cycles[0].get("global_ids") or [])[:2] if cycles else []
            inputs = case_inputs[case_id]
            records.append({
                "arm": "forced_baseline",
                "replicate": replicate,
                "case_id": case_id,
                "selected_ids": selected_ids,
                "raw": cycles[0].get("global") if cycles else {},
                "audit": _reference_audit(
                    selected_ids,
                    facts=inputs["facts"],
                    annotation=inputs["case"]["annotation"],
                    composed=composed,
                ),
            })
    return records


def run(args: argparse.Namespace) -> dict[str, Any]:
    args.output_dir.mkdir(parents=True, exist_ok=True)
    composed = bfs._load_module("contrastive_eval_composed", bfs.COMPOSED_SCRIPT)
    partial = bfs._load_module("contrastive_eval_partial", bfs.PARTIAL_SCRIPT)
    talp = bfs._load_module("contrastive_eval_talp", bfs.TALP_SCRIPT)
    cases = partial._select_cases(partial.assemble_cases(), args.cases, args.limit)
    frozen_arms = composed.FrozenOfflineArms(
        talp, {"p5_headline": bfs.DEFAULT_ARM_OUTPUTS["p5_headline"]}
    )
    case_inputs: dict[str, dict[str, Any]] = {}
    for case in cases:
        tree_path = bfs.DEFAULT_SHARED_TREE_DIR / f"{case['id']}.json"
        tree_payload = json.loads(tree_path.read_text(encoding="utf-8"))
        frozen_tree = composed._deserialize_state(tree_payload["state"])
        facts = bfs._facts_for_case(
            frozen_tree, case["annotation"], composed, deduplicate=True,
        )
        blocks = frozen_arms.blocks("p5_headline", case["id"], facts)
        case_inputs[case["id"]] = {
            "case": case,
            "facts": facts,
            "payload": _selection_payload(case, frozen_tree, facts, blocks),
        }

    baseline_dirs = [Path(value) for value in args.baseline_run_dir]
    baseline = _baseline_records(baseline_dirs, case_inputs, composed)
    contrastive: list[dict[str, Any]] = []
    for replicate in range(1, args.replicates + 1):
        client = RobustLLMClient(
            model=args.model,
            call_timeout=args.call_timeout,
            max_retries=5,
            timeout_retry_cap=2,
            temperature=args.temperature,
        )
        cache = bfs.CachedLLM(
            client,
            args.output_dir / f"contrastive_r{replicate:02d}_cache.json",
            args.model,
        )
        selector, _, _, _ = bfs._runtime_functions(
            cache, "p5_contrastive_direct", talp,
        )
        for case_id, inputs in case_inputs.items():
            raw = dict(selector(inputs["payload"]))
            selected_ids = list(raw.get("ranked_fact_ids") or [])[:2]
            contrastive.append({
                "arm": "contrastive",
                "replicate": replicate,
                "case_id": case_id,
                "selected_ids": selected_ids,
                "raw": raw,
                "audit": _reference_audit(
                    selected_ids,
                    facts=inputs["facts"],
                    annotation=inputs["case"]["annotation"],
                    composed=composed,
                ),
            })
    result = {
        "schema_version": 1,
        "model": args.model,
        "temperature": args.temperature,
        "cases": sorted(case_inputs),
        "metric_note": (
            "SELECT uses the repository _best_reference Jaccard audit matcher; "
            "it is deterministic but retains known semantic false positives/negatives."
        ),
        "baseline": _aggregate(baseline),
        "contrastive": _aggregate(contrastive),
        "paired_case_bootstrap": _paired_case_bootstrap(
            baseline, contrastive,
        ),
        "records": baseline + contrastive,
    }
    output_path = args.output_dir / "summary.json"
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=bfs.DEFAULT_MODEL)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--replicates", type=int, default=3)
    parser.add_argument("--call-timeout", type=float, default=180.0)
    parser.add_argument("--cases", default="")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "logs" / "l1_contrastive_selection_isolated",
    )
    default_runs = [
        ROOT / "logs" / "l1_bfs_adaptive_stop" / "f30_saturation_t0_r1",
        *[
            ROOT / "logs" / "l1_bfs_adaptive_stop" / f"f30_saturation_t0_r{i:02d}"
            for i in range(2, 10)
        ],
    ]
    parser.add_argument(
        "--baseline-run-dir",
        action="append",
        default=[str(path) for path in default_runs],
    )
    return parser.parse_args()


if __name__ == "__main__":
    result = run(parse_args())
    print(json.dumps({
        "baseline": result["baseline"]["mean_across_replicates"],
        "contrastive": result["contrastive"]["mean_across_replicates"],
    }, ensure_ascii=False, indent=2))
