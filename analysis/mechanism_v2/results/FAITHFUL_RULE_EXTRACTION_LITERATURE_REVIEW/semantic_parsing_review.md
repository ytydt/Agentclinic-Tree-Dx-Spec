# 受控语言、组合语义与约束生成：忠实提取的保证究竟止于何处

审阅日期：2026-09-05。本文是第二任务中经典语义解析与形式约束路线的独立分报告；不替代临床指南研究或近期 LLM 文献分报告，也不提出第三任务的实施方案。纳入 8 项原始系统/研究及 1 组正规形官方资料；检索与读取范围见 `semantic_parsing_search_log.json`，逐项出处、代码可得性及限制见 `semantic_parsing_sources.json`。本轮只审读文献与官方代码，没有运行这些系统，不能把其论文成绩当成本仓库复现成绩。

## 1. 结论：可以保证形式约束，不能由此保证原文解释

本组研究提供三种不同的保证。ACE 给被接受的**受控语言**规定解释；PICARD、Synchromesh 和类型约束生成限制输出满足特定语法、绑定或类型约束；Sketch 的验证器检查程序满足**已给定的形式规格**。三者都没有证明任意临床散文经过自动转换后，原作者所指的连词、量词域、否定及诊断方向会全部正确。此处“没有证明”限于审读材料，不能扩张为整个领域的不可能性结论。[ACE 解释规则](https://attempto.ifi.uzh.ch/site/docs/ace_interpretationrules.html)；[PICARD §2](https://aclanthology.org/2021.emnlp-main.779.pdf)；[Synchromesh §3–4](https://arxiv.org/pdf/2201.11227)；[Sketch §3–5](https://people.csail.mit.edu/asolar/papers/asplos06-final.pdf)。

| 保证所在的边界 | 文献中的对象 | 仍然可以发生的错误 |
|---|---|---|
| 受控句子 → 规定的意义 | ACE 的词法、组合与作用域规则 | 将原指南改写为 ACE 时已把必要条件写成充分条件 |
| 输出前缀 → 合法的完整形式 | PICARD 的解析/作用域守卫；Synchromesh 的 completion engine | 一个合法公式使用了错误连词或错误结论方向 |
| 表达式 → 类型正确的程序 | 类型环境与可完成前缀 | 同类型参数交换、数值绑定到错误但同类型的指标 |
| 候选实现 → 满足形式规格 | Sketch 的有限域合成—验证循环 | 规格和实现忠实地共享同一个源文误读 |
| 文本 → 人工核验的语义表示 | PMB 的可追溯人工纠正 | 自动输出尚未核验；人工审定也不等于临床适用性已证实 |

以上最后一列是本次分析的迁移推断，而非原论文针对本仓库报告的实验结果。其共同含义是：**合法性、参考形式的等价性、来源保真度、临床适用性是不同终点**。Boxer 尤其明确地区分了能生成表示的覆盖率和没有金标准时无法测出的语义质量。[Boxer §5](https://aclanthology.org/W08-2222.pdf)。

## 2. 受控自然语言：用规定消除歧义，把剩余责任显式留给改写者

**SP01，ACE / APE。** ACE 不靠模型自行猜测每句话的组合规则：官方规范给出连词结合优先级、局部与全局量词范围、协调结构中的条件句作用域和照应可达性。其 DRS 表示允许条件内部再嵌套 DRS，并给原子条件保留句号/词号锚点；APE 可输出释义、DRS 以及支持范围内的 FOL/PNF/TPTP。[解释规则的 Coordination、Quantifiers、Anaphora Resolution](https://attempto.ifi.uzh.ch/site/docs/ace_interpretationrules.html)；[ACE 6.7 报告 §2.4.8、§2.5](https://attempto.ifi.uzh.ch/site/pubs/papers/drs_report_67.pdf)；[APE 参数接口](https://github.com/Attempto/APE)。

这是一条“人或上游过程先采用受控表达，再解析”的路线。固定 `and` 与 `or` 的优先级能够消除 ACE 内部歧义，却不能证明这种优先级就是任意医学原文的作者意图。APE 释义适合供人比较解释差异，文献接口本身没有赋予自动 round-trip 一个保真度定理。ACE 还区分经典否定、negation as failure 与模态扩展；不能将整个语言的扩展 DRS 都无条件称为普通 FOL。[ACE 6.7 §2.4.1–2.4.7](https://attempto.ifi.uzh.ch/site/pubs/papers/drs_report_67.pdf)。

可借鉴的是把“解释约定”和“原文是否适合该约定”分开审查，而不是直接把自由散文装进一个合法 JSON。量词词面出现并不自动解决量词域：集合成员、患者、时间点还是检查结果，仍须在源文改写时明确。

## 3. 组合语义：保留绑定与作用域，也允许暂时不裁定歧义

**SP02，MRS / RMRS。** MRS 的关键并非“树比表好”，而是作用域不能在序列化时消失。它以 elementary predications、handles、量词的限制域与主体及作用域约束保存结构。论文 §2 展示去掉作用域后相同谓词集合可对应不同意义；§3 进一步允许保留多个兼容的量词读取。官方 ERG 文档明确指出，语法常只能确定部分作用域，且广义量词包括不能直接当作普通 `forall`/`exists` 的表达。[MRS §2–3](https://www.cl.cam.ac.uk/~aac10/papers/mrs.pdf)；[ERG Quantification](https://delph-in.github.io/docs/erg/ErgSemantics_Quantification/)。

因此，**扁平存储并非天然错误，丢失绑定、角色和作用域的扁平存储才错误**。带 handles 的图可以表达组合结构；把原子排成列表并赋各自 relation，却不给组的布尔语义和结论，不能获得同样的性质。RMRS 也指出特征结构类型体系并不自动强制整个语义代数，仍需要额外检查。[RMRS §1–2](https://aclanthology.org/W07-1210.pdf)。这些研究支持保留尚未消解的歧义；它们不保证自动选出临床语境中的唯一正确解释。

**SP03，Boxer。** Boxer 用 CCG 组合语义生成含事件与角色的 DRS，再单独处理照应。论文同时报告角色分析的成功和代词、量度、协调的失败；其超过 95% 的新闻文本覆盖率是“能产生表示”，作者明确说缺少金标准，无法据此量化语义质量。[Boxer §3.3–5](https://aclanthology.org/W08-2222.pdf)。这直接提醒我们不能用“规则条数”“可执行率”代替忠实率。

**SP04，Parallel Meaning Bank。** PMB 将分词、句法、语义标签、符号归一与组合表示分成可纠正环节，并保存人工纠正；与已审核标注冲突时再交专家裁决。其 gold/silver/bronze 表示不同人工核验程度，而非三个自动模型置信度等级。[PMB §3、§5](https://aclanthology.org/E17-2039.pdf)；[官方数据定义](https://pmb.let.rug.nl/data.php)。可迁移的是把来源单位、解析单位和核验状态分开记账；官方数据规模不能外推为医学指南的抽取准确率。

## 4. 约束解码：不仅可以检查 JSON，但仍不能自动识别意图

**SP05，PICARD。** PICARD 在生成过程中执行增量解析。论文区分词法检查、语法解析和守卫；守卫能约束数据库列、表及别名作用域。实际官方 `Parse.hs` 中的 `ParserState` 保存别名/表/当前作用域，`withGuards` 检查引用是否在范围内。这是超出括号和 JSON schema 的真实语义环境约束。[PICARD §2](https://aclanthology.org/2021.emnlp-main.779.pdf)；[官方解析代码](https://github.com/ServiceNow/picard/blob/main/picard/src/Language/SQL/SpiderSQL/Parse.hs)。

但 SQL 作用域正确不等于问题意图正确：论文将 exact-set、执行匹配及执行错误率分开测量，并把更多类型守卫列为当时的后续工作。不能把当前仓库里的扩展反写成 2021 论文已有保证，也不能把一张数据库上的执行相同当作所有输入上的公式等价。[PICARD §2.3、§3](https://aclanthology.org/2021.emnlp-main.779.pdf)。

**SP06，Synchromesh。** completion engine 可施加语法、作用域、类型及上下文约束；TST 另用目标 AST 的结构相似性寻找示例。§3 的保证以 completion-engine 公理和已实现约束为前提，§4.2 则明确展示形式有效但概念错误的输出。Table 2 中 Codex 175B 的 SQL CSD+TST 有效率 85%，执行匹配率 64%；SMCalFlow 相应为 99% 有效、63% 精确匹配。差距本身证明两种终点不能混称。[Synchromesh §2–4、Table 2](https://arxiv.org/pdf/2201.11227)。

其目标结构示例检索是有价值的独立部件，但也不替代源文裁决。此次核对的作者论文与 Microsoft 页面没有建立作者维护代码的可得链接；搜索所得同名 GitHub 实现自称 unofficial，未将其当作原作者实现。[官方出版页](https://www.microsoft.com/en-us/research/publication/synchromesh-reliable-code-generation-from-pre-trained-language-models/)。

**SP07，Type-Constrained Code Generation。** 2025 年 PLDI 工作进一步检查前缀是否还能完成为所需类型的表达式。其形式体系用类型环境和前缀自动机，实际 TypeScript 支持有明确范围；为保证搜索终止，形式构造牺牲了部分完备性。论文报告编译错误及功能正确率两个不同终点，并未声称类型安全等于自然语言保真。前缀仍可被合法完成，也不保证模型一定完成生成：§6 的剩余编译错误包括生成循环及预算截断；保证须限定在支持的语言与正常完成输出上。[论文 §3.4–6](https://arxiv.org/pdf/2504.09246)；[作者复现代码](https://github.com/eth-sri/type-constrained-code-generation)。

这三条路线能阻止一部分“不可能合法”的输出。本仓库式的 `TAPSE/PASP` 比值错绑成 `PASP` 数值，若类型含量纲和测量身份，原则上可能被拒绝；但两个合法疾病标签对调，或将同一条件从充分条件改为必要条件，仍可能完全通过类型检查。这里是基于论文机制的推断，并非已有临床实验结论。

## 5. 程序与反例：形式验证只能验证已经形式化的责任边界

**SP08，Combinatorial Sketching。** Sketch 接受带空洞的程序和独立的形式规格，交替调用合成与验证求解器；找到违反规格的输入，就将其加入下一轮约束。2006 年论文的保证建立在有限程序/有限域语义之上，实验是程序内核，不是医学散文转换。[Sketch §3–5，尤其 §5.4 / Figure 4](https://people.csail.mit.edu/asolar/papers/asplos06-final.pdf)。

这给“让模型自我修复”加上关键条件：反例必须针对独立可辩护的参照。让同一个生成过程同时产出误读的规格和符合它的程序，可以通过形式验证，却仍然错读指南。反例能区分两个候选公式的行为，不能凭空决定原文意图。官方实现及手册可获取，但本轮没有运行。[作者代码](https://github.com/asolarlez/sketch-frontend)。

## 6. CNF/DNF 不是复杂判据的唯一入口

**SP09，正规形资料。** LogicNG 官方文档与 Avigad 的形式推理教材均区分：保持逻辑等价的直接分配展开可能指数膨胀；Tseitin 用辅助变量和子公式定义获得较紧凑的可满足性编码。后者的术语是 equisatisfiable，不能直接冒充在所有原始与辅助变量赋值上的 pointwise equivalence。[LogicNG CNF Transformations](https://www.logicng.org/documentation/formulas/operations/transformations/normal-form-transformations/)；[Avigad §6.1](https://avigad.github.io/lamr/decision_procedures_for_propositional_logic.html)。

对采用完整双向子公式定义并断言根节点的 Tseitin 编码，关系可写为 `φ(x) ↔ ∃z T(x,z)`：原变量上的模型投影恢复原式，满足原式的赋值还可按子公式真值扩展辅助变量。这比抽象的“同可满足”更具体，不能将任意仅同可满足的编码都当作保持这种投影。[Avigad §6.1](https://avigad.github.io/lamr/decision_procedures_for_propositional_logic.html)

所以，能提取 CNF/DNF 应解释为能保留并执行相应组合意义，而不是强制模型在抽取时完成分配展开。原始递归 AST 或保留绑定/作用域的图可作为语义表示，正规形用于特定求解任务。使用辅助变量时还须保留定义、根公式与原始变量上的投影语义。这是形式资料支持的表示选择，不是一个新的抽取准确率结论。

还需区分**高层嵌套**与**高阶逻辑**：谓词只接受个体参数时，`AND/OR/NOT` 和 `forall/exists` 任意递归嵌套仍可属于一阶逻辑；量化谓词或函数才触及更高阶对象。广义量词、模态、默认/失败否定也不能未经定义便塞入同一二值 FOL。ACE 与 MRS 各自的扩展范围正说明这一点。[ACE §2.4](https://attempto.ifi.uzh.ch/site/pubs/papers/drs_report_67.pdf)；[MRS §1–3](https://www.cl.cam.ac.uk/~aac10/papers/mrs.pdf)。

## 7. 对现有审计问题的文献回答与证据缺口

| 用户关心的槽位 | 已审读研究提供的实际能力 | 仍须独立解决的问题 |
|---|---|---|
| 嵌套连词、组的结构 | ACE/DRS 的递归条件；MRS handles；受约束的递归语法 | 源文中的“并且/或者/列表”究竟是哪一种关系 |
| 量词、计数、作用域 | ACE 明确解释约定；MRS 限制域/主体与未决范围 | 集合是否完整、量词对谁成立、时间窗或人群限制 |
| 否定与诊断方向 | 否定、蕴涵可独立表示；形式工具可比较公式行为 | “建议排查”是否被误当作排除证据，充分/必要条件是否误读 |
| 变量角色与量纲 | DRS 事件角色；PICARD 绑定守卫；类型约束生成 | 合法但医学身份错误的绑定，省略和照应的消解 |
| 形式正确与修复 | 求解器产生反例；Sketch 对形式规格验证 | 原文→规格本身是否忠实，参照是否独立 |
| 能力边界 | PMB 分层人工核验；Boxer 区分覆盖/质量；代码研究分开有效/正确 | 本仓库逐源规则的忠实、曲解、遗漏及无来源输出分母 |

本组文献最可靠的启发是将模糊的“抽取成功”拆成可检查的责任边界，同时保留原文锚点和不确定解释。它没有提供一个可直接引用的“任意临床指南 FOL 忠实率”，也没有证明正确形式化以后必然提高诊断 MRR。后一个问题仍取决于适用人群、病例缺失信息、准则的必要/充分地位及候选粒度；需要与本轮已完成的新旧差量证据结合，而不能由语言或程序基准代答。
