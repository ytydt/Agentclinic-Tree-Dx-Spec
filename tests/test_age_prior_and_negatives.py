"""Regression tests for the structured age/sex prior channel and the
demographics / pertinent-negative finding-LR hygiene helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from agentclinic_tree_dx.knowledge.prior_modifier import (
    PriorModifier,
    parse_age_sex,
)
from agentclinic_tree_dx.controller import (
    _is_demographic_fact,
    _extract_negated_phenotype,
)

DATA = Path(__file__).resolve().parents[1] / "data" / "knowledge_raw" / "age_sex_incidence.json"


@dataclass
class _B:
    label: str
    prior: float
    posterior: float = 0.0


# ── parse_age_sex ───────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "text,age,sex",
    [
        ("A 64-year-old man presents with fatigue", 64, "male"),
        ("A 6-year-old girl with fever", 6, "female"),
        ("3-month-old infant", 0, None),
        ("Age: 72, female", 72, "female"),
        ("no age or sex here", None, None),
    ],
)
def test_parse_age_sex(text, age, sex):
    assert parse_age_sex(text) == (age, sex)


# ── PriorModifier ───────────────────────────────────────────────────────────

def _modifier() -> PriorModifier:
    pm = PriorModifier()
    pm.load(DATA)
    assert pm.loaded
    return pm


def test_data_file_is_valid_json():
    json.loads(DATA.read_text(encoding="utf-8"))


def test_f7_age_sex_cached_per_state_not_across_cases():
    """F7 regression: demographics must cache on the per-case `state`, never on the
    shared controller. A second case (10yo girl) must NOT inherit the first case's
    (55, male) — which previously leaked via `self._patient_age_sex`."""
    import types
    from agentclinic_tree_dx.controller import AgentClinicTreeController

    apply = AgentClinicTreeController._apply_age_prior
    ns = types.SimpleNamespace(_prior_modifier=_modifier(),
                               _raw_atomic_facts=lambda state: [])

    s1 = types.SimpleNamespace(static_vignette="", case_summary="A 55-year-old man presents")
    apply(ns, {"b": _B("Chronic myeloid leukemia", 1.0, 1.0)}, s1)
    assert getattr(s1, "_age_sex_cache", None) == (55, "male")

    s2 = types.SimpleNamespace(static_vignette="", case_summary="A 10-year-old girl is admitted")
    apply(ns, {"b": _B("Acute lymphoblastic leukemia", 1.0, 1.0)}, s2)
    # Must reflect case 2's own demographics, not case 1's leaked (55, male).
    assert getattr(s2, "_age_sex_cache", None) == (10, "female")


def test_cml_favored_in_elderly_suppressed_in_child():
    pm = _modifier()
    assert pm.multiplier("Chronic myeloid leukemia", 70, "male") > 1.5
    assert pm.multiplier("Chronic myeloid leukemia", 7, "male") < 0.3


def test_all_favored_in_child():
    pm = _modifier()
    # ALL peaks in childhood; matched via the 'all' token override.
    assert pm.multiplier("Acute lymphoblastic leukemia", 5, "female") > 1.5


def test_sex_mismatch_zeroes_out():
    pm = _modifier()
    assert pm.multiplier("Prostate cancer", 70, "female") < 0.1
    assert pm.multiplier("Prostate cancer", 70, "male") > 1.5


def test_no_match_is_neutral():
    pm = _modifier()
    assert pm.multiplier("Some unmapped syndrome", 70, "male") == 1.0


def test_no_age_is_neutral():
    pm = _modifier()
    assert pm.multiplier("Chronic myeloid leukemia", None, "male") == 1.0


def test_apply_renormalizes_and_reweights():
    pm = _modifier()
    branches = {
        "b1": _B("Chronic myeloid leukemia", 0.5, 0.5),
        "b2": _B("Acute lymphoblastic leukemia", 0.5, 0.5),
    }
    total_before = sum(b.prior for b in branches.values())
    trace = pm.apply(branches, age=70, sex="male")
    total_after = sum(b.prior for b in branches.values())
    assert total_after == pytest.approx(total_before, rel=1e-6)
    # Elderly → CML should now dominate ALL.
    assert branches["b1"].prior > branches["b2"].prior
    assert branches["b1"].posterior == branches["b1"].prior
    assert trace  # adjustments recorded


def test_apply_noop_when_age_unknown():
    pm = _modifier()
    branches = {"b1": _B("Chronic myeloid leukemia", 0.5, 0.5)}
    trace = pm.apply(branches, age=None, sex="male")
    assert trace == {}
    assert branches["b1"].prior == 0.5


# ── demographics / negation helpers ─────────────────────────────────────────

@pytest.mark.parametrize(
    "text",
    [
        "A 55-year-old man",
        "64-year-old woman",
        "Age: 72",
        "3-month-old",
    ],
)
def test_demographic_facts_detected(text):
    assert _is_demographic_fact(text)


@pytest.mark.parametrize(
    "text",
    ["Splenomegaly on exam", "WBC 57,000", "Night sweats and weight loss"],
)
def test_non_demographic_not_flagged(text):
    assert not _is_demographic_fact(text)


def test_extract_named_negation():
    assert _extract_negated_phenotype("No lymphadenopathy") == "lymphadenopathy"
    assert _extract_negated_phenotype("negative for hepatosplenomegaly") == "hepatosplenomegaly"
    assert _extract_negated_phenotype("without fever") == "fever"


def test_extract_system_negation():
    out = _extract_negated_phenotype("Cardiopulmonary exam: within normal limits")
    assert out == "__system__:cardiopulmonary"
    out2 = _extract_negated_phenotype("Abdominal exam unremarkable")
    assert out2 == "__system__:abdominal"


def test_present_finding_not_treated_as_negation():
    assert _extract_negated_phenotype("Splenomegaly present") is None
    assert _extract_negated_phenotype("Fever 39C") is None
