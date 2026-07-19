#!/usr/bin/env python3
"""Joint L2 test with corrected order, dynamic champions, and component ablations."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import statistics
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import eval_l2_competition_strategies as base  # noqa: E402
import eval_l2_dynamic_evidence_marginals as dynamic  # noqa: E402
from agentclinic_tree_dx.l1_evidence_bfs import (  # noqa: E402
    assert_no_gold_leak,
    stable_hash,
)
from agentclinic_tree_dx.llm_client import RobustLLMClient  # noqa: E402

JOINT_ARBITER_PROMPT_PATH = (
    ROOT / "src" / "agentclinic_tree_dx" / "prompts"
    / "l2_joint_champion_arbiter.txt"
)
DEFAULT_OUTPUT = (
    ROOT / "logs" / "l2_competition_strategies_v1"
    / "l2_joint_dynamic_v1"
)
ARBITER_MODULE = "L2JointArbiter"

ARM_SPECS = {
    "A0-bug-catalog-f2": {
        "champions": "bug",
        "evidence": "catalog_f2",
        "prior": True,
        "audit": True,
        "context": "full",
        "effects": False,
    },
    "A1-order-fixed-f2": {
        "champions": "true",
        "evidence": "true_f2",
        "prior": True,
        "audit": True,
        "context": "full",
        "effects": False,
    },
    "A2-dynamic-champions": {
        "champions": "dynamic",
        "evidence": "true_f2",
        "prior": True,
        "audit": True,
        "context": "full",
        "effects": False,
    },
    "A3-joint-primary": {
        "champions": "dynamic",
        "evidence": "dynamic_f2",
        "prior": True,
        "audit": True,
        "context": "full",
        "effects": False,
    },
    "A4-joint-no-prior": {
        "champions": "dynamic",
        "evidence": "dynamic_f2",
        "prior": False,
        "audit": True,
        "context": "full",
        "effects": False,
    },
    "A5-joint-no-audit": {
        "champions": "dynamic",
        "evidence": "dynamic_f2",
        "prior": True,
        "audit": False,
        "context": "full",
        "effects": False,
    },
    "A6-joint-selected-only": {
        "champions": "dynamic",
        "evidence": "dynamic_f2",
        "prior": True,
        "audit": True,
        "context": "selected_only",
        "effects": False,
    },
    "A7-joint-effect-handoff": {
        "champions": "dynamic",
        "evidence": "dynamic_f2",
        "prior": True,
        "audit": True,
        "context": "full",
        "effects": True,
    },
    "A8-joint-clean-effects": {
        "champions": "dynamic",
        "evidence": "dynamic_f2",
        "prior": False,
        "audit": False,
        "context": "selected_only",
        "effects": True,
    },
}

COMPONENT_COMPARISONS = {
    "repair_catalog_prefix_and_champions": (
        "A0-bug-catalog-f2", "A1-order-fixed-f2",
    ),
    "dynamic_local_f4": ("A1-order-fixed-f2", "A2-dynamic-champions"),
    "dynamic_between_f2": ("A2-dynamic-champions", "A3-joint-primary"),
    "remove_parent_prior": ("A3-joint-primary", "A4-joint-no-prior"),
    "remove_local_audit": ("A3-joint-primary", "A5-joint-no-audit"),
    "remove_context_bypass": (
        "A3-joint-primary", "A6-joint-selected-only",
    ),
    "handoff_selector_effects": (
        "A3-joint-primary", "A7-joint-effect-handoff",
    ),
    "remove_all_interference": (
        "A3-joint-primary", "A8-joint-clean-effects",
    ),
    "joint_primary_vs_order_fixed": (
        "A1-order-fixed-f2", "A3-joint-primary",
    ),
    "clean_joint_vs_order_fixed": (
        "A1-order-fixed-f2", "A8-joint-clean-effects",
    ),
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def true_consumption_order(full_record: Mapping[str, Any]) -> list[str]:
    trace = full_record.get("trace", {})
    rounds = list(trace.get("rounds") or ())
    round_order = [
        str(row["fact_id"]) for row in rounds if row.get("fact_id")
    ]
    ordered = [
        str(fact_id)
        for fact_id in trace.get("consumption_order_fact_ids") or round_order
    ]
    if ordered != round_order:
        raise ValueError("explicit L1 consumption order disagrees with rounds")
    if len(ordered) != len(set(ordered)):
        raise ValueError("true L1 consumption order contains duplicate fact IDs")
    consumed = set(
        trace.get("selected_fact_ids") or ()
    )
    if set(ordered) != consumed:
        raise ValueError("L1 rounds and consumed fact set disagree")
    return ordered


def _facts_for_ids(
    findings: Sequence[Mapping[str, Any]],
    fact_ids: Sequence[str],
) -> list[dict[str, Any]]:
    by_id = {str(row["id"]): dict(row) for row in findings}
    missing = [fact_id for fact_id in fact_ids if fact_id not in by_id]
    if missing:
        raise ValueError(f"facts missing from catalog: {missing}")
    return [by_id[fact_id] for fact_id in fact_ids]


def _selector_candidates(
    candidates: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    allowed = ("id", "label", "parent_id", "parent_label")
    return [
        {key: row[key] for key in allowed if key in row}
        for row in candidates
    ]


def _prior_local_output(branches: Mapping[str, Any]) -> dict[str, Any]:
    ranking = [
        branch.id for branch in sorted(
            branches.values(),
            key=lambda branch: (-float(branch.posterior), branch.id),
        )
    ]
    return {
        "schema_valid": True,
        "repair_used": False,
        "ranking": ranking,
        "posteriors": [
            {
                "id": branch.id,
                "label": branch.label,
                "parent_id": branch.parent,
                "posterior": float(branch.posterior),
            }
            for branch in sorted(
                branches.values(),
                key=lambda branch: (-float(branch.posterior), branch.id),
            )
        ],
        "fact_rationales": {},
        "rejected": [],
    }


def _build_champions(
    *,
    mode: str,
    cache,
    selector_prompt: str,
    annotator_prompt: str,
    case_text: str,
    findings: Sequence[Mapping[str, Any]],
    l1_rows: Sequence[Mapping[str, Any]],
    tree_state,
    true_f2: Sequence[Mapping[str, Any]],
    champions_per_parent: int = 1,
) -> dict[str, Any]:
    if champions_per_parent < 1:
        raise ValueError("champions_per_parent must be positive")
    parent_ids = [str(row["id"]) for row in l1_rows]
    parent_scores = {
        str(row["id"]): float(row["posterior"]) for row in l1_rows
    }
    champions = []
    local_outputs = {}
    selections = {}
    for parent_id in parent_ids:
        branches = base.rescale_l2_scope(
            tree_state, l1_rows, [parent_id], use_parent_mass=False,
        )
        if mode == "dynamic":
            candidate_rows = base._candidate_rows(branches, tree_state)
            selection = dynamic.dynamic_l2_evidence_order(
                cache=cache,
                module="L2JointDynamicLocalEvidenceSelector",
                prompt=selector_prompt,
                case_text=case_text,
                findings=findings,
                candidates=_selector_candidates(candidate_rows),
                stop_after=4,
            )
            selected_facts = _facts_for_ids(
                findings, selection["selected_fact_ids"][:4],
            )
            selections[parent_id] = selection
        elif mode == "true":
            selected_facts = [dict(row) for row in true_f2]
            selections[parent_id] = {
                "selected_fact_ids": [
                    str(row["id"]) for row in selected_facts
                ],
                "stop_reason": "fixed_true_round_f2",
                "cycles": [],
            }
        else:
            raise ValueError(f"unknown champion mode: {mode}")
        if selected_facts:
            output = base._annotate_scope(
                cache=cache,
                module=f"L2JointLocalAnnotator_{mode}",
                prompt=annotator_prompt,
                case_text=case_text,
                findings=findings,
                selected_facts=selected_facts,
                branches=branches,
                tree_state=tree_state,
            )
        else:
            output = _prior_local_output(branches)
        local_outputs[parent_id] = output
        if output["schema_valid"] and output.get("posteriors"):
            parent = tree_state.branches[parent_id]
            for local_rank, winner_value in enumerate(
                output["posteriors"][:champions_per_parent], start=1,
            ):
                winner = dict(winner_value)
                champions.append({
                    "id": winner["id"],
                    "label": winner["label"],
                    "parent_id": parent_id,
                    "parent_label": parent.label,
                    "local_rank": local_rank,
                    "local_score": winner["posterior"],
                    "parent_posterior": parent_scores[parent_id],
                    "local_evidence_ids": [
                        str(row["id"]) for row in selected_facts
                    ],
                    "local_fact_rationales": dict(
                        output.get("fact_rationales") or {}
                    ),
                })
    return {
        "mode": mode,
        "champions": champions,
        "local_outputs": local_outputs,
        "selections": selections,
        "champions_per_parent": champions_per_parent,
        "all_valid": (
            len(local_outputs) == len(parent_ids)
            and all(
                bool(row.get("schema_valid")) and bool(row.get("posteriors"))
                for row in local_outputs.values()
            )
        ),
    }


def _local_margin(posteriors: Sequence[Mapping[str, Any]]) -> Optional[float]:
    if not posteriors:
        return None
    if len(posteriors) == 1:
        return 1.0
    return (
        float(posteriors[0].get("posterior") or 0.0)
        - float(posteriors[1].get("posterior") or 0.0)
    )


def _deterministic_arbiter_ranking(
    champions: Sequence[Mapping[str, Any]],
) -> list[str]:
    ordered = sorted(
        champions,
        key=lambda row: (
            -(
                max(float(row.get("parent_posterior") or 0.0), 1e-12)
                * max(float(row.get("local_score") or 0.0), 1e-12)
            ),
            str(row.get("id") or ""),
        ),
    )
    return [str(row["id"]) for row in ordered]


def _build_champions_v2(
    *,
    mode: str,
    cache,
    selector_prompt: str,
    annotator_prompt: str,
    case_text: str,
    findings: Sequence[Mapping[str, Any]],
    l1_rows: Sequence[Mapping[str, Any]],
    tree_state,
    true_f2: Sequence[Mapping[str, Any]],
    champions_per_parent: int = 1,
    technical_resilience: bool = False,
    rescue_enabled: bool = False,
    margin_threshold: float = 0.08,
    tree_payload: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """V2 champion builder: active-only first pass, optional reserve rescue.

    Always returns at most one champion per parent when champions_per_parent=1.
    Reserve leaves (status=closed_for_now) are invisible on the first pass.
    """
    if champions_per_parent != 1 and rescue_enabled:
        raise ValueError("A22 rescue requires champions_per_parent=1")
    parent_ids = [str(row["id"]) for row in l1_rows]
    parent_scores = {
        str(row["id"]): float(row["posterior"]) for row in l1_rows
    }
    champions = []
    local_outputs = {}
    selections = {}
    rescue_trace = []
    fallback_parents = []
    for parent_id in parent_ids:
        branches = base.rescale_l2_scope(
            tree_state, l1_rows, [parent_id], use_parent_mass=False,
        )
        # First pass already excludes closed_for_now via _l2_children.
        if mode == "dynamic":
            candidate_rows = base._candidate_rows(branches, tree_state)
            selection = dynamic.dynamic_l2_evidence_order(
                cache=cache,
                module="L2JointDynamicLocalEvidenceSelectorV2",
                prompt=selector_prompt,
                case_text=case_text,
                findings=findings,
                candidates=_selector_candidates(candidate_rows),
                stop_after=4,
            )
            selected_facts = _facts_for_ids(
                findings, selection["selected_fact_ids"][:4],
            )
            selections[parent_id] = selection
        elif mode == "true":
            selected_facts = [dict(row) for row in true_f2]
            selections[parent_id] = {
                "selected_fact_ids": [
                    str(row["id"]) for row in selected_facts
                ],
                "stop_reason": "fixed_true_round_f2",
                "cycles": [],
            }
        else:
            raise ValueError(f"unknown champion mode: {mode}")
        if selected_facts:
            output = base._annotate_scope(
                cache=cache,
                module=f"L2JointLocalAnnotatorV2_{mode}",
                prompt=annotator_prompt,
                case_text=case_text,
                findings=findings,
                selected_facts=selected_facts,
                branches=branches,
                tree_state=tree_state,
            )
        else:
            output = _prior_local_output(branches)
        used_fallback = False
        if (
            technical_resilience
            and (
                not output.get("schema_valid")
                or not output.get("posteriors")
            )
        ):
            output = {
                **_prior_local_output(branches),
                "schema_valid": False,
                "repair_used": bool(output.get("repair_used")),
                "technical_fallback": "prior_local_for_parent",
                "rejected": list(output.get("rejected") or ()),
            }
            used_fallback = True
            fallback_parents.append(parent_id)
        local_outputs[parent_id] = {
            **output,
            "local_margin": _local_margin(output.get("posteriors") or ()),
            "technical_fallback": used_fallback,
        }
        posteriors = list(output.get("posteriors") or ())
        margin = _local_margin(posteriors)
        trigger_rescue = (
            rescue_enabled
            and tree_payload is not None
            and (
                bool(output.get("repair_used"))
                or (
                    margin is not None
                    and margin < float(margin_threshold)
                )
            )
        )
        challenger_id = None
        if trigger_rescue:
            import l2_a_variant_v2_transforms as v2t

            challenger = v2t.select_reserve_challenger(
                tree_payload,
                parent_id,
                exclude_ids=[str(row["id"]) for row in posteriors[:1]],
            )
            if challenger is not None:
                challenger_id = str(challenger["id"])
                # Temporarily reopen one reserve challenger for a second pass.
                reopen = copy.deepcopy(tree_state)
                branch = reopen.branches[challenger_id]
                branch.status = "live"
                branch.closure_reason = ""
                challenge_branches = base.rescale_l2_scope(
                    reopen, l1_rows, [parent_id], use_parent_mass=False,
                )
                if mode == "dynamic":
                    challenge_rows = base._candidate_rows(
                        challenge_branches, reopen,
                    )
                    challenge_selection = dynamic.dynamic_l2_evidence_order(
                        cache=cache,
                        module="L2JointDynamicLocalEvidenceSelectorV2Rescue",
                        prompt=selector_prompt,
                        case_text=case_text,
                        findings=findings,
                        candidates=_selector_candidates(challenge_rows),
                        stop_after=4,
                    )
                    challenge_facts = _facts_for_ids(
                        findings,
                        challenge_selection["selected_fact_ids"][:4],
                    )
                else:
                    challenge_facts = [dict(row) for row in true_f2]
                if challenge_facts:
                    challenge_output = base._annotate_scope(
                        cache=cache,
                        module=f"L2JointLocalAnnotatorV2Rescue_{mode}",
                        prompt=annotator_prompt,
                        case_text=case_text,
                        findings=findings,
                        selected_facts=challenge_facts,
                        branches=challenge_branches,
                        tree_state=reopen,
                    )
                else:
                    challenge_output = _prior_local_output(challenge_branches)
                if (
                    technical_resilience
                    and (
                        not challenge_output.get("schema_valid")
                        or not challenge_output.get("posteriors")
                    )
                ):
                    challenge_output = _prior_local_output(challenge_branches)
                challenge_posteriors = list(
                    challenge_output.get("posteriors") or ()
                )
                if challenge_posteriors:
                    winner = challenge_posteriors[0]
                    first_pass_winner = (
                        posteriors[0]["id"] if posteriors else None
                    )
                    challenger_won = str(winner["id"]) == challenger_id
                    posteriors = challenge_posteriors
                    output = challenge_output
                    local_outputs[parent_id] = {
                        **output,
                        "local_margin": _local_margin(posteriors),
                        "technical_fallback": used_fallback,
                        "rescue_applied": True,
                        "challenger_id": challenger_id,
                        "challenger_won": challenger_won,
                        "first_pass_winner": first_pass_winner,
                    }
                    rescue_trace.append({
                        "parent_id": parent_id,
                        "challenger_id": challenger_id,
                        "challenger_won": challenger_won,
                        "trigger_margin": margin,
                        "trigger_repair": bool(
                            local_outputs[parent_id].get("repair_used")
                            if "repair_used" in local_outputs[parent_id]
                            else False
                        ),
                    })
        if output.get("schema_valid") or technical_resilience:
            if posteriors:
                parent = tree_state.branches[parent_id]
                winner_value = posteriors[0]
                champions.append({
                    "id": winner_value["id"],
                    "label": winner_value["label"],
                    "parent_id": parent_id,
                    "parent_label": parent.label,
                    "local_rank": 1,
                    "local_score": winner_value["posterior"],
                    "parent_posterior": parent_scores[parent_id],
                    "local_evidence_ids": [
                        str(row["id"]) for row in selected_facts
                    ],
                    "local_fact_rationales": dict(
                        output.get("fact_rationales") or {}
                    ),
                    "local_margin": _local_margin(posteriors),
                    "technical_fallback": used_fallback,
                    "challenger_id": challenger_id,
                })
    schema_all_valid = (
        len(local_outputs) == len(parent_ids)
        and all(
            bool(row.get("schema_valid")) and bool(row.get("posteriors"))
            for row in local_outputs.values()
        )
    )
    resilient_valid = bool(champions) and (
        technical_resilience or schema_all_valid
    )
    return {
        "mode": mode,
        "champions": champions,
        "local_outputs": local_outputs,
        "selections": selections,
        "champions_per_parent": 1,
        "all_valid": schema_all_valid,
        "resilient_valid": resilient_valid,
        "rescue_trace": rescue_trace,
        "fallback_parents": fallback_parents,
        "technical_resilience": technical_resilience,
        "rescue_enabled": rescue_enabled,
        "margin_threshold": margin_threshold,
    }


def _joint_arbitrate_v2(
    *,
    cache,
    module: str,
    prompt: str,
    case_text: str,
    findings: Sequence[Mapping[str, Any]],
    selected_facts: Sequence[Mapping[str, Any]],
    champions: Sequence[Mapping[str, Any]],
    include_prior: bool,
    include_audit: bool,
    context_mode: str,
    selector_effects: Sequence[Mapping[str, Any]],
    technical_resilience: bool = False,
) -> dict[str, Any]:
    primary = _joint_arbitrate(
        cache=cache,
        module=module,
        prompt=prompt,
        case_text=case_text,
        findings=findings,
        selected_facts=selected_facts,
        champions=champions,
        include_prior=include_prior,
        include_audit=include_audit,
        context_mode=context_mode,
        selector_effects=selector_effects,
    )
    strict = {
        "schema_valid": bool(primary.get("schema_valid")),
        "ranking": list(primary.get("ranking") or ()),
        "repair_used": bool(primary.get("repair_used")),
        "technical_fallback": False,
    }
    resilient = dict(strict)
    if technical_resilience and not primary.get("schema_valid"):
        resilient = {
            "schema_valid": False,
            "ranking": _deterministic_arbiter_ranking(champions),
            "repair_used": bool(primary.get("repair_used")),
            "technical_fallback": True,
            "fallback_reason": "parent_posterior_times_local_score",
        }
    return {
        **primary,
        "strict_legacy": strict,
        "resilient_legacy": resilient,
        "technical_fallback": bool(resilient.get("technical_fallback")),
    }


def _selected_effects(
    selection: Mapping[str, Any],
    fact_ids: Sequence[str],
) -> list[dict[str, Any]]:
    wanted = set(fact_ids)
    output = []
    for cycle in selection.get("cycles") or ():
        for row in cycle.get("cleaned", {}).get("comparisons") or ():
            if str(row.get("fact_id")) in wanted:
                output.append(dict(row))
    return output


def _selection_call_count(selection: Mapping[str, Any]) -> int:
    return sum(
        1 + int(bool(cycle.get("repair_used")))
        for cycle in selection.get("cycles") or ()
    )


def _local_asset_call_count(asset: Mapping[str, Any]) -> int:
    selector_calls = sum(
        _selection_call_count(selection)
        for selection in asset.get("selections", {}).values()
    )
    annotation_calls = sum(
        1 + int(bool(output.get("repair_used")))
        for output in asset.get("local_outputs", {}).values()
        if output.get("candidates") or output.get("fact_rationales")
    )
    return selector_calls + annotation_calls


def _arbiter_rows(
    champions: Sequence[Mapping[str, Any]],
    *,
    include_prior: bool,
    include_audit: bool,
) -> list[dict[str, Any]]:
    rows = []
    for champion in champions:
        row = {
            key: champion[key]
            for key in ("id", "label", "parent_id", "parent_label")
        }
        if include_prior:
            row["parent_posterior"] = champion["parent_posterior"]
        if include_audit:
            row["local_score"] = champion["local_score"]
            row["local_audit"] = {
                "evidence_ids": list(
                    champion.get("local_evidence_ids") or ()
                ),
                "fact_rationales": dict(
                    champion.get("local_fact_rationales") or {}
                ),
            }
        rows.append(row)
    return rows


def _joint_arbitrate(
    *,
    cache,
    module: str,
    prompt: str,
    case_text: str,
    findings: Sequence[Mapping[str, Any]],
    selected_facts: Sequence[Mapping[str, Any]],
    champions: Sequence[Mapping[str, Any]],
    include_prior: bool,
    include_audit: bool,
    context_mode: str,
    selector_effects: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    rows = _arbiter_rows(
        champions,
        include_prior=include_prior,
        include_audit=include_audit,
    )
    payload = {
        "selected_evidence": list(selected_facts),
        "champions": rows,
        "parent_prior_mode": (
            "soft_parent_posterior" if include_prior else "uniform"
        ),
        "local_audit_mode": "included" if include_audit else "omitted",
        "context_mode": context_mode,
    }
    if context_mode == "full":
        payload["vignette"] = case_text
        payload["available_findings"] = list(findings)
    elif context_mode != "selected_only":
        raise ValueError(f"unknown context mode: {context_mode}")
    if selector_effects:
        payload["selector_effects"] = list(selector_effects)
    assert_no_gold_leak(payload)
    response = cache.call(module, prompt, payload)
    cleaned = base.clean_champion_ranking(
        response, [str(row["id"]) for row in rows],
    )
    repair_used = False
    if not cleaned["schema_valid"]:
        repair_payload = {
            **payload,
            "invalid_response": response,
            "validation_errors": cleaned["rejected"],
            "schema_repair": "Return every supplied champion ID exactly once.",
        }
        assert_no_gold_leak(repair_payload)
        repaired = cache.call(f"{module}Repair", prompt, repair_payload)
        cleaned = base.clean_champion_ranking(
            repaired, [str(row["id"]) for row in rows],
        )
        repair_used = True
    return {
        **cleaned,
        "repair_used": repair_used,
        "champions": rows,
        "payload_audit": {
            "selected_fact_ids": [
                str(row["id"]) for row in selected_facts
            ],
            "include_prior": include_prior,
            "include_audit": include_audit,
            "context_mode": context_mode,
            "selector_effect_fact_ids": [
                str(row["fact_id"]) for row in selector_effects
            ],
        },
    }


def _case_records(
    *,
    replicate: int,
    case: Mapping[str, Any],
    auto_asset: Mapping[str, Any],
    frozen_asset: Mapping[str, Any],
    full_record: Mapping[str, Any],
    gold: Mapping[str, Any],
    tree_state,
    old_champions: Sequence[Mapping[str, Any]],
    cache,
    selector_prompt: str,
    annotator_prompt: str,
    arbiter_prompt: str,
) -> dict[str, Any]:
    findings = list(auto_asset["full_findings"])
    true_order = true_consumption_order(full_record)
    true_f2 = _facts_for_ids(findings, true_order[:2])
    catalog_f2 = list(frozen_asset["selected_facts"])[:2]
    true_assets = _build_champions(
        mode="true",
        cache=cache,
        selector_prompt=selector_prompt,
        annotator_prompt=annotator_prompt,
        case_text=str(case["case_text"]),
        findings=findings,
        l1_rows=frozen_asset["l1_posteriors"],
        tree_state=tree_state,
        true_f2=true_f2,
    )
    dynamic_assets = _build_champions(
        mode="dynamic",
        cache=cache,
        selector_prompt=selector_prompt,
        annotator_prompt=annotator_prompt,
        case_text=str(case["case_text"]),
        findings=findings,
        l1_rows=frozen_asset["l1_posteriors"],
        tree_state=tree_state,
        true_f2=true_f2,
    )
    clean_dynamic_candidates = _selector_candidates(
        dynamic_assets["champions"],
    )
    between_selection = dynamic.dynamic_l2_evidence_order(
        cache=cache,
        module="L2JointDynamicBetweenEvidenceSelector",
        prompt=selector_prompt,
        case_text=str(case["case_text"]),
        findings=findings,
        candidates=clean_dynamic_candidates,
        stop_after=2,
    )
    dynamic_f2 = _facts_for_ids(
        findings, between_selection["selected_fact_ids"][:2],
    )
    dynamic_effects = _selected_effects(
        between_selection,
        [str(row["id"]) for row in dynamic_f2],
    )
    normalized_old_champions = []
    for champion in old_champions:
        row = dict(champion)
        row["local_evidence_ids"] = list(
            (row.get("local_fact_rationales") or {}).keys()
        )
        normalized_old_champions.append(row)
    champion_sources = {
        "bug": {
            "champions": normalized_old_champions,
            "all_valid": bool(old_champions),
        },
        "true": true_assets,
        "dynamic": dynamic_assets,
    }
    evidence_sources = {
        "catalog_f2": catalog_f2,
        "true_f2": true_f2,
        "dynamic_f2": dynamic_f2,
    }
    local_call_counts = {
        "bug": len(frozen_asset["l1_posteriors"]),
        "true": _local_asset_call_count(true_assets),
        "dynamic": _local_asset_call_count(dynamic_assets),
    }
    between_selector_calls = _selection_call_count(between_selection)
    records = []
    for arm, spec in ARM_SPECS.items():
        source = champion_sources[spec["champions"]]
        champions = list(source["champions"])
        selected_facts = list(evidence_sources[spec["evidence"]])
        effects = dynamic_effects if spec["effects"] else []
        if source["all_valid"] and champions and selected_facts:
            output = _joint_arbitrate(
                cache=cache,
                # A shared module key makes CachedLLM reuse the exact same
                # response when two ablation arms have identical payloads.
                # Separate arm keys would inject model nondeterminism into a
                # nominally no-op comparison.
                module=ARBITER_MODULE,
                prompt=arbiter_prompt,
                case_text=str(case["case_text"]),
                findings=findings,
                selected_facts=selected_facts,
                champions=champions,
                include_prior=bool(spec["prior"]),
                include_audit=bool(spec["audit"]),
                context_mode=str(spec["context"]),
                selector_effects=effects,
            )
        else:
            output = {
                "schema_valid": False,
                "repair_used": False,
                "ranking": [],
                "champions": champions,
                "rejected": ["missing_champions_or_evidence"],
            }
        champion_ids = [str(row["id"]) for row in champions]
        records.append({
            "schema_version": 1,
            "arm": arm,
            "replicate": replicate,
            "case_id": str(case["id"]),
            "selected_fact_ids": [
                str(row["id"]) for row in selected_facts
            ],
            "true_l1_f2_fact_ids": [
                str(row["id"]) for row in true_f2
            ],
            "catalog_f2_fact_ids": [
                str(row["id"]) for row in catalog_f2
            ],
            "champion_source": spec["champions"],
            "champion_ids": champion_ids,
            "output": output,
            "audit": base.score_ranking(
                output.get("ranking") or (),
                gold,
                scope_ids=champion_ids,
                schema_valid=bool(output.get("schema_valid")),
                local_champion_ids=champion_ids,
            ),
            "schema_valid": bool(output.get("schema_valid")),
            "repair_used": bool(output.get("repair_used")),
            "candidate_count": len(champions),
            "estimated_llm_calls": (
                local_call_counts[spec["champions"]]
                + (
                    between_selector_calls
                    if spec["evidence"] == "dynamic_f2" else 0
                )
                + 1
            ),
        })
    return {
        "records": records,
        "true_order": true_order,
        "true_assets": true_assets,
        "dynamic_assets": dynamic_assets,
        "between_selection": between_selection,
        "dynamic_effects": dynamic_effects,
    }


def _run_replicate(
    *,
    replicate: int,
    args: argparse.Namespace,
    cases: Sequence[Mapping[str, Any]],
    fixture_cases: Mapping[str, Mapping[str, Any]],
    frozen_assets: Mapping[tuple[int, str], Mapping[str, Any]],
    full_records: Mapping[tuple[int, str], Mapping[str, Any]],
    gold_cases: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    composed = base.bfs._load_module(
        f"l2_joint_composed_r{replicate}", base.bfs.COMPOSED_SCRIPT,
    )
    client = RobustLLMClient(
        model=args.model,
        call_timeout=args.call_timeout,
        max_retries=5,
        timeout_retry_cap=2,
        temperature=args.temperature,
    )
    cache = base.bfs.CachedLLM(
        client,
        args.output_dir / "cache" / f"r{replicate:02d}.json",
        args.model,
    )
    selector_prompt = dynamic.PROMPT_PATH.read_text(encoding="utf-8")
    annotator_prompt = base.ANNOTATOR_PROMPT_PATH.read_text(encoding="utf-8")
    arbiter_prompt = JOINT_ARBITER_PROMPT_PATH.read_text(encoding="utf-8")
    records = []
    for case in cases:
        case_id = str(case["id"])
        frozen_asset = frozen_assets[(replicate, case_id)]
        full_record = full_records[(replicate, case_id)]
        old_champions = base._f2_champions(
            args.base_output_dir,
            replicate=replicate,
            case_id=case_id,
            frozen_asset_hash=str(frozen_asset["asset_hash"]),
        )
        tree_payload = base._tree_payload(args.tree_dir, case_id)
        if tree_payload.get("tree_hash") != frozen_asset["shared_tree_hash"]:
            raise ValueError(f"{case_id} tree drifted after L1 freeze")
        if (
            auto_hash := fixture_cases[case_id]["full_catalog_hash"]
        ) != frozen_asset["full_catalog_hash"]:
            raise ValueError(
                f"{case_id} catalog drifted: {auto_hash}",
            )
        if stable_hash(case["case_text"]) != frozen_asset["case_text_hash"]:
            raise ValueError(f"{case_id} vignette drifted after L1 freeze")
        identity = {
            "protocol_version": 2,
            "model": args.model,
            "temperature": args.temperature,
            "frozen_l1_asset_hash": frozen_asset["asset_hash"],
            "full_trace_hash": stable_hash(full_record),
            "gold_case_hash": stable_hash(gold_cases[case_id]),
            "old_champion_hash": stable_hash(old_champions),
            "tree_hash": tree_payload["tree_hash"],
            "catalog_hash": auto_hash,
            "case_text_hash": stable_hash(case["case_text"]),
            "selector_prompt_sha256": _sha256(dynamic.PROMPT_PATH),
            "annotator_prompt_sha256": _sha256(
                base.ANNOTATOR_PROMPT_PATH,
            ),
            "arbiter_prompt_sha256": _sha256(
                JOINT_ARBITER_PROMPT_PATH,
            ),
        }
        output_path = (
            args.output_dir / "traces"
            / f"r{replicate:02d}__{case_id}.json"
        )
        if output_path.is_file():
            existing = json.loads(output_path.read_text(encoding="utf-8"))
            existing_identity = existing.get("identity") or {}
            if all(
                existing_identity.get(key) == value
                for key, value in identity.items()
            ):
                records.extend(existing["records"])
                continue
        tree_state = composed._deserialize_state(tree_payload["state"])
        result = _case_records(
            replicate=replicate,
            case=case,
            auto_asset=fixture_cases[case_id],
            frozen_asset=frozen_asset,
            full_record=full_record,
            gold=gold_cases[case_id],
            tree_state=tree_state,
            old_champions=old_champions,
            cache=cache,
            selector_prompt=selector_prompt,
            annotator_prompt=annotator_prompt,
            arbiter_prompt=arbiter_prompt,
        )
        base._atomic_json(output_path, {
            "schema_version": 1,
            "identity": identity,
            "case_id": case_id,
            "replicate": replicate,
            **result,
        })
        records.extend(result["records"])
        print(
            f"[l2-joint] r{replicate:02d} {case_id} complete",
            flush=True,
        )
    return records


def _component_bootstrap(
    records: Sequence[Mapping[str, Any]],
    *,
    n_boot: int,
) -> dict[str, Any]:
    by_arm = {
        arm: [row for row in records if row["arm"] == arm]
        for arm in ARM_SPECS
    }
    output = {}
    for component, (before, after) in COMPONENT_COMPARISONS.items():
        for subset_name, predicate in (
            ("all17", lambda row: True),
            ("gold_present", lambda row: row["audit"]["gold_present"]),
        ):
            for metric in ("top1", "top2", "rr"):
                output[
                    f"{component}::{subset_name}::{metric}"
                ] = base._bootstrap_delta(
                    [row for row in by_arm[before] if predicate(row)],
                    [row for row in by_arm[after] if predicate(row)],
                    metric=metric,
                    n_boot=n_boot,
                )
    return output


def _component_transitions(
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    by_arm = {
        arm: {
            (int(row["replicate"]), str(row["case_id"])): row
            for row in records if row["arm"] == arm
        }
        for arm in ARM_SPECS
    }
    output = {}
    for component, (before, after) in COMPONENT_COMPARISONS.items():
        left = by_arm[before]
        right = by_arm[after]
        component_rows = {}
        for metric in ("top1", "top2", "rr", "structural_reach"):
            gains = []
            losses = []
            unchanged = 0
            for key in sorted(set(left) & set(right)):
                before_value = float(left[key]["audit"][metric])
                after_value = float(right[key]["audit"][metric])
                delta = after_value - before_value
                row = {
                    "replicate": key[0],
                    "case_id": key[1],
                    "before": before_value,
                    "after": after_value,
                    "delta": delta,
                }
                if delta > 0:
                    gains.append(row)
                elif delta < 0:
                    losses.append(row)
                else:
                    unchanged += 1
            component_rows[metric] = {
                "gains": gains,
                "losses": losses,
                "unchanged_count": unchanged,
            }
        output[component] = component_rows
    return output


def _aggregate_joint(
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    arm_summary = {}
    for arm in ARM_SPECS:
        rows = [row for row in records if row["arm"] == arm]
        present = [row for row in rows if row["audit"]["gold_present"]]
        unique = [
            row for row in rows if row["audit"]["gold_status"] == "unique"
        ]
        top_ids_by_case = {}
        for row in rows:
            ranking = row["output"].get("ranking") or ()
            top_ids_by_case.setdefault(str(row["case_id"]), []).append(
                str(ranking[0]) if ranking else ""
            )

        def metrics(values):
            return {
                metric: statistics.fmean(
                    float(row["audit"][metric]) for row in values
                )
                for metric in ("top1", "top2", "rr", "structural_reach")
            }

        arm_summary[arm] = {
            "n_records": len(rows),
            "all17": metrics(rows),
            "gold_present": {
                "n_records": len(present),
                **metrics(present),
            },
            "unique_path_top1": (
                statistics.fmean(
                    bool(row["audit"]["unique_path_top1"])
                    for row in unique
                ) if unique else None
            ),
            "schema_valid_rate": statistics.fmean(
                bool(row["schema_valid"]) for row in rows
            ),
            "repair_rate": statistics.fmean(
                bool(row["repair_used"]) for row in rows
            ),
            "mean_candidate_count": statistics.fmean(
                int(row.get("candidate_count") or 0) for row in rows
            ),
            "mean_estimated_llm_calls": statistics.fmean(
                int(row.get("estimated_llm_calls") or 0) for row in rows
            ),
            "top1_stability": statistics.fmean(
                max(Counter(values).values()) / len(values)
                for values in top_ids_by_case.values()
            ),
            "error_attribution": dict(Counter(
                str(row["audit"]["error_attribution"]) for row in rows
            )),
            "by_case": {
                case_id: {
                    "top1": statistics.fmean(
                        bool(row["audit"]["top1"]) for row in rows
                        if str(row["case_id"]) == case_id
                    ),
                    "top2": statistics.fmean(
                        bool(row["audit"]["top2"]) for row in rows
                        if str(row["case_id"]) == case_id
                    ),
                    "rr": statistics.fmean(
                        float(row["audit"]["rr"]) for row in rows
                        if str(row["case_id"]) == case_id
                    ),
                    "structural_reach": statistics.fmean(
                        bool(row["audit"]["structural_reach"]) for row in rows
                        if str(row["case_id"]) == case_id
                    ),
                    "top1_ids": [
                        str((row["output"].get("ranking") or [""])[0])
                        for row in rows if str(row["case_id"]) == case_id
                    ],
                }
                for case_id in sorted(top_ids_by_case)
            },
        }
    return {"arms": arm_summary}


def _error_decomposition(
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    output = {}
    for arm in ARM_SPECS:
        rows = [
            row for row in records
            if row["arm"] == arm and row["audit"]["gold_present"]
        ]
        output[arm] = {
            "n": len(rows),
            "error_attribution": dict(Counter(
                str(row["audit"]["error_attribution"]) for row in rows
            )),
            "structural_reach_rate": statistics.fmean(
                bool(row["audit"]["structural_reach"]) for row in rows
            ),
            "local_champion_recall_rate": statistics.fmean(
                bool(row["audit"]["local_champion_recall"]) for row in rows
            ),
            "schema_valid_rate": statistics.fmean(
                bool(row["schema_valid"]) for row in rows
            ),
            "case_replicates_by_error": {
                attribution: [
                    {
                        "replicate": int(row["replicate"]),
                        "case_id": str(row["case_id"]),
                    }
                    for row in rows
                    if str(row["audit"]["error_attribution"]) == attribution
                ]
                for attribution in sorted({
                    str(row["audit"]["error_attribution"]) for row in rows
                })
            },
        }
    return output


def _asset_decomposition(output_dir: Path) -> dict[str, Any]:
    old_vs_true = 0
    true_vs_dynamic = 0
    order_mismatch = 0
    dynamic_matches_true_f2 = 0
    units = 0
    for path in sorted((output_dir / "traces").glob("*.json")):
        row = json.loads(path.read_text(encoding="utf-8"))
        records = {item["arm"]: item for item in row["records"]}
        old_ids = records["A0-bug-catalog-f2"]["champion_ids"]
        true_ids = records["A1-order-fixed-f2"]["champion_ids"]
        dynamic_ids = records["A3-joint-primary"]["champion_ids"]
        old_vs_true += old_ids != true_ids
        true_vs_dynamic += true_ids != dynamic_ids
        order_mismatch += (
            records["A0-bug-catalog-f2"]["catalog_f2_fact_ids"]
            != records["A0-bug-catalog-f2"]["true_l1_f2_fact_ids"]
        )
        dynamic_matches_true_f2 += (
            records["A3-joint-primary"]["selected_fact_ids"]
            == records["A3-joint-primary"]["true_l1_f2_fact_ids"]
        )
        units += 1
    return {
        "case_replicates": units,
        "catalog_f2_order_mismatch": order_mismatch,
        "old_vs_true_champion_set_changed": old_vs_true,
        "true_vs_dynamic_champion_set_changed": true_vs_dynamic,
        "dynamic_between_exactly_matches_true_f2": (
            dynamic_matches_true_f2
        ),
    }


def _enrich_call_counts(
    records: Sequence[dict[str, Any]],
    output_dir: Path,
) -> None:
    counts = {}
    for path in sorted((output_dir / "traces").glob("*.json")):
        trace = json.loads(path.read_text(encoding="utf-8"))
        key = (int(trace["replicate"]), str(trace["case_id"]))
        local_counts = {
            "bug": len(trace["true_assets"]["local_outputs"]),
            "true": _local_asset_call_count(trace["true_assets"]),
            "dynamic": _local_asset_call_count(trace["dynamic_assets"]),
        }
        between_calls = _selection_call_count(trace["between_selection"])
        counts[key] = (local_counts, between_calls)
    for record in records:
        local_counts, between_calls = counts[(
            int(record["replicate"]), str(record["case_id"]),
        )]
        spec = ARM_SPECS[str(record["arm"])]
        record["estimated_llm_calls"] = (
            local_counts[str(spec["champions"])]
            + (
                between_calls
                if spec["evidence"] == "dynamic_f2" else 0
            )
            + 1
        )


def run(args: argparse.Namespace) -> dict[str, Any]:
    args.output_dir.mkdir(parents=True, exist_ok=True)
    _, full_record_rows = base._load_full_records(args.base_output_dir)
    full_records = {
        (int(row["replicate"]), str(row["case_id"])): row
        for row in full_record_rows
    }
    frozen_manifest, frozen_assets = base._load_frozen_assets(
        args.base_output_dir,
    )
    fixture_doc, fixture_cases = base._fixture_cases(args.fixture)
    cases = base._runtime_cases(args.cases, args.limit)
    gold_doc = json.loads(args.gold.read_text(encoding="utf-8"))
    gold_cases = base.validate_l2_gold(
        gold_doc,
        tree_dir=args.tree_dir,
        expected_case_ids=[str(case["id"]) for case in cases],
    )
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
                fixture_cases=fixture_cases,
                frozen_assets=frozen_assets,
                full_records=full_records,
                gold_cases=gold_cases,
            )
            for replicate in range(1, args.replicates + 1)
        ]
        for future in as_completed(futures):
            records.extend(future.result())
    _enrich_call_counts(records, args.output_dir)
    records.sort(key=lambda row: (
        row["arm"], row["replicate"], row["case_id"],
    ))
    aggregate = _aggregate_joint(records)
    summary = {
        "schema_version": 1,
        "protocol_version": 2,
        "model": args.model,
        "temperature": args.temperature,
        "replicates": args.replicates,
        "arm_specs": ARM_SPECS,
        "component_comparisons": COMPONENT_COMPARISONS,
        "input_hashes": {
            "fixture": stable_hash(fixture_doc),
            "gold": stable_hash(gold_doc),
            "frozen_manifest": frozen_manifest[
                "frozen_manifest_hash"
            ],
            "harness_sha256": _sha256(Path(__file__)),
            "selector_prompt_sha256": _sha256(dynamic.PROMPT_PATH),
            "annotator_prompt_sha256": _sha256(
                base.ANNOTATOR_PROMPT_PATH,
            ),
            "arbiter_prompt_sha256": _sha256(
                JOINT_ARBITER_PROMPT_PATH,
            ),
        },
        "performance": aggregate,
        "component_bootstrap": _component_bootstrap(
            records, n_boot=args.n_boot,
        ),
        "component_transitions": _component_transitions(records),
        "error_decomposition": _error_decomposition(records),
        "asset_decomposition": _asset_decomposition(args.output_dir),
        "records": records,
    }
    base._atomic_json(args.output_dir / "summary.json", summary)
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=base.bfs.DEFAULT_MODEL)
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
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    result = run(parse_args())
    print(json.dumps({
        "arms": result["performance"]["arms"],
        "asset_decomposition": result["asset_decomposition"],
        "error_decomposition": result["error_decomposition"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
