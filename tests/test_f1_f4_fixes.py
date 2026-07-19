"""Regression tests for the F1–F4 root-cause fixes.

F1  KB-grounded direction reconciliation + pathognomonic posterior floor
F2  numeric Bayesian (odds×LR) probability update
F3  AnswerMapper self-consistency (final_answer == argmax of mapping)
F4  separation-aware (margin) commit gating
"""
from __future__ import annotations

from agentclinic_tree_dx.config import ControllerConfig
from agentclinic_tree_dx.controller import AgentClinicTreeController
from agentclinic_tree_dx.state import Branch, DiagnosticState, EvidenceItem
from agentclinic_tree_dx.update_router import choose_update_method
from agentclinic_tree_dx.updater import bayesian_lr_update


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


def test_f2_bayesian_lr_update_makes_supported_branch_lead():
    branches = {
        "B1": _branch("B1", "CML", 0.20),
        "B2": _branch("B2", "AML", 0.49),
        "B3": _branch("B3", "MDS", 0.31),
    }
    post = bayesian_lr_update(branches, {"B1": 100.0, "B2": 0.33, "B3": 1.0})
    assert abs(sum(post.values()) - 1.0) < 1e-6
    assert max(post, key=post.get) == "B1"


def test_choose_update_method_routes_numeric_lr_to_calculator():
    assert choose_update_method({"branch_lr": {"B1": 2.0}}) == "calculator"
    assert choose_update_method({"branch_effects": {"B1": "strong_for"}}) == "ordinal"


def test_f1_pathognomonic_floor_and_renormalization():
    ctrl = AgentClinicTreeController(env=_Env(), config=ControllerConfig())
    state = DiagnosticState(case_id="t")
    state.branches = {
        "B1": _branch("B1", "CML", 0.30),
        "B2": _branch("B2", "AML", 0.50),
        "B3": _branch("B3", "MDS", 0.20),
    }
    ctrl._apply_pathognomonic_floor(state, {"_pathognomonic_floor_branches": ["B1"]})
    assert state.branches["B1"].posterior >= ctrl.config.pathognomonic_posterior_floor
    total = sum(b.posterior for b in state.branches.values())
    assert abs(total - 1.0) < 1e-6


def test_f3_answer_consistency_forces_argmax():
    ctrl = AgentClinicTreeController(env=_Env(), config=ControllerConfig())
    final, _ = ctrl._enforce_answer_consistency(
        "B", {"A": 0.05, "B": 0.35, "C": 0.05, "D": 0.06, "E": 0.49}
    )
    assert final == "E"


def test_f3_temperature_softens_distribution():
    cfg = ControllerConfig(answer_mapping_softmax_temperature=2.0)
    ctrl = AgentClinicTreeController(env=_Env(), config=cfg)
    final, mapping = ctrl._enforce_answer_consistency("A", {"A": 0.9, "B": 0.1})
    assert final == "A"
    assert mapping["A"] < 0.9  # softened


def test_f4_margin_gate_blocks_near_flat_commit():
    cfg = ControllerConfig(
        execution_mode="static_diagnosis_qa",
        min_readiness_to_commit=0.0,
        min_leader_margin_to_commit=0.15,
    )
    ctrl = AgentClinicTreeController(env=_Env(), config=cfg)
    state = DiagnosticState(case_id="t")
    state.max_turn_budget = 5
    state.turn_budget_used = 1
    state.branches = {
        "B1": _branch("B1", "CML", 0.40),
        "B2": _branch("B2", "AML", 0.38),
    }
    assert ctrl.check_diagnosis_readiness(state) is False  # margin 0.02
    state.branches["B2"].posterior = 0.10  # margin 0.30
    assert ctrl.check_diagnosis_readiness(state) is True


class _FakeRetriever:
    """Mimics DxFeatureRetriever for the atomic-finding reconcile path: only the
    clean symptom 'basophilia' maps to CML with a strong inclusion LR.

    match_evidence_to_phenotypes keys by the input text (the real match_batch
    contract); the structured atomic facts are already clean so the mapping is
    identity."""

    def match_evidence_to_phenotypes(self, texts, *, threshold=0.4):
        return {t: [{"phenotype": t}] for t in texts}

    def get_lr_reference(self, finding, diseases, hpo_id="", fast=False):
        data = {}
        for d in diseases:
            if "CML" in d and finding == "basophilia":
                # Real cache entries carry conclusive LRs under a "medium" label.
                data[d] = {"confidence": "medium", "lr_positive": 10.9, "source": "cache"}
            else:
                data[d] = None
        return {"finding": finding, "lr_data": data, "source": "cache"}


def test_f1_atomic_finding_reconcile_grounds_via_clean_symptom():
    cfg = ControllerConfig(enable_knowledge_injection=True,
                           enable_kb_direction_reconciliation=True,
                           enable_numeric_lr_update=True)
    ctrl = AgentClinicTreeController(env=_Env(), config=cfg)
    ctrl._knowledge_retriever = _FakeRetriever()
    state = DiagnosticState(case_id="t")
    # Lossless path: VignetteParser already produced atomic EvidenceItem facts;
    # _gather_atomic_findings reads them directly (no phrase-split / embedding).
    state.static_evidence_items = [
        EvidenceItem(id="e0", kind="direct", content="basophilia"),
        EvidenceItem(id="e1", kind="direct", content="splenomegaly"),
    ]
    state.branches = {
        "B1": _branch("B1", "CML in chronic phase", 0.30),
        "B2": _branch("B2", "AML", 0.50),
    }
    ann = ctrl._reconcile_annotation_with_kb(
        state, {"branch_effects": {"B1": "neutral", "B2": "moderate_for"}}
    )
    # The clean atomic finding 'basophilia' grounds CML even though the branch
    # label is the verbose 'CML in chronic phase'.
    assert ann["branch_effects"]["B1"] == "moderate_for"
    assert ann.get("branch_lr", {}).get("B1") == 10.9


def test_f4_budget_exhaustion_overrides_margin_gate():
    cfg = ControllerConfig(
        execution_mode="static_diagnosis_qa",
        min_readiness_to_commit=0.0,
        min_leader_margin_to_commit=0.15,
    )
    ctrl = AgentClinicTreeController(env=_Env(), config=cfg)
    state = DiagnosticState(case_id="t")
    state.max_turn_budget = 5
    state.turn_budget_used = 5  # exhausted
    state.branches = {
        "B1": _branch("B1", "CML", 0.40),
        "B2": _branch("B2", "AML", 0.38),
    }
    assert ctrl.check_diagnosis_readiness(state) is True
