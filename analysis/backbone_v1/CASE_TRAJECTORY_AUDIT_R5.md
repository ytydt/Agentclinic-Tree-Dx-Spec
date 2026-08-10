# CASE_TRAJECTORY_AUDIT R5 — 跨族轨迹机制审计

> 把 APHHM-C 变体与 MOSAIC 族纳入案例轨迹机制审计，并把 R1–R4 按 stage 命名的分析范式改造成按机制命名的跨族范式。新增身份生命周期、证据不对称、取向溯源三条只有新方法才支持的机制轴，并补上运行间噪声门这一 R1–R4 缺失的前提。
>
> 日期：2026-08-10。病例基底：R4 的 800 例（DA400+MCR400）。分析脚本零 LLM；干预 J1–J3 与同配置重复跑消耗 LLM。

---

## 0. 为什么 R1–R4 的范式不能直接套用

三条不匹配：

1. **locus 是 stage 名而非机制名。** `e7_locus = s2_miss / s3_hit_s4_miss` 对 MOSAIC / APHHM-C 无定义——它们是「多视图生成 → 全局身份 registry → 门控 → frontier → selector」。
2. **`baseline_dissection.py` / `aphhm_funnel.py` 逐臂硬编码**，扩到 13 臂不可复用。
3. **R1–R4 把逐例轨迹当作事实。** `temperature=0` 下同配置重复的候选池 Jaccard 仅约 0.60、冠军约 25% 会翻（见 §3）。任何逐例机制结论必须先过稳定性门。

三条新增能力（R1–R4 想做但做不到）：

- 身份生命周期（`events` / `merge_audit`）
- 逐候选证据（`support_spans` / `contradict_spans`）
- 视图溯源（`stances` / `generator_views` / `axis_nodes` / `agent_votes`）

---

## 1. 臂集、口径与统一读取层

**13 臂（每个代表一种独立机制）：**

| 族 | 臂 | 覆盖 |
|---|---|---|
| APHHM-C | `aphhm_c_v1`, `collapse3c`, `multistance`, `multistance_r2`, `msplit` | v1/r2/msplit 仅 dev400；其余 800 |
| MOSAIC | `lite`, `forest`, `impc`, `adaptive4v2` | adaptive4v2 仅 400；其余 800 |
| 参照 | `e7`, `v0`, `B06`, `B07`, 原 `APHHM` | APHHM=300；其余 800 |

**双口径（强制）：** 全部臂同时报 `scored_correct` / `chain_correct` / `mapper_rescue`（复用 `r4_lib`）。DA 上 scored−chain 差距仍约 20–30pp，只报 scored 会得出相反臂序。

**统一 Trajectory**（`r5_lib.py`）：三种 layout → `{candidates[label,views,for,against,status], shortlist, finalists, champion, events, gate}`。

**六桶 locus（按首次命中）：**

```
generation_miss → identity_loss → prune_loss → decision_loss → interface_loss → ok
```

产物：`mosaic_eval/r5_locus/{da,mcr,pooled}.tsv`、`cross_tabs.json`；`mosaic_eval/r5_dual/`。

---

## 2. 双口径总表（pooled）

| 臂 | n | scored | chain | mapper_rescue |
|---|---:|---:|---:|---:|
| forest | 800 | 0.451 | **0.266** | 0.220 |
| impc | 800 | 0.434 | **0.265** | 0.204 |
| B06 | 800 | 0.445 | 0.243 | 0.235 |
| lite | 800 | 0.429 | 0.238 | 0.214 |
| multistance | 800 | 0.450 | 0.226 | 0.245 |
| collapse3c | 800 | **0.461** | 0.211 | 0.266 |
| B07 | 800 | 0.440 | 0.213 | 0.255 |
| APHHM | 300 | 0.480 | 0.210 | 0.290 |
| e7 | 800 | 0.416 | 0.203 | 0.228 |
| aphhm_c_v1 | 400 | 0.355 | 0.113 | 0.260 |

**可读：** 在 chain 口径上 MOSAIC（forest/impc/lite）整体高于 APHHM-C 的窄池臂与 e7；collapse3c 的 scored 最高但 chain 中游——DA mapper_rescue 仍在拉大差距。全矩阵 `aphhm_c_v1` 的 chain 崩到 0.11，与 APHHM-C 试点报告一致。

---

## 3. 噪声门（同配置重复）

五对重复（各 n=400 dev）：

| 对 | champ 一致 | locus 一致 | 池 Jaccard |
|---|---:|---:|---:|
| multistance | 0.773 | 0.795 | 0.609 |
| collapse3c | 0.753 | 0.868 | 0.592 |
| lite | 0.760 | 0.923 | 0.752 |
| forest | 0.810 | 0.883 | 0.750 |
| impc | 0.760 | 0.893 | 0.734 |

**聚合噪声地板（locus 占比差低于此则不可分辨）：**

| generation_miss | identity_loss | prune_loss | decision_loss | ok |
|---:|---:|---:|---:|---:|
| 0.085 | 0.030 | 0.125 | 0.118 | 0.073 |

产物：`mosaic_eval/r5_stability.json`。

---

## 4. 跨族 locus 分布（DA / chain）

| 臂 | gen_miss | id_loss | prune | decision | interface | ok |
|---|---:|---:|---:|---:|---:|---:|
| collapse3c | **0.605** | 0.003 | 0.020 | 0.080 | 0.093 | 0.200 |
| multistance | **0.355** | 0.028 | **0.230** | 0.075 | 0.080 | 0.233 |
| lite | 0.590 | 0.008 | 0.000 | 0.073 | 0.073 | 0.258 |
| forest | 0.503 | 0.035 | 0.000 | 0.078 | 0.105 | **0.280** |
| impc | 0.510 | 0.023 | 0.000 | 0.090 | 0.085 | **0.293** |
| e7 | 0.498 | 0.000 | 0.120 | **0.180** | 0.000 | 0.203 |
| B06 | **0.138** | 0.000 | 0.000 | 0.180 | **0.395** | 0.288 |
| B07 | 0.338 | 0.000 | 0.000 | 0.000 | **0.423** | 0.240 |

MCR 上 interface 几乎消失（judge 与 chain 更对齐），generation_miss 仍是主桶；MOSAIC 的 decision_loss 约 0.11–0.17，与 APHHM-C 同量级。

**机制阅读（过噪声门之后）：**

1. **collapse3c 的主损是 generation_miss（0.60）**，不是决策——窄承诺池换来了高转化，但召回不够。与 APHHM-C 试点报告一致。
2. **multistance 把 generation_miss 压到 0.36**（相对 collapse3c 的 −0.25，远超地板 0.085），但 **prune_loss 升到 0.23**（锦标赛/宽池把金标留在池外决策集）——召回增益没有全部兑换成决策机会。
3. **MOSAIC 几乎没有 prune_loss**（frontier≈全池），主损仍是 generation_miss；forest/impc 的 ok 最高。
4. **B06/B07 的 interface_loss 极大（0.40/0.42）**——R4 的 mapper_rescue 叙事在参照臂上复现；新方法 interface 约 0.07–0.10，仍在但不是主因。
5. **e7 的 decision_loss（0.18）高于新方法（≈0.08）**——过地板；同簇终裁问题在新架构上被削弱。

---

## 5. 三条新机制轴

### 5.1 身份生命周期（预注册判据）

| 臂 | DA id_loss | MCR id_loss |
|---|---:|---:|
| collapse3c | **0.0025** | 0.0125 |
| multistance | 0.0275 | 0.025 |
| forest | 0.035 | 0.0175 |
| lite | 0.0075 | 0.000 |

**判据：**「若 APHHM-C 上 identity_loss <3% 且过不了噪声门，则不得写『全局身份唯一吃掉金标』。」collapse3c 的 0.25% 远低于 3% 与地板 3.0%；multistance 的 2.8% 贴着地板。**结论：全局身份唯一不是主损机制，不得写入。**

### 5.2 证据不对称（预注册判据）

在 decision_loss 病例上，`evidence_says_champ_worse_frac`（冠军 against 更多且 for 更少）为 0–8%。**证据跨度几乎不能预测谁赢。** 判据要求：若不能预测 decision_loss，则不得写「selector 违背证据」，只能写「证据不足以定序」——**本条成立，按此措辞。**

### 5.3 视图溯源与宽度残差

- multistance 的召回来自三取向并集（池召回 DA 0.618），但转化落在拟合线 `conv≈0.74−0.047·width` 之上仅 +0.06——与 APHHM-C 试点 §17 一致。
- MOSAIC 在同等宽度下残差为正（lite DA +0.11，forest +0.08），解释了其更高的 chain。

产物：`mosaic_eval/r5_mechanisms.json`。

---

## 6. 盲裁（银标）

210 例按新 locus 分层。银标（独立的词汇簇判定 + 结构重放）与规则 locus 的一致率 **0.943，κ=0.932**——远高于 R4 失败码的 κ≈0.14。原因：R5 locus 是结构量（池里有没有、短名单有没有），不是语言学话术码。

decision_loss 的冠军–金标簇：unrelated 30 / parent_subtype 11 / sibling 9 / **same_entity 0**。与 R4「同簇终裁占 80%」不同——新方法决策失败时，冠军往往已是另一家族，而不是近义换皮。

产物：`r5_adjudication/`（含 210 张卡与 `judgments/silver.jsonl`；人类裁决可覆盖银标）。

---

## 7. 反事实干预（因果）

只重跑最终 selector（`--reuse-from`）。与 R4 I4（e7 金标注入后转化率 **≈20.6%**）直接可比。

| 干预 | 臂 | DA chain | 基线→oracle | MCR chain |
|---|---|---:|:--|---:|
| **J1 裸注入** | collapse3c | **0.390** | 0.185→0.390（2-43, p≈0） | 0.265 |
| **J1 裸注入** | forest | **0.650** | 0.270→0.650（3-79, p≈0） | 0.340 |
| **J2 公平注入** | collapse3c | **0.870** | 0.210→0.870（0-66） | 0.490 |
| **J2 公平注入** | forest | **0.920** | 0.300→0.920（0-62） | 0.550 |
| J3 反并合+注入 | multistance | 0.445 | 0.240→0.445 | 0.280 |

**预注册判据：**「若 J1 与 R4 的 20.6% 无显著差异，则新架构决策瓶颈与 e7 同构。」**否决。** collapse3c J1=39%、forest J1=65%，显著高于 20.6%。含义：

1. **金标一旦进入决策集，新方法（尤其 forest）远比 e7 更能选中它。** 瓶颈从「同簇终裁话术」转向「生成阶段是否提出金标」。
2. **J2≃J1+证据** 在 DA 上再抬到 0.87/0.92——裸注入时「没证据可读」仍是一部分损失；给金标写诚实 span 后，selector 几乎能兑现。
3. **J3 的增益主要来自注入本身**（identity_loss 仅 ~3%），与 §5.1 一致：反并合不是杠杆。

产物：`mosaic_eval/r5_interventions.json`；运行器 `scripts/paper/run_r5_selector_oracle.py`。

---

## 8. 机制卡

按六桶 × 代表臂抽样 72 张，并排「谁提出金标 / 它的证据 / 谁赢了 / 赢家的证据」。见 [`r5_cards/index.md`](r5_cards/index.md)。

---

## 9. 可写 / 不可写

### 可写

1. R5 的机制级六桶 locus 在新方法上可结构重放，银标 κ≈0.93；比 R4 话术失败码可信。
2. **collapse3c 主损是 generation_miss；multistance 用取向多样性换召回，但引入 prune_loss。** 二者是召回–决策集宽度的权衡，不是同一缺陷的两种表现。
3. **MOSAIC（forest/impc）在 chain 上领先**，几乎无 prune，主损仍是 generation_miss；同宽度转化残差为正。
4. **全局身份唯一不是主损**（id_loss≪3%）。
5. **新方法的决策天花板高于 e7**：J1 转化 39–65% vs R4 I4 的 20.6%；J2 达 87–92%。金标在池内时，证据接地的 selector 能兑现。
6. B06/B07 的 interface_loss 仍是 DA 主伪影；比较臂序必须拆 scored/chain。
7. 运行间噪声地板已测：locus 占比差 < 地板不得作为跨臂结论。

### 不可写

1. 「全局身份唯一吃掉金标」——否决（§5.1）。
2. 「selector 违背自己的证据」——否决；应写「证据不足以定序」（§5.2）。
3. 「新架构决策瓶颈与 e7 同构」——否决（§7）。
4. 「multistance 的 prune_loss 高于 collapse3c 的 generation 优势」——prune 差 0.21 过地板，但净 chain 仅 +1–2pp，不得夸张为全面更优。
5. 任何不共用缓存、差值小于 §3 噪声地板的 locus/chain 细差。

---

## 10. 对后续算法的直接含义

| 若目标是… | 优先动… | 不要动… |
|---|---|---|
| 抬 chain | 生成召回（MOSAIC 多视图 / 承诺+覆盖取向），保持决策集宽度 ≲5 | 加并合/拆分决赛/确定性后处理 |
| 保留低成本 | collapse3c（3.3 calls）——接受 generation_miss | 为边际 chain 付 5–6 calls，除非过噪声门 |
| 兑现已召回金标 | 保证金标带诚实证据进入 selector（J2 方向） | 再加一次「孤立提名轮」（msplit 已否） |
| 写论文臂序 | 主报 chain；DA scored 仅作附录 | 用 scored 讲 DA 独占 |

---

## 11. 产物索引

| 产物 | 路径 |
|---|---|
| 统一读取层 | `analysis/backbone_v1/r5_lib.py` |
| locus | `r5_locus.py` → `mosaic_eval/r5_locus/` |
| 双口径 | `r5_dual.py` → `mosaic_eval/r5_dual/` |
| 机制轴 | `r5_mechanisms.py` → `mosaic_eval/r5_mechanisms.json` |
| 稳定性 | `r5_stability.py` → `mosaic_eval/r5_stability.json` |
| 盲裁 | `r5_adjudication_sample.py` → `r5_adjudication/` |
| 干预 | `scripts/paper/run_r5_selector_oracle.py`、`run_r5_oracle.sh`、`r5_summarize_interventions.py` → `mosaic_eval/r5_interventions.json` |
| 机制卡 | `r5_cards.py` → `r5_cards/` |
| 重复跑 | `aphhm_c_collapse3c_r2`、`mosaic_{lite,forest,impc}_r2` |

---

## 12. 与 R1–R4 / DEEP 的衔接

| 旧结论 | R5 更新 |
|---|---|
| 基线净救回以 S3/S4 同簇终裁为主 | 新方法 decision_loss 更低；失败时冠军多属 unrelated/父型，而非同簇近义 |
| 瓶颈是保真转化而非搜索广度（DEEP+R4） | **对新方法部分改写**：生成召回仍是第一桶；但一旦金标在决策集，保真转化已显著好于 e7 |
| APHHM 剪枝与 e7 终裁部分同构 | APHHM-C/MOSAIC 的 identity_loss 可忽略；prune 只在宽池锦标赛臂出现 |
| 规则失败码不可作主叙事（κ≈0.14） | 机制级结构 locus 可作主叙事（κ≈0.93） |
| 缺运行间误差棒 | 已补；地板见 §3 |
