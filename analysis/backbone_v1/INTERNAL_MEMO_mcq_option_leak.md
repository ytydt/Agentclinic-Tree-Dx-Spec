# 关键内部备忘：流水线臂的 MCQ 选项泄漏

Created: 2026-08-07 · 内部，不进入正文 · **优先级最高**

追查"骨干与 AB02 在两个数据集上的性能落差"时发现：落差不是机制差异，
而是**流水线臂与其基线拿到的输入不同**。流水线臂的上下文里逐字包含金标准诊断。

---

## 1. 机制

### 1.1 注入链路

数据集适配层产出的 `case_text` 自带 MCQ 尾巴（DA 原生带；MCR/OX 由适配层合成）：

```
<临床叙述>

What is the most likely diagnosis?

Options:
A. schwannoma
B. intraligamentary myoma with cystic degeneration
...
```

该字段原样存入 `annotate/normalized_cases.json`，再原样成为 `state.case_summary`。
**逐字核验：`case_summary` 与 `normalized_cases.case_text` 完全相同**——
MCR M00 100/100、OX M00 100/100、DA M00 76/76。

`state.case_summary` 随后进入：

- `_llm_ddx_entities` 的 `context`（召回入口，`controller.py:1909-1914, 1969-1974`）
- `_l2_case_context`（L2/L3 各模块的病例上下文，`controller.py:2002-2013`）
- `_build_recall_hints` 与 `_build_l2_per_parent_asset` 的 `context`

> **更正（2026-08-07）**：本备忘录初稿把注入点归给
> `static_qa_env.StaticQAEnv.get_case_summary()`。那是错的——该类只在探针与测试中构造
> （`scripts/eval_lr_coverage_isolated.py:326` 等三处），**不在论文运行路径上**。
> 判别依据：它的模板会产出 `Question: ` 前缀，而实际 `case_summary` 中没有该前缀。
> 真正的路径是 `case_text` 未经剥离直接落入状态。

### 1.2 代码库知道这个块的存在，且只挡住了一个模块

`controller.py:1394-1408` 为 RootSelector 显式做了屏蔽：

```python
payload["static_options"] = []      # hide answer choices from root selection
# Also redact the raw case_summary question/options block ...
payload["case_summary"] = re.sub(
    r"\n+(?:Question|Options)\s*:.*",
    "\n[Answer options redacted — use clinical findings only]",
    payload["case_summary"], flags=re.DOTALL | re.IGNORECASE)
```

**这段屏蔽只作用于 RootSelector**。召回入口、L2 候选生成、证据裁决等其余模块
拿到的都是未屏蔽的 `case_summary`。同样地，至少 5 处脚本
（`run_diagnosisarena_m01.py:1116`、`run_diagnosisarena_p5_bfs.py:871`、
`run_l1_calib_smoke.py:44` 等）都显式剥离了这个块。
也就是说，"选项不该进模型"在本代码库里是既有共识，只是没有贯彻到主路径。

### 1.3 基线侧（已逐项核验为干净）

基线与骨干走 `scripts/paper/baseline_common.py:load_runtime_cases`，
docstring 为 *"Load cases and strip gold from runtime-facing fields"*，
注释为 *"OX/MCR/RareArena: open vignette only — do not inject MCQ options into arms"*，
调用 `diagnosisarena_adapter.vignette_body()` 剥掉 `\nOptions:` 之后的全部内容。

| 基线实际输入 | n | vignette 含 Options 块 | 金标准逐字在 vignette |
|---|---:|---:|---:|
| DiagnosisArena | 100 | 0 | 1 (1%) |
| MedCaseReasoning | 100 | 0 | 3 (3%) |
| OpenXDDx | 100 | 0 | 0 (0%) |
| RareArena | 100 | 0 | 1 (1%) |

（1–3% 是本底巧合率：金标准词恰好出现在叙述中，例如病理描述里提到该病名。）

`load_runtime_cases` 确实为 DiagnosisArena 填充了 `options` 字段（100/100 非空），
但穷举 `baseline_arms.py` 与 `run_baseline.py` 中 `options` 的全部出现位置后确认：
唯一的消费点是 `baseline_arms.py:259` 的 `_dry_topk`，即 **dry-run / 缓存缺失时的确定性占位符**，
不进入任何实时提示；`baseline_arms.py:88` 的提示词反而明确写着
*"disease names that are plausible differentials (no letters/options)"*。

**结论：四个数据集上基线全部干净。不对等是单向的——只有流水线臂拿到了金标准。**

---

## 2. 波及范围（逐例核查，非抽样）

| 运行 | n | case_summary 含 Options | 金标准逐字在 context | 金标准在选项中的位置 |
|---|---:|---:|---:|---|
| DA AB02 (flat) | 100 | 100 | **100 (100%)** | A:55 B:25 C:15 D:5 |
| MCR v1 AB02 (flat) | 100 | 100 | **100 (100%)** | **A:100** |
| MCR v1 M00（正文主结果） | 100 | 100 | **100 (100%)** | **A:100** |
| MCR v2 AB02 (flat) | 100 | 100 | **100 (100%)** | **A:100** |
| MCR v2 M00 | 100 | 100 | **100 (100%)** | **A:100** |
| OX M00 (compat_synonym_v1) | 100 | 100 | **100 (100%)** | 无固定偏置 |
| **DA M00 (pipeline_remaining76_v1)** | 76 | 76 | **76 (100%)** | A:39 B:20 C:12 D:5 |
| RA M00 (compat_synonym_v1) | 100 | **0** | 1（本底巧合） | 无选项块 |

**完整模型 APHHM / M00 本身在 DA、MCR、OX 三个数据集上均受污染**，
与消融臂同等程度——泄漏发生在状态构建阶段，早于任何臂的分叉。

按数据集扫描全部运行目录：**OX 全部 17 个、MCR 两切片各 4 个、DA 全部 6 个流水线运行均泄漏；
RareArena 全部 9 个运行干净**（RA 数据无 MCQ 选项，`case_summary` 止于问句）。
四个数据集里三个受影响。

按"截断到 1500 字符后金标准是否仍进入模型"排序，严重程度为
**OX（97%）> MCR（74%）> DA（46%）**。

### 2.1 OX 与 MCR 本无选项，选项是适配层造出来的

三个适配层共用 `diagnosisarena_adapter.build_case_text()`（`:66-88`），它把
`Options` 缺失当作**错误直接抛异常**（`raise ValueError("case %s missing Options")`），
即强制每个数据集都套进 DiagnosisArena 的 MCQ 模式，并固定追加：

```
{body}\n\n What is the most likely diagnosis?\n\nOptions:\n{A. …}\n
```

两个数据集的选项来源与污染性质**完全不同**：

| | MedCaseReasoning | OpenXDDx |
|---|---|---|
| 干扰项来源 | 用正则从**同一病例的 `diagnostic_reasoning`** 里挖（`medcasereasoning_adapter.py:70-92`） | 源数据 `interpretation` 字段的疾病键（`open_xddx_adapter.py:87-89`） |
| 金标准位置 | `parse_differentials` 先 `out.append(gold)` 再挖干扰项 → **恒为 A（100/100）** | 按 `interp` 键序 → A:35 B:22 C:13 D:11 E:15 F:2 G:2 |
| 干扰项形态 | 中位 8 词，**57% 含 "was considered / excluded because" 等推理残留** | 中位 2 词，干净病名，推理残留 1/369 |
| 金标准形态 | 中位 2 词，推理残留 0% | 中位 2 词，推理残留 0% |
| 平均真实选项数 | 6.0（另补 197 个 `None` 占位） | 4.7（另补 231 个 `None` 占位） |

MCR 的干扰项实际上是"该病例中被考虑过并已排除的鉴别诊断"，且常常不成句，例如
`"due to decreased ankle-brachial indices, but arteriography was negative"`
根本不是一个诊断名；金标准有时还会在尾部以片段形式二次出现。

### 2.2 MCR 的合成 MCQ 完全不读病历即可满分

| 启发式（完全不看临床文本） | MCR | OX |
|---|---:|---:|
| 固定选 A | **1.00** | 0.35 |
| 选第一个不含推理残留词的选项 | **1.00** | 0.35 |
| 选最短的选项 | 0.63 | 0.26 |
| 均匀随机（参照） | 0.18 | 0.23 |

**MCR 有两条相互独立的路径可以 100% 命中**：位置（恒为 A）与格式（唯一干净的病名）。
即便把选项顺序打乱，格式线索单独仍给出 1.00。作为对照，骨干在干净输入下的
MCR 判官 Acc@1 只有 0.24。

**OX 的性质则不同**：无格式线索（0.35 与其位置分布一致），选项都是同质的干净病名。
泄漏的价值在于把"开放式回忆"降级成"约 4.7 选一"，随机基线 0.23——
仍是重大提示，但需要读病历才能利用。

另需单独记录：OX 的金标准本身是算法代理标签
（`open_xddx_adapter.py:60-70`，`gold_source: "max_grounded_rationale_proxy"`），
由"最多有据支撑的 rationale"从该病例自己的 DDx 列表中选出，非人工标注。这是与泄漏
无关的另一项效度隐患。

---

MCR 上金标准永远是选项 A，是构造使然：
`medcasereasoning_adapter.py:109-113` 用 `parse_differentials(..., gold=gold)`
把金标准放在首位，`letters_for_diseases` 再按序分配字母。
干扰项则是从该病例自己的 `diagnostic_reasoning` 里切出来的片段，
形如 `"Lactic acidosis was considered but was excluded because …"`——
即便不认识金标准，仅凭"哪个选项是一个干净的疾病名"也能选中。

DA 上选项 A 占 55%（均匀应为 25%），存在额外的位置偏置。

原子事实目录（`finding_fixture_v1.json`）**干净**：金标准出现率 MCR 3% / DA 1%，
无 Options 残留。泄漏只经 `case_summary` 一条路径。

---

## 3. 定量：入口探针（`z4_leak_probe.py`，600 次调用）

同一 S2 提示、同一 S1 锚点，只换 `context`：

| 条件 | MCR 覆盖 | MCR 首项 | DA 覆盖 | DA 首项 |
|---|---:|---:|---:|---:|
| a 剥离病历（骨干/基线所见） | 0.570 | 0.190 | 0.700 | 0.370 |
| b 流水线文本、剥掉 Options | 0.510 | 0.200 | 0.740 | 0.380 |
| c 流水线文本原样（M00/AB02 所见） | **0.780** | **0.430** | **0.830** | **0.470** |
| *AB02 缓存实测（每次调用均值）* | *0.775* | *0.400* | *0.826* | *0.481* |

条件 c 与 AB02 实测吻合到 0.005 以内；条件 b 与 a 无差异，说明
`case_summary` 比病历多出的那 410 字符（MCR 中位）**全部价值都在 Options 块**。

此前记录的"AB02 单次 DDx 调用覆盖率高 11–20pp"因此不是入口机制差异。

---

## 4. 定量：端到端等输入对照（`run_backbone_batch8.sh`）

把同一份 `case_summary` 喂给骨干（`--context-source pipeline_summary`），其余不变：

**MCR 切片一（Prompt-7 判官 Acc@1）**

| 臂 | 调用/例 | cov池 | cov候选 | Acc@1 |
|---|---:|---:|---:|---:|
| 骨干 k=1，剥离病历 | 4 | 0.55 | 0.48 | 0.24 |
| **骨干 k=1，泄漏输入** | **4** | 0.78 | 0.69 | **0.47** |
| 骨干 k=3，泄漏输入 | 6 | 0.78 | 0.66 | 0.46 |
| AB02 flat，泄漏输入 | 84 | 0.85 | 0.66 | 0.44 |
| M00，泄漏输入 | ~84 | — | — | 0.50 |

**DA**

| 臂 | 调用/例 | cov池 | cov候选 | lexical | option@1 |
|---|---:|---:|---:|---:|---:|
| 骨干 k=1，剥离病历 | 4 | 0.71 | 0.59 | 0.36 | 0.50 |
| **骨干 k=1，泄漏输入** | **4** | 0.83 | 0.85 | **0.65** | **0.67** |
| 骨干 k=3，泄漏输入 | 6 | 0.89 | 0.88 | 0.65 | — |
| AB02 flat，泄漏输入 | 84 | 0.92 | 0.80 | 0.64 | 0.68 |

**输入拉平之后，4 次调用的骨干在两个数据集上追平甚至略胜 84 次调用的 AB02**
（MCR 0.47 vs 0.44；DA 0.65/0.67 vs 0.64/0.68）。**残差性能落差不存在。**

另注：泄漏输入下 k=3 不再优于 k=1（MCR 0.46 vs 0.47，DA 0.65 vs 0.65）——
答案已在上下文里时，召回广度自然失去价值。这是对该解释的一个独立佐证。

---

## 5. 这解释了本轮全部的负结果

第二轮花了约 2.3 万次调用去移植 AB02 的选择机制，八种实现全部为负
（见 `RESIDUAL_GAP_ANALYSIS_R2.md` §3）。现在有了统一解释：
**根本不存在待移植的选择优势。** AB02 的候选集之所以更好，是因为金标准写在它的
上下文里；它的 84 次调用相对 4 次买不到任何东西。

同样得到解释的还有：
- 为什么 AB02 的 level-2 后验只经历一次序数更新却"有效"（§4）；
- 为什么它 71% 的证据裁决预算作用于被压平的 L1 轴仍不影响结果；
- 为什么 flat 臂与完整模型只差 0.02（DA）/ 0.025（MCR，p=0.405）。

---

## 6. 结论与待办

**结论**

1. DA 与 MCR 上 M00 / AB02 的已刊数字与其基线**不可比**：流水线臂的上下文含金标准，
   基线臂被显式剥离。
2. MCR 上尤其严重：金标准 100% 位于选项 A，干扰项是同一病例推理文本的片段。
   MCR 本是自由文本任务，这些选项完全是适配层合成的。
3. 输入拉平后不存在性能落差，因此"层级 / 证据 / 后验"三类机制在本证据下
   **没有可归因的净贡献**。

正文条目清单见 `PAPER_CLAIMS_AT_RISK_option_leak.md`：一级（与事实矛盾的陈述）5 条、
二级（失效）约 72 条、三级（需重述）约 18 条、四级（可保留但效应量待复核）约 35 条。
论文五份源文件中**未找到任何一处披露流水线推理时接收 MCQ 选项**，且有四处明确声称
"Gold labels are never used during generation"。

**待办（按优先级）**

1. 在状态构建处就剥离：让 `state.case_summary` 取 `vignette_body(case_text)` 而非
   原始 `case_text`，使其与基线的 `load_runtime_cases` 口径一致。
   把 `controller.py:1400-1407` 那段目前只服务 RootSelector 的 redact 上提为全局默认，
   仅在确需选项的评测接口处显式解禁。同时审计
   `_l2_case_context` / `_build_recall_hints` / `_build_l2_per_parent_asset` 的 context 组装。
2. 用干净输入重跑 M00 与 AB02（DA + MCR 两切片）。按 §4 的等输入对照外推，
   预计 M00 的 MCR Acc 从 0.50 降到 0.25 附近、DA lexical 从 0.64 降到 0.40 附近。
3. 在重跑出结果之前，**冻结正文中所有依赖 M00/AB02 与基线对比的论断**。
4. 复核其他数据集（OX / MedBullets / RareArena）是否走同一 env 路径。

**保留有效的结论**

- 入口广度（多次异条件 DDx 取并集）在干净输入下确实有效：
  DA option@1 0.50→0.58、MCR 0.24→0.28，+1 次调用即饱和。
- 严格下标式 S3 不劣于自由文本 S3，且可校验。
- 温度 0 下 n=100 的噪声地板为 ±0.05。

---

## 7. 复现

```bash
PYTHONPATH=src:scripts:scripts/paper python3 analysis/backbone_v1/z4_leak_probe.py
bash scripts/paper/run_backbone_batch8.sh
```

产物：`analysis/backbone_v1/z4_leak_probe.json`、
`logs/backbone_v1/{diagnosisarena,medcasereasoning}/leak_*/`。
