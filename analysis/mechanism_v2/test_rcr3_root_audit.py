from __future__ import annotations

import json
from collections import Counter

from analysis.mechanism_v2.rcr3_end_to_end import DEFAULT_OUT
from analysis.mechanism_v2.rcr3_root_audit import (
    CODE_MAP,
    ROOT_REVIEW_DECISION_CODES,
    critical_case_reasons,
    root_review_pairs,
)


def test_frozen_root_review_scope() -> None:
    reasons = critical_case_reasons(DEFAULT_OUT)
    rows = root_review_pairs(DEFAULT_OUT)
    assert len(reasons) == 98
    assert Counter(row["family"] for row in rows) == {"DA": 133, "MCR": 242}
    assert len(rows) == 375
    assert sum(bool(row["e12_prior_root_relation"]) for row in rows) == 44
    assert sum(row["proxy_relation"] == "complete_equivalent" for row in rows) == 104


def test_negative_sample_is_family_balanced() -> None:
    reasons = critical_case_reasons(DEFAULT_OUT)
    negative = [key for key, values in reasons.items() if "frozen_proxy_negative_sample" in values]
    assert len(negative) == 30
    family = {
        row["case_key"]: row["family"]
        for row in root_review_pairs(DEFAULT_OUT)
    }
    assert Counter(family[key] for key in negative) == {"DA": 15, "MCR": 15}


def test_root_decision_codes_cover_frozen_pairs() -> None:
    assert len(ROOT_REVIEW_DECISION_CODES) == len(root_review_pairs(DEFAULT_OUT)) == 375
    assert set(ROOT_REVIEW_DECISION_CODES).issubset(CODE_MAP)
    assert Counter(ROOT_REVIEW_DECISION_CODES) == {"C": 78, "P": 76, "N": 221}


def test_frozen_root_clinical_outputs() -> None:
    adjudication = json.loads(
        (DEFAULT_OUT / "root_adjudication.json").read_text(encoding="utf-8")
    )
    analysis = json.loads(
        (DEFAULT_OUT / "root_clinical_analysis.json").read_text(encoding="utf-8")
    )
    assert adjudication["reviewed_case_candidate_n"] == 375
    assert adjudication["root_proxy_relation_disagreement_n"] == 107
    assert adjudication["negative_sample"]["root_complete_case_n"] == 0
    assert {
        arm: row["top1_n"] for arm, row in analysis["complete"]["arms"].items()
    } == {
        "lite3_safe": 29,
        "rcr3_default": 20,
        "compact4_true3gen": 18,
    }
    assert analysis["root_coverage"]["all_final_complete_discordances_root_reviewed"]
