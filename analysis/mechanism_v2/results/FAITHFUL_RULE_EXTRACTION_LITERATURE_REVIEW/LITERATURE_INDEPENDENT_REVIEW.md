# 文献分报告独立复核

审阅日期：2026-09-06。审阅者：`/root/differential_methods_review`。对象为 [modern_fol_review.md](modern_fol_review.md) 与 [semantic_parsing_review.md](semantic_parsing_review.md)，连同各自来源和检索账本。临床分报告由另一审阅者检查，见 [CLINICAL_REVIEW_CHECK.md](CLINICAL_REVIEW_CHECK.md)；本文不将自审当作独立复核。

## 结论

**完成以下修订后，两份报告可供主综合引用。** 未发现会推翻主论点的数值错误。必须保留的结论是：形式约束、相对参考公式的等价、原文忠实和临床执行有效性是不同终点。两份报告已经把本仓迁移写成待检验推论，没有把通用逻辑或代码基准成绩当作医学规则忠实率。

本复核阅读原始论文方法、指定表格与官方实现，未运行外部项目，也未复现论文成绩。另由独立协作者重查 Synchromesh 数字、类型约束证明边界及 Tseitin 编码关系。

## 已直接修订并同步账本的项目

| 项目 | 修订及其影响 | 原始依据 |
|---|---|---|
| 等价的量化范围 | “固定解释下等价”改为固定签名、符号映射及背景理论下等价；单个解释的同值不足以证明等价 | [Vossel §3.5](https://arxiv.org/html/2509.22338v2) |
| NL2FOL 数据集 | 0.96/0.78与0.70/0.80数值正确，标签改为 **LOGIC+SNLI、LOGICCLIMATE+SNLI**，避免误作原始数据集成绩 | [Table 2及数据构造](https://aclanthology.org/2025.findings-ijcnlp.8.pdf) |
| FoVer 验证对象 | 加入 Algorithm 1 对冲突辅助定义的删除；证明相对于保留理论，不证明删改保真 | [§3.3 Algorithm 1](https://aclanthology.org/2025.tacl-1.61.pdf) |
| FoVer 条件与对照 | FOLIO70.4%明确为统一Entity的专用提示；通用提示为62.1%。95.5%与all-question strict78.5%不能当作已控制同一公式的纯评分效应 | [Tables 1–3](https://aclanthology.org/2025.tacl-1.61.pdf) |
| CLOVER 源文预处理 | 补充先生成估计理论和目标自然语言句；后续验证不能补回这一整理环节丢失的原文限定 | [§2式2–3](https://arxiv.org/html/2410.08047v2) |
| LINC 聚合 | 数字不变，补充LINC及CoT等对照均为bootstrap十票结果，不作单调用比较 | [Figure 3](https://aclanthology.org/2023.emnlp-main.313.pdf) |
| 类型约束生成 | 可完成前缀不保证实际生成终止；限定支持语言与完成输出，明确循环/预算截断边界 | [§3与§6](https://arxiv.org/pdf/2504.09246) |
| Tseitin | 补充完整定义且断言根节点时`φ(x) ↔ ∃z T(x,z)`；模型投影保证比抽象同可满足更具体 | [§6.1](https://avigad.github.io/lamr/decision_procedures_for_propositional_logic.html) |

这些修改均已同步至两份正文、两份来源JSON及两份检索日志。FoVer JSON同时纠正GPT-4/GPT-4o字段命名。没有新增本仓性能数字。

## 复核通过的关键数字及实现主张

- Logic-LM FOLIO执行率79.9→85.8而执行条件准确率80.4→79.9，FOLIO few-shot语法有效93.9/执行准确63.8，CLOVER的程序整体、执行率、条件准确率三组数字均对应原表，报告没有把它们混合。[Logic-LM Table 3](https://aclanthology.org/2023.findings-emnlp.248.pdf)、[FOLIO Table 5](https://aclanthology.org/2024.emnlp-main.1229.pdf)、[CLOVER Table 2](https://arxiv.org/html/2410.08047v2)。
- Logic-LM++的GPT-4增益与GPT-3.5反向结果、Vossel的金标谓词/预测谓词条件、MenTaL的模型依赖、ALTA的绝对准确率比较均与原表一致。它们不能共同拼接成一个跨论文排行榜。[Logic-LM++ Table 1](https://aclanthology.org/2024.nlrse-1.6.pdf)、[Vossel §4.2](https://arxiv.org/html/2509.22338v2)、[MenTaL Table 3](https://arxiv.org/html/2506.04575v3)、[ALTA Table 2](https://aclanthology.org/2025.alta-main.1.pdf)。
- Synchromesh SQL85%有效/64%执行，SMCalFlow99%有效/63%精确匹配，确为Codex175B的CSD+TST，两个任务准确率定义已区分。[Table 2](https://arxiv.org/pdf/2201.11227)。
- LogicLLaMA LE的量词盲点有官方源码静态证据：`S`节点沿公式体递归，后续为原子布尔表匹配。源码已锁定commit `785a2c08e8fe964c8b2a10bb183ce5a08867aa3b`并将两文件SHA256写入账本；不声称执行过外部评测器。[metrics.py](https://github.com/gblackout/LogicLLaMA/blob/785a2c08e8fe964c8b2a10bb183ce5a08867aa3b/metrics.py)、[fol_parser.py](https://github.com/gblackout/LogicLLaMA/blob/785a2c08e8fe964c8b2a10bb183ce5a08867aa3b/fol_parser.py)。

## 对主综合的引用限制

不把本轮查阅表述为穷尽性系统综述；不把临床人工审定树的执行成绩表述为自动抽取忠实率；不把执行一致当作全规则等价。对本库的建议应标为迁移假设，并继续区分来源缺失、语义表示、实体绑定和排序传播。这些是现有证据的适用范围，无需为完成本次文献交付额外启动实验。

## 综合报告与临床标准的交付复核

追加于2026-09-06，审阅 [REPORT.md](REPORT.md) 及 [clinical_standards_review.md](clinical_standards_review.md)。结论：**以下口径同步后通过，无新增阻断项。**

- 主综合原先再次把FoVer95.5/78.5写成同样本只改变评分的下降，主审阅者已同步改为两设置的报告结果，并保留非同缓存控制的限制；本次明确补入冲突定义删除改变验证理论。
- Text2MDT整树终点统一为“精确匹配率”，加100例测试、5次运行均值；CPGPrompt注明测试病例源自经审定树；LogicLLaMA代码引用改为冻结commit；约束生成补上完成预算边界。
- 四份账本分别为11、9、8、7条，共35条研究/标准记录。主综合已明确一个条目可含多种原始资料，未声称35篇独立实验论文。部分摘要或全文不可得边界仍保留。
- CQL 2.0.0条文独立核实：`AllTrue`忽略null，空列表、全null列表和null列表均返回true；`exists(null)`返回false。原标准分报告正确，主综合仅将“全空”改成明确的三个输入情形。[CQL AllTrue及Exists](https://cql.hl7.org/09-b-cqlreference.html)。
- OWL开放世界、不同名字不蕴涵不同个体，与SHACL给定数据图的合规检查保持分离。SHACL2017§3.4.3确实未规定循环递归shapes的统一验证语义；这不限制有限深度的嵌套逻辑组合。标准分报告未将此误作“不支持嵌套”。[OWL Primer](https://www.w3.org/TR/owl2-primer/)、[SHACL §3.4.3](https://www.w3.org/TR/shacl/#shapes-recursion)。
- CQL/ELM递归表达式及类型/作用域校验来自官方语言语义，不包含任意源文到CQL的忠实性保证。标准分报告明确了这一点，无需修正研究内容。[CQL §5.2](https://cql.hl7.org/05-languagesemantics.html)。

本次只补读必要官方条文并修订综合措辞，没有新增大范围检索，也未运行外部语言实现。研究矩阵由主审阅者从账本另行生成。
