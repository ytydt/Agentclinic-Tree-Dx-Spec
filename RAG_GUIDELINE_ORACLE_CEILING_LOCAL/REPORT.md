# 本地全量指南语料下的 oracle 诊断能力上限复审（D0–D3 同口径）

上游审计快照：`4f865ce87`、`08bc927ea`（远端，仅三份指南文件）
本次复审快照：本地工作树 `e4ba16832`
病例样本：与上游完全相同的 48 例分层概率样本（DA 400 + MCR 400 抽出，六层各 8 例）
量尺：与上游完全相同的 D0–D3 rubric，未做任何放宽或收紧

## 结论先行

上游审计的核心数字被显著低估，原因是可审计语料只有三份文件（Merck 19e、manifest CPG、WikEM），而 PMC-OA、StatPearls、教材集在远端是 LFS 指针、在本地才有实体文件。用同一份 48 例账本、同一套 rubric、同一套抽样权重重判后：

| 指标（抽样权重外推） | 三源 T1（上游） | 全本地源 T3（本次） | 配对差 Δ ± SE |
|---|---|---|---|
| **D3** 直接解释 vignette 决定性线索 | 21.88% | **54.69%** | **+32.81 pp ± 7.26** |
| **D2+D3** 至少存在直接疾病讨论 | 51.56% | **84.38%** | **+32.81 pp ± 6.50** |
| D1 仅父类/组件/列表/名字级 | 35.94% | 12.50% | −23.44 pp |
| D0 完全不可达 | 12.50% | **3.12%** | −9.38 pp |
| 平均等级 | — | — | **+0.750 级 ± 0.126** |

48 例中 **24 例提级、0 例降级**（配对精确检验单侧 `p = 5.96e-8`）。等级迁移：D0→D3 3 例、D0→D2 2 例、D1→D3 7 例、D1→D2 5 例、D2→D3 7 例；仍停在 D0 的只剩 1 例。

三条需要同时记住的限定：

1. **上限不是可兑现能力。** 这里测的是 oracle 检索（已知金标、允许全库定向搜索、允许跨切片拼接）下来源是否含有足够规则。上游第 4 节记录的检索链损失（E11 的 400 个 bundle 里只有 3.50% 含完整标签、400/400 被 1,400 字符截断）在本次复审中一点没有改变。来源上限从 51.56% 抬到 84.38%，检索链能送到模型的比例并没有随之改变。
2. **提级高度依赖 StatPearls。** 24 例提级中 22 例的判定证据包含 StatPearls，16 例以 StatPearls 为首要来源；只有 1 例可以单靠 PMC-OA 成立。若本地语料只补 PMC 而不补 StatPearls，收益会大幅缩水。
3. **污染风险显著且必须单独看。** 48 例中 31 例（加权 62.50%）在 case-report 语料里存在实体命中且线索覆盖过半，属于高近重复风险。本次判定全程**不把 case-report 语料计入指南能力**，只作为污染探针单独报告；但这说明如果生产 RAG 索引里混入了 MedCaseReasoning/RareArena 类的病例报告，D3 会被"检回原文"而非"读懂指南"虚高。

## 1. 为什么需要复审

上游 `RAG_PIPELINE_INVENTORY.md` 记录：远端仓库中除三份文件外，PMC-OA、StatPearls、教材集的 chunk 文件与绝大多数索引文件都是 Git LFS 指针，无法读取内容。因此上游 D0–D3 的分母其实是"三份文件"，报告里 51.56% / 21.88% 这两个数只能解释为**三源子语料**的能力，不能解释为"仓库指南能力"。

本地实际可用语料：

| 层级 | 来源 | chunk 数 | 体积 | 上游可见 |
|---|---|---|---|---|
| T1 | Merck Manual 19e | 9,629 | 19 MB | 是 |
| T1 | manifest CPG | 39,091 | 73 MB | 是 |
| T1 | WikEM DDx | 1,055 | 1.0 MB | 是 |
| T2 | PMC-OA DDx | 317,710 | 487 MB | 否（LFS 指针） |
| T3 | StatPearls | 367,799 | 220 MB | 否（LFS 指针） |
| T3 | 教材集 | 125,847 | 110 MB | 否（LFS 指针） |
| — | 合计（计入能力） | **861,131** | ~910 MB | — |
| 探针 | case report | 77,849 | 149 MB | 否；**永不计入能力** |

未切片原文同样在本地可用：Merck 全文 `merck_manual_19e_extracted.txt`（12.4 MB）、PMC-OA 5,869 篇原文、WikEM 与 manifest CPG 的 `data/cpg/text/*` 目录。这是本次能做"未切片核验"的前提。

## 2. 方法：复用上游口径，只换语料范围

### 2.1 严格保持不变的部分

直接 import 上游 `audit_rag_guideline_capacity.py` 的 `load_cases`、`bridge_tables`、`label_variants`、`norm`、`bounded_contains`，以及上游冻结的别名/规范名桥接表。48 例样本、分层、抽样概率与权重、D0–D3 rubric 文本、加权汇总脚本 `summarize_manual_source_coverage.py` 全部原样复用，未改一行。

新账本 `manual_source_coverage_48_local_expanded.jsonl` 保留上游每条记录的全部字段，只覆写 `diagnostic_support`，并新增 `upstream_diagnostic_support`、`grade_delta`、`deciding_sources`、`guideline_tier_reach`、`contamination_probe` 五个字段，因此两版账本可以逐例配对比较。

### 2.2 必须改造的部分

**驼峰金标切分。** 上游 `norm()` 把 MCR 的驼峰金标（`ClearCellSarcoma`、`ProstateStromalSarcoma`、`StumpAppendicitis`）当成单 token，无法与自然语言写法匹配，会对 MCR 家族造成系统性漏召。新增 `camel_split` 变体类型并给予与 `exact` 同等权重（+6.0）。这是 MCR 提级幅度（+0.938 级）高于 DA（+0.562 级）的部分原因——上游对 MCR 的低估里包含了一部分匹配工具缺陷，而非纯粹的语料缺失。

**概念锚点。** 把上游人工账本里的 `matched_concept` 作为额外检索锚（`oracle_concept`，权重 +2.0），使 oracle 搜索能沿人工已确认的概念继续扩展。

**规模。** 86 万切片全量扫描，用最长 token 触发的短语索引，单次全量扫描约数分钟量级。

### 2.3 切片不完整性的两条核验路径

这是本次复审专门增加的环节，用来回答"D0/D1 是真的语料没有，还是被切片切碎了"。

**路径 A：去切片按序还原。** 按 `document_key` + chunk 序号把切片重新拼回文档，在文档级重跑实体/线索匹配，与"最佳单切片"对照。教材源的"文档"是整本书（如 `Pathology_Robbins` 一本 5,297 切片），文档级命中没有意义，从统计中剔除。

在 371 个真实文档（非整本书）上：

- **28 个文档的金标实体只有在去切片后才可达**——单切片里被切断，拼回后才出现。
- 143/371 个文档在去切片后新增至少 1 条决定性线索，平均新增 0.65 条，最多 4 条。
- **32/48 例**至少有一个真实文档因去切片而多出 1 条以上线索。

**路径 B：未切片原文滑窗核验。** 直接在原始 `.txt` 上做 3,000 字符窗口 / 1,500 字符步长扫描，绕开切片管线。在有原文的四个源（Merck、manifest CPG、WikEM、PMC-OA）内做同口径对比：13 例的未切片窗口比最佳单切片多命中线索（合计 +17 条），3 例更少（窗口边界切断所致）。

**切片保真度定量。** 121 个有原文对照的文档，重组文本相对原文的 token 保留率：

| 源 | 文档数 | 中位保留率 | 均值 | p10 | <0.9 的文档数 |
|---|---|---|---|---|---|
| WikEM | 12 | 0.937 | 0.935 | 0.917 | 0 |
| PMC-OA | 78 | 0.802 | 0.800 | 0.721 | 71 |
| manifest CPG | 31 | **0.429** | 0.471 | 0.143 | 28 |
| 全部 | 121 | 0.796 | 0.729 | 0.342 | — |

manifest CPG 的切片只保留了原文的四成左右内容（最差 8.5%），PMC-OA 丢失约两成。这与上游第 5 节"PDF 到 chunk 的结构损失"是同一类问题，但这里给出了可量化的比例：**即使 oracle 检索命中了正确文档，切片层面平均已经丢掉 20%–57% 的原文 token**。因此本报告的 D0–D3 是在"允许跨切片拼接 + 允许回原文"的最宽松条件下测得的，是真正的上限。

### 2.4 扫描器与上游判定的一致性校验

用 T1 三源的实体可达强度回检上游等级，作为扫描器未跑偏的证据：上游 6 例 D0 中**没有任何一例**在 T1 出现强实体命中（exact / camel_split / 去括号 / 别名），而上游 10 例 D3 中 7 例有强命中。方向与上游判定一致。

## 3. 复审结果

### 3.1 总体与分家族

| 等级 | 总体 T1 | 总体 T3 | DA T1 | DA T3 | MCR T1 | MCR T3 |
|---|---|---|---|---|---|---|
| D0 | 12.50% | 3.12% | 12.50% | 6.25% | 12.50% | **0.00%** |
| D1 | 35.94% | 12.50% | 28.12% | 15.62% | 43.75% | 9.38% |
| D2 | 29.69% | 29.69% | 43.75% | 31.25% | 15.62% | 28.12% |
| D3 | 21.88% | **54.69%** | 15.62% | 46.88% | 28.12% | **62.50%** |
| D2+D3 | 51.56% | **84.38%** | 59.38% | 78.12% | 43.75% | **90.62%** |

配对差（分层加权，含设计 SE）：

| 家族 | Δ D2+D3 | Δ D3 | Δ 平均等级 |
|---|---|---|---|
| 总体 | +32.81 pp ± 6.50 | +32.81 pp ± 7.26 | +0.750 ± 0.126 |
| DA | +18.75 pp ± 6.47 | +31.25 pp ± 10.30 | +0.562 ± 0.155 |
| MCR | +46.88 pp ± 11.27 | +34.38 pp ± 10.23 | +0.938 ± 0.198 |

MCR 的 D2+D3 从 43.75% 跳到 90.62%，是本次最大的单项变化。MCR 金标多为单一罕见实体名（`StumpAppendicitis`、`ClearCellSarcoma`、`SpindleCellHemangioma`），StatPearls 的"一病一篇"结构正好覆盖这类实体；而 DA 金标常是复合诊断（"X 合并 Y"、"药物 A 诱发的 B"），单篇文章给不出组合，所以 DA 的 D2→D3 提升明显但 D1→D2 提升有限。

### 3.2 提级来源归因

24 例提级的判定证据来源（一例可含多源）：StatPearls 22 例、PMC-OA 14 例、教材 10 例。若只看首要来源：StatPearls 16、PMC-OA 6、教材 2。可以单靠一个新源成立的：仅 StatPearls 6 例，仅 PMC-OA 1 例。

**这意味着"补 PMC"这个直觉性的补法回报最小。** 用户最初的判断是远端缺 PMC，但真正把 D3 从 21.88% 抬到 54.69% 的主力是 StatPearls——它对罕见实体的覆盖密度远高于 PMC-OA 的综述文献。PMC-OA 的作用集中在 DA 家族的复合诊断（Netherton 三联征、前列腺间质肉瘤 mpMRI + STUMP 鉴别、透明细胞肉瘤 EWSR1-ATF1），即"需要一篇专题综述才能拼出的组合"。

### 3.3 仍然不可达的部分

**唯一的 D0**：`DA_d2_heldout200b/754`（MIC-CAP 综合征合并 Mowat-Wilson 综合征）。全库既无 MIC-CAP，也无 ZEB2 表型描述，双综合征复合诊断在任何层级都不可达。

**7 例仍停在 D1**，共性是"实体名出现但无实体描述"或"两个概念各自存在但无因果链接"：

- `DA_d2_heldout100/348` 后部鳄鱼皮样角膜营养不良——只在列表里出现名字。
- `DA_d2_heldout200b/522` 紧张症继发于路易体痴呆——两病各自完整，无因果连接。
- `DA_d2_seq100/118` SARS-CoV-2 全葡萄膜炎继发炎症性视神经病变——同上。
- `DA_d2_seq100/149` 软组织巨细胞瘤——只有骨巨细胞瘤和泛化软组织肉瘤。
- `MCR_v1_seq100/114` 骶尾部皮下（脊髓外）室管膜瘤——只有颅内/椎管内，该部位仅存在于 case report。
- `MCR_v2_seq100/179` 低氧诱导血小板减少——发绀型心脏病只连到红细胞增多，不连到血小板减少。
- `MCR_v2_seq100/234` 梭形细胞血管瘤——只作为鉴别列表名和参考文献标题出现。

**6 例仍停在 D2**，共性是"实体描述完整但缺一个金标定义性限定"：色素性乳房外 Paget 病的色素变异型、利格列汀（只有 DPP-4 类级别）、滤泡淋巴瘤 3A 亚分级与 IVB 分期、放射性孤立性直肠溃疡的"其余直肠正常"形态、梭形细胞鳞癌的牙龈部位与 p63+/CK− 读法、滤泡状甲状腺癌的胸骨柄侵犯路径。

D1 与 D2 的残余共同点很明确：**缺的不是疾病知识，是"组合"与"部位/亚型限定"**。这直接支持上游第 8 节的判断——桥接不能只做同义词表，必须显式携带部位、病因、亚型/阶段与关系约束。

### 3.4 逐例对照

完整表见 `readjudication_diff_48.csv`；提级部分：

| case | family | gold | T1 | T3 | Δ | 首要来源 | 污染风险 |
|---|---|---|---|---|---|---|---|
| DA_d2_heldout100/261 | DA | Cutaneous malakoplakia | D0 | D3 | +3 | statpearls | high |
| MCR_v1_seq100/65 | MCR | myelolipoma | D0 | D3 | +3 | statpearls | medium |
| MCR_v2_seq100/232 | MCR | eccrine chromhidrosis | D0 | D3 | +3 | statpearls | none |
| DA_d2_heldout100/423 | DA | Leptomeningeal lymphoplasmacytic lymphoma | D1 | D3 | +2 | textbooks | high |
| DA_d2_seq100/119 | DA | Eruptive pruritic papular porokeratosis | D0 | D2 | +2 | statpearls | none |
| DA_d2_seq100/173 | DA | Netherton syndrome | D1 | D3 | +2 | pmc_oa | high |
| DA_d2_seq100/5 | DA | Left maxillary giant cell reparative granuloma | D1 | D3 | +2 | statpearls | low |
| MCR_seq200b/291 | MCR | Necrolytic acral erythema | D1 | D3 | +2 | statpearls | high |
| MCR_seq200b/331 | MCR | tumoral calcinosis | D0 | D2 | +2 | statpearls | low |
| MCR_v2_seq100/133 | MCR | ProstateStromalSarcoma | D1 | D3 | +2 | pmc_oa | high |
| MCR_v2_seq100/196 | MCR | vertebral hemangioma | D1 | D3 | +2 | statpearls | medium |
| MCR_v2_seq100/215 | MCR | ClearCellSarcoma | D1 | D3 | +2 | pmc_oa | high |
| DA_d2_heldout100/303 | DA | Cutaneous Bacillus cereus infection | D1 | D2 | +1 | statpearls | low |
| DA_d2_heldout200b/529 | DA | Multidrug-resistant CMV infection | D2 | D3 | +1 | statpearls | high |
| DA_d2_heldout200b/735 | DA | CD5-positive DLBCL | D2 | D3 | +1 | pmc_oa | high |
| DA_d2_seq100/100 | DA | Telangiectatic metastatic breast carcinoma | D2 | D3 | +1 | pmc_oa | medium |
| DA_d2_seq100/216 | DA | COVID-19 with ARDS | D2 | D3 | +1 | statpearls | high |
| MCR_seq200b/375 | MCR | gliomatosis cerebri | D1 | D2 | +1 | textbooks | low |
| MCR_seq200b/405 | MCR | Synovial sarcoma | D1 | D2 | +1 | statpearls | medium |
| MCR_seq200b/409 | MCR | Chronic necrotizing pancreatitis | D2 | D3 | +1 | statpearls | high |
| MCR_v1_seq100/49 | MCR | StumpAppendicitis | D2 | D3 | +1 | statpearls | high |
| MCR_v1_seq100/91 | MCR | Angiosarcoma | D1 | D2 | +1 | statpearls | high |
| MCR_v2_seq100/146 | MCR | Diffuse large B cell lymphoma | D2 | D3 | +1 | pmc_oa | high |
| MCR_v2_seq100/202 | MCR | Mantle cell lymphoma | D1 | D2 | +1 | statpearls | high |

上游 10 例 D3 按单调性保留：扩展语料是三源的严格超集，已达 D3 的病例不可能因增源而失去证据，故未逐条重判（账本中标注 `confidence: inherited`）。

## 4. 污染风险

case-report 语料（77,849 切片，含 MedCaseReasoning/RareArena 同源材料）从未计入任何等级判定，只作为探针扫描。按"实体命中文档数 + 决定性线索覆盖比例"分级：

| 风险 | 例数 | 加权占比 |
|---|---|---|
| high（有实体命中且线索覆盖 ≥ 半数） | 31 | 62.50% ± 7.42 |
| medium | 8 | — |
| low | 5 | — |
| none | 4 | — |

7 例的 case-report 线索覆盖率为 **1.0**（全部决定性线索都能在病例报告里找到），其中 `DA_d2_heldout200b/551`（利格列汀胰腺炎）、`DA_d2_seq100/118`（SARS-CoV-2 全葡萄膜炎视神经病变）、`MCR_v2_seq100/234`（梭形细胞血管瘤）在指南层仍分别只有 D2/D1/D1。**这三例是最典型的污染陷阱**：如果生产索引把 case report 与指南混在同一库里，它们会表现为 D3，但那是把答案原文检索回来，不是指南推理。

操作含义：任何用于报告 RAG 收益的索引，必须能在切片级区分 `publisher ∈ {case_report}` 并可关闭；报告中的 RAG on/off 效应必须在关闭该分区的条件下给出，否则 62.50% 的样本存在近重复泄漏。

## 5. 与上游结论的关系

上游六项主结论中，**第 2 条需要按本报告修订**，其余五条不受影响：

- 上游结论 2（"可见指南子语料诊断能力有限"，D2+D3 = 51.56%、D3 = 21.88%）——**修订为**：三源子语料 51.56% / 21.88%，全本地指南语料 84.38% / 54.69%。原数字应明确标注为"三源子语料"，不能作为仓库指南能力。
- 结论 1（四个目标方法无诊断时 RAG）、结论 4（实际检索链几乎不兑现来源能力）、结论 5（E11 不构成对 RAG 的否定）、结论 6（相关但只支持父类的文本最危险）——本次未改变任何检索链证据，全部维持。
- 结论 3（完整金标字符串既非必要也非充分）——维持，且本次新增支持：`Synovial sarcoma`、`Ependymoma`、`Angiosarcoma`、`Mantle cell lymphoma` 四例在扩展语料中仍未达 D3，原因仍是"名字在、部位/组合不在"。

由此产生的实验含义：**来源能力不再是瓶颈的首因**。三源条件下 D2+D3 只有 51.56%，"来源没有"与"检索没送到"混在一起；全本地语料下来源侧上限已达 84.38%，而检索侧的 3.50% 完整标签命中率没有变化，因此上游第 11 节的 E0（先修数据与索引）应把优先级从"补语料"移到"补索引与桥接"，并且必须先把 StatPearls 分区接入索引——它贡献了 24 例提级中的 22 例。

## 6. 可复查产物

数据与账本（`RAG_GUIDELINE_ORACLE_CEILING_LOCAL/`，与上游目录布局对齐）：

| 文件 | 内容 |
|---|---|
| `manual_source_coverage_48_local_expanded.jsonl` | 复审后 48 例账本，含上游等级、delta、判定来源、分层可达性、污染探针 |
| `readjudication_diff_48.csv` | 逐例 T1 vs T3 对照表 |
| `design_estimates_local_expanded.json` | 分层加权估计（由上游 `summarize_manual_source_coverage.py` 原样生成） |
| `expanded_oracle_scan_48.jsonl` | 86 万切片全量 oracle 扫描原始结果 |
| `dechunked_evidence_48.jsonl` | 去切片文档重组、保真度、线索增益 |
| `unsliced_window_capacity_48.jsonl` | 未切片原文滑窗核验 |
| `adjudication_pack_48.md`、`pack_D0.md`–`pack_D3.md` | 人工裁定证据包 |

脚本（`analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL/`）：`scan_expanded_source_capacity.py`、`dechunk_and_pack.py`、`scan_unsliced_sources.py`、`probe_source.py`、`build_adjudication_pack.py`、`readjudicate_local_expanded.py`。

复现：

```bash
python analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL/scan_expanded_source_capacity.py
python analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL/dechunk_and_pack.py
python analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL/scan_unsliced_sources.py
python analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL/readjudicate_local_expanded.py
python RAG_GUIDELINE_SOURCE_CAPACITY_AUDIT/summarize_manual_source_coverage.py \
  --ledger RAG_GUIDELINE_ORACLE_CEILING_LOCAL/manual_source_coverage_48_local_expanded.jsonl \
  --out    RAG_GUIDELINE_ORACLE_CEILING_LOCAL/design_estimates_local_expanded.json
```

## 限制

1. **单审阅、小样本。** 48 例、单人裁定，与上游同一限制。设计 SE 已给出，但 D0/D1 这类低频格的分层方差在 n=8 时不可靠，D0 的 CI 下界被截到 0。
2. **上游 D3 未逐条重判。** 依据单调性继承，若上游某例 D3 判定本身有误，本次不会纠正。
3. **等级判定含主观边界。** D2 与 D3 的分界（"是否解释了决定性线索"）在复合诊断上尤其难判，账本中每例都记录了 `confidence`（high/medium）与判定理由，medium 的 11 例应视为可争议。
4. **oracle 条件极宽松。** 允许已知金标定向搜索、跨切片拼接、回原文滑窗。真实 RAG 无一具备，因此 84.38% 是严格上界而非预期表现。
5. **教材源的文档粒度问题。** 教材切片的 `document_key` 是整本书，去切片统计中已剔除；这意味着教材源的"文档级增益"未被量化，其贡献只通过人工阅读切片确认。
6. **切片保真度只覆盖 121 个有原文对照的文档。** StatPearls 与教材无 `data/cpg/text/` 原文镜像，其切片损失率未测；StatPearls 切片是 section 级（`标题 > 小节`），结构上比 manifest CPG 更完整，但未定量。
