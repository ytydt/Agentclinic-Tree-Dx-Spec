# 粒度支线烟测（AdaptiveMerge / Subdivide / Deepen）

**日期**：2026-07-23  
**代码**：[`adaptive_subdivide_under_l2.py`](../../scripts/paper/adaptive_subdivide_under_l2.py)、[`adaptive_deepen_or_merge.py`](../../scripts/paper/adaptive_deepen_or_merge.py)、[`run_at1_calibration_smoke.py --preset granularity`](../../scripts/paper/run_at1_calibration_smoke.py)  
**日志**：`logs/diagnosisarena_d2_m01_v1/at1_granularity_v1/`  
**口径**：无金标 G2（与 harness 一致）；mapper 仍为既有 `typed_llm` rematch。

## 机制摘要

| 模块 | 行为 |
|------|------|
| `AdaptiveMergeSiblings` | 全榜同义簇合并为代表叶（离线/在线均可） |
| `AdaptiveSubdivideUnderL2` | 过粗叶下按选项生成伪 L3；vignette 词重叠排序；不改树库 |
| `AdaptiveDeepenOrMerge` | Fine→merge；**仅当非 Fine** 时 Coarse→subdivide；再串 `both_l1fallback` |
| Coarse 门控 | ≥2 选项共绑一叶，且选项对中至少一对 **非同义**（避免把同义挤占误当细分） |

## all100 全表（ε_@2=0.01）

| arm | @1 | @2 | MRR | Δ@1 | Δ@2 | status |
|-----|---:|---:|----:|----:|----:|--------|
| ours | 0.59 | 0.78 | 0.688 | — | — | PASS |
| both_l1fallback | 0.65 | 0.79 | 0.720 | +0.06 | +0.01 | PASS |
| merge | **0.68** | 0.78 | 0.733 | +0.09 | 0 | PASS |
| both_merge | 0.66 | 0.78 | 0.723 | +0.07 | 0 | PASS |
| subdivide | 0.51 | 0.73 | 0.640 | −0.08 | −0.05 | **REJECTED** |
| subdivide_calib | 0.53 | 0.74 | 0.652 | −0.06 | −0.04 | **REJECTED** |
| deepen | **0.67** | 0.78 | 0.728 | +0.08 | 0 | PASS |

## G4 分层（A 集相关）

| arm | Fine primary @1 (n=7) | Coarse-agent @1 (n=7) | set A @1 (n=19) |
|-----|----------------------:|----------------------:|----------------:|
| ours | 0.00 | 0.00 | 0.00 |
| both_l1fallback | 0.71 | **0.71** | 0.63 |
| merge | **1.00** | 0.29 | 0.53 |
| deepen | **1.00** | 0.43 | 0.63 |
| subdivide | 0.14 | 0.14 | 0.16 |

**解读**：

- Fine：merge / deepen 强（1.00）；与设计一致。  
- Coarse：伪 L3 **未能**超过仅校准（0.14/0.43 ≪ 0.71）；`subdivide*` 伤全量 @2 → 否决进默认。  
- 禁止把校准在 Coarse 子集上的涨点记成「细分修复」。

## Pilot24

全部臂 @2 不降；merge / deepen 领先（@1≈0.67–0.71）。

## Harness 默认

- `--granularity-mode deepen`（Fine 门控 merge；纯 Coarse 才 subdivide）  
- `--calibration-arm both_l1fallback`  
- 正式组合点估计：**@1 0.67 / @2 0.78 / MRR 0.73**（与校准-only **0.65 / 0.79 / 0.72** 分列）  
- 离线 `merge` 臂 @1 0.68 为上界参考，但「恒合并 + 校准」的 `both_merge` 为 0.66；gated `deepen` 更稳。

## 单元测试

`pytest tests/test_adaptive_granularity.py tests/test_topk_calibration.py`：15 passed。

## 未解决 / 下一跳

- Coarse 真 L3 进树 + 局部 joint（当前仅伪叶 rematch）  
- 可选 mapper `typed_llm_disagreement_rag` 对齐重评  
