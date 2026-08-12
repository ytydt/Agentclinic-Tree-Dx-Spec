"""Dependency-free checks for the E11 root clinical audit."""
from __future__ import annotations

import json

from analysis.mechanism_v2.e11_b07_factorial import DEFAULT_OUT
from analysis.mechanism_v2.e11_root_audit import (
    COMPLETE,
    COMPLETE_OR_PARTIAL,
    resolve_candidate_relations,
)
from analysis.mechanism_v2.online_runner import read_jsonl


def _inputs():
    rows = read_jsonl(DEFAULT_OUT / "semantic_screen" / "screen_results.jsonl")
    screen = {str(row["case_key"]): row for row in rows}
    adjudication = json.loads(
        (DEFAULT_OUT / "root_adjudication.json").read_text(encoding="utf-8")
    )
    return screen, adjudication


def test_root_overrides_cover_all_candidate_screen_failures() -> None:
    screen, adjudication = _inputs()
    failures = {
        key for key, row in screen.items()
        if not row["component_success"]["candidate"]
    }
    assert failures == set(adjudication["candidate_screen_failure_case_keys"])
    assert failures.issubset(adjudication["cases"])


def test_resolved_occurrences_cover_all_6400_arm_ranks() -> None:
    screen, adjudication = _inputs()
    relations, _ = resolve_candidate_relations(screen, adjudication)
    assert len(relations) == 400 * 8 * 2
    assert set(relations.values()).issubset(
        COMPLETE_OR_PARTIAL | {"not_equivalent", "unresolved"}
    )
    assert COMPLETE.issubset(COMPLETE_OR_PARTIAL)


def test_all_clinical_relevant_vs_off_discordances_are_root_reviewed() -> None:
    analysis = json.loads(
        (DEFAULT_OUT / "root_clinical_analysis.json").read_text(encoding="utf-8")
    )
    assert analysis["bootstrap_repetitions"] == 10_000
    assert analysis["root_review_coverage"][
        "all_clinical_complete_relevant_vs_off_discordances_reviewed"
    ] is True
    reviewed = set(_inputs()[1]["deep_review_case_keys"])
    discordant = set(
        analysis["root_review_coverage"][
            "clinical_complete_relevant_vs_off_discordant_case_keys"
        ]
    )
    assert discordant
    assert discordant.issubset(reviewed)
