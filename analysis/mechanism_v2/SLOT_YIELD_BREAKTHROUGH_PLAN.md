# 槽位产出律突破方案：以已过门 E 机制重构召回—转化前沿

> 取代对象：[`RECALL_CONVERSION_CEILING_BREAKTHROUGH_ROADMAP.md`](RECALL_CONVERSION_CEILING_BREAKTHROUGH_ROADMAP.md) 的 Phase 0–2 优先顺序
> 继承对象：[`RECALL_CONVERSION_CEILING_ROOT_CAUSE_ANALYSIS.md`](RECALL_CONVERSION_CEILING_ROOT_CAUSE_ANALYSIS.md) §11.1 可写清单、[`CROSS_EXPERIMENT_ROOT_CRITICAL_SYNTHESIS.md`](CROSS_EXPERIMENT_ROOT_CRITICAL_SYNTHESIS.md) §8 架构约束
> 新增可复算证据：[`slot_yield_diagnostic.py`](slot_yield_diagnostic.py) → `results/SLOT_YIELD_DIAGNOSTIC/diagnostic.json`
> 端点血缘：C0 三模型面板的**二元** complete 边界（19,599 关系，raw 0.9857 / Gwet AC1 0.9843，已过可靠性门）；model-panel sensitivity，非 human-root
> 推断单位：病例；DA/MCR 严格分族，禁止 pooling

---

## 0. 裁决

旧 ROADMAP 失效不是因为它的方向"不够激进"，而是因为它**建立在一个被数据否证的问题陈述之上**：它假设瓶颈是召回与转化之间的数学权衡，因而把资源投向"表示保真 / 关系基底 / 主动取证"三条重型改造。

本轮在唯一通过可靠性门的端点上做完整漏斗分解后，问题陈述必须改写：

> **召回—转化权衡在使用合格比较器时几乎不存在。DA 每新增一个候选槽位的转化代价是 +0.07pp（即零），MCR 是 −0.74pp（由 E12 同代生成器内部斜率 −0.73pp 独立印证）。真正的天花板是 complete 诊断对象从未被生成：DA 有 226/400（56.50%）病例的参考完全可辨识、已生成 parent/component 候选、但跨全部约 40 个历史臂从未有任何系统写出过完整对象。**

因此下一轮的主攻方向不是排序、不是关系图、不是检索，而是**在已有 partial 候选之上做证据锚定的 modifier 补全（completion-by-append）**，并用已过门的 E 机制（E7b 身份、E9 独立视图、E4 证据整合比较器、E5 类型化准入）构成承载它的底座。

三个实验，按依赖顺序：**M1 组合底座 → M2 补全主攻 → M3 确认**。M0 诊断已完成且离线可复算。

---

## 1. 旧 ROADMAP 为何完全无法 work

不是执行不力，而是三个结构性错误，每一个都已由实际结果证实。

### 1.1 错误一：把不可靠的细标测量放在关键路径最前端

ROADMAP 的 Phase 0 要求先建立 full-pool human-root relation census 作为一切的前置。C0 实际执行结果（`results/CEILING_POOL_CENSUS/REPORT.md`）：

| 检查 | 要求 | 实测 | 结果 |
|---|---:|---:|---|
| A/B complete 二元边界一致率 | ≥0.90 | 0.9857 | 通过 |
| A/B complete 二元边界 AC1 | ≥0.75 | 0.9843 | 通过 |
| A/B 五分类细标一致率 | ≥0.80 | 0.7210 | **失败** |
| overall uncertain 率 | ≤0.05 | 0.0332 | 通过 |

发布规则是合取的，于是**一个细标检查的失败让整个 Phase 0 判为 `NO_GO`，连带阻断 Phase 1/2 的全部路由**。但失败的那一项从来不是主端点需要的东西：`clinical-complete` 只消费二元边界，而二元边界在全部 19,599 个冻结关系上是可靠的。

**这是一次纯粹的合同设计事故，不是科学发现。** 该面板已经交付了一个高质量、可复用、离线的二元真值层，却因为一个不被使用的细分类维度而被整体封存。本方案第一步就是把它解封使用。

### 1.2 错误二：把"因子化"实现为跨候选归并，而归并本身不可靠

C2 要求把诊断表示为 core + modifier 的可执行 lattice，做法是让 LLM 把池内候选映射到共享 core。其科学门失败项（`results/CEILING_CLOSURE/C2_factorization/`）全部集中在**归并操作**上：

| 指标 | 要求 | 实测 |
|---|---:|---:|
| grouped-pair precision | ≥0.95 | 0.897 |
| modifier-axis precision | ≥0.85 | 0.847 |
| 双 reviewer raw agreement | ≥0.90 | 0.818 |
| unresolved rate | ≤0.10 | 0.15 |
| unsafe synonym merges | 0 | **18** |

而同期的人工代理校准（`results/CLAIM_FIRST_MODIFIER_CALIBRATION/REPORT.md`）给出相反方向的结论：**50 例 DA 中 35 例（70%）的全部参考 modifier 都可由 vignette 判定。** 也就是说，*信息是有的，失败的是把多个候选强行归并到同一 core 的那个动作*。

C2 的失败不否证 modifier 表示，只否证 merge-based 因子化。**本方案的 M2 因此改为 append-only 补全：只对单个候选追加一个证据锚定的完整变体，永不归并、永不删除。** 这在结构上绕开了 18 个 unsafe merge 和 grouped-pair precision 这两个致命项——因为它不产生 group，也不产生 pair。

### 1.3 错误三：把服务率门设成与结构性空集不相容

C1 的 qualified frontier 在方向上是成立的：complete 暴露 0.11 → 0.1425（+3.25pp），ITA complete 0.0675 → 0.0775。但它被两件事否决：

- 服务率 0.8725（门槛 0.98）——而 12 例主 frontier 结构性为空使该臂在数学上封顶 0.97；
- 相对 sham 仅 +1.25pp 暴露（门槛 3pp）。

第一项是**门与设计不相容**，不是治疗失败。第二项才是真实的：sham 也拿到 0.13 暴露，说明"资格化"这个动作本身贡献很小。

**可继承的教训**：frontier 资格化不是一个有效杠杆（sham 已经复现其大部分效应），不应再投入。真正有效的杠杆必须能证明它改变了池里**有没有那个完整对象**，而不是改变了候选的排列方式。

---

## 2. 新量化诊断：唯一可靠端点上的完整漏斗分解

以下全部由 `slot_yield_diagnostic.py` 从冻结账本确定性重算，无任何新 provider 调用。口径：`complete = 池内是否存在 complete-equivalent 候选`（暴露）与 `Top-1 是否为 complete-equivalent`（转化），E5 因构造性注入参考而从所有并集中剔除。

### 2.1 漏斗的两个乘数因子

| 家族 | 最佳单臂 complete | 该臂暴露率 | 该臂条件转化率 | 跨全部历史臂并集暴露上限 |
|---|---:|---:|---:|---:|
| DA | 4.25%（MultiStance 17/400） | 6.00% | 70.8% | **16.25%（65/400）** |
| MCR | 26.75%（Collapse3c 107/400） | 38.50% | 69.5% | **52.75%（211/400）** |

两族的限速步骤完全不同，这是旧文档从未分离的关键事实：

- **DA 是暴露受限**：即使转化率提到 100%，最佳单臂也只能到 6%–10.5%。
- **MCR 是双重受限**：211 例曾暴露 complete，最佳单臂只转化 107 例，损失 104 例；同时 400 例中仅 170 例参考可唯一辨识，230 例受 reference identifiability 约束。

并集不是噪声。DA 的 65 例中 36 例被 ≥4 个臂暴露、仅 9 例只被 1 个臂暴露；MCR 的 211 例中 173 例被 ≥4 个臂暴露、仅 15 例单臂。**并集主要是稳定的、被反复复现的生成能力，只是从未在同一个系统里同时出现。**

### 2.2 DA 的真实天花板：完整对象从未被生成

把并集缺口与 E2 的 root-audited reference identifiability 求交：

| DA (n=400) | 曾暴露 complete | **有 partial 但 complete 从未生成** | 两者皆无 |
|---|---:|---:|---:|
| unique_full_reference (285) | 54 | **226** | 5 |
| family_only (78) | 9 | 69 | 0 |
| unsupported_specificity (30) | 2 | 27 | 1 |
| insufficient_information (6) | 0 | 5 | 1 |
| **合计** | **65** | **328** | **7** |

MCR 的同一交集只有 39 例（9.75%）。

**226 例（DA 的 56.50%）构成整个项目中最大的单一可干预缺口**：参考已被根审计确认为可由 vignette 唯一辨识，系统已经生成了正确的 parent/component，但完整对象从未出现在任何池中。抽样查看其缺口形态，全部是有界 modifier：

| 参考 | 已生成的 partial | 缺失轴 |
|---|---|---|
| Isolated cardiac sarcoidosis | Cardiac Sarcoidosis | 范围（isolated） |
| Methimazole-induced vasculitis | Cutaneous Vasculitis | 病因（药物） |
| Nonbullous neutrophilic lupus erythematosus | Systemic lupus erythematosus | 亚型/组织学 |
| Phlegmonous enteritis | Infectious colitis | 部位 + 病理形态 |
| Poncet's Disease with tuberculous lymphadenitis | Tuberculosis | 命名综合征 + 部位 |
| Ureterosciatic hernia with incarceration | Sciatic hernia | 复合对象 + 并发症 |
| Endogenous endophthalmitis with iris abscess | Bacterial endophthalmitis | 途径 + 并发症 |

这与 C2 冻结的六条 modifier 轴完全对齐，也与人工校准的 70% 可判定率一致。

对 Collapse3c 的 211 个 DA `compatible-partial` 冠军，按根审 `scope_detail` 与 `draft_reason` 交叉归类得到缺失类型分布（**派生统计量，非仓库预聚合产物，M2 冻结前需独立复算**）：

| 缺失类型 | 计数 | 占 211 |
|---|---:|---:|
| 欠特异父类（broader_parent） | 75 | 35.5% |
| 病因 / 病原（etiology） | 35 | 16.6% |
| 组成部分 + 复合对象（component + composite） | 28 + 12 | 19.0% |
| 部位（anatomy） | 19 | 9.0% |
| 亚型（subtype） | 11 | 5.2% |
| 并发症（complication） | 9 | 4.3% |
| 时序 / 分期（temporal） | 4 | 1.9% |
| 未归类 | 18 | 8.5% |

M2 的轴优先级由此确定：**父类收紧、病因、组成/复合** 三类合计约 71%，应作为补全提示的主要目标；时序与并发症占比最低，可不进入首轮。

### 2.3 召回—转化权衡在合格比较器下几乎消失

对全部非注入臂做暴露加权最小二乘（转化率 ~ 平均池大小）：

| 家族 | 全部自然臂 | 剔除两个已知弱比较器（事后） | E12 同代生成器内部池梯（k5 vs k10） |
|---|---|---|---|
| DA | 72.0% −1.68pp/候选 (19 臂→21) | **63.9% +0.07pp/候选** | 暴露样本过少，不可估 |
| MCR | 73.2% −1.28pp/候选 (43 臂) | **71.1% −0.74pp/候选** | **71.6% −0.73pp/候选** |

被剔除的两个臂是 E4 的 `evidence_count_control`（DA 转化 23.5%/MCR 31.8%）与 legacy `APHHM-C`（33.3%/37.7%），二者均已被其归属实验判定为弱对照。剔除后 DA 斜率塌到零，MCR 减半。**MCR 的清洁斜率被 E12 内部池梯独立复现（−0.74 vs −0.73），这一项不是事后挑选的产物。DA 的近零斜率仍依赖事后剔除，必须作为待检假设而非既成结论。**

对照 E5 注入臂在同一端点上的 gold-exposed 转化率，可以看清"−4.5pp/候选"从何而来：

| E5 臂 | 池 | DA 转化 | MCR 转化 |
|---|---:|---:|---:|
| remove_non_gold3 | 3 | 74.00% | 86.00% |
| base4 | 4 | 69.00% | 81.00% |
| **add_synonym5** | 5 | **70.79%** | **88.16%** |
| add_component5 | 5 | 68.89% | 80.26% |
| add_unrelated5 | 5 | 67.78% | 71.05% |
| add_parent5 | 5 | 64.44% | 67.11% |
| add_sibling5 | 5 | 60.67% | 63.16% |
| nested_width6 | 6 | 62.22% | 64.47% |
| nested_width8 | 8 | 57.30% | 54.67% |

E5 的陡负斜率来自**故意注入的 sibling 类竞争者且暴露增量恒为零**（参考已在池中）。它测的是"纯竞争成本"，不是"宽度成本"。synonym 注入反而提高转化（MCR +9.21pp），因为它增加表面形式而不增加竞争对象——但该效应在 complete 层未过 Holm（`q=.506`），只在 C∪P 层确认。

类型化效应是强烈 MCR 主导的（common-served, clinical-complete）：synonym DA +1.12pp / MCR +9.21pp；sibling DA −7.87pp / MCR −15.79pp（`q=.0377`）；component DA 0.00pp / MCR +1.32pp；unrelated DA 0.00pp / MCR −6.58pp。这与 E5 报告的机制解读一致——MCR 的宽度伤害以**新增 plausible 疾病直接夺冠**为主，DA 以**共享候选重排**为主。**推论：类型化准入是一条 MCR 杠杆，DA 的收益必须来自暴露侧。这与 §2.1–2.2 的限速步骤分离相互独立地印证。**

### 2.4 本诊断的两项自检

**复现性自检**：本诊断从冻结账本重算 E9 四臂的 clinical-complete，得到 `real_views` 61/400、`single_anchor` 48/400，与 E9 报告 2026-08-13 migration addendum 公布的 61/400（15.25%）与 48/400（12.0%）**逐例完全一致**。同法重算 E4 得 Forest 17.0%、evidence-count 7.75%，与 E4 报告的 17.2%/7.8% 一致。这说明本诊断的 join 与端点口径与各实验的已发布合同相同，不是另一套算法。

**污染陷阱**：`design/known_relations.jsonl` 若不按 `experiment_groups` 剔除 E5，会给出 DA 136 例"曾暴露 complete"。其中 **94 例的 complete 候选只出现在 E5**，即只因该实验把参考**故意注入**池中，属构造性而非生成能力。剔除后该口径为 DA 49 / MCR 186，本诊断的全面板口径为 DA 65 / MCR 211（面板是 known_relations 的超集，另标注了 337 个新 complete 关系）。**任何复用该普查的后续分析都必须先剔除 E5，否则 DA 的暴露头寸会被虚高约 2 倍，并把本方案的主攻方向误导到转化侧。**

---

## 3. 统一定律：槽位边际暴露密度

把 complete 率写成两个因子的积，`complete(p) = E(p) · C(p)`（p = 允许进入主比较的候选槽位数），则净增益条件为

```
dcomplete/dp > 0   ⟺   E'(p) > E(p) · ( −C'(p) / C(p) )
```

即：**每新增一个槽位，必须带来至少 `E × |C'|/C` 的 complete 暴露增益。** 用清洁斜率代入实测工作点：

| 家族 | 工作点 | 需要的边际暴露密度 |
|---|---|---:|
| DA | pool 6.37, E=10.50% | **> −0.01 pp/槽**（任何正增量均净赚） |
| MCR | pool 9.02, E=42.50% | **> 0.49 pp/槽** |

这条定律一次性解释了此前全部过门与未过门的结果，**无需引入任何新机制假设**：

| 机制 | 边际暴露密度（实测） | 定律预测 | 实际结果 |
|---|---:|---|---|
| **E9 单锚 → 三真实视图** | DA 1.26 / MCR 3.14 pp/槽 | 远超阈值，净赚 | complete +3.25pp `q=.01328` ✓ |
| **E7b exact identity** | 不消耗槽位（恢复被折叠的对象） | 密度无穷，最优动作 | complete +3.25pp `q=.00885` ✓ |
| E5 add_synonym | 0（不增对象）但**不增竞争者** | 走 C 通道，非 E 通道 | complete +4.85pp 但 `q=.506` **未过**；C∪P +6.67pp `q=.02954` ✓ |
| 并集 k=1→3 | DA 0.83–0.88 / MCR 3.05–3.38 | 超阈值 | 未测（本方案 M1） |
| 并集 k=4→6 | DA 0.60–0.71 / MCR 1.47–2.56 | DA 超、MCR 超 | 未测 |
| E12 k5→k10 | DA 0.14 / MCR 0.44 pp/槽 | **低于阈值，净损** | Holm39 complete survivor = 0 ✗ |
| E5 add_sibling | **0**（参考已暴露） | 纯竞争成本，必净损 | complete −11.52pp `q=.00439` ✓（确认为负） |
| E5 width 阶梯 | **0** | 同上 | width6 −10.84pp `q=.00286`、width8 −17.68pp `q=7.29e-6` ✓（确认为负） |
| E5 add_parent / unrelated / component | **0** | 竞争成本但量级更小 | complete `q=.246 / .849 / 1.0`，**均未过**（方向性证据） |
| E9 duplicate_anchor | 0（重复非信息） | 无净益 | complete 无净益 ✗ |
| E4 Forest vs evidence-count | 固定池，E 不变 | 走 C 通道 | DA 转化 23.5%→70.6%，complete +9.5pp ✓ |

**没有一个例外。** "每多一个候选降 4.5pp" 从来不是宽度定律，而是"零暴露增量的竞争者注入"的特例；E12 的零结果则是"边际密度低于盈亏平衡点"的特例。

同时定律指出两个从未被利用的最优动作类型：

1. **零槽位成本地提高暴露**（E7b 已证；本方案继续使用）；
2. **单槽位换取某病例从 E=0 到 E=1**——这正是 DA 补全动作的形态，其边际密度为 `56.50 × s pp/槽`（s 为补全成功率）。即使 s=0.10，密度也是 5.65 pp/槽，是 DA 盈亏平衡阈值的 **数百倍**，是本项目测量过的最高密度干预。

---

## 4. 已过门 E 机制的角色重排

不再按"实验编号"拼接赢家，而按定律中的通道分配职责。只列已过 Holm 门或已被根审计确认的机制。

| 通道 | 机制 | 来源与效应量 | 在新架构中的职责 |
|---|---|---|---|
| **E ↑，零槽位成本** | exact / frozen-synonym identity | E7b：complete +3.25pp `q=.00885`；消除 160 个污染冠军 | 唯一允许的合并规则。保证补全变体与其 parent 不被互相折叠 |
| **E ↑，高密度** | 三个真正独立的提案视图 | E9：real−single +3.25pp `q=.01328`；real−duplicate +3.50pp `q=.01031`；暴露 DA 4.0→7.0%、MCR 27.5→35.0%，池仅 2.86→5.25 | 基础提案层。视图必须语义独立（cluster 比 0.552），role rotation 与重复均无效 |
| **E ↑，最高密度（新）** | evidence-anchored completion-by-append | 未测；密度 56.50×s pp/槽（DA） | M2 主攻。只追加、不归并、不删除 |
| **C ↑，固定池** | 证据整合式比较器 | E4：Forest 相对 evidence-count DA 转化 23.5%→70.6%、complete +9.5pp | 唯一比较器。必须输出候选独有判别证据与反事实缺失项 |
| **C ↑，表示保真** | raw 原文 + pairwise 对比 | E12：MCR raw_k10_pairwise 转化 77.6%（同池 s1 版本 61.2%）；raw pairwise−first C∪P k10 +12.33pp `q=.000175` | 比较器输入必须是可回看的 raw span，禁止 S1/graph 作唯一事实源 |
| **C 保护，类型化准入** | **拒 sibling 类**（唯一在 complete 层确认的准入规则） | E5：sibling complete −11.52pp `q=.00439`；synonym 仅 C∪P +6.67pp `q=.02954`（complete `q=.506` 未过）；parent/unrelated/component 均未过 | 准入规则。sibling 类候选进 residual ledger 不进主比较。**"许 synonym"只有 C∪P 级证据，不得作为 complete 级主张** |
| **安全硬约束** | 禁绝对 veto、禁无门控 RAG、禁 self-reported completeness | E8 9/9 hard veto 根审无一成立；E11 relevant chunk 仅 6.62% case-specific；RCR-3 self-complete 66 例仅 9 例为真 | 全程禁用，不作为臂 |

已被证否、明确不再投入的：merge-based 因子化（C2）、frontier 资格化（C1，sham 已复现）、自由生成方向图（E7c 方向一致率 64.82%）、当前 unexplained-span Call-4 gate（E14x）、sequential history 共识压缩（E10 只改 C∪P 软着陆）。

---

## 5. 突破方案

### 5.0 M0 — 离线诊断（已完成）

产物：`slot_yield_diagnostic.py` + `results/SLOT_YIELD_DIAGNOSTIC/diagnostic.json`。零 provider 调用，从冻结账本确定性重算。它把 C0 的二元真值层从"整体封存"状态解封为可用测量基座，并给出上文全部系数。

**这一步已经改变了问题陈述，且不消耗任何预算。**

### 5.1 M1 — 组合底座（Track A）

**问题**：并集暴露（DA 16.25%、MCR 52.75%）与最佳条件转化（DA ~71%、MCR raw+pairwise 77.6%）从未在同一个臂里出现。

**处理**：单一系统，四调用预算：

```
raw vignette ──┬─ 提案视图 1（综合征/表现层）
               ├─ 提案视图 2（机制/病因层）      ← E9：三个语义独立视图
               └─ 提案视图 3（模态/病理层）
                      │
                      ├─ exact / frozen-synonym registry（E7b，确定性，零调用）
                      ├─ 类型化准入：synonym 类合并入同一对象；sibling 类
                      │   进 residual coverage ledger，不进主比较（E5）
                      │
                      └─ 主 frontier（不固定 k，目标池 8–11 槽）
                                 │
                      Call 4：raw-span pairwise 证据整合比较器（E4 + E12）
                                 │
                                 └─ Top-1 + 候选独有判别证据 + 反事实缺失项
```

**四个臂**（同 800 例，冻结前定义，outcome-blind）：

| 臂 | 提案层 | 准入 | 比较器 | 作用 |
|---|---|---|---|---|
| `A0_control` | 单视图 | 无类型 | 冻结 Lite comparator | 对照（复现最佳单臂） |
| `A1_views` | 三独立视图 | exact identity | 同上 | 隔离 E9 通道 |
| `A2_views_typed` | 三独立视图 | + 类型化准入 | 同上 | 隔离 E5 准入通道 |
| `A3_full` | 三独立视图 | + 类型化准入 | raw-span pairwise 证据整合 | 全组合 |

**预期**（用清洁斜率与实测边际密度外推，作为预注册的方向性预期，不是承诺）：

| 家族 | A0 | A3 暴露 | A3 转化 | A3 complete |
|---|---:|---:|---:|---:|
| DA | 4.25% | ~10.7%（k≈5 等效，池 11.4） | ~64–72% | **6.9%–7.7%** |
| MCR | 26.75% | ~41.6%（池 9.9） | ~63–78% | **26.2%–32.4%** |

DA 预期净增 +2.7pp（1.6×），MCR 区间跨越零，其上界依赖能否把 E12 的高转化水平（77.6%）搬到高暴露池上——**这正是 M1 要检验而非假定的东西**。

**联合缺口已独立确认**：仓库内不存在任何把这些机制组合起来的已运行臂。E7b 三臂只改 registry 身份策略（且其 pool 始终来自 syndrome/mechanism/modality **加 adaptive a1** 四路 occurrence）；E9 四臂只改视图结构（且其 registry **始终**用 exact bridge，从未测 legacy）；E4 五臂只改 selector（同一冻结池）；E5 九臂只改 membership。"只许 synonym、拒 sibling"的类型化准入从未作为臂运行——C1 的 `typed_fixed_k` 用的是 requested-object ↔ candidate-kind 严格相等，不是 sibling/synonym 关系过滤。旧 ROADMAP 的 Phase 1-C（membership × evidence binding × comparator 联合因子）至今为待做项。

因此 M1 的最小可识别形式可以进一步收窄为一个在 E4 已冻结的同 400 例上的 **2×2：{legacy, exact} × {single_anchor, real_views}**，用以闭合 red-team 指出的"两个各自过门的机制从未联合检验"缺口；四臂完整版本则在其上再叠加准入与比较器。

### 5.2 M2 — completion-by-append（Track B，DA 主攻）

**问题**：DA 有 226 例参考可唯一辨识、partial 已生成、完整对象从未被写出。

**处理**：在 M1 的 registry 之后插入一个**只追加**的补全步骤。对每个已进入主 frontier 的候选，沿六条冻结 modifier 轴（病因/病原、部位、亚型或组织学、并发症、范围或分布、时序或演变）提问：vignette 中是否存在支持某个该候选标签未表达的 modifier 的**逐字 span**？

硬约束（每一条都对应一个已知失败模式）：

- **只追加**：原候选必须保留在池中。补全变体与原候选并存，构成 parent/child 对。
- **永不归并**：不做跨候选 core 归并，不产生 group、不产生 pair。这在结构上消除 C2 的 18 个 unsafe merge 与 grouped-pair precision 门。
- **逐字锚定**：每个 modifier 必须携带 vignette 中逐字出现的 support span，offset 由确定性恢复而非模型算术（沿用 C2 已修好的 `_normalize_quotation` 路径）。无 span 者不得生成。
- **不得引入未观察到的患者事实**：补全只能重述 vignette 已有内容，不得推断检查结果或病史。
- **每候选至多一个补全变体**，槽位增量因此上界为 +1 池宽。

**为什么这次可能成立，而 C2 不成立**：

| C2 失败项 | M2 是否触发 |
|---|---|
| grouped-pair precision 0.897 | 不产生 group ⇒ 不适用 |
| unsafe synonym merges 18 | 不归并 ⇒ 结构上为 0 |
| unresolved rate 0.15 | 无需解析 core 归属 ⇒ 不适用 |
| modifier-axis precision 0.847 | **仍适用**，是 M2 的主要风险，须设入场门 |

**入场门（看不到任何 complete outcome 之前必须通过）**：

- modifier span 逐字闭合率 = 1.00（无 span 即拒绝生成）；
- 双 reviewer 对"该 modifier 是否被 vignette 支持"的二元一致率 ≥0.85、AC1 ≥0.70（**只用二元判断，绝不用五分类细标——这是从 C0 学到的教训**）；
- 幻觉率：补全 modifier 中被判为无支持的比例 ≤0.10；
- 服务率 ≥0.95（门槛按结构可达性设定，不再设成与设计不相容的 0.98）。

**预期产出**（`complete ≈ (6.00% + 56.50% × s) × C`，C≈64.5%）：

| 补全成功率 s | DA 暴露 | DA complete | 相对 4.25% |
|---:|---:|---:|---:|
| 0.10 | 11.7% | **7.5%** | 1.8× |
| 0.20 | 17.3% | **11.2%** | 2.6× |
| 0.30 | 23.0% | **14.8%** | 3.5× |

**下行风险已由 E5 定量界定**：补全变体与其 parent 并存构成 parent/child 竞争，E5 的 `add_parent5` 正是这个构型的经验校准——在参考与其 parent 同池时，完整对象仍以 DA 64.44% / MCR 67.11% 胜出。因此最坏情形不是崩溃，而是转化率退到 ~64%，这已计入上表。若补全 modifier 错误，损失表现为 catastrophic substitution，必须以 C∪P 作为强制并报的次要端点捕捉。

MCR 只有 39 例可寻址（9.75%），M2 对 MCR 按预注册**仅作次要分析**，不作主张。

### 5.3 可复用基础设施

M1/M2 不需要新建执行框架。已核对可直接复用的组件：

| 层 | 复用对象 | 位置 |
|---|---|---|
| 执行骨架 | `prepare-only → --arm X → --finalize` 三段式，含 freeze fail-closed 比对 | `e5_candidate_interference.py`（`freeze_preregistration` L674–724）或 `e4_fixed_pool_crossover.py`（L580–629） |
| LLM 调用 | `OnlineJSONCaller`：target-blind 断言、磁盘缓存、并发单飞、telemetry | `online_runner.py` L103–150 |
| 运行契约 | `RunManifest`、`atomic_json`、`validate_workers`（非 RAG ≤50） | `runtime_contract.py` L22–102 |
| 身份合并 | `FrozenExactSynonymBridge`（exact + 冻结 synonym，禁 substring/fuzzy） | `common.py` L157–244，桥数据 `data/knowledge_raw/disease_name_bridge.json`（27,371 alias / 26,583 canonical） |
| 提案视图 | Forest 三轴 prompt 与 `MosaicPipeline` | `prompts/mosaic_axis_{syndrome,mechanism,modality}.txt`；`mosaic.py` L258+ |
| 比较器 | Forest 证据整合 prompt（独立整合四类证据、折扣相关复述、保留高特异低先验、输出 decisive_items） | `e4_fixed_pool_crossover.py` `ARM_FOREST` L99–107 |
| 逐字 span 规范化 | `_normalize_quotation`（C2 已修好，确定性恢复 offset） | `ceiling_closure_online.py` |
| 统计 | `paired_contrast` + `holm_adjust` + `bootstrap_mean`（ITA 为主、common-served 标注为敏感性） | `e5_analysis.py` L113–287 |
| 冻结样本 | E4 400 例同池（DA200+MCR200）；E5 base4 1,800 条件行 | `E4_JOINED_RESULTS.tar.gz` + `canonical_pools.jsonl`；`E5_JOINED_RESULTS.tar.gz` |

模型与运行参数沿用各 selector 实验的冻结值：selector `deepseek/deepseek-v4-flash-0731`，标注/补全 `google/gemini-2.5-flash`，入场门双 reviewer `anthropic/claude-sonnet-4.6` + `openai/gpt-5.6-sol`，temperature 0，workers ≤50。

### 5.4 M3 — 确认

M1/M2 均在同一 800 例开发集上运行，全部结论仍为机制证据。M3 只在 M1+M2 架构冻结后启动，且必须是新队列。当前用户已明确排除扩容确认集，故 M3 保持"已定义、未排期"状态，不得以开发集结果冒充部署优越性。

---

## 6. 预注册契约

### 6.1 端点

- **主端点**：`clinical-complete`，判定为 C0 三模型面板的**二元** complete 边界（对新产生的候选按同一冻结 rubric 与同一三模型面板扩展标注）。血缘标为 `model_panel_sensitivity`，**不得称 human-root**。
- **强制并报次要端点**：`complete-or-compatible-partial`（C∪P）、暴露率、条件转化率、服务率、平均主 frontier 池宽、每病例调用数与 token。
- **禁止**：把 DA option mapper 的 `task` 与 MCR calibrated judge 的 `task` 合并；把 `legacy-chain` 当准确率；读 selector 自报 completeness。

### 6.2 统计

- 分族相干家族内 Holm 校正；**DA 与 MCR 永不 pooling**；
- 主推断为病例级配对精确 McNemar；ITA（全 intended 分母）为主，共同服务为标注过的敏感性；
- 每个 complete 净差必须闭合到四类转移（specificity rescue / object rescue / scope compression / catastrophic substitution），净差不得只报代数和。

### 6.3 盲法与冻结

- 所有 prompt、阈值、准入规则、modifier 轴在看到任何 arm outcome 前冻结；
- 补全步骤不得访问参考、选项或任何 outcome 字段；
- 失败 fail-closed 为显式失败，不删除、不插补。

### 6.4 功效

按配对 McNemar 精确检验，n=400/族：

| 对比 | 基线 | 目标 | 预期不一致对 | 双侧精确 p |
|---|---:|---:|---|---:|
| M1 A3 vs A0（DA） | 17/400 | 28/400 | 13 / 2 | ≈0.0074 |
| M1 A3 vs A0（MCR） | 107/400 | 128/400 | 35 / 14 | ≈0.003 |
| M2 vs M1 A3（DA, s=0.10） | 28/400 | 30/400 | 至少 11 / 2 | ≈0.027 |
| M2 vs M1 A3（DA, s=0.20） | 28/400 | 45/400 | 至少 19 / 2 | <0.001 |

DA 的检出力实际上优于 MCR：基线极低且补全带来的增益近乎单向（新暴露病例此前不可能为 complete）。**MCR 的 +5pp 目标处于检出边界，若 M1 的 MCR 效应落在区间下半，应按预注册报为未确认，不得靠 pooling 或换端点抢救。**

---

## 7. 失败条件与不可写边界

### 7.1 各步骤的证否条件

- **M1 失败**：若 `A1_views` 相对 `A0` 的暴露增益不复现（E9 在新实现下失效），或 `A3` 的池宽增长带来的转化损失超过清洁斜率预测两倍（说明 DA 近零斜率是事后剔除的产物），则槽位定律的 DA 分支被证否，须退回单视图窄池。
- **M2 失败**：若 modifier 幻觉率 >0.10，或双 reviewer 二元一致率 <0.85，则补全工具不可靠，按 C2 先例封为入场门失败，**不得执行下游 complete 对比**。
- **M2 成立但无收益**：若补全成功率 s<0.05，则 226 例缺口在当前模型能力下不可达，DA 天花板确认为 ~16% 生成上限，此时唯一剩余路径是主动取证（ROADMAP 的 A1/A2 轨），而非再改表示。

### 7.2 不能写

- 不能写"召回与转化无权衡"：MCR 的 −0.74pp/候选 已被两个独立口径确认为真；成立的只是"DA 分支近零，且两族的斜率都远小于 E5 注入臂的 −4.5pp"。
- 不能写 DA 近零斜率已确认：它依赖事后剔除两个弱比较器，必须由 M1 内部的池宽梯度前瞻验证。
- 不能写这些数字是 human-root 真值：它们是 C0 三模型面板的二元边界，其中 2,601 个关系复用 E2 root、217 个由 frozen safe-exact 确定，其余为模型面板多数。面板对隐藏 E2 sentinel 的细标准确率仅 70.93%。
- 不能写并集暴露上限（DA 16.25% / MCR 52.75%）是模型能力上限：它是**已运行过的这些臂**的能力并集，既非理论上限也非可保证达到的目标。
- 不能写 800 例结果支持部署：全部 800 例已参与多轮开发。
- 不能在未剔除 E5 的情况下引用任何池普查暴露数字：DA 会被虚高约 2 倍（136 vs 65），并把主攻方向误导到转化侧（见 §2.4）。
- 不能把"许 synonym"写成 complete 级确认机制：它的 complete 效应 `q=.506`。在 complete 层唯一确认的准入结论是"拒 sibling"。
- 不能把 226 例全部当作可补全：其中存在极长复合参考（如"AMI due to critical stenosis of proximal LAD, presenting with de Winter pattern evolving to Wellens syndrome"）。M2 必须按**缺失 modifier 轴数**分层预注册，主张只落在 1–2 轴层，≥3 轴层作探索性报告。

### 7.3 一个必须承认的测量张力

抽样中出现 `ELANE-associated severe congenital neutropenia with hepatic involvement` 被判为 partial、而参考为 `SCN with hepatic abscess caused by Staphylococcus aureus` 这类窄间隙。二元边界的一致率虽为 0.9857，但部分 226 例的缺口可能靠**命名纪律**而非新推理即可跨过。这既是 M2 的机会（成本更低），也是解释风险（收益可能部分来自表述而非诊断能力）。M2 必须对每个新 complete 病例记录"补全轴 + 支持 span"，使收益可被逐例归因到具体 modifier，而不是笼统归功于补全模块。

---

## 7.4 执行结果指针

M1/M2 已在 800 例五臂上执行完毕，结果见
[`results/SLOT_YIELD_BREAKTHROUGH/REPORT.md`](results/SLOT_YIELD_BREAKTHROUGH/REPORT.md)。
三项与本计划预期不一致、需要在后续引用时以实测替代预期的点：

- **M1 未失败**：DA C∪P 暴露 +13.75pp、官方 Acc@4 +6.00pp（Holm q=.0184），暴露增益复现。
- **M2 入场门失败**：modifier 幻觉率 0.1112 > 0.10，B1 的 complete 对比按 §7 规则扣留。
  失败按 axis 强分层（表面型 0.0587、推断型 0.1862），故 M2 应判为受限工具而非失效工具。
- **§7.3 的测量张力被部分证实但未主导**：DA 净增益 22 例中 17 例来自 modifier 全部获双
  reviewer 支持的补全，4 例来自含未获支持 modifier 的补全。最严苛重新归因下效应跌出显著。

另外，本计划关于「候选槽位几乎免费」的表述需按实测收窄：槽位成本取决于**槽位类型**。
DA 上横向槽位的 complete 边际产出为 0.87pp/槽，纵向补全槽位为 3.59pp/槽。

---

## 8. 与既有文档的关系

| 文档 | 处置 |
|---|---|
| `RECALL_CONVERSION_CEILING_ROOT_CAUSE_ANALYSIS.md` | 保留。§11.1 可写清单与§12 开放问题仍有效；其"每候选 −4.5pp 非普遍定律"的判断被本方案量化确认并给出具体系数 |
| `RECALL_CONVERSION_CEILING_BREAKTHROUGH_ROADMAP.md` | Phase 0–2 优先顺序被取代。其主动取证轨（A1/A2）定义保留为 M2 失败后的唯一剩余路径 |
| `CEILING_CLOSURE_PREREGISTRATION.md` | C0 的二元产物解封复用；C1/C2/C4 判定保留为已证否记录；C3/C5 未启动 |
| `CROSS_EXPERIMENT_ROOT_CRITICAL_SYNTHESIS.md` | §8 架构约束全部继承，无一条被本方案放松 |
| `results/CEILING_POOL_CENSUS/` | 从 `NO_GO`（细标）改为**二元边界可用**；`clinical_width_outputs_released` 仍为 false，本方案不发布任何 width 系数作为结论，只作设计外推 |

---

## 最终收束

旧路线的失败可以用一句话概括：**它去修一个不是瓶颈的东西，同时用一个不需要的测量维度把自己锁死。**

新的问题陈述是可证伪且已被量化的：在合格比较器下，候选槽位几乎是免费的（DA +0.07pp/槽，MCR −0.74pp/槽），因此系统的 complete 率几乎线性地由"完整诊断对象有没有出现在池里"决定。而 DA 的 226 例告诉我们，它大多数时候没有出现——不是因为信息不在 vignette 里（70% 可判定），不是因为核心实体没找到（partial 已生成），而是因为**没有任何一步的职责是把已找到的核心补全成被要求的那个对象**。

M2 就是补上这一步，并且是以已证明安全的方式补（只追加、逐字锚定、永不归并）。它的边际暴露密度比本项目测量过的任何干预都高两个数量级以上，这是它值得优先于一切排序、关系与检索改造的唯一理由。
