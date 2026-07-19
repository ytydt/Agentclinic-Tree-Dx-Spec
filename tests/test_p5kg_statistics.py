"""Synthetic regression tests for P5KG statistical and quality gates."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_script(name: str):
    spec = importlib.util.spec_from_file_location(
        f"test_{name}", ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


SUMMARIZER = _load_script("summarize_talp_typed_ladder")
REGRESSION = _load_script("talp_regression_gate")
QUALITY = _load_script("cceg_quality_gate")


def _row(case_id: str, *, ok: bool, shared: bool, select: bool = True) -> dict:
    return {
        "id": case_id,
        "n_decisive": 1,
        "select@1": select,
        "select_match": select,
        "select_valid": select,
        "provenance_coverage": 1.0,
        "direction": [
            {"kind": "rulein", "ok": ok, "got": "gold" if ok else "none"},
            {"kind": "ruleout", "ok": ok, "got": "other" if ok else "none"},
            {"kind": "shared", "ok": shared,
             "got": "none" if shared else "gold"},
        ],
    }


def _write(path: Path, rows: list[dict], **extra) -> Path:
    path.write_text(json.dumps({"rows": rows, **extra}))
    return path


def test_p5kg_summary_discovers_g0_and_clusters_multiple_seeds(tmp_path):
    for seed in (7, 11):
        _write(
            tmp_path / f"talp_discrim_p5kg_g0_s{seed}r0_dv2_p5.json",
            [_row("case-a", ok=False, shared=False),
             _row("case-b", ok=False, shared=False)])
        _write(
            tmp_path / f"talp_discrim_p5kg_g1_s{seed}r0_dv2_p5.json",
            [_row("case-a", ok=True, shared=True),
             _row("case-b", ok=True, shared=True)])

    grouped = SUMMARIZER.discover_files(tmp_path, "p5kg")
    result = SUMMARIZER.summarize_family(
        grouped, family="p5kg", baseline="g0", n_boot=200)

    assert set(grouped) == {"g0", "g1"}
    assert result["baseline"] == "g0"
    assert result["arms"]["g1"]["sampling"] == {
        "case_clusters": 2, "seed_case_rows": 4, "files": 2}
    assert result["paired_delta"]["g1"]["DIRECTION"]["delta"] == 1.0
    assert result["paired_delta"]["g1"]["DIRECTION"]["ci"] == [1.0, 1.0]


def test_research_summary_reuses_baseline_without_polluting_clinical(tmp_path):
    _write(
        tmp_path / "talp_discrim_p5kg_g0_s7r0_dv2_p5.json",
        [_row("case-a", ok=False, shared=False)])
    _write(
        tmp_path / "talp_discrim_p5kg_research_g2cr_s7r0_dv2_p5.json",
        [_row("case-a", ok=True, shared=True)])

    clinical = SUMMARIZER.discover_files(tmp_path, "p5kg")
    research = SUMMARIZER.discover_files(tmp_path, "p5kg_research")

    assert set(clinical) == {"g0"}
    assert set(research) == {"g0", "g2cr"}


def test_strict_p5kg_regression_gate_passes_complete_candidate(tmp_path):
    baseline = _write(
        tmp_path / "base.json",
        [_row("a", ok=True, shared=False)],
        false_organism_attribution=0)
    candidate = _write(
        tmp_path / "candidate.json",
        [_row("a", ok=True, shared=True)],
        false_organism_attribution=0)

    base = REGRESSION._rates([baseline])
    cand = REGRESSION._rates([candidate])
    assert REGRESSION.evaluate(base, cand, strict_p5kg=True) == []


def test_strict_p5kg_regression_gate_blocks_all_new_safety_failures(tmp_path):
    baseline = _write(
        tmp_path / "base.json",
        [_row("a", ok=True, shared=False)],
        false_organism_attribution=0)
    bad_row = _row("a", ok=False, shared=False, select=False)
    bad_row["provenance_coverage"] = 50.0  # percentage form is also supported
    candidate = _write(
        tmp_path / "candidate.json", [bad_row],
        false_organism_attribution=1)

    failures = REGRESSION.evaluate(
        REGRESSION._rates([baseline]),
        REGRESSION._rates([candidate]),
        strict_p5kg=True)
    assert any("direction drop" in failure for failure in failures)
    assert any("ruleout drop" in failure for failure in failures)
    assert any("select_valid drop" in failure for failure in failures)
    assert any("shared gain" in failure for failure in failures)
    assert any("provenance coverage" in failure for failure in failures)
    assert any("pathogen false attribution" in failure for failure in failures)


def test_legacy_regression_gate_does_not_enable_p5kg_checks(tmp_path):
    baseline = _write(
        tmp_path / "base.json", [_row("a", ok=True, shared=True)])
    candidate_row = _row("a", ok=True, shared=False)
    candidate_row["provenance_coverage"] = 0.0
    candidate = _write(
        tmp_path / "candidate.json", [candidate_row],
        false_organism_attribution=3)

    assert REGRESSION.evaluate(
        REGRESSION._rates([baseline]),
        REGRESSION._rates([candidate])) == []


def test_research_gate_requires_lane_and_hydration(tmp_path):
    baseline = _write(
        tmp_path / "base.json", [_row("a", ok=True, shared=False)])
    candidate = _write(
        tmp_path / "candidate.json", [_row("a", ok=True, shared=True)],
        evidence_lane="research", research_evidence_mode="composed",
        hydration_coverage=1.0)
    failures = REGRESSION.evaluate(
        REGRESSION._rates([baseline]), REGRESSION._rates([candidate]),
        research_lane=True)
    assert failures == []


def test_quality_gate_passes_only_when_all_three_reports_pass():
    passed = QUALITY.combine_reports(
        {"publishable": True}, {"passed": True}, {"passed": True})
    blocked = QUALITY.combine_reports(
        {"publishable": True}, {"passed": False, "failures": ["low recall"]},
        {"passed": True})

    assert passed["passed"] is True
    assert blocked["passed"] is False
    assert blocked["failures"][0]["component"] == "retrieval"


def test_quality_gate_fails_closed_for_unmarked_report():
    result = QUALITY.combine_reports(
        {"publishable": True}, {"recall_at_k": 1.0}, {"passed": True})
    assert result["passed"] is False
    assert result["components"]["retrieval"]["passed"] is False
