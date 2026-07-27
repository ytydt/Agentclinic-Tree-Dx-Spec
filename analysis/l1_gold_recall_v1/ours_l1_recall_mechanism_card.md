# 本方法 L1 / 树构建：召回失败机制卡片

**对照代码（只读）**：[`l1_evidence_bfs.py`](../../src/agentclinic_tree_dx/l1_evidence_bfs.py)、[`controller.py`](../../src/agentclinic_tree_dx/controller.py)（`_build_branch_candidates` / `_gap_fill_branches` / `force_expand_all_l1`）、[`config.py`](../../src/agentclinic_tree_dx/config.py)  
**审计结论入口**：[`l1_gold_recall_audit.md`](l1_gold_recall_audit.md)

---

## 1. L1 候选从何而来

| 阶段 | 机制 | 是否开放加族 |
|------|------|--------------|
| 建树 | BranchCreator +（可选）`enable_branch_knowledge` 的轴域 `mandatory_coverage` / recall-hints | **是**（仅此阶段决定族集合） |
| 可选 gap-fill | `branch_recall_gap_fill`：核对 mandatory 域是否都有分支，缺则补 | 仅补 **预声明域**，非任意疾病名 |
| L1 BFS | 在 **冻结** L1 差分上做证据选择与后验更新 | **否**（模块头注释：不创建分支、不加族） |
| `force_expand_all_l1` | 对每个已有 L1 强制扩 L2 | 不新增 L1，只保证每族有 L2 |
| L2 gap-fill / exemplars / 配置 A | 依赖「已有 L1 父」做 per-parent 召回 | 父集封闭 |

**要点**：运行时 L1 集合在建树结束时基本冻结；后续算子（含 B12 类排序）**无法**修复「族从未出现」。但本轮 20 例假 MISS 中，可接受父 **几乎都已在** `l1_posteriors`——瓶颈不在 BFS 挤出，而在 **评测绑定** 与少数 **建树轴错位**。

---

## 2. 失败模式 × 代码位点

| 模式 | 代码/数据位点 | 本批 20 例 |
|------|---------------|------------|
| 叶在树、mapper 未绑 → AutoCoverage 假 MISS | `RelationAwareAnswerMapper` 投影；`v1_auto_parent` 只认 matched 叶父或 L1 标签同义 | **主导（18）** |
| 建树轴与金标诊断轴错位 | `_build_branch_candidates` / syndrome axis / LLM 分区 | **2**（67、231） |
| 金标只在 L2、父标签不对轴 | SubBranchCreator 挂错父 | 本批未单列；假 MISS 中父轴多数临床可接受 |
| BFS 不开放加族 | `l1_evidence_bfs` 设计约束 | 对假 MISS **无关**；对真缺父 **相关但需建树前扩** |
| gap-fill 默认关 | `branch_recall_gap_fill=False` | 真缺父时无自动补轴 |

---

## 3. 可证伪假说

| ID | 假说 | 预期证据 | 本轮结果 |
|----|------|----------|----------|
| H1 | 自动 `L1_MISS` 主要是 mapper 叶未绑定，而非树上无父 | 半自动 TreeParentPresent ≫ AutoCoverage | **支持**（18/20 UNBIND） |
| H2 | 金标父在树但不在 `l1_posteriors` | `PARENT_NOT_IN_L1_SET`>0 | **不支持**（0） |
| H3 | 金标只在 L2 且无可接受 L1 轴 | 叶在树但所有 L1 临床不可接受 | **少数**：主要为轴错位整树（67/231），非「有叶无父」 |
| H4 | BFS / 排序把 gold 父挤出候选集 | MISS 例的可接受父不在后验 | **不支持** |
| H5 | mapper `relation_type` 过严（unrelated）导致假 MISS | matched=False 且树上有近义叶 | **支持**（多例 exact leaf + unrelated） |
| H6 | `labels_synonymish` 无法把粗 L1 名对齐到具体金标病名 | 无叶绑定时 parent_source 仍 none | **支持**（粗家族名难与具体诊断同义命中） |
| H7 | `force_expand` / Config A 依赖已有 L1，放大建树召回缺口 | 真缺父例下游叶也偏离金标轴 | **条件支持**（231 副肿瘤轴 vs 原发癌） |
| H8 | 打开 `branch_recall_gap_fill` 可修多数 AutoCoverage | gap-fill 只补 mandatory 域 | **预期 REJECT 多数**：18 例父已在 mandatory 轴上 |

---

## 4. 对设计的直接含义

1. **不要**把 L1-Calib-B12（排序）或「加宽 BFS」当作修 0.80 AutoCoverage 的主杠杆。  
2. **要**把「从已有 L2 叶反推父并修复评测绑定」算作 Track B 召回/coverage 修复（实为 **度量与映射**）。  
3. 真扩族（Track C）预算应锚定在 **~2%** 量级真缺父 + 未来盲法修订，而非 20%。

产出完成：本文件。
