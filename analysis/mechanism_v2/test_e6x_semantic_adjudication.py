from analysis.mechanism_v2.e6x_semantic_adjudication import (
    ARMS,
    DEFAULT_MODEL,
    DEFAULT_OUT,
    freeze_design,
    load_jobs,
)


def test_e6x_semantic_jobs_are_arm_blind_and_complete():
    jobs, hashes = load_jobs(DEFAULT_OUT)
    assert len(jobs) == 300
    assert set(hashes) == set(ARMS)
    assert {len(job["outputs"]) for job in jobs} <= {0, 1, 2}
    assert sum(len(job["outputs"]) == 2 for job in jobs) == 255
    for job in jobs:
        assert all(set(row) == {"output_id", "diagnostic_output"} for row in job["outputs"])
        assert not any(arm in str(job["outputs"]) for arm in ARMS)


def test_e6x_semantic_design_freezes_both_result_files():
    jobs, hashes = load_jobs(DEFAULT_OUT)
    design = freeze_design(DEFAULT_OUT, jobs, hashes, DEFAULT_MODEL)
    assert design["arm_identity_visible_to_auditor"] is False
    assert design["output_count_distribution"] == {"0": 42, "1": 3, "2": 255}
