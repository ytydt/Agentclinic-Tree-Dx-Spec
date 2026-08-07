# Calibration smoke summary (pilot24)

- created: 2026-07-23T00:19:03.144504+00:00
- n=24 dry_run=False epsilon_at2=0.0
- ours rematch vs official mismatches: 0

| arm | @1 | @2 | MRR | Δ@1 | Δ@2 | status | reverted |
|-----|---:|---:|----:|----:|----:|--------|---------:|
| ours | 0.5833 | 0.7500 | 0.6667 | 0.0 | 0.0 | PASS | 0 |
| support_rerank | 0.5833 | 0.7500 | 0.6667 | 0.0 | 0.0 | PASS | 2 |
| pair | 0.6250 | 0.7500 | 0.6875 | 0.0417 | 0.0 | PASS | 0 |
| both | 0.5833 | 0.7500 | 0.6667 | 0.0 | 0.0 | PASS | 2 |
| both_l1fallback | 0.6250 | 0.7500 | 0.6875 | 0.0417 | 0.0 | PASS | 12 |
| merge | 0.7083 | 0.7500 | 0.7292 | 0.125 | 0.0 | PASS | 0 |
| both_merge | 0.7083 | 0.7500 | 0.7292 | 0.125 | 0.0 | PASS | 1 |

