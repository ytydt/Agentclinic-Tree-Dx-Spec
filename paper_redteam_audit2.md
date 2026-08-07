## 红队结论

以苛刻 AAAI 审稿人的视角，当前稿件更接近 **Weak Reject / Borderline**：

- 系统层面的结果较强；
- “cross-stage alignment”叙事具有潜在创新性；
- 但三项机制贡献尚未被统一、独立地识别；
- 可复现性材料是当前最现实的拒稿风险。

AAAI-27 明确按贡献重要性与新颖性、论证可靠性、评测质量、清晰度和可复现性评分，并偏好能够超越单一子领域、提出新问题或方向的工作。

## 一、最薄弱的论证

| 优先级 | 审稿人攻击 | 当前证据问题 | 风险 |
|---|---|---|---|
| 1 | “三个组件是否真的分别有效？” | RQ1、RQ2、RQ3 分别只在 DA、MCR、OX 隔离，没有统一 factorial 或跨数据集复制 | 极高 |
| 2 | “结果是否只是这 100 个顺序病例？” | 使用固定 first-100，且每配置只有一次运行 | 极高 |
| 3 | “case-adaptive axis 还是 selector 崩溃造成增益？” | random axis 导致 45 个 empty rankings；axis 与 selector cascade 强耦合 | 极高 |
| 4 | “semantic compression 的显著性是否能泛化到病例？” | \(p=0.015\) 是固定病例上的 partition randomization，不是 case-level sampling inference | 高 |
| 5 | “write-back 是否只是修复一个刻意保留 stale scores 的残缺基线？” | 只在 OX 验证，缺少 shuffled update、flat recomputation 等替代控制 | 高 |
| 6 | “总体领先是否有统计可靠性？” | 完整基线表只有点估计，没有 APHHM–strongest baseline 的配对区间 | 高 |
| 7 | “错误分解是否主观、选择性？” | stage audit 仅覆盖 20 个 DA misses，且为 retrospective audit | 高 |
| 8 | “代码和结果能否复现？” | checklist 明确回答 preprocessing code=no、experiment code=no、hardware=no，seed/hyperparameters=partial | 极高 |

相关文本分别见：

- [单次运行](/codex_workspace/94530029-2500-4540-a192-0e9f08b7e8a7/AuthorKit27/paper/main.tex:256)
- [固定 100 例与证据边界](/codex_workspace/94530029-2500-4540-a192-0e9f08b7e8a7/AuthorKit27/paper/main.tex:270)
- [axis pipeline effect](/codex_workspace/94530029-2500-4540-a192-0e9f08b7e8a7/AuthorKit27/paper/main.tex:325)
- [partition-level 证据](/codex_workspace/94530029-2500-4540-a192-0e9f08b7e8a7/AuthorKit27/paper/main.tex:390)
- [仅 OX 的 write-back 归因](/codex_workspace/94530029-2500-4540-a192-0e9f08b7e8a7/AuthorKit27/paper/main.tex:426)
- [20 例 retrospective audit](/codex_workspace/94530029-2500-4540-a192-0e9f08b7e8a7/AuthorKit27/paper/main.tex:436)
- [复现清单缺口](/codex_workspace/94530029-2500-4540-a192-0e9f08b7e8a7/AuthorKit27/ReproducibilityChecklist.tex:181)

AAAI 明确要求评审根据投稿时实际提供的代码、数据和文档评估复现性；“接受后发布”不能算作复现证据。

## 二、必须优先补充的实验

### P0-1：独立样本复制

不要继续在当前 first-100 上增加更多后验分析。应冻结假设、指标和阈值，在独立病例或完整 benchmark 上重新运行：

- DA：完整数据，或至少新增 300 例；
- MCR compression：至少 300 个可扰动病例，保守目标 450；
- OX write-back：至少 250 例，或完整集合；
- 每个配置至少 3 次独立运行；高风险主结果建议 5 次。

主要报告：

- 配对效应及 95% CI；
- APHHM 对最强共享 backbone baseline 的配对比较；
- case bootstrap 与 run-level variability；
- 预注册的三项 primary contrasts 使用 Holm；
- 其余 subgroup/diagnostic comparisons 使用 FDR。

### P0-2：axis × selector factorial

至少运行：

| Axis | Selector |
|---|---|
| Case-adaptive | Candidate-relative |
| Case-adaptive | Salience |
| Fixed ICD | Candidate-relative |
| Fixed ICD | Salience |
| Random matched | Candidate-relative |
| Random matched | Salience |

再增加一个不会因 abstention 产生空输出的 neutral/fallback selector。

这样才能估计：

- axis 主效应；
- selector 主效应；
- axis×selector interaction；
- 排除“random baseline 因接口不兼容而被人为破坏”。

建议用病例聚类 bootstrap 计算 factorial contrasts，而不是只比较六个独立点估计。

### P0-3：compression 的病例级确认

需要独立样本上的：

- semantic merge；
- count-matched blind merge；
- no compression；
- unconditional merge；
- human concept-equivalence reference。

对 equivalence classes 报告：

- pairwise precision/recall/F1；
- over-merge rate；
- under-merge rate；
- B-cubed F1；
- candidate-slot efficiency；
- any-hit@5 与 open-MRR@5 的病例级 bootstrap CI。

partition permutation 可以继续保留，但只能作为“语义分区敏感性”证据，不能代替病例泛化。

### P0-4：write-back 的非平凡控制

除现有 no-write-back 外，加入：

1. **Shuffled write-back**：写入相同分布但跨候选打乱的分数；
2. **Random-evidence write-back**：更新数量一致但证据随机；
3. **Flat recomputation**：使用同一证据直接全局重排，不经过层级状态；
4. **Local-only update**：本地更新但不进入全局状态；
5. **Copy-only control**：复制字段但不改变数值。

如果 APHHM 只胜 stale-state baseline，而不胜 flat recomputation，创新更像工程修复；如果仍显著领先，才真正支持“共享层级 belief state”的机制主张。

### P0-5：统一 \(2^3\) 组件实验

如果预算允许，在至少两个数据集上运行：

\[
\text{adaptive axis}\times
\text{semantic competition}\times
\text{write-back}.
\]

八个配置可估计：

- 三个主效应；
- 两两 interaction；
- 三阶 interaction；
- 每例 component Shapley contribution。

这是最有可能把论文从“强系统”升级为“有一般性 insight 的 AAAI 方法论文”的实验。

## 三、近似功效分析

以下根据当前汇总效应和假定配对 discordance 计算；正式设计必须使用病例级输出重新估计。

| 对比 | 目标效应 | 80% power | 90% power | 建议 |
|---|---:|---:|---:|---:|
| Axis residual effect | 0.135 | 99 | 132 | ≥200 |
| Semantic vs blind | 0.097 | 159–326 | 213–437 | ≥300，保守 450 |
| Write-back replication | 0.040 | 190 | 254 | ≥250 |
| APHHM vs DA strongest baseline | 0.090 | 138–332 | 185–444 | 使用完整 DA |

当前 write-back 的 \(+0.075\) 本身功效较强；扩大样本的目的不是再次证明巨大效应，而是检验其在新病例、其他数据集和更强控制下是否仍有约 \(0.04\) 的实际增益。

## 四、建议增设的专门指标

### 1. Concept Slot Efficiency

\[
\mathrm{CSE@}k=\frac{|\pi(S_k)|}{|S_k|}.
\]

衡量输出槽位中有多少对应不同概念。同步报告：

\[
\mathrm{RedundantSlotRate@}k=1-\mathrm{CSE@}k.
\]

这比“候选减少 56.5%”更直接对应 APHHM 的理论对象。

### 2. Stage Survival Profile

依次统计目标在各阶段的存活：

\[
R_0:\text{recalled}\rightarrow
R_1:\text{parent exists}\rightarrow
R_2:\text{leaf exists}\rightarrow
R_3:\text{local frontier}\rightarrow
R_4:\text{global Top-}k\rightarrow
R_5:\text{bound}.
\]

定义阶段 hazard：

\[
h_s=\frac{N_{s-1}-N_s}{N_{s-1}}.
\]

这能把目前的错误 taxonomy 转化为真正可量化、可比较的诊断工具。

### 3. Counterfactual Repair Value

仅用于离线审计：

\[
\mathrm{CRV}_s=
\mathrm{Score}(\text{oracle repair at stage }s)
-\mathrm{Score}(\text{observed}).
\]

它回答“若只修复 parent、leaf、local pruning、global ranking 或 binding，最多能提升多少”，比错误计数更具行动意义。

### 4. State Transfer Fidelity

对所有因证据更新而发生局部次序变化的候选对，计算其变化是否进入全局状态：

\[
\mathrm{STF}=
\frac{\#\text{globally preserved local order changes}}
{\#\text{local order changes}}.
\]

另报 gold concept 的 rank gain、Kendall rank agreement，以及“local improvement but global loss”的 violation rate。

### 5. Axis Quality

建议报告：

- Parent Accommodation Rate；
- orphan candidate rate；
- cross-family synonym split rate；
- selector abstention rate；
- discriminative evidence yield；
- average selected facts / evidence budget；
- clinician-rated family exclusivity、coverage、discriminability。

不要把这些随意加权成一个总分；用三维 alignment vector 更可信：

\[
(\mathrm{CSE},\ \mathrm{STF},\ \mathrm{BindingRate}).
\]

## 五、最有价值的可视化

1. **Stage-survival Sankey / waterfall**  
   对比 APHHM、flat rerank、fixed axis，展示候选在哪一阶段丢失。

2. **Mechanism forest plot**  
   每个数据集分别展示 axis、compression、write-back 的效应及 95% CI；不要只画柱状图。

3. **Factorial interaction plot**  
   axis×selector、write-back×budget，直接显示 interaction，而非六张独立表。

4. **Compute Pareto frontier**  
   横轴 token/cost/latency，纵轴任务指标；加入 2、5、10 trajectory flat controls 和 APHHM。

5. **Concept quotient diagnostic**  
   横轴 CSE@5，纵轴任务增益，颜色标注 over-/under-merge rate。

6. **Subgroup heatmap**  
   按 synonym crowding、候选数、病例长度、专科、疾病频率、mapper ambiguity 分层展示 paired effect。

正文最值得保留的是“stage survival + forest plot”的双面板图；其余可放补充材料。

## 六、案例分析应如何避免 cherry-picking

预先规定选例规则：

- 每个机制的 median positive-effect case；
- largest positive-effect case；
- largest negative-effect case；
- 一个 binding failure；
- 一个 transitive-closure over-merge failure。

每个案例固定展示：

- 原始候选及 equivalence classes；
- L1 axis；
- 被选择的证据；
- 各阶段目标 rank；
- local score delta；
- write-back 前后 global rank；
- 最终 failure code。

至少两名临床标注者盲评 family suitability、equivalence 与 failure stage，并报告 Cohen’s \(\kappa\) 或 prevalence 不平衡时的 Gwet AC1。

## 七、新颖性风险

“hierarchy”“evidence tree”“case-adaptive multi-agent”和“multi-source differential diagnosis”本身已经被近期工作覆盖：Tree-of-Reasoning 使用 evidence tree，CAMP 使用 case-adaptive specialist panels，MultiDx 进行多来源证据整合和 differential diagnosis。

因此最安全的新颖性定位不是：

> 我们首次使用 hierarchy 或 case adaptation。

而是：

> APHHM 首次将 concept identity、state propagation 和 evaluation binding 统一为可审计的 cross-stage invariants，并通过 operator-sensitive endpoints、factorial interventions 与 stage-attributable errors 定量验证这些 invariants。

上述专门指标和统一 factorial 是让这一定位真正成立的关键。

