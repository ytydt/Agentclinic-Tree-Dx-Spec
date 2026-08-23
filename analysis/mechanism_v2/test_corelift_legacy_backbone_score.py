from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.mechanism_v2.corelift_legacy_backbone_score import (  # noqa: E402
    SLICE_SPEC,
    mcnemar,
    mosaic_case_id,
    parse_args,
    prediction_row,
    resolve_workers,
    scoring_complete,
)


def test_mosaic_case_id_zero_pads_numeric_source() -> None:
    assert mosaic_case_id("diagnosisarena", "100") == "diagnosisarena__000100"
    assert mosaic_case_id("medcasereasoning", "93") == "medcasereasoning__000093"


def test_prediction_row_uses_champion_then_runner_as_top2() -> None:
    spec = SLICE_SPEC["DA_d2_seq100"]
    row = prediction_row(
        {
            "arm": "A0_control",
            "case_key": "DA_d2_seq100/100",
            "slice": "DA_d2_seq100",
            "source_id": "100",
            "success": True,
            "champion_label": "Cutaneous metastasis",
            "runner_up_label": "Angiosarcoma",
        },
        spec,
    )
    assert row["case_id"] == "diagnosisarena__000100"
    assert row["top2_diagnoses"] == ["Cutaneous metastasis", "Angiosarcoma"]
    assert row["list_k"] == 2
    assert row["success"] is True


def test_unserved_prediction_has_empty_list() -> None:
    spec = SLICE_SPEC["MCR_v1_seq100"]
    row = prediction_row(
        {
            "arm": "B1_corelift",
            "case_key": "MCR_v1_seq100/93",
            "slice": "MCR_v1_seq100",
            "source_id": "93",
            "success": False,
            "champion_label": "",
            "runner_up_label": "",
        },
        spec,
    )
    assert row["ordered_diagnoses"] == []
    assert row["success"] is False
    assert row["dataset"] == "medcasereasoning"


def test_mcnemar_matches_forest_table_orientation() -> None:
    # Forest left, CoreLift right: right_only - left_only is CoreLift minus Forest.
    forest = {"1": True, "2": True, "3": False}
    corelift = {"1": True, "2": False, "3": True}
    result = mcnemar(forest, corelift)
    assert result["left_only"] == 1
    assert result["right_only"] == 1
    assert result["delta_right_minus_left"] == 0.0


def test_scoring_complete_requires_mapper_summary(tmp_path: Path) -> None:
    dest = tmp_path / "diagnosisarena"
    dest.mkdir()
    spec = SLICE_SPEC["DA_d2_seq100"]
    assert scoring_complete(dest, spec, da=True, mcr=False) is False
    (dest / "mapper").mkdir()
    (dest / "mapper" / "summary.json").write_text("{}", encoding="utf-8")
    assert scoring_complete(dest, spec, da=True, mcr=False) is True


def test_default_workers_are_rag_25_and_non_rag_50() -> None:
    da_workers, mcr_workers = resolve_workers(parse_args([]))
    assert da_workers == 25
    assert mcr_workers == 50
    da_workers, mcr_workers = resolve_workers(parse_args(["--workers", "50"]))
    assert da_workers == 25
    assert mcr_workers == 50
