# Addendum: 79-arm endpoint-migration sensitivity analyses

## Status and interpretation boundary

This addendum is a deterministic, case-level replay over the canonical 79-arm
artifact. It adds no LLM calls and changes no canonical endpoint decision.
**Novel clinical relations remain a blinded three-model-panel sensitivity
census, not a human-root census.** Embedded E2 root sentinels measure panel
error but do not transfer root ownership to novel predictions. E2 therefore
remains the only full human-root capability census.

The input contains 24,076 intention rows,
23,046 served rows, 79 arms and
99 frozen contrasts. Every inferential comparison
below uses paired cases. There are 162 Holm-significant cells
among the complete common-served output; this count spans different endpoints
and is descriptive, not a new global familywise claim. Task contrasts are
reported only within DA and MCR; their different evaluator contracts are not
pooled into an artificial ALL-scope task endpoint.

## Panel measurement sensitivity

Against 1,173 hidden E2 root sentinels, aggregate-panel fine-label
accuracy is 70.93%; C-boundary accuracy
is 97.70% and C∪P
accuracy is 91.90%.
The best single reviewer on the same sentinels is `reviewer_c` at
74.00% fine-label accuracy,
98.21% C accuracy,
and 94.37%
C∪P accuracy. Thus unweighted majority aggregation does not automatically
dominate its strongest member, even though it is less reviewer-specific.
On the 3,407 novel relations, Fleiss κ is
0.597 for the six-way relation, 0.740
for C, and 0.794 for C∪P. Agreement is therefore
endpoint-dependent; majority voting must not be mistaken for root truth.

The individual-reviewer replay finds 95/594
C or C∪P contrast/scope cells whose panel and all three reviewers do not share
one direction (zeros count as their own direction). Of 115
panel-significant cells, 106 remain Holm-significant in all three
single-reviewer replays with the same direction. The largest reviewer delta
range is 9.00 pp for
E1 / `shuffle_vs_fixed_options__ab02_flat` /
MCR / `complete_or_compatible_partial`. These are measurement-model
sensitivity diagnostics, not independent clinical experiments.

## E5: typed additions, width expansion, and pruning are separate Holm families

The original E5 mixed semantically typed width-5 additions with the generic
width ladder. The sensitivity replay separates five typed additions from the
three genuine expansion contrasts. `remove_non_gold3` is a one-item pruning
intervention, not width expansion, and is retained in its own singleton
secondary family. Values below condition on both arms having served and use
clinical-complete as the endpoint.

| Holm family | Contrast | ITA Δ pp | ITA q | Common served n | Common Δ pp | Gain/loss | Common q |
|---|---|---:|---:|---:|---:|---:|---:|
| `pruning_secondary_1` | `remove_non_gold3_vs_base4` | 4.50 | 0.175465 | 200 | 4.50 | 22/13 | 0.175465 |
| `typed_addition_5` | `add_component5_vs_base4` | -14.50 | 0.000163427 | 166 | 0.60 | 12/11 | 1 |
| `typed_addition_5` | `add_parent5_vs_base4` | -20.50 | 2.10593e-07 | 166 | -6.63 | 9/20 | 0.245713 |
| `typed_addition_5` | `add_sibling5_vs_base4` | -24.50 | 2.69031e-10 | 165 | -11.52 | 6/25 | 0.00438955 |
| `typed_addition_5` | `add_synonym5_vs_base4` | -11.00 | 0.00456153 | 165 | 4.85 | 17/9 | 0.505913 |
| `typed_addition_5` | `add_unrelated5_vs_base4` | -17.50 | 6.17179e-06 | 166 | -3.01 | 10/15 | 0.848712 |
| `width_ladder_3` | `nested_width6_vs_base4` | -24.00 | 1.94459e-10 | 166 | -10.84 | 6/24 | 0.00286181 |
| `width_ladder_3` | `nested_width8_vs_base4` | -30.00 | 6.64606e-14 | 164 | -17.68 | 5/34 | 7.28972e-06 |
| `width_ladder_3` | `width8_vs_width6` | -6.00 | 0.0226558 | 164 | -6.71 | 6/17 | 0.0346897 |

Conditioning on common service materially changes the typed-candidate story:
the sibling addition retains a -11.52
pp C penalty (q=0.00439), while the synonym addition
moves to 4.85 pp for C and
6.67 pp for C∪P
(C∪P q=0.02954). By contrast, genuine expansion
still loses 10.84 pp at width 6
and 17.68 pp at width 8
(q=0.002862 and
q=7.29e-06). The ITA loss therefore mixes technical
service attrition with a residual, topology-dependent interference effect.

This split prevents the generic width ladder from borrowing multiplicity from
the mechanistically different candidate-type interventions. It still does not
identify a universal width law: candidate type, technical service, and the
model-panel endpoint remain distinct components.

## Complete task replay: common-served sensitivity

With all 5,839 unique task payloads now complete,
**15 family-specific task contrasts** remain
Holm-significant after restricting to
cases served by both arms. DA and MCR are kept separate because their task
evaluators implement different benchmark contracts.

| Experiment | Benchmark | Contrast | Common served n | Δ pp | Gain/loss | Holm q |
|---|---|---|---:|---:|---:|---:|
| E1 | DA | `options_vs_clean_fixed__ab02_flat` | 100 | 26.00 | 35/9 | 0.000636268 |
| E1 | DA | `options_vs_clean_fixed__aphhm_hierarchical` | 95 | 31.58 | 36/6 | 1.98021e-05 |
| E1 | DA | `options_vs_clean_shuffled__ab02_flat` | 98 | 32.65 | 38/6 | 7.5443e-06 |
| E1 | DA | `options_vs_clean_shuffled__aphhm_hierarchical` | 83 | 25.30 | 29/8 | 0.00376449 |
| E1 | MCR | `options_vs_clean_fixed__ab02_flat` | 99 | 28.28 | 31/3 | 5.36209e-06 |
| E1 | MCR | `options_vs_clean_fixed__aphhm_hierarchical` | 83 | 33.73 | 29/1 | 4.61936e-07 |
| E1 | MCR | `options_vs_clean_shuffled__ab02_flat` | 100 | 26.00 | 30/4 | 3.08244e-05 |
| E1 | MCR | `options_vs_clean_shuffled__aphhm_hierarchical` | 85 | 30.59 | 29/3 | 1.53361e-05 |
| E12 | MCR | `pairwise_vs_first_raw_k10` | 149 | 10.07 | 16/1 | 0.0107117 |
| E12 | MCR | `pairwise_vs_first_raw_k5` | 150 | 9.33 | 15/1 | 0.0197144 |
| E4 | MCR | `collapse_obligation_ledger_vs_evidence_count_control` | 200 | 17.00 | 40/6 | 2.79252e-06 |
| E4 | MCR | `e7_contrast_vs_evidence_count_control` | 200 | 14.50 | 36/7 | 6.27413e-05 |
| E4 | MCR | `forest_evidence_integrator_vs_evidence_count_control` | 200 | 17.00 | 41/7 | 4.99233e-06 |
| E4 | MCR | `pairwise_tournament_vs_evidence_count_control` | 200 | 18.00 | 42/6 | 1.00875e-06 |
| E5 | MCR | `nested_width8_vs_base4` | 75 | -26.67 | 1/21 | 8.7738e-05 |

These task results do not relabel a partial or conflicting clinical object as
clinical-complete. They test benchmark projection/acceptability after service,
and must remain a separate estimand. Within E5's corrected three-contrast width
family, MCR task drops 14.47
pp at width 6 (q=0.02545) and
26.67 pp at width 8
(q=3.29e-05).

## Service path: descriptive decomposition, not causal mediation

For E1, E6, E8 and RCR3, ITA endpoint change is decomposed exactly into:
(i) changes among cases served by both arms, (ii) positive outcomes in cases
served only by the right arm, and (iii) lost positive outcomes in cases served
only by the left arm. The three terms sum exactly to the ITA delta. Service
itself is not randomized, so this is an arithmetic path decomposition rather
than a causal mediation analysis.

Largest absolute ALL-scope service-rate differences:

| Experiment | Contrast | n | Service Δ pp | Right-only/left-only | Holm q |
|---|---|---:|---:|---:|---:|
| RCR3 | `third_generator_marginal_utility` | 300 | -40.33 | 1/122 | 6.99654e-35 |
| E8 | `invalid_vs_soft` | 220 | -30.91 | 0/68 | 2.03288e-20 |
| RCR3 | `compact4_vs_rcr3` | 300 | -29.00 | 24/111 | 2.86464e-14 |
| E6 | `flat_vs_raw` | 300 | -12.67 | 6/44 | 9.73122e-08 |
| E6 | `graph_vs_raw` | 300 | -12.33 | 6/43 | 1.14555e-07 |
| RCR3 | `rcr3_vs_lite3_same_3call_budget` | 300 | -11.33 | 3/37 | 1.9465e-08 |
| E1 | `options_vs_clean_shuffled__aphhm_hierarchical` | 200 | -6.50 | 8/21 | 0.192956 |
| E1 | `shuffle_vs_fixed_options__aphhm_hierarchical` | 200 | -5.50 | 9/20 | 0.429998 |

The decomposition changes several mechanism readings. E8 `invalid_vs_soft`
loses 4.55 pp C entirely
through the left-only-service path (common-served Δ =
0.00 pp); for C∪P,
14.09 of
the 15.45 pp ITA loss is
the same path. RCR3's third-generator C∪P loss is
21.00 pp ITA but only
1.72 pp among
common-served cases; RCR3 versus Lite is similarly
-7.00 pp ITA versus
-0.39 pp common-served.
By contrast, E6 graph versus raw retains a
-10.00 pp C∪P deficit after
conditioning on service. The E1 hierarchical-options shuffle penalty attenuates
from -8.00 pp ITA to
-2.99 pp common-served.
Thus service reliability dominates the apparent E8-invalid and RCR3 losses,
whereas E6 retains a representation-dependent clinical deficit.

Holm families for service status are experiment × frozen contrast family ×
scope; clinical decompositions carry no additional p-value.

## Legacy-chain calibration and endpoint transitions

At the deduplicated case-prediction-relation unit, legacy-chain precision is
59.51% for C and
96.09% for C∪P; sensitivity is
61.01% and
37.58%, respectively. These targets
mix exact E2 root reuse, deterministic safe-exact decisions, and novel model
panel decisions, so the table is calibration of a historical endpoint against
the migrated measurement system—not validation against a new human gold set.

Largest deduplicated endpoint-transition classes:

| Transition | n | Rate |
|---|---:|---:|
| `concordant_noncompatible_not_equivalent` | 1196 | 22.35% |
| `compatible_partial_missed_by_legacy` | 1183 | 22.11% |
| `concordant_noncompatible_scope_conflict` | 1093 | 20.43% |
| `concordant_noncompatible_manifestation_related` | 392 | 7.33% |
| `clinical_complete_missed_by_legacy` | 365 | 6.82% |
| `safe_exact_confirmed_complete` | 359 | 6.71% |
| `legacy_only_compatible_partial` | 356 | 6.65% |
| `legacy_only_confirmed_complete` | 225 | 4.20% |

The case-level transition ledger preserves every occurrence so that aggregate
claims can be traced back to experiment, arm, case, relation and audit source.

## Multiplicity and artifact map

| Output | Unit and family |
|---|---|
| `common_served_paired_contrasts.*` | Case-paired; Holm within experiment × frozen family × scope × endpoint; task only within DA/MCR |
| `e5_family_split.*` | Case-paired; Holm separately within typed-addition-5, width-ladder-3, and pruning-secondary-1 × estimand × scope × endpoint |
| `service_status_contrasts.*` | Case-paired service status; Holm within experiment × frozen family × scope |
| `service_path_decomposition.*` | Case-level exact arithmetic decomposition; clinical endpoints in all scopes and task within DA/MCR; no causal or multiplicity claim |
| `individual_reviewer_contrasts.*` | ITA case-paired; Holm within reviewer × experiment × frozen family × scope × endpoint |
| `panel_aggregate_calibration.json` | Sentinel relation; descriptive against hidden E2 root truth |
| `novel_reviewer_agreement.json` | Novel relation; Fleiss/Cohen agreement without truth |
| `legacy_clinical_calibration.*` | Case-arm occurrence and deduplicated relation; descriptive |
| `endpoint_transition_case_ledger.csv` | Served case-arm occurrence |
| `endpoint_transition_typology.*` | Case-arm and deduplicated-relation summaries; descriptive |

Reproduce with:

```bash
python -m analysis.mechanism_v2.endpoint_migration_sensitivity
```
