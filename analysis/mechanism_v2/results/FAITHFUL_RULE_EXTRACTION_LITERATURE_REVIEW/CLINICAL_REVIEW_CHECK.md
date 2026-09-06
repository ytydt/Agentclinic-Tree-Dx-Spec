# 临床子报告独立复核记录

审阅日期：2026-09-06。审阅者：与临床子报告作者独立的 `differential_replay` 子任务。

对象：[clinical_llm_review.md](clinical_llm_review.md) 与 [clinical_llm_sources.json](clinical_llm_sources.json)。范围按任务要求聚焦 CPGPrompt、Text2MDT、NICE→ASP D2K、TSDTE；没有重新审查其余四篇的全部主张，也没有执行外部 LLM 管线。

**结论：聚焦范围内通过，无阻断性事实或算术错误；建议加入下述两项评测口径补充。** 本记录不替作者静默改写原报告，补充项供主综合与作者修订采用。

## 1. 已核验项目

| 项目 | 独立证据 | 裁决 |
|---|---|---|
| CPGPrompt 人工介入 | 原文 §2.1 人工选择叙述段落；§2.2 明确每棵自动树人工验证，并修提示/重生成/少量人工调整 | 报告“经过人工保障的树执行”准确，不能解读为原始自动抽取准确率 |
| CPGPrompt 结构能力 | 官方 Node 的 `criteria: Optional[List[str]]`、`min_criteria: Optional[int]`；生成提示明确成员为字符串而非嵌套对象 | 报告区分平面阈值与任意节点内递归逻辑，表述准确；树路径可以组合条件，不能因此声称 schema 支持任意量词域 |
| CPGPrompt 实际执行 | 外层 traversal 调一次 rephrase，内层 ask 又调一次；yes 子串解析；达到计数阈值才走 yes_action | 两次改写、无独立 unknown、整组阈值实际生效的代码判断均准确 |
| CPGPrompt 合并 | merge 遍历所有相邻节点，替换结束/空 no_node | 报告纠正代码注释“章节末节点”的范围，准确 |
| Text2MDT 指标 | Table 4 整任务 0.490/0.632；Table 3 组装子任务 0.748，输入已含节点；§6.7 明确表达与跨段限制 | 没有混淆子任务与完整树终点 |
| D2K 公开 CSV | 独立逐行读 12 份 CSV，重算 rows、ID、五类评级；检查下载 hash 与均值 | 全部一致，见第 3 节 |
| TSDTE 后处理 | `classify_triplet`、`convert_pseudocode2DT` 两处删除/缩进调整及评测器 | relation 分类与作用域扩大的“可能性”判断成立；报告未假称已测临床发生率 |

论文原文：[CPGPrompt §2–3](https://arxiv.org/html/2601.03475v1)、[Text2MDT §6](https://arxiv.org/html/2401.02034v1)。代码原始位置：[CPGPrompt text2tree](https://github.com/bionlplab/CPGPrompt/blob/aa6061e2f6b2e810f7c5897232f45ab223a956a2/text2tree.py)、[traverse_tree](https://github.com/bionlplab/CPGPrompt/blob/aa6061e2f6b2e810f7c5897232f45ab223a956a2/traverse_tree.py)、[merge_tree](https://github.com/bionlplab/CPGPrompt/blob/aa6061e2f6b2e810f7c5897232f45ab223a956a2/merge_tree.py)、[TSDTE Pseudocode](https://github.com/nlper-hou/TSDTE/blob/299159c41f7a564cb00a70dd01f32d8cb500175d/Pseudocode.py)。

## 2. 建议补充的评测边界

### C1：Text2MDT 的分母与重复

原文 §6.3 的原始 split 为 800/100/100；§6.2 说明每项实验运行五次并报告平均。故 0.490 是 **100 个测试样本上的五次均值**，不是独立临床人群中“49%的所有规则都抽对”，也不应写成一次运行确定的49/100。0.748 仍是不同输入条件下的组装子任务，不能作为端到端抽取率。[Text2MDT §6.2–6.3、Tables 3–4](https://arxiv.org/html/2401.02034v1)

原报告已避免最主要的指标误读；加入样本量与重复次数能使未来横向比较更清楚。本补充不改变其现有结论。

### C2：CPGPrompt 的病例生成依赖已审树

原文 §2.4.1 说明 synthetic vignettes 由 guidance tree 生成，临床质检是每个领域抽10例、由3位临床人员审查。树本身已人工检查，这一点确实提高了实验输入质量；与此同时，使用该树派生的病例主要检验树的执行，不能独立发现建树时遗漏、而生成器也没有再询问的源规则。这是测试依赖结构的推论，不能夸大为论文没有人工质检。[CPGPrompt §2.2、§2.4.1](https://arxiv.org/html/2601.03475v1)

原文 Table 1 的腰痛99例均为转诊阳性，以及 Table 2 头痛二分类0.90/细路径0.44，均与报告一致；摘要数字与表格的差异已经被作者明确保留，无须重新归并。

## 3. D2K：独立计数、hash 与图表核验

以 UTF-8-sig 的 CSV DictReader 读取全部行，按 `rating` 统计，缺失类别补零，再计算各 reviewer 的类别数/该文件行数，最后取三审阅员均值。结果为：

| 公开快照 | 每位审阅员行数 / distinct guideline IDs | 未译% | 正确% | 错误% | 遗漏% | 幻觉% |
|---|---:|---:|---:|---:|---:|---:|
| 胰腺 D2K | 40 / 25 | 5.000000 | 71.666667 | 4.166667 | 16.666667 | 2.500000 |
| 胰腺 direct | 44 / 25 | 8.333333 | 66.666667 | 0.757576 | 21.212121 | 3.030303 |
| 肺 D2K | 56 / 36 | 13.095238 | 57.142857 | 10.714286 | 14.880952 | 4.166667 |
| 肺 direct | 59 / 36 | 27.683616 | 58.192090 | 9.039548 | 4.519774 | 0.564972 |

与临床 ledger 的全部12组人数/行数/分类计数及20个均值一致。进行了 **74项独立检查**：12份CSV各自的行数、ID数、分类向量、SHA256（48项）；四臂五类均值（20项）；CPGPrompt traversal及TSDTE四份代码SHA256（5项）；D2K PDF SHA256（1项）。这里没有把重复审阅员的评级当作独立源规则样本。

[官方审阅 CSV](https://github.com/Ashvin-Gupta/NICE-2-ASP/tree/9d9acadea2c8d4b7a4c60b5f7fff4eac5a81d57a/src/output_files/CLAUDE/reviews) 的一条源规则可展开多行，也存在空的未翻译占位。因此原报告称“审阅行评级比例”准确，不能用这些值替换用户要求的固定来源单位忠实/曲解/遗漏/无来源幻觉比例。

独立查看已渲染 Figure 6：肺 D2K 的正确柱在约54.8%，胰腺 direct 在约61.5%，与当前CSV分别57.143%及66.667%的差异属实；论文附录亦明确写出肺54.8%。原报告没有静默混用。另，§3.1把胰腺direct称为42条规则，当前CSV为42条非空规则加2条空占位，共44行；这一事实值得在需要讨论论文计数时注明，但**不能据此推断它就解释了 Figure 6 的评级差异**，差异来源仍未识别。[D2K 原文 §3.1、Figure 6、附录](https://arxiv.org/pdf/2608.30022)

原文将常见邻文中的“pancreatic protocol CT”泛化到本应为普通CT的条目列为幻觉。报告将此与用户“完全无可追溯来源”的严格定义区别，准确；它在本仓分类中可以是可溯源曲解，而非无源生成。

## 4. TSDTE：后处理机制是否被说得过强

官方 `convert_pseudocode2DT` 第一轮找不到条件三元组时记录该行，随后删去；在回到同级/外层之前，嵌套后续行缩进被减一。第二轮填充仍有条件无匹配时跳过并调整缩进的路径。`classify_triplet` 仅将指定的“临床表现/基本情况”（及英文对应）归为条件，其他 relation 归入决策池。因此错误 relation 可以先改变池归属，再造成条件填充缺失；代码不是只丢掉一个无关叶子的纯格式清理。[官方实现](https://github.com/nlper-hou/TSDTE/blob/299159c41f7a564cb00a70dd01f32d8cb500175d/Pseudocode.py)

原报告使用“可能升级成作用域扩大”是合适的静态推论。更精确的措辞可为“删掉缺失条件，并降低其嵌套后续行的缩进”，而非让人理解为无条件修改文件后面所有行。这项复核未声称该路径在发表实验中出现多少次，也未取得出版社全文，因此不补报论文增益数字。

## 5. 访问与审阅限制

CPGPrompt、Text2MDT 原文进行了本轮独立网络读取；TSDTE 固定GitHub代码页与 D2K 新 arXiv PDF 此次 web 请求返回 internal error，遂读取临床作者已经下载的原始公开文件，并核对账本 SHA256。缓存位于本次工作空间临时目录，交付的复核证据是上面的原始URL、哈希账本与计数说明，而不是额外复制整篇来源文献。

本复核没有重新抽取指南，没有使用模型重跑论文，没有展开其余四项研究的全面第二轮审查，也没有进入第三任务的实现设计。后续综合可以采用上述通过结论，同时保留 C1/C2 和纸面/CSV差异限定。
