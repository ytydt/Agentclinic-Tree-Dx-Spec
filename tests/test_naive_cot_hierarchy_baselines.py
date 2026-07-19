from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location(
    "eval_naive_cot_hierarchy_baselines",
    ROOT / "scripts" / "eval_naive_cot_hierarchy_baselines.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class FakeCache:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def call(self, module, prompt, payload):
        self.calls.append((module, payload))
        response = self.responses[module]
        return response(payload) if callable(response) else response


def _branch(branch_id, label, level, prior, parent="ROOT"):
    return SimpleNamespace(
        id=branch_id,
        label=label,
        level=level,
        prior=prior,
        posterior=prior,
        parent=parent,
        status="live",
    )


def _tree():
    return SimpleNamespace(branches={
        "B1": _branch("B1", "Family 1", 1, 0.6),
        "B2": _branch("B2", "Family 2", 1, 0.3),
        "B3": _branch("B3", "Family 3", 1, 0.1),
        "B1.1": _branch("B1.1", "Disease 11", 2, 0.3, "B1"),
        "B1.2": _branch("B1.2", "Disease 12", 2, 0.3, "B1"),
        "B2.1": _branch("B2.1", "Disease 21", 2, 0.2, "B2"),
        "B2.2": _branch("B2.2", "Disease 22", 2, 0.1, "B2"),
        "B3.1": _branch("B3.1", "Disease 31", 2, 0.1, "B3"),
    })


def test_arm_blind_bundle_round_robins_facts():
    excerpts = [
        {"access_id": "A1", "fact_id": "F1", "has_compare": False},
        {"access_id": "A2", "fact_id": "F1", "has_compare": True},
        {"access_id": "B1", "fact_id": "F2", "has_compare": False},
    ]
    selected = MODULE.select_arm_blind_bundle(excerpts, limit=2)
    assert [row["access_id"] for row in selected] == ["A2", "B1"]


def test_free_top2_keeps_raw_disease_text_without_mapping():
    output = MODULE.clean_free_top2({
        "top2_diagnoses": [
            {
                "diagnosis": "Pancoast tumor",
                "reasoning_summary": "apical syndrome",
                "knowledge_access_ids": ["K1"],
            },
            {
                "diagnosis": "Cervical radiculopathy",
                "reasoning_summary": "arm symptoms",
                "knowledge_access_ids": [],
            },
        ],
    }, ["K1"])
    assert output["schema_valid"]
    assert output["top2_diagnoses"][0]["diagnosis"] == "Pancoast tumor"
    assert "id" not in output["top2_diagnoses"][0]


def test_list_top2_rejects_unknown_ids_and_citations():
    output = MODULE.clean_list_top2({
        "top_candidate_ids": ["B1", "GOLD"],
        "knowledge_access_ids": ["K2"],
    }, ["B1", "B2"], ["K1"])
    assert not output["schema_valid"]
    assert "unknown_candidate_id" in output["rejected"]
    assert "unknown_knowledge_access_id" in output["rejected"]


def test_mrr2_is_truncated_at_two():
    assert MODULE._mrr2_from_rank(1) == 1.0
    assert MODULE._mrr2_from_rank(2) == 0.5
    assert MODULE._mrr2_from_rank(3) == 0.0
    assert MODULE._mrr2_from_rank(None) == 0.0


def test_n1_runs_l1_within_between_top2_and_carries_initial_prior():
    cache = FakeCache({
        "NaiveCoTBranchOnly_L1": {
            "top_candidate_ids": ["B1", "B2"],
            "reasoning_summary": {},
            "knowledge_access_ids": [],
        },
        "NaiveCoTBranchOnly_Within": lambda payload: {
            "top_candidate_ids": [
                row["id"] for row in payload["candidates"][:2]
            ],
            "reasoning_summary": {},
            "knowledge_access_ids": [],
        },
        "NaiveCoTBranchOnly_Between": {
            "top_candidate_ids": ["B1.1", "B2.1"],
            "reasoning_summary": {},
            "knowledge_access_ids": [],
        },
    })
    record = MODULE._n1_record(
        replicate=1,
        case={"id": "case", "case_text": "vignette"},
        knowledge_chunks=[],
        knowledge_hash="kh",
        tree_state=_tree(),
        gold={
            "status": "unique",
            "acceptable_l2": [{"id": "B1.1", "parent_id": "B1"}],
        },
        cache=cache,
        prompt="prompt",
    )
    assert record["output"]["ranking"] == ["B1.1", "B2.1"]
    assert record["audit"]["top1"]
    assert [call[0] for call in cache.calls] == [
        "NaiveCoTBranchOnly_L1",
        "NaiveCoTBranchOnly_Within",
        "NaiveCoTBranchOnly_Within",
        "NaiveCoTBranchOnly_Between",
    ]
    final_candidates = record["between_stage"]["payload"]["candidates"]
    assert {row["parent_prior"] for row in final_candidates} == {0.6, 0.3}


def test_n2_changes_local_selection_but_keeps_original_arbiter():
    def local(payload):
        ids = [row["id"] for row in payload["candidates"]]
        return {
            "top_candidate_ids": ids[:2],
            "reasoning_summary": {},
            "knowledge_access_ids": [],
        }

    cache = FakeCache({
        "NaiveCoTL2Local": local,
        "NaiveCoTL2Local_OriginalChampionArbiter": {
            "ranked_candidate_ids": ["B1.1", "B2.1", "B3.1"],
            "why": {},
        },
    })
    record = MODULE._n2_record(
        replicate=1,
        case={"id": "case", "case_text": "vignette"},
        auto_asset={"full_findings": [
            {"id": "F1", "text": "one"},
            {"id": "F2", "text": "two"},
        ]},
        frozen_asset={"l1_posteriors": [
            {"id": "B1", "posterior": 0.6},
            {"id": "B2", "posterior": 0.3},
            {"id": "B3", "posterior": 0.1},
        ]},
        full_record={"trace": {
            "rounds": [{"fact_id": "F2"}, {"fact_id": "F1"}],
            "selected_fact_ids": ["F1", "F2"],
        }},
        knowledge_chunks=[],
        knowledge_hash="kh",
        tree_state=_tree(),
        gold={
            "status": "unique",
            "acceptable_l2": [{"id": "B1.1", "parent_id": "B1"}],
        },
        cache=cache,
        local_prompt="local",
        arbiter_prompt="arbiter",
    )
    assert record["selected_fact_ids"] == ["F2", "F1"]
    assert record["output"]["ranking"] == ["B1.1", "B2.1"]
    assert cache.calls[-1][0] == (
        "NaiveCoTL2Local_OriginalChampionArbiter"
    )
    assert cache.calls[-1][1]["parent_prior_mode"] == (
        "soft_parent_posterior"
    )


def test_manual_adjudication_is_only_source_of_free_text_score():
    records = [{
        "arm": MODULE.ARMS[0],
        "replicate": 1,
        "case_id": "case",
        "output": {
            "top2_diagnoses": [
                {"diagnosis": "disease one"},
                {"diagnosis": "disease two"},
            ],
        },
        "audit": None,
    }]
    MODULE._apply_manual_scores(
        records,
        {"1::case": {
            "replicate": 1,
            "case_id": "case",
            "answer_1": "disease one",
            "answer_2": "disease two",
            "best_rank": 2,
            "reviewer": "manual",
        }},
        {"case": {"status": "unique"}},
    )
    assert records[0]["audit"]["top1"] is False
    assert records[0]["audit"]["top2"] is True
    assert records[0]["audit"]["mrr2"] == 0.5


def test_frozen_manual_adjudication_validates_and_covers_all_outputs():
    fixture, rows = MODULE._manual_fixture(MODULE.MANUAL_ADJUDICATION)
    assert fixture is not None
    assert len(rows) == 51
    assert fixture["adjudication_mode"].startswith("manual")
    assert all(row["reviewer"] for row in rows.values())
