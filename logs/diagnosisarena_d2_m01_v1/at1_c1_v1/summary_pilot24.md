# Calibration smoke summary (pilot24)

- created: 2026-07-27T12:35:38.513563+00:00
- n=24 dry_run=True epsilon_at2=0.0
- synonym_bind: OFF (main reporting standard)
- ours rematch vs official mismatches: 0

| arm | @1 | @2 | MRR | Δ@1 | Δ@2 | status | reverted |
|-----|---:|---:|----:|----:|----:|--------|---------:|
| ours | 0.5833 | 0.7500 | 0.6667 | 0.0 | 0.0 | PASS | 0 |
| merge | 0.7083 | 0.7500 | 0.7292 | 0.125 | 0.0 | PASS | 0 |
| both_l1fallback | 0.6667 | 0.7500 | 0.7083 | 0.0834 | 0.0 | PASS | 0 |
| compat_serial_safe | 0.7500 | 0.7500 | 0.7500 | 0.1667 | 0.0 | PASS | 0 |
| compat_parallel | 0.7500 | 0.7500 | 0.7500 | 0.1667 | 0.0 | PASS | 0 |
| compat_random_route | 0.7083 | 0.7500 | 0.7292 | 0.125 | 0.0 | PASS | 0 |
| concept_id_merge | 0.5417 | 0.7500 | 0.6458 | -0.0416 | 0.0 | PASS | 0 |
| compat_parallel_no_l1_prior | 0.7500 | 0.7500 | 0.7500 | 0.1667 | 0.0 | PASS | 0 |

