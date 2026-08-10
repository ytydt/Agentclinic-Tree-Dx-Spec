#!/usr/bin/env python3
"""Structural guarantees for APHHM-C (no LLM).

These correspond to the "can be guaranteed by implementation" list in
``APHHM_COMPACT_REDESIGN.md`` section 10.4.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from agentclinic_tree_dx.aphhm_c import (  # noqa: E402
    AphhmCPipeline,
    ConceptRegistry,
    EvidenceLedger,
    ObservedFact,
)


class FakeLLM:
    """Deterministic stub covering C1..C5."""

    def __init__(self, **overrides: Any) -> None:
        self.calls: list[str] = []
        self.overrides = overrides

    def call(self, module: str, prompt: str, payload: Mapping[str, Any]) -> dict:
        self.calls.append(module)
        if module in self.overrides:
            return self.overrides[module]
        return getattr(self, f"_{module}")(payload)

    def _AphhmCFactLedger(self, payload: Mapping[str, Any]) -> dict:
        return {
            "facts": [
                {
                    "raw_span": "spindle cell tumour with S100 positivity",
                    "specificity": "high",
                    "reliability": "high",
                    "modality": "pathology",
                    "correlation_group": "G1",
                },
                {
                    "raw_span": "S100 positive on immunohistochemistry",
                    "specificity": "high",
                    "reliability": "high",
                    "modality": "pathology",
                    "correlation_group": "G1",
                },
                {
                    "raw_span": "painless enlarging mass",
                    "specificity": "low",
                    "reliability": "medium",
                    "correlation_group": "G2",
                },
                {
                    "raw_span": "presumed lipoma on referral",
                    "specificity": "high",
                    "reliability": "medium",
                    "epistemic_status": "provisional_diagnosis",
                    "correlation_group": "G3",
                },
            ]
        }

    def _AphhmCAxisContract(self, payload: Mapping[str, Any]) -> dict:
        return {
            "axis": "mechanism",
            "families": [
                {
                    "family_id": "B1",
                    "label": "nerve sheath tumours",
                    "scope_in": ["peripheral nerve origin"],
                    "scope_out": ["epithelial tumours"],
                    "initial_belief_rank": 1,
                },
                {
                    "family_id": "B2",
                    "label": "soft tissue sarcoma",
                    "scope_in": ["mesenchymal malignancy"],
                    "scope_out": ["benign lipomatous"],
                    "initial_belief_rank": 2,
                },
            ],
            "fact_coverage": [
                {"fact_id": "F01", "family_ids": ["B1"], "coverage": "specific"},
                {"fact_id": "F02", "family_ids": ["B1"], "coverage": "specific"},
                {"fact_id": "F03", "family_ids": ["B1", "B2"], "coverage": "partial"},
                {"fact_id": "F04", "family_ids": [], "coverage": "none"},
            ],
            "recall_placement": [],
            "provisional_anchor_used_as_evidence": False,
        }

    def _AphhmCBatchedConcepts(self, payload: Mapping[str, Any]) -> dict:
        return {
            "concepts": [
                {
                    "preferred_label": "Schwannoma",
                    "aliases": ["neurilemmoma"],
                    "primary_parent": "B1",
                    "secondary_parent_refs": [],
                    "support_fact_ids": ["F01", "F02"],
                },
                {
                    # same disease proposed again from another family
                    "preferred_label": "schwannoma",
                    "primary_parent": "B2",
                    "support_fact_ids": ["F03"],
                },
                {
                    "preferred_label": "Neurilemmoma",
                    "primary_parent": "B2",
                    "support_fact_ids": ["F02"],
                },
                {
                    "preferred_label": "Malignant peripheral nerve sheath tumour",
                    "primary_parent": "B2",
                    "support_fact_ids": ["F03"],
                },
            ]
        }

    def _AphhmCComplement(self, payload: Mapping[str, Any]) -> dict:
        return {"concepts": []}

    def _AphhmCGlobalMatrix(self, payload: Mapping[str, Any]) -> dict:
        effects = {}
        concepts = [c["concept_id"] for c in payload["concepts"]]
        for f in payload["facts"]:
            row = {}
            for i, cid in enumerate(concepts):
                if f["fact_id"] in ("F01", "F02"):
                    row[cid] = (
                        {"direction": "rule_in", "strength": "strong"}
                        if i == 0
                        else {"direction": "rule_out", "strength": "moderate"}
                    )
                elif f["fact_id"] == "F03":
                    row[cid] = {"direction": "rule_in", "strength": "weak"}
                else:
                    row[cid] = {"direction": "rule_in", "strength": "strong"}
            effects[f["fact_id"]] = row
        return {"effects": effects, "rationales": {}}

    def _AphhmCAdjudicator(self, payload: Mapping[str, Any]) -> dict:
        return {"verdict": "abstain", "corrections": []}

    def _AphhmCFrontierSelector(self, payload: Mapping[str, Any]) -> dict:
        return {"champion": payload["shortlist"][-1], "runner_up": ""}


def _facts() -> list[ObservedFact]:
    return [
        ObservedFact("F01", "a", specificity="high", reliability="high", correlation_group="G1"),
        ObservedFact("F02", "b", specificity="high", reliability="high", correlation_group="G1"),
        ObservedFact("F03", "c", specificity="low", correlation_group="G2"),
    ]


def test_same_as_merges_but_subtype_does_not() -> None:
    reg = ConceptRegistry()
    a = reg.add(label="Schwannoma", primary_parent="B1", support_fact_ids=["F01"])
    b = reg.add(label="schwannoma", primary_parent="B2", support_fact_ids=["F02"])
    assert a == b, "case-only difference must be same_as"
    c = reg.add(label="Malignant peripheral nerve sheath tumour", primary_parent="B2")
    assert c != a, "a different entity must not fold into Schwannoma"
    node = reg.concepts[a]
    assert node.support_fact_ids == ["F01", "F02"]
    assert "B2" in node.secondary_parent_refs
    assert reg.resolved_duplicate_count() == 0


def test_broader_narrower_is_relation_not_merge() -> None:
    reg = ConceptRegistry()
    broad = reg.add(label="Renal cell carcinoma")
    narrow = reg.add(label="Chromophobe renal cell carcinoma")
    assert broad != narrow
    assert broad in reg.concepts[narrow].narrower_than
    assert narrow in reg.concepts[broad].broader_than


def test_correlation_group_clips_double_counting() -> None:
    facts = _facts()
    reg = ConceptRegistry()
    cid = reg.add(label="X")
    ledger = EvidenceLedger(facts, [reg.concepts[cid]])
    # two restatements of the same observation, both strong rule-in
    ledger.ingest(
        {
            "F01": {cid: {"direction": "rule_in", "strength": "strong"}},
            "F02": {cid: {"direction": "rule_in", "strength": "strong"}},
        }
    )
    ledger.apply_gates(reg)
    score, comp = ledger.score_concept(reg.concepts[cid], 0.0)
    # raw would be +6; the group clip caps it at +3
    assert comp["groups"]["G1"]["raw"] == 6
    assert comp["groups"]["G1"]["clipped"] == 3
    assert score == 3.0


def test_p5_vetoes_shared_phenotype_and_provisional() -> None:
    facts = [
        ObservedFact("F01", "fever", specificity="low", correlation_group="G1"),
        ObservedFact(
            "F02",
            "known lymphoma",
            specificity="high",
            epistemic_status="provisional_diagnosis",
            correlation_group="G2",
        ),
    ]
    reg = ConceptRegistry()
    ids = [reg.add(label=n) for n in ("A", "B", "C")]
    ledger = EvidenceLedger(facts, [reg.concepts[i] for i in ids])
    ledger.ingest(
        {
            "F01": {i: {"direction": "rule_in", "strength": "moderate"} for i in ids},
            "F02": {i: {"direction": "rule_in", "strength": "strong"} for i in ids},
        }
    )
    ledger.apply_gates(reg)
    assert all(
        ledger.cells[("F01", i)].veto_reason == "p5_shared_phenotype" for i in ids
    )
    assert all(not ledger.cells[("F01", i)].admitted for i in ids)
    assert all(
        ledger.cells[("F02", i)].veto_reason == "p5_provisional_anchor" for i in ids
    )


def test_axis_bias_is_capped() -> None:
    llm = FakeLLM()
    pipe = AphhmCPipeline(llm, axis_lambda=100.0)
    from agentclinic_tree_dx.aphhm_c import AXIS_BIAS_CAP, AxisContract, Family

    contract = AxisContract(families=[Family("B1", "x", initial_belief_rank=1)])
    reg = ConceptRegistry()
    cid = reg.add(label="X", primary_parent="B1")
    bias = pipe._axis_bias(reg.concepts[cid], contract)
    assert bias <= AXIS_BIAS_CAP


def test_end_to_end_structural_invariants() -> None:
    llm = FakeLLM()
    pipe = AphhmCPipeline(llm)
    res = pipe.run(case_id="t1", vignette="a long vignette " * 20)
    m = res.metrics

    # budget: 4 fixed calls, optional slots only when gated
    assert 4 <= res.llm_calls <= 6, res.llm_calls
    assert llm.calls[:4] == [
        "AphhmCFactLedger",
        "AphhmCAxisContract",
        "AphhmCBatchedConcepts",
        "AphhmCGlobalMatrix",
    ]
    # P5 is offline: it must never appear as its own module call
    assert not any(c.startswith("AphhmCP5") for c in llm.calls)

    # resolved duplicates are structurally impossible
    assert m["resolved_duplicates"] == 0
    # Schwannoma/schwannoma/Neurilemmoma collapse to one slot
    labels = [c["preferred_label"] for c in res.stages["registry"]]
    assert len(labels) == len(set(_l.lower() for _l in labels))
    assert m["n_concepts"] <= pipe.unique_budget

    # nothing leaves active without an event
    assert m["unexplained_disappearance"] == 0
    # every concept generated is still scored (no pre-score pruning)
    assert m["n_active_concepts"] == m["n_concepts"]
    assert len(res.stages["ledger_rank"]) == m["n_active_concepts"]
    # final order is the ledger order
    assert m["ledger_final_inversion"] == 0
    ranked_labels = [
        next(c["preferred_label"] for c in res.stages["registry"] if c["concept_id"] == cid)
        for cid in res.stages["ledger_rank"]
    ]
    assert res.ordered_diagnoses == ranked_labels[:5]
    # matrix completeness
    assert m["p3_completeness"] == 1.0


def test_gap_lane_requires_uncovered_fact_binding() -> None:
    llm = FakeLLM(
        AphhmCComplement={
            "concepts": [
                {"preferred_label": "Unbound zebra", "support_fact_ids": []},
                {"preferred_label": "Bound entity", "support_fact_ids": ["F04"]},
            ]
        }
    )
    pipe = AphhmCPipeline(llm)
    res = pipe.run(case_id="t2", vignette="v " * 50)
    labels = {c["preferred_label"] for c in res.stages["registry"]}
    # F04 is the provisional fact, so it is not an uncovered *observed* fact:
    # neither proposal may enter without binding a real gap obligation.
    assert "Unbound zebra" not in labels


def test_verifier_cannot_add_concepts_or_reorder_freely() -> None:
    llm = FakeLLM(
        AphhmCAdjudicator={
            "verdict": "corrected",
            "corrections": [
                {"fact_id": "F99", "concept_id": "C01", "direction": "rule_out"},
                {"fact_id": "F01", "concept_id": "C99", "direction": "rule_out"},
                {"preferred_label": "Brand new disease"},
            ],
            "ranking": ["Brand new disease"],
        }
    )
    pipe = AphhmCPipeline(llm)
    res = pipe.run(case_id="t3", vignette="v " * 50)
    labels = {c["preferred_label"] for c in res.stages["registry"]}
    assert "Brand new disease" not in labels
    c5 = res.stages.get("c5")
    if c5:
        assert c5["_applied"] == 0
        assert c5["_rejected"] >= 2


def test_selector_arms_stay_inside_the_shortlist() -> None:
    for mode, wide in (
        ("c4_selector", False),
        ("c4_selector_wide", True),
        ("c4_selector_rich", True),
        ("c4_selector_clean", True),
    ):
        llm = FakeLLM(
            AphhmCFrontierSelector={"champion": "Invented disease", "runner_up": "also fake"}
        )
        pipe = AphhmCPipeline(llm, mode=mode)
        res = pipe.run(case_id="s", vignette="v " * 50)
        m = res.metrics
        labels = {c["preferred_label"] for c in res.stages["registry"]}
        # an off-list champion falls back to the shortlist, never invents a label
        assert res.champion in labels, mode
        assert "Invented disease" not in res.ordered_diagnoses, mode
        # wide arms must not let the score prune the shortlist
        if wide:
            assert m["selector_shortlist_n"] == m["n_active_concepts"], mode
        else:
            assert m["selector_shortlist_n"] <= m["n_active_concepts"], mode
        # the verifier slot is spent on the selector instead
        assert "c5" not in res.stages, mode


def test_axis_modes_control_conditioning_and_budget() -> None:
    seen: dict[str, list[str]] = {}

    class Cap(FakeLLM):
        def call(self, module: str, prompt: str, payload: Mapping[str, Any]) -> dict:
            if module == "AphhmCBatchedConcepts":
                seen["keys"] = sorted(payload.keys())
            return super().call(module, prompt, payload)

    base_calls = None
    for axis_mode in ("conditioned", "unconditioned", "off"):
        llm = Cap()
        pipe = AphhmCPipeline(
            llm,
            mode="c4_selector_clean",
            axis_mode=axis_mode,
            concept_contract="v2" if axis_mode == "conditioned" else "noaxis",
        )
        res = pipe.run(case_id="a", vignette="v " * 50)
        conditioned = "families" in seen["keys"]
        assert conditioned == (axis_mode == "conditioned"), axis_mode
        called_c2 = "AphhmCAxisContract" in llm.calls
        assert called_c2 == (axis_mode != "off"), axis_mode
        if axis_mode == "off":
            # the axis slot is removed from the budget and cannot bias the score
            assert res.llm_calls == base_calls - 1
            assert pipe.axis_lambda == 0.0
        else:
            base_calls = res.llm_calls
        # the structural base is untouched by the axis factor
        assert res.metrics["resolved_duplicates"] == 0, axis_mode
        assert res.metrics["unexplained_disappearance"] == 0, axis_mode
        assert res.metrics["p3_completeness"] == 1.0, axis_mode


def test_candidate_evidence_spans_must_be_verbatim() -> None:
    vignette = (
        "A 40-year-old man had progressive dyspnea and a right pleural effusion. "
        "Biopsy showed epithelioid mesothelioma with asbestos exposure."
    )
    seen_notes: list[dict] = []

    class Ev(FakeLLM):
        def _AphhmCBatchedConcepts(self, payload: Mapping[str, Any]) -> dict:
            out = super()._AphhmCBatchedConcepts(payload)
            for c in out["concepts"]:
                c["support_spans"] = ["progressive dyspnea", "a finding never written"]
                c["contradict_spans"] = ["asbestos exposure", "invented contradiction"]
            return out

        def _AphhmCFrontierSelector(self, payload: Mapping[str, Any]) -> dict:
            seen_notes.extend(payload["candidate_notes"])
            return super()._AphhmCFrontierSelector(payload)

    calls_by_mode = {}
    for mode in ("c4_selector_candev", "c4_selector_candev_nomatrix"):
        seen_notes.clear()
        pipe = AphhmCPipeline(
            Ev(), mode=mode, concept_contract="evid", axis_mode="off", unique_budget=10
        )
        res = pipe.run(case_id="a", vignette=vignette)
        calls_by_mode[mode] = res.llm_calls
        for c in res.stages["registry"]:
            # hallucinated spans never reach the ledger or the selector
            assert c["support_spans"] == ["progressive dyspnea"], c
            assert c["contradict_spans"] == ["asbestos exposure"], c
        assert seen_notes, mode
        for note in seen_notes:
            assert set(note) == {"label", "for", "against"}, note
            # no score or rank leaks in as a selection anchor
            assert "score" not in note
        assert res.metrics["resolved_duplicates"] == 0
        assert res.metrics["unexplained_disappearance"] == 0
    # dropping the matrix removes exactly one fixed call and makes P3 undefined
    assert (
        calls_by_mode["c4_selector_candev"]
        - calls_by_mode["c4_selector_candev_nomatrix"]
        == 1
    )


def test_multistance_unions_pools_and_keeps_the_tournament_bounded() -> None:
    vignette = (
        "A 40-year-old man had progressive dyspnea and a right pleural effusion. "
        "Biopsy showed epithelioid mesothelioma with asbestos exposure."
    )
    per_stance = {
        "commit": ["Epithelioid mesothelioma", "Schwannoma"],
        "coverage": ["Lymphoma", "Schwannoma"],
        "mechanism": ["Cholesterol embolisation syndrome"],
    }
    seen_payloads: list[dict] = []

    class Ms(FakeLLM):
        def _AphhmCBatchedConcepts(self, payload: Mapping[str, Any]) -> dict:
            # the prompt text is the only thing that distinguishes the stances, so
            # key off the order the pipeline asks for them
            stance = list(per_stance)[len([c for c in self.calls if c.endswith("Concepts")]) - 1]
            return {
                "concepts": [
                    {
                        "preferred_label": label,
                        "support_fact_ids": ["F01"],
                        "support_spans": ["progressive dyspnea"],
                        "contradict_spans": [],
                    }
                    for label in per_stance[stance]
                ]
            }

        def _AphhmCFrontierSelector(self, payload: Mapping[str, Any]) -> dict:
            seen_payloads.append(dict(payload))
            return {"champion": "not on the shortlist at all", "runner_up": ""}

    pipe = AphhmCPipeline(Ms(), mode="multistance", axis_mode="off", unique_budget=10)
    res = pipe.run(case_id="a", vignette=vignette)

    labels = {c["preferred_label"] for c in res.stages["registry"]}
    assert "Cholesterol embolisation syndrome" in labels, "mechanism stance must survive the union"
    assert "Lymphoma" in labels, "coverage stance must survive the union"
    # one disease proposed by two stances stays one concept, credited to both
    dupes = [c for c in res.stages["registry"] if c["preferred_label"] == "Schwannoma"]
    assert len(dupes) == 1, dupes
    assert dupes[0]["stances"] == ["commit", "coverage"], dupes[0]
    assert res.metrics["resolved_duplicates"] == 0
    assert res.metrics["n_multi_stance_concepts"] == 1
    assert res.metrics["n_concepts_per_stance"] == {"commit": 2, "coverage": 2, "mechanism": 1}

    # the selector sees stance groups, never a flat ranked list
    payload = seen_payloads[-1]
    assert "candidate_notes" not in payload
    groups = {g["group"] for g in payload["groups"]}
    assert groups == {"commit", "coverage", "mechanism"}, groups
    for group in payload["groups"]:
        for cand in group["candidates"]:
            assert set(cand) <= {"label", "for", "against", "also_found_by"}, cand
            assert "score" not in cand and "rank" not in cand
    # a stance costs exactly one call and the gap lane still fits under the cap
    assert res.llm_calls <= pipe.max_calls == len(pipe.stances) + 3
    assert res.metrics["llm_calls"] >= 1 + len(pipe.stances) + 1
    # an off-shortlist champion is refused, exactly as in the single-stance arms
    assert res.champion in {c["preferred_label"] for c in res.stages["registry"]}


def test_split_final_runs_two_rounds_and_confines_the_champion() -> None:
    vignette = (
        "A 40-year-old man had progressive dyspnea and a right pleural effusion. "
        "Biopsy showed epithelioid mesothelioma with asbestos exposure."
    )
    per_stance = {
        "commit": ["Epithelioid mesothelioma", "Schwannoma"],
        "coverage": ["Lymphoma", "Adenocarcinoma"],
        "mechanism": ["Cholesterol embolisation syndrome"],
    }
    final_payloads: list[dict] = []

    class Split(FakeLLM):
        def _AphhmCBatchedConcepts(self, payload: Mapping[str, Any]) -> dict:
            stance = list(per_stance)[len([c for c in self.calls if c.endswith("Concepts")]) - 1]
            return {
                "concepts": [
                    {
                        "preferred_label": label,
                        "support_fact_ids": ["F01"],
                        "support_spans": ["progressive dyspnea"],
                        "contradict_spans": ["asbestos exposure"],
                    }
                    for label in per_stance[stance]
                ]
            }

        def _AphhmCStanceNomination(self, payload: Mapping[str, Any]) -> dict:
            return {
                "finalists": [
                    {"group": "commit", "label": "Schwannoma", "why": "w"},
                    # nominating another group's candidate must be dropped
                    {"group": "coverage", "label": "Schwannoma", "why": "w"},
                    # a label nobody proposed must be dropped
                    {"group": "mechanism", "label": "Invented disease", "why": "w"},
                ]
            }

        def _AphhmCFinalAdjudicator(self, payload: Mapping[str, Any]) -> dict:
            final_payloads.append(dict(payload))
            return {"champion": "Lymphoma", "runner_up": "Schwannoma"}

    pipe = AphhmCPipeline(Split(), mode="multistance_split", axis_mode="off", unique_budget=10)
    res = pipe.run(case_id="a", vignette=vignette)

    # only the in-group nomination survived, so the final round never happened
    assert not final_payloads, "a single surviving finalist must not cost a second call"
    assert res.champion == "Schwannoma", res.champion
    sel = res.stages["frontier_selector"]
    assert [f["label"] for f in sel["finalists"]] == ["Schwannoma"], sel["finalists"]

    # with one valid nomination per group the final round runs and is bounded by them
    class Split2(Split):
        def _AphhmCStanceNomination(self, payload: Mapping[str, Any]) -> dict:
            return {
                "finalists": [
                    {"group": "commit", "label": "Schwannoma", "unexplained": "u"},
                    {"group": "coverage", "label": "Lymphoma", "unexplained": ""},
                ]
            }

        def _AphhmCFinalAdjudicator(self, payload: Mapping[str, Any]) -> dict:
            final_payloads.append(dict(payload))
            return {"champion": "Epithelioid mesothelioma", "runner_up": "Lymphoma"}

    llm = Split2()
    pipe = AphhmCPipeline(llm, mode="multistance_split", axis_mode="off", unique_budget=10)
    res = pipe.run(case_id="a", vignette=vignette)
    assert len(final_payloads) == 1
    payload = final_payloads[0]
    assert payload["shortlist"] == ["Schwannoma", "Lymphoma"], payload["shortlist"]
    for f in payload["finalists"]:
        assert set(f) == {"group", "label", "for", "against", "why", "unexplained"}, f
        assert f["for"] == ["progressive dyspnea"] and f["against"] == ["asbestos exposure"]
    # the adjudicator reached past the finalists, so its answer is refused
    assert res.champion in {"Schwannoma", "Lymphoma"}, res.champion
    assert llm.calls.count("AphhmCStanceNomination") == 1
    assert llm.calls.count("AphhmCFinalAdjudicator") == 1
    # two selector rounds cost one more call than the single-round tournament
    single = AphhmCPipeline(Split2(), mode="multistance", axis_mode="off", unique_budget=10)
    assert res.llm_calls == single.run(case_id="a", vignette=vignette).llm_calls + 1
    assert res.llm_calls <= pipe.max_calls == len(pipe.stances) + 4


TESTS = [
    test_same_as_merges_but_subtype_does_not,
    test_broader_narrower_is_relation_not_merge,
    test_correlation_group_clips_double_counting,
    test_p5_vetoes_shared_phenotype_and_provisional,
    test_axis_bias_is_capped,
    test_end_to_end_structural_invariants,
    test_gap_lane_requires_uncovered_fact_binding,
    test_verifier_cannot_add_concepts_or_reorder_freely,
    test_selector_arms_stay_inside_the_shortlist,
    test_axis_modes_control_conditioning_and_budget,
    test_candidate_evidence_spans_must_be_verbatim,
    test_multistance_unions_pools_and_keeps_the_tournament_bounded,
    test_split_final_runs_two_rounds_and_confines_the_champion,
]


if __name__ == "__main__":
    for fn in TESTS:
        fn()
        print(f"  ok {fn.__name__}")
    print("OK aphhm_c unit tests")
