"""Regression tests for §21.8 fixes.

(a) Branch ``representative_diseases`` → KB/LR lookup hit-ability: a broad family
    LABEL cannot key the disease-keyed cache, but the canonical representative
    entity behind it can. Gated by ``enable_representative_disease_lr``.

(b) Pivotal-clue surfacing / anti-anchoring: ``_compute_pivotal_hint`` surfaces
    the strongest finding→disease association so the annotator is nudged off the
    common/framed anchor. Gated by ``enable_anti_anchoring``.
"""
from __future__ import annotations

import pytest

from agentclinic_tree_dx.config import ControllerConfig
from agentclinic_tree_dx.controller import (
    AgentClinicTreeController, _clean_representative_diseases,
)
from agentclinic_tree_dx.state import Branch, DiagnosticState, EvidenceItem


class _Env:
    def get_case_summary(self):
        return ""

    def root_changed_materially(self, state):
        return False


def _branch(bid, label, posterior, rep=None, status="live"):
    return Branch(
        id=bid, label=label, parent=None, level=1, status=status,
        prior=posterior, posterior=posterior, danger=0.0,
        actionability=0.0, explanatory_coverage=0.0,
        representative_diseases=list(rep or []),
    )


class _FakeNorm:
    """Everything is a qualitative symptom (no numeric lab recognised)."""

    def normalize_multi(self, raw):
        return []


class _RepDiseaseRetriever:
    """LR fires ONLY when the query string is the canonical entity 'glucagonoma'
    — never on the broad family label."""

    finding_normalizer = _FakeNorm()

    def match_evidence_to_phenotypes(self, texts, *, threshold=0.4):
        return {t: [{"phenotype": "Necrolytic migratory erythema"}] for t in texts}

    def get_lr_reference(self, finding, diseases, hpo_id="", fast=False):
        data = {}
        for d in diseases:
            if d.lower() == "glucagonoma" and finding == "Necrolytic migratory erythema":
                data[d] = {"confidence": "high", "lr_positive": 40.0,
                           "sensitivity": 0.7, "source": "cache"}
            else:
                data[d] = None
        return {"finding": finding, "lr_data": data, "source": "cache"}


def _glucagonoma_state():
    state = DiagnosticState(case_id="t")
    state.static_evidence_items = [
        EvidenceItem(id="e0", kind="direct",
                     content="Painful migratory erythematous rash"),
    ]
    state.branches = {
        # the framed/common anchor
        "B1": _branch("B1", "Insulin Resistance / Metabolic Hyperglycaemia", 0.60,
                      rep=["type 2 diabetes mellitus"]),
        # broad family whose canonical entity is glucagonoma
        "B2": _branch("B2", "Neuroendocrine Tumor-Related Hyperglycaemia", 0.40,
                      rep=["glucagonoma", "somatostatinoma"]),
    }
    return state


# ── _clean_representative_diseases ──────────────────────────────────────────
def test_clean_representative_diseases():
    assert _clean_representative_diseases(None) == []
    assert _clean_representative_diseases("glucagonoma") == ["glucagonoma"]
    assert _clean_representative_diseases(
        ["Glucagonoma", "glucagonoma", "  ", "somatostatinoma"]
    ) == ["Glucagonoma", "somatostatinoma"]
    # template placeholder text is dropped
    assert _clean_representative_diseases(
        ["most likely specific disease", "real entity"]
    ) == ["real entity"]
    # capped at 4
    assert len(_clean_representative_diseases([f"d{i}" for i in range(9)])) == 4


# ── Fix (a): family label MISSes, representative entity HITs ─────────────────
def test_family_label_alone_misses_without_fix_a():
    cfg = ControllerConfig(
        enable_knowledge_injection=True,
        enable_kb_direction_reconciliation=True,
        enable_numeric_lr_update=True,
        enable_representative_disease_lr=False,
    )
    ctrl = AgentClinicTreeController(env=_Env(), config=cfg)
    ctrl._knowledge_retriever = _RepDiseaseRetriever()
    ann = ctrl._reconcile_annotation_with_kb(
        _glucagonoma_state(), {"branch_effects": {"B1": "weak_for", "B2": "neutral"}}
    )
    # No representative-disease query → glucagonoma never looked up → MISS.
    assert ann["branch_effects"]["B2"] == "neutral"
    assert ann.get("branch_lr", {}).get("B2", 1.0) == pytest.approx(1.0)


def test_representative_disease_enables_hit_with_fix_a():
    cfg = ControllerConfig(
        enable_knowledge_injection=True,
        enable_kb_direction_reconciliation=True,
        enable_numeric_lr_update=True,
        enable_representative_disease_lr=True,
    )
    ctrl = AgentClinicTreeController(env=_Env(), config=cfg)
    ctrl._knowledge_retriever = _RepDiseaseRetriever()
    ann = ctrl._reconcile_annotation_with_kb(
        _glucagonoma_state(), {"branch_effects": {"B1": "weak_for", "B2": "neutral"}}
    )
    # glucagonoma is now a query string → LR+ 40 fires on B2 (anti-anchoring).
    assert ann["branch_effects"]["B2"] == "moderate_for"
    assert ann["branch_lr"]["B2"] == pytest.approx(40.0)


# ── Fix (b): pivotal-evidence hint ──────────────────────────────────────────
def test_pivotal_hint_surfaces_strongest_association():
    cfg = ControllerConfig(
        enable_knowledge_injection=True,
        enable_anti_anchoring=True,
        enable_representative_disease_lr=True,
    )
    ctrl = AgentClinicTreeController(env=_Env(), config=cfg)
    ctrl._knowledge_retriever = _RepDiseaseRetriever()
    hint = ctrl._compute_pivotal_hint(
        ["Necrolytic migratory erythema"], ["type 2 diabetes mellitus", "glucagonoma"]
    )
    assert "glucagonoma" in hint.lower()
    # §22.3 (B′): the hint is now NEUTRAL FACTUAL — it surfaces the curated
    # association and its LR, but no longer issues the contrarian
    # "override the common diagnosis / ≥moderate_for" instruction (which biased
    # the annotator away from correct common diagnoses, §21.13.3). The
    # anti-anchoring is carried mechanically by the numeric LR update instead.
    assert "lr+" in hint.lower()
    assert "moderate_for" not in hint.lower()


def test_pivotal_hint_empty_when_no_strong_signal():
    cfg = ControllerConfig(enable_knowledge_injection=True, enable_anti_anchoring=True)
    ctrl = AgentClinicTreeController(env=_Env(), config=cfg)
    ctrl._knowledge_retriever = _RepDiseaseRetriever()
    # finding that maps to nothing strong → no hint
    hint = ctrl._compute_pivotal_hint(["Fatigue"], ["type 2 diabetes mellitus"])
    assert hint == ""
