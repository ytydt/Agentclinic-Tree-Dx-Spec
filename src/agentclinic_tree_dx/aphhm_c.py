"""APHHM-C: compact, concept-consistent APHHM.

Design: ``APHHM_COMPACT_REDESIGN.md``.

Fixed diagnostic calls (4):
  C1  observed fact ledger
  C2  axis contract (families + fact coverage + recall placement)
  C3  batched branch-conditioned unique-concept generation
  C4  global ``fact x concept`` relative-evidence matrix

Optional slots (>=5 calls only when gated):
  C3b gap/complement generation  — axis coverage obligation exists
  C4b second matrix chunk        — fact rows split, never candidate split
  C5  top-pair disputed-cell adjudicator

Everything after C4 is deterministic: P3/P4/P5 gates, the ordinal belief score
and the tie-break all read the same append-only ledger.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Optional

from agentclinic_tree_dx.backbone import _read_prompt
from agentclinic_tree_dx import near_dedup as nd

MODES = (
    "c4",
    "c4_noaxisbias",
    "c4_nogap",
    "c4_noverifier",
    "c4_selector",
    "c4_selector_wide",
    "c4_selector_rich",
    "c4_selector_clean",
    "c4_selector_candev",
    "c4_selector_candev_nomatrix",
    "multistance",
    "multistance_split",
    "legacy_champion",
)
SELECTOR_MODES = (
    "c4_selector",
    "c4_selector_wide",
    "c4_selector_rich",
    "c4_selector_clean",
    "c4_selector_candev",
    "c4_selector_candev_nomatrix",
    "multistance",
    "multistance_split",
)
# v1 hard-codes a floor of 8 concepts; v2 sizes the differential to the budget
# so that unique_budget can be swept without the prompt fighting it.
CONCEPT_CONTRACTS = {
    "v1": "aphhm_c_batched_concepts.txt",
    "v2": "aphhm_c_batched_concepts_v2.txt",
    "noaxis": "aphhm_c_batched_concepts_noaxis.txt",
    "evid": "aphhm_c_batched_concepts_evid.txt",
    "evid_wide": "aphhm_c_batched_concepts_evid_wide.txt",
    "evid_commit": "aphhm_c_batched_concepts_commit.txt",
}
# conditioned  = design default: C3 sees families, scopes and per-family quotas
# unconditioned= C2 still runs (guard/gap intact) but C3 is not told about it
# off          = C2 is not called at all; the axis slot is removed from the budget
AXIS_MODES = ("conditioned", "unconditioned", "off")
# Recall comes from stance diversity, not from budget: four arms that all condition
# on the same C1 ledger pool to 0.53/0.45 recall, while three genuinely different
# stances reach 0.59/0.50 at ~10 candidates, against the original APHHM's
# 0.555/0.530 at ~31 nodes. Each stance is one call.
STANCES = {
    "commit": "aphhm_c_batched_concepts_commit.txt",
    "coverage": "aphhm_c_stance_coverage.txt",
    "mechanism": "aphhm_c_stance_mechanism.txt",
}

# Frozen ordinal effect map (design 4.1).
EFFECT_VALUE: dict[tuple[str, str], int] = {
    ("rule_in", "strong"): 3,
    ("rule_in", "moderate"): 2,
    ("rule_in", "weak"): 1,
    ("rule_out", "weak"): -1,
    ("rule_out", "moderate"): -2,
    ("rule_out", "strong"): -3,
}
RELIABILITY_WEIGHT = {"high": 1.0, "medium": 0.7, "low": 0.4}
SPECIFICITY_RANK = {"high": 2, "medium": 1, "low": 0}
GROUP_CLIP = 3
# Axis bias must never exceed one moderate evidence step (design 4.1).
AXIS_BIAS_CAP = 2.0

_DIRECTIONS = ("rule_in", "rule_out", "neutral", "unknown")
_STRENGTHS = ("strong", "moderate", "weak", "none")


def _norm(s: Any) -> str:
    s = str(s or "").strip().lower()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[^\w\s\-/\+]", "", s)
    return s


def _as_list(x: Any) -> list[Any]:
    if x is None:
        return []
    if isinstance(x, list):
        return x
    if isinstance(x, tuple):
        return list(x)
    return [x]


def _pick(value: Any, allowed: Iterable[str], default: str) -> str:
    v = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    allowed = tuple(allowed)
    return v if v in allowed else default


@dataclass
class ObservedFact:
    """C1 row. ``raw_span`` is verbatim vignette text; never a paraphrase."""

    fact_id: str
    raw_span: str
    polarity: str = "present"
    temporality: str = "current"
    epistemic_status: str = "observed"
    modality: str = "history"
    specificity: str = "medium"
    reliability: str = "medium"
    correlation_group: str = ""

    @property
    def is_provisional(self) -> bool:
        return self.epistemic_status == "provisional_diagnosis"

    @property
    def group_key(self) -> str:
        return self.correlation_group or self.fact_id

    def as_dict(self) -> dict[str, Any]:
        return {
            "fact_id": self.fact_id,
            "raw_span": self.raw_span,
            "polarity": self.polarity,
            "temporality": self.temporality,
            "epistemic_status": self.epistemic_status,
            "modality": self.modality,
            "specificity": self.specificity,
            "reliability": self.reliability,
            "correlation_group": self.correlation_group,
        }


@dataclass
class Family:
    family_id: str
    label: str
    scope_in: list[str] = field(default_factory=list)
    scope_out: list[str] = field(default_factory=list)
    initial_belief_rank: int = 99

    def as_dict(self) -> dict[str, Any]:
        return {
            "family_id": self.family_id,
            "label": self.label,
            "scope_in": list(self.scope_in),
            "scope_out": list(self.scope_out),
            "initial_belief_rank": self.initial_belief_rank,
        }


@dataclass
class AxisContract:
    axis: str = ""
    families: list[Family] = field(default_factory=list)
    fact_coverage: dict[str, list[str]] = field(default_factory=dict)
    coverage_kind: dict[str, str] = field(default_factory=dict)
    recall_placement: dict[str, str] = field(default_factory=dict)
    provisional_anchor_used_as_evidence: bool = False

    def belief_of(self, family_id: str) -> float:
        """Rank 1 -> 1.0, decaying; unknown family -> 0."""
        for f in self.families:
            if f.family_id == family_id:
                rank = max(1, int(f.initial_belief_rank or 99))
                return 1.0 / rank
        return 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "axis": self.axis,
            "families": [f.as_dict() for f in self.families],
            "fact_coverage": {k: list(v) for k, v in self.fact_coverage.items()},
            "coverage_kind": dict(self.coverage_kind),
            "recall_placement": dict(self.recall_placement),
            "provisional_anchor_used_as_evidence": self.provisional_anchor_used_as_evidence,
        }


@dataclass
class AxisGuardReport:
    uncovered_high_specific_fact_ids: list[str] = field(default_factory=list)
    unassigned_high_quality_recall_ids: list[str] = field(default_factory=list)
    multi_primary_recall_ids: list[str] = field(default_factory=list)
    granularity_violations: list[str] = field(default_factory=list)
    provisional_anchor_clone: bool = False

    @property
    def requires_gap_lane(self) -> bool:
        return bool(
            self.uncovered_high_specific_fact_ids
            or self.unassigned_high_quality_recall_ids
            or self.granularity_violations
            or self.provisional_anchor_clone
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "uncovered_high_specific_fact_ids": list(self.uncovered_high_specific_fact_ids),
            "unassigned_high_quality_recall_ids": list(self.unassigned_high_quality_recall_ids),
            "multi_primary_recall_ids": list(self.multi_primary_recall_ids),
            "granularity_violations": list(self.granularity_violations),
            "provisional_anchor_clone": self.provisional_anchor_clone,
            "requires_gap_lane": self.requires_gap_lane,
        }


@dataclass
class ConceptNode:
    concept_id: str
    preferred_label: str
    aliases: list[str] = field(default_factory=list)
    primary_parent: str = ""
    secondary_parent_refs: list[str] = field(default_factory=list)
    support_fact_ids: list[str] = field(default_factory=list)
    support_spans: list[str] = field(default_factory=list)
    contradict_spans: list[str] = field(default_factory=list)
    stances: list[str] = field(default_factory=list)
    recall_provenance: list[str] = field(default_factory=list)
    origin: str = "c3"
    gap_bound_fact_ids: list[str] = field(default_factory=list)
    status: str = "active"
    status_reason: str = ""
    score: float = 0.0
    score_components: dict[str, Any] = field(default_factory=dict)
    narrower_than: list[str] = field(default_factory=list)
    broader_than: list[str] = field(default_factory=list)
    related_to: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "concept_id": self.concept_id,
            "preferred_label": self.preferred_label,
            "aliases": list(self.aliases),
            "primary_parent": self.primary_parent,
            "secondary_parent_refs": list(self.secondary_parent_refs),
            "support_fact_ids": list(self.support_fact_ids),
            "support_spans": list(self.support_spans),
            "contradict_spans": list(self.contradict_spans),
            "stances": list(self.stances),
            "recall_provenance": list(self.recall_provenance),
            "origin": self.origin,
            "gap_bound_fact_ids": list(self.gap_bound_fact_ids),
            "status": self.status,
            "status_reason": self.status_reason,
            "score": self.score,
            "score_components": dict(self.score_components),
            "narrower_than": list(self.narrower_than),
            "broader_than": list(self.broader_than),
            "related_to": list(self.related_to),
        }


class ConceptRegistry:
    """Global concept identity (design 2.2) + append-only lifecycle (design 5)."""

    ACTIVE_STATES = ("active", "protected")

    def __init__(self, resolver: Any = None) -> None:
        self.resolver = resolver
        self.concepts: dict[str, ConceptNode] = {}
        self.events: list[dict[str, Any]] = []
        self._alias_index: dict[str, str] = {}
        self._next_id = 1
        self._next_event = 1
        self.merge_audit: list[dict[str, Any]] = []

    # --- identity -----------------------------------------------------
    def _same_as(self, a: str, b: str) -> bool:
        """Only confirmed equivalence merges. Substring is NOT same_as: it is
        a broader/narrower relation and must stay a separate concept."""
        if not a or not b:
            return False
        na, nb = _norm(a), _norm(b)
        if na == nb:
            return True
        if self.resolver is not None:
            try:
                fn = getattr(self.resolver, "resolve", None)
                if callable(fn):
                    ra, rb = str(fn(a) or a), str(fn(b) or b)
                    if _norm(ra) == _norm(rb) and _norm(ra):
                        return True
            except Exception:
                pass
        return False

    def _relation(self, a: str, b: str) -> str:
        """Directed relation of ``a`` w.r.t. ``b`` when they are not same_as."""
        na, nb = _norm(a), _norm(b)
        if not na or not nb or na == nb:
            return ""
        aw, bw = set(na.split()), set(nb.split())
        if len(na) >= 6 and len(nb) >= 6:
            if nb in na or bw < aw:
                return "narrower_than"
            if na in nb or aw < bw:
                return "broader_than"
        return ""

    def _find_same_as(self, label: str) -> Optional[str]:
        key = _norm(label)
        if key in self._alias_index:
            return self._alias_index[key]
        for cid, c in self.concepts.items():
            if self._same_as(label, c.preferred_label):
                return cid
            if any(self._same_as(label, al) for al in c.aliases):
                return cid
        return None

    def _log(self, op: str, concept_id: str, **kw: Any) -> str:
        eid = f"EV{self._next_event:03d}"
        self._next_event += 1
        self.events.append({"event_id": eid, "op": op, "concept_id": concept_id, **kw})
        return eid

    def add(
        self,
        *,
        label: str,
        primary_parent: str = "",
        secondary_parents: Optional[list[str]] = None,
        support_fact_ids: Optional[list[str]] = None,
        support_spans: Optional[list[str]] = None,
        contradict_spans: Optional[list[str]] = None,
        stance: str = "",
        aliases: Optional[list[str]] = None,
        recall_provenance: Optional[list[str]] = None,
        origin: str = "c3",
        gap_bound_fact_ids: Optional[list[str]] = None,
    ) -> str:
        label = str(label or "").strip()
        if not label:
            return ""
        secondary_parents = list(secondary_parents or [])
        support_fact_ids = list(support_fact_ids or [])
        support_spans = list(support_spans or [])
        contradict_spans = list(contradict_spans or [])
        aliases = [str(a).strip() for a in (aliases or []) if str(a).strip()]

        existing = self._find_same_as(label)
        if existing is None:
            for al in aliases:
                existing = self._find_same_as(al)
                if existing:
                    break

        if existing:
            c = self.concepts[existing]
            if _norm(label) != _norm(c.preferred_label) and label not in c.aliases:
                c.aliases.append(label)
            for al in aliases:
                if _norm(al) != _norm(c.preferred_label) and al not in c.aliases:
                    c.aliases.append(al)
            for p in ([primary_parent] if primary_parent else []) + secondary_parents:
                if p and p != c.primary_parent and p not in c.secondary_parent_refs:
                    c.secondary_parent_refs.append(p)
            for f in support_fact_ids:
                if f not in c.support_fact_ids:
                    c.support_fact_ids.append(f)
            for sp in support_spans:
                if sp not in c.support_spans:
                    c.support_spans.append(sp)
            for sp in contradict_spans:
                if sp not in c.contradict_spans:
                    c.contradict_spans.append(sp)
            if stance and stance not in c.stances:
                c.stances.append(stance)
            for r in recall_provenance or []:
                if r not in c.recall_provenance:
                    c.recall_provenance.append(r)
            for f in gap_bound_fact_ids or []:
                if f not in c.gap_bound_fact_ids:
                    c.gap_bound_fact_ids.append(f)
            self._alias_index[_norm(label)] = existing
            self.merge_audit.append(
                {"kind": "same_as", "into": existing, "label": label, "origin": origin}
            )
            self._log("merge_alias", existing, label=label, origin=origin)
            return existing

        cid = f"C{self._next_id:02d}"
        self._next_id += 1
        node = ConceptNode(
            concept_id=cid,
            preferred_label=label,
            aliases=aliases,
            primary_parent=primary_parent,
            secondary_parent_refs=[p for p in secondary_parents if p and p != primary_parent],
            support_fact_ids=support_fact_ids,
            support_spans=support_spans,
            contradict_spans=contradict_spans,
            stances=[stance] if stance else [],
            recall_provenance=list(recall_provenance or []),
            origin=origin,
            gap_bound_fact_ids=list(gap_bound_fact_ids or []),
        )
        # broad/subtype only creates relations, never a silent fold (design 2.2)
        for other in self.concepts.values():
            rel = self._relation(label, other.preferred_label)
            if rel == "narrower_than":
                node.narrower_than.append(other.concept_id)
                other.broader_than.append(cid)
                self.merge_audit.append(
                    {"kind": "narrower_than", "child": cid, "parent": other.concept_id}
                )
            elif rel == "broader_than":
                node.broader_than.append(other.concept_id)
                other.narrower_than.append(cid)
                self.merge_audit.append(
                    {"kind": "broader_than", "parent": cid, "child": other.concept_id}
                )
        self.concepts[cid] = node
        self._alias_index[_norm(label)] = cid
        for al in aliases:
            self._alias_index.setdefault(_norm(al), cid)
        self._log("add", cid, label=label, origin=origin)
        return cid

    def set_status(
        self, concept_id: str, status: str, reason: str, *, score_before: float = 0.0
    ) -> None:
        c = self.concepts.get(concept_id)
        if c is None or c.status == status:
            return
        prev = c.status
        c.status = status
        c.status_reason = reason
        self._log(
            "status",
            concept_id,
            previous_status=prev,
            new_status=status,
            reason=reason,
            score_before=score_before,
            score_after=c.score,
        )

    def active(self) -> list[ConceptNode]:
        return [c for c in self.concepts.values() if c.status in self.ACTIVE_STATES]

    def resolved_duplicate_count(self) -> int:
        """Same_as-resolvable labels occupying two concept slots. Must be 0."""
        dups = 0
        seen: list[ConceptNode] = []
        for c in self.concepts.values():
            if any(self._same_as(c.preferred_label, s.preferred_label) for s in seen):
                dups += 1
            seen.append(c)
        return dups

    def unexplained_events(self) -> int:
        """Concepts whose status left ``active`` without a logged event."""
        logged = {
            e["concept_id"] for e in self.events if e.get("op") == "status"
        }
        return sum(
            1
            for c in self.concepts.values()
            if c.status != "active" and c.concept_id not in logged
        )


@dataclass
class EvidenceCell:
    fact_id: str
    concept_id: str
    direction: str
    strength: str
    admitted: bool = False
    veto_reason: str = ""
    value: int = 0
    source: str = "c4"

    def as_dict(self) -> dict[str, Any]:
        return {
            "fact_id": self.fact_id,
            "concept_id": self.concept_id,
            "direction": self.direction,
            "strength": self.strength,
            "admitted": self.admitted,
            "veto_reason": self.veto_reason,
            "value": self.value,
            "source": self.source,
        }


class EvidenceLedger:
    """Single authoritative source for cells, gates, scores and rank."""

    def __init__(self, facts: list[ObservedFact], concepts: list[ConceptNode]) -> None:
        self.facts = {f.fact_id: f for f in facts}
        self.concept_ids = [c.concept_id for c in concepts]
        self.cells: dict[tuple[str, str], EvidenceCell] = {}
        self.rationales: dict[str, str] = {}
        self.gate_log: list[dict[str, Any]] = []
        for f in facts:
            for c in concepts:
                self.cells[(f.fact_id, c.concept_id)] = EvidenceCell(
                    fact_id=f.fact_id,
                    concept_id=c.concept_id,
                    direction="unknown",
                    strength="none",
                    source="default",
                )

    # --- ingest -------------------------------------------------------
    def ingest(self, effects: Mapping[str, Any], *, source: str = "c4") -> int:
        filled = 0
        for fid, row in (effects or {}).items():
            fid = str(fid).strip()
            if fid not in self.facts or not isinstance(row, Mapping):
                continue
            for cid, cell in row.items():
                cid = str(cid).strip()
                key = (fid, cid)
                if key not in self.cells:
                    continue
                if isinstance(cell, Mapping):
                    direction = _pick(cell.get("direction"), _DIRECTIONS, "unknown")
                    strength = _pick(cell.get("strength"), _STRENGTHS, "none")
                else:
                    # compact form: "rule_in:strong" | "neutral"
                    head, _, tail = str(cell or "").partition(":")
                    direction = _pick(head, _DIRECTIONS, "unknown")
                    strength = _pick(tail, _STRENGTHS, "moderate")
                if direction in ("neutral", "unknown"):
                    strength = "none"
                elif strength == "none":
                    strength = "weak"
                target = self.cells[key]
                target.direction = direction
                target.strength = strength
                target.source = source
                filled += 1
        return filled

    def p3_completeness(self) -> float:
        if not self.cells:
            return 0.0
        got = sum(1 for c in self.cells.values() if c.source != "default")
        return got / len(self.cells)

    # --- gates --------------------------------------------------------
    def apply_gates(self, registry: ConceptRegistry, *, shared_ratio: float = 0.7) -> None:
        """P4 admission + P5 offline vetoes. No LLM call here (design 2.5)."""
        n_concepts = max(1, len(self.concept_ids))
        for fid, fact in self.facts.items():
            row = [self.cells[(fid, cid)] for cid in self.concept_ids]
            non_neutral = [c for c in row if c.direction in ("rule_in", "rule_out")]

            # P5-b takes precedence: a provisional label in the chart is not an
            # observed fact, so it never even reaches the discrimination tests.
            if fact.is_provisional:
                for cell in row:
                    cell.admitted = False
                    cell.value = 0
                    if cell.direction in ("rule_in", "rule_out"):
                        cell.veto_reason = "p5_provisional_anchor"
                self.gate_log.append(
                    {
                        "fact_id": fid,
                        "shared_phenotype": False,
                        "paired": False,
                        "provisional": True,
                        "n_admitted": 0,
                    }
                )
                continue

            # P5-a: a finding pointing the same way at most candidates is a
            # shared phenotype and cannot discriminate.
            shared = False
            for direction in ("rule_in", "rule_out"):
                same = [c for c in row if c.direction == direction]
                if len(same) >= max(2, int(shared_ratio * n_concepts)):
                    shared = True
                    for c in same:
                        c.veto_reason = "p5_shared_phenotype"
            # paired evidence: the fact separates candidates
            paired = len(non_neutral) >= 1 and len(non_neutral) < n_concepts and not shared

            for cell in row:
                if cell.direction in ("neutral", "unknown"):
                    cell.admitted = False
                    cell.value = 0
                    continue
                if cell.veto_reason == "p5_shared_phenotype":
                    cell.admitted = False
                    cell.value = 0
                    continue
                # P4: paired evidence OR high-specificity claim OR reliable LR
                high_spec = fact.specificity == "high"
                reliable_lr = fact.reliability == "high" and cell.strength == "strong"
                if not (paired or high_spec or reliable_lr):
                    cell.admitted = False
                    cell.value = 0
                    cell.veto_reason = cell.veto_reason or "p4_not_admissible"
                    continue
                cell.admitted = True
                cell.value = EFFECT_VALUE.get((cell.direction, cell.strength), 0)

            self.gate_log.append(
                {
                    "fact_id": fid,
                    "shared_phenotype": shared,
                    "paired": paired,
                    "provisional": fact.is_provisional,
                    "n_admitted": sum(1 for c in row if c.admitted),
                }
            )

        # P5-c: child-to-parent scope error. A finding that rules IN a specific
        # subtype must not simultaneously rule OUT its broader parent.
        for concept in registry.concepts.values():
            for parent_id in concept.narrower_than:
                for fid in self.facts:
                    child_cell = self.cells.get((fid, concept.concept_id))
                    parent_cell = self.cells.get((fid, parent_id))
                    if child_cell is None or parent_cell is None:
                        continue
                    if (
                        child_cell.direction == "rule_in"
                        and parent_cell.direction == "rule_out"
                        and parent_cell.admitted
                    ):
                        parent_cell.admitted = False
                        parent_cell.value = 0
                        parent_cell.veto_reason = "p5_scope_error_child_to_parent"

    # --- score --------------------------------------------------------
    def score_concept(self, concept: ConceptNode, axis_bias: float) -> tuple[float, dict]:
        groups: dict[str, list[EvidenceCell]] = {}
        for fid, fact in self.facts.items():
            cell = self.cells.get((fid, concept.concept_id))
            if cell is None or not cell.admitted:
                continue
            groups.setdefault(fact.group_key, []).append(cell)
        total = 0.0
        per_group = {}
        for gkey, cells in groups.items():
            raw = sum(c.value for c in cells)
            clipped = max(-GROUP_CLIP, min(GROUP_CLIP, raw))
            rel = max(
                RELIABILITY_WEIGHT.get(self.facts[c.fact_id].reliability, 0.7)
                for c in cells
            )
            total += rel * clipped
            per_group[gkey] = {"raw": raw, "clipped": clipped, "reliability": rel}
        components = {
            "evidence": total,
            "axis_bias": axis_bias,
            "groups": per_group,
            "n_admitted": sum(len(v) for v in groups.values()),
        }
        return total + axis_bias, components

    def admitted_cells(self, concept_id: str) -> list[EvidenceCell]:
        return [
            c
            for (fid, cid), c in self.cells.items()
            if cid == concept_id and c.admitted
        ]

    def as_dict(self) -> dict[str, Any]:
        return {
            "cells": [c.as_dict() for c in self.cells.values() if c.source != "default"],
            "rationales": dict(self.rationales),
            "gate_log": list(self.gate_log),
            "p3_completeness": self.p3_completeness(),
        }


@dataclass
class AphhmCResult:
    case_id: str
    champion: str
    ordered_diagnoses: list[str]
    llm_calls: int
    stages: dict[str, Any]
    metrics: dict[str, Any]

    def as_prediction(self, *, arm: str, source_id: str, dataset: str) -> dict[str, Any]:
        top = list(self.ordered_diagnoses) or ([self.champion] if self.champion else [])
        return {
            "arm": arm,
            "case_id": self.case_id,
            "source_id": source_id,
            "dataset": dataset,
            "list_k": len(top[:2]),
            "ordered_diagnoses": top,
            "top2_diagnoses": top[:2],
            "cost": {"llm_calls": int(self.llm_calls)},
            "stages": self.stages,
            "aphhm_c_metrics": self.metrics,
        }


class AphhmCPipeline:
    def __init__(
        self,
        llm: Any,
        *,
        mode: str = "c4",
        unique_budget: int = 10,
        max_facts: int = 12,
        main_k: int = 4,
        protected_k: int = 2,
        axis_lambda: float = 0.5,
        resolver: Any = None,
        max_calls: Optional[int] = None,
        concept_contract: str = "v1",
        axis_mode: str = "conditioned",
        stances: Optional[list[str]] = None,
        near_dedup_shortlist: bool = False,
        group_near_dedup: bool = False,
        near_dedup_jaccard: float = 0.4,
    ) -> None:
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}")
        if concept_contract not in CONCEPT_CONTRACTS:
            raise ValueError(f"concept_contract must be one of {CONCEPT_CONTRACTS}")
        if axis_mode not in AXIS_MODES:
            raise ValueError(f"axis_mode must be one of {AXIS_MODES}")
        self.llm = llm
        self.mode = mode
        self.unique_budget = int(unique_budget)
        self.max_facts = int(max_facts)
        self.main_k = int(main_k)
        self.protected_k = int(protected_k)
        self.axis_mode = axis_mode
        self.axis_lambda = (
            0.0
            if (mode == "c4_noaxisbias" or axis_mode == "off")
            else float(axis_lambda)
        )
        self.enable_gap = mode != "c4_nogap"
        # The selector arms isolate the cost of the deterministic-rank
        # constraint, so they spend the optional slot on the selector rather
        # than on the verifier.
        self.enable_verifier = mode not in ("c4_noverifier",) + SELECTOR_MODES
        self.frontier_selector = mode in SELECTOR_MODES
        # wide/rich stop the score from pruning the shortlist: the frontier
        # measurably drops gold that generation had already found.
        self.selector_all_concepts = mode in (
            "c4_selector_wide",
            "c4_selector_rich",
            "c4_selector_clean",
            "c4_selector_candev",
            "c4_selector_candev_nomatrix",
            "multistance",
            "multistance_split",
        )
        # candev feeds the selector the generator's own per-candidate spans
        # instead of cells drawn from the shared ledger (design 2.4 under test).
        self.selector_candidate_evidence = mode in (
            "c4_selector_candev",
            "c4_selector_candev_nomatrix",
            "multistance",
            "multistance_split",
        )
        # the collapsed arm drops C4 entirely: 3 fixed calls, B07/Lite budget
        self.enable_matrix = mode not in (
            "c4_selector_candev_nomatrix",
            "multistance",
            "multistance_split",
        )
        # multistance buys recall with one generation call per stance and protects
        # conversion by deciding as a tournament instead of over a flat shortlist
        self.stances: list[str] = []
        if mode in ("multistance", "multistance_split"):
            self.stances = list(stances or ("commit", "coverage", "mechanism"))
            bad = [x for x in self.stances if x not in STANCES]
            if bad:
                raise ValueError(f"unknown stances {bad}; choose from {sorted(STANCES)}")
        self.tournament = mode in ("multistance", "multistance_split")
        # R6/R6.1: near-sibling competition drives silent_drop / group_drop.
        # Optional collapses before selector / stance nomination (off by default).
        self.near_dedup_shortlist = bool(near_dedup_shortlist)
        self.group_near_dedup = bool(group_near_dedup)
        self.near_dedup_jaccard = float(near_dedup_jaccard)
        # §17.3 put conversion on a line that falls 4.6pp per extra candidate, and
        # the tournament sits 0.065 above it. Splitting the two rounds into their
        # own calls tests whether the single-call version was losing the final for
        # want of attention rather than for want of evidence.
        self.split_final = mode == "multistance_split"
        self.selector_rich_notes = mode in ("c4_selector_rich", "c4_selector_clean")
        # offline replay showed the ordinal score is anti-correlated with the
        # gold rank, so the clean arm withholds it as a selection anchor.
        self.selector_unanchored = mode in (
            "c4_selector_clean",
            "c4_selector_candev",
            "c4_selector_candev_nomatrix",
            "multistance",
            "multistance_split",
        )
        self.legacy_champion = mode == "legacy_champion"
        self.resolver = resolver
        self.max_calls = int(
            max_calls
            or (len(self.stances) + (4 if self.split_final else 3) if self.stances else 6)
        )
        self.prompt_c1 = _read_prompt("aphhm_c_fact_ledger.txt")
        self.prompt_c2 = _read_prompt("aphhm_c_axis_contract.txt")
        self.concept_contract = concept_contract
        self.prompt_c3 = _read_prompt(CONCEPT_CONTRACTS[concept_contract])
        self.stance_prompts = {k: _read_prompt(v) for k, v in STANCES.items()}
        self.prompt_c3b = _read_prompt("aphhm_c_complement.txt")
        self.prompt_c4 = _read_prompt("aphhm_c_global_matrix.txt")
        self.prompt_c5 = _read_prompt("aphhm_c_adjudicator.txt")
        self.prompt_nomination = _read_prompt("aphhm_c_stance_nomination.txt")
        self.prompt_final = _read_prompt("aphhm_c_final_adjudicator.txt")
        if self.tournament:
            sel_prompt = "aphhm_c_frontier_selector_tournament.txt"
        elif self.selector_candidate_evidence:
            sel_prompt = "aphhm_c_frontier_selector_candev.txt"
        elif self.selector_unanchored:
            sel_prompt = "aphhm_c_frontier_selector_clean.txt"
        elif self.selector_rich_notes:
            sel_prompt = "aphhm_c_frontier_selector_rich.txt"
        else:
            sel_prompt = "aphhm_c_frontier_selector.txt"
        self.prompt_sel = _read_prompt(sel_prompt)

    # --- LLM ----------------------------------------------------------
    def _call(self, module: str, prompt: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        raw = self.llm.call(module, prompt, dict(payload))
        return dict(raw) if isinstance(raw, Mapping) else {"raw": raw}

    # --- C1 -----------------------------------------------------------
    def _build_fact_ledger(self, vignette: str) -> tuple[list[ObservedFact], dict]:
        raw = self._call(
            "AphhmCFactLedger",
            self.prompt_c1,
            {"vignette": vignette, "max_facts": self.max_facts},
        )
        facts: list[ObservedFact] = []
        seen: set[str] = set()
        for i, item in enumerate(_as_list(raw.get("facts"))):
            if not isinstance(item, Mapping):
                continue
            span = str(item.get("raw_span") or "").strip()
            if not span or _norm(span) in seen:
                continue
            seen.add(_norm(span))
            facts.append(
                ObservedFact(
                    fact_id=f"F{len(facts)+1:02d}",
                    raw_span=span,
                    polarity=_pick(item.get("polarity"), ("present", "absent", "uncertain"), "present"),
                    temporality=_pick(
                        item.get("temporality"), ("current", "past", "progressive"), "current"
                    ),
                    epistemic_status=_pick(
                        item.get("epistemic_status"),
                        ("observed", "reported", "provisional_diagnosis"),
                        "observed",
                    ),
                    modality=_pick(
                        item.get("modality"),
                        ("pathology", "imaging", "laboratory", "history", "exam", "genetics", "treatment_response"),
                        "history",
                    ),
                    specificity=_pick(item.get("specificity"), ("high", "medium", "low"), "medium"),
                    reliability=_pick(item.get("reliability"), ("high", "medium", "low"), "medium"),
                    correlation_group=str(item.get("correlation_group") or "").strip(),
                )
            )
            if len(facts) >= self.max_facts:
                break
        return facts, raw

    # --- C2 -----------------------------------------------------------
    def _build_axis_contract(
        self, vignette: str, facts: list[ObservedFact]
    ) -> tuple[AxisContract, dict]:
        raw = self._call(
            "AphhmCAxisContract",
            self.prompt_c2,
            {
                "vignette": vignette,
                "facts": [
                    {
                        "fact_id": f.fact_id,
                        "raw_span": f.raw_span,
                        "specificity": f.specificity,
                        "modality": f.modality,
                        "epistemic_status": f.epistemic_status,
                    }
                    for f in facts
                ],
            },
        )
        families: list[Family] = []
        for i, item in enumerate(_as_list(raw.get("families"))):
            if not isinstance(item, Mapping):
                continue
            fid = str(item.get("family_id") or f"B{len(families)+1}").strip()
            families.append(
                Family(
                    family_id=fid,
                    label=str(item.get("label") or fid).strip(),
                    scope_in=[str(x) for x in _as_list(item.get("scope_in"))],
                    scope_out=[str(x) for x in _as_list(item.get("scope_out"))],
                    initial_belief_rank=int(item.get("initial_belief_rank") or (len(families) + 1)),
                )
            )
        coverage: dict[str, list[str]] = {}
        kind: dict[str, str] = {}
        for item in _as_list(raw.get("fact_coverage")):
            if not isinstance(item, Mapping):
                continue
            fid = str(item.get("fact_id") or "").strip()
            if not fid:
                continue
            coverage[fid] = [str(x).strip() for x in _as_list(item.get("family_ids")) if str(x).strip()]
            kind[fid] = _pick(item.get("coverage"), ("specific", "partial", "none"), "partial")
        placement: dict[str, str] = {}
        for item in _as_list(raw.get("recall_placement")):
            if not isinstance(item, Mapping):
                continue
            rid = str(item.get("recall_id") or "").strip()
            if rid:
                placement[rid] = str(item.get("primary_family_id") or "").strip()
        contract = AxisContract(
            axis=str(raw.get("axis") or "").strip(),
            families=families,
            fact_coverage=coverage,
            coverage_kind=kind,
            recall_placement=placement,
            provisional_anchor_used_as_evidence=bool(
                raw.get("provisional_anchor_used_as_evidence")
            ),
        )
        return contract, raw

    def _axis_guard(
        self, contract: AxisContract, facts: list[ObservedFact]
    ) -> AxisGuardReport:
        family_ids = {f.family_id for f in contract.families}
        report = AxisGuardReport()
        for f in facts:
            if f.specificity != "high" or f.is_provisional:
                continue
            fams = [x for x in contract.fact_coverage.get(f.fact_id, []) if x in family_ids]
            if not fams or contract.coverage_kind.get(f.fact_id) == "none":
                report.uncovered_high_specific_fact_ids.append(f.fact_id)
        seen_primary: dict[str, int] = {}
        for rid, fam in contract.recall_placement.items():
            if fam not in family_ids:
                report.unassigned_high_quality_recall_ids.append(rid)
            seen_primary[rid] = seen_primary.get(rid, 0) + 1
        report.multi_primary_recall_ids = [r for r, n in seen_primary.items() if n > 1]
        # granularity: a "family" that is actually a single disease entity
        for fam in contract.families:
            if not fam.scope_in and not fam.scope_out:
                report.granularity_violations.append(fam.family_id)
        report.provisional_anchor_clone = contract.provisional_anchor_used_as_evidence
        return report

    # --- C3 -----------------------------------------------------------
    def _quotas(self, contract: AxisContract, guard: AxisGuardReport) -> dict[str, int]:
        fams = sorted(contract.families, key=lambda f: f.initial_belief_rank)
        if not fams:
            return {}
        quotas = {f.family_id: 1 for f in fams}
        remaining = max(0, self.unique_budget - len(fams))
        # extra quota to high-belief families and families carrying uncovered facts
        carrying: set[str] = set()
        for fid in guard.uncovered_high_specific_fact_ids:
            for fam in contract.fact_coverage.get(fid, []):
                carrying.add(fam)
        order = [f.family_id for f in fams if f.family_id in carrying]
        order += [f.family_id for f in fams if f.family_id not in carrying]
        i = 0
        while remaining > 0 and order:
            quotas[order[i % len(order)]] += 1
            remaining -= 1
            i += 1
        return quotas

    def _generate_concepts(
        self,
        *,
        vignette: str,
        facts: list[ObservedFact],
        contract: AxisContract,
        guard: AxisGuardReport,
        registry: ConceptRegistry,
    ) -> dict:
        payload: dict[str, Any] = {
            "vignette": vignette,
            "facts": [
                {"fact_id": f.fact_id, "raw_span": f.raw_span, "specificity": f.specificity}
                for f in facts
            ],
            "gap_obligation_fact_ids": guard.uncovered_high_specific_fact_ids,
            "unique_budget": self.unique_budget,
        }
        if self.axis_mode == "conditioned":
            quotas = self._quotas(contract, guard)
            payload["axis"] = contract.axis
            payload["families"] = [
                {**f.as_dict(), "quota": quotas.get(f.family_id, 1)}
                for f in contract.families
            ]
        if self.stances:
            raws = []
            for stance in self.stances:
                raws.append(
                    {
                        "stance": stance,
                        **self._ingest_concepts(
                            self._call(
                                "AphhmCBatchedConcepts",
                                self.stance_prompts[stance],
                                payload,
                            ),
                            vignette=vignette,
                            facts=facts,
                            registry=registry,
                            stance=stance,
                        ),
                    }
                )
            return {"stances": raws}
        return self._ingest_concepts(
            self._call("AphhmCBatchedConcepts", self.prompt_c3, payload),
            vignette=vignette,
            facts=facts,
            registry=registry,
            stance="",
        )

    def _ingest_concepts(
        self,
        raw: dict,
        *,
        vignette: str,
        facts: list[ObservedFact],
        registry: ConceptRegistry,
        stance: str,
    ) -> dict:
        valid_facts = {f.fact_id for f in facts}
        hay = _norm(vignette)
        for item in _as_list(raw.get("concepts")):
            if not isinstance(item, Mapping):
                continue
            registry.add(
                label=str(item.get("preferred_label") or "").strip(),
                primary_parent=str(item.get("primary_parent") or "").strip(),
                secondary_parents=[str(x).strip() for x in _as_list(item.get("secondary_parent_refs"))],
                support_fact_ids=[
                    str(x).strip() for x in _as_list(item.get("support_fact_ids"))
                    if str(x).strip() in valid_facts
                ],
                support_spans=self._verbatim(item.get("support_spans"), hay),
                contradict_spans=self._verbatim(item.get("contradict_spans"), hay),
                aliases=[str(x) for x in _as_list(item.get("aliases"))],
                recall_provenance=[str(x) for x in _as_list(item.get("recall_provenance"))],
                origin=f"c3:{stance}" if stance else "c3",
                stance=stance,
            )
        return raw

    @staticmethod
    def _verbatim(raw: Any, hay: str) -> list[str]:
        """Keep only spans the vignette really contains (design 3.1 provenance)."""
        out: list[str] = []
        for x in _as_list(raw):
            span = str(x or "").strip()
            if len(span) < 4 or span in out:
                continue
            if _norm(span) in hay:
                out.append(span)
        return out

    @staticmethod
    def _registry_uncovered_specific(
        facts: list[ObservedFact], registry: ConceptRegistry
    ) -> list[str]:
        """High-specificity observed facts that no generated concept explains."""
        explained: set[str] = set()
        for c in registry.concepts.values():
            explained.update(c.support_fact_ids)
        return [
            f.fact_id
            for f in facts
            if f.specificity == "high" and not f.is_provisional and f.fact_id not in explained
        ]

    def _complement(
        self,
        *,
        vignette: str,
        facts: list[ObservedFact],
        obligations: list[str],
        registry: ConceptRegistry,
    ) -> dict:
        obligation_set = set(obligations)
        uncovered = [f for f in facts if f.fact_id in obligation_set]
        raw = self._call(
            "AphhmCComplement",
            self.prompt_c3b,
            {
                "vignette": vignette,
                "uncovered_facts": [
                    {"fact_id": f.fact_id, "raw_span": f.raw_span, "modality": f.modality}
                    for f in uncovered
                ],
                "existing_labels": [c.preferred_label for c in registry.concepts.values()],
                "max_new": 2,
            },
        )
        valid_facts = {f.fact_id for f in facts}
        added = 0
        for item in _as_list(raw.get("concepts")):
            if added >= 2 or not isinstance(item, Mapping):
                continue
            bound = [
                str(x).strip() for x in _as_list(item.get("support_fact_ids"))
                if str(x).strip() in valid_facts
            ]
            # gap lane is not a rare-disease dumpster: must bind an uncovered fact
            if not (set(bound) & obligation_set):
                continue
            before = len(registry.concepts)
            registry.add(
                label=str(item.get("preferred_label") or "").strip(),
                primary_parent="AXIS_GAP",
                support_fact_ids=bound,
                aliases=[str(x) for x in _as_list(item.get("aliases"))],
                origin="c3b_gap",
                gap_bound_fact_ids=bound,
            )
            if len(registry.concepts) > before:
                added += 1
        raw["_admitted_new"] = added
        return raw

    # --- C4 -----------------------------------------------------------
    def _annotate_matrix(
        self,
        *,
        vignette: str,
        facts: list[ObservedFact],
        concepts: list[ConceptNode],
        ledger: EvidenceLedger,
        calls: int,
    ) -> tuple[list[dict], int]:
        # Chunk by FACT ROWS only; every chunk still carries all concepts so the
        # candidate-relative scale never drifts (design 3.4).
        cells = len(facts) * max(1, len(concepts))
        n_chunks = 2 if (cells > 180 and calls + 1 < self.max_calls) else 1
        size = (len(facts) + n_chunks - 1) // max(1, n_chunks)
        chunks = [facts[i : i + size] for i in range(0, len(facts), size)] or [facts]
        payload_concepts = [
            {
                "concept_id": c.concept_id,
                "label": c.preferred_label,
                "primary_parent": c.primary_parent,
            }
            for c in concepts
        ]
        raws = []
        for chunk in chunks:
            if calls >= self.max_calls:
                break
            raw = self._call(
                "AphhmCGlobalMatrix",
                self.prompt_c4,
                {
                    "vignette": vignette,
                    "facts": [
                        {
                            "fact_id": f.fact_id,
                            "raw_span": f.raw_span,
                            "polarity": f.polarity,
                            "specificity": f.specificity,
                        }
                        for f in chunk
                    ],
                    "concepts": payload_concepts,
                },
            )
            calls += 1
            ledger.ingest(raw.get("effects") or {}, source="c4")
            for fid, text in (raw.get("rationales") or {}).items():
                ledger.rationales[str(fid)] = str(text)
            raws.append(raw)
        return raws, calls

    # --- ranking ------------------------------------------------------
    def _axis_bias(self, concept: ConceptNode, contract: AxisContract) -> float:
        if self.axis_lambda <= 0:
            return 0.0
        belief = contract.belief_of(concept.primary_parent)
        for p in concept.secondary_parent_refs:
            belief = max(belief, 0.5 * contract.belief_of(p))
        raw = self.axis_lambda * belief
        return max(-AXIS_BIAS_CAP, min(AXIS_BIAS_CAP, raw))

    def _rank(
        self, registry: ConceptRegistry, ledger: EvidenceLedger, contract: AxisContract
    ) -> list[ConceptNode]:
        """Write scores first, then rank (design 7.1). Deterministic tie-break."""
        for c in registry.concepts.values():
            score, comp = ledger.score_concept(c, self._axis_bias(c, contract))
            c.score = score
            c.score_components = comp

        def key(c: ConceptNode):
            admitted = ledger.admitted_cells(c.concept_id)
            strong_out = sum(
                1 for x in admitted if x.direction == "rule_out" and x.strength == "strong"
            )
            spec_in = sum(
                1
                for x in admitted
                if x.direction == "rule_in"
                and ledger.facts[x.fact_id].specificity == "high"
            )
            decisive = {
                fid for fid, f in ledger.facts.items() if f.specificity == "high"
            }
            covered = len(
                {x.fact_id for x in admitted if x.direction == "rule_in"} & decisive
            )
            # evidence-supported specificity: a subtype with its own admitted
            # rule-in outranks its broader parent
            granularity = len(c.narrower_than) if spec_in > 0 else 0
            return (
                -c.score,
                strong_out,
                -spec_in,
                -covered,
                -granularity,
                c.concept_id,
            )

        return sorted(registry.active(), key=key)

    def _frontier(
        self, ranked: list[ConceptNode], ledger: EvidenceLedger, registry: ConceptRegistry
    ) -> list[ConceptNode]:
        """Post-score display set. Never a pre-score prune (design 4.2)."""
        main = ranked[: self.main_k]
        main_ids = {c.concept_id for c in main}
        rest = [c for c in ranked if c.concept_id not in main_ids]
        protected: list[ConceptNode] = []
        for c in rest:
            if len(protected) >= self.protected_k:
                break
            admitted = ledger.admitted_cells(c.concept_id)
            has_strong_out = any(
                x.direction == "rule_out" and x.strength == "strong" for x in admitted
            )
            unique_spec_in = any(
                x.direction == "rule_in"
                and ledger.facts[x.fact_id].specificity == "high"
                for x in admitted
            )
            if has_strong_out:
                continue
            if unique_spec_in or c.gap_bound_fact_ids:
                protected.append(c)
                registry.set_status(
                    c.concept_id, "protected", "unique_high_specific_rule_in_or_gap"
                )
        return main + protected

    def _disputed_top_pair(
        self, ranked: list[ConceptNode], ledger: EvidenceLedger
    ) -> Optional[str]:
        if len(ranked) < 2:
            return None
        top, second = ranked[0], ranked[1]
        admitted = ledger.admitted_cells(top.concept_id)
        if any(x.direction == "rule_out" and x.strength == "strong" for x in admitted):
            return "top1_strong_rule_out"
        unknown = 0
        conflict = 0
        for fid, fact in ledger.facts.items():
            a = ledger.cells[(fid, top.concept_id)]
            b = ledger.cells[(fid, second.concept_id)]
            if fact.specificity != "high":
                continue
            if a.direction == "unknown" or b.direction == "unknown":
                unknown += 1
            if {a.direction, b.direction} == {"rule_in", "rule_out"}:
                conflict += 1
        if unknown >= 1 or conflict >= 2:
            return "top_pair_disputed_cells"
        if second.concept_id in top.broader_than or second.concept_id in top.narrower_than:
            return "broad_subtype_unresolved"
        if abs(top.score - second.score) < 1e-9:
            return "tied_score"
        return None

    def _adjudicate(
        self,
        *,
        vignette: str,
        ranked: list[ConceptNode],
        ledger: EvidenceLedger,
        reason: str,
    ) -> dict:
        top, second = ranked[0], ranked[1]
        disputed = []
        for fid, fact in ledger.facts.items():
            a = ledger.cells[(fid, top.concept_id)]
            b = ledger.cells[(fid, second.concept_id)]
            if fact.specificity != "high":
                continue
            if a.direction == "unknown" or b.direction == "unknown" or {
                a.direction,
                b.direction,
            } == {"rule_in", "rule_out"}:
                disputed.append(
                    {
                        "fact_id": fid,
                        "raw_span": fact.raw_span,
                        "a": {"direction": a.direction, "strength": a.strength},
                        "b": {"direction": b.direction, "strength": b.strength},
                    }
                )
        raw = self._call(
            "AphhmCAdjudicator",
            self.prompt_c5,
            {
                "vignette": vignette,
                "reason": reason,
                "candidate_a": {"concept_id": top.concept_id, "label": top.preferred_label},
                "candidate_b": {"concept_id": second.concept_id, "label": second.preferred_label},
                "disputed_cells": disputed[:8],
            },
        )
        applied = 0
        rejected = 0
        if str(raw.get("verdict") or "").strip().lower() != "abstain":
            for item in _as_list(raw.get("corrections")):
                if not isinstance(item, Mapping):
                    rejected += 1
                    continue
                fid = str(item.get("fact_id") or "").strip()
                cid = str(item.get("concept_id") or "").strip()
                key = (fid, cid)
                # verifier may only touch existing disputed cells of the top pair
                if key not in ledger.cells or cid not in (top.concept_id, second.concept_id):
                    rejected += 1
                    continue
                if fid not in {d["fact_id"] for d in disputed}:
                    rejected += 1
                    continue
                direction = _pick(item.get("direction"), _DIRECTIONS, "")
                if not direction:
                    rejected += 1
                    continue
                strength = _pick(item.get("strength"), _STRENGTHS, "moderate")
                cell = ledger.cells[key]
                cell.direction = direction
                cell.strength = "none" if direction in ("neutral", "unknown") else strength
                cell.source = "c5"
                applied += 1
        raw["_applied"] = applied
        raw["_rejected"] = rejected
        return raw

    def _select_frontier(
        self,
        *,
        vignette: str,
        frontier: list[ConceptNode],
        ledger: EvidenceLedger,
    ) -> tuple[dict, str]:
        notes = []
        for c in frontier:
            admitted = ledger.admitted_cells(c.concept_id)
            note = {
                "label": c.preferred_label,
                "score": round(c.score, 3),
                "supports": [
                    ledger.facts[x.fact_id].raw_span
                    for x in admitted
                    if x.direction == "rule_in"
                ][:3],
                "contradicts": [
                    ledger.facts[x.fact_id].raw_span
                    for x in admitted
                    if x.direction == "rule_out"
                ][:2],
            }
            if self.selector_candidate_evidence:
                note = {
                    "label": c.preferred_label,
                    "for": list(c.support_spans)[:4],
                    "against": list(c.contradict_spans)[:3],
                }
            elif self.selector_rich_notes:
                note = {
                    "label": note["label"],
                    "generation_support": [
                        ledger.facts[f].raw_span
                        for f in c.support_fact_ids
                        if f in ledger.facts
                    ][:4],
                    "admitted_for": note["supports"],
                    "admitted_against": note["contradicts"],
                }
                if not self.selector_unanchored:
                    note["score"] = round(c.score, 3)
            notes.append(note)
        shortlist = [c.preferred_label for c in frontier]
        if self.tournament:
            groups: dict[str, list[dict]] = {}
            for c, note in zip(frontier, notes):
                stance = (c.stances or ["unassigned"])[0]
                entry = dict(note)
                if len(c.stances) > 1:
                    entry["also_found_by"] = c.stances[1:]
                groups.setdefault(stance, []).append(entry)
            payload = {
                "vignette": vignette,
                "shortlist": shortlist,
                "groups": [
                    {"group": g, "candidates": v} for g, v in groups.items()
                ],
            }
            if self.group_near_dedup:
                before = sum(len(g["candidates"]) for g in payload["groups"])
                payload["groups"] = nd.dedupe_group_notes(
                    payload["groups"], jaccard=self.near_dedup_jaccard
                )
                # refresh flat shortlist from deduped groups
                labs = []
                for g in payload["groups"]:
                    for c in g["candidates"]:
                        lab = str(c.get("label") or "")
                        if lab and lab not in labs:
                            labs.append(lab)
                payload["shortlist"] = labs
                payload["group_near_dedup"] = {
                    "before": before,
                    "after": sum(len(g["candidates"]) for g in payload["groups"]),
                }
        else:
            payload = {
                "vignette": vignette,
                "shortlist": shortlist,
                "candidate_notes": notes,
            }
        if self.tournament and self.split_final:
            return self._select_in_two_rounds(
                vignette=vignette, frontier=frontier, payload=payload
            )
        raw = self._call("AphhmCFrontierSelector", self.prompt_sel, payload)
        champ = str(raw.get("champion") or "").strip()
        if champ not in shortlist:
            champ = next(
                (x for x in shortlist if _norm(x) == _norm(champ)), shortlist[0]
            )
        return raw, champ, 1

    def _select_in_two_rounds(
        self, *, vignette: str, frontier: list[ConceptNode], payload: dict
    ) -> tuple[dict, str, int]:
        """Nominate one finalist per stance, then adjudicate the finalists."""
        by_label = {_norm(c.preferred_label): c for c in frontier}
        allowed = {
            g["group"]: {_norm(str(x.get("label") or "")) for x in g["candidates"]}
            for g in payload["groups"]
        }
        nomination = self._call(
            "AphhmCStanceNomination", self.prompt_nomination, payload
        )
        finalists: list[dict] = []
        seen: set[str] = set()
        for item in _as_list(nomination.get("finalists")):
            if not isinstance(item, Mapping):
                continue
            norm = _norm(str(item.get("label") or ""))
            group = str(item.get("group") or "")
            # a nomination that reaches outside its own group is dropped, not
            # remapped: the point of the round is that each stance speaks for itself
            if norm not in by_label or norm in seen or norm not in allowed.get(group, set()):
                continue
            seen.add(norm)
            node = by_label[norm]
            finalists.append(
                {
                    "group": group,
                    "label": node.preferred_label,
                    "for": list(node.support_spans)[:4],
                    "against": list(node.contradict_spans)[:3],
                    "why": str(item.get("why") or ""),
                    "unexplained": str(item.get("unexplained") or ""),
                }
            )
        if not finalists:
            # nothing usable came back; fall back to the single-call tournament
            raw = self._call("AphhmCFrontierSelector", self.prompt_sel, payload)
            champ = str(raw.get("champion") or "").strip()
            shortlist = payload["shortlist"]
            if champ not in shortlist:
                champ = next(
                    (x for x in shortlist if _norm(x) == _norm(champ)), shortlist[0]
                )
            return {"nomination": nomination, "fallback": raw}, champ, 2
        labels = [f["label"] for f in finalists]
        if len(finalists) == 1:
            return {"nomination": nomination, "finalists": finalists}, labels[0], 1
        final = self._call(
            "AphhmCFinalAdjudicator",
            self.prompt_final,
            {"vignette": vignette, "finalists": finalists, "shortlist": labels},
        )
        champ = str(final.get("champion") or "").strip()
        if champ not in labels:
            champ = next((x for x in labels if _norm(x) == _norm(champ)), labels[0])
        runner = str(final.get("runner_up") or "").strip()
        if runner and runner not in labels:
            runner = next((x for x in labels if _norm(x) == _norm(runner)), "")
        merged = {
            "nomination": nomination,
            "finalists": finalists,
            "final": final,
            "champion": champ,
            "runner_up": runner if runner != champ else "",
        }
        return merged, champ, 2

    # --- entry point --------------------------------------------------
    def run(self, *, case_id: str, vignette: str) -> AphhmCResult:
        calls = 0
        stages: dict[str, Any] = {"mode": self.mode, "vignette_chars": len(vignette)}
        registry = ConceptRegistry(resolver=self.resolver)

        facts, c1 = self._build_fact_ledger(vignette)
        calls += 1
        stages["c1"] = c1
        stages["facts"] = [f.as_dict() for f in facts]

        if self.axis_mode == "off":
            contract, guard = AxisContract(), AxisGuardReport()
            stages["c2"] = {"skipped": True, "reason": "axis_mode=off"}
        else:
            contract, c2 = self._build_axis_contract(vignette, facts)
            calls += 1
            stages["c2"] = c2
            guard = self._axis_guard(contract, facts)
        stages["axis_contract"] = contract.as_dict()
        stages["axis_guard"] = guard.as_dict()

        c3 = self._generate_concepts(
            vignette=vignette, facts=facts, contract=contract, guard=guard, registry=registry
        )
        calls += len(self.stances) or 1
        stages["c3"] = c3

        # design 7.1: axis gap obligations OR decisive facts no concept explains
        obligations = list(
            dict.fromkeys(
                guard.uncovered_high_specific_fact_ids
                + self._registry_uncovered_specific(facts, registry)
            )
        )
        stages["gap_obligations"] = obligations
        gap_used = False
        if self.enable_gap and obligations and calls + 2 <= self.max_calls:
            stages["c3b"] = self._complement(
                vignette=vignette, facts=facts, obligations=obligations, registry=registry
            )
            calls += 1
            gap_used = True

        concepts = registry.active()
        ledger = EvidenceLedger(facts, concepts)
        if self.enable_matrix:
            matrix_raws, calls = self._annotate_matrix(
                vignette=vignette,
                facts=facts,
                concepts=concepts,
                ledger=ledger,
                calls=calls,
            )
            stages["c4"] = matrix_raws
        else:
            stages["c4"] = {"skipped": True, "reason": f"mode={self.mode}"}
        ledger.apply_gates(registry)

        ranked = self._rank(registry, ledger, contract)
        ledger_rank_before = [c.concept_id for c in ranked]

        verifier_reason = None
        verifier_applied = 0
        if self.enable_verifier and len(ranked) >= 2 and calls < self.max_calls:
            verifier_reason = self._disputed_top_pair(ranked, ledger)
            if verifier_reason:
                c5 = self._adjudicate(
                    vignette=vignette, ranked=ranked, ledger=ledger, reason=verifier_reason
                )
                calls += 1
                stages["c5"] = c5
                verifier_applied = int(c5.get("_applied") or 0)
                if verifier_applied:
                    for cell in ledger.cells.values():
                        if cell.source != "c5":
                            cell.admitted = False
                            cell.value = 0
                            cell.veto_reason = ""
                    ledger.gate_log.clear()
                    ledger.apply_gates(registry)
                    ranked = self._rank(registry, ledger, contract)

        frontier = self._frontier(ranked, ledger, registry)
        # Final order IS the ledger order; the frontier only marks lanes.
        ordered = [c.preferred_label for c in ranked]
        champion = ordered[0] if ordered else ""

        shortlist = ranked if self.selector_all_concepts else frontier
        if self.selector_unanchored:
            # present in generation order so the shortlist carries no ranking
            shortlist = sorted(shortlist, key=lambda c: c.concept_id)
        if self.near_dedup_shortlist and shortlist:
            before_n = len(shortlist)
            shortlist = nd.dedupe_by_label(
                shortlist,
                lambda c: c.preferred_label,
                jaccard=self.near_dedup_jaccard,
            )
            stages["near_dedup_shortlist"] = {
                "before": before_n,
                "after": len(shortlist),
                "jaccard": self.near_dedup_jaccard,
            }
        rounds = 2 if self.split_final else 1
        if self.frontier_selector and shortlist and calls + rounds <= self.max_calls:
            sel, champion, used = self._select_frontier(
                vignette=vignette, frontier=shortlist, ledger=ledger
            )
            calls += used
            stages["frontier_selector"] = sel
            runner = str(sel.get("runner_up") or "").strip()
            rest = [x for x in ordered if x != champion]
            if runner and runner in rest:
                rest = [runner] + [x for x in rest if x != runner]
            ordered = [champion] + rest

        if self.legacy_champion:
            # ablation arm: one champion per family before global comparison
            by_family: dict[str, ConceptNode] = {}
            for c in ranked:
                by_family.setdefault(c.primary_parent or "NA", c)
            legacy = sorted(by_family.values(), key=lambda c: -c.score)
            ordered = [c.preferred_label for c in legacy]
            champion = ordered[0] if ordered else champion

        stages["ledger"] = ledger.as_dict()
        stages["registry"] = [c.as_dict() for c in registry.concepts.values()]
        stages["events"] = list(registry.events)
        stages["merge_audit"] = list(registry.merge_audit)
        stages["frontier"] = [c.concept_id for c in frontier]
        stages["ledger_rank"] = [c.concept_id for c in ranked]

        n_decisive = sum(1 for f in facts if f.specificity == "high")
        metrics = {
            "mode": self.mode,
            "concept_contract": self.concept_contract,
            "axis_mode": self.axis_mode,
            "stances": list(self.stances),
            "unique_budget": self.unique_budget,
            "llm_calls": calls,
            "n_concepts_per_stance": {
                st: sum(1 for c in registry.concepts.values() if st in c.stances)
                for st in self.stances
            },
            "n_multi_stance_concepts": sum(
                1 for c in registry.concepts.values() if len(c.stances) > 1
            ),
            "n_facts": len(facts),
            "n_decisive_facts": n_decisive,
            "n_families": len(contract.families),
            "n_concepts": len(registry.concepts),
            "n_active_concepts": len(registry.active()),
            "resolved_duplicates": registry.resolved_duplicate_count(),
            "unexplained_disappearance": registry.unexplained_events(),
            "p3_completeness": (
                ledger.p3_completeness() if self.enable_matrix else None
            ),
            "p4_admitted_cells": sum(1 for c in ledger.cells.values() if c.admitted),
            "p5_shared_phenotype_vetoes": sum(
                1 for c in ledger.cells.values() if c.veto_reason == "p5_shared_phenotype"
            ),
            "p5_scope_error_vetoes": sum(
                1
                for c in ledger.cells.values()
                if c.veto_reason == "p5_scope_error_child_to_parent"
            ),
            "axis_uncovered_high_specific": len(guard.uncovered_high_specific_fact_ids),
            "gap_obligations": len(obligations),
            "axis_gap_lane_used": gap_used,
            "gap_concepts": sum(1 for c in registry.concepts.values() if c.gap_bound_fact_ids),
            "frontier_n": len(frontier),
            "protected_n": sum(1 for c in registry.concepts.values() if c.status == "protected"),
            "verifier_reason": verifier_reason,
            "verifier_applied_cells": verifier_applied,
            "ledger_final_inversion": int(
                not self.frontier_selector
                and [c.concept_id for c in ranked] != ledger_rank_before
                and verifier_applied == 0
            ),
            "frontier_selector_used": self.frontier_selector,
            "selector_shortlist_n": len(shortlist) if self.frontier_selector else 0,
            "legacy_champion_arm": self.legacy_champion,
        }
        return AphhmCResult(
            case_id=case_id,
            champion=champion,
            ordered_diagnoses=ordered[:5],
            llm_calls=calls,
            stages=stages,
            metrics=metrics,
        )
