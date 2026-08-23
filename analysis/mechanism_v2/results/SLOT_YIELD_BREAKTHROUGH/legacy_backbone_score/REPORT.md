# CoreLift × Forest 旧链对照（含 Llama 选择器）

口径与 `MOSAIC_EXPAND_REPORT.md` / `aphhm_c_holdout.json` 主表相同：

- DA task = llama-3.3-70b `typed_llm_disagreement_rag` option@1
- MCR task = Gemini 2.5 Flash 官方 Prompt-7 `diagnostic_hit`
- concept = `dc.match(champion, r4_facts gold)`
- ITA：选择器失败计 0；分母固定 400

两套 CoreLift 预测的差别**只有选择器**。视图与 Gemini 类型化准入 / 补全冻结复用。

## 1. 发表表参照（DA400 / MCR400）

| 臂 | DA task | DA concept | MCR task | MCR concept |
|---|---:|---:|---:|---:|
| Forest | 0.6375 | 0.2800 | 0.2650 | 0.2525 |
| IMPC | 0.6250 | 0.2925 | 0.2425 | 0.2375 |
| Collapse3c | 0.6300 | 0.2000 | 0.2925 | 0.2225 |
| Lite | 0.6025 | 0.2575 | 0.2550 | 0.2175 |

## 2. CoreLift · DeepSeek 选择器（服务率 0.97–0.995）

| 臂 | DA ITA | DA among-served | MCR ITA | DA concept | MCR concept | vs Forest DA McNemar p |
|---|---:|---:|---:|---:|---:|---:|
| A0_control | 0.5950 | 0.6134 | 0.2825 | 0.2600 | 0.2350 | 0.068 |
| A1_views | 0.6150 | 0.6196 | 0.2975 | 0.2700 | 0.2550 | — |
| A2_views_typed | 0.6150 | 0.6340 | 0.2850 | 0.2600 | 0.2475 | — |
| A3_full | 0.6325 | 0.6357 | 0.2875 | 0.2575 | 0.2525 | 0.904 |
| B1_corelift | **0.6400** | 0.6448 | 0.2775 | 0.1875 | 0.2225 | **1.000**（Δ +0.25pp） |

B1 与 Forest 的 DA task 在 400 例配对上不可区分（40 vs 39 discordant）。MCR task +1.25pp，p=0.57。B1 的 DA **concept** 显著低于 Forest（−9.25pp，p&lt;10⁻⁴）：旧链 option@1 被补全抬到 Forest 水位，概念命中没有跟上。

A0（单视图 + Lite 比较器）DA ITA 0.595，贴近发表表 Lite 0.6025，说明这条旧链确实接到了同一估计量。

## 3. CoreLift · Llama 选择器（服务率未过 0.95 门）

主因是选择器校验 `decisive item is not a verbatim vignette span`。未放宽契约。

| 臂 | 服务率 DA / MCR | DA ITA | DA among-served | MCR ITA |
|---|---:|---:|---:|---:|
| A0_control | 0.8225 / 0.8200 | 0.5175 | 0.6292 | 0.1900 |
| A1_views | 0.8125 / 0.8025 | 0.4975 | 0.6123 | 0.1875 |
| A2_views_typed | 0.8400 / 0.8225 | 0.5350 | 0.6369 | 0.1800 |
| A3_full | 0.8800 / 0.8675 | 0.5400 | 0.6136 | 0.1850 |
| B1_corelift | 0.8800 / 0.8950 | 0.5325 | 0.6051 | 0.1875 |

Llama ITA 全面低于 Forest（B1 DA Δ −10.5pp，p&lt;10⁻³），**不能**读成算法更差。同口径 among-served DA 约 0.61–0.64，与 DeepSeek 选择器几乎同带。缺口来自未服务例被 ITA 记 0。

## 4. 并发（本轮调整）

串行 mapper 已停。后续默认：

- 依赖 RAG 的任务（DA `typed_llm_disagreement_rag`）：**25**
- 无 RAG 评分（MCR Prompt-7、CoreLift 正规链 task / reviewer）：**50**

已完成切片跳过；仅重跑 B1 `diagnosisarena_heldout200b`（DeepSeek cache 266 键、Llama 76 键后续打满）。产物：`legacy_leaderboard.json`。
