# E12：e7 表征 × 宽度 × 比较器及调用深度的病例轨迹机制解剖

## 判定

E12 最可靠的正结论不是“更多候选”或“更多调用”有效，而是：在冻结候选池上，**让比较器读取完整原始病例并做显式候选比较，确实优于直接沿用历史首候选**。在 300 个配对病例、39 个预注册主比较的临床完整等价 Top-1 端点上，只有两个比较通过 Holm 校正：

- raw、k=5、pairwise 相对 first：51/300→65/300，`+4.67 pp`，16 gain/2 loss，McNemar `p=.00131`，Holm `q=.04987`；
- raw、k=10、pairwise 相对 first：51/300→66/300，`+5.00 pp`，17/2，`p=.000729`，`q=.02842`。

这证明候选顺序不是充分排序器，病例证据可以把更完整的病因、亚型或实体从候选池中提到第一。但它**没有证明 pairwise 优于 pointwise**：raw k=5 两者同为 65/300，raw k=10 为 60/300 对 66/300，后一个 `+2.00 pp` 只有 8/2 discordance，39 重校正后 `q=1`。pairwise 的强结论是“胜过不比较”，不是“已经胜过所有单次比较方式”。

表征因素给出更重要的负结论。历史 e7 S1 摘要经常删除病理、解剖压迫、时间演化、病原学或病例末尾的诊断性句子。raw 相对 S1 的 clinical-complete Top-1 在四个在线比较中均为正：k=5 pointwise `+5.00 pp`（19/4，未校正 `p=.00260`，Holm `q=.09534`），k=5 pairwise `+4.00 pp`（14/2，`q=.14633`），k=10 pointwise `+3.33 pp`（14/4，`q=1`），k=10 pairwise `+4.00 pp`（14/2，`q=.14633`）。它们未通过 39 重 primary 校正，不能宣称确认性表征优势；不过方向、病例链路和 complete+partial 敏感性端点一致，足以定位 S1 的破坏性压缩机制。

冻结 E6 graph 也没有修复这个问题。graph 相对 S1 的主比较近零，且 42/300 病例没有合格 graph、在线臂必须 fail-closed；graph JSON 平均 3,590 字符，反而显著长于 raw 的 1,511 字符。它既不是更短的压缩，也不是可靠的信息保持变换。病例审计显示它会把“未见某细胞谱系”编码成对病灶本身的宽泛 `contradicts`，或保留观察却丢失观察对病因/亚型的限定关系。E12 因而再次否定当前生成式 graph 实现，而不是否定所有关系图。

宽度和调用深度均没有稳定净收益。k=5→k=10 只新增 2 个 strict reference exposure、无 exposure loss，但 raw pointwise 的 clinical-complete Top-1 反而 `−1.67 pp`（4 gain/9 loss），raw pairwise 仅 `+0.33 pp`（3/2）。第二次 S2 调用改变 81/300 个 capped pool、加入并挤出各 117 个候选，却没有 strict exposure gain；第三次改变 44/300、加入并挤出各 56 个，仍没有 strict exposure gain。clinical-complete Top-1 为 depth1 62、depth2 65、depth3 66；两次增量比较均未通过两重校正。更关键的是，depth1→2 的 5 个端点翻转只有 2 个真的改变了候选池，depth2→3 的 3 个翻转只有 1 个改变候选池；其余是相同输入的独立 selector 调用、schema failure 或路由方差，不能归因为“额外生成调用”。

所以 E12 对 RCR-3 的直接约束是：保留原文 span 和关系，不再以 S1 摘要替代病例；候选新增必须携带可区分的证据与类型，而不是在固定 k 上做无证据替换；Call-3 应以成对 decisive contrast 排序并保留罕见候选覆盖；调用深度的收益必须以“新实体/新证据进入并造成何种变化”计量，不能只比较三次独立 selector 的最终准确率。

## 设计与可识别边界

实验冻结 E6 的 300 个关系挑战病例（DA 150、MCR 150）和历史 e7 的三次 S2 proposal multiset。主设计为：

| 因素 | 水平 | 固定项 |
|---|---|---|
| 表征 | raw 原文、历史 S1、冻结 E6 graph | 同一病例、同一候选 ID 和候选 payload |
| 宽度 | k=5、k=10 | k=5 为安全实体归并后的历史 S3 优先池；k=10 嵌套补入未用 S2 候选 |
| 比较器 | first、pointwise、pairwise | first 不调用模型；另两者各一 semantic call |

18 个主臂之外，raw+k10+pairwise 冻结 depth1、depth2，并复用主臂 depth3，构成累计 S2 call 深度路径。候选 payload 隐去 gold、选项、历史得分、投票、旧 champion 和来源顺序；身份只允许 exact/frozen-safe-synonym，不用 substring/Jaccard 合并。

这个设计能识别“给同一 comparator 的输入表征”“可见候选集合”“比较 prompt”在当前实际 OpenRouter 路由合同下的联合处理效应。它不能识别以下对象：

1. 历史 S2 没有共享 evidence ledger，故 Call-2/3 的**证据新颖性**不可观测；只能知道候选实体是否新增；
2. 每个 online cell 是独立 API 调用，provider 未随机固定；相同 payload 的跨臂翻转不能自动归因于实验因素；
3. graph 是 E6 已生成产物，不是 oracle graph；42 个构造失败属于处理本身，而不是可删除缺失；
4. raw 病例有时包含“was suspected/leading to suspicion”式病例报告结论，raw 优势可能部分来自诊断性文本保留，不等于纯粹从症状推理能力；
5. 300 例仍是开发/机制集；按约定没有把重复运行、扩容确认集或 provider/retry 统一包装成新科学臂。

## 端点与根审计

三个端点有意分层：

1. `strict`：exact 或冻结 safe-synonym，预注册 primary；
2. `clinical complete`：与 reference 是病例要求层级上的完整同一实体；
3. `complete+partial`：允许疾病族、表现或复合诊断的一部分正确，只作范围敏感性分析。

Gemini 2.5 Flash 只用于异质候选关系 screen 和扩展审计队列，300/300 病例成功。它对 3,191 个候选给出 81 exact、148 acceptable variant、260 broader/narrower、1,299 related、1,403 unrelated。根审计随后逐候选复核 154 个病例、385 个 case-candidate relation，覆盖全部 45 个最终 primary clinical-complete discordance 病例和 30 个分层负样本病例。

异质 screen 与根判断的分歧很大：385 个复核关系中有 154 个类别下调。screen 所称的 102 个 `acceptable_clinical_variant` 中，根审计只保留 14 个 complete，65 个降为 partial，23 个降为 not-equivalent；59 个 `exact` 中也有 15 个 partial、5 个 not-equivalent。典型错误包括：

- 把 bone hemangioma 当成 intraosseous metaplastic meningioma；
- 把 ADEM 当成 glioblastoma；
- 把 type-1/IgG4-related pancreatitis 当成 type-2 autoimmune pancreatitis；
- 把 vasculitic neuropathy/腓总神经麻痹当成 EGPA 本体；
- 把 diabetic amyotrophy 当成肾癌；
- 把复合 reference 的单个表现或病因组件当作完整答案。

最终根关系为 53 complete、116 partial、216 not-equivalent。以下机制结论以根审计 clinical-complete 为主；未进入端点关键队列的关系仍明确保留 heterogeneous proxy 来源，未伪称全量人工 gold。

## 二十个条件的端点全景

表中每格为 Top-1/Top-2 病例数，分母均按 ITA 计为 300；在线失败按错处理。

| 表征/宽度/比较器 | strict | clinical complete | complete+partial |
|---|---:|---:|---:|
| raw k5 first | 21 / 24 | 51 / 62 | 120 / 160 |
| raw k5 pointwise | 24 / 28 | 65 / 71 | 140 / 175 |
| raw k5 pairwise | 25 / 29 | 65 / 69 | 144 / 169 |
| raw k10 first | 21 / 24 | 51 / 62 | 120 / 160 |
| raw k10 pointwise | 25 / 28 | 60 / 67 | 142 / 168 |
| raw k10 pairwise | 26 / 29 | 66 / 68 | 146 / 172 |
| S1 k5 first | 21 / 24 | 51 / 62 | 120 / 160 |
| S1 k5 pointwise | 17 / 26 | 50 / 59 | 123 / 159 |
| S1 k5 pairwise | 21 / 26 | 53 / 61 | 131 / 160 |
| S1 k10 first | 21 / 24 | 51 / 62 | 120 / 160 |
| S1 k10 pointwise | 17 / 23 | 50 / 58 | 119 / 152 |
| S1 k10 pairwise | 20 / 26 | 54 / 63 | 123 / 153 |
| graph k5 first | 21 / 24 | 51 / 62 | 120 / 160 |
| graph k5 pointwise | 21 / 24 | 55 / 58 | 120 / 140 |
| graph k5 pairwise | 21 / 24 | 53 / 61 | 116 / 143 |
| graph k10 first | 21 / 24 | 51 / 62 | 120 / 160 |
| graph k10 pointwise | 19 / 22 | 50 / 56 | 108 / 131 |
| graph k10 pairwise | 20 / 25 | 53 / 63 | 119 / 145 |
| raw depth1 k10 pairwise | 25 / 30 | 62 / 68 | 141 / 175 |
| raw depth2 k10 pairwise | 25 / 29 | 65 / 68 | 143 / 169 |

first 的九个表征/宽度组合输出完全相同，是设计正确的负控制：first 不读取表征，宽度从 5 扩到 10 也不改变第一历史候选。它们的恒等结果说明后续差异来自 online comparator 或其输入，而不是候选 ID 构造在不同表征间漂移。

strict Top-1 只有 17–26/300，clinical complete 为 50–66/300，complete+partial 为 108–146/300。三层之间的巨大差距不是可以忽略的评估细节：系统主要在“泛病种/表现/病因/亚型/复合范围”之间移动，而不是简单地在正确和完全无关之间移动。

## 39 个预注册比较：哪些结果能说、哪些不能说

clinical-complete Top-1 的两个 Holm survivor 都是 raw pairwise 对 first；其余 37 个比较均未通过 `alpha=.05`。raw pointwise 对 first 的 k5 比较同为 `+4.67 pp`，但 17 gain/3 loss，Holm `q=.09534`；k10 为 `+3.00 pp`，14/5，`q=1`。不能因为 pairwise 的 q 刚过阈值，就把 pointwise 描述成无效；两者的绝对表现高度接近，discordance 结构不同。

complete+partial 端点中，raw 相对 S1 的 k10 pointwise/pairwise 都是 `+7.67 pp`，未校正 `p=.00219/.00140`，Holm `q=.08104/.05470`；仍没有通过 .05。唯一通过该敏感性 family 校正的是 graph k10 pointwise 相对 first 的 Top-2 **下降** `−9.67 pp`（Holm `q=.02034`）。这与 graph 在较宽候选池上易受表现/相关实体吸引一致，但该端点不是 primary，不能单独升级成“graph 必然有害”的确认性结论。

共同成功病例分析没有反转主结论。它对 graph 的意义主要是区分两件事：42 个构造失败造成的 ITA 处罚，以及 258 个有 graph 病例上的排序质量。graph 在共同支持集也没有显示相对 S1 的稳定优势；因此不能把全部弱势解释成缺失惩罚。

## S1 为什么损失：不是一般性的“摘要较短”，而是删除决定性关系

raw 平均 1,511 字符，S1 JSON 平均 1,049 字符。长度差本身不是机制；病例轨迹显示被删的是能够区分病因、表现和亚型的关系。

### 病理与解剖证据被删

- `DA_d2_heldout100/392`，reference 为 pigmented onychomatricoma。raw 含 bland spindle-cell proliferation、villous fibroepithelial projections、无 melanocytic proliferation、S100/CD34 阴性和 intracorneal hemorrhage；S1 只保留“进行性甲色素带”。同一 k10 候选池下，raw pointwise/pairwise 选 onychomatricoma（根审计为完整临床等价），S1 选 subungual/nail-unit melanoma 或 nail-matrix nevus。这里不是模型在同一证据上偏好不同，而是 S1 把诊断性组织学全部删除。
- `DA_d2_heldout200b/540`，reference 为 acute oxalate nephropathy。raw 含肾活检 multifocal oxalate crystal deposits；S1 只保留 DKA、AKI、UTI 和心包积液。k=5 不暴露 oxalate candidate；k=10 后 raw 和 graph 都将其排第一，S1 仍选 DKA/AKI。这个病例同时展示宽度只在“新候选 + 决定性证据仍可见”时有用。
- `MCR_seq200b/320`，reference 为 May–Thurner syndrome。raw 明确给出右髂总动脉压迫左髂总静脉并有充盈缺损；S1 只保留 Doppler 证实 DVT。raw/graph comparator 选 May–Thurner，S1 明确以“缺少 confirmatory imaging”为理由选 generic DVT。理由与被删字段直接对齐，是最强的 representation→reason→rank 因果链之一。

### 时间、病因与完整对象被压平成表现

- `MCR_seq200b/431`，reference 为 congenital CMV infection。raw 含母体感染线索、胎儿出血/孔洞脑、micropolygyria、出生后 microcephaly、micropurpura、jaundice 与 germinolytic cyst；S1 把感染病因关系压成“先天神经病伴产前出血”。raw 选 CMV，S1/graph 选 structural consequence `porencephaly`。这正是“表现替代病因”。
- `MCR_seq200b/251`，reference 为 twin anemia–polycythemia sequence。raw 保留两个胎儿相反的 MCA-PSV、胎盘差异及病例作者据此怀疑 TAPS 的链路；S1 突出 growth restriction、preeclampsia 和 Tetralogy of Fallot，却删除速度对比和诊断性关系。raw 选 TAPS，S1 多选 sIUGR/preeclampsia/TOF。
- `MCR_v2_seq100/208`，reference 为 Takotsubo syndrome。raw 末段给出冠脉处理后 apical/mid akinesia、basal hyperkinesia 和明确 suspicion；S1 将其框成 acute coronary syndrome with arrhythmia，在线臂偏向 MI/stent thrombosis。raw 候选 `Takotsubo cardiomyopathy` 被根审计视为完整等价，S1 丢失病因性/形态学排序。

### 摘要还会制造内部矛盾

`MCR_v1_seq100/74` 的 key facts 正确写出 QTc 380 ms、无 Brugada pattern，但 `salient_findings` 又写成“prolonged QTc”。S1 pointwise 因而声称“initial ECG showed prolonged QTc”并选 long-QT syndrome，S1 pairwise 偏向 risperidone-induced QT prolongation。这里不是单纯遗漏，而是摘要层自相矛盾后被 comparator 当成高显著度事实。

### raw 优势也含 benchmark 结论句泄漏

不能把全部 raw gain 解释为更好的医学关系推理。`MCR_seq200b/411` 的 raw 末句直接说 multiple plexiform schwannoma was suspected；`MCR_seq200b/251` 和 `MCR_v2_seq100/208` 也含“prompted suspicion/leading to suspicion”。S1 往往恰好删掉这些结论句。raw 的处理效应是真实的输入保真效应，但其中混合了“保留原始证据”和“保留病例报告作者的诊断提示”。RCR-3 应保留 source span，同时单独标注 `author_diagnostic_assertion`，报告有/无该类句子的敏感性，避免把文本泄漏当作独立诊断能力。

## graph 为什么没有成为安全中间层

258 个可用 graph 的平均 JSON 长度约为 raw 的 2.38 倍，包含 nodes、source quote、polarity、scope、time anchor 和 relations；信息量不小，但决定性语义未必连接正确。

`DA_d2_heldout100/392` 中 graph 保留“no melanocytic lesions”和 S100 negative，却把前者建成 polarity=absent 的 pathology node，再用宽泛 `contradicts` 指向“new pigmented lesion”。这没有表达“病灶存在，但不是 melanocytic proliferation”，使 comparator 更易把临床色素外观与病理反证割裂；graph k10 两种 comparator 都错误选择 nail-unit squamous-cell carcinoma。

`MCR_seq200b/431` 的 graph 保留孔洞脑等结构观察，却没把母体感染、胎儿时序和新生儿系统征象绑定到 CMV 病因，因此两种 k10 comparator 都停在 porencephaly。相反，`MCR_seq200b/320` 的 graph 成功保留髂动静脉压迫关系，能与 raw 一样从 DVT 上溯到 May–Thurner。成功与失败的分界不是“结构化/非结构化”，而是**决定性 relation 是否忠实、对象是否同一、否定是否作用在正确属性上**。

graph 在线臂的完成数为 k5 pointwise 257、k5 pairwise 258、k10 pointwise 252、k10 pairwise 256。除 42 个预注册 graph 构造失败外，还有少量 schema failure；全部 fail-closed。first graph 臂为 300/300，只因为 first 不消费 graph，不能被拿来证明 graph 可用性。

## comparator：明确的排序价值与明确的过度纠偏

pairwise 对 first 的两个 primary survivor 来自三类可复核修复：

1. **表现→病因/实体**：`MCR_seq200b/320` 从 DVT 提升 May–Thurner；`MCR_seq200b/431` 从 porencephaly 提升 congenital CMV；
2. **泛类→具体暴露/亚型**：`MCR_v1_seq100/112` 从 sympathomimetic toxicity 提升 bath-salt intoxication；`MCR_v1_seq100/74` 在 k=5 从 long-QT 提升 CPVT；
3. **外观→病理实体**：`DA_d2_heldout100/392` 从 melanonychia 提升 onychomatricoma；`DA_d2_heldout100/439` 从 commotio retinae 提升 lightning-induced maculopathy。

这些病例的共同点是 correct/complete candidate 已在 payload 中，比较器能引用一个区分性关系击败历史先验。first 的 51/300 不是生成器上限，而是“历史顺序直接作答案”的下限。

但 pairwise 也有可重复伤害。`MCR_seq200b/458` 的第一候选 LAM 是完整 reference；raw pairwise 在 k5/k10 都改选 Birt–Hogg–Dubé，尽管病例是 36 岁女性、弥漫薄壁肺囊肿、复发气胸且没有 BHD 的皮肤/肾脏线索。它把“复发气胸 + 囊肿”的共享特征当成决定性，却没有按性别、分布和系统伴随征做反事实比较。`DA_d2_heldout200b/633` 也是 pairwise 对 first 的另一共同 loss。故 comparator 必须输出 candidate-unique evidence 和最强反证，不能只生成流畅的 pairwise rationale。

pointwise 的主要弱点是输出量和 schema 稳定性。raw k10 pointwise 为 336,214 output tokens、337 physical attempts，pairwise 为 80,745 和 300；S1 k10 pointwise 为 410,754/395，pairwise为 81,332/303。当前 pointwise prompt 实际让模型对每个候选展开评分，成本是 pairwise 的约 4–5 倍，却没有更好端点。pairwise 因此是当前工程默认的合理选择，但依据是**成本、解析稳定性和不劣的准确率联合**，不是已证实的准确率 superiority。

## 宽度：新增暴露很少，干扰发生在正确候选已经存在时

k=5→k=10 每例机械增加 5 个候选，共 1,500 个新 exposure，只带来 2 个 strict reference exposure：`DA_d2_heldout200b/540` 的 acute oxalate nephropathy 和 `MCR_seq200b/480` 的 reference；没有 strict exposure loss。即每 750 个新增候选才有一个 strict reference 暴露，边际召回极低。

端点也没有单调上升：

- raw pointwise 65→60，`−1.67 pp`，4 gain/9 loss；
- raw pairwise 65→66，`+0.33 pp`，3/2；
- S1 pointwise 50→50、pairwise 53→54；
- graph pointwise 55→50、pairwise 53→53。

`DA_d2_heldout200b/540` 是理想宽度收益：新增 D14 acute oxalate nephropathy，raw 中又有晶体活检证据，k10 两个 comparator 都正确。`MCR_v1_seq100/74` 是干扰反例：CPVT 已在 k5 且 raw k5 pointwise/pairwise 都选中；k10 加入 Brugada、idiopathic VF、early-repolarization 等邻近 channelopathy 后，两者分别改选 idiopathic VF 和 Brugada。pairwise 甚至以“无 exercise-induced arrhythmia”为理由否定 CPVT，却忽略 collapse 发生于强噪声/应激情境。更宽的邻近候选集改变比较吸引域，并非单纯增加 recall。

这复现 E5 的 IIA 机制，但更精确：宽度损害主要不是把 gold 挤出，而是在 gold 已暴露时，用多个共享特征的 sibling 分散或重定向排序。RCR-3 的候选扩展应按新增 unique evidence/关系门控，而不是固定把 k 从 5 填到 10。

## 调用深度：实体新增、cap displacement 与重复 selector 方差必须分开

Call-2 相对 Call-1：81 个 pool 改变，117 个新候选进入、117 个旧候选被 cap 挤出；strict exposure 0 gain/0 loss。clinical-complete Top-1 62→65，4 gain/1 loss，`p=.375`、两重 Holm `q=.75`。五个 endpoint flip 中：

- `DA_d2_heldout100/439` 与 `MCR_seq200b/411` 的 pool 真正改变。前者 Call-2 加入 lightning-induced maculopathy，后者加入 plexiform schwannoma，均把正确具体实体带进选择路径，是可信的生成深度收益；
- `DA_d2_heldout100/372`、`MCR_v1_seq100/112`、`MCR_seq200b/335` 的 pool SHA 在 depth1/2 相同。MCR112 的 depth1 是一个 fail-closed schema row，depth2 才成功；另外两个是相同候选输入的独立 selector 翻转。它们不能归因于 Call-2 新信息。

Call-3 相对 Call-2：44 个 pool 改变，56 入/56 出，仍无 strict exposure变化。clinical-complete Top-1 65→66，2 gain/1 loss，`p=1`。三例中只有 `MCR_seq200b/283` 的 pool 发生改变并得到可信 rescue；`MCR_seq200b/335` 的 repair 与 `DA_d2_heldout100/372` 的 harm 都发生在相同 pool 上。

strict 层也只有 Call-3 的 `MCR_seq200b/283` 一个 rescue；总体 strict Top-1 为 25→25→26。历史 S3 另有 14 个病例、18 个标签在全部冻结 S2 中不存在，包括 metastatic melanoma、ALK-positive lung adenocarcinoma、rhabdomyolysis、sepsis、glioblastoma、PCNSL、Hurthle-cell carcinoma、disseminated aspergillosis/candidiasis 等。E12 按预注册将其审计但排除，避免让 S3 “凭空造候选”污染 S2 深度比较。这同时暴露旧流水线的阶段合同不完整：历史 shortlist 并非严格只是上游 proposal 的子集。

因此不能把 62→65→66 读成“三次调用逐步有效”。可归因于 pool 改变的完整 Top-1 新收益只有 Call-2 两例、Call-3 一例；其余净变化混有相同输入重采样和失败恢复。RCR-3 必须复用一次冻结 Call-3 comparator 来比较不同累计 pool，或至少对相同 payload 强制同一缓存结果；否则“调用深度”与“又抽一次 selector”不可识别。

## 运行、失败与网络路径

14 个实际在线选择臂合计 4,032 semantic calls、4,258 physical attempts、约 405.3 万 input tokens、217.8 万 output tokens，记录到 25 个 OpenRouter provider；DeepSeek v4 Flash 没有绑定 Groq 单点。主臂成功数除 graph 外为 298–300；所有失败保留并按 ITA 错误处理，没有根据结果好坏选择性补跑。

异质 screen 使用 Gemini 2.5 Flash，300 calls、327 attempts，全部由 OpenRouter 的 Google provider 成功返回，没有出现 Google region-not-supported 或公用机房 IP 拒绝。当前容器真正的 `direct` 模式无法解析 `openrouter.ai`，因此不能直连验证；可工作的路径是平台动态 `environment` proxy，而不是仓库内固定 `127.0.0.1:7890` 代理，也无需另启 Clash/VPN。

环境缺少 `openai`、`httpx` 和 `requests`，运行时 `auto` 选择 dependency-free `stdlib_openrouter`。共享 client 仍保留由环境参数选择的官方 OpenAI SDK 分支及测试；实验脚本没有把简易 HTTP 实现变成唯一生产路径。credential 未写入代码、日志、JSON 或 tar archive。

## 对 e7/RCR-3 各组件的定位

### 历史 S1 summarizer

优点是降低文本长度、突出一般临床框架。致命弱点是没有 completeness contract：病理、精确解剖、否定的作用对象、末段时间演化和病因线索都可被删除，还可能制造 key-fact 与 salient-finding 冲突。它不能再作为唯一病例表示；至多作为 raw/graph 旁路索引。

### 历史 S2/S3 candidate path

优点是即使 first 只有 17% complete Top-1，k5 pool 中已有足够候选让 comparator 提升约 5 pp。弱点是额外 S2 call 的新实体密度低，cap replacement 没有 evidence novelty 约束；历史 S3 又含 18 个无法回溯到 S2 的标签。下一版必须让每个 candidate ID 绑定 source call、type、unique supporting span 和反证，不允许 shortlist 新造无 provenance 实体。

### first/pointwise/pairwise selector

first 是稳定低成本负控制，但把 proposal order 偷换成诊断排序。pointwise 能纠正大量表现/病因错误，却输出冗长、schema failure 较多。pairwise 在当前 prompt 下以约四分之一输出 token 获得不劣结果，并且是唯一对 first 通过 primary 校正的 online comparator；但仍会对 LAM 等病例过度纠偏。默认应选 pairwise，同时加入 coverage guard、candidate-unique evidence 和反事实否证。

### typed graph

优点是显式记录 source quote、极性、scope、time 和 relation，在 May–Thurner 等解剖关系清楚的病例可恢复 raw 结果。弱点是构造失败率、长度和关系错误同时存在；“节点都在”不等于“决定性关系正确”。RCR Call-1 应把 graph 当可审计索引，selector 仍能回看原文 span，不能只读 graph serialization。

### strict bridge 与语义审计

strict bridge 可复现、不会把组件偷算完整，但对临床同义和安全具体化 recall 低。异质 screen 适合扩队列，却在 154/385 个根复核关系上过度授予等价，绝不能代替人工责任。E2 应把完整性和可识别性拆开盲审：先判输出对象与 reference 的关系，再判病例文本是否足以唯一要求该具体 reference。

## 对 RCR-3 的可执行约束与可证伪预测

1. Call-1 输出 relation/event skeleton，但每个 node/relation 必须回指原文 span；raw 始终可回看，graph 不作唯一真相。
2. Call-2 不是三个无类型长列表，而是 syndrome/anatomy、etiology/temporal、subtype/exception 三个视角的 batched proposal；每个候选附 `candidate_type`、unique evidence、missing obligation 和 strongest counterevidence。
3. registry 只作 exact/frozen-safe identity；解剖、病因、时相、分子修饰和复合对象不能通过字符串相似合并。
4. k 不固定填满。新增候选若没有候选独有证据，保留在 coverage ledger 而不进入主比较；报告 exposure gain、cap displacement 和 IIA harm。
5. Call-3 默认 completeness-first pairwise；同一 frozen comparator 同时评估累计 pool，避免把独立重采样误写成深度收益。
6. comparator 必须输出 decisive pair、source spans、最强反例及是否只解释表现；删除 rare-but-plausible 候选需显式反证。
7. 时间/范围只作软排序特征；不能把 S1 的“prolonged QT”式冲突或 graph 的错误 `contradicts` 变成 hard veto。
8. 对含作者诊断结论句的病例单独标记，报告保留/遮蔽该句的轨迹敏感性；这不是重复降方差实验，而是检验 raw 优势是否来自标签性文本。
9. 预注册失败条件：若 RCR-3 不能提高 complete exposure→Top-1 conversion，或新增候选造成的 loss 不少于 gain，或 relation skeleton 的关键关系错误仍接近 E6，则关系保留机制被否证。

E12 已经回答了“现有 e7 哪一段值得保留”：保留多候选覆盖和一次显式 comparator；停止以 S1 为唯一输入、停止无证据填宽、停止把额外独立 selector 抽样称为调用深度收益。RCR-3 的价值必须来自关系忠实、类型化候选、范围安全和可追溯对比，而不是把现有流水线简单再调用一次。
