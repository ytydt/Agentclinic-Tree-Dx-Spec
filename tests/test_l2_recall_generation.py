from __future__ import annotations

from types import SimpleNamespace

import pytest

from agentclinic_tree_dx.adapters.mock_env import MockAgentClinicEnv
from agentclinic_tree_dx.config import ControllerConfig
from agentclinic_tree_dx.controller import AgentClinicTreeController
from agentclinic_tree_dx.prompting import load_module_prompt
from agentclinic_tree_dx.state import Branch, DiagnosticState, RootNode


def _branch(bid: str, label: str) -> Branch:
    return Branch(
        id=bid,
        label=label,
        parent="ROOT",
        level=1,
        status="live",
        prior=0.5,
        posterior=0.5,
        danger=0.1,
        actionability=0.0,
        explanatory_coverage=0.0,
        classification_axis="etiology",
    )


def _state(*parents: Branch) -> DiagnosticState:
    state = DiagnosticState(
        case_id="case-1",
        case_summary="Young adult with fever, rash, and severe abdominal pain.",
        root=RootNode(
            label="systemic inflammatory syndrome",
            time_course="acute",
            severity="severe",
            confidence=0.8,
            salient_findings=["fever", "rash", "abdominal pain"],
        ),
    )
    state.branches = {parent.id: parent for parent in parents}
    state.frontier = [parent.id for parent in parents]
    return state


def _subbranches(parent_id: str, labels: list[str]) -> dict:
    return {
        "needs_expansion": True,
        "reason_if_not": "",
        "sub_branches": [
            {
                "id": f"{parent_id}.{index}",
                "label": label,
                "parent_id": parent_id,
                "level": 2,
                "level_role": "specific_disease",
                "classification_axis": "etiology",
                "status": "live",
                "prior_estimate": 1 / len(labels),
                "danger": 0.1,
            }
            for index, label in enumerate(labels, start=1)
        ],
        "need_external_knowledge": False,
    }


class _Retriever:
    is_ready = True

    def __init__(self, hits):
        self.hits = hits
        self.calls = []

    def search(self, query, **kwargs):
        self.calls.append((query, kwargs))
        return [dict(hit) for hit in self.hits]


class _Source:
    def __init__(self, ranking, hits=None):
        self.ranking = ranking
        self.calls = []
        self._r = _Retriever(hits or []) if hits is not None else None

    def recall(self, syndrome, **kwargs):
        self.calls.append((syndrome, kwargs))
        return dict(self.ranking)


class _L2LLM:
    def __init__(self):
        self.calls = []
        self.repair_labels: list[str] | None = None

    def call_module(self, module_name, prompt, payload):
        self.calls.append((module_name, prompt, payload))
        if module_name == "LLMDdxEntrance":
            return {"differentials": ["Disease C", "Disease D"]}
        if module_name == "L2RecallParentAssign":
            return {
                "assignments": [
                    {"disease": "Disease A", "parent_ids": ["B1"]},
                    {"disease": "Disease B", "parent_ids": ["B2"]},
                ]
            }
        if module_name == "RecallGapAssign":
            return {
                "assignments": [
                    {"candidate": candidate["disease"], "index": -1}
                    for candidate in payload.get("recall_candidates", [])
                ]
            } if "recall_candidates" in payload else {
                "assignments": [
                    {"candidate": "Disease C", "index": -1}
                ]
            }
        if module_name == "L2RecallCreator":
            parent_id = payload["parent_branch"]["id"]
            if payload.get("repair"):
                return _subbranches(
                    parent_id,
                    self.repair_labels
                    or ["Disease A", "Disease B", "Disease C"],
                )
            diseases = [
                row["disease"] for row in payload["recall_candidates"][:2]
            ]
            return _subbranches(parent_id, diseases)
        raise AssertionError(f"unexpected module: {module_name}")


def _controller(config: ControllerConfig, llm=None) -> AgentClinicTreeController:
    return AgentClinicTreeController(
        env=SimpleNamespace(),
        llm=llm,
        config=config,
    )


def test_default_none_preserves_legacy_module_and_payload():
    seen = []
    parent = _branch("B1", "Inflammatory")
    state = _state(parent)
    expected_state = state.project_for("SubBranchCreator")

    def response(payload):
        seen.append(payload)
        return _subbranches("B1", ["Disease A", "Disease B"])

    env = MockAgentClinicEnv(
        module_responses={"SubBranchCreator": response}
    )
    controller = AgentClinicTreeController(
        env,
        config=ControllerConfig(talp_disc_profile="off"),
    )
    result = controller.expand_branch(state, parent)

    assert "l2_recall_audit" not in result
    assert seen == [{
        "state": expected_state,
        "parent_branch": {
            "id": "B1",
            "label": "Inflammatory",
            "level": 1,
            "posterior": 0.5,
            "danger": 0.1,
            "evidence_for": [],
            "evidence_against": [],
            "unresolved_questions": [],
            "askable_discriminators": [],
            "requestable_discriminators": [],
        },
        "target_level": 2,
    }]


def test_per_parent_rrf_has_parent_query_source_rank_and_provenance():
    llm = _L2LLM()
    config = ControllerConfig(
        talp_disc_profile="off",
        l2_branch_generation_mode="per_parent",
        l2_recall_candidate_budget=6,
        l2_recall_snippet_budget=7,
        enable_llm_ddx_branch_entrance=True,
    )
    controller = _controller(config, llm)
    case_source = _Source(
        {"Disease A": 0.9, "Disease B": 0.8},
        hits=[{
            "id": "case-1",
            "title": "Inflammatory case report",
            "content": "Disease A is a differential diagnosis.",
            "chunk_type": "differential",
            "score": 0.9,
        }],
    )
    cpg_source = _Source(
        {"disease a": 1.0, "Disease C": 0.7},
        hits=[{
            "id": "cpg-1",
            "title": "Inflammatory > Differential Diagnosis",
            "content": "Disease C and Disease A should be considered.",
            "chunk_type": "differential",
            "score": 0.8,
        }],
    )
    controller._case_report_source = case_source
    controller._cpg_branch_source = cpg_source
    parent = _branch("B1", "Inflammatory")
    state = _state(parent)

    result = controller.expand_branch(state, parent)
    creator_payload = next(
        payload for name, _prompt, payload in llm.calls
        if name == "L2RecallCreator"
    )
    candidates = creator_payload["recall_candidates"]
    disease_a = next(
        row for row in candidates if row["disease"].casefold() == "disease a"
    )

    assert case_source.calls[0][0].startswith(
        "Inflammatory within systemic inflammatory syndrome"
    )
    assert "Young adult with fever" in case_source.calls[0][1]["context"]
    assert case_source.calls[0][1]["top_k"] == 7
    assert disease_a["source_rank"] == {"case_report": 1, "cpg": 1}
    assert {p["source"] for p in disease_a["provenance"]} == {
        "case_report", "cpg"
    }
    assert len({
        row["disease"].casefold() for row in candidates
    }) == len(candidates)
    assert result["l2_recall_audit"]["mode"] == "per_parent"
    assert controller.get_l2_recall_audit()[0]["candidates"]
    assert creator_payload["knowledge_fragments"]
    assert len(creator_payload["knowledge_fragments"]) <= 7
    assert set(creator_payload["knowledge_fragments"][0]) == {
        "source", "title", "content", "id"
    }


def test_recall_creator_ids_are_rebound_to_actual_parent_namespace():
    llm = _L2LLM()
    controller = _controller(
        ControllerConfig(
            talp_disc_profile="off",
            l2_branch_generation_mode="per_parent",
        ),
        llm,
    )
    controller._case_report_source = _Source({
        "Disease A": 1.0,
        "Disease B": 0.9,
    })
    parent = _branch("B2", "Neoplastic")
    state = _state(parent)

    original_call = llm.call_module

    def copied_example_ids(module, prompt, payload):
        if module == "L2RecallCreator":
            return _subbranches("B1", ["Disease A", "Disease B"])
        return original_call(module, prompt, payload)

    llm.call_module = copied_example_ids
    result = controller.expand_branch(state, parent)

    assert [row["id"] for row in result["sub_branches"]] == ["B2.1", "B2.2"]
    assert [row["parent_id"] for row in result["sub_branches"]] == ["B2", "B2"]
    assert parent.children == ["B2.1", "B2.2"]
    assert set(state.branches) == {"B2", "B2.1", "B2.2"}
    assert result["l2_recall_audit"]["child_ids_rewritten"] is True


def test_public_case_asset_matches_l1_sources_and_contains_bounded_fragments():
    controller = _controller(
        ControllerConfig(
            talp_disc_profile="off",
            l2_branch_generation_mode="reuse_l1",
            l2_recall_snippet_budget=3,
            branch_recall_hints_cap=24,
        ),
        _L2LLM(),
    )
    ranking = {f"Disease {index:02d}": 30 - index for index in range(30)}
    case_hits = [{
        "id": f"case-{index}",
        "title": "Systemic inflammatory syndrome case report",
        "content": f"Disease {index:02d} presented with fever and rash.",
        "chunk_type": "differential",
        "score": 1.0 - index / 100,
    } for index in range(5)]
    cpg_hits = [{
        "id": f"cpg-{index}",
        "title": "Systemic inflammatory syndrome > Differential Diagnosis",
        "content": f"Consider Disease {index:02d} in the differential.",
        "chunk_type": "differential",
        "score": 1.0 - index / 100,
    } for index in range(5)]
    controller._case_report_source = _Source(ranking, hits=case_hits)
    controller._cpg_branch_source = _Source(ranking, hits=cpg_hits)
    state = _state(_branch("B1", "Inflammatory"))

    asset = controller.build_l2_case_recall_asset(state)
    l1_hints = controller._build_recall_hints(state)

    assert asset["asset_version"] == "l2_case_recall_v1"
    assert len(asset["candidates"]) == 24
    assert [row["disease"] for row in asset["candidates"]] == (
        l1_hints["candidate_diseases"]
    )
    assert asset["candidates"][0]["source_rank"] == {
        "case_report": 1, "cpg": 1
    }
    assert len(asset["knowledge_fragments"]) == 3
    assert {
        fragment["source"] for fragment in asset["knowledge_fragments"]
    } == {"case_report", "cpg"}
    assert all(
        set(fragment) == {"source", "title", "content", "id"}
        for fragment in asset["knowledge_fragments"]
    )
    assert all(
        kwargs["top_k"] == 3
        for _query, kwargs in (
            controller._case_report_source._r.calls
            + controller._cpg_branch_source._r.calls
        )
    )
    source_calls_before = (
        len(controller._case_report_source.calls),
        len(controller._cpg_branch_source.calls),
    )
    retriever_calls_before = (
        len(controller._case_report_source._r.calls),
        len(controller._cpg_branch_source._r.calls),
    )
    controller.freeze_l2_recall_asset(asset)
    controller.expand_branch(state, state.branches["B1"])
    assert source_calls_before == (
        len(controller._case_report_source.calls),
        len(controller._cpg_branch_source.calls),
    )
    assert retriever_calls_before == (
        len(controller._case_report_source._r.calls),
        len(controller._cpg_branch_source._r.calls),
    )


def test_reuse_l1_maps_once_and_never_calls_parent_retrieval():
    llm = _L2LLM()
    controller = _controller(
        ControllerConfig(
            talp_disc_profile="off",
            l2_branch_generation_mode="reuse_l1",
        ),
        llm,
    )
    forbidden_source = _Source({})

    def forbidden(*args, **kwargs):
        raise AssertionError("reuse_l1 must not retrieve below a parent")

    forbidden_source.recall = forbidden
    controller._case_report_source = forbidden_source
    controller._cpg_branch_source = forbidden_source
    frozen = controller.freeze_l2_recall_asset({
        "asset_version": "l2_case_recall_v1",
        "candidates": [
            {
                "disease": "Disease A",
                "source_rank": {"case_report": 1},
                "provenance": [{"source": "case_report", "rank": 1}],
            },
            {
                "disease": "Disease B",
                "source_rank": {"cpg": 2},
                "provenance": [{"source": "cpg", "rank": 2}],
            },
        ],
        "knowledge_fragments": [{
            "source": "cpg",
            "title": "Inflammatory differential",
            "content": "Disease A is supported by this guideline.",
            "id": "frag-1",
        }],
    })
    first = _branch("B1", "Inflammatory")
    second = _branch("B2", "Neoplastic")
    state = _state(first, second)

    result_1 = controller.expand_branch(state, first)
    result_2 = controller.expand_branch(state, second)

    assert [
        name for name, _prompt, _payload in llm.calls
    ].count("L2RecallParentAssign") == 1
    assert result_1["l2_recall_audit"]["retrieval_calls"] == 0
    assert result_2["l2_recall_audit"]["retrieval_calls"] == 0
    assert result_1["l2_recall_audit"]["mapping_calls"] == 1
    assert result_2["l2_recall_audit"]["mapping_calls"] == 0
    assert frozen["knowledge_fragments"][0]["id"] == "frag-1"
    creator_payloads = [
        payload for name, _prompt, payload in llm.calls
        if name == "L2RecallCreator"
    ]
    assert creator_payloads[0]["knowledge_fragments"] == (
        frozen["knowledge_fragments"]
    )


def test_shared_gap_repair_dedupes_and_preserves_existing_coverage():
    llm = _L2LLM()
    controller = _controller(
        ControllerConfig(
            talp_disc_profile="off",
            l2_branch_generation_mode="per_parent",
            l2_recall_gap_fill=True,
        ),
        llm,
    )
    controller._case_report_source = _Source({
        "Disease A": 1.0,
        "Disease B": 0.9,
        "Disease C": 0.8,
    })
    parent = _branch("B1", "Inflammatory")
    state = _state(parent)

    result = controller.expand_branch(state, parent)

    assert [row["label"] for row in result["sub_branches"]] == [
        "Disease A", "Disease B", "Disease C"
    ]
    audit = result["l2_recall_audit"]
    assert audit["gap_fill"] == "repair_accepted"
    assert audit["repair_no_shrink"] is True
    assert audit["repair_no_coverage_loss"] is True


def test_gap_repair_rejects_equal_or_larger_result_that_loses_coverage():
    llm = _L2LLM()
    llm.repair_labels = ["Disease A", "Disease C", "Disease D"]
    controller = _controller(
        ControllerConfig(
            talp_disc_profile="off",
            l2_branch_generation_mode="per_parent",
            l2_recall_gap_fill=True,
        ),
        llm,
    )
    controller._case_report_source = _Source({
        "Disease A": 1.0,
        "Disease B": 0.9,
        "Disease C": 0.8,
    })
    parent = _branch("B1", "Inflammatory")

    result = controller.expand_branch(_state(parent), parent)

    assert [row["label"] for row in result["sub_branches"]] == [
        "Disease A", "Disease B"
    ]
    audit = result["l2_recall_audit"]
    assert audit["gap_fill"] == "repair_rejected"
    assert audit["repair_no_shrink"] is True
    assert audit["repair_no_coverage_loss"] is False


def test_prompt_loads_and_gold_fields_are_rejected():
    assert "concrete, canonical disease entity" in load_module_prompt(
        "L2RecallCreator"
    )
    controller = _controller(ControllerConfig(talp_disc_profile="off"))
    with pytest.raises(ValueError, match="gold/answer"):
        controller.freeze_l2_recall_asset({
            "gold_diagnosis": "Disease A",
            "candidates": ["Disease A"],
        })


def test_l1_recall_payload_remains_string_only_without_provenance():
    config = ControllerConfig(
        talp_disc_profile="off",
        enable_llm_ddx_branch_entrance=False,
        branch_recall_hints_cap=4,
    )
    controller = _controller(config)
    controller._case_report_source = _Source({"Disease A": 1.0})
    controller._cpg_branch_source = _Source({"Disease B": 1.0})
    block = controller._build_recall_hints(_state(_branch("B1", "X")))

    assert set(block) == {
        "recall_hints_mode",
        "candidate_diseases",
        "syndrome_matched",
        "n_entrances",
    }
    assert all(isinstance(item, str) for item in block["candidate_diseases"])
