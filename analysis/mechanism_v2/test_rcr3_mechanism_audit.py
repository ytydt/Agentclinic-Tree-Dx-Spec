from __future__ import annotations

import json
from collections import Counter

from analysis.mechanism_v2.rcr3_analysis import load_stages
from analysis.mechanism_v2.rcr3_end_to_end import DEFAULT_OUT, RCR3
from analysis.mechanism_v2.rcr3_mechanism_audit import (
    RELATION_QUALITY,
    ROOT_MATERIAL_DROP_FACTS,
    ROOT_RELATION_REVIEW_CODES,
    grounding_drops,
    invalid_reference_rows,
    relation_sample,
)


def test_root_relation_sample_is_type_stratified_and_frozen() -> None:
    rows = relation_sample(load_stages(DEFAULT_OUT)[RCR3])
    assert len(rows) == len(ROOT_RELATION_REVIEW_CODES) == 60
    assert Counter(row["relation_type"] for row in rows) == {
        "after": 6,
        "associated_with": 6,
        "before": 6,
        "causes": 6,
        "contradicts": 6,
        "has_result": 6,
        "located_at": 6,
        "refines": 6,
        "response_to": 6,
        "same_episode_as": 6,
    }
    assert set(ROOT_RELATION_REVIEW_CODES).issubset(RELATION_QUALITY)
    assert Counter(ROOT_RELATION_REVIEW_CODES) == {"I": 29, "S": 11, "D": 11, "U": 9}


def test_grounding_and_invalid_reference_inventories_are_complete() -> None:
    stages = load_stages(DEFAULT_OUT)[RCR3]
    drops = grounding_drops(stages)
    invalid = invalid_reference_rows(stages)
    assert len(drops) == 119
    assert len(ROOT_MATERIAL_DROP_FACTS) == 69
    assert sum(row["root_material_diagnostic_evidence"] for row in drops) == 69
    assert len(invalid) == 51
    assert len({row["case_key"] for row in invalid}) == 9


def test_frozen_mechanism_summary_calibration() -> None:
    analysis = json.loads(
        (DEFAULT_OUT / "mechanism_root_analysis.json").read_text(encoding="utf-8")
    )
    selector = analysis["selector_calibration"]
    assert selector["served_selector_n"] == 262
    assert selector["selector_self_complete_n"] == 66
    assert selector["selector_self_complete_root_complete_n"] == 9
    assert selector["selector_self_complete_root_not_equivalent_n"] == 38
    assert analysis["frontier"]["case_keys"] == [
        "MCR_seq200b/320",
        "MCR_v2_seq100/208",
        "MCR_v2_seq100/227",
    ]
