# 外部机制 → L1 **召回**可迁移卡片（Track B / C）

**前提**：MAC/Dual 无显式 L1；i-MedRAG（B17，[`baselines/imedrag/`](../../baselines/imedrag/)、`run_b17`）是迭代 follow-up + 共享 KB 的 **flat** 诊断协议。上轮 **排序**上移（SupportRerank/Pair）**不算**本轮完成。  
**审计前提**：20 例自动 MISS 中 **90% 为 `MAPPER_UNBIND`** → 开放扩族 **不是**修 AutoCoverage 的默认主轨。

硬过滤：金标选臂。软过滤：私有不可复现 KG → 只借鉴环路，沿用共享 KB。

---

## Track B — 封闭召回 / 去假 MISS（默认整合主轨）

| 来源 | 与召回相关的机制 | 上移到本方法 L1 的设想 | 判定 |
|------|------------------|------------------------|------|
| 本方法内部 | 从 L2 叶反推父；轴极 / gap-fill 仅补树内缺口 | **Leaf→Parent 审计绑定**：用树叶近义命中修复 `v1_auto_parent`；可选 `branch_recall_gap_fill` 仅补 mandatory 空域 | **主推荐** |
| 本方法内部 | typed mapper 过严 | 放宽 equivalent/related 绑叶；空 `matched_leaf_ids` 时回退字符串/嵌入近邻叶 | **主推荐（映射臂）** |
| MedRAG-style B16 | retrieve → elicit differences | 差异线索驱动 **树内** 补叶/补父标签对齐（不开放新轴） | **条件可迁** |
| A01 taxonomy | 先选 specialty | 对照「显式家族化」；非 BFS 补丁 | **仅对照** |
| Dual/MAC 排序算子 | support / pair | **本轮不作为召回主杠杆**（已在 rank-gap 验证过排序） | **降优先 / 旁路** |

**Track B 推荐优先级**

1. **MapperBind-Repair**（修假 MISS → AutoCoverage↑）  
2. **TreeLeaf-Synonym-Parent**（审计/评测层父集，不改推理）  
3. **AxisGapFill-lite**（仅 mandatory 空域；预期对 18 例假 MISS 无效，对真缺父有限）

---

## Track C — 开放扩族（探索；分列报成本）

| 来源 | 机制 | 上移设想 | 轨道角色 | 判定 |
|------|------|----------|----------|------|
| **i-MedRAG** | 迭代 follow-up 查询 + 每轮 RAG | 在 **建树前/中** 用证据驱动生成「缺失家族假设」，再 **归一** 到 L1 标签挂树 | **C 高潜力（真缺父）** | **可迁环路**；默认不对 18 例假 MISS 启用 |
| Dual-Inf | forward 开放疾病列表 | 生成病名 → 家族对齐 → 缺失则提议新 L1 | C 扩族 | **条件可迁** |
| MAC | 多医生列表扩覆盖 | 多角色提议家族并集再归一 | C | **条件可迁**；成本高 |
| MedRAG B16 | 差异检索 | 线索驱动补召 **新** L1 轴 | C | **中** |
| RareScale 思想 | 召回导向候选生成再融合大模型 | 小模型/检索器出 recall 列表 → 对齐树轴 | C 思想 | **可迁思想**；需训练/KB 则分列 |

### i-MedRAG 迁移细则

| 项 | 内容 |
|----|------|
| 上游 | arXiv:2408.00727；本仓 `baselines/imedrag/adapter.py`（共享 KB，非官方 Textbooks） |
| 可借 | Analysis→Queries 迭代、每轮检索 grounding、假设扩展环路 |
| 不借 | 直接用 flat Top-2 替换树推理作主终点 |
| 插入点 | BranchCreator **之前**或 gap-fill 触发时；输出须经 **树归一**（失败则丢弃） |
| 适用 | `TREE_PARENT_ABSENT`（本批 67、231）及盲法新发现 |
| REJECT 为默认生产路径若 | 无归一门控、或对全量 100 无差别开启（成本↑且对假 MISS 无效） |

### MAC / Dual 扩覆盖

- **可迁**：多列表并集 → 归一到现有 L1 或「新标签+挂载」。  
- **REJECT 整段多医生嵌建树** 作默认（成本与归因混乱）；可作分列上界。  
- 与 OpenRegen（上轮 Track C）同族：必须 **归一失败丢弃**，禁止金标导向选族。

---

## 与排序卡片的边界

| 文档 | 主题 |
|------|------|
| [`../l1_rank_gap_v1/external_l1_transfer_cards.md`](../l1_rank_gap_v1/external_l1_transfer_cards.md) | 冻结后 **排序**（Support/Pair） |
| **本文件** | **召回 / coverage / 建树扩族** |

禁止混报：B12 REJECT ≠ 召回 REJECT；Mapper 修复成功 ≠ L1 排序变强。

产出完成：本文件。
