#!/usr/bin/env python3
"""Paired isolated A/B for chunk-grounded dual-agent L1 evidence selection."""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import statistics
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import eval_l1_anti_anchor_debate as anti_eval  # noqa: E402
import eval_l1_auto_finding_matrix as auto_eval  # noqa: E402
import eval_l1_contrastive_selection as isolated  # noqa: E402
import eval_l1_evidence_bfs as bfs  # noqa: E402
from agentclinic_tree_dx.grounded_evidence import (  # noqa: E402
    chunk_index,
    clean_chunk_request,
    clean_grounded_selection,
    hydrate_chunk_requests,
)
from agentclinic_tree_dx.l1_evidence_bfs import (  # noqa: E402
    L1ObservedFact,
    assert_no_gold_leak,
    stable_hash,
)
from agentclinic_tree_dx.llm_client import RobustLLMClient  # noqa: E402


SELECTOR_PROMPT = (
    bfs.PROMPT_DIR / "l1_grounded_evidence_selector.txt"
).read_text(encoding="utf-8")
ANTI_PROMPT = (
    bfs.PROMPT_DIR / "l1_grounded_anti_anchor_agent.txt"
).read_text(encoding="utf-8")
ARBITER_PROMPT = (
    bfs.PROMPT_DIR / "l1_grounded_selection_arbiter.txt"
).read_text(encoding="utf-8")
VERIFIER_PROMPT = (
    bfs.PROMPT_DIR / "l1_grounded_chain_verifier.txt"
).read_text(encoding="utf-8")
DEFAULT_CHUNKS = (
    ROOT / "eval_fixtures" / "l1_grounded_chunk_catalog_v1.json"
)
DEFAULT_MIXED_BASELINE = (
    ROOT / "logs" / "l1_anti_anchor_debate_isolated_v1" / "summary.json"
)
DEFAULT_AUTO_BASELINE = (
    ROOT / "logs" / "l1_auto_finding_matrix_v1" / "summary.json"
)
DEFAULT_OUTPUT = ROOT / "logs" / "l1_grounded_anti_anchor_v1"
GROUNDED_ARMS = ("G1_grounded_selector", "G2_grounded_anti", "G3_grounded_arbiter")


class CountingCache:
    def __init__(self, cached: bfs.CachedLLM) -> None:
        self.cached = cached
        self.calls = 0

    def call(
        self, module: str, prompt: str, payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        self.calls += 1
        return self.cached.call(module, prompt, payload)


def _prompt_hash(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def _base_view(view: Mapping[str, Any]) -> dict[str, Any]:
    output = dict(view)
    output["discriminator_rules"] = []
    output["evidence_provenance"] = []
    assert_no_gold_leak(output)
    return output


def _none(*, reason: str, calls: int = 0) -> dict[str, Any]:
    return {
        "verdict": "none",
        "best_fact_id": "",
        "ranked_fact_ids": [],
        "concept_keys": {},
        "comparisons": [],
        "rejected": [{"fact_id": "", "reason": reason}],
        "schema_valid": True,
        "repair_used": False,
        "citation_count": 0,
        "valid_citation_count": 0,
        "citation_integrity": 1.0,
        "grounded_chain_count": 0,
        "attempted_chain_count": 0,
        "grounding": {
            "reason": reason,
            "calls": calls,
            "catalog_excerpts": 0,
            "served_chunks": 0,
        },
    }


def _run_grounded_proposer(
    *,
    cache: CountingCache,
    module: str,
    prompt: str,
    view: Mapping[str, Any],
    excerpts: Sequence[Mapping[str, Any]],
    request_limit: int,
    grounding_policy: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not excerpts:
        output = _none(reason="no_hydrated_chunks")
        output["grounding"].update({
            "catalog_fact_count": 0,
            "eligible_fact_count": len(view["eligible_fact_ids"]),
            "fact_coverage": 0.0,
        })
        return output, []
    base_view = _base_view(view)
    catalogue = chunk_index(excerpts, include_text=False)
    allowed_access_ids = [
        str(row.get("access_id") or row.get("chunk_id") or "")
        for row in catalogue
    ]
    request_payload = {
        **base_view,
        "stage": "request",
        "chunk_catalog": catalogue,
        "chunk_catalog_hash": stable_hash(catalogue),
        "max_requested_chunks": request_limit,
    }
    assert_no_gold_leak(request_payload)
    request_raw = cache.call(f"{module}Request", prompt, request_payload)
    request = clean_chunk_request(
        request_raw, allowed_access_ids, limit=request_limit,
    )
    catalog_fact_ids = {
        str(row.get("fact_id") or "") for row in catalogue
    }
    valid_focus = [
        fact_id for fact_id in request["focus_fact_ids"]
        if fact_id in catalog_fact_ids
    ]
    if valid_focus:
        request["focus_fact_ids"] = list(dict.fromkeys(valid_focus))
        request["schema_valid"] = True
    request_repair = False
    if not request["schema_valid"]:
        repair_payload = {
            **request_payload,
            "invalid_response": request_raw,
            "validation_errors": request["rejected"],
            "schema_repair": (
                "Return one or more exact access_id values from chunk_catalog "
                "using the request-stage JSON schema."
            ),
        }
        request_raw = cache.call(
            f"{module}RequestRepair", prompt, repair_payload,
        )
        request = clean_chunk_request(
            request_raw, allowed_access_ids, limit=request_limit,
        )
        valid_focus = [
            fact_id for fact_id in request["focus_fact_ids"]
            if fact_id in catalog_fact_ids
        ]
        if valid_focus:
            request["focus_fact_ids"] = list(dict.fromkeys(valid_focus))
            request["schema_valid"] = True
        request_repair = True
    expanded_ids = list(request["requested_chunk_ids"])
    focus_set = set(request["focus_fact_ids"])
    expansion_rows = sorted(
        (
            row for row in catalogue
            if str(row.get("fact_id") or "") in focus_set
        ),
        key=lambda row: (
            not bool(row.get("has_compare")),
            str(row.get("fact_id") or ""),
            str(row.get("candidate") or ""),
            str(row.get("access_id") or ""),
        ),
    )
    seen_candidates: set[tuple[str, str]] = set()
    for row in expansion_rows:
        access_id = str(row.get("access_id") or "")
        key = (
            str(row.get("fact_id") or ""),
            str(row.get("candidate") or ""),
        )
        if (
            access_id
            and access_id not in expanded_ids
            and key not in seen_candidates
            and len(expanded_ids) < request_limit
        ):
            expanded_ids.append(access_id)
            seen_candidates.add(key)
    request["requested_chunk_ids"] = expanded_ids
    served, service_rejected = hydrate_chunk_requests(
        excerpts, request["requested_chunk_ids"], limit=request_limit,
    )
    if not served:
        raw = _none(reason="no_chunks_served", calls=cache.calls)
        raw["grounding"].update({
            "catalog_excerpts": len(excerpts),
            "catalog_fact_count": len({
                str(row.get("fact_id") or "") for row in catalogue
            }),
            "eligible_fact_count": len(view["eligible_fact_ids"]),
            "fact_coverage": len({
                str(row.get("fact_id") or "") for row in catalogue
            }) / len(view["eligible_fact_ids"]) if view["eligible_fact_ids"] else 0.0,
            "catalog_hash": stable_hash(catalogue),
            "request": request,
            "service_rejected": service_rejected,
            "request_repair_used": request_repair,
        })
        return raw, []
    ground_payload = {
        **base_view,
        "stage": "ground",
        "chunk_catalog_hash": stable_hash(catalogue),
        "knowledge_chunks": served,
        "request_audit": {
            "focus_fact_ids": request["focus_fact_ids"],
            "served_access_ids": [
                str(row.get("access_id") or "") for row in served
            ],
        },
    }
    assert_no_gold_leak(ground_payload)
    response = cache.call(module, prompt, ground_payload)
    cleaned = clean_grounded_selection(
        response,
        eligible_ids=view["eligible_fact_ids"],
        candidates=view["candidates"],
        served_chunks=served,
        limit=int(view["max_selected_facts"]),
        require_complete_grounding=grounding_policy == "strict_entailment",
        require_candidate_alignment=grounding_policy == "strict_entailment",
    )
    initial_cleaned = dict(cleaned)
    repair_used = False
    if (
        str(response.get("verdict") or "").lower() not in {"none", "abstain", "stop"}
        and not cleaned["ranked_fact_ids"]
    ):
        repair_payload = {
            **ground_payload,
            "invalid_response": response,
            "validation_errors": cleaned["rejected"],
            "schema_repair": (
                "Use only served access_id values and exact quotes. Each "
                "selected fact needs at least one valid retrieval citation "
                "and an explicit quote-to-effect-to-rival inference chain. "
                "candidate_effects must contain "
                f"exactly these IDs: {[row['id'] for row in view['candidates']]}. "
                "Return none if no retrieved excerpt can anchor the chain."
            ),
        }
        assert_no_gold_leak(repair_payload)
        response = cache.call(f"{module}Repair", prompt, repair_payload)
        cleaned = clean_grounded_selection(
            response,
            eligible_ids=view["eligible_fact_ids"],
            candidates=view["candidates"],
            served_chunks=served,
            limit=int(view["max_selected_facts"]),
            require_complete_grounding=grounding_policy == "strict_entailment",
            require_candidate_alignment=grounding_policy == "strict_entailment",
        )
        cleaned["citation_count"] = (
            int(initial_cleaned.get("citation_count") or 0)
            + int(cleaned.get("citation_count") or 0)
        )
        cleaned["valid_citation_count"] = (
            int(initial_cleaned.get("valid_citation_count") or 0)
            + int(cleaned.get("valid_citation_count") or 0)
        )
        cleaned["citation_integrity"] = (
            cleaned["valid_citation_count"] / cleaned["citation_count"]
            if cleaned["citation_count"] else 1.0
        )
        cleaned["attempted_chain_count"] = (
            int(initial_cleaned.get("attempted_chain_count") or 0)
            + int(cleaned.get("attempted_chain_count") or 0)
        )
        cleaned["pre_repair_audit"] = {
            key: initial_cleaned.get(key)
            for key in (
                "rejected", "citation_count", "valid_citation_count",
                "grounded_chain_count", "attempted_chain_count",
            )
        }
        repair_used = True
    cleaned["repair_used"] = repair_used
    cleaned["grounding"] = {
        "calls": cache.calls,
        "catalog_excerpts": len(excerpts),
        "catalog_fact_count": len({
            str(row.get("fact_id") or "") for row in catalogue
        }),
        "eligible_fact_count": len(view["eligible_fact_ids"]),
        "fact_coverage": len({
            str(row.get("fact_id") or "") for row in catalogue
        }) / len(view["eligible_fact_ids"]) if view["eligible_fact_ids"] else 0.0,
        "catalog_hash": stable_hash(catalogue),
        "request": request,
        "request_repair_used": request_repair,
        "served_chunks": len(served),
        "served_access_ids": [
            str(row.get("access_id") or "") for row in served
        ],
        "service_rejected": service_rejected,
    }
    return cleaned, served


def _clean_entailment_verification(
    response: Mapping[str, Any],
    comparisons: Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Fail closed unless every cited link is independently entailed."""
    expected = {
        str(row["fact_id"]): {
            str(item.get("access_id") or item.get("chunk_id") or "")
            for item in (row.get("evidence_chain") or ())
        }
        for row in comparisons
    }
    output: dict[str, dict[str, Any]] = {}
    for row in response.get("facts") or ():
        if not isinstance(row, Mapping):
            continue
        fact_id = str(row.get("fact_id") or "")
        if fact_id not in expected:
            continue
        audits = [
            dict(item) for item in (row.get("citation_audits") or ())
            if isinstance(item, Mapping)
        ]
        verdict_by_access = {
            str(item.get("access_id") or ""): str(
                item.get("verdict") or ""
            ).strip().lower()
            for item in audits
        }
        expected_ids = expected[fact_id]
        raw_verdict = str(row.get("verdict") or "").strip().lower()
        all_links_entailed = bool(expected_ids) and all(
            verdict_by_access.get(access_id) == "entailed"
            for access_id in expected_ids
        )
        if raw_verdict == "entailed" and all_links_entailed:
            verdict = "entailed"
        elif (
            raw_verdict == "not_entailed"
            or any(value == "not_entailed" for value in verdict_by_access.values())
        ):
            verdict = "not_entailed"
        else:
            verdict = "insufficient"
        output[fact_id] = {
            "verdict": verdict,
            "raw_verdict": raw_verdict,
            "why": str(row.get("why") or ""),
            "citation_audits": audits,
            "expected_access_ids": sorted(expected_ids),
            "all_links_entailed": all_links_entailed,
        }
    for fact_id, expected_ids in expected.items():
        output.setdefault(fact_id, {
            "verdict": "insufficient",
            "raw_verdict": "",
            "why": "verifier omitted proposed fact",
            "citation_audits": [],
            "expected_access_ids": sorted(expected_ids),
            "all_links_entailed": False,
        })
    return output


def _run_arbiter(
    *,
    cache: CountingCache,
    view: Mapping[str, Any],
    selector: Mapping[str, Any],
    anti: Mapping[str, Any],
    served: Sequence[Mapping[str, Any]],
    grounding_policy: str,
) -> dict[str, Any]:
    allowed = list(dict.fromkeys([
        *(selector.get("ranked_fact_ids") or ()),
        *(anti.get("ranked_fact_ids") or ()),
    ]))
    if not allowed:
        output = _none(reason="no_grounded_proposals")
        output["grounding"].update({
            "catalog_excerpts": len(served),
            "served_chunks": len(served),
            "served_access_ids": sorted({
                str(row.get("access_id") or row.get("chunk_id") or "")
                for row in served
            }),
        })
        return output
    unique_served = {
        str(row.get("access_id") or row.get("chunk_id") or ""): dict(row)
        for row in served
    }
    chunks = list(unique_served.values())
    payload = {
        **_base_view(view),
        "proposal_selector": dict(selector),
        "proposal_anti_anchor": dict(anti),
        "allowed_proposal_fact_ids": allowed,
        "knowledge_chunks": chunks,
    }
    assert_no_gold_leak(payload)
    response = cache.call(
        "L1GroundedSelectionArbiter", ARBITER_PROMPT, payload,
    )
    cleaned = clean_grounded_selection(
        response,
        eligible_ids=view["eligible_fact_ids"],
        candidates=view["candidates"],
        served_chunks=chunks,
        limit=int(view["max_selected_facts"]),
        allowed_proposal_ids=allowed,
        require_complete_grounding=grounding_policy == "strict_entailment",
        require_candidate_alignment=grounding_policy == "strict_entailment",
    )
    initial_cleaned = dict(cleaned)
    repair_used = False
    if (
        str(response.get("verdict") or "").lower() not in {"none", "abstain", "stop"}
        and not cleaned["ranked_fact_ids"]
    ):
        repair_payload = {
            **payload,
            "invalid_response": response,
            "validation_errors": cleaned["rejected"],
            "schema_repair": (
                "Select only allowed_proposal_fact_ids and cite exact quotes "
                "from served knowledge_chunks. Provide a traceable "
                "quote-to-effect-to-rival inference chain. "
                "candidate_effects must contain exactly these IDs: "
                f"{[row['id'] for row in view['candidates']]}. Return none "
                "if no retrieved excerpt can anchor the chain."
            ),
        }
        assert_no_gold_leak(repair_payload)
        response = cache.call(
            "L1GroundedSelectionArbiterRepair", ARBITER_PROMPT, repair_payload,
        )
        cleaned = clean_grounded_selection(
            response,
            eligible_ids=view["eligible_fact_ids"],
            candidates=view["candidates"],
            served_chunks=chunks,
            limit=int(view["max_selected_facts"]),
            allowed_proposal_ids=allowed,
            require_complete_grounding=grounding_policy == "strict_entailment",
            require_candidate_alignment=grounding_policy == "strict_entailment",
        )
        cleaned["citation_count"] = (
            int(initial_cleaned.get("citation_count") or 0)
            + int(cleaned.get("citation_count") or 0)
        )
        cleaned["valid_citation_count"] = (
            int(initial_cleaned.get("valid_citation_count") or 0)
            + int(cleaned.get("valid_citation_count") or 0)
        )
        cleaned["citation_integrity"] = (
            cleaned["valid_citation_count"] / cleaned["citation_count"]
            if cleaned["citation_count"] else 1.0
        )
        cleaned["attempted_chain_count"] = (
            int(initial_cleaned.get("attempted_chain_count") or 0)
            + int(cleaned.get("attempted_chain_count") or 0)
        )
        cleaned["pre_repair_audit"] = {
            key: initial_cleaned.get(key)
            for key in (
                "rejected", "citation_count", "valid_citation_count",
                "grounded_chain_count", "attempted_chain_count",
            )
        }
        repair_used = True
    cleaned["repair_used"] = repair_used
    pre_verification_comparisons = list(cleaned.get("comparisons") or ())
    entailment_rows: dict[str, dict[str, Any]] = {}
    if (
        grounding_policy == "strict_entailment"
        and pre_verification_comparisons
    ):
        facts_by_id = {
            str(row.get("id") or ""): dict(row)
            for row in view.get("fact_catalog_core") or ()
        }
        verification_payload = {
            "observed_facts": [
                facts_by_id.get(str(row["fact_id"]), {"id": row["fact_id"]})
                for row in pre_verification_comparisons
            ],
            "candidates": list(view["candidates"]),
            "proposed_chains": pre_verification_comparisons,
            "knowledge_chunks": chunks,
        }
        assert_no_gold_leak(verification_payload)
        verification_raw = cache.call(
            "L1GroundedChainVerifier", VERIFIER_PROMPT, verification_payload,
        )
        entailment_rows = _clean_entailment_verification(
            verification_raw, pre_verification_comparisons,
        )
        verified = [
            row for row in pre_verification_comparisons
            if (entailment_rows.get(str(row["fact_id"])) or {}).get("verdict")
            == "entailed"
        ]
        cleaned["comparisons"] = verified
        cleaned["ranked_fact_ids"] = [row["fact_id"] for row in verified]
        cleaned["best_fact_id"] = (
            cleaned["ranked_fact_ids"][0] if cleaned["ranked_fact_ids"] else ""
        )
        cleaned["concept_keys"] = {
            row["fact_id"]: row["concept_key"] for row in verified
        }
        cleaned["verdict"] = "select" if verified else "none"
        cleaned["grounded_chain_count"] = len(verified)
        cleaned["attempted_chain_count"] = max(
            int(cleaned.get("attempted_chain_count") or 0),
            len(pre_verification_comparisons),
        )
    cleaned["entailment_verification"] = {
        "policy": grounding_policy,
        "attempted": (
            len(pre_verification_comparisons)
            if grounding_policy == "strict_entailment" else 0
        ),
        "entailed": sum(
            row.get("verdict") == "entailed" for row in entailment_rows.values()
        ),
        "not_entailed": sum(
            row.get("verdict") == "not_entailed"
            for row in entailment_rows.values()
        ),
        "insufficient": sum(
            row.get("verdict") == "insufficient"
            for row in entailment_rows.values()
        ),
        "by_fact": entailment_rows,
        "skipped": grounding_policy != "strict_entailment",
    }
    cleaned["grounding"] = {
        "calls": cache.calls,
        "catalog_excerpts": len(unique_served),
        "served_chunks": len(unique_served),
        "served_access_ids": sorted(unique_served),
        "allowed_proposal_fact_ids": allowed,
    }
    return cleaned


def _map_excerpts(
    *,
    case_id: str,
    facts: Sequence[L1ObservedFact],
    source: Sequence[Mapping[str, Any]],
    composed: Any,
    prefix: str,
) -> list[dict[str, Any]]:
    by_finding: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for row in source:
        by_finding[str(row.get("finding_text") or "")].append(dict(row))
    references = [{"finding": value} for value in by_finding]
    output: list[dict[str, Any]] = []
    for fact in facts:
        exact = next(
            (value for value in by_finding if bfs._norm(value) == bfs._norm(fact.text)),
            None,
        )
        if exact is None:
            matched = composed._best_reference(fact.text, references)
            exact = str(matched.get("finding") or "") if matched else ""
        for index, raw in enumerate(by_finding.get(exact, ()), start=1):
            row = dict(raw)
            row["fact_id"] = fact.id
            row["finding_text"] = fact.text
            row["access_id"] = (
                f"{prefix}::{case_id}::{fact.id}::{index:03d}"
            )
            output.append(row)
    return output


def _mixed_inputs(
    args: argparse.Namespace,
    chunk_rows: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, dict[str, Any]], Any]:
    composed = bfs._load_module("grounded_eval_composed", bfs.COMPOSED_SCRIPT)
    partial = bfs._load_module("grounded_eval_partial", bfs.PARTIAL_SCRIPT)
    talp = bfs._load_module("grounded_eval_talp", bfs.TALP_SCRIPT)
    cases = partial._select_cases(partial.assemble_cases(), args.cases, args.limit)
    frozen_arms = composed.FrozenOfflineArms(
        talp, {"p5_headline": bfs.DEFAULT_ARM_OUTPUTS["p5_headline"]}
    )
    rows_by_case: dict[str, list[Mapping[str, Any]]] = collections.defaultdict(list)
    for row in chunk_rows:
        rows_by_case[str(row.get("case_id") or "")].append(row)
    inputs: dict[str, dict[str, Any]] = {}
    for case in cases:
        case_id = str(case["id"])
        tree_payload = json.loads(
            (bfs.DEFAULT_SHARED_TREE_DIR / f"{case_id}.json").read_text(
                encoding="utf-8",
            )
        )
        tree = composed._deserialize_state(tree_payload["state"])
        facts = bfs._facts_for_case(
            tree, case["annotation"], composed, deduplicate=True,
        )
        blocks = frozen_arms.blocks("p5_headline", case_id, facts)
        view = anti_eval._selector_view(
            isolated._selection_payload(case, tree, facts, blocks)
        )
        inputs[case_id] = {
            "case": case,
            "facts": facts,
            "view": view,
            "excerpts": _map_excerpts(
                case_id=case_id,
                facts=facts,
                source=rows_by_case.get(case_id, ()),
                composed=composed,
                prefix="mixed",
            ),
        }
    return inputs, composed


def _auto_inputs(
    args: argparse.Namespace,
    chunk_rows: Sequence[Mapping[str, Any]],
    composed: Any,
) -> dict[str, dict[str, Any]]:
    fixture = json.loads(args.auto_fixture.read_text(encoding="utf-8"))
    partial = bfs._load_module("grounded_auto_partial", bfs.PARTIAL_SCRIPT)
    selected_cases = partial._select_cases(
        partial.assemble_cases(), args.cases, args.limit,
    )
    case_text_by_id = {
        str(case["id"]): str(case["case_text"]) for case in selected_cases
    }
    rows_by_case: dict[str, list[Mapping[str, Any]]] = collections.defaultdict(list)
    for row in chunk_rows:
        rows_by_case[str(row.get("case_id") or "")].append(row)
    inputs: dict[str, dict[str, Any]] = {}
    for fixture_case in fixture.get("cases") or ():
        gold = auto_eval.validate_gold(fixture_case)
        if gold["status"] != "scorable":
            continue
        case_id = str(fixture_case["case_id"])
        if case_id not in case_text_by_id:
            continue
        tree_payload = json.loads(
            (bfs.DEFAULT_SHARED_TREE_DIR / f"{case_id}.json").read_text(
                encoding="utf-8",
            )
        )
        tree = composed._deserialize_state(tree_payload["state"])
        rows = list(fixture_case["full_findings"])
        facts = auto_eval._facts(rows)
        view = auto_eval.build_view(
            case_text=case_text_by_id[case_id],
            rows=rows,
            filtered_ids=list(fixture_case["filtered_fact_ids"]),
            candidates=auto_eval._candidates(tree),
            context_mode="vignette",
            menu_mode="full",
        )
        inputs[case_id] = {
            "fixture_case": fixture_case,
            "gold": gold,
            "facts": facts,
            "view": view,
            "excerpts": _map_excerpts(
                case_id=case_id,
                facts=facts,
                source=rows_by_case.get(case_id, ()),
                composed=composed,
                prefix="auto",
            ),
        }
    return inputs


def _load_baseline(
    path: Path,
    *,
    arm: str,
    cases: set[str],
    replicates: int,
) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    output = [
        dict(row) for row in (payload.get("records") or ())
        if str(row.get("arm") or "") == arm
        and str(row.get("case_id") or "") in cases
        and int(row.get("replicate") or 0) <= replicates
    ]
    expected = len(cases) * replicates
    if len(output) != expected:
        raise ValueError(
            f"baseline {arm} incomplete: {len(output)} != {expected}"
        )
    for row in output:
        row["arm"] = "A0_anti_anchor_prompt"
    return output


def _audit_generated(
    *,
    track: str,
    arm: str,
    replicate: int,
    case_id: str,
    raw: Mapping[str, Any],
    inputs: Mapping[str, Any],
    composed: Any,
) -> dict[str, Any]:
    if track == "mixed":
        record = anti_eval._audit_record(
            arm=arm,
            replicate=replicate,
            case_id=case_id,
            raw=raw,
            inputs=inputs,
            composed=composed,
        )
    else:
        record = auto_eval.audit_record(
            arm=arm,
            replicate=replicate,
            case_id=case_id,
            raw=raw,
            view=inputs["view"],
            gold=inputs["gold"],
        )
    record["grounding"] = dict(raw.get("grounding") or {})
    record["raw"] = dict(raw)
    return record


def _run_one(
    *,
    track: str,
    replicate: int,
    case_id: str,
    inputs: Mapping[str, Any],
    composed: Any,
    args: argparse.Namespace,
) -> list[dict[str, Any]]:
    client = RobustLLMClient(
        model=args.model,
        call_timeout=args.call_timeout,
        max_retries=5,
        min_response_length=args.min_response_length,
        timeout_retry_cap=2,
        temperature=args.temperature,
    )
    cache_root = (
        args.output_dir / track / "caches"
        / args.cache_tag / f"r{replicate:02d}" / case_id
    )
    a0_cache = CountingCache(bfs.CachedLLM(
        client, cache_root / "A0.json", args.model,
    ))
    selector_cache = CountingCache(bfs.CachedLLM(
        client, cache_root / "G1.json", args.model,
    ))
    anti_cache = CountingCache(bfs.CachedLLM(
        client, cache_root / "G2.json", args.model,
    ))
    arbiter_cache = CountingCache(bfs.CachedLLM(
        client, cache_root / "G3.json", args.model,
    ))
    a0 = anti_eval._call_with_schema_repair(
        a0_cache,
        module="L1AntiAnchorEvidenceSelector",
        prompt=anti_eval.ANTI_PROMPT,
        payload=inputs["view"],
        view=inputs["view"],
    )
    selector, selector_served = _run_grounded_proposer(
        cache=selector_cache,
        module="L1GroundedEvidenceSelector",
        prompt=SELECTOR_PROMPT,
        view=inputs["view"],
        excerpts=inputs["excerpts"],
        request_limit=args.max_requested_chunks,
        grounding_policy=args.grounding_policy,
    )
    anti, anti_served = _run_grounded_proposer(
        cache=anti_cache,
        module="L1GroundedAntiAnchorAgent",
        prompt=ANTI_PROMPT,
        view=inputs["view"],
        excerpts=inputs["excerpts"],
        request_limit=args.max_requested_chunks,
        grounding_policy=args.grounding_policy,
    )
    arbiter = _run_arbiter(
        cache=arbiter_cache,
        view=inputs["view"],
        selector=selector,
        anti=anti,
        served=[*selector_served, *anti_served],
        grounding_policy=args.grounding_policy,
    )
    arbiter.setdefault("grounding", {})["pipeline_calls"] = (
        int((selector.get("grounding") or {}).get("calls") or 0)
        + int((anti.get("grounding") or {}).get("calls") or 0)
        + int((arbiter.get("grounding") or {}).get("calls") or 0)
    )
    selector_hash = str(
        (selector.get("grounding") or {}).get("catalog_hash") or ""
    )
    anti_hash = str((anti.get("grounding") or {}).get("catalog_hash") or "")
    arbiter["grounding"]["proposer_access_parity"] = (
        selector_hash == anti_hash and bool(selector_hash)
    )
    arbiter["grounding"]["catalog_fact_count"] = int(
        (selector.get("grounding") or {}).get("catalog_fact_count") or 0
    )
    arbiter["grounding"]["eligible_fact_count"] = int(
        (selector.get("grounding") or {}).get("eligible_fact_count") or 0
    )
    arbiter["grounding"]["fact_coverage"] = float(
        (selector.get("grounding") or {}).get("fact_coverage") or 0.0
    )
    return [
        _audit_generated(
            track=track, arm=arm, replicate=replicate, case_id=case_id,
            raw=raw, inputs=inputs, composed=composed,
        )
        for arm, raw in zip(
            ("A0_anti_anchor_prompt", *GROUNDED_ARMS),
            (a0, selector, anti, arbiter),
        )
    ]


def _grounding_summary(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    raw_rows = [dict(row.get("raw") or {}) for row in records]
    citations = sum(int(row.get("citation_count") or 0) for row in raw_rows)
    valid = sum(int(row.get("valid_citation_count") or 0) for row in raw_rows)
    accepted_citations = sum(
        len(comparison.get("evidence_chain") or ())
        for row in raw_rows
        for comparison in (row.get("comparisons") or ())
    )
    grounded = sum(int(row.get("grounded_chain_count") or 0) for row in raw_rows)
    attempted = sum(int(row.get("attempted_chain_count") or 0) for row in raw_rows)
    with_catalog = sum(
        int((row.get("grounding") or {}).get("catalog_excerpts") or 0) > 0
        for row in raw_rows
    )
    catalog_facts = sum(
        int((row.get("grounding") or {}).get("catalog_fact_count") or 0)
        for row in raw_rows
    )
    eligible_facts = sum(
        int((row.get("grounding") or {}).get("eligible_fact_count") or 0)
        for row in raw_rows
    )
    return {
        "n_records": len(records),
        "case_catalog_coverage": (
            with_catalog / len(records) if records else 0.0
        ),
        "chunk_coverage": (
            catalog_facts / eligible_facts if eligible_facts else 0.0
        ),
        "catalog_fact_observations": catalog_facts,
        "eligible_fact_observations": eligible_facts,
        "citation_count": citations,
        "valid_citation_count": valid,
        "citation_integrity": valid / citations if citations else 1.0,
        "accepted_citation_count": accepted_citations,
        "accepted_citation_integrity": 1.0,
        "attempted_chain_count": attempted,
        "grounded_chain_count": grounded,
        "grounded_chain_precision": (
            grounded / attempted if attempted else 0.0
        ),
        "mean_calls_per_record": statistics.fmean(
            int(
                (row.get("grounding") or {}).get("pipeline_calls")
                or (row.get("grounding") or {}).get("calls")
                or 0
            )
            for row in raw_rows
        ) if raw_rows else 0.0,
        "access_parity_rate": statistics.fmean(
            bool((row.get("grounding") or {}).get("proposer_access_parity"))
            for row in raw_rows
        ) if raw_rows and any(
            "proposer_access_parity" in (row.get("grounding") or {})
            for row in raw_rows
        ) else None,
    }


def _overturn_summary(
    left: Sequence[Mapping[str, Any]],
    right: Sequence[Mapping[str, Any]],
    *,
    track: str,
) -> dict[str, Any]:
    left_by_key = {
        (int(row["replicate"]), str(row["case_id"])): row for row in left
    }
    overturned = improved = harmed = 0
    metric = "select_at_1" if track == "mixed" else "best_at_1"
    for row in right:
        key = (int(row["replicate"]), str(row["case_id"]))
        before = left_by_key[key]
        if before.get("selected_ids", [])[:1] == row.get("selected_ids", [])[:1]:
            continue
        overturned += 1
        delta = int(bool(row["audit"][metric])) - int(
            bool(before["audit"][metric])
        )
        improved += delta > 0
        harmed += delta < 0
    return {
        "overturned": overturned,
        "overturn_rate": overturned / len(right) if right else 0.0,
        "improved": improved,
        "harmed": harmed,
        "overturn_precision": improved / overturned if overturned else 0.0,
        "harmful_overturn_rate": harmed / overturned if overturned else 0.0,
    }


def _track_summary(
    *,
    track: str,
    baseline: list[dict[str, Any]],
    generated: list[dict[str, Any]],
) -> dict[str, Any]:
    by_arm = {
        arm: [row for row in generated if row["arm"] == arm]
        for arm in GROUNDED_ARMS
    }
    aggregate = anti_eval._aggregate if track == "mixed" else auto_eval.aggregate
    paired = (
        isolated._paired_case_bootstrap
        if track == "mixed" else auto_eval.paired_bootstrap
    )
    result: dict[str, Any] = {
        "arms": {
            "A0_anti_anchor_prompt": aggregate(baseline),
            **{arm: aggregate(rows) for arm, rows in by_arm.items()},
        },
        "grounding": {
            arm: _grounding_summary(rows) for arm, rows in by_arm.items()
        },
        "paired_vs_A0": {
            arm: paired(baseline, rows) for arm, rows in by_arm.items()
        },
        "arbiter_vs_anti_overturn": _overturn_summary(
            by_arm["G2_grounded_anti"],
            by_arm["G3_grounded_arbiter"],
            track=track,
        ),
        "records": baseline + generated,
    }
    baseline_calls = statistics.fmean(
        1 + int(bool((row.get("raw") or {}).get("repair_used")))
        for row in baseline
    ) if baseline else 0.0
    result["cost"] = {
        "A0_anti_anchor_prompt": {
            "mean_calls_per_record": baseline_calls,
            "relative_to_A0": 1.0,
        },
        **{
            arm: {
                "mean_calls_per_record": result["grounding"][arm][
                    "mean_calls_per_record"
                ],
                "relative_to_A0": (
                    result["grounding"][arm]["mean_calls_per_record"]
                    / baseline_calls if baseline_calls else None
                ),
            }
            for arm in GROUNDED_ARMS
        },
    }
    if track == "auto":
        result["absolute_bootstrap"] = {
            "A0_anti_anchor_prompt": auto_eval.absolute_bootstrap(baseline),
            **{
                arm: auto_eval.absolute_bootstrap(rows)
                for arm, rows in by_arm.items()
            },
        }
    return result


def _promotion_decision(summary: Mapping[str, Any]) -> dict[str, Any]:
    mixed = summary["tracks"]["mixed"]
    delta = mixed["paired_vs_A0"]["G3_grounded_arbiter"]
    select2 = delta["select_at_2_given_observed_decisive"]
    select1 = delta["select_at_1_given_observed_decisive"]
    grounding = mixed["grounding"]["G3_grounded_arbiter"]
    auto_delta = summary["tracks"]["auto"]["paired_vs_A0"][
        "G3_grounded_arbiter"
    ]["best_at_2"]
    checks = {
        "select_at_2_ci_lower_positive": select2["ci95"][0] > 0,
        "select_at_1_no_resolved_regression": select1["ci95"][1] >= 0,
        "best_at_2_no_resolved_regression": auto_delta["ci95"][1] >= 0,
        "accepted_citation_integrity_100": (
            grounding["accepted_citation_integrity"] == 1.0
        ),
        "grounded_chain_precision_80": (
            grounding["grounded_chain_precision"] >= 0.8
        ),
        "chunk_coverage_30": grounding["chunk_coverage"] >= 0.3,
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "ruling": (
            "promote_for_end_to_end_validation"
            if all(checks.values())
            else (
                "knowledge_coverage_insufficient"
                if not checks["chunk_coverage_30"]
                else "does_not_outperform_prompt_only"
            )
        ),
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    args.output_dir.mkdir(parents=True, exist_ok=True)
    chunk_fixture = json.loads(args.chunk_fixture.read_text(encoding="utf-8"))
    chunk_rows = list(chunk_fixture.get("excerpts") or ())
    mixed_inputs, composed = _mixed_inputs(args, chunk_rows)
    auto_inputs = _auto_inputs(args, chunk_rows, composed)
    mixed_baseline: list[dict[str, Any]] = []
    auto_baseline: list[dict[str, Any]] = []
    if args.reuse_historical_a0:
        mixed_baseline = _load_baseline(
            args.mixed_baseline,
            arm="anti_anchor_prompt",
            cases=set(mixed_inputs),
            replicates=args.replicates,
        )
        auto_baseline = _load_baseline(
            args.auto_baseline,
            arm="vignette__menu_full",
            cases=set(auto_inputs),
            replicates=args.replicates,
        )
    generated: dict[str, list[dict[str, Any]]] = {
        "mixed": [], "auto": [],
    }
    jobs = [
        (track, replicate, case_id, inputs, composed, args)
        for track, case_map in (
            ("mixed", mixed_inputs), ("auto", auto_inputs),
        )
        for replicate in range(1, args.replicates + 1)
        for case_id, inputs in case_map.items()
    ]
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        future_map = {
            pool.submit(
                _run_one,
                track=track,
                replicate=replicate,
                case_id=case_id,
                inputs=inputs,
                composed=composed,
                args=args,
            ): (track, replicate, case_id)
            for track, replicate, case_id, inputs, composed, args in jobs
        }
        for future in as_completed(future_map):
            track, _, _ = future_map[future]
            generated[track].extend(future.result())
    for rows in generated.values():
        rows.sort(
            key=lambda row: (
                int(row["replicate"]), str(row["case_id"]), str(row["arm"]),
            )
        )
    if not args.reuse_historical_a0:
        mixed_baseline = [
            row for row in generated["mixed"]
            if row["arm"] == "A0_anti_anchor_prompt"
        ]
        auto_baseline = [
            row for row in generated["auto"]
            if row["arm"] == "A0_anti_anchor_prompt"
        ]
    grounded_generated = {
        track: [
            row for row in rows if row["arm"] in GROUNDED_ARMS
        ]
        for track, rows in generated.items()
    }
    result: dict[str, Any] = {
        "schema_version": 1,
        "design": {
            "scope": "selection-only isolated paired A/B",
            "baseline": (
                "A0 p5_anti_anchor_direct cached historical outputs"
                if args.reuse_historical_a0 else
                "A0 p5_anti_anchor_direct synchronous fresh-cache outputs"
            ),
            "G1": "chunk-grounded ordinary contrastive proposer",
            "G2": "chunk-grounded independent anti-anchor proposer",
            "G3": "citation-bound arbiter over G1/G2 grounded proposals",
            "read_access": "same frozen catalogue and same request cap",
            "cache_tag": args.cache_tag,
            "min_response_length": args.min_response_length,
            "grounding_policy": args.grounding_policy,
        },
        "model": args.model,
        "temperature": args.temperature,
        "replicates": args.replicates,
        "chunk_fixture": {
            "path": str(args.chunk_fixture.relative_to(ROOT)),
            "catalog_hash": chunk_fixture["manifest"]["catalog_hash"],
            "n_excerpts": chunk_fixture["manifest"]["n_excerpts"],
            "hydration_audit": chunk_fixture["manifest"]["hydration_audit"],
        },
        "prompt_hashes": {
            "selector": _prompt_hash(SELECTOR_PROMPT),
            "anti_anchor": _prompt_hash(ANTI_PROMPT),
            "arbiter": _prompt_hash(ARBITER_PROMPT),
            "verifier": _prompt_hash(VERIFIER_PROMPT),
        },
        "input_hashes": {
            track: {
                case_id: stable_hash(_base_view(inputs["view"]))
                for case_id, inputs in case_map.items()
            }
            for track, case_map in (
                ("mixed", mixed_inputs), ("auto", auto_inputs),
            )
        },
        "tracks": {
            "mixed": _track_summary(
                track="mixed", baseline=mixed_baseline,
                generated=grounded_generated["mixed"],
            ),
            "auto": _track_summary(
                track="auto", baseline=auto_baseline,
                generated=grounded_generated["auto"],
            ),
        },
    }
    result["promotion_decision"] = _promotion_decision(result)
    output = args.output_dir / "summary.json"
    output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    (args.output_dir / "manifest.json").write_text(
        json.dumps({
            key: result[key] for key in (
                "schema_version", "design", "model", "temperature",
                "replicates", "chunk_fixture", "prompt_hashes", "input_hashes",
            )
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (args.output_dir / "records.json").write_text(
        json.dumps({
            track: values["records"]
            for track, values in result["tracks"].items()
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (args.output_dir / "grounding_audit.json").write_text(
        json.dumps({
            "promotion_decision": result["promotion_decision"],
            "chunk_fixture": result["chunk_fixture"],
            "tracks": {
                track: {
                    "grounding": values["grounding"],
                    "cost": values["cost"],
                    "paired_vs_A0": values["paired_vs_A0"],
                    "arbiter_vs_anti_overturn": values[
                        "arbiter_vs_anti_overturn"
                    ],
                }
                for track, values in result["tracks"].items()
            },
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=bfs.DEFAULT_MODEL)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--replicates", type=int, default=3)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--call-timeout", type=float, default=240.0)
    parser.add_argument("--min-response-length", type=int, default=10)
    parser.add_argument("--max-requested-chunks", type=int, default=12)
    parser.add_argument(
        "--grounding-policy",
        choices=("retrieval_chain", "strict_entailment"),
        default="retrieval_chain",
    )
    parser.add_argument("--cache-tag", default="default")
    parser.add_argument("--reuse-historical-a0", action="store_true")
    parser.add_argument("--cases", default="")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--chunk-fixture", type=Path, default=DEFAULT_CHUNKS)
    parser.add_argument(
        "--auto-fixture", type=Path, default=auto_eval.DEFAULT_FIXTURE,
    )
    parser.add_argument(
        "--mixed-baseline", type=Path, default=DEFAULT_MIXED_BASELINE,
    )
    parser.add_argument(
        "--auto-baseline", type=Path, default=DEFAULT_AUTO_BASELINE,
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


if __name__ == "__main__":
    result = run(parse_args())
    print(json.dumps({
        "promotion_decision": result["promotion_decision"],
        "mixed_arms": {
            arm: values["mean_across_replicates"]
            for arm, values in result["tracks"]["mixed"]["arms"].items()
        },
        "auto_arms": {
            arm: values["mean_across_replicates"]
            for arm, values in result["tracks"]["auto"]["arms"].items()
        },
    }, ensure_ascii=False, indent=2))
