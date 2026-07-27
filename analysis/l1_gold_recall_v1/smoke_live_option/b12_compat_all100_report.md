# B12+compat all100 live option gate

- generated: `2026-07-24T09:08:48.336403+00:00`
- baseline: compat_parallel rematch **0.72/0.78**

| cohort | n | typed @1 | typed @2 | MRR |
|--------|--:|---------:|---------:|----:|
| Pilot24 | 24 | 0.750 | 0.833 | 0.792 |
| Remain76 | 76 | 0.684 | 0.776 | 0.735 |
| **all100** | 100 | **0.700** | **0.790** | 0.748 |

- Δ@1=-0.0200 Δ@2=+0.0100
- merge_only all100: 93/98 (94.90%)
- **GATE: REJECT** — all100 B12 typed 0.700/0.790 vs compat_parallel rematch 0.72/0.78; merge_only_rate=0.9489795918367347
- set_default_l1_calib_b12=`False`

