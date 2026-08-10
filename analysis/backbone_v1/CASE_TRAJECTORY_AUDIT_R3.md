# 800 题轨迹机理解剖（R3）

> 升级自 [`CASE_TRAJECTORY_AUDIT_R2.md`](CASE_TRAJECTORY_AUDIT_R2.md)。  
> R2 停在位点名（`s3_hit_s4_miss`）；R3 把位点拆成**可复现失败码**，并用跨臂候选对齐回答「答对集分歧是同簇终裁还是真入口」。  
> 范围：DA400+MCR400=800；APHHM 仅已作答交集 n=300。零新增 LLM 调用。  
> 脚本：`candidate_alignment.py` · `failure_taxonomy.py` · `deep_covariates.py` · `mechanism_cards.py`（共享 [`r3_lib.py`](r3_lib.py)）  
> 表：`candidate_alignment/` · `failure_taxonomy/` · `deep_covariates/` · `mechanism_cards/`

## 0. 一句话

基线相对 e7 的净救回（`base_win_*`，n=56）里，**约 52% 是金标同簇上的终裁分歧**（`base_win_rank` 上更高达 **74%**），**约 30% 是真入口盲区**（e7 S2 未召回）。  
S4 已召回却排错时，主导码是 `rationale_overfit` / `parent_vs_subtype` / `near_synonym_prefer`（全量 147 例中无 `other`）。  
APHHM 剪枝 77 例里只有 10 例被扁平 e7 救回——层次召回优势多数时候两边一起死。

---

## 1. 对齐后的答对集分歧

数据：`candidate_alignment/summary.json`。

| 集合 | n | 同簇终裁翻转 | 真入口缺口 |
|---|---|---|---|
| `base_win_*`（基线对、e7 错） | 56 | **29 (52%)** | **17 (30%)** |
| 其中 `base_win_rank` | 39 | **29 (74%)** | 0 |
| 其中 `base_win_recall` | 17 | 0 | **17 (100%)** |

`base_win_rank` 层细节：

| | 率 |
|---|---|
| e7 S3 含金标簇 | 0.74 |
| e7 champion 落在 near 簇 | 0.36 |
| B06 supervisor 含金标簇 | 0.87 |
| B07 diagnose 含金标簇 | 0.74 |

**可检验主张：** 基线相对 e7 的净救回中，约一半是「大家都摸到了金标近义簇，骨干 S4 选错、基线终裁选对」；约三成是真入口；其余为 S3 剪枝等中间态（见 §2）。

典型同簇终裁：[`mechanism_cards/da_d2_heldout100_299.md`](mechanism_cards/da_d2_heldout100_299.md)  
gold=`Exophytic Schneiderian papilloma`；e7 S3 含 `Schneiderian Papilloma`，S4 选 `Inverted Papilloma`（`near_synonym_prefer`）；B06 supervisor 收 Schneiderian；APHHM 树含金标叶却 final 剪成 Inverted。

---

## 2. e7 失败码（全量）

数据：`failure_taxonomy/cross_tabs.json`。

### 2.1 `s3_hit_s4_miss`（n=147）— 零 `other`

| 失败码 | n | 含义 |
|---|---|---|
| `rationale_overfit` | 59 | rejected 含金标簇，却用「更宽/更特/不常用」话术拒掉 |
| `parent_vs_subtype` | 38 | gold 更特（subtype/括注/词数），champion 更宽 |
| `near_synonym_prefer` | 32 | champion 落在 near 簇，未硬匹配 gold |
| `option_echo_da` | 15 | DA：champion 贴近 distractor option |
| `label_drift` | 3 | shortlist 仅 resolver 命中，字面远离 |

### 2.2 `base_win_rank`（n=39）— 非平凡码 **39/39 = 100%**

| 失败码 | n |
|---|---|
| `rationale_overfit` | 11 |
| `near_synonym_prefer` | 7 |
| `s2_gold_low_rank`（实为 S3 前的低排位→落入 drop 路径的边界） | 7 |
| `parent_vs_subtype` | 6 |
| `s4_hit_judge_miss` | 4 |
| `s2_near_crowd_out` | 3 |
| `option_echo_da` | 1 |

> 成功标准达成：`base_win_rank` 非平凡码 ≥80%（实测 100%）。

### 2.3 `base_win_*` 合计（n=56）按 e7 码

| 桶 | n | 份额 |
|---|---|---|
| 终裁/近义类（`rationale_overfit`+`parent_vs_subtype`+`near_synonym_prefer`+`option_echo_da`+`s4_hit_judge_miss`） | 29 | **52%** |
| 真入口 `s2_miss` | 17 | **30%** |
| S3 拥挤/低位（`s2_gold_low_rank`+`s2_near_crowd_out`） | 10 | 18% |

与对齐表一致。

---

## 3. 各臂机制表

### 3.1 骨干 e7

| 优势 | 证据 |
|---|---|
| 短调用下 Acc 与强基线非劣（见 CLEAN §12） | MCR400 / DA400 |
| `e7_win_rank`（n=8）几乎全是 S4 命中且基线 judge/映射失手 | 对齐：同簇翻转 0.88 |

| 劣势 | 证据 |
|---|---|
| **S4 终裁**：已含金标仍选 near/父类 | 147 例 S4 miss；`base_win_rank` 主体 |
| **S3 剪枝**：低位金标或 near 拥挤 | `s2_gold_low_rank` / `s2_near_crowd_out` |
| **真入口**（次要） | `base_win_recall` 17 例，100% `s2_miss` |
| DA mapper 伪赢 | `e7_mapper_rescue` 须从 `e7_win_*` 剥离（R2 已报） |

**可写的机制排序（相对 R2 更硬）：**  
1. S4 近义/层级话术过拟合（`rationale_overfit`+`near_synonym_prefer`+`parent_vs_subtype`）  
2. S3 短表丢金标（低位/拥挤）  
3. 真入口盲区  
4. DA 选项回声（`option_echo_da`，体量小但机制清晰）

### 3.2 B06 MAC

- 在 `base_win_rank` 上 supervisor 金标簇命中率 **0.87**——终裁把讨论里已出现的 Schneiderian/同簇名收住。  
- 位点码：`b06_ok` 主导救回；仍有大量 `b06_supervisor_drop` / `b06_mapper_rescue`（DA）。  
- **机制：** discussion→supervisor 是「同簇稳定器」，不是更深检索。

### 3.3 B07 MEDDx

- `base_win_rank` 上 diagnose 金标簇 **0.74**。  
- 救回同样卡在 e7 的 S4/S3；draft 未召回时与 e7 `s2_miss` 同病。  
- **机制：** diagnose 终裁稳定性，不是 refine 链（R2 已警告 refine 字段弱）。

### 3.4 B01 CoT-RAG

- 相对 e7 net 仍为负（R2）；R3 不把它算进「强基线救回」主叙事。  
- 无 chunk 正文 → `rag_hit` 仍为启发式；机制卡只记 queries/top2。

### 3.5 APHHM（n=300）

| | n |
|---|---|
| `aphhm_tree_miss` | 136 |
| `aphhm_prune` | 77 |
| `aphhm_ok` | 66 |
| `aphhm_judge_miss` | 21 |
| 剪枝且 e7 仍对 | **10 / 77** |
| 剪枝且 e7 也错 | 65 / 77 |

- 独错（`aphhm_lose` 60）≫ 独对（`aphhm_win` 9）。  
- 剪枝优势几乎不能兑换成相对 e7 的终值优势：77 次剪枝里只有 13% 被扁平骨干救回。  
- **机制：** 树召回真有；final 剪枝 + 与 e7 共享的近义终裁病一起吃掉收益。

---

## 4. 外部变量（vignette / gold / options）× 失败码

数据：`deep_covariates/layer_by_failcode.json`（相对无分歧层的 572 例均值差）。

### 4.1 成立的共变

| 码（在 `base_win_rank`） | 信号 |
|---|---|
| `parent_vs_subtype` (n=6) | gold_has_subtype **+0.46**；选项近义对 **+1.5**；vignette 更长 **+25 词** |
| `near_synonym_prefer` (n=7) | gold 更短（Δ gold_words **−2.1**）；histo 密度略升 |
| `rationale_overfit` (n=11) | gold 更短（**−3.4**）；champion–gold Jaccard **更低（−0.24）**——话术拒掉的是字面更远的金标簇成员 |
| `option_echo_da` | 全量 S4 miss 有 15 例；`base_win_rank` 仅 1 例——存在但不是基线净胜主因 |

### 4.2 不成立 / 弱

- 「分歧题 = 更长 vignette」：仅 `parent_vs_subtype` 成立；`rationale_overfit` / `near_synonym` 反而更短。  
- 「实验室/鉴别措辞密度驱动」：效应量小、方向不一（与 R2 一致）。  
- 「eponym 专名」：非主轴。

**结论：** 外部变量不能单独预测谁赢；它们调节**哪一种终裁失败**会出现（亚型题→parent_vs_subtype；短粗金标→overfit/near）。

---

## 5. 机理卡索引

- **165** 张全量关键层卡：[`mechanism_cards/index.md`](mechanism_cards/index.md)  
  - `base_win_rank` 39 · `base_win_recall` 17 · `e7_win_*` 21 · `aphhm_*` 49 · `all_miss` 按码配额 39  
- 每卡含：对齐簇、失败码、S3 why_kept、**S4 rationale/rejected 全文**、基线终裁标签、APHHM final。

---

## 6. 主张边界

### 可写

- 800 题上 e7 对强基线非劣，但答对集不嵌套；基线净救回以**同簇终裁**为主、入口为次。  
- S4 失败可编码为近义/层级/选项回声，且 `base_win_rank` 上 100% 非平凡。  
- B06/B07 是两条终裁稳定路径；APHHM 剪枝很少转化为相对 e7 的优势。

### 不可写

- 「入口广度是 e7 主优势」（聚合零效应 + 净救回里入口仅 30%）。  
- 「基线靠多智能体/RAG 全面更强」（B01 net 负；B06/B07 优势在终裁）。  
- 「APHHM 层次带来终值优势」（独错≫独对；剪枝后 e7 仅救回 13%）。  
- 把 DA option@1 独占直接当诊断能力（mapper_rescue；选项 D 与 gold 同簇等）。

---

## 7. 复现

```bash
export PYTHONPATH=src:scripts:scripts/paper:analysis/backbone_v1
# 前置（若 census/loci 已在则可跳过）
# python3 analysis/backbone_v1/disagreement_census.py
# python3 analysis/backbone_v1/trajectory_locus.py

python3 analysis/backbone_v1/candidate_alignment.py
python3 analysis/backbone_v1/failure_taxonomy.py
python3 analysis/backbone_v1/deep_covariates.py
python3 analysis/backbone_v1/mechanism_cards.py
```

产物均在 `analysis/backbone_v1/{candidate_alignment,failure_taxonomy,deep_covariates,mechanism_cards}/`。
