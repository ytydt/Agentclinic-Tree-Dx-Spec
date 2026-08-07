# Calibration smoke summary (all100)

- created: 2026-07-27T12:36:21.683601+00:00
- n=100 dry_run=False epsilon_at2=0.0
- synonym_bind: OFF (main reporting standard)
- ours rematch vs official mismatches: 0

| arm | @1 | @2 | MRR | Δ@1 | Δ@2 | status | reverted |
|-----|---:|---:|----:|----:|----:|--------|---------:|
| ours | 0.5900 | 0.7800 | 0.6883 | 0.0 | 0.0 | PASS | 0 |
| merge | 0.6800 | 0.7800 | 0.7333 | 0.09 | 0.0 | PASS | 0 |
| both_l1fallback | 0.6500 | 0.7800 | 0.7183 | 0.06 | 0.0 | PASS | 0 |
| compat_serial_safe | 0.7100 | 0.7900 | 0.7500 | 0.12 | 0.01 | PASS | 0 |
| compat_parallel | 0.7100 | 0.7800 | 0.7483 | 0.12 | 0.0 | PASS | 0 |
| compat_random_route | 0.6900 | 0.7800 | 0.7383 | 0.1 | 0.0 | PASS | 0 |
| concept_id_merge | 0.5700 | 0.7800 | 0.6783 | -0.02 | 0.0 | PASS | 0 |
| compat_parallel_no_l1_prior | 0.7000 | 0.7800 | 0.7433 | 0.11 | 0.0 | PASS | 0 |

