# RareArena ra_rdc_seq100_v1 主方法 + 基线汇总

生成时间：2026-07-29（LLM judge；**本方法 ddx_k=5 已对齐 MCR**；基线 list_k=2 与 MCR 一致）

## 1. 实验设定

| 项 | 值 |
|---|---|
| 子集 | `data/benchmarks/rarearena/subsets/ra_rdc_seq100_v1`（100 例） |
| 本方法管线 | MCR transfer：compat + synonym_bind；`l1-calib=off` |
| 本方法评测 | `--ddx-source compat` · **`--ddx-k 5`** · LLM · skip RR |
| 基线评测 | `list_k=2` · LLM（与 MCR 基线表同） |
| 裁判 | Gemini 2.5 Flash · `gnn-llm` + `clashon` · workers=50 |
| 骨干 | `meta-llama/llama-3.3-70b-instruct` |
| 扫描 | selected=100 / scanned=104；排除 `{'kb_coverage:none': 3}` |
| 管线墙钟 | 7853s；vp:OK,trees:OK,p5:OK,annotate:OK,mapper:OK |

### 1.1 口径对齐说明

- 建树/标注：与 MCR `compat_synonym_v1` 同 harness（非 DA b12 live）。
- 本方法 open Acc：与 MCR 主表同为 `compat` + **ddx_k=5**（已从误用的 k=2 更正；旧 k=2 结果作废）。
- 基线仍 `list_k=2`，与 MCR 基线表相同（树 k=5 / 基线 k=2 的不对称是 MCR 既有设定）。
- Acc 为 top-1 `pred_diagnosis` 命中，不是 any-hit@k。

## 2. 主结果（LLM Acc 降序）

| 排名 | 臂 | 类别 | n | err | Acc (LLM) | Hits | k |
|---:|---|---|---:|---:|---:|---:|---:|
| — | **Ours**（compat B0） | 本方法（树） | 100 | 0 | **0.47** | 47 | 5 |
| 1 | `B04-dual-inf` | API pure | 100 | 0 | 0.47 | 47 | 2 |
| 2 | `B00-direct-cot` | API pure | 100 | 0 | 0.45 | 45 | 2 |
| 3 | `B06-mac-single-vendor` | API pure | 100 | 0 | 0.45 | 45 | 2 |
| 4 | `B12-sc-cot-5` | API pure | 100 | 0 | 0.43 | 43 | 2 |
| 5 | `B07-meddxagent-complete` | API+shared RAG | 100 | 0 | 0.41 | 41 | 2 |
| 6 | `B05-mdagents` | API pure | 100 | 0 | 0.40 | 40 | 2 |
| 7 | `B17-imedrag` | API+shared RAG | 100 | 0 | 0.38 | 38 | 2 |
| 8 | `B01-cot-rag` | API+shared RAG | 100 | 0 | 0.37 | 37 | 2 |
| 9 | `B03-flat-beam` | API+shared RAG | 100 | 0 | 0.36 | 36 | 2 |
| 10 | `B11b-cod-prompt-shared-kb` | API+shared RAG | 100 | 0 | 0.36 | 36 | 2 |
| 11 | `B13-self-refine-1` | API pure | 100 | 0 | 0.35 | 35 | 2 |
| 12 | `B02-flat-matched-rerank` | API+shared RAG | 100 | 0 | 0.34 | 34 | 2 |
| 13 | `B16-medrag-kg` | API+shared RAG | 100 | 0 | 0.33 | 33 | 2 |
| 14 | `B15-medprompt-style` | API+shared RAG | 100 | 0 | 0.29 | 29 | 2 |

## 3. 分组

- Pure 均值 Acc=0.425（n=6）
- RAG 均值 Acc=0.355（n=8）
- 最强基线：`B04-dual-inf` Acc=0.47；Ours−best = +0.00

## 4. 观察

1. **Ours@k5 LLM Acc=0.47**，最强基线 `B04-dual-inf`=0.47（Δ=+0.00）。
2. 相对误用的 k=2 结果（0.45），k=5 重投影后 Acc=0.47（judge 非确定性也可能贡献小幅波动）。
3. 相对 MCR（Ours 0.50 vs B07 0.24），RareArena 优势收窄。

## 4.1 预算重校准（F4 live vs F6）

离线 Acc 网格平坦后曾试锁 OX 同款 F4（L1=4/local=4/between=2/cand=6）并做 live 重标：

| 设定 | LLM Acc | Hits |
|------|--------:|-----:|
| **F6 主跑（正式）** | **0.47** | 47 |
| F4 live reann | 0.42 | 42 |

**结论：保留 F6**；F4 侧跑不覆盖主表。详见 `analysis/transfer_metrics_v1/ra_budget_recalib.md`。

## 5. 路径

| 项 | 路径 |
|---|---|
| Ours LLM Acc (k=5) | `logs/.../compat_synonym_v1/annotate/official_eval_llm_compat/` |
| F4 live 侧跑 | `logs/.../compat_synonym_noemit_fopt_live_v1/annotate/official_eval_llm_compat/` |
| 投影 | `logs/.../annotate/eval_projection_compat/` |
| 基线 LLM | `runs/paper_v1/rarearena_ra_rdc_seq100_v1/<arm>/.../official_eval_llm/` |
| 重校准 | `analysis/transfer_metrics_v1/ra_budget_recalib.{md,json}` |
