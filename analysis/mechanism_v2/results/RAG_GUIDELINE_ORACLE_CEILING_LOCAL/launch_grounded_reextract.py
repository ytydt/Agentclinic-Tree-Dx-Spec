#!/usr/bin/env python3
"""Launcher: grounded re-extract with fast-fail on length truncations."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from agentclinic_tree_dx import llm_client as lc
import run_trial_extraction as r

_orig = lc.RobustLLMClient.get_robust_completion


def _patched(self, messages, description="completion", min_length=None,
             max_retries=None, temperature=None):
    max_retries = 2 if max_retries is None else min(int(max_retries), 2)
    return _orig(
        self, messages, description=description, min_length=min_length,
        max_retries=max_retries, temperature=temperature,
    )


lc.RobustLLMClient.get_robust_completion = _patched

_orig_gcm = lc.RobustLLMClient.get_completion_from_messages


def _gcm(self, *a, **k):
    try:
        return _orig_gcm(self, *a, **k)
    except RuntimeError as e:
        msg = str(e).lower()
        if (
            "did not finish" in msg
            or "finish_reason" in msg
            or "failed after" in msg
        ):
            raise RuntimeError(
                f"token limit / context length (mapped from: {e})"
            ) from e
        raise


lc.RobustLLMClient.get_completion_from_messages = _gcm

sys.argv = [
    "run_trial_extraction.py",
    "--arm", "k30",
    "--tasks", "trial_tasks_11_all4.json",
    "--groups",
    "--strip-options",
    "--grounded",
    "--out-tag", "_grounded",
    "--workers", "24",
]
raise SystemExit(r.main())
