# Baseline dissection summary

## mcr (n=400)
### vs e7
| arm | acc | saves | misses | net |
|---|---|---|---|---|
| B06 | 0.275 | 29 | 24 | 5 |
| B07 | 0.265 | 27 | 26 | 1 |
| B01 | 0.2425 | 25 | 33 | -8 |

### correct-set combos
{'B06': 19, 'B06+B07+B01': 70, 'B01+B06': 7, 'B01+B07': 7, 'B06+B07': 14, 'B07': 15, 'B01': 13}

### layer contribution
- **base_win_recall** n=10: {'B07': 7, 'B01': 3, 'B06': 8} alone={'multi_baseline': 6, 'B06_only': 3, 'B07_only': 1}
- **base_win_rank** n=19: {'B07': 13, 'B06': 14, 'B01': 8} alone={'B07_only': 3, 'multi_baseline': 10, 'B06_only': 6}
- **e7_win_recall** n=7: {'e7': 7, 'B01': 1} alone={'no_baseline': 6, 'B01_only': 1}
- **e7_win_rank** n=5: {'e7': 5} alone={'no_baseline': 5}

### save loci (baseline correct, e7 wrong)
- **B06** saves=29 base_locus={'supervisor_ok': 20, 'supervisor_miss_but_scored_ok': 9} e7_locus={'s3_hit_s4_miss': 14, 's2_hit_s3_drop': 1, 's2_miss': 13, 's4_hit_judge_miss': 1}
- **B07** saves=27 base_locus={'diagnose_ok': 19, 'diagnose_miss_but_scored_ok': 8} e7_locus={'s2_miss': 12, 's2_hit_s3_drop': 2, 's3_hit_s4_miss': 12, 's4_hit_judge_miss': 1}
- **B01** saves=25 base_locus={'gen_ok': 20, 'rag_miss': 4, 'rag_hit_gen_miss': 1} e7_locus={'s2_miss': 9, 's3_hit_s4_miss': 14, 's2_hit_s3_drop': 1, 's4_hit_judge_miss': 1}

### mechanism rates
- **B06** {'n': 400, 'agents_hit_rate': 0.64, 'supervisor_hit_rate': 0.315, 'acc': 0.275} locus={'agents_miss': 137, 'supervisor_miss_but_scored_ok': 28, 'supervisor_ok': 82, 'agents_hit_supervisor_drop': 109, 'supervisor_hit_judge_miss': 44}
- **B07** {'n': 400, 'draft_hit_rate': 0.2825, 'refine_hit_rate': 0.0, 'diagnose_hit_rate': 0.2825, 'has_refine_rate': 1.0, 'acc': 0.265} locus={'draft_miss': 256, 'diagnose_ok': 75, 'diagnose_hit_judge_miss': 38, 'diagnose_miss_but_scored_ok': 31}
- **B01** {'n': 400, 'rag_hit_rate': 0.3675, 'gen_hit_rate': 0.2825, 'acc': 0.2425, 'acc_given_rag_hit': 0.4014, 'acc_given_rag_miss': 0.1502} locus={'rag_miss': 207, 'gen_ok': 76, 'rag_hit_gen_miss': 80, 'gen_hit_judge_miss': 37}

## da (n=400)
### vs e7
| arm | acc | saves | misses | net |
|---|---|---|---|---|
| B06 | 0.615 | 60 | 42 | 18 |
| B07 | 0.615 | 65 | 47 | 18 |
| B01 | 0.55 | 16 | 20 | -4 |

### correct-set combos
{'B06+B07+B01': 40, 'B07': 36, 'B06+B07': 166, 'B01': 6, 'B01+B06': 5, 'B01+B07': 4, 'B06': 35}

### layer contribution
- **base_win_recall** n=7: {'B07': 6, 'B01': 2, 'B06': 6} alone={'multi_baseline': 6, 'B06_only': 1}
- **base_win_rank** n=20: {'B07': 16, 'B06': 16, 'B01': 3} alone={'B07_only': 4, 'multi_baseline': 12, 'B06_only': 4}
- **e7_win_recall** n=6: {'e7': 6} alone={'no_baseline': 6}
- **e7_win_rank** n=3: {'B01': 1, 'e7': 3} alone={'B01_only': 1, 'no_baseline': 2}

### save loci (baseline correct, e7 wrong)
- **B06** saves=60 base_locus={'supervisor_ok': 21, 'supervisor_miss_but_scored_ok': 39} e7_locus={'s3_hit_s4_miss': 17, 's2_miss': 32, 's2_hit_s3_drop': 8, 's4_hit_judge_miss': 3}
- **B07** saves=65 base_locus={'diagnose_ok': 17, 'diagnose_miss_but_scored_ok': 48} e7_locus={'s2_hit_s3_drop': 13, 's2_miss': 35, 's3_hit_s4_miss': 15, 's4_hit_judge_miss': 2}
- **B01** saves=16 base_locus={'rag_hit_gen_miss': 5, 'gen_ok': 6, 'rag_miss': 5} e7_locus={'s2_hit_s3_drop': 2, 's2_miss': 7, 's3_hit_s4_miss': 6, 's4_hit_judge_miss': 1}

### mechanism rates
- **B06** {'n': 400, 'agents_hit_rate': 0.735, 'supervisor_hit_rate': 0.33, 'acc': 0.615} locus={'supervisor_ok': 105, 'agents_hit_supervisor_drop': 72, 'supervisor_miss_but_scored_ok': 141, 'agents_miss': 55, 'supervisor_hit_judge_miss': 27}
- **B07** {'n': 400, 'draft_hit_rate': 0.2625, 'refine_hit_rate': 0.0, 'diagnose_hit_rate': 0.2625, 'has_refine_rate': 1.0, 'acc': 0.615} locus={'diagnose_miss_but_scored_ok': 160, 'diagnose_ok': 86, 'draft_miss': 135, 'diagnose_hit_judge_miss': 19}
- **B01** {'n': 100, 'rag_hit_rate': 0.42, 'gen_hit_rate': 0.34, 'acc': 0.55, 'acc_given_rag_hit': 0.6905, 'acc_given_rag_miss': 0.4483} locus={'gen_ok': 26, 'rag_miss': 46, 'rag_hit_gen_miss': 20, 'gen_hit_judge_miss': 8}

## pooled (n=800)
### vs e7
| arm | acc | saves | misses | net |
|---|---|---|---|---|
| B06 | 0.445 | 89 | 66 | 23 |
| B07 | 0.44 | 92 | 73 | 19 |
| B01 | 0.304 | 41 | 53 | -12 |

### correct-set combos
{'B06+B07+B01': 110, 'B07': 51, 'B06+B07': 180, 'B01': 19, 'B01+B06': 12, 'B01+B07': 11, 'B06': 54}

### layer contribution
- **base_win_recall** n=17: {'B07': 13, 'B01': 5, 'B06': 14} alone={'multi_baseline': 12, 'B06_only': 4, 'B07_only': 1}
- **base_win_rank** n=39: {'B07': 29, 'B06': 30, 'B01': 11} alone={'B07_only': 7, 'multi_baseline': 22, 'B06_only': 10}
- **e7_win_recall** n=13: {'e7': 13, 'B01': 1} alone={'no_baseline': 12, 'B01_only': 1}
- **e7_win_rank** n=8: {'B01': 1, 'e7': 8} alone={'B01_only': 1, 'no_baseline': 7}

### save loci (baseline correct, e7 wrong)
- **B06** saves=89 base_locus={'supervisor_ok': 41, 'supervisor_miss_but_scored_ok': 48} e7_locus={'s3_hit_s4_miss': 31, 's2_miss': 45, 's2_hit_s3_drop': 9, 's4_hit_judge_miss': 4}
- **B07** saves=92 base_locus={'diagnose_ok': 36, 'diagnose_miss_but_scored_ok': 56} e7_locus={'s2_hit_s3_drop': 15, 's2_miss': 47, 's3_hit_s4_miss': 27, 's4_hit_judge_miss': 3}
- **B01** saves=41 base_locus={'rag_hit_gen_miss': 6, 'gen_ok': 26, 'rag_miss': 9} e7_locus={'s2_hit_s3_drop': 3, 's2_miss': 16, 's3_hit_s4_miss': 20, 's4_hit_judge_miss': 2}

### mechanism rates
- **B06** {'n': 800, 'agents_hit_rate': 0.6875, 'supervisor_hit_rate': 0.3225, 'acc': 0.445} locus={'supervisor_ok': 187, 'agents_hit_supervisor_drop': 181, 'supervisor_miss_but_scored_ok': 169, 'agents_miss': 192, 'supervisor_hit_judge_miss': 71}
- **B07** {'n': 800, 'draft_hit_rate': 0.2725, 'refine_hit_rate': 0.0, 'diagnose_hit_rate': 0.2725, 'has_refine_rate': 1.0, 'acc': 0.44} locus={'diagnose_miss_but_scored_ok': 191, 'diagnose_ok': 161, 'draft_miss': 391, 'diagnose_hit_judge_miss': 57}
- **B01** {'n': 500, 'rag_hit_rate': 0.378, 'gen_hit_rate': 0.294, 'acc': 0.304, 'acc_given_rag_hit': 0.4656, 'acc_given_rag_miss': 0.2058} locus={'gen_ok': 102, 'rag_miss': 253, 'rag_hit_gen_miss': 100, 'gen_hit_judge_miss': 45}

