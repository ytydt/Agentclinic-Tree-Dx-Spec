"""Guard: main-pipeline OpenRouter direct-POST default output_cap stays 1024.

VignetteParser long-output needs are handled by offline freeze + optional
dedicated probe runs, not by raising the shared production cap.
"""
from __future__ import annotations

from pathlib import Path


def test_direct_post_default_output_cap_is_1024():
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "agentclinic_tree_dx"
        / "llm_client.py"
    ).read_text(encoding="utf-8")
    assert "else 1024" in source
    assert "min(max_tokens, 1024)" in source
    assert "else 4096" not in source
