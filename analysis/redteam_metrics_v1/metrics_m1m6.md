# Purpose-built metrics M1-M6 (zero-inference)

## M1/M2 mechanism panel: ranking-window redundancy

| Dataset | n | window slots | effective width | wasted-slot rate | 95% CI | any redundancy | top-1 crowded | mean top-1 class |
|---|---|---|---|---|---|---|---|---|
| DiagnosisArena | 98 | 4.61 | 1.69 | 0.632 | [0.597, 0.666] | 1.000 | 0.949 | 3.72 |
| MedCaseReasoning | 98 | 4.66 | 1.90 | 0.593 | [0.552, 0.631] | 0.980 | 0.837 | 3.29 |
| Open-XDDx | 99 | 4.47 | 1.59 | 0.643 | [0.602, 0.679] | 0.960 | 0.889 | 3.68 |

## Predicate agreement (validity check for the two panels)

multi-member top concept classes: 88; lexical predicate also merges the whole class in 87 (0.989); mean class size 4.01; mean lexical subgroups 1.01

- disagreement, case 35 (2 subgroups): ['Pneumocystis jirovecii pneumonia', 'Community-Acquired Pneumonia', 'pneumonia', 'pneumonia', 'Streptococcal pneumonia']

## M1/M2 cross-system panel: emitted-list redundancy on Open-XDDx

predicate: gold-blind lexical equivalence (normalised containment or token overlap)

| System | slots | width | wasted | wasted (2-name prefix) |
|---|---|---|---|---|
| Flat beam search | 5 | 4.51 | 0.098 | 0.035 |
| Self-consistent CoT | 5 | 4.62 | 0.076 | 0.015 |
| MDAgents | 5 | 4.63 | 0.074 | 0.025 |
| MEDDxAgent | 5 | 4.64 | 0.072 | 0.030 |
| Self-refine | 5 | 4.65 | 0.070 | 0.045 |
| i-MedRAG | 2 | 1.88 | 0.060 | 0.060 |
| Direct CoT | 5 | 4.72 | 0.056 | 0.025 |
| CoT+RAG | 5 | 4.73 | 0.054 | 0.035 |
| Dual-Inf | 4.74 | 4.49 | 0.050 | 0.040 |
| Medprompt-style | 5 | 4.77 | 0.046 | 0.010 |
| MAC | 5 | 4.78 | 0.044 | 0.025 |
| Flat rerank | 5 | 4.79 | 0.042 | 0.025 |
| MedRAG | 4.92 | 4.72 | 0.040 | 0.025 |
| Chain-of-Diagnosis | 4.99 | 4.83 | 0.033 | 0.010 |
| APHHM | 1.72 | 1.59 | 0.029 | 0.010 |

flat systems: mean wasted 0.058 (range 0.033-0.098), two-name prefix mean 0.029

## M3 state-propagation volume and cap activity

instrumented benchmarks: Open-XDDx; absent on: DiagnosisArena, MedCaseReasoning

| Arm | n | cap | mean revised | median | range | emitted | revised/emitted | capped |
|---|---|---|---|---|---|---|---|---|
| deployed | 100 | {6: 100} | 22.92 | 22.0 | 11-45 | 1.70 | 13.5 | 0 |
| no_writeback | 100 | {6: 100} | 23.46 | 22.0 | 12-55 | 1.66 | 14.1 | 0 |
| wider_evidence | 100 | {6: 100} | 23.68 | 22.5 | 10-55 | 1.66 | 14.3 | 0 |
| cap_1 | 100 | {1: 100} | 22.95 | 22.0 | 11-44 | 1.58 | 14.5 | 0 |
| cap_unbounded | 100 | {999: 100} | 24.34 | 22.0 | 12-60 | 1.62 | 15.0 | 0 |

summary: {"revisions_computed_when_writeback_off": 23.46, "revisions_computed_when_writeback_on": 22.92, "cap_never_binds_at_writeback": true, "cap_span_effect_on_revisions": 1.39}

## M5/M6 conversion and failure-quality vector on DiagnosisArena

| System | n | credited | delivered | conversion | misranked | interface | absent |
|---|---|---|---|---|---|---|---|
| APHHM | 100 | 0.710 | 0.790 | 0.899 | 0.080 | 0.020 | 0.190 |
| MEDDxAgent | 100 | 0.620 | 0.710 | 0.873 | 0.090 | 0.050 | 0.240 |
| MAC | 100 | 0.610 | 0.670 | 0.910 | 0.060 | 0.040 | 0.290 |
| Dual-Inf | 100 | 0.600 | 0.700 | 0.857 | 0.100 | 0.020 | 0.280 |
| i-MedRAG | 100 | 0.600 | 0.670 | 0.896 | 0.070 | 0.030 | 0.300 |
| MDAgents | 100 | 0.580 | 0.670 | 0.866 | 0.090 | 0.040 | 0.290 |
| Self-refine | 100 | 0.570 | 0.620 | 0.919 | 0.050 | 0.080 | 0.300 |
| Flat rerank | 100 | 0.560 | 0.630 | 0.889 | 0.070 | 0.040 | 0.330 |
| CoT+RAG | 100 | 0.550 | 0.630 | 0.873 | 0.080 | 0.040 | 0.330 |
| Direct CoT | 100 | 0.540 | 0.610 | 0.885 | 0.070 | 0.050 | 0.340 |
| Chain-of-Diagnosis | 100 | 0.540 | 0.550 | 0.982 | 0.010 | 0.040 | 0.410 |
| Flat beam search | 100 | 0.520 | 0.600 | 0.867 | 0.080 | 0.030 | 0.370 |
| Self-consistent CoT | 100 | 0.520 | 0.610 | 0.852 | 0.090 | 0.060 | 0.330 |
| Medprompt-style | 100 | 0.520 | 0.570 | 0.912 | 0.050 | 0.050 | 0.380 |
| Flat rerank (structural proxy) | 100 | 0.480 | 0.590 | 0.814 | 0.110 | 0.050 | 0.360 |
| MedRAG | 100 | 0.480 | 0.520 | 0.923 | 0.040 | 0.050 | 0.430 |
| Flat rerank $\times 10$ (RRF) | 100 | 0.470 | 0.590 | 0.797 | 0.120 | 0.030 | 0.380 |
| DiagnosisGPT-6B | 100 | 0.140 | 0.140 | 1.000 | 0.000 | 0.000 | 0.860 |

flat conversion mean 0.889 (range 0.797-1.000); flat delivered coverage mean 0.593
coverage vs conversion across systems: Pearson r = -0.540

### matched-subset comparison (each flat system's own delivered set)

| System | n subset | their conversion | full model on same subset | delta |
|---|---|---|---|---|
| Flat rerank $\times 10$ (RRF) | 59 | 0.797 | 0.780 | -0.017 |
| Flat rerank (structural proxy) | 59 | 0.814 | 0.763 | -0.051 |
| Dual-Inf | 70 | 0.857 | 0.786 | -0.071 |
| MDAgents | 67 | 0.866 | 0.791 | -0.075 |
| Self-refine | 62 | 0.919 | 0.839 | -0.081 |
| Self-consistent CoT | 61 | 0.852 | 0.770 | -0.082 |
| Direct CoT | 61 | 0.885 | 0.787 | -0.098 |
| MEDDxAgent | 71 | 0.873 | 0.775 | -0.099 |
| i-MedRAG | 67 | 0.896 | 0.791 | -0.104 |
| Flat rerank | 63 | 0.889 | 0.778 | -0.111 |
| CoT+RAG | 63 | 0.873 | 0.762 | -0.111 |
| Flat beam search | 60 | 0.867 | 0.733 | -0.133 |
| MAC | 67 | 0.910 | 0.776 | -0.134 |
| Medprompt-style | 57 | 0.912 | 0.754 | -0.158 |
| MedRAG | 52 | 0.923 | 0.731 | -0.192 |
| Chain-of-Diagnosis | 55 | 0.982 | 0.764 | -0.218 |
| DiagnosisGPT-6B | 14 | 1.000 | 0.571 | -0.429 |

full model higher on 0/17 delivered subsets; mean delta -0.127

### mirrored comparison (the full model's own delivered set)

| System | n subset | full model conversion | that system on same subset | delta |
|---|---|---|---|---|
| DiagnosisGPT-6B | 79 | 0.899 | 0.152 | 0.747 |
| MedRAG | 79 | 0.899 | 0.519 | 0.380 |
| Flat rerank (structural proxy) | 79 | 0.899 | 0.532 | 0.367 |
| Flat rerank $\times 10$ (RRF) | 79 | 0.899 | 0.532 | 0.367 |
| CoT+RAG | 79 | 0.899 | 0.570 | 0.329 |
| Flat beam search | 79 | 0.899 | 0.570 | 0.329 |
| Chain-of-Diagnosis | 79 | 0.899 | 0.582 | 0.316 |
| Medprompt-style | 79 | 0.899 | 0.582 | 0.316 |
| Self-consistent CoT | 79 | 0.899 | 0.595 | 0.304 |
| Direct CoT | 79 | 0.899 | 0.608 | 0.291 |
| Flat rerank | 79 | 0.899 | 0.633 | 0.266 |
| MDAgents | 79 | 0.899 | 0.646 | 0.253 |
| Self-refine | 79 | 0.899 | 0.658 | 0.241 |
| Dual-Inf | 79 | 0.899 | 0.671 | 0.228 |
| MAC | 79 | 0.899 | 0.671 | 0.228 |
| MEDDxAgent | 79 | 0.899 | 0.671 | 0.228 |
| i-MedRAG | 79 | 0.899 | 0.671 | 0.228 |

full model higher on 17/17 mirrored subsets; mean delta 0.319
