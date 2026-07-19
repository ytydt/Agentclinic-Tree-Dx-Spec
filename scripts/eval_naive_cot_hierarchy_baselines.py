#!/usr/bin/env python3
"""Evaluate three Naive CoT replacements against the frozen BFS hierarchy."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import statistics
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import eval_l1_evidence_bfs as bfs  # noqa: E402
import eval_l2_competition_strategies as base  # noqa: E402
import eval_l2_joint_dynamic_pipeline as joint  # noqa: E402
from freeze_naive_cot_bfs_knowledge import (  # noqa: E402
    select_arm_blind_bundle,
)
from agentclinic_tree_dx.l1_evidence_bfs import (  # noqa: E402
    assert_no_gold_leak,
    stable_hash,
)
from agentclinic_tree_dx.llm_client import RobustLLMClient  # noqa: E402

PROMPT_DIR = ROOT / "src" / "agentclinic_tree_dx" / "prompts"
N0_PROMPT_PATH = PROMPT_DIR / "naive_cot_vignette_top2.txt"
N1_PROMPT_PATH = PROMPT_DIR / "naive_cot_list_top2.txt"
N2_PROMPT_PATH = PROMPT_DIR / "naive_cot_l2_local_top2.txt"
KNOWLEDGE_FIXTURE = (
    ROOT / "eval_fixtures" / "naive_cot_bfs_knowledge_v1.json"
)
MANUAL_ADJUDICATION = (
    ROOT / "eval_fixtures" / "naive_cot_vignette_manual_gold_v1.json"
)
DEFAULT_OUTPUT = (
    ROOT / "logs" / "naive_cot_hierarchy_baselines_v1"
)
ARMS = (
    "N0-CoT-vignette-free",
    "N1-CoT-branch-only-hierarchy",
    "N2-CoT-L2-local-only",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    temp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp.replace(path)


def _knowledge_fixture(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    fixture = json.loads(path.read_text(encoding="utf-8"))
    expected = str(fixture.pop("fixture_hash"))
    if stable_hash(fixture) != expected:
        raise ValueError("Naive CoT BFS knowledge fixture hash mismatch")
    fixture["fixture_hash"] = expected
    cases = {
        str(row["case_id"]): dict(row)
        for row in fixture.get("cases") or ()
    }
    return fixture, cases


def _knowledge_chunks(case_asset: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Expose identical minimal text records to every arm."""
    return [
        {
            "access_id": str(row["access_id"]),
            "source": str(row.get("source") or ""),
            "text": str(row.get("text") or ""),
        }
        for row in case_asset.get("knowledge_chunks") or ()
    ]


def clean_free_top2(
    response: Mapping[str, Any],
    allowed_access_ids: Sequence[str],
) -> dict[str, Any]:
    rows = response.get("top2_diagnoses") or ()
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        rows = ()
    cleaned = []
    rejected = []
    allowed = set(allowed_access_ids)
    seen_names = set()
    for row in rows:
        if not isinstance(row, Mapping):
            rejected.append("diagnosis_row_not_object")
            continue
        diagnosis = str(row.get("diagnosis") or "").strip()
        key = diagnosis.casefold()
        if not diagnosis:
            rejected.append("empty_diagnosis")
            continue
        if key in seen_names:
            rejected.append("duplicate_diagnosis")
            continue
        seen_names.add(key)
        raw_access = row.get("knowledge_access_ids") or ()
        if isinstance(raw_access, str):
            raw_access = [raw_access]
        access_ids = [
            str(value) for value in raw_access
            if str(value) in allowed
        ]
        invalid_access = [
            str(value) for value in raw_access
            if str(value) not in allowed
        ]
        if invalid_access:
            rejected.append("unknown_knowledge_access_id")
        cleaned.append({
            "diagnosis": diagnosis,
            "reasoning_summary": str(
                row.get("reasoning_summary") or ""
            ).strip(),
            "knowledge_access_ids": list(dict.fromkeys(access_ids)),
        })
    valid = len(cleaned) == 2 and not rejected
    return {
        "schema_valid": valid,
        "top2_diagnoses": cleaned if valid else [],
        "rejected": rejected or (
            [] if len(cleaned) == 2 else ["requires_exactly_two_diagnoses"]
        ),
        "raw": dict(response),
    }


def clean_list_top2(
    response: Mapping[str, Any],
    candidate_ids: Sequence[str],
    allowed_access_ids: Sequence[str],
) -> dict[str, Any]:
    expected = min(2, len(candidate_ids))
    raw_ids = (
        response.get("top_candidate_ids")
        or response.get("ranked_candidate_ids")
        or ()
    )
    if isinstance(raw_ids, str):
        raw_ids = [raw_ids]
    values = [str(value) for value in raw_ids]
    allowed = set(candidate_ids)
    selected = []
    rejected = []
    for candidate_id in values:
        if candidate_id not in allowed:
            rejected.append("unknown_candidate_id")
        elif candidate_id in selected:
            rejected.append("duplicate_candidate_id")
        else:
            selected.append(candidate_id)
    raw_access = response.get("knowledge_access_ids") or ()
    if isinstance(raw_access, str):
        raw_access = [raw_access]
    allowed_knowledge = set(allowed_access_ids)
    invalid_access = [
        str(value) for value in raw_access
        if str(value) not in allowed_knowledge
    ]
    if invalid_access:
        rejected.append("unknown_knowledge_access_id")
    valid = len(selected) == expected and not rejected
    return {
        "schema_valid": valid,
        "top_candidate_ids": selected if valid else [],
        "reasoning_summary": dict(
            response.get("reasoning_summary") or {}
        ),
        "knowledge_access_ids": list(dict.fromkeys(
            str(value) for value in raw_access
            if str(value) in allowed_knowledge
        )),
        "rejected": rejected or (
            [] if len(selected) == expected
            else [f"requires_exactly_{expected}_candidate_ids"]
        ),
        "raw": dict(response),
    }


def _call_free_top2(
    *,
    cache,
    prompt: str,
    payload: Mapping[str, Any],
    module: str = "NaiveCoTVignetteTop2",
) -> dict[str, Any]:
    assert_no_gold_leak(payload)
    raw = cache.call(module, prompt, payload)
    allowed = [
        str(row["access_id"])
        for row in payload.get("knowledge_chunks") or ()
    ]
    cleaned = clean_free_top2(raw, allowed)
    repair_used = False
    if not cleaned["schema_valid"]:
        repair_payload = {
            **payload,
            "invalid_response": raw,
            "validation_errors": cleaned["rejected"],
            "schema_repair": (
                "Return exactly two distinct concrete disease names using "
                "the required JSON schema. Do not return tree IDs."
            ),
        }
        assert_no_gold_leak(repair_payload)
        repaired = cache.call(
            f"{module}Repair", prompt, repair_payload,
        )
        cleaned = clean_free_top2(repaired, allowed)
        repair_used = True
    return {**cleaned, "repair_used": repair_used}


def _call_list_top2(
    *,
    cache,
    module: str,
    prompt: str,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    candidate_ids = [
        str(row["id"]) for row in payload.get("candidates") or ()
    ]
    allowed_access = [
        str(row["access_id"])
        for row in payload.get("knowledge_chunks") or ()
    ]
    if not candidate_ids:
        return {
            "schema_valid": False,
            "top_candidate_ids": [],
            "reasoning_summary": {},
            "knowledge_access_ids": [],
            "rejected": ["empty_candidate_scope"],
            "repair_used": False,
            "raw": {},
        }
    if len(candidate_ids) == 1:
        return {
            "schema_valid": True,
            "top_candidate_ids": candidate_ids,
            "reasoning_summary": {
                candidate_ids[0]: "only supplied candidate"
            },
            "knowledge_access_ids": [],
            "rejected": [],
            "repair_used": False,
            "raw": {"singleton_shortcut": True},
        }
    assert_no_gold_leak(payload)
    raw = cache.call(module, prompt, payload)
    cleaned = clean_list_top2(raw, candidate_ids, allowed_access)
    repair_used = False
    if not cleaned["schema_valid"]:
        repair_payload = {
            **payload,
            "invalid_response": raw,
            "validation_errors": cleaned["rejected"],
            "schema_repair": (
                "Return exactly two distinct IDs from candidates, best first, "
                "using the required JSON schema."
            ),
        }
        assert_no_gold_leak(repair_payload)
        repaired = cache.call(f"{module}Repair", prompt, repair_payload)
        cleaned = clean_list_top2(
            repaired, candidate_ids, allowed_access,
        )
        repair_used = True
    return {**cleaned, "repair_used": repair_used}


def _branch_rows(tree_state, *, level: int) -> list[dict[str, Any]]:
    rows = []
    for branch in tree_state.branches.values():
        if int(branch.level) != level:
            continue
        if level == 2 and branch.status == "closed_for_now":
            continue
        row = {
            "id": str(branch.id),
            "label": str(branch.label),
            "prior": float(branch.prior),
        }
        if level == 2:
            parent = tree_state.branches[str(branch.parent)]
            row.update({
                "parent_id": str(parent.id),
                "parent_label": str(parent.label),
                "parent_prior": float(parent.prior),
            })
        rows.append(row)
    return sorted(rows, key=lambda row: str(row["id"]))


def _children_rows(tree_state, parent_id: str) -> list[dict[str, Any]]:
    return [
        row for row in _branch_rows(tree_state, level=2)
        if row["parent_id"] == parent_id
    ]


def _mrr2_from_rank(rank: int | None) -> float:
    if rank == 1:
        return 1.0
    if rank == 2:
        return 0.5
    return 0.0


def _score_tree_top2(
    ranking: Sequence[str],
    gold: Mapping[str, Any],
    *,
    scope_ids: Sequence[str],
    error_attribution: str | None = None,
) -> dict[str, Any]:
    audit = base.score_ranking(
        ranking,
        gold,
        scope_ids=scope_ids,
        schema_valid=bool(ranking),
    )
    audit["mrr2"] = _mrr2_from_rank(audit["rank"])
    if error_attribution and audit["error_attribution"] != "success":
        audit["error_attribution"] = error_attribution
    return audit


def _n0_record(
    *,
    replicate: int,
    case: Mapping[str, Any],
    knowledge_chunks: Sequence[Mapping[str, Any]],
    knowledge_hash: str,
    cache,
    prompt: str,
) -> dict[str, Any]:
    payload = {
        "vignette": str(case["case_text"]),
        "knowledge_chunks": list(knowledge_chunks),
    }
    output = _call_free_top2(
        cache=cache, prompt=prompt, payload=payload,
    )
    return {
        "schema_version": 1,
        "arm": ARMS[0],
        "replicate": replicate,
        "case_id": str(case["id"]),
        "knowledge_bundle_hash": knowledge_hash,
        "knowledge_access_ids": [
            str(row["access_id"]) for row in knowledge_chunks
        ],
        "input": payload,
        "output": output,
        "audit": None,
        "schema_valid": bool(output["schema_valid"]),
        "repair_used": bool(output["repair_used"]),
        "estimated_llm_calls": 1 + int(output["repair_used"]),
    }


def _n1_record(
    *,
    replicate: int,
    case: Mapping[str, Any],
    knowledge_chunks: Sequence[Mapping[str, Any]],
    knowledge_hash: str,
    tree_state,
    gold: Mapping[str, Any],
    cache,
    prompt: str,
) -> dict[str, Any]:
    vignette = str(case["case_text"])
    l1_candidates = _branch_rows(tree_state, level=1)
    l1_payload = {
        "stage": "l1_top2",
        "vignette": vignette,
        "knowledge_chunks": list(knowledge_chunks),
        "candidates": l1_candidates,
    }
    l1_output = _call_list_top2(
        cache=cache,
        module="NaiveCoTBranchOnly_L1",
        prompt=prompt,
        payload=l1_payload,
    )
    selected_parents = list(l1_output["top_candidate_ids"])
    local_outputs = {}
    pooled = []
    for parent_id in selected_parents:
        candidates = _children_rows(tree_state, parent_id)
        payload = {
            "stage": "within_l1_top2",
            "vignette": vignette,
            "knowledge_chunks": list(knowledge_chunks),
            "selected_parent_id": parent_id,
            "candidates": candidates,
        }
        output = _call_list_top2(
            cache=cache,
            module="NaiveCoTBranchOnly_Within",
            prompt=prompt,
            payload=payload,
        )
        local_outputs[parent_id] = {
            "payload": payload,
            "output": output,
        }
        by_id = {str(row["id"]): row for row in candidates}
        pooled.extend(
            by_id[candidate_id]
            for candidate_id in output["top_candidate_ids"]
            if candidate_id in by_id
        )
    pooled_by_id = {str(row["id"]): dict(row) for row in pooled}
    final_candidates = list(pooled_by_id.values())
    final_payload = {
        "stage": "between_l1_top2",
        "vignette": vignette,
        "knowledge_chunks": list(knowledge_chunks),
        "parent_prior_mode": "frozen_initial_l1_prior",
        "candidates": final_candidates,
    }
    if l1_output["schema_valid"] and all(
        row["output"]["schema_valid"]
        for row in local_outputs.values()
    ):
        final_output = _call_list_top2(
            cache=cache,
            module="NaiveCoTBranchOnly_Between",
            prompt=prompt,
            payload=final_payload,
        )
    else:
        final_output = {
            "schema_valid": False,
            "top_candidate_ids": [],
            "reasoning_summary": {},
            "knowledge_access_ids": [],
            "rejected": ["upstream_list_selection_failure"],
            "repair_used": False,
            "raw": {},
        }
    ranking = list(final_output["top_candidate_ids"])
    acceptable = {
        str(row["id"]) for row in gold.get("acceptable_l2") or ()
    }
    acceptable_parents = {
        str(row["parent_id"]) for row in gold.get("acceptable_l2") or ()
    }
    local_scope = set(pooled_by_id)
    if gold.get("status") == "absent":
        attribution = "gold_absent"
    elif not l1_output["schema_valid"] or not final_output["schema_valid"]:
        attribution = "schema_failure"
    elif not (acceptable_parents & set(selected_parents)):
        attribution = "l1_top2_gate_elimination"
    elif not (acceptable & local_scope):
        attribution = "within_group_top2_elimination"
    elif not (acceptable & set(ranking[:1])):
        attribution = "between_group_final_miss"
    else:
        attribution = "success"
    audit = _score_tree_top2(
        ranking,
        gold,
        scope_ids=list(pooled_by_id),
        error_attribution=attribution,
    )
    audit["error_attribution"] = attribution
    calls = (
        1 + int(l1_output.get("repair_used"))
        + sum(
            1 + int(row["output"].get("repair_used"))
            for row in local_outputs.values()
            if not row["output"].get("raw", {}).get("singleton_shortcut")
        )
        + 1 + int(final_output.get("repair_used"))
    )
    return {
        "schema_version": 1,
        "arm": ARMS[1],
        "replicate": replicate,
        "case_id": str(case["id"]),
        "knowledge_bundle_hash": knowledge_hash,
        "knowledge_access_ids": [
            str(row["access_id"]) for row in knowledge_chunks
        ],
        "l1_stage": {"payload": l1_payload, "output": l1_output},
        "within_stages": local_outputs,
        "between_stage": {
            "payload": final_payload,
            "output": final_output,
        },
        "output": {
            "ranking": ranking,
            "top2": [
                pooled_by_id[candidate_id]
                for candidate_id in ranking
                if candidate_id in pooled_by_id
            ],
        },
        "audit": audit,
        "schema_valid": bool(final_output["schema_valid"]),
        "repair_used": bool(
            l1_output.get("repair_used")
            or final_output.get("repair_used")
            or any(
                row["output"].get("repair_used")
                for row in local_outputs.values()
            )
        ),
        "estimated_llm_calls": calls,
    }


def _n2_record(
    *,
    replicate: int,
    case: Mapping[str, Any],
    auto_asset: Mapping[str, Any],
    frozen_asset: Mapping[str, Any],
    full_record: Mapping[str, Any],
    knowledge_chunks: Sequence[Mapping[str, Any]],
    knowledge_hash: str,
    tree_state,
    gold: Mapping[str, Any],
    cache,
    local_prompt: str,
    arbiter_prompt: str,
) -> dict[str, Any]:
    findings = list(auto_asset["full_findings"])
    order = joint.true_consumption_order(full_record)
    selected_facts = joint._facts_for_ids(findings, order[:2])
    l1_rows = list(frozen_asset["l1_posteriors"])
    parent_scores = {
        str(row["id"]): float(row["posterior"]) for row in l1_rows
    }
    local_outputs = {}
    champions = []
    for parent_id in [str(row["id"]) for row in l1_rows]:
        candidates = _children_rows(tree_state, parent_id)
        payload = {
            "vignette": str(case["case_text"]),
            "available_findings": findings,
            "selected_evidence": selected_facts,
            "knowledge_chunks": list(knowledge_chunks),
            "selected_parent_id": parent_id,
            "candidates": candidates,
        }
        output = _call_list_top2(
            cache=cache,
            module="NaiveCoTL2Local",
            prompt=local_prompt,
            payload=payload,
        )
        local_outputs[parent_id] = {
            "payload": payload,
            "output": output,
        }
        if output["schema_valid"] and output["top_candidate_ids"]:
            winner_id = str(output["top_candidate_ids"][0])
            winner = next(
                row for row in candidates if row["id"] == winner_id
            )
            parent = tree_state.branches[parent_id]
            champions.append({
                "id": winner_id,
                "label": winner["label"],
                "parent_id": parent_id,
                "parent_label": str(parent.label),
                "local_score": 1.0,
                "parent_posterior": parent_scores[parent_id],
                "local_fact_rationales": dict(
                    output.get("reasoning_summary") or {}
                ),
                "local_top2_ids": list(
                    output["top_candidate_ids"]
                ),
            })
    all_valid = (
        len(champions) == len(l1_rows)
        and all(
            row["output"]["schema_valid"]
            for row in local_outputs.values()
        )
    )
    if all_valid and champions:
        arbiter = base._arbitrate_champions(
            cache=cache,
            module="NaiveCoTL2Local_OriginalChampionArbiter",
            prompt=arbiter_prompt,
            case_text=str(case["case_text"]),
            findings=findings,
            selected_facts=selected_facts,
            champions=champions,
            include_parent_prior=True,
        )
    else:
        arbiter = {
            "schema_valid": False,
            "ranking": [],
            "repair_used": False,
            "champions": champions,
            "rejected": ["local_top2_failure"],
        }
    ranking = list(arbiter.get("ranking") or ())[:2]
    champion_ids = [str(row["id"]) for row in champions]
    audit = _score_tree_top2(
        ranking,
        gold,
        scope_ids=champion_ids,
    )
    calls = sum(
        1 + int(row["output"].get("repair_used"))
        for row in local_outputs.values()
        if not row["output"].get("raw", {}).get("singleton_shortcut")
    ) + (1 + int(arbiter.get("repair_used")) if champions else 0)
    return {
        "schema_version": 1,
        "arm": ARMS[2],
        "replicate": replicate,
        "case_id": str(case["id"]),
        "knowledge_bundle_hash": knowledge_hash,
        "knowledge_access_ids": [
            str(row["access_id"]) for row in knowledge_chunks
        ],
        "selected_fact_ids": [
            str(row["id"]) for row in selected_facts
        ],
        "l1_posteriors": l1_rows,
        "local_stages": local_outputs,
        "champions": champions,
        "arbiter": arbiter,
        "output": {
            "ranking": ranking,
            "full_arbiter_ranking": list(
                arbiter.get("ranking") or ()
            ),
        },
        "audit": audit,
        "schema_valid": bool(arbiter.get("schema_valid")),
        "repair_used": bool(
            arbiter.get("repair_used")
            or any(
                row["output"].get("repair_used")
                for row in local_outputs.values()
            )
        ),
        "estimated_llm_calls": calls,
    }


def _case_trace(
    *,
    replicate: int,
    case: Mapping[str, Any],
    auto_asset: Mapping[str, Any],
    frozen_asset: Mapping[str, Any],
    full_record: Mapping[str, Any],
    knowledge_asset: Mapping[str, Any],
    gold: Mapping[str, Any],
    tree_state,
    cache,
    prompts: Mapping[str, str],
) -> dict[str, Any]:
    knowledge = _knowledge_chunks(knowledge_asset)
    bundle_hash = str(knowledge_asset["served_bundle_hash"])
    return {
        "schema_version": 1,
        "replicate": replicate,
        "case_id": str(case["id"]),
        "knowledge_bundle_hash": bundle_hash,
        "records": [
            _n0_record(
                replicate=replicate,
                case=case,
                knowledge_chunks=knowledge,
                knowledge_hash=bundle_hash,
                cache=cache,
                prompt=prompts["n0"],
            ),
            _n1_record(
                replicate=replicate,
                case=case,
                knowledge_chunks=knowledge,
                knowledge_hash=bundle_hash,
                tree_state=tree_state,
                gold=gold,
                cache=cache,
                prompt=prompts["n1"],
            ),
            _n2_record(
                replicate=replicate,
                case=case,
                auto_asset=auto_asset,
                frozen_asset=frozen_asset,
                full_record=full_record,
                knowledge_chunks=knowledge,
                knowledge_hash=bundle_hash,
                tree_state=tree_state,
                gold=gold,
                cache=cache,
                local_prompt=prompts["n2"],
                arbiter_prompt=prompts["arbiter"],
            ),
        ],
    }


def _run_replicate(
    *,
    replicate: int,
    args: argparse.Namespace,
    cases: Sequence[Mapping[str, Any]],
    auto_cases: Mapping[str, Mapping[str, Any]],
    frozen_assets: Mapping[tuple[int, str], Mapping[str, Any]],
    full_records: Mapping[tuple[int, str], Mapping[str, Any]],
    knowledge_cases: Mapping[str, Mapping[str, Any]],
    gold_cases: Mapping[str, Mapping[str, Any]],
    prompts: Mapping[str, str],
) -> list[dict[str, Any]]:
    composed = bfs._load_module(
        f"naive_cot_composed_r{replicate}", bfs.COMPOSED_SCRIPT,
    )
    client = RobustLLMClient(
        model=args.model,
        call_timeout=args.call_timeout,
        max_retries=5,
        timeout_retry_cap=2,
        temperature=args.temperature,
    )
    cache = bfs.CachedLLM(
        client,
        args.output_dir / "cache" / f"r{replicate:02d}.json",
        args.model,
    )
    records = []
    for case in cases:
        case_id = str(case["id"])
        frozen_asset = frozen_assets[(replicate, case_id)]
        full_record = full_records[(replicate, case_id)]
        knowledge_asset = knowledge_cases[case_id]
        tree_payload = base._tree_payload(args.tree_dir, case_id)
        identity = {
            "protocol_version": 1,
            "model": args.model,
            "temperature": args.temperature,
            "case_text_hash": stable_hash(case["case_text"]),
            "tree_hash": stable_hash(tree_payload),
            "auto_asset_hash": stable_hash(auto_cases[case_id]),
            "frozen_l1_asset_hash": frozen_asset["asset_hash"],
            "full_record_hash": stable_hash(full_record),
            "knowledge_bundle_hash": knowledge_asset[
                "served_bundle_hash"
            ],
            "gold_hash": stable_hash(gold_cases[case_id]),
            "prompt_hashes": {
                key: hashlib.sha256(value.encode("utf-8")).hexdigest()
                for key, value in prompts.items()
            },
        }
        output_path = (
            args.output_dir / "traces"
            / f"r{replicate:02d}__{case_id}.json"
        )
        if output_path.is_file():
            existing = json.loads(
                output_path.read_text(encoding="utf-8")
            )
            if existing.get("identity") == identity:
                records.extend(existing["records"])
                continue
        tree_state = composed._deserialize_state(tree_payload["state"])
        trace = _case_trace(
            replicate=replicate,
            case=case,
            auto_asset=auto_cases[case_id],
            frozen_asset=frozen_asset,
            full_record=full_record,
            knowledge_asset=knowledge_asset,
            gold=gold_cases[case_id],
            tree_state=tree_state,
            cache=cache,
            prompts=prompts,
        )
        trace["identity"] = identity
        _atomic_json(output_path, trace)
        records.extend(trace["records"])
        print(
            f"[naive-cot] r{replicate:02d} {case_id} complete",
            flush=True,
        )
    return records


def _manual_fixture(path: Path) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    if not path.is_file():
        return None, {}
    fixture = json.loads(path.read_text(encoding="utf-8"))
    expected = str(fixture.pop("fixture_hash"))
    if stable_hash(fixture) != expected:
        raise ValueError("manual Naive CoT adjudication hash mismatch")
    fixture["fixture_hash"] = expected
    rows = {
        f"{int(row['replicate'])}::{row['case_id']}": dict(row)
        for row in fixture.get("records") or ()
    }
    return fixture, rows


def _apply_manual_scores(
    records: Sequence[dict[str, Any]],
    adjudication: Mapping[str, Mapping[str, Any]],
    gold_cases: Mapping[str, Mapping[str, Any]],
) -> None:
    for record in records:
        if record["arm"] != ARMS[0]:
            continue
        key = f"{int(record['replicate'])}::{record['case_id']}"
        row = adjudication.get(key)
        if row is None:
            record["audit"] = None
            continue
        current_answers = [
            str(value["diagnosis"])
            for value in record["output"].get("top2_diagnoses") or ()
        ]
        current_answers = (current_answers + ["", ""])[:2]
        frozen_answers = [
            str(row.get("answer_1") or ""),
            str(row.get("answer_2") or ""),
        ]
        if current_answers != frozen_answers:
            raise ValueError(
                f"{key} manual adjudication answers do not match trace"
            )
        rank = row.get("best_rank")
        if rank not in (1, 2, None):
            raise ValueError(f"{key} invalid manual best_rank")
        gold = gold_cases[str(record["case_id"])]
        record["audit"] = {
            "gold_present": gold.get("status") != "absent",
            "gold_status": gold.get("status"),
            "top1": rank == 1,
            "top2": rank in (1, 2),
            "rank": rank,
            "mrr2": _mrr2_from_rank(rank),
            "structural_reach": True,
            "error_attribution": (
                "success" if rank == 1
                else "free_text_rank2" if rank == 2
                else "free_text_miss"
            ),
            "manual_adjudication": dict(row),
        }


def _write_answer_sheet(
    records: Sequence[Mapping[str, Any]],
    gold_cases: Mapping[str, Mapping[str, Any]],
    path: Path,
) -> None:
    rows = []
    for record in records:
        if record["arm"] != ARMS[0]:
            continue
        diagnoses = list(
            record["output"].get("top2_diagnoses") or ()
        )
        rows.append({
            "replicate": int(record["replicate"]),
            "case_id": str(record["case_id"]),
            "answer_1": (
                diagnoses[0]["diagnosis"] if len(diagnoses) > 0 else ""
            ),
            "answer_2": (
                diagnoses[1]["diagnosis"] if len(diagnoses) > 1 else ""
            ),
            "gold_diagnosis_for_manual_review": str(
                gold_cases[str(record["case_id"])]["gold_diagnosis"]
            ),
            "best_rank": None,
            "accepted_answer": "",
            "adjudication_reason": "",
            "reviewer": "",
        })
    _atomic_json(path, {
        "schema_version": 1,
        "purpose": (
            "Manual review sheet; do not use an automatic or LLM mapper"
        ),
        "records": sorted(
            rows, key=lambda row: (row["replicate"], row["case_id"]),
        ),
    })


def _arm_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    scored = [row for row in rows if row.get("audit") is not None]
    present = [
        row for row in scored if row["audit"]["gold_present"]
    ]

    def metrics(values):
        if not values:
            return {
                "top1": None, "top2": None, "mrr2": None,
                "n_records": 0,
            }
        return {
            "top1": statistics.fmean(
                bool(row["audit"]["top1"]) for row in values
            ),
            "top2": statistics.fmean(
                bool(row["audit"]["top2"]) for row in values
            ),
            "mrr2": statistics.fmean(
                float(row["audit"]["mrr2"]) for row in values
            ),
            "n_records": len(values),
        }
    top_ids_by_case = {}
    for row in rows:
        if row["arm"] == ARMS[0]:
            diagnoses = row["output"].get("top2_diagnoses") or ()
            top = (
                str(diagnoses[0]["diagnosis"]).casefold()
                if diagnoses else ""
            )
        else:
            ranking = row["output"].get("ranking") or ()
            top = str(ranking[0]) if ranking else ""
        top_ids_by_case.setdefault(str(row["case_id"]), []).append(top)
    return {
        "all17": metrics(scored),
        "gold_present": metrics(present),
        "schema_valid_rate": statistics.fmean(
            bool(row["schema_valid"]) for row in rows
        ),
        "repair_rate": statistics.fmean(
            bool(row["repair_used"]) for row in rows
        ),
        "mean_estimated_llm_calls": statistics.fmean(
            int(row["estimated_llm_calls"]) for row in rows
        ),
        "top1_stability": statistics.fmean(
            max(Counter(values).values()) / len(values)
            for values in top_ids_by_case.values()
        ),
        "error_attribution": dict(Counter(
            str(row["audit"]["error_attribution"])
            for row in scored
        )),
        "knowledge_citation": _citation_audit(rows),
    }


def _record_citations(row: Mapping[str, Any]) -> list[str]:
    cited = []
    if row["arm"] == ARMS[0]:
        outputs = row["output"].get("top2_diagnoses") or ()
        for output in outputs:
            cited.extend(output.get("knowledge_access_ids") or ())
    elif row["arm"] == ARMS[1]:
        outputs = [row["l1_stage"]["output"]]
        outputs.extend(
            stage["output"]
            for stage in row["within_stages"].values()
        )
        outputs.append(row["between_stage"]["output"])
        for output in outputs:
            cited.extend(output.get("knowledge_access_ids") or ())
    elif row["arm"] == ARMS[2]:
        for stage in row["local_stages"].values():
            cited.extend(
                stage["output"].get("knowledge_access_ids") or ()
            )
    return list(dict.fromkeys(str(value) for value in cited))


def _citation_audit(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    citations = [_record_citations(row) for row in rows]
    with_knowledge = [
        (row, values) for row, values in zip(rows, citations)
        if row.get("knowledge_access_ids")
    ]
    return {
        "record_citation_rate": statistics.fmean(
            bool(values) for values in citations
        ) if rows else 0.0,
        "eligible_record_citation_rate": statistics.fmean(
            bool(values) for _, values in with_knowledge
        ) if with_knowledge else None,
        "mean_unique_citations": statistics.fmean(
            len(values) for values in citations
        ) if rows else 0.0,
        "records_without_served_knowledge": sum(
            not bool(row.get("knowledge_access_ids")) for row in rows
        ),
    }


def _paired_transitions(
    baseline: Sequence[Mapping[str, Any]],
    treatment: Sequence[Mapping[str, Any]],
    *,
    metric: str,
) -> dict[str, Any]:
    left = {
        (int(row["replicate"]), str(row["case_id"])): row
        for row in baseline
        if row.get("audit") is not None
        and row["audit"]["gold_present"]
    }
    right = {
        (int(row["replicate"]), str(row["case_id"])): row
        for row in treatment
        if row.get("audit") is not None
        and row["audit"]["gold_present"]
    }
    keys = sorted(set(left) & set(right))
    deltas = {
        key: (
            float(right[key]["audit"][metric])
            - float(left[key]["audit"][metric])
        )
        for key in keys
    }
    per_case = {}
    for case_id in sorted({key[1] for key in keys}):
        values = [
            delta for (replicate, cid), delta in deltas.items()
            if cid == case_id
        ]
        per_case[case_id] = statistics.fmean(values)
    return {
        "paired_records": len(keys),
        "gains": sum(delta > 0 for delta in deltas.values()),
        "losses": sum(delta < 0 for delta in deltas.values()),
        "ties": sum(delta == 0 for delta in deltas.values()),
        "case_mean_deltas": per_case,
    }


def _component_decomposition(
    by_arm: Mapping[str, Sequence[Mapping[str, Any]]],
) -> dict[str, Any]:
    n0 = [
        row for row in by_arm[ARMS[0]]
        if row.get("audit") is not None
        and row["audit"]["gold_present"]
    ]
    n1 = [
        row for row in by_arm[ARMS[1]]
        if row["audit"]["gold_present"]
    ]
    n2 = [
        row for row in by_arm[ARMS[2]]
        if row["audit"]["gold_present"]
    ]
    n1_errors = Counter(
        row["audit"]["error_attribution"] for row in n1
    )
    n2_errors = Counter(
        row["audit"]["error_attribution"] for row in n2
    )
    return {
        "N0_free_diagnosis": {
            "rank1": sum(row["audit"]["rank"] == 1 for row in n0),
            "rank2": sum(row["audit"]["rank"] == 2 for row in n0),
            "miss": sum(row["audit"]["rank"] is None for row in n0),
            "schema_failures": sum(
                not row["schema_valid"] for row in n0
            ),
        },
        "N1_hierarchical_gates": {
            "l1_top2_eliminations": n1_errors[
                "l1_top2_gate_elimination"
            ],
            "within_parent_top2_eliminations": n1_errors[
                "within_group_top2_elimination"
            ],
            "between_parent_final_misses": n1_errors[
                "between_group_final_miss"
            ],
            "schema_failures": n1_errors["schema_failure"],
            "rank1_successes": n1_errors["success"],
        },
        "N2_local_replacement": {
            "upstream_l1_unreachable": n2_errors[
                "upstream_l1_unreachable"
            ],
            "final_arbiter_misses_including_rank2": n2_errors[
                "final_ranking_miss"
            ],
            "schema_failures": n2_errors["schema_failure"],
            "rank1_successes": n2_errors["success"],
            "records_with_any_repair": sum(
                bool(row["repair_used"]) for row in n2
            ),
        },
    }


def _bundle_fairness_audit(
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    by_key: dict[tuple[int, str], list[Mapping[str, Any]]] = {}
    for row in records:
        key = (int(row["replicate"]), str(row["case_id"]))
        by_key.setdefault(key, []).append(row)
    unequal = []
    for key, rows in by_key.items():
        hashes = {str(row["knowledge_bundle_hash"]) for row in rows}
        access = {
            tuple(row.get("knowledge_access_ids") or ()) for row in rows
        }
        if len(rows) != len(ARMS) or len(hashes) != 1 or len(access) != 1:
            unequal.append({
                "replicate": key[0],
                "case_id": key[1],
                "arms": [row["arm"] for row in rows],
            })
    return {
        "paired_case_replicates": len(by_key),
        "expected_arms_per_pair": len(ARMS),
        "identical_bundle_hash_and_order": not unequal,
        "unequal_pairs": unequal,
    }


def _external_a1_records(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    summary = json.loads(path.read_text(encoding="utf-8"))
    records = []
    for row in summary.get("records") or ():
        if row.get("arm") != "A1-order-fixed-f2":
            continue
        copied = dict(row)
        copied["arm"] = "REF-A1-order-fixed-f2"
        copied["audit"] = dict(row["audit"])
        copied["audit"]["mrr2"] = _mrr2_from_rank(
            row["audit"].get("rank")
        )
        records.append(copied)
    return records


def _bootstrap_delta(
    baseline: Sequence[Mapping[str, Any]],
    treatment: Sequence[Mapping[str, Any]],
    metric: str,
    n_boot: int,
) -> dict[str, Any]:
    return base._bootstrap_delta(
        baseline, treatment, metric=metric, n_boot=n_boot,
    )


def _write_csv(records: Sequence[Mapping[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=[
            "arm", "replicate", "case_id", "schema_valid",
            "top1", "top2", "mrr2", "rank",
            "error_attribution", "knowledge_bundle_hash",
        ])
        writer.writeheader()
        for row in records:
            audit = row.get("audit") or {}
            writer.writerow({
                "arm": row["arm"],
                "replicate": row["replicate"],
                "case_id": row["case_id"],
                "schema_valid": row["schema_valid"],
                "top1": audit.get("top1"),
                "top2": audit.get("top2"),
                "mrr2": audit.get("mrr2"),
                "rank": audit.get("rank"),
                "error_attribution": audit.get("error_attribution"),
                "knowledge_bundle_hash": row.get(
                    "knowledge_bundle_hash", ""
                ),
            })


def run(args: argparse.Namespace) -> dict[str, Any]:
    args.output_dir.mkdir(parents=True, exist_ok=True)
    cases = base._runtime_cases(args.cases, args.limit)
    case_ids = [str(case["id"]) for case in cases]
    auto_doc, auto_cases = base._fixture_cases(args.fixture)
    frozen_manifest, frozen_assets = base._load_frozen_assets(
        args.base_output_dir,
    )
    full_manifest, full_rows = base._load_full_records(
        args.base_output_dir,
    )
    full_records = {
        (int(row["replicate"]), str(row["case_id"])): row
        for row in full_rows
    }
    knowledge_doc, knowledge_cases = _knowledge_fixture(
        args.knowledge_fixture,
    )
    if not set(case_ids).issubset(knowledge_cases):
        raise ValueError("knowledge fixture is missing requested cases")
    gold_doc = json.loads(args.gold.read_text(encoding="utf-8"))
    gold_cases = base.validate_l2_gold(
        gold_doc,
        tree_dir=args.tree_dir,
        expected_case_ids=case_ids,
    )
    prompts = {
        "n0": N0_PROMPT_PATH.read_text(encoding="utf-8"),
        "n1": N1_PROMPT_PATH.read_text(encoding="utf-8"),
        "n2": N2_PROMPT_PATH.read_text(encoding="utf-8"),
        "arbiter": base.ARBITER_PROMPT_PATH.read_text(encoding="utf-8"),
    }
    records = []
    with ThreadPoolExecutor(
        max_workers=max(1, min(args.workers, args.replicates)),
    ) as pool:
        futures = [
            pool.submit(
                _run_replicate,
                replicate=replicate,
                args=args,
                cases=cases,
                auto_cases=auto_cases,
                frozen_assets=frozen_assets,
                full_records=full_records,
                knowledge_cases=knowledge_cases,
                gold_cases=gold_cases,
                prompts=prompts,
            )
            for replicate in range(1, args.replicates + 1)
        ]
        for future in as_completed(futures):
            records.extend(future.result())
    records.sort(key=lambda row: (
        row["arm"], int(row["replicate"]), str(row["case_id"]),
    ))
    answer_sheet = args.output_dir / "n0_manual_answer_sheet.json"
    _write_answer_sheet(records, gold_cases, answer_sheet)
    manual_doc, manual_rows = _manual_fixture(args.manual_adjudication)
    if manual_doc is not None:
        current_sheet = json.loads(
            answer_sheet.read_text(encoding="utf-8")
        )
        if stable_hash(current_sheet) != str(
            manual_doc["source_answer_sheet_hash"]
        ):
            raise ValueError(
                "manual adjudication source answer sheet hash mismatch"
            )
    _apply_manual_scores(records, manual_rows, gold_cases)
    by_arm = {
        arm: [row for row in records if row["arm"] == arm]
        for arm in ARMS
    }
    reference = _external_a1_records(args.a1_reference)
    comparisons = {}
    transitions = {}
    if reference:
        reference_present = [
            row for row in reference
            if row["audit"]["gold_present"]
        ]
        for arm, rows in by_arm.items():
            treatment = [
                row for row in rows
                if row.get("audit") is not None
                and row["audit"]["gold_present"]
            ]
            if not treatment:
                continue
            for metric in ("top1", "top2", "mrr2"):
                comparisons[
                    f"{arm}_minus_REF-A1::{metric}"
                ] = _bootstrap_delta(
                    reference_present,
                    treatment,
                    metric,
                    args.n_boot,
                )
                transitions[
                    f"{arm}_minus_REF-A1::{metric}"
                ] = _paired_transitions(
                    reference_present,
                    treatment,
                    metric=metric,
                )
    summary = {
        "schema_version": 1,
        "protocol_version": 1,
        "model": args.model,
        "temperature": args.temperature,
        "replicates": args.replicates,
        "primary_metric_scope": "14 gold-present cases",
        "mrr_definition": "MRR@2: rank1=1, rank2=0.5, else=0",
        "arms": {
            arm: _arm_summary(rows) for arm, rows in by_arm.items()
        },
        "external_reference": (
            _arm_summary(reference) if reference else None
        ),
        "paired_case_cluster_bootstrap": comparisons,
        "paired_case_transitions": transitions,
        "component_decomposition": _component_decomposition(by_arm),
        "manual_adjudication_status": {
            "path": str(args.manual_adjudication),
            "loaded": manual_doc is not None,
            "scored_records": len(manual_rows),
            "required_records": len(by_arm[ARMS[0]]),
            "answer_sheet": str(answer_sheet),
        },
        "input_hashes": {
            "auto_fixture": stable_hash(auto_doc),
            "knowledge_fixture": knowledge_doc["fixture_hash"],
            "knowledge_source_catalog": knowledge_doc[
                "source_catalog_hash"
            ],
            "gold": stable_hash(gold_doc),
            "frozen_l1_manifest": frozen_manifest[
                "frozen_manifest_hash"
            ],
            "full_l1_manifest": stable_hash(full_manifest),
            "prompts": {
                key: hashlib.sha256(value.encode("utf-8")).hexdigest()
                for key, value in prompts.items()
            },
            "harness_sha256": _sha256(Path(__file__)),
        },
        "knowledge_coverage_audit": knowledge_doc[
            "coverage_audit"
        ],
        "knowledge_bundle_fairness_audit": _bundle_fairness_audit(
            records
        ),
        "records": records,
    }
    _atomic_json(args.output_dir / "summary.json", summary)
    _write_csv(records, args.output_dir / "records.csv")
    _atomic_json(args.output_dir / "manifest.json", {
        key: value for key, value in summary.items()
        if key not in {"records", "arms", "paired_case_cluster_bootstrap"}
    })
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=bfs.DEFAULT_MODEL)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--replicates", type=int, default=3)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--call-timeout", type=float, default=240.0)
    parser.add_argument("--n-boot", type=int, default=5000)
    parser.add_argument("--cases", default="")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--fixture", type=Path, default=base.DEFAULT_FIXTURE)
    parser.add_argument("--gold", type=Path, default=base.DEFAULT_GOLD)
    parser.add_argument(
        "--tree-dir", type=Path, default=base.DEFAULT_TREE_DIR,
    )
    parser.add_argument(
        "--base-output-dir", type=Path, default=base.DEFAULT_OUTPUT,
    )
    parser.add_argument(
        "--knowledge-fixture", type=Path, default=KNOWLEDGE_FIXTURE,
    )
    parser.add_argument(
        "--manual-adjudication",
        type=Path,
        default=MANUAL_ADJUDICATION,
    )
    parser.add_argument(
        "--a1-reference",
        type=Path,
        default=(
            base.DEFAULT_OUTPUT / "l2_joint_dynamic_v1" / "summary.json"
        ),
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    summary = run(parse_args())
    print(json.dumps({
        "arms": summary["arms"],
        "external_reference": summary["external_reference"],
        "manual_adjudication_status": (
            summary["manual_adjudication_status"]
        ),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
