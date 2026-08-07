# C2 计算档消融结果（不入论文主表）

- created_at: `2026-07-28T00:43:40.824392+00:00`
- updated_at: `2026-07-28T17:00:00+00:00`（R2b/R2c：撤回错误因子读数；补配对与等价界）
- tier: **C2**（复用冻结树 T，从 E/W live；非 confirmatory AB10b）
- backup: `/data2/wanghongyi/Agentclinic-Tree-Dx-Spec/backups/c2_preflight_20260728_041650`
- OX workers: `12`；DA workers: `12`
- DA scoring: **无 synonym_bind**
- 块4切片: **DA `d2_seq100` 代理**（计划 D1b-dev-freeze 未物化）
- AB16: **历史复用**；档案 `/data2/wanghongyi/Agentclinic-Tree-Dx-Spec/runs/paper_v1/ablations_c2_ab16_reused.json`
- AB28: **历史复用**；档案 `/data2/wanghongyi/Agentclinic-Tree-Dx-Spec/runs/paper_v1/ablations_c2_ab28_reused.json`
- **进度**: AB21+AB22 complete；块 3/4 配对与因子分解见下

## 锚点（只读）

- OX M00 closed_live_mac: F1=0.6508264462809917 P=0.6312625250501002 R=0.6716417910447762 Interp=0.3545183714001986
- DA compat 名义 option@1/@2: {'option_top1': 0.71, 'option_top2': 0.78}

## 块3 OX（预算 / 写回 / cap）

| ID | 设置 | micro | live_trees | exits |
|---|---|---|---|---|
| AB13 | L1=4 wb=False cap=6 | F1=0.5758513931888545 P=0.558 R=0.5948827292110874 Interp=0.3516483516483517 | 0 | ann=0 llm=0 |
| AB14 | L1=6 wb=True cap=6 | F1=0.6576763485477178 P=0.6404040404040404 R=0.67590618336887 Interp=0.3464955577492596 | 100 | ann=0 llm=0 |
| AB16 **[reuse]** | L1=6 wb=False cap=6 | F1=0.5841073271413829 P=0.566 R=0.603411513859275 Interp=0.354978354978355 | 0 | ann=0 llm=0 |
| AB17 | L1=4 wb=True cap=1 | F1=0.6570247933884297 P=0.6372745490981964 R=0.6780383795309168 Interp=0.35735439289239884 | 100 | ann=0 llm=0 |
| AB19 | L1=4 wb=True cap=999 | F1=0.6487046632124353 P=0.6310483870967742 R=0.6673773987206824 Interp=0.3501006036217304 | 100 | ann=0 llm=0 |

## 块4 DA 选择器（代理切片）

| ID | 设置 | option@1 | option@2 | Δ@1 vs M00 | Δ@2 vs M00 | 状态 |
|---|---|---:|---:|---:|---:|---|
| AB21 | salience≈p5_contrastive_direct | 0.67 | 0.72 | -0.04 | -0.06 | COMPLETE |
| AB22 | anti-anchor + no P5 compiler inject | 0.67 | 0.70 | -0.04 | -0.08 | COMPLETE |

## 块6 AB28 重核

- **reused**: `True`
- out: `/data2/wanghongyi/Agentclinic-Tree-Dx-Spec/analysis/l1_gold_recall_v1/smoke_typed_remap`
- R_compat @1/@2: `{'opt1': 0.72, 'opt2': 0.78, 'mrr': 0.7533333333333333}`
- inject_typed @1/@2: `{'opt1': 0.42, 'opt2': 0.69, 'mrr': 0.6283333333333335, 'coverage': 0.93, 'mean_extra_leaves': 16.12}`
- Δ@1: `-0.3`
- note: C2 AB28 maps to historical smoke_typed_remap all100 (full leaf inject + typed_llm remap). Plan cites @1 0.72→0.42; gate REJECT / claim_allowed=false. Not re-run in this C2 round.

## 预注册解读（**已更正，R2b/R2c**）

> ⚠️ **撤回**：原稿「`M00−AB13 ≈ AB14−AB13` ⇒ prefer budget-calibration reading over writeback」是**因子混淆**。AB14 同时改预算与写回；干净的预算单因子臂是 AB16。

机器可读：[`ablations_block3_state_factorial.json`](ablations_block3_state_factorial.json)、[`ablations_block4_selector_exclusion.json`](ablations_block4_selector_exclusion.json)；§7 Holm：[`confirmatory_holm_five.json`](confirmatory_holm_five.json)。

### 块 3｜干净 2×2（预算 × 写回，cap=6）

| | 冷（不写回） | 热（写回） |
|---|---:|---:|
| 锁定 L1=4 | AB13 **0.576** | M00 **0.651** |
| 默认 L1=6 | AB16 **0.584** | AB14 **0.658** |

- 写回效应：锁定 +0.075；默认 +0.074
- 预算效应：冷 +0.008；热 +0.007
- 交互：−0.001（无）
- **配对 micro-F1 bootstrap（M00 vs AB13，confirmatory 主端点）**：Δ = +0.075，95% CI **[0.036, 0.113]**，双侧 add-one p = **4.0×10⁻⁴**（5000 次病例重抽样）
- 辅证配对 case-F1：mean Δ = +0.073，42/14，p = 2.3×10⁻⁴，bootstrap 95% CI [0.035, 0.112]
- **预注册否证**：「增益可被预算单独解释」**未触发**；「AB13 与主方法无差」**未触发**
- **AB19（cap=999）** Δ micro-F1 = +0.002（不损害）⇒ **预注册否证条款触发：cap 从机制表述删除，只保留写回**
- **AB17（cap=1，单冠军）** Δ = −0.006（反而略好）⇒ 与手稿「Against the single champion」实证立场冲突；两侧同时 null ⇒ **cap 在 OX 上双向不承重**
- AB15（同热树只换解码）：closed 0.651 / post_n_mcr 0.610 / posterior 0.593；closed vs posterior 配对 case-F1 mean Δ +0.056（32/9，p=4×10⁻⁴）

### 块 4｜选择器排除界

| 臂 | @1 | Δ vs M00 | b/c | p | \|Δ\|<0.10 | TOST ±5pp |
|---|---:|---:|---|---:|---|---|
| AB21 | 0.67 | −0.04 | 11/7 | 0.48 | 是 | **否**（CI 仍含 ~12pp） |
| AB22 | 0.67 | −0.04 | 9/5 | 0.42 | 是 | **否** |

- **预注册排除成立**（无一致的可解释下降）⇒「主结果不由选择器解释」
- 正式 TOST 等价**未达成**（n=100 下不一致率使 CI 偏宽）⇒ 报有界方向性 null，不报可互换
- 与块 1 交叉：**选择器策略不承重，但选择器的输入结构（病例自适应轴）承重**

### 块 6｜AB28

- 复现有害注入：Δ@1 = −0.300（0.72→0.42）；**真配对** b/c = **39/9**（ties 52），精确符号双侧 p = **1.5×10⁻⁵**（源：`analysis/l1_gold_recall_v1/smoke_typed_remap/metrics_typed_all100.tsv` 的 `compat_opt1` vs `typed_opt1`）
- §8 重核义务仍未清（历史复用；judge 合同未按冻结协议重跑）

### §7 五对照 Holm（真配对修订后）

| 对照 | 端点 | 效应 | p_raw | p_Holm | 存活 |
|---|---|---:|---:|---:|---|
| C1 AB03 | DA @1 满样本 | +0.34 | ~0 | ~0 | 是 |
| C2 AB10b | MCR any-hit 置换 | +0.097 | 0.015 | 0.030 | 是 |
| C3 AB13 | OX **micro-F1 配对 bootstrap** | +0.075 | **4.0×10⁻⁴** | **1.2×10⁻³** | 是 |
| C4 AB28 | DA @1 **真配对 39/9** | +0.30 | **1.5×10⁻⁵** | **6.0×10⁻⁵** | 是 |
| C5 AB21 | DA @1 | +0.04 | 0.48 | 0.48 | 否（排除对照的预期） |

端点异质性按注册表原样执行。C3 不再用 case-F1 符号检验作 Holm 输入（该检验保留为辅证，同向）；C4 不再用聚合假配对（b=30,c=0）。C5 不存活 = 排除对照的目标结果。

## 路径索引

- `/data2/wanghongyi/Agentclinic-Tree-Dx-Spec/runs/paper_v1/ablations_c2_ox_raw.json`
- `/data2/wanghongyi/Agentclinic-Tree-Dx-Spec/runs/paper_v1/ablations_c2_da_raw.json`
- `/data2/wanghongyi/Agentclinic-Tree-Dx-Spec/runs/paper_v1/ablations_c2_results.json`
- `/data2/wanghongyi/Agentclinic-Tree-Dx-Spec/runs/paper_v1/ablations_block3_state_factorial.json`
- `/data2/wanghongyi/Agentclinic-Tree-Dx-Spec/runs/paper_v1/ablations_block4_selector_exclusion.json`
- `/data2/wanghongyi/Agentclinic-Tree-Dx-Spec/runs/paper_v1/confirmatory_holm_five.json`

> 本文件仅供内部消融归档；勿写入论文主结果表。
