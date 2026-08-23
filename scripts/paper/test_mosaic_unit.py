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


def test_containment_records_relation_instead_of_folding() -> None:
    """A qualified composite must stay separately addressable from its parent.

    The selector shortlist is built from ``preferred_name`` only, so folding a
    composite into its parent as an alias makes the composite unreachable. This
    is the DA 709 defect.
    """
    reg = GlobalConceptRegistry()
    parent = reg.merge_candidate(
        name="Tuberculosis", view="ax_syndrome", support_ids=["E1"], contradict_ids=[]
    )
    child = reg.merge_candidate(
        name="Disseminated Tuberculosis with Hemophagocytic Lymphohistiocytosis",
        view="ax_modality",
        support_ids=["E2"],
        contradict_ids=[],
    )
    assert child != parent, "containment must not fold the composite into its parent"
    assert parent in reg.concepts[child].narrower_than
    assert child in reg.concepts[parent].broader_than
    # the composite must not have been demoted to an alias
    assert not reg.concepts[parent].aliases
    # and its evidence must not have been absorbed by the parent
    assert reg.concepts[parent].supporting_evidence == ["E1"]
    assert reg.concepts[child].supporting_evidence == ["E2"]


def test_legacy_flag_restores_the_fold_so_archived_arms_can_replay() -> None:
    """The repair is on by default but must stay switchable.

    Without a working legacy path, `safe_identity=False` in a manifest would be
    a claim nothing backs, and the archived Forest/IMPC arms could not be
    reproduced from this code at all.
    """
    reg = GlobalConceptRegistry(safe_identity=False)
    parent = reg.merge_candidate(
        name="Tuberculosis", view="ax_syndrome", support_ids=["E1"], contradict_ids=[]
    )
    child = reg.merge_candidate(
        name="Disseminated Tuberculosis with Hemophagocytic Lymphohistiocytosis",
        view="ax_modality",
        support_ids=["E2"],
        contradict_ids=[],
    )
    assert child == parent, "the legacy predicate folded on containment"
    assert reg.concepts[parent].supporting_evidence == ["E1", "E2"]
    assert not reg.concepts[parent].narrower_than
    assert not reg.merge_audit


def test_exact_and_case_variants_still_merge() -> None:
    """Removing containment must not stop confirmed equivalence from merging."""
    reg = GlobalConceptRegistry()
    cid = reg.merge_candidate(
        name="Schwannoma", view="g1", support_ids=["E1"], contradict_ids=[]
    )
    again = reg.merge_candidate(
        name="  schwannoma ", view="g2", support_ids=["E2"], contradict_ids=[]
    )
    assert again == cid
    assert len(reg.concepts) == 1


def test_split_pair_does_not_evict_a_third_party() -> None:
    """Seating a parent/child pair must not cost an unrelated candidate its slot.

    Without the refund the pool grows past ``main_k + protected_k`` and the
    lowest-scoring incumbent falls off, which is how the safe-identity split used
    to trade one rescue for one loss.
    """
    reg = GlobalConceptRegistry()
    plan = [
        ("Nephrotic Syndrome", 4),
        ("Acute Kidney Injury", 4),
        ("Minimal change disease", 3),
        ("Allopurinol-induced nephropathy", 2),
        ("Hypertension-related kidney disease", 2),
        ("Acute Interstitial Nephritis", 1),
    ]
    for i, (name, n) in enumerate(plan):
        reg.merge_candidate(
            name=name,
            view="ax_syndrome",
            support_ids=[f"{i}E{j}" for j in range(n)],
            contradict_ids=[],
        )
    reg.score()
    incumbents = {c.preferred_name for c in reg.two_lane_frontier(4, 2)}
    assert "Acute Interstitial Nephritis" in incumbents

    # now split a child out of one incumbent, as safe identity does
    reg.merge_candidate(
        name="Sildenafil-induced Acute Kidney Injury",
        view="ax_mechanism",
        support_ids=["XE1", "XE2", "XE3"],
        contradict_ids=[],
    )
    reg.score()
    after = {c.preferred_name for c in reg.two_lane_frontier(4, 2)}
    assert "Sildenafil-induced Acute Kidney Injury" in after
    assert "Acute Kidney Injury" in after, "parent must stay addressable"
    assert "Acute Interstitial Nephritis" in after, "split must not evict a third party"

    # the refund is bounded, not a general widening
    assert len(reg.two_lane_frontier(4, 2, parent_refund_k=0)) <= 6


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
    test_containment_records_relation_instead_of_folding()
    test_legacy_flag_restores_the_fold_so_archived_arms_can_replay()
    test_exact_and_case_variants_still_merge()
    test_split_pair_does_not_evict_a_third_party()
    test_two_lane_frontier()
    print("OK mosaic unit tests")
