# 从字符串匹配到受约束语义绑定：针对实现缺陷的技术调研与方案

检索/核验日期：2026-09-08。只采用原论文、作者稿及官方标准。本文服务于IDN-01–12的修复选择，不替代上轮逻辑抽取文献综述；没有训练、下载模型权重或调用OpenRouter，所有方法比较均为待验证设计。来源及访问边界见[identity_sources.json](identity_sources.json)。

**建议的技术核心不是“用更强模型给每条规则找最近疾病”，而是建立可拒绝、可追溯、区分关系类别的绑定系统。** 全局exact优先、组引用完整性和类型守卫先以代码修复。仅对不能由已知术语和字段约束解决的残余项引入语义模型；检索候选分数、术语映射、规则迁移许可和患者literal真值必须分开。

## 1. 哪些既有研究可直接借鉴，哪些能力没有被证明

| 工作/标准 | 可借鉴的机制及原始证据 | 本仓库适用位置 | 不应声称的能力 |
|---|---|---|---|
| **BioSyn，ACL2020** | 稀疏字符特征与dense表示联合候选检索；对同概念的多个同义名称做边际化训练，并迭代更新难负例。论文§6.2自身区分词典缺项、上下文多义、重叠、缩写、上下位错误。[原论文](https://aclanthology.org/2020.acl-main.335.pdf) | 把规则subject或observation概念召回到有限术语候选集，尤其补词面不相似的名称。 | 不证明候选same-as；论文的实体归一化指标不是整条诊断规则的方向/范围/临床执行正确率。 |
| **SapBERT，NAACL2021** | 利用UMLS同概念名称做度量学习、自对齐与难样本挖掘。原文明确其设定只处理名称自身、不使用名称的上下文；推理为近邻检索。[作者camera-ready稿](https://arxiv.org/html/2010.11784v2) | 可作为比通用MiniLM更贴近同义关系的候选召回对照；受控词典已知同义边用于训练/候选构建。 | 名称相似度不解决临床适用范围，也不自动区分所有同名异义。不能设一个全局cosine阈值便授予硬动作。 |
| **BELHD，2024** | 把知识库同名异义条目加入消歧名称；利用有边界的上下文表示和同文档candidate sharing。作者稿以**已知mention span、in-KB实体**为实验设定，并把返回多个实体判错。[作者原稿](https://arxiv.org/html/2401.05125v1)、[正式论文](https://doi.org/10.1093/bioinformatics/btae474) | 保留疾病类型/部位等消歧描述，供上下文reranking；同名不应直接union，格式括号不应被无差别删除。 | “名称扩展后唯一”只是知识库表示唯一，不等于mention已正确消歧；该实验不能证明NIL/未入库概念识别能力。 |
| **Schwartz–Hearst，PSB2003** | 由文本中的短形/长形定义对提取缩写。论文在标准集合报告96%precision/82%recall，并讨论定义匹配与多义消歧的区别。[作者原文](https://people.ischool.berkeley.edu/~hearst/papers/psb03.pdf) | 先解析文章内明确定义，再用文档/章节作用域限定缩写映射，成本低于每次请求LLM。 | 未定义缩写不一定可解析；在一篇文章成立的缩写，不能写成全库永久same-as。性能数字不用于本仓库保证。 |
| **SNOMED CT官方语义** | 明确区分描述逻辑下的subsumption和equivalence，并允许按较宽概念查询更细概念。[官方说明](https://docs.snomed.org/snomed-ct-practical-guides/snomed-ct-data-analytics-guide/4-snomed-ct-overview) | ConceptMapping区分exact/broad/narrow/related；已知is-a作有方向的继承证明。 | 父类检索覆盖不是子类诊断充分性；“related”更不是“synonym”。规则上下位继承取决于箭头方向和scope。 |
| **LOINC观察身份** | 用Component、Property、Time、System、Scale、Method六部分描述观察/检验身份。[官方Users' Guide](https://loinc.org/kb/users-guide/major-parts-of-a-loinc-term) | 补足“neutrophils”是血中数量还是组织形态；区分同单位不同压力/比值、测试方法、标本。 | 代码化观察身份不证明患者做过测试或结果阳性；LOINC轴也不代替全部患者角色/时点/诊断阶段信息。 |
| **UCUM** | 单位语法、维度与换算；区分case-sensitive和专门的case-insensitive编码体系，不能对前者任意lower。[官方规范](https://ucum.org/ucum)；可复用[NLM转换接口规范](https://ucum.nlm.nih.gov/ucum-service.html) | 替代手写的ms/mmHg别名；精确换算、单位有效性和维度检查；支持保留原单位及转换证明。 | 单位可换算不代表被测量对象相同；两种压力同为mmHg仍不能互换，百分比也可能是完全不同分母。 |

这些方法互补而非自动叠加后保证正确。BioSyn/SapBERT解决名称召回，BELHD提示同名消歧和上下文重要，SNOMED/LOINC/UCUM提供类型与关系约束。如何从完整指南句识别真正subject、如何从病例读取事件与数值，仍是上游语义抽取任务。术语库只约束允许的解释，不替来源编造解释。

## 2. 两条绑定链采用不同合同

**规则→疾病概念**的输入应包括source span、章节继承范围、原始subject表述、目标角色、类型、限定和已知术语候选。输出是`BindingDecision`，而非改写后的疾病字符串。建议字段：`source_occurrence_id / mention_span / candidate_concept_ids / chosen_concept_id / mapping_relation / scope_id / evidence_basis / resolver_version / status`。`status`至少为accepted、ambiguous、unbound、rejected；`mapping_relation`至少包括equivalent、source_narrower、source_broader、overlap/related、causal_component、incompatible、unresolved。

**规则literal→患者观察**还需predicate concept、被测属性、结果、unit、specimen、method、site/laterality、person/role、event/time和极性。先做类型与范围准入，再判断哪个观察可作为见证，最后求literal真值。`matched_concept=true`不能立即变成`satisfied=true`：同一marker的阴性观察可证明阳性literal为False；未测试为Unknown；不同标本或时点则未必是这个literal的合法见证。

两个命名空间不共用无类型的`concept_match`。规则主体无疾病可以是test/procedure/management goal；这类对象送往工作流动作，不因当前候选focus被强配疾病。具体阶段与branch权限由任务2补充合同定义。

## 3. 分阶段技术方案

### B0：确定性保护，先停止可证明的错接

仅做不依赖新医学知识的修改：安全格式归一化；既有typed字段兼容守卫；global exact lookup；遍历finding全部label/canonical；保留冲突和多见证；单位/有限数验证；语义leaf共享而member edges保留；完整key的已知重复去重；schema和来源对象不可变。这层**不接受“找不到就nearest”**，未绑定项保持可审计。

exact并非绝对真理：当同一个已知字符串属于多个不同概念，exact阶段输出ambiguous集合，而不是挑排在前面的一个。`DiseaseX`大小写安全副本可合并；`Hemangioma`带Angiosarcoma错误alias不能因此合并。Code-only阶段可阻止未验证alias进入等价闭包，但无法单靠代码知道所有未知alias是否正确。

### B1：版本化术语与显式关系，复用已有KG结构

为文档和观察建立版本化术语子集，先用已知canonical ID与审核alias。保留同义映射的证据、术语版本、语域和限定；同名映射保留多目标集合。复用仓内`Concept/ConceptMapping/DiagnosisExpression/FeaturePattern`，通过adapter接入机械链，不能再以字符串label作为永久身份。

关系推理先只开放最小可证明子集：exact可绑定；父类必要条件向子类派生、子类充分结论向父类派生需独立proof；病因、部件、可能相关只保留类型化边而不当same-as。混合规则组的root target固定后，成员不能借另一个目标的alias改变组归属。

缩写解析先取来源内明确定义，记录definition span和可见范围。跨章节遇到新定义必须遮蔽/重开作用域。marker词典和疾病词典分开；PECAM-1↔CD31是marker概念映射，不能生成Kaposi↔Angiosarcoma映射。

### B2：残余名称召回与上下文裁决

在B0/B1的unbound/ambiguous集合上比较：词典exact基线、BioSyn稀疏+dense、SapBERT dense、加入BELHD式消歧描述/上下文的模型。只取候选Top-k，**不将retrieval top1直接写入临床绑定**。加入明确NIL选项以及原术语未被候选集覆盖的状态；仅比较in-KB问题会掩盖真实缺词。

裁决器只输出上述关系类别、对应source spans及缺失槽位，不能补缺失检查结果。可以是受约束cross-encoder、冻结LLM或人工审阅，对照时输入相同候选集与相同完整上下文。两端都要审：原文到底指哪个疾病，以及该概念与当前候选的关系；否则只是把focus污染从抽取器搬到resolver。

置信度必须在按source/concept分组的开发样本上校准，按语义类别和hard/soft用途分别设门槛；高相似度不宣称概率。无法消歧时保持unknown，不软化为“微弱支持”继续计分。错误拒绝率和覆盖率必须同时报告，防止系统以拒绝所有困难项获得表面高精度。

### B3：完整命题的受约束去重

仅当两个literal经确定性规则或审核映射获得同一typed语义对象，且极性、阈值、范围、事件变量、比较方向一致时共享leaf。规则级去重另比较完整AST/root target/effect/scope/proof profile，并保留所有member edge与来源occurrence。来源相同的重复窗口不新增独立支持；不同来源的一致性可另报source agreement，不能默认转成患者likelihood ratio。

语义近似只建立`possibly_equivalent`待审边。禁止以embedding连通分量自动union；一条false-positive边可污染整个簇。方向相反、阈值不同、部位或时序不同必须成为hard-negative对照。父子规则可能存在蕴含关系但不是同一规则，不能为“降重复率”删掉更具体的规则。

## 4. 评价必须比Accuracy@1更细

在任何新模型试验前冻结以下关系标注和反例集。每个测试项有原始source、可见上下文、两端概念/观察和裁决说明，人工式AI审阅不得标作独立临床双审。

| 测试层 | 正例 | 关键反例 | 主要指标 |
|---|---|---|---|
| safe format身份 | CPVT大小写副本 | 不同部位/亚型括号限定 | order/duplicate invariance；错误合并率 |
| synonym | PECAM-1与CD31 | Hemangioma与Angiosarcoma | same-as precision/recall；false-same-as方向表 |
| hierarchy | 已验证child→parent | 父类充分条件偷渡给child、跨兄弟继承 | relation混淆矩阵；许可错误数 |
| category/causal | 明确病原体引起疾病的边 | 病原体性质当疾病必要条件 | type violation与causal→same-as误判 |
| observation identity | 同指标合法单位换算 | PASP/mPAP、比值/分量、血液/组织 | typed join precision/recall；槽位错误 |
| result/state | CD31阳性见证阳性literal | 阴性、未测；推荐测试当阳性结果 | literal T/F/U正确率；非法硬动作 |
| temporal scope | 同一相关事件的两个表述 | 当前阳性/既往阴性；患者/家族成员 | event binding正确率与unknown覆盖 |
| compound rule identity | 同AST同scope多来源 | 相同谓词不同阈值/组/动作 | member完整率；错误merge/split；proof保持 |
| open-set | 术语内候选存在 | 真正概念未入库或未入候选集 | NIL precision/recall；coverage-risk曲线 |

需要两种互补样本：实际旧/v2输出的概率抽样用于估计错误分布；困难负例富集集用于验证易误杀边界。不能把后者的通过比例外推为总体性能。切分以来源文档、概念/近邻族和规则模板为单位，避免同义列表或同一指南释义同时进入训练和确认。

对照顺序为`现行字符串→B0确定性修补→B1受控术语→B2语义裁决`，各阶段冻结同样规则、病例事实和候选集合，随后再独立测试自动抽取端到端。报告未绑定、错误绑定、语义歧义、类型拒绝、漏掉合法继承以及新增硬错误，保留所有候选分差。不能因某项bug曾巧合救回gold，便把保留错误作为最优技术方案。

## 5. 交付边界

本轮完成了明确实现位点、可运行反例、原始文献核验和可执行研究方案，未声称已建立高准确的临床实体链接器。B0是可以立即拆成代码PR的修补清单；B1需规范化术语映射及adapter；B2/B3涉及新的语义技术与评测，应先证明受限任务上的可靠性，再获得root动作权限。所有source/group/observation身份与任务2的阶段/适用范围语义同时保留，避免修好名称后继续执行错误种类的规则。
