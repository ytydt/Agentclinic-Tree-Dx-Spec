# 突破召回—转化前沿：未尝试方向与分阶段实验路线图

> 证据冻结点：`c8175f6356f62e6c94a903f04dc55a39baa071d2`（2026-08-13）
> 配套根因报告：[`RECALL_CONVERSION_CEILING_ROOT_CAUSE_ANALYSIS.md`](RECALL_CONVERSION_CEILING_ROOT_CAUSE_ANALYSIS.md)
> 目标：提出真正尚未被现有轨迹实验覆盖、能够检验并突破当前 flat/fixed-`k` 前沿的方向；不是再列一轮 prompt arms。

---

## 0. 路线总裁决

### 0.1 优先顺序

下一轮不应先“跑一个更聪明的 selector”，而应按以下依赖关系推进：

1. **Phase 0 — 先补测量：** 对冻结候选池做 full-pool、human-root clinical relation census，并完成 evidence sufficiency/source-cue 审计。
2. **Phase 1 — 再改静态状态：** 先检验 evidence-qualified main frontier + append-only residual coverage ledger；成立后再检验 core/modifier 因子化和 rare protection。
3. **Phase 1 — 做联合因果实验：** 分开操纵 candidate membership、span→candidate binding、evidence duplication/presentation 与 comparator，拆出 capture、context reorder 和 evidence rescue。
4. **Phase 2 — 修复输入保真：** 用关键 span 删除/恢复的精确干预验证 representation bottleneck。
5. **Phase 2 — 建立缺失判别项 gate：** 只有当 top competitors 在现有证据下不可分，才触发单独的主动取证轨。
6. **Phase 2 — 关系/时间结构先过确定性 fidelity 门：** 不再让自由生成 graph 直接进入在线排序。
7. **Phase 3 — 架构冻结后才做新队列确认。** 当前 800 例继续只承担开发机制研究。

Phase 0 的 root labels 只负责定义测量对象；Phase 1/2 的阈值、规则和 prompts 必须在看不到 arm outcome 的开发/预试材料上冻结，不能利用未盲 census 的结果反向调到有利于某一架构。

### 0.2 两条轨道必须分开

#### 静态诊断主轨

输入仍是同一份冻结 vignette。目标是提高：

- clinical-complete exposure；
- 已暴露 complete object 的 retention/conversion；
- specificity rescue；
- service/schema 稳定性。

这一轨不能声称获得了新患者证据。

#### 主动取证轨

系统先声明：

- 当前 top hypotheses；
- 缺失的判别信息类型；
- 为什么该信息能改变两者的相对支持；
- 允许执行的问题、检查或检索；
- 若没有可行动证据则 abstain。

然后才从独立来源获得新证据。它的第一主端点应是 information-need resolution 与 source grounding，不应与静态 accuracy 直接混排。

主动轨再分两种，绝不互相改名：A1 获取新的**患者信息**（问题、检查、随访结果）；A2 只检索新的**医学知识**来解释既有患者证据。A2 不得生成或暗示任何未观察到的患者事实。

### 0.3 目标架构的最小形态

```text
                           ┌─ independent proposal A ─┐
raw vignette + raw spans ──┤                           ├─ typed exact-identity registry
                           └─ independent proposal B ─┘              │
                                                                     ├─ main frontier
                       deterministic key facts / guards ─────────────┤  (独有判别证据、同对象层级)
                                                                     │
                                                                     └─ residual coverage ledger
                                                                        (append-only，不直接计票)

main frontier ── completeness-first frozen comparator ── core entity + modifiers
                                      │
                                      ├─ margin/obligations sufficient → static Top-1
                                      │
                                      └─ missing typed discriminator → active-evidence track
```

关键不是增加模块，而是改变职责：registry 负责不误合并，ledger 负责不漏候选，frontier 负责只让有资格的对象竞争，comparator 负责病例特异比较，active gate 负责改变信息集。

---

## 1. 哪些方向已经试过，不能再包装成“新尝试”

### 1.1 已充分试过或方向性关闭

| 方向 | 已有证据 | 当前状态 |
|---|---|---|
| 无条件增加调用/候选 | e7 late calls、Collapse3w、E12 k5→10 | 边际 capture 极低、干扰增加；关闭 fixed-fill |
| 换 selector prompt | R4 S4 variants、E4 多 selector、R6 X1/X1b | selector 可动，但继续微调文案不是主线 |
| 拆两轮决赛 | MSplit | 失去跨组语境，净退化；关闭该实现 |
| C4 ledger/score/veto | APHHM-C、R6 veto counterfactual | 净伤害；关闭默认路径 |
| 去 axis/调纯度/扫 K | APHHM-C K4/K6/K10/NoAxis | 单独不足，不能突破前沿 |
| blind near-dedup | R6 全 800 | Collapse3c/MultiStance 均下降；关闭 |
| evidence-consistent sibling deletion | R6 CompactForest X3 | 弱池有害、强池近零；不作默认 |
| 删除共享 span | R6 X2 | span-resolved 后仍有害；关闭 |
| 按 evidence 数量配额 | R6 X5 | 有害/无益；关闭 |
| 简单顺序 shuffle | R6 X4 | 平均 spread 小；不是主性能杠杆 |
| 普通多视图/角色投票 | MultiStance、E9、Compact4 | 真实 novelty 有小收益，重复/角色不是独立票 |
| 顺序多医生共识 | B06/E10 | 是 rank propagation/consensus compression，不是独立覆盖 |
| generic RAG/refine | B07/E11 | query-top chunks 多不 case-specific，收益主要 partial |
| 自由生成 relation graph | E6/E7c/RCR-3 | span/方向/type/requested-object 不过门；当前实现关闭 |
| hard time veto / prompt soft veto | E8 | hard 不安全，soft 净益未确认 |
| unexplained-span Call-4 | E14x | 新增 135 实体但无 safe-exact discovery；关闭该 gate |
| 仅凭 specialty 的路由依据 | R6 full-800 specialty labels/exclusive AUC | 现有臂的专科分工信号未过噪声门；router 本身未随机试验，但缺乏立项依据、降为低优先 |

### 1.2 已取得部分成功，应继承而不是重跑

| 可继承机制 | 证据 | 下一版如何使用 |
|---|---|---|
| 每候选 verbatim evidence | APHHM 历史 MCR conversion +16.5pp | 作为 candidate contract，不再作为新 arm 单独宣传 |
| Forest-style evidence integration | E4 胜过 evidence-count | 作为 comparator 候选和弱控制，不声称 universal winner |
| 真实独有视图 | E9 complete +3.25/+3.50pp | admission 看 novelty/provenance，不按 view 数投票 |
| 高信息生成池 | R6 X1、CompactForest v1.1 | 低调用独立 proposal 的生成基座 |
| exact/frozen identity | E7/E7b | 安全不变量，不当作完整性能治疗 |
| raw evidence 可回看 | E6/E12 | derived representation 只作索引，不作唯一真相 |
| 一次冻结 comparator | E4/E12 | 避免把重采样方差写成 depth gain |
| Lite-like 简单服务合同 | E2/RCR3 | 作为当前部署控制和可靠性下界 |

### 1.3 “未尝试”的严格定义

“未尝试”在本文中的精确含义是：**尚未以本文指定的 executable state topology、确定性 hard gate、root-owned endpoint 和关键 placebo 做过干净检验**；不表示 `requested_object`、relation 或 evidence 字段从未在旧系统中出现。一个方向只有满足下列条件才列入本路线图：

1. 改变了被检验的 causal interface，而不只是换模型或 prompt；
2. 现有实验没有用相同 estimand 和关键控制完成它；
3. 能预注册主失败条件，而不是只期待 overall accuracy 上升；
4. 能区分 capture、retention、scope compression、catastrophic substitution 与 service；
5. 不依赖 safe-exact/legacy-chain 冒充临床完整性。

---

## 2. 所有下一轮实验共用的测量合同

### 2.1 主端点

静态轨主端点：

1. **ITA overall clinical-complete Top-1**：capture、admission、conversion 与 service 的端到端主 estimand；
2. **处理前冻结 exposure stratum 的 retention**：由 base pool 或 outcome-blind master manifest 在处理前定义，避免用处理后暴露选择病例；
3. **post-treatment common-exposed conversion**：只作 selector-side 条件 sensitivity，明确可能受 post-treatment conditioning/collider 影响；
4. `clinical-complete exposure`：actual comparator payload 中是否存在至少一个完整请求对象；
5. relation transitions：
   - specificity rescue；
   - object rescue；
   - scope compression；
   - catastrophic substitution。

次端点：compatible-partial、C∪P、safe-exact、task、service/schema、cost。禁止将次端点改名为主端点。

### 2.2 统计合同

- unit of inference = case；
- DA/MCR 分开，ALL 只在预冻结时报告；
- 预定义少量 coherent contrast families，Holm 校正；
- paired exact/McNemar + case bootstrap；
- 多候选/多类型时使用 case random intercept 的层级 logistic 或条件模型；
- ITA 是端到端主 estimand；common-served 与 post-treatment common-exposed 只作条件 sensitivity，不能无偏识别 membership/admission 总效应；
- 新 capture 与由**处理前** base/master manifest 定义的 retention 分开；
- 所有模型面板结果标为 sensitivity；能力结论由 arm-blind human-root 负责；
- candidate order 随机化并记录，至少一个冻结 canonical order；
- provider、retry、schema、tokens、latency 全量记录，但不把 provider 调优当科学 arm。

外部确认的样本量不沿用单臂二项率粗算；应在锁定 primary paired contrast、最小有意义 complete 差值、预期 discordance、service missingness 和 DA/MCR 分层后做配对功效设计。

### 2.3 候选对象最小 schema

```json
{
  "entity_id": "canonical immutable id",
  "core_diagnosis": "disease/entity core",
  "requested_object": "disease|etiology|subtype|manifestation|complication|composite",
  "modifiers": {
    "etiology": [],
    "anatomy": [],
    "time_stage": [],
    "subtype": [],
    "complication": []
  },
  "support_spans": [],
  "unique_discriminator": [],
  "strongest_counterevidence": [],
  "missing_obligation": [],
  "provenance": [],
  "admission_state": "main|residual|quarantine"
}
```

`requested_object` 不能只是自报字段；它必须控制哪些候选可互相取代、哪些 modifiers 是 complete 的必要条件，以及何时只允许输出 compatible-partial。

### 2.4 构造与 admission 标签的盲法合同

`unique_discriminator`、`decisive`、`modifier completion`、`rare` 和 `high-specificity` 都可能产生事后 gold leakage。它们只能由 raw vignette、冻结 source spans、外部预定义知识规则和 outcome-blind candidate manifest 构造；构造者/模型不得看到 reference、arm winner、旧 endpoint、错误码或成对结果。

- `rare` 由冻结外部 prevalence/ontology 定义，而不是“reference 很罕见”；
- `modifier completion` 由任务请求层级与预冻结 object schema 定义；
- `unique` 是相对同一冻结 pool 的 span/命题关系，不是“只支持 gold”；
- admission-label agreement、误纳入与漏纳入按 candidate type 分报；
- 任何需要 reference 才能构造的标签只能用于离线评估/stratification，不得进入在线 treatment。

---

## 3. Phase 0-A：full-pool human-root clinical relation census

### 3.1 为什么它是第一优先级

旧 width 回归需要的临床分母至今不存在：79 臂迁移只覆盖各 arm-case 的 Top-1。E2 已对九臂**完整 candidate registries** 中的 3,103 个 candidate–reference relations 做了 exhaustive human-root partition，并另外闭合 2,878 个 unique case-output clusters/7,200 个 case-arm Top-1 行；E2 本身的 full-registry relation 分母已经闭合。

真正缺失的是旧 14 臂 APHHM width OLS 以及 E4/E5/E9/E12 等非 E2 实验的 `case × actual comparator pool-member × requested-object × modifier specification` root 分母，尤其是只出现但从未夺冠的候选。继续用这些实验的 safe/legacy pool recall 除 model-panel complete Top-1，会制造一个混口径的“clinical conversion”。

### 3.2 设计

从以下冻结池中抽取或全量纳入：

- 旧 14 臂中仍有 immutable actual pool manifest 的所有候选，用于直接重审历史 OLS；若某臂 provenance 不完整，则明确不可重算，不以模型补标签；
- E5 base4/width6/width8/typed additions；
- E4 fixed union pool；
- E9 single/real union；
- E12 k5/k10 raw pools；
- 一个新架构候选池与 Lite/Collapse3c 控制。

如果旧 14 臂无法达到完整 provenance/coverage 门，则以一个新、小规模、预注册的 nested-pool 实验取代其临床系数估计，并正式保留旧 OLS 为 legacy-only 历史描述；两种方案不得拼接成同一回归。

`eligible candidate` 必须在 freeze 时由明确 manifest 定义：属于哪个实验/arm、actual comparator payload、candidate ID、原始 label/alias、位置、payload SHA、builder/version 和 provenance。不能在看到结果后增删。对每个候选 relation，由 arm-blind human-root 判：

- complete；
- compatible-partial；
- incompatible/wrong object；
- uncertain；
- candidate 与 reference 的 type/scope/parent/subtype/component relation；
- visible evidence 是否足够支持该 relation。

复用键至少为：

```text
case × canonical entity × requested-object × normalized modifier specification × candidate-card version
```

同一 core entity 的 parent/subtype/composite 表达若 modifiers 或 requested-object 不同，不得仅因 `entity_id` 相同而复用。原始 alias、所在 arm、顺序和候选卡版本保留血缘，但不展示给 reviewer。卡片随机候选顺序，不显示 arm、rank、winner 或旧 endpoint。

可跨臂复用的只是 candidate–reference **semantic relation**。candidate-specific evidence 是否忠实、provenance 是否闭合、以及 actual payload 中是否具备充分证据，必须按对应 arm/payload 单独审计；不能因 entity relation 相同而“一候选只判一次”后连 evidence treatment 也复用。

无法消解的 `uncertain` 不隐式排除：主表保存 C/P/N/U；complete exposure 同时报保守下界（U 非 complete）与最宽上界（所有可能 complete 的 U 计 complete）。若上下界跨越预注册决策门，则该对比不得给单一胜负结论。

### 3.3 主要产物

- 真正的 full-pool complete exposure；
- conditional complete conversion；
- marginal complete capture per admitted candidate；
- type×family×width interaction；
- safe-exact/legacy-chain 对 pool relation 的 calibration；
- 后续所有 membership 实验的 root-owned truth table。

### 3.4 成功与停止门

- 100% eligible pool relations 进入双人独立初审，所有 complete-boundary/fine-label 冲突由第三位 root adjudicator 处理；
- complete boundary 初审 raw agreement ≥90%，并同时报告 prevalence-robust Gwet AC1，目标 ≥0.75；fine relation raw agreement ≥80%、AC1 ≥0.60；
- irreducible `U` 总体不得高于 5%，任一 `family × candidate type` 不高于 10%；
- 至少 95% eligible relations 得到 resolved root C/P/N，其余全部进入显式 bound；
- 若可靠性/覆盖门未达，只能发布描述性审计，不得拟合 clinical width coefficient、训练 admission gate 或宣称架构优越；
- 不确定项不强行 majority，不从分母静默删除。

### 3.5 新颖性

E2 已完成九臂 full-registry human-root census，79 臂迁移已完成 model-panel Top-1 census；尚未闭合的是上述**非 E2 实验 actual comparator pool-member、requested-object-aware** 的 root exposure census。

---

## 4. Phase 1-A：按独有判别信息 admission，而不是按固定 `k`

### 4.1 假设

当前张力来自一个状态承担两个冲突职责：

- coverage 要求“不漏掉低先验对象”；
- ranking 要求“只比较有判别资格的对象”。

将 registry 拆成 residual ledger 与 evidence-qualified main frontier，可以保留 coverage 而不让所有候选立即参与冠军竞争。

### 4.2 三臂最小实验

所有臂共享同一 raw proposal union、canonical IDs、evidence spans 与 frozen comparator：

1. **Fixed-`k` control**：按当前 outcome-blind priority 填满 k；
2. **Typed fixed-`k`**：加 requested-object/type，但仍填满 k；用于隔离 typing；
3. **Qualified frontier + residual ledger**：
   - 有 candidate-unique support 或能解释未覆盖 decisive finding 才进 main；
   - true synonyms 聚合 provenance，不新增竞争票；
   - 无独有 discriminator 的 plausible candidates 留 residual；
   - residual 不丢失，但在 primary first pass 中不展示给 comparator，也不动态晋升；
   - 不设置“必须填满”的下限。

可加一个 **sham qualification** 控制：随机挑同数量候选进入 main，以排除纯缩窄效应。

动态晋升属于第二阶段独立实验，只有 §9 的 missing-discriminator gate 先通过校准后才允许。晋升触发器不得使用 comparator 自报 `complete/confident/sufficient`；须由冻结的外部规则或独立验证 gate 决定。预先固定最多晋升数、outcome-blind 晋升顺序、总比较/调用预算和停止规则，并分别报告 `main-first-pass` 与 `post-promotion`，避免把更多计算冒充 admission 效应。

### 4.3 admission 规则必须可执行

候选进入 main 至少满足一项：

1. 引入一个当前 main 中没有的 clinical object；
2. 有至少一个 source-grounded、对 top competitor 不共享的 decisive span；
3. 能解释一个 main candidates 均未解释的高特异 finding；
4. 是当前请求对象必需的 modifier completion；
5. 是带独有高特异证据的低先验 rare candidate。

仅有“另一位 doctor 也提到”“支持条数更多”“换了角色名”不构成 admission。

### 4.4 主检验

- complete exposure 是否不降；
- 处理前 base/master exposure stratum 的 complete retention 是否上升；
- post-treatment common-exposed 结果仅作条件 sensitivity；
- residual 中 complete object 的漏晋升率；
- main frontier qualified width 分布，而非平均 raw width；
- catastrophic substitution 是否下降；
- service/schema 是否不恶化。

### 4.5 失败门

若 qualified frontier：

- 降低 complete exposure；或
- 增加 catastrophic substitution 多于 object rescue；或
- 只是缩窄池而没有优于等宽 random/sham；

则 admission contract 被否证，不能以“理论更合理”保留。

### 4.6 新颖性

历史 width/K、near-dedup、group nomination 都是删除/截断规则；没有一个实验把 **coverage 保留** 与 **冠军竞争资格** 分成两个持久状态，并以 candidate-unique discriminator 作为晋升条件。

---

## 5. Phase 1-B：完整诊断对象因子化，而不是 flat label competition

### 5.1 假设

DA 的大量“干扰”并非不同疾病竞争，而是同一 core entity 的 parent/subtype/etiology/anatomy/complication/composite 表述互相抢槽。把它们平铺为多个 candidates，会同时降低 slot efficiency 和 scope stability。

### 5.2 新架构

将诊断表示为：

```text
core entity
  ├─ etiology
  ├─ anatomy/site
  ├─ temporal/stage
  ├─ subtype/molecular modifier
  └─ complication/composite component
```

规则：

- exact/frozen synonyms 共享一个 core ID；
- parent/subtype 不是 synonym，而是同一 lattice 的不同粒度节点；
- comparator 先比较 core entities，再检查 modifiers 的 evidence obligations；
- generic core 不会因为多个 subtype 占满 frontier 而被机械删除；
- complete 需要满足 reference 指定的必要 modifiers；
- evidence 只支持 core 时，输出 compatible-partial，而不是虚构 modifier；
- 多个 view 对同一 core 的支持聚合 provenance，不增加票数。

### 5.3 因果对照

共享同一 proposals/evidence/comparator backbone：

1. flat labels；
2. exact identity only；
3. factorized object lattice；
4. text length、node 数和序列化结构匹配、但不改变 object topology 的 structure-sham；
5. deliberately corrupted modifier mapping placebo。

reference 的必要 modifiers 由看不到 arm outcome/冠军的 root protocol 在运行前冻结，不能在观察模型输出后补写；模型 treatment 仍不得看到 reference。

### 5.4 主端点

- P→C specificity rescue；
- C→P scope compression；
- sibling crowding 与 duplicate slot 数；
- complete core retention；
- modifier hallucination；
- DA/MCR interaction。

### 5.5 失败门

如果 factorization 只提高 lexical exact/safe-exact，human-root complete 不升；或 modifier hallucination/catastrophic substitution 上升，则不能宣称解决对象天花板。

### 5.6 为什么不是 RCR-3 重跑

RCR-3 有 `requested_object` 字段，但它不是 executable gate：manifestation、etiology、subtype 仍混排夺冠，relation/spans 也不稳定。这里检验的是尚未被干净测试的 **executable core/modifier state topology 与选择合同**，不是宣称 requested-object 概念从未出现，也不是再生成一份 typed JSON。

该阶段只在 Phase 1-A admission 合同过门后启动；rare protection（§8）作为预定义 stratum/ablation，避免三套前沿机制同时改动而无法归因。

---

## 6. Phase 1-C：membership × evidence binding/presentation × comparator 的联合因果立方

### 6.1 要回答的问题

E4 只改 selector，E5 只改 membership，E9 同时改变 view/candidate/evidence。三者单独不能回答：

> 一个新增候选之所以有益或有害，究竟来自它的 membership、本身的独有证据、证据在上下文中的重复方式，还是 comparator？

### 6.2 分块随机化设计

“unique decisive evidence”与“shared evidence”在临床语义上天然不同，不能直接随机替换后称为纯 provenance 效应。先由 outcome-blind protocol 将真实 spans 按 `candidate-unique/shared/none` 分层；这个自然层只作 effect modifier。真正随机操纵的接口为：

1. **Membership**：base vs add one typed candidate；
2. **Span→candidate binding**：正确绑定 vs 病例内等长度、等位置、语义可核验的 outcome-blind permuted binding；
3. **Duplication/presentation**：每个命题一次 vs 在 token、container、位置匹配的结构中重复；另设 node-only/structure-sham；
4. **Comparator**：weak evidence-count/control vs completeness-first candidate-specific contrast。

可分成两个预注册 block 而非一次跑满所有组合：Block A 识别 membership×binding×comparator；Block B 在固定 membership 下识别 duplication/presentation×comparator。候选类型至少分 sibling、verified synonym treatment、distinct disease、modifier completion。

order 是病例内随机化因素。每一种**不同的 ordered payload**有自己的冻结 cache/result；只有逐字相同的 ordered payload 才能跨对比复用。重复运行只用于预注册的聚合/运行噪声敏感性，不把 provider 或独立重采样当 treatment effect。

### 6.3 需要闭合的转移

- new complete capture；
- direct alternative capture；
- shared-candidate context reorder；
- evidence rescue；
- scope compression；
- catastrophic substitution；
- order-only flip；
- schema/service failure。

### 6.4 关键交互

- membership × natural unique-evidence stratum：只有带 unique evidence 的新增项是否正收益；
- membership × comparator：强 comparator 是否降低 sibling harm；
- binding × comparator：candidate-specific contrast 是否依赖正确 candidate binding；
- duplication × comparator：重复是否被错误当成更强证据；
- type × family：DA scope vs MCR distinct disease；
- order × membership：context effect 是否对排列稳健。

### 6.5 失败门

不能把某个 gain 归因于“多视图”“Forest”或“pairwise”，除非在 membership、真实 span 内容、binding 与 presentation 固定后仍存在。若 correct/permuted binding 或 single/duplicate presentation 的效应不可区分，说明所谓 evidence integration 仍主要响应 salience/格式。

### 6.6 新颖性

现有 E4/E5/E9 提供三个边，但没有在同一病例、同一候选与同一 root-owned endpoint 下闭合这组 randomized interfaces。

---

## 7. Phase 2-A：关键事实保真实验，而不是再比较 raw 与摘要

### 7.1 假设

S1/graph 的损失来自删除或反转 decisive pathology/anatomy/etiology/time relations，而不是“文本变短”本身。

### 7.2 精确干预

对预先由 arm-blind adjudicator 标记的关键 spans，生成四个输入：

1. raw vignette；
2. S1/flat/graph derived input；
3. derived + **critical span restored**；
4. derived + 同长度 **noncritical span restored**。

对数值、polarity、time、anatomy、pathology、etiology 分层。所有条件共享 frozen candidates 与 comparator，避免把表示效应混入生成。自动比对加盲法人工复核必须确认“恢复”的命题在 derived input 中确实不存在，而不是已被等义保留。

所有主条件先统一遮蔽 `was suspected/diagnosed as` 等 author-diagnostic assertions；断言可见性另作独立随机因子，防止 raw、span 恢复与 source-cue leakage 再次混合。

### 7.3 主端点

- complete rescue caused by critical restoration；
- reason/rank 是否明确引用恢复 span；
- noncritical matched control 的差值；
- task-only rescue 与 clinical rescue 分开；
- relation transition 与 benchmark identifiability 交互。

### 7.4 失败门

若 critical restoration 不优于 matched noncritical restoration，或增益只出现在 task mapper，则“关键事实丢失造成 ceiling”的具体实现假设不成立。

### 7.5 新颖性

E6/E12 比较了整体表示；没有用 exact deleted/restored span 做最小因果干预，也没有同时控制作者诊断断言。

---

## 8. Phase 2-B：单调 canonical frontier 与低先验高特异候选保护

### 8.1 假设

APHHM 少数真实优势来自让低位置先验、但有强特异 evidence 的实体长期存活；失败来自不可校准的全局 arbiter、代表化和 local pruning。应把这个偶发行为变成显式可消融合同。

### 8.2 机制

- canonical entity ID 与 append-only history；
- 每 entity 一个竞争槽，所有 provenance/evidence 仍保留；
- core/subtype 形成 non-dominated frontier；
- 新候选默认 residual/quarantine，不直接夺冠；
- 低先验候选只有携带 candidate-unique 高特异 evidence 才获 protected status；
- 删除必须绑定同 object、同 episode、同 anatomy 的更强 counterevidence；
- “更常见”“证据条数少”不能单独删除；
- comparator 输出 prior、local likelihood evidence 与 modifier completeness，三者不压成不透明单分数。

### 8.3 对照

1. posterior-only；
2. posterior × evidence count；
3. posterior + calibrated local discriminator；
4. completeness-first + rare protection；
5. no-protection ablation。

同 proposals、同预算、同 evidence，预先冻结 rare/high-specificity stratum；不得用 gold 在线决定保护。

`rare/high-specificity` 的在线标签完全遵守 §2.4 盲法合同；任何需 reference 才能确认的 stratum 只用于离线 effect modification，不进入保护规则。

### 8.4 主端点

- rare complete-object retention；
- pruning-caused losses；
- mimic-driven catastrophic substitutions；
- protection precision；
- overall complete 仅作联合结果，不掩盖 protection 的 gain/harm。

### 8.5 失败门

若保护造成的 mimic substitutions 多于 complete rare rescues，或 root review 后效应消失，则保护规则淘汰。

### 8.6 新颖性

旧 APHHM 有不透明低先验旁支，C4/ledger 也曾尝试数值保护；没有实验将 **独有高特异 evidence** 设为唯一保护资格，并用 monotone non-dominated frontier 约束删除。

---

## 9. Phase 2-C：候选对反事实判别器与校准 abstention

### 9.1 假设

当前 comparator 常能写流畅理由，却未回答真正的判别问题：

> 如果 A 而不是 B 为真，应额外看到什么？现有病例是否提供、否定或根本没有该信息？

将 top pair 的预期观察、缺失义务和反证显式化，可以测出“现有信息不足”，而不是强迫在共享证据上选一。

### 9.2 输出合同

对每个 top pair：

```text
shared evidence
A-unique expected evidence
B-unique expected evidence
observed support for each
valid counterevidence for each
missing discriminator type
current evidence sufficiency
decision / abstain / request evidence
```

所有 observed claims 必须回指 raw spans；医学背景知识与患者观察分开标记。

### 9.3 对照

- free-form rationale；
- evidence-count；
- ordinary pairwise；
- counterfactual discriminator；
- corrupted expected-finding placebo。

### 9.4 主端点

- 处理前 exposure stratum 的 complete retention；
- post-treatment common-exposed conversion 仅作条件 sensitivity；
- unjustified confidence；
- abstention calibration；
- missing-discriminator label 的 root agreement；
- E9 duplicate/E5 sibling 下的稳定性。

### 9.5 失败门

若反事实字段不能预测 root-reviewed gain/harm，或 corrupted placebo 效果相同，则它只是更长 rationale，不应进入 active gate。

静态 `abstain` 在 ITA 中仍占一个未给 clinical-complete Top-1 的结果，不能从分母删除；同时单报 selective risk、coverage、转人工/进入 active gate 的成本与延迟。进入 active track、延后决策和最终无答案是三个不同状态，必须在 freeze 时定义，不能靠弃答困难病例虚增 conversion。

### 9.6 新颖性

现有 pairwise/Forest 会比较证据，但没有把“缺失什么才可区分”作为独立、可校准、可触发后续行动的输出对象。

---

## 10. A1：主动获取新患者证据——单独建立 active-diagnosis benchmark

### 10.1 为什么这是最有希望、也最容易被假实现的方向

旧 static 范式只能在同一证据集上增加候选。若 top hypotheses 的 decisive discriminator 根本不在 vignette，继续排序只会增加流畅性，不增加信息。

但 E14x 不是这个实验：它按 unexplained spans 再生成候选，没有选择问题/检查，也没有获得独立新患者证据。E11 的 generic RAG 主要检索弱 lexical bundles，也不是 patient evidence acquisition。

### 10.2 两阶段 benchmark

#### 阶段 A：retrospective evidence-release

选择病例中可按时间切分的真实信息：

- initial presentation 作为静态输入；
- later pathology/imaging/lab/follow-up 作为隐藏 evidence bank；
- 每个隐藏结果有获取成本、可请求 type 和时间戳；
- 系统不能自由浏览全部后续文本，只能从允许 action space 中选问题/检查。

为了避免把“读未来答案”当能力，benchmark freeze 还必须满足：

- 每个 action 由临床审查员确认在 initial timepoint 可执行，不能请求当时不可能知道或实施的项目；
- primary action-complete subset 只包含预定义菜单中每个可选 action 都有真实结果、明确 `not_available` 或可验证“未执行”的病例；历史未执行不得当作阴性；
- 若只保留历史实际执行过的 actions，则明确这是受临床选择偏倚约束的 off-policy benchmark，不能评价未执行检查的最优性；
- hidden pathology/follow-up 去除 final diagnosis、source title、回顾性总结和答案性措辞，只返回该 action 合法产生的原始结果；
- 每个 action 记录成本、延迟、侵入/风险、不可得、无结果和无谓检查；
- action menu、释放函数与泄漏审计在模型运行前冻结。

系统先提交：

- top hypotheses；
- missing discriminator；
- 选择的 action；
- 预期结果如何改变 odds；
- 若无可行动信息则 abstain。

然后 benchmark 返回真实隐藏结果，再允许一次冻结更新。

#### 阶段 B：前瞻或独立模拟确认

只有阶段 A 通过后，才在新队列或由专家构造的可行动 vignette 上确认。不得用当前 800 例反复调 gate 后再称外部成功。

### 10.3 对照

1. no acquisition；
2. random cost-matched action；
3. generic “ask for more tests”；
4. oracle best available action（只作不可竞争的上界）；
5. typed discriminator policy；
6. adversarial plausible but non-discriminative result。

### 10.4 主端点

- information-need resolution precision/recall；
- action relevance；
- source-grounding accuracy；
- diagnostic information gain per unit cost；
- calibrated abstention；
- post-acquisition complete transition，仅在 evidence-eligible cases 报告；
- unnecessary action rate 与 harmful anchoring。

### 10.5 失败门

在以下任一条件成立时，不得声称突破诊断 ceiling：

- 系统不能稳定识别 missing discriminator；
- action 与 root-defined need 无关；
- random/matched control 同样有效；
- 新证据被错误绑定到 object/episode；
- 只增加 partial/task，不增加 eligible cases 的 complete；
- 成本/无谓检查超过预注册门槛。

### 10.6 与静态系统的关系

主动轨不应以 overall static accuracy 为首要排名。正确比较是：

- 在静态证据不足且有合法 action 的病例中，是否准确识别需要行动；
- 获取的信息是否真实解决声明的判别问题；
- 获得证据后是否减少 root-reviewed uncertainty。

它是一种新能力，而不是给 static arm 偷加信息后继续混排。

A1 改变患者信息集，并以 no-action 为控制；A2 只改变医学知识支持，并以 no-retrieval 为控制。二者分别报告，均不与静态主轨总体 accuracy 混排。

---

## 11. A2：typed knowledge retrieval——只查缺失医学关系，不做病例相似检索

### 11.1 与 patient evidence acquisition 的区别

这一方向不获得新的患者检查结果，而是补充：

- 某 subtype 的 defining criterion；
- 某 test 在特定病程/人群中的 sensitivity；
- disease–etiology relation；
- competitor 的关键反证；
- medication/time causality 条件。

它能改善如何解释已有患者证据，但不能伪装成患者事实。任何 retrieved statement 都进入 `medical_knowledge` namespace，不得写入 patient event/state；A2 是知识支持轨，不是 A1 患者证据轨。

### 11.2 设计

先由 counterfactual discriminator 生成一个 typed information need，再检索 curated corpus：

```text
need_type
target_entity_pair
required relation
population/time/scope
source quality threshold
```

chunk admission 由独立 reviewer 判：same entity/subtype、broader context、competitor、generic、irrelevant。系统必须允许 `no actionable evidence`。

### 11.3 对照

- no retrieval；
- E11-style lexical bundle；
- random matched-length text；
- hard-negative but plausible competitor evidence；
- curated typed retrieval。

### 11.4 主端点

- source relevance/quality；
- requested relation resolution；
- unsupported patient-fact hallucination；
- eligible-case complete transition；
- rare candidate deletion harm。

### 11.5 失败门

typed retrieval 在 relation/source gates 通过前，不进入诊断 comparator。若 generic/random context 与 curated retrieval 效果相同，则检索只是 salience injection。

### 11.6 新颖性

E11 测的是 query-top contextual bundle 与 generic refine；没有先声明 typed need，也没有独立验证 chunk 是否解决该 need。

---

## 12. Phase 2-D：确定性 relation substrate 通过硬门后再上线

### 12.1 核心原则

不要再让一个 LLM 同时决定：

- node 是什么；
- span 在哪；
- relation 方向；
- inverse；
- polarity/time/scope；
- 该 edge 是否可推动冠军。

先建立可验证 substrate，再测试 relation 是否有增量。

### 12.2 离线硬门

- offset-based span alignment；
- deterministic node/type signatures；
- inverse normalization；
- duplicate pair collapse；
- cycle/contradictory-direction rejection；
- `negative`、`not tested`、`normal at t`、family history、proband/maternal/fetal scope 分型；
- relation 无 source support 时为 `unknown`；
- candidate citation closure：证据删掉，依赖 candidate 进入 quarantine；
- requested-object executable gate。

### 12.3 三臂在线测试

1. no relation；
2. validated relation；
3. deliberately corrupted edge placebo；
4. node-only/structure-sham。

所有臂共享 nodes、raw spans、pool、order 与 comparator。corrupted 与 validated payload 的 edge 数、位置、标签长度、引用数量和 serialization 完全匹配，只改变经验证的关系语义，避免把怪异格式/salience 当 relation effect。

### 12.4 主端点

- relation fidelity/inverse consistency/citation coverage；
- relation-caused catastrophic substitution；
- complete rescue；
- corrupted vs validated 的差异；
- service/schema。

### 12.5 失败门

在线前 relation fidelity 必须过预注册阈值。若 validated 与 corrupted edges 对 champion 的影响相同，说明 selector 响应的是 graph salience，而非关系语义，整条路径停止。

### 12.6 新颖性

E6/E7c/RCR-3 测了自由生成 graph/edge/inheritance；尚未以 deterministic substrate hard gate、salience-matched placebo 和 root-owned endpoint 做 online causal contrast。

---

## 13. Phase 2-E：确定性时间/阴性证据矛盾引擎

### 13.1 假设

E8 证明 absolute hard veto 不安全，prompt-only soft policy 又未确认净益。问题不在“时间无用”，而在 episode/object/anatomy/test sensitivity 没有同时约束。

### 13.2 规则

一个阴性结果只有同时满足以下条件，才可成为强 counterevidence：

- 同一 candidate object；
- 同一 episode/time window；
- 同一 anatomy/site；
- 检查在该阶段具有足够 sensitivity；
- 不是 `not tested`、技术不足或治疗前后不可比；
- 没有后续更高权重阳性证据。

不满足时只能作为弱 rank feature，不可 veto。

### 13.3 对照

- historical atemporal hard；
- prompt soft；
- deterministic typed engine；
- legal-order permutation；
- invalid-time permutation；
- no-time control；
- 行数、位置、标签长度与引用数匹配的 time-structure sham。

### 13.4 主端点

- false hard-veto rate；
- complete reference retention；
- temporal contradiction fidelity；
- legal order stability；
- net complete rescue/harm。

### 13.5 失败门

预先用逐字相同 payload 的独立运行/冻结复现估计运行噪声基线。若合法行顺序或 invalid-time 的 effect 未超过该基线，或与 structure-sham 不可区分，则不能归因 temporal reasoning；应先稳定 comparator，再谈性能。

---

## 14. Phase 0-B：evidence sufficiency 与 source-cue leakage 审计

本节虽为便于将静态与主动取证接口连读而置于后文，执行顺序仍属于 Phase 0：必须在 Phase 1/2 的阈值、gate 与主分析冻结前完成。

### 14.1 设计

对 references 由双盲 adjudicator 判：

- visible text 是否足以识别 core entity；
- 是否足以识别完整 modifiers；
- 关键患者证据是否缺失；
- reference 是否依赖 source title、病例最终诊断句或未展示后续病理；
- 是否存在多个同样合理的 complete objects。

构造 title/final-diagnosis-cue masked 与 unmasked 随机卡；DA/MCR 分开。

### 14.2 用途

- 将静态能力主分析限制到 evidence-sufficient stratum；
- 把 non-identifiable 病例转入主动取证适用性分析；
- 测 architecture × identifiability interaction；
- 识别 raw 优势有多少来自作者诊断结论句。

### 14.3 失败门

若 adjudicator 无法可靠区分 sufficiency strata，则不能把该标签当新的硬过滤器；只作 sensitivity。

### 14.4 新颖性

E2 已有 reference identifiability，但没有完整的 source-cue masked 因果实验，也没有把它连接到 active-evidence eligibility。

---

## 15. Phase 3：冻结架构后的外部确认

### 15.1 进入条件

只有一个静态架构同时通过：

- full-pool root measurement；
- qualified admission；
- object factorization；
- service/schema 门；
- 预冻结 paired development success；

才允许锁定并进入新队列。

active track 则必须先通过 information-need/source/action gates，不能因静态主轨成功而自动放行。

### 15.2 必须冻结的内容

- architecture/code commit；
- prompts/model/provider policy；
- retry/failure handling；
- candidate schema 与 ontology；
- root adjudication protocol；
- primary contrasts、multiplicity family 与 stopping rules；
- DA/MCR 或新 benchmark 的分族规则；
- cost/latency/service targets。

### 15.3 对照与端点

- frozen Lite-like control；
- Collapse3c specificity-retention reference；
- 新系统；
- clinical-complete 为主，C/P/task 分列；
- full-pool exposure 子样本或全量；
- ITA 主、common-served sensitivity；
- paired case analysis。

确认方案在解封前还要写死：

- 唯一 primary paired contrast 与最小有意义 complete 差值；
- 依据 locked development discordance、而非单臂率估计的配对样本量，并为 DA/MCR 各自留足功效；
- ITA 中 service/schema failure 的计法、不可评价输出和失访处理；
- full-pool root census 是全量执行，还是按预定义随机/机制分层子样本执行；若是子样本，权重与外推方法预注册；
- 中期查看、停止边界和任何安全停表；
- active track 另有自己的 evidence-eligible 样本量和端点，不借用静态主轨功效。

### 15.4 禁止事项

- 在确认集上调整 prompt、threshold 或 ontology；
- 把当前 800 例扩样后叫“外部”；
- 根据初步结果补跑有利 provider；
- 只公布 task 或 legacy endpoint；
- 失败后选择性删病例。

---

## 16. 推荐的实际执行包

### 16.1 最小高信息包

若资源有限，只做四项：

1. 旧 14 臂及 E4/E5/E9/E12 等优先非 E2 pools 的 full-pool human-root census；
2. fixed-`k` vs qualified frontier+residual ledger；
3. membership×evidence×comparator 立方；
4. factorized object lattice。

这四项能直接回答：旧斜率有多少是临床真实、admission 是否能同时保 coverage/retention、unique evidence 是否是宽度效应修饰符、DA scope 干扰能否通过对象因子化解除。

### 16.2 完整静态机制包

在最小包上增加：

- critical-span preservation；
- rare-specific monotone protection；
- counterfactual discriminator；
- deterministic relation/time substrate。

### 16.3 主动轨最小包

1. missing-discriminator labeling；
2. retrospective evidence-release action benchmark；
3. typed knowledge retrieval；
4. active eligibility 与 static identifiability 对账。

### 16.4 每轮 Go/No-Go

| 阶段 | Go 条件 | No-Go 后做什么 |
|---|---|---|
| 测量 | full-pool root coverage/reliability 达门 | 不拟合 conversion；先修 adjudication |
| admission | complete exposure 不降且 retention/transition 净正 | 淘汰 gate，不以更窄为胜 |
| factorization | C rescue > compression/hallucination | 回退 exact identity，不上线 lattice |
| causal cube | unique evidence 与 comparator 有可解释交互 | 不再声称 evidence-aware width 策略 |
| active gate | missing need 与 action relevance 校准 | 停止主动取证，不直接跑诊断增益 |
| relation/time | fidelity 与 corrupt-placebo 分离 | 不进 online selector |
| external | 预冻结 clinical-complete 通过 | 不做部署/普遍优越性主张 |

依赖顺序是 `Phase 0 → Phase 1-A → Phase 1-B/1-C → Phase 2 → Phase 3`。Phase 1-A 失败时，不把 factorization/rare protection 与一个未成立的 admission gate 捆绑跑满；active A1/A2 可作为独立能力研究，但必须各自先过 gate，不因静态架构成功自动放行。

---

## 17. 建议的优先级与预期信息价值

| 优先级 | 方向 | 预计信息价值 | 主要依赖 | 风险 |
|---:|---|---|---|---|
| 1 | 优先非 E2 pools 的 full-pool root census | 极高：决定旧 OLS 与新机制池的 conversion 主张是否合法 | 冻结 pools、root reviewer | 成本高但无替代 |
| 2 | qualified frontier + residual ledger | 极高：直接处理 coverage/ranking 冲突 | census、candidate schema | gate 可能漏 complete |
| 3 | membership×evidence×comparator | 极高：识别真正 width effect modifier | 冻结 payload、root endpoints | factorial 规模 |
| 4 | factorized object lattice | 高：直接针对 DA scope/sibling | ontology、modifier obligations | 复杂度/schema |
| 5 | critical-span preservation | 高：隔离表示因果 | span audit | 人工标注 |
| 6 | rare-specific monotone protection | 中高：继承 APHHM 真优势 | unique evidence calibration | mimic harm |
| 7 | counterfactual discriminator | 中高：连接 static 与 active | root missing-need labels | 可能只是长 rationale |
| 8 | active evidence-release | 高但独立：真正改变信息集 | hidden evidence/action bank | benchmark 构建难 |
| 9 | deterministic relation/time substrate | 中高：重启被错误实现否决的理念 | 工程 fidelity gates | 构建成本 |
| 10 | external confirmation | 最终必要 | 架构完全冻结 | 不能过早 |

---

## 18. 预期会产生的新增科学结论

若路线按设计执行，下一轮可以把当前含混的“天花板”拆成可验证主张：

1. 在 human-root complete relation 下，宽度的局部效应是否仍约为 E5 面板锚点；
2. 该效应是否主要由 sibling density、unique discriminator scarcity 或 object-level mismatch 修饰；
3. residual ledger 是否能保留新增 capture 而不引入即时冠军干扰；
4. factorized objects 是否把 DA 的 scope compression 转成显式 partial，而不是错误冠军；
5. candidate-specific evidence 是否只在强 comparator 中产生正收益；
6. compression loss 是否可由恢复一个决定性 span 因果救回；
7. rare protection 是否有正的 root-reviewed benefit/harm ratio；
8. 哪些病例确实需要新患者证据，系统是否能选择有用 action；
9. validated relations 是否与 corrupted graph salience 可区分；
10. 改进能否在未参与开发的新队列复现。

这些结论比再报一条 overall accuracy 或一个新 slope 更有机制价值。

---

## 19. 不建议继续投入的工作

1. 再扫 K=3/4/5/6/8/10，若 admission 仍是 fixed-fill；
2. 再换一组 selector prompt，若 pool/evidence/object contract 不变；
3. 再加一位相同上下文的 doctor 并做多数投票；
4. 再用字符串/embedding 盲合并近邻；
5. 再删除共享 evidence 或按证据条数投票；
6. 再开 C4 ledger/veto 网格；
7. 再做无 typed need 的 generic RAG/refine；
8. 再以 unexplained span 数触发 Call-4 候选生成；
9. 再把 model-panel Top-1 与 safe/legacy pool recall 拼成 clinical conversion；
10. 在当前 800 例继续迭代后声称确认性 superiority。

---

## 20. 可复核来源

- 根因与旧拟合修订：[`APHHM_C_PILOT200_REPORT.md`](../backbone_v1/APHHM_C_PILOT200_REPORT.md)
- 早期跨轨迹漏斗：[`DEEP_TRAJECTORY_MECHANISM_AUDIT.md`](../backbone_v1/DEEP_TRAJECTORY_MECHANISM_AUDIT.md)
- R1 基线快照：[`CASE_TRAJECTORY_AUDIT.md`](../backbone_v1/CASE_TRAJECTORY_AUDIT.md)
- R2/R3 漏斗与失败形态：[`CASE_TRAJECTORY_AUDIT_R2.md`](../backbone_v1/CASE_TRAJECTORY_AUDIT_R2.md)、[`CASE_TRAJECTORY_AUDIT_R3.md`](../backbone_v1/CASE_TRAJECTORY_AUDIT_R3.md)
- 反事实与 comparator ceiling：[`CASE_TRAJECTORY_AUDIT_R4.md`](../backbone_v1/CASE_TRAJECTORY_AUDIT_R4.md)
- 新方法 locus/noise gate：[`CASE_TRAJECTORY_AUDIT_R5.md`](../backbone_v1/CASE_TRAJECTORY_AUDIT_R5.md)
- X1–X5、CompactForest 与已尝试方向：[`CASE_TRAJECTORY_AUDIT_R6.md`](../backbone_v1/CASE_TRAJECTORY_AUDIT_R6.md)
- MOSAIC 历史首轮与五端点纠正：[`MOSAIC_LANDING_TEST_REPORT.md`](../backbone_v1/MOSAIC_LANDING_TEST_REPORT.md)、[`MOSAIC_EXPAND_REPORT.md`](../backbone_v1/MOSAIC_EXPAND_REPORT.md)
- 统一端点综合：[`CROSS_EXPERIMENT_ROOT_CRITICAL_SYNTHESIS.md`](CROSS_EXPERIMENT_ROOT_CRITICAL_SYNTHESIS.md)
- 实验闭环与来源 crosswalk：[`EXPERIMENT_REGISTER.md`](EXPERIMENT_REGISTER.md)
- E4/E5/E6/E7/E8/E9/E10/E11/E12/E14x/RCR-3 owning reports：`results/`
- 79 臂 endpoint migration、common-served、service 与 transition artifacts：`results/ALL_ARM_ENDPOINT_MIGRATION/`

---

## 最终建议

当前证据支持度最高、但仍需上述 root/placebo/failure gates 证伪的静态假设，不是“更窄”或“更宽”，而是 **让候选获得不同状态**：所有 plausible objects 可留在 residual coverage ledger，只有带独有、可引用、同 requested-object 层级判别信息的对象进入 main frontier；comparator 先选核心实体，再补完整 modifiers，并允许在证据不足时不强行把 partial 伪装成 complete。

当前最值得优先验证的范式突破假设是 **真正主动获取缺失判别证据**：先证明当前 top hypotheses 缺什么信息，再选择问题、检查或知识关系，从独立来源取得结果，并以信息需求是否被解决作为首要端点。它必须是一条独立 active track；E14x 的“多生成候选”和 E11 的 generic RAG 都不能替代它。只有通过 action availability、leakage、root relevance 与 cost gates 后，才能称为突破。

两者共同遵循同一原则：**新增计算只有在改变可核验信息集、提高单位候选的条件判别信息，或安全保留一个本会丢失的完整对象时，才有资格被称为突破。**
