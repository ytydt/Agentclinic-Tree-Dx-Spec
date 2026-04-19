from __future__ import annotations

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


def normalize(raw_scores: dict[str, float]) -> dict[str, float]:
    total = sum(raw_scores.values())
    if total <= 0:
        n = len(raw_scores)
        return {k: 1.0 / n for k in raw_scores} if n else {}
    return {k: v / total for k, v in raw_scores.items()}


def ordinal_update(
    branches: dict[str, Branch],
    annotation: dict,
    weights: dict[str, float] | None = None,
) -> dict[str, float]:
    weights = weights or ORDINAL_WEIGHTS
    raw: dict[str, float] = {}
    effects = annotation.get("branch_effects", {})
    for bid, branch in branches.items():
        label = effects.get(bid, "neutral")
        weight = weights.get(label, 1.0)
        raw[bid] = max(branch.posterior, 1e-6) * weight
    return normalize(raw)
