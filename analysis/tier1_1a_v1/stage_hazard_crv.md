# T1-03 Stage hazards + T1-05 CRV

Created: 2026-07-31T05:01:24.756563+00:00
Lexical match threshold: 0.7

## mcr_v1
n_scored=100 / trees=100

| stage | N_prev | N_cur | dropped | h | Wilson95 | survival |
|---|---:|---:|---:|---:|---|---:|
| enter→L1 | 100 | 70 | 30 | 0.300 | [0.219,0.396] | 0.700 |
| L1→leaf | 70 | 69 | 1 | 0.014 | [0.003,0.077] | 0.690 |
| leaf→cap | 69 | 69 | 0 | 0.000 | [0.000,0.053] | 0.690 |
| cap→arbiter | 69 | 52 | 17 | 0.246 | [0.160,0.360] | 0.520 |
| arbiter→compat | 52 | 51 | 1 | 0.019 | [0.003,0.101] | 0.510 |
| compat→emitted | 51 | 51 | 0 | 0.000 | [0.000,0.070] | 0.510 |
| emitted→credited | 51 | 42 | 9 | 0.176 | [0.096,0.303] | 0.420 |

### CRV (Acc upper bound if stage repaired)

Observed credit rate (s7_credited): 0.42

| stage | n_fail | p(credit\|pass) | CRV | deterministic? |
|---|---:|---:|---:|---|
| s1_l1 | 30 | 0.600 | 0.180 | False |
| s2_leaf | 1 | 0.609 | 0.006 | False |
| s3_cap | 0 | 0.609 | 0.000 | True |
| s4_arbiter | 17 | 0.808 | 0.137 | False |
| s5_compat | 1 | 0.824 | 0.008 | True |
| s6_emitted | 0 | 0.824 | 0.000 | True |
| s7_credited | 9 | 1.000 | 0.090 | False |

## ox_hot
n_scored=100 / trees=100

| stage | N_prev | N_cur | dropped | h | Wilson95 | survival |
|---|---:|---:|---:|---:|---|---:|
| enter→L1 | 100 | 99 | 1 | 0.010 | [0.002,0.054] | 0.990 |
| L1→leaf | 99 | 98 | 1 | 0.010 | [0.002,0.055] | 0.980 |
| leaf→cap | 98 | 98 | 0 | 0.000 | [0.000,0.038] | 0.980 |
| cap→arbiter | 98 | 93 | 5 | 0.051 | [0.022,0.114] | 0.930 |
| arbiter→compat | 93 | 93 | 0 | 0.000 | [0.000,0.040] | 0.930 |
| compat→emitted | 93 | 92 | 1 | 0.011 | [0.002,0.058] | 0.920 |
| emitted→credited | 92 | 92 | 0 | 0.000 | [0.000,0.040] | 0.920 |

### CRV (Acc upper bound if stage repaired)

Observed credit rate (s7_credited): 0.92

| stage | n_fail | p(credit\|pass) | CRV | deterministic? |
|---|---:|---:|---:|---|
| s1_l1 | 1 | 0.929 | 0.009 | False |
| s2_leaf | 1 | 0.939 | 0.009 | False |
| s3_cap | 0 | 0.939 | 0.000 | True |
| s4_arbiter | 5 | 0.989 | 0.049 | False |
| s5_compat | 0 | 0.989 | 0.000 | True |
| s6_emitted | 1 | 1.000 | 0.010 | True |
| s7_credited | 0 | 1.000 | 0.000 | False |

