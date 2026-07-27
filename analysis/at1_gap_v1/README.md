# 阶段 6：验收清单与汇总

## Checklist（对照计划阶段 6）

- [x] 失败分型覆盖 A 集 ≥90%，且含 Fine / Coarse 独立标签  
  - A=19；预填+Agent 审核覆盖 19/19；见 `at1_failure_taxonomy.tsv`、`granularity_audit_sheet.jsonl`
- [x] `l2_vs_l1` 增益表完整（全量 + A 子集）  
  - `l2_vs_l1_metrics.tsv`、`l2_vs_l1_summary.json`、`l2_vs_l1_prior_gain.md`
- [x] Fine 挤占比例 + 合并模拟 Δ@1  
  - Fine 自动 13/19；主模式 8/19；合并模拟见 `tree_granularity_fine_crowd.md`
- [x] Coarse：自动检出数、Agent 审核通过数、细分上界  
  - 自动 10；通过 7；L3 上界 7 例；见 `tree_granularity_coarse_multi_option.md`
- [x] 融合方案含 **不伤害 Top2** 护栏；粒度支线去留有数据依据  
  - `design_constraints.md`、`hybrid_scoring_design_v1.md`

## 关键结论（一页）

| 结论 | 证据 |
|------|------|
| @1 转化弱于基线（校准前） | P(@1\|@2)=0.756 vs MAC 0.910 |
| 主因是粒度 + 校准，非单纯缺召回 | A 集 Fine+Coarse≈79% |
| L2 组间未显示稳健 @1 增益 | 叶序重匹配 Δ@1=−0.06；A 集 L1-prior 虚拟 @1≈0.63 |
| 可迁移算子 | Dual support 计数 + MAC pair；须封闭候选 |
| **正式校准数字（harness，无金标 G2）** | **both_l1fallback @1=0.65 @2=0.79 MRR=0.72** |
| **正式组合（compat_parallel）** | **@1=0.72 @2=0.78 MRR=0.75**（分列，见 `merge_calib_compat_report.md`） |
| deepen 组合（旧默认） | @1=0.67 @2=0.78；串行 merge×强校准会互伤 |
| 烟测 0.69 | 金标感知 G2 神谕消融，不作主结果 |
| 金标盲冻结 Top2 | 不作弊；实测 @1=0.59/@2=0.79，不作默认（见 `gold_blind_top2_freeze_report.md`） |
| 离线 merge 上界 | @1=0.68 @2=0.78；`subdivide*` 伤 @2 → REJECTED |

## 交付物索引

| 文件 | 阶段 |
|------|------|
| `protocol_alignment.md` | 0 |
| `at1_failure_taxonomy.tsv` / `*_report.md` / `case_sets.json` | 1 |
| `ours_joint_calibration_cause.md` | 2a |
| `l2_vs_l1_prior_gain.md` (+ tsv/json) | 2b |
| `tree_granularity_*.md` / `granularity_*` / audit_packets/ | 2c |
| `baseline_conversion_mechanisms.md` | 3 |
| `design_constraints.md` | 4 |
| `hybrid_scoring_design_v1.md` | 5 |
| `calibration_smoke_report.md` / `granularity_branch_smoke_report.md` | 校准 / 粒度烟测 |
| `merge_calib_interaction_rootcause.md` / `merge_calib_compat_report.md` | merge×calib 交互与兼容 |
| `compat_parallel_mechanism_explainer.md` | **默认后处理：算法、门控、起效根因** |
| 本文件 | 6 |

## 下一跳（另开任务）

- [x] 24 例烟测校准臂（不动树）→ 见 [`calibration_smoke_report.md`](calibration_smoke_report.md)
- [x] Merge 离线原型（`AdaptiveMergeSiblings`）
- [x] 100 例全量（护栏通过后）；更新方法 vs 基线表（同报告）
- [x] Subdivide 伪 L3 原型 + Deepen 调度 + harness 挂载 → [`granularity_branch_smoke_report.md`](granularity_branch_smoke_report.md)
- [x] Merge×Calibration 并行兼容（`compat_parallel`）→ [`merge_calib_compat_report.md`](merge_calib_compat_report.md)
- [x] 机制专档（算法 / 门控 / 起效根因）→ [`compat_parallel_mechanism_explainer.md`](compat_parallel_mechanism_explainer.md)
- [ ] Coarse 真 L3 进树 + 局部 joint（伪叶未能在 Coarse 子集上超过仅校准）
- [ ] （可选）本方法 `typed_llm_disagreement_rag` 重评
- [x] 将通过臂挂入生产 joint→mapper 路径（默认 `--granularity-mode compat`）