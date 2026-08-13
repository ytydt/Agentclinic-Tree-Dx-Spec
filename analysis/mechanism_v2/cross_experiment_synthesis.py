#!/usr/bin/env python3
"""Build the auditable cross-experiment mechanism-v2 synthesis bundle.

The numerical and mechanistic statements below are a deliberately curated
root-level ledger.  They are not re-estimated by scraping prose: every entry
points to its owning experiment report, and an exact anchor is checked before
the ledger is emitted.  This makes transcription drift fail closed while
keeping the final scientific interpretation under the root auditor's control.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import math
import re
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]
if __package__ in {None, ""}:
    sys.path.insert(0, str(REPO_ROOT))

from analysis.mechanism_v2 import endpoint_coverage_audit  # noqa: E402


DEFAULT_OUT = REPO_ROOT / "analysis/mechanism_v2/results/CROSS_EXPERIMENT_ROOT_SYNTHESIS"
REGISTER = "analysis/mechanism_v2/EXPERIMENT_REGISTER.md"
FINAL_REPORT = "analysis/mechanism_v2/CROSS_EXPERIMENT_ROOT_CRITICAL_SYNTHESIS.md"
CLAIM_LEDGER = "analysis/mechanism_v2/claim_ledger.jsonl"
E2_UNIFIED = "analysis/mechanism_v2/results/E2_blinded_clinical_adjudication/unified_800"
MIGRATION_ROOT = "analysis/mechanism_v2/results/ALL_ARM_ENDPOINT_MIGRATION"

GRADE_DEFINITIONS = {
    "A": "pre-frozen paired or factorial intervention with case-level ITA accounting",
    "B": "frozen replay, full-census adjudication, or structured observational reconstruction",
    "C": "retrospective/exploratory evidence without a clean causal contrast",
    "D": "root-owned manual case or relation audit supporting mechanism attribution",
}


EVIDENCE: tuple[dict[str, Any], ...] = (
    {
        "experiment": "E1",
        "stage": "runtime_input",
        "design": "paired 2x2 input visibility-by-organization micro-pipeline factorial",
        "population": {"cases": 200, "DA": 100, "MCR": 100},
        "grade": "A+D",
        "finding": (
            "Visible answer options enter candidate generation, supply benchmark surfaces, "
            "and collapse search; the migrated model-panel endpoint confirms very large apparent "
            "complete/C∪P gains that must be interpreted as contamination, while clinical-block "
            "organization materially moderates the effect."
        ),
        "effect": {
            "hierarchical_fixed_options_minus_clean_safe_exact_top1_pp": 41.0,
            "flat_fixed_options_minus_clean_safe_exact_top1_pp": 40.2,
            "hierarchical_clean_reorder_champion_flips": "133/180",
            "flat_clean_reorder_champion_flips": "165/199",
            "model_panel_hierarchical_fixed_options_minus_clean_clinical_complete_pp": 42.0,
            "model_panel_flat_fixed_options_minus_clean_clinical_complete_pp": 39.0,
            "model_panel_hierarchical_option_shuffle_clinical_complete_pp": -11.0,
            "model_panel_hierarchical_option_shuffle_clinical_complete_holm_q": 0.01824613098563288,
            "model_panel_hierarchical_option_shuffle_clinical_complete_common_served_pp": -7.18562874251497,
            "model_panel_hierarchical_option_shuffle_clinical_complete_common_served_holm_q": 0.2304506916552782,
        },
        "causal_scope": "input-sensitive one-call stages, not the full legacy APHHM runtime",
        "refutes": ["answer options are a harmless display layer", "equal aggregate scores imply equal trajectories"],
        "report": "analysis/mechanism_v2/results/E1_input_factorial/REPORT.md",
        "anchors": ["+41.0pp", "+40.2pp", "133/180 H champions"],
    },
    {
        "experiment": "E2",
        "stage": "endpoint_and_identifiability",
        "design": "method-blind full-800 root census followed by a canonical complete/compatible-partial/union replay of all frozen outputs",
        "population": {"cases": 800, "DA": 400, "MCR": 400, "case_arm_rows": 7200},
        "grade": "B+D",
        "finding": (
            "Safe-exact is a deterministic lower bound, legacy-chain is a historical diagnostic, clinical-complete is the "
            "primary ability endpoint, compatible-partial is a scope-loss state, its union with complete is secondary coverage, "
            "and task is a family-specific interface. Only 455/800 "
            "references are uniquely identifiable. No overall clinical-complete contrast survives its coherent Holm family; "
            "the MCR Collapse3c-versus-IMPC contrast does, but its DA-versus-MCR interaction is not multiplicity-confirmed."
        ),
        "effect": {
            "unique_full_reference": "455/800",
            "family_only_cases": 139,
            "unsupported_specificity_cases": 131,
            "insufficient_information_cases": 70,
            "multiple_complete_answers_cases": 5,
            "safe_exact_range_pct": "7.12-8.62",
            "legacy_chain_range_pct": "19.38-26.62",
            "clinical_complete_range_pct": "12.25-15.25",
            "compatible_partial_range_pct": "29.88-35.25",
            "family_specific_task_interface_range_pct": "40.12-46.12",
            "clinical_complete_leader": "collapse3c 122/800 (15.25%)",
            "clinical_complete_runner_up": "multistance 121/800 (15.12%)",
            "overall_coherent_holm_survivors": 0,
            "DA_coherent_holm_survivors": 0,
            "MCR_coherent_holm_survivors": 1,
            "MCR_collapse3c_minus_impc_pp": 5.50,
            "MCR_collapse3c_vs_impc_holm_q": 0.0456153274640822,
            "family_interaction_holm_q": 0.22848857557122143,
        },
        "causal_scope": "full-census measurement and frozen-output anatomy; historical arm differences are not fresh runtime effects",
        "refutes": [
            "one correctness flag measures clinical output quality",
            "legacy-chain is concept accuracy",
            "the combined DA/MCR task column is a homogeneous ability estimand",
        ],
        "report": "analysis/mechanism_v2/results/E2_blinded_clinical_adjudication/REPORT.md",
        "anchors": ["455 | 285 | 170", "7,200 个唯一 case-arm 行", "q10=.045615", "q=.228489"],
    },
    {
        "experiment": "E4",
        "stage": "fixed_pool_selection",
        "design": "five selectors on the same blinded canonical pool and evidence table",
        "population": {"cases": 400, "safe_exact_exposed": 62},
        "grade": "A+D",
        "finding": (
            "Forest-style evidence integration and pairwise comparison both outperform the weak evidence-count control "
            "on migrated model-panel clinical endpoints, but Forest no longer has a multiplicity-confirmed complete "
            "advantage over e7 and pairwise remains indistinguishable from Forest."
        ),
        "effect": {
            "forest_safe_exact_top1": "41/400",
            "e7_safe_exact_top1": "33/400",
            "forest_minus_e7_safe_exact_pp": 2.0,
            "discordance_gain_harm": "9/1",
            "mcnemar_p": 0.021484375,
            "model_panel_forest_minus_evidence_count_clinical_complete_pp": 9.5,
            "model_panel_forest_minus_evidence_count_clinical_complete_holm_q": 1.2459019476107613e-06,
            "model_panel_forest_minus_e7_clinical_complete_holm_q": 0.2314453125,
            "model_panel_pairwise_minus_forest_clinical_complete_pp": 0.0,
        },
        "causal_scope": "selector behavior on one frozen candidate/evidence state, chiefly exposed MCR cases",
        "refutes": ["generation alone explains all method differences", "evidence count or exhaustive tournament is sufficient"],
        "report": "analysis/mechanism_v2/results/E4_fixed_pool_crossover/REPORT.md",
        "anchors": ["9 safe-exact gains and one loss", "only seven DA cases are safe-exact-exposed"],
    },
    {
        "experiment": "E5",
        "stage": "candidate_set_interference",
        "design": "nine-arm candidate-membership intervention with byte-stable shared labels and order",
        "population": {"cases": 200, "common_complete": 162},
        "grade": "A+D",
        "finding": (
            "Candidate independence is false, but ITA feasibility and candidate-membership interference must be separated. "
            "Every addition arm is lower than base4 in ITA because candidate treatment and differential service are bundled; "
            "among cases served by both arms, genuine width expansion and sibling additions remain harmful, while synonyms "
            "improve C∪P and components are approximately null. Width is therefore a topology-dependent treatment, not a law."
        ),
        "effect": {
            "sibling_safe_exact_delta_pp": -10.91,
            "sibling_holm_p": 0.01472,
            "width8_safe_exact_delta_pp": -16.46,
            "width8_holm_p": 0.000114,
            "width6_to_width8_safe_exact_delta_pp": -7.93,
            "model_panel_width8_minus_base4_clinical_complete_ita_pp": -30.0,
            "model_panel_width8_minus_base4_clinical_complete_ita_holm_q": 1.7722822721107784e-13,
            "model_panel_width8_minus_base4_clinical_complete_common_served_pp": -17.682926829268293,
            "model_panel_width8_minus_base4_clinical_complete_common_served_width_family_holm_q": 7.289723725989461e-06,
            "model_panel_width8_minus_width6_clinical_complete_common_served_pp": -6.707317073170732,
            "model_panel_width8_minus_width6_clinical_complete_common_served_holm_q": 0.03468966484069824,
            "model_panel_all_nine_common_served_width4_to_width8_pp_per_added_candidate": -4.4753086419753085,
            "model_panel_all_nine_common_served_DA_width4_to_width8_pp_per_added_candidate": -2.873563218390803,
            "model_panel_all_nine_common_served_MCR_width4_to_width8_pp_per_added_candidate": -6.33333333333333,
            "model_panel_sibling_common_served_clinical_complete_pp": -11.515151515151516,
            "model_panel_synonym_common_served_clinical_complete_pp": 4.848484848484849,
            "model_panel_synonym_common_served_complete_or_partial_pp": 6.666666666666667,
            "model_panel_component_common_served_clinical_complete_pp": 0.6024096385542169,
        },
        "causal_scope": (
            "gold-exposed constructed pools; common-served estimates isolate the realised membership path only descriptively, "
            "service is post-treatment, and typed-label construction errors limit relation-specific subarms"
        ),
        "refutes": ["more candidates are monotonically safer", "removing a loser cannot change the winner among survivors"],
        "report": "analysis/mechanism_v2/results/E5_candidate_interference/REPORT.md",
        "anchors": ["−10.91pp", "−16.46pp", "Candidate-set context is itself causally active"],
    },
    {
        "experiment": "E6",
        "stage": "representation_fidelity",
        "design": "raw vignette versus quoted flat facts versus generated typed event graph",
        "population": {"cases": 300, "builder_valid": 258, "manual_graph_cases": 30},
        "grade": "A+D",
        "finding": (
            "The tested generated graph is a lossy and error-adding representation: relations are new clinical claims, "
            "not formatting. ITA puts both flat facts and graph below raw text for complete and C∪P, but common-served "
            "analysis attenuates the complete deficit below Holm significance while preserving the C∪P deficit. The "
            "robust mechanism is loss of compatible coverage plus service cost, not a confirmed complete-only coefficient."
        ),
        "effect": {
            "graph_minus_raw_proxy_complete_equivalent_sensitivity_pp": -7.63,
            "discordance_raw_only_graph_only": "24/5",
            "mcnemar_p": 0.00055,
            "graphs_with_relation_error": "25/30",
            "model_panel_graph_minus_raw_clinical_complete_ita_pp": -10.0,
            "model_panel_graph_minus_raw_clinical_complete_ita_holm_q": 0.00021999655190846346,
            "model_panel_flat_minus_raw_clinical_complete_ita_pp": -7.666666666666666,
            "model_panel_flat_minus_raw_clinical_complete_ita_holm_q": 0.015241043710051394,
            "model_panel_graph_minus_raw_clinical_complete_common_served_pp": -6.0,
            "model_panel_graph_minus_raw_clinical_complete_common_served_holm_q": 0.060221555759198964,
            "model_panel_flat_minus_raw_clinical_complete_common_served_pp": -3.21285140562249,
            "model_panel_flat_minus_raw_clinical_complete_common_served_holm_q": 0.52986179292202,
            "model_panel_graph_minus_raw_complete_or_partial_common_served_pp": -10.0,
            "model_panel_graph_minus_raw_complete_or_partial_common_served_holm_q": 0.0014092719540244047,
            "model_panel_flat_minus_raw_complete_or_partial_common_served_pp": -8.835341365461848,
            "model_panel_flat_minus_raw_complete_or_partial_common_served_holm_q": 0.014297467666326134,
        },
        "causal_scope": "the tested generative graph constructor and selector, not all structured representations",
        "refutes": ["typed graph generation is lossless", "explicit time/scope fields are reliable merely because present"],
        "report": "analysis/mechanism_v2/results/E6_representation_fidelity/REPORT.md",
        "anchors": ["下降 7.63", "25 例至少有一条关系语义错误"],
    },
    {
        "experiment": "E6x",
        "stage": "runtime_representation_control",
        "design": "remove only the flat-fact sentinel padding while freezing facts and selector contract",
        "population": {"cases": 300, "common_outputs": 255},
        "grade": "A+D",
        "finding": (
            "Whitespace-matched sentinel padding inflated prompt tokens catastrophically but did not explain the semantic quality effect; "
            "the migrated model-panel replay also finds no complete or C∪P improvement from removing it, while tiny "
            "nonclinical input changes can still send the generator to different trajectories."
        ),
        "effect": {
            "mean_input_token_reduction_pct": 64.9,
            "proxy_complete_equivalent_sensitivity_delta_pp": 1.57,
            "proxy_complete_equivalent_sensitivity_mcnemar_p": 0.481,
            "champion_flip_pct": 95.29,
            "model_panel_unpadded_minus_padded_clinical_complete_pp": 1.3333333333333333,
            "model_panel_unpadded_minus_padded_clinical_complete_holm_q": 0.5715880393981934,
            "model_panel_unpadded_minus_padded_complete_or_partial_pp": -0.6666666666666666,
        },
        "causal_scope": "tokenization and one representation perturbation; provider/time effects remain a runtime limitation",
        "refutes": ["whitespace word matching equalizes model input", "padding alone explains flat-fact quality"],
        "report": "analysis/mechanism_v2/results/E6x_unpadded_flat/REPORT.md",
        "anchors": ["64.9%", "95.29%"],
    },
    {
        "experiment": "E7a",
        "stage": "entity_identity",
        "design": "full 800-case offline replay of legacy substring versus exact frozen-synonym identity",
        "population": {"cases": 800, "unsafe_fold_cases": 299},
        "grade": "B+D",
        "finding": (
            "Substring identity is not benign deduplication: it folds non-synonyms, transfers evidence, and erases separately addressable concepts."
        ),
        "effect": {
            "unsafe_fold_cases_pct": 37.4,
            "unsafe_pairs": 1199,
            "mean_nodes_restored": 0.55,
            "exact_identity_contamination_pct": 0.0,
        },
        "causal_scope": "identity/exposure replay, not fresh selector accuracy",
        "refutes": ["substring containment is a safe equivalence relation"],
        "report": "analysis/mechanism_v2/results/E7_registry_replay/REPORT.md",
        "anchors": ["299 cases (37.4%)", "1199 rows"],
    },
    {
        "experiment": "E7b",
        "stage": "entity_identity_and_selection",
        "design": "fresh blinded selector on legacy, exact, and generic-relation counterfactual registries",
        "population": {"cases": 400, "unsafe_fold_cases": 299},
        "grade": "A+D",
        "finding": (
            "Exact identity is a safety/addressability invariant and restores reference exposure; the migrated model-panel "
            "endpoint additionally shows a complete gain with no C∪P gain, consistent with specificity repair rather than "
            "new family coverage. Generic/typed prose still adds no confirmed benefit."
        ),
        "effect": {
            "contaminated_selected_concepts_legacy_exact": "160/0",
            "unsafe_exposure_restoration_gain_loss": "11/1",
            "exposure_mcnemar_p": 0.00635,
            "safe_exact_top1_gain_loss": "8/5",
            "safe_exact_mcnemar_p": 0.58105,
            "model_panel_exact_minus_legacy_clinical_complete_pp": 3.25,
            "model_panel_exact_minus_legacy_clinical_complete_holm_q": 0.00885009765625,
            "model_panel_exact_minus_legacy_complete_or_partial_pp": -0.5,
        },
        "causal_scope": "unsafe-fold development cases under a fixed-width selector payload",
        "refutes": ["safe identity repair alone fixes ranking", "undirected non-equivalence text supplies task projection"],
        "report": "analysis/mechanism_v2/results/E7b_registry_selector/REPORT.md",
        "anchors": ["160 to 0", "11 paired restorations versus 1 loss"],
    },
    {
        "experiment": "E7c",
        "stage": "typed_relations",
        "design": "fixed exact-identity pools with LLM directional relations and bounded inheritance",
        "population": {"cases": 299, "complete_relation_typing": 290},
        "grade": "A+D",
        "finding": (
            "The realised directional graph is too inconsistent for deployment; relation wording and even irrelevant graph "
            "context act as salience perturbations, and the migrated model-panel endpoints show no confirmed clinical gain."
        ),
        "effect": {
            "directional_minus_exact_safe_exact_pp": -0.67,
            "bounded_minus_directional_safe_exact_pp": 0.0,
            "internal_direction_agreement_pct": 64.82,
            "repeat_pair_consistency_pct": 80.58,
            "model_panel_directional_minus_exact_clinical_complete_pp": -0.33444816053511706,
            "model_panel_directional_minus_exact_clinical_complete_holm_q": 1.0,
        },
        "causal_scope": "the implemented LLM relation typer, not an oracle typed ontology",
        "refutes": ["free-form directional annotation is ready for evidence inheritance"],
        "report": "analysis/mechanism_v2/results/E7c_directional_registry/REPORT.md",
        "anchors": ["64.82%", "80.58% repeat"],
    },
    {
        "experiment": "E8",
        "stage": "negative_evidence_and_time",
        "design": "hard versus time/scope soft veto plus legal-order and invalid-time perturbations",
        "population": {"cases": 220, "hard_soft_common_served": 193, "invalid_time_common_served": 125},
        "grade": "A+D",
        "finding": (
            "Atemporal absolute veto is clinically unsafe; softening it removes invalid reference vetoes but does not by itself identify a superior ranker, "
            "and migrated model-panel complete/C∪P contrasts do not confirm soft over hard. The invalid-time arm is operationally "
            "worse in ITA because of failures, which cannot be isolated as correct temporal reasoning."
        ),
        "effect": {
            "hard_reference_vetoes": 9,
            "manually_valid_hard_reference_vetoes": 0,
            "soft_minus_hard_safe_exact_top1_pp": 1.64,
            "soft_minus_hard_mcnemar_p": 0.453,
            "legal_order_flip_pct": 24.6,
            "invalid_time_flip_pct": 23.2,
            "model_panel_soft_minus_hard_clinical_complete_pp": 1.8181818181818181,
            "model_panel_soft_minus_hard_clinical_complete_holm_q": 0.775390625,
            "model_panel_invalid_minus_soft_clinical_complete_pp": -4.545454545454546,
            "model_panel_invalid_minus_soft_clinical_complete_holm_q": 0.038818359375,
            "model_panel_invalid_minus_soft_clinical_complete_common_served_pp": 0.0,
            "model_panel_invalid_minus_soft_complete_or_partial_common_served_pp": -2.4,
            "source_rows_with_valid_model_panel_top1_recovered_despite_full_response_failure": 11,
        },
        "causal_scope": "fixed pools with a generated negative ledger; builder errors are part of the treatment risk",
        "refutes": ["missing a typical finding safely excludes a diagnosis", "time fields guarantee correct temporal reasoning"],
        "report": "analysis/mechanism_v2/results/E8_temporal_veto/REPORT.md",
        "anchors": ["0 例能支持该绝对否证", "24.6%", "23.2%"],
    },
    {
        "experiment": "E9",
        "stage": "multi_view_generation",
        "design": "real views, role rotation, one balanced anchor, and exact duplicate-view placebo",
        "population": {"cases": 400, "root_audit_cases": 70},
        "grade": "A+D",
        "finding": (
            "Forest views are correlated but retain a small complete gain in the exhaustive model-panel replay; the targeted "
            "70-case root queue remains mechanism-only. Their benefit is not independent voting, and duplicate/role "
            "perturbations expose selector path dependence."
        ),
        "effect": {
            "real_minus_single_safe_exact_pp": 2.25,
            "real_minus_single_mcnemar_p": 0.0117,
            "safe_exact_real_only_root_reviewed_better_cases": "6/10",
            "targeted_root_review_true_new_capture_to_safe_exact_top1": 3,
            "semantic_cluster_observation_ratio": 0.552,
            "model_panel_real_minus_single_clinical_complete_pp": 3.25,
            "model_panel_real_minus_single_clinical_complete_holm_q": 0.013275146484375,
            "model_panel_real_minus_duplicate_clinical_complete_pp": 3.5,
            "model_panel_real_minus_duplicate_clinical_complete_holm_q": 0.01030731201171875,
        },
        "causal_scope": "joint effect of extra view content on union plus selection; role/duplicate flips are instability upper bounds",
        "refutes": ["three views are three independent votes", "duplicate evidence should raise confidence"],
        "report": "analysis/mechanism_v2/results/E9_view_independence/REPORT.md",
        "anchors": ["6/1/4 不是新规范的 clinical-complete 重编码", "cluster/observation 比为 0.552"],
    },
    {
        "experiment": "E10",
        "stage": "sequential_deliberation",
        "design": "doctor history isolated/sequential crossed with deterministic RRF/closed-pool Supervisor",
        "population": {"cases": 400, "root_audit_cases": 166},
        "grade": "A+D",
        "finding": (
            "Sequential history compresses candidate diversity dramatically and improves a frozen binary-acceptable proxy's "
            "current-sample rank conversion. The migrated model-panel replay finds no confirmed complete gain, but C∪P improves "
            "for history under RRF and Supervisor under isolated generation. The Supervisor remains a conditional coverage rescue, "
            "not the source of diversity loss."
        ),
        "effect": {
            "mean_union_isolated_sequential": "6.82/5.21",
            "pairwise_jaccard_isolated_sequential": "0.689/0.954",
            "rrf_binary_acceptable_proxy_top2_delta_pp": 4.5,
            "supervisor_binary_acceptable_proxy_top2_delta_pp": 3.25,
            "d3_new_concepts_total_sequential": 6,
            "model_panel_history_rrf_complete_or_partial_pp": 6.0,
            "model_panel_history_rrf_complete_or_partial_holm_q": 0.0015525236117355234,
            "model_panel_supervisor_isolated_complete_or_partial_pp": 4.25,
            "model_panel_supervisor_isolated_complete_or_partial_holm_q": 0.004541158676147461,
            "model_panel_clinical_complete_holm_survivors": 0,
        },
        "causal_scope": (
            "homogeneous Llama panel on development cases; Top-1 three-state clinical relations are a blinded model-panel "
            "sensitivity rather than a human-root census, while candidate-registry novelty remains unmigrated"
        ),
        "refutes": ["sequential discussion creates independent expert search", "Supervisor is the primary diversity bottleneck"],
        "report": "analysis/mechanism_v2/results/E10_mac_factorial/REPORT.md",
        "anchors": ["6.82 降到 5.21", "0.689 升到 0.954", "合计只新增 6 个概念"],
    },
    {
        "experiment": "E11",
        "stage": "retrieval_and_refinement",
        "design": "retrieval off/query-top/random/hard-negative crossed with refine off/on",
        "population": {"cases": 400, "retrieval_screen_valid": 325},
        "grade": "A+D",
        "finding": (
            "The tested retriever supplies weak topical context rather than case-specific relations; query-top context tends to flatten specificity, "
            "while the migrated model-panel replay finds no clinical-complete advantage from retrieval or refine. Refine does "
            "increase C∪P with retrieval off and under hard-negative context, indicating broad compatible coverage rather than "
            "complete-object recovery. This is not a human-root capability endpoint."
        ),
        "effect": {
            "relevant_case_specific_chunk_pct": 6.62,
            "relevant_minus_off_proxy_complete_equivalent_sensitivity_top1_pp": -2.0,
            "relevant_minus_off_holm_q": 0.27,
            "off_refine_proxy_complete_or_compatible_partial_sensitivity_delta_pp": 3.5,
            "off_refine_sensitivity_holm_q": 0.0463,
            "model_panel_relevant_minus_off_clinical_complete_pp": -1.25,
            "model_panel_relevant_minus_off_clinical_complete_holm_q": 1.0,
            "model_panel_refine_off_context_complete_or_partial_pp": 4.25,
            "model_panel_refine_off_context_complete_or_partial_holm_q": 0.00154876708984375,
            "model_panel_refine_hard_negative_complete_or_partial_pp": 3.5,
            "model_panel_refine_hard_negative_complete_or_partial_holm_q": 0.015460968017578125,
        },
        "causal_scope": (
            "the current lexical bundle contract, not ideal typed RAG; Top-1 complete/partial is an exhaustive blinded "
            "model-panel sensitivity and cannot support the human-root capability ranking"
        ),
        "refutes": ["query-top text is clinically relevant evidence", "a generic second-pass refine is a safe fallback"],
        "report": "analysis/mechanism_v2/results/E11_b07_factorial/REPORT.md",
        "anchors": ["6.62%", "`q=.2700`", "rare-but-plausible Top-2"],
    },
    {
        "experiment": "E12",
        "stage": "e7_pipeline_factorial",
        "design": "raw/S1/graph by k5/k10 by first/pointwise/pairwise plus frozen depth path",
        "population": {"cases": 300, "root_audit_cases": 154},
        "grade": "A+D",
        "finding": (
            "On frozen candidate pools, the migrated model-panel replay withdraws the two old proxy clinical-complete survivors: "
            "none survives Holm39 for complete. Raw pairwise retains C∪P gains over first at k5/k10 and over S1 at k10. "
            "Six first arms are structurally identical controls; width and depth remain unconfirmed."
        ),
        "effect": {
            "raw_k5_pairwise_minus_first_proxy_complete_equivalent_sensitivity_pp": 4.67,
            "raw_k5_pairwise_holm_q": 0.04987,
            "raw_k10_pairwise_minus_first_proxy_complete_equivalent_sensitivity_pp": 5.0,
            "raw_k10_pairwise_holm_q": 0.02842,
            "safe_exact_exposure_gain_k5_to_k10": 2,
            "model_panel_factorial39_clinical_complete_holm_survivors": 0,
            "model_panel_raw_k5_pairwise_minus_first_complete_or_partial_pp": 9.666666666666666,
            "model_panel_raw_k5_pairwise_minus_first_complete_or_partial_holm_q": 0.0192996720020261,
            "model_panel_raw_k10_pairwise_minus_first_complete_or_partial_pp": 12.333333333333334,
            "model_panel_raw_k10_pairwise_minus_first_complete_or_partial_holm_q": 0.00017453376913001406,
            "model_panel_raw_minus_s1_k10_pairwise_complete_or_partial_pp": 8.666666666666668,
            "model_panel_raw_minus_s1_k10_pairwise_complete_or_partial_holm_q": 0.011622832060936616,
        },
        "causal_scope": "frozen historical e7 candidate pools; raw includes occasional author diagnostic assertions",
        "refutes": ["historical candidate order is a sufficient selector", "S1 or generated graph is a safe sole representation", "extra selector samples measure call-depth value"],
        "report": "analysis/mechanism_v2/results/E12_e7_factorial/REPORT.md",
        "anchors": ["Holm `q=.04987`", "`q=.02842`", "每 750 个新增候选"],
    },
    {
        "experiment": "E14x",
        "stage": "adaptive_call_gate",
        "design": "retrospective safe-exact-gate funnel with exhaustive root review of triggered champion flips",
        "population": {"cases": 300, "triggered": 90, "triggered_champion_flips": 34},
        "grade": "C+D",
        "finding": (
            "The realised unexplained-span/low-margin fourth-call gate adds many surviving entities but no safe-exact reference discovery; "
            "the old 6-repair/15-harm result is an ordinal relative-closeness audit rather than a canonical binary endpoint. "
            "The exhaustive model-panel replay is near-null overall and suggests exploratory triggered MCR C∪P coverage gain, "
            "while historical upstream states remain nonexchangeable."
        ),
        "effect": {
            "new_entities": 135,
            "safe_exact_reference_discoveries": 0,
            "root_repairs_harms_neutral": "6/15/13",
            "identical_upstream_pairs": "0/300",
            "model_panel_adaptive_minus_lite_clinical_complete_pp": 0.3333333333333333,
            "model_panel_adaptive_minus_lite_clinical_complete_mcnemar_p": 1.0,
            "model_panel_adaptive_minus_lite_complete_or_partial_pp": 1.3333333333333333,
            "model_panel_triggered90_complete_or_partial_gain_loss": "9/3",
            "model_panel_triggered90_complete_or_partial_mcnemar_p": 0.14599609375,
            "model_panel_triggered_MCR65_complete_or_partial_gain_loss": "6/0",
            "model_panel_triggered_MCR65_complete_or_partial_unadjusted_p": 0.03125,
        },
        "causal_scope": "deployment decision on the current gate; no causal coefficient for an ideal relation-aware Call-4",
        "refutes": ["unexplained span count is an adequate call target", "more surviving novelty implies utility"],
        "report": "analysis/mechanism_v2/results/E14x_runtime_gate/REPORT.md",
        "anchors": ["135 个新实体没有一个 `safe-exact` 命中", "6 个观察到的临床 repair、15 个 harm、13 个 neutral"],
    },
    {
        "experiment": "RCR3",
        "stage": "end_to_end_relation_system",
        "design": "pre-frozen Lite3, relation-preserving RCR3, and true-third-generator Compact4 arms",
        "population": {"cases": 300, "root_relation_cases": 109, "root_relation_judgments": 375},
        "grade": "A+D",
        "finding": (
            "The default RCR-3 implementation fails its fidelity, exposure, reliability, and conversion criteria; "
            "safe identity survives, but its ITA C∪P deficits versus Lite and Compact4's deficits are dominated by service/schema "
            "reliability. The corresponding common-served C∪P differences are near zero. No complete contrast survives Holm, "
            "so deployment rejection is an end-to-end interface/fidelity decision rather than proof of inferior successful trajectories."
        ),
        "effect": {
            "proxy_complete_equivalent_sensitivity_top1_lite_rcr_compact4": "29/20/18",
            "proxy_complete_equivalent_sensitivity_top2_lite_rcr_compact4": "42/31/26",
            "rcr_minus_lite_safe_exact_frontier_exposure_pp": -7.0,
            "frontier_exposure_holm_q": 0.000311,
            "material_span_drops": "at least 69/119",
            "wrong_or_unsupported_relations": "20/60",
            "root_reviewed_full_equivalence_among_self_reported_complete": "9/66",
            "model_panel_lite_rcr_compact4_clinical_complete_counts": "22/13/13 of 300",
            "model_panel_rcr_minus_lite_complete_or_partial_ita_pp": -7.0,
            "model_panel_rcr_minus_lite_complete_or_partial_ita_holm_q": 0.0314181102338461,
            "model_panel_compact4_minus_rcr_complete_or_partial_ita_pp": -14.0,
            "model_panel_compact4_minus_rcr_complete_or_partial_ita_holm_q": 0.0001310074158496009,
            "model_panel_third_generator_minus_lite_complete_or_partial_ita_pp": -21.0,
            "model_panel_third_generator_minus_lite_complete_or_partial_ita_holm_q": 7.367231650043769e-13,
            "model_panel_rcr_minus_lite_complete_or_partial_common_served_pp": -0.3861003861003861,
            "model_panel_compact4_minus_rcr_complete_or_partial_common_served_pp": -1.3245033112582782,
            "model_panel_third_generator_minus_lite_complete_or_partial_common_served_pp": -1.7241379310344827,
        },
        "causal_scope": "the realised generated skeleton/typed-candidate/frontier implementation on a development relation challenge set",
        "refutes": ["current RCR-3 is the default three-call replacement", "generated relation fields and self-reported completeness are trustworthy"],
        "report": "analysis/mechanism_v2/results/RCR3_relation_preserving/REPORT.md",
        "anchors": ["119 个 exact-span drop", "至少 69 个", "20/60", "9/66"],
    },
)


MECHANISM_CHAIN: tuple[dict[str, Any], ...] = (
    {
        "order": 1,
        "stage": "runtime input and benchmark object",
        "failure_modes": ["answer-option label supply", "source text under-identifiability", "format-driven trajectory replacement"],
        "evidence": ["E1", "E2"],
        "safe_contract": "clean vignette, input hash, option-visibility flag, and separate identifiability audit",
    },
    {
        "order": 2,
        "stage": "evidence representation",
        "failure_modes": ["decisive relation deletion", "generated polarity/time/causal claims", "token-control confounding"],
        "evidence": ["E6", "E6x", "E12", "RCR3"],
        "safe_contract": "raw text remains recoverable; every derived node and edge binds to validated spans and may be quarantined",
    },
    {
        "order": 3,
        "stage": "candidate proposal and view diversity",
        "failure_modes": ["correlated pseudo-views", "history echo", "low-yield width fill", "manifestation-as-diagnosis"],
        "evidence": ["E9", "E10", "E12", "E14x"],
        "safe_contract": "independent proposal payloads, typed requested object, provenance, unique evidence, and no vote credit for repetition",
    },
    {
        "order": 4,
        "stage": "identity and relation registry",
        "failure_modes": ["substring overmerge", "wrong relation direction", "unsafe evidence inheritance", "composite fragmentation"],
        "evidence": ["E7a", "E7b", "E7c", "RCR3"],
        "safe_contract": "merge exact/frozen synonyms only; keep parent, sibling, component, etiology, manifestation, and subtype directional",
    },
    {
        "order": 5,
        "stage": "decision exposure and frontier",
        "failure_modes": ["fixed-width undercoverage", "sibling interference", "shared-candidate reordering", "rare-candidate deletion"],
        "evidence": ["E4", "E5", "E7b", "E12", "RCR3"],
        "safe_contract": "small non-dominated pool chosen by unique discriminative evidence, with residual coverage and reversible deletion",
    },
    {
        "order": 6,
        "stage": "evidence weighting, veto, and retrieval",
        "failure_modes": ["atemporal absolute veto", "topic-count voting", "generic RAG dilution", "common-disease anchoring"],
        "evidence": ["E8", "E9", "E11", "RCR3"],
        "safe_contract": "time/scope-aware soft negatives, typed retrieval admission, evidence specificity, and one vote per proposition",
    },
    {
        "order": 7,
        "stage": "comparison and convergence",
        "failure_modes": ["historical-first shortcut", "consensus compression", "overcorrection", "self-reported completeness"],
        "evidence": ["E4", "E10", "E12", "RCR3"],
        "safe_contract": "one frozen-pool comparator with candidate-unique evidence, strongest counterexample, minority coverage, and schema checks",
    },
    {
        "order": 8,
        "stage": "diagnostic object and task projection",
        "failure_modes": ["parent/component credited as complete", "manifestation substituted for etiology", "mapper rescue/harm", "reference over-specificity"],
        "evidence": ["E2", "E7b", "E10", "E11", "RCR3"],
        "safe_contract": (
            "report safe-exact, legacy-chain, clinical-complete, partial, family-specific task, requested-object relation, "
            "and reference identifiability separately; clinical-complete is the primary ability endpoint"
        ),
    },
)


BASELINE_PROFILES: tuple[dict[str, Any], ...] = (
    {
        "system": "legacy APHHM",
        "strength": "historically preserves some low-prior candidates through a large search state",
        "weakness": "option-contaminated legacy input and repeated irreversible state writes prevent a clean architecture attribution",
        "best_supported_use": "internal historical anatomy only; do not use its published comparison as clean evidence",
        "evidence": ["E1", "E2"],
        "caveat": "E1 is an input-stage micro-pipeline, not a full APHHM rerun",
    },
    {
        "system": "Collapse3c",
        "strength": "highest full-800 clinical-complete rate (122/800, 15.25%); retains causal, anatomical, temporal, stage, and composite qualifiers",
        "weakness": "specificity retention is offset by generation misses and catastrophic substitutions; no overall complete contrast is multiplicity-confirmed",
        "best_supported_use": "specificity/composite-retention reference implementation",
        "evidence": ["E2"],
        "caveat": "MCR favors Collapse3c over IMPC within its coherent family, but the DA-MCR interaction is not multiplicity-confirmed and no universal winner follows",
    },
    {
        "system": "MultiStance",
        "strength": "second-highest full-800 clinical-complete rate (121/800, 15.12%) and the highest safe-exact lower bound (8.62%)",
        "weakness": "its 21 complete gains over Collapse3c are offset by 22 losses; wider correlated competition has essentially zero net complete effect",
        "best_supported_use": "proposal diversity source, not a default final selector",
        "evidence": ["E2", "E5"],
        "caveat": "profile is frozen-output anatomy, not a fresh head-to-head intervention",
    },
    {
        "system": "Lite",
        "strength": "simple, reliable two-proposal plus comparator path; preserves broader frontier exposure and beats current RCR-3",
        "weakness": "full-800 clinical-complete is 106/800 (13.25%), below Collapse3c, and many outputs remain parent/component partials",
        "best_supported_use": "current three-call default control",
        "evidence": ["E2", "RCR3"],
        "caveat": "not demonstrated universally superior; chosen because the proposed replacement failed",
    },
    {
        "system": "Forest",
        "strength": "best fixed-pool evidence integration in E4, useful residual view capture, and the highest complete-or-compatible-partial coverage in E2 (48.25%)",
        "weakness": "its high legacy-chain rate (26.62%) does not imply clinical completeness (13.38%); stable-parent preference, repeated views, and unsafe substring identity compress scope",
        "best_supported_use": "evidence-integration comparator pattern after exact identity repair",
        "evidence": ["E2", "E4", "E7a", "E7b", "E9"],
        "caveat": "fixed-pool selector advantage is not a complete Forest architecture win",
    },
    {
        "system": "IMPC",
        "strength": "broad stable family recognition and 19 object rescues relative to Collapse3c in the full-800 transition audit",
        "weakness": "legacy-chain is 26.50% but clinical-complete only 12.25%; 32 catastrophic substitutions and 17 scope compressions outweigh those rescues",
        "best_supported_use": "canonical-family proposal signal, not full-object endpoint leader",
        "evidence": ["E2"],
        "caveat": "Collapse3c-to-IMPC is -3.00pp overall (q=.070843) and -5.50pp in MCR (q=.045615); the family interaction is not confirmed (q=.228489)",
    },
    {
        "system": "e7",
        "strength": "occasionally recovers rare specific entities; raw fixed-pool comparison can improve its historical first-candidate result",
        "weakness": "S1 deletes decisive relations, safe width has low marginal capture, and extra selector samples are not identifiable depth gains",
        "best_supported_use": "retain proposal coverage and one explicit comparator; retire S1 as sole source",
        "evidence": ["E2", "E6", "E12"],
        "caveat": "E7 complete advantage over v0 is a mechanism signal, not multiplicity-adjusted confirmation",
    },
    {
        "system": "v0",
        "strength": "small/simple state offers a useful minimal baseline",
        "weakness": "clinical-complete is 12.88% and task 40.12%; e7 loses 21 complete cases but rescues only 11 when replaced by v0",
        "best_supported_use": "historical lower-complexity comparator",
        "evidence": ["E2"],
        "caveat": "full-census historical outputs remain development data; v0 is not the lowest arm on every endpoint",
    },
    {
        "system": "B06",
        "strength": "sequential history converts already-exposed candidates; E2 shows 32 complete rescues versus B07 and E10 isolates rank propagation",
        "weakness": "B07 simultaneously rescues 28 cases, while history nearly eliminates D3 novelty and can erase rare correct minority opinions",
        "best_supported_use": "rank-propagation mechanism, not an independent multi-expert panel",
        "evidence": ["E2", "E10"],
        "caveat": "current-sample ranking gain and long-tail capture harm coexist",
    },
    {
        "system": "B07",
        "strength": "highest partial rate (35.25%) and frequent soft landing in a compatible disease family",
        "weakness": "clinical-complete is only 12.62%; current lexical retrieval is weakly relevant and generic refine may delete rare candidates",
        "best_supported_use": "no-retrieval draft plus typed, gated retrieval research control",
        "evidence": ["E2", "E11"],
        "caveat": "E11 tests the realised TF-IDF bundle, not ideal RAG",
    },
    {
        "system": "RCR-3",
        "strength": "safe-exact identity, explicit typed composite proposals, original-span intent, and a testable three-stage contract",
        "weakness": "span drops, relation errors, schema failures, fixed frontier losses, requested-object leakage, and severe self-calibration error",
        "best_supported_use": "falsified research prototype; mine validated components only",
        "evidence": ["E6", "E7c", "E8", "E12", "RCR3"],
        "caveat": "failure of this generated implementation is not failure of all constrained relational systems",
    },
    {
        "system": "Compact4 true third generator",
        "strength": "tests whether a genuine additional independent subtype view adds value beyond Lite",
        "weakness": "schema/view failures dominate ITA and common-success performance is near Lite rather than better",
        "best_supported_use": "negative control against call-count expansion",
        "evidence": ["RCR3"],
        "caveat": "its ITA loss is largely reliability-mediated",
    },
)


TRAJECTORY_MOTIFS: tuple[dict[str, Any], ...] = (
    {
        "case": "MCR_seq200b/320",
        "reference": "May-Thurner syndrome",
        "chain": [
            "E2 full-800 replay shows B07 and e7 complete, while B06 regresses to the downstream DVT manifestation",
            "E12 raw/graph preserve the iliac artery-on-vein compression and beat S1's generic DVT",
            "RCR-3 span alignment drops the decisive CT relation",
            "the damaged support score removes May-Thurner from the frontier",
            "the selector then returns the manifestation DVT",
        ],
        "mechanism": "representation loss -> exposure loss -> requested-object regression",
        "evidence": ["E2", "E12", "RCR3"],
    },
    {
        "case": "MCR_seq200b/345",
        "reference": "HHRH",
        "chain": [
            "E8 hard veto wrongly excludes HHRH; soft policy rescues it but row order can undo the gain",
            "E9's mechanism view supplies the decisive FGF23-independent relation and creates a true capture gain",
            "E10 sequential D2 discovers HHRH and Supervisor converts it while RRF remains anchored",
            "E11 query-top retrieval first flattens to generic hypophosphatemic rickets, then refine restores HHRH",
        ],
        "mechanism": "a correct rare subtype is reachable by several modules, but conversion depends on relation specificity and ordering",
        "evidence": ["E8", "E9", "E10", "E11"],
    },
    {
        "case": "MCR_seq200b/326",
        "reference": "Brucellosis",
        "chain": [
            "E7b generic non-equivalence graph shifts exact Brucellosis to its spinal complication",
            "E9 mechanism view adds sheep exposure and restores the systemic etiology",
            "E10 RRF can retain Brucellosis while Supervisor sometimes prefers the manifestation",
            "E11 relevant refine again reverses etiology toward spinal epidural abscess",
        ],
        "mechanism": "etiology-versus-manifestation task projection, not mere synonymy",
        "evidence": ["E7b", "E9", "E10", "E11"],
    },
    {
        "case": "MCR_v2_seq100/208",
        "reference": "Takotsubo syndrome",
        "chain": [
            "E12 raw retains the apical/mid akinesia, basal hyperkinesia, and author suspicion that S1 removes",
            "RCR-3 keeps a mismatched mid-ventricular subtype but drops the generic core from the frontier",
            "the final answer becomes more specific in form but clinically less faithful",
        ],
        "mechanism": "specificity without relation fidelity creates a false refinement",
        "evidence": ["E12", "RCR3"],
    },
    {
        "case": "MCR_seq200b/458",
        "reference": "LAM",
        "chain": [
            "E6x removal of nonclinical padding flips BHD to LAM",
            "E9 real and duplicate-view context can reinforce LAM over BHD",
            "E12 raw pairwise overcorrects a correct first LAM candidate back to BHD",
        ],
        "mechanism": "the candidate is exposed throughout; representation-path and comparator instability dominate",
        "evidence": ["E6x", "E9", "E12"],
    },
    {
        "case": "MCR_v1_seq100/74",
        "reference": "CPVT",
        "chain": [
            "E6x padding perturbation can move CPVT to Brugada",
            "E10 sequential rank propagation can rescue CPVT",
            "E12 S1 invents prolonged QT and width expansion adds channelopathy siblings that displace CPVT",
        ],
        "mechanism": "summary contradiction plus sibling interference overwhelms the defining stress-trigger relation",
        "evidence": ["E6x", "E10", "E12"],
    },
    {
        "case": "MCR_v2_seq100/173",
        "reference": "chronic subdural hematoma",
        "chain": [
            "E8's negative-event builder reverses a positive CT into an absence and manufactures a veto",
            "E10 isolated D3 can recover chronicity, while sequential history erases it",
        ],
        "mechanism": "polarity construction error and history echo converge on the same lost object",
        "evidence": ["E8", "E10"],
    },
    {
        "case": "MCR_seq200b/480",
        "reference": "bulbar myasthenia gravis",
        "chain": [
            "E8 soft veto removes an invalid exclusion but the selector remains anchored on TIA",
            "E11 every injected bundle moves farther toward common vascular/migraine/demyelinating explanations",
            "E12 wider exposure alone does not guarantee conversion",
        ],
        "mechanism": "removing one bad veto is necessary but cannot repair omitted discriminators or common-disease anchoring",
        "evidence": ["E8", "E11", "E12"],
    },
    {
        "case": "DA_d2_heldout200b/729",
        "reference": "acute myocardial infarction with left-ventricular free-wall rupture",
        "chain": [
            "E2 full-800 root replay scores Collapse3c's MI-with-rupture as complete",
            "Forest retains only myocardial infarction and becomes partial despite contrast leaking from myocardium into the pericardium",
            "a task mapper may still select the intended option, so task success would conceal the lost complication object",
        ],
        "mechanism": "stable-parent preference -> scope compression -> projection can conceal the loss",
        "evidence": ["E2"],
    },
    {
        "case": "MCR_seq200b/292",
        "reference": "anaplastic large-cell lymphoma",
        "chain": [
            "Collapse3c preserves ALCL as complete in the full-800 replay",
            "Forest substitutes Hodgkin lymphoma despite CD30 positivity with CD15 negativity and the full morphology/IHC pattern",
            "the transition is conflicting subtype/entity, not a harmless alias or broader parent",
        ],
        "mechanism": "salient morphologic mimic overwhelms discriminative immunophenotype",
        "evidence": ["E2"],
    },
    {
        "case": "MCR_seq200b/395",
        "reference": "Kummell disease",
        "chain": [
            "Collapse3c and v0 retain the named syndrome supported by delayed collapse and an intravertebral vacuum cleft",
            "MultiStance substitutes unsupported steroid-induced osteoporosis",
            "e7 stops at the compatible but incomplete parent vertebral osteonecrosis",
        ],
        "mechanism": "weak exposure narrative can cause catastrophic substitution, while conservative abstraction causes scope compression",
        "evidence": ["E2"],
    },
    {
        "case": "DA_d2_heldout200b/628",
        "reference": "peri-infarction pericarditis",
        "chain": [
            "B06 preserves acute MI followed by acute pericarditis as a complete temporal-causal object",
            "e7 composes myocardium plus pericardium into myopericarditis",
            "the latter reverses causality because inflammation follows an angiographically proven infarct",
        ],
        "mechanism": "component co-occurrence without temporal direction creates a false composite",
        "evidence": ["E2", "E12"],
    },
    {
        "case": "MCR_v2_seq100/134",
        "reference": "malakoplakia",
        "chain": [
            "Collapse3c returns the partial morphologic family gastrointestinal histiocytosis",
            "IMPC uses Michaelis-Gutmann bodies with von Kossa/PAS positivity to recover malakoplakia",
            "the same arm nevertheless has more catastrophic substitutions than object rescues across the full census",
        ],
        "mechanism": "a genuine pathology-specific rescue does not imply a monotone system-level selector advantage",
        "evidence": ["E2"],
    },
)


CLOSURE_ITEMS: tuple[dict[str, Any], ...] = (
    {"item": "E0 runtime/payload/cost ledger", "status": "implemented", "artifacts": ["runtime_contract.py", "online_runner.py"]},
    {"item": "E1 input contamination factorial", "status": "complete", "artifacts": ["E1"]},
    {"item": "E2 completeness and identifiability adjudication", "status": "complete", "artifacts": ["E2"]},
    {"item": "E3 claim ledger and frozen dependencies", "status": "implemented", "artifacts": ["claim_ledger.jsonl"]},
    {"item": "E4 fixed-pool selector crossover", "status": "complete", "artifacts": ["E4"]},
    {"item": "E5 candidate interference/width", "status": "complete", "artifacts": ["E5"]},
    {"item": "E6 representation fidelity", "status": "complete", "artifacts": ["E6"]},
    {"item": "E7 safe identity and typed relation registry", "status": "complete", "artifacts": ["E7a", "E7b", "E7c"]},
    {"item": "E8 temporal/scope veto", "status": "complete", "artifacts": ["E8"]},
    {"item": "E9 view independence", "status": "complete", "artifacts": ["E9"]},
    {"item": "E10 B06 history x aggregation", "status": "complete", "artifacts": ["E10"]},
    {"item": "E11 B07 retrieval x refine", "status": "complete", "artifacts": ["E11"]},
    {"item": "E12 e7 representation x width x comparator/depth", "status": "complete", "artifacts": ["E12"]},
    {
        "item": "E13 multi-run latent-error programme",
        "status": "excluded_by_request",
        "reason": "repeat/provider-normalisation programme whose scientific purpose is variance reduction",
    },
    {
        "item": "E14 formal router after E13",
        "status": "blocked_by_excluded_prerequisite",
        "reason": "the source proposal requires E13 latent multi-run labels; the realised deployable gate was instead tested and disabled in E14x",
        "artifacts": ["E14x"],
    },
    {"item": "RCR-3 and clean Compact comparison", "status": "complete", "artifacts": ["RCR3"]},
    {
        "item": "new confirmation cohort",
        "status": "excluded_by_request",
        "reason": "confirmation-set expansion was explicitly excluded",
    },
    {
        "item": "provider/retry standardisation arms",
        "status": "excluded_by_request",
        "reason": "technical variance-only arms were explicitly excluded; provenance remains logged",
    },
    {"item": "E6x tokenizer padding falsifier", "status": "complete_new_gap", "artifacts": ["E6x"]},
    {"item": "E7c direction/inheritance fidelity falsifier", "status": "complete_new_gap", "artifacts": ["E7c"]},
    {"item": "E14x realised runtime gate utility audit", "status": "complete_new_gap", "artifacts": ["E14x"]},
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(dict(row), ensure_ascii=False, sort_keys=True) + "\n")
    temporary.replace(path)


def read_json(path: Path) -> Any:
    if not path.is_file():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def build_endpoint_migration_snapshot(repo_root: Path) -> dict[str, Any]:
    """Fail closed on the final 79-arm migration and its sensitivity replay."""

    root = repo_root / MIGRATION_ROOT
    final = read_json(root / "final/summary.json")
    panel = read_json(root / "panel/summary.json")
    task = read_json(root / "task_evaluator/summary.json")
    sensitivity = read_json(root / "sensitivity/summary.json")
    calibration = read_json(root / "sensitivity/panel_aggregate_calibration.json")
    agreement = read_json(root / "sensitivity/novel_reviewer_agreement.json")
    legacy = read_json(root / "sensitivity/legacy_clinical_calibration.json")
    contrasts = read_json(root / "final/paired_contrasts.json")["records"]
    common_served = read_json(root / "sensitivity/common_served_paired_contrasts.json")["records"]
    e5_split = read_json(root / "sensitivity/e5_family_split.json")["records"]

    expected_final = {
        "n_arms": 79,
        "n_intention_rows": 24076,
        "n_served_rows": 23046,
        "n_clinical_relations": 5351,
        "n_task_payloads": 5839,
        "n_task_payloads_successful": 5839,
        "n_task_payloads_not_evaluable": 0,
        "task_census_status": "complete_fresh_replay",
    }
    drift = {
        key: {"expected": value, "observed": final.get(key)}
        for key, value in expected_final.items()
        if final.get(key) != value
    }
    if drift:
        raise ValueError(f"79-arm endpoint-migration final summary drifted: {drift}")
    if task.get("n_unique_tasks") != 5839 or task.get("n_success") != 5839 or task.get("n_failure") != 0:
        raise ValueError("fresh task namespace is not the required 5,839/5,839 complete replay")
    if (
        panel.get("n_novel_relations") != 3407
        or panel.get("n_sentinel_relations") != 1173
        or panel.get("n_unresolved") != 152
        or sensitivity.get("n_served_rows") != 23046
    ):
        raise ValueError("panel or sensitivity census drifted from the corrected final replay")

    sentinel_per_card: dict[str, int] = {}
    with (root / "design/sentinel_truth.jsonl").open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            blind_candidate_id = str(json.loads(line)["blind_candidate_id"])
            blind_case_id = blind_candidate_id.split("-", 1)[0]
            sentinel_per_card[blind_case_id] = sentinel_per_card.get(blind_case_id, 0) + 1
    sentinel_card_distribution = {
        "zero": 628 - len(sentinel_per_card),
        "one": sum(value == 1 for value in sentinel_per_card.values()),
        "two": sum(value == 2 for value in sentinel_per_card.values()),
        "more_than_two": sum(value > 2 for value in sentinel_per_card.values()),
    }
    if sentinel_card_distribution != {"zero": 11, "one": 61, "two": 556, "more_than_two": 0}:
        raise ValueError(f"corrected sentinel allocation drifted: {sentinel_card_distribution}")

    task_survivors = [
        row
        for row in contrasts
        if row.get("endpoint") == "task" and float(row.get("holm_adjusted_p", 1.0)) < 0.05
    ]
    if len(task_survivors) != 26 or {row.get("scope") for row in task_survivors} - {"DA", "MCR"}:
        raise ValueError("task Holm survivors must be exactly 26 family-specific DA/MCR contrasts")
    if any(row.get("endpoint") == "task" and row.get("scope") == "ALL" for row in contrasts):
        raise ValueError("pooled ALL task contrast is prohibited")
    common_served_task_survivors = [
        row
        for row in common_served
        if row.get("endpoint") == "task" and float(row.get("holm_adjusted_p", 1.0)) < 0.05
    ]
    if (
        len(common_served_task_survivors) != 15
        or sum(row.get("scope") == "DA" for row in common_served_task_survivors) != 4
        or sum(row.get("scope") == "MCR" for row in common_served_task_survivors) != 11
    ):
        raise ValueError("common-served task Holm survivors must be 15: DA=4 and MCR=11")

    def unique_record(rows: Sequence[Mapping[str, Any]], **filters: Any) -> Mapping[str, Any]:
        matches = [row for row in rows if all(row.get(key) == value for key, value in filters.items())]
        if len(matches) != 1:
            raise ValueError(f"expected one migration record for {filters}, found {len(matches)}")
        return matches[0]

    e5_width8 = unique_record(
        e5_split,
        experiment_id="E5",
        label="nested_width8_vs_base4",
        estimand="common_served_case_paired",
        scope="ALL",
        endpoint="clinical_complete",
    )
    e5_sibling = unique_record(
        e5_split,
        experiment_id="E5",
        label="add_sibling5_vs_base4",
        estimand="common_served_case_paired",
        scope="ALL",
        endpoint="clinical_complete",
    )
    e5_synonym_c = unique_record(
        e5_split,
        experiment_id="E5",
        label="add_synonym5_vs_base4",
        estimand="common_served_case_paired",
        scope="ALL",
        endpoint="clinical_complete",
    )
    e5_synonym_union = unique_record(
        e5_split,
        experiment_id="E5",
        label="add_synonym5_vs_base4",
        estimand="common_served_case_paired",
        scope="ALL",
        endpoint="complete_or_compatible_partial",
    )
    e5_component = unique_record(
        e5_split,
        experiment_id="E5",
        label="add_component5_vs_base4",
        estimand="common_served_case_paired",
        scope="ALL",
        endpoint="clinical_complete",
    )

    replay_rows: list[dict[str, Any]] = []
    with (root / "final/five_endpoint_replay.jsonl").open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                replay_rows.append(json.loads(line))
    recovered_top1 = sum(bool(row.get("source_top1_recovery")) for row in replay_rows)
    if recovered_top1 != 11:
        raise ValueError(f"expected 11 formally recovered E8 Top-1 rows, found {recovered_top1}")

    e5_by_case: dict[str, dict[str, dict[str, Any]]] = {}
    for row in replay_rows:
        if row.get("experiment_id") == "E5":
            e5_by_case.setdefault(str(row["case_key"]), {})[str(row["arm_id"])] = row
    joint_rates: dict[str, dict[str, Any]] = {}
    for scope in ("ALL", "DA", "MCR"):
        joint = [
            arms
            for arms in e5_by_case.values()
            if len(arms) == 9
            and all(bool(row.get("served")) for row in arms.values())
            and (
                scope == "ALL"
                or str(next(iter(arms.values()))["benchmark_family"]) == scope
            )
        ]
        base_n = sum(bool(arms["base4"]["clinical_complete"]) for arms in joint)
        width8_n = sum(bool(arms["nested_width8"]["clinical_complete"]) for arms in joint)
        joint_rates[scope] = {
            "n": len(joint),
            "base4_complete_n": base_n,
            "width8_complete_n": width8_n,
            "width4_to_width8_delta_pp": 100.0 * (width8_n - base_n) / len(joint),
            "delta_pp_per_added_candidate": 25.0 * (width8_n - base_n) / len(joint),
        }
    if {scope: row["n"] for scope, row in joint_rates.items()} != {"ALL": 162, "DA": 87, "MCR": 75}:
        raise ValueError(f"E5 all-nine common-served census drifted: {joint_rates}")

    def common_delta(experiment: str, label: str, endpoint: str) -> dict[str, Any]:
        row = unique_record(
            common_served,
            experiment_id=experiment,
            label=label,
            scope="ALL",
            endpoint=endpoint,
        )
        return {
            "n": row["n"],
            "delta_pp": 100.0 * float(row["delta_right_minus_left"]),
            "holm_q": row["holm_adjusted_p"],
        }

    legacy_occurrence = {
        str(row["target_endpoint"]): row
        for row in legacy["records"]
        if row.get("unit") == "case_arm_occurrence" and row.get("group") == "ALL"
    }
    if set(legacy_occurrence) != {"clinical_complete", "complete_or_compatible_partial"}:
        raise ValueError("legacy-chain occurrence calibration is incomplete")

    aggregate = calibration["strata"]["all"]
    fleiss = agreement["fleiss"]
    return {
        "schema_version": "cross-synthesis-endpoint-migration-snapshot-v1",
        "coverage": {
            "arms": final["n_arms"],
            "intention_rows": final["n_intention_rows"],
            "served_rows": final["n_served_rows"],
            "unserved_rows": final["n_intention_rows"] - final["n_served_rows"],
            "unique_clinical_relations": final["n_clinical_relations"],
            "novel_relations": panel["n_novel_relations"],
            "sentinel_relations": panel["n_sentinel_relations"],
            "sentinel_card_distribution": sentinel_card_distribution,
            "unresolved_novel_relations": panel["n_unresolved"],
            "source_top1_recovered": recovered_top1,
        },
        "task": {
            "status": final["task_census_status"],
            "payloads": final["n_task_payloads"],
            "successful": final["n_task_payloads_successful"],
            "not_evaluable": final["n_task_payloads_not_evaluable"],
            "holm_survivors_total": len(task_survivors),
            "holm_survivors_DA": sum(row["scope"] == "DA" for row in task_survivors),
            "holm_survivors_MCR": sum(row["scope"] == "MCR" for row in task_survivors),
            "common_served_holm_survivors_total": len(common_served_task_survivors),
            "common_served_holm_survivors_DA": sum(
                row["scope"] == "DA" for row in common_served_task_survivors
            ),
            "common_served_holm_survivors_MCR": sum(
                row["scope"] == "MCR" for row in common_served_task_survivors
            ),
            "pooled_ALL_estimand": "prohibited",
        },
        "panel_calibration": {
            "fine_label_accuracy": aggregate["fine_label_accuracy"],
            "clinical_complete": aggregate["clinical_complete_boundary"],
            "complete_or_compatible_partial": aggregate["complete_or_compatible_partial_boundary"],
            "novel_fleiss_kappa": {
                "fine_relation": fleiss["fine_relation"]["fleiss_kappa"],
                "clinical_complete": fleiss["clinical_complete"]["fleiss_kappa"],
                "complete_or_compatible_partial": fleiss["complete_or_compatible_partial"]["fleiss_kappa"],
            },
        },
        "e5": {
            "all_nine_common_served": joint_rates,
            "pairwise_width8_minus_base4_complete_pp": 100.0 * float(e5_width8["delta_right_minus_left"]),
            "sibling_complete_pp": 100.0 * float(e5_sibling["delta_right_minus_left"]),
            "synonym_complete_pp": 100.0 * float(e5_synonym_c["delta_right_minus_left"]),
            "synonym_union_pp": 100.0 * float(e5_synonym_union["delta_right_minus_left"]),
            "component_complete_pp": 100.0 * float(e5_component["delta_right_minus_left"]),
        },
        "common_served": {
            "E6_flat_vs_raw_complete": common_delta("E6", "flat_vs_raw", "clinical_complete"),
            "E6_graph_vs_raw_complete": common_delta("E6", "graph_vs_raw", "clinical_complete"),
            "E6_flat_vs_raw_union": common_delta("E6", "flat_vs_raw", "complete_or_compatible_partial"),
            "E6_graph_vs_raw_union": common_delta("E6", "graph_vs_raw", "complete_or_compatible_partial"),
            "RCR3_rcr_vs_lite_union": common_delta("RCR3", "rcr3_vs_lite3_same_3call_budget", "complete_or_compatible_partial"),
            "RCR3_third_generator_vs_lite_union": common_delta("RCR3", "third_generator_marginal_utility", "complete_or_compatible_partial"),
        },
        "legacy_chain_occurrence_calibration": {
            endpoint: {
                "n": row["n"],
                "precision": row["precision"],
                "recall": row["sensitivity"],
            }
            for endpoint, row in legacy_occurrence.items()
        },
        "interpretation": (
            "E2 remains the only full human-root capability census; all novel 79-arm labels are "
            "calibrated blinded-model-panel sensitivities."
        ),
    }


def build_e2_full800_snapshot(repo_root: Path) -> dict[str, Any]:
    """Validate and preserve the full-census E2 measurement basis.

    The cross-experiment ledger used to transcribe an outcome-enriched subset
    analysis.  This loader deliberately fails closed unless the new
    9-arm x 800-case canonical endpoint replay is complete.  It emits the complete
    leaderboard plus the clinical paired/transition anatomy needed to audit the
    prose without treating 7,200 repeated case-arm rows as independent cases.
    """
    base = repo_root / E2_UNIFIED
    names = {
        "manifest": "manifest.json",
        "validation": "validation_summary.json",
        "leaderboard": "leaderboard.json",
        "paired_contrasts": "paired_contrasts.json",
        "identifiability": "reference_identifiability.json",
        "identifiability_effect_modification": "identifiability_effect_modification.json",
        "clinical_interactions": "clinical_interaction_inference.json",
        "relation_transitions": "relation_transition_matrices.json",
        "projection_error": "projection_error_decomposition.json",
    }
    paths = {key: base / name for key, name in names.items()}
    payload = {key: read_json(path) for key, path in paths.items()}

    def assert_close(actual: Any, expected: float, label: str) -> None:
        if not math.isclose(float(actual), expected, rel_tol=0, abs_tol=1e-15):
            raise ValueError(f"{label} drifted: {actual!r} != {expected!r}")

    def assert_interval(actual: Any, expected: Sequence[float], label: str) -> None:
        if not isinstance(actual, list) or len(actual) != len(expected):
            raise ValueError(f"{label} has invalid interval shape: {actual!r}")
        for index, (observed, target) in enumerate(zip(actual, expected)):
            assert_close(observed, target, f"{label}[{index}]")

    manifest = payload["manifest"]
    validation = payload["validation"]
    legacy_endpoints = [
        "safe_exact",
        "legacy_chain",
        "clinical_complete",
        "partial",
        "task",
    ]
    canonical_endpoints = [
        "safe_exact",
        "legacy_chain",
        "clinical_complete",
        "compatible_partial",
        "complete_or_compatible_partial",
        "task",
    ]
    arms = ["collapse3c", "multistance", "lite", "forest", "impc", "e7", "v0", "B06", "B07"]
    if manifest.get("cases_n") != 800 or manifest.get("arm_case_rows_n") != 7200:
        raise ValueError("E2 unified replay is not the required 800-case/7,200-row census")
    source_endpoints = tuple(manifest.get("endpoint_columns") or ())
    if manifest.get("arms") != arms or source_endpoints not in {
        tuple(legacy_endpoints),
        tuple(canonical_endpoints),
    }:
        raise ValueError("E2 arm order or canonical endpoint contract drifted")
    if validation.get("cases_n") != 800 or validation.get("case_arm_rows_n") != 7200:
        raise ValueError("E2 validation counts disagree with the manifest")
    overlap_n = validation.get(
        "clinical_complete_compatible_partial_overlap_n",
        validation.get("complete_partial_overlap_n"),
    )
    union_mismatch_n = validation.get("complete_or_compatible_partial_mismatch_n", 0)
    if (
        validation.get("clinical_missing_n") != 0
        or overlap_n != 0
        or union_mismatch_n != 0
    ):
        raise ValueError("E2 clinical endpoint replay has missing or overlapping labels")
    if any(validation.get("arm_counts", {}).get(arm) != 800 for arm in arms):
        raise ValueError("E2 has incomplete arm coverage")

    leaderboard = []
    for source_row in payload["leaderboard"]:
        row = dict(source_row)
        for suffix in ("n", "rate", "wilson95"):
            legacy_key = f"partial_{suffix}"
            canonical_key = f"compatible_partial_{suffix}"
            if legacy_key in row and canonical_key not in row:
                row[canonical_key] = row.pop(legacy_key)
        for suffix in ("n", "rate", "wilson95"):
            legacy_key = f"complete_or_partial_{suffix}"
            canonical_key = f"complete_or_compatible_partial_{suffix}"
            if legacy_key in row and canonical_key not in row:
                row[canonical_key] = row.pop(legacy_key)
        if row.get("complete_or_compatible_partial_n") != (
            row.get("clinical_complete_n", 0) + row.get("compatible_partial_n", 0)
        ):
            raise ValueError(
                "E2 leaderboard union does not equal clinical-complete plus compatible-partial"
            )
        leaderboard.append(row)
    expected_cells = {(scope, arm) for scope in ("ALL", "DA", "MCR") for arm in arms}
    observed_cells = {(row["scope"], row["arm"]) for row in leaderboard}
    if observed_cells != expected_cells or len(leaderboard) != 27:
        raise ValueError("E2 leaderboard does not contain exactly 9 arms x 3 scopes")
    identities = payload["identifiability"]["case_census"]
    identity_all = next(row for row in identities if row["scope"] == "ALL")
    if identity_all.get("unique_full_n") != 455 or identity_all.get("n") != 800:
        raise ValueError("E2 identifiability census drifted from 455/800 unique-full")

    complete_contrasts = [
        row for row in payload["paired_contrasts"] if row.get("endpoint") == "clinical_complete"
    ]
    if len(complete_contrasts) != 30:
        raise ValueError("E2 must contain ten clinical-complete contrasts in each of ALL/DA/MCR")
    coherent_counts = {
        scope: sum(row.get("scope") == scope for row in complete_contrasts)
        for scope in ("ALL", "DA", "MCR")
    }
    if coherent_counts != {"ALL": 10, "DA": 10, "MCR": 10}:
        raise ValueError(f"E2 coherent clinical contrast families drifted: {coherent_counts}")
    mcr_collapse_impc = next(
        row
        for row in complete_contrasts
        if row.get("scope") == "MCR"
        and row.get("left") == "collapse3c"
        and row.get("right") == "impc"
    )
    overall_collapse_impc = next(
        row
        for row in complete_contrasts
        if row.get("scope") == "ALL"
        and row.get("left") == "collapse3c"
        and row.get("right") == "impc"
    )
    assert_close(
        overall_collapse_impc.get("coherent_family_holm_p"),
        0.07084252673880494,
        "E2 overall coherent clinical Holm q",
    )
    assert_interval(
        overall_collapse_impc.get("slice_stratified_case_bootstrap_ci95"),
        [-0.05, -0.00875],
        "E2 overall Collapse3c-to-IMPC unadjusted CI",
    )
    assert_close(
        mcr_collapse_impc.get("coherent_family_holm_p"),
        0.0456153274640822,
        "E2 MCR coherent clinical Holm q",
    )
    assert_close(
        mcr_collapse_impc.get("holm_adjusted_p_within_endpoint_family"),
        0.1368459823922466,
        "E2 MCR mixed-30 clinical Holm q",
    )
    assert_interval(
        mcr_collapse_impc.get("slice_stratified_case_bootstrap_ci95"),
        [-0.0925, -0.0175],
        "E2 MCR Collapse3c-to-IMPC unadjusted CI",
    )
    if any(
        row.get("bootstrap_ci_multiplicity_status") != "unadjusted"
        for row in complete_contrasts
    ):
        raise ValueError("E2 clinical contrast percentile CI lost its unadjusted label")
    complete_effects = [
        row
        for row in payload["identifiability_effect_modification"]
        if row.get("endpoint") == "clinical_complete"
    ]
    if len(complete_effects) != 30:
        raise ValueError("E2 identifiability effect-modification table is incomplete")
    transitions = payload["relation_transitions"]
    if len(transitions) != 30:
        raise ValueError("E2 relation transition table is incomplete")
    task_calibration = [
        row
        for row in payload["projection_error"]["rows"]
        if row.get("proxy") == "task" and row.get("scope") in {"DA", "MCR"}
    ]
    if len(task_calibration) != 20:
        raise ValueError("E2 DA/MCR task calibration table (nine arms plus macro row per family) is incomplete")
    interactions = payload["clinical_interactions"]
    family_interactions = interactions.get("family_interactions", [])
    identifiability_interactions = interactions.get("identifiability_interactions", [])
    if len(family_interactions) != 10 or len(identifiability_interactions) != 30:
        raise ValueError("E2 clinical interaction inference is incomplete")
    collapse_impc_interaction = next(
        row
        for row in family_interactions
        if row.get("left") == "collapse3c" and row.get("right") == "impc"
    )
    assert_close(
        collapse_impc_interaction.get("holm_adjusted_bootstrap_p"),
        0.22848857557122143,
        "E2 family-interaction Holm q",
    )
    assert_interval(
        collapse_impc_interaction.get("unadjusted_percentile_bootstrap_ci95"),
        [-0.0925, -0.0075000000000000015],
        "E2 DA-MCR family-interaction unadjusted CI",
    )
    if "unadjusted descriptive uncertainty" not in str(interactions.get("method")):
        raise ValueError("E2 interaction CI lost its unadjusted descriptive label")
    expected_identifiability_min_q = {
        "ALL": 0.1544922753862307,
        "DA": 1.0,
        "MCR": 0.5864706764661767,
    }
    observed_identifiability_min_q = {
        scope: min(
            float(row["holm_adjusted_bootstrap_p"])
            for row in identifiability_interactions
            if row.get("scope") == scope
        )
        for scope in expected_identifiability_min_q
    }
    for scope, expected in expected_identifiability_min_q.items():
        assert_close(
            observed_identifiability_min_q[scope],
            expected,
            f"E2 {scope} identifiability-interaction minimum Holm q",
        )

    return {
        "schema_version": "cross-synthesis-e2-full800-v2",
        "coverage": {
            "cases": 800,
            "DA": 400,
            "MCR": 400,
            "arms": 9,
            "case_arm_rows": 7200,
            "candidate_reference_registry_relations": 3103,
            "old_400_registry_relations": 1673,
            "supplemental_400_registry_relations": 1430,
            "unique_case_output_clusters": 2878,
            "clinical_missing": 0,
            "inference_unit": "case; the nine arm rows per case are correlated",
        },
        "source_endpoint_schema_version": manifest.get("schema_version"),
        "endpoint_contract": {
            "columns": canonical_endpoints,
            "clinical_capability_endpoint": "clinical_complete",
            "secondary_coverage_endpoint": "complete_or_compatible_partial",
            "diagnostic_only_endpoints": ["safe_exact", "legacy_chain", "task"],
            "deprecated_source_aliases_are_normalized": True,
        },
        "endpoint_definitions": {
            "safe_exact": "exact or frozen safe synonym; deterministic conservative lower bound",
            "legacy_chain": "historical substring/resolver chain; diagnostic compatibility only",
            "clinical_complete": "root-audited complete clinical object; primary true diagnostic ability",
            "compatible_partial": "root-audited parent/component or otherwise incomplete but clinically related object",
            "complete_or_compatible_partial": "clinical-complete OR compatible-partial; secondary coverage sensitivity, not complete ability",
            "task": "DA option mapper or MCR cached calibrated semantic judge; never pool as one homogeneous estimand",
        },
        "identifiability_census": identities,
        "leaderboard": leaderboard,
        "clinical_complete_paired_contrasts": complete_contrasts,
        "clinical_complete_identifiability_effect_modification": complete_effects,
        "clinical_interaction_inference": interactions,
        "inferential_sentinels": {
            "overall_collapse3c_vs_impc_holm_q": 0.07084252673880494,
            "MCR_collapse3c_vs_impc_holm_q": 0.0456153274640822,
            "MCR_collapse3c_vs_impc_mixed30_holm_q": 0.1368459823922466,
            "family_interaction_holm_q": 0.22848857557122143,
            "identifiability_interaction_min_holm_q": expected_identifiability_min_q,
            "percentile_ci_multiplicity_status": "unadjusted",
        },
        "relation_transition_matrices": transitions,
        "task_calibration_DA_MCR": task_calibration,
        "source_files": [
            {
                "path": str(path.relative_to(repo_root)),
                "sha256": sha256(path),
            }
            for path in paths.values()
        ],
        "interpretation_guard": (
            "clinical-complete is the primary ability endpoint; safe-exact is a lower bound, legacy-chain is historical-only, "
            "compatible-partial and its union with complete are not complete ability, and combined task mixes two different benchmark interfaces"
        ),
    }


def validate_evidence(
    repo_root: Path,
    evidence: Sequence[Mapping[str, Any]],
    endpoint_coverage: Mapping[str, Any],
) -> list[dict[str, Any]]:
    if endpoint_coverage.get("schema_version") != "endpoint-coverage-audit-v2":
        raise ValueError("unsupported endpoint coverage matrix schema")
    coverage_records = list(endpoint_coverage.get("records", []))
    coverage_ids = [str(record.get("experiment_id")) for record in coverage_records]
    expected_ids = list(endpoint_coverage_audit.EXPECTED_EXPERIMENT_IDS)
    if coverage_ids != expected_ids or len(coverage_ids) != len(set(coverage_ids)):
        raise ValueError("endpoint coverage records do not match the frozen experiment registry")
    coverage_by_id = {str(record["experiment_id"]): dict(record) for record in coverage_records}
    arms_by_experiment: dict[str, list[dict[str, Any]]] = {
        experiment: [] for experiment in coverage_ids
    }
    for raw_arm in endpoint_coverage.get("arm_records", []):
        arm = dict(raw_arm)
        experiment = str(arm.get("experiment_id"))
        if experiment not in arms_by_experiment:
            raise ValueError(f"endpoint coverage contains an arm for unknown experiment: {experiment}")
        arms_by_experiment[experiment].append(arm)
    if sum(len(rows) for rows in arms_by_experiment.values()) != endpoint_coverage.get("arm_record_count"):
        raise ValueError("endpoint coverage arm count disagrees with its arm records")

    evidence_ids = [str(row.get("experiment")) for row in evidence]
    if evidence_ids != expected_ids:
        raise ValueError(
            "cross-experiment evidence must be a one-to-one ordered join with endpoint coverage: "
            f"expected {expected_ids!r}, found {evidence_ids!r}"
        )

    seen: set[str] = set()
    validated: list[dict[str, Any]] = []
    for raw in evidence:
        row = dict(raw)
        experiment = str(row["experiment"])
        if experiment in seen:
            raise ValueError(f"duplicate evidence id: {experiment}")
        seen.add(experiment)
        grade_parts = str(row["grade"]).split("+")
        if any(part not in GRADE_DEFINITIONS for part in grade_parts):
            raise ValueError(f"invalid evidence grade for {experiment}: {row['grade']}")
        report = repo_root / str(row["report"])
        if not report.is_file():
            raise FileNotFoundError(f"missing owning report for {experiment}: {report}")
        text = report.read_text(encoding="utf-8")
        missing = [anchor for anchor in row.get("anchors", []) if str(anchor) not in text]
        if missing:
            raise ValueError(f"source anchor drift for {experiment}: {missing}")
        row["source_sha256"] = sha256(report)
        coverage = coverage_by_id[experiment]
        if str(row["report"]) != str(coverage["report_path"]):
            raise ValueError(f"evidence/coverage report-path mismatch for {experiment}")
        if row["source_sha256"] != coverage["source_report_sha256"]:
            raise ValueError(f"evidence/coverage source hash mismatch for {experiment}")
        experiment_arms = arms_by_experiment[experiment]
        if len(experiment_arms) != int(coverage["arm_count"]):
            raise ValueError(f"evidence/coverage arm-count mismatch for {experiment}")
        arm_ids = [str(arm["arm_id"]) for arm in experiment_arms]
        if len(arm_ids) != len(set(arm_ids)):
            raise ValueError(f"duplicate endpoint coverage arms for {experiment}")

        # Never allow historically overloaded endpoint names to return through
        # a new effect field.  ``strict`` meant legacy-chain in E2 but
        # safe-exact elsewhere; ``Concept`` and bare ``task``/``accuracy`` are
        # likewise uninterpretable without an explicit interface or provenance
        # qualifier.  This guard applies even to the E2 census.
        reserved_name_violations: list[str] = []
        for raw_key in row.get("effect", {}):
            key = str(raw_key).lower()
            tokens = {token for token in re.split(r"[^a-z0-9]+", key) if token}
            if tokens.intersection({"strict", "concept"}):
                reserved_name_violations.append(str(raw_key))
                continue
            if "task" in tokens and not tokens.intersection(
                {"family", "interface", "mapper", "projection", "legacy"}
            ):
                reserved_name_violations.append(str(raw_key))
                continue
            if "accuracy" in tokens and not tokens.intersection(
                {
                    "safe",
                    "exact",
                    "proxy",
                    "mapper",
                    "interface",
                    "projection",
                    "legacy",
                    "binary",
                    "acceptable",
                    "root",
                    "reviewed",
                    "targeted",
                }
            ):
                reserved_name_violations.append(str(raw_key))
        if reserved_name_violations:
            raise ValueError(
                f"evidence uses unqualified endpoint effect names for {experiment}: "
                f"{reserved_name_violations}"
            )

        # Machine-readable names must disclose proxy/targeted provenance.  A
        # downstream consumer must never infer full-root capability from a bare
        # ``complete`` or ``clinical`` effect key on a non-census experiment.
        if not bool(coverage["full_root_census"]):
            invalid_effect_keys = []
            for raw_key in row.get("effect", {}):
                key = str(raw_key).lower()
                if (
                    "clinical_complete" in key or "clinical_capability" in key
                ) and "model_panel" not in key:
                    invalid_effect_keys.append(str(raw_key))
                    continue
                if ("complete" in key or "clinical" in key) and not any(
                    qualifier in key
                    for qualifier in (
                        "proxy",
                        "root_reviewed",
                        "targeted_root_review",
                        "model_panel",
                    )
                ):
                    invalid_effect_keys.append(str(raw_key))
                    continue
                if ("top1" in key or "top2" in key) and not any(
                    qualifier in key
                    for qualifier in (
                        "safe_exact",
                        "proxy",
                        "targeted_root_review",
                        "root_reviewed",
                        "binary_acceptable",
                        "model_panel",
                    )
                ):
                    invalid_effect_keys.append(str(raw_key))
            if invalid_effect_keys:
                raise ValueError(
                    f"non-census evidence uses unqualified endpoint effect names for {experiment}: "
                    f"{invalid_effect_keys}"
                )
        if (
            experiment == "E10"
            and coverage.get("clinical_complete_status")
            != endpoint_coverage_audit.FULL_BLINDED_PANEL
        ):
            e10_keys = [str(key).lower() for key in row.get("effect", {})]
            invalid_e10 = [
                key for key in e10_keys if any(token in key for token in ("clinical", "complete", "partial"))
            ]
            if invalid_e10:
                raise ValueError(
                    "E10 binary acceptable sensitivity cannot be named as a clinical-complete/partial endpoint: "
                    f"{invalid_e10}"
                )

        row["endpoint_coverage_contract"] = {
            "coverage_matrix_schema_version": endpoint_coverage["schema_version"],
            **coverage,
            "arm_ids": arm_ids,
        }
        validated.append(row)
    return validated


def validate_closure(
    rows: Sequence[Mapping[str, Any]], endpoint_coverage: Mapping[str, Any]
) -> dict[str, Any]:
    allowed = {
        "implemented",
        "complete",
        "complete_new_gap",
        "excluded_by_request",
        "blocked_by_excluded_prerequisite",
    }
    invalid = [dict(row) for row in rows if row.get("status") not in allowed]
    if invalid:
        raise ValueError(f"invalid closure statuses: {invalid}")
    unresolved = [
        dict(row)
        for row in rows
        if row.get("status") not in {"implemented", "complete", "complete_new_gap", "excluded_by_request", "blocked_by_excluded_prerequisite"}
    ]
    coverage_records = list(endpoint_coverage.get("records", []))
    full_root = [
        str(record["experiment_id"])
        for record in coverage_records
        if bool(record.get("full_root_census"))
    ]
    not_applicable = [
        str(record["experiment_id"])
        for record in coverage_records
        if {
            record.get("clinical_complete_status"),
            record.get("compatible_partial_status"),
            record.get("complete_or_compatible_partial_status"),
        }
        == {endpoint_coverage_audit.NOT_APPLICABLE}
    ]
    panel_census = [
        str(record["experiment_id"])
        for record in coverage_records
        if record.get("clinical_complete_status")
        == endpoint_coverage_audit.FULL_BLINDED_PANEL
    ]
    migration_gaps = [
        str(record["experiment_id"])
        for record in coverage_records
        if str(record["experiment_id"])
        not in set(full_root) | set(panel_census) | set(not_applicable)
    ]
    migration_present = endpoint_coverage.get("migration_contract") is not None
    task_census_status = (
        str(
            endpoint_coverage["migration_contract"]["summary"].get(
                "task_census_status"
            )
        )
        if migration_present
        else "not_started"
    )
    task_closed = task_census_status == "complete_fresh_replay"
    expected_panel = sorted(endpoint_coverage_audit.MIGRATION_EXPERIMENT_IDS) if migration_present else []
    if (
        full_root != ["E2"]
        or not_applicable != ["E7a"]
        or sorted(panel_census) != expected_panel
        or len(migration_gaps) != (0 if migration_present else 14)
    ):
        raise ValueError(
            "metric-migration closure drift: "
            f"full={full_root}, panel={panel_census}, n/a={not_applicable}, gaps={migration_gaps}"
        )
    return {
        "schema_version": "cross-experiment-closure-v2",
        "scientific_execution": {
            "items": [dict(row) for row in rows],
            "eligible_remaining_count": len(unresolved),
            "eligible_remaining": unresolved,
            "closed": len(unresolved) == 0,
            "interpretation": (
                "No scientifically eligible experiment remains under the authorised execution scope. "
                "This statement concerns execution only and does not imply endpoint migration completeness. "
                "The formal E14 router is not marked pending because its required E13 latent labels were explicitly excluded; "
                "E14x directly tested and disabled the realised gate."
            ),
        },
        "metric_migration": {
            "closed": len(migration_gaps) == 0 and task_closed,
            "clinical_relation_closed": len(migration_gaps) == 0,
            "task_closed": task_closed,
            "task_census_status": task_census_status,
            "full_root_census_count": len(full_root),
            "full_root_census_experiments": full_root,
            "full_blinded_model_panel_count": len(panel_census),
            "full_blinded_model_panel_experiments": panel_census,
            "not_applicable_count": len(not_applicable),
            "not_applicable_experiments": not_applicable,
            "gap_count": len(migration_gaps),
            "gap_experiments": migration_gaps,
            "interpretation": (
                "All 79 target arms have exhaustive blinded three-reviewer model-panel clinical "
                "relations with ITA failure accounting, and the fresh family-specific task namespace "
                "is complete at 5,839/5,839 payloads. DA mapper and MCR semantic-judge estimates remain "
                "separate and may not be pooled. E2 remains the only human-root census and E7a remains structural N/A."
                if migration_present
                else
                "Only E2 has the full blinded/root census. E7a is N/A and the other "
                "14 experiments retain explicit metric-migration gaps."
            ),
        },
    }


def deterministic_tar_gz(archive: Path, files: Sequence[Path], base: Path) -> None:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w", format=tarfile.PAX_FORMAT) as tar:
        for path in sorted(files, key=lambda item: str(item.relative_to(base))):
            data = path.read_bytes()
            info = tarfile.TarInfo(str(path.relative_to(base)))
            info.size = len(data)
            info.mtime = 0
            info.uid = 0
            info.gid = 0
            info.uname = "root"
            info.gname = "root"
            info.mode = 0o644
            tar.addfile(info, io.BytesIO(data))
    archive.parent.mkdir(parents=True, exist_ok=True)
    with archive.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            compressed.write(buffer.getvalue())


def build(repo_root: Path, out: Path) -> dict[str, Any]:
    started = datetime.now(timezone.utc).isoformat()
    endpoint_coverage = endpoint_coverage_audit.build_payload(repo_root)
    e2_snapshot = build_e2_full800_snapshot(repo_root)
    migration_snapshot = build_endpoint_migration_snapshot(repo_root)
    validated = validate_evidence(repo_root, EVIDENCE, endpoint_coverage)
    closure = validate_closure(CLOSURE_ITEMS, endpoint_coverage)
    register_path = repo_root / REGISTER
    if not register_path.is_file():
        raise FileNotFoundError(register_path)
    register_text = register_path.read_text(encoding="utf-8")
    required_register_anchors = [
        "All scientifically eligible rows in the crosswalk are now implemented",
        "E13 remains excluded",
        "realised deployable gate was instead tested directly in",
        "E14x and disabled",
    ]
    missing_register = [anchor for anchor in required_register_anchors if anchor not in register_text]
    if missing_register:
        raise ValueError(f"experiment register is not closed: {missing_register}")

    out.mkdir(parents=True, exist_ok=True)
    evidence_payload = {
        "schema_version": "cross-experiment-evidence-v2",
        "grade_definitions": GRADE_DEFINITIONS,
        "records": validated,
    }
    write_json(out / "evidence_matrix.json", evidence_payload)
    write_jsonl(out / "evidence_matrix.jsonl", validated)
    write_json(out / "mechanism_chain.json", {"stages": list(MECHANISM_CHAIN)})
    write_json(out / "baseline_profiles.json", {"profiles": list(BASELINE_PROFILES)})
    write_json(out / "trajectory_motifs.json", {"motifs": list(TRAJECTORY_MOTIFS)})
    write_json(out / "closure_matrix.json", closure)
    write_json(out / "endpoint_coverage_matrix.json", endpoint_coverage)
    write_json(out / "e2_full800_snapshot.json", e2_snapshot)
    write_json(out / "endpoint_migration_snapshot.json", migration_snapshot)

    experiments = {str(row["experiment"]) for row in validated}
    stage_references = {item for stage in MECHANISM_CHAIN for item in stage["evidence"]}
    profile_references = {item for profile in BASELINE_PROFILES for item in profile["evidence"]}
    trajectory_references = {item for motif in TRAJECTORY_MOTIFS for item in motif["evidence"]}
    dangling = sorted((stage_references | profile_references | trajectory_references) - experiments)
    if dangling:
        raise ValueError(f"cross-synthesis references missing evidence rows: {dangling}")

    claim_path = repo_root / CLAIM_LEDGER
    claims = [
        json.loads(line)
        for line in claim_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    for claim in claims:
        if claim.get("claim_id") == "C015":
            migration_present = endpoint_coverage.get("migration_contract") is not None
            claim["claim"] = (
                "Safe-exact, legacy-chain, deprecated experiment-local strict fields, family-specific task, clinical-complete, "
                "compatible-partial, complete-or-compatible-partial coverage, binary-acceptable proxy, root-priority/proxy "
                "sensitivities, and reference-identifiability are distinct; no "
                "unscoped strict or Concept field is an ability endpoint. Clinical-complete supports diagnostic-capability "
                "interpretation only under a full blinded/root census; the complete-or-compatible-partial union remains a "
                "secondary coverage sensitivity. E2 alone is human-root-owned; the other 79 target arms now have an "
                "exhaustive blinded three-reviewer model-panel clinical census and a complete 5,839/5,839 fresh task replay; "
                "DA mapper and MCR semantic-judge task estimands remain separate and may not be pooled. E7a remains structural N/A."
                if migration_present
                else
                "Safe-exact, legacy-chain, task and clinical relations remain distinct. E2 alone has the full "
                "root contract; E7a is N/A and the other 14 experiments retain migration gaps."
            )
            claim["dependencies"] = list(endpoint_coverage_audit.EXPECTED_EXPERIMENT_IDS)
            claim["endpoint_coverage_contract"] = {
                "artifact": "endpoint_coverage_matrix.json",
                "clinical_capability_allowlist": ["E2"],
                "clinical_capability_endpoint": "clinical_complete",
                "secondary_coverage_endpoint": "complete_or_compatible_partial",
                "deprecated_unscoped_fields": ["strict", "Concept"],
                "not_applicable": ["E7a"],
                "full_blinded_model_panel_experiments": (
                    sorted(endpoint_coverage_audit.MIGRATION_EXPERIMENT_IDS)
                    if migration_present
                    else []
                ),
                "metric_migration_gap_count": 0 if migration_present else 14,
            }
    claim_ids = [str(row["claim_id"]) for row in claims]
    if len(claim_ids) != len(set(claim_ids)):
        raise ValueError("duplicate final claim ids")
    dangling_claim_dependencies = sorted(
        {
            str(item)
            for row in claims
            for item in row.get("dependencies", [])
        }
        - experiments
    )
    if dangling_claim_dependencies:
        raise ValueError(f"claim dependencies missing evidence rows: {dangling_claim_dependencies}")
    write_jsonl(out / "claim_ledger_final.jsonl", claims)

    summary = {
        "schema_version": "cross-experiment-root-synthesis-v2",
        "generated_at_utc": started,
        "evidence_record_count": len(validated),
        "mechanism_stage_count": len(MECHANISM_CHAIN),
        "baseline_profile_count": len(BASELINE_PROFILES),
        "cross_case_motif_count": len(TRAJECTORY_MOTIFS),
        "final_claim_count": len(claims),
        "scientific_execution_remaining_experiments": closure["scientific_execution"][
            "eligible_remaining_count"
        ],
        "metric_migration_gap_experiment_count": closure["metric_migration"]["gap_count"],
        "metric_migration_gap_experiments": closure["metric_migration"]["gap_experiments"],
        "metric_migration_overall_closed": closure["metric_migration"]["closed"],
        "metric_migration_clinical_relation_closed": closure["metric_migration"][
            "clinical_relation_closed"
        ],
        "metric_migration_full_root_census_experiments": closure["metric_migration"][
            "full_root_census_experiments"
        ],
        "metric_migration_not_applicable_experiments": closure["metric_migration"][
            "not_applicable_experiments"
        ],
        "endpoint_coverage_experiment_count": endpoint_coverage["experiment_count"],
        "endpoint_coverage_arm_record_count": endpoint_coverage["arm_record_count"],
        "metric_migration_model_panel_experiments": closure["metric_migration"][
            "full_blinded_model_panel_experiments"
        ],
        "metric_migration_task_census_status": endpoint_coverage["migration_contract"][
            "summary"
        ]["task_census_status"],
        "metric_migration_intention_rows": migration_snapshot["coverage"]["intention_rows"],
        "metric_migration_served_rows": migration_snapshot["coverage"]["served_rows"],
        "metric_migration_unserved_rows": migration_snapshot["coverage"]["unserved_rows"],
        "metric_migration_novel_relations": migration_snapshot["coverage"]["novel_relations"],
        "metric_migration_sentinel_relations": migration_snapshot["coverage"]["sentinel_relations"],
        "metric_migration_task_payloads_successful": migration_snapshot["task"]["successful"],
        "metric_migration_task_family_specific_holm_survivors": migration_snapshot["task"]["holm_survivors_total"],
        "e2_full800_cases": e2_snapshot["coverage"]["cases"],
        "e2_case_arm_rows": e2_snapshot["coverage"]["case_arm_rows"],
        "e2_unique_full_references": 455,
        "e2_overall_clinical_holm_survivors": 0,
        "e2_MCR_clinical_holm_survivors": 1,
        "e2_MCR_collapse3c_vs_impc_holm_q": 0.0456153274640822,
        "e2_overall_collapse3c_vs_impc_holm_q": 0.07084252673880494,
        "e2_MCR_collapse3c_vs_impc_mixed30_holm_q": 0.1368459823922466,
        "e2_family_interaction_holm_q": 0.22848857557122143,
        "e2_identifiability_interaction_holm_survivors": 0,
        "e2_identifiability_interaction_min_holm_q": {
            "ALL": 0.1544922753862307,
            "DA": 1.0,
            "MCR": 0.5864706764661767,
        },
        "primary_diagnostic_endpoint": (
            "clinical_complete; capability interpretation allowed only for full_root_census experiments"
        ),
        "clinical_capability_leaderboard_eligible_experiments": ["E2"],
        "default_system_decision": "retain Lite-like two independent proposals plus one frozen-pool comparator",
        "rejected_default": "current RCR-3 and current fourth-call gate",
        "network_finding": (
            "managed environment routing reached the configured providers for the three complete clinical reviewers; "
            "after the transient insufficient-credit response was resolved, the fresh task replay resumed and completed "
            "all 5,839 family-specific payloads without imputation"
        ),
        "register_sha256": sha256(register_path),
    }
    write_json(out / "synthesis_summary.json", summary)

    log_lines = [
        f"started_at_utc={started}",
        f"repo_root={repo_root}",
        f"evidence_records={len(validated)}",
        f"mechanism_stages={len(MECHANISM_CHAIN)}",
        f"baseline_profiles={len(BASELINE_PROFILES)}",
        f"trajectory_motifs={len(TRAJECTORY_MOTIFS)}",
        f"final_claims={len(claims)}",
        f"scientific_execution_remaining={closure['scientific_execution']['eligible_remaining_count']}",
        f"metric_migration_gap_count={closure['metric_migration']['gap_count']}",
        "metric_migration_full_root=E2",
        "metric_migration_not_applicable=E7a",
        f"endpoint_coverage_experiments={endpoint_coverage['experiment_count']}",
        f"endpoint_coverage_arm_records={endpoint_coverage['arm_record_count']}",
        "e2_full800_validation=passed",
        "endpoint_migration_snapshot_validation=passed",
        "e2_endpoint_contract=safe_exact,legacy_chain,clinical_complete,compatible_partial,complete_or_compatible_partial,task",
        "source_anchor_validation=passed",
        "endpoint_coverage_join_validation=passed",
        "cross_reference_validation=passed",
        "scientific_execution_closure_validation=passed",
        f"metric_migration_clinical_closure_validation={'closed_79_model_panel_arms' if endpoint_coverage.get('migration_contract') else 'open_79_arms'}",
        f"metric_migration_task_closure_validation={closure['metric_migration']['task_census_status']}",
    ]
    (out / "run.log").write_text("\n".join(log_lines) + "\n", encoding="utf-8")

    artifact_files = [
        out / "evidence_matrix.json",
        out / "evidence_matrix.jsonl",
        out / "mechanism_chain.json",
        out / "baseline_profiles.json",
        out / "trajectory_motifs.json",
        out / "closure_matrix.json",
        out / "endpoint_coverage_matrix.json",
        out / "e2_full800_snapshot.json",
        out / "endpoint_migration_snapshot.json",
        out / "claim_ledger_final.jsonl",
        out / "synthesis_summary.json",
        out / "run.log",
    ]
    report = repo_root / FINAL_REPORT
    if report.is_file():
        artifact_files.append(report)
    manifest = {
        "schema_version": "cross-experiment-manifest-v2",
        "files": [
            {
                "path": str(path.relative_to(repo_root)),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
            for path in artifact_files
        ],
        "source_reports": [
            {
                "experiment": row["experiment"],
                "path": row["report"],
                "sha256": row["source_sha256"],
            }
            for row in validated
        ],
    }
    write_json(out / "artifact_manifest.json", manifest)
    artifact_files.append(out / "artifact_manifest.json")

    archive = out / "CROSS_EXPERIMENT_ROOT_SYNTHESIS.tar.gz"
    deterministic_tar_gz(archive, artifact_files, repo_root)
    checksum = sha256(archive)
    (out / "CROSS_EXPERIMENT_ROOT_SYNTHESIS.tar.gz.sha256").write_text(
        f"{checksum}  {archive.name}\n", encoding="utf-8"
    )
    return {
        **summary,
        "archive_sha256": checksum,
        "archive_bytes": archive.stat().st_size,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = build(args.repo_root.resolve(), args.out.resolve())
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
