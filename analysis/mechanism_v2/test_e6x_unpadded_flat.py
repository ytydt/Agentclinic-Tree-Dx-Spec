from analysis.mechanism_v2.e6_representation_fidelity import PAD_TOKEN
from analysis.mechanism_v2.e6x_unpadded_flat import (
    DEFAULT_OUT,
    E6_OUT,
    _paired_binary,
    freeze_design,
    load_inputs,
    unpadded_representation,
)


def test_unpadded_representation_reuses_builder_without_sentinel():
    jobs, builders = load_inputs()
    successful = next(builders[job["case_key"]] for job in jobs if builders[job["case_key"]]["success"])
    record = unpadded_representation(successful)
    assert PAD_TOKEN not in record["text"]
    assert record["padding_words"] == 0
    assert record["original_whitespace_words"] == record["presented_whitespace_words"]


def test_e6x_design_hashes_original_padded_arm_and_frozen_builder():
    design = freeze_design(DEFAULT_OUT, "deepseek/deepseek-v4-flash-0731")
    assert design["n_cases"] == 300
    assert set(design["input_hashes"]) == {
        "builder_results", "padded_flat_results", "padded_flat_telemetry", "bridge"
    }
    assert design["input_hashes"]["builder_results"]
    assert (E6_OUT / "arms/flat_facts/case_results.jsonl").is_file()


def test_paired_binary_retains_failures_and_direction():
    padded = [
        {"case_key": "a", "success": True},
        {"case_key": "b", "success": False},
    ]
    unpadded = [
        {"case_key": "a", "success": False},
        {"case_key": "b", "success": True},
    ]
    result = _paired_binary(padded, unpadded, "success")
    assert result["n"] == 2
    assert result["padded_only"] == result["unpadded_only"] == 1
    assert result["delta_unpadded_minus_padded"] == 0
