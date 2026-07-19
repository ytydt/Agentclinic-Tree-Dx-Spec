# TALP：从 CPG / case report 构建鉴别知识图与 GraphRAG 的针对性调研

> 日期：2026-07-11  
> 范围：研究与实验设计；不修改生产 controller，不改变 P5 默认配置。  
> 基线：P5+MedXpert-v2，17 case × 3 seed；SELECT@1 80.4%、SELECT-valid
> 86.3%、DIRECTION 79.8%、RULE-OUT 82.5%、SHARED 56.1%。  
> 与既有调研的关系：`GRAPHRAG_MULTISOURCE_FEASIBILITY_RESEARCH.md` 面向
> BranchCreator 的候选召回、MECE 轴和长尾覆盖；本文只回答 GraphRAG 是否能突破
> P5 TALP 的叶级证据选择与方向判别瓶颈。

## 0. 结论

**值得做受限试点，但不应把通用 GraphRAG 当成 P5 的下一代替代链。**

真正有希望的不是“把 28 万段语料建成实体共现图”，而是构建一个
**候选病对条件化、值/否定/时序敏感、每条边带原文证据的对比临床证据图**
（下称 CCEG，Contrastive Clinical Evidence Graph），再把它作为 P5 的结构化先验。

CCEG 最可能解决两类问题：

1. CPG 中方向性鉴别句已经存在，但散落在不同 chunk、排序靠后，P5 只拿到 association；
2. PrimeKG/DiagRL 对关键候选缺少 disease→phenotype 边，导致 P5 表型交集 veto
   出现 `n_present=0`。

它只能部分缓解：

- SHARED 共性陷阱；
- 阴性证据、数值条件和形态 gestalt；
- 需要主动提名的鉴别检查；
- 有培养结果时的病原体确认。

它不能直接解决：

- hard-none 与 DIRECTION 的路由 Pareto 冲突；
- 语料 mention 无法提供的真实 LR、敏感度和特异度；
- vignette 本身没有培养/决定性检查时的菌种归属；
- 未临床签字的 gold、评分口径差异和远端模型非确定性；
- “反证已检索但编译器忽略”的消费逻辑错误。

因此，研究命题不是“GraphRAG 是否优于 RAG”，而应改成：

> 在相同 CPG 文档和相同 P5 consumer 下，结构化对比断言和有界图遍历是否分别带来
> 可归因、无回归的增益？

## 1. 为什么既有 GraphRAG 调研不能直接回答当前问题

既有调研的主要结论仍成立：

- 双入口和 case report 长尾补源适合 BranchCreator；
- MedRAG 式诊断差异边比通用社区摘要更贴近临床鉴别；
- GraphRAG 不会凭空产生语料中不存在的边；
- 全图 walk 容易返回冗长上下文，加重候选拥挤。

但 TALP 与 BranchCreator 有三处根本差异。

### 1.1 TALP 候选集已给定，主问题不是找病名

P5 的输入已经有 gold 与 distractors。当前审计显示：

- `contrast_not_retrieved = 0`；
- `contrast_retrieved_but_ignored = 全部`；
- 单纯增加 P1 对称检索几乎不改变 SELECT/SHARED。

这说明主要故障是把“某病可见此表现”编成“此表现能区分该病”，而不是缺少更多候选或
更多相似 chunk。

### 1.2 当前 case-report 索引不是方向性证据源

现有资产规模为：

- CPG：205,115 chunks；
- case report：77,849 chunks。

对 39 个关键 finding 的深扫描显示：

- CPG 任意深度存在方向性块 32/39；top-6 只命中 20/39，主要是排序问题；
- CPG 方向块由 differential 17 条、evaluation 15 条组成；
- case-report co-mention 很多，但方向性 prose 为 0/39；
- 当前 case-report co-mention 全是 “differential includes …” 一类成员清单。

所以当前索引的角色必须保持：

- **CPG prose**：可抽方向性鉴别边；
- **case-report 索引**：只作成员、召回和比较集来源；
- 若以后回到原始病例全文，可抽“病例→表现→确诊/检查序列”，但仍是个案断言，
  不能直接当群体方向、患病先验或 LR。

### 1.3 P5 最缺的是对比语义，不是全局主题

通用 GraphRAG 的 entity graph、community summary 和 global search 适合主题聚合。
P5 需要的是更窄的查询：

`(candidate A, candidate B, typed finding/value/context) → 支持谁、反对谁、是否共性、下一步查什么`

因此应采用病对作用域的局部图检索，而不是社区摘要主检索。

## 2. 文献证据：支持什么，不支持什么

### 2.1 支持结构化诊断差异与分层检索

- **MedGraphRAG（Wu et al., 2024）**：
  用用户文档→权威医学来源→术语体系的三层链接和 U-Retrieval，在多个医学 QA/
  fact-checking benchmark 优于标准 RAG。它支持“图作导航和溯源”的方向，但这些 benchmark
  不是 P5 的候选条件化 DIRECTION/SHARED 任务。
- **MedRAG（WWW 2025）**：
  构建四层诊断 KG，显式组织相似疾病的 critical diagnostic differences，并与相似 EHR
  融合；这是与 TALP 最接近的外部证据。它支持“诊断差异边有价值”，但不能证明从本项目
  CPG/case-report 自动抽边后仍有同样收益。
- **KG4Diagnosis（PMLR 2025）**：
  覆盖 362 种常见病，采用语义抽取、多维决策关系重建和 human-guided expansion。
  其专家验证阶段反而说明医学诊断边不能依靠全自动抽取直接进入硬决策。
- **Guideline2Graph（2026 preprint）**：
  在单一前列腺指南的裁决 benchmark 上，decomposition-first 构图把完整图的 edge/triplet
  precision/recall 提到 69.0%/87.5%，node recall 93.8%。它证明跨页接口、拓扑分解和
  provenance 必要；也证明即使先进流程，69% 边精度仍不足以驱动 P5 的硬方向覆盖。

### 2.2 自动抽取的主要风险是 precision，而非 recall

- **GLiM（Findings of ACL 2025）**：
  LLM 推理阶段提升 biomedical document-level relation extraction 的 recall/F1，
  但 precision 因幻觉下降。
- **ACL 2025 biomedical relation-extraction judge 研究**：
  LLM judge 对非结构化关系输出通常低于 50% accuracy；结构化输出平均改善约 15%，
  仍不能替代临床抽样审核。
- 医学 KG 应用研究反复报告：错误 seed concept、无关路径和否定 scope 会把结构化图
  从“减少幻觉”变成“稳定注入错误”。

因此，外部文献支持的是：

1. 结构化关系和多跳导航可能优于纯 chunk 相似度；
2. 医学构图必须保留 provenance、schema 约束和人工质量门；
3. 不能从论文 headline 推导“自动构图后端到端一定优于 P5”。

## 3. P5 残余故障与 CCEG 的可解边界

### 3.1 可直接解决其知识覆盖子问题

**疾病侧表型缺边**

从 CPG prose 和病例确诊段抽取标准化 disease→HPO/SNOMED assertion，可以补：

- malignancy-associated hypercalcemia；
- adhesions / sigmoid volvulus；
- milk-alkali syndrome；
- 其他 PrimeKG/DiagRL 零覆盖候选。

这能让 P5 的集合差/veto 从 `n_present=0` 进入可计算状态。但是否改善 SHARED，
仍取决于实体归一 precision 和软消费策略。

**mention≠discrimination 的结构缺口**

若抽取 schema 强制要求：

- 候选 A 与候选 B 同时绑定；
- finding 的 value/polarity/context 明确；
- supporting excerpt 与 contrasting excerpt 均可回到原文；

则可以把 association 与 discrimination 分开。这是 CCEG 相对普通 RAG 的核心增量。

### 3.2 只能部分帮助

**SHARED 共性陷阱**

图可以显式记录 `common_to(A,B)` 或同一 HPO finding 对两个候选均为 typical，从而给 P5
一个软降权信号。但旧实验已经证明，成员确认或 hard-none 会提高 SHARED、同时显著损失
DIRECTION。图只能改善信号质量，不能替代软路由。

**阴性证据与主动检查**

图可表示：

- `absence_of(X) argues_against A`；
- `test T differentiates A from B`；
- `result R supports A / rules_out B`。

这有助于提名下一步检查，但“未查”与“阴性”的区分、主动询问策略仍属于 planner/consumer。

**复合 morphology / gestalt**

简单 SPO 会拆坏“成熟粒细胞全谱”“毒性高热且肾上腺素无反应”等组合。只有采用 reified
claim 或 hyperedge，保留多个原子条件及其联合语义，才可能帮助；普通实体图无效。

**病原体归属**

图可连接培养/PCR 结果、菌种和感染综合征；有确认性结果时有用。无培养时，正确行为仍是
缩小 syndrome 并请求微生物检查，而不是图遍历后猜菌种。

### 3.3 无法解决

- 真实数值 LR 缺失：case-report 频数和 CPG mention 不能转换为 LR；
- hard-none 策略：这是 P5 consumer 的控制问题；
- gold/fixture 缺陷与 task-dataset mismatch；
- 决定性证据不在 vignette；
- LLM 在证据已充分时仍做出的基础方向错误。

## 4. 推荐产物：CCEG，而不是通用实体图

### 4.1 用 reified claim 表示临床条件

每条可消费知识应是一个 claim，而非裸三元组：

```json
{
  "candidate_a": {"id": "MONDO:...", "name": "..."},
  "candidate_b": {"id": "MONDO:...", "name": "..."},
  "finding": {
    "concept_id": "HP:...",
    "surface": "...",
    "value_state": "elevated|suppressed|present|absent",
    "temporality": "...",
    "specimen": "...",
    "context": {"age": "...", "stage": "...", "treatment": "..."}
  },
  "relation": "supports_a|supports_b|argues_against_a|argues_against_b|common",
  "recommended_test": null,
  "strength": "explicit|qualified|anecdotal",
  "provenance": {
    "source_id": "...",
    "chunk_id": "...",
    "section": "...",
    "quote": "...",
    "evidence_grade": "...",
    "date": "..."
  },
  "extraction": {
    "model": "...",
    "confidence": 0.0,
    "entailment_status": "grounded|rejected|pending_review"
  }
}
```

reified claim 允许表达：

- PTH 升高与受抑制的相反方向；
- 阴性/缺失 finding；
- 疾病阶段、年龄、疫苗状态和治疗后反应；
- 一条边的来源、证据等级和审核状态；
- 多条件 gestalt，而不把它错误拆成互相独立的病理事实。

### 4.2 来源严格分工

**CPG / 指南**

可抽：

- diagnostic criterion；
- explicitly distinguishes / argues against；
- recommended test for differentiation；
- red flag / cannot-miss；
- evidence-graded conditional recommendation。

优先 chunk type：

- `differential`；
- `evaluation`；
- `red_flag`。

检索入口优先使用具体 L2 disease×finding，而不是抽象 L1 标签。

**当前 case-report 索引**

只抽：

- candidate membership；
- disease→typical/atypical phenotype assertion；
- 比较集候选。

禁止：

- 从 “differential includes” 推 rule-in/out；
- 从清单缺席推 argues-against；
- 从 mention 数推患病先验或 LR。

**未来原始病例全文**

可以补：

- presentation→confirmed diagnosis；
- test/result→confirmation；
- temporal trajectory；
- 治疗反应。

但边必须标为 anecdotal；除非原文显式比较候选，否则不生成
`discriminates_for/against`。

**结构化外部 KB**

- HPO/MONDO/SNOMED：实体与层级 backbone；
- LOINC：检查/结果；
- NCBI Taxonomy：病原体身份；
- PathoPhenoDB 等：带 provenance 的 causative-agent 补充；
- 不把 `associated_with` 自动提升为 `causes` 或诊断 LR。

## 5. 构图流程

### 5.1 文档侧

1. 按文章和章节保留结构，不对全库做无界 OpenIE；
2. 用 disease-pair×finding 查询定位候选 CPG 段；
3. 在同一 source 内扩展必要 sibling，恢复跨段条件；
4. 先抽 source-local claim，再做跨文档融合；
5. 每个 claim 必须保留精确 quote/span；
6. 冲突 claim 并存，不用多数 mention 自动消解。

### 5.2 规范化侧

1. disease→MONDO/现有 PrimeKG key；
2. finding→HPO/LOINC/SNOMED/RadLex/NCBI Taxonomy；
3. 单独解析 polarity、value、单位、specimen、temporality、stage；
4. 无高置信映射时 abstain，保留 surface，不生成伪 ID；
5. named syndrome 只有在 ontology/corpus entailment 成立时进入图。

### 5.3 质量门

一条方向性边进入 P5 前必须同时满足：

- schema 合法；
- source quote 存在；
- quote 对 relation 的双向 entailment 通过；
- 否定、数值和 comparator scope 一致；
- 不是 enumeration-only；
- source type 允许该 relation；
- `grounded` 状态；`pending` 只能进入审计，不进入推理。

自动 judge 只能作第一层过滤。pilot 必须对方向边和 common 边做临床双人抽样裁决。

## 6. 检索：图作约束与导航，原文作证据

推荐 query flow：

1. 从病例取 candidate pair 与 typed finding；
2. exact/ontology lookup 找直接 claim；
3. 最多 1–2 hop 扩展到：
   - 同义 finding；
   - parent/child disease；
   - recommended test / confirmatory result；
4. 对 hub 节点做 degree cap；
5. 按 source authority、relation specificity、value/context match、source diversity 排序；
6. hydrate 每条图边的原文 quote；
7. 向 P5 注入“图路径 + 原文”，不注入无引文 community summary。

社区摘要可用于文档导航，不得作为 DIRECTION 的最终证据。

## 7. 必须采用的因果可归因 A/B 梯度

所有实验均以同批 P5+v2 为起点，默认 OFF，使用独立 `p5kg_*` tag、独立 cache 和独立
manifest；P5 的 12 个外部输入继续由 SHA-256 manifest 前后验证。

### G0：P5+v2

冻结治理基线。

### G1：P5 + 同源 raw CPG RAG

扩大/优化 disease×finding、chunk-type-aware 检索，但不抽图。

目的：测“同一语料下，单纯召回/排序还有多少增益”。

### G2：P5 + CCEG direct claim lookup

使用从 G1 同一批 source 抽出的 claim 表，只做直接索引，不做 graph walk。

目的：测“结构化断言”的独立增益。

### G3：P5 + bounded graph traversal

在 G2 上增加 1–2 hop ontology、test-result、parent/child 与 disease-pair 路径。

目的：测“图拓扑/多跳”本身的独立增益。

### G4：P5 + graph path + hydrated quotes

图只负责找路径，每条路径回填原始 CPG quote，并由 entailment gate 再验。

目的：测原文 hydration 是否降低错误边注入和 decisive suppression。

### G5：P5 + clinician-curated oracle claims

对 pilot 子集使用人工裁决 claim，不使用自动抽取结果。

目的：给 GraphRAG 路线建立上界，并定位失败层：

- 若 G5 也不能优于 G0，问题不在抽取，应停止扩图；
- 若 G5 优于 G0、G2 不优，瓶颈是抽取质量；
- 若 G2 优于 G1、G3≈G2，claim table 已足够，不需要 GraphRAG；
- 只有 G3 明确优于 G2，才证明图遍历有独立价值；
- 若 G4 优于 G3，说明 graph-only context 不安全，生产必须 hydrate 原文。

### G6：case-report membership expansion

只扩充 disease→phenotype/member assertion，不提供方向边。

目的：隔离 case report 对 P5 veto 覆盖的贡献，避免与 CPG direction 混合归因。

## 8. 评测设计与门槛

### 8.1 构图层

必须报告：

- entity linking precision/coverage；
- relation precision/recall/F1；
- value、polarity、negation、temporality、specimen accuracy；
- quote→claim entailment precision；
- pair-binding accuracy；
- enumeration→direction false-positive rate；
- provenance completeness。

方向边优先保证 precision。自动边未达到至少 90% 的临床抽样 precision 前，不得作为硬门。

### 8.2 检索层

必须报告：

- decisive claim recall@k；
- support+contrast pair completeness；
- common claim precision；
- disease-pair coverage；
- source diversity；
- token cost 与 latency；
- graph path 中无关 hub 比例；
- 图边命中后原文 hydration 成功率。

### 8.3 端到端层

继续报告：

- SELECT@1 与 SELECT-valid；
- DIRECTION；
- RULE-OUT；
- SHARED；
- decisive suppression；
- organism-attribution 的 culture resolution、no-culture abstain、false attribution。

统计要求：

- 相同 case、相同 seed、复用固定 P5 compiler blocks；
- paired case-cluster bootstrap；
- 报绝对值和 delta 95% CI；
- 至少扩到 30–50 个临床签字独立病例后再决定默认开关；
- organism-attribution、phenotype discrimination、gestalt/compound 分层报告。

### 8.4 晋级门

候选臂必须同时满足：

- DIRECTION 点估计不低于 G0；
- RULE-OUT 点估计不低于 G0；
- decisive suppression 不增加；
- SELECT-valid 不下降；
- SHARED 有正向增益；
- provenance coverage 100%；
- 无培养病原体 false attribution 保持 0；
- 关键增益在扩样本 paired CI 中 resolved。

## 9. Pilot 范围

不建议先把 205k CPG + 77k case-report chunks 全量建 Neo4j。

推荐先做 6–8 个高价值 disease family：

- hypercalcemia DDx；
- leukocytosis / leukemoid / CML / AML；
- small-bowel obstruction / volvulus / adhesions；
- upper-airway infection；
- heat illness / NMS / serotonin syndrome；
- MEN / marfanoid phenotype；
- 1–2 个阴性证据或 morphology gestalt 家族。

Pilot 产物：

- 100–200 条 CPG pair-scoped direction/common/test claim；
- 关键零覆盖候选的 HPO assertion 补洞；
- 方向边与 common 边的双人临床抽样裁决；
- G0–G5 同源、同批 A/B；
- 一份错误分解：抽取错、检索错、consumer 错、gold 错。

防泄漏：

- 不用 fixture 的 gold role 生成边；
- 只用候选疾病名和预先定义 schema 检索文献；
- claim extraction 在看端到端答案前冻结；
- source/document split 与 case split 分开；
- 对研究过的 disease family 做 family-held-out 或至少 source-held-out 复核。

## 10. 工程裁决

### 应做

- 新建稀疏 JSONL claim 表和轻量 adjacency；
- 先证明 claim table 的结构化增益；
- 每条边保留 source quote；
- CPG 与 case-report 权限分离；
- 图信号先作为 P3/P4/P5 的软提示；
- 所有功能参数化、默认 OFF；
- 输出、cache、manifest 与 P5 资产完全隔离。

### 暂不做

- 全量 OpenIE；
- 用 case-report 清单抽 rule-in/out；
- 用 community summary 直接判方向；
- 把 mention 数变成 LR；
- 先部署 Neo4j 再寻找任务；
- 用错误或低精度边硬覆盖 P5；
- 未做 G1/G2 对照就把改善归因于 GraphRAG。

## 11. 最终判断

**GraphRAG 有机会突破 P5，但必要条件不是“图更大”，而是“图中出现 P5 目前缺失的
候选条件化鉴别关系”。**

当前最合理的研究路线是：

1. 从 CPG 的 differential/evaluation/red_flag prose 抽高精度 pair-scoped claim；
2. 从 case report 只补成员、罕见 presentation 和确诊轨迹；
3. 先用 JSONL claim lookup 证明结构化增益；
4. 再以 bounded traversal 证明图拓扑是否有额外价值；
5. 所有图边回填原文，保持 P5 consumer 可审计；
6. 用 oracle G5 决定这条路线是否存在足够高的理论上界。

若 G5 无法无回归地超过 P5，应停止 GraphRAG 扩建，转向 consumer 软路由、grounded LR
补全和 fixture 治理。若 G2 已达到 G5 而 G3 无增益，则最终产品应是
“对比证据表 + 原文检索”，而不是完整 GraphRAG。

## 12. Pilot 实施状态与首轮裁决（2026-07-12）

实现与数据产物已经按前置质量门执行：

- 冻结 8 个 family、394 个 label-blind pair×finding query；family-held-out 与基于
  `article_id/source_id` 哈希的 source-document split 独立。
- CPG 抽取执行 1,970 个请求，并发上限 100。逐 claim L0 拒绝不会再删除同一 query
  的其他合格 claim；最终产出 259 条 schema/source-policy 合格 raw claim，其中
  direction 18、common 3、test recommendation 6。
- 独立 L1 判定 96/259 为 entailed 并进入 `pending_review`；其余为 rejected 或未验证，
  不进入 serving index。
- 临床审核包共 100 条，强制覆盖全部 21 条 direction/common，并按 membership 分层补样；
  阈值冻结为 raw direction precision ≥0.90、双审 κ≥0.80。当前包保持 `UNSIGNED`，
  实测 scorer 返回硬阻断，因此尚未生成 `claims.validated.jsonl`。
- case-record enumeration 只生成 membership：L0 1,389/1,389 合格，L1 1,360/1,389
  entailed；另有 100 条独立 unsigned 审核包。它不产生 direction edge。
- direct index、冻结 adjacency、1–2 hop retriever、原 chunk hydration、membership
  provider、P5 默认 OFF 接线、cache/asset fingerprint 和 G0–G6 runner 均已实现并测试。

不依赖 KG 放行的 G0/G1 已完成 17 case × 3 seed 同批实验：

- G0：SELECT@1 84.3%、SELECT-valid 82.4%、DIRECTION 79.8%、RULE-OUT 79.4%、
  SHARED 59.1%。
- G1：SELECT@1 78.4%、SELECT-valid 80.4%、DIRECTION 82.5%、RULE-OUT 76.2%、
  SHARED 62.1%。
- G1 相对 G0 的 paired delta：SELECT@1 −5.9
  [−23.5,+7.8]、SELECT-valid −2.0 [−17.6,+9.8]、DIRECTION +2.6
  [−2.6,+9.4]、RULE-OUT −3.2 [−11.1,+3.3]、SHARED +3.0
  [−4.2,+14.3] 个百分点，均未 resolved。
- 严格零回归门因 RULE-OUT、SELECT-valid 与 decisive suppression 回归而失败。
  因此 raw CPG query/rerank 不能晋级；这再次支持“结构化 claim 是否有独立增益”
  必须由 G2/G5 回答。

临床 lane 的 G2–G6 当前没有运行，不是工程缺失，而是质量治理的预期阻断：必须先由两名真实临床
审核者完成两个 packet，并由人工补齐 `claims.oracle.jsonl`。不得用 LLM 签名或复制示例
身份绕过该门。

## 13. CCEG v2 跨 Chunk 合成研究梯度裁决（2026-07-12）

本节是与临床生命周期物理隔离的 research-only 模拟，不改变 §12 的临床阻断状态，也不把
LLM 审核写成临床签字。CCEG v2 冻结了 `candidate_effect`、`derived_contrast`、
finding-state canonical key、双 provenance 和 `synthetic_dual_llm` review；所有研究开关
默认 OFF，资产冻结号为 `cceg-v2-research-20260712`。

真实资产链结果如下：

- 17 case 生成 401 条 label-blind candidate×finding query；top-5 共执行 2,005 个
  CPG chunk 抽取作业，得到 170 条 L0 合格 unary claim。
- 独立 L1 判定 118/170 grounded；双模型研究审核对这 118 条产生 96 次分歧，最终仅
  38 条接受，其中 supports 34、argues-against 4。
- 旧 pair-scoped 链的 96 条 L1 grounded claim 中，按 G2PR 许可类型
  `direction/common/test_recommendation` 过滤后只剩 1 条 direction，且被模拟审核拒绝，
  因而有效 G2PR 输入为 0。一次未做类型过滤的探索运行误接纳了 11 条 membership 和
  1 条 phenotype assertion，已判为无效臂并从最终裁决排除。runner 现会按臂拒绝错误
  claim type。
- 38 条 unary edge 冻结为 20 个 candidate node、23 个 finding-state node。按
  “同 article + 同 canonical finding-state + 一正一负”白名单合成时，候选组合数为 0，
  因而 `derived_contrast=0`。原因不是 composer 故障，而是审核后仅剩 4 条负边，且没有
  与其他候选的正边落在同一 article/finding-state group。

17 case × 3 seed 的 research-only 梯度以 G0 为配对基线：

- G2UR（38 条 unary claim）：SELECT@1 80.4%（−3.9），SELECT-valid 86.3%
  （+3.9），DIRECTION 86.0%（+6.1，CI [0,+13.7]），RULE-OUT 82.5%
  （+3.2，CI [0,+10.0]），SHARED 60.6%（+1.5）；但 decisive suppression
  增加 3.9 点，且全部关键增益未 resolved，未过零回归门。
- G2PR 与 G2CR 均因有效输入为空而在修正后的 runner 中 `skipped_no_evidence`；
  G3R/G4R 同样因没有 derived claim 跳过。早期空输入 G2CR 试跑及错误类型 G2PR
  试跑只用于暴露编排缺陷，其模型波动不进入能力裁决。

本轮直接证伪的是“仅把当前 pilot 改成跨 chunk unary 合成，就会产生足够 GraphRAG
拓扑并突破 P5”。唯一有效的 G2UR 出现了值得保留的方向信号，但仍未满足零回归和统计解决条件。
下一步若继续，不应先扩大图遍历，而应提高负 unary edge 的定向召回、降低 synthetic
review 分歧，并在独立语料上证明同文互补边实际存在；否则最终形态仍应是稀疏 claim
lookup，而不是 GraphRAG。

可复现产物：
`data/cceg/unary_v1/`、
`logs/talp_p5kg_research_ab_manifest_v2.json`、
`logs/talp_p5kg_research_final_ruling.json` 与
`logs/talp_discrim_p5kg_research_g2ur_s{7,11,13}r0_dv2_p5.json`。旧
G2PR/G2CR 日志保留作审计，不属于有效实验臂。

## 14. 生产 profile 部分流程验证（2026-07-12）

共享 discrimination runtime、`p5_headline|g2ur|off` production profile 和两轮
partial controller 已落地。专用 harness 使用冻结的 `recall_hints_gap` 分支算法运行
17 题 × 2 profile；轮次 1 强制展开全部 L1，轮次 2 在 evidence explanation 后截断，
不调用 AnswerMapper。

最终 34/34 条 trace 成功，两个 profile 的 L1 recall、L1 展开率和两轮 annotator
coverage 均为 100%。但知识命中呈现关键差异：P5 有 66 次 rule/provenance 命中，
G2UR 为 0。结合 §13，这把问题进一步定位为 serving key mismatch/coverage：
当前 38 条 unary edge 虽能在离线 fixture finding 上产生方向信号，但不能命中生产树
生成的 family label 与 vignette atomic finding。因此“允许选择 G2UR”已成为可执行产品
能力，“G2UR 在该 17 题部分流程提供了额外证据”则被本次运行否定。

该部分流程不含答案映射，不能用 L1 recall 或 L2 leaf 数宣称诊断性能提升；两 profile
独立调用非确定性分支模型，311 vs 322 个 L2 leaf 也不是可归因 profile 的 A/B 指标。
完整配置、资产指纹、汇总和逐题 trace 位于
`logs/partial_flow_talp17/talp17_p5_g2ur_partial_20260712/`。

## 参考文献与项目证据

- Wu et al. *Medical Graph RAG: Towards Safe Medical Large Language Model via
  Graph Retrieval-Augmented Generation*. arXiv:2408.04187, 2024.
  https://arxiv.org/abs/2408.04187
- Zhao et al. *MedRAG: Enhancing Retrieval-augmented Generation with Knowledge
  Graph-Elicited Reasoning for Healthcare Copilot*. WWW 2025.
  https://doi.org/10.1145/3696410.3714782
- Zuo et al. *KG4Diagnosis: A Hierarchical Multi-Agent LLM Framework with
  Knowledge Graph Enhancement for Medical Diagnosis*. PMLR 281, 2025.
  https://proceedings.mlr.press/v281/zuo25a.html
- Kilic et al. *Guideline2Graph: Profile-Aware Multimodal Parsing for Executable
  Clinical Decision Graphs*. arXiv:2604.02477, 2026 preprint.
  https://arxiv.org/abs/2604.02477
- Fang et al. *GLiM: Integrating Graph Transformer and LLM for Document-Level
  Biomedical Relation Extraction with Incomplete Labeling*. Findings of ACL 2025.
  https://aclanthology.org/2025.findings-acl.727/
- Ahmed et al. *Improving Automatic Evaluation of Large Language Models in
  Biomedical Relation Extraction via LLMs-as-the-Judge*. ACL 2025.
  https://aclanthology.org/2025.acl-long.1238/
- `GRAPHRAG_MULTISOURCE_FEASIBILITY_RESEARCH.md`
- `QUALITATIVE_KNOWLEDGE_INJECTION_RESEARCH.md`
- `TALP_DISCRIMINATION_CAPABILITY.md`
- `TALP_STATUS_EXPLAINER.md`
- `TALP_DEFECT_REMEDIATION_PLAN.md`
