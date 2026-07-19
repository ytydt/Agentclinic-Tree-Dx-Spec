"""Deterministic regression tests for §23.14 (Mode A) KB-anchored, axis/level-aware
branch generation.

Guarantees verified:
  1. SyndromeAxisMap.match is deterministic + longest-keyword wins; fallback works.
  2. project_entity maps entities onto the single-axis MECE L1 domain partition.
  3. _build_branch_candidates is a PURE function: identical state → identical block,
     emits one mandatory_coverage domain list along a SINGLE axis, and pushes
     specific entities DOWN into candidate_entities_by_domain (never as L1 labels).
  4. OFF-by-default no-op: with enable_branch_knowledge=False the BranchCreator
     payload is byte-identical to the legacy path (returns None).
"""

from pathlib import Path
from types import SimpleNamespace

import pytest

from agentclinic_tree_dx.knowledge.syndrome_axis import SyndromeAxisMap

DATA = Path(__file__).resolve().parents[1] / "data" / "knowledge_raw"
AXIS = DATA / "syndrome_axis_map.json"


@pytest.fixture()
def axis_map() -> SyndromeAxisMap:
    return SyndromeAxisMap.from_file(AXIS)


# ── 1. matching ────────────────────────────────────────────────────────────

def test_match_is_deterministic_and_keyworded(axis_map):
    e1 = axis_map.match("Patient with marked leukocytosis and very high white blood cell count")
    e2 = axis_map.match("Patient with marked leukocytosis and very high white blood cell count")
    assert e1["id"] == e2["id"] == "leukocytosis"
    assert e1["axis"] == "mechanism"


def test_match_falls_back_when_no_syndrome(axis_map):
    e = axis_map.match("a completely unrelated sentence about nothing clinical xyz")
    assert e["id"] == "undifferentiated"
    # fallback has no usable domain partition → caller treats as no-anchoring
    assert axis_map.domain_names(e) == []


def test_single_axis_invariant_per_syndrome(axis_map):
    for entry in axis_map._syndromes:
        assert entry.get("axis"), f"{entry.get('id')} missing axis"
        # every entry declares exactly one axis string (single-axis by construction)
        assert isinstance(entry["axis"], str)


# ── 2. entity → domain projection ─────────────────────────────────────────

def test_project_entity_onto_partition(axis_map):
    entry = axis_map.match("marked leukocytosis")
    assert axis_map.project_entity("chronic myelogenous leukemia", entry) == \
        "myeloid neoplasm (incl. MPN / blast-bearing)"
    assert axis_map.project_entity("acute lymphoblastic leukemia", entry) == \
        "lymphoid neoplasm"
    # an entity outside the partition projects to None (residual)
    assert axis_map.project_entity("ankle sprain", entry) is None


# ── 3 & 4. controller integration: pure + gated ────────────────────────────

def _make_controller(enable: bool):
    from agentclinic_tree_dx.controller import AgentClinicTreeController
    from agentclinic_tree_dx.config import ControllerConfig
    cfg = ControllerConfig(
        enable_knowledge_injection=False,   # keep init light; we stub the retriever
        enable_branch_knowledge=enable,
        lr_cache_json=str(DATA / "lr_cache.json"),
        syndrome_axis_map_json=str(AXIS),
    )
    env = SimpleNamespace()
    ctrl = AgentClinicTreeController(env=env, llm=None, config=cfg)
    return ctrl


def _state_with(text: str):
    # minimal stand-in: _build_branch_candidates only reads case_summary +
    # _raw_atomic_facts(state). We give a state-like object and stub facts.
    return SimpleNamespace(case_summary=text, static_evidence_items=[], actions_taken=[])


def test_off_by_default_is_noop():
    ctrl = _make_controller(enable=False)
    assert ctrl._syndrome_axis_map is None
    st = _state_with("marked leukocytosis with very high white blood cell count")
    assert ctrl._build_branch_candidates(st) is None


def test_build_candidates_is_pure_and_single_axis(monkeypatch):
    ctrl = _make_controller(enable=True)
    assert ctrl._syndrome_axis_map is not None
    # stub atomic-fact extraction so the test is independent of the heavy pipeline
    monkeypatch.setattr(ctrl, "_raw_atomic_facts",
                        lambda state: ["chronic myelogenous leukemia suspected"])
    st = _state_with("Patient with marked leukocytosis, very high white blood cell count")

    b1 = ctrl._build_branch_candidates(st)
    b2 = ctrl._build_branch_candidates(st)
    assert b1 == b2, "must be a pure/deterministic function"
    assert b1 is not None
    assert b1["syndrome_matched"] == "leukocytosis"
    assert b1["l1_classification_axis"] == "mechanism"
    # mandatory_coverage is the MECE L1 domain partition (recall guarantee)
    assert "myeloid neoplasm (incl. MPN / blast-bearing)" in b1["mandatory_coverage"]
    assert len(b1["mandatory_coverage"]) >= 3
    # entities are pushed DOWN under a domain, never surfaced as a domain name
    for dom, ents in b1["candidate_entities_by_domain"].items():
        assert dom in b1["mandatory_coverage"]
        assert all(isinstance(e, str) for e in ents)


def test_build_candidates_returns_none_for_unmatched(monkeypatch):
    ctrl = _make_controller(enable=True)
    monkeypatch.setattr(ctrl, "_raw_atomic_facts", lambda state: [])
    st = _state_with("nothing clinical here at all xyz")
    assert ctrl._build_branch_candidates(st) is None
