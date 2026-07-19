#!/usr/bin/env python3
"""Replay label-blind L2 downstream variants A5 and A11--A17.

The input is either a frozen JSON document with a ``cases`` list or a generation
matrix output directory.  Each case supplies ``tree``, ``vignette`` (or
``case_text``), ``findings``, ``evidence_order``, ``parent_priors`` and,
optionally, branch-generation ``recall_audit`` rows.
No model answer is synthesized: every support or ranking decision is obtained
through ``CachedLLM`` and invalid schemas are repaired at most once.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import sys
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import eval_l2_competition_strategies as competition  # noqa: E402
from agentclinic_tree_dx.l1_evidence_bfs import (  # noqa: E402
    assert_no_gold_leak,
    stable_hash,
)
from agentclinic_tree_dx.llm_client import RobustLLMClient  # noqa: E402

SCHEMA_VERSION = 1
PROTOCOL_VERSION = 1
ARMS = ("A5", "A11", "A12", "A13", "A14", "A15", "A16", "A17")
_CACHE_LOCKS: dict[str, threading.Lock] = {}
_CACHE_LOCKS_GUARD = threading.Lock()


class CountingCachedLLM:
    def __init__(self, cached: Any) -> None:
        self.cached = cached
        self.requested = 0
        self.model_calls = 0
        self.cache_hits = 0

    def call(
        self, module: str, prompt: str, payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        key = stable_hash({
            "model": self.cached.model,
            "temperature": self.cached.temperature,
            "module": module,
            "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
            "payload": payload,
        })
        self.requested += 1
        if key in self.cached.cache:
            self.cache_hits += 1
        else:
            self.model_calls += 1
        return self.cached.call(module, prompt, payload)

    def accounting(self) -> dict[str, int]:
        return {
            "requested": self.requested,
            "model": self.model_calls,
            "cache_hits": self.cache_hits,
        }
SUPPORTING_EFFECTS = frozenset({"weak_for", "moderate_for", "strong_for"})
DEFAULT_OUTPUT = ROOT / "logs" / "l2_a_variant_downstream_v1"
DEFAULT_GENERATION_OUTPUT = ROOT / "logs" / "l2_a_variant_matrix_v1"
DEFAULT_FINDING_FIXTURE = competition.DEFAULT_FIXTURE

RANK_PROMPT = """Rank every supplied concrete L2 candidate against the others.
Use only the vignette and selected observed evidence.  A parent_prior, when
present, is a soft prior and is not evidence.  Return strict JSON containing
ranked_candidate_ids with every supplied candidate ID exactly once, best first,
and an optional why object.  Do not invent findings or candidates."""

SUPPORT_PROMPT = """Audit whether each supplied concrete L2 candidate has direct
support in selected_evidence.  Return strict JSON:
{"candidate_support": {"candidate-id": {"supported": true,
"evidence_ids": ["finding-id"]}}}
Include every candidate exactly once.  evidence_ids must be selected finding
IDs.  Generic vignette similarity or a parent prior is not evidence support."""


def _normal(value: Any) -> str:
    return " ".join(str(value or "").casefold().split())


def _tree_state(tree: Mapping[str, Any]) -> Mapping[str, Any]:
    state = tree.get("state", tree)
    if not isinstance(state, Mapping):
        raise TypeError("tree/state must be an object")
    return state


def _parent_prior_map(value: Any) -> dict[str, float]:
    if isinstance(value, Mapping):
        return {str(key): max(float(score), 0.0) for key, score in value.items()}
    return {
        str(row["id"]): max(float(row["posterior"]), 0.0)
        for row in value or ()
    }


def temper_parent_priors(
    priors: Mapping[str, float],
    temperature: float,
) -> dict[str, float]:
    """Apply p**(1/T) and normalise; T=inf is exactly uniform."""
    keys = sorted(str(key) for key in priors)
    if not keys:
        return {}
    if temperature <= 0 or math.isnan(temperature):
        raise ValueError("prior temperature must be positive")
    if math.isinf(temperature):
        return {key: 1.0 / len(keys) for key in keys}
    weights = {
        key: max(float(priors[key]), 1e-12) ** (1.0 / temperature)
        for key in keys
    }
    total = sum(weights.values())
    return {key: weights[key] / total for key in keys}


def provenance_rrf_score(
    provenance: Sequence[Mapping[str, Any]],
    *,
    k: int = 60,
) -> float:
    """RRF over independent source/query rankings, deduplicating repeated hits."""
    if k < 1:
        raise ValueError("RRF k must be >= 1")
    best: dict[tuple[str, str], int] = {}
    for row in provenance:
        rank = int(row.get("rank") or 0)
        if rank < 1:
            continue
        key = (str(row.get("source") or ""), str(row.get("query") or ""))
        best[key] = min(rank, best.get(key, rank))
    return sum(1.0 / (k + rank) for rank in best.values())


def leaf_candidates(
    tree: Mapping[str, Any],
    parent_priors: Mapping[str, float],
    recall_audit: Sequence[Mapping[str, Any]] = (),
    *,
    allow_empty: bool = False,
) -> list[dict[str, Any]]:
    """Extract live L2 leaves and attach exact-label generation provenance."""
    branches = dict(_tree_state(tree).get("branches") or {})
    audit_by_parent = {
        str(row.get("parent_id") or ""): row for row in recall_audit
    }
    rows = []
    for branch_id, branch in branches.items():
        if (
            not isinstance(branch, Mapping)
            or int(branch.get("level") or 0) != 2
            or str(branch.get("status") or "live") == "closed_for_now"
        ):
            continue
        parent_id = str(branch.get("parent") or "")
        parent = branches.get(parent_id) or {}
        matches = [
            item for item in (
                audit_by_parent.get(parent_id, {}).get("candidates") or ()
            )
            if isinstance(item, Mapping)
            and _normal(item.get("disease")) == _normal(branch.get("label"))
        ]
        provenance = [
            dict(item)
            for match in matches
            for item in match.get("provenance") or ()
            if isinstance(item, Mapping)
        ]
        rows.append({
            "id": str(branch_id),
            "label": str(branch.get("label") or ""),
            "parent_id": parent_id,
            "parent_label": str(parent.get("label") or ""),
            "parent_posterior": float(parent_priors.get(parent_id, 0.0)),
            "provenance": provenance,
            "provenance_rrf": provenance_rrf_score(provenance),
        })
    if not rows and not allow_empty:
        raise ValueError("tree has no live L2 candidates")
    return sorted(rows, key=lambda row: (row["parent_id"], row["id"]))


def provenance_core_shadow(
    candidates: Sequence[Mapping[str, Any]],
    *,
    top_n: int = 3,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Keep provenance-RRF top-N per parent as core and retain the rest shadow."""
    if top_n < 1:
        raise ValueError("top_n must be >= 1")
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for raw in candidates:
        grouped[str(raw["parent_id"])].append(dict(raw))
    core, shadow = [], []
    for parent_id in sorted(grouped):
        ordered = sorted(
            grouped[parent_id],
            key=lambda row: (-float(row.get("provenance_rrf") or 0.0), row["id"]),
        )
        core.extend(ordered[:top_n])
        shadow.extend(ordered[top_n:])
    return core, shadow


def build_cache_identity(
    *,
    tree: Mapping[str, Any],
    payload: Mapping[str, Any],
    evidence: Sequence[Mapping[str, Any]],
    champions: Sequence[Mapping[str, Any]],
    priors: Mapping[str, float],
) -> dict[str, Any]:
    """Bind cache reuse to every mutable replay input named by the protocol."""
    return {
        "protocol_version": PROTOCOL_VERSION,
        "tree_hash": stable_hash(tree),
        "payload_hash": stable_hash(payload),
        "evidence_hash": stable_hash(list(evidence)),
        "champion_hash": stable_hash(list(champions)),
        "prior_hash": stable_hash(dict(priors)),
    }


def _clean_ranking(
    response: Mapping[str, Any],
    candidate_ids: Sequence[str],
) -> dict[str, Any]:
    ranked = response.get("ranked_candidate_ids") or ()
    if isinstance(ranked, str):
        ranked = [ranked]
    ranking = [str(value) for value in ranked]
    expected = [str(value) for value in candidate_ids]
    valid = (
        len(ranking) == len(expected)
        and len(set(ranking)) == len(ranking)
        and set(ranking) == set(expected)
    )
    why = response.get("why")
    return {
        "schema_valid": valid,
        "ranking": ranking if valid else [],
        "why": dict(why) if isinstance(why, Mapping) else {},
        "raw": dict(response),
        "rejected": [] if valid else ["incomplete_candidate_ranking"],
    }


def _candidate_payload_rows(
    candidates: Sequence[Mapping[str, Any]],
    priors: Mapping[str, float],
) -> list[dict[str, Any]]:
    return [{
        "id": str(row["id"]),
        "label": str(row.get("label") or ""),
        "parent_id": str(row.get("parent_id") or ""),
        "parent_label": str(row.get("parent_label") or ""),
        "parent_prior": float(priors.get(str(row.get("parent_id") or ""), 0.0)),
        "provenance_rrf": float(row.get("provenance_rrf") or 0.0),
    } for row in candidates]


def _rank_with_repair(
    *,
    cache: Any,
    module: str,
    tree: Mapping[str, Any],
    vignette: str,
    evidence: Sequence[Mapping[str, Any]],
    candidates: Sequence[Mapping[str, Any]],
    parent_priors: Mapping[str, float],
    prior_temperature: float = 1.0,
) -> dict[str, Any]:
    if not candidates:
        return {
            "schema_valid": False,
            "repair_used": False,
            "ranking": [],
            "rejected": ["no_candidates"],
            "cache_identity": {},
        }
    priors = temper_parent_priors(parent_priors, prior_temperature)
    rows = _candidate_payload_rows(candidates, priors)
    semantic_payload = {
        "vignette": vignette,
        "selected_evidence": list(evidence),
        "candidates": rows,
        "prior_temperature": (
            "inf" if math.isinf(prior_temperature) else prior_temperature
        ),
    }
    identity = build_cache_identity(
        tree=tree,
        payload=semantic_payload,
        evidence=evidence,
        champions=rows,
        priors=priors,
    )
    payload = {**semantic_payload, "cache_identity": identity}
    assert_no_gold_leak(payload)
    response = cache.call(module, RANK_PROMPT, payload)
    cleaned = _clean_ranking(response, [row["id"] for row in rows])
    repair_used = False
    if not cleaned["schema_valid"]:
        repair_payload = {
            **payload,
            "invalid_response": response,
            "validation_errors": cleaned["rejected"],
            "schema_repair": "Return every supplied candidate ID exactly once.",
        }
        assert_no_gold_leak(repair_payload)
        response = cache.call(f"{module}Repair", RANK_PROMPT, repair_payload)
        cleaned = _clean_ranking(response, [row["id"] for row in rows])
        repair_used = True
    return {
        **cleaned,
        "repair_used": repair_used,
        "candidates": rows,
        "cache_identity": identity,
    }


def _clean_support(
    response: Mapping[str, Any],
    candidate_ids: Sequence[str],
    evidence_ids: Sequence[str],
) -> dict[str, Any]:
    raw = response.get("candidate_support")
    rejected = []
    expected = set(candidate_ids)
    allowed_evidence = set(evidence_ids)
    if not isinstance(raw, Mapping) or set(map(str, raw or {})) != expected:
        rejected.append("incomplete_candidate_support")
        raw = raw if isinstance(raw, Mapping) else {}
    cleaned = {}
    for candidate_id in candidate_ids:
        item = raw.get(candidate_id)
        if not isinstance(item, Mapping) or not isinstance(item.get("supported"), bool):
            rejected.append(f"{candidate_id}:invalid_support")
            continue
        ids = [str(value) for value in item.get("evidence_ids") or ()]
        if not set(ids).issubset(allowed_evidence):
            rejected.append(f"{candidate_id}:unknown_evidence")
            continue
        if bool(item["supported"]) != bool(ids):
            rejected.append(f"{candidate_id}:support_evidence_mismatch")
            continue
        cleaned[candidate_id] = {
            "supported": bool(item["supported"]),
            "evidence_ids": ids,
        }
    return {
        "schema_valid": not rejected and set(cleaned) == expected,
        "candidate_support": cleaned,
        "rejected": rejected,
        "raw": dict(response),
    }


def _support_with_repair(
    *,
    cache: Any,
    tree: Mapping[str, Any],
    vignette: str,
    evidence: Sequence[Mapping[str, Any]],
    candidates: Sequence[Mapping[str, Any]],
    parent_priors: Mapping[str, float],
) -> dict[str, Any]:
    rows = _candidate_payload_rows(candidates, {})
    semantic_payload = {
        "vignette": vignette,
        "selected_evidence": list(evidence),
        "candidates": rows,
    }
    identity = build_cache_identity(
        tree=tree,
        payload=semantic_payload,
        evidence=evidence,
        champions=rows,
        priors=parent_priors,
    )
    payload = {**semantic_payload, "cache_identity": identity}
    assert_no_gold_leak(payload)
    response = cache.call("L2A12EvidenceSupportGate", SUPPORT_PROMPT, payload)
    candidate_ids = [row["id"] for row in rows]
    evidence_ids = [str(row["id"]) for row in evidence]
    cleaned = _clean_support(response, candidate_ids, evidence_ids)
    repair_used = False
    if not cleaned["schema_valid"]:
        repair_payload = {
            **payload,
            "invalid_response": response,
            "validation_errors": cleaned["rejected"],
            "schema_repair": (
                "Return every candidate with a boolean supported and only "
                "selected evidence IDs."
            ),
        }
        assert_no_gold_leak(repair_payload)
        response = cache.call(
            "L2A12EvidenceSupportGateRepair", SUPPORT_PROMPT, repair_payload,
        )
        cleaned = _clean_support(response, candidate_ids, evidence_ids)
        repair_used = True
    return {
        **cleaned,
        "repair_used": repair_used,
        "cache_identity": identity,
    }


def apply_evidence_support_gate(
    candidates: Sequence[Mapping[str, Any]],
    support_output: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Move unsupported candidates to shadow; invalid gate retains all safely."""
    rows = [dict(row) for row in candidates]
    if not support_output.get("schema_valid"):
        return rows, []
    support = support_output.get("candidate_support") or {}
    active = [row for row in rows if support[str(row["id"])]["supported"]]
    shadow = [row for row in rows if not support[str(row["id"])]["supported"]]
    return active, shadow


def leave_one_out_prune(
    baseline_ranking: Sequence[str],
    candidates: Sequence[Mapping[str, Any]],
    counterfactuals: Mapping[str, Mapping[str, Any]],
    *,
    protected_top: int = 3,
) -> dict[str, Any]:
    """Prune only lower-ranked candidates with a valid invariant LOO replay."""
    ids = [str(row["id"]) for row in candidates]
    baseline = [str(value) for value in baseline_ranking]
    protected = set(baseline[:protected_top])
    pruned = []
    schema = {}
    for candidate_id in ids:
        if candidate_id in protected:
            continue
        output = counterfactuals.get(candidate_id) or {}
        valid = bool(output.get("schema_valid"))
        expected = [value for value in baseline if value != candidate_id]
        invariant = valid and list(output.get("ranking") or ()) == expected
        schema[candidate_id] = {
            "schema_valid": valid,
            "repair_used": bool(output.get("repair_used")),
            "fail_closed": not valid,
            "invariant": invariant,
        }
        if invariant:
            pruned.append(candidate_id)
    return {
        "active_ids": [value for value in ids if value not in set(pruned)],
        "pruned_ids": pruned,
        "counterfactual_schema": schema,
    }


def rank_movement(
    reference: Sequence[str],
    current: Sequence[str],
) -> dict[str, dict[str, int | None]]:
    left = {str(value): index for index, value in enumerate(reference, start=1)}
    right = {str(value): index for index, value in enumerate(current, start=1)}
    return {
        candidate_id: {
            "from": left.get(candidate_id),
            "to": right.get(candidate_id),
            "delta": (
                left[candidate_id] - right[candidate_id]
                if candidate_id in left and candidate_id in right else None
            ),
        }
        for candidate_id in sorted(set(left) | set(right))
    }


def _arm_trace(
    *,
    active: Sequence[Mapping[str, Any]],
    shadow: Sequence[Mapping[str, Any]],
    pruned: Sequence[str],
    output: Mapping[str, Any],
    reference_ranking: Sequence[str],
    champions: Sequence[Mapping[str, Any]] = (),
    extra_repairs: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    repairs = [
        {
            "repair_used": bool(output.get("repair_used")),
            "schema_valid": bool(output.get("schema_valid")),
        },
        *[dict(row) for row in extra_repairs],
    ]
    return {
        "active": [str(row["id"]) for row in active],
        "shadow": [str(row["id"]) for row in shadow],
        "pruned": [str(value) for value in pruned],
        "movement": rank_movement(reference_ranking, output.get("ranking") or ()),
        "champion": [str(row["id"]) for row in champions],
        "schema_repair": repairs,
        "output": dict(output),
    }


def _local_rankings(
    *,
    cache: Any,
    tree: Mapping[str, Any],
    vignette: str,
    evidence: Sequence[Mapping[str, Any]],
    candidates: Sequence[Mapping[str, Any]],
    parent_priors: Mapping[str, float],
) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in candidates:
        grouped[str(row["parent_id"])].append(dict(row))
    return {
        parent_id: _rank_with_repair(
            cache=cache,
            module="L2A14LocalF4",
            tree=tree,
            vignette=vignette,
            evidence=evidence,
            candidates=rows,
            parent_priors={parent_id: 1.0},
        )
        for parent_id, rows in sorted(grouped.items())
    }


def _champions(
    candidates: Sequence[Mapping[str, Any]],
    local_outputs: Mapping[str, Mapping[str, Any]],
    count: int,
) -> list[dict[str, Any]]:
    by_id = {str(row["id"]): dict(row) for row in candidates}
    result = []
    for parent_id, output in sorted(local_outputs.items()):
        if not output.get("schema_valid"):
            continue
        for candidate_id in list(output.get("ranking") or ())[:count]:
            row = dict(by_id[str(candidate_id)])
            row["champion_rank"] = len([
                item for item in result if item["parent_id"] == parent_id
            ]) + 1
            result.append(row)
    return result


def _facts(
    case: Mapping[str, Any],
    limit: int,
) -> list[dict[str, Any]]:
    findings = {
        str(row["id"]): dict(row) for row in case.get("findings") or ()
    }
    order = [
        str(value.get("id") if isinstance(value, Mapping) else value)
        for value in case.get("evidence_order") or ()
    ]
    missing = [fact_id for fact_id in order[:limit] if fact_id not in findings]
    if missing:
        raise ValueError(f"evidence_order IDs missing from findings: {missing}")
    return [findings[fact_id] for fact_id in order[:limit]]


def case_run_identity(case: Mapping[str, Any]) -> dict[str, Any]:
    """Stable resume/run identity shared by CLI resume and replay records."""
    tree = case["tree"]
    parent_priors = _parent_prior_map(case.get("parent_priors") or {})
    leaves = leaf_candidates(
        tree, parent_priors, case.get("recall_audit") or (), allow_empty=True,
    )
    return build_cache_identity(
        tree=tree,
        payload={
            "vignette": str(case.get("vignette") or case.get("case_text") or ""),
            "candidate_ids": [row["id"] for row in leaves],
            "source_arm": str(case.get("source_arm") or "A-raw"),
            "replicate": int(case.get("replicate") or 1),
        },
        evidence=_facts(case, 4),
        champions=leaves,
        priors=parent_priors,
    )


def replay_case(case: Mapping[str, Any], cache: Any) -> dict[str, Any]:
    """Execute all downstream variants against one immutable case/tree.

    Each pure-downstream arm is isolated against the A-raw leaf pool. A16 alone
    may compose a quality-gated core as its registered input; A11+A12 remains an
    auxiliary comparison rather than a hidden prerequisite for other arms.
    """
    tree = dict(case["tree"])
    declared_tree_hash = str(case.get("tree_hash") or "")
    if declared_tree_hash and stable_hash(tree) != declared_tree_hash:
        raise ValueError("replay tree hash mismatch")
    vignette = str(case.get("vignette") or case.get("case_text") or "")
    parent_priors = _parent_prior_map(case.get("parent_priors") or {})
    leaves = leaf_candidates(
        tree, parent_priors, case.get("recall_audit") or (),
    )
    evidence_f2 = _facts(case, 2)
    evidence_f4 = _facts(case, 4)
    if len(evidence_f2) < 2:
        raise ValueError("downstream replay requires at least two evidence items")

    baseline_local = _local_rankings(
        cache=cache, tree=tree, vignette=vignette, evidence=evidence_f2,
        candidates=leaves, parent_priors=parent_priors,
    )
    baseline_champion = _champions(leaves, baseline_local, 1)
    baseline_output = _rank_with_repair(
        cache=cache, module="L2ABaselineIntergroupF2", tree=tree,
        vignette=vignette, evidence=evidence_f2,
        candidates=baseline_champion, parent_priors=parent_priors,
    )
    baseline_trace = _arm_trace(
        active=baseline_champion, shadow=[], pruned=[],
        output=baseline_output,
        reference_ranking=baseline_output.get("ranking") or (),
        champions=baseline_champion,
        extra_repairs=[
            {
                "stage": "baseline_local_f2",
                "parent_id": parent_id,
                "repair_used": bool(output.get("repair_used")),
                "schema_valid": bool(output.get("schema_valid")),
            }
            for parent_id, output in baseline_local.items()
        ],
    )
    baseline_trace["evidence_budget"] = {
        "local": "true_F2",
        "intergroup": "true_F2",
    }

    a5_output = _rank_with_repair(
        cache=cache, module="L2A5RawGlobalArbiter", tree=tree,
        vignette=vignette, evidence=evidence_f2, candidates=leaves,
        parent_priors=parent_priors,
    )
    a5_ranking = list(a5_output.get("ranking") or ())
    traces: dict[str, Any] = {
        "A5": _arm_trace(
            active=leaves, shadow=[], pruned=[], output=a5_output,
            reference_ranking=a5_ranking,
        )
    }

    # A11: only core/shadow activation over the full A-raw pool.
    core, provenance_shadow = provenance_core_shadow(leaves, top_n=3)
    a11_output = _rank_with_repair(
        cache=cache, module="L2A11ProvenanceRRF", tree=tree,
        vignette=vignette, evidence=evidence_f2, candidates=core,
        parent_priors=parent_priors,
    )
    traces["A11"] = _arm_trace(
        active=core, shadow=provenance_shadow, pruned=[], output=a11_output,
        reference_ranking=a5_ranking,
    )

    # A12: absolute evidence-support gate over all A leaves (not A11 core).
    support_all = _support_with_repair(
        cache=cache, tree=tree, vignette=vignette, evidence=evidence_f4,
        candidates=leaves, parent_priors=parent_priors,
    )
    gated_all, unsupported_all = apply_evidence_support_gate(leaves, support_all)
    a12_output = _rank_with_repair(
        cache=cache, module="L2A12SupportedGlobal", tree=tree,
        vignette=vignette, evidence=evidence_f2, candidates=gated_all,
        parent_priors=parent_priors,
    )
    support_all_repair = {
        "stage": "evidence_support",
        "repair_used": bool(support_all.get("repair_used")),
        "schema_valid": bool(support_all.get("schema_valid")),
    }
    traces["A12"] = _arm_trace(
        active=gated_all, shadow=unsupported_all, pruned=[], output=a12_output,
        reference_ranking=a5_ranking, extra_repairs=[support_all_repair],
    )

    # A13: counterfactual prune over the A-raw pool; baseline is A5 ranking.
    counterfactuals = {}
    for candidate_id in a5_ranking[3:]:
        remaining = [row for row in leaves if str(row["id"]) != candidate_id]
        counterfactuals[candidate_id] = _rank_with_repair(
            cache=cache, module="L2A13LeaveOneOut", tree=tree,
            vignette=vignette, evidence=evidence_f2, candidates=remaining,
            parent_priors=parent_priors,
        )
    prune = leave_one_out_prune(a5_ranking, leaves, counterfactuals)
    pruned_set = set(prune["pruned_ids"])
    a13_active = [row for row in leaves if str(row["id"]) not in pruned_set]
    a13_output = _rank_with_repair(
        cache=cache, module="L2A13CounterfactualPruned", tree=tree,
        vignette=vignette, evidence=evidence_f2, candidates=a13_active,
        parent_priors=parent_priors,
    )
    traces["A13"] = _arm_trace(
        active=a13_active, shadow=[], pruned=prune["pruned_ids"],
        output=a13_output, reference_ranking=a5_ranking,
        extra_repairs=[
            {
                "stage": "leave_one_out",
                "candidate_id": key,
                **value,
            }
            for key, value in prune["counterfactual_schema"].items()
        ],
    )
    traces["A13"]["counterfactual_schema"] = prune["counterfactual_schema"]

    # A14/A15/A17: local F4 + champion handoff over the full A-raw pool.
    local_outputs = _local_rankings(
        cache=cache, tree=tree, vignette=vignette, evidence=evidence_f4,
        candidates=leaves, parent_priors=parent_priors,
    )
    one_champion = _champions(leaves, local_outputs, 1)
    two_champions = _champions(leaves, local_outputs, 2)
    local_repairs = [
        {
            "stage": "local_f4",
            "parent_id": parent_id,
            "repair_used": bool(output.get("repair_used")),
            "schema_valid": bool(output.get("schema_valid")),
        }
        for parent_id, output in local_outputs.items()
    ]
    a14_output = _rank_with_repair(
        cache=cache, module="L2A14IntergroupF2", tree=tree,
        vignette=vignette, evidence=evidence_f2, candidates=one_champion,
        parent_priors=parent_priors,
    )
    traces["A14"] = _arm_trace(
        active=one_champion, shadow=[], pruned=[],
        output=a14_output, reference_ranking=a5_ranking,
        champions=one_champion, extra_repairs=local_repairs,
    )
    traces["A14"]["evidence_budget"] = {
        "local": "dynamic_F4",
        "intergroup": "true_F2",
    }

    a15_output = _rank_with_repair(
        cache=cache, module="L2A15TwoChampionIntergroupF2", tree=tree,
        vignette=vignette, evidence=evidence_f2, candidates=two_champions,
        parent_priors=parent_priors,
    )
    traces["A15"] = _arm_trace(
        active=two_champions, shadow=[], pruned=[],
        output=a15_output, reference_ranking=a5_ranking,
        champions=two_champions, extra_repairs=local_repairs,
    )

    # A16: registered quality-gated core input; gate shared with its reference.
    support_by_id = (support_all.get("candidate_support") or {}) if support_all.get(
        "schema_valid"
    ) else {
        str(row["id"]): {"supported": True} for row in leaves
    }
    gated_core = [
        row for row in core
        if bool((support_by_id.get(str(row["id"])) or {}).get("supported", True))
    ]
    gated_core_shadow = [
        row for row in leaves if str(row["id"]) not in {str(r["id"]) for r in gated_core}
    ]
    a16_local = _local_rankings(
        cache=cache, tree=tree, vignette=vignette, evidence=evidence_f4,
        candidates=gated_core, parent_priors=parent_priors,
    )
    a16_champion = _champions(gated_core, a16_local, 1)
    a16_local_repairs = [
        {
            "stage": "local_f4",
            "parent_id": parent_id,
            "repair_used": bool(output.get("repair_used")),
            "schema_valid": bool(output.get("schema_valid")),
        }
        for parent_id, output in a16_local.items()
    ]
    quality_gate_identity = stable_hash({
        "active": [row["id"] for row in gated_core],
        "shadow": [row["id"] for row in gated_core_shadow],
        "support_identity": support_all.get("cache_identity") or {},
        "core_ids": [row["id"] for row in core],
    })
    a16_reference = _rank_with_repair(
        cache=cache, module="L2A16SingleChampionReference", tree=tree,
        vignette=vignette, evidence=evidence_f2, candidates=a16_champion,
        parent_priors=parent_priors,
    )
    a16_global = _rank_with_repair(
        cache=cache, module="L2A16GlobalLeafArbiter", tree=tree,
        vignette=vignette, evidence=evidence_f2, candidates=gated_core,
        parent_priors=parent_priors,
    )
    traces["A16"] = {
        "active": [str(row["id"]) for row in gated_core],
        "shadow": [str(row["id"]) for row in gated_core_shadow],
        "pruned": [],
        "movement": {
            "single_champion_reference": rank_movement(
                a5_ranking, a16_reference.get("ranking") or (),
            ),
            "global_leaf_arbiter": rank_movement(
                a5_ranking, a16_global.get("ranking") or (),
            ),
        },
        "champion": [str(row["id"]) for row in a16_champion],
        "schema_repair": [
            support_all_repair,
            *a16_local_repairs,
            {
                "stage": "single_champion_reference",
                "repair_used": bool(a16_reference.get("repair_used")),
                "schema_valid": bool(a16_reference.get("schema_valid")),
            },
            {
                "stage": "global_leaf_arbiter",
                "repair_used": bool(a16_global.get("repair_used")),
                "schema_valid": bool(a16_global.get("schema_valid")),
            },
        ],
        "quality_gate_identity": quality_gate_identity,
        "single_champion_reference": a16_reference,
        "global_leaf_arbiter": a16_global,
    }

    sensitivities = {}
    for label, temperature in (("1.5", 1.5), ("2", 2.0), ("inf", math.inf)):
        sensitivities[label] = _rank_with_repair(
            cache=cache, module="L2A17PriorTemperature", tree=tree,
            vignette=vignette, evidence=evidence_f2,
            candidates=one_champion, parent_priors=parent_priors,
            prior_temperature=temperature,
        )
    primary = sensitivities["2"]
    traces["A17"] = _arm_trace(
        active=one_champion, shadow=[], pruned=[],
        output=primary, reference_ranking=a5_ranking,
        champions=one_champion,
        extra_repairs=[
            {
                "stage": f"prior_temperature_{label}",
                "repair_used": bool(output.get("repair_used")),
                "schema_valid": bool(output.get("schema_valid")),
            }
            for label, output in sensitivities.items()
        ],
    )
    traces["A17"]["prior_temperature"] = 2.0
    traces["A17"]["sensitivity"] = sensitivities

    combo_local = _local_rankings(
        cache=cache, tree=tree, vignette=vignette, evidence=evidence_f4,
        candidates=core, parent_priors=parent_priors,
    )
    combo_champion = _champions(core, combo_local, 1)
    combo_a11_a14_output = _rank_with_repair(
        cache=cache, module="L2ComboA11A14IntergroupF2", tree=tree,
        vignette=vignette, evidence=evidence_f2,
        candidates=combo_champion, parent_priors=parent_priors,
    )
    combinations = {
        "A11+A14": _arm_trace(
            active=combo_champion,
            shadow=provenance_shadow,
            pruned=[],
            output=combo_a11_a14_output,
            reference_ranking=a5_ranking,
            champions=combo_champion,
        ),
        "A11+A16": copy.deepcopy(traces["A16"]),
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "case_id": str(case["case_id"]),
        "source_arm": str(case.get("source_arm") or "A-raw"),
        "replicate": int(case.get("replicate") or 1),
        "identity": case_run_identity(case),
        "baseline": baseline_trace,
        "arms": traces,
        "combinations": combinations,
    }


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _strip_prefix(value: str, prefix: str) -> str:
    return value[len(prefix):] if value.startswith(prefix) else value


def _generation_cases(
    generation_output: Path,
    finding_fixture: Path,
    source_arms: Sequence[str],
) -> dict[str, Any]:
    """Join label-blind generation traces to frozen evidence by case/replicate."""
    manifest = _read_json(generation_output / "generation" / "manifest.json")
    fixture = _read_json(finding_fixture)
    fixture_cases = {
        str(row["case_id"]): row for row in fixture.get("cases") or ()
    }
    if not fixture_cases:
        raise ValueError("finding fixture has no cases")
    wanted = set(source_arms)
    cases = []
    for key in sorted(manifest.get("tree_hashes") or {}):
        arm, replicate_token, case_id = key.split("/", 2)
        if arm not in wanted:
            continue
        replicate = int(_strip_prefix(str(replicate_token), "r"))
        trace = _read_json(
            generation_output / "generation" / "traces" / arm
            / f"r{replicate:02d}__{case_id}.json"
        )
        if str(trace.get("tree_hash") or "") != str(
            (manifest.get("tree_hashes") or {}).get(key) or ""
        ):
            raise ValueError(f"generation bridge tree_hash mismatch: {key}")
        fixture_case = fixture_cases.get(case_id)
        if fixture_case is None:
            raise ValueError(f"finding fixture missing case: {case_id}")
        filter_run = next(
            (
                row for row in fixture_case.get("filter_runs") or ()
                if int(row.get("replicate") or 0) == replicate
            ),
            None,
        )
        if filter_run is None:
            raise ValueError(
                f"finding fixture missing replicate {replicate}: {case_id}"
            )
        tree = trace["tree"]
        if stable_hash(tree) != str(trace.get("tree_hash") or ""):
            raise ValueError(f"generation trace tree hash drift: {key}")
        branches = _tree_state(tree).get("branches") or {}
        parent_priors = {
            str(branch_id): float(branch.get("posterior") or 0.0)
            for branch_id, branch in branches.items()
            if int(branch.get("level") or 0) == 1
        }
        bridge_payload = {
            "tree": tree,
            "findings": fixture_case.get("full_findings") or (),
            "evidence_order": filter_run.get("ranked_fact_ids") or (),
            "recall_audit": trace.get("recall_audit") or (),
            "transform_lineage": trace.get("transform_lineage") or (),
        }
        assert_no_gold_leak(bridge_payload)
        cases.append({
            "case_id": case_id,
            "source_arm": arm,
            "source_arm_slug": str(trace.get("arm_slug") or ""),
            "replicate": replicate,
            "tree": tree,
            "tree_hash": trace["tree_hash"],
            "protocol_sha256": str(
                (trace.get("identity") or {}).get("protocol_sha256")
                or manifest.get("protocol_sha256")
                or ""
            ),
            "source_a_tree_hash": str(
                (trace.get("identity") or {}).get("source_a_tree_hash") or ""
            ),
            "transform_lineage": copy.deepcopy(
                list(trace.get("transform_lineage") or ())
            ),
            "vignette": str(tree.get("case_summary") or ""),
            "findings": fixture_case.get("full_findings") or (),
            "evidence_order": filter_run.get("ranked_fact_ids") or (),
            "parent_priors": parent_priors,
            "recall_audit": trace.get("recall_audit") or (),
        })
    if not cases:
        raise ValueError(
            f"no generation traces for requested source arms: {sorted(wanted)}"
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "asset_kind": "l2_a_variant_downstream_replay_input",
        "generation_manifest_hash": manifest.get("manifest_hash"),
        "finding_fixture_hash": stable_hash(fixture),
        "source_arms": sorted(wanted),
        "cases": cases,
    }


def _run_case(args: argparse.Namespace, case: Mapping[str, Any]) -> dict[str, Any]:
    case_id = str(case["case_id"])
    source_arm = str(case.get("source_arm") or "A-raw")
    replicate = int(case.get("replicate") or 1)
    output_path = (
        args.output_dir / "traces" / source_arm
        / f"r{replicate:02d}__{case_id}.json"
    )
    expected_identity = case_run_identity(case)
    if output_path.is_file():
        existing = _read_json(output_path)
        existing_record = existing.get("record")
        current_schema = (
            isinstance(existing_record, Mapping)
            and "baseline" in existing_record
            and "calls" in existing_record
            and (
                source_arm not in {"A6", "A7", "A8"}
                or "combinations" in existing_record
            )
        )
        if (
            args.resume
            and existing.get("run_identity") == expected_identity
            and current_schema
        ):
            return existing_record
        if existing.get("record") and not args.resume:
            raise FileExistsError(
                "refusing to overwrite downstream trace without --resume: "
                f"{output_path}"
            )
        if (
            existing.get("record")
            and existing.get("run_identity") != expected_identity
        ):
            raise FileExistsError(
                "refusing to overwrite downstream trace with drifted "
                f"identity: {output_path}"
            )
    client = RobustLLMClient(
        model=args.model,
        call_timeout=args.call_timeout,
        max_retries=5,
        timeout_retry_cap=2,
        temperature=args.temperature,
    )
    cache_identity = stable_hash({
        "tree_hash": case.get("tree_hash"),
        "vignette": case.get("vignette") or case.get("case_text"),
        "findings": case.get("findings"),
        "evidence_order": case.get("evidence_order"),
        "parent_priors": case.get("parent_priors"),
        "model": args.model,
        "temperature": args.temperature,
    })
    cache_path = args.output_dir / "cache" / f"{cache_identity}.json"
    cache_key = str(cache_path)
    with _CACHE_LOCKS_GUARD:
        cache_lock = _CACHE_LOCKS.setdefault(cache_key, threading.Lock())
    with cache_lock:
        base_cache = competition.bfs.CachedLLM(
            client, cache_path, args.model,
        )
        cache = CountingCachedLLM(base_cache)
        try:
            record = replay_case(case, cache)
        except ValueError as exc:
            if str(exc) not in {
                "tree has no live L2 candidates",
                "downstream replay requires at least two evidence items",
            }:
                raise
            empty = {"output": {"ranking": []}, "schema_repair": []}
            record = {
                "schema_version": SCHEMA_VERSION,
                "protocol_version": PROTOCOL_VERSION,
                "case_id": case_id,
                "source_arm": source_arm,
                "replicate": replicate,
                "identity": expected_identity,
                "runtime_failure": str(exc),
                "baseline": copy.deepcopy(empty),
                "arms": {
                    arm: copy.deepcopy(empty) for arm in ARMS
                },
                "combinations": {
                    "A11+A14": copy.deepcopy(empty),
                    "A11+A16": copy.deepcopy(empty),
                },
            }
        record["calls"] = cache.accounting()
    if record.get("identity") != expected_identity:
        raise RuntimeError("replay record identity drifted from run identity")
    competition._atomic_json(output_path, {
        "schema_version": SCHEMA_VERSION,
        "run_identity": expected_identity,
        "record": record,
    })
    return record


def run(args: argparse.Namespace) -> dict[str, Any]:
    if args.input is not None:
        source = _read_json(args.input)
    else:
        source = _generation_cases(
            args.generation_output,
            args.finding_fixture,
            tuple(
                value.strip() for value in args.source_arms.split(",")
                if value.strip()
            ),
        )
    cases = list(source.get("cases") or ())
    if args.case_filter:
        wanted = {value.strip() for value in args.case_filter.split(",") if value.strip()}
        cases = [row for row in cases if str(row.get("case_id")) in wanted]
    if args.limit:
        cases = cases[:args.limit]
    if not cases:
        raise ValueError("replay input has no selected cases")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    records = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [executor.submit(_run_case, args, case) for case in cases]
        for future in as_completed(futures):
            records.append(future.result())
    records.sort(
        key=lambda row: (
            str(row["source_arm"]), int(row["replicate"]),
            str(row["case_id"]),
        )
    )
    summary = {
        "schema_version": SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "model": args.model,
        "temperature": args.temperature,
        "source_hash": stable_hash(source),
        "arms": list(ARMS),
        "records": records,
    }
    competition._atomic_json(args.output_dir / "summary.json", summary)
    return summary


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", type=Path)
    source.add_argument(
        "--generation-output",
        type=Path,
        help="generation matrix root containing generation/manifest.json",
    )
    parser.add_argument(
        "--source-arms",
        default="A-raw",
        help="comma-separated generation arms used with --generation-output",
    )
    parser.add_argument(
        "--finding-fixture", type=Path, default=DEFAULT_FINDING_FIXTURE,
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--model", default=competition.bfs.DEFAULT_MODEL)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--call-timeout", type=float, default=240.0)
    parser.add_argument("--case-filter", default="")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)
    if args.limit < 0:
        parser.error("--limit must be >= 0")
    if args.workers < 1:
        parser.error("--workers must be >= 1")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    result = run(parse_args(argv))
    print(json.dumps({
        "arms": result["arms"],
        "case_count": len(result["records"]),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
