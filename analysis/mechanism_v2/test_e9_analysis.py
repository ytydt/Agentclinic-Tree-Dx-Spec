from analysis.mechanism_v2.e9_analysis import (
    capture_decomposition,
    paired_bootstrap,
    semantic_summary,
)


def test_e9_bootstrap_is_deterministic_and_paired():
    rows = [
        {"case_key": "a", "arm": "left", "success": True, "gold_top1": False},
        {"case_key": "a", "arm": "right", "success": True, "gold_top1": True},
        {"case_key": "b", "arm": "left", "success": True, "gold_top1": False},
        {"case_key": "b", "arm": "right", "success": True, "gold_top1": True},
    ]
    first = paired_bootstrap(rows, "left", "right", repetitions=100)
    assert first == [1.0, 1.0]
    assert paired_bootstrap(rows, "left", "right", repetitions=100) == first


def test_e9_semantic_summary_keeps_contract_failures_and_uses_global_ratio():
    metrics = {
        "observation_n": 4,
        "cluster_n": 2,
        "compression_ratio": 0.5,
        "cross_view_cluster_n": 1,
        "all_three_cluster_n": 0,
        "semantic_jaccard_pairs": {"V1__V2": 0.5, "V1__V3": 0.0, "V2__V3": 0.25},
    }
    result = semantic_summary([
        {"success": True, "metrics": metrics},
        {"success": False, "error": "bad partition", "metrics": {}},
    ])
    assert result["n_served"] == 1
    assert result["n_failed_contract"] == 1
    assert result["failure_reasons"] == {"bad partition": 1}
    assert result["global_cluster_to_observation_ratio"] == 0.5


def test_e9_capture_decomposition_separates_reach_from_conversion():
    rows = []
    for case_key, single_exposed, real_exposed, single_hit, real_hit in (
        ("a", True, True, True, False),
        ("b", False, True, False, True),
    ):
        for arm, exposed, hit in (
            ("single_anchor", single_exposed, single_hit),
            ("real_views", real_exposed, real_hit),
        ):
            rows.append({
                "case_key": case_key,
                "family": "DA",
                "arm": arm,
                "gold_exposure_hit": exposed,
                "gold_top1": hit,
            })
    result = capture_decomposition(rows)["all"]
    assert result["shared_exposure_n"] == 1
    assert result["shared_exposure_single_only_top1_n"] == 1
    assert result["real_only_exposure_n"] == 1
    assert result["real_only_exposure_top1_n"] == 1
