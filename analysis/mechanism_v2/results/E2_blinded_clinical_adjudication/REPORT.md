# E2 — 全 800 例五端点根级临床审计与轨迹机制重放

## 结论先行

E2 的旧版结论需要实质纠正，而不是只改表头。旧报告把
`strict_chain_correct` 显示为 `Strict`，但该字段实际是带双向 substring /
resolver 的历史 `chain_correct`。因此，旧报告中的 18.76%–25.98% 不是
safe-exact；它们是 `legacy-chain`。旧版又只在按结局富集、分层抽取的 400
例上做根审，再以设计权重外推到 800 例；其普通未加权 McNemar 检验与加权
estimand 不匹配。

本版直接完成 800/800 例根级 census，并对九个完整历史臂的 7,200 个
case-arm 输出统一重放五列：

1. `safe-exact`：7.12%–8.62%，是高精度、低召回的冻结下界；
2. `legacy-chain`：19.38%–26.62%，会因 substring 与父类兼容产生系统性
   排名偏移；
3. `clinical-complete`：12.25%–15.25%，是本研究衡量“完整诊断对象是否
   正确”的主端点；
4. `partial`：29.88%–35.25%，表示兼容父类、组成部分或欠特异对象，不能
   报作诊断正确；
5. `task`：40.12%–46.12%，但 DA 是 option mapper，MCR 是缓存语义 judge，
   二者必须分层解释。

全 800 例中，Collapse3c 的 `clinical-complete` 最高（15.25%），
Multistance 极接近（15.12%）；在 **overall** 的预定义 10 对比 Holm 家族中，
没有 clinical-complete 对比达到 `q<.05`。MCR 家族内 Collapse3c 相对 IMPC
达到 `q=.045615`，但 DA–MCR 交互经 Holm 后不成立，因此仍不能据此宣称“全局
赢家”。真正稳固的结论是：各系统之间存在大量方向相反的对象恢复、限定语压平
与灾难性替换；legacy-chain 的显著排序差异没有转化为完整临床对象差异。

MCR 内部自动评估可优先采用校准后的 task judge：相对 clinical-complete，
其 PPV 84.83%、sensitivity 94.74%、specificity 94.72%、MCC .862。
DA task mapper 的 PPV 仅 5.12%，衡量的是接口/选项命中，不是完整诊断能力。
`safe-exact` 保留为保守下界；`legacy-chain` 不再承担主指标角色。

## 1. 端点契约与禁止解释

| 列 | 可复现定义 | 本研究用途 | 不允许的解释 |
|---|---|---|---|
| safe-exact | 规范化 exact 或冻结的安全同义词；禁用 substring/fuzzy | 高精度保守下界、回归测试 | 无偏的绝对能力估计 |
| legacy-chain | 历史双向 substring/resolver `chain_correct` | 复现旧结果、诊断旧排名为何变化 | strict、concept accuracy 或完整临床正确 |
| clinical-complete | 根审确认输出与 reference 所要求的完整诊断对象临床完全等价 | **能力主端点** | 在 reference 本身不可由病例唯一支持时，自动等同“真实世界真相” |
| partial | 兼容父类、组成部分或欠特异对象；与 complete 互斥 | 覆盖/软着陆机制 | 完整正确、半个正确分数 |
| task | DA option mapper；MCR 缓存语义 judge | 家族内接口成功；MCR 可作校准 proxy | 合并 DA+MCR 后的同质能力端点 |

`complete-or-partial` 仅作为次要 coverage sensitivity，并非第六个主端点。
所有 clinical-complete 解释必须同时报告 `reference-identifiability`：病例是否
唯一支持 reference 的全部病因、解剖、时间、阶段与复合组件。

## 2. 从旧 400 例外推纠正为 full-800 census

旧 E2 的 400 例不是随机 census，而是 DA/MCR 各 200 例，按
`family × slice × primary_stratum` 分层并富集 mapper harm、stable-exclusive、
all-method failure 等机制层，设计权重之和为 800。旧 400 例包含 1,673 个去重
`(case_key, candidate_id)` 关系；这些关系在九臂之间共同投影，并非每个臂独立
审计。

本轮冻结其余 400 例后，在不查看 arm、旧端点或 leaderboard 的条件下构造中性
cards，并由三个互斥批次独立人工盲审：

| 批次 | Case | 候选关系 | 覆盖范围 |
|---|---:|---:|---|
| A | 134 | 472 | U0001–U0134 |
| B | 133 | 456 | U0135–U0267 |
| C | 133 | 443 | U0268–U0400 |
| **合计人工关系** | **400** | **1,371** | 全部非确定性安全 exact 关系 |

另有 59 个确定性 safe-exact 关系按冻结规则直接标为 complete；故补充 registry
共有 1,430 个关系。根审随后逐项复核全部 `uncertain`、低置信、complete/partial
边界和同义语义对，记录 1 个 identity 与 14 个 relation override 及理由。一个
关系仍明确保留为 `uncertain`，没有被强行塞入 complete 或 partial。

最终 800 例的 reference identity 分布为：

| Identity | ALL | DA | MCR |
|---|---:|---:|---:|
| unique full reference | 455 | 285 | 170 |
| family-only, not full specificity | 139 | 78 | 61 |
| unsupported reference specificity | 131 | 30 | 101 |
| insufficient case information | 70 | 6 | 64 |
| multiple complete answers | 5 | 1 | 4 |
| uncertain | 0 | 0 | 0 |

本次补齐未调用外部 LLM。此前 400 例审计中外部模型的意见只保留为历史
subcontractor 轨迹；本版新增 400 例的 clinical 决策和最终 override 均由根级
人工审计负责。

## 3. 数据完整性与重放校验

重放覆盖 9 个全域臂：Collapse3c、Multistance、Lite、Forest、IMPC、E7、v0、
B06、B07。验证结果：

- 800 个唯一 case，DA/MCR 各 400；
- 7,200 个唯一 case-arm 行，每臂恰好 800；
- `clinical-complete` / `partial` 缺失 0，重叠 0；
- safe-exact 阳性却被根审判为 non-complete 的矛盾 0；
- 与冻结 matrix 的 legacy-chain 与 task 不一致均为 0；
- 旧 400 例的 1,673 关系与新增 400 例的 1,430 关系均保留血缘；
- 原始历史 leaderboard 不改字节，迁移结果写入独立 v2 artifact。

## 4. 全 800 例五端点结果

### 4.1 Overall

| Arm | safe-exact | legacy-chain | clinical-complete | partial | task | complete-or-partial |
|---|---:|---:|---:|---:|---:|---:|
| Collapse3c | 8.50% | 21.12% | **15.25%** | 32.88% | **46.12%** | 48.12% |
| Multistance | **8.62%** | 22.62% | 15.12% | 32.50% | 45.00% | 47.62% |
| Lite | 7.88% | 23.75% | 13.25% | 33.75% | 42.88% | 47.00% |
| Forest | 8.25% | **26.62%** | 13.38% | 34.88% | 45.12% | **48.25%** |
| IMPC | 8.50% | 26.50% | 12.25% | 34.38% | 43.38% | 46.62% |
| E7 | 7.38% | 20.25% | 14.12% | 29.88% | 41.62% | 44.00% |
| v0 | 7.50% | 19.38% | 12.88% | 30.88% | 40.12% | 43.75% |
| B06 | 7.75% | 24.25% | 13.12% | 35.00% | 44.50% | 48.12% |
| B07 | 7.12% | 21.25% | 12.62% | **35.25%** | 44.00% | 47.88% |

这个表解释了“E 开头实验臂为何经常只有个位数 accuracy”的反常现象：这些
实验大多报告 safe-exact，而历史强基线常被标为 `Concept/Strict` 的数实际是
legacy-chain 或 stage-specific chain。对同一批输出换回统一定义后，所有系统的
safe-exact 都只有 7%–9%，并非 E 臂独有崩溃；真正的临床完全等价为
12%–15%，partial 又占约 30%–35%。反差主要来自端点混用，其次才是模型的对象
完整性不足。

### 4.2 DiagnosisArena（DA）

| Arm | safe-exact | legacy-chain | clinical-complete | partial | task | complete-or-partial |
|---|---:|---:|---:|---:|---:|---:|
| Collapse3c | 0.75% | 20.00% | 3.75% | 52.75% | 63.00% | 56.50% |
| Multistance | 0.75% | 23.25% | **4.25%** | 52.50% | 61.75% | 56.75% |
| Lite | **1.25%** | 25.75% | 4.00% | **53.75%** | 60.25% | **57.75%** |
| Forest | 0.50% | 28.00% | 3.50% | 53.25% | **63.75%** | 56.75% |
| IMPC | **1.25%** | **29.25%** | 3.25% | 52.75% | 62.50% | 56.00% |
| E7 | 1.00% | 20.25% | 3.75% | 48.75% | 57.00% | 52.50% |
| v0 | 0.25% | 17.50% | 2.25% | 47.50% | 55.25% | 49.75% |
| B06 | 0.00% | 24.50% | 2.25% | 53.50% | 61.50% | 55.75% |
| B07 | 1.00% | 21.25% | 3.00% | 53.50% | 61.50% | 56.50% |

DA 的 reference 可唯一识别率反而更高（71.25%），但 complete 只有
2.25%–4.25%。这不是“病例不可判定”造成的：主要失败位于**输出粒度**。DA
reference 经常要求长复合对象、病因、部位、阶段或并发组件；系统往往只输出
parent、一个 component 或临床相关 manifestation。因而 DA 的 partial 超过
47%，而 option mapper 又把大量宽泛/相关对象映射成正确选项。

### 4.3 MedCaseReasoning（MCR）

| Arm | safe-exact | legacy-chain | clinical-complete | partial | task | complete-or-partial |
|---|---:|---:|---:|---:|---:|---:|
| Collapse3c | 16.25% | 22.25% | **26.75%** | 13.00% | **29.25%** | 39.75% |
| Multistance | **16.50%** | 22.00% | 26.00% | 12.50% | 28.25% | 38.50% |
| Lite | 14.50% | 21.75% | 22.50% | 13.75% | 25.50% | 36.25% |
| Forest | 16.00% | **25.25%** | 23.25% | 16.50% | 26.50% | 39.75% |
| IMPC | 15.75% | 23.75% | 21.25% | 16.00% | 24.25% | 37.25% |
| E7 | 13.75% | 20.25% | 24.50% | 11.00% | 26.25% | 35.50% |
| v0 | 14.75% | 21.25% | 23.50% | 14.25% | 25.00% | 37.75% |
| B06 | 15.50% | 24.00% | 24.00% | 16.50% | 27.50% | **40.50%** |
| B07 | 13.25% | 21.25% | 22.25% | **17.00%** | 26.50% | 39.25% |

MCR reference 唯一可识别率仅 42.50%，却有 21.25%–26.75% complete。这说明
reference-identifiability 与“是否复现 benchmark label”是两条轴：短病例可能未
唯一排除其他完整诊断，但系统仍能给出记录的 reference。MCR 的 task judge
校准良好；此前没有发生 DA 那种“个位数 safe-exact（旧字段 strict）+ 60%
mapper”式反常，只是旧 legacy-chain 会夸大 Forest/IMPC 等稳定 parent 输出的
相对优势。

## 5. 哪个指标最接近真实诊断能力

以 clinical-complete 为真值、把九臂输出作为描述性校准样本，得到：

| Family | Proxy | PPV | Sensitivity | Specificity | MCC |
|---|---|---:|---:|---:|---:|
| DA | safe-exact | 100.00% | 22.50% | 100.00% | .468 |
| DA | legacy-chain | 7.03% | 49.17% | 77.59% | .114 |
| DA | task mapper | 5.12% | 93.33% | 40.40% | .124 |
| MCR | safe-exact | 100.00% | 63.67% | 100.00% | .756 |
| MCR | legacy-chain | 76.95% | 72.55% | 93.22% | .671 |
| MCR | task judge | **84.83%** | **94.74%** | **94.72%** | **.862** |

这些数把三种自动指标的角色分开：

- safe-exact 从未制造 clinical false positive，但这是 frozen safe-exact 阳性按
  契约确定性进入 complete、并对矛盾 fail-fast 的**结构性保证**，不是一次独立的
  100% 精度验证；它在 DA 漏掉近八成 complete，适合做保守下界，不适合单独
  衡量能力；
- legacy-chain 在 MCR 尚可，却在 DA 把大量 partial 当正确，跨 benchmark 不
  稳定；
- MCR task judge 同时具备较高 PPV/recall，是内部自动评估的优先 proxy；
- DA task mapper 几乎是高召回、极低精度的接口通过器，只能描述“能否映射到
  选项”，不能回答“是否给出完整诊断”。

ALL 的 task 校准值不用于推断，因为它把两种不同任务合同混成一个数。上表把同一
case 在九个 arm 中重复作为输出级描述单位；7,200 行实际只有 800 个病例和
2,878 个唯一 case-candidate 输出簇，不能把它们误当 7,200 个独立病例做显著性
检验。配对检验与 rank bootstrap 始终以 case 为单位，因此没有这项伪重复。

## 6. 配对统计、乘数控制与排名不确定性

由于现在是真正 800 例 census，overall 差值直接用 800 个配对病例的 exact
McNemar；置信区间采用 DA/MCR 分层的 case bootstrap。预定义的十个对比在每个
相干 overall endpoint 内做 Holm；另保留跨 ALL/DA/MCR 的 30-test endpoint-wide
Holm 供审计。task 不做 ALL 推断，只在 DA 和 MCR 各自的十对比家族内校正。

### 6.1 Clinical-complete 的预定义 overall 对比

差值方向均为 `right − left`。

| 对比 | Δ complete | left-only / right-only | raw McNemar p | coherent Holm q | stratified bootstrap 95% CI |
|---|---:|---:|---:|---:|---:|
| Collapse3c → Multistance | −0.12pp | 22 / 21 | 1.000 | 1.000 | [−1.75, 1.50]pp |
| Collapse3c → Forest | −1.88pp | 37 / 22 | .0674 | .6070 | [−3.75, 0.00]pp |
| Collapse3c → IMPC | −3.00pp | 49 / 25 | .00708 | .0708 | [−5.00, −0.88]pp |
| E7 → v0 | −1.25pp | 21 / 11 | .1102 | .8815 | [−2.62, 0.12]pp |
| Forest → E7 | +0.75pp | 30 / 36 | .5386 | 1.000 | [−1.25, 2.75]pp |
| Forest → B06 | −0.25pp | 26 / 24 | .8877 | 1.000 | [−2.00, 1.50]pp |
| B06 → E7 | +1.00pp | 28 / 36 | .3817 | 1.000 | [−1.00, 3.00]pp |
| B07 → E7 | +1.50pp | 26 / 38 | .1686 | 1.000 | [−0.38, 3.50]pp |
| B07 → B06 | +0.50pp | 28 / 32 | .6989 | 1.000 | [−1.38, 2.38]pp |
| Forest → Lite | −0.12pp | 20 / 19 | 1.000 | 1.000 | [−1.62, 1.38]pp |

上述 overall coherent Holm 家族没有 survivor。Collapse3c–IMPC 的原始效应
最强，但校正后 `q=.070843`，应写成“有方向一致、病例级支持的候选机制”，
不能写成确认性胜出。

最终统计合同预定义并分别冻结 overall、DA、MCR 三个相干十对比家族；其中 MCR
内 Collapse3c 相对 IMPC 高 5.50pp，未校正 95% CI [1.75, 9.25]pp，raw
`p=.004562`，Holm `q10=.045615`。ALL/DA/MCR 混合 30-row 校正仅作为保守
敏感性（同一对比 `q30=.136846`），不得取代预定义家族，也不得根据是否跨过
.05 事后切换合同。MCR 信号是家族内证据，不是跨 benchmark 的胜者证明：
`MCR delta − DA delta` 为 −5.00pp，未校正 bootstrap 95% CI
[−9.25, −0.75]pp、bootstrap `p=.022849`，但十交互 Holm `q=.228489`。

相反，legacy-chain 产生多项显著排序：Forest 相对 Collapse3c +5.50pp，
`q=.000352`；IMPC 相对 Collapse3c +5.38pp，`q=.00173`；E7 相对 Forest
−6.38pp，`q=.0000328`。这些显著差异没有在 clinical-complete 中复现，直接
证明 substring/parent 偏好能制造统计上很“漂亮”但临床对象错误的排名。

Partial 也不是噪音：E7 相对 B07 低 5.38pp，30-test endpoint-wide
`q=.0147`；相对 B06 低 5.12pp，`q=.0168`。这描述的是 B06/B07 更容易落在
兼容 family/component，而不是它们更准确。

### 6.2 Task 与 bootstrap 排名

DA task 中 Forest→E7 为 −6.75pp（raw `p=.0168`，Holm `q=.1679`）；MCR
task 中 Collapse3c→IMPC 为 −5.00pp（raw `p=.0169`，`q=.1686`）。均未通过
家族校正。

10,000 次分层 case bootstrap 显示名次也不稳定：DA clinical-complete 中
Multistance mean rank 2.53，成为并列第一的概率 .414、唯一第一 .306；MCR 中
Collapse3c mean rank 1.51，并列第一 .678、唯一第一 .604。它们是当前九臂开发
宇宙中的相对稳定性，不是对未来病例或新模型的 universal rank 保证。

## 7. Reference-identifiability 揭示“测量难”与“输出残缺”

| Scope | unique full reference | non-unique full |
|---|---:|---:|
| ALL | 455/800 = 56.88% | 345/800 = 43.12% |
| DA | 285/400 = 71.25% | 115/400 = 28.75% |
| MCR | 170/400 = 42.50% | 230/400 = 57.50% |

九臂在 unique-full 病例上的 complete 为 18.02%–21.54%，在 non-unique 上仅
4.35%–7.54%。最终 artifact 对每个 scope 用 slice-fixed case bootstrap 给出
interaction CI/p，并在各十对比家族内做 Holm；没有任何 arm×identifiability
交互通过校正。ALL 中最强的 E7→v0 交互为 −3.22pp，未校正 bootstrap
`p=.01545`，Holm `q=.1545`。所以以下方向翻转只能作为待验证机制：

- `v0 − E7` 在 unique-full 为 −2.64pp，在 non-unique 为 +0.58pp，交互
  −3.22pp；这是“E7 增益可能更集中于 reference 明确病例”的待验证机制；
- `Forest − Collapse3c` 在 unique-full 为 −3.08pp，在 non-unique 为
  −0.29pp；它提示 Collapse3c 的对象保留差异可能主要位于可辨病例；
- `IMPC − Collapse3c` 在 unique-full 为 −3.30pp，在 non-unique 为
  −2.61pp，方向较一致，说明 IMPC 的压平并不只是 reference 过特异造成。

尤其 DA 的 71.25% identifiability 与仅 2%–4% complete 同时出现，排除了“低分
主要因为 benchmark reference 不可辨”的简单解释。DA 的主要瓶颈是候选与
selector 把复合对象降格成 parent/component；MCR 的低 identifiability 则要求
报告条件化能力，避免把 benchmark 末端特异性当病例唯一真相。

## 8. 关系转移分解：平均分背后的双向机制

仅报 Δaccuracy 会把同一模块的 rescue 与 harm 相互抵消。下表统计 800 个配对
病例中的完整关系转移；`specificity/object rescue` 是 right 臂的收益，
`scope compression/catastrophic substitution` 是 right 臂的损失。

| 对比 | 无关系变化 | specificity rescue | object rescue | scope compression | catastrophic substitution | Δ complete (right−left) |
|---|---:|---:|---:|---:|---:|---:|
| Collapse3c → Multistance | 675 | 11 | 10 | 7 | 15 | −0.12pp |
| Collapse3c → Forest | 586 | 7 | 15 | 15 | 22 | −1.88pp |
| Collapse3c → IMPC | 572 | 6 | 19 | 17 | 32 | −3.00pp |
| E7 → v0 | 670 | 3 | 8 | 14 | 7 | −1.25pp |
| B06 → E7 | 569 | 21 | 15 | 8 | 20 | +1.00pp |
| B07 → B06 | 586 | 15 | 17 | 13 | 15 | +0.50pp |

### 8.1 Forest/IMPC：稳定 parent 与对象压平并存

Forest 并非“只会压平”。相对 Collapse3c，它能把 `CARASIL syndrome` 的冲突
亚型纠正为 `HTRA1-related hereditary CSVD`，也恢复 organizing pneumonia 与
complex odontoma。但同一模块又把 Surfer's myelopathy 压成 spinal cord injury，
把 COVID-19 换成 RSV，把 ischemic colitis 换成 ulcerative colitis。其
legacy-chain +5.50pp、clinical-complete −1.88pp 的反向结果，正是稳定常见 parent
获得 substring 奖励、完整对象同时丢失的综合表现。

IMPC 的双向幅度更大：它恢复 Rowell syndrome、HFLT、Netherton syndrome，
却把 rheumatoid meningitis 换成 neurosarcoidosis、visceral leishmaniasis 换成
tuberculosis、starvation colitis 换成 ulcerative colitis。32 个 catastrophic
substitution 超过 19 个 object rescue；不能把它的 legacy-chain 高分解释成更强
诊断能力。

### 8.2 Multistance：均值近零不等于机制等价

Collapse3c 与 Multistance 的 complete 仅差 1/800，但仍有 125 个病例发生关系
类别变化。Multistance 恢复 Phaeohyphomycosis、Netherton syndrome 与 scar
endometriosis，同时丢失 Surfer's myelopathy、rheumatoid meningitis 和 cryptogenic
organizing pneumonia。均值“打平”掩盖了高 churn；临床部署需要按对象类型识别
何时启用多视图，而不是据 aggregate tie 宣布两者可互换。

### 8.3 E7、B06、B07：specificity rescue 与风险尾

相对 E7，v0 少 10 个 complete；其损失集中在 unique-full 病例。E7 能恢复 scar
endometriosis、familial cerebral cavernous malformations、myopericarditis、
compound odontoma 等 specificity，但也会把 starvation colitis 推成 infectious
colitis、把 organizing pneumonia 换成 Pneumocystis pneumonia。它的机制是更敢于
选择特异对象，而非单调安全改进。

B06→E7 同时出现 36 个 specificity/object rescue 与 28 个
compression/catastrophic loss，净增仅 8 个 complete。B06 的 partial 为 35.00%，
明显高于 E7 的 29.88%，说明 B06 更常“软着陆”在正确 family；E7 用一部分软着陆
换取完整 specificity，也承担更长的错对象尾部。B07→B06 的两类流量几乎相消，
解释了二者 complete 只差 0.50pp、但具体病例并不稳定一致。

## 9. 历史 leaderboard 的端点迁移

原 `leaderboard_400.json` 的 `Concept` 不是一个共同端点：普通 run arms 使用
champion 的 `dc.match`；B06/MAC 使用 supervisor-stage hard hit；B07 使用
diagnose-stage hard hit。后两者甚至可能给后续分号诊断记分，而最终 champion 已
改变。

v2 迁移因此同时保留：

- `*_historical_legacy_chain`：原始数值，只用于复现；
- `*_legacy_chain`：统一对最终 pre-projection champion 重放；
- 全 800 的五端点 canonical 表与新的配对统计。

普通可比臂的 historical 与 unified chain mismatch 为 0，task mismatch 为 0；
stage-specific 四个差异是预期且已明示：B07 DA 26.25%→21.25%、MCR
28.25%→21.25%；MAC/B06 DA 33.00%→24.50%、MCR 31.50%→24.00%。今后不得
把旧 `Concept` 列作为同质 accuracy 横向排序。

## 10. 能力画像与下一步决策

- **Collapse3c**：当前 complete 最高，擅长保留病因、解剖、时间、stage 与
  composite；弱点是常见 parent 表面不稳定，并非所有具体化都正确。
- **Multistance**：complete 与 Collapse3c 几乎相同，safe-exact 最高；优点是
  个别稀有对象恢复，缺点是高 churn 与灾难替换抵消增益。
- **Forest**：固定池证据整合与稳定 parent 强，coverage 最高；但 legacy-chain
  优势显著高估其完整对象能力，需显式防止 scope compression。
- **IMPC**：能恢复部分稀有对象，但 catastrophic tail 最大，不能凭旧 Concept
  高分选为默认骨干。
- **E7**：相对 v0 的收益在点估计上集中于 reference 明确病例，具备
  specificity rescue；但交互未获乘数校正确认，且代价是更激进的错对象尾部。
- **B06/B07**：partial/coverage 较高，适合作为保留 family 的安全候选源；若直接
  作为 champion，欠特异与 stage/champion 端点错位会夸大表现。

因此默认评估顺序为：以 `clinical-complete × reference-identifiability` 做能力
主分析；MCR 开发循环采用校准 task judge；safe-exact 做冻结回归下界；partial
单独报告对象压平；legacy-chain 仅用于历史兼容和误差诊断。

## 11. 局限与可证伪条件

1. Clinical-complete 是相对记录 reference 的对象等价，不是无条件现实真值；
   non-unique reference 必须条件化报告。
2. 人工审计虽覆盖全 800，但仍有一个关系保留 uncertain；任何重编码都必须留下
   override 理由和版本哈希。
3. 九臂来自同一开发宇宙，bootstrap rank 不代表外部泛化；新增模型需在同一冻结
   800 例合同下重放。
4. MCR task judge 的高校准不能外推到 DA mapper，也不能外推到未审的开放域输出。
5. 任一新模块若声称提升能力，必须同时证明：complete 增加不是 partial/mapper
   重编码；unique-full 病例收益不被 catastrophic tail 抵消；配对 contrast 在预先
   冻结的 multiplicity family 中仍成立。

## 12. 可复现产物

- `unified_800/five_endpoint_replay.jsonl`：7,200 行统一五端点 replay；
- `unified_800/leaderboard.json` / `.csv`：ALL、DA、MCR 五端点表；
- `unified_800/endpoint_calibration.json`：proxy 对 clinical-complete 的校准；
- `unified_800/paired_contrasts.json` / `.csv`：paired McNemar、Holm 与分层 bootstrap；
- `unified_800/relation_transition_matrices.json`：关系转移与机制计数；
- `unified_800/trajectory_endpoint_transitions.jsonl`：逐病例、逐对比轨迹；
- `unified_800/identifiability_effect_modification.json`：可辨识性效应修饰；
- `unified_800/clinical_interaction_inference.json`：family 与 identifiability
  交互的 case-bootstrap 推断、命名家族与 Holm；
- `unified_800/rank_stability.json`：10,000 次分层 case bootstrap 排名；
- `unified_800/root_audit/`：blind cards、三批草稿、根复核、override 与最终决定；
- `analysis/backbone_v1/mosaic_eval/leaderboard_400_v2.json`：历史命名迁移；
- `analysis/mechanism_v2/e2_unified_replay.py`：统一重放和统计实现。
