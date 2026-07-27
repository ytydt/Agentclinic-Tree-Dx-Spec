# L1 排序偏弱：根因综合

**证据来源**：[`l1_rank_gap_audit.md`](l1_rank_gap_audit.md)、[`ours_l1_ranking_mechanism_card.md`](ours_l1_ranking_mechanism_card.md)、[`external_l1_transfer_cards.md`](external_l1_transfer_cards.md)、[`l1_related_work_transfer.md`](l1_related_work_transfer.md)

---

## 1. 「偏弱」精确定义（本队列）

| 层 | 数字 | 解读 |
|----|------|------|
| 家族序（全量） | @1 **0.60** / @2 **0.70** | 主终点偏弱 |
| 家族序 \| coverage | @1 **0.75** / @2 **0.875** | 排除自动绑父失败后仍有排序缺口 |
| option 代理 | @1 0.60 / @2 **0.69** | @2 远低于官方 mapper 0.78 |
| 漏斗 | MISS 20 / MISRANK 10 / OK∧option_miss 10 / OK∧hit 60 | 多瓶颈并存 |

**结论句**：偏弱首先是 **L1 家族排序与（自动规则下的）金标父绑定** 问题；其次是 **代表叶→option** 衔接；不能用 L2 leaf calib 的涨点替代。

---

## 2. 根因 taxonomy × 证据强度

| ID | 根因 | 证据 | 强度 | 应对轨道 |
|----|------|------|------|----------|
| R1 | 冻结后验缺乏显式破平（无 support 计数 / pair） | 机制卡片；文献 Dual/MAC；10 例 misrank | 高 | **B** Support/Pair |
| R2 | 选择过早 abstain → 证据不足 | 68% abstain；misrank 9/10 abstain | 中 | **B** Reflect-lite / 调 abstain |
| R3 | 金标叶未映射 → 无法定义/命中父（表象 L1_MISS） | 20 例 parent_source=none 且 mapper @2=0 | 高（对「假 L1_MISS」） | 映射/召回；**非**纯重排 |
| R4 | 近义多 L1 父稀释与乐观 @k | 平均可接受父 2.33 | 中（待盲法） | 父集审核；粒度 |
| R5 | ordinal 更新与叙事特异家族耦合 | TALP 17 例假说 + 本队列 misrank | 中 | **B** 近并列门控重排 |
| R6 | 家族对了但代表叶/映射错 | `L1_OK_OPTION_MISS`=10 | 高 | 代表叶策略；非 L1 重排唯一解 |
| R7 | 未启用多采样/会诊破平 | 外部机制卡片 | 中（潜力） | **C** council/SC |
| R8 | 真召回缺口（树上无父） | 需盲法；当前与 R3 混杂 | 未分清 | **C** OpenRegen（分列） |

---

## 3. 因果草图

```text
证据选择(anti-anchor, 高 abstain)
  → ordinal 对称更新（无条数破平）
  → 冻结 L1 后验
      ├─ misrank（R1/R2/R5）──► family @1 受损
      ├─ 映射未绑叶（R3）──► 审计表象 L1_MISS
      └─ 家族对、代表叶错（R6）──► option 代理仍弱
下游 joint + mapper 可抬 option @2，但不修复 family 序本身
```

---

## 4. 设计优先级（供 design_v1）

1. **必做 Track B**：冻结后 L1-SupportRerank + 近并列 L1-Pair。  
2. **条件 Track B**：Reflect-lite / closed RRF。  
3. **分列 Track C**：MAC-council、Self-Refine、OpenRegen（仅在父召回问题坐实后）。  
4. **并行非 L1**：映射覆盖（R3）与代表叶（R6）——写入验收分列，避免归因错误。
