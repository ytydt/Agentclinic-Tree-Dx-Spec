#!/usr/bin/env python3
"""Freeze production auto-findings and a candidate-blind important subset."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import eval_l1_evidence_bfs as bfs  # noqa: E402
from agentclinic_tree_dx.composed_pipeline import observed_facts  # noqa: E402
from agentclinic_tree_dx.l1_evidence_bfs import (  # noqa: E402
    assert_no_gold_leak,
    stable_hash,
)
from agentclinic_tree_dx.llm_client import RobustLLMClient  # noqa: E402


PROMPT_PATH = (
    bfs.PROMPT_DIR / "l1_auto_finding_importance_filter.txt"
)
DEFAULT_FIXTURE = ROOT / "eval_fixtures" / "l1_auto_finding_selection_v1.json"
DEFAULT_OUTPUT_DIR = ROOT / "logs" / "l1_auto_finding_filter_v1"


def _source_id(item: Any, index: int) -> str:
    if isinstance(item, Mapping):
        return str(item.get("id") or f"E{index}")
    return str(getattr(item, "id", "") or f"E{index}")


def production_auto_findings(state: Any) -> list[dict[str, str]]:
    """Reproduce ``observed_facts`` while retaining parser source IDs."""
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, item in enumerate(state.static_evidence_items, start=1):
        text = bfs._value_from(item).strip()
        key = " ".join(text.lower().split())
        if not text or not key or key in seen:
            continue
        seen.add(key)
        rows.append({
            "id": f"F{len(rows) + 1}",
            "source_id": _source_id(item, index),
            "text": text,
        })
        if len(rows) >= 40:
            break
    expected = [
        fact.to_dict() for fact in observed_facts(state.static_evidence_items)
    ]
    assert [
        {"id": row["id"], "text": row["text"]} for row in rows
    ] == expected
    return rows


def clean_filter_response(
    response: Mapping[str, Any],
    allowed_ids: Sequence[str],
    *,
    minimum: int,
    maximum: int,
) -> dict[str, Any]:
    allowed = set(allowed_ids)
    values = response.get("ranked_fact_ids") or []
    if isinstance(values, str):
        values = [values]
    ranked: list[str] = []
    rejected: list[str] = []
    for value in values if isinstance(values, (list, tuple)) else ():
        fact_id = str(value or "").strip()
        if fact_id in allowed and fact_id not in ranked:
            ranked.append(fact_id)
        elif fact_id:
            rejected.append(fact_id)
        if len(ranked) >= maximum:
            break
    required = min(minimum, len(allowed))
    return {
        "ranked_fact_ids": ranked,
        "rejected_ids": rejected,
        "schema_valid": len(ranked) >= required,
    }


def consensus_fact_ids(
    rankings: Sequence[Sequence[str]],
    allowed_ids: Sequence[str],
    *,
    minimum: int,
    maximum: int,
) -> list[str]:
    """Majority-first rank aggregation with deterministic fallback filling."""
    allowed = set(allowed_ids)
    cleaned = [
        [fact_id for fact_id in ranking if fact_id in allowed]
        for ranking in rankings
    ]
    appearances: dict[str, int] = {}
    rank_sum: dict[str, float] = {}
    for ranking in cleaned:
        for index, fact_id in enumerate(dict.fromkeys(ranking), start=1):
            appearances[fact_id] = appearances.get(fact_id, 0) + 1
            rank_sum[fact_id] = rank_sum.get(fact_id, 0.0) + index
    majority = math.ceil(len(cleaned) / 2) if cleaned else 1

    def key(fact_id: str) -> tuple[float, float, str]:
        count = appearances[fact_id]
        return (-count, rank_sum[fact_id] / count, fact_id)

    ranked_all = sorted(appearances, key=key)
    output = [
        fact_id for fact_id in ranked_all
        if appearances[fact_id] >= majority
    ][:maximum]
    required = min(minimum, len(allowed_ids))
    for fact_id in ranked_all:
        if len(output) >= required:
            break
        if fact_id not in output:
            output.append(fact_id)
    return output[:maximum]


def _filter_once(
    cache: bfs.CachedLLM,
    *,
    prompt: str,
    findings: Sequence[Mapping[str, str]],
    minimum: int,
    maximum: int,
) -> dict[str, Any]:
    allowed_ids = [row["id"] for row in findings]
    payload = {
        "auto_findings": [
            {"id": row["id"], "text": row["text"]} for row in findings
        ],
        "min_selected_facts": min(minimum, len(findings)),
        "max_selected_facts": min(maximum, len(findings)),
    }
    assert_no_gold_leak(payload)
    response = cache.call(
        "L1AutoFindingImportanceFilter", prompt, payload,
    )
    cleaned = clean_filter_response(
        response, allowed_ids, minimum=minimum, maximum=maximum,
    )
    repair_used = False
    if not cleaned["schema_valid"]:
        repair_payload = {
            **payload,
            "invalid_response": response,
            "validation_errors": {
                "rejected_ids": cleaned["rejected_ids"],
                "accepted_count": len(cleaned["ranked_fact_ids"]),
            },
            "schema_repair": (
                "Return only IDs from auto_findings and satisfy the requested "
                "minimum and maximum counts."
            ),
        }
        assert_no_gold_leak(repair_payload)
        response = cache.call(
            "L1AutoFindingImportanceFilterRepair", prompt, repair_payload,
        )
        cleaned = clean_filter_response(
            response, allowed_ids, minimum=minimum, maximum=maximum,
        )
        repair_used = True
    return {
        "raw": response,
        **cleaned,
        "repair_used": repair_used,
    }


def build_fixture(args: argparse.Namespace) -> dict[str, Any]:
    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.fixture.parent.mkdir(parents=True, exist_ok=True)
    prompt = PROMPT_PATH.read_text(encoding="utf-8")
    composed = bfs._load_module("auto_finding_freeze_composed", bfs.COMPOSED_SCRIPT)
    partial = bfs._load_module("auto_finding_freeze_partial", bfs.PARTIAL_SCRIPT)
    cases = partial._select_cases(
        partial.assemble_cases(), args.cases, args.limit,
    )
    case_assets: list[dict[str, Any]] = []
    caches: list[bfs.CachedLLM] = []
    if not args.dry_run:
        for replicate in range(1, args.replicates + 1):
            client = RobustLLMClient(
                model=args.model,
                call_timeout=args.call_timeout,
                max_retries=5,
                timeout_retry_cap=2,
                temperature=args.temperature,
            )
            caches.append(bfs.CachedLLM(
                client,
                args.output_dir / f"filter_r{replicate:02d}_cache.json",
                args.model,
            ))
    for case in cases:
        tree_path = bfs.DEFAULT_SHARED_TREE_DIR / f"{case['id']}.json"
        tree_payload = json.loads(tree_path.read_text(encoding="utf-8"))
        state = composed._deserialize_state(tree_payload["state"])
        findings = production_auto_findings(state)
        runs = [
            {
                "replicate": replicate,
                **_filter_once(
                    cache,
                    prompt=prompt,
                    findings=findings,
                    minimum=args.min_findings,
                    maximum=args.max_findings,
                ),
            }
            for replicate, cache in enumerate(caches, start=1)
        ]
        filtered = consensus_fact_ids(
            [row["ranked_fact_ids"] for row in runs],
            [row["id"] for row in findings],
            minimum=args.min_findings,
            maximum=args.max_findings,
        )
        case_assets.append({
            "case_id": case["id"],
            "shared_tree_sha256": bfs._sha256(tree_path),
            "full_catalog_hash": stable_hash(findings),
            "full_findings": findings,
            "filter_runs": runs,
            "filtered_fact_ids": filtered,
            "gold": {
                "status": "pending_manual_adjudication",
                "best_l1_fact_ids": [],
                "valid_l1_fact_ids": [],
                "shared_or_misleading_fact_ids": [],
                "best_fact_sets": [],
                "rationale": "",
            },
        })
    result = {
        "schema_version": 1,
        "asset_kind": "frozen_production_auto_finding_catalogs",
        "model": args.model,
        "temperature": args.temperature,
        "filter_replicates": args.replicates,
        "filter_prompt_path": str(PROMPT_PATH.relative_to(ROOT)),
        "filter_prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "source": {
            "shared_tree_dir": str(bfs.DEFAULT_SHARED_TREE_DIR.relative_to(ROOT)),
            "catalog": "state.static_evidence_items only",
            "annotation_findings_injected": False,
            "candidate_labels_visible_to_filter": False,
            "case_text_visible_to_filter": False,
        },
        "consensus": {
            "method": "majority_count_then_mean_rank",
            "min_findings": args.min_findings,
            "max_findings": args.max_findings,
        },
        "cases": case_assets,
    }
    bfs._atomic_json(args.fixture, result)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=bfs.DEFAULT_MODEL)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--replicates", type=int, default=3)
    parser.add_argument("--min-findings", type=int, default=3)
    parser.add_argument("--max-findings", type=int, default=8)
    parser.add_argument("--call-timeout", type=float, default=240.0)
    parser.add_argument("--cases", default="")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


if __name__ == "__main__":
    fixture = build_fixture(parse_args())
    print(json.dumps({
        "cases": len(fixture["cases"]),
        "full_findings": sum(
            len(row["full_findings"]) for row in fixture["cases"]
        ),
        "filtered_findings": sum(
            len(row["filtered_fact_ids"]) for row in fixture["cases"]
        ),
    }, ensure_ascii=False, indent=2))
