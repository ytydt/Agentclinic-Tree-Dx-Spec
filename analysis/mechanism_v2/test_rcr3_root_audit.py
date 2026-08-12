from __future__ import annotations

from collections import Counter

from analysis.mechanism_v2.rcr3_end_to_end import DEFAULT_OUT
from analysis.mechanism_v2.rcr3_root_audit import (
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
