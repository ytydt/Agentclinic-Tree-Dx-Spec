from __future__ import annotations

import importlib.util
import hashlib
import json
import sys
from pathlib import Path

import pytest

from agentclinic_tree_dx.l1_evidence_bfs import L1ObservedFact
from agentclinic_tree_dx.state import DiagnosticState

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "eval_l1_evidence_bfs.py"
SPEC = importlib.util.spec_from_file_location("eval_l1_evidence_bfs_test", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
harness = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = harness
SPEC.loader.exec_module(harness)


def test_frozen_17_case_l1_contract_has_observed_cross_l1_ruleout_coverage():
    paths = (
        ROOT / "data" / "eval" / "talp_discrimination_cases.json",
        ROOT / "data" / "eval" / "talp_medxpert_expansion_cases_v2.json",
    )
    cases = [
        row
        for path in paths
        for row in json.loads(path.read_text(encoding="utf-8"))["cases"]
    ]
    assert len(cases) == 17
    covered_cases = 0
    covered_findings = 0
    track_a_eligible = 0
    for annotation in cases:
        wrapped = {"gold": annotation["gold"], "annotation": annotation}
        projection = harness._manual_projection(wrapped)
        track_a_eligible += len(projection["labels"]) >= 2
        rows = [
            row for row in projection["findings"]
            if row["role"] == "rule_out_distractor"
        ]
        if rows:
            covered_cases += 1
            covered_findings += len(rows)
    assert covered_cases == 12
    assert covered_findings == 16
    assert track_a_eligible == 16


def test_shared_tree_contract_is_complete_and_hashes_branch_payloads():
    tree_dir = harness.DEFAULT_SHARED_TREE_DIR
    paths = sorted(tree_dir.glob("*.json"))
    assert len(paths) == 17
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["tree_hash"]
        expected = hashlib.sha256(
            json.dumps(
                payload["state"]["branches"],
                ensure_ascii=False,
                sort_keys=True,
            ).encode()
        ).hexdigest()
        assert payload["tree_hash"] == expected


def test_manual_projection_collapses_same_l1_ruleout_to_shared():
    case = {
        "id": "x",
        "gold": "Gold disease",
        "annotation": {
            "l1_label": "Family A",
            "candidates": [
                {"name": "Gold disease", "l1_parent": "Family A", "is_gold": True},
                {"name": "Sibling", "l1_parent": "Family A", "is_gold": False},
                {"name": "Other", "l1_parent": "Family B", "is_gold": False},
            ],
            "findings": [
                {
                    "finding": "same-family exclusion",
                    "role": "rule_out_distractor",
                    "direction_target": "Sibling",
                    "in_vignette": True,
                },
                {
                    "finding": "cross-family exclusion",
                    "role": "rule_out_distractor",
                    "direction_target": "Other",
                    "in_vignette": True,
                },
            ],
        },
    }
    projection = harness._manual_projection(case)
    assert projection["findings"][0]["role"] == "shared_nondiscriminating"
    assert projection["findings"][1]["role"] == "rule_out_distractor"


def test_fact_catalog_excludes_non_vignette_expected_results():
    class Composed:
        @staticmethod
        def _best_reference(text, findings):
            return next(
                (row for row in findings if row["finding"] == text),
                None,
            )

    facts = harness._facts_for_case(
        DiagnosticState(case_id="case"),
        {
            "findings": [
                {"finding": "observed result", "in_vignette": True},
                {
                    "finding": "unobserved disease-specific expected result",
                    "in_vignette": False,
                },
            ],
        },
        Composed(),
        deduplicate=True,
    )
    assert [fact.text for fact in facts] == ["observed result"]


def _record(case_id: str, arm: str, rank: int) -> dict:
    return {
        "status": "OK",
        "track": "B",
        "arm": arm,
        "profile": "p5_headline",
        "prior_mode": "branch",
        "case_id": case_id,
        "gold": {
            "final": {
                "exists": True,
                "rank": rank,
                "top1": rank == 1,
            }
        },
        "metrics": {
            "select@1": True,
            "select@2": True,
            "select_valid": True,
            "ro_select@1": False,
            "ro_select@2": False,
            "selector_false_abstain": False,
            "direction_rows": [],
        },
        "profile_rule_hits": 1,
    }


def test_case_cluster_bootstrap_and_gates_use_case_pairs():
    rows = [
        _record("c1", "B1", 2),
        _record("c2", "B1", 3),
        _record("c1", "B2", 1),
        _record("c2", "B2", 1),
    ]
    summary = harness._summarize(rows, n_boot=200)
    paired = summary["paired_case_cluster_bootstrap"][
        "B::p5_headline::branch::B2-B1"
    ]
    assert paired["cases"] == 2
    assert paired["top1"]["delta"] == pytest.approx(1.0)
    assert paired["mrr"]["delta"] > 0
    assert summary["promotion_gates"]["p5_headline"]["passed"]


def test_harness_excludes_controller_and_answer_mapping():
    source = SCRIPT.read_text(encoding="utf-8")
    for forbidden in (
        "controller.run(",
        "AnswerMapper",
        "TerminationJudge",
        "force_expand_all_l1(",
    ):
        assert forbidden not in source


def test_anti_anchor_runtime_repairs_incomplete_effect_matrix():
    assert harness.ARM_SPECS["B1a"].preset == "p5_anti_anchor_direct"

    class Cache:
        def __init__(self):
            self.modules = []

        def call(self, module, prompt, payload):
            self.modules.append(module)
            row = {
                "fact_id": "F1",
                "concept_key": "decisive finding",
                "supports": ["B1"],
                "contrasts_with": ["B2"],
                "candidate_effects": {"B1": 2},
            }
            if module.endswith("Repair"):
                row["candidate_effects"]["B2"] = 0
            return {"verdict": "select", "ranked_facts": [row]}

    cache = Cache()
    selector, _, _, _ = harness._runtime_functions(
        cache, "p5_anti_anchor_direct", object(),
    )
    response = selector({
        "case_context": "case",
        "candidates": [
            {"id": "B1", "label": "A", "score": 0.5},
            {"id": "B2", "label": "B", "score": 0.5},
        ],
        "fact_catalog_core": [{"id": "F1", "text": "finding"}],
        "selection_status_by_id": {"F1": "eligible"},
        "eligible_fact_ids": ["F1"],
        "max_selected_facts": 1,
        "accounted_evidence_history": [],
        "discriminator_rules": [],
        "evidence_provenance": [],
    })
    assert response["ranked_fact_ids"] == ["F1"]
    assert response["repair_used"]
    assert cache.modules == [
        "L1AntiAnchorEvidenceSelector",
        "L1AntiAnchorEvidenceSelectorRepair",
    ]


def test_shard_merge_recomputes_case_paired_summary(tmp_path):
    merge_path = ROOT / "scripts" / "merge_l1_evidence_bfs_runs.py"
    merge_spec = importlib.util.spec_from_file_location("merge_l1_bfs_test", merge_path)
    assert merge_spec is not None and merge_spec.loader is not None
    merger = importlib.util.module_from_spec(merge_spec)
    sys.modules[merge_spec.name] = merger
    merge_spec.loader.exec_module(merger)
    run_dirs = []
    for index, case_id in enumerate(("c1", "c2"), start=1):
        run_dir = tmp_path / f"s{index}"
        trace_dir = run_dir / "traces"
        trace_dir.mkdir(parents=True)
        (run_dir / "manifest.json").write_text(json.dumps({
            "run_fingerprint": f"f{index}",
        }))
        for arm, rank in (("B1", 2 + index), ("B2", 1)):
            (trace_dir / f"{arm}.json").write_text(json.dumps(
                _record(case_id, arm, rank)
            ))
        run_dirs.append(run_dir)
    summary = merger.merge(run_dirs, tmp_path / "merged", n_boot=100)
    assert summary["completed"] == 4
    assert summary["paired_case_cluster_bootstrap"][
        "B::p5_headline::branch::B2-B1"
    ]["cases"] == 2
    assert (tmp_path / "merged" / "summary.json").is_file()


def test_depleted_pool_does_not_default_unmatched_facts_to_shared():
    projection = {
        "labels": ["A", "B"],
        "gold_branch_id": "L1",
        "findings": [
            {"finding": "explicit shared", "role": "shared_nondiscriminating"}
        ],
    }
    state = harness._manual_state("c", {
        **projection,
        "label_to_id": {"A": "L1", "B": "L2"},
        "gold_l1": "A",
    })

    class Composed:
        @staticmethod
        def _best_reference(text, findings):
            return findings[0] if text == "explicit shared" else None

    def selector(payload):
        assert payload["eligible_fact_ids"] == ["F2"]
        return {
            "verdict": "none",
            "best_fact_id": "",
            "ranked_fact_ids": [],
        }

    result = harness._depleted_false_select(
        global_selector=selector,
        preset="bfs_sparse",
        state=state,
        case_context="case",
        facts=(
            L1ObservedFact("F1", "unmatched"),
            L1ObservedFact("F2", "explicit shared"),
        ),
        blocks={},
        projection=projection,
        composed=Composed(),
    )
    assert result is False


def test_cached_llm_keys_include_effective_temperature(tmp_path):
    class FakeLLM:
        def __init__(self, temperature):
            self.temperature = temperature
            self.calls = 0

        def call_module(self, module, prompt, payload):
            self.calls += 1
            return {"temperature": self.temperature, "calls": self.calls}

    cache_path = tmp_path / "llm_cache.json"
    zero_llm = FakeLLM(0.0)
    default_llm = FakeLLM(None)
    zero = harness.CachedLLM(zero_llm, cache_path, "model")
    assert zero.call("module", "prompt", {"x": 1})["temperature"] == 0.0
    default = harness.CachedLLM(default_llm, cache_path, "model")
    assert default.call("module", "prompt", {"x": 1})["temperature"] is None
    assert zero_llm.calls == 1
    assert default_llm.calls == 1
