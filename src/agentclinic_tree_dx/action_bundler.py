"""FrontierCoverageBundler — dual-channel multi-action bundle constructor.

Implements the redesigned algorithm from TALP_BUNDLER_REDESIGN_SPEC.md §6.
Replaces the single-channel bundler (v1.1) with a confirm + challenge
dual-channel strategy aligned with SNAPPS Step 3.

Algorithm outline
-----------------
Phase 0:  If the top candidate is DIAGNOSIS_READY, return it alone.
Phase 1:  Confirm channel — for each live frontier branch, select the
          highest-scoring candidate whose target_branches[bid] == "support".
Phase 1b: Challenge channel — for each live frontier branch, select the
          highest-scoring candidate whose target_branches[bid] == "against".
Phase 2:  Directional diversity guarantee — if the leading branch has no
          "against" coverage, inject one from the pool or synthesize.
Phase 3:  Cross-branch supplement — add high action_separation_value actions.
Phase 4:  Sort bundle by expected_delay ascending.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .state import CandidateLeaf, DiagnosticState
    from .config import ControllerConfig


_RESULT_DEPENDENT_TYPES: frozenset[str] = frozenset({
    "USE_CALCULATOR",
    "RETRIEVE_KNOWLEDGE",
    "RETRIEVE_EXTERNAL_KNOWLEDGE",
})

_DATA_PRODUCING_TYPES: frozenset[str] = frozenset({
    "ORDER_LAB",
    "ORDER_IMAGING",
    "REQUEST_VITAL",
    "REQUEST_EXAM",
})

_KNOWLEDGE_RETRIEVAL_TYPES: frozenset[str] = frozenset({
    "RETRIEVE_KNOWLEDGE",
    "RETRIEVE_EXTERNAL_KNOWLEDGE",
})


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _normalize(text: str) -> str:
    return " ".join(w for w in text.lower().split() if len(w) > 2)


def _jaccard(s1: str, s2: str) -> float:
    t1 = set(s1.split())
    t2 = set(s2.split())
    if not t1 or not t2:
        return 0.0
    return len(t1 & t2) / len(t1 | t2)


def _get_target_direction(candidate: "CandidateLeaf", branch_id: str) -> str | None:
    """Read the expected impact direction for *branch_id* from target_branches.

    Supports both the new dict format and the legacy list format for
    backward compatibility during migration.
    """
    tb = candidate.target_branches
    if isinstance(tb, dict):
        return tb.get(branch_id)
    if isinstance(tb, list):
        return "support" if branch_id in tb else None
    return None


def _is_dependent(candidate: "CandidateLeaf", bundle: list["CandidateLeaf"]) -> bool:
    if candidate.leaf_type not in _RESULT_DEPENDENT_TYPES:
        return False
    return any(b.leaf_type in _DATA_PRODUCING_TYPES for b in bundle)


def _is_duplicate_knowledge_retrieval(
    candidate: "CandidateLeaf",
    bundle: list["CandidateLeaf"],
) -> bool:
    if candidate.leaf_type not in _KNOWLEDGE_RETRIEVAL_TYPES:
        return False
    return any(b.leaf_type in _KNOWLEDGE_RETRIEVAL_TYPES for b in bundle)


def _same_branch_opposite_direction(a: "CandidateLeaf", b: "CandidateLeaf") -> bool:
    """True when two candidates target the same branch in opposite directions."""
    if a.branch_id != b.branch_id:
        return False
    dir_a = _get_target_direction(a, a.branch_id)
    dir_b = _get_target_direction(b, b.branch_id)
    if dir_a and dir_b and dir_a != dir_b:
        return True
    return False


def _is_redundant(
    candidate: "CandidateLeaf",
    bundle: list["CandidateLeaf"],
    content_set: set[str],
    threshold: float,
) -> bool:
    """Return True if *candidate* is semantically redundant with the bundle.

    Exempts same-branch opposite-direction pairs (confirm vs challenge for the
    same branch naturally share vocabulary but serve different cognitive purposes).
    """
    if candidate.redundancy_group:
        if any(
            b.redundancy_group == candidate.redundancy_group
            for b in bundle
            if b.redundancy_group
        ):
            return True

    norm_c = _normalize(candidate.content)
    for existing in bundle:
        if _same_branch_opposite_direction(candidate, existing):
            continue
        existing_norm = _normalize(existing.content)
        if _jaccard(norm_c, existing_norm) > threshold:
            return True
    return False


def _passes_gates(
    candidate: "CandidateLeaf",
    bundle: list["CandidateLeaf"],
    content_set: set[str],
    config: "ControllerConfig",
    min_ig: float,
) -> bool:
    if _is_dependent(candidate, bundle):
        return False
    if _is_duplicate_knowledge_retrieval(candidate, bundle):
        return False
    if _is_redundant(candidate, bundle, content_set, config.redundancy_similarity_threshold):
        return False
    if candidate.expected_information_gain < min_ig:
        return False
    return True


# ---------------------------------------------------------------------------
# Synthetic challenge constructor
# ---------------------------------------------------------------------------

def _build_synthetic_challenge(leader, default_leaf_type: str = "ANALYZE_VIGNETTE") -> "CandidateLeaf":
    from .state import CandidateLeaf
    return CandidateLeaf(
        leaf_id=f"{leader.id}::synthetic_challenge",
        branch_id=leader.id,
        leaf_type=default_leaf_type,
        content=(
            f"What evidence is MOST INCONSISTENT with "
            f"{leader.label}? Identify the single strongest finding that "
            f"argues against this diagnosis."
        ),
        expected_information_gain=0.4,
        expected_cost=0.0,
        expected_delay=0.0,
        safety_value=0.0,
        action_separation_value=0.0,
        total_score=0.4,
        target_branches={leader.id: "against"},
        primary_function="challenge",
        falsification_value=0.5,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_bundle(
    candidate_leaves: list["CandidateLeaf"],
    state: "DiagnosticState",
    config: "ControllerConfig",
) -> tuple[list["CandidateLeaf"], dict[str, dict]]:
    """Construct the action bundle for the current turn.

    When config.use_dual_channel_bundler is True (default), uses the
    confirm + challenge dual-channel algorithm.  Otherwise falls back to
    the legacy single-channel Phase 1.
    """
    if not candidate_leaves:
        return [], {}

    if config.use_dual_channel_bundler:
        return _build_dual_channel(candidate_leaves, state, config)
    return _build_legacy(candidate_leaves, state, config)


def _build_dual_channel(
    candidate_leaves: list["CandidateLeaf"],
    state: "DiagnosticState",
    config: "ControllerConfig",
) -> tuple[list["CandidateLeaf"], dict[str, dict]]:

    # ── Phase 0: termination short-circuit ─────────────────────────────────
    if candidate_leaves[0].leaf_type == "DIAGNOSIS_READY":
        return [candidate_leaves[0]], {}

    min_ig = config.min_marginal_ig_threshold
    bundle: list["CandidateLeaf"] = []
    content_set: set[str] = set()
    confirm_covered: dict[str, "CandidateLeaf"] = {}
    challenge_covered: dict[str, "CandidateLeaf"] = {}

    # ── Phase 1: confirm channel ───────────────────────────────────────────
    for branch_id in state.frontier:
        branch = state.branches.get(branch_id)
        if branch is None or branch.status not in ("live", "reopened"):
            continue
        for candidate in candidate_leaves:
            if candidate.branch_id != branch_id:
                continue
            if _get_target_direction(candidate, branch_id) != "support":
                continue
            if not _passes_gates(candidate, bundle, content_set, config, min_ig):
                continue
            confirm_covered[branch_id] = candidate
            bundle.append(candidate)
            content_set.add(_normalize(candidate.content))
            break

    # ── Phase 1b: challenge channel ────────────────────────────────────────
    for branch_id in state.frontier:
        branch = state.branches.get(branch_id)
        if branch is None or branch.status not in ("live", "reopened"):
            continue
        for candidate in candidate_leaves:
            if candidate.branch_id != branch_id:
                continue
            if _get_target_direction(candidate, branch_id) != "against":
                continue
            if not _passes_gates(candidate, bundle, content_set, config, min_ig):
                continue
            challenge_covered[branch_id] = candidate
            bundle.append(candidate)
            content_set.add(_normalize(candidate.content))
            break

    # ── Phase 2: directional diversity guarantee ───────────────────────────
    live_branches = [
        b for b in state.branches.values()
        if b.status in ("live", "reopened")
    ]
    if live_branches:
        leader = max(live_branches, key=lambda b: b.posterior)
        threshold = config.leader_challenge_threshold
        if leader.posterior >= threshold and leader.id not in challenge_covered:
            for candidate in candidate_leaves:
                if candidate in bundle:
                    continue
                if _get_target_direction(candidate, leader.id) != "against":
                    continue
                if _passes_gates(candidate, bundle, content_set, config, min_ig):
                    bundle.append(candidate)
                    content_set.add(_normalize(candidate.content))
                    challenge_covered[leader.id] = candidate
                    break
            if leader.id not in challenge_covered:
                dominant_type = candidate_leaves[0].leaf_type if candidate_leaves else "ANALYZE_VIGNETTE"
                synthetic = _build_synthetic_challenge(leader, default_leaf_type=dominant_type)
                bundle.append(synthetic)
                challenge_covered[leader.id] = synthetic

    # ── Phase 3: cross-branch supplement ───────────────────────────────────
    sep_threshold = config.min_separation_value_for_supplement
    sorted_by_sep = sorted(
        candidate_leaves,
        key=lambda c: c.action_separation_value,
        reverse=True,
    )
    for candidate in sorted_by_sep:
        if candidate in bundle:
            continue
        if candidate.action_separation_value < sep_threshold:
            break
        if not _passes_gates(candidate, bundle, content_set, config, min_ig):
            continue
        bundle.append(candidate)
        content_set.add(_normalize(candidate.content))

    # ── Phase 4: sort by expected delay ────────────────────────────────────
    bundle.sort(key=lambda a: a.expected_delay)

    # ── Build coverage audit ───────────────────────────────────────────────
    branch_coverage = _build_dual_coverage_audit(
        state, confirm_covered, challenge_covered, candidate_leaves, min_ig
    )
    return bundle, branch_coverage


# ---------------------------------------------------------------------------
# Legacy single-channel builder (fallback when use_dual_channel_bundler=False)
# ---------------------------------------------------------------------------

def _build_legacy(
    candidate_leaves: list["CandidateLeaf"],
    state: "DiagnosticState",
    config: "ControllerConfig",
) -> tuple[list["CandidateLeaf"], dict[str, dict]]:

    if candidate_leaves[0].leaf_type == "DIAGNOSIS_READY":
        return [candidate_leaves[0]], {}

    min_ig = config.min_marginal_ig_threshold
    bundle: list["CandidateLeaf"] = []
    content_set: set[str] = set()
    covered: dict[str, "CandidateLeaf"] = {}

    for branch_id in state.frontier:
        branch = state.branches.get(branch_id)
        if branch is None or branch.status not in ("live", "reopened"):
            continue
        for candidate in candidate_leaves:
            if candidate.branch_id != branch_id:
                continue
            if not _passes_gates(candidate, bundle, content_set, config, min_ig):
                continue
            covered[branch_id] = candidate
            bundle.append(candidate)
            content_set.add(_normalize(candidate.content))
            break

    live_branches = [
        b for b in state.branches.values()
        if b.status in ("live", "reopened")
    ]
    if live_branches:
        leader = max(live_branches, key=lambda b: b.posterior)
        if leader.posterior >= 0.5:
            has_falsifier = any(
                candidate.primary_function in ("falsify", "challenge")
                and _get_target_direction(candidate, leader.id) == "against"
                for candidate in bundle
            )
            if not has_falsifier:
                for candidate in candidate_leaves:
                    if candidate in bundle:
                        continue
                    if candidate.primary_function not in ("falsify", "challenge"):
                        continue
                    if _get_target_direction(candidate, leader.id) != "against":
                        continue
                    if _passes_gates(candidate, bundle, content_set, config, min_ig):
                        bundle.append(candidate)
                        content_set.add(_normalize(candidate.content))
                        break

    uncovered = [
        bid for bid in state.frontier
        if bid not in covered
        and state.branches.get(bid) is not None
        and state.branches[bid].status in ("live", "reopened")
    ]
    for bid in uncovered:
        for candidate in candidate_leaves:
            if candidate in bundle:
                continue
            if _get_target_direction(candidate, bid) is None:
                continue
            if not _passes_gates(candidate, bundle, content_set, config, min_ig):
                continue
            bundle.append(candidate)
            content_set.add(_normalize(candidate.content))
            covered[bid] = candidate
            break

    sep_threshold = config.min_separation_value_for_supplement
    sorted_by_sep = sorted(
        candidate_leaves,
        key=lambda c: c.action_separation_value,
        reverse=True,
    )
    for candidate in sorted_by_sep:
        if candidate in bundle:
            continue
        if candidate.action_separation_value < sep_threshold:
            break
        if not _passes_gates(candidate, bundle, content_set, config, min_ig):
            continue
        bundle.append(candidate)
        content_set.add(_normalize(candidate.content))

    bundle.sort(key=lambda a: a.expected_delay)

    branch_coverage: dict[str, dict] = {}
    for branch_id in state.frontier:
        branch = state.branches.get(branch_id)
        if branch is None:
            continue
        if branch_id in covered:
            action = covered[branch_id]
            branch_coverage[branch_id] = {
                "status": "covered",
                "selected_action_contents": [action.content],
                "coverage_mode": _infer_coverage_mode(action, branch_id),
                "deferral_reason": None,
            }
        else:
            branch_coverage[branch_id] = {
                "status": "deferred",
                "selected_action_contents": [],
                "coverage_mode": "justified_deferral",
                "deferral_reason": _deferral_reason_simple(branch_id, state, candidate_leaves, min_ig),
            }
    return bundle, branch_coverage


# ---------------------------------------------------------------------------
# Coverage audit helpers
# ---------------------------------------------------------------------------

def _build_dual_coverage_audit(
    state: "DiagnosticState",
    confirm_covered: dict[str, "CandidateLeaf"],
    challenge_covered: dict[str, "CandidateLeaf"],
    candidates: list["CandidateLeaf"],
    min_ig: float,
) -> dict[str, dict]:
    audit: dict[str, dict] = {}
    for branch_id in state.frontier:
        branch = state.branches.get(branch_id)
        if branch is None:
            continue
        audit[branch_id] = {
            "confirm_status": "covered" if branch_id in confirm_covered else "deferred",
            "challenge_status": "covered" if branch_id in challenge_covered else "deferred",
            "confirm_content": confirm_covered[branch_id].content if branch_id in confirm_covered else None,
            "challenge_content": challenge_covered[branch_id].content if branch_id in challenge_covered else None,
        }
    return audit


def _infer_coverage_mode(action: "CandidateLeaf", branch_id: str) -> str:
    if action.primary_function == "safety_ensure":
        return "safety_sentinel"
    tb = action.target_branches
    if isinstance(tb, dict) and len(tb) > 1:
        return "shared"
    if isinstance(tb, list) and len(tb) > 1:
        return "shared"
    return "direct"


def _deferral_reason_simple(
    branch_id: str,
    state: "DiagnosticState",
    candidates: list["CandidateLeaf"],
    min_ig: float,
) -> str:
    branch = state.branches.get(branch_id)
    if branch is None:
        return "branch not found in state"
    if branch.posterior < 0.05:
        return (
            f"posterior {branch.posterior:.2f} below testing threshold (0.05); "
            f"reopen triggers: {branch.reopen_triggers or 'none specified'}"
        )
    all_ig_low = all(
        c.expected_information_gain < min_ig
        for c in candidates
        if c.branch_id == branch_id
    )
    if all_ig_low:
        return "all available candidates for this branch have information gain below threshold"
    already_asked = {a.get("content", "") for a in state.actions_taken}
    all_asked = all(
        c.content in already_asked
        for c in candidates
        if c.branch_id == branch_id
    )
    if all_asked:
        return "all discriminating actions for this branch have already been taken"
    return "coverage deferred due to dependency or redundancy constraints"
