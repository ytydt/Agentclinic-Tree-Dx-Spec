# Canonical endpoint migration: 79-arm exhaustive Top-1 replay

## Decision

The 79-arm metric-migration gap is closed at the exhaustive blinded three-reviewer model-panel level: every intended row has an ITA disposition and every served Top-1 has canonical clinical-complete, compatible-partial, and C∪P status. The strict human-root capability allowlist is **not** expanded: E2 remains the only human-root-owned full census, while the 79 migrated arms are a calibrated model-panel sensitivity census.

The fresh task replay stopped when the authorized external API returned an insufficient-credit error. Cache-complete task rows are reported only with their evaluation coverage; historical task values were not copied, failed rows were not imputed, and no partial-cache task contrast is inferred.

Historical proxy, targeted, binary-acceptable, safe-exact, and old task fields remain in their source reports as mechanism/provenance evidence; they are not renamed as canonical clinical outcomes.

## Coverage and provenance

| Quantity | Value |
|---|---:|
| Registered target arms | 79 |
| Intention rows | 24,076 |
| Served Top-1 rows | 23,035 |
| Technical failures retained in ITA | 1,041 |
| Unique case-prediction relations | 5,344 |
| Exact-normalized E2 root relations reused | 1,693 |
| Newly blinded relations | 3,400 |
| Hidden E2 sentinels | 1,507 |
| Registered fresh task payloads | 5,832 |
| Fresh task payloads completed | 3,337 |
| Fresh task payloads not evaluable | 2,495 |

No credential is present in a prompt, cache identity, response artifact, manifest, or report. Clinical cards hide case key, experiment, arm, old endpoint, proxy status, safe/legacy/task status, and sentinel identity.
`artifact_manifest.json` closes every migration artifact with byte count and SHA-256.

## Embedded calibration

| Reviewer | Model | Fine-label accuracy | Complete accuracy | Complete precision | Complete recall | C∪P accuracy | C∪P precision | C∪P recall |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| reviewer_a | `google/gemini-2.5-flash` | 68.35% | 96.62% | 79.79% | 70.09% | 87.79% | 83.31% | 91.75% |
| reviewer_b | `anthropic/claude-sonnet-4.6` | 72.59% | 97.54% | 85.71% | 78.50% | 91.24% | 88.77% | 92.62% |
| reviewer_c | `openai/gpt-5.6` | 74.65% | 98.08% | 92.39% | 79.44% | 93.17% | 94.82% | 90.01% |

The sentinels calibrate measurement error; they do not convert model decisions into human root decisions. Fine-label error is materially larger than the binary complete boundary error, so C/P/X/M/N counts must retain their model-panel provenance.

## All-arm canonical endpoint table

Clinical rates are ITA. Task is shown separately for DA and MCR as `observed rate (evaluable/ITA)`; incomplete task cells are descriptive only because cache completion is non-random.

| Experiment | Arm | Served/ITA | Safe exact | Legacy chain | Clinical complete | Compatible partial | C∪P | DA task | MCR task |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| E1 | `ab02_flat__clean_fixed` | 200/200 | 6.50% | 23.00% | 25.00% | 28.00% | 53.00% | 33.33% (69/100) | 23.91% (46/100) |
| E1 | `ab02_flat__clean_shuffled_blocks` | 199/200 | 5.50% | 19.50% | 28.50% | 24.50% | 53.00% | 33.82% (68/100) | 26.67% (45/100) |
| E1 | `ab02_flat__options_fixed` | 199/200 | 46.50% | 62.50% | 64.00% | 16.00% | 80.00% | 63.41% (82/100) | 44.44% (54/100) |
| E1 | `ab02_flat__options_shuffled_blocks` | 199/200 | 37.00% | 56.00% | 60.00% | 15.50% | 75.50% | 61.04% (77/100) | 45.28% (53/100) |
| E1 | `aphhm_hierarchical__clean_fixed` | 189/200 | 8.00% | 22.00% | 19.00% | 32.50% | 51.50% | 29.73% (74/100) | 30.36% (56/100) |
| E1 | `aphhm_hierarchical__clean_shuffled_blocks` | 189/200 | 8.50% | 24.50% | 21.50% | 29.00% | 50.50% | 27.87% (61/100) | 21.43% (56/100) |
| E1 | `aphhm_hierarchical__options_fixed` | 187/200 | 47.00% | 58.50% | 61.00% | 17.50% | 78.50% | 70.51% (78/100) | 48.39% (62/100) |
| E1 | `aphhm_hierarchical__options_shuffled_blocks` | 176/200 | 29.00% | 45.50% | 50.00% | 21.00% | 71.00% | 52.70% (74/100) | 43.10% (58/100) |
| E10 | `isolated_rrf` | 400/400 | 5.25% | 20.00% | 9.00% | 28.75% | 37.75% | 21.97% (132/200) | 25.23% (111/200) |
| E10 | `isolated_supervisor` | 400/400 | 5.50% | 21.50% | 9.25% | 32.75% | 42.00% | 20.59% (136/200) | 28.18% (110/200) |
| E10 | `sequential_rrf` | 400/400 | 6.50% | 22.50% | 10.25% | 33.50% | 43.75% | 21.71% (129/200) | 30.56% (108/200) |
| E10 | `sequential_supervisor` | 400/400 | 6.50% | 22.00% | 11.00% | 33.50% | 44.50% | 20.93% (129/200) | 31.13% (106/200) |
| E11 | `hard_negative_refine_off` | 400/400 | 6.75% | 19.50% | 12.25% | 31.25% | 43.50% | 21.95% (123/200) | 31.78% (107/200) |
| E11 | `hard_negative_refine_on` | 400/400 | 6.75% | 18.50% | 12.75% | 34.25% | 47.00% | 25.00% (120/200) | 35.24% (105/200) |
| E11 | `off_refine_off` | 400/400 | 7.25% | 19.00% | 13.25% | 30.50% | 43.75% | 19.84% (126/200) | 33.33% (99/200) |
| E11 | `off_refine_on` | 400/400 | 6.75% | 19.00% | 13.25% | 34.75% | 48.00% | 22.83% (127/200) | 34.62% (104/200) |
| E11 | `random_refine_off` | 400/400 | 6.00% | 19.25% | 12.00% | 32.25% | 44.25% | 22.58% (124/200) | 31.48% (108/200) |
| E11 | `random_refine_on` | 400/400 | 6.25% | 18.75% | 12.75% | 33.50% | 46.25% | 24.19% (124/200) | 35.24% (105/200) |
| E11 | `relevant_refine_off` | 400/400 | 6.00% | 19.50% | 12.00% | 31.75% | 43.75% | 20.69% (116/200) | 31.00% (100/200) |
| E11 | `relevant_refine_on` | 400/400 | 5.75% | 19.25% | 12.25% | 33.25% | 45.50% | 22.50% (120/200) | 35.42% (96/200) |
| E12 | `graph_k10_first` | 300/300 | 7.00% | 19.00% | 9.67% | 29.33% | 39.00% | 19.57% (92/150) | 26.32% (76/150) |
| E12 | `graph_k10_pairwise` | 256/300 | 6.67% | 17.33% | 10.00% | 29.00% | 39.00% | 19.17% (120/150) | 22.09% (86/150) |
| E12 | `graph_k10_pointwise` | 252/300 | 6.33% | 16.33% | 9.33% | 27.33% | 36.67% | 17.24% (116/150) | 18.18% (88/150) |
| E12 | `graph_k5_first` | 300/300 | 7.00% | 19.00% | 9.67% | 29.33% | 39.00% | 19.57% (92/150) | 26.32% (76/150) |
| E12 | `graph_k5_pairwise` | 258/300 | 7.00% | 18.00% | 9.67% | 30.00% | 39.67% | 18.26% (115/150) | 23.81% (84/150) |
| E12 | `graph_k5_pointwise` | 257/300 | 7.00% | 17.67% | 10.33% | 28.33% | 38.67% | 20.35% (113/150) | 23.53% (85/150) |
| E12 | `raw_depth1_k10_pairwise` | 299/300 | 8.33% | 23.00% | 12.67% | 36.67% | 49.33% | 24.76% (105/150) | 31.08% (74/150) |
| E12 | `raw_depth2_k10_pairwise` | 300/300 | 8.33% | 23.00% | 13.00% | 36.33% | 49.33% | 23.00% (100/150) | 33.33% (72/150) |
| E12 | `raw_k10_first` | 300/300 | 7.00% | 19.00% | 9.67% | 29.33% | 39.00% | 19.57% (92/150) | 26.32% (76/150) |
| E12 | `raw_k10_pairwise` | 298/300 | 8.67% | 23.67% | 13.67% | 37.67% | 51.33% | 22.64% (106/150) | 31.08% (74/150) |
| E12 | `raw_k10_pointwise` | 298/300 | 8.33% | 23.33% | 13.00% | 34.33% | 47.33% | 27.93% (111/150) | 28.57% (70/150) |
| E12 | `raw_k5_first` | 300/300 | 7.00% | 19.00% | 9.67% | 29.33% | 39.00% | 19.57% (92/150) | 26.32% (76/150) |
| E12 | `raw_k5_pairwise` | 300/300 | 8.33% | 22.33% | 13.67% | 35.00% | 48.67% | 24.55% (110/150) | 29.73% (74/150) |
| E12 | `raw_k5_pointwise` | 299/300 | 8.00% | 20.00% | 13.33% | 34.00% | 47.33% | 25.24% (103/150) | 26.92% (78/150) |
| E12 | `s1_k10_first` | 300/300 | 7.00% | 19.00% | 9.67% | 29.33% | 39.00% | 19.57% (92/150) | 26.32% (76/150) |
| E12 | `s1_k10_pairwise` | 299/300 | 6.67% | 17.33% | 11.00% | 31.67% | 42.67% | 21.36% (103/150) | 29.73% (74/150) |
| E12 | `s1_k10_pointwise` | 299/300 | 5.67% | 15.33% | 9.33% | 32.00% | 41.33% | 20.19% (104/150) | 24.29% (70/150) |
| E12 | `s1_k5_first` | 300/300 | 7.00% | 19.00% | 9.67% | 29.33% | 39.00% | 19.57% (92/150) | 26.32% (76/150) |
| E12 | `s1_k5_pairwise` | 298/300 | 7.00% | 19.00% | 10.67% | 33.00% | 43.67% | 23.58% (106/150) | 27.54% (69/150) |
| E12 | `s1_k5_pointwise` | 298/300 | 5.67% | 17.67% | 9.67% | 33.00% | 42.67% | 22.00% (100/150) | 22.22% (72/150) |
| E14x | `mosaic_adaptive4v2_v1` | 300/300 | 10.33% | 24.00% | 16.33% | 29.33% | 45.67% | 13.43% (67/100) | 28.83% (111/200) |
| E14x | `mosaic_lite_v1` | 300/300 | 11.33% | 27.00% | 16.00% | 28.33% | 44.33% | 19.70% (66/100) | 28.44% (109/200) |
| E4 | `collapse_obligation_ledger` | 400/400 | 9.25% | 22.75% | 16.25% | 35.75% | 52.00% | 23.19% (138/200) | 34.34% (99/200) |
| E4 | `e7_contrast` | 400/400 | 8.25% | 20.75% | 15.25% | 36.50% | 51.75% | 26.76% (142/200) | 30.77% (104/200) |
| E4 | `evidence_count_control` | 400/400 | 4.25% | 17.00% | 7.75% | 30.50% | 38.25% | 21.62% (111/200) | 21.15% (104/200) |
| E4 | `forest_evidence_integrator` | 400/400 | 10.25% | 24.25% | 17.25% | 34.50% | 51.75% | 24.11% (141/200) | 36.73% (98/200) |
| E4 | `pairwise_tournament` | 400/400 | 9.50% | 23.75% | 17.25% | 35.25% | 52.50% | 27.66% (141/200) | 33.33% (108/200) |
| E5 | `add_component5` | 166/200 | 55.00% | 58.50% | 60.00% | 11.50% | 71.50% | 60.49% (81/100) | 50.00% (62/100) |
| E5 | `add_parent5` | 166/200 | 48.00% | 52.50% | 54.00% | 17.50% | 71.50% | 48.19% (83/100) | 38.71% (62/100) |
| E5 | `add_sibling5` | 165/200 | 46.00% | 49.00% | 50.00% | 12.00% | 62.00% | 53.16% (79/100) | 37.29% (59/100) |
| E5 | `add_synonym5` | 165/200 | 54.50% | 56.00% | 63.50% | 11.00% | 74.50% | 58.44% (77/100) | 54.69% (64/100) |
| E5 | `add_unrelated5` | 166/200 | 53.00% | 54.50% | 57.00% | 11.00% | 68.00% | 57.32% (82/100) | 42.62% (61/100) |
| E5 | `base4` | 200/200 | 68.00% | 69.50% | 74.00% | 9.50% | 83.50% | 67.09% (79/100) | 77.59% (58/100) |
| E5 | `nested_width6` | 166/200 | 48.00% | 50.00% | 50.50% | 12.00% | 62.50% | 51.85% (81/100) | 36.36% (66/100) |
| E5 | `nested_width8` | 164/200 | 41.00% | 43.50% | 44.50% | 13.00% | 57.50% | 46.15% (78/100) | 30.65% (62/100) |
| E5 | `remove_non_gold3` | 200/200 | 76.00% | 77.00% | 79.00% | 7.50% | 86.50% | 72.29% (83/100) | 87.27% (55/100) |
| E6 | `flat_facts` | 255/300 | 1.00% | 12.33% | 19.33% | 20.33% | 39.67% | 31.00% (100/150) | 12.50% (80/150) |
| E6 | `raw_vignette` | 293/300 | 1.33% | 16.67% | 27.67% | 26.67% | 54.33% | 42.25% (71/150) | 20.99% (81/150) |
| E6 | `typed_event_graph` | 256/300 | 1.00% | 13.00% | 17.33% | 21.33% | 38.67% | 30.39% (102/150) | 14.77% (88/150) |
| E6x | `flat_facts_padded` | 255/300 | 1.00% | 12.33% | 19.33% | 20.33% | 39.67% | 31.00% (100/150) | 12.50% (80/150) |
| E6x | `flat_facts_unpadded` | 258/300 | 0.67% | 13.67% | 20.67% | 18.33% | 39.00% | 29.79% (94/150) | 18.07% (83/150) |
| E7b | `exact_synonym` | 399/400 | 7.00% | 24.50% | 16.00% | 40.50% | 56.50% | 22.22% (153/218) | 30.11% (93/182) |
| E7b | `legacy_substring` | 399/400 | 6.25% | 29.75% | 12.75% | 44.00% | 56.75% | 24.16% (149/218) | 30.00% (90/182) |
| E7b | `typed_relation` | 399/400 | 6.75% | 23.75% | 16.50% | 39.50% | 56.00% | 23.97% (146/218) | 33.33% (90/182) |
| E7c | `bounded_inheritance` | 297/299 | 6.35% | 25.08% | 16.39% | 41.47% | 57.86% | 17.54% (114/167) | 36.92% (65/132) |
| E7c | `directional_relation` | 297/299 | 6.35% | 23.41% | 16.72% | 39.80% | 56.52% | 19.83% (121/167) | 33.82% (68/132) |
| E7c | `exact_control` | 299/299 | 7.02% | 24.75% | 17.06% | 40.13% | 57.19% | 20.17% (119/167) | 33.85% (65/132) |
| E7c | `generic_non_equivalence` | 296/299 | 7.02% | 23.08% | 16.39% | 40.47% | 56.86% | 18.26% (115/167) | 30.88% (68/132) |
| E8 | `atemporal_hard_veto` | 184/220 | 8.18% | 18.64% | 14.09% | 27.73% | 41.82% | 20.00% (80/110) | 20.90% (67/110) |
| E8 | `time_scope_soft_invalid_time` | 125/220 | 6.82% | 12.73% | 11.36% | 17.73% | 29.09% | 9.68% (93/110) | 15.38% (78/110) |
| E8 | `time_scope_soft_legal_order` | 192/220 | 9.55% | 20.91% | 14.09% | 29.09% | 43.18% | 23.17% (82/110) | 23.53% (68/110) |
| E8 | `time_scope_soft_veto` | 192/220 | 10.00% | 20.91% | 15.91% | 28.18% | 44.09% | 19.05% (84/110) | 29.23% (65/110) |
| E9 | `duplicate_anchor` | 399/400 | 7.25% | 23.00% | 11.75% | 37.25% | 49.00% | 25.00% (128/200) | 31.37% (102/200) |
| E9 | `real_views` | 400/400 | 9.50% | 25.00% | 15.25% | 37.00% | 52.25% | 25.42% (118/200) | 34.26% (108/200) |
| E9 | `role_rotated` | 400/400 | 9.00% | 24.00% | 15.00% | 36.75% | 51.75% | 26.23% (122/200) | 33.33% (108/200) |
| E9 | `single_anchor` | 400/400 | 7.25% | 22.25% | 12.00% | 36.25% | 48.25% | 23.39% (124/200) | 29.36% (109/200) |
| RCR3 | `compact4_true3gen` | 175/300 | 2.67% | 9.33% | 4.33% | 17.67% | 22.00% | 9.17% (120/150) | 11.01% (109/150) |
| RCR3 | `lite3_safe` | 296/300 | 5.33% | 16.67% | 7.33% | 36.00% | 43.33% | 23.08% (91/150) | 21.69% (83/150) |
| RCR3 | `rcr3_default` | 262/300 | 2.33% | 10.00% | 4.33% | 31.67% | 36.00% | 19.61% (102/150) | 14.63% (82/150) |

## Multiplicity-controlled clinical contrasts

Only ALL-scope canonical clinical contrasts with Holm-adjusted `q<.05` are listed here. Family-specific estimates and all null contrasts are preserved in `final/paired_contrasts.csv`.

| Experiment | Family | Contrast | Endpoint | Δ pp | Gain/loss | McNemar p | Holm q |
|---|---|---|---|---:|---:|---:|---:|
| E1 | `primary` | `options_vs_clean_fixed__ab02_flat` | `clinical_complete` | 39.00 | 87/9 | 3.64026e-17 | 2.54818e-16 |
| E1 | `primary` | `options_vs_clean_fixed__aphhm_hierarchical` | `clinical_complete` | 42.00 | 90/6 | 2.50326e-20 | 2.0026e-19 |
| E1 | `primary` | `options_vs_clean_shuffled__ab02_flat` | `clinical_complete` | 31.50 | 72/9 | 2.45574e-13 | 1.47345e-12 |
| E1 | `primary` | `options_vs_clean_shuffled__aphhm_hierarchical` | `clinical_complete` | 28.50 | 68/11 | 3.54456e-11 | 1.77228e-10 |
| E1 | `primary` | `shuffle_vs_fixed_options__aphhm_hierarchical` | `clinical_complete` | -11.00 | 17/39 | 0.00456153 | 0.0182461 |
| E1 | `primary` | `options_vs_clean_fixed__ab02_flat` | `complete_or_compatible_partial` | 27.00 | 62/8 | 1.82677e-11 | 1.46141e-10 |
| E1 | `primary` | `options_vs_clean_fixed__aphhm_hierarchical` | `complete_or_compatible_partial` | 27.00 | 67/13 | 6.41514e-10 | 4.4906e-09 |
| E1 | `primary` | `options_vs_clean_shuffled__ab02_flat` | `complete_or_compatible_partial` | 22.50 | 57/12 | 3.74225e-08 | 2.24535e-07 |
| E1 | `primary` | `options_vs_clean_shuffled__aphhm_hierarchical` | `complete_or_compatible_partial` | 20.50 | 60/19 | 4.19404e-06 | 2.09702e-05 |
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
| E4 | `primary` | `collapse_obligation_ledger_vs_evidence_count_control` | `complete_or_compatible_partial` | 13.75 | 81/26 | 9.37451e-08 | 7.49961e-07 |
| E4 | `primary` | `e7_contrast_vs_evidence_count_control` | `complete_or_compatible_partial` | 13.50 | 78/24 | 7.67943e-08 | 6.91149e-07 |
| E4 | `primary` | `forest_evidence_integrator_vs_evidence_count_control` | `complete_or_compatible_partial` | 13.50 | 80/26 | 1.42696e-07 | 9.98875e-07 |
| E4 | `primary` | `pairwise_tournament_vs_evidence_count_control` | `complete_or_compatible_partial` | 14.25 | 84/27 | 5.46198e-08 | 5.46198e-07 |
| E5 | `primary` | `add_component5_vs_base4` | `clinical_complete` | -14.00 | 12/40 | 0.000127539 | 0.000382616 |
| E5 | `primary` | `add_parent5_vs_base4` | `clinical_complete` | -20.00 | 9/49 | 8.9594e-08 | 4.4797e-07 |
| E5 | `primary` | `add_sibling5_vs_base4` | `clinical_complete` | -24.00 | 6/54 | 9.72296e-11 | 6.80607e-10 |
| E5 | `primary` | `add_synonym5_vs_base4` | `clinical_complete` | -10.50 | 17/38 | 0.0064558 | 0.0129116 |
| E5 | `primary` | `add_unrelated5_vs_base4` | `clinical_complete` | -17.00 | 10/44 | 3.38569e-06 | 1.35427e-05 |
| E5 | `primary` | `nested_width6_vs_base4` | `clinical_complete` | -23.50 | 6/53 | 1.75392e-10 | 1.05235e-09 |
| E5 | `primary` | `nested_width8_vs_base4` | `clinical_complete` | -29.50 | 5/64 | 4.11923e-14 | 3.29538e-13 |
| E5 | `primary` | `add_component5_vs_base4` | `complete_or_compatible_partial` | -12.00 | 10/34 | 0.000388131 | 0.00155252 |
| E5 | `primary` | `add_parent5_vs_base4` | `complete_or_compatible_partial` | -12.00 | 10/34 | 0.000388131 | 0.00155252 |
| E5 | `primary` | `add_sibling5_vs_base4` | `complete_or_compatible_partial` | -21.50 | 4/47 | 2.41631e-10 | 1.69142e-09 |
| E5 | `primary` | `add_synonym5_vs_base4` | `complete_or_compatible_partial` | -9.00 | 13/31 | 0.00955988 | 0.0191198 |
| E5 | `primary` | `add_unrelated5_vs_base4` | `complete_or_compatible_partial` | -15.50 | 6/37 | 1.63612e-06 | 8.18062e-06 |
| E5 | `primary` | `nested_width6_vs_base4` | `complete_or_compatible_partial` | -21.00 | 4/46 | 4.46178e-10 | 2.67707e-09 |
| E5 | `primary` | `nested_width8_vs_base4` | `complete_or_compatible_partial` | -26.00 | 1/53 | 6.10623e-15 | 4.88498e-14 |
| E5 | `width_secondary` | `width8_vs_width6` | `clinical_complete` | -6.00 | 6/18 | 0.0226558 | 0.0226558 |
| E6 | `primary` | `flat_vs_raw` | `clinical_complete` | -8.33 | 22/47 | 0.00354481 | 0.00708963 |
| E6 | `primary` | `graph_vs_raw` | `clinical_complete` | -10.33 | 13/44 | 4.71044e-05 | 0.000141313 |
| E6 | `primary` | `flat_vs_raw` | `complete_or_compatible_partial` | -14.67 | 24/68 | 4.93535e-06 | 9.8707e-06 |
| E6 | `primary` | `graph_vs_raw` | `complete_or_compatible_partial` | -15.67 | 18/65 | 2.10545e-07 | 6.31636e-07 |
| E7b | `primary` | `exact_vs_legacy` | `clinical_complete` | 3.25 | 16/3 | 0.00442505 | 0.0088501 |
| E8 | `primary` | `invalid_vs_soft` | `clinical_complete` | -4.55 | 2/12 | 0.0129395 | 0.0388184 |
| E8 | `primary` | `invalid_vs_soft` | `complete_or_compatible_partial` | -15.00 | 3/36 | 3.60887e-08 | 1.08266e-07 |
| E9 | `primary` | `real_vs_duplicate` | `clinical_complete` | 3.50 | 17/3 | 0.00257683 | 0.0103073 |
| E9 | `primary` | `real_vs_single` | `clinical_complete` | 3.25 | 16/3 | 0.00442505 | 0.0132751 |
| RCR3 | `primary` | `compact4_vs_rcr3` | `complete_or_compatible_partial` | -14.00 | 32/74 | 5.54198e-05 | 0.00011084 |
| RCR3 | `primary` | `rcr3_vs_lite3_same_3call_budget` | `complete_or_compatible_partial` | -7.33 | 33/55 | 0.0246228 | 0.0246228 |
| RCR3 | `primary` | `third_generator_marginal_utility` | `complete_or_compatible_partial` | -21.33 | 9/73 | 1.37674e-13 | 4.13021e-13 |

## Interpretation boundary

This replay can update arm-level Top-1 clinical conclusions. It cannot update task conclusions until the fresh evaluator namespace is complete. It cannot by itself update candidate-registry exposure, selector capture, or trajectory-level mechanisms where non-winning candidates still use old proxy labels. Those mechanisms remain hypotheses until a separate full-pool relation migration is completed.

Reproduction:

```bash
python -m analysis.mechanism_v2.endpoint_migration freeze
python -m analysis.mechanism_v2.endpoint_migration run-reviewer --reviewer-id reviewer_a --model google/gemini-2.5-flash
python -m analysis.mechanism_v2.endpoint_migration compile-panel
python -m analysis.mechanism_v2.endpoint_migration run-task
python -m analysis.mechanism_v2.endpoint_migration finalize --allow-model-only
python -m analysis.mechanism_v2.endpoint_migration render-report
```
