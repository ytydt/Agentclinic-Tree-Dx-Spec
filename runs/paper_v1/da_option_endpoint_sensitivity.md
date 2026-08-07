# DA option 端点敏感性审计（并列判定占比）

- 生成时间: `2026-08-05T16:51:59.226964+00:00`
- 脚本: `scripts/paper/da_option_endpoint_sensitivity_audit.py`
- 机器可读: [`da_option_endpoint_sensitivity.json`](da_option_endpoint_sensitivity.json)
- 切片: DA `d2_seq100`，n=100，4 选项，随机基线 **0.250**

> **不入论文主表。** `strict@1` 与 `forced_choice` 为事后定义端点，未经预注册，进入论文前需先写入 `paper_ablation_plan.md` 并补配对显著性检验。

## 端点定义

| 端点 | 定义 |
|---|---|
| `option@1` | 官方 mapper 指标：gold 选项排名第 1（并列也算命中） |
| `strict@1` | 命中 **且** rank-1 集合只有 gold 一个选项 |
| `equivalent@1` | 命中 **且** gold 选项与叶的关系判为 `equivalent`（非 `subtype_of` 等跨粒度关系） |
| `forced_choice` | 并列随机打破的期望正确率；完全无匹配视为弃答，按 1/选项数 计 |

## 结果

| 臂 | option@1 | strict@1 | equivalent@1 | 并列救回 | forced-choice | 弃答 | 命中时并列宽度 |
|---|---:|---:|---:|---:|---:|---:|---:|
| M00 compat (live) | 0.700 | 0.210 | 0.310 | 0.490 | 0.407 | 5 | 2.08 |
| M00 pre-compat | 0.590 | 0.220 | 0.270 | 0.370 | 0.367 | 3 | 1.86 |
| AB01 fixed_icd | 0.510 | 0.170 | 0.260 | 0.340 | 0.339 | 12 | 1.82 |
| AB02 flat | 0.680 | 0.170 | 0.310 | 0.510 | 0.382 | 7 | 2.12 |
| AB03 random | 0.370 | 0.100 | 0.180 | 0.270 | 0.322 | 47 | 2.08 |
| AB21 contrastive | 0.670 | 0.190 | 0.290 | 0.480 | 0.386 | 3 | 2.05 |
| AB22 no-P5 | 0.670 | 0.180 | 0.370 | 0.490 | 0.376 | 4 | 2.06 |
| B02 matched-rerank | 0.560 | 0.020 | 0.060 | 0.540 | 0.267 | 24 | 2.58 |
| B02 compute-matched | 0.480 | 0.030 | 0.080 | 0.450 | 0.243 | 22 | 2.32 |
| B02 cm-sc10 | 0.470 | 0.020 | 0.060 | 0.450 | 0.244 | 24 | 2.33 |

## 读数

1. **并列救回是 DA option 端点的系统性性质，不是某个臂的伪影。** M00 与 AB02 的命中里都有约一半来自并列，命中时平均并列宽度均在 2.1 左右。
2. **AB02 与 M00 的差距对端点不敏感**：option@1 −0.02、strict@1 −0.04、forced-choice −0.025。换严格端点不能恢复「层级必要」的主张。
3. **B02 的命中几乎全是并列 credit**：strict@1 仅 0.02–0.03，forced-choice 贴近随机基线 0.250。本方法栈与平面基线的差距在严格端点下远大于 option@1 所显示的。
4. **反向代价**：AB03 的 47 次弃答在 option@1 下全记为错，在 forced-choice 下各得 0.25，其效应量从 −0.34 压到约 −0.085，接近 n=100 的功效阈值。严格端点不是无代价的替代，只能作敏感性分析。
5. **compat 中间件的增益全部是并列 credit**：pre-compat → compat 使 option@1 由 0.59 升到 0.70（+0.11），但 `strict@1` 由 0.22 微降到 0.21，命中时并列宽度由 1.86 升到 2.08。合并等价类确实会拓宽 rank-1 并列集；当被并的选项是真同义时该 credit 合理，是 `subtype_of` 跨粒度关系时则是粒度损失。**须与贡献二的读数一并复核。**
6. **关系类型分布**：M00 命中里 `subtype_of` 33 / `equivalent` 31；B02 则是 `subtype_of` 37–44 / `equivalent` 仅 6–8。平面基线几乎从不产出与 gold 同粒度的标签。

## 锚点溯源（M00 0.71 的出处）

| 数字 | 出处 | 性质 |
|---|---|---|
| **0.59 / 0.78** | `downstream_top2_w12_v1` + `pipeline_remaining76_v1` mapper | 原生 mapper，compat 路由前 |
| **0.71 / 0.78** | `at1_c1_v1/per_case_compat_parallel_all100.tsv` 的 `opt1`/`opt2` 列 | **rematch**：对上一行的 `option_maps` 施加 compat_parallel 合并后重算（`run_at1_calibration_smoke.rematch_option_metrics`），非原生跑 |
| **0.70 / 0.79** | `pilot24_compat_b12_live_v1` + `remain76_compat_b12_live_v1` mapper | 原生 compat+b12 live 跑 |

同一 TSV 里 `official_opt1` = 0.59 与 `opt1` = 0.71 并存，可确认 0.71 是重算值。

**影响**：C3/C2 各臂的 option@1 来自**原生 compat mapper 跑**，与之协议最接近的 M00 是 0.70（live），而现用锚点 0.71 是 rematch 值。两者仅差 1 例，不改变任何既有结论，但报数时应注明锚点与臂的打分路径不同源。

