# B02 输入 token：少量病例精确重建校准

Tokenizer：`tiktoken_cl100k_base`  ·  每集抽样 **5** 例

## 做法

1. 从 trace 读取 `served_access_ids` / `queries` / 各步 LLM raw；
2. 在 `rag_index` / `cpg_index` 的 `metadata.jsonl` 中按 chunk id 取回正文，截断 `max_chunk_chars`；
3. 按 `call_module` 格式重建每次调用的 system+user（含真实 `knowledge_chunks` 对象列表）；
4. 与 `snippet_chars` 字符代理估计对比。

## 结果

| 数据集 | n | mean precise in | mean proxy in | precise/proxy | mean KB payload 占比 | chunk正文/logged snippet |
|---|---:|---:|---:|---:|---:|---:|
| diagnosisarena | 5 | 80955 | 47254 | **1.692** | 91.6% | 1.034 |
| open_xddx | 5 | 71993 | 50721 | **1.376** | 92.0% | 0.919 |
| medcasereasoning | 5 | 121808 | 60486 | **1.995** | 93.6% | 1.034 |

总体：n=15，mean precise/proxy=**1.688**，mean KB payload 占比=**92.4%**。

## 解读

- **上下文重发送**：已按每次 LLM 调用计入完整 vignette + chunks。
- **KB chunks**：已用真实正文计入；在 payload 中约占 **92%** 字符（JSON 含 title/access_id/text 等字段）。
- **precise/proxy ≈ 1.38–2.00（总均 1.69）**：`snippet_chars` 的 `"K"*n` 代理系统性低估——真实 `knowledge_chunks` 是对象列表，JSON 结构开销与 tiktoken 对结构化文本的计价都更高。
- 用该比值校准全量 B02 matched 输入后（每例均值）：DA ≈78k、OX ≈51k、MCR ≈96k input tokens；总 token（+out）约 81k / 54k / 99k。相对主方法输出/调用量级差距方向不变。

复现：

```bash
PYTHONPATH=src:scripts:scripts/paper \
  python3 scripts/paper/rebuild_b02_input_tokens_sample.py --per-dataset 5
```

JSON：[`b02_input_rebuild_sample_v1.json`](b02_input_rebuild_sample_v1.json)
