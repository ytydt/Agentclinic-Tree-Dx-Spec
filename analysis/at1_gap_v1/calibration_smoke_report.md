# TopKCalibration 烟测与 100 例结果

**日期**：2026-07-23（**口径修订**：正式数字改为 harness / 无金标 G2）  
**代码**：[`scripts/paper/topk_calibration.py`](../../scripts/paper/topk_calibration.py)、[`adaptive_merge_siblings.py`](../../scripts/paper/adaptive_merge_siblings.py)、[`run_at1_calibration_smoke.py`](../../scripts/paper/run_at1_calibration_smoke.py)  
**日志**：`logs/diagnosisarena_d2_m01_v1/at1_calibration_v1/`  
**Mapper 口径**：既有 `typed_llm` 投影 + `_rank_and_expand` 叶序重匹配（`ours` 与官方 0 mismatch）。

## 口径声明（重要）

| 口径 | G2 | 用途 |
|------|-----|------|
| **harness / 无金标 G2** | `gold_leaf_ids=[]`，与默认下游一致 | **正式方法数字** |
| 旁路烟测 + 金标感知 G2 | 用金标叶是否仍在 Top-2 决定回退 | 神谕消融；**不得**作主结果 |

金标感知 G2 在推理时不可得 → 有神谕/作弊嫌疑。金标盲「冻结整个 Top-2 集合」不泄题，但实测 @1=0.59（抹掉 harness 增益）、@2=0.79，故采用 **报告 harness 口径**；见 `gold_blind_top2_freeze_report.md`。

## 正式结果（100 例，`both_l1fallback`，无金标 G2）

| 系统 | option @1 | option @2 | MRR |
|------|----------:|----------:|----:|
| ours（未校准） | 0.59 | 0.78 | 0.688 |
| **本方法 harness +both_l1fallback** | **0.65** | **0.79** | **0.720** |
| B06 MAC | 0.61 | 0.67 | 0.640 |
| B04 Dual-Inf | 0.60 | 0.70 | 0.650 |

相对 ours：Δ@1 **+0.06**，Δ@2 **+0.01**。仍高于 MAC/DualInf 的 @1，且保住 @2 优势。  
（基线 mapper 为 `typed_llm_disagreement_rag`，不完全同构。）

## 旁路烟测全表（含金标感知 G2；仅消融）

### Pilot 24

| arm | @1 | @2 | MRR | Δ@1 | Δ@2 | status |
|-----|---:|---:|----:|----:|----:|--------|
| ours | 0.5833 | 0.7500 | 0.6667 | — | — | PASS |
| support_rerank | 0.5833 | 0.7500 | 0.6667 | 0 | 0 | PASS |
| pair | 0.6250 | 0.7500 | 0.6875 | +0.0417 | 0 | PASS |
| both | 0.5833 | 0.7500 | 0.6667 | 0 | 0 | PASS |
| both_l1fallback | 0.6250 | 0.7500 | 0.6875 | +0.0417 | 0 | PASS |
| merge | 0.7083 | 0.7500 | 0.7292 | +0.1250 | 0 | PASS |
| both_merge | 0.7083 | 0.7500 | 0.7292 | +0.1250 | 0 | PASS |

### all100（金标感知 G2）

| arm | @1 | @2 | MRR | Δ@1 | Δ@2 | status | reverted |
|-----|---:|---:|----:|----:|----:|--------|---------:|
| ours | 0.59 | 0.78 | 0.6883 | — | — | PASS | 0 |
| support_rerank | 0.65 | 0.79 | 0.7200 | +0.06 | +0.01 | PASS | 3 |
| pair | 0.60 | 0.78 | 0.6933 | +0.01 | 0 | PASS | 0 |
| both | 0.65 | 0.79 | 0.7200 | +0.06 | +0.01 | PASS | 3 |
| both_l1fallback | 0.69 | 0.79 | 0.7400 | +0.10 | +0.01 | PASS | 44 |
| merge | 0.68 | 0.78 | 0.7333 | +0.09 | 0 | PASS | 0 |
| both_merge | 0.67 | 0.78 | 0.7283 | +0.08 | 0 | PASS | 1 |

同配置去掉金标 G2 后：`both_l1fallback` → **@1=0.65，@2=0.79，MRR=0.72**（与正式表一致）；叶序与神谕烟测在 44 例上不同。

## A 集分层（烟测金标 G2；n=19，@2 恒为 1.0）

| arm | A @1 | Fine⊂A @1 (n=8) | Coarse-agent⊂A @1 (n=7) |
|-----|------:|----------------:|------------------------:|
| ours | 0.00 | 0.00 | 0.00 |
| support_rerank | 0.26 | 0.13 | 0.43 |
| pair | 0.05 | 0.13 | 0.00 |
| both | 0.26 | 0.13 | 0.43 |
| both_l1fallback | 0.53 | 0.63 | 0.57 |
| merge | 0.53 | 1.00 | 0.29 |
| both_merge | 0.58 | 1.00 | 0.29 |

**G4 解读**：Fine 上 merge 强、校准有限；Coarse 不得宣称重排根治；merge **未进默认 harness**。

## 默认 harness 接入

- `run_diagnosisarena_downstream_top2.py`：默认 `--calibration-arm both_l1fallback`，`gold_leaf_ids=[]`
- `run_diagnosisarena_pipeline_staged.py`：annotate 透传
- Explainer：`CURRENT_HIERARCHICAL_DIAGNOSIS_RESEARCH_PIPELINE_EXPLAINER.md` §6.1

## 单元测试

`pytest tests/test_topk_calibration.py`：7 passed。

## 明确未做 / 已否决

- Coarse **真** L3 进树 + 局部 joint（伪叶 rematch 未能在 Coarse 子集超过仅校准）  
- 默认 harness 接入单独 `subdivide*`（伤 @2 → REJECTED）  
- mapper 模式对齐重评  
- 不以金标感知 G2 或金标盲强冻结 Top2 去追烟测 0.69  

粒度支线全量结果见 [`granularity_branch_smoke_report.md`](granularity_branch_smoke_report.md)。