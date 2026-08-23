# 决赛失手解剖（B/C）：补全与判别器两条路各自有没有靶

生成脚本 `analysis/mechanism_v2/finals_loss_anatomy.py`（零 LLM 调用，读冻结的
`aphhm_c_multistance_v1/case_stages`，六个开发切片共 800 例，取金标进过决赛的
294 例：`ok` 181 + `final_drop` 113）。产物 `summary.json`、`cases.jsonl`。

上游：[`CORE_REGROUP_HEADROOM/REPORT.md`](../CORE_REGROUP_HEADROOM/REPORT.md) §5.1 提出
DA 决赛与 MCR 决赛需要两种不同干预。B 检验 DA 那条（受限轴纵向补全），C 检验 MCR 那条
（候选独有判别项 / 反事实对比）。

端点口径同上游：一切席位与命中都是 `dc.match`（legacy-chain），对 clinical-complete 的
PPV 只有 56.48%。

> **后续更正（2026-08-20，[`CLINICAL_RESCORE/REPORT.md`](../CLINICAL_RESCORE/REPORT.md)）：
> 本报告关于 B 的结论已被真端点推翻，关于 C 的结论保留。**
>
> 那台 clinical-complete 评分器早已存在（判定按 `(case, label)` 冻结、与臂无关、覆盖 800/800
> 冠军），已在真端点上重算。结果是：
>
> - **B 有靶，而且大一个量级。** 真端点上 DA 有 **210/400** 例冠军是
>   `partial_parent_or_component`（对但不完整的父类），其中冠军是参照真词法子集的 91 例、
>   加词属表层轴的 45 例、加词 ≤2 的 **30 例**；且 **207/210 例池内不存在任何更好的席位**。
>   本报告只看到 1–2 例，原因是**找错了地方**：`final_drop` 是 `dc.match` 定义的子集，
>   而那 210 例分散在旧分类的 `ok` 83 / `not_proposed` 49 / `group_drop` 44 / `final_drop` 34。
>   §0 那句"MultiStance 决赛的冠军几乎从不欠修饰词"在临床口径下是**错的**：一半以上的 DA 冠军
>   正好欠修饰词。
> - **§1.1 的阶梯（`8 → 2 → 0`）作废。** 它度量的是"补全后能否改变 `dc.match` 记分"，
>   而不是"补全后诊断是否变完整"。粗父类早已被匹配器记分，所以补全它在旧端点上恒为零收益——
>   这是记分口径的性质，不是补全能力的上界。
> - **B 的"反方向 29/45：模型答得比被记分的参照更具体"这一观察保留**，且被真端点解释了：
>   被记分的那个池内标签正是粗父类（DA 93 例 legacy 命中里 83 例临床上是 `partial`）。
> - **C 的结论保留**（22/24 金标独有证据为 0，反事实判别器缺材料，与端点无关）。但 MCR 的真问题
>   不在决赛比较器：真端点上 MCR 有 **63 例**池内已有完整标签却没赢，完整标签 ledger rank
>   中位数 2、50/63 落在 top-5 与 commit 组内。C 测的不是这件事。
>
> 基于本报告写的预注册已按真端点重写为
> [`DA_FINALS_AXIS_COMPLETION/PREREGISTRATION.md`](../DA_FINALS_AXIS_COMPLETION/PREREGISTRATION.md) v2
> （G0 解除，靶从 2 例变为 14 例可寻址）。

## 0. 一句话结论（已被上方更正推翻其中 B 的部分）

**两条都没有靶，而且否掉它们的是同一个事实：MultiStance 决赛的冠军几乎从不"欠修饰词"。**

- B：DA 45 例输给词法近亲的决赛失手里，**只有 4 例冠军是金标的词法父类，受限轴口径下只剩 1 例**。
  反方向却有 **29/45**：legacy-chain 记为金标的那个池内标签是冠军的真子集，即模型答的比被
  记分的参照**更具体**。append-only 补全治的是欠具体，DA 决赛输的是**在错误分支上过具体**。
- C：MCR 24 例输给无关对象的决赛失手里，**22 例金标的 `gold_disc = 0`**——它的每一条 support
  span 都同时挂在别的候选上。候选对反事实判别器要"各自独有的证据"，冻结证据里没有这个材料。
  且 `against` 规则不是杀手：败例金标带 `contradict_spans` 的只有 5/24，胜例反而是 44/88。

## 1. B：DA 决赛失手能被 append-only 补全改变吗

对 113 例 `final_drop` 中冠军与金标有词法亲缘的那部分（DA 45 / MCR 17）：

| 判据 | DA (n=45) | MCR (n=17) |
|---|---:|---:|
| 池内存在金标的词法父类（金标可由加修饰词得到） | **43** | 15 |
| 其中加的词不触发四条推断轴标记（可能是表层轴） | 20 | 13 |
| **且这个父类就是冠军本身**（补全冠军即得金标） | **1** | **0** |
| 冠军是金标的词法父类（不限轴） | 4 | 0 |
| 金标是冠军的词法父类（冠军过具体） | 0 | 2 |
| legacy-chain 记分的池内标签是冠军的真子集 | **29** | 11 |
| 同一判据在 `ok` 例上的对照 | **3 / 93** | 2 / 88 |

最后两行是这一节的重点。**"记分标签 ⊂ 冠军" 在决赛败例里是 29/45，在决赛胜例里只有 3/93。**
这不是模型少写了修饰词，而是记分参照比模型的答案粗。几个逐例样本（`cases.jsonl`）：

| 真金标 | 冠军 | 池内被记分的父类 |
|---|---|---|
| Caruncular melanoma | Malignant Melanoma of the Caruncle | Melanoma |
| Intergluteal and sacral hyperhidrosis | Primary Hyperhidrosis | Hyperhidrosis |
| Epidermolysis bullosa pruriginosa | Dystrophic Epidermolysis Bullosa | Epidermolysis Bullosa |
| Heterozygous HTRA1-related CSVD | HTRA1-related hereditary vascular dementia | HTRA1-Related Cerebral Small Vessel Disease |

第一行是纯记分伪影：`Caruncular melanoma` 与 `Malignant Melanoma of the Caruncle` 是同一个
东西，`dc.match` 因词序/派生词判负。按 jaccard ≥ 0.5 粗筛，45 例里有 3 例是这类。第二、三行
是真机制但方向与补全相反：模型**已经加了修饰词，只是加在了另一条轴上**（etiology 而非
anatomy；dystrophic 而非 pruriginosa）。第四行池里已有近乎精确的金标，它在决赛里输掉了——
要修的是比较，不是标签粒度。

另一个必须记录的数：**72 例 DA `final_drop` 里有 71 例的"金标在池内"是由非同一字符串授予的**。
也就是说这一层的 `ok/final_drop` 划分几乎全部建立在粗粒度父类信用上。

### 1.1 决赛层的上限阶梯（补全作用在 finalist 上，不是冠军上）

上游 §5.1 的设计是补全 2–3 个 finalist，所以正确的靶定义是"某个 finalist 是参照的粗粒度
父类"。这个数看起来很大，但两道过滤把它清干净：

| 阶梯 | DA | MCR |
|---|---:|---:|
| `final_drop` | 72 | 41 |
| 存在 finalist 是参照的词法父类 | **65** | 28 |
| ⤷ 且它**当前还不能** `dc.match` 记分 | **8** | **0** |
| ⤷ 且加的词属表层轴 | **2** | 0 |
| ⤷ 且加词不超过 2 个 | **0** | 0 |

第二行到第三行的塌陷（65 → 8）就是这一节的结论：**那个"粗粒度父类 finalist"绝大多数就是
`dc.match` 已经记为金标的那个席位本身**。`final_drop` 的定义是金标已占席但输掉比较，所以
在 legacy-chain 口径下补全它**不改变任何记分**——它改变的是标签粒度，而记分早已由粗父类拿到。

这条阶梯把 A 的处境说清楚了：**在当前端点下 A 的靶是 2/72（DA）、0/41（MCR）；
而如果端点换成 clinical-complete，同一批 65 例全部变成靶。** A 的价值完全取决于端点，
不取决于机制。

轴标记分布（43 例可达例，加的词命中哪条推断轴；未命中记 `none_surface_plausible`）：
`none` 20、etiology 9、temporal 9、scope 6、complication 5（可多重命中）；另有 17 例金标本身
是 `with/and` 复合标签。SLOT_YIELD 的 M2 门槛在这四条推断轴上幻觉率 0.1862、表层轴 0.0587，
所以即使只做表层轴，可达面也只有 20/45，再要求靶是冠军本身就只剩 1 例。

## 2. C：MCR 决赛失手有判别器可用的材料吗

`evidence_discriminability`（金标的 support span 中不被任何其他候选共享的比例）：

| 分层 | n | `gold_disc` 均值 | `champ_disc` 均值 | `gold_disc=0` | 金标带 `against` | 金标 span 数 |
|---|---:|---:|---:|---:|---:|---:|
| MCR `ok` | 88 | 0.133 | 0.133 | 54 | **44** | 3.69 |
| MCR `final_drop` 无关对象 | 24 | 0.056 | 0.123 | **22** | 5 | 2.46 |
| MCR `final_drop` 词法近亲 | 17 | 0.103 | 0.051 | 14 | 5 | 2.29 |
| DA `ok` | 93 | 0.233 | 0.225 | 46 | 24 | 3.76 |
| DA `final_drop` 无关对象 | 27 | 0.120 | 0.106 | 19 | 5 | 2.59 |
| DA `final_drop` 词法近亲 | 45 | 0.096 | 0.124 | 36 | 10 | 2.67 |

三条读数：

1. **判别器没有材料。** 24 例里 22 例金标独有证据为 0，冠军独有证据也多半为 0
   （`champ_disc > gold_disc` 只有 7/24）。这是一场**共享证据下的先验之争**，
   "让模型比较两个候选各自独有的证据"在这批例子上无从下手。要产生独有项必须回到
   vignette 取新观察——那是 C3 active-evidence，而 C3 是 `NOT_EXECUTED_OPERATIONAL_NO_GO`。
2. **区分胜负的是证据量，不是证据特异度。** 胜例金标 3.69 条 span、败例 2.46 条；
   `gold_disc` 两边都接近 0。这正是 CEILING_ROOT §6.6 "evidence 量胜过 evidence 特异度"
   在 MultiStance 决赛内部的复现。
3. **`against` 规则不是杀手，可以关闭这条假设。** tournament prompt 写着"带强 against 的候选
   通常是错的"，但败例金标带 against 的只有 5/24，胜例是 44/88。这条 prompt 规则没有在杀
   正确答案。
4. 4/24 的无关对象败例里，被记分的池内标签是冠军的真子集（`Sarcoma` vs
   `Prostatic Stromal Sarcoma`、`Appendicitis` vs `Appendiceal stump appendicitis`、
   `Osteomyelitis` vs `Brodie's abscess`）。同 §1 的记分伪影。

## 3. 对上游两条建议的处置

| 上游 §5.1 建议 | 本次判定 |
|---|---|
| DA 决赛：完整度优先 + 受限轴纵向补全 | **在 legacy-chain 端点下关闭**（靶 2/72，加词 ≤2 时为 0）；**在 clinical-complete 端点下靶变成 65/72**。是端点问题，不是机制问题 |
| MCR 决赛：候选独有判别项 / 反事实对比 | **关闭。** 22/24 金标独有证据为 0，冻结证据里没有可对比的独有项 |

同时新暴露一个必须先处理的问题：**决赛这一层的胜负判定本身有相当比例是 legacy-chain 的
父类信用产物**（DA 71/72 非同一字符串；败例 29/45 记分标签 ⊂ 冠军，胜例仅 3/93）。在把它
测清楚之前，任何针对决赛比较器的机制实验都在优化一个已知 PPV 0.5648 的目标。

## 4. 可写与不可写

**可以写：**
- MultiStance 决赛失手中，冠军是金标词法父类的只有 4/45（DA）、0/17（MCR）；受限轴口径 1/45。
- 决赛层上限阶梯：65/72 例有 finalist 是参照的父类，但其中 57 例那个 finalist 就是
  `dc.match` 已记分的席位；扣掉后 8/72，再限表层轴 2/72，再限加词 ≤2 为 0/72。
- 反方向"记分标签 ⊂ 冠军"在 DA 决赛败例是 29/45，胜例 3/93。
- MCR 无关对象败例中 22/24 金标独有证据为 0；胜负差异体现在 span 数（3.69 vs 2.46）。
- 决赛败例金标带 `contradict_spans` 的比例低于胜例（5/24 vs 44/88），`against` 规则未杀金标。
- DA 72 例 `final_drop` 中 71 例的池内金标信用来自非同一字符串。

**不可以写：**
- 不可把轴标记当成轴的真值：它是小词表确定性代理，43 例中 20 例只是"未命中推断轴标记"，
  不等于"确认是表层轴"。
- 不可把 `evidence_discriminability = 0` 读成"这条证据不能区分"：它只说这条 span 同时挂在
  别的候选上；一条共享 span 在临床上仍可能是决定性的。
- 不可用 §1 的样本表推断幻觉率或补全收益：它是 45 例里的抽样展示，不是估计量。
- 不可据 §3 声称"补全机制无效"：SLOT_YIELD 的 DA +5.50pp 是在另一个基臂上实测的；本节只说
  它在 **MultiStance 决赛这一层、在 legacy-chain 端点下**没有靶。
- 不可把 §1.1 的 65/72 读成 clinical-complete 下的预期收益：那 65 例只是"存在一个词法父类
  finalist"，能否被正确补全、补全后是否临床完整，本节都没有测。

## 5. 复现

```bash
python3 analysis/mechanism_v2/finals_loss_anatomy.py \
  --out analysis/mechanism_v2/results/FINALS_LOSS_ANATOMY
```
