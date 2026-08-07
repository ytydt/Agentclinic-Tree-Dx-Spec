"""Dual-Inf adapter for DiagnosisArena paper baselines.

Runtime path (default): multi-module Dual-Inf on the shared
``RobustLLMClient`` backbone in ``scripts/paper/baseline_arms.run_b04``:

1. Forward inference (diagnoses → support reasons)
2. Backward inference (diagnoses → representative manifestations)
3. Examination (filter/supplement supports; confidence by support count)
4. Optional self-reflection when any diagnosis has ≤β supports

This matches betterzhou/Dual-Inf module roles while using the project model
only (no private tools or KB).

Optional: clone upstream into ``baselines/dual_inf/upstream`` at commit
``a8ea4a954479e38f318ae8a871192c4daa2b26ec`` for prompt cross-check.
"""
from __future__ import annotations

UPSTREAM_URL = "https://github.com/betterzhou/Dual-Inf"
PINNED_COMMIT = "a8ea4a954479e38f318ae8a871192c4daa2b26ec"
