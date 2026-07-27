# 失败分型：无效 vs 反害 → 再归因

**协议**：[`protocol.md`](protocol.md)  
**原则**：先看 live option Δ（相对 compat），再看召回漏斗桶，再看叶集/映射差分。禁止一上来改排序或扩族。

---

## 1. 顶层二分

| 分型 | 判据 | 本批归属 |
|------|------|----------|
| **反害** | typed/正式 option @1 或 @2 相对 compat **下降** | **R2 typed**（主轴） |
| **无效** | 目标指标不动，或仅度量变好而 option 不变 | R1、R3、R4/R5 |
| **伪增益** | 非正式口径抬点 | R2 事后 rematch |
| **旁证未过门** | 非召回臂；Δ@1 未达宣称门 | B12 all100 typed |

---

## 2. 五类失败模式（判别规则）

### M1 度量错位

- **现象**：把 AutoCoverage / `v1_auto_parent` 假 MISS 当成「树上缺 L1」。  
- **判别**：`MAPPER_UNBIND` 占主导；树上已有可接受父 / 近义叶；`PARENT_NOT_IN_L1_SET=0`。  
- **本批**：18/20 MISS = UNBIND（[`../l1_gold_recall_v1/l1_gold_recall_audit.md`](../l1_gold_recall_v1/l1_gold_recall_audit.md)）。  
- **对策轨**：度量双列 / 绑定修复规格；**不是**默认扩族。

### M2 绑定层过宽（R2 主嫌疑）

- **现象**：全树叶注入 → typed mapper 重跑后 option 大跌。  
- **判别**：`n_extra` 大；compat@1=1→typed@1=0 例占比高；Top-k 叶 Jaccard 低或金标秩恶化。  
- **本批**：mean_extra_leaves≈16.1；@1 0.72→0.42。  
- **对策轨**：受限注入（I1）、关系护栏（I2）。

### M3 轴错位不可 gap-fill

- **现象**：hints 已含金标/近金标串，L1 轴仍错；gap_fill 已开仍 ABSENT。  
- **判别**：临床 `TREE_PARENT_ABSENT`；provenance `recall_hints`；goldish∈hints 但 L1 关键字不容纳。  
- **本批**：67、231；R3 冻结已 `recall_hints_gap`。  
- **对策轨**：轴白名单（I4），非再开 gap_fill。

### M4 上界 ≠ 可实现

- **现象**：外部基线病名「可容纳」金标（上界 PASS），inject 后 BranchCreator 仍不造对应 L1。  
- **判别**：`tree_parent_present_upper_bound=true` 且 live `accommodates=false`。  
- **本批**：R4 231、R5-mac 67。  
- **对策轨**：轴/强制极，而非只堆 hints。

### M5 协议混比

- **现象**：用 rematch 对比 typed、Pilot 外推 all100、merge_only 坍缩叶集上的 option。  
- **判别**：对照臂协议字段不一致；或 merge_only 率极高仍宣称「同栈增益」。  
- **本批**：B12 rematch 0.458 无效；R2 事后 0.75/0.88 伪增益。  
- **对策轨**：分表硬规则（I5）。

---

## 3. 归因决策树（操作）

```text
option_Δ vs compat?
├─ 下降 → 反害 → 做 R2 风格叶集/映射差分（M2 优先）
├─ 不变且 coverage 仅度量升 → 无效-度量（M1/R1）
├─ 不变且临床 ABSENT 仍在 → 无效-轴（M3/M4）
└─ 上升但口径非正式 → 伪增益（M5）→ 拒绝宣称
```

---

## 4. 与既有根因文档的关系

- 召回缺口主因（绑定假 MISS）：[`../l1_gold_recall_v1/l1_gold_recall_rootcause.md`](../l1_gold_recall_v1/l1_gold_recall_rootcause.md) — **解释无效叙事**。  
- 本包补充：**干预落地后为何反害/仍无效**（尤其 R2 typed），并导向门控改进规格。
