"""Evidence-axis breadth-first discrimination over a frozen L1 differential.

The module deliberately owns no branch creation, controller loop, action
execution, termination, or answer mapping.  A caller supplies an immutable case,
an observed-fact catalogue, frozen profile compiler blocks, and small LLM
callables.  Only selection eligibility and L1 belief scores may change.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Mapping, Sequence

from .adaptive_stopping import (
    FixedBudgetPolicy,
    StopPolicy,
    build_stop_snapshot,
    policy_config,
)
from .state import Branch, DiagnosticState

LLMCallable = Callable[[Mapping[str, Any]], Mapping[str, Any]]

FORBIDDEN_RUNTIME_KEYS = frozenset({
    "is_gold",
    "gold",
    "gold_option",
    "gold_diagnosis",
    "role",
    "favors",
    "decisive",
    "direction_target",
    "target",
})

_SPACE_RE = re.compile(r"\s+")
_CONCEPT_KEY_RE = re.compile(r"[\W_]+", re.UNICODE)


def _canonical_concept_key(value: Any) -> str:
    return _SPACE_RE.sub(
        " ", _CONCEPT_KEY_RE.sub(" ", str(value or "").strip().lower()),
    ).strip()


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "__dataclass_fields__"):
        return _jsonable(asdict(value))
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def stable_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            _jsonable(value), ensure_ascii=False, sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def assert_no_gold_leak(payload: Any, *, path: str = "payload") -> None:
    """Reject evaluation-only labels from any runtime LLM payload."""
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            normalized = str(key).strip().lower()
            if normalized in FORBIDDEN_RUNTIME_KEYS:
                raise ValueError(f"gold-leak field at {path}.{key}")
            assert_no_gold_leak(value, path=f"{path}.{key}")
    elif isinstance(payload, (list, tuple)):
        for index, value in enumerate(payload):
            assert_no_gold_leak(value, path=f"{path}[{index}]")


@dataclass(frozen=True)
class L1ObservedFact:
    id: str
    text: str
    concept: str = ""
    value_state: str = ""
    polarity: str = ""
    specimen: str = ""
    temporal_context: str = ""

    def to_dict(self) -> dict[str, str]:
        return asdict(self)

    @property
    def canonical_key(self) -> str:
        values = (
            self.concept or self.text,
            self.value_state,
            self.polarity,
            self.specimen,
            self.temporal_context,
        )
        return "|".join(_SPACE_RE.sub(" ", value.strip().lower()) for value in values)


@dataclass(frozen=True)
class PipelinePreset:
    name: str
    selector_contract: str
    allocation_contract: str
    update_contract: str
    ruleout_selector: str
    selector_abstains: bool

    def validate(self, *, track: str | None = None) -> None:
        if self.selector_contract not in {
            "p5_forced", "abstaining", "contrastive", "anti_anchor",
        }:
            raise ValueError(f"invalid selector contract: {self.selector_contract}")
        if self.allocation_contract not in {"p5_single", "sparse_ranked"}:
            raise ValueError(f"invalid allocation contract: {self.allocation_contract}")
        if self.update_contract not in {
            "metrics_only", "direct_rank", "legacy_annotator_ordinal",
        }:
            raise ValueError(f"invalid update contract: {self.update_contract}")
        if self.ruleout_selector not in {"off", "dedicated"}:
            raise ValueError(f"invalid rule-out selector: {self.ruleout_selector}")
        if self.selector_abstains != (
            self.selector_contract in {
                "abstaining", "contrastive", "anti_anchor",
            }
        ):
            raise ValueError("selector_abstains must match selector_contract")
        if track == "B" and self.update_contract == "metrics_only":
            raise ValueError("metrics_only preset cannot produce Track B ranking")
        if self.name == "p5_eval_compat" and self.update_contract != "metrics_only":
            raise ValueError("p5_eval_compat must remain metrics-only")


PRESETS: dict[str, PipelinePreset] = {
    "p5_eval_compat": PipelinePreset(
        "p5_eval_compat", "p5_forced", "p5_single", "metrics_only", "off", False,
    ),
    "p5_single_direct": PipelinePreset(
        "p5_single_direct", "p5_forced", "p5_single", "direct_rank", "off", False,
    ),
    "p5_single_abstaining": PipelinePreset(
        "p5_single_abstaining", "abstaining", "p5_single", "direct_rank", "off", True,
    ),
    "p5_contrastive_direct": PipelinePreset(
        "p5_contrastive_direct", "contrastive",
        "p5_single", "direct_rank", "off", True,
    ),
    "p5_anti_anchor_direct": PipelinePreset(
        "p5_anti_anchor_direct", "anti_anchor",
        "p5_single", "direct_rank", "off", True,
    ),
    "e1q_legacy": PipelinePreset(
        "e1q_legacy", "p5_forced", "p5_single",
        "legacy_annotator_ordinal", "off", False,
    ),
    "bfs_sparse": PipelinePreset(
        "bfs_sparse", "abstaining", "sparse_ranked", "direct_rank", "off", True,
    ),
    "bfs_sparse_dual_ro": PipelinePreset(
        "bfs_sparse_dual_ro", "abstaining", "sparse_ranked",
        "direct_rank", "dedicated", True,
    ),
    "bfs_sparse_branch_proposal": PipelinePreset(
        "bfs_sparse_branch_proposal", "abstaining", "sparse_ranked",
        "direct_rank", "off", True,
    ),
}


def clean_contrastive_selection(
    response: Mapping[str, Any],
    eligible_ids: Sequence[str],
    branch_ids: Sequence[str],
    *,
    limit: int = 2,
) -> dict[str, Any]:
    """Validate pairwise-contrast selection and collapse semantic aliases."""
    eligible = set(eligible_ids)
    branches = set(branch_ids)
    verdict = str(response.get("verdict") or "").strip().lower()
    raw_rows = response.get("ranked_facts") or []
    if verdict in {"none", "abstain", "stop"}:
        raw_rows = []
    if not isinstance(raw_rows, list):
        raw_rows = []
    selected: list[str] = []
    concept_keys: dict[str, str] = {}
    comparisons: list[dict[str, Any]] = []
    seen_concepts: set[str] = set()
    rejected: list[dict[str, str]] = []
    for raw in raw_rows:
        if not isinstance(raw, Mapping):
            rejected.append({"fact_id": "", "reason": "row_not_object"})
            continue
        fact_id = str(raw.get("fact_id") or "").strip()
        concept_key = _canonical_concept_key(raw.get("concept_key"))
        supports = [
            str(value) for value in (raw.get("supports") or ())
            if str(value) in branches
        ]
        contrasts = [
            str(value) for value in (raw.get("contrasts_with") or ())
            if str(value) in branches
        ]
        raw_effects = raw.get("candidate_effects") or {}
        effects: dict[str, int] = {}
        if isinstance(raw_effects, Mapping):
            for branch_id, value in raw_effects.items():
                try:
                    score = int(value)
                except (TypeError, ValueError):
                    continue
                if str(branch_id) in branches and -2 <= score <= 2:
                    effects[str(branch_id)] = score
        reason = ""
        if fact_id not in eligible:
            reason = "ineligible_fact"
        elif not concept_key:
            reason = "missing_concept_key"
        elif concept_key in seen_concepts:
            reason = "duplicate_concept"
        elif not supports or not contrasts:
            reason = "missing_pairwise_contrast"
        elif set(supports) & set(contrasts):
            reason = "support_contrast_conflict"
        elif set(effects) != branches:
            reason = "incomplete_effect_matrix"
        elif max(effects.values()) - min(effects.values()) < 2:
            reason = "weak_candidate_contrast"
        elif any(effects[value] <= 0 for value in supports):
            reason = "nonpositive_support"
        elif any(effects[value] >= max(effects.values()) for value in contrasts):
            reason = "invalid_contrast_target"
        if reason:
            rejected.append({"fact_id": fact_id, "reason": reason})
            continue
        selected.append(fact_id)
        concept_keys[fact_id] = concept_key
        seen_concepts.add(concept_key)
        comparisons.append({
            "fact_id": fact_id,
            "concept_key": concept_key,
            "supports": list(dict.fromkeys(supports)),
            "contrasts_with": list(dict.fromkeys(contrasts)),
            "candidate_effects": effects,
            "why": str(raw.get("why") or ""),
        })
        if len(selected) >= limit:
            break
    return {
        "verdict": "select" if selected else "none",
        "best_fact_id": selected[0] if selected else "",
        "ranked_fact_ids": selected,
        "concept_keys": concept_keys,
        "comparisons": comparisons,
        "rejected": rejected,
        "schema_valid": bool(selected) or verdict in {"none", "abstain", "stop"},
    }


def resolve_preset(name: str, *, track: str | None = None) -> PipelinePreset:
    try:
        preset = PRESETS[name.strip().lower()]
    except KeyError as exc:
        raise ValueError(f"unknown pipeline preset: {name!r}") from exc
    preset.validate(track=track)
    return preset


def _normalized(values: Mapping[str, float]) -> dict[str, float]:
    positive = {key: max(float(value), 1e-12) for key, value in values.items()}
    total = sum(positive.values())
    if total <= 0:
        return {key: 1.0 / len(positive) for key in positive} if positive else {}
    return {key: value / total for key, value in positive.items()}


def _block_items(value: Any) -> list[Any]:
    if value in (None, ""):
        return []
    if isinstance(value, (str, Mapping)):
        return [value]
    return list(value)


def _candidate_match(value: Any, branches: Mapping[str, Branch]) -> str | None:
    text = _SPACE_RE.sub(" ", str(value or "").strip().lower())
    if not text or text == "none":
        return None
    if text in {branch_id.lower() for branch_id in branches}:
        return next(branch_id for branch_id in branches if branch_id.lower() == text)
    exact = [
        branch_id for branch_id, branch in branches.items()
        if _SPACE_RE.sub(" ", branch.label.strip().lower()) == text
    ]
    return exact[0] if len(exact) == 1 else None


def clean_selected_fact_ids(
    response: Mapping[str, Any],
    eligible_ids: Sequence[str],
    *,
    limit: int = 2,
    allow_abstain: bool,
) -> list[str]:
    allowed = set(eligible_ids)
    verdict = str(response.get("verdict") or "").strip().lower()
    if allow_abstain and verdict in {"none", "abstain", "stop"}:
        return []
    raw = response.get("ranked_fact_ids") or response.get("selected_fact_ids") or []
    if isinstance(raw, str):
        raw = [raw]
    best = response.get("best_fact_id")
    values = ([best] if best else []) + list(raw)
    selected: list[str] = []
    for value in values:
        fact_id = str(value or "").strip()
        if fact_id in allowed and fact_id not in selected:
            selected.append(fact_id)
        if len(selected) >= limit:
            break
    if not selected and not allow_abstain:
        raise ValueError("forced selector returned no eligible fact IDs")
    return selected


def clean_allocation(
    response: Mapping[str, Any],
    branches: Mapping[str, Branch],
    *,
    contract: str,
    axis: str,
) -> tuple[list[str], dict[str, Any]]:
    """Return sparse canonical branch IDs and a validation audit."""
    if contract == "p5_single":
        field_name = "favored" if axis == "rule_in" else "argues_against"
        raw_value = response.get(field_name)
        if raw_value is None:
            raw_value = response.get("candidate")
        branch_id = _candidate_match(raw_value, branches)
        raw_text = str(raw_value or "").strip().lower()
        verdict = "none" if raw_text in {"", "none"} or branch_id is None else "specific"
        return ([branch_id] if branch_id else []), {
            "verdict": verdict,
            "schema_valid": raw_text in {"", "none"} or branch_id is not None,
        }

    if contract != "sparse_ranked":
        raise ValueError(f"unsupported allocation contract: {contract}")
    verdict = str(response.get("verdict") or "").strip().lower()
    raw = response.get("ranked_candidates") or []
    if isinstance(raw, str):
        raw = [raw]
    ranked: list[str] = []
    for value in raw:
        branch_id = _candidate_match(value, branches)
        if branch_id and branch_id not in ranked:
            ranked.append(branch_id)
        if len(ranked) >= 3:
            break
    valid_verdict = verdict in {"specific", "none"}
    schema_valid = valid_verdict and (
        (verdict == "none" and not ranked)
        or (verdict == "specific" and bool(ranked))
    )
    if not schema_valid:
        return [], {"verdict": "none", "schema_valid": False}
    return ranked, {"verdict": verdict, "schema_valid": True}


RANK_CREDITS = (1.0, 0.5, 0.25)


def symmetric_rank_update(
    branches: Mapping[str, Branch],
    rule_in_ranked: Sequence[str],
    rule_out_ranked: Sequence[str],
    *,
    eta: float = math.log(3.0),
    evidence_id: str = "",
) -> dict[str, Any]:
    """Apply one bounded, symmetric ordinal update to all L1 branches."""
    support = list(dict.fromkeys(rule_in_ranked[:3]))
    against = list(dict.fromkeys(rule_out_ranked[:3]))
    conflicts = sorted(set(support) & set(against))
    support = [branch_id for branch_id in support if branch_id not in conflicts]
    against = [branch_id for branch_id in against if branch_id not in conflicts]
    old = _normalized({key: branch.posterior for key, branch in branches.items()})
    if not support and not against:
        return {
            "posteriors": old,
            "deltas": {key: 0.0 for key in branches},
            "conflicts": conflicts,
            "updated": False,
        }
    deltas = {key: 0.0 for key in branches}
    for rank, branch_id in enumerate(support):
        if branch_id in deltas:
            deltas[branch_id] += eta * RANK_CREDITS[rank]
    for rank, branch_id in enumerate(against):
        if branch_id in deltas:
            deltas[branch_id] -= eta * RANK_CREDITS[rank]
    raw = {
        branch_id: old[branch_id] * math.exp(deltas[branch_id])
        for branch_id in branches
    }
    posteriors = _normalized(raw)
    for branch_id, branch in branches.items():
        branch.prior = old[branch_id]
        branch.posterior = posteriors[branch_id]
        if evidence_id and branch_id in support and evidence_id not in branch.evidence_for:
            branch.evidence_for.append(evidence_id)
        if evidence_id and branch_id in against and evidence_id not in branch.evidence_against:
            branch.evidence_against.append(evidence_id)
    return {
        "posteriors": posteriors,
        "deltas": deltas,
        "conflicts": conflicts,
        "updated": True,
    }


def l1_leaf_exemplars(
    branches: Mapping[str, Branch],
    *,
    limit_per_l1: int = 12,
) -> dict[str, list[dict[str, str]]]:
    """Expose frozen descendant labels without creating or scoring branches."""
    result: dict[str, list[dict[str, str]]] = {}
    for branch in branches.values():
        if branch.level != 1:
            continue
        queue = list(branch.children)
        visited: set[str] = set()
        rows: list[dict[str, str]] = []
        while queue and len(rows) < limit_per_l1:
            child_id = queue.pop(0)
            if child_id in visited:
                continue
            visited.add(child_id)
            child = branches.get(child_id)
            if child is None:
                continue
            if child.children:
                queue.extend(child.children)
            else:
                rows.append({"id": child.id, "label": child.label})
        result[branch.id] = rows
    return result


@dataclass
class L1EvidenceBFSState:
    case_context: str
    fact_catalog_core: tuple[L1ObservedFact, ...]
    compiler_master_blocks: dict[str, dict[str, Any]]
    branches: dict[str, Branch]
    branch_leaf_exemplars: dict[str, list[dict[str, str]]]
    selection_status_by_id: dict[str, str]
    accounted_evidence_history: list[dict[str, Any]] = field(default_factory=list)
    accounted_concept_keys: set[str] = field(default_factory=set)
    cycle_index: int = 0
    micro_round: int = 0
    posterior_trajectory: list[dict[str, Any]] = field(default_factory=list)
    selection_audit: list[dict[str, Any]] = field(default_factory=list)
    allocation_audit: list[dict[str, Any]] = field(default_factory=list)
    case_context_hash: str = ""
    fact_catalog_hash: str = ""
    compiler_master_hash: str = ""

    @classmethod
    def create(
        cls,
        frozen_state: DiagnosticState,
        *,
        case_context: str,
        facts: Sequence[L1ObservedFact],
        compiler_master_blocks: Mapping[str, Mapping[str, Any]],
        prior_mode: str,
        enforce_canonical_dedup: bool = True,
    ) -> "L1EvidenceBFSState":
        if prior_mode not in {"uniform", "branch"}:
            raise ValueError("prior_mode must be uniform or branch")
        branches = {
            branch_id: copy.deepcopy(branch)
            for branch_id, branch in frozen_state.branches.items()
            if branch.level == 1
        }
        if len(branches) < 2:
            raise ValueError("L1 Evidence-BFS requires at least two L1 branches")
        if prior_mode == "uniform":
            initial = {branch_id: 1.0 for branch_id in branches}
        else:
            initial = {
                branch_id: max(
                    branch.posterior if branch.posterior > 0 else branch.prior,
                    1e-12,
                )
                for branch_id, branch in branches.items()
            }
        initial = _normalized(initial)
        for branch_id, branch in branches.items():
            branch.prior = initial[branch_id]
            branch.posterior = initial[branch_id]
        catalog = tuple(copy.deepcopy(tuple(facts)))
        if len({fact.id for fact in catalog}) != len(catalog):
            raise ValueError("fact IDs must be unique")
        if (
            enforce_canonical_dedup
            and len({fact.canonical_key for fact in catalog}) != len(catalog)
        ):
            raise ValueError("canonical duplicate facts are not allowed")
        blocks = {
            fact_id: copy.deepcopy(dict(block))
            for fact_id, block in compiler_master_blocks.items()
        }
        state = cls(
            case_context=str(case_context),
            fact_catalog_core=catalog,
            compiler_master_blocks=blocks,
            branches=branches,
            branch_leaf_exemplars=l1_leaf_exemplars(frozen_state.branches),
            selection_status_by_id={fact.id: "eligible" for fact in catalog},
        )
        state.case_context_hash = stable_hash(state.case_context)
        state.fact_catalog_hash = stable_hash(
            [fact.to_dict() for fact in state.fact_catalog_core]
        )
        state.compiler_master_hash = stable_hash(state.compiler_master_blocks)
        state.posterior_trajectory.append(state.snapshot(fact_id=None))
        return state

    @property
    def eligible_fact_ids(self) -> list[str]:
        return [
            fact.id for fact in self.fact_catalog_core
            if self.selection_status_by_id.get(fact.id) == "eligible"
        ]

    @property
    def consumed_fact_ids(self) -> list[str]:
        """Fact IDs in actual BFS consumption order."""
        return [
            str(row["fact_id"]) for row in self.allocation_audit
            if row.get("fact_id")
        ]

    @property
    def consumed_fact_ids_catalog_order(self) -> list[str]:
        """Consumed fact set projected onto catalog order for legacy audits."""
        return [
            fact.id for fact in self.fact_catalog_core
            if self.selection_status_by_id.get(fact.id) == "consumed"
        ]

    def assert_semantic_integrity(self) -> None:
        if stable_hash(self.case_context) != self.case_context_hash:
            raise RuntimeError("case context mutated during L1 BFS")
        if stable_hash([fact.to_dict() for fact in self.fact_catalog_core]) != self.fact_catalog_hash:
            raise RuntimeError("fact catalogue mutated during L1 BFS")
        if stable_hash(self.compiler_master_blocks) != self.compiler_master_hash:
            raise RuntimeError("compiler master blocks mutated during L1 BFS")

    def snapshot(self, *, fact_id: str | None) -> dict[str, Any]:
        rows = sorted(
            (
                {"id": branch.id, "label": branch.label, "posterior": branch.posterior}
                for branch in self.branches.values()
            ),
            key=lambda row: (-float(row["posterior"]), str(row["id"])),
        )
        return {"round": self.micro_round, "fact_id": fact_id, "posteriors": rows}


class L1EvidenceBFSPipeline:
    """Sequentially select observed facts and update every frozen L1 branch."""

    def __init__(
        self,
        *,
        preset: str | PipelinePreset,
        global_selector: LLMCallable,
        rule_in_allocator: LLMCallable,
        rule_out_allocator: LLMCallable,
        ruleout_selector: LLMCallable | None = None,
        max_micro_rounds: int = 4,
        facts_per_cycle: int = 2,
        eta: float = math.log(3.0),
        enforce_canonical_dedup: bool = True,
        stop_policy: StopPolicy | None = None,
        shadow_stop_policy: bool = False,
    ) -> None:
        self.preset = resolve_preset(preset) if isinstance(preset, str) else preset
        self.preset.validate()
        if self.preset.update_contract == "legacy_annotator_ordinal":
            raise ValueError("e1q_legacy must be delegated to ComposedTALPPipeline")
        if self.preset.ruleout_selector == "dedicated" and ruleout_selector is None:
            raise ValueError("dedicated rule-out selector callable is required")
        if max_micro_rounds < 1 or facts_per_cycle not in {1, 2, 3}:
            raise ValueError("invalid L1 BFS evidence budget")
        self.global_selector = global_selector
        self.rule_in_allocator = rule_in_allocator
        self.rule_out_allocator = rule_out_allocator
        self.ruleout_selector = ruleout_selector
        self.max_micro_rounds = max_micro_rounds
        self.facts_per_cycle = facts_per_cycle
        self.eta = eta
        self.enforce_canonical_dedup = enforce_canonical_dedup
        self._stop_policy_explicit = stop_policy is not None
        self.stop_policy = stop_policy or FixedBudgetPolicy(max_micro_rounds)
        self.shadow_stop_policy = bool(shadow_stop_policy)

    def _selection_payload(
        self, state: L1EvidenceBFSState, *, ruleout_only: bool,
    ) -> dict[str, Any]:
        eligible = set(state.eligible_fact_ids)
        select_rules: list[Any] = []
        provenance: list[Any] = []
        for fact_id in eligible:
            block = state.compiler_master_blocks.get(fact_id) or {}
            select_rules.extend(_block_items(block.get("select")))
            provenance.extend(_block_items(block.get("provenance")))
        payload = {
            "case_context": state.case_context,
            "candidates": [
                {
                    "id": branch.id,
                    "label": branch.label,
                    "score": branch.posterior,
                    "leaf_exemplars": state.branch_leaf_exemplars.get(branch.id, []),
                }
                for branch in state.branches.values()
            ],
            "fact_catalog_core": [fact.to_dict() for fact in state.fact_catalog_core],
            "selection_status_by_id": dict(state.selection_status_by_id),
            "eligible_fact_ids": state.eligible_fact_ids,
            "max_selected_facts": self.facts_per_cycle,
            "accounted_evidence_history": copy.deepcopy(
                state.accounted_evidence_history
            ),
            "discriminator_rules": select_rules[:64],
            "evidence_provenance": provenance[:64],
            "selection_goal": "rule_out" if ruleout_only else "global_discrimination",
        }
        assert_no_gold_leak(payload)
        return payload

    def _allocator_payload(
        self,
        state: L1EvidenceBFSState,
        fact: L1ObservedFact,
        *,
        axis: str,
    ) -> dict[str, Any]:
        block = state.compiler_master_blocks.get(fact.id) or {}
        payload = {
            "case_context": state.case_context,
            "candidates": [
                {"id": branch.id, "label": branch.label, "score": branch.posterior}
                for branch in state.branches.values()
            ],
            "selected_fact": fact.to_dict(),
            "accounted_evidence_history": copy.deepcopy(
                state.accounted_evidence_history
            ),
            "discriminator_rules": (
                _block_items(block.get("direction")) if axis == "rule_in" else []
            ),
            "ruleout_rules": (
                _block_items(block.get("ruleout")) if axis == "rule_out" else []
            ),
            "evidence_provenance": _block_items(block.get("provenance"))[:32],
        }
        assert_no_gold_leak(payload)
        return payload

    def _challenge_payload(self, state: L1EvidenceBFSState) -> dict[str, Any]:
        ranked = sorted(
            state.branches.values(),
            key=lambda branch: (-float(branch.posterior), branch.id),
        )
        eligible = set(state.eligible_fact_ids)
        payload = {
            "case_context": state.case_context,
            "top_pair": [
                {
                    "id": branch.id,
                    "label": branch.label,
                    "score": branch.posterior,
                }
                for branch in ranked[:2]
            ],
            "eligible_fact_ids": state.eligible_fact_ids,
            "eligible_facts": [
                fact.to_dict()
                for fact in state.fact_catalog_core
                if fact.id in eligible
            ],
            "accounted_evidence_history": copy.deepcopy(
                state.accounted_evidence_history
            ),
        }
        assert_no_gold_leak(payload)
        return payload

    def run(
        self,
        frozen_state: DiagnosticState,
        *,
        case_context: str,
        facts: Sequence[L1ObservedFact],
        compiler_master_blocks: Mapping[str, Mapping[str, Any]],
        prior_mode: str = "branch",
    ) -> tuple[DiagnosticState, dict[str, Any]]:
        state = L1EvidenceBFSState.create(
            frozen_state,
            case_context=case_context,
            facts=facts,
            compiler_master_blocks=compiler_master_blocks,
            prior_mode=prior_mode,
            enforce_canonical_dedup=self.enforce_canonical_dedup,
        )
        fact_by_id = {fact.id: fact for fact in state.fact_catalog_core}
        stop_reason = "budget_exhausted"
        stop_snapshots: list[dict[str, Any]] = []
        stop_decisions: list[dict[str, Any]] = []
        initial_order = sorted(
            state.branches.values(),
            key=lambda branch: (-float(branch.posterior), branch.id),
        )
        previous_top1_id = initial_order[0].id if initial_order else ""
        top1_stable_cycles = 0
        empty_queue_streak = 0
        while state.micro_round < self.max_micro_rounds and state.eligible_fact_ids:
            state.assert_semantic_integrity()
            state.cycle_index += 1
            cycle_start_round = state.micro_round
            cycle_start_scores = {
                key: branch.posterior for key, branch in state.branches.items()
            }
            global_payload = self._selection_payload(state, ruleout_only=False)
            global_raw = dict(self.global_selector(global_payload))
            global_ids = clean_selected_fact_ids(
                global_raw,
                state.eligible_fact_ids,
                limit=self.facts_per_cycle,
                allow_abstain=self.preset.selector_abstains,
            )
            global_concepts = {
                str(fact_id): _canonical_concept_key(concept)
                for fact_id, concept in (
                    global_raw.get("concept_keys") or {}
                ).items()
                if str(fact_id) in global_ids and str(concept).strip()
            }
            semantic_rejected: list[dict[str, str]] = []
            if self.preset.selector_contract in {"contrastive", "anti_anchor"}:
                filtered_ids: list[str] = []
                cycle_concepts: set[str] = set()
                for fact_id in global_ids:
                    concept_key = global_concepts.get(fact_id, "")
                    if (
                        not concept_key
                        or concept_key in state.accounted_concept_keys
                        or concept_key in cycle_concepts
                    ):
                        semantic_rejected.append({
                            "fact_id": fact_id,
                            "reason": (
                                "missing_concept_key" if not concept_key
                                else "semantic_duplicate"
                            ),
                        })
                        continue
                    filtered_ids.append(fact_id)
                    cycle_concepts.add(concept_key)
                global_ids = filtered_ids
            ro_raw: dict[str, Any] | None = None
            ro_ids: list[str] = []
            if self.preset.ruleout_selector == "dedicated":
                ro_payload = self._selection_payload(state, ruleout_only=True)
                ro_raw = dict(self.ruleout_selector(ro_payload))  # type: ignore[misc]
                ro_ids = clean_selected_fact_ids(
                    ro_raw,
                    state.eligible_fact_ids,
                    limit=self.facts_per_cycle,
                    allow_abstain=True,
                )
            queue: list[str] = []
            if global_ids:
                queue.append(global_ids[0])
            if self.facts_per_cycle > 1:
                ro_first = next((item for item in ro_ids if item not in queue), None)
                global_second = next(
                    (item for item in global_ids[1:] if item not in queue), None
                )
                if self.facts_per_cycle == 2:
                    chosen = ro_first if ro_first is not None else global_second
                    if chosen is not None:
                        queue.append(chosen)
                else:
                    if global_second is not None:
                        queue.append(global_second)
                    if ro_first is not None and ro_first not in queue:
                        queue.append(ro_first)
            if not queue and ro_ids:
                queue.extend(ro_ids[: self.facts_per_cycle])
            state.selection_audit.append({
                "cycle": state.cycle_index,
                "global": global_raw,
                "global_ids": global_ids,
                "ruleout": ro_raw,
                "ruleout_ids": ro_ids,
                "queue": list(queue),
                "semantic_rejected": semantic_rejected,
                "displaced_global_ids": [
                    item for item in global_ids if item not in queue
                ],
            })
            if not queue:
                if not self._stop_policy_explicit:
                    stop_reason = "selector_abstained"
                    break
                empty_queue_streak += 1
                snapshot = build_stop_snapshot(
                    cycle_index=state.cycle_index,
                    micro_round=state.micro_round,
                    queue_length=0,
                    eligible_count=len(state.eligible_fact_ids),
                    before_scores=cycle_start_scores,
                    after_scores=cycle_start_scores,
                    previous_top1_id=previous_top1_id,
                    previous_stable_cycles=top1_stable_cycles,
                    effective_updates=0,
                    canonical_novel_count=0,
                    compiler_hit_count=0,
                    provenance_hit_count=0,
                    empty_queue_streak=empty_queue_streak,
                )
                decision = self.stop_policy.decide(
                    snapshot,
                    context={
                        "eligible_fact_ids": state.eligible_fact_ids,
                        "advisor_payload": self._challenge_payload(state),
                    },
                    shadow=self.shadow_stop_policy,
                )
                stop_snapshots.append(snapshot.to_dict())
                stop_decisions.append(decision.to_dict())
                previous_top1_id = snapshot.top1_id
                top1_stable_cycles = snapshot.top1_stable_cycles
                state.selection_audit[-1]["actual_queue_length"] = 0
                if (
                    not self.shadow_stop_policy and decision.action == "stop"
                ) or empty_queue_streak >= 2:
                    stop_reason = decision.reason
                    break
                continue
            empty_queue_streak = 0

            for fact_id in queue:
                if state.micro_round >= self.max_micro_rounds:
                    break
                if state.selection_status_by_id.get(fact_id) != "eligible":
                    continue
                state.assert_semantic_integrity()
                fact = fact_by_id[fact_id]
                rule_in_raw = dict(self.rule_in_allocator(
                    self._allocator_payload(state, fact, axis="rule_in")
                ))
                rule_out_raw = dict(self.rule_out_allocator(
                    self._allocator_payload(state, fact, axis="rule_out")
                ))
                rule_in, rule_in_audit = clean_allocation(
                    rule_in_raw,
                    state.branches,
                    contract=self.preset.allocation_contract,
                    axis="rule_in",
                )
                rule_out, rule_out_audit = clean_allocation(
                    rule_out_raw,
                    state.branches,
                    contract=self.preset.allocation_contract,
                    axis="rule_out",
                )
                state.micro_round += 1
                if self.preset.update_contract == "direct_rank":
                    update = symmetric_rank_update(
                        state.branches,
                        rule_in,
                        rule_out,
                        eta=self.eta,
                        evidence_id=fact_id,
                    )
                else:
                    update = {
                        "posteriors": {
                            key: branch.posterior
                            for key, branch in state.branches.items()
                        },
                        "deltas": {key: 0.0 for key in state.branches},
                        "conflicts": sorted(set(rule_in) & set(rule_out)),
                        "updated": False,
                    }
                state.selection_status_by_id[fact_id] = "consumed"
                concept_key = (
                    global_concepts.get(fact_id, "")
                    if self.preset.selector_contract in {
                        "contrastive", "anti_anchor",
                    }
                    else fact.canonical_key
                )
                if concept_key:
                    state.accounted_concept_keys.add(concept_key)
                history = {
                    "round": state.micro_round,
                    "fact_id": fact_id,
                    "concept_key": concept_key,
                    "rule_in_ranked": rule_in,
                    "rule_out_ranked": rule_out,
                    "rule_in_verdict": rule_in_audit["verdict"],
                    "rule_out_verdict": rule_out_audit["verdict"],
                    "updated": update["updated"],
                }
                state.accounted_evidence_history.append(history)
                state.allocation_audit.append({
                    **history,
                    "fact": fact.to_dict(),
                    "rule_in_raw": rule_in_raw,
                    "rule_out_raw": rule_out_raw,
                    "rule_in_schema_valid": rule_in_audit["schema_valid"],
                    "rule_out_schema_valid": rule_out_audit["schema_valid"],
                    "update": update,
                })
                state.posterior_trajectory.append(state.snapshot(fact_id=fact_id))
                state.assert_semantic_integrity()

            cycle_rows = state.allocation_audit[cycle_start_round:]
            processed_ids = [str(row["fact_id"]) for row in cycle_rows]
            actual_queue_length = state.micro_round - cycle_start_round
            state.selection_audit[-1]["actual_queue_length"] = actual_queue_length
            effective_updates = sum(
                bool(row.get("update", {}).get("updated"))
                and bool(row.get("rule_in_schema_valid"))
                and bool(row.get("rule_out_schema_valid"))
                and bool(
                    row.get("rule_in_ranked") or row.get("rule_out_ranked")
                )
                and not row.get("update", {}).get("conflicts")
                for row in cycle_rows
            )
            compiler_hit_count = sum(
                bool(
                    (state.compiler_master_blocks.get(fact_id) or {}).get("select")
                    or (state.compiler_master_blocks.get(fact_id) or {}).get("direction")
                    or (state.compiler_master_blocks.get(fact_id) or {}).get("ruleout")
                )
                for fact_id in processed_ids
            )
            provenance_hit_count = sum(
                len(_block_items(
                    (state.compiler_master_blocks.get(fact_id) or {}).get(
                        "provenance"
                    )
                ))
                for fact_id in processed_ids
            )
            cycle_end_scores = {
                key: branch.posterior for key, branch in state.branches.items()
            }
            cycle_leader_id = min(
                cycle_end_scores,
                key=lambda key: (-float(cycle_end_scores[key]), str(key)),
            )
            leader_support_count = sum(
                cycle_leader_id in (row.get("rule_in_ranked") or ())
                for row in cycle_rows
            )
            leader_against_count = sum(
                cycle_leader_id in (row.get("rule_out_ranked") or ())
                for row in cycle_rows
            )
            snapshot = build_stop_snapshot(
                cycle_index=state.cycle_index,
                micro_round=state.micro_round,
                queue_length=actual_queue_length,
                eligible_count=len(state.eligible_fact_ids),
                before_scores=cycle_start_scores,
                after_scores=cycle_end_scores,
                previous_top1_id=previous_top1_id,
                previous_stable_cycles=top1_stable_cycles,
                effective_updates=effective_updates,
                canonical_novel_count=actual_queue_length,
                compiler_hit_count=compiler_hit_count,
                provenance_hit_count=provenance_hit_count,
                leader_support_count=leader_support_count,
                leader_against_count=leader_against_count,
            )
            decision = self.stop_policy.decide(
                snapshot,
                context={
                    "eligible_fact_ids": state.eligible_fact_ids,
                    "advisor_payload": self._challenge_payload(state),
                },
                shadow=self.shadow_stop_policy,
            )
            stop_snapshots.append(snapshot.to_dict())
            stop_decisions.append(decision.to_dict())
            previous_top1_id = snapshot.top1_id
            top1_stable_cycles = snapshot.top1_stable_cycles
            if not self.shadow_stop_policy and decision.action == "stop":
                stop_reason = decision.reason
                if (
                    not self._stop_policy_explicit
                    and stop_reason == "fixed_budget_reached"
                ):
                    stop_reason = "budget_exhausted"
                break

        output_state = copy.deepcopy(frozen_state)
        for branch_id, branch in state.branches.items():
            output_state.branches[branch_id] = copy.deepcopy(branch)
        output_state.timestep = state.micro_round
        trace = {
            "schema_version": 1,
            "preset": self.preset.name,
            "resolved_config": asdict(self.preset),
            "prior_mode": prior_mode,
            "max_micro_rounds": self.max_micro_rounds,
            "facts_per_cycle": self.facts_per_cycle,
            "enforce_canonical_dedup": self.enforce_canonical_dedup,
            "stop_policy": policy_config(self.stop_policy),
            "shadow_stop_policy": self.shadow_stop_policy,
            "stop_reason": stop_reason,
            "case_context_hash": state.case_context_hash,
            "fact_catalog_hash": state.fact_catalog_hash,
            "compiler_master_hash": state.compiler_master_hash,
            "selection_status_by_id": dict(state.selection_status_by_id),
            "selected_fact_ids": state.consumed_fact_ids,
            "consumption_order_fact_ids": state.consumed_fact_ids,
            "consumed_fact_ids_catalog_order": (
                state.consumed_fact_ids_catalog_order
            ),
            "accounted_evidence_history": state.accounted_evidence_history,
            "accounted_concept_keys": sorted(state.accounted_concept_keys),
            "selection_cycles": state.selection_audit,
            "rounds": state.allocation_audit,
            "posterior_trajectory": state.posterior_trajectory,
            "stop_snapshots": stop_snapshots,
            "stop_decisions": stop_decisions,
            "answer_mapper_called": False,
        }
        return output_state, trace
