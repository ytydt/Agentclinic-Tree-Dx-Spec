from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.mechanism_v2.clinical_endpoint import (  # noqa: E402
    COMPLETE,
    PARTIAL,
    ClinicalEndpoint,
)
from analysis.mechanism_v2.clinical_rescore import _state, mcnemar  # noqa: E402


def _write(path: Path, rows: list[dict]) -> Path:
    path.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
        encoding="utf-8",
    )
    return path


def _bridge(path: Path) -> Path:
    path.write_text(
        json.dumps(
            {
                "by_alias": {"PCC": "Primary cutaneous cryptococcosis"},
                "by_canonical": {
                    "Primary cutaneous cryptococcosis": {"aliases": ["PCC"]},
                    "Pericarditis": {"aliases": []},
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def _fixture(
    tmp_path: Path,
    *,
    panel: list[dict] | None = None,
    ledger: list[dict] | None = None,
    migration: list[dict] | None = None,
) -> ClinicalEndpoint:
    return ClinicalEndpoint(
        panel=_write(tmp_path / "panel.jsonl", panel or []),
        occurrence_ledger=_write(tmp_path / "ledger.jsonl", ledger or []),
        migration=_write(tmp_path / "mig.jsonl", migration or []),
        bridge=_bridge(tmp_path / "bridge.json"),
        strict_sources=False,
    )


def test_lookup_is_normalized_and_alias_resolved(tmp_path: Path) -> None:
    ce = _fixture(
        tmp_path,
        panel=[
            {
                "case_key": "DA_d2_seq100/1",
                "candidate_label": "Primary cutaneous cryptococcosis",
                "final_relation": COMPLETE,
                "relation_id": "r1",
            }
        ],
        ledger=[{"relation_id": "r1"}],
    )
    # surface variation and a frozen alias both reach the same verdict
    assert ce.relation("da", "d2_seq100", "1", "primary  cutaneous cryptococcosis") == COMPLETE
    assert ce.relation("da", "d2_seq100", "1", "PCC") == COMPLETE
    assert ce.is_complete("da", "d2_seq100", "1", "PCC")
    # a different case never inherits another case's verdict
    assert ce.relation("da", "d2_seq100", "2", "PCC") is None


def test_occurrence_ledger_gates_panel_rows(tmp_path: Path) -> None:
    ce = _fixture(
        tmp_path,
        panel=[
            {
                "case_key": "DA_d2_seq100/1",
                "candidate_label": "Pericarditis",
                "final_relation": COMPLETE,
                "relation_id": "in",
            },
            {
                "case_key": "DA_d2_seq100/2",
                "candidate_label": "Pericarditis",
                "final_relation": COMPLETE,
                "relation_id": "out",
            },
        ],
        ledger=[{"relation_id": "in"}],
    )
    assert ce.relation("da", "d2_seq100", "1", "Pericarditis") == COMPLETE
    assert ce.relation("da", "d2_seq100", "2", "Pericarditis") is None


def test_unserved_migration_rows_are_ignored(tmp_path: Path) -> None:
    ce = _fixture(
        tmp_path,
        migration=[
            {
                "case_key": "MCR_seq200b/9",
                "prediction_pre_projection": "Pericarditis",
                "clinical_relation": PARTIAL,
                "served": False,
            }
        ],
    )
    assert ce.relation("mcr", "mcr_200b", "9", "Pericarditis") is None


def test_panel_wins_and_conflicts_are_recorded_then_droppable(tmp_path: Path) -> None:
    ce = _fixture(
        tmp_path,
        panel=[
            {
                "case_key": "DA_d2_seq100/1",
                "candidate_label": "Pericarditis",
                "final_relation": COMPLETE,
                "relation_id": "r1",
            }
        ],
        ledger=[{"relation_id": "r1"}],
        migration=[
            {
                "case_key": "DA_d2_seq100/1",
                "prediction_pre_projection": "Pericarditis",
                "clinical_relation": PARTIAL,
                "served": True,
            }
        ],
    )
    # the adjudicated panel is authoritative over the migration replay
    assert ce.relation("da", "d2_seq100", "1", "Pericarditis") == COMPLETE
    assert len(ce.conflicts) == 1
    ce.drop_conflicts()
    assert ce.relation("da", "d2_seq100", "1", "Pericarditis") is None


def test_case_key_prefixes_cover_six_slices_and_reject_unknown(tmp_path: Path) -> None:
    ce = _fixture(tmp_path)
    assert ce.case_key("da", "d2_heldout200b", "7") == "DA_d2_heldout200b/7"
    assert ce.case_key("mcr", "mcr_v1", "7") == "MCR_v1_seq100/7"
    assert ce.case_key("mcr", "mcr_200b", "7") == "MCR_seq200b/7"
    assert ce.case_key("da", "not_a_slice", "7") is None
    assert ce.relation("da", "not_a_slice", "7", "Pericarditis") is None


def test_complete_and_partial_predicates(tmp_path: Path) -> None:
    rows = []
    ledger = []
    for i, rel in enumerate(
        [COMPLETE, PARTIAL, "not_equivalent", "conflicting_subtype_or_scope", "uncertain"]
    ):
        rows.append(
            {
                "case_key": f"DA_d2_seq100/{i}",
                "candidate_label": "Pericarditis",
                "final_relation": rel,
                "relation_id": f"r{i}",
            }
        )
        ledger.append({"relation_id": f"r{i}"})
    ce = _fixture(tmp_path, panel=rows, ledger=ledger)
    flags = [
        (
            ce.is_complete("da", "d2_seq100", str(i), "Pericarditis"),
            ce.is_complete_or_partial("da", "d2_seq100", str(i), "Pericarditis"),
        )
        for i in range(5)
    ]
    assert flags == [
        (True, True),
        (False, True),
        (False, False),
        (False, False),
        (False, False),
    ]
    got, total = ce.coverage("da", "d2_seq100", "0", ["Pericarditis", "Unjudged thing", ""])
    assert (got, total) == (1, 2)


def _state_fixture(tmp_path: Path) -> ClinicalEndpoint:
    rows = [
        {
            "case_key": "DA_d2_seq100/1",
            "candidate_label": "Complete label",
            "final_relation": COMPLETE,
            "relation_id": "c",
        },
        {
            "case_key": "DA_d2_seq100/1",
            "candidate_label": "Parent label",
            "final_relation": PARTIAL,
            "relation_id": "p",
        },
        {
            "case_key": "DA_d2_seq100/1",
            "candidate_label": "Wrong label",
            "final_relation": "not_equivalent",
            "relation_id": "w",
        },
    ]
    return _fixture(
        tmp_path,
        panel=rows,
        ledger=[{"relation_id": r["relation_id"]} for r in rows],
    )


def test_state_classification_covers_every_branch(tmp_path: Path) -> None:
    ce = _state_fixture(tmp_path)
    args = ("da", "d2_seq100", "1")

    assert _state(ce, *args, "Complete label", [], []) == "complete_champion"
    assert _state(ce, *args, "Parent label", [], []) == "partial_champion"
    # a champion with no verdict must not be silently scored
    assert _state(ce, *args, "Never judged", [], []) == "champion_unjudged"
    assert (
        _state(ce, *args, "Wrong label", ["Complete label"], ["Complete label"])
        == "complete_lost_in_finals"
    )
    assert (
        _state(ce, *args, "Wrong label", ["Parent label"], ["Complete label"])
        == "complete_lost_before_finals"
    )
    assert (
        _state(ce, *args, "Wrong label", ["Parent label"], ["Parent label"])
        == "no_complete_in_pool"
    )


def test_partial_champion_takes_precedence_over_pool_state(tmp_path: Path) -> None:
    """A partial champion is its own state even when a complete label existed.

    The completion ladder and the selection headroom must not double-count the
    same case, so `partial_champion` is decided from the champion alone.
    """
    ce = _state_fixture(tmp_path)
    assert (
        _state(ce, "da", "d2_seq100", "1", "Parent label", ["Complete label"], ["Complete label"])
        == "partial_champion"
    )


def test_mcnemar_matches_exact_binomial() -> None:
    assert mcnemar([])["p_two_sided"] == 1.0
    assert mcnemar([(True, True), (False, False)])["p_two_sided"] == 1.0
    # 0 vs 6 discordant -> 2 * (1/64)
    r = mcnemar([(False, True)] * 6)
    assert (r["base_only"], r["fix_only"]) == (0, 6)
    assert abs(r["p_two_sided"] - 0.0312) < 1e-3
    # symmetric discordance is never significant
    assert mcnemar([(True, False), (False, True)])["p_two_sided"] == 1.0
