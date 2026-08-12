from analysis.mechanism_v2.e6_manual_audit import (
    CORRECTIONS,
    DEFAULT_OUT,
    _mechanism_by_case,
    full_semantic_rows,
    manual_semantic_rows,
    representation_rows,
    representation_summary,
    semantic_summary,
)


def test_manual_semantic_audit_has_complete_frozen_coverage():
    rows = manual_semantic_rows(DEFAULT_OUT)
    assert len(rows) == 94
    assert sum("complete_equivalence_discordance" in row["queue_reason"] for row in rows) == 64
    assert len(_mechanism_by_case()) == 64
    assert all(row["manual_reviewed"] for row in rows)
    observed = {
        (row["case_key"], judgment["arm"])
        for row in rows for judgment in row["judgments"]
        if judgment["manual_changed"]
    }
    assert observed == set(CORRECTIONS)


def test_manual_semantic_summary_is_bounded_to_queue():
    rows = manual_semantic_rows(DEFAULT_OUT)
    summary = semantic_summary(rows)
    assert summary["manual_case_n"] == 94
    assert summary["changed_judgment_n"] == len(CORRECTIONS)
    assert len(summary["paired_on_queue"]) == 6


def test_manual_decisions_are_applied_to_full_semantic_population():
    manual = manual_semantic_rows(DEFAULT_OUT)
    rows, summary = full_semantic_rows(DEFAULT_OUT, manual)
    assert len(rows) > 700
    assert summary["root_manually_reviewed_row_n"] == sum(
        len(row["judgments"]) for row in manual
    )
    assert len(summary["paired"]) == 6
    assert sum(row["manual_changed"] for row in rows) == len(CORRECTIONS)


def test_representation_audit_covers_all_frozen_cases_and_counts_errors():
    rows = representation_rows(DEFAULT_OUT)
    summary = representation_summary(rows)
    assert len(rows) == 30
    assert all(row["manual_reviewed"] for row in rows)
    assert summary["graph_relation_error_case_n"] > 20
    assert len(summary["gold_evidence_absent_case_keys"]) == 4
