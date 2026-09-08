# 疾病主体、患者事实与语义去重：实现缺陷及修复边界

本分项核对冻结 `bbc036e8` 的实际机械执行器及任务构造器，并将病例56、74、91、326、49、773中的错误回指到执行代码。**“疾病匹配错误必须引入新模型”不是成立的总判断**：精确主体被先出现的父类抢占、大小写副本成为空候选、已存在类型字段不参与接合、去重删除组归属、单位小写化等，可以确定性修改。未知同义词、多义缩写、父子/组件/病因关系和复杂观察等价，需要受控术语、来源上下文或人工/模型语义裁决；不能靠放宽字符串或换一个 embedding 阈值解决。

本文件所称“修复”均为待实施建议。生产文件未修改；[复现脚本](reproduce_identity_defects.py)调用原生产函数，生成[23项验证结果](identity_reproduction_results.json)：含1项显式负控制及成对机制组成检查，并非22个独立错误输出。它们证明机制可触发，不估计11例错误比例，也不是新算法临床验证。历史反事实数值引用上轮已冻结病例报告，未冒称本轮新跑临床实验。

## 1. 缺陷账本

行号属于上述冻结版本。[机器可读账本](identity_defects.json)保存同样的机制、修复分类和先前迁移覆盖。

| ID | 具体实现位置 | 机制与后果 | 纯代码修复边界 / 仍需语义的部分 | 既有目标与本轮增补 |
|---|---|---|---|---|
| IDN-01 | `run_mechanical_engine.py:39–54`，`norm/tokens` | 删除全部括号；把normal/abnormal/high/low/with/without当停用词。`Carcinoma(lung)`和`Carcinoma(kidney)`变相同，正常QT可与延长QT接合。有无、部位、方向先被破坏，后层无从恢复。 | 保留原文，安全格式归一化与语义解析分离是代码修复；括号是别名还是限定、正常所指的指标需解析。不能简单规定所有括号均是病种限定。 | M10/M15已有总体要求；IDR01–03明确新增最小反例。 |
| IDN-02 | `:363–372`，`run_case`主体绑定 | 第一个候选任何级别的match就break，未在全候选寻找更好身份。候选顺序决定谁获得规则。 | 全局canonical ID/受证实exact优先，收集并裁决全部命中；无精确命中则可unbound/ambiguous。此控制流修复不需要新的ML。原规则主体本身抽错，不在该修补能力内。 | M11已明确覆盖；IDR04–05提供小型执行证明。 |
| IDN-03 | `build_trial_tasks.py:121–148,175`，`slot_for`/alias union；执行器`:359` | raw label作为字典身份，上游aliases无校验并入；排序使父类/错误别名更容易先出现。同病大小写候选同时排名，后者可0断言。 | 安全格式副本合并、exact优先、保留所有原label/methods是代码；未知别名正确性是语义。禁止不经裁决把aliases建成传递闭包，单条污染会合并整个概念簇。 | M10/M11已覆盖；IDR06–07。 |
| IDN-04 | `:235–255,258–270`，`concept_match/subject_match` | 对称token包含被当主体可用性；子类、父类、兄弟病和仅共享术语都没有关系类别。 | 不用containment当same-as可以立即做；允许哪些父类命题下传、哪些子类结论上推，需要类型化本体关系与方向证明。 | M11已有；本轮明确继承真值表与open-set决策。IDR08。 |
| IDN-05 | `:140–152,266–270`，`med_stem/subject_match` | F3去词尾把organism与disease接成一个主体；字符串共同词根不是类型相同。 | 停止把词干当身份是代码；已确认病原体—疾病关系可作为causes，而不是same-as。病原体特性不能无条件迁移成患者疾病标准。 | M10/M11方向已覆盖，organism具体分型为增补；IDR09。 |
| IDN-06 | `:401–410`，predicate→finding选择 | 同一finding先匹配canonical，若弱命中即break，不再看label的exact；多个同等级事实只保留第一个，忽略时点/冲突。 | 遍历全部表述，比较完整候选；保留多见证与冲突是代码。决定哪一时点/对象适用于规则仍需scope及事件解析。**禁止仅用排序换出另一条任意事实。** | M15已有多见证总体要求；canonical提前退出是本轮具体新位点。IDR10–11。 |
| IDN-07 | `:133–135,273–291`，`markers/predicate_match` | F2共享marker便可match，marker相同不能证明positive/negative相同；反之PECAM-1↔CD31没有词面重叠而漏接。 | marker ID和结果值分离可代码实现；CD31/PECAM-1需受控别名证据。桥接marker不能移植表达该marker的不同疾病规则。 | M10/M15已有正反例；IDR12–14包含关闭marker时的正确负控制。 |
| IDN-08 | `:316–346`，`threshold_ok` | 只在两侧都给unit时检查；直接lower单位；没有measurand核验；NaN比较得到False，range高端非数值抛异常；不做单位换算。 | 有限数/范围验证、结构化invalid/unknown、缺单位不认证、UCUM转换均可确定性实现。认定PASP/mPAP、血液/组织等测量是否可比较需typed facts；单位相同仍不够。 | M07/M15/M16已有量纲和数值要求；大小写、非有限、上端异常为本轮新增具体位点。IDR15–19。 |
| IDN-09 | `:380–393`，assertion-level dedupe | key仅predicate/relation/polarity，阈值/主体范围/组/来源不同仍合并；保留首行quote和threshold却把后行最大modality写上。不是一条原规则，而是拼接物。 | 先保留occurrence/member edges，再按完整语义对象共享存储；不同阈值和来源冲突保留，不做max-modality覆盖。不需新ML即可保护已明确结构；未知同义不能自动合并。 | M12/M13已详细覆盖；IDR20复現阈值顺序决定1.5或0.5分。组成员专项由组执行审计给出。 |
| IDN-10 | 同`:384`；L3`:591–615` | 字面不同但等价的“fever”“presence of fever”各投0.8，合成1.6；改成强语义去重又可能错误合并不同时间/部位/阈值。 | 完全相同语义key/同一来源复制的一次性聚合是代码；自由释义等价需术语及逻辑约束。全局每finding一票也不总正确：同一事实可显式满足不同合法criterion。 | M12/M20已覆盖；本轮分清同义解析、表达式共享、支持来源及患者证据四种身份。IDR21。 |
| IDN-11 | `:401–402`；抽取schema `run_trial_extraction.py:219–225` | 已抽取的`value.text`不参与候选finding匹配；病例326病原体结果只存value时可不可达。 | 完整读取已有字段是代码；将`value.text`解析为test/analyte/result是语义。直接把value拼到label中可引入新的substring误接，不是充分修复。 | M14已覆盖；IDR22。 |
| IDN-12 | `:396–415`；抽取schema`:57,220–224` | 源`predicate_kind`与患者`kind/qualifiers.site/timing/laterality`已有，却完全不参与join；histopathology neutrophils可接blood lab。 | 可信类型/已填写字段的兼容守卫可以立即编码。缺字段或字段错误不能默认为兼容；需保留unknown并评测语义补全。 | M14/M15已覆盖typed join，本轮确认是“已有字段未用”而非全是schema缺槽。IDR23。 |

## 2. 把主体匹配错误拆为五个不同环节

“规则跑到不相关疾病”可来自：①LLM把原文疾病改成retrieval focus；②候选alias污染；③原始subject正确，但first-hit路由错误；④合法父子关系被当作双向等价；⑤原文确实只讲一般父类，系统却要求其为某个特异亚型证明。它们在日志里的最后形态可能相同，修补入口不同。

- **病例56是③的直接证据。** 四臂完整Sarcomatoid SCC均0条绑定，而raw已有同名subject；Carcinoma先出现抢走。上轮对已有原始行做exact主体强制路由，完整标签到3/3/5/5；这个干预没有添加新医学规则，也没证明其余被路由行全部语义正确。[病例56](../V2_INDEX_DIFFERENTIAL_AUDIT/cases/case_56.md)
- **病例773是③+④的混合。** free_v2 CTEPH绑定417条，6条同名；另411包括general PH与IPAH。不能把411全判为无关，general PH对CTEPH上位状态可能相关。实质错误是IPAH专属命题被作为CTEPH自己的规则，以及一般PH证据被反复算成特异鉴别力。[病例773](../V2_INDEX_DIFFERENTIAL_AUDIT/cases/case_773.md)
- **病例91是②+⑤及marker召回不足。** Angiosarcoma错误并入Hemangioma alias，独立完整候选缺失；PECAM-1已被抽出且正确绑定Kaposi，却没接患者CD31。安全解决marker别名，不能将Kaposi规则改送Angiosarcoma，更不能由共同marker认定两病等价。[病例91](../V2_INDEX_DIFFERENTIAL_AUDIT/cases/case_91.md)
- **病例74是候选身份与评测双层错误。** 两v2臂active CPVT实际第10，大小写空副本却第4，proxy rank可由无证据对象提供。必须在concept层计一次，保留原label终点供历史复算，而非把空副本当执行器恢复正确诊断。[病例74](../V2_INDEX_DIFFERENTIAL_AUDIT/cases/case_74.md)
- **病例49/326的证据类型问题先于相似度阈值。** 血液中性粒细胞不能充当组织浸润；阳性Brucella血清学也不能因label仅“serology”而遗失病原体。两个相反失误需同时验收，不能仅靠更宽或更严的词法阈值。[病例49](../V2_INDEX_DIFFERENTIAL_AUDIT/cases/case_49.md)、[病例326](../V2_INDEX_DIFFERENTIAL_AUDIT/cases/case_326.md)

## 3. 继承不是“有is-a边就共享所有规则”

假设本体给出`D_child → D_parent`，且作用域、时间和实体角色兼容：

| 已知父/子规则 | 可证明的派生方向 | 不允许的操作 |
|---|---|---|
| `D_parent → C`，C确是父类必要条件 | `D_child → C` | 一般“常见feature”不能改成必要条件 |
| `C → D_child`，C是子类充分条件 | `C → D_parent` | `C → D_parent`不能反推`C → D_child` |
| `C → ¬D_parent` | `C → ¬D_child` | 排除某一子类不能因此排除父类或另一兄弟类 |
| 描述父类常见征象的软关联 | 可另存明确继承的弱背景证据，具体聚合需评估 | 不生成多个独立来源票，不声明亚型特异性 |

这张表是形式推导边界，**不是本体中的所有临床描述都满足其前提**。应用规则必须保留原来源、派生路径、作用域和效力许可；统计关联不是上述逻辑箭头。同样，`Brucella causes Brucellosis`或“PFO是复合诊断一个组件”不属于is-a，不能套用继承表。

## 4. 语义去重应保护什么，而非只改字符串key

至少分离`source_occurrence_id`、`semantic_leaf_id`、`rule_id`、`member_edge_id`、`observation_event_id`、`support_provenance_id`。同一叶A在`(A∧B)→D1`与`(A∧C)→D2`中可以只存一次语义定义，但两条member edge都必须存在；跨疾病组更不应依靠同名g1归并。**成员丢失后不是简单留了一个null槽：现行代码会把不足2个成员的组删除，再让剩余原子进入L1/L2/L3。** 因此只把null替换canonical字符串还不够，必须先建立完整组身份，再维护共享引用。

表达式等价至少包括predicate concept、argument角色、极性、比较操作/阈值/单位、部位、标本、方法、时间、适用范围及逻辑profile。相同症状词并不能证明这些维度相同。严格语义对象完全一致时可以确定性hash共享；自由释义只能在受证实术语映射和完整槽位一致后合并。CNF/DNF的形式等价必须保持前轮约定的Strong Kleene未知语义，不能用经典二值恒等式消除未知传播。

存储共享与打分去重也不同：重复打印一条规则不增加患者事实，但两次不同时间的合法观察可能改变病程判据；同一观察的两个明确属性也可能满足两个独立criterion。故“每候选每finding只保留一行”与“所有语义相似句子合成一条”都不能作为通用修补。

## 5. 原仓库已有可复用结构，不能重新发明后称首次引入

除11例机械链外，仓库已经有 `src/agentclinic_tree_dx/knowledge/guideline_kg_schema.py`：`Concept`带kind/system/code，`DiagnosisExpression`分base/qualifiers/components，`FeaturePattern`含measurement/temporality/site/specimen，`ConceptMapping`区分exact/broad/narrow/related。`guideline_kg_extraction.py:_canonical_target`也有封闭alias/source-entry机制。这些通过`git show HEAD:<path>`只读核对，**不是11例机械引擎实际使用的结构**，不能拿它们的存在否认本轮bug，也不能将其验证器自动等同临床语义验证。

应做adapter兼容性审查后复用ID、类型和出处契约；仍需补执行许可、scope真值与branch语义。KG已有FeaturePattern身份字段和组引用可减少重建成本，但未知别名、术语版本、broad/narrow方向和候选alias污染仍须独立裁决。最终技术方案见[受约束语义绑定研究](semantic_binding_research.md)。

## 6. 最小可实施次序与验收边界

1. 冻结原始occurrence和字段；先修exact全局搜索、无破坏norm、完整finding遍历、类型guard、有限数/单位/range处理、成员引用及不修改跨行modality。所有改变写BindingProof/RejectReason，保持可回放。
2. 接入本仓库已有类型KG契约及版本化受控术语。明确映射类别，不把未识别对象强派给最近候选；rule subject和case finding采用不同的类型/关系判据。
3. 对仍unresolved的自由名称或同义释义，才引入BioSyn/SapBERT候选召回、上下文消歧和来源绑定裁决；候选相似度只是检索分，不是执行许可。
4. 在既有11例上只做开发性回放，按冻结候选/事实/规则分别消融。通过本文确定性不变量后仍需独立人工语义账本和新确认集，报告错误匹配率、漏匹配率、硬动作误触发、覆盖率及成本，不能以整体MRR上升替代正确性。

特别要保持两个反例：CD31/PECAM-1应桥接而CD31positive/negative不可同值；exact子类应收回自己规则而正确父类必要条件仍可有证据地继承。只拒绝全部join的实现不会满足验收。
