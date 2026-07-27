# Targeted L2 Gapfill 配置冒烟复测（2026-07-26）

状态：研究轨复测笔记（非正式 claim）  
范围：MedBullets AB 冻结树（n=17）；**非** DA/OX 标准 harness

## 1. 测了什么

| 检查 | 命令 / 入口 | 结果 |
|------|-------------|------|
| 单元测试 | `pytest tests/test_l2_targeted_gapfill_{hybrid,gates,global_reassign}.py` | **28 passed** |
| evaluate 复跑 | 三脚本 `evaluate --resume`（bootstrap=200） | **exit 0**；leakage OK |
| generate 冒烟 | `hybrid generate --limit 1 --replicates 1 --resume` | **exit 0**（`mb11_pancoast` 缓存命中） |

泄漏审计（三套一致）：`generation_opened_fixture=false`，`b_zero_parent_retrieval=true`。

## 2. 指标（all17 vs 冻结 C）

| 变体 | 代表臂 | top1 | top2 | gold_l2_cov | added/case | bad_parent | vs C Δtop2 |
|------|--------|------|------|-------------|------------|------------|------------|
| C（hybrid 基线） | C | 0.333 | 0.510 | 0.765 | 0 | 0 | — |
| hybrid | ALL_B_b1 | **0.392** | **0.588** | 0.824 | 0.47 | 0.458 | **+7.8pp** |
| gates | ALL_B_b1_PG_SD | 0.373 | 0.569 | 0.824 | 0.31 | 0.25 | +5.9pp |
| global_reassign | ALL_B_b1_GR_PG | 0.373 | **0.588** | **0.882** | 1.78 | **0.022** | +5.9pp* |

\* GR 的 C 基线略不同（top2=0.529）；相对该 C：Δtop2=+5.9pp。  
GR 字典序最佳臂：`ALL_B_b1_GR_PG`（`research_only` / `descriptive_research_only`）。

## 3. 生产门控

三套 `production_promote=false`（`pilot_support_only`）。  
主阻挡：`duplicate_le_10pct`（**legacy source-pool 冗余率**；gates 审计显示 final-tree semantic duplicate≈0）。  
A 源臂额外失败：C 成功保持 / top2 CI。

→ **研究可用、协议仍不可 promote**（与可用性评估一致）。

## 4. 与 Config A 的关系（复测语境）

- Config A `l2_recall_gap_fill` 已在身份配置里为 **true**（生成期补叶仍在上游 C 树里）。
- Targeted gapfill 是在该 C 树之上的 **二次定向补叶**；本次复测确认管线可复现，但 **未** 接线 DA/OX 主表。

## 5. 未做

- OX C-class 限量子集适配（需新 adapter；对抬开放 Recall 更对口）
- DA all100 option@1 副作用门控
- 全新 live 全量 regenerate（仅 1-case resume 冒烟）
