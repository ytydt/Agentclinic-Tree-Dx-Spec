# 阶段与适用范围补充：独立语义及反例复核

日期：2026-09-08。基线 `cursor4@bbc036e8a6ec93583be915a4609fe86278ed062c`。复核对象是本轮新设计与有限合成检查器，**不是已经部署的生产算法**。本文件由独立审阅者编写，未改写作者的合同、夹具或生产代码；发现的问题先回传作者修订，再独立复查。

**最终状态：本次提出的八项具体夹具问题均已关闭。24 个合成 Rule、10 个 BranchSet 的 116 个作者向量复跑通过；另有 123 项独立检查全部通过。** 当前没有保留的合同范围内阻塞项，但下文列出的未实现能力仍然未被验证。计数是有限检查数，不是正确抽取率或临床准确率。

## 1. 复核问题与边界

本次不以“新增字段存在”作为通过依据，而检查字段是否确实限制动作：检查建议不能转成检验阳性，治疗资格不能倒推病因，范围为假不能排除疾病，未知不能进入默认 else，未审核分支不能借已审核规则根发出硬动作，重叠规则不能以数量或数组顺序掩盖冲突。

采用三层证据：与旧语义合同逐项对读；核验所引用的 FHIR/CQL 官方规范；对有限检查器另造反例并枚举有限真值组合。作者向量复跑与独立反例分别计数。即使全部通过，也只说明这些输入下的合同一致性，不证明任何实际指南被忠实抽取、临床诊断有效、源规则审核标志可信或下游排名提高。

## 2. 已核验的核心逻辑

| 问题 | 独立判断 | 为什么 |
|---|---|---|
| 旧 redesign 是否完全没有 stage/scope 思路 | 不是 | 旧 `SEMANTIC_CONTRACT` 已有 applicability、流程对象、诊断权限；本轮补齐的是可执行类型与分支政策，不宜将既有原则叙述为全新发现 |
| 范围内必要条件 | `(G ∧ D) → C` 正确 | `D → (G ∧ C)` 会在不属于 G 时错误约束疾病 D；二值反例 G=FALSE、D=TRUE、C=FALSE 足以区分 |
| 范围内充分条件 | `(G ∧ C) → D` 的规则动作需先有 G/C 的适用见证 | 不能将 `G→C` 的空真当作患者 D 的证据 |
| 范围未知时暂停 | 是本合同的保守动作政策 | 不是声称任意可能世界推理都必须暂停；若穷尽分支全部证明同一动作，另可研究带证书的 branch consensus，当前未实现 |
| 只有嵌套 AND 是否足够 | 不足 | AND/OR/NOT 可表达有限布尔分支；个体量词嵌套仍可是一阶，语法括号深度不等于高阶逻辑 |
| 拟诊、建议检查、实际观察、确诊 | 应分层 | 行为/认识状态与疾病真值并非同一断言；无疾病目标的检查推荐是合法规则 |
| 流程阶段与语义意图是否可合成一列 | 不可 | 治疗响应可能有独立来源授权的诊断价值；把治疗段落全部删除与全部保留计分都不正确 |
| 必要/充分及资格方向 | 必须逐效果授权 | `C→eligible` 并不许可 `¬C→¬eligible`；工作流语义也不能例外地使用错误逆向推理 |

## 3. 官方来源复核

以下是对标准内容的核验，不将这些标准当作自动文本忠实性技术。所有页面于 2026-09-08 查阅；本轮没有运行 FHIR 服务、CQL 引擎或外部临床系统。

| 官方来源 | 本轮核验内容 | 不可外推的保证 |
|---|---|---|
| [FHIR R5 Workflow](https://hl7.org/fhir/R5/workflow.html) | requests、events、definitions 是不同活动表示；请求的存在不保证未来实施；它们不是严格 1:1 对应 | 此模型不自动证明指南→Rule 的语义准确，也不规定本补充的疾病动作权限 |
| [FHIR R5 ServiceRequest](https://hl7.org/fhir/R5/servicerequest.html) | 服务请求与 Procedure、DiagnosticReport、Observation 等事件/结果资源分开，并可关联 | 不能由检查请求或完成状态推导检验值；资源对接仍需指标、对象和时序核验 |
| [FHIR R5 PlanDefinition](https://hl7.org/fhir/R5/plandefinition-definitions.html) | action 条件区分 applicability/start/stop；selectionBehavior 与 requiredBehavior 独立 | 规范的缺省 selectionBehavior 可为 all；不能把这类后端缺省直接当成本合同的源文授权 |
| [CQL 2.0.0 conditional expressions](https://cql.hl7.org/03-developersguide.html#conditional-expressions) | if 与标准 case 的 null 条件不会命中 true 分支；else 因而可被选中 | CQL 的合法表达式不自动满足“未知必须挂起”的本合同；需显式 true/false/defer 路由 |
| [FHIR CPG 2.0.0 Methodology](https://www.hl7.org/fhir/uv/cpg/methodology.html) | 推荐内容经选择、表示、翻译、验证，并包括领域专家审查、正负及边界场景 | 这是知识工程与验证方法；不等于 LLM 已能自动恢复正确动作、范围与例外 |

另一个后端适配提醒：CQL 2.0.0 的参数 `@constraint` 在结果为 null 时可视为约束满足。若将“已获硬效力许可”等门写成一般约束，也必须明确要求 `is true`，不能依赖此默认行为。[CQL Developer's Guide](https://cql.hl7.org/03-developersguide.html)。这与 CQL 的 if/else null 处理是两个独立的接口风险，不应混称为 CQL “没有三值逻辑”。

## 4. 独立反例发现与关闭记录

审阅初版及中间版检查器时，通过源码检查及独立输入发现下列问题。它们属于新补充夹具的审阅反馈，**不能伪称为对旧生产算法的新实测错误或临床损害**。[历史反例快照](review_initial_counterexamples.json) 保存两个检查器哈希及四个实际重现结果（SR01–SR03、SR08）；其他行是静态语义发现与修订后的定向验证。不是声称每行都在旧版本完整运行过反事实实验。

| 编号 | 初版反例及结果 | 要求的处理 | 最终状态 |
|---|---|---|---|
| SR01 | 非布尔结果槽 `X.result='UNKNOWN'` 被 eq 判为 FALSE，必要条件发出 EXCLUDE | 未知标记统一处理；错类型拒绝，不作为阴性 | 已修订，独立 UNKNOWN/None/错类型反例通过 |
| SR02 | `run_branch` 直接消费未经审核且未获优先级许可的 BranchSet，仍执行已审核根并 EXCLUDE | 入口校验、分支来源/分类/guard 审核及根范围准入 | 已修订，直接 runtime 无授权拒绝、未审及缺源分支无动作 |
| SR03 | `eligible_when` 无完整定义/必要性许可时，以条件 FALSE 输出 NOT_ELIGIBLE | 分成充分、必要、完整资格定义；最后一种要求完整来源授权 | 已修订，三效果×三真值九项独立向量及缺 iff 授权拒绝通过 |
| SR04 | 多个已触发根可能同时给同一目标 CONFIRM 与 EXCLUDE | 独立动作冲突账本及终态门，保留两条证明 | 已修订，同目标相反动作被阻断；不同目标不被假设互斥 |
| SR05 | exclusive 将恰一/至多一及覆盖状态混合；source_priority 只依赖数组顺序 | 显式覆盖/基数声明与来源顺序/授权域 | 已修订，恰一覆盖矛盾可见；数组重排不改授权顺序，跨目标覆盖被拒绝 |
| SR06 | 只看 branch.guard 先选优先分支，再发现其 root 不适用，可能吞掉有效低优先分支 | 选择前使用 parent∧guard∧root.applicability | 已修订，高优先 root 范围假允许低优先；高优先范围未知挂起 |
| SR07 | effect 许可仅在诊断通道检查，且字符串 `"false"` 可凭 truthiness 变成许可 | 所有通道均检查效果许可，字段严格 Boolean | 已修订，推荐/禁令/资格/权限无授权均无动作；字符串、数字、null 许可被拒绝 |
| SR08 | 将 else 自动取为完整有效 scope 的补集，会把“儿童分支的机构范围不符”误作“不是儿童” | 保存原文 else_guard 的来源/作用域，不由额外 root 范围重写 | 已修订，儿童机构范围不符不进入成人 else，年龄未知不走 else，缺少源 else_guard 拒绝 |

SR08 尤其说明：**把 scope 正确放到优先级路由之前，仍不能自动确定 else 究竟否定哪一层 scope。** 本轮中间版的年龄为 10、额外 hospital_scope 为 FALSE 的合成儿童，曾被错误送入 ELSE 并确认 D。必须回到原文保存“否则”绑定的 guard；此问题无法由“已有 AND/OR 嵌套”或一个覆盖授权布尔数自动解决。这里的疾病和年龄都不是医学标准。

## 5. 独立验收与保留边界

独立脚本 [review_checks.py](review_checks.py) 另造输入，验证完整三值 scope×condition 的诊断动作矩阵；未授权及未审输入的阻断；目标/意图错配；允许无疾病目标的流程；检查请求/完成/结果状态；父范围为假/未知；分支空隙/else；高优先级未知；同目标动作冲突；核心必要条件公式的反例。它没有把作者向量再次计入自己的检查分母。事实及断言均为合成，非医学实体。

最终 [review_checks.json](review_checks.json) 为 **123/123 passed**，保存被复核代码、源合同及两个输入 JSON 的 SHA-256；[作者验收](supplement_validation.json) 为 **116/116 passed**。两套分母独立列出，不能当作 239 个独立临床样本。SR01–SR08 的关闭仅针对所列具体风险；不表示对任意输入已完成穷尽验证。

复现：

```bash
python analysis/mechanism_v2/results/RULE_STAGE_SCOPE_SUPPLEMENT/validate_supplement.py
python analysis/mechanism_v2/results/RULE_STAGE_SCOPE_SUPPLEMENT/review_checks.py
```

以下边界保留且不应被“向量全通过”掩盖：

- `reviewed_fixture`、范围完整与来源许可是人工给定的夹具元数据；检查器不证明这些标志与实际指南一致。
- 检查器没有医学术语链接、病例事实提取、量纲系统、日期年龄计算、任意 FOL 证明或新旧 11 例排名重跑。
- 冲突检测仅覆盖同一显式目标的有限相反动作类型，不实现语义同义目标匹配、临床疾病共存判定或任意工作流冲突。
- `LIMIT_EXCLUSION_METHOD` 仅是权限对象路由输出；检查器没有执行跨规则的方法/目标/范围权限匹配与消费。不能声称真实排除已被权限引擎截获。
- 有效分支在本夹具中采用保守的来源/分类审核门。允许病历事实 unknown，不代表允许缺失原文例外或未审核 guard 被悄悄忽略。
- 这里的 WorkflowProposal 不是实际医嘱执行；FHIR/CQL 引用是设计借鉴，未生成或验证可部署后端。
