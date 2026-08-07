# B02 vs 主方法 token 差距（事后估计）

Tokenizer：`tiktoken_cl100k_base`  ·  无正式 token ledger（I05 deferred）

## 方法边界

- **当前预算匹配是 call/结构代理**，不是 token；B02 matched 与 structural schedule 的 llm_calls 对齐（G5）。
- **M00 无 input 落盘**：仅对 `*llm_cache.json` 的输出 JSON 做 tiktoken；`llm_calls_proxy` = cache entry 数。
- **B02**：输出取自 `trace`；输入按 `call_module` 格式重建（system prompt + payload），`knowledge_chunks` 用 `snippet_chars` 代理。
- **总 token 投影**：`M00_total ≈ M00_out × (1 + B02_in/B02_out)`，仅作量级敏感性，非官方账本。

## 主结果（每例均值，n=100）

| 数据集 | M00 calls‡ | B02 matched calls | calls 比 | M00 out tok | B02 matched out tok | out 比 | B02 matched total tok† | M00 total 投影† | total 比† |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| diagnosisarena | 94.3 | 9.24 | **10.2×** | 24488 | 2618 | **9.4×** | 48895 | 457302 | **9.4×** |
| open_xddx | 68.6 | 8.98 | **7.6×** | 16774 | 3002 | **5.6×** | 40235 | 224813 | **5.6×** |
| medcasereasoning | 81.2 | 9.32 | **8.7×** | 18744 | 2584 | **7.3×** | 50684 | 367606 | **7.3×** |

‡ cache entry 代理；† B02 total = 重建 in+out；M00 total = 输出 × (1+B02 I/O 比)。

## 与 structural schedule 对照

| 数据集 | schedule mean llm_calls | B02 matched mean | Δ |
|---|---:|---:|---:|
| diagnosisarena | 9.24 | 9.24 | 0.00 |
| open_xddx | 8.98 | 8.98 | 0.00 |
| medcasereasoning | 9.32 | 9.32 | 0.00 |

## B02 native vs matched（参考）

| 数据集 | native total tok† | matched total tok† | matched/native |
|---|---:|---:|---:|
| diagnosisarena | 7285 | 48895 | 6.7× |
| open_xddx | 7600 | 40235 | 5.3× |
| medcasereasoning | 7320 | 50684 | 6.9× |

## 解读

1. **Call 匹配成功、真实算力未匹配**：B02 matched 与结构 schedule 的 llm_calls 完全对齐，但相对主方法实际 cache 调用约 **7–10× 更少**。
2. **输出 token**：主方法 completion 约 **5–9×** 于 B02 matched（可直接估的硬指标）。
3. **因此当前 G5「等预算」不能写成「等 token」**；若论文要严格 compute-matched，需补主方法 token/call ledger 后重配 B02。

JSON：[`b02_vs_m00_token_gap_v1.json`](b02_vs_m00_token_gap_v1.json)  ·  脚本：`scripts/paper/estimate_b02_m00_token_gap.py`

## 附录：少量病例精确输入重建校准

对每集 5 例，用 `served_access_ids` 从语料 `metadata.jsonl` 取回真实 KB 正文并重建每次 `call_module` 输入（详见 [`b02_input_rebuild_sample_v1.md`](b02_input_rebuild_sample_v1.md)）：

| 数据集 | n | precise/proxy | KB 占 payload |
|---|---:|---:|---:|
| DA | 5 | 1.69 | ~92% |
| OX | 5 | 1.38 | ~92% |
| MCR | 5 | 1.99 | ~94% |
| 总体 | 15 | **≈1.69** | **≈92%** |

含义：全量报告中的 B02 `input_tokens_est`（`snippet_chars` 代理）约低估 **1.4–2.0×**；校准后 B02 matched 总 token 更大，但相对主方法 cache 调用/输出量级差距（约 5–10×）方向不变。KB chunks 已计入，且因每次调用重发而占 payload 绝大部分。
