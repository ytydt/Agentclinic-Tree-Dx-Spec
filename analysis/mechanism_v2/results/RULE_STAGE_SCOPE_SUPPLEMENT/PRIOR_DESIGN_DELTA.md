# 阶段与适用范围补充版：相对于上一版真正新增什么

基准：`cursor4@bbc036e8a6ec93583be915a4609fe86278ed062c`。本文件区分既有要求、遗留实现以及本轮需要补齐的行为合同。详细锚点见 [既有覆盖复核](../IMPLEMENTATION_DEFECT_AUDIT/PRIOR_COVERAGE_REVIEW.md) 和 [机器映射](../IMPLEMENTATION_DEFECT_AUDIT/prior_coverage_map.json)。

## 1. 不能沿用的两个前提

**“原 redesign 完全没考虑阶段/适用范围”不成立。** 原 `RULE_EXTRACTION_EXECUTION_REDESIGN/REPORT.md` 动作表已把检查/治疗/工作流从疾病真值分开，`EXTRACTION_PROTOCOL.md` 要求识别用途、人群、人物、部位、时间和工作流分支，`SEMANTIC_CONTRACT.md` 的字段表已有独立 `applicability`，硬动作门要求其为 TRUE。M05、M14、M18、M19 也分别约束决策类型、事件、scope 和准入。本轮补充的是完整 schema、分派/消费规则、分支政策及验收，而不是第一次提出这些原则。

**“旧实现完全没有任何阶段近似字段”也不成立。** 遗留抽取器有 `context_type=treatment/prognosis/epidemiology` 和 `treated_by`，原子硬动作有 soft-context guard。其真正不足在于 source context 混合文本布局、证据模态和用途；建议检查没有独立动作类型，流程/患者事实/检验结果没有完整状态区分；保护未统一传至 groups、claimants、L4 及排序。由此应建立贯穿全链的用途/效果合同，不能只增加一个 `stage` 字符串。

## 2. 新增合同空间

| 维度 | 原提案已有 | 本轮补充必须明确 |
|---|---|---|
| 规则用途 | 诊断、分类、评分、建议检查、治疗、资格/路径等分类原则 | 临床活动、知识断言、推荐/禁止动作与消费者权限是独立维度；同章节/同检查可承担不同用途 |
| 动作目标 | Rule target 可为疾病/流程对象 | 无疾病主语的检查/治疗建议如何表示；不能将操作对象硬塞进 disease candidate |
| 模态 | 必要/充分/排除、弱证据和推断权限已分离 | 推荐强度/行动义务、事实确定性、诊断逻辑必要性不能互换；“must test”不是“test finding necessary for disease” |
| 患者事件 | 检查已做不等于结果阳性 | 推荐、下单、采样/执行、观察结果、解释结果及治疗反应的可接受证据链 |
| 适用性 | 独立 applicability、TRUE 才能发硬动作 | scope 的来源/继承、缺省与未知、年龄/时间边界、目标关联，以及不适用的退出状态 |
| 分支 | 递归表达式和整体工作流分支 | branch guards、互斥/穷尽声明、重叠处理、多规则并行、显式优先级、else 的源许可与未知 guard 处理 |
| 验收 | 有限合成 IR、范围不符不发硬动作 | 每个用途×动作×真值×适用性组合；错误范围不应排病，合法治疗反应证据不应被一概丢弃 |
| 兼容 | 无法无损迁移留未审核/unsupported | legacy context 到新类型只能映射确定子集；其他由源文恢复，不能默认 stage=diagnosis、scope=all |

## 3. 表达能力与执行语义：分支不只是“再加 AND”

在经典逻辑里，具备 NOT/OR/AND 及合适原子条件的表达式可以表示有限命题分支；只有反复嵌套 AND 本身并不逻辑完备，FOL 还涉及变量和量词，而规则动作/推荐/优先级又不等同于疾病真值公式。结构可表示并不意味着提取忠实、适用范围可求值或执行动作已受约束。

设 `A` 表示适用人群，`D` 为疾病，`C` 为该人群下必要标准。正确局部必要性是：

\[
(A \land D) \rightarrow C.
\]

不能把 A 填进必要条件根后变成 `D → (A ∧ C)`；后一式会因“不是该人群”而排除疾病。举例用纯合成语义：成人规则只约束成人，儿童不满足 adult guard 是规则不适用，而不是疾病被否定。只有在 A 已确定成立、C 是合格的明确反例、必要性及来源权限均合格时，才能申请对 D 的排除动作。

充分规则 `(A ∧ C) → D` 在纯真值层可以将适用性放进前件，但运行时仍应区分 **A 不适用、A 未知、C 失败、C 未知**，因为下一步是补年龄/改用其他分支/补检查等不同动作，审核的来源和覆盖分母也不同。把它们全部压成“不确认”虽可能碰巧保持一个疾病动作，却会丢失可解释性和流程信息。

`if child then C_child else C_adult` 必须有源文依据证明 else 等于成人，且 child guard 可判定。年龄未记录时不能执行成人 else；也不能把 `not known child` 当作 `known not child`。若成年、老年、妊娠等范围重叠，则多条标准可能并行适用。缺少原文优先级时不能任意 first-hit；应保留多个适用规则及其冲突，或者明确需要审核。

历史主设计已经声明 Strong Kleene 三值语义。经典二值恒等变换、CNF/DNF 化简或 solver 的等价结论不能不经验证就替换三值执行；也不能因原文标准表达式可以转成公式，就删掉其人群、版本、规范动作和来源权限。

## 4. 已有内部资源的继承边界

独立 KG schema 已具有 `population_context_ids`、递归 `LogicExpression`、typed FeaturePattern 和 ConceptMapping；这些能复用为结构校验和术语/来源接口。它没有因此实现本实验所需的 applicability 求值、branch policy、clinical action dispatcher 或完整诊断硬许可。机械实验的六个核心 runtime 文件没有引用这些类型/许可标识。

因此补充版可以继承内部 KG 的引用/循环/类型检查，同时需要新合同适配层；不应另造一个同名但语义不兼容的 `LogicExpression` 后静默互换。Graph-valid、source-faithful、patient-applicable、action-authorized 是四个不同状态。

本补充文件是覆盖和概念边界审查。阶段/范围的完整规范、实现范例、有限向量和迁移建议以本目录其他主交付文件为准；通过合成向量不代表已自动恢复任何真实指南的用途或分支。
