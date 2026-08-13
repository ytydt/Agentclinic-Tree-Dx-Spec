# Cross-experiment endpoint coverage audit

## Decision

Only **E2** is a full blinded/root-level clinical census and therefore the only experiment eligible for a clinical-capability leaderboard. All other experiments are blocked from that ingestion path: they are structural-only, safe-exact mechanism studies, targeted root audits, or proxy-completed/root-priority sensitivities. E10 is additionally blocked because its frozen binary `acceptable` recode does not separate complete from compatible partial.
Across 91 independently sourced, declared audit arms, 9 E2 arms have the full contract, 79 arms retain metric-migration gaps, and 3 E7a structural replay arms are clinically N/A.

Safe-exact remains a valid conservative identity lower bound. Legacy-chain, Concept, generic `accuracy`, task/mapper, or starred proxy endpoints must not be promoted to clinical-complete capability by an aggregation script.
Frozen raw summaries are provenance only—not a cross-experiment table that may be flattened or ingested directly. In particular, E1/E4/E5/E6/E6x/E8 historical `strict`, generic accuracy, and `complete*`-style fields remain under their local contracts. Every downstream consumer must join through `endpoint_coverage_matrix.json` and enforce its coverage gate before reading those fields.

## Coverage matrix

| Experiment | Arms | Intended cases/arm | Clinical complete | Compatible partial | Complete or compatible partial | Full root census | Leaderboard | Conclusion use |
|---|---:|---:|---|---|---|---|---|---|
| E1 | 8 | 200 | targeted only | not available | not available | no | prohibited | `safe_exact_input_contamination_mechanism_only` |
| E2 | 9 | 800 | full-root census | full-root census | full-root census | yes | allowed | `clinical_capability_leaderboard` |
| E4 | 5 | 400 | targeted only | not available | not available | no | prohibited | `safe_exact_fixed_pool_selector_mechanism_only` |
| E5 | 9 | 200 | targeted only | targeted only | not available | no | prohibited | `safe_exact_candidate_interference_mechanism_only` |
| E6 | 3 | 300 | proxy + root-priority | proxy + root-priority | proxy + root-priority | no | prohibited | `semantic_proxy_sensitivity_not_capability_leaderboard` |
| E6x | 2 | 300 | proxy + root-priority | proxy + root-priority | proxy + root-priority | no | prohibited | `semantic_proxy_sensitivity_not_capability_leaderboard` |
| E7a | 3 | 800 | N/A (no fresh output) | N/A (no fresh output) | N/A (no fresh output) | no | prohibited | `structural_registry_identity_only` |
| E7b | 3 | 400 | targeted only | not available | not available | no | prohibited | `identity_addressability_and_safe_exact_mechanism_only` |
| E7c | 4 | 299 | targeted only | not available | not available | no | prohibited | `safe_exact_and_relation_fidelity_mechanism_only` |
| E8 | 4 | 220 | targeted only | targeted only | not available | no | prohibited | `veto_safety_mechanism_only` |
| E9 | 4 | 400 | not available | not available | not available | no | prohibited | `view_capture_and_instability_mechanism_only` |
| E10 | 4 | 400 | not measured (binary acceptable only) | not measured / not separately coded | not measured (binary acceptable is not union) | no | prohibited | `binary_acceptable_sensitivity_only_no_clinical_endpoint_no_leaderboard` |
| E11 | 8 | 400 | proxy + root-priority | proxy + root-priority | proxy + root-priority | no | prohibited | `root_priority_proxy_sensitivity_not_capability_leaderboard` |
| E12 | 20 | 300 | proxy + root-priority | proxy + root-priority | proxy + root-priority | no | prohibited | `root_priority_proxy_sensitivity_not_capability_leaderboard` |
| E14x | 2 | 300 | targeted only | targeted only | not available | no | prohibited | `retrospective_gate_mechanism_only_no_causal_leaderboard` |
| RCR3 | 3 | 300 | proxy + root-priority | proxy + root-priority | proxy + root-priority | no | prohibited | `root_priority_proxy_sensitivity_not_capability_leaderboard` |

## Coverage boundaries

- **E1** — Clinical review covers 4 fixed-format harms plus 18 mechanism transitions, not all eight arms. Blindness grade: `targeted_mechanism_review_not_full_blind_census`.
- **E2** — All 7,200 case-arm rows have mutually exclusive clinical-complete and compatible-partial decisions; complete-or-compatible-partial is secondary coverage. Blindness grade: `arm_endpoint_hidden_root_relation_census`.
- **E4** — All 17 safe-exact correctness discordances and 12 sampled all-miss flips were reviewed; the remaining outputs are not clinically censused. Blindness grade: `selector_blinded_targeted_transition_review`.
- **E5** — The 339 judgments cover construction labels, injected champions, and sampled transitions; they are not 1,800 case-arm clinical outcomes. Blindness grade: `targeted_nonblind_relation_and_transition_review`.
- **E6** — 801 served outputs are proxy-completed; 262 rows received root review and 539 remain external-screen-only. Blindness grade: `arm_blind_external_screen_with_targeted_root_correction`.
- **E6x** — All 513 served outputs have proxy labels, but only 126 judgments in 63 cases received root review. Blindness grade: `arm_blind_external_screen_with_targeted_root_correction`.
- **E7a** — No fresh selector consumes the counterfactual registry, so clinical arm outcomes are undefined rather than missing. Blindness grade: `not_applicable_structural_offline_replay`.
- **E7b** — The clinical queue contains 40 priority cases; 360 cases lack exhaustive clinical equivalence adjudication. Blindness grade: `selector_blinded_targeted_priority_review`.
- **E7c** — All 84 discordant cases were mechanism-reviewed, but the remaining 215 cases have no full clinical classification. Blindness grade: `selector_blinded_discordance_enriched_root_review`.
- **E8** — Root review covers 30 mechanism-enriched cases; 190 cases have no complete/compatible-partial/no judgment. Blindness grade: `selector_blinded_mechanism_enriched_root_review`.
- **E9** — The frozen root queue has 70 cases, but its legacy binary scope/surface labels do not implement the canonical complete/compatible-partial/no partition; 330 cases remain clinically unadjudicated. Blindness grade: `selector_blinded_mechanism_enriched_root_review`.
- **E10** — The corrected table is explicitly binary-clinical-acceptable only; complete, compatible-partial and their union are unmeasured. 166 cases were root-reviewed and 234 remain proxy-negative. Blindness grade: `nonblind_root_priority_binary_screen_review`.
- **E11** — Root review covers 624 of 6,400 arm-rank occurrences; 5,776 occurrences retain heterogeneous proxy labels. Blindness grade: `nonblind_endpoint_critical_root_overrides_with_proxy_completion`.
- **E12** — Root review covers 385 of 3,191 candidate relations in 154 cases; 2,806 relations remain heterogeneous proxy. Blindness grade: `nonblind_arm_visible_endpoint_critical_root_overrides_with_proxy_completion`.
- **E14x** — The primary comparison has two historical arms over 300 cases; 56 cases were root-reviewed and no proxy completion was performed. Blindness grade: `retrospective_mechanism_enriched_root_review`.
- **RCR3** — 375 high-impact relations were root-reviewed; 3,151 noncritical relations retain heterogeneous proxy and 7 screen failures are fail-closed. Blindness grade: `nonblind_arm_visible_endpoint_critical_root_overrides_with_proxy_completion`.

## Raw-field ingestion risks

- **E1**: `strict_top1_fields_are_safe_exact_aliases`.
- **E2**: `legacy_chain_retained_diagnostic_only_under_explicit_contract`.
- **E4**: `generic_accuracy_and_primary_strict_fields_mean_safe_exact`.
- **E5**: `strict_top1_fields_are_safe_exact_aliases`.
- **E6**: `strict_top1_alias_plus_complete_equivalent_proxy_may_be_overread`.
- **E6x**: `strict_top1_alias_plus_complete_equivalent_proxy_may_be_overread`.
- **E7a**: `legacy_substring_is_treatment_and_score_top1_gold_is_diagnostic_only`.
- **E7b**: `legacy_substring_is_treatment_and_gold_top1_rate_is_served_safe_exact`.
- **E7c**: `gold_top1_rate_is_served_safe_exact_while_primary_report_is_ita`.
- **E8**: `summary_accuracy_is_served_safe_exact`.
- **E9**: `strict_endpoint_fields_are_safe_exact_aliases`.
- **E10**: `binary_acceptable_historical_values_are_not_complete_or_complete_plus_partial`.
- **E11**: `clinical_complete_star_and_complete_partial_star_are_proxy_completed`.
- **E12**: `clinical_complete_star_and_complete_partial_star_are_proxy_completed`.
- **E14x**: `strict_gate_and_mapper_fields_are_not_clinical_endpoints`.
- **RCR3**: `strict_fields_and_clinical_complete_star_are_not_full_root`.

## Arm-registry sources

The canonical arm ordering is checked against one independently stored machine source per experiment. Paths and SHA-256 values below are part of the generated contract; source drift, parse failure, missing/extra arms, or duplicate declared arms aborts generation.

| Experiment | Parsed arms | Source kind | Parser | Source path | SHA-256 |
|---|---:|---|---|---|---|
| E1 | 8 | `pre_online_preregistration` | `json_list_at_path` | `analysis/mechanism_v2/results/E1_input_factorial/preregistration.json` | `d748fc05888ac784ec1a2a1b832209d37f27e7b277c3043281cc9bb18a0d0703` |
| E2 | 9 | `full_replay_manifest` | `json_list_at_path` | `analysis/mechanism_v2/results/E2_blinded_clinical_adjudication/unified_800/manifest.json` | `14d8d02479fa7372a9aca9a6e8ec2876f609f24032fde307b52dbe2d52553704` |
| E4 | 5 | `pre_online_preregistration` | `json_list_at_path` | `analysis/mechanism_v2/results/E4_fixed_pool_crossover/preregistration.json` | `2bcd2a2340573a7ca6e971d0afac4045e0162ec6d5f8b1b2e59042b982e28710` |
| E5 | 9 | `pre_online_preregistration` | `json_list_at_path` | `analysis/mechanism_v2/results/E5_candidate_interference/preregistration.json` | `198ea829c4265ce1bf36c9d3296ebabf58751a6c8959af7a6782d34d4063c59e` |
| E6 | 3 | `pre_online_preregistration` | `json_list_at_path` | `analysis/mechanism_v2/results/E6_representation_fidelity/preregistration.json` | `d1828d1ed912fc6645d8efb667497bf8271ae6c5691af8e33ac843562a973d14` |
| E6x | 2 | `final_semantic_analysis_arm_table` | `json_object_keys_at_path` | `analysis/mechanism_v2/results/E6x_unpadded_flat/semantic_final_summary.json` | `ba055eabcfeb0559609a394f1f5edf18fd11eb252df0ae6b0d0ced9440e81118` |
| E7a | 3 | `full_structural_replay_group_tables` | `json_consistent_group_arm_keys` | `analysis/mechanism_v2/results/E7_registry_replay/summary.json` | `0f6e312cb602a6ca8bdc5d1eb594a1cf356f54d1078d2d33a93846b52c554904` |
| E7b | 3 | `pre_online_preregistration` | `json_list_at_path` | `analysis/mechanism_v2/results/E7b_registry_selector/preregistration.json` | `53e9f933b31a1aa2c76101d646c1bc915b6f03c74e1e30d7b3c8fff441a27d28` |
| E7c | 4 | `pre_online_preregistration` | `json_list_at_path` | `analysis/mechanism_v2/results/E7c_directional_registry/preregistration.json` | `352226c101d30d9d2d5e69887c0cd8f4ed97fe0b72a73788fe620a36bf8f5288` |
| E8 | 4 | `pre_online_preregistration` | `json_list_at_path` | `analysis/mechanism_v2/results/E8_temporal_veto/preregistration.json` | `4dba1196392295285df7c647b4660a74903bf3baad26e80d3a828a314371ff5e` |
| E9 | 4 | `pre_online_preregistration` | `json_list_at_path` | `analysis/mechanism_v2/results/E9_view_independence/preregistration.json` | `9a084378b5f2e5f97ddd70662719f82a39ec984371d4de8cdacdaf6f5564ab79` |
| E10 | 4 | `pre_online_preregistration` | `json_list_at_path` | `analysis/mechanism_v2/results/E10_mac_factorial/preregistration.json` | `0224081a9c17be18f4730ac7a167f3549544c5df6272cbfdbff562092466a798` |
| E11 | 8 | `pre_online_preregistration` | `json_list_at_path` | `analysis/mechanism_v2/results/E11_b07_factorial/preregistration.json` | `2508611d9507d8747830739589969752e5b537cce902f2b8c5cd0f4d1b382336` |
| E12 | 20 | `all_served_case_condition_rows` | `jsonl_unique_string_field` | `analysis/mechanism_v2/results/E12_e7_factorial/case_conditions.jsonl` | `ca1ec08c89d0358316ba906de677b94240656b46b71e652d79715a2e9a9be63f` |
| E14x | 2 | `frozen_provenance_index_primary_dataset_intersection` | `e14x_primary_manifest_dataset_intersection` | `analysis/mechanism_v2/results/E14x_runtime_gate/source_provenance.json` | `d71cc6157cd51f145d06bf3a3cbba3482f67697e84a12b12c04fe5c95bafa3f4` |
| RCR3 | 3 | `pre_online_preregistration` | `json_object_keys_at_path` | `analysis/mechanism_v2/results/RCR3_relation_preserving/preregistration.json` | `9c90e2091e6bcd21c0f9dbf56c815369eda9e926d6239ed91875241ecb9d8ebc` |

**E14x source limit:** The indexed historical log manifests are absent from this sparse checkout; the checked-in provenance index and its recorded paths/hashes are the machine source.

## Fail-closed rules

1. The experiment list must contain exactly the 16 registered IDs, once each, in the frozen order.
2. Every canonical ARM_IDS set must exactly equal its independently parsed arm-registry source; the 91-row total is not accepted as self-validation.
3. Direct flattening/ingestion of frozen raw experiment summaries is prohibited; downstream use requires a join through the coverage-gated cross matrix.
4. The full-root allowlist must equal `{E2}`; adding another experiment requires an explicit audit-contract revision.
5. Every non-full experiment has `leaderboard_ingestion=prohibited`.
6. E7a remains clinical-endpoint N/A until a fresh selector consumes each counterfactual registry.
7. E10 remains blocked from complete scoring because the frozen binary acceptable audit does not separate complete, compatible-partial, and not-equivalent.
8. Source reports must retain the evidence anchors used by this classification; drift aborts generation.

## Reproduction

```bash
python -m analysis.mechanism_v2.endpoint_coverage_audit
python -m analysis.mechanism_v2.endpoint_coverage_audit --check
```

Generation is deterministic: no timestamp, network call, model call, or random sampling is used. Source-report and arm-registry-source SHA-256 values are recorded in the JSON matrix.
