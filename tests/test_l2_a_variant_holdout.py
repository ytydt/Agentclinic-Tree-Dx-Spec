from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import build_l2_a_variant_holdout as holdout  # noqa: E402


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def test_seal_and_verify_roundtrip():
    sealed = holdout.seal_payload({"frozen": True, "status": "blocked", "n": 0})
    holdout.verify_sealed(sealed, label="roundtrip")
    drifted = copy.deepcopy(sealed)
    drifted["n"] = 1
    with pytest.raises(ValueError, match="hash drift"):
        holdout.verify_sealed(drifted, label="drifted")


def test_development_fingerprints_cover_protocol_ids():
    protocol = holdout.load_protocol()
    fps = holdout.collect_development_fingerprints(protocol)
    assert set(fps) == set(holdout.development_case_ids(protocol))
    assert len(fps) == 17


def test_build_blocks_when_legal_pool_below_minimum(tmp_path: Path):
    fixture = tmp_path / "l2_a_variant_holdout_v1.json"
    blocked = tmp_path / "blocked_manifest.json"
    interface = tmp_path / "execution_interface.json"

    result = holdout.run_build(
        fixture_path=fixture,
        blocked_manifest_path=blocked,
        execution_interface_path=interface,
        winner_path=tmp_path / "missing_winner.json",
    )

    assert result["status"] == "blocked"
    assert result["promotion_eligible"] is False
    assert result["case_count"] == 0
    assert result["development_overlap_count"] == 0
    assert result["available_legal_candidates"] < holdout.MIN_CASES
    assert result["gap_to_minimum"] == (
        holdout.MIN_CASES - result["available_legal_candidates"]
    )
    assert result["execution_ready"] is False
    assert blocked.exists()

    doc = json.loads(fixture.read_text(encoding="utf-8"))
    holdout.verify_sealed(doc, label="fixture")
    assert doc["frozen"] is True
    assert doc["status"] == "blocked"
    assert doc["promotion_eligible"] is False
    assert doc["cases"] == []
    assert doc["case_ids"] == []
    assert doc["development_overlap_count"] == 0
    assert doc["algorithm_outputs_present"] is False
    assert "refusing_to_fabricate_holdout_cases" in doc["blockers"]

    manifest = json.loads(blocked.read_text(encoding="utf-8"))
    holdout.verify_sealed(manifest, label="blocked manifest")
    assert manifest["promotion_eligible"] is False
    assert manifest["available_legal_candidates"] == doc["available_legal_candidates"]
    assert manifest["gap_to_minimum"] == doc["gap_to_minimum"]

    iface = json.loads(interface.read_text(encoding="utf-8"))
    holdout.verify_sealed(iface, label="interface")
    assert iface["arms"] == ["C-prod", "frozen_development_winner"]
    assert iface["ready_to_execute"] is False
    assert iface["pre_run_forbidden_until_ready"] is True
    with pytest.raises(RuntimeError, match="not ready"):
        holdout.assert_execution_ready(iface)


def test_build_is_reproducible(tmp_path: Path):
    a_fix = tmp_path / "a"
    b_fix = tmp_path / "b"
    a = holdout.run_build(
        fixture_path=a_fix / "holdout.json",
        blocked_manifest_path=a_fix / "blocked.json",
        execution_interface_path=a_fix / "interface.json",
        winner_path=a_fix / "winner.json",
    )
    b = holdout.run_build(
        fixture_path=b_fix / "holdout.json",
        blocked_manifest_path=b_fix / "blocked.json",
        execution_interface_path=b_fix / "interface.json",
        winner_path=b_fix / "winner.json",
    )
    assert a["fixture_hash"] == b["fixture_hash"]
    assert a["blocked_manifest_hash"] == b["blocked_manifest_hash"]
    assert a["available_legal_candidates"] == b["available_legal_candidates"]


def test_evaluate_legality_excludes_development_and_raw_pools():
    protocol = holdout.load_protocol()
    dev_ids = holdout.development_case_ids(protocol)
    dev_fps = holdout.collect_development_fingerprints(protocol)
    pools = holdout.inventory_candidate_pools()
    legality = holdout.evaluate_legality(
        pools, development_ids=dev_ids, development_fps=dev_fps,
    )

    assert legality["development_overlap_count"] == 0
    assert legality["legal_candidate_count"] == 0
    reasons = legality["exclusion_reason_counts"]
    assert reasons.get("development_case_id", 0) >= 17
    assert reasons.get("medbullets_hard_full_diagnosis_pool_historically_run", 0) >= 25
    assert reasons.get("uncalibrated_raw_tsv_not_talp_legal", 0) >= 80

    legal_ids = {row["case_id"] for row in legality["legal_candidates"]}
    assert legal_ids.isdisjoint(set(dev_ids))


def test_sealed_path_requires_min_cases_and_strips_algorithm_outputs():
    protocol = holdout.load_protocol()
    fake_legal = []
    for index in range(holdout.MIN_CASES):
        fake_legal.append({
            "case_id": f"hold_{index:03d}",
            "case_source": "synthetic_source",
            "source_path": "test",
            "source_index": index,
            "vignette": f"A {20 + index}-year-old patient presents with finding {index}.",
            "gold": f"Disease {index}",
            "gold_option": f"Disease {index}",
            "syndrome_type": "syndrome_a" if index % 2 == 0 else "syndrome_b",
            "parent_complexity": "low" if index % 3 else "high",
            "rare_disease_fraction": 0.1 if index % 4 else 0.6,
            "calibration_status": "literature_reviewed",
            "content_fingerprint": holdout.content_fingerprint(
                vignette=f"vignette {index}",
                gold=f"Disease {index}",
                gold_option=f"Disease {index}",
            ),
            "tree": {"branches": {"B1": {}}},  # must be stripped
            "tree_hash": "should-not-survive",
        })
    selection = holdout.stratified_select(fake_legal)
    legality = {
        "legal_candidates": fake_legal,
        "legal_candidate_count": len(fake_legal),
        "exclusions": [],
        "exclusion_reason_counts": {},
        "development_overlap_case_ids": [],
        "development_overlap_count": 0,
        "scanned_candidate_count": len(fake_legal),
        "historical_scheme_selection_case_id_count": 0,
    }
    pools = {
        "synthetic": {
            "candidate_count": len(fake_legal),
            "candidates": fake_legal,
        }
    }
    doc = holdout.build_holdout_document(
        protocol=protocol,
        pools=pools,
        legality=legality,
        selection=selection,
        builder_code_sha256="abc",
    )
    holdout.verify_sealed(doc, label="synthetic sealed")
    assert doc["status"] == "sealed"
    assert doc["case_count"] == holdout.MIN_CASES
    assert doc["promotion_eligible"] is False
    assert doc["algorithm_outputs_present"] is False
    assert all("tree" not in case for case in doc["cases"])
    assert all("tree_hash" not in case for case in doc["cases"])
    assert all(
        set(case["strata"]) == set(holdout.STRATIFICATION_AXES)
        for case in doc["cases"]
    )


def test_prepare_execution_refuses_without_frozen_winner(tmp_path: Path):
    fixture = tmp_path / "holdout.json"
    interface = tmp_path / "interface.json"
    holdout.run_build(
        fixture_path=fixture,
        blocked_manifest_path=tmp_path / "blocked.json",
        execution_interface_path=interface,
        winner_path=tmp_path / "winner.json",
    )
    prepared = holdout.prepare_execution_only(
        fixture_path=fixture,
        execution_interface_path=interface,
        winner_path=tmp_path / "winner.json",
    )
    assert prepared["ready_to_execute"] is False
    assert prepared["promotion_eligible"] is False
    assert "frozen_development_winner_missing_or_unfrozen" in prepared["blockers"]


def test_validate_fixture_stage_on_repo_output_if_present():
    path = holdout.DEFAULT_FIXTURE
    if not path.exists():
        pytest.skip("repo holdout fixture not built yet")
    result = holdout.validate_fixture(path)
    assert result["status"] == "OK"
    assert result["promotion_eligible"] is False
