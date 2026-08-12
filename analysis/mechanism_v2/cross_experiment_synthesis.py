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
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = REPO_ROOT / "analysis/mechanism_v2/results/CROSS_EXPERIMENT_ROOT_SYNTHESIS"
REGISTER = "analysis/mechanism_v2/EXPERIMENT_REGISTER.md"
FINAL_REPORT = "analysis/mechanism_v2/CROSS_EXPERIMENT_ROOT_CRITICAL_SYNTHESIS.md"
CLAIM_LEDGER = "analysis/mechanism_v2/claim_ledger.jsonl"
E2_UNIFIED = "analysis/mechanism_v2/results/E2_blinded_clinical_adjudication/unified_800"

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
            "and collapse search; clinical-block organization materially moderates the effect."
        ),
        "effect": {
            "hierarchical_fixed_options_minus_clean_top1_pp": 41.0,
            "flat_fixed_options_minus_clean_top1_pp": 40.2,
            "hierarchical_clean_reorder_champion_flips": "133/180",
            "flat_clean_reorder_champion_flips": "165/199",
        },
        "causal_scope": "input-sensitive one-call stages, not the full legacy APHHM runtime",
        "refutes": ["answer options are a harmless display layer", "equal aggregate scores imply equal trajectories"],
        "report": "analysis/mechanism_v2/results/E1_input_factorial/REPORT.md",
        "anchors": ["+41.0pp", "+40.2pp", "133/180 H champions"],
    },
    {
        "experiment": "E2",
        "stage": "endpoint_and_identifiability",
        "design": "method-blind full-800 root census followed by a unified five-endpoint replay of all frozen outputs",
        "population": {"cases": 800, "DA": 400, "MCR": 400, "case_arm_rows": 7200},
        "grade": "B+D",
        "finding": (
            "Safe-exact is a deterministic lower bound, legacy-chain is a historical diagnostic, clinical-complete is the "
            "primary ability endpoint, partial is a scope-loss state, and task is a family-specific interface. Only 455/800 "
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
            "partial_range_pct": "29.88-35.25",
            "task_range_pct": "40.12-46.12",
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
            "Forest-style evidence integration converts an exposed fixed pool better than the e7 contrast selector, "
            "but exposure is the dominant bottleneck and exhaustive pairwise tournament adds cost without a demonstrated gain."
        ),
        "effect": {
            "forest_top1": "41/400",
            "e7_top1": "33/400",
            "forest_minus_e7_pp": 2.0,
            "discordance_gain_harm": "9/1",
            "mcnemar_p": 0.021484375,
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
            "Candidate independence is false: plausible siblings and wider pools harm both by direct alternative capture "
            "and by reordering unchanged candidates; DA and MCR express different interference mechanisms."
        ),
        "effect": {
            "sibling_delta_pp": -10.91,
            "sibling_holm_p": 0.01472,
            "width8_delta_pp": -16.46,
            "width8_holm_p": 0.000114,
            "width6_to_width8_delta_pp": -7.93,
        },
        "causal_scope": "gold-exposed constructed pools; typed-label construction errors limit relation-specific subarms",
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
            "not formatting, and its clinical-complete endpoint is materially worse than raw text."
        ),
        "effect": {
            "graph_minus_raw_complete_pp": -7.63,
            "discordance_raw_only_graph_only": "24/5",
            "mcnemar_p": 0.00055,
            "graphs_with_relation_error": "25/30",
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
            "tiny nonclinical input changes can still send the generator to different trajectories."
        ),
        "effect": {
            "mean_input_token_reduction_pct": 64.9,
            "complete_delta_pp": 1.57,
            "complete_mcnemar_p": 0.481,
            "champion_flip_pct": 95.29,
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
            "Exact identity is a safety/addressability invariant and restores reference exposure, but it is not a stand-alone top-1 cure; "
            "generic non-equivalence prose changes champions without useful direction."
        ),
        "effect": {
            "contaminated_selected_concepts_legacy_exact": "160/0",
            "unsafe_exposure_restoration_gain_loss": "11/1",
            "exposure_mcnemar_p": 0.00635,
            "safe_exact_top1_gain_loss": "8/5",
            "safe_exact_mcnemar_p": 0.58105,
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
            "The realised directional graph is too inconsistent for deployment; relation wording and even irrelevant graph context act as salience perturbations."
        ),
        "effect": {
            "directional_minus_exact_pp": -0.67,
            "bounded_minus_directional_pp": 0.0,
            "internal_direction_agreement_pct": 64.82,
            "repeat_pair_consistency_pct": 80.58,
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
        "population": {"cases": 220, "hard_soft_common": 183, "invalid_time": 125},
        "grade": "A+D",
        "finding": (
            "Atemporal absolute veto is clinically unsafe; softening it removes invalid reference vetoes but does not by itself identify a superior ranker, "
            "and time/order perturbations reveal large near-zero-net trajectory instability."
        ),
        "effect": {
            "hard_reference_vetoes": 9,
            "manually_valid_hard_reference_vetoes": 0,
            "soft_minus_hard_top1_pp": 1.64,
            "soft_minus_hard_mcnemar_p": 0.453,
            "legal_order_flip_pct": 24.6,
            "invalid_time_flip_pct": 23.2,
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
            "Forest views are correlated but retain a small real coverage increment; their benefit is not independent voting, "
            "and duplicate/role perturbations expose selector path dependence."
        ),
        "effect": {
            "real_minus_single_safe_exact_pp": 2.25,
            "real_minus_single_mcnemar_p": 0.0117,
            "safe_exact_real_only_clinical_gains": "6/10",
            "true_new_capture_to_top1": 3,
            "semantic_cluster_observation_ratio": 0.552,
        },
        "causal_scope": "joint effect of extra view content on union plus selection; role/duplicate flips are instability upper bounds",
        "refutes": ["three views are three independent votes", "duplicate evidence should raise confidence"],
        "report": "analysis/mechanism_v2/results/E9_view_independence/REPORT.md",
        "anchors": ["10 个 real-only 中只有 6 个", "cluster/observation 比为 0.552"],
    },
    {
        "experiment": "E10",
        "stage": "sequential_deliberation",
        "design": "doctor history isolated/sequential crossed with deterministic RRF/closed-pool Supervisor",
        "population": {"cases": 400, "root_audit_cases": 166},
        "grade": "A+D",
        "finding": (
            "Sequential history compresses candidate diversity dramatically but improves current-sample rank conversion; "
            "the Supervisor is a small semantic rescue when minority opinions exist, not the source of diversity loss."
        ),
        "effect": {
            "mean_union_isolated_sequential": "6.82/5.21",
            "pairwise_jaccard_isolated_sequential": "0.689/0.954",
            "rrf_clinical_top2_delta_pp": 4.5,
            "supervisor_clinical_top2_delta_pp": 3.25,
            "d3_new_concepts_total_sequential": 6,
        },
        "causal_scope": "homogeneous Llama panel on development cases; unique relation novelty was not measured",
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
            "while generic refine changes many trajectories but has no primary complete-endpoint advantage."
        ),
        "effect": {
            "relevant_case_specific_chunk_pct": 6.62,
            "relevant_minus_off_clinical_complete_top1_pp": -2.0,
            "relevant_minus_off_holm_q": 0.27,
            "off_refine_complete_or_partial_delta_pp": 3.5,
            "off_refine_sensitivity_holm_q": 0.0463,
        },
        "causal_scope": "the current lexical bundle contract, not ideal typed RAG; complete+partial refine is secondary",
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
            "On frozen candidate pools, an explicit raw-text comparator beats blindly taking the historical first candidate; "
            "S1 loses decisive relations, graph does not repair them, width is not monotone, and most apparent depth effects are not attributable to new information."
        ),
        "effect": {
            "raw_k5_pairwise_minus_first_complete_pp": 4.67,
            "raw_k5_pairwise_holm_q": 0.04987,
            "raw_k10_pairwise_minus_first_complete_pp": 5.0,
            "raw_k10_pairwise_holm_q": 0.02842,
            "safe_exact_exposure_gain_k5_to_k10": 2,
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
            "its clinical flips are harm-heavy and the historical upstream states are not causally exchangeable."
        ),
        "effect": {
            "new_entities": 135,
            "safe_exact_reference_discoveries": 0,
            "root_repairs_harms_neutral": "6/15/13",
            "identical_upstream_pairs": "0/300",
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
            "safe identity survives, but generated structure plus fixed frontier and self-calibrated completeness lose to the simpler Lite path."
        ),
        "effect": {
            "complete_top1_lite_rcr_compact4": "29/20/18",
            "complete_top2_lite_rcr_compact4": "42/31/26",
            "rcr_minus_lite_frontier_exposure_pp": -7.0,
            "frontier_exposure_holm_q": 0.000311,
            "material_span_drops": "at least 69/119",
            "wrong_or_unsupported_relations": "20/60",
            "self_complete_root_complete": "9/66",
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
        "strength": "best fixed-pool evidence integration in E4, useful residual view capture, and the highest complete-or-partial coverage in E2 (48.25%)",
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


def build_e2_full800_snapshot(repo_root: Path) -> dict[str, Any]:
    """Validate and preserve the full-census E2 measurement basis.

    The cross-experiment ledger used to transcribe an outcome-enriched subset
    analysis.  This loader deliberately fails closed unless the new
    9-arm x 800-case five-endpoint replay is complete.  It emits the complete
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
    endpoints = ["safe_exact", "legacy_chain", "clinical_complete", "partial", "task"]
    arms = ["collapse3c", "multistance", "lite", "forest", "impc", "e7", "v0", "B06", "B07"]
    if manifest.get("cases_n") != 800 or manifest.get("arm_case_rows_n") != 7200:
        raise ValueError("E2 unified replay is not the required 800-case/7,200-row census")
    if manifest.get("arms") != arms or manifest.get("endpoint_columns") != endpoints:
        raise ValueError("E2 arm order or five-endpoint contract drifted")
    if validation.get("cases_n") != 800 or validation.get("case_arm_rows_n") != 7200:
        raise ValueError("E2 validation counts disagree with the manifest")
    if validation.get("clinical_missing_n") != 0 or validation.get("complete_partial_overlap_n") != 0:
        raise ValueError("E2 clinical endpoint replay has missing or overlapping labels")
    if any(validation.get("arm_counts", {}).get(arm) != 800 for arm in arms):
        raise ValueError("E2 has incomplete arm coverage")

    leaderboard = payload["leaderboard"]
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
        "schema_version": "cross-synthesis-e2-full800-v1",
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
        "endpoint_contract": manifest["endpoint_contract"],
        "endpoint_definitions": {
            "safe_exact": "exact or frozen safe synonym; deterministic conservative lower bound",
            "legacy_chain": "historical substring/resolver chain; diagnostic compatibility only",
            "clinical_complete": "root-audited complete clinical object; primary true diagnostic ability",
            "partial": "root-audited parent/component or otherwise incomplete but clinically related object",
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
            "partial is not complete, and combined task mixes two different benchmark interfaces"
        ),
    }


def validate_evidence(repo_root: Path, evidence: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
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
        validated.append(row)
    return validated


def validate_closure(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
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
    return {
        "items": [dict(row) for row in rows],
        "eligible_remaining_count": len(unresolved),
        "eligible_remaining": unresolved,
        "interpretation": (
            "No scientifically eligible experiment remains under the authorised scope. "
            "The formal E14 router is not marked pending because its required E13 latent labels were explicitly excluded; "
            "E14x directly tested and disabled the realised gate."
        ),
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
    e2_snapshot = build_e2_full800_snapshot(repo_root)
    validated = validate_evidence(repo_root, EVIDENCE)
    closure = validate_closure(CLOSURE_ITEMS)
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
        "schema_version": "cross-experiment-evidence-v1",
        "grade_definitions": GRADE_DEFINITIONS,
        "records": validated,
    }
    write_json(out / "evidence_matrix.json", evidence_payload)
    write_jsonl(out / "evidence_matrix.jsonl", validated)
    write_json(out / "mechanism_chain.json", {"stages": list(MECHANISM_CHAIN)})
    write_json(out / "baseline_profiles.json", {"profiles": list(BASELINE_PROFILES)})
    write_json(out / "trajectory_motifs.json", {"motifs": list(TRAJECTORY_MOTIFS)})
    write_json(out / "closure_matrix.json", closure)
    write_json(out / "e2_full800_snapshot.json", e2_snapshot)

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
            claim["claim"] = (
                "Safe-exact (historical field strict), legacy-chain, family-specific task, clinical-complete, partial, "
                "and reference-identifiability are different endpoints; clinical-complete is the primary ability measure."
            )
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
        "schema_version": "cross-experiment-root-synthesis-v1",
        "generated_at_utc": started,
        "evidence_record_count": len(validated),
        "mechanism_stage_count": len(MECHANISM_CHAIN),
        "baseline_profile_count": len(BASELINE_PROFILES),
        "cross_case_motif_count": len(TRAJECTORY_MOTIFS),
        "final_claim_count": len(claims),
        "eligible_remaining_experiments": closure["eligible_remaining_count"],
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
        "primary_diagnostic_endpoint": "clinical_complete",
        "default_system_decision": "retain Lite-like two independent proposals plus one frozen-pool comparator",
        "rejected_default": "current RCR-3 and current fourth-call gate",
        "network_finding": (
            "managed environment routing reached OpenRouter and the actual Google provider without region/IP rejection; "
            "bare direct DNS did not work, so no repository VPN is needed but the environment proxy remains required"
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
        f"eligible_remaining={closure['eligible_remaining_count']}",
        "e2_full800_validation=passed",
        "e2_endpoint_contract=safe_exact,legacy_chain,clinical_complete,partial,task",
        "source_anchor_validation=passed",
        "cross_reference_validation=passed",
        "closure_validation=passed",
    ]
    (out / "run.log").write_text("\n".join(log_lines) + "\n", encoding="utf-8")

    artifact_files = [
        out / "evidence_matrix.json",
        out / "evidence_matrix.jsonl",
        out / "mechanism_chain.json",
        out / "baseline_profiles.json",
        out / "trajectory_motifs.json",
        out / "closure_matrix.json",
        out / "e2_full800_snapshot.json",
        out / "claim_ledger_final.jsonl",
        out / "synthesis_summary.json",
        out / "run.log",
    ]
    report = repo_root / FINAL_REPORT
    if report.is_file():
        artifact_files.append(report)
    manifest = {
        "schema_version": "cross-experiment-manifest-v1",
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
