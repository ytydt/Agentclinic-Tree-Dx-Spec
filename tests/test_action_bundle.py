"""Unit + integration tests for FrontierCoverageBundler.

Covers requirements from TALP_BUNDLER_REDESIGN_SPEC.md and
MULTI_ACTION_DESIGN_REVISION.md §9:
  - is_redundant (high-similarity blocked, low-similarity passes)
  - is_dependent (CALCULATOR after ORDER_LAB blocked)
  - RETRIEVE_KNOWLEDGE serial constraint (at most one per bundle)
  - account_turn_budget: per_bundle / per_action / time_weighted
  - DIAGNOSIS_READY short-circuit returns single action
  - Frontier coverage: each live branch gets at least one representative
  - Dual-channel: confirm + challenge per branch
  - Integration: bundle_size=2, two branches, EvidenceAnnotator receives list
"""
from __future__ import annotations

import pytest

from agentclinic_tree_dx.action_bundler import (
    _is_dependent,
    _is_duplicate_knowledge_retrieval,
    _is_redundant,
    _jaccard,
    _normalize,
    build_bundle,
)
from agentclinic_tree_dx.config import ControllerConfig
from agentclinic_tree_dx.state import Branch, CandidateLeaf, DiagnosticState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _leaf(
    lid: str,
    branch_id: str,
    content: str,
    leaf_type: str = "ASK_PATIENT",
    *,
    score: float = 0.8,
    ig: float = 0.3,
    falsification_value: float = 0.0,
    primary_function: str = "confirm",
    redundancy_group: str = "",
    result_dependency: bool = False,
    target_branches: dict[str, str] | None = None,
    action_separation_value: float = 0.5,
) -> CandidateLeaf:
    leaf = CandidateLeaf(
        leaf_id=lid,
        branch_id=branch_id,
        content=content,
        leaf_type=leaf_type,
        total_score=score,
        expected_information_gain=ig,
        expected_cost=0.0,
        expected_delay=0.0,
        safety_value=0.0,
        action_separation_value=action_separation_value,
        falsification_value=falsification_value,
        primary_function=primary_function,
        redundancy_group=redundancy_group,
        result_dependency=result_dependency,
        target_branches=target_branches or {branch_id: "support"},
    )
    return leaf


def _state(branches_spec: dict[str, float]) -> DiagnosticState:
    """Create a minimal DiagnosticState with live branches.

    branches_spec: {branch_id: posterior}
    """
    state = DiagnosticState(case_id="t")
    state.max_tree_depth = 3
    for bid, post in branches_spec.items():
        b = Branch(
            id=bid,
            label=f"Branch {bid}",
            parent="",
            level=1,
            status="live",
            prior=post,
            posterior=post,
            danger=0.0,
            actionability=0.0,
            explanatory_coverage=0.0,
        )
        state.branches[bid] = b
    state.frontier = list(branches_spec.keys())
    return state


# ---------------------------------------------------------------------------
# Helpers tests
# ---------------------------------------------------------------------------

class TestNormalize:
    def test_lowercases(self):
        assert _normalize("PAIN") == "pain"

    def test_drops_short_tokens(self):
        # Single and two-letter tokens are dropped
        result = _normalize("is it bad")
        assert "is" not in result
        assert "it" not in result

    def test_keeps_long_tokens(self):
        result = _normalize("chest pain radiation")
        assert "chest" in result
        assert "pain" in result


class TestJaccard:
    def test_identical(self):
        assert _jaccard("chest pain", "chest pain") == 1.0

    def test_no_overlap(self):
        assert _jaccard("chest pain", "fever nausea") == 0.0

    def test_partial_overlap(self):
        v = _jaccard("chest pain radiation", "radiation nausea")
        assert 0.0 < v < 1.0

    def test_empty_string(self):
        assert _jaccard("", "something") == 0.0


# ---------------------------------------------------------------------------
# _is_redundant
# ---------------------------------------------------------------------------

class TestIsRedundant:
    def test_high_jaccard_blocked(self):
        bundle = [_leaf("a", "B1", "chest pain radiation to arm")]
        candidate = _leaf("b", "B1", "pain radiates arm chest")
        content_set = {_normalize(bundle[0].content)}
        assert _is_redundant(candidate, bundle, content_set, threshold=0.50) is True

    def test_low_jaccard_passes(self):
        bundle = [_leaf("a", "B1", "radiation to arm")]
        candidate = _leaf("b", "B2", "fever and chills duration")
        content_set = {_normalize(bundle[0].content)}
        assert _is_redundant(candidate, bundle, content_set, threshold=0.50) is False

    def test_same_redundancy_group_blocked(self):
        bundle = [_leaf("a", "B1", "D-dimer test", redundancy_group="venous_workup")]
        candidate = _leaf("b", "B1", "leg ultrasound", redundancy_group="venous_workup")
        content_set = {_normalize(bundle[0].content)}
        assert _is_redundant(candidate, bundle, content_set, threshold=0.60) is True

    def test_different_redundancy_group_passes(self):
        bundle = [_leaf("a", "B1", "D-dimer", redundancy_group="venous_workup")]
        candidate = _leaf("b", "B2", "troponin level", redundancy_group="cardiac_markers")
        content_set = {_normalize(bundle[0].content)}
        assert _is_redundant(candidate, bundle, content_set, threshold=0.60) is False


# ---------------------------------------------------------------------------
# _is_dependent
# ---------------------------------------------------------------------------

class TestIsDependent:
    def test_calculator_after_lab_blocked(self):
        bundle = [_leaf("a", "B1", "CBC", leaf_type="ORDER_LAB")]
        candidate = _leaf("b", "B1", "Wells score", leaf_type="USE_CALCULATOR")
        assert _is_dependent(candidate, bundle) is True

    def test_ask_patient_not_blocked_by_lab(self):
        bundle = [_leaf("a", "B1", "CBC", leaf_type="ORDER_LAB")]
        candidate = _leaf("b", "B2", "fever duration?", leaf_type="ASK_PATIENT")
        assert _is_dependent(candidate, bundle) is False

    def test_calculator_in_empty_bundle_ok(self):
        candidate = _leaf("a", "B1", "Wells score", leaf_type="USE_CALCULATOR")
        assert _is_dependent(candidate, []) is False


# ---------------------------------------------------------------------------
# RETRIEVE_KNOWLEDGE serial constraint
# ---------------------------------------------------------------------------

class TestKnowledgeRetrievalSerial:
    def test_second_knowledge_blocked(self):
        bundle = [_leaf("a", "B1", "rare mutation query", leaf_type="RETRIEVE_KNOWLEDGE")]
        candidate = _leaf("b", "B2", "another knowledge lookup", leaf_type="RETRIEVE_KNOWLEDGE")
        assert _is_duplicate_knowledge_retrieval(candidate, bundle) is True

    def test_first_knowledge_allowed(self):
        bundle = [_leaf("a", "B1", "troponin level", leaf_type="ORDER_LAB")]
        candidate = _leaf("b", "B2", "rare mutation query", leaf_type="RETRIEVE_KNOWLEDGE")
        assert _is_duplicate_knowledge_retrieval(candidate, bundle) is False

    def test_external_knowledge_also_blocked(self):
        bundle = [_leaf("a", "B1", "query1", leaf_type="RETRIEVE_KNOWLEDGE")]
        candidate = _leaf("b", "B2", "query2", leaf_type="RETRIEVE_EXTERNAL_KNOWLEDGE")
        assert _is_duplicate_knowledge_retrieval(candidate, bundle) is True


# ---------------------------------------------------------------------------
# DIAGNOSIS_READY short-circuit
# ---------------------------------------------------------------------------

class TestDiagnosisReadyShortCircuit:
    def test_returns_single_diagnosis_ready_action(self):
        state = _state({"B1": 0.8, "B2": 0.2})
        config = ControllerConfig()
        ready_leaf = _leaf(
            "dr", "B1", "DIAGNOSE_ACS",
            leaf_type="DIAGNOSIS_READY",
            score=0.99,
        )
        other = _leaf("o1", "B2", "check fever?", score=0.5)
        bundle, _ = build_bundle([ready_leaf, other], state, config)
        assert len(bundle) == 1
        assert bundle[0].leaf_type == "DIAGNOSIS_READY"


# ---------------------------------------------------------------------------
# Frontier coverage guarantee
# ---------------------------------------------------------------------------

class TestFrontierCoverage:
    def test_both_live_branches_covered(self):
        state = _state({"B1": 0.6, "B2": 0.4})
        config = ControllerConfig(min_marginal_ig_threshold=0.01)
        leaves = [
            _leaf("a", "B1", "radiation to arm", target_branches={"B1": "support"}),
            _leaf("b", "B2", "fever onset time", target_branches={"B2": "support"}),
        ]
        bundle, coverage = build_bundle(leaves, state, config)
        covered_branches = {b.branch_id for b in bundle}
        assert "B1" in covered_branches
        assert "B2" in covered_branches

    def test_single_branch_gets_one_representative(self):
        state = _state({"B1": 1.0})
        config = ControllerConfig(min_marginal_ig_threshold=0.01)
        leaves = [
            _leaf("a1", "B1", "radiation", score=0.9),
            _leaf("a2", "B1", "onset time", score=0.7),
        ]
        bundle, _ = build_bundle(leaves, state, config)
        b1_items = [l for l in bundle if l.branch_id == "B1"]
        assert len(b1_items) >= 1


# ---------------------------------------------------------------------------
# account_turn_budget
# ---------------------------------------------------------------------------

class TestAccountTurnBudget:
    def _ctrl(self, mode: str):
        from agentclinic_tree_dx.adapters.mock_env import MockAgentClinicEnv
        cfg = ControllerConfig(bundle_budget_mode=mode)
        env = MockAgentClinicEnv(module_responses={})
        from agentclinic_tree_dx.controller import AgentClinicTreeController
        return AgentClinicTreeController(env, config=cfg)

    def _bundle(self, n: int) -> list[CandidateLeaf]:
        return [
            _leaf(f"l{i}", "B1", f"action {i}", leaf_type="ASK_PATIENT")
            for i in range(n)
        ]

    def test_per_bundle_always_1(self):
        ctrl = self._ctrl("per_bundle")
        state = DiagnosticState(case_id="t")
        state.turn_budget_used = 0
        bundle = self._bundle(3)
        ctrl.account_turn_budget(state, bundle)
        assert state.turn_budget_used == 1

    def test_per_action_counts_each(self):
        ctrl = self._ctrl("per_action")
        state = DiagnosticState(case_id="t")
        state.turn_budget_used = 0
        bundle = self._bundle(3)
        ctrl.account_turn_budget(state, bundle)
        assert state.turn_budget_used == 3

    def test_time_weighted_between_1_and_n(self):
        ctrl = self._ctrl("time_weighted")
        state = DiagnosticState(case_id="t")
        state.turn_budget_used = 0
        bundle = self._bundle(4)
        ctrl.account_turn_budget(state, bundle)
        assert 1 <= state.turn_budget_used <= 4


# ---------------------------------------------------------------------------
# Integration: two branches, two independent actions bundled together
# ---------------------------------------------------------------------------

class TestBundleIntegration:
    def test_independent_branches_get_separate_actions(self):
        """A bundle for two live branches should include one action per branch
        when two independent candidates are available."""
        state = _state({"B1": 0.55, "B2": 0.45})
        config = ControllerConfig(min_marginal_ig_threshold=0.01)
        leaves = [
            _leaf("x1", "B1", "order ECG", leaf_type="ORDER_LAB", ig=0.4, target_branches={"B1": "support"}),
            _leaf("x2", "B2", "ask about fever", leaf_type="ASK_PATIENT", ig=0.3, target_branches={"B2": "support"}),
        ]
        bundle, coverage = build_bundle(leaves, state, config)
        ids_in_bundle = {l.leaf_id for l in bundle}
        assert "x1" in ids_in_bundle
        assert "x2" in ids_in_bundle
        assert len(bundle) >= 2

    def test_no_duplicate_leaf_in_bundle(self):
        state = _state({"B1": 0.6, "B2": 0.4})
        config = ControllerConfig(min_marginal_ig_threshold=0.01)
        leaves = [
            _leaf("a", "B1", "unique query A", target_branches={"B1": "support"}),
            _leaf("b", "B2", "unique query B", target_branches={"B2": "support"}),
            _leaf("c", "B1", "unique query C", target_branches={"B1": "support"}, score=0.5),
        ]
        bundle, _ = build_bundle(leaves, state, config)
        ids = [l.leaf_id for l in bundle]
        assert len(ids) == len(set(ids)), "Duplicate actions detected in bundle"

    def test_regression_single_candidate_bundle(self):
        """When only one candidate is available, bundle has at least 1 entry
        (may include synthetic challenge when dual-channel is active)."""
        state = _state({"B1": 1.0})
        config = ControllerConfig()
        leaves = [_leaf("only", "B1", "any question?")]
        bundle, _ = build_bundle(leaves, state, config)
        assert len(bundle) >= 1
        assert any(l.leaf_id == "only" for l in bundle)


# ---------------------------------------------------------------------------
# Dual-channel bundler (TALP_BUNDLER_REDESIGN_SPEC)
# ---------------------------------------------------------------------------

class TestDualChannelBundler:
    def test_confirm_and_challenge_both_selected(self):
        """Phase 1 + Phase 1b: both confirm and challenge candidates enter bundle."""
        state = _state({"B1": 0.6, "B2": 0.4})
        config = ControllerConfig(
            min_marginal_ig_threshold=0.01,
            use_dual_channel_bundler=True,
        )
        leaves = [
            _leaf("b1_confirm", "B1", "chest pain radiation supports acute coronary syndrome", ig=0.5,
                  target_branches={"B1": "support", "B2": "against"},
                  primary_function="confirm"),
            _leaf("b1_challenge", "B1", "normal troponin argues against acute coronary syndrome", ig=0.4,
                  target_branches={"B1": "against", "B2": "support"},
                  primary_function="challenge", falsification_value=0.6),
            _leaf("b2_confirm", "B2", "fever and productive cough supports pneumonia diagnosis", ig=0.5,
                  target_branches={"B2": "support"},
                  primary_function="confirm"),
            _leaf("b2_challenge", "B2", "clear lung auscultation argues against pneumonia diagnosis", ig=0.3,
                  target_branches={"B2": "against"},
                  primary_function="challenge", falsification_value=0.4),
        ]
        bundle, coverage = build_bundle(leaves, state, config)
        ids = {l.leaf_id for l in bundle}
        assert "b1_confirm" in ids
        assert "b1_challenge" in ids
        assert "b2_confirm" in ids
        assert "b2_challenge" in ids
        assert coverage["B1"]["confirm_status"] == "covered"
        assert coverage["B1"]["challenge_status"] == "covered"
        assert coverage["B2"]["confirm_status"] == "covered"
        assert coverage["B2"]["challenge_status"] == "covered"

    def test_synthetic_challenge_injected_when_missing(self):
        """Phase 2: when leader has no challenge candidate, a synthetic one is injected."""
        state = _state({"B1": 0.7, "B2": 0.3})
        config = ControllerConfig(
            min_marginal_ig_threshold=0.01,
            use_dual_channel_bundler=True,
            leader_challenge_threshold=0.3,
        )
        leaves = [
            _leaf("b1_confirm", "B1", "chest pain radiation supports acute coronary", ig=0.5,
                  target_branches={"B1": "support"},
                  primary_function="confirm"),
            _leaf("b2_confirm", "B2", "fever with productive cough supports pneumonia", ig=0.4,
                  target_branches={"B2": "support"},
                  primary_function="confirm"),
        ]
        bundle, coverage = build_bundle(leaves, state, config)
        synthetic_ids = [l.leaf_id for l in bundle if "synthetic" in l.leaf_id]
        assert len(synthetic_ids) == 1, "Expected one synthetic challenge for leader B1"

    def test_legacy_mode_fallback(self):
        """When use_dual_channel_bundler=False, uses single-channel legacy path."""
        state = _state({"B1": 0.6, "B2": 0.4})
        config = ControllerConfig(
            min_marginal_ig_threshold=0.01,
            use_dual_channel_bundler=False,
        )
        leaves = [
            _leaf("a", "B1", "radiation to arm", target_branches={"B1": "support"}),
            _leaf("b", "B2", "fever onset time", target_branches={"B2": "support"}),
        ]
        bundle, coverage = build_bundle(leaves, state, config)
        assert len(bundle) >= 2
        assert "B1" in coverage
        assert "B2" in coverage

    def test_opposite_direction_not_redundant(self):
        """Confirm and challenge for same branch should not be filtered as redundant."""
        state = _state({"B1": 0.6})
        config = ControllerConfig(
            min_marginal_ig_threshold=0.01,
            use_dual_channel_bundler=True,
            redundancy_similarity_threshold=0.3,
        )
        leaves = [
            _leaf("b1_confirm", "B1", "WBC count elevated supports leukemia diagnosis",
                  ig=0.5, target_branches={"B1": "support"}, primary_function="confirm"),
            _leaf("b1_challenge", "B1", "WBC count elevated argues against leukemia diagnosis",
                  ig=0.4, target_branches={"B1": "against"}, primary_function="challenge",
                  falsification_value=0.5),
        ]
        bundle, _ = build_bundle(leaves, state, config)
        ids = {l.leaf_id for l in bundle}
        assert "b1_confirm" in ids
        assert "b1_challenge" in ids
