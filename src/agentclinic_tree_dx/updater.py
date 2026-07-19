from __future__ import annotations

from typing import Any, Callable

from .state import Branch

ORDINAL_WEIGHTS = {
    "strong_for": 3.0,
    "moderate_for": 1.8,
    "weak_for": 1.2,
    "neutral": 1.0,
    "weak_against": 0.8,
    "moderate_against": 0.5,
    "strong_against": 0.2,
}

# §13 discrimination gate: labels that make a turn genuinely "discriminative".
_DISCRIMINATIVE_LABELS = {
    "strong_for", "moderate_for", "strong_against", "moderate_against",
}


def normalize(raw_scores: dict[str, float]) -> dict[str, float]:
    total = sum(raw_scores.values())
    if total <= 0:
        n = len(raw_scores)
        return {k: 1.0 / n for k in raw_scores} if n else {}
    return {k: v / total for k, v in raw_scores.items()}


def _is_discriminative_effects(effects: dict[str, str]) -> bool:
    """True if at least one branch carries a moderate/strong (dis)confirming
    label — i.e. the turn genuinely separates hypotheses."""
    return any(lab in _DISCRIMINATIVE_LABELS for lab in effects.values())


def ordinal_update(
    branches: dict[str, Branch],
    annotation: dict,
    weights: dict[str, float] | None = None,
    gate: bool = False,
) -> dict[str, float]:
    """Update branch posteriors using ordinal evidence-weight multiplication.

    §13 discrimination gate (``gate=True``, opt-in): a turn whose effects are
    ENTIRELY non-discriminative (only neutral / weak_for / weak_against) is
    FROZEN — posteriors are returned unchanged. Rationale: with softmax-style
    renormalization, a lone ``weak_for`` on one distractor silently bleeds every
    other family (incl. a broad correct one that is merely ``neutral`` this
    turn) even though NOTHING argued against it (see the down-weight root cause).
    Freezing non-discriminative turns stops that dilution while leaving every
    genuinely discriminative turn (≥1 moderate/strong label) fully intact.
    Default OFF → byte-identical legacy behaviour."""
    weights = weights or ORDINAL_WEIGHTS
    effects = annotation.get("branch_effects", {})
    if gate and effects and not _is_discriminative_effects(effects):
        return normalize({bid: max(b.posterior, 1e-6) for bid, b in branches.items()})
    raw: dict[str, float] = {}
    for bid, branch in branches.items():
        label = effects.get(bid, "neutral")
        weight = weights.get(label, 1.0)
        raw[bid] = max(branch.posterior, 1e-6) * weight
    return normalize(raw)


# §13 gate band for the numeric-LR path: LRs inside [1/1.5, 1.5] are treated as
# non-discriminative (mild) for the freeze decision.
_LR_GATE_LO = 1.0 / 1.5
_LR_GATE_HI = 1.5


def bayesian_lr_update(
    branches: dict[str, Branch],
    branch_lr: dict[str, float],
    gate: bool = False,
) -> dict[str, float]:
    """Update branch posteriors via Bayes' rule using per-branch numeric LRs.

        posterior_odds_i = prior_odds_i * LR_i        (LR=1.0 when unknown)
        posterior_i      = odds_i / (1 + odds_i)       → then renormalize

    Branches without an LR entry are treated as LR=1.0 (no movement) so that
    a single annotated finding only moves the branches it actually bears on.

    §13 discrimination gate (``gate=True``, opt-in): freeze the turn when EVERY
    supplied LR is mild (within ``[1/1.5, 1.5]``) so a near-1 LR on a distractor
    does not dilute a broad correct family via renormalization. Default OFF."""
    if gate and branch_lr:
        vals = [v for v in branch_lr.values() if v and v > 0]
        if vals and all(_LR_GATE_LO <= v <= _LR_GATE_HI for v in vals):
            return normalize({bid: min(max(b.posterior, 1e-6), 1 - 1e-6)
                              for bid, b in branches.items()})
    raw: dict[str, float] = {}
    for bid, branch in branches.items():
        p = min(max(branch.posterior, 1e-6), 1 - 1e-6)
        odds = p / (1 - p)
        lr = branch_lr.get(bid, 1.0)
        if lr is None or lr <= 0:
            lr = 1.0
        post_odds = odds * lr
        raw[bid] = post_odds / (1 + post_odds)
    return normalize(raw)


def calculator_update(
    branches: dict[str, Branch],
    annotation: dict,
    calculator_result: dict[str, Any] | None = None,
    gate: bool = False,
) -> dict[str, float]:
    """Update branch posteriors using numeric LRs when available (F2).

    Priority:
      1. `annotation["branch_lr"]` — per-branch numeric LRs injected by the
         KB-direction reconciliation step (controller F1) → Bayesian update.
      2. `calculator_result["branch_lr"]` — from a clinical calculator router.
      3. Fall back to the ordinal band update.

    ``gate`` (§13) forwards the discrimination gate to whichever path runs.
    """
    branch_lr = annotation.get("branch_lr")
    if not branch_lr and isinstance(calculator_result, dict):
        branch_lr = calculator_result.get("branch_lr")
    if branch_lr:
        return bayesian_lr_update(branches, branch_lr, gate=gate)
    return ordinal_update(branches, annotation, gate=gate)


def rule_based_update(
    branches: dict[str, Branch],
    annotation: dict,
    rule_fn: Callable[[dict[str, Branch], dict], dict[str, float]] | None = None,
) -> dict[str, float]:
    """Update branch posteriors using a formal benchmark or environment rule.

    Abstract path: a real implementation would invoke rule_fn (supplied by the
    benchmark environment) which encodes explicit interpretation logic.
    Falls back to ordinal update until a real rule function is supplied.
    """
    if rule_fn is not None:
        return rule_fn(branches, annotation)
    return ordinal_update(branches, annotation)
