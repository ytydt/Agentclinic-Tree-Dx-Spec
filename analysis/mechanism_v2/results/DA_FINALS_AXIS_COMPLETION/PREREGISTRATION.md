# 预注册 v2：DA 受限轴纵向补全（冠军级，clinical-complete 端点）

实验 ID：`DA_CHAMPION_AXIS_COMPLETION_V2`
日期：2026-08-20
性质：**确证试验。G0 已解除。**

上游依据：[`CLINICAL_RESCORE/REPORT.md`](../CLINICAL_RESCORE/REPORT.md) §2/§3/§4。
仪器：`analysis/mechanism_v2/clinical_endpoint.py`。

## 0. v1 → v2 改了什么，以及为什么

v1 有一条前置阻断门 G0（"在存在 clinical-complete 端点评分器之前不得执行"）。
**G0 基于一个事实错误：那台评分器早已存在。** 临床判定按 `(case_key, canonical_label)`
存在两个冻结源里、与臂无关，实测覆盖 MultiStance 冠军 800/800、池内标签 100%，零调用。
**G0 就此解除。**

换上真尺子后设计有三处实质变化：

| | v1（legacy-chain 下推得） | v2（clinical-complete 下实测） |
|---|---|---|
| 靶的定义 | `final_drop` 中"父类 finalist 尚未记分"= **2/72** | `partial_champion` = **210/400（dev-400）**；本实验队列 holdout-200 上为 107/200，契约内 14（§1） |
| 补全对象 | 每个 finalist（2–4 个）+ 重裁 | **冠军本身，不重裁**（见下） |
| 对照臂 | 4 臂（含 `readjudicate_only`） | **3 臂**，预算减 40% |

**为什么不再动 finalists、不再重裁：** 210 例 partial 冠军里 **207 例池内不存在任何临床完整的
标签**（`CLINICAL_RESCORE` §4）。既然没有更好的席位可选，"补全 finalists 再重裁"里的重裁一步
无事可做，纯属噪声与成本。DA 的选择层在真端点上总共只值 7 例。所以 v2 是**单点纵向补全**：
对冠军补一次，直接替换，不引入任何新的比较。这同时消掉了 v1 的 `readjudicate_only` 对照。

## 1. 队列（冻结后不得改）

- 切片：**DA `d2_heldout200b_v1` 200 例**。v1 里的 MCR 200 例**移出本实验**——MCR 的补全梯
  只有 8–10 例，而它的真问题是选择层 63 例（`CLINICAL_RESCORE` §5），归属另一份预注册。
- 入选：规范化 vignette、gold、非空冻结 MultiStance registry、冠军非空。
  **入选不看冠军对错，也不看冠军的临床关系**（否则用到了端点信息）。
- 冻结基线：`logs/backbone_v1/diagnosisarena_heldout200b/aphhm_c_multistance_v1`。
- gold 与临床判定仅在 analyze 阶段使用。

靶规模在**目标切片上直接实测**（非外推，零调用）：

| DA `d2_heldout200b`（n=200） | 例数 | 被谁挡住 |
|---|---:|---|
| `frozen` 基线 clinical-complete | **6（0.030）** | — |
| 实际发起补全调用 | **200** | 无：§1 入选不看冠军的临床关系 |
| `partial_champion`（补全可能有用） | **107** | 给 `not_equivalent` / `conflicting` 的冠军加修饰词，核心错的仍错 |
| ⤷ 冠军是参照的真词法子集 | 46 | 61 例须替换中心词，append-only 到不了 |
| ⤷ 且加词属表层轴 | 19 | **27 例被 §3 轴契约挡掉** |
| ⤷ 且加词 ≤ 2 个 | **14** | 5 例触发 `over_specified` |

两个 dev 切片的同一阶梯为 51/16/9（`d2_seq100`）与 52/10/7（`d2_heldout100`），
比率一致，说明 holdout 切片不是异常样本。

### 1.1 这 14 例是什么、不是什么

**它不是"可寻址上界"，也不是下界。** 它是"字符串重构代理量在最严一档上的计数"，两侧偏差方向相反：

- **偏窄**：端点 `complete_equivalent` 是面板对"候选 vs 参照"的关系判定，**不要求复现参照字符串**。
  补出 `Neuro Behçet's disease` 与参照 `Neuro-Behçet Disease` 不同串，但面板极可能判 complete。
  阶梯用 `token_subset(champion, reference)` 是比端点更严的条件，因此漏掉这一类。
- **偏宽**：模型必须真的补对那个修饰词（运行时看不到参照，可能补一个别的表层轴词），
  面板还必须同意（五分类准确率 0.7082）。

因此 §7 的预测按"14 例乘以兑现率"给出区间，但**不得把 14 写成硬上界**：非参照串的补全若被判
complete，会落在这 14 例之外。

**≤2 词这条线对分词敏感，不是稳健边界。** 换一套更宽的归一化（去撇号、连字符、变音符、复数）
重算，这一档从 14 变为 10。因此它只用于给出预期规模，**门槛判定不依赖它**——§6 用的是配对
McNemar，而 `over_specified` 是运行时按冻结 `content_tokens` 机械执行的契约门。

### 1.2 两道门各自收窄了多少：必须看联合分布

46 例可重构标签在 §3 的两道门（仅表层轴、加词 ≤2）上的 2×2：

| | 加词 ≤2 | 不限词数 |
|---|---:|---:|
| **仅表层轴** | **14（当前契约）** | 19 |
| 不限轴 | 20 | 46 |

所以**单独放开任一道门收益都很小**：只放开轴限制 14 → 20（+6），只放开词数上限 14 → 19（+5），
两个都放开才 14 → 46。原因是被轴挡掉的 27 例里有 21 例**同时**超过 2 词——推断轴的补全往往
是长短语，两道门高度共线：

```
Hepatitis C Virus Infection → Acute-on-chronic liver failure due to acute hepatitis  [complication, temporal] 4 词
Atrial Tachycardia w/ Cardiomyopathy → Arrhythmia-induced cardiomyopathy due to ...  [etiology] 4 词
Systemic Sclerosis → Overlap syndrome involving diffuse systemic sclerosis and ...   [scope_distribution] 6 词
Hemophagocytic lymphohistiocytosis → Catastrophic Adult-onset Still Disease ...      [etiology] 9 词
Catatonia → Catatonia related to underlying Lewy body dementia                       [etiology] 5 词
```

```
Hepatitis C Virus Infection → Acute-on-chronic liver failure due to acute hepatitis  [complication, temporal_evolution]
Atrial Tachycardia w/ Cardiomyopathy → Arrhythmia-induced cardiomyopathy due to ...  [etiology]
Systemic Sclerosis → Overlap syndrome involving diffuse systemic sclerosis and ...   [scope_distribution]
Catatonia → Catatonia related to underlying Lewy body dementia                       [etiology]
```

这正是 SLOT_YIELD 实测幻觉率 **0.1862** 的地带（表层轴 0.0587）。**这是有意的取舍，不是疏漏。**
要把靶从 14 显著扩大必须**同时**放开两道门（→46），即让模型生成多词的推断性短语，
而 §6 的硬门是幻觉率 ≤ 0.10——两者不可兼得。若要检验这条取舍，必须另开一臂并**单独预注册**，
不得在本臂内放开。

## 2. 装置（冻结）

- MultiStance registry、stance 分组、tournament、冠军选择**全部冻结**，逐例配对。
- 补全对象：**冠军单一标签**。每例 **1 次**补全调用。**无重裁调用。**
- 补全模型 `google/gemini-2.5-flash`；不引入任何新比较器。
- 并发 25，temperature 0。

## 3. 受限轴契约（沿用 v1，未改）

只允许三条表层轴（SLOT_YIELD M2 实测幻觉率 0.0587）：
`anatomy`、`subtype_histology`、`composite_component`。

**禁止**四条推断轴（同实验 0.1862）：`etiology`、`temporal_evolution`、`complication`、
`scope_distribution`。命中推断轴词表即整条丢弃并记 `axis_violation`。

- `support_span` 必须是 vignette 的**逐字子串**，否则丢弃。
- **append-only**：只能在原冠军标签上加修饰词，不得替换中心词、不得改词序。违反记 `not_append_only`。
- 最多加 **2** 个内容词（§4 阶梯的 ≤2 档）；超过记 `over_specified` 并保留原标签。
- **极性拒绝**：vignette 中存在与该修饰词矛盾的逐字 span 时必须拒绝；矛盾 span 由补全调用给出，
  analyze 阶段核验其为逐字子串。
- 在线 payload 禁止 gold / options / 任何端点信息。

§4 的靶例正是这三条轴的形态：`Histoplasmosis → Primary oral histoplasmosis`（anatomy）、
`Angiosarcoma → Cutaneous angiosarcoma`（anatomy）、`Amyloidosis → Bullous amyloidosis`
（subtype_histology）、`Giant Cell Tumor → Giant cell tumor of soft tissue`（anatomy）。

## 4. 四臂

| 臂 | 说明 | 契约 | 严格口径靶 | 新标签数 |
|---|---|---|---:|---:|
| `frozen` | 冻结 MultiStance 冠军。**配对基线** | — | 6（基线） | 0（100% 复用冻结面板） |
| `complete` | 受限轴 append-only 补全冠军 | §3（表层轴 & ≤2 词） | 14 | ≤200 |
| `placebo_corrupt` | 把 `complete` 实际产出的修饰词换成**同轴、逐字出现在 vignette、但语义上属于另一处解剖/亚型**的修饰词 | 同 `complete` | — | ≤200 |
| **`complete_unrestricted`** | **同一 append-only 补全，但放开两道门：七条轴全开、不设词数上限** | §4.1 | **46** | ≤200 |

`placebo_corrupt` 分离"标签变长变具体"本身的效应——这是本实验最关键的对照，因为面板可能
系统性偏好更具体的标签。**只有 `complete` 同时优于 `frozen` 与 `placebo_corrupt`，才算补全的
内容起了作用。**

### 4.1 `complete_unrestricted` 为什么必须与 `complete` 同实验、同队列

§1.2 测出两道门高度共线：单独放开任一道只 +6 / +5，同时放开才 14 → 46。所以"轴限制值不值"
这个问题**只能在同时放开的条件下回答**，这就是本臂的契约：

- 七条轴全开（表层三条 + `etiology`、`temporal_evolution`、`complication`、`scope_distribution`），
  不记 `axis_violation`。
- **不设 ≤2 词上限**，不记 `over_specified`。
- 其余全部沿用 §3 且不得放松：append-only（不许换中心词/改词序）、`support_span` 必须逐字、
  极性拒绝、payload 禁 gold/options/端点信息。

放在同一实验同一队列而不是另开一份预注册，是因为这样 `complete_unrestricted` vs `complete`
是**逐例配对**的，能直接给出轴限制的**兑换率**（多覆盖多少例 ÷ 多付多少幻觉），
两份独立实验做不到这一点。代价是多重比较，按 §6.1 的 Holm 处理。

### 4.2 本臂不是为了"追上某个基线"

[`CLINICAL_RESCORE`](../CLINICAL_RESCORE/REPORT.md) §7 已零调用测出：`partial_parent` 在 DA
全覆盖的 5 个归档臂上分别是 210/215/211/213/211，≤2 词补全梯 30/32/25/31/29。
**这是全族同构的失败态，不是 MultiStance 的特性**，且 MultiStance 与 Collapse3c / Forest 在
clinical-complete 上四个配对对比全不显著（p = 0.79 / 0.55 / 0.71 / 0.13）。
因此本实验测的是"纵向补全这个机制有没有用"，**不是"MultiStance 能否超过 Collapse3c"**；
底座选 MultiStance 只因为它有冻结日志与 100% 端点覆盖。§9 禁止把结果写成臂间比较。

## 5. 端点

主端点：**clinical-complete top-1**（`complete_equivalent`）。

判定来源，按此顺序且不得回退：

1. **冻结复用**：`(case_key, canonical_label)` 命中冻结源即采用。`frozen` 臂 200/200 全部命中。
2. **在线三模型盲评面板**：仅对冻结源中不存在的新标签（`complete` / `placebo_corrupt` /
   `complete_unrestricted` 产出的补全标签）裁定。必须复用 C0 的同一套盲评卡协议与 prompt：
   隐藏系统与臂、隐藏是哪个臂产出、三模型多数，三方分裂记 `uncertain`。
   **三臂的新标签必须混洗后交给同一面板**，不得按臂分批送裁。
3. 不得用 `dc.match` 或任何词法规则代替面板判定。

**幻觉率**（对 `complete_unrestricted` 是共同主端点，见 §6）：逐字 span 核验通过率 +
面板盲评判定该修饰词是否被 vignette 支持。定义与 SLOT_YIELD M2 一致，以便与 0.0587 / 0.1862
两个既有读数对齐。

**官方 task 端点（预注册次端点，不作门槛）**：DA 选项投射准确率。判定同样先复用冻结的
`ALL_ARM_ENDPOINT_MIGRATION/task_evaluator/` 结果，未覆盖的新标签需在线跑官方投射器。

> **task 端点有两条硬限制，必须随读数携带。** (a) 冻结覆盖只有 **0.663**（MultiStance DA 冠军），
> 且"哪些 `(case, label)` 有判定"是非随机的；本臂产出的补全标签**全部**是新标签，须全部在线投射。
> (b) DA 上 task 与 clinical-complete 松耦合：临床完整的冠军仍有 4/11 拿不到 task 分，
> 临床非完整的却有 23.6% 拿到（`CLINICAL_RESCORE` §8.2）。**因此 task 不能作为本实验的
> 主端点，也不得用它反推补全是否有效。**

次端点（描述用）：complete ∪ compatible-partial、legacy-chain `dc.match`、服务率、
`not_append_only` / 极性拒绝率、以及仅对 `complete` 有意义的 `axis_violation` /
`over_specified` 触发率。

### 5.1 仪器误差如何进入判定

面板五分类 exact accuracy **0.7082**、Gwet AC1 **0.6544**（E2 隐藏哨兵 n=2601）。
两条必须写进设计而不是事后讨论：

- 误分类对四臂是**非差分**的（同一面板、同一病例、对臂盲、混洗送裁）。非差分误分类使观测效应
  **向零收缩**，因此一个显著的正结果是**保守**的；但它同时意味着**不能从零结果推出效应不存在**。
  NO_GO 只能写成"未测出"，不得写成"无效"。
- 预注册敏感性分析（不得事后添加）：(a) 把 `uncertain` 判定分别当作失败与剔除，各报一次；
  (b) 用 `--drop-source-conflicts` 口径重算 `frozen` 基线。

## 6. Go 门槛（执行前冻结）

### 6.1 `complete`（受限轴）——主假设

全部满足才算 Go：

- 四臂服务率各 ≥ 0.98。
- `complete` 的 clinical-complete ≥ `frozen`，且**配对精确 McNemar 双侧 p < 0.05**。
- `complete` ≥ `placebo_corrupt`，且配对精确 McNemar 双侧 p < 0.05。
- 修饰词幻觉率 ≤ **0.10**（硬门）。SLOT_YIELD 的 M2 门槛是在 0.1862 上失败的。
- 均宽恒等于 `frozen`（append-only 不增席，机械核验）。

以上两个 McNemar 是本实验的**主族**，按 Holm 在族内校正（2 个对比）。

**v1 用的是"+3pp 且下界 > 0"。v2 改为 McNemar 显著性**，因为基线只有 6/200：在 3% 基线上
"+3pp"意味着效应翻倍，把门槛写成百分点会让一个真实但较小的效应被判 NO_GO，而配对检定在
单向不一致对上更有力。这一改动在执行前冻结，不得在见到结果后回退。

**No-Go：** 任一条不满足即 NO_GO，不得改门槛后重测同一批例。

### 6.2 `complete_unrestricted`（放开两道门）——不设 Go/No-Go，只报兑换率

**本臂没有幻觉率硬门，也没有 Go 门槛。** 理由：它的设计预期就是把幻觉率推到 0.1862 段，
对它设 ≤0.10 的门等于预先判它失败，读不到任何信息。因此它的角色是**测量轴限制的兑换率**，
共同主端点两个、方向相反：

1. **覆盖**：`complete_unrestricted` 相对 `complete` 的 clinical-complete 增量（配对 McNemar）。
2. **代价**：`complete_unrestricted` 相对 `complete` 的幻觉率增量（配对，同一批修饰词口径）。

预注册的读法（**执行前冻结，不得事后调整**）：

| 覆盖增量 | 幻觉增量 | 结论 |
|---|---|---|
| 显著 > 0 | ≤ +0.05 | 轴限制**过严**，后续实验应放开并单独确证 |
| 显著 > 0 | > +0.05 | **取舍成立**：记录兑换率，受限轴仍是默认；是否放开留给下游按风险偏好决定 |
| 不显著 | 任意 | 轴限制**不是瓶颈**，§1.2 的 14→46 只是词法可达性，不代表模型能力 |
| 显著 < 0 | 任意 | 放开轴**反而更差**（长推断短语挤掉正确核心），受限轴得到正面支持 |

这四格覆盖全部可能结果，**没有一格是"失败"**——本臂无论怎样都产出一个可写的兑换率。
这是它值得占 ≤800 次调用的理由。

§7 预测 7 给出本臂的先验；两个共同主端点在**本臂族内**按 Holm 校正（2 个对比），
与 §6.1 的主族**分开校正**，不合并。

## 7. 预注册预测

1. 严格口径靶 **14 例**（§1 实测，非上界，见 §1.1），其中被 `complete` 实际改写标签的
   60–100 例（补全作用于全部 107 个 partial 冠军，不止 ≤2 词档）。
2. `complete` 相对 `frozen` 的 clinical-complete Δ ∈ **[+2pp, +6pp]**：基线 6/200，
   14 例按 50%–90% 兑现即 13–19/200。不一致对预计 5–13 例且高度单向。
   若兑现率 < 35%（Δ < +2.5pp）则不一致对不足以过 McNemar，判 NO_GO。
   **区间上沿允许被突破**：非参照串的补全若被面板判 complete，收益会落在这 14 例之外
   （§1.1 的偏窄方向）。若 Δ > +6pp，须先核验新增命中是否为 §3 契约内的补全，
   再报告，不得直接归因。
3. `placebo_corrupt` ≤ `frozen`（Δ ∈ [−3pp, 0]）。
4. **legacy-chain 端点上 `complete` 相对 `frozen` 的 Δ ∈ [−4pp, +1pp]**，且可能为负：
   把 `Amyloidosis` 补成 `Bullous amyloidosis` 会**丢掉** `dc.match` 对粗父类的信用
   （DA 93 例 legacy 命中里 83 例是粗父类）。**这是预期行为，不是回归。** 若 legacy-chain
   反而大涨，说明补全在改变记分匹配而非诊断内容，按可疑处理。
5. complete ∪ compatible-partial 近似不变（Δ ∈ [−2pp, +2pp]）：append-only 补全把
   partial 变成 complete，两者都计入这个并集。
6. **官方 task 端点：`complete` 相对 `frozen` 的 Δ ∈ [0, +5pp]，方向为正但小于 clinical-complete
   的 Δ。** 依据：严格臂的靶当前 **23/26 是 task 错的**（`CLINICAL_RESCORE` §8.3），
   所以选项投射并没有替补全把粗父类兜住，头寸是真的；但把标签补具体之后投射器是否改判**未测**，
   且 DA 上 task 与完整性松耦合，所以不预期 1:1 兑现。
   **若 task Δ ≤ 0 而 clinical-complete Δ 显著为正，不得判本实验失败**——那是两个不同估计量
   （§5 的限制 b），应报告为"补全改善诊断完整性但未改善选项投射"。
7. **`complete_unrestricted`：落在 §6.2 的第二格（取舍成立）。** 具体先验——
   clinical-complete 相对 `complete` 的 Δ ∈ **[0, +5pp]**（词法可达性 14 → 46，但推断轴的
   补全平均要加 4–9 个词，模型答对整条长短语的概率远低于答对单个解剖词）；
   幻觉率相对 `complete` 的 Δ ∈ **[+0.08, +0.15]**（对齐 SLOT_YIELD 的 0.0587 → 0.1862）。
   附带预测：本臂的 `not_append_only` 触发率高于 `complete`，因为长推断短语更容易顺带改写中心词。

预测 4 是 v2 相对 v1 最重要的新增：**两把尺子在本实验上会给出相反符号**，事先写死可以防止
事后择尺。预测 7 是四臂版新增：它把 §1.2 那个"14 vs 46"的词法落差与**模型实际能力**分开，
若 Δ 接近 0 则说明 46 从来不是真实可达规模。

## 8. 调用预算

| 项 | 次数 |
|---|---:|
| 补全调用（受限轴；`complete` 与 `placebo_corrupt` 共用） | 200 |
| 补全调用（放开两道门；`complete_unrestricted` 专用 prompt） | 200 |
| 在线面板：`complete` 新标签 × 3 模型 | ≤600 |
| 在线面板：`placebo_corrupt` 新标签 × 3 模型 | ≤600 |
| 在线面板：`complete_unrestricted` 新标签 × 3 模型 | ≤600 |
| `frozen` 臂 | 0 |
| **合计** | **≤2200** |

`complete_unrestricted` 需要独立的补全调用（契约不同，不能与受限轴共用响应），所以它的
增量是 200 + ≤600 = **≤800 次**。

v1 是 1600 次且换不到可解读的读数（G0 预测 Δ ∈ [−1,+2] 例）。四臂版是 ≤2200 次换两个读数：
主假设的配对检定，加上轴限制的兑换率（§6.2 四格中无论落在哪一格都可写）。

可裁减顺序，若预算受限：
1. 先砍 `complete_unrestricted`（回到三臂 ≤1400），主假设不受影响。
2. **不可**砍 `placebo_corrupt`：它是唯一能排除"面板偏好长标签"的对照，砍掉它主假设就不可解读。

## 9. 可写与不可写（执行前冻结）

**可以写（无论结果）：**
- `CLINICAL_RESCORE` §4 在 **dev-400** 上的阶梯（210 → 91 → 45 → 30）与本文件 §1 在
  **holdout-200** 上的阶梯（107 → 46 → 19 → 14）：零调用、可复现的**结构测量**
  （不是效应上限，见 §1.1）。
- 两把尺子的符号差异（预测 4），无论方向。
- 四臂的相对关系与各项契约违约率。
- **轴限制的兑换率**（§6.2）：四格中任一格都是可写结果。

**不可以写：**
- **不可把本实验写成臂间比较。** MultiStance 与 Collapse3c / Forest 在 clinical-complete 上
  四个配对对比全不显著（`CLINICAL_RESCORE` §7.3），且 `partial_parent` 与补全梯在 5 个归档臂上
  几乎相同。本实验测机制，不测哪个方法更好；不得声称"补全让 MultiStance 超过 X"。
- 不可把 `complete_unrestricted` 的幻觉率超过 0.10 写成该臂失败：它**没有**幻觉率门（§6.2）。
- 不可把 §6.2 的兑换率外推到其它轴组合或其它族：本实验只测"三条表层轴 & ≤2 词"对"七轴 & 不限词"
  这一对，且只在 DA 上。
- **不可混用三个分母。** 210 是 dev-400 的 `partial_champion` 数，**不是本实验的队列**；
  本队列（holdout-200b, n=200）对应 107；契约内严格口径 14。任何"210 例可干预"的表述都是错的。
- 不可把 14 写成可寻址上界或下界（§1.1）。
- 不可把"只有 14 例"单独归因于任一道门：两道门高度共线，单独放开各只 +6 / +5（§1.2）。
- 不可把 `complete` 优于 `frozen` 但不优于 `placebo_corrupt` 写成补全有效。
- 不可把 NO_GO 写成"补全无效"：面板非差分误分类使检定偏保守（§5.1）。
- 不可把面板判定报成人工根真值；truth tier 是 model-panel sensitivity。
- 不可跨族合并（本实验只有 DA）。
- 不可把结果外推到 9 宽池上的补全：该口径已在 `MULTISTANCE_CORELIFT_PROBE` 被否
  （DA 池召回 .60 → .40）。
- 不可把 legacy-chain 的下降报成性能回归（预测 4）。

## 10. 状态

**`EXECUTED` — 主假设 NO_GO**（2026-08-21）。四臂 1195 次调用，结果见
[`REPORT.md`](REPORT.md)、[`summary.json`](summary.json)。

摘要：`frozen` 6 / `complete` 8 / `placebo_corrupt` 6 / `complete_unrestricted` 9（n=200）。
主族两个对比 Δ 均 +2 例、p = 0.6875、Holm 1.0，未过 §6.1；受限轴幻觉率 **0.1583** 冲破
≤0.10 硬门。§6.2 兑换率落**第三格**（轴限制不是瓶颈）。§1 钉死的 `frozen`=6 与
`partial_champion`=107 均复现（REPORT §1），该复现检出了一处端点连接键错误。
预测 4 的"两把尺子相反符号"被证实且幅度超界（legacy `dc.match` 45 → 22，−11.5pp）。

**`READY`**（2026-08-20，历史）。G0 已解除，四臂设计已冻结，待执行。
`complete_unrestricted` 于同日加入（§4.1），与三臂主假设同队列同基线。

同级预注册已写就：**MCR 选择层候选截断**
[`MCR_SELECTOR_TRUNCATION/PREREGISTRATION.md`](../MCR_SELECTOR_TRUNCATION/PREREGISTRATION.md)
（`CLINICAL_RESCORE` §5 的 63 例，主队列 167 例，668 次调用、零面板）。
注意它的 §0 更正了 `CLINICAL_RESCORE` §5 读数 2：冻结 multistance 臂**没有**每组一个提名席位，
比较器 payload 里本来就含完整 ledger 平铺全表（均 8.75 宽），所以那 63 例的完整标签从未被藏起来，
干预方向是**截断**而非加宽。两份实验族不同、机制不同、无共享调用，可并行。

**MCR 那份已于 2026-08-21 执行完毕，主假设 NO_GO**（截断 5 宽 −2 例 p=0.754，3 宽 −5 例；
[`REPORT.md`](../MCR_SELECTOR_TRUNCATION/REPORT.md)）。这不改变本预注册的任何设计——两者
族不同、层不同（MCR 打选择层，本份打生成层），且本份的靶（210/400 partial 冠军里 207 例
池内没有任何完整标签）**在定义上就与选择层无关**。但它确实使本份成为目前唯一在跑的干预，
排期上应据此提前。
