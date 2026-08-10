# 800 题轨迹机理解剖 R4：验证标签 + 因果归因 + 内部机制

> 主口径：`chain_correct`（臂是否真的说出金标）。`scored_correct`（DA option@1 / MCR diagnostic_hit）与 `mapper_rescue` 并列保留。  
> 证据根目录：`analysis/backbone_v1/r4_*`、`logs/backbone_v1/*/r4_i*`。  
> 本文件由 R4 流水线自动+人工汇总；**不编辑**计划文件本身。

---

## 0. 双口径统一与 R2/R3 对账

**产物：** `analysis/backbone_v1/r4_facts/{pooled,da,mcr}.tsv`、`summary.json`、`RECONCILIATION.md`

| 口径 | e7 | v0 | B06 | B07 |
|------|----|----|-----|-----|
| scored Acc (800) | 0.416 | 0.401 | 0.445 | 0.440 |
| chain Acc (800) | **0.203** | 0.194 | **0.323** | 0.273 |

- DA 上 e7 的 `mapper_rescue` 极大：scored≃2×chain。比较臂序必须拆开。
- `layer_chain`：`base_win_rank=98`，`base_win_recall=54`，`e7_win_*=17`，`both_correct=145`，`all_miss*=486`。  
  （scored 口径下 base_win_rank 曾报 39——**换口径后必须重报**。）

### R2 的 34/77 vs R3 的 10/77

同一批 `APHHM_locus=tree_hit_final_drop`（n=77）：

| 定义 | 计数 | 率 |
|------|------|----|
| R2：`e7_scored_correct` | 34 | 44.2% |
| R3：`e7_correct ∧ e7_locus==ok` | 10 | 13.0% |
| R4：`e7_chain_correct` | 13 | 16.9% |

差额 24 例中 **23 例是 `e7_mapper_rescue`**（21 DA / 3 MCR）。  
**不可写：**「扁平骨干救回了层次剪枝损失 44%」。  
**可写：**剪枝后 e7 全链路仍对约 13–17%；R2 的 44% 被 DA mapper 捡漏灌水。

---

## 1. 盲裁：标签错误率

**样本：** 210 例分层卡（`r4_adjudication/`），`cursor-grok-4.5-high` 子代理盲裁（不读 `failure_taxonomy` / `sample.tsv` 规则列）。

| 指标 | 值 |
|------|----|
| Cohen κ（失败码） | **0.14** |
| Cohen κ（簇，规则二值映射→四分类） | **0.17** |
| `near_gold` → 裁决 `unrelated` 假阳率 | 2.9%（2/70） |
| `near_gold` → 裁决仍属相关（same/parent/sibling） | **97.1%** |
| `base_win_rank` 同族份额（裁决） | **80%**，Wilson 95% CI **[0.68, 0.88]**（n=60） |

**成功标准判定：** κ < 0.6 → **规则失败码不得再作 R4 主叙事**。  
同簇头条修正：R3 的「52% 同簇」在盲裁四分类下上修为约 **80% [68%, 88%]**（同族：同一实体 / 父类-亚型 / 同族兄弟）。  
`near_gold` 的松词干规则假阳（判成无关）很少，但与裁决者的**细粒度码表**对齐很差——问题在失败码离散化，不在「是否相关」二值。

---

## 2. 反事实干预（机制归因）

约定：新 arm + `--reuse-from e7`；R4 为 `run_backbone_v1.py` 增加 `--keep-s2`（否则 `s2_k>1` 会强制丢掉复用的 S2）。  
`--case-id` 使用 **source_id**。

### I1：S4 必要性（`--select a` = 取 S3 首项）

| 切片 | e7 scored | I1 scored |
|------|-----------|-----------|
| DA seq100 / heldout / 200b | 0.59 / 0.58 / 0.555 | 0.58 / 0.57 / 0.515 |
| DA 加权 option@1 | **0.570** | **0.545** |
| MCR v1 / v2 / 200b Acc@1 | 0.28 / 0.23 / 0.27 | 0.22 / 0.21 / 0.235 |
| MCR 加权 | **0.263** | **0.225** |
| 800 题 chain Acc | 0.2025 | 0.2025（McNemar 35–35，p=1） |

**与 R2 对账：** `RESIDUAL_GAP_ANALYSIS_R2` 称「取 S3 首项胜过全部 S4」。在 **干净 800 题 + option@1/diagnostic_hit** 上 **未复现**：I1 略差于 e7-b。  
chain 口径净 Acc 相同但 70 例对打平局——S4-b 不是无操作，也不是稳赚。

### I2：S4 替代（`--select c/d`，s3_hit_s4_miss + 等量 ok，n=289）

| 臂 | chain Acc | vs e7 Δ | McNemar |
|----|-----------|---------|---------|
| e7-b（同子集） | 0.491 | — | — |
| select c | 0.474 | −1.7pp | 14–19，p=0.49 |
| select d | 0.422 | **−6.9pp** | 22–42，**p=0.017** |

scored（子集，偏高，不可外推全量）：DA c≈0.71–0.72，d≈0.68；MCR c≈0.43–0.53，d≈0.37–0.49。  
**结论：** 换 S4 变体不能修复 s4_miss；d 显著更差。

### I3：S3 必要性（`--force-s3`，同 n=289）

| 臂 | chain Acc | Δ | McNemar |
|----|-----------|---|---------|
| e7（复用 S3） | 0.491 | — | — |
| force-s3 + S4-b | 0.491 | **0** | 5–5，p=1 |

**结论：** 在该子集上重跑 S3 **不改变** net chain Acc——S3 不是「重跑就能抬分」的承重件；与 I4 合看，瓶颈在终裁偏好。

### I4：S4 转化天花板（gold 注入 S3 shortlist）

脚本：`scripts/paper/run_backbone_s4_oracle.py`（离线探针）。

| 池 | hits/n | 转化率 |
|----|---------|--------|
| DA 400 | 82/400 | 0.205 |
| MCR 400 | 83/400 | 0.208 |
| **Pooled 800** | **165/800** | **0.206** |

相对 e7 已有 chain 成功的分解：`both=156, only_I4=9, only_e7=6, neither=629`。  
**金标强制进表后，S4 几乎只在「本来就会选对」的题上选对；对其余 miss 题只多救回 9 例。**  
这与「S4 终裁是主承重」叙事直接矛盾，也解释了为何换 S4 变体（R2 八臂）难以抬 Acc：瓶颈是 **同簇近义终裁偏好**，不是「表里有没有金标」。

### I5：跨臂候选移植

| 设置 | chain Acc |
|------|-----------|
| e7 S3→S4（DA seq100） | 0.22 |
| B06 supervisor 候选 → e7 S4 | **0.27** |
| APHHM 树叶 → e7 S4 | 0.24 |
| e7（MCR v1） | 0.21 |
| B06→e7 S4（MCR v1） | 0.22 |
| B06→e7 S4 DA option@1 | **0.63**（e7=0.59） |

**分离结论：** 候选质量有小幅正贡献（DA chain +5pp），但远小于「S4 转化天花板」缺口；终裁质量仍是主约束。

### 机制归因表（chain 主口径）

| 机制 | Δ Acc（chain） | 证据 |
|------|----------------|------|
| 去掉 S4（取 S3[0]） | scored −2.5pp DA / −3.8pp MCR；chain Δ=0（35–35） | I1 |
| 换 S4-c | −1.7pp（n.s.） | I2 |
| 换 S4-d | **−6.9pp（p=0.017）** | I2 |
| 重跑 S3 | **0**（5–5） | I3 |
| 保证金标在 shortlist | **+9 例 / 800（+0.4pp，n.s.）** | I4 |
| 换 B06 候选进 e7 S4 | +3.0pp（n=200，n.s.） | I5 |
| 换 APHHM 叶进 e7 S4 | +2.0pp（n=100，n.s.） | I5 |
| DA mapper_rescue | scored−chain 巨大 | r4_facts |
| S3 丢金标 | 82.5% 因 S2 排位>5 | r4_internal |

---

## 3. 各臂内部机制

### 3a S3 为何丢金标（`r4_internal/s3_b06_summary.json`）

- `s2_hit_s3_drop` n=103；金标在 S2 的均位 **16.8**（ok 组 4.4）。  
- **`drop_rank_gt5_share=82.5%`** → 主因是 **排位过低 / k=5 硬截断**，不是「已在 top-5 仍被 why_kept 挤掉」。  
- 仅 17.5% 金标已在 S2 top-5 仍被 S3 丢掉（拥挤/改写类）。

### 3a′ B06 supervisor

- `base_win_rank` 下 B06 `supervisor_hit` 率 **85.7%**（chain 口径）。  
- DA `supervisor_miss_but_scored_ok` = **141/400（35.3%）** → 与 e7 mapper_rescue 同构，chain 下不应记为 B06 赢。  
- 金标首次出现在 discussion turn 0 占绝大多数（496）。

### 3b B07 refine / B01 RAG（`r4_internal/b07_b01_summary.json`）

- refine 字段为 **dict**（非空）；`refine==draft` 率 **93.4%**，`refine==diagnose` **93.3%**。  
  → R2「refine 读数 0」是解析口径问题；修好后结论是 **refine 近似空操作**，不是「没有 refine」。  
- locus：`draft_miss` 391，`diagnose_miss_but_scored_ok` 191（又是 mapper/judge 捡漏）。  
- B01：有 `served_access_ids` / chunk 计数，**无 chunk 正文** → 只能刻画检索行为；`rag_miss` 253/500 量级切片。

### 3c APHHM final 剪枝 vs e7 S3（`r4_internal/aphhm_prune_summary.json`）

- 77 例剪枝审计：`granularity.gate` 触发 **64/77**；`gold_capped_out` **0**（叶分保真里金标叶很少被标记为 capped_out）。  
- 同题 e7_locus：`s2_miss` 32，`s2_hit_s3_drop` 13，`s3_hit_s4_miss` 20，`ok` 10。  
- **部分同构：** ~43% 与 e7 同处「召回后终裁/剪枝失败」；~42% e7 入口就没召回。  
  → 「层次 vs 扁平」在剪枝损失上 **不是** 唯一解释；近义终裁病两边都有。  
- **可比性边界：** APHHM n=300；DA 用 `typed_llm` mapper，基线/骨干用 `typed_llm_disagreement_rag`——**不可混排 Acc 表**。

---

## 4. 共变与预测（`r4_covariates/`）

- 单变量置换检验 + BH：对 `y_e7_chain_fail`，**`n_opts_near_gold` AUC=0.69**（q_BH=0.028）——DA 选项近金标越多，chain 失败越少（选项结构信号）。  
- 对 `y_base_win_chain` / `y_s4_miss`：**最佳 AUC≈0.54–0.55**，无显著特征。  
- **诚实结论：** 除 DA 选项簇外，「无稳定 vignette 共性」成立；不可再堆 n=6 均值差叙事。  
- 基线独占（chain）n=152 桶：大量落在 `mcr|nosub|short|base_win_rank`（45）与 DA long gold——可分型但非单一题型。

---

## 5. 与平行分析线桥接

### vs `RESIDUAL_GAP_ANALYSIS_R2.md`（S4 消融）

| R2 主张 | R4 800 题检验 |
|---------|----------------|
| 取 S3 首项 ≥ 全部 S4 | **未复现**（I1 scored 更低；chain 打平） |
| S4 实现不转化 shortlist | **强确认**（I4：注入金标仅 +9 例） |
| 近义终裁是病 | **确认**（盲裁同族 80%；I4/I5） |

### vs `CLEAN_METRIC_VERDICT.md` §9–§12

- 轨迹结论与 n=400 McNemar **同用 chain/scored 双列**；DA 臂序优势在 scored 上含 mapper_rescue，chain 下 **B06/B07 更明显领先 e7**（0.32/0.27 vs 0.20）。  
- MCR 五臂非劣带仍成立；I1 说明换 select 变体不会把 e7 推出该带上方。

### APHHM

- 只使用已有 annotate/trees；不再建树。  
- n=300 + mapper 不一致 → 解释边界，不进主 Acc 表。

---

## 6. 可写 / 不可写清单

| 可写 | 证据 |
|------|------|
| DA scored Acc 大量是 mapper_rescue | `r4_facts/summary.json` |
| R2 的 34/77 被捡漏灌水；全链路约 13–17% | `r4_facts/RECONCILIATION.md` |
| 规则失败码 κ≈0.14，不可作主叙事 | `r4_adjudication/summary.json` |
| 同族终裁份额 ≈80% [68,88]（修正原 52%） | 同上 |
| S4 转化天花板 ~20.6%；注入金标几乎不救 miss | I4 `oracle_summary.json` |
| S3 丢金标主因 S2 排位>5（82.5%） | `r4_internal/s3_b06_summary.json` |
| B07 refine≈空操作（93% 等于 draft） | `r4_internal/b07_b01_summary.json` |
| B06 DA 35% supervisor_miss_but_scored_ok=捡漏 | 同上 |
| APHHM 剪枝与 e7 终裁失败部分同构 | `r4_internal/aphhm_prune_summary.json` |

| 不可写 | 原因 |
|--------|------|
| 「S4 是主承重、去掉会塌」 | I1/I4 反证 |
| 「取 S3 首项稳赢 S4」（全量 scored） | I1 未复现 R2 |
| 「层次剪枝是 APHHM 独有缺陷」 | 与 e7 S3/S4 同构证据 |
| 用规则五码做精确占比主文 | κ≪0.6 |
| 把 APHHM Acc 与基线/骨干混排 | mapper/n 不可比 |
| 用 scored 口径讲 DA「基线独占 119」而不标 rescue | chain 下数字已变 |

---

## 7. 产物索引

| 路径 | 内容 |
|------|------|
| `r4_lib.py` / `r4_facts.py` | 双口径事实表 |
| `r4_facts/RECONCILIATION.md` | 34↔10 对账 |
| `r4_adjudication/` | 盲裁卡、judgment、κ |
| `r4_interventions/` | I2 id 列表、机制表 |
| `r4_internal/` | S3/B06/B07/B01/APHHM |
| `r4_covariates/` | 协变量与 AUC |
| `scripts/paper/run_backbone_s4_oracle.py` | I4 |
| `scripts/paper/run_backbone_r4_transplant.py` | I5 |
| `logs/backbone_v1/*/r4_i*` | 干预 run |

---

*生成时间：R4 流水线完成（含 I1–I5）。机制表见 `r4_interventions/mechanism_table.json`。*
