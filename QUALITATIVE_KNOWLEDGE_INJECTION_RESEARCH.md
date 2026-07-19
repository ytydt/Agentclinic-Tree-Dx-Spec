# 定性路知识注入：CPG / case_report 语料的鉴别证据覆盖核验与注入设计

> 触发：既然定量 LR 只在罕见/表型侧可行（见 [`LR_QUANT_FEASIBILITY_VERDICT.md`](LR_QUANT_FEASIBILITY_VERDICT.md) §8–§10），常见 dx 的鉴别主要落在**定性路**。本文核验现有 CPG + case_report 语料能否覆盖关键鉴别证据，且覆盖是否"带判断（支持/反对）"、是否会诱发"未检索到=反对"的谬误；并回答一级抽象分支是否需先展开、以及父子分支 rule-in/rule-out 的语义。
>
> 隔离数据：[`data/eval/lr_coverage_cases.json`](data/eval/lr_coverage_cases.json)（正确+关键干扰分支、关键鉴别 finding）。脚本：[`scripts/eval_qualitative_corpus_coverage.py`](scripts/eval_qualitative_corpus_coverage.py)。日期 2026-07-08。

## 1. 覆盖的三档定义

不止"能检索到"，而是分三档，只有第 3 档对 rule-in/out 真有用：

1. **retrievable（co-mention）**：top-k 里有 chunk 同时提到 finding 与该分支。
2. **enumeration-only**：chunk 是"Differential diagnosis includes: A; B; C"式的**成员清单**——只有归属信号，无推理。
3. **directional**：chunk 带**支持/反对**判断（"characteristic of / argues against / distinguishes …"），才是 rule-in/out 可用的证据。

## 2. 核验结果（39 个 gold-favoring 关键 finding）

| 语料 | 粒度 | 可检索(co-mention) | dir-cue(启发式) | enumeration-only | **directional(LLM 判定)** |
|---|---|---|---|---|---|
| **CPG** | specific(具体病) | 16/39 (41%) | 25% | **0%** | 11/39 (28%) |
| CPG | L1 抽象标签 | 9/28 (32%) | 10% | 0% | 5/28 (17%) |
| **case_report** | specific(具体病) | 27/39 (69%) | 28% | **69%** | 21/39 (53%) |
| case_report | L1 抽象标签 | 4/28 (14%) | 7% | 14% | 2/28 (7%) |

关键交叉表（specific 粒度，co-mention chunk 的性质）：

| 语料 | co-mention | 其中 enumeration 被判 directional（**谬误源**） | 其中 prose 真判别（**真信号**） |
|---|---|---|---|
| CPG | 16 | 0 / 0（CPG 无清单） | **11 / 16** |
| case_report | 27 | **21 / 27** | 0 / 0（case_report 全是清单） |

## 3. 三个结论（对症用户三问）

### 3.1 「未检索到=反对」谬误：**已实证，且 case_report 是重灾区**

- **case_report 的 co-mention 100% 是成员清单**（27/27 enumeration），无一条 prose 推理。LLM 裁判把其中 21/27 读成了 "SUPPORTS/REFUTES"——**这正是谬误在发生**：模型把"清单里出现"当成支持判断。由对称性，"清单里没有"就会被读成反对。
- ⇒ **case_report 不能作为 rule-in/out 的方向性证据源**；它只提供**候选归属/召回信号**（这与它当前作为分支 RECALL 入口的定位一致，见 controller `_build_recall_hints`）。若把 case_report 原文喂进标注器做判别，必然放大谬误。
- **缓解**（注入侧，不改语料）：
  1. enumeration chunk 显式打标 **"membership/candidate signal only — NOT a support/refute judgment; 缺席不构成反对证据"**；
  2. 标注器 prompt 明确 **open-world 假设**：只有 chunk 里**显式**"argues against/excludes"才允许 REFUTE；单纯"未见提及"一律映射为 `neutral / not assessed`，禁止转成 `weak_against`；
  3. REFUTE 结论**只允许来自 prose（CPG）**chunk，不允许来自清单。

### 3.2 一级抽象分支检索：**确需先展开到二级再检索**

- 抽象 L1 标签（"Neoplastic Process"、"Vascular/Ischemic Abdominal Condition"、"Metabolic/Bone Disorder"）检索显著变差：
  - case_report 可检索 69% → **14%**，directional 53% → **7%**；
  - CPG 可检索 41% → 32%，directional 28% → **17%**。
- 抽象家族名不是语料的可索引词面。⇒ **rule-in/out 前应把 L1 展开为其 L2 子病，逐子病检索再向上聚合**；不要用 L1 标签直接检索 chunk。

### 3.3 CPG vs case_report 的分工

- **CPG（prose，含指南/PMC）= 真方向性证据源**：enumeration 0%，co-mention 中 11/16 是真判别。短板是 co-mention 召回只 41% → 需**按具体 L2 病 + finding 组合查询**、并扩 red_flag/differential/evaluation chunk_type。
- **case_report = 召回/归属信号**：广覆盖（69%）但全是清单 → 只用于候选召回与"哪些病该进比较集"，不用于判别方向。

## 4. 父子分支 rule-in / rule-out 语义（回答用户第 4 问）

把诊断树的概率单调性讲清楚（`P(parent) = Σ P(child_i)`，MECE 下）：

### 4.1 rule-in 向上传播 = **OR / max over children**（用户猜想成立）

- 因 `P(parent) ≥ P(any child)`：任一子病被强 rule-in，父分支即被 rule-in。
- ⇒ **某个子分支的 rule-in 症状足以 rule-in 整个父分支**——用户的直觉是对的，且可证。
- 实现：父分支 rule-in 分数 = 子分支 rule-in 的 **max**（不是平均，平均会被无关子病稀释——正是此前"证据塌缩"的一种来源）。

### 4.2 rule-out 向上传播 = **AND over children（只保留共性）**（用户的 CML-blast 例子成立）

- 要 rule-out 父分支，须证据同时反对**所有**子病；只要有一个子病仍相容，父分支不能被 rule-out。
- **CML-blast 例**：`未分化细胞多` 对 "CML 慢性期" 是反对、但对子分支 "CML 急变期(blast phase)" 恰是**支持**。因该 finding 支持父类下的一个子病，故**不得据此 rule-out CML 家族**。
- ⇒ rule-out 计算时，**先排除任何 rule-in 了某个子病的 finding，只保留"反对全部子病"的共性证据**。等价于：`parent_ruleout = min over children 的 rule-out`（对每个子病都反对，才成立）。

### 4.3 两条规则合起来（与 §8.4 分层 LR 语义一致）

| 操作 | 向上聚合算子 | 直觉 |
|---|---|---|
| rule-in | **max**（OR） | 命中任一子病即命中家族 |
| rule-out | **min**（AND，取共性） | 须排除所有子病才排除家族 |

- 二者**非对称**：rule-in 从任一子病上浮，rule-out 只从"全体子病的交集"上浮。
- 这直接修两个已知病灶：① rule-in 用 max 避免家族被无关子病稀释（证据塌缩）；② rule-out 用交集避免"子病特异征被误当父类反对证据"（CML-blast 类误杀）。

## 5. 落地建议（定性注入管线，优先级）

1. **P0 谷仓分工**：case_report 仅作召回/比较集来源；判别方向只信 CPG prose + §9 的 LR 锚点。标注器 prompt 加 open-world 护栏（缺席≠反对；REFUTE 须显式）。
2. **P0 先展开后检索**：rule-in/out 前把 L1 展开为 L2 具体病，逐病 `"{disease} {finding}"` 查询 CPG，再按 §4 向上聚合。
3. **P1 CPG 召回增强**：co-mention 仅 41% → 提高 finding×disease 组合查询、优先 differential/red_flag/evaluation chunk_type、必要时补 statpearls/textbooks。
4. **P1 聚合算子**：rule-in=max(children)、rule-out=min(children)（保留共性），并与判别门控/后验更新对接。

局限：39 关键 finding、单 backbone 裁判、TF-IDF 检索（未用 dense/MedCPT）。趋势清晰，绝对数待扩样本 + MedCPT 复核。

---

## 6. chunk_type / sibling / 入口扩展 与「数量 vs 排序」诊断（回答用户追问）

深扫描全量 `cpg_index`(205k) + `case_report_index`(77k)，对每个关键 finding 记录"首个方向性 co-mention 块"在多深处出现。脚本 [`scripts/probe_cpg_chunk_diagnosis.py`](scripts/probe_cpg_chunk_diagnosis.py)（K=6, depth=400）。

### 6.1 关键数据

| 语料 | 方向性块**存在**(任意深度) | top-6 命中 | **RANK 问题**(存在但排>6) | **COUNT 问题**(全无) | co-mention 存在 |
|---|---|---|---|---|---|
| **CPG** | 32/39 (82%) | 20/39 (51%) | **12/39 (30%)** | 7/39 (17%) | 34/39 |
| case_report | 0/39 (0%) | 0/39 | 0 | **39/39 (100%)** | 35/39 |

- CPG 方向性块 chunk_type 构成：**differential 17 / evaluation 15**。
- CPG 最有效入口（首先浮出方向性块的查询）：**`disease+finding` 20** / finding_only 6 / disease_only 4 / L1+finding 2。
- sibling/article-closure 能补救的 RANK 问题：**仅 2/12**。

### 6.2 三问答复

**Q1 现在是否只用 differential？该扩吗？** — 不该只用 differential。CPG 里真正的方向性证据 **differential 与 evaluation 几乎各半（17 vs 15）**，只取 differential 会丢 ~47% 的可判别块。⇒ **检索/注入必须纳入 `evaluation`（及 `red_flag`）chunk_type**（`DifferentiatedCPGRetriever._DDX_USEFUL` 已含，但分支召回的 `"differential diagnosis of {S}"` 查询是 differential 偏置，需在证据路改成含 evaluation 的多面查询）。

**Q2 sibling / 入口扩展能否获益？**
- **入口扩展 = 大收益**：`disease+finding` 组合入口独揽 20/32 的方向性首命中，远超单病(4)或单 finding(6)。⇒ 证据路应**用 `"{具体病} {finding}"` 组合查询**，而非抽象 syndrome/单病。
- **sibling(article-closure) = 小收益**：只补救 2/12 排序问题——与你"分支创建时 sibling 并非大收益"的观察一致。证据路可保留但非重点。

**Q3 主要问题是数量不足还是排序靠后？**
- **CPG = 以排序问题为主**：方向性块 82% 其实存在语料里，但只有 51% 落进 top-6；**30% 是"存在但被挤到 6 名后"（排序）**，仅 17% 是真缺（数量）。⇒ 提升手段是**更好的排序/召回**（组合入口 + chunk_type 感知加权 + 适度增大 k + MedCPT dense 重排），而非先急着扩语料。
- **case_report = kind-count 问题**：方向性块在任意深度都 0——因为它整库是"differential includes: …"清单，**结构上不含方向性 prose**（co-mention 却有 35/39，故它只能供召回/成员信号，见 §3.1）。这不是排序能救的，也不该靠它做判别。

### 6.3 据此收敛的落地优先级（更新 §5）

1. **P0 组合入口 + 扩 chunk_type**：证据检索用 `"{L2 具体病} {finding}"` 查询，纳入 differential+evaluation+red_flag。预计把 CPG 方向性 top-6 命中从 51% 拉向 ~80%（把 30% 排序损失大部分收回）。
2. **P0 谷仓分工不变**：case_report 只作召回/比较集（0% 方向性），判别只信 CPG prose + LR 锚点 + open-world 护栏。
3. **P1 dense 重排**：TF-IDF 之上加 MedCPT（`cpg_medcpt_index` 已存在）重排 top-N，进一步压缩排序损失。
4. **P2 sibling-closure**：小补丁，保留但不优先。

---

## 7. 实验层落地 + 消融 + K 门限研究（2026-07-08）

> 触发：用户要求「在实验层落地以上措施，并研究**知识支持下 LLM 判别准确率**能否超过 LLM 单独（§10 基线：MedBullets 64%、RareArena 90%），测多种措施组合（含回归风险），并研究 K=6 是否合理」。
>
> 隔离设计：把 §10 的 LLM 单选判别任务（给一个 finding + 候选诊断列表，问它最特异支持哪个）作为共同底座，唯一变量是**是否注入知识块、以哪种措施组合注入**。知识块来自 CPG 语料（谷仓分工），逐候选病用组合入口检索方向性 prose。脚本：[`scripts/eval_qual_injection_ablation.py`](scripts/eval_qual_injection_ablation.py)（消融）、[`scripts/eval_k_threshold_sweep.py`](scripts/eval_k_threshold_sweep.py)（K 门限）、[`scripts/eval_aggregation_operators.py`](scripts/eval_aggregation_operators.py)（聚合算子）、[`scripts/eval_medcpt_dir_coverage.py`](scripts/eval_medcpt_dir_coverage.py)（P1 dense）。按 LR 判决分桶（`logs/lr_coverage_all.json`）看**知识在哪个区间帮上忙**。

### 7.1 消融结果（llama-3.3-70b，k=6，39 个 gold-favoring finding）

| arm | 措施组合 | MedBullets | RareArena | gold 方向块命中 |
|---|---|---|---|---|
| `llm_alone` | 无知识（基线） | 14/28 (50%) | 10/11 (90%) | — |
| `kb_p0` | 组合入口+宽 chunk_type+谷仓+护栏 | 15/28 (53%) | 8/11 (72%) | 6 |
| `kb_noguard` | 同上但**关护栏** | 15/28 (53%) | 8/11 (72%) | 6 |
| `kb_diffonly` | 同上但**只 differential** | 14/28 (50%) | 8/11 (72%) | 5 |
| `kb_disease_only` | 同上但**单病入口** | 13/28 (46%) | 6/11 (54%) | 3 |
| `kb_naive_cr` | 组合入口+宽+**关护栏+塞 case_report 清单** | 17/28 (60%) | 10/11 (90%) | 6 |
| **`kb_gated`** | **kb_p0 + 无方向块则回退 LLM 单独** | **16/28 (57%)** | 9/11 (81%) | 7 |
| **`kb_gated_cr`** | **kb_gated + case_report 清单作召回提示** | **16/28 (57%)** | **10/11 (90%)** | 7 |

按 LR 桶（Δ vs `llm_alone`；两次运行基线有 ±1 抽样噪声）：

| arm | LR→gold（强量化） | LR~tie（护栏区） | LR_none（纯定性区） |
|---|---|---|---|
| `llm_alone` | 15–16/16 | 1/3 | 7/20 |
| `kb_p0` | 12/16 (**−19**) | 2/3 (**+33**) | 9/20 (**+10**) |
| `kb_gated_cr` | 15/16 (−6，噪声内) | 2/3 (**+33**) | 9/20 (**+10**) |
| `kb_naive_cr` | 15/16 (0) | 2/3 (+33) | 10/20 (**+15**) |

### 7.2 关键发现

1. **知识最该注入的是 LR_none 定性区，且确有净增益（+10~15pp）**。这正是 §10 交叉表里 LLM 单独最弱的区（55%）。逐条 flip：`kb_gated` 在 LR_none 救回 `hypophosphatemia→甲旁亢`、`鼻腔血性分泌物→异物`，在 LR~tie 救回 `bronchiectasis→Kartagener`。

2. **无差别注入会伤 LR→gold 强区（回归！）**。`kb_p0`/`kb_diffonly`/`kb_disease_only` 在 LR→gold 桶掉 19–25pp——因为对本来 LLM 靠自身知识就能答对的强区，塞入一条"检索到的、可能片面/离题"的方向块，反而把模型带偏（典型：`homocystinuria` 的 `intellectual disability`/`thromboembolism` 被 CPG 里泛化措辞干扰）。**这证实了回归风险是真的**，也说明"检索到就注入"是错的。

3. **门控（gated）基本消除回归**：`kb_gated`/`kb_gated_cr` 只在"确有方向块被检索到"时注入，否则回退 LLM 单独 → LR→gold 桶回到 15/16（噪声内），同时保住 LR_none/LR~tie 的增益。**这是推荐落地形态**：MedBullets 50%→57%、RareArena 保 90%，且无实质回归。

4. **单病入口是最差组合（−25pp、RareArena 90%→54%）**——再次印证 §6.2「组合入口 `{病} {finding}` 是大收益」。去掉组合入口，知识块召回质量崩掉，注入的噪声害处最大。

5. **护栏（open-world）在本隔离任务里差异不显著**（`kb_p0` vs `kb_noguard` 完全同分）。原因：单选判别任务本身不问"缺席=反对"，护栏的价值在**多轮后验更新**（缺席被读成 weak_against 那条路径），本任务测不出——护栏应在下游后验环回归里验证，此处不能据"无差异"就撤掉。

6. **case_report 清单作召回提示（非判别）是安全增量**：`kb_gated_cr` 相对 `kb_gated` 把 RareArena 拉回 90%，MedBullets 持平——与 §3.1「case_report 只供召回/比较集」一致；它没有制造 LR→gold 回归，因为清单是显式标注的"membership hint"而非判别。（注意 `kb_naive_cr` 的 60% 有"关护栏"叠加，不能单独归功于 case_report。）

### 7.3 K 门限研究（K=6 是否合理）

`scripts/eval_k_threshold_sweep.py`（检索-only，P0 stack，CPG 方向性块首命中秩）：

| K | 1 | 2 | 3 | 4 | **6** | 8 | 10 | 15 | 20 | 30 | 50 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| all 覆盖% | 17 | 23 | 38 | 43 | **48** | 56 | 58 | 64 | 64 | 69 | 71 |

- 首命中秩：**中位 3、p75=7、max=41**；天花板（≤50）只有 71%（另 29% 是 §6.3 的 count 缺，加 k 也救不回）。
- 边际增益：K3→K6 +2 块，K6→K10 +4 块（较陡），K10→K15 +2，此后趋平。**K=6 落在中位数(3)与 p75(7)之间，是"多数已浮出、噪声尚可控"的合理折中；但把 K 提到 8–10 能再收 ~10pp 方向覆盖，代价是每候选多 2–4 个块的注入噪声**。
- 结论：**K=6 合理但偏保守**。因为 §7.2 已证"无差别多注入会伤强区"，**推荐 K 与门控联动**：门控开着时可安全把 K 提到 8–10（多召回方向块、无方向块仍回退），既吃到 +10pp 覆盖又不引回归。单纯裸增 K 不推荐。

### 7.4 聚合算子（rule-in=max / rule-out=min-commonality）

`scripts/eval_aggregation_operators.py` 确定性验证 §4 代数，3/3 PASS：
- **CML-blast 陷阱**：`excess blast cells` 对 blast phase 是强 rule-in（0.95），对 chronic phase 是 rule-out（0.9）；家族 rule-in=max=0.95、rule-out=min(把被支持的子病置零)=0 → **正确地 rule-IN 家族、绝不 rule-out**。
- **全子病反对**：三子病都被反对 → 家族 rule-out=min=0.7（最弱共性强度）。
- **稀释护栏**：一个强命中(0.9)+两个无关(0) → max 保 0.9，mean 会塌到 0.30（正是"证据塌缩"病灶）。

### 7.5 P1 MedCPT dense 重排 —— 前置已修复 + 复测（2026-07-09）

**前置缺陷（已修）**：`cpg_medcpt_index` 建于 6/26（`ntotal=203830`），而当前 `cpg_index` 已重切到 `205115`（且顺序在第 971 行起就发散，非前缀关系）。FAISS 行号无法映射回当前 metadata，dense/RRF 结果无效。

**修复**：用当前 `cpg_index/metadata.jsonl` 重建行对齐索引（`scripts/build_medcpt_cpg_index.py --batch 128`，GPU 上重编码 205,115 块，用时 25.9 min），新 `config.json` 的 `ntotal=205115`，行对齐恢复。

**复测 1 — 方向性 top-6 覆盖**（`scripts/eval_medcpt_dir_coverage.py`，检索-only）：

| 语料 | n | sparse | dense | **RRF 融合** |
|---|---|---|---|---|
| all | 39 | 48% | 61% | **69%** |
| medbullets | 28 | 46% | 57% | **67%** |
| rarearena | 11 | 54% | 72% | **72%** |

⇒ dense 单塔就把方向覆盖从 48%→61%，**RRF 融合达 69%**（≈ §6.3 预期的 ~80% 上界的大部分），把 §6.3 诊断出的 30% 排序损失收回大半——**证实 P1 是真收益，且是"排序问题"的正确解药**。

**复测 2 — 注入消融（CPG 检索换成 hybrid RRF）**（`scripts/eval_qual_injection_ablation.py --retriever hybrid`）：

| arm | MedBullets | RareArena | gold 方向块命中 | LR→gold | LR~tie | LR_none | 回归 |
|---|---|---|---|---|---|---|---|
| `llm_alone` | 16/28 (57%) | 10/11 (90%) | — | 16/16 | 1/3 | 9/20 | — |
| `kb_gated`(hybrid) | **18/28 (64%)** | 10/11 (90%) | **15** | 16/16 (0) | 2/3 (+33) | 10/20 (+5) | **无** |
| **`kb_gated_cr`(hybrid)** | **19/28 (67%)** | 10/11 (90%) | **15** | 16/16 (0) | 1/3 | **12/20 (+15)** | **无** |

对比 §7.1 的 sparse 版（`kb_gated_cr` MedBullets 57%、gold 方向块 7）：**hybrid 把 gold 方向块命中从 7 翻到 15**（dense 召回了 sparse 排到 k 后的方向块），直接转化为 **MedBullets 57%→67%、LR_none +15pp、且零回归**。这是本轮最强的净增益来源。

### 7.5b 更新的落地建议

- **P1 hybrid（TF-IDF ∪ MedCPT dense RRF）应纳入证据检索**：它不是可选优化，而是把定性注入从"聊胜于无(+7pp)"提到"实质有效(+10pp、零回归)"的关键。已用重建后的行对齐索引验证。
- 生产接入路径已存在：`HybridCPGRetriever`（`src/agentclinic_tree_dx/knowledge/hybrid_cpg_retriever.py`）本就是 `GuidelineBranchSource` 的 drop-in，只需指向重建后的 `cpg_medcpt_index`。

### 7.6 落地结论（本轮生效）

1. **推荐形态 = `kb_gated_cr` + hybrid 检索（门控注入 + case_report 召回提示 + TF-IDF∪MedCPT dense RRF）**：只在检索到方向性 prose 时注入 CPG 判别证据，否则回退 LLM 单独。实验层（hybrid）**MedBullets 57%→67%、RareArena 保 90%、LR_none 定性区 +15pp、零回归**。
2. **知识确实在"LLM 单独最弱的定性区"抬升判别准确率**，验证了协作策略；但**必须门控**，否则强区回归。
3. **K=6 合理但偏保守**；建议"门控开 → K 提到 8–10"联动，吃覆盖不吃回归。
4. **聚合算子 rule-in=max / rule-out=min(共性)** 代数已验证，可对接后验更新/判别门控。
5. **P1 MedCPT dense 已复测确认为关键净增益**（前置索引已重建、行对齐恢复；见 §7.5）：sparse 方向覆盖 48% → RRF 69%，gold 方向块命中 7→15，MedBullets 注入准确率 57%→67%。**open-world 护栏**的净收益仍待下游多轮后验环回归验证（本单选任务测不出），列为下一步回归项。

> 局限：39 关键 finding、单 backbone（llama）、temp=0 仍有 ±1 抽样噪声（基线 LR→gold 15~16/16 波动即此）。趋势（门控消回归、知识补定性区、hybrid 大幅抬升、K=6 偏保守）稳健；绝对数待扩样本 + 下游后验环复核。
