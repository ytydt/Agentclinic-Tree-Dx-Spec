# CASE_TRAJECTORY_AUDIT R6 — 轨迹机制级解剖

> 把 R5 的占比计数升级为机制级解剖：噪声门控的胜集几何 → 题目协变量与轨迹内部决策变量 → 配对归因树 → 生成器×selector 交叉换装等五个因果探针。  
> 日期：2026-08-10。病例基底：R4/R5 的 800 例。每个分析小节强制包含：数字 / 机制解读 / 批判性审查 / 下一步实验建议 / 对算法计划的推论。

---

## 0. 对 R5 的一处错误标注（必须先登记）

**错误：** [r5_locus.py](analysis/backbone_v1/r5_locus.py) 把 APHHM-C selector 臂（collapse3c / multistance / msplit）的 `prune_loss` 子码写成 `score_below_frontier`。

**事实：** 这些臂的 `stages.c4` 被 skip，`ledger.cells` 均值 = 0，`registry.score` **恒为 0.0**。冠军 100% 由 LLM `frontier_selector` 决定，不存在数值 frontier 截断。

**修正：** 子码已改为 `no_numeric_score`，R5 locus 表已重跑（`prune_loss:no_numeric_score` 共 306 处；`score_below_frontier` 归零）。

**机制含义：** R5 把「金标在池但不在 shortlist」误读成了 ledger 排序失败；真实机制是 **提名/frontier 构造规则或 prompt 短名单截断**，不是分数。

**批判性审查：** 修正只改了子码名，没有改六桶归属；若有人基于旧子码写过「提高 score 就能进 frontier」，那条推论作废。

**下一步：** 在 multistance/msplit 上单独解剖 `frontier` 是如何从 `registry` 选出的（`unique_budget`、stance 内提名），不要再提 score。

**算法推论：** 不要给 collapse3c 加回 c4/ledger 幻想用分数救 prune；prune 的杠杆在提名结构。

---

## 1. 噪声门控的胜集几何

### 1.1 数字

复制对 exclusive-win null（同一臂两次运行：一方对另一方错的比率）：

| 臂 | n | exclusive_rate_either | stable_win_rate | champ_agree |
|---|---:|---:|---:|---:|
| aphhm_c_v1 | 378 | **0.113** | 0.069 | — |
| msplit | 391 | 0.090 | 0.166 | — |
| e7 | 400 | 0.083 | 0.160 | — |
| forest | 400 | 0.073 | 0.223 | — |
| collapse3c | 400 | 0.053 | 0.178 | — |
| lite | 400 | 0.055 | 0.223 | — |

**聚合噪声地板（跨臂 exclusive 解读阈值）：`0.113`**

焦点成对（chain，800 例；`a_only`/`b_only` 为 exclusive win 计数）：

| 对 | a_only | b_only | Jaccard | a_excl_rate | b_excl_rate | 过地板？ |
|---|---:|---:|---:|---:|---:|---|
| collapse3c vs forest | 34 | 78 | 0.547 | 0.043 | 0.098 | **否** |
| collapse3c vs lite | 39 | 60 | 0.568 | 0.049 | 0.075 | **否** |
| lite vs forest | 27 | 50 | 0.679 | 0.034 | 0.063 | **否** |
| collapse3c vs multistance | 20 | 32 | 0.741 | 0.025 | 0.040 | **否** |
| forest vs e7 | 85 | 34 | 0.518 | 0.106 | 0.043 | **边缘/否**（0.106 < 0.113） |

Rasch/1PL 能力（居中后）：`forest +0.28`、`impc +0.27`、`B06 +0.11`、`lite +0.07`、`multistance ≈0`、`collapse3c −0.13`、`e7 −0.20`、`v0 −0.27`。臂专属残差旗标 140/7200（约 1.9%）。

产物：`mosaic_eval/r6_winsets/`。

### 1.2 机制解读

R5 的冠军一致率 0.75–0.81 意味着：**单次运行的「A 对 B 错」大部分是运行噪声，不是稳定专长**。胜集 Jaccard 在 0.55–0.74，说明各臂大体答对同一批「易题」，差异主要是**能力水位**（Rasch），不是题型分工。

`stages` 无关——这是跨臂结果几何，约束的是后续所有「谁擅长哪类题」叙事。

### 1.3 批判性审查

- **无法验证：** stable_win 只在有 r2 的 dev 400 上定义；200b 无复制，holdout 上的「专属题」仍可能是噪声。
- **无法解释的反例：** forest vs e7 的 forest_only=85（rate 0.106）贴着地板——可能有一小撮真专属题，但本轮统计上不能宣称可分辨。
- **混淆：** chain 口径下 B06/B07 的 mapper_rescue 不进入胜集；若用 scored，几何会大变（R5 已证明）。
- **替代解释：**「能力差」与「专长差」被 exclusive-rate 混在一起；Rasch 残差才是专长候选，但 140 旗标未做人工核实。

### 1.4 下一步实验/分析建议

1. 对 Rasch 残差旗标做 50 例人工审阅，看是否集中于某模态（pathology/genetics）。  
2. 给 200b 也跑一对 forest/collapse3c 复制，把地板外推到 holdout。  
3. 用 **stable_win** 重做全部下游归因（当前归因仍用单次 primary）。

### 1.5 对算法计划的推论

- **可写：** forest/impc 是更高能力臂，不是「另一类题的专家」。  
- **不可写：**「forest 专治 collapse3c 不会的题」——exclusive 未过噪声门。  
- **不该动：** 为「互补集成」而简单投票/并集——并集增益会被噪声高估。

---

## 2. 题目协变量：谁在什么题上失败？

### 2.1 数字

新增/复用特征表 `r6_covariates.tsv`（n=800）：gold 语料流行度、`pathology_or_genetics_needed`（约 比例见 meta）、near-gold distractor 等。

| 臂 | cov→chain holdout AUC | cov→generation_miss |
|---|---:|---|
| collapse3c | 0.591 | （见 models.json） |
| forest | 0.587 | |
| lite | 0.571 | |
| multistance | 0.580 | |
| aphhm_c_v1 | 0.536 | |

成对模型 `P(A赢且B输 | covariates)` holdout AUC：

| 对 | A exclusive AUC | B exclusive AUC | exclusive 率 |
|---|---:|---:|---|
| forest vs collapse3c | 0.553 | 0.488 | 0.098 / 0.043 |
| multistance vs collapse3c | 0.545 | 0.471 | 0.040 / 0.025 |
| forest vs e7 | 0.590 | 0.513 | 0.106 / 0.043 |

### 2.2 机制解读

纯题型特征对单臂 chain 只有 **弱预测**（AUC≈0.54–0.59）。对「A 赢 B 输」同样弱（≈0.49–0.59）。**题面变量解释不了臂间差异的主体**——差异若存在，更可能在轨迹内部状态，而不在 vignette/gold 表面形态。

### 2.3 批判性审查

- 成对 exclusive 本身多数未过 §1 噪声门，因此即便 AUC=0.59 也不能写成「forest 优势题型是 X」。  
- gold prevalence 用多臂提案文档频率作代理，**不是**真实疾病发病率；稀有金标与「难」混淆。  
- MCR 的 options 是从 reasoning 抽的伪 MCQ，`n_option_near_pairs` 在 MCR 上语义弱于 DA。  
- **无法验证：** 专科/亚科元数据不存在，无法测「皮肤病 vs 心脏」专长。

### 2.4 下一步

1. 引入外部疾病频率（Orphanet / ICD 统计）替换语料 prevalence。  
2. 用 LLM 给 800 金标打 specialty 标签，再测成对模型。  
3. 只在 stable exclusive 子集上重拟合成对模型。

### 2.5 算法推论

- **不要**按「病理题 / 罕见病题」做臂路由——当前证据不足。  
- **要**把算力投向轨迹内部可干预量（生成视图、证据结构、短名单构造）。

---

## 3. 轨迹内部决策变量（核心层）

### 3.1 数字（`r6_mechvars_summary.json`）

| 臂 | chain | pool_has_gold | gold_disc | top_margin | unexplained_n | gen_jaccard | score_gap | gold_rejected | decision_loss 下 gold_disc |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| forest | 0.266 | 0.414 | **0.638** | **4.18** | **0.96** | 0.446 | 0.71 | 0.100 | 0.579 |
| lite | 0.238 | 0.393 | 0.632 | 1.69 | 2.70 | 0.316 | 0.40 | 0.094 | 0.536 |
| collapse3c | 0.211 | 0.384 | 0.434 | — | — | — | 0* | — | 0.389 |
| multistance | 0.226 | **0.545** | **0.147** | — | — | — | 0* | — | 0.121 |
| aphhm_c_v1 | 0.113 | 0.400 | —† | — | — | — | **2.92** | — | — |

\* selector 臂 score≡0。† c_v1 的 spans 未进入 disc（ledger 路径）。

multistance 失利轮次：`not_proposed 343` / `group_drop 163` / `final_drop 113` / `ok 181`（n=800）。

aphhm_c_v1：`mean_ledger_cells≈94.7`，`gold_veto_rate≈0.78`（金标概念曾被某种 veto 打到）。

**增量解释力（剔除 pool_has_gold 泄漏后）：**

| 臂 | 无条件 cov AUC | +mech Δ | **给定 pool 命中：cov→mech Δ** | 过预注册 Δ>0.02？ |
|---|---:|---:|---:|---|
| forest | 0.587 | +0.38 | **+0.340** | 是 |
| lite | 0.571 | +0.39 | **+0.312** | 是 |
| multistance | 0.580 | +0.29 | **+0.118** | 是 |
| collapse3c | 0.591 | +0.35 | **+0.038** | 是（边缘） |
| aphhm_c_v1 | 0.536 | +0.43 | **+0.353** | 是 |

`disc(gold)` 单独预测 chain（pool 命中子集）：collapse3c **0.541（未过 0.55）**；lite 0.605；multistance 0.590；forest 0.565。

### 3.2 机制解读（点名 stages 字段）

1. **forest vs lite（同族）：** `state_after_axes.top_margin` 4.18 vs `state_after_g.top_margin` 1.69；`unexplained_specific_evidence` 0.96 vs 2.70。三轴生成让数值排序更「分得开」，未解释特异证据更少——这是 **生成器几何**，不是 selector prompt 差异（二者共用 `selector`）。  
2. **multistance：** 池召回最高（0.545），但 `gold_disc` 极低（0.147）——三取向写入大量**共享** support_spans，证据不再判别。失利以 `group_drop`（组内赛）和 `not_proposed` 为主。对应 `frontier_selector.finalists` / `c3.stances`。  
3. **collapse3c：** 窄池 + 高 verbatim span（0.989）；内部变量对「池已命中后能否转」几乎帮不上（Δ=0.038）——瓶颈在 **进池之前**。  
4. **aphhm_c_v1：** ledger 全开后 `score_gap` 大、`gold_veto_rate` 高——`ledger.cells[].veto_reason`（p4/p5_*）与数值排序一起把金标压下去；chain 崩到 0.11。

MOSAIC 的 `gold_span_verbatim_rate=0` 是因为 `supporting_evidence` 存的是 **evidence_id**（如 `G1E001`）而非原文 span；disc 在 MOSAIC 上应读作 **证据 ID 共享率的互补**，与 APHHM 的 span-disc 不可直接比绝对值。

### 3.3 批判性审查

- 无条件 +mech 的巨大 Δ 仍可能被「金标不在池时 gold_* 缺失模式」部分泄漏；**以 given_pool 列为准**。  
- disc 预注册：collapse3c 未过 0.55 → **不得**在 collapse3c 上写「证据不判别导致失败」。forest/lite 刚过，效应小。  
- X2（共享证据剥离）在 §7 显示 **无效**——与 disc 的弱 AUC 一致：相关 ≠ 因果。  
- aphhm_c_v1 的 veto_rate 0.78 是「该概念任意 cell 被 veto」的宽松计数，不是「金标因此未进 frontier」的因果率。

### 3.4 下一步

1. 把 MOSAIC evidence_id 解析回 `evidence[].raw_span` 后重算 span-disc 与保真度。  
2. 对 aphhm_c_v1 的四类 `veto_reason` 做「是否阻断金标进入 ledger_rank」的因果计数。  
3. multistance：在 `group_drop` 子集上读 `frontier_selector.finalists[].why`，编码否决理由（现缺 rejected 列表）。

### 3.5 算法推论

- **优先复制 forest 的生成几何**（多轴 + 高 margin + 低 unexplained），而不是复制其 selector 文案。  
- **不要**靠「加更多共享证据 span」救 multistance——会进一步稀释 disc。  
- **不要**默认打开全量 C4 ledger（aphhm_c_v1 已展示净伤害）。  
- collapse3c：继续打 generation，不打 selector 微调用。

---

## 4. 拒绝理由编码

### 4.1 数字

金标出现在 `selector.rejected`（或 msplit `final.assessment.fails`）共 **406** 例。  
正则 vs LLM 一致率 **0.333** → `trust_final_labels=false`。

forest 子集（正则，较干净）：cited_contradiction 41 / less_specific 24 / fails_key_finding 14。  
msplit：other 133（assessment.fails 短语与 selector.why 分布不同，编码器失效）。

### 4.2 机制解读

MOSAIC 的 `stages.selector.rejected[{label,why}]` 是跨族唯一能直接读「金标被主动否掉」的通道。APHHM `frontier_selector` 只有全局 `why`，机制不可比。

### 4.3 批判性审查

- 一致率太低，**整张分类表不得作主证据**。  
- 「金标在 rejected」≠「若无 rejected 就会赢」——可能只是事后合理化。  
- msplit 的 fails 列表结构不同，强行共用六类是错误设定。

### 4.4 下一步

1. 只对 forest/lite 的 rejected.why 重写专用编码 schema，再测 κ。  
2. 因果探针：删除 rejected 中金标条目的 why 文本或强制 champion=gold 对照。  

### 4.5 算法推论

暂时 **不要**根据「矛盾引用 / 更常见」等拒绝话术改 prompt；等编码可信后再动。

---

## 5. 配对轨迹差分归因

### 5.1 数字（单次 primary；须对照地板 0.113）

| 方向 | n exclusive | generation_gap | prune | explicit_reject | silent_drop | identity_merge |
|---|---:|---:|---:|---:|---:|---:|
| forest⊤ collapse3c⊥ | 78 | 36 (46%) | 2 | 0 | **37 (47%)** | 3 |
| collapse3c⊤ forest⊥ | 34 | 10 | 0 | **12 (35%)** | 11 | 1 |
| multistance⊤ collapse3c⊥ | 32 | 7 | 0 | 0 | **24 (75%)** | 1 |
| collapse3c⊤ multistance⊥ | 20 | 3 | 3 | 0 | 12 | 2 |
| forest⊤ e7⊥ | 85 | 35 | 9 | 0 | 41 | 0 |
| e7⊤ forest⊥ | 34 | 12 | 0 | 7 | 12 | 3 |

（⊤=赢，⊥=输）

### 5.2 机制解读

- forest 赢 collapse3c：近半是 **collapse3c 根本没生成金标**（generation_gap），近半是金标进了决策集却 **silent_drop**（无 MOSAIC 式 rejected 字段可查）。  
- collapse3c 偶发赢 forest：forest 侧常见 **explicit_reject**（selector 写了否决金标的 why）——即 forest 的池里有金标但 selector 主动扔掉。  
- multistance 相对 collapse3c 的 exclusive 很少且未过地板；即便在这些噪声级差异里，也是 silent_drop 主导，不是「多取向生成多出来的题」。

### 5.3 批判性审查

- 所有 n_exclusive/N 均 **≤ 噪声地板**，叶子百分比只能当 **假设生成器**，不能当已证实机制份额。  
- silent_drop 是残余桶，可能混合：位置偏置、证据配额、随机性。  
- 例：`da/d2_seq100` 上需抽 silent_drop 卡做人工阅读（归因 JSON 的 examples 字段）。

### 5.4 下一步

1. 仅在 **双侧 stable** 的 exclusive 集上重跑归因树。  
2. 对 silent_drop 跑 X3/X4/X5 的局部版本（只改这些病例）。  
3. 把 forest 的 explicit_reject why 与 §4 编码器打通。

### 5.5 算法推论

- 若要追赶 forest：collapse3c 的第一刀仍是 **generation**；第二刀才是决策集内 silent_drop。  
- forest 自身有「会显式拒金标」的失败模式——改进 selector 对 forest 仍有边际，但 X1 显示边际小于生成器。

---

## 6. 因果探针（预注册判据逐条）

### 6.1 X1 生成器 × selector 交叉换装

**数字（dev 400，chain）：**

| 池 \ selector | mosaic sel | aphhm_c sel | 原臂基线 |
|---|---:|---:|---:|
| forest 池 (DA) | 0.255 | **0.265** | forest 0.270 |
| forest 池 (MCR) | 0.255 | **0.260** | forest 0.260 |
| collapse3c 池 (DA) | 0.185 | 0.190 | c3c 0.185 |
| collapse3c 池 (MCR) | 0.210 | 0.205 | c3c 0.215 |

**判据：** `forest_pool + aphhm_sel` 贴近 forest 基线，远离 collapse3c 基线 → **`advantage_in_generator`（DA/MCR 均成立）**。

**机制解读：** 换用 APHHM candev selector prompt+notes 几乎不掉点；换用 collapse3c 的池则直接掉到 collapse3c 水位。优势在 **`stages.registry` / 轴生成内容**，不在 `stages.selector` 的提示词族。

**批判性审查：**  
- shortlist 截断到 6、notes 字段对齐可能损失 forest 特有的 `axis_nodes`/`protected_reason` 信号——若有，会**低估** selector 族差异。  
- 未控制「同池同顺序」以外的 temperature 噪声；但四点估计非常贴基线，偶然性小。  
- **无法验证：** 若把 forest 的 score_logit 排序硬塞进 APHHM 提名，是否还能更高。

**下一步：** 做 X1b——保留 forest `score_logit` 排序作为 shortlist 序，只换 selector 正文。  
**算法推论：** 下一版算法应移植 **forest 的多轴生成与状态几何**，而不是移植 APHHM selector 文案；collapse3c 路线若要坚持低调用，必须改 c3 生成而不是 frontier_selector。

### 6.2 X2 共享证据剥离

Δ ≈ 0，全部不显著。  
**与 disc 预注册一致：** 不能写「证据不判别导致失败」为因果机制（至少不能靠「删掉共享 span」救）。  
**批判：** MOSAIC 上 for 列表常为 evidence_id，剥离逻辑可能没删到真正共享原文。  
**下一步：** ID→span 解析后再跑 X2。  
**算法推论：** 暂缓「去共享证据」工程。

### 6.3 X3 近邻兄弟移除

| 臂 | DA Δ | p | MCR Δ | p | 支持兄弟混淆？ |
|---|---:|---:|---:|---:|---|
| forest | **+0.059** | 0.007 | 0.000 | 1.0 | **仅 DA** |
| collapse3c | **+0.096** | 4e-6 | +0.010 | 0.69 | **仅 DA** |

**判据：** DA 上成立，MCR 上不成立。  
**机制：** DA 有真 MCQ 近邻干扰；MCR 伪选项/开放生成下兄弟结构不同。对应 shortlist 内 `near_gold` 非金标项。  
**批判：** 删除兄弟缩小了 shortlist，可能偶然抬高金标位置（与 X4 交互）；且只作用于「池中已有金标」的隐含子集。  
**下一步：** X3 后固定顺序再测；在 MCR 用 LLM 近邻定义重做。  
**算法推论：** DA 部署可加 **近邻去重/合并**；不能期望 MCR 同等收益。

### 6.4 X4 顺序置换

三种子序 spread ≤ 0.01（阈值 0.03）。  
**判据：** **不敏感** → R5 的 J1/J2 **不必**因「金标放首位」做修正。  
**批判：** 置换的是完整 shortlist；若金标本不在 shortlist，X4 无意义（本探针不注入金标）。  
**算法推论：** 位置偏置不是当前主矛盾。

### 6.5 X5 证据配额均衡

Δ≈0，不显著。  
**判据：** 「证据条数多者胜」不成立。  
**批判：** 只均衡了 for/against **条数**，未均衡判别度或关键发现覆盖。  
**下一步：** 按 disc 加权的配额，或强制双方引用同一组 decisive facts。

---

## 7. aphhm_c_v1 崩塌对照（ledger 全开）

### 7.1 数字

chain 0.113（dev400）；`score_gap` 均值 2.92；`gold_veto_rate` 0.78；池召回其实不差（0.40）。  
复制 null exclusive 0.113——自身噪声最大的臂之一，stable_win 仅 0.069。

### 7.2 机制解读

`c4` effects matrix + `ledger.cells` 的 p4/p5 veto 与数值 `score_components` 把决策从 LLM selector 接管后，**既放大了排序错误，又引入了运行不可复现性**（同一配置冠军更抖）。

### 7.3 批判性审查

未逐 veto 类型分解「若取消该类 veto，金标是否升至 ledger_rank[0]」——当前是相关。  
**下一步：** 对 p5_shared_phenotype 做反事实（放行被 veto 的金标 cell 后重算 rank）。  

### 7.4 算法推论

**确认关闭默认 C4/ledger 路径**；APHHM-C 的活路在 collapse3c/Multistance 的 LLM 决策，而非确定性矩阵。

---

## 8. 可写 / 不可写

### 可写

1. R5 的 `score_below_frontier` 是伪证；已更正为 `no_numeric_score`。  
2. 跨臂 exclusive win **普遍低于复制噪声地板**；臂差异首先是能力水位（forest/impc > collapse3c > e7），不是稳定题型专长。  
3. **X1：forest 优势在生成器（池），不在 selector 族。**  
4. 内部机制变量在 **pool 命中条件**下对 forest/lite/multistance 有增量解释力；collapse3c 增量很小→瓶颈在生成。  
5. multistance：高召回、低 disc、大量 group_drop；共享证据稀释是关键机制假说（相关成立，X2 因果未成）。  
6. X3：DA 上兄弟混淆是真机制；MCR 上不是。  
7. X4：顺序不敏感；R5 J1/J2 可继续引用。  
8. aphhm_c_v1 ledger 路径净伤害 + 高噪声。

### 不可写

1. 「forest 专治某类题 / 与 collapse3c 互补」——未过噪声门。  
2. 「selector 违背证据 / 证据不判别导致失败」作为 **collapse3c** 的因果结论（disc AUC 未过；X2 无效）。  
3. 「拒绝理由分布表明 …」——编码 κ 不足。  
4. 「全局身份唯一吃掉金标」——R5 已否；本轮 identity_merge 叶子也极少。  
5. 归因树叶子百分比作为精确机制份额。  
6. 无条件 mech AUC≈0.97 的字面解读（存在缺失模式泄漏风险）。

---

## 9. 开放问题登记表

> **R6.1 更新：** 下表保留历史动机；闭合状态以 **§13.10** 为准（Q1/Q4/Q5/Q7 已关；Q3 部分关；Q6 升级为大规模标注）。

| # | 问题 | 为什么现在答不了 | 怎样才能答 |
|---|---|---|---|
| Q1 | forest 相对 e7 的 85 例 exclusive 里有多少是稳定专长？ | ~~单次运行~~ → **已用 stable 答：不过地板** | — |
| Q2 | multistance 低 disc 是 span 真共享还是写法套话？ | 只有字符串相等 disc | 降级：X2 已否因果；语义去重非主线 |
| Q3 | MOSAIC rejected.why 的真类别分布？ | 正则-LLM κ=0.33 | 人工 50 条已给粒度主题；全量双人标高成本 |
| Q4 | silent_drop 的主导亚型？ | ~~残余桶未再分~~ → **近邻 47%** | — |
| Q5 | 取消 p5_shared_phenotype 能否救 aphhm_c_v1？ | ~~只有 veto 计数~~ → **newly_top1≈9%** | — |
| Q6 | 题型专长是否存在于 specialty 粒度？ | 无专科标签 | **大规模** LLM/UMLS 专科标注后再作成对模型 |
| Q7 | X1 是否低估了 selector，因丢掉 axis_nodes？ | notes 对齐不完整 | **X1b 已跑：不改变结论** |

---

## 10. R7 / 算法迭代优先级

> **R6.1 + §15：** 分析与 800 验收已完成。执行清单见 **§15.6**。摘要：

1. **P0 — 算法 v1：** ≤3–4 calls **内生** forest 式多轴池（不再复用预跑 forest）；800 复验达 compact/forest 水位。  
2. **P0 — 评测：** 主文并列 near-match（已有基线表）。  
3. **P1 — X3 生产版：** gold-aware 兄弟删除（**禁止**无监督全合并；§15.2 已证明有害）。  
4. **关闭：** 无监督 near-dedup 默认开启、ledger/veto、按专科路由、去共享 span。

---

## 11. 产物索引

| 产物 | 路径 |
|---|---|
| R5 子码修正 | `r5_locus.py` → `no_numeric_score` |
| 复制跑 | `run_r6_replicates.sh`；`*_r2` 臂 |
| 胜集 | `r6_winsets.py` → `mosaic_eval/r6_winsets/` |
| 协变量 | `r6_covariates.py` → `r6_covariates.tsv` |
| 机制变量 | `r6_lib.py`, `r6_mechvars.py` → `r6_mechvars.tsv` |
| 模型 | `r6_models.py` → `r6_models.json` |
| 拒绝理由 | `r6_reject_reasons.py` → `r6_reject_reasons.json` |
| 归因 | `r6_pairwise_attribution.py` → `r6_attribution.json` |
| 探针 | `scripts/paper/run_r6_probe.py`, `run_r6_probes.sh`, `r6_summarize_probes.py` → `r6_probes.json` |
| R6.1 闭合 | `r6_closure.py`, `r6_adjudicate_closure.py` → `mosaic_eval/r6_closure/`, `r6_adjudication/` |
| X1b / X2span | `logs/.../r6_x1b_forest_score_aphhm_sel`, `r6_x2_*_spanresolved` |

---

## 12. 一句话收束

**各臂答对集合的差异，在噪声门下主要是能力水位差，不是题型分工；forest 的水位来自生成器几何（X1），collapse3c 输在生成召回，multistance 赢了召回却用共享证据与组内赛把判别力和转化率吐回去——下一刀应砍在生成结构，而不是 selector 话术或 ledger 复活。**

---

## 13. R6.1 闭合迭代（对照计划 0c4d854f 的剩余差距 → 审查 + 轻量实验）

本节把 R6 正文里标为「需人工审查 / 零成本或轻量重跑」的项全部做完，直到**下一步只剩大规模实验或算法移植验收**。产物：`mosaic_eval/r6_closure/`、`r6_adjudication/`、`logs/.../r6_x1b_*`、`r6_x2_*_spanresolved`。

### 13.0 差距清单与处置

| 计划/R6 缺口 | 处置 | 结论是否可写 |
|---|---|---|
| stable_win 几何 + 归因未进正文 | 已算（dev400，地板 0.113） | 可写：仍不过噪声门 |
| Rasch 残差「真专长题」人工审 | 审查员审 20 例 pack | 可写：非专科专长证据 |
| MOSAIC `evidence_id`→`raw_span`；disc/X2 | 解析后重算 + DA seq100 X2 | 可写：verbatim≈0.95；X2 仍无效（甚至略伤） |
| aphhm_c_v1 veto 反事实 | 离线重放 `score_concept`，清 `p5_shared_phenotype` | 可写：几乎救不回 |
| 拒绝理由可信编码 | 审查员重标 forest/lite 金标 rejected 50 条 | 可写粒度主题；仍不可写自动 κ 分布 |
| silent_drop 亚型 | 稳定 exclusive 30 卡医学审查 | 可写：近邻/粒度主导 |
| multistance `group_drop` | 163 例统计 + 样例 | 可写：近半决赛是 near-gold |
| X1b（保留 score_logit 序） | DA seq100 跑完 | 可写：不改变「优势在池」 |
| genmiss AUC 未写入 | 从 `r6_models.json` 补录 | 可写：~0.58，弱 |

---

### 13.1 稳定胜集几何与归因（闭合 Q1 / R7-P0 分析）

**数字**

复制 null exclusive ≈ **0.113**。dev400 stable：

| 对 | a_only 率 | b_only 率 | Jaccard | a/b stable_acc |
|---|---:|---:|---:|---|
| forest vs collapse3c | **0.085** | 0.040 | 0.52 | 0.222 / 0.178 |
| forest vs e7 | **0.095** | 0.033 | 0.50 | 0.222 / 0.160 |
| multistance vs collapse3c | 0.030 | 0.020 | 0.76 | 0.188 / 0.178 |
| lite vs forest | 0.033 | 0.033 | 0.75 | 0.222 / 0.222 |

均 **低于** 0.113 地板。稳定归因（forest⊤ collapse3c⊥，n=30）：`silent_drop` 16、`generation_gap` 11、`identity_merge` 2、`prune` 1。forest⊤ e7⊥（n=32）：`silent_drop` 21、`generation_gap` 8。

**机制：** 双侧都对才算 win 后，跨臂「专属题」份额塌缩到噪声下；剩余森林赢例里，败方多数已生成金标却静默落选或根本没生成——与单次归因同构，但 n 更小、更可信。

**批判：** stable 只覆盖有 `_r2` 的臂；lite≡forest stable_acc 说明 MOSAIC 两档差异本身也不稳定。例：`da/d2_seq100/59`（prune）、`mcr/mcr_v1/76`（identity_merge）仍是稀有叶子，不能外推份额。

**下一步：** 停止用 exclusive 叙事专长；专长问题若还要问，必须先做 **专科标签 × 800**（大规模标注），见 §13.8。

**算法推论：** 不要做「按题型路由到某臂」；继续压低调用预算下的 **生成几何**。

---

### 13.2 审查员：Rasch 残差旗标（20 例）

**数字：** 20 旗标散布 8 臂（无单臂垄断）；tag：`path_driven` 10/20，`heme_onc` 7，`neuro` 6，`derm` 5；surprise hits 按臂近似均匀。

**机制：** Rasch 残差抓的是「相对能力出人意料」的观测，不是流水线某一 `stages` 键。

**批判 / 医学阅读：** 病理/遗传学 vignette 在残差里偏多，更像 **题难 + 模态** 混杂，不像「某臂专治皮肤病」。例：`da/d2_seq100/4` lite 命中 MVH、`da/d2_seq100/63` B07 命中 synchysis scintillans——均为罕见表型，复制一次即可翻转。

**结论：** **不可**把 Rasch 旗标写成臂专科专长；视为噪声加厚的残差样本即可。

**算法推论：** 不要根据残差清单加 specialty adapter。

---

### 13.3 审查员：silent_drop 亚型（稳定 forest⊤ 卡，n=30）

**数字**

| 亚型 | n | 率 |
|---|---:|---:|
| `near_sibling_confusion` | 14 | **0.47** |
| `true_wrong_family` | 6 | 0.20 |
| `gold_has_against_champ_clean` | 6 | 0.20 |
| `evidence_count_bias` | 4 | 0.13 |

**机制（点名字段）：** 败方 APHHM `frontier_selector` 无 `rejected[]`，金标在 shortlist/`registry` 却未夺冠 → 归因树 `silent_drop`。亚型由冠军标签 vs gold 的实体关系 + `for`/`against` 不对称判定。

**医学审查举例**

1. **近邻/病因粒度** — `da/d2_seq100/45`：gold=`Drug-induced dermatomyositis secondary to ipilimumab`；败方冠军 `Ipilimumab-induced Dermatomyositis`，胜方 `Dermatomyositis`。同一皮肌炎谱系，差别在药物归因是否写入标签——临床可接受为 near-match，严格 chain 则记失败。  
2. **真错家族** — `da/d2_seq100/27`：gold=`Histiocytoid Sweet syndrome`；败方 `Leukemia Cutis`。两者均可吃 CD68/MPO 皮损叙述，Sweet 需中性粒细胞真皮浸润 + 发热/血液病背景的综合，轨迹把血液病锚点压过了 Sweet 形态学。  
3. **against 不对称** — `da/d2_seq100/22`：MDA5 CADM；金标代理带 against（肌力 5/5），冠军 SLE against 空——selector 可能「罚」了更完整的金标笔记。

**批判：** `dc.match`/`near_gold` 偏字符串，会把部分 parent/subtype 打成 near_sibling；`granularity_flip` 在本包为 0 是因为规则阈值，不等于临床无粒度问题（见拒绝审查 50% 粒度相关）。

**下一步：** 局部已足够——silent_drop 主矛盾是 **近邻标签竞争 + 偶发 against 惩罚**，不是神秘 bug。大规模需要的是 **统一粒度/别名的评分口径**（算法+评测规范），而非再拆 30 卡。

**算法推论：** DA 侧延续 X3 近邻合并；APHHM 笔记避免「金标独有 against、干扰项零 against」的不对称书写。

---

### 13.4 审查员：MOSAIC 金标拒绝理由（forest/lite，n=50）

**数字：** 审查员分布 — `less_specific` 17、`other` 19、`fails_key_finding` 8、`cited_contradiction` 5、`prefers_common` 1。与正则一致率 **0.66**，与 LLM 编码器 **0.46**（原报告 κ≈0.33 的不可信判断维持）。冠军与 gold 呈 parent/near/same 关系的比例 **0.50**。

**机制：** 读的是 `stages.selector.rejected[].why`；审查员规则优先抓「不够特异 / 未解释主发现 / 矛盾」。

**批判：** 自动六类仍不可写分布；但人工样本支持：**一半拒绝发生在粒度邻近对上**，与 X3（DA）同向。例：`da/d2_seq100/11` forest why 称「原发是眶感染而非孤立泪囊炎」——临床上金标本就含继发视神经损伤，属于框架争执而非硬矛盾。

**算法推论：** 在可信自动编码完成前，**不要**按六类分布改 selector prompt；优先做 shortlist 近邻归并。

---

### 13.5 MOSAIC span 解析、disc、X2 重跑（闭合 R6 §6.2 批判）

**数字**

- ID→`stages.evidence[].raw_span` 后：forest mean `disc`≈**0.634**（与 ID 口径几乎相同）；**verbatim≈0.954**（n=331）。先前 closure 脚本 `verbatim=null` 是解析漏写，不是数据幻觉。  
- disc→chain（池内）AUC：forest **0.552**、lite **0.610** — forest **未过**预注册 0.55 门槛的稳健侧，lite 勉强过。  
- **X2 span-resolved（DA seq100）：** forest chain **0.24**（基线 0.30，Δ=−0.06，6 例只输不赢）；collapse3c **0.20**（基线 0.21）。旧 X2 为 0.29——解析后不是「没剥到」，而是 **剥共享 span 有害/无益**。

**机制：** `supporting_evidence` 存的是 `AX_SExxx`；探针现已解析后再做「删与其它候选共享的 for」。共享 span 常是真正的枢纽发现（影像/病理句），多候选同时引用不等于无信息。

**批判：** 仅 DA seq100；MCR 未重跑。但方向与预注册「AUC≤0.55 不得写因果」一致，且效应为负。

**下一步：** **停止** disc/X2 轻量迭代。

**算法推论：** 确认暂缓「去共享证据」工程；判别应靠 **生成端拉开候选支撑集**，不是 selector 删句。

---

### 13.6 X1b：保留 forest `score_logit` 序（闭合 Q7）

**数字（DA seq100）：** X1b = forest 池 + APHHM selector + score 序 → chain **0.32**；forest 基线 0.30；原 X1（ordered_diagnoses）0.29。相对基线 +0.02（仅 2 例单边改善），未超复制噪声叙事所需幅度。

**机制：** `shortlist_from(..., prefer_score_order=True)` 按 `registry.score_logit` 排序后只换 `aphhm_c_frontier_selector` 正文。

**批判：** 仍未注入 `axis_nodes`/`protected_reason` 全文；若这些字段有大作用，本探针仍可能低估。但 score 序是最强的可量化几何信号，已无效应，继续抠 notes 对齐的期望收益低。

**结论：** **不改变** X1 主结论——forest 优势在生成器/池几何，不在 selector 族或排序接口。

**算法推论：** 移植目标仍是 **多轴生成 + top_margin/unexplained 几何**，不是 APHHM selector 文案。

---

### 13.7 aphhm_c_v1：`p5_shared_phenotype` 反事实（闭合 Q5）

**数字：** 金标在 registry 且自身 cell 曾被 `p5_shared_phenotype` 标记：n=**82**。按 `EvidenceLedger.score_concept` 规则放行该类 veto 后重排：基线 top1=24 → 清 p5 后 top1=26；**newly_top1=5**（非 top1 子集上仅 **8.6%**）；rank 改善 18 例但多数仍非第一。`score_inversion` 仍为 0。

**机制：** `apply_gates` 中同向命中 ≥`shared_ratio` 候选的 fact 整行 veto；反事实恢复 `EFFECT_VALUE` 后重算 group-clip 证据分 + 原 `axis_bias`。

**批判：** 同时放行所有概念的 p5（正确模拟「关掉该规则」）会给竞争者同样加分，故金标难独占收益——这正是该规则的设计意图。例：`da/d2_seq100/60` OS-ASD 从 rank5→1（偶发得救）；`da/d2_seq100/11` 泪囊炎 rank7→7（加分不够）。

**结论：** **取消 p5 不能救活 ledger 路径**；崩塌是整体打分/可接纳结构问题，不是单一 veto 开关。

**算法推论：** 维持「关闭默认 C4/ledger」；不必再开 veto 消融的大规模网格。

---

### 13.8 multistance `group_drop` 深挖 + genmiss AUC

**数字**

- `group_drop` n=**163**；金标在 commit/coverage/mechanism 均高频出现后仍组内出局。  
- **near_gold_finalist_rate=0.49**：组提名决赛选手近半是金标近邻。  
- genmiss holdout AUC：collapse3c 0.584 / multistance 0.573 / forest 0.597 / lite 0.591 / aphhm_c_v1 0.645——协变量只弱预测「没生成」，主信号仍是 `gold_prevalence`。

**医学样例：** `da/d2_seq100/19` 金标「滤泡甲状腺癌伴柄胸骨侵犯」；组决赛变成 `Thyroid metastasis to bone` / `Thyroid cancer` / `Thyroid cancer with local invasion`——临床同谱，组内赛用近义标签互相挤掉精确金标。`da/d2_seq100/102` AEI 被 `Epidermolytic Hyperkeratosis` / `Ichthyosis Bullosa of Siemens` 挤出。

**机制：** stance 组内 LLM 提名 → `frontier_selector` 只见决赛名单；金标未入决赛则后期不可挽回。

**批判：** near_gold 字符串定义会高估「半对」；但方向稳定。

**下一步：** 组提名策略属于 **算法改动 + 全量 800 验收**，不是再统计一遍。

**算法推论：** multistance 优先改 **组内去重/粒度合并后再提名**；禁止叠加共享 span 补丁。

---

### 13.9 更新后的可写 / 不可写（相对 §8 的增量）

**新增可写**

1. stable exclusive **仍低于**复制地板 → 专长叙事关闭（不只是「建议重做」）。  
2. silent_drop 主亚型是 **近邻/粒度竞争**（~47%），真错家族约 20%。  
3. MOSAIC span 保真度高（verbatim≈0.95）；disc 解析后仍 **不足以**支撑「共享证据致败」因果；X2 解析后仍 null/有害。  
4. X1b 不改变「优势在池」。  
5. 清 `p5_shared_phenotype` newly_top1 仅 ~9% → 不救 v1。  
6. group_drop 近半决赛为 near-gold。  
7. 拒绝理由：人工样本支持粒度主题；自动编码仍不可写。

**维持不可写**

- 臂专科专长、自动拒绝六类分布、把归因叶子百分比当精确份额、无条件 mech AUC≈0.97 字面解读。

---

### 13.10 开放问题登记表（更新）

| # | 状态 | 说明 |
|---|---|---|
| Q1 稳定专长份额 | **已关闭** | stable exclusive < 地板 |
| Q2 multistance 低 disc 语义 | **降级** | 字符串 disc 已足够否定「删共享可救」；语义去重改为算法侧可选，不再挡主线 |
| Q3 拒绝理由真分布 | **部分关闭** | 人工 50 条给出粒度主题；全量双人标注属高成本，非算法关键路径 |
| Q4 silent_drop 亚型 | **已关闭** | §13.3 |
| Q5 取消 p5 救 v1？ | **已关闭** | newly_top1≈8.6% |
| Q6 专科粒度专长？ | **升级为大规模** | 需 UMLS/LLM 专科标签 ×800 后再作成对模型 |
| Q7 X1 是否低估 selector？ | **基本关闭** | X1b 无效；残差字段注入期望低 |

---

### 13.11 下一步：仅保留大规模 / 算法主线

轻量分析循环到此结束。建议顺序：

1. **大规模算法验收（P0）：** 实现「低调用骨架 + forest 式多轴生成几何」（目标 calls≈collapse3c，池质量≈forest）。验收：全量 DA+MCR（≥dev400，最终 800）上 chain 与 X1 式「新池+旧 selector」对照；复制 `_r2` 过噪声门。  
2. **大规模评测规范（P0/P1）：** 近邻/粒度敏感的二级指标（near-match / parent-subtype），避免只报严格 chain 时高估 silent_drop。  
3. **算法（P1，DA）：** shortlist 近邻去重（X3 已支持）嵌入主臂，800 验收。  
4. **算法（P1，multistance）：** 组内提名去重/合并，800 验收 `group_drop` 率。  
5. **可选大规模分析（P2）：** 专科标签后再问 Q6；不做则保持「无稳定题型专长」结论。  
6. **明确不做：** ledger/veto 网格、去共享 span、selector 话术按拒绝六类调参、再开一轮纯统计 R7。

---

### 13.12 R6.1 一句话

**人工审查与轻量探针把 R6 的开放尾巴收束为同一指向：差异是能力水位与生成/近邻结构问题，不是可调的 veto、共享证据或 selector 族；下一跳必须是 forest 几何的低成本移植并在全量数据上验收。**

---

## 14. R7 执行轮：未闭合下一步的全表推进

> 对照 §0–§13 全部「下一步」，把**无需大规模调用**的项做完，并把 §13.11 算法项落到代码/试点；大规模 800 验收登记为显式待办（本轮不跑满）。  
> 产物：`mosaic_eval/r7_offline/`、`COMPACT_FOREST_GEOM.md`、`near_dedup.py`、`run_compact_forest_aphhm.py`、`eval_near_match.py`、`logs/.../r7_*`、`compact_forest_v0`。

### 14.0 全表清单与状态

| 来源 | 建议 | 规模 | 本轮状态 |
|---|---|---|---|
| §0 | 解剖 frontier←registry（unique_budget/stance） | 离线 | **完成** |
| §1.4 | Rasch 旗标扩至 ~50 + 模态 | 离线审查 | **完成** |
| §1.4 | 200b forest/c3c 复制 | 大规模 | **登记** |
| §2.4 | 外部疾病频率替换 prevalence | 需外部表 | **阻塞**（无本地 Orphanet/ICD） |
| §2.4 | specialty×800 | 大规模 | **登记** |
| §2.4 | stable exclusive 成对协变量模型 | 离线 | **完成** |
| §3.4 | 四类 veto 反事实 | 离线 | **完成** |
| §3.4 | group_drop finalists.why 编码 | 离线 | **完成** |
| §4.4 | forest/lite 专用拒绝 schema + κ | 离线 | **完成**（相对审查员规则；非独立双人） |
| §4.4 | 抹 reject-why 因果探针 | 轻量 | **降级**：用 against-blank 代理未优先；X3 已覆盖主机制 |
| §5.4 | stable silent 上局部 X3/X4/X5 | 轻量 | **完成** |
| §5.4 | forest explicit_reject × 编码器 | 离线 | **完成** |
| §6.3 | X3 后固定顺序 | 轻量 | **完成**（X3f） |
| §6.5 | disc 加权配额 / 共享 decisive | 轻量 | **完成**（有害/无益） |
| §13.11 | near-match 二级指标 | 代码 | **完成** + 基线表 |
| §13.11 | shortlist 近邻去重入主臂 | 代码 | **完成**（`--near-dedup-shortlist`） |
| §13.11 | multistance 组内去重 | 代码 | **完成**（`--group-near-dedup`） |
| §13.11 | forest 几何低调用移植 | 代码+试点 | **v0 完成**（DA seq100） |
| §13.11 | 全量 800 + 复制验收 | 大规模 | **登记** |

---

### 14.1 Frontier 解剖（§0）

**数字（每臂抽样 ≤80/slice，合计见下）：**

| 臂 | n | mean registry | mean frontier 字段 | gold∈registry | gold∈frontier字段 | gold∈finalists |
|---|---:|---:|---:|---:|---:|---:|
| collapse3c | 480 | 5.27 | 4.29 | 0.379 | 0.350 | — |
| multistance | 480 | 8.90 | 4.17 | 0.550 | 0.354 | 0.371 |
| msplit | 320 | 8.87 | 4.16 | 0.534 | 0.341 | 0.319 |

**机制：** `selector_all_concepts=True` 时 selector 吃的是**全部 active registry**（生成序），不是 `stages.frontier`。`frontier` 字段仍写 main_k+protected_k，但 **不喂给** collapse3c/multistance/msplit 的 selector。multistance/msplit 的转化瓶颈在 `finalists`（组提名），金标 registry 召回 0.55 但 finalists 仅 ~0.37。

**批判：** 分析侧若用 `adapt_aphhm_c` 的 frontier 重建 shortlist，会**低估**真实决策集宽度。

**算法推论：** 近邻去重必须打在 **selector shortlist / groups**，不能只改 `_frontier()`。

---

### 14.2 Rasch50 / stable 成对模型 / 全 veto CF

**Rasch50：** n=50，臂分散；tag 以 heme_onc 稍多，**无单模态垄断**；维持「非专科专长」结论。

**Stable exclusive 成对 cov 模型：** 全部 `rate_a_excl < 0.113`；AUC 不稳（forest⊤e7 仅 0.44）。**即使在 stable 子集上，题型仍解释不了 exclusive。**

**Veto CF（金标曾被该类型打到）：**

| 清掉的 veto | n | newly_top1 率（非 top1 子集） |
|---|---:|---:|
| p5_shared_phenotype | 82 | 0.086 |
| p4_not_admissible | 6 | 0.333（n 极小） |
| p5_provisional_anchor | 8 | 0.000 |
| p5_scope_error_child_to_parent | 2 | 0.000 |
| 全部四类一起 | 87 | 0.082 |

**结论：** 关掉全部 P4/P5 也几乎救不回 v1；与 §13.7 一致并加强。

---

### 14.3 group_drop why / forest explicit_reject

**group_drop（n=142）：** near_gold_finalist **0.48**；why 码以 `stronger_for` / `other` 为主——组提名话术是「证据更强」，不是显式「金标太宽」。

**forest 金标 explicit_reject（n=73）：** granularity_related_champ **0.38**；why 多为 `other`/`broader_label`。与审查员拒绝样本同向：森林也会在粒度邻近上主动否金标。

---

### 14.4 拒绝 schema（§4.4）

相对 R6.1 审查员标签：专用 schema 一致率 **0.98**（规则同源，**不能**当独立双人 κ）。  
**可写：** schema 已稳定到可工程化过滤「粒度」类。  
**不可写：** 自动六类分布的科学 κ；仍禁止按分布改 prompt。

---

### 14.5 轻量探针（§5.4 / §6.3 / §6.5）

DA seq100（forest 基线 chain≈0.30）：

| 探针 | chain | Δ vs 基线 | 判读 |
|---|---:|---:|---|
| X3f（去兄弟+固定序） | **0.34–0.35** | **+0.04** | DA 兄弟混淆成立；固定序不抹掉收益 |
| X5d disc 配额 | 0.24 | −0.06 | **有害** |
| X5s 共享 decisive | 0.24 | −0.06 | **有害** |

stable silent_drop 子集（DA seq100，n=15，collapse3c 池重跑 selector）：

| 探针 | chain | 相对该子集再跑基线 |
|---|---:|---|
| 局部 X3 | **0.73** | +0.33 |
| 局部 X4 | **0.80** | +0.40 |
| 局部 X5 | 0.40 | 0 |

**批判：** n=15 且「基线」是同池重跑而非原始错例快照，X4 高命中含噪声；但 **X3 方向与全量 DA X3 一致**，强化 silent_drop≈近邻竞争。X5 仍无效。

**算法推论：** 上线 `--near-dedup-shortlist` / `--group-near-dedup`；放弃 disc 配额类补丁。

---

### 14.6 评测二级指标（§13.11）

全量 800（`eval_near_match.py` / `r7_offline`）：

| 臂 | chain | near_match | near−chain |
|---|---:|---:|---:|
| forest | 0.266 | **0.494** | 0.228 |
| lite | 0.238 | 0.490 | 0.253 |
| collapse3c | 0.211 | 0.495 | **0.284** |
| multistance | 0.226 | 0.495 | 0.269 |
| e7 | 0.203 | 0.494 | 0.291 |
| impc | 0.265 | 0.468 | 0.203 |

**机制解读：** 严格 chain 把大量 parent/near 记成失败；collapse3c 的 near−chain 最大——silent_drop 通胀最重。今后主文必须并列 near-match。

---

### 14.7 算法落地与 compact forest 试点

**代码**
- `src/agentclinic_tree_dx/near_dedup.py`
- `AphhmCPipeline(..., near_dedup_shortlist=, group_near_dedup=)` + CLI 开关
- `scripts/paper/run_compact_forest_aphhm.py` + `COMPACT_FOREST_GEOM.md`

**试点 DA seq100：** `compact_forest_v0` chain **0.32**（forest 0.30 / collapse3c 0.21）——与 X1「池≈forest」一致的可运行臂；calls≈4（3 axis + APHHM selector；A1 关）。

**批判：** v0 尚未压到 collapse3c 的 3-call；800 与复制未跑，不得宣称超越 forest。

---

### 14.8 外部 prevalence（§2.4）

仓库内无 Orphanet/ICD 表 → **阻塞**。加载约定：`analysis/backbone_v1/data/disease_prevalence.tsv`（`key,rate`）。在接入前继续用语料 prevalence，并保持「不可写流行病学稀有」纪律。

---

### 14.9 大规模待办（→ 已在 §15 跑满）

1. ~~`compact_forest_v0` 800 + r2~~ → **§15.1**  
2. ~~near-dedup collapse3c/multistance 800~~ → **§15.2**（结论：无监督全对合并有害）  
3. ~~200b forest/collapse3c 复制~~ → **§15.3**  
4. ~~specialty×800 + Q6~~ → **§15.4**  
5. 独立双人拒绝标注 — 仍可选，非算法关键路径。

---

### 14.10 更新后的可写增量

1. Selector 臂的真实决策集是 **active registry**，不是 `stages.frontier` 字段。  
2. 关掉全部 ledger veto 仍几乎不救 aphhm_c_v1。  
3. near-match 约 **0.49**，chain 与临床可接受匹配之间有 ~0.23–0.29 的缺口。  
4. X3f 证实：去兄弟收益在固定序下仍在；X5d/X5s 有害。  
5. silent_drop 局部 X3 大幅翻盘（小样本）。  
6. `compact_forest_v0` 试点达到 forest 水位（seq100）。

---

### 14.11 R7 一句话

**所有可离线/轻量的 R6 尾巴已清完：瓶颈在生成几何与近邻结构；代码钩子与 compact-forest 试点已就位——下一动作只剩全量 800（+复制）验收，而不是再开分析轮。**

---

## 15. R7 大规模验收（800 跑满）

> 执行 §14.9 清单。主控：`analysis/backbone_v1/run_r7_scale.sh`。汇总：`mosaic_eval/r7_scale/summary.json`。  
> 噪声地板参照 R6：`0.113`（复制 exclusive either）。

### 15.1 compact_forest_v0：800 + r2

**配置：** 复用 `mosaic_forest_v1` 池 + APHHM candev selector + `--near-dedup-shortlist`（selector-only，1 call/例）；`compact_forest_v0_r2` 同配置独立 cache。

**数字（n=800）**

| 臂 | chain | near_match | near−chain |
|---|---:|---:|---:|
| forest | **0.266** | 0.494 | 0.228 |
| **compact_forest** | **0.254** | 0.484 | 0.230 |
| compact_forest_r2 | 0.256 | 0.484 | 0.228 |
| collapse3c | 0.211 | 0.495 | 0.284 |

复制（compact vs r2）：exclusive either **0.0025**，Jaccard 0.99（T=0 + 同池 → 几乎确定性）。  
compact vs forest：exclusive either **0.040** ≪ 0.113；compact vs collapse3c：compact_only 率 0.090。

**判据**
- `compact_reaches_forest`：**是**（Δ chain = −0.012，在 ±0.02 容差内）  
- `compact_beats_collapse3c`：**是**（+0.043）  
- 复制低于地板：**是**

**机制：** 再确认 X1——把 forest 几何池接到 APHHM selector，水位跟 forest，不跟 collapse3c。

**批判：** v0 仍依赖已生成的 forest 池（未压到 3-call 内生轴）；r2 几乎无噪声不能用来估「能力抖动」，只能说明 selector 确定性。压调用的 v1（单次 batched multi-view C3）仍待实现，但**验收假设「池≈forest」在 800 上成立**。

**算法推论：** 主路径继续做 **低调用生成几何移植**；不要改 APHHM selector 文案追 forest。

---

### 15.2 near-dedup 嵌入主臂（800）— 负结果

**配置：** selector-only 重跑；collapse3c=`flat` 全 shortlist `dedupe_labels`；multistance=`tournament` + `group_near_dedup`。

| 臂 | chain | vs 原臂 Δ |
|---|---:|---:|
| collapse3c | 0.211 | — |
| collapse3c_neardedup | **0.180** | **−0.031** |
| multistance | 0.226 | — |
| multistance_neardedup | **0.208** | **−0.019** |

成对：nd 相对原臂 exclusive 极少且多为原臂赢（c3c：nd_only=3 / base_only=28）。

**机制解读：** 本实现是**无监督全对近邻合并**（更长标签优先），与探针 X3「只删 near-gold 的非金标兄弟」**不是同一操作**。合并可能把金标并进错误的更长别名，或删掉必要鉴别项。

**批判 / 下一步：** 生产默认 **关闭** `--near-dedup-shortlist` / `--group-near-dedup`。若要用 X3，必须改成 **gold-aware 或仅删 shortlist 内互为 near 且保留更特异且与证据一致的一项**，并再跑 800——当前无监督版不可上线。

**算法推论：** DA 上 X3 的收益不能靠「盲目近邻折叠」兑现。

---

### 15.3 200b forest / collapse3c 复制 → 外推噪声地板

在 `d2_heldout200b` + `mcr_200b`（n=400）上补齐 `mosaic_forest_r2` / `aphhm_c_collapse3c_r2`（此前仅 400 有 r2）。

| 复制对 | n | exclusive either | a_excl | Jaccard |
|---|---:|---:|---:|---:|
| forest vs forest_r2（200b） | 400 | **0.053** | 0.030 | 0.82 |
| collapse3c vs r2（200b） | 400 | **0.038** | 0.020 | 0.84 |
| forest vs r2（全重叠 800） | 800 | 0.063 | 0.036 | 0.79 |
| collapse3c vs r2（800） | 800 | 0.045 | 0.021 | 0.81 |

**解读：** 200b 上的复制噪声 **低于** R6 聚合地板 0.113（该地板被 aphhm_c_v1 等高噪臂抬高）。用 0.113 解释跨臂 exclusive 仍然保守安全；若只比较 forest/collapse3c，可采用 ~0.05–0.06 的更紧地板——**即便如此，§1 的跨臂 exclusive 仍多数不过门**。

**算法推论：** holdout200b 不改变「能力水位而非题型专长」的主结论。

---

### 15.4 Specialty×800 + Q6

**标注：** 774 个唯一金标 → 13 类专科（缓存 LLM）。分布头部分：heme/onc 112、ID 109、derm 106、cardio 78、neuro 69。

**成对 exclusive ~ specialty one-hot（holdout AUC）**

| 对 | A exclusive AUC | B exclusive AUC | A excl 率 |
|---|---:|---:|---:|
| forest vs collapse3c | 0.491 | 0.488 | 0.098 |
| forest vs e7 | 0.488 | 0.527 | 0.106 |
| multistance vs collapse3c | **0.606** | 0.491 | **0.040** |

按专科的 exclusive 率（例 forest⊤collapse3c⊥）：cardio 0.128、derm 0.120——贴着或低于 0.113 地板；multistance 对 collapse3c 的全局 excl 仅 0.04，AUC 0.61 **不可写成专长**（预注册：不过噪声门的 exclusive 不能叙事）。

**Q6 结论：** **不可写**「某臂专治某专科」。专科标签未解锁稳定题型分工。

---

### 15.5 可写 / 不可写（大规模增量）

**可写**
1. compact_forest（forest 池 + APHHM selector）在 **800** 上达到 forest 水位并显著高于 collapse3c。  
2. 200b 复制噪声 ≈0.04–0.06，支持把 0.113 当作保守上界。  
3. 无监督近邻全合并在 800 上 **伤害** collapse3c/multistance。  
4. Specialty 条件化后仍无过门的臂专长。

**不可写**
1. 「已上线近邻去重并涨点」——实测跌点。  
2. 「compact_forest 已是 3-call 内生生成器」——当前复用 forest 池。  
3. 「心脏病/皮肤病上 forest 有稳定专长」——专科 exclusive 未过紧地板。

---

### 15.6 下一步（真正剩下的）

1. **算法 v1：** 在 ≤3–4 calls 内**内生**多轴/多视图池（不依赖预跑 forest），800 复验 compact 水位。 → **已执行，见 §16**（v1 chain=0.244 > collapse3c，逼近 forest）。  
2. **X3 生产版：** gold-aware / 证据一致的兄弟删除（非盲目 merge），小流量 A/B → 800。 → **已执行，见 §16**（证据 X3 对 v1 有害 / 对 v0 null；默认关闭）。  
3. 可选：独立双人拒绝标注；Orphanet prevalence 表接入。

---

### 15.7 一句话

**大规模跑满后主结论不变且更硬：移植 forest 池几何就能在 800 上站上 forest 水位；盲目近邻合并会掉点；专科标签也挖不出过噪声门的题型专长——下一刀只剩「把该几何用低调用自己长出来」。**


---

## 16. CompactForest v1 内生多轴 + 证据一致 X3（§15.6 执行）

> 执行 §15.6。主控：`analysis/backbone_v1/run_compact_v1_scale.sh`。汇总：`mosaic_eval/r7_scale/compact_v1_summary.json`、`compact_v1_pairs.json`。  

### 16.1 设计

| 臂 | 池 | 选择器 | 调用 | 备注 |
|---|---|---|---:|---|
| `compact_forest_v0` | 复用 `mosaic_forest_v1` | APHHM candev | 1 | §15 已验收 |
| `compact_forest_v1` | **内生** `MosaicBatchedAxes`（单次三轴） | APHHM candev | **2** | 不依赖预跑 forest |
| `*_x3ev` | 同上 | + `evidence_consistent_sibling_dedupe` | +0 | 非盲目 merge；按证据可分性留兄弟 |
| `*_x3oracle` | 同上 | + `x3_drop_near_siblings(gold)` | +0 | 仅诊断上限 |

产物：`scripts/paper/run_compact_forest_v1.py`、`reselect_compact_x3.py`；`near_dedup.py` 增 X3；prompt `mosaic_batched_axes.txt`。

### 16.2 DA seq100 试点

| 臂 | chain | near |
|---|---:|---:|
| forest | 0.30 | 0.59 |
| collapse3c | 0.21 | 0.62 |
| compact_forest_v0 | 0.31 | 0.59 |
| **compact_forest_v1** | **0.31** | 0.59 |
| v1_x3ev | 0.30 | 0.58 |
| v1_x3oracle | 0.32 | 0.59 |

**门控：** v1 追平 forest/v0、显著高于 collapse3c → 进入 800。Oracle X3 仅 +1pp → 兄弟删除天花板极薄。

### 16.3 全量 800

| 臂 | n | chain | near | vs collapse3c | vs forest |
|---|---:|---:|---:|---|---|
| forest | 800 | **0.266** | 0.494 | +0.055 | — |
| compact_forest_v0 | 800 | 0.254 | 0.484 | +0.043 | −0.012 |
| **compact_forest_v1** | 800 | **0.244** | 0.475 | **+0.033** | −0.022 |
| v0_x3ev | 800 | 0.253 | 0.484 | +0.041 | −0.014 |
| v1_x3ev | 800 | 0.226 | 0.466 | +0.015 | −0.040 |
| collapse3c | 800 | 0.211 | 0.495 | — | −0.055 |

成对 exclusive（chain）：

| 对 | a_only | b_only | either | a_excl |
|---|---:|---:|---:|---:|
| v1 vs forest | 42 | 60 | 0.128 | 0.053 |
| v1 vs collapse3c | 72 | 46 | 0.148 | 0.090 |
| v1 vs v0 | 46 | 54 | 0.125 | 0.058 |
| v1 vs v1_x3ev | 23 | 9 | 0.040 | 0.029 |
| v0 vs v0_x3ev | 9 | 8 | 0.021 | 0.011 |

按切片：v1 在 **DA** 上贴近 forest（seq100 0.31、heldout200b 0.28）；缺口主要在 **MCR**（mcr_v1 0.21 vs forest 0.31；mcr_200b 0.195 vs 0.245）。

### 16.4 可写 / 不可写

**可写**
1. **2-call 内生** compact_forest_v1 在 800 上 **高于 collapse3c**（+3.3pp），接近 v0/forest，证实「多轴池几何」可用单次 batched axes **自己长出来**，不必预跑 3–4 call forest。  
2. 证据一致 X3 在 **强池（v0/forest）上近似 null**（−0.1pp）；在 **弱池（v1）上有害**（−1.7pp）——与盲目 near-dedup 同向，不可作默认。  
3. Gold-oracle X3 上限 ≈+1pp（seq100）→ 兄弟竞争不是主瓶颈。

**不可写**
1. 「v1 已完全追平 forest」——仍差 ~2.2pp，且 MCR 缺口更大。  
2. 「上线证据 X3」——800 上对 v1 掉点。  
3. 「v1 已是 0-call 池」——仍需 1 次 batched + 1 次 selector。

### 16.5 批判与优先级

- Batched 单 call 的轴质量仍弱于独立三轴（尤其 MCR）；下一刀是 **提高单 call 池召回/特异性**（更强约束、可选廉价 facts 预抽取变成 3-call），而不是再拧 selector / X3。  
- v1 vs forest exclusive either 0.128 贴着保守噪声地板——差异叙事要克制。  
- 生产默认：**compact_forest_v1（或继续用 v0 复用强池）**；**关闭** blind near-dedup 与 evidence-X3。

### 16.6 下一步（若继续）

1. 强化 `MosaicBatchedAxes`（或 2+1：短 facts + axes）把 MCR 池召回拉到 forest。 → **已执行，见 §17**（v11_facts 800 chain=0.258）。  
2. 可选：v1 `_r2` 仅在 DA 或全量，确认 0.244 水位稳定。 → **已做 DA seq100 r2=0.30**。  
3. Orphanet / 双人拒绝标注仍为低优先可选。

### 16.7 一句话

**2-call 内生 compact_forest_v1 已在 800 上跨过 collapse3c、逼近 forest；证据 X3 再证实不能当默认——下一刀只剩把 batched 池在 MCR 上的召回补齐。**


---

## 17. CompactForest v1.1：补 MCR 池召回（§16.6 执行）

> 执行 §16.6。诊断：`mosaic_eval/r7_scale/v1_pool_gap.json`。主控：`run_compact_v11_scale.sh`。汇总：`compact_v11_summary.json`、`compact_v11_pairs.json`。  

### 17.1 缺口诊断（为何不是再拧 selector）

| 家族 | 臂 | gold_in_pool | P(chain\|pool) | chain |
|---|---|---:|---:|---:|
| MCR | v1 | 0.343 | 0.628 | 0.215 |
| MCR | forest | 0.365 | 0.692 | 0.253 |
| DA | v1 | 0.438 | 0.623 | 0.273 |
| DA | forest | 0.463 | 0.605 | 0.280 |

MCR 精确池只差 ~2pp，但 forest⊤v1⊥ 的漏召回样本多为**稀有具名实体**（MIS-C、lipoblastoma、clear cell sarcoma…）；同时 v1 注册表过小（~4）。→ 优先 **加宽/锚定 batched 池**，不是 X3。

### 17.2 设计

| 臂 | 预算 | 改动 |
|---|---:|---|
| `compact_forest_v11` | 2 | 强化 `mosaic_batched_axes`：每轴 4–5 候选 + rare_hooks 召回 |
| `compact_forest_v11_facts` | **3** | `MosaicKeyFacts` → BatchedAxes（注入 facts/rare_hooks）→ selector |
| `compact_forest_v1_r2` | 2 | DA seq100 复制（水位稳定性） |

### 17.3 试点（MCR×2 + DA seq100）

| 臂 | mcr_v1 | mcr_v2 | DA | MCR均值 |
|---|---:|---:|---:|---:|
| v1 | 0.21 | 0.26 | 0.31 | 0.235 |
| v11（2-call） | 0.22 | 0.20 | 0.27 | 0.210 |
| **v11_facts（3-call）** | **0.30** | 0.19 | 0.29 | **0.245** |
| forest | 0.31 | 0.21 | 0.30 | 0.260 |

**门控：** 纯 prompt 加宽 **伤害** DA/mcr_v2 → 淘汰。facts+axes 在 mcr_v1 追上 forest、DA 仅 −2pp → **放行 800**。

### 17.4 全量 800

| 臂 | n | chain | near | vs v1 | vs forest | vs collapse3c |
|---|---:|---:|---:|---|---|---|
| forest | 800 | **0.266** | 0.494 | — | — | +0.055 |
| **v11_facts** | 800 | **0.258** | 0.481 | **+0.014** | −0.009 | **+0.046** |
| v0 | 800 | 0.254 | 0.484 | +0.010 | −0.012 | +0.043 |
| v1 | 800 | 0.244 | 0.475 | — | −0.022 | +0.033 |
| collapse3c | 800 | 0.211 | 0.495 | −0.033 | −0.055 | — |

成对 exclusive（chain）：

| 对 | a_only | b_only | either |
|---|---:|---:|---:|
| v11_facts vs v1 | 54 | 43 | 0.121 |
| v11_facts vs forest | 45 | 52 | 0.121 |
| v11_facts vs collapse3c | 73 | 36 | 0.136 |

MCR 池召回：v11_facts gold_in_pool **0.417**（v1 0.343；avg registry ~9.3 vs ~4.5）。

切片：mcr_v1 0.30≈forest 0.31；mcr_200b 0.225≈v0；mcr_v2 仍弱（0.19）。DA 整体不掉（heldout200b 0.29=forest）。

### 17.5 v1 复制（DA seq100）

| 臂 | chain | exclusive either |
|---|---:|---:|
| v1 | 0.31 | — |
| v1_r2 | 0.30 | 0.13 |

水位稳定；复制噪声与 forest/c3c 紧地板同量级。

### 17.6 可写 / 不可写

**可写**
1. **3-call** facts→batched→selector 把内生 compact 从 0.244 抬到 **0.258**，超过 v0、距 forest **<1pp**。  
2. 机制是 **MCR 池召回**（0.34→0.42）+ 更大注册表，不是 selector/X3。  
3. 仅加宽 2-call prompt **不够**且可能伤 DA。

**不可写**
1. 「2-call 已追平 forest」——v11 试点失败。  
2. 「已超越 forest」——仍差 ~0.9pp，exclusive 未过噪声门。  
3. 「mcr_v2 已修好」——仍是弱切片。

### 17.7 生产默认与下一步

- **有预跑 forest 池：** 继续 `compact_forest_v0`（1-call selector）或直接 forest。  
- **需内生：** 默认 **`compact_forest_v11_facts`（3 calls）**；关闭 X3 / blind near-dedup。  
- 下一刀（若还要抠）：针对 mcr_v2 的稀有实体/长病历召回，或接受 <1pp 残差为噪声。  
- Orphanet / 双人拒绝仍低优先。

### 17.8 一句话

**用 1 次廉价 KeyFacts 锚定后，3-call 内生池在 800 上超过 v0、逼近 forest；证明 §16 的残差主要是池召回，而且补得动。**

