# L1 金标召回烟测报告（Track B）

**队列**：`all100`  
**生成**：`2026-07-23T17:12:44.988163+00:00`  
**机制**：R0=`v1_auto_parent`；R1=`v2_leaf_parent`；R2=bind-repair→`v1_auto_parent`
**生产默认**：仍 **off**（仅离线后处理 / 评测协议）

## 主表

| 臂 | n | AutoCoverage | TreeParentPresent | L1CandidateRecall | mapper @1 | mapper @2 | bind率 |
|----|--:|-------------:|------------------:|------------------:|----------|--------:|--------:|-------:|
| R0 | 100 | 0.800 | 0.890 | 0.890 | 0.590 | 0.780 | 0.000 |
| R1 | 100 | 0.890 | 0.890 | 0.890 | 0.590 | 0.780 | 0.000 |
| R2 | 100 | 0.950 | 0.890 | 0.890 | 0.560 | 0.670 | 0.160 |

## 漏斗桶

- **R0**：`{'MAPPER_UNBIND': 15, 'L1_PRESENT_OK': 80, 'TREE_PARENT_ABSENT': 5}`
- **R1**：`{'L1_PRESENT_OK': 89, 'TREE_PARENT_ABSENT': 11}`
- **R2**：`{'L1_PRESENT_OK': 95, 'TREE_PARENT_ABSENT': 5}`

## 门控

- **决策**：`PASS`
- **推荐默认整合**：`R1_v2_leaf_parent_audit`（生产 mapper 仍 off）
- **R1/R2 pass**：`True` / `False`
- **理由**：
  - R1 auto_coverage +0.090 (>=+0.08)
  - R2 auto_coverage +0.150 (>=+0.08)
  - R1 MAPPER_UNBIND/miss drop 100.0% (n0=15→0)
  - R2 MAPPER_UNBIND/miss drop 100.0% (n0=15→0)
  - R2 mapper_opt2 drop 0.110 > 0.02 (R2 integration blocked)
  - PASS via R1 only; R2 not cleared for default integration

## 说明

- R1 的 AutoCoverage 列使用 `v2_leaf_parent` 定义的 coverage（叶反推父 ∈ `l1_posteriors`）。
- R2 的 mapper @k 为修复金标叶后相对 joint 叶序的重匹配，与 R0 官方落盘 @k 对照作护栏。
- Track C / gap-fill / 生产 mapper 默认未改。

