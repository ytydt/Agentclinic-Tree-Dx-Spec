# C3 P0 消融结果（不入论文主表）

- 生成时间: `2026-07-28T13:15:52.566929+00:00`
- 备份: `/data2/wanghongyi/Agentclinic-Tree-Dx-Spec/backups/c3_preflight_20260728_110336`
- **切片代理**: 块1 = DA `d2_seq100`（D1b 未物化）；块2 = MCR `mcr_val_seq100`
- **DA mapper**: 无 `--synonym-bind-repair`
- **P0 C3 帽突破**: 计划「P0 C3≤4」，本轮跑满 AB01/02/03/04/06（AB04 无法降档复用历史 0.59）
- **口径纠正**: 计划「AB04≈0.59」实为 **AB05**（去重开 + 路由关）

## 锚点（只读）

- DA M00 option @1/@2 = **0.71/0.78**（无 bind）
- MCR M00 开放 Acc = **0.50**（`compat_synonym_v1`，Prompt7 judge）
- MCR M00 downstream @1 = **0.460**（另一口径，勿与上行混比）

## 块 1｜层级轴（DA d2_seq100 代理）

| 臂 | L1 轴 | option@1 | option@2 | Δ@1 vs M00 | Δ@2 vs M00 |
|---|---|---:|---:|---:|---:|
| AB01 | fixed_icd | 0.510 | 0.600 | -0.200 | -0.180 |
| AB02 | flat | 0.680 | 0.680 | -0.030 | -0.100 |
| AB03 | random | 0.370 | 0.420 | -0.340 | -0.360 |

### 否证读数（贡献一）

- AB03 满样本 Δ@1 = `−0.340`（配对 40/6）→ 默认口径下保留「病例自适应轴」主张
- ⚠️ **AB02 已降级为探索性，不入论文**，理由见下节可比性审计；其 Δ 不得用于支持或否证贡献一
- ⚠️ AB03 的 Δ 混入 45/100 空排序；空排序是**设计必然后果**（见级联审计），不是技术 bug。满样本为默认叙述口径；条件化为进阶严格条件

### 轴级联审计（块 1，R2a）

机器可读：[`ablations_block1_axis_cascade.json`](ablations_block1_axis_cascade.json)；脚本 `scripts/paper/audit_block1_axis_cascade.py`。

**过程指标（同一选择器代码）**

| 臂 | 平均 n_selected | n_selected=0 | 空排序 | 主 stop_reason |
|---|---:|---:|---:|---|
| M00 | 4.94 | 17 | 1 | selector_abstained 68 / pool_exhausted 30 |
| AB01 | 0.65 | 89 | 11 | selector_abstained 97 |
| AB03 | 0.13 | 97 | 45 | selector_abstained 100 |

L1 证据选择器是候选相对的对比式选证：轴不由病例决定 ⇒ 家族间无可判别对比 ⇒ 立即弃选 ⇒ 级联到空排序。故空排序率是轴质量的过程端点，不是实现故障。

**双口径 Δ@1（M00 − arm）**

| 臂 | 满样本 Δ | b/c | p | 非空子集 n | 条件 Δ | b/c | p | 空子集对满样本 Δ 的份额 |
|---|---:|---|---:|---:|---:|---|---:|---:|
| AB01 | +0.200 | 25/5 | <10⁻³ | 89 | **+0.135** | **17/5** | **0.017** | +0.080 |
| AB03 | +0.340 | 40/6 | <10⁻⁶ | 55 | +0.018 | 7/6 | ≈1 | **+0.330** |

- **默认口径（满样本）**：AB03 差异显著 ⇒ 贡献一 confirmatory 未触发否证；效应经选择器级联中介，本设计不可分离「轴质量」与「选择器输入结构」
- **进阶口径（非空）**：AB03 塌成噪声；**AB01 仍存活**（候选更多——30.1 vs 17.8 叶——仍更差），是条件化下唯一干净的准确率残差
- **切片代理**：§6 登记主跑为 dev-freeze；本轮为 DA 复制切片

### 可比性审计（块 1）

机器可读：[`ablations_c3_block1_comparability.json`](ablations_c3_block1_comparability.json)；脚本 `scripts/paper/c3_block1_comparability_audit.py`。

| 臂 | 平均 L1 数 | 平均 L2 叶数 | 平均排序深度 | 深度=1 占比 | 空排序 | structural_reach | champion_recall |
|---|---:|---:|---:|---:|---:|---:|---:|
| M00 | 4.63 | 17.8 | 4.56 | 0.00 | 1 | 0.79 | 0.55 |
| AB01 | 6.00 | 30.1 | 1.68 | 0.43 | 11 | 0.80 | 0.59 |
| AB02 | 1.00 | 4.98 | 1.00 | 1.00 | 0 | 0.66 | 0.39 |
| AB03 | 4.63 | 24.4 | 1.01 | 0.26 | 45 | 0.73 | 0.49 |

**AB02 三条失效原因（降级依据）**

1. **候选预算不变式被破坏。** 臂定义要求「保留同一召回池与总预算」，实测叶总量 4.98 vs M00 17.8（28%）。per-parent 生成器每个父节点约只 emit 5–6 个子叶，**叶总量 ∝ L1 家族数**；`--l2-candidate-max-per-live-family` / `candidate_budget` 抬到 36 只放大喂给 `L2RecallCreator` 的召回候选池，不放大其 emit 的子叶数。
2. **排序深度塌成 1（100/100）。** joint 每个父节点取 1 个 champion，单父 `FLAT` → 单 champion → arbiter 只排一个叶。因此 `option@2 ≡ option@1 = 0.680` 是构造性恒等，`Δ@2 = -0.100` 反映的是排序被截断而非层级效应。
3. **算力与覆盖未匹配。** 平均每例 172s（AB01 424s / AB03 380s）；`structural_reach` 0.66 vs M00 0.79。在池只有 28%、reach 低 13 个点、深度只有 1 的条件下仍得 0.68，更可能说明 DA 选择题 option 端点对这些差异不敏感（mapper 会把单叶投影到选项），不能读作「层级无用」。

**当前块 1 能支撑与不能支撑的**

- 支撑：**轴的组织质量 / 病例自适应性重要**（AB01 −0.20、AB03 −0.34，且 AB01 叶数反而多于 M00 仍更差）
- 不支撑：**「必须存在 L1 分桶」**——该主张由基线 B02 承担；AB02 这一跑不能作为任一方向的证据
- 预注册否证条件（`paper_ablation_plan.md` 块 1）只绑定 AB03，AB03 差异显著 ⇒ 贡献一不因本轮撤下

**若日后要恢复 AB02 为可用证据，需同时满足**：单父下多轮生成使叶总量 ≈18、flat 下取 top-k champions（k ≈ 4.6）让 arbiter 有可排序集合、并把 `structural_reach` 与算力一并对齐后报告。

### 端点敏感性（并列判定）

见 [`da_option_endpoint_sensitivity.md`](da_option_endpoint_sensitivity.md)。要点：AB02 的 0.68 里 0.51 来自 rank-1 并列 credit，但 M00 的 0.70 里同样有 0.49 —— 并列救回是 DA option 端点的系统性性质。AB02 与 M00 的差距对端点不敏感（strict@1 −0.04、forced-choice −0.025），**换严格端点也不能恢复「层级必要」的主张**，与上文降级判断一致。同一审计另记录了 M00 锚点 0.71 实为 rematch 值（原生 compat live 跑为 0.70）。

### 禁止平局 mapper 全量重评

见 [`da_strict_order_v1/summary.md`](da_strict_order_v1/summary.md)。在现有投影上对并列例调用 `L2OptionStrictTotalOrder`，强制唯一全序，并施加 matched≺unmatched。M00 论文版（0.71 rematch 源）严格@1=**0.36**；AB01/02/03=0.32/0.35/0.19；B02 各档≈0.14–0.16。**不入论文主表**（事后端点）。

## 块 2｜执行位点（MCR seq100）

两列是**两个不同口径**，各自对各自的 M00 锚做 Δ，禁止交叉相减。

| 臂 | 建树语义去重 | 路由 | 开放 Acc | Δ vs M00(开放) | downstream@1 | Δ vs M00(downstream) |
|---|---|---|---:|---:|---:|---:|
| M00 | 开 | 开 | 0.500 | — | 0.460 | — |
| AB04 | 关 | 关 | 0.420 | -0.080 | 0.390 | -0.070 |
| AB06 | 关 | 开 | 0.500 | 0.000 | 0.470 | 0.010 |

### 位点读数

- AB04 vs M00：同时关掉建树去重与路由 → 联合损失上界
- AB06 vs M00：仅关建树去重、保留路由 → 建树去重边际
- AB04 vs AB06：路由在「无建树去重」树上的边际
- **完整 2×2（含 AB05）＋ any-hit@5 / open-MRR ＋ 配对 McNemar ＋ Holm**：见 `ablations_c1_results.md` §2.10；机器可读 `ablations_block2_site_rank_metrics.json`。本表仅保留 Acc@1 口径。
- 主口径：MCR 开放 Acc / any-hit@k / open-MRR（对齐 R1b/R1c）；闭集 rematch 不敏感时注明
- ⚠️ **口径纪律**：`downstream@1` 与开放 Acc 是两套判分，M00 分别为 0.460 与 0.500。历史版本曾把臂的 downstream@1 与开放 Acc 的 M00 锚相减（得 AB04 −0.11 / AB06 −0.03），该数已作废。

## 产物路径

- DA: `logs/diagnosisarena_d2_m01_v1/c3_ab0{1,2,3}_v1/`
- MCR: `logs/medcasereasoning_mcr_val_seq100_v1/c3_ab0{4,6}_v1/`
- 共享无去重树: `logs/medcasereasoning_mcr_val_seq100_v1/c3_shared_no_dedupe_v1/`
- JSON: `/data2/wanghongyi/Agentclinic-Tree-Dx-Spec/runs/paper_v1/ablations_c3_results.json`
- 块 1 轴级联: `runs/paper_v1/ablations_block1_axis_cascade.json`；脚本 `scripts/paper/audit_block1_axis_cascade.py`
- 可比性审计: `runs/paper_v1/ablations_c3_block1_comparability.json`

> 本文仅供消融工作区；**不得**写入论文主表。
