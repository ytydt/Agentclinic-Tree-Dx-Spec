# GraphRAG / 双检索入口 / 多数据源 可行性调研

> 独立调研报告 · 2026-07-02
> 面向问题：`BRANCH_GENERATION_PHASE_REPORT.md`（下称《分支报告》）与 `CPG_RAG_EXTRACTION.md`（下称《CPG 抽取》）记录的分支创建困局，是否应改用 GraphRAG（配合语料结构化 / 知识图谱抽取）解决；检索入口是否应同时包含综合征表征与显著症状；数据源是否应超出 CPG。
> 本文为**调研 + 借鉴可行性分析**，不改动任何流水线代码。落地路线见 §7。

---

## 0. 结论速览（TL;DR）

| 命题 | 判断 | 依据 |
|------|------|------|
| **是否应上 GraphRAG 推倒重来** | ❌ **否**（P2 受限试点） | 报告 §18 已证「数据够、瓶颈在工程与源」；GraphRAG 主要解决跨篇聚合/多跳，不解决最痛的 c1 词面鸿沟 |
| **是否借鉴 GraphRAG 的某些机制** | ✅ **是（选择性）** | MedRAG「诊断差异 KG」对轴可分/相似病最相关；MedGraphRAG 的 U-Retrieve/三层链接可优化 sibling；MED-COPILOT 的双通道印证双入口 |
| **检索入口是否加显著症状** | ✅ **强烈建议（P0）** | 文献一边倒（hybrid recall 73%→92%）；c1 失败正因单综合征入口；**区别于已证伪的 fanout** |
| **数据源是否超出 CPG** | ✅ **是（角色分工，非堆量）** | CPG 强于 MECE 轴/mandatory，罕见病召回上界应由 case reports/合成病例补 |
| **CPG 是否分支创建最理想单一源** | ❌ **否** | 完备/召回靠 case reports；互斥/可分靠 CPG/指南；二者互补 |

核心一句：**GraphRAG 的"结构化/诊断差异 KG"思想值得借鉴，但应以"补 nominate/轴极表 + 提升相似病可分"的轻量形态落地，而非替换现有 RAG 主链。** 最高性价比的改动是**双检索入口 + case reports 长尾补源**。

---

## 1. 判断基准：两份报告已坐实的困局

后文所有借鉴分析都对应到这里的困局编号（沿用报告原始编号）：

| 困局 | 报告位置 | 本质 | 现状 |
|------|----------|------|------|
| **词面/eponym 鸿沟**（c1 Pancoast） | 分支报告 §6.10、§18.2 B5 | 综合征标签与答案病名无共同词，检索够不着 | IMP-58 nominate 部分补 |
| **候选池拥挤 C4** | §6.6 | 40 槽被高频常见病占满，罕见 gold 挤掉 | IMP-64 归族已落地 |
| **轴可分性差**（最佳 0.571→0.714） | §19.5#4 | 只召回单轴极，无法正确切分 | IMP-60 待扩源 |
| **SNOMED 分区墙 D1** | §6.14、§6.32 | 召回 6/9 但覆盖 3/9，机制/解剖措辞投影失败 | 方案A LLM MECE 绕墙 |
| **长尾语料稀疏 L13** | §6.28、CPG §1667 | peliosis/glucagonoma 语料稀疏、嵌入不可分 | 待补源 |
| **入口检索单一** | §18.2 c1 | 124 入口块 0 direct，靠 PMC sibling 闭包才够 | 待双入口 |
| **cant_miss 轴极源缺** | §19.8（IMP-60「源未覆盖 → 无效」） | 无 can't-miss 双极标注源 | **待补源** |

**元结论（分支报告 §18 / CPG §1514）**：entry+closure oracle 上界 **8/8=100%**——"语料里不是没有 gold"，瓶颈在 ①索引未解锁（IMP-31）、②检索排序/spotting、③分区归一、④度量。**这句话决定了"GraphRAG 不是主药"的判断。**

---

## 2. 四篇 GraphRAG 文献的机制拆解

逐篇拆到"具体做了什么"，而非只看结论，便于判断可借鉴点。

### 2.1 MedGraphRAG (Wu et al., 2024)：三层链接 + U-Retrieve

- **构建**："macro–micro"分层图；**三层链接（Triple Graph）**：用户/私有文档 → 权威医学论文/教科书 → 基础医学词典（UMLS）。每个抽取实体向上锚定到更权威层，形成可溯源链。
- **检索**：**U-Retrieve**——先自顶向下按 tag/摘要定位相关社区，再自底向上用实体+社区摘要精炼回答，平衡"全局主题 vs 局部精度"。
- **效果**：较标准 RAG 医学 QA **+8%**、事实核查 **+10–11%**。
- **对本项目的映射**：`source_id` 闭包（IMP-31）本质是"最小 article graph"；MedGraphRAG 的三层链接 = 你已有的 `disease→SNOMED/UMLS 归一`思路的图化版。**U-Retrieve 的"先定位文章再篇内精取"正对应分支报告 §14.6 建议的"两阶段 RAG + sibling 配额"**。

### 2.2 MedRAG (WWW'25)：四层诊断差异 KG —— 与本项目最相关

- **构建**：**四层层次诊断 KG**（系统类别 → 亚类 → 疾病 → 表现/manifestation），关键是**显式编码"疾病间关键诊断差异"（critical diagnostic differences）**，专门服务"相似临床表现疾病"的区分。
- **检索/推理**：把 KG 的诊断差异**动态融合**从 EHR 库检索到的相似病例，再在 LLM 内推理；并主动生成**追问问题**降低不确定性。
- **效果**：DDXPlus **88.65%**、私有慢性痛数据集 CPDD **79.25%**；**降误诊**，尤其相似表现疾病。已发布 **DDXPlus 的诊断 KG 文件**。
- **对本项目的映射**：这正对应你最难的 **轴可分性 / CML-BC vs AML 分期鉴别**（分支报告 §19.5#4、PrimeKG 检查结论"三分期表型完全相同、无法区分"）。**MedRAG 的"诊断差异边"= 把你缺的 discriminating features 显式建成图边**，可直接喂 EvidenceAnnotator / 轴极注入。

### 2.3 MED-COPILOT (ACL'26)：指南 GraphRAG + 相似病例双通道

- **构建**：WHO/NICE 指南建 KG + **社区级摘要**；另建 **36,000 例相似病例库**（SOAP 规范化 MIMIC-IV + Synthea 合成）。
- **检索**：**双通道并联**——① 指南 GraphRAG（结构化证据）；② **hybrid semantic-keyword 相似病例检索**（keyword 分量抓离散临床信号=诊断/合并症/关键干预，semantic 分量抓轨迹相似）。
- **效果**：优于 parametric LLM 与标准 RAG。
- **对本项目的映射**：**双通道 = 你问的"双检索入口"的直接先例**。keyword 通道正对应"显著症状实体入口"，semantic 通道对应"综合征 episode 表征"。且**引入相似病例库**印证了"数据源应含 case reports/合成病例"。

### 2.4 medRxiv 复杂病例 RAG vs GraphRAG 对照：关键 caveat

- GraphRAG 在 NICE CKD KG 上**多跳能力最强**（阈值判断、算法决策、开放式管理 patient-specificity 最高）；
- **但**：graph walk 常返回**冗长片段、clarity 更低**；**所有 RAG 都受限于索引语料范围，缺信息时表现差**（Q8 缺 SGLT-2i/finerenone → 忠实检索必然漏）；
- 作者建议：加 **UMLS/SNOMED 归一层**修复"CKD vs Chronic Kidney Disease"这类词面重复导致的图碎片化。
- **对本项目的映射**：与分支报告 §18「缺的不是范式，是工程与源」**完全一致**。GraphRAG **不会凭空补上缺失的语料/边**；且"冗长片段 clarity 低"会加重你 §6.6 候选池拥挤。**印证 GraphRAG 非主药。**

---

## 3. 借鉴可行性：把哪些机制搬进本项目

按"收益 / 成本 / 风险"评估，明确**搬什么、不搬什么**。

| 论文机制 | 是否借鉴 | 对应困局 | 落地形态（本项目） | 成本/风险 |
|----------|----------|----------|---------------------|-----------|
| **MedRAG 诊断差异 KG** | ✅ **借鉴（核心）** | 轴可分 / L13 / 相似病 | 把 discriminating features 抽成 `finding_discriminates_for/against` 边 → 喂 `_reconcile_annotation_with_kb` 与 IMP-60 轴极注入 | 中；需抽取+核验门 |
| **MedGraphRAG U-Retrieve（两阶段）** | ✅ **借鉴（轻量）** | sibling 利用 / 入口单一 | 分支报告 §14.6 已规划：Stage1 定位文章 → Stage2 篇内精取 DDx；`source_id` 闭包已是最小图 | 低；纯 RAG 内改后处理 |
| **MED-COPILOT 双通道检索** | ✅ **借鉴（P0）** | 入口单一 / c1 | 综合征 query ∪ 显著症状实体 query，RRF 合并（复用 `HybridCPGRetriever`） | 低；基建已有 |
| **MED-COPILOT 相似病例库** | ✅ **借鉴（数据）** | L13 长尾 / 完备 | 引入 PMC-Patients/RareArena/DDXPlus 做相似病例 + silver DDx | 中；许可与编码成本 |
| **三层 UMLS/SNOMED 归一** | ✅ **已部分有** | 分区墙 / 词面 | 你已有 SNOMED/`DiseaseNameResolver`；补 alias 归一（IMP-59） | 低 |
| **全量 GraphRAG 主链替换** | ❌ **不借鉴** | — | §18 证数据够；换范式 alone 不够（§19.8 Hybrid 全栈未超 unified） | 高；推倒重来 |
| **社区摘要作主检索** | ⚠️ **暂缓** | — | medRxiv 证"冗长片段 clarity 低"，加重 C4 拥挤 | 中 |

### 3.1 推荐的"轻量 GraphRAG"形态（不是完整 GraphRAG）

结合你现有资产（`source_id` 闭包 = 最小 article graph；`PrimeKGIndex`；SNOMED 三件套；nominate 表），可落地的是一个**"诊断差异增强层 + 两阶段篇内检索"**，而非 Neo4j 全图：

```text
现有（纯 RAG + nominate）        借鉴后（增强，仍非完整 GraphRAG）
─────────────────────────       ──────────────────────────────────
综合征 query → TF-IDF top-k  →   ① 双入口：综合征 ∪ 显著症状实体（RRF）
闭包灌池 → spotter 40 槽          ② 两阶段：定位 source_id → 篇内精取 differential/red_flag
nominate 补机制/专名             ③ 诊断差异层：MedRAG 式 discriminating edges
                                    → 喂轴极注入(IMP-60) + EvidenceAnnotator
                                 ④ 归一层：SNOMED/UMLS alias（IMP-59，修分区墙碎片）
```

关键：**边要带 `axis_pole` / `must_not_miss` / `discriminates` 属性**（分支报告 §结尾已指出"GraphRAG alone 不解决，除非边带 must_not_miss"）——即把 cant_miss/轴极语义写进图，才对轴可分有用。

---

## 4. 双检索入口（syndrome representation + salient symptoms）

### 4.1 结论：强烈建议（P0），且与已证伪的 fanout 本质不同

| 维度 | fanout（**已证伪**，§6.7） | 双入口（**建议**） |
|------|---------------------------|---------------------|
| 做法 | `differential of X` 的 N 种改写 | 综合征 episode ∪ 显著症状/体征实体 |
| 语义 | 绕同一语义簇 | 打到**不同**语料区域 |
| 证据 | 14 题 L1tgt 可回退、8 题 +0 flip | hybrid recall 73%→92%（MDPI 2026）；MED-COPILOT 双通道 |

### 4.2 落地（结合现有代码，成本近乎 0）

1. **root 阶段附加任务**：RootSelector 同时输出 `presenting_syndrome` **和** `salient_findings: [top-k 显著症状/体征实体]`。你现有 `controller._gather_atomic_findings` / `_raw_atomic_facts` 已产原子 finding，可直接复用。
2. **入口 = 综合征 query ∪ 每个 salient finding query** → 各自 top-k → **RRF 合并**（IMP-53 `HybridCPGRetriever` 的 RRF 已验证正收益）。
3. 与 **IMP-58 nominate 并联**：症状入口负责"检索够得着"，nominate 负责"检索够不着的机制/专名格"（c1 类）。

预期：直接缓解 §18.2 c1"综合征标签够不着答案文章"的入口失败，无新范式风险。

---

## 5. 数据源：CPG 不是分支创建的最理想单一源

### 5.1 按四目标拆解（回答核心问题）

| 目标 | 最适合的源 | 理由 |
|------|-----------|------|
| **互斥 MECE / 可分（轴）** | ✅ **CPG / 指南** | approach-to-symptom 章节天然给 MECE 轴；方案A"纯 CPG LLM 建 MECE 轴正确率 5/5=100%"（CPG §1265） |
| **完备 / 召回上界（罕见病）** | ❌ CPG 不足；✅ **case reports** | CPG 覆盖常见病 approach，长尾稀疏（L13）；case reports 天然覆盖 zebra |
| **presentation→diagnosis 真实映射** | ✅ **case reports / 合成病例** | CPG 是教科书式 DDx 列表；case report 是真实 presentation→确诊 |
| **can't-miss 轴极标注** | ✅ **合成病例（带 DDx 概率）** | 补 IMP-60"源未覆盖→无效"的洞 |

**一句话**：CPG 擅长"给对轴、给全 mandatory 方向"，**召回完备性（不漏罕见 gold）应由 case reports 补**；**can't-miss 双极可用带 DDx 概率的合成病例补**。注意 CPG §568 提醒"新源边际增益须先证后投"——先用 oracle 量化再投，不盲目全量 PMC 编码。

### 5.2 可用开放数据源（已核实）

| 数据源 | 规模 | 许可 | 用途 |
|--------|------|------|------|
| **RareArena** (Lancet Digital Health 2026) | ~50,000 例 / >4,000 罕见病，源自 PMC-Patients，诊断映射 Orphanet | **CC BY-NC-SA 4.0（非商业）** | 罕见病召回上界 + silver DDx；补 L13 |
| **PMC-Patients** | 167,000 患者摘要 + 关系标注 | 开放 | 相似病例 / 症状→病名 silver 边 |
| **ZebraMap** (Zenodo 2025) | 36,131 全文 case reports / 69,146 结构化病例 / 1,727 罕见病，挂 Orphanet+PubMed | 开放 | **已结构化 case→disease，近现成三元组** |
| **DDXPlus** | ~130 万合成患者，49 病/110 症状，**每例带完整 DDx+概率** | **CC-BY** | 现成 symptom→DDx 概率，做召回/轴/can't-miss silver GT |
| **MIMIC-IV-Ext-DiReCT** | 25 疾病类别诊断 KG（JSON 诊断流程树），9 临床医生标注+3 专家审 | PhysioNet 受控 | **诊断流程树 + 前提知识的结构参考** |
| **EPFL/Meditron CPG 语料** | 37K 可再分发 CPG（CCO/CDC/CMA/ICRC/NICE/SPOR/WHO/WikiDoc） | 可再分发子集 | 补 CPG 证据层 |

**许可红线**：RareArena 为 **NC（非商业）**，商用需谨慎；DDXPlus/PMC-Patients 更宽松；MIMIC 需 PhysioNet 认证。

---

## 6. 外部方案《构建临床诊断kg_20260702_2110.md》可借鉴之处

该文件是一次面向"临床诊断/鉴别诊断 KG"的深度调研，与本项目场景高度重合。可直接借鉴：

### 6.1 KG schema 设计（强烈建议采纳）

外部方案主张**不要只做 disease–symptom 共现图**，而是显式建这些关系类型——**这正是本项目缺的 discriminating features**：

| 关系类型 | 对本项目的用途 |
|----------|----------------|
| `disease_similar_to / differential_diagnosis` | 相似病组 → 轴可分、候选池族竞争 |
| `finding_discriminates_for / _against` | **喂 EvidenceAnnotator 方向判定 + LR**（补 case 9 LAP、case 17 分期） |
| `red_flag_for` | **can't-miss 硬下界（IMP-56）** |
| `recommended_test_for_differentiation` | discriminator_hints 质量提升 |
| `provenance`（来源/章节/证据等级/审核状态） | 与你的接地核验门（TODO-GL-16）一致 |

其核心警句与本项目 pathognomonic 表设计一致：**"最危险的错误不是漏边，而是把共现关系误当诊断依据"** → 支撑你坚持"curated + 接地核验"而非全自动。

### 6.2 三层/五层 KG 分层（与本项目分工判断一致）

外部方案的三层结构：
```
syndrome/chief complaint layer  →  differential disease group layer  →  discriminating evidence layer
（综合征入口，自建/DDXPlus/schema）   （PrimeKG/HPO/Orphanet）              （指南+综述+case reports 抽取）
```
与本文 §5.1 的"CPG 定轴 / case reports 补召回 / 合成病例补 can't-miss"**完全对齐**，且比本项目现状多了显式的 **syndrome-entry layer**——正对应你问的"综合征入口 + 显著症状"。

### 6.3 具体数据源与现有研究映射（可直接复用其调研成果）

外部方案已核实并归类了大量源，可省去本项目重复调研：
- **backbone 复用**：PrimeKG（你已用）、HPO、Orphanet、Mondo；
- **syndrome-entry 参考**：DDXPlus、diagnostic schema、**MIMIC-IV-Ext-DiReCT（25 类诊断流程树 JSON）**；
- **相似研究路线**：MedKGI（PrimeKG disease–symptom/disease–disease）、KG4Diagnosis（文本抽取+SNOMED/UMLS+专家校验，362 病）、Thinking Like a Doctor（教材 decision tree → 338 病 3,935 边诊断 KG）、DeepRare（罕见病：开放 KB+文献病例+表型标准化）。
- **MedRAG 已发布 DDXPlus 诊断 KG** → 可直接作"诊断差异层"的启动种子（注意其基于合成数据，临床真实性需核验）。

### 6.4 与本项目的差异（需注意）

- 外部方案偏"**从零构建可发表 KG**"；本项目更务实——**只需补 nominate/轴极/discriminating 表**，不必建完整 Neo4j 图。
- 外部方案的 syndrome layer 建议"自建"；本项目可用 **UnionAxisMap（A∪C）+ 双入口检索**先低成本覆盖，KG 化作为后续增强。

---

## 7. 落地优先级路线图

按 ROI/风险排序，全部与现有 IMP 链衔接：

### P0（低风险高收益，立即）
1. **双检索入口**：root 附加 `salient_findings` → 综合征 ∪ 症状实体 RRF（复用 `HybridCPGRetriever`）。直击 c1 入口失败。
2. **case reports 长尾补源做召回上界**：先用 **DDXPlus + RareArena** 建 silver DDx，落地待建的 **IMP-54 `eval_coverage_oracle.py`**，量化 CPG 到底漏多少罕见 gold（先证再投）。

### P1（中等成本，明确收益）
3. **DDXPlus/RareArena 补 IMP-60 cant_miss 轴极源**：解决 §19.8"源未覆盖→轴极注入无效"。
4. **诊断差异层抽取（MedRAG 式 + 外部方案 schema）**：从 ZebraMap（已结构化）/case reports 抽 `finding_discriminates_for/against`、`red_flag_for`，经接地核验门入表 → 喂 EvidenceAnnotator + 轴极注入。**这才是"KG 抽取"对本项目真正有用的形态**（补表，非建全图）。
5. **两阶段篇内检索（MedGraphRAG U-Retrieve 轻量版）**：Stage1 定位 `source_id` → Stage2 篇内精取 differential/red_flag（分支报告 §14.6 已规划）。

### P2（中长期，受限试点）
6. **GraphRAG 只在"轴可分/相似病鉴别"线试点**（MedRAG 四层诊断 KG 范式），边带 `axis_pole`/`must_not_miss`/`discriminates` 属性；作 rerank/覆盖审计补充，**不替换主检索链**。

---

## 8. 直接回答四个原始问题

1. **困局是否适合改 GraphRAG？** — 部分适合但**非主药**。GraphRAG 解决跨篇聚合+相似病区分，不解决最痛的 c1 召回；§18 已证瓶颈在工程与源。**借鉴其"诊断差异 KG / U-Retrieve / 双通道"机制以补表和优化检索，而非推倒重来。**

2. **检索入口是否应含显著症状？** — **是（P0）**。文献一边倒（recall 73%→92%），c1 失败正因单综合征入口。root 附加 salient findings + RRF，**区别于已证伪的 fanout**。

3. **数据源是否应超出 CPG？** — **是**。补 case reports（RareArena/PMC-Patients/ZebraMap）+ 合成病例（DDXPlus）+ 诊断流程树（MIMIC-IV-Ext-DiReCT）。

4. **CPG 是否分支创建最理想单一源？** — **不是**。理想是分工：CPG/指南定 MECE 轴与 mandatory，case reports 保长尾召回上界，合成病例提供 silver DDx + can't-miss 轴极。

---

## 附录 A：引用来源

- MedGraphRAG: *Medical Graph RAG: Evidence-based Medical LLM via Graph Retrieval-Augmented Generation* (Wu et al., 2024, arXiv:2408.04187)
- MedRAG: *MedRAG: Enhancing RAG with Knowledge Graph-Elicited Reasoning for Healthcare Copilot* (WWW'25, dl.acm.org/doi/10.1145/3696410.3714782；代码 SNOWTEAM2023/MedRAG)
- MED-COPILOT: *MED-COPILOT: A Medical Assistant Powered by GraphRAG and Similar Patient Case Retrieval* (ACL'26 demo, arXiv:2603.00460)
- medRxiv 对照: *Development and validation of RAG and GraphRAG for complex clinical cases* (medRxiv 2025.11.25.25341010)
- Hybrid RAG: *Enhancing Medical QA with LLMs via a Hybrid RAG Framework* (MDPI Information 2026, 17(2):133)
- 数据源: RareArena (Lancet Digital Health 2026)、PMC-Patients、ZebraMap (Zenodo 2025)、DDXPlus (NeurIPS 2022)、MIMIC-IV-Ext-DiReCT
- 外部方案: `构建临床诊断kg_20260702_2110.md`（本仓库）
- 本项目: `BRANCH_GENERATION_PHASE_REPORT.md` §6/§14.6/§18/§19；`CPG_RAG_EXTRACTION.md` §13.5/§18；`BRANCH_KNOWLEDGE_IMPLEMENTATION_PLAN.md`
----
对话返回的调研：
已完成对两份报告困局的梳理和互联网深入调研。下面给出结论。

---

# 总体判断

你提的三件事——**上 GraphRAG、双检索入口、多数据源**——方向都对，但优先级和作用不同。我把它们对应到报告里已坐实的困局，逐项给出证据与建议。核心结论先说：

1. **GraphRAG 不是当前 P0**，且对你最痛的 c1 类"词面/机制鸿沟"帮助有限；它解决的是**跨篇 DDx 聚合与多跳推理**，而你报告已证明"数据够、瓶颈在检索排序+抽取+分区"。**应先补数据源与双入口，再评估是否上图。**
2. **双入口（syndrome representation + salient symptoms）几乎是无争议的收益**，文献一边倒支持，且报告里 §6.10/§18.2 的 c1 失败正是"只用综合征短语入口"造成的。**这是最高性价比的改动。**
3. **CPG 不是分支创建阶段最理想的单一数据源**。对"完备/召回/互斥/可分"这四个目标，CPG 擅长的是 MECE 轴与 mandatory，而**召回上界（尤其罕见病长尾）应由 case reports 语料补**。**多源是对的**，但要按"角色分工"而非"堆语料"。

---

# 一、报告里已坐实的困局（作为判断基准）

先把两份文档记录的困局归类，后面的建议都对应到这里：

| 困局 | 报告位置 | 本质 |
|------|----------|------|
| **词面/eponym 鸿沟**（c1 Pancoast） | §6.10、§18.2 B5 | 综合征标签与答案病名无共同词，检索够不着 |
| **候选池拥挤**（C4） | §6.6 | 40 槽被高频常见病占满，罕见 gold 被挤掉 |
| **轴可分性差**（最佳仅 0.571→0.714） | §19.5 #4 | 只召回单轴极，无法正确切分 |
| **SNOMED 分区墙**（D1） | §6.14、§6.32 | 召回 6/9 但覆盖 3/9，机制/解剖措辞投影失败 |
| **长尾语料稀疏**（L13） | §6.28、CPG §1667 | peliosis/glucagonoma 在语料稀疏、嵌入不可分 |
| **入口检索单一** | §18.2 c1 | 124 入口块 0 direct，靠 PMC sibling 闭包才够 |

关键的元结论（报告 §18、CPG §1514）：**"语料里不是没有 gold"——entry+closure oracle 上界 8/8=100%**；瓶颈在①索引未解锁、②检索排序/spotting、③分区归一、④度量。**这句话直接影响"是否该上 GraphRAG"的判断。**

---

# 二、GraphRAG：是中长期选项，不是当前解药

## 文献证据（2025–2026）

- **Medical GraphRAG (MedGraphRAG)**：较标准 RAG 医学 QA +8%、事实核查 +10–11%。
- **MedRAG (WWW'25)**：四层诊断 KG，DDXPlus 88.65%、专治"相似表现疾病误诊"——**这点和你的轴可分/难病鉴别最相关**。
- **MED-COPILOT (ACL'26)**：GraphRAG（WHO/NICE 指南建图 + 社区摘要）+ 36,000 例相似病例混合检索，优于标准 RAG。
- **一篇 medRxiv 复杂临床病例 RAG vs GraphRAG 对照**给出关键 caveat：**GraphRAG 多跳能力强，但"graph walk 常返回冗长片段、clarity 更低"，且"所有 RAG 都受限于索引语料范围，缺信息时表现差"**——这正是你 §18 说的"缺的不是范式，是工程与源"。

## 对你项目的具体判断

报告 §14.6 已经自问自答过这个问题，结论我完全认同并用外部证据强化：

| 你的困局 | GraphRAG 能否解决 | 说明 |
|----------|------------------|------|
| sibling 利用难（0/8 进 24 槽） | ⚠️ 能，但不必 | `source_id` 闭包已是"最小 article graph"；缺的是**遍历预算分配**，纯 RAG 内可修（§14.6.1） |
| c1 词面/机制鸿沟 | ❌ 基本不能 | GraphRAG 也要先有"右臂无力↔Pancoast"的边；除非把 nominate/别名写进图（§14.10 "GraphRAG alone 不解决除非边带 must_not_miss"） |
| 轴可分性/相似病鉴别 | ✅ **这是 GraphRAG 唯一强项** | MedRAG 四层 KG 显式编码"诊断差异"，正对你的 CML-BC vs AML 分期难题 |
| 候选池拥挤 C4 | ❌ 无关 | 是 40 槽规则问题，IMP-64 归族已在做 |

**结论**：GraphRAG 的价值集中在**"显式编码诊断差异 → 提升轴可分/相似病区分"**（对应 MedRAG 范式），而不是解决你最痛的 c1 召回。且 §19.8 已证 **Hybrid 全栈 LLM 没把综合分推过 unified 全栈**——说明当前瓶颈"不只在检索词面，还在抽取链与 40 槽规则"，**换范式 alone 不够**。

建议：**把 GraphRAG 降级为 P2 备选**，只在"轴可分性/相似病鉴别"这条线上做一个**受限试点**（见第五节），不推倒重来。

---

# 三、双检索入口：最高性价比，强烈建议做

## 你的直觉是对的，文献一边倒支持

- Hybrid RAG (MDPI 2026)：**BM25（术语/症状/药名）+ MedCPT dense** 混合，context recall 从单塔 73–82% → **92.14%**；纯 dense"overgeneralization"、纯 sparse 精度低——**症状词这种离散临床信号恰恰要 sparse/keyword 通道**。
- MED-COPILOT 的 hybrid similarity：**keyword 分量强调 discrete clinical signals（诊断、合并症、关键干预）+ semantic 分量抓轨迹相似**，双分量正是"综合征表征 + 显著症状"的对应。
- EHR hybrid graph RAG (arXiv 2602.00009)：**即使"简单查询"，Cypher-only 也漏 20%——因为临床信号只存在于 free-text**；必须 keyword+vector 双通道保召回。

## 对应你报告的证据

c1 的失败根因（§18.2 B5）就是**只用综合征短语 `focal limb neuro deficit` 做入口**，而答案词是 `Pancoast/superior sulcus`。报告 §6.7 证伪的是 **fanout（同一综合征换 5 种问法）**，**不是**"综合征 + 症状实体"这种**正交入口**。二者本质不同：

- fanout（已证伪）：`differential of X` 的 N 种改写 → 仍绕着同一语义簇
- **双入口（建议）**：综合征 episode 表征 **∪** 从 vignette 抽的**显著症状/体征实体**（`Horner`、`apical mass`、`arm weakness`）→ 打到**不同**语料区域

## 落地建议（结合你现有代码）

1. **在 root 提取阶段附加任务**：让 RootSelector 同时输出 `presenting_syndrome` **和** `salient_findings: [top-k 显著症状/体征实体]`（你现在 `_gather_atomic_findings` 已有原子 finding，可直接复用，成本近乎 0）。
2. **检索入口 = 综合征 query ∪ 每个 salient finding 的 query**，各自 top-k 后 RRF 合并（你已有 `HybridCPGRetriever` 的 RRF 基建，IMP-53 已验证正收益）。
3. 这与 IMP-58 nominate **并联**：症状入口负责"检索够得着"，nominate 负责"检索够不着的机制/专名格"。

预期收益：直接缓解 §18.2 c1 那类"综合征标签够不着答案文章"的入口失败，且**不引入新范式风险**。

---

# 四、数据源：CPG 不是分支创建的最理想单一源

## 按四个目标拆解（这是回答你核心问题的关键）

| 目标 | 最适合的源 | 理由 |
|------|-----------|------|
| **互斥 MECE / 可分（轴）** | ✅ **CPG / 指南** | CPG 的 approach-to-symptom 章节天然给 MECE 轴与 mandatory；报告 §15 方案A 已证"纯 CPG LLM 建 MECE 轴正确率 5/5=100%" |
| **完备 / 召回上界（尤其罕见病）** | ❌ CPG 不足；✅ **case reports** | CPG 覆盖常见病 approach，长尾罕见病（peliosis/glucagonoma）稀疏（L13）；case reports 天然覆盖 zebra |
| **presentation→diagnosis 的真实映射** | ✅ **case reports / 模拟病例** | CPG 是"教科书式 DDx 列表"，case report 是"真实 presentation → 确诊"，更贴合 episode representation |

**一句话**：CPG 擅长"给对轴、给全 mandatory 方向"，但**召回完备性（不漏罕见 gold）应由 case reports 补**。报告 CPG §568 也提醒"新源边际增益须先证后投"——所以不是无脑加 PMC 全库，而是**定向补长尾**。

## 可直接用的开放数据源（我已核实）

| 数据源 | 规模 | 许可 | 对你的用途 |
|--------|------|------|-----------|
| **RareArena** (Lancet Digital Health 2026) | ~50,000 例 / >4,000 罕见病，源自 PMC-Patients，诊断已映射 Orphanet | CC BY-NC-SA 4.0 | **罕见病召回上界 + silver DDx**；直接补 L13 长尾 |
| **PMC-Patients** | 167,000 患者摘要 + 关系标注 | 开放 | 相似病例检索 / 症状→病名 silver 边 |
| **ZebraMap** | 36,131 全文 case reports / 69,146 结构化病例 / 1,727 罕见病，挂 Orphanet + PubMed | 开放(Zenodo) | **已结构化的 case→disease，接近现成 KG 三元组** |
| **DDXPlus** | ~130 万合成患者，49 病 / 110 症状 / 113 antecedent，**每例带完整 DDx + 概率** | CC-BY | **现成的 symptom→DDx 概率表**，可直接做召回/轴/can't-miss 的 silver ground truth |
| **RaDaR 训练集** | 49,170 真实 + 104,666 合成 case（phenotype-anchored） | 开源 | 佐证"真实+合成混合"是主流范式 |

**注意许可**：RareArena 是 **NC（非商业）**，若你项目商用需谨慎；DDXPlus/PMC-Patients 更宽松。

## 模拟病例（benchmark）的定位

DDXPlus 这类**合成病例自带 differential diagnosis + 概率**，对你的分支创建阶段有独特价值：

- 可作 **oracle-union recall 的 silver 标准**（对应你待建的 IMP-54 `eval_coverage_oracle.py`）；
- 可挖 **can't-miss / 轴极 双极对**（对应 IMP-60 说的"cant_miss 源未覆盖导致 A4u 无效"——**DDXPlus 的 DDx 概率正好能补这个源缺口**）。

报告 §19.8 明确写 **IMP-60 轴极注入"本评测集 cant_miss 源未覆盖 → 无效，需扩源"**——**这就是 DDXPlus/RareArena 能立刻补上的洞。**

---

# 五、综合建议与优先级

按 ROI 和风险排序：

### P0（低风险高收益，立即做）
1. **双入口检索**：root 阶段附加 `salient_findings` 输出 → 综合征 query ∪ 症状实体 query，RRF 合并（复用现有 Hybrid/RRF）。直击 c1 入口失败。
2. **补 case reports 长尾源做召回上界**：先用 **DDXPlus + RareArena** 建 silver DDx，落地待建的 IMP-54 oracle-union recall，**量化 CPG 到底漏多少罕见 gold**——先证再投，避免盲目全库 PMC 编码（呼应 CPG §568）。

### P1（中等成本，明确收益）
3. **用 DDXPlus/RareArena 补 IMP-60 的 cant_miss 轴极源**：解决 §19.8 "源未覆盖导致轴极注入无效"。
4. **case report → 结构化抽取喂 mechanism/pathognomonic 表**：用 ZebraMap（已结构化）或 LLM 抽 `{presentation, salient_finding, diagnosis}` 三元组，经接地核验门入表——**这才是"知识图谱抽取"对你真正有用的形态**（补 nominate 表，而非建全图）。

### P2（中长期，受限试点）
5. **GraphRAG 只在"轴可分/相似病鉴别"线试点**（MedRAG 四层诊断 KG 范式），显式编码"分期/相似病诊断差异"（如 CML chronic vs blast vs AML）。**不替换主检索链**，作为 rerank/覆盖审计的补充。

---

# 六、直接回答你的四个问题

1. **困局是否适合改 GraphRAG？** — 部分适合，但**不是主药**。GraphRAG 解决"跨篇聚合+相似病区分"，不解决你最痛的 c1 召回；报告已证"瓶颈在工程与源，非范式"。建议 P2 受限试点，配合语料结构化/KG 抽取来**补 nominate 表**而非重建全链。

2. **检索入口是否应含显著症状？** — **是，强烈建议**。文献一边倒（hybrid recall 73%→92%），且 c1 失败正因单综合征入口。用 root 附加任务输出 salient findings，与综合征入口 RRF 合并。**注意区别于已证伪的 fanout**。

3. **数据源是否应超出 CPG？** — **是**。CPG 给轴/MECE 强，但罕见病召回完备性弱。补 **case reports（RareArena/PMC-Patients/ZebraMap）+ 合成病例（DDXPlus）**。

4. **CPG 是否分支创建最理想源？** — **不是单一最理想源**。理想配置是**分工**：CPG/指南定 MECE 轴与 mandatory，case reports 保长尾召回上界，合成病例（DDXPlus）提供 silver DDx + can't-miss 轴极。**从哪获取**：RareArena（GitHub/HF，CC BY-NC-SA）、PMC-Patients（GitHub）、ZebraMap（Zenodo）、DDXPlus（GitHub/HF，CC-BY）。

---

需要的话，我可以把这份调研写成报告的新小节（如 §20 数据源与检索入口演进路线），或者直接落地 P0 里最具体的一项——**在 root 提取阶段加 `salient_findings` 输出并接到双入口 RRF 检索**。你希望先推进哪个？