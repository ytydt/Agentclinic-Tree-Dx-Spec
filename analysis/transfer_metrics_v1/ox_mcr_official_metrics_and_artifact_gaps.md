# Open-XDDx / MedCaseReasoning：官方指标调研与本项目产物差距

状态：调研笔记（非正式 claim）  
日期：2026-07-25  
关联：`PAPER_EXPERIMENT_EXECUTION_PLAN.md` §13.4 / D3；`analysis/l1_recall_failure_v1/transfer_compat_synonym_harness.md`

---

## 0. 一句话结论

- **Open-XDDx** 正式评测 = **多标签 DDx 集合命中** + **每病解释对齐**（LLM-judge + BERTScore/SBERT/METEOR）+ 可选人工三维分；**不是** MCQ Hit@1。
- **MedCaseReasoning** 正式评测 = **单诊断 N-shot LLM-judge 准确率** + **Reasoning Recall**（金标推理点覆盖）；**不是**伪选项 @1。
- 本仓库当前 staged / `compat_parallel` 产物足以支撑 DiagnosisArena 式 Top-k，但相对上述正式指标存在 **金标未贯通、系统输出形态不匹配、短列表过短、缺一等公民推理文本** 四类缺口。
- **不必**把整棵树路径原样当论文主输出；需要的是一层 **可评测投影**：`pred_ddx[]` + `pred_interpretation[dx→证据文本]`（OX），以及 `pred_diagnosis` + `pred_reasoning_trace`（MCR）。P5/`selected_fact_ids`/树结构是投影的原料，不是最终提交格式。

---

## 1. 官方指标与实现路径（联网 + 论文）

### 1.1 Open-XDDx（Dual-Inf，npj Health Systems 2025）

| 指标 | 定义 | 判分方式 | 官方/可复现路径 |
|------|------|----------|-----------------|
| Diagnostic Accuracy (Eq.1) | `#correct diagnoses / #total diagnoses`（集合累计） | 预测 vs 专家 DDx；同义/亚型可算对；自动侧用 LLM 比对 prompt | 论文 Methods + Supp. Appendix 3；代码仓 [betterzhou/Dual-Inf](https://github.com/betterzhou/Dual-Inf)（主脚本 `Code_Dual-Inf.py`，**无独立 evaluate.py**） |
| Interpretation Accuracy (Eq.2) | `#correct interpretations / #total interpretations` | **GPT-4o** 判断预测解释与金标解释一致性 | 同上 Appendix 3 |
| BERTScore / Sentence-BERT / METEOR | 金标 vs 生成解释语义对齐 | 标准 NLG 库 | `bert-score` / sentence-transformers / METEOR |
| 人工 | correctness / completeness / usefulness（1–5）；错误类型 missing / factual / low-relevance | 医师 | 论文 Fig.2b |

**数据形态（本仓库 raw 实测，n=570）**

| 统计 | 值 |
|------|-----|
| DDx 数 / 注 | min **2**，mean **4.59**，max **7**（论文 Table1：mean 4.6±1.0） |
| 解释条数 / 诊断 | mean ≈ **3.15**（论文 3.1±1.5） |
| 病名形式 | 自由文本医学短语，常含缩写括号，如 `acute kidney injury (AKI)`；**非**强制 ICD/SNOMED 规范名 |
| 解释形式 | `dict[disease_name → list[str]]`，条目多为题干可接地事实片段（症状/化验/体征），非整段 CoT |

**长度/形式限制（官方）**

- **无硬性固定长度**（非“必须恰好 5 条”）；经验分布约 2–7，均值 ~4.6。
- Dual-Inf 方法侧有迭代上限 λ=5、低置信过滤阈值 β=3，那是**模型超参**，不是数据集字段约束。
- **无**要求提交 ICD 码；人类评测明确允许同义/亚型。
- 本 adapter 仅因 MCQ 字母表限制：`>26` 抛错；全库 max=7，**永不触发**。

**学术目标**：可解释鉴别诊断——同时抬高 DDx 集合质量与证据解释质量（含稀有病），填补“只评诊断、不评解释”的空白。

### 1.2 MedCaseReasoning（arXiv:2505.11733）

| 指标 | 定义 | 判分方式 | 实现路径 |
|------|------|----------|----------|
| Diagnostic Accuracy 1/5/10-shot | 每例采样 10 次（T=0.8, top-p=0.95）；N-shot≈best-of-N 是否命中正确诊断 | **gpt-4o-mini** LLM-as-judge（McDuff et al. prompt） | 文档入口 `evaluate.py`；仓 [Stanford-MedCaseReasoning](https://github.com/kevinwu23/Stanford-MedCaseReasoning) 目前 **under construction**，脚本可能未齐 |
| Reasoning Recall | \(c_i=\|R_i\cap T_i\|/\|R_i\|\)，病例平均；**只评 recall** | **o4-mini** 对每个金标推理点判是否出现在模型 trace；医师校验约 94% | 论文 Definition 1 + Appendix Prompt 5 |
| 外推 | 同协议 NEJM CPC（302） | 同上 | 不开源 |

**金标字段**：`final_diagnosis`（单标签）+ `diagnostic_reasoning`（枚举推理点）。

**学术目标**：突破 MedQA/MMLU 的“只看最终答案”；度量与**临床医生撰写**推理的对齐，并作 SFT 资源。

---

## 2. 本项目已有产物（可复用原料）

| 阶段 | 典型路径 | 与正式指标相关的字段 |
|------|----------|----------------------|
| 归一化用例 | `…/normalized_cases.json`、子集 parquet | OX：`annotation.ddx_set`；**解释全文在 parquet `interpretation_json`，load 时未注入每条例文**。MCR：`final_diagnosis`；**`diagnostic_reasoning` 未进 pipeline case** |
| 树 / 标注 | `shared_trees/{id}.json` | `branches`、`static_evidence_items`、`frontier` — 结构证据，非叙事 |
| L1 选证 | `case_results` → `l1.selected_fact_ids`、`l1_posteriors` | 事实选择序列；预算固定 **6** |
| P5 | `p5_audit/{id}.json` | `rules[].effects[]`：`candidate` / `effect` / `why` / `evidence_ids` — **最接近“每病解释”的结构化原料** |
| L2 / compat | `l2.final_ranking_ids/labels` | 排序叶标签；`compat_parallel` 合并后常 **极短**（实测 OX 多为 1–2，校准默认 k=5） |
| Mapper | `mapper/projections/{id}.json` | `option_maps.*.matched_leaf_ids`、`rationale`（**实体映射关系**，非临床鉴别解释） |
| Fixture | `finding_fixture_v1.json` | `full_findings[{id,text}]` — 解释落地所需的题干事实白名单 |

当前 transfer harness（`compat_synonym_v1`）仍以 **proxy MCQ / rematch @1** 为主出口；与 §1 正式表不可横比。

---

## 3. 产物差距矩阵

### 3.1 Open-XDDx 正式指标所需 vs 现状

| 正式需要 | 现状 | 差距等级 | 建议产物 |
|----------|------|----------|----------|
| 金标 DDx 集合 | adapter 有 `ddx_set` / `interpretation` 键 | 低 | 评测加载时强制读 `interpretation_json`，弃用 proxy 单金标作主表 |
| 金标每病解释列表 | parquet 有；`load_subset_cases` **不暴露** rationale 列表 | **中** | `annotation.interpretation: dict[str,list[str]]` 贯通 |
| 系统预测 DDx **集合**（变长，约 2–7） | `final_ranking_labels` 常 **≪ 金标长度**（compat 合并后尤甚） | **高** | 新增 `pred_ddx_set`：从校准池 / L2 召回 / 未合并池取 **Top-K（建议 K∈{5,7} 或阈值门控）叶标签去重**；禁止只用 merge 后 1 条当 DDx |
| 系统每病 **interpretation 文本** | P5 有 per-candidate `why`，但未按最终 DDx 聚合、未对齐全标格式 | **高** | `pred_interpretation[label] = [why…]` 或“选中事实文本 + 支持/反对方向”的模板渲染 |
| Diagnostic Acc (Eq.1) 匹配器 | 仅有 `agent_label_match` / mapper 选项绑定 | **高** | LLM-judge 或同义绑定：pred 集合 × gold 集合（允许多对多） |
| Interpretation Acc + NLG | 无 | **高** | GPT-4o 一致性 judge + BERTScore 等；配对键=匹配后的 (gold_dx, pred_dx) |
| 人工三维 | PAPER §15.2 有计划，未接流水线 | 中 | 导出盲评包：pred 解释 vs gold |

### 3.2 MedCaseReasoning 正式指标所需 vs 现状

| 正式需要 | 现状 | 差距等级 | 建议产物 |
|----------|------|----------|----------|
| 单金标诊断 | 有 `final_diagnosis` | 低 | 保持 |
| 金标推理点列表 | parquet 有 `diagnostic_reasoning`；normalized **丢掉** | **高** | `annotation.reasoning_points: list[str]` |
| 系统最终诊断（开放式字符串） | 有 Top-1 leaf label / 选项字母 | 低–中 | 开放式 `pred_diagnosis`；judge 不用伪选项 |
| 系统 **reasoning trace 文本** | 无统一叙事；仅有 fact_ids、P5 why、树 parent | **高** | 见 §4 投影方案 |
| N-shot Acc（10 采样） | 流水线通常单次确定性路径 | **高**（协议差） | 若严格对齐官方：对诊断头做 10 次采样；树流水线可声明“单轨迹协议变体”并单独报表 |
| Reasoning Recall | 无 | **高** | o4-mini 点覆盖 judge；输入=`reasoning_points` × `pred_trace` |
| 伪 MCQ distractor | regex 噪声大 | n/a | **正式指标不用**；仅 harness plumbing |

### 3.3 PAPER 计划中已写、尚未实现的桥

- §13.4「与 Open-XDDx 专家支持/反对解释的**概念覆盖**」——无脚本。
- §15.2 D3 解释人工盲排——无导出器。
- 计划强调 **候选相对证据 / shared-evidence misuse**；P5 `discriminating` + `effect` 可支撑，但需先有稳定的 `pred_interpretation` 投影。

---

## 4. 是否需要把树 / P5 / compat「转写」为人类可读推理路径？

### 4.1 结论（分数据集）

| 数据集 | 是否必须整树叙事化？ | 实际需要 |
|--------|----------------------|----------|
| **Open-XDDx** | **否** | 需要 **按诊断组织的证据列表**（接近金标 `interpretation`），不是一篇从根到叶的故事。P5 `why` + 选中 finding 文本是主原料；树路径可选作辅助上下文。 |
| **MedCaseReasoning** | **是（轻量）** | 需要一篇 **连贯 reasoning trace**（或等价分点），供 Reasoning Recall 的 LLM-judge 扫描。官方金标是分点列表；模型侧通常是一段/多段文本。 |

### 4.2 推荐投影（最小可评测包）

对每个 `case_id` 增加（建议路径）`…/eval_projection/{id}.json`：

```json
{
  "case_id": "65",
  "dataset": "open_xddx",
  "pred_ddx": [{"label": "pneumonia", "rank": 1, "leaf_id": "B3.1"}],
  "pred_interpretation": {
    "pneumonia": [
      "Support: fever + infiltrate (F4,F9); P5: …"
    ]
  },
  "pred_diagnosis": "pneumonia",
  "pred_reasoning_trace": "…人类可读段落…",
  "sources": {
    "ranking": "l2.final_ranking_labels|calib_pool",
    "evidence": ["p5_audit", "selected_fact_ids", "finding_fixture"]
  }
}
```

**建议转写规则（确定性模板优先，必要时再 LLM stitch）**

1. **选证**：按 `selected_fact_ids` 顺序展开 fixture 文本 → “Observed: …”。
2. **L1**：Top 后验分支标签 → “Leading axes: …”。
3. **P5**：对每个进入 `pred_ddx` 的候选，聚合 `effect∈{support,oppose}` 且非弱噪音的 `why`（或 finding+方向）。
4. **排序**：列出 `pred_ddx` 名次与（可选）compat 合并说明一句。
5. **勿**把 mapper `rationale`（“选项↔叶同义绑定”）当成临床解释。
6. **MCR stitch**：若要对齐官方 SFT 风格，可用 LLM 把 1–4 缝成流畅段落，但须冻结模型与 prompt；评估 Recall 时以 stitch 后文本为准。
7. **默认不含 KB chunk 原文**（见 §4.3）：推理正文以题干事实 + P5 方向性 why 为主；KB 仅作可选的一句蒸馏知识声明或留在 `sources` 审计，不整段粘贴检索片段。

**compat_parallel**：只影响“提交哪几个叶 / 是否合并代表叶”，应写入 `sources` 审计；**不要**指望 merge 后的 1 条名单充当 OX 的完整 DDx 集合。

### 4.3 KB chunks 是否写入可读推理文本？

**当前设计：不包含。** §4.2 原料为 `selected_fact_ids` / fixture 文本、L1 轴、P5 `why`、`pred_ddx` 排序。流水线内部 L2 召回虽有 `snippet_budget`（KB/检索），但**未投影**进 `pred_reasoning_trace` / `pred_interpretation`。

| 写入方式 | 对可靠性 | 对可读性 | 对正式指标 |
|----------|----------|----------|------------|
| **整段粘贴 KB chunks** | 易引入离题/过时片段；读者分不清“本病所见”vs“教科书” | 明显变差（长、碎、不像临床叙述） | **OX**：金标解释是题干可接地短事实，chunk 风格错配会伤 Interpretation Acc / BERTScore。**MCR**：金标是病例报告里的鉴别/排除理由，通用 KB 很少直接覆盖那些点 → Reasoning Recall 增益有限甚至稀释 |
| **不写 KB，只写事实+P5**（默认） | 与系统真实决策链一致、可审计 | 短、清晰 | 与双数据集金标形态最对齐 |
| **一句蒸馏知识**（推荐可选增强） | 若绑定“本候选曾检索且用于 P5”可升可靠性；须标成 *background* 非 *observed* | 可读（限 1 句/候选） | 可能略助人工 usefulness；对 Recall/解释自动分勿指望大涨 |

**结论**：把知识写进文本**有条件地**有助于质量——应写**已用于决策的短结论**（例如 “PE 典型可有低氧与胸痛，但本例无腿肿，故降权”），**不要**把 raw KB chunks 塞进评测用推理正文。Chunk 原文可放 `sources.kb_snippets` 供审计，不进 judge 主文本。
## 5. Open-XDDx：诊断列表长度 / 形式 vs mapper 短列表适配

### 5.1 金标侧

- 长度：**2–7**，均值 ~4.6；**无**固定上限（adapter 26 字母足够）。
- 形式：自由文本病名 + 缩写；解释为短事实短语列表。
- **正式评测应对齐整份 `interpretation` 键集合**，不是 proxy 单字母。

### 5.2 系统侧现状（不适配点）

| 组件 | 典型长度 | 相对 OX 金标 |
|------|----------|--------------|
| L2 `candidate_budget` | 24（召回） | 够用作候选池 |
| TopK 校准 `calibration_k` | 默认 **5** | 与均值 4.6 **接近**，是合理的 `pred_ddx` 来源 |
| `compat_parallel` 后 `final_ranking` | OX `compat_synonym_v1` 已跑 case（n=82）：长度直方图 `(0:1, 1:49, 2:19, 3:5, 4:3, 5:5)`，**均值 ≈1.70** | **过短**，直接当 DDx 集合会系统性压低 Eq.1 的 recall 型累计命中 |
| Mapper 选项短列表 | = 金标 DDx 数（2–7） | **输入侧适配良好**（选项即专家 DDx）；缺的是“系统自己生成的开放 DDx”，不是选项映射 |
| Mapper `matched_leaf_ids` | 每选项 0–n 叶 | 服务 MCQ rematch；**不能替代**开放式 DDx 列表评测 |

### 5.3 适配建议

1. **OX 正式表**：用 **校准前/校准池 Top-5（或 Top-7）去重叶标签** 作为 `pred_ddx`；`final_ranking` 仅作排序/主诊断。
2. **名称规范性**：不做强制规范化到 ICD；评测用 **LLM 语义等价 + 可选同义词表**（与 Dual-Inf 人工规则一致）。Mapper 的 synonym bind 可复用于集合匹配，但匹配对象应从“选项字母”扩展到“pred↔gold 集合”。
3. **解释长度**：金标每病约 3 条短证据；系统侧每病导出 **2–5 条** P5/选证要点即可对接 Interpretation Acc，无需长篇 CoT。
4. **Mapper 短列表**：继续可用于 plumbing 与诊断绑定审计；**不能**用 `option_top1` 代替 Eq.1。若要坚持 mapper 路径，可定义辅助指标：`option_set_hit = 系统排序叶是否覆盖各选项的 matched leaves`，与官方 Eq.1 分表报告。

### 5.4 该用哪份诊断列表？（实证，ox_seq100 × 粗匹配）

在已有 `shared_trees` + `case_results` 上，用宽松字符串/Jaccard 匹配对金标 `interpretation` 键估 **集合 Recall / Precision / F1**（非正式 judge，只作选源）：

| 候选源 | 均值 \|pred\| | R | P | F1 |
|--------|--------------:|--:|--:|---:|
| **L1 frontier 家族名** | 3.7 | 0.08 | 0.09 | 0.09 |
| compat 后 `final_ranking` | 1.6 | 0.25 | **0.80** | 0.37 |
| 每父 **1** 个 L2 champion | 3.6 | 0.35 | 0.45 | 0.38 |
| 每父 **2** 个 L2 champion | 7.2 | 0.51 | 0.38 | 0.42 |
| **全局叶后验 Top-5** | 5.0 | 0.46 | 0.46 | **0.45** |
| 全局叶后验 Top-7 | 7.0 | 0.55 | 0.42 | **0.46** |
| **全部 L2 叶（去重）** | **16.9** | **0.67** | **0.24** | 0.34 |
| 金标 DDx 均值 | 4.7 | — | — | — |


### 5.5 主表 P/R 与 mapper / 全 L2「偏离」审核（2026-07-26）

复算结论见 [`ox_eval_metric_divergence_audit.md`](ox_eval_metric_divergence_audit.md)：

- micro-P（后验 Top-5 LLM **0.50**）≪ mapper `option_top1`（**0.80**）：**任务+列表不同**；同用 compat 短列表时开放 micro-P=**0.81**。
- micro-R（Top-5 LLM **0.53**）≪ 全 L2 R（lexical **0.70**）：**K=5 截断丢 TP≈108**；全叶是覆盖上界，正式表不用。
- **非实现 bug**；禁止把三类数字静默横比。

**推荐（最终诊断列表，非推理过程）**：长度对齐 OX 的 **排序 L2 叶短列表**（优先 `global_posterior_top5/7` 或 joint 排序截断到 K≈5–7；可选每父 champion 作消歧变体）。  
**不要用**：L1 家族名（粒度不合规）；**不要用**：全体 L2 叶（特异度崩、解释指标连带受害）。  
Dual-Inf 本身也靠 examination **过滤**低置信诊断；Eq.1 若以预测侧为分母则偏 precision——灌叶会直接打脸。正式报告应 **分列 R/P/F1**，避免单一“accuracy”被召回灌水。

---

## 6. 实现优先级（建议）

| 优先级 | 工作项 | 解锁指标 | 状态（2026-07-25） |
|--------|--------|----------|-------------------|
| P0 | 金标贯通：`interpretation` / `diagnostic_reasoning` 进 case 与评测加载 | 一切正式表 | **done** — `open_xddx_adapter` / `medcasereasoning_adapter` `load_subset_cases` + `transfer_eval/io_gold.py` |
| P0 | `eval_projection`：`pred_ddx`（全局叶后验 Top-K）+ `pred_interpretation`（P5 聚合） | OX Eq.1/2 原料 | **done** — `scripts/paper/build_eval_projection.py` |
| P0 | 集合匹配 lexical / LLM-judge → Diagnostic R/P/F1 | OX 主表 | **done** — `transfer_eval/matching.py` + `ox_metrics.py`；默认 lexical |
| P1 | Interpretation Acc judge + BERTScore 管线 | OX 解释主表 | **done** — 配对边上解释 Acc；`--nlg-metrics` 可选 BERTScore（缺依赖则跳过） |
| P1 | `pred_reasoning_trace` 模板 + Reasoning Recall | MCR 主表 | **done** — 投影模板 + `mcr_metrics.py` |
| P1 | MCR 开放式诊断 judge（弃伪 MCQ 主表） | MCR Acc | **done** — 字段名 `diagnostic_accuracy_single_trajectory` |
| P1 | 基线 OX/MCR：`ordered_diagnoses` list_k∈{5,7} → `eval_projection` → 同指标 | 基线正式表（公平长度） | **done** — `build_baseline_eval_projection.py` + `run_baseline_ox_mcr_eval.py`；协议 `baseline_ordered_topk_v1` |
| P1 | MCR 开放 Acc@1 离线重排消融（D/C/A） | 抬开放 Acc | **done（未过 G1）** — 见 §6.2 |
| P1b | MCR `mcr_val_seq100` 基线全量推理 + LLM 正式评测（14 臂） | 基线 MCR 主表 | **done**（2026-07-25）— [`mcr_val_seq100_baselines_summary.md`](../../runs/paper_v1/medcasereasoning_mcr_val_seq100_v1/mcr_val_seq100_baselines_summary.md)；`JUDGE=llm` `workers=50` |
| P1b | OX `ox_seq100` 基线全量推理 + LLM 正式评测（14 臂，`list_k=5`） | 基线 OX 主表 | **done**（2026-07-26）— [`ox_seq100_baselines_summary.md`](../../runs/paper_v1/open_xddx_ox_seq100_v1/ox_seq100_baselines_summary.md)；`JUDGE=llm` `workers=50` |
| P2 | 严格 10-shot 采样协议（或书面声明单轨迹变体） | 与官方数字可对齐度 | **deferred**（summary 已声明 single_trajectory） |
| P2 | D3 人工盲评导出（PAPER §15.2） | 审稿可信度 | **deferred** |
| P2 | E 类生成覆盖（树无金标叶） | 吃掉 ~30% miss | **deferred_generation**（15/15 轴也不在） |
| P3 | 概念覆盖 / 删证敏感性（PAPER §13.4） | 机制 claim | **deferred** |

### 6.1 CLI（lexical 验收）

```bash
python3 scripts/paper/run_ox_mcr_official_eval.py \
  --dataset open_xddx \
  --run-dir logs/open_xddx_ox_seq100_v1/compat_synonym_v1 \
  --subset-parquet data/benchmarks/open_xddx/subsets/ox_seq100_v1/cases.parquet \
  --judge lexical --ddx-k 5 --build-projection

python3 scripts/paper/run_ox_mcr_official_eval.py \
  --dataset medcasereasoning \
  --run-dir logs/medcasereasoning_mcr_val_seq100_v1/compat_synonym_v1 \
  --subset-parquet data/benchmarks/medcasereasoning/subsets/mcr_val_seq100_v1/cases.parquet \
  --judge lexical --build-projection
```

输出：`annotate/eval_projection/{id}.json`、`annotate/official_eval/summary.json`（+ `summary.md`）、`case_scores/`。  
`--judge llm` 须 `conda activate gnn-llm` + `clashon` + **`--workers 50`**，summary 写 `judge_model=gemini-2.5-flash`。详见 [`README.md`](README.md) 与 [`judge_prompts/JUDGE_MODEL_CONTRACT.md`](judge_prompts/JUDGE_MODEL_CONTRACT.md)。

### 6.2 MCR 开放 Acc@1：推荐投影源与消融结论（2026-07-25）

主指标：`diagnostic_accuracy_single_trajectory`（Prompt7 / Gemini 2.5 Flash）。**禁止**把 mapper `option_top1≈0.81` 写进开放 Acc 主表。

| 投影源 | LLM Acc@1 | lex any-hit@K | 门控 | 备注 |
|--------|-----------|---------------|------|------|
| **B0 `compat_parallel_final_ranking`（默认开放）** | **0.50** | 0.60 | 锚 | 当前推荐默认 |
| B1 / R1 全局叶后验 Top-1 | 0.24 | 0.59–0.63 | — | 池覆盖可，Top-1 弱 |
| **R2 `compat_then_pad_posterior`** | **0.50** | **0.69** | G4✓，G1✗ | 保 Top-1；抬覆盖（吃部分 D/A） |
| R3 / R4 dry 或 live calib on post | 0.26–0.30 | 0.59 | **G3 REJECT** | 伤 Acc；勿晋升 |
| mapper `option_top1` | 0.81 | — | 监控 only | 闭集，禁止混表 |

消融产物：[`mcr_open_acc_ablation_report.md`](mcr_open_acc_ablation_report.md) / [`mcr_open_acc_ablation_summary.json`](mcr_open_acc_ablation_summary.json)；CLI：`scripts/paper/run_mcr_open_acc_ablation.py`。

**结论**

1. **默认开放投影源保持 B0（compat `final_ranking`）**；G1（≥0.55）无一臂过门。
2. 若需要更长鉴别列表 / any-hit：可选 **R2 pad**（Acc@1 不降、any-hit +0.09）；**不要**换 R3/R4 作默认。
3. 剩余 miss：D 需能改 Top-1 的池内重排（当前 calib 在后验池上伤 Acc）；C 需列表内重排；**E（15/15 轴也不在）→ deferred 生成**，见 [`mcr_e_class_coverage_audit.json`](mcr_e_class_coverage_audit.json)。
4. 诚实披露：单轨迹 ≠ 论文 10-shot；E≈30% 开放 miss 非离线重排可解。

```bash
PYTHONPATH=src:scripts/paper python scripts/paper/run_mcr_open_acc_ablation.py \
  --judge llm --workers 50 --resume-scores
```

---

## 7. 与当前 transfer harness 的边界声明

- `ox_seq100` / `mcr_val_seq100` 上的 **compat + synonym_bind @1**：仅证明流水线可跑通与相对 DA 的迁移手感。
- **不得**写入论文主结果表为“Open-XDDx / MedCaseReasoning 官方指标”。
- §6 P0–P1 代码已落地；**lexical** 协议名为 `compatible_metrics_lexical_v1`（**不得**标 official）；与 mapper `option_top1` **禁止混表**。LLM-judge 为 `paper_aligned_judge_v1`（裁判模型替换为 Gemini 2.5 Flash）。

---

## 9. 与官方评测协议的语义一致性核验（2026-07-25）

> 对照对象：Open-XDDx/Dual-Inf 论文 Methods + Supp. Appendix（仓内**无**独立 `evaluate.py`）；MedCaseReasoning 论文 §2.2–2.3（README 宣称 `evaluate.py`，当前仓 **under construction / 文件缺失**）。  
> 故“官方工具”= **论文冻结的指标定义与判分流程**，而非可直接 import 的库。

### 9.1 总判

| 层面 | Open-XDDx | MedCaseReasoning |
|------|-----------|------------------|
| **指标语义（测什么）** | 与计划 **一致**：多标签 DDx 集合质量 + 每病解释对齐 | 与计划 **一致**：单诊断正确性 + 金标推理点覆盖（只 recall） |
| 判分机制（怎么判） | 论文默认 **LLM-judge**（诊断比对 + GPT-4o 解释一致性）+ NLG；计划默认 **lexical**；`--judge llm` 用 **Gemini 2.5 Flash**（`gnn-llm`+`clashon`，替换 gpt-4o-mini/o4-mini） | 论文默认 gpt-4o-mini / o4-mini；计划默认 lexical，llm→**Gemini 2.5 Flash** |
| **采样/轨迹协议** | 官方多次 run 平均；计划单次树轨迹 — **可接受的系统差异**（评的是我们的系统，不是复现 Dual-Inf） | 官方 **10 次采样 N-shot**；计划 **`single_trajectory_v1`** — **实质协议差**，不得与论文表横比 |
| **预测物形态** | 官方：模型自由生成 DDx+解释；计划：树叶 Top-K + P5 模板 — **任务同构、生成器不同**（合理） | 官方：端到端 LLM CoT；计划：投影模板 trace — **指标定义同构、文本分布不同**（合理，但 Recall 可能系统性偏低） |

**结论**：计划在“计量对象”上与官方 **语义对齐**；差异主要在 **判分器强度、采样协议、预测物生成方式**，不全是“换了个 LLM 名字”。这些差异在工程上合理，但必须在 `summary.protocol` 里写死，且 **lexical 结果不得标成 paper-comparable official**。

### 9.2 Open-XDDx：逐项差异

| 官方 | 本计划 | 是否仅模型不同？ | 合理性 |
|------|--------|------------------|--------|
| Diagnostic Acc = `#correct / #total diagnoses`（Eq.1）；自动侧 LLM prompt（Appendix 3）；人工允同义/亚型 | 分列 **P / R / F1**（及 pred/gold 分母两版 micro） | **否**：分母歧义被显式拆开；默认 lexical 非 LLM | **更可取**：Eq.1 原文分母不清；分列避免灌叶虚高 |
| 诊断匹配：LLM 语义等价 | 默认 `leaf_match_score≥0.7`；可选 LLM | **否** | lexical 适合 CI/离线；**声称对齐 Dual-Inf 数字时必须开 llm** |
| Interpretation Acc（Eq.2）：GPT-4o 判 GT↔pred 解释一致 | 在 **匹配成功的 (gold,pred) 边** 上评解释；lexical 或 llm | **部分**：配对边假设合理；默认非 GPT-4o | 先匹配再比解释与“先有对应诊断再评解释”一致；须在文档写清 |
| BERTScore / SBERT / METEOR | `--nlg-metrics` 可选 | 基本是依赖/默认开关差 | 合理；正文 NLG 应对齐“拼接后的解释字符串” |
| 预测 = 自由生成 DDx 列表 | 预测 = **全局叶后验 Top-5** | **否**（系统形态） | 合理：评本系统开放 DDx，不是复现 Dual-Inf |
| 解释 = 模型生成证据句 | 解释 = P5 why 模板（无 KB chunk） | **否**（风格） | 合理且与金标“短事实”更近；BERTScore 可能仍因模板句式偏低 |
| 人工 1–5 三维 | P2 未做 | 否 | 可延期 |

### 9.3 MedCaseReasoning：逐项差异

| 官方 | 本计划 | 是否仅模型不同？ | 合理性 |
|------|--------|------------------|--------|
| Diagnostic Acc：每例 **10 次**采样（T=0.8, top-p=0.95），报 1/5/10-shot；**gpt-4o-mini** + McDuff prompt | **单轨迹** Top-1 叶；lexical 或 llm | **否**（协议 + 默认判分） | 树流水线确定性单轨迹；必须标 `single_trajectory_v1`，**禁止**与论文 10-shot 表合并 |
| Reasoning Recall：金标点是否出现在 **该次** 模型 trace；**o4-mini** JSON；只 recall | 同一定义 \(c_i=\|R\cap T\|/\|R\|\)；trace=模板投影；lexical/llm 覆盖判定 | **定义一致**；判分器与 trace 来源不同 | 指标语义对齐；模板 trace 可能压低绝对 Recall，但不改变“覆盖金标点”的含义 |
| 评测用 best-of-10 中抽一条正确（或全错任抽）的 trace | 固定单轨迹 | **否** | 与单轨迹 Acc 一致；写进 protocol |
| 金标 `diagnostic_reasoning` 分点 | parquet 已有；计划解析为 `reasoning_points` | 一致 | 解析规则需冻结并测 |
| 官方 `evaluate.py` | 自研 `run_ox_mcr_official_eval.py` | 工具缺失下的替代 | **合理**；prompt 应尽量贴近论文 Appendix / McDuff |

### 9.4 对实现计划的约束（落实前必守）

1. **默认 `lexical` 的 summary 标题**用 `compatible_metrics_lexical_v1`，不用 `official_dualinf` / `official_mcr`。  
2. **`--judge llm`** 才允许副标题 `paper_aligned_judge_v1`（仍注明非 10-shot、非 Dual-Inf 复现）。  
3. OX **必须**同时输出 precision / recall / F1，禁止只报一个模糊 “accuracy”。  
4. MCR Acc 字段名用 `diagnostic_accuracy_single_trajectory`，不用 `10shot_accuracy`。  
5. 与 mapper `option_top1`（proxy MCQ）分文件、分表；协议声明写入每个 `summary.json`。

### 9.6 裁判提示词编列（2026-07-25）

完整原文与缺口见目录：[`judge_prompts/README.md`](judge_prompts/README.md)。

| 指标 | 取得？ |
|------|--------|
| MCR Prompt 7 诊断 y/n | 是 |
| MCR Prompt 5 Reasoning Recall | 是 |
| McDuff 诊断 y/n（祖本） | 是 |
| Dual-Inf Appendix 3 / Supp Data 2（诊断+解释一致性） | **是**（SI `MOESM2`，2026-07-25）→ [`ox_appendix3_diagnosis_match.md`](judge_prompts/ox_appendix3_diagnosis_match.md)、[`ox_appendix3_interpretation_consistency.md`](judge_prompts/ox_appendix3_interpretation_consistency.md) |
| Dual-Inf 开源 examination prompts | 是（**非** Appendix 3） |

### 9.7 本仓裁判模型契约（替换 gpt-4o-mini / o4-mini）

- **统一裁判**：**Gemini 2.5 Flash**
- **环境**：`conda activate gnn-llm`；调用前 **`clashon`** VPN
- **并发**：正式 LLM 评测 **`--workers 50`**
- **证据与边界**：[`judge_prompts/JUDGE_MODEL_CONTRACT.md`](judge_prompts/JUDGE_MODEL_CONTRACT.md)
- 论文原文模型名仅作溯源；本仓 `--judge llm` **不得**默认 OpenAI mini 系
- summary 必填：`judge_model` / `judge_env=gnn-llm` / `vpn=clashon` / `workers`

### 9.8 合理性一句话

计划测量的是**同一科学问题**（集合鉴别是否对、解释/推理是否盖住专家要点），用的是**适配本系统产物的兼容协议**；在官方可执行工具缺失的前提下，这是正确路径。不可合理化的只有一件事：把 lexical 单轨迹数字**静默当成** Dual-Inf / MCR 论文主表。
