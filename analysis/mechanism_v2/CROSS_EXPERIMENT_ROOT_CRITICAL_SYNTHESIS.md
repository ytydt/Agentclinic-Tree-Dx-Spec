# Mechanism-v2 跨实验根级病例轨迹解剖与批判性综合

> 分支：`cursor4`
> 综合范围：E0–E12、E14x、RCR-3，以及 E6x/E7c/E2 exhaustive correction 这些由实验中新暴露的缺口
> 推断单位：病例；DA 与 MCR 分层；现有 800 例一律视为开发/机制数据
> 审计责任：外部 LLM 只承担盲化初筛、反例扩展或结构化分包；本文的病例解释、主张升降级和系统裁决由根审计承担
> 结构化证据：`results/CROSS_EXPERIMENT_ROOT_SYNTHESIS/`

## 0. 最终裁决

这一轮没有识别出一个在所有临床对象、所有终点上普遍占优的系统。识别出来的是一条比“模型不够聪明”更具体、也更可干预的共同机制：

> **多调用系统的主要损失来自信息在输入、表示、候选、身份、暴露、比较、诊断对象完整性和任务投影之间连续转化时发生的删除、伪造、重复加权与不可逆选择。**

调用数本身既不是能力，也不是成本效益的充分代理。一次额外调用可以像 E10 一样，在几乎没有新增候选时通过 rank propagation 改善当前样本；也可以像 E14x 一样生成 135 个全部存活的新实体，却没有一个 strict reference discovery，并产生 6 个观察 repair、15 个 harm、13 个 neutral。真正需要计算的是：新增的、可验证的关系信息或可归因排名修正，是否大于新增干扰、关系损失、不可逆删除与接口失真。

当前开发机制证据支持以下系统决策：

1. **默认仍用 Lite-like 三调用**：两次相互独立、读取完整原文的 proposal，加一次冻结候选池 comparator。它不是已确认的普遍最佳，而是在当前 RCR-3 未通过预注册门槛后最安全的对照路径。
2. **当前 RCR-3 不上线**。它相对 Lite 的完整 Top-1/Top-2 为 20/31 对 29/42；strict frontier exposure 低 7.00pp，Holm `q=.000311`。至少 69/119 个 span drop 是物质性证据，20/60 条分层 relation 错误或无支持，selector 自报 complete 的冠军只有 9/66 被根审计确认完整。
3. **当前第四调用 gate 关闭**。`unexplained_spans + low margin` 检测到的是“当前生成文本未解释什么”，不是“缺失哪个诊断对象或决定性关系”。E14x 足以否定现有 gate 的部署证据，不足以否定未来受约束的 Call-4。
4. **exact/frozen-synonym identity 是硬安全约束**，但不是准确率插件。E7b 消除了 160 个被选概念的身份污染并恢复 reference exposure，却没有形成显著 Top-1 增益；安全身份之后仍要解决宽度压力、关系方向与 requested-object projection。
5. **raw 原文必须始终可回看**。S1 摘要和当前生成图都不能作为唯一事实源；结构字段是新增临床命题，不是免费格式。原文中的作者诊断性断言又必须单独标记，不能把其保留效应冒充独立医学推理。
6. **候选池应小而可分，但不能固定填满某个 k**。E5 证明 sibling/宽池会直接捕获和重排共享候选；E12 又证明 k=5→10 每增加 750 个 exposure 才带来一个 strict reference exposure。有效宽度由新增候选的独有证据和对象类型决定，不由槽位数决定。
7. **时间/范围只允许软约束，RAG 只允许 typed admission**。E8 的 9 个 hard reference veto 经根审计无一成立；E11 的“relevant” chunk 只有 6.62% case-specific。没有通过关系、对象和范围门控的上下文，安全行为是不用，而不是强制注入。
8. **评估必须并列 strict、task、clinical-complete、partial 和 reference-identifiability**。E2 中只有 55.82% 的完整 reference 能由文本唯一识别；不同终点对系统排序不同，且 1,070 个原 reviewer-consensus 边界中有 73 个被根审计改变。

在用户明确排除重复多运行、确认集扩容和 provider/retry 统一之后，冻结 crosswalk 中可执行且有科学识别价值的实验已经全部完成。形式化 E14 router 依赖被排除的 E13 latent multi-run labels，不能被诚实地标记为“待跑一个普通臂”；当前真实 gate 已由 E14x 直接检验并关闭。当前授权范围内剩余 eligible experiment 数为 **0**。

## 1. 证据等级与推断纪律

综合账本不把所有实验的 p 值放在一张表里竞赛，而按它们能识别的对象分层：

| 等级 | 含义 | 代表实验 | 可写边界 |
|---|---|---|---|
| A | 调用前冻结的病例级配对/因子干预，含 ITA | E1、E4–E12、RCR3 | 可归因到冻结处理合同；不能越过具体实现外推 |
| B | 冻结 replay、加权 adjudication 或结构化重建 | E2、E7a | 可校正测量与状态会计；不等于新运行因果效应 |
| C | 上游不可比的回顾性/探索性证据 | E14x | 可做部署否决和假说定位；不能估算理想处理系数 |
| D | 根代理逐案/逐关系责任审计 | 全部关键实验 | 支持机制方向与错误链；富集队列计数不能当总体发生率 |

三条纪律贯穿本文。

第一，**处理效果与处理保真度分开**。E7c 的 directional arm 没有赢，不足以否定正确 typed ontology；但 64.82% 的内部方向一致率和 80.58% 的重复 pair consistency 已足以否定“这个实现可部署”。E11 同理：query-top RAG 失败的是一个只有 6.62% case-specific chunk 的实际处理，不是理想检索。

第二，**严格主终点与临床解释并列而不互相替换**。strict 提供冻结、可重放的下界；root complete 检查对象是否完整；partial 只表示覆盖边界，不能偷换成正确；identifiability 再问病例是否唯一要求该完整 reference。任何一个端点单独做 headline 都会偏向某种输出风格。

第三，**病例审计只为其冻结覆盖负责**。E2 的 1,673 个关系已达到 537 primary root + 1,070 supplemental root + 66 exact 的完整 partition；RCR-3 的根审计则穷尽 endpoint-critical selected relations，并非遍历全部未选候选。两者不能用同一句“人工审计过”模糊覆盖差异。

执行 crosswalk 以 `EXPERIMENT_REGISTER.md` 为冻结口径。当前 sparse 工作区可直接读取 R1–R6 综合正文；独立 APHHM-C/MOSAIC 审计原文没有随此 sparse checkout 出现，因此本文对其提案映射只使用基线时已冻结进 register 的 crosswalk，不伪称本轮重新读取了缺失原文。width、ranker 与 clean-Compact 项分别保留为 E5、E4、RCR3 的独立可识别处理。

## 2. 实验闭环：做了什么，排除了什么

| 任务簇 | 状态 | 最终识别结果 |
|---|---|---|
| E0/E3 runtime、payload、cost、claim ledger | implemented | 每个 stage、物理 attempt、provider、缓存与 endpoint 进入可追责账本 |
| E1 输入污染 | complete | options 进入生成；固定格式下 H/F Top-1 分别 +41.0/+40.2pp，但这是标签供给与搜索塌缩，不是独立推理增益 |
| E2 完整性与可辨识性 | complete + exhaustive correction | full-identifiable 55.82%；九臂无 predefined Holm survivor；LLM consensus 产生差异化测量偏置 |
| E4 selector crossover | complete | Forest fixed-pool 比 e7 +2.0pp（9/1），但暴露只有 62/400，DA 只有 7 例 |
| E5 IIA/width | complete | sibling −10.91pp、width8 −16.46pp；直接 capture 与共享候选重排并存 |
| E6/E6x representation | complete | graph vs raw complete −7.63pp；padding 使 token +64.9% 量级但不是质量损失单因 |
| E7a/b/c identity/relation | complete | exact identity 恢复 addressability；generic/directional relation 实现均未形成净益且方向可靠性不足 |
| E8 temporal veto | complete | 9/9 hard gold veto 无效；soft 排名净益未确认；合法顺序和错时都翻约四分之一冠军 |
| E9 Forest views | complete | real vs single strict +2.25pp；10 个 strict gain 仅 6 个临床 gain、3 个 true new capture |
| E10 B06 | complete | union 6.82→5.21、Jaccard .689→.954；rank conversion 正收益与 rare-candidate erasure 同时存在 |
| E11 B07 | complete | query-top complete −2.0pp、q=.270；generic refine 主端点无益，partial sensitivity 有条件信号 |
| E12 e7 | complete | raw pairwise vs first 在 k5/k10 complete +4.67/+5.00pp 且通过 39-test Holm；未证明 pairwise 胜 pointwise |
| E14x current gate | complete exploratory | 90 次调用、135 新实体、0 strict discovery；root 6 repair/15 harm/13 neutral；gate disabled |
| RCR-3 / Compact4 | complete | RCR 未过任何核心成功门；Compact4 ITA 主要被 schema/view failure 拖累，common-success 无净边际 |
| E13 多运行、provider-normalized programme | excluded | 属用户明确排除的重复/降方差程序 |
| formal E14 router after E13 | prerequisite excluded | 不使用不存在的 latent labels 伪造 router；实际 gate 已由 E14x 处理 |
| new confirmation cohort | excluded | 用户明确排除扩容确认集 |

两份源审计都未预先写出的实质缺口也没有被漏掉：E6x 处理 tokenizer sentinel 混杂；E7c 检验方向图和 bounded inheritance；E14x 检验真实 runtime gate；E2 在 reviewer consensus 被 IgA nephropathy→tuberculosis 反例击穿后扩展为 exhaustive root sweep；RCR-3 又增加 relation、span-drop、frontier 和 selector self-calibration 的独立根审计。

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

E2 又证明 benchmark reference 本身不是统一难度对象：230/400 unique-full，96 family-only，74 unsupported-specificity。all-method strict-failure stratum 的 full-identifiable weighted mass 仅 25.80%。因此，“所有方法都错”可能是共同能力缺口，也可能是病例文本并未唯一包含 benchmark 要求的最后亚型/病因/复合组件。两者必须分开，否则架构会被迫学习 benchmark 叙事末端，而不是病例可支持的诊断。

### 3.2 表示不是容器，而是临床断言层

E6 的图节点可逐字引用原文，边仍然可以错。风险因素被写成病例内因果，早期阴性 CT 与后续阳性 MRI 被写成矛盾，确认检查被写成病程进展，失败治疗先被写成 `responds_to` 再靠另一条 `contradicts` 修补。30 个根审计 graph 中 25 个至少有一个关系语义错误；graph 相对 raw 的 complete-equivalent 净差 −7.63pp（24 raw-only/5 graph-only，`p=.00055`）。

E6x 排除了一个容易但错误的解释：flat 的 `[LENGTH_CONTROL_PAD]` 约等于 8 tokenizer token，去掉后 prompt token 平均下降 64.9%，complete 仅 +1.57pp、`p=.481`。因此 padding 是严重成本混杂，却不能解释关系损失。更值得警惕的是 95.29% champion flip：温度 0 并没有把模型变成同一确定函数，非临床 sentinel、provider 路径或早期 token 分叉都能重写完整候选轨迹。

E12 对历史 e7 提供同方向但更具体的证据。S1 不是因为“短”而差，而是删除组织学、精确解剖、病原、时序与诊断桥，还能把 QTc 380 ms 同时写成正常值和 prolonged QT。raw comparator 的优势中又混有病例作者的 `was suspected` 类诊断性句子。正确的系统约束不是“永远 raw”，而是：原文 span 可回看；derived fact 标记它是原文陈述、作者诊断断言还是模型推断；任何关系若无 span 或确定性规则支持，只能进入 hypothesis/quarantine，不得成为 veto 或 frontier priority。

RCR-3 没有遵守这一强度。119 个 exact-span drop 至少 69 个物质性；sanitizer 删除 invalid evidence ID，却让依赖它的 candidate 继续存活，形成“引用 fail-closed、候选语义 fail-open”。这比普通 schema failure 更危险：系统看似可解释，实际解释链已断。

### 3.3 多视图、多医生与候选宽度：多样性既是资源也是干扰

E9 把 Forest 的三视图拆成四种状态。real views 比 balanced single anchor strict +2.25pp（10/1，`p=.0117`），但根审计把 10 个 real-only strict gain 重编码为 6 个临床 gain，其中只有 3 个是新增 reference capture；其余来自共同候选的排序或 scope/surface。语义 cluster/observation 比 0.552，证明视图约一半重叠。exact duplicate 仍翻转 51/399 champion，role rotation 翻转 58/400；重复不是信息，却会改变模型内部权重。

E10 则给出一个重要反例，迫使旧主张升级：sequential history 将 union 6.82 压到 5.21、pairwise Jaccard .689 拉到 .954，D3 在 400 例只新增 6 个 concept；它仍使 RRF/Supervisor clinical Top-2 分别 +4.50/+3.25pp。23 个 RRF 顺序正向病例全部是 rank conversion，不是新 capture。额外调用的价值因此不能只用“新增候选数”衡量；正确低位候选被历史重复抬高，也是一种可验证的信息转化。但同一过程会删除 schwannoma、uterine inversion、TEN 和 chronic subdural hematoma。它是一种以长尾召回换主流转换的 consensus compressor，不是三位独立专家。

E5 与 E12 共同否定固定宽度神话。E5 在每个 base pool 都暴露 gold 的条件下加入 sibling，使 Top-1 −10.91pp；width8 −16.46pp。MCR 主要由新增 plausible disease 直接夺冠，DA 主要由新成员改变共享近邻候选排序。E12 的历史池中 k5→k10 增加 1,500 个 exposure，只增加 2 个 strict reference exposure；raw pointwise 反而 −1.67pp，pairwise +0.33pp。两者并不矛盾：E5 估计候选成员本身的干扰，E12 估计一批低 marginal-yield historical proposals 的端到端变化。结论不是 `k=5`，而是候选只有在带来独有、可引用 discriminator 时才进入主比较；其余保留在 coverage ledger。

### 3.4 身份安全与关系安全是两个问题

E7a 在 800 例中找到 299 例 unsafe substring fold、1,199 个 unsafe pair，exact identity 平均恢复 0.550 个可独立寻址节点。E7b 的 fresh selector 将 contaminated champion 160→0，并在 unsafe stratum 带来 11 exposure restoration/1 loss（`p=.00635`）；Top-1 仅 8 gain/5 loss，`p=.581`。这说明 identity 是安全约束，不是充分治疗。

原因在 E7c 被直接看见：exact pool 固定后，加入 LLM directional graph 仍为 −0.67pp；bounded inheritance 净 0。776 个可由 lexical containment 检查方向的边只有 64.82% 一致；重复 label-pair consistency 80.58%。generic 非语义 graph 也能翻转 47 个 champion，其中 15 个 flip 两个 champion 都不是 graph node。这里存在三种不同风险：错误临床方向、正确但任务无关的 salience、纯上下文 placebo instability。不能把它们合并为“关系推理无效”。

安全合同应当是：identity 只合并 exact/frozen synonyms；parent/subtype、etiology/manifestation、disease/complication、component/composite 分开；方向、inverse、duplicate、cycle、type signature 由确定性规则检查；证据只沿经验证的 edge 继承；没有 requested-object projection 的 relation 不进入冠军排序。

### 3.5 阴性、时间与检索：更多结构可能等于更多伪证据

E8 的 hard selector 对暴露 reference 作 9 次绝对 veto。根审计：8 次临床 overreach，1 次由 builder 将阳性 CT 反写成“无异常”，0 次成立。soft 删除这些 veto，但全共同成功病例只 18→21，`p=.453`。soft 解决的是错误排除，并不能生成缺失候选、恢复复合对象或纠正 subtype identity。合法 ledger 行顺序产生 24.6% champion flip，非法 time/episode 置换产生 23.2%，两者净准确都约 0。这说明模型确实“响应”字段，却没有被识别出方向正确的时间推理。

E11 把同一风险扩展到外部上下文。所谓 relevant bundle 的 1,950 chunks 中只有 129 个 case-specific；71.64% 无病例适配。hard-negative 又混入同病/亚型支持，不能当干净安慰剂。relevant 相对 off clinical-complete Top-1 −2.0pp（10 loss/2 gain，Holm `q=.270`），complete+partial 则 +0.5pp：它更常把完整病因、部位或亚型压成正确疾病族，而不是把病例推向完全无关疾病。generic refine 行为很强，却只在 secondary broad endpoint 的 off 条件下 +3.5pp 通过七重校正；它也会跨四个上下文一致删除 mucormycosis 等 rare-but-plausible candidate。

因此 RAG 的入口不应是“病例全文相似”。需要 typed information need：要查的是 etiologic relation、subtype defining criterion、test sensitivity，还是 competitor counterevidence；chunk admission 必须区分 same entity/subtype、broader context、competitor 和 generic。未通过门控就返回 no-RAG comparator。

### 3.6 selector 能修什么，不能修什么

E4 是最干净的 selector 证据。400 个相同 pool 上，Forest 41、tournament 38、ledger 37、e7 33、evidence-count 17；Forest 对 e7 的 9/1 gain 完全来自 MCR。17 个 strict discordance 中，Forest 的 9 gain 只有 5 个强临床 gain、1 个未充分确认、3 个 surface/scope artifact。Forest 的优势是病例特异证据整合，不是“来自 Forest 的候选”或投票；它无法改善 338 个 strict-unexposed 病例。

E12 又证明“不比较”确实是弱基线。raw k5/k10 pairwise 相对 frozen first 的 clinical-complete Top-1 分别 +4.67/+5.00pp，且是 39-test Holm family 中仅有的两项 survivor。这证明候选顺序不能直接充当诊断排序。它没有证明 pairwise accuracy 胜 pointwise：raw k5 两者都是 65/300，k10 60 vs 66 的差异未校正显著。pairwise 目前成为工程默认的理由是输出 token 约为 pointwise 的四分之一、schema 更稳定且结果不劣，而不是已确认的准确率优势。

同样，E10 的 Supervisor 只在真实 minority opinion 存在的 isolated 条件下有较明显语义价值；history 已经压平 union 后，它无法复活池外候选。RCR-3 selector 的 `complete/strong/fits` 自报字段更不能作 gate：66 个 self-complete 冠军 38 个根审计为错误实体。模型对自己 rationale 的一致性不是外部校准。

### 3.7 task projection 不是 reasoning 的尾声，而是另一处理层

E2 的九臂 weighted 结果显示 strict、task、complete、accepted 四个排序不同：IMPC strict 25.98% 最高，Collapse3c complete 16.16% 和 accepted 50.63% 最高，B07 complete 12.19% 却 accepted 49.93%。mapper 既拒绝真实 alias，也接受错误 manifestation、histology 或 etiology。task-positive but clinically non-accepted 占 weighted 5.37–7.33%；task-negative but accepted 为 10.10–13.16%。

E14x 提供更直接的 mapper placebo：18 个 DA option flip 中 8 个 champion 文本完全相同；错误的 Adult-onset Still disease 和 ARVC 还能映到 gold option。option@1 不能为 gate 或候选生成提供正反馈。任何系统报告都必须保存 pre-mapper diagnosis、object relation、clinical completeness 和 task projection 的完整 transition。

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

## 5. 各基线与骨干的真实优劣势

E2 的九臂 weighted 总表是测量基座，而不是胜负榜：没有一个 predefined contrast 在每 endpoint 的 30 个 contrast/scope Holm family 中 `q<.05`。以下优劣来自端点结构、受控模块实验和病例链的共同证据。

### 5.1 legacy APHHM

可保留的假说是：大状态可能让低先验、强病理/IHC 候选存活更久。不能保留的是它与 clean arms 的架构胜负，因为历史 runtime 曾让 answer options 进入 input-sensitive stages。E1 证明这种泄漏能直接改变生成与 token 轨迹，但 E1 不是 full APHHM rerun，故不能把 +40pp 微管线效应量直接减回历史分数。legacy APHHM 目前只适合作内部污染运行解剖，不适合作 clean superiority baseline。

### 5.2 Collapse3c、MultiStance、Lite

- **Collapse3c**：weighted complete 16.16%、accepted 50.63%，在 E2 两项最高；优势是保留病因、解剖、stage、time 和 composite。弱点是 strict 20.59%，常被 canonical surface 低估，也不如 Forest/IMPC 稳定输出常见 parent。
- **MultiStance**：complete 14.83%，说明宽提案能覆盖更多对象；但 E5/E9 的证据表明多样性若相关或无独有证据，会转成竞争负担。
- **Lite**：complete 12.29% 不是 E2 最佳，却在 RCR3 以 296/300 served、较宽 exposure 和较少 schema failure 保持优势。它的价值是简单、可审计、不会让结构失败先吞掉候选；不足是常停在 family/partial。

因此当前选 Lite 是“更复杂替代品没有证明净益”的安全决定，不是声称 Lite 临床完整性最高。下一版应把 Collapse3c 的 specificity retention 融入 Lite comparator，而不是把两个完整系统并联投票。

### 5.3 Forest 与 IMPC

Forest/IMPC weighted strict 分别 25.67/25.98%，但 complete 只有 12.48/12.45%。它们擅长稳定、常见、task-recognized parent；E4 又证明 Forest selector 在同池上能用高特异证据优于 e7。弱点是容易把病因、部位或 subtype 压平，且 Forest 旧 substring registry 会吞兄弟/组件；多视图重复还可能让证据量压过证据特异度。

可迁移的不是“Forest 整体”，而是三点：病例证据整合、少量 residual view capture、显式反证。必须删除 substring identity、view-count voting 和不可逆 fixed frontier。

### 5.4 e7 与 v0

E7 相对 v0 weighted complete +3.20pp，bootstrap CI +1.29 至 +5.26，但 Holm `q=.209`。病例上它确有 Surfer's myelopathy、scar endometriosis、familial CCM、myopericarditis 等具体恢复，也有把 starvation colitis 推成 infectious colitis 等 catastrophic tail。

E12 确认 e7 最值得保留的是已有多候选池和一次显式 comparator；应退役 S1 唯一表示、无证据填宽和把独立 selector 重采样叫“depth gain”。v0 则是有价值的最小状态负对照，但 E2 四项率均最低，不能作为性能目标。

### 5.5 B06

B06 的强项不是群体智慧，而是 rank propagation。history 能把三份低位正确候选推到前列，当前样本 clinical Top-2 有明确净益；isolated Supervisor 又能偶尔从 singleton 里做病例语义 rescue。弱点是 D3 近乎零搜索、错误锚会级联、rare correct minority 永久删除。生产上可以借用“对低位候选做一次集中比较”，不能借用顺序自由讨论或把三次复述当三票。

### 5.6 B07

B07 weighted accepted 49.93%、complete 12.19%，典型行为是正确 family 的软着陆。E11 证明当前 retrieval 并非这一优势的可靠来源；no-retrieval draft 反而是 clinical-complete 最佳单臂。refine 可修复 gastric lipoma、HHRH 等 specificity，也会稳定删除 rare candidates。下一步若再做 B07，只保留 no-RAG draft 为控制，检索由 typed need 与 admission gate 驱动，refine 必须 append-only 或给出明确 counterevidence 才能删除。

### 5.7 RCR-3 与 Compact4

RCR-3 的优点是把 desired architecture 写成可证伪合同：span、typed candidate、requested object、time/scope comparator。其失败也因此能被定位，而不是只得到“分数低”。Compact4 则直接检验“再加一个真正 generator”，其 125 个总失败主要来自第三 view contract；共同成功 174 例相对 Lite Top-1 +0.57pp、Top-2 0。调用数扩张没有显示可用边际。

可保留：safe identity、typed composite proposal、原文 provenance 意图、一次 fixed comparator。必须重做：offset span、relation ontology、引用闭包、requested-object hard gate、non-dominated frontier、selector completeness calibration。

## 6. 看似矛盾的结果如何统一

| 表面矛盾 | 实际解释 |
|---|---|
| Forest E4 赢 e7，但 E2 没有 universal winner | E4 只识别已暴露固定池上的 selector；E2 衡量历史全链且 complete 与 strict 排名不同 |
| E5 宽度显著有害，E12 k5→10 近零 | E5 gold 已暴露且干预 candidate membership；E12 新增历史候选 reference yield 极低，并混合 pool topology；共同结论都是 fixed fill 不安全 |
| B06 history 压缩多样性，却提高 Top-2 | history 删除召回同时强化幸存正确候选的 rank；capture 与 conversion 是两个方向相反的状态 |
| soft veto 没有显著赢，hard veto 仍应禁用 | hard 的 9 个 gold veto 全无效是安全性结论；soft ranker 净益是另一个需要候选与权重共同满足的问题 |
| relevant RAG complete 变差，partial 略正 | 上下文把具体对象压成正确 family；对“相关”与对“完整”的影响方向可相反 |
| raw 优于 S1/graph，但不能全算 reasoning | raw 同时保留真实关系和作者诊断性断言；表征保真效应真实，独立推理效应尚未隔离 |
| typed relation 理论合理，E7c/RCR3 却失败 | 失败的是方向不稳、无 span closure、无 requested-object gate 的生成式实现，不是所有约束关系表示 |
| strict 很低、task/accepted 很高 | strict 漏 alias/parent，task 又有 rescue 与 false acceptance；E2 已把这些对象分开 |

这些调和不是“所有结果都可以解释”。相反，它们收窄了可写主张：任何体系若只优化一个中间率，都必须显示它没有通过另一层付出更大代价。

## 7. RCR-3 的预注册成功条件为何逐项失败

| 条件 | 观察 | 根因 |
|---|---|---|
| relation fidelity 优于 E6 | 20/60 edge 错误/无支持，另 11/60 浅共现 | 关系是自由生成命题，缺 deterministic signature 与 span closure |
| 不降低 exposure | raw −6pp、frontier −7pp；3 个 reference raw→frontier loss | skeleton 调用替代 proposal、span drop 降分、固定 priority 截断 |
| complete exposure→Top-1 提高 | Lite/RCR complete Top-1 29/20、Top-2 42/31 | requested-object 只是字段；manifestation/etiology/subtype 混排 |
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

达到这些工程硬门只是让下一次实验“测到了想测的关系系统”，不是自动证明更好。新的实现仍需用 frozen Lite control、ITA、clinical-complete 和 relation fidelity 预注册门槛重新检验。

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
4. **root audit 覆盖不同。** E2 是 exhaustive relation partition；其他实验是 endpoint-critical + frozen controls/negative samples。富集队列计数不估 prevalence。
5. **external reviewer 有相关偏差。** Gemini/DeepSeek 对 accepted precision 只有 74.82/79.66%，GPT 也会 over-call partial。异质模型扩大反例召回，不使多数票成为 gold。
6. **DA/MCR 不能合并成一个机制系数。** DA 常见 composite/scope 和共享候选重排；MCR 更常是 distinct disease capture。相同 pp 可以来自完全不同的轨迹。
7. **多重比较必须保留。** E2 有多个 raw/bootstrap signal，但无 predefined q<.05；E12 只有两个 primary survivor；不能把未校正病例故事升级成 universal ranking。
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
- strict/task/complete/partial/identifiability 必须分报；
- 当前 RCR-3 与 current Call-4 gate 均不应成为默认。

### 不能写

- 某一个完整系统已确认普遍优于所有基线；
- Forest 的完整优势已因果定位到 generator 或 selector 单一模块；
- pairwise accuracy 已确认优于 pointwise；
- 关系图本身无用，或任何未来 typed RAG/Call-4 都无用；
- soft veto 已显著提高整体准确率；
- E10 的顺序 history 在所有分布都净有益；
- E2 中 raw CI 排序就是确认性胜负；
- 当前 800 题上的机制可以直接外推临床部署。

## 12. 可复核产物

- `cross_experiment_synthesis.py`：校验 16 份 owning report 的原文锚点，生成闭环账本；
- `results/CROSS_EXPERIMENT_ROOT_SYNTHESIS/evidence_matrix.json[l]`：实验设计、数值、因果边界、source SHA；
- `mechanism_chain.json`：八阶段失败链与安全合同；
- `baseline_profiles.json`：十二个基线/骨干的优势、弱点、用途与限制；
- `trajectory_motifs.json`：八条跨实验同案机制链；
- `closure_matrix.json`：完成、明确排除和 prerequisite-blocked 项；
- `claim_ledger_final.jsonl`：16 条最终主张及可证伪条件；
- `artifact_manifest.json`、deterministic tar.gz 与 SHA-256；
- 每个 E1–E12、E14x、RCR3 目录中的主报告、原始结果、telemetry、manual/root audit 与 archive。

## 最终收束

最值得保留的不是某个完整 pipeline 的名字，而是几个已经经受住反证的局部原则：clean input、原文可回溯、safe identity、typed requested object、少量真正残差候选、一次显式比较、时间/范围软约束、rare-candidate coverage guard，以及任务投影与临床对象分离。

最应当删除的是：options 泄漏、S1/graph 唯一真相、substring identity、自由生成关系继承、固定宽度填满、view/history 重复计票、绝对 veto、无门控 RAG、generic refine 删除、self-reported completeness 和当前 unexplained-span Call-4。

跨实验最深的结论不是“少调用一定更好”，而是：**每一次状态写入都必须证明它增加了可核验、与请求对象同层、能够存活到固定 comparator 的判别信息；否则复杂 deliberation 只会把知识不足转化成更难审计的信息失真。**
