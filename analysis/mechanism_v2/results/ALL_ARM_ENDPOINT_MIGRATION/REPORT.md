# Canonical endpoint migration: 79-arm exhaustive Top-1 replay

## Decision

The 79-arm metric-migration gap is closed at the exhaustive blinded three-reviewer model-panel level: every intended row has an ITA disposition and every served Top-1 has canonical clinical-complete, compatible-partial, and C∪P status. The strict human-root capability allowlist is **not** expanded: E2 remains the only human-root-owned full census, while the 79 migrated arms are a calibrated model-panel sensitivity census.

The fresh task namespace is complete: every frozen unique payload was evaluated, historical task values were not copied, and no missing value was imputed. DA mapper and MCR semantic-judge outcomes remain separate interface endpoints rather than a pooled clinical estimand.

Historical proxy, targeted, binary-acceptable, safe-exact, and old task fields remain in their source reports as mechanism/provenance evidence; they are not renamed as canonical clinical outcomes.
Eleven E8 rows with a valid frozen champion but invalid auxiliary runner-up/veto fields are recovered only for Top-1 evaluation. Their full-response failure and source error remain explicit; the other 1,030 rows without an evaluable Top-1 remain ITA failures.

## Coverage and provenance

| Quantity | Value |
|---|---:|
| Registered target arms | 79 |
| Intention rows | 24,076 |
| Served Top-1 rows | 23,046 |
| Technical failures retained in ITA | 1,030 |
| Unique case-prediction relations | 5,351 |
| Exact-normalized E2 root relations reused | 1,693 |
| Newly blinded relations | 3,407 |
| Hidden E2 sentinels | 1,173 |
| Registered fresh task payloads | 5,839 |
| Fresh task payloads completed | 5,839 |
| Fresh task payloads not evaluable | 0 |

No credential is present in a prompt, cache identity, response artifact, manifest, or report. Clinical cards hide case key, experiment, arm, old endpoint, proxy status, safe/legacy/task status, and sentinel identity.
`artifact_manifest.json` closes every migration artifact with byte count and SHA-256.
`design/source_binding_manifest.json` additionally binds all 72 consumed source result files to SHA-256 and Git worktree/HEAD/source-commit blob IDs.
Nineteen invalid historical records in the fresh MCR cache namespace are preserved in a quarantine ledger and replaced by validator-compliant responses at the same content addresses. DA mapper calls use per-task resolver state, and all 7,648 online call records have one task owner and module/prompt/payload provenance matching their immutable cache records.

## Embedded calibration

| Reviewer | Model | Fine-label accuracy | Complete accuracy | Complete precision | Complete recall | C∪P accuracy | C∪P precision | C∪P recall |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| reviewer_a | `google/gemini-2.5-flash` | 65.98% | 96.25% | 74.19% | 62.16% | 87.55% | 79.82% | 93.37% |
| reviewer_b | `anthropic/claude-sonnet-4.6` | 70.08% | 97.53% | 82.61% | 77.03% | 90.96% | 85.77% | 93.58% |
| reviewer_c | `openai/gpt-5.6` | 74.00% | 98.21% | 89.55% | 81.08% | 94.37% | 93.35% | 92.96% |

The sentinels calibrate measurement error; they do not convert model decisions into human root decisions. Fine-label error is materially larger than the binary complete boundary error, so C/P/X/M/N counts must retain their model-panel provenance.

## All-arm canonical endpoint table

Clinical rates are ITA. Task is shown separately for DA and MCR as `rate (evaluable/ITA)`. The completed task census supports paired family-specific interface contrasts, but DA and MCR remain non-poolable.

| Experiment | Arm | Served/ITA | Safe exact | Legacy chain | Clinical complete | Compatible partial | C∪P | DA task | MCR task |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| E1 | `ab02_flat__clean_fixed` | 200/200 | 6.50% | 23.00% | 24.50% | 29.50% | 54.00% | 38.00% (100/100) | 31.00% (100/100) |
| E1 | `ab02_flat__clean_shuffled_blocks` | 199/200 | 5.50% | 19.50% | 28.50% | 26.00% | 54.50% | 31.00% (100/100) | 29.00% (100/100) |
| E1 | `ab02_flat__options_fixed` | 199/200 | 46.50% | 62.50% | 64.00% | 16.50% | 80.50% | 64.00% (100/100) | 59.00% (100/100) |
| E1 | `ab02_flat__options_shuffled_blocks` | 199/200 | 37.00% | 56.00% | 59.50% | 16.00% | 75.50% | 63.00% (100/100) | 55.00% (100/100) |
| E1 | `aphhm_hierarchical__clean_fixed` | 189/200 | 8.00% | 22.00% | 19.00% | 33.00% | 52.00% | 32.00% (100/100) | 31.00% (100/100) |
| E1 | `aphhm_hierarchical__clean_shuffled_blocks` | 189/200 | 8.50% | 24.50% | 21.50% | 29.50% | 51.00% | 31.00% (100/100) | 30.00% (100/100) |
| E1 | `aphhm_hierarchical__options_fixed` | 187/200 | 47.00% | 58.50% | 60.50% | 18.50% | 79.00% | 66.00% (100/100) | 59.00% (100/100) |
| E1 | `aphhm_hierarchical__options_shuffled_blocks` | 176/200 | 29.00% | 45.50% | 49.50% | 21.50% | 71.00% | 53.00% (100/100) | 53.00% (100/100) |
| E10 | `isolated_rrf` | 400/400 | 5.25% | 20.00% | 9.00% | 28.75% | 37.75% | 24.50% (200/200) | 24.00% (200/200) |
| E10 | `isolated_supervisor` | 400/400 | 5.50% | 21.50% | 9.25% | 32.75% | 42.00% | 23.50% (200/200) | 25.00% (200/200) |
| E10 | `sequential_rrf` | 400/400 | 6.50% | 22.50% | 10.25% | 33.50% | 43.75% | 24.00% (200/200) | 27.00% (200/200) |
| E10 | `sequential_supervisor` | 400/400 | 6.50% | 22.00% | 11.00% | 33.50% | 44.50% | 24.00% (200/200) | 27.00% (200/200) |
| E11 | `hard_negative_refine_off` | 400/400 | 6.75% | 19.50% | 12.25% | 31.25% | 43.50% | 26.00% (200/200) | 28.00% (200/200) |
| E11 | `hard_negative_refine_on` | 400/400 | 6.75% | 18.50% | 12.75% | 34.25% | 47.00% | 28.00% (200/200) | 29.00% (200/200) |
| E11 | `off_refine_off` | 400/400 | 7.25% | 19.00% | 13.00% | 30.75% | 43.75% | 24.00% (200/200) | 30.00% (200/200) |
| E11 | `off_refine_on` | 400/400 | 6.75% | 19.00% | 13.00% | 35.00% | 48.00% | 26.00% (200/200) | 30.00% (200/200) |
| E11 | `random_refine_off` | 400/400 | 6.00% | 19.25% | 12.00% | 32.25% | 44.25% | 28.00% (200/200) | 28.50% (200/200) |
| E11 | `random_refine_on` | 400/400 | 6.25% | 18.75% | 12.75% | 33.75% | 46.50% | 28.00% (200/200) | 30.00% (200/200) |
| E11 | `relevant_refine_off` | 400/400 | 6.00% | 19.50% | 12.00% | 32.00% | 44.00% | 27.50% (200/200) | 27.00% (200/200) |
| E11 | `relevant_refine_on` | 400/400 | 5.75% | 19.25% | 12.25% | 33.25% | 45.50% | 27.00% (200/200) | 27.50% (200/200) |
| E12 | `graph_k10_first` | 300/300 | 7.00% | 19.00% | 9.67% | 29.33% | 39.00% | 24.00% (150/150) | 24.00% (150/150) |
| E12 | `graph_k10_pairwise` | 256/300 | 6.67% | 17.33% | 10.00% | 29.00% | 39.00% | 20.00% (150/150) | 24.67% (150/150) |
| E12 | `graph_k10_pointwise` | 252/300 | 6.33% | 16.33% | 9.33% | 27.33% | 36.67% | 19.33% (150/150) | 23.33% (150/150) |
| E12 | `graph_k5_first` | 300/300 | 7.00% | 19.00% | 9.67% | 29.33% | 39.00% | 24.00% (150/150) | 24.00% (150/150) |
| E12 | `graph_k5_pairwise` | 258/300 | 7.00% | 18.00% | 9.67% | 30.00% | 39.67% | 21.33% (150/150) | 24.67% (150/150) |
| E12 | `graph_k5_pointwise` | 257/300 | 7.00% | 17.67% | 10.33% | 28.33% | 38.67% | 22.67% (150/150) | 24.67% (150/150) |
| E12 | `raw_depth1_k10_pairwise` | 299/300 | 8.33% | 23.00% | 12.67% | 36.67% | 49.33% | 26.67% (150/150) | 32.00% (150/150) |
| E12 | `raw_depth2_k10_pairwise` | 300/300 | 8.33% | 23.00% | 13.00% | 36.33% | 49.33% | 26.67% (150/150) | 32.67% (150/150) |
| E12 | `raw_k10_first` | 300/300 | 7.00% | 19.00% | 9.67% | 29.33% | 39.00% | 24.00% (150/150) | 24.00% (150/150) |
| E12 | `raw_k10_pairwise` | 298/300 | 8.67% | 23.67% | 13.67% | 37.67% | 51.33% | 25.33% (150/150) | 34.00% (150/150) |
| E12 | `raw_k10_pointwise` | 298/300 | 8.33% | 23.33% | 13.00% | 34.33% | 47.33% | 28.67% (150/150) | 28.67% (150/150) |
| E12 | `raw_k5_first` | 300/300 | 7.00% | 19.00% | 9.67% | 29.33% | 39.00% | 24.00% (150/150) | 24.00% (150/150) |
| E12 | `raw_k5_pairwise` | 300/300 | 8.33% | 22.33% | 13.67% | 35.00% | 48.67% | 27.33% (150/150) | 33.33% (150/150) |
| E12 | `raw_k5_pointwise` | 299/300 | 8.00% | 20.00% | 13.33% | 34.00% | 47.33% | 28.67% (150/150) | 31.33% (150/150) |
| E12 | `s1_k10_first` | 300/300 | 7.00% | 19.00% | 9.67% | 29.33% | 39.00% | 24.00% (150/150) | 24.00% (150/150) |
| E12 | `s1_k10_pairwise` | 299/300 | 6.67% | 17.33% | 11.00% | 31.67% | 42.67% | 25.33% (150/150) | 28.00% (150/150) |
| E12 | `s1_k10_pointwise` | 299/300 | 5.67% | 15.33% | 9.33% | 32.00% | 41.33% | 26.67% (150/150) | 24.00% (150/150) |
| E12 | `s1_k5_first` | 300/300 | 7.00% | 19.00% | 9.67% | 29.33% | 39.00% | 24.00% (150/150) | 24.00% (150/150) |
| E12 | `s1_k5_pairwise` | 298/300 | 7.00% | 19.00% | 10.67% | 33.00% | 43.67% | 26.67% (150/150) | 27.33% (150/150) |
| E12 | `s1_k5_pointwise` | 298/300 | 5.67% | 17.67% | 9.67% | 33.00% | 42.67% | 28.00% (150/150) | 24.67% (150/150) |
| E14x | `mosaic_adaptive4v2_v1` | 300/300 | 10.33% | 24.00% | 16.33% | 29.33% | 45.67% | 18.00% (100/100) | 30.00% (200/200) |
| E14x | `mosaic_lite_v1` | 300/300 | 11.33% | 27.00% | 16.00% | 28.33% | 44.33% | 21.00% (100/100) | 29.50% (200/200) |
| E4 | `collapse_obligation_ledger` | 400/400 | 9.25% | 22.75% | 16.25% | 36.00% | 52.25% | 26.00% (200/200) | 34.00% (200/200) |
| E4 | `e7_contrast` | 400/400 | 8.25% | 20.75% | 15.25% | 36.50% | 51.75% | 28.00% (200/200) | 31.50% (200/200) |
| E4 | `evidence_count_control` | 400/400 | 4.25% | 17.00% | 7.75% | 30.50% | 38.25% | 22.50% (200/200) | 17.00% (200/200) |
| E4 | `forest_evidence_integrator` | 400/400 | 10.25% | 24.25% | 17.25% | 34.75% | 52.00% | 25.00% (200/200) | 34.00% (200/200) |
| E4 | `pairwise_tournament` | 400/400 | 9.50% | 23.75% | 17.25% | 35.25% | 52.50% | 29.00% (200/200) | 35.00% (200/200) |
| E5 | `add_component5` | 166/200 | 55.00% | 58.50% | 60.00% | 11.50% | 71.50% | 60.00% (100/100) | 63.00% (100/100) |
| E5 | `add_parent5` | 166/200 | 48.00% | 52.50% | 54.00% | 17.50% | 71.50% | 50.00% (100/100) | 55.00% (100/100) |
| E5 | `add_sibling5` | 165/200 | 46.00% | 49.00% | 50.00% | 12.00% | 62.00% | 53.00% (100/100) | 50.00% (100/100) |
| E5 | `add_synonym5` | 165/200 | 54.50% | 56.00% | 63.50% | 11.00% | 74.50% | 57.00% (100/100) | 68.00% (100/100) |
| E5 | `add_unrelated5` | 166/200 | 53.00% | 54.50% | 57.00% | 11.00% | 68.00% | 55.00% (100/100) | 54.00% (100/100) |
| E5 | `base4` | 200/200 | 68.00% | 69.50% | 74.50% | 9.50% | 84.00% | 63.00% (100/100) | 81.00% (100/100) |
| E5 | `nested_width6` | 166/200 | 48.00% | 50.00% | 50.50% | 12.00% | 62.50% | 52.00% (100/100) | 49.00% (100/100) |
| E5 | `nested_width8` | 164/200 | 41.00% | 43.50% | 44.50% | 13.00% | 57.50% | 49.00% (100/100) | 40.00% (100/100) |
| E5 | `remove_non_gold3` | 200/200 | 76.00% | 77.00% | 79.00% | 7.50% | 86.50% | 69.00% (100/100) | 86.00% (100/100) |
| E6 | `flat_facts` | 255/300 | 1.00% | 12.33% | 19.33% | 20.00% | 39.33% | 34.67% (150/150) | 16.67% (150/150) |
| E6 | `raw_vignette` | 293/300 | 1.33% | 16.67% | 27.00% | 27.33% | 54.33% | 40.67% (150/150) | 23.33% (150/150) |
| E6 | `typed_event_graph` | 256/300 | 1.00% | 13.00% | 17.00% | 21.33% | 38.33% | 32.00% (150/150) | 19.33% (150/150) |
| E6x | `flat_facts_padded` | 255/300 | 1.00% | 12.33% | 19.33% | 20.00% | 39.33% | 34.67% (150/150) | 16.67% (150/150) |
| E6x | `flat_facts_unpadded` | 258/300 | 0.67% | 13.67% | 20.67% | 18.33% | 39.00% | 32.67% (150/150) | 21.33% (150/150) |
| E7b | `exact_synonym` | 399/400 | 7.00% | 24.50% | 16.00% | 40.75% | 56.75% | 25.69% (218/218) | 31.32% (182/182) |
| E7b | `legacy_substring` | 399/400 | 6.25% | 29.75% | 12.75% | 44.50% | 57.25% | 24.31% (218/218) | 30.77% (182/182) |
| E7b | `typed_relation` | 399/400 | 6.75% | 23.75% | 16.50% | 40.00% | 56.50% | 26.61% (218/218) | 32.97% (182/182) |
| E7c | `bounded_inheritance` | 297/299 | 6.35% | 25.08% | 16.39% | 41.47% | 57.86% | 25.15% (167/167) | 34.85% (132/132) |
| E7c | `directional_relation` | 297/299 | 6.35% | 23.41% | 16.72% | 39.80% | 56.52% | 23.95% (167/167) | 33.33% (132/132) |
| E7c | `exact_control` | 299/299 | 7.02% | 24.75% | 17.06% | 40.47% | 57.53% | 24.55% (167/167) | 34.09% (132/132) |
| E7c | `generic_non_equivalence` | 296/299 | 7.02% | 23.08% | 16.39% | 40.47% | 56.86% | 25.15% (167/167) | 32.58% (132/132) |
| E8 | `atemporal_hard_veto` | 193/220 | 8.18% | 18.64% | 14.09% | 28.64% | 42.73% | 21.82% (110/110) | 27.27% (110/110) |
| E8 | `time_scope_soft_invalid_time` | 125/220 | 6.82% | 12.73% | 11.36% | 17.73% | 29.09% | 10.00% (110/110) | 24.55% (110/110) |
| E8 | `time_scope_soft_legal_order` | 193/220 | 9.55% | 20.91% | 14.55% | 29.09% | 43.64% | 24.55% (110/110) | 26.36% (110/110) |
| E8 | `time_scope_soft_veto` | 193/220 | 10.00% | 20.91% | 15.91% | 28.64% | 44.55% | 20.00% (110/110) | 30.91% (110/110) |
| E9 | `duplicate_anchor` | 399/400 | 7.25% | 23.00% | 11.75% | 37.50% | 49.25% | 29.50% (200/200) | 30.00% (200/200) |
| E9 | `real_views` | 400/400 | 9.50% | 25.00% | 15.25% | 37.25% | 52.50% | 29.00% (200/200) | 31.50% (200/200) |
| E9 | `role_rotated` | 400/400 | 9.00% | 24.00% | 15.00% | 37.00% | 52.00% | 30.00% (200/200) | 31.00% (200/200) |
| E9 | `single_anchor` | 400/400 | 7.25% | 22.25% | 12.00% | 36.50% | 48.50% | 28.00% (200/200) | 29.00% (200/200) |
| RCR3 | `compact4_true3gen` | 175/300 | 2.67% | 9.33% | 4.33% | 18.00% | 22.33% | 11.33% (150/150) | 10.67% (150/150) |
| RCR3 | `lite3_safe` | 296/300 | 5.33% | 16.67% | 7.33% | 36.00% | 43.33% | 24.67% (150/150) | 20.00% (150/150) |
| RCR3 | `rcr3_default` | 262/300 | 2.33% | 10.00% | 4.33% | 32.00% | 36.33% | 26.67% (150/150) | 12.00% (150/150) |

## Multiplicity-controlled clinical contrasts

Only ALL-scope canonical clinical contrasts with Holm-adjusted `q<.05` are listed here. Family-specific estimates and all null contrasts are preserved in `final/paired_contrasts.csv`.

| Experiment | Family | Contrast | Endpoint | Δ pp | Gain/loss | McNemar p | Holm q |
|---|---|---|---|---:|---:|---:|---:|
| E1 | `primary` | `options_vs_clean_fixed__ab02_flat` | `clinical_complete` | 39.50 | 88/9 | 2.00379e-17 | 1.40265e-16 |
| E1 | `primary` | `options_vs_clean_fixed__aphhm_hierarchical` | `clinical_complete` | 41.50 | 89/6 | 4.69719e-20 | 3.75775e-19 |
| E1 | `primary` | `options_vs_clean_shuffled__ab02_flat` | `clinical_complete` | 31.00 | 71/9 | 4.37398e-13 | 2.62439e-12 |
| E1 | `primary` | `options_vs_clean_shuffled__aphhm_hierarchical` | `clinical_complete` | 28.00 | 67/11 | 6.11831e-11 | 3.05916e-10 |
| E1 | `primary` | `shuffle_vs_fixed_options__aphhm_hierarchical` | `clinical_complete` | -11.00 | 17/39 | 0.00456153 | 0.0182461 |
| E1 | `primary` | `options_vs_clean_fixed__ab02_flat` | `complete_or_compatible_partial` | 26.50 | 60/7 | 1.32804e-11 | 1.06243e-10 |
| E1 | `primary` | `options_vs_clean_fixed__aphhm_hierarchical` | `complete_or_compatible_partial` | 27.00 | 67/13 | 6.41514e-10 | 4.4906e-09 |
| E1 | `primary` | `options_vs_clean_shuffled__ab02_flat` | `complete_or_compatible_partial` | 21.00 | 54/12 | 1.69449e-07 | 1.0167e-06 |
| E1 | `primary` | `options_vs_clean_shuffled__aphhm_hierarchical` | `complete_or_compatible_partial` | 20.00 | 59/19 | 6.41506e-06 | 3.20753e-05 |
| E10 | `primary` | `history_effect_rrf` | `complete_or_compatible_partial` | 6.00 | 34/10 | 0.000388131 | 0.00155252 |
| E10 | `primary` | `supervisor_effect_isolated` | `complete_or_compatible_partial` | 4.25 | 22/5 | 0.00151372 | 0.00454116 |
| E11 | `primary` | `refine_effect_with_hard_negative_context` | `complete_or_compatible_partial` | 3.50 | 17/3 | 0.00257683 | 0.015461 |
| E11 | `primary` | `refine_effect_with_retrieval_off` | `complete_or_compatible_partial` | 4.25 | 19/2 | 0.000221252 | 0.00154877 |
| E12 | `factorial39` | `pairwise_vs_first_raw_k10` | `complete_or_compatible_partial` | 12.33 | 51/14 | 4.47522e-06 | 0.000174534 |
| E12 | `factorial39` | `pairwise_vs_first_raw_k5` | `complete_or_compatible_partial` | 9.67 | 48/19 | 0.000521613 | 0.0192997 |
| E12 | `factorial39` | `raw_vs_s1_k10_pairwise` | `complete_or_compatible_partial` | 8.67 | 38/12 | 0.000305864 | 0.0116228 |
| E4 | `primary` | `collapse_obligation_ledger_vs_evidence_count_control` | `clinical_complete` | 8.50 | 42/8 | 1.16356e-06 | 9.30845e-06 |
| E4 | `primary` | `e7_contrast_vs_evidence_count_control` | `clinical_complete` | 7.50 | 40/10 | 2.38613e-05 | 0.000167029 |
| E4 | `primary` | `forest_evidence_integrator_vs_evidence_count_control` | `clinical_complete` | 9.50 | 46/8 | 1.38434e-07 | 1.2459e-06 |
| E4 | `primary` | `pairwise_tournament_vs_evidence_count_control` | `clinical_complete` | 9.50 | 45/7 | 6.97381e-08 | 6.97381e-07 |
| E4 | `primary` | `collapse_obligation_ledger_vs_evidence_count_control` | `complete_or_compatible_partial` | 14.00 | 82/26 | 6.1413e-08 | 5.52717e-07 |
| E4 | `primary` | `e7_contrast_vs_evidence_count_control` | `complete_or_compatible_partial` | 13.50 | 78/24 | 7.67943e-08 | 6.14354e-07 |
| E4 | `primary` | `forest_evidence_integrator_vs_evidence_count_control` | `complete_or_compatible_partial` | 13.75 | 81/26 | 9.37451e-08 | 6.56216e-07 |
| E4 | `primary` | `pairwise_tournament_vs_evidence_count_control` | `complete_or_compatible_partial` | 14.25 | 84/27 | 5.46198e-08 | 5.46198e-07 |
| E5 | `primary` | `add_component5_vs_base4` | `clinical_complete` | -14.50 | 12/41 | 8.17133e-05 | 0.00024514 |
| E5 | `primary` | `add_parent5_vs_base4` | `clinical_complete` | -20.50 | 9/50 | 5.26483e-08 | 2.63242e-07 |
| E5 | `primary` | `add_sibling5_vs_base4` | `clinical_complete` | -24.50 | 6/55 | 5.38061e-11 | 3.76643e-10 |
| E5 | `primary` | `add_synonym5_vs_base4` | `clinical_complete` | -11.00 | 17/39 | 0.00456153 | 0.00912307 |
| E5 | `primary` | `add_unrelated5_vs_base4` | `clinical_complete` | -17.50 | 10/45 | 2.05726e-06 | 8.22906e-06 |
| E5 | `primary` | `nested_width6_vs_base4` | `clinical_complete` | -24.00 | 6/54 | 9.72296e-11 | 5.83378e-10 |
| E5 | `primary` | `nested_width8_vs_base4` | `clinical_complete` | -30.00 | 5/65 | 2.21535e-14 | 1.77228e-13 |
| E5 | `primary` | `add_component5_vs_base4` | `complete_or_compatible_partial` | -12.50 | 10/35 | 0.000247088 | 0.000988351 |
| E5 | `primary` | `add_parent5_vs_base4` | `complete_or_compatible_partial` | -12.50 | 10/35 | 0.000247088 | 0.000988351 |
| E5 | `primary` | `add_sibling5_vs_base4` | `complete_or_compatible_partial` | -22.00 | 4/48 | 1.30653e-10 | 9.1457e-10 |
| E5 | `primary` | `add_synonym5_vs_base4` | `complete_or_compatible_partial` | -9.50 | 13/32 | 0.00660882 | 0.0132176 |
| E5 | `primary` | `add_unrelated5_vs_base4` | `complete_or_compatible_partial` | -16.00 | 6/38 | 9.43038e-07 | 4.71519e-06 |
| E5 | `primary` | `nested_width6_vs_base4` | `complete_or_compatible_partial` | -21.50 | 4/47 | 2.41631e-10 | 1.44978e-09 |
| E5 | `primary` | `nested_width8_vs_base4` | `complete_or_compatible_partial` | -26.50 | 1/54 | 3.10862e-15 | 2.4869e-14 |
| E5 | `width_secondary` | `width8_vs_width6` | `clinical_complete` | -6.00 | 6/18 | 0.0226558 | 0.0226558 |
| E6 | `primary` | `flat_vs_raw` | `clinical_complete` | -7.67 | 23/46 | 0.00762052 | 0.015241 |
| E6 | `primary` | `graph_vs_raw` | `clinical_complete` | -10.00 | 13/43 | 7.33322e-05 | 0.000219997 |
| E6 | `primary` | `flat_vs_raw` | `complete_or_compatible_partial` | -15.00 | 23/68 | 2.52215e-06 | 5.04431e-06 |
| E6 | `primary` | `graph_vs_raw` | `complete_or_compatible_partial` | -16.00 | 16/64 | 5.87133e-08 | 1.7614e-07 |
| E7b | `primary` | `exact_vs_legacy` | `clinical_complete` | 3.25 | 16/3 | 0.00442505 | 0.0088501 |
| E8 | `primary` | `invalid_vs_soft` | `clinical_complete` | -4.55 | 2/12 | 0.0129395 | 0.0388184 |
| E8 | `primary` | `invalid_vs_soft` | `complete_or_compatible_partial` | -15.45 | 3/37 | 1.9465e-08 | 5.8395e-08 |
| E9 | `primary` | `real_vs_duplicate` | `clinical_complete` | 3.50 | 17/3 | 0.00257683 | 0.0103073 |
| E9 | `primary` | `real_vs_single` | `clinical_complete` | 3.25 | 16/3 | 0.00442505 | 0.0132751 |
| RCR3 | `primary` | `compact4_vs_rcr3` | `complete_or_compatible_partial` | -14.00 | 33/75 | 6.55037e-05 | 0.000131007 |
| RCR3 | `primary` | `rcr3_vs_lite3_same_3call_budget` | `complete_or_compatible_partial` | -7.00 | 33/54 | 0.0314181 | 0.0314181 |
| RCR3 | `primary` | `third_generator_marginal_utility` | `complete_or_compatible_partial` | -21.00 | 9/72 | 2.45574e-13 | 7.36723e-13 |

## Multiplicity-controlled task-interface contrasts

The completed namespace adds family-specific task inference. These are DA mapper or MCR semantic-judge effects, not clinical-complete effects and not a poolable ALL endpoint.

| Experiment | Scope | Family | Contrast | Δ pp | Gain/loss | Holm q |
|---|---|---|---|---:|---:|---:|
| E1 | DA | `primary` | `options_vs_clean_fixed__ab02_flat` | 26.00 | 35/9 | 0.000636268 |
| E1 | DA | `primary` | `options_vs_clean_fixed__aphhm_hierarchical` | 34.00 | 40/6 | 2.48224e-06 |
| E1 | DA | `primary` | `options_vs_clean_shuffled__ab02_flat` | 32.00 | 38/6 | 6.60126e-06 |
| E1 | DA | `primary` | `options_vs_clean_shuffled__aphhm_hierarchical` | 22.00 | 33/11 | 0.00630017 |
| E1 | MCR | `primary` | `options_vs_clean_fixed__ab02_flat` | 28.00 | 31/3 | 6.1281e-06 |
| E1 | MCR | `primary` | `options_vs_clean_fixed__aphhm_hierarchical` | 28.00 | 32/4 | 1.3591e-05 |
| E1 | MCR | `primary` | `options_vs_clean_shuffled__ab02_flat` | 26.00 | 30/4 | 3.69893e-05 |
| E1 | MCR | `primary` | `options_vs_clean_shuffled__aphhm_hierarchical` | 23.00 | 30/7 | 0.000955382 |
| E12 | MCR | `factorial39` | `pairwise_vs_first_raw_k10` | 10.00 | 16/1 | 0.0107117 |
| E12 | MCR | `factorial39` | `pairwise_vs_first_raw_k5` | 9.33 | 15/1 | 0.0197144 |
| E4 | MCR | `primary` | `collapse_obligation_ledger_vs_evidence_count_control` | 17.00 | 40/6 | 2.79252e-06 |
| E4 | MCR | `primary` | `e7_contrast_vs_evidence_count_control` | 14.50 | 36/7 | 6.27413e-05 |
| E4 | MCR | `primary` | `forest_evidence_integrator_vs_evidence_count_control` | 17.00 | 41/7 | 4.99233e-06 |
| E4 | MCR | `primary` | `pairwise_tournament_vs_evidence_count_control` | 18.00 | 42/6 | 1.00875e-06 |
| E5 | MCR | `primary` | `add_component5_vs_base4` | -18.00 | 7/25 | 0.0063072 |
| E5 | MCR | `primary` | `add_parent5_vs_base4` | -26.00 | 6/32 | 9.73702e-05 |
| E5 | MCR | `primary` | `add_sibling5_vs_base4` | -31.00 | 3/34 | 7.39878e-07 |
| E5 | MCR | `primary` | `add_unrelated5_vs_base4` | -27.00 | 3/30 | 7.00587e-06 |
| E5 | MCR | `primary` | `nested_width6_vs_base4` | -32.00 | 3/35 | 4.67451e-07 |
| E5 | MCR | `primary` | `nested_width8_vs_base4` | -41.00 | 1/42 | 8.00355e-11 |
| E5 | MCR | `width_secondary` | `width8_vs_width6` | -9.00 | 4/13 | 0.0490417 |
| E8 | DA | `primary` | `invalid_vs_soft` | -10.00 | 0/11 | 0.00292969 |
| RCR3 | DA | `primary` | `compact4_vs_rcr3` | -15.33 | 9/32 | 0.000861714 |
| RCR3 | DA | `primary` | `third_generator_marginal_utility` | -13.33 | 1/21 | 3.29018e-05 |
| RCR3 | MCR | `primary` | `rcr3_vs_lite3_same_3call_budget` | -8.00 | 5/17 | 0.0338011 |
| RCR3 | MCR | `primary` | `third_generator_marginal_utility` | -9.33 | 3/17 | 0.00773048 |

## Interpretation boundary

This replay can update arm-level Top-1 clinical and family-specific task conclusions. It cannot by itself update candidate-registry exposure, selector capture, or trajectory-level mechanisms where non-winning candidates still use old proxy labels. Those mechanisms remain hypotheses until a separate full-pool relation migration is completed.

Reproduction:

```bash
python -m analysis.mechanism_v2.endpoint_migration freeze
python -m analysis.mechanism_v2.endpoint_migration run-reviewer --reviewer-id reviewer_a --model google/gemini-2.5-flash
python -m analysis.mechanism_v2.endpoint_migration compile-panel
python -m analysis.mechanism_v2.endpoint_migration run-task
python -m analysis.mechanism_v2.endpoint_migration finalize --allow-model-only
python -m analysis.mechanism_v2.endpoint_migration render-report
```
