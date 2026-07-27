# L1 family calib smoke report

**备份**：`backups/compat_parallel_before_l1_calib_20260723_230115/`（`MANIFEST.sha256` 已校验）  
**代码**：[`scripts/paper/l1_family_calibration.py`](../../scripts/paper/l1_family_calibration.py)、[`run_l1_calib_smoke.py`](../../scripts/paper/run_l1_calib_smoke.py)  
**日志**：`logs/diagnosisarena_d2_m01_v1/l1_calib_v1/`（初轮）+ `logs/diagnosisarena_d2_m01_v1/l1_calib_ablation_v1/`（消融）  
**Harness**：`--l1-calib` 默认 **off**（本轮未改生产默认）

口径：离线在冻结 `l1_posteriors` 上跑 Track B；**不重跑 L2/mapper**。家族指标用 `v1_auto_parent`。

---

## Pilot24（初轮，`tau_post=0.15`，`M=5`）

| arm | family @1 | family @2 | MRR | coverage | MISRANK | skip_gate |
|-----|----------:|----------:|----:|---------:|--------:|----------:|
| ours | 0.583 | 0.667 | — | — | 2 | 0.00 |
| support | 0.583 | 0.667 | — | — | 2 | 0.79 |
| pair | 0.583 | 0.667 | — | — | 2 | 0.79 |
| **b12** | **0.583** | **0.667** | — | — | **2** | **0.79** |

Option 代理（L1-prior-only）各臂与 ours 同点（约 @1 0.58 / @2 0.67）。

### 门控判定（相对 ours）

| arm | 结果 | Δ@1 | Δ@2 | MISRANKΔ |
|-----|------|----:|----:|---------:|
| b12 | **REJECT** | +0.000 | +0.000 | 0 |
| support | REJECT | +0.000 | +0.000 | 0 |
| pair | REJECT | +0.000 | +0.000 | 0 |

通过门要求：Δ@1≥+0.04 **或** MISRANK 净减≥3，且 Δ@2≥−0.01。

### 归因

1. **门控过严（主因）**：Pilot24 仅 **5/24** 例 Top1–Top2 后验差 ≤ 0.15，故 ~79% 例直接跳过校准。  
2. **作用例无抬过 @2**：非跳过例中，MISRANK 仍为 2。  
3. **不宣称端到端修好**：未重跑 L2；mapper option 不变属预期。

**结论**：`L1-Calib-B12` 在 Pilot24 **未过门** → **不**建议改为生产默认。

---

## all100 live（compat + B12 → typed_llm）

报告：[`../l1_gold_recall_v1/smoke_live_option/b12_compat_all100_report.md`](../l1_gold_recall_v1/smoke_live_option/b12_compat_all100_report.md)

| cohort | typed @1 | typed @2 |
|--------|---------:|---------:|
| Pilot24 | 0.750 | 0.833 |
| Remain76 | 0.684 | 0.776 |
| **all100** | **0.700** | **0.790** |

相对正式 compat rematch **0.72/0.78**：Δ@1=−0.02 → **REJECT**；**不**改 `DEFAULT_L1_CALIB`（仍为 `off`）。

---

## 消融矩阵（Pilot24）

机器可读：[`l1_calib_ablation_summary.json`](l1_calib_ablation_summary.json)  
CLI：`--tau-post`；`--force-misrank`（仅对 case 4、21 绕过门控）。  
`tau_post=0.0` 语义：**永不跳过**（全量校准消融）。

| 设置 | b12 @1 | b12 @2 | MISRANK | skip_gate | 门控 |
|------|-------:|-------:|--------:|----------:|------|
| tau=0.15 | 0.583 | 0.667 | 2 | 0.79 | **REJECT**（Δ=0） |
| tau=0.05 | 0.583 | 0.667 | 2 | 0.79 | **REJECT**（与 0.15 同批近并列例） |
| tau=0.0（全量） | **0.542** | **0.583** | **4** | 0.00 | **REJECT**（反害） |
| force-MISRANK + tau=0.15 | 0.583 | 0.667 | 2 | 0.79 | **REJECT**（4/21 仍 MISRANK） |

**消融结论**：放宽 `tau_post` 或强制 MISRANK **均不能**过门；全量校准（tau=0）反而降低 family @1/@2 并增加 MISRANK。正式关闭「B12 可救 option / family」叙事；生产默认保持 **off**。

---

## all100

**跳过**（Pilot 未过门；消融仍 REJECT）。

---

## 复现

```bash
PYTHONPATH=src:scripts/paper:scripts \
  python3 -u scripts/paper/run_l1_calib_smoke.py \
  --cohort pilot24 --workers 6 \
  --model meta-llama/llama-3.3-70b-instruct \
  --tau-post 0.15

# 消融
PYTHONPATH=src:scripts/paper:scripts \
  python3 -u scripts/paper/run_l1_calib_smoke.py \
  --cohort pilot24 --tau-post 0.0 --output-dir logs/diagnosisarena_d2_m01_v1/l1_calib_ablation_v1/tau000

PYTHONPATH=src:scripts/paper:scripts \
  python3 -u scripts/paper/run_l1_calib_smoke.py \
  --cohort pilot24 --tau-post 0.15 --force-misrank \
  --output-dir logs/diagnosisarena_d2_m01_v1/l1_calib_ablation_v1/force_misrank_tau015
```

单测：`python3 tests/test_l1_family_calibration.py`
