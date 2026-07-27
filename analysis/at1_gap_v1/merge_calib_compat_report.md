# Merge × Calibration 兼容机制烟测

**日期**：2026-07-23  
**代码**：[`merge_calib_compat.py`](../../scripts/paper/merge_calib_compat.py)、[`run_at1_calibration_smoke.py --preset compat`](../../scripts/paper/run_at1_calibration_smoke.py)  
**日志**：`logs/diagnosisarena_d2_m01_v1/at1_compat_v1/`  
**根因短文**：[`merge_calib_interaction_rootcause.md`](merge_calib_interaction_rootcause.md)  
**机制专档（算法 / 门控 / 起效根因）**：[`compat_parallel_mechanism_explainer.md`](compat_parallel_mechanism_explainer.md)  
**口径**：无金标 G2；备份 deepen 管线于 `backups/merge_calib_compat_20260723/`

## 机制

| 模式 | 行为 |
|------|------|
| **compat_parallel**（默认） | Fine 拥挤门控（Top1 簇≥2 或 Top1–Top2 同义）→ **仅 merge**；否则 → **仅 both_l1fallback**。禁止串行叠用 |
| compat_serial_safe | 门控真：merge → `support_rerank` + 金标盲 Merge-Top1 护栏；否则同 calib-only |
| both_merge（修正） | 强制 merge → `both_l1fallback`（公平串行对照） |

## all100（ε_@2=0.01）

| arm | @1 | @2 | MRR | Δ@1 | Δ@2 | status |
|-----|---:|---:|----:|----:|----:|--------|
| ours | 0.59 | 0.78 | 0.688 | — | — | PASS |
| both_l1fallback | 0.65 | 0.79 | 0.720 | +0.06 | +0.01 | PASS |
| merge | 0.68 | 0.78 | 0.733 | +0.09 | 0 | PASS |
| both_merge（修正） | 0.67 | 0.78 | 0.728 | +0.08 | 0 | PASS |
| **compat_parallel** | **0.72** | **0.78** | **0.753** | **+0.13** | 0 | **PASS** |
| compat_serial_safe | 0.72 | 0.78 | 0.753 | +0.13 | 0 | PASS |

路径分布（compat_parallel）：`merge_only` 89 / `calib_only` 11。

## 关键个案（串行损伤被避免）

| case | ours | merge | calib | both_merge | compat |
|------|-----:|------:|------:|-----------:|-------:|
| 140 | 1 | 1 | 1 | **0** | **1** |
| 28 | 1 | 1 | 1 | **0** | **1** |
| 89 | 1 | 1 | 0 | 0 | **1** |

## G4 分层

| arm | Fine primary @1 | Coarse-agent @1 |
|-----|----------------:|----------------:|
| both_l1fallback | 0.71 | **0.71** |
| merge | **1.00** | 0.29 |
| compat_parallel | **1.00** | 0.43 |

## Harness

- 默认 `--granularity-mode compat`（`run_diagnosisarena_downstream_top2` / `pipeline_staged`）
- compat 已内含 XOR 校准，不再串二次 `both_l1fallback`
- 正式组合数字：**@1 0.72 / @2 0.78 / MRR 0.75**（与校准-only 0.65/0.79/0.72、merge-only 0.68/0.78 **分列**）

## 验收

- [x] `@1 ≥ 0.70` 且 `@2 ≥ ours−0.01`
- [x] 相对修正后 both_merge 净胜（0.72 > 0.67）
- [x] 140/28 类叠用错被 parallel 避免
- [x] 单元测试 `tests/test_merge_calib_compat.py`
