# Phenotype target-profile 模糊反向检索与 typed-subgraph 假设：零调用离线对照实验

> **后续实测（2026-08-25）：** typed prototype-card matcher、T/F/U gate、一对一 assignment、
> 29-case mechanics acceptance 与 200-case parser-cache safety screen 已完成，见
> [`PHENOTYPE_PROTOTYPE_GRAPH_TYPED_ALIGNMENT_AUDIT.md`](PHENOTYPE_PROTOTYPE_GRAPH_TYPED_ALIGNMENT_AUDIT.md)。
> 本文仍是 `291e9800` 的历史 whole-vignette/target-profile 对照，不能用其“typed matcher 未实现”状态覆盖后续进度。

> 日期：2026-08-25
> 冻结仓库：`cursor4@7e5546f22732725243fed8f1de68e2f8c8ad9bfb`
> 新 LLM/API 调用：**0**；probe scoring execution 网络调用：**0**（固定 MedCPT 模型的先行获取不计入 scoring）
> 模型调用：仅本地固定的 MedCPT Query/Article Encoder
> 端点：phenotype / syndrome target retrieval 与 abstention；不是疾病 Top-1 或临床部署验证

## 0. 结论先行

用户提出的方向需要拆成两个不同判决。

1. **target-profile fuzzy lane：CONDITIONAL GO-to-test；automatic ego/subgraph gain：证据不足。**
   node profile/MedCPT 值得进入受控 P1/P2，且 postings/profile ranking 比枚举 2–3 finding 组合更可扩展；
   但证据只来自 6 targets 与人工 stress cases，回答“与哪个 target profile 语义最接近”。本轮
   MedCPT 在 6 个标准阳性上 rank-only Top-1 为 **6/6**，在 6 个非逐字 paraphrase 上为 **5/6**；HPO/Mondo
   target-node lexical 在 paraphrase 上也是 **5/6**。这只是在 6 个人工、非独立临床 gold 的 paraphrase 上
   显示 rank-only surface-robustness signal；但 ego lexical 与 node lexical 的标准/改写 Top-1 完全相同（4/6、5/6），paired separation
   反而为 2/6 vs 3/6，故不能宣称自动子图扩张带来检索增益。

2. **用模糊子图分数替代 typed rule / 命题验证：NO-GO。** 同一 target 的标准阳性与配对反例比较时，
   MedCPT 只有 **3/6** 个 target 的阳性分数更高；自动扩张的 phenotype ego-subgraph 也只有 **2/6**。
   MedCPT 虽把 6 个标准阳性全部排在正确 target 的第一位，也把 5 个 assertion/identity adversarial 中的
   **5/5** 个“不应成立的 target”排到第一。用一个保证 6 个开发反例零误报的全局阈值后，MedCPT 的标准
   阳性只接受 **1/6**，paraphrase 接受 **0/6**。安全来自几乎全 abstain，而不是模型学会了否定、主体、
   时间和必要条件。

因此，最合理的迭代不是“规则 vs 子图二选一”，而是：

```text
assertion-preserving atomic facts
    ├─ exact / LOINC2HPO / ontology atom routing
    ├─ target-node lexical retrieval
    ├─ target-centric text-derived subgraph retrieval
    └─ MedCPT target-profile proposal（未来 residual lane 候选）
                ↓ 只取 union / query proposal
typed T/F/U verifier + contradiction/context gates
                ↓
query-only phenotype ledger；不得形成新票、veto 或直接写 observed fact
```

子图解决“可寻址性”，规则/验证器解决“患者现在是否真的满足”。二者不可互换。

## 1. 本轮为什么另开实验，而不是重复既有 NO-GO

既有 `PHENOTYPE_LIFT_OFFLINE_PROBE` 测了 6 张规则卡、regex proposal、疾病语料及 CPG retrieval；本轮专门
检验此前没有直接回答的问题：

> 如果不枚举 `{symptom_a, symptom_b, symptom_c} => phenotype`，而从每个 phenotype 的定义、同义词、
> ontology 邻居和文本提及构建 ego-subgraph，再让病例事实模糊匹配这些 target profile，能否同时获得
> 非逐字召回和可接受的 abstention？

旧实验已知：

- 12 个 unit smoke 的 regex 为 12/12；但 5 个 assertion/identity adversarial 为 **0/5**；
- 400 个 raw MCR vignette 只有 8 个 regex proposal；
- normalized cache 的 HPO silver linker recall@1/5/10/20 为 16.98%/50.47%/65.57%/74.06%，但 silver 本身含
  已知错链；
- G1/MedEinst 失败审计已证明 working diagnosis、否定、主体、时间和 dangling edge 不能被无类型图吞掉。

本实验不推翻这些结论，而是把“子图 fuzzy proposal 是否值得保留”与“它能否断言综合征”分开。

## 2. 实验对象与冻结端点

### 2.1 五个对照臂

| arm | 实际计算内容 | 是否能写患者事实 |
|---|---|---:|
| `rule_lookup` | 既有 6 个 whole-vignette Boolean regex matcher | 否；当前实现仍缺完整 assertion/identity 合同 |
| `ontology_node_lexical` | card-supplied HPO anchor 的 name/synonym/definition/comment（anchor scope 可能不同于 target）+ exact **target-label** Mondo identity alias；word/char TF-IDF 平均 | 否；query proposal only |
| `phenotype_ego_lexical` | node profile + HPO definition/comment 中最长、非重叠 HPO phrase mention + 一跳 `is_a` 邻居 label | 否；text mention 一律 unverified/query-only |
| `hpo_dense_ego` | 已链接 HPO atom 的冻结 all-MiniLM 向量均值 vs target anchor + definition-mention 节点均值 | 否；query proposal only |
| `medcpt_target_dense` | raw vignette → Query Encoder；target ego-profile → Article Encoder；官方 `[CLS]` + raw dot | 否；query proposal only |

子图 arm **没有读取规则卡的 `required/supportive/contradictions` 字段**。规则卡只提供 6 个 target ID/label，
以免把拟比较的规则 premise 暗中泄漏到子图。

### 2.2 子图如何自动构建

对每个 target：

1. 绑定一个 HPO anchor；
2. 保留 HPO name、synonym、definition、comment；
3. 在 definition/comment 中抽取最长非重叠的唯一 HPO alias；
4. 仅作为 `unverified_text_mention` 保存规范化 definition/comment field 与 span；这些 span **不是**可回放到原始文献的 L1 provenance；
5. 加入一跳 `is_a` parent/child 的 label；
6. 只用 **target label** exact-match Mondo identity alias；HPO anchor 名称可能比本地 target 更宽/更窄，不得冒充 target identity；
7. dense centroid 只取 anchor 与 definition-mention 节点。

本轮 19,389 个 HPO term、6 个 target 产生 24 个 mention occurrence、14 条 unique target→mentioned-node
候选边，**没有枚举任何 symptom pair/triple**。

6 个 target 中 3 个有 native target HPO ID；另 3 个本地 target 仅由 card 提供 query anchor
（HAGMA→metabolic acidosis、cholestatic pattern→cholestasis、hemolytic process→hemolytic anemia）。这些
anchor 只提供检索表面，不能被提升为 target identity。若把 target-label 与 anchor-name 查询事件合并诊断，
会在 4/6 targets 得到 5 次匹配、4 个 unique Mondo IDs（nephrotic 重复命中同一 ID）；anchor-name 命中
不得冒充 target identity。严格限制为 target-label exact identity 后，只保留 nephrotic
syndrome 的 1 个 Mondo row。

这也直接暴露了自动文本图谱的风险：

- HAGMA comment 中一般英语 `imbalance` 被唯一 alias 链到 `HP:0002172 Postural instability`；
- UIP comment 中的 `pneumonia`、`rheumatoid arthritis` 是比较/association 语境，并非 UIP 的必要组成；
- cholestasis 与 hypoxemia 定义没有可抽出的 component HPO mention；
- hemolytic anemia 只自动得到 `anemia`，没有 LDH、haptoglobin、schistocytes 等判别 marker；
- nephrotic syndrome 的定义则较理想，自动恢复 proteinuria、hypoalbuminemia、edema、hyperlipidemia。

所以“文本出现了另一个 HPO 名称”只能成为待核验边，不能自动命名为 `has_component`。

### 2.3 评测集与阈值

| cohort | n | 用途 | gold 边界 |
|---|---:|---|---|
| frozen unit positives | 6 | 每个 target 一个标准阳性 | 既有 contrast；小型工程 gold |
| frozen unit negatives | 6 | 每个 target 一个配对反例；只用其 top score 定 threshold | 既有 contrast |
| assertion/identity adversarial | 5 | 否定、错主体、混合时间、差测量质量 holdout | 既有 contrast；不参与 threshold |
| surface paraphrase positives | 6 | 人工改写标准阳性，避免逐字依赖 | robustness stress，不是独立临床 gold |
| parsed positives | 2 | normalized cache 中 MCR 2/82 的 HAGMA replay | 来自既有 query-only rule event；exploratory |
| normalized cache load screen | 200 | proposal/abstention 负载 | 无 phenotype gold，不计算 precision/FPR |

除 Boolean rule 外，每个 arm 的阈值固定为：

```text
max(top score among the six unit negatives) + 1e-9
```

即不读取任何阳性 label，优先保证开发反例零 proposal。这个阈值不是性能最优阈值，而是有意测试：
semantic similarity 能否在保守 abstention 下仍保留有效召回。

## 3. 主结果

### 3.1 Rank-only 可寻址性 vs 阈值后 proposal

| arm | 标准阳性 raw Top-1 | 标准阳性阈值后正确 | paraphrase raw Top-1 | paraphrase 阈值后正确 | adversarial 阈值后 FP |
|---|---:|---:|---:|---:|---:|
| rule lookup | 6/6 | **6/6** | 0/6 | 0/6 | **5/5** |
| ontology-node lexical | 4/6 | 0/6 | **5/6** | 0/6 | 0/5 |
| phenotype-ego lexical | 4/6 | 0/6 | **5/6** | 0/6 | 0/5 |
| HPO dense ego | 2/6 | 1/6 | 3/6 | 0/6 | 0/5 |
| MedCPT target dense | **6/6** | 1/6 | **5/6** | 0/6 | 0/5 |

这里不能把 fuzzy/MedCPT 的 adversarial FP=0 解释为理解了否定。它们只是被一个极高阈值统一拒绝：

- MedCPT 的 5 个 adversarial absent target 在 rank-only 下仍然 **5/5 排第一**；
- ontology node/ego 对 negated hemolysis、UIP、wrong-subject nephrotic 等也多把对应 target 排第一；
- HPO dense 受 linker failure 影响，有时甚至没有可评分 atom。

换言之，rank 适合 retrieval；accept/reject 需要另一种结构化信号。

### 3.2 同 target 的阳性—反例分离

| arm | 6 个 target 中“阳性分数 > 配对反例” |
|---|---:|
| rule lookup | **6/6** |
| ontology-node lexical | **3/6**；cholestatic 的正 margin 仅约 0.001，hemolytic/hypoxemia 已为负 |
| phenotype-ego lexical | **2/6** |
| HPO dense ego | **2/6** |
| MedCPT target dense | **3/6** |

MedCPT 的精确差值尤其说明问题：

| target | positive | matched negative | positive − negative |
|---|---:|---:|---:|
| HAGMA | 66.1659 | 67.2074 | **−1.0414** |
| cholestatic pattern | 58.2278 | 58.0787 | +0.1490 |
| hemolytic process | 60.0627 | 57.3025 | +2.7602 |
| nephrotic syndrome | 68.0891 | 63.3202 | +4.7689 |
| UIP pattern | 54.1296 | 58.3905 | **−4.2610** |
| hypoxemia | 59.6091 | 60.8451 | **−1.2359** |

反例与阳性共享大部分医学词汇，甚至更直白地重复 target 术语。semantic retriever 正确地认为它们“相关”，
但 retrieval relevance 与患者命题真值不是同一个任务。

### 3.3 非逐字与 parsed vignette

规则 regex 在 6 个表面改写上 0/6 proposal；MedCPT raw Top-1 为 5/6，node/ego lexical 也为 5/6，仅显示
rank-only surface-robustness signal，不能外推为全队列召回增益。MedCPT 唯一 Top-1 错误是改写后的 hemolysis 被排为 cholestatic pattern；HPO dense
还受 atom linker 错配影响。

两个完整 parsed HAGMA vignette 上：

- rule：2/2；
- node/ego lexical：rank-only 2/2，但均低于保守阈值；
- HPO dense：Top-1 0/2；
- MedCPT：Top-1 0/2，均误排 hypoxemia。

两例中决定性的 bicarbonate/pH/anion-gap 位于官方 Query Encoder `max_length=64` 的截断尾部之外，前 64
token 主要是人口学与合并症；这与错误排序一致，是一个明确的 input-contract defect 和强候选机制。由于本轮
没有补做 tail-preserving/short-query counterfactual，不能把全部失败因果归于截断，也不能据此排除 MedCPT
语义排序失败。值得注意的是 MedCPT recall@3 为 2/2，而 Top-1 为 0/2。生产假设应比较 raw vignette、
assertion-preserving short atoms 与 tail-preserving query；但当前 normalized cache 又有 `anion gap 31 →
3.0/unknown`、`pH 7.18 → TNF-alpha-like 7.1` 等已知错误，必须同时修 parser substrate。

### 3.4 200-case normalized-cache load screen

该 cohort 无 phenotype gold，只能报告 proposal load：

| arm | proposals / 200 | target distribution |
|---|---:|---|
| rule | 2 (1.0%) | HAGMA ×2 |
| node lexical | 0 | — |
| ego lexical | 0 | — |
| HPO dense | 3 (1.5%) | hemolytic ×2；hypoxemia ×1 |

MedCPT 只在 25 个 labeled/exploratory case 上执行，没有把 200 个无 gold 病例扩张成昂贵但不可解释的
precision 数字。上述 3 个 HPO-dense proposal 也不能称为 FP；需要盲法 phenotype target gold 才能判断。

这次 screen 还暴露了输入 substrate 的身份债务：45,000 条 raw HPO embedding metadata 中，42,714 条的
ID 仍 active；再按 2026-02-16 HPO 当前 name/synonym 对存储文本做严格 gate 后只剩 42,552 条。2,286 条
inactive/unknown 与 162 条 active-ID 但 stored-label mismatch 的 vector/surface 均被排除，且仍覆盖全部
19,389 个 active HPO IDs。200-case cache 的 214 个 HPO mapping events 中有 31 个（14.49%，涉及 20/200
cases）被同一严格规则隔离：1 个 obsolete、30 个 stored-label mismatch。该比率是保守的 identity-quarantine
rate，并不等于 31 个临床错误；但 `procalcitonin→obsolete radial-ray phenotype`、`GGT→LDH`、
`lipase→intussusception` 等例说明不得继续无闸门路由，也不得自动 follow `replaced_by`。

## 4. 对“以 phenotype 子图取代症状→phenotype 规则”的正式回答

### 4.1 应当做的替代

应当替代的是：

- 大量手写、表面形式固定的 `{text_a,text_b,text_c} → target` lookup；
- 对所有 2/3 组合的 materialization；
- substring 或 embedding 命中后立即写回 derived fact；
- 把 target proximity 当诊断票数。

以 target 为中心建立 profile 后，每个已链接 atom 查 posting list，并执行有界 target retrieval；完整未来 typed
路径的成本应写为：

```text
C_link(m) + C_sparse + C_dense(N_h,d,k) + O(sum postings) + O(Kma) + K*C_assign(m,a)
```

exact dense scan 的 \(C_{dense}=O(N_h d)\)，ANN 依索引而变；exact distinct-fact assignment 若用 Hungarian，
\(C_{assign}=O(\max(m,a)^3)\)。\(K\) 与每个模板 slot 数 \(a\) 必须设 cap。避免的是全局 \(O(V^2/V^3)\)
materialization；成本转移到 source-backed targets/edges、索引检索和少量 target 的局部 assignment，而不是声称
dense 只需 \(O(k)\) 或 exact matching 恒为 \(O(Kma)\)。

组合爆炸的规模也必须按 identity gate 区分：45,000 个 raw metadata surfaces 若全部误用会产生约 15.19
万亿个 pair+triple；当前可用的 42,552 个 identity-valid surfaces 仍有
12,841,290,809,676（约 12.84 万亿）个。identity 清洗不能使全局枚举变得可行；它只是避免把 2,448 条
inactive/unknown/stale surfaces 继续扩散进 linker 与向量 scorer。

### 4.2 不能替代的部分

子图 proximity 不能回答：

- finding 是 present、absent、normal 还是 speculative？
- 是患者、母亲、胎儿还是 donor？
- 事实是否来自同一时间、同一标本、同一 CT study？
- 测量是否单位/参考区间/波形可靠？
- target 需要的必要 premise 是否全部 T？
- 是否存在 contradiction 或仅有 supportive manifestation？

因此每个 target 仍需 typed verification schema。它可以不是笨重的手写“症状组合表”，而是一个版本化
predicate template：`required / supportive / contradiction / context / T-F-U / provenance / write_policy`。

## 5. 自制文本图谱应该怎样构建

### 5.1 需要构建，但不能把文本共现冒充医学关系

现有 ontology 主要提供 identity、alias 与 `is_a`；真正缺的是 target definition/criteria 到 atomic observation
的 typed edge。建议构建自制的 **provenance-bearing phenotype target graph**，其边至少区分：

| edge type | 例子 | 初始权限 |
|---|---|---|
| `lexical_identity` | shortness of breath ↔ dyspnea | canonical view；同一 fact ID |
| `ontology_is_a` | generalized edema → edema | query view；零新增票 |
| `definition_mentions` | HPO definition 中出现 proteinuria | unverified/query-only |
| `definitional_component` | 经人工核验：nephrotic syndrome requires heavy proteinuria | verifier premise |
| `criterion_for` | 正式 classification/diagnostic criteria | criteria-satisfied，不自动等于病因诊断 |
| `measurement_maps_to` | LOINC/result category → HPO | 绑定 observation、单位/参考/方法后使用 |
| `supportive_of` | dyspnea supports oxygenation concern | query-only |
| `contradicts` | normal gap / no proteinuria / poor waveform | signed verifier input |
| `associated_with` | UIP associated with rheumatoid arthritis | candidate retrieval；绝非 component |

每条文本边保存 `source URI/version/license/span/hash/relation status/reviewer`。机器抽取的边从
`unverified_text_mention` 开始；只有核验后才能变为 verifier 可消费关系。

### 5.2 可用语料的优先顺序

结合本轮 focused ledger 及其显式继承的 `PHENOTYPE_LIFT_SOURCE_AUDIT/source_ledger.json` 与本轮实测：

1. **HPO definition/comment + target-label Mondo identity**：匿名、版本化、适合作为 target spine。本轮观察到某些定义（尤其
   nephrotic syndrome）可自动提取 component proposal，但覆盖极不均匀且上下文混杂。
2. **LOINC2HPO 上游固定 TSV**：7,415 行中有 48 行命中本轮 target/subgraph HPO，涉及 7 个 active HPO ID；
   全表有 29 行/6 IDs inactive/unknown（0.391%），必须按 release/identity gate 隔离。其 interpretation 明确
   仅供 academic research，医疗使用前还需 legal governance 与 licensed medical professional 复核；在此前提下
   适合把 observation 与 L/N/H result category 路由到 atomic phenotype。它不提供 multi-finding syndrome
   entailment。`2703-7/2708-6/59408-5 low → HP:0012418` 只指本轮已核验的上游行。当前仓库 processed
   `loinc2hpo_annotations.json` 则在 162 mappings 中隔离 59（36.42%）：1 inactive +58 stored-label mismatch；
   包括 MCHC 高低方向反标、lipase→intussusception、HbA1c→先天左心畸形和 GGT→LDH，故该本地快照在重建前
   **NO-GO for routing**。strict mismatch 是 identity quarantine，不应把全部 58 条等同为已人工确认的临床错误。
3. **PMC Open Access 的定义、review、CPG 文本**：适合抽取 target→premise/contradiction 候选；必须按 article
   license 过滤并回存原句。本地旧 CPG smoke 已证明 sparse/MedCPT 路径机械可行，但索引混有 purchased Merck、
   NC/ND/NO-CC 内容，开放部署只能使用许可白名单。
4. **WikEM CC-BY-SA、Orphadata/HPOA、Monarch source-filtered associations**：分别补 emergency/syndrome
   definition 与 rare-disease candidate retrieval；association 仍不得晋升为 entailment。
5. **DisMech**：适合作为 relation/rule source discovery；pre-alpha/AI-curated，只能进入 quarantine。
6. **PubTator / PubMed text mining**：用于候选边发现和原文定位，不直接激活规则。

不建议把 heterogeneous commercial excerpts 或许可不清的整库内容作为默认 target graph 基础。

## 6. 推荐实现：两阶段、倒排而非组合枚举

### 6.1 索引

离线为每个 phenotype target 构建：

```text
target_id / label / target_type
identity aliases and ontology anchor
definition text + source span
typed premise nodes
supportive / contradiction nodes
population, time, specimen, modality gates
lexical sparse vector
MedCPT article vector
atom_id -> target_id postings
edge provenance and validation status
```

运行时：

1. parser 保留 raw span、assertion、subject、time、specimen、method、value/unit/range；
2. exact/LOINC2HPO/char+dense N-best 将每个 observation 绑定 atomic concepts；
3. postings、lexical target profile 与 MedCPT 各召回一小组 target；
4. union 后只在这些 target 上执行 typed T/F/U verifier；
5. 输出 `query_only phenotype proposal`，默认不进入 evidence count；
6. residual knowledge/candidate retrieval 使用独立 cap；base query 与排序不被覆盖；
7. 只有预先声明为 `definitional` 且全部必要 premise 为 T 的极少数 mapping，才允许生成
   `derived_zero_vote`，并保留所有 source fact IDs。

### 6.2 MedCPT 的正确使用

该 6-target engineered probe 支持把 MedCPT 保留为 query-only target-profile ranking arm；泛化、阈值和临床
效能均未证实，而且它不适合直接做 truth gate。下一次受控实验应比较：

- raw vignette query（本轮基线）；
- parser atom short query；
- parser atom + polarity/context tokens；
- sparse/MedCPT RRF；
- 以上各 arm 后接同一个 typed verifier。

primary endpoint 应为 phenotype target recall@k；safety endpoint 为 absent/wrong-subject/mixed-time proposal rate；
验证后才测 residual disease/candidate exposure。不可先用 disease Top-1 把 retrieval 与验证混在一起。

## 7. 判决边界

| 路径 | 本轮状态 |
|---|---|
| target-centric HPO/Mondo node profile 用于 fuzzy retrieval | **CONDITIONAL GO-to-test，query-only** |
| MedCPT Query→target Article profile 作为 target proposal、未来 residual lane 候选 | **CONDITIONAL GO-to-test，query-only** |
| 自动 definition-mention ego-subgraph | **source discovery 可继续并隔离；retrieval gain insufficient** |
| 自动文本 mention 直接命名为 component/criterion | **NO-GO** |
| 全局相似度阈值作为 phenotype truth/abstention gate | **NO-GO** |
| fuzzy/subgraph proposal 写 observed fact、票、veto 或 selector score | **NO-GO** |
| typed verifier + target postings，避免 pair/triple 枚举 | **PRE-REGISTERED / GO-to-build-and-test；本轮未实现** |
| full 400/800 clinical-complete 或 disease Top-1 gain | **本轮未测试** |

这个判决比“规则方案 NO-GO / fuzzy 方案 GO”更准确：规则原型在 canonical 例上精确，但表面和 assertion
脆弱；fuzzy **target-profile arms** 在 6 个手工 paraphrase 上 rank-only 更强，但 automatic ego expansion
没有显示增益，也不能判断命题成立。推荐进入下一阶段验证的架构假设是 fuzzy profile proposal + typed
verification；后者本轮尚未实现或测试。

## 8. 可复现性、模型与阻塞项

### 8.1 执行命令

```bash
python -m unittest tests/test_phenotype_lift_offline_probe.py
python analysis/mechanism_v2/phenotype_lift_failure_audit.py --check
python -m unittest \
  tests/test_phenotype_subgraph_offline_probe.py \
  tests/test_phenotype_lift_offline_probe.py
python analysis/mechanism_v2/phenotype_subgraph_offline_probe.py \
  --medcpt-python /tmp/phenotype-medcpt-venv/bin/python \
  --medcpt-query-model /tmp/MedCPT-Query-Encoder \
  --medcpt-article-model /tmp/MedCPT-Article-Encoder
```

结果：

- 既有测试：5/5 pass；
- frozen failure audit：`audit.json` byte-identical；
- contrast/parser/rule-hit 三个可物化子审计与已提交 summary 完全一致；
- 新旧联合测试：18/18 pass（含 canonical MedCPT 缺失/错误 provenance、dirty worktree、tokenizer asset fail-closed，以及 target/anchor/HPO metadata identity 合同）；
- 新 probe 第二次运行的 `summary/profile/case/cache/manifest` 五个文件逐字节一致。

canonical output 对 MedCPT **fail-closed**：任一固定本地 interpreter/model 缺失，或 Query/Article 的 commit、
weights/config/全部 tokenizer asset SHA、worktree-clean 与 `safetensors` 合同不符时，脚本在写结果前失败，不会静默省略/替换 dense arm 后覆盖同一
路径。仅调试时可用 `--allow-missing-medcpt`，且必须同时指定一个不同于提交结果目录的 `--output`；这种输出明确
是 noncanonical。summary 同时记录主进程 Python/NumPy/scikit-learn 和 helper 的 Python/torch/transformers 版本。

既有 full probe 的 reverse-disease 与 CPG 两段没有在当前 checkout 重新运行：`Guideline_*`、CPG sparse
metadata/matrix 未物化，MedCPT article FAISS/embedding 是 Git-LFS pointer。它们的已提交结果只作为历史
smoke 引用，没有混入本轮 target-level 指标。

### 8.2 本地 MedCPT provenance

| model | commit | `model.safetensors` SHA-256 |
|---|---|---|
| Query Encoder | `d83a36cc6b8e3a5c5e9d9d6ba156808c1643dcbc` | `19d78c0d5eaee2f81e6c47c5425bbadcc0c6af016cbb5da4a000d64e59d6e342` |
| Article Encoder | `d05a736da4bb84ee4057b7f7999485be6ed85465` | `a5d5ffe4d8666c1d0aa15f371b94fc3492ca8f927e5621abd4b3ee9fc845b0f3` |

两者 `config.json` SHA-256 均为
`3fea00b31d018d676d6b7e2f6cddcfe1abc69bcb88f5f09f51b848212e1671d1`。两模型的五个 tokenizer assets
也逐文件冻结：`added_tokens.json=691a5c…`、`special_tokens_map.json=b6d346…`、
`tokenizer.json=6e0460…`、`tokenizer_config.json=cabeef…`、`vocab.txt=79489a…`；完整 hashes 见
`summary.json`。两 checkout 必须 clean，helper 强制 `use_safetensors=True`。运行环境：Python 3.12.13、
torch 2.8.0+cpu、transformers 4.55.2。模型权重位于 `/tmp`，**未加入提交产物**。

HPO frozen vector 文件 SHA-256 为
`fb8d0e7607645f108d69582dcb5a7cf45780b0bb5174c4a7dc290b4d88b66d04`；其 metadata SHA-256 为
`32e398107444ddb4647a8d97e7b678ad2a950a11ed6c659bdbf770e9e222a56c`。

### 8.3 尚存限制

- 只有 6 个 target、17 个既有 contrast、6 个人工 paraphrase；不支持泛化效能声明；
- 2 个 parsed positive 是既有 rule event，不是独立 clinical gold；
- 200-case cache 无 phenotype target gold，不能计算 precision/FPR；
- normalized cache 已知存在数值、analyte、方向错链；本轮 strict identity gate 隔离 31/214 mapping events，
  但尚未重建完整 parser；
- 本地 processed `loinc2hpo_annotations.json` 的 162 个 mapping rows 中有 59 个（36.42%）strict identity
  quarantine：1 inactive + 58 stored-label mismatch，故当前资产 **NO-GO for routing**，必须从冻结上游 TSV
  重建并逐 row 审计；上游 TSV 本身 7,415 行中仅 29 行 inactive/unknown（0.391%），本轮 48 relevant rows
  均 active，仍是受 research/legal gate 约束的 conditional source；
- HPO linker 已做 active+stored-label gate，但仍不含完整 polarity/subject/numeric validation；
- MedCPT 64-token query 截断是 parsed HAGMA 失败的强候选机制，因果贡献尚未用 short/tail-preserving ablation 隔离；
- MedCPT 的 Article title 是 target label，body 只移除了与 target surface 整段完全相等的 standalone 重复字段；
  definition/comment 等来源文本仍可自然包含 target term。仍未做 label-only / anchor-node /
  +definition-mention / +is-a 的嵌套消融，不能把 MedCPT rank 信号归因于 ego edges；
- 自动 definition mention 还未做 relation/polarity/context extraction；当前 14 条边只有规范化 field offsets，
  没有 raw source URI/version/license/hash/predicate/negation round-trip，只能作 discovery diagnostic；
- 本轮未测试新 LLM verifier，也没有临床专家盲审。

## 9. 新增产物

- `analysis/mechanism_v2/phenotype_subgraph_offline_probe.py`
- `analysis/mechanism_v2/phenotype_subgraph_medcpt_encode.py`
- `analysis/mechanism_v2/phenotype_subgraph_stress_cases.json`
- `tests/test_phenotype_subgraph_offline_probe.py`
- `analysis/mechanism_v2/results/PHENOTYPE_SUBGRAPH_OFFLINE_PROBE/summary.json`
- `analysis/mechanism_v2/results/PHENOTYPE_SUBGRAPH_OFFLINE_PROBE/profile_catalog.json`
- `analysis/mechanism_v2/results/PHENOTYPE_SUBGRAPH_OFFLINE_PROBE/case_predictions.jsonl`
- `analysis/mechanism_v2/results/PHENOTYPE_SUBGRAPH_OFFLINE_PROBE/normalized_cache_predictions.jsonl`
- `analysis/mechanism_v2/results/PHENOTYPE_SUBGRAPH_OFFLINE_PROBE/input_manifest.json`
- 本报告。

本实验没有修改既有实现、规则卡、contrast、cache 或旧结果；综合提交另外只在三份既有分析文档顶部加入
状态/迭代指针，以消除 G1 前后裁决文字的歧义，不重写其历史结果。
