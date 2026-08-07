# 因 MCQ 选项泄漏而需冻结／改写的论文条目清单

Created: 2026-08-07 · 内部 · 配套 `INTERNAL_MEMO_mcq_option_leak.md`

前提事实（已逐例确证，见配套备忘录）：流水线臂（M00/APHHM 及全部消融臂）的
`state.case_summary` 来自 `static_qa_env.get_case_summary()`，逐字包含
`Question + Options`，金标准即选项之一；基线臂经 `vignette_body()` 剥离选项。
**"流水线 vs 基线"的一切数值对比输入不对等；流水线臂之间的对比输入一致。**

---

## 0. 波及范围（逐运行核查，非抽样）

| 数据集 | 主臂与消融臂 | 金标准逐字在 context | 截断后仍在前 1500 字符 | 选项位置 |
|---|---|---:|---:|---|
| **OpenXDDx (OX)** | 全部 17 个运行 | **100%** | **97%** | 无固定偏置 |
| **MedCaseReasoning** 切片一/二 | M00 + AB02/AB04/AB06 | **100%** | 74% | **恒为选项 A** |
| **DiagnosisArena** | M00 + AB01/AB02/AB03/AB21/AB22 | **100%** | 46% | A 55%（均匀应 25%） |
| **RareArena** | 全部 9 个运行 | 1%（本底巧合） | — | **无选项块，干净** |

**四个数据集里三个受影响，RareArena 是唯一干净的。**
按"截断后仍进入模型"排序，严重程度为 **OX > MCR > DA**。

---

## 一级：与实验事实直接矛盾的陈述（最高优先级）

这不是"数字需更新"，而是论文明确写下的事实性声明与代码行为不符。
无论重跑与否，这四句都必须改。

| 文件 : 行 | 原文 |
|---|---|
| `paper_aaai/main.tex:316` | *Gold labels are never used during generation, evidence selection, state update, or arbitration.* |
| `paper/sections/body.tex:373` | *Gold never enters runtime generation, evidence selection, write-back, or arbitration.* |
| `paper_aaai/SupplementaryMaterial copy.tex:275` | *Gold labels are excluded from generation, evidence selection, state update, and arbitration…* |
| `paper_aaai/SupplementaryMaterial.tex:132` | 同上 |

相关的输入定义同样不完整：`main.tex:116` 把输入定义为
*"a static clinical vignette $V$, observed facts $F$…"*，未提及模型上下文含 MCQ 选项。

**五份源文件中未找到任何一处披露流水线推理时接收 MCQ 选项。**
最接近的表述（`main.tex:299,311` 的 *option-mapped Top-1*、*option-to-leaf binding*，
`body.tex:359` 的 *MCR… no option-mapping interface*）指的都是**评测接口**，不是推理输入。

---

## 二级：【失效】——结论完全依赖不可比对比，重跑前必须撤下

### 主结果表与"优于基线"

| 文件 : 行 | 内容 |
|---|---|
| `main.tex:355–387` `tab:main` | 主表：APHHM 与 MEDDxAgent/MAC/Dual-Inf/Flat rerank×10 同列六指标 |
| `main.tex:384` | caption *"Bold marks the best reported value in each column"* |
| `main.tex:389` | *"APHHM ranks first in all six columns"* |
| `main.tex:390–391` | *"+0.09/+0.07 on DA… +0.26 on MCR… +0.081 on OX"* |
| `main.tex:391–392` | MCR reasoning recall *"0.753 vs. 0.570"* |
| `body.tex:422–432` `tab:main` | 同一主表的模块化版本，含 *"Best external 0.62/0.71 (B07)"* |
| `appendix.tex:50–79` `tab:da-full` / `82–110` `tab:mcr-full` / `113–143` `tab:ox-full` | 三份全基线表 |
| `Supp copy.tex:301–330` `tab:all-baselines` | 全基线表 |
| `Supp copy.tex:426` `tab:interp` | *"APHHM ranks first on the diagnostic endpoint"* |

### budget-matched / compute-matched 优于平坦控制

| 文件 : 行 | 内容 |
|---|---|
| `main.tex:635–654` `tab:budget` | Flat rerank 2/9/90 calls 对照表 + *"APHHM reaches 0.71, 0.50, 0.651"* |
| `main.tex:654` | *"persistent margin at similar or higher call counts indicates that structured hypothesis management contributes beyond repeated flat sampling"* |
| `main.tex:54, 87, 679` | 摘要／引言／结论中的 *"retains its end-task margins under a similar-call-count flat control"* |
| `body.tex:651–679` `sec:rq4` | *"B02-SC10 removes that objection, and the conclusion strengthens"* |
| `body.tex:670–672, 723` | *"Every value remains far below the corresponding APHHM row"* |
| `Supp copy.tex:333–365` | *"between 0.16 and 0.35 above the ten-trajectory flat control"* |
| `Supp copy.tex:1006–1008` | *"gain is attributable to organisation rather than to inference budget"* |

> 这一组我有直接反证：等输入对照下，4 次调用的骨干与 84 次调用的 AB02 打平
> （MCR 0.47 vs 0.44、DA 0.65/0.67 vs 0.64/0.68）。**调用预算与层级组织在拉平输入后
> 都没有可归因的净贡献。** 见配套备忘录 §4。

### 对基线的统计显著性检验

| 文件 : 行 | 内容 |
|---|---|
| `Supp copy.tex:526–563` `tab:second-judge` | 第二 judge 下对 13 条基线的 Holm 校正配对检验全部显著 |
| `Supp copy.tex:923–965` `tab:rec-paired` | DA @1 对 17 条基线的配对 Δ 与 p_Holm |

### 跨系统机制／失败分解

| 文件 : 行 | 内容 |
|---|---|
| `Supp copy.tex:639–668` `tab:slots-cross` | OX wasted-slot 0.029 vs 平坦基线 0.042–0.098 |
| `Supp copy.tex:675` | 参考概念交付率 0.593 vs 0.790 |
| `Supp copy.tex:729–762` `tab:failvec` | DA 失败向量跨系统对比 |
| `Supp copy.tex:1030–1044` `tab:exposure` | MCR 分层 margin +0.250/+0.262（MCR 金标准恒为 A，此表最不可信） |
| `Supp copy.tex:447–474` `tab:ial` | 各系统 native/bound Top-1 |
| `Supp copy.tex:1261` | Mechanistic Synthesis 的总括句 |

---

## 三级：【需重述】——数字受影响，定性方向可能仍成立

| 文件 : 行 | 内容 | 为何仍有救 |
|---|---|---|
| `main.tex:300`, `body.tex:58–59, 348–349` | 绑定修复使外部基线提升 +0.02–0.08 | 修复效应本身在基线内部测得，但"缩小了差距"的表述依赖不可比的原生差距 |
| `main.tex:392` | *"The following mechanism tests explain these margins"* | 机制测试本身有效，但不能再挂靠主表 margin |
| `appendix.tex:146–164` `tab:compute` | 调用数匹配 | 调用统计与输入无关，成立；由此推出的 end-task 论断不成立 |
| `appendix.tex:292–293` | 以平坦基线作为层次必要性的证据 | 需改由流水线内部消融支撑 |
| `Supp copy.tex:296–298` | *"differences are attributable to method rather than to model capacity"* | 需增加"且输入一致"这一前提，当前不满足 |
| `Supp copy.tex:486–518` `sec:decoupling` | Acc 与 R-Recall 解耦（基线臂间相关 0.141） | 基线臂之间输入一致，相关性分析成立；但 §518 的 *"margin 非同义重述"* 依赖 margin |
| `Supp copy.tex:806–813` `tab:conversion` | 条件转换率 | 文内已部分自我限制，需进一步降级 |
| `Supp copy.tex:962–965` | *"competitive with strongest published designs"* | 方向可能反转，需重跑 |

---

## 四级：【可保留】但效应量需在干净输入下复核

流水线臂内部的消融（M00 vs ABxx）输入一致，**内部效度成立**：

- `main.tex:397–424` `tab:org-axis` DA 轴消融 0.37 → 0.71，p=3.1×10⁻⁷
- `main.tex:457–464` MCR 等价处理 0.50 → 0.42，p=0.002；盲合并 p=0.015
- `main.tex:550–576` `tab:state-2x2` OX write-back 0.576 → 0.651，bootstrap p=4.0×10⁻⁴
- `main.tex:617–630` `fig:attribution` leaf injection 0.72 → 0.42，p=1.5×10⁻⁵
- `appendix.tex:337–341` `tab:holm5` C1–C5 五对比
- `Supp copy.tex:1077–1107` `tab:confirmatory`
- 全部方法描述、成本／调用统计、可复现性说明

**但有一条重要保留意见：内部效度 ≠ 效应量可迁移。** 这些效应都是在"答案已在上下文里"
的条件下测得的。我自己的骨干实验提供了效应量在干净／泄漏输入下反转的直接先例：
入口广度在干净输入下 +0.08（DA option@1 0.50→0.58），在泄漏输入下 **0.00**
（0.65→0.65）——答案已在上下文时该机制完全失效。因此上述消融的效应量在干净输入下
**可能显著缩小甚至消失**，重跑后需逐项复核，不宜直接沿用当前数字。

RareArena 相关的全部结论**不受影响**（该数据集无选项块）。

---

## 五级：计数与建议处置顺序

| 分级 | 约条数 |
|---|---:|
| 一级 事实性矛盾陈述 | 5 |
| 二级 失效 | ~72 |
| 三级 需重述 | ~18 |
| 四级 可保留（效应量待复核） | ~35 |

**建议顺序**

1. 先改一级的五句——与重跑无关，且这是最不可辩护的一类问题。
2. 冻结二级全部条目：主表、三份全基线表、budget 一节、跨系统分析、对基线的显著性检验。
   在重跑出干净数字之前不要对外送出任何包含这些表的版本。
3. 修 `static_qa_env.get_case_summary()` 后，按 **OX → MCR → DA** 的顺序重跑
   （按泄漏严重度排序，OX 的 97% 截断存活率意味着它的数字最可能大幅下修）。
4. 重跑完成后，先复核四级各项消融的效应量是否仍成立，再决定三级条目如何重述。
5. RareArena 部分可以照常推进。

---

## 复现

范围核查与泄漏定量的脚本、日志见 `INTERNAL_MEMO_mcq_option_leak.md` §7。
本清单的行号基于 2026-08-07 的工作区状态：`main.tex` 695 行、
`SupplementaryMaterial copy.tex` 1265 行、`body.tex` 725 行、`appendix.tex` 352 行。
