"""Minimal branch-tree + TALP evidence evaluation pipeline.

This module deliberately owns no Controller orchestration.  A caller supplies a
frozen L1/L2 ``DiagnosticState`` plus selector/annotator callables; the module
only validates observed evidence, annotates leaves, and updates posteriors.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping

from .state import DiagnosticState
from .updater import ordinal_update

Selector = Callable[[Mapping[str, Any]], Mapping[str, Any]]
Annotator = Callable[[Mapping[str, Any]], Mapping[str, Any]]

EFFECT_LABELS = frozenset({
    "strong_for",
    "moderate_for",
    "weak_for",
    "neutral",
    "weak_against",
    "moderate_against",
    "strong_against",
})


def _items(value: Any) -> list[Any]:
    if value is None or value == "":
        return []
    if isinstance(value, (str, Mapping)):
        return [value]
    return list(value)


@dataclass(frozen=True)
class ObservedFact:
    id: str
    text: str

    def to_dict(self) -> dict[str, str]:
        return {"id": self.id, "text": self.text}


def observed_facts(items: Iterable[Any], *, limit: int = 40) -> tuple[ObservedFact, ...]:
    """Materialize a bounded, de-duplicated whitelist from vignette evidence."""
    texts: list[str] = []
    seen: set[str] = set()
    for item in items:
        if isinstance(item, Mapping):
            value = item.get("content") or item.get("text") or item.get("finding")
        else:
            value = getattr(item, "content", None) or str(item)
        text = str(value or "").strip()
        key = " ".join(text.lower().split())
        if text and key and key not in seen:
            seen.add(key)
            texts.append(text)
        if len(texts) >= limit:
            break
    return tuple(ObservedFact(f"F{index + 1}", text) for index, text in enumerate(texts))


def leaf_branches(state: DiagnosticState) -> dict[str, Any]:
    leaves = {
        branch_id: branch
        for branch_id, branch in state.branches.items()
        if branch.level == 2 and branch.status != "expanded"
    }
    if not leaves:
        raise ValueError("composed pipeline requires at least one L2 leaf")
    return leaves


def clean_selected_fact_ids(
    response: Mapping[str, Any],
    facts: tuple[ObservedFact, ...],
    *,
    limit: int,
) -> list[str]:
    """Accept only unique fact IDs from the explicit observed whitelist."""
    allowed = {fact.id for fact in facts}
    raw = response.get("ranked_fact_ids") or response.get("selected_fact_ids") or []
    if isinstance(raw, str):
        raw = [raw]
    first = response.get("best_fact_id")
    values = ([first] if first else []) + list(raw)
    selected: list[str] = []
    for value in values:
        fact_id = str(value or "").strip()
        if fact_id in allowed and fact_id not in selected:
            selected.append(fact_id)
        if len(selected) >= limit:
            break
    return selected


def clean_annotation(
    state: DiagnosticState, annotation: Mapping[str, Any]
) -> dict[str, Any]:
    """Validate effect labels and prevent direct updates to container nodes."""
    output = dict(annotation)
    raw = output.get("branch_effects") or {}
    cleaned: dict[str, str] = {}
    leaves = leaf_branches(state)
    for branch_id in leaves:
        effect = str(raw.get(branch_id, "neutral"))
        cleaned[branch_id] = effect if effect in EFFECT_LABELS else "neutral"
    for branch_id, branch in state.branches.items():
        if branch.status == "expanded":
            cleaned[branch_id] = "neutral"
    output["branch_effects"] = cleaned
    return output


def update_leaf_posteriors(
    state: DiagnosticState,
    annotation: Mapping[str, Any],
    *,
    gate: bool = True,
) -> None:
    """Apply one ordinal update to L2 leaves and aggregate their L1 parents."""
    leaves = leaf_branches(state)
    posteriors = ordinal_update(leaves, dict(annotation), gate=gate)
    for branch_id, posterior in posteriors.items():
        branch = state.branches[branch_id]
        branch.prior = branch.posterior
        branch.posterior = posterior
    for parent in (branch for branch in state.branches.values() if branch.level == 1):
        children = [
            state.branches[child_id]
            for child_id in parent.children
            if child_id in state.branches
            and state.branches[child_id].status != "closed_for_now"
        ]
        parent.posterior = sum(child.posterior for child in children)


def posterior_snapshot(state: DiagnosticState) -> list[dict[str, Any]]:
    rows = [
        {
            "id": branch.id,
            "label": branch.label,
            "parent": branch.parent,
            "posterior": float(branch.posterior),
            "prior": float(branch.prior),
        }
        for branch in leaf_branches(state).values()
    ]
    return sorted(rows, key=lambda row: (-row["posterior"], row["id"]))


class ComposedTALPPipeline:
    """Run evidence selection and two sequential updates on a frozen tree."""

    def __init__(
        self,
        *,
        selector: Selector,
        annotator: Annotator,
        evidence_limit: int = 2,
        discrimination_gate: bool = True,
    ) -> None:
        if evidence_limit < 1:
            raise ValueError("evidence_limit must be positive")
        self.selector = selector
        self.annotator = annotator
        self.evidence_limit = evidence_limit
        self.discrimination_gate = discrimination_gate

    def run(
        self,
        frozen_state: DiagnosticState,
        *,
        profile: str,
        vignette: str,
        facts: tuple[ObservedFact, ...],
        routed_blocks: Mapping[str, Mapping[str, Any]],
    ) -> tuple[DiagnosticState, dict[str, Any]]:
        if not facts:
            raise ValueError("no observed vignette facts")
        state = copy.deepcopy(frozen_state)
        leaves = leaf_branches(state)
        candidates = [
            {"id": branch.id, "label": branch.label, "parent": branch.parent}
            for branch in leaves.values()
        ]
        select_rules: list[Any] = []
        select_provenance: list[Any] = []
        for fact in facts:
            block = routed_blocks.get(fact.id) or {}
            select_rules.extend(_items(block.get("select")))
            select_provenance.extend(_items(block.get("provenance")))
        select_payload = {
            "vignette": vignette,
            "profile": profile,
            "candidates": candidates,
            "available_findings": [fact.to_dict() for fact in facts],
            "discriminator_rules": select_rules[:48],
            "evidence_provenance": select_provenance[:64],
        }
        selection = dict(self.selector(select_payload))
        selected_ids = clean_selected_fact_ids(
            selection, facts, limit=self.evidence_limit
        )
        if not selected_ids:
            raise ValueError("selector returned no whitelisted observed fact IDs")

        fact_by_id = {fact.id: fact for fact in facts}
        trajectory = [{
            "round": 0,
            "fact_id": None,
            "posteriors": posterior_snapshot(state),
        }]
        rounds: list[dict[str, Any]] = []
        for round_index, fact_id in enumerate(selected_ids, start=1):
            fact = fact_by_id[fact_id]
            block = dict(routed_blocks.get(fact_id) or {})
            state.timestep = round_index
            annotator_payload = {
                "state": state.project_for("EvidenceAnnotator"),
                "raw_result": {
                    "selected_fact_id": fact_id,
                    "observed_finding": fact.text,
                },
                "discrimination_profile": profile,
                "discriminator_rules": _items(block.get("direction")),
                "ruleout_rules": _items(block.get("ruleout")),
                "evidence_provenance": _items(block.get("provenance")),
            }
            annotation = clean_annotation(state, self.annotator(annotator_payload))
            update_leaf_posteriors(
                state, annotation, gate=self.discrimination_gate
            )
            snapshot = posterior_snapshot(state)
            trajectory.append({
                "round": round_index,
                "fact_id": fact_id,
                "posteriors": snapshot,
            })
            rounds.append({
                "round": round_index,
                "fact": fact.to_dict(),
                "routed_block": block,
                "annotation": annotation,
                "posteriors": snapshot,
            })
        return state, {
            "profile": profile,
            "selection": selection,
            "selected_fact_ids": selected_ids,
            "rounds": rounds,
            "posterior_trajectory": trajectory,
        }
