# 召回—转化负相关与范式性诊断天花板：跨轨迹根因分析

> 证据冻结点：`c8175f6356f62e6c94a903f04dc55a39baa071d2`（2026-08-13）
> 分析对象：APHHM/APHHM-C、e7、MOSAIC、Forest/Lite/IMPC、MultiStance、B06/B07，以及 mechanism-v2 E1–E12、E14x、RCR-3 的已归档开发集轨迹与统一端点迁移。
> 本文回答“为什么出现召回—转化张力、天花板究竟由什么决定”；实验路线另见 [`RECALL_CONVERSION_CEILING_BREAKTHROUGH_ROADMAP.md`](RECALL_CONVERSION_CEILING_BREAKTHROUGH_ROADMAP.md)。

---

## 0. 最终裁决

### 0.1 一句话结论

**真实存在的不是“每增加一个候选，转化率必然下降约 4.5 个百分点”的普遍定律，而是：在既有证据不变、候选被平铺进一次比较、对象层级未分型且主池按固定宽度填满时，新增候选的边际判别信息很快递减，而直接夺冠、共享候选重排、不可逆剪枝、对象粒度混排、服务失败和评测投影的代价同时增加；这些因素共同形成当前实现的局部能力前沿。**

这个前沿是真实的，但它属于一组明确条件下的范式：

- frozen evidence：决策只能在已有 vignette 与已有候选证据上重排；
- flat candidate list：病因、疾病、表现、亚型、并发症和复合对象在同一列表竞争；
- fixed-`k` fill：没有独有证据的候选也被机械送入主比较；
- one-shot contextual ranking：所有候选共同进入一次未保证置换不变、对上下文序列化敏感的比较；
- lossy upstream state：表示、去重、组内提名、frontier 和 veto 可在比较前不可逆丢信息；
- endpoint mismatch：legacy-chain、safe-exact、task mapper 与 clinical-complete 衡量不同对象。

它**不属于所有 selector、所有候选比较器或所有诊断系统的普遍上限**。E4 证明同池同宽只换 evidence integration 就能大幅移动转化；E9 的 real-view treatment 在更丰富的候选/证据状态下取得 model-panel complete 净增益；E5 的 nominal synonym arm 成功轨迹 complete 点估计非负、C∪P 为正，而 sibling 为负。这些反例共同否定 raw width 的单因素解释，但不把生成 synonym 的 treatment 当成 oracle true-synonym 操纵。

### 0.2 对旧 APHHM-C 结论的精确更新

旧报告的两条历史拟合：

```text
DA:  legacy conversion ≈ 0.736 − 0.0469 × width
MCR: legacy conversion ≈ 0.820 − 0.0453 × width
```

只能保留为 **14 个相关开发臂、legacy-chain 条件分母下的臂级描述性关联**。它们不是病例级因果回归，也不是 clinical-complete 上限。原因包括：

1. 各臂的 pool、selector、证据形式、方法族、病例数和服务状态同时变化；
2. `conversion` 条件在本臂 pool 已被 legacy-chain 命中，扩池会改变条件人群组成；
3. legacy-chain 接受 substring/resolver bridge，不等于完整临床对象；
4. 14 个臂共享病例、缓存、上游模型与适应性开发，不是独立样本；
5. 旧线覆盖的 width 区间有限，截距和逐 slot 外推没有工程常数含义。

E5 给出了更强的病例内 membership/IIA 证据：在 base pool 已含 safe-exact reference、共享候选文本/ID/相对顺序和 selector 都冻结时，safe-exact 的 direct capture/context reorder 可归因于集合操纵。common-served 的三 reviewer model-panel clinical-complete 则给出临床方向与量级敏感性：width 4→8 下降 17.68pp；九臂全部服务的 162 例下降 17.90pp，折合约 4.48pp/新增候选。common-served 是 post-treatment survivor sensitivity、面板也不是 human-root，不能当总体 clinical causal coefficient；ITA 才描述完整 treatment contract，但混有 service。这个局部量级与旧斜率接近，说明旧线并非纯统计幻觉；DA/MCR、候选类型与增量步长的异质性又证明它不是定律。

### 0.3 “天花板”应改写为条件能力面

更合适的问题不是：

> width 增加 1，conversion 固定下降多少？

而是：

> 在某种 evidence state、候选拓扑、对象层级、admission policy、排列、selector、服务合同和 benchmark family 下，增加一个具有何种独有判别信息的候选，会改变完整对象暴露、共享候选重排和最终选择多少？

可将当前条件转化写成一个待识别的能力面，而不是直线：

```text
V = f(
  qualified_width,
  candidate_topology_and_type,
  unique_discriminator_density,
  evidence_fidelity_and_specificity,
  requested_object_alignment,
  order_and_serialization,
  selector,
  benchmark_family,
  service_contract
)
```

其中 raw `width` 只是 `qualified_width`、近邻密度、证据重复度和 schema 负担的粗代理。

---

## 1. 证据范围、责任边界与术语

### 1.1 实际读取的证据

本分析直接复核了当前 checkout 中的：

- [`APHHM_C_PILOT200_REPORT.md`](../backbone_v1/APHHM_C_PILOT200_REPORT.md)；
- [`DEEP_TRAJECTORY_MECHANISM_AUDIT.md`](../backbone_v1/DEEP_TRAJECTORY_MECHANISM_AUDIT.md)；
- [`CASE_TRAJECTORY_AUDIT.md`](../backbone_v1/CASE_TRAJECTORY_AUDIT.md)（R1 快照，后续由 R2 更新）；
- [`CASE_TRAJECTORY_AUDIT_R2.md`](../backbone_v1/CASE_TRAJECTORY_AUDIT_R2.md) 至 [`CASE_TRAJECTORY_AUDIT_R6.md`](../backbone_v1/CASE_TRAJECTORY_AUDIT_R6.md)；
- [`MOSAIC_LANDING_TEST_REPORT.md`](../backbone_v1/MOSAIC_LANDING_TEST_REPORT.md)（已撤销的历史首轮结果页）与 [`MOSAIC_EXPAND_REPORT.md`](../backbone_v1/MOSAIC_EXPAND_REPORT.md)（五端点纠正版）；
- [`CROSS_EXPERIMENT_ROOT_CRITICAL_SYNTHESIS.md`](CROSS_EXPERIMENT_ROOT_CRITICAL_SYNTHESIS.md)；
- E1–E12、E14x、RCR-3 owning reports 与统一端点迁移产物；
- R4/R5/R6 的反事实探针、复制噪声、病例卡与机制中间量。

用户点名的 `CASE_TRAJECTORY_AUDIT_R1_R6_CRITICAL_SYNTHESIS.md` 和 `INDEPENDENT_APHHM_C_MOSAIC_DEEP_TRAJECTORY_AUDIT.md` 原文不在当前 checkout 或可见 git history 中。本文没有伪称重新读取这两份缺失原文；只使用 [`EXPERIMENT_REGISTER.md`](EXPERIMENT_REGISTER.md) 冻结的 proposal crosswalk，并以已落地的实验和当前综合报告复核其后续状态。

### 1.2 证据等级

| 等级 | 证据 | 可支持什么 | 不能支持什么 |
|---|---|---|---|
| A | E2 full-800、9 臂、完整 registries 3,103 relations、2,878 unique output clusters/7,200 Top-1 行的人类根级 census | 当前 800 开发病例上的 clinical-complete、compatible-partial、transition 与 identifiability | E2 外实验的 pool exposure；外部泛化或部署优越性 |
| B | E4/E5 等冻结病例内操纵；其中 E5 safe-exact membership transition 最干净 | selector、membership、context reorder 等局部因果机制 | common-served model-panel 的总体 clinical causal coefficient；通用系数 |
| C | 79 臂 arm-hidden 三 reviewer model-panel Top-1 迁移 | 全臂发生率敏感性、方向与 service/common-served 对账 | human-root truth；full-pool clinical exposure/conversion |
| D | 定向人工审计、safe-exact、legacy-chain、旧 proxy | 机制定位、异常队列、历史复现 | 未审病例的临床阴性、完整能力排名 |
| E | 病例故事、post-hoc 位置/拒绝话术 | 假设生成、解释已确认效应 | 机制发生率或稳定亚组优势 |

### 1.3 六个不能混写的端点

1. `safe-exact`：normalized exact 或 frozen-safe synonym 的高精度下界；临床同义可能被漏掉。
2. `legacy-chain`：历史 substring/resolver replay；可把 parent/component/fragment 记作命中。
3. `clinical-complete`：输出是否给出请求层级的完整诊断对象；只有全病例、全臂、盲法 human-root 合同下才是能力主端点。79 臂同名字段是 model-panel sensitivity。
4. `compatible-partial`：临床兼容但对象范围不完整。
5. `C∪P`：完整或兼容的 coverage sensitivity；不能改名为 complete。
6. `task`：DA option mapper 或 MCR semantic judge 的 benchmark 投影；两族不能合并成一种诊断能力。

在 23,046 个 served case-arm occurrence 上，legacy-chain 对 complete 的 PPV/recall 为 56.48%/74.47%，对 C∪P 为 98.72%/48.90%。它更接近“稀疏但高精度的兼容覆盖 marker”，不是完整诊断率。

79 臂面板在修正后的 1,173 个 sentinels 上，aggregate fine-label accuracy 为 70.93%；complete boundary accuracy/precision/recall 为 97.70%/84.06%/78.38%，另有 152 条 novel relations 三方分裂保留为 `U`。因此 E5 的大幅 width 方向可以作为敏感性锚，小的 type 差与绝对率不能冒充 root truth。

### 1.4 两种服务 estimand

- **ITA**：按意向处理，schema/builder/provider failure 计失败；描述端到端 treatment contract。
- **common-served**：只看两臂都成功返回可评价 Top-1 的病例；用于拆出成功轨迹内的 membership/representation/selector 差异。

共同服务不是“更正确”的主结果，而是一个 post-treatment sensitivity；ITA 也不能自动被解释为纯认知机制。二者必须并列。

### 1.5 DA 与 MCR 不应池成一个机制系数

- DA 的 reference 常含病因、部位、亚型、stage、并发症或复合时序；候选池常是同一病例轨迹的多个粒度版本，mapper 又能把 partial 投成选项。
- MCR 更常是开放疾病实体竞争；新增 plausible disease 可以直接夺冠，visible evidence 又可能不足以推出病例报告最终 surprise diagnosis。

E5 width 4→8 的共同服务 complete 损失在 DA 为 11.24pp，在 MCR 为 25.33pp；相同净方向来自不同转移机制，不能平均成“普遍 distractor susceptibility”。

---

## 2. 先澄清：召回与转化究竟是什么

### 2.1 一个有用但危险的会计式

若针对同一临床对象定义：

```text
R = P(至少一个 clinical-complete object 进入实际 comparator payload)
V = P(最终 Top-1 clinical-complete | complete object 已进入 comparator payload)
```

只有在 E4/E5 式 **closed pool、champion-ID constrained selector** 中，最终 complete champion 必须来自 actual payload，此时才可做会计分解：

```text
P(clinical-complete Top-1) = R × V
```

开放输出、允许 selector/S3 合成或改写对象时，完整式是：

```text
P(Y_complete) = P(R)P(Y_complete | R)
              + P(not R)P(Y_complete | not R)
```

第二项包含 downstream synthesis、非单调新造和 mapper/projection rescue，不能静默设为零。即便在闭池中，乘积分解也只是一套共同口径下的定义，不意味着 `R` 与 `V` 独立，更不意味着 `V` 只由 width 决定。实际上：

- treatment 会同时改变谁被暴露、池的拓扑、证据与 selector 输入；
- 条件在“已暴露”会引入 post-treatment selection；
- 新暴露病例往往更难，构成效应可在没有同病例干扰时降低 `V`；
- 生成、frontier、selector 可非单调地新造、删除或改写候选；
- 旧报告的 pool match 与 champion match 还不是 clinical-complete 同一对象。

因此旧臂级 `top1 = recall × conversion` 只在其历史 closed-match 定义内是会计恒等式，不是可迁移的临床因果模型。

### 2.2 “候选已在 registry”不等于获得了决策机会

轨迹里至少有三个不同的 recall：

1. raw proposal/完整树是否曾提出；
2. exact identity 后 registry 是否仍可独立寻址；
3. actual selector payload/finalists 是否真正包含。

e7 在 800 例上的 strict 漏斗是：S2 并集 408 → S3 309 → S4 champion 162。S2 已想到的 408 例中，有 250 例在 S3/S4 丢失。MultiStance 的 registry gold recall 约 0.55，但 finalists 约 0.37；组内提名先把近邻正确对象互相挤掉，后期 selector 无法恢复。

因此一部分“转化损失”其实是 **decision-opportunity loss**：对象曾在上游出现，却没有进入最终比较器的可达状态。

### 2.3 旧负相关至少混合五种来源

| 来源 | 是否是真 selector membership 干扰 | 识别方式 |
|---|---:|---|
| 条件分母构成：扩池新增的是更难病例 | 否 | 固定共同暴露病例，或统一 full-pool relation census |
| 同病例 direct capture/context reorder | 是 | E5 式冻结共享候选与 selector，仅操纵 membership |
| frontier/group/cap 造成机会损失 | 不完全 | 区分 registry、actual payload、finalists |
| schema/service attrition | 否，但属部署成本 | ITA 与 common-served 并报 |
| safe/legacy/task projection 误差 | 否 | clinical relation 与 task transition 分列 |

把这五种来源压成一条 width 直线，会把不同可修机制误当成同一个不可突破的容量约束。

---

## 3. 真正成立的负相关证据

### 3.1 E5：候选独立性被病例内实验直接证伪

E5 是目前最干净的 membership 干预：

- 200 个开发病例，base width 4；
- base pool 强制含一个 safe-exact reference；
- 共享候选的文本、ID、相对顺序 byte-stable；
- selector、vignette 与 prompt 固定；
- width 6 是稳定的两个新增候选前缀，width 8 再加两个；
- 新增类型含 parent、sibling、unrelated、synonym、component。

共同服务的 model-panel clinical-complete sensitivity：

| 对比 | n | gain/loss | 净差 | 每新增候选 |
|---|---:|---:|---:|---:|
| width 4→6 | 166 | 6/24 | −10.84pp | −5.42pp |
| width 4→8 | 164 | 5/34 | −17.68pp | −4.42pp |
| width 6→8 | 164 | 6/17 | −6.71pp | −3.35pp |

三点很关键，但必须按 estimand 读取：

1. 损失在共同服务病例中仍存在，说明方向不能全归因 builder/schema failure；common-served 本身仍是 post-treatment survivor sensitivity；
2. 每一步斜率不同，已经不是严格线性；
3. base pool 已暴露 safe-exact reference，消除了这组病例中“新增难例进入分母”的主要构成解释，但没有把面板 complete 变成人类根级结果。

历史 safe-exact 机制分解又显示 width 8 的 33 个 harm 中：

- 23 个是新增候选直接成为冠军；
- 10 个是新增候选没有夺冠，却改变了共享 base candidates 之间的冠军。

第二类是 candidate-set context effect：没有任何共享候选文本变化，选择函数却随集合变化。这里的冻结 safe-exact transition 直接否定 IIA；上表 model-panel complete 只负责临床方向/量级敏感性。

### 3.2 width 只是候选类型与拓扑的代理

E5 common-served 的 typed additions：

| 新增类型 | complete 净差 | C∪P 解释 |
|---|---:|---|
| sibling | **−11.52pp**，Holm `q=.00439` | 高相似、共享证据、直接竞争最危险 |
| parent | −6.63pp | 可把完整对象压成上位泛类 |
| unrelated | −3.01pp | 平均危害较小，仍会产生上下文重排 |
| component | +0.60pp | 近零；且 builder 中大量方向误标，不能视为 oracle component 效应 |
| nominal generated-synonym arm | +4.85pp，Holm `q=.5059` | C∪P **+6.67pp**，`q=.02954`；complete 仅非负点估，C∪P 信号确认 |

typed builder 并非 oracle：20 个抽样 synonym 仅 13 个 fully valid；全部 typed construction 180 个中仅 134 个完全满足请求类型。component winner 中也有大量方向误标。因此，如果“宽度本身”是决定因素，同样增加一个名义候选不应出现如此异质的点估计；但这些 type treatments 尚未正交、保真地识别。候选关系、独有证据、requested-object 层级、安全合并与 comparator context 是**更接近下一轮目标 estimand 的处理属性**，不是本文已经估出的“真正因果量”。

### 3.3 DA 与 MCR 是两种干扰机制

历史 safe-exact 的 width 4→8 分解：

- MCR：20 harm/2 gain，20 个 harm 全是 plausible alternative 直接夺冠；
- DA：13 harm/4 gain，仅 3 个 direct capture，10 个是共享候选重排。

MCR 更像 plausible-alternative direct capture/contextual decision dilution：多个疾病都能解释共享表现，新疾病直接取代 reference。DA 更像 shared-candidate contextual reorder/granularity competition：候选常是 parent/subtype/composite 的多种文字投影，新增内容改变这些版本的相对吸引力。这里不使用规范 Bayesian `posterior dilution`，也不与 E6 的 representation treatment 混名。

同一个 pooled “每候选损失”会掩盖两种完全不同的工程修复：MCR 需要独有 discriminator 与反事实证据；DA 更需要对象因子化、scope binding 和稳定的近邻表示。

### 3.4 E12：盲目填宽的边际召回极低

E12 在 300 例上把历史池从 k=5 扩到 k=10，每例机械增加五个候选，共 1,500 个 exposure，只增加 2 个 safe-exact reference exposure，即每 750 个新增候选才有一个 reference exposure。

与此同时：

- 旧 non-blind root-priority/proxy `clinical-complete*` 中 raw pointwise 65→60，−1.67pp；
- 同一旧 proxy 中 raw pairwise 65→66，+0.33pp；
- S1/graph 近零或负；
- 统一 model-panel 迁移后，k5→10 无 clinical-complete 确认增益。

病例 `DA_d2_heldout200b/540` 是正例：新加入 acute oxalate nephropathy，raw 又保留活检晶体，扩宽有“新对象 + 决定性证据”。`MCR_v1_seq100/74` 是反例：CPVT 已在 k5；加入 Brugada、idiopathic VF、early-repolarization 等 channelopathy siblings 后，被共享特征带走。

这说明边际收益取决于 `新增对象的独有证据产率`，而不是槽位数。

### 3.5 MultiStance 与 APHHM-C：召回增加可被中间状态吐回去

MultiStance 用 coverage/mechanism/commitment 三种取向提高历史 pool recall，却在组内提名和 final selection 丢失：

- registry recall 高，`gold_disc` 低；
- `group_drop` 163 例，近半 finalist 是 near-gold；
- E2 人类根审计中 MultiStance clinical-complete 为 121/800，Collapse3c 为 122/800；21 rescue 对 22 loss。

它不是“召回没用”，而是多取向生成的候选和证据高度相关，先分组后提名让 label variants 内耗，收益没有形成可达、可判别的主比较对象。

APHHM-C 的 Collapse3→Collapse3w 也显示同样张力：宽池补回 legacy recall，MCR conversion 0.652→0.551，Top-1 不升。slot 被通用鉴别和兄弟亚型占用，单位候选的信息增益下降。

### 3.6 B06/E10：压缩召回可以提高幸存候选的排序转化

sequential history 把平均 union 6.82 压到 5.21、两两 Jaccard 0.689 拉到 0.954，Doctor 3 在 400 例只新增 6 个概念。历史 binary-acceptable 暴露下降，但幸存候选的 Top-2 conversion 上升。

统一迁移后 clinical-complete 四个主对比均未通过 Holm，C∪P 则有：

- history×RRF +6.0pp，34 gain/10 loss，`q=.00155`；
- isolated Supervisor +4.25pp，22/5，`q=.00454`。

因此可写的是：在 sequential-history treatment 下，recall compression 与 compatible rank-conversion **共现**，而且收益主要是 compatible soft landing，不是完整对象提升。history 同时改变生成内容、重复、rank propagation 和共识结构，不能把净差隔离归因于“池变小”。顺序 history 是 consensus compressor，不是独立多专家。

---

## 4. 为什么这不是普遍 selector 上限

### 4.1 E4：同池、同宽、同证据表，selector 仍能移动结果

E4 给 400 个病例的五种 selector 完全相同的 source-blind pool、候选 ID/顺序和合并证据表。统一 model-panel ITA clinical-complete：

| Selector | complete |
|---|---:|
| evidence-count | 31/400 = 7.75% |
| e7 | 61/400 = 15.25% |
| ledger | 65/400 = 16.25% |
| Forest | 69/400 = 17.25% |
| pairwise | 69/400 = 17.25% |

Forest 相对 evidence-count +9.5pp，46 gain/8 loss，Holm 显著。Forest 相对 e7 只有 +2pp，Holm `q=.23145`；pairwise 相对 Forest 为 0。

结论不是“Forest 已解决 selector”，而是 **相同 width 并没有唯一 conversion**。病例特异的高特异证据整合能显著移动弱控制线；当前证据尚不能选出一个普遍最佳 comparator。

### 4.2 候选自带证据曾一次移动历史 conversion 16.5pp

APHHM-C 消融中，将共享 ledger fact IDs 改为每候选自带 verbatim support/contradict spans 后，MCR historical conversion 由 0.487 升至 0.652。删掉无人消费的 C4 matrix 后成本还更低。

虽然这是旧 legacy endpoint，不能当 canonical clinical 率，但它定位出一个强机制：**证据是否与候选绑定、是否能形成区分性对比，比 raw width 更接近转化的决定量。**

### 4.3 E9：real-view treatment 可以净受益，但未隔离 capture

真实三视图相对 balanced single：

- model-panel clinical-complete +3.25pp，16/3，Holm `q=.01328`；
- 相对 exact duplicate +3.50pp，17/3，`q=.01031`；
- C∪P +4.0pp，但四重 family 下 `q=.05541`。

real views 不是三张独立票。70 例富集定向审计显示少量 plausible unique-object/decisive-relation capture paths，但不能用这批个案解释全 400 臂的 +3.25/+3.50pp；Top-1 迁移没有把该全臂效应拆成 pool capture 与 shared-exposure selection。与此同时，exact duplicate treatment 有 51/399 个 champion flip，role rotation 有 58/400 个 flip；这些 fresh-call、多 provider 结果是“重复/角色扰动 + 运行路径”的敏感性上界，不是全部可归因于序列化的纯系数。

这组结果同时说明：

- “更宽必然有害”是错的；
- “更多 view 就是更多独立证据”也是错的；
- 下一轮应识别新视图的条件信息增益，以及重复/序列化是否被错误计权；现有 E9 尚未正交分开两者。

### 4.4 CompactForest：historical-chain 的生成几何方向证据

R6 的 X1 交叉换装把 Forest pool 接给 APHHM selector，结果仍贴近 Forest，而不是 Collapse3c，定位优势主要在 generator/pool geometry。

随后低调用移植逐步实现：

- 2-call batched multi-axis `compact_forest_v1`：chain 0.244；
- 3-call KeyFacts→batched axes→selector `v11_facts`：0.258；
- Forest：0.266；Collapse3c：0.211。

`v11_facts` 的 MCR gold-in-pool 从 v1 的 0.343 升到 0.417，同时不靠再拧 selector。这些是 adaptive development、historical-chain 结果；`v11_facts` 与 Forest 的 exclusive 也未过噪声门，不能与 E4/E9 的 canonical model-panel sensitivity 等级并列。它们只提供方向证据：减少重复、用 key facts 锚定多轴生成，可能提高单位候选信息量，值得用 root-owned endpoint 重新检验。

---

## 5. 负相关的五层生成机制

### 5.1 构成层：新增召回通常来自更难的病例

若一个窄臂只暴露“容易且高证据”的 complete objects，宽臂又暴露一批低先验、同胞多、证据欠定的病例，那么：

```text
P(Top1 complete | exposed, wide)
```

可能下降，即使共同病例上的选择完全不变。这是条件分母构成效应。旧 14 臂 OLS 无法区分它与真正的 set interference。

因此任何新的 conversion 曲线都必须至少分报：

- 窄池已 complete-exposed 的共同病例上的 retention；
- 宽池新增 complete capture 的病例；
- 宽池新增但仍 partial/no 的对象；
- common-served 与 ITA。

### 5.2 信息层：新增候选的条件判别信息递减

同一 vignette 上不断调用相似模型，新增内容往往是：

- 首轮候选的同义改写；
- 同一疾病族的 siblings；
- 共享症状可解释的 generic differentials；
- 更流畅但没有候选独有 evidence 的 rationale。

e7 后两次生成首次补入 54 个 strict hits，但只有 12 个进 S3、8 个成 S4 strict champion；能严格归因到 e7-over-v0 最终独赢的只有 2 例。B06 后两位 doctor 几乎复制首轮，三列表平均 Jaccard 0.972。APHHM 完整树中位 26 leaves，但唯一 label 仅 14，重复比例中位 47.2%。

计算增加了 token 和候选数，却没有同比增加对 top competing hypotheses 的互信息。

### 5.3 竞争层：新增候选改变整个上下文能量面

LLM comparator 不是独立地为每个候选打一个固定分数再取最大值。候选 membership 可改变：

- 哪些共享特征被叙述为“最关键”；
- 候选之间的对比基准；
- 对 parent/subtype 的完整性偏好；
- serial-position salience；
- rationale 的故事结构与终止点。

证据等级需要分开：E5 的 shared-candidate context harms 是共享文本/ID/相对顺序冻结后的最强集合因果证据；E9 duplicate/role 的 51/58 flips 是 fresh-call、多 provider 下的扰动敏感性上界；E8 合法 ledger 行重排的约四分之一 flips 是“排序处理 + 当前运行合同”的联合效应。三者共同警告上下文/序列化敏感，但不能都解释成纯位置系数。

### 5.4 状态机层：信息会在末端比较之前不可逆消失

典型不可逆操作包括：

- S1 压缩删掉 decisive anatomy/pathology/time relation；
- k=5 cap 把低排位 rare candidate 截断；
- MultiStance group nomination 先淘汰 gold；
- substring merge 把可独立寻址实体折叠；
- APHHM local champion 与 granularity representative 替换具体对象；
- C4 P4/P5 veto 和 numerical ledger 接管选择；
- graph sanitizer 删证据 ID，却让依赖 candidate 语义 fail-open；
- RCR fixed frontier 让多个 subtype 挤掉 generic core。

末端 selector 只能在剩余状态上优化；上游决定性信息已丢失时，模型仍可能凭 prior 偶中或合成表面答案，但换 prompt 不能系统性、可验证地恢复该信息。

### 5.5 系统与测量层：技术失败和投影可制造伪天花板

- E5 typed arms ITA 全负，部分来自 34–36 个 differential builder/service failures；nominal synonym arm 的 ITA complete 为 −11pp，却在 common-served 变为 complete +4.85pp 点估计（`q=.5059`）和 C∪P +6.67pp（`q=.02954`）。
- E8 invalid-time 的 complete ITA −4.55pp、C∪P −15.45pp；共同服务为 0/−2.4pp 且均不显著，差异几乎全是 service path。
- RCR−Lite C∪P 从 ITA −7.0pp（`q=.03142`）缩到 common-served −0.39pp（`q=1`）；Compact4−Lite 从 ITA −21pp 缩到 −1.72pp（`q=1`）。部署可靠性差是真的，但不是成功轨迹临床质量系数。
- DA mapper 可把 parent/component/manifestation 映到正确 option；E14x 中 18 个 option flip 有 8 个 champion 文本完全相同。

如果不拆这些路径，就会把更复杂 schema 的失败、旧 matcher 的 fragment credit 和真实 candidate interference 加总成一个假的“认知容量”。

---

## 6. 天花板的层级决定因素

### 6.1 审计链，而不是独立概率乘积

对病例 `i`，可按以下层级做归责。它们是审计维度，不全是机械必要条件：L0 是 epistemic validity/effect modifier，不可辨识题仍可能猜中；L1 缺失时模型可凭 prior 偶中；L3/L4 只在 closed-pool selector 下构成必要链；L6 的 service/schema 又贯穿 builder、registry 与 selector，而不是严格发生在 L5 之后。

| 层 | 变量 | 核心问题 |
|---|---|---|
| L0 | `I_i` 可辨识性 | 可见文本是否足以唯一支持 reference 的完整层级？ |
| L1 | `E_i` 源证据存在 | 决定性 span/关系是否真的在输入中？ |
| L2 | `F_i` 表示保真 | 派生状态是否保留且不伪造 polarity/time/scope/relation？ |
| L3 | `G_i` 对象生成与身份 | 是否生成同 requested-object 层级、可独立寻址的 complete candidate？ |
| L4 | `A_i` admission/机会 | 它是否越过 dedup/cap/group/frontier/schema，进入 actual comparator payload？ |
| L5 | `V_i` 条件转换 | 在当前 topology/evidence/order 下，selector 是否选中它？ |
| L6 | `S_i` 执行 | treatment 是否返回可评价 Top-1？ |
| L7 | `P_i` 任务投影 | clinical object 如何被 mapper/judge 映射到 benchmark？ |

这些层不是独立 Bernoulli 变量，不能机械相乘成科学模型；selector 或 mapper 也可能产生表面 rescue。它们是一套 transition ledger/归责坐标：任何完整能力主张都要说明损失首先在哪里出现、深层原因在哪一维、是否被后续投影掩盖。

### 6.2 L0/L1：任务本身的信息充分性

E2 的 800 references 中有 455 个被判为 `unique-full`：DA 285/400（71.25%），MCR 170/400（42.5%）。MCR case 94 的可见病历反复支持 branchial cleft cyst，真正 schwannoma 依赖未展示术后病理或 source title。此类病例的上限来自可用信息，不是 selector。

DA 与 MCR 的不足不同：

- DA 的 unique-full 反而更高，但 complete 仅 2.25–4.25%；其主问题不是普遍 L0 不可辨识，而是病因/并发症/复合 scope 在生成与输出中被压平；
- MCR 病例报告可能把 surprise outcome 放在正文之外，或由 source title 泄漏。

若不先标 visible-evidence sufficiency，就会要求系统“推理”出输入中不存在的信息。

### 6.3 L2：表示保真决定后续可达上限

S1/graph 的问题不是一般性的“短”或“结构化”，而是临床断言被改变：

- MCR 78：删掉肿物起源并沿坐骨神经走行，Schwannoma 虽在池内仍被 Tarlov cyst 压过；
- MCR 74：QTc 380 ms 被同时写成正常与 prolonged；
- May–Thurner：S1 删掉髂总动脉压迫髂静脉，只剩 DVT；
- congenital CMV：病因—时间—系统表现关系被压成结构后果 porencephaly；
- E6 30 个 graph 中 25 个至少有一条关系语义错误。

统一迁移里 E6 graph−raw 的 common-served complete 为 −6pp、`q=.06022`，C∪P 仍 −10pp、`q=.001409`；flat−raw complete 不显著，C∪P 仍 −8.84pp、`q=.0143`。可靠结论是 derived representation 损害兼容覆盖，不是每次成功返回都固定损失多少 complete。

### 6.4 L3：生成 attractor 与对象身份

生成器受首轮锚、显著症状和错误 partition 约束：

- DA case 5 的 APHHM L1 没按决定性组织病理构轴，整棵树在错误子空间重复；
- B06 sequential doctors 读取前人 history，后两位几乎不增加 recall；
- APHHM 的层次树跨 parent 重复同一候选，却未提高独有对象密度；
- 低先验 rare entity 常在候选表末端，容易被 cap 或“更常见”话术删除。

identity 又是另一问题。E7 exact identity 消除 contaminated champion、恢复可寻址节点，并表现为 specificity restoration；但 identity safety 不是生成 complete object 的充分条件。把 parent/subtype 或 component/composite 当 synonym 合并，会把临床对象本身改掉。

统一迁移中 exact−legacy complete 为 +3.25pp（16/3，`q=.00885`），C∪P 为 −0.5pp、`q=1`；它主要把 partial 收紧为 complete，而不是扩大总体兼容 coverage。E7c 又显示方向结构一致率仅 64.82%、重复 label-pair consistency 80.58%；generic nonsemantic graph 也翻转 47 个 champion，其中 15 次两边冠军都不是 graph node。identity safety、relation semantics、graph salience 和运行扰动必须分开。

### 6.5 L4：admission policy 决定“有效宽度”

raw width 不区分：

- 已有候选的真正 synonym；
- 有独有 decisive evidence 的新疾病；
- 只重复共享表现的 sibling；
- 与请求对象不同层级的 manifestation/component；
- 无引用或 schema 不完整的自由生成项。

真正影响前沿的是 **qualified width**：有多少候选同时具有可核验 provenance、同层 requested object、独有 discriminator，并被允许直接竞争冠军。

固定 cap 还有双向风险：

- 太窄会删 rare-but-correct；
- 太宽会让 siblings/泛类稀释证据；
- unsafe dedup 会 overmerge；
- exact split 后若仍固定 frontier，又可能 undercoverage。

因此 identity-safe registry、append-only coverage ledger 与 evidence-qualified main frontier 是当前证据支持度较高、但仍需端到端证伪的候选设计；现有实验尚未证明它们“必须”以该实现分层。

RCR 提供了 admission/state failure 的直接锚点：119 个 exact-span drops 至少 69 个物质性；60 条审计 edges 中 20 条错误/无支持、11 条只是浅共现；3 个 references 在 raw→frontier 丢失；66 个 self-reported `complete` 中仅 9 个 root-complete，38 个是错误实体。自报完整性、长 schema 和 fixed frontier 都不能替代外部 gate。

### 6.6 L5：当前 conditional conversion 的可证伪决定因素

候选池已 complete-exposed 时，selector 面对的是一个病例特异的判别问题。现有实验提示、但尚未用同一个正交设计估计的关键因素包括：

1. top competitors 是否共享大部分证据；
2. 是否存在 candidate-unique decisive evidence；
3. strongest counterevidence 是否同 object、episode、anatomy；
4. evidence weight 是否按特异度而不是次数累加；
5. candidate ordering/serialization 是否稳定；
6. comparator 是否明确保护 complete object，避免退成 compatible parent；
7. 候选是否被错误 type/scope 允许互相取代。

MCR 19 的 Leiomyosarcoma 是正例：低位置先验被 α-SMA/vimentin/desmin IHC 这种高特异 likelihood 推翻。E9 Cryptococcal meningitis 是反例：阳性 cryptococcal antigen 被重复的 mass lesion、低 CD4 和梗死叙事淹没，证据量胜过证据特异度。

### 6.7 L6/L7：系统可靠性与输出投影是独立天花板

复杂 schema 可能提高可解释性，却同时增加 fail-closed、span drop、ID 引用错误与 token 压力。它属于端到端系统能力的一部分，但不应被偷换成成功服务时的 clinical reasoning。

task projection 也会重写结果：E2 中 DA complete 只有 2.25–4.25%，DA task 却为 55.25–63.75%；这不是系统在 mapper 后突然变得临床完整，而是 option bridge 允许 compatible fragments。MCR judge 的 calibration 较好，但仍不是 human root。

---

## 7. 关键病例：表面失败点与深层根因并不相同

| 病例 | 表面第一断点 | 深层决定因素 | 对突破方向的含义 |
|---|---|---|---|
| MCR 78 · Schwannoma | S4 选 Tarlov cyst | S1 丢 nerve-origin 解剖关系；不是 pool miss | 原文 span 必须可回看；恢复 decisive relation 后再比较 |
| MCR 74 · CPVT | 选 long-QT/risperidone；宽池又被 Brugada 挤掉 | 数值/极性反转 + sibling topology | 先做 deterministic numeric/polarity guard，再做 candidate-unique contrast |
| DA 5 · GCRG | 整树未生成 | 首层轴与组织病理不对齐，预算在错误子空间重复 | 生成预算按缺失 modality/discriminator 分配，不按固定 taxonomy |
| MCR 19 · Leiomyosarcoma | e7 shortlist 有 gold 仍未选 | 解剖先验压过高特异 IHC likelihood | 低先验候选若有独有强证据，应获 protected lane |
| DA 241 · endophthalmitis + iris abscess | 粗 representative 取代具体对象 | posterior、identity、granularity 与 mapper 契约断裂 | 核心实体与 modifiers 因子化，禁止任意代表化 |
| DA 299 · Schneiderian papilloma | S4 选近邻 inverted papilloma | near-sibling 竞争 + “更常见/更具体”流畅理由 | 对比必须输出 decisive difference，而不是可事后合理化话术 |
| MCR 94 · Schwannoma surprise | 所有系统偏 branchial cyst | 可见证据不足，reference 依赖未展示病理 | 将 non-identifiable stratum 与诊断能力主分析分开 |
| MCR 346 · rare sarcoma | e7 内部 call 2 带入 exact，打破 B06/B07 锚定 | 异条件生成可提供新对象；但 v0 单调用也已生成并选对 | 只能说明 e7 内部后轮的解锚路径，不能当作 extra-call 相对 v0 的边际胜例 |
| E9 Cryptococcus | real/rotated 转向 toxoplasmosis | 重复非特异证据覆盖阳性特异检测 | evidence weighting 按 likelihood specificity 与反事实区分 |
| MultiStance thyroid/AEI | gold 在 stance 内，未进 finalists | label variants 在组内赛内耗 | 先构造 canonical non-dominated object frontier，再提名 |

这些案例共同说明：记录 `generation_miss/prune_loss/decision_loss` 只找到第一断点；根因可能在更早的 evidence fidelity、candidate topology 或 requested-object contract。

---

## 8. 为什么过去的直觉修复大多没有越过前沿

### 8.1 “再多问几次”没有改变信息集

e7 后两次调用、B06 顺序医生、APHHM 大树和 exact duplicate 都显示：在相同可见证据与相似模型先验下，新增采样高度相关。它能偶尔打破锚定，但平均边际 novelty 很低，且下游会把稀有新增候选删掉。

### 8.2 “保证 gold 在表里”没有修复判别机制

R4 将 gold 强制注入 S3 后，S4 只选中 165/800（20.6%），比原 e7 只多救 9 例。换 S4 variants、重跑 S3、跨臂候选移植也没有稳定越线。

这个旧 20.6% 不是所有 comparator 的固有上限：R5 的新 evidence-grounded selector 在条件集上明显更高，E4 同池也证明 selector 可移动。它说明的是旧 S4 没有把 candidate-specific evidence 转成 margin。

### 8.3 “用确定性规则更可靠”反而放大共享噪声

C4 ledger 的 cell 稀疏、共享 phenotype 大量 veto、score/tie-break 与实际诊断证据不校准；全开 v1 chain 只有 0.113。清 `p5_shared_phenotype` 或全部 veto 只让约 8% 的相关非 top-1 病例 newly top-1，无法救活整体路径。

### 8.4 “删近邻/删共享证据”误删了必要信息

- gold-aware X3 在 DA 探针中曾正，但全 800 无监督 near-merge 使 Collapse3c −3.1pp、MultiStance −1.9pp；
- evidence-consistent X3 对弱池有害、强池近零，oracle 上限约 +1pp；
- span-resolved X2 删除共享 evidence 使 Forest 约 −6pp；
- evidence-count quota/X5 同样有害。

共享事实可以是枢纽证据；近邻也可能是必要鉴别。问题不是“共享”本身，而是缺少 candidate-unique difference 与安全代表选择。

### 8.5 “拆成两轮决赛”没有解除上下文瓶颈

MSplit 将组内提名与决赛隔离，多一次调用反而让 MCR group miss 0.150→0.205。它只否定机械拆分实现，不能证明所有 comparator 被旧 OLS 封顶。

### 8.6 “加 graph/RAG/Call-4”没有获得正确的新证据

- E6/E7c/RCR 的自由生成关系方向、span closure、requested-object gate 不可靠；
- E8 的 9 个 reference hard veto 经根审计无一成立：8 个是过度排除，1 个源于 builder 极性反转；撤销错误 veto 是安全要求，但 soft treatment 的 complete 净益没有确认；
- E11 的 1,950 个所谓 relevant chunks 只有 129 个（6.62%）case-specific，71.64% 无病例适配；relevant−off complete 为 −1.25pp（2/7，`q=1`），C∪P 为 0，generic refine 的显著收益只落在若干 C∪P secondary contrasts，没有 complete 增益；
- E14x 的 Call-4 生成 135 个新实体、全部存活，却没有 safe-exact discovery；全 300 例 Adaptive−Lite 的 model-panel complete +0.33pp、C∪P +1.33pp 均未确认，triggered MCR 的 C∪P 6/0、未校正 `p=.03125` 仅是探索性信号。

E14x 没有主动获取外部证据，只是按 unexplained spans 再生成候选。它否定的是错误 gate，不是否定“针对缺失 discriminator 获取新证据”。

---

## 9. 天花板的四种含义必须分开

### 9.1 信息天花板

reference 或决定性检查结果不在可见输入中。任何静态系统都不能可靠跨越；只能标不可辨识，或进入单独的主动取证任务。

### 9.2 表示/状态天花板

证据原本存在，但压缩、关系图、identity、cap、group nomination 或 veto 将其不可逆删除。突破依赖状态保真和单调性，不是更强末端 prompt。

### 9.3 条件比较天花板

complete object 已在实际 payload，但 candidates 共享证据、对象层级混排、特异 evidence 被计数淹没或 context/order 造成 non-IIA。这里 selector/evidence integration 有真实改进空间。

### 9.4 系统/测量天花板

schema/service 失败、旧 matcher 和 task mapper 限制可观测率。它影响部署效用和论文结论，却不是模型在共同成功轨迹上的认知容量。

把四种 ceiling 统称“诊断能力天花板”会误导工程优先级。

---

## 10. 一个更深的统一解释：状态写入外部性

跨报告最稳定的共同机制，不是“调用数多”或“层次结构坏”，而是 **每一次状态写入都会改变后续可达空间和证据权重**：

1. 摘要写入可能删除/反转事实；
2. 新候选写入可能增加真正 coverage，也可能创建 sibling attractor；
3. identity merge 写入可能消除重复，也可能吞掉 subtype；
4. graph relation 写入可能保留因果，也可能制造伪关系 salience；
5. frontier 写入可能节省上下文，也可能永久删除 rare complete object；
6. history 写入可能传播正确 rank，也可能抹掉 minority hypothesis；
7. mapper 写入可得到 benchmark 正确，却掩盖临床对象不完整。

因此一个状态写入要可靠提高当前前沿，应满足下列条件之一并控制其外部性：取得可核验的新信息，或更可靠地利用已经存在的 decisive evidence；同时还需满足：

- 新增内容不是重复同一命题，既有证据的重整也不能伪装成新事实；
- 保留 source provenance、polarity、time、scope 和 requested-object；
- 不对旧候选作无证据的不可逆删除；
- 对冠军竞争的影响可通过病例内反事实检验；
- 它的 schema/service 成本没有吞掉净收益。

这也是为何“更多 deliberation”常把知识不足转化成更难审计的信息失真。

---

## 11. 当前可写与不可写的科学结论

### 11.1 可以写

1. E5 在冻结共同候选与 selector 的病例内设计中证实 candidate-set interference 和 IIA 违背。
2. flat、untyped、fixed-`k` 填宽会在低增量证据和 sibling-rich pools 中造成真实 conversion harm。
3. harm 同时来自 direct alternative capture 与 shared-candidate context reorder；DA/MCR 机制不同。
4. 旧约 −4.5pp/slot 在 E5 局部 model-panel 共同服务样本中量级复现，但不是通用系数。
5. raw width 只是 candidate topology、unique evidence、对象层级、排列与服务负担的代理。
6. 表示保真、生成几何、admission、requested-object contract、evidence specificity 和 service reliability 共同决定当前前沿。
7. E4/E9 的 model-panel sensitivity 表明 evidence integration 与 real-view treatment 能移动已观察前沿；CompactForest 只提供 historical-chain、适应性开发下的生成几何方向证据。
8. exact/frozen identity、typed requested object、candidate-specific spans、evidence-qualified main frontier、append-only residual ledger 与一次冻结 comparator，是当前证据支持度最高、但仍需 root/placebo/failure gates 证伪的候选结构。

### 11.2 不能写

1. 每多一个候选必降 4.5pp；
2. coverage 与 conversion 在数学上不可兼得；
3. 所有 one-pass selector 已到普遍上限；
4. E5 每个 addition 都内在有害；
5. Forest 或 pairwise 已是普遍最佳 selector；
6. RCR 成功返回时 clinical relation 必然更差；
7. graph、relation、RAG 或主动取证原则上无用；
8. 79 臂 model-panel 是 human-root truth，或可重算旧 14 臂 full-pool clinical conversion；
9. 当前 800 开发病例支持外部部署优越性。

---

## 12. 尚未闭合的关键问题

1. **非 E2 实验的 full-pool clinical exposure 尚未闭合。** E2 已对九臂完整 registries 的 3,103 个 candidate–reference relations 做 exhaustive human-root partition；79 臂迁移只标 Top-1，旧 14 个 APHHM width 臂以及 E4/E5/E9/E12 等非 E2 冻结池仍没有同等级 census。
2. **E5 complete slope 仍是模型面板敏感性。** 需要对共同服务 discordant transitions 做盲法 human-root 复核。
3. **active evidence acquisition 尚未真正测试。** 现有实验增加候选或上下文，没有先声明缺失 discriminator 再获取新证据。
4. **对象因子化未被端到端检验。** 现有 requested-object 多为字段，不是可执行的 core/modifier lattice。
5. **确定性 relation substrate 未通过入场门。** 当前失败的是 LLM 生成的方向/引用实现，非所有关系系统。
6. **外部确认缺失。** 800 例已参与多轮开发，所有结果仍是机制证据。

这些问题决定下一轮不能继续围绕旧斜率微调，而应先改变测量合同与候选状态结构。

---

## 13. 可复核锚点

- 旧拟合与结论修订：[`APHHM_C_PILOT200_REPORT.md` §17–19](../backbone_v1/APHHM_C_PILOT200_REPORT.md)
- e7/B06/B07/APHHM 早期漏斗：[`DEEP_TRAJECTORY_MECHANISM_AUDIT.md`](../backbone_v1/DEEP_TRAJECTORY_MECHANISM_AUDIT.md)
- R1 基线与 R2/R3 漏斗/失败形态：[`CASE_TRAJECTORY_AUDIT.md`](../backbone_v1/CASE_TRAJECTORY_AUDIT.md)、[`CASE_TRAJECTORY_AUDIT_R2.md`](../backbone_v1/CASE_TRAJECTORY_AUDIT_R2.md)、[`CASE_TRAJECTORY_AUDIT_R3.md`](../backbone_v1/CASE_TRAJECTORY_AUDIT_R3.md)
- gold 注入、selector variants、S3/S4 反事实：[`CASE_TRAJECTORY_AUDIT_R4.md`](../backbone_v1/CASE_TRAJECTORY_AUDIT_R4.md)
- 新结构 locus、噪声门与 selector oracle：[`CASE_TRAJECTORY_AUDIT_R5.md`](../backbone_v1/CASE_TRAJECTORY_AUDIT_R5.md)
- X1–X5、MultiStance group drop、CompactForest v1/v1.1：[`CASE_TRAJECTORY_AUDIT_R6.md`](../backbone_v1/CASE_TRAJECTORY_AUDIT_R6.md)
- MOSAIC 历史首轮与五端点纠正：[`MOSAIC_LANDING_TEST_REPORT.md`](../backbone_v1/MOSAIC_LANDING_TEST_REPORT.md)、[`MOSAIC_EXPAND_REPORT.md`](../backbone_v1/MOSAIC_EXPAND_REPORT.md)
- 统一端点与跨实验 transition：[`CROSS_EXPERIMENT_ROOT_CRITICAL_SYNTHESIS.md`](CROSS_EXPERIMENT_ROOT_CRITICAL_SYNTHESIS.md)
- 同池 selector：[`E4_fixed_pool_crossover/REPORT.md`](results/E4_fixed_pool_crossover/REPORT.md)
- membership/width/type：[`E5_candidate_interference/REPORT.md`](results/E5_candidate_interference/REPORT.md)
- representation：[`E6_representation_fidelity/REPORT.md`](results/E6_representation_fidelity/REPORT.md)
- view novelty/repetition：[`E9_view_independence/REPORT.md`](results/E9_view_independence/REPORT.md)
- representation×width×comparator：[`E12_e7_factorial/REPORT.md`](results/E12_e7_factorial/REPORT.md)
- 共同服务病例级对比：[`common_served_paired_contrasts.csv`](results/ALL_ARM_ENDPOINT_MIGRATION/sensitivity/common_served_paired_contrasts.csv)
- E5 width/type 分家族：[`e5_family_split.csv`](results/ALL_ARM_ENDPOINT_MIGRATION/sensitivity/e5_family_split.csv)
- service 路径算术分解：[`service_path_decomposition.csv`](results/ALL_ARM_ENDPOINT_MIGRATION/sensitivity/service_path_decomposition.csv)
- clinical transition 病例 ledger：[`endpoint_transition_case_ledger.csv`](results/ALL_ARM_ENDPOINT_MIGRATION/sensitivity/endpoint_transition_case_ledger.csv)
- panel calibration：[`panel_aggregate_calibration.json`](results/ALL_ARM_ENDPOINT_MIGRATION/sensitivity/panel_aggregate_calibration.json)
- 79 臂 canonical migration 与 sensitivity 总入口：[`ALL_ARM_ENDPOINT_MIGRATION/`](results/ALL_ARM_ENDPOINT_MIGRATION/)

---

## 最终收束

“召回越高、转化越低”在当前系统里并非虚构：当 reference 已经暴露时，新增 sibling/plausible alternatives 确实能夺冠或重排共享候选；E5 给出了最强因果证据。但旧报告把这个真实局部机制升级成固定宽度定律和 selector 范式上限，越过了证据。

更深的决定因素是：**可见信息是否充分，决定性关系是否保真，完整 requested object 是否生成并保持可寻址，候选是否凭独有 discriminator 获得主比较资格，比较器是否按证据特异度而非重复次数形成 margin，以及整个 treatment 是否可靠返回并被正确评测。**

所以真正的突破条件不是“找到一个更强的排序 prompt”，也不是“永远减少候选”。它是让每一次新增计算提高可核验的信息密度，或在信息不足时改变证据集；同时把未获资格的 coverage 与会直接竞争的 frontier 分离，避免用一个平铺列表同时承担“不漏诊”和“必须选一”的互相冲突职责。
