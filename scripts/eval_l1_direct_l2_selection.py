#!/usr/bin/env python3
"""Isolate evidence selection with frozen L2 leaves as direct targets."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import eval_l1_anti_anchor_debate as anti_eval  # noqa: E402
import eval_l1_contrastive_selection as isolated  # noqa: E402
import eval_l1_evidence_bfs as bfs  # noqa: E402
from agentclinic_tree_dx.l1_evidence_bfs import assert_no_gold_leak  # noqa: E402
from agentclinic_tree_dx.llm_client import RobustLLMClient  # noqa: E402


PROMPT = (
    bfs.PROMPT_DIR / "l1_anti_anchor_evidence_selector.txt"
).read_text(encoding="utf-8") + (
    bfs.PROMPT_DIR / "l1_direct_l2_selector_guard.txt"
).read_text(encoding="utf-8")


def _norm(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text.lower()).split())


def _l1_ancestor(branch, branches: Mapping[str, Any]):
    current = branch
    visited: set[str] = set()
    while current.level > 1 and current.parent not in visited:
        visited.add(current.id)
        parent = branches.get(current.parent)
        if parent is None:
            break
        current = parent
    return current if current.level == 1 else None


def _direct_l2_candidates(frozen_tree) -> list[dict[str, Any]]:
    leaves = sorted(
        (
            branch for branch in frozen_tree.branches.values()
            if branch.level > 1 and not branch.children
        ),
        key=lambda branch: branch.id,
    )
    score = 1.0 / len(leaves) if leaves else 0.0
    rows = []
    for branch in leaves:
        parent = _l1_ancestor(branch, frozen_tree.branches)
        rows.append({
            "id": branch.id,
            "label": branch.label,
            "score": score,
            "l1_parent_id": parent.id if parent is not None else "",
            "l1_parent_label": parent.label if parent is not None else "",
            "leaf_exemplars": [],
        })
    return rows


def _candidate_overlap(
    case: Mapping[str, Any],
    l2_candidates: list[Mapping[str, Any]],
) -> dict[str, int]:
    p5_names = [
        _norm(str(row["name"]))
        for row in case["annotation"].get("candidates") or ()
    ]
    l2_names = [_norm(str(row["label"])) for row in l2_candidates]
    return {
        "p5_candidates": len(p5_names),
        "exact_name_matches": sum(name in l2_names for name in p5_names),
        "substring_matches": sum(
            any(name in leaf or leaf in name for leaf in l2_names)
            for name in p5_names
        ),
    }


def _source_records(
    path: Path,
    *,
    replicates: int,
    case_ids: set[str],
) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = [
        row for row in (payload.get("records") or [])
        if row.get("arm") == "anti_anchor_prompt"
        and int(row.get("replicate") or 0) <= replicates
        and row.get("case_id") in case_ids
    ]
    expected = replicates * len(case_ids)
    if len(rows) != expected:
        raise ValueError(f"anti-anchor source incomplete: {len(rows)} != {expected}")
    return rows


def run(args: argparse.Namespace) -> dict[str, Any]:
    args.output_dir.mkdir(parents=True, exist_ok=True)
    composed = bfs._load_module("direct_l2_composed", bfs.COMPOSED_SCRIPT)
    partial = bfs._load_module("direct_l2_partial", bfs.PARTIAL_SCRIPT)
    talp = bfs._load_module("direct_l2_talp", bfs.TALP_SCRIPT)
    cases = partial._select_cases(partial.assemble_cases(), args.cases, args.limit)
    frozen_arms = composed.FrozenOfflineArms(
        talp, {"p5_headline": bfs.DEFAULT_ARM_OUTPUTS["p5_headline"]}
    )
    case_inputs: dict[str, dict[str, Any]] = {}
    overlap: dict[str, dict[str, int]] = {}
    for case in cases:
        tree_payload = json.loads(
            (bfs.DEFAULT_SHARED_TREE_DIR / f"{case['id']}.json").read_text(
                encoding="utf-8"
            )
        )
        frozen_tree = composed._deserialize_state(tree_payload["state"])
        facts = bfs._facts_for_case(
            frozen_tree, case["annotation"], composed, deduplicate=True,
        )
        blocks = frozen_arms.blocks("p5_headline", case["id"], facts)
        view = anti_eval._selector_view(
            isolated._selection_payload(case, frozen_tree, facts, blocks)
        )
        l2_candidates = _direct_l2_candidates(frozen_tree)
        if len(l2_candidates) < 2:
            raise ValueError(f"{case['id']} has fewer than two frozen L2 leaves")
        view["candidates"] = l2_candidates
        assert_no_gold_leak(view)
        overlap[case["id"]] = _candidate_overlap(case, l2_candidates)
        case_inputs[case["id"]] = {
            "case": case,
            "facts": facts,
            "view": view,
        }

    baseline = _source_records(
        args.source_summary,
        replicates=args.replicates,
        case_ids=set(case_inputs),
    )
    direct_records: list[dict[str, Any]] = []
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
            args.output_dir / f"direct_l2_r{replicate:02d}_cache.json",
            args.model,
        )
        for case_id, inputs in case_inputs.items():
            raw = anti_eval._call_with_schema_repair(
                cache,
                module="L1AntiAnchorDirectL2EvidenceSelector",
                prompt=PROMPT,
                payload=inputs["view"],
                view=inputs["view"],
            )
            direct_records.append(anti_eval._audit_record(
                arm="anti_anchor_direct_l2_targets",
                replicate=replicate,
                case_id=case_id,
                raw=raw,
                inputs=inputs,
                composed=composed,
            ))

    overlap_totals = {
        key: sum(row[key] for row in overlap.values())
        for key in ("p5_candidates", "exact_name_matches", "substring_matches")
    }
    result = {
        "schema_version": 1,
        "model": args.model,
        "temperature": args.temperature,
        "cases": sorted(case_inputs),
        "replicates": args.replicates,
        "design": {
            "baseline": "anti-anchor targets L1; frozen L2 names are exemplars",
            "intervention": (
                "anti-anchor candidate_effects directly target every frozen L2 leaf"
            ),
            "post_selection_l1_allocation_run": False,
            "scope": "selection only",
        },
        "l2_candidate_counts": {
            case_id: len(inputs["view"]["candidates"])
            for case_id, inputs in case_inputs.items()
        },
        "p5_to_generated_l2_name_overlap": {
            "by_case": overlap,
            "totals": overlap_totals,
        },
        "arms": {
            "anti_anchor_l1_targets": anti_eval._aggregate(baseline),
            "anti_anchor_direct_l2_targets": anti_eval._aggregate(direct_records),
        },
        "paired_case_bootstrap": isolated._paired_case_bootstrap(
            baseline, direct_records,
        ),
        "records": direct_records,
    }
    (args.output_dir / "summary.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=bfs.DEFAULT_MODEL)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--replicates", type=int, default=3)
    parser.add_argument("--call-timeout", type=float, default=240.0)
    parser.add_argument("--cases", default="")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument(
        "--source-summary",
        type=Path,
        default=ROOT / "logs" / "l1_anti_anchor_debate_isolated_v1"
        / "summary.json",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "logs" / "l1_direct_l2_selection_isolated_v1",
    )
    return parser.parse_args()


if __name__ == "__main__":
    result = run(parse_args())
    print(json.dumps({
        name: values["mean_across_replicates"]
        for name, values in result["arms"].items()
    }, ensure_ascii=False, indent=2))
