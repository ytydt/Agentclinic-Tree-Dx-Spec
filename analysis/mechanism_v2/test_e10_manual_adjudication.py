from analysis.mechanism_v2.e10_manual_adjudication import _binomial_two_sided, _paired_from_values


def test_exact_pairing():
    result = _paired_from_values(
        {"a": True, "b": True, "c": False},
        {"a": True, "b": False, "c": True},
    )
    assert result["left_only"] == 1
    assert result["right_only"] == 1
    assert result["delta_right_minus_left"] == 0
    assert result["exact_mcnemar_p"] == 1


def test_binomial_edge():
    assert _binomial_two_sided(0, 0) == 1
    assert _binomial_two_sided(0, 5) == 0.0625
