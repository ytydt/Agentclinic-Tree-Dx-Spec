# 低层临床事实 → 高层 phenotype / 综合征 → 反向检索：可行性实测与落地方案

> **迭代说明（2026-08-25）：** 本文保留 `7e5546f2` 首轮 6-card/CPG/MedCPT 可行性证据；关于
> “phenotype 子图还是症状→phenotype 规则”、文本语料自制图谱、组合复杂度及新增 target-level 离线对照的
> 现行结论，见
> [`PHENOTYPE_SUBGRAPH_RETRIEVAL_ITERATION_REPORT.md`](PHENOTYPE_SUBGRAPH_RETRIEVAL_ITERATION_REPORT.md)。
> 当前实测只支持 fuzzy target-profile proposal 作为 query-only 候选；automatic ego expansion 的增益证据
> 不足。带 slot/edge、distinct-fact、T/F/U 的 typed-subgraph matcher/validator 是预注册待建假设，未来若
> 通过验证，才可能成为 entailment/write-back 授权层。

> 日期：2026-08-25
> 冻结仓库基线：`cursor4@a945aa57ae1254c0cd24dd0ff0b04fb4e680040f`
> 上游方案：[`PHENOTYPE_LIFT_REVERSE_RETRIEVAL_RESEARCH.md`](PHENOTYPE_LIFT_REVERSE_RETRIEVAL_RESEARCH.md)（提交 `38977314c`）
> 新诊断 LLM/API 调用：**0**；本轮仅运行规则、TF-IDF、仓库既有 CPG 索引及 MedCPT Query Encoder
> 结论适用范围：检索可寻址性与候选暴露；不是临床部署验证，也不是最终 Top-1 提升声明

---

## 0. 执行结论

这条路线**可行，且值得进入 P0–P2 工程验证**；但工程对象不能是一个无类型的
`{任意 2/3 findings} => syndrome` 字典，更不能把综合征标签与组成 findings 拼接后直接覆盖原查询或
加入同一诊断分数。

当前决策应明确分层：**GO**＝修建 atomic substrate、规则规格、开放语料过滤和独立 residual-retrieval
评测；**NO-GO**＝把当前 6-card regex 原型接入 Forest/IMPC/Collapse3c、写 derived fact 或声称 disease
exposure/accuracy 增益。它在 5-case exact-card disease replay 中没有显示 lift-only rank gain，并在 5 个
assertion/identity adversarial 上全部失败。

本轮实测支持的最小安全范式是：

```text
原文与结构化 evidence
  → assertion-preserving atomic facts
  → modality-specific concept proposals
  → 单项 observation interpretation
  → candidate-blind、三值逻辑的 typed rule cards
  → append-only phenotype-lift ledger
  → atom-only base retrieval（冻结）
     + 独立 phenotype-lift residual retrieval
  → identity-safe candidate admission
  → 原有 selector/comparator
```

上图是**目标架构**，不是本轮 regex probe 已完成的实现。本轮 6 张 card 是可执行引擎的规格草案；实际
scan 仍是 candidate-blind 的 whole-vignette Boolean regex，只能测试“是否值得提议一个查询”，尚未实现
T/F/U、distinct fact ID、subject/time/specimen/same-panel 等合同，故其所有触发一律 `query_only`。

其中高层 phenotype 的价值是给检索器增加一个原文未出现、但临床上可寻址的查询视图；它**不是第二份
患者证据**。只有严格定义型 measurement/pattern rule 在全部必要前提为真时，才可写入
`derived_zero_vote`；proxy、疾病关联、embedding 相似、机制路径及正式 criteria 尚未完全核验的结果都只能
是 `query_only`。

离线原型已经给出三条决定性证据：

1. regex proposal 可在未见选项/答案的 400 例 MCR 原文中提出 8 个 pattern query，但 12 个 unit smoke
   之外新增的 5 个 assertion/identity adversarial contrast **0/5 通过**；这证明 candidate-blind proposal
   可运行，也证明 typed fact substrate 是先决条件，不能把 8 次触发当成临床 rule pass。
2. 使用 card 实际发出的精确 label，而非事后更具体的 oracle query 后，`hemolytic process` 对 TTP 的
   lift-only rank 是 58（base 7），对 MAHA family 是 50（base 2），未形成 exposure 增益；急性间质性肾炎
   中，真实存在的 `nephrotic syndrome` 若与原子查询拼接，还会把病因从第 35 拖至第 45。pattern label
   本身不会自动连接到正确病因，且不能与 base 共享查询/cap。
3. 在 205,115 个 CPG chunks 上，sparse、MedCPT 与 RRF 均可完成五个 pattern query；保守 open-license
   subset 中 cholestatic 的 heuristic first-relevant rank 为 sparse 4、dense 4、RRF 1。但这只是五-query、
   非盲 chunk smoke，且 full index 混有采购/NC/ND/NO-CC 内容；不能据此宣称临床 relevance 或开放部署收益。

因此建议把项目正式命名为 **typed phenotype lift / residual query expansion**，而不是继续称为“症状集群
打包”。

---

## 1. 本轮相对既有进度新增了什么

本报告不把 `3897731`、`aba0832`、`59fe703a7` 与最新进度混为一谈：

| 冻结点 | 本轮如何使用 |
|---|---|
| `38977314c` | 读取初步数据源与 `PHENOTYPE_LIFT_V1` 方案，作为待验证假设，不重复当作新结论 |
| `aba083272` | 读取此前症状集群代码、逐阶段日志、失败报告与 normalized vignette cache |
| `59fe703a7` | 读取 MedEinst held-out 结果与分析；不把缺失运行轨迹误当完整证据 |
| `a945aa57a` | **本轮唯一最新基线**；补齐的 `cases.jsonl`、`llm_calls.jsonl`、mapper、replay 与 case score 是轨迹审计依据 |

输入还包括用户上传的结构化 vignette 与补充说明。补充说明中对 hypoxemia 示例的修正、typed relation、
“保留 atoms + composite”及 HAGMA/胆汁淤积/溶血/肾病综合征/UIP 五组目标例，均在本轮规则卡和 contrast
set 中落实；没有把说明中的每个建议未经验证地当成医学真值。

本轮新增并可重跑的资产：

- [`phenotype_lift_offline_probe.py`](phenotype_lift_offline_probe.py)：零网络、零 LLM 的离线实测；
- [`phenotype_lift_failure_audit.py`](phenotype_lift_failure_audit.py)：从 G1 与 `a945` 冻结轨迹机械重算计数，并绑定人工语义账本；
- [`phenotype_lift_rules_v1.json`](../../data/knowledge_raw/phenotype_lift_rules_v1.json)：6 张 typed rule prose/spec 草案；
- [`phenotype_lift_contrast_cases.json`](phenotype_lift_contrast_cases.json)：12 个 unit smoke + 5 个 assertion/identity adversarial contrast；
- [`PHENOTYPE_LIFT_OFFLINE_PROBE/summary.json`](results/PHENOTYPE_LIFT_OFFLINE_PROBE/summary.json)：规则、linker、
  disease retrieval 与 CPG/MedCPT 结果；
- [`case_rule_audit.jsonl`](results/PHENOTYPE_LIFT_OFFLINE_PROBE/case_rule_audit.jsonl)：400 例中 8 个触发事件；
- [`input_manifest.json`](results/PHENOTYPE_LIFT_OFFLINE_PROBE/input_manifest.json)：输入版本与 SHA-256；
- [`source_ledger.json`](results/PHENOTYPE_LIFT_SOURCE_AUDIT/source_ledger.json)：22 个数据源/语料/模型的访问、许可、角色与再分发 guard；
- [`failure audit.json`](results/PHENOTYPE_LIFT_FAILURE_AUDIT/audit.json)：13 个 G1 exact-loss 与 400 例/9,225 条 MedEinst 调用的可复现失败账本；
- 固定的 LOINC2HPO annotation、上游许可和导入说明。

---

## 2. 首先修正“2–3 个症状转成综合征”的语义

### 2.1 hypoxemia 不是三票表决

原示例不能写成：

```text
tachypnea + SpO2↓ + dyspnea = hypoxemia
```

更准确的表示是：

| 输入 | 与 hypoxemia 的关系 | 输出权限 |
|---|---|---|
| 经标本、单位和参考解释校验的低动脉 PaO2 | `measurement_definition` | 可产生零票 derived phenotype |
| 低 SpO2，且波形/设备、供氧、海拔、人群语境可信 | `direct_proxy_for` | 默认 query-only；完整校验后才可升级 |
| dyspnea | `manifestation_of/corroborates` | 不能单独推出 hypoxemia |
| tachypnea | `manifestation_of/corroborates` | 不能单独推出 hypoxemia |

dyspnea 与 tachypnea 也可见于代谢性酸中毒、疼痛、焦虑、心衰等。反过来，明确低氧测量已足以提出
hypoxemia；另外两项只是支持表现。当前仓库把 `SpO2 < 92` 直接映射到 HPO 的做法必须降级，因为原路径
还会丢失 `test_name/value/unit`，无法保留供氧和测量质量。

### 2.2 必须分开的关系

| relation | 例子 | 能否构成新证据票 |
|---|---|---:|
| `lexical_equivalent` | shortness of breath ↔ dyspnea | 否；同一 fact 的 canonical view |
| `interprets_as` | 低 K 测量 → hypokalemia | 否；可为零票 derived fact |
| `direct_proxy_for` | 低 SpO2 → hypoxemia proposal | 否；先 query-only |
| `manifestation_of` | tachypnea → respiratory distress | 否；相关表现不等于定义 |
| `corroborates` | dyspnea 支持已存在的氧合异常 | 否 |
| `criterion_for` | 多项条件满足某正式 criteria | 按完整规则；缺任一必要槽位为 U |
| `shares_mechanism` | fever/CRP/WBC 共享炎症过程 | 只用于依赖建模/检索 |
| `synergizes_with` | honeycombing + traction bronchiectasis + distribution | 组合有新增信息，不能先压掉 |
| `contradicts` | 正常氧合或不兼容测量语境 | signed negative，不能无符号计数 |

这里的根本区别是：**本体祖先、疾病具有表型、若干事实满足规则**是三种不同的边。任何实现若把它们
统一成 `related_to`，都会复活此前已经观察到的关系方向错误。

---

## 3. 既有失败路径的逐层根因，以及本轮对旧结论的修正

### 3.1 大本体/substring/cluster score 为什么不够

此前 4,641 条 parser facts 的冻结审计已经显示：

| 旧路径 | 结果 | 根因 |
|---|---:|---|
| 名称含 syndrome 的精确查表 | 5/4,641 = 0.11% | 事实很少逐字等于命名综合征 |
| HPO label/synonym exact | 178/4,641 = 3.84% | parser 输出包含修饰、数值和整句描述 |
| 双向 substring | 3,489/4,641 = 75.18% | 覆盖来自误配；无 assertion/type/context |
| HPOA gold disease coverage | 66/400 = 16.5% | disease–phenotype association 不是综合征定义 |
| 冻结 payload cluster rerank | conversion 0.355 → 0.307 | cluster 命中数不是 candidate-specific likelihood |

因此可用的不是“更大 fuzzy”，而是 N-best proposal + 类型/命题校验 + abstain。

### 3.2 G1 的旧 NO-GO 需要收窄

原 G1 报告按字符串/canonical-key gate 得到 arm A `60/67`、arm B `56/67`，并据此关闭两臂。本轮逐案
复核 13 个 unique exact-loss 后发现：这个 gate 混合了临床丢失与 label identity 变化。

| 语义类别 | unique cases | arm-case events | 例子 |
|---|---:|---:|---|
| exact-equivalent | 2 | 2 | Stump appendicitis；Milker’s nodule/Paravaccinia |
| clinically complete | 3 | 5 | Auricular angiosarcoma；GPA/Wegener；Hyperglycemic hemiballismus/diabetic striatopathy |
| compatible parent/component | 4 | 5 | metastatic liver adenocarcinoma；sarcoma；nerve sheath tumor；DIC |
| true loss | 3 | 4 | Malakoplakia；Liposarcoma；vertebral hemangioma |
| unresolved | 1 | 2 | congenital lower-lip palsy vs asymmetric crying face syndrome |

按可确定的临床等价恢复：

- exploratory、非盲的语义复核会把 arm A 计为至少 `63/67`；
- arm B 会计为至少 `60/67`，case 67 的盲审决定是否到 `61/67`。

这**不能追溯性改写预注册门**：原 canonical-key identity gate 仍按预注册口径失败于 60/67、56/67，
也不能用 post-hoc 复核重开 arm。它只说明原 gate 不足以支持“临床召回失败”的解释；如需改变科学判定，
必须预注册 clinical-complete endpoint 并做独立盲审/确认 replay。

所以 G1 支持的是“prompt 会改变候选表面/对象粒度且存在少量真丢失”，而不是“两个 arm 均已证明临床
召回失败，更不是 phenotype lift 的普遍否证”。其中真丢失反而给规则层提供了具体靶点：MCR134 已出现
Michaelis–Gutmann bodies 这一高度特异的组合，却没有映射回 Malakoplakia；MCR19/196 则暴露了把同一
correlation group 的协同证据当冗余压缩的风险。

这也修正了 `3897731` 初版报告中“G1 两臂均不过门”的表述：那是 identity gate 的历史结果，不可再写成
clinical-complete gate。

### 3.3 `a945aa57` 的新轨迹把问题定位到命题与边，而不只是实体名

对 400 例完整 MedEinst 轨迹的离线审计显示：

| 阶段 | 冻结轨迹现象 | 对 phenotype lift 的约束 |
|---|---|---|
| 抽取 | 7,334 个 P node，6,358 个（86.69%）可逐字回指原文；analytic parse failure 5/400 | 缺抽取不是唯一主瓶颈；必须保留 offset/provenance |
| assertion | raw Absent 1,282 条，其中 488 条因窄 cue set 被降为 Missing | `present/absent/unknown` 不能由脆弱关键词表决定 |
| 命题角色 | 179 个 P node/129 案与 frozen Top5 疾病串重叠；73/395 one-liner 含 candidate；40 个 provisional/differential 疾病名被标 Present | working diagnosis/differential 不得作为 phenotype atom |
| 复合 proposal | 3,170 个复合 K node；composite ReExamine Found 1,115/1,743（63.97%），atomic 676/2,309（29.28%） | candidate-conditioned 复合串通过 OR-like 搜索自证，不可作为 syndrome discovery |
| 图完整性 | 25,713 条边中 2,963（11.52%）端点悬空；matching 边 1,923/9,575（20.08%）悬空仍计分 | 先验 edge integrity/proposition validation 是硬门 |
| signed evidence | frozen lexical/heuristic `n_match_absent=234`、`n_match_generic=221`，仍进入无符号匹配特征 | lift 不能靠无符号“匹配数”进入排序 |
| legacy soft-match diagnostic | `diagnoses_match`（exact/双向 substring/leaf score≥0.85，DA 还允许 gold option）判 163/400 “in Top5”；最终 audit candidate 399/400 仍来自原 Top5 | 这不是 safe-exact 或 clinical-complete exposure；只能说明系统几乎不创建新 candidate identity |
| legacy score diagnostic | 在上述 legacy-soft-match 163 例中，score argmax 为 37/163（22.70%） | 不是 clinical conversion；仅说明 matching 数量不具 specificity，lift 分数不能直接成为 selector 分数 |

逐案机制尤其清楚：

- **MCR259**：把 varicosities 升级推成 AV fistula，将 KTS 改错为 Parkes Weber；这是从表现到机制的
  无授权上推。
- **MCR344**：共享肺部/全身表现被重复计数，“无发热”还被当作 TB 正向支持；这是 dependency 与 polarity
  双重错误。
- **MCR432**：working diagnosis 与 differential 被当成 Present，令候选自带支持；这是命题角色泄漏。
- **DA473**：`influenza panel=negative` 被拆为 “Influenza panel, Present”，阳性 PCR 又丢了 analyte；这是
  assay–analyte–result 绑定失败。
- **DA480**：2500 m 雪埋窒息与呼吸表现被拼成 HAPE compound，再以“entire narrative”自证；这是
  candidate-conditioned composite hallucination。

因此新实现必须 **candidate-blind**：规则 matcher 只能看原始/规范化事实，不得看候选疾病名、答案选项或
后续候选解释。

### 3.4 现有 structured parser 的具体数据债

本轮读取的 200 例 normalized cache 含 3,561 个 evidence items、387 个 normalized entries；305 个 items
产生至少一个数值 parse（共 308 个数值 entry），212 个 items 带 HPO ID。它适合错误发现，不适合作为
clinical gold，因为没有 offset、specimen、method、experiencer、temporality，影像/病理标准化近乎空白。

已确认的逐 case 错误包括：

- CA-125 → KL-6；
- creatinine `130–150` 被解析为 `13.0`；
- `type 2 diabetes` 的 `2` 被路由为 BNP=2；
- neutrophils `16.5×10^9/L` 被 percent 规则判成 neutropenia；
- pH 7.18 被误路由为 TNF-alpha=7.1；
- anion gap 31 被读成 3.0/unknown；
- ALP 235、原文参考范围 15–250，却被标为 Elevated ALP；
- high anion gap 与 low bicarbonate 都过早 collapse 为 `Metabolic acidosis`，抹掉 HAGMA 的两个独立前提。

最后一例是关键：higher-order rule 必须匹配带 identity 的原子事实，而不是匹配已经 collapse 的 HPO label。

---

## 4. 可用数据源：没有单一真值库，应按角色分层

### 4.1 匿名或低摩擦核心层

| 数据源 | 获取/许可 | 最适合的角色 | 明确不能承担的角色 | 本轮决定 |
|---|---|---|---|---|
| [HPO/HPOA](https://github.com/obophenotype/human-phenotype-ontology/releases) | 匿名 release；HPO 专用许可 | atomic phenotype、同义词、`is_a`、罕见病 association | 多 finding 充分条件、通用数值阈值 | 使用；本地 `2026-02-16`，官方最新 `2026-06-23`，先固定本地以复现 |
| [LOINC2HPO](https://github.com/TheJacksonLaboratory/loinc2hpoAnnotation) | 匿名 Git；随上游许可/LOINC notice | 已绑定 LOINC + H/L/N/POS/NEG → 单项 HPO | 自由文本、参考范围、多项 syndrome | 上游固定 TSV 经 release/identity gate 后 conditional；当前 processed JSON 59/162 strict quarantine，重建前 NO-GO for routing |
| [RadLex](https://radlex.org/) | 无账户但 click-through license | imaging finding/anatomy/同义词 | 影像组合判据 | 建议 P0 拉取；保留原 RID/关系，不改写 |
| [Mondo](https://github.com/monarch-initiative/mondo/releases) / [DO](https://github.com/DiseaseOntology/HumanDiseaseOntology) | Mondo CC BY 4.0；DO CC0 | syndrome/disease target identity、crosswalk | 患者事实与组合规则 | 用作 target namespace；官方最新 Mondo `v2026-07-06` |
| [Orphadata](https://sciences.orphadata.com/phenotypes/) | 匿名，CC BY 4.0 | ORPHA–HPO–frequency reverse DDx | 常见病与 syndrome 定义 | 推荐作为开放 rare-disease lane |
| [Monarch KG](https://monarchinitiative.org/kg/downloads) | 匿名 association downloads；逐 source 许可 | phenotype→disease association、跨源候选 | entailment/criteria | 只拉 disease–phenotype association；保留 `provided_by` |
| [MedGen](https://ftp.ncbi.nlm.nih.gov/pub/medgen/README.txt) | 匿名 FTP/NCBI API | source-filtered alias/xref/manifestation relation | 未过滤的开放再分发真值 | 可用；按 `SAB` 排除 OMIM/SNOMED 等受限 atoms |
| [OHDSI Phenotype Library](https://github.com/OHDSI/PhenotypeLibrary) | Apache-2.0；当前 3.37.0 | measurement/time/inclusion/exclusion 的表达范式 | 短 vignette 的现成 syndrome 总库 | 研究规则表达与测试，不直接导入为 truth |
| [DisMech](https://github.com/monarch-initiative/dismech) | 内容 CC BY 4.0、代码 BSD-3；pre-alpha | shared-mechanism/rule proposal、来源发现 | 自动激活、veto、诊断权威 | 本轮审计 3 个 module；只作 candidate source |
| [PheKB](https://www.phekb.org/phenotypes_old) / [PheMA CQL](https://github.com/PheMA/phekb-phenotypes) | public 浏览；全库机器许可/顶层 license 不清 | 少量 criteria 的人工参考、CQL pattern | 批量 scrape/再分发 | 选择性研究，不纳入默认数据包 |

HPO 的 true-path 只允许真正的 `is_a` 传播；官方建模指南明确警告不要把 bundled phenotype 的“常见组成”
误编码为父子关系。HPOA、Monarch、MedGen 等 association 只能产生候选，不得升级成临床定义。

### 4.2 免费但需个人注册/许可的增强层

| 数据源 | 门槛 | 价值 | MVP 决定 |
|---|---|---|---|
| [LOINC 2.83](https://loinc.org/news/loinc-version-2-83-release-highlights) | 免费个人账户，无机构采购 | observation identity、specimen/method/scale | 不阻塞 MVP；站点/报告参考范围优先于默认值 |
| [UMLS 2026AA](https://www.nlm.nih.gov/databases/umls.html) | 免费个人 UTS 许可与使用义务 | 大规模别名、CUI、semantic type、crosswalk | 可插拔 linker 增强；必须 source/license filter |
| [SNOMED CT](https://www.snomed.org/get-snomed) | member/affiliate/地域许可 | finding model、同义词、属性与后协调 | 不作为匿名默认依赖；严格隔离许可 |
| SNOMED GPS | 全球免费但仅 flat term | ID、FSN、US preferred term | **不能做语义推理**；无 hierarchy/relations/logical definitions |

这些来源都不要求机构出面采购，但注册、地域与再分发治理会损害匿名复现，故不应成为 P0/P1 的硬依赖。

### 4.3 本轮实际拉取与冻结

只把体量小、匿名可得、与本轮实测直接相关的 LOINC2HPO annotation 提交进仓库：

- upstream commit `c1068d6d6b80ce757ff7a26e4c38a5ac8e7c830c`（2021-11-07）；
- 7,415 rows，3,118 unique LOINC，827 unique HPO；
- scale：Qn 6,116、Ord 1,208、Nom 91；
- table SHA-256 `bb112ccf9359719bdf2c18a45d3a3e6116059a19d917cdc4473ad0642e4141e0`；
- 原始 [`License.md`](../../data/knowledge_raw/phenotype_lift_sources/loinc2hpoAnnotation/License.md) 与
  [`README.md`](../../data/knowledge_raw/phenotype_lift_sources/loinc2hpoAnnotation/README.md) 同步保存。

后续 identity audit 更新了执行边界：上游 TSV 的 7,415 rows 中有 29 rows/6 HPO IDs inactive/unknown
（0.391%），本轮 48 target-relevant rows/7 IDs 均 active；但当前 processed
`data/knowledge_raw/loinc2hpo_annotations.json` 的 162 mappings 有 59（36.42%）需 strict identity
quarantine（1 inactive +58 stored-label mismatch）。因此“已拉取上游”不等于“本地处理版可路由”；后者必须
从冻结 TSV 重建并逐 row 审计，且 obsolete ID 不自动 follow `replaced_by`。

没有把 RadLex click-through、需账户的 LOINC/UMLS/SNOMED、许可不清的 PheKB/PheMA 批量内容提交；也没有
把 DisMech 的 AI-curated YAML 复制成真值。DisMech 本轮固定审计 commit
`4056b61c01f7f9eedf60db3c863ecd697c80eb9d`，只在 rule card 中保存上游 URI、commit 与 pre-alpha 警告。

---

## 5. 可处理非标准 vignette 文本的实现路径

### 5.1 parser 忠实抽取，normalizer 后置

不应要求 vignette parser 一开始就输出标准 HPO/LOINC。最小 atomic fact 应保存：

```json
{
  "fact_id": "F17",
  "raw_text": "satting in the mid 80s on room air",
  "start": 418,
  "end": 455,
  "modality": "vital",
  "polarity": "present",
  "epistemic": "observed",
  "temporality": "current",
  "experiencer": "patient",
  "observable_candidates": ["pulse oxygen saturation"],
  "test_or_loinc_candidates": ["LOINC:59408-5"],
  "value": 85,
  "comparator": "approximately",
  "unit": "%",
  "specimen": null,
  "method": "pulse_oximetry",
  "oxygen_context": "room_air",
  "quality": "unknown",
  "provenance": {"parser": "...", "source_span_sha256": "..."}
}
```

linking 顺序：

1. exact/local alias 与已知 observation code；
2. modality-filtered word/char BM25/TF-IDF N-best；
3. HPO/RadLex/LOINC/SNOMED/UMLS 各自受控词表的 dense proposal；
4. 用 semantic type、specimen、method、assertion、age/context 过滤或重排；
5. 低 score、低 margin 或类型冲突时 abstain，绝不使用双向 substring 自动落 top-1。

本轮用 HPO 43,284 个带 ID 的 label/synonym 对 212 个现有 silver-mapped items 做 char 3–4 gram proposal：

| k | silver recall | 解释 |
|---:|---:|---|
| 1 | 36/212 = 16.98% | 不可自动 top-1 写入 |
| 5 | 107/212 = 50.47% | 可作为候选生成 |
| 10 | 139/212 = 65.57% | 仍需 context/type rerank |
| 20 | 157/212 = 74.06% | recall 上升同时噪声增加 |

这不是 accuracy：silver labels 本身包含上述 CA-125、pH、anion gap 等错误。它只证明 lexical N-best 是
有用 proposal layer，不能证明自动归一化可靠。

### 5.2 单项 observation adapter 先于多项规则

每种模态要有不同 adapter：

- lab/vital：`raw test → observation identity → value/unit/range → result category → phenotype`；
- imaging：`study + anatomy + finding + distribution + assertion`，不能把 procedure 当 finding；
- pathology：`specimen + morphology/stain + result`；
- history/treatment response：保留主体、时序、干预与反应，不强行塞进 HPO。

数值参考顺序必须是：原 vignette/performing-lab range > site/method/population validated rule > unknown。病例 76
给出 ALP 235 与本实验室 15–250；本轮 matcher 正确判 ALP=0.94×ULN、R-ratio=7.7756，未触发胆汁淤积，
而旧 cache 错标 Elevated ALP。

### 5.3 production typed rule card 目标规格，不做“2/3 即通过”

正式可执行的每张 card 至少必须结构化包含：

```text
rule_id, target_id/label/type, semantics,
required branches, supportive atoms, contradictions,
threshold/unit/specimen/method, temporal window,
population/setting, source/version/license,
write_policy, validation_status
```

本轮 JSON 中的 6 张卡只是**有版本的 prose/spec 草案**，用于固定 target、premise、contradiction、quality gate
与预期写权限；它们尚未把 threshold/unit/specimen/method/time window、source license、target type 与
`validation_status` 全部结构化，也没有配套 JSON Schema。因此它们不能被运行时解释为 production typed cards。

目标引擎必须使用 T/F/U：缺失为 U，不是 F；不同时间、标本、主体或 correlation identity 的事实不得凑成 AND；
derived phenotype 必须保存全部 `derived_from_fact_ids` 与 raw spans，并继承 correlation identity，防止 parent、
child、atoms 四重计票。

本轮 6 张 card 的目标权限刻意不同；下表是正式引擎通过验证后的 activation intent，本轮 probe 一律不执行：

| rule | 必要结构 | 目标权限（本轮不执行） |
|---|---|---|
| HAGMA | acidemia/明确代谢性酸中毒 + 低 HCO3 + 高 AG，同一 panel/time | 全 T 时 `derived_zero_vote` |
| cholestatic pattern | ALP>ULN、相对 ALT/AST 不成比例、肝源支持 | 参考范围/R-ratio 未全面验证前 query-only |
| hemolytic process | anemia/Hb fall + ≥2 独立 destruction/response markers | clinical gold 前 query-only |
| nephrotic syndrome | heavy proteinuria + hypoalbuminemia + edema | 全 T 时零票 derived；阈值须人群/单位合格 |
| UIP pattern | honeycombing + traction bronchiectasis + basal/subpleural distribution | 影像 study/context/alternative 未绑定前 query-only |
| hypoxemia | validated low PaO2，或有质量/供氧语境的低 SpO2 proxy | PaO2 可验证后 derive；SpO2 默认 query-only |

12 个 unit smoke 全部通过，包括 threshold、缺一项、症状-only、单一 haptoglobin marker 及病例 76
参考范围反例。但新增的 5 个 adversarial contrast 全部失败：negated hemolysis markers、negated UIP findings、
母亲 proteinuria 与患者 albumin/edema 混主体、治疗前后 HAGMA 混时间，以及 `unreliable` 被 substring 当成
`reliable`。因此当前 matcher 只能叫 **unsafe proposal smoke**，不能叫 typed rule implementation，更不能
执行 card 中的 derived write policy。

---

## 6. 离线实测

### 6.1 400 例 candidate-blind rule scan

probe 在每例 question/options 之前截断文本；400/400 均移除了 answer material，截断后残留 0/400，确保
答案/候选名不能触发 proposal。400 例仅 8 次；它们全部是 `query_only`，不是 rule pass：

| rule | n | cases / gold |
|---|---:|---|
| HAGMA | 2 | MCR2 5-oxoprolinemia；MCR82 euglycemic DKA |
| cholestatic pattern | 3 | MCR295 gallbladder carcinoma；MCR410 IPNB；MCR438 chemotherapy-induced sclerosing cholangitis |
| hemolytic process | 2 | MCR397 cancer-associated MAHA；MCR448 TTP |
| nephrotic syndrome | 1 | MCR364 acute interstitial nephritis |
| UIP / hypoxemia | 0 | 当前 matcher/队列无合格触发 |

这 8 次说明 candidate-blind proposal matcher 能发出查询，也揭示两个边界：

- 拟设计为高 precision 的 rule proposal 在当前小规则集上很稀疏；需要 30–50 条优先规则或富集 contrast cohort
  才能做总体效应评价；当前 0/5 adversarial 也说明“高 precision”尚未被实现；
- phenotype 为真不代表它能替代病因信息。MCR364 的 nephrotic syndrome 与 AIN 可以同时成立，但 syndrome
  query 对病因检索是噪声。

### 6.2 disease reverse retrieval

在 `Guideline_common + Guideline_rare` 的 16,371 行（16,102 个 casefold-unique labels）上，以 word 1–2 gram
以及 char 3–5 gram TF-IDF 做 rank fusion。文件与 Hugging Face `QiaoyuZheng/DiagRL-Corpus@402ff97d` 哈希一致；
dataset card 标 Apache-2.0，但 common rows 聚合 Mayo/WebMD/Merck/随机网页等来源，dataset-level tag 不能自动
覆盖底层 excerpt 的再分发权。因此这是仓库既有、许可异质的 exploratory corpus，不是本轮推荐的开放 KB。
五个 base query 是人工从病例整理的 post-hoc query，lift query 才严格使用 card label；它没有测试 upstream
binder 的端到端质量。结果仅是机制 smoke，不是诊断准确率：

| case | endpoint | base rank | exact-card lift-only rank | 拼接查询 rank（诊断臂） | 解释 |
|---|---|---:|---:|---:|---|
| MCR397 | MAHA family | 2 | 50 | 2 | `hemolytic process` 太宽；先前用 MAHA oracle 得到的第 3 位不属于 card 输出 |
| MCR448 | TTP complete | 7 | 58 | 4 | exact-card lift 无 exposure 增益；拼接改善不可部署 |
| MCR364 | AIN complete | 35 | 1,252 | 45 | syndrome lift 真实但伤害 etiologic retrieval |
| MCR2 | 5-oxoprolinemia | — | — | — | target 不在 corpus，lift 不能创造缺失 relation/doc |
| MCR82 | euglycemic DKA | — | — | — | 同上 |

因此这 5 个病例没有证明 exact-card disease exposure gain；它们证明 corpus relation、target 粒度与 lane
隔离必须另测。部署中禁止“拼接查询”臂；它只作为诊断性对照保留。正确合同是：

```text
base results = byte-identical atom-only retrieval
lift results = independently capped residual tranche
merge = base unchanged + lift-only identities
```

跨 lane 的 duplicate 只能屏蔽 lift duplicate，不能把 lift 的 support/view/score 合并回 base，也不能让 lift
占用 base cap。

### 6.3 CPG sparse / MedCPT / RRF

仓库已有 205,115 个 chunk（8,038 个 unique article）的 768 维 `IndexFlatIP` Article Encoder 索引。本轮临时拉取官方
`ncbi/MedCPT-Query-Encoder`，固定 commit
`d83a36cc6b8e3a5c5e9d9d6ba156808c1643dcbc`，权重 SHA-256
`19d78c0d5eaee2f81e6c47c5425bbadcc0c6af016cbb5da4a000d64e59d6e342`。模型权重和临时运行环境未提交。
实际 dense replay 使用 Python 3.12.13、`faiss-cpu 1.15.0`、`torch 2.13.0+cpu`、
`transformers 5.15.1`、`numpy 2.5.2`、`scikit-learn 1.9.0`；版本也写入机器摘要。复跑形式为：

```bash
<venv>/bin/python analysis/mechanism_v2/phenotype_lift_offline_probe.py \
  --medcpt-model <pinned-ncbi-MedCPT-Query-Encoder-checkout>
```

probe fail-closed 核对 CPG metadata、sparse matrix、dense `ids.json`、config `ntotal` 与 FAISS `ntotal` 均为
205,115，且逐行 metadata ID 与 dense ID 完全一致；模型目录缺失时不会联网下载。

这个 CPG 不是全开放 corpus：198,996 个 PMC-OA chunks 中既有 CC BY，也有 CC BY-NC/ND/NO-CC；另含
3,311 个已采购 `Merck-Manual-19e` chunks 和 2,149 个缺 license note 的 chunks。full-index 的 HAGMA 与
hemolytic dense top hit 即来自 Merck；因此不能用其结果声称匿名开放方案成立。本轮另做了保守 open replay，
只保留 `PMC CC BY`、`PMC CC0` 与 `WikEM CC BY-SA`，共 142,074 chunks；dense open arm 从前 1,000 个
FAISS hits 后置过滤。

以透明、非盲的 term/marker heuristic 判断 top-10 中是否有 pattern 相关 chunk，并排除标题末尾明确为
References/Conflict-of-Interest/Acknowledgments 的 chunk 作为“相关”命中。保守 open replay 为：

| query | sparse-open first relevant | MedCPT-open | RRF-open | 描述性观察 |
|---|---:|---:|---:|---|
| HAGMA | 1 | 1 | 1 | 五-query smoke 中两路均找到 marker-rich chunk |
| nephrotic | 1 | 1 | 1 | 同上 |
| hemolytic | 3 | 1 | 1 | dense/RRF 在此 query 较早 |
| cholestatic | 4 | 4 | 1 | RRF 在此 query 较早 |
| UIP | 2 | 5 | 1 | RRF 在此 query 较早 |

这只证明 sparse、MedCPT 与 RRF 的机械路径都可运行，并提示 fusion 可能改变非逐字 chunk 的可达顺序；
它不是 blinded relevance benchmark，也没有证明 current lift 增加 disease target exposure。top hit 仍会落在
泛相关甚至 section-noise chunk（例如 References/Conflict-of-Interest 标题），故下一步需 article-level 去重、
section quality filter、open-license hard gate 与盲法 relevance judgement。dense similarity 绝不能写成临床
关系边。

---

## 7. 在 Forest、IMPC、Collapse3c/APHHM-C 中如何应用

### 7.1 共同硬约束

任何分支都必须满足：

1. lift 发生在原始 vignette 的 assertion-preserving fact substrate 上；
2. rule matcher 看不到 candidate/option/gold；
3. base registry、base score、base frontier、ID 与相对顺序先冻结；
4. lift 使用第二个 registry/frontier 与预留 `lift_k`，不固定填满；
5. 无 candidate-unique 原文证据时只输出 document/DDx retrieval，不直接 admission；
6. derived phenotype 不进入 evidence count、vote、veto 或 base candidate score；
7. 全链记录 `atom → proposal → validation → fragment → candidate → selection → mapping`；
8. failure 时 query sidecar fail-open 回 base；validation 不完整时 fail-closed 为 U。

### 7.2 Forest / IMPC

安全插入点在 [`mosaic.py`](../../src/agentclinic_tree_dx/mosaic.py) 的 `_ingest_generator` 之后、三路/多视图
identity registry 与 `registry.score()` 完成、base frontier 已冻结而 selector payload 尚未构造时。

不能直接消费历史 Forest/IMPC evidence ledger：现有 2,400 条轨迹普查表明 polarity、epistemic、modality、
reliability 分别退化为 `present/observed/text/1.0`，且没有 temporality。应从原 vignette 建 sidecar typed facts。

实现建议：

```text
base_registry/base_frontier  -- existing, frozen
lift_rule_engine(raw facts)  -- deterministic, candidate-blind
lift_retriever(query_lifts)  -- independent cap
lift_registry                -- no view/support/score merge into base
selector_payload             -- base + admitted lift-only reserved slots
```

IMPC 的多 view 是生成器视图，不等于不同独立症状；不得把 `n_views` 当 syndrome rule 的 premise count。

### 7.3 Collapse3c / APHHM-C

在 C1 后可生成 query sidecar，但必须先校验 `raw_span` 的 verbatim/offset、subject、time、polarity；保持
`_generate_concepts`、C3 prompt、ConceptRegistry 及现有 base ranking/frontier 不变。只有 base frontier 冻结后，
才允许一个 deterministic knowledge-nomination API 追加 lift-only 候选；最终比较仍在
[`aphhm_c.py`](../../src/agentclinic_tree_dx/aphhm_c.py) `_select_frontier` 前完成 admission。

不可复活 C4 全局 relation matrix，也不可把 lift 送回 C3 prompt：现有日志已证明生成式 composite 与
candidate-conditioned “Found” 会自证；C4 relation substrate 又有方向/有效性 NO-GO。规则卡的每条 edge
必须有独立 source、版本、premise 与 write policy。

Collapse3c 虽比 Forest/IMPC 保存更多 absent/past facts，但 a945 轨迹中的 dangling edge、unsigned negative
与 differential-as-present 表明它仍未达到直接规则真值的要求。

---

## 8. 建议实施顺序与预注册

### P0：atomic binder/linker gold

从 current 200 parsed + a945 400 raw vignettes 按 history/exam/lab/vital/imaging/pathology 分层，人工标注至少
每模态 50 spans；过采样：

- explicit absent / unknown / historical / family member / possible；
- CSF/BAL/urine 与 blood 的 specimen 冲突；
- room air vs supplemental oxygen、poor waveform；
- 多生命体征同句、范围、比较符、等价单位；
- working diagnosis/differential 与真实 observed finding。

指标：span P/R/F1；value/unit/specimen/method/polarity/time/experiencer slot accuracy；link Recall@1/5/10、
MRR、semantic-type exact、risk–coverage；危险 assertion/specimen/subject 错误单独报告。

进入 P1 的硬门建议：

- source span/offset 可回指率 1.00；
- option/candidate leakage 0；
- high-confidence 自动链接的错误上限及 abstention coverage 预注册；
- 不再使用 substring containment 作为 truth gate。

### P1：30–50 条来源化 rule pack

优先级：

1. measurement interpretation：电解质、血细胞、明确酸碱状态；
2. 少量多前提 physiologic patterns：HAGMA、hemolysis、cholestatic、nephrotic；
3. imaging patterns：UIP 等，必须绑定同一 study/distribution；
4. formal criteria：只有明确版本、适用人群、时间窗和排除条件时加入；
5. shared mechanism 只作 proposal，不激活。

每条正例至少有一个只翻转一个槽位的 contrast：present↔absent、current↔past、patient↔family、
confirmed↔possible、threshold±epsilon、blood↔CSF/BAL、room-air↔oxygen、valid waveform↔artifact、顺序置换与
无关 distractor。

规则指标：T/F/U confusion、precision/recall、false entailment、contrast flip、provenance completeness；
`supported/query_only → entailed/observed` 越权必须为 0。任何没有临床 gold 的 card 继续 query-only。

### P2：冻结 retrieval A/B（本轮原型的下一步）

```text
A = atoms-only base tranche
B = byte-identical A + independently capped phenotype-lift tranche
```

报告：document/candidate Recall@k、MRR、clinical-complete 与 partial exposure、unique lift gain、duplicate/noise、
target-absent、base identity retention、base cap eviction、错误对象粒度。base identity retention 必须 1.00、
base cap eviction 必须 0。

P2 只能声称 retrieval/exposure；没有 selector 输出的 lift candidate 不得伪造 Top-1。DA 与 MCR 分开，且
safe-exact、clinical-complete、partial、task mapper 端点不得混读。

### P3：分支接入

只有 P0–P2 过门才分别接入 Forest、IMPC、Collapse3c/APHHM-C。比较：

- base-only；
- lift residual document retrieval；
- lift-only reserved candidate admission；
- 可选的 future verifier，但调用数与 prompt 需单独预注册。

指标分解：

```text
新增暴露并正确转化
- lift 直接夺冠干扰
- 共享候选上下文重排
- 对象粒度损失
- schema/interface failure
```

不要再用一个“cluster score”或“width”把这些机制压成单指标。

---

## 9. 本轮不执行、但可预注册的 LLM 路径

本轮没有新增 LLM 调用。若未来需要，可把 LLM 限制在两个窄接口：

1. **linker disambiguator**：输入原文 span、N-best ontology candidates 与结构化 context，只能选一个、保留
   top-k 或 abstain；不能生成疾病或新事实。
2. **rule evidence verifier**：输入已冻结 facts、rule premises、source snippet，只能逐 premise 输出 T/F/U 与
   span；不能自由诊断、改写规则、删除候选或产生 score。

需预注册：模型/provider/version、temperature、schema、最大重试、cache、blindness、调用上限、fail policy、
人工 adjudication sample。未来 LLM 结果仍不得把 association/embedding 提升为定义性 entailment。

---

## 10. 不能从本轮结果宣称什么

- 12/12 unit smoke 与 0/5 adversarial 一起表明 regex 不是 typed engine，更不是规则临床准确率；
- 400 例只有 8 个 triggers，不能估总体 recall 或最终 accuracy；
- HPO linker 以有错误的 cache 为 silver，只能估 proposal recall；
- CPG “相关”使用透明 term/marker heuristic，不是 blinded expert relevance；
- disease corpus 缺 5-oxoprolinemia 与 euglycemic DKA 目标，不能把 null rank归因于 rule；
- MedCPT/RRF 在五个 query 上的 rank 变化只说明检索机械路径可运行，不说明 relevance 或 syndrome 成立；
- G1 的 manual semantic audit 修正了 identity gate，但 case 67 仍需盲审，且不能倒推新 prompt 会提高最终
  clinical-complete Top-1；
- a945 的 MedEinst 轨迹是理解失败机制的观察证据，不能作为 phenotype-lift intervention 的效果实验。

---

## 11. 最终建议

### 立即做

1. 合入本轮 6-card/17-contrast/离线 probe 作为研究基线，并把 0/5 adversarial 明示为 P0 blocker；
2. 修 atom substrate：offset、assertion、subject、time、specimen/method、value/unit/range、oxygen context；
3. 扩展到 30–50 张高价值、来源化 rule cards，但默认 query-only；
4. 拉取匿名开放的 Orphadata、Monarch disease–phenotype association 与 source-filtered MedGen 处理物；
   RadLex 另走 click-through/license gate，保留原 RID/名称/关系且不擅自改写；每条保留版本、provenance、
   license tier；
5. 完成 P0 gold 和 P2 双通道 exposure replay，再决定是否接 selector。

### 暂不做

- 不找或构造一个无来源的“2–3 symptoms → syndrome”大字典；
- 不用 substring、embedding、HPO ancestor、SNOMED two-hop 或 DisMech path 直接写患者事实；
- 不把 syndrome 拼进 base query、共享 cap 或共享 score；
- 不让 candidate-conditioned LLM 发现/确认 composite；
- 不固定填满 lift_k，不用 lift 删除或 veto base candidate；
- 不把需注册/受限的 UMLS/SNOMED 作为匿名 MVP 的硬依赖。

最值得验证的正式命题是：

> 在原始 facts、生成调用及 base retrieval tranche 完全保留的前提下，少量高精度、带 provenance 的
> measurement/pattern lift，能否通过独立 residual lane 增加 clinical-complete candidate exposure；只有当
> 新增暴露与转化超过对象粒度损失、候选干扰和关系错误时，才进入 Forest/IMPC/Collapse3c 的预留槽实验。

这既利用了高层 phenotype 的检索价值，又避免把相关、代理、机制和正式综合征定义混成同一逻辑边。
