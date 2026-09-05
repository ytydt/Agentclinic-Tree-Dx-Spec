# 显式阴性入集核验：27.9% 是组成不是召回

对应问题：抽取结果里 `absent`+`normal` 只占 78/280 = 27.9%，硬约束几乎打不响——这是抽取器把原文阴性弄丢了，还是病例文本本来就没写？

结论先行：**不是漏抽。** 剥离选项块后的 11 份 vignette 里，人工冻结了 97 条显式否定/正常，**82 条进入发现集合（召回 84.5%）**；未入集 15/97 = 15.5%（Wilson 95% CI 约 10–24%）。27.9% 测的是发现集合的**组成**，84.5% 才是原文阴性的**召回**。硬约束打不响，是因为指南特征在病例里根本没被陈述（封闭世界缺口），不是因为抽取器把已写的阴性丢掉了。

## 口径

只计文本里明确否认、报为 `normal` / `negative` / `unrevealing` / `unremarkable` 的条目。列表拆成原子项（“palms, soles, and oral mucosa were not involved” 计 3 条）。封闭世界推断不入账：Kanavel 未提及的梭形肿胀、被动伸指痛等，vignette 从未否认，不算抽取失误。

清单冻结在 `freeze_explicit_negatives.py` 的 `ITEMS`，与抽取产物 `trial_extraction_k30oracleclean_groups.json` 对照。入集判定要求发现的 quote 覆盖原文跨度，或 label/canonical 点名该条目，且极性为 `absent`/`normal`。quote 含否定但极性挂在父检查上的，记为 `polarity_error`。

## 两个数字

| 口径 | 数值 | 含义 |
|---|---:|---|
| 发现集合中 `absent`+`normal` 的占比 | 78/280 = **27.9%** | 抽取器输出的组成 |
| 原文显式阴性进入发现集合的比例 | 82/97 = **84.5%** | 召回 |
| 未入集（漏检 14 + 极性挂错 1） | 15/97 = **15.5%** | Wilson 95% CI 约 10–24% |

组成偏低来自切分不对称，不是漏抽：

- **阳性侧切碎。** 每个化验数字单独成条。522 一题 BUN、Cr、LDH、白蛋白、血红蛋白、血小板、同型半胱氨酸、B12、25-OH-D 就占了 9 条 `present`。
- **阴性侧合并。** 同一句里的多项否定常并成一条。腰椎穿刺 “negative for infectious, autoimmune, malignant causes and paraneoplastic encephalitis” 原文 4 项，只产出 1 条 `lumbar puncture [absent]`。

## 按例

| 病例 | 原文条数 | 入集 | 未入集 |
|---|---:|---:|---:|
| DA_d2_heldout200b/522 | 13 | 12 | 1（EEG without seizures 极性挂错） |
| DA_d2_heldout200b/773 | 5 | 4 | 1（initially acyanotic） |
| DA_d2_seq100/119 | 14 | 14 | 0 |
| MCR_seq200b/257 | 5 | 4 | 1（without skin break） |
| MCR_seq200b/326 | 3 | 2 | 1（cefprozil 无应答） |
| MCR_seq200b/475 | 10 | 6 | 4 |
| MCR_v1_seq100/49 | 5 | 4 | 1（no other significant PMH） |
| MCR_v1_seq100/56 | 7 | 5 | 2 |
| MCR_v1_seq100/74 | 13 | 13 | 0 |
| MCR_v1_seq100/91 | 8 | 7 | 1（no postoperative complications） |
| MCR_v2_seq100/179 | 14 | 11 | 3 |
| **合计** | **97** | **82** | **15** |

119 与 74 全中。475 最差：一句话 “Routine laboratory tests and her personal and family history were unremarkable” 三个合取支全部未入集。

## 未入集的 15 条

没有一条是 Kanavel 四征、QTc、室壁厚度这类引擎要用的硬阴性。

| 类型 | 条数 | 例子 |
|---|---:|---|
| 整句丢掉 | 3 | 475 “labs and personal and family history were unremarkable” |
| 合取句尾丢掉 | 2 | 56 抽了 `negative for pan-cytokeratin`，丢掉并列的 `other epithelial markers`；179 抽了 `no bleeding history`，丢掉同一句的 `or medications` |
| 套话 / 残余正常 | 6 | previously healthy、no recurrence until now、no other significant PMH、other values were normal、no postoperative complications、without skin break |
| 治疗无应答 / 未输注 | 2 | 326 cefprozil no lasting benefit；179 increased without transfusion |
| 时间极性被后来的阳性盖住 | 1 | 773 “The patient was initially acyanotic” 未入集，只有后来的 `cyanosis [present]` |
| 极性挂在父检查上 | 1 | 522 “EEG showed diffuse slowing **without seizures**” → `electroencephalography [present]`，quote 里有 without seizures，没有独立的 `seizures [absent]` |

## 对封闭世界争论的含义

`MECHANICAL_RULE_TRIAL_REPORT.md` 第六节写硬约束打不响，有两个机制需要拆开：

1. **指南写阳性特征、不写排除**——本核验不涉及。
2. **病例没写阴性**——本核验针对这一条。

257 上 Kanavel 三征未触发，**不是抽取漏了显式阴性**。vignette 只写了 “focal tenderness over the flexor sheath”，从未写无梭形肿胀、无被动伸指痛。那是封闭世界，不是召回失败。开启封闭世界因子后 6 个格子全部变差，是因为“未匹配”的成员绝大多数是接合失败而不是真的缺失。

引擎真正用得上的显式阴性基本都在：afebrile、无肺栓塞、结核血清学阴性、无 Brugada、室壁厚度正常、CD34/Bcl-2 阴性、抗血小板抗体阴性。QTc 380 ms 原文也没写 “QTc normal”，抽成带数值的 `present` 是对的。

因此：硬约束打不响，是因为**指南特征在病例里根本没被陈述**；抽取漏检约占原文显式阴性的 1/7，且漏的不是判别用的那些。

## 产物

| 文件 | 内容 |
|---|---|
| `explicit_negative_recall_11.csv` | 97 条原文条目的 span、kind、status、匹配到的 finding |
| `explicit_negative_recall_summary.json` | 召回、组成、按例计数、Wilson 区间 |
| `freeze_explicit_negatives.py` | 冻结清单与入集对照脚本 |
