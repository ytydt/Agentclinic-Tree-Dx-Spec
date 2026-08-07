## 总体结论

以严格 AAAI 主赛道审稿人的视角，`main(9)` 当前大致处于 **Borderline / Weak Reject**：选题与核心 insight 是成立的，RQ3 的状态回写实验尤其有说服力；但数字一致性、样本外推、数据污染排除和机制归因仍存在足以在第一阶段触发拒稿的漏洞。

最危险的不是“绝对性能仍然不高”。当前版本已经正确删除了这种自我削弱式表述。真正的拒稿路径会是：

> APHHM 是多个合理工程组件的组合；作者只在每个数据集上验证其中一个组件，使用固定连续 100 例和单次运行，而且部分统计数字互相矛盾。因此结果尚不足以证明一个可泛化的“cross-stage consistency”方法论。

这恰好击中 AAAI-27 强调的 substantive novelty、soundness、clarity 和 reproducibility；AAAI 还明确偏好能超越单一窄领域、指明新研究方向的工作。[AAAI-27 评审标准](https://aaai.org/conference/aaai/aaai-27/main-technical-track-call/)

---

# 一、必须立即处理的 P0 问题

## 1. 两处数字不可能同时成立

| 位置                 | 当前数字                                                                     | 数学核验                                                                      | 风险                         |
| ------------------ | ------------------------------------------------------------------------ | ------------------------------------------------------------------------- | -------------------------- |
| Table 4 / Sec. 6.3 | MCR `n=98`，Full `0.50`，Neither `0.42`；同时写 `10/0` discordant、差异 `+10.2pp` | `10/98=10.2pp`。若 Full 为 `49/98=0.50`，Neither 必须是 `39/98=0.40`，不可能是 `0.42` | 摘要、正文、表格和 Figure 2 至少有一处错误 |
| Table 2            | DA `@1=0.71, @2=0.78, MRR@2=0.748`                                       | 对 100 个二元病例，MRR@2 应为 (0.71+0.5(0.78-0.71)=0.745)                          | 暗示分母不是 100、舍入错误或 MRR 定义错误  |

必须从逐例预测重新生成所有表格，不要人工修一个数字。建议在补充材料加入每个比较的四格表：

[
(n_{11},n_{10},n_{01},n_{00}),\quad
\Delta,\quad 95%,CI,\quad p
]

另外，Figure 3 使用 `0.72→0.42`，而主结果是 `0.71`。正文虽提到这是 earlier judge configuration，但图注必须直接说明，否则仍像版本残留。

## 2. Figure 2 的“pre-registered ±5pp non-inferiority”目前站不住

正文没有给出：

* 时间戳明确的预注册文件；
* 为什么临床或方法学上选择 5pp；
* 标准非劣检验；
* 独立确认样本。

更关键的是，当前区间是在固定 discordant-pair 数量后计算的条件区间。discordant pairs 很少时，它会显得异常狭窄，却忽略了病例抽样对“不一致率”本身的不确定性。因此不能据此声称：

> narrow bounds follow from the paired design rather than limited power.

处理原则：

* 若确实有结果产生前的注册文件：在 supplement 中提供不可修改的时间戳证据和 margin rationale。
* 若没有：删除 `pre-registered` 和 `non-inferiority`，改为 `illustrative ±5pp equivalence region`，所有结论降为 exploratory。
* 使用无条件 matched-pair CI 或病例级 paired bootstrap。
* 若要正式证明 ±5pp 非劣，在 discordance rate 为 0.10–0.20 时，通常需要约 250–500 例，而非 98 例。

## 3. 检索语料污染是潜在的一票否决点

DA 和 MCR 均源于病例报告，而 APHHM 又从 case-report corpora 检索。稿件没有说明：

* benchmark 原始病例对应的文章是否从检索库排除；
* 是否存在同一病例、摘要或近重复文本；
* MCR 的 clinician reasoning 是否可能从原始病例文章直接检索到。

即使所有方法共享语料，这仍会严重影响“reasoning recall”和结构增益的解释。至少应完成：

1. DOI/PMCID/article-level leave-one-source-out；
2. MinHash/embedding 近重复检测；
3. 报告 exact-source hit rate；
4. 对比原检索库与去污染检索库的配对性能；
5. 按病例发布时间或潜在预训练暴露分层。

若无法完成全部实验，至少在 supplement 提供每个病例的 source ID、排除规则和检索 top passages。

## 4. 当前不是“四个数据集”，而是三个固定连续 100 例子集

公开数据规模大约为：

* DiagnosisArena：1,113 例，当前只用约 9%；[ACL 论文](https://aclanthology.org/2026.findings-acl.151.pdf)
* MCR：897 个测试病例，当前约 11%；[MedCaseReasoning](https://arxiv.org/html/2505.11733v1)
* Open-XDDx：570 例，当前约 18%。[Open-XDDx](https://www.nature.com/articles/s44401-025-00015-6)

“fixed sequential”不能支持常规总体推断：连续顺序可能与文章、专科、难度或时间相关，而且病例 bootstrap 不能弥补非随机取样。

优先方案：

* 最佳：在完整 DA/MCR/OX 上至少运行 Full、最强 baseline 和关键 ablation。
* 预算受限：每数据集锁定 300 例分层随机确认集，按专科、罕见度、病例来源和难度分层。
* 原 100 例应降为 development/mechanism-discovery set，不再作为唯一确认集。

---

# 二、现有证据强度的重新评级

| 主张                           | 当前证据                                                                | 审稿判断                                                                         |
| ---------------------------- | ------------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| Case-adaptive axis 有效        | DA adaptive vs random：`40/6`，Δ=+34pp；vs fixed：`25/5`，Δ=+20pp        | 效应很强，但主要伴随 nonempty ranking 从 55%/89% 升至 99%，尚不能区分“轴质量”与“selector 是否失效”      |
| Concept equivalence 有效       | 压缩 56.5%，盲合并较差，关闭两个执行点性能下降                                          | 中等；Acc@1 本来就被 rank-1 invariance 保证不变，且 equivalence predicate 未经人工验证，核心数字还有矛盾 |
| Score write-back 有效          | OX 2×2：ΔF1=+0.075，CI `[0.036,0.113]`；预算效应 ≤0.008，interaction=-0.001 | 当前最强证据，设计清晰；但只在 OX 和一个 backbone 上直接验证                                        |
| Bounded decoder 是核心贡献        | closed panel 0.651 vs pool 0.610 vs direct 0.593                    | 有支持，但不是独立 RQ，且仅在 OX；应新增 RQ4，否则降为实现选择                                         |
| Evaluation consistency 是普遍问题 | 20 个 apparent misses 中 18 个归为 binding failure                       | 有价值但高度回顾性；只分析选出的 20 例，90% 的 Wilson 95% CI 约为 70%–97%，且缺少双人标注与全样本分母           |
| APHHM 优于大量 baselines         | Table 2 六列第一                                                        | 只有点估计，无 strongest-baseline 配对 CI/检验；基线适配忠实度和计算曲线不足                           |
| 结构优于更多推理量                    | Flat rerank×10 约 90 calls 仍较弱                                       | 尚不充分；若十轨迹在 temperature 0 下高度重复，RRF 控制可能只是浪费调用量的弱控制                           |

---

# 三、最高回报的扩展实验

## 1. 拆开 axis 与 selector：这是当前最薄弱的因果归因

当前对 nonempty cases 的条件分析属于对处理后变量进行条件化，不能直接解释为 mediation。建议做真正的 factorial：

| Axis                         | Selector           |
| ---------------------------- | ------------------ |
| case-adaptive                | candidate-relative |
| case-adaptive                | salience           |
| fixed taxonomy               | candidate-relative |
| fixed taxonomy               | salience           |
| case-shuffled plausible axis | 两种 selector        |

“case-shuffled plausible axis”比完全随机轴更强：从另一病例借用结构合理的轴，同时匹配 family count、family size、leaf budget，并保证有合法输出。这样可以避免 random axis 因 45% 空 ranking 而成为过弱对照。

应增加 axis 本身的前置指标：

* Target-family coverage；
* valid/nonempty ranking rate；
* residual-family load；
* sibling exclusivity；
* evidence separability；
* 跨运行 adjusted Rand index；
* 人工 axis quality 评分。

## 2. 不要再堆普通 agent baseline，增加三种“结构归因控制”

最重要的不是再加入五个名字，而是：

1. **Flat + same candidate pool + same final arbiter**
   只去掉 hierarchy，其他组件相同。

2. **Flat stateful control**
   保留 evidence selector 和 score write-back，但用平面 registry，检验收益究竟来自 hierarchy 还是下游状态更新。

3. **Best-of-N + same judge**
   十条独立轨迹先汇总候选，再使用 APHHM 同一个最终 judge，而不是仅用 RRF。

同时报告十轨迹的 unique-concept yield、pairwise Jaccard 和 rank correlation。若轨迹几乎相同，90-call 对照没有解释力。

## 3. 建立 APHHM 三组件的联合归因

在锁定确认集上运行：

[
\text{Axis}\times\text{Equivalence}\times\text{WriteBack}
]

完整 (2^3) 设计可计算每个组件及交互项；若预算不足，至少运行：

* Full；
* −Axis；
* −Equivalence；
* −WriteBack；
* −Axis−Equivalence−WriteBack；
* Flat stateful control。

利用逐病例 coalition performance 计算 paired Shapley contribution，可以回答审稿人最关心的问题：

> APHHM 的增益到底来自哪个组件？这些组件是互补、替代，还是只有组合后有效？

## 4. 扩展 score write-back，而不是只再跑一次

把证据预算从两个点扩为：

[
B_{\text{evid}}\in{0,2,4,6,8,12}
]

绘制 write-back on/off 的 dose-response curve。至少在 DA 或 MCR 上复制一次 write-back 对照，证明它不是 OX closed-panel decoder 的特性。

还应验证：

* 两臂本地阶段使用完全相同的证据；
* 差别仅在 global decoder 读取 (B_t) 还是 (B_{t+1})；
* prompt/token 长度差异；
* 本地排序变化是否真正传递到全局排序。

## 5. 人工验证两个 LLM 评估器

至少抽取：

* 200–300 个 equivalence candidate pairs；
* 100 个 concept clusters；
* 150–200 个 case–reasoning-fact 对；
* 全部 stage-audit 异常病例。

由两名独立标注者判断，再报告 agreement、precision/recall/F1、Gwet AC1 或 Cohen’s (\kappa)，分歧由第三人裁决。重点诊断：

* 同义词 vs 上下位病种；
* syndrome vs etiologic diagnosis；
* disease vs subtype；
* connected-component chaining 造成的 false merge；
* reasoning judge 是否偏爱更长输出。

---

# 四、统计分析应如何重构

1. **统计单位始终是病例。**
   200 次随机 partition、多个 seed 和多条轨迹都是病例内重复，不能被当作独立样本扩大 (n)。

2. **三个确认性主检验即可：**

   * RQ1：adaptive vs case-shuffled plausible axis；
   * RQ2：semantic equivalence vs strongest count/ontology-matched control；
   * RQ3：write-back vs no write-back at fixed budget。

   三者用 Holm 校正；其余标记 exploratory，不要临时选择“四个 contemporaneous contrasts”。

3. **二元终点：** paired McNemar exact test + 无条件 matched-pair 95% CI。
   **MRR/F1：** paired case bootstrap 或 paired randomization；跨 seed 时用 hierarchical bootstrap。

4. **至少 3 次重复运行，关键比较 5 次。**
   temperature 0 不等于 API 完全确定；Gemini judge、服务端模型更新和检索排序仍可能波动。

5. **Table 2 必须增加 strongest-baseline 配对差值与 CI。**
   现在 DA +9pp 是否显著，单靠两个点估计无法判断；需要逐病例 discordance。

6. **MCR 的两个未共同评分病例必须解释。**
   主分析采用 intention-to-evaluate，把接口失败计为错误；同时给 complete-case sensitivity analysis。

7. **不要将 nonempty 条件结果解释为因果中介。**
   更好的方法是为所有轴提供固定 fallback，消除空输出；或用正式的两阶段/中介模型。

---

# 五、建议新增的 APHHM 专属指标

不建议创造大量复杂综合分数。下面五个足以把贡献讲清楚。

| 指标                              | 定义                                                                             | 对应贡献                                |    |       |    |                |
| ------------------------------- | ------------------------------------------------------------------------------ | ----------------------------------- | -- | ----- | -- | -------------- |
| Recalled-to-Scored Yield@k      | (\frac{#{y\text{ recalled and finally bound in top-}k}}{#{y\text{ recalled}}}) | 衡量 APHHM 把 recall 转化为可计分决策的能力       |    |       |    |                |
| Stage Retention (R_s)           | (\frac{\sum_i z_{i,s+1}}{\sum_i z_{i,s}})                                      | 定位 L1、L2、local、global、binding 各阶段损失 |    |       |    |                |
| Duplicate Budget Waste@k        | (1-\frac{                                                                      | \pi(P_i^k)                          | }{ | P_i^k | }) | 量化同义字符串消耗的决策预算 |
| Local-to-Global Update Transfer | 本地 evidence 改变排序后，全局排序按同方向变化的比例                                                | 直接量化 write-back 是否被下游消费             |    |       |    |                |
| Binding Gap Rate                | native interface 判错但固定 ontology/human matcher 判对的比例                            | 将模型错误与评测接口错误分开                      |    |       |    |                |

另以 performance–unique-concept-budget 曲线及其 AUC 表达压缩效率，比“减少 56.5% 且准确率不降”更全面。

---

# 六、最值得加入或替换的图

1. **用全样本 stage waterfall/alluvial 替换当前 Figure 3。**
   从 100% 病例依次展示：

   [
   \text{L1 host}\rightarrow\text{L2 target}\rightarrow
   \text{local survival}\rightarrow\text{global top-}k
   \rightarrow\text{binding}
   ]

   APHHM、Flat stateful 和 strongest baseline 并列。不要只画选出的 20 个 apparent misses。

2. **将 Figure 2 改为标准 forest plot。**
   显示点估计、无条件 95% CI、病例数和 discordant pairs；删除未经证实的 pre-registered/non-inferiority 表述。

3. **Compute–performance Pareto 图。**
   横轴分别报告 calls、tokens、cost；纵轴为各数据集原生指标。画 0.5×、1×、1.5× 预算曲线，而不是只比较一个约 90-call 点。

4. **Component-attribution heatmap/forest plot。**
   行为 Axis、Equivalence、Write-back 及交互，列为数据集/backbone。

5. **Concept-budget curve。**
   横轴为 unique concept budget，纵轴为 any-hit@k/MRR/accuracy；semantic、lexical、ontology、blind merge 四条曲线。

Figure 1 的符号错误已经修正，`L/\sim` 和 APHHM 名称正确；但内部字号仍偏小，可删减 stage 内部示例文字并放大核心状态流。

---

# 七、案例分析应包含成功与失败，而不是只展示漂亮案例

按预先定义的 error strata 随机选取，每类至少一例：

1. **Axis rescue**：固定 taxonomy 混合了不可比较疾病；adaptive axis 产生可分辨 siblings。
2. **Equivalence rescue**：Flat Top-5 被多个同义词占据，quotient 后正确替代病种进入 Top-5。
3. **Write-back rescue**：局部证据已使 A 超过 B，但 stale decoder 仍输出 B；回写后纠正。
4. **Binding-only failure**：正确概念已在输出中，native mapper 因名称变体判错。
5. **APHHM harm case**：错误 axis、上下位病种误合并或 synonym chain 导致正确病种被压缩。
6. **Unrecoverable case**：候选生成阶段完全缺失目标，说明 APHHM 的边界。

每例统一展示：

* vignette 中使用的证据 span；
* flat candidates；
* L1/L2 结构；
* equivalence graph；
* local score before/after；
* global rank；
* emitted string 与 canonical binding；
* Full 和相关 ablation 的反事实输出；
* 人工评审结论。

失败案例非常重要，它能把论文从“系统展示”提升为“机制研究”。

---

# 八、创新性叙事的最佳收束方式

不要把创新写成“hierarchy + de-duplication + write-back + decoder”的组件清单。更有 AAAI 味道的中心命题是：

> Multi-stage open-ended reasoning requires an alignment contract: downstream operations must be invariant to synonymous surface forms, consume the latest evidence-conditioned state, and expose outputs through a concept-consistent evaluation map.

可进一步形式化：

* concept operation 应在商空间 (L/\sim) 上定义；
* transition 与 canonicalization 应近似交换；
* decoder 必须读取 (B_{t+1})，而非 stale (B_t)；
* benchmark binder 应能因子化为 (m=\bar m\circ\pi)，即同一等价类的代表不改变评分。

这样，APHHM 是满足一组跨阶段契约的实例，而不是若干 prompt trick 的集合。

同时需要正面区分最接近的工作：

* [AgentAuditor](https://arxiv.org/html/2602.09341v1) 已经使用 semantic deduplication、reasoning tree 和 localized evidence audit；
* [MoBayes](https://arxiv.org/html/2604.20022v3) 已明确维护外部 belief state 并进行 evidence update；
* 同期的 [AegisDx](https://arxiv.org/html/2607.08038v1) 已在多 backbone、专科与 physician evaluation 上验证分阶段诊断框架。

APHHM 的差异应明确为：

> 对开放疾病候选空间的 case-adaptive coordinate system、concept quotient、local-to-global state contract，以及 evaluation-binding diagnosis。

`bounded decoding` 若不补独立 RQ，建议降为实现机制；否则会稀释最核心的三项创新。

---

# 九、当前最现实的提交优先级

AAAI-27 主稿截止已是 2026 年 7 月 28 日，supplement/code 截止为 7 月 31 日；若该版本已经提交，不应再替换主稿。[AAAI-27 提交时间与修改规则](https://aaai.org/conference/aaai/aaai-27/submission-instructions/)

在剩余补充材料窗口内，最高优先级依次是：

1. 重新生成逐例 contingency tables，解释所有数字冲突；
2. 提供精确 subset IDs、数据版本/commit、两例 missingness；
3. 上传 prompts、candidate lists、equivalence graphs、stage traces 和原始输出；
4. 增加 source-overlap/leave-one-article-out 污染审计；
5. 增加 calls/tokens/cost/latency 表及三者相关性；既然现有日志显示预算口径近线性，就不应继续写成 future work；
6. 若确有预注册，提供证据；否则不要在补充材料继续强化该主张；
7. 明确 Flat×10 的轨迹多样性及其与 APHHM 使用同一模型池和最终裁决器的程度。

AAAI 明确说明主稿必须自包含，审稿人没有义务阅读 supplement，但复现材料会影响最终决定。[AAAI-27 Supplementary Material 规则](https://aaai.org/conference/aaai/aaai-27/supplementary-material/)

最关键的判断是：**不要再用资源堆更多普通 baseline。先修复数字可信度、污染排除、独立样本和结构归因。** 这四项完成后，本文最有机会从“复杂但有效的医疗 pipeline”上升为“具有一般 AI 意义的跨阶段假设一致性方法”。
