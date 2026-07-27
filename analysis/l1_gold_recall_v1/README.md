# L1 金标召回调研包（`l1_gold_recall_v1`）

| 阶段 | 状态 |
|------|------|
| 调研 A–G | 完成 |
| 事后 rematch（字符串 repair） | 乐观上界；**不可作正式增益** |
| **typed mapper 重跑（R2）** | **完成 → REJECT，反害** |
| **R1 父集** | **无效**（仅度量；option 不变） |
| **R3 gap-fill** | **REJECT**（见下） |
| **R4/R5 Track C** | **REJECT 默认生产**（ABSENT live 未起效） |
| **L1-Calib-B12** | **REJECT**（消融 + all100 live typed 未过门；默认仍 off） |
| **live option 实测** | **完成（含 all100）** |
| **无效/反害调查框架** | **[`../l1_recall_failure_v1/`](../l1_recall_failure_v1/)**（漏斗 + 假设电池 + 改进门控） |
| **I1 受限注入 Pilot** | **REJECT**（@1 0.417 vs Pilot compat 0.75；mean_extra 3.3；默认仍 off）→ [`../l1_recall_failure_v1/smoke_i1_restricted/`](../l1_recall_failure_v1/smoke_i1_restricted/) |

**度量双列（I3）**：AutoCoverage 与 TreeParentPresent 分列；假 MISS（UNBIND）不驱动默认注入。见 [`../l1_recall_failure_v1/protocol.md`](../l1_recall_failure_v1/protocol.md)。

## Live option @1/@2（compat 基线 × 测试臂）

报告：[`smoke_live_option/`](smoke_live_option/)  
all100 门控：[`smoke_live_option/b12_compat_all100_report.md`](smoke_live_option/b12_compat_all100_report.md)

| 臂 | 队列 | 协议 | @1 | @2 |
|----|------|------|---:|---:|
| compat_parallel | all100 | rematch | **0.72** | **0.78** |
| R3（=compat，gap_fill 已开） | all100 | rematch | **0.72** | **0.78** |
| R4/R5 ABSENT {67,231} | 2 | typed mapper | **0.00** | **0.00** |
| B12+compat | Pilot24 | typed_llm | 0.750 | 0.833 |
| B12+compat | Remain76 | typed_llm | 0.684 | 0.776 |
| **B12+compat** | **all100** | **typed_llm** | **0.700** | **0.790** |

- 相对正式 compat rematch（0.72/0.78）：Δ@1=**−0.02**、Δ@2=+0.01 → **REJECT**；**不**改默认 harness。  
- `--l1-calib` 仍默认 **`off`**（opt-in `b12` 可手动开；回退即保持/显式 `--l1-calib off`）。  
- merge_only≈95% 叶坍缩；97/198 空 ranking；正式宣称不可用。

## 后 R1/R2：R3 / Track C / B12 评测

脚本：[`scripts/paper/run_r3_r45_eval.py`](../../scripts/paper/run_r3_r45_eval.py)

### R3 gap-fill — **REJECT**

报告：[`smoke_r3/`](smoke_r3/)

- **UNBIND（18）**：父已在树；gap-fill 不能修 mapper AutoCoverage → 不作 coverage 主杠杆。  
- **ABSENT（67、231）**：冻结建树已是 `branch_mode=recall_hints_gap`（**gap_fill 已开**），临床仍真缺父 → R3 已应用仍失败。  
- live option：**等于** compat 基线 0.72/0.78（无增量）。  
- 生产：保持现状（建树已开 gap_fill；无需再宣称增益）。

### R4/R5 Track C — **REJECT 默认生产**

报告：[`smoke_track_c/`](smoke_track_c/)

| 臂 | 上界（ABSENT） | Live inject |
|----|----------------|-------------|
| R4 i-MedRAG | PASS_UPPER（仅 231：`Urothelial carcinoma`） | **未起效**（仍皮肤/副肿瘤轴） |
| R5 Dual | REJECT_UPPER | 跳过 |
| R5 MAC | PASS_UPPER（仅 67：`Severe Infection`） | **未起效**（`Infectious Process` 未到 septic-shock） |

- ABSENT 官方 mapper option 仍为 **0/0**。  
- **禁止**外推全表 AutoCoverage；默认生产路径 **REJECT**。

### L1-Calib-B12 — **REJECT**（排序臂，与召回解耦）

报告：[`../l1_rank_gap_v1/l1_calib_smoke_report.md`](../l1_rank_gap_v1/l1_calib_smoke_report.md)、[`../l1_rank_gap_v1/l1_calib_ablation_summary.json`](../l1_rank_gap_v1/l1_calib_ablation_summary.json)、[`smoke_live_option/b12_compat_all100_report.md`](smoke_live_option/b12_compat_all100_report.md)

- tau∈{0.15,0.05}：零增益；tau=0：**反害**。  
- **all100 live typed（compat+b12）**：@1/**0.700** @2/0.790 vs compat rematch 0.72/0.78 → **REJECT**（Δ@1=−0.02）。  
- 生产默认：**保持 `--l1-calib off`**；未纳入默认 harness。

## 其他产物

- [`smoke_compat/`](smoke_compat/)：compat×事后 R2（上界对照）  
- [`smoke_live/`](smoke_live/)：无 compat 的 inject rematch  
- Harness opt-in：`--leaf-inject-bind-repair`（annotate R2 扩叶；默认 off）  
- Harness opt-in：`--synonym-bind-repair`（mapper Approach A 空绑修绑；默认 off；live ~0.81/0.93）  
  → 见 [`../l1_recall_failure_v1/smoke_synonym_bind_live/`](../l1_recall_failure_v1/smoke_synonym_bind_live/)
