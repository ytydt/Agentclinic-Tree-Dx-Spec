"""MOSAIC-Dx / IMPC-Dx pipelines.

Modes:
  lite        — G1+G2+S (3 calls)
  adaptive4   — legacy Adaptive-4 gate
  adaptive4v2 — stricter A1 + optional A5 pairwise (≤4 calls)
  forest      — 3 non-exclusive axes + S (+ optional A1) (4–5 calls)
  impc        — 3 history-isolated doctors + union + S (4 calls)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

from agentclinic_tree_dx.backbone import _read_prompt

MODES = ("lite", "adaptive4", "adaptive4v2", "forest", "impc")


def _norm(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[^\w\s\-/\+]", "", s)
    return s


def _as_list(x: Any) -> list[Any]:
    if x is None:
        return []
    if isinstance(x, list):
        return x
    return [x]


@dataclass
class EvidenceFact:
    evidence_id: str
    raw_span: str
    polarity: str = "present"
    epistemic_status: str = "observed"
    modality: str = "text"
    reliability: float = 1.0
    source_view: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "raw_span": self.raw_span,
            "polarity": self.polarity,
            "epistemic_status": self.epistemic_status,
            "modality": self.modality,
            "reliability": self.reliability,
            "source_view": self.source_view,
        }


@dataclass
class CandidateConcept:
    concept_id: str
    preferred_name: str
    aliases: list[str] = field(default_factory=list)
    generator_views: list[str] = field(default_factory=list)
    axis_nodes: list[str] = field(default_factory=list)
    supporting_evidence: list[str] = field(default_factory=list)
    contradicting_evidence: list[str] = field(default_factory=list)
    protected_reason: str = ""
    score_logit: float = 0.0
    status: str = "live"
    agent_votes: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "concept_id": self.concept_id,
            "preferred_name": self.preferred_name,
            "aliases": list(self.aliases),
            "generator_views": list(self.generator_views),
            "axis_nodes": list(self.axis_nodes),
            "supporting_evidence": list(self.supporting_evidence),
            "contradicting_evidence": list(self.contradicting_evidence),
            "protected_reason": self.protected_reason,
            "score_logit": self.score_logit,
            "status": self.status,
            "agent_votes": self.agent_votes,
        }


class GlobalConceptRegistry:
    def __init__(self, resolver: Any = None) -> None:
        self.resolver = resolver
        self.concepts: dict[str, CandidateConcept] = {}
        self._alias_index: dict[str, str] = {}
        self.events: list[dict[str, Any]] = []
        self._next_id = 1

    def _match(self, a: str, b: str) -> bool:
        if not a or not b:
            return False
        if _norm(a) == _norm(b):
            return True
        if self.resolver is not None:
            try:
                ra = getattr(self.resolver, "resolve", None)
                if callable(ra):
                    aa = str(ra(a) or a)
                    bb = str(ra(b) or b)
                    if _norm(aa) == _norm(bb):
                        return True
            except Exception:
                pass
        na, nb = _norm(a), _norm(b)
        if len(na) >= 6 and len(nb) >= 6 and (na in nb or nb in na):
            return True
        return False

    def _find(self, name: str) -> Optional[str]:
        key = _norm(name)
        if key in self._alias_index:
            return self._alias_index[key]
        for cid, c in self.concepts.items():
            if self._match(name, c.preferred_name):
                return cid
            for al in c.aliases:
                if self._match(name, al):
                    return cid
        return None

    def merge_candidate(
        self,
        *,
        name: str,
        view: str,
        support_ids: list[str],
        contradict_ids: list[str],
        protected_reason: str = "",
        axis_node: str = "",
        count_vote: bool = False,
    ) -> str:
        name = str(name or "").strip()
        if not name:
            return ""
        existing = self._find(name)
        if existing:
            c = self.concepts[existing]
            if view not in c.generator_views:
                c.generator_views.append(view)
            if name.lower() != c.preferred_name.lower() and name not in c.aliases:
                c.aliases.append(name)
            for e in support_ids:
                if e not in c.supporting_evidence:
                    c.supporting_evidence.append(e)
            for e in contradict_ids:
                if e not in c.contradicting_evidence:
                    c.contradicting_evidence.append(e)
            if protected_reason and not c.protected_reason:
                c.protected_reason = protected_reason
            if axis_node and axis_node not in c.axis_nodes:
                c.axis_nodes.append(axis_node)
            if count_vote:
                c.agent_votes += 1
            self.events.append({"op": "merge", "concept_id": existing, "name": name, "view": view})
            return existing
        cid = f"C{self._next_id:03d}"
        self._next_id += 1
        c = CandidateConcept(
            concept_id=cid,
            preferred_name=name,
            generator_views=[view],
            supporting_evidence=list(support_ids),
            contradicting_evidence=list(contradict_ids),
            protected_reason=protected_reason or "",
            axis_nodes=[axis_node] if axis_node else [],
            agent_votes=1 if count_vote else 0,
        )
        self.concepts[cid] = c
        self._alias_index[_norm(name)] = cid
        self.events.append({"op": "add", "concept_id": cid, "name": name, "view": view})
        return cid

    def score(self) -> None:
        for c in self.concepts.values():
            if c.status != "live":
                continue
            z = 0.0
            z += 1.0 * len(c.supporting_evidence)
            z -= 1.25 * len(c.contradicting_evidence)
            z += 0.35 * max(0, len(c.generator_views) - 1)
            z += 0.15 * max(0, len(c.axis_nodes) - 1)  # multi-axis attachment
            if c.protected_reason:
                z += 0.25
            if not c.supporting_evidence:
                z -= 0.5
            # agent_votes MUST NOT enter likelihood (IMPC constraint)
            c.score_logit = z

    def exact_duplicate_count(self) -> int:
        seen: dict[str, str] = {}
        dups = 0
        for c in self.concepts.values():
            k = _norm(c.preferred_name)
            if k in seen:
                dups += 1
            seen[k] = c.concept_id
        return dups

    def two_lane_frontier(self, main_k: int = 4, protected_k: int = 2) -> list[CandidateConcept]:
        live = [c for c in self.concepts.values() if c.status == "live"]
        live.sort(key=lambda c: (-c.score_logit, c.preferred_name.lower()))
        main = live[:main_k]
        main_ids = {c.concept_id for c in main}
        rest = [c for c in live if c.concept_id not in main_ids]
        protected: list[CandidateConcept] = []
        for c in rest:
            if c.protected_reason or (
                len(c.supporting_evidence) >= 1 and len(c.generator_views) == 1
            ):
                protected.append(c)
            if len(protected) >= protected_k:
                break
        for c in rest:
            if len(protected) >= protected_k:
                break
            if c not in protected:
                protected.append(c)
        out = list(main)
        for c in protected:
            if c.concept_id not in {x.concept_id for x in out}:
                out.append(c)
        return out


@dataclass
class MosaicResult:
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
            "mosaic_metrics": self.metrics,
        }


class MosaicPipeline:
    def __init__(
        self,
        llm: Any,
        *,
        mode: str = "lite",
        main_k: int = 4,
        protected_k: int = 2,
        resolver: Any = None,
        margin_threshold: float = 0.75,
        max_calls: Optional[int] = None,
    ) -> None:
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}")
        self.llm = llm
        self.mode = mode
        self.main_k = main_k
        self.protected_k = protected_k
        self.resolver = resolver
        self.margin_threshold = margin_threshold
        default_caps = {
            "lite": 3,
            "adaptive4": 4,
            "adaptive4v2": 4,
            "forest": 5,
            "impc": 4,
        }
        self.max_calls = int(max_calls or default_caps[mode])
        self.prompt_g1 = _read_prompt("mosaic_g1_common.txt")
        self.prompt_g2 = _read_prompt("mosaic_g2_counter.txt")
        self.prompt_s = _read_prompt("mosaic_selector.txt")
        self.prompt_a1 = _read_prompt("mosaic_orthogonal.txt")
        self.prompt_a5 = _read_prompt("mosaic_pairwise.txt")
        self.prompt_ax1 = _read_prompt("mosaic_axis_syndrome.txt")
        self.prompt_ax2 = _read_prompt("mosaic_axis_mechanism.txt")
        self.prompt_ax3 = _read_prompt("mosaic_axis_modality.txt")
        self.prompt_impc = _read_prompt("mosaic_impc_doctor.txt")

    def _call(self, module: str, prompt: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        raw = self.llm.call(module, prompt, dict(payload))
        return dict(raw) if isinstance(raw, Mapping) else {"raw": raw}

    def _ingest_generator(
        self,
        *,
        registry: GlobalConceptRegistry,
        evidence: dict[str, EvidenceFact],
        raw: Mapping[str, Any],
        view: str,
        eid_prefix: str,
        count_vote: bool = False,
    ) -> None:
        for span in _as_list(raw.get("key_evidence_spans")):
            span = str(span or "").strip()
            if not span:
                continue
            exists = next((e for e in evidence.values() if e.raw_span == span), None)
            if exists is None:
                eid = f"{eid_prefix}E{len(evidence)+1:03d}"
                evidence[eid] = EvidenceFact(
                    evidence_id=eid, raw_span=span, source_view=view
                )
        for item in _as_list(raw.get("candidates")):
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            support_ids = []
            for span in _as_list(item.get("support_spans")):
                span = str(span or "").strip()
                if not span:
                    continue
                exists = next((e for e in evidence.values() if e.raw_span == span), None)
                if exists is None:
                    eid = f"{eid_prefix}E{len(evidence)+1:03d}"
                    evidence[eid] = EvidenceFact(
                        evidence_id=eid, raw_span=span, source_view=view
                    )
                    support_ids.append(eid)
                else:
                    support_ids.append(exists.evidence_id)
            contradict_ids = []
            for span in _as_list(item.get("contradict_spans")):
                span = str(span or "").strip()
                if not span:
                    continue
                exists = next((e for e in evidence.values() if e.raw_span == span), None)
                if exists is None:
                    eid = f"{eid_prefix}E{len(evidence)+1:03d}"
                    evidence[eid] = EvidenceFact(
                        evidence_id=eid, raw_span=span, source_view=view
                    )
                    contradict_ids.append(eid)
                else:
                    contradict_ids.append(exists.evidence_id)
            registry.merge_candidate(
                name=name,
                view=view,
                support_ids=support_ids,
                contradict_ids=contradict_ids,
                protected_reason=str(item.get("protected_reason") or ""),
                axis_node=str(item.get("axis_node") or ""),
                count_vote=count_vote,
            )

    def _jaccard(self, a: set[str], b: set[str]) -> float:
        if not a and not b:
            return 1.0
        if not a or not b:
            return 0.0
        return len(a & b) / len(a | b)

    def _diagnose_state(
        self,
        registry: GlobalConceptRegistry,
        evidence: dict[str, EvidenceFact],
        frontier: list[CandidateConcept],
        name_sets: list[set[str]],
    ) -> dict[str, Any]:
        live = [c for c in registry.concepts.values() if c.status == "live"]
        covered = set()
        for c in live:
            covered.update(c.supporting_evidence)
        unexplained = [
            e.raw_span
            for eid, e in evidence.items()
            if eid not in covered and len(e.raw_span) >= 12
        ]
        scores = sorted((c.score_logit for c in frontier), reverse=True)
        margin = (scores[0] - scores[1]) if len(scores) >= 2 else 99.0
        top_views = frontier[0].generator_views if frontier else []
        jacc = 0.0
        pairs = 0
        for i in range(len(name_sets)):
            for j in range(i + 1, len(name_sets)):
                jacc += self._jaccard(
                    {_norm(x) for x in name_sets[i]}, {_norm(x) for x in name_sets[j]}
                )
                pairs += 1
        return {
            "unexplained_specific_evidence": unexplained[:8],
            "generator_jaccard": (jacc / pairs) if pairs else 0.0,
            "top1_same_across_views": len(top_views) >= 2,
            "top_margin": margin,
            "leave_one_view_instability": len(top_views) == 1,
            "contradiction_mass": (
                len(frontier[0].contradicting_evidence) if frontier else 0
            ),
        }

    def _notes(self, frontier: list[CandidateConcept], evidence: dict[str, EvidenceFact]) -> list[dict]:
        notes = []
        for c in frontier:
            notes.append(
                {
                    "label": c.preferred_name,
                    "support": [
                        evidence[e].raw_span
                        for e in c.supporting_evidence
                        if e in evidence
                    ][:3],
                    "contradict": [
                        evidence[e].raw_span
                        for e in c.contradicting_evidence
                        if e in evidence
                    ][:2],
                    "views": c.generator_views,
                    "axis_nodes": c.axis_nodes,
                    "protected_reason": c.protected_reason,
                    "score_logit": c.score_logit,
                    "agent_votes": c.agent_votes,
                }
            )
        return notes

    def _select_from_frontier(
        self,
        *,
        vignette: str,
        frontier: list[CandidateConcept],
        evidence: dict[str, EvidenceFact],
        stages: dict[str, Any],
        calls: int,
        prefer_pairwise: bool = False,
    ) -> tuple[str, list[str], int]:
        shortlist = [c.preferred_name for c in frontier]
        if not shortlist:
            return "", [], calls
        notes = self._notes(frontier, evidence)
        if prefer_pairwise and len(shortlist) >= 2 and calls < self.max_calls:
            a5 = self._call(
                "MosaicPairwiseVerifier",
                self.prompt_a5,
                {
                    "vignette": vignette[:6000],
                    "candidate_a": shortlist[0],
                    "candidate_b": shortlist[1],
                    "notes": notes[:2],
                },
            )
            calls += 1
            stages["a5"] = a5
            champ = str(a5.get("champion") or "").strip()
            if champ not in shortlist:
                champ = next((x for x in shortlist if _norm(x) == _norm(champ)), shortlist[0])
            ordered = [champ] + [x for x in shortlist if x != champ]
            return champ, ordered, calls

        if calls < self.max_calls:
            sel = self._call(
                "MosaicEvidenceSelector",
                self.prompt_s,
                {
                    "vignette": vignette[:6000],
                    "shortlist": shortlist,
                    "candidate_notes": notes,
                },
            )
            calls += 1
            stages["selector"] = sel
            champ = str(sel.get("champion") or "").strip()
            if champ not in shortlist:
                champ = next((x for x in shortlist if _norm(x) == _norm(champ)), shortlist[0])
            runner = str(sel.get("runner_up") or "").strip()
            ordered = [champ] + [x for x in shortlist if x != champ]
            if runner and runner in shortlist and runner != champ:
                ordered = [champ, runner] + [
                    x for x in ordered if x not in (champ, runner)
                ]
            return champ, ordered, calls

        stages["selector"] = {"skipped": True, "reason": "budget"}
        return shortlist[0], list(shortlist), calls

    def _maybe_a1(
        self,
        *,
        vignette: str,
        registry: GlobalConceptRegistry,
        evidence: dict[str, EvidenceFact],
        state: dict[str, Any],
        stages: dict[str, Any],
        calls: int,
        strict: bool,
    ) -> tuple[Optional[str], list[CandidateConcept], int]:
        if calls >= self.max_calls - 1:  # reserve 1 for selector
            return None, registry.two_lane_frontier(self.main_k, self.protected_k), calls
        unexplained = state["unexplained_specific_evidence"]
        if strict:
            # report recommendation: unexplained≥2 AND low margin; do NOT expand on high Jaccard alone
            need = (
                len(unexplained) >= 2
                and state["top_margin"] < self.margin_threshold
                and state["generator_jaccard"] < 0.85
            )
        else:
            need = bool(unexplained) and (
                len(unexplained) >= 2
                or state["generator_jaccard"] > 0.85
                or state["leave_one_view_instability"]
                or state["top_margin"] < self.margin_threshold
            )
        if not need or not unexplained:
            return None, registry.two_lane_frontier(self.main_k, self.protected_k), calls
        o = self._call(
            "MosaicOrthogonalGenerator",
            self.prompt_a1,
            {"vignette": vignette[:6000], "unexplained_spans": unexplained[:6]},
        )
        calls += 1
        stages["a1"] = o
        self._ingest_generator(
            registry=registry, evidence=evidence, raw=o, view="a1", eid_prefix="A1"
        )
        registry.score()
        return "ORTHOGONAL_GENERATE", registry.two_lane_frontier(self.main_k, self.protected_k), calls

    def _finish(
        self,
        *,
        case_id: str,
        registry: GlobalConceptRegistry,
        evidence: dict[str, EvidenceFact],
        frontier: list[CandidateConcept],
        state: dict[str, Any],
        stages: dict[str, Any],
        champ: str,
        ordered: list[str],
        calls: int,
        action: Optional[str],
        name_sets: list[set[str]],
    ) -> MosaicResult:
        metrics = {
            "n_concepts": len(registry.concepts),
            "n_evidence": len(evidence),
            "exact_duplicates": registry.exact_duplicate_count(),
            "generator_jaccard": state.get("generator_jaccard"),
            "frontier_n": len(frontier),
            "protected_n": sum(1 for c in frontier if c.protected_reason),
            "n_generators": len(name_sets),
            "adaptive_action": action,
            "llm_calls": calls,
            "history_leakage": 0,
            "mode": self.mode,
        }
        stages["evidence"] = [e.as_dict() for e in evidence.values()]
        stages["registry"] = [c.as_dict() for c in registry.concepts.values()]
        stages["events"] = list(registry.events)
        stages["frontier_final"] = [c.as_dict() for c in frontier]
        return MosaicResult(
            case_id=case_id,
            champion=champ,
            ordered_diagnoses=ordered[:5],
            llm_calls=calls,
            stages=stages,
            metrics=metrics,
        )

    def _run_lite_family(self, *, case_id: str, vignette: str, strict_gate: bool) -> MosaicResult:
        calls = 0
        registry = GlobalConceptRegistry(resolver=self.resolver)
        evidence: dict[str, EvidenceFact] = {}
        stages: dict[str, Any] = {"mode": self.mode, "vignette_chars": len(vignette)}

        g1 = self._call("MosaicGeneratorCommon", self.prompt_g1, {"vignette": vignette[:6000]})
        calls += 1
        g2 = self._call(
            "MosaicGeneratorCounterAnchor", self.prompt_g2, {"vignette": vignette[:6000]}
        )
        calls += 1
        stages["g1"] = g1
        stages["g2"] = g2
        g1_names = {
            str(x.get("name") or "")
            for x in _as_list(g1.get("candidates"))
            if isinstance(x, dict)
        }
        g2_names = {
            str(x.get("name") or "")
            for x in _as_list(g2.get("candidates"))
            if isinstance(x, dict)
        }
        self._ingest_generator(
            registry=registry, evidence=evidence, raw=g1, view="g1", eid_prefix="G1"
        )
        self._ingest_generator(
            registry=registry, evidence=evidence, raw=g2, view="g2", eid_prefix="G2"
        )
        registry.score()
        frontier = registry.two_lane_frontier(self.main_k, self.protected_k)
        state = self._diagnose_state(registry, evidence, frontier, [g1_names, g2_names])
        stages["state_after_g"] = state

        action = None
        if self.mode in ("adaptive4", "adaptive4v2"):
            action, frontier, calls = self._maybe_a1(
                vignette=vignette,
                registry=registry,
                evidence=evidence,
                state=state,
                stages=stages,
                calls=calls,
                strict=strict_gate,
            )
            state = self._diagnose_state(
                registry, evidence, frontier, [g1_names, g2_names]
            )
            stages["state_after_a1"] = state
        stages["adaptive_action"] = action

        prefer_pw = (
            self.mode == "adaptive4v2"
            and action is None
            and state["top_margin"] < self.margin_threshold
            and calls <= self.max_calls - 1
        )
        champ, ordered, calls = self._select_from_frontier(
            vignette=vignette,
            frontier=frontier,
            evidence=evidence,
            stages=stages,
            calls=calls,
            prefer_pairwise=prefer_pw,
        )
        return self._finish(
            case_id=case_id,
            registry=registry,
            evidence=evidence,
            frontier=frontier,
            state=state,
            stages=stages,
            champ=champ,
            ordered=ordered,
            calls=calls,
            action=action,
            name_sets=[g1_names, g2_names],
        )

    def _run_forest(self, *, case_id: str, vignette: str) -> MosaicResult:
        calls = 0
        registry = GlobalConceptRegistry(resolver=self.resolver)
        evidence: dict[str, EvidenceFact] = {}
        stages: dict[str, Any] = {"mode": "forest", "vignette_chars": len(vignette)}
        axes = [
            ("ax_syndrome", "MosaicAxisSyndrome", self.prompt_ax1),
            ("ax_mechanism", "MosaicAxisMechanism", self.prompt_ax2),
            ("ax_modality", "MosaicAxisModality", self.prompt_ax3),
        ]
        name_sets: list[set[str]] = []
        for view, module, prompt in axes:
            raw = self._call(module, prompt, {"vignette": vignette[:6000]})
            calls += 1
            stages[view] = raw
            names = {
                str(x.get("name") or "")
                for x in _as_list(raw.get("candidates"))
                if isinstance(x, dict)
            }
            name_sets.append(names)
            self._ingest_generator(
                registry=registry,
                evidence=evidence,
                raw=raw,
                view=view,
                eid_prefix=view.upper()[:4],
            )
        registry.score()
        frontier = registry.two_lane_frontier(self.main_k, self.protected_k)
        state = self._diagnose_state(registry, evidence, frontier, name_sets)
        stages["state_after_axes"] = state
        action, frontier, calls = self._maybe_a1(
            vignette=vignette,
            registry=registry,
            evidence=evidence,
            state=state,
            stages=stages,
            calls=calls,
            strict=True,
        )
        stages["adaptive_action"] = action
        if action:
            state = self._diagnose_state(registry, evidence, frontier, name_sets)
        champ, ordered, calls = self._select_from_frontier(
            vignette=vignette,
            frontier=frontier,
            evidence=evidence,
            stages=stages,
            calls=calls,
            prefer_pairwise=False,
        )
        return self._finish(
            case_id=case_id,
            registry=registry,
            evidence=evidence,
            frontier=frontier,
            state=state,
            stages=stages,
            champ=champ,
            ordered=ordered,
            calls=calls,
            action=action,
            name_sets=name_sets,
        )

    def _run_impc(self, *, case_id: str, vignette: str) -> MosaicResult:
        calls = 0
        registry = GlobalConceptRegistry(resolver=self.resolver)
        evidence: dict[str, EvidenceFact] = {}
        stages: dict[str, Any] = {"mode": "impc", "vignette_chars": len(vignette)}
        name_sets: list[set[str]] = []
        for i, did in enumerate(("D1", "D2", "D3")):
            # heterogeneous perspective hints without revealing other doctors
            hint = {
                "D1": "Focus on the most likely common diagnosis covering all decisive findings.",
                "D2": "Actively consider uncommon / high-specificity alternatives.",
                "D3": "Challenge any provisional label in the vignette; look for mimics.",
            }[did]
            raw = self._call(
                "MosaicIMPCDoctor",
                self.prompt_impc,
                {
                    "vignette": vignette[:6000],
                    "doctor_id": did,
                    "perspective_hint": hint,
                },
            )
            calls += 1
            stages[did] = raw
            names = {
                str(x.get("name") or "")
                for x in _as_list(raw.get("candidates"))
                if isinstance(x, dict)
            }
            name_sets.append(names)
            # UNION-first: merge all; agent_votes tracked but not used in likelihood
            self._ingest_generator(
                registry=registry,
                evidence=evidence,
                raw=raw,
                view=did,
                eid_prefix=did,
                count_vote=True,
            )
        # minority preservation: never delete by vote count
        registry.score()
        frontier = registry.two_lane_frontier(self.main_k, self.protected_k)
        # boost protected lane for single-doctor concepts with evidence
        state = self._diagnose_state(registry, evidence, frontier, name_sets)
        stages["state_after_doctors"] = state
        stages["adaptive_action"] = None
        champ, ordered, calls = self._select_from_frontier(
            vignette=vignette,
            frontier=frontier,
            evidence=evidence,
            stages=stages,
            calls=calls,
            prefer_pairwise=False,
        )
        return self._finish(
            case_id=case_id,
            registry=registry,
            evidence=evidence,
            frontier=frontier,
            state=state,
            stages=stages,
            champ=champ,
            ordered=ordered,
            calls=calls,
            action=None,
            name_sets=name_sets,
        )

    def run(self, *, case_id: str, vignette: str) -> MosaicResult:
        if self.mode == "lite":
            return self._run_lite_family(case_id=case_id, vignette=vignette, strict_gate=False)
        if self.mode == "adaptive4":
            return self._run_lite_family(case_id=case_id, vignette=vignette, strict_gate=False)
        if self.mode == "adaptive4v2":
            return self._run_lite_family(case_id=case_id, vignette=vignette, strict_gate=True)
        if self.mode == "forest":
            return self._run_forest(case_id=case_id, vignette=vignette)
        if self.mode == "impc":
            return self._run_impc(case_id=case_id, vignette=vignette)
        raise ValueError(self.mode)
