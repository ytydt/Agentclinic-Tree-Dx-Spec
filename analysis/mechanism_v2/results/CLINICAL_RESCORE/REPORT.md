# 换尺子：MultiStance 损失解剖在冻结 clinical-complete 端点上的重算

脚本 `analysis/mechanism_v2/clinical_rescore.py` + loader `analysis/mechanism_v2/clinical_endpoint.py`。
**零 LLM 调用。** 800 例开发集（DA 400 / MCR 400），另含 contractfix 臂的 holdout-400 配对。

## 0. 一句话结论

**DA 和 MCR 不是同一个问题，而旧尺子把这件事完全盖住了。** 在真端点上：

- **DA 是补全问题。** 210/400（52.5%）冠军是 `partial_parent_or_component`——对但不完整的父类，
  且其中 207 例池内没有任何更好的席位；选择层总共只值 **7 例**。
- **MCR 是选择问题。** **63 例**池内已有完整标签却没赢（52 例在决赛之前就丢了），
  完整标签的 ledger rank 中位数只有 **2**；补全梯只有 8–10 例。

顺带两条更正：D 的契约修复在真端点上**完全中性**（DA 0.030→0.030、MCR complete 0.285→0.295，
p=0.625）；step 0 那个"`not_proposed` 43% 是任何比较器都碰不到的上限"是旧尺子的产物。

## 1. 仪器

临床判定不绑定臂，按 `(case_key, canonical_label)` 存在两个冻结源里：
`CEILING_POOL_CENSUS/panel/three_model_adjudicated_panel.jsonl`（C0 三模型盲评，19,406 条可用）
与 `ALL_ARM_ENDPOINT_MIGRATION/final/five_endpoint_replay.jsonl`（补 2,250 条）。键构造复用
`FrozenExactSynonymBridge` 与归档评估器同一套 `relation_key` 语义。合计 21,656 条，
跨源冲突 1,214 条（默认保留 C0 值，`--drop-source-conflicts` 为敏感性开关）。

**覆盖率（零调用）：** MultiStance 冠军 800/800；池内标签 DA 3618/3618、MCR 3500/3500；
contractfix 臂冠军 400/400。**全部 100%。**

**跨源冲突敏感性：** 丢掉那 1,214 条冲突键后，DA clinical-complete 0.0425 不变、
池内完整暴露 0.0600 → 0.0575；MCR complete 0.2600 不变、选择损失 63 → 62；
两族的补全梯（210/91/45/30 与 49/14/10/8）**完全一致**。本报告的结论不依赖冲突处理方式。

**必须随结论携带的限度：** 三模型面板在 E2 隐藏哨兵上（n=2601）对五分类关系的
exact accuracy **0.7082**、Gwet AC1 **0.6544**；只有退化成 `safe_exact` 二分类才是 1.000。
而 `complete_equivalent` / `partial_parent_or_component` 恰是最难的那条边。
truth tier 是 **model-panel sensitivity，不是人工根真值**；800 例是反复使用的开发集，
development-not-confirmation。

## 2. 两把尺子并列

| 端点 | DA (n=400) | MCR (n=400) |
|---|---:|---:|
| legacy-chain top-1 | 0.2325 | 0.2200 |
| **clinical-complete top-1** | **0.0425** | **0.2600** |
| complete ∪ compatible-partial top-1 | 0.5675 | 0.3825 |
| legacy-chain 池召回 | 0.6175 | 0.4725 |
| **池内存在完整标签（complete exposure）** | **0.0600** | 0.4175 |

DA 的两个缺口都极大：top-1 上 0.2325 vs 0.0425，池召回上 0.6175 vs **0.0600**。
也就是说 DA"池召回 62%"这件事在临床意义上几乎不存在——**94% 的 DA 病例，
~9 宽的池子里没有任何一个临床完整的标签**。MCR 相反，legacy-chain 反而**低估**
（0.22 vs 0.26），池内完整暴露率 41.75%。

旧尺子在 DA 上到底在记什么：93 例 legacy 命中（= 旧分类的 DA `ok`）里 **83 例的临床关系是
`partial_parent_or_component`**、9 例 complete、1 例 manifestation。**89.2% 是粗父类信用。**
MCR 的 88 例 legacy 命中里 71 例 complete（80.7%）、16 例 partial——旧尺子在 MCR 上基本可用。

## 3. 新的损失态分布（取代 `multistance_loss_round`）

旧分类无法表达真端点下的主导态"冠军是对但不完整的父类"，因为 `dc.match` 把它记成命中。

| 态 | DA | MCR |
|---|---:|---:|
| `complete_champion`（成功） | 17 | 104 |
| **`partial_champion`**（对但不完整） | **210** | 49 |
| `complete_lost_in_finals` | 1 | 7 |
| `complete_lost_before_finals` | 3 | 48 |
| `no_complete_in_pool`（生成天花板） | 169 | 192 |

**DA 的选择层按本表只丢 4 例（1+3），计入 partial 冠军后共 7 例（§5）。**
DA 的全部差距在生成：169 例池里根本没有完整标签，另外 210 例冠军是正确父类而完整标签同样
没被生成过（complete exposure 仅 6% = 24 例，其中 17 例已经赢了）。
**MCR 按本表丢 55 例、计入后共 63 例**，其中 48 例在进决赛之前就丢了。

### 3.1 旧 loss round 与新态的交叉表：`not_proposed` 上限是旧尺子的产物

| 旧 round | DA 组成 | MCR 组成 |
|---|---|---|
| `ok` | partial 83 / **complete 仅 9** / no_complete 1 | complete 71 / partial 16 / lost_before 1 |
| `final_drop` | partial 34 / no_complete 33 / complete 3 / lost 2 | no_complete 13 / complete 10 / partial 6 / lost 12 |
| `group_drop` | no_complete 46 / partial 44 / lost_before 2 / complete 1 | **lost_before 30** / no_complete 27 / complete 8 / partial 5 |
| `not_proposed` | no_complete 89 / **partial 49 / complete 4** | no_complete 152 / partial 22 / **complete 15** / lost 12 |

两条读数：

1. **DA 的 93 例 legacy `ok` 里只有 9 例是临床完整的**（9.7%），83 例是粗父类。旧尺子在 DA 上
   测的基本不是诊断正确性。（181 是 DA+MCR 合计，勿混用。）
2. **`not_proposed` 不是上限。** 旧分析把 DA 142 / MCR 201 例判为"金标从未被提出、任何比较器
   都碰不到"，但其中 DA 53 例（partial 49 + complete 4）、MCR 37 例（partial 22 + complete 15）
   的冠军在临床上是正确父类甚至完整——只是 `dc.match` 没匹配上。step 0 §6 那句"不可把
   `not_proposed` 343 例（43%）的上限归给任何比较器改动"需要作废：真正的生成天花板是
   `no_complete_in_pool`，DA 169/400（42.25%）、MCR 192/400（48.0%），量级相近但**是另一批病例**。

## 4. DA：补全的靶（真端点）

对 210 例 `partial_champion` 逐级收紧（判据同 `FINALS_LOSS_ANATOMY`，但作用对象是**已知不完整**
的冠军，不再是被 legacy-chain 记过分的席位）：

| 阶梯 | DA | MCR |
|---|---:|---:|
| `partial_champion` | 210 | 49 |
| 冠军是参照的真词法子集（可靠加词得到） | 91 | 14 |
| ⤷ 且加的词属表层轴 | **45** | 10 |
| ⤷ 且加词 ≤ 2 个 | **30** | 8 |
| 其中池内**没有**任何完整标签（补全是唯一出路） | 207 / 210 | 41 / 49 |

样本（`case_id | 冠军 → 参照 | 加的词`）：

```
 15 | Histoplasmosis        → Primary oral histoplasmosis            | primary, oral
 36 | Cutaneous cryptococcosis → Primary cutaneous cryptococcosis    | primary
 60 | Atrial Septal Defect  → Ostium secundum atrial septal defect   | ostium, secundum
111 | Lichen planus         → Inverse lichen planus                  | inverse
128 | Angiosarcoma          → Cutaneous angiosarcoma                 | cutaneous
149 | Giant Cell Tumor      → Giant cell tumor of soft tissue        | soft, tissue
227 | Amyloidosis           → Bullous amyloidosis                    | bullous
```

这些正是 anatomy / subtype_histology 轴上的单修饰词补全。**207/210 例池内没有替代的完整标签，
所以重排序在这一层无效，只有纵向补全能动它。** 对照基线 complete = 4.25%（17/400），
可寻址 30–45 例意味着这条路的名义上限是 4.25% → 11.5%–15.5%。

## 5. MCR：选择的靶（真端点）

靶的定义是"**冠军不完整、但池内存在完整标签**"，即席位选择本可以改善的全部病例。
它与 §3 的态表这样对齐（两处口径不同，不是矛盾）：

| | DA | MCR |
|---|---:|---:|
| §3 的 `complete_lost_in_finals` + `complete_lost_before_finals` | 4 | 55 |
| 加上：`partial_champion` 且池内另有完整标签 | +3 | +8 |
| **= 选择层可干预总数** | **7** | **63** |

差额来自 §3 的态表按**冠军**归类（partial 冠军优先记为 `partial_champion`，即便池内另有完整
标签），而本节按**池内是否还有更好的席位**归类。同一批病例不重复计入两条干预路径：那 3/8 例
既可补全也可重排序，在 §4 的梯子里也出现过。

63 例的结构（52 例决赛前丢、11 例决赛内丢）：

| 量 | 值 |
|---|---:|
| 完整标签的 ledger rank 中位数 | **2** |
| 已经落在当前决赛宽度内（决赛看见了却没选） | 29 / 63 |
| 平铺 top-N 覆盖到完整标签所需宽度 | top2: 22、top3: 35、top4: 42、**top5: 50**、top6: 53、top8: 57、top10: 62 |
| 完整标签所在 stance 组的平均组内候选数 | 4.30 |
| 完整标签所在组分布 | commit 50、mechanism 7、coverage 5、unassigned 4 |

三条读数：

1. **完整标签排得很前（中位 rank 2），而当前决赛只有 ~2.65 席。** 平铺到 top-5 就能暴露 50/63。
2. **50/63 落在 `commit` 组**，而 commit 是系统性最大的组（step 0 测得均 4.99）。所以 MCR 的
   损失形态是"完整标签挤在拥挤的 commit 组里，而该组只有一个提名席位"。这比 step 0 试过的
   "核分组"是一个**更具体也更可测**的机制：按组内候选数分配席位，而不是一组一席。
3. 但 29/63 是决赛**已经看见**完整标签仍选了别的——那 29 例开宽度无效，需要比较器本身改变。

注意这与 step 0 的结论并不矛盾而是补充：step 0 说"同席位数下核分组不优于平铺 sham"，
本节说"平铺开宽在 MCR 的真端点上有 50/63 的暴露空间"。这两件事从未在真端点上被测过——
`MULTISTANCE_CORELIFT_PROBE` 的 `union` 臂（平铺 9 宽）只报了 legacy-chain concept。

> ### 更正（2026-08-20）：上面三条读数里，读数 2 作废，读数 1 与 3 需重述
>
> 写 MCR 预注册时核查 `src/agentclinic_tree_dx/aphhm_c.py`，发现**读数 2 依赖的机制在冻结臂里
> 不存在**：
>
> - 冻结臂 `mode='multistance'`，而 `split_final = (mode == "multistance_split")` 为 `False`，
>   `enforce_group_quota` 也为 `False`。**因此没有 `AphhmCStanceNomination` 这一路提名调用，
>   不存在"一组一个提名席位"这回事。**
> - 实际只有**一次** `AphhmCFrontierSelector` 调用，payload 是
>   `{vignette, shortlist, groups}`；multistance 属 `selector_all_concepts`，所以 `shortlist`
>   是**完整 ledger 的平铺全表**，实测均 **8.75** 宽（中位 9）。`finalists` 是这同一次响应里
>   模型**自报的中间量**，不是装置施加的配额。机械核验：400/400 例的 `frontier_selector` 键恰为
>   `(champion, finalists, runner_up, why)`，**不含 `nomination`**。
>
> 因此：
>
> - **读数 2 作废。** "按组内候选数分配席位"这个提议没有作用对象，不得据此设计实验。
> - **读数 1 的"暴露"用词错误。** 那 63 例里完整标签**自始至终都在 payload 里**，从未被藏起来；
>   "平铺 top-5 覆盖 50 例"的正确含义是**截断到 top-5 时完整标签仍被保留**，不是新增暴露。
>   本表"平铺 top-N 覆盖所需宽度"一行应读作**保留率**而非覆盖率。
> - **读数 3 的 29 是排名代理量**（`best_rank < len(finalists)`），不是集合成员关系。
>   按成员关系实测，完整标签真正出现在自报 finalists 里的只有 **11/63**。但由于全部 63 例的
>   payload 都含完整标签，读数 3 的结论其实适用于**全部 63 例**：加宽在这一层是空操作。
>
> **干预方向由此反转：这一层唯一剩下的杠杆是删干扰项（截断），不是加宽或重分席位。**
> E5 测得 MCR 自己的宽度斜率是 **−6.33pp/候选**（DA −2.87），当前均宽 8.75 正在这条斜率的作用区。
> 重新设计后的实验见 [`MCR_SELECTOR_TRUNCATION/PREREGISTRATION.md`](../MCR_SELECTOR_TRUNCATION/PREREGISTRATION.md) §0。
>
> 附带的零调用测量（同见该预注册 §3.1/§3.2）：按"独有 support span"构造的**证据资格准入**规则
> 均宽 4.10、保留完整 129/167、必回归 5，被朴素**平铺 top-3**（3.00 / 136 / 3）在三个维度上
> 全面支配——这是"平铺 sham 打败结构规则"的第三次独立复现。
>
> ### 追记（2026-08-21）：截断实验已执行完毕，结论是本节的 63 例**不能靠改名单拿回来**
>
> [`MCR_SELECTOR_TRUNCATION/REPORT.md`](../MCR_SELECTOR_TRUNCATION/REPORT.md)：截断到 5 宽
> 相对冻结是 **−2 例**（p = 0.754），截断到 3 宽是 **−5 例**；越窄越差。删掉 8.54 个候选里的
> 3.54 个，**冠军只在 15/167（9.0%）例上改变**，50 例"完整标签仍留在名单上"的病例里
> **只兑现 4 例（8%）**——完整标签就在更短的名单上，比较器依然选了别的。
>
> 因此本节那张表里的"平铺 top-N 保留 22/35/42/50/53/57/62"是**结构可达性，不是可实现增益**；
> 引用时不得当作头寸。本节读数 3（"需要比较器本身改变"）原本只针对已进决赛的部分，
> 现在**在全部 63 例上得到确证并推广**。这一层剩下的杠杆在比较器内部（E4 的证据整合方向），
> 不在候选集合。
>
> ### 再追记（2026-08-21）：63 例的机制已定位到**证据分配层**，不是比较器判断失误
>
> [`MCR_SELECTION_LAYER_AUDIT`](../MCR_SELECTION_LAYER_AUDIT/REPORT.md)（零调用）与
> [`MCR_EVIDENCE_SYMMETRY_GATE`](../MCR_EVIDENCE_SYMMETRY_GATE/REPORT.md)（128 调用）把
> "比较器内部"进一步收窄。**63 例的数值不变**，机制归因更新如下：
>
> - **不是粒度退让。** 按临床关系分解：`not_equivalent` 25、`conflicting_subtype_or_scope` 17、
>   `manifestation_or_related` 13、`partial_parent_or_component` 仅 **8**。主导模式是放着
>   shortlist 里的精确匹配不选、去选临床上不同的同族兄弟。
> - **比较器是忠实执行了一份被污染的输入。** 正确候选相对被选冠军系统性弱势：`for` span
>   更少 48/63（均数 2.29 vs 3.84），带 `against` 42/63 vs 28/63，payload 位置更靠后 55/63。
>   tournament prompt 的判据正是"权衡 for 与 against、偏好解释最多决定性发现者"。
> - **该不对称主要是证据写法的产物。** 每候选独立、对彼此盲的对称重推使其基本消失
>   （`for` 更少 48 → 28，均数差 1.56 → 0.59，符号检验 p = 0.0031），且收窄几乎全部来自
>   **冠军一侧缩水**（3.84 → 2.81），并集中在 payload 位置 0 的冠军（Δ −1.25 vs 位置 >0 的
>   −0.53）。stance 调用在一趟里既提候选又写证据，系统性地给最先提出的候选堆砌支持 span。
> - **选择层可提取信号已接近榨干。** 同一 payload 上：比较器 104/167，盲取位置 0 得 93/167
>   （零调用），盲取 `for` 最多者 59/167；比较器与位置 0 一致率 130/167 = 77.8%。整个 LLM
>   比较步骤的边际价值是 **+11 例**。且生成序已是最优可得排序——8 个离线替代排序在 dev 与
>   holdout 上全部掉点。
>
> 因此 §8.3 那句"修好 MCR 的选择层，其 task 收益量级远大于把补全搬到 MCR"在**头寸上仍然成立**
> （池内完整标签 30/33 是 task 正确的），但**修法**必须改：靶是逐候选证据分配的次序性偏置，
> 不是比较器判据、不是名单宽度、不是候选集来源。后者三条均已被实验或零调用审计否掉。
>
> ### 三追记（2026-08-21）：证据分配层也已被否，MCR 选择层项目结束
>
> [`MCR_EVIDENCE_REASSIGNMENT_V1`](../MCR_EVIDENCE_REASSIGNMENT/REPORT.md)（1801 调用，零 panel）
> 把去偏置后的证据喂回冻结选择器：`sym_evidence − frozen` = **−6 例**（p = 0.362），
> `sym_shuffle − shuffle_only` = **−1**（p = 1.000），触发预注册的否证形态。干预在机制上生效
> （24% 冠军改变、位置 0 顺从率 77.8% → 67.7%）但方向不占优（救回 12、弄坏 18）。
>
> 至此 MCR 选择层输入空间的四个维度全部实测：候选集来源 **−13**、名单宽度 **−2/−5**、
> payload 顺序 **−11**、逐候选证据 **−6**。**全部中性或更差**，冻结配置在其输入空间上是局部最优。
> 机制上的统一解释是：生成器写给最有信心候选的"膨胀"证据与生成序，是同一条**置信通道**的两种
> 表现，抹平偏置即抹掉真信息。
>
> 所以本节那 63 例（以及 §8.3 由它推出的 task 头寸）**不应再作为选择层或证据层的可干预头寸引用**。
> 它仍是真实的头寸，但只能从**生成层**去取——需要能把正确诊断排得更前的生成器。审计给出该层
> 边界：比较器相对"盲取 payload 位置 0"只值 +11 例（104 vs 93），池内可达上限 167。

## 6. D 的契约修复在真端点上是中性的

holdout-400 配对（base = 冻结 MultiStance，fix = 加两个开关）：

| 端点 | DA base → fix | McNemar | MCR base → fix | McNemar |
|---|---|---|---|---|
| clinical-complete | 0.030 → 0.030 | 1 vs 1，p=1.00 | 0.285 → 0.295 | 1 vs 3，p=0.625 |
| complete ∪ partial | 0.565 → 0.560 | 3 vs 2，p=1.00 | 0.390 → 0.415 | 1 vs 6，p=0.125 |
| 池内完整暴露 | 0.040 → 0.040 | 0 vs 0，p=1.00 | 0.470 → 0.475 | 0 vs 1，p=1.00 |

**legacy-chain 上那个 MCR concept +2.5pp 没有在真端点上留下来。** 这证实了
`CONTRACT_FIX_VERIFY` §2 的限定，也确证 step 0 的判断：这是**契约债/正确性修复，不是性能杠杆**。
它仍然应当保留（它消除了嵌合标签与父子折叠），但不得作为收益写入任何结论。

## 7. 跨臂：真端点把整个方法族压进一条窄带，且 partial 失败态是全族共有的

临床判定不含臂身份，所以**全部 9 个 full-800 归档臂都能零调用重新记分**。

### 7.1 DA（dev-400，按 clinical-complete 降序）

| 臂 | 端点覆盖 | clinical-complete | rate | `partial_parent` | legacy-chain | legacy rate | ≤2词补全梯 |
|---|---:|---:|---:|---:|---:|---:|---:|
| **multistance** | 1.00 | **17** | **0.0425** | 210 | 93 | 0.2325 | 30 |
| lite | 1.00 | 16 | 0.0400 | 215 | 103 | 0.2575 | 32 |
| collapse3c | 1.00 | 15 | 0.0375 | 211 | 80 | 0.2000 | 25 |
| e7 | 0.91 | 15 | 0.0375 | 183 | 81 | 0.2025 | 29 |
| forest | 1.00 | 14 | 0.0350 | 213 | 112 | 0.2800 | 31 |
| impc | 1.00 | 13 | 0.0325 | 211 | 117 | 0.2925 | 29 |
| B07 | 0.78 | 11 | 0.0275 | 165 | 85 | 0.2125 | 27 |
| v0 | 0.84 | 8 | 0.0200 | 173 | 70 | 0.1750 | 24 |
| B06 | 0.93 | 7 | 0.0175 | 200 | 98 | 0.2450 | 30 |

### 7.2 MCR（dev-400）

| 臂 | clinical-complete | rate | `partial_parent` | legacy rate |
|---|---:|---:|---:|---:|
| collapse3c | **107** | 0.2675 | 52 | 0.2225 |
| multistance | 104 | 0.2600 | 49 | 0.2200 |
| forest | 93 | 0.2325 | 66 | 0.2525 |
| e7 | 93 | 0.2325 | 42 | 0.2025 |
| v0 | 92 | 0.2300 | 52 | 0.2125 |
| B06 | 91 | 0.2275 | 61 | 0.2400 |
| lite | 90 | 0.2250 | 55 | 0.2175 |
| impc | 85 | 0.2125 | 64 | 0.2375 |
| B07 | 83 | 0.2075 | 47 | 0.2125 |

### 7.3 三条读数

1. **DA 上没有任何臂间排序是可支撑的。** 9 个臂的 clinical-complete 落在 7–17/400
   （1.75%–4.25%），全覆盖的 5 个臂落在 13–17/400——**4 例宽**，而面板五分类准确率是 0.7082。
   与此同时 legacy-chain 的跨度是 70–117/400（**47 例宽**）。旧尺子在 DA 上排的是别的东西。
   在全覆盖的 5 个臂里 Spearman(legacy, clinical) = **−0.700**（10 对里 8 对反向），
   但 n=5、p≈0.19，**只能说两把尺子的排序无关，不能声称系统性反向**。

2. **MultiStance 与 Collapse3c / Forest 在真端点上无法区分。** 配对精确 McNemar（同 400 例）：

   | 对比 | 计数 | 只有对方命中 | 只有 ms 命中 | p |
   |---|---|---:|---:|---:|
   | DA ms vs collapse3c | 17 vs 15 | 6 | 8 | 0.79 |
   | DA ms vs forest | 17 vs 14 | 4 | 7 | 0.55 |
   | MCR ms vs collapse3c | 104 vs 107 | 16 | 13 | 0.71 |
   | MCR ms vs forest | 104 vs 93 | 16 | 27 | 0.13 |

   **四个对比全部不显著。** 此前基于 concept / legacy-chain 观察到的"MultiStance 与
   Collapse3c 的差距"在临床端点上不存在。

3. **`partial_parent` 是全族共有的失败态，不是 MultiStance 的特性。** DA 上全覆盖的 5 个臂
   分别是 210 / 215 / 211 / 213 / 211，≤2 词补全梯 30 / 32 / 25 / 31 / 29。
   所以纵向补全**不是"让 MultiStance 追上某个基线"的修补，而是针对全族同构失败态的干预**；
   它作用在哪个底座上，几乎不影响可寻址规模。

## 8. task 端点：MultiStance 与 Collapse3c 在这里也不显著，但两族的杠杆完全不同

官方 task 判定（DA 选项投射准确率 / MCR 冻结 Prompt-7）同样按 `(family, case, label)` 存在
`ALL_ARM_ENDPOINT_MIGRATION/task_evaluator/`，5,240 条可用（丢弃 26 条冲突）。

> **覆盖率是部分的、而且各臂不同**：冠军覆盖 DA 0.663（ms）/ 0.675（c3c）/ 0.753（forest），
> MCR 0.745 / 0.753 / 0.823。一个 `(case, label)` 只有进过 CoreLift migration 的 task index
> 才有判定。**因此绝不能跨臂比原始 rate**，本节所有跨臂读数都是**限定在双方均有判定的病例上的
> 配对对比**。即便如此，"哪些病例被判定"本身仍是非随机子集，这是本节无法消除的限制。

### 8.1 配对跨臂（仅共同判定病例）

| 对比 | 共同 n | 对方 | MultiStance | 只对方 | 只 ms | p |
|---|---:|---:|---:|---:|---:|---:|
| DA vs collapse3c | 240 | 58 | 59 | 8 | 9 | 1.00 |
| DA vs forest | 245 | 54 | 58 | 11 | 15 | 0.56 |
| DA vs lite | 232 | 52 | 55 | 12 | 15 | 0.70 |
| DA vs impc | 233 | 52 | 54 | 10 | 12 | 0.83 |
| **MCR vs collapse3c** | 272 | **98** | 92 | **8** | **2** | **0.109** |
| MCR vs forest | 276 | 95 | 99 | 13 | 17 | 0.58 |
| MCR vs lite | 268 | 89 | 93 | 11 | 15 | 0.56 |
| MCR vs impc | 260 | 80 | 89 | 7 | 16 | 0.093 |

**八个对比全部不显著。** DA 上 MultiStance 与 Collapse3c 实际上相等（59 vs 58）。
唯一一处 Collapse3c 占优的是 **MCR，领先 6/272 = 2.2pp，不一致对 8 比 2，p=0.109**——
这大概是"MultiStance 在 task 上落后 Collapse3c"这一印象的来源，但它没有过显著性，
量级也只有 2pp。

### 8.2 clinical-complete 换不换得到 task 分，两族差别极大

| 族 | 冠军临床完整 → task 正确 | 冠军非完整 → task 正确 |
|---|---|---|
| DA | 7/11 = **0.636** | 60/254 = 0.236 |
| MCR | **87/87 = 1.000** | 15/211 = 0.071 |

**MCR 上 task ≈ clinical-complete**：临床完整则 task 必对（87/87），不完整则几乎必错（7.1%）。
**DA 上两者松耦合**：临床完整的冠军里仍有 4/11 拿不到 task 分，非完整的却有 23.6% 拿到——
DA 的选项投射把大量粗父类兜成了正确选项，也把一些正确诊断投错。

### 8.3 因此两族的 task 杠杆是不同的

**DA：补全有头寸，但只在 DA。** 严格臂的靶在各档上的当前 task 状态（dev-400）：

| 档 | 有 task 判定 | 其中已 task 正确 |
|---|---:|---:|
| `partial_champion` | 150 | 41（27.3%） |
| ⤷ 可重构 | 79 | 21 |
| ⤷⤷ 表层轴 | 40 | 7 |
| ⤷⤷⤷ **≤2 词（严格臂靶）** | **26** | **3（11.5%）** |

严格臂的靶**当前有 23/26 是 task 错的**，所以选项投射并没有替补全把粗父类兜住，
补全在 task 上确实有头寸（holdout-200b 上是 11 例判定里 9 例错）。

**MCR：补全几乎无用，选择才是杠杆。** MCR 的严格臂靶只有 3 例（判定 7 例中 4 例已正确）。
而 63 例选择损失里，池内那个完整标签**有判定的 33 例中 30 例是 task 正确的（90.9%）**。
DA 的 7 例选择损失同样是 4/4。

**把 §5 的 63 例与本节的 90.9% 放在一起：修好 MCR 的选择层，其 task 收益的量级远大于
把补全搬到 MCR。** 这也解释了 §8.1 里唯一那处 Collapse3c 占优为什么出现在 MCR——
MCR 的胜负由选择层决定，而 task 在 MCR 上几乎就是 clinical-complete 的同义词。

## 9. 可写与不可写

**可以写：**
- 临床判定覆盖 MultiStance 冠军 800/800、池标签 100%、contractfix 冠军 400/400，零调用。
- DA clinical-complete 4.25% / 池内完整暴露 6.00%；MCR 26.0% / 41.75%。
- DA 93 例 legacy 命中（= DA `ok`）里 83 例临床上是粗父类、仅 9 例临床完整。
- 新态分布与旧 round 的交叉表；`not_proposed` 中 DA 53 / MCR 37 例冠军其实临床正确或完整。
- DA 补全梯 210 → 91 → 45 → 30，且 207/210 池内无替代完整标签。
- MCR 63 例选择损失，完整标签 rank 中位数 2，top-5 覆盖 50 例，50 例在 commit 组。
- D 的修复在三个临床端点上均无显著变化。
- §7 的跨臂表：9 臂零调用重记分，DA 全覆盖 5 臂落在 13–17/400，`partial_parent` 210–215，
  MultiStance vs Collapse3c / Forest 四个配对对比全部不显著（p = 0.79 / 0.55 / 0.71 / 0.13）。
- §8 的 task 端点：八个配对跨臂对比全部不显著；MCR 上 clinical-complete → task 是 87/87，
  DA 上只有 7/11；严格臂靶当前 23/26 是 task 错的；MCR 选择损失的池内完整标签 30/33 是 task 正确的。

**不可以写：**
- **不可用 §7 声称任何臂优于另一臂**：DA 全覆盖 5 臂只差 4 例，远在面板噪声内。
  "MultiStance 在 DA clinical-complete 上第一"是排序位置的陈述，**不是优势的陈述**。
- 不可声称 legacy-chain 系统性反向排序：Spearman −0.700 但 n=5、p≈0.19。可写的是"两把尺子
  排序无关"。
- 不可把覆盖率 < 1.00 的臂（e7 / v0 / B06 / B07）与全覆盖臂直接比 rate：它们的分母里有
  未判定冠军，rate 被系统性低估。
- **不可报告 task 端点的跨臂原始 rate。** task 覆盖只有 0.66–0.82 且**各臂不同**
  （DA ms 0.663 vs forest 0.753），原始 rate 不可比。只能报 §8.1 的配对共同子集读数，
  且必须注明"哪些病例被判定"本身是非随机的。
- 不可把 §8.3 的"补全在 DA task 上有头寸"读成"补全会涨 task"：本节只测出靶当前是错的，
  **没有测**补全后投射会不会改判。
- 不可把 MCR 的 2.2pp（p=0.109）写成 Collapse3c 优于 MultiStance。
- 不可把面板判定当真值：五分类 exact accuracy 0.7082、AC1 0.6544。210 vs 17 这种量级远在
  噪声之外，但任何 ≤5pp 的对比都必须做面板误分类的敏感性分析。
- 不可把 §4 的 30–45 例读成预期收益：那只是"词法上可由加词得到且加的词像表层轴"，
  模型能否正确补出、补出后面板是否判 complete，本节都没测。
- 不可把 §5 的 top-5 覆盖读成"开宽到 5 席能涨 50 例"：暴露不等于转化，且 29/63 是决赛
  已见仍未选。
- 不可跨族合并 DA/MCR 报单一数字。
- 不可把本报告当确证：800 例是反复使用的开发集，且 truth tier 是模型面板敏感度。
- 不可据 §3.1 声称旧结论"全错"：旧尺子在 MCR 上与临床端点大体一致（71/88 命中为 complete），
  作废的只是 DA 上的读数与 `not_proposed` 上限那一条。

## 10. 复现

```bash
python3 analysis/mechanism_v2/clinical_endpoint.py          # 仪器自检
python3 analysis/mechanism_v2/clinical_rescore.py \
  --out analysis/mechanism_v2/results/CLINICAL_RESCORE
python3 analysis/mechanism_v2/clinical_rescore.py --drop-source-conflicts  # 敏感性
```
