from __future__ import annotations

import json
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "eval_partial_flow_talp17",
    ROOT / "scripts" / "eval_partial_flow_talp17.py",
)
assert SPEC is not None and SPEC.loader is not None
harness = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(harness)


def _fixture_cases() -> list[dict]:
    return [
        {
            "id": f"case{i:02d}",
            "corpus": "fixture",
            "source_case_idx": i,
            "gold": f"gold {i}",
            "gold_option": f"option {i}",
            "case_text": f"vignette {i}\n\nOptions:\nA. option {i}\n",
            "annotation": {},
        }
        for i in range(17)
    ]


def test_assembles_nine_base_and_eight_expansion(monkeypatch):
    base = json.loads(harness.BASE_CASES_PATH.read_text(encoding="utf-8"))["cases"]
    source = [
        {
            "q": f"question for {row['id']}",
            "options": {"A": row["gold_option"], "B": "distractor"},
            "answer": row["gold_option"],
        }
        for row in base
    ]
    monkeypatch.setattr(
        harness,
        "_pipeline_module",
        lambda: SimpleNamespace(
            build_case_text=lambda case: harness._options_text(
                case["q"], case["options"]
            )
        ),
    )

    cases = harness.assemble_cases(medbullets_cases=source)

    assert len(cases) == 17
    assert len({case["id"] for case in cases}) == 17
    assert sum(case["corpus"] == "medbullets" for case in cases) == 9
    assert sum(case["id"].startswith("mxh") for case in cases) == 8
    assert all("\n\nOptions:\n" in case["case_text"] for case in cases)


def test_profile_and_partial_overrides_reuse_production_builder():
    captured = {}

    def builder(model, branch_mode, config_overrides):
        captured.update({
            "model": model,
            "branch_mode": branch_mode,
            "overrides": dict(config_overrides),
        })
        config = SimpleNamespace(**config_overrides)
        return object(), object(), config, {"last": None}

    _, _, config, _ = harness.build_profile_controller(
        "fixture-model",
        "g2ur",
        max_timesteps=2,
        force_expand_all_l1=True,
        controller_builder=builder,
    )

    assert captured["branch_mode"] == "recall_hints_gap"
    assert captured["overrides"] == {
        "talp_disc_profile": "g2ur",
        "partial_flow": True,
        "max_timesteps": 2,
        "force_expand_all_l1": True,
        "stop_after_evidence": True,
    }
    assert config.talp_disc_profile == "g2ur"


class _FakeEnv:
    def set_case(self, text):
        self.case = text


class _FakeController:
    def __init__(self, calls):
        self.calls = calls

    def run(self, state):
        self.calls.append(state.case_id)
        return {
            "trace_type": "partial_controller",
            "partial": True,
            "stop_reason": "max_timesteps_post_evidence",
            "timesteps_completed": 2,
            "turns": [
                {"timestep": 1, "checkpoint": "turn_complete"},
                {"timestep": 2, "checkpoint": "post_evidence"},
            ],
            "tree_snapshots": {},
            "l1_tree": [{"id": "B1", "label": "fixture family"}],
            "l2_tree": [{"id": "B1.1", "label": "fixture leaf"}],
            "l1_expansion_audit": {
                "l1_total": 1,
                "l1_expanded": 1,
                "l1_expansion_rate": 1.0,
            },
            "discrimination_audit": [
                {
                    "phase": "evidence_annotator",
                    "timestep": 1,
                    "discriminator_rules": [{"effect": "rule_in"}],
                    "ruleout_rules": [],
                    "evidence_provenance": [{"claim_id": "c1"}],
                },
                {
                    "phase": "evidence_annotator",
                    "timestep": 2,
                    "discriminator_rules": [],
                    "ruleout_rules": [{"effect": "rule_out"}],
                    "evidence_provenance": [],
                },
            ],
            "answer_mapper_called": False,
        }


def test_atomic_trace_and_resume_do_not_rerun(tmp_path):
    calls = []

    def builder(model, branch_mode, config_overrides):
        return (
            _FakeController(calls),
            _FakeEnv(),
            SimpleNamespace(**config_overrides),
            {"last": {"mode": "recall_hints"}},
        )

    kwargs = {
        "output_dir": tmp_path,
        "tag": "resume",
        "profiles": ("p5_headline",),
        "limit": 1,
        "assembled_cases": _fixture_cases(),
        "controller_builder": builder,
        "judge_factory": lambda model: (lambda gold, labels: 0),
    }
    summary, _ = harness.run_harness(**kwargs)
    trace_path = tmp_path / "resume" / "traces" / "p5_headline__case00.json"

    assert summary["written_traces"] == 1
    assert trace_path.is_file()
    assert not list(trace_path.parent.glob("*.tmp"))
    first = json.loads(trace_path.read_text(encoding="utf-8"))
    assert first["status"] == "OK"
    assert first["metrics"]["evidence_annotator_coverage"] == 1.0
    assert calls == ["p5_headline::case00"]

    resumed, _ = harness.run_harness(**kwargs, resume=True)
    assert resumed["written_traces"] == 1
    assert calls == ["p5_headline::case00"]


def test_summary_aggregates_partial_metrics_without_answer_metrics():
    records = [
        {
            "status": "OK",
            "profile": "p5_headline",
            "duration_seconds": 1.25,
            "metrics": {
                "l1_recall": True,
                "l1_expansion_rate": 1.0,
                "l2_leaf_count": 3,
                "evidence_annotator_coverage": 1.0,
                "profile_rule_hits": 2,
                "profile_provenance_hits": 1,
            },
        },
        {
            "status": "ERROR",
            "profile": "p5_headline",
            "duration_seconds": 0.5,
            "error": "fixture",
        },
    ]

    summary = harness.summarize(records, planned=2)

    assert summary["planned_traces"] == 2
    assert summary["overall"]["completed"] == 1
    assert summary["overall"]["errors"] == 1
    assert summary["overall"]["l1_recall"] == pytest.approx(1.0)
    assert summary["overall"]["l1_expansion_rate"] == pytest.approx(1.0)
    assert summary["overall"]["l2_leaf_count"] == 3
    assert "answer" not in json.dumps(summary).lower()
