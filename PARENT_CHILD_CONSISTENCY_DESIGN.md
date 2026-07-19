# 父/子分支 rule-out / rule-in 一致性设计(仅设计,不改生产)

> 本文只给出**原则 + 落点**,不含代码改动。落地应放在一个默认 OFF 的开关后,由后续 PR 实施
> (见文末「落地开关」)。评测侧证据见 [`TALP_DISCRIMINATION_CAPABILITY.md`](TALP_DISCRIMINATION_CAPABILITY.md)
> 的 PARENT trap / PARENT lift 结果与数据集 [`data/eval/talp_discrimination_cases.json`](data/eval/talp_discrimination_cases.json)
> 的 `parent_child` 块。

## 1. 问题

树形诊断里,L1 是抽象父家族(如「慢性骨髓增殖性肿瘤」),L2 是其子型/具体叶(如 CML 慢性期 /
加速期 / 急变期)。当证据被标注到叶、再由 `recompute_parent_posteriors` 自底向上聚合到父时,
存在两类**层级不一致**的失误:

- **rule-out 越级(假阴性):** 某个 finding 只与**父家族内某个子型冲突**,却被当作**排除整个父家族**。
  典型:CML **急变期**本就带**大量外周原始细胞**;若把「出现原始细胞」读成「排除 CML(它是慢性
  白血病)」,就会错杀父家族——但原始细胞恰恰是 CML 一个子型的表现。数据集里这就是
  `parent_child_trap`(mb65「many circulating blasts」、mb82「small bowel obstruction pattern」)。
- **rule-in 不上浮(假阴性):** 子型特异的强阳性证据(如低 LAP、Ph 染色体)本应**同时抬升父家族**
  概率,却因只落在叶上、且父被 `_clean_annotation` 强制 neutral,没有把「子确诊 → 父确诊」这层
  逻辑体现出来。

评测证据(llama,9 例):LLM **单独**在这两点上其实做对了(PARENT trap 2/2「不排除父」、
PARENT lift 2/2「子阳性支持父」),说明**问题不在 LLM 判断,而在流水线的聚合与清洗规则**——
父后验完全由子求和得到,任何「越级 rule-out」都是通过错误压低子、再被求和放大的。

## 2. 原则(两条)

**原则 A — 仅在「父子共有的矛盾」上做 rule-out。**
一个 finding 只有在它与**父家族所有子型都矛盾**时,才允许排除父;若它只是与**某一子型**不符
(甚至是另一子型的典型表现),它**至多下调那个子型**,**不得**降低父家族或其它兄弟子型。
即:rule-out 作用域 = 子型局部;要作用到父,必须是 family-common contradiction。

**原则 B — 子的 rule-in 上浮到父。**
子型特异的强阳性证据在抬升该子型的同时,应对父家族给一个**非负**(支持或至少中性)的贡献,
不能因为「证据不直接指向父容器」而在父层被抹平。换言之:`P(parent)` 对「任一子型被强支持」
应单调不减。

> 二者的共同内核:**父家族的概率对「子型内部的此消彼长」应当稳健**——子型之间的重新分配不应
> 无故改变父家族的总质量,除非出现 family-common 的正/负证据。

## 3. 落点(现有代码,均为设计标注,不在本轮改)

1. **`_clean_annotation`(`controller.py` L2389,expanded→neutral 规则在 L2401-2403)。**
   现状:所有 `expanded` 父被强制 `neutral`,父后验纯由子聚合。这条规则是原则 A/B 失效的
   **结构原因**——它把「父级的直接证据效应」一律丢弃,于是既无法在父层拦截「越级 rule-out」,
   也无法承接「子 rule-in 上浮」。
   设计:保留「父不吃直接叶证据」的初衷,但**新增一条 family-common 通道**:当某 finding 被判为
   与**全部活跃子型**同向(全 against → 允许作用于父的 against;全 for → 允许 for),才允许它
   在父层生效;只与部分子型冲突的,维持 neutral(即被限制在子层)。

2. **`_reconcile_annotation_with_kb`(`controller.py` L2676;复用 `_gather_atomic_findings` L2694)。**
   这是把 KB 方向与 LLM 标注对齐的既有钩子。
   设计:在此加入**层级一致性校验**——对每个被标为 `*_against` 的父/子对,查 finding 是
   family-common 还是 child-specific(可用数据集 `parent_child_trap` 同源的规则:该 finding 是否为
   任一兄弟子型的典型表现)。若是 child-specific,则**撤销对父与兄弟子型的 against**,只保留对
   目标子型的效应(原则 A)。反向地,对子型特异的强 `*_for`,补一条对父的非负效应(原则 B)。

3. **`recompute_parent_posteriors`(`controller.py` L3294)。**
   现状:`parent.posterior = sum(child.posterior)`,纯求和。
   设计:聚合**之后**加一个**单调保护**:记录本轮聚合前的 `parent.posterior`,若本轮没有任何
   family-common 证据(仅发生子型间再分配),则父后验对「子型总质量」的下调设下限,避免「压低
   某子型」经求和后错误拖垮父家族(实现原则 A/B 的数值护栏,与 §13b 的判别门控同源思路:
   非判别/仅局部的证据不改变父层)。

## 4. 与已落地判别门控的关系

§13b 的 `enable_discrimination_gate` 冻结的是**非判别证据对叶后验的被动稀释**;本文管的是
**局部(子型内)证据对父家族的越级作用**。两者互补:门控防「共性证据乱动叶」,层级一致性防
「子型证据乱动父」。建议同属一个「后验稳健性」系列,各自独立默认 OFF。

## 5. 落地开关(后续 PR)

- `enable_parent_child_consistency: bool = False`(总开关)。
- 依赖一个「子型 ↔ 典型 finding」判定:优先复用 KB(sibling-set / `get_discriminator_hints` 的
  present-in-child 集合),LLM 兜底(prompt 已验证 2/2 有效),**不得**引入手工策展的父子映射表
  (可扩展性缺陷)。
- A/B:在 `eval_downstream_trace_medbullets.py` 上对 mb65(CML)、mb82(adhesions)验证「原始细胞/
  SBO 不再错杀父家族」,并确认无回归再考虑默认开启。
