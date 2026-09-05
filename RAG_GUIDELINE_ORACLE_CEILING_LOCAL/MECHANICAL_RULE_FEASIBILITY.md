
# 11 例可分病例的落地可行性核验：检索侧与表示侧

针对两个问题：(1) RAG 能否取到手工流程所需的全部切片；(2) 用什么 schema 存放 LLM 从切片中提取的信息、做哪些预处理，使后续决策规则可以由无 LLM 调用的机械程序构建。本轮为理论核验，未做任何模型调用；所有测量都是对冻结语料的正则与统计。

结论先行：**9/11 例的全部必要断言都能从单个切片中获得**，被卡住的 2 例正是上一轮判定为"需语料外知识"的那两例，两条独立路径给出一致结果。但检索不能由 vignette 驱动——26 条断言中有 5 条的主语在 vignette 里根本不出现，必须按候选假设逐个检索。表示侧的关键不是把切片文本存起来，而是把每条断言拆成 `(主语, 发现, 关系, 极性, 情态, 阈值, 语境类型)` 七元组；其中**关系与极性、以及语境类型**是机械程序无法从文本恢复、必须在 LLM 抽取阶段定死的字段。

## 一、检索侧核验

### 方法

把 11 例的每条决策分支拆成原子断言，形式为 `(主语, 谓语[, 阈值])`——主语是断言所述的诊断，谓语是发现或规则。共 26 条。对每条断言在六源语料中测量：是否存在同时含主语与谓语的单个切片（`single_chunk`）、还是二者只在同一文档的不同切片中出现（`split`）、还是根本没有。随后**逐条阅读命中的原文**，判定该段落是否真的陈述了这条规则，而不是恰好两个词共现。

逐条阅读是必要的。26 条中有 4 条的首位命中是无效共现：

- `91.a`（血管肉瘤 / CD31）首位命中是一张肝活检标志物表；
- `179.b`（紫绀型先心病 / 血小板减少）唯一命中是 Nelson 儿科表 149-1——"红细胞增多—紫绀型心脏病"与"血小板减少"是同一张表的**不同行**，被切成了一个切片；
- `773.c`（PFO 非大量分流）首位命中是卒中章节讲腔隙性梗死；
- `326.c`（布鲁氏菌为革兰阴性）首位命中是革兰阴性菌致 DIC。

表格伪共现（`179.b`）是最值得注意的一类：它在任何基于切片的字符串或向量匹配下都无法与真实断言区分。

### 结果

| 裁定 | 条数 | 含义 |
|---|---:|---|
| `stated` | 18 | 首位命中段落直接陈述该规则 |
| `stated_but_buried` | 4 | 规则在语料中存在，但排名最高的共现段落是无效的 |
| `partial` | 1 | 只陈述了规则的一部分 |
| `split` | 1 | 主语与谓语从未同处一个切片 |
| `absent` | 2 | 语料中无任何段落陈述 |

**可从单切片获得：22/26。** 按病例聚合（只统计该例流程实际需要的断言）：

- **9 例全部覆盖**：522、773、119、257、326、475、49、74、56
- **2 例被卡住**：91（缺 CD34+/Bcl-2+ 与内皮标志的对照表述，语料只有孤立性纤维性肿瘤的 STAT6 重排）、179（`179.a` 跨切片、`179.b` 语料中不存在）

这两例正是 `MANUAL_DECISION_TREE_REPORT.md` 中判为 `separable_needs_outside` 的两例。检索侧的独立测量复现了手工裁定的结论。

### 三个结构性发现

**1. 检索必须按假设条件化，不能由 vignette 驱动。** 26 条断言中有 5 条的主语在本例 vignette 中一次都没出现：Eisenmenger 综合征（两条）、残端阑尾炎、孤立性纤维性肿瘤/血管外皮瘤、紫绀型先心病—血小板减少。原因是结构性的：**排除性规则写在竞争假设的文档里**。要排除 Eisenmenger，需要的是 Eisenmenger 那篇的准入条件；而病人 vignette 里只有"肺动脉压 60/39"和"卵圆孔未闭 7.34 mm"，任何以 vignette 为查询的检索都到不了那篇。可行的形态是：先生成候选假设集，再对每个候选各做一次检索（gold 一次、每个竞争假设各一次），而不是对病例做一次检索。

**2. 数值阈值必须作为一等对象抽取。** 5 条断言依赖数值比较，其中 3 条的阈值在语料中以数字形式明确存在：QTc >480 ms（用于排除长 QT，可直接与 vignette 的 380 ms 比较）、室壁厚度 ≥15 mm（肥厚型心肌病）、残端 ≤5 mm（残端阑尾炎风险）。另外两条是关系型阈值：肺动脉压 ≥ 体循环压（Eisenmenger）、Kanavel 四征需满足的条数。如果只把段落文本存下来，机械程序无法执行"380 < 480"这个比较；阈值必须被抽取成 `{operator, value, unit}`。

**3. 排序噪声大，每条断言中位有 8 篇文档共现。** 这意味着抽取阶段不能只处理 top-1 切片；需要对候选切片集合逐个抽取断言，再在断言层面去重与投票。

### 切片形态对抽取的约束

| 源 | 切片数 | token 中位 | <80 token 占比 | 章节可得 |
|---|---:|---:|---:|---|
| merck | 9,629 | 154 | 27.9% | `section_path` |
| manifest_cpg | 39,091 | 66 | 54.8% | `section_path` |
| wikem | 1,055 | 36 | 90.0% | `section_path` |
| pmc_oa | 317,710 | 81 | 49.3% | `section_path` |
| statpearls | 367,799 | 60 | 67.6% | 标题后缀（99.9%） |
| textbooks | 125,847 | 124 | 20.3% | **无** |

两点直接影响设计：

- 切片普遍偏小（中位 36–154 token，半数以上源有近半切片不足 80 token）。像 Kanavel 四征这样的多句判据，"四征列表"与"缺少某些征象可与其他病鉴别"经常落在相邻切片。因此**抽取的输入单位应当是重组后的文档段落，而不是检索返回的单个切片**；检索仍以切片为召回单位，但抽取前需按 `document_key + ordinal` 把命中切片与其前后邻居拼回。
- 语境类型可从元数据直接得到，无需 LLM 判断：4 个源有 `section_path`，StatPearls 有 99.9% 的切片在标题后缀里携带章节名，其中**9,312 个切片明确属于 "Differential Diagnosis" 章节**。这正是"共现极性"问题的来源段落，能被机械地标记出来。只有 textbooks 完全没有章节信息（其"文档"是整本书），应从抽取范围中降级或单独处理。

## 二、表示侧：schema 与预处理

设计目标：LLM 只在两处出现——语料侧每个段落抽一次（离线，可缓存复用）、病例侧每份 vignette 抽一次——之后决策规则的构建与执行全部机械化。

### 2.1 语料侧：诊断判据断言

```json
{
  "assertion_id": "sp:12345#c07:a2",
  "subject":   {"label": "Eisenmenger syndrome", "concept_id": "C_EISENMENGER",
                "kind": "disease"},
  "predicate": {"label": "large left-to-right shunt", "concept_id": "F_LARGE_LR_SHUNT",
                "kind": "hemodynamic"},
  "relation":  "required_for",
  "polarity":  "asserted",
  "modality":  "obligatory",
  "threshold": {"operator": ">=", "value": null, "unit": null,
                "relational": "PAP >= systemic_pressure"},
  "comparator": null,
  "qualifiers": {"age_group": null, "site": null, "timing": null, "host_state": null},
  "context_type": "definition",
  "provenance": {"source": "merck", "doc_id": "merck19e_ch293", "chunk_ids": ["...p12"],
                 "quote": "Large left-to-right shunts ... may lead to Eisenmenger's syndrome"}
}
```

字段中只有三类是机械程序绝对无法自行恢复的，也正是 LLM 抽取的全部价值所在：

- **`relation`**：`feature_of` / `required_for` / `sufficient_for` / `pathognomonic_for` / `excludes` / `argues_against` / `distinguishes_from` / `variant_of` / `synonym_of` / `caused_by`。共现只能告诉你两个概念同现，说不出是哪一种。
- **`polarity`**：谓语是被肯定还是被否定（"QTc 正常"与"QTc 延长"在词面上都含 QTc）。这一条直接对应 74 号例中方法把"QTc 380 ms 正常"读成支持长 QT 的失败。
- **`context_type`**：`definition` / `criteria` / `differential` / `histopathology` / `epidemiology` / `treatment` / `table_row`。虽然大部分可由章节元数据预填，但表格行（Nelson 表 149-1 那类）必须由抽取阶段识别并标为 `table_row`，否则同一表格不同行会被读成一条断言。

`modality`（obligatory / typical / frequent / occasional / rare）决定后续是硬约束还是打分权重；`threshold` 决定能否做数值比较；`comparator` 只在 `distinguishes_from` / `argues_against` 时填写另一方假设。

**试运行后补记：这个 schema 没有断言间连词。** 15,588 条抽取结果里，字段全集止于上列十项；`comparator` 是唯一跨假设边（8.8%），且引擎实际只触发 5–34 次。指南原文里的 `if` / `both...and` / `either...or` / `at least N` 只活在 `quote` 里。后续机械执行退化为按条求和，正是因为缺少一个 `criterion_group`（组 id + `all` / `any` / `at_least_n` + n）。详见 `MECHANICAL_RULE_TRIAL_REPORT.md` 第五节。

### 2.2 病例侧：结构化发现

```json
{
  "finding_id": "case74:f11",
  "label": "QTc",
  "concept_id": "F_QTC",
  "kind": "ecg",
  "polarity": "present",
  "value": {"number": 380, "unit": "ms"},
  "qualifiers": {"timing": "initial ECG", "site": null},
  "provenance": {"char_span": [1180, 1204]}
}
```

`polarity` 取 `present` / `absent` / `normal` / `not_assessed` 四值。`normal` 与 `absent` 必须分开：vignette 说"室壁厚度正常"是一条**被测量过且为阴性**的证据（可用于排除肥厚型心肌病），而"未提及室壁厚度"不能用于排除任何东西。这一区分是 11 例中多条排除分支成立的前提。

### 2.3 预处理（全部无需 LLM）

1. **文档重组**：按 `document_key + chunk_ordinal` 把切片拼回文档，抽取时以"命中切片 ± 1"为窗口，解决 `179.a` 那类跨切片断言。textbooks 因缺少文档边界而排除。
2. **章节类型映射**：`section_path`（4 源）与标题后缀（StatPearls）→ `context_type` 预填值；"Differential Diagnosis" 段落预标为 `differential`。
3. **表格检测与按行切分**：识别制表符/多空格对齐的表格块，按行切开后再送抽取，避免 `179.b` 那类跨行伪共现。
4. **概念归一层**：这是此前几轮分析反复出问题的地方（`Cutaneous malakoplakia` 与 `Malakoplakia` 被当成两个概念，导致方法答对了却被记为竞争假设）。需要一张概念表，支持：精确、别名、去括号、驼峰拆分、**限定词剥离**（`Cutaneous malakoplakia` → `Malakoplakia`，`Linagliptin-induced acute pancreatitis` → `acute pancreatitis` + 病因限定），并在概念间保留 `variant_of` / `subtype_of` 边。
5. **单位与数值归一**：ms / mm / U/L / mmHg 统一，范围表达（"440–480 ms"）转成区间。
6. **主题锚点标注**：文档标题 → 概念，用于按假设条件化检索时建立倒排。

### 2.4 机械规则构建（无 LLM）

输入：候选假设集 H、病例发现集 F、按假设检索并抽取得到的断言库 A。

```
for h in H:
    # 第一层：硬约束，顺序固定，可复现
    for a in A[h] where a.relation == "required_for" and a.modality == "obligatory":
        if F[a.predicate].polarity not in {present} or not threshold_satisfied(a, F):
            eliminate(h, reason=a)                    # 773: PAP < systemic → 排除 Eisenmenger
    for a in A[h] where a.relation == "excludes":
        if F[a.predicate].polarity == present:
            eliminate(h, reason=a)
    # 第二层：确诊性证据
    for a in A[h] where a.relation == "pathognomonic_for":
        if F[a.predicate].polarity == present:
            confirm(h, reason=a)                      # 119: 角样板层 → 汗孔角化症
# 第三层：幸存者按 feature_of 的 modality 权重打分
# 第四层：distinguishes_from 边在并列幸存者之间做定向比较
# 输出：被排除者的排除理由链 = 决策流程本身
```

三层之后输出的排除理由链就是可读的决策流程，与手工搭的流程同构。`context_type == "differential"` 的断言在第一、二层中**不参与**，只在第四层作为定向比较使用——这正是把 30.1% 的鉴别语境共现从"特征"降级为"对比"的机械实现。

### 2.5 这套方案覆盖不到的部分

- **回答轴**（326 号例）：流程的第一层分支是"题目问病因还是问病变"，这不是判据问题，需要在题目侧加一个 `answer_axis` 字段（etiologic / anatomic / syndromic），由题干抽取而非由指南判据推出。
- **同义与命名**（272、646、5、409 四例）：概念归一层能把同义标签合并，但金标与选项之间的命名之争（如 `Central Giant Cell Granuloma` 与 `GCRG`）属于基准侧缺陷，schema 只能把它暴露出来，不能解决。
- **语料确无的规则**（91、179）：`91.b` 与 `179.b` 需要补充免疫组化对照表与紫绀型先心病血液学并发症的来源，属于定向补料而非扩大规模。

## 三、可行性判定

| 环节 | 判定 | 依据 |
|---|---|---|
| 必要切片可召回 | 9/11 例可行 | 22/26 条断言可从单切片获得；被卡 2 例与手工裁定一致 |
| 检索形态 | 需改为按假设条件化 | 5/26 条断言的主语不在 vignette 中，排除性规则写在竞争假设文档里 |
| 抽取单位 | 需文档重组后再抽 | 切片中位 36–154 token，多句判据常跨切片 |
| 语境标注 | 可由元数据预填 | 5/6 源有章节信息，StatPearls 有 9,312 个明确的鉴别诊断段落 |
| 表格 | 需按行切分 | 存在跨行伪共现（Nelson 表 149-1） |
| 阈值比较 | 可行 | 3 条阈值在语料中以数字形式存在，需抽成 `{operator,value,unit}` |
| 规则构建 | 可全机械化 | 四层算法只依赖 schema 字段，不需要再调用 LLM |

LLM 的调用被压缩到两处且都可缓存：语料侧每个候选段落抽一次断言（离线、跨病例复用），病例侧每份 vignette 抽一次发现。之后从假设集到决策流程的全过程无需模型参与。

## 产物

| 文件 | 内容 |
|---|---|
| `branch_retrievability.json` | 26 条断言的切片定位、包含性、锚点标题、证据段落 |
| `branch_retrievability_summary.json` | 检索侧汇总 |
| `assertion_adjudication_26.csv` | 逐条人工裁定（stated / buried / partial / split / absent）与理由 |
| `assertion_adjudication_summary.json` | 裁定汇总与按例覆盖情况 |

脚本：`analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL/` 下的 `audit_branch_retrievability.py`、`freeze_assertion_adjudication.py`。
