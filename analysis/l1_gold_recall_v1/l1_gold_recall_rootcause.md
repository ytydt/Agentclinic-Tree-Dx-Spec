# L1 金标召回：根因综合

**输入**：[`l1_gold_recall_audit.md`](l1_gold_recall_audit.md)、[`ours_l1_recall_mechanism_card.md`](ours_l1_recall_mechanism_card.md)、[`external_l1_recall_transfer_cards.md`](external_l1_recall_transfer_cards.md)、[`l1_gold_recall_related_work.md`](l1_gold_recall_related_work.md)

---

## 1. 主结论（完成定义句）

**80% AutoCoverage 缺口主因是映射假 MISS（`MAPPER_UNBIND`，18/20）；真缺父（`TREE_PARENT_ABSENT`）仅 2 例；父在树但未入 L1 候选（`PARENT_NOT_IN_L1_SET`）本批为 0。**

---

## 2. 根因 taxonomy

| ID | 根因 | 证据强度 | 作用层 | 默认对策轨 |
|----|------|----------|--------|------------|
| R1 | Mapper 未绑金标叶 / 关系标 unrelated，导致 `v1_auto_parent` 空 | **高**（20/20 matched=False；13/20 树有近义叶） | 评测绑定 | **Track B：映射修复** |
| R2 | L1 粗标签无法与具体诊断同义命中（无叶时的 fallback 失效） | 高 | 评测启发式 | Track B：叶反推父 / 放宽同义 |
| R3 | 建树轴与金标诊断轴错位 | 中（2/20） | 树构建 | Track C 或轴校正 |
| R4 | L1 BFS 封闭不加族「挤出」金标父 | **低/否定**（0 例 PARENT_NOT_IN_L1_SET） | L1 更新 | 不作为 coverage 主因 |
| R5 | 排序弱（family misrank） | 上轮已证（另 10 例）；**非本轮 20 MISS** | 冻结后排序 | 见 rank-gap；与召回解耦 |

---

## 3. 对「软上界」叙事的修正

先前：若修满 coverage，compat @1 软上界约 0.80。  
修正：那 20 例里多数 **树侧父已在**；修的是 **绑定与度量**，不是「长出新 L1」。  
真扩族的期望收益应按 **~2 例量级** 估，而非 +0.20 AutoCoverage 幻想。

---

## 4. 与 compat_parallel / L1-Calib-B12 解耦

| 组件 | 关系 |
|------|------|
| compat_parallel | 下游粒度；不解决 mapper 假 MISS |
| L1-Calib-B12 | 排序；Pilot REJECT；**不**修 coverage |
| 本设计 Track B | 建树后、评测前的 **绑定/父集**；或建树 gap-fill（有限） |
| Track C | 建树前/中扩族；与排序臂分列 |

---

## 5. 残余风险

- 半自动父判定偏乐观 → 真缺父可能略多于 2。  
- 映射修复可能抬 option 但不抬临床 TreeParentPresent（本来就有）。  
- Track C 无归一时会污染树 MECE。

产出完成：本文件。
