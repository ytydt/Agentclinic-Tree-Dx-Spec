# E7a 人工案例轨迹解剖

## 审计边界

本文件不是对自动表格的复述。审计者回到原始 vignette、三个生成视图、实际 registry、实际 selector 响应，以及 exact-synonym 反事实 frontier，逐例追踪“字符串折叠 → 证据归属 → 分数/暴露 → 选择标签”的完整链条。下列案例是按机制杠杆选取的目的性样本，不能用于估计总体发生率；总体频率只取自 800 例全量重放。

`unsafe` 在这里有严格但有限的含义：两个 surface 未被冻结同义词表或可验证的括号首字母缩写判为同一实体，却被 production substring 规则折进同一节点。它不自动等于“临床上一定有害”。有些是错误实体碰撞，有些是父子/部位/时相/并发症关系，还有些是基准答案与临床粒度不一致。正因如此，安全策略不能只是“全部拆开”，而应是“默认不合并、保留关系、由关系/时间/范围感知的 selector 比较”。

## 十个高杠杆轨迹

### 1. DA heldout 261：部位特异性被吞没

- 金标准：`Cutaneous malakoplakia`；实际输出：`Malakoplakia`。
- syndrome 视图提出拼写变体 `Malacoplakia`，mechanism 视图同时提出 `Malakoplakia` 和 `Cutaneous Malakoplakia`，modality 再次提出广义标签。
- substring registry 把后两者合成广义节点，分数由 3.75 增至 5.75；皮肤部位和 *E. coli* 培养证据被转移到广义节点。selector 随后只在广义节点与未被拼写归一的 `Malacoplakia` 之间选择，并将后者斥为 duplicate。
- 机制判断：这是“粒度丢失＋同义词漏并”同时存在。substring 解决了错误的问题（部位父子关系），却没有解决真正的同义词问题（Malaco-/Malako- 拼写）。答案 mapper 可能把广义输出投影为正确选项，但那是下游救援，不能证明前置身份处理正确。

### 2. DA heldout200b 638：局部、播散和宿主限定被压成同一疾病

- 金标准：`Laryngeal histoplasmosis`；实际输出：`Histoplasmosis`。
- raw nominations 同时包含广义 histoplasmosis、laryngeal、disseminated、immunodeficiency-related 四种范围。病例有明确喉部培养和活检证据，却无全身症状，播散型仅由低 CD4 和轻微肺部影推测。
- production 将七次提名折进一个节点，分数 8.60；安全拆分后广义 3.00、喉型 2.50、播散型 2.00、宿主限定 1.00。广义节点的“多视图一致”部分来自不同临床命题，而非对同一命题的独立复现。
- 机制判断：这是典型的范围混叠。折叠既让错误的播散假设为正确家族加分，也让正确的喉部定位失去独立可选性。selector 只能输出广义名称，因此轨迹在 mapper 前已经失去案例所要求的解剖粒度。

### 3. MCR v2 144：错误病因候选给正确综合征输血，但 selector 成功抵抗

- 金标准及实际输出：`Systemic lupus erythematosus`。
- production 把 `Uremic Pericarditis` 并入 `Pericarditis`，使后者的启发式分数从 3.50 增至 6.00，并超过 SLE 的 4.25。病例肌酐仅 1.3 mg/dL，尿毒症病因证据很弱。
- 实际 selector 仍根据 anti-Smith、低补体和激素反应选择 SLE，说明此例的 LLM selector 能覆盖 registry 的错误先验。
- 机制判断：这是“中间机制受损、最终端点暂时稳健”，不是无害证据。若 pool 更宽、证据更弱或 selector 更依赖 score，污染可能转化为错误。括号缩写 `Systemic Lupus Erythematosus (SLE)` 在安全臂中被验证为显式同义词并正确合并，证明安全策略并非机械拆散所有表面变体。

### 4. MCR v2 173：时间状态被广义诊断覆盖

- 金标准：`Chronic subdural hematoma`；实际输出：`Subdural Hematoma`。
- 三个视图分别多次提出 generic 与 chronic 标签。production 合并后形成 8.25 分的广义节点；拆分后 chronic 7.25、generic 4.25，排序首位直接翻转。
- 病例发生在脊麻后 31 天，CT 呈混合密度并有明显中线移位；“chronic”不是修辞，而是时间演化和影像解释的一部分。
- 机制判断：substring 折叠抹掉时相，使 selector 无法比较“急/慢性”范围。此例直接支持时间感知 registry 和 comparator，而不只是更强的通用排序器。

### 5. MCR v2 197：`pseudo-` 与病原性诊断发生语义反转碰撞

- 金标准：`Pseudoseptic arthritis`；实际输出为 `viscosupplementation-related inflammatory reaction`，语义接近但非同一 surface。
- production 把 septic 与 pseudoseptic 的七次提名并成 6.50 分节点；安全臂将 pseudoseptic 6.10 与 septic 4.35 分开。
- 两者的核心区别恰是感染是否存在。字符串包含关系在此不是父子关系，而是鉴别诊断/否定性修饰。把二者证据汇总会使培养、时序和治疗反应的解释失真。
- 机制判断：这是最明确的“词法相似 ≠ 临床接近”。因此 E7a 的 typed edge 只标记 `non_equivalent_lexical_relation`，不把长字符串武断标成 `narrower_than`；临床方向必须由 E6/RCR 的关系抽取和时间/范围比较器确定。

### 6. MCR 200b 322：拆分也会破坏有用的家族共识

- 金标准：`Factitious disorder`；实际输出：`Factitious disorder imposed on self`。
- production 将 generic 与 subtype 合并为 6.25 分，与 somatoform 6.25 并列，selector 选中更具体 subtype。安全拆分后 generic 4.75、subtype 2.00，somatoform 单独以 6.25 领先启发式排序。
- 机制判断：此例不能被诚实地表述为 substring 一定有害。generic 与 subtype 的证据确有可共享部分，且实际 subtype 与病例较匹配。问题是 production 把“证据可继承”错误实现成“实体完全相同”。正确替代是保留两个节点，并通过 `subtype_of`/证据继承规则让 comparator 看见层级，而不是完全隔离或完全折叠。

### 7. MCR 200b 383：仅拆分不足以恢复正确病因粒度

- 金标准及实际输出：`Idiopathic granulomatous mastitis`。
- production 将 idiopathic 与 generic 多次合并，金标准节点分数 7.25；安全拆分后 generic 因跨视图重复达到 5.75，idiopathic 仅 3.75，启发式首位反而变成 generic。
- 病例的正常感染检查正是 idiopathic 限定的重要证据。拆分后若 selector 只按提名次数/支持 span 数，病因限定仍会吃亏。
- 机制判断：安全身份聚合是必要条件而非充分条件。需要把“正常培养排除感染 → 支持 idiopathic 限定”表达为有方向的关系证据，并在完整性比较中要求解释该限定。

### 8. MCR 200b 418：基准粒度与临床粒度冲突

- 数据金标准及实际输出：`Sarcoidosis`；文章/病例的临床目标是 cardiac sarcoidosis。
- production 将 cardiac 与 generic 合并，广义节点 3.25 排首；安全拆分后 ARVC 2.50、cardiac sarcoidosis 2.25、generic sarcoidosis 1.50，简单分数首位变成 ARVC。
- 机制判断：production 合并对该数据集的 exact-like 投影可能有利，却在临床上丢掉受累器官。反过来，纯拆分会稀释同一家族证据并伤害候选排序。应同时报告 pre-mapper 临床标签与 post-mapper 基准投影，否则会把“更适合选择题映射”误判为“诊断机制更好”。

### 9. MCR 200b 407：`lipoma` 是 `myelolipoma` 的字符子串，却不是同义词

- 金标准：`Adrenal myelolipoma`；实际输出：`Myelolipoma`。
- production 把 `Myelolipoma`、`Lipoma` 和 `Adrenal myelolipoma` 全部压进一个 4.15 分节点；安全臂分别为 3.00、1.50、1.00。
- 机制判断：这是纯字符串算法造成的实体碰撞，不依赖临床边界争议。它同时吞掉组织学差异和解剖部位。该例是反对 substring same-as 的直接反例。

### 10. MCR 200b 464：并发症/事件状态被抹除

- 金标准：`ruptured popliteal artery aneurysm`；实际输出：`Popliteal artery aneurysm`。
- production 将 ruptured 与 generic 合并，广义节点 7.00；安全臂分别为 5.00 与 2.00。
- “ruptured”改变紧急程度、病理状态和治疗路径，不应作为可丢弃修饰词。现有 selector 的输入已经没有独立 ruptured 候选，因而无法以完整性为准则惩罚广义答案。
- 机制判断：这类状态限定应进入事件骨架和 scope-aware comparator；只在最终字符串映射阶段补回是不可能的。

## 跨案例机制归纳

1. **错误合并有三种不同后果。** 一是永久删除可选标签（261、638、173、464）；二是把另一个命题的证据、视图一致性和轴加分转移过来（144、197、407）；三是让 benchmark-friendly 广义标签替代临床完整标签（418）。只看最终 accuracy 会把三者混在一起。
2. **多视图一致性被系统性高估。** 当前 registry 在实体同一性判定之后才计算 generator-view bonus；一旦同一性过宽，不同视图提出的父、子、部位、时相甚至相反概念会被计成“独立复现”。这不是普通 calibration 问题，而是分数输入被错误重写。
3. **纯 exact 拆分也不是终点。** 322、383、418 显示证据应在有类型的关系上有限传递；完全隔离会把同一家族的正确信息稀释。RCR-3 的价值应通过“节点分离＋关系保存＋成对完整性比较”整体检验，不能只比较候选数量。
4. **mapper 会掩盖前置机制。** 261、173、418 的广义标签可能被选项 mapper 判为命中，但这不恢复被丢掉的部位、时间或器官信息。后续实验必须同时冻结 pre-mapper diagnosis、option projection 与 mapper rescue/harm。
5. **桥表仍有高精度漏召回。** `Malacoplakia`/`Malakoplakia` 等拼写同义词未被安全臂合并。该漏召回使 exact-synonym 臂偏保守；它不会制造 substring 有害效应，却会低估安全聚合能恢复的共识。新增同义词必须冻结并逐条有来源，不能用模糊相似度回填。

## 对后续臂的约束

- E7b 必须让 selector 在 blind、同证据、同宽度条件下分别看到 legacy、exact 和 typed payload；不能复用旧 champion 充当新响应。
- E6/RCR 的关系类型至少要区分 `same_as`、`subtype/parent`、`anatomic_scope`、`temporal_state`、`complication/event_state`、`contrast/mimic`，并允许 `unresolved`；不得从字符串包含直接推断临床方向。
- E8 的时间/范围 veto 应覆盖 173 与 464 类案例；197 类 `pseudo-` 对照应进入 contrast/mimic 层而非时间层。
- 临床判断端点与 benchmark projection 必须双轨报告；任何只改善 mapper 后选项命中的结论都不得表述为临床机制改善。
