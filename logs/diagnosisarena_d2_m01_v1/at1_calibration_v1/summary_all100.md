# Calibration smoke summary (all100)

- created: 2026-07-23T00:19:04.560724+00:00
- n=100 dry_run=False epsilon_at2=0.01
- ours rematch vs official mismatches: 0

| arm | @1 | @2 | MRR | Δ@1 | Δ@2 | status | reverted |
|-----|---:|---:|----:|----:|----:|--------|---------:|
| ours | 0.5900 | 0.7800 | 0.6883 | 0.0 | 0.0 | PASS | 0 |
| support_rerank | 0.6500 | 0.7900 | 0.7200 | 0.06 | 0.01 | PASS | 3 |
| pair | 0.6000 | 0.7800 | 0.6933 | 0.01 | 0.0 | PASS | 0 |
| both | 0.6500 | 0.7900 | 0.7200 | 0.06 | 0.01 | PASS | 3 |
| both_l1fallback | 0.6900 | 0.7900 | 0.7400 | 0.1 | 0.01 | PASS | 44 |
| merge | 0.6800 | 0.7800 | 0.7333 | 0.09 | 0.0 | PASS | 0 |
| both_merge | 0.6700 | 0.7800 | 0.7283 | 0.08 | 0.0 | PASS | 1 |

