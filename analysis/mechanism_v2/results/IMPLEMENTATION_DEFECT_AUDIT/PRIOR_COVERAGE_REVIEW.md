# 既有设计覆盖、实现边界与本轮新增义务的独立复核

冻结输入：`cursor4@bbc036e8a6ec93583be915a4609fe86278ed062c`。本文件独立复核“缺陷是否已列入 redesign”，不替代本目录的代码缺陷复现，也不宣称修复已进入生产。机器对应表为 [prior_coverage_map.json](prior_coverage_map.json)；定位引用均绑定该提交，行号变化后须重新定位。

## 1. 结论：应补实施规格和机制复现，不能把已写明的要求称作首次发现

用户举出的五类实现问题——错误主语绑定、跨窗口组混并、原子去重损坏成员边、语义去重不足、竞争名单被作为定向反证——在既有 M10–M13、M19–M22 中已经明确列出。治疗/检查/诊断用途分离与 `applicability` 也已列入主报告和合同。它们仍然是未落实的提案，因此“已覆盖”不能回答“是否已经修好”。本轮的新增价值应是把每个故障定位到输入—代码状态—输出的可复现机制，给出最小修复边界，再把原来原则性的阶段/范围要求补成可执行的数据和动作合同。

既有产物并没有把所有问题称为纯代码 bug：M10/M11 区分已知身份绑定和未知语义关系；M12/M20 区分重复出现与独立证据；M05/M18 已要求规则类型和授权。新报告需要进一步给出**现在能修的实现错误、修后仍然未解决的语义问题、需要新方法验证的部分**，避免把采用术语库/LLM verifier 当作修复确定性 first-hit 的必要条件。

## 2. 用户所举问题与原提案逐项对应

| 问题 | 原覆盖位置 | 本轮需要深化的部分 |
|---|---|---|
| 模糊主语抢占真正 exact 候选 | M10/M11；旧 REPORT §7 明确全局 exact/verified alias 优先 | 顺序置换、父类/兄弟/组件反例；确定身份后如何绑定可直接修，未知身份需要术语与关系解析 |
| 规则组莫名合并 | M13；EXTRACTION_PROTOCOL §4 明确跨窗口局部 ID 不可合并 | 对 `_title/_section/_focus/gid/norm(subject)` 的完整碰撞条件给最小复现；不要泛称所有不同疾病组都无条件合并 |
| 去重后的组成员缺失 | M12/M13；REPORT §3 明确保留每处 member occurrence；协议写明 `shared leaf不删除occurrence` | 先建 occurrence 和成员边再共享原子存储；审查 singleton 退回原子硬动作的后果 |
| 字符串去重不足 | M12/M20 | 同时测过度去重：阈值、范围、比较目标、来源不同却被合并；语义等价识别必须兼顾漏合并和误合并 |
| 竞争语句数充作定向反证数 | M22；REPORT §9 明确 DDx 名单不产生 −0.5 | 逐行 L4 缺失的 polarity/context/threshold/root/direction 许可，及重复惩罚和存活者依赖 |
| 无直接分行改变别人权重 | M19；REPORT §8 和 case49 | 先准入再建 claimants；增加不合格行不应改变任何候选权重；合法证据删除可能重加权，不能静态减票代替重放 |
| 治疗/检查/诊断不分用途 | M05/M08/M18/M19；REPORT 的动作表已有“检查、治疗、工作流” | 增补 `rule_purpose/action_target/action_modality/event_status/allowed_consumers`，提供全消费者准入矩阵 |
| 推荐检查变成患者阳性证据 | M05/M14；SEMANTIC_CONTRACT §4 已禁止 | 区分推荐、医嘱、执行、结果观察；未指明疾病目标的建议应允许非疾病客体，不能补造 disease subject |
| 适用范围/人群条件 | M04/M18；SEMANTIC_CONTRACT 字段表已有独立 `applicability` | 定义 scope 继承、unknown/不适用、年龄界值、缺省范围、必要性反例的范围条件 |
| 分情况讨论与分支 | 提取协议要求整体保留工作流分支；原递归 IR 可表达局部条件，但选择政策不完整 | 新增多分支选择/重叠/优先级/覆盖/else/异常政策，以及分支 guard 的来源和求值证明 |

每条对应的精确原文、文件行号和 M 编号保存在 `prior_coverage_map.json`。表中 `explicit` 表示要求已明确出现，**不表示有生产实现或通过了医学验证**；`explicit_principle_partial_executable_contract` 和 `partial` 表示已有原则而本轮需补行为合同。

## 3. 对现有实现的两项必要纠正

### 3.1 它不是完全没有阶段信息，也不是已经正确执行阶段语义

`run_trial_extraction.py:36–45` 的 relation 已含 `treated_by`，`context_type` 已含 `treatment/prognosis/epidemiology`；`:65` 将该字段输出。`run_mechanical_engine.py:28` 定义 `SOFT_CONTEXTS`，`:520–528` 和 `:557` 用其阻止部分原子硬动作。因此“从未记录阶段、所有阶段完全同处理”不符合代码。

但这个字段混合了章节性质、论证用途和文本布局：`table_row` 是布局，`imaging/histopathology` 是证据模态，`treatment` 是临床活动。它无法区分同一诊断章节中的治疗推荐、同一治疗章节中的不良反应诊断，也没有完整的动作客体/行动状态/适用范围语义。`claimants` 在完整准入前建立；组用全部 context 集合的子集判定整体 soft；L4 不消费同一 context 门。因此已有局部保护不能作为端到端阶段隔离的证据。

“治疗内容都没有诊断价值”也不应变成新规则：已观察到的治疗反应、不良反应、诊断性试验治疗可以有诊断用途，前提是原文确有相应诊断关系、病人有对应事件和时间证据，并且该用途单独通过准入。单纯治疗建议或治疗资格不能反推患者确诊。新槽位应表达此区别，不能按章节标题一刀切。

### 3.2 当前组错误不是字面上的空槽，也不是所有不同疾病组直接无条件合并

`run_mechanical_engine.py:380–394` 在**已绑定候选内部**按 `(norm(predicate), relation, polarity)` 留首行；被去重的后行及其成员关系被删除，并没有创建显式 `null member` 占位。随后 `:434–446` 才按窗口标识片段和规范化原始 subject 建组，少于两行的组被丢弃，剩余原子不在 `grouped_ids` 中，便进入独立原子执行。这是**成员边丢失、来源/效力混合、组退化**，不是一个已正确识别缺失成员但暂未填值的数据结构。

组 key 中仍含 `norm(a['subject'])`，因此原始 subject 规范化后不同，单靠绑定到同一候选并不会必然合成一组。真正应分别复现：跨缓存但同标题/章节/focus/局部 gid/规范 subject 的碰撞；主语先被抽错；规范化丢掉限定后成为相同 subject；以及不同疾病来源的行都被误标为相同 subject。这些机制不能混成一种“group_id 全局 g1”错误。修 stable namespace 能阻止身份碰撞，但不能修复原始主语语义错误。

## 4. 另一条既有 KG 路线可复用，但不能冒充已接入本实验

此前迁移矩阵追踪的是机械实验栈的十个源文件，未纳入独立的 `src/agentclinic_tree_dx/knowledge/guideline_kg_schema.py` 及其 authoring/export 工具。这份 KG schema 已具有下列资源：

| 现有资源 | 冻结代码锚点 | 可以直接复用的工程部分 | 不能由此推断的语义能力 |
|---|---|---|---|
| Concept/DiagnosisExpression/ConceptMapping | schema:317、330、495；`MAPPING_PREDICATES` | 稳定 ID，疾病/检验/标本等类型，exact/broad/narrow/related 边分离 | related/broad 不是同义；合法映射记录不证明医学映射正确 |
| 递归 LogicExpression | schema:85、361、698 | 引用结构、operator arity、not 单子式、k 合法范围 | 不含完整量词变量/域，未给 K3 求值、root effect 和源组完整性语义 |
| typed feature 与人口字段 | schema:343、386；cross-record:993 | 时间/标本/部位/单位、population 引用的类型检查 | `population_context_ids` 不是可求值适用表达式，也不规定 unknown guard/age cutoff/分支优先级 |
| 完整图/增量图校验 | schema:903、1065、1096、1128 | dangling reference、operand 类型、循环、证据跨度引用、增量原子验证 | 图结构有效不等于规则忠实、患者证据吻合或有硬动作权限 |
| WikEM 名单非计分通道 | extraction:653 起；`enumeration_only=true`、`ranking_eligible=false` | 将检索导航与诊断证据分离的接口、非计分导出 | 消费者仍须执行标记；标记本身不是反证内容或许可 |

本复核在六个冻结机械 runtime 文件中搜索 `guideline_kg_schema/LogicExpression/DiagnosticAssertion/population_context_ids/ranking_eligible`，均无引用。它们分别是抽取、门闸、机械引擎、四臂评分、检索编排和检索类；扫描结果保存在 JSON。这个证据只说明**上述六文件没有使用这些 KG 对象/许可**，不声称仓库每个算法都从未接入 KG。

KG 的 `extract_wikem_differential_memberships` 函数说明“candidate-membership, never as criteria”；`scripts/build_guideline_diagnostic_kg.py:134–138` 又显式将广义未审核导出标为 `ranking_eligible=false`；`scripts/export_guideline_kg_safe_views.py` 开头明确只输出 non-ranking views、不能验证临床含义。因此可借用现有校验器/枚举类型/身份结构来降低新实现成本，不能直接把已有 KG 导出接到 L4 或疾病硬裁定。

迁移仍需一个显式适配合同：哪些字段能无损映射，哪些缺失必须 `unsupported/needs_review`；不得把 KG `necessity/diagnostic_role/direction` 的独立枚举自动拼成获授权的必要/充分规则。`LogicExpression` 不允许重复 operand 是结构约束，但“两个患者事件属于同一概念”不等于重复标准，也不能以删 operand 代替成员来源和临床计数单位的判断。

## 5. 本轮归类与证据标准

| 类型 | 判定标准 | 本轮适当的交付 |
|---|---|---|
| 确定性实现缺陷 | 对已明确规格，给定合法输入发生错误变换/依赖/状态 | 最小反例、真实函数路径、修复建议和修后正反例；不需要新 LLM 技术 |
| 规格/接口缺口 | 没有规定完整数据或动作语义，无法仅凭旧输出决定正确行为 | 明确新合同与兼容边界；不是改一行即可恢复缺失信息 |
| 语义启发式能力限制 | 名称/文本/来源含义无法从现有结构确定，模糊匹配猜错 | 术语/语义解析/验证方案、拒绝与覆盖曲线、独立参照；修法不能承诺零错误 |
| 有意消融/研究政策 | 例如 closed-world、all⇒required、F10 平均或可选 F8 的配置 | 记录实际启用情况及政策有效性；未启用路径不得解释冻结 11 例下降 |
| 观察器/评测约定 | trace 截断、fate 标签近似、proxy gold/历史 ranking 定义 | 修审计与指标；保留历史版本，不把测量变化当临床能力提高 |

“纯代码修复”和“需要新技术”并非穷尽且互斥的两类。代码可以**停止非法推断**，但未必自动找回正确规则；新的 schema 是表示改变，未必是新的模型技术；人工冻结术语映射能修已知别名，但不证明未见实体的泛化。每个缺陷应至少分列即时保护、必要信息、语义恢复方法、残余风险和验收标准。

静态代码、合成反例、历史病例轨迹、局部重放、正式新模型/新端到端实验具有不同证据强度。程序支持某种错误不表示它在本 11 例中实际触发；合成反例证明实现不符合所写合同，不证明该缺陷解释多少 MRR；旧指标下降不能否决正确的 bug fix，因为原错误可能偶然帮助 proxy。代码修复是否保持患者安全和诊断召回，必须同时测有效硬动作正例，不能用“全部规则拒绝”获得低错误率。

## 6. 复现与范围

运行 `python analysis/mechanism_v2/results/IMPLEMENTATION_DEFECT_AUDIT/build_prior_coverage.py` 可重建 15 条覆盖映射、5 条内部复用说明和 37 个精确代码/原文锚点，并核对六个冻结机械文件的接入标识。它按冻结 commit 读取已选文本 blob，拒绝把 LFS 指针当源内容；不读取大图或 LFS 对象，不调用 OpenRouter，不改生产文件。

本复核未给所有 KG 构建/导出/应用代码作完整缺陷审计；内部复用项只用于防止“全仓库从无此类能力”的错误结论。后续真正采用 KG 验证器时，应对被采用版本和适配语义另建迁移验收。
