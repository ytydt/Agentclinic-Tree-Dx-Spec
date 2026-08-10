# cursor4 轨迹差异与机制深度审计

审计对象：`ytydt/Agentclinic-Tree-Dx-Spec` 的 `cursor4` 分支  
固定版本：`a81631a3b34664fa273b58f2ba2a5e08790dd2d9`  
审计日期：2026-08-07  
覆盖：DiagnosisArena（DA）400 例、MedCaseReasoning（MCR）400 例；APHHM 仅纳入已有完整作答的 DA 200 例与 MCR 100 例。

## 结论先行

这次轨迹审计改变了问题的核心表述。

1. **“e7 只用极少调用、却追平数倍调用的强基线”这一成本前提不成立。** 逐例读取 `predictions.jsonl` 的 `cost.llm_calls` 后，e7 固定为 **6 次 LLM 调用/例**，B06 MAC 为 **4 次**，B07 MEDDx-style 为 **3 次**。当前文档把 B06/B07 写成约 40/30 次，恰好放大约 10 倍。e7 相对强基线不是更轻，而是分别多用 50% 和 100% 的 LLM 调用。
2. **现有结果也不能支持“e7 非劣”。** DA 上 e7 为 0.570，B06/B07 均为 0.615；配对 McNemar 的差异未达显著（分别 `p=0.0918/0.1078`），但“未显著更差”不等于通过预设界值的非劣检验。MCR 上各方法差异同样不显著。能说的是“当前样本未检出差异”，不能说“非劣”。
3. **正确集互补很大，但其来源不是单一的‘临床专长分工’。** e7 与两条强基线并集相对 e7 多覆盖 DA 78 例、MCR 41 例；反向 e7 独有 20/14 例。不过，在 DA 的 98 个排他正确题中，至少 **67 例**是候选到四选一答案的 mapper 桥接造成的。严格诊断候选层面的互补远小于 option@1 所显示的互补。
4. **e7 的额外入口调用确实增加召回，却几乎不转化。** 800 例中，后两次 S2 生成让金标首次进入候选池 54 次；只有 12 次存活到 S3、8 次存活到 S4。最终只有 2 个 e7 相对 v0 的独有胜例，能明确归因于“晚到候选存活并完成诊断”。瓶颈不是继续扩池，而是候选保真、剪枝与排序。
5. **MAC 的三位 doctor 并不是独立集成。** Doctor B 看见 A 的历史，C 看见 A+B；三轮列表平均两两 Jaccard 为 **0.972**，629/800 例三者 top-1 完全一致。Doctor A 已召回 327 例，后两轮合计只新增 3 例；supervisor 又从 doctor 并集中删掉 72 个金标。MAC 的偶发优势来自完整 vignette 与保留少数候选，而不是“多智能体独立多样性”。
6. **B07 的 refine 调用基本是死计算。** 800 例中 747 例输出完全不变；只改变候选集合 2 次，集合层面 0 次救回、1 次伤害；排序层面 6 次救回、7 次伤害，净效应约为 −1 例。它当前可见的强项是：用完整 vignette 在一个很短的 post-retrieval 列表上做较高效的 top-1 选择。因为代码没有 pre-retrieval diagnosis，对“检索是否导致优势”没有可识别的反事实。
7. **APHHM 的主要问题不是树还不够大，而是资源在重复候选上浪费，并在阶段接口中丢失信息。** 300/300 棵树都存在跨 parent 的完全同名重复；中位数 26 个叶子仅有 14 个唯一标签，中位重复率 47.2%。树召回 164/300 后，局部淘汰 60 例，全球排序再丢 17 例，只剩 87 例的 final-list 严格召回。更严重的是，最终得分与 final-list 金标匹配强烈脱钩：78 例“得分正确但 final list 无金标”，21 例“final list 有金标但得分错误”。
8. **病例表面特征没有形成可泛化的 e7/B06/B07 专长区域。** 在 DA、MCR 内分别检验 vignette 长度、否定、数值、模态、病理/影像/遗传、金标形态、选项相似度、S1 保留率与 S2 金标位置，并作组内 BH 校正后，`baseline-only vs e7-only` 与 `B06-only vs B07-only` 均无特征显著。当前互补更像病例边界上的随机/路径依赖翻转，而不是已经识别出的稳定 router 条件。
9. **可被数据支持的新论文中心命题**应是：额外 deliberation 大多在高度相关、重复的候选之间重排；真正限制性能的是从证据到候选、再到最终评测标签的“保真转化”，而不是搜索量本身。APHHM 的优势主张不能保留，但这套失败机制本身有研究价值。

---

## 1. 审计口径与可复现性

本审计只读取已提交日志，不重新调用模型或裁判，避免把新采样噪声混入机制归因。分析脚本为 `trajectory_audit/deep_audit.py`，主要产物包括：

- `tables/case_features_and_trajectories.csv`：800 例统一轨迹表；
- `tables/stage_funnels.csv`：各方法逐阶段金标存活漏斗；
- `tables/correct_set_overlap.csv`：逐方法正确集重合、Jaccard、phi 与精确 McNemar；
- `tables/feature_contrasts.csv`：病例、金标、选项与内部轨迹特征的组间检验及 BH 校正；
- `tables/mechanism_counts.json`：入口边际贡献、剪枝/排序损失、MAC 共识、MEDDx refine、APHHM 重复与阶段损失；
- `tables/cost_audit.csv`：逐例调用量账本。

“候选是否包含金标”使用仓库既有严格 label resolver：去括号后 exact/substring 匹配。这一口径适合做同一流水线内的存活追踪，但会漏掉部分医学同义词；因此：

- DA 的 option@1 是 relation-aware mapper 的最终判定；
- MCR 的 Acc@1 是 LLM judge 判定；
- 本文把“最终判定正确、但严格 resolver 无金标”统一称为**评测桥接**，而不武断称为 evaluator 错误；
- 对 MCR 尤其应把它解释为 judge–resolver 语义口径差异，需人工复核后才能判定哪一方更合理。

由于 APHHM 只覆盖 300 例，所有 APHHM 比较都明确限定在这一 answered subset，不与 800 例总体直接混算。

## 2. 首要校正：调用量叙事错误

### 2.1 强基线实际 LLM 调用

| 方法 | 已提交逐例账本 | 每例 LLM 调用 | 额外本地检索 | 相对 e7 |
|---|---|---:|---:|---:|
| e7 | `cost.llm_calls` | 6 | 0 | 1.00× |
| v0 | `cost.llm_calls` | 4 | 0 | 0.67× |
| B06 MAC | `cost.llm_calls` + 实现核查 | 4 | 0 | 0.67× |
| B07 MEDDx-style | `cost.llm_calls` + 实现核查 | 3 | 约 5.5–6.1 次 retrieval | 0.50× |

B06 的 4 次是三位顺序 doctor 加一次 supervisor；B07 的 3 次是 orchestrator、diagnose、refine。本地 retrieval 不能计作 LLM 调用。因而 `CLEAN_METRIC_VERDICT.md` 中 B06 `~40`、B07 `~30` 的表格不能继续使用。

此外，B07 日志明确写的是 **“MEDDxAgent-style complete-profile static adaptation”**，不是官方 MEDDx 私有栈。论文中应将它称为 MEDDx-style adaptation，避免把复现体结果等同于官方系统。

### 2.2 APHHM 成本只能给下界

APHHM 没有统一的逐例调用 ledger。由 annotate cache、带 evidence 的 P5 规则以及 DA mapper cache 反推：

| answered slice | n | 可确认调用下界/例 | 范围 |
|---|---:|---:|---:|
| DA seq100 | 100 | 98.48 | 49–158 |
| DA heldout100 | 100 | 97.55 | 28–154 |
| MCR v1 | 100 | 100.19 | 52–172 |

这些数字还不包括 vignette parser、tree generation 与未写入缓存的 retry，所以只可写作 **≥约 100 次/例**。`~300` 目前无法由提交产物验证。即使采用保守下界，APHHM 仍至少是 e7 的约 16 倍、B06 的约 25 倍、B07 的约 33 倍；“APHHM 高度冗余”仍成立，但精确倍率必须重建完整 ledger 后再写。

## 3. 表现、配对关系与“非劣”误读

### 3.1 800 例上的单臂表现

| 数据集 | e7 | v0 | B06 | B07 | 强基线相对 e7 |
|---|---:|---:|---:|---:|---|
| DA，n=400 | 0.570 | 0.5525 | **0.615** | **0.615** | +0.045 |
| MCR，n=400 | 0.2625 | 0.250 | **0.275** | 0.265 | +0.0125 / +0.0025 |

DA 的 e7–B06 配对格为：共同正确 186、e7 独有 42、B06 独有 60、共同错误 112，精确 McNemar `p=0.0918`。e7–B07 为 181/47/65/107，`p=0.1078`。MCR 的相应 p 值为 0.583 与 1.000。

这些数据只说明现有样本未排除“无差异”，也未排除 DA 上约 4.5 个百分点的真实劣势。非劣结论需要事先声明临床/任务可接受界值 Δ，并检验置信区间是否完全高于 `−Δ`；当前没有这一设计。

MCR 首个 n=100 slice 上 e7 的 0.28 还带有 25-arm 扫描后的赢家诅咒：后续 heldout 为 0.23，扩到 n=400 后为 0.2625。不能把首个 0.28 当作稳定优势。

### 3.2 正确集并集：有互补，但只是 oracle 上界

| 数据集 | e7 独有 | 强基线并集独有 | 共同正确 | 二者并集 | e7 单臂 |
|---|---:|---:|---:|---:|---:|
| DA | 20 | 78 | 208 | 306/400 = 0.765 | 0.570 |
| MCR | 14 | 41 | 91 | 146/400 = 0.365 | 0.2625 |
| 合计 | 34 | 119 | 299 | 452/800 = 0.565 | 0.4163 |

四臂 e7/v0/B06/B07 的 oracle union 为 DA 0.7875、MCR 0.3725、合计 0.580。这个并集只表示“事后知道谁答对时”的天花板，不是一个可部署 ensemble；在没有独立可验证的 gating signal 前，不能把 union 增益写成方法增益。

B06 与 B07 自身也并非同一个正确集：DA 共同正确 206、各自独有 40，Jaccard 0.720；MCR 共同正确 84、B06 独有 26、B07 独有 22，Jaccard 0.636。这证明轨迹确实分叉，但不证明分叉可预测。

## 4. 先拆掉评测接口，再谈临床机制

### 4.1 严格候选命中与最终得分严重脱钩

| 数据集/方法 | 最终得分正确 | 其中 strict final candidate 无金标 | 占正确数 |
|---|---:|---:|---:|
| DA e7 | 228 | 152 | 66.7% |
| DA B06 | 246 | 141 | 57.3% |
| DA B07 | 246 | 160 | 65.0% |
| MCR e7 | 105 | 30 | 28.6% |
| MCR B06 | 110 | 28 | 25.5% |
| MCR B07 | 106 | 31 | 29.2% |

DA 之所以更严重，是它要求自由文本诊断经 mapper 绑定到四个高度具体、常含限定词的选项。一个较粗或邻近诊断可以经病历与候选项关系被映成正确 option；反过来，候选含某个 broad gold component 也未必能选中正确限定项。

### 4.2 e7 与强基线的排他正确题如何构成

- **DA e7 独有 20 例**：15 例是 e7 mapper bridge，仅 5 例有严格金标候选支持。
- **DA 强基线并集独有 78 例**：52 例主要由 mapper bridge 解释，21 例来自 MAC 内部路径，5 例来自 MEDDx post-retrieval draft；57/78 至少有一个强基线的最终得分依赖评测桥接。
- **MCR e7 独有 14 例**：3 例为 judge–resolver gap，11 例有严格候选支持。
- **MCR 强基线并集独有 41 例**：13 例为 judge–resolver gap，20 例归于 MAC，6 例归于 MEDDx draft，2 例是 MEDDx refine 排序救回。

因此，153 个 e7–强基线并集的排他正确题里，至少 83 个先落在 evaluator/resolver 口径差异上；真正由内部金标生成、保留、排序造成的排他题约 70 个。DA 尤其由接口主导。

这不是说 mapper 一定“错”，而是说论文必须报告两个结果层：

1. **free-text concept 层**：金标/同义词是否进入候选、是否进入 final list、排位如何；
2. **task evaluator 层**：最终 option@1 或 LLM-judge Acc@1。

若只报告第二层，就会把诊断互补和接口互补混成一个现象。

## 5. e7：优势、退化点与真实边际机制

### 5.1 逐阶段漏斗

800 例合并后：

| 阶段 | 金标存活 | 相对上一阶段损失 |
|---|---:|---:|
| S2 三次生成并集 | 408/800 = 51.0% | — |
| S3 shortlist | 309/800 = 38.6% | 103 个已召回金标被剪掉；另有 4 个此前未命中的金标被 S3 引入 |
| S4 champion strict match | 162/800 = 20.3% | 再丢 147 个 |
| evaluator 得分正确 | 333/800 = 41.6% | 与 strict candidate 层不等价 |

e7 的瓶颈不是单纯“没有想到金标”：在 S2 已想到的 408 例中，有 250 例在 S3/S4 失去 strict gold，仅 158 例一路存活；另外 4 例由 S3 非单调地新引入，得到 162 个 S4 strict hit。原始入口命中到最终候选的保真转化率只有 158/408=38.7%。

### 5.2 额外两次生成的收益去哪了

第一轮 S2 已覆盖 354 例；后两轮首次补入 54 例。其后：

- 12/54 进入 S3；
- 8/54 成为 S4 strict champion；
- 18/54 最终得分正确，但多出的 10 例主要靠 evaluator bridge；
- e7 相对 4-call v0 的 92 个得分翻转中，只有 **2 例**能严格证明为“晚到候选存活并带来 e7 独有胜利”，均在 MCR。

所以“换条件多问两次”确实增加池召回，却受到强烈的下游选择抵消。改进方向不是无条件扩到 k=5/k=7，而是：让新颖但低先验的候选在 S3/S4 获得可校准的证据通道；并明确区分“候选覆盖”与“映射碰巧答对”。

### 5.3 S1 压缩是一个真实信息瓶颈

按病历模态词启发式统计，S1 平均保留约 76% 的原始模态，41/800 例没有保留任何被检测到的模态类型。这个指标较粗，且即使词被保留也可能发生语义反转。病例 78 与 74 展示了两种具体退化：

- **遗漏决定性事实**：神经 MR 明确“肿物起源于坐骨神经并沿神经走行”，S1 未保留；S4 因“完全囊性”把已保留的 schwannoma 压到 Tarlov cyst 后面。
- **数值解释错误**：QTc 380 ms 被 S1 描述成 prolonged QTc，后续所有选择围绕药物性 QT 延长展开，覆盖了运动/噪声诱发的肾上腺素能触发模式。

这说明 S1 的风险不只是 recall，而是**证据语义与极性保真**。后续增加候选调用无法修复一个被错误标准化的关键事实。

### 5.4 e7 的真实优势边界

e7 最可信的优势不是总体准确率，而是小概率出现的“异条件生成打破首轮锚定”。病例 346 中，首轮围绕 myxoid liposarcoma/Hodgkin；第二轮首次生成 myxoinflammatory fibroblastic sarcoma，且幸运地穿过 S3/S4。B06 的顺序 doctor 继续复制首轮锚点，B07 的检索 query 也围绕 Reed–Sternberg/lipoblast/myxoid 构造。此类罕见实体是入口多样性真正有用的区域，但当前只形成 2 个严格可归因的 e7-over-v0 胜例，不能扩张成总体机制结论。

## 6. B06 MAC：并非独立多专家，核心是顺序锚定与聚合损失

### 6.1 实现事实

代码不是三位 doctor 对同一病例独立作答后投票：Doctor B 读取 A 的 history，Doctor C 读取 A+B。这种协议天然促进一致，而非误差去相关。

| 指标，n=800 | 数值 |
|---|---:|
| Doctor A list 已召回金标 | 327 |
| 三位 doctor 并集召回 | 330 |
| 后两轮新增召回 | **3** |
| top-1 三者完全一致 | 629（78.6%） |
| 整个列表完全一致 | 239 |
| 平均两两 list Jaccard | **0.972** |
| supervisor 从 doctor list 中救回非 top-1 金标 | 52 |
| supervisor 删掉 doctor union 中已有金标 | **72** |
| supervisor 凭空生成 doctor 均未提及的金标 | 0 |

这排除了“多 agent 独立意见带来广泛候选覆盖”的解释。MAC 的后两位 doctor 几乎不扩大召回，supervisor 也只是 filter/reranker，并且净损失金标。

### 6.2 它为什么仍会赢一些题

MAC 的可见优势有两类：

1. **直接读取完整 vignette**，避免 e7 S1 的压缩损失。病例 78 中，后两位 doctor 能把 schwannoma 提到第一位，所依赖的是原文中的明确 nerve-origin 证据。
2. **top-2 supervisor 偶尔保留非共识候选**。在 52 个 aggregation recovery 中，金标已在某位 doctor 的列表里但不在共同 top-1；supervisor 将其保住。

其系统性弱点也同样清楚：顺序可见 history 使早期错误成为共享锚点。病例 74 中三位 doctor 虽曾把 CPVT 放到第 3 位，却共同把正常 QTc 误读与 risperidone 线索放大，supervisor 最终删掉 CPVT。病例 94 中，所有 doctor 都接受病历内的 provisional branchial cleft cyst，所谓“共识”只是同一信息条件下的相关错误。

因此 MAC 的合理机制标签不是“群体智慧”，而是**full-vignette sequential self-consistency + bounded aggregation**。要声称多智能体优势，必须补做 history 隔离的 parallel-doctor 反事实。

## 7. B07 MEDDx-style：强在短列表转化，不足以归因给 retrieval/refine

### 7.1 refine 的净效应

| refine 行为，n=800 | 次数 |
|---|---:|
| 完全不变 | 747（93.4%） |
| 候选集合改变 | 2 |
| 集合层面救回/伤害 | 0 / 1 |
| 排序层面救回/伤害 | 6 / 7 |

病例 62 是少数真实 rescue：18 个月、脂肪性分叶大腿肿块，draft 已含 `Lipoma, Lipoblastoma`，refine 仅把 Lipoblastoma 调到首位；病例 34 则反向把本来首位正确的 Tonsillolith 下移。总体看，第三次 refine 调用没有正的可测边际价值。

### 7.2 可见强项

B07 的 post-retrieval draft strict top-2 召回仅 27.3%，但 strict top-1 为 21.3%，即在它已经提出的很短列表中有较高首位转化。MCR 上约为 21.3/28.0=76%，而 e7 为 20.3/39.0=52%。这更符合**窄候选、高精度选择**，不是广覆盖搜索。

### 7.3 当前无法识别 retrieval 的因果贡献

实现先 retrieval、后唯一一次 diagnosis；仓库没有相同 prompt/seed 下的 no-retrieval diagnosis。因而“检索帮助了病例 X”与“诊断模型本来就会答对”在观测日志中不可分。病例 346 与 74 还显示 query 会继承显著但错误的病理/药物锚点，使检索成为 confirmation loop。

严谨的机制实验应固定病例、query 生成与诊断调用，仅把 retrieved chunks 替换为空、随机、正确命中或 hard-negative，做配对比较；同时直接删掉 refine 检验准确率是否不降。

## 8. APHHM：搜索冗余、非单调扩张、局部剪枝与全局契约破裂

### 8.1 answered subset 上并没有新的互补覆盖

在 APHHM 已作答的 300 例上：APHHM、e7、B06 的准确率都约 0.48，B07 为 0.46；强基线并集为 0.567。与四个 core arms 的 union 比较，APHHM 独有 9 例、core 独有 60 例、共同正确 135 例。9 个 APHHM 独有题中只有 3 个 final list 有 strict gold，另 6 个仍是评测桥接。

因此 APHHM 并未用约百次以上调用占领一个稳定的新病例区域。其少数真胜例值得研究，但不是总体优势。

### 8.2 漏斗定位

| APHHM 阶段，n=300 | 金标存活 | 阶段损失 |
|---|---:|---:|
| 完整树 | 164（54.7%） | tree miss 136 |
| local champions | 104（34.7%） | local elimination 60，即 tree hits 的 36.6% |
| final list | 87（29.0%） | global loss 17，即 local survivors 的 16.3% |
| evaluator 得分正确 | 144（48.0%） | 与 final list 严重脱钩 |

最终 2×2 表是：final strict gold 且得分正确 66；得分正确但 final 无 gold 78；final 有 gold 但得分错误 21；两者都无 135。也就是说，144 个“正确”里 54.2% 没有 strict final gold；87 个 final-list hit 中 24.1% 又没有变成得分。APHHM 的内部诊断层与对外答案层没有形成可靠契约。

### 8.3 树不是有效扩张，而是大量重复分配预算

- 300/300 例存在跨 parent 的完全同名候选；
- 中位 tree leaves 26，唯一 label 仅 14；
- 中位 duplicate fraction 47.2%；
- 中位每例有 6 个 label 被重复放在多个 parent；
- 139/300 例的金标或同义匹配散落于多个 leaf/parent；宽松 substring resolver 可能放大该数字，但完全同名重复本身不受此影响。

从 frozen 到 annotate，叶子均值由 18.28 增至 31.15，树召回只由 50.3% 增至 54.7%；期间出现 72 个 rescue 和 59 个 harm。纯追加式扩张不应让已有命中消失，因此这些 harm 暗示 rewrite、dedupe、重标或 resolver 边界导致的**非单调候选 churn**。

### 8.4 两类结构性失败

**错误的 L1 轴让整个树系统性失明。** DA case 5 的 biopsy 已给出 giant cells/no atypia，但 L1 主要按 sinonasal inflammatory/neoplastic/vascular/infectious 展开，多个 parent 反复生成 angiofibroma、rhabdomyosarcoma、Ewing 等，exact giant cell reparative granuloma 始终缺席。层次搜索不是天然更宽；如果第一层互斥轴与决定性组织病理不对齐，后续预算只会在错误子空间内重复。

**全局 arbiter 不遵守层次 posterior，重复候选的代表选择改变答案粒度。** DA case 241 中，L1 `Infectious Endophthalmitis` posterior 为 0.995，B1.1 `Strep intermedius endophthalmitis` 为 0.758；但 pre-compatibility joint arbiter 把来自低先验 parent、global posterior 仅约 0.000377 的 B2.3 `Streptococcal endophthalmitis` 排第一。granularity merge 以该粗标签为代表，把更具体且含 iris abscess 线索的 B1.1 合并到第二位，最终难以绑定要求“endogenous endophthalmitis with iris abscess”的选项。这里不是候选不足，而是跨阶段评分契约断裂。

### 8.5 APHHM 的真实优势

MCR case 19 的 malignant spindle tumor 同时 α-SMA/vimentin/desmin 阳性。e7 已生成 Leiomyosarcoma，却因颅内/脑膜位置先验在 S4 选择 sarcomatoid meningioma；MAC 只到 generic sarcoma，B07 偏向 SFT/hemangiopericytoma。APHHM 则让 Leiomyosarcoma 在一个低先验 branch 中长期存活，global arbiter 最终借 IHC 把它提升到第一。

这是 APHHM 最有说服力的机制：**为低先验、跨解剖常规分区但有强特异证据的实体保留生存通道**。然而同一 arbiter 在 case 241 又无视 posterior，说明它尚不是稳定机制，而是偶发成功。要使这一点成为论文贡献，应把“低先验候选保存”实现成显式、可校准、可消融的规则，而非依赖一个不透明全局排序调用。

## 9. vignette、金标、候选项是否存在共性退化特征

### 9.1 方法

在 DA 与 MCR 内分别比较：

- `baseline union only` vs `e7 only`；
- `B06 only` vs `B07 only`；
- 四个 core arms 全错 vs 至少一臂正确。

连续变量使用组间检验并报告标准化均值差；二元变量用 Fisher exact/odds ratio；每个 contrast、dataset 内做 Benjamini–Hochberg 校正。特征含病例长度/段落、否定、数字、误导/暂定措辞、证据模态，病理/遗传/影像/微生物/实验室/治疗反应/definitive test，金标长度、罕见度、括号/缩写/复合/限定词/综合征、金标是否出现在 vignette/source title，DA 金标与 distractor 的词面相似度，以及 e7 的 S1 模态保留、S2 候选量/金标排位/新颖度。

### 9.2 没有发现可稳健路由的“谁更擅长什么病例”

`baseline-only vs e7-only` 在 DA、MCR 均无特征通过 FDR；`B06-only vs B07-only` 同样无特征通过 FDR。DA 中 baseline-only 的 gold–distractor 词面相似度原始 `p=0.037`，校正后 `q=0.954`；MCR 中 e7-only 的 S2 gold rank 原始 `p=0.0099`，校正后 `q=0.278`。都不能作为规律。

这否定了一个过早的解释：目前没有证据说“e7 专长某种病理题、MAC 专长长 vignette、MEDDx 专长检索型题”。案例上可以找到这样的故事，但总体特征检验不支持稳定分区。正确集差异更可能由细粒度证据如何被压缩、候选措辞、随机采样、早期锚定及 evaluator 接口共同造成。

### 9.3 DA 的共同失败显示的是标签/映射可供性，而非纯临床难度

DA 四臂全错 85 例、至少一臂正确 315 例。通过 FDR 的特征为：

| 特征 | 全错 | 至少一臂正确 | BH q |
|---|---:|---:|---:|
| gold tokens | 4.74 | 6.17 | 0.0020 |
| gold chars | 48.9 | 61.5 | 0.0051 |
| gold 为 composite | 25.9% | 45.7% | 0.0110 |
| gold–distractor 最大词面相似度 | 0.502 | 0.562 | 0.0202 |
| gold 含 qualifier | 16.5% | 31.7% | 0.0362 |
| gold token rarity | 5.350 | 5.196 | 0.0445 |

较长、复合、带限定词的金标反而更容易被至少一个系统答对；短而词汇罕见的标签更容易四臂全错。合理解释是，长 composite label 暴露了更多 broad component，使自由文本候选更容易被 mapper 搭桥；短 eponym/稀有 syndrome 缺少词面和概念把手。这个结果首先是**标签形态与接口可供性**，不能直接解释成临床病例更容易。

MCR 上没有任何共同失败特征通过 FDR。`gold exact in vignette` 在全错/至少一臂正确为 2.8%/10.1%，原始 `p=0.00286`、`q=0.080`，仅可作后续假设。

### 9.4 病例报告的“诊断惊奇”会制造不可辨识题

MCR case 94 的可见病历反复支持 branchial cleft cyst：超声如此解释，FNA/cystogram 也相符，文本在术后病理揭晓前结束；source title 才泄露最终是 schwannoma。四个 core arms 全部选 provisional diagnosis。APHHM 虽在三个 parent 下生成多个 schwannoma 变体，但 neoplastic L1 posterior 约 0.018，局部概率极低，最终仍选 branchial cyst。

这种题的错误不能简单归因于“推理不够深”：给定可见证据，金标是病例报告的 surprise outcome，可能在信息论上欠定。应给 MCR 增加 `visible-evidence sufficiency` 人工标签，区分可由 vignette 合理推出、需要未展示病理、以及题源标题泄漏三类。

## 10. 八个代表性轨迹的因果解剖

| 数据集/病例 | 金标 | 关键分叉 | 所暴露机制 |
|---|---|---|---|
| MCR 346 | Myxoinflammatory fibroblastic sarcoma | e7 第 2 轮首次提出 exact rare entity 并存活；MAC/B07 都沿 liposarcoma/Hodgkin 锚定 | e7 异条件生成的真实但稀少收益 |
| MCR 62 | Lipoblastoma | e7 生成后被 S3 剪掉；B07 refine 只做顺序翻转即救回 | 召回不是瓶颈终点；rank 可决定结果 |
| MCR 78 | Schwannoma | e7 S1 丢失 nerve-origin；MAC 读完整原文而正确 | 压缩损失，而非多 agent 多样性 |
| MCR 74 | CPVT | QTc 380 被误写为 prolonged；所有系统围绕 risperidone/Long-QT 锚定 | 数值语义反转 + shared salience failure |
| DA 5 | Giant cell reparative granuloma | APHHM 的 L1 家族轴遗漏组织病理实体，树内重复错误分支 | 层次 partition miss，预算无法补救 |
| MCR 19 | Leiomyosarcoma | APHHM 保存低先验实体并由 IHC 逆转位置先验 | APHHM 少数真实机制优势 |
| MCR 94 | Schwannoma | 可见证据支持 provisional cyst，真实金标只在后续病理/标题揭晓 | benchmark sufficiency / surprise-outcome 问题 |
| DA 241 | Endogenous endophthalmitis with iris abscess | 高 posterior 具体候选被低 posterior 粗候选代表化、mapper 绑定受损 | APHHM posterior–arbiter–granularity 契约破裂 |

另一个纯接口案例是 DA 27：所有方法大致生成 generic Sweet syndrome，而选项含三个高度相近的 Sweet 亚型；backbone/baseline 使用的 mapper 与 APHHM mapper 不同，前者选对、后者未选对。这不应标作“APHHM 剪枝失败”，而是 mapper protocol confound。

## 11. 对论文主张的修订

### 11.1 当前不可保留

- APHHM 显著优于最强基线；
- e7 以远少于强基线的 LLM 调用达到非劣表现；
- MAC 的收益来自独立多智能体多样性；
- B07 的收益已经被证明来自 retrieval 或 refine；
- APHHM 的树规模/层次本身带来稳定增益；
- oracle union 说明已有一个可部署组合器。

### 11.2 当前可以支持

> 在两个数据集的已提交轨迹中，增加 deliberation 主要扩大、复制或重排高度相关候选，并未稳定提高准确率。e7 的额外入口生成提高候选召回，但绝大部分新增候选在剪枝与排序中消失；MAC 的顺序 doctor 高度相关，MEDDx-style refine 几乎无边际作用；APHHM 则受到候选重复、非单调扩张、局部淘汰和跨阶段评分契约失配限制。方法间的大量排他正确还被 evaluator/mapper 接口显著放大。

更凝练的机制命题是：

> **搜索广度不是当前系统的主要稀缺资源；稀缺的是从原始证据到规范化候选、从候选到最终标签的可校准保真转化。**

APHHM 的可研究价值可以改为“为什么大规模层次 deliberation 未转化为性能”，并把 failure anatomy 作为实证贡献，而不是保留无数据支撑的 superiority 结论。

## 12. 下一轮最有信息量的可证伪实验

按优先级排序：

1. **修复计量层。** 所有方法记录统一的 LLM/retrieval/token/latency/retry ledger；重建 APHHM 全模块成本。把 B06/B07 的错误 `~40/~30` 从所有稿件与表格移除。
2. **统一外部接口。** 所有臂使用同一 mapper、同一输入字段与同一 final-list 长度；同时报告 strict concept recall/top-k、人工同义词 adjudication 与最终 task score。对 DA 近邻选项增加 blinded 双人复核。
3. **e7 入口—转化因果分解。** 用缓存固定 call-1，逐步添加 call-2/3；分别冻结 S3、冻结 S4、使用 oracle keep-gold，量化 54 个新增召回究竟被哪一层消耗。再做 full-vignette vs S1 summary 的配对实验和关键事实 injection。
4. **MAC 去锚定实验。** 三位 doctor 并行、互不可见 vs 当前顺序协议；再比较 supervisor、简单 union、保留每位 top-1。主要终点应是 list Jaccard、新增 gold recall、aggregation loss，而不只是最终 Acc@1。
5. **MEDDx 2×2 因子实验。** retrieval on/off × refine on/off；固定 diagnose prompt、seed/temperature 与 query，另设 random/hard-negative chunks。若删 refine 不降性能，可直接移除第三次 LLM 调用。
6. **APHHM 单调、去重、校准实验。** 使用全局 canonical entity ID；扩张只增不删；每个实体只占一个预算位但保留 provenance；global ranking 比较 `parent posterior × local likelihood`、纯 posterior sort 与当前 LLM arbiter；显式测试 duplicate representative 的粒度选择。
7. **APHHM 低先验保存消融。** 预注册“高特异证据、低位置/流行先验”病例，比较是否设保护槽位；验证 case 19 式优势能否重复，同时检查 case 241 式失配是否下降。
8. **重评 benchmark sufficiency。** 对 MCR 标注 visible evidence 是否足以推出 final diagnosis、是否依赖未展示病理、source title 是否泄漏；分层报告性能，避免把病例报告 surprise 当作一般诊断错误。
9. **最后才训练 router。** 只在接口清洗后，用 nested cross-validation 测试内部不确定性特征（S2/S3 rank margin、MAC disagreement、retrieval support、APHHM entropy）。当前表面特征无 FDR 信号，直接对 800 例拟合 selector 极易过拟合 oracle union。
10. **统计设计预注册。** 若要声称非劣，先定 Δ；准确率用配对区间/McNemar，重复运行用 case 与 run 的混合效应 logistic model；多臂与亚组检验控制 FDR。至少重复若干独立 run，因为 temperature=0 的 API 也不保证位级确定性。

### 建议的最小论文实验包

若资源有限，最优先只跑四组：统一 mapper 的 free-text/option 双层评测；e7 full-vignette 与 S1 summary；MAC parallel 与 sequential；APHHM canonical dedupe + posterior-consistent arbiter。它们分别直接检验评测桥接、压缩损失、顺序锚定和层次契约失配，是当前最可能推翻或确认上述机制的实验。

## 13. 限制

- 本审计是对既有轨迹的机制归因，除代码结构和确定性阶段计数外，仍不能替代随机化反事实。
- strict resolver 对医学同义词不完美；MCR 的 judge–resolver gap 必须人工 adjudicate。
- vignette/金标特征使用规则与词面代理，只适合发现强信号，不代表完整临床语义。
- APHHM 仅有 300 例，且成本是缓存下界；不能外推到未作答 500 例。
- DA 与 MCR 的 evaluator、标签形态和任务结构不同，不应把 pooled feature significance 当作跨数据集机制；本报告的特征结论以数据集内检验为准。
- 正确集 union 是 oracle ceiling；没有经 heldout 验证的 selector 前，不是系统性能。

## 最终判断

“e7 以几次调用追平数倍调用强基线”不是一个需要解释的真实现象，因为强基线实际只用 3–4 次 LLM 调用，少于 e7 的 6 次。真正值得解释的是：**为什么 3、4、6 乃至 ≥约 100 次调用都停留在相近性能带，却在个案上剧烈翻转。**

证据给出的回答是四重的：

1. 生成调用高度相关，新增覆盖很快饱和；
2. 压缩、局部剪枝和最终排序持续丢掉已生成的正确候选；
3. 顺序 history、检索 query 与显著线索形成路径依赖和共同锚定；
4. 自由文本候选到 benchmark 标签的映射接口制造了大量表观互补。

APHHM 把这些问题放大：它搜索更多，但约一半叶子是重复标签；它召回更多，却在局部/全局阶段继续丢失；它偶尔保存关键低先验实体，却没有稳定的 posterior-consistent 选择契约。因此，下一篇可信的论文不应再问“如何堆更多 deliberation”，而应问：**怎样让一次已经出现的正确诊断，以可追踪、可校准、接口一致的方式活到最终答案。**
