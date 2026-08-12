from pathlib import Path

from analysis.mechanism_v2.common import FrozenExactSynonymBridge, ROOT
from analysis.mechanism_v2.e14x_runtime_gate import exact_mcnemar, novel_labels, selector_kind


def test_exact_mcnemar_two_sided_tail() -> None:
    assert exact_mcnemar(0, 0) == 1.0
    assert exact_mcnemar(1, 10) == 0.01171875


def test_novel_labels_respect_frozen_synonym_identity() -> None:
    bridge = FrozenExactSynonymBridge(ROOT / "data/knowledge_raw/disease_name_bridge.json")
    assert novel_labels(["pulmonary embolism", "brand new label"], ["Pulmonary embolism"], bridge) == ["brand new label"]


def test_selector_kind_distinguishes_a5() -> None:
    assert selector_kind({"a5": {"champion": "x"}}) == "pairwise_a5"
    assert selector_kind({"selector": {"champion": "x"}}) == "evidence_selector"
    assert selector_kind({}) == "missing_selector_trace"


def test_full_run_artifact_shape_when_present() -> None:
    path = ROOT / "analysis/mechanism_v2/results/E14x_runtime_gate/analysis_summary_pre_manual.json"
    if not Path(path).exists():
        return
    import json

    summary = json.loads(Path(path).read_text(encoding="utf-8"))
    assert summary["n_paired"] == 300
    assert summary["n_attrition"] == 0
    assert summary["gate_cost"]["trigger_n"] > 0
    assert summary["comparability"]["upstream_g1_g2_identical_n"] <= 300

