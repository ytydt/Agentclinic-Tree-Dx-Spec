# 证据标注 / LR 环节缺陷调研（算法 + 数据源）

> **前置调研**（数据源级联、LLM+KB 协同、CPG 评估、外部 KG 借鉴）：[`LR_EVIDENCE_DATASOURCE_RESEARCH.md`](LR_EVIDENCE_DATASOURCE_RESEARCH.md)  
> 调研范围：证据标注器（EvidenceAnnotator）及其依赖的 LR 计算/证据选择全链路。
> 方法：代码走查 + 两组实测探针 + 数据源量化 + 9 题实证 + 外部方案与最新研究对照。
> 探针脚本：`scripts/probe_lr_annotation_defects.py`（缓存臂 + `--rag` 臂）。
> 探针语料：medxpert hard 诊断题经典 finding→disease 对、8/14 MedBullets 残余漏检金标、故意构造的失败模式输入。
>
> **⚠️ 2026-07-08 修订**：本报告把 HPO/Orphadata 频率归为「pseudo-LR/伪标定」。经 [`LR_QUANT_FEASIBILITY_VERDICT.md`](LR_QUANT_FEASIBILITY_VERDICT.md) §8 复核，此定性需收窄——缺陷在**用法**（频率当 Sn + 默认 Sp），而非数据；按 LIRICAL 范式（`P(h|D)/背景频率`）重算即为合法表型 LR，本地 `phenotype.hpoa` 有 264k 条可算。另新增**分层 LR 语义**（comparator 绑定、同胞级 LR）直接对症本报告未解的 MAP_FAIL 叶子鉴别瓶颈。

---

## 0. 调研方法与探针设计

标注环节太依赖 LLM 在线调用，逐案跑全流程既慢又受 CPU-runaway 干扰，因此设计了一个**绕开 LLM、直击 LR 机器**的探针：对每个 `(finding, disease)` 对直接调生产路径
`controller._knowledge_retriever.get_lr_reference(finding,[disease],fast=...)`，
报告命中层级、LR±、置信度、以及数值是否"grounded（explicit）"还是"fabricated（默认 Sp / pct 启发式）"。21 个探针对覆盖三类：经典高 LR 教学对、9 题金标的鉴别发现、故意的噪声输入（人口学 / 正常体检 / 非特异常见症状）。

两臂结果（完整见脚本输出）：

| 臂 | grounded | miss(覆盖漏) | fabricated-Sp | 说明 |
|---|---|---|---|---|
| 缓存路径（默认，`fast=True`） | 16/21 | **5** | 0 | 覆盖漏是主要问题 |
| RAG 路径（`--rag`，StatPearls+Textbooks） | 19/21 | 0 | **2** | 覆盖补齐，但制造伪造 Sp |

这两行本身就点出了核心张力：**默认路径覆盖不足，打开 RAG 能补覆盖但引入伪造数值** —— 这正是用户问题的答案框架。

---

## 1. 标注环节数据流（回顾，便于定位缺陷）

```
证据文本
 └─ _raw_atomic_facts (controller.py:2428)           取本轮结构化证据/结果摘要
 └─ _gather_atomic_findings (2527)                   数值→方向感知HPO(FindingNormalizer)；定性→嵌入表型；过滤人口学/否定
     ↓ atomic findings
 └─ _build_annotator_payload (2183)                  对每个finding查 format_lr_reference_for_prompt → 注入 lr_reference(≤4000字)
     ↓  get_lr_reference (dx_feature_retriever.py:491)  Layer0 marker → Layer2 unified cache(lookup_fuzzy) → [Layer3 RAG/PubMed] → 2-hop
 └─ EvidenceAnnotator (LLM, prompts/evidence_annotator.txt)  输出 branch_effects 七档定性
 └─ _reconcile_annotation_with_kb (2676)             再查KB → _kb_entry_to_signal → 高置信KB覆盖LLM方向 / 产出 branch_lr / floor
 └─ apply_probability_update (3018)                  bayesian_lr_update 或 ordinal_update(+discrimination_gate)
```

分工：**LLM 判定"支持/反对哪个分支、强度几档"；外部知识做（a）prompt 锚点，（b）事后方向/数值纠偏。**

---

## 2. 算法缺陷（逐部件）

### 2.1 `_gather_atomic_findings`（原子发现提取，controller.py:2527）

| # | 缺陷 | 证据 | 影响 |
|---|---|---|---|
| A1 | **嵌入表型映射 top-1 且阈值固定 0.5**（2616-2625），只取第一个匹配、丢弃次优 | 代码 `_add(mlist[0]...)` | 一个定性发现只映射到单一 HPO，若首选错则整条证据错向；无多候选回退 |
| A2 | **降噪只在这一层**：人口学/否定过滤（`_is_demographic_fact`/`_extract_negated_phenotype`）仅在此，`get_lr_reference` 本身无守卫 | RAG 探针里 `57-year-old man→MI` 直接拿到 LR+=0.2（人口学漏进 RAG-quant） | 任何绕开该 gather 的调用（rep-disease、RAG）都会让人口学/正常值产出伪 LR |
| A3 | **上限 15、注入上限 8**（2629、2227）无显著性排序 | `findings[:15]`，注入 `atomic[:8]` | 长病例里"显著证据"可能被前 8 个普通发现挤出注入窗口（外部方案 §6 的 salience 未落地） |

### 2.2 `lookup_fuzzy`（unified cache 模糊匹配，lr_retriever.py:366）

| # | 缺陷 | 证据 | 影响 |
|---|---|---|---|
| A4 | **finding 同义桥覆盖不足** | 探针 `lens dislocation→homocystinuria` 命中 HPO 的 LR+=**0**（退化），而缓存里其实有 `Ectopia lentis→homocystinuria` LR+=10 / `Lens subluxation` LR+=1.2，未被"lens dislocation"桥接 | 强鉴别发现因表述差异漏检，甚至落到退化条目 → 方向反 |
| A5 | **同一发现的多个疾病名变体 LR 不一致，取谁靠字符串分** | `fasting hypoglycemia→GSD type1` 走 HPO 得 1.33；而缓存 `Hypoglycemia→G6Pase deficiency` 是 10.0 | 疾病名归一化缺口导致强弱倒挂，取到弱条目 |
| A6 | **HPO 上位衰减 attenuation 是线性 `max(0.3,1-0.2·depth)`**（499-500），无证据支撑的经验式 | 代码 | 上位继承的 LR 幅度是拍脑袋，可能高估 |

### 2.3 `_kb_entry_to_signal` / reconcile（方向纠偏，controller.py:2631/2676）

| # | 缺陷 | 证据 | 影响 |
|---|---|---|---|
| A7 | **pathognomonic 判定只认 `confidence=="pathognomonic"` 字面标签**（2660），不认等价的高 LR | 探针 `Kayser-Fleischer→Wilson` 走 HPO 被标 `confidence=high`（LR+=10.6），**拿不到 posterior floor**（floor 只给 rank3 pathognomonic） | 事实上的确诊征象（KF 环）被降级为普通 moderate_for，无法钉住正确分支 |
| A8 | **RAG/qualitative 一律禁止方向覆盖**（2657-2658，`rag_lr_can_override_direction=False`） | 配置默认 | 为压噪声牺牲了 RAG 的方向信息：即使 RAG 抽到强 rule-out，也只进 prompt 不能纠偏 → 依赖 LLM 自觉 |
| A9 | **强弱信号"每分支取最强单条"**（2740-2742 best_signal），多条相关证据不叠加 | 代码 | 防双计但也丢失了多条弱证据的合理累积（与 A10 归一化稀释叠加） |

### 2.4 `updater` / `apply_probability_update`（概率更新，updater.py）

| # | 缺陷 | 证据 | 影响 |
|---|---|---|---|
| A10 | **softmax 式全局重归一化的稀释性 down-weight**（`ordinal_update` 乘权后 normalize） | 前序 §13b 受控模拟 + 9 题轨迹 | 宽泛正确家族被标 neutral 时，别人一个 weak_for 就把它单调稀释到垫底（已加 `enable_discrimination_gate`，默认 OFF） |
| A11 | **定性档→伪 LR 折算 `_EFFECT_PSEUDO_LR`**（2410）把 LLM 的语言档位当数值 | 代码 | LLM 档位本身可能错，折算成数值后进贝叶斯更新，错误被"数值化"放大 |
| A12 | **末轮塌缩无防护**：case18 正确家族 0.534→0.02 且全家族塌到≈0，AnswerMapper 拿全 0 默认输出 A | §13 轨迹 | 缺少末轮"全家族坍缩"检测与冻结 |

### 2.5 LLM 侧（EvidenceAnnotator prompt）

| # | 缺陷 | 证据 | 影响 |
|---|---|---|---|
| A13 | **prompt 未描述 `lr_reference`/`pivotal_hint` 字段语义**，仅靠 JSON 里出现 | `evidence_annotator.txt` 通篇无这两个键 | LLM 未被明确指示"必须以注入的 LR 为准"，方向仍可自由发挥 |
| A14 | **档位锚点是 LLM 自评**（"LR+≥5 → strong_for"），无强制用注入值 | prompt:33-39 | LLM 幻觉 LR / 锚定常见诊断（最新研究 Dual-Inf/MedKGI 均列为首要失败源） |

---

## 3. 数据源缺陷（量化实证）

`unified_symptom_disease_cache.json` 共 **267,305** 条，来源分布与 LR 质量：

| 来源 | 条数 | 占比 | LR 状况 | 有真实 Sn/Sp 的条数 |
|---|---|---|---|---|
| `guideline_common` | 139,523 | 52% | **LR± 全为 None**（纯定性存在列表） | 0 |
| `orphanet_rare` | 114,581 | 43% | LR 仅 **6 个离散桶**，由 Orphadata 频率标签映射 | **0** |
| `doclogica` | 13,193 | 5% | LR± 全为 None | 0 |
| wikidata / 其他 | 8 | ~0 | — | — |

**关键发现 D1（头号数据缺陷）：`orphanet_rare` 的 LR 是"频率→LR"的伪似然比。** 全部 114k 条**没有任何真实 Sn/Sp**，LR 只有 6 种取值：

```
Obligate(100%)   → LR+=99  / LR-=0.01   (0.5%)
Very frequent    → LR+=10  / LR-=0.15   (22%)
Frequent(79-30%) → LR+=3   / LR-=0.4    (33%)
Occasional       → LR+=1.2 / LR-=0.85   (36%)
Very rare        → LR+=0.5 / LR-=0.97   (5%)
Excluded         → LR+=0.01/ LR-=99     (0.5%)
```

这**把"该病里这个发现有多常见"（敏感度）当成了似然比**，完全忽略特异度（该发现在鉴别诊断里其他病中有多常见）。后果实测：
- `hypoglycemia → GSD`（G6Pase 缺乏）拿到 **LR+=10**（低血糖对 GSD 并不特异），
- `lens subluxation → homocystinuria` 只有 **LR+=1.2**（晶状体脱位其实高度特异），
- 这是**方向性系统偏差**：常见但不特异的发现被高估，罕见但特异的发现被低估。

**关键发现 D2：95% 的缓存没有可用数值 LR。** `guideline_common`+`doclogica`（57%）LR 全 None，只能当"存在与否"用；加上 `orphanet_rare` 的伪 LR，真正 grounded 的数值 LR 几乎只来自手工 marker 层（`pathognomonic_markers.json` ~24 条 + Orphadata `diagnostic_markers`）。探针里所有正确的强 LR（basophilia 18、Auer rods 120、Horner 25、NME 90）**全部来自这层手工表**。

**关键发现 D3：覆盖漏集中在"常见综合征的鉴别发现"。** 缓存偏罕见病（Orphanet）与手工标志物，但探针里 `elevated ESR→subacute thyroiditis`、`leukocytosis→leukemoid reaction`、`LAP→leukemoid` 在缓存路径**全部 MISS**。这些恰是常见病房场景的关键鉴别发现——缓存没覆盖。

**关键发现 D4：RAG 抽取（lr_quant）制造伪造 Sp。** 打开 RAG 后覆盖漏全补上，但：
- `elevated ESR→subacute thyroiditis` 抽出 LR+=6.4 / **LR-=0.047（伪造 Sp=0.85）**——"ESR 不高就强烈排除亚急性甲状腺炎"是被制造出来的强 rule-out；
- `57-year-old man→MI` 抽出 LR+=0.2（人口学漏进，见 A2）。
这印证前一轮结论：RAG 抽取路径遇到的是 `quantify_snippet` 的 pct 误读 + 默认 Sp 伪造，**换语料不解决，反而是 case report 更危险**（个案频率无群体统计意义）。

---

## 4. 9 题实证映射（把缺陷落到实际问题）

结合 §13 下游轨迹与本次探针，9 道 text-only 难题的标注环节失分可归到上述缺陷：

| 题 | 金标 | 触发的缺陷 | 机制 |
|---|---|---|---|
| Pancoast | apical lung tumor | A10 稀释 | Horner→Pancoast 有强 marker(LR25)，但家族后验被逐轮稀释 0.643→0.102 |
| 类白反应(9) | leukemoid reaction | **D3 覆盖漏 + A7** | `LAP↑→leukemoid` 缓存 MISS；LAP 本应是区分 CML/类白的关键，无 grounded LR → LLM 自由发挥被 CML 家族压过 |
| 胰高血糖素瘤(13) | alpha cell tumor | A10 + A11 | NME→glucagonoma 有 marker(LR90)但若未原子化到"NME"，走定性档折算被稀释 |
| CML(17) | CML | A9 + A10 prior-starved | 多条弱证据不叠加 + 稀释，家族峰值仅 0.157 |
| 肝血管扩张(18) | vascular ectasia | **A12 末轮塌缩** | 0.534→0.02 全家族坍缩，AnswerMapper 全 0 默认 A |
| 肠粘连(23) | adhesions | D3 + AnswerMapper | `SBO→adhesions` 仅定性(Guideline_common 无 LR)；家族对但叶层选错(粘连 vs 扭转) |
| 鼻腔异物(24) | foreign body | D2/D3 | 异物无 grounded LR，prior-starved |
| 舒张期杂音(14) | 体征串 | judge 伪缺失 | 金标是体征描述非病名，非标注缺陷 |

**共性**：真正卡住的是 **(a) 常见鉴别发现无 grounded LR（D2/D3）→ LLM 无锚点自由发挥**，与 **(b) 归一化稀释/末轮塌缩（A10/A12）→ 正确家族被逐轮压低**。数据源与算法各占一半。

---

## 5. 需要的算法调整

按投入产出排序：

1. **【高，低风险】pathognomonic 语义化判定（修 A7）**：`_kb_entry_to_signal` 不只认 `confidence=="pathognomonic"`，改为"**LR+ ≥ floor 阈值即给 posterior floor**"（KF 环 LR10.6、Horner LR25 这类应能钉住分支）。
2. **【高，低风险】特异度感知的频率→LR 修正（配合 D1）**：对 `orphanet_rare` 伪 LR 增加**跨病流行度惩罚**——一个发现命中的疾病数越多（越不特异），其 LR+ 越向 1 收缩。可离线预计算 `finding → #diseases` 作为特异度代理，运行时缩放。
3. **【中】显著性排序注入（修 A3）**：注入 prompt 的 8 条 LR 参考按"显著性分"（abnormal×new/changed×specificity）排序而非原序，落实外部方案 §6 salience。
4. **【中】末轮全家族坍缩防护（修 A12）**：更新后若 top-1 后验 < 阈值或全家族熵骤升，冻结/回退到上一轮分布，避免 AnswerMapper 拿全 0。
5. **【中】证据累积而非单条取最强（调 A9+A10）**：把 `enable_discrimination_gate` 设为默认候选，并允许同向多条弱证据有界叠加。
6. **【中】RAG 方向"软"利用（调 A8）**：不做硬覆盖，但把 RAG 抽到的方向作为 prompt 里显式的"外部证据方向"提示，让 LLM 有据可依（呼应最新 RAG-grounding 研究：faithfulness 可从 43%→99.5%）。
7. **【低】同义桥/疾病名归一化补齐（修 A4/A5）**：把 `lens dislocation↔ectopia lentis↔lens subluxation`、GSD 亚型名等纳入 `finding_synonym_bridge`/`disease_name_bridge`，消除退化条目命中。
8. **【低】prompt 显式约束（修 A13/A14）**：在 `evidence_annotator.txt` 增加"若 `lr_reference` 提供了某分支的 LR，方向必须与之一致；仅在无 LR 时才用临床判断"。

---

## 6. 数据源补充建议（含 CPG/Case report 定位与外部方案借鉴）

### 6.1 新增 CPG / Case report 能弥补什么、不能弥补什么

- **能弥补 D3 覆盖漏**：探针证明打开 RAG 后 `ESR→thyroiditis`、`LAP→leukemoid` 等常见鉴别发现全部补上。CPG 的 `differential`/`red_flag` chunk（`build_cpg_chunks.py:42` 已分类）正是缓存最缺的"常见综合征鉴别依据"。
- **不能弥补 D1/D4 的数值质量**：LR 抽取机器 `quantify_snippet` 是索引无关的，换成 CPG/case report 会遇到**相同的 pct 误读 + 默认 Sp 伪造**；case report 尤其危险（个案频率无统计意义）。
- **结论**：把 CPG/case report 作为**定性鉴别证据层**（抽 `finding_discriminates_for/against`、`red_flag`，带 provenance，注入 prompt 做方向锚定），**不要**直接喂 `quantify_snippet` 当定量 LR 源。

### 6.2 需要补的"真 LR"数据源（解决 D1/D2）

真正的似然比需要 **Sn+Sp 对**，应优先接入带真实统计量的源：
- **GetTheDiagnosis.org**（`build_unified_cache.py:5` 已列为最高优先，但当前缓存里 grounded 数值极少）——应核查其抽取是否真的落库、扩大覆盖。
- **诊断标志物手工表扩容**：探针证明所有正确强 LR 都来自这层；按 9 题与常见综合征缺口，**定向补充带 LR+/LR- 与来源的鉴别标志物**（如 LAP→类白/CML、ESR→亚急性甲状腺炎），比扩罕见病表更划算。
- **provenance 硬门控**：只有 `explicit:`（真实报告 Sn+Sp/LR）才进数值 LR 通道，`orphanet_rare` 频率桶降级为"仅方向/仅先验提示"——即把 `purify_entry` 思路设为默认。

### 6.3 借鉴外部 KG 方案（`构建临床诊断kg`）与最新研究

- **分离"共现"与"鉴别依据"**（外部 §1、§5）：建 `finding_discriminates_for/against`、`red_flag_for`、`diagnostic_criterion` 带方向边，而非频率共现——直接对治 D1 的"敏感度当 LR"。
- **provenance + 证据分级强制化**（外部 §5 第五层）：每条 LR/鉴别边带来源、证据等级、抽取模型、人工审核态；用它做 §6.2 的硬门控。
- **salience filtering 六标签**（外部 §6）：`episode_related/new_or_changed/severity/specificity/explained_by_background/diagnostic_role`，落实 §5-3 的显著性注入排序，把慢性基线异常降为 background。
- **KG 锚定 + 双向验证**（MedKGI / medIKAL / Nature Dual-Inf 2025）：用 KG 约束推理到已验证本体、用"正推诊断→反推代表症状→核验"替代 LLM 直接给 LR，强化 §5-6 的方向纠偏与 §2.3 的 reconcile。

---

## 7. 优先级路线图

| 阶段 | 动作 | 缺陷 | 风险 |
|---|---|---|---|
| P0 | pathognomonic 语义化(A7) + provenance 硬门控(D1/D2) | 立即止血伪 LR + 钉住确诊征象 | 低 |
| P0 | 定向补充常见综合征鉴别标志物(带真实 LR)(D3) | 补覆盖漏 | 低（纯加数据） |
| P1 | 特异度惩罚缩放(D1) + 显著性注入排序(A3) + 末轮塌缩防护(A12) | 系统偏差 + 塌缩 | 中 |
| P1 | CPG/case report 作定性鉴别层注入 + prompt 方向约束(A13/A8) | 覆盖 + 方向锚定 | 中 |
| P2 | 同义桥/疾病名归一化(A4/A5) + 证据累积(A9/A10 gate 默认) | 长尾 + 稀释 | 中 |

**一句话**：标注环节的失分是**数据源（95% 无真 LR、43% 是频率伪 LR、常见鉴别发现覆盖漏）**与**算法（pathognomonic 判定过严、归一化稀释、末轮塌缩、RAG 方向被一刀切禁用）**共同造成的；新增 CPG/case report 能补覆盖漏并作定性方向锚，但精确 LR 仍须靠带 Sn/Sp 的真统计源 + provenance 门控，不能指望从叙述文本可靠地量化出来。
