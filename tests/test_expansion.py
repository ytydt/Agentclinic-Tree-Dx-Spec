"""Unit + integration tests for multi-level tree expansion.

Covers requirements from MULTI_LEVEL_EXPANSION_DESIGN.md §13 (Step 6):
  - ExpansionGate hard constraints and ALLOW conditions
  - initialize_child_posteriors probability normalisation
  - recompute_parent_posteriors bottom-up aggregation
  - allow_depth_4 flag correctly raises depth ceiling
  - Regression: max_tree_depth=1 blocks all expansion
"""
from __future__ import annotations

import pytest

from agentclinic_tree_dx.config import ControllerConfig
from agentclinic_tree_dx.controller import AgentClinicTreeController
from agentclinic_tree_dx.state import Branch, DiagnosticState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_branch(
    bid: str,
    *,
    level: int = 1,
    posterior: float = 0.5,
    danger: float = 0.0,
    status: str = "live",
    expand_score: float = 0.6,
    classification_axis: str = "mechanism",
    diagnosis_commitment_gain: float = 0.8,
    turn_cost_to_refine: float = 1.0,
    askable_discriminators: list[str] | None = None,
    requestable_discriminators: list[str] | None = None,
    children: list[str] | None = None,
) -> Branch:
    b = Branch(
        id=bid,
        label=f"Branch {bid}",
        parent="",
        level=level,
        status=status,
        prior=posterior,
        posterior=posterior,
        danger=danger,
        actionability=0.0,
        explanatory_coverage=0.0,
        expand_score=expand_score,
        classification_axis=classification_axis,
        diagnosis_commitment_gain=diagnosis_commitment_gain,
        turn_cost_to_refine=turn_cost_to_refine,
        askable_discriminators=askable_discriminators or ["Q1"],
        requestable_discriminators=requestable_discriminators or [],
    )
    b.children = children or []
    return b


def _controller(config: ControllerConfig | None = None):
    from agentclinic_tree_dx.adapters.mock_env import MockAgentClinicEnv
    env = MockAgentClinicEnv(module_responses={})
    return AgentClinicTreeController(env, config=config)


def _state_with_branches(*branches: Branch) -> DiagnosticState:
    state = DiagnosticState(case_id="test")
    state.max_tree_depth = 3
    state.actions_taken = []
    for b in branches:
        state.branches[b.id] = b
    state.frontier = [b.id for b in branches if b.status in {"live", "reopened"}]
    return state


# ---------------------------------------------------------------------------
# ExpansionGate — hard constraints
# ---------------------------------------------------------------------------

class TestExpansionGateHardConstraints:
    def test_blocks_at_max_depth(self):
        """A branch at max_tree_depth=3 must not expand (level >= max)."""
        ctrl = _controller(ControllerConfig(max_tree_depth=3))
        b = _make_branch("B1", level=3, posterior=0.8, expand_score=1.0)
        state = _state_with_branches(b)
        assert ctrl._passes_expansion_gate(b, state) is False

    def test_blocks_confirmed_branch(self):
        ctrl = _controller()
        b = _make_branch("B1", level=1, status="confirmed", posterior=0.8)
        state = _state_with_branches(b)
        assert ctrl._passes_expansion_gate(b, state) is False

    def test_blocks_low_posterior(self):
        ctrl = _controller(ControllerConfig(test_threshold=0.05))
        b = _make_branch("B1", level=1, posterior=0.03)
        state = _state_with_branches(b)
        assert ctrl._passes_expansion_gate(b, state) is False

    def test_blocks_already_has_children(self):
        ctrl = _controller()
        b = _make_branch("B1", level=1, posterior=0.8, children=["B1.1"])
        state = _state_with_branches(b)
        assert ctrl._passes_expansion_gate(b, state) is False


class TestExpansionGateAllowConditions:
    def test_danger_overrides_action_diff(self):
        """High-danger branch should be allowed even if action_diff is low."""
        ctrl = _controller(ControllerConfig(min_action_diff_to_expand=0.9))
        b = _make_branch(
            "B1",
            level=1,
            posterior=0.6,
            danger=0.8,
            diagnosis_commitment_gain=0.1,  # low → action_diff fails
        )
        state = _state_with_branches(b)
        assert ctrl._passes_expansion_gate(b, state) is True

    def test_unresolved_discriminator_allows(self):
        """Unresolved discriminator satisfies ALLOW condition (C)."""
        ctrl = _controller()
        b = _make_branch(
            "B1",
            level=1,
            posterior=0.6,
            danger=0.0,
            diagnosis_commitment_gain=0.0,  # action_diff fails
            askable_discriminators=["What is the character of the pain?"],
        )
        state = _state_with_branches(b)
        assert ctrl._passes_expansion_gate(b, state) is True

    def test_resolved_discriminators_does_not_allow_alone(self):
        """If all discriminators are already asked, condition C fails."""
        ctrl = _controller(ControllerConfig(min_action_diff_to_expand=0.9))
        q = "What is the character?"
        b = _make_branch(
            "B1",
            level=1,
            posterior=0.6,
            danger=0.0,
            diagnosis_commitment_gain=0.0,
            askable_discriminators=[q],
        )
        state = _state_with_branches(b)
        state.actions_taken = [{"content": q}]
        assert ctrl._passes_expansion_gate(b, state) is False


# ---------------------------------------------------------------------------
# allow_depth_4 flag
# ---------------------------------------------------------------------------

class TestAllowDepth4:
    def test_depth4_blocked_by_default(self):
        """With allow_depth_4=False and max_tree_depth=3, level-3 branch cannot expand."""
        ctrl = _controller(ControllerConfig(max_tree_depth=3, allow_depth_4=False))
        b = _make_branch("B1", level=3, posterior=0.8, expand_score=1.0)
        state = _state_with_branches(b)
        assert ctrl._passes_expansion_gate(b, state) is False

    def test_depth4_allowed_when_flag_set(self):
        """With allow_depth_4=True, level-3 branch may expand (level < 4)."""
        ctrl = _controller(ControllerConfig(max_tree_depth=3, allow_depth_4=True))
        b = _make_branch(
            "B1",
            level=3,
            posterior=0.8,
            expand_score=1.0,
            danger=0.9,  # triggers ALLOW condition
        )
        state = _state_with_branches(b)
        assert ctrl._passes_expansion_gate(b, state) is True


# ---------------------------------------------------------------------------
# initialize_child_posteriors
# ---------------------------------------------------------------------------

class TestInitializeChildPosteriors:
    def test_posteriors_sum_to_original_parent_mass(self):
        """Children's posteriors must sum to the parent's original posterior mass."""
        ctrl = _controller()
        parent = _make_branch("P", level=1, posterior=0.6)
        children = [
            _make_branch("C1", level=2, posterior=0.6),
            _make_branch("C2", level=2, posterior=0.4),
        ]
        original_parent_mass = parent.posterior
        ctrl.initialize_child_posteriors(parent, children)
        total = sum(c.posterior for c in children)
        # Parent is zeroed after expansion (becomes container node)
        assert parent.posterior == 0.0
        assert parent.status == "expanded"
        assert abs(total - original_parent_mass) < 1e-9

    def test_uniform_when_priors_equal(self):
        ctrl = _controller()
        parent = _make_branch("P", level=1, posterior=0.8)
        children = [_make_branch(f"C{i}", level=2, posterior=0.5) for i in range(4)]
        ctrl.initialize_child_posteriors(parent, children)
        expected = 0.8 / 4
        for c in children:
            assert abs(c.posterior - expected) < 1e-9

    def test_proportional_to_prior_estimate(self):
        ctrl = _controller()
        parent = _make_branch("P", level=1, posterior=1.0)
        c1 = _make_branch("C1", level=2, posterior=0.0)
        c1.prior = 0.3
        c2 = _make_branch("C2", level=2, posterior=0.0)
        c2.prior = 0.7
        ctrl.initialize_child_posteriors(parent, [c1, c2])
        assert abs(c1.posterior - 0.3) < 1e-9
        assert abs(c2.posterior - 0.7) < 1e-9


# ---------------------------------------------------------------------------
# recompute_parent_posteriors
# ---------------------------------------------------------------------------

class TestRecomputeParentPosteriors:
    def test_parent_equals_sum_of_children(self):
        ctrl = _controller()
        parent = _make_branch("P", level=1, posterior=0.99, status="expanded",
                               children=["C1", "C2"])
        c1 = _make_branch("C1", level=2, posterior=0.35)
        c1.parent = "P"
        c2 = _make_branch("C2", level=2, posterior=0.25)
        c2.parent = "P"
        state = _state_with_branches(parent, c1, c2)

        ctrl.recompute_parent_posteriors(state)

        assert abs(state.branches["P"].posterior - 0.60) < 1e-9

    def test_no_change_for_leaf_branches(self):
        ctrl = _controller()
        b1 = _make_branch("B1", level=1, posterior=0.4)
        b2 = _make_branch("B2", level=1, posterior=0.6)
        state = _state_with_branches(b1, b2)

        ctrl.recompute_parent_posteriors(state)

        assert abs(state.branches["B1"].posterior - 0.4) < 1e-9
        assert abs(state.branches["B2"].posterior - 0.6) < 1e-9


# ---------------------------------------------------------------------------
# Regression: max_tree_depth=1 blocks all expansion
# ---------------------------------------------------------------------------

class TestMaxDepth1Regression:
    def test_no_expansion_when_depth_1(self):
        ctrl = _controller(ControllerConfig(max_tree_depth=1))
        b = _make_branch(
            "B1",
            level=1,
            posterior=0.9,
            danger=0.9,
            expand_score=1.0,
        )
        state = _state_with_branches(b)
        assert ctrl._passes_expansion_gate(b, state) is False
