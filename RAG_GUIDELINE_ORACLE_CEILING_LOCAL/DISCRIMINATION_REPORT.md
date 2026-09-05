# 四方法在 48 例深审样本上的假设召回与鉴别能力审查

审查对象：Collapse3c、MultiStance、IMPC、MOSAIC Forest 在 DA+MCR 六个 split 上的运行轨迹
运行产物：`logs/backbone_v1/{dataset}/{arm}/case_stages/{id}.json`（每方法每 split 100 或 200 例，共 24 套）
病例样本：与指南 oracle 上限审计完全相同的 48 例分层概率样本
指南核验：Merck 19e、manifest CPG、WikEM，加上本轮新确认有效的 StatPearls（必要时旁证 Schwartz/Harrison 教材与 PMC-OA）

## 结论先行

把"召回"和"鉴别"拆开之后，四个方法的瓶颈明确落在鉴别侧，而不是召回侧。

| 环节 | 抽样权重外推 |
|---|---|
| 指南来源含直接疾病讨论（D2+D3，上一轮结果） | 84.4% |
| 至少一个方法把金标纳入假设集（strong） | **68.8% ± 7.1** |
| 至少一个方法最终答对 | **53.1% ± 4.7** |

逐方法看，条件鉴别率 P(答对 \| 已把金标纳入假设集) 只有 38.5%–66.7%：

| 方法 | strong 召回 | 判分准确 | **P(答对\|已召回)** |
|---|---|---|---|
| Collapse3c | 42.2% ± 7.4 | 45.3% ± 5.6 | **66.7% ± 5.9**（n=18） |
| MultiStance | 67.2% ± 7.1 | 39.1% ± 6.1 | **44.4% ± 7.6**（n=32） |
| IMPC | 43.8% ± 6.6 | 37.5% ± 5.8 | **38.5% ± 7.9**（n=21） |
| MOSAIC Forest | 40.6% ± 6.1 | 35.9% ± 5.7 | **40.9% ± 7.3**（n=18） |

MultiStance 的召回率几乎是其他三者的 1.6 倍（多立场生成器铺得更宽），但条件鉴别率反而掉到 44.4%，总准确率并没有因此领先。**扩大候选集本身不产生收益，因为选择器把多出来的正确候选又丢掉了。**

进一步对 22 例"至少一个方法召回了金标、且至少一个召回它的方法没选中"的病例逐条人工裁定后，主导失败模式不是知识缺失：

| 主导失败模式 | 例数 | 含义 |
|---|---|---|
| **极性/归属倒置** | **7** | 鉴别性 finding 被原文摘出，然后挂到了错误假设上，或被读成反证 |
| 基准缺陷 | 5 | 决定性 finding 根本不在 vignette 里，金标不可推导 |
| 粒度损失 | 4 | 答了金标的父类或同胞 |
| 诊断轴错位 | 3 | 答了另一条轴（解剖病灶而非病原、结构畸形而非血液学问题） |
| 指南源缺口 | 2 | 四源确实没有该鉴别规则 |
| 选项集缺陷 | 1 | 选项本身彼此同义 |

跨 22 例统计：鉴别性 finding 在指南中可得 13 例、部分可得 4 例；在 vignette 中存在 16 例；被方法逐字摘出 16 例；**但真正被正确用于支持金标的只有 0 例完全成立、3 例部分成立**。

## 1. 方法与判据

### 1.1 假设集的提取位置

四个方法的 trace 结构不同但都保留了完整候选注册表，因此"召回"可以在假设集层面测量，而不只看最终答案：

| 方法 | 逐视角候选 | 合并注册表 | 最终选择 |
|---|---|---|---|
| Collapse3c | `stages.c3.concepts[*]` | `stages.registry[*]`（含 `score`） | `stages.frontier_selector.champion` |
| MultiStance | `stages.c3.stances[*].concepts[*]`（commit/coverage/mechanism 三立场） | 同上（含 `stances`） | 同上（含 `finalists`） |
| IMPC | `stages.D1/D2/D3.candidates[*]` | `stages.registry[*]`（含 `score_logit`、`agent_votes`） | `stages.selector.champion` + `rejected[*].why` |
| MOSAIC Forest | `stages.ax_syndrome / ax_mechanism / ax_modality.candidates[*]` | 同上 | 同上 |

每个候选都带模型自己写的 `support_spans`、`contradict_spans` 和 `why`，这正是判断"是否识别并正确使用了鉴别 finding"所需的材料。四方法的 trace 中都**不含 vignette 全文**（只有 `vignette_chars`）与金标，需要 join `data/benchmarks/.../normalized_cases.json`。

### 1.2 召回分级

用上一轮审计冻结的桥接表与变体逻辑（含本轮新增的驼峰切分），对每个候选标签判定与金标的关系：

- `strong`：候选名含金标的精确名、去括号名、冻结别名或驼峰还原名
- `near`：与金标共享 ≥60% 的信息性词干（父类、同胞、组件级）
- 召回状态取最强者：`champion_strong` > `top2_strong` > `set_strong` > `set_near` > `miss`

并集分布（48 例）：champion 级 15、top2 级 7、集合内 11、仅近似 5、完全未召回 10。

### 1.3 与 D0–D3 的交叉

| 指南能力 | 并集 strong 召回 | 仅近召回 | 未召回 |
|---|---|---|---|
| D3（19+3+5=27 例） | 19 | 3 | 5 |
| D2（13 例） | 9 | 1 | 3 |
| D1（7 例） | 5 | 1 | 1 |
| D0（1 例） | 0 | 0 | 1 |

召回与指南能力弱相关（D3 组召回 70%，D1 组也有 71%），说明模型的候选生成主要靠参数化知识而不是来源覆盖——这与上游"四方法运行中没有诊断时 RAG"的结论一致。

## 2. DA 判分口径的一个独立问题

在做鉴别分析之前必须先说明一个会污染所有 DA 结论的现象。

DA 的 `option_top1` 由 `mapper/records.json` 的 `projection.option_maps` 决定。在 48 例中的 24 例 DA 病例 × 4 方法 = 96 个方法-例对里：

- **32 对（加权 32.8% ± 5.1）的预测同时被映射到全部四个选项**，四个选项的 `option_rank` 都是 1、`posterior` 都是 1.0；其中 **28 对被判为 top-1 正确**。
- 在全部 71 个被判正确的方法-例对中，金标选项与预测的关系是 `subtype_of`（选项是预测的子类，即预测更泛）的有 **52 对**，真正 `equivalent` 的只有 **16 对**。

典型例：`DA_d2_seq100/100`，方法答"Cutaneous metastasis of breast carcinoma"，映射器把它同时判为 A、B、C、D 四个选项的父类（"Telangiectatic metastatic breast carcinoma is a subtype of cutaneous metastasis of breast carcinoma"），四选项全部 matched=true，于是 top-1 记为正确。方法从未在四个选项之间做过任何区分。

**含义**：DA 上的 `option_top1` 在预测为父类时会退化为"只要答对疾病族就算全对"，因此它系统性高估鉴别能力。本报告凡涉及 DA 的正确性，都同时给出自由文本层面的召回等级；两者不一致的 29 个方法-例对全部是"判分正确但自由文本只到父类或未命中"。

MCR 侧不受此影响（用 LLM judge 的 `diagnostic_hit` 判自由文本），但 MCR 的 `options` 字段本身是坏的：B–H 选项是病例报告讨论段落的截断片段，部分直接泄漏答案（如 `MCR_seq200b/326` 的 G "Brucellosis was confirmed when the Gram"、`MCR_v2_seq100/234` 的 E "Spindle cell hemangioma" 与 A 重复）。由于 MCR 不按选项判分，这不影响本次结论，但任何未来在 MCR 上做选项式评测的实验都必须先修这个字段。

## 3. 22 例鉴别失败的逐类解剖

完整逐例表见 `discrimination_findings_22.csv`，证据包见 `discrimination_pack.md`。

### 3.1 极性/归属倒置（7 例）——最主要的失败模式

这类病例满足全部四个前置条件：指南有规则、vignette 有 finding、方法逐字摘出了它、并把它写进了选择器理由——然后把它挂到了错误的假设上。

**`MCR_v1_seq100/74` CPVT（D3）** 是最干净的例子。StatPearls 定义长 QT 综合征为 QTc >440 ms（男）/>460 ms（女），定义 CPVT 为"运动相关的多形性或双向性室速"。vignette 给出 QTc = 380 ms，按规则这是正常值、直接排除 LQTS。三个方法都摘出了"QTc of 380 ms"，并在选择器理由中把它作为**支持 Long QT Syndrome 的正面证据**。唯一答对的 Forest 则完全没有使用 QTc——它答对了，但不是因为做对了鉴别。

**`MCR_v1_seq100/91` 血管肉瘤（D2）**：vignette 给出 CD31+、Fli-1+、CD34−、Bcl-2−。StatPearls 明确孤立性纤维性肿瘤是 CD34+/STAT6+ 并带 NAB2-STAT6 融合，血管肉瘤表达 CD31/CD34/ERG。CD34 阴性本身就排除 SFT/血管外皮瘤。四个方法全部摘出了完整的免疫组化面板（包括"negative staining for CD34"），IMPC 与 Forest 把这条阴性结果直接列为**支持血管外皮瘤**的证据。

**`DA_d2_seq100/119` 疣状汗孔角化（D2）**：StatPearls 称鸡眼样板层（cornoid lamella）是汗孔角化症的独特组织学标志，而 Darier/Grover 病的组织学是棘层松解与角化不良。四个方法全部摘出"well-developed cornoid lamellae"并在选择器理由中把它作为 **Darier 或 Grover 病的支持证据**。

**`MCR_seq200b/257` 领扣状脓肿（D3）**：Merck 把 collar-button abscess 列为掌部脓肿的一种，Schwartz 有专节描述它是"蹼间隙的筋膜下感染，掌侧蹼间隙皮肤与掌腱膜粘连阻止其向侧方扩散"；StatPearls 则给出竞争假设化脓性屈肌腱鞘炎的四条 Kanavel 征。vignette 的"palmar web space"与钝性背侧外伤史都在，四个方法全部摘出 web space 并把它作为**屈肌腱鞘炎的支持证据**写进选择器理由。

**`DA_d2_heldout100/272` 窗口期 AMI（D3）**：StatPearls 说 hyperacute T 波"提示早期缺血并将进展为 ST 抬高"，ACC/AHA ACS 指南给出肌钙蛋白在症状后 1–2 小时才开始升高、必须在疼痛发作 3 小时后仍正常才能排除 MI 的规则。vignette 的疼痛只有约 20 分钟，因此单次正常肌钙蛋白毫无排除价值。四个方法全部摘出了这两条事实，三个把正常肌钙蛋白当作**反对心肌梗死的证据**。

另两例是 `DA_d2_heldout200b/773`（把 PFO 与右向左分流当作 Eisenmenger 的正面支持，而 Eisenmenger 要求先存在大的左向右分流）与 `MCR_seq200b/475`（Collapse3c 与 MultiStance 已把 biceps/triceps/deltoid 的额外失神经正确挂到神经痛性肌萎缩候选上，选择器仍选了孤立的骨间前神经综合征；IMPC 与 Forest 的证据台账里根本没有这三块肌肉）。

**这一类的共同点**：不是检索问题，也不是知识问题，而是**证据-假设绑定关系错误**。模型有能力定位鉴别性 finding，却没有把"这条 finding 属于哪个假设、以什么极性属于"这件事算对。这与上游第 6 条结论（"最危险的是相关但只支持父类/竞争诊断的文本"）是同一现象在无 RAG 条件下的内生版本。

### 3.2 基准缺陷（5 例）——金标从 vignette 不可推导

这五例不是方法的失败：

- **`DA_d2_heldout200b/551` 利格列汀诱发的急性胰腺炎**：vignette 的用药清单列了 11 种药，**没有利格列汀**。金标要求的归因步骤无法执行。三个方法答"急性胰腺炎"并靠父类映射被记为正确。
- **`MCR_v2_seq100/146` 弥漫大 B 细胞淋巴瘤**：vignette 写"取了回肠与结肠节段活检"，但**从不报告活检结果**，同时给出 QuantiFERON 阳性与流行区暴露。四个方法答肠结核，这是所给信息下最合理的读法。
- **`MCR_v2_seq100/202` 套细胞淋巴瘤**：只有腭部缓慢生长肿物的临床描述，无组织学、无免疫表型（无 cyclin D1/t(11;14)）。四个方法答腭隆突或巨细胞肉芽肿。
- **`MCR_v2_seq100/234` 梭形细胞血管瘤**：只有影像，无活检结果。
- **`DA_d2_heldout200b/566` 高级别(3A)滤泡淋巴瘤 IVB 期**：vignette 给的是 CD5−/CD10− B 细胞、BCL2 异常表达、Ki-67 升高，既无滤泡分级也无分期；且 CD10 阴性本身就与滤泡淋巴瘤相悖，所给发现并不支持金标优于选项 C（DLBCL）。

**含义**：把这五例计入"方法失败"会高估失败率。48 例中至少 10.4% 的病例在 vignette 层面就不可解，任何方法改进都无法回收。

### 3.3 诊断轴错位（3 例）

方法回答了另一条轴上的正确答案。

**`MCR_seq200b/326` 布鲁氏菌病（D3）** 最典型：接触未经巴氏消毒的羊胃 + 手部伤口、血培养革兰阴性杆菌、头孢丙烯无效——四个方法**全部摘出了这些线索，并且在自己的注册表里正确挂到了 Brucellosis 候选下**，然后选择器一致选了解剖病灶（脊髓硬膜外脓肿 / 脊柱椎间盘炎）。选择器理由里完全没有提暴露史。也就是说，正确假设与正确证据都在，选择阶段的目标函数偏向"最能解释影像所见的病灶"，而不是"最能解释全部证据的病因"。

`MCR_seq200b/409`（答机制层的胰腺胸膜瘘，金标要的是其上游的慢性坏死性胰腺炎）与 `MCR_v2_seq100/179`（答结构性心脏畸形，金标要的是血液学问题）同理。179 的 MultiStance 甚至把血小板/饱和度序列当作反对自己答案的证据仍未改选。

### 3.4 粒度损失（4 例）与指南源缺口（2 例）

粒度损失：`DA_d2_seq100/5`（答巨细胞瘤，金标是巨细胞修复性肉芽肿，缺"无细胞异型性"这一分界）、`MCR_v1_seq100/49`（IMPC/Forest 停在"脓肿"，Collapse3c/MultiStance 答对了残端阑尾炎）、`DA_d2_seq100/19`（答骨转移，金标是直接侵犯）、`DA_d2_heldout200b/522`（复合诊断被拆散，三个方法答紧张症、一个答路易体痴呆，无一提出二者的合并）。

指南源缺口只有 2 例：`DA_d2_heldout100/348`（后部角膜营养不良仅列表级，D1）与 `MCR_v1_seq100/56`（p63 阳性/细胞角蛋白阴性在牙龈部位的判读规则在四源中不可得，D2）。

### 3.5 选项集缺陷（1 例）

`DA_d2_heldout200b/646` 的四个选项中 A、C、D 指同一实体（"放射性孤立性直肠溃疡" / "放射性直肠溃疡（放射性直肠病）" / "放射性直肠炎伴溃疡"）。四个方法都答"放射性直肠炎"，它们之间的判分差异完全由选项映射产生，与推理无关。

## 4. 对四方法设计的直接含义

1. **候选生成不是瓶颈，绑定与选择才是。** MultiStance 用三立场把召回抬到 67.2%，条件鉴别率却是四者中第二低。下一版应把预算从"生成更多候选"移到"为每条 finding 判定它支持/反对哪个候选、以及该 finding 是否具备判别力"。
2. **需要显式的阈值与时相语义。** 本轮最干净的三个失败（QTc 380 ms 判为 LQTS 支持、20 分钟疼痛的正常肌钙蛋白判为 MI 反证、CD34 阴性判为 SFT 支持）都是数值/时相/阴性结果的语义被丢掉。`support_spans` 只记录了字符串，没有记录"该值相对参考区间的方向"和"该阴性结果排除了什么"。这是一个可以在 schema 层修的缺陷，不需要 RAG。
3. **选择器的目标函数需要区分诊断轴。** 布鲁氏菌病与低氧性血小板减少两例说明，当证据同时支持一个解剖病灶和一个病因/机制时，现有选择器偏向病灶。Forest 已经有 syndrome/mechanism/modality 三轴生成器，但 selector 把三轴压回单一冠军，轴信息在选择阶段丢失。
4. **评测口径必须先修。** 在 DA 上，32.8% 的方法-例对因父类映射被无差别记功；在 MCR 上选项字段被污染。这两项不修，任何 RAG on/off 或方法间比较的效应量都不可信。
5. **五例基准缺陷应从主指标中剔除或单列。** 它们在 48 例样本中占 10.4%，且集中在 MCR 家族的"只给临床描述不给病理"型病例。

## 5. 可复查产物

数据（`RAG_GUIDELINE_ORACLE_CEILING_LOCAL/`）：

| 文件 | 内容 |
|---|---|
| `method_hypothesis_recall_48.jsonl` | 48 例 × 4 方法的完整假设集、支持/反对 span、选择器理由、召回等级、判分与 DA 选项映射明细 |
| `discrimination_scope.csv` | 22 例深审范围与入选原因 |
| `discrimination_pack.md` | 逐例证据包：vignette 全文 + 四方法候选表 + 逐视角理由 + 淘汰理由 |
| `discrimination_findings_22.csv` | 逐例鉴别 finding、四源可得性、vignette 存在性、是否被摘出、是否被正确使用、失败模式 |

脚本（`analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL/`）：`extract_method_hypotheses.py`、`build_discrimination_pack.py`、`check_discriminator_use.py`、`classify_discrimination_failures.py`、`probe_source.py`。

```bash
python analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL/extract_method_hypotheses.py
python analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL/build_discrimination_pack.py
python analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL/classify_discrimination_failures.py
# 单例核验示例
python analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL/check_discriminator_use.py \
  --case MCR_v1_seq100/74 --patterns 'QTc of 380||380 ms||exertion||bidirectional'
```

## 限制

1. **单审阅、小样本。** 22 例逐条裁定由单人完成；设计 SE 已给出，但按方法分层后每格 n 很小，条件鉴别率的区间偏乐观。
2. **召回判据是词面的。** `strong` / `near` 基于标签变体与词干覆盖，不是临床等价判断。父类型答案（如"Giant Cell Tumor" vs "giant cell reparative granuloma"）被判为 `near`，其临床可接受程度需个案判断。
3. **"被正确使用"依赖模型自陈。** 判断依据是 trace 里的 `support_spans` / `contradict_spans` / `why`，即模型自己写的归因。若模型内部实际用了某条证据却没写出来，本方法会低估"使用"。反向的风险（写了但没真正影响决策）同样存在。
4. **只审了主 `_v1` 运行。** 各 split 下还有 `_r2` 复跑版本，未纳入；因此单例结论不代表方法的可重复行为，方法间差异未做多次运行的方差估计。
5. **未做反事实实验。** 本报告只能说明"鉴别 finding 在场却未被正确使用"，不能证明"若修正绑定关系就会答对"。要证明后者需要在 selector 层做受控消融。
