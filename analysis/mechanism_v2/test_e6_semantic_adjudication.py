from analysis.mechanism_v2.e6_representation_fidelity import ARMS
from analysis.mechanism_v2.e6_semantic_adjudication import (
    AUDITOR_PROMPT,
    exact_mcnemar,
    load_jobs,
    validate_response,
)


def _judgment(output_id, equivalence="complete_equivalent"):
    return {
        "output_id": output_id,
        "equivalence": equivalence,
        "direction": "same",
        "reference_components_preserved": ["core diagnosis"],
        "reference_components_missing": [],
        "unsupported_additions": [],
        "vignette_consistency": "supported",
        "explanation": "Same complete diagnosis.",
    }


def test_adjudicator_contract_requires_exact_opaque_output_set():
    response = {"judgments": [_judgment("O2"), _judgment("O1")]}
    assert validate_response(response, ["O1", "O2"]) is None
    response["judgments"][0]["output_id"] = "O3"
    assert "exactly match" in validate_response(response, ["O1", "O2"])


def test_adjudicator_rejects_unrecognized_partial_category():
    response = {"judgments": [_judgment("O1", "mostly right")]}
    assert "equivalence" in validate_response(response, ["O1"])


def test_frozen_jobs_blind_arm_names_and_preserve_all_successful_outputs():
    # Use the completed E6 tree rather than manufacturing semantically invalid
    # selector rows.  The function is read-only and hashes every arm input.
    from analysis.mechanism_v2.e6_representation_fidelity import DEFAULT_OUT

    jobs, hashes = load_jobs(DEFAULT_OUT)
    assert len(jobs) == 300
    assert set(hashes) == set(ARMS)
    for job in jobs:
        assert all(set(row) == {"output_id", "diagnostic_output"} for row in job["outputs"])
        assert not any(arm in str(job["outputs"]) for arm in ARMS)
        assert set(job["arm_by_output"].values()) <= set(ARMS)
    assert "opaque" in AUDITOR_PROMPT.lower()


def test_preregistration_distribution_uses_json_stable_string_keys():
    from analysis.mechanism_v2.e6_representation_fidelity import DEFAULT_OUT
    from analysis.mechanism_v2.e6_semantic_adjudication import freeze_design

    jobs, hashes = load_jobs(DEFAULT_OUT)
    frozen = freeze_design(DEFAULT_OUT, jobs, hashes, "google/gemini-2.5-flash")
    assert frozen["output_count_distribution"] == {"0": 1, "1": 41, "2": 11, "3": 247}


def test_exact_mcnemar_boundary_cases():
    assert exact_mcnemar(0, 0) == 1.0
    assert exact_mcnemar(0, 8) == 2 / 256
