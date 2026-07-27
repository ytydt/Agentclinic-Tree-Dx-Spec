# L1 金标召回：文献与联网迁移笔记

**范围**：候选 **召回** 与最终 **排序** 拆开（与诊断/检索 canvas 一致）。  
**种子**：RareScale、DeepRare（门控）、CURE、MedRAG、i-MedRAG；本仓基线点估计见 [`runs/paper_v1/diagnosisarena_d2_seq100_baselines_summary.md`](../../runs/paper_v1/diagnosisarena_d2_seq100_baselines_summary.md)。

---

## 1. 核心原则（文献共识 → 本课题）

| 原则 | 来源倾向 | 对本方法 |
|------|----------|----------|
| 先保证候选覆盖，再谈排序 | RareScale（recall-oriented ≤5 候选再融合大模型）；临床 CDS | AutoCoverage 0.80 的「缺口」须先分清真假召回 |
| 迭代检索扩展假设 | i-MedRAG（follow-up queries） | Track C：建树前/中扩家族假设 |
| 多路径并集提高覆盖 | MAC 多医生列表；Dual forward 列表 | Track C：并集后归一，不作默认排序补丁 |
| 私有 KG 不可比 | 官方 MedRAG KG | 只借环路；检索用共享 `rag_index`/`cpg_index` |
| 排序≠召回 | 上轮 B12 REJECT | 本轮文档禁止复用排序结论 |

---

## 2. 条目卡片

### 2.1 i-MedRAG（Xiong et al., arXiv:2408.00727 / PSB 2025）

- **机制**：多轮生成 follow-up queries → 每轮 vanilla RAG → 累积上下文 → 最终作答。  
- **迁移**：把「query 扩展」改写为「L1 家族假设扩展 + 证据检索验证 + 树归一」。  
- **仓内**：B17 adapter；共享 KB；flat Top-2 协议。  
- **注意**：主结果在 MedQA/USMLE 类 QA，不是分层诊断树；迁移的是 **环路** 不是数字。

### 2.2 RareScale（Schumacher et al., arXiv:2502.15069 / MLHC）

- **机制**：专家系统+LLM 模拟对话 → 训练 **召回导向** 稀有病候选器（≤5）→ 注入黑盒 LLM 出最终鉴别。  
- **迁移**：显式「recall list → fuse」两段式；对应我们的 **候选召回层** vs **joint/compat 排序层**。  
- **限制**：依赖稀有病专家系统与训练数据；d2 无同构训练池 → **思想可迁，模型不可直接搬**。

### 2.3 MedRAG / B16（本仓共享 KB 变体）

- **机制**：retrieve +（KG 风格）差异线索。  
- **点估计**：B16 @1=0.48（弱于 MAC/Dual flat）。  
- **迁移**：差异线索驱动 **补叶/补轴**；不作主排序器。

### 2.4 MAC（B06）/ Dual-Inf（B04）

- **点估计**：@1≈0.61 / 0.60（开放列表）。  
- **召回相关**：多列表 / forward 生成扩大病名覆盖。  
- **迁移**：病名→家族对齐；与上轮「support/pair 排序」解耦。

### 2.5 DeepRare / RareBench 门控臂

- **状态**：本仓 B08 门控（专用基准）。  
- **迁移**：稀有病召回工具链思想可参考；**不**并入 d2 主表数字。

### 2.6 CURE / 其他诊断 agent

- 多步工具/协作提高覆盖的叙事与 MAC 同类；落地时仍需 **树归一** 与成本分列。

---

## 3. 与本审计的咬合

本批 20 例假/真 MISS 拆分后：文献中的「开放扩候选」对 **`TREE_PARENT_ABSENT`（2 例）** 有直接动机；对 **`MAPPER_UNBIND`（18 例）** 更应对齐 **实体链接 / 答案映射** 文献，而非再扩一轮 RAG 假设。

---

## 4. 引用速查

- Xiong et al. i-MedRAG: https://arxiv.org/abs/2408.00727  
- Schumacher et al. RareScale: https://arxiv.org/abs/2502.15069  
- MedRAG 实现：https://github.com/Teddy-XiongGZ/MedRAG  

产出完成：本文件。
