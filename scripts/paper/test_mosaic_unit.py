#!/usr/bin/env python3
"""Unit checks for MOSAIC structural guarantees (no LLM)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from agentclinic_tree_dx.mosaic import GlobalConceptRegistry  # noqa: E402


def test_no_exact_duplicates() -> None:
    reg = GlobalConceptRegistry()
    reg.merge_candidate(name="CPVT", view="g1", support_ids=["E1"], contradict_ids=[])
    reg.merge_candidate(
        name="Catecholaminergic polymorphic ventricular tachycardia",
        view="g2",
        support_ids=["E2"],
        contradict_ids=[],
    )
    # substring / containment may merge; if not, still at most one preferred per norm after score
    reg.merge_candidate(name="CPVT", view="g1", support_ids=["E3"], contradict_ids=[])
    assert reg.exact_duplicate_count() == 0
    # CPVT should have merged into one concept
    assert len(reg.concepts) <= 2


def test_monotone_merge_keeps_evidence() -> None:
    reg = GlobalConceptRegistry()
    cid = reg.merge_candidate(
        name="Schwannoma", view="g1", support_ids=["E1"], contradict_ids=[]
    )
    reg.merge_candidate(
        name="schwannoma", view="g2", support_ids=["E2"], contradict_ids=["E9"]
    )
    c = reg.concepts[cid]
    assert "E1" in c.supporting_evidence and "E2" in c.supporting_evidence
    assert "E9" in c.contradicting_evidence
    assert set(c.generator_views) == {"g1", "g2"}


def test_two_lane_frontier() -> None:
    reg = GlobalConceptRegistry()
    for i, name in enumerate(["A", "B", "C", "D", "E", "RareZebra"]):
        reg.merge_candidate(
            name=name,
            view="g1" if i < 3 else "g2",
            support_ids=[f"E{i}"],
            contradict_ids=[],
            protected_reason="high-specificity" if name == "RareZebra" else "",
        )
    reg.score()
    frontier = reg.two_lane_frontier(main_k=4, protected_k=2)
    assert 4 <= len(frontier) <= 6
    names = {c.preferred_name for c in frontier}
    assert "RareZebra" in names


if __name__ == "__main__":
    test_no_exact_duplicates()
    test_monotone_merge_keeps_evidence()
    test_two_lane_frontier()
    print("OK mosaic unit tests")
