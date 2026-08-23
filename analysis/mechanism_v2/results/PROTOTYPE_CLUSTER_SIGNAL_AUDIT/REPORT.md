# 症状集群信号：跨原型与 task 目标决策报告

执行日期：2026-08-22  
零调用审计：`analysis/mechanism_v2/prototype_cluster_signal_audit.py`  
机读结果：[`audit.json`](audit.json)  
关联解剖：[`../CLUSTER_SIGNAL_ANATOMY/REPORT.md`](../CLUSTER_SIGNAL_ANATOMY/REPORT.md)

## 0. 决策

**把“症状集群作为通用生成/排序机制”暂时搁置。**

它不应再直接移植到 MultiStance、Collapse3c、Forest 或 IMPC 的主诊断链。现有证据不是
“还没找到正确 prompt”，而是：

1. 集群计数比各原型已有选择器更粗；
2. Forest/IMPC 已通过 support 数、多视图数和 `score_logit` 吸收了最接近的代理；
3. MCR Prompt-7 与 clinical-complete 高度耦合，换 task 尺子不会救活已关闭路线；
4. DA mapper task 与临床完整性松耦合，确实可能出现 task 增益，但最合理入口是
   **投影层/K 输出层**，不是诊断生成层。该方向只能另立“DA projection”方案，
   且不得声称为诊断能力改进。

保留两项低成本工作：

- **推荐 cheap gate：** DA 旧链 Top-2→mapper 中，第二候选只有在得到正交/多视图证据时
  才进入 mapper；用冻结 mapper records 做零调用 gain/loss 审计。
- **研究性备选：** IMPC 的 `n_views` 是跨原型代理中唯一接近收支平衡的量
  （相对冻结选择器 13 gain / 16 loss，净 −3），但它是“跨医生共识”而非真正症状集群；
  只值得做新的未见数据 cheap gate，不值得直接在线。

## 1. 跨原型直接审计（MCR strict）

群体为 MCR 400 例，clinical endpoint 为冻结三模型面板敏感性，不是人工根真值。
Collapse3c 使用真实 `fact_id → correlation_group/specificity`；
Forest/IMPC 没有相关组或 specificity，只能用“不同引用跨度”和“generator views”作代理，
因此跨系统数值不可解释为同一构念。

| 原型 | 代理排序 top-1 / 池可达 | 生成顺序 | 冻结选择器 | 代理相对冻结选择器 gain/loss | 净值 |
|---|---:|---:|---:|---:|---:|
| Collapse3c：高特异相关组数 | 0.5621 | 0.5948 | **0.6993** | 4 / 25 | **−21** |
| Forest：不同引用跨度 | 0.4928 | 0.5362 | **0.6739** | 5 / 30 | **−25** |
| Forest：多视图数 | 0.5870 | 0.5362 | **0.6739** | 7 / 19 | **−12** |
| IMPC：不同引用跨度 | 0.4615 | 0.5175 | **0.5944** | 5 / 24 | **−19** |
| IMPC：多视图数 | 0.5734 | 0.5175 | **0.5944** | 13 / 16 | **−3** |

结论不是“代理无信息”。例如 Forest/IMPC 的多视图数相对**生成顺序**有增益，
但相对真正要替代的**冻结选择器**仍为负；这恰好说明该信息已经进入
`score_logit` 和 Mosaic selector。以集群规则覆盖选择器只会降级。

### 1.1 Collapse3c

- 技术上最容易接入：已有 `correlation_group` 和 `specificity`。
- 但真实高特异组排序相对冻结 selector **净 −21**。
- MCR strict 与 task 上 Collapse3c 已是三者最强或接近最强，继续加集群约束的上行空间小，
  破坏现有 0.6993 转化的风险大。
- **判定：不推进。**

### 1.2 Forest

- 无相关组 schema；`score_logit` 已奖励 support 数、views 和 axes。
- 不同跨度净 −25；多视图净 −12。
- Forest 在 DA 旧 mapper task 上领先（63.75%），但没有证据表明领先来自症状集群；
  它更可能来自多视图候选覆盖与 option projection。
- **判定：不移植 correlation-group/C4；若优化 DA task，保留 Forest 为基线。**

### 1.3 IMPC

- 无相关组 schema；多医生 views 最接近“独立证据来源”。
- `n_views` 相对生成顺序有明显正信息，但相对冻结 selector 仍为 **13 gain / 16 loss**。
- 这条 −3 是唯一接近收支平衡的结果，但 IMPC 的 MCR strict/task 绝对表现均低于
  Collapse3c，且 views 是医生共识而非症状合取。
- **判定：只保留新数据上的离线 gate，不直接在线。**

## 2. DA task 有两个不同 estimand

仓库内“DA task”不能只报一个名字：

### 2.1 旧发表链：Top-2 free-text → Llama typed mapper → option@K

- 实现：`scripts/paper/baseline_mapper_score.py`
- 输入为两个按序诊断叶；输出 `option_top1`、`option_top2`、MRR。
- 三原型 400 例：
  - Forest 63.75%
  - Collapse3c 63.00%
  - IMPC 62.50%
  - MultiStance 61.75%

该链允许第二诊断和 option relation 改写结果。E14x 的 placebo 已显示：
18 次 option flip 中 **8 次 champion 文本完全相同**，且有临床错误诊断被 mapper 判对。
所以它适合作为 benchmark interface 指标，不适合作为生成器或临床机制的反馈。

### 2.2 正规迁移链：单 Top-1 → Gemini projection → Acc@N（N=4）

- 实现：`corelift_evaluate.py`
- CoreLift 五臂为 22.5%–31.0%，不是旧链的 60%+。
- A1 多视图相对 A0：**+6.0pp task**，同时 C∪P +6.5pp；
- B1 纵向补全相对 A3：**+5.5pp task**，但 modifier 幻觉门失败。

这条证据支持的是“DA task 会奖励多视图 compatible coverage / 选项投影”，
不是“症状集群计数会提高 task”。

## 3. 换成 task 目标后，结论如何变化

### 3.1 MCR Prompt-7：基本不变

- MCR task 对 clinical-complete 的 PPV 80.19%–88.50%，sensitivity 91.84%–96.77%。
- MultiStance 冻结复用中 complete champion → task **87/87 正确**；
  非 complete champion 只有 15/211（7.1%）task 正确。
- 三原型 task：Collapse3c 29.25%、Forest 26.50%、IMPC 24.25%，
  与 strict 的方向基本一致。

因此 G1 丢 complete recall 的问题不会因换成 Prompt-7 而消失。
**MCR 上应继续搁置。**

### 3.2 DA mapper@K：情况不同，但它是投影问题

DA mapper 可给 parent/component/manifestation 信用；旧链 task 相对 complete 的 PPV
只有 3.62%–6.48%。所以集群干预可能：

- 不改善诊断对象，却通过第二候选或 option relation 提升 mapper@K；
- 改善 compatible coverage，而 strict complete 不变；
- 也可能因候选变窄、丢失可映射父类而降低 mapper@K。

因此不能用 G1 strict 结果直接断言 DA mapper 无效；但也不能用 mapper 增益
复活“症状集群提高诊断能力”的叙事。

## 4. 仍可推进的窄方向

### P1（推荐）：DA Top-2/K 投影层的 cluster-qualified second leaf

不改冠军、不改生成器、不改主池。只问：

> 第二候选若有与第一候选不同的、病例内正交证据/视图，允许进入 mapper；
> 否则 mapper 只看第一候选。

它与已否证的全池重排、打包、G1 prompt 均不同。第一步必须零调用：

1. 在冻结 mapper records 中找出 Top-2 相对 Top-1 的 option gain/loss；
2. 按第二候选的不同 evidence spans / views 分层；
3. 同时报 mapper@1/@2、clinical relation transition、champion 不变但 option flip 数；
4. 若净 task gain ≤0，或 gains 主要为 projection-only，关闭；
5. 只有存在稳定净 gain，才预注册新的 mapper 调用。

该方向优化的是 benchmark interface，必须明确标注为 **projection optimization**。

### P2（低优先级）：IMPC view-interaction tie-break

仅在冻结 selector 不确定且两个候选 `n_views` 并列/接近时，用“不同观察 × 不同医生”
交互而非单一 view 数破平局。Cheap gate 必须在**全新未见数据**上冻结规则后执行；
当前 400 例已被反复查看，不能再承担确认。

### P3（仅有 top-K/abstention 产品需求时）：集群作为置信度，不作为排名

用集群宽度判断输出 K 或 abstain，不改 top-1。只有评价函数明确奖励 calibrated top-K
或选择性预测时才成立；对固定 top-1 Acc 没有自然增益。

## 5. 暂时搁置的方向

- MultiStance / Collapse3c 的生成 prompt 集群硬约束；
- 全池 `n_groups` / `n_high_groups` 重排；
- Forest/IMPC 移植 correlation-group/C4 clipping；
- 单纯改进实体链接后重启合取排序；
- 以 DA mapper 增益反向训练诊断生成器；
- 在当前反复使用的 400/800 例上继续搜索软权重。

## 6. 最终优先级

1. **先做 P1 零调用审计**，因为它直接对应用户指定的 DA mapper@K，且不危及诊断召回。
2. 若 P1 不过，**症状集群整体搁置**。
3. P2 只有出现新未见数据时再考虑。
4. MCR Prompt-7 不再投入集群路线。

过程限制：

- 本审计读取了 400 例冻结工件作描述性分析，属于 development-not-confirmation。
- task candidate verdict 覆盖仅 28%–43%，且 label-dependent；机读文件中的 candidate-level
  task 分析仅作描述。本文 task 判断主要依据全覆盖发表表与已校准的 family-level 报告。
- DA 与 MCR 不池化；旧 DA mapper 与正规 Acc@4 不池化。
