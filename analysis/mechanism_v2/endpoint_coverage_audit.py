#!/usr/bin/env python3
"""Fail-closed endpoint-coverage audit for the mechanism-v2 experiment reports.

This module does not recompute scientific endpoints.  It records which endpoint
contracts the checked-in reports actually support, verifies the evidence anchors
used for that classification, and emits a deterministic matrix that downstream
report builders can use as an ingestion guard.

Only a full, blinded root-level census is eligible for a clinical-capability
leaderboard.  Proxy-completed, root-priority, targeted, and structural audits are
valuable mechanism evidence, but are deliberately blocked from that use.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = ROOT / "analysis/mechanism_v2/results/ENDPOINT_COVERAGE_AUDIT"

EXPECTED_EXPERIMENT_IDS = (
    "E1",
    "E2",
    "E4",
    "E5",
    "E6",
    "E6x",
    "E7a",
    "E7b",
    "E7c",
    "E8",
    "E9",
    "E10",
    "E11",
    "E12",
    "E14x",
    "RCR3",
)
FULL_ROOT_CENSUS_ALLOWLIST = frozenset({"E2"})

FULL_ROOT = "full_root_census"
FULL_BLINDED_PANEL = "full_blinded_model_panel_census_not_root"
PROXY_ROOT_PRIORITY = "proxy_completed_root_priority"
TARGETED_ONLY = "targeted_root_audit_only_no_arm_rate"
NOT_AVAILABLE = "not_available"
NOT_APPLICABLE = "not_applicable_no_fresh_arm_output"
E10_MISLABEL = "not_measured_binary_acceptable_only"
E10_PARTIAL = "not_measured_not_separately_coded"
E10_UNION = "not_measured_binary_acceptable_is_not_valid_union"

ALLOWED_ENDPOINT_STATUSES = frozenset(
    {
        FULL_ROOT,
        FULL_BLINDED_PANEL,
        PROXY_ROOT_PRIORITY,
        TARGETED_ONLY,
        NOT_AVAILABLE,
        NOT_APPLICABLE,
        E10_MISLABEL,
        E10_PARTIAL,
        E10_UNION,
    }
)

MIGRATION_EXPERIMENT_IDS = frozenset(
    experiment_id
    for experiment_id in EXPECTED_EXPERIMENT_IDS
    if experiment_id not in {"E2", "E7a"}
)
MIGRATION_SUMMARY_PATH = Path(
    "analysis/mechanism_v2/results/ALL_ARM_ENDPOINT_MIGRATION/final/summary.json"
)
MIGRATION_REPLAY_PATH = Path(
    "analysis/mechanism_v2/results/ALL_ARM_ENDPOINT_MIGRATION/final/five_endpoint_replay.jsonl"
)


# The classification is intentionally explicit instead of inferred from metric
# names.  In particular, ``clinical_complete*`` does not prove a full root census,
# and ``legacy_substring`` in E7a/E7b is a treatment name rather than the old
# legacy-chain scoring endpoint.
EXPERIMENT_SPECS: tuple[dict[str, Any], ...] = (
    {
        "experiment_id": "E1",
        "report_path": "analysis/mechanism_v2/results/E1_input_factorial/REPORT.md",
        "arm_count": 8,
        "intended_case_n": 200,
        "clinical_complete_status": TARGETED_ONLY,
        "compatible_partial_status": NOT_AVAILABLE,
        "complete_or_compatible_partial_status": NOT_AVAILABLE,
        "blind_status": "targeted_mechanism_review_not_full_blind_census",
        "full_root_census": False,
        "conclusion_use": "safe_exact_input_contamination_mechanism_only",
        "raw_legacy_field_risk": "strict_top1_fields_are_safe_exact_aliases",
        "coverage_note": "Clinical review covers 4 fixed-format harms plus 18 mechanism transitions, not all eight arms.",
        "report_markers": (
            "Safe-exact is a reproducible high-precision lower bound",
            "It did **not** clinically\nadjudicate every output",
        ),
    },
    {
        "experiment_id": "E2",
        "report_path": "analysis/mechanism_v2/results/E2_blinded_clinical_adjudication/REPORT.md",
        "arm_count": 9,
        "intended_case_n": 800,
        "clinical_complete_status": FULL_ROOT,
        "compatible_partial_status": FULL_ROOT,
        "complete_or_compatible_partial_status": FULL_ROOT,
        "blind_status": "arm_endpoint_hidden_root_relation_census",
        "full_root_census": True,
        "conclusion_use": "clinical_capability_leaderboard",
        "raw_legacy_field_risk": "legacy_chain_retained_diagnostic_only_under_explicit_contract",
        "coverage_note": "All 7,200 case-arm rows have mutually exclusive clinical-complete and compatible-partial decisions; complete-or-compatible-partial is secondary coverage.",
        "report_markers": (
            "7,200 个唯一 case-arm 行",
            "`clinical-complete` / `compatible-partial` 缺失 0，重叠 0",
        ),
    },
    {
        "experiment_id": "E4",
        "report_path": "analysis/mechanism_v2/results/E4_fixed_pool_crossover/REPORT.md",
        "arm_count": 5,
        "intended_case_n": 400,
        "clinical_complete_status": TARGETED_ONLY,
        "compatible_partial_status": NOT_AVAILABLE,
        "complete_or_compatible_partial_status": NOT_AVAILABLE,
        "blind_status": "selector_blinded_targeted_transition_review",
        "full_root_census": False,
        "conclusion_use": "safe_exact_fixed_pool_selector_mechanism_only",
        "raw_legacy_field_risk": "generic_accuracy_and_primary_strict_fields_mean_safe_exact",
        "coverage_note": "All 17 safe-exact correctness discordances and 12 sampled all-miss flips were reviewed; the remaining outputs are not clinically censused.",
        "report_markers": (
            "Clinical audit coverage is bounded",
            "The other 154 all-miss cases",
        ),
    },
    {
        "experiment_id": "E5",
        "report_path": "analysis/mechanism_v2/results/E5_candidate_interference/REPORT.md",
        "arm_count": 9,
        "intended_case_n": 200,
        "clinical_complete_status": TARGETED_ONLY,
        "compatible_partial_status": TARGETED_ONLY,
        "complete_or_compatible_partial_status": NOT_AVAILABLE,
        "blind_status": "targeted_nonblind_relation_and_transition_review",
        "full_root_census": False,
        "conclusion_use": "safe_exact_candidate_interference_mechanism_only",
        "raw_legacy_field_risk": "strict_top1_fields_are_safe_exact_aliases",
        "coverage_note": "The 339 judgments cover construction labels, injected champions, and sampled transitions; they are not 1,800 case-arm clinical outcomes.",
        "report_markers": (
            "The manual clinical audit contains 339 explicit judgments",
            "rather than a replacement whole-experiment clinical score",
        ),
    },
    {
        "experiment_id": "E6",
        "report_path": "analysis/mechanism_v2/results/E6_representation_fidelity/REPORT.md",
        "arm_count": 3,
        "intended_case_n": 300,
        "clinical_complete_status": PROXY_ROOT_PRIORITY,
        "compatible_partial_status": PROXY_ROOT_PRIORITY,
        "complete_or_compatible_partial_status": PROXY_ROOT_PRIORITY,
        "blind_status": "arm_blind_external_screen_with_targeted_root_correction",
        "full_root_census": False,
        "conclusion_use": "semantic_proxy_sensitivity_not_capability_leaderboard",
        "raw_legacy_field_risk": "strict_top1_alias_plus_complete_equivalent_proxy_may_be_overread",
        "coverage_note": "801 served outputs are proxy-completed; 262 rows received root review and 539 remain external-screen-only.",
        "report_markers": (
            "根代理人工责任覆盖 94 例、262 个输出",
            "它**不是**对三臂全部输出的逐例人工临床审计",
        ),
    },
    {
        "experiment_id": "E6x",
        "report_path": "analysis/mechanism_v2/results/E6x_unpadded_flat/REPORT.md",
        "arm_count": 2,
        "intended_case_n": 300,
        "clinical_complete_status": PROXY_ROOT_PRIORITY,
        "compatible_partial_status": PROXY_ROOT_PRIORITY,
        "complete_or_compatible_partial_status": PROXY_ROOT_PRIORITY,
        "blind_status": "arm_blind_external_screen_with_targeted_root_correction",
        "full_root_census": False,
        "conclusion_use": "semantic_proxy_sensitivity_not_capability_leaderboard",
        "raw_legacy_field_risk": "strict_top1_alias_plus_complete_equivalent_proxy_may_be_overread",
        "coverage_note": "All 513 served outputs have proxy labels, but only 126 judgments in 63 cases received root review.",
        "report_markers": (
            "根代理最终复核 33 个完整等价分歧和 30 个冻结一致样本",
            "不是完整 300 例临床 leaderboard",
        ),
    },
    {
        "experiment_id": "E7a",
        "report_path": "analysis/mechanism_v2/results/E7_registry_replay/REPORT.md",
        "arm_count": 3,
        "intended_case_n": 800,
        "clinical_complete_status": NOT_APPLICABLE,
        "compatible_partial_status": NOT_APPLICABLE,
        "complete_or_compatible_partial_status": NOT_APPLICABLE,
        "blind_status": "not_applicable_structural_offline_replay",
        "full_root_census": False,
        "conclusion_use": "structural_registry_identity_only",
        "raw_legacy_field_risk": "legacy_substring_is_treatment_and_score_top1_gold_is_diagnostic_only",
        "coverage_note": "No fresh selector consumes the counterfactual registry, so clinical arm outcomes are undefined rather than missing.",
        "report_markers": (
            "this report does not present safe-exact diagnosis accuracy",
            "Those\nendpoints require an actual arm output",
        ),
    },
    {
        "experiment_id": "E7b",
        "report_path": "analysis/mechanism_v2/results/E7b_registry_selector/REPORT.md",
        "arm_count": 3,
        "intended_case_n": 400,
        "clinical_complete_status": TARGETED_ONLY,
        "compatible_partial_status": NOT_AVAILABLE,
        "complete_or_compatible_partial_status": NOT_AVAILABLE,
        "blind_status": "selector_blinded_targeted_priority_review",
        "full_root_census": False,
        "conclusion_use": "identity_addressability_and_safe_exact_mechanism_only",
        "raw_legacy_field_risk": "legacy_substring_is_treatment_and_gold_top1_rate_is_served_safe_exact",
        "coverage_note": "The clinical queue contains 40 priority cases; 360 cases lack exhaustive clinical equivalence adjudication.",
        "report_markers": (
            "Clinical audit coverage is explicitly limited to all 40 cases",
            "The remaining 360 selected cases were not exhaustively adjudicated",
        ),
    },
    {
        "experiment_id": "E7c",
        "report_path": "analysis/mechanism_v2/results/E7c_directional_registry/REPORT.md",
        "arm_count": 4,
        "intended_case_n": 299,
        "clinical_complete_status": TARGETED_ONLY,
        "compatible_partial_status": NOT_AVAILABLE,
        "complete_or_compatible_partial_status": NOT_AVAILABLE,
        "blind_status": "selector_blinded_discordance_enriched_root_review",
        "full_root_census": False,
        "conclusion_use": "safe_exact_and_relation_fidelity_mechanism_only",
        "raw_legacy_field_risk": "gold_top1_rate_is_served_safe_exact_while_primary_report_is_ita",
        "coverage_note": "All 84 discordant cases were mechanism-reviewed, but the remaining 215 cases have no full clinical classification.",
        "report_markers": (
            "The manual clinical audit is exhaustive for all 84 cases",
            "It is not an exhaustive clinical adjudication of the remaining 215 cases",
        ),
    },
    {
        "experiment_id": "E8",
        "report_path": "analysis/mechanism_v2/results/E8_temporal_veto/REPORT.md",
        "arm_count": 4,
        "intended_case_n": 220,
        "clinical_complete_status": TARGETED_ONLY,
        "compatible_partial_status": TARGETED_ONLY,
        "complete_or_compatible_partial_status": NOT_AVAILABLE,
        "blind_status": "selector_blinded_mechanism_enriched_root_review",
        "full_root_census": False,
        "conclusion_use": "veto_safety_mechanism_only",
        "raw_legacy_field_risk": "summary_accuracy_is_served_safe_exact",
        "coverage_note": "Root review covers 30 mechanism-enriched cases; 190 cases have no complete/compatible-partial/no judgment.",
        "report_markers": (
            "根代理逐案审计 30 例",
            "其余 190/220 例未做临床 complete/compatible-partial/no 逐案裁决",
        ),
    },
    {
        "experiment_id": "E9",
        "report_path": "analysis/mechanism_v2/results/E9_view_independence/REPORT.md",
        "arm_count": 4,
        "intended_case_n": 400,
        "clinical_complete_status": NOT_AVAILABLE,
        "compatible_partial_status": NOT_AVAILABLE,
        "complete_or_compatible_partial_status": NOT_AVAILABLE,
        "blind_status": "selector_blinded_mechanism_enriched_root_review",
        "full_root_census": False,
        "conclusion_use": "view_capture_and_instability_mechanism_only",
        "raw_legacy_field_risk": "strict_endpoint_fields_are_safe_exact_aliases",
        "coverage_note": "The frozen root queue has 70 cases, but its legacy binary scope/surface labels do not implement the canonical complete/compatible-partial/no partition; 330 cases remain clinically unadjudicated.",
        "report_markers": (
            "70 例是机制富集人工队列",
            "其余 330 例没有 complete/compatible-partial/no 根裁决",
        ),
    },
    {
        "experiment_id": "E10",
        "report_path": "analysis/mechanism_v2/results/E10_mac_factorial/REPORT.md",
        "arm_count": 4,
        "intended_case_n": 400,
        "clinical_complete_status": E10_MISLABEL,
        "compatible_partial_status": E10_PARTIAL,
        "complete_or_compatible_partial_status": E10_UNION,
        "blind_status": "nonblind_root_priority_binary_screen_review",
        "full_root_census": False,
        "conclusion_use": "binary_acceptable_sensitivity_only_no_clinical_endpoint_no_leaderboard",
        "raw_legacy_field_risk": "binary_acceptable_historical_values_are_not_complete_or_complete_plus_partial",
        "coverage_note": "The corrected table is explicitly binary-clinical-acceptable only; complete, compatible-partial and their union are unmeasured. 166 cases were root-reviewed and 234 remain proxy-negative.",
        "report_markers": (
            "端点迁移更正",
            "全臂三 reviewer model-panel census",
        ),
    },
    {
        "experiment_id": "E11",
        "report_path": "analysis/mechanism_v2/results/E11_b07_factorial/REPORT.md",
        "arm_count": 8,
        "intended_case_n": 400,
        "clinical_complete_status": PROXY_ROOT_PRIORITY,
        "compatible_partial_status": PROXY_ROOT_PRIORITY,
        "complete_or_compatible_partial_status": PROXY_ROOT_PRIORITY,
        "blind_status": "nonblind_endpoint_critical_root_overrides_with_proxy_completion",
        "full_root_census": False,
        "conclusion_use": "root_priority_proxy_sensitivity_not_capability_leaderboard",
        "raw_legacy_field_risk": "clinical_complete_star_and_complete_partial_star_are_proxy_completed",
        "coverage_note": "Root review covers 624 of 6,400 arm-rank occurrences; 5,776 occurrences retain heterogeneous proxy labels.",
        "report_markers": (
            "其余 5,776/6,400 个 occurrence",
            "不能当作 400 例全人工或盲法临床标注",
        ),
    },
    {
        "experiment_id": "E12",
        "report_path": "analysis/mechanism_v2/results/E12_e7_factorial/REPORT.md",
        "arm_count": 20,
        "intended_case_n": 300,
        "clinical_complete_status": PROXY_ROOT_PRIORITY,
        "compatible_partial_status": PROXY_ROOT_PRIORITY,
        "complete_or_compatible_partial_status": PROXY_ROOT_PRIORITY,
        "blind_status": "nonblind_arm_visible_endpoint_critical_root_overrides_with_proxy_completion",
        "full_root_census": False,
        "conclusion_use": "root_priority_proxy_sensitivity_not_capability_leaderboard",
        "raw_legacy_field_risk": "clinical_complete_star_and_complete_partial_star_are_proxy_completed",
        "coverage_note": "Root review covers 385 of 3,191 candidate relations in 154 cases; 2,806 relations remain heterogeneous proxy.",
        "report_markers": (
            "根审计随后逐候选复核 154/300 个病例、385/3,191 个 case-candidate relation",
            "其余 2,806 条关系没有人工逐候选复核",
        ),
    },
    {
        "experiment_id": "E14x",
        "report_path": "analysis/mechanism_v2/results/E14x_runtime_gate/REPORT.md",
        "arm_count": 2,
        "intended_case_n": 300,
        "clinical_complete_status": TARGETED_ONLY,
        "compatible_partial_status": TARGETED_ONLY,
        "complete_or_compatible_partial_status": NOT_AVAILABLE,
        "blind_status": "retrospective_mechanism_enriched_root_review",
        "full_root_census": False,
        "conclusion_use": "retrospective_gate_mechanism_only_no_causal_leaderboard",
        "raw_legacy_field_risk": "strict_gate_and_mapper_fields_are_not_clinical_endpoints",
        "coverage_note": "The primary comparison has two historical arms over 300 cases; 56 cases were root-reviewed and no proxy completion was performed.",
        "report_markers": (
            "类别重叠后为 56/300 个唯一病例逐案审计",
            "没有 proxy 补全临床端点",
        ),
    },
    {
        "experiment_id": "RCR3",
        "report_path": "analysis/mechanism_v2/results/RCR3_relation_preserving/REPORT.md",
        "arm_count": 3,
        "intended_case_n": 300,
        "clinical_complete_status": PROXY_ROOT_PRIORITY,
        "compatible_partial_status": PROXY_ROOT_PRIORITY,
        "complete_or_compatible_partial_status": PROXY_ROOT_PRIORITY,
        "blind_status": "nonblind_arm_visible_endpoint_critical_root_overrides_with_proxy_completion",
        "full_root_census": False,
        "conclusion_use": "root_priority_proxy_sensitivity_not_capability_leaderboard",
        "raw_legacy_field_risk": "strict_fields_and_clinical_complete_star_are_not_full_root",
        "coverage_note": "375 high-impact relations were root-reviewed; 3,151 noncritical relations retain heterogeneous proxy and 7 screen failures are fail-closed.",
        "report_markers": (
            "375 条为 root manual、3,151 条为 heterogeneous proxy noncritical",
            "root-priority/proxy-completed 端点",
        ),
    },
)


ARM_IDS: dict[str, tuple[str, ...]] = {
    "E1": (
        "aphhm_hierarchical__clean_fixed", "aphhm_hierarchical__clean_shuffled_blocks",
        "aphhm_hierarchical__options_fixed", "aphhm_hierarchical__options_shuffled_blocks",
        "ab02_flat__clean_fixed", "ab02_flat__clean_shuffled_blocks",
        "ab02_flat__options_fixed", "ab02_flat__options_shuffled_blocks",
    ),
    "E2": ("collapse3c", "multistance", "lite", "forest", "impc", "e7", "v0", "B06", "B07"),
    "E4": ("evidence_count_control", "e7_contrast", "forest_evidence_integrator", "collapse_obligation_ledger", "pairwise_tournament"),
    "E5": ("base4", "remove_non_gold3", "add_parent5", "add_sibling5", "add_unrelated5", "add_synonym5", "add_component5", "nested_width6", "nested_width8"),
    "E6": ("raw_vignette", "flat_facts", "typed_event_graph"),
    "E6x": ("flat_facts_padded", "flat_facts_unpadded"),
    "E7a": ("legacy_substring", "exact_synonym", "typed_relation"),
    "E7b": ("legacy_substring", "exact_synonym", "typed_relation"),
    "E7c": ("exact_control", "generic_non_equivalence", "directional_relation", "bounded_inheritance"),
    "E8": ("atemporal_hard_veto", "time_scope_soft_veto", "time_scope_soft_legal_order", "time_scope_soft_invalid_time"),
    "E9": ("real_views", "role_rotated", "single_anchor", "duplicate_anchor"),
    "E10": ("isolated_rrf", "isolated_supervisor", "sequential_rrf", "sequential_supervisor"),
    "E11": ("off_refine_off", "off_refine_on", "relevant_refine_off", "relevant_refine_on", "random_refine_off", "random_refine_on", "hard_negative_refine_off", "hard_negative_refine_on"),
    "E12": (
        "raw_k5_first", "raw_k5_pointwise", "raw_k5_pairwise", "raw_k10_first", "raw_k10_pointwise", "raw_k10_pairwise",
        "s1_k5_first", "s1_k5_pointwise", "s1_k5_pairwise", "s1_k10_first", "s1_k10_pointwise", "s1_k10_pairwise",
        "graph_k5_first", "graph_k5_pointwise", "graph_k5_pairwise", "graph_k10_first", "graph_k10_pointwise", "graph_k10_pairwise",
        "raw_depth1_k10_pairwise", "raw_depth2_k10_pairwise",
    ),
    "E14x": ("mosaic_lite_v1", "mosaic_adaptive4v2_v1"),
    "RCR3": ("lite3_safe", "rcr3_default", "compact4_true3gen"),
}


# ARM_IDS is the root-auditor's canonical ordering, not its own evidence.  Every
# tuple is checked against an independently stored machine artifact below.  The
# parsers intentionally vary with the owning experiment's frozen schema rather
# than guessing arm names from prose or directory names.
ARM_REGISTRY_SOURCES: dict[str, dict[str, Any]] = {
    "E1": {
        "path": "analysis/mechanism_v2/results/E1_input_factorial/preregistration.json",
        "parser": "json_list_at_path",
        "json_path": ("arms",),
        "source_kind": "pre_online_preregistration",
    },
    "E2": {
        "path": "analysis/mechanism_v2/results/E2_blinded_clinical_adjudication/unified_800/manifest.json",
        "parser": "json_list_at_path",
        "json_path": ("arms",),
        "source_kind": "full_replay_manifest",
    },
    "E4": {
        "path": "analysis/mechanism_v2/results/E4_fixed_pool_crossover/preregistration.json",
        "parser": "json_list_at_path",
        "json_path": ("arms",),
        "source_kind": "pre_online_preregistration",
    },
    "E5": {
        "path": "analysis/mechanism_v2/results/E5_candidate_interference/preregistration.json",
        "parser": "json_list_at_path",
        "json_path": ("arms",),
        "source_kind": "pre_online_preregistration",
    },
    "E6": {
        "path": "analysis/mechanism_v2/results/E6_representation_fidelity/preregistration.json",
        "parser": "json_list_at_path",
        "json_path": ("arms",),
        "source_kind": "pre_online_preregistration",
    },
    "E6x": {
        "path": "analysis/mechanism_v2/results/E6x_unpadded_flat/semantic_final_summary.json",
        "parser": "json_object_keys_at_path",
        "json_path": ("arms",),
        "source_kind": "final_semantic_analysis_arm_table",
    },
    "E7a": {
        "path": "analysis/mechanism_v2/results/E7_registry_replay/summary.json",
        "parser": "json_consistent_group_arm_keys",
        "source_kind": "full_structural_replay_group_tables",
    },
    "E7b": {
        "path": "analysis/mechanism_v2/results/E7b_registry_selector/preregistration.json",
        "parser": "json_list_at_path",
        "json_path": ("arms",),
        "source_kind": "pre_online_preregistration",
    },
    "E7c": {
        "path": "analysis/mechanism_v2/results/E7c_directional_registry/preregistration.json",
        "parser": "json_list_at_path",
        "json_path": ("arms",),
        "source_kind": "pre_online_preregistration",
    },
    "E8": {
        "path": "analysis/mechanism_v2/results/E8_temporal_veto/preregistration.json",
        "parser": "json_list_at_path",
        "json_path": ("arms",),
        "source_kind": "pre_online_preregistration",
    },
    "E9": {
        "path": "analysis/mechanism_v2/results/E9_view_independence/preregistration.json",
        "parser": "json_list_at_path",
        "json_path": ("arms",),
        "source_kind": "pre_online_preregistration",
    },
    "E10": {
        "path": "analysis/mechanism_v2/results/E10_mac_factorial/preregistration.json",
        "parser": "json_list_at_path",
        "json_path": ("arms",),
        "source_kind": "pre_online_preregistration",
    },
    "E11": {
        "path": "analysis/mechanism_v2/results/E11_b07_factorial/preregistration.json",
        "parser": "json_list_at_path",
        "json_path": ("arms",),
        "source_kind": "pre_online_preregistration",
    },
    "E12": {
        "path": "analysis/mechanism_v2/results/E12_e7_factorial/case_conditions.jsonl",
        "parser": "jsonl_unique_string_field",
        "field": "arm",
        "source_kind": "all_served_case_condition_rows",
    },
    "E14x": {
        "path": "analysis/mechanism_v2/results/E14x_runtime_gate/source_provenance.json",
        "parser": "e14x_primary_manifest_dataset_intersection",
        "required_datasets": (
            "diagnosisarena",
            "medcasereasoning",
            "medcasereasoning_v2",
        ),
        "source_kind": "frozen_provenance_index_primary_dataset_intersection",
        "source_limit": (
            "The indexed historical log manifests are absent from this sparse checkout; "
            "the checked-in provenance index and its recorded paths/hashes are the machine source."
        ),
    },
    "RCR3": {
        "path": "analysis/mechanism_v2/results/RCR3_relation_preserving/preregistration.json",
        "parser": "json_object_keys_at_path",
        "json_path": ("arms",),
        "source_kind": "pre_online_preregistration",
    },
}


REQUIRED_RECORD_FIELDS = frozenset(
    {
        "experiment_id",
        "report_path",
        "arm_count",
        "intended_case_n",
        "clinical_complete_status",
        "compatible_partial_status",
        "complete_or_compatible_partial_status",
        "blind_status",
        "full_root_census",
        "conclusion_use",
        "raw_legacy_field_risk",
        "coverage_note",
    }
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_value_at_path(payload: Any, json_path: Sequence[str], label: str) -> Any:
    value = payload
    for key in json_path:
        if not isinstance(value, Mapping) or key not in value:
            raise AssertionError(f"{label}: missing JSON path component {key!r}")
        value = value[key]
    return value


def _validated_string_ids(values: Any, label: str) -> list[str]:
    if not isinstance(values, list) or not values:
        raise AssertionError(f"{label}: arm registry must be a non-empty list")
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise AssertionError(f"{label}: arm registry contains a non-string/empty id")
    result = [str(value) for value in values]
    if len(result) != len(set(result)):
        raise AssertionError(f"{label}: duplicate arm ids: {result!r}")
    return result


def _parse_arm_registry_source(
    root: Path, experiment_id: str, spec: Mapping[str, Any]
) -> dict[str, Any]:
    relative_path = str(spec["path"])
    source_path = root / relative_path
    if not source_path.is_file():
        raise AssertionError(
            f"missing arm-registry source for {experiment_id}: {source_path}"
        )
    parser = str(spec["parser"])
    parse_details: dict[str, Any] = {}

    if parser in {"json_list_at_path", "json_object_keys_at_path"}:
        payload = json.loads(source_path.read_text(encoding="utf-8"))
        json_path = tuple(str(key) for key in spec.get("json_path", ()))
        value = _json_value_at_path(payload, json_path, experiment_id)
        if parser == "json_list_at_path":
            arm_ids = _validated_string_ids(value, experiment_id)
        else:
            if not isinstance(value, Mapping) or not value:
                raise AssertionError(
                    f"{experiment_id}: arm registry at {json_path!r} must be a non-empty object"
                )
            arm_ids = _validated_string_ids(list(value), experiment_id)
        parse_details["json_path"] = list(json_path)
    elif parser == "json_consistent_group_arm_keys":
        payload = json.loads(source_path.read_text(encoding="utf-8"))
        groups = payload.get("groups") if isinstance(payload, Mapping) else None
        if not isinstance(groups, list) or not groups:
            raise AssertionError(f"{experiment_id}: missing non-empty groups array")
        group_arm_ids: list[list[str]] = []
        for index, group in enumerate(groups):
            arms = group.get("arms") if isinstance(group, Mapping) else None
            if not isinstance(arms, Mapping) or not arms:
                raise AssertionError(f"{experiment_id}: groups[{index}].arms is invalid")
            group_arm_ids.append(
                _validated_string_ids(list(arms), f"{experiment_id}/groups[{index}]")
            )
        first_set = set(group_arm_ids[0])
        if any(set(values) != first_set for values in group_arm_ids[1:]):
            raise AssertionError(f"{experiment_id}: arm keys differ across analysis groups")
        arm_ids = group_arm_ids[0]
        parse_details.update(
            {
                "json_path": ["groups", "*", "arms", "<keys>"],
                "groups_checked": len(group_arm_ids),
            }
        )
    elif parser == "jsonl_unique_string_field":
        field = str(spec["field"])
        observed: list[str] = []
        rows_n = 0
        for line_number, line in enumerate(
            source_path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if not line.strip():
                continue
            rows_n += 1
            row = json.loads(line)
            value = row.get(field) if isinstance(row, Mapping) else None
            if not isinstance(value, str) or not value.strip():
                raise AssertionError(
                    f"{experiment_id}: invalid {field!r} in JSONL line {line_number}"
                )
            if value not in observed:
                observed.append(value)
        arm_ids = _validated_string_ids(observed, experiment_id)
        parse_details.update({"jsonl_field": field, "rows_checked": rows_n})
    elif parser == "e14x_primary_manifest_dataset_intersection":
        payload = json.loads(source_path.read_text(encoding="utf-8"))
        inputs = payload.get("inputs") if isinstance(payload, Mapping) else None
        if not isinstance(inputs, list) or not inputs:
            raise AssertionError(f"{experiment_id}: provenance inputs are missing")
        required_datasets = tuple(str(item) for item in spec["required_datasets"])
        arms_by_dataset: dict[str, set[str]] = {
            dataset: set() for dataset in required_datasets
        }
        manifest_hashes: dict[str, str] = {}
        for item in inputs:
            if not isinstance(item, Mapping):
                continue
            path_text = str(item.get("path", ""))
            parts = Path(path_text).parts
            if (
                len(parts) == 5
                and parts[:2] == ("logs", "backbone_v1")
                and parts[2] in arms_by_dataset
                and parts[4] == "manifest.json"
            ):
                recorded_hash = str(item.get("sha256", ""))
                if len(recorded_hash) != 64 or any(
                    character not in "0123456789abcdef" for character in recorded_hash
                ):
                    raise AssertionError(
                        f"{experiment_id}: invalid recorded manifest hash for {path_text}"
                    )
                dataset, arm_id = parts[2], parts[3]
                arms_by_dataset[dataset].add(arm_id)
                manifest_hashes[f"{dataset}/{arm_id}"] = recorded_hash
        if any(not arms for arms in arms_by_dataset.values()):
            raise AssertionError(
                f"{experiment_id}: one or more primary datasets lack indexed arm manifests"
            )
        shared = set.intersection(*(arms for arms in arms_by_dataset.values()))
        arm_ids = _validated_string_ids(sorted(shared), experiment_id)
        parse_details.update(
            {
                "required_datasets": list(required_datasets),
                "indexed_arms_by_dataset": {
                    dataset: sorted(arms) for dataset, arms in arms_by_dataset.items()
                },
                "shared_primary_arm_rule": "intersection across all required datasets",
                "indexed_manifest_sha256": dict(sorted(manifest_hashes.items())),
            }
        )
    elif parser == "manual_frozen":
        reason = str(spec.get("manual_reason", "")).strip()
        if not reason:
            raise AssertionError(f"{experiment_id}: manual frozen source lacks a reason")
        arm_ids = _validated_string_ids(list(spec.get("arm_ids", ())), experiment_id)
        parse_details["manual_reason"] = reason
    else:
        raise AssertionError(f"{experiment_id}: unsupported arm-registry parser {parser!r}")

    return {
        "experiment_id": experiment_id,
        "path": relative_path,
        "sha256": _sha256(source_path),
        "parser": parser,
        "source_kind": str(spec["source_kind"]),
        "source_limit": spec.get("source_limit"),
        "source_arm_ids": arm_ids,
        "source_arm_count": len(arm_ids),
        "parse_details": parse_details,
    }


def _validate_arm_registry_sources(root: Path) -> dict[str, dict[str, Any]]:
    if set(ARM_REGISTRY_SOURCES) != set(EXPECTED_EXPERIMENT_IDS):
        raise AssertionError("arm-registry sources and experiment registry are not a bijection")
    if set(ARM_IDS) != set(EXPECTED_EXPERIMENT_IDS):
        raise AssertionError("audited arm declarations and experiment registry are not a bijection")

    parsed: dict[str, dict[str, Any]] = {}
    for experiment_id in EXPECTED_EXPERIMENT_IDS:
        source = _parse_arm_registry_source(
            root, experiment_id, ARM_REGISTRY_SOURCES[experiment_id]
        )
        source_ids = set(source["source_arm_ids"])
        audit_ids = set(ARM_IDS[experiment_id])
        if source_ids != audit_ids:
            raise AssertionError(
                f"{experiment_id}: audit/source arm registry mismatch; "
                f"missing_from_source={sorted(audit_ids - source_ids)!r}, "
                f"unexpected_in_source={sorted(source_ids - audit_ids)!r}"
            )
        source["audit_arm_ids"] = list(ARM_IDS[experiment_id])
        source["validation_status"] = "declared_audit_arms_match_independent_source"
        parsed[experiment_id] = source

    total = sum(len(source["source_arm_ids"]) for source in parsed.values())
    if total != 91:
        raise AssertionError(f"independently sourced arm registry must contain 91 rows, found {total}")
    return parsed


def _assert_report_evidence(root: Path, spec: Mapping[str, Any]) -> str:
    report_path = root / str(spec["report_path"])
    if not report_path.is_file():
        raise AssertionError(f"missing source report for {spec['experiment_id']}: {report_path}")
    report_text = report_path.read_text(encoding="utf-8")
    for marker in spec.get("report_markers", ()):
        if marker not in report_text:
            raise AssertionError(
                f"coverage evidence drift for {spec['experiment_id']}: missing marker {marker!r}"
            )
    return _sha256(report_path)


def validate_records(
    records: Sequence[Mapping[str, Any]],
    arm_registry_sources: Mapping[str, Mapping[str, Any]],
) -> None:
    ids = [str(record.get("experiment_id")) for record in records]
    if tuple(ids) != EXPECTED_EXPERIMENT_IDS:
        raise AssertionError(
            "experiment coverage/order drift: "
            f"expected {list(EXPECTED_EXPERIMENT_IDS)!r}, found {ids!r}"
        )
    if len(ids) != len(set(ids)):
        raise AssertionError(f"duplicate experiment ids: {ids!r}")
    if set(arm_registry_sources) != set(EXPECTED_EXPERIMENT_IDS):
        raise AssertionError("validated arm sources and experiment registry are not a bijection")

    for record in records:
        missing = REQUIRED_RECORD_FIELDS - set(record)
        if missing:
            raise AssertionError(
                f"{record.get('experiment_id')} missing required fields: {sorted(missing)!r}"
            )
        if type(record["arm_count"]) is not int or record["arm_count"] <= 0:
            raise AssertionError(f"invalid arm_count for {record['experiment_id']}")
        if type(record["intended_case_n"]) is not int or record["intended_case_n"] <= 0:
            raise AssertionError(f"invalid intended_case_n for {record['experiment_id']}")
        if type(record["full_root_census"]) is not bool:
            raise AssertionError(f"full_root_census must be bool for {record['experiment_id']}")
        arm_ids = ARM_IDS[str(record["experiment_id"])]
        source = arm_registry_sources[str(record["experiment_id"])]
        if len(arm_ids) != record["arm_count"] or len(arm_ids) != len(set(arm_ids)):
            raise AssertionError(f"arm registry count/uniqueness drift for {record['experiment_id']}")
        if set(arm_ids) != set(source["source_arm_ids"]):
            raise AssertionError(f"validated arm source drift for {record['experiment_id']}")
        if record["arm_count"] != source["source_arm_count"]:
            raise AssertionError(
                f"validated arm-source count drift for {record['experiment_id']}"
            )
        for field in (
            "clinical_complete_status",
            "compatible_partial_status",
            "complete_or_compatible_partial_status",
        ):
            if record[field] not in ALLOWED_ENDPOINT_STATUSES:
                raise AssertionError(
                    f"invalid {field} for {record['experiment_id']}: {record[field]!r}"
                )

    full_root_ids = {record["experiment_id"] for record in records if record["full_root_census"]}
    if full_root_ids != FULL_ROOT_CENSUS_ALLOWLIST:
        raise AssertionError(
            "full-root census allowlist violation: "
            f"expected {sorted(FULL_ROOT_CENSUS_ALLOWLIST)!r}, found {sorted(full_root_ids)!r}"
        )

    for record in records:
        endpoint_statuses = {
            record["clinical_complete_status"],
            record["compatible_partial_status"],
            record["complete_or_compatible_partial_status"],
        }
        if record["full_root_census"]:
            if endpoint_statuses != {FULL_ROOT}:
                raise AssertionError(
                    f"full-root record lacks all three census endpoints: {record['experiment_id']}"
                )
            if record["conclusion_use"] != "clinical_capability_leaderboard":
                raise AssertionError(
                    f"full-root record is not leaderboard-enabled: {record['experiment_id']}"
                )
        elif record["conclusion_use"] == "clinical_capability_leaderboard":
            raise AssertionError(
                f"non-full record cannot feed a capability leaderboard: {record['experiment_id']}"
            )

    by_id = {record["experiment_id"]: record for record in records}
    e7a = by_id["E7a"]
    if {
        e7a["clinical_complete_status"],
        e7a["compatible_partial_status"],
        e7a["complete_or_compatible_partial_status"],
    } != {NOT_APPLICABLE}:
        raise AssertionError("E7a must remain clinical-endpoint N/A without a fresh arm output")
    if by_id["E10"]["clinical_complete_status"] not in {
        E10_MISLABEL,
        FULL_BLINDED_PANEL,
    }:
        raise AssertionError(
            "E10 must retain either its historical binary-only status or the "
            "new full blinded panel status"
        )


def _migration_contract(root: Path) -> dict[str, Any] | None:
    summary_path = root / MIGRATION_SUMMARY_PATH
    replay_path = root / MIGRATION_REPLAY_PATH
    if not summary_path.is_file() and not replay_path.is_file():
        return None
    if not summary_path.is_file() or not replay_path.is_file():
        raise AssertionError("endpoint migration final artifacts are only partially present")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if summary.get("schema_version") != "canonical-endpoint-migration-final-v1":
        raise AssertionError("unsupported endpoint migration final schema")
    if int(summary.get("n_arms") or 0) != 79:
        raise AssertionError("endpoint migration must cover exactly 79 arms")
    if int(summary.get("n_intention_rows") or 0) != 24076:
        raise AssertionError("endpoint migration intention ledger drift")
    if int(summary.get("n_served_rows") or 0) != 23046:
        raise AssertionError("endpoint migration served ledger drift")
    if int(summary.get("n_task_payloads") or 0) != 5839:
        raise AssertionError("endpoint migration task registry drift")
    if summary.get("task_census_status") != "complete_fresh_replay":
        raise AssertionError("endpoint migration fresh task census is incomplete")
    if summary.get("clinical_census_status") not in {
        "full_blinded_model_panel_sensitivity_not_root",
        "full_blinded_three_model_panel_census_not_root",
        "full_root_census",
    }:
        raise AssertionError("endpoint migration clinical census is incomplete")
    return {
        "summary": summary,
        "summary_path": str(MIGRATION_SUMMARY_PATH),
        "summary_sha256": _sha256(summary_path),
        "replay_path": str(MIGRATION_REPLAY_PATH),
        "replay_sha256": _sha256(replay_path),
    }


def build_payload(root: Path = ROOT) -> dict[str, Any]:
    arm_registry_sources = _validate_arm_registry_sources(root)
    migration = _migration_contract(root)
    records: list[dict[str, Any]] = []
    for spec in EXPERIMENT_SPECS:
        record = {key: value for key, value in spec.items() if key != "report_markers"}
        record["source_report_sha256"] = _assert_report_evidence(root, spec)
        record["arm_registry_source"] = arm_registry_sources[
            str(record["experiment_id"])
        ]
        if migration is not None and str(record["experiment_id"]) in MIGRATION_EXPERIMENT_IDS:
            record.update(
                {
                    "clinical_complete_status": FULL_BLINDED_PANEL,
                    "compatible_partial_status": FULL_BLINDED_PANEL,
                    "complete_or_compatible_partial_status": FULL_BLINDED_PANEL,
                    "blind_status": "arm_hidden_three_reviewer_panel_census",
                    "full_root_census": False,
                    "conclusion_use": "full_panel_clinical_sensitivity_not_root_capability_leaderboard",
                    "coverage_note": (
                        "All intended rows have deterministic failure handling and all served "
                        "Top-1 relations have blinded three-reviewer panel decisions; "
                        "unanimous, majority, and unresolved decisions retain explicit "
                        "model-panel provenance rather than human-root ownership."
                    ),
                    "migration_artifact_path": migration["replay_path"],
                    "migration_artifact_sha256": migration["replay_sha256"],
                }
            )
        record["clinical_capability_leaderboard_eligible"] = bool(record["full_root_census"])
        record["leaderboard_ingestion"] = (
            "allowed" if record["full_root_census"] else "prohibited"
        )
        record["direct_raw_summary_flattening"] = "prohibited"
        record["coverage_gated_cross_matrix_required"] = True
        records.append(record)

    validate_records(records, arm_registry_sources)
    arm_records = [
        {
            "experiment_id": record["experiment_id"],
            "arm_id": arm_id,
            "intended_case_n": record["intended_case_n"],
            "clinical_complete_status": record["clinical_complete_status"],
            "compatible_partial_status": record["compatible_partial_status"],
            "complete_or_compatible_partial_status": record[
                "complete_or_compatible_partial_status"
            ],
            "blind_status": record["blind_status"],
            "full_root_census": record["full_root_census"],
            "clinical_capability_leaderboard_eligible": record[
                "clinical_capability_leaderboard_eligible"
            ],
            "leaderboard_ingestion": record["leaderboard_ingestion"],
            "direct_raw_summary_flattening": record[
                "direct_raw_summary_flattening"
            ],
            "coverage_gated_cross_matrix_required": record[
                "coverage_gated_cross_matrix_required"
            ],
            "arm_registry_source_path": record["arm_registry_source"]["path"],
            "arm_registry_source_sha256": record["arm_registry_source"]["sha256"],
            "arm_registry_source_kind": record["arm_registry_source"]["source_kind"],
            "arm_registry_validation_status": record["arm_registry_source"][
                "validation_status"
            ],
        }
        for record in records
        for arm_id in ARM_IDS[str(record["experiment_id"])]
    ]
    if len(arm_records) != 91 or len({(row["experiment_id"], row["arm_id"]) for row in arm_records}) != 91:
        raise AssertionError("arm-level endpoint matrix must contain 91 unique experiment-arm rows")
    full_census_arm_count = sum(bool(row["full_root_census"]) for row in arm_records)
    not_applicable_arm_count = sum(
        {
            row["clinical_complete_status"],
            row["compatible_partial_status"],
            row["complete_or_compatible_partial_status"],
        }
        == {NOT_APPLICABLE}
        for row in arm_records
    )
    panel_census_arm_count = sum(
        row["clinical_complete_status"] == FULL_BLINDED_PANEL for row in arm_records
    )
    migration_gap_arm_count = (
        len(arm_records)
        - full_census_arm_count
        - panel_census_arm_count
        - not_applicable_arm_count
    )
    expected_counts = (9, 79, 0, 3) if migration is not None else (9, 0, 79, 3)
    observed_counts = (
        full_census_arm_count,
        panel_census_arm_count,
        migration_gap_arm_count,
        not_applicable_arm_count,
    )
    if observed_counts != expected_counts:
        raise AssertionError(
            f"arm-level endpoint coverage drift: expected {expected_counts}, found {observed_counts}"
        )
    return {
        "schema_version": "endpoint-coverage-audit-v2",
        "experiment_count": len(records),
        "expected_experiment_ids": list(EXPECTED_EXPERIMENT_IDS),
        "full_root_census_allowlist": sorted(FULL_ROOT_CENSUS_ALLOWLIST),
        "migration_contract": migration,
        "leaderboard_rule": (
            "Only full_root_census=true records may be ingested into a clinical-capability "
            "leaderboard; proxy/root-priority, targeted, unavailable, and structural-only "
            "records are prohibited."
        ),
        "raw_summary_ingestion_rule": (
            "Frozen raw experiment summaries are provenance, not a flattenable cross-experiment "
            "endpoint table. Downstream consumers must join through this endpoint coverage contract "
            "before using any strict, generic accuracy, complete*, task, or other historical field."
        ),
        "direct_raw_summary_flattening": "prohibited",
        "coverage_gated_cross_matrix_required": True,
        "records": records,
        "arm_record_count": len(arm_records),
        "arm_coverage_summary": {
            "full_blinded_root_census_arm_count": full_census_arm_count,
            "full_blinded_model_panel_census_arm_count": panel_census_arm_count,
            "metric_migration_gap_arm_count": migration_gap_arm_count,
            "structural_not_applicable_arm_count": not_applicable_arm_count,
        },
        "arm_records": arm_records,
        "arm_registry_source_count": len(arm_registry_sources),
        "machine_parsed_arm_registry_source_count": sum(
            source["parser"] != "manual_frozen"
            for source in arm_registry_sources.values()
        ),
        "manual_frozen_arm_registry_source_count": sum(
            source["parser"] == "manual_frozen"
            for source in arm_registry_sources.values()
        ),
        "arm_registry_sources": [
            arm_registry_sources[experiment_id]
            for experiment_id in EXPECTED_EXPERIMENT_IDS
        ],
        "arm_registry_rule": (
            "ARM_IDS is an audited canonical ordering only. Each experiment's declared arm set "
            "must equal the set parsed from its independently stored preregistration, manifest, "
            "analysis table, case-condition census, or frozen provenance index; any mismatch aborts."
        ),
        "validation": {
            "all_expected_experiments_present_once": True,
            "all_declared_audit_arms_present_once": True,
            "all_declared_audit_arms_match_independent_sources": True,
            "all_arm_registry_sources_hashed": True,
            "direct_raw_summary_flattening_prohibited": True,
            "full_root_allowlist_exact": True,
            "non_full_leaderboard_ingestion_prohibited": True,
            "e7a_structural_na_enforced": True,
            "e10_historical_binary_acceptable_blocked_from_canonical": True,
            "task_replay_complete": bool(
                migration is None
                or migration["summary"].get("task_census_status")
                == "complete_fresh_replay"
            ),
        },
    }


def render_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _short_status(value: str) -> str:
    aliases = {
        FULL_ROOT: "full-root census",
        FULL_BLINDED_PANEL: "full blinded model-panel census (not root)",
        PROXY_ROOT_PRIORITY: "proxy + root-priority",
        TARGETED_ONLY: "targeted only",
        NOT_AVAILABLE: "not available",
        NOT_APPLICABLE: "N/A (no fresh output)",
        E10_MISLABEL: "not measured (binary acceptable only)",
        E10_PARTIAL: "not measured / not separately coded",
        E10_UNION: "not measured (binary acceptable is not union)",
    }
    return aliases[value]


def render_report(payload: Mapping[str, Any]) -> str:
    records = list(payload["records"])
    coverage = payload["arm_coverage_summary"]
    migration_complete = int(coverage["metric_migration_gap_arm_count"]) == 0
    lines = [
        "# Cross-experiment endpoint coverage audit",
        "",
        "## Decision",
        "",
        (
            "Only **E2** is a full blinded/human-root-level clinical census and therefore "
            "the only experiment eligible for the strict clinical-capability leaderboard. "
            "The 79 migrated arms now have exhaustive blinded model-panel clinical endpoints, "
            "but remain blocked from that root-only leaderboard."
            if migration_complete
            else
            "Only **E2** is a full blinded/root-level clinical census and therefore the only "
            "experiment eligible for a clinical-capability leaderboard. All other experiments "
            "remain blocked pending canonical migration."
        ),
        (
            "Across 91 independently sourced declared arms, 9 E2 arms have the full root "
            "contract, 79 arms have the complete blinded model-panel contract with zero "
            "remaining metric-migration gaps, and 3 E7a structural replay arms are clinically N/A."
            if migration_complete
            else
            "Across 91 independently sourced declared arms, 9 E2 arms have the full contract, "
            "79 arms retain metric-migration gaps, and 3 E7a arms are clinically N/A."
        ),
        "",
        "Safe-exact remains a valid conservative identity lower bound. Legacy-chain, "
        "Concept, generic `accuracy`, task/mapper, or starred proxy endpoints must not be "
        "promoted to clinical-complete capability by an aggregation script.",
        "Frozen raw summaries are provenance only—not a cross-experiment table that may be "
        "flattened or ingested directly. In particular, E1/E4/E5/E6/E6x/E8 historical "
        "`strict`, generic accuracy, and `complete*`-style fields remain under their local "
        "contracts. Every downstream consumer must join through `endpoint_coverage_matrix.json` "
        "and enforce its coverage gate before reading those fields.",
        *(
            [
                "The fresh task namespace is also complete: "
                f"{payload['migration_contract']['summary']['n_task_payloads_successful']:,}/"
                f"{payload['migration_contract']['summary']['n_task_payloads']:,} unique payloads are evaluable. "
                "DA mapper and MCR judge remain separate task endpoints."
            ]
            if migration_complete
            and payload.get("migration_contract", {}).get("summary", {}).get(
                "task_census_status"
            )
            == "complete_fresh_replay"
            else []
        ),
        *(
            [
                "The migrated clinical relation contract is complete, but the fresh task "
                f"namespace is partial: {payload['migration_contract']['summary']['n_task_payloads_successful']:,}/"
                f"{payload['migration_contract']['summary']['n_task_payloads']:,} unique payloads are evaluable. "
                "Partial task rows are not used for inference."
            ]
            if migration_complete
            and payload.get("migration_contract", {}).get("summary", {}).get(
                "task_census_status"
            )
            != "complete_fresh_replay"
            else []
        ),
        "",
        "## Coverage matrix",
        "",
        "| Experiment | Arms | Intended cases/arm | Clinical complete | Compatible partial | Complete or compatible partial | Full root census | Leaderboard | Conclusion use |",
        "|---|---:|---:|---|---|---|---|---|---|",
    ]
    for record in records:
        lines.append(
            "| {experiment_id} | {arm_count} | {intended_case_n} | {clinical} | "
            "{partial} | {union} | {full_root} | {ingestion} | `{conclusion_use}` |".format(
                experiment_id=record["experiment_id"],
                arm_count=record["arm_count"],
                intended_case_n=record["intended_case_n"],
                clinical=_short_status(record["clinical_complete_status"]),
                partial=_short_status(record["compatible_partial_status"]),
                union=_short_status(record["complete_or_compatible_partial_status"]),
                full_root="yes" if record["full_root_census"] else "no",
                ingestion=record["leaderboard_ingestion"],
                conclusion_use=record["conclusion_use"],
            )
        )

    lines.extend(
        [
            "",
            "## Coverage boundaries",
            "",
        ]
    )
    for record in records:
        lines.append(
            f"- **{record['experiment_id']}** — {record['coverage_note']} "
            f"Blindness grade: `{record['blind_status']}`."
        )

    lines.extend(
        [
            "",
            "## Raw-field ingestion risks",
            "",
        ]
    )
    for record in records:
        lines.append(
            f"- **{record['experiment_id']}**: `{record['raw_legacy_field_risk']}`."
        )

    lines.extend(
        [
            "",
            "## Arm-registry sources",
            "",
            "The canonical arm ordering is checked against one independently stored machine "
            "source per experiment. Paths and SHA-256 values below are part of the generated "
            "contract; source drift, parse failure, missing/extra arms, or duplicate declared "
            "arms aborts generation.",
            "",
            "| Experiment | Parsed arms | Source kind | Parser | Source path | SHA-256 |",
            "|---|---:|---|---|---|---|",
        ]
    )
    for source in payload["arm_registry_sources"]:
        lines.append(
            "| {experiment_id} | {source_arm_count} | `{source_kind}` | `{parser}` | "
            "`{path}` | `{sha256}` |".format(**source)
        )
    for source in payload["arm_registry_sources"]:
        if source.get("source_limit"):
            lines.extend(
                [
                    "",
                    f"**{source['experiment_id']} source limit:** {source['source_limit']}",
                ]
            )

    lines.extend(
        [
            "",
            "## Fail-closed rules",
            "",
            "1. The experiment list must contain exactly the 16 registered IDs, once each, in the frozen order.",
            "2. Every canonical ARM_IDS set must exactly equal its independently parsed arm-registry source; the 91-row total is not accepted as self-validation.",
            "3. Direct flattening/ingestion of frozen raw experiment summaries is prohibited; downstream use requires a join through the coverage-gated cross matrix.",
            "4. The full-root allowlist must equal `{E2}`; model-panel census completion does not silently expand it.",
            "5. Every non-full experiment has `leaderboard_ingestion=prohibited`.",
            "6. E7a remains clinical-endpoint N/A until a fresh selector consumes each counterfactual registry.",
            "7. E10's historical binary-acceptable field remains blocked from canonical scoring; only the separate migrated model-panel ledger supplies complete/partial/union status.",
            "8. An incomplete fresh task namespace cannot be called a closed task migration and cannot support partial-cache inference.",
            "9. Source reports must retain the evidence anchors used by this classification; drift aborts generation.",
            "",
            "## Reproduction",
            "",
            "```bash",
            "python -m analysis.mechanism_v2.endpoint_coverage_audit",
            "python -m analysis.mechanism_v2.endpoint_coverage_audit --check",
            "```",
            "",
            "Generation is deterministic: no timestamp, network call, model call, or random sampling is used. Source-report and arm-registry-source SHA-256 values are recorded in the JSON matrix.",
            "",
        ]
    )
    return "\n".join(lines)


def build_artifacts(root: Path = ROOT) -> dict[str, str]:
    payload = build_payload(root)
    return {
        "endpoint_coverage_matrix.json": render_json(payload),
        "REPORT.md": render_report(payload),
    }


def _check_artifacts(output_dir: Path, artifacts: Mapping[str, str]) -> None:
    for name, expected in artifacts.items():
        path = output_dir / name
        if not path.is_file():
            raise AssertionError(f"missing generated artifact: {path}")
        actual = path.read_text(encoding="utf-8")
        if actual != expected:
            raise AssertionError(f"stale generated artifact: {path}")


def _write_artifacts(output_dir: Path, artifacts: Mapping[str, str]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, text in artifacts.items():
        path = output_dir / name
        path.write_text(text, encoding="utf-8")


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail if checked-in artifacts differ from deterministic regeneration",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="artifact directory (default: %(default)s)",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    artifacts = build_artifacts(ROOT)
    if args.check:
        _check_artifacts(args.output_dir, artifacts)
    else:
        _write_artifacts(args.output_dir, artifacts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
