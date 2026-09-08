# 需要语义恢复的全部工作项：技术覆盖与实验矩阵

本表补足“entity linking 不能包办全部语义缺陷”的边界。登记中27项 hybrid_semantic 按下面六个恢复任务完整映射，机器列表见 [semantic_repair_matrix.json](semantic_repair_matrix.json)。一个任务可以同时含纯代码保护和新的语义恢复；这里只为仍无法从已有正确字段确定的部分制定研究。

## 1. 六类技术任务

| 任务 / 覆盖项 | 输入与输出合同 | 借鉴的方法与需要改造之处 | 冻结对照与失败判据 |
|---|---|---|---|
| T1 概念身份及原文主体：IDN-01/03/04/05/07、UP-15/25、AUX-03 | 源跨度、章节/指代、类型与限定→候选身份＋equivalent/broader/narrower/related/causal/NIL；marker与疾病分库 | 版本化术语、文内缩写先行；BioSyn/SapBERT只召回；BELHD式上下文消歧；未知指代保留未决，不采用最近名称默认值 | 词法/可信词典/召回＋裁决三臂；同时测错误same-as、漏合法别名、层级方向、NIL；只有Top-k召回提高不晋级 |
| T2 观察事件及数值依附：IDN-06/08/11/12、UP-10/11/16 | 每个数字、单位、否定cue、取样和时间均绑定到特定观察事件，不按数字数组位置配对 | LOINC/UCUM提供指标/单位结构；ConText/medspaCy提供带范围的否定、经验者和时间状态基线；复杂跨句时间仍需事件关系解析及独立复核 | 固定实体span下先评context/metric/argument，再端到端；对年份/年龄/真正阈值、左右部位、患者/家属、当前/既往及两个不同长度数值列表测误配；原文未给时间边不得造边 |
| T3 命题等价与计数单位：IDN-10、ENG-04/08 | 完整typed literal/AST与每个member edge→same semantic object / implication / different / unresolved | 完整槽位哈希先做；语义检索只提出等价候选；复用上一轮CLOVER式区别反例、逻辑作用域与profile绑定验证；每个计数类需独立可追溯见证 | 改写重复不增票；相同词不同阈值/时间/部位不能合并；两个明确独立属性可来自同一原始fact；同时报告错合并与漏合并 |
| T4 来源蕴涵、方向与作用域：UP-06/09/12/13/14/19/27 | 原文及完整列举/限定→受控句法草图、变量/比较/根方向，再编译；quote存在与内容蕴涵分别检查 | 复用前轮受控语言、MRS式作用域、组合FOL翻译和反例验证方案；NLI输入应完整表达条件内否定、root action与scope，不再对整个relation取not | 先source-first人工参考；把必要换充分、AND换OR、范围互换、负分变排除、治疗建议变诊断等作为可区分反例；solver合法/等价与源文忠实分开计 |
| T5 真正的定向比较：ENG-14 | pair(A,B)、条件、作用域、favors、来源及见证；允许neither/context-dependent及coexisting | 复用已有KG DifferentialAssertion/CCEG的pair-binding和enumeration-only准入思路；采用受限关系/条件抽取，不将“列在同一个DDx表”当负例方向 | 固定pair与患者事实，交换A/B、翻转条件、复制句子、增无关疾病；方向应相应变化或弃权，不能新增无来源处罚；允许双方可共存 |
| T6 规则用途与完整源单元：UP-17 | 保留短而完整的命题与长但不完整段落；输出stage/intent/typed target/state/applicability及未决槽 | 使用任务2的类型合同与FHIR CPG分步知识工程；枚举/格式约束只做语法门，源清单和阶段/动作/范围跨度审查决定完整性 | 短规则召回、无疾病对象建议、合法跨阶段证据、未闭合条件/例外同时测；不能用长度或成功JSON代替完整性 |

T1细节及八项一手来源在 [semantic_binding_research.md](semantic_binding_research.md)。T3/T4复用已完成的 [逻辑抽取综述](../FAITHFUL_RULE_EXTRACTION_LITERATURE_REVIEW/REPORT.md)、[现代FOL分析](../FAITHFUL_RULE_EXTRACTION_LITERATURE_REVIEW/modern_fol_review.md)及[形式语义分析](../FAITHFUL_RULE_EXTRACTION_LITERATURE_REVIEW/semantic_parsing_review.md)，不是再次宣称执行了那些外部模型。尤其CLOVER的求解器只能验证形式候选之间的区别/等价，源文反例判断仍有模型误差；不能用同一个LLM的两次同意当临床源忠实证明。原始研究：[Divide and Translate](https://openreview.net/forum?id=09FiNmvNMw)。

## 2. 本轮追加核验：临床上下文抽取不必全部靠自由式 LLM

ConText 在已定位临床概念周围使用触发词、伪触发词与范围终止词，区分否定、历史/假设状态和经验者。可借鉴的关键是 **cue作用于哪个概念及到哪里结束**，而不是重新加入一个全句regex。该工作有默认 affirmed/recent/patient 和特定任务的历史时间定义；本仓硬动作通路不能把这些默认值直接作为明确患者见证。早期试验的概念集/报告类型有限，跨时点和指代并未因此全部解决。[ConText原论文](https://aclanthology.org/W07-1011.pdf)。2009年扩展论文也明确指出，完整的历史/近期判别需要超出表层cue的知识；本轮该文只核验PubMed原始摘要，全文PMC访问受阻。[2009原始摘要](https://pubmed.ncbi.nlm.nih.gov/19435614/)。

medspaCy 提供模块化临床文本处理，含上下文属性和章节处理；可以作为有源跨度、可配置的确定性基线，并与模型部件组合。[作者预印本摘要](https://arxiv.org/abs/2106.07799)、[官方项目](https://github.com/medspacy/medspacy)。它不是可靠的整条指南→FOL转换器。本轮没有安装或运行它；拟采用版本仍须冻结，禁用会破坏原文偏移的预处理或同时维护可逆offset映射；不能因为工具支持negation就撤掉未知/冲突与效力许可。

这两类工具适合T2的一部分与T4的cue候选生成，**不替代精确数值依附、跨句事件排序、通用指代或临床诊断效力判断**。对病例表中两个没有显式连接的测量列表，正确默认是无已证时间关系；不是更精致的自动zip。

## 3. 所有技术任务共同的评价约束

先固定来源单元，独立记录source→IR忠实/曲解/遗漏及output无来源幻觉；失败任务保留在端到端分母。对条件成功的局部模块指标另起名字。困难反例集检验边界，概率抽样估计真实分布；二者不能混算。

比较C代码保护、C＋术语/context工具、C＋受限语义模型，分别报告覆盖与错误，保留合法硬动作召回。金标与下游名次只能用于之后追踪，不能用于挑选本次源语义解释。上轮11例只作为开发素材；确证需新来源/新病例、概念/文档族隔离、冻结阈值和实际成本账本。所有方法均为待实施方案，未以文献中其他端点的准确率承诺本仓效果。
