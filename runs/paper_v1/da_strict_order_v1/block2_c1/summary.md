# 块 2｜DA C1 臂严格@1 重核

> **本表「Δ vs M00 live」列口径混用，勿引用。** 消融臂是 rematch、M00 是 live，
> 同一 `compat_parallel` 算子在两条打分路径间本身就差 +0.03（6/3, p=0.51）。
> 同口径（双方 rematch）Δ 与配对检验见
> [`../../da_strict_order_endpoint_audit.md`](../../da_strict_order_endpoint_audit.md)：
> 最大 |Δ| = 0.04，无一显著，AB08/AB20 符号翻转，AB09 逐例恒等。
> 该文档同时判定 **LLM 破并列端点不得入论文**：决定性理由是基线臂 payload 退化
> （空 vignette + 无文本选项字母），辅助理由是破并列器相对 `1/宽度` 无可测增益。
> 初版「不如随机」的措辞已于 2026-07-29 撤回，见该文档 2.3。

- 生成时间: `2026-07-28T18:51:02.153523+00:00`
- 输出: `/data2/wanghongyi/Agentclinic-Tree-Dx-Spec/runs/paper_v1/da_strict_order_v1/block2_c1`
- 协议: 与 `da_strict_order_v1` 相同（并列 → LLM 全序；matched ≺ unmatched）
- **M00 锚点: native compat+b12 live 严格@1 = 0.390**（与原生 mapper 臂统一；rematch 版 0.360 仅作脚注）
- 消融臂输入: pre-compat joint + `at1_c1_v1` rematch 缓存（与 C1 表同源）

| ID | smoke arm | 旧 option@1 | 严格@1 | 严格@2 | Δ vs 旧 | Δ vs M00 live | 原并列 | LLM破并列 |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| AB05 | `ours` | 0.59 | 0.340 | 0.570 | -0.250 | -0.050 | 98 | 98 |
| AB07 | `merge` | 0.68 | 0.340 | 0.560 | -0.340 | -0.050 | 99 | 99 |
| AB08 | `both_l1fallback` | 0.65 | 0.380 | 0.560 | -0.270 | -0.010 | 98 | 98 |
| AB09 | `compat_serial_safe` | 0.71 | 0.360 | 0.590 | -0.350 | -0.030 | 99 | 99 |
| M00 | `compat_parallel` **live** | 0.71 | **0.390** | 0.610 | -0.320 | — | 99 | 99 |
| AB10 | `compat_random_route` | 0.69 | 0.340 | 0.560 | -0.350 | -0.050 | 99 | 99 |
| AB11 | `concept_id_merge` | 0.57 | 0.320 | 0.550 | -0.250 | -0.070 | 98 | 98 |
| AB20 | `compat_parallel_no_l1_prior` | 0.70 | 0.370 | 0.590 | -0.330 | -0.020 | 99 | 99 |

> 脚注：同协议下 rematch `compat_parallel` 严格@1 = 0.360（`block2_c1/arms/M00`）。块 2 内 Δ 一律相对 **live 0.390**。

## 跳过

- **AB04 / AB06**：仅 MCR 有建树臂，无 DA option 投影可核。
- **AB10b / AB10c**：DA option rematch 对合并语义构造性不敏感（R1b）；confirmatory 端点是 MCR any-hit@5 / open-MRR，不在本脚本范围。

## 读数注意

- **不入论文主表**（事后严格端点）。
- 旧 C1 表里 AB05 +0.12 等大 Δ 在严格口径（相对 live M00）下全部 ≤0.05。
- 消融臂为 rematch、M00 为 live：协议上 live 与 C3/基线严格表一致；若需与 rematch 表逐位同构，见脚注 0.360。

