"""Two APHHM-C contract fixes found by auditing the frozen multistance logs.

Both defaults must stay off so every archived arm replays unchanged; the tests
therefore assert the legacy behaviour as well as the repaired behaviour.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from agentclinic_tree_dx.aphhm_c import (  # noqa: E402
    AphhmCPipeline,
    ConceptRegistry,
    _strict_key,
)


class ScriptedLLM:
    """Returns a canned reply per module name and records the payloads seen."""

    def __init__(self, replies: dict[str, Any]) -> None:
        self.replies = replies
        self.calls: list[tuple[str, dict]] = []

    def call(self, module: str, prompt: str, payload: dict) -> Any:
        self.calls.append((module, payload))
        r = self.replies.get(module, {})
        return r.pop(0) if isinstance(r, list) else r


# --------------------------------------------------------------------------
# Debt 1: every non-empty stance group owes exactly one finalist.
# --------------------------------------------------------------------------

PAYLOAD = {
    "vignette": "v",
    "shortlist": ["Acute Pericarditis", "Myocarditis", "Pulmonary Embolism"],
    "groups": [
        {"group": "commit", "candidates": [{"label": "Acute Pericarditis"}]},
        {"group": "coverage", "candidates": [{"label": "Myocarditis"}]},
        {"group": "mechanism", "candidates": [{"label": "Pulmonary Embolism"}]},
    ],
}


def _pipe(llm: ScriptedLLM, **kw: Any) -> AphhmCPipeline:
    return AphhmCPipeline(llm, mode="multistance", **kw)


def test_silent_group_is_seated_and_final_is_re_adjudicated():
    llm = ScriptedLLM(
        {
            "AphhmCFinalAdjudicator": {"champion": "Pulmonary Embolism"},
        }
    )
    pipe = _pipe(llm, enforce_group_quota=True)
    raw = {
        "champion": "Acute Pericarditis",
        "finalists": [{"group": "commit", "label": "Acute Pericarditis"}],
    }
    out, champ, calls = pipe._enforce_group_quota(
        vignette="v", payload=PAYLOAD, raw=raw, champ="Acute Pericarditis"
    )

    assert {f["group"] for f in out["finalists"]} == {
        "commit",
        "coverage",
        "mechanism",
    }
    assert out["group_quota"]["n_finalists_from_model"] == 1
    assert [f["label"] for f in out["group_quota"]["filled"]] == [
        "Myocarditis",
        "Pulmonary Embolism",
    ]
    # a stance the model ignored can now actually win
    assert champ == "Pulmonary Embolism"
    assert out["champion_before_quota"] == "Acute Pericarditis"
    assert calls == 2


def test_seat_filler_takes_the_groups_highest_ranked_member():
    llm = ScriptedLLM({"AphhmCFinalAdjudicator": {"champion": "Myocarditis"}})
    pipe = _pipe(llm, enforce_group_quota=True)
    payload = {
        "vignette": "v",
        "shortlist": ["Acute Pericarditis", "Myocarditis", "Viral Myocarditis"],
        "groups": [
            {"group": "commit", "candidates": [{"label": "Acute Pericarditis"}]},
            {
                "group": "coverage",
                "candidates": [{"label": "Myocarditis"}, {"label": "Viral Myocarditis"}],
            },
        ],
    }
    out, _, _ = pipe._enforce_group_quota(
        vignette="v",
        payload=payload,
        raw={"finalists": [{"group": "commit", "label": "Acute Pericarditis"}]},
        champ="Acute Pericarditis",
    )
    assert out["group_quota"]["filled"] == [
        {"group": "coverage", "label": "Myocarditis"}
    ]


def test_compliant_reply_costs_nothing_and_keeps_its_champion():
    llm = ScriptedLLM({})
    pipe = _pipe(llm, enforce_group_quota=True)
    raw = {
        "champion": "Myocarditis",
        "finalists": [
            {"group": "commit", "label": "Acute Pericarditis"},
            {"group": "coverage", "label": "Myocarditis"},
            {"group": "mechanism", "label": "Pulmonary Embolism"},
        ],
    }
    out, champ, calls = pipe._enforce_group_quota(
        vignette="v", payload=PAYLOAD, raw=raw, champ="Myocarditis"
    )
    assert champ == "Myocarditis"
    assert calls == 1
    assert out["group_quota"]["filled"] == []
    assert llm.calls == []


def test_finalist_outside_the_shortlist_is_dropped_then_its_group_refilled():
    llm = ScriptedLLM({"AphhmCFinalAdjudicator": {"champion": "Acute Pericarditis"}})
    pipe = _pipe(llm, enforce_group_quota=True)
    out, _, _ = pipe._enforce_group_quota(
        vignette="v",
        payload=PAYLOAD,
        raw={"finalists": [{"group": "commit", "label": "Hallucinated Disease"}]},
        champ="Acute Pericarditis",
    )
    labels = {f["label"] for f in out["finalists"]}
    assert "Hallucinated Disease" not in labels
    assert labels == {"Acute Pericarditis", "Myocarditis", "Pulmonary Embolism"}
    assert out["group_quota"]["n_finalists_from_model"] == 0


def test_quota_is_off_by_default():
    assert _pipe(ScriptedLLM({})).enforce_group_quota is False
    assert _pipe(ScriptedLLM({})).max_calls == _pipe(
        ScriptedLLM({}), enforce_group_quota=True
    ).max_calls - 1


# --------------------------------------------------------------------------
# Debt 2: identity must not fold a parent into a child.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "a,b",
    [
        ("Grover's disease", "Grover disease"),
        ("Right Bundle-Branch Block", "Right Bundle Branch Block"),
        ("Optic disc pits", "optic disc pit"),
    ],
)
def test_strict_key_folds_surface_morphology(a: str, b: str):
    assert _strict_key(a) == _strict_key(b)


@pytest.mark.parametrize(
    "a,b",
    [
        ("Pericarditis", "Acute Pericarditis"),
        ("Schwannoma", "Facial nerve schwannoma"),
        ("Leukemic cutis", "Leukemia Cutis"),
        ("Myocardial Ischemia", "Myocardial Infarction"),
        # an acronym keeps its tail `s`, so plural folding cannot merge these
        ("AIDS", "AID"),
        ("ARDS", "ARD"),
    ],
)
def test_strict_key_keeps_modifiers_and_derivations_apart(a: str, b: str):
    assert _strict_key(a) != _strict_key(b)


def test_claimed_alias_folds_parent_into_child_by_default():
    """The archived behaviour: `Acute Pericarditis` claims `Pericarditis`, so the
    coarse concept disappears and only the specific label stays visible."""
    reg = ConceptRegistry()
    child = reg.add(label="Acute Pericarditis", aliases=["Pericarditis"], stance="commit")
    parent = reg.add(label="Pericarditis", stance="coverage")
    assert parent == child
    assert len(reg.concepts) == 1
    assert reg.concepts[child].preferred_label == "Acute Pericarditis"


def test_strict_identity_keeps_them_separate_as_a_broader_narrower_pair():
    reg = ConceptRegistry(strict_identity=True)
    child = reg.add(label="Acute Pericarditis", aliases=["Pericarditis"], stance="commit")
    parent = reg.add(label="Pericarditis", stance="coverage")
    assert parent != child
    assert {c.preferred_label for c in reg.concepts.values()} == {
        "Acute Pericarditis",
        "Pericarditis",
    }
    # the lattice `add` already builds is now allowed to record the relation
    assert child in reg.concepts[parent].broader_than
    assert parent in reg.concepts[child].narrower_than
    # and the unproven claim is preserved rather than silently dropped
    assert any(
        m["kind"] == "claimed_alias_not_merged" and m["label"] == "Pericarditis"
        for m in reg.merge_audit
    )


def test_strict_identity_still_merges_the_same_label_twice():
    reg = ConceptRegistry(strict_identity=True)
    a = reg.add(label="Acute Pericarditis", stance="commit", support_spans=["s1"])
    b = reg.add(label="acute  pericarditis", stance="coverage", support_spans=["s2"])
    assert a == b
    assert reg.concepts[a].stances == ["commit", "coverage"]
    assert reg.concepts[a].support_spans == ["s1", "s2"]


def test_strict_identity_ignores_a_resolver_that_maps_parent_and_child_together():
    class CollapsingResolver:
        def resolve(self, label: str) -> str:
            return "PERICARDITIS"

    lax = ConceptRegistry(resolver=CollapsingResolver())
    assert lax.add(label="Acute Pericarditis") == lax.add(label="Constrictive Pericarditis")

    strict = ConceptRegistry(resolver=CollapsingResolver(), strict_identity=True)
    assert strict.add(label="Acute Pericarditis") != strict.add(
        label="Constrictive Pericarditis"
    )


def test_strict_identity_is_off_by_default():
    assert ConceptRegistry().strict_identity is False
    assert AphhmCPipeline(ScriptedLLM({}), mode="multistance").strict_identity is False
