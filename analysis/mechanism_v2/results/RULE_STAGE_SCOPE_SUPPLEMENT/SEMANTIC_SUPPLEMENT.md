# 阶段、意图、对象、适用范围与分支执行：语义补充合同 0.2

日期：2026-09-08。输入冻结于 `cursor4@bbc036e8a6ec93583be915a4609fe86278ed062c`。状态：**设计补充与有限合成验收，未改动生产算法，未运行新 LLM 抽取，未证明临床正确率或 MRR 提升**。文中所有 D、X、A/B 指标、年龄边界、处置及 JSON 示例均为合成逻辑夹具，不是医学建议或真实诊断标准。

## 1. 核对前提：已有原则，缺少可执行的类型合同

上一版并非完全没有这些概念。[SEMANTIC_CONTRACT](../RULE_EXTRACTION_EXECUTION_REDESIGN/SEMANTIC_CONTRACT.md) §1 已有 `applicability`、疾病/流程目标，§2、§6 已区分诊断动作与推断权限；[EXTRACTION_PROTOCOL](../RULE_EXTRACTION_EXECUTION_REDESIGN/EXTRACTION_PROTOCOL.md) §1 已要求识别诊断、建议检查、治疗、资格/路径；[MIGRATION_MAP](../RULE_EXTRACTION_EXECUTION_REDESIGN/MIGRATION_MAP.md) 已要求流程不能成为诊断票、年龄范围不适用不能排病。但是这些原则没有形成完整的**阶段 × 句子意图 × 结论对象 × 状态**类型矩阵，没有完整的分支集合、else/未知、覆盖/重叠和例外优先级合同。本文将其变为明确的字段、编译约束、路由规则与反例测试。

本次 11 例使用的机械管线仍主要依靠 `context_type`、原子 `relation`、`modality` 等混合字段；已有 `SOFT_CONTEXTS` 与原子软性过滤，因此并非所有阶段一律相同。[run_mechanical_engine.py](../RAG_GUIDELINE_ORACLE_CEILING_LOCAL/run_mechanical_engine.py) 的 `clamp_relation` 可把 `treatment` 等上下文标签或未识别关系变成 `feature_of`；criterion-group 根依据成员 `relation`/`modality` 推定必要性，还可由 `GROUP_ALL_IS_REQUIRED` 把 AND 变成必要条件。[gate_assertions.py](../RAG_GUIDELINE_ORACLE_CEILING_LOCAL/gate_assertions.py) 中 E10 治疗规则和 E4 检查过程规则只是特定模式的降级处理，并非端到端对象/意图合同。**已有软性防护不等于已解决设计缺口，也不能声称现行算法对所有阶段完全没有任何区分。**

还须区分仓库中的另一条 KG schema 路径。`src/agentclinic_tree_dx/knowledge/guideline_kg_schema.py` 已有 `population_context_ids`、保留时序/取样/部位的 `FeaturePattern`、递归 `LogicExpression` 和类型化概念。它不是本轮 11 例冻结机械执行器所消费的结构，因此不能据机械路径的缺陷声称仓库全局没有范围或组合逻辑；后续应复用其合格字段并补充动作语义/运行合同，而非另造互不兼容的第四套 schema。[冻结 KG schema](https://github.com/ytydt/Agentclinic-Tree-Dx-Spec/blob/bbc036e8a6ec93583be915a4609fe86278ed062c/src/agentclinic_tree_dx/knowledge/guideline_kg_schema.py)。

## 2. 不能只增加一个互斥的 stage 字段

一个段落可能同时描述诊断、检查和治疗；治疗反应也可能成为来源明示的诊断证据。章节标题不能独自决定规则用途。至少拆成以下相互独立的字段：

| 字段 | 语义与取值 | 编译时禁止的混淆 |
|---|---|---|
| `care_process_stages[]` | 筛查、诊断、检查、治疗、监测、随访、预防、康复等，可多值；记录来源锚点及未决状态 | 标为治疗即整段丢弃；标为诊断即所有原子都能确诊 |
| `semantic_intent` | `diagnostic_inference`、`recommend_action`、`action_eligibility`、`evidence_description`、`inference_permission` | 建议行为被编成已发生事实；描述关联被升为必要条件 |
| `target` | 类型化结论对象：疾病、检查、治疗、操作、流程、转诊服务或推断行为 | 所有主语都强行对齐疾病候选 |
| `effect.kind` | 对整个条件根的动作，例如确诊/排除、建议/不建议/禁止、资格判定、权限限制 | `mandatory` 自动变成疾病 `required_for` |
| `disease_context[]` 与状态 | 来源明确提及的疾病关联，可为空且标记 `not_mentioned`；不是隐含结论 | “建议查血常规”被迫补一个疾病主语 |
| `normative_strength` | 推荐/可考虑/必须等规范力度，仅约束所述动作；需原文证据 | 推荐力度变诊断似然、必要性或效力分数 |
| `applicability` | 人群、场景、时间、测量条件、已有疾病状态等适用范围 AST | 源文未写范围即盲目推断所有人；范围不符当反证 |
| `condition` | 在范围内决定结论的递归条件 AST | 条件为真就跳过范围，或把适用范围内蕴涵当患者证据 |
| `execution_state` / 事实状态 | 建议、医嘱、已实施、已完成、结果及其解释分别建模 | 已医嘱/已完成自动意味着阳性结果 |
| `branch_contract` | 分支身份、父范围、分支 guard、组合策略、覆盖声明、显式例外/优先级 | 默认 first-match、默认所有分支互斥、默认 else 吃掉未知 |

`care_process_stages` 是护理/诊疗流程分类，`semantic_intent` 是句子在做什么，`target` 是结论关于什么，`execution_state` 是患者事件发生到了哪一步。四者不能合并成一个枚举。`screening`、`diagnosis` 等名称也不能直接充当患者当下阶段事实；“本规则用于筛查”与“患者已完成筛查”来自不同层。

FHIR R5 将可定义的活动、希望或要求执行的活动、实际发生的事件分成 Definition、Request、Event，并允许它们相互引用；Request 的存在不保证以后一定实施。这可借鉴为状态分层，但本文的疾病逻辑权限是另外的合同，并不是 FHIR 资源本身提供的保证。[FHIR R5 Workflow](https://hl7.org/fhir/R5/workflow.html)。

### 2.1 结论对象可以没有疾病

以下三者不同：

1. “出现 C 时建议做 X”：`C → recommend(test X)`，目标是 X；来源没有疾病时 `disease_context=[]`，不能补成 `C→D`。
2. “为了检查 D，在 C 时建议做 X”：目标仍是 X；D 只是明确的检验目的，不能由目的推出患者已有 D。
3. “在适用人群中，X 的结果 R 足以建立 D”：目标才是 D；条件是带指标、方法、部位、时间与结果状态的 R。

若同一句独立给出检查建议和诊断条件，保留共同 `source_bundle_id`，生成两个独立的完整 Rule。各 Rule 根有自己的目标与动作；不能给共同原子挂上两个互相冲突的 relation，再让组执行器猜总效果。对真正必须原子地一起发布的多结论规则，可扩展为根部 `conclusions[]`，但必须分别做目标/权限检查并保留结论间依赖；本次夹具采用共享来源的多个根，不实现事务型多结论引擎。

## 3. 行为建议、状态、证据与疾病真值的隔离

| 来源语义 | 合法通道 | 可以输出 | 不可以输出 |
|---|---|---|---|
| 建议/必须实施检查 X | 工作流 | X 的建议及推荐力度 | D 确诊、D 排除、X 阳性 |
| 已开具 X 医嘱 | 患者事件 | `X.state=ordered` | X 已实施、完成或阳性 |
| 已完成 X、未报告结果 | 患者事件 | 完成事实，结果 UNKNOWN | 阳性结果或正常结果 |
| X 结果 R 支持 D | 诊断证据 | 来源许可的软证据/刚性动作 | 未观测 R 时借检查名称发出动作 |
| 治疗 T 的适用条件 C | 处置资格 | 在 C 下适用/建议 T | `接受 T → C`；`不适用 T → ¬D` |
| C 是 T 的禁忌 | 工作流安全 | 在 C 下禁止 T | C 排除 T 所治疗的疾病 |
| 不推荐用 X 排除 D | 推断权限 | 限定方法、对象、范围的排除禁令 | D 为真，或所有方法均不得排除 D |
| 治疗后真实观察 R 有诊断价值 | 诊断证据 | 经独立来源授权、时间/响应/混杂范围合格的 R 证据 | 任意治疗有效即倒推原病；无反应即排除 |
| 将 D 列为“拟诊、待证实” | 工作流/认识状态 | `propose_diagnosis(D)` | `confirm(D)` |

资格标准本身仍需保留必要/充分方向：`C→Eligible(T)` 在 C 假时不能判不适用；`Eligible(T)→C` 在 C 真时不能单独判适用。只有来源完整定义并授权 `Eligible(T)↔C` 时，才可按 C 真/假输出适用/不适用。JSON 因此分成 `eligibility_sufficient`、`eligibility_necessary`、`eligibility_complete_definition`，最后一种必须带 `complete_eligibility_basis_source_authorized=true`。工作流不是方向错误的豁免区。

“不推荐”不自动等于“禁止”，“资格不满足”也不自动等于“禁止”。应记录原文究竟规定 not-recommended、ineligible、contraindicated 还是 prohibited；不同推荐强度不能被统一映射为负刚性诊断关系。临床中接受某项治疗可能反映医生曾怀疑某病，这可以是单独研究的**决策过程证据**，但不是把治疗推荐规则反向执行的逻辑许可。若需使用，应建立独立来源、偏倚及混杂模型，不能在 extractor repair 中悄悄新增。

检查标准还必须区别“确立诊断的程序要求”和“疾病本体的必要条件”。“需活检才能按本指南确立诊断”可约束 `workflow establish_D`；没有活检时是确认资格未建立，而不是疾病不存在。来源若确实陈述疾病必须有某个组织学结果，应另建目标 D 的必要条件 Rule，并绑定**组织结果**，不绑定“曾做检查”。

因此诊断服务只消费合格的 `DiagnosticEvidence/DiagnosticAction`；`WorkflowProposal`、`EligibilityDecision`、`PermissionConstraint` 分路保存。未适用/未知/流程规则不得进入正支持 claimants、L4 定向扣分或强度归一化分母。治疗或检查文本不应默认被清洗成可计分 `feature_of`；真正跨阶段的诊断证据也不应一刀切删除。

ServiceRequest 在 FHIR 中表示服务请求，其结果可以体现在 Procedure、DiagnosticReport、Observation 等资源中，而不由请求本身承担结果事实。本仓可借鉴请求—实施—结果关联，但仍须自行核验实体、时序、取样和疾病效果。[FHIR R5 ServiceRequest](https://hl7.org/fhir/R5/servicerequest.html)。

## 4. 适用范围：真值与动作不能压成一个布尔数

令 G 为适用范围、C 为标准、D 为诊断。范围内的必要条件是：

```text
(G ∧ D) → C
```

不是：

```text
D → (G ∧ C)
```

反例 `G=FALSE, D=TRUE, C=FALSE`：前式仍成立，后式不成立。不能因为患者不是儿童便排除只在儿童部分给出的疾病。范围内充分条件是 `(G ∧ C) → D`。执行合同为先判 G，G 真时才把 C 的决定性结果交给效果引擎。

另一种危险实现是先求 `G→C`，结果为真便确认 D。G 为假时该蕴涵在二值语义下空真，即使 C 为假也会错误确诊；这不是 `(G∧C)→D` 的许可。**Rule 是带范围和效果的推断指令，不能把一个材料蕴涵公式为真当作疾病证据。**

| G | C | 必要条件 Rule | 充分条件 Rule |
|---|---|---|---|
| FALSE | 任意 | NOT_APPLICABLE，无诊断动作 | NOT_APPLICABLE，无诊断动作 |
| UNKNOWN | 任意 | DEFER_SCOPE，无诊断动作 | DEFER_SCOPE，无诊断动作 |
| TRUE | UNKNOWN | NEEDS_EVIDENCE，不排除 | NEEDS_EVIDENCE，不确认 |
| TRUE | FALSE | 源效力/事实/完整性通过后才可排除 | NOT_TRIGGERED，不排除 |
| TRUE | TRUE | 不单独确认 | 源效力/事实/完整性通过后才可确认 |

`NOT_APPLICABLE` 是规则执行状态，**不是疾病为 FALSE，也不是第五种患者真值**；`DEFER_SCOPE` 是范围未明，不能拿来排病。空 scope 与显式全域 TRUE 也不同：全域声明须经源审定，历史缺字段不能机械补 TRUE。本夹具保守地在范围未知时暂停动作；将来若所有可能且穷尽的适用分支都独立证明同一结论，可以设计带证明证书的 branch-consensus 推理，但须先证明分支覆盖、所有根权限和见证，并保留未知范围事实；不能伪装成 else 或默认年龄。本文未实现该扩展。

人口学之外，适用范围还应包含目标任务（疾病/病因/并发症/是否转诊）、患者/家属、急性/既往/治疗后时点、机构/环境、测量方法及已知基础疾病。范围可能引用此前已成立的诊断，但推理依赖图必须防止 `推测 D→适用治疗→确认 D` 自支撑环。家属患病不能激活患者已患病的资格分支，既往符合范围也不能默认当前仍适用。

## 5. 分支表达能力与执行语义是两个问题

嵌套 AND **单独**不具备一般布尔表达能力；AND/OR/NOT 完整时，有限、明确分支可以表达为布尔式。带个体量词及递归作用域仍可属于一阶逻辑；语法嵌套深不等于“高阶逻辑”。高阶逻辑涉及对谓词/关系/函数等量化，而不是仅多套一层括号。

若原文有儿童分支 G1、老年分支 G2，并分别给出充分标准 C1/C2，可表达 `((G1∧C1)∨(G2∧C2))→D`，无需新的逻辑阶。若是必要标准，应保存 `(G1∧D)→C1` 与 `(G2∧D)→C2`；不能未经穷尽性证明改成 `D→((G1∧C1)∨(G2∧C2))`，否则中间年龄未覆盖者会被误排。

因此“缺 scope 槽位”不一定是逻辑语言的绝对表达能力不足，却是严重的**提取、类型、审核、运行和错误处理缺陷**：显式 guard 能保存来源适用范围并阻止不适用被当作标准不满足。开放世界下的未知、时间事件、动作规范和来源例外也不会因为有嵌套 AND/OR 就被自动抽出或正确执行。可在更丰富的一阶多类型语言中编码许多关系，但还须明确编码的语义与运行合同；不能把布尔表达能力当作临床流程已建模。

### 5.1 BranchSet 合同

每个 `BranchSet` 保存 `parent_scope`、来源同一性与完整性、分支列表和组合策略。每个分支有稳定 ID、guard、根 Rule 引用与自己的源锚点；有效范围为 `parent_scope ∧ branch.guard ∧ rule.applicability`，**先用完整有效范围路由**，不能先按 branch.guard 选中高优先分支，再发现其根不适用而把有效低优先分支吞掉。BranchSet 的结构完整性、分类审定、每个 guard 的审定和根范围来源授权都须通过；根已审核不等于分支也已审核。共享原子可以被引用，但不会移除分支成员或合并动作。

| 策略 | 用途 | 必须验证 |
|---|---|---|
| `exclusive` | 来源规定恰选一条或至多一条 | guard 是否互斥；覆盖声明是真正全域还是仅来源分区；多个 TRUE 报 BRANCH_CONFLICT；未知不当 FALSE |
| `all_applicable` | 同时适用的独立建议或规则 | 所有 TRUE 分支保留；UNKNOWN 分支挂起；根动作冲突另行解析；不同分支不自动互斥 |
| `source_priority` | 来源明确规定例外、覆盖或先后选择 | 优先级源证据、影响的目标/动作/范围；高优先分支 UNKNOWN 时不能直接执行可能被覆盖的低优先分支 |
| `explicit_else` | 来源明确“否则”，保存独立已审 `else_guard` 及其否定的源条件范围 | 源文所指的前置条件已知 FALSE，且 else 自身范围为 TRUE；未知不进入 else；不可自动对 root 额外范围取补集 |

互斥性与覆盖性是独立维度：`at_most_one` 可以合法地没有适用分支；`exactly_one` 且来源已审穷尽时，如果全部有效 guard 已知 FALSE，应报 `COVERAGE_CONFLICT`，检查原文范围、边界或事实，而非静默继续。`source_priority` 还须保存来源声明的分支 ID 顺序与 `override_domain`，限定它覆盖的目标/动作/范围；存储数组重排不应改变优先级。当前夹具仅模拟同一已审疾病目标内的 diagnostic-decision 优先域，不实现任意跨对象覆盖 DAG。

不要给所有来源默认 `first_match`。年轻与老年条件若重叠、指南阈值边界不清，先保留为歧义，不由数组顺序决定诊断。例外不能凭“更具体的规则看起来应优先”自动授权；source-priority 只是记录原文规定或独立审定的版本/冲突政策。不同年代指南、不同机构规则冲突，仍可能无法确定，应输出争议而非规则数投票。

年龄例子中的 `<12` 与 `≥70` 刻意留下未覆盖区间；这不是一般医学年龄分组。源文只覆盖两个范围时，对 12–69.999 的患者应报告无适用分支，不能补出成人标准。若源文真的给出“其余年龄”，才增加 explicit-else。检查阈值端点开闭、年龄参照时点、年龄单位和不确定年龄区间；“约 12 岁”跨边界时保留未知。有限夹具只检验已给的年数和缺失值，不实现日期年龄计算或区间患者输入。

**else 的否定范围必须来自原文。** “儿童……否则……”通常对年龄条件取补集；若儿童规则另外仅适用于住院场景，儿童不在住院场景不应因此变成成人 else。JSON 保存独立已审 `else_guard`；执行器将它与父范围和 else 根自身范围组合，不自动计算 `NOT OR(branch.guard AND root.applicability)`。当前夹具仅支持明确来源的 exclusive-else；更一般的工作流 else、优先链和覆盖 DAG 需要另行规格。

FHIR PlanDefinition 把活动条件区分为 applicability、start、stop，并独立保存动作的选择行为和相互关系。这支持将范围、启动/停止和动作依赖分开；它不意味着自然语言的例外已经被自动识别，也不强制使用本文的三值分支策略。[FHIR R5 PlanDefinition](https://hl7.org/fhir/R5/plandefinition-definitions.html)。

### 5.2 未知不能随编译后端改变

上一合同使用 Strong Kleene 三值。任意转成 Python `if value:` 会把 `None` 送进 else；不同 CQL 算子也有各自 null 规则。CQL `if` 的 null 条件按否则分支处理，而二元布尔逻辑另有三值表。因此导出时应先生成 `guard is true`、`guard is false`、`else deferred` 的显式路由，不直接用后端默认 if/else 代替本文合同。CNF/DNF 或经典求解器的等价证书须绑定逻辑 profile，不能把二值等价当未知输入下的运行等价。[CQL 2.0.0 conditional expressions](https://cql.hl7.org/03-developersguide.html#conditional-expressions)。

## 6. 抽取器、编译器、执行器的具体增补

### 6.1 来源清单与抽取槽位

先固定源规则清单，再抽取，不允许以模型已输出项定义分母。每个源单元记录：章节用途提示、句子发言功能、条件/例外/人群跨度、动作词与否定归属、动作对象、是否真的声明疾病结论、时间/状态、来源是否有明确的原子或多结论、未决解释。

抽取必须给每个关键槽位附源跨度；章节标题可以辅助，不能覆盖句子。必要时提出两个候选解释并标未决，例如“必须检查 X”究竟表示治疗前安全筛查、建立诊断程序，还是目标病的必要阳性结果。没有源证据的 disease target 不得被候选诊断列表补齐。检验目的与疾病背景允许 `not_mentioned`；“未提及”不是 JSON 缺字段的错误，也不是模型虚构目标的理由。

建议的四步是：①源结构/发言功能清单；②类型化对象、谓词论元、阶段/状态、guard 和 action 草图；③受类型/作用域约束编译；④独立源对齐与反例检查。关键反例包括同一检查从推荐变已完成再变阳性、同一条件从患者改家属、治疗成功但来源只给治疗指征、年龄落在另一分支或未覆盖区间。反例应由源规则及合同生成，不能用当前金标排名裁决语义。

FHIR CPG 的实施方法将概念、适用条件、推荐动作及其翻译分阶段，并要求边界/正负场景和专业审查。本文借鉴其知识工程流程；不把规范型数据结构误称为自动忠实提取技术。[CPG Methodology](https://www.hl7.org/fhir/uv/cpg/methodology.html)。

### 6.2 编译拒绝与可保留的不确定性

- `diagnostic_inference` 必须有已解析 disease target、诊断 effect、来源授权及完整 guard；`recommend_action` 不得用 `sufficient_for_target` 冒充建议。
- 检查/治疗/工作流 target 不能进入疾病 candidate binder；需要疾病背景检索时使用单独的 `disease_context` 边，不把它当结论。
- 根动作与 target 类型不符、行为 recommendation 被用作 observation、目标疾病未解析、原文的群体/例外缺失：拒绝产生可执行诊断 Rule，保留原始输出与错误原因。
- 阶段多值本身不是错误。某规则阶段为治疗/诊断、意图为诊断、条件为明确响应 observation 时可编译；仍需独立的诊断效力来源，不能从治疗指征倒推。
- 分支互斥/覆盖无法证明时保留 uncertain；不能无条件改为 all_applicable、补 else 或丢掉例外。
- 历史无字段记录统一进入 `legacy_unreviewed`，不补全域 TRUE、不根据已输出 relation 默认 diagnostic、不根据章节标题默认 treatment。一部分高精度明确模式可先人工审查后迁移；不安全模式保持待核验。

### 6.3 运行协议与证明账本

输出 `RuleExecutionRecord` 至少含：规则/源/IR 版本、分类审核、阶段标签、target/action 类型、scope 求值和见证、分支集合/选择/未决、condition 根结果、事件状态、已采用与未采用的证据、触发或拒绝理由、目标通道。

当 all-applicable 分支产生同一目标的相反有效效果，保留两条证明并建立 `ACTION_CONFLICT`；禁止以分支数量或读取次序消解。夹具只识别同一显式目标的 CONFIRM/EXCLUDE、PROPOSE/PROHIBIT、ELIGIBLE/NOT_ELIGIBLE 三类相反动作，阻止它们进入 `admitted_actions`；并不实现任意医学冲突、语义同义目标匹配或完整工作流调度。真值与证据冲突仍独立：`{"value": true, "conflict": true}` 可以保留根 TRUE，同时使动作挂起。非布尔状态缺失用 null，保留字 UNKNOWN 也统一为未知；不能因为它不是字面 positive 就解释为明确阴性。

推荐管线为：源谱系核验 → 类型化编译 → 事实及动作/结果状态编译 → 范围与分支路由 → 根条件求值 → 效力/权限 → 诊断证据或工作流通道。若共享原子求值缓存，缓存键必须含主体、时点、取样/指标、guard 依赖与版本，不能把儿童正常范围结果供老年分支复用。分支动作不会改写原始事实；建议检查不能回写 `test_positive=true`。

规则间依赖应显式建图：资格可依赖既有诊断状态，但新诊断结论不能只以同一条规则产生的建议为见证形成环。启用流程执行需另外的动作确认与系统权限，本设计只是计算推荐，**不实际发出医嘱或执行治疗**。

## 7. 与原 redesign 的兼容及交付边界

| 原接口 | 补充内容 | 最小兼容措施 |
|---|---|---|
| Rule.target/effect | 目标与动作的 discriminated union；目标可非疾病 | 诊断 binder 只接受明确疾病结论；其余进入独立 ledger |
| Rule.applicability | scope 真值与执行状态；源范围是否完整 | 缺值不补 TRUE；FALSE/UNKNOWN 不产生诊断反证 |
| condition AST | 保留 guard 与 condition 的功能角色 | 不求 `G→C` 然后拿空真触发 D |
| extraction protocol | 阶段多值、句子意图、事件状态、疾病背景缺省政策 | 旧 schema 未存的信息回源提取或标未审 |
| group/root action | BranchSet + 根 Rule 引用 | 别名/原子共享不会删成员或拼接不同根动作 |
| EvidenceLedger | 工作流/资格/权限与诊断通道 | 流程不进入 claimants、L4 或诊断排序分母 |
| verifier/acceptance | 状态翻转、范围反例、覆盖/重叠/else、例外未知 | 语法通过不能代替源文核验；冻结新源样本评估 |

纯代码能够可靠实现字段约束、类型校验、状态隔离、未知路由、重复引用和准入规则。**从旧扁平行恢复遗失的人群、动作意图、检验结果和例外范围，则通常不能仅改几个 if 来完成**：需回源、结构化提取、术语/事件模型、独立审核及必要的 LLM 或人工语义判断。新技术不一定意味着换模型；可靠的受控语言中间层、类型化编译器和来源反例审查也属于可分阶段验证的方案。

## 8. 实证验证建议：不是多加几个字段便算完成

本补充至少增设五类源抽取终点：阶段/意图混淆率、动作对象准确率（含正确的“无疾病目标”）、推荐/实施/结果状态混淆率、guard/例外完整召回率、分支覆盖与运行一致率。source 单位仍分别计算忠实/曲解/遗漏，output 单位单列无可追溯来源幻觉；不可用丢弃所有流程或所有复杂分支获得虚假的低错率。

离线固定原始抽取的纯结构修补，与回源重抽分开试验；分别对比：原实现、增加字段但不路由、类型与阶段路由、再加 scope/branch 合同。保持候选、源窗和事实固定后先看规则级转化与误动作；加入真实事实抽取后再看端到端。对“治疗阶段但确有诊断价值”的保留组和“检查意图无疾病主语”的组单列召回，不可只报告拒绝成功。任何 rank 增益仍同时报告完整疾病/组件/父类标签，并检查真正可共存疾病，不能以假定候选互斥决定排除正确性。

病例 522 的 B12 检查菜单、773 的检查非指征与疾病排除、74 的治疗/时序与诊断条件转移均可作开发回归，但不能用它们作为新的确认样本。阶段/范围审定先盲于金标与 arm 排名，随后再追踪诊断贡献变化。[逐例差量审计](../V2_INDEX_DIFFERENTIAL_AUDIT/REPORT.md)。

## 9. 本目录夹具能证明和不能证明什么

`supplemental_examples.json` 保存合成 Rule/BranchSet 和语义元数据；`supplemental_vectors.json` 保存人工规定的输入与期望结果；`validate_supplement.py` 验证形状、目标/效果类型及有限三值例子，并写 `supplement_validation.json`。当前包含 **24 个合成 Rule、10 个 BranchSet、116 个有限向量**。它覆盖：检查建议/医嘱/实施/阳性差异，治疗资格与禁忌方向，跨阶段合法诊断证据，拟诊与确诊，scope FALSE/UNKNOWN，条件必要性与错误公式的反例，材料蕴涵空真陷阱，分支年龄边界/缺口/重叠/未知/显式 else/来源优先级。

权限夹具只验证将元规则路由为权限对象；它**不实现跨规则的方法/目标/scope 匹配及权限禁令消费**，不能用 `LIMIT_EXCLUSION_METHOD` 输出声称真实排除动作已被权限引擎拦截。

验证器不进行源文→IR 抽取、不运行现行 11 例、不实现完整医学术语服务、年龄日期计算、任意 FOL 证明、动作调度、多结论事务或真实医嘱。例子所有 `clinical_use_authorized=false`；其中允许的硬效果只在 `fixture_effect_authorized` 下模拟。**通过表示这些有限夹具与本文合同自洽；不证明指南保真、医学效力、实际错误率或生产安全。**
