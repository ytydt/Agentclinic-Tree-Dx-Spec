# 总体审稿判定

本文已经具备一个有吸引力的核心命题：

> 开放假设空间的性能瓶颈不只在召回，而在于候选组织、概念身份、局部证据状态和评价绑定能否跨阶段保持一致。

这个命题比单纯提出一个医疗多智能体流程更具有AAAI价值。当前实验也不是单纯“跑更多模型”：基线覆盖广，RQ1、RQ2、RQ3分别提供了组织、概念竞争和状态写回的机制证据，并设置了约90次调用的flat control。

但是，从苛刻审稿人的角度看，论文最薄弱的不是“基线数量不足”，而是：

> **论文提出一个统一的三机制框架，却分别在三个不同数据集、不同端点、不同评价接口上验证三个机制；目前没有一个共同实验环境同时证明三者的独立贡献、交互和整体必要性。**

这将成为最可能导致 borderline/reject 的主线质疑。

AAAI-27明确按贡献的显著性与创新性、理论或实证可靠性、AAAI相关性、表达清晰度和可复现性评价论文，并偏好能够开辟新问题或对单一窄领域之外具有意义的工作。主文应自包含，因为审稿人不必阅读补充材料。AAAI-27第一阶段还可能在没有作者反馈机会的情况下直接拒稿，因此明显的统计术语、因果归因和复现缺口尤其危险。([AAAI][1])

我的模拟结论是：

| 维度        | 当前状态                       |
| --------- | -------------------------- |
| 问题重要性     | 强                          |
| 核心insight | 强                          |
| 方法统一性     | 中强                         |
| 端任务结果     | 强                          |
| 机制因果隔离    | 中等，当前最大弱点                  |
| 统计推断完整性   | 中等偏弱                       |
| 外部有效性     | 弱                          |
| 可解释分析潜力   | 强，但尚未充分兑现                  |
| 复现与资源公平性  | 中等                         |
| 当前综合判断    | Borderline，补强后可达较强accept区间 |

---

# 一、论证最薄弱的位置：按风险排序

## 1. 三项机制没有在同一实验空间中被联合检验

当前证据结构是：

* case-adaptive axis：主要在DiagnosisArena验证；
* concept-level competition：主要在MedCaseReasoning验证；
* score write-back：主要在Open-XDDx验证。

论文因此能够说“每个机制在某个环境中有支持”，但还不能充分说：

* 三个机制共同构成一个统一系统；
* 三者在同一任务上各自贡献；
* 三者之间是互补、冗余还是存在负交互；
* APHHM整体增益能由这三个机制完整解释。

### 审稿人可能写出的批评

> Each claimed mechanism is validated on a different benchmark and endpoint. The paper never shows that all three components jointly matter in a common experimental setting, making the unified APHHM narrative stronger than the causal evidence.

### 必要修复：统一的 (2^3) 因子实验

至少在一个适合开放Top-(k)评价的数据集上运行：

| 因子                             | 0                        | 1                         |
| ------------------------------ | ------------------------ | ------------------------- |
| (A)：case-adaptive organization | fixed/flat organization  | adaptive axis             |
| (C)：concept competition        | string-level competition | concept-level competition |
| (W)：write-back                 | stale state              | updated state             |

共8个配置：

[
Y=\beta_0+\beta_A A+\beta_C C+\beta_W W
+\beta_{AC}AC+\beta_{AW}AW+\beta_{CW}CW+\beta_{ACW}ACW.
]

应报告：

* 三个主效应；
* 三个二阶交互；
* 三阶交互；
* full APHHM相对all-off的总效应；
* 基于8个配置的Shapley贡献分解。

这项实验的价值高于再增加5个普通基线，因为它直接决定论文是否能够从“组件集合”上升为“统一方法”。

---

## 2. RQ1主要证明的是axis–selector cascade，而非独立的axis效应

当前case-adaptive、fixed taxonomy和random axis使用同一selector，但不同axis导致：

* selected L1 facts从4.94降至0.65和0.13；
* empty rankings从1增至11和45；
* conditioning on nonempty cases后，random-axis差异从0.34大幅缩小；
* fixed taxonomy仍有残余差异。

这说明结果具有真实意义，但也表明：

> 大效应部分来自axis使下游selector能够正常工作，而不是纯粹来自更优的候选组织。

random control尤其容易被批评为“病理性控制”：45%的病例不能形成ranking时，0.37对0.71可能部分测量系统崩溃，而非组织质量。

### 必须增加的全交叉实验

建议采用至少 (3\times3)：

**Axis**

* case-adaptive；
* fixed ICD/specialty；
* matched random。

**Selector**

* candidate-relative；
* salience-based；
* selector-free或统一事实集。

这样才能回答：

1. adaptive axis是否对所有selector均有效；
2. candidate-relative selector是否只在adaptive axis下有效；
3. 当前效应是main effect还是interaction；
4. random axis的劣势是否主要来自empty-output failure。

### 应新增的中间变量

不要只报告准确率，还应报告：

* ranking completion rate；
* nonempty ranking rate；
* selected evidence count；
* family-pair distinguishability；
* residual-family proportion；
* target-hosting-family recall；
* L1 family mutual-exclusivity；
* L2 leaves per family；
* correct target进入global pool的概率。

这样可以把“axis改变了geometry”转化为可量化的机制链：

[
\text{axis quality}
\rightarrow
\text{evidence distinguishability}
\rightarrow
\text{target survival}
\rightarrow
\text{final accuracy}.
]

---

## 3. RQ2的方向有价值，但统计表述是当前最容易被统计审稿人攻击的部分

论文正确指出：保留每个equivalence class的最高排名成员时，Top-1对纯删除式压缩是代数不变量，因此使用any-hit@5、open-MRR和候选多样性等operator-sensitive endpoints。这是很好的insight。

但目前仍有四个问题。

### 3.1 对称的 (\pm5) 区域不是non-inferiority margin

Figure 2使用：

> pre-registered ±5 percentage-point non-inferiority margin

统计上：

* 双侧 ([-5,+5]) 是**equivalence margin**；
* 单侧 (-5) 才是**non-inferiority threshold**。

应二选一：

**若主张具体策略彼此等价：**

[
H_0:\Delta\leq-5\quad\text{or}\quad\Delta\geq5
]

采用TOST，并称：

> pre-specified ±5 pp equivalence region.

**若只主张变体不显著更差：**

只画 (-5) pp阈值，并进行单侧non-inferiority test。

### 3.2 “pre-registered”必须有可审核证据

如果没有带时间戳的正式注册文档、冻结commit或提交前分析计划，建议改为：

> pre-specified

“pre-registered”会使审稿人合理地要求注册时间、endpoint、margin和variant set的原始记录。

### 3.3 partition randomization不是case-sampling inference

当前blind merge随机化的是partitions，而不是病例。它能够证明：

> 在当前病例和随机分组机制下，语义分组优于相同数量/规模的盲分组。

但它不能直接证明：

> 在病例总体中，semantic compression具有相同效果。

论文当前将partition-randomization结果纳入Holm family，并使用较强的“shows semantic class membership matters”表述，容易放大其推断范围。

应增加两层nested resampling：

1. 外层对cases重采样；
2. 内层在每个case中重采blind partitions；
3. 每次重新计算any-hit和open-MRR差值。

这样得到的区间才同时体现：

* case uncertainty；
* partition uncertainty。

### 3.4 当前样本不足以证明小变体的等价性

以近似McNemar功效计算：

* 若真实差异为5个百分点、discordance约15%，80%功效需要约470个paired cases；
* 若真实差异为3个百分点，约需1,300个cases；
* 当前 (n=98) 能检出10个百分点左右的大效应，但不足以稳健宣称多个routing variants在±3或±5个百分点内等价。

因此Figure 2目前最安全的定位是：

> descriptive bounded sensitivity analysis

而非完成的equivalence conclusion。

---

## 4. stage audit是最有insight但证据最弱的headline

18/20 apparent coverage misses被归入binding failure，并通过full-tree leaf injection展示“错误诊断失败阶段会推荐错误干预”，这一分析极具论文辨识度。

但当前证据有明显弱点：

* 只有20例；
* retrospective；
* 来自earlier judge configuration；
* 没有独立、盲法的临床专家标注；
* 中间三个阶段均为0，容易让人怀疑规则或审计流程是否天然把错误推向两端；
* 正文将18/20概括为“nine tenths of an apparent recall gap”，语气近似总体比例。

18/20的Wilson 95%区间约为：

[
[0.70,0.97].
]

因此，当前数据支持：

> 在这20个回顾性审计案例中，binding failure占多数。

不能充分支持：

> 90%的表面召回错误通常来自评价接口。

### 必须增加的人类审计

对所有错误病例或至少100个错误病例进行：

* 两名独立临床标注者；
* 对方法身份和最终分数盲法；
* 随机化展示顺序；
* 预定义五阶段判定手册；
* 第三人仲裁；
* 报告Cohen’s (\kappa)或Krippendorff’s (\alpha)；
* 报告每类的95%区间；
* 将自动audit与人工gold比较，报告macro-F1和混淆矩阵。

还应审计正确病例，防止分类规则只在失败案例上看似合理。

### 更强的验证：stage-targeted intervention实验

将错误案例按人工stage分层，然后比较：

* 正确的stage-specific intervention；
* generic “retrieve more” intervention；
* 随机选择的错误intervention；
* no intervention。

定义：

[
\text{Intervention Regret}
==========================

Y_{\text{stage-targeted}}-Y_{\text{wrong intervention}}.
]

这会将stage attribution从一个解释性taxonomy提升为：

> 能够预测哪种干预有效的可操作诊断理论。

这是很符合AAAI偏好的新增insight。

---

## 5. write-back证据最干净，但只直接来自一个数据集

当前 (2\times2) evidence budget × write-back设计是论文中最强的因果实验：

* 固定预算下增加0.075 micro-F1；
* bootstrap 95% CI为[0.036, 0.113]；
* evidence budget本身最多变化0.008；
* interaction近乎为0；
* decoder、family cap和emit-enabled variants进一步定位到state update。

主要问题是：

> 该机制只在Open-XDDx上直接验证。

因此“state consistency是一般设计原则”的外推仍然不足。

### 建议增加两个控制

#### 跨数据集复现

至少在MCR或DA上增加：

* stale-state decoder；
* updated-state decoder；
* 同一候选池；
* 同一evidence budget；
* 同一final decoder。

即使只在100–200例上复现同方向，也能显著降低“OX-specific implementation artifact”的质疑。

#### serialization/refresh placebo control

需要排除“重写状态”本身改变prompt布局、上下文近期性或token位置，而非更新分数产生效果。

加入：

1. **No write-back**：读取旧状态；
2. **Placebo refresh**：重新序列化状态，但保留旧分数；
3. **True write-back**：重新序列化并写入新分数；
4. **Shuffled write-back**：写入其他leaf的更新值。

若只有true write-back有效，state propagation主张会非常强。

---

## 6. 固定顺序100例不足以支持稳定外推

三个数据集均采用固定顺序100例，每个configuration只有一个固定evaluation pass。论文明确将其限定为mechanism analysis，但摘要和Overall Performance仍容易被快速读成广泛性能优势。

主要风险包括：

* 顺序块可能集中于某些疾病、来源或难度；
* 无法估计跨病例块的异质性；
* 无法判断结果是否由少数高收益病例驱动；
* 模型API即使temperature为0，也未必完全确定；
* 机制小效应难以稳定估计。

### 最佳扩样方案

优先级从高到低：

1. **完整benchmark评估**；
2. 多个预先冻结、互不重叠的100例block；
3. 独立随机holdout；
4. 当前100例的重复模型运行。

建议最低规模：

| 目标                         |               建议规模 |
| -------------------------- | -----------------: |
| 复现当前大效应                    |       200–300例/数据集 |
| 稳健估计约5 pp效应                |              约500例 |
| 证明约3 pp小组件等价               |         接近1,000例以上 |
| stage failure比例            |         至少100个失败事件 |
| 将OX write-back CI半宽缩至约0.02 | 约350–400例，假设方差近似不变 |

还应按以下维度做stratified analysis：

* benchmark difficulty；
* rare/common disease；
* synonym density；
  -初始候选集大小；
  -目标初始rank；
  -是否存在明确L1 family；
  -文档来源；
  -病例文本长度；
  -不同专科。

---

## 7. equivalence operator本身缺少独立质量验证

论文将等价关系定义为gold-blind pairwise predicate，经对称化和connected-component closure形成 (L/!\sim)。形式化清楚，但方法风险仍很大：

* overmerge：将相近但不等价的疾病合并；
* undermerge：遗漏真正同义标签；
* granularity mismatch：疾病、亚型、综合征混为同类；
* transitive drift：A≈B、B≈C，但A与C并不等价；
* representative bias：选择的代表名称影响最终binding。

### 建议的人工标注实验

抽样：

* 300–500个候选pair；
* 100–150个完整clusters；
* 对transitive-only edges过采样；
* 对疾病–亚型、旧称–新称、综合征–病因对过采样。

报告：

* pairwise precision/recall/F1；
* B³ cluster precision/recall/F1；
* overmerge rate；
* undermerge rate；
* transitive-only edge error rate；
* representative-selection stability；
* 两名临床标注者的一致性。

这项分析会把“LLM做同义合并”提升为对**concept identity operator**的正式验证，显著增强方法创新性。

---

## 8. baseline数量已经足够，公平性审计比继续加方法更重要

当前主表已包含Direct CoT、CoT+RAG、flat reranking、beam、Dual-Inf、i-MedRAG、MDAgents、MAC、MEDDxAgent、self-refine、self-consistency、Medprompt、MedRAG和Chain-of-Diagnosis等共享backbone arms。继续增加普通基线的边际价值已经较低。

更可能被质疑的是：

* 各基线是否获得相同的retrieval depth；
* context token budget是否匹配；
* APHHM是否经过更多prompt/hyperparameter tuning；
* 官方方法在共享backbone上的适配是否保持原始协议；
* 各方法是否使用相同的证据文档和输出约束；
* 约90次调用是否等价于token、latency或cost预算。

### 应增加一张“fairness audit table”

| 项目                   | APHHM | strongest flat | strongest RAG | strongest agent |
| -------------------- | ----: | -------------: | ------------: | --------------: |
| Model calls          |       |                |               |                 |
| Input tokens         |       |                |               |                 |
| Output tokens        |       |                |               |                 |
| Retrieved documents  |       |                |               |                 |
| Context tokens       |       |                |               |                 |
| Wall-clock latency   |       |                |               |                 |
| Monetary cost        |       |                |               |                 |
| Prompt tuning trials |       |                |               |                 |
| Dev cases used       |       |                |               |                 |

结果不一定要证明完全等成本，而是要清楚区分：

* model-call parity；
* token parity；
* latency parity；
* monetary parity。

---

## 9. 检索语料与benchmark之间的潜在重叠必须审计

APHHM使用case-report corpora，而MCR本身来自clinical case reports。即使所有RAG方法共享索引，APHHM更强的组织与多阶段检索能力也可能更有效地利用近重复文档。

审稿人可能提出：

> Is the method retrieving the source report or a near-duplicate of the benchmark case?

### 建议四项污染审计

1. benchmark vignette与corpus文档的MinHash/lexical overlap；
2. embedding nearest-neighbor similarity分布；
3. source title、DOI、病例描述去重；
4. leave-nearest-document-out重新评估。

还可增加：

* answer-string masking；
* remove same-journal/same-source documents；
* high-overlap与low-overlap病例分层效果。

若APHHM在low-overlap子集仍有稳定增益，论文说服力会大幅提高。

---

## 10. reasoning recall不能作为belief-state机制的证据

论文报告APHHM的MCR reasoning recall最高，并将其描述为“consistent with a belief state that preserves diagnostically relevant facts”。但该指标由Gemini 2.5 Flash judge给出，尚无独立人工验证。

“consistent with”虽然不是正式因果主张，但仍容易被理解为机制证据。

### 建议

人工标注至少100个输出，评价：

* supporting finding recall；
* contradictory finding recall；
* hallucinated finding rate；
* evidence traceability；
* diagnosis-discriminative evidence precision。

报告：

* judge–human correlation；
* judge bias按方法分层；
* judge preference是否受输出长度和格式影响；
* 各方法在长度匹配后的reasoning recall。

在完成前，主文应写：

> APHHM also obtains the highest auxiliary LLM-judged reasoning-recall score; this metric is not used as evidence for explanation quality or causal state preservation.

---

# 二、最值得新增的统一指标

当前指标主要测最终答案。为了真正量化APHHM的贡献，建议增加一组与三个机制一一对应的指标。

## 1. Concept-slot utilization

[
\mathrm{UCR}@k
==============

\frac{|\pi(S_k)|}{|S_k|}.
]

其中 (S_k) 是前 (k) 个字符串输出。

对应的slot浪费率：

[
\mathrm{SSW}@k
==============

1-\mathrm{UCR}@k.
]

解释：

* UCR越高，有限输出预算覆盖的独立概念越多；
* SSW直接量化synonym fragmentation消耗了多少槽位。

应同时报告：

* 全部病例均值；
* 有synonym病例子集；
* target初始rank较低的困难病例。

---

## 2. Stage-conditional survival rates

设正确概念通过五个阶段的事件分别为 (Z_1,\dots,Z_5)。

定义：

[
p_j
===

P(Z_j=1\mid Z_1=\cdots=Z_{j-1}=1).
]

对应：

* parent-hosting rate；
* leaf-generation rate；
* local survival rate；
* global cutoff survival rate；
* binding success rate。

最终成功率可写为：

[
P(\text{success})=\prod_{j=1}^{5}p_j.
]

比较APHHM与flat/RAG baseline的 (p_j)，可直接说明性能差距究竟在哪个阶段产生。

还可以对：

[
\log P(\text{success})
======================

\sum_j\log p_j
]

做stage contribution decomposition。

---

## 3. Axis discriminability yield

[
\mathrm{ADY}
============

\frac{
#{\text{family pairs with at least one discriminative fact}}
}{
#{\text{live family pairs}}
}.
]

配套指标：

* mean discriminative facts per family pair；
* selector abstention rate；
* empty-ranking rate；
* residual-family rate；
* family balance entropy。

这些指标比“平均选择了4.94条事实”更能说明axis的几何质量。

---

## 4. State propagation fidelity

对每个被本地更新的leaf，比较local score change与global state中的实际变化：

[
\mathrm{SPF}
============

\operatorname{corr}
\left(
\Delta s_i^{\mathrm{local}},
\Delta s_i^{\mathrm{global}}
\right).
]

还应报告：

[
\mathrm{WriteBackCoverage}
==========================

\frac{
#{\text{locally updated leaves correctly reflected globally}}
}{
#{\text{locally updated leaves}}
}.
]

以及：

[
\mathrm{RankResponseRate}
=========================

P(\text{global rank changes in the expected direction}
\mid
\text{local evidence favors target}).
]

这会把write-back从一个二元开关变成可解释的状态传递机制。

---

## 5. Evaluation detachment rate

[
\mathrm{EDR}@k
==============

\frac{
#{\text{correct concept is in top-}k\text{ but unbound}}
}{
#{\text{correct concept is in top-}k}
}.
]

应对每种方法分别报告，而不是只对APHHM报告。

另可报告：

* exact-name binding；
* synonym binding；
* bridge binding；
* unresolved binding；
* method-specific emitted-name diversity。

---

## 6. Hypothesis-management efficiency

不建议只使用“accuracy per token”这种不稳定比值。更好的方法是画Pareto frontier：

横轴分别使用：

* unique concept count；
* input/output tokens；
* latency；
* monetary cost；
* model calls。

纵轴使用：

* accuracy；
* any-hit@5；
* open-MRR；
* micro-F1。

定义面积指标：

[
\mathrm{HM\text{-}AUC}
======================

\operatorname{AUC}
\bigl(
\text{performance vs. unique-concept budget}
\bigr).
]

它能够直接检验：

> APHHM是否在相同概念预算下得到更高性能，而不仅仅是生成不同数量的字符串。

---

## 7. Component Shapley attribution

在完整 (2^3) 因子实验中，对axis、concept competition和write-back计算：

[
\phi_j
======

\sum_{S\subseteq N\setminus{j}}
\frac{|S|!(|N|-|S|-1)!}{|N|!}
\left[
v(S\cup{j})-v(S)
\right].
]

同时报告interaction value。

这会给出一个非常清晰的headline：

> 在总增益中，多少来自组织、概念竞争、状态写回，以及它们的协同。

---

# 三、推荐新增的可视化

## 主文优先级最高

### Figure A：统一机制贡献waterfall

展示：

[
\text{flat}
\rightarrow +A
\rightarrow +C
\rightarrow +W
\rightarrow \text{full APHHM}
]

但顺序可能影响结果，因此最终使用：

* Shapley主效应；
* interaction contribution；
* 95% case-bootstrap CI。

这张图能够替代大量口头机制归因。

### Figure B：stage-survival funnel或alluvial diagram

对APHHM和最强baseline分别展示：

```text
All cases
→ valid L1 parent
→ target L2 leaf
→ survives local selection
→ reaches global Top-k
→ successful binding
```

每条边标记conditional survival rate。
它会把论文最独特的stage-aware insight直接变成定量证据。

### Figure C：跨数据集/跨backbone forest plot

每行显示：

* dataset；
* backbone；
* component；
* paired effect；
* 95% CI。

这比只在三个不同章节分别给单点结果更能证明机制可迁移性。

---

## 补充材料优先

### Figure D：gold-concept rank trajectory

每个病例画：

[
r_{\mathrm{recall}}
\rightarrow
r_{\mathrm{local}}
\rightarrow
r_{\mathrm{writeback}}
\rightarrow
r_{\mathrm{global}}
\rightarrow
r_{\mathrm{bound}}.
]

用：

* 细线表示病例；
* 粗线表示中位数；
* 颜色区分最终correct/incorrect。

可直接看到：

* 目标在哪里上升；
* 哪里被丢弃；
* write-back在哪些病例真正改变结果。

### Figure E：概念聚类误差图

展示：

* true merge；
* false merge；
* missed merge；
* transitive-only merge；
* representative-binding failure。

可使用cluster confusion matrix或equivalence graph案例。

### Figure F：performance–resource Pareto

同时显示：

* APHHM；
* native flat；
* 9-call proxy；
* 90-call flat；
* strongest RAG；
* strongest agent。

避免仅用“更多调用没有改善flat baseline”的单条结果支持效率叙事。

---

# 四、案例分析应怎样设计

不应只选择三个成功案例。建议使用预先定义的六类案例：

| 案例类型               | 目的                               |
| ------------------ | -------------------------------- |
| Axis rescue        | adaptive axis使正确family可区分        |
| Concept rescue     | synonym compression释放一个关键slot    |
| Write-back rescue  | local evidence将目标从低rank推到最终输出    |
| Binding failure    | 正确concept存在但mapper失败             |
| Overmerge failure  | equivalence operator错误合并相关但不等价疾病 |
| Wrong-axis failure | adaptive hierarchy本身误导后续选择       |

每个case card固定展示：

1. 关键vignette findings；
2. flat candidate list；
3. L1/L2 structure；
4. concept classes；
5. local score before/after；
6. global rank；
7. emitted name与benchmark binding；
8. baseline与APHHM最终结果；
9. earliest failed stage；
10. 专家解释。

### 防止cherry-picking

使用预先规定的选择规则：

* 最大正向差异；
* 中位数正向差异；
* 最大负向差异；
* 最常见失败类型；
* 一个overmerge；
* 一个binding failure。

补充材料应列出所有满足条件的病例，而不是仅展示最有利案例。

---

# 五、建议重构统计分析

## 1. 将primary和exploratory analysis分离

建议三个primary hypotheses：

* H1：adaptive axis–selector pipeline优于fixed taxonomy；
* H2：concept-level competition优于both-off；
* H3：write-back优于no write-back。

分别使用：

* paired exact test；
* case-level bootstrap；
* 明确的primary endpoint。

不要将case-level tests和partition-level randomization放入同一个模糊的Holm family。更合理的是：

* 每个RQ一个primary endpoint；
* RQ内进行Holm或gatekeeping；
* partition randomization和routing variants标为mechanism/exploratory analyses。

## 2. 所有headline结果报告效应量和CI

不只报告 (p)：

* absolute difference；
* relative error reduction；
* paired win/tie/loss；
* 95% CI；
* number of discordant cases。

例如：

[
\text{relative error reduction}
===============================

\frac{e_{\text{control}}-e_{\text{APHHM}}}
{e_{\text{control}}}.
]

但不要用relative improvement替代absolute effect。

## 3. 多运行与case uncertainty同时建模

若每个配置运行 (R) 次，使用两层bootstrap：

1. 重采cases；
2. 在每个case内重采runs；
3. 重新计算paired difference。

或者使用混合效应模型：

[
g(E[Y_{imr}])
=============

\beta_0+\beta^\top X_m
+u_i+v_r,
]

其中：

* (i)：case；
* (m)：method/configuration；
* (r)：run；
* (u_i)：case random effect；
* (v_r)：run/model-instance effect。

## 4. 异质性分析

不要只给平均效应。检查：

[
\Delta_i=f(
\text{candidate size},
\text{synonym density},
\text{initial rank},
\text{case difficulty},
\text{specialty},
\text{text length}
).
]

这会回答：

> APHHM在哪些病例真正有用？

这通常比增加总体平均准确率更能产生AAAI式insight。

---

# 六、对当前文字主张的红队修订

## 当前过强或易被攻击的表述

### 1. “The results show...”

建议：

> The results support the view that...

### 2. “APHHM ranks first in all six columns”

建议：

> On the three fixed mechanism-evaluation subsets, APHHM obtains the highest value in each reported column among the completed shared-backbone arms.

避免被理解为full-benchmark SOTA。

### 3. “nine tenths of an apparent recall gap...”

建议：

> In the retrospective 20-case audit, 18 cases were provisionally assigned to binding failure.

### 4. “pre-registered ±5 pp non-inferiority margin”

建议：

> pre-specified ±5 pp equivalence region

前提是确实要做equivalence testing。

### 5. reasoning recall机制解释

删除：

> consistent with a belief state that preserves diagnostically relevant facts

改为：

> This auxiliary LLM-judged metric remains to be validated independently and is not used as evidence for explanation quality.

### 6. Discussion中的“establish”

建议：

> The results support a state-management view...

---

# 七、最高收益的实验执行顺序

## Tier 0：提交前最值得完成

| 优先级 | 实验                                  | 解决的核心风险             |
| --: | ----------------------------------- | ------------------- |
|   1 | 共同数据集上的 (2^3) APHHM因子实验             | 统一方法缺乏联合机制验证        |
|   2 | axis × selector全交叉                  | RQ1因果纠缠             |
|   3 | 人工盲法stage audit                     | 18/20审计可信度          |
|   4 | human equivalence/cluster audit     | concept operator有效性 |
|   5 | write-back在第二数据集复现＋placebo refresh  | OX/decoder特异性       |
|   6 | 修正Figure 2统计术语和case-level inference | 统计审稿攻击面             |

## Tier 1：显著提高accept概率

| 实验                               | 价值                          |
| -------------------------------- | --------------------------- |
| 300–500例独立holdout或完整benchmark    | 外部有效性                       |
| 3次以上重复运行                         | 模型非确定性                      |
| 2个额外backbone                     | model-family generalization |
| token/latency/cost audit         | 公平性                         |
| corpus-overlap与leave-nearest-out | 数据污染风险                      |
| stage funnel和Shapley图            | 可解释机制贡献                     |

## Tier 2：把论文提升为更广泛AI贡献

| 实验                                | 价值                            |
| --------------------------------- | ----------------------------- |
| 非医疗开放假设任务的小规模迁移                   | 证明不是医疗专用heuristic             |
| stage-targeted intervention trial | 将error taxonomy变为可操作理论        |
| concept-budget Pareto分析           | 提出新的hypothesis-management评价范式 |
| 多数据集层次化meta-analysis              | 证明跨任务稳定机制                     |

---

# 八、最终战略判断

当前论文最不需要的是继续无限扩充baseline名单。它已经有足够广的对比面。真正决定AAAI审稿结果的将是三个问题：

1. **三项机制是否在同一个受控实验中共同成立？**
2. **stage audit和concept equivalence是否经过独立人工验证？**
3. **当前效果是否能在更大样本、第二数据集和第二backbone上复现？**

最理想的论文实证结构应改造成：

[
\boxed{
\text{Unified factorial evidence}
+
\text{stage-wise error decomposition}
+
\text{human-validated concept identity}
+
\text{independent replication}
}
]

若资源有限，最优组合是：

* 一个共同数据集上的8格因子实验；
* 一个axis × selector交叉实验；
* 对所有错误的双人盲法stage audit；
* 300–500例独立复现；
* 一张stage funnel；
* 一张Shapley contribution figure；
* 一组正例与负例并存的case cards。

完成这些后，论文的核心叙事就可以从：

> APHHM在三个困难诊断子集上取得较好结果，并有若干组件消融。

升级为：

> **APHHM揭示并实证分解了开放假设管理中的三种跨阶段失真机制，证明这些机制如何独立及交互地影响候选生存、概念预算利用和最终决策。**

后者更能最大化学术创新性、说服力和可迁移insight，同时显著降低“复杂工程pipeline”“数据集特例”“评价接口偶然性”和“统计过度解释”等审稿风险。

[1]: https://aaai.org/conference/aaai/aaai-27/main-technical-track-call/ "AAAI-27 Main Technical Track Call - AAAI"
