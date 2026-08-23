# CoreLift M1/M2 槽位产出实验报告（800 例，五臂）

实验 ID `SLOT_YIELD_BREAKTHROUGH_M1_M2`。执行计划见
[`SLOT_YIELD_BREAKTHROUGH_PLAN.md`](../../SLOT_YIELD_BREAKTHROUGH_PLAN.md)。

## 0. 一句话结论

**槽位定律在 DA 上成立，但方向与旧路线的假设相反：横向槽位（不同疾病）便宜地买到覆盖却几乎买不到完整对象，纵向槽位（对已有候选追加 modifier）以约 4 倍的密度买到完整对象。** DA 官方 Acc@4 从 A3 的 25.50% 升到 B1 的 31.00%（+5.50pp，精确 McNemar p=.0038，族内 Holm q=.0184）；MCR 官方 Acc 无收益（−2.00pp，q=.740）。但 **M2 补全工具的入场门以 0.1112 对 0.10 的幻觉率之差未过**，因此 B1 的 clinical-complete 确证性解释与 B1-vs-A3 临床对比按预注册规则扣留。

这是**开发集分析，不是确证分析**；临床完整性是三模型盲审面板的敏感性度量，**不是人工根真值**。

**读数前必看 §9b。** 本报告的 DA 官方数字用的是迁移后的正规评分链（gemini-2.5-flash 单
Top-1 投影），与 `MOSAIC_EXPAND_REPORT.md` 主表的 `backbone_v1` 旧链（llama 映射器 + Top-2 +
选项排序）**不是同一估计量**，同臂同 100 例实测链差 42.0pp。在同一口径下 CoreLift 不低于
forest / lite。另外，比较器模型为 DeepSeek 而非 llama，跨实验绝对值比较受此混淆。

## 1. 执行口径与服务率

800 例 = DA 400 + MCR 400，五臂全交叉，共 4000 个条件行，矩形无缺失。
DA 报告 gold-blind 投影后的 **Acc@N（N=4）**，MCR 报告冻结的 **Prompt-7 Acc**，均由
`google/gemini-2.5-flash` 评分，与 forest 系列、aphhm-c 系列同口径，两者从不合并。

| 臂 | 机制 | 每例调用 | 服务率 | 主 frontier 均宽 |
|---|---|---:|---:|---:|
| `A0_control` | 单视图 + Lite 比较器 | 2 | 97.13% | 2.86 |
| `A1_views` | 三视图横向提案 | 4 | 98.38% | 4.97 |
| `A2_views_typed` | 三视图 + 类型化准入 | 5 | 97.25% | 3.65 |
| `A3_full` | A2 + 残余账簿可见的比较器 | 5 | 98.38% | 3.65 |
| `B1_corelift` | A3 + append-only 补全（M2） | 5 | 98.50% | 4.73 |

服务率门槛 0.95，五臂全部达标。首轮 DeepSeek 比较器超时/截断较多（A0 最低 704/800），
按 PD-002 的失败例重跑机制恢复，未删除、未插补任何病例。

## 2. 主端点结果

### 2.1 DA（n=400，Acc@4）

| 对比 | Δ官方 | p | Holm q | Δclinical-complete | ΔC∪P |
|---|---:|---:|---:|---:|---:|
| A1−A0 | **+6.00pp** | .0037 | **.0184** | +1.75pp (q=.063) | **+6.50pp (q=.0087)** |
| A2−A1 | −3.00pp | .065 | .196 | −0.50pp | −1.75pp |
| A3−A2 | 0.00pp | 1.0 | 1.0 | 0.00pp | −0.25pp |
| A3−A0 | +3.00pp | .169 | .337 | +1.25pp | +4.50pp |
| B1−A3 | **+5.50pp** | .0038 | **.0184** | 扣留 | 扣留 |

绝对值：A0 22.50% → A1 28.50% → A2 25.50% → A3 25.50% → B1 31.00%。

### 2.2 MCR（n=400，Prompt-7 Acc）

| 对比 | Δ官方 | p | Holm q | Δclinical-complete |
|---|---:|---:|---:|---:|
| A1−A0 | +3.00pp | .104 | .519 | +3.00pp (q=.219) |
| A2−A1 | −2.00pp | .185 | .740 | −2.75pp (q=.209) |
| A3−A2 | −0.25pp | 1.0 | 1.0 | −0.50pp |
| B1−A3 | −2.00pp | .229 | .740 | 扣留 |

绝对值：A0 31.75% → A1 34.75% → A2 32.75% → A3 32.50% → B1 30.50%。
**MCR 上没有任何对比过门。**

## 3. 核心机制：两类槽位的边际产出密度不同

把每个对比的暴露增量除以主 frontier 宽度增量，得到「每个准入槽位买到多少暴露」：

| 家族 | 对比 | Δ宽度 | 每槽 C∪P 暴露 | 每槽 **complete** 暴露 |
|---|---:|---:|---:|---:|
| DA | A1−A0（横向） | +2.30 | 5.97pp | 0.87pp |
| DA | B1−A3（纵向补全） | +1.11 | 1.57pp | **3.59pp** |
| MCR | A1−A0（横向） | +1.94 | 5.67pp | 3.09pp |
| MCR | B1−A3（纵向补全） | +1.02 | 1.47pp | 2.44pp |

DA 上纵向槽位的 complete 产出密度是横向槽位的 **4.1 倍**（3.59 对 0.87），而横向槽位的
C∪P 产出密度是纵向的 3.8 倍。两类槽位买的**不是同一种东西**：横向槽位扩的是「大致相关」
的覆盖面，纵向槽位扩的是「对象完整度」。DA 的限速步骤是后者，所以只有 B1 抬起了官方指标。
MCR 上两类密度接近（3.09 对 2.44），纵向槽位没有比较优势，这与 MCR 全线无收益一致。

这是本实验相对既有报告的主要新增量：过去所有加宽实验都只测一种槽位（横向），因而把
「加宽换不到转化」误读为槽位定律的普遍上限，实际上是**槽位类型选错了**。

## 4. 召回—转化权衡在单一实验内被量化

类型化准入（A2 相对 A1）的效果值得单独记录，因为它精确复现了权衡本身：

| 家族 | Δ条件转化率 | Δ C∪P 暴露 | Δ官方 |
|---|---:|---:|---:|
| DA | 84.62% → 95.24%（**+10.62pp**） | −6.25pp | −3.00pp |
| MCR | 77.78% → 78.91%（+1.13pp） | −3.75pp | −2.00pp |

类型化准入确实做到了它被设计去做的事——把同层竞争候选移出主池，DA 条件转化率提升
10.62pp。但代价是暴露损失，净效应在两个家族上都是负的（虽未达显著）。**「提升转化率」
本身不是有效干预**：在固定信息量下它只是把同一份暴露重新分配。

`A3−A2` 在 DA 官方指标上恰好为 0.00pp，在 MCR 上为 −0.25pp。让比较器额外看到残余账簿
不产生任何可测效应——这一条计划中的机制应判为无效。

## 5. M2 入场门：未过门，但失败是分层的

预注册的五项门槛中四项通过，一项以极小差距失败：

| 指标 | 门槛 | 实测 | 判定 |
|---|---:|---:|---|
| 逐字 span 闭合 | 1.00 | **1.0000** | 通过 |
| 双 reviewer 原始一致 | ≥0.85 | 0.9271 | 通过 |
| Gwet AC1 | ≥0.70 | 0.9154 | 通过 |
| 服务率 | ≥0.95 | 1.0000 | 通过 |
| modifier 幻觉率 | ≤0.10 | **0.1112** | **失败** |

1331 个 modifier 中 148 个被双 reviewer 面板判为「span 真实存在但不能临床支撑该 modifier」。
逐字闭合为 1.0 说明**引用机制本身没有造假**，失败全部发生在「引文能否支撑该限定词」这一层。

按 axis 分层后（`corelift_gate_axis_diagnostic.py`，产物
`evaluation/modifier_gate/axis_stratification.json`）：

| 层 | 组成 | 幻觉率 |
|---|---|---:|
| 表面型单 axis | anatomy, subtype_histology, composite_component | **40/681 = 0.0587** |
| 推断型单 axis | etiology, complication, temporal_evolution, scope_distribution | 89/478 = 0.1862 |
| 复合多 axis | 两个及以上 axis | 19/172 = 0.1105 |

单 axis 明细中最差的三项是 `temporal_evolution` 0.220、`complication` 0.207、
`etiology` 0.182；最好的是 `anatomy` 0.054。典型失败形态有两种，都很有诊断价值：

- **极性反转**：用「No cherry-red spot, hemorrhage, or peripheral neovascularization was
  present」去支撑「Sickle Cell Retinopathy, **proliferative**」——引文直接否证该限定词。
- **时程越权**：用「4-day history of palpitations at rest」去支撑「Atrial Fibrillation,
  **chronic**」；用「more than 10 years' duration」去支撑「**acquired**」（病程长短不能
  区分先天与后天）。

结论：append-only 补全在**病历直接陈述的表面属性**上可靠（0.059，本可过门），在**需要跨
时程、因果、并发状态做推断**的属性上不可靠（0.186）。这是一个受限工具而非失效工具。

必须明确：0.0587 是**对已冻结门失败结果的事后分层描述，不构成一个通过了的预注册门**，
不能据此宣称 M2 通过。要把它变成有效结论，需要以受限 axis 集重新预注册并重跑。

## 6. B1 的 DA 增益是否由幻觉 modifier 驱动？

这是本实验最关键的完整性检查，因为门失败与 DA 显著增益同时出现。

DA 官方指标上 B1 相对 A3 净胜 22 例（胜 38、负 16）。按夺冠候选的门判定拆解：

| 净增益来源 | 净例数 |
|---|---:|
| 全部 modifier 均通过双 reviewer 的补全 | **+17** |
| 含至少一个未获支持 modifier 的补全 | +4 |
| 夺冠候选不是补全 | +1 |

即 **77% 的净增益来自 modifier 全部获得双 reviewer 支持的补全**。三档敏感性：

| 处置 | 胜/负 | p |
|---|---:|---:|
| 按实评估 | 38/16 | .0038（Holm q=.0184） |
| 剔除全部由未获支持 modifier 驱动的胜例 | 34/16 | .0153（Holm 后 q≈.061，边缘） |
| 进一步把这些胜例反计为负例 | 34/20 | .0759（不显著） |

因此：DA 增益**不是**幻觉 modifier 的产物（主体来自获支持的补全），但在最严苛的重新归因
下会跌出显著。结合门失败，正确的表述是**提示性证据，尚未确证**。

A3→B1 的完整性转移分类为：特异性救回 14、对象救回 12、范围压缩 3、灾难性替换 12，
带符号净值 +11。灾难性替换 12 例不可忽视——补全在少数病例上把正确对象换成了错误对象。

## 7. 与计划中失败条件的对照

计划 §7 的 M1 失败条件为「A1 相对 A0 的暴露增益不复现」或「A3 的池宽增长带来的转化损失
超过清洁斜率预测两倍」。

- 暴露增益复现：DA C∪P 暴露 71.50% → 85.25%（+13.75pp），官方 +6.00pp（q=.0184）。**M1 未失败。**
- DA 条件转化率随池宽**上升**（A0 83.33% → A3 95.24%），不存在需要检验的转化损失。
- M2 失败条件「幻觉率 >0.10」**已触发**，下游 complete 对比按 C2 先例封存。

## 8. 可写与不可写

**可以写的：**
- 三视图横向提案在 DA 官方指标上给出 +6.00pp（q=.0184），在 C∪P 上 +6.50pp（q=.0087）。
- append-only 纵向补全在 DA 官方指标上给出 +5.50pp（q=.0184），且主体不由幻觉 modifier 驱动。
- 纵向槽位的 complete 边际产出密度在 DA 上约为横向槽位的 4 倍。
- 类型化准入把 DA 条件转化率抬高 10.62pp，但净效应为负；比较器看到残余账簿的效应为 0。
- M2 入场门未过（0.1112 > 0.10），失败按 axis 强分层。

**不可以写的：**
- 不可宣称 B1 的 clinical-complete 或 complete 暴露优于 A3——该对比已按预注册扣留。
- 不可宣称 M2 通过入场门，也不可把 0.0587 的受限 axis 率当作通过的门。
- 不可宣称任何 MCR 结论——MCR 上无一对比过门，包括 B1（−2.00pp）。
- 不可把任何数字当作确证结果：这是被反复使用的开发集。
- **不可把本报告的 DA 数字与 `MOSAIC_EXPAND_REPORT.md` 主表的 DA task 并列**：那是
  `backbone_v1` 旧链（llama 映射器、Top-2、选项排序），同臂同 100 例实测链差 42.0pp。详见 §9b。
- 不可把 CoreLift 与 forest / lite 的绝对值差异归因于纯算法：比较器模型不同
  （DeepSeek 对 llama），仅生成层同源。
- 不可把临床完整性称为真值——它是三模型面板敏感性（complete 边界原始一致 0.966、
  Gwet AC1 0.958，n=900）。

## 9. 下一步

只有一条由数据指向的路径：**以受限 axis 集重新预注册 M2**。把补全限制在
`{anatomy, subtype_histology, composite_component}`，禁止多 axis 复合追加，并对
`temporal_evolution` / `complication` / `etiology` 增加一条极性检查（引文若含否定词则拒绝
该 modifier）。该子工具在本实验的冻结数据上幻觉率为 0.0587，有过门的先验；DA 净增益中
+17 例本就来自这类补全。此路径同时保留五调用预算不变。

MCR 分支应停止在加宽方向上投入。MCR 上横向与纵向槽位的 complete 产出密度接近，说明其限速
步骤不在候选池的构造上，需要另行定位。

## 9b. 与 forest / aphhm-c 系列的可比性（必读，否则数字会被误引）

### 9b.1 底座模型并非完全相同

| 环节 | forest / lite / mosaic 系列 | CoreLift |
|---|---|---|
| 候选生成 | `meta-llama/llama-3.3-70b-instruct` | **同一批冻结的 llama forest 视图**（`logs/backbone_v1/*/mosaic_forest_v1/case_stages`） |
| 比较器 / 选择 | `meta-llama/llama-3.3-70b-instruct` | **`deepseek/deepseek-v4-flash-0731`** |
| 类型化准入 + 补全 | 不存在 | **`google/gemini-2.5-flash`** |

生成层是同一份 llama 产物、逐字节冻结复用，但**比较器换了模型**。因此本实验的**臂间对比
（A1−A0、A2−A1、B1−A3 等）内部有效**——五臂共用同一个 DeepSeek 比较器；而**与 forest / lite
的跨实验绝对值比较受比较器模型混淆**，不能当作纯算法差异。

### 9b.2 DA 官方指标存在两条不同的评分链，绝不可混排

仓库里并存两条 DA 评分链，二者是**不同的估计量**：

| | `backbone_v1` 旧链 | 迁移后的正规链（本实验采用） |
|---|---|---|
| 映射模型 | llama-3.3-70b | `google/gemini-2.5-flash` |
| 输入预测深度 | **Top-2 列表** | **单一 Top-1** |
| 判定方式 | 对全部选项排序，看金选项是否排第一 | 把 Top-1 投影到语义最近的选项，允许 `NONE` |
| 辅助机制 | RAG critic + 分歧消解 | 单次投影调用 |

在**同一个臂、同一批 100 例 DA**（`DA_d2_seq100`）上实测偏移：

| 臂 | 旧链 option_top1 | 正规链 task | 偏移 |
|---|---:|---:|---:|
| `mosaic_lite_v1` | 0.630 | **0.210** | **42.0pp** |
| `mosaic_forest_v1` | 0.700 | 未重评分（迁移表中无此臂） | — |

因此 `MOSAIC_EXPAND_REPORT.md` 主表里的 Forest DA400 task = 0.6375、Lite = 0.6025，**与本报告
的 DA 数字不在同一口径上**，二者相差约 40pp 属于链差而非能力差。产物见
`evaluation/final/cross_chain_comparability.json`（由
`corelift_cross_chain_comparability.py` 确定性生成）。

临床端点则**完全同口径**：CoreLift 的 reviewer 提示 sha256 与迁移一致
（`463c126908d57538bc5d7e04a9b75ec87f6b41fc1afd26a835068d4067c50978`），面板设计相同。
MCR task 同模型、同 Prompt-7 判准，封装措辞不同（迁移为批量多预测、本实验为单预测），
且本实验 1608 条 task 中有 **1031 条直接复用迁移的冻结结果**，那部分逐字节同口径。

### 9b.3 同口径下的横向对照

下表所有行均为 `google/gemini-2.5-flash` 正规链、ITA 口径；参照臂的病例集合**全部是**
CoreLift 800 例宇宙的子集（已逐例校验）。

| 臂 | DA task | DA complete | DA C∪P | MCR task | MCR complete | MCR C∪P |
|---|---:|---:|---:|---:|---:|---:|
| `mosaic_lite_v1` | .210 (100) | .060 | .610 | .295 (200) | .210 | .360 |
| `forest_evidence_integrator` † | .250 (200) | .065 | .615 | .340 (200) | .280 | .425 |
| `mosaic_adaptive4v2_v1` | .180 (100) | .030 | .580 | .300 (200) | .230 | .395 |
| `lite3_safe` | .247 (150) | .000 | .547 | .200 (150) | .147 | .320 |
| CoreLift `A0_control` | .225 (400) | .037 | .585 | .318 (400) | .250 | .417 |
| CoreLift `A1_views` | .285 (400) | .055 | **.650** | **.347** (400) | **.280** | **.438** |
| CoreLift `B1_corelift` | **.310** (400) | **.075** | .647 | .305 (400) | .250 | .438 |

† `mosaic_forest_v1` 本身从未在正规链上重评分；E4 的 forest 池整合臂是可得的最近替代，
不等同于 forest 骨干本身。

**结论：在同一口径下 CoreLift 并不比 forest / lite 差。** B1 在 DA task（.310 对 .250）、
DA complete（.075 对 .065）上领先可得的 forest 参照臂；A1 在 MCR task（.347 对 .340）、
MCR complete（.280 对 .280）、MCR C∪P（.438 对 .425）上持平或略优。用户观察到的「更差」
来自与旧链 0.6375 的对比，那是链差。

### 9c. 旧链重评分（与发表表同估计量）

已把五臂 champion 导出到 mosaic `predictions.jsonl`，走 `score_da` / `score_mcr`。完整对照见
`legacy_backbone_score/REPORT.md`。要点：

- DeepSeek 选择器 B1 DA ITA **0.6400**，Forest 发表表 **0.6375**，配对 McNemar p=1.0。
- 同一旧链上 A0=0.5950，贴近 Lite 0.6025。
- Llama 选择器 ITA 被服务率（0.81–0.89，未过 0.95）拉低；among-served DA 仍在 0.61–0.64，
  不可把 0.53 对 0.6375 读成算法差。
- 后续评分默认：RAG mapper **25** 并发，无 RAG **50** 并发。

### 9b.4 一个必须记录的测量缺陷

正规链的 DA 映射器会丢弃相当一部分本来正确的答案。按临床关系分层（DA 全臂合并 n=1968）：

| 临床关系 | n | 官方 task 正确率 |
|---|---:|---:|
| `complete_equivalent` | 107 | **0.692** |
| `partial_parent_or_component` | 1151 | 0.281 |
| `conflicting_subtype_or_scope` | 327 | 0.180 |
| `manifestation_or_related` | 180 | 0.106 |

即**在预测与参考诊断完全等价的病例上，官方 DA 指标仍有 30.8% 判为错误**。同时 `NONE`
投影率为 0，映射选项分布接近均匀（A 126 / C 99 / B 85 / D 78），A0 的 .225 几乎就是四选一
的随机水平。这说明正规链的 DA 映射对**部分正确**的预测几乎不给信用，压低了所有臂的绝对值。
由于全部臂共用同一映射器，**臂间对比不受影响**；但**不应把这些 DA 绝对值当作系统的 MCQ 作答
能力**——旧链 0.63–0.70 才更接近「给定四选项时能否选对」的语义。

## 10. 资产索引

| 资产 | 路径 |
|---|---|
| 五臂运行结果（4000 行） | `case_conditions.jsonl` |
| 运行侧遥测与池宽分布 | `summary.json` |
| 冻结预注册 | `preregistration.json` |
| 协议偏离（PD-001 至 PD-004） | `protocol_deviations.json` |
| 臂级端点统计 | `evaluation/final/arm_statistics.{csv,json}` |
| 配对对比与 Holm | `evaluation/final/paired_contrasts.{csv,json}` |
| 病例级端点 | `evaluation/final/case_endpoints.jsonl` |
| 三 reviewer 面板 | `evaluation/panel/` |
| M2 入场门与 axis 分层 | `evaluation/modifier_gate/` |
| 跨评分链可比性 | `evaluation/final/cross_chain_comparability.json` |
| 旧链重评分（DeepSeek 选择器） | `legacy_backbone_score/` |
| Llama 选择器 + 旧链 | `../SLOT_YIELD_BREAKTHROUGH_LLAMA_SELECTOR/` |
| 冻结复用冲突审计 | `evaluation/design/frozen_reuse_audit.json` |
| 机器生成端点报告 | `evaluation/REPORT.md` |

## 11. 复用契约的一处修补

评估器初次运行时在冻结复用上 fail-closed 中止：C0 三模型面板与
`ALL_ARM_ENDPOINT_MIGRATION` 终局重放在 3016 个重叠键上有 368 个（12.20%）细标不一致。
测量后发现分歧完全集中在端点不消费的那一层：

| 边界 | 分歧率 |
|---|---:|
| 五分类细标 | 12.20% |
| C∪P 边界 | 3.05% |
| **complete 边界** | **0.70%** |

这精确复现了 C0 自身的已知结论（二元 complete 边界可靠，五分类细标以 0.7210 未过 0.80 门）。
修补后的规则是：**两来源在端点消费的边界上分歧则丢弃复用、交由在线三 reviewer 面板重裁；
仅细标分歧则保留首个来源并把分歧标签作为溯源携带。** 实测丢弃 118 个临床键与 43 个 task
键，保留 280 个仅细标分歧的键。完整记录见 PD-004 与 `frozen_reuse_audit.json`。
