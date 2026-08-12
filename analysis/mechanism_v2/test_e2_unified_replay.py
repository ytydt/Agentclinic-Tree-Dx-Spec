from pathlib import Path

import pytest

from analysis.mechanism_v2 import e2_unified_replay as replay


def test_code_decoder_fails_closed_and_decodes():
    assert replay._decode_codes("C P\nN", replay.RELATION_CODE_MAP, 3, "test") == [
        "complete_equivalent",
        "partial_parent_or_component",
        "not_equivalent",
    ]
    with pytest.raises(AssertionError, match="coverage"):
        replay._decode_codes("CP", replay.RELATION_CODE_MAP, 3, "test")
    with pytest.raises(AssertionError, match="invalid"):
        replay._decode_codes("CPZ", replay.RELATION_CODE_MAP, 3, "test")


def test_exact_mcnemar_known_values():
    assert replay._mcnemar_exact(0, 0) == 1.0
    assert replay._mcnemar_exact(1, 9) == pytest.approx(0.021484375)
    assert replay._mcnemar_exact(5, 5) == 1.0


def test_freeze_has_no_arm_or_endpoint_provenance(tmp_path: Path):
    summary = replay.freeze_audit(tmp_path)
    assert summary["new_root_audit_cases_n"] == 400
    assert summary["candidate_relations_n"] == 1646
    cards = replay.read_jsonl(tmp_path / "root_audit/cards.jsonl")
    assert len(cards) == 400
    forbidden = {"case_key", "family", "slice", "arm", "legacy_chain", "task"}
    assert not (forbidden & set(cards[0]))
    assert all(not (forbidden | {"safe_exact"}) & set(candidate) for row in cards for candidate in row["candidate_registry"])
    assert sum(len(row["candidate_registry"]) for row in cards) == 1587
