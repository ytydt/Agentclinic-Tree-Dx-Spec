# L1 金标召回 **Live** 烟测（标注前注入）

**队列**：`all100`  
**生成**：`2026-07-23T17:25:47.611333+00:00`  
**机制**：R0 官方落盘；R1=`v2_leaf_parent`（度量）；R2=全树叶注入+bind-repair+`_rank_and_expand`（标注前）
**生产默认**：仍 **off**

## 主表

| 臂 | n | AutoCoverage | TreeParentPresent | mapper @1 | mapper @2 | MRR | bind率 | 均增叶 |
|----|--:|-------------:|------------------:|----------|--------:|--------:|----:|-------:|-------:|
| R0 | 100 | 0.800 | 0.890 | 0.590 | 0.780 | 0.688 | 0.000 | 0.0 |
| R1 | 100 | 0.890 | 0.890 | 0.590 | 0.780 | 0.688 | 0.000 | 0.0 |
| R2 | 100 | 0.960 | 0.890 | 0.610 | 0.880 | 0.769 | 0.730 | 13.4 |

## 漏斗

- **R0**：`{'MAPPER_UNBIND': 15, 'L1_PRESENT_OK': 80, 'TREE_PARENT_ABSENT': 5}`
- **R1**：`{'L1_PRESENT_OK': 89, 'TREE_PARENT_ABSENT': 11}`
- **R2**：`{'MAPPER_UNBIND': 1, 'L1_PRESENT_OK': 96, 'TREE_PARENT_ABSENT': 3}`

## 门控

- **决策**：`PASS`
- **推荐**：`R2_live_inject_bind_repair`
- **R1/R2 pass**：`True` / `True`
- **理由**：
  - R1 auto_coverage +0.090
  - R2 auto_coverage +0.160
  - R2 live mapper_opt2 +0.100 (guard drop<=0.02: OK)

## 与离线 smoke 的区别

- 离线 R2 仅用 joint `final_ranking` 重匹配 → 树上有叶但未入 joint 时 option 虚假下跌。
- 本 live R2 在标注前把 **shared_trees 叶**注入叶目录并赋 `joint_rank`，再 bind-repair + 生产 `_rank_and_expand`。

