"""Collapse3c evidence-direction contract (design 9.3 items 1-3 and 5).

Four defects from the frozen-log audit:

- ``contradict_spans`` shipped with no id column, so an against edge could not
  carry polarity, time or specificity anywhere downstream;
- a fact asserted as both support and contradict for one candidate carries zero
  net direction, and the selector still read both strings;
- the candev selector payload dropped every type C1 had captured;
- nothing audited the disputed edge before the selector decided it.

The repairs that are selector-visible are opt-in, matching `strict_identity` and
`enforce_group_quota`: defaults must stay off so every archived arm replays
unchanged, so each test asserts the legacy behaviour as well as the repaired one.
Which side of a direction conflict is clinically right is not decidable offline,
so the contract is withdrawal plus an audit entry, never a guessed repair.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from agentclinic_tree_dx.aphhm_c import (  # noqa: E402
    AphhmCPipeline,
    ConceptNode,
    ConceptRegistry,
    EvidenceLedger,
    ObservedFact,
)

HHV8 = "Negative for human herpesvirus 8 (HHV-8)"
SPINDLE = "spindle cell proliferation with slit-like vascular spaces"
PLAQUES = "violaceous plaques on the lower legs"


def _facts() -> list[ObservedFact]:
    return [
        ObservedFact(
            fact_id="F01",
            raw_span=HHV8,
            polarity="absent",
            specificity="high",
            reliability="high",
        ),
        ObservedFact(
            fact_id="F02",
            raw_span=PLAQUES,
            polarity="present",
            specificity="medium",
            reliability="high",
        ),
        ObservedFact(
            fact_id="F03",
            raw_span=SPINDLE,
            polarity="present",
            specificity="high",
            reliability="high",
        ),
    ]


def _registry(*nodes: ConceptNode) -> ConceptRegistry:
    registry = ConceptRegistry()
    for n in nodes:
        registry.concepts[n.concept_id] = n
    return registry


def _conflicted() -> ConceptNode:
    return ConceptNode(
        concept_id="C01",
        preferred_label="Kaposi sarcoma",
        support_fact_ids=["F01", "F03"],
        support_spans=[HHV8, SPINDLE],
        contradict_spans=[HHV8],
    )


# --------------------------------------------------------------------------
# item 2: bind the against direction, then withdraw only when asked
# --------------------------------------------------------------------------


def test_against_direction_gets_an_id_column_without_any_flag() -> None:
    node = ConceptNode(
        concept_id="C01",
        preferred_label="Kaposi sarcoma",
        support_fact_ids=["F02", "F03"],
        support_spans=[PLAQUES],
        contradict_spans=[HHV8],
    )
    registry = _registry(node)
    report = registry.audit_directions(_facts())
    assert node.contradict_fact_ids == ["F01"]
    assert not registry.direction_quarantine
    assert report["against_citation_closure"] == 1.0
    assert report["citation_closure_gate_0_98"] is True


def test_default_off_reports_the_conflict_but_changes_nothing() -> None:
    """The archived-replay guarantee: a conflict is logged, not withdrawn."""
    node = _conflicted()
    registry = _registry(node)
    report = registry.audit_directions(_facts())

    assert report["self_contradictory_edges"] == 1
    assert report["quarantine_enabled"] is False
    assert report["edges_withdrawn"] == 0
    assert not registry.direction_quarantine
    # every selector-visible field is untouched
    assert node.support_fact_ids == ["F01", "F03"]
    assert node.support_spans == [HHV8, SPINDLE]
    assert node.contradict_spans == [HHV8]
    # the review queue still names it
    assert report["review_queue"]["self_contradictory"][0]["fact_id"] == "F01"


def test_quarantine_withdraws_both_sides_when_enabled() -> None:
    node = _conflicted()
    registry = _registry(node)
    report = registry.audit_directions(_facts(), quarantine=True)

    assert report["edges_withdrawn"] == 1
    assert [r["fact_id"] for r in registry.direction_quarantine] == ["F01"]
    assert node.support_fact_ids == ["F03"]
    assert node.contradict_fact_ids == []
    assert node.contradict_spans == []
    assert node.support_spans == [SPINDLE]
    assert any(e["op"] == "quarantine_direction" for e in registry.events)


def test_unbindable_against_span_is_reported_not_bound() -> None:
    """Containment is not used to bind: it is the tier that conflates objects."""
    node = ConceptNode(
        concept_id="C01",
        preferred_label="Kaposi sarcoma",
        support_fact_ids=["F03"],
        contradict_spans=["human herpesvirus 8"],  # a fragment, not the fact
    )
    registry = _registry(node)
    report = registry.audit_directions(_facts())
    assert node.contradict_fact_ids == []
    assert report["against_spans_bound"] == 0
    assert report["citation_closure_gate_0_98"] is False
    assert not registry.direction_quarantine


def test_conflict_across_two_ingestion_paths_is_still_caught() -> None:
    """Support can arrive under one stance and the contradiction under another."""
    registry = ConceptRegistry()
    registry.add(
        label="Kaposi sarcoma",
        support_fact_ids=["F01"],
        support_spans=[HHV8],
        stance="commit",
    )
    registry.add(label="Kaposi sarcoma", contradict_spans=[HHV8], stance="coverage")
    assert len(registry.concepts) == 1, "same label must merge before the check runs"
    report = registry.audit_directions(_facts(), quarantine=True)
    assert report["edges_withdrawn"] == 1


def test_absent_high_specificity_support_is_a_queue_not_an_error() -> None:
    """Absence can correctly support by exclusion, so it is never auto-repaired."""
    node = ConceptNode(
        concept_id="C01",
        preferred_label="Kaposi sarcoma",
        support_fact_ids=["F01"],
        support_spans=[HHV8],
    )
    registry = _registry(node)
    report = registry.audit_directions(_facts(), quarantine=True)
    assert report["absent_high_specificity_used_as_support"] == 1
    assert node.support_fact_ids == ["F01"], "queued for review, not withdrawn"


# --------------------------------------------------------------------------
# item 5: typed selector cards
# --------------------------------------------------------------------------


def _ledger(node: ConceptNode) -> EvidenceLedger:
    return EvidenceLedger(_facts(), [node])


def test_typed_cards_carry_the_types_c1_already_captured() -> None:
    node = ConceptNode(
        concept_id="C01",
        preferred_label="Kaposi sarcoma",
        support_fact_ids=["F03"],
        support_spans=[SPINDLE],
        contradict_fact_ids=["F01"],
        contradict_spans=[HHV8],
    )
    cards = AphhmCPipeline._fact_cards(
        node.contradict_fact_ids, node.contradict_spans, _ledger(node), 3
    )
    assert cards == [
        {
            "fact_id": "F01",
            "span": HHV8,
            "polarity": "absent",
            "temporality": "current",
            "specificity": "high",
            "reliability": "high",
            "bound": True,
        }
    ]


def test_unbound_span_is_kept_and_marked_rather_than_dropped() -> None:
    node = ConceptNode(concept_id="C01", preferred_label="x")
    cards = AphhmCPipeline._fact_cards([], ["a span no fact backs"], _ledger(node), 3)
    assert cards == [{"span": "a span no fact backs", "bound": False}]


class _SpyLLM:
    """Records the payload the selector was handed."""

    def __init__(self) -> None:
        self.payloads: list[dict] = []

    def call(self, module: str, prompt: str, payload: dict) -> Any:
        self.payloads.append(payload)
        return {"champion": "Kaposi sarcoma"}


def _selector_note(*, typed: bool) -> dict[str, Any]:
    node = ConceptNode(
        concept_id="C01",
        preferred_label="Kaposi sarcoma",
        support_fact_ids=["F03"],
        support_spans=[SPINDLE],
        contradict_fact_ids=["F01"],
        contradict_spans=[HHV8],
    )
    llm = _SpyLLM()
    pipe = AphhmCPipeline(
        llm, mode="c4_selector_candev_nomatrix", typed_selector_cards=typed
    )
    pipe._select_frontier(vignette="v", frontier=[node], ledger=_ledger(node))
    return llm.payloads[0]["candidate_notes"][0]


def test_selector_payload_keeps_raw_strings_when_flag_is_off() -> None:
    note = _selector_note(typed=False)
    assert note["for"] == [SPINDLE]
    assert note["against"] == [HHV8]


def test_selector_payload_carries_typed_cards_when_flag_is_on() -> None:
    note = _selector_note(typed=True)
    assert note["against"][0]["polarity"] == "absent"
    assert note["against"][0]["specificity"] == "high"
    assert note["for"][0]["fact_id"] == "F03"


def test_edge_audit_reaches_the_selector_payload_only_as_a_feature() -> None:
    a, b = _pair()
    llm = _SpyLLM()
    pipe = AphhmCPipeline(
        llm, mode="c4_selector_candev_nomatrix", pair_edge_audit=True
    )
    ledger = EvidenceLedger(_facts(), [a, b])
    audit = pipe._pair_edge_audit_payload(shortlist=[a, b], ranked=[a, b], ledger=ledger)
    pipe._select_frontier(
        vignette="v", frontier=[a, b], ledger=ledger, edge_audit=audit
    )
    payload = llm.payloads[0]
    assert payload["shortlist"] == ["Kaposi sarcoma", "Bacillary angiomatosis"], (
        "the audit must not add or remove a candidate"
    )
    assert "disputed_edge_audit" in payload
    assert "candidate_order_hash" not in payload["disputed_edge_audit"]

    llm2 = _SpyLLM()
    pipe2 = AphhmCPipeline(llm2, mode="c4_selector_candev_nomatrix")
    pipe2._select_frontier(vignette="v", frontier=[a, b], ledger=ledger)
    assert "disputed_edge_audit" not in llm2.payloads[0]


# --------------------------------------------------------------------------
# item 3: pair-edge audit
# --------------------------------------------------------------------------


def _pair() -> tuple[ConceptNode, ConceptNode]:
    a = ConceptNode(
        concept_id="C01",
        preferred_label="Kaposi sarcoma",
        support_fact_ids=["F03"],
        contradict_fact_ids=["F01"],
    )
    b = ConceptNode(
        concept_id="C02",
        preferred_label="Bacillary angiomatosis",
        support_fact_ids=["F02"],
    )
    return a, b


def _audit(pipe: AphhmCPipeline, a: ConceptNode, b: ConceptNode) -> dict[str, Any]:
    ledger = EvidenceLedger(_facts(), [a, b])
    return pipe._pair_edge_audit_payload(shortlist=[a, b], ranked=[a, b], ledger=ledger)


def test_pair_edge_audit_is_off_by_default() -> None:
    assert AphhmCPipeline(None, mode="c4_selector_candev_nomatrix").pair_edge_audit is False


def test_pair_edge_audit_labels_exclusive_discriminators_without_the_matrix() -> None:
    pipe = AphhmCPipeline(
        None, mode="c4_selector_candev_nomatrix", pair_edge_audit=True
    )
    a, b = _pair()
    out = _audit(pipe, a, b)
    # F03 is A's own high-specificity rule-in; F01 opposes A; F02 is B's only
    # support and is not high specificity.
    assert out["a_exclusive_high_specificity"] == ["F03"]
    assert out["b_exclusive_high_specificity"] == []
    assert out["resolvable_on_present_evidence"] is True
    by_id = {c["fact_id"]: c for c in out["edge_cards"]}
    assert by_id["F03"]["relation"] == "favours_a" and by_id["F03"]["role_a"] == "for"
    assert by_id["F01"]["relation"] == "favours_b", "an against on A favours B"
    assert by_id["F01"]["polarity"] == "absent", "cards must carry the type"


def test_a_fact_supporting_both_is_shared_not_a_conflict() -> None:
    """Shared support settles nothing; it must not be reported as a contradiction."""
    pipe = AphhmCPipeline(
        None, mode="c4_selector_candev_nomatrix", pair_edge_audit=True
    )
    a, b = _pair()
    b.support_fact_ids = ["F03"]  # both hold F03 as support
    out = _audit(pipe, a, b)
    by_id = {c["fact_id"]: c for c in out["edge_cards"]}
    assert by_id["F03"]["relation"] == "shared_support"
    assert by_id["F03"]["discriminating"] is False
    assert out["shared_non_discriminating_fact_ids"] == ["F03"]
    assert not out["self_contradictory_fact_ids"]
    # F03 is no longer exclusive to A, so A loses its discriminator
    assert out["a_exclusive_high_specificity"] == []


def test_support_here_against_there_is_a_clean_discriminator() -> None:
    pipe = AphhmCPipeline(
        None, mode="c4_selector_candev_nomatrix", pair_edge_audit=True
    )
    a, b = _pair()
    b.support_fact_ids = ["F02"]
    b.contradict_fact_ids = ["F03"]  # F03 rules A in and B out
    out = _audit(pipe, a, b)
    by_id = {c["fact_id"]: c for c in out["edge_cards"]}
    assert by_id["F03"]["relation"] == "discriminates_a"
    assert by_id["F03"]["discriminating"] is True


def test_pair_edge_audit_flags_an_unresolvable_edge() -> None:
    pipe = AphhmCPipeline(
        None, mode="c4_selector_candev_nomatrix", pair_edge_audit=True
    )
    a, b = _pair()
    a.support_fact_ids = ["F02"]
    a.contradict_fact_ids = []
    b.support_fact_ids = ["F02"]
    out = _audit(pipe, a, b)
    assert (
        out["disputed_reason"]
        == "neither_side_holds_an_exclusive_high_specificity_discriminator"
    )
    assert out["resolvable_on_present_evidence"] is False


def test_pair_edge_audit_surfaces_a_surviving_self_contradiction() -> None:
    """With the quarantine off, the item-2 defect reaches the pair; say so."""
    pipe = AphhmCPipeline(
        None, mode="c4_selector_candev_nomatrix", pair_edge_audit=True
    )
    a, b = _pair()
    b.support_fact_ids = ["F03"]
    b.contradict_fact_ids = ["F03"]  # one candidate, both directions
    out = _audit(pipe, a, b)
    assert out["self_contradictory_fact_ids"] == ["F03"]
    assert out["disputed_reason"] == "self_contradictory_edge_present"
    assert out["resolvable_on_present_evidence"] is False


def test_pair_edge_audit_takes_ranked_order_not_shortlist_order() -> None:
    """`selector_unanchored` re-sorts the shortlist, so entry 0 is not the top."""
    pipe = AphhmCPipeline(
        None, mode="c4_selector_candev_nomatrix", pair_edge_audit=True
    )
    a, b = _pair()
    c = ConceptNode(concept_id="C03", preferred_label="Angiosarcoma")
    ledger = EvidenceLedger(_facts(), [a, b, c])
    out = pipe._pair_edge_audit_payload(
        shortlist=[c, b, a], ranked=[a, b, c], ledger=ledger
    )
    assert (out["candidate_a"], out["candidate_b"]) == (
        "Kaposi sarcoma",
        "Bacillary angiomatosis",
    )
