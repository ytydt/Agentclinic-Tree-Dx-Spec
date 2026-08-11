from analysis.mechanism_v2.e4_analysis import paired_bootstrap, wilson


def test_wilson_is_bounded_and_contains_point_estimate():
    low, high = wilson(5, 10)
    assert 0 <= low < 0.5 < high <= 1


def test_paired_bootstrap_is_deterministic():
    rows = []
    for index, (left, right) in enumerate([(0, 1), (1, 1), (1, 0), (0, 0)]):
        rows.extend(
            [
                {"case_key": str(index), "arm": "a", "success": True, "gold_top1": left},
                {"case_key": str(index), "arm": "b", "success": True, "gold_top1": right},
            ]
        )
    first = paired_bootstrap(rows, "a", "b", repetitions=1000)
    second = paired_bootstrap(rows, "a", "b", repetitions=1000)
    assert first == second
    assert first[0] <= 0 <= first[1]
