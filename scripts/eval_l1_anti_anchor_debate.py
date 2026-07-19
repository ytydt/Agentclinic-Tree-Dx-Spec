#!/usr/bin/env python3
"""Prompt-only and two-proposer debate ablation for selector anchoring."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import eval_l1_contrastive_selection as isolated  # noqa: E402
import eval_l1_evidence_bfs as bfs  # noqa: E402
from agentclinic_tree_dx.l1_evidence_bfs import (  # noqa: E402
    assert_no_gold_leak,
    clean_contrastive_selection,
)
from agentclinic_tree_dx.llm_client import RobustLLMClient  # noqa: E402


ANTI_PROMPT = (
    bfs.PROMPT_DIR / "l1_anti_anchor_evidence_selector.txt"
).read_text(encoding="utf-8")
ARBITER_PROMPT = (
    bfs.PROMPT_DIR / "l1_selection_debate_arbiter.txt"
).read_text(encoding="utf-8")


def _selector_view(payload: Mapping[str, Any]) -> dict[str, Any]:
    eligible = set(payload["eligible_fact_ids"])
    view = {
        "vignette": payload["case_context"],
        "case_context": payload["case_context"],
        "candidates": payload["candidates"],
        "available_findings": [
            row for row in payload["fact_catalog_core"] if row["id"] in eligible
        ],
        "fact_catalog_core": payload["fact_catalog_core"],
        "selection_status_by_id": payload["selection_status_by_id"],
        "eligible_fact_ids": payload["eligible_fact_ids"],
        "max_selected_facts": payload["max_selected_facts"],
        "accounted_evidence_history": payload["accounted_evidence_history"],
        "discriminator_rules": payload.get("discriminator_rules") or [],
        "evidence_provenance": payload.get("evidence_provenance") or [],
    }
    assert_no_gold_leak(view)
    return view


def _clean(response: Mapping[str, Any], view: Mapping[str, Any]) -> dict[str, Any]:
    return clean_contrastive_selection(
        response,
        view["eligible_fact_ids"],
        [row["id"] for row in view["candidates"]],
        limit=int(view["max_selected_facts"]),
    )


def _call_with_schema_repair(
    cache: bfs.CachedLLM,
    *,
    module: str,
    prompt: str,
    payload: Mapping[str, Any],
    view: Mapping[str, Any],
) -> dict[str, Any]:
    response = cache.call(module, prompt, payload)
    cleaned = _clean(response, view)
    if cleaned["schema_valid"]:
        cleaned["repair_used"] = False
        return cleaned
    repair_payload = {
        **payload,
        "invalid_response": response,
        "validation_errors": cleaned["rejected"],
        "schema_repair": (
            "Preserve the clinical ranking if defensible, but return a complete "
            "candidate_effects matrix containing every current candidate ID and "
            "satisfy the final JSON schema exactly."
        ),
    }
    assert_no_gold_leak(repair_payload)
    repaired = _clean(
        cache.call(f"{module}Repair", prompt, repair_payload),
        view,
    )
    repaired["repair_used"] = True
    return repaired


def _audit_record(
    *,
    arm: str,
    replicate: int,
    case_id: str,
    raw: Mapping[str, Any],
    inputs: Mapping[str, Any],
    composed,
) -> dict[str, Any]:
    selected_ids = list(raw.get("ranked_fact_ids") or [])[:2]
    audit = isolated._reference_audit(
        selected_ids,
        facts=inputs["facts"],
        annotation=inputs["case"]["annotation"],
        composed=composed,
    )
    audit["schema_invalid"] = not bool(raw.get("schema_valid", True))
    return {
        "arm": arm,
        "replicate": replicate,
        "case_id": case_id,
        "selected_ids": selected_ids,
        "raw": dict(raw),
        "audit": audit,
    }


def _aggregate(records: list[dict[str, Any]]) -> dict[str, Any]:
    result = isolated._aggregate(records)
    result["schema_invalid_rate"] = (
        sum(bool(row["audit"]["schema_invalid"]) for row in records) / len(records)
        if records else 0.0
    )
    return result


def _load_current(
    path: Path,
    *,
    replicates: int,
    case_inputs: Mapping[str, Mapping[str, Any]],
    composed,
) -> tuple[list[dict[str, Any]], dict[tuple[int, str], dict[str, Any]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    records: list[dict[str, Any]] = []
    by_key: dict[tuple[int, str], dict[str, Any]] = {}
    for row in payload.get("records") or []:
        if row.get("arm") != "contrastive":
            continue
        replicate = int(row["replicate"])
        case_id = str(row["case_id"])
        if replicate > replicates or case_id not in case_inputs:
            continue
        raw = dict(row.get("raw") or {})
        raw.setdefault("schema_valid", True)
        record = _audit_record(
            arm="contrastive_current",
            replicate=replicate,
            case_id=case_id,
            raw=raw,
            inputs=case_inputs[case_id],
            composed=composed,
        )
        records.append(record)
        by_key[(replicate, case_id)] = raw
    expected = replicates * len(case_inputs)
    if len(records) != expected:
        raise ValueError(
            f"current contrastive records incomplete: {len(records)} != {expected}"
        )
    return records, by_key


def run(args: argparse.Namespace) -> dict[str, Any]:
    args.output_dir.mkdir(parents=True, exist_ok=True)
    composed = bfs._load_module("anti_anchor_composed", bfs.COMPOSED_SCRIPT)
    partial = bfs._load_module("anti_anchor_partial", bfs.PARTIAL_SCRIPT)
    talp = bfs._load_module("anti_anchor_talp", bfs.TALP_SCRIPT)
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
        case_inputs[case["id"]] = {
            "case": case,
            "facts": facts,
            "view": _selector_view(
                isolated._selection_payload(case, frozen_tree, facts, blocks)
            ),
        }

    current, current_by_key = _load_current(
        args.current_summary,
        replicates=args.replicates,
        case_inputs=case_inputs,
        composed=composed,
    )
    anti_records: list[dict[str, Any]] = []
    debate_records: list[dict[str, Any]] = []
    for replicate in range(1, args.replicates + 1):
        client = RobustLLMClient(
            model=args.model,
            call_timeout=args.call_timeout,
            max_retries=5,
            timeout_retry_cap=2,
            temperature=args.temperature,
        )
        anti_cache = bfs.CachedLLM(
            client,
            args.output_dir / f"anti_anchor_r{replicate:02d}_cache.json",
            args.model,
        )
        debate_cache = bfs.CachedLLM(
            client,
            args.output_dir / f"debate_r{replicate:02d}_cache.json",
            args.model,
        )
        for case_id, inputs in case_inputs.items():
            view = inputs["view"]
            anti_raw = _call_with_schema_repair(
                anti_cache,
                module="L1AntiAnchorEvidenceSelector",
                prompt=ANTI_PROMPT,
                payload=view,
                view=view,
            )
            anti_records.append(_audit_record(
                arm="anti_anchor_prompt",
                replicate=replicate,
                case_id=case_id,
                raw=anti_raw,
                inputs=inputs,
                composed=composed,
            ))
            debate_payload = {
                **view,
                "proposal_a_contrastive": current_by_key[(replicate, case_id)],
                "proposal_b_anti_anchor": anti_raw,
            }
            assert_no_gold_leak(debate_payload)
            debate_raw = _call_with_schema_repair(
                debate_cache,
                module="L1SelectionDebateArbiter",
                prompt=ARBITER_PROMPT,
                payload=debate_payload,
                view=view,
            )
            debate_records.append(_audit_record(
                arm="debate_arbiter",
                replicate=replicate,
                case_id=case_id,
                raw=debate_raw,
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
            "contrastive_current": "cached independent proposal A",
            "anti_anchor_prompt": "counterfactual prompt-only proposal B",
            "debate_arbiter": "extra LLM agent adjudicates A, B, and full catalogue",
            "scope": "selection only; no direction allocation or posterior update",
        },
        "metric_note": (
            "SELECT and anchoring proxies use repository _best_reference; "
            "known Jaccard semantic matcher errors remain."
        ),
        "arms": {
            "contrastive_current": _aggregate(current),
            "anti_anchor_prompt": _aggregate(anti_records),
            "debate_arbiter": _aggregate(debate_records),
        },
        "paired_case_bootstrap": {
            "anti_minus_current": isolated._paired_case_bootstrap(
                current, anti_records,
            ),
            "debate_minus_current": isolated._paired_case_bootstrap(
                current, debate_records,
            ),
            "debate_minus_anti": isolated._paired_case_bootstrap(
                anti_records, debate_records,
            ),
        },
        "records": current + anti_records + debate_records,
    }
    (args.output_dir / "summary.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=bfs.DEFAULT_MODEL)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--replicates", type=int, default=1)
    parser.add_argument("--call-timeout", type=float, default=180.0)
    parser.add_argument("--cases", default="")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument(
        "--current-summary",
        type=Path,
        default=ROOT / "logs" / "l1_contrastive_selection_isolated_v1"
        / "summary.json",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "logs" / "l1_anti_anchor_debate_isolated",
    )
    return parser.parse_args()


if __name__ == "__main__":
    result = run(parse_args())
    print(json.dumps({
        name: values["mean_across_replicates"]
        for name, values in result["arms"].items()
    }, ensure_ascii=False, indent=2))
