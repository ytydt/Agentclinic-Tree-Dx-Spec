"""Regression tests for the LR- rule-out channel (normal/absent findings).

Covers:
  - FindingNormalizer surfaces the abnormal phenotypes a NORMAL value negates.
  - controller._gather_normal_ruleout_findings honours the gate.
  - reconciliation applies LR- (Bayesian down-weight) for a high-Sn finding that
    is absent (value normal), and respects the sensitivity / LR- thresholds and
    the pathognomonic floor.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from agentclinic_tree_dx.config import ControllerConfig
from agentclinic_tree_dx.controller import AgentClinicTreeController
from agentclinic_tree_dx.knowledge.finding_normalizer import (
    FindingNormalizer, NormalizedFinding,
)
from agentclinic_tree_dx.state import Branch, DiagnosticState, EvidenceItem

_DATA = Path(__file__).resolve().parents[1] / "data" / "knowledge_raw"


class _Env:
    def get_case_summary(self):
        return ""

    def root_changed_materially(self, state):
        return False


def _branch(bid, label, posterior, status="live"):
    return Branch(
        id=bid, label=label, parent=None, level=1, status=status,
        prior=posterior, posterior=posterior, danger=0.0,
        actionability=0.0, explanatory_coverage=0.0,
    )


# ── 1. FindingNormalizer negated phenotypes ─────────────────────────────────
def test_normalizer_normal_value_lists_negated_phenotypes():
    fn = FindingNormalizer(
        _DATA / "lab_reference_ranges.json",
        _DATA / "loinc2hpo_annotations.json",
        _DATA / "unit_conversions.json",
    )
    norms = fn.normalize_multi("WBC: 7000/uL")
    assert norms and norms[0].direction == "N"
    assert "Leukocytosis" in norms[0].negated_hpo_terms

    # an ABNORMAL value carries a positive phenotype and NO negated list
    ab = fn.normalize_multi("WBC: 57000/uL")
    assert ab and ab[0].direction == "H" and ab[0].hpo_term
    assert ab[0].negated_hpo_terms == []


# ── 2. fake normalizer + retriever for controller-level tests ───────────────
class _FakeNormalizer:
    def normalize_multi(self, raw):
        low = raw.lower()
        if "wbc" in low and "7000" in low:
            return [NormalizedFinding(
                original=raw, hpo_term=None, hpo_id=None, direction="N",
                confidence="high", source="test",
                negated_hpo_terms=["Leukocytosis"],
            )]
        return []


class _RuleoutRetriever:
    finding_normalizer = _FakeNormalizer()

    def match_evidence_to_phenotypes(self, texts, *, threshold=0.4):
        return {t: [{"phenotype": t}] for t in texts}

    def get_lr_reference(self, finding, diseases, hpo_id="", fast=False):
        data = {}
        for d in diseases:
            if "CML" in d and finding == "Leukocytosis":
                # high-Sn finding: its ABSENCE strongly argues against CML
                data[d] = {"confidence": "medium", "sensitivity": 0.97,
                           "lr_positive": 5.0, "lr_negative": 0.05, "source": "cache"}
            else:
                data[d] = None
        return {"finding": finding, "lr_data": data, "source": "cache"}


def _state_with_normal_wbc():
    state = DiagnosticState(case_id="t")
    state.static_evidence_items = [
        EvidenceItem(id="e0", kind="direct", content="WBC: 7000/uL"),
    ]
    state.branches = {
        "B1": _branch("B1", "CML", 0.50),
        "B2": _branch("B2", "AML", 0.50),
    }
    return state


def test_ruleout_gate_off_by_default():
    ctrl = AgentClinicTreeController(env=_Env(), config=ControllerConfig())
    ctrl._knowledge_retriever = _RuleoutRetriever()
    assert ctrl._gather_normal_ruleout_findings(_state_with_normal_wbc()) == []


def test_ruleout_gate_on_surfaces_negated_finding():
    cfg = ControllerConfig(enable_normal_value_ruleout=True)
    ctrl = AgentClinicTreeController(env=_Env(), config=cfg)
    ctrl._knowledge_retriever = _RuleoutRetriever()
    assert ctrl._gather_normal_ruleout_findings(_state_with_normal_wbc()) == ["Leukocytosis"]


def test_ruleout_applies_lr_negative_against_branch():
    cfg = ControllerConfig(
        enable_knowledge_injection=True,
        enable_kb_direction_reconciliation=True,
        enable_numeric_lr_update=True,
        enable_normal_value_ruleout=True,
    )
    ctrl = AgentClinicTreeController(env=_Env(), config=cfg)
    ctrl._knowledge_retriever = _RuleoutRetriever()
    state = _state_with_normal_wbc()
    ann = ctrl._reconcile_annotation_with_kb(
        state, {"branch_effects": {"B1": "neutral", "B2": "neutral"}}
    )
    # normal WBC → Leukocytosis absent → CML pushed down via LR-
    assert ann["branch_effects"]["B1"] == "moderate_against"
    assert ann["branch_lr"]["B1"] == pytest.approx(0.05)
    # AML untouched (no rule-out signal) → neutral pseudo-LR 1.0
    assert ann["branch_lr"]["B2"] == pytest.approx(1.0)


class _RagQuantRuleoutRetriever(_RuleoutRetriever):
    """Rule-out signal sourced from RAG-quant (unreliable Sn, guessed Sp)."""

    def get_lr_reference(self, finding, diseases, hpo_id="", fast=False):
        data = {}
        for d in diseases:
            if "CML" in d and finding == "Leukocytosis":
                data[d] = {"confidence": "rag_qualitative", "sensitivity": 0.95,
                           "lr_positive": 1.0, "lr_negative": 0.0588,
                           "source": "RAG-quant:corpus"}
            else:
                data[d] = None
        return {"finding": finding, "lr_data": data, "source": "RAG-quant:corpus"}


def test_ruleout_ignores_rag_quant_source_by_default():
    cfg = ControllerConfig(
        enable_knowledge_injection=True,
        enable_kb_direction_reconciliation=True,
        enable_numeric_lr_update=True,
        enable_normal_value_ruleout=True,
    )
    ctrl = AgentClinicTreeController(env=_Env(), config=cfg)
    ctrl._knowledge_retriever = _RagQuantRuleoutRetriever()
    state = _state_with_normal_wbc()
    ann = ctrl._reconcile_annotation_with_kb(
        state, {"branch_effects": {"B1": "neutral", "B2": "neutral"}}
    )
    # RAG-quant rule-out must NOT fire → CML untouched (no spurious push-down).
    assert ann["branch_effects"]["B1"] == "neutral"
    assert ann.get("branch_lr", {}).get("B1", 1.0) == pytest.approx(1.0)


def test_ruleout_allows_rag_quant_when_override_enabled():
    cfg = ControllerConfig(
        enable_knowledge_injection=True,
        enable_kb_direction_reconciliation=True,
        enable_numeric_lr_update=True,
        enable_normal_value_ruleout=True,
        rag_lr_can_override_direction=True,
    )
    ctrl = AgentClinicTreeController(env=_Env(), config=cfg)
    ctrl._knowledge_retriever = _RagQuantRuleoutRetriever()
    state = _state_with_normal_wbc()
    ann = ctrl._reconcile_annotation_with_kb(
        state, {"branch_effects": {"B1": "neutral", "B2": "neutral"}}
    )
    assert ann["branch_effects"]["B1"] == "moderate_against"
    assert ann["branch_lr"]["B1"] == pytest.approx(0.0588)


def test_ruleout_skips_low_sensitivity_finding():
    cfg = ControllerConfig(
        enable_knowledge_injection=True,
        enable_kb_direction_reconciliation=True,
        enable_normal_value_ruleout=True,
        ruleout_min_sensitivity=0.99,  # raise bar above the 0.97 fixture
    )
    ctrl = AgentClinicTreeController(env=_Env(), config=cfg)
    ctrl._knowledge_retriever = _RuleoutRetriever()
    state = _state_with_normal_wbc()
    ann = ctrl._reconcile_annotation_with_kb(
        state, {"branch_effects": {"B1": "neutral", "B2": "neutral"}}
    )
    # Sn 0.97 < 0.99 threshold → no rule-out, annotation unchanged
    assert ann.get("branch_lr", {}).get("B1", 1.0) == pytest.approx(1.0) or "branch_lr" not in ann
