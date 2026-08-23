"""Selector presentation order as an isolated variable (ORDER_COUNTERFACTUAL_V1).

`selector_unanchored` was added to remove the score anchor and presents the
shortlist `sorted(key=concept_id)` so that it "carries no ranking" -- but
concept_id order *is* generation order, and on the frozen 800 the selector's
champion sits at pool index 0 in 71.0% of cases against a width-weighted uniform
expectation of 19.2%.

The re-analysis of the archived R6 X4 probe (`cf_order_stability.py`) shows that
concentration is **not** causal: under permutation the index-0 rate falls to
0.19/0.24, i.e. to chance, so the selector keeps its candidate wherever it sits.
The arm is kept anyway because it is the only instrument that can re-check this on
a slice R6 never probed, and because the default must provably stay put.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from agentclinic_tree_dx.aphhm_c import (  # noqa: E402
    SELECTOR_ORDERS,
    AphhmCPipeline,
    ConceptNode,
)


def _pipe(order: str) -> AphhmCPipeline:
    return AphhmCPipeline(
        None, mode="c4_selector_candev_nomatrix", selector_order=order
    )


def _nodes(n: int = 5) -> list[ConceptNode]:
    return [
        ConceptNode(concept_id=f"C{i:02d}", preferred_label=f"Dx {i}")
        for i in range(1, n + 1)
    ]


def test_generation_is_the_default_and_is_a_no_op() -> None:
    pipe = _pipe("generation")
    assert pipe.selector_order == "generation"
    assert AphhmCPipeline(None, mode="c4_selector_candev_nomatrix").selector_order == (
        "generation"
    )
    nodes = _nodes()
    assert pipe._order_shortlist(nodes, case_id="c1") == nodes


def test_reverse_is_a_total_reversal() -> None:
    nodes = _nodes()
    got = _pipe("reverse")._order_shortlist(nodes, case_id="c1")
    assert [c.concept_id for c in got] == ["C05", "C04", "C03", "C02", "C01"]


def test_permutation_is_deterministic_and_keyed_on_the_case() -> None:
    nodes = _nodes()
    pipe = _pipe("permuted")
    a = [c.concept_id for c in pipe._order_shortlist(nodes, case_id="A")]
    b = [c.concept_id for c in pipe._order_shortlist(nodes, case_id="A")]
    c = [c.concept_id for c in pipe._order_shortlist(nodes, case_id="B")]
    assert a == b, "must be reproducible from the manifest"
    assert a != c, "must not be the same permutation for every case"


def test_permutation_ignores_labels_so_it_carries_no_candidate_information() -> None:
    """Keyed on concept_id only: renaming a candidate must not move it."""
    pipe = _pipe("permuted")
    base = _nodes()
    renamed = _nodes()
    for node in renamed:
        node.preferred_label = f"zzz {node.concept_id}"
    assert [c.concept_id for c in pipe._order_shortlist(base, case_id="k")] == [
        c.concept_id for c in pipe._order_shortlist(renamed, case_id="k")
    ]


@pytest.mark.parametrize("order", SELECTOR_ORDERS)
def test_every_arm_preserves_the_candidate_set_exactly(order: str) -> None:
    nodes = _nodes(6)
    got = _pipe(order)._order_shortlist(nodes, case_id="case-9")
    assert sorted(c.concept_id for c in got) == sorted(c.concept_id for c in nodes)
    assert len(got) == len(nodes)
    # the same objects, so no note content can differ
    assert {id(c) for c in got} == {id(c) for c in nodes}


def test_singleton_and_empty_shortlists_are_untouched() -> None:
    pipe = _pipe("reverse")
    one = _nodes(1)
    assert pipe._order_shortlist(one, case_id="x") == one
    assert pipe._order_shortlist([], case_id="x") == []


def test_unknown_order_is_rejected_at_construction() -> None:
    with pytest.raises(ValueError):
        _pipe("shuffle")
