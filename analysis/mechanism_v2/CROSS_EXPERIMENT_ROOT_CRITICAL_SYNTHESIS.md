# Mechanism-v2 跨实验根级病例轨迹解剖与批判性综合

> 分支：`cursor4`
> 综合范围：E0–E12、E14x、RCR-3，以及 E6x/E7c/E2 full-800 canonical-endpoint replay 这些由实验中新暴露的缺口
> 推断单位：病例；DA 与 MCR 分层；现有 800 例一律视为开发/机制数据
> 审计责任：只有 E2 完成全病例、全臂、端点隐藏的 human-root census；另 79 臂已完成臂隐藏三 reviewer 模型面板临床 census，必须保留 `model_panel` 血缘，不得冒充 root truth
> 结构化证据：`results/CROSS_EXPERIMENT_ROOT_SYNTHESIS/`

## 0. 最终裁决

这一轮没有识别出一个在所有临床对象、所有终点上普遍占优的系统。识别出来的是一条比“模型不够聪明”更具体、也更可干预的共同机制：

> **多调用系统的主要损失来自信息在输入、表示、候选、身份、暴露、比较、诊断对象完整性和任务投影之间连续转化时发生的删除、伪造、重复加权与不可逆选择。**

调用数本身既不是能力，也不是成本效益的充分代理。一次额外调用可以像 E10 一样，在几乎没有新增候选时通过 rank propagation 改变当前排序；也可以像 E14x 一样生成 135 个全部存活的新实体，却没有一个 `safe-exact` reference discovery。E14x 旧 6 repair/15 harm/13 neutral 是 34 个 triggered flips 的相对临床贴切度序数审计，不是 canonical clinical-complete 净损害；新全臂模型面板结果接近零，另在 triggered MCR 的 C∪P 上出现探索性正信号。真正需要计算的是：新增的、可验证的关系信息或可归因排名修正，是否大于新增干扰、关系损失、不可逆删除与接口失真。

当前开发机制证据支持以下系统决策：

1. **默认仍用 Lite-like 三调用**：两次相互独立、读取完整原文的 proposal，加一次冻结候选池 comparator。它不是已确认的普遍最佳，而是在当前 RCR-3 未通过预注册门槛后最安全的对照路径。
2. **当前 RCR-3 不上线，但否决理由从“成功轨迹更差”收窄为“端到端合同不可靠”**。迁移后的 model-panel clinical-complete 为 Lite/RCR3/Compact4 = 22/13/13（complete 对比无 Holm survivor），C∪P 为 130/109/67；ITA 中 RCR3−Lite −7.00pp、`q=.03142`，但共同服务病例只差 −0.39pp、`q=1`；Compact4 相对 Lite 的 −21.00pp ITA 也缩为共同服务 −1.72pp。部署否决仍有独立证据：`safe-exact` frontier exposure 低 7.00pp，Holm `q=.000311`；至少 69/119 个 span drop 是物质性证据，20/60 条分层 relation 错误或无支持，selector 自报 complete 的冠军只有 9/66 被根审计确认完整。
3. **当前第四调用 gate 关闭**。`unexplained_spans + low margin` 检测到的是“当前生成文本未解释什么”，不是“缺失哪个诊断对象或决定性关系”。E14x 足以否定现有 gate 的部署证据，不足以否定未来受约束的 Call-4。
4. **exact/frozen-synonym identity 是硬安全约束**，但不是准确率插件。E7b 消除了 160 个被选概念的身份污染并恢复 reference exposure，却没有形成显著 Top-1 增益；安全身份之后仍要解决宽度压力、关系方向与 requested-object projection。
5. **raw 原文必须始终可回看**。S1 摘要和当前生成图都不能作为唯一事实源；结构字段是新增临床命题，不是免费格式。原文中的作者诊断性断言又必须单独标记，不能把其保留效应冒充独立医学推理。
6. **候选池应小而可分，但不能固定填满某个 k**。E5 在共同服务病例中仍显示 width4→8 complete −17.68pp（约 −4.42pp/新增候选），但 sibling −11.52pp、synonym +4.85pp（C∪P +6.67pp）、component 约 0，且 DA/MCR 的九臂共同服务斜率为 −2.87/−6.33pp/候选。E12 又证明 k=5→10 每增加 750 个 exposure 才带来一个 `safe-exact` reference exposure。有效宽度由新增候选的独有证据、对象类型与拓扑决定，不由槽位数决定。
7. **时间/范围只允许软约束，RAG 只允许 typed admission**。E8 的 9 个 hard reference veto 经根审计无一成立；E11 的“relevant” chunk 只有 6.62% case-specific。没有通过关系、对象和范围门控的上下文，安全行为是不用，而不是强制注入。
8. **真实诊断能力只允许由全量盲法根级 `clinical-complete` 排名**。`safe-exact` 是冻结保守下界，`legacy-chain` 只诊断历史 resolver，`compatible-partial` 记录对象压平，`task` 必须按 DA mapper 与 MCR calibrated judge 分开解释。当前只有 E2 满足 human-root 准入合同。79 个迁移臂的 23,046 个 served Top-1 均有 clinical-complete/compatible-partial/union 模型面板关系，可更新敏感性和机制结论，却不能进入 root-only capability leaderboard。

在用户明确排除重复多运行、确认集扩容和 provider/retry 统一之后，冻结 crosswalk 中可执行且有科学识别价值的实验已经全部完成。形式化 E14 router 依赖被排除的 E13 latent multi-run labels，不能被诚实地标记为“待跑一个普通臂”；当前真实 gate 已由 E14x 直接检验并关闭。因此 **scientific execution remaining = 0**。本次又把 **79 个实验臂的 clinical metric-migration gap 降到 0**；E7a 三臂仍为结构 replay、临床端点 N/A。补充充值后重试成功，fresh task 新命名空间现已完成 **5,839/5,839**，无失败、无历史值插补；26 个 Holm survivor 必须保留为 DA 7 个与 MCR 19 个 family-specific 对比，禁止汇成 pooled `ALL task`。

### 0.1 新指标覆盖核查

机器覆盖矩阵逐一登记 16 个实验、91 个实验臂，并禁止非合格行进入能力榜：

| 覆盖合同 | 实验 | 臂数 | 能否给出盲法临床完全等价率 |
|---|---|---:|---|
| 全病例、全臂、盲法根级 complete/compatible-partial/union census | E2 | 9 | 是；当前唯一合格集合 |
| 臂隐藏三 reviewer model-panel complete/compatible-partial/union census | E1、E4–E6x、E7b–E12、E14x、RCR3 | 79 | 否；完整模型面板敏感性，不是 human-root |
| 无 fresh selector output | E7a | 3 | N/A |

因此，91 臂中 9 个 E2 臂有 human-root 合同，79 臂已有完整模型面板临床合同且 migration gap=0，另 3 臂结构上不适用。最终 5,351 个 unique case–prediction relation 中，1,693 个直接复用 E2 root、251 个由 frozen-safe identity 确定、3,407 个由三 reviewer 臂盲评审；1,899 个新关系 unanimous、1,356 个 majority、152 个三方分裂保持 `U`。修复 sentinel 选择上限后，628 张卡严格分为 556×2、61×1、11×0，共 1,173 个隐藏 E2 sentinel；不再有一张卡超过两个 sentinel。完整逐臂记录见 `results/ENDPOINT_COVERAGE_AUDIT/endpoint_coverage_matrix.json`。

聚合面板在这 1,173 个 sentinel 上的 fine-label accuracy 为 70.93%，complete boundary accuracy/precision/recall 为 97.70%/84.06%/78.38%，C∪P 为 91.90%/87.74%/93.37%。对 3,407 个新关系，三 reviewer 的 Fleiss κ 为 fine `.597`、complete `.740`、C∪P `.794`。这比旧 sentinel 分配更严格地校准了二元边界，也再次说明 majority 不是 human root。

## 1. 证据等级与推断纪律

综合账本不把所有实验的 p 值放在一张表里竞赛，而按它们能识别的对象分层：

| 等级 | 含义 | 代表实验 | 可写边界 |
|---|---|---|---|
| A | 调用前冻结的病例级配对/因子干预，含 ITA | E1、E4–E12、RCR3 | 可归因到冻结处理合同；不能越过具体实现外推 |
| B | 冻结 replay、full-census adjudication 或结构化重建 | E2、E7a | 可校正测量与状态会计；不等于新运行因果效应 |
| C | 上游不可比的回顾性/探索性证据 | E14x | 可做部署否决和假说定位；不能估算理想处理系数 |
| D | 根代理逐案/逐关系责任审计 | 全部关键实验 | 支持机制方向与错误链；富集队列计数不能当总体发生率 |

三条纪律贯穿本文。

第一，**处理效果与处理保真度分开**。E7c 的 directional arm 没有赢，不足以否定正确 typed ontology；但 64.82% 的内部方向一致率和 80.58% 的重复 pair consistency 已足以否定“这个实现可部署”。E11 同理：query-top RAG 失败的是一个只有 6.62% case-specific chunk 的实际处理，不是理想检索。

第二，**规范端点有明确主从合同和准入门**。`clinical-complete` 衡量根级完整临床对象，只有在全病例、全臂、盲法根级 adjudication 下才可作真实能力主端点；`safe-exact` 提供冻结、可重放的保守下界；`legacy-chain` 只复现 substring/resolver 历史；`compatible-partial` 只表示 parent/component 覆盖，不能偷换成完整正确；`complete-or-compatible-partial` 是覆盖敏感性而不是完整率；`task` 在 DA 是 option mapper、在 MCR 是缓存且经校准的语义 judge，不能合并成同一个能力 estimand。identifiability 再问病例是否唯一要求该完整 reference。

第三，**病例审计只为其冻结覆盖负责**。E2 对 800/800 病例完成 identity census，并对完整 candidate registry 中的 3,103 个 candidate-reference 关系形成完整 partition：旧 400 例 1,673 个关系，加新 400 例 1,430 个关系（其中 1,371 条新增人工关系码、59 条冻结 safe-exact 确定性 complete）；九臂实际冠军形成 2,878 个 unique case-output cluster，7,200 case-arm 行无 clinical missing。RCR-3 的队列臂可见，只穷尽 endpoint-critical selected relations，另以 proxy 补全，并非盲审或遍历全部未选候选。两者不能用同一句“人工审计过”模糊覆盖差异。

执行 crosswalk 以 `EXPERIMENT_REGISTER.md` 为冻结口径。当前 sparse 工作区可直接读取 R1–R6 综合正文；独立 APHHM-C/MOSAIC 审计原文没有随此 sparse checkout 出现，因此本文对其提案映射只使用基线时已冻结进 register 的 crosswalk，不伪称本轮重新读取了缺失原文。width、ranker 与 clean-Compact 项分别保留为 E5、E4、RCR3 的独立可识别处理。

## 2. 实验闭环：做了什么，排除了什么

| 任务簇 | 状态 | 最终识别结果 |
|---|---|---|
| E0/E3 runtime、payload、cost、claim ledger | implemented | 每个 stage、物理 attempt、provider、缓存与 endpoint 进入可追责账本 |
| E1 输入污染 | complete + migrated | options 进入生成；固定格式下 H/F Top-1 分别 +41.0/+40.2pp，是标签供给与搜索塌缩；H options shuffle 的 complete ITA −11.0pp、`q=.0182`，共同服务则 −7.19pp、`q=.230`，不能把接口失败和排序轨迹混写 |
| E2 完整性与可辨识性 | complete + full-800 replay | 455/800 unique-full；7,200 case-arm 的 complete/compatible-partial/union 无缺失；overall/DA clinical-complete 无 coherent Holm survivor，MCR 的 Collapse3c–IMPC `q=.045615`；family interaction `q=.228489`；DA/MCR task 不可合并 |
| E4 selector crossover | complete + migrated | model-panel 中 Forest/e7/pairwise 都优于 evidence-count；Forest−e7 complete 仅 raw `p=.0386`、Holm `q=.231`，pairwise−Forest 净 0 |
| E5 IIA/width | complete + migrated | ITA 中所有 add/width 臂均低于 base4，但含 34–36 个 differential failure；common-served width8−base4 complete −17.68pp、width8−width6 −6.71pp，sibling −11.52pp，synonym +4.85pp/C∪P +6.67pp，component 约 0 |
| E6/E6x representation | complete + migrated | ITA graph−raw complete/C∪P −10.0/−16.0pp；common-served complete 缩为 −6.0pp、`q=.0602`，C∪P 仍 −10.0pp、`q=.00141`；flat 同样只在 common-served C∪P 保留确认 deficit；unpadded−padded 无临床差异 |
| E7a/b/c identity/relation | complete + migrated | exact identity 相对 legacy complete +3.25pp、`q=.00885`，但 C∪P 净 0；typed/directional/bounded 无确认收益 |
| E8 temporal veto | complete + migrated | 9/9 hard gold veto 无效；从 full-response failure 中正式恢复 11 个有效 Top-1 后，invalid-time ITA 仍显著更差，但共同服务 complete 为 0pp、C∪P −2.4pp 且均 `q=1`，损失来自接口服务路径 |
| E9 Forest views | complete + migrated | model-panel real−single complete +3.25pp、`q=.01328`；real−duplicate +3.50pp、`q=.01031`；旧 6/1/4 仍仅是富集机制重编码 |
| E10 B06 | complete + migrated | complete 四对比均 null；C∪P 在 history×RRF +6.0pp、`q=.00155`，isolated Supervisor +4.25pp、`q=.00454` |
| E11 B07 | complete + migrated | complete 七对比全 null；refine 在 off 与 hard-negative 条件下提高 C∪P，而非完整对象 |
| E12 e7 | complete + migrated | clinical-complete Holm39 survivor=0；survivor 转移到 raw pairwise 的 C∪P，六个 first 臂是同一逐例结构控制 |
| E14x current gate | complete exploratory + migrated | 全 300 例 complete/C∪P 近零；triggered MCR65 C∪P 6/0、未校正 `p=.03125` 仅探索性；旧 6/15 是序数贴切度而非 canonical 净伤害 |
| RCR-3 / Compact4 | complete + migrated | complete 无 Holm survivor；C∪P ITA RCR−Lite −7.00pp、`q=.03142`，第三 generator−Lite −21.00pp；共同服务仅 −0.39/−1.72pp 且 `q=1`，部署否决主要由 schema/service、span 与 relation fidelity 支撑 |
| E13 多运行、provider-normalized programme | excluded | 属用户明确排除的重复/降方差程序 |
| formal E14 router after E13 | prerequisite excluded | 不使用不存在的 latent labels 伪造 router；实际 gate 已由 E14x 处理 |
| new confirmation cohort | excluded | 用户明确排除扩容确认集 |

两份源审计都未预先写出的实质缺口也没有被漏掉：E6x 处理 tokenizer sentinel 混杂；E7c 检验方向图和 bounded inheritance；E14x 检验真实 runtime gate；E2 从旧的结局富集 400 例扩展为 800/800 identity census、关系全 partition 和规范端点 replay；RCR-3 又增加 relation、span-drop、frontier 和 selector self-calibration 的独立根审计。

## 3. 统一因果链：损失发生在哪里

```text
runtime input
  → raw/derived representation
  → candidate proposals
  → entity/relation registry
  → actual exposed frontier
  → evidence/veto/retrieval weighting
  → comparator/ranking
  → diagnostic object and completeness
  → mapper/judge task projection
```

这不是单调漏斗。后段 mapper 可以救回一个没有严格 surface 的临床正确对象，也可以把错误 manifestation 映成正确选项；候选扩展可以增加 gold exposure，也可以改变原有候选的相对落点；结构化可以压缩，也可以新增一条错误因果命题。每一层都既可能 rescue，也可能 harm。

### 3.1 输入与 benchmark 对象

E1 证明 options 不只是 selector 可见标签。固定格式下，H 的 raw gold recall 22→129、Top-1 16→94；F 为 20→125、13→93。候选 option-copy 上升约 42pp，输出 token 下降，说明搜索被标签供给收缩。clean reordering 的净分近零，却翻转 133/180 个 H champion 和 165/199 个 F champion；“均值不变”并不意味着推理路径稳定。

E2 又证明 benchmark reference 本身不是统一难度对象：800 例中 455 unique-full、139 family-only、131 unsupported-specificity、70 insufficient-information、5 multiple-complete。分族更反直觉：DA 有 285/400（71.25%）unique-full，MCR 只有 170/400（42.50%）；但 DA 的 clinical-complete 仅 2.25%–4.25%，MCR 为 21.25%–26.75%。DA 不是“题更不可判”，而是 reference 常要求病因、部位、亚型、并发症、时序或复合对象，而冠军常停在 parent/component。MCR 的 ceiling 则更受 reference identifiability 约束。因此，“所有方法都错”必须拆成病例不可唯一识别、对象范围丢失和真正实体替换三类。

### 3.2 表示不是容器，而是临床断言层

E6 的图节点可逐字引用原文，边仍然可以错。风险因素被写成病例内因果，早期阴性 CT 与后续阳性 MRI 被写成矛盾，确认检查被写成病程进展，失败治疗先被写成 `responds_to` 再靠另一条 `contradicts` 修补。30 个根审计 graph 中 25 个至少有一个关系语义错误；在臂盲外部筛查、定向根纠错并由 proxy 补全的旧 sensitivity 中，graph 相对 raw 净差 −7.63pp（24 raw-only/5 graph-only，`p=.00055`）。新全量 model-panel ITA 为 graph−raw complete −10.0pp、C∪P −16.0pp；但共同服务后 complete 缩为 −6.0pp、`q=.0602`，C∪P 仍 −10.0pp、`q=.00141`。flat−raw 也由 ITA complete −7.67pp 缩为共同服务 −3.21pp、`q=.530`，而 C∪P 仍 −8.84pp、`q=.0143`。因此确定的是“表示+服务损害兼容覆盖”，不是“成功服务时 complete 必然下降”的单一路径；这些仍不是 E2 级 human-root 临床率。

E6x 排除了一个容易但错误的解释：flat 的 `[LENGTH_CONTROL_PAD]` 约等于 8 tokenizer token，去掉后 prompt token 平均下降 64.9%，同口径 complete-proxy 仅 +1.57pp、`p=.481`。因此 padding 是严重成本混杂，却不能解释关系损失。更值得警惕的是 95.29% champion flip：温度 0 并没有把模型变成同一确定函数，非临床 sentinel、provider 路径或早期 token 分叉都能重写完整候选轨迹。

E12 对历史 e7 提供同方向但更具体的证据。S1 不是因为“短”而差，而是删除组织学、精确解剖、病原、时序与诊断桥，还能把 QTc 380 ms 同时写成正常值和 prolonged QT。raw comparator 的优势中又混有病例作者的 `was suspected` 类诊断性句子。正确的系统约束不是“永远 raw”，而是：原文 span 可回看；derived fact 标记它是原文陈述、作者诊断断言还是模型推断；任何关系若无 span 或确定性规则支持，只能进入 hypothesis/quarantine，不得成为 veto 或 frontier priority。

RCR-3 没有遵守这一强度。119 个 exact-span drop 至少 69 个物质性；sanitizer 删除 invalid evidence ID，却让依赖它的 candidate 继续存活，形成“引用 fail-closed、候选语义 fail-open”。这比普通 schema failure 更危险：系统看似可解释，实际解释链已断。

### 3.3 多视图、多医生与候选宽度：多样性既是资源也是干扰

E9 把 Forest 的三视图拆成四种状态。real views 比 balanced single anchor `safe-exact` +2.25pp（10/1，`p=.0117`）。旧 70 例定向审计把 `same_entity` 与 `scope_or_surface_artifact` 混成二元可接受，并曾把 10 个 real-only lower-bound gain 写成 6 个“临床 gain”；复核发现后者包含缺失部位、亚型和复合成分，不能满足 clinical-complete，也没有独立 compatible-partial 列。故 6/1/4 只保留为历史机制重编码，不能作为临床净效应；“3 个 new capture”也只能作为富集队列假说。语义 cluster/observation 比 0.552，证明视图约一半重叠。exact duplicate 仍翻转 51/399 champion，role rotation 翻转 58/400；重复不是信息，却会改变模型内部权重。

本次全臂模型面板迁移补上发生率层：real−single clinical-complete +3.25pp（16/3，Holm `q=.01328`），real−duplicate +3.50pp（17/3，`q=.01031`）；C∪P 的对应对比均未过 Holm，role rotation 与 duplicate placebo 也无 complete 净益。这是“real views 对完整对象有小幅信号”的新增发现，但 Top-1 迁移不能把它定位为 pool capture、selector conversion 或独立投票。

E10 则给出一个重要反例，迫使旧主张升级：sequential history 将 union 6.82 压到 5.21、pairwise Jaccard .689 拉到 .954，D3 在 400 例只新增 6 个 concept。历史二元 `same_entity + acceptable_clinical_variant` 只能称 binary-acceptable proxy。新模型面板中所有 clinical-complete 主对比均为 Holm-null，但 C∪P 在 history×RRF 下 +6.0pp（34/10，`q=.00155`），isolated Supervisor 相对 RRF +4.25pp（22/5，`q=.00454`）。因此可写“条件性兼容覆盖/排序转换”，不可写“完整对象提升”；history 压缩候选并传播排名、也可能永久删除正确少数意见的结构机制保持。它是一种 consensus compressor，不是三位独立专家。

E5 与 E12 共同否定固定宽度神话，但 E5 必须先拆成两个 estimand。ITA 中 base4 served 200/200，width6/8 仅 166/164，因此 width8−base4 complete −30.0pp 同时包含 candidate membership 与 36 个 differential failure；“每个 addition 都有害”只是一条端到端 feasibility+membership 结论。对两臂共同服务病例，width4→6 为 −10.84pp（6/24，width-family `q=.00286`），width4→8 为 −17.68pp（5/34，`q=7.29e-6`），width6→8 为 −6.71pp（6/17，`q=.03469`）。在九臂全部服务的 162 例上，72.84%→54.94%，相当于 −4.48pp/新增候选；这个量级局部复现 APHHM 旧约 −4.6pp/slot 的描述性斜率，却不是通用系数。

异质性本身是更重要的新发现。九臂共同服务中 DA width4→8 为 −2.87pp/候选，MCR 为 −6.33pp/候选；typed common-served complete 中 sibling −11.52pp，synonym +4.85pp（其 C∪P +6.67pp、`q=.02954`），component +0.60pp，unrelated −3.01pp，parent −6.63pp。也就是说 raw width 只是 candidate topology、类型与 benchmark mechanism 的代理；MCR 更多是新增 plausible disease 直接夺冠，DA 更多是共享近邻重排。

E12 的历史池中 k5→k10 增加 1,500 个 exposure，只增加 2 个 `safe-exact` reference exposure；raw pointwise 反而 −1.67pp，pairwise +0.33pp。E5 识别 reference 已暴露时的局部成员干扰，E12 识别低 marginal-yield historical proposals 的端到端变化，两者并不矛盾。结论不是 `k=5`，而是候选只有在带来独有、可引用 discriminator 时才进入主比较；其余保留在 coverage ledger。

### 3.4 身份安全与关系安全是两个问题

E7a 在 800 例中找到 299 例 unsafe substring fold、1,199 个 unsafe pair，exact identity 平均恢复 0.550 个可独立寻址节点。E7b 的 fresh selector 将 contaminated champion 160→0，并在 unsafe stratum 带来 11 exposure restoration/1 loss（`p=.00635`）；Top-1 仅 8 gain/5 loss，`p=.581`。这说明 identity 是安全约束，不是充分治疗。

原因在 E7c 被直接看见：exact pool 固定后，加入 LLM directional graph 仍为 −0.67pp；bounded inheritance 净 0。776 个可由 lexical containment 检查方向的边只有 64.82% 一致；重复 label-pair consistency 80.58%。generic 非语义 graph 也能翻转 47 个 champion，其中 15 个 flip 两个 champion 都不是 graph node。这里存在三种不同风险：错误临床方向、正确但任务无关的 salience、纯上下文 placebo instability。不能把它们合并为“关系推理无效”。

安全合同应当是：identity 只合并 exact/frozen synonyms；parent/subtype、etiology/manifestation、disease/complication、component/composite 分开；方向、inverse、duplicate、cycle、type signature 由确定性规则检查；证据只沿经验证的 edge 继承；没有 requested-object projection 的 relation 不进入冠军排序。

### 3.5 阴性、时间与检索：更多结构可能等于更多伪证据

E8 的 hard selector 对暴露 reference 作 9 次绝对 veto。根审计：8 次临床 overreach，1 次由 builder 将阳性 CT 反写成“无异常”，0 次成立。soft 删除这些 veto，但旧共同成功病例只 18→21，`p=.453`。迁移核查又发现 11 行虽 full-response schema 失败，却有合法、非空的 Top-1；本轮把 Top-1 evaluability 与完整事件/veto schema 成功正式分离，恢复这些冠军，同时在 provenance 保留源失败。恢复后 invalid−soft 的 complete ITA 为 −4.55pp、`q=.0388`，C∪P −15.45pp、`q=5.84e-8`；共同服务则为 0/−2.4pp、均 `q=1`。所以 invalid arm 的显著损失是接口服务路径，不是错误时间推理的独立系数。soft 解决的是错误排除，并不能生成缺失候选、恢复复合对象或纠正 subtype identity。合法 ledger 行顺序产生 24.6% champion flip，非法 time/episode 置换产生 23.2%，两者净准确都约 0。这说明模型确实“响应”字段，却没有被识别出方向正确的时间推理。

E11 把同一风险扩展到外部上下文。所谓 relevant bundle 的 1,950 chunks 中只有 129 个 case-specific；71.64% 无病例适配。hard-negative 又混入同病/亚型支持，不能当干净安慰剂。新模型面板中 relevant−off clinical-complete −1.25pp（2/7，Holm `q=1`），C∪P 恰为 0pp（16/16，`q=1`）；七个 complete 主对比全部为 null。generic refine 仅在 secondary C∪P 的 off 条件下 +4.25pp（19/2，`q=.00155`）、hard-negative 下 +3.50pp（17/3，`q=.01546`），没有 complete 增益。它提示的是兼容疾病族软着陆，同时仍会跨四个上下文一致删除 mucormycosis 等 rare-but-plausible candidate。

因此 RAG 的入口不应是“病例全文相似”。需要 typed information need：要查的是 etiologic relation、subtype defining criterion、test sensitivity，还是 competitor counterevidence；chunk admission 必须区分 same entity/subtype、broader context、competitor 和 generic。未通过门控就返回 no-RAG comparator。

### 3.6 selector 能修什么，不能修什么

E4 是最干净的 selector 证据。400 个相同 pool 上，Forest 41、tournament 38、ledger 37、e7 33、evidence-count 17；Forest 对 e7 的 9/1 `safe-exact` gain 完全来自 MCR。17 个 lower-bound discordance 中，Forest 的 9 gain 只有 5 个强临床 gain、1 个未充分确认、3 个 surface/scope artifact。Forest 的优势是病例特异证据整合，不是“来自 Forest 的候选”或投票；它无法改善 338 个 `safe-exact`-unexposed 病例。

E12 的旧 proxy 中 raw k5/k10 pairwise 相对 frozen first 曾有两个 clinical-complete Holm survivor；新模型面板 Holm39 下 **clinical-complete survivor=0**，故该主张撤回。survivor 转移到 secondary C∪P：raw pairwise−first 在 k5 +9.67pp（48/19，`q=.01930`）、k10 +12.33pp（51/14，`q=.000175`），raw−S1 在 k10 pairwise +8.67pp（38/12，`q=.01162`）。六个 first 臂逐例 Top-1 完全相同，是共享结构控制而非六份独立证据。pairwise 目前成为工程默认的理由只能是 C∪P 覆盖、输出 token、schema 稳定且结果不劣，而不是已确认的完整准确率优势。

同样，E10 的 Supervisor 只在真实 minority opinion 存在的 isolated 条件下有较明显语义价值；history 已经压平 union 后，它无法复活池外候选。RCR-3 selector 的 `complete/strong/fits` 自报字段更不能作 gate：66 个 self-complete 冠军 38 个根审计为错误实体。模型对自己 rationale 的一致性不是外部校准。

### 3.7 task projection 不是 reasoning 的尾声，而是另一处理层

E2 full-800 replay 先把五个经常被混写的端点固定为不同对象：

| Arm | safe-exact | legacy-chain | clinical-complete | compatible-partial | task | complete-or-compatible-partial |
|---|---:|---:|---:|---:|---:|---:|
| Collapse3c | 8.50% | 21.12% | **15.25%** | 32.88% | **46.12%** | 48.12% |
| Multistance | **8.62%** | 22.62% | 15.12% | 32.50% | 45.00% | 47.62% |
| Lite | 7.88% | 23.75% | 13.25% | 33.75% | 42.88% | 47.00% |
| Forest | 8.25% | **26.62%** | 13.38% | 34.88% | 45.12% | **48.25%** |
| IMPC | 8.50% | 26.50% | 12.25% | 34.38% | 43.38% | 46.62% |
| e7 | 7.38% | 20.25% | 14.12% | 29.88% | 41.62% | 44.00% |
| v0 | 7.50% | 19.38% | 12.88% | 30.88% | 40.12% | 43.75% |
| B06 | 7.75% | 24.25% | 13.12% | 35.00% | 44.50% | 48.12% |
| B07 | 7.12% | 21.25% | 12.62% | **35.25%** | 44.00% | 47.88% |

分族后，同一 task 百分比的含义明显不同：

| Arm | DA complete | DA compatible-partial | DA task mapper | MCR complete | MCR compatible-partial | MCR task judge |
|---|---:|---:|---:|---:|---:|---:|
| Collapse3c | 3.75% | 52.75% | 63.00% | 26.75% | 13.00% | 29.25% |
| Multistance | 4.25% | 52.50% | 61.75% | 26.00% | 12.50% | 28.25% |
| Lite | 4.00% | 53.75% | 60.25% | 22.50% | 13.75% | 25.50% |
| Forest | 3.50% | 53.25% | 63.75% | 23.25% | 16.50% | 26.50% |
| IMPC | 3.25% | 52.75% | 62.50% | 21.25% | 16.00% | 24.25% |
| e7 | 3.75% | 48.75% | 57.00% | 24.50% | 11.00% | 26.25% |
| v0 | 2.25% | 47.50% | 55.25% | 23.50% | 14.25% | 25.00% |
| B06 | 2.25% | 53.50% | 61.50% | 24.00% | 16.50% | 27.50% |
| B07 | 3.00% | 53.50% | 61.50% | 22.25% | 17.00% | 26.50% |

这张表没有支持“旧 E 臂只有个位数所以能力崩溃”的解释。所有系统的 `safe-exact` 都只有 7.12%–8.62%，因为它只接受 exact/frozen-safe-synonym；旧强基线 19.38%–26.62% 的所谓 `strict`/concept 数实际是 `legacy-chain`，其中含 substring 与父类兼容。真正统一的 `clinical-complete` 为 12.25%–15.25%。Forest/IMPC 的 legacy-chain 排名靠前，却没有转化为完整临床对象领先，正说明 chain 不应再承担主指标角色。

`task` 又不能跨 family 读成同一能力。DA option mapper 的 task 为 55.25%–63.75%，但相对 complete 的 PPV 仅 3.62%–6.48%，大量把 parent/component/manifestation 投成目标选项；MCR cached calibrated judge 的 task 为 24.25%–29.25%，PPV 80.19%–88.50%、sensitivity 91.84%–96.77%、specificity 93.25%–95.75%，可作内部自动评估但仍需根级校准。把二者平均得到的 40.12%–46.12% 只能描述 benchmark interface，不能称为真实诊断准确率。

79 臂 fresh task replay 现在也已闭环：2,975 个 DA mapper payload 与 2,864 个 MCR semantic-judge payload，共 5,839/5,839 成功。各实验预冻结 family 内 Holm 后，ITA 有 26 个 task survivor（DA 7、MCR 19）；改用两臂都成功服务的 post-treatment sensitivity 后是 15 个（DA 4、MCR 11）。这不是互相冲突的计数，也不是可相加的“能力胜利”：二者 estimand 不同，两个 benchmark family 的 gold、evaluator 和错误含义也不同，代码根本不生成 `scope=ALL, endpoint=task` 的对比。此前 3,337 个 cache-complete 行只作 provenance 的限制已解除；禁止 pooling 的测量边界没有解除。

`legacy-chain` 的全臂校准进一步解释为何旧端点不能代替新端点。在 23,046 个 served case-arm occurrence 上，它对 clinical-complete 的 PPV/recall 为 56.48%/74.47%，对 C∪P 则为 98.72%/48.90%。也就是说它几乎不把明显不相容对象叫作“命中”，却只覆盖约一半的完整或兼容输出，并把相当一部分 partial 当 complete；它是稀疏 compatible-coverage marker，不是完整诊断准确率。

配对推断也必须落在病例而非 7,200 case-arm 行。Collapse3c→Multistance complete 为 122→121（22/21，−0.125pp，未校正 95% CI [−1.75,+1.50]）；→Forest 122→107（37/22，−1.875pp [−3.75,0]）；→IMPC 122→98（49/25，−3.00pp [−5.00,−0.875]，raw `p=.00708`，overall coherent Holm `q=.070843`）。e7→v0 为 113→103，B06→e7 为 105→113，B07→B06 为 101→105。最终统计合同分别冻结 ALL、DA、MCR 三个相干 10 对比家族：ALL 与 DA 无 survivor；MCR 中 Collapse3c 相对 IMPC 高 5.50pp（未校正 CI [1.75,9.25]，`q=.045615`）。混合 30-row 的同一对比 `q=.136846` 仅作保守敏感性；DA–MCR family interaction 经十对比 Holm 后 `q=.228489`，因此这是 MCR 家族内证据，不是跨 benchmark 或全系统胜者证明。

E14x 提供更直接的 mapper placebo：18 个 DA option flip 中 8 个 champion 文本完全相同；错误的 Adult-onset Still disease 和 ARVC 还能映到 gold option。option@1 不能为 gate 或候选生成提供正反馈。任何系统报告都必须保存 pre-mapper diagnosis、object relation、clinical completeness 和 task projection 的完整 transition。

### 3.8 complete 净差必须闭合到 relation transition

E2 不只重算分数，还把每个预定义配对拆成四个互斥的 complete 边界事件：右臂从 P/X/M/N 进入 C 的 `specificity_rescue` 与 `object_rescue`，以及从 C 退出到 P 或 X/M/N 的 `scope_compression` 与 `catastrophic_substitution`。例如 Collapse3c→Forest 的 22 个 complete gain 恰为 7 specificity + 15 object rescue；37 个 loss 恰为 15 compression + 22 catastrophic，因此净差是 −15/800。其余关键对比同样闭合：

| 配对（右−左） | specificity rescue | object rescue | scope compression | catastrophic substitution | complete gain/loss |
|---|---:|---:|---:|---:|---:|
| Collapse3c→Multistance | 11 | 10 | 7 | 15 | 21/22 |
| Collapse3c→Forest | 7 | 15 | 15 | 22 | 22/37 |
| Collapse3c→IMPC | 6 | 19 | 17 | 32 | 25/49 |
| e7→v0 | 3 | 8 | 14 | 7 | 11/21 |
| B06→e7 | 21 | 15 | 8 | 20 | 36/28 |
| B07→B06 | 15 | 17 | 13 | 15 | 32/28 |

这改写了系统差异的含义。IMPC 不是“不会诊断”：它有六对比中最多的 19 个 object rescue；但同时有最多的 32 个 catastrophic substitution。Forest 既能把 HTRA1 错误遗传对象纠正，也会把已完整的游离壁破裂压成 MI parent。B06/B07 也不是简单的 specific/broad 二分：B06 能保住 H3N2，却会把 May–Thurner 压成 DVT。净 accuracy 是两条方向相反机制的代数和，只有 transition 才告诉下一版该保留什么、阻断什么。

identifiability 还是效应修饰符。e7→v0 在 unique-full 455 例为 −2.64pp，在 nonunique 345 例反为 +0.58pp；B06→e7 分别为 +2.42pp 与 −0.87pp。更保守的 parent 输出在模糊 reference 上可能少犯过特异错误，却在证据充分病例中压掉决定性 scope；更积极的 specificity 恰好相反。分层点估计与 percentile CI 是未校正描述量；正式的 slice-fixed case bootstrap 对每个 ALL/DA/MCR 十交互家族做 Holm 后无 survivor（最小 `q` 分别 `.154492/1/.586471`）。因此它们是需要复验的机制方向，不是确认性亚组优越性，但已经足以否定“一个总体均值就是固定系统能力”的粗糙解释。

### 3.9 迁移后的 endpoint transition 形成四类，而不是一条 accuracy 轴

把每个配对的 C、P 与非兼容状态转移保留下来后，确认效应可归为四种工程类型：

1. **specificity restorer**：E7b exact−legacy complete +3.25pp、`q=.00885`，15 个 gain 是 P→C，而 C∪P 净 −0.50pp；E9 real−single complete +3.25pp、`q=.01328`，其中 8 个 P→C。它们主要把已有正确 family 收紧成完整对象，而不是普遍扩 coverage。
2. **compatible soft landing**：E10 history×RRF 的 34 个 C∪P gain 中 29 个落在 P；isolated Supervisor 22 个 gain 中 21 个为 P；E11 off-refine 的 19 个 gain 中 16 个为 P；E12 raw-k10 pairwise 的 51 个 gain 中 40 个为 P。它们改善 secondary coverage，但不能据此声称 complete reasoning。
3. **selector rescue against a weak control**：E4 Forest 相对 evidence-count 的 81 个 C∪P gain 为 51P/30C，且有 16 个 P→C；可确认的是 evidence integration 胜过弱计数器，Forest−e7 complete 仍 `q=.231`，不能升级为 universal selector winner。
4. **destructive interference**：E5 的宽池在共同服务中同时降低 C 与 C∪P；E6 的 derived representation 在共同服务中 complete 证据减弱，但 C∪P deficit 仍确认。前者是候选拓扑干扰，后者是表示丢失，不能压成同一个“selector coefficient”。

这套类型学直接导向两层状态：coverage ledger 负责不丢候选，evidence-qualified main frontier 只接纳有独有 discriminator 的对象；comparator 先保护 complete，再把 P 明确报告为软着陆，而不是把二者合并成一次“正确”。

## 4. 跨实验同案深解剖

单实验平均效应无法显示同一病例如何在不同系统里重复暴露相同薄弱环节。以下病例不是 anecdotal victory list；每一条都用于区分哪一阶段改变了什么。

### 4.1 `MCR_seq200b/320`：May–Thurner 的决定性 CT 如何连续两次被丢失

原文的诊断桥是右髂总动脉压迫左髂总静脉并伴充盈缺损。E12 中 raw 和 graph 能从 manifestation `DVT` 上溯到 May–Thurner，S1 删除压迫关系后，selector 明确以“缺少 confirmatory imaging”为理由停在 DVT。这里 representation→rationale→rank 的链条是可观察的。

RCR-3 又以不同实现重复同一错误：span alignment 丢掉完整 CT pattern，May–Thurner 的 support 失效，固定 frontier 将它删除，selector 最终只能选 DVT。这个病例否定了“只要 typed candidate 曾经生成，关系系统就会保护它”。保护必须作用于原始 span、候选证据和 frontier 三个连续状态；任何一处断裂，requested-object field 都只是 JSON 装饰。

### 4.2 `MCR_seq200b/345`：HHRH 是同一正确对象的四种 rescue，也是四种不稳定

HHRH 的 discriminator 是 FGF23-independent phosphate wasting、1,25-D 与 nephrocalcinosis 的联合关系。

- E8 hard veto 因 normal urine calcium/no stones 错误排除 HHRH；soft 恢复，但 legal-order 又能翻掉收益。
- E9 的 mechanism view 首次补入正确对象与决定性关系，构成少数真正的 new-capture-to-top1。
- E10 sequential D2 发现 HHRH、D3 复制；RRF 仍被 X-linked hypophosphatemia 共识压住，Supervisor 才用 vignette 转换。
- E11 relevant draft 先退到 generic hypophosphatemic rickets，refine 再利用 undetectable FGF23 等恢复 HHRH。

这不是“四个模块都有效”。它说明正确候选可以由 view、history、refine 多条路径到达，但没有一个模块稳定保证关系不被顺序、共识或泛知识覆盖。评价一个 rescue 必须记录它新增了哪条 relation、是否原文支持、后续是否在固定 comparator 下仍成立。

### 4.3 `MCR_seq200b/326`：Brucellosis 与 spinal abscess 的对象投影

E7b 的 generic non-equivalence graph 把 exact selector 的 Brucellosis 推向其 spinal epidural abscess complication。E9 mechanism view 同时提供羊组织暴露与系统病因，真正从局部表现上移到 Brucellosis。E10 中 RRF 能保留 etiology，Supervisor 有时偏好影像 manifestation；E11 relevant refine 再次将 Brucellosis 与 spinal abscess 反转。

四个实验的共同变量不是词面相似，而是“题目要求病因还是并发症”。relation graph 若不编码 `etiology_of/complication_of` 和 requested object，更多临床相关上下文只会让两个都合理的对象更易互换。

### 4.4 `MCR_v2_seq100/208`：Takotsubo 的“更具体但更错”

raw 保留 apical/mid akinesia、basal hyperkinesia 和病例作者的 suspicion；S1 压成 ACS/arrhythmia，在线 selector 偏向 MI/stent thrombosis。RCR-3 raw registry 曾有 generic Takotsubo，却在 frontier 中被 CAD/MI 和多个 subtype 挤掉，最后选择与 apical pattern 冲突的 mid-ventricular subtype。

这条轨迹说明 specificity 不是单调价值。只有被关系支持的 specificity 才是完整性；没有 pattern match 的 subtype 是错误实体。另一方面，raw 中含 author diagnostic assertion，故 raw 的胜利同时包含事实保真和叙事标签保留，不能全部归功于模型独立推理。

### 4.5 `MCR_seq200b/458`：LAM 已在池中，失败仍来自路径与 comparator

E6x 去掉非临床 padding 可把 BHD 翻回 LAM；E9 的真实视图或 exact duplicate 又能通过重复强化 LAM；E12 raw pairwise 却把正确 first LAM 改成 BHD，忽略年轻女性、弥漫薄壁囊肿、复发气胸和缺少 BHD 皮肤/肾脏线索。

这里不存在候选缺失。相同疾病对在非临床 sentinel、重复上下文和 comparator prompt 下来回翻转，证明“候选已暴露”仍不足以定位为 selector 能力；需要 candidate-unique discriminator、反事实缺失项和一致的 frozen payload。重复不是独立证据，流畅 pairwise rationale 也不保证真正比较了差异。

### 4.6 `MCR_v1_seq100/74`：CPVT 的关系被摘要矛盾和 sibling 池共同破坏

E12 的 S1 一处记录 QTc 380 ms/无 Brugada，另一处又写 prolonged QT；selector 因此选择 long-QT 或药物性 QT 延长。raw k5 comparator 能利用强噪声/应激诱发 collapse 恢复 CPVT；k10 加入 Brugada、idiopathic VF、early repolarization 等 sibling 后，又可把 CPVT 挤掉。E10 sequential history 在另一轨迹中通过 rank propagation 救回 CPVT，E6x 的 padding扰动却能把它翻成 Brugada。

同一病例同时展示 relation deletion、内部 contradiction、sibling interference 和 trajectory instability。修复其中任何一个，不代表其余机制消失。生产系统需要在候选对上问“CPVT 独有的 trigger 是什么、B/long-QT 必须满足而病例缺少什么”，而不是累计 channelopathy 共性。

### 4.7 `MCR_v2_seq100/173`：慢性硬膜下血肿被 polarity 与 history 双重删除

E8 builder 将明确显示 15 mm 硬膜下积液和 13 mm 中线移位的阳性 CT quote 写成“无其他异常”，随后据此 hard-veto chronic subdural hematoma。E10 isolated D3 能补回 chronicity，sequential D3 读取错误锚后又回到前文模板。

这个病例把两个看似不同的架构弱点连接起来：结构化 builder 可制造伪阴性，顺序协作可复制伪阴性。若 downstream 只看到 ledger/历史而不能回看原文，更多调用只会增加错误一致性。

### 4.8 `MCR_seq200b/480`：撤销错误 veto 仍救不回 bulbar MG

无早期复视、吞咽困难或肢体无力不能绝对排除 bulbar myasthenia gravis；E8 soft 撤销 veto 后仍锚在 TIA，因为六事件预算又漏掉 fatigue/neostigmine 等更关键 discriminator。E11 的 relevant、random、hard-negative 三种 bundle 都进一步推向血管、偏头痛或脱髓鞘解释；off refine 也被常见危险因素吸引。E12 更宽 exposure 并没有保证转换。

这说明 safety fix 与 performance fix 必须分开。禁止 hard veto 是无条件安全要求；它不自动提供遗漏证据、正确 prior 或病因转换。把 soft-veto 的不显著净益当成“hard veto 没问题”，或把撤销 veto 当成“系统已修好”，都同样错误。

### 4.9 `DA_d2_heldout200b/729`：Forest 的稳定 parent 如何掩盖游离壁破裂

reference 是急性 MI 后左室游离壁破裂。Collapse3c 输出 `MI with cardiac rupture`（C）；Forest 只输出 `MI`（P）。这不是苛求命名：病例在 STEMI 后出现剧烈胸背痛、心包积液，CTA 直接见造影剂从 myocardium 漏入 pericardial cavity。Forest 保留常见 parent，却删除了决定病例对象和处置风险的并发症。DA mapper 仍可能把 MI 映到正确选项，所以 task success 会把 scope compression 擦掉。

### 4.10 `MCR_seq200b/292`：ALCL 被高显著 mimic 替换

Collapse3c 为 anaplastic large-cell lymphoma（C），Forest 变为 Hodgkin lymphoma（X）。大而多形、肾形核细胞与 CD30 强阳性提供表面吸引，但 CD15、CD3、CD20、ALK、EMA 全阴性和整体形态支持 ALK-negative ALCL。这里不是 parent/alias 分歧，而是 discriminator 没有压过 Reed–Sternberg-like salience。它解释 Forest 相对 Collapse3c 的 catastrophic tail，也限制了“多视图证据更多所以更可靠”的外推。

### 4.11 `MCR_seq200b/395`：同一 Kummell 病例区分替换与压平

延迟性椎体塌陷、intravertebral vacuum cleft、double-line sign 且无脓肿/肿块，使 Kummell disease 可辨识。Collapse3c 与 v0 保留 C；MultiStance 猜测无病例支持的 steroid-induced osteoporosis（N），是 catastrophic substitution；e7 输出 vertebral osteonecrosis（P），是相容机制但丢失命名综合征的 scope compression。同一病例把“错误实体”和“正确 parent”分开，证明 compatible-partial 不能与 complete 合并，N 也不能与 P 都写成普通 miss。

### 4.12 `DA_d2_heldout200b/628`：共现不能替代因果时间方向

B06 保留 angiographically proven STEMI 后两小时出现发热、摩擦音、diffuse ST elevation/PR depression 的 peri-infarction pericarditis（C）；e7 合成 `myopericarditis`（X）。后者词面上同时包含 myocardium 与 pericardium，却暗示原发炎症累及心肌，反转了 infarction→pericarditis 的方向。这是为什么“更完整的 composite 字符串”仍可能更错，也直接支持 relation type signature 必须包含时序与病因方向。

### 4.13 `MCR_v2_seq100/134`：真实 rescue 不等于系统单调优势

Collapse3c 停在 gastrointestinal histiocytosis（P）；IMPC 根据 pale histiocytes 内 basophilic targetoid inclusions、von Kossa/PAS 阳性的 Michaelis–Gutmann bodies 恢复 malakoplakia（C）。这是可信的 pathology specificity rescue。然而同一 full-800 配对中 IMPC 有 19 个 object rescue，却有 32 个 catastrophic substitution 和 17 个 compression。这个病例应作为可迁移的“决定性病理特征驱动收紧”机制，而不能作为 IMPC 整体优越的轶事证明。

## 5. 各基线与骨干的真实优劣势

E2 的九臂 full-800 总表是测量基座，而不是胜负榜：临床主推断使用 ALL/DA/MCR 各自相干的 10 对比 Holm 家族。overall 与 DA 没有 survivor；MCR 的 Collapse3c–IMPC `q=.045615`，但 family interaction `q=.228489`，不支持把局部结果外推为跨 benchmark 胜者。30-test endpoint-wide family 仅保留为审计敏感性。以下优劣来自端点结构、配对 transition、受控模块实验和病例链的共同证据。

### 5.1 legacy APHHM

可保留的假说是：大状态可能让低先验、强病理/IHC 候选存活更久。不能保留的是它与 clean arms 的架构胜负，因为历史 runtime 曾让 answer options 进入 input-sensitive stages。E1 证明这种泄漏能直接改变生成与 token 轨迹，但 E1 不是 full APHHM rerun，故不能把 +40pp 微管线效应量直接减回历史分数。legacy APHHM 目前只适合作内部污染运行解剖，不适合作 clean superiority baseline。

`APHHM_C_PILOT200_REPORT.md` 的旧拟合 DA `conv≈0.74−0.047×width`、MCR `0.82−0.045×width` 仍可保留为 14 个相关历史臂、legacy-chain 条件分母上的描述性 OLS；E5 的九臂 joint-common-served model-panel complete 恰好给出 −4.48pp/新增候选的局部量级复现。但结论不能靠“微调系数”维持为确定律或 selector ceiling：E5 的 DA/MCR 为 −2.87/−6.33pp，synonym 与 component 不沿同一负斜率；E4 在同宽度同池上仅换 evidence integration 就带来 evidence-count→Forest +9.50pp complete；E9 增加真实独有视图反而 +3.25pp、`q=.01328`。因此成立的是“flat、untyped、fixed-k fill 会诱发候选干扰”，不成立的是“coverage 与 conversion 数学上不可兼得”或“必须越过 selector 范式才能改进”。应修改的是状态/admission 范式：safe identity、typed requested object、evidence-qualified main frontier、residual coverage ledger 与一次冻结 comparator；主动取证只是缺失 discriminator 时的一条路径，不是逻辑上唯一出路。

### 5.2 Collapse3c、MultiStance、Lite

- **Collapse3c**：clinical-complete 122/800（15.25%）最高，优势是保留病因、解剖、stage、time 和 composite；但仍发生生成 miss 与错误替换，且与 Multistance 只有 1 例净差。它是 specificity-retention 参考，不是全局赢家。
- **MultiStance**：complete 121/800（15.12%）、safe-exact 8.62% 最高；但相对 Collapse3c 是 21 rescue 对 22 loss。不同取向既能修正病变类型，也会在相关候选竞争中丢掉已证实 subtype，净增益近零。
- **Lite**：complete 106/800（13.25%）不是 E2 最佳，却在 RCR3 以 296/300 served、较宽 exposure 和较少 schema failure 保持优势。它的价值是简单、可审计、不会让结构失败先吞掉候选；不足是常停在 family/compatible-partial。

因此当前选 Lite 是“更复杂替代品没有证明净益”的安全决定，不是声称 Lite 临床完整性最高。下一版应把 Collapse3c 的 specificity retention 融入 Lite comparator，而不是把两个完整系统并联投票。

### 5.3 Forest 与 IMPC

Forest/IMPC 的 legacy-chain 分别为 26.62%/26.50%，但 clinical-complete 只有 13.38%/12.25%。它们擅长稳定、常见、task-recognized parent；E4 又证明 Forest selector 在同池上能用高特异证据优于 e7。full-800 transition 同时给出更精确的代价：Forest 相对 Collapse3c 为 22 rescue/37 loss；IMPC 为 25/49，后者虽有 19 个 object rescue，却伴随 32 个 catastrophic substitution。旧 chain 高分主要说明 resolver 接受 parent/surface，不是完整对象更强。

可迁移的不是“Forest 整体”，而是三点：病例证据整合、少量 residual view capture、显式反证。必须删除 substring identity、view-count voting 和不可逆 fixed frontier。

### 5.4 e7 与 v0

e7 相对 v0 full-800 clinical-complete 为 113/800 对 103/800，即 v0−e7 −1.25pp（21/11，95% CI [−2.625,+0.125]，coherent Holm `q=.881`）。unique-full 中 v0−e7 为 −2.64pp，nonunique 反为 +0.58pp：e7 在证据充分病例更常保住具体对象，v0 在模糊题上有时因保守 parent 少犯过特异错误。病例上 e7 有真实 rescue，也有 peri-infarction pericarditis→myopericarditis 等 catastrophic tail。

E12 确认 e7 最值得保留的是已有多候选池和一次显式 comparator；应退役 S1 唯一表示、无证据填宽和把独立 selector 重采样叫“depth gain”。v0 是有价值的最小状态负对照，但不是每个端点最低，也不能仅凭更保守就作为性能目标。

### 5.5 B06

B06 的强项不是群体智慧，而是 rank propagation。E10 显示 history 能把低位候选推到前列，但其旧 Top-2 数只是 binary-acceptable proxy，不能证明 clinical-complete 净益；isolated Supervisor 的定向病例仍可用于定位 singleton rescue。真正可比的完整临床证据来自 E2：B06 相对 B07 为 32 complete gain/28 loss（+0.50pp），并非稳定支配。它能保留 H3N2 和排除 myeloma，却会把 May–Thurner 压成 DVT、把 RVO→CME 压成 CME。弱点是 D3 近乎零搜索、错误锚级联和 rare correct minority 永久删除。

### 5.6 B07

B07 在 E2 full-800 中 compatible-partial 35.25% 为最高、clinical-complete 12.62%，典型行为是正确 family 的软着陆，但也有 lytic lesions/hypercalcemia→myeloma 这类原型替换。E11 的非盲 proxy sensitivity 不足以证明当前 retrieval 是 compatible-partial coverage 的可靠来源，也不能把 no-retrieval draft 称为临床能力最佳单臂；它只支持把 no-RAG 保留为下一轮控制。refine 的定向队列可见 gastric lipoma、HHRH 等 specificity rescue，也可见 rare-candidate 删除。下一步检索应由 typed need 与 admission gate 驱动，refine 必须 append-only 或给出明确 counterevidence 才能删除。

### 5.7 RCR-3 与 Compact4

RCR-3 的优点是把 desired architecture 写成可证伪合同：span、typed candidate、requested object、time/scope comparator。其失败也因此能被定位，而不是只得到“分数低”。新全臂模型面板 complete 无 Holm survivor；C∪P 的 ITA 明确低于 Lite，但共同服务后 RCR−Lite 只 −0.39pp、Compact4−RCR −1.32pp、第三 generator−Lite −1.72pp，均未确认。所以上线否决同时且主要依靠 safe-exact exposure、schema/view failure、span loss 与 relation fidelity；不能再写成“成功返回时 RCR clinical relation 明显更差”。Compact4 的 125 个总失败主要来自第三 view contract，调用数扩张没有显示可用的端到端价值。

可保留：safe identity、typed composite proposal、原文 provenance 意图、一次 fixed comparator。必须重做：offset span、relation ontology、引用闭包、requested-object hard gate、non-dominated frontier、selector completeness calibration。

## 6. 看似矛盾的结果如何统一

| 表面矛盾 | 实际解释 |
|---|---|
| Forest E4 赢 e7，但 E2 没有 universal winner | E4 只识别已暴露固定池上的 selector；E2 衡量历史全链且 clinical-complete 与 safe-exact/legacy-chain 排名不同 |
| E5 ITA 每个 addition 都有害，但 common-served synonym 正、component 近零 | ITA 混合 34–36 个 differential failure；成功服务时效应由 candidate type/topology 决定，只有 genuine width ladder 与 sibling 稳健为负 |
| E5 局部约 −4.48pp/候选，E12 k5→10 近零 | E5 base pool 已暴露 reference 并冻结 membership；E12 新增历史候选 reference yield 极低且混合 pool topology；共同结论是 fixed fill 不安全，不是 universal width coefficient |
| E6 ITA complete 显著，common-served complete 不显著 | 表示处理同时改变 schema/service；共同服务后 C∪P deficit 仍确认，故关系丢失成立但 complete-only 系数需收窄 |
| RCR3 ITA C∪P 差，common-served 近零 | 端到端否决主要来自接口/schema、span 与 relation fidelity；不能把部署可靠性差偷换成成功轨迹能力差 |
| B06 history 压缩多样性，旧 E10 Top-2 proxy 却上升 | history 删除召回同时强化幸存候选的 rank；结构机制成立，但二元 acceptable 不能证明 complete conversion |
| soft veto 没有显著赢，hard veto 仍应禁用 | hard 的 9 个 gold veto 全无效是安全性结论；soft ranker 净益是另一个需要候选与权重共同满足的问题 |
| relevant RAG 的 complete-proxy 变差，broad-proxy 略正 | 非盲敏感性提示上下文可能把具体对象压成正确 family；方向是假说，不是发生率 |
| raw 优于 S1/graph，但不能全算 reasoning | raw 同时保留真实关系和作者诊断性断言；表征保真效应真实，独立推理效应尚未隔离 |
| typed relation 理论合理，E7c/RCR3 却失败 | 失败的是方向不稳、无 span closure、无 requested-object gate 的生成式实现，不是所有约束关系表示 |
| safe-exact 很低、task 很高 | safe-exact 是高精度保守下界；DA mapper 大量接受 compatible-partial，MCR judge 才较接近 complete；E2 已按 family 分开 |

这些调和不是“所有结果都可以解释”。相反，它们收窄了可写主张：任何体系若只优化一个中间率，都必须显示它没有通过另一层付出更大代价。

## 7. RCR-3 的预注册成功条件为何逐项失败

| 条件 | 观察 | 根因 |
|---|---|---|
| relation fidelity 优于 E6 | 20/60 edge 错误/无支持，另 11/60 浅共现 | 关系是自由生成命题，缺 deterministic signature 与 span closure |
| 不降低 exposure | raw −6pp、frontier −7pp；3 个 reference raw→frontier loss | skeleton 调用替代 proposal、span drop 降分、固定 priority 截断 |
| complete exposure→Top-1 提高 | model-panel complete Lite/RCR3 22/13，无 Holm survivor；C∪P ITA 130/109、`q=.03142`，共同服务仅 −0.39pp、`q=1` | requested-object 只是字段；manifestation/etiology/subtype 混排，且 schema/service 承担大部分端到端损失 |
| typed candidate gain > interference | Top-1 6 gain/15 loss | 新候选不受 unique evidence、type gate 和 counterfactual contrast 约束 |
| 三调用优于简单三调用 | ITA 与 common-success 均无正净益 | 同预算但 schema 更长、token 更高、失败更多，且牺牲一个 independent proposal |
| 第三独立 generator 有边际价值 | Compact4 common-success 近零，ITA 显著受 failure 拖累 | 第三 view 常只给一个候选或违反 view/type contract |
| selector complete 可作校准 | 9/66 self-complete 真 complete | 自洽 rationale 与外部 clinical completeness 不是同一变量 |

需要强调：schema failure 不是“纯技术噪音”而应从科学结果中删除。RCR 的 schema 正是架构要求更复杂 clinical object 的接口成本；38 个 RCR failure 对 4 个 Lite failure 是端到端可用性的一部分。共同成功 sensitivity 用于拆出机制，却不能取代 ITA 部署估计。相反，provider/retry 统一只为了降方差，按用户要求未作为科学臂执行。

RCR 的少量 rescue 仍有价值：RVO+CME 的 composite、sacrococcygeal teratoma 的 requested-object rescue、GI sarcoidosis 的跨部位 granuloma。它们证明 typed candidate/comparator 有局部潜力。APS rescue 的 skeleton 却是零 relation，不能事后归功关系层。每个 rescue 必须沿 treatment-specific path 归因，不能只因发生在 RCR arm 就给所有模块记功。

## 8. 下一版可执行架构约束

这不是再拼接“每个实验的赢家”，而是只保留通过机制检验的接口。

### 8.1 当前默认路径

1. Call 1 与 Call 2 相互独立，均可看完整 clean vignette；不共享自由文本 history。
2. 每个候选输出 `candidate_type`、requested-object level、独有 supporting span、strongest counterevidence 和 provenance。
3. registry 只合并 exact/frozen synonyms；其他 lexical relation 只作为待验证边。
4. 候选不固定填 k。具有独有 discriminator 的进入主池；其余进入 residual coverage ledger，不获得票数。
5. Call 3 读取冻结 pool 和 raw spans，做 completeness-first contrast。pairwise 是当前工程默认，但要输出 candidate-unique evidence、反事实缺失和 scope projection。
6. 低先验/rare candidate 不能仅因支持条数少被删除；删除必须绑定一条比它更强、同对象/同 episode 的 counterevidence。
7. 默认 no-RAG、no Call-4。只有新的 typed retrieval/gate 在受控实验通过后才重新启用。

### 8.2 关系层重新进入在线实验前的硬门

- offset-based span 对齐，不使用脆弱 exact substring 作为唯一 grounding；
- relation endpoint 类型签名与 inverse 规范；
- duplicate pair collapse、矛盾 direction reject、cycle detection；
- `not tested`、`negative`、`normal at time t`、`family history`、maternal/fetal/proband scope 分型；
- sensitivity 无原文依据时强制 `unknown`；
- candidate 引用 closure：证据被删，依赖 candidate 必须 quarantine，不能语义 fail-open；
- requested-object executable gate：manifestation/complication 不得在 disease/etiology 任务里无说明夺冠；
- non-dominated frontier：相同核心诊断的多个 subtype 不能机械挤掉 generic core；
- selector 的 complete/confidence 需外部校准，不读自身字段作为停止信号。

达到这些工程硬门只是让下一次实验“测到了想测的关系系统”，不是自动证明更好。新的实现仍需用 frozen Lite control、ITA、全病例全臂盲法根级 clinical-complete/compatible-partial/union，以及 relation fidelity 预注册门槛重新检验。

## 9. OpenRouter、Google 地区限制与运行环境

当前环境的可工作路径是平台管理的动态网络路由 `TREE_DX_PROXY_MODE=environment`。它已经完成实际在线验证：

- E2/E12 的 Gemini 2.5 Flash 请求经 OpenRouter 实际落到 Google provider；
- 未出现 `region unsupported` 或公用机房 IP block；
- GPT-4.1 400/400 semantic/physical calls 全部 HTTP 200，provider association 为 OpenAI 399、Azure 1；
- Llama arms 使用 DeepInfra 与 Groq 等多 provider，不是 Groq 单点；
- 非 RAG 使用并发 50，RAG 使用 25 或更小的受控恢复任务；E11 早期 process storm 被中止并保留 incident，恢复任务拆分执行。

真正的裸 `TREE_DX_PROXY_MODE=direct` 在这个容器无法解析 `openrouter.ai` DNS。因此“无需 VPN”的准确含义是：**无需仓库内 Clash/固定 VPN，继续使用环境动态代理即可**；不是说网络完全不经过平台路由。当前路径无需额外 VPN，也没有触发 Google 地区/IP 错误。

当前 Python image 缺 `openai/httpx/requests`，所以共享 `RobustLLMClient` 的 `auto` 模式选择 audited stdlib OpenRouter transport。代码继续保留环境控制的官方 OpenAI SDK 路径，依赖存在时可用 `TREE_DX_LLM_TRANSPORT=openai`；没有把实验专用简易 terminal 变成唯一生产实现。credential 未写入代码、JSON、log、tar 或报告。

## 10. 仍然不能越过的有效性边界

1. **没有确认集外推。** 800 例已被多轮分析和算法开发使用；所有优劣都是开发机制证据。
2. **没有 E13 潜在正确率。** 单次 trajectory flip 可能混入服务端/provider 方差；本文只对成组、方向一致且有中间状态证据的机制作强解释。
3. **provider 未随机固定。** 同 provider loss 证明它不是全部解释，但不能把每个 arm 差值全归于 prompt/module。
4. **root 与 model-panel 责任不同。** E2 是 800/800 identity census 与 3,103 relation 的 human-root exhaustive partition。79 臂迁移则复用 1,693 个 E2 root relation、确定性补 251 个 safe identity，并对 3,407 个新 relation 做三 reviewer 臂隐藏模型面板；其发生率完整，但 truth ownership 不是 root。源报告旧定向、proxy 与二元 acceptable 只作历史/机制校准。
5. **external reviewer 有相关偏差。** 修正后的 1,173 个隐藏 E2 sentinel（每卡至多 2 个）上，三 reviewer 的 fine-label accuracy 为 65.98%/70.08%/74.00%，complete boundary accuracy 为 96.25%/97.53%/98.21%；聚合面板为 70.93%/97.70%。因此 unanimous/majority 仍只能叫 model proxy；152 个新关系三方分裂保留 `U`，不强行变成 clinical truth，也不扩展 root-only leaderboard。
6. **DA/MCR 不能合并成一个机制系数。** DA 常见 composite/scope 和共享候选重排；MCR 更常是 distinct disease capture。相同 pp 可以来自完全不同的轨迹。
7. **多重比较必须保留。** E2 的 clinical primary family 是每个 scope 相干的 10 对比 Holm；30-test endpoint-wide family 只作审计。MCR 有一个 family-local survivor，但 DA–MCR interaction 未确认，所以不存在 universal winner。迁移按 experiment × 预注册 contrast family × scope × endpoint 分别 Holm；E12 的旧 complete survivor 已消失，新增 survivor 属 C∪P secondary，不能借用到 complete。task 的 26 个 survivor 是 ITA、family-specific 的 DA/MCR cells；common-served sensitivity 为 15 个（DA 4/MCR 11），采用另一 estimand，二者不可互称或相加。不能把未校正病例故事升级成 universal ranking。
8. **raw 表示含潜在作者结论。** raw 胜 S1/graph 是保真结论，不足以证明纯症状推理能力。

## 11. 当前可以写与不能写

### 可以写

- options visibility 会进入候选生成，旧污染臂不能与 clean arms 作纯架构归因；
- exact identity 是必要安全约束，substring merge 会转移证据；
- sibling/宽池会产生直接 capture 和共享候选 reordering，IIA 被证伪；
- 当前生成 graph/directional relation/RCR skeleton 的 fidelity 不足，且损害可定位到 span、edge、frontier 和 requested object；
- Forest 在固定暴露池上的 evidence integration 优于 e7 selector，但总体瓶颈仍在 exposure；
- B06 sequential 是 consensus compression，能改善 rank conversion，也会擦除 rare minority；
- 当前 B07 query-top retrieval 不是 clinically relevant RAG，generic refine 不是可靠兜底；
- hard atemporal veto 不安全，soft policy 的净准确率优越性未确认；
- 只有满足全病例、全臂、盲法根级合同的 clinical-complete 才可作真实能力主端点；79 个迁移臂的完整 model-panel census 只更新敏感性/机制；safe-exact/legacy-chain/compatible-partial/union/DA-task/MCR-task/identifiability 必须分报；目前仍仅 E2 进入 root leaderboard；
- 当前 RCR-3 与 current Call-4 gate 均不应成为默认。

### 不能写

- 某一个完整系统已确认普遍优于所有基线；
- Forest 的完整优势已因果定位到 generator 或 selector 单一模块；
- pairwise accuracy 已确认优于 pointwise；
- 关系图本身无用，或任何未来 typed RAG/Call-4 都无用；
- soft veto 已显著提高整体准确率；
- E10 的顺序 history 在所有分布都净有益；
- E9 的旧 6/1/4 或 E10 的 binary-acceptable Top-1/Top-2 是 clinical-complete、compatible-partial 或两者并集；
- 79 臂的模型面板标签是 human-root truth，或旧 root-priority/proxy 数值可替代迁移结果；
- E2 中 raw CI、transition 个案或 legacy-chain 排序就是确认性胜负；
- 当前 800 题上的机制可以直接外推临床部署。

## 12. 可复核产物

- `cross_experiment_synthesis.py`：校验 16 份 owning report 的原文锚点，生成闭环账本；
- `results/CROSS_EXPERIMENT_ROOT_SYNTHESIS/evidence_matrix.json[l]`：实验设计、数值、因果边界、source SHA；
- `results/ENDPOINT_COVERAGE_AUDIT/endpoint_coverage_matrix.json` 及综合目录副本：16 个实验、91 个实验臂的端点状态、盲法/根审/proxy 合同和 leaderboard 准入门；
- `e2_full800_snapshot.json`：规范端点合同、27 行 ALL/DA/MCR leaderboard、30 个 complete 配对、10 个 family interaction、30 个 identifiability interaction、relation transition、task calibration 与关键推断回归哨兵；
- `mechanism_chain.json`：八阶段失败链与安全合同；
- `baseline_profiles.json`：十二个基线/骨干的优势、弱点、用途与限制；
- `trajectory_motifs.json`：十三条跨实验同案机制链，含 full-800 specificity/object rescue、scope compression 与 catastrophic substitution；
- `closure_matrix.json`：完成、明确排除和 prerequisite-blocked 项；
- `claim_ledger_final.jsonl`：16 条最终主张及可证伪条件；
- `artifact_manifest.json`、deterministic tar.gz 与 SHA-256；
- 每个 E1–E12、E14x、RCR3 目录中的主报告、原始结果、telemetry、manual/root audit 与 archive。

## 最终收束

最值得保留的不是某个完整 pipeline 的名字，而是几个已经经受住反证的局部原则：clean input、原文可回溯、safe identity、typed requested object、少量真正残差候选、一次显式比较、时间/范围软约束、rare-candidate coverage guard，以及任务投影与临床对象分离。

最应当删除的是：options 泄漏、S1/graph 唯一真相、substring identity、自由生成关系继承、固定宽度填满、view/history 重复计票、绝对 veto、无门控 RAG、generic refine 删除、self-reported completeness 和当前 unexplained-span Call-4。

跨实验最深的结论不是“少调用一定更好”，而是：**每一次状态写入都必须证明它增加了可核验、与请求对象同层、能够存活到固定 comparator 的判别信息；否则复杂 deliberation 只会把知识不足转化成更难审计的信息失真。**
