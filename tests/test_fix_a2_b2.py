"""Regression tests for the §22 corrected fixes (A′/B′) and the ported
§21.13.4 data-bug fixes.

A′ (taxonomy-derived representative entities): branch labels are expanded to
canonical entities MECHANICALLY (no prompt), so the label is never hollowed.
B′ relies on the same entity side-channel + the existing numeric LR update; the
data-bug fixes (Bug1 negation guard, Bug2 family curves) restore correct priors.
"""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from agentclinic_tree_dx.knowledge.disease_name_resolver import DiseaseNameResolver
from agentclinic_tree_dx.knowledge.prior_modifier import _kw_hit, PriorModifier

DATA = Path(__file__).resolve().parents[1] / "data" / "knowledge_raw"
MECH = DATA / "mechanism_to_disease.json"
AGE = DATA / "age_sex_incidence.json"
PATHO = DATA / "pathognomonic_markers.json"


def _mk_branch(label: str):
    from agentclinic_tree_dx.state import Branch
    return Branch(id="b1", label=label, parent="ROOT", level=1, status="live",
                  prior=0.1, posterior=0.1, danger=0.0, actionability=0.0,
                  explanatory_coverage=0.0)


@pytest.fixture()
def resolver() -> DiseaseNameResolver:
    r = DiseaseNameResolver()
    r.load_mechanism_map(MECH)
    return r


# ── A′: taxonomy expansion ────────────────────────────────────────────────

def test_a2_family_expansion_myeloproliferative(resolver):
    ents = resolver.expand_to_entities("Chronic Myeloproliferative Neoplasm (chronic phase)")
    assert "chronic myeloid leukemia" in ents
    assert "polycythemia vera" in ents
    assert len(ents) <= 4


def test_a2_family_expansion_hepatic_vascular(resolver):
    ents = resolver.expand_to_entities("Hepatic Vascular Disorder")
    assert "peliosis hepatis" in ents
    assert "budd-chiari syndrome" in ents


def test_a2_exact_mechanism_still_maps(resolver):
    assert resolver.expand_to_entities("Increased PTH") == ["primary hyperparathyroidism"]


def test_a2_generic_label_yields_nothing(resolver):
    # The whole point of A′: a generic organ bucket must NOT invent entities
    # (it is the hollowed label that A′ exists to avoid relying on).
    assert resolver.expand_to_entities("Endocrine Disorder") == []
    assert resolver.expand_to_entities("Malignancy") == []


def test_a2_dedup_and_cap(resolver):
    ents = resolver.expand_to_entities("Malignancy with Hypercalcemia and Elevated Alk Phos")
    assert len(ents) == len(set(ents))  # deduped
    assert len(ents) <= 4


# ── A′: controller mechanical population leaves the LABEL untouched ────────

def test_a2_populate_lookup_entities_does_not_touch_label(resolver):
    from agentclinic_tree_dx.controller import AgentClinicTreeController
    from agentclinic_tree_dx.state import Branch

    b = _mk_branch("Chronic Myeloproliferative Neoplasm")
    branches = {"b1": b}
    stub = SimpleNamespace(
        config=SimpleNamespace(enable_taxonomy_entities=True),
        _knowledge_retriever=SimpleNamespace(resolver=resolver),
    )
    AgentClinicTreeController._populate_lookup_entities(stub, branches)
    # label is unchanged (no hollowing); entities attached as side-channel
    assert b.label == "Chronic Myeloproliferative Neoplasm"
    assert "chronic myeloid leukemia" in b.representative_diseases


def test_a2_disabled_flag_is_noop(resolver):
    from agentclinic_tree_dx.controller import AgentClinicTreeController
    from agentclinic_tree_dx.state import Branch

    b = _mk_branch("Chronic Myeloproliferative Neoplasm")
    stub = SimpleNamespace(
        config=SimpleNamespace(enable_taxonomy_entities=False),
        _knowledge_retriever=SimpleNamespace(resolver=resolver),
    )
    AgentClinicTreeController._populate_lookup_entities(stub, {"b1": b})
    assert b.representative_diseases == []


# ── Bug1: negation guard in prior keyword matcher ─────────────────────────

def test_bug1_non_malignant_does_not_hit_malignancy():
    assert _kw_hit("malignan", "reactive / non-malignant leukocytosis") is False
    assert _kw_hit("malignan", "benign reactive process") is False


def test_bug1_plain_malignant_still_hits():
    assert _kw_hit("malignan", "malignant hypercalcemia") is True


def test_bug1_reactive_leukocytosis_prior_is_neutral():
    pm = PriorModifier()
    pm.load(AGE)
    # A benign/reactive process must not be put on the solid-malignancy curve.
    mult = pm.multiplier("Reactive / Non-malignant Leukocytosis", age=55, sex="male")
    assert mult == pytest.approx(1.0)


# ── Bug2: family curves (myeloid elderly-peaked, lymphoid child-peaked) ────

def test_bug2_lymphoid_family_child_peaked_not_inverted():
    pm = PriorModifier()
    pm.load(AGE)
    child = pm.multiplier("Lymphoid Neoplasm with Increased Blasts", age=8, sex="male")
    old = pm.multiplier("Lymphoid Neoplasm with Increased Blasts", age=70, sex="male")
    assert child > 1.0          # ALL peaks in children
    assert child > old          # not the inverted solid-tumour curve


def test_bug2_myeloid_family_elderly_peaked():
    pm = PriorModifier()
    pm.load(AGE)
    child = pm.multiplier("Myeloid Neoplasm with Increased Blasts", age=8, sex="male")
    old = pm.multiplier("Myeloid Neoplasm with Increased Blasts", age=70, sex="male")
    assert old > child


# ── F4 LR holes filled in curated markers ─────────────────────────────────

def test_lrholes_markers_present():
    data = json.load(open(PATHO, encoding="utf-8"))
    terms = {t.lower() for m in data["markers"] for t in m.get("terms", [])}
    assert "necrolytic migratory erythema" in terms
    assert "basophilia" in terms
    assert "anabolic steroid use" in terms
    # each maps to the intended target disease
    by_term = {}
    for m in data["markers"]:
        for t in m.get("terms", []):
            by_term[t.lower()] = [d.lower() for d in m.get("target_diseases", [])]
    assert any("glucagonoma" in d for d in by_term["necrolytic migratory erythema"])
    assert any("chronic myeloid leukemia" in d for d in by_term["basophilia"])
    assert any("peliosis" in d for d in by_term["anabolic steroid use"])
