from analysis.mechanism_v2.e6x_manual_audit import (
    CORRECTIONS,
    DEFAULT_OUT,
    _mechanisms,
    final_semantic_rows,
    load_manual_queue,
    trajectory_diagnostics,
)


def test_e6x_manual_audit_covers_frozen_queue_and_all_discordances():
    rows = load_manual_queue(DEFAULT_OUT)
    assert len(rows) == 63
    assert sum("complete_equivalence_discordance" in row["queue_reason"] for row in rows) == 33
    assert len(_mechanisms()) == 33
    assert all(row["manual_reviewed"] for row in rows)
    changed = {
        (row["case_key"], judgment["arm"])
        for row in rows for judgment in row["judgments"] if judgment["manual_changed"]
    }
    assert changed == set(CORRECTIONS)


def test_e6x_manual_overrides_apply_to_full_population():
    manual = load_manual_queue(DEFAULT_OUT)
    rows, summary = final_semantic_rows(DEFAULT_OUT, manual)
    assert len(rows) == 513
    assert summary["root_manually_reviewed_row_n"] == 126
    assert summary["manual_changed_judgment_n"] == len(CORRECTIONS)
    assert len(summary["paired"]) == 2


def test_e6x_trajectory_diagnostics_expose_selector_instability():
    manual = load_manual_queue(DEFAULT_OUT)
    rows, _ = final_semantic_rows(DEFAULT_OUT, manual)
    trajectories, summary = trajectory_diagnostics(DEFAULT_OUT, rows)
    assert len(trajectories) == summary["served_both_n"] == 255
    assert summary["champion_flip_rate"] > 0.9
    assert summary["mean_top5_exact_set_overlap_n"] < 2
    assert summary["single_physical_attempt_both_n"] > 150
    assert summary["padding_words_to_input_token_saving_single_attempt_pearson_r"] > 0.99
