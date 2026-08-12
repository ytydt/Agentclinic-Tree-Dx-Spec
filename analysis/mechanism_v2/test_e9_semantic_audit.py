from analysis.mechanism_v2.e9_semantic_audit import derive_metrics, validate_response


def test_validate_complete_partition() -> None:
    response = {
        "clusters": [
            {"cluster_id": "C1", "member_ids": ["V1O1", "V2O1"],
             "proposition": "same", "merge_basis": "paraphrase"},
            {"cluster_id": "C2", "member_ids": ["V3O1"],
             "proposition": "other", "merge_basis": "singleton"},
        ],
        "audit_note": "x",
    }
    assert validate_response(response, ["V1O1", "V2O1", "V3O1"]) is None
    response["clusters"][1]["member_ids"] = ["V1O1"]
    assert "duplicated" in str(validate_response(response, ["V1O1", "V2O1", "V3O1"]))


def test_derive_metrics() -> None:
    response = {
        "clusters": [
            {"cluster_id": "C1", "member_ids": ["V1O1", "V2O1", "V3O1"]},
            {"cluster_id": "C2", "member_ids": ["V1O2"]},
            {"cluster_id": "C3", "member_ids": ["V2O2", "V3O2"]},
        ]
    }
    metrics = derive_metrics(response)
    assert metrics["cluster_n"] == 3
    assert metrics["observation_n"] == 6
    assert metrics["cross_view_cluster_n"] == 2
    assert metrics["all_three_cluster_n"] == 1
    assert metrics["unique_cluster_by_view"]["V1"] == 1
    assert metrics["semantic_jaccard_pairs"]["V2__V3"] == 1.0
