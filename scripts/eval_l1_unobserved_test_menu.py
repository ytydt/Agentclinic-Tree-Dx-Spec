#!/usr/bin/env python3
"""Ablate a label-blind, result-unknown tree test menu for BFS selection."""
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
    bfs.PROMPT_DIR / "l1_unobserved_test_menu_guard.txt"
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


def _test_menu(frozen_tree, *, limit: int = 64) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    ordered = sorted(
        frozen_tree.branches.values(),
        key=lambda branch: (branch.level, branch.id),
    )
    for branch in ordered:
        ancestor = _l1_ancestor(branch, frozen_tree.branches)
        if ancestor is None:
            continue
        for kind, questions in (
            ("unanswered_question", branch.askable_discriminators),
            ("unperformed_test", branch.requestable_discriminators),
        ):
            for question in questions:
                key = _norm(str(question))
                if not key or key in seen:
                    continue
                seen.add(key)
                rows.append({
                    "kind": kind,
                    "l1_branch_id": ancestor.id,
                    "l1_branch_label": ancestor.label,
                    "source_branch_id": branch.id,
                    "source_branch_label": branch.label,
                    "question_or_test": str(question),
                    "result_status": "unknown_not_observed",
                })
                if len(rows) >= limit:
                    return rows
    return rows


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
    composed = bfs._load_module("test_menu_composed", bfs.COMPOSED_SCRIPT)
    partial = bfs._load_module("test_menu_partial", bfs.PARTIAL_SCRIPT)
    talp = bfs._load_module("test_menu_talp", bfs.TALP_SCRIPT)
    cases = partial._select_cases(partial.assemble_cases(), args.cases, args.limit)
    frozen_arms = composed.FrozenOfflineArms(
        talp, {"p5_headline": bfs.DEFAULT_ARM_OUTPUTS["p5_headline"]}
    )
    case_inputs: dict[str, dict[str, Any]] = {}
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
        view["unobserved_test_menu"] = _test_menu(
            frozen_tree, limit=args.menu_limit,
        )
        assert_no_gold_leak(view)
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
    menu_records: list[dict[str, Any]] = []
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
            args.output_dir / f"test_menu_r{replicate:02d}_cache.json",
            args.model,
        )
        for case_id, inputs in case_inputs.items():
            raw = anti_eval._call_with_schema_repair(
                cache,
                module="L1AntiAnchorMenuEvidenceSelector",
                prompt=PROMPT,
                payload=inputs["view"],
                view=inputs["view"],
            )
            menu_records.append(anti_eval._audit_record(
                arm="anti_anchor_with_unobserved_test_menu",
                replicate=replicate,
                case_id=case_id,
                raw=raw,
                inputs=inputs,
                composed=composed,
            ))

    result = {
        "schema_version": 1,
        "model": args.model,
        "temperature": args.temperature,
        "cases": sorted(case_inputs),
        "replicates": args.replicates,
        "design": {
            "baseline": "anti-anchor observed-only",
            "intervention": (
                "label-blind tree askable/requestable menu; results unknown; "
                "menu items cannot be selected"
            ),
            "raw_non_vignette_annotation_injected": False,
            "reason": (
                "raw non-vignette rows contain expected outcomes and would leak "
                "unobserved patient results"
            ),
            "menu_limit": args.menu_limit,
        },
        "menu_sizes": {
            case_id: len(inputs["view"]["unobserved_test_menu"])
            for case_id, inputs in case_inputs.items()
        },
        "arms": {
            "anti_anchor_observed_only": anti_eval._aggregate(baseline),
            "anti_anchor_with_test_menu": anti_eval._aggregate(menu_records),
        },
        "paired_case_bootstrap": isolated._paired_case_bootstrap(
            baseline, menu_records,
        ),
        "records": menu_records,
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
    parser.add_argument("--call-timeout", type=float, default=180.0)
    parser.add_argument("--cases", default="")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--menu-limit", type=int, default=64)
    parser.add_argument(
        "--source-summary",
        type=Path,
        default=ROOT / "logs" / "l1_anti_anchor_debate_isolated_v1"
        / "summary.json",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "logs" / "l1_unobserved_test_menu_isolated_v1",
    )
    return parser.parse_args()


if __name__ == "__main__":
    result = run(parse_args())
    print(json.dumps({
        name: values["mean_across_replicates"]
        for name, values in result["arms"].items()
    }, ensure_ascii=False, indent=2))
