# 指南诊断知识图谱：Schema、提取路径与 Token 预算

研究对象：仓库 `cursor4@291e980` 当前可见的 Merck Manual 19e、manifest CPG 与 WikEM DDx；结合既有 RAG 指南源审计和仓内 CCEG/P5KG pilot。

日期：2026-08-25

## 一、结论

最佳方案不是把每个旧 chunk 交给 LLM 生成 `疾病—症状—表现` 三元组，而是建立一个**带原文证据、条件、逻辑和版本的诊断主张账本**，再把它编译成 property graph、RDF 和检索索引：

```text
source-native 结构恢复
  → 诊断相关 passage 的高召回筛选
  → 术语识别、数值/单位、否定与时序候选
  → 高精度模板抽取
  → LLM 仅处理复杂/歧义残差
  → 确定性 schema 与原文 span 验证
  → 独立蕴含验证与人工分层抽审
  → assertion ledger
  → RDF/property-graph/vector 等运行时视图
```

推荐的权威数据模型为 **LinkML authoring schema + JSONL/Parquet assertion ledger**。LinkML 可生成 JSON Schema、Pydantic、SHACL、RDF/JSON-LD 等产物，适合同时维持严格抽取契约与多种运行时视图；不建议把 Neo4j edge 或 OWL 公理直接当唯一真值层。[LinkML generators](https://linkml.io/linkml/generators/)、[LinkML RDF/JSON-LD/SHACL](https://linkml.io/linkml/data/rdf.html)

在当前可见语料上，推荐路线的核心抽取预算中心值约 **330 万 token**（输入、输出及 retry/repair 合计），规划范围约 **129 万–786 万**。该数尚不含独立 LLM verifier；确定性验证不花 API token，若对高风险/冲突 assertion 做定向语义复核，全流程应先预留约 **400 万–500 万 token**，再由 pilot 校准。这个范围来自对仓库文件的 `o200k_base` 实测以及显式的低/中/高场景假设；它不是供应商账单或准确率承诺。若把全部 49,775 个旧 chunk 逐块送给 LLM，单是重复 schema prompt 就会形成巨大浪费，且会继承当前分片缺陷。

## 二、为什么普通三元组 schema 不够

此前 48 例手工 source-oracle 审计显示，vignette 与指南之间最常见的 bridge 不是同义词替换，而是解剖部位、病理到实体、限定词、否定、时序、影像、阈值、复合诊断和免疫表型的关系重建。指南里的诊断知识通常是：

- 在特定人群、病程、器官或检测方法下成立；
- 说明某 finding 的出现或缺失；
- 可能只支持、反对、排除、要求或区分某个候选；
- 由 `AND / OR / NOT / 至少 k 项 / 时间窗` 组合；
- 可能与另一来源冲突，但各自都有适用范围；
- 必须回溯到具体版本、章节、页码和原文 span。

因此裸边 `Disease — has_finding → Finding` 会丢失四类决定性信息：

1. `absence of rash supports X` 中 finding 的缺失与诊断支持是两个不同方向；
2. “常见”不是“有鉴别力”，frequency 不能自动当成 likelihood ratio；
3. “A 相比 B 更符合 F”是带 comparator 的 n-ary 主张，不是 `F supports A`；
4. “至少 2/4 项”拆成四条独立边会制造错误的充分条件。

## 三、推荐的权威 Schema

### 3.1 概念层与表达式层分开

`Concept` 只表示稳定身份：

- `canonical_id`
- `concept_type`
- `preferred_label`
- `synonyms`
- `ontology_release`
- `local_source_mentions`

建议的开放概念骨架：

- 疾病：Mondo；DOID 可作补充/核对；
- 表型：HPO；其 annotation 模型已经区分 frequency、onset、NOT、sex、reference/evidence，可借鉴但不能直接覆盖一般内科指南。[HPOA schema](https://obophenotype.github.io/human-phenotype-ontology/annotations/phenotype_hpoa/)
- 检验：LOINC；其六轴为 component、property、time、system、scale、method。[LOINC term model](https://loinc.org/kb/users-guide/major-parts-of-a-loinc-term)
- 单位：UCUM；
- 解剖：UBERON；
- 化学物/药物：ChEBI；
- 生物医学通用关系：RO；
- SNOMED CT：只作为有许可的内部映射层，不作为必须公开再分发的主身份层。SNOMED 的 relationship grouping 与显式上下文很适合校验 site、morphology、causative agent、present/absent/possible 等组合，但许可条件必须单独遵守。[SNOMED relationship grouping](https://docs.snomed.org/snomed-ct-specifications/snomed-ct-editorial-guide/readme/authoring/general-modeling/relationship-group)、[SNOMED licensing](https://www.snomed.org/get-snomed)

完整诊断答案使用 `DiagnosisExpression`，而不是强行压成一个疾病 ID：

```yaml
DiagnosisExpression:
  head_disease: ConceptRef
  anatomical_site: [ConceptRef]
  laterality: left | right | bilateral | midline | unspecified
  etiology_or_trigger: [ConceptRef]
  pathology_or_molecular_subtype: [ConceptRef]
  stage_or_grade: [ConceptRef]
  temporal_qualifier: TemporalConstraint
  co_condition: [DiagnosisExpressionRef]
  component_relation: and | due_to | associated_with | complication_of
  source_surface: string
```

这允许检索时暂时放宽限定，返回时逐项核验；不会把父类、病理成分或并发组件误当成完整金标。

### 3.2 Finding、测量与时序

`FeaturePattern` 至少包括：

```yaml
FeaturePattern:
  feature_concept: ConceptRef
  finding_state: present | absent | uncertain | unknown
  value_constraint:
    comparator: eq | ne | gt | ge | lt | le | between | relative_to_reference
    lower_value: number?
    upper_value: number?
    original_unit: string?
    ucum_unit: string?
  qualitative_interpretation: positive | negative | high | low | normal | abnormal
  site: ConceptRef?
  laterality: string?
  specimen: ConceptRef?
  method: ConceptRef?
  severity: ConceptRef?
  subject: patient | family_member | fetus | donor | other
  onset: TimeExpression?
  duration: TimeExpression?
  course: acute | chronic | recurrent | progressive | resolving | unknown
  relative_to_event: TemporalRelation?
  original_mention_ids: [MentionRef]
```

时序需明确 `before / after / during / overlaps / within_window` 及 reference event；单独的 `historical=true` 不足以表达停药后发病、暴露潜伏期、serial ECG/marker 变化等情况。单位归一交给 UCUM，而不是 LLM；例如“2× upper limit of normal”应保留 reference-relative comparator，不能伪造绝对数值。[UCUM specification](https://ucum.org/ucum)

### 3.3 组合规则

`LogicExpression` 是一等对象：

```yaml
LogicExpression:
  operator: leaf | all_of | any_of | not | k_of_n | ordered_sequence | within_time_window
  k: integer?
  children: [LogicExpression | FeaturePatternRef]
```

每个 leaf 保留自己的 polarity、值域、部位和时序；`NOT` 只作用于显式 scope。图遵循开放世界语义：没有某条边表示 unknown，不表示 absent。

### 3.4 诊断主张节点

权威事实单元是 reified `DiagnosticAssertion`：

```yaml
DiagnosticAssertion:
  assertion_id: string
  assertion_kind: manifestation_association | diagnostic_criterion |
                  exclusion_criterion | differential_discriminator |
                  risk_factor | etiology | test_interpretation |
                  syndrome_definition
  target_diagnosis: DiagnosisExpressionRef
  contrast_diagnoses: [DiagnosisExpressionRef]
  evidence_pattern: LogicExpressionRef
  diagnostic_effect: supports | opposes | rules_out | required_for | sufficient_for |
                     supports_target_over_contrast
  modality: must | usually | often | may | rarely | insufficient_evidence
  applicability_scope: PopulationContext
  frequency: FrequencyValue?
  quantitative_evidence: QuantitativeEvidence?
  clinical_evidence_certainty: EvidenceCertainty?
  assertion_status: asserted | disputed | deprecated
  evidence_items: [EvidenceItemRef]
```

`DifferentialAssertion` 可作为专门子类，固定表达：在 scope S 下，pattern F 更支持 A 而不是 B。来源只说“常见”的边不允许自动转换为排序权重；只有原文给出 sensitivity、specificity、LR、OR/RR 等量时才进入 `quantitative_evidence`。

### 3.5 来源、证据与抽取活动

文档链必须是：

```text
SourceWork → DocumentVersion → Section → Passage → EvidenceSpan
                                      ↘ previous/next passage
```

核心字段：

- 文档稳定 ID、edition/version、发布日期/有效期、publisher、license；
- chapter/entry/section hierarchy；
- PDF physical page、printed page、bbox；
- passage ordinal、前后 passage ID；
- 原始字符 offsets、exact quote、quote hash；
- table/list/paragraph/sentence 类型；
- parser 与 source hash。

`ExtractionActivity` 保存 method、model/provider/version、prompt/schema hash、parser version、input passage hash、timestamp、输出与 reviewer。可用 PROV-O 的 Entity–Activity–Agent 与 revision/derivation 模式导出 provenance。[W3C PROV-O](https://www.w3.org/TR/prov-o/)

以下四个量必须分开：

- `clinical_evidence_certainty`
- `extraction_confidence`
- `ontology_mapping_confidence`
- `human_review_status`

概念映射使用 SSSOM 的 `subject_id + predicate_id + object_id + mapping_justification`，并保留 confidence、source version 和 reviewer；禁止用 `owl:sameAs` 合并 parent、component、sibling 或带限定表达。[SSSOM model](https://mapping-commons.github.io/sssom/1.0/spec-model/)

FHIR Evidence 能表达 study variables、statistics 与 certainty，但当前 R5 仍是 Maturity 1/Trial Use，且对 Merck 的普通定性诊断句过重；适合作为有定量证据的出口，不适合作为内部唯一 schema。[FHIR Evidence](https://hl7.org/fhir/R5/evidence.html)

## 四、与仓内 CCEG/P5KG 的关系

现有 CCEG v2 已做对几件重要事情：exact quote/span、prompt/model hash、finding state、部分 negation/value audit、研究与生产 consumer 隔离。应保留这些契约。

但当前产物只是 query-conditioned pilot，不是 corpus-wide KG：

- `claims.raw.jsonl` 170 条，`claims.research_validated.jsonl` 仅 38 条；研究图只有 38 个 unary edges、20 个 candidate nodes 和 23 个 finding nodes；
- `scope_queries` 先给定 candidate–finding 对，再从 top-5 chunks 找支持/反对；这适合验证已知 pair，不适合发现完整图谱，也可能把 benchmark scope 带入构建；
- 研究图的 38 条均是 unary `candidate_effect`，没有复合逻辑、真正 pairwise comparator、适用人群或完整 DiagnosisExpression；
- 示例中 candidate ID 常为 `null`，部分 finding normalization abstain；
- `strength=explicit` 未区分频率与鉴别价值；
- 仍可见 References section、标题式 quote 和否定 scope 错误；双 LLM synthetic review 不能等同临床验证；
- 当前日志没有官方 token usage，因此无法反推出其真实构建成本。

最佳迁移方式不是废弃 CCEG，而是把它变为新账本的**定向确认与运行时编译层**：

1. `EvidenceSpan`、hash、research-only lane 和确定性 validators 直接继承；
2. `candidate_effect` 升级为不同 `assertion_kind`；
3. 增加 `DiagnosisExpression / LogicExpression / DifferentialAssertion / PopulationContext`；
4. corpus-wide discovery 与 benchmark-conditioned confirmation 分离；
5. 合并后再编译出兼容现有 P3/P4/P5 的 unary/contrast views。

## 五、最佳提取路径

### Phase 0：先修复来源结构

按来源分流：

- Merck 19e：Docling/版面块 + PDF TOC/书签 + 字体、编号和医学 section 规则；保留 page、bbox、entry 与 ordinal。GROBID主要面向科技论文，可作为 parser-consensus 辅助，不应独自解析 4,000 页医学书。[Docling](https://github.com/docling-project/docling)、[GROBID principles](https://grobid.readthedocs.io/en/latest/Principles/)
- manifest CPG：原始 HTML/JATS/XML 优先；PMC 文本优先使用 JATS/BioC，避免从 PDF/plain text 重猜 section、list 和 table。
- WikEM：直接解析 MediaWiki page、heading、bullet nesting 和 wiki links；很多列表关系可零 LLM token 抽取。

本仓 Merck 必须先处理：Chapter 353 后 228 个附录/索引误挂 chunk、页码丢失、entry title 误挂、零 overlap 固定切分、下标损坏和 PDF 本身缺失表体。原 PDF 已不存在的表内容必须标记 `content_missing_in_source=true`，不能让 LLM 补写。

### Phase 1：高召回 passage admission

将 source-specific headings 统一到：Clinical features、Diagnosis/Evaluation、Differential、Etiology/Risk、Laboratory、Imaging、Pathology、Criteria、Red flags。

采用 heading + 句式 + 表格/列表结构筛选：`diagnosis is based on`、`characterized by`、`suspect when`、`suggests`、`makes unlikely`、`requires at least n`、阈值比较、定义冒号、鉴别比较句等。

当前 `chunk_type∈{evaluation,differential,red_flag}` 只能作为初始 gate，不能直接丢弃其余内容，因为 introduction/background 中仍有疾病定义和临床特征。最终 gate 要在完整标注的 entry 样本上以 passage-selection recall 校准。

上下文单位应是同一 entry 内的 clause/paragraph + 必要邻段；不要再沿用 `content[:1400/1600]`，也不要做整章 closure。

### Phase 2：确定性识别与候选 linking

依次执行：

1. ontology/alias exact 与 normalized match；
2. 缩写展开、最长边界匹配；
3. 疾病、finding、test、anatomy、chemical、organism 的 NER；
4. 数值、comparator、range、单位与 reference-relative threshold parser；
5. negation、uncertainty、subject 和初步 temporal trigger；
6. SapBERT/MedCAT 生成 top-k link candidates；
7. 由 semantic type、entry title、section role 和 relation domain/range 重排。

scispaCy 可作为 NER/词法 baseline；SapBERT 的 self-alignment 专门改善生物医学实体同义链接。[scispaCy paper](https://aclanthology.org/W19-5034/)、[SapBERT paper](https://aclanthology.org/2021.naacl-main.334/)

无法唯一链接时保留 unresolved mention 和候选集合，不强行合并。LLM 不得自由生成 ontology ID；它只能选择已枚举的 mention/link candidates。

### Phase 3：模板优先

确定性模板负责高频、高精度结构：

- entry title 作为 subject 的定义/临床特征；
- heading-conditioned symptom、test、differential、red-flag bullet；
- `is characterized/defined/diagnosed by`；
- `absence/presence of X supports/opposes D`；
- comparator + number/range + unit；
- `more/less likely than`、`distinguish A from B`；
- criteria table 和 `k of n`。

WikEM 的 `LISTS_DIFFERENTIAL` 必须与 `SUPPORTED_BY` 分开：列表成员通常只是候选集合，不是诊断证据。

### Phase 4：LLM 只处理复杂残差

LLM 输入只含完整 entry 上下文中的局部段落、section hierarchy、预编号 mentions、闭集 relation/role enum 与 schema；输出是 citation-bounded slot filling：

- 只能引用 `mention_id`；
- 必须返回 exact quote 和 offsets；
- 必须给出 criterion bundle、diagnostic role、modality/frequency、population、temporal constraint、quantity 和 logic operator；
- 无法确定时返回 `ambiguous/not_asserted`；
- 禁止根据医学常识补齐，禁止自由造 ID。

SPIRES/OntoGPT 证明了“用户定义嵌套 schema + LLM 填槽 + 外部 ontology grounding”的可行性，但其论文把准确率定位在既有 RE 方法的中游，故应把它作为可定制 extractor 原型，而非免验证真值生成器。[SPIRES paper](https://pubmed.ncbi.nlm.nih.gov/38383067/)、[OntoGPT](https://github.com/monarch-initiative/ontogpt)

### Phase 5：双层验证

确定性 validator 自动拒绝：

- quote 不是 passage 精确子串或 offsets 不符；
- mention 不在 inventory；
- relation domain/range 错；
- comparator/value/unit 不完整或 UCUM 无法校验；
- direction 与 canonical schema 冲突；
- logic tree 不完整；
- disease subject 与 passage/entry 来源脱离；
- index/reference/treatment 列表被伪装成诊断规则。

RDF 导出可使用 SHACL 约束验证。[W3C SHACL](https://www.w3.org/TR/shacl/)

独立 verifier 只读候选 assertion、exact span 和 relation 定义，输出 `entailed / contradicted / not_stated / scope_incomplete / direction_wrong`，不能改写 assertion。失败项进入 quarantine，而不是由 verifier 生成“更好”的边。

### Phase 6：合并、版本和运行时编译

- 按 concept + 全部 qualifiers + scope 去重，不按 substring 合并；
- 多来源相同主张聚合 provenance，但不覆盖冲突主张；
- 分开 `asserted_graph`、`normalized_graph`、`derived_graph`；
- 用 source hash 做增量更新，只重抽 changed passages；
- 输出 property graph/RDF 用于查询，另建 evidence-span 向量索引；
- 为 APHHM-C/MOSAIC 编译 hypothesis-relative packets：支持 A、反对 A、区分 A/B、未覆盖限定，而不是返回宽泛疾病邻域。

## 六、Token 实测与预算

### 6.1 实测口径

使用 `tiktoken 0.11.0` 对仓库三个 JSONL 的 `content` 字段逐条编码；`o200k_base` 为主口径，`cl100k_base` 作敏感性检查。仓库 `tokens` 字段实际是 `split()` 词数，不是模型 token。

| 可见语料 | chunks | 仓库“tokens”字段 | `o200k_base` content token |
|---|---:|---:|---:|
| Merck 19e | 9,629 | 1,674,154 | 2,586,806 |
| manifest CPG | 39,091 | 5,919,514 | 8,655,893 |
| WikEM DDx | 1,055 | 44,564 | 85,801 |
| 合计 | **49,775** | **7,638,232** | **11,328,500** |

`cl100k_base` 合计 11,570,544，比主口径高 2.14%。仓库字段比 `o200k_base` 低估 48.3%。

清除 Merck Chapter 353 误挂的 228 个附录/索引块后：

| 语料口径 | chunks | content token | 加 `chunk_id + section_path + chunk_type` 的序列化 payload token |
|---|---:|---:|---:|
| 全部可见、清污染 | 49,547 | 11,155,439 | **13,617,210** |
| 诊断核心类型、清污染 | 11,576 | 4,042,307 | **4,632,568** |
| 诊断核心 + 同 source 内的 ±1 chunk | 15,879 | 5,306,440 | **6,124,892** |

最后一行是较合理的规划基数：它为当前缺乏 entry/page 邻接的旧数据提供保守闭包。结构修复后应改成 entry-local adjacency，token 可能进一步下降，同时提高有效信息完整性。

### 6.2 预算公式

```text
T_extract = (S + N_calls × (P + H) + qS) × (1 + r)

T_build = T_extract
        + T_targeted_semantic_verifier
        + T_optional_embedding_API
```

其中 `S` 为带 provenance 的 passage payload，`P` 为重复 schema/system prompt，`H` 为批头，`q` 为结构化输出相对 source payload 的比例，`r` 为 retry/JSON repair 重跑率。这里的 token 是输入 + 输出工作量，不是价格。若 NER/linking/embedding 在本地运行，相关 API token 为 0；若使用远程 embedding，应额外加一次所选文本的 embedding input token。

### 6.3 三条路线

| 路线 | 低 | 中心 | 高 | 解释 |
|---|---:|---:|---:|---|
| 全语料 batched LLM | 16.28M | **20.76M** | 29.65M | 全部清污染 payload；仍需重验证 |
| 诊断预筛 + 同源 ±1 chunk 后全 LLM | 8.26M | **10.33M** | 15.11M | 不把纯治疗/参考内容全送入，但 gate 必须先测 recall |
| **规则/术语先行，歧义残差才用 LLM** | **1.29M** | **3.30M** | **7.86M** | 推荐；LLM 处理闭包 payload 的 15%/30%/50% |

场景假设：

- 低/中心/高有效 payload cap 分别为 12k/8k/4k；
- 每调用 schema/prompt 为 800/1,200/1,800 token；
- retry/repair 为 2%/8%/15%；
- 全语料 LLM 输出约为输入 payload 的 10%/25%/40%；
- 诊断预筛路线输出约为 25%/40%/65%；
- 混合路线把闭包 payload 的 15%/30%/50% 送入 LLM，输出约为所见 payload 的 30%/50%/75%。

中心场景的估计调用数分别为 1,757、791 和 239。该估计允许把 2–4 个明确 `doc_id` 分隔的短 entry 放入同一批；若强制每个 `source_id` 单独调用，前两条路线中心成本分别上升至约 23.38M 和 12.11M。不能为了追求最低调用数而把大量无关 entry 无界拼接；pilot 应同时测 batch 串扰率。

这些是容量规划参数，不是测得的 assertion density。中心值 3.30M 最敏感的变量是 `f_ambiguous`：模板与 linker 之后仍需 LLM 的文本比例。独立 verifier 未包含在表中，因为其成本取决于接受的 assertion 数而非原文长度；在 pilot 前可对中心方案预留 0.7M–1.7M，使端到端准备金为约 4M–5M，禁止对所有边无差别重跑一个同等规模的第二 extractor。

### 6.4 不推荐的逐旧-chunk方案

若 49,775 个旧 chunk 每个独立调用，假设每次重复 650-token schema prompt，仅 prompt overhead 就约 32.35M；再加 11.33M content 和输出，首轮约 47M–58M，而且每块缺少完整 entry、邻段和表头，成本更高但语义更差。

精确/归一文本去重只能节省约 314,984 `o200k_base` token（2.78%）。因此主要节约来自结构化 passage admission 和歧义门控，而不是去重；相同文本可以折叠一次抽取，但所有 source/version provenance 必须保留。

### 6.5 增量更新

每个 passage 以 `document_version + section_path + page/bbox + normalized_text_hash` 定位：

```text
T_update ≈ f_changed × T_initial_extraction
         + T_mapping_revalidation
         + T_conflict_checks
```

不要按全库重跑；ontology release 更新时只重做受影响的 SSSOM mapping 与由其派生的 view，原始 asserted graph 不变。

## 七、Pilot 与实验设计

### 7.1 先做 100-entry 成本/质量 pilot

按 Merck、CPG、WikEM和 section/relation 类型分层，完整标注 100 个 entry，而不是只审阅模型输出。记录：

- parser hierarchy/page/adjacency accuracy；
- admission recall；
- mention boundary F1；
- exact/parent/sibling/component linking confusion；
- assertion strict precision/recall/F1；
- direction、negation、temporality、quantity、population、logic fidelity；
- exact-span validity、unsupported-edge rate、abstention precision；
- 每个接受 assertion 的 input/output/retry token。

该 pilot 用所选生产模型的官方 usage 字段和精确 tokenizer重新估计：

```text
f_ambiguous
output_tokens / accepted_assertion
verification_rate
repair_rate
accepted_assertions / 1k source tokens
```

再以 document cluster bootstrap 给出全库 token 和边数区间。

### 7.2 精度与召回 QA

- Recall gold：完整双人标注约 100–150 entries；只抽查模型输出无法测漏提。
- Precision audit：按来源、relation、方法、置信度及是否含否定/时序/阈值分层抽 600–1,000 assertions；两名临床审阅者独立标注、第三人裁决。
- `clinical evidence certainty` 与“抽取得对”分开评分。

### 7.3 必做消融

1. 当前固定 chunk vs structure-aware parser；
2. sentence、paragraph±1、whole section，等输入 token；
3. rule-only、LLM-only、hybrid；
4. exact dictionary、dictionary+SapBERT、LLM linker；
5. 无 validator、deterministic validator、independent verifier；
6. flat triples vs reified criterion bundles；
7. 逐项去掉 negation、temporality、quantity、modality；
8. 无 abstention vs quarantine；
9. WikEM structural、Merck、CPG 和 combined；
10. decoy、反向语态、`not diagnostic`、标题污染、AND/OR、年龄/人群特异阈值的对抗集。

### 7.4 下游 KG-RAG 实验

先扩展既有 48 例 source-oracle 为至少 160 例双临床审阅集，冻结构建语料与验证病例。所有 query target-blind，不含 gold 或 DA options。固定同一候选池和 selector，比较：

1. no-RAG；
2. 现有 raw-chunk RAG；
3. KG 检索；
4. KG + 原文局部 span；
5. 人工 source-oracle evidence packet。

分层终点：source capacity、assertion retrieval recall@k、decisive-evidence recall、支持/反证平衡、完整诊断与限定保真、clinical harm。这样才能区分“图谱缺边、检索错边、上下文截断、模型未利用、mapper 错判”。

## 八、实施顺序与 go/no-go

1. 冻结 source/version/license manifest；修 Merck 结构与 page/entry/adjacency。
2. 定义 LinkML v0.1；生成 JSON Schema、Pydantic 与 SHACL。
3. 做 WikEM 结构图和 Merck/CPG 高精度模板图。
4. 建 mention inventory 与 ontology linking；保留 unresolved。
5. 做 100-entry pilot，实测 `f_ambiguous` 与 token/accepted-assertion。
6. 只对复杂残差运行 citation-bounded LLM + deterministic validator。
7. 独立 verifier 与临床抽审；低置信/高风险规则 quarantine。
8. 完成 corpus-wide assertion ledger 后，再编译 CCEG/P5 与 hypothesis-relative retrieval views。
9. 下游固定候选/selector 做 raw-RAG vs KG-RAG 因果实验。

建议的首个 go/no-go 门槛：

- admission recall ≥95%；
- exact-span validity ≥99.5%；
- unsupported assertion ≤1%；
- direction、negation与 logic fidelity 分别 ≥97%；
- ontology exact-vs-parent/sibling/component 错误 ≤2%；
- 双审 high-impact assertions 全部通过；
- 相对 raw RAG，提高 decisive-evidence recall 且不增加 clinical harm；
- 报告 token/accepted clinically usable assertion，而不只报总边数。

阈值是工程启动门槛，应在 pilot 前冻结；若达不到，先修 parser/schema/validator，不应通过增加 LLM calls 掩盖。

## 九、发布与许可边界

用户对仓库数据集处理产物的发布授权不自动覆盖第三方手册或术语体系的权利。仓库 Merck manifest 已标示 `redistribution prohibited`；SNOMED 也有许可条件。因此：

- schema、代码、统计和许可兼容来源的映射可公开；
- Merck-derived graph、原文 span、长 quote 和可重建原文的结构化产物，在外发前需独立许可审查；
- 公共版可只发布本地 assertion ID、允许公开的概念映射、页/章节定位和不复刻表达的最小结构，但这仍不能替代法律/许可核验；
- 内部图与公共图应由 license policy 自动编译，不靠人工删字段。

## 十、最终推荐

采用 **Claim-centric Diagnostic KG v0.1**：LinkML 权威模型、带限定的诊断主张节点、完整逻辑树、不可变 evidence span、SSSOM mappings 与 PROV-O lineage。提取上采用 structure/template/local-linker-first，LLM 只处理复杂残差，并以“精确引用 + 确定性校验 + 独立验证 + 人工分层 QA”为准入门。

当前最合理的建设预算是先批准 **100-entry pilot**，而不是直接批准全库调用；若 pilot 的歧义比例接近中心假设，三类可见指南的核心混合抽取可按约 **330 万 token** 规划，连同定向 verifier 建议准备 **400 万–500 万 token**。混合抽取本身的高情景为 786 万；全语料 LLM 路线的中心预算约 2,076 万，质量上也不占优，不建议采用。
