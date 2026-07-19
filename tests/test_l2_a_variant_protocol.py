from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PROTOCOL_PATH = ROOT / "eval_fixtures" / "l2_a_variant_protocol_v1.json"


def _protocol() -> dict:
    return json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))


def _arms(protocol: dict) -> dict[str, dict]:
    return {row["id"]: row for row in protocol["arms"]}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def test_protocol_is_frozen_and_source_assets_are_content_bound():
    protocol = _protocol()

    assert protocol["schema_version"] == 1
    assert protocol["protocol_version"] == 1
    assert protocol["asset_kind"] == "l2_a_variant_experiment_protocol"
    assert protocol["frozen"] is True
    assert protocol["protocol_namespace"] == "l2-a-variant-v1"

    for binding in protocol["source_bindings"].values():
        path = ROOT / binding["path"]
        assert path.is_file(), binding["path"]
        assert re.fullmatch(r"[0-9a-f]{64}", binding["sha256"])
        assert _sha256(path) == binding["sha256"]

    required = set(protocol["execution_identity"]["required_manifest_bindings"])
    assert {
        "protocol_sha256",
        "seed_hash",
        "source_a_tree_hash",
        "source_candidate_asset_hash",
        "arm_spec_hash",
        "code_sha256",
        "prompt_sha256",
        "model",
        "temperature",
        "transport",
    } == required


def test_control_and_a1_to_a17_registry_is_complete_and_unique():
    protocol = _protocol()
    controls = protocol["controls"]
    arms = protocol["arms"]

    assert [row["id"] for row in controls] == ["C-prod", "A-raw"]
    assert [row["id"] for row in arms] == [f"A{index}" for index in range(1, 18)]
    assert protocol["development"]["headline_arm_count"] == 19
    assert protocol["development"]["headline_unit_count"] == 19 * 17 * 3

    all_rows = controls + arms
    slugs = [row["slug"] for row in all_rows]
    assert len(slugs) == len(set(slugs))
    assert all(re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug) for slug in slugs)

    for arm in arms:
        assert arm["single_factor_baseline"] == "A-raw"
        assert arm["single_factor"]
        assert arm["category"]
        assert isinstance(arm["parameters"], dict) and arm["parameters"]
        assert isinstance(arm["pure_downstream_diagnostic"], bool)


def test_arm_slugs_categories_and_registered_parameters_are_frozen():
    arms = _arms(_protocol())
    expected = {
        "A1": ("a1-local-parent-gate", "generation_transform"),
        "A2": ("a2-semantic-dedupe-cap", "generation_transform"),
        "A3": ("a3-evidence-rerank", "generation_transform"),
        "A4": ("a4-gated-deduped-reranked", "registered_component_combination"),
        "A5": ("a5-raw-global-arbiter", "downstream_arbiter"),
        "A6": ("a6-a-recall-c-generate", "generation_hybrid"),
        "A7": ("a7-global-parent-assignment", "generation_transform"),
        "A8": ("a8-sibling-contrastive-generation", "generation"),
        "A9": ("a9-stability-consensus", "stochastic_generation"),
        "A10": ("a10-n-best-tree-selection", "stochastic_generation"),
        "A11": ("a11-core-shadow", "candidate_activation"),
        "A12": ("a12-evidence-support-gate", "candidate_activation"),
        "A13": ("a13-counterfactual-prune", "candidate_pruning"),
        "A14": ("a14-dynamic-f4", "local_ranking"),
        "A15": ("a15-multi-champion", "candidate_compression"),
        "A16": ("a16-gated-global-leaf-arbiter", "downstream_arbiter"),
        "A17": ("a17-prior-calibration", "prior_calibration"),
    }
    assert {
        arm_id: (row["slug"], row["category"])
        for arm_id, row in arms.items()
    } == expected

    assert arms["A1"]["parameters"]["may_view_other_parents"] is False
    assert arms["A2"]["parameters"]["final_leaf_cap_per_parent"] == 5
    assert arms["A3"]["parameters"]["top_k_per_parent"] == 4
    assert arms["A4"]["parameters"]["components"] == ["A1", "A2", "A3"]
    assert arms["A4"]["parameters"]["application_order"] == [
        "local_parent_gate",
        "semantic_dedupe_and_parent_cap",
        "evidence_rerank",
    ]
    assert arms["A5"]["parameters"]["pre_arbiter_pruning"] == "none"
    assert arms["A6"]["parameters"]["recall_source"] == "A"
    assert arms["A6"]["parameters"]["generation_behavior"] == "C"
    assert arms["A7"]["parameters"]["scope"] == "all_parents_and_all_candidates"
    assert arms["A8"]["parameters"]["contrast_scope"] == "sibling_parents"
    assert arms["A11"]["parameters"]["core_top_k_per_parent"] == 3
    assert arms["A12"]["parameters"]["unsupported_state"] == "shadow"
    assert (
        arms["A13"]["parameters"]["schema_failure_policy"]
        == "fail_closed_keep_candidate"
    )
    assert arms["A14"]["parameters"] == {
        "local_evidence_budget": "dynamic_F4",
        "inter_parent_evidence_budget": "true_F2",
        "champions_per_parent": 1,
    }
    assert arms["A15"]["parameters"]["champions_per_parent"] == 2
    assert arms["A15"]["parameters"]["reference_champions_per_parent"] == 1
    assert arms["A16"]["parameters"]["only_changed_factor"] == "arbiter_granularity"
    assert arms["A17"]["parameters"]["main_temperature"] == 2.0
    assert arms["A17"]["parameters"]["sensitivity_temperatures"] == [
        1.5,
        "infinity",
    ]


def test_a9_and_a10_share_one_stochastic_pool_and_matched_control():
    protocol = _protocol()
    arms = _arms(protocol)
    a9 = arms["A9"]["parameters"]
    a10 = arms["A10"]["parameters"]
    pool = protocol["randomness_and_replicates"]["stochastic_pool"]

    assert a9["shared_pool_id"] == a10["shared_pool_id"] == pool["pool_id"]
    assert a9["pool_size"] == a10["pool_size"] == pool["samples_per_case_replicate"] == 5
    assert a9["temperature"] == a10["temperature"] == pool["temperature"] == 0.3
    assert a9["matched_first_sample_control"] is True
    assert a10["matched_first_sample_control"] is True
    assert pool["shared_sample_ids_and_order_required"] is True
    assert protocol["cache_contract"]["a9_a10_generation_pool_shared"] is True


def test_registered_combinations_are_exact_and_reference_known_arms():
    protocol = _protocol()
    known = set(_arms(protocol))
    combinations = protocol["registered_combinations"]
    auxiliary = protocol["registered_auxiliary_comparisons"]

    assert [row["components"] for row in combinations] == [
        ["A8", "A11", "A14"],
        ["A8", "A11", "A16"],
        ["A6", "A11", "A16"],
        ["A7", "A11", "A14"],
    ]
    assert all(row["components"] == row["order"] for row in combinations)
    assert all(set(row["components"]) <= known for row in combinations)
    assert len({row["slug"] for row in combinations}) == 4
    assert [row["id"] for row in auxiliary] == [
        "A11+A12",
        "A9/A10-first-sample",
        "A16-paired-reference",
        "A17-sensitivity",
    ]
    assert all(set(row["components"]) <= known for row in auxiliary)
    assert all(
        row["eligible_as_standalone_holdout_candidate"] is False
        for row in auxiliary
    )


def test_endpoints_and_development_gate_order_are_frozen():
    protocol = _protocol()
    endpoints = protocol["endpoints"]
    development = protocol["development"]
    gate = development["entry_gate"]

    assert endpoints["primary"]["id"] == "actual_e2e_top2_all_cases"
    assert endpoints["primary"]["gold_absent_policy"] == "miss"
    assert endpoints["key_secondary_ordered"] == [
        "gold_l2_coverage",
        "mrr_at_2",
        "actual_e2e_top1",
    ]
    assert all("oracle_parent_f4" in item for item in endpoints["diagnostic_only"])
    assert gate["hard_all_required"] == {
        "leakage_count": 0,
        "topology_loss_count": 0,
        "runtime_hard_gate_pass": True,
    }
    assert gate["performance"]["actual_top2_delta_vs_a_raw_min"] == 0.0
    assert gate["performance"]["gold_l2_coverage_delta_vs_a_raw_min"] == -0.05
    assert (
        gate["quality"]["parent_invalid_relative_reduction_vs_a_raw_min"]
        == gate["quality"][
            "semantic_duplicate_excess_relative_reduction_vs_a_raw_min"
        ]
        == 0.5
    )
    assert development["winner_selection_lexicographic_order"] == [
        "safety_hard_gates",
        "actual_e2e_top2",
        "gold_l2_coverage",
        "mrr_at_2",
        "clean_rate",
    ]
    assert development["model_call_count_affects_winner_selection"] is False
    assert development["winners_allowed_for_holdout"] == 1


def test_holdout_is_sealed_case_level_and_uses_closed_testing():
    holdout = _protocol()["holdout"]

    assert holdout[
        "must_be_created_and_sealed_before_combination_results_are_read"
    ] is True
    assert holdout["must_exclude_development_cases"] is True
    assert holdout["quality_weighting"] == "case_equal"
    assert holdout["arms"] == ["C-prod", "frozen_development_winner"]
    assert holdout["replicates_per_case"] == 3
    assert holdout["sample_size_rule"]["target_gain_15pp_min_cases"] == 80
    assert holdout["sample_size_rule"][
        "target_gain_10pp_discordance_20_to_25pct_case_range"
    ] == [150, 190]
    assert holdout["hard_gates"]["leakage_count"] == 0
    assert holdout["hard_gates"]["topology_loss_count"] == 0
    assert holdout["hard_gates"]["runtime_failure_rate_max"] == 0.05
    assert holdout["quality_gates"]["one_sided_confidence_level"] == 0.975
    assert holdout["quality_gates"]["parent_invalid_rate_ucb_max"] == 0.1
    assert holdout["quality_gates"][
        "semantic_duplicate_excess_rate_ucb_max"
    ] == 0.1
    assert [
        row["test"] for row in holdout["confirmatory_closed_test_order"]
    ] == [
        "actual_top2_noninferiority_vs_c",
        "gold_l2_coverage_superiority_vs_c",
        "actual_top2_superiority_vs_c",
        "mrr_at_2_superiority_vs_c",
    ]
    assert holdout["confirmatory_closed_test_order"][0][
        "lcb_delta_strictly_greater_than"
    ] == -0.05


def test_three_tier_audit_contract_and_disagreement_escalation_are_frozen():
    audit = _protocol()["audit_contract"]
    tier_1 = audit["tier_1"]
    tier_2 = audit["tier_2"]
    tier_3 = audit["tier_3"]

    assert tier_1["model"] == "gemma-4-31b"
    assert tier_1["sole_external_api_judge"] is True
    assert tier_1["generation_model_self_judging_forbidden"] is True
    assert [row["id"] for row in tier_1["judges"]] == [
        "LeafQualityJudge",
        "SemanticClusterJudge",
        "GoldMatchJudge",
    ]
    quality, semantic, gold_match = tier_1["judges"]
    assert {"gold", "arm"} <= set(quality["hidden_fields"])
    assert {"gold", "arm"} <= set(semantic["hidden_fields"])
    assert gold_match["stage"] == "evaluation_only_after_generation_is_frozen"
    assert gold_match["hidden_fields"] == ["arm", "historical_results"]

    calibration = tier_1["offline_calibration"]
    assert calibration["specific_cohen_kappa_min"] == 0.85
    assert calibration["parent_valid_cohen_kappa_min"] == 0.85
    assert calibration["semantic_duplicate_f1_min"] == 0.9
    assert calibration["gold_presence_sensitivity_min"] == 0.98
    assert calibration["acceptable_id_macro_f1_min"] == 0.95
    assert "forbid_promotion" in calibration["failure_or_api_unavailable_policy"]

    assert tier_2["model"] == "cursor-grok-4.5-high-fast"
    assert tier_2["review_is_blind_to_tier_1_output"] is True
    assert tier_2["payload_must_equal_tier_1_blind_payload"] is True
    assert tier_2["sentinel_fraction_range"] == [0.02, 0.05]
    assert audit["agreement_rule"] == {
        "auto_accept_only_if_field_level_agreement": True,
        "both_confidences_must_pass_threshold": True,
        "otherwise_escalate": True,
    }
    assert tier_3["trigger"] == "any_field_disagreement_between_gemma_and_grok"
    assert tier_3["queue"] == "manual-escalation-queue"
    assert tier_3["unresolved_unit_counts_toward_promotion"] is False
    assert tier_3["decision_is_final_gold"] is True


def test_gold_leakage_seed_replicate_and_cache_contracts_are_explicit():
    protocol = _protocol()
    leakage = protocol["gold_leakage_contract"]
    randomness = protocol["randomness_and_replicates"]
    cache = protocol["cache_contract"]

    assert leakage["runtime_guard"]["callable"] == "assert_no_gold_leak"
    assert leakage["runtime_guard"]["recursive"] is True
    assert set(leakage["forbidden_runtime_keys"]) == {
        "is_gold",
        "gold",
        "gold_option",
        "gold_diagnosis",
        "role",
        "favors",
        "decisive",
        "direction_target",
        "target",
    }
    assert "generation" in leakage["guarded_stages"]
    assert "global_arbitration" in leakage["guarded_stages"]
    assert leakage["generation_and_evaluation_cache_namespaces_must_be_disjoint"]
    assert leakage["evaluation_output_must_not_feed_runtime"]

    assert randomness["default_replicates"] == [1, 2, 3]
    assert randomness["default_temperature"] == 0.0
    assert randomness["replicate_rule"].endswith(
        "never count as independent external cases."
    )
    assert protocol["development"]["bootstrap"]["cluster"] == "case_id"
    assert protocol["development"]["bootstrap"]["iterations"] == 20000
    assert protocol["development"]["bootstrap"][
        "replicates_are_not_independent_samples"
    ] is True

    assert cache["arm_id_in_key"] is False
    assert cache["same_tree_and_effective_payload_must_hit"] is True
    assert cache["different_tree_must_miss"] is True
    assert {
        "evidence",
        "champion_identity_or_count",
        "parent_prior",
    } <= set(cache["differences_requiring_distinct_keys"])
    assert cache["generation_evaluation_namespace_isolation"] is True


def test_development_case_registry_matches_bound_input_manifest():
    protocol = _protocol()
    source = json.loads(
        (
            ROOT
            / protocol["source_bindings"]["development_input_manifest"]["path"]
        ).read_text(encoding="utf-8")
    )

    assert protocol["development"]["case_count"] == 17
    assert protocol["development"]["case_ids"] == source["case_ids"]
    assert protocol["development"]["replicates_per_case"] == 3
    assert protocol["randomness_and_replicates"]["default_replicates"] == [1, 2, 3]
