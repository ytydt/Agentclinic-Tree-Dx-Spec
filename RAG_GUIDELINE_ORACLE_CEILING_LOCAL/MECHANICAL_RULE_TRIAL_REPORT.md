
# 11 例可分病例上的端到端试运行：检索 → 规则抽取 → 机械执行 → 失败追溯

> **2026-09-05 独立再审计更新：** 本文历史记录保留，但§34–35关于“逻辑保真改善”“抽取已达可用程度”“不是判据组的锅”及例74全局删除排除规则的因果解释，需要按[最新v2规则语义再审计](../analysis/mechanism_v2/results/POST_V2_RULE_SEMANTICS_AUDIT/REPORT.md)修订。新审计从原始缓存精确复原140,652条断言，检查组合/原子语义、程序执行、真实病例与测量误差。例74有证据的CPVT实际第10，报告第4来自空重复标签；仅删除其特定错误否决，两v2臂均恢复第1，全局删除却另行复活LQTS。旧top1/MRR是存在实体/粒度错误的`gold_labels_in_set`代理，不是clinical-complete。证据账本、确定性反例与复算脚本已随新报告提交。

上一轮 `MECHANICAL_RULE_FEASIBILITY.md` 是纯理论核验（无模型调用）。本轮把那套设计真的跑了一遍：在与审计完全同一份语料上重建索引，按假设条件化检索，用 LLM 按 schema 抽取断言与病例发现，再用**不含任何模型调用**的四层规则引擎给候选假设排序（层一硬排除、层二确诊确认、层三加权符合、层四幸存者定向比较；定义见 **§5.0**），最后把 26 条人工断言逐条追踪到它死在哪一级。候选集固定为 collapse3c 与 multistance 两方法实际提出的假设并集。

结论先行：**理论核验的检索侧预测被证实，表示侧预测被证伪。** 必要切片确实取得到（k=30 时 21/26，注入 oracle 后 25/26），LLM 也确实能把段落转成 schema（1,941 段 → 15,588 条断言，含 280 条 required_for/obligatory 与 297 条 excludes/obligatory）。但机械引擎在最优配置下只有 3/11 命中，默认配置 0/11；且**把检索换成完美 oracle，结果一格都没变**。失败不在检索，在三处：断言与病例发现之间的接合、"排除"在真实指南里根本不以排除形式书写、以及**断言之间没有任何显式连词**——指南原文里的合取 / 析取 / 条件 / m-of-n 只活在 `quote` 里，schema 一个都没保留。

## 一、试运行怎么搭的

**语料与索引。** 现成的 `data/corpus/*_index` 覆盖的是另一份快照（Merck 只收了 3,311/9,629 切片，PMC 版本也不同），在它上面检索失败会与索引缺漏混淆。因此在审计用的那 861,131 个切片上重建了一份混合索引：sklearn TF-IDF（185,959 维）+ MiniLM-L6 稠密向量（fp16，A100 上 5 分钟编码完），RRF 融合。切片不复制文本，按 (源, 字节偏移) 寻址回原始 jsonl。命中后按文档边界把切片与前后邻居拼成 passage 再送抽取——这是理论核验里"切片中位仅 36–154 token、多句判据常跨切片"那条的实现。

**两处模型调用，其余全机械。**

- `GuidelineAssertionExtractor`：每个 (passage, 焦点假设) 一次。它看不到 vignette、金标、候选集，因此产物可跨病例缓存（1,909 个缓存条目，第二个臂 1,941 次调用里 1,930 次命中缓存）。
- `CaseFindingExtractor`：每份 vignette 一次，看不到候选集与金标。

**四层引擎（无模型）。** 设计稿 `MECHANICAL_RULE_FEASIBILITY.md` §2.4；实现 `run_mechanical_engine.py`。F7/F8 只在进引擎前改断言，不改四层。层的触发条件、跳过条件、组求值与排序键见 **§5.0**；槽位合法取值见 **§5.1**。

**四个臂。** 检索深度 k=8 与 k=30；k=30 之上再加"强制注入 oracle 段落"的对照臂，用来把检索排序的影响从下游剥离。评分侧另有两个开关：概念接合用严格还是宽松匹配、以及是否只给"独有特征"计分。

**一个必须记下的混淆。** 这些病例的 `case_text` 里内嵌了选项块，而且选项本身把排除理由写出来了（74 号例的选项 C 直接写着 "Hypertrophic cardiomyopathy was excluded because 'The transthoracic echocardiogram revealed ... normal wall'"）。四个方法当初读到的也是这个文本。为了让病例侧抽取干净，本轮所有主结果都在剥离选项块后的 vignette 上跑。

## 二、结果

| 臂 | top-1 命中金标 | 金标进前三 | 金标中位排名 |
|---|---:|---:|---:|
| k=30，求和打分，严格接合 | 0/11 | 4/11 | 5 |
| k=30，求和打分，宽松接合 | 0/11 | 6/11 | 3 |
| k=30，独有特征打分，严格接合 | 2/11 | 5/11 | 8 |
| k=30，独有特征打分，宽松接合 | 3/11 | 3/11 | 7 |
| 注入 oracle，求和打分，严格接合 | 0/11 | 4/11 | 5 |
| 注入 oracle，求和打分，宽松接合 | 0/11 | 6/11 | 3 |
| 注入 oracle，独有特征打分，严格接合 | 2/11 | 5/11 | 8 |
| 注入 oracle，独有特征打分，宽松接合 | 3/11 | 3/11 | 7 |

**注入 oracle 与不注入完全同分。** 检索侧的召回从 21/26 提到 25/26，最终排名一个都没变。这是本轮最硬的一条结论：在这个子集上，检索不是瓶颈。

金标从未被引擎**排除**（`elim_gold` 全空），它只是被别的候选压过去了：11 例中有 10 例金标排在 2–6 位。

## 三、26 条人工断言逐级追踪

按流水线顺序判定每条断言死在哪一级，取第一处失败（注入 oracle 臂）：

| 阶段 | 条数 | 实际成因 |
|---|---:|---|
| S0 候选集无此主语 | 3 | 119.a/119.b 是两方法口径下的真实召回缺口（金标只被 impc 召回）；257.b 是粒度缺口（金标以泛标签 "Abscess" 在集内，但无人提出"领扣状脓肿"）。详见下文 |
| S1 检索未召回 | 1 | 179.a：主语与谓语从未同处一个切片，无可注入 |
| S2 抽取未陈述 | 4 | 见下 |
| S3 关系类型不可用 | 1 | 475.a：模型把 `definition` 填进了 relation 槽（枚举外溢） |
| S4 主语未绑定候选 | 1 | 326.c：断言主语是 "Brucella"（菌），候选标签是 "Brucellosis"（病），机械归一化不跨菌—病轴 |
| S5b 病例抽取漏掉发现 | 3 | 522.a（"intermittent" 未被记成波动性）、49.a（阑尾切除史未成为 finding）、74.b（噪声/应激触发未成为 finding）。三条的患者侧事实**都在 vignette 原文里** |
| S6 接合失败 | 6 | 见下 |
| S7 到达引擎仍失败 | 7 | 见第六节 |

**S0 的三条不是同一回事，需要拆开。** 22 例深审集的入选标准是"**四种**方法中至少一种召回金标"，而本轮按要求只取 collapse3c 与 multistance 的候选集，两者之间存在口径落差：

- **119.a / 119.b（DA_d2_seq100/119）**：金标 EPPP 的召回**只来自 impc**（其候选集里有 "Porokeratosis"，判为 strong）。collapse3c、multistance、forest 三家全 miss。这是两方法口径下的真实召回缺口，是本轮唯一一例因限定候选来源而丢掉金标的病例——若放开到四方法，11 例的金标全部在集内。
- **257.b（MCR_seq200b/257）**：金标其实**在**我的候选集里，但只以 "Abscess" 这个泛标签的形式存在（multistance 的注册项，别名 Soft Tissue Abscess / Pus-filled cavity，被判为 strong 召回 "collar button abscess"）。四种方法没有任何一种提出过"领扣状脓肿"这个具体实体，所以 257.b 这条关于该实体的准入断言没有可条件化的主语。这不是召回缺口，是**粒度缺口**。

粒度这件事在 11 例里是普遍的，值得单列。把"被判为 strong 的候选标签"与金标逐例对齐：

| 关系 | 例数 | 病例 |
|---|---:|---|
| 与金标同义或更细 | 3 | 326（Brucellosis）、74（CPVT）、49（Appendiceal stump appendicitis，金标 `StumpAppendicitis` 驼峰拆分后一致） |
| 真同义但零词面重叠 | 1 | 475（Neuralgic Amyotrophy = Parsonage-Turner） |
| 严格更粗的上位概念 | 5 | 522（Catatonia，缺"继发于路易体痴呆"）、773（IPAH，缺"合并 PFO"）、257（Abscess）、56（Carcinoma）、179（Thrombocytopenia，缺"低氧所致"） |
| 概念混淆 | 1 | 91：候选标签是 "Hemangioma"（良性），别名表里塞了 "Angiosarcoma"（恶性），召回判定走的是别名 |
| 不在集内 | 1 | 119 |

只有 4/11 例的候选集里存在与金标真正同粒度的标签。这直接影响 `top1_is_gold` 的读法：即使引擎完美工作，522 例它最多只能选中 "Catatonia"（金标的复合结构"紧张症继发于 DLB"需要同时挑中两个候选，扁平排序表达不了），91 例它最多只能选中一个标着"血管瘤"的条目。**"金标被召回"这个入选标准比字面上宽松得多**，本轮所有以它为分母的指标都应按此折价。

**S2 的四条要分开看。** 91.a 与 56.b 的注入段落本身就是上一轮人工裁定的 `stated_but_buried`——注入用的是语料序第一个正则命中，91.a 拿到的是肝活检标志物表、56.b 拿到的是间皮瘤角蛋白段。抽取器拒绝从这些段落里造出规则是**正确行为**，这两条应记在"正则 oracle 有 4/26 的首位命中是伪共现"上，不是抽取失败。773.b 是真正的抽取失败：Merck 第 293 章写的是"血流初期左向右，因为体循环压力与阻力高于肺循环"，而规则是这句话的**逆命题**（梯度逆转即 Eisenmenger 反应），抽取器没有做这一步取逆。179.b 的唯一命中是 Nelson 表 149-1 的跨行伪共现，语料里本就没有这条。

**S6 全是表面失配，且都是"差一点"。** 典型例子：

- 56.a：断言谓语 `p63 positivity`，病例发现 `p63 staining`。词集 {p63, positivity} 与 {p63, staining} 的 Jaccard 是 0.33，低于 0.5 的阈值。
- 326.a：断言谓语 `unpasteurized milk`，病例发现 `exposure to unpasteurized sheep stomach`。Jaccard 0.2。
- 74.a：断言谓语 `structurally normal heart`，病例发现 `normal wall thickness` / `no valvular abnormalities`。这一条不是表面失配，是**需要知道"室壁厚度正常 + 无瓣膜异常 ⇒ 结构正常"这个蕴含关系**，纯字符串层面接不上。

把接合放宽（共享含数字的标记 token 如 p63/cd34，或 Jaccard≥0.25）后，全局接合数从 ~50/例 提到 ~120/例，金标进前三从 4/11 提到 6/11——但 top-1 仍然 0/11。**接合是必要修复，不是充分修复。** 下面把这几条连同成功链一起展开成「断言 → 指南原文 → vignette 命中项」的完整证据，11 例全量见 `evidence_pack_k30clean.md`（118 条）。

## 四、断言 → 原文 → vignette 命中项

以下均取自 k=30、剥离选项块后的抽取产物。每条链给出 schema 化断言、指南段落、病例发现，以及机械接合的结果。

### 4.1 成功链：两端都对，加法把金标淹没

522 号例（金标 Catatonia related to underlying Lewy body dementia）。竞争假设 Delirium 靠泛特征拿到 15 次接合、得分 6.15；金标 Catatonia 只有 5 次接合、得分 4.0。单条链质量上金标更好：

**竞争假设（Delirium）**

```
断言        Delirium —[feature_of/asserted/typical]→ "inattention"
出处        pmc_oa / The agitated older adult in the emergency department
            › CAUSES OF AGITATION IN OLDER ADULTS > Delirium
原文        "...all of which include formal tests of attention as inattention is one of
            the defining features of delirium. Nonetheless, delirium is missed
            in the ED in up to 67% to 75% of cases."
vignette项  `inattention`（canonical=`inattention`，极性 present）
vignette原句 "Inattention"
接合        exact     引擎影响 Δ=+0.8
```

同例 Delirium 还用 `hallucinations` 命中 `visual hallucinations`（containment）、`delusions` 命中 `paranoid delusions`（containment）、`inappropriate or unsafe behavior` 命中 `abnormal behaviors`（containment）。这些在指南里都写得没错，但它们不是紧张症与谵妄的鉴别点。

**金标（Catatonia）**

```
断言        Catatonia —[feature_of/asserted/typical]→ "echopraxia"
出处        statpearls / Schizophrenia with prominent catatonic features
            › History and Physical
原文        "...4. Inability to suppress motor functions (stereotypy, echolalia,
            echopraxia).[16]"
vignette项  `echopraxia`（canonical=`echopraxia`，极性 present）
vignette原句 "Echopraxia"
接合        exact     引擎影响 Δ=+0.8
```

同例还有 `Akinetic catatonia —[feature_of]→ mutism` 命中 vignette 的 `Mutism`（exact）。每条链单看都对，错的是把它们与 Delirium 的泛特征**等权相加**。

### 4.2 阈值抽出了，单位挡住了比较

74 号例（金标 CPVT）。WikEM 儿科晕厥篇把长 QT 的切点写在一张 ECG 鉴别表里：

```
断言        Long QT syndrome —[feature_of/asserted/typical]→ "QTc"
            阈值 {operator: ">", value: 0.45, unit: "sec"}
出处        wikem / Syncope (peds)    ctx=diagnosis
原文        "ECG may show:
             WPW – short PR, Delta waves, wide QRS
             Long QT syndrome – QTc >0.450 sec
             Hypertrophic cardiomyopathy – LVH, ST changes, T wave inversions..."
vignette项  `QTc interval`（canonical=`qt interval`，极性 present，值 380 ms）
vignette原句 "QTc of 380 ms"
接合        containment（走 label 侧 `QTc interval`；canonical 词集
            {interval} 与 {qtc} 不相交，Jaccard=0.00）
```

380 ms < 450 ms 本该一刀切掉长 QT。`threshold_ok()` 因 `sec` / `ms` 单位不一致直接返回 `no_numeric_pair`，比较从未发生。同一段落还并列写着肥厚型心肌病的 ECG 征象——这正是「对照表被抽成彼此无关的独立断言」的典型。

### 4.3 接合失败：语义相同，词面差一点

**56.a（肉瘤样鳞癌 / p63）**

```
断言        sarcomatoid squamous cell carcinoma —[feature_of/asserted/typical]
            → "p63 positivity"
出处        pmc_oa / Immunohistochemistry for Skin Cancers    ctx=differential
引语        "patchy p63 positivity"
vignette项  `p63 staining`（canonical=`p63 staining`，极性 present）
vignette原句 "positive for p63"
接合        失败 —— {p63, positivity} vs {p63, staining}，Jaccard=0.33 < 0.5
```

**326.a（布鲁氏菌病 / 未消毒暴露）**

```
断言        Brucellosis —[caused_by/asserted/typical]→ "unpasteurized milk"
出处        statpearls / Respiratory protection for Health Care Workers
            › Issues of Concern
原文        "Brucellosis is a very contagious zoonosis that may be contracted by
            consumption of undercooked meat, unpasteurized milk, or contact
            with other secretions."
vignette项  `exposure to unpasteurized sheep stomach`
            （canonical=`exposure to unpasteurized animal product`，极性 present）
vignette原句 "unpasteurized sheep stomach"
接合        失败 —— {milk, unpasteurized} vs {animal, exposure, product, unpasteurized}，
            Jaccard=0.20
```

病例侧 `canonical` 已经泛化到 "unpasteurized animal product"，语料侧停在具体的 milk，两边各自泛化到不同层级，还是接不上。

### 4.4 主语绑定失败：菌 ↔ 病

**326.c**

```
断言        Brucella —[feature_of/asserted/obligatory]→ "gram-negative"
出处        statpearls / Respiratory protection for Health Care Workers
            › Issues of Concern
原文        "...Brucella is small gram-negative, nonmotile, non spore-forming,
            rod-shaped coccobacilli bacteria. It is a facultative intracellular
            parasite resulting in chronic disease."
vignette项  `blood cultures`（极性 present）
vignette原句 "blood cultures grew a Gram-negative bacillus"
绑定        失败 —— 断言主语 "Brucella" 与候选标签 "Brucellosis" 词集不相交
```

指南原文与 vignette 都写明了，断在候选绑定：缺一条 `Brucella --causative_agent_of--> Brucellosis` 的边。即使强制把主语绑上，谓语 `gram-negative` 与发现 `blood cultures` 也接不上——患者侧的发现粒度是「血培养长出了革兰阴性杆菌」，断言粒度是「该菌为革兰阴性」。

### 4.5 谓语打包：整组判据塌成一个字符串

**257.a（化脓性屈肌腱鞘炎 / Kanavel 四征）**

```
断言        Flexor tenosynovitis —[feature_of/asserted/typical]
            → "Kanavel's cardinal signs"
出处        statpearls / Hand Infections › History and Physical    ctx=differential
原文        "Presence of some or all of Kanavel's cardinal signs (flexor posturing
            and fusiform swelling of the digit, tenderness to palpation along
            the flexor tendon sheath, and pain upon passive digit extension)
            may indicate the presence of flexor tenosynovitis."
vignette项  `focal tenderness`（canonical=`tenderness`，极性 present）
vignette原句 "focal tenderness over the flexor sheath"
接合        失败 —— {kanavel, cardinal} vs {tenderness}，Jaccard=0.00
```

原文把四个征象、它们之间的合取、以及 "some or all" 这个计数条件全写清楚了，抽取后只剩一个不可拆的名词短语。257 号例的手工判别恰恰要数「四征只满足压痛一项」，而这条链连「压痛属于 Kanavel 四征之一」都表达不出来。这是上一轮「断言之间没有任何显式连词」在数据里的直接对应。

### 4.6 这五类合在一起说明什么

**每一条链的指南原文都是对的。** 断点分别在：单位归一（4.2）、词面泛化层级（4.3）、本体缺边（4.4）、谓语粒度 / 组内逻辑丢失（4.5）、以及两端都对之后的等权求和（4.1）。这也解释了为什么把检索换成完美 oracle 结果一格不动——问题全在接合层往后。11 例 top-1 与金标的完整链见 `evidence_pack_k30clean.md`。

## 五、断言之间靠什么连接

当前的答案是：**断言之间没有任何显式连词。** 每条断言是一个独立的七元组，逻辑连接完全是引擎在运行时隐式重建的，而且只有三条通道。引擎如何把这些独立断言变成「排除 / 确认 / 打分 / 互比」，就是下面的四层。

### 5.0 四层分别是什么

出处：`MECHANICAL_RULE_FEASIBILITY.md` §2.4。实现：`run_mechanical_engine.py` 的 `run_case`（注释 `# ---- four layers`）。**不含模型。** 输入是已经绑定到候选、并已接到病例发现的断言；输出是每个候选的 `eliminated` / `confirmed` / `score`，再按固定键排序。

四层做的事情不同，不是同一套加减分换个名字：

| 层 | 名称 | 对候选做什么 | 写进哪 | 能否单独定名次 |
|---|---|---|---|---|
| **层一** | 硬约束 | **一票否决**该候选（不看分数） | `eliminated[]`，`layer: 1` | 能。被否决者排在所有未否决者之后 |
| **层二** | 确诊确认 | 记下一条「单独即可确诊」的命中，并 **+2.0** | `confirmed[]`，`layer: 2`；同时加分 | 能。未否决者之间 **确认条数优先于得分** |
| **层三** | 加权特征符合 | 按 modality 权重加减分 | `score`、`contributions` | 不能单独淘汰；是大多数断言的归宿 |
| **层四** | 定向比较 | 只在**未淘汰**的候选之间，按 `comparator` 给对方 **−0.5** | 对方的 `score`、`layer4_penalties` | 不能淘汰，只微调存活者分数 |

**执行顺序（每个病例一次）：**

1. 前置（不算层）：`subject` 绑候选 → 按 `(predicate, relation, polarity)` 去重 → `predicate` 接发现 → 统计 `claimants` → 若开 `--groups` 则聚 `criterion_group`。
2. **对每个候选**：先求值该候选的判据组（组可走层一，否则一次给分，见 5.0.5）→ 再对**未入组**的断言按条走 **层一 → 层二 → 层三**（一条触发层一或层二后 `continue`，不再给该条走后面的层）。
3. **全部候选都有 verdict 之后**才跑层四（需要知道谁还活着）。
4. 排序：`(是否被层一否决, −层二确认条数, −得分)`。

一条断言触发层一，**只跳过该条**的层二/层三；同候选其他断言照常跑。被否决的候选仍会累计分数和确认，但排序键第一位把它们沉底。设计稿里「先排除再给幸存者打分」的停机，实现里是靠排序而不是靠提前 `break`。

#### 5.0.1 层一：硬约束（淘汰）

**医学意图。** 「缺了就不能诊」或「出现了就不能诊」。对应人工树的第一刀。74 的设计承重柱是 `required_for`+`obligatory` 且切点失败 → `threshold_violated`；119 的 Brugada 缺失是 `required_but_absent`；指南若写成排除句则走 `exclusion_triggered`。

**整层总闸（缺一则本条不跑层一）：**

- `context_type` **不在** `SOFT_CONTEXTS` = `{differential, table_row, epidemiology, treatment, prognosis}`。
- 断言 `polarity == asserted`（`negated` **整层不跑**）。
- 该条已接到一条病例发现（`_finding` 非空）。**没接到就不淘汰**：引擎不做封闭世界，「vignette 没写」≠「发现缺失」。例外见组规则 + `CLOSED_WORLD`（5.0.5）。

**三条单断言规则**（实现里按此顺序，一条命中即 `continue`）：

| 规则码 `rule` | 断言侧还要满足 | 发现侧还要满足 | 切点 | 本试验里的典型 |
|---|---|---|---|---|
| `required_but_absent` | `relation=required_for` **且** `modality=obligatory` | 发现 `polarity ∈ {absent, normal}` | 不看 | 74 无 Brugada I 型；475 在 F7 前 MRI normal 误杀 AIN |
| `threshold_violated` | 同上 `required_for`+`obligatory` | 已接合（极性通常是 present，否则上一条已处理） | **`threshold_ok is False`**（不是 `None`） | 设计给 74 的 QTc 380 ms 低于切点；单位不一致则是 `None`，**不淘汰** |
| `exclusion_triggered` | `relation ∈ {excludes, argues_against}` | 发现 `polarity == present` | **不看** threshold | 指南写成排除句且患者身上有该发现 |

`threshold_ok` 的三值：两边都有可比数字且单位一致（字符串相等，**不换算** `ms`/`msec`/`sec`）才得到 `True`/`False`；否则 `None`（`no_numeric_pair` / `unit_mismatch` / 未知算子），层一当「比较没发生」，不淘汰。算子：`<` `<=` `>` `>=` `=` `range`（`value ≤ 发现 ≤ value_high`）。`threshold.relational` 不读。

**层一明确不消费的 relation：** `feature_of`、`sufficient_for`、`pathognomonic_for`、`distinguishes_from`、`variant_of`、`synonym_of`、`caused_by`、`treated_by`。其中 `sufficient_for` schema 有充分性槽，层一/层二都未接；`pathognomonic_for` 走层二不是层一（有该发现则确认，**缺该发现不淘汰**）。

**组触发的层一**（`--groups` 且组大小 ≥2）：见 5.0.5 的 `criterion_group_violated`。

#### 5.0.1.1 为何 `negated` 整层不进层一（合理性核验）

设计稿 §2.4 **没有**写 polarity 闸；实现写成 `if not soft and pol == asserted`。层三却对 `negated` 做了极性对偶（发现 present 扣分）。两层口径不一致，需要单独核验：是逻辑上该挡，还是实现图省事。

**两套口径。** 机器：现行层一规则（`required_but_absent` / `threshold_violated` / `exclusion_triggered`）在 **C1 栈**（B1+S6+F7）上原样跑，只拿掉 `pol==asserted`。手工：先丢掉接合/单位等技术缺陷，再问「quote 相对 vignette 事实应不应当硬排除该候选」。手工的用途正是把 74 的 `ms`/`msec` 这类实现债从逻辑判断里拿掉，不让技术失败冒充规则对错。

**抽取里 `negated` 实际在写什么。** prompt 说：原文称该特征在主语上不出现 / 正常。F8 口头化则把同一槽读成命题外层否定（「并非 F 排除 D」）。抽取器大量走了第三条路：把「缺席、不必做、不能排除、rarely」塞进 `excludes`+`negated`。C1 绑定后 `negated` 904 条，其中 `excludes` 674、`argues_against` 36、`feature_of` 144；**`required_for`+`negated` 绑定为 0**（全库原始抽取仅 6 条，且全是 `typical`，quote 如 “Without surgical intervention” / “only around half … all 4 Kanavel signs”）。

**机器：只拿掉闸、规则不改，会新增不当否决。** 高权 `negated` 已接合 127 条；其中发现 present 且非 soft 的 53 条会全部走 `exclusion_triggered`（`excludes` 52 + `argues_against` 1）。**没有一条**走 `required_but_absent`（没有 `required_for`+`negated`+`obligatory`）。接合：loose 30 / containment 12 / embed 7 / exact 4。这 53 次否决打在 33 个候选上，其中 **6 次打在金标**：257 Abscess、56 Carcinoma、74 CPVT（三条）。金标 CPVT 会被「缺血/结构心脏病 → 接到 pulse」「室性早搏 → 接到室颤」杀掉。因此：**「同一套层一规则套到 negated 上」在本集不是空操作，且会误杀。**

**手工：剔掉技术缺陷之后，这 53 条仍然几乎都不是合格硬排除。** 判定时忽略：loose/embed 把无关发现粘上（pulse、BUN、室颤↔早搏）、单位字符串不等（B12 `pg/ml` vs `pmol/l`、血小板 `10^9/l` vs `/mm3`）。剩下 exact/containment 里，quote 的命题类型是：

| 类型 | 例 | 手工：该不该层一否决主语 |
|---|---|---|
| 「并非 F 排除 D」（F8 读法） | 49 “a normal-appearing CT scan does not exclude the diagnosis”；257 “PFT should not be excluded based on the lack of this sign” | **否。** 现行 `exclusion_triggered` 会在发现 present 时淘汰主语，方向反了 |
| 疾病常不出现 F，但不是永不 | 326 “Often these patients are afebrile”；119 “rarely demonstrates eosinophils”；“do not typically itch” | **否。** 至多层三；`often`/`rarely`/`typically` 不是 obligatory 永不 |
| 检查「不必做」 | 119 “punch biopsy is usually not indicated” | **否。** 做了活检 ≠ 排除该诊断 |
| 缺席特征写进 excludes | 56 “without much pain”；“Nuclear atypia … are not seen” | 若编码是「该病不应有 F」且患者有 F，手工可反对该病；那是 **feature 否定的对偶**，不是 `excludes`+present |
| 数据不支持某风险 | 257 “data does not support … diabetes” × 金标 Abscess | **否。** 患者有糖尿病不能排除脓肿 |
| 74 LQTS `normal QTc`（单位已一致，**不是** 440 ms 技术债） | quote “A normal QTc in men is less than 440ms”；发现 QTc 380 ms present；`threshold_ok` 为 `380 ms < 440 ms` | **手工应排除 LQTS。** 但现行层一 `excludes` **不读切点**，否决条件是「QTc interval 为 present」。QTc=500 ms 同样 present，也会杀 LQTS。挡 `negated` 并没有挡住一条正确的切点规则——正确形式应是 `asserted` 的 `required_for`+`obligatory`+`>440`，或发现 polarity=`normal` 的 `excludes` |

结论先说：**不能把闸拿掉还沿用现行三条规则。** 那样新增的否决不是「终于执行了极性对偶」，而是把「原文在谈缺席/不必做/不能排除」当成「该发现出现则排除该病」。用户反事实「若移除后没有不当否决，则闸缺乏 reasonability」在本集上不成立——不当否决是多数，且含金标。

**逻辑上缺的不是「让 negated 走同一套规则」，而是极性对偶（prompt 口径）。** 层三已经在做；层一没有。

| 断言 | 发现 | 层一应对（手工 / prompt） | 现行 |
|---|---|---|---|
| `required_for`/`feature_of` + **asserted** + obligatory | absent/normal 或切点失败 | 淘汰（已实现） | 做 |
| `required_for`/`feature_of` + **negated** + obligatory | **present**（疾病不应有 F，患者有） | 淘汰（对偶） | **不做**（整层跳过） |
| `excludes`/`argues_against` + **asserted** | present | 淘汰 | 做 |
| `excludes`/`argues_against` + **negated** | 任意 | **不淘汰**（并非 F 排除 D；或抽取把缺席塞进了 excludes） | 碰巧做对（整层跳过） |

对偶在 C1 上 **开火 0 次**：没有绑定的 `required_for`+`negated`+`obligatory`；`feature_of`+`negated`+`obligatory` 原始 14 条（如 475 “Sensation remains intact”）未接到「感觉缺失 present」（本例感觉是 absent，对偶本就不应开火）。因此：闸在外延上几乎等于「不要对 `excludes`+`negated` 跑 `exclusion_triggered`」；它**不是**因为对偶会误杀才加上的。把理由写成「negated 在层一没有医学含义」过宽——层三承认它有含义；层一只是拒绝用 asserted 规则去解释它。

**不改引擎。** 补对偶是另一条规则（新 `rule` 码），不是删除 `pol==asserted`。对偶在本集是否有害、误杀是否来自 relation 抽错，见下节。产物：`negated_l1_census.json`（脚本 `census_negated_l1.py`）。

#### 5.0.1.2 对偶淘汰是否有害（及是否为 relation 抽错的副产物）

对偶定义不变：非 soft，`(feature_of | required_for)` + `negated` + `obligatory` + 发现 **present** → 淘汰。配置仍是 B1+S6，对比 C0（无 F7）与 C1（有 F7）。手工口径同样先丢掉接合/单位技术债。产物 `dual_l1_harm_audit.json`。

**按定义实现的对偶：C0 与 C1 都是 0 次淘汰，本集无害。** 不是 F7 把它压空的。形状匹配 6 条（去重后），全部 `why_not ∈ {unbound, unjoined}`，没有接到 present。

| 例 | 主语 | 谓语 / quote | 为何没开火 | 手工：若接到 present 该不该淘汰 | relation 是否抽错 |
|---|---|---|---|---|---|
| 522 | Prion（未绑定） | treatability / “currently untreatable” | 未绑定 | 否。可治疗性不是病例发现 | 谓语不是特征；`feature_of` 用错槽，但不是 `excludes`↔`feature_of` 搞反 |
| 119 | Darier | myocardial infarction / “though not with MI” | 未接合（vignette 无 MI） | 否。「无关联」不是硬排除。本条原始 relation 是非法值 `not_associated_with`，**F5a 夹成 `feature_of`** 才进入对偶形状 | 夹逼制造的对偶候选，不是指南排除句 |
| 475 | AIN | sensation / “Sensation remains intact” | 未接合；病例 `sensory deficits = absent` | **该病纯运动、有感觉缺失才应反对 AIN**。本例感觉缺失为 absent，对偶正确地不开火 | `feature_of`+negated 可接受（稍糙） |
| 179 | CHD | separation of cardiac segments | 未接合 | 否。胚胎学机制不是 vignette 发现 | 谓语不是可接合特征 |
| 179 | Myelofibrosis / CGL（未绑定） | platelet function / “not functional” | 未绑定 | 视发现而定；本例未绑到候选 | 主语不在候选集 |

原始 `feature_of`+`negated`+`obligatory` 共 14 条：另 5 条在 `differential`（91 的 CD34/desmin/SMA/Rb 阴性）、2 条在 `prognosis`，对偶因 soft **根本不看**。91 的 CD34/desmin 发现是 **absent**，与「该病阴性」一致；即便取消 soft，对偶仍要求 present，本例也不会淘汰 Leiomyoma / SFT。475 感觉同理。

因此：**本集上对偶没有误淘汰，也没有「该淘没淘」的漏网（AIN 感觉、91 IHC 都是发现方向与否定特征一致）。** 无从把「有害」记在对偶头上。

**有害的 19 次出现在错误的反事实里：把 `excludes`/`argues_against`+`negated`+`obligatory` 改写成 `feature_of` 再跑对偶。** C1 上 19 次开火（与 §5.0.1.1 那 53 条里 obligatory 的子集重合），含金标 56 Carcinoma。真正的对偶实现**不会**吃 `excludes`。这 19 条能进这个反事实，正是因为抽取把 relation 写成了 `excludes` 而不是 `feature_of`。

对这 19 条问「误淘汰是不是 relation 抽错的副产物」——要拆开，不是一句「是」：

| 机制 | 代表 | 改对 relation 之后 | 误杀主因 |
|---|---|---|---|
| **接合技术债** | 773 CAD→肺动脉压；74 先心病→pulse；49 平片→右髂窝痛 | 多数仍会因 loose/embed 接到无关 present | **接合**，不是 relation 独有 |
| **应为 `feature_of`+negated，但 obligatory 是抬高** | 119 “rarely demonstrates eosinophils” | 若抽成 `feature_of`+`rare`，对偶不开火；若抽成 `feature_of`+`obligatory`，**encoded 对偶会开火** | modality 抬高；写成 `excludes` 反而让 encoded 对偶碰不到 |
| **主语/原文不是该病规则（E1/E6）** | 475 “No deficit should be expected in the AIN”（腕骨骨折文）× 拇指屈曲/对掌/外展 → 接到 FPL 无力 present，**会淘汰 AIN** | 若抽成 `feature_of`+negated+obligatory，encoded 对偶同样杀 AIN | **是抽取错误（主语+relation）的副产物**。现行写成 `excludes`，encoded 对偶吃不到，成了误打误撞的隔离 |
| **polarity 应是 `asserted` 的排除/切点** | 74 `normal QTc`；522 `normal serum B12` | 正确是 `excludes`+asserted（或 `required_for` 延长/低下），不是 `feature_of`+negated | **不是**「错写成 excludes、本该 feature_of」。对偶机制（「疾病没有 normal QTc」+「QTc 测量 present」）仍然错；本例 380 ms 手工该排除 LQTS，但是靠切点，不是靠对偶 |

**总判。** (1) 按槽位实现的对偶在 11 例上 **零淘汰、无害**。(2) 把 `excludes`+negated 强行当对偶来跑才会有害；那是 relation 抽错之后的二次误用，不是对偶规则本身的开火集。(3) 若抽取器把 475 那类句子「改」成 `feature_of`+`negated`+`obligatory`，对偶会变成有害——那种有害是 **obligatory 否定特征贴错主语** 的副产物，relation 写成 `excludes` 目前反而把它们挡在对偶外面。(4) 不改引擎：对偶若落地，只吃 `feature_of`/`required_for`，不要 recast `excludes`。

#### 5.0.2 层二：确诊确认（排序键）

**医学意图。** 「单独出现即可确诊」（hallmark / pathognomonic / will be diagnostic）。119 的角样板层走的就是这一层。它**不是**必要性（缺了该排除——那是层一的 `required_for`），也**不算切点方向**。

**触发（全部同时成立）：**

- 非 soft 语境；
- `relation == pathognomonic_for`；
- 断言 `polarity == asserted`；
- 已接合，且发现 `polarity == present`。

**效果：** `confirmed` 记一条；`score += 2.0`；`continue`，**同一条不再走层三**（避免 +2.0 再加一次 `w`）。不读 `modality`、不读 `threshold`。因此 74 把病名循环写成 `pathognomonic_for prolonged QT`、患者又有「QTc 这个检查 present」（380 ms 仍是 present）时，层二照样确认——F7 要拦的是进层二的断言，不是层二算法本身。

**不触发时落到哪：** 未接合或 soft → 该条结束（层三也因 `f is None or soft` 跳过）。接合但发现是 absent/normal → 层二不记确认，落入层三：asserted+absent 扣 `0.5w`。`negated` 的 pathognomonic 层二不跑，走层三极性对偶。

**排序含义。** 存活者内部第一键是 `−len(confirmed)`，第二才是 `−score`。74 在 F7 前：CPVT 得分可以高于 LQTS，仍排第 2，因为 LQTS 的层二确认条数更多。层二因此既是 +2.0，更是**覆盖计数无法表达的优先权**。

#### 5.0.3 层三：加权特征符合（打分）

**医学意图。** 既非硬排除、也非单独确诊的符合度：典型征出现则加分，该有却没有则轻扣，指南否定的特征若患者有则扣分。这是引擎退化成「覆盖计数」时真正在跑的层（第六节）。

**跳过：** 未接合，或 `context_type ∈ SOFT_CONTEXTS`。因此鉴别段 / 表行 / 治疗 / 预后 / 流行的断言**默认零分**，除非它们走层四（5.0.4）。已入 `criterion_group` 的成员不逐条进层三，改按组给一次分（5.0.5）。

**极性配对（先算 `delta`，`w = MODALITY_W[modality]`，缺省 `0.5`）：**

| 断言 `polarity` | 发现 `polarity` | `delta` |
|---|---|---|
| `asserted` | `present` | `+w` |
| `asserted` | `absent` 或 `normal` | `−0.5w` |
| `negated` | `present` | `−w` |
| `negated` | `absent` 或 `normal` | `+0.3w` |
| 任意 | `not_assessed` 或未列出 | 0（本条不加分） |

**切点在层三只是加减，不淘汰：** `threshold_ok is True` → 再 `+0.5w`；`False` → 再 `−0.5w`；`None` → 不动。所以 `feature_of` + `QTc >440 ms` 在 380 ms 且单位一致时只罚分；单位 `msec` vs `ms` 则连罚分都没有。层二的 pathognomonic **不算**切点，不能靠这一条排除 LQTS。

**正向 `delta` 的再加权（负向不乘）：**

- 候选集内频次 `specificity(宣称该发现的候选数, 本例候选数)`：默认方案 `none` 恒为 1；`binary` / `inv` / `idf` / `k1bonus` 等见第十一节。
- 若开 F1：再乘 `lr_weight`（语料似然比，裁剪后指数）。

`sufficient_for`、`variant_of`、`synonym_of`、`caused_by`、`treated_by`，以及未打开层一闸的 `required_for`，全部按上表走层三。

#### 5.0.4 层四：幸存者之间的定向比较

**医学意图。** 指南写的是「用该发现把主语和另一病分开」，不是「该发现排除主语自己」。对应 `distinguishes_from`（以及带 `comparator` 的 `argues_against`）。

**时机：** 所有候选的层一–三结束后。只考虑 `eliminated` 为空的候选（**幸存者**）。已被层一否决的候选既不发起、也不作为「还活着的对方」挨罚。

**触发（断言侧）：**

- `relation ∈ {distinguishes_from, argues_against}`；
- `comparator` 非空；
- 已接合且发现 `polarity == present`。

**不检查：** `SOFT_CONTEXTS`（鉴别段正是层四的设计用途）、断言 `polarity`、`modality`、threshold。`feature_of` 即使写在 differential 里也**不会**因层四给分或扣分。

**效果：** 对每个**其他**幸存者，若 `concept_match(comparator, 对方.label)` 成功，则对方 `score − 0.5`，并记 `layer4_penalties: {from: 本候选, predicate}`。匹配失败则边不触发（早期严格接合下全库只触发数次到数十次，见 5.2）。

**与层一的关系。** `argues_against` 在非 soft 且 asserted 时，发现 present 会先走层一淘汰**主语自己**；该候选就不再是幸存者，层四从它发出的边也不会跑。因此层四里真正常见的是 `distinguishes_from`（层一不淘汰主语）。`excludes` 不进层四。

#### 5.0.5 判据组插在哪一层

`--groups` 打开时，组在「逐条层一–三」**之前**求值；组成员随后 `continue`，不再逐条进层。组不是第五层，而是把若干断言收成一次判定：

| `logic` | 满足 | 未满足时的得分（层三形态） | 层一 |
|---|---|---|---|
| `all` | `\|sat\| ≥ (n 或组大小)` 且无显式违反 | `\|sat\|/target − 0.5·\|vio\|` | 组被当作必要，且有违反，且组内 context **并非全部** soft → `criterion_group_violated` |
| `at_least_n` | `\|sat\| ≥ n`（缺省 1） | `0.5 · \|sat\|/n` | 无 |
| `any` | 至少一员发现 present | 0 | 无 |

`sat` = 接到的发现极性为 present；`vio` = absent/normal。组内全未接合则跳过（不给分、不淘汰），除非 `CLOSED_WORLD`：`all` 组把从未提及的成员也算进 `vio`（257 Kanavel「只写了压痛」依赖这一假设；默认关闭，因为会误杀其他例）。

组被当作必要，当且仅当：组内任一条 `required_for`+`obligatory`，或开关 F4b `GROUP_ALL_IS_REQUIRED`（`logic=all` 即使成员是 `feature_of/typical` 也当必要）。`w` 取组内最高 modality 权重；正向分再乘频次权重。组循环**不读**成员的 threshold、也不做 negated 极性对偶。

#### 5.0.6 排序键（四层如何合成名次）

```
key = (bool(eliminated), −len(confirmed), −score)
```

| 键 | 来自 | 含义 |
|---|---|---|
| 1. 是否淘汰 | 层一（含组违反） | `True` 的全部排在 `False` 之后 |
| 2. 确认条数 | 层二 `confirmed` | 存活者里条数多的在前（74 的致命键） |
| 3. 得分 | 层二的 +2.0 + 层三（及组）+ 层四的 −0.5 | 同确认数时分高者在前 |

`top1` 是该序下第一条的 `label`。金标可以分数更高但仍因键 1 或键 2 落败。

#### 5.0.7 与设计稿 §2.4 的差别（实现为准）

| 设计稿 | 当前实现 |
|---|---|
| `required_for`+`obligatory`：发现非 present **或**切点不满足即淘汰 | 仅当**已接合**且（absent/normal 或 `threshold_ok is False`）。未提及不淘汰 |
| 层一只写 `excludes` | 另含 `argues_against`；组另有 `criterion_group_violated` |
| 层三只给「幸存者」的 `feature_of` 打分 | 未淘汰者也打分；被淘汰者同样累加，只是排序沉底。除 soft / 未接合 / 已被层一或层二 `continue` 的条外，**所有 relation** 都可进层三 |
| `differential` 不进层一/二，只进层四 | soft 五种语境跳过层一/**二/三**；层四**不看** context，且只认 `distinguishes_from` / `argues_against` + `comparator` |
| 未写 polarity | 层一要求 `asserted`；`negated` 整层跳过。层三做极性对偶。拿掉闸而不改规则会误杀，见 §5.0.1.1 |
| 排除链即决策流程 | `eliminated`/`confirmed`/`contributions`/`layer4_penalties` 可打印；排序另用确认条数压过得分 |

槽位如何填、F7 如何改写后再喂给上述四层，见 **§5.1**。

### 5.1 schema 里没有「断言间」连词；规则逻辑是多槽合取

字段全集（指南断言）是十项加后来的组字段：`subject / predicate / predicate_kind / relation / polarity / modality / threshold / comparator / context_type / quote`，以及 `--groups` 时的 `criterion_group`。这些编码的都是**一条断言内部**的命题。没有字段指向另一条断言。唯一的跨假设边是 `comparator`（早期 15,588 条里占 8.8%，主要挂在 `distinguishes_from`）。

**决定「这条规则在引擎里怎么执行」的不是单看 `relation`。** `relation` 只选规则族；能否硬排除、确认还是加减分，由 `relation × polarity × modality × threshold × context_type × criterion_group`（外加应用时接到的**发现 polarity / value**）合取决定，再送入 **§5.0** 的对应层。下面按取值、含义、抽取填充、引擎消费四列写全。代码源：`run_trial_extraction.py` 的 prompt 枚举、`run_mechanical_engine.py` 四层、`gate_assertions.py` 的 F7 改写。

#### 5.1.1 填充流水线（谁在写这些槽）

| 阶段 | 谁 | 写什么 |
|---|---|---|
| 指南抽取 | LLM，payload 含 `focus_disease`（旧）或 `retrieval_query`（`--grounded`）+ `passage` | 一次调用填完整条 JSON；`quote` 须为 passage 子串且 ≤200 字 |
| 病例抽取 | LLM，payload 为 vignette（可 `--strip-options`） | `findings[]`；与断言分开，应用时才接合 |
| 组字段 | 仅 `--groups` | 同句多发现拆成多条，共享 `group_id/logic/n` |
| F5a `clamp_relation` | 程序，`--enum-clamp` / 栈 S4 | 非法 `relation` 映射到合法枚举或改 `context_type` 后落成 `feature_of` |
| F7 `gate_assertions` | 程序，`--quote-gate` | 按 quote（正向授权可扩到粘接 passage ±1200 字）改 `relation`/`modality`/`threshold`/`criterion_group`，或丢弃 |
| `--grounded` 后处理 | 程序 | `subject ∈ mentioned_diseases`；忽略模型 `threshold`，改 `parse_threshold_from_quote`；无 antecedent 的 `this variant` 丢弃 |
| 引擎 | 无模型 | 不改字段；按槽位走层一–四 |

检索侧：命中 chunk 与同文档邻块粘成 `passage`（`TrialRetriever.passage(window=1)`），这是 LLM 看见的证据窗口；`quote` 仍截断到 200 字。

#### 5.1.2 `relation`（11 个合法值）

**抽取填充。** prompt 闭集。仅当原文说该发现对诊断**必要**才写 `required_for`；仅当原文说单独即可诊断 / hallmark / pathognomonic / will be diagnostic 才写 `pathognomonic_for`。模型仍常过声称（E4/E12）。出界字符串（如 `associated_with`、`definition`）F5a 才夹住。

| 取值 | 含义（抽取意图） | 引擎消费（当前实现） |
|---|---|---|
| `feature_of` | 该发现是主语疾病的特征 | 层三加权加减分；切点只 ±0.5w，**不淘汰** |
| `required_for` | 该发现对诊断主语**必要** | 仅当 **`modality=obligatory` 且 `polarity=asserted` 且 context 非 soft**：发现 absent/normal → `required_but_absent`；`threshold_ok is False` → `threshold_violated`。否则同层三 |
| `sufficient_for` | 该发现单独足以诊断 | **层一、层二均不消费**；与 `feature_of` 一样走层三。schema 有槽，引擎未接充分性 |
| `pathognomonic_for` | 该发现单独即可确诊 | 层二：asserted + 发现 present → 确认 +2.0，**不算 threshold** |
| `excludes` | 该发现出现则排除主语 | 层一：asserted + 发现 present → `exclusion_triggered`（**不用 threshold**）。`negated` 不跑层一，见 **§5.0.1.1** |
| `argues_against` | 该发现反对主语 | 层一与 `excludes` 相同；另可走层四（需 `comparator`） |
| `distinguishes_from` | 该发现把主语与另一病分开 | 层一不淘汰；层四：发现 present 且 `comparator` 匹配另一存活候选 → 对方 −0.5 |
| `variant_of` | 主语是另一病的变体 | 仅层三（若接到发现） |
| `synonym_of` | 别名 | 仅层三 |
| `caused_by` | 病因 / 暴露 | 仅层三 |
| `treated_by` | 治疗 | 仅层三。F7 把 `context_type=treatment` 的 `required_for` 改成此值，避免进层一 |

**F5a 别名 → 合法值：** `associated_with`/`presents_with`/`characterized_by`/`indicates`/`suggests`/`diagnosed_by` → `feature_of`；`risk_factor_for` → `caused_by`；`includes`/`subtype_of` → `variant_of`；`same_as`/`also_known_as`/`equivalent_to` → `synonym_of`。若模型把 `definition` 等 **context 名写进 relation**：写入 `context_type`（若空）并把 relation 改为 `feature_of`。

**F7 改 relation：** 无 patho cue → `pathognomonic_for` 降 `feature_of`；无 necessity cue → `required_for` 降 `feature_of`；mimic 句上的正向 `excludes`/`feature_of` → `distinguishes_from`；治疗语境 `required_for` → `treated_by`。F7 **不会**把 `pathognomonic_for` 升成 `required_for`。

#### 5.1.3 `polarity`（断言侧 2 值）

| 取值 | 含义 | 抽取填充 | 引擎 |
|---|---|---|---|
| `asserted` | 原文说该特征**属于**主语（或排除句的正向排除） | 默认 | 层一硬规则的前提；层三：发现 present 加分、absent/normal 扣 0.5w |
| `negated` | 原文说该特征在主语上**不出现 / 正常 / 不发生**。例：原文 “QTc is normal” 对谓语 `prolonged QTc` 应为 negated | prompt 明示 | **层一不跑**（§5.0.1.1：不是因为对偶不当，而是同一套 `exclusion_triggered` 套上去会误杀）；层三：发现 present 扣分、absent/normal 小加分 |

与**发现** polarity 是两套枚举，应用时配对（见 5.1.10）。

#### 5.1.4 `modality`（5 值）

| 取值 | 含义 | 抽取填充 | 层一 | 层三权重 `MODALITY_W` |
|---|---|---|---|---:|
| `obligatory` | 强制；缺则不能诊 | 模型常把 usually/must/relies 抬到此档（E3） | `required_for` 硬排除的**必要**条件 | 1.0 |
| `typical` | 典型、常见但不强制 | 默认档最多 | 不打开 `required_for` 层一 | 0.8 |
| `frequent` | 经常 | 模型自填 | 同上 | 0.6 |
| `occasional` | 有时 | 模型自填 | 同上 | 0.35 |
| `rare` | 罕见 | 模型自填 | 同上 | 0.15 |
| （缺省/非法） | — | — | — | `DEFAULT_W=0.5` |

**F7：** `required_for`+`obligatory` 且 quote 含 may/might/usually/typically/should/relies on 等 → 降为 `typical`（E3）。and/or 合并时也会去掉 obligatory。去重保留 modality 权重更高的一条。

#### 5.1.5 `threshold`（对象，非单一枚举）

| 子字段 | 合法取值 | 含义 | 抽取填充 | 引擎 `threshold_ok` |
|---|---|---|---|---|
| `operator` | `<` `<=` `>` `>=` `=` `range` 或 null | 与发现数值的比较 | 旧抽取：LLM 从原文抄。`--grounded`：**忽略模型**，`parse_threshold_from_quote` 只在 quote 里有比较符时填写 | 缺 operator/value 或发现无数 → `no_numeric_pair`（None，不淘汰） |
| `value` | 数字或 null | 切点 | 同上；F7：数字须在 quote，或在粘接 passage 中 quote 邻域 ±1200 字内，否则清空（E14） | 与发现 `value.number` 比较 |
| `value_high` | 数字或 null | `range` 上界 | LLM 或正则 `A to B` | 仅 `operator=range`：`value ≤ 发现 ≤ value_high` |
| `unit` | 自由字符串或 null | 单位 | 从原文抄。**无归一**：`ms`≠`msec`≠`sec` → `unit_mismatch`，比较取消 | 两边都有且不等 → 返回 None |
| `relational` | 自由字符串或 null | 跨发现比较，如 PAP≥体循环压 | prompt 允许填写 | **引擎不读**。773 的两压比较是 L，不是本槽能执行的 |

空 threshold 回填：F7 只从 **quote** 正则抽，不从邻块捞新数。有比较符的裸数才成切点。

#### 5.1.6 `context_type`（10 值）

**抽取填充。** 模型从 enumerated 中选；payload 另有 `context_hint`（由标题/section 关键词：differential diagnosis → differential，treatment → treatment 等），**不强制覆盖**模型输出。

| 取值 | 含义 | 抽取提示 | 引擎 `SOFT_CONTEXTS` |
|---|---|---|---|
| `definition` | 定义、概述 | etiolog / introduction 类标题可 hint | **硬**：可进层一/二 |
| `criteria` | 诊断标准 | evaluation 类标题 | 硬 |
| `histopathology` | 病理 | histopatholog | 硬 |
| `imaging` | 影像描述 | （标题未必 hint） | 硬 |
| `other` | 其他 | — | 硬 |
| `differential` | 对照、鉴别句，未必断言主语自身特征 | 提示：对比句用此档 | **soft**：层一/二/**三**跳过；层四不检查 soft |
| `table_row` | 表格行，可能是邻行伪关联 | 提示：表格用此档 | soft |
| `epidemiology` | 流行、人群 | epidemiolog | soft |
| `treatment` | 治疗 | treatment | soft；F7 另把其中 `required_for` 改 `treated_by` |
| `prognosis` | 预后 | prognos | soft |

凡标 soft 的五档：层一、层二、层三都跳过（§5.0.1–5.0.3）；层四不检查 `context_type`。F5a 可能把误写入 relation 的 context 名填到本槽。组内若**全部**成员都是 soft，整组不当层一违反。

#### 5.1.7 `criterion_group`（断言间逻辑，仅 `--groups`）

| 子字段 | 取值 | 含义 | 抽取填充 | 引擎 |
|---|---|---|---|---|
| `group_id` | 段内短 id 或 null | 同一判据集 | 同句拆成员、共享 id；独立断言为 null | 按 id 聚合成组后一次计分 |
| `logic` | `all` / `any` / `at_least_n` / null | 合取 / 析取 / 至少 n | `all`：A and B and C 或具名 n 征（Kanavel）；`any`：one or more；`at_least_n`：at least N | `all`：可 `criterion_group_violated`（需组被当作 required）；`any`：有一满足即给分；`at_least_n`：按 n |
| `n` | 整数或 null | at_least_n 的 n，或具名征的个数 | 与 logic 同填 | `all` 时 `need or size` 为达标人数 |

**F7：** quote 含 some or all / one or more 且 `logic=all` → 改为 `any`；同一 `(quote[:80], subject)` 下 and/or 拆开的多条 `required_for` → 收成同一 `any` 组并去掉 obligatory。

F4b（`GROUP_ALL_IS_REQUIRED`）：`logic=all` 的组即使成员是 `feature_of/typical` 也当必要（257 Kanavel 设计如此）。

#### 5.1.8 `comparator`

自由字符串或 null。prompt：仅 `distinguishes_from` / `argues_against` 填写另一疾病名。引擎层四用 `concept_match(comparator, 其他存活候选名)`；匹配失败则边不触发。早期统计主要出现在 `distinguishes_from`。

#### 5.1.9 `subject` / `predicate` / `predicate_kind` / `quote`

| 槽 | 取值 | 填充 | 引擎 |
|---|---|---|---|
| `subject` | 自由病名 | 须为段落对疾病的称呼。旧抽取「优先焦点病」→ E1。`--grounded`：先 `mentioned_diseases`（须为 passage 子串），`subject` 必须属于该闭集；`this/the variant` 须有 `antecedent` 否则丢弃 | `subject_match` 绑到候选 label/aliases |
| `predicate` | 自由名词短语 | 一发现一条；禁止把 and 合取塞进一个字符串 | `predicate_match` 接到发现 label/canonical |
| `predicate_kind` | symptom / sign / lab / imaging / histopathology / ecg / hemodynamic / exposure / demographic / course / other | 模型自填 | **不消费** |
| `quote` | 原文 ≤200 字 | 必须 verbatim 出现在 passage | 引擎推理不读；F7 与阈值解析读它 |

#### 5.1.10 病例发现（应用层与断言合取）

断言本身不编码患者状态。发现由 vignette 抽取（及 grounded 的正则补集）填写：

| 槽 | 取值 | 填充 | 与断言合取时 |
|---|---|---|---|
| `polarity` | `present` / `absent` / `normal` / `not_assessed` | **normal**=查了且在正常范围；**absent**=明确否认。未提及则**省略**，禁止用 absent 表示没写 | present：可触发排除/确认/加分；absent/normal：可 `required_but_absent` 或层三扣分；`not_assessed` 通常当未接合 |
| `value.number` / `unit` | 数值、单位 | 从 vignette 抄 | 只与断言 `threshold` 比；单位字符串必须相等 |
| `kind` | 比断言多一个 `treatment_response` | 模型自填 | 不消费 |
| `qualifiers` | timing/site/laterality | 可空 | 不消费 |
| `canonical` | 小写通称 | 模型 | 接合时与 label 并列尝试 |

#### 5.1.11 合取示例（槽如何一起决定规则）

同一主语 `Long QT Syndrome`、同一谓语 `prolonged QT interval`、发现 `QTc=380 ms` present：

| relation | modality | polarity | threshold | context | 引擎结果 |
|---|---|---|---|---|---|
| `pathognomonic_for` | 任意 | asserted | 有无 440 **无所谓** | 非 soft | 层二确认（74 误杀 CPVT 的排序键） |
| `feature_of` | typical | asserted | `>440 ms` | definition | 层三；切点失败只罚分；`msec` vs `ms` 则连罚分都没有 |
| `required_for` | typical | asserted | `>440` | definition | **不淘汰**（缺 obligatory） |
| `required_for` | obligatory | asserted | `>440` 且单位一致 | definition | **层一 `threshold_violated`**（设计上的承重柱） |
| `required_for` | obligatory | asserted | `>440` | treatment / differential | soft，层一跳过 |
| `excludes` | 任意 | asserted | `<440`（引擎**不用**） | 非 soft | 发现 present 即淘汰（接错「normal QTc」时会误杀） |
| `excludes` | 任意 | negated | 任意 | 非 soft | 层一不跑（拿掉闸会按 present 淘汰主语；本集 53 次，含金标，见 §5.0.1.1） |

326：`(Brucellosis, required_for, serologic tests, obligatory)` ×2，quote 含 usually must 与 and/or → F7 降 typical 并 `logic=any`，层一不再因「TB serology absent」淘汰金标。

475：`(AIN, required_for, advanced MRI, obligatory)` + quote “this variant relies on” → F7 降档，层一不再因 MRI normal 淘汰 AIN。

257：四条 `feature_of/typical` + `criterion_group logic=all` → 单条无层一；F4b 把 `all` 当必要后才可能组违反。

#### 5.1.12 引擎明确不执行的「逻辑」

- `sufficient_for` 的充分性（无层二对称于 pathognomonic 的「有则确诊、无则中性」以外的专门规则）。
- `threshold.relational` 跨发现比较（PAP vs Ao）。
- quote 里的 if / unless / both…and（除非抽进 `criterion_group` 或拆成两条）。
- 单位换算、converse / 逆否（O1，F5b 另臂）。
- `predicate_kind`、发现 `kind`/`qualifiers`。

### 5.2 连接实际发生在三个地方，都是隐式的

**共享主语 = 隐式合取。** 绑定到同一候选的断言被求和。这是个无结构的 AND：`score += delta`。没有合取组、没有求值顺序。

**共享发现 = 隐式竞争。** `claimants` 把每个病例发现映射到宣称它的候选集合，这是唯一表达"这条证据不专属于谁"的结构，而且只在独有特征门控那个臂里被用到。

**`comparator` = 唯一显式边。** 但实际只触发了 5 次（严格接合）/ 34 次（宽松接合），因为要求 comparator 字符串能匹配到同一病例里另一个存活候选。

### 5.3 原文里的连词在抽取时被丢掉了

指南原文用的是自然语言连词，它们只活在 `quote` 里，schema 一个都没保留：

| 连词类型 | 出现在 quote 中的条数 |
|---|---:|
| `if`（条件） | 131 |
| `both...and`（合取） | 75 |
| `but`（转折） | 69 |
| `either...or`（析取） | 35 |
| `at least N` / `one or more`（m-of-n） | 40 |
| `rather than`（对比） | 19 |
| `in the absence of`（缺失条件） | 9 |
| `however` / `whereas` / `in contrast` | 18 |
| `unless` | 6 |

几个实例说明丢的是什么：

**m-of-n 塌成了单条必要项。** 原文 "diagnosis of dementia requires **at least one of the following** cognitive deficits"，抽成 `Dementia -[required_for/obligatory]-> cognitive deficits`。"至少一项"这个计数量词消失了，机械程序无从知道满足一项就够。

**合取塌成了单条。** "Obtaining a history from **both** patients **and** family members is essential" → `delirium -[required_for/obligatory]-> history from patients and family members`。两个合取支被塞进一个谓语字符串，接合层再也拆不开。

**Kanavel 四征是最典型的损失。** 原文写的是 "Presence of **some or all of** Kanavel's cardinal signs (flexor posturing **and** fusiform swelling, tenderness along the flexor tendon sheath, **and** pain upon passive extension)"，抽出来是：

```
Flexor tenosynovitis -[feature_of/asserted/typical]-> "Kanavel's cardinal signs"   ctx=differential
```

四个征象成了一个不可分的字符串，"some or all" 这个阈值也没了。257 号例的手工判别恰恰依赖"四征只满足压痛一项"——机械程序既数不出满足几项，也不知道该数到几才算数。完整证据链见 4.5。

**条件从句被翻译成了排除，这一条反而是对的。** "if the catatonia is better explained by another mental disorder" → `excludes/obligatory`，`comparator='another mental disorder'`。DSM 式的排他条款是少数能被现有 schema 正确承接的连词。

**对比连词丢了方向。** "lichen planus usually affects middle-aged patients, **whereas** drug eruptions are more common in the elderly" 抽成了 `Lichen planus -[feature_of]-> middle-aged patients`，`comparator='drug eruptions'`。comparator 保住了对比对象，但"年龄轴上两者相反"这个方向性没有编码，引擎只能给出固定的 −0.5 惩罚。

### 5.4 这解释了下一节的退化现象

引擎之所以变成覆盖计数，根子就在这里：**唯一可用的连接是加法**。没有合取组（Kanavel 四征该作为一个整体判定）、没有 m-of-n 计数器、没有条件门（满足 A 才评估 B）、没有互斥组。手工决策流程的力量来自**顺序**——一个硬分支定生死，只有幸存者才进入打分；而当前表示里没有任何字段能表达"这条断言应当先于那条断言求值"。

要补的最小结构是一个 `criterion_group` 字段（组 id + 组内逻辑 `all` / `any` / `at_least_n` + n 值），让同一判据集的多条断言挂到一个组上，再由引擎按组求值而不是按条求和。这一层连同候选集内的频次权重已在随后一轮实现并交叉验证，见第十一节。

## 六、引擎为什么会 0/11：它退化成了覆盖计数

这是本轮最重要的发现。在求和打分下，候选的最终得分与"它有多少条断言接合上了病例发现"的相关系数是 **0.74（严格接合）/ 0.85（宽松接合）**，而且 **11 例里有 10 例，top-1 就是接合条数最多的那个候选**。

74 号例最能说明问题：

| 候选 | 得分 | 接合/绑定断言数 |
|---|---:|---:|
| Long QT Syndrome | 6.00 | 13/73 |
| **CPVT（金标）** | 1.60 | 6/73 |
| Channelopathy | 0.80 | 1/31 |

抽取器其实**抓到了那条决定性断言**：`Long QT Syndrome -[excludes/negated/typical/criteria]-> normal QTc`，引擎也给它扣了分。但长 QT 综合征是文献量大得多的实体，晕厥、室颤、心脏骤停、青年、运动这些非鉴别性特征让它累积了 13 次正向接合，一条 −0.8 的扣分被淹没。773 号例同理：CTEPH 与 Eisenmenger 靠 15 条与 10 条泛特征压过金标 PFO 的 4 条。

四层算法（**§5.0**）里的硬约束层几乎没启动过：11 例 × 约 12 个候选，`required_but_absent` 只触发 2–3 次，`exclusion_triggered` 触发 0–2 次，`pathognomonic_for` 确认 0–2 次。原因有两个，都是结构性的：

1. **真实指南极少写"排除"，它写竞争假设的阳性特征。** 91.b 是标准样本：语料说的是"CD34 是血管外皮瘤的特征"（`feature_of`），而不是"CD34 阴性排除血管外皮瘤"。要把它用成排除规则，机械程序必须知道这个特征的必要性有多强——那正是 `modality` 该编码的，可抽取器把 11,796 条标成 `typical`、只有 1,462 条标成 `obligatory`。
2. **不做封闭世界假设，硬约束就打不响。** 引擎只在病例明确写了"缺失/正常"时才排除，而多数指南特征在 vignette 里根本没被提及。抽取结果里 `absent`+`normal` 只占 78/280 = 27.9%，看起来像漏抽；独立核验表明这是**组成统计而非召回**（原文 97 条显式阴性有 84.5% 已入集，详见第十节）。手工决策流程之所以能走通，是因为人默认"没写就是没有"；机械程序一旦这么假设，就会开始误杀。

**独有特征门控证明了信息是够的，只是聚合方式不对。** 只给"仅一个候选宣称"的发现计分后，top-1 从 0/11 升到 2–3/11：522 → Catatonia、326 → Brucellosis、49 → Appendiceal stump appendicitis（而且是细粒度金标，不是粗标签）。代价是方差变大：56 号例金标从第 3 掉到第 16，74 号例从第 2 掉到第 8——因为金标的特征一旦被竞争假设共享，就被一并清零了。这说明需要的是**连续的判别性权重（似然比）**，不是二值门控。

## 七、与上一轮理论核验的对照

| 上一轮的预测 | 本轮实测 | 判定 |
|---|---|---|
| 22/26 条断言可从单切片获得 | k=30 召回 21/26，注入后 25/26 | **证实** |
| 检索必须按假设条件化 | 3 条断言因候选集无此主语而永远发不出查询 | **证实且更强**：候选集缺口会直接传导成检索缺口 |
| 抽取需先做文档重组 | 已实现（命中切片 ±1）；S6 失败与切片边界无关 | 证实，但不是主要矛盾 |
| 语境类型可由元数据预填 | 可行；但模型仍会写出枚举外的值（`pathophysiology`、`anatomy`、`definition` 填进 relation 槽） | 部分证实，需要后处理夹逼 |
| 阈值须抽成一等对象 | 已抽出；但 5 条阈值断言中只有 74.c 真正参与了比较 | 证实但影响被高估 |
| 四层算法只依赖 schema 字段即可机械化 | 可以机械化，但退化为覆盖计数 | **证伪**：schema 字段齐备不等于规则可判别 |
| 断言间逻辑可由 relation / modality / comparator 隐式重建 | 15,588 条断言无一指向另一条；quote 里的 `if` / `both...and` / `at least N` 全部丢掉 | **证伪**：唯一可用的连接是加法 |
| LLM 调用可压缩到两处且可缓存 | 成立：1,941 次调用里 1,930 次跨臂命中缓存 | **证实** |

上一轮把难点定位在"检索能否取到"和"字段够不够"，这两点都过了。真正的难点在上一轮没被测出来：**接合层、聚合层、以及断言间连词在抽取时被丢掉**。schema 字段齐备只保证每条断言内部可读，不保证一组断言能还原指南里的合取 / 析取 / 条件 / m-of-n。

## 八、按收益排序的修复清单

1. **判别性权重取代求和计数**（预计收益最大）。候选集内频次权重已实现并验证（第十一节）：\(k=1\) 处 lift 1.43，单调衰减不成立，可用形态是 `k1bonus` / `idf` 而不是 `binary`。更强的一步仍是语料侧似然比——已有 `feature_hypothesis_matrix_48` 与 `clue_discriminativeness_48` 给出每个 (发现, 假设) 对的 \(P(f|h)\)。把层三的 `w(modality)` 换成 \(\log P(f|h) - \log \mathrm{mean}_{h'} P(f|h')\)，可以在不做二值门控的前提下压掉泛特征。这是唯一能同时修好 74 与 56 的改动。
2. **概念接合层**。当前是纯词集匹配。需要的最小增量是：标记 token（p63、CD34、Fli-1 这类含数字的免疫组化标记）单独成键；同义扩展（positivity/staining/expression/immunoreactivity 归一为"阳性表达"）；以及一张蕴含表处理 74.a 那类"室壁厚度正常 + 无瓣膜异常 ⇒ 结构正常"。前两项是词表工程，第三项需要本体。
3. **菌—病轴归一**（326.c）。`Brucella` 与 `Brucellosis` 之间的 `causative_agent_of` 边，同类还有病毒—感染、基因—综合征。
4. **`criterion_group`：把连词从 quote 里捞回来**（已实现，见第十一节）。抽取时把同一判据集的多条断言挂到一个组上（组 id + `all` / `any` / `at_least_n` + n 值），引擎按组求值而不是按条求和。表示层完全可行（Kanavel 四征被正确拆成 `all/n=4`），但执行被接合层堵住：组违反在该触发的 257 号例上一次都没打响。没有这一层，Kanavel 四征、DSM 的"至少一项"、以及任何合取准入条件都无法机械执行。
5. **抽取端的枚举夹逼与逆命题**。relation/context_type 用受限解码或后处理映射，杜绝 `definition` 进 relation 槽；773.b 那类"语料写正命题、规则是逆命题"的情况需要在提示里显式要求。
6. **候选集与粒度缺口**（119、257）无法在本管线内修复，且性质不同。119 是召回问题：换成四方法并集即可解决（impc 提出了 Porokeratosis）。257 是粒度问题：四种方法没有一种提出过"领扣状脓肿"，扩大方法数没用，需要候选生成阶段能下探到亚型层级。

需要说明的是，第 1 项修好之后能到多少，本轮数据无法外推。金标在 6/11 例已经进了前三，说明信号存在；但两处封顶要一并算上：119 与 257 因候选/粒度缺口不可达（上限 9/11），而 522、91 这类只能命中粗标签或混淆标签的病例，即使"命中"也不等于答对。第十一节的交叉验证进一步表明：**第 2 项接合层是第 1、4 项的共同前置**——频次 \(k\) 是在接合结果上数出来的，组内成员也必须先接到病例发现才能按 `all`/`any`/`at_least_n` 求值。修复顺序应是接合 → 判据组 → 频次/似然比权重，而不是并行推进。

## 九、几条口径上的告诫

- **不要把 3/11 与四方法的成绩直接比。** 11 例里只有 3 例（522、773、119）来自 DiagnosisArena、有选项映射式的判正；其余 8 例来自 MedCaseReasoning，本账本里 `correct` 字段为空（该基准用 LLM judge），我在装配时按 False 处理了。跨口径比较会失真。
- **正则 oracle 不是金标准。** 26 条里有 4 条（773.a、326.c、56.b、91.a）的首位正则命中是伪共现，其中 91.a 与 56.b 的注入段落就是错的。凡是以"注入 oracle 后仍失败"为论据的地方，都要先看注入的是不是有效段落。
- **"金标在候选集内"不等于"候选集里有一个可以答对的标签"。** 11 例里只有 4 例的候选标签与金标同粒度；5 例只有上位概念，1 例（91）靠别名表把良性血管瘤与血管肉瘤混在一条目里。分母口径见第三节。
- **选项内嵌是这批病例的共有缺陷。** 74 号例的选项直接写出了排除理由。本轮主结果已剥离，但任何直接读 `case_text` 的实验都会吃到这个泄漏。
- **发现集合中的阴性占比 ≠ 原文阴性被抽到的比例。** 27.9% 是组成，84.5% 才是召回，口径见第十节。

## 十、27.9% 是组成不是召回：显式阴性入集核验

全文与逐条清单见 `EXPLICIT_NEGATIVE_RECALL.md`。此处只记结论。

第六节用「抽取结果里阴性只占 27.9%」支持"硬约束打不响是因为病例没写阴性"。这个数字测的是**发现集合的组成**，回答不了「原文写了的阴性有没有被抽进来」。本轮在剥离选项块后的 11 份 vignette 上做了独立清单：只计文本里明确否认、报为 normal / negative / unrevealing / unremarkable 的条目，列表拆成原子项，封闭世界推断（Kanavel 未提及的三征）不入账。

### 10.1 两个数字

| 口径 | 数值 | 含义 |
|---|---:|---|
| 发现集合中 `absent`+`normal` 的占比 | 78/280 = **27.9%** | 抽取器输出的组成 |
| 原文显式阴性进入发现集合的比例 | 82/97 = **84.5%** | 召回 |
| 未入集（漏检 14 + 极性挂错 1） | 15/97 = **15.5%** | Wilson 95% CI 约 10–24% |

**低占比主要不是漏抽。** 阳性侧每个化验数字单独成条（522 一题 BUN、Cr、LDH、白蛋白、血红蛋白等就占了 9 条 `present`），阴性侧同一句里的多项否定常并成一条——腰椎穿刺 “negative for infectious, autoimmune, malignant causes and paraneoplastic encephalitis” 原文 4 项，只产出 1 条 `lumbar puncture [absent]`。分母被切碎、分子被合并，组成自然偏低。

按例：119 与 74 全中（14/14、13/13）；475 最差（6/10），一句话 “Routine laboratory tests and her personal and family history were unremarkable” 三个合取支全部未入集。

### 10.2 未入集的 15 条

没有一条是 Kanavel 四征、QTc、室壁厚度这类引擎要用的硬阴性。

| 类型 | 条数 | 例子 |
|---|---:|---|
| 整句丢掉 | 3 | 475 “labs and personal and family history were unremarkable” |
| 合取句尾丢掉 | 2 | 56 抽了 pan-cytokeratin 阴性、丢掉并列的 other epithelial markers；179 抽了 no bleeding history、丢掉同一句的 or medications |
| 套话 / 残余正常 | 6 | previously healthy、no recurrence until now、no other significant PMH、other values were normal、no postoperative complications、without skin break |
| 治疗无应答 / 未输注 | 2 | 326 cefprozil no lasting benefit；179 increased without transfusion |
| 时间极性被后来的阳性盖住 | 1 | 773 “initially acyanotic” 未入集，只有后来的 `cyanosis [present]` |
| 极性挂在父检查上 | 1 | 522 “EEG showed diffuse slowing **without seizures**” → `electroencephalography [present]`，quote 里有 without seizures，没有独立的 `seizures [absent]` |

### 10.3 对封闭世界争论的含义

257 上 Kanavel 三征未触发，**不是抽取漏了显式阴性**——vignette 从未写“无梭形肿胀 / 无被动伸指痛”，只写了压痛。那是封闭世界，不是召回失败。

引擎真正用得上的显式阴性基本都在：afebrile、无肺栓塞、结核血清学阴性、无 Brugada、室壁厚度正常、CD34/Bcl-2 阴性、抗血小板抗体阴性。QTc 380 ms 原文也没写 “QTc normal”，抽成带数值的 `present` 是对的。

因此第六节第 2 点仍然成立，但机制要改写：硬约束打不响，是因为**指南特征在病例里根本没被陈述**（封闭世界缺口），不是因为抽取器把已写的阴性弄丢了。抽取漏检约占原文显式阴性的 1/7，且漏的不是判别用的那些。

逐条清单见 `EXPLICIT_NEGATIVE_RECALL.md` 与 `explicit_negative_recall_11.csv`。

## 十一、两个假设的交叉验证：判据组与频次权重

针对第五节的连词缺口与第六节的覆盖计数，提出并同时验证两条假设：

- **H1（判据组）**：同一句里由 `and` / `or` / `at least N` / 具名 n 征（Kanavel）连起来的发现，应抽成一组、按组求值一次，而不是拆成独立断言后等权相加。
- **H2（频次权重）**：一个发现在**本例候选集**里被越少的假设宣称，应赋予越大权重。\(k\) 是病例内计数，不是语料全局 IDF。

11 例的 top-1 差 1 格是噪声，因此配置扫描同时报 MRR 与 4000 次 bootstrap 区间；H2 另在 (候选, 发现) 配对层做置换检验（统计功效远高于 11 例）。

### 11.1 判据组怎么抽、怎么求值

**抽取侧。** 在指南抽取 prompt 里增加 `criterion_group` 三元组，并强制"一成员一断言、同组共享 id/logic/n"：

```63:75:analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL/run_trial_extraction.py
  "criterion_group": {{"group_id": "<short id local to this passage, e.g. g1, or null>",
                      "logic": "all" | "any" | "at_least_n" | null,
                      "n": <integer or null>}},
  "quote": "<verbatim substring of the passage, <=200 chars, that states this>"
}}

Criterion groups: when one sentence lists several findings that together form ONE diagnostic
criterion set, emit one assertion per member and give all members the same group_id, the same
logic and the same n. Use "all" for "A and B and C are required" or a named n-sign set such as
"Kanavel's four cardinal signs"; use "at_least_n" with n for "at least two of the following";
use "any" for "one or more of". Never merge two findings joined by "and" into a single predicate
string -- split them into separate members of one group. Leave group_id null when the assertion
stands alone.
```

`--groups` 把缓存键从 `guideline` 换成 `guideline_groups`，避免与无组抽取串缓存。产物 `trial_extraction_k30oracleclean_groups.json`：17,029 条断言中 1,207 条（7.1%）进组，299 个有效组；logic 分布 `any` 781 / `all` 329 / `at_least_n` 63。Kanavel 四征被正确拆成：

```
subject=Flexor tenosynovitis  group=g1  logic=all  n=4
  - flexor posturing
  - fusiform swelling of the digit
  - tenderness to palpation along the flexor tendon sheath
  - pain upon passive digit extension
```

无组抽取里同一段塌成单条谓语 `"Kanavel's cardinal signs"`（见 4.5），对比即 H1 在表示层的收益。

**引擎侧。** 组键为 `(文档标题, 章节, 焦点假设, group_id, 归一化主语)`，丢弃不足 2 个成员的组；组成员不再单独进入层三求和：

```211:229:analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL/run_mechanical_engine.py
    # ---- criterion groups -------------------------------------------------
    # Members of one criterion set are evaluated together and contribute once,
    # instead of once each: summing them is what let a well-documented
    # competitor outscore the gold on sheer feature count.
    groups: dict[str, dict[tuple, list[dict]]] = defaultdict(lambda: defaultdict(list))
    if USE_CRITERION_GROUPS:
        for label, items in bound.items():
            for a in items:
                cg = a.get("criterion_group") or {}
                gid = cg.get("group_id")
                if not gid or cg.get("logic") not in {"all", "any", "at_least_n"}:
                    continue
                key = (a.get("_title"), a.get("_section"), a.get("_focus"), gid, norm(a["subject"]))
                groups[label][key].append(a)
        for label in list(groups):
            for key in list(groups[label]):
                if len(groups[label][key]) < 2:
                    del groups[label][key]
        grouped_ids = {id(a) for label in groups for key in groups[label] for a in groups[label][key]}
```

组内满足 / 违反按病例发现极性计数，再按 logic 一次给分。`w` 取组内最高 modality 权重，`spec` 取已满足成员的最大频次权重（与 H2 共用同一套 `specificity()`）：

```243:289:analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL/run_mechanical_engine.py
        for key, members in groups.get(label, {}).items():
            cg = members[0].get("criterion_group") or {}
            logic = cg.get("logic")
            size = len(members)
            need = cg.get("n") if isinstance(cg.get("n"), int) else None
            sat = [m for m in members
                   if m.get("_finding") and m["_finding"].get("polarity") == "present"]
            vio = [m for m in members
                   if m.get("_finding") and m["_finding"].get("polarity") in {"absent", "normal"}]
            ...
            if logic == "all":
                target = need or size
                met = len(sat) >= target and not vio
                if CLOSED_WORLD and not vio and len(sat) < target:
                    vio = [m for m in members if not m.get("_finding")]
                if vio and required and not soft_group:
                    eliminated.append({"layer": 1, "rule": "criterion_group_violated", ...})
                    continue
                delta = w * spec * (1.0 if met else (len(sat) / target - 0.5 * len(vio)))
            elif logic == "at_least_n":
                target = need or 1
                delta = w * spec * (1.0 if len(sat) >= target else len(sat) / target * 0.5)
            else:                                   # "any"
                delta = w * spec * (1.0 if sat else 0.0)
```

| `logic` | 满足条件 | 未满足时的得分 | 硬排除 |
|---|---|---|---|
| `all` | `\|sat\| ≥ (n 或组大小)` 且无显式违反 | `\|sat\|/target − 0.5·\|vio\|` | 组含 `required_for/obligatory` 且有违反 |
| `at_least_n` | `\|sat\| ≥ n`（缺省 1） | `0.5 · \|sat\|/n` | 无 |
| `any` | 至少一员 `present` | 0 | 无 |

`CLOSED_WORLD=True` 时，`all` 组里 vignette 从未提及的成员视为违反。257 号例的手工流程（"四征只满足压痛一项"）依赖这一假设：原文只写了压痛，没写另外三征缺失。

### 11.2 频次权重怎么算、怎么乘

\(k\) 不是语料文档频次。先把每条已接合、极性为 `asserted` 的断言记到"宣称该发现的候选集合"上，再在**本例候选列表**内计数：

```201:209:analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL/run_mechanical_engine.py
    claimants: dict[str, set[str]] = defaultdict(set)
    for label, items in bound.items():
        for a in items:
            f = a.get("_finding")
            if f is not None and (a.get("polarity") or "asserted") == "asserted":
                claimants[norm(f.get("label"))].add(label)
```

权重方案全部定义在 `specificity(k, N)`，其中 \(N\) 是本例候选数。只乘在**正向** \(\Delta\) 上（负向证据不因"很多候选都否认它"而减弱）：

```68:86:analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL/run_mechanical_engine.py
def specificity(n_claimants: int, n_candidates: int) -> float:
    c = max(int(n_claimants), 1)
    if WEIGHT_SCHEME == "none":
        return 1.0
    if WEIGHT_SCHEME == "binary":
        return 1.0 if c == 1 else 0.0
    if WEIGHT_SCHEME == "inv":
        return 1.0 / c
    if WEIGHT_SCHEME == "inv2":
        return 1.0 / (c * c)
    if WEIGHT_SCHEME == "k1bonus":
        return 2.0 if c == 1 else 1.0
    if WEIGHT_SCHEME == "idf":
        import math
        return math.log((n_candidates + 1) / (c + 0.5))
```

```353:357:analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL/run_mechanical_engine.py
            n_claim = len(claimants.get(norm(f.get("label")), ())) or 1
            if delta > 0:
                delta *= specificity(n_claim, len(candidates))
```

| 方案 | 公式 | 设计意图 |
|---|---|---|
| `none` | \(1\) | 基线：第六节的覆盖计数 |
| `binary` | \(1_{[k=1]}\) | 第一轮独有特征门控；约 87% 的证据被清零 |
| `inv` / `inv2` | \(1/k\)、\(1/k^2\) | 单调衰减 |
| `idf` | \(\log\frac{N+1}{k+0.5}\) | 平滑的候选集内 IDF |
| `k1bonus` | \(k=1\) 时 \(2\)，否则 \(1\) | 配对检验只支持 \(k=1\) 处富集，不是单调衰减 |

### 11.3 H2 在配对层不成立于其原始形式

配置扫描的统计功效几乎为零。直接检验的对象是 877 个（宽松接合）已接合、`asserted`×`present` 的 (候选, 发现) 对：\(P(\text{候选是金标等价} \mid k)\) 对基础率 0.135。置换在病例内打乱金标标签，使检验不受"某例贡献了多少对"干扰。

| 命中候选数 \(k\) | 配对数 | \(P(\text{金标}\|k)\) | lift |
|---:|---:|---:|---:|
| 1 | 52 | 0.192 | **1.43** |
| 2 | 67 | 0.075 | 0.55 |
| 3 | 144 | 0.153 | 1.14 |
| 4 | 182 | 0.137 | 1.02 |
| 5 | 126 | 0.127 | 0.94 |
| ≥6 | 306 | 0.131 | 0.97 |

**关系不是单调的。** 宽松接合下金标减竞争假设的平均 \(k\) 为 \(+0.96\)，置换 \(p=0.72\)；严格接合下点估计甚至反号（\(p=0.98\)）。\(k=1\) 处 lift 1.43 是真信号；\(k \ge 6\) 的表观富集是**金标粒度伪信号**：11 例里只有 2 例（326 Brucellosis、74 CPVT）的金标标签是精确匹配，其余多为 Abscess / Carcinoma / Thrombocytopenia 这类上位概念，天然宣称大量共享发现（粗金标 31% 的配对落在 \(k \ge 6\)，竞争假设只有 19%）。

因此 H2 的可辩护形式是**唯一性加成，不是单调衰减**。

### 11.4 配置扫描：两个主效应都为正，封闭世界为负

扫描格子：`groups ∈ {off, on}` × `join ∈ {strict, loose}` × `weight ∈ {none, binary, inv, inv2, idf, k1bonus}`，另加封闭世界因子（仅 loose）。H1 在 12 个配对格子上比（同一 join×weight，开关分组）；H2 在 4 个 (groups, join) 格子上比（相对 `none`）。

**H1。** 平均 MRR \(0.304 \to 0.327\)，12 格中 9 格改善，符号检验单侧 \(p=0.073\)。收益来自"一个组只计一次分"，不是来自组违反排除——后者在该触发的 257 号例上一次都没打响（见 11.5）。

**H2，相对纯求和：**

| 权重方案 | \(\Delta\)MRR | \(\Delta\)Top-1 | \(\Delta\)Top-3 |
|---|---:|---:|---:|
| `binary` | +0.083 | +2.25 | **−1.00** |
| `inv2` | +0.048 | +2.00 | **−1.75** |
| `idf` | +0.048 | +0.75 | ±0.00 |
| `k1bonus` | +0.036 | +0.25 | +0.50 |
| `inv` | +0.017 | +1.00 | −1.00 |

每一种加权都优于纯求和。激进方案（`binary`、`inv2`）用清零换 Top-1，Top-3 跟着崩；温和方案（`idf`、`k1bonus`）不伤排名。与 11.3 一致：该加的是 \(k=1\) 的加成，不是把 \(k \ge 2\) 的证据丢掉。

最均衡的一格是 `groups + idf + loose`：Top-1 = 1/11，Top-3 = 7/11，MRR = 0.351 \([0.207, 0.520]\)，中位排名 3。相对基线 `none + strict`（MRR 0.274，中位 5），522 从第 2 升到第 1（Catatonia），773 从第 6 升到第 3，326 从第 5 升到第 2；475 / 91 / 179 变差。bootstrap 区间与基线大量重叠，11 例不足以宣称配置间的显著差异，方向是稳的。

**封闭世界。** 开启分组的 6 个格子全部变差（`idf` 从 0.351 掉到 0.273，`binary` 从 0.362 掉到 0.300），并误杀 1 例金标。组违反规则总共只触发 2 次。原因：未接合的成员绝大多数是词面接不上，不是真的缺失；把它们当阴性等于把接合失败当成证据。

### 11.5 机制检查：Kanavel 组为什么没排除 257

引擎在 11 例上确实打出了组贡献（`all/4` 11 次、`any/4` 10 次等），但 257 号例的 Pyogenic Flexor Tenosynovitis **没有任何组贡献、也没有被排除**。两层原因：

1. **原文没有阴性。** vignette 只写 "focal tenderness over the flexor sheath"，从未否认梭形肿胀或被动伸指痛。封闭世界补上这一步之后，PFT 仍未被排除。
2. **四个成员全部接合失败**（宽松模式）：

| 判据组成员 | 病例发现 | Jaccard | 结果 |
|---|---|---:|---|
| tenderness to palpation along the flexor tendon sheath | focal tenderness | 0.14 | 不匹配 |
| fusiform swelling of the digit | right hand swelling | 0.20 | 不匹配 |
| flexor posturing | limited active digit motion | 0.00 | 不匹配 |
| pain upon passive digit extension | painful fluctuant mass | 0.00 | 不匹配 |

前两条是词面差一点（共享 `tenderness` / `swelling` 但 Jaccard 低于 0.25）；后两条需要临床等价（"活动受限" ≙ "屈曲位姿势"）。组结构抽对了，执行层收不到任何 `sat`/`vio` 计数，等价于组不存在。

### 11.6 合并判断与修复顺序

| 假设 | 判定 | 可辩护的实现形态 |
|---|---|---|
| H1 判据组 | 表示层成立，执行层被接合堵住；配置扫描正向弱显著 | 维持 `criterion_group` 抽取与按组一次计分；**不要**默认开封闭世界 |
| H2 频次权重 | \(k=1\) 处成立（lift 1.43）；单调衰减被金标粒度污染，置换不显著 | `k1bonus` 或 `idf`；不要 `binary`/`inv2` |

两条假设在同一处汇合：**概念接合是共同前置。** \(k\) 是在接合结果上数的，组员也必须先接到发现才能按 `all`/`any`/`at_least_n` 求值。接合修好之前，H1 无法执行，H2 的 \(k\) 统计本身有偏（漏接合 = 少数一个宣称者）。顺序仍是接合 → 判据组 → 唯一性加成 / 语料似然比，而不是并行。

## 十二、第八章六条修复的实现与隔离检测

第八章按收益排了六条修复。这一轮把它们全部实现成引擎上的独立开关，逐条做隔离检测：每条修复在**两个基线**上各测一次——B0 是第六章那个退化成覆盖计数的纯求和（`weight=none, join=strict, groups=off`），B1 是 11.4 最均衡的一格（`weight=idf, join=loose, groups=on`）。只在一个基线上出现的效应因此可见。11 例的排名指标一例之差就是噪声，所以聚合表配 bootstrap 区间，并且**必须**和机制检查一起读：机制检查问的是"这条修复瞄准的那条链现在通不通"，而不是 MRR 动了几个点。

候选集换成四方法并集（collapse3c ∪ multistance ∪ IMPC ∪ MOSAIC Forest），11 例候选数从 9–16 扩到 10–23，`build_trial_tasks.py --all-methods`。这么做是因为若干例的失败根本不在引擎里，而在候选集本身没装下正确粒度的标签。

### 12.1 隔离检测结果

| 修复 | B0 ΔMRR | B1 ΔMRR | 机制检查判定 |
|---|---:|---:|---|
| F2a 标记 token 成键 | ±0.000 | ±0.000 | **无效**：目标链 56.a（p63）基线就已经以 `containment` 接上了，是我把没坏的东西当坏的修 |
| F2b 嵌入接合 τ=0.60 | **+0.062** | **+0.032** | **有效**：接合率 0.068→0.114（B0）、0.149→0.167（B1）；326.a 从 `loose` 升级为 `embed` |
| F2c 锚定嵌入 τ=0.55 | +0.065 | −0.040 | **不稳**：加词面锚定在 B0 上略胜纯嵌入，在 B1 上反而伤 |
| F3 菌—病轴词干化 | +0.015 | ±0.000 | **有效但窄**：只让 326.c 从"完全未绑定"变成绑到 Brucellosis，多接 101 条断言，其余 10 例不动 |
| F5a 枚举夹逼 | +0.015 | ±0.000 | **有效**：15,642 条断言里 371 条（2.4%）relation 出界，`associated_with`(126)、`risk_factor_for`(46+39+16)、`definition`(12) 三类占八成，全部映射回枚举内 |
| F1 语料似然比 | **+0.026** | −0.014 | **符号相反**：见 12.3 |
| F4b 组 `all` 强制必需 | ±0.000 | ±0.000 | **打不响**：11 例 `vio_total` 合计仅 8，且都不在金标身上 |

τ 是敏感的：B1 上 0.55/0.60 给 +0.04，0.65 掉到 −0.045，0.70 回到 0。嵌入接合是在**用一个阈值换准确率**，不是免费的语义理解。抽样 601 条纯嵌入命中，好的确实好（`cyanotic::cyanosis` 0.874、`paraspinal abscesses::epidural abscess` 0.646），坏的也确实坏且在同一区间：`echolalia::echopraxia` 0.779、`genuine parasitosis::parakeratosis` 0.672、`diarrhea::nausea` 0.603。**MiniLM 分不开"形近但临床相反"**，这个失败模式没有阈值能绕开。

### 12.2 F5b 逆命题：抽取修好了，排名反而更差

773.b 是真正的抽取失败——Merck 第 293 章写"血流初期左向右，因为体循环压力与阻力高于肺循环"，规则要的是它的逆命题。给抽取提示加了 `CONVERSE_ADDENDUM`（显式要求在陈述蕴含逆命题时把逆命题也写出来），只对目标病例 773 重抽。

抽取层**成功了**。逆命题臂比基线多出 22 条含"反转/右向左"的断言，其中包括字面意义上的取逆：

- `Eisenmenger syndrome -[feature_of]-> right-to-left shunt when pulmonary pressure exceeds systemic pressure`
- `Patent Foramen Ovale -[feature_of]-> right-to-left shunting of bubbles`

排名**失败了**，金标从第 3 掉到第 5：

| 候选 | 基线得分 | 逆命题臂 |
|---|---:|---:|
| Chronic Thromboembolic Pulmonary Hypertension | 13.654 | 13.702 |
| Eisenmenger Syndrome | 12.903 | 10.241 |
| Tricuspid Regurgitation | — | 9.561 |
| Cardiomyopathy | 5.446 | 9.114 |
| **Patent Foramen Ovale**（金标等价） | **6.250** | **8.851** |
| Congenital Heart Disease | 2.869 | 8.111 |

金标绝对分涨了 42%，但竞争者涨得更多。原因是结构性的：**逆命题提示是无差别放大器**。它对每一个假设都同样生成逆命题，而引擎没有任何机制知道 PFO 的那条逆命题是鉴别性的、Cardiomyopathy 的那条不是。这条修复在抽取层是对的，在排名层需要先有 12.4 里缺的那个东西。

### 12.3 F1 语料似然比：两次返工才拿到可用的表

想法是从 861K 切片语料里估 \(P(f \mid h)\)，用似然比给接合加权，把"泛特征"压下去。做到第三版才对：

**第一版（文档级 + 引擎分词器）废了。** QTc interval 的 lift 指向 HCM 而不是 Long QT，CPVT 的 topic 文档数为 0。两个原因：引擎的 `tokens()` 为接合优化，会丢短词和通用词，用在标题上把 "Long QT Syndrome" 切没了；`MIN_TOPIC_DOCS=3` 又太严。

**第二版（标题分词器 + 切片级计数）暴露了语料缺陷。** 换成保留短 token 的 `title_tokens`，并从文档级改成切片级计数以消掉长度混杂后，做了一次标题正确性审计（`audit_statpearls_titles.py`，抽 400 篇）：**33.3% 的 StatPearls 标题与正文内容无关**——标题是从参考文献里抓的，比如正文讲肌骨创伤、标题是《Removal of the Long Spine Board From Clinical Practice》。而且全部 367,799 条切片的 `article_id` 都是空的，无法按文章回溯。以标题为锚的主题定位在这个语料上不可靠。

**第三版（提及级锚定）可用。** 改成"候选名出现在切片正文里"来定义主题切片。这才拿到有意义的分布（522 例：Dementia 3822 切片、Catatonia 229、Vitamin B12 deficiency 有量）。

代价是这条修复的效果**依赖基线符号相反**：B0 上 +0.026（Top-1 0→2），B1 上 −0.014。B0 没有 idf，语料似然比补上了它缺的那层频次校正；B1 已经有 idf，再叠似然比是重复计数，把 326 从 3 推到 5、49 从 1 推到 3。**F1 和 idf 是同一件事的两种做法，不能叠。**

### 12.4 F6 粒度：候选集装得下正确标签，证据链却装不下

第八章说"多立场宽泛类要靠知识库强制拆分"。分两步做：

**F6a 四方法并集。** 候选集扩到 10–23。B1 基线 MRR 从 0.351（11 例老候选集）变到 0.367，但 `gold_eliminated` 从 0 变成 2——**候选集变大，误杀也变多**。

**F6b 语料亚型挖掘**（`mine_subtypes.py`）。这里返工了三次，因为亚型在语料里的表达方式根本不统一：

- 纯求和打分奖励啰嗦亚型；纯密度打分惩罚常见亚型。最后用平滑密度（精度与语料频次的折中）。
- 修饰语窗口从 3 词放宽到 4 词，才够装下 "spindle cell squamous cell carcinoma"。
- 加了嵌套短语去重。
- 加了 Hearst 模式通道做显式分类学抽取。

**两个通道必须都要**，因为它们覆盖互补：n-gram 密度擅长"叙述里顺带提到"的罕见亚型（257 的 collar button abscess），Hearst 模式擅长"教科书里显式枚举"的常见亚型（522 的痴呆各型）。单用任一个都会在另一半上失灵。

拆分后候选集扩到 16–36。对 257 号例做定点检验，24 个候选，`Collar Button Abscess` **确实进了候选集**，金标排名从第 3 升到第 2——但这个第 2 是宽泛类 `Abscess` 拿的，`Collar Button Abscess` 本身得分 **0.000，零条接合对**。往下追是两层饿死：

1. **检索饿死。** 421 条 passage 里 `Collar Button Abscess` 只分到 **1 条**，而 8 个宽泛类各自吃满 30 条上限。罕见亚型在 861K 语料里本就没多少材料，它带着 1/30 的证据预算进场。
2. **发现侧粒度已经先丢了。** 抽取确实从那 1 条 passage 里拿到了正确断言——`Collar-Button Abscess -[feature_of]-> dorsal web space swelling and tenderness`、`fingers held in abduction with pain on adduction`。但 257 的 16 条病例发现里没有"web space"、没有"abduction"、没有"fluctuance"，vignette 把它们抽象成了 `right hand swelling` / `focal tenderness` / `limited active digit motion`。**没有东西可以和这些断言接合。**

所以粒度问题不是"候选集里缺标签"这一层的问题。把标签补进去是必要的，但同一次抽象损失同时发生在 vignette 侧，补候选集救不回来。

顺带暴露一个打分病理：top-1 被挖掘噪声 `Adenopathy In Lyme Arthritis` 拿走（43.958 分，2 条 passage、45 对接合），高于 `Abscess`（29.935 分、39 对）。它的 2 条 passage 恰好是一段手部感染鉴别诊断的罗列，什么都提到了。这与 522/74/773 的"泛特征累积"是同一个病，只是这次泛特征的来源是挖掘噪声。

### 12.5 六条修复的复盘

| 修复 | 第八章的预期 | 实测 |
|---|---|---|
| F1 语料似然比 | 压泛特征 | 与 idf 冗余，不可叠加；且逼出语料标题 33% 不可用的缺陷 |
| F2 接合层 | 最大收益 | 唯一稳定为正的一条（+0.03～0.06），但受阈值支配，且分不开形近词 |
| F3 词干化 | 修菌—病轴 | 有效但只影响 1 例 1 条链 |
| F4b 判据组 | 修好接合后能打响 | 仍打不响：`vio` 总数 8，无一落在金标上 |
| F5a 枚举夹逼 | 清理槽位污染 | 有效，2.4% 的 relation 出界被夹回 |
| F5b 逆命题 | 修 773.b | 抽取修好、排名变差 |
| F6 粒度 | 拆宽泛类 | 候选集能补上，证据链补不上 |

## 十三、累加栈与残留失败的剖析

按 B1 上的隔离效应从大到小累加：`S1 +F2b60 → S2 +F2a → S3 +F3 → S4 +F5a → S5 +F1 → S6 +F4b`，两个基线各跑一遍（`sweep_fixes.py --stack`，四方法候选集）。

| 栈 | B0 Top-1 | B0 Top-3 | B0 MRR | B1 Top-1 | B1 Top-3 | B1 MRR |
|---|---:|---:|---|---:|---:|---|
| S0 基线 | 0/11 | 7/11 | 0.321 [0.224, 0.412] | 1/11 | 6/11 | 0.367 [0.236, 0.526] |
| S1 +F2b60 | 1/11 | 8/11 | 0.383 | 1/11 | 7/11 | 0.399 |
| S2 +F2a | 1/11 | 8/11 | 0.383 | 1/11 | 7/11 | 0.399 |
| S3 +F3 | 1/11 | 8/11 | 0.398 | 1/11 | 7/11 | 0.399 |
| S4 +F5a | 1/11 | 8/11 | 0.413 | 1/11 | 7/11 | 0.399 |
| S5 +F1 | 2/11 | 7/11 | 0.439 | 1/11 | 6/11 | 0.385 |
| S6 +F4b | 2/11 | 7/11 | **0.439 [0.280, 0.636]** | 1/11 | 6/11 | **0.385 [0.256, 0.538]** |

**六条修复全上，在均衡基线上买到 +0.018 MRR，Top-3 从 6 回到 6。** 这个数字在 11 例的 bootstrap 区间里完全淹没。B0 上的 +0.118 看着可观，但它衡量的是"修复替代了 B1 本来就有的加权与宽松接合"，不是新增能力。**修复的表观收益高度依赖你从哪个基线出发，且不可加**——S5 之后两个基线的方向就分岔了。

### 13.1 326 号例：宽松接合把金标淘汰了

累加栈最刺眼的一格：326 在 B0 上是第 **1**，在 B1 上是第 **12**。逐个消融 B1 的三个旋钮：

| 配置 | 金标排名 | Brucellosis 得分 | 淘汰 |
|---|---:|---:|---|
| `none + strict + groups=off` | 1 | 26.658 | — |
| `idf + strict + groups=off` | 1 | 20.160 | — |
| `none + strict + groups=on` | 1 | 26.658 | — |
| `none + **loose** + groups=off` | **12** | **30.175** | **Brucellosis** |
| `idf + loose + groups=on` | 12 | 16.554 | Brucellosis |

罪魁是 `join=loose`，而且不是通过打分——Brucellosis 在宽松接合下得分**全场最高**（30.175），是被**淘汰规则**踢出去的。淘汰理由可以精确定位到一条：

```
rule: required_but_absent
predicate: serologic tests
quote:  "the clinical diagnosis usually must be supported by the results of
         bacteriologic and/or serologic tests"
finding: serological test for tuberculosis   (polarity = absent)
```

一句话里叠了三个独立缺陷：

1. **接合漂移。** 宽松接合把 `serologic tests` 和 `serological test for tuberculosis` 接上了，丢掉了 "for tuberculosis" 这个决定一切的限定语。
2. **极性语义错位。** 该发现的 `absent` 指的是"结核血清学**结果阴性**"——这对布鲁氏菌病是**支持证据**（排除了结核）。引擎把 `absent` 读成"这项检查没做"，于是 `required_for` 判为未满足。检查类谓词的 `required_for` 需要的是"已执行"，不是"结果阳性"，当前 schema 没有区分这两种极性。
3. **模态被抬高。** 原文写的是 "usually must be"，带对冲；抽取记成了 obligatory，于是一条软要求获得了硬淘汰权。

这条链解释了为什么 `join=loose` 同时抬高接合率又杀死病例：**接合放宽的收益进打分、代价进淘汰，而淘汰是不可逆的**。一个可辩护的改法是让淘汰只接受 `strict` 接合、打分才用 `loose`——两条通路用不同的证据门槛。

### 13.2 剩余失败项归类

以 B1 + S6 的最终排名看，11 例里 1 例 Top-1、6 例 Top-3，5 例落榜：

| 病例 | 最终排名 | top-1 被谁拿走 | 根因归类 |
|---|---:|---|---|
| 326 Brucellosis | 12 | Epidural abscess | **淘汰规则误杀**（13.1），非打分问题 |
| 179 | 6 | Pulmonary Atresia with VSD | 上位概念更粗（缺"低氧所致"），且唯一正则命中是跨行伪共现，语料里本无此条 |
| 257 collar button abscess | 5 | Septic Arthritis | 双侧粒度损失（12.4），候选集与 vignette 同时抽象掉了 web space |
| 91 | 5 | Cavernous Angioma | 注入的 oracle 段落本身是伪共现（肝活检标志物表），抽取拒绝造规则是正确行为 |
| 56 spindle cell SCC | 4 | Leiomyosarcoma | 上位概念更粗；注入段落同样是伪共现（间皮瘤角蛋白段） |

五例里只有 **326 和 257 是引擎能修的**。91 和 56 的失败发生在 oracle 注入这一步之前——正则 oracle 的首位命中就是错段落，第九章已经记过这一笔（26 条里 4 条首位正则命中是伪共现）。179 的目标断言在语料里不存在。

把这两类分开之后，真实结论是：**在 11 例这个规模上，六条修复合起来把可修的失败修好了 0 例。** 326 是修复引入的新失败（宽松接合是 B1 的组成部分），257 是被两层抽象夹住的老失败。

### 13.3 这一轮学到的

1. **"修复清单"的排序是靠不住的。** 第八章按预期收益排的六条，实测里排第一的 F2 是唯一稳定为正的，排第二的 F1 与既有的 idf 冗余，排第三的 F2a 修的是没坏的东西。隔离检测的价值不在于确认，在于证伪。
2. **两个基线是必需的，不是冗余。** F1 在 B0 上 +0.026、B1 上 −0.014；F2c 在 B0 上 +0.065、B1 上 −0.040。只测一个基线会把"补齐缺失的加权"误报成"新增能力"。
3. **打分通路和淘汰通路要分开设证据门槛。** 326 证明了同一个接合放宽在两条通路上一个是收益一个是灾难。
4. **粒度损失是双侧的。** 补候选集只补了一侧；vignette 侧的抽象（web space tenderness → focal tenderness）没有对应的补法，因为那是数据集构造时就发生的信息损失。
5. **语料本身要审计。** 33% 的 StatPearls 标题与正文无关、`article_id` 全空，这个缺陷在做 F1 之前完全不可见，是被"lift 指向错误疾病"这个症状逼出来的。任何以标题为锚的语料侧统计在这批数据上都要重做。

## 十四、案例研究：人工决策树与机械执行的逐例对照

前两轮报告给的是**人工能走通的判别流程**（`MANUAL_DECISION_TREE_REPORT.md`）和**四方法把鉴别 finding 挂错极性**的解剖（`DISCRIMINATION_REPORT.md`）。本轮引擎做的是另一件事：把指南断言与病例发现做成无模型的四层算法（硬约束 → 确认 → 加权求和 → 跨候选扣分）。十一例都是人工裁定为可分离的，因此每一例都可以把两条逻辑并排放：人走的是**顺序硬分支**，引擎走的是**断言覆盖计数加偶尔触发的淘汰**。差异能定位到具体的发现、断言和排序键，而不是笼统的"还不够准"。

对照配置取四方法并集候选集上的 B1+S6（`idf + loose + groups`，叠加全部修复开关），这是"技术修复尽量做完"之后的执行态。B0+S6 作为对照，用来把"修复本身引入的失败"从"修复之前就有的失败"里拆出来。人工流程一律取自 `manual_decision_tree_verdicts_22.csv` 的 `decision_flow`。

### 14.1 三种根因，必须拆开

失败要分三档，混在一起会把修得动的和修不动的平均掉：

| 档 | 代号 | 含义 | 修完这一档之后 |
|---|---|---|---|
| **技术性失败** | T | 当前管线的实现缺陷：抽取漏了 vignette 里写明的事实、单位对不上、接合漂移、排序键把确认项压过得分、`obligatory` 抽过了、菌—病主语绑不上 | 同一条人工分支在现有四层算法里**可以打响** |
| **数据性不可及** | D | T 修好之后，本地语料仍没有该分支所需的陈述，或候选集里没有与金标同粒度的标签，或 vignette 构造时就把决定性短语抽象掉了、原文里也不存在可补回的字段 | 任何接合/权重/组逻辑都救不回来 |
| **逻辑性不可及** | L | T 修好且数据在场之后，四层加法引擎的**计算模型**仍执行不了该推理：顺序排除、封闭世界、回答轴、两个发现之间的比较、时序共变、复合诊断、标志物层级、领地外推 | 要换表示或换算法，不是再加一个开关 |

T 是第十二、十三章已经在修的那一层。本章问的是另一句：**T 修完之后，人工逻辑还有多少步是引擎表达不了的。** 下面每例都按"人工分支 → 引擎实际做了什么 → T / D / L"写。排名未注明时一律指 B1+S6。

### 14.2 总表

| 病例 | 人工第一刀 | 引擎 top-1（金标位） | 主导残留 | T 修完能否走上人工树 |
|---|---|---|---|---|
| 74 CPVT | QTc 380 ms 排除长 QT | Long QT（2） | **T** | **能**。层一就是为这条设计的，死在单位与 pathognomonic |
| 49 残端阑尾炎 | 阑尾切除史 + 手术夹 | 盲肠憩室炎（3） | **T** | **能**。切除史写在 vignette 里，抽取没入集 |
| 326 布鲁氏菌病 | 先定回答轴，再暴露史 | 硬膜外脓肿（12，金标被淘汰） | **T**（误杀）+ **L**（轴） | **部分**。B0 上已是第 1；B1 的宽松接合把金标踢掉 |
| 119 汗孔角化 | 角样板层 → 汗孔角化 | Porokeratosis（1） | **D** 亚型 | **第一刀已经走对**；EPPP 不在候选集 |
| 522 紧张症+DLB | 紧张症征 → 排除谵妄；波动+视幻觉 → DLB | 维生素 B12 缺乏（2=Catatonia） | **T** + **L** 复合诊断 | 紧张症可到第 1；"继发于 DLB" 扁平排序表达不了 |
| 773 IPAH+PFO | 肺动脉压低于主动脉压 → 排除 Eisenmenger | Eisenmenger（2=PFO） | **L** | 不能。缺"两发现比较"和顺序排除 |
| 257 领扣状脓肿 | Kanavel 只满足 1/4；病灶在指蹼 | 化脓性关节炎（5=Abscess） | **T** 抽取粒度 + **L** 封闭世界 | 脓肿层可接近；四征排除与亚型准入仍不可及 |
| 475 神经痛性肌萎缩 | 失神经超出骨间前神经 | 单神经病（2；AIN 37 分被误杀） | **T** 误杀/极性 + **L** 领地外推 | T 修完 AIN 会回到 top-1；第 2 步仍不可及（详见 14.3.1–6） |
| 56 梭形细胞鳞癌 | p63 定上皮起源 | 平滑肌肉瘤（4=Carcinoma） | **L** 标志物层级 | p63 已接合；SMA 与 p63 等权，层级表达不了 |
| 91 血管肉瘤 | CD34− 排除 SFT/HPC | 海绵状血管瘤（5=Hemangioma） | **D** | 语料没有这组对照，人工也标了 `needs_outside` |
| 179 低氧性血小板减少 | 四时点血小板与 SaO2 同向 | 肺动脉闭锁+VSD（6=Thrombocytopenia） | **D** + **L** | 语料无此规则，且引擎没有时序共变算子 |

**两例是纯 T、修完就能走上人工树（74、49）。** 其余九例里，119 的第一刀已经机械执行对了；326 在不做宽松接合时也能走到金标；剩下六例的残留是 D 或 L，再叠加第十二章那类开关不会改变可达性。

### 14.3 逐例

#### 74 CPVT — 人工树与层一设计重合，死在单位和排序键（T，可修复）

人工三步都是排除：室壁厚度正常 → 排除 HCM；QTc 380 ms → 排除长 QT；无 Brugada 波形、电解质正常 → 排除 Brugada 与代谢性；剩下"结构正常心脏 + 肾上腺素能应激下 VF" → CPVT。鉴别报告里这是极性反转的标准样本：三个方法把 QTc 380 ms 写成了支持长 QT。

引擎这边，发现集合其实已经具备走完这棵树的原料：`QTc interval = 380 ms`、`wall thickness [normal]`、`Brugada pattern [absent]`、`electrolytes [normal]`、`valvular abnormalities [absent]`。层一也确实排除了 Brugada（`required_but_absent type I pattern`）和代谢性。HCM 得分被打到 0。**CPVT 的分数（27.4）高于长 QT（22.5）**，却排在第 2，因为排序键是 `(是否淘汰, −确认条数, −得分)`：长 QT 靠 QTc 拿了两条 `pathognomonic` 确认，确认项压过了得分。

断点全是 T：

1. `threshold_ok()` 因 `sec` / `ms` 直接返回 `no_numeric_pair`，380 < 450 的比较从未发生（第四章 4.2）。
2. 抽取器把"提到 QTc"标成 `pathognomonic_for`，层二把**有 QTc 这个检查**当成了长 QT 的确诊，不管数值方向。
3. 嘈杂环境 / 肾上腺素能触发仍未入发现集（第三节 S5b 的 74.b），但前两步修好后这条不是必需的——人工树在排除长 QT 之后已经只剩 CPVT。

**T 修完之后没有 D、也没有 L。** 语料有 CPVT 的准入原文（manifest_cpg / PMC），vignette 有切点，schema 有 `threshold`，层一有 `threshold_violated`。这是十一例里最干净的"机械逻辑与人工逻辑同构、实现没接上"的例。

#### 49 残端阑尾炎 — 决定性病史在原文里，发现集里没有（T，可修复）

人工：CT 盲肠极部肿胀管状结构 → 阑尾样炎症；八个月前阑尾切除且病灶紧邻手术夹 → 残端而非原阑尾。四方法里 collapse3c / MultiStance 已经答对，鉴别报告记的是粒度而不是极性。

引擎把金标放到第 3（`Appendiceal stump appendicitis`，16.2 分），top-1 是盲肠憩室炎（34.6 分）。赢家的贡献是 `required_for` 挂在 CRP、腹部 CT、WBC 上——全是右下腹感染的泛特征。金标的贡献同样是中性粒细胞和右下腹压痛，**两条人工第二刀用的事实都没有进入发现集**：vignette 原文写着 "laparoscopic appendectomy performed 8 months earlier" 和 "adjacent to surgical clips"，抽取结果 16 条发现里既没有阑尾切除史，也没有手术夹。这与第三节 S5b 的 49.a 是同一条漏检。

StatPearls 对残端阑尾炎的定义（切除不全后残留过长残端的复发性阑尾炎）语料里有。**T 修完（把已写明的手术史与手术夹抽进来）之后，人工第二刀可以机械执行**，没有语料缺口，也不需要封闭世界或跨发现比较。盲肠憩室炎之所以赢，只是因为引擎在缺那两刀的情况下退化成了覆盖右下腹感染的公共特征。

#### 326 布鲁氏菌病 — 人工先切轴；引擎在宽松接合下误杀金标（T 可部分修复，L 残留轴）

人工第一刀不是临床发现，而是**回答轴**：题目问病因，硬膜外脓肿是病变。之后才是暴露（破损手 + 未消毒羊胃）→ 血培养 GNB + 头孢丙烯无效 + 结核血清学阴性。鉴别报告记录四方法把暴露史正确挂到了 Brucellosis 候选下，选择器仍选了解剖病灶。

引擎在 B0+S6 上金标第 **1**（26.7 分），在 B1+S6 上第 **12** 且被淘汰。十三章已经把误杀钉死：宽松接合把 `serologic tests` 接到 `serological test for tuberculosis [absent]`，再把"结果阴性"读成"检查没做"，`required_but_absent` 一票否决。暴露史本身已经接上了（`caused_by → exposure to unpasteurized sheep stomach`，F2b/F3 的目标链）。赢家硬膜外脓肿吃的是背痛、肌力下降、影像上的脓肿本身——人工明确划到另一条轴上的那些发现。

分档：

- **T**：淘汰与打分必须分门槛（十三章已写）；菌—病词干（F3）在 B0 上已经让 326.c 绑定成功。这两项修完，B0 的第 1 可以保持。
- **L**：引擎没有"本题要病因还是病灶"的算子。解剖发现对硬膜外脓肿是合法 `feature_of`，加法模型会一直给它分。B0 能赢是因为布鲁氏菌的暴露+发热特征在严格接合下足够独有；B1 一放宽，轴问题就从风险变成失败。轴不是开关能修的，要在任务层编码问题类型。
- **D**：无。Merck 有羊/山羊与未消毒乳制品的传播途径。

#### 119 疣状汗孔角化 — 第一刀机械执行对了（本轮唯一的同构成功）

人工：发育良好的角样板层 → 汗孔角化，排除 Darier / Grover / 银屑病；不沿 Blaschko 线 → 排除线状；三月内播散 + 剧痒 + 嗜酸细胞 → EPPP 而非 DSAP/DSP。鉴别报告里四方法把角样板层挂到了 Darier/Grover 上。

引擎 top-1 就是 `Porokeratosis`（11.3 分）。贡献里有 `pathognomonic cornoid lamellae`（+2.0）和 `feature_of cornoid lamellae`（+2.4）——**人工第一刀被原样执行了**，而且走的是层二确认，不是覆盖计数。发现集里有 `cornoid lamellae`、`eosinophil infiltrate`、`pruritic papules`、掌跖口腔未受累。Darier/Grover 没有被硬排除（Grover 仍在第 8），但已经排在金标后面。

残留全在第一刀之后：

- **D**：候选集只有 `Porokeratosis`，没有 EPPP。人工第三刀（嗜酸细胞+急性播散）即使全接上，也没有更细的标签可点。这是第三节说的"强召回不等于同粒度"。
- **L**：从汗孔角化再分型需要顺序过滤（分布、病程），加法模型不会做"先锁定属再分种"。
- **T**：无阻断项。角样板层的接合是 exact/containment，不依赖嵌入阈值。

这一例证明：**当人工第一刀是指南里写成 pathognomonic 的单发现、且候选粒度恰好停在那一层时，机械逻辑与人工逻辑可以重合。** 十一例里只发生了一次。

#### 522 紧张症继发于 DLB — 紧张症可走到，复合结构走不到（T + L）

人工：模仿动作 / 模仿顺从 / 缄默 / 凝视 → 紧张症，排除单纯谵妄与抑郁；波动性认知 + 反复视幻觉（DLB 两项核心）→ 病因是 DLB 不是 MDD。鉴别报告记的是复合诊断被拆散，三个方法答紧张症、一个答 DLB，无人合并。

引擎把 `Catatonia` 放到第 2（22.2 分），发现集里 **echopraxia、mitmachen、mutism、staring 全部在**，并且判据组打出了 `group:all/5 mutism`。谵妄被 `criterion_group_violated` 淘汰——这是人工第一刀里"排除单纯谵妄"的机械对应，而且打响了。top-1 却是维生素 B12 缺乏（66.3 分），贡献几乎全部来自发现 `B12`：数值是 **1154.67 pmol/L**（偏高，不是缺乏），引擎只看见"B12 这个检查存在"就按 `feature_of` / `caused_by` / `treated_by` 连加了八次。

分档：

- **T**：B12 缺乏需要的是低值，阈值/方向没执行（与 74 的 QTc 同构）；波动性（"intermittent"）仍未入集（S5b 的 522.a）。前一项修好后 Catatonia 会成为 top-1（现在只差一名，且领先者是假阳性）。
- **L**：金标是复合结构。候选集里 `Catatonia` 与 `Dementia` 是两个扁平标签，引擎一次只能点一个。人工第二刀"病因为 DLB"即使发现全在，也没有"A 继发于 B"的排序对象。第十一章的加法模型表达不了这个。
- **D**：Merck 有波动性认知相对特异于 DLB 的原文。缺口不在语料，在表示。

#### 773 IPAH 合并 PFO — 人工靠两个量的不等式排除；引擎把右向左分流加给了 Eisenmenger（L）

人工：右心导管 60/39 mmHg **低于**主动脉压 → 未达体循环水平 → 不符合 Eisenmenger；7.34 mm PFO 不是大量左向右分流；肺动脉造影排除 PE/AVM → 特发性 PAH + 并存 PFO。鉴别报告：四方法把 PFO 与右向左分流当作 Eisenmenger 的正面支持。

引擎发现集里两个压都在（`pulmonary artery pressure = 60/39 mmHg`、`aortic pressure [present]`），PFO 宽度与持续右向左分流也在，PE 与动静脉瘘为 `absent`。CTEPH 被 `exclusion_triggered: pulmonary hypertension` 淘汰（方向对，但是误用了排除）。金标侧 `Patent Foramen Ovale` 第 2（19.3 分），`Idiopathic Pulmonary Arterial Hypertension` 被淘汰。top-1 Eisenmenger（22.4 分）的贡献是肺动脉压、紫绀、**右向左分流**、主动脉压——人工用来**排除**它的那几条，被加成了支持。

F5b 已经证明：把 Merck 正命题的逆命题抽出来，PFO 绝对分上涨，竞争者涨得更多（第十二章）。抽取不是瓶颈。

- **T**：IPAH 被淘汰属于与 326 同类的硬约束误杀，可按"淘汰只走严格接合"修；两压的单位是齐的，但 `threshold_ok` 只比较**一条断言的阈值与一个发现**，不能比较两个发现。
- **L**：人工第一刀是 `PAP < Ao` 这个**跨发现谓词**，加上"先排除再命名"。四层算法没有比较两个发现的算子，也没有把排除当作控制流——排除只在单条 `excludes` 命中时触发，而指南写的是 Eisenmenger 的阳性特征（紫绀、右向左分流），不是"PAP 低于体循环则排除"。这是表示层不可及，不是接合没接上。
- **D**：Merck 第 293 章有大量左向右分流才导致 Eisenmenger 的原文。规则在语料里。

#### 257 领扣状脓肿 — 人工数四征；发现集先把指蹼和波动抽象掉了（T + L）

人工：波动性肿块 → 脓肿，排除蜂窝织炎；骨质完整 → 排除骨髓炎；Kanavel 四征只满足腱鞘压痛 → 不符合化脓性屈肌腱鞘炎；病灶在掌侧指蹼 → 领扣状脓肿。四方法一致答屈肌腱鞘炎，并把 web space 写成了它的支持证据。

vignette 原文有 "painful, **fluctuant** mass extending from the **palmar web space**"。发现集变成了 `painful mass`、`focal tenderness`、`right hand swelling`、`limited active digit motion`——波动、指蹼、掌侧中心全部丢掉。这不是 vignette 没写，是抽取粒度（T）。骨质完整倒是留下了（`bony anatomy [normal]`、`fracture [absent]`），但没有任何竞争假设因此被排除。

Kanavel 组抽对了 `all/n=4`（第十一章），执行层四个成员全部接合失败；vignette 又从未否认梭形肿胀与被动伸指痛，封闭世界是人工在用、引擎默认不开的假设（开了会误杀其他例）。金标只以 `Abscess` 在集内，第 5，得分 2.9，贡献是年龄和挫伤。top-1 化脓性关节炎吃的是 WBC 和年龄。F6b 把 `Collar Button Abscess` 补进候选集后它得 0 分：检索只分到 1 段，且发现侧已经没有 web space 可接。

- **T**：把原文已有的 fluctuance / palmar web space 抽成独立发现，脓肿 vs 蜂窝织炎的第一刀可以走；与 Kanavel 成员的词面接合（tenderness along flexor sheath ↔ focal tenderness）也属 T，但嵌入 τ=0.60 仍接不上（11.5 的 Jaccard 表）。
- **L**：四征"只满足一项"依赖封闭世界（没写 = 没有）。第十章核过：这不是阴性漏抽。引擎一开封闭世界，11 例整体变差并误杀金标。这条人工分支在当前计算模型里**故意不可执行**。
- **D**：领扣状脓肿在 Merck / Schwartz 有条目，但 861K 语料里可检索材料极少（1/30 段）。亚型准入即使发现侧修好，检索预算仍不够。这是数据密度问题，不是规则不存在。

#### 475 神经痛性肌萎缩 — 人工靠领地外推排除 AIN；引擎既没建成这条规则，又把假淘汰和极性接反写进了打分

本例四方法一致答骨间前神经综合征（AIN），人工树把它排除掉。机械侧金标 `Neuralgic Amyotrophy` 排第 2（3.55 分），top-1 是上位类 `Mononeuropathy`（8.62 分）。AIN 自己的分数其实是全场最高的 **37.3**，却被一条错误的 `required_but_absent` 一票否决。下面把人工逻辑、引擎实际应用的规则（含原文）和构建/应用对错拆开写。配置仍是 B1+S6。逐条接合与引语见 `dump_case_475.py` 的输出。

##### 14.3.1 人工逻辑（三步，每步都有 vignette 事实）

剥离选项后的原文关键句：

> weakness of the distal phalanx of the thumb and middle phalanx of the index finger, with inability to perform the “Ok” sign … electromyographic evaluation … neurogenic atrophy of muscles innervated by the anterior interosseous nerve, including the flexor digitorum profundus and pronator quadratus, **and also changes in the biceps brachii, triceps brachii, and deltoid muscles**. MRI … showed no abnormalities.

| 步 | 人工做什么 | 依据的发现 | 要排除 / 要准入的 |
|---|---|---|---|
| 1 | 承认 AIN 的阳性证据在 | OK 征消失、FPL/FDP/PQ 失神经、无感觉障碍 | 这一步**不**排除 AIN，所以四方法停在这里 |
| 2 | 领地外推：三角肌=腋神经，肱二头肌=肌皮神经，肱三头肌=桡神经，都不在 AIN 支配表里 | EMG 额外累及 biceps / triceps / deltoid | **排除孤立 AIN**（以及桡、尺单一神经） |
| 3 | 多神经/丛性分布 + 青年急性起病 + 既往健康 + MRI 正常（无结构压迫） | 同上，外加 22 岁、previously healthy、MRI normal | 准入急性臂丛神经炎 = 神经痛性肌萎缩 / Parsonage-Turner |

第二步是整棵树的刀。它不是“金标有一条独有阳性特征”，而是“竞争假设的解剖学外延被违反”。鉴别报告里 Collapse3c / MultiStance 已经把这三块肌肉挂到了 Neuralgic Amyotrophy 的支持 span 上，选择器仍选 AIN——方法失败与引擎失败同构，都发生在第 2 步没有变成排除。

人工引用的语料锚点有两处，职责不同：

- Merck 第 185 章：*Acute brachial neuritis (neuralgic amyotrophy, Parsonage-Turner syndrome) occurs primarily in men and typically in young adults*。这只支撑第 3 步的流行病学，而且本例是女性，锚得并不紧。
- Adams《神经病学》在本例检索命中里写了领地名单：*certain muscles involved in brachial neuritis, such as the serratus anterior, deltoid, biceps, or triceps, may be totally or almost paralyzed*。这才是第 2 步需要的阳性描述。AIN 侧对应的是 475.b：支配范围限于 FPL / FDP / 旋前方肌——StatPearls《Anterior Interosseous Nerve Syndrome Reconsidered》有 AIN 肌表，但**没有写成**“三角肌受累则排除 AIN”。

所以人工第 2 步是**用 AIN 的解剖学外延做蕴含**，不是从语料里读到一条现成的 `AIN -[excludes]-> deltoid`。裁定 `separable_corpus_grounded` 的根据是“领地名单 + AIN 肌表都在语料里，人可以把二者合起来”；机械抽取没有做这个合取。

##### 14.3.2 机械逻辑实际排了什么

| 位 | 候选 | 得分 | 接合/绑定 | 引擎处置 |
|---:|---|---:|---:|---|
| 1 | Mononeuropathy | 8.62 | 80/477 | 存活，取胜 |
| 2 | **Neuralgic Amyotrophy**（金标） | 3.55 | 19/91 | 存活 |
| 3 | Mononeuritis Multiplex | 1.04 | 13/131 | 存活 |
| 5 | Brachial Plexitis | 0.65 | 12/135 | 存活 |
| 13 | Anterior Interosseous Nerve Syndrome | **37.33** | 43/163 | **淘汰** `required_but_absent` |

若不去掉那条误杀，AIN 会以 37 分压过所有人，引擎就会和四方法给出同一个错答案。金标能排到第 2，部分是误杀的副作用，不是第 2 步走对了。

发现集 14 条里，人工三步用到的事实**都在**：OK 征、拇指/食指无力、AIN 肌群神经源性萎缩、biceps/triceps/deltoid 改变、无感觉障碍、腱反射正常、MRI 正常。475 不是 49 那种“决定性病史没入集”。失败在规则怎么建、怎么接到这些发现上、接到之后怎么用。

##### 14.3.3 引擎真正打分/淘汰用到的规则（原文 + 对错）

只列对排名有实质贡献的。判定拆两栏：**构建**指从段落抽成七元组对不对；**应用**指接到哪条发现、给出的 Δ 对不对。

**A. 把 AIN 淘汰掉的那一条（决定了 AIN 不能赢，也决定了金标不是赢在排除上）**

```
断言   Anterior Interosseous Nerve Syndrome
       -[required_for/asserted/obligatory/diagnosis]→ "advanced MRI techniques"
出处   statpearls / Anterior Interosseous Nerve Syndrome Reconsidered
引语   "Diagnosis of this variant relies on advanced MRI techniques"
发现   MRI of the left upper extremity   极性 = normal
接合   containment
处置   layer-1 required_but_absent  → 淘汰 AIN
```

- **构建：错。** 原文说的是“这一**变体**的诊断依赖高级 MRI”，不是 AIN 本体的必要检查；`modality` 从 “relies on” 抬成了 `obligatory`。与 326 的 “usually must be” 同一类过抽取。
- **应用：错。** 病例做了上肢 MRI 且报告正常。`normal` 的意思是“检查已做、结果阴性”，引擎把它读成“必要项缺失”。326 的结核血清学是同一个极性槽位漏洞。
- 即便构建和应用都改对，这条规则也**不是**人工第 2 步。它与 biceps/triceps/deltoid 无关。

**B. AIN 在被淘汰前已经靠正确规则拿到了 37 分（人工第 1 步，引擎走对了）**

| 断言谓语 | 引语 / 出处 | 接到的发现 | 构建 | 应用 |
|---|---|---|---|---|
| inability to form an OK sign | “inability to form an OK sign”，StatPearls *The Median Nerve at the Carpal Tunnel* | inability to perform the "Ok" sign | **对** | **对**（+3.75） |
| inability to flex IP of thumb / DIP of index | “unable to flex the interphalangeal joint of the thumb and the distal interphalangeal joint of the index finger”，StatPearls *AIN Syndrome Reconsidered* | 接到了 OK 征（containment），没接到更细的拇指/食指无力 | **对** | **部分对**：临床等价，但粒度被 OK 征吞掉 |
| weakness of muscles innervated by the AIN | 同篇 AIN 综述 | AIN 肌群神经源性萎缩 | **对** | **对** |
| no sensory loss / without associated sensory loss | “presents solely with motor deficits / no sensory loss” | sensory deficits [absent] | **对**（AIN 是纯运动） | **对**（阴性对上阴性） |
| difficulty forming a fist | AIN 综述 | inability to form a fist | **对** | **对** |

这一组说明：AIN 的教科书特征引擎**会**用，而且用对了。四方法停在第 1 步，不是因为引擎找不到 AIN 规则。

**C. 同一条发现上，AIN 还吃到了构建反了或接反了的规则**

| 断言 | 引语 / 出处 | 接到 | 构建 | 应用 |
|---|---|---|---|---|
| `ability to make 'OK' sign` feature_of/asserted | “The patient may still be able to make an 'OK' sign”，StatPearls *Fractures and dislocations of the carpus* | **inability** to perform the Ok sign（embed） | **错**：腕骨骨折文说的是“AIN 未受累时仍能做 OK 征”，抽成了 AIN 的阳性特征 | **错**：ability 接到 inability，+3.75。MiniLM 在 “OK sign” 上对极性致盲，与 echolalia/echopraxia 同类 |
| `OK sign formation` feature_of/asserted | 同上 | inability to form a fist | **错**（同上） | **错** |
| `excludes/negated` thumb flexion strength | “No deficit should be expected in the AIN”，同一篇腕骨骨折 | 拇指远端指节无力 [present] | **错**：原文是“该骨折不应伤到 AIN”，不是“AIN 排除拇指屈曲” | 应用层按 negated×present 给了 −1.0，方向碰巧伤 AIN，机制是错的 |
| thenar atrophy / subtle weakness in APB | “Thenar atrophy may be seen in advanced CTS / a subtle weakness in the APB”，PMC 周围神经三联征 | AIN 萎缩 / 拇指无力 | **错主语**：CTS/APB 不是 AIN | **错接合** |
| `required_for` high index of suspicion | “A high index of suspicion by the clinician” | 食指中节无力（loose） | **错**：把套话抽成 obligatory 必要条件 | **错**：接到一条无关无力，+3.60 |
| `distinguishes_from` flexor tendon rupture | AIN 鉴别表 | **腱反射正常**（loose，共享 tendon） | 构建尚可 | **错接合**：腱病 vs 腱反射 |

AIN 的 37 分里，大约一半是 B 组的合法 AIN 特征，一半是 C 组的极性/主语/套话污染。层一把整候选一票否决，这些分没有进入最终排序，但它们说明：**即便拿掉误杀，引擎也不是在干净地执行 AIN 规则。**

**D. 金标 Neuralgic Amyotrophy 实际加分的规则**

| Δ | 断言谓语 | 引语 / 出处 | 接到的发现 | 构建 | 应用 |
|---:|---|---|---|---|---|
| +1.37 | muscle oedema | “MRI can recognize muscle oedema as an early feature of denervation”，PMC *Don't be perplexed by the plexus!* | **EMG** 的 biceps/triceps/deltoid **changes** | 原文说的是 MRI 上的水肿，抽成 feature_of 尚可 | **错**：病例 MRI 正常，水肿断言应接到 MRI，不该接到肌电图 “changes”。这是金标最大单条正分，接到了正确的肌肉名单、错误的检查轴 |
| +1.12 | anterior interosseous nerve involvement | “Other extraplexal nerves that tend to be affected are the … anterior interosseous”，同文 | AIN 肌群萎缩 | **对**：NA 可以累及 AIN（正是本例表现） | **对**，但无判别力——AIN 候选也宣称同一发现 |
| +1.12 | **posterior** interosseous nerve involvement | 同一句的后半 “posterior interosseous” | **同一条** AIN 肌群萎缩 | 构建对 PIN 本身是对的 | **错**：embed 把 AIN 与 PIN 接在一起（共享 interosseous）。F2b 的形近词失败 |
| +0.75×n | weakness / muscular weakness / muscle weakness | Adams “rapid development of muscular weakness”；StatPearls “onset of muscle weakness” | 左上肢无力 | **对**（泛） | **对**（泛），Mononeuropathy 也在吃 |
| +0.33 | weakness of the AIN innervated muscles | “some patients also develop weakness of the AIN innervated muscles”，PMC 正中神经近端卡压 | 左上肢无力（embed，丢掉了 AIN 限定） | **对** | **部分错**：限定词在接合时丢失 |
| −0.40×n | sensory symptoms / sensory deficits | “leads to both motor and sensory symptoms”；“Sensory deficits may also be noted in **some** patients” | sensory deficits [absent] | 后一条 modality 已是 occasional，前一条抽成 typical 过重 | 应用按 typical 缺席扣分。本例无感觉障碍与 NA 的运动型相容，人工不扣这一刀 |
| −0.40 | sufficient_for MRI；feature_of imaging | “MRI generally is more sensitive than ultrasound” | MRI [normal] | **错**：比较的是 MRI vs 超声灵敏度，不是“NA 需要 MRI 异常” | **错**：正常 MRI 在人工第 3 步是**支持**（排除结构压迫），引擎当缺席来扣 |

金标 3.55 分的结构：泛化无力约 +2.2，AIN 受累 +1.1（不判别），错误接到 EMG 的“水肿”+1.4，感觉缺席与正常 MRI 各扣一截。**人工第 2 步的三块肌肉，没有一条断言的谓语是 biceps / triceps / deltoid。** 它们只作为 “muscle oedema” 的错误接合对象出现。

**E. top-1 Mononeuropathy 为什么能到 8.62**

候选标签带别名 `nerve damage`、`Neuropathy`。主语接合把 **median / radial / ulnar / high-median neuropathy** 的断言整批绑到这个上位类上（containment / loose），再对拇指无力、食指无力做宽松谓语接合。贡献清单里反复出现的是：

```
median nerve injuries -[feature_of]→ thumb flexion / opposition / abduction
出处  statpearls / Fractures and dislocations of the carpus
引语  "Decreased strength of thumb flexion, opposition, and abduction"
接到  weakness of the distal phalanx of the thumb     各 +0.51
```

构建对正中神经损伤是对的；应用把**对掌/外展**（鱼际，腕管/低位正中）接到**拇指远端指节屈曲**（FPL，AIN）上——解剖上不是同一块肌。`group:any/5` 里谓语是 `numbness of the dorsum of the foot`，仍给了 +0.51：一组足部神经病成员里只要有一条接到上肢发现，`any` 整组得分。`context_type=definition` 不在 `SOFT_CONTEXTS` 里，定义段照常进层三。

Adams 那句领地名单也被检索到了，但主语抽成了 `Neuropathy`，绑定到 Mononeuropathy，谓语是 `muscle paralysis`，接到 biceps/triceps/deltoid：

```
Neuropathy -[feature_of/asserted/typical/definition]→ muscle paralysis
出处  textbooks / Neurology_Adams
引语  "certain muscles involved in brachial neuritis, such as the serratus anterior,
       deltoid, biceps, or triceps, may be totally or almost paralyzed"
接到  changes in the biceps brachii, triceps brachii, and deltoid muscles
```

- **构建：主语错。** 原文主语是 brachial neuritis，抽成了 Neuropathy。
- **应用：接到了正确发现，加给了错误候选。** 人工第 2 步最需要的原文，分数记在上位类头上，没有变成对 AIN 的排除。

##### 14.3.4 构建链上缺的那条规则

475.a（Parsonage-Turner 等同神经痛性肌萎缩）抽到了 `synonym_of`，不接发现，对排序无影响——构建对，应用无所谓。

475.b（AIN 支配限于 FPL/FDP/PQ）**没有**变成一条可执行的排除：没有任何断言是 `AIN -[excludes]-> biceps/triceps/deltoid` 或 `AIN -[required_for]-> 仅 AIN 肌群且组逻辑 all 被违反`。StatPearls AIN 综述写的是肌表和“与腱病鉴别”，Adams 写的是臂丛神经炎的肌表；抽取器没有跨文档做“AIN 肌表的补集 = 排除项”。这不是漏检某一段，是 schema 没有“外延违反”这种关系。

因此第 2 步在机械侧的命运是：

1. 正确原文被抽错主语，加给了 Mononeuropathy（T，构建）；
2. 金标侧三块肌肉只作为 MRI 水肿的错误接合对象（T，应用）；
3. AIN 侧没有排除通道，即使不去掉误杀也仍会靠第 1 步的合法特征赢（L：领地外推不是七元组能表达的蕴含，除非有人先写成 `excludes`）。

##### 14.3.5 这一例的 T / D / L 要改写

先前把 475 记成单纯的 L（finding 已接到金标但不能排除 AIN）。逐条规则之后，档要拆开：

| 档 | 本例里是什么 | 修完之后 |
|---|---|---|
| **T** | AIN 的 MRI `required_but_absent` 误杀（与 326 同构）；OK 征 ability/inability 极性接合；PIN/AIN 的 embed；NA 的 MRI 水肿接到 EMG；Mononeuropathy 别名把半条上肢神经病绑进来；Adams 领地名单主语抽成 Neuropathy | 去掉误杀后 **AIN 会回到 top-1**（37 ≫ 8），引擎与四方法对齐——也就是人工第 1 步被执行、第 2 步仍未执行。金标的 +1.37 也会从错误接合里消失，排名更差 |
| **D** | 无。AIN 肌表、NA 可累及 AIN、臂丛神经炎的 deltoid/biceps/triceps 名单、青年好发，检索都取到了 | — |
| **L** | 人工第 2 步是“AIN 外延的蕴含”，语料只分别陈述两个肌表。现有关系槽没有“外延违反”。`distinguishes_from` 在本例接到了腱反射，通道在，谓词不对 | T 全部修好之后，孤立 AIN 仍然无法被三块肌肉排除。这才是不可及的那一步 |

**修正后的结论：** 475 不是“鉴别 finding 接到了金标就够了”。那条 +1.37 是接错轴的假阳性。真正接到金标且构建正确的，是 AIN 受累和泛化无力——人工第 1 步的内容，不能排除 AIN。人工第 2 步在语料里以**两张肌表**的形式存在，抽取建成了加分项而不是排除项；引擎又用一条与领地无关的 MRI 误杀把 AIN 拿掉，让金标看起来像排到了第 2。把 T 修干净之后，本例会**退回**四方法的失败模式，只剩 L。

##### 14.3.6 抽取规则的逻辑缺陷：核验与归类

14.3.3 按「构建 / 应用」拆的是**引擎实际打分**的那几条。这里只核 **LLM 写出的七元组相对它自己的 `quote` 是否已经错了**。接合层的 PIN/AIN embed、Mononeuropathy 别名、`required_but_absent` 把 `MRI [normal]` 当成缺失，一律不算进本表。对象是 `trial_extraction_k30all4clean_groups.json` 本案 2,552 条原始断言（去重键 `(subj, rel, pol, mod, pred, quote[:80])` → **2,110** 条独特七元组）。主语含 `interosseous` 的 279 条，加上 `AIN Compressive Neuropathy` 共 285 条；NA / Parsonage / 臂丛神经炎主语 147 条。逐条标签冻结在 `case475_extraction_defect_census.json`。

全量启发式（`audit_475_extraction.py`）只打出 **115/2,110 = 5.5%**。这个比例不能当主结论：绝大多数是局部忠实的 `feature_of → weakness/pain`，启发式既不报 E11（引语对、病不对），也覆盖不了「this variant」折叠以外的辖域错误。**「大量逻辑缺陷」指的是高权槽位**，不是每条 `feature_of` 都反了。

**核验口径。** 一条断言算有抽取逻辑缺陷，当且仅当七元组对 `quote` 过声称、说反了、把另一种病的句子安到当前主语上、或把析取/可选写成合取。段落忠实、只是病不在本案 AIN vs NA 问题上，单列 **E11**（抽取对，当作本案规则则错）——这是焦点假设检索 +「段落里点名的病也要抽」的产物，不是引语被读反。

| 代号 | 缺陷 | 判定标准 | 本案核验（独特七元组） |
|---|---|---|---|
| **E1** 主语错置 | `subject` 不是引语在讲的那个病 | 引语点名 CTS/APB/thenar，主语写成 AIN；Adams「Affected patients usually have no fever」挂到 AIN（该段是臂丛神经炎）；Adams 领地名单主语抽成 `Neuropathy` | AIN←thenar/APB 各 1；Adams 发热/白细胞/ESR 的 `excludes` 6 条（AINS/AIS 各 3）；领地名单 3 条挂在 `Neuropathy` |
| **E2** 极性或条件取反 | 引语方向与 `polarity`/`predicate` 相反，或把条件句后件当无条件排除 | 「仍能做 OK 征」→ `feature_of ability`；「近端卡压才应有感觉障碍」→ `excludes sensory involvement` | 腕骨骨折文 ability / OK sign formation 2 条；条件句 1 条；同文「No deficit should be expected in the AIN」拆成拇指屈曲/对掌/外展 3 条 `excludes`（另 1 条重复主语，共 4） |
| **E3** 模态抬高 | `obligatory` 的引语带 may / usually / relies / should / whenever possible | 对冲语言获得层一淘汰权 | `required_for` 里 obligatory 且引语带对冲：启发式 4 条；MRI 变体 obligatory、血管炎活检「whenever possible」、桡神经「indicated when trauma」都在此列 |
| **E4** 关系槽错填 | 比较、套话、阳性率、定义写成 `required_for` / `sufficient_for` / `pathognomonic_for` | 抽取提示要求 `required_for` 仅用于必要诊断条件 | 「high index of suspicion」；「MRI generally is more sensitive than ultrasound」→ NA 的 `sufficient_for MRI`；「75% positive outcomes following surgery」→ AIN 的 `sufficient_for`；「surgery might be offered」同；Spurling「one of the most specific」→ `pathognomonic`；枚举外溢 `associated_with` 18、`more common in patients with` 2 |
| **E5** 辖域折叠 | 「this variant / this form」提升为父类的必要条件 | 变体规则当成 AIN 本体 | AIN 主语 `required_for advanced MRI techniques` **4 条独特**（typical/obligatory × AINS/AIS；另 1 条引语被截成「advanced MRI techniques」）。正是层一淘汰 AIN 的那条 |
| **E6** 语境剥离 | 段落框架是另一种伤病，AIN 只作为「未被累及的对照」 | 对照陈述变成 AIN 自身标准 | StatPearls *Fractures and dislocations of the carpus*：OK 征仍能做、AIN 不应有缺损。同文 *Carpal Tunnel* 里「presents solely with motor deficits」对真正的 AIN 反而是对的，不算 E6 |
| **E7** 空规则 / 流行病学当判据 | 谓语无法构成可执行的诊断条件 | 套话、发病率无差别、quote 短到无法支撑关系 | 「high index of suspicion」；Mononeuropathy `required_for NCS and EMG` 的 quote 只有「mononeuropathies」；「No difference … men and women」→ `excludes sex difference`（obligatory）；NA `excludes smoking/alcoholism/diabetes/thyroid` 的 quote 等于谓语单词；「compression cannot explain most AINS」把论文论题写成排除 |
| **E8** 误诊/模仿句 | 「常被误认为 / can mimic」抽成 `excludes` 或抽成模仿者自己的 `feature_of` | 鉴别提醒 ≠ 排除，模仿 ≠ 特征 | 「frequent misidentification as a ligamentous finger injury」2 条；「PIN, long thoracic, plexitis can mimic segmental weakness」抽成三者各自的 `feature_of segmental weakness`（6 条） |
| **E9** 虚假组 | `or` 写成 `all`；可选发现强制合取；下肢成员挂进上肢组 | `criterion_group` 改变命题结构 | IgA「petechiae **or** palpable purpura」抽成 `logic=all` 两条 `required_for`；**臂丛神经炎** `logic=all` 把「Sensory deficits **may also** be noted in some patients」收进合取——这是金标近邻标签上的在题缺陷；腓总神经 `any` 组含足背麻木（E11 兼 E9） |
| **E10** 治疗条件当诊断必要 | 手术指征、保守治疗失败写成 `required_for` | 诊断规则与治疗规则未分开 | 「If conservative therapy fails beyond 3 months」；「only if a prolonged period of nonoperative treatment fails」（主语 `AIN Compressive Neuropathy`）；尺神经「early intervention critical」 |
| **E11** 忠实离题 | 七元组对引语成立，主语却不是本案要判的病 | 焦点检索把 CIDP / 血管炎 / 跗管 / TTP / 尺桡神经段落送进来 | `required_for` 33 条里 **22** 条主键是 E11；`pathognomonic_for` **5/5** 离题（腕管、CIDP、Spurling、Finkelstein） |

**高权槽位计数（独特七元组，人工逐条，分母不是 2,110）：**

| 槽 | n | 相对引语可接受 | 相对引语已错（带 E1–E10） | 仅离题（E11 为唯一或主键） |
|---|---:|---:|---:|---:|
| `required_for` 全部 | 33 | **1**（AIN 支配肌无力） | **10** 主键在 AIN/单神经病侧 + 若干 E11 行还带 E3/E4/E9/E10 | **22** |
| 其中主语为 AIN 家族 | 8 | 1 | **7** | 0 |
| `pathognomonic_for` | 5 | 0 | 5 条在离题之上还有 E4 过声称 | 5 |
| `sufficient_for` | 17 | 0 | AIN 术后阳性率、手术「might be offered」、NA 的 MRI 灵敏度比较（≥5） | 跗管/尺神经电生理等 |
| AIN `excludes` | 33 | **11**（无感觉障碍）+ **3** 边界（创伤不符合 *syndrome* 定义） | **19** | 0 |

AIN 家族 8 条 `required_for` 的主键：E5×4、E7×1、E10×2、OK×1。层一用来淘汰 AIN 的就是 E5（再叠加 E3 的 obligatory）。**不是人工第 2 步，也不是接合层发明的。**

`required_for` 里互相矛盾的在题套话（都挂在候选 `Mononeuropathy` 上，本例 top-1）：Harrison「诊断可通过查体作出」→ `required_for clinical examination / obligatory`；Merck「临床诊断但应用电生理确认」→ `required_for electrodiagnostic tests / obligatory`；NCS 综述 indications 段 quote 只有「mononeuropathies」→ `required_for NCS and EMG / obligatory`。三条相对引语都过声称，且第 1、2 条互相否定。

**AIN `excludes` 33 条拆开：**

| 裁定 | n | 内容 |
|---|---:|---|
| 可接受 | 11 | 无感觉缺失 / numbness / tingling / sensory changes（定义性纯运动） |
| 边界 | 3 | 「直接外伤造成的 AIN 损伤不符合 AIN *syndrome* 诊断标准」——引语成立，写成诊断 `excludes` 过宽 |
| E7 流行病学 | 4 | 无性别差异、无优势侧差异，obligatory |
| E7 论题当排除 | 2 | 「compression cannot explain most AINS」 |
| E8 | 2 | 常被误认为韧带伤 |
| E2+E6 | 4 | 腕骨骨折文「AIN 不应有缺损」→ 排除拇指三动作 |
| E2 条件取反 | 1 | 近端压迫才有感觉 → 无条件 `excludes sensory involvement` |
| E1 | 6 | Adams 臂丛神经炎「通常无发热/白细胞/血沉」挂到 AIN |

可接受的那 11 条正是人工第 1 步、也是引擎给 AIN 加分的那组。写错的 19 条里，**没有一条是「三角肌 / 肱二头肌 / 肱三头肌受累则排除孤立 AIN」**。抽取器在排除槽上并不是沉默，而是把流行病学、对照句、条件句、误诊句填进去了——缺的那条规则（14.3.4）和胡填的排除规则同时存在。

**在题、但不在 `required_for`/`excludes` 计数里的抽取缺陷（补充）：**

- 腕骨骨折文 `"The patient may still be able to make an 'OK' sign"` → AIN 的 `feature_of ability` / `OK sign formation`（E2+E6）。正是 14.3.3 里 +3.75 的那条，抽取当下已经反了。
- `"Thenar atrophy may be seen in advanced CTS"`、`"a subtle weakness in the APB is most commonly found"` → AIN 的 `feature_of`（E1+E6）。
- NA `distinguishes_from brachial neuritis`，引语其实是「急性肩痛后局灶性轻瘫提示臂丛神经炎」——把同义词/自身表现写成鉴别（E4）。
- 臂丛神经炎 `criterion_group logic=all` 收进「部分患者可有感觉缺失」（E9+E3）。金标近邻标签上，合取一旦进层一/组违反，会朝与人工第 3 步相反的方向走：本案可以没有感觉缺失。

**和「全量 5.5%」的关系。** 启发式召回低，因为：(1) `feature_of weakness` 相对引语经常是对的，只是无判别力；(2) E11 对引语成立，启发式不报；(3) 同一引语在 AINS / AIS 下重复，缺陷条数被放大但独特率看起来不高。按**会进层一的关系**看，`required_for` 对本案可接受率 **1/8**（AIN 家族）或 **1/33**（全槽），`pathognomonic_for` **0/5**，AIN `excludes` 大约三分之一是感觉缺失（对）、一半以上是填错的排除。缺陷是槽位选择性的，不是均匀噪声。

**对 14.3.5 的补充。** T 里「MRI 误杀、OK 征 polarity、Adams 主语」在抽取当下已经成立，不是引擎后处理单独造成的。F5a 枚举夹逼只把非法 relation 收成 `feature_of`，管不到 `required_for` 用错；F2 接合修的是谓语匹配，修不了「this variant」折叠。所以 475 的抽取逻辑缺陷是 T 的上游：**七元组在离开 LLM 时已经不能当作规则用。** 即便下一层接合完美，层一仍会吃到 E5/E3 的 MRI 条，层三仍会吃到 E2 的 ability 条。L（外延违反）仍然成立——正确抽取的排除槽里没有那条领地规则。

#### 56 梭形细胞鳞癌 — p63 已接合，被 SMA 等权淹没（L）

人工：牙龈恶性梭形细胞 + p63 阳性（即便全角蛋白阴性）→ 上皮起源 → 肉瘤样鳞癌，而非放射后肉瘤或真性肉瘤。前一轮曾判源缺口，定向检索后 PMC 有 p63/p40 灶性阳性确认上皮起源的原文，改判 `separable_corpus_grounded`。

引擎发现集里 IHC 面板完整：`p63 staining [present]`、`pan-cytokeratin [absent]`、`α-smooth muscle actin [present]`、`vimentin [present]`。金标绑定到粗标签 `Carcinoma`（第 4，9.4 分），p63 已经接到（+0.493）。top-1 平滑肌肉瘤（31.0 分）的最大贡献是 **α-SMA 阳性**（+1.88）——这条 IHC 在 vignette 里也是真的，人工靠的是**标志物层级**：p63 定谱系，SMA 在肉瘤样癌里可以阳性、不能用来定平滑肌源性。

- **T**：候选粒度停在 Carcinoma（F6 没把 spindle cell SCC 稳稳送进可打分标签）；56.b 的正则 oracle 首位是间皮瘤角蛋白段，抽取拒绝造规则是正确行为。
- **L**：引擎对所有 IHC 等权。没有"谱系标志物优先于分化标志物"的偏序。修好接合只让 p63 进加法，不会让它压过 SMA。这与 74 不同：74 有数值切点可进层一，56 的层级是本体知识，schema 里没有槽。
- **D**：PMC 有规则。不是源缺口。

#### 91 血管肉瘤 — 人工第二刀的对照在语料里不存在（D）

人工：CD31+ / Fli-1+ → 内皮分化；CD34− / Bcl-2− → 不支持 SFT / 血管外皮瘤；20 个核分裂/10HPF + 侵犯大脑镰 → 恶性，排除海绵状血管瘤。人工裁定为 `separable_needs_outside`：语料有 SFT 的 STAT6 重排，没有这组标志物对照。

引擎发现集里面板完整（CD31、Fli-1、CD34 absent、Bcl-2 absent、核分裂 20）。金标绑到 `Hemangioma`（别名表混入 Angiosarcoma，第三节的概念混淆），第 5，唯一贡献是 CD31（+0.636）。top-1 海绵状血管瘤（5.9 分）吃的是头痛和脑出血——血管源性肿物的泛特征。CD34 阴性没有触发对 HPC/SFT 的排除（SFT 得分 0，HPC 第 2 仍活着）。91.a 的 oracle 注入是肝活检标志物表，抽取拒绝是正确的。

- **T**：良性/恶性标签混在 Hemangioma 一条目里，上限不是 Angiosarcoma；核分裂阈值若有断言可以进层一。
- **D**：人工第二刀所需的对照陈述，定向检索已经判过不在本地六源。T 修完（正确绑定 Angiosarcoma、接合 CD34−）之后，仍然没有一条断言能说"CD34 阴性排除 SFT/HPC"。这是十一例里唯一把 `needs_outside` 坐实到机械层的例。
- **L**：恶性 vs 海绵状血管瘤还可以靠核分裂与侵犯，那是 T+阈值；挡死本例的是第二刀的语料缺口。

#### 179 低氧性血小板减少 — 规则不在语料，时序也不在引擎里（D + L）

人工：凝血与血涂片正常、抗血小板抗体阴性 → 不支持免疫性；IVIG 后血小板未升 → 再否定免疫；四个时点血小板与 SaO2 同向（80%→103k，95%→173k，85–87%→225k，80%→68k）→ 低氧驱动。裁定为 `separable_needs_outside`：语料只讲紫绀型先心病慢性低氧致继发性红细胞增多，不讲低氧致血小板减少。鉴别报告记的是答错轴（结构畸形 vs 血液学）。

引擎发现集把四个时点拆成了互相无关的重复项：多条 `oxygen saturation [present]`、多条 `platelet count [present]`，没有配对、没有方向、没有"同向变化"。抗体阴性、血涂片正常、PT/APTT 正常都在。金标只以 `Thrombocytopenia` 在集内，第 6。top-1 是 `Pulmonary Atresia with Ventricular Septal Defect`（24.3 分），贡献就是 vignette 里写明的心脏畸形——人工认为答错了轴的那个答案。免疫性血小板减少排第 2，抗体阴性没有把它排除掉（`absent` 只给了金标 −0.4，没有给 ITP 发 `exclusion_triggered`）。

- **T**：回答轴与 326 同构，可在任务层编码；ITP 的硬排除需要 `excludes` 断言接到抗体阴性上，属于抽取/接合。
- **D**：目标规则在语料里不存在（179.b 的正则命中是跨行伪共现）。任何检索深度、oracle 注入、逆命题提示都变不出一条没写过的病理生理。
- **L**：即使把"低氧致血小板减少"写进语料，人工第三刀仍是**四对测量的共变**。schema 没有时间、没有配对、没有相关。发现抽取把纵向数据摊成独立的 `present`，加法模型在结构上无法重建这条推断。

这是十一例里唯一 D 与 L **同时**不可及的：缺规则，且即使得规则也缺算子。

### 14.4 其余十例的规则抽取逻辑核验

口径与 14.3.6 相同：只核指南七元组相对自己的 `quote`，不计接合与 `required_but_absent`。对象仍是 `trial_extraction_k30all4clean_groups.json`。逐例标签冻结在 `case_extraction_defect_census_10.json`。病例发现抽取（阑尾切除史、指蹼波动、B12 高低）另列，不算指南规则。

E1–E11 里，**E5（this variant 折叠）在其余十例的 `required_for` 上没有再打响**，标本仍是 475。其余类均再现：E8（mimic 句当 `feature_of`）在 522/326/49/56/74 的独特断言里都能见到。另外出现了三类 475 高权槽里没独立出来、但这里反复打响、且不能并进旧类的缺陷：

| 代号 | 缺陷 | 为何不并进 E1–E11 | 判定标准 |
|---|---|---|---|
| **E12** 循环定义 / 能指当所指 | 把病名或「做了这项检查」写成该病的 `pathognomonic_for` / `required_for`，引语里没有可用的判据 | E4 是关系用错（比较句写成 sufficient）；E7 是空谓语（imaging）。E12 的谓语看起来像临床特征（prolonged QT），引语却只是病名本身 | 引语去掉病名后剩不下可执行条件 |
| **E13** 论元对调 | 发现与疾病互换主谓，或把治疗条件写成对并发症的 `sufficient_for` | E1 是主语安到另一种病；这里主语根本不是病。E2 是极性反了；这里槽位反了 | `pathognomonic_for` 的 subject 是体征、predicate 是病名 |
| **E14** 阈值幻觉 / 错数 | `threshold` 里的数字、比较符或单位引语没有，或与引语矛盾 | 提示写明 never invent a threshold。百分数抄成 0.xx 比例、且数字能对上引语的，不算 | 引语无该数，或引语是 90%、阈值写成 20–40 |

E9 在十例里多了一个 475 的 `or→all` 之外的写法，仍归 E9 不新开类：**一句析取拆成两条彼此独立的 `required_for/obligatory`**（326 的 bacteriologic and/or serologic；血培养 or 脑脊液培养）。层一只缺其中一条就会淘汰。

机制句只抽正命题、不写 F5b 要求的逆命题，记 **O1**（抽取不全），不记 E：写出的那条相对引语往往是对的。475 的领地外推仍是 O2/L。

**十例体量（独特七元组）。** `required_for` 合计 701，`pathognomonic_for` 107。分母仍然是高权槽，不是全量 `feature_of`。

| 例 | unique | `required_for` | `pathognomonic` | 新类 | 对本例排名是否卡在抽取写错 |
|---|---:|---:|---:|---|---|
| 74 | 2201 | 57（**42 条假必要**；含 440/460 的 `required_for` **0 条**） | 28 | E12、E14、G1–G3 | **是。** 层二靠 LQTS 循环定义；真切点在 `excludes`/`feature_of`；CPVT 双向 VT 全是 `feature_of` |
| 49 | 3277 | 96 | 5 | — | **否。** 残端规则写对了；漏的是发现抽取 |
| 326 | 2735 | 69 | 9 | — | **是。** 金标误杀的 `serologic tests` 在抽取当下已是两条独立 obligatory |
| 119 | 2509 | 33 | 14 | E13 | **否。** 角样板层 pathognomonic 写对，第一刀同构成功 |
| 522 | 3611 | 118 | 13 | — | **部分。** DSM 紧张症组写对；B12「低值」谓语也对，引擎无视高低是应用层 |
| 773 | 1895 | 75 | 1 | E12、E14 | **否（主导是 L）。** 右向左分流作为 Eisenmenger 阳性特征相对引语往往成立；逆命题缺的是 O1 |
| 257 | 2003 | 52 | 12 | — | **部分。** 「some or all」抽成 `all/4` 是 E9；Schwartz 四征拆分本身按提示是对的 |
| 56 | 3161 | 68 | 12 | E13 | **否（主导是 L）。** p63/CK 合取相对那句引语成立；草莓龈主谓对调是离题 E13 |
| 91 | 2230 | 41 | 10 | — | **否（主导是 D）。** SFT 的 STAT6/CD34 写对；缺的是本案标志物对照 |
| 179 | 2848 | 92 | 3 | — | **否（主导是 D+L）。** 低氧–血小板共变断言数为 0 |

#### 74 CPVT — E12 直接喂给层二

LQTS 的 8 条独特 `pathognomonic_for prolonged QT interval` 里，引语是 `"a condition termed long QT syndrome"`、`"congenital long QT syndrome"`、`"long QT syndrome (Fig.16.35 )"`、`"prolonged QT syndrome"`。这是 **E12**：病名循环成确诊特征。其中 `"congenital long QT syndrome"` 还带了引语没有的 `threshold >440 ms`（**E14**）。同一例里，另有若干 `feature_of` 把 `QTc >440/460/470/480 ms` 从引语里如实抄进 threshold——那些相对引语可接受。引擎拿去当层二确认、压过 CPVT 得分的，是循环定义那一组，不是带切点的那一组。

其余：Brugada type 1、ARVC epsilon 波，引语说了 pathognomonic，可接受。CPVT `required_for exercise test` 引语是 `"Exercise testing is advised"`（E4）。治疗适应证（心脏骤停史）抽成诊断 `required_for`（E10）。癫痫灶段落（E11）数量大，但不驱动本例排序。E4/E10 不是零星两条：下面按全量 `required_for` 核验。

##### 74 号例 `required_for` 全量核验（诊断为主）

口径与 14.3.6 相同：只判 `quote` 是否授权闭集 `relation`。E11（离题但局部忠实）、E3（modality）、E14（数字）不计入本比例。单位是 unique 七元组 `(subject, relation, polarity, modality, predicate, quote[:80])`，对象 `trial_extraction_k30all4clean_groups.json` 本案 2,582 条 → unique 2,201；高权槽 unique 225。冻结：`case74_highstakes_unique.json`、`case74_relation_error_census.json`。Prompt 规定 `required_for` **仅当原文说该发现对诊断 necessary**；层一只吃 `required_for`+`obligatory`。

| 槽 | unique | relation 错 | 错率 |
|---|---:|---:|---:|
| `pathognomonic_for` | 28 | 19 | 67.9% |
| `required_for` | 57 | **42** | **73.7%** |
| 其中 `obligatory` | 44 | 30 | 68.2% |
| `sufficient_for` | 6 | 5（完整原文下致病突变条方向对，见 G3） | 83% |
| 三槽合计（诊断必要/充分） | 91 | 66 | 72.5% |
| `excludes` | 134 | 134 | 100%（124 条 `negated`；见下） |
| 高权槽合计 | 225 | 200 | 88.9% |

`excludes` 的 100% 是系统性 polarity×relation 编码：schema 要求「发现**出现**→排除该病」，抽取却把 without / do not / 鉴别表 “No” 写成 `excludes`+`negated`。4 条 LQTS `"A normal QTc in men is less than 440ms"` 也落在这个槽上——正确应是 `required_for`+prolonged QTc `>440`。治疗切点（HOCM 50 mmHg、水杨酸 100、停飞）5 条，记 E10，下面当次要。

**诊断向 `required_for` 错型**（42 条里约 37 条；A 类过半）：

| 类型 | 机制 | 正确槽 |
|---|---|---|
| **A** 检查清单写成诊断必要 | Evaluation includes / diagnosis is based on / diagnosis requires … this includes 被拆成多条 `required_for`，常加 `obligatory` | 多数不抽；至多 `feature_of`/`typical`。主语是评估流程，不是疾病必备发现 |
| **B** 建议/可做的检查写成必要 | advised / may / should be considered；同句常有「阴性不能排除」 | 不抽 `required_for` |
| **C** 家系筛查 / 分子尸检写成先证者诊断必要 | essential / should 的对象是识别高危亲属 | 不进诊断规则 |
| **D** ICD/危险分层适应证写成诊断标准 | 「有 X 就该装 ICD」→「有 X 才能诊」 | `treated_by` 或不抽 |
| **E** 「缓解/治愈定义」写成「患病必要」 | epilepsy resolved after 10 years | 病程/预后 |
| **F** 治疗适应证（次要） | 手术/透析/停飞切点 | `treated_by`（F7 对 `context_type=treatment` 会改槽） |

共同机制：必要性词的**论元抓错**（`requires`/`essential`/`based on`/`includes` 的宾语经常是方法或亲属，不是发现 F）；**检查 vs 发现未分**（点名要做 Holter ≠ Holter 上必须出现双向 VT）；建议语气抬成 necessary；*extract every assertion* 把清单炸成 4–8 条；quote≤200 时常只抄检查名，原文的 or / may / at-risk 消失。

**案例 A1 — 「评估通常包括」→ 心肌病必须有 ECG。** Merck *Chapter 212. Cardiomyopathies*：

> Evaluation typically includes ECG and echocardiography and sometimes MRI. Some patients require endomyocardial biopsy … Other tests are done as needed to determine the cause.

同主题 AHA 综述：

> … followed by diagnostic tools including electrocardiogram, laboratory testing, imaging studies, and may require a myocardial biopsy to reach the definitive diagnosis. Echocardiogram, cardiac MRI, cardiac CT, and nuclear medicine imaging are the primary imaging modalities used for both work up and follow up …

语义：接诊工作流；活检只对部分人；影像是主要检查手段，不是「没有 MRI 就不能叫心肌病」。抽取：同一段拆成 ECG / echocardiography / CT / MRI / nuclear / laboratory testing 多条 `required_for`+`obligatory`，quote 如 `"Evaluation typically includes ECG"`。正确：不抽成疾病必备发现；`typically`/`sometimes`/`may`/`as needed` 否定 obligatory。原因：`evaluation/diagnosis`+`includes`+检查名被当成诊断标准条目；`some patients require biopsy` 的 `require` 作用域是「部分患者」，模型（以及 F7 的 `REQUIRED_CUE`）当成全局 necessity。

**案例 A2 — 本例 CPVT：「诊断与危险分层基于 A 或 B」→ 四条必要检查。** StatPearls *Indications for electrophysiologic testing…*：

> Diagnosis and risk stratification are based on the exercise stress test, Holter monitor, or ILRs combined with genetic testing.

语义：确诊/分层靠这些**检查手段**（运动试验、Holter **或** ILR，再结合基因）；不是「患者必须 Holter 阳性」。抽取：四条独立 `required_for`/`typical`，quote 往往只剩 `"Holter monitor"`、`"ILRs"`、`"exercise stress test"`、`"genetic testing"`。正确：四条都不是 `required_for`。患者身上的必要发现在专家共识里（结构正常心脏 ∧ 正常 ECG ∧ 运动诱发双向 VT）。原因：*diagnosis is based on X* 在医学文本里几乎总是「靠什么检查」；`or` 未进 `criterion_group.logic=any`。

同类：意大利 COCIS「Diagnosis **requires** a multidisciplinary approach. This **includes** clinical assessment, resting ECG, exercise testing, 24 h Holter monitoring, pharmacological stress tests, and genetic analysis.」`requires` 的宾语是 multidisciplinary approach；模型把 necessity 分发到每一个检查，五条全部 `required_for`+`obligatory`。这是 A 类句法核心。

**案例 B — 同句已经否认必要性。** PMC *Cardiac evaluation of paediatric athletes*（抽取缓存 `b941d706…` 同一次调用）：

> Exercise testing is advised, but a negative exercise test does not exclude a diagnosis if other sentinels such as syncope, family history or positive genetics are present.

语义：建议做运动试验；**阴性不能排除**。抽取：`(CPVT, required_for, exercise test, typical)` quote `"Exercise testing is advised"`，同调用里还有 `(CPVT, excludes, negative exercise test, negated)`。同段 Brugada：`"A high lead 12-lead ambulatory ECG may also help rule out an intermittent Type 1 Brugada pattern"` → `required_for`。正确：运动试验不抽 `required_for`；「阴性不能排除」不是 `excludes`（元语言否定）。原因：`advised`/`may` 抬成 necessity；后半句已是 `required_for` 的反证，模型做短语对齐而非整句命题。

**案例 C — `essential` 的对象是家系。** StatPearls *Evolving Diagnostic Criteria for Arrhythmogenic Cardiomyopathy*：

> Genetic testing is essential to identify at-risk individuals, as cardiac arrest can be the first presentation of ARVC.

语义：基因检测对**识别高危亲属** essential，不是「阴性基因就不能诊 ARVC」。抽取：`(ARVC, required_for, genetic testing, obligatory)`。正确：不是诊断 `required_for`；同文 `at least 1 criterion must be fulfilled from groups I or II` 才是。原因：字面命中 prompt 白名单 `essential`；不定式 `to identify at-risk individuals` 被丢掉。**F7 同样只扫 cue：这条错误 `required_for` 会留下。** 同类：SIDS 段 `"Postmortem genetic testing … should be considered, particularly when the family history is positive"` → channelopathy 的 `required_for`。

**案例 D — ICD 适应证当成 Brugada 诊断必要。** StatPearls 小节标题即 *Treatment / Management*：

> Current guidelines recommend ICD placement in individuals who have a history of cardiac arrest, demonstrate spontaneous Type I Brugada ECG patterns accompanied by syncope, or exhibit diagnostic Brugada ECG changes during a drug challenge test.

语义：ICD 高危适应证（`or` 析取）。没有晕厥的 Brugada 仍是 Brugada。抽取：心脏骤停史、I 型+晕厥 两条 `required_for`+`obligatory`，quote 截成短语。正确：`treated_by`；药物诱发 Type 1 可作诊断标准的析取支，应与 `"type I pattern necessary for the diagnosis"` 对齐，`logic=any`。原因：`who have X` 被读成疾病定义；诊断标准与 ICD 标准塌缩。

**案例 E — 「癫痫已缓解」写成诊断必要。**

> … the Task Force deems epilepsy as resolved in patients who are seizure-free and medication-free for ten years.

语义：十年无发作且停药 → 诊断**解除**。起病标准在 Harrison：`"definition of epilepsy as two or more unprovoked seizures"`（那条 `required_for` 是对的）。抽取：`(Epilepsy, required_for, seizure-free and medication-free for ten years, obligatory)`。原因：定义句模板过触发，没读 *resolved*。

**对照：同一例里真正该写 `required_for` 的句子。** 模型不是不会这个槽，而是 cue 一弱就泛化、cue 一强就不管论元。

| 原文 | 抽取 | 裁定 |
|---|---|---|
| *When present in at least 2 of V1–V3, the type I pattern **necessary for the diagnosis** is satisfied.* | `required_for` Type I | **对** |
| *CPVT is **diagnosed in the presence of** a structurally normal heart, normal ECG **and** unexplained exercise-induced bidirectional VT …* | 拆成 `required_for` normal ECG / structurally normal heart；双向 VT 常另写或丢失 | 槽位方向对，**合取丢失**（E9） |
| *takotsubo … **can only be made after** coronary angiography* | `required_for` angiography | **对**（F7 若只认 necessary/must/essential，会把这条误降） |
| *A normal QTc in men is less than 440ms* | `excludes`+`negated`+`normal QTc` | **漏写成 `required_for` prolonged QTc >440** |

最后一行是本例层一承重柱该落的位置：模型在 `required_for` 上过度生产检查清单，却把**唯一带数字的诊断切点**放进了 `excludes`。F7 能清掉 A 类中没有 `must/essential` 的行，清不掉 C 类 `essential to identify at-risk`，也**填不回**那条没被写成 `required_for` 的 440 ms 规则。`REQUIRED_CUE` 与错误同构：有 `essential`/`require` 的错句留下，没有这些词的对句（*can only be made after*、*diagnosed in the presence of*）反而被降。

##### 反方向：真正的 `required_for` 被归入其他 relation

上一小节是假必要进槽。这里只计「原文语义是诊断必要、却没写成 `required_for`」。检查清单（*An ECG is required*）写成 `feature_of` 比写成 `required_for` 更对，**不算**漏槽。对象仍是本案 unique 七元组。硬计数：**`required_for` 的 quote/predicate 含 440 或 460 的条数为 0。**

与 A–F 不对称：假必要 42/57；真必要条数少但更致命。F7 **只降不升**，看不见下面任何一条。

| 代号 | 错入的槽 | 机制 | 本例标本 |
|---|---|---|---|
| **G1** | `pathognomonic_for` | 把必要当成充分；「诊断」默认走 hallmark | Type I *necessary for the diagnosis* 双槽；LQTS tautology 8 条；ARVC 脂肪纤维定义句；SE >5 min 操作定义 |
| **G2** | `excludes`+`negated` | 把切点/缺席必要编成「正常值排除该病」 | LQTS `normal QTc <440/460`（4 条 unique）；酒精性心肌病 *absence of other etiologies*；HCM 定义性 *in the absence of CAD/HTN* |
| **G3** | `feature_of`（或出界 `defined_as`） | 合取里阳性支降成典型特征；定义句不进必要槽 | CPVT 共识第 1 条的双向 VT；*QTc is prolonged (>440 msec…)*；*HCM is defined as LVH* |

**案例 G1 — 已写明 necessary，仍进充分性槽。** 与 A 类对照：同一篇 StatPearls *Cardiac pain… > Issues of Concern*：

> When present in at least 2 of the three precordial leads, V1, V2, and V3, the type I pattern necessary for the diagnosis is satisfied.

语义：Type 1 形态出现在 ≥2 个右胸导联，是 Brugada 诊断的**必要** ECG（不是单独充分）。抽取：**同一 quote 两条**——`(Brugada, required_for, type I pattern)`（对）和 `(Brugada, pathognomonic_for, type I pattern)`（错）。层二会吃后一条：病例一旦有任何「Type 1 样」接合，就按确诊加分，而不是按「缺了则不能诊」淘汰。原因：prompt 把 *necessary for the diagnosis* 与 *pathognomonic / diagnostic / hallmark* 写在相邻规则；模型见到 for the diagnosis 走充分性默认。双槽说明它不是漏写 `required_for`，而是**额外发明了一条充分性规则**。

LQTS 8 条 E12（*termed long QT syndrome* / *prolongation of the QT segment*）是同一偏置的病名版：定义性 QT 延长若要进诊断规则，槽应是 `required_for`，不是 `pathognomonic_for`。引擎拿去压过 CPVT 的是这组充分性断言。ARVC 组织学「replacement of myocytes … with fibrous tissue and fat cells」无 pathognomonic 用语，却写成 `pathognomonic_for`——疾病定义更接近「缺了不能叫 ARVC」的必要，不是单独确诊。SE：*Seizures lasting more than 5 minutes … meets the definition of status epilepticus* → `pathognomonic_for`；操作定义是必要且充分，抽成 patho 把「不到 5 分钟则不是 SE」弄丢了。

**案例 G2 — 层一承重柱写成排除槽，且不带切点。** 运动员 SCD 预防综述 *Evaluation*：

> The most common cause of prolonged QT on an ECG is secondary to medication use. The absence of medication-induced QT prolongation warrants further investigation into a possible congenital etiology. A normal QTc in men is less than 440ms, and in women, it is less than 460ms. The following represents a scoring system to assess the probability of long QT syndrome in a patient.

语义：先排除药物性延长，再谈先天 LQTS；男 <440 / 女 <460 是**正常上限**，超过才进入 LQTS 概率评分。正确七元组：`(LQTS, required_for, prolonged QTc, obligatory)`，`threshold >440 ms`（男）/ `>460 ms`（女）。抽取：`(LQTS, excludes, normal QTc, negated)`，至少 4 条 unique（`Long QT Syndrome` / `Long QT syndrome` × 男/女）。层一 `excludes` **不读 threshold**：开火条件是发现 present。QTc 380 ms 与 500 ms 都是「做了 QTc 检查」，会被同等处理。380 ms 手工该排除 LQTS，靠的是切点，不是「有 QTc 这项检查」。

同主题另一段（与 G1 同一篇 Issues of Concern）把切点写在正向句里，仍不进 `required_for`：

> In all three, the QTc is prolonged (>440 msec in men, >460 msec in women), but in LQT1, the T wave is symmetric; in LQT2, the T waves tend to be lower amplitude and notched …

抽成 `(LQTS, feature_of, prolonged QTc, typical)`，threshold 往往从 quote 抄对了。相对引语局部忠实，但 **relation+modality 进不了层一**。本例 unique 里没有任何 `required_for` 携带 440/460。切点同时以 G2（`excludes`+negated）和 G3（`feature_of`/typical）两种弱形式存在，就是没有必要形式。

酒精性心肌病是半对半错：

> The diagnosis of alcoholic cardiomyopathy is non-specific. The key to diagnosis is a personal history of chronic heavy alcohol use and the absence of other etiologies.

前半 `(Alcoholic cardiomyopathy, required_for, Chronic heavy alcohol use)` 对；后半 `(…, excludes, Other etiologies, negated)` quote `"the absence of other etiologies"`。缺席必要应是 `required_for`「无其他病因」，或 `excludes`+**asserted**+其他病因。Harrison 对 HCM 同构：*defined as left ventricular hypertrophy that develops in the absence of causative hemodynamic factors, such as hypertension, aortic valve disease, or systemic infiltrative or storage diseases* → `excludes`+`negated`+hypertension / aortic valve / storage（G2），LVH 本身进了出界 `defined_as`（G3）。另有心肌病段落 *in the absence of coronary artery disease, hypertension, valvular disease* 抽成 `excludes` 且 predicate 写成 *absence of CAD*（双重否定）。

**案例 G3 — 合取阳性支降成 `feature_of`，正常支却写成必要。** CPVT 综述专家共识表：

> 1. CPVT is diagnosed in the presence of a structurally normal heart, normal ECG and unexplained exercise or catecholamine induced bidirectional VT or polymorphic PVCs in patients < 40 years of age
> 2. CPVT is diagnosed in patients (index case or family member) who have a pathogenic mutation.

语义：第 1 条是 **A ∧ B ∧ C**（结构正常心脏 ∧ 正常 ECG ∧ 运动/儿茶酚胺诱发双向 VT 或多形 PVC）；第 2 条是**充分**（有致病突变即可诊），不是必要。抽取：

| 成员 | 抽取 | 裁定 |
|---|---|---|
| structurally normal heart | `required_for`/`obligatory` | 槽对 |
| normal ECG | `required_for`/`obligatory` | 槽对 |
| **unexplained exercise … bidirectional VT / polymorphic PVCs** | **`feature_of`/`typical`**（该句至少 2 条；本案 CPVT 主语下双向 VT 十余条全部 `feature_of`） | **漏必要**：这才是诊断阳性支 |
| pathogenic mutation | `sufficient_for`/`obligatory` quote `"who have a pathogenic mutation"` | 槽位方向**对**（充分不是必要）；先前按残句把 6 条 sufficient 全打错，完整原文下这条应保留 |

层一若开火，会卡「心是否结构正常 / ECG 是否正常」，**不会**因为没有双向 VT 而淘汰鉴别；层二也不会把双向 VT 当确认。假必要（Holter/ILR、「建议运动试验」）占着 `required_for`，真阳性发现在层三与 LQTS 的泛特征等权相加。原因：*diagnosed in the presence of* 被读成「背景条件必要」，and 后面的心律失常当成伴随 `feature_of`；quote 截成短语后合取消失（E9 的成员级写法）。F7 对无 `necessary/must` 的 `feature_of` 不动，对无 cue 的 `required_for` 反而可能把结构正常心脏那条真必要降掉。

HCM 定义句进了枚举外的 `defined_as`：*Hypertrophic cardiomyopathy is defined as left ventricular hypertrophy that develops in the absence of …*。F5a 若夹逼，通常收成 `feature_of`，仍不是 `required_for` LVH。LVH 对 HCM 标签是定义性必要。

**不算反例（避免与 A 类对打）。** *An ECG is required* / *a careful history and an ECG are essential* → `feature_of`：评估工具，不应升成诊断 `required_for`。*mechanical ventilation may be required* → `treated_by`：对。*mutations … required for normal function of Na+, K+, and Ca+ channels* → `caused_by`：分子必要，不是诊断必要。

**与假必要合起来。** 不是「必要槽空着」，而是槽被检查清单占满，切点和合取阳性支写到 `pathognomonic_for` / `excludes` / `feature_of` 里。再鼓励模型多写 `required_for` 只会加重 A–F；要修的是论元结构（必要的是发现还是检查、合取哪一支、切点方向）。F7 清 A/B、留 C、发明不了 G2 的 440 ms 柱，还会误伤 G3 里没有白名单词的真必要。

#### 49 残端阑尾炎 — 指南规则不是断点

`Stump appendicitis -[caused_by]→ incomplete resection / long stump`、`incompletely excised appendiceal stump (>0.5 cm)` 相对引语成立。失败在病例发现抽取没把阑尾切除史和手术夹写入发现集。指南侧的问题是 E11/E4 常态：憩室炎 `sufficient_for` CT，阑尾炎 Alvarado `≥7 = Surgical consultation` 抽成 `sufficient_for` 诊断。

#### 326 布鲁氏菌 — E3+E9 就是误杀规则

Harrison：`"the clinical diagnosis usually must be supported by the results of bacteriologic and/or serologic tests"` 抽成两条：

- `required_for bacteriologic tests / obligatory`
- `required_for serologic tests / obligatory`

**E3**（usually must → obligatory）加 **E9**（and/or 拆成两条各自必要）。层一把阴性的结核血清学接到后一条上，金标被淘汰。同一模式：`"Diagnose Brucellosis by blood or cerebrospinal fluid cultures"` → 血培养、脑脊液培养各一条 obligatory。SEA `"MRI as the gold standard"` → `pathognomonic_for MRI` 与 `required_for MRI`（E4）。`"high index of suspicion"`（E7）再现。暴露史 `caused_by unpasteurized milk` 写对。

#### 119 汗孔角化 — 第一刀的 pathognomonic 写对了

`cornoid lamella` 作为 porokeratosis 的 pathognomonic / defining feature，引语是 `"will be diagnostic"` / `"distinctive histopathologic feature"`，可接受。同篇又抽了 `Porokeratosis -[distinguishes_from]→ cornoid lamella`，引语是「一度被认为是致病特征，后来在别的病也出现」——关系槽错（E4），没有毁掉层二那条确认。新类 **E13**：`actinic keratosis -[pathognomonic_for]→ invasive squamous cell carcinoma`，引语是 `"can potentially progress into"`（进展 ≠ 确诊）。NMSC 进展率抽成 porokeratosis 的 pathognomonic（E4）。

#### 522 紧张症+DLB — DSM 组写对；B12 谓语方向也对

Catatonia `at_least_n/3` 收 echopraxia 等，相对 DSM 引语可接受。Merck 把波动/视幻觉写成 AD 的 `argues_against`（指向 LBD）也写对。B12 `pathognomonic_for low serum vitamin B12 level` 谓语带 **low**，相对引语成立；引擎后来把 1154 当「有 B12 检查」连加，是应用层与发现抽取，不是这条指南断言把高低写反。`"a single blood test can be enough"` → `sufficient_for`（E4）。银杏剂量行是 E10/E11。

#### 773 IPAH+PFO — 正命题往往对；逆命题是 O1

Eisenmenger `feature_of right-to-left shunt` 相对 `"leading to a right-to-left shunt"` / `"which is known as Eisenmenger’s syndrome"` 成立——人工用来排除的发现，指南写成了阳性特征，这是 L 不是抽取读反。Merck `"systemic pressure and vascular resistance are higher than pulmonary"` 抽在主语 `Left-to-right shunts` 下，相对正命题忠实。本文件里没有 `"right-to-left when pulmonary exceeds systemic"`（**O1**；F5b 对照臂不在这份 `k30all4clean_groups` 里）。新类：CTEPH `pathognomonic_for pulmonary hypertension`，引语 `"pulmonary hypertension in CTEPH"`（E12）；Eisenmenger `"severe PAH"` 填了引语没有的 `>25 mmHg`（E14）。

#### 257 领扣状脓肿 — 「some or all」抽成合取四征

StatPearls：`"Presence of some or all of Kanavel’s cardinal signs (...)"` → 四个成员外加一条总称，`logic=all n=4`。引语是 some or all，抽取器用了提示里「具名 n 征收成 all」的默认，**E9**。`pathognomonic_for Kanavel signs` 引语只是 `"important to recognize"` / `"91 to 97% sensitive"`（E4：敏感 ≠ 确诊）。Schwartz 四征拆成四条 `all/4` 符合提示，相对「cardinal signs」名单可接受。领扣状 / 指蹼规则本文件里几乎没有（D 密度），不是把 web space 读成腱鞘炎。

#### 56 梭形细胞鳞癌 — 在题 IHC 相对引语往往对；E13 出现在离题句

`sarcomatoid squamous cell carcinoma` 的 `p63` + `pan-cytokeratin` `all/2`，引语 `"patchy p63 and pan-cytokeratin positivity"`，构建对。人工靠的是「p63 定谱系、SMA 不能定平滑肌」——引语若没写层级，抽成等权 `feature_of` 不算读反（L）。**E13**：引语 `"a red-purplish, granular gingivitis ... is a pathognomonic sign of granulomatosis with polyangiitis"`，抽成 subject=草莓龈、predicate=GPA。`"unlike sarcomatoid or spindle squamous cell carcinoma"` 抽成梭形细胞的 `feature_of p63`（E6）。滑膜肉瘤句 `"the exclusion of the t(X,18) rearrangement which is characteristic"` 丢掉 exclusion of（E2+E6）。

#### 91 血管肉瘤 — 抽到的对照不是本案那组

SFT `pathognomonic_for NAB2-STAT6`、`feature_of CD34/STAT6` 相对引语成立。GLUT-1 `"sensitive marker"` → `pathognomonic obligatory`（E4+E3）。`"characteristic imaging findings"`（E7）。PHACE `"one major criterion"` / `"two minor criteria"` 抽成谓语 `major criterion` / `minor criterion`，计数 2 丢掉（E7+E9）。本案 CD34− / Bcl-2− 排除 SFT 的面板不在命中段落里（D），不是把 STAT6 读反。

#### 179 低氧性血小板减少 — 目标规则抽取条数为 0

缺氧–血小板共变相关断言 0 条，与语料缺口一致。ITP/出血病的 `required_for` 大量是治疗套餐（E10）和 `"platelet count (normal = 150,000 to 500,000/ml)"` 把参考范围抬成诊断必要（E4）。Alagille 胆管稀少 pathognomonic 对引语成立，E11。

**病例发现抽取（不是指南七元组，但同是 LLM 抽取逻辑）：** 49 漏切除史与手术夹；257 把 fluctuance / palmar web space 抽成 painful mass；522 把 B12=1154 只记成检查存在；179 把四对 SaO2–血小板拆成互不配对的 `present`。后两条是发现侧的能指/去配对，和 E12 同构，只是发生在 vignette 抽取器上。

**跨例结论。** (1) E1–E11 是这套抽取器的稳定病谱，475 不是孤例。(2) 新独立类只有 E12/E13/E14；E9 要补上「析取 → 两条独立必要」这一写法，否则 326 的误杀会被算成接合问题。(3) 抽取写错足以改变排名的是 **74（E12 喂层二；G2/G3 漏写层一柱）和 326（E3+E9 喂层一）**；119 证明 pathognomonic 写对时第一刀可以同构；49/91/179/773/56 的主导残留仍是发现漏抽、D 或 L，不是把已有引语读反。(4) `required_for` 的错误是双向的：假必要（A–F）与真必要进错槽（G1–G3）同时存在，F7 只处理前一半里无 cue 的子集。

### 14.5 人工逻辑比机械逻辑多出来的算子

把十一例人工树用到、而四层引擎没有的操作收成一张表：

| 人工在用的操作 | 出现于 | 引擎对应物 | 缺失的档 |
|---|---|---|---|
| 单发现硬排除（QTc < 切点、角样板层、无 Brugada） | 74、119、74 的 Brugada | 层一 `threshold_violated` / 层二 pathognomonic / `required_but_absent` | 有槽；74 死在 T |
| 跨发现比较（PAP < Ao） | 773 | 无。`threshold` 只绑一条断言 | **L** |
| 顺序控制流（先排除再在幸存者里命名） | 全部 11 例 | 无。淘汰与打分并行，幸存者仍靠加法 | **L** |
| 封闭世界（没写 = 没有） | 257 Kanavel | 有开关；默认关，开了误杀 | **L**（与数据分布冲突） |
| 回答轴（病因 vs 病灶 vs 血液学） | 326、179 | 无 | **L** |
| 领地外推（超出 AIN → 排除 AIN） | 475 | 两张肌表分别抽成加分；无外延违反槽。`distinguishes_from` 接到了腱反射 | **L**（T 修完会让 AIN 赢） |
| 标志物层级（p63 ≫ SMA） | 56 | 等权 `feature_of` | **L** |
| 复合诊断（A 继发于 B） | 522 | 扁平 argmax | **L** |
| 时序共变 | 179 | 无时间、无配对 | **L** |
| 逆命题（正命题的取逆才是排除条件） | 773 | 主抽取文件里逆命题仍缺（O1）；对照臂 F5b 能抽，加法仍无差别放大 | **L**（外加抽取不全） |
| 语料中不存在的规则 | 91、179 | 无中生有做不到 | **D** |
| 候选集没有同粒度标签 | 119 EPPP、257 领扣、56 梭形细胞、522 复合 | F6 补标签补不了证据链 | **D** / 粒度 |

对照鉴别报告的失败模式：四方法的主导失败是极性/归属倒置（7/22）。引擎把极性反转收成了另一件事——**阳性特征的等权累加**。74 的 QTc、773 的右向左分流、257 的腱鞘压痛、475 的远端无力，在人工树里是排除竞争者的刀，在引擎里是给竞争者（或上位类）加分的项。极性并没有在 schema 里反转（74 甚至抽出了 `Long QT -[excludes]-> normal QTc`），而是在聚合层被淹没或从未拿去淘汰该淘汰的候选。

### 14.6 T 修完之后的天花板

把"只剩 T"的例从分母里拿掉，十一例的可达性是：

| 集合 | 例 | 含义 |
|---|---|---|
| T 修完即走上人工树 | **74、49** | 层一/发现抽取的实现缺陷，不改计算模型 |
| T 修完可到金标，但靠的不是人工第一刀 | **326**（严格接合下）、**119**（属级）、**522**（紧张症单列） | 可达标签粗于金标，或轴问题仍在 |
| T 修完仍走不上人工树 | **773、257、475、56、91、179** | L 且/或 D |

六例不可及里，91 与 179 的 D 在手工裁定时就已经标了 `needs_outside`，机械执行只是把这张状重新宣读了一遍。其余四例（773、257、475、56）语料里**有**规则，人工**能**走，引擎不能——缺口全在 14.5 那些算子，不是第十二章的接合/词干/枚举/似然比。

这把第八章的修复清单和第十三章的累加栈放回原位：那六条修复瞄准的是 T。十一例里 T 是瓶颈的只有两三例；把 T 修到隔离检测能看见的极限（B1+S6，MRR +0.018），正好停在 L/D 的边界上。再往上不是再加开关，而是换计算模型：顺序排除、跨发现谓词、轴、封闭世界的局部化、标志物偏序。其中封闭世界已经测过，全局打开是净亏损——257 需要它，其他例会被接合失败误杀。所以连"把人工假设搬进引擎"也不是一个总开关能做的。

## 十五、规则抽取逻辑缺陷怎么修：提示词以外的方法

14.3.6 / 14.4 把缺陷钉在七元组相对 `quote` 已经错了。F5a（枚举夹逼）和 F5b（逆命题加提示）已经试过：非法 relation 能夹，`required_for` 用错、`this variant` 折叠、循环定义喂层二，提示改不动。下面只收**不靠再写一段英文指令**的路线，并标明每条对应哪一类 E。来源是 2023–2026 的抽取/指南形式化文献，不是本管线的新实验。

先把边界说清：**约束解码只能保证 JSON 合法，不能保证内容忠实。** JSONSchemaBench（Geng et al., 2025）把 Outlines / XGrammar / Guidance 评在真实 schema 上，合规率上去了，语义错误率没有自动下去。本管线的 E1–E14 几乎全是内容错，enum 夹住 `relation` 只覆盖 E4 的「写出 associated_with」那一小截。

### 15.1 七条技术路线（按对现有 schema 的侵入性由低到高）

**A. 程序门闸：零模型，对高权槽立即能拦。**

提示已经要求 `quote` 必须是原文子串、阈值不得编造，但抽取器输出没有被检查就进了引擎。文献里对应的是「provenance / restoration」的最薄一层：元素必须能回到原文（AEVS 的 restore；财务报告三元组抽取里 regex 验主语把幻觉率从 65% 降到 1.6%，arXiv:2602.11886）。对本 schema 可执行、且直接打在已核缺陷上的规则：

| 门 | 打掉的类 | 对本例的标本 |
|---|---|---|
| `quote` 必须是 passage 的连续子串；否则丢弃 | 截断引语、空 quote（E7） | 475 NA `excludes smoking` quote=`smoking` |
| `threshold.value` 的数字必须出现在 quote（允许 `,` / 百分数↔小数）；否则丢掉 threshold 或整条 | **E14** | 74 循环定义行的 `>440 ms`；773 `"severe PAH"` 的 `>25 mmHg` |
| quote 含 may / usually / typically / should / advised / whenever possible / relies on 时，禁止 `modality=obligatory` 且禁止 `required_for` 进层一 | **E3** | 326 `usually must`；475 MRI `relies on` |
| 同一 quote 含 `and/or` 或 `or` 连接两个检查时，禁止拆成两条独立 `required_for/obligatory`；必须进同一 `criterion_group logic=any` | **E9 析取拆分** | 326 bacteriologic and/or serologic；血培养 or 脑脊液 |
| quote 含 some or all / one or more 时，禁止 `logic=all` | **E9** | 257 Kanavel |
| `pathognomonic_for` 仅当 quote 含 pathognomonic / hallmark / diagnostic of / will be diagnostic；`required_for` 仅当 necessary / required / must / essential for diagnosis | **E4、E12** | 74 `"a condition termed long QT syndrome"`；326 `"MRI as the gold standard"` |
| subject 的规范名必须能在 quote 里找到，或 quote 含 this/the variant/the syndrome 且能链到焦点——否则降权或丢弃 | **E1、E5** | 475 Adams 发热挂 AIN；MRI this variant |
| `context_type=treatment` 的 `required_for` 不得进层一 | **E10** | 475 保守治疗失败；74 心脏骤停史 |
| subject 是体征、predicate 是病名（可用 UMLS 语义型）→ 槽位对调，丢弃或翻转 | **E13** | 56 草莓龈 / GPA |

这一层对 74 的层二确认和 326 的层一误杀是对症的：两条排名卡点都是高权槽写错，不是 `feature_of weakness` 噪声。

**B. 锚定抽取 + 还原核验（AEVS 类）。**

[AEVS](https://www.mdpi.com/2073-431X/15/3/178)（Computers 2026）：先发现实体/关系/属性的字符级锚，再只允许从锚里组三元组，最后 extract-then-restore。消融表明降幻觉的主因是锚约束，不是更大的模型。实现见 [yyz-nbt/AEVS](https://github.com/yyz-nbt/AEVS)。对本管线：疾病名、检查名、数字、情态词先做成闭集，抽取器只能填锚 ID，不能自由生成 `advanced MRI techniques` 这种从「this variant」提升来的短语。E14、E12、E7 空谓语会被「锚里没有这个值」拦住。**拦不住**「锚都在、命题过声称」：`usually must` 和 `serologic tests` 都是真锚，拼成 obligatory `required_for` 仍然过 restore——这要靠 A 的情态门或 C 的 NLI。

**C. 把七元组说成一句话，用 NLI / 归因模型验蕴含。**

Echo-LLM：三元组口头化成假设，从原文取句，BART-NLI 判蕴含，阈值下拒绝。AttrScore（Yue et al., Findings EMNLP 2023）把归因分成 attributable / extrapolatory / contradictory。FActScore（Min et al., EMNLP 2023）把生成切成原子事实再对知识源计支持率。对本 schema：只对 `required_for` / `pathognomonic_for` / `sufficient_for` / `excludes` 口头化（全量 2k 条 `feature_of` 不必）。例如 74 的假设 *"Prolonged QT interval is pathognomonic for long QT syndrome"* 对前提 `"a condition termed long QT syndrome"` 应判 extrapolatory，不能进层二。326 的 *"Serologic tests are obligatory for diagnosing brucellosis"* 对 `"usually must be supported by bacteriologic and/or serologic tests"` 应判不蕴含（情态+析取都被压扁了）。代价是每条高权断言一次 NLI；可用较小的 NLI 模型，不必再调抽取 LLM。

局限：NLI 对「比较句当 sufficient」（E4 的 MRI vs 超声）有时仍判蕴含，因为句子确实在谈 MRI。关系槽过声称要叠加 A 的关键词门，不能单靠蕴含。

**D. 流水线拆开：先实体与断言状态，再关系。**

临床 NLP 的经典栈是 i2b2 的概念 → assertion → relation，而不是一枪打出七元组。Text2MDT（Zhu et al., arXiv:2401.02034）把指南成树拆成三步：三元组抽取、节点分组（显式 `logical_rel` ∈ {and, or, null}）、组树；encoder 流水线参数量小两个数量级仍能接近 LLM。FT-MDT（EMNLP 2025 industry）用 PI-LoRA 微调同一任务。i2b2 assertion 与 NegEx / NegBio / ConText（Peng et al., 2018 用依存图定否定辖域）以及 2025 年的综合 assertion 模型（arXiv:2503.17425，细粒度 LLM 在 Hypothetical 上比 GPT-4o +23 点）专门管极性与虚拟语气——这是 E2、E3 的本职，不该交给同一个 JSON 解码器。

对本管线的改法：焦点假设检索保留；抽取改成 (1) 段内疾病提及（含指示词，见 E）；(2) 每个疾病跨上的发现 + NegBio 断言状态；(3) 关系分类器只在「疾病跨、发现跨」闭集上选 `feature_of` 等。主语无法再被写成焦点病，除非该病在段内有跨（打 E1、E6、E11 的「段里没点名却挂了焦点」）。E9 交给分组子任务的 `and/or`，不要让 LLM 先拆成两条 `required_for`。

**E. 语言学前处理：共指、语义角色、组合事实性。**

- **共指 / 指示消解。** SemRep 的 sortal anaphora（BMC Bioinformatics 2016）把 "these drugs" 换成先行词再抽关系。E5 的 `this variant`、E1 的 `the syndrome` 是同一现象：先链到最近的具名变体/病，禁止链到检索焦点。
- **语义角色（SRL）。** BIOSMILE / SENNA 式 ARG0–ARG1 决定「谁是病、谁是征」（E13）。草莓龈是 ARG1（sign of），GPA 是 ARG0 方向上的疾病；当前抽取把 ARG1 写成了 subject。
- **组合事实性。** Kilicoglu et al.（BioNLP 2015；PLOS One 2017）把情态、否定、hedge 组合到 SemRep 谓词上，而不是让 LLM 从五档 modality 里猜。2026 LREC 的联合关系+认识承诺分类指出：词表 distractor（句中有 might 但辖域不在目标关系上）是 LLM 事实性错误的主因——与 E3 把句内某个 may 抬成 obligatory 同构。规则组合器比再写提示稳。

**F. 闭模式 IE 模型替代「自由 JSON」。**

GoLLIE（Sainz et al., ICLR 2024）在标注指南（Python dataclass + docstring）上微调，零样本跟未见 schema。本任务的 `required_for` 定义已经写在提示里，但通用聊天模型不跟指南；GoLLIE 的设定就是「跟人类标注员看的那份 guideline」。GLiNER / GLiNER2（EMNLP 2025 demo）在编码器上做 schema 驱动抽取，输出是原文 span，不能发明 440 ms。ReLiK（Orlando et al., ACL Findings 2024）retriever–reader：先从关系/实体词表检索候选，reader 把候选对齐到 span，单向前传。闭集关系正好是本 schema 的 11 个 LEGAL_RELATIONS。这些模型**不会**写 `associated_with`，也难以写出引语里没有的数字。它们需要少量本 schema 的标注；14.3.6 / 14.4 的人工核验已经是种子。

**G. 换表示：计算机可解释指南 / 决策树，而不是加法三元组。**

若目标是可执行规则，扁平 `required_for` 本身就是错的表示。GLIF / PROforma / Asbru / GEM 以及 LERM（Medlock et al., 2011）把推荐写成带 AND/OR 的逻辑元件。近年自动编码：Text2MDT、MedDM（从流程图建 LLM 可执行临床指导树，arXiv:2312.02441）、CPGPrompt（arXiv:2601.03475，子树合并）、Guideline2Graph（arXiv:2604.02477）。E9 在树/图里是一阶公民；326 的 and/or 不会变成两张否决票。O1 的逆命题更接近「在机制边上写一条反向转移」，不是再抽一个名词短语。这条路修的是 14.5 的 L，不单是抽取噪声；代价是要标注或校对树，十一例可先手工做金标树当评测，不要一上来全语料自动成树。

### 15.2 缺陷类到方法的对照

| 类 | 提示已经说过 | 提示以外、证据更硬的修法 | 预期够不够改 74/326 排名 |
|---|---|---|---|
| E1 主语错置 | 主语用段落里的病名 | D 先 NER；E 共指；A subject∈quote | 475 Adams→AIN：能拦 |
| E2 极性/条件 | polarity 规则 | NegBio/ConText 辖域；NLI | 腕骨骨折 OK 征：NLI 能拦 ability←inability |
| E3 模态抬高 | 无（只写了 obligatory 档） | A 情态词门；Kilicoglu 组合事实性 | 326 usually must：能拦层一 |
| E4 关系错填 | required 仅当 necessary | A 关键词门；GoLLIE 指南微调；闭集 RE | 金标准 MRI→pathognomonic：关键词门能拦 |
| E5 辖域折叠 | 无 | 共指 this variant；禁止未消解指示词当父类 | 475 MRI 变体：共指+A |
| E6 语境剥离 | differential 填 context | D 按句内疾病跨绑定；SOFT_CONTEXTS 扩到 definition 仍是应用层 | 对照句：绑定到段内主语即可 |
| E7 空规则 | 无 | A 谓语词表；锚里必须有内容词 | high index：词表黑名单 |
| E8 误诊句 | 无 | quote 含 mimic/misidentified → 禁止 excludes/feature_of 正向 | 475 韧带伤：规则门 |
| E9 组逻辑 | 提示反而把具名四征收成 all | Text2MDT 分组；A 的 or/some-or-all 门 | 326 误杀、257 some or all：能拦 |
| E10 治疗当诊断 | context=treatment | A：treatment 不得进层一 | 能从硬约束拿掉 |
| E11 忠实离题 | 提示要求也抽点名的病 | **检索/焦点**问题：段级 on-topic 门（已有 cpg gate 可搬）；不是抽取器读反 | 不改 74/326 卡点 |
| E12 循环定义 | pathognomonic 仅当 hallmark | A 关键词；NLI extrapolatory；禁止 subject 词面⊆predicate 且 quote 无新判据 | **74 层二：这是对症** |
| E13 论元对调 | 无 | SRL ARG0/ARG1；UMLS 语义型 | 56 离题句；非排名主因 |
| E14 阈值幻觉 | 不要编造数字 | A 数字∈quote；GLiNER span；程序从 quote 用 regex 抽数，LLM 不准填 threshold | **74 的 440 ms：程序层即可** |
| O1 缺逆命题 | F5b 加过提示 | 符号层：机制模板 rewrite（若 A because B 则 ¬B→¬A）；不是再抽一次 | 773 仍是 L：有逆命题加法也会给 Eisenmenger 加分 |

### 15.3 建议在本管线里的落地顺序

1. **先做 A（程序门闸）**，只作用于层一/层二用的关系。实现量小，且 74、326 的失败模式已经被写成可判定的正则。现有 F5a 夹 relation 枚举，应扩成「quote/情态/析取/阈值」同一层，而不是再调一次 LLM。
2. **高权槽加 C（NLI）** 做 A 的语义补丁：关键词门有假阴性（hallmark 的同义说法），蕴含模型补漏。不要对全部 `feature_of` 跑。
3. **抽取改流水线 D+E**：指示词共指 → 疾病跨 → 断言状态 → 闭集关系。焦点假设仍用于检索，**不再作为默认 subject**。这是 E1/E5/E11 的结构解，不是提示解。
4. **threshold 字段改为从 quote 解析**（regex / 数量 NER），LLM 只许标 operator 是否存在。E14 从生成问题变成检测问题。
5. **若要跟标注指南走**，用 14.3.6/14.4 的正反例做 GoLLIE 式少量微调，专门打 `required_for` vs `feature_of` vs `pathognomonic_for`。不要指望通用聊天模型记住 475 那种「relies ≠ obligatory」。
6. **E9 与 O1、领地外推不要再堆抽取。** 分组用 Text2MDT 的 `logical_rel`；逆命题用模板；475 第 2 步仍是 14.5 的 L。更好的抽取最多让 AIN 不被 MRI 误杀、LQTS 不再靠病名确诊——这正是 14.6 里「纯 T」的那两例。

### 15.4 文献

- AEVS 锚定抽取：[mdpi.com/2073-431X/15/3/178](https://www.mdpi.com/2073-431X/15/3/178)，代码 [github.com/yyz-nbt/AEVS](https://github.com/yyz-nbt/AEVS)
- 三元组 NLI 核验：Echo-LLM；AttrScore（Findings EMNLP 2023）；FActScore（EMNLP 2023）
- 财务三元组 faithfulness + regex/LLM-as-judge：arXiv:2602.11886
- Text2MDT：arXiv:2401.02034；FT-MDT：EMNLP 2025 industry；MedDM：arXiv:2312.02441；CPGPrompt：arXiv:2601.03475
- GoLLIE：ICLR 2024；ReLiK：ACL Findings 2024；GLiNER2：EMNLP 2025 demo
- NegBio（Peng et al., 2018）；临床 assertion 综合模型：arXiv:2503.17425
- SemRep 事实性 / 组合情态：Kilicoglu et al., BioNLP 2015，PLOS One 2017
- 约束解码能力边界：JSONSchemaBench，arXiv:2501.10868
- CIG 人工形式化：LERM（Int J Med Inform 2011）；GLIF / PROforma / Asbru

### 15.5 关系错置（假必要 / 真必要进错槽）在文献里怎么解

14.4 的双向错置（A–F 假 `required_for`；G1–G3 漏写/错写必要）在 15.1 的 A–G 里只被部分覆盖：A 的关键词门打的是 **无 cue 的过声称**，升不回 G2/G3；C 的 NLI 验「这句话是否支持这条断言」，不验「检查 vs 发现」「requires 的论元」。下面按**问题在文献中的名字**收解法。§15.4 已列的标「已有」；联网补到的标「新增」。都不是本管线新实验。

**文献里的对应问题，不是「LLM 抽错了一个枚举」。** 至少五条独立线索：(1) 义务逻辑 *must/should/may* 与诊断必要不是同一轴（指南推荐强度 ≠ 缺了就不能诊）；(2) 试验入排把 required / allowed / excluded 分成三值，禁止把 *may have received* 写成必须；(3) UMLS 把 Diagnostic Procedure 与 Finding / Sign or Symptom 分成不同类型，合法谓词不同；(4) 生成式 RE **系统过预测**无关实体对上的关系；(5) *overclaim* = 局部有支持、辖域被放大（条件性检查写成普遍必要）。

#### 已有路线对错置覆盖了什么

| 15.1 路线 | 假必要 A–F | 反方向 G1–G3 | 缺口 |
|---|---|---|---|
| A 程序门闸（已落地 F7） | 无 *necessary/must* 的清单可降；*typically/advised* 降 obligatory | **不升** `feature_of`/`excludes`；G1 无 patho cue 的 tautology 可降 | *essential to identify at-risk* 会留下；*can only be made after* 无白名单词会被误降 |
| C NLI（F8，本机未跑通） | 口头化「F 对 D 诊断必要」对 *advised / typically includes* 应不蕴含 | 「prolonged QT is pathognomonic」对病名 tautology → extrapolatory | 比较句、*diagnosis is based on Holter* 仍可能判蕴含（句子确实在谈诊断+Holter） |
| D 流水线 / assertion | E2/E3 本职 | 不选 relation | 不区分 procedure vs finding |
| F GoLLIE / GLiNER | 用**标注指南**而不是 label 名；span 不能发明 440 | 可把 `required_for` 写成带正反例的 dataclass | 需要本 schema 种子；通用聊天模型不跟指南（GoLLIE 论文的核心实证） |
| G 成树（Text2MDT / CPGPrompt / Guideline2Graph） | 流程句进「评估节点」而不是扁平必要 | 合取是一阶公民（G3） | 评测多在转诊/路径，不在「QTc>440 是否必要」这种七元组槽 |

Guideline2Graph（arXiv:2604.02477，已有）：分解优先 + 接口约束 + 可溯源聚合，边/三元组精度从 19.6% 提到 69.0%（单一前列腺癌指南）。打的是跨页控制流，不是 relation 过声称。CPGPrompt（arXiv:2601.03475，已有）把叙事切成子树再合并；简单特征检查节点接近层一，多类路径 F1 仍明显低于二分类转诊——和「扁平加法吃不到顺序排除」同构。

#### 新增：义务逻辑与「建议 ≠ 必要」

指南作者自己也知道 *must/should/may* 被读者解释得不一致。Lomotan 等（Qual Saf Health Care 2010，PMC2982946）调查卫生服务界：*must* 义务最高，*may / may consider* 最低，*should* 居中；并建议把义务用语绑到推荐强度等级，而不是让模型自由映射。G-DEE（Georg 等）用有限状态自动机标出义务算子及其前后辖域，再与 RST 核/卫星对齐——直接针对「*requires* 的宾语是 approach 还是每个检查」。2026 年多病共患指南冲突消解（arXiv:2604.17340）把动作类型做成有序集合：ALLOW / RECOMMEND / REQUIRE / CONSIDER / AVOID / CONTRAINDICATE。A/B/F 类假必要在这套符号里应是 RECOMMEND/CONSIDER 或评估步骤，不是 REQUIRE。

**对本管线：** 在 F7 的 `REQUIRED_CUE` 之前加一层义务算子+辖域（G-DEE 式），*Diagnosis requires a multidisciplinary approach. This includes Holter…* 的 REQUIRE 停在 approach，includes 列表不得继承 obligatory。这是关键词门做不到的论元结构。

#### 新增：试验入排把 required / allowed 拆开（假必要的最近邻任务）

入排句式与指南评估段同构（*may have received chemotherapy, though this is not required*）。

- **AutoCriteria**（JAMIA 2024, ocad218）：LLM 抽入排时**单独一列 value ∈ {yes, allowed, no}**，prompt 用一句话定义 allowed = 特定条件下许可、非必须。正是 A/B 类要的槽，本 schema 没有。
- **EliIE**（JAMIA 2017）、**Chia**（Sci Data 2020）、**EliXR**（JAMIA 2011）：实体域是 observation / condition / procedure / measurement 分开的；Chia 的边是可执行布尔（AND/OR），不是两条独立 `required_for`。EliXR 写明 UMLS 没有 Finding—Diagnostic Procedure 的直接边，要经 *laboratory or test result* **result of** *diagnostic procedure* 才合法——Holter 作为检查手段不能和「Holter 上的双向 VT」共用一个 predicate 槽。

**对本管线：** (1) 高权断言加 `strength: required | allowed | not_applicable`，*advised/may/should* 默认 allowed，层一只吃 required；(2) predicate 先 UMLS 语义型：Diagnostic Procedure / Laboratory Procedure 禁止单独作为 `required_for` 的发现，除非另有 *result of* 的异常值（切点、形态）。(2) 同时挡 A 类假必要和「漏写双向 VT」：手段进评估，结果才能进必要。

#### 新增：生成式 RE 过预测是定量事实，不是本例特例

- **DiMB-RE**（Hong 等，JAMIA 2025 / arXiv:2409.19581）：金实体上 GPT-4o 仍对**无关实体对过预测关系**（约 10% 测试对）；监督 BiomedBERT 的关系+事实性 F1 高于零样本 GPT。与「清单里每个检查都挂 `required_for`」同构：实体都在，关系不该有。
- **ClinIQLink / BioNLP 2026**：把 *overclaim* 定义成「局部有支持，然后放大辖域」——把有条件的直肠出血检查写成普遍唯一器械。A 类 *typically includes ECG* → 心肌病 obligatory `required_for` 是同一跳跃。
- **Do LLMs Adhere to Label Definitions?**（arXiv:2509.02452）：外部定义对 GPT-4 可能微降、对较小模型可大降；质量差的定义比没有更糟。解释了为何本管线「only when necessary」挡不住 typically：聊天模型**不跟标注指南**（GoLLIE 已证），再写长定义不是充分解；GoLLIE 式微调或**正反例**（AutoCriteria 那种 allowed 句）比再加一句英文禁则硬。
- BioRelFact（LREC 2026，15.1 E 已点名）：定义式 few-shot 多数模型最优；主要混淆是词表 distractor、对比否定——与 *essential* 出现但论元是 at-risk 同构。

#### 新增：类型约束选合法谓词（检查 vs 发现、充分 vs 必要）

SemRep（Kilicoglu 等，BMC Bioinformatics 2020）用 UMLS 语义网**过滤**主谓宾：Finding 与 Diagnostic Procedure 之间优先 MEASURES / DIAGNOSES 的方向，不允许任意谓词。本 schema 的 11 个 relation 没有这层类型门，所以 Holter 和双向 VT 竞争同一个 `required_for`。Kilicoglu 2017（PLOS One，已有）把事实性标在谓词上而不是让 LLM 猜五档 modality——E3 的本职。

G1（必要写成 pathognomonic）：闭集 RE + **互斥**（同一 quote 禁止同时 `required_for` 与 `pathognomonic_for`）在 GoLLIE/ReLiK 里比聊天 JSON 自然，因为 reader 对每个实体对只选一个关系。Prompt 允许 *extract every assertion* 等于授权双槽。

G2（参考范围写成 `excludes`+negated）：i2b2 assertion / NegBio 把 *normal* 标成 associated-with 的 **conditional/absent**，不把它变成另一条排除关系。正确组合是：predicate=`prolonged QTc`，assertion=absent 或 threshold 失败——与 §5.0.1 层一只吃 `required_for`+切点 一致。极性规则「QTc is normal → negated」若不同时改 predicate，就会掉进 G2。

#### 对照：错型 → 文献解法 → 本管线状态

| 错型 | 文献解法 | 本管线 |
|---|---|---|
| A 检查清单当必要 | UMLS procedure≠finding；AutoCriteria allowed；G-DEE 辖域 | F7 无 cue 则降；有 *requires/includes* 的清单仍过 |
| B advised/阴性不排除 | 义务三值；NLI 不蕴含「必要」 | F7 hedge→typical；*does not exclude* 未专项 |
| C essential 论元是家系 | BioRelFact distractor；SRL ARG2=identify at-risk | F7 命中 essential 会留下 |
| D/F 治疗/ICD | context=treatment 门；deontic REQUIRE 的动作是 implant | F7 E10 改 `treated_by`（依赖 context_type 抽对） |
| G1 必要当充分 / 双槽 | 每对实体只选一个 relation；patho 定义收窄到 pathognomonic 一词 | F7 降无 cue patho；**不删**与 `required_for` 并存的那条 |
| G2 切点进 excludes+negated | assertion 状态机；threshold 只挂 prolonged 谓词 | 引擎 excludes 不读切点；抽取侧未改编码 |
| G3 合取阳性支变 feature_of | Text2MDT `logical_rel`；Chia AND 边 | groups 提示已有，模型没走；F7 不升 feature_of |
| 过预测关系本身 | 先闭集实体对、再分类（DiMB-RE 监督 RE）；NLI 拒绝对无关对 | 抽取器自由生成七元组，无「无关系」类 |

**空白（检索未见到可直接搬运的系统）：** 没有现成基准叫「指南评估句 vs 诊断必要句」；最接近的是入排 required/allowed 和 CIG 义务算子，都要把 schema 加一维。没有论文把 *diagnosis is based on test X* 自动改写成 *X-result is required_for*。Guideline2Graph / CPGPrompt 评的是图/树忠实度，不评 `required_for` 精确率。

**落地含义（接 15.3，不改已做的 F7 顺序）。** 假必要的文献解是 **类型门 + 义务辖域 + allowed 档**，不是再鼓励多写 `required_for`。反方向的文献解是 **成组/成树 + 每对单关系 + assertion≠excludes**，F7 只降不升所以覆盖不了。GoLLIE 仍是「让模型跟标注指南」的正路，但 2509.02452 表明只把定义塞进聊天提示不够，要微调或正反例。入排三值（AutoCriteria）是改 schema 成本最低、且与层一「只吃 obligatory 必要」对齐的一刀。


按 §15.3 顺序实现：**程序门闸（F7）→ 高权槽 NLI（F8）→ grounded 重抽**。不改引擎四层算法（层的定义见 **§5.0**），不修 §14.5 的 L（领地外推等）。目标是让 **74 的 E12 不再喂层二、326 的 E3+E9 不再喂层一**，并观察 119 的 cornoid pathognomonic 是否被误杀。

断言各槽的合法取值、抽取填充与引擎消费的完整表见 **§5.1**（含 F7/F5a/`--grounded` 改写）。要点：规则逻辑是多槽合取，不是单看 `relation`；F7 把无 cue 的 `pathognomonic_for` 降为 `feature_of`，不会升成 `required_for`+`obligatory`。

### 16.1 实现落点

| 组件 | 路径 | 作用 |
|---|---|---|
| F7 门闸 | `gate_assertions.py` | quote vs 七元组：阈值回填、情态降档、and/or 合并、patho/required 关键词、variant/mimic/treatment/黑名单等；§16.7 起：`required_for` 必要性改 quote-local、G1 双槽、G2 QTc 改写、G3 合取肢；标本单测覆盖 326/74/257/475/119 与 G-A/G1–G3 |
| F8 NLI | `nli_verify_assertions.py` | 仅 `required_for`/`pathognomonic_for`/`sufficient_for`/`excludes`；口头化假设 + `cross-encoder/nli-MiniLM-L6-v2`；缓存 `nli_cache.json`；**模型不可用则跳过** |
| 引擎接线 | `run_mechanical_engine.py` | `clamp_relation` 之后、`subject_match` 之前调用门闸；`--quote-gate` / `--nli`；`threshold_ok` 认 `ms`≡`msec`（不改四层公式） |
| 隔离栈 | `sweep_fixes.py` | `F7_quote_gate`、`F8_nli`；累加 `S7_+F7`、`S8_+F8` |
| 机制题 | `check_fixes.py` → `f7_mechanism_checks` | 原 326 / 74 / 119 / 475 四条，加 G-A / G1 / G2 / G3 |
| 目标迭代 | `iter_f9_goals.py` | §16.7：相对 C1 的交付核对 |
| grounded 重抽 | `run_trial_extraction.py --grounded` | `GUIDELINE_KIND=guideline_groups_grounded`；`mentioned_diseases` 闭集主语；threshold 忽略模型改走 `parse_threshold_from_quote`；vignette 正则补集（阑尾/夹、fluctuant/web space、B12、SaO2–platelet） |
| 四格隔离 | `isolate_f7_f8.py` | 产出 `f7_f8_isolation.json` |

### 16.2 F7 门闸命中（旧抽取 `k30all4clean_groups`）

对 34,353 条断言跑 **当时** F7（不进引擎；§16.7 之后的 `E4_required_scope` / `G2_qtc_recode` 不在此表，见 `f9_goal_iteration.json`）：

| 原因码 | 次数 | 对应 E 类 |
|---|---:|---|
| `E4_required_no_cue` | 589 | E4 |
| `E14_threshold_cleared` | 208 | E14 |
| `E10_treatment_required` | 157 | E10 |
| `threshold_from_quote` | 108 | E14 回填 |
| `E12_or_E4_patho_no_cue` | 97 | E12/E4 |
| `E8_mimic` | 14 | E8 |
| `E9_some_or_all` | 13 | E9 |
| `E3_modality_hedge` | 4 | E3 |
| `E9_and_or_merge` | 4 | E9（326 标本类） |
| 丢弃合计 | 33 | E7/E13 等 |

grounded 重抽后体量约半（16,828→16,812），E12/E4 patho 无 cue 降至 27，说明闭集主语减少了「焦点病名 tautology」原料。

### 16.3 四格隔离（均在 B1+S6）

配置：B1（idf + loose + groups）+ 累加栈至 `S6_+F4b`（embed0.60、marker、organism、enum、corpus LR、group_all_required）。

| 格 | 抽取 | 门闸 | top1 | top3 | MRR | 金标被淘汰 |
|---|---|---|---:|---:|---:|---:|
| C0 | 旧 | 无 | 1/11 | 6/11 | 0.385 | 2 |
| C1 | 旧 | F7 | **2/11** | **7/11** | **0.415** | **1** |
| C2 | 旧 | F7+F8 | 2/11 | 7/11 | 0.415 | 1 |
| C3 | grounded | F7+F8 | 1/11 | 4/11 | 0.323 | 1 |

**焦点例排名：**

| 例 | C0 | C1 (=C2) | C3 | 机制解读 |
|---|---|---|---|---|
| **74** | rank 2，top1=LQTS（名 tautology 层二确认） | **rank 1**，top1=CPVT | **rank 1** | F7 去掉「termed long QT」类 pathognomonic → E12 不再喂层二 |
| **326** | rank 12，金标因 serology `required_but_absent` 被淘汰 | **rank 3**，金标不再淘汰 | **rank 2** | E3 情态 + E9 and/or 合并后层一不再误杀 |
| **119** | rank 1 | **rank 1**（cornoid 仍在） | **rank 13** | F7 不误杀；**grounded 重抽丢掉了 cornoid pathognomonic**（退步） |
| **475** | rank 2 | rank 3（AIN MRI obligatory 已降档，AIN 反成 top1） | rank 5 | T 侧 MRI 误杀已解；排名仍受 L/鉴别牵制，**不宣称修好** |

### 16.4 机制检查是否闭合

旧抽取 + F7（B1+S6）：

| 检查 | 结果 |
|---|---|
| 326：金标不再因 serologic + absent 被 `required_but_absent` | **PASS** |
| 74：LQTS 层二确认不再来自「仅病名」quote | **PASS** |
| 119：cornoid lamella pathognomonic 仍在 | **PASS** |
| 475：AIN `required_for`+MRI+obligatory 被降档，不再淘汰 | **PASS** |

grounded + F7：326/74/475 PASS；**119 FAIL**（重抽未保留 cornoid pathognomonic 行）。

### 16.5 F8 与 grounded 的结论边界

- **F8**：本机无法下载 `cross-encoder/nli-MiniLM-L6-v2`（HF 镜像 401 / 无本地权重），按设计 **跳过**；C2≡C1。NLI 只是关键词门的语义补丁，不是 74/326 的必要路径。
- **F7 单独即可打掉 74/326 的抽取卡点**（与 §15.3 第 1 步预期一致）。74 的排名翻转靠的是 E12 pathognomonic→`feature_of`（层二不再确认 LQTS），不是把检查清单 `required_for` 升成诊断必要，也不是补上 QTc>440 的层一柱。
- **F7 与 `required_for` 错型不同构处**见 §14.4。§16.5 当时的结论是：无 cue 的 A/B 可降；带 `essential`/`require` 的 C 类会留下；G2/G3 **只降不升**。§16.7 在同一 `--quote-gate` 里对**已经抽出的**错槽做定向改写（仍不从原文发明新断言），并修正 C 类假必要。
- **grounded 重抽**解决的是「焦点默认主语」结构问题，并补上 49/257/179 的 vignette 发现；但当前一版在 119 上 **过度过滤**，整体 MRR 低于旧抽取+F7。后续应把 cornoid /「will be diagnostic」类句纳入 grounded 回归，而不是用 C3 替换 C1。
- **不宣称** L/D 例（含 475 领地、773 逆命题等）被本轮修好。

### 16.5.1 F7 与检索粘接窗口对齐

本试验检索（`TrialRetriever.passage(window=1)`）把命中 chunk 与同文档邻块粘成 passage，原因与远端 guideline-KG 的 claim-window 重组相同：中位 chunk 只有几十到一百多 token，判据常跨边界。抽取器看到的是这段粘接文本（中位约 1320 字），但 schema 要求 `quote` ≤200 字。

F7 原先只在 quote 里核数/核 cue，会把邻块里真实存在的切点判成 E14。74 号例实测：同一粘接 passage（gids 509556–558，1085 字）里 `congenital long QT syndrome` 与 `440 ms` 相距 463 字——在粘接窗口内、在 200 字 quote 外。

适配规则（§16.7 后）：

- **正向授权（数字、pathognomonic cue、主语）**：仍在 quote 于 passage 中的 ±1200 字邻域核。
- **`required_for` 必要性**：改为 **quote-local**。邻句 *Diagnosis requires a multidisciplinary approach* 不得再给拆开的 Holter/ECG 行发执照（G-A 的根因）。
- **负向降档**（may/usually、mimic）：仍只看 quote。
- **空 threshold 回填**：仍只从 quote 解析。

E12 降档不变：该粘接段没有 pathognomonic cue，`pathognomonic_for` 仍降为 `feature_of`；440 在窗口内则保留。

### 16.6 产物文件

| 文件 | 内容 |
|---|---|
| `trial_extraction_k30clean_groups_grounded.json` | grounded 重抽 11 例 |
| `f7_f8_isolation.json` | 四格隔离 + 门闸命中计数 |
| `nli_cache.json` | F8 缓存（本次为空：模型未加载） |
| `negated_l1_census.json` | §5.0.1.1：拿掉 `asserted` 闸后的层一开火清单 |
| `case74_highstakes_unique.json` | §14.4：74 号例高权槽 unique 七元组（225 条） |
| `case74_relation_error_census.json` | §14.4：74 号例 relation 对错比例、A–F 假必要、G1–G3 真必要进错槽 |
| `f9_goal_iteration.json` | §16.7：G-A/G1/G2/G3 机制题与相对 C1 的 11 例排名 |
| `case74_inverse_required_after_f9.json` | §16.7.1：真必要 KEEP / G1–G3 漏槽收回对照 |
| `gate_generality_census.json` | §16.7.2：各门闸码的跨病例开火数与逐例 `required_for` 存活清单 |

### 16.7 借鉴 §15.5 的定向改写：假必要与 G1–G3

§16.5 停在「F7 只降不升」。§15.5 的文献解是义务辖域 + 手段/发现分型 + 每对单关系 + assertion≠excludes。本轮在 **不改四层引擎**、不重抽的前提下，把这些解收进同一 `--quote-gate`，对每个交付目标：第一方案不够就查根因再改，直到机制题闭合或证明该路径做不到排名级收益。

对照基线是 C1（旧抽取 + F7，B1+S6）：top1 **2/11**，MRR **0.415**，金标淘汰 1；74 rank 1 / 326 rank 3 / 119 rank 1 / 475 rank 3。回归要求不低于此，且 326/119/475 原机制题仍 PASS。

#### 交付目标

| 目标 | 第一方案（§15.5） | 成功标准 |
|---|---|---|
| **G-A** 假必要 | 义务辖域 quote-local；检查名短 quote / includes / at-risk 降档；*essential to identify at-risk* 不得因 essential 留下 | 74 假 `required_for` 清掉；Type I *necessary*、结构正常心脏、takotsubo angio、ARVC ≥1 criterion **仍保留** |
| **G2** | `excludes`+negated+normal QTc+&lt;440/460 → `required_for` prolonged QTc + `>` + asserted + obligatory | 层一对 QTc 380 开火 `threshold_violated`（`ms`≡`msec`） |
| **G1** | 同一 (subject, quote[:80]) 禁止双槽：有 necessary 则留 `required_for`、降 patho | Type I 不再 patho+required 并存 |
| **G3** | 「diagnosed in the presence of」窗口里的双向 VT 升 `required_for`；**不升 obligatory**（vignette 是 VF，宽松接合会假满足） | 共识肢不再全是 `feature_of`；Holter 清单不误升 |
| **回归** | — | 326/119/475/74 原题 PASS；11 例 top1/MRR 不差于 C1 |

#### 第 0 轮：当时 F7 为什么不够

74 unique `required_for` 57 条，F7 后仍 14 条（obligatory 12）。留下的假必要：

- Channelopathy 的 *resting ECG / exercise testing / 24 h Holter / pharmacological stress / genetic analysis*：quote 是裸检查名，**±1200 窗口**里有意大利 COCIS「Diagnosis **requires** a multidisciplinary approach」，`REQUIRED_CUE` 误授权。
- ARVC「Genetic testing is **essential to identify at-risk**」：F7 的 `REQUIRED_CUE` 含 essential，C 类假必要留下。
- 真必要被误降：*in the presence of a structurally normal heart*、*normal ECG*（quote 里没有 necessary/must）；*can only be made after coronary angiography* 能留下是因为当时走的是窗口 cue，quote-local 之后必须单开 KEEP。

G2：四条 `excludes`+negated「A normal QTc in men is less than 440ms」层一不读切点；正向句「QTc is prolonged (>440 **msec** …)」在 `feature_of`，进不了层一，且 `msec`≠`ms` 会挡住 `threshold_ok`。

G1：同一 quote「type I pattern necessary for the diagnosis」双槽。

G3：共识句被拆成短语，双向 VT 全是 `feature_of`；粘接窗口里仍有 *diagnosed in the presence of*。

#### 第 1 轮

1. **`required_for` 必要性改 quote-local**，KEEP 只认诊断发现义务（*necessary for the diagnosis*、*can only be made*、*must be fulfilled*、*in the presence of*、*diagnosis … must*）。`SCOPE_REJECT`：at-risk / to identify / multidisciplinary approach / this includes / advised / aviator。短 quote 且谓词是 Holter/ECG/运动试验等 → 降 `feature_of`。
2. **G2**：`excludes`+negated+normal QTc+less than 440/460 → `required_for` prolonged QTc、asserted、obligatory、`>`、单位规范成 `ms`。另把「QTc is prolonged (>440 msec…」从 `feature_of` 升 obligatory（E4 之后做，避免刚改完又被降）。`threshold_ok` 认 `ms`≡`msec`。
3. **G1**：门闸后同一 (subject, quote[:80]) 若已有 `required_for`，patho 降 `feature_of`。
4. **G3**：主语 CPVT 且窗口含 *diagnosed in the presence of* 且谓词是双向/多态 VT → `required_for` **typical**（不 obligatory）。

**结果。** 假必要清零；四条真必要保留；Type I 双槽消失；LQTS（绑定到 `Long QT Syndrome` 的那条）层一 `threshold_violated`：`380.0ms > 440.0ms`；共识双向 VT 4 条升 typical，Holter 未误升。326/119/475/E12 原题仍 PASS。11 例 **top1 2/11、top3 7/11、MRR 0.415，逐例排名与 C1 逐字相同**。

**第 1 轮未完成处（根因）。**

- *normal ECG* quote 只有两词，KEEP 的 *in the presence of* 不在 quote 里，E4 仍降档——G3 第一方案只升了 VT 肢。
- 普查 ok 例「type I in ≥2 of V1–V3」quote 是 *present in at least 2 of the three precordial leads*，无 necessary，被降。
- 诊断打印曾把候选表里的 `Long QT syndrome`（score 0、无断言绑定）当成「LQTS 未淘汰」。真正有分的 `Long QT Syndrome`（score 20.171）已被层一淘汰。根因是 `run_case` **只把断言绑到第一个匹配候选**，两条大小写不同的 LQTS 标签各吃一半；不改绑定算法（属引擎侧、超出四层公式也不在本轮范围）。score 0 的重复标签不进入竞争。

#### 第 2 轮（补 G-A / G3 残留）

- KEEP 增加 *present in at least N* / *at least N of the three precordial*。
- G3 背景肢：窗口已有 *diagnosed in the presence of* 时，把被 E4 降掉的 `normal ECG` / 结构正常心脏从 `feature_of` 收回 `required_for`。

**结果。** 74 unique `required_for` 现 **14 条**（obligatory 11）：Type I、≥2 胸导、结构正常心脏、normal ECG（`E4_required_no_cue+G3_presence_conjunction`）、takotsubo angio、ARVC ≥1 criterion、G2 切点、G3 双向 VT。工作清单 / at-risk / 裸 Holter **0 条**。机制题 9/9 PASS。排名仍与 C1 相同。

G3 **不**把双向 VT 升 obligatory：病例发现是心室颤动，没有双向 VT；宽松接合 `bidirectional ventricular tachycardia` ↔ `ventricular fibrillation`（Jaccard 0.25）会把「必要已满足」写错。这条路径在当前发现集上 **做不到正确的层一约束**，到此停。

#### 相对 C1 改了什么、没改什么

| | C1（§16.3） | 本轮 |
|---|---|---|
| 74 金标排名 | 1（E12 不再喂层二） | 仍 1；**新增**对有分 LQTS 的层一 `threshold_violated`（380 ms ≯ 440 ms） |
| 74 假必要 obligatory | Holter/ECG/at-risk 仍在 | 清掉 |
| 11 例 top1 / MRR | 2/11，0.415 | **相同**（逐例排名不变） |
| 326 / 119 cornoid / 475 MRI | PASS | PASS |

**显著改善在机制层，不在 11 例加法排名。** 74 在 C1 已经是 rank 1，层一把竞争者 LQTS 杀掉不会再改变 top1 计数；其余 10 例的主导残留仍是 L/D/发现漏抽（§13.2、§14.6），本路径不修。继续改门闸不能提高 2/11，除非改四层公式或重抽发现——那是另一条路径。

标本单测新增：裸 Holter+邻句 requires 必降、at-risk essential 必降、Type I / takotsubo / 结构正常心脏 / 胸导必留、G1 双槽、G2 改写与 msec→ms、G3 VT 升 typical 且不升 Holter、normal ECG 从窗口收回。

#### 本轮明确不做

不改层一–四公式；不把「An ECG is required」升成诊断必要；不把 G3 升 obligatory；不改主语「第一匹配即绑定」（重复 LQTS 标签）；不宣称 11 例 top1 超过 C1。

#### 16.7.1 反方向核验：真必要是否仍在别的槽里

假 `required_for` 清零只覆盖 A–F。§14.4 的反方向是「原文语义是诊断必要，却写成了 `pathognomonic_for` / `excludes` / `feature_of`」。对象仍是 74 号例 unique 七元组；*An ECG is required* 写成 `feature_of` **不算**漏槽。产物：`case74_inverse_required_after_f9.json`。

**先看本已在 `required_for` 的真必要有没有被本轮误降。** 普查 15 条 ok 例（unique 上是 Type I / 胸导 / CPVT 两肢 / ARVC 标准 / 癫痫定义 / 代谢综合征 ≥3 / takotsubo 造影 / 肌强直组合）加上酒精性心肌病「慢性大量饮酒史」（G2 案例前半，槽本就对）。第 1–2 轮 quote-local E4 把其中 **癫痫 / 代谢综合征 / 肌强直 / 饮酒史** 降成 `feature_of`（quote 里没有 necessary/must）。这是假必要清零的附带误伤，不是改善。第 3 轮 KEEP 补上 *definition of … as*、*two or more unprovoked*、*N or more metabolic*、*diagnosis is made with a combination*；饮酒史靠窗口 *key to diagnosis* 收回（谓词不是检查名，Holter 仍降）。之后 **12/12 条 KEEP**。假必要启发式仍 0。机制题 9/9 仍 PASS。（本小节的数字是泛化改造**之前**的状态；§16.7.2 用构式级规则替换这些特例后为 11/12，差的一条是肌强直检查组合，见该节记账。）

**再看 G1–G3 漏写/错写入槽，门闸后落到哪。** 硬计数：raw `required_for` 含 440/460 的条数 **0**；门闸后 **4**（G2 改写的男/女切点 unique）。正向句 *QTc is prolonged (>440 msec…)* 另 1 条由 G3/G2 升档，计入剩余 18 条 unique `required_for`。

| 簇 | raw 槽 | unique | 收回 `required_for` | 仍在别的槽 | 判定 |
|---|---|---:|---:|---:|---|
| G1 Type I 双槽 patho | `pathognomonic_for`（同 quote 已有 `required_for`） | 1 | 1（双槽解除，必要槽本已在） | 0 | **改善**（不再喂层二） |
| G1 LQTS 病名 tautology | `pathognomonic_for` | 7 | 0 | 7 → `feature_of`（E12） | **半改善**：层二危害去掉；不是发现级必要，升不回 `required_for`（切点已由 G2 承担） |
| G1 ARVC 脂肪纤维定义 | `pathognomonic_for` | 2 | 0 | 2 → `feature_of` | 同上：无 hallmark cue，降档正确；组织学「缺了不叫 ARVC」本管线没有独立发现可接合 |
| G1 SE >5 min 操作定义 | `pathognomonic_for` | 1 | 0 | 1 → `feature_of` | 未收回。操作定义是必要∧充分；升 `required_for` 不会改变 74 的发现集（无发作时长） |
| **G2 LQTS 正常 QTc 切点** | `excludes`+negated | 4 | **4** | 0 | **改善**（层一柱） |
| G2 酒精性心肌病 *absence of other etiologies* | `excludes`+negated | 1 | 0 | 1 仍 `excludes` | **未改善**。前半饮酒史已 KEEP；后半改写成「无其他病因」必要，病例没有对应发现，层一仍空 |
| G2 HCM *in the absence of* HTN/瓣膜/储存病 | `excludes`+negated | 7 | 0 | 7 仍 `excludes` | **未改善**。定义性排除病因，不是 74 的鉴别承重柱；乱升会在别例误杀 |
| **G3 CPVT 共识双向 VT** | `feature_of` | 11 | **2** | 9 | **部分改善**：有 *diagnosed in the presence of* 窗口的 2 条升 typical；其余 quote 是电生理诱导 VT/短标签，粘接段对不上共识句，升会把 Holter 同类短句一并带上 |
| **G3 QTc is prolonged (>440 msec…)** | `feature_of`/typical | 1 | **1** obligatory | 0 | **改善** |
| G3 HCM *defined as LVH* | `defined_as` | 1 | 0 | 1 | **未改善**。F5a 夹逼也只到 `feature_of`；LVH 对 74 不是接合对象 |

**合计。** 排名相关的反方向（G2 440 ms 柱、G3 正向切点、G1 Type I 双槽、G3 共识阳性肢在窗口内的那 2 条）**已改善**。仍留在别的槽里的，一类是 E12 降档后的定义句（本就不该当 hallmark，也不该当可接合的发现必要），一类是 *absence of / defined as* 的缺席必要，一类是短 quote 对不上共识窗口的双向 VT。后两类在当前发现集上 **升槽没有层一对象**，继续改门闸不会改变 74 的排名；要修只能重抽成带「无 X / LVH」的发现，或改层一只读 `excludes`+negated 的切点——都超出「不改四层公式、不发明断言」的本路径。

门闸后 74 unique `required_for` **18 条**（假必要 0）：普查真必要 12 + G2 切点 + G3 双向 VT 2 条。残余 pathognomonic 4 条均为普查 ok（epsilon、Type 1 Brugada *is pathognomonic*、地高辛双向 VT）。

#### 16.7.2 泛化改造：把 74 号例的字面量换成语言学模式

§16.7 第 1–3 轮的规则里混进了大量 74 号例专名。这类规则命中的是**这一份语料的这一句话**，换一个科室就是死代码，机制题全绿只说明它记住了标本。本节把它们逐条改成构式级规则或废弃，并给出可证伪的泛化判据。产物：`gate_generality_census.json`。

**先点名。** 改造前 `gate_assertions.py` 里的病例特异字面量：

| 位置 | 硬编码 | 只能命中 |
|---|---|---|
| `QTC_NORMAL_CUT` | `less than (440\|460)` | LQTS 男/女切点 |
| `QTC_PROLONGED_CUT` | `QTc is prolonged \(>(440\|460)` | 74 的一句正向定义 |
| `G3_SUBJ` / `G3_VT` / `G3_BACKGROUND` | `CPVT\|catecholaminergic`、`bidirectional\|polymorphic VT`、`structurally normal heart\|^normal ECG$` | CPVT 共识句的四个肢 |
| `KEEP_REQUIRED` 尾部 | `at least N of the three precordial`、`two or more unprovoked`、`N or more metabolic`、`diagnosis is made with a combination` | Brugada / 癫痫 / 代谢综合征 / 肌强直各一句 |
| `SCOPE_REJECT` 尾部 | `aviator`、`required to be grounded`、`based on .{0,40}(holter\|ilr\|ecg\|echo)` | 74 的航空医学句与两句心内科句 |
| `PROCEDURE_NAME` | Holter / ILR / 运动试验 / 心脏 MRI / 胸片…… | 心内科检查清单 |
| `parse_threshold_from_quote` 头部提示 | `QTc\|QT\|PAP\|WBC\|CSA` | 本 11 例出现过的测量名（且该组可选，实际惰性） |

**判据。** 一条门闸算可扩展，要同时满足：(a) 正则里不出现疾病名、器官名、测量名、检查名——只出现指南英语的构式；(b) 在 11 例上跨病例开火，单例开火的要能说明是语料覆盖问题而非规则形状问题。(b) 由 `audit_generality.py` 按 `_gate` 码统计。

**改造后的规则。** 七条硬编码折叠成五条构式 + 一条类型闸：

| 规则 | 形状（无专名） | 取代 |
|---|---|---|
| `NECESSITY_CUE` + **同句辖域** | 必要性必须与**该谓词出现在同一句**：句子切分后要求 cue 句覆盖谓词内容词 ≥50% | quote-local + `KEEP_REQUIRED` 尾部特例；「Diagnosis requires a multidisciplinary approach」不再授权邻句的裸检查名，截断 quote（*key to diagnosis* 那句）却能凭同句收回 |
| `PROCEDURE_LIKE` + `EXCLUSIVE_NECESSITY` | 形态学判检查名（`-graphy/-gram/-scopy/-metry/-opsy` + 通用检查名词），检查只有在**排他性**表述（*can only be made*、*cannot be diagnosed without*、*required for the diagnosis*、EliXR 的 *results of*）下才能当必要 | `PROCEDURE_NAME` 心内科清单；这就是 §15.5 的 SemRep 类型闸（Diagnostic Procedure ≠ Finding） |
| `COUNT_CRITERION` + `DEFINITIONAL_CUE` | *at least N* / *N or more* / *≥N* / *defined as*，且 `context_type ∈ {criteria, definition}` | `precordial` / `unprovoked` / `metabolic` 三条特例 |
| `SCOPE_REJECT` | 筛查辖域（at-risk / family members / cascade screening / to identify）、清单动词（*X includes*）、建议（*is advised / recommended*）、行政动作（`require[sd]? to be \w+ed`） | `aviator` / `grounded` / `based on Holter` |
| `NORMAL_RANGE`（G2） | 「normal … *less than/greater than* N unit」，**由比较词决定哪一侧异常**，谓词改写成 `abnormal <measure>` | `QTC_NORMAL_CUT` 的 440/460 |
| `PRESENCE_CLAUSE`（G3） | 抓「X **is diagnosed in the presence of** A, B and C」子句；肢的成员资格由**谓词内容词落在子句里**（覆盖 ≥75%）判定，主语由子句前缀判定；**只改 relation 不改情态** | `G3_SUBJ/G3_VT/G3_BACKGROUND` 三条清单；也顺带取消了「VT 特判为 typical」——强度沿用抽取结果，规则本身就无法凭空造出 obligatory 的层一约束 |

**弃用两条。** ① `QTC_PROLONGED_CUT` 正向提升整条删除：删掉后 LQTS 的层一 `threshold_violated`（`380.0ms > 440.0ms`）仍然开火，只是改由通用参考区间改写产生（谓词 `abnormal QTc`）——说明这条特例本来就是冗余的第二条路径。② `parse_threshold_from_quote` 的测量名提示组是可选分组，删除不改变任何匹配。

**证据一：跨病例开火。** 11 例、`_gate` 码级：

| 码 | 开火病例数 | 行数 |
|---|---:|---:|
| `E4_procedure_not_finding`（新类型闸） | **11/11** | 265 |
| `E16_excludes_negated`（§16.8 第 6 轮补） | **11/11** | 1213 |
| `E15_sufficiency_no_cue`（§16.8 第 5 轮补） | 10/11 | 87 |
| `E4_required_no_cue`（同句辖域后的降档） | 11/11 | 293 → 274 |
| `E4_counting_criterion` | 5 → **6** | 27 → 30 |
| `E4_necessity_from_sentence` | 4 → **7** | 13 → 21 |
| `E4_required_scope` | 3 | 18 |
| `G3_presence_conjunction` | **2**（74、522） | 17 |
| `G2_reference_range` | 1（74） | 12 |

（箭头右侧为 §16.8 第 6 轮 cue 扩展后的复测值：必要性构式补全后，`E4_necessity_from_sentence` 的覆盖从 4 例升到 7 例，计数标准从 5 例升到 6 例，相应地 `E4_required_no_cue` 的误降从 293 行减到 274 行。）

改造前 G3 只可能在 74 开火（正则里写着 CPVT）。改造后它在 522 号例（精神科）上承载了「Schizoaffective disorder ← concurrent depressive or manic episodes with active-phase schizophrenia symptoms」这类合取肢；`E4_counting_criterion` 承载了 DSM 的 N-of-M（AUD ≥2 项、紧张症 12 选 3、精神分裂症状持续 ≥6 月）；`E4_procedure_not_finding` 在 522 上放行了「definitive diagnosis can only be made by histological analysis」（排他）而降掉了普通检查清单。`G2_reference_range` 仍只在 74 开火，但正则里没有任何测量名——这是**语料覆盖**问题（只有 74 的指南写了「A normal X is less than N」这种参考区间句），不是规则形状问题，域外单测已证明它在血液科文本上同样成立。

**证据二：域外标本单测。** 每条改造后的规则都用另一科室的句子重测（`gate_assertions.py` `_self_test`，`od_*` 七条）：莱姆病 *Evaluation typically includes a Western blot* 必降；乳糜泻 *can only be made after duodenal biopsy* 必留；Lynch 综合征 *essential to identify at-risk relatives* 必降；SLE *at least 4 of the 11* 必留；中性粒细胞减少 *A normal neutrophil count is **greater than** 1500* → 必要 + 运算符反向成 `<`；脓毒症 *diagnosed in the presence of infection and organ dysfunction* 升肢，同窗口的 *blood culture* 不升。全部 PASS（含原 74/326/119/257/475 标本共 31 条；§16.8 第 5、6 轮又加了 4 条域外——幽门螺杆菌、结直肠癌、甲减、结节病——标本总数增至 **37 条**，域外 11 条）。

**证据三：不劣于且略优于 C1。** 机制题 9/9 PASS（含 326/119/475 原题与 G-A/G1/G2/G3 四题）。11 例 B1+S6：门闸开 top1 **2/11**、top3 **7/11**、MRR **0.430**、金标淘汰 1；门闸关 top1 1/11、top3 6/11、MRR 0.385、金标淘汰 2。逐例排名（门闸开→关）：326 3→12*、74 1→2 改善，475 3→2、56 6→4 变差，其余不变。相对 C1（2/11、0.415）为 **+0.015 MRR**，仍在噪声量级内，本节的收益仍应记在机制层。

**与人工普查的一处分歧（须记账）。** 肌强直「The diagnosis is made with a combination of clinical, electrophysiological, and genetic studies」在 §14.4 普查里记为 ok 例，改造后被类型闸降成 `feature_of`：谓词是三项**检查**且句中没有排他性表述，与「An ECG is required 不算必要」是同一条口径。因此 §16.7.1 的 KEEP 由 12/12 变成 **11/12**，且这一条降档是安全方向——它原本是 obligatory `required_for`，若病例没有肌电图发现，层一会误杀 Myotonia congenita。G1–G3 收回表其余各行不变，唯 `G3_qtc_prolonged_cut` 由 1/1 变 0/1（该条特例已弃用，层一柱由 G2 承担）。

**残留的不干净处。** ① CPVT 同时留下 *age < 40 years* 与 *age > 40 years* 两条 typical 必要，两条 quote 都真的落在共识子句里（共识对 <40 与 >40 各有一条判据），这是抽取把两条判据拆散后主语都绑到 CPVT，门闸无法分辨——属 §14.4 的判据组问题，不是辖域问题。② `E9_some_or_all` 仍只在 257 开火（既有，本轮未动）。③ 522 上 `E4_counting_criterion` 放行了「Vitamin B12 deficiency ← at least 1 common risk factor」这类弱判据句，`context_type=criteria` 挡不住它；这是计数构式的假阳，代价是 522 的 `required_for` 存活数从个位升到 25 条，但该例排名未变（rank 2）。

### 16.8 微调 MedCPT 当关系槽验证器：两轮迭代与它撞到的墙

§16.7 的门闸是正则。正则的上限是「写规则的人想到的构式」，所以自然要问：能不能把这件事交给一个在生物医学文本上预训练过的编码器。参照 arXiv:2409.16461（NL→一阶逻辑翻译）的做法——那篇不是关系抽取，可迁移的是它的**验证器**：用少量人工种子按错误分类学做**受控扰动**造负例，再混入模型真实犯过的错，训一个判「correct / 改正」的小模型，用它在解码时逐条校验。这里把「一条断言」换成「一个关系槽」，把 T5 换成 **MedCPT-Cross-Encoder**（PubMedBERT 底座，109.5M，成对输入天然适合验证任务）。

**任务形式。** 输入是一对 `(指南证据, 断言的自然语言化)`，输出「该关系槽是否被这段文字许可」。断言语言化按槽写成蕴含句，例如 `required_for` → *"X must be present to diagnose Y."*，`excludes` → *"The presence of X rules out Y."*。这与 F7 的行级判定（保留 / 降档）是同一个决策，因此两者可直接对拍。

**划分按病例隔离。** 测试集是 74 号例的 225 条 unique 高权槽，标签由 §14.4 的**人工普查**重链而来；训练集是其余十例，模型从未见过 74。重链结果与普查自身的计数对账：`pathognomonic_for` 9 ok / 19 wrong、`sufficient_for` 1/5、`excludes` 0/134 **完全吻合**；`required_for` 只回收到 12 条 ok（普查记 15）——普查在该槽下只列了 examples 而非全表，缺的 3 条无法从文件复原，它们对所有系统一律记作 not-licensed，因此**licensed 类的召回被系统性低估约 3 行**，这是测试集的已知噪声上限。

**必须声明的偏置：F7 基线是乐观的。** §16.7 的正则是在读过这份普查之后写的，等于见过测试标签；模型没有。所以「模型追平 F7」已经不是平局。

#### 第 0 轮：同分布近乎完美，跨病例低于随机

教师标签用 F7 的行级判定（保留=1/降档=0），加上按 §15.5 分类学做的受控扰动（把教师保留的行换一个关系槽，构造上即负例）。训练 2490 行、dev 676 行（49/119 两例）。

结果是同分布 dev macro-F1 **0.951**，74 号例上 AUC **0.259**——低于随机，且方向是反的。根因不是过拟合而是**教师的盲区**：F7 按设计不动 `excludes`，训练里 `excludes` 大多被标成「成立」，而人工普查判定 74 的 134 条 `excludes` **全错**（schema 的 `excludes` 是「该发现**出现**则排除该病」，124 条 `polarity=negated` 在定义上就放错了槽）。这一项占测试集 60%，学到的先验直接把排序倒过来。

#### 第 1 轮：补 schema 标签 + 阈值标定

改两处：`excludes`+negated 在训练集里按 **schema 定义**（不是启发式）标 0，这正是人工普查对 124/124 行用的同一条理由；决策阈值不再固定 0.5，改为在 dev 上搜。

| 系统 | 全部 225 | 诊断槽 91 | `required_for` 57 |
|---|---:|---:|---:|
| 多数类（全判 not-licensed） | 0.474 | 0.431 | 0.441 |
| F7 正则门闸（乐观偏置） | 0.335 | **0.820** | **0.887** |
| MedCPT 微调（3 种子均值） | 0.612 | 0.610 | 0.658 |

（macro-F1。F7 在「全部 225」上低，是因为那 134 条 `excludes` 它按设计放行，不是失败。）

排序质量则明显提升：AUC 从 0.259 升到 **0.866**（sd 0.005），零样本 MedCPT 是 0.708。但阈值化后的 licensed-F1 只有 **0.291，且 sd 高达 0.187**（三个种子分别 0.05/0.51/0.31）——排序迁移了，工作点没迁移。

**阈值不是瓶颈。** 用 74 的**全部 225 条人工标签**去挑最优阈值（oracle 上界），macro-F1 也只有 **0.687**，仍低于 F7 的 0.820/0.887。按标注量拆：20 条 0.617、40 条 0.640、80 条 0.665（各 200 次抽样均值），即再标 80 行也只逼近那个 0.687 的上界。所以「多标几条来标定阈值」这条路径**收益封顶**。

#### 第 2 轮：把证据粒度对齐到 F7 的同句辖域

§16.7.2 的主要收益来自「必要性必须与该谓词同句」。而模型看的是 ±900 字符窗口，里面恰好含有那句会误导的邻句（*Diagnosis requires a multidisciplinary approach*）。于是把证据换成 F7 读的同一批句子再训。

结果几乎不变：AUC 0.861（vs 0.866），诊断槽 macro-F1 0.621（vs 0.610），`required_for` AUC 反而从 0.802 降到 0.760。**证据粒度这个根因被否证**。

#### 停在哪里，为什么

两轮定向迭代之后，剩下的根因只有一个，而且不能靠改代码解决：**训练信号本身**。按 schema 重标之后，十例合起来只剩 **299 条正例**；教师是正则，学生最多只能把正则的构式推广到正则没写到的措辞上，学不到正则没有的判断依据。这与 2409.16461 的前提一致——那篇的验证器也建立在 FOLIO 的 **1k 条人工标注**种子之上，扰动只是放大种子，不能替代种子。

因此这条路径的结论是：**在没有人工标签的条件下不可行**（不是「无效」——AUC 0.866、诊断槽 0.73–0.75 说明编码器确实学到了可迁移的排序信号，只是达不到可用的工作点）。要继续，需要标注，且标注量的数量级由训练正例决定，不由阈值决定。

#### 标注方案（已备好，等确认）

`make_annotation_kit.py` 已把其余十例的**诊断槽全集 848 行**导出为 TSV：`required_for` 678、`sufficient_for` 86、`pathognomonic_for` 84；按 (病例, 关系) 分层轮转排序，因此**任取前 N 行仍是无偏子集**，可以分批标。每行给出 subject / relation / predicate / quote / 同句上下文与一个空的 `licensed` 列；**故意不显示 F7 的判定**，否则标签会被门闸暗示带跑，而独立信号正是这件事的全部意义。判定口径写在 `ANNOTATION_CODEBOOK.md` 里，沿用前几轮已固定的七条约定（工作清单不是必要、检查需排他性或结果、筛查不是索引诊断、治疗/行政阈值不是判据、计数判据是必要、病名同义反复不是 pathognomonic、按写下的槽判而不是按「本该写哪个槽」判）。quote 平均 59 字符，按每行 15–20 秒估算，全量约 3.5–4.7 小时。

#### 第 3 轮：先验收标注质量，再决定要不要用它训练

标注由一个**独立子智能体**完成，它只能读 codebook 与待标行，看不到 F7 的判定、看不到任何既有普查、也不许读仓库其他文件。它不是人类标注者，所以「这批标签能不能当训练信号」本身必须先被检验，否则就是拿一个模型的偏好去训另一个模型。

检验方式是盲测：从 74 号例诊断槽里分层抽 **60 行**（`required_for` 38 / `pathognomonic_for` 16 / `sufficient_for` 6），去掉标签发给同样的标注流程，事后与 §14.4 人工普查的答案对拍（答案存在 `batch_qc_case74_key.json`，标注时不可见）。

| 指标 | 值 |
|---|---|
| 原始一致率 | **56/60 = 0.933** |
| Cohen's κ | **0.822** |
| 普查 licensed 率 vs 标注 licensed 率 | 0.250 vs 0.250 |
| `?`（判不了） | 0 |
| 分槽正确 | `required_for` 36/38、`pathognomonic_for` 14/16、`sufficient_for` 6/6 |

两点值得记账。其一，licensed 率**逐点相同**（各 15 行），说明标注没有系统性地偏松或偏紧，这比一致率本身更重要——先验漂移正是第 1 轮里毁掉工作点的东西。其二，4 条分歧全部落在标注者**自己主动标为「难判」**的行里，即它的不确定性是校准的：

| 行 | 槽 | 普查 | 标注 | 争点 |
|---|---|---|---|---|
| ε sign *indicative of* ARVC | patho | 1 | 0 | 「提示性」是否等于单独确诊 |
| *characteristic* type 1 Brugada 且引文括号截断 | patho | 1 | 0 | 「典型」是否等于排他性确诊 |
| 药物激发试验出现诊断性 Brugada ECG 改变 | required | 0 | 1 | 要求的是检查的**结果**（公约 2 许可） |
| *Diagnosis of NPE is made from thoracic radiographs* | required | 0 | 1 | 无 *only*，但把检查陈述为诊断依据本身 |

后两条属于本节开头声明过的测试集已知缺口——普查在 `required_for` 下只列 examples，有 3 条 ok 行无法复原、一律被记作 not-licensed。药物激发那条很可能正是其中之一。**若如此，真实一致率是 58/60**，而不是 56/60。无论取哪个数，κ 都落在「基本一致」区间，因此这批标签可以进训练集；但它们在报告里始终按「子智能体标注」记账，不冒充人工标注。

#### 第 4 轮：200 条标签的学习曲线，以及它顺带暴露的门闸空洞

标注批（200 行，44 个 1 / 156 个 0，无 `?`）折进训练集，覆盖对应行的教师标签，按 k=50/100/200 取前缀（分层轮转保证任意前缀无偏），每点 3 种子。

| k（标注行数） | 全部 225 | 诊断槽 91 | `required_for` 57 | licensed-F1 | licensed-F1 的 sd | 诊断槽 AUC |
|---:|---:|---:|---:|---:|---:|---:|
| 0（纯教师） | 0.607 | 0.610 | 0.658 | 0.291 | 0.187 | 0.751 |
| 50 | 0.593 | 0.591 | 0.652 | 0.266 | 0.197 | 0.726 |
| 100 | 0.577 | 0.575 | 0.618 | 0.235 | 0.123 | 0.709 |
| **200** | **0.663** | **0.662** | **0.695** | **0.411** | **0.057** | **0.766** |

两件事同时发生。其一，**曲线非单调**：50 和 100 反而略降。原因是标注与教师只有 0.609 一致，小批量替换等于给模型灌进自相矛盾的监督——同类构式一半按门闸标、一半按标注标；要到 200 行，人工信号才自洽到能压过教师。其二，**k=200 处方差坍缩**：licensed-F1 的 sd 从 0.187 降到 0.057，AUC 的 sd 从 0.005 级别保持稳定，说明工作点终于不再靠种子运气。

但斜率的量级也要说清楚：200 条标签买到诊断槽 +0.052 macro-F1（0.610→0.662），距 F7 的 0.820 还差 0.158。按这个斜率线性外推需要再标约 600 行才可能追平，而曲线前半段是负的，外推的误差棒很大。**结论是这条路径「可行但昂贵」，不是「已经成功」。**

**真正有价值的副产品是标注对 F7 的独立审计。** 标注者对 74 号例人工普查的一致率是 0.933/κ 0.822，可视作一把还算准的尺；用它量 F7 在**其余十例**上的判定：

| 槽 | F7 与标注一致 | 说明 |
|---|---:|---|
| `required_for` | 66/81 = **0.81** | F7 治理该槽；相对 74 号例诊断槽的 0.868 只是温和下降 |
| `pathognomonic_for` | 50/64 = **0.78** | 同上 |
| `sufficient_for` | 7/57 = **0.12** | **F7 对该槽没有任何规则**，一律放行 |
| 合计 | 123/202 = 0.609 | 被 `sufficient_for` 拉低 |

这把 §16.7.2 的泛化问题回答得更准了：F7 治理的两个槽**确实迁移**（0.78–0.81），跨病例掉点有限；被拉低的整体数字来自它**从不看守的槽**。`excludes` 早已由 §14.4 记为 1.0 错误率并在本节用 schema 规则处理，而 `sufficient_for` 是同样的空洞——74 号例普查记它 5/6 错，十例标注记它 50/57 错，两处独立证据一致。混淆方向也单一：F7=1 而标注=0 有 56 例，反向只有 23 例，即门闸的问题是**过度放行**而非过度降档。

#### 第 5 轮：按审计补上 `sufficient_for` 槽（E15）

第 4 轮定位的空洞可以直接补，而且补法是构式级的，不需要神经网络。新增 `SUFFICIENCY_CUE`：*is/are diagnostic of*、*establishes/confirms the diagnosis*、*sufficient to/for*、*enough to diagnose*、*makes the diagnosis*、*diagnosed in patients who…*、*if present, the diagnosis…*。辖域规则与 E4 完全相同（cue 要么在 quote 里，要么在窗口中**同时覆盖该谓词**的那一句里），再叠加既有的 `SCOPE_REJECT`。没有充分性构式的 `sufficient_for` 一律降 `feature_of`（gate 码 `E15_sufficiency_no_cue`）。

规则是从 schema 定义与 §14.4 已记录的错误模式（治疗性充分、*consider EMB*、*may suggest evaluation*、*first-level imaging*）写出来的，写完只在标注行上量一次，不按行调参。结果：

| 槽 | E15 之前 | E15 之后 | n |
|---|---:|---:|---:|
| `pathognomonic_for` | 0.79 | 0.79 | 61 |
| `required_for` | 0.81 | 0.81 | 80 |
| **`sufficient_for`** | **0.14** | **0.86** | 56 |
| 合计 | 0.614 | **0.817** | 197 |

（本表 n=197 按五元组去重，第 4 轮表 n=202 按含 modality/polarity 的七元组去重，故 `sufficient_for` 基线在两表分别记 0.14 与 0.12；before/after 在本表内用同一脚本、同一去重口径算出，可直接相减。）

回归全部干净：机制题 **9/9 PASS**；11 例排名 top1 2/11、top3 7/11、MRR 0.430、金标淘汰 1，与 §16.7.2 逐字相同；`E15_sufficiency_no_cue` 在 **11/11 例**开火（90 行，第 6 轮的 cue 扩展许可了少数行后变为 10/11、87 行），按 §16.7.2 的判据是规则而非补丁；标本单测增至 35 条，含两条域外（幽门螺杆菌尿素呼气试验 *is diagnostic of* 必留、结直肠癌 *primary imaging modality* 必降）。

这条改进的来路值得记一笔：**它是神经实验的副产品，不是神经模型本身**。MedCPT 没有达到可用工作点，但为了评测它而做的独立标注，量出了正则门闸自己看不见的空洞——这比模型本身值钱。

#### 第 6 轮：把标注当尺子，逐簇补完受治理槽（E16 与四组构式扩展）

第 5 轮之后残余 36 条分歧，方向已经翻转：两个受治理槽里 **22/26 是过度降档**——门闸把标注者认为成立的行降掉了，正是 §16.2 提出的「真 required_for 被归入其他逻辑类」。用 `audit_slot_errors.py` 按槽与方向摊开逐条读，聚成五簇，其中四簇有构式级修法：

| 簇 | 失配原因 | 修法 |
|---|---|---|
| 计数标准漏配 | `COUNT_CRITERION` 只认 "at least N"/"N or more"，不认裸的 "five minor criteria" | 加 `NUMERAL + (形容词) + criteri(a\|on)`、`total score of N`；并让计数标准同样许可 `sufficient_for`（它本身就是判定规则） |
| 必要性构式漏配 | 只认 `for the diagnosis`，不认 `essential **in** diagnosing`、`is diagnosed based on`、`the only way to`、`criteria have been met` | 介词扩为 `for\|in\|to`，另加四条构式 |
| 诊断价值动词漏配 | `PATHO_CUE` 不认 `considered diagnostic`、`diagnostic **for**`、`diagnosis is made/confirmed/established by`（后者在段落库出现 **7 次**） | 补入 |
| **拼写变体** | 段落原文写作 *"Caseation necrosis is **pathognomic** of ITB"*，少一个 on，正则整条匹配不上 | `pathognom(?:on)?ic`；该误拼在段落库占 1/9 |
| 裸名词短语（未修） | quote 只有发现名，窗口内根本没有任何 cue 句 | 属证据窗口问题，非 cue 缺口，留作已知残余 |

明确不修三类：程序名槽（"Skin biopsy is required for definitive diagnosis"）按 §16.7.1 既定设计不得升为 `required_for`；两条 *suggests* 对冲行（E3 按设计降档，标注者在此偏宽）；标注者自陈存疑的 *sensitive enough to detect* 行。

**E16：`excludes` 槽的 schema 蕴含。** `excludes` 的语义是「该发现**存在**即排除该病」，而 `negated` 行断言的是**不存在**，槽位按定义自相矛盾。这条只靠 schema 就能判定，此前只用在训练标签上，门闸自身没应用。全语料 `excludes` 共 1373 行，其中 **negated 1226 行、11 例全有**；74 号例被普查的 134 行**全部为错**。

递归成 `required_for` 的变体**被实测否决**：它让 G-A 已清零的假必要性复活（`74_ga_false_required_cleared` FAIL），因为这些行多是 workup 散文而非成文标准。最终取降 `feature_of`，内容仍留给层三加权，不武装层一约束。

**留出集验证。** 本轮全部规则由**其余十例**induce，74 号例的人工普查完全没参与，因此它是一次真正的样本外检验：

| 行集 | 本轮前 | 本轮后 |
|---|---|---|
| `all_225` | acc 0.369 / macroF1 0.335 | **0.929 / 0.820** |
| `diagnostic_91` | acc 0.868 / macroF1 0.820 | **0.934 / 0.904** |
| `required_57` | acc 0.930 / macroF1 0.887 | **0.965 / 0.947** |

同时十例标注上的一致率 0.614 → **0.893**（`required_for` 0.81→0.91、`pathognomonic_for` 0.79→0.85、`sufficient_for` 0.14→0.91）。回归：机制题 **9/9 PASS**，标本单测 **37 条全过**（新增 4 条域外：甲减 *in the absence of secondary causes* 必降、结节病 *presence of AFB excludes* 必留、幽门螺杆菌、结直肠癌），11 例排名 top1 2/11、MRR 0.430、金标淘汰 1，与本轮前**逐字相同**。

排名不动这一点要如实说：E16 改写了 1213 行，却对排名毫无影响，说明引擎本来就没在用 negated `excludes` 做淘汰。**本轮买到的是表示正确性，不是排名。** 另外 `all_225` 从 0.335 跃到 0.820 有部分循环性——E16 的规则虽由 schema 推出、不看具体行，但「该槽整体偏错」这个事实来自 74 号例普查本身；`diagnostic_91` 与十例一致率不受此影响，是干净的样本外证据。

对照之下，MedCPT 微调在 `diagnostic_91` 上最好为 0.662，而规则现已到 0.904。**在这个任务上神经验证器已被规则明确压过，§16.8 的神经路径可以按「可行但不划算」结案。**

#### 本节明确不做

不用 F7 的判定当测试标签（那会自证）；不把 74 号例任何行放进训练；不在报告里把 F7 与模型的差距说成公平比较（F7 见过这份普查）；不因为「全部 225 行」上模型 0.612 > F7 0.335 就宣称模型更好——那个差距全部来自 F7 按设计放行的 `excludes`；不把子智能体的标注称作人工标注；不宣称 E15 的 0.86 是无偏估计——规则虽未按行调参，但它是在知道该槽整体偏错之后写的。

## 十七、替代路径：不抽七元组，只摘录自然语言规则句，改用 LLM 当执行引擎

§14.4 的普查给出的动机很直接：74 号例高权诊断槽的 relation 错误率是 **67/91 = 0.736**，`sufficient_for` 与 `excludes` 更是 1.0。如果抽取器在逻辑关系上错得这么厉害，那么强迫它填七个槽本身可能就是错的选择——不如让它**只做一件它擅长的事：把原文规则句原样抄下来**，逻辑连词留在英文里不做形式化，只由程序补一个阈值作为附注，再把推理交给 LLM。

这一节做的就是这条路径，并把它与机械引擎放在同一批 11 例、同一候选集、同一份病人证据上对拍。

### 17.1 两个阶段怎么实现

**阶段 A（`extract_nl_rules.py`）**：每个 passage 一次调用，只要求返回

```json
{"rules": [{"disease": "...", "sentence": "<逐字抄写>", "use": "diagnosis|treatment|prognosis|other"}]}
```

提示词里写死三条：整句抄、把 `and / or / unless / if / without / at least / in the absence of` 和所有数字单位一起抄进来、**不要标注这句是必要/充分/典型/排除**。没有 relation、没有 modality、没有 polarity——这正是被砍掉的东西。程序侧只做两件事：用子串核验这句确实出自本段（不是就丢），以及用 §16 的 `parse_threshold_from_quote` 从句子里解析阈值挂成附注。

载荷里不含焦点假设，所以同一 passage 被不同假设检索到时共用一个缓存条目：11 例 3842 个 passage 槽位去重后 **2683 次调用**。

**阶段 B（`run_llm_executor.py`）**：一次调用排完一个病例的全部候选。喂给它的病人证据与机械引擎完全一致（同一份 `findings`），主语绑定也复用机械引擎的 `subject_match`，所以两条路径之间**唯一变的是规则表示与推理器**。五个臂：

| 臂 | 喂给执行器的东西 |
|---|---|
| `none` | 不给任何规则——参数化知识对照组 |
| `tuple` | 七元组的槽位（relation/polarity/modality/threshold/group），不给 quote |
| `tuple_quote` | 槽位 + quote |
| `nl_quote` | 只给旧抽取的 quote，槽位全丢——用现成抽取做的廉价版本路径 |
| `nl_rule` | 阶段 A 摘录的逐字规则句 |

候选顺序按重复次序打乱，每臂跑 3 次。`none` 臂是整节的锚：**没有它，任何分数都无法归因给规则**。

### 17.2 抽取正确率：这条路径赢得干净

| 口径 | 七元组路径（74 号例） | 自然语言摘录路径 |
|---|---|---|
| 逻辑关系错标 | `required_for` 42/57、`pathognomonic_for` 19/28、`sufficient_for` 6/6、`excludes` 134/134 | **0**（不作任何逻辑断言） |
| 逐字忠实度 | quote ≤200 字，常被切成裸名词短语 | 16049 条完全逐字 + 625 条仅空白差异 = **98.7%** |
| 编造的片段 | 需要 NLI 或人工才发现 | 216 条（1.3%）被一次子串检查直接丢掉 |

差别的性质比数字更重要：**编造的摘录用一行字符串比对就能查出来，编造的 relation 不能**。这是这条路径唯一无可争议的收益。

代价在另一头。`case74_nl_rule_quality_census.json` 里对 74 号例 CPVT / LQTS / Brugada / HCM 各抽 10 条（HCM 只有 9 条唯一句）人工判读 39 条：

| 类别 | 条数 | 占比 |
|---|---|---|
| 可执行的诊断规则 | 8 | 0.205 |
| 有效但不是诊断规则（检查选择、治疗） | 8 | 0.205 |
| 在主语上但不是规则（流行病学、遗传学、告诫） | 10 | 0.256 |
| 退化的表格行 / 表单字段 | 9 | 0.231 |
| **绑到了错误的疾病** | 4 | 0.103 |
| 悬空指代（`It is also indicated in...`） | 1 | 0.026 |
| **作出虚假逻辑断言** | **0** | **0** |

所以：**五分之一是真规则，四分之三是无害的噪声，1/10 挂错了病**。挂错病这一类不是这条路径引入的——主语绑定用的是同一个 `subject_match`，两条路径共享这个缺陷。表格行退化也共享（chunk 切开表格后表头丢失）。

摘录路径确实把 §14.4 里被毁掉的判据救了回来：

- **LQTS 切点**：`A normal QTc in men is less than 440ms, and in women, it is less than 460ms.` 在七元组路径里被写成 `excludes` + `negated`（引擎无法执行，所以 QTc 380 ms 从未排除 LQTS）；摘录路径原样保留，另一条 `Long QT syndrome – QTc >0.450 sec` 还带上了程序解析的 `{">", 0.45, "sec"}`。
- **CPVT 触发条件**：七元组把它拆成裸检查名（Holter、运动试验、基因检测）标 `required_for`+`obligatory`；摘录路径把 `This cascade of events can be triggered by emotional or physical stress, exertion or bathing ...` 整句留下。

但它在**选择**上输了：CPVT 那一块按语料支持度排序的前 12 条里有 5 条是硫酸镁和 β 受体阻滞剂的治疗句，真正决定性的触发句排在第 13 位。支持度（一句话被多少个 passage 重复）不是诊断决定性的代理量。

### 17.3 执行正确率：名义上略胜，实际落在噪声里

`llm_executor_comparison.json`，全部 11 例、LLM 臂为 3 次重复的均值：

| 引擎 | 表示 | 病人证据 | top1 | top3 | MRR | 中位排名 | 淘汰金标 |
|---|---|---|---|---|---|---|---|
| 机械 | 七元组 | findings | 1/11 | 6/11 | 0.385 | 3 | 2 |
| 机械 +F7 | 七元组 | findings | 2/11 | **7/11** | 0.415 | 3 | **1** |
| LLM | **无规则（对照）** | findings | 2.33 | 4.00 | 0.360 | 5.7 | 1.67 |
| LLM | 七元组槽位 | findings | 2.00 | 4.33 | 0.361 | 4.3 | 2.67 |
| LLM | 槽位 + quote | findings | 2.67 | 4.67 | 0.403 | 5.0 | 1.33 |
| LLM | 旧 quote 当规则 | findings | 2.67 | 4.33 | 0.393 | 5.0 | 2.67 |
| LLM | **NL 规则句（cap 40）** | findings | 3.00 | 4.67 | 0.416 | 5.0 | 2.00 |
| LLM | NL 规则句（cap 100） | findings | **3.33** | 4.67 | **0.436** | 4.7 | **0.33** |
| LLM | NL 规则句（cap 12） | findings | 2.33 | 4.33 | 0.379 | 5.7 | 2.33 |
| LLM | NL 规则句 | vignette | 2.67 | 5.33 | 0.408 | 5.3 | 2.33 |
| LLM | 无规则 | vignette | 2.67 | 4.33 | 0.388 | 4.7 | 2.33 |

三件事要一起读：

1. **NL 规则 + LLM 的 MRR 与机械引擎打平**（0.416 vs 0.415），top1 从 2 涨到 3。但 rep0 的 bootstrap 区间是 [0.244, 0.673] 对 [0.264, 0.603]——11 例上这两个数不可分。
2. **不给任何规则的对照就已经拿到 2.33/11、MRR 0.360**。整套检索 + 摘录 + 执行相对于「只看病人事实凭参数化知识排」的净增益是 **+0.67 例 top1、+0.056 MRR**。规则在做事，但做得很少。
3. **机械引擎在 top3 和中位排名上明显更好**（7/11 vs 4.7/11；中位 3 vs 5）。两者的失败形状不同：机械引擎的分数对证据覆盖单调，金标掉不出中段；LLM 会自信地把金标压到很深（56 号例排到 17–19 位，326 排 9–11，179 排 11–13，机械引擎同例是 6、3、6）。

**配对检验讲得更清楚。**逐例比较金标排名（LLM 取 3 次均值）：

| 对比 | LLM 更好 | 机械更好 | 平 | 符号检验 p |
|---|---|---|---|---|
| C1+F7 vs NL 规则（打乱顺序） | 2 | 6 | 3 | 0.289 |
| C1+F7 vs NL 规则（固定顺序） | 3 | 4 | 4 | 1.000 |
| C1+F7 vs 槽位+quote | 1 | 8 | 2 | **0.039** |
| C1+F7 vs 无规则对照 | 2 | 9 | 0 | 0.065 |

臂级均值说 LLM 略优，配对说机械引擎在多数病例上把金标放得更靠前。两者不矛盾：LLM 赢在头部（把 3 例顶到第 1），输在腰部。哪个更重要取决于下游是取 top1 还是取一个短列表。

### 17.4 一个没预料到的结果：候选呈现顺序比整套规则更有影响

三次重复之间打乱候选顺序，同时另跑一组**固定顺序**的三次重复，就能把「解码噪声」和「位置敏感性」拆开（Kendall τ 只在模型自己排过的候选上算）：

| 变的是什么 | Kendall τ | top1 一致率 |
|---|---|---|
| 什么都不变，重复调用（固定顺序，`nl_rule`） | 0.832 | 0.82 |
| 什么都不变，重复调用（固定顺序，`none`） | 0.862 | 0.94 |
| 只打乱候选呈现顺序（`nl_rule`） | **0.328** | 0.42 |
| 只打乱候选呈现顺序（`none`） | **0.458** | 0.24 |
| 顺序相同，把整套规则换掉甚至删光（`nl_rule` vs `none`） | **0.613** | — |

解码噪声很小（τ≈0.85）。但**换一个候选排列对输出排序的扰动（τ≈0.33），大于把全部 332 条规则整体撤走（τ≈0.61）**。也就是说，在这个规模上「LLM 当执行引擎」不是一个稳定的引擎：它对提示词里候选出现的位置比对证据本身更敏感。机械引擎没有这个自由度——它的输出是候选顺序的函数意义上恒等的。

固定顺序那一组 `nl_rule` 拿到 top1 3.33、MRR 0.472，是全表最高，但这恰恰是同一现象的另一面：那个特定排列碰巧有利。

### 17.5 上下文预算是单调的，说明选择器还没起作用

`nl_rule` 的每候选规则条数上限从 12 → 40 → 100：top1 2.33 → 3.00 → 3.33，MRR 0.379 → 0.416 → 0.436，被淘汰的金标 2.33 → 2.00 → **0.33**。给得越多越好，一直到上下文塞不下（cap 100 时 522 号例出现一次 JSON 截断）。

两个推论：

- 现在的按支持度排序**没有把决定性规则排上来**（§17.2 的 CPVT 例子），否则前 12 条就该够用；多给只是提高了撞上正确那条的概率。
- 金标淘汰随材料增多而下降，说明 LLM 的「ruled_out」判定很大程度上是**材料不足时的猜测**，不是规则触发。这与机械引擎的层一相反：层一是材料越多越容易开火。

### 17.6 结论

问的是「这条路径的规则提取/执行正确率是否大于机械规则引擎」。分开答：

- **提取端：是，而且是数量级的差别。**逻辑关系错误率从高权诊断槽的 0.74 降到 0（因为不再作逻辑断言），逐字忠实度 98.7%，编造片段可用一次子串比对查出。但这是**把问题挪走而不是解掉**：只有 20.5% 的摘录是可执行的诊断规则，10.3% 挂错疾病，23.1% 是失去表头的表格行。七元组的错误是**恶性**的（一条假 `required_for` 会在层一直接淘汰金标），摘录的错误是**良性**的（跑题句子只消耗上下文）——这是这条路径真正的价值所在，而不是排名分数。
- **执行端：不能说更大。**MRR 打平（0.416 vs 0.415），top1 名义 +1 例但落在 bootstrap 区间内，top3 与中位排名反而更差，逐例配对是 2 胜 6 负。更关键的是无规则对照已经拿到 2.33/11——把整条管线（检索 + 摘录 + 执行）相对于「LLM 凭自己的知识排」的净增益压到不足 1 例。
- **稳定性：更差，而且差得可测。**候选呈现顺序对结果的影响大于整套规则的有无。这是把可审计的机械执行换成 LLM 执行时付出的、之前没有计价的成本。

因此建议的形态不是二选一，而是**摘录做证据层、机械槽位只在能被程序验证的地方保留**：用摘录路径承接「原文说了什么」（可逐字核验），只对带明确切点的句子（本轮 2.8% 的规则解析出了阈值）生成可执行的层一柱子，其余留作 LLM 或人工阅读的材料。这也解释了 §16 的 F7 门闸为什么有效——它做的正是「只在程序能验证的地方保留强槽」。

**本节的口径告诫**：11 例、单一 backbone（`meta-llama/llama-3.3-70b-instruct`）、每臂 3 次重复。所有臂间差异都在 bootstrap 区间内互相重叠；§17.4 的顺序效应和 §17.2 的抽取忠实度是本节唯二在噪声之外的结论。人工判读只有 39 条、单标注者、只覆盖 74 号例。

### 17.7 错误模式对照：不是同一类错换了名字

§17.2 说摘录「不再作逻辑断言」，§17.6 说七元组的错是恶性、摘录的错是良性。这两句都对，但不够。两条路径的失败**不住在管线的同一层**，对同一条临床漏判，坏掉的模块也不同。冻结：`altpath_error_mode_census.json`。

#### 17.7.1 错误发生在哪一层

七元组抽取器被强制做一件事：把一句原文**承诺**成闭集 `relation / polarity / modality / threshold`。错误是**形式化承诺错误**——quote 没有授权这个槽，槽却被写进去了，并且机械引擎会执行它。F7 能修，正是因为承诺落在可检查的槽上。

替代路径把承诺拆成三步，每一步有自己的错：

| 步 | 做什么 | 错误形态 |
|---|---|---|
| 摘录 | 整句抄下来，标一个病名 | 抄了不该抄的、挂错病、指代悬空。**不作**必要/充分/排除的承诺 |
| 选择 | 按语料重复次数取每候选 top-K | 决定性句子在 unique 集里，但不进入执行器窗口（N1） |
| 执行 | findings + 窗口内句子 → ranking + `supported/neutral/ruled_out` | 把摘录拒绝作出的逻辑承诺，在这里**不透明地重新做一遍**（N6/N7），外加顺序（N8）和参数化先验（N9） |

所以「提取正确率高」只覆盖第一行。排名由三行一起决定。把七元组 0.74 的 relation 错误率拿来和摘录 0.205 的「可执行诊断规则率」比，比的不是同一个随机变量。

#### 17.7.2 七元组错类在替代路径上的命运

不是消失 / 残留二分。有四种归宿：**构造上消失、伤害塌缩、迁到执行器、选择层重演**。

| 错类 | 七元组上做什么 | 替代路径上的命运 |
|---|---|---|
| **E14** 阈值幻觉 | 槽里出现引语没有的数字 | **消失。**阈值只从抄出的句子解析；非逐字跨 1.3% 已被丢掉 |
| **E12** 循环定义喂层二 | LQTS `pathognomonic_for prolonged QT` 来自 *termed long QT syndrome*，C0 给 LQTS +2 确认、金标第 2 | **伤害塌缩。**定义句仍被摘（LQTS cap40 第 2、第 12 条仍是 TdP / characteristic arrhythmia），但没有层二槽可开火。C0 那种靠 tautology 翻盘不再发生 |
| **G1** 真必要双槽进 pathognomonic | Type I *necessary for the diagnosis* 同时写成 `pathognomonic_for` | **提取端修好。**同一句在 Brugada cap40 第 3 条整句保留。执行器 3/3 把 Brugada 标 `ruled_out`（病例：Brugada pattern absent） |
| **E9** 析取拆成两条独立 obligatory | 326 `bacteriologic and/or serologic` → 两条 `required_for`+`obligatory`，C0 金标被层一淘汰、排名 12 | **提取端消失，选择层埋掉。**Harrison 原句在 unique 集第 **111** 位，cap 40 根本看不到。拆分无法开火 |
| **A–F / E4** 假必要 | 检查清单 / advised / 家系 essential / ICD 适应证写成诊断必要 | **提取端修好、执行端可重演。**74 的 B 类标本 `"Exercise testing is advised, but a negative exercise test does not exclude…"` 整句进了 CPVT cap40 第 18 条——后半句的反证还在，执行器也没有把 CPVT 杀掉。326 的 `"Diagnose Brucellosis by blood or CSF cultures"` 却以 x6 占住 cap40 **第 1 条**，金标 2/3 被 `ruled_out`：方法句被当成缺检查就排除 |
| **G2** 切点写成 `excludes`+`negated` | 74 的 `required_for` 带 440/460 的条数为 0；层一不能比 QTc | **提取修好、执行失败。**见 17.7.3 |
| **G3** 合取阳性支写成 `feature_of` | CPVT 共识第 1 条双向 VT 全是 `feature_of` | **提取修好、选择层重演。**共识原句在 unique 集第 **44** 位，cap 40 之外；cap 100 才进窗口（#44、#47）。支持度排序把 G3 的「阳性支进不了层一」重演成「阳性支进不了 prompt」 |
| **E3** 情态抬升 | usually must → obligatory | 槽没了，英文 hedge 留在句子里。326 那句 usually must 排在 unique #111，执行器没看见；看见的是另一句方法句 |
| **E2** 极性反转 | 槽 polarity 与 quote 相反 | 不能存成槽。执行器仍可在应用时反转（326 金标 `ruled_out`） |
| **E10** 治疗当诊断 | 槽 `context_type=treatment` 仍可进层一 | `use=treatment` **可过滤但未过滤**。LQTS cap40：诊断 21 / 治疗 10 / 预后 5 |
| **E7** 空谓语 | 裸 imaging | 少于 6 词丢掉；表格单元格仍在 |
| **E5 / E13 / 主语绑定** | this variant；主谓对调 | **共享。**同一 `subject_match`。74 绑到 CPVT 的 223 条里，**90 条（40%）** 的 `disease` 是泛化的 ventricular tachycardia / PVT，不是 CPVT |
| **E11** 离题但局部忠实 | 不计 relation 错，仍绑定打分 | **共享。**NL 上伤害是占窗口，七元组上还可以变成一条 `feature_of` 加分 |
| **O1** 逆命题未抽 | 773 只有正命题 | **共享。**摘录器只抄存在的句子，发明不了逆命题 |

一句话：替代路径消灭的是**可执行的虚假逻辑力**（E14、E12 的层二、G1 双槽、E9 的两条独立必要），不是消灭「模型会把建议当成必要」这个偏好。后者从槽位迁到了执行器。

#### 17.7.3 同一条临床漏判，坏掉的模块不同

**74 QTc → 排除 LQTS。** 病例 findings 里有 `QTc interval = 380 ms`、`Brugada pattern` absent、`wall thickness` normal。人工树用切点排除 LQTS。

- 七元组：G2 把 `"A normal QTc in men is less than 440ms, and in women, it is less than 460ms."` 写成 `excludes`+`negated`。层一 `excludes` 的开火条件是发现 **present**，不读 threshold；380 与 500 同等处理。同时 E12 把病名循环喂给层二，C0 的 top1 是 LQTS，金标第 2、**未被淘汰**。F7 修的是 E12（层二不再确认 LQTS），**不是**补上 440 的层一柱。
- NL：同一句在 LQTS cap40 **第 5 条**（x6），另有 `"Long QT syndrome – QTc >0.450 sec"` 在第 11 条并带程序解析的阈值。病人数字也在。执行器对 LQTS 的三次判决是 **neutral / supported / neutral**——`ruled_out` 为 0。CPVT 仍排第 1，是因为自身被标 `supported`，不是因为 LQTS 被排除。

对照同一例的 Brugada：Type I *necessary for the diagnosis* 在 cap40 第 3 条，finding 是 pattern absent，执行器 **3/3 `ruled_out`**。执行器会用「点名的 ECG 形态缺席」，不会做「380 < 440」这种两边都在 prompt 里的数值比较。机械引擎的 `threshold_ok` 正是为后一件事写的，却被 G2 饿死；NL 把两个输入都补回来了，比较仍然没做。

因此 NL 在 74 上「赢」C0，机制与 F7 不同：F7 关掉一条假确认，NL 从不发那条假确认，也从不发那条真排除。排名指标把两种机制算成同一分。

**326 and/or → 不得用阴性结核血清学杀布鲁氏菌。**

- 七元组：E3+E9，C0 金标层一淘汰、排名 12；C1+F7 不再淘汰、排名 3。
- NL：真正的 `usually must be supported by bacteriologic and/or serologic tests` 在 unique **#111**。窗口第一条是 `"Diagnose Brucellosis by blood or CSF cultures"`（x6）。finding 是 `blood cultures grew a Gram-negative bacillus`（未点名 Brucella）。`nl_rule` 金标 2/3 `ruled_out`、排名 9–11，与 `none` 臂（9–11，1/3 淘汰）同形。E9 拆分没有了；A 类「方法当成必要」在另一句话上由执行器重做，再叠上对椎管内脓肿的参数化偏好。

#### 17.7.4 替代路径独有的错类（N1–N11）

七元组 schema 里不存在这些槽，所以它们不是「提取错误的变体」，是换执行器之后新出现的。

| 代号 | 错类 | 含义 | 本轮标本 |
|---|---|---|---|
| **N1** | 支持度埋葬 | 决定性诊断句在 unique 集里，赢不了 cap-K | CPVT 共识第 44；326 Harrison and/or 第 111 |
| **N2** | 上位类过绑定 | `subject_match` 把泛化 VT 规则挂到 CPVT 上 | 74：40% 的 CPVT 绑定规则主语是 VT/PVT |
| **N3** | 表格行当句子 | 去表头后的单元格被当成规则 | 39 条样本 9/39；CPVT cap40 #31–32 是评分表行 |
| **N4** | 悬空指代 | 句子级摘录丢掉先行词 | 39 条里 1 条 *It is also indicated…* |
| **N5** | 治疗句占窗 | `use=treatment` 标了但不丢 | LQTS cap40 的 1/4 是治疗 |
| **N6** | 执行器对已回收切点欠火 | 规则和病人数字都在，不标 `ruled_out` | 74 LQTS 0/3 淘汰 |
| **N7** | 执行器过火 / 方法当必要 | 高支持度工作流句被当成缺检查就排除 | 326 金标 2/3 `ruled_out` |
| **N8** | 候选呈现顺序 | 打乱顺序对排序的扰动大于撤走全部规则 | §17.4 τ 0.33 vs 0.61。机械引擎对顺序恒等 |
| **N9** | 参数化先验压过规则 | 无规则对照已经把错误病排第一，给规则推不走 | 56：`none` 与 `nl_rule` 都是 UPS 第 1、金标第 17 vs 19；179：都是 PA-VSD 第 1、金标第 13 vs 11 |
| **N10** | 输出截断 | ranking JSON 截断，未点名的候选按呈现顺序垫底 | cap 100 时 **773** 一次 `n_ranked_by_model=0`（先前误记为 522）。机械引擎不会截断排名 |
| **N11** | 软埋葬（不淘汰） | 金标排到 8–19，verdict 经常是 `neutral` | 56、179、475、326。机械引擎中位排名 3，金标掉不出中段 |

N6 与 N7 是同一枚硬币：执行器重新获得了作逻辑承诺的权力，却没有 schema、也没有 F7。欠火和过火可以在同一例里同时发生——74 对 LQTS 欠火、对 Brugada 过得恰好；326 对金标过火。

N9 是替代路径相对机械引擎最不像「规则系统」的一点。机械引擎没有参数化诊断先验：候选不得分就不排前面。LLM 执行器在 56/179 上的错误**与规则表示无关**——换七元组、换摘录、不给规则，top1 仍是同一个错病。§17.3 里「无规则对照已经 2.33/11」不是附录，是这条路径的主误差项。

#### 17.7.5 伤害极性与可否审计

| | 七元组抽取 | NL 摘录 | LLM 执行 |
|---|---|---|---|
| 极性 | 逻辑力的**假阳性**（把建议写成必要） | 逻辑力的**假阴性**（什么都不承诺）加窗口污染 | 逻辑力的**无约束再引入**（欠火+过火） |
| 一条错的代价 | 层一可杀金标（326 C0）；层二可让竞争者冒充确诊（74 C0） | 多占一条上下文；默认不淘汰 | 可杀金标（326）、可不杀该杀的（74 LQTS）、可把金标埋到第 19（56） |
| 可否程序发现 | 可以。cue 对槽（F7）、NLI 对 quote | 可以。逐字子串、`use=`、病名是否在段内 | **不可以**用同一套门闸。要门，得在执行器上另做「这句话是否授权对这个 finding 作 ruled_out」的 NLI/阈值引擎 |
| 修复方向 | 降槽、不升槽（F7 的边界） | 换选择器（支持度不是决定性）、过滤 `treatment`、收紧绑定 | 把可验证切点交回机械层一；执行器只读没有切点的句子 |

§17.2 样本上「虚假逻辑断言 = 0」仍然成立，它说的是摘录器。执行器在 326 上作出了虚假排除、在 74 上作出了虚假中立，这两条都不进那 0。把提取正确率当成路径正确率，会把 N6/N7 藏过去。

#### 17.7.6 对 §17.6 建议的收紧

「摘录做证据层、机械槽位只在能被程序验证的地方保留」仍然对，但要补一句执行器做不到的事：**数值切点不能交给 LLM 执行。** 74 是直接反例——句子在第 5 条、数字在 findings、比较没有发生。G2 饿死的 `threshold_ok` 一旦有了两端输入，就应该由程序算，而不是再进执行器 prompt。LLM 执行器留下来的合理工作，是 N9 已经表明它本来就会做的那部分（把 vignette 读成鉴别），以及没有切点、只有整句英语的材料（G1 那种 *necessary for the diagnosis* 形态缺席，74 的 Brugada 说明它可以）。

N1 也把「多给上下文」从 §17.5 的经验观察写成机制：cap 40→100 让 CPVT 共识句从窗外走进窗口，这不是执行变聪明，是选择器的召回涨了。支持度排序与诊断决定性反相关（治疗句、病名定义句被重复最多），所以 N1 不会随模型换代自动消失，除非换排序键。

#### 17.7.7 错误类型案例分析

口径与 §14.4 相同：给指南原文、原始语义、七元组怎么写（若适用）、NL 摘录/选择/执行怎么处理、以及判错原因。N 类是替代路径独有；E/G 类给「同一原文在两条路径上的不同失败」。标本除非注明，来自 74 / 326 / 56 / 179 / 475 / 773 / 522。

**N1 + G3 — 决定性合取句被支持度埋到 cap 40 窗外（74 CPVT）**

专家共识表（与 §14.4 G3 同一句）：

> CPVT is diagnosed in the presence of a structurally normal heart, normal ECG and unexplained exercise or catecholamine induced bidirectional VT or polymorphic PVCs in patients < 40 years of age.

语义：诊断合取 **A ∧ B ∧ C**。七元组：A/B 写成 `required_for`，C（双向 VT）全部 `feature_of`——阳性支进不了层一。NL：原句逐字在 unique 集里，按语料重复次数排第 **44**，cap 40 看不到；cap 100 才进窗口（#44、#47）。执行器实际看到的 CPVT 前 8 条是：

| # | 句子（压缩） | 问题 |
|---|---|---|
| 1 | CPVT is an inherited … disorder associated with exercise-or stress-induced ventricular arrhythmias | 定义，不是判据 |
| 2–5 | VT 心率与晕厥、血流动力学、多形 VT 不稳定 | **N2**：泛化 VT 生理，不是 CPVT 诊断 |
| 6–7 | 硫酸镁治疗多形 VT / Long QT-induced PVT | **N5**：治疗，且 #7 主语是 LQTS |

原因：选择键是「这句话被多少个 passage 重复」。定义句、ACL S 治疗句、VT 生理句在语料里反复出现；共识表只在少数指南里出现一次。G3 的「阳性支写错槽」在 NL 上重演成「阳性支进不了 prompt」。不是摘录器没抄到。

**N2 — 上位类过绑定：VT 生理句挂到 CPVT（74）**

原文（与 CPVT 无关的 VT 综述）：

> The likelihood of syncope with ventricular tachycardia is in part dependent on the ventricular rate; rates below 200 beats/min are less likely to cause syncope.

语义：任何 VT 的血流动力学，不是 CPVT 的诊断规则。摘录器 `disease=Ventricular tachycardia` 相对该句是对的。`subject_match` 把 "ventricular tachycardia" 接到候选 **Catecholaminergic Polymorphic Ventricular Tachycardia**（标签字符串包含这几个词）。本案绑到 CPVT 的 223 条里 **90 条（40%）** 主语是泛化 VT/PVT。cap 40 第 2–5 条全是这类。七元组同一匹配器也有 E1/E13，但谓语是短名词，泛化 VT 较少整段灌进一个病。NL 的「整句」把伤害放大成窗口污染。

**N3 — 去表头的评分行被当成规则（74 CPVT cap40 #31–40）**

原文是 CPVT 诊断评分表的一行，表头（项目 / 分值）在邻块：

> Inducible bidirectional ventricular tachycardia at HR > 100 bpm	4

语义：评分表的 +4 分项，不是「心率 >100 即可诊 CPVT」。NL 整行抄下；程序侧还从中解析出 `threshold > 100 bpm`——数是真的，**谓词被抬成了切点规则**。七元组碰到同一类表格，常写成 `feature_of` 或空谓语（E7）。NL 没有槽，伤害是执行器可能把 +4 分项读成诊断必要。本案双向 VT 真正的合取句在窗外（N1），窗口里只剩评分行，看起来像「有双向 VT」，其实是一张残表。

**N4 + N5 — 悬空 *It* 与治疗句占窗（74 LQTS）**

连续两句（StatPearls，摘录器拆开）：

> An implantable cardioverter defibrillator (ICD) is recommended in patients with Long QT syndrome who were resuscitated from a cardiac arrest. It is also indicated in those who have beta-blocker-resistant symptoms or have contraindications to beta-blockers.

语义：ICD 的第二适应证；*It* = ICD。NL：后一句单独成条，`disease=Long QT syndrome`，`use=treatment`。cap 40 第 22 条是前一句，第 23 条是 *It is also indicated…*，第 24 条 *It also may be indicated in asymptomatic individuals…*——三条指代链断开。同窗还有 Nadolol/propranolol、Mexiletine、硫酸镁（第 6–8、19–21 条）。`use=treatment` **已经标对**，执行器提示词没有丢弃。病例是 21 岁晕厥后 VF、QTc 380、无心脏骤停史后的 ICD 讨论对象——这些治疗句与「能不能诊 LQTS」无关，却占掉 10/40 条。七元组对应 E10：同一适应证写成诊断 `required_for`，层一可开火；NL 不开火，只挤掉诊断句。

**G1 — 真必要整句保留，执行器这次用对了（74 Brugada；对照 N6）**

> When present in at least 2 of the three precordial leads, V1, V2, and V3, the type I pattern necessary for the diagnosis is satisfied.

语义：Type 1 在 ≥2 个右胸导联是诊断**必要** ECG，不是单独充分。七元组：**同一 quote 两条**——`required_for`（对）和 `pathognomonic_for`（错，G1）；层二会把任何 Type-1 样接合当确诊加分。NL：整句在 Brugada cap40 **第 3 条**，没有双槽。病例 finding：`Brugada pattern` **absent**。执行器 **3/3 `ruled_out`**。说明：缺席一个点名的 ECG 形态时，执行器**会**作排除；G1 的「额外发明充分性」在无槽路径上构造性消失。

**N6 + G2 — 切点回收了，数值比较没做（74 LQTS）**

与 §17.7.3 同一标本，这里补两端输入。指南：

> A normal QTc in men is less than 440ms, and in women, it is less than 460ms.

语义：超过才进入先天 LQTS 的概率评分。七元组：`(LQTS, excludes, normal QTc, negated)`，threshold 不进层一；本案 `required_for` 带 440/460 的条数为 0。NL：同一句 LQTS cap40 **第 5 条**（x6），另有 `"Long QT syndrome – QTc >0.450 sec"` 第 11 条并带程序解析阈值。病例 finding：`QTc interval = 380 ms`（女，<460）。执行器三次：`neutral / supported / neutral`，`ruled_out` = 0。原因不是没看见规则：看见了，没有做 380<440 的比较。与 G1 对照：同一执行器、同一病例、同一轮调用，点名形态缺席会排除，数值切点不会。机械引擎的 `threshold_ok` 正是为后一件事写的。

**E14 — 七元组发明引语没有的 440；NL 发明不了（74）**

七元组 quote 仅为 `"congenital long QT syndrome"`，同条却带 `threshold {operator: ">", value: 440, unit: "ms"}`，relation 还是 `pathognomonic_for`。引语去掉病名后剩不下切点，数是模型从别处（或参数化知识）填的。NL：阈值只从抄出的句子解析；这句话若被抄成 `"congenital long QT syndrome"` 会因不足 6 词丢掉，抄成带 440 的整句才有阈值。E14 在摘录路径上**构造性消失**。残留的假切点改走 N3（表格行里真有一个数，但不是这条规则的数）。

**E12 — 循环定义：七元组喂层二，NL 只占窗口（74 LQTS）**

七元组若干条 `pathognomonic_for prolonged QT interval`，quote 是 `"a condition termed long QT syndrome"` / `"congenital long QT syndrome"` / `"long QT syndrome (Fig.16.35 )"`。C0 拿去给 LQTS +2 确认，金标第 2。NL cap40 第 2 条仍是 TdP 定义、第 12 条 `"LQTS … with torsades de pointes as its characteristic arrhythmia"`——定义句还在，但没有层二槽。伤害从「假确诊」塌成「占两条窗口」。C0 那种 tautology 翻盘不再发生。

**E9 + E3 → N1 埋葬，N7 在另一句上重演（326 布鲁氏菌）**

Harrison：

> the clinical diagnosis usually must be supported by the results of bacteriologic and/or serologic tests

语义：usually；bacteriologic **或** serologic。七元组：两条独立 `required_for`+`obligatory`（E3 情态抬升 + E9 析取拆分）。病例有 `serological test for tuberculosis was negative`，层一接到后一条，C0 金标淘汰、排名 12。NL：原句逐字在 unique **第 111** 位，cap 40 没有——拆分无法开火。窗口第 1 条换成了另一句：

> Diagnose Brucellosis by blood or cerebrospinal fluid cultures and treat with doxycycline plus either rifampin or streptomycin…

语义：诊断**方法**（血培养 **或** 脑脊液）+ 治疗方案，不是「培养没长出 Brucella 就排除」。病例：`blood cultures grew a Gram-negative bacillus`（未点名 Brucella），另有 `exposure to unpasteurized sheep stomach`。`nl_rule` 金标 2/3 `ruled_out`、排名 9–11，与 `none` 臂同形。原因：E9 消失了；A 类「方法当成必要」在支持度最高的另一句话上由执行器重做，再叠 N9 对椎管内脓肿的先验。finding 里的暴露史本应支持布鲁氏菌，执行器没用。

**N7 细节 — 过火的是缺「点名病原」，不是缺培养。** 培养已经阳性（GNB）。执行器把「Diagnose by cultures」读成「培养必须长出病名」，这是参数化的更强必要，原文 `or CSF` 的析取也丢了。七元组至少把错误写在槽里（可被 F7/人工看见）；NL 的过火只存在于 `ruled_out` 标签，prompt 级审计看不到「它用了第 1 条而不是第 111 条」。

**N8 — 同一规则、换候选顺序，金标从第 2 掉到第 13（475）**

金标 Parsonage-Turner（神经痛性肌萎缩）；领地竞争者是前骨间神经综合征（AIN）。人工树用「超出 AIN 支配」排除 AIN。`nl_rule` 三次打乱顺序：

| 重复 | 金标排名 | top1 | 金标 verdict |
|---|---|---|---|
| 0 | **2** | AIN | supported |
| 1 | **13** | AIN | 模型未点名（垫底） |
| 2 | **13** | AIN | 未点名 |

规则材料相同，变的只是候选在 prompt 里的出现次序。`none` 臂同样是 4 / 13 / 13，说明顺序敏感性不依赖规则，规则也压不住。机械引擎对候选顺序恒等。522 是同一现象的另一面：三次 top1 在 DLB 与慢性缺血性脑病之间跳，金标（紧张症+DLB 复合）排名 5 / **11** / 5，中间一次还被标 `ruled_out`。

**N9 — 参数化先验压过规则（56 梭形细胞鳞癌；179 低氧性血小板减少）**

56：69 岁下牙龈息肉样肿物，15 年前颊黏膜鳞癌放疗后；IHC `p63` 阳性、`pan-cytokeratin` 阴性。金标梭形细胞鳞癌。`none` 与 `nl_rule` 的 top1 都是未分化多形性肉瘤（UPS），金标排名 17 vs 19。规则没有把 top1 从 UPS 推开。

179：新生儿发绀，SaO2 与血小板多次共变；金标缺氧诱导性血小板减少。两臂 top1 都是肺动脉闭锁+VSD（结构诊断），金标 13 vs 11。语料里本就几乎没有共变规则（§14.4，D），执行器退回「先给解剖诊断」的先验。机械引擎没有这套先验：不得分就不排前面；这两例机械中位在第 4–6，失败是 D/L，不是先验。

**N10 — JSON 截断后按呈现顺序垫底（773，cap 100）**

cap 100 把每候选规则加到约 592 条/例，773 一次输出在 `"Eisenmenger Syndrome" … "The term Eisenmenger's syndrome is applied to patients with a large communication betwee` 处被截断，`n_ranked_by_model=0`。解析失败后，未点名的候选保持**打乱后的呈现顺序**作为排名。该次 `gold_rank=1`（IPAH+PFO 碰巧排在呈现序列第一）——这是截断的运气，不是规则执行。机械引擎不会因为材料变多而丢排名。§17.5「cap 越大越好」在单次调用上有这个反例。

**N11 — 不淘汰、埋到第 19（56）**

`nl_rule` rep0：金标梭形细胞鳞癌 **排名 19 / 23**，verdict `neutral`，不是 `ruled_out`。前面是 UPS、肉瘤样癌、MFH、放射性肉瘤等一串软组织肿瘤。层一没有开火，金标也没有被一条假必要杀掉——只是覆盖计数/先验把真正带 p63 的诊断压到末尾。机械引擎同例 C1 排名 6：加法会淹没，但中位仍在中段。N11 是替代路径把「恶性杀伤」换成「软埋葬」之后，top3/中位排名反而更差的机制。

**E11 — 离题但局部忠实：癫痫段占 74 的窗口**

病例是 CPVT，候选集里有 Seizure disorder。NL 绑到该候选 85 条，例如 `"Diagnosis is confirmed by EEG"`、新生儿惊厥流行病学、表格行 `Seizures	Epilepsy	Detailed history…`。相对那些段落局部忠实，对 CPVT 鉴别无用。七元组不计 E11 为 relation 错，但仍可给癫痫候选加 `feature_of` 分；NL 伤害是占 85 条绑定（cap 之后仍占该候选的 40 槽）。执行器 74 上有时把 Seizure disorder 标 `ruled_out`（rep2），有时不——离题材料的应用也不稳定。

**O1 — 逆命题：NL 抄到了转向句，执行器仍把 Eisenmenger 排第一（773）**

金标是 IPAH+PFO，不是 Eisenmenger。NL 在 Eisenmenger 的 cap40 里**有**转向句：`"Without early repair, reversal of a left-to-right shunt may result in a bidirectional or right-to-left shunt."`（第 3 条）、`"the left-to-right shunt will become a right-to-left shunt, resulting in … cyanosis"`（第 14 条）。七元组主文件缺这条逆命题（O1）；NL 摘录端其实修好了。`nl_rule` 三次 top1 仍是 Eisenmenger / 三尖瓣反流 / Eisenmenger，金标第 2。执行器没有用「无大的左右交通 + 无发绀」去排除 Eisenmenger。O1 从「没抽到」变成「抽到了不用」（N6 的非数值版）。

**E4/B 提取端修好的对照 — 不要把 N7 当成「假必要从未消失」。** 74 同一篇里：

> Exercise testing is advised, but a negative exercise test does not exclude a diagnosis if other sentinels such as syncope, family history or positive genetics are present.

七元组：`(CPVT, required_for, exercise test)`，quote 截成 `"Exercise testing is advised"`，后半句反证丢掉。NL：整句在 CPVT cap40 **第 18 条**。执行器没有因此把 CPVT 标 `ruled_out`。同一偏好（把检查当必要）在 74 上被整句救下来，在 326 上因另一句高支持度方法句而在执行器重演。差别是**哪一句进了窗口**，不是模型不会再把建议当成必要。

### 17.8 产物文件



| 文件 | 内容 |
|---|---|
| `trial_nl_rules_k30all4.json` | 11 例逐字规则句摘录（2683 个唯一 passage，16145 条留存） |
| `trial_nl_rules_k30all4_stats.json` | 摘录端调用与后处理统计（逐字率、丢弃原因） |
| `llm_executor_findings.json` | 五臂 × 3 次重复（病人证据 = findings，打乱顺序） |
| `llm_executor_vignette.json` | `none`/`tuple_quote`/`nl_rule` × 3 次（病人证据 = 原始 vignette） |
| `llm_executor_nl_cap12.json` / `_cap100.json` | 每候选规则条数上限消融 |
| `llm_executor_fixedorder.json` | 固定候选顺序的 3 次重复：分离解码噪声与位置敏感性 |
| `llm_executor_comparison.json` | 汇总表、与机械引擎的逐例配对与符号检验、稳定性分解 |
| `case74_nl_rule_quality_census.json` | §17.2：39 条摘录的人工判读与决定性规则回收情况 |
| `altpath_error_mode_census.json` | §17.7：E/A–F/G 错类在 NL 路径上的归宿、N1–N11、74/326 同漏判对照；案例分析见 §17.7.7 |

---

## 18 把 11 例整体变成测试集：门闸的第一次无污染测量

到 §16.8 为止的每一条门闸规则，都是从这 11 例自身induce 出来的——先是 74 号例的全量普查，再是其余十例的 200 行标注。用它们量自己的规则，量出来的 0.893 是**样本内**数字，不能回答「这些规则是构式级的，还是把 11 例背下来了」。本节换一批病例重做这件事。

### 18.1 为什么不必重跑四方法

原以为新病例需要先跑 multi-stance / collapse3c / IMPC / forest 才有候选集。核查 `logs/backbone_v1/` 后发现**四方法早已在全部 800 例上跑完**，逐例 trace 都在归档里：

| 数据集目录 | collapse3c | multistance | forest | impc |
|---|---|---|---|---|
| `diagnosisarena` | 100 | 100 | 100 | 100 |
| `diagnosisarena_heldout` | 100 | 100 | 100 | 100 |
| `diagnosisarena_heldout200b` | 200 | 200 | 200 | 200 |
| `medcasereasoning` | 100 | 100 | 100 | 100 |
| `medcasereasoning_200b` | 200 | 200 | 200 | 200 |
| `medcasereasoning_v2` | 100 | 100 | 100 | 100 |

`method_hypothesis_recall_48.jsonl` 只是其中 48 例的**分析聚合**，不是候选集的来源上限。`build_trial_tasks_pool.py --from-traces` 直接解析 trace，为 11 例之外的 **789 例**建出任务（12,221 个候选，15.5 个/例），**零 LLM 调用**。通往 800 例的路上没有四方法这笔成本。

### 18.2 检索环境的可复现性核验

当初的索引由 sklearn 1.4.1 腌制，本机只有 py3.8 + sklearn 0.23.2（1.4 需要 py≥3.9，装不上），解 pickle 会报版本警告。与其相信警告，不如量一次：把 74 号例在本环境重跑检索，与冻结的 `trial_retrieval_k30all4.json` 逐条比。

| 指标 | 值 |
|---|---|
| passage 数 | 319（冻结 320） |
| gid 集合 Jaccard | **0.991** |
| 13 个假设中 gid 序列**逐位相同** | 9 |

差异是浮点与并列打破的噪声量级，检索臂可比。`run_trial_retrieval.py` 的 `get_feature_names_out` 加了向后兼容回退（新版行为不变）。

### 18.3 批次设计：让交付自带质检

`trial_tasks_pool6.json` 取 6 个 11 例之外的病例（跨 5 个子集），检索 2,072 条 passage，抽取 ~1,830 次调用、6 分钟。诊断槽去重后 457 条，按 (病例 × 槽) 分层抽 200 行。

新病例没有人工答案可对，所以**混入 30 行 74 号例盲测行**（其人工普查答案已知）打乱编号——标注者分不出哪些是控制行，一次交付同时给出「这位标注者有多准」和「门闸有多准」。

| 控制行（n=30） | 值 |
|---|---|
| 与 74 号例普查一致 | 27/30 = **0.900** |
| κ | 0.672 |
| 分歧方向 | 3 条全是 普查=1 / 标注=0（这位标注者更严） |

κ 低于第 3 轮的 0.822，是 n 小加正例稀疏（30 行里只有 7 个正例）所致；一致率 0.900 与之相当。**注意这把尺子略严于第 3 轮那把**，样本内外的比较要带着这个偏差读。

### 18.4 结果：规则是构式级的

**唯一干净的样本外数字是首测的 0.875**，因为此刻的规则集全部 induce 自 11 例，pool6 未参与过任何一条。分槽：

| 槽 | 11 例内（197 行，**样本内**） | **11 例外（200 行，样本外）** |
|---|---|---|
| `required_for` | 0.91 | **0.95** |
| `pathognomonic_for` | 0.85 | 0.77 |
| `sufficient_for` | 0.91 | 0.86 |
| **总计** | 0.893 | **0.875** |

0.875 对 0.893 只差 1.8 个百分点，`required_for` 反而更高。规则不是把 11 例背下来了。

〔**更正（§18.4.2）**：上面这句话对 `required_for` 的读法是错的。它的 0.95 恰好**等于**该槽的多数类基线 0.95——正例只有 5/93，全判 not-licensed 也得 0.95。这个数字不是「更高」，而是「什么也没测出来」。总计 0.875 同样必须对着 0.800 的多数类基线读，净增只有 7.5 个百分点。见 §18.4.2。〕

按病例聚类的自助法（6 簇）给出 95% CI **[0.87, 0.95]**，与朴素二项 CI 几乎重合（逐例 0.857–1.000，病例间方差不大）——但 6 个簇做自助本身就不稳，这个区间只能当量级看。

**0.910 不是样本外数字。** §18.5 的四处修补是读了这 200 行的分歧之后写的，改完再在同一批行上重测得 0.910；净增的 7 行**全部**来自被我看过的那 25 条。当前规则集没有干净的测量，要拿到它必须换一批病例（37 例的检索已就绪，见 §18.7）。

### 18.4.1 这两个数字量的到底是什么

三层污染，按严重程度排：

**一、`0.893` 完全是样本内。** E15、E16、构式扩展都是拿这 200 行的分歧 induce 出来的。它是拟合值，不是泛化度量，本节列它只为与样本外对照。

**二、尺子不独立于被测对象。** 标注者遵循的公约 1–8 是我从 74 号例普查和 11 例审计里写出来的，与规则同源；控制行锚定的那份普查，§16.8 已经声明过「F7 基线是乐观的——正则是在读过普查之后写的」。所以 0.875 度量的是：**给定一把固定的判读标准，规则的语言覆盖能否迁移到没见过的文本**。它不度量这把标准本身是否正确。真正样本外的是**文本**，不是**判读口径**。

**三、尺子有噪声，且已与信号同量级。** 控制行上标注者与普查一致 0.900（κ 0.672）。也就是说尺子自身约 10% 的误差，与门闸 9–12% 的分歧率已经是同一量级；κ 0.672 还低于第 3 轮那把尺子的 0.822，两批的数字严格来说不同刻度。继续在这把尺子上把数字往上推，很难分清推的是门闸质量还是标注者的偏好。

**结论**：0.875 可以支撑「规则是构式级而非病例级」这一条定性结论——这也是本节要回答的问题。它不能支撑「门闸准确率是 87.5%」这样的绝对读数，更不能用来做百分点级的方法比较。

### 18.4.2 更正：这些一致率必须对着多数类基线读，以及被降级的真高权逐条手审

§18.4 把 0.875 与 0.893 并排，暗示门闸在这三个槽上都学到了东西。这个读法是错的，因为**它没有给出多数类基线**。真高权在这两批标注里都是少数类：

| 批 | n | 标注判「授权」 | 多数类基线（全部降级） | 门闸一致率 | 净增 |
|---|---:|---:|---:|---:|---:|
| pool6（11 例外） | 200 | 40（20.0%） | 0.800 | 0.910 | **+0.110** |
| case74 留出普查 | 225 | 22（9.8%） | **0.902** | 0.929 | **+0.027** |

分槽看（pool6，当前门闸），差异更刺眼——这里报的是**对「真授权」那一类的召回**，即过度降级的直接量度：

| 槽 | n | 真授权 | 门闸保留 | 召回 | 95% CI | 该槽多数类基线 | 该槽一致率 |
|---|---:|---:|---:|---:|---|---:|---:|
| `pathognomonic_for` | 57 | 27 | 23 | **0.85** | [0.70, 0.96] | 0.53 | 0.84 |
| `sufficient_for` | 50 | 8 | 8 | **1.00** | [1.00, 1.00] | 0.84 | 0.92 |
| `required_for` | 93 | 5 | 2 | **0.40** | [0.00, 0.80] | **0.95** | **0.95** |

**`required_for` 那一行是 §18.4 结论的反例。** 它的 0.95 不是「反而更高」，而是**恰好等于全判 not-licensed 的基线**：正例只有 5/93，门闸在这个槽上没有产生任何可测量的增益，同时把 5 条真必要中的 3 条降掉了。CI [0.00, 0.80] 说明 5 个正例根本不足以估计这个召回——**这个槽此前从未被有效测量过**。门闸真正做出贡献的是 `pathognomonic_for`（0.84 对基线 0.53）。

#### 被降级的真高权：逐条手审，不借助排名

判断降级对不对**不能**用「改了排名没有」来反推：排名是另一个下游任务，有自己独立的误差源，而 §19 已表明它对几乎一切都不敏感。所以把两批标注中「普查判为真高权、当前门闸降级」的行全部取出直接读（`audit_false_demotions.py` → `false_demotion_audit.json`、`batch_false_demotions.tsv`）。case74 普查含 134 条 `excludes`，pool6 的 `DIAGNOSTIC` 只有三个诊断槽、不含 `excludes`。全 425 行都能匹配回抽取原文，pool6 复现冻结值（召回 33/40、一致率 0.910），case74 复现 §18.6 的 0.929。

共 **12 条**假降级。逐条读完的归类：

| 归类 | n | 行 | 判定 |
|---|---:|---|---|
| 特异度／characteristic 声称 | 5 | Brugada「characteristic ECG pattern」、畸胎瘤「are highly specific」、SFT「specificity is 100% for」、PCP「almost 100% sensitive and specific for」、CMV colitis「high sensitivity and specificity for diagnosing」 | **不是缺陷**，是 §18.5 已记录并有意未编码的标准分歧 |
| 词表缺口 | 1 | ARVC「ε sign **indicative of** ARVC」 | **真缺陷**。`indicative of` 与词表已有的 `diagnostic of` 同构，纯属漏收 |
| 引语被截断，授权语在相邻从句 | 2 | CPVT、结节病 | **真缺陷**，见下 |
| 普查判错，门闸判对 | 2 | 先天性肌强直「diagnosis is made with a combination of clinical, electrophysiological, and genetic studies」（§14.4 的 A 型检查清单）；ETEC「large inoculum is needed to **produce disease**」（致病必要 ≠ 诊断必要） | **门闸正确**，普查标签错 |
| 无对应规则类 | 2 | 癫痫持续状态「发作 >5 分钟」（定义即判据）；输血相关细菌感染的病例定义 | 灰区，当前无 cue 类可依 |

**两条截断型值得单列，因为它们是可修的，而且原因是两重的。** 结节病 `required_for exclusion of alternative diagnoses`：引语只有「exclusion of all alternative diagnoses」，而段落原文是「the diagnosis of sarcoidosis should rely on three criteria, two positive … and one negative (exclusion of all alternative diagnoses…)」，`NECESSITY_CUE` 在段落里能命中（"These two criteria must"），在被截断的引语里命不中。CPVT `sufficient_for pathogenic mutation`：引语被截成关系从句「who have a pathogenic mutation」，段落原文是「CPVT **is diagnosed in patients (index case or family member) who** have a pathogenic mutation」——`SUFFICIENCY_CUE` 里本就有 `diagnosed in (patients|…) (who|with)`，但它要求相邻，被括号插入打断了。**这是 §18.5 已经修过两次的同一族形态学脆性的第三个变体**（单复数、副词插入、名词短语插入，现在是括号插入）。

两条都有两个独立成因：抽取把引语截短（即 §20.2 的 `NEW:predicate_truncated` 作用在授权语上），以及门闸只在引语里找 cue。后者是设计上的不对称——门闸对**阈值**已经有 `E14_licensed_from_passage` 会去段落窗口里取证，对 **cue** 却没有同等机制。

#### 结论

用户的质疑成立，但落点需要精确：

1. **0.875 / 0.910 / 0.929 都被少数类撑高了**，必须对着 0.800 / 0.902 的基线读；§18.4「`required_for` 反而更高」那句话是误读，该槽的表观优势全部来自类不平衡。
2. **确实存在真高权被错误降级**，但直接手审的量级是 12 条，其中只有 **3 条是当前可修的门闸缺陷**（1 条词表漏收 + 2 条截断/仅读引语），5 条属已记录的标准分歧，2 条其实是普查自己标错。
3. **`required_for` 槽的门闸质量至今没有有效测量**（正例 5 个，CI 覆盖 [0, 0.80]）。要判断它是否在系统性地清除真必要，必须专门富集这一槽的正例重新标注，而不是继续在自然分布上抽样——在 5.4% 的正例率下，200 行的批次期望只能带来约 11 个正例。

（附带记账：先前那个「恢复金标身上全部 545 条降级、排名一个名次不动」的探针，按上述方法学不作为抽取质量的证据，仅说明排名对这一层不敏感；结论以本节的逐条手审为准。另：复现 pool6 判定必须设 `F7_EXTRA_RETRIEVAL=trial_retrieval_pool37k30all4.json`，否则段落解析失败会把假降级虚报成 18 条。）

### 18.5 首测 25 条分歧：两类脆性 vs 一类判断分歧

以下修补**消耗了 pool6 的样本外资格**：9 行由分歧转为一致、2 行新破，净 +7（0.875 → 0.910），被修的行全在下表所列的 25 条之内。列出来是为了记账，不是为了主张改进幅度。

**已修（纯正则脆性，不涉及判断）**

| 现象 | 原因 | 例 |
|---|---|---|
| 单复数不一致 | `PATHO_CUE` 只写了 `is diagnostic` | "trophozoites or cysts in stool **are** diagnostic" |
| 助动词与分词间插副词 | `is (confirmed\|established)` 要求相邻 | "is **generally** established with PCR" |
| 主语名词短语横插其间 | `diagnos\w+\s+(is\|are)` 要求相邻 | "Diagnosis **of CMV infection** is generally established" |
| 排他式未收 | 无 | "can only be **achieved** through histology"、"the only **definitive** test" |

这四处改的是形态学容差，不是判断标准——一条规则不该因为原文用了复数或插了个副词就失效。补 2 条 out-of-domain 标本（`od_patho_plural_agreement`、`od_sufficiency_adverb_infix`），自测标本 37 → 39 条全过。

**未修（判断分歧，证据不足以编码）**

一是**特异度陈述**（"highly specific for"、"specificity is 100% for"、"almost 100% sensitive and specific"）：这位标注者在 `pathognomonic_for` 上判为授权（5 行），在 `sufficient_for` 上却拒绝了同构的 pheochromocytoma 97%/93% 行。他交付时把判据写明了，且在同一病例内成对地用：

- STAT6「combined **specificity** 100%」判 1，而同案 STAT6「diffuse nuclear expression in **100% cases**」（敏感度方向）判 0；
- 肉芽肿「the histological **hallmark** of sarcoidosis is…」判 1，而「sarcoidosis is **characterized histologically by**…」（病→征，必要性方向）判 0；
- pheochromocytoma 97%/93% 在 `sufficient_for` 判 0，理由是该句自认存在假阳性。

即「高特异度授权收入（pathognomonic），高敏感度指向必要性而非收入，并列统计量不构成充分性」。这个区分刻意、一致且自洽，但仍只有一位标注者的证据；要编进规则，应先用第二把尺子复核这一族。

（他还把两条从纯语言看更严的界线记了下来：单个化验 cutoff 若通篇无要求性断言则按公约 8 判 0，与公约 5 的「计数标准」不同族；CD4<50 一类宿主风险陈述按公约 3 排除在索引诊断之外。这两条与门闸现行行为一致。）

二是**光杆名词短语**（"The presence of a burrow"、"Miescher radial microgranulomas"）：本轮标注者按公约 8 判 0，而 11 例内那批标注者倾向判 1——两把尺子在这里**互相矛盾**。这是灰区，不是空洞，追它只会追到标注者的偏好上。

### 18.6 回归

| 检查 | 结果 |
|---|---|
| 门闸自测标本 | 39/39 |
| 机制题 | 9/9 PASS |
| 11 例排名（B1+S6+quote_gate） | top1=2/11、top3=7/11、MRR **0.430**（C1 为 2/11、0.415） |
| 74 号例留出普查 `all_225` | acc 0.929 / macroF1 0.820 |
| 同 `diagnostic_91` | acc 0.934 / macroF1 0.904 |
| 同 `required_57` | acc 0.965 / macroF1 0.947 |

全部不变或改善。

### 18.7 到 800 例还差什么

四方法（0）与检索（本地免费，37 例已跑完，12,980 条 passage）都不再是成本。唯一的成本是抽取：观察到 ~345 条 passage/例、1 次 LLM 调用/passage，789 例约 **27 万次调用**（llama-3.3-70b）。按本轮实测吞吐约 17 小时。这是一个可执行但需要明确授权的量级——而 18.4 已经说明，判断「规则是否构式级」并不需要跑到 800。

**但当前规则集确实还欠一次干净测量**（§18.4.1）。代价很小：37 例里另外 31 例的检索已就绪，抽取约 1.1 万次调用、半小时，切一批新的盲测行即可。要让这次测量真正有意义，还需同时解掉「尺子不独立」那一层——至少换一位标注者独立复核，或对特异度陈述那一族做双标注，否则拿到的仍是同一把尺子的读数。

### 18.8 本节产物

| 文件 | 内容 |
|---|---|
| `build_trial_tasks_pool.py` | 11 例外的任务构建；`--from-traces` 直接读四方法 trace，覆盖全部 789 例 |
| `trial_tasks_pool6.json` / `pool37.json` / `all789.json` | 6 / 37 / 789 例任务 |
| `trial_retrieval_pool6k30all4.json` / `pool37k30all4.json` | 对应检索（2,072 / 12,980 条 passage） |
| `trial_tasks_repro74.json` / `trial_retrieval_repro74.json` | §18.2 检索可复现性核验：74 号例本环境重跑 |
| `trial_extraction_pool6k30all4clean_groups.json` | 6 例抽取产物 |
| `prep_pool_annotation.py` | 从任意抽取臂切诊断槽标注批，门闸判定另存私钥 |
| `mix_control_rows.py` | 混入已知答案的控制行，令交付自带质检 |
| `score_pool_annotation.py` | 先算标注者质量，再算门闸样本外一致率 |
| `relation_verifier/batch_pool6_mixed.tsv` / `_key.json` / `labels_pool6_mixed.tsv` | 230 行盲测批、私钥、标注结果 |
| `relation_verifier/pool6_gate_audit.json` | §18.4 的分槽一致率与混淆表 |

---

## 19 标签变好之后，top-1 还错在哪；以及刚性化值不值

§18 说明门闸的逻辑标签质量已经不低。那就该问两件事：**残余的 top-1 错误里还有多少是逻辑标签的锅**，以及**层一/层二当年为标签不可靠而设的辖域限制，现在能不能放开**。两件事的答案是同一个，而且都不在预期方向上。

### 19.1 残余错误：9 例全部由层三决定

C1 栈（B1+S6+F7）当前 top-1 **2/11**（119、74）。九个错例与金标名次：

| 例 | 金标名次 | 赢家 | 赢家分 / 金标分 |
|---|---|---|---|
| 522 | 2 | Vitamin B12 deficiency | 66.3 / 22.2 |
| 773 | 2 | Eisenmenger Syndrome | 22.4 / 19.3 |
| 326 | 3 | Epidural abscess | 23.1 / 16.1 |
| 475 | 3 | Anterior Interosseous Nerve Syndrome | 31.5 / 3.9 |
| 49 | 3 | Cecal diverticulitis | 34.6 / 16.2 |
| 257 | 5 | Septic Arthritis | 23.0 / 2.9 |
| 91 | 5 | Cavernous Angioma | 5.9 / 0.6 |
| 56 | 6 | Leiomyosarcoma | 29.4 / 8.9 |
| 179 | 6 | Pulmonary Atresia with VSD | 24.3 / 8.1 |

**九个赢家没有一个是靠层一或层二赢的。** 全集 174 个候选上层一共淘汰 13 次（`exclusion_triggered` 5、`required_but_absent` 4、`criterion_group_violated` 3、`threshold_violated` 1），其中 12 次打在既非金标也非赢家的候选上，1 次打在 773 的金标上；层二全集只确认 **2 次**（119 金标 1 次、另一候选 1 次）。九个错例的排序，是层三把 `feature_of` 逐条加出来的结果。

### 19.2 按三分法归因

用户要求把「真必要被违反却没否决 / 假充分直接确诊」与「380 ms 没跟 440 比出来」这类执行问题分开计数，再单列主语错挂一类。逐例核完（`top1_error_audit.json`、`rigid_headroom_audit.json`）：

| 归因 | 例数 | 依据 |
|---|---|---|
| **逻辑标签错致漏否决**（真必要违反未否决） | **0** | 九个赢家身上**接合的**高权断言总数为 0，没有一条真必要可被违反 |
| **逻辑标签错致误确诊**（假充分直接确诊） | **0** | 层二全集只开火 2 次，均非错例赢家 |
| **逻辑执行错**（切点/单位比不出来） | **0** | 九个错例里没有一次 `threshold_ok` 求值发生在赢家或金标身上 |
| **必要条件存在但从未接合** | **9/9 例可见** | 赢家侧 `required_for` 接合 1 条、**未接合 16 条** |
| **主语错挂等非逻辑** | 至少 1（475） | AIN 的 31.5 分由「做 OK 手势」等谓语堆出，源出腕骨骨折文（E1/E6），层三消费 |

也就是说：**在当前接合率下，逻辑标签的对错对 top-1 几乎不产生因果影响**。§16–18 那些门闸改进能把标签一致率从 0.6 抬到 0.9，却一分 top-1 都没换来，原因就在这里——被修正的那些断言根本走不到会改变排序的位置。

**未接合的必要条件是什么样子。** 赢家侧 16 条里抽查三例，几乎全是检查/程序或元标准谓语：

| 例 | 赢家 | 未接合的 `required_for` 谓语 |
|---|---|---|
| 49 | Cecal diverticulitis | colonoscopy（obligatory）、colonoscopic evidence、radiological evidence、imaging of the morphological substrate（obligatory）等 7 条 |
| 522 | Vitamin B12 deficiency | at least 1 common risk factor（obligatory）、at least 1 common symptom or sign（obligatory） |
| 56 | Leiomyosarcoma | morphological diagnosis（obligatory）、image-guided core needle biopsy（obligatory） |

这些是漏网的**假必要**（「必须做结肠镜」不是诊断必要条件），门闸该降而没降。它们今天无害，纯粹因为「结肠镜」接不到任何病例发现——这一点在 19.3 会变成陷阱。

### 19.3 刚性化：三个限制是空操作，第四个有害

把层一/层二的辖域限制逐条放开（`run_mechanical_engine.py` 的四个 `RIGID_*` 开关，默认全关；脚本 `sweep_rigidity.py`）：

| 变体 | top1 | top3 | MRR | 误杀金标 | 层一淘汰 | 层二确认 |
|---|---|---|---|---|---|---|
| V0 现状 | 2 | 7 | 0.430 | 1 | 13 | 2 |
| V1 `required_for` 不再要求 obligatory | 2 | 7 | 0.430 | 1 | 14 | 2 |
| V2 `sufficient_for` 满足即确诊 | 2 | 7 | **0.430** | 1 | 13 | **2** |
| V3 `pathognomonic_for` 读切点 | 2 | 7 | 0.430 | 1 | 13 | 2 |
| V4 必要条件未接合即视为缺失（封闭世界） | 2 | **6** | **0.415** | **3** | 35 | 2 |
| V5 四者全开 | **1** | 6 | **0.355** | **4** | 43 | 2 |

逐条读：

- **V1 的外延是 1 条。** modality 限制在全集上只压住了一次淘汰，指标全同。而这条限制并非无意义：326 金标 Brucellosis 身上有 2 条接合的 `required_for`，正是靠 modality 挡着才没被否决——放开它在别处不赚，在这里要赔。
- **V2 的外延是 0。** 全集没有任何一条 `sufficient_for` 接到 present 发现。「`sufficient_for` 降为层三」这条被认为奇怪的设计，实际上是一条**空规则**：改不改，引擎行为逐位相同。
- **V3 的外延是 0。** 层二只开火 2 次，两次的切点都不是 `False`。
- **V4 是真正有外延的那个，也是有害的那个。** 淘汰 13→35，但误杀金标 1→3（新增 522、56），top3 和 MRR 双降。原因就是 19.2 那批假必要：封闭世界把「病历没写做过结肠镜」读成「结肠镜缺失」，于是候选因为**没做某项检查**而被否决。它确实否决了一些错误赢家，但理由是伪的，而且同一机制会以同样的伪理由否决金标。
- **V5 最差**，连 74 的金标都被杀掉，top1 跌到 1、MRR 跌到 0.355。

**结论：那些「看起来奇怪且复杂」的辖域限制，不是当前性能的瓶颈。** 其中三条在这份数据上是空操作或近乎空操作，放开不改变任何东西；唯一有外延的那条放开就赔。把它们简化或刚性化是可以的，但要以「代码更清楚」为理由，不能指望换来 top-1——本节已经把这个指望证伪了。

### 19.4 杠杆在层三的求和，不在层一的刚性

真正决定九个错例的，是层三把 `feature_of` 逐条相加。全集 174 个候选上：

- `r(score, n_joined) = 0.559`，`r(score, n_assertions) = 0.549`；
- 九个错例中，**赢家的接合行数 9/9 全部多于金标**（均值 40.4 对 29.3）。

这正是用户提出的那个机制：检索到资料更多的候选，靠海量冗余重复的弱规则堆出高分。49 号例的赢家得分前三位是「C 反应蛋白检查」「腹盆 CT」「全血计数」——三条都是检查提及，不是鉴别性发现；475 的赢家靠一批挂错主语的谓语拿到 31.5 分。

因此可动的地方有三处，都在层三及其上游，与层一刚性无关：

1. **归一化**：score 对接合行数的依赖需要打断。〔**更正（§20.3）**：此处原写「当前 §11 的 specificity 方案默认 `none`，即恒为 1」，是错的。C1 栈继承 B1 的 `weight: idf`，`WEIGHT_SCHEME` 实为 `idf`，共享发现的折扣一直开着。真正的漏洞不在这里，见 §20.3。〕
2. **检查提及不该计分**：`required_for` 里的程序谓语已被门闸盯上，但同样一批词进 `feature_of` 就无人管，而层三才是它们真正生效的地方。
3. **主语错挂**（475 类）在层三按体量放大，门闸只看 quote 授权关系，管不到主语是否属于本病。

### 19.5 本节产物

| 文件 | 内容 |
|---|---|
| `audit_top1_errors.py` / `top1_error_audit.json` | 逐例 top-1 残余错误、赢家与金标的驱动项与淘汰理由 |
| `audit_rigid_headroom.py` / `rigid_headroom_audit.json` | 高权断言按「刚性读法会做什么」分类；bound 但未接合的分槽计数 |
| `sweep_rigidity.py` / `rigidity_sweep.json` | V0–V5 刚性化变体的 top1/top3/MRR/误杀金标 |
| `run_mechanical_engine.py` 的 `RIGID_*` 开关 | 四条辖域限制的可开关实现，**默认全关**，既有结果逐位不变（39 标本、机制 9/9、MRR 0.430） |

## 20 尺子变准之后重审抽取缺陷：审计对象必须换，换了之后三条修法全部失败

§14.3.6（E1–E11，475 例）、§14.4（E12–E14 十例；其下子节的假必要 A–F 与真必要错槽 G1–G3）是先前的手动归类，冻结在 `case475_extraction_defect_census.json`、`case_extraction_defect_census_10.json`、`case74_relation_error_census.json`，修法映射在 §15.2。本节重做这件事。结论有两层：**类别分布确实大变，也确实出现了新类；但真正的发现是旧普查的审计对象已经几乎不起作用了**，而按新对象找出的三条修法，逐条实测全部失败。

### 20.1 旧普查审的那个 population，如今占实际起作用行数的 1%

`dump_engine_consumed.py` 把金标与「击败金标的那个候选」名下、过闸之后的全部断言连同它们在引擎里的命运摄出（`engine_consumed_rows.json`），11 例共 4,368 条：

| | 条数 |
|---|---:|
| 真正影响得分（活跃） | **538** |
| 其中 `feature_of` | **486** |
| 其中高权槽合计 | **6** |
| 惰性（未接合 / 软语境 / 极性不参与） | 3,830 |

原因在数据里：门闸把绑定到这两个候选的 **329 条高权断言降级成了 `feature_of`**（`excludes` 183、`required_for` 111、`sufficient_for` 22、`pathognomonic_for` 13），高权槽只剩 47 条站着、其中 6 条活跃。§14 逐条核的 `required_for`/`pathognomonic_for`，如今是引擎行为里可以忽略的那一部分。

因此重审批（260 行，`prep_defect_reaudit.py`）按引擎实际消费的比例抽样，并加了**第二个标注轴**：除旧的「七元组相对引语是否忠实」（E 轴），另判「就算忠实，这行对这个病有没有鉴别力」。§14 没有这一轴，而 §19 已证明它才是决定排名的那一轴。

### 20.2 分布：忠实不等于有用，两者几乎正交

260 行的结果（`labels_defect_reaudit.tsv`、`defect_reaudit_summary.json`）：

| | useful=1 | useful=0 | 合计 |
|---|---:|---:|---:|
| defect=OK | 79 | **83** | 162 |
| defect≠OK | 15 | 83 | 98 |

**`OK` 率 62.3%，但只有 36.2% 有鉴别力；忠实的行里过半（83/162）对鉴别毫无帮助。** 这 83 行是完全合法的抽取，内容却是该病例每个候选都会声称的表现（疼痛、肿胀、发热、虚弱），或治疗、预后、同义词、检查名称。**任何只读 quote 的门闸都抓不到它们**——门闸的判据是「元组是否忠于引语」，而这里元组是忠实的。

E 轴的分布相对 §14 大变：`required_for` 的假必要曾是 74 例 57 条中 42 条（73.7%），如今高权槽在活跃集里只剩 6 行。占据主位的是 **E11 忠实离题 23 行**与 **E12 循环定义 / 检查当特征 21 行**，其次 E7 空规则 14 行、E13 论元对调 8 行。E6、E10 零实例。

**两个新类**（审计员开出，均不能并进 E1–E14）：

| 新码 | n | 定义 | 为何不并类 |
|---|---:|---|---|
| `NEW:predicate_truncated` | 8 | 谓语只抄了引语的一部分，丢掉的恰是使它可判定或锚定指称的成分 | E14 要求元组里*出现*引语所无的数字；这里方向相反——引语原有的阈值被抽取器**丢掉**了。E7 归咎于来源，而这些行的引语恰恰给出了精确标准 |
| `NEW:prognostic_as_diagnostic` | 3 | 引语讲的是预后 / 严重度分层 / 风险，元组改写成诊断特征或病因 | E7 要求谓语不可执行，但「起病年龄 <30 岁」完全可判定；坏的是它在引语里的**角色**。E4 只覆盖高权槽，这三行都在 `feature_of` |

`NEW:predicate_truncated` 的存在价值有一个直接证据：同一句滑膜液标准在表里出现四次，三次保留了「WBC >50,000」（判 useful=1），一次被砍成裸指标「synovial fluid WBC count」（useful=0）——同一句引语因截断与否落在 useful 的两侧。

`caused_by` 有自己独有的失效模式：**E13 的 8 行里 7 行在这里**，全部是把并发症/转归写成病因（阑尾炎 `caused_by` 腹膜炎、CPVT `caused_by` 心源性猝死），互换主谓即与引语相符。这条因果箭头的系统性倒置只在 `caused_by` 出现，而层三对 relation 不做任何筛选，`caused_by` 与 `feature_of` 同权计分。

### 20.3 三条修法，逐条实测失败

§19.4 提的三处杠杆，加上本节新发现的一处，全部做成默认关闭的开关后实测：

| 修法 | 依据 | top1 | top3 | MRR |
|---|---|---:|---:|---:|
| 现状 C1 | — | 2 | 7 | 0.430 |
| **F9** 门闸判定「非诊断判据」者不计分 | 降级即赦免（下） | 2 | 7 | 0.430 |
| **F10** 每个发现按 `n^beta` 衰减重复计票（beta=0.25） | 68% 是重复投票（下） | 2 | 6 | 0.423 |
| F10 beta=0.5 / 0.75 / 1.0 | 同上 | 2 | 6 | 0.418 / 0.418 / 0.417 |
| oracle：删掉临床医师判为无鉴别力的行（双向） | 上表 166 行 | **1** | 6 | **0.347** |

**（1）降级即赦免。** 层三对 relation 不做筛选，所以门闸的降级不是惩罚：`Porokeratosis feature_of "biopsy"`（`_gate=E4_procedure_not_finding`）接合到患者的「skin biopsy present」照样加分——门闸判定「biopsy 是操作不是判据」，这个判断是对的，却因为降级目标 `feature_of` 本身是计分槽而被丢弃。E10 降级到 `treated_by` 同理。此类**降级后仍在计分**的行 39 条（活跃行 7.2%，赢家 23 / 金标 16）。F9 让判定生效为「不计分」，**指标零变化**。为排除开关空转，把匹配放宽到命中所有门闸标记做探针，指标会动（top1 2→1、MRR 0.430→0.392），故此零为真。

**（2）idf 折扣一直开着，漏的是另一件事。** 更正 §19.4：C1 的 `WEIGHT_SCHEME` 是 `idf` 不是 `none`。但 idf 按「多少个**候选**声称该发现」打折，完全不管「同一候选有多少条断言接到**同一个**发现」。实测（`check_claimants_vs_useful.py`）：`useful=0` 的平均 claimant 数 6.51、`useful=1` 为 5.46，方向对但分离极弱。真正的漏洞是重复计票——538 条活跃行只对应 **172 个不同的 (候选, 发现) 对，冗余度 3.13×，68% 的计分行是对已计过的对的重复投票**：

| 重复次数 | 例 | 候选 | 发现 |
|---:|---|---|---|
| ×17 | 56 | Leiomyosarcoma | atypical spindle cells |
| ×16 | 49 | Cecal diverticulitis（赢家） | right iliac fossa pain |
| ×15 | 773 | Eisenmenger Syndrome | widened pulmonary arteries |
| ×9 | 49 | Appendiceal stump appendicitis（**金标**） | right iliac fossa pain |

49 号例最直白：同一个病人、同一个发现，赢家计 16 次、金标计 9 次，排序由「哪个候选被更多指南句子提到」决定。冗余度金标 2.67× 而赢家 3.76×，看起来对金标有利。**但 F10 在每一档 beta 都更差**（top3 7→6，MRR 单调下降至 0.417）：金标同样靠重复得分，压制重复对它的伤害不小于对赢家。

**（3）完美的鉴别力判别器也救不了。** 前两条失败的共同点是「无差别削减体量」，而审计的不对称在于**哪些行无用**（赢家 72.7% 对金标 56.1%，聚类自助 95% CI [+0.024, +0.328]，不跨零）。于是用审计标签当 oracle 测上界。系统级 oracle 有混杂——审计只覆盖金标与赢家，删除会让未审计的其他候选白占便宜——所以只看**头对头**（`oracle_useful_ceiling.py`）：

| 例 | 金标 → oracle 后 | 赢家 → oracle 后 |
|---|---|---|
| 475 | 3.9 → **0.0** | 31.5 → 30.3 |
| 91 | 0.6 → **0.0** | 5.9 → 3.3 |
| 179 | 8.1 → 1.7 | 24.3 → 16.0 |
| 522 | 22.2 → 19.0 | 66.3 → 58.0 |
| 49 | 16.2 → 14.5 | 34.6 → 27.8 |

**在完美的临床 oracle 双向删除后，金标仍然 10/11 输给击败它的候选，一次翻转都没有。** 更尖锐的是份额：金标平均 **38.6%** 的分来自被判无鉴别力的行，赢家只有 **21.1%**（审计覆盖金标 52.1%、赢家 44.6%，这点差距不足以解释这个缺口）。475 和 91 两例金标分**归零**——金标的全部得分都来自临床医师认为不能鉴别的行。

### 20.4 这改变了问题的性质

§19 的结论是「层一刚性不是瓶颈，杠杆在层三」。本节把层三这个杠杆也证伪了：归一化、非判据过滤、乃至完美的鉴别力 oracle，三条路都不通，原因是同一个——**金标当前也是靠无效证据得分的，对称地清理垃圾不改变次序**。2/11 的 top-1 不是「大体正确、差在打磨」，而是连对的那两例也未必是因为对的理由。

所以下一步不在打分层，而在**金标一侧的证据召回**：让关于正确诊断的鉴别性陈述先进入断言集。审计已经指出几条具体的、当前完全不可见的损失来源：

- **接合层错配**，两列都记录不到，且可以 `defect=OK`+`useful=1` 却彻底污染排序。审计点名：布鲁氏菌病同义词「Malta fever」匹配到患者的「high fever」；「lorazepam challenge test」匹配到「HIV tests」；最刺眼的是 475——谓语「**仍能**做出 OK 手势」匹配上患者「**无法**做出 OK 手势」，极性在**匹配环节**被反转后为该候选加了分。这是纯字符串重叠，任何只看元组与引语的审计都抓不到。
- **`NEW:predicate_truncated`**：阈值在抽取环节被砍掉，使可判定标准退化为裸指标名。这是召回损失，不是过声称。
- **候选标签过泛**：56 号例候选是裸 `Carcinoma`、179 是裸 `Thrombocytopenia`，绑进来的全是亚型专属规则。这两例的 OK 率（35%、29%）与 useful 率（23%、12%）都是全表最低，但病根在候选生成端。

需要说明的方法学限制：审计批只覆盖金标与赢家两个候选的活跃行，因此系统级 oracle 探针不可解释，只有头对头可用；要把 oracle 上界做成系统级结论，需要把全部候选的活跃行纳入审计。

### 20.5 本节产物

| 文件 | 内容 |
|---|---|
| `dump_engine_consumed.py` / `engine_consumed_rows.json` | 金标与赢家名下过闸断言 4,368 条，含引擎命运（层一/层二/层三/惰性）与门闸标记 |
| `prep_defect_reaudit.py` / `batch_defect_reaudit.tsv` | 按引擎消费比例分层抽样的 260 行双轴审计批 |
| `score_defect_reaudit.py` / `defect_reaudit_summary.json` | E 轴与 useful 轴分布、交叉表、按槽位与角色的缺陷率 |
| `check_claimants_vs_useful.py` / `claimants_vs_useful.json` | idf 折扣与人工 useful 标签的分离度检验 |
| `sweep_noncriterion.py` / `noncriterion_sweep.json` | F9 及其空转探针 |
| `sweep_pooling.py` / `pooling_sweep.json` | F10 的 beta=0/0.25/0.5/0.75/1.0 扫描 |
| `oracle_useful_ceiling.py` / `oracle_useful_ceiling.json` | 鉴别力 oracle 的系统级与头对头上界 |
| `run_mechanical_engine.py` 的 `NONCRITERION_INERT` / `FINDING_POOL_BETA` / `LAYER3_DROP` | 三个开关，**默认全关**，既有结果逐位不变（门闸 39 标本、top1 2、top3 7、MRR 0.430） |

## 21 刚性天花板：把 40 条真授权高权规则按一票制正确执行，能答对几例

§18.4.2 手审确认门闸只错降了 12 条，其中真缺陷 3 条。那就该问一个更彻底的问题：**假设这 40 条被标注确认为真授权的高权关系全部被正确提取、findings 完全正确提取与绑定、并按最高优先级一票制执行（pathognomonic/sufficient 命中即确诊，required 被违反即否决），能答对几例。** 这是刚性层的天花板，与层三无关。

对象是 pool6 的 6 例（这 40 条正是 §18.4.2 表中 27+8+5 的那批）。脚本 `oracle_rigid_ceiling.py`，产物 `rigid_ceiling_binding.json`。

### 21.1 先看这 40 条是不是在讲对的病

| 例 | 金标 | 金标在候选集？ | 落在金标 | 落在对手 | 绑不上任何候选 |
|---|---|---|---:|---:|---:|
| 100 | Telangiectatic metastatic breast carcinoma | 是（`Cutaneous metastasis of breast carcinoma`） | 0 | 0 | 3 |
| 114 | Ependymoma | **否** | 0 | 4 | 1 |
| 133 | ProstateStromalSarcoma | 是（`Prostatic Stromal Sarcoma`） | 0 | 0 | 1 |
| 261 | Cutaneous malakoplakia | 是 | **2** | 6 | 3 |
| 291 | Necrolytic acral erythema | **否** | 0 | 0 | 2 |
| 529 | Multidrug-resistant CMV infection | 是 | **4** | 10 | 4 |
| **合计** | | **4/6** | **6** | **22** | **14** |

**40 条里只有 6 条落在金标身上（15%）**，22 条落在对手、14 条连候选集都绑不上。刚性层能否赢，先取决于检索与抽取有没有把**关于正确那个病**的高权规则带回来，而在 6 例里它只对 2 例做到了。

（须声明一处口径修正：任务文件的 `gold_match` 是按别名精确匹配打的，系统性地把**泛化标签**标成金标、把**真正正确的具体标签**标成非金标——261 标的是裸 `Malakoplakia` 而非 `Cutaneous Malakoplakia`，133 标的是裸 `Sarcoma` 而非 `Prostatic Stromal Sarcoma`。这正是 §20.4 记的候选标签过泛问题。上表按人工裁定，不按 `gold_match`。）

### 21.2 逐例执行：2/6

按一票制、findings 取自 vignette 原文：

| 例 | 刚性层会不会开火 | 结果 |
|---|---|---|
| **261** | `Michaelis-Gutmann bodies` **pathognomonic_for** Cutaneous Malakoplakia；病历原文「Intracytoplasmic **Michaelis-Gutmann bodies present**」 | **确诊金标，对** |
| **529** | `PCR` **sufficient_for** CMV infection（引语「Diagnosis of CMV infection is generally established with PCR」）；病历有连续 CMV 病毒载量 63→3171 IU/mL | **确诊金标，对** |
| 100 | 该例 3 条真授权全部关于 ATLL / Hydrocele，均绑不上任何候选 | 不开火，无票 |
| 133 | 唯一 1 条关于 solitary fibrous tumor，非本例候选 | 不开火，无票 |
| 291 | 2 条关于甲旁亢 / 嗜铬细胞瘤，非本例候选；且金标不在候选集 | 不开火，无票 |
| 114 | 4 条落在对手（Dermoid cyst「hair protruding from punctum」×3、Coccygeal teratoma「multiple fat-fluid levels」）；病历明写「no visible pilonidal pits」，均不存在 | 不开火；金标本就不在候选集 |

**答案：2/6。** 另需注意 529 那一票的性质：它确诊的是「CMV 感染」，而本例选项要区分的是**多重耐药** CMV 与更昔洛韦耐药 CMV，真正的判据是 UL97/UL54 突变。这一票之所以记对，是因为别名匹配把泛化的 CMV 标签当成了金标；刚性规则并没有回答题目实际在问的那个区分。

### 21.3 相对当前引擎的增量：0

当前 C1 引擎在同样 6 例上：

| | 100 | 114 | 133 | 261 | 291 | 529 | top-1 |
|---|---|---|---|---|---|---|---|
| C1 的 top-1 | Angiosarcoma | Dermoid cyst | Phyllodes Tumor | **Cutaneous Malakoplakia** | Lichen planus | **CMV infection** | 按任务标注 1/6、**按人工裁定 2/6** |
| 刚性 oracle | 无票 | 无票 | 无票 | **确诊对** | 无票 | **确诊对** | **2/6** |

**增量为 0。** 刚性层答对的那两例，层三靠体量求和已经排在第一位了；层三答错的那四例，刚性层一票也投不出来。

### 21.4 为什么不能带来提升：三个互不相同的原因

失败的四例各有各的原因，都不在「规则语义执行」这一层：

1. **候选集里没有金标（291、114）。** Necrolytic acral erythema 与 Ependymoma 根本不在候选表中（114 的候选全是囊肿/畸胎瘤/脓肿）。任何基于候选的推理都不可能答对，**病根在四方法的候选生成**，比规则抽取更靠上游。
2. **规则讲的是别的病（100、133）。** 这两例金标在候选集里，但该例全部真授权高权规则关于的疾病压根不是候选——100 的 3 条讲 ATLL 和鞘膜积液，133 的 1 条讲孤立性纤维性肿瘤。刚性层无票可投。**病根在检索：焦点检索把关于其他病的段落送了进来，却没带回关于正确诊断的判据性陈述。** 这与 §20.4 的结论一致——瓶颈在金标一侧的证据召回。
3. **答对的那两例并不需要刚性层（261、529）。** 规则确实正确开火，但层三已经给出同样的答案。刚性层在这里是冗余的确认，不是新增能力。

还有一个贯穿性的量级问题：**85% 的正确高权规则（34/40）是关于非金标的疾病的**。即便把提取与执行都做到完美，这个比例决定了刚性层大部分时候要么沉默、要么替对手说话——114 例那 4 条落在 Dermoid cyst / Coccygeal teratoma 上的真 pathognomonic 就是后者的样本，只是因为病历里那些体征恰好不存在才没有酿成错误确诊。

### 21.5 本节产物

| 文件 | 内容 |
|---|---|
| `oracle_rigid_ceiling.py` / `rigid_ceiling_binding.json` | 40 条真授权高权规则按例绑定到金标 / 对手 / 无候选的分槽结果与原文 |

## 22 复合判据去哪了：指南写成「四条中的两条」，引擎却只会加权求和

指南把刚性判据写成**组合**——「以下四条中满足三条」「A 且 B」「符合全部下列条件」——这类复合命题在临床上具有与单命题同等的刚性。但本引擎除单命题刚性外，其余一律进入层三加权求和。这个反常现象来自语料、抽取、还是引擎？三处都查了，**语料没有问题，另外两处各有一份责任**。脚本 `audit_compound_criteria.py`、`audit_criteria_fidelity.py`，产物 `compound_criteria_audit.json`、`criteria_fidelity_audit.json`。

### 22.1 语料：不是原因

9,928 条去重段落里：

| 复合判据语言 | 段落数 | 占比 |
|---|---:|---:|
| 任一形式 | 1,511 | **15.2%** |
| `criteri(on\|a)` | 592 | 6.0% |
| in addition to / together with / accompanied by | 551 | 5.5% |
| and/or | 391 | 3.9% |
| 「N of the following」 | 86 | 0.9% |
| 「all of the following」 | 6 | 0.1% |

其中**自身明确枚举出一个判据集**的段落有 155 条，按句子自述的 logic 分：`at_least_n` 80、`all` 49、`any` 26。指南是按正常方式写判据的，显式枚举式占比不高（约 1.6%）但确实存在且结构清晰。

### 22.2 抽取：主要责任，且是两种不同的失败

把这 155 条判据段落与从中抽出的断言对接（引语为段落子串），共 2,372 条：

| 抽取器给出的 logic | n | 占比 |
|---|---:|---:|
| 无 `criterion_group` | 2,037 | 85.9% |
| `any` | 230 | 9.7% |
| `at_least_n` | 58 | 2.4% |
| `all` | 38 | 1.6% |

**句子自述的 logic 与抽取器给出的 logic 一致率 6.3%（149/2,372）。** 错配方向集中：`at_least_n`→无组 1,061、`all`→无组 740、`at_least_n`→`any` 82、`all`→`any` 71、`at_least_n`→`all` 24。

（口径说明：85.9% 这个数偏高，因为一条判据段落里也有与判据集无关的句子，其断言本就不该成组。所以下面用逐例核对补一刀。）

**失败一：判据成员根本没被抽出来。** 逐条核对三个段落的成员词在全部 53,071 条断言里的出现次数：

| 段落自述 | 成员 | 全库断言数 |
|---|---|---:|
| 语义性痴呆「three of the following four phenomena **must be present**」 | impaired object knowledge / surface dyslexia / dysgraphia / spared repetition | **0 / 0 / 0 / 0** |
| 血管性痴呆「dementia **and two or more of the following**」 | focal neurologic signs / stepwise / abrupt | **0** / 1 / 18 |
| 路易体痴呆「requiring **2 of 3 of the following**」 | parkinsonian / fluctuation / hallucination | 18 / 16 / 118 |

语义性痴呆那四条成员在全库一次都没出现——那一句明写 must be present 的刚性判据集，抽取产出为零。而同一段落抽出来的是 `feature_of degenerative cerebral atrophy`、`variant_of dementia`、`feature_of postural instability`：**抽取器绕开了判据集本身，去捡了段落里其他位置的零散名词。** 血管性痴呆同理。路易体痴呆的三个成员倒是抽到了，说明抽取器**有能力**做这件事，只是不稳定。

**失败二：成组时把 logic 塌成 `any`。** 全量抽取的组 logic 分布：

| | 11 例 | pool6 |
|---|---|---|
| 断言总数 | 34,353 | 18,725 |
| 带 `criterion_group` | 2,318（6.75%） | 1,138（6.08%） |
| `any` | 1,594（69%） | 954（**84%**） |
| `all` | 648（28%） | 184（16%） |
| `at_least_n` | **76（3.3%）** | **0** |

`at_least_n` 正是临床上最典型的刚性构式，在 11 例里只占 3.3%，在 pool6 里**一条都没有**。而 `any` 占了七到八成——下一节说明，`any` 是引擎里唯一永远不可能刚性的那个 logic。

### 22.3 引擎：第三份独立责任，而且更根本

即便组被正确抽出，引擎的执行语义本身也拦着它（`run_mechanical_engine.py` 的组处理段）：

| logic | 能否刚性淘汰 | 能否刚性确诊 |
|---|---|---|
| `all` | 仅当组内有成员是 `required_for`+`obligatory`，或 F4b 强制 | **否** |
| `at_least_n` | **否** | **否** |
| `any` | **否** | **否** |

`any` 与 `at_least_n` 没有任何刚性通路，只产生一个加权 delta。更关键的是**没有任何组可以确诊**：一个被完全满足的判据集拿到的是 `delta = w × spec × 1.0`，与一条普通强特征同量级，随后照样在层三与体量竞争。「满足了 4 条中的 3 条」与「有一条 feature_of」在打分上没有量级差别。

11 例实测（174 个候选）：

| 组的去向 | n |
|---|---:|
| 只产生层三加权 delta | **124**（`any` 82、`all` 39、`at_least_n` 3） |
| 走到刚性淘汰 `criterion_group_violated` | **3** |
| 走到刚性确诊 | **0**（引擎不存在这条通路） |

### 22.4 结论与归因

用户指出的反常是真的，但它不是一个原因造成的，而是三个独立环节叠加，语料不在其中：

1. **语料无责。** 15.2% 的段落含复合判据语言，155 条明确枚举判据集，写法正常。
2. **抽取责任最大，且分两种。** 一是判据集成员经常整组抽不出来（语义性痴呆四条成员全库为 0），抽取器转而捡段落里无关的零散名词；二是成组时 logic 塌向 `any`（`at_least_n` 在 pool6 为 0），对判据段落的 logic 保真率只有 6.3%。
3. **引擎语义有独立缺口，且是最根本的一个。** 即使前两步都做对，`any`/`at_least_n` 仍无刚性通路，且**任何组都无法确诊**。这意味着「修好抽取」并不足以让复合判据发挥刚性作用——引擎侧必须先补上「判据集满足即确诊」这条通路，否则修好的组只会变成层三里又一个加权项，重蹈 §20.3 的覆辙。

顺序上，引擎侧的缺口应当先补，因为它可以独立验证（现成的 124 个组里，`all` 39 个与 `at_least_n` 3 个已经在被满足/违反地求值，只是结果被降格成 delta），而抽取侧的召回改造成本远高且收益依赖于引擎先能消费它。

### 22.5 本节产物

| 文件 | 内容 |
|---|---|
| `audit_compound_criteria.py` / `compound_criteria_audit.json` | 语料段落的复合判据语言分布；两份抽取的 `criterion_group` logic 与组大小分布 |
| `audit_criteria_fidelity.py` / `criteria_fidelity_audit.json` | 155 条判据段落与其抽出断言的 logic 对接、保真率与错配混淆表 |

## 23 三种 logic 够不够用、失真有多大、判据集在原文里是什么身份

§22 用的是 `stated_logic()` 这把尺子去挑判据段落，而这把尺子只认 `all`/`any`/`at_least_n` 三种写法——用它来回答「文本里还有没有第三种以外的结构」是循环论证。本节改用不提及三种 logic 的独立检测器扫全部 9,928 条段落，并把「文本自述的判据集效力」与「抽取器给出的 relation」逐段落配对。

### 23.1 三种 logic 不足以概括原文的逻辑连接

全语料扫描（检测器与三种 logic 无关）：

| 结构 | 段落数 | 占语料 | 其中被三种 logic 检出的 |
|---|---:|---:|---:|
| `negated_conjunct`（成员必须**不存在**：in the absence of / after excluding / not attributable to） | 223 | 2.2% | 2 |
| `durational`（整组附带时长门槛：lasting at least 6 months） | 81 | 0.8% | 4 |
| `scored_threshold`（**计分制**：Beighton score ≥ 5 points out of 9） | 43 | 0.4% | 3 |
| `gated_by_context`（判据集只在某类患者中适用） | 43 | 0.4% | 1 |
| `sequenced`（次序有意义：followed by ... confirm） | 29 | 0.3% | 1 |
| `two_tier`（**major/minor、core/suggestive 两层**） | 23 | 0.2% | 1 |
| `graded_certainty`（输出是 definite/probable/possible **三值**而非二值） | 19 | 0.2% | 2 |
| `exclusive_or`（either ... or） | 573 | 5.8% | 20 |

需要区分噪声与真缺口。`exclusive_or` 的 573 条绝大多数是散文里的普通「或」，可以归约为 `any`，不算新结构。真正无法用三种 logic 表达的是后四类：

- **计分制（43）**：`Beighton score: ≥ 5 points out of 9`、`ECOG score of 2 or more`。这是带权重的求和加阈值，`at_least_n` 只能数个数、不能给成员配权。
- **两层（23）**：见 23.2。
- **三值输出（19）**：`a combination of core diagnostic features and suggestive diagnostic features for either probable or possible neurocognitive disorder with Lewy bodies`。同一批成员按不同计数门槛给出不同确信度，schema 里没有位置放这个。
- **否定合取（223）**：`possible Alzheimer's disease can be applied in the absence of neurologic, psychiatric disorders`。schema 层面尚可表达（`polarity` 是逐成员的），但**引擎的组求值器读不了**：它把 `sat` 定义为「成员的 `_finding.polarity == present`」，一个靠「缺席」而被满足的否定成员会被算成违反。而且抽取侧实际也没在用——509 个组里只有 **8 个**含否定成员，语料里却有 223 条段落写了否定合取。

### 23.2 二阶组存在，而且 schema 从构造上就装不下

全语料二阶候选 45 条（0.45%），其中 22 条是最典型的两层判据：

| 疾病 | 原文结构 | 三种 logic 能否表达 |
|---|---|---|
| 路易体痴呆 | `probable if 2 core features **or** 1 suggestive feature **with** 1 or more core features` | 否，是 `at_least_n(core,2) ∨ (at_least_n(sugg,1) ∧ at_least_n(core,1))` |
| MCAS | `Major criteria of MC activation symptoms in **2 or more systems plus ≥ 1 minor criteria**` | 否 |
| PHACE | `facial hemangioma > 5 cm **with** one major criterion **or** two minor criteria` | 否 |
| Castleman | `meets **both major** criteria, **at least two of the minor** criteria **and one** laboratory abnormality` | 否，三个组的合取 |
| POEMS | `Mandatory major criteria (2) + Other major criteria (3) + Minor criteria (5)` | 否 |
| pNET 相关糖尿病 | `Major Criteria (**All Must Be Fulfilled**) / Minor Criteria` | 否 |

两件事值得单独指出。第一，**22 条两层段落里只有 1 条被 §22 的判据集检测器认出来**——§22 报的「155 条判据段落」系统性漏掉了整个两层家族，因为「both major criteria」不带 `of`，`N_OF_M` 正则匹配不上。第二，`criterion_group` 的 schema 是 `{group_id, logic, n}` 三个字段，**没有 parent_group、没有 tier、没有组间连接词**，所以即使 LLM 完全读懂了 Castleman 那句话，它也只能把三个组压成一个平面组、或拆成三个互不相干的组。二阶在这套表示下不是「抽得不好」，是**不可表达**。

### 23.3 失真度：TVD 0.617，`any` 被高估 4.7 倍

按段落为单位（文本一段只声明一次 logic，抽取器却逐成员出一行；按行数会让长 `any` 列表压过短 `at_least_n` 列表）：

| 文本声明 | 抽取器产出 | n |
|---|---|---:|
| `at_least_n` | NO_GROUP | 39 |
| `all` | NO_GROUP | 27 |
| `at_least_n` | `any` | 17 |
| `at_least_n` | 未抽到 | 15 |
| `all` | `any` | 14 |
| `any` | NO_GROUP | 10 |
| `any` | `any` | 9 ← 保真 |
| `any` | 未抽到 | 7 |
| `at_least_n` | `at_least_n` | 6 ← 保真 |
| `all` | 未抽到 | 6 |
| `at_least_n` | `all` | 3 |
| `all` | `all` | 2 ← 保真 |

- **段落级 logic 保真率 17/155 = 11.0%**（§22 报的 6.3% 是断言级）。
- **判据段落里只有 32.9% 产出了任何组**，另外 48.4% 抽出了断言但一个组也没成，18.1% 完全没抽到。
- 在产出了组的 51 条上比较分布：

| logic | 文本 | 抽取器 | 比值 |
|---|---:|---:|---:|
| `at_least_n` | 51.6% | 11.8% | **0.23×** |
| `all` | 31.6% | 9.8% | **0.31×** |
| `any` | 16.8% | 78.4% | **4.68×** |

**总变差距离 TVD = 0.617**（0 为一致，1 为不相交）。作为标尺：一个完全无视文本、在三种 logic 上均匀乱猜的抽取器，TVD 只有 0.183。**当前抽取器的 logic 分布比随机猜测离真实分布还远 3.4 倍**——它不是噪声，是系统性地把所有判据集读成 `any`。方向也正是最坏的那个：`any` 恰好是引擎唯一永远不可能刚性的 logic（§22.3）。

### 23.4 原文里判据集是刚性身份，抽取器把它降成 feature_of

文本侧，155 条判据段落自述的效力：

| 文本说这个集合是 | n | 占比 |
|---|---:|---:|
| 充分（establishes / confirms the diagnosis） | 5 | 3.2% |
| 必需（must be present / is required / mandatory） | 33 | 21.3% |
| 只称为 "criteria"，效力未明说 | 33 | 21.3% |
| 仅支持性（supports / suggests / typical） | 54 | 34.8% |
| 无线索 | 30 | 19.4% |

**45.8% 的判据段落在文本里就是刚性身份**（充分 / 必需 / 名为判据）。

抽取侧，全部 3,456 条进组断言的 relation：

| relation | n | 占比 |
|---|---:|---:|
| `feature_of` | 2,780 | **80.4%** |
| `required_for` | 170 | 4.9% |
| `distinguishes_from` | 144 | 4.2% |
| `caused_by` | 111 | 3.2% |
| `excludes` | 23 | 0.7% |
| `pathognomonic_for` | **3** | 0.09% |
| `sufficient_for` | **3** | 0.09% |
| 高权合计 | 199 | 5.8% |

逐段落配对，把文本自述效力与该段落抽出的断言 relation 对上：

| 文本说这个集合是 | 抽出断言数 | 高权 | 主要 relation |
|---|---:|---:|---|
| 充分 | 113 | 4（**3.5%**） | feature_of 87、treated_by 9、caused_by 7 |
| 必需 | 423 | 24（**5.7%**） | feature_of 298、caused_by 35、treated_by 28 |
| 名为 criteria | 436 | 35（8.0%） | feature_of 314、distinguishes_from 42 |
| 仅支持性 | 1,400 | 58（4.1%） | feature_of 1,000 |

关键在于**「充分」那一行连一条 `sufficient_for` 或 `pathognomonic_for` 都没有**（4 条高权是 3 条 `required_for` 加 1 条 `excludes`）。原文明说「满足这些即可确诊」，抽出来的是 87 条 `feature_of`。全库 3,456 条进组断言里 `pathognomonic_for` + `sufficient_for` 合计 **6 条（0.17%）**。

这条与 §22.3 的引擎缺口正好互为因果闭环：引擎没有「组确诊」通路，所以即使抽出 `sufficient_for` 也走不通；抽取器没有把判据集读成 `sufficient_for`，所以引擎那条通路即便补上也暂时无料可喂。两端必须同时动，单边修任何一侧都不会改变排名——这与 §20.3 三条层三修法全部失败、§21 刚性天花板为零是同一个结论的三个侧面。

### 23.5 对修复顺序的修正

§22.4 建议「引擎侧先补组确诊通路」。本节的数据要求把这个建议收窄：

1. **schema 必须先扩。** 二阶（22 条两层段落）、计分制（43 条）、否定合取（223 条段落 vs 仅 8 个组）三类在 `{group_id, logic, n}` 下不可表达。不扩 schema，抽取器再准也只能继续压平。
2. **组的效力必须成为组级字段，而非逐成员 relation。** 现在「这个集合能确诊」这件事只能靠每个成员各自扛一个 `sufficient_for` 来表示，实测 0.17% 的成功率说明这条路不通。
3. **`stated_logic()` 这把尺子本身要修。** 它漏掉了 22 条两层段落中的 21 条，所以 §22 的「155 条判据段落」和由它派生的一切比例都是下界，真实的判据段落数更高。

### 23.6 三阶及以上：存在，但更要紧的是深度根本没有上界

沿着 23.2 往上再问一层。把三阶拆成三种来源分别检测（它们需要不同的修法），全语料命中 13 条（0.13%），逐条读过之后的裁定：

**（甲）多确信度层，每层各带自己的二阶式——3 条，全部为真。**

| 疾病 | 原文 | 结构 |
|---|---|---|
| 路易体痴呆 | `probable if 2 core features **or** 1 suggestive feature **with** 1 or more core features. **possible** if only 1 core feature **or** 1 or more suggestive features` | 特征 → 层（core/suggestive）→ 计数 → 布尔组合 → **确信度映射**，共四层 |
| 血管性神经认知障碍 | `**Probable** ... is diagnosed if **one of the following** is present; **otherwise possible** ... should be diagnosed` | 基础判据 A∧B∧C∧D，其上再套一个 `any`，再套确信度二分 |
| PHACE | `**definite** PS = hemangioma > 5 cm **with** one major **or** two minor. **Possible** PS = cervicofacial hemangioma **with** one minor` | 两个确信度各带一个二阶式 |

这一类的关键在于**输出不是布尔值**。引擎的每一层都假定候选要么被淘汰、要么被确诊、要么拿到一个分数；「probable 还是 possible」是第三种输出维度，现有四层里没有任何位置承载它。

**（乙）三个或以上带修饰的层——1 条为真。** POEMS：`Mandatory major criteria (2 条，全需) + Other major criteria (3 条，≥1) + Minor criteria (5 条，≥1)`。三个内层集合各自带不同的量词，外层再做合取。`{group_id, logic, n}` 只能表示其中一个内层。

**（丙）递归引用：成员本身是一个由判据定义的实体——这一类才是真正的问题。** 上面的窄检测器只报了 9 条，放宽后全语料 **38 条（0.38%）** 含 `meets / fulfils criteria for <另一个实体>`，其中 **17 条是否定式**（`does not meet criteria for`）。分布集中在 DSM-5（11 条）、Harrison、Nelson 等成体系的诊断手册里；有 7 条段落在同一处出现 2–3 次引用。

典型的三条：

- DSM-5 路易体痴呆：`Suggestive diagnostic features: a. **Meets criteria for** rapid eye movement sleep behavior disorder.` ——判据集的一个成员本身是另一个疾病的判据集。
- 出血分级：`Type 2: any clinically overt sign of haemorrhage that is actionable but **does not meet criteria for** Type 3, Type 4, or Type 5` ——对三个判据集的否定合取。
- 精神分裂症谱系残余类：`used in situations in which the presentation **does not meet the criteria for any specific** schizophrenia spectrum and other psychotic disorder` ——对一整族判据集的全称否定。

这一类的意义不在于 38 这个数字，而在于**它让判据结构的深度失去上界**。「满足 X 的判据」中的 X 又由判据定义，深度由诊断分类体系本身决定，不是 2 也不是 3。第三条那种全称否定（「不满足该族中任何一个」）更是连有限枚举都做不到——它需要引擎能对一整组候选做量化，而当前引擎逐候选独立打分，结构上没有这种能力。

**检测覆盖率的诚实交代。** 这些检测器和 23.2 的一样是词汇型的，而 23.2 已经证明词汇型检测器会系统性漏检（22 条两层段落只认出 1 条）。所以 13 和 38 都是**下界**，真实数量更高。反过来说，即使按下界读，也已经足以否定「三种 logic 加二阶就够了」这个设想。

**这些段落抽出来是什么样子。** 13 条三阶候选共产出 283 条断言：`NO_GROUP` 238 条（84.1%）、`any` 28 条、`all` 17 条、`at_least_n` **0 条**。也就是说，语料里结构最复杂的那批段落，抽取器给出的组结构比平均水平还要退化——84% 的断言连一阶组都没成。

**对 23.5 修复顺序的进一步修正。** 甲、乙两类可以靠扩 schema 解决（组级效力字段 + 组间连接 + 确信度输出维度）。丙类不能：递归引用要求断言的谓词位置能放一个「另一个诊断实体的判据集」，这在扁平七元组里没有落点，而全称否定还额外要求引擎能跨候选量化。因此本节的结论是——**丙类应当明确划出范围之外并记录为已知边界，而不是当作待修缺陷**；把工程力量投在甲、乙和 23.1 的四类非平面结构上，收益更实在。

### 23.7 本节产物

| 文件 | 内容 |
|---|---|
| `audit_criteria_structure.py` / `criteria_structure_audit.json` | 判据段落内的非平面结构清点、logic 失真初算、进组断言 relation 分布 |
| `audit_criteria_taxonomy.py` / `criteria_taxonomy_audit.json` | 全 9,928 段落的独立结构扫描（八类）、二阶深度、文本自述效力分类 |
| `probe_second_order.py` / `second_order_probe.json` | 二阶候选的三种检出形态与逐条阅读；文本效力 × 抽出 relation 配对表 |
| `probe_third_order.py` / `third_order_probe.json` | 三阶三类来源（多确信度层 / 三层带修饰 / 递归引用）的检出与逐条阅读，及其抽取产物 |
| `calc_logic_distortion.py` | 段落级 logic 混淆表、保真率、TVD 与随机基线对照 |

## 24 逐段深读原始语料：§22「语料无责」的判断必须推翻

§22–§23 的全部结论都来自词汇型检测器统计。本节改为把原始段落原文导出逐条阅读——例 74 的全部 233 条检索段落，加上跨全语料按结构分层抽取的 64 条样本。读完之后，§22.4「语料无责，责任在抽取和引擎」这个判断站不住了：**语料的渲染环节才是第一因**，而且它同时解释了 §22 与 §23 记在抽取头上的大部分现象。

### 24.1 决定性证据：宣告了判据列表，列表却不在

例 74 检索到的一条段落原文：

> The diagnosis of metabolic syndrome **requires the presence of 3 or more metabolic abnormalities:** Patients with metabolic syndrome are estimated to have a 2-fold increased risk of ...

冒号之后直接是下一段。**量词活了下来，成员被删干净了。**代谢综合征那 5 条判据一条都不在段落里。

全语料清点：**286 条段落宣告了一个判据列表，其中 259 条（90.6%）列表不存在。**

更能说明问题的是 CAM 谵妄判据那几条：

> it includes the following criteria: **The presence of delirium requires features 1 and 2 and either 3 or 4:**

量词不但活了下来，还是个二阶布尔式 `(1 ∧ 2) ∧ (3 ∨ 4)`，成员用**序号**指代——而被序号指代的那张编号列表被删了。这条既是二阶结构的实例，又是「成员不可寻址」的实例。

这一条推翻了 §22.2 的归因。当时观察到「语义性痴呆四条成员在全库出现 0 次，抽取器转而去捡段落里其他位置的零散名词」，并把它记为抽取器的召回缺陷。真相是：**冒号处根本没有东西可抽**，抽取器捡零散名词不是绕开判据集，是判据集已经不在段落里了，它只剩下零散名词可捡。

### 24.2 量词与成员在文本里的实际排布

对 155 条判据段落，量词与第一个列表标记的句子位置关系：

| | n | 占比 |
|---|---:|---:|
| 量词与列表在**同一句** | 19 | **12.3%** |
| 在**不同句** | 23 | 14.8% |
| 量词之后**根本没有列表标记** | 113 | **72.9%** |

而当前抽取提示词的成组规则原文是：

> Criterion groups: **when one sentence lists several findings** that together form ONE diagnostic criterion set, emit one assertion per member and give all members the same group_id ...

**提示词把成组的适用范围限定在单句内，而单句内同时含量词和成员的只占 12.3%。**这不是模型没做好，是规则本身覆盖不到 87.7% 的真实情形。§23.3 测到的「只有 32.9% 的判据段落产出了任何组」，与这个 12.3% 加上跨句的 14.8% 合计 27.1% 在同一量级——这两个数字互相印证。

### 24.3 量词的表层形态清单（供抽取算法使用）

逐条阅读得到的量词表层形态，按是否落在句子里分类。带 ✗ 的形态被当前单句规则漏掉：

| 形态 | 实例 | 单句规则可及 |
|---|---|:--:|
| 句内显式 | `at least two of the following features: onset ... ; and absence of ...` | ✓ |
| 冒号引导，成员在其后独立成句/成列表 | `requires the presence of all of the following criteria:` + 编号列表 | ✗ |
| **表格列头即量词** | `Major Criteria **(All Must Be Fulfilled)** \| Minor Criteria` | ✗ |
| **表头与成员分列两栏被压平** | `Major Criteria (All Must Be Fulfilled) Minor Criteria Exocrine pancreatic insufficiency Absence of pancreatic polypeptide secretion ...` | ✗ |
| **序号指代** | `requires features 1 and 2 and either 3 or 4` | ✗ |
| **跨块悬空引用** | `at least 1 criterion must be fulfilled from **groups I or II**`（组 I、II 的定义在另一个切片） | ✗ |
| 成员被句号切断 | `The four criteria ... are, fever higher than 38.5 C, ESR more than 40**.** Weight-bearing status ..., and WBC count ...` | ✗ |
| 命名判据集（量词隐含在名字里） | `Kanavel's four cardinal signs` | ✓ |
| 分数带阈值 | `A total score of ≥ 4 ... confirms classification` | ✗ |

两条附带发现：

**表格压平使层归属不可恢复。**pNET 那条的两栏表头相邻出现，随后两栏的条目交替混入同一文本流，`Exocrine pancreatic insufficiency` 到底属于 major 还是 minor，从文本上无法判定。EDS 那张表更进一步，连词边界都没了（`ClassicalAD`、`hyperextensibilityWidened`）。全语料两栏表头相邻的段落 10 条，其中 2 条含 ≥5 处词粘连。数量不大，但它们恰好是 §23.2 认定的二阶结构所在。

**跨块悬空引用是检索切片造成的。**例 74 检索到的 ARVC 段落只有一句 `at least 1 criterion must be fulfilled from groups I or II`，而 ARVC 国际工作组判据表本身**一条都没被检索到**。量词与成员被切到了不同 passage，且只有前者进了候选池。

### 24.4 例 74 端到端：金标自己的诊断量表被压成 83 条 `feature_of`

例 74 的金标是 CPVT。它检索到的 233 条段落里，**被 `stated_logic()` 认作判据集的有 0 条**——而这个病例的两个主要候选（CPVT 与 ARVC）都各有一套正式判据。检出为 0 本身就说明尺子失效。

其中一条是完整保留下来的 CPVT 诊断计分卡：

> Clinical Criteria **Points** ... Exercise/activity-associated ACA/SCA **2** ... Inducible bidirectional VT at HR > 100 bpm **4** ... QTc ≤ 420 ms **0.5** / 421 < QTc < 460 ms **0** / QTc ≥ 460 ms **−0.5** ... Negative CPVT genetic test **−1** ... Evidence of ischemic or structural heart disease **−2** ... **3.5–12 points**: high pre-test probability (definite/probable ≥ 90%) / **2–3 points**: intermediate (possible, ≈50%) / **0.5–1.5**: low / **≤0**: no evidence

这是整个例 74 检索结果里最权威的一个对象，而且渲染完好：带权重、带**负权重**、带前置门槛（`requires an exercise stress test/ambulatory Holter finding`）、带四段确信度输出。病历给的 QTc 是 380 ms，正好落在 `QTc ≤ 420 ms → +0.5` 这一档。

抽取器从这一条段落抽出 **113 条断言**：

| | n |
|---|---:|
| `feature_of` | 83 |
| `excludes` | 23 |
| `required_for` / `diagnostic_for` / `risk_factor_for` / `exacerbates` | 7 |
| 带 `criterion_group` | **5**（全部 `any`） |
| 带数值 threshold | 21 |

分值 2 / 4 / 1 / 0.5 / −0.5 / −1 / −2 一个都没有落地，四段确信度输出没有落地，前置门槛没有落地。而谓词 `syncope` **被重复抽出 8 次以上**——一张计分卡的一行，变成了层三里 8 张相同的弱票。这正是 §19.4 与 §20.4 反复测到的体量效应，此处能看到它的直接来源。

### 24.5 归因的修正

§22.4 写的是「语料无责，抽取责任最大，引擎有独立缺口」。逐段深读后应改为四段，且顺序颠倒：

1. **语料渲染是第一因。**90.6% 的判据列表宣告后成员缺失；表格压平使层归属不可恢复；检索切片把量词与成员切散。这一层不修，后面三层做什么都没有输入。（§25 把这一条定位到了具体来源与具体代码：89.6% 的缺失来自 StatPearls 的 NXML 解析脚本漏读 `<list>`，原始 XML 完好，可无损恢复。）
2. **schema 是第二因。**即使成员齐全，`{group_id, logic, n}` 装不下权重、负权重、层、组间连接、确信度输出、序号指代（§23.1–23.2）。
3. **提示词的单句限制是第三因。**成组规则只覆盖 12.3% 的真实排布。这一条是四者中最便宜的，改写规则即可。
4. **引擎语义是第四因。**`any`/`at_least_n` 无刚性通路，任何组都无法确诊（§22.3）。

§22.4 与 §23.5 里「引擎侧先补」的建议因此再次收窄：**引擎侧的改造在语料渲染修好之前无法验证**，因为现在送进引擎的组本身就是残缺的。合理的次序是 1 → 3 → 2 → 4，其中第 3 步可以立刻做且不依赖前一步。

### 24.6 抽取算法需要的输入形态

逐条阅读得出的、可直接落到实现上的要求：

- **成组的作用域必须是段落而非单句**，并且要能跨越冒号、换行、编号列表和被误插的句号。
- **量词必须允许出现在成员之前任意距离处**，包括表格列头位置和括号内（`(All Must Be Fulfilled)`）。
- **需要一个「成员缺失」的显式返回值。**现在抽取器遇到悬空冒号时会去捡邻近名词，产生的是噪声；正确行为是报告「此处有一个 logic=at_least_n、n=3 的组，成员不可得」，这样下游至少知道自己缺什么，也能把这类段落回流给语料修复。
- **序号指代与跨块引用需要一个未解析引用类型**，而不是丢弃。
- 分数制需要 `weight` 字段与 `score_threshold` 组级字段；负权重必须允许。
- 层结构需要组级 `tier` 与组间连接，否则 major/minor 只能压成一个平面组。

### 24.7 本节产物

| 文件 | 内容 |
|---|---|
| `dump_for_close_reading.py` | 导出例 74 全部 233 条检索段落原文（带结构线索标注），及跨语料按结构分层的 64 条阅读样本 |
| `reading_case74.md` | 例 74 逐段原文，供人工阅读 |
| `reading_sample.md` | 七类结构各自的原文样本 |
| `audit_dangling_enumeration.py` / `dangling_enumeration_audit.json` | 宣告判据列表但成员缺失的清点（286 / 259）、压平表格、裸量词 |

## 25 判据列表是在哪一步丢的：不是 PDF 语料，是 XML 入库脚本漏了一个标签

§24 把 90.6% 的判据列表缺失记在「语料渲染」头上，但没有区分是 PDF/OCR 入库（textbooks、merck）还是抓取入库（statpearls、pmc_oa）造成的。检索池的 9,928 条段落带 `source` 字段，可以直接分开算。结论与直觉相反：**PDF 语料基本无责，责任几乎全在 StatPearls 这个 XML 语料的入库脚本上，而且是一处可以精确定位的代码缺陷。**

### 25.1 按来源拆开

| source | 段落数 | 宣告了判据列表 | 其中列表缺失 | 缺失/宣告 | 缺失/段落 |
|---|---:|---:|---:|---:|---:|
| **statpearls** | 6,945 | 251 | **232** | **92.4%** | **3.34%** |
| pmc_oa | 1,519 | 16 | 12 | 75.0% | 0.79% |
| textbooks | 1,114 | 14 | 11 | 78.6% | 0.99% |
| merck | 155 | 4 | 4 | 100.0% | 2.58% |
| manifest_cpg | 165 | 1 | 0 | 0.0% | 0.00% |
| wikem | 30 | 0 | 0 | — | 0.00% |
| 合计 | 9,928 | 286 | 259 | 90.6% | 2.61% |

**259 条缺失里 232 条（89.6%）来自 StatPearls。**StatPearls 既宣告得更频繁（3.6% vs 其他 1.0–1.3%），缺失率又最高。

列表标记的保留情况是判定的关键：

| source | 项目符号 `•▪` | `1. … 2.` 编号 | 连字符断行 | 连字 `ﬁﬂ` | 页码引用 |
|---|---:|---:|---:|---:|---:|
| statpearls | **0.0%** | 0.2% | 1.1% | 0.0% | 0.0% |
| pmc_oa | 1.2% | 0.5% | 3.6% | 0.0% | 0.1% |
| textbooks | 1.8% | 1.9% | 3.9% | **2.4%** | **0.6%** |
| merck | **6.5%** | 0.0% | 1.9% | 0.0% | 0.0% |

右边三列是 PDF/OCR 的指纹，集中在 `textbooks`（DSM-5、Harrison、Adams 等）；这确实是 OCR 损伤，但它造成的是连字、断词、页码噪声，**不是列表丢失**——textbooks 只占缺失总量的 4.2%。

而 `merck`（`manifest.json` 记为 `format: pdf_chm_export`，即用户所说的 MSD PDF 语料）的项目符号保留率 **6.5%，是全部来源中最高的**。也就是说，PDF 抽取管线保住了列表结构，XML 解析管线反而没保住。

### 25.2 定位到具体位置：列表在切块之前就没了

取代谢综合征那条追到底。它在 StatPearls 原始 chunk 文件里的形态：

| chunk | tokens | 内容 |
|---|---:|---|
| `_p3` | 49 | Metabolic syndrome is an accumulation of several disorders ... |
| `_p4` | **14** | `The diagnosis of metabolic syndrome requires the presence of 3 or more metabolic abnormalities:` |
| `_p5` | 110 | Patients with metabolic syndrome are estimated to have a 2-fold increased risk ... |

这篇文章一共 39 个 chunk，**5 条判据成员一条都不在其中任何一个里**。所以不是检索切片切走的，是入库时就没进来。

再看原始 NXML（`article-25039.nxml`）同一位置：

```xml
<p>The diagnosis of metabolic syndrome requires the presence of 3 or more metabolic abnormalities:</p>
<list list-type="bullet">
  <list-item><p>A waist circumference of more than 40 inches in men and 35 inches in women</p></list-item>
  <list-item><p>Serum triglycerides level of 150 mg/dL or greater</p></list-item>
  <list-item><p>Reduced high-density lipoprotein cholesterol, less than 40 mg/dL in men or less than 50 mg/dL in women</p></list-item>
  <list-item><p>Elevated fasting glucose of l00 mg/dL or greater</p></list-item>
  <list-item><p>Blood pressure values of systolic 130 mm Hg or higher or diastolic 85 mm Hg or higher</p></list-item>
</list>
```

**五条判据连同各自的数值阈值全都在原始 XML 里。**丢失发生在解析这一步：

```77:78:scripts/build_statpearls_corpus.py
            for p in sec.findall("p"):
                text = _clean(_text(p))
```

`sec.findall("p")` 只取 `<sec>` 的直接子级 `<p>`。`<list>` 是 `<p>` 的兄弟节点，从不被访问；`<list-item>` 里的 `<p>` 因为不是 `<sec>` 的直接子级，同样取不到。`<table-wrap>` 也是同理。

### 25.3 丢了多少、能捞回多少

全部 9,638 份原始 NXML：

| | 数量 |
|---|---:|
| 含至少一个 `<list>` 的文章 | 9,637 / 9,638（**100.0%**） |
| `<list>` 元素 | 82,942 |
| `<list-item>` 元素 | **294,966** |
| `<table>` 元素 | 1,695 |
| `<list-item>` 内的正文 | **27.7 M 字符**（约 550 万词） |

对照入库结果：367,799 个 chunk 里含项目符号的只有 **13 个（0.004%）**，含 `1. … 2.` 编号的 118 个（0.032%）。而 **21,404 个 chunk（5.82%）以冒号结尾**——每一个都是一句宣告，后面本该跟的列表被丢掉了。另有 32.7% 的 chunk 不足 40 token，与「段落留下、列表消失」的形态一致。

原始 XML 完好，因此**这部分内容无需重新下载即可恢复**，改一处解析逻辑即可。这是目前发现的所有问题中修复成本最低、影响面最大的一个：它同时是 §24.1（90.6% 判据列表缺失）、§23.3（`at_least_n` 只有文本比例的 0.23 倍）、§22.2（判据成员全库出现 0 次）三处观测的共同上游。

### 25.4 各来源的责任归属修正

| 来源 | 入库方式 | 主要缺陷 | 严重度 |
|---|---|---|---|
| statpearls（70% 段落） | NXML 解析 | **`<list>` / `<table-wrap>` 整体丢失** | 高，且可完全恢复 |
| pmc_oa（15%） | 期刊全文 | 表格压平，层归属不可恢复（10 张压平表中占 6 张）；词粘连 1.9% | 中 |
| textbooks（11%） | PDF/OCR | 连字 2.4%、断词 3.9%、页码噪声 0.6% | 低（噪声，非结构丢失） |
| merck（1.6%） | PDF 导出 | 列表保留最好（6.5%），无系统性缺陷 | 低 |

用户问的「PDF 识别语料 vs 爬取语料」，答案是**爬取/XML 侧**；而且在 PDF 侧，MSD 恰恰是保留结构最好的那一个。

### 25.5 本节产物

| 文件 | 内容 |
|---|---|
| `audit_defects_by_source.py` / `defects_by_source.json` | 按 6 个来源分列的判据列表缺失率、PDF/OCR 指纹、判据段落与分层表格分布 |

## 26 pmc_oa 与 textbooks 的丢法与 StatPearls 不同，修法也不同

§25 把 StatPearls 的缺失定位到一处解析缺陷并确认可无损恢复。另外两个来源不是同一回事：**pmc_oa 不是 XML 解析漏读，textbooks 根本不是 XML**。三者的丢失机制、本地是否还握有结构化源、以及能恢复到什么程度，都要分开说。

### 26.1 pmc_oa：内容还在，丢的是「归属」，再被长度下限滤掉一部分

pmc_oa 走的是 NCBI 的 **BioC JSON API**（`scripts/fetch_pmc_bioc.py`），原始响应存盘在 `data/cpg/raw/pmc_oa/`，共 **5,869 份**。所以结构化源在本地。

但 BioC 本身就已经把层级压掉了。抽样统计 BioC 的 passage 类型，**没有 `list` 这个类型**：`paragraph`、`title_1..5`、`table`、`table_caption`、`fig_caption`、`ref`、`footnote`。实际观察到的行为是——`<list-item>` 被转成了**普通 `paragraph`**：

> `[paragraph]` `Studies were categorised according to:`
> `[paragraph]` `Whether they were empirical (research-based) studies.`
> `[paragraph]` `What level prioritisation occurred at (macro – national or international level, ...)`
> `[paragraph]` `Whether prioritisation was carried out across diseases/areas in public health ...`

内容全在，但**没有任何标记表明这四条属于上面那句宣告**。这与 StatPearls 的「内容消失」是两种不同的损坏。

在此之上，本仓库的 `should_keep_chunk` 又加了一道长度下限（含换行/项目符号/百分号/分号时 30 字符，否则 **60 字符**）：

```158:160:scripts/pmc_oa_ddx_common.py
    min_len = 30 if re.search(r"\n|•|–|\d+%|;\s", text) else 60
    if len(text) < min_len:
        return False
```

判据条目通常很短，正好撞在这条线上。全量统计：

| | n | 占比 |
|---|---:|---:|
| `paragraph` passage | 320,354 | — |
| 低于长度下限、被 `should_keep_chunk` 丢弃 | **44,853** | **14.0%** |
| `table` passage（BioC 已把每张表压成一段文本） | 14,317 | — |
| 以冒号结尾的宣告句 | 1,373 | — |
| 　后面跟着 ≥2 条短 paragraph（即列表尚在，只是无标记） | **659** | 48.0% |
| 　　其中至少一条成员低于长度下限 | 344 | 52.2% |
| 　后面没有列表状内容（真丢失） | 714 | 52.0% |

列表成员长度中位数 101 字符，p25 为 51 字符，**30.4% 低于 60 字符的下限**。

「714 条真丢失」应读作**上界**：这个判定要求宣告句之后紧跟 ≥2 条不超过 400 字符的 paragraph，被小标题打断或首条成员偏长的情形会被误判为丢失。

**修法（按性价比排序）：**

1. **降低并改写长度下限。**当前规则对「短」的惩罚与判据条目的自然长度直接冲突。改为：紧跟在冒号宣告之后的 paragraph 不受长度下限约束。成本极低，能救回 344 条宣告中的短成员。
2. **重切块时按邻接把列表项挂回宣告句。**BioC 的 passage 是有序的，宣告句 + 其后连续的短 paragraph 构成一个可恢复的组。这是把「归属」重建出来，直接对应 §24.6 要求的段落级成组作用域。`scripts/rechunk_pmc_oa.py` 已存在，是合适的落点。
3. **表格需要另取 JATS XML。**BioC 把每张表压成一段带 `\t` 的文本（14,317 张），列边界不可恢复——§23.2 认定的二阶结构里，pmc_oa 占了压平表格的 6/10 和分层段落的 50%。要恢复列结构必须重新拉 PMC OA 的原始 JATS XML，这一步需要联网重取，成本最高，建议放到最后。

### 26.2 textbooks：本地没有结构化源，只能做规范化

textbooks 不是 XML，也不是我们自己抽的 PDF。它是 **MedRAG 发布的 Textbooks 语料**（`data/corpus/textbooks/README.md` 指向 arXiv 2402.13178），下载下来就已经是切好块的纯文本：

| | |
|---|---|
| 分册 chunk 文件 | 18 |
| chunk 数 | 125,847 |
| 中位长度 | 865 字符（固定窗口，**无任何章节元数据**，`title` 只有书名） |
| 本地持有的教科书 PDF | **0**（`data/` 下 110 份 PDF 全是 NCCN/ACR/KDIGO/WHO 等指南） |

切块是纯固定窗口，会从句子中间切断（如 `Neurology_Adams_2` 以 `a benign cyst.` 开头）。上游的 OCR 损伤也一并继承：

| 缺陷 | chunk 数 | 占比 | 可修 |
|---|---:|---:|---|
| 连字 `ﬁ ﬂ ﬀ` | 2,456 | 1.95% | ✓ 字符规范化 |
| 行末断词 `neurode- generative` | 3,612 | 2.87% | ✓ 正则合并 |
| 页码引用 `(p. 184)` | 635 | 0.50% | ✓ 剥离 |

**修法：**只能做上面三项规范化，成本很低但收益也有限——它们制造的是噪声，不是 §24 所关心的结构丢失（textbooks 只占判据列表缺失总量的 4.2%）。真正的结构问题（固定窗口切断列表、无章节路径）在本地无源可依，要修必须重新获得原始 PDF 并自建抽取管线，这已经超出「修补」的范畴。

在此之前有一个更实际的判断：textbooks 只占检索池的 11.2%，却贡献了 28.4% 的判据段落（DSM-5、Harrison、Adams 是判据密度最高的几本）。所以它虽然修不动，但**不应该被降权或剔除**——正确的做法是接受它的噪声，并在抽取侧对断词与连字做输入端规范化。

### 26.3 三个来源的修复对照

| 来源 | 占检索池 | 本地结构化源 | 丢失机制 | 修法 | 可恢复度 |
|---|---:|---|---|---|---|
| **statpearls** | 70.0% | ✓ 9,638 份 NXML | 解析器只读 `<sec>` 的直接子 `<p>`，`<list>` / `<table-wrap>` 从不访问 | 改 `build_statpearls_corpus.py` 的遍历逻辑 | **完全**：294,966 条 `<list-item>`、27.7 M 字符 |
| **pmc_oa** | 15.3% | ✓ 5,869 份 BioC JSON（但 BioC 已压掉列表层级） | 归属标记丢失 + 60 字符下限滤掉 14.0% 段落 + 表格压平 | 降下限、按邻接重建组；表格需重取 JATS | **部分**：659 条宣告的成员可挂回，表格需联网 |
| **textbooks** | 11.2% | ✗ 只有 MedRAG 预切块文本 | 上游 OCR 损伤 + 固定窗口切块 | 连字/断词/页码规范化（重新装配切分已核算为不值得，见 §26.4） | **很低**：只能除噪 |

三者共同的下游成本是一样的：改完任何一个都要重建检索索引（861,131 切片的 TF-IDF + MiniLM）。因此建议合并成一次改动后统一重建，而不是分三次。

优先级由「可恢复度 × 占比」决定，与 §25.3 的结论一致：**先修 StatPearls**（70% 的段落、完全可恢复、一处解析改动），再做 pmc_oa 的前两项（不需要联网），textbooks 的规范化可以顺手带上，pmc_oa 的 JATS 重取放在最后再评估是否值得。

### 26.4 textbooks 能重新装配切分吗：能，但不值得

§26.2 说 textbooks「固定窗口切块无结构」，自然的下一个问题是能否把块拼回去再按结构重切。技术上可行，收益接近于零，理由有两条，都要用数据说清楚。

**装配本身是可行且近乎无损的。**18 册共 125,847 个块，id 严格连续（`Neurology_Adams_0..12369`），相邻块的重叠率只有 **0.3%**，而 **26.0% 的块以小写字母开头**——说明切点大多落在句中，按 id 顺序拼接即可还原原文。实测拼回 `Neurology_Adams` 后，路易体痴呆那句判据完整可读：

> Diagnostic criteria have been offered by a working group, **requiring 2 of 3 of the following**: a parkinsonian syndrome (usually symmetric), fluctuations in behavior and cognition, and recurrent hallucinations (McKeith et al).

**但切点本来就几乎没有割断判据集。**在拼回的全文里找出 1,262 处判据宣告，看它们连同其后 700 字符跨了几个块：

| | n | 占比 |
|---|---:|---:|
| 宣告与成员在同一块内 | 202 | 16.0% |
| 跨两个块 | 969 | 76.8% |
| 跨三个及以上 | 91 | 7.2% |
| **被检索窗口（命中块 ±1）覆盖** | **1,260** | **99.8%** |
| 加上窗口仍被割断 | **2** | **0.2%** |

检索层本来就发的是三片窗口（`window_gids`），跨两块的 76.8% 全部被它接上。**1,262 处判据宣告里，最终真正被切分割断的只有 2 处**，分别在 `Neurology_Adams` 和 `Physiology_Levy`，且其中一处还是原文自身重复导致的误判。重新装配能修的就是这 2 处。

**更根本的原因是重切时没有结构可依。**上游 PDF 抽取已经把版面压平了：

| | chunk 数 | 占比 |
|---|---:|---:|
| 含换行符 | **0** | **0.00%** |
| 含项目符号 `•▪` | 2,783 | 2.21% |
| 含 `1.` / `(1)` 编号 | 6,555 | 5.21% |
| 含 ≥2 个分号（判据写成行内散文） | 14,900 | 11.84% |

125,847 个块里**换行符一个都没有**。所以「重新按结构切分」这件事没有输入——重切器唯一能用的是项目符号、编号和分号这些词汇线索，而这些线索抽取器在当前文本上已经能直接看到，不需要先装配。

textbooks 与 StatPearls 的对比正好说明了两类损坏的区别：StatPearls 是**内容缺失、结构源完好**，所以改一处解析就能全量恢复；textbooks 是**内容完好、结构源已毁**，装配只能还原字符流，还不回版面。

**结论：不做装配。**这 2 处的收益不足以支撑一次 861,131 切片的索引重建。textbooks 侧仍然只推荐 §26.2 的三项规范化（连字 1.95%、断词 2.87%、页码 0.50%），而且可以在抽取输入端做，不必动语料。

### 26.5 本节产物

| 文件 | 内容 |
|---|---|
| `audit_pmc_textbook_repair.py` / `pmc_textbook_repair_audit.json` | BioC passage 类型与长度下限的丢弃量、冒号宣告的成员可恢复性；textbooks 的持有源清点与 OCR 噪声率 |
| `audit_textbook_reassembly.py` / `textbook_reassembly_audit.json` | textbooks 块的连续性与重叠率、1,262 处判据宣告的跨块分布与窗口覆盖率、重切可用的版面线索清点 |

## 27 现有的两套跨 chunk 机制能不能顶上：不能替代语料修复，但它是修复之后的正确落点

仓库里确实有两套独立的跨 chunk 机制。核查之后的结论分两半：**它们都够不着 §24–§26 的问题，原因是同一个——损失发生在建库阶段，而两套机制都在建库下游**；但 KG 那套的设计恰好就是 §24.6 要的东西，修完语料之后应当复用它而不是另写。

### 27.1 两套机制

| | (a) 试验/天花板管线 | (b) 指南 KG 管线 |
|---|---|---|
| 入口 | `trial_retriever.py::TrialRetriever.passage(gid, window=1)` | `scripts/build_guideline_kg_claim_windows.py::detect_claim_blocks` |
| 时机 | **检索时** | **建库时**（Passage 之后） |
| 拼接单位 | 全局 `gid` | `source_ordinal` / `passage_id` |
| 邻居策略 | 同文档固定 ±1 | closure ±N → 连续 ordinal 组成 `EntryRun` → 结构块合并 → token 预算打包 + 句级 overlap |
| 邻接凭证 | `window_gids` 列表 | `offset_map` 字符级无损映射、`synthetic_regions` |
| 对「冒号 + 列表」 | 无处理，靠 ±1 碰运气 | **`LEAD_IN` 显式把引导句与其后列表合并成不可分割的 `criteria_*` 块** |
| 消费语料 | merck / manifest_cpg / wikem / **pmc_oa / statpearls / textbooks** | **仅** merck / cpg / wikem（其他 family 直接抛错） |

(a) 已经在跑，而且 §26.4 测到的「textbooks 99.8% 的判据宣告被覆盖」正是它的功劳。(b) 的 `detect_claim_blocks` 在 `LEAD_IN` 命中时会把 `criteria require ...:` 这类引导句与紧随的列表并成一个块，还有专门的回归测试 `test_cross_chunk_criteria_are_reassembled_as_one_claim_block`——这就是 §24.6 提的「成组作用域必须是段落而非单句」。

### 27.2 为什么两套都够不着：损失在建库，机制在建库下游

检索索引的输入是**过滤之后**的 chunk 文件：

```35:41:analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL/build_trial_index.py
SOURCES = {
    "merck": ROOT / "data/corpus/merck/merck_manual_19e_chunks.jsonl",
    ...
    "pmc_oa": ROOT / "data/cpg/processed/pmc_oa_ddx_chunks.jsonl",
    "statpearls": ROOT / "data/corpus/statpearls/statpearls_chunks.jsonl",
```

这两个文件就是缺失发生的地方。逐个语料对照：

| 语料 | 内容还在索引里吗 | ±1 窗口 / claim window 能做什么 |
|---|---|---|
| **statpearls** | **否**——`<list>` 在 NXML 解析时就没进 `statpearls_chunks.jsonl`（§25.2） | 什么也做不了。`_p4`（冒号宣告）的邻居是 `_p3` 和 `_p5`，都是无关段落；把它们粘起来只会得到「宣告 + 错误内容」，**比不粘更坏** |
| **pmc_oa** | **部分**——44,853 条（14.0%）低于 `should_keep_chunk` 的 60 字符下限，从未进入 chunk 文件，因此也不在索引里（§26.1） | 够不着已被丢弃的那部分；对幸存的部分，±1 窗口已经在无意中接上了一些 |
| **textbooks** | **是**——什么都没丢 | 已经生效，覆盖 99.8%（§26.4） |

所以跨 chunk 机制**不能替代**语料修复。它能拼的只是索引里已有的东西，而问题恰恰是东西不在索引里。

### 27.3 KG 那套为什么在 Merck 上能用、在这三个语料上不能用

即使把三个语料喂给 (b)，`detect_claim_blocks` 也不会触发合并，因为它的结构判定是**行级 + 标记级**的：

```519:521:scripts/build_guideline_kg_claim_windows.py
def _line_spans(text: str) -> list[tuple[int, int, str]]:
    result: list[tuple[int, int, str]] = []
    for match in re.finditer(r"[^\n]+", text):
```

```550:551:scripts/build_guideline_kg_claim_windows.py
def _looks_list(value: str) -> bool:
    return bool(LIST_MARKER.match(value))
```

`_line_spans` 按 `\n` 切行，`_looks_list` 要求行首有项目符号或 `1.` / `a)` 标记。而 `LEAD_IN` 合并的前提是**其后的块被判为 list/table**。三个语料的实际情况：

| 语料 | 换行符 | 行首列表标记 | `_looks_list` 会触发吗 |
|---|---:|---:|---|
| merck | 有 | **6.5%**（全库最高） | **会**——所以它在 Merck 上工作 |
| statpearls | 每 chunk 之间有 | **0.004%** | 不会 |
| pmc_oa（BioC） | 有 | 列表项是**无标记的普通 paragraph** | 不会 |
| textbooks | **0.00%** | 2.21%，但全文是一行 | 不会（整个 EntryRun 塌成一个 prose 块） |

KG 管线只接 merck/cpg/wikem 不是偶然——**它的结构检测器只在保留了版面标记的语料上成立**。这与 §25.1 的发现互为印证：Merck 这个 PDF 语料恰好是列表保留最好的一个。

### 27.4 正确的用法：修完语料之后复用 (b)，并给它补一个位置型列表检测

结论不是「机制没用」，而是**顺序反了**。正确的接法：

1. **先修 StatPearls 解析**（§25.2）。恢复出来的是真正的 `<list>` 标记，可以直接渲染成带项目符号的行——**这样 `_looks_list` 原生就能命中**，`LEAD_IN` 合并无需改动即可工作。这是把 (b) 用起来的前提，不是替代品。
2. **给 `detect_claim_blocks` 补一个位置型列表检测**，供 pmc_oa 使用。BioC 的列表项没有任何标记，只能靠位置识别：*紧跟在 `LEAD_IN` passage 之后、连续 ≥2 条、每条短于某阈值的同级 passage*，判为 list。这与现有的行级检测是并列的第二条通路，不冲突。§26.1 测到 659 条宣告（48.0%）符合这个形态，是可直接验证的目标集。
3. **同时放宽 `should_keep_chunk` 的长度下限**（§26.1）。否则第 2 步认得出形态也拿不到成员——成员长度中位数 101 字符、p25 为 51，30.4% 在 60 字符线以下。
4. **把 statpearls / pmc_oa 加入 KG 的 family 白名单**（当前 `family not in {"merck","cpg","wikem"}` 直接抛错）。
5. **textbooks 不接入**。它没有换行可切（§26.4），(b) 对它退化成一个 prose 块；而 (a) 的 ±1 窗口已经覆盖 99.8%，没有剩余收益。

`offset_map`、`ordinal gap 不桥接`、`resplit` 这些 (b) 已有的性质正好对应 §24.6 要求的「成员可寻址」与「不跨文档误合」，所以第 2 步应当是往 (b) 里加一条检测通路，而不是在试验管线里另起一套。

### 27.5 本节产物

本节为代码核查，无新产物文件。涉及的实现位置：`trial_retriever.py:69`（±1 窗口）、`gate_assertions.py:292`（quote ±1200 字符证据窗）、`build_guideline_kg_passages.py:495`（closure ±N）、`build_guideline_kg_claim_windows.py:574`（`detect_claim_blocks`，含 `LEAD_IN` 合并）、`build_trial_index.py:35`（索引输入清单）。

## 28 textbooks 的输入端规范化具体怎么做，以及它对判据值多少

§26.2 与 §26.4 把 textbooks 的处置定为「只做三项规范化，不做装配」，但没有把规范化实现出来，也没有量过它对判据的贡献。本节补上这两件事。结论：**朴素正则做规范化是有害的，必须用语料自身词表授权；做对之后，它能修好 14.9% 的判据段落，剩下的 85% 靠它没用。**

### 28.1 朴素正则会造成新的损坏

第一版用 `([A-Za-z]{2,})-\s+([a-z]{2,})` 直接合并断行连字符，抽样立刻暴露两类错误：

| 原文 | 朴素规则 | 应该是 |
|---|---|---|
| `temporo- mandibular` | `temporomandibular` | ✓ |
| `box- shaped` | `boxshaped` | ✗ 应保留 `box-shaped` |
| `sin- your reasoning. gle-celled`（PDF 双栏交错） | `sinyour reasoning. gle-celled` | ✗ 根本不该合并 |

第三例尤其要紧：双栏 PDF 的两列文字交错后，`sin-` 的真正下文是隔了一段的 `gle-celled`，而紧邻的是另一列的 `your reasoning.`。按字符形状合并，等于把两列的碎片焊在一起，制造出词表里不存在的假词。

### 28.2 用语料自身的词表授权合并

改为由**词频**而非字形决定，判定顺序：

1. 合并形在词表中 ≥20 次且带连字符形从未出现 → **合并**（这条必须最先，否则 `ribo- some` 会被下一条误挡）；
2. 后半截是功能词（`your` `the` `into` `may` …）→ **不动**（双栏交错的特征）；
3. 带连字符形比合并形更常见 → **保留连字符**；
4. 合并形出现 ≥3 次 → **合并**；
5. 两种形式都不在词表 → **不动**。

词表从 18 册教科书自身构建：63,634 个词、12,241 个带连字符复合词（各取频次 ≥3）。在全部 8,880 处断行连字符上的裁定：

| 裁定 | n | 占比 | 实例 |
|---|---:|---:|---|
| 合并（断开的词） | 8,181 | 92.1% | `para- urethral`、`temporo- mandibular`、`ter- ritory`、`ret- roviral` |
| 不动（两种形式都不在词表） | 407 | 4.6% | `box- shaped`、`high- glyceraldehyde`、`per- organelles` |
| 保留连字符（真复合词） | 220 | 2.5% | `cell- mediated`、`high- density`、`outward- open` |
| 不动（功能词，双栏交错） | 72 | 0.8% | `sin- your`、`com- into`、`in- the`、`re- may` |

第 2 行是保守漏修（`box- shaped` 理想应变成 `box-shaped`），无害；第 4 行是正确拦截，正是 28.1 里那类错误。

除断词外还做四件：连字 `ﬁ ﬂ ﬀ ﬃ ﬄ` 展开、软连字符归一、页码引用 `(p. 184)` 剥离、DSM-5 的编码噪声 `P?PF'JNT'` 剥离。

### 28.3 它对判据值多少：14.9%

| | n | 占比 |
|---|---:|---:|
| 全语料 chunk | 125,847 | — |
| 规范化改动了内容的 chunk | 6,582 | **5.23%** |
| 陈述判据集 / 宣告列表的 chunk | 718 | 0.57% |
| 　其中规范化改动了内容 | 169 | 23.5% |
| 　**其中改动落在判据句及其成员的跨度内** | **107** | **14.9%** |

最后一行才是对判据的直接贡献。判据段落被规范化触及的比例（23.5%）明显高于全库平均（5.23%），说明判据段落本身的 OCR 噪声更密集——判据往往出现在表格、缩写、多音节术语附近，正是断词与连字的高发区。但其中只有 14.9% 的损伤真正落在判据句上，其余改的是同一块里别处的噪声。

**因此规范化对 textbooks 判据的可恢复贡献是 718 条中的 107 条。**它便宜、无风险、可以只在抽取输入端做而不动语料，但它不是杠杆。

### 28.4 与 §26.4 的交叉验证：成员丢失率确实约为 0

§26.4 是在拼回的全文上测的（1,262 处宣告，±1 窗口覆盖 99.8%）。本节换一个角度，在**未拼接的 chunk 上**定位成员位置，用严格与宽松两种判据给出双界：

| 成员在哪 | 严格（编号/项目符号/短逗号列表） | 宽松（额外接受散文化列表） |
|---|---:|---:|
| 同一 chunk 内 | 47.1% | **71.3%** |
| 仅在后 1–2 个 chunk | 21.3% | **28.3%** |
| 附近找不到 | 31.6% | **0.4%（3 条）** |

两者的差额（31.6% → 0.4%）度量的是**PDF 抽取把列表变成了散文：条目边界没了，条目本身在**。例如：

> `Assessment of myocardial and valve function is obtained in the following ways:`
> 下一 chunk：`ECG/EKG (electrocardiography)—a series of electrical traces taken around the long and short axes of the heart that reveal heart rate and rhythm ...`

宽松判据下剩余的 3 条也逐条读过，成员同样都在后一个 chunk（如 Robbins 的 `Mechanisms of liver injury include the following:` 后接 `Stimulation of collagen formation ... DNA damage by reactive oxygen species ...`）。**真丢失为 0**，与 §26.4 从另一条路得到的 99.8% 覆盖率一致。

这也顺带校正了本节自己第一版的两个测量错误，记录在此以免复用：其一，判据检测器把 `all of these defects produce a left-to-right shunt` 这类回指误判为判据集，抽查 10 条里有 4 条属此，收紧为要求「these」后接判据类名词后，判据段落数从 2,018 降到 718；其二，比较 `norm(span) != span` 时没有对基线施加同样的空白压缩，导致「损伤落在判据句内」一度算出 25.1% 这个大于总改动率 10.7% 的自相矛盾值。

### 28.5 对 textbooks 处置的最终表述

| 手段 | 覆盖 718 条判据段落中的 | 是否推荐 |
|---|---:|---|
| 字符级规范化（本节） | 14.9% | ✓ 做，成本极低，可在抽取输入端完成 |
| 相邻 chunk 缝合 | 28.3% | 已由检索的 ±1 窗口覆盖（§26.4：99.8%），无需新做 |
| 散文列表的条目切分 | 大部分 | 归入 §24.6 的段落级成组作用域，属抽取侧改造 |
| 重新装配后按结构重切 | — | ✗ 不做（§26.4：仅剩 2 处，不足以支撑索引重建） |
| 重取 PDF 重做抽取 | ≈ 0% | ✗ 不需要，内容没丢 |

即：textbooks 侧只剩两件事——**输入端字符规范化**，和**把散文化列表的切分责任交给抽取侧**。语料本身不必再动。

### 28.6 本节产物

| 文件 | 内容 |
|---|---|
| `normalize_textbooks.py` | 词表守卫的规范化实现（`--write` 输出 `textbooks_chunks_normalised.jsonl`）；断词裁定分布、判据子集的改动率、成员位置的严格/宽松双界 |
| `textbooks_normalisation_audit.json` | 上述全部计数 |
| `textbooks_vocab.json` | 从 18 册自身构建的词频表（63,634 词 + 12,241 复合词） |

## 29 三个语料的入库修复落地：量词与成员重新回到同一个 chunk

§25–§28 把「复合判据丢在哪」定位到了入库环节而非抽取环节。本节执行修复，按 StatPearls → pmc_oa 本地三项 → textbooks 规范化的顺序，pmc_oa 的 JATS 重取留到最后再评估。

所有产物都写到**新文件**，不覆盖现行索引所依赖的语料，以便新旧两套并存对比。

### 29.1 判定修复成败的指标

chunk 数、字符数这些都不是目标。真正的目标只有一个：**一句「至少满足以下 3 条」到达抽取器时，它的成员在不在同一个 chunk 里**。成员不在，`at_least_n` 就无从谈起，抽取器再准也造不出这个组。

`verify_corpus_repair.py` 因此只测两件事：

- `intact` —— 一个宣告了枚举的 chunk（`……following/criteria/features：`结尾），后面是否带着 ≥2 个可信成员；
- `q_intact` —— 一个明确写了数量的 chunk（「3 or more of the following」），成员数是否够得上它自己声明的那个数。

| 语料 | | chunk | 宣告枚举 | intact | 声明数量 | q_intact |
|---|---|---:|---:|---:|---:|---:|
| statpearls | 修前 | 367,799 | 11,513 | 0 (0.0%) | 224 | 0 (0.0%) |
| | 修后 | 411,552 | 11,602 | **10,369 (89.4%)** | 227 | **209 (92.1%)** |
| pmc_oa | 修前 | 317,710 | 1,051 | 0 (0.0%) | 25 | 0 (0.0%) |
| | 修后 | 320,197 | 2,001 | **887 (44.3%)** | 45 | **18 (40.0%)** |
| textbooks | 修前 | 125,847 | 89 | 0 (0.0%) | 8 | 0 (0.0%) |
| | 修后 | 125,847 | 90 | 0 (0.0%) | 8 | 0 (0.0%) |

修前三个语料一律是 0——不是测量口径的问题，是**全库没有任何一个 chunk 同时装着量词和它的成员**。§22 观察到的「引擎只会加权求和」，在语料这一层就已经注定了。

> ⚠ pmc_oa 的 44.3% 不可单独引用：§30.4 实测发现其中 23.8% 是综述自己的**文献纳排标准**而非诊断判据，折算后真正与诊断相关的恢复量在 200–250 个量级而非 887。StatPearls 不受此影响。

### 29.2 StatPearls：漏标签之外，还漏了文章号

§25 定位的 bug 是 `sec.findall("p")` 只取 `<sec>` 的直接 `<p>` 子元素，而 `<list>` 是 `<p>` 的兄弟节点，`<list-item>` 里的 `<p>` 也不是 `<sec>` 的直接子元素，于是整棵列表子树从未被访问。

修法是改为**按文档顺序遍历 `<sec>` 的直接子元素**，并且把列表**接回宣告它的那句话**：冒号引导句先挂起，遇到紧随的 `<list>` 就合并成同一个 chunk；条目一行一条、前置项目符号；嵌套 `<list>` 用缩进保留层级，因为「大标准里套小标准」正是原文写二阶判据集的方式。

> ⚠ §32.4 更正：一行一条的渲染是为**生产 KG 管线**的 `_looks_list`／`LEAD_IN` 检测器服务的，**试验管线不经过它**（`run_trial_extraction.py` 直接把 chunk 原文送 LLM）。对试验管线，本次修复的收益全部来自「量词与成员共处同一 chunk」这一可见性改善，与是否有项目符号无关；而多行渲染与提示词里的 `one sentence` 限制存在潜在冲突，须先改提示词。`<table-wrap>` 单独成 chunk。合并后超过 6,000 字符则拆开，避免一张长列表把整节吞成一个 chunk。

修的过程中发现第二个 bug：脚本找的是 `<article-id pub-id-type="bookaccession">`，但这份档案用的是 **BITS DTD 而非 JATS article DTD**，根本没有这个元素。真正的标识符在 `book-part-wrapper/@id`。后果是此前 367,799 个切片的 `article_id` **全为空**，`id` 全都是 `_p0`、`_p1`……**在 9,638 篇文章之间互相碰撞**。改用 `root.get("id")` 后 id 恢复唯一。

效果：

| | 修前 | 修后 |
|---|---:|---:|
| chunk | 367,799 | 411,552（paragraph 84.7% / list 14.8% / table 0.4%） |
| 正文字符 | 166.9 M | 192.2 M（+25.3 M） |
| 以冒号结尾（悬空） | 21,404（5.82%） | 2,507（**0.61%**） |
| 含项目符号 | 13（0.00%） | 61,129（14.85%） |

§24 那个作为全篇引子的例 74 代谢综合征判据，现在完整落在一个 chunk 里：

> `The diagnosis of metabolic syndrome requires the presence of 3 or more metabolic abnormalities:`
> `• A waist circumference of more than 40 inches in men and 35 inches in women`
> `• Serum triglycerides level of 150 mg/dL or greater`
> `• Reduced high-density lipoprotein cholesterol, less than 40 mg/dL in men or less than 50 mg/dL in women`
> `• Elevated fasting glucose of l00 mg/dL or greater`
> `• Blood pressure values of systolic 130 mm Hg or higher or diastolic 85 mm Hg or higher`

残余的 0.61% 抽样读过，主要是引导句后面跟的是**嵌套 `<sec>`**——子章节标题本身充当列表成员。这是另一种结构，不在本次修法范围内。

### 29.3 pmc_oa：先量盘子，再决定造多大的机器

§26 给 pmc_oa 列了三项本地可做的修复。动手前先用 `measure_pmc_repair.py` 扫全部 5,869 份 BioC 缓存，量各自的规模——结果和事先的排序完全不同：

| 修复项 | 规模 | 结论 |
|---|---:|---|
| 表格被压平 | 14,292 个 table passage，**单行率 100%**，其中 14,290 个带 `infons["xml"]` | 最大且结构 100% 可本地还原 |
| 长度下限砍掉的 passage | 65,750（对比保留 315,149） | 一刀放宽会灌进 6.6 万条杂讯 |
| ……其中位于枚举宣告之下的 | 1,357 | 这才是判据相关的部分 |
| 邻接列表 | 948 组宣告、7,264 个条目 | 中等 |

三点据此定了做法：

**表格。** BioC 的 `text` 字段把整张表的所有单元格用 tab 拼成**一行**，行边界全丢。但 `infons["xml"]` 原样保留了 JATS `<table>` 源码——不联网就能还原网格。`render_table_xml()` 重新渲染为行换行、单元格 tab 分隔，并把 `<break/>` 转空格。效果是带行结构的表格从 **0/12,368 变成 12,781/12,895**。

**长度下限。** 不做一刀切放宽。`should_keep_chunk` 增加 `in_criteria_run` 参数，只对「位于枚举宣告之后的成员」把下限从 60/30 降到 12，并让它绕过 `background` 分类的丢弃。这样只召回 1,357 条判据成员，而不是 65,750 条杂讯。

**邻接列表。** BioC **没有 `list` passage 类型**，PMC 把每个 `<list-item>` 都压成普通 `paragraph`，量词与成员之间只剩「相邻」这一条线索。第一版用「冒号 + 后随短段落」的朴素规则，抽样立刻暴露问题：大量文档的引文块和出处行完全符合这个形状（`……impacting their lives:` 后跟一串引号开头的短段）。改用 §24 的 `ANNOUNCE` 正则，要求冒号前出现 following / criteria / features 一类枚举名词，抽样精度即达到可用；run 的终止条件则用引号开头、超长、以及「标记一致性」（列表若显式带标记，后续条目必须也带）三重判据。

run 的**结尾**仍然收不干净，会吞进列表后的第一两句正文。这里的处置是**让合并块作为新增 chunk 而非替换**：`criteria_block` 与原有各段并存，于是边界判错只造成少量冗余，不会丢内容。代价是 +881 个 chunk（+0.3%）。

综合结果：

| | 修前 | 修后 |
|---|---:|---:|
| chunk | 317,710 | 320,197 |
| 多行 chunk | 917（0.29%） | 14,579（**4.55%**） |
| 带行结构的表格 | 0 / 12,368 | **12,781 / 12,895** |
| `criteria_block` | — | 881 |

`intact` 只到 44.3%，明显低于 StatPearls 的 89.4%。这是 BioC 这一层的信息损失所决定的上界：结构在 PMC 转 BioC 时就已经抹掉，靠邻接只能猜回一部分。要越过这条线只能走 JATS 重取，那需要联网，按计划留到最后评估。

### 29.4 textbooks：规范化做了，但它治不了这里的病

`normalize_textbooks.py --write` 已落盘 `textbooks_chunks_normalised.jsonl`。词表守卫的断词裁定分布与 §28 一致：92.1% 判为断词并合并，2.5% 判为真复合词而保留连字符，4.6% 两种形式都不在词表故不动，0.8% 因后半是虚词（分栏交错）而不动。全库 5.23% 的 chunk 有改动，718 条判据段落中 23.5% 有改动、14.9% 的改动落在判据句内。

但 29.1 的表里 textbooks 修前修后都是 **0%**，这不是规范化失败，而是**它本来就治不了这个病**。textbooks 是 OCR 后按固定窗口预切的纯文本，判据列表被渲染成没有任何换行或标记的散文，`intact` 检测器（找换行、项目符号、分号序列）根本看不见它们。§28.4 从另一条路测得的数才是这里的真相：宽松判据下 71.3% 的成员在同一 chunk、28.3% 在后 1–2 个 chunk，**真丢失为 0**。

所以 textbooks 的结论维持 §28.5 不变：内容没丢，缺的是结构；字符规范化拿到它能拿的 14.9%，其余归**检索的 ±1 窗口缝合**（§26.4 已覆盖 99.8%）和**抽取侧的散文列表切分**（§24.6 的段落级成组作用域），语料本身不必再动。

### 29.5 索引重建成本

`build_trial_index.py` 加了 `--v2` 开关，指向修复后的三个语料，产物写入 `data/corpus/ceiling_trial_index_v2/`，与现行索引并存以便同任务对比。

| | 现行 | v2 |
|---|---:|---:|
| chunk | 861,131 | 907,371（+46,240，+5.4%） |
| TF-IDF | — | 190,050 词表，nnz 37.7 M，56 s |
| dense（MiniLM-L6，cuda:0） | — | ≈2,450 chunk/s，约 6 min |
| 磁盘 | 1.1 G | ≈1.2 G |

重建总耗时约 8 分钟，成本可忽略。构建时踩到一个与本任务无关的环境问题记录在此：`~/.bashrc` 里 `PYTORCH_CUDA_ALLOC_CONF=max_split_size_mb:4`，而 torch 要求该值 > 20，任何 CUDA 初始化都会直接抛 `RuntimeError`；构建时以 `max_split_size_mb:128` 覆盖。

### 29.6 尚未回答的问题

修复只保证「量词和成员到达抽取器时在一起」。**抽取器是否因此真的多产出 `at_least_n` / `all` 组、§23.2 那个 0.617 的 logic 分布失真度是否收窄、下游 top-1 是否变化**——这三件事都还没测，需要在 v2 索引上重跑抽取与试验才能回答。在拿到那组数之前，本节的成果只应表述为**语料侧的必要条件已经满足**，不能表述为复合判据问题已解决。

> §34 已结算前两件：跨行成组率 6.9%→19.4%（旧提示词，只换索引，p=4.6e-10），`at_least_n` 占比与 logic 保真率同向上升，同索引内 TVD 下降。第三件（下游 top-1）仍未测。

pmc_oa 的 JATS 重取按计划留到最后：它要联网、要重跑 5,869 篇，而它能买到的只是 pmc_oa 从 44.3% 往上的那一段，而 pmc_oa 的判据宣告总量（2,001）本就只有 StatPearls（11,602）的 17%。是否值得，等 v2 索引上的抽取结果出来再判。

> 更新：不必等了。§31 用 BioC offset 连续性证明 pmc_oa 的成员文本基本没丢（无处可寻的仅 0.6%），JATS 重取只能买到列表边界这层元数据，**已判定放弃**。

### 29.7 本节产物

| 文件 | 内容 |
|---|---|
| `scripts/build_statpearls_corpus.py` | 改为按文档顺序遍历，恢复 `<list>`/`<list-item>`/`<table-wrap>`，列表接回引导句，修 BITS 文章号 |
| `scripts/pmc_oa_ddx_common.py` | `find_criteria_runs()` 邻接列表重建、`render_table_xml()` 表格还原、`should_keep_chunk(in_criteria_run=)` 定向放宽长度下限 |
| `scripts/rechunk_pmc_oa_offline.py` | 纯离线重切（原 `rechunk_pmc_oa.py` 会在缓存缺失时回落到 HTTP，且会并入现行 chunk 文件） |
| `measure_pmc_repair.py` | 动手前的三项规模测量 |
| `verify_corpus_repair.py` | 三语料修前/修后的 `intact` / `q_intact` 对照 |
| `build_trial_index.py --v2` | 在修复后语料上重建试验索引 |

## 30 被长度下限砍掉的 65,750 个 passage 里到底有什么

§29.3 决定「不一刀放宽长度下限」时，理由只是「65,750 太多，会灌进杂讯」——这是个未经检验的断言。本节检验它，并顺带查出一个会削弱 §29.3 结论的问题。

### 30.1 光有命中率没有意义，必须有对照

「其中多少能被候选疾病名命中」这个问题不能直接回答。被丢弃的 passage 中位长度只有 **20 字符**（p90 = 49，均值 23），而保留的均值是 **735 字符**——短文本命中疾病名的机会本来就低几十倍，拿两者直接比会得出「丢弃的没价值」这个正确结论，但理由是错的。

因此设了三重对照（`audit_dropped_passages.py`，候选词表取自 `trial_tasks_all789.json` 的 789 例全部候选与金标，清洗掉 `PE`/`MI`/`TB` 一类高歧义缩写和 `cancer`/`infection` 一类泛词后得 8,822 个疾病名）：

| | 命中候选疾病名 |
|---|---:|
| 被丢弃的 65,750 条 | **3.78%** |
| 长度匹配对照（从保留段落里裁同长度的随机窗口） | **1.71%** |
| 保留的 315,149 条（未做长度匹配） | 30.35% |

也就是说，在**扣除长度效应之后**，被丢弃的文本命中疾病名的概率只有背景水平的 2.2 倍，绝对值 3.78%。这不是「富含疾病信息的文本被误杀」应有的样子——真被误杀的判据成员，命中率应当远高于同长度的随机窗口。

### 30.2 命中疾病名 ≠ 有效信息

3.78% 里还要再扣两层：

| 判据 | 条数 | 占 65,750 |
|---|---:|---:|
| 命中候选疾病名 | 2,486 | 3.78% |
| 文本已经出现在**同文章某个保留段落之内** | 18,797 | **28.59%** |
| 带任何临床词（剂量单位、检查、阳性/阴性、升高/降低……） | 3,038 | 4.62% |
| **同时**命中疾病名**且**带临床词 | **211** | **0.32%** |
| 是综述自己的文献纳排标准 | 1,145 | 1.74% |

关键是最后那个 0.32%：**65,750 条里，同时携带一个候选疾病名和一个临床词的只有 211 条**。而且其中还有一部分被 28.59% 那一行覆盖（文本原样出现在同文章的保留段落里，丢了也没丢）。211 就是「有效信息」的**上界**，真值更低。

### 30.3 它们实际上是什么

按形态分桶后一目了然：

| 形态 | 条数 | 占比 | 命中疾病名 |
|---|---:|---:|---:|
| 章节标签／缩写词表条目 | 40,532 | **61.6%** | 3.62% |
| 零散片段（图注尾、脚注、单位说明） | 14,702 | 22.4% | 5.54% |
| 声明式样板 | 5,693 | 8.7% | 0.26% |
| 纯数字／编号片段 | 2,289 | 3.5% | 1.27% |
| 位于枚举宣告之下的成员 | 1,284 | 2.0% | 4.83% |
| 临床散文片段 | 1,250 | 1.9% | 7.76% |

抽样实读（`dropped_passage_sample.md`）证实了这个分布：

- 章节标签：`Methods`、`Conclusion`、`Background and Objective`、`OA`、`WBV`
- 缩写词表：`AC Adenocarcinoma, SCC Squamous cell carcinoma`、`VATS, video-assisted thoracoscopic surgery`——这类会命中疾病名，但它是词表条目，不是命题
- 样板：`Not applicable.`（重复数千次）、`The authors declare no conflict of interest.`
- 编号片段：`Fig. 2`、`10.1371/journal.pone.0292800.r006`、`11. or/9-10`

第一类之所以命中率不低（3.62%），正是因为缩写词表逐条列疾病名——**命中疾病名恰恰是它没有诊断价值的原因，而不是有价值的证据**。

所以 §29.3「不一刀放宽」这个决定是对的，而且理由比当初写的更强：不是「怕灌进杂讯」，是**丢弃集里的有效信息上界只有 211 条（0.32%），其中还有近三成本来就没丢**。

### 30.4 但这个审计查出了一个反过来削弱 §29.3 的问题

上表里 2.0% 那一桶（1,284 条位于枚举宣告之下的成员）正是 §29.3 用 `in_criteria_run` 定向召回的那批。逐条读下来，它们大多**不是诊断判据**：

> `Papers without full text;`　`This study did not contain descriptive reviews.`
> `Studies that relate to the management of existing PIs only.`
> `Inclusion criteria and exclusion criteria`
> `* All references, tables, and figures are properly cited`　`3. Write your Python code in the file.`

这些是**综述自己的文献筛选标准**，甚至是投稿清单。原因很直接：pmc_oa 这批语料是按「approach to / differential diagnosis of / evaluation of」检索出来的**综述文章**，而综述的 Methods 一节必然写「研究纳入需满足以下标准：」——它在文本形态上和「诊断需满足以下 3 条」完全一致，`ANNOUNCE` 正则分不开。

回头查 §29.3 恢复的 881 个 `criteria_block`，污染程度是实测的：

| | 条数 | 占 881 |
|---|---:|---:|
| 是综述自己的文献纳排标准 | 210 | **23.8%** |
| 命中候选疾病名 | 277 | 31.4% |
| 命中疾病名**且**不是文献纳排标准 | 228 | **25.9%** |

即 881 个 `criteria_block` 里，只有约 **1/4** 既涉及候选疾病又不是文献筛选标准。而且抽样看，这 228 条里仍有相当部分是综述式表述（`possible side effects could include the following`、`screening conditions for LPS-induced depression in mice`），离「诊断判据集」还有距离。

**因此 §29.1 表中 pmc_oa 的 44.3% `intact` 必须重新表述**：那个数衡量的是「宣告的枚举拿回了成员」这一机械事实，它**不等于**拿回了 887 个诊断判据集。按 25.9% 折算，pmc_oa 侧真正与诊断相关的判据集恢复量在 **200–250 个**量级，而不是 887。这不改变 §29.6「pmc_oa 的 JATS 重取优先级低」的判断，反而加强它：pmc_oa 这批综述语料的判据密度本身就比 StatPearls 低得多。

StatPearls 不受此影响——它是疾病条目式的临床参考书，没有「文献纳入标准」这一节；`q_intact` 92.1% 那一栏（明确写了数量的判据集，成员数够得上声明的数）也是更硬的指标。

### 30.5 结论与待办

1. **长度下限维持定向放宽，不做一刀切**——丢弃集有效信息上界 0.32%，理由已实测，不再是猜测。
2. `criteria_block` 需要加一道**文献纳排标准过滤**（`STUDY_CRITERIA` 正则已实现并测过，在 881 条上召回 23.8%），否则这批噪声会以「判据集」的身份进入抽取器，而它们恰恰长得最像判据。这一步应在 v2 索引上重跑抽取**之前**做掉。
3. 同一个过滤器也应回头作用于 §23 的 logic 分布统计——那里的 `any`/`at_least_n` 计数同样没有区分诊断判据和文献筛选标准，§23.2 那个 0.617 的失真度可能因此被高估。

### 30.6 本节产物

| 文件 | 内容 |
|---|---|
| `audit_dropped_passages.py` | 丢弃集的长度分布、三重对照命中率、同文章覆盖检验、形态分桶、抽样转储；候选词表用 n-gram 集合查表（相对 25 万字符正则轮扫提速约 30 倍） |
| `dropped_passage_audit.json` | 上述全部计数 |
| `dropped_passage_sample.md` | 按形态分组的抽样，供手读 |

## 31 pmc_oa 的缺失是真缺失还是结构损坏

§29.6 把「pmc_oa 的 JATS 重取值不值」挂了起来，理由是要等抽取结果。其实有个更前置的问题可以先答，而且答完就不必等了：**成员到底是从语料里消失了，还是还在、只是结构被压平了？** 前者只能联网重取，后者是抽取侧的事，输入侧已经到顶。

### 31.1 判定证据：BioC 的 passage offset

BioC 每个 passage 带 `offset`，指向原文档的字符位置。实测这些 offset **连续铺满**原文：正常间隔 +1，偶尔 +3/+9/+21，来自被剥掉的行内引文标记。

于是有一个不需联网的判定：**一个宣告枚举的段落之后，如果到下一个 passage 存在大段 offset 空洞，说明 BioC 对原文中存在的文字没有输出任何 passage——那是真缺失；如果 offset 严丝合缝，成员就还在，绑不上它只是结构问题。**

实测（`audit_pmc_loss_kind.py`，全部 5,869 份 BioC，8,486 个枚举宣告）：

> 悬空宣告之后的 offset 空洞：**中位数 1，p90 = 3，最大 49**

最大值 49 都还在引文标记剥离的量级内。**BioC 这一层基本没有丢字。**

### 31.2 成员实际在哪

| 宣告的去向 | 条数 | 占 8,486 |
|---|---:|---:|
| **成员就在同一段落里，写成散文** | 5,080 | **59.9%** |
| 宣告后只跟很短的尾巴（交叉引用、1–2 项） | 1,896 | 22.3% |
| 冒号结尾、成员不在本段（悬空） | 1,510 | 17.8% |

近六成的宣告**根本不是悬空的**——冒号后面的成员就在同一个 passage 里，只是以散文形式（分号、`and/or` 串联）书写，没有任何列表结构。这正是 §28 给 textbooks 下的判断，只不过 textbooks 是 OCR 压平的，pmc 是原文本来就这么写。

再拆那 1,510 个真正悬空的：

| | 条数 | 占 1,510 | 内容在不在 |
|---|---:|---:|---|
| 邻接重建已拿回（§29.3） | 742 | 49.1% | 在 |
| 成员在，但被我的绑定规则拒了 | 436 | 28.9% | 在 |
| 后面紧跟章节标题 | 290 | 19.2% | 见下 |
| 成员在表格／图注里 | 39 | 2.6% | 在（§29.3 已重渲染） |
| **offset 空洞（疑似真缺失）** | **2** | **0.1%** | 手查后见下 |
| 文档结束 | 1 | 0.1% | — |

三处需要逐条落实：

**那 2 个 offset 空洞逐条手查，都不是缺失。** 一个是 `The following criteria were used to identify articles...`，空洞 49，但下一段就是 `(1) Patients who underwent DTI`——成员在，空洞来自别处；另一个是 `...using the following formula:`，丢的是数学公式（公式在 JATS 里是 MathML／图片，本就不产出文本），与判据无关。

**290 个「后跟章节标题」里，84.1%（244 个）的那个标题本身就是第一个成员。** 例如 `Other miscellaneous causes associated with myopathy include:` → `2.6.1 Sarcoidosis`，`...the most frequently described genes include (Table 2):` → `b) Impaired androgen action`。这和 §29.2 里 StatPearls 残余 0.61% 是同一形态：**成员被渲染成了子章节标题**。只有 46 个（15.9%）后面跟的是 `Discussion`／`Methods` 这类文章骨架标题，才算真的悬在那里。

**436 个「成员在但被拒」，纯粹是我的启发式太紧。** §31.1 里那个 PA 的例子最典型：

> `In brief, the diagnostic management of PA comprises three steps:`（off=8710, len=64）
> → `Screening : PA is biochemically suspected by an increased ratio of PAC to PRA...`（off=8775）
> → `Confirmation : Lack of response to suppressive maneuvers...`（off=9071）
> → `Subtype differentiation : Computerized tomography (CT) with an adrenal protocol...`（off=9475, len=822）

三个成员齐全、offset 逐段相接，是一组货真价实的临床判据；被拒只因第三段 822 字符超过了 `MAX_ITEM_CHARS = 400`。拒绝原因分布与放宽阈值的收益：

| 拒绝原因 | 条数 | | 首个成员长度上限 | 可容纳 |
|---|---:|---|---|---:|
| 下一段太长 | 221 (50.7%) | | ≤ 400（现值） | 49.3% |
| 只有 1 个成员就遇到标题 | 82 (18.8%) | | ≤ 600 | 71.3% |
| run 中途遇到超长段 | 68 (15.6%) | | ≤ 900 | 86.7% |
| 尺寸突变 | 44 (10.1%) | | ≤ 1400 | 95.9% |
| 下一段以引号开头 | 14 (3.2%) | | ≤ 2500 | **99.3%** |
| 标记不一致 | 7 (1.6%) | | | |

### 31.3 结论

**pmc_oa 的缺失是结构损坏，不是真缺失。** 8,486 个宣告里，成员确实无处可寻的只有约 49 个（46 个悬在骨架标题前 + 2 个 offset 空洞 + 1 个文档末尾），**0.6%**。

这直接回答了 §29.6 挂起的问题：**JATS 重取买不到内容，可以放弃**。它唯一能买到的是「列表标签」这一层元数据（`<list>`／`<list-item>` 的边界），而 §31.2 表明成员文本本身一个都没少。用一次全量联网重取换一层可以用邻接和标点推断的边界标注，不划算。

但用户提问里「输入侧不再能解决」这半句，对 pmc 只**部分**成立，需要分开说：

| 占 8,486 | 归谁修 | 理由 |
|---|---|---|
| 59.9% 散文内联 | **抽取侧（提示词）** | 成员就在同一段落里，LLM 本来就读得到；卡住它的是提示词的 `one sentence` 限制，不是散文难解析（§32.3） |
| 22.3% 短尾 | 抽取侧（提示词） | 同上 |
| 5.1%（436/8,486）成员被拒 | **输入侧仍可修** | 阈值放宽到 2,500 可覆盖 99.3%，改一个常数的事 |
| 2.9%（244/8,486）成员是子标题 | **输入侧仍可修** | 把内容型子标题当作成员，与 §29.2 StatPearls 残余同解 |
| 0.6% | 无解，也不值得 | — |

即：pmc 的输入侧**还没到顶**，还有约 8% 的宣告可以靠改绑定规则（放宽长度上限 + 子标题当成员）拿回来，这比 JATS 重取便宜得多；但主体（82%）确实只能交给抽取侧的散文兼容。textbooks 是输入侧已到顶，pmc 不是——这两者不能一概而论。

### 31.4 一个必须同时记住的折扣

§30.4 的结论在这里同样适用，而且更重：**8,486 个宣告里 28.0%（2,377 个）是综述自己的文献纳排标准**。上面所有比例都没有扣除这一项。也就是说「靠改绑定规则再拿回 8%」这个收益，按诊断相关性折算后应再打约七折。这不改变结论的方向（结构损坏、JATS 不值得），但会进一步压低 pmc_oa 相对 StatPearls 的优先级。

### 31.5 本节产物

| 文件 | 内容 |
|---|---|
| `audit_pmc_loss_kind.py` | 用 BioC offset 连续性判定真缺失；宣告去向的完整分类；绑定规则拒绝原因与阈值放宽收益曲线 |
| `pmc_loss_kind_audit.json` | 上述全部计数 |
| `pmc_loss_kind_sample.md` | 各类别抽样，含 2 个疑似真缺失的原文，供手查 |

## 32 抽取侧靠规则还是靠 LLM：散文与列表的差别到底在不在

§29–§31 一路把「复合判据丢失」归到语料结构上，但有个前提一直没验：**抽取侧是怎么决定 `all`/`any`/`at_least_n` 的？** 如果是 LLM 读段落自己判断，那只要内容完整进窗口，散文和带项目符号的列表对它应当没有本质差别，前面几节强调「恢复列表结构」的部分就需要重新归位。

结论：**是纯 LLM，没有任何规则参与逻辑类型的判定**；因此「散文 vs 列表」确实不是瓶颈，但**不等于没有瓶颈**——真正卡住的是提示词里的一句话。

### 32.1 仓库里有两条管线，不能混为一谈

| | 生产 KG 管线 | RAG 机械试验管线（§22–§31 全部基于它） |
|---|---|---|
| 入口 | `build_guideline_kg_claim_windows.py` → `extract_guideline_kg_residuals.py` | `run_trial_extraction.py` |
| 逻辑字段 | `logic_operator`：`atomic`/`and`/`or`/`k_of_n`/`sequence` | `criterion_group.logic`：`all`/`any`/`at_least_n` |
| 输入 | 经分块的 claim window | **检索到的 chunk 原文** |
| 模型 | `deepseek-v4-flash`，strict JSON schema | `llama-3.3-70b-instruct`，自由 JSON |
| 是否依赖列表结构 | **是**（`_looks_list`／`_line_spans`／`LEAD_IN`） | **否** |

§22 以来讨论的 `all`/`any`/`at_least_n` 全部属于试验管线。

### 32.2 试验管线：LLM 直接填，规则只做事后改写

送进模型的就是检索命中的 chunk 原文，中间没有任何分块或列表检测：

```531:531:analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL/run_trial_extraction.py
                passage = p["text"][: args.max_passage_chars]
```

（`--max-passage-chars` 默认 6000。）逻辑类型由提示词让模型自己填 `criterion_group.logic`，**没有任何 Python 规则从文本判定 `all`/`any`/`at_least_n`**。

规则只在事后改写已有的组，不产生新的逻辑判断：`gate_assertions.py` 的 E9 把命中 `some or all` 的 `all` 改成 `any`（666–672 行），以及把同一 quote 下被拆成多条 `required_for` 的断言合并成一个 `any` 组（`_merge_and_or_required`，773–805 行）。

**所以「散文 vs 结构化列表」这个区分，对试验管线本身是不成立的**——模型读的是同一段文字，有没有项目符号不改变它能否读到成员。这一点用户的判断是对的。

### 32.3 但提示词里有一句硬限制，而且实测生效

提示词对成组的适用范围写死在单句内：

> `Criterion groups: when **one sentence** lists several findings that together form ONE diagnostic criterion set, emit one assertion per member and give all members the same group_id...`

§24.2 已经从语料侧量过这条规则的覆盖率：**量词与成员同处一句的只占 12.3%**。现在从产物侧做对侧验证——把已有抽取结果里每个组的成员 quote 拿出来，看它们在原文里跨不跨句、跨不跨行（`audit_group_span.py`）：

| 组内成员 quote 的分布 | k30all4（548 组） | pool6k30all4（220 组） |
|---|---:|---:|
| 多条 quote，同一句内 | 69.8% | 75.5% |
| 单条 quote，单句 | 26.4% | 21.3% |
| **多条 quote，跨句** | **3.6%** | **3.2%** |
| **跨行（多行）** | **0** | **0** |

**96.4% 的组在单句内形成，跨句只有 3.6%，跨行为 0。** 模型确实在服从这条限制。这就是复合判据成组率低的直接原因，而它是一个提示词字符串，不是语料属性，也不是模型能力问题。

顺带两个数据质量问题：组内断言只占全部断言的 6.1–6.9%；`logic` 字段里混有 `and`、`typical`、字面字符串 `"null"` 等非法值（自由 JSON 无 schema 约束所致，生产管线用 strict JSON schema 就没有这个问题）。

### 32.4 那 §29 的语料修复还算不算数

算，但**理由要换**，而且我在 §29.2 写的一条justification是错的。

**仍然成立的（而且是主要收益）：共处同一检索单元。** 量词与成员必须同时进入送给模型的那段文字，否则改提示词也没用。§29.1 测的 `intact`（0% → 89.4%）衡量的正是这件事，它与散文/列表之分无关，是**可见性**问题。

> ⚠ §33.1 更正：这里原写「模型一次只看一个 chunk」，是错的。检索返回的是 gid±1 三个 chunk 的拼接（`TrialRetriever.passage(window=1)`），所以「检索单元」是三 chunk 窗口而非单 chunk。但对 StatPearls 这不改变结论——它的列表成员根本没有入库，窗口无从缝起（§33.6）。

**需要更正的：§29.2 说列表条目一行一条渲染是「让下游 `build_guideline_kg_claim_windows.py` 的列表检测器看得见」。** 那个检测器属于**生产 KG 管线**，试验管线根本不经过它。对生产管线这句话是对的（它确实用 `_looks_list`/`LEAD_IN` 把引导句和列表合并成不可分的 `criteria_*` 块，且其提示词明确允许 evidence unit 含 bullets 和多句）；对试验管线，换行至多是中性的。

**而且存在一个我引入的新风险，必须在重跑前处理。** 提示词说「one sentence」，而我在 §29.2 把列表渲染成了多行——一个带项目符号的多行列表**不是一句话**。既然实测跨行成组率为 0，那么把原本挤在一行里的散文列表拆成多行，有可能反而让模型**更不愿意**成组。修复语料在这条提示词下不一定能兑现成组，甚至可能倒退。

### 32.5 由此改变的行动顺序

原计划是「在 v2 索引上重跑抽取，看 logic 分布失真度是否收窄」。这个顺序现在是错的：**先改提示词，再重跑**，否则测到的将是提示词限制，而不是语料修复的效果，且两者混在一起无法归因。

具体三步，成本都极低：

1. **删掉 `one sentence` 限制**，改为「一个引导句加其后的成员行、或一段散文内的枚举，都算一个判据集」，并显式说明成员可以跨行、跨句。这是 §24 结论 3 说的「四者中最便宜的一条」，至今未做。
2. **给 `criterion_group.logic` 加枚举校验**，把 `and`/`typical`/`"null"` 这类非法值挡在入口（或改用 strict JSON schema，与生产管线对齐）。
3. 重跑抽取时**做 2×2**：{旧提示词, 新提示词} × {旧索引, v2 索引}。只有这样才能把「提示词限制」和「语料共处率」两个因素分开——否则又是一次 §18 之前那种归因不清的测量。

在这组数出来之前，§23.2 那个 0.617 的 logic 失真度**不能**归因于抽取器能力，它至少同时包含了提示词限制、§30.4 的文献纳排标准污染、以及语料共处率三个来源。

> **三步已全部执行，结果见 §34。** 上面那个「多行渲染可能让模型更不愿成组」的风险没有兑现：v2 索引在旧提示词下跨行成组率不降反升（6.9%→19.4%），换新提示词后到 31.6%。

### 32.6 本节产物

| 文件 | 内容 |
|---|---|
| `audit_group_span.py` | 从已有抽取产物反推组的成员 quote 跨句/跨行分布，验证提示词单句限制是否生效；同时报告 logic 字段的非法值 |

## 33 跨 chunk 窗口到底接没接进管线：一处更正、两个缺陷、一个接线缺口

§32.4 写了「模型一次只看一个 chunk」。**这句话是错的**，必须更正；但顺着它查下去，发现跨 chunk 机制虽然接进了管线，却有两处会让它静默失效的缺陷，其中一处是我自己在 §29 引入的。

### 33.1 更正：窗口是 3 个 chunk，不是 1 个

`TrialRetriever.passage()` 把命中 chunk 与同文档前后邻居拼成一个 passage：

```69:87:analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL/trial_retriever.py
    def passage(self, gid: int, window: int = 1) -> dict:
        """Hit chunk plus same-document neighbours, in reading order."""
        ...
            "text": "\n".join(self.text(g) for g in gids),
```

而 `run_trial_retrieval.py:132` 用默认 `window=1` 调用它，`run_trial_extraction.py` 再消费 `p["text"]`。所以抽取器看到的是 **gid−1、gid、gid+1 三个 chunk 的拼接**，跨 chunk 机制确实接进了管线。§32.4 据此得出的「共处同一 chunk 是主要收益」这个论断，其粒度应当是**共处同一窗口**，下面 33.4 重新结算。

### 33.2 缺陷一：StatPearls 的文档边界保护此前完全失效

窗口靠 `doc_key` 判断邻居是否还在同一篇文章：

```42:42:analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL/trial_retriever.py
        self.doc_key = [f"{m['source']}|{m['article_id']}" for m in self.meta]
```

而 §29.2 查出旧 StatPearls 的 `article_id` **全为空**。实测旧索引 meta：

| 来源 | chunk | `article_id` 为空 |
|---|---:|---:|
| statpearls | 367,799 | **367,799（100%）** |
| 其余五个来源 | — | 0 |

于是全部 367,799 个切片的 `doc_key` 都是 `"statpearls|"`，边界判断恒为真——**占语料 42.7% 的最大来源，其文档边界保护是关掉的**。

实测危害（`audit_window_integrity.py`，用 `_pN` 计数器回绕还原真实文章边界）：

| | 邻接槽粘进别的文章 |
|---|---:|
| 旧索引 statpearls | **19,270 / 735,598（2.62%）** |
| 旧索引 其余来源 | 0 |
| v2 全部来源 | **0** |

19,270 恰好等于 9,635 个文章边界 × 2，说明危害精确地局限在边界处，不是全面污染：约 5.2% 的 StatPearls 切片会被拼进一段来自**另一篇文章**的邻居。§29.2 修 `article_id` 时是为了 chunk id 唯一性，顺带把这个 bug 一起治了。

### 33.3 缺陷二：我在 §29 把同一个 bug 搬到了 textbooks

本次审计的直接产出是发现 v2 的 textbooks **也**丢了 `article_id`——而旧版本是有的。原因是 `normalize_textbooks.py` 读的是 `data/corpus/textbooks/chunk/*.jsonl`（MedRAG 分册文件，schema 为 `{id,title,content,contents}`），而索引构建读的是 `textbooks_chunks.jsonl`（schema 为 `{id,title,content,article_id,tokens}`）。落盘时按前者的 schema 写出，`article_id` 就没了。

这等于把 33.2 那个 bug 从 StatPearls 原样搬到了 textbooks，而且是我引入的。已修：落盘改为以 `textbooks_chunks.jsonl` 为骨架、只替换 `content`（两者 id 集合完全一致，内容差异 5.2% 正是规范化改动）。修复后 `article_id` 空值归零。

**因此 v2 索引已重建。** 顺带一提，这个 bug 是被审计脚本的一次崩溃暴露的：重写 textbooks 文件后字节偏移改变，meta 里的 `offset` 全部失效——这也提醒，**任何语料文件的改动都必须连带重建索引**，两者通过字节偏移强耦合。

### 33.4 截断阈值：不是问题，且未因本次修复恶化

`run_trial_extraction.py` 在 `--max-passage-chars`（默认 6000）处切断 passage。§29.2 把列表并回引导句会让 chunk 变长，理论上会推高截断率。实测（抽样 4.1 万个窗口）：

| | 窗口长度中位／p90／p99 | 超过 6000 |
|---|---|---:|
| 旧索引 | 1,691 / 3,030 / 6,622 | 1.72% |
| v2 | 1,658 / 3,037 / 6,680 | **1.71%** |

StatPearls 自身从 0.02% 升到 0.10%，绝对量可忽略。**合并列表没有制造截断问题**（因为 §29.2 的 `MAX_JOINED_CHARS = 6000` 恰好与这条线对齐）。真正的截断大户是 `manifest_cpg`（18.2%）和 `merck`（8.2%），与本轮工作无关，是既有问题。

### 33.5 接线缺口：修好的语料此前根本用不上

`trial_retriever.py` 把索引目录和六个语料路径**硬编码**指向旧版本，所以 §29 修好的语料在管线里是不可达的。已改为：

- 从索引自己的 `config.json` 读取语料路径（索引与语料因此不会漂移）；
- `TrialRetriever(index=...)` 参数化，`run_trial_retrieval.py` 增加 `--index`；
- 构造时若发现任何来源 `article_id` 为空，**打印警告**——33.2 那个 bug 静默了很久，代价是全靠人去翻 meta 才发现。

端到端验证：`TrialRetriever(index=INDEX_V2)` 载入 907,371 切片，检索返回 `window_gids=[740893, 740894, 740895]` 的三段拼接 passage，偏移寻址正确。

### 33.6 这对 §29–§32 的结论意味着什么

**§29 的 StatPearls 修复不受影响，而且理由要说得更准。** 窗口能缝合的前提是内容在语料里。textbooks 的成员在相邻 chunk，所以 ±1 窗口能救（§26.4 测得 99.8%）；但 StatPearls 的列表成员**根本没有被入库**（`findall("p")` 从未访问 `<list>`），窗口无从缝起——只有入库修复能拿回那 25.3M 字符。三个语料的处境因此是不同的：

| | 成员在哪 | ±1 窗口能否救 | 靠什么修 |
|---|---|---|---|
| statpearls | **不在语料里** | 否 | 入库修复（§29.2） |
| pmc_oa | 在，同段或邻段 | 部分 | 窗口 + 提示词（§31、§32） |
| textbooks | 在，邻 chunk | 是（99.8%） | 已被窗口覆盖 |

**§32.5 的 2×2 计划需要加一条前置校验。** 在跑之前必须确认两个索引的窗口完整性一致（本节的 `audit_window_integrity.py` 即为此），否则「旧索引 vs v2 索引」这一维会混入 33.2 那个 2.62% 的跨文章粘连差异，而不是纯粹的语料修复效果。

> §34 已跑完 2×2。这条校验的结论要说清楚：两个索引的窗口完整性**并不一致**，v2 修好了 33.2 的粘连，所以「v2 索引」这一维是**语料修复 + 文档边界修复**的合并效应，不是纯语料。两者都指向同一方向（更多完整判据集进入窗口），本报告不再拆分。

### 33.7 本节产物

| 文件 | 内容 |
|---|---|
| `audit_window_integrity.py` | ±1 窗口的跨文档粘连率与窗口长度／截断率，新旧索引对照 |
| `trial_retriever.py` | 索引与语料路径参数化（从 `config.json` 读），`article_id` 为空时告警 |
| `run_trial_retrieval.py` | 新增 `--index` |
| `normalize_textbooks.py` | 落盘改为保留规范语料的完整 schema |

## 34 2×2：提示词的「单句」限制与语料修复，各自值多少

§32.5 定的顺序是**先改提示词、再重跑**，否则测到的是提示词限制而非语料修复。本节把两者交叉，四臂各跑一次完整抽取（每臂 3,842 个 passage-假设任务，11 例，`trial_tasks_11_all4.json`，top-k 30 / keep 30）。

### 34.1 两个改动分别是什么

**提示词。** 旧段落把成组范围限定在 `when one sentence lists several findings`，模型照办：§32.4 测得 768 个组里 96.4% 落在单句内，跨行 0。但 §24.2 测得真实判据集只有 12.3% 把量词和成员写在同一句，常态是「引导句以冒号结尾 + 成员各占一行」。新段落（`FREE_GROUP_BLOCK`，`--free-groups`）把范围放到整个 passage，并列出四种版式 (a) 单句内、(b) 冒号引导 + 成员分行、(c) 冒号引导 + 成员散文、(d) 成员跨句跨行，明写「成员不必与量词同句同行」。

**枚举校验。** 试验管线是自由 JSON、无 schema，模型会返回字符串 `"null"`（在 Python 里为真，会把一个 passage 内所有未成组断言并成一个伪组），也会自造 logic。`normalise_group()` 把 `criterion_group` 夹到 schema：清洗 `"null"/"none"/""`，`and→all`、`or→any` 归一，非法值降为 `None`，`at_least_n` 缺 `n` 时降为 `any`。

两者都用独立的 cache kind（`guideline_groups_free`），否则两个提示词会读到对方的缓存——缓存键是 `(kind, payload, model)`，**不含提示词本身**。

### 34.2 三处必须先排掉的伪影

**旧索引臂是忠实对照。** 重跑的 `x2_oldidx` 与历史 `k30all4` 臂在 §23 那把尺子上完全一致（保真 12/44、成组率 52.3%、TVD 0.365），逐槽对齐 93.4%（差异是并列打破噪声，与 §12 记录同量级）。

**v2 的 oracle 召回「掉到 11/26」是伪影。** `oracle_gids` 是索引行号，旧索引 861,131 行、v2 索引 907,371 行，同一个整数指向不同 chunk。按 `(source, native_id)` 重映射后为 18/26，但 statpearls 有 161 个 oracle chunk 无对应——§29.2 的 `article_id` 修复重写了它的 `native_id`，例 119 的 6/6 与 1/1 全部落空，`hit=False` 是**不可测**而非真漏。改用与索引无关的尺子（任务文件自带的 `subject_re`/`predicate_re` 在窗口正文上匹配）：**旧索引 24/26，v2 索引 25/26**，v2 略优，检索层没有回退。

**「跨行成组率」的原尺子是坏的。** 模型引用时会归一化空白：34,332 条引文里只有 11 条含换行，而 3,842 个 passage **全部**含换行。按「引文里有没有 `\n`」判跨行，永远得 0，无论提示词怎么写。改成把引文定位回原 passage、按它落在原文第几行来判（`measure_2x2_groups.py` 的 `prepare()`/`line_of()`）。

### 34.3 主终点：跨行成组率

一个组的成员是否落在原文不同的行——这正是「单句」限制封死的那件事。

| | groups≥2 | 成员数 | 单引文 | 同句 | 跨句 | **跨行** | 定位失败 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 旧提示词 / 旧索引 | 540 | 2,344 | 25.6% | 59.6% | 6.1% | **6.9%** | 1.9% |
| 新提示词 / 旧索引 | 390 | 1,766 | 26.7% | 52.6% | 8.2% | **10.3%** | 2.3% |
| 旧提示词 / v2 索引 | 612 | 2,864 | 21.6% | 52.3% | 5.6% | **19.4%** | 1.1% |
| 新提示词 / v2 索引 | 500 | 2,512 | 19.6% | 42.0% | 5.8% | **31.6%** | 1.0% |

两个比例检验（组为单位，各臂独立）：

| 对比 | 跨行率 | z | p |
|---|---|---:|---:|
| 提示词效应，旧索引 | 6.9% → 10.3% | 1.86 | 0.063 |
| 提示词效应，v2 索引 | 19.4% → 31.6% | 4.66 | 3.1e-06 |
| 语料效应，旧提示词 | 6.9% → 19.4% | 6.23 | 4.6e-10 |
| 语料效应，新提示词 | 10.3% → 31.6% | 7.60 | 3.1e-14 |

**语料是更大的那个杠杆**：固定提示词，只换索引就把跨行率抬了 2.8×–3.1×，两个方向都远超显著。**提示词只在 v2 上达到显著**（旧索引 p=0.063）——旧语料里成员根本没被渲染成独立行（§29.2 的 `<list>` 从未入库），放开单句限制也无行可跨。

但**不能说两者相乘**：对数几率尺度上的交互项为 +0.209（se 0.275，z=0.76，**p=0.449**），不拒绝「两个比值比相等」。可以说的是：两个杠杆各自有效、语料是更大的一个、提示词的绝对增益在基线率高的地方更大；不能说提示词在 v2 上「更管用」。

### 34.4 logic 分布与 TVD

| | `all` | `any` | `at_least_n` | 无 logic |
|---|---:|---:|---:|---:|
| 旧提示词 / 旧索引 | 30.9% | 64.8% | 2.2% | 2.0% |
| 新提示词 / 旧索引 | 39.5% | 55.1% | 5.1% | 0.3% |
| 旧提示词 / v2 索引 | 27.8% | 68.0% | 2.0% | 2.3% |
| 新提示词 / v2 索引 | 33.4% | 62.2% | 4.4% | 0.0% |

新提示词在两个索引上都把 `any` 压下去、把 `all` 与 `at_least_n` 抬起来。`at_least_n` 翻倍（2.2%→5.1%、2.0%→4.4%），方向正是 §23.3 指出最坏的那个偏差的反向——`any` 是引擎唯一永远不可能刚性的 logic。枚举校验则把「有组无 logic」几乎清零（44→5、57→6）；非法 logic 值（`typical`、`obligatory`、`required_for`、`and`）每臂只有个位数，所以它是正确性兜底，不是产量修复。

段落级 TVD（`calc_logic_distortion.py`，同索引内可比）：

| | 判据段落 | logic 保真 | 成组率 | TVD |
|---|---:|---:|---:|---:|
| 旧提示词 / 旧索引 | 44 | 27.3% | 52.3% | 0.365 |
| 新提示词 / 旧索引 | 44 | 31.8% | 54.5% | **0.303** |
| 旧提示词 / v2 索引 | 41 | 26.8% | 63.4% | 0.493 |
| 新提示词 / v2 索引 | 41 | 36.6% | 68.3% | **0.378** |

**这里的 TVD 不能与 §23.3 的 0.617 对比。** 那个数是把 `k30all4` 与 `pool37k30all4` 两个检索文件合并后的 155 段算的，本节每臂只有一个检索文件，判据段落 41–44 段。跨索引也不可比（文本侧分布本身不同）。同索引内提示词都让 TVD 下降（−0.062、−0.115），保真率都上升。

配对分析（同一批段落，`paired_logic_flips.py`）：旧索引 2 修 0 坏（p=0.500），v2 索引 5 修 1 坏（p=0.219），合并 7 修 1 坏（**p=0.070**）。**方向在每一把尺子上都一致，但判据段落这个样本量（41–44）不足以让 TVD 一族的指标达到显著。** 主终点跨行率的样本量是 390–612 个组，那一族才是有功效的。

### 34.5 一个必须交代的捆绑

新提示词同时做了第二件事：明写忽略文献纳排标准（§30.4 的污染）。这会**减少**组数，所以组数从 540→390、612→500 不能读成成组能力退化。但它只解释一小部分：落在文献纳排 passage 里的组，旧索引 26→15、v2 索引 22→12，即 −11 与 −10，而总降幅是 −150 与 −112（`audit_prompt_confound.py`）。**其余降幅来自成组判据本身收紧**：新提示词的组更少但更大（每组成员 4.34→4.53、4.68→5.02），且跨行率大幅上升。要把这两件事彻底分开，需要再跑一臂「只放开单句限制、不加文献过滤」，目前没跑。

### 34.6 结论与下一步

- 「单句」限制确实是真限制，放开它让跨行成组率从 6.9%/19.4% 升到 10.3%/31.6%，并把 logic 分布推向文本方向；但**只有在语料已经把成员渲染成独立行之后，这个改动才达到显著**。
- 语料修复（§29）是更大的杠杆，且它的收益此前被提示词限制盖住了——这正是 §32.5 坚持「先改提示词再重跑」的理由，若按原顺序，测到的会是一个被压低的语料效应。
- **下游 top-1 尚未测。** 本节只结算到抽取侧的组结构与 logic 分布。四臂的抽取产物已经落盘，跑 `run_mechanical_engine.py` 即可结算排名，这是下一步。
- §23.3 那个 0.617 仍不能归因于抽取器能力：本节移除了其中的提示词限制这一项，另两项（§30.4 文献纳排污染、语料共处率）分别由 34.5 的过滤和 §29 的修复处理，但三者合并后的净值需要在统一口径（合并两个检索文件的 155 段）上重算才可与 0.617 直接对比。

### 34.7 本节产物

| 文件 | 内容 |
|---|---|
| `run_trial_extraction.py` | `FREE_GROUP_BLOCK` + `swap_group_block()` + `--free-groups`；`normalise_group()` 枚举校验与修复计数 |
| `trial_retriever.py` | `--index` 接受裸索引名（此前只认绝对路径，v2 索引实际用不上） |
| `smoke_free_groups.py` | 在同一批判据 passage 上对跑新旧提示词的小规模对照 |
| `measure_2x2_groups.py` | 四臂的成组率、成员数、跨行/跨句跨度（引文定位回原文行）、logic 分布 |
| `remap_oracle_gids.py` | gid 跨索引重映射 + 与索引无关的正则 oracle 召回 |
| `paired_logic_flips.py` | 同批判据段落上的配对翻转与符号检验 |
| `audit_prompt_confound.py` | 拆开新提示词捆绑的文献纳排过滤的贡献 |
| `calc_logic_distortion.py` / `audit_criteria_fidelity.py` | 增 `--retrieval`/`--extraction`，可按臂计算 |
| `trial_retrieval_x2_{oldidx,v2idx}.json` | 两个检索臂 |
| `trial_extraction_x2_{oldidx,v2idx}clean_groups[_free].json` | 2×2 四臂抽取产物 |

## 35 下游结算：抽取变好了，排名没有跟上，瓶颈换了位置

§34 只结算到抽取侧。本节把四臂过一遍交付配置（B1 + S7，即 `embed_tau=0.60`、`marker`、`organism`、`enum_clamp`、`corpus_lr`、`group_all_required`、`quote_gate`），任务集 `trial_tasks_11_all4.json`。

### 35.1 结果：排名不升反降

| | top-1 | top-3 | MRR | MRR 95% CI | 金标被淘汰 | 组贡献 | 组淘汰 |
|---|---:|---:|---:|---|---:|---:|---:|
| 旧提示词 / 旧索引 | 2/11 | 7/11 | 0.427 | [0.273, 0.609] | 1 | 124 | 3 |
| 新提示词 / 旧索引 | 2/11 | 6/11 | 0.413 | [0.258, 0.606] | 1 | 84 | 7 |
| 旧提示词 / v2 索引 | 1/11 | 6/11 | 0.367 | [0.253, 0.515] | 2 | 136 | 6 |
| 新提示词 / v2 索引 | 1/11 | 4/11 | 0.307 | [0.207, 0.463] | 2 | 102 | 7 |

**先说不能声称的东西。** n=11，四个 MRR 的 95% CI 两两重叠；逐例金标名次的配对符号检验（旧/旧 对 新/v2：5 例变差、2 例变好、4 例不变）p=0.453。**这组数不支持「变好」，也不支持「变差」**，它只支持一条否定结论：§34 那些在抽取侧显著的改善（跨行成组率 6.9%→31.6%）**没有在排名上兑现**。

### 35.2 不是判据组的锅

两个探针都指向组之外：

- **`at_least_n` 组几乎进不了分数。** 抽取侧 `at_least_n` 占比翻倍（2.2%→5.1%、2.0%→4.4%），但真正进到打分的 `at_least_n` 组只有 3 / 3 / 5 / 5 个。绝大多数组要么没绑定到候选，要么成员没接合到病人发现。
- **F4b 消融毫无变化。** 关掉 `group_all_required`（`all` 组当否决）后四臂的 top-1 一个没动，MRR 最多变 0.003。组淘汰虽然从 3 涨到 7，但**杀死金标的不是它**。

### 35.3 真正的机制：层一 `excludes` 硬否决

六次金标淘汰，规则**全部**是 `exclusion_triggered`：

| 臂 | 例 | 触发谓词 |
|---|---|---|
| 旧提示词 / 旧索引 | 773 | pulmonary hypertension |
| 新提示词 / 旧索引 | 773 | joint pain |
| 旧提示词 / v2 索引 | 773 | pulmonary hypertension |
| 旧提示词 / v2 索引 | **74** | ischemic or structural heart disease |
| 新提示词 / v2 索引 | 773 | joint pain |
| 新提示词 / v2 索引 | **74** | ambulatory ventricular ectopy |

量化对得上：v2 语料把 `excludes` 断言从 1,374 抬到 1,574（+14.6%，固定旧提示词）。**语料修复让更多文本进入窗口，更多 `excludes` 被抽出来，层一的一票否决把其中一部分打在了金标上。**

消融该路径（`--drop-excludes`，把 `excludes`/`argues_against` 从抽取输入里去掉）：

| | top-1 | top-3 | MRR | 金标被淘汰 |
|---|---:|---:|---:|---:|
| 旧提示词 / 旧索引 | 2/11 | 7/11 | 0.420 | 0 |
| 新提示词 / 旧索引 | 2/11 | 7/11 | 0.438 | 0 |
| 旧提示词 / v2 索引 | 1/11 | 7/11 | 0.392 | 0 |
| 新提示词 / v2 索引 | 1/11 | 6/11 | 0.360 | 0 |

金标淘汰归零，top-3 全面回升，MRR 部分回收。**但 top-1 一个没变。** 例 74 是唯一在 v2 上丢掉 top-1 的例：带 `excludes` 时金标被淘汰、名次 4，去掉后回到名次 **2**——仍不是 1。所以 `excludes` 否决解释了 4→2 那一段，剩下 2→1 那一段是别的东西：v2 让更多文本进入窗口，也给竞争候选提供了更多证据。

### 35.4 一个意外的正向发现：新提示词把高权关系捞回来了

新提示词只改了成组范围，但高权 relation 的产量明显上升：

| | 断言总数 | `required_for` | `pathognomonic_for` | `sufficient_for` | `excludes` |
|---|---:|---:|---:|---:|---:|
| 旧提示词 / 旧索引 | 34,338 | 836 | 127 | 102 | 1,374 |
| 新提示词 / 旧索引 | 33,533 | **1,054** | 133 | **146** | 1,255 |
| 旧提示词 / v2 索引 | 36,837 | 839 | 123 | 108 | 1,574 |
| 新提示词 / v2 索引 | 35,944 | **1,162** | 120 | **158** | 1,368 |

在断言总数**下降**的同时，`required_for` 升 26%/38%、`sufficient_for` 升 43%/46%。这正是 §23.4 记录的那个缺陷的反向：文本里判据集是刚性身份（21.3% 明写 must/required、3.2% 明写 establishes），抽取器却把它降成 `feature_of`。把成组范围放到整个 passage 之后，模型能读到引导句里的量词与效力词，并把它施加到成员上。**§23.4 的降级问题被这次提示词修改部分修复了，这是本轮唯一在抽取侧有净收益且方向明确的一项。**

顺带一提，新提示词把 `excludes` 压低了（1,374→1,255、1,574→1,368），方向对，但不足以抵消 v2 带来的增量。

### 35.5 结论：瓶颈从「抽不出复合判据」移到了「层一太刚」

把 §34 与本节合起来读：

1. **语料侧与提示词侧的问题已经解决到可用程度。** 跨行成组率 6.9%→31.6%，logic 分布向文本靠拢，高权关系产量回升。§29–§34 这条线的交付目标达成。
2. **收益卡在接合与层一。** 组进不了分数（`at_least_n` 只有 5 个真正打分），说明绑定/接合是新的窄口；而抽出来的东西越多，层一 `excludes` 的一票否决打中金标的机会越大——**更好的抽取在当前引擎下会被转化成排名损失**。
3. 这与用户此前对层一/层二刚性的疑虑指向同一处，但结论要反过来说：问题不是刚性规则太少（§34 之前担心的是真高权被降级），而是**刚性规则的否决方向缺少保护**。`excludes` 走的是无条件一票否决，没有情态、辖域或竞争性证据的约束。

### 35.6 下一步

- **优先级最高：给 `excludes` 加约束**，而不是给它加权重。可选路径：只让 `obligatory` 情态的 `excludes` 进层一；要求排除项与病人发现的接合是精确匹配而非嵌入近似；或在有多条相反证据时降级为扣分而非淘汰。本节的 `--drop-excludes` 消融给出了这条路径的上界（金标淘汰 2→0、top-3 6→7）。
- **其次：查组为什么进不了分数。** 500 个组只有 5 个 `at_least_n` 进到打分，中间的绑定与接合损耗尚未定位，这是把 §34 的抽取收益变现的前提。
- **不要再用 11 例做排名级判定。** 本节四臂的差异全部在噪声内。要判定这些修改对排名的净效应，需要扩到 §18 那种规模的样本外集合。

### 35.7 本节产物

| 文件 | 内容 |
|---|---|
| `score_2x2_engine.py` | 四臂在 B1+S7 下的 top-1/MRR/金标淘汰、判据组开火计数与逐条淘汰原因；`--ablate-f4b`、`--drop-excludes` 两个消融 |
| `trial_engine_x2.json` | 主配置四臂结果 |
| `trial_engine_x2_noexcl.json` | 去掉 `excludes`/`argues_against` 的消融结果 |

## 产物


| 文件 | 内容 |
|---|---|
| `trial_tasks_11.json` | 11 例任务：vignette、金标、候选集（collapse3c ∪ multistance，含别名与各方法排名）、26 条断言及其正则 oracle 切片全集 |
| `trial_retrieval_k8.json` / `_k30.json` / `_k30oracle.json` | 三个检索臂的逐假设 passage 与 oracle 召回 |
| `retrieval_depth_diagnosis.json` | 每条断言在各 lane 与融合排名下需要的检索深度 |
| `trial_extraction_k30clean.json` / `_k30oracleclean.json` | 病例发现与指南断言（无组） |
| `trial_extraction_k30oracleclean_groups.json` | 带 `criterion_group` 的指南断言（17,029 条，7.1% 进组） |
| `trial_engine_*.json`（8 个臂） | 第一轮引擎：排除链、确认、得分与贡献 |
| `trial_failure_trace_k30clean.json` / `_k30oracleclean.json` | 26 条断言的逐级死亡定位 |
| `trial_summary_11.csv` / `trial_summary.json` | 全臂汇总与逐例归因 |
| `evidence_pack_k30clean.md` / `.json` | 11 例 top-1 与金标的断言 → 原文 → vignette 命中项（118 条） |
| `EXPLICIT_NEGATIVE_RECALL.md` | 显式阴性入集核验：组成 vs 召回、按例表、未入集 15 条分类 |
| `explicit_negative_recall_11.csv` | 97 条原文显式阴性的入集裁定（hit / miss / polarity_error） |
| `explicit_negative_recall_summary.json` | 召回、组成、按例计数与 Wilson 区间 |
| `hypothesis_sweep_k30oracleclean.json` | H2 权重扫描（无组） |
| `hypothesis_sweep_k30oracleclean_groups.json` | H1×H2 因子扫描（24 格：groups × join × weight） |
| `hypothesis_sweep_k30oracleclean_groups_cwa.json` | 同上并交叉封闭世界 |
| `specificity_test_k30oracleclean_strict.json` / `_loose.json` | H2 配对层：按 \(k\) 的 lift 与置换 \(p\) |
| `data/corpus/ceiling_trial_index/` | 861,131 切片的 TF-IDF + MiniLM 索引 |
| `fix_isolation_stage1.json` / `_stage2.json` | 六条修复的逐条隔离检测（两基线 × 18 配置） |
| `fix_isolation_all4.json` | 四方法并集候选集上的隔离检测 |
| `fix_stack_all4.json` | 累加栈 S0–S6 的逐步消融与逐例排名 |
| `fix_mechanism_checks.json` | 机制层检查：9 条目标链的接合类型、组触发计数、371 条出界 relation、601 条纯嵌入命中抽样 |
| `join_embeddings.npz` | 14,013 条断言谓词/发现标签/候选别名的 MiniLM 嵌入（384 维） |
| `corpus_lift_table.json` / `_all4.json` | 语料侧 \(P(f \mid h)\) 与似然比（提及级锚定） |
| `statpearls_title_audit.json` | 400 篇抽样：33.3% 标题与正文无关，367,799 条切片 `article_id` 全空 |
| `subtype_mining.json` / `_top1.json` | n-gram 密度 + Hearst 模式双通道亚型挖掘 |
| `trial_tasks_11_all4.json` / `_split.json` / `_split1.json` | 四方法并集候选集，及亚型拆分后的扩展候选集 |
| `trial_tasks_257_split.json` / `trial_retrieval_k30split257.json` | 257 号例亚型拆分定点检验（24 候选、421 passage） |
| `case475_extraction_defect_census.json` | 475：高权槽人工标签（E1–E11） |
| `case_extraction_defect_census_10.json` | 其余十例：高权槽核验与 E12–E14 |
| `trial_extraction_k30oracleclean_groups_conv_773.json` | F5b 逆命题提示对 773 号例的重抽 |
| `trial_extraction_k30clean_groups_grounded.json` | §16：闭集主语 + quote 阈值 + vignette 补集重抽 |
| `f7_f8_isolation.json` | §16：B1+S6 上 C0–C3 四格与门闸命中 |
| `nli_cache.json` | F8 NLI 蕴含标签缓存 |
| `negated_l1_census.json` | §5.0.1.1：C1 上拿掉 `asserted` 闸后的层一开火与对偶开火 |
| `dual_l1_harm_audit.json` | §5.0.1.2：对偶淘汰是否有害；`excludes` recast 反事实 |
| `case74_highstakes_unique.json` | §14.4：74 号例高权槽 unique 七元组 |
| `case74_relation_error_census.json` | §14.4：74 号例 `required_for` 假必要（A–F）与真必要进错槽（G1–G3） |
| `f9_goal_iteration.json` | §16.7：G-A/G1/G2/G3 机制题与相对 C1 排名 |
| `case74_inverse_required_after_f9.json` | §16.7.1：真必要进错槽门闸前后 |
| `gate_generality_census.json` | §16.7.2：门闸码跨病例开火数与逐例 `required_for` 存活 |
| `relation_verifier/train_other10.jsonl` / `test_case74.jsonl` | §16.8：验证器训练集（十例，教师+扰动+schema）与 74 号例人工标签测试集 |
| `relation_verifier/build_audit.json` | §16.8：测试集重链与普查计数的对账 |
| `relation_verifier/verifier_results.json` | §16.8：三种子结果、分槽 AUC、阈值-标注量研究、与 F7 的逐行分歧 |
| `relation_verifier/annotate_diagnostic_slots.tsv` / `ANNOTATION_CODEBOOK.md` | §16.8：848 行分层标注表与判定口径 |
| `relation_verifier/batch_qc_case74.tsv` / `_key.json` / `labels_qc_case74.tsv` | §16.8 第 3 轮：60 行盲测片、留出答案、标注结果 |
| `relation_verifier/annotation_qc.json` | §16.8 第 3 轮：一致率 0.933、κ 0.822、混淆表 |
| `trial_nl_rules_k30all4.json` / `_stats.json` | §17：逐字规则句摘录（16,145 条）与后处理统计 |
| `llm_executor_findings.json` / `_vignette.json` / `_nl_cap12.json` / `_nl_cap100.json` / `_fixedorder.json` | §17：LLM 执行引擎五臂与三组消融 |
| `llm_executor_comparison.json` | §17：与机械引擎的汇总、逐例配对符号检验、稳定性分解 |
| `case74_nl_rule_quality_census.json` | §17.2：39 条摘录的人工判读 |
| `altpath_error_mode_census.json` | §17.7：提取错类映射与 N1–N11 |

脚本均在 `analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL/`：

| 脚本 | 职责 |
|---|---|
| `build_trial_index.py` / `trial_retriever.py` | 审计语料上的混合索引与 RRF 检索 |
| `build_trial_tasks.py` | 11 例任务文件（collapse3c ∪ multistance 候选集） |
| `run_trial_retrieval.py` / `diagnose_retrieval_depth.py` | 假设条件化检索与深度诊断 |
| `run_trial_extraction.py` | 两处 LLM：`--groups` 抽出 `criterion_group` |
| `run_mechanical_engine.py` | 无模型规则引擎：`specificity()`、判据组求值、封闭世界开关 |
| `sweep_hypotheses.py` | H1×H2×CWA 因子扫描与 MRR bootstrap |
| `test_specificity_hypothesis.py` | H2 配对层置换检验 |
| `trace_trial_failures.py` / `summarize_trial.py` | 26 条断言死亡定位与全臂汇总 |
| `build_evidence_pack.py` / `freeze_explicit_negatives.py` | 证据链与显式阴性入集核验 |
| `sweep_fixes.py` | 修复隔离检测与累加栈（含 F7/F8 → S7/S8） |
| `check_fixes.py` | 机制层检查：目标链、组、枚举、F7 四题 + G-A/G1/G2/G3 |
| `gate_assertions.py` | F7：quote/情态/析取/阈值程序门闸；§16.7 G-A 同句辖域、检查/发现类型闸、G1 双槽、G2 参考区间改写、G3 合取肢（§16.7.2 起规则内不含任何专名）；§16.8 增 E15 充分性槽、E16 `excludes`+negated schema 闸与四组构式扩展 |
| `iter_f9_goals.py` | §16.7 交付核对（相对 C1） |
| `audit_inverse_required.py` | §16.7.1：真必要 KEEP 与 G1–G3 漏槽收回 |
| `audit_generality.py` | §16.7.2：门闸码跨病例开火统计与 `required_for` 存活清单 |
| `build_relation_verifier_data.py` | §16.8：74 人工普查重链为测试集；十例教师标签 + 受控扰动 + schema `excludes` 标签 |
| `finetune_relation_verifier.py` | §16.8：MedCPT-Cross-Encoder 微调、分槽评测、阈值-标注量研究 |
| `make_annotation_kit.py` | §16.8：848 行分层标注表与 codebook |
| `prep_annotation_batches.py` | §16.8：切出 200 行训练标注批与 60 行盲测质检批（均无标签） |
| `score_annotation_qc.py` | §16.8：盲测批与人工普查的一致率与 κ |
| `apply_human_labels.py` | §16.8：把标注折进训练集（`?` 丢弃），并报与 F7 教师的一致率 |
| `audit_slot_errors.py` | §16.8 第 6 轮：按槽与方向（过度放行／过度降档）摊开门闸与标注的每条分歧 |
| `nli_verify_assertions.py` | F8：高权槽 NLI（无模型则跳过） |
| `isolate_f7_f8.py` | §16 四格隔离 |
| `census_negated_l1.py` | §5.0.1.1：`negated` 进层一的反事实普查 |
| `audit_dual_l1_harm.py` | §5.0.1.2：对偶开火与 relation recast |
| `postmortem.py` | 单例双配置追踪：排名倒挂归因到具体接合对 |
| `build_join_embeddings.py` | 接合层嵌入预计算（MiniLM-L6） |
| `build_corpus_lift.py` | 语料侧似然比表（`--anchor mention/title`） |
| `audit_statpearls_titles.py` | StatPearls 标题正确性审计 |
| `mine_subtypes.py` | 亚型挖掘：n-gram 平滑密度 + Hearst 模式双通道 |
| `dump_case_study.py` | 十四章：逐例发现集、B1+S6 排名、金标/赢家贡献与淘汰链 |
| `dump_case_475.py` | 475 号例：全部打分/淘汰规则的引语、出处、接合与绑定 |
| `audit_475_extraction.py` | 475 抽取缺陷启发式 |
| `dump_extraction_slots_10.py` | 其余十例高权槽（required/pathognomonic/sufficient/excludes）转储 |
| `extract_nl_rules.py` | §17 阶段 A：逐字规则句摘录 + 程序侧阈值回填 + 子串忠实度核验 |
| `run_llm_executor.py` | §17 阶段 B：LLM 执行引擎，五种规则表示 × findings/vignette × 固定/打乱顺序 |
| `compare_llm_vs_mechanical.py` | §17：汇总表、逐例配对符号检验、解码噪声与位置敏感性分解 |
