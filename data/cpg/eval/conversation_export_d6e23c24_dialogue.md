# 对话导出：RAG / snippet / 闭包 / 召回（transcript L3370+）

| 字段 | 值 |
|---|---|
| conversation_id | `d6e23c24-82b3-4786-a36b-03356b21f410` |
| transcript 起始行 | **3370** |
| 导出时间 | 2026-06-28T01:50:30+00:00 |
| 轮次数 | **16**（L3370+；9–11 手动补回，12–14 transcript/L3435+，15–16 续论） |
| 源 JSON | `data/cpg/eval/conversation_export_d6e23c24_full.json` |

> 本文档由 `conversation_export_d6e23c24_full.json` 的 `messages_chronological` 整理而成，保留 assistant 完整 Markdown 正文。
> **第 9–11 轮**因 JSON/transcript 丢失，于 2026-06-28 自会话正文 **手动补回**（非脚本导出）。
> 原始 transcript 中 tool 中间步骤含 `[REDACTED]` 脱敏，已省略。

---

## 第 1 轮（transcript L3370）

### 用户

整理成 ≤24 条短摘要的具体做法是如何

### 助手

**「≤24 条短摘要」** 指：大模型 **不读整库 chunk**，只读 `_retrieve_snippets()` 产出的 **最多 24 条** 格式化 prose。实现如下。

## 流程概览

```text
4–5 条 query
  → 每条 TF-IDF top_k=30
  → expand_ddx_siblings（同篇闭包，grounding 路径始终开）
  → snippet_on_topic 门控
  → 按 title+content 前段去重
  → 格式化为 "[标题] 正文前400字"
  → 合并后硬截断 out[:24]
  → 喂 recall_llm / build_branch_knowledge_llm
```

Spotter 仍只读 **检索 top-30**（grounding 模式下闭包块 **不进** 40 槽候选池）；闭包信息经上述 24 条摘要间接给 LLM。

## 逐步说明

**1. 构造 query（约 4–5 条）**

- `"differential diagnosis of {综合征}"`
- `"causes and etiology of {综合征}"`
- 若有口语别名：再加 `"approach to {colloquial}"`
- 若有病例 context：再加 `"differential diagnosis of … clinical features: {context 前300字}"`

**2. 检索 + 闭包**

每条 query 调用 `search(top_k=30)`，再 `expand_ddx_siblings(hits)` 拉同 `source_id` 的 sibling 块。闭包后 hit 数可远大于 30（实验索引上常见 8→213），但 **尚未截到 24**。

**3. 门控**

`snippet_on_topic()` 按 `chunk_type` / `entry_type` / `syndrome_anchor` 等过滤离题块（NICE recommendation、无关 PMC 散文等）。

**4. 去重**

签名 `title[:60] + "|" + content[:40]`；重复块只保留一条。

**5. 格式化为「短摘要」**

每条变成一行字符串：

```text
[{title 前70字符}] {content 前400字符}
```

对应代码：

```651:652:src/agentclinic_tree_dx/knowledge/guideline_branch_source.py
                out.append(f"[{title[:70]}] {content[:400]}")
        return out[:24]
```

**6. 硬上限 24 条**

所有 query 的命中 **按 query 顺序、块内检索顺序** 依次 append；满 24 即停（`out[:24]`）。**无 MMR/重排**——MMR 只用于 Spotter 路径的 `_gather_spot_hits`，不用于 LLM 摘要。

理论字符上界约 **24 × 400 ≈ 9600**（再加标题前缀），报告中的 ~9.6k 即由此而来。

## 谁消费这 24 条

| 消费者 | 用途 |
|---|---|
| `recall_llm()` | GARMLE-G②：LLM 只许列出 **摘要里出现过的** 病名，与 Spotter 合并 |
| `build_branch_knowledge_llm()` | 方案 A：LLM 定 MECE 域 + mandatory |

Prompt 里字段名为 `reference_excerpts`，即这 ≤24 条字符串列表。

## 与 Spotter 的分工（grounding 模式）

```text
检索 top-30 块     → Spotter 做 n-gram 匹配 → max_candidates=40
同篇 sibling 块    → 只进 _retrieve_snippets → ≤24 条摘要 → LLM 有依据补抽
```

因此：**不是**把 200+ 闭包块都灌进 Spotter；扩展块以 **截断 prose 摘要** 形式给 LLM，避免 C4 候选池拥挤（§6.6）。

## 已知边界

- 长 DDx 枚举 **400 字后被截断**，列表后半可能进不了 LLM 上下文（§6.24）。
- 24 条按 **检索顺序** 截取，不保证覆盖所有 sibling；靠闭包扩大候选池、靠 LLM 从已入选摘要里抽实体。
- 增大 24 或 400 **单独调参尚未证** 优于当前 A9l 全栈。


---

## 第 2 轮（transcript L3375）

### 用户

snippet_on_topic()的过滤标准具体有哪些？ 按 query 顺序、块内检索顺序 具体而言是什么样的顺序？

### 助手

`snippet_on_topic()` 是 **IMP-35** 引入的门控：判断一条检索 hit 是否与当前综合征的 DDx/病因召回相关。下面按 **判定顺序** 和 **24 条摘要的排列顺序** 说明（对应 `_retrieve_snippets()` → LLM grounding 路径）。

---

## 一、`snippet_on_topic()` 过滤标准

实现见 `cpg_chunk_gate.py`，逻辑是 **短路式 OR**：任一条件满足即 **通过**；全部不满足则 **丢弃**。

### 输入

| 参数 | 含义 |
|---|---|
| `syndrome_tokens` | 来自综合征名：`re.findall(r"[a-z0-9]+", syn)` 且 **`len(t) > 3`** 的 token 集合 |
| `chunk_type` / `entry_type` / `syndrome_anchor` / `section_path` | 来自 chunk 元数据（依赖 IMP-31 索引是否写入这些字段） |

门控内部 `_tokens()` 用 **`len(t) > 2`** 做交集匹配，但 syndrome 侧只传入 **>3** 的 token，所以短词（如 `pain`）不会参与 syndrome 侧匹配。

### 判定链（按代码执行顺序）

**① `chunk_type` 白名单 — 直接通过，不做 syndrome 相关性检查**

```7:9:src/agentclinic_tree_dx/knowledge/cpg_chunk_gate.py
_USEFUL_CHUNK_TYPES = frozenset(
    {"differential", "red_flag", "evaluation", "recommendation", "diagnostic"}
)
```

若 `chunk_type ∈` 上述集合 → **True**。  
这是 IMP-35 的核心：NICE「Recommendations」、WikEM「Clinical Features」等标题不含 DDx 字面，但 `chunk_type` 正确时仍保留。

**② `entry_type == "syndrome_entry"` + anchor 匹配**

- 取 `syndrome_anchor`，若无则取 `title` 中 ` > ` 前的第一段
- 若 `syndrome_tokens ∩ _tokens(anchor) ≠ ∅` → **True**

**③ 章节语义正则 + syndrome token 重叠**

拼接 `blob = title + section_path + content[:200]`，用 `_SECTION_RE` 匹配是否含：

```
differential diagnos | etiolog | causes | evaluation | work-up/workup |
assessment | clinical features | red flag | can't miss | must not miss |
recommendations | approach
```

若匹配，还需满足以下 **之一**：
- `syndrome_tokens ∩ _tokens(title) ≠ ∅`
- `section_path` 存在且 `syndrome_tokens ∩ _tokens(section_path) ≠ ∅`

**④ 象限/解剖部位标题**

- `title` 含 `RUQ/RLQ/LUQ/LLQ/epigastric/pelvic`（不区分大小写）
- 且 `syndrome_tokens ∩ _tokens(title) ≠ ∅` → **True**

**⑤ 兜底：仅看 title**

- `syndrome_tokens ∩ _tokens(title) ≠ ∅` → **True**
- 否则 → **False**

### 要点

- **不是**「必须 title 含 Differential Diagnosis」的旧逻辑；`chunk_type` 或 anchor 匹配即可绕过标题字面要求。
- 无 `chunk_type` 的旧索引上，大量 chunk 会落到 ③–⑤，CPG 文档里 ~81–90% 误滤率主要来自这条路径。
- 通过门控后还有 **去重**：`sig = title[:60] + "|" + content[:40]`，与门控独立。

---

## 二、按 query 顺序：`_retrieve_snippets()` 的 2–4 条 query

```618:624:src/agentclinic_tree_dx/knowledge/guideline_branch_source.py
        queries = [f"differential diagnosis of {syndrome}",
                   f"causes and etiology of {syndrome}"]
        if colloq and colloq != syn:
            queries.append(f"approach to {colloq}")
        if context.strip():
            queries.append(f"differential diagnosis of {colloq or syndrome}. "
                           f"clinical features: {context.strip()[:300]}")
```

| 序号 | 条件 | Query 文本 |
|:---:|---|---|
| Q1 | 始终 | `differential diagnosis of {syndrome}` |
| Q2 | 始终 | `causes and etiology of {syndrome}` |
| Q3 | `colloq ≠ syndrome`（经 `_colloquial()` 去 jargon 后） | `approach to {colloq}` |
| Q4 | `context` 非空 | `differential diagnosis of {colloq or syndrome}. clinical features: {context[:300]}` |

注意：Spotter 路径的 `_build_queries()` 在 Q3 前还有 `differential diagnosis of {colloq}`，且 `query_mode=fanout` 时再加 5 条 facet query；**`_retrieve_snippets()` 没有这些**，LLM grounding 用的 query 列表更短。

每条 query：`search(top_k=k, score_threshold=0.0)` → **始终** `expand_ddx_siblings(hits)`（与 Spotter 在 `closure_mode='grounding'` 下不同，grounding 路径不做 sibling 扩展的是 spot pool，不是 `_retrieve_snippets`）。

---

## 三、块内（单条 query 内 hits）顺序

对 **每一条 query**，处理顺序如下：

```
search(top_k)          → 按检索分数降序（最相关在前）
expand_ddx_siblings    → [原 hits] + [扩展块]
逐块 gate + 去重       → 通过的 append 到全局 out
全局截断               → out[:24]
```

### 3.1 `search()` 返回顺序

- **FAISS**：`index.search` 返回的 `(score, idx)` 顺序，**分数从高到低**（`score_threshold=0.0` 时 top_k 内基本全保留）。
- **TF-IDF**：`argsort(scores)[::-1][:top_k]`，同样是 **相似度降序**。

### 3.2 `expand_ddx_siblings()` 追加顺序

返回 **`hits + extra`**，原检索结果顺序不变，扩展块接在后面：

1. **原 hits**：保持 search 的分数序（rank 1 → rank k）
2. **对每个原 hit 依次**：若有 `wiki_links`，合成一条 `chunk_type=differential` 的虚拟块追加
3. **对每个 hit 的 `source_id`（去重，顺序≈首次出现在 hits 中的顺序）**：
   - 从 `_sid_index[sid]` 取同文 sibling（`_DDX_USEFUL` 类型：`differential/red_flag/evaluation/recommendation/diagnostic`）
   - sibling 顺序 = **语料 metadata 文件中的索引顺序**（`enumerate(self._metadata)` 写入 sid_index 的顺序），**不是** relevance 重排
   - 每个 sibling 若还有 `wiki_links`，再追加虚拟块

### 3.3 单 query 内的遍历与占位

```627:652:src/agentclinic_tree_dx/knowledge/guideline_branch_source.py
        for q in queries:
            ...
            for h in hits:
                ...
                if not snippet_on_topic(...):
                    continue
                ...
                out.append(f"[{title[:70]}] {content[:400]}")
        return out[:24]
```

对扩展后的 `hits` 列表 **从前到后**：
1. `snippet_on_topic` → 不过则 skip  
2. `sig` 去重 → 重复则 skip  
3. 格式化 append  

**无 MMR、无按 score 二次排序**；顺序就是「query 优先级 × 块在 expanded hits 中的位置」。

---

## 四、全局 24 条的总顺序（直观）

```mermaid
flowchart TD
    Q1[Q1: differential of syndrome] --> H1[search top_k 按分数降序]
    H1 --> E1[expand_ddx_siblings]
    E1 --> F1[gate + dedupe → out]
    Q2[Q2: causes/etiology] --> H2[同上]
    H2 --> F2[append 到 out 尾部]
    Q3[Q3: approach to colloq 可选] --> F3[append]
    Q4[Q4: context 可选] --> F4[append]
    F4 --> CAP[out[:24] 截断]
```

**优先级规则**：

1. **Query 间**：Q1 占满 24 槽后，Q2–Q4 的块进不来（先 query 先占位）。
2. **Query 内**：检索 rank 高的原 hit 优先；sibling / wiki_links 扩展块排在对应 query 的原 hits 之后。
3. **跨 query 去重**：同一 `sig` 只在 **第一次出现** 时保留（通常保留在更靠前 query 里的那次）。

最终每条格式：`[{title[:70]}] {content[:400]}`，最多 **24** 条。

---

## 五、与 Spotter 路径的差异（便于对照）

| 维度 | `_retrieve_snippets`（LLM grounding） | `_gather_spot_hits` / `_recall_v2`（Spotter） |
|---|---|---|
| Query 数 | 2–4 | `_build_queries`：2–5+，fanout 时最多 10 |
| sibling 扩展 | **始终** expand | 仅 `closure_mode='pool'` 时 expand |
| 截断/重排 | 固定 `out[:24]`，无 MMR | 可经 `_mmr_select` 多样性裁剪 |
| 门控函数 | 同一 `snippet_on_topic()` | 同一 |

若还需要 `_recall_v2` 在 MMR 前后的完整顺序，或 `syn_toks` 与 gate `_tokens` 长度阈值不一致的影响，可以继续问。


---

## 第 3 轮（transcript L3385）

### 用户

这个FAISS指的是MedCPT或miniLM吗

### 助手

**不是。** FAISS 本身既不是 MedCPT，也不是 miniLM——它是 **向量近邻检索库**（存 embedding、做 top-k 搜索）。真正决定语义的是 **建索引时用的 encoder**，写在各索引目录的 `config.json` 里。

---

## 三层关系

```
Query 文本
  → Encoder（MiniLM / MedCPT / …）编码成向量
  → FAISS（或 TF-IDF）在索引里做 top-k
  → hits 列表 → snippet_on_topic → 24 条摘要
```

我上一条里说的「FAISS 按分数降序」，指的是 **若** `RAGRetriever` 检测到 `faiss.index` 并走 dense 后端时的行为；**不等于**分支实验默认就在用 FAISS。

---

## 本仓库里各索引实际用什么

| 索引目录 | 后端 | 编码模型 | 用途 |
|---|---|---|---|
| `data/corpus/rag_index` | **FAISS** | **`all-MiniLM-L6-v2`**（384 维） | StatPearls + Textbooks 通用 RAG |
| `data/corpus/cpg_index` | **TF-IDF**（无 FAISS） | sklearn 稀疏向量，无神经网络 | 分支实验主索引（A9l 等） |
| `data/corpus/cpg_medcpt_index` | **FAISS** | **`ncbi/MedCPT-Article-Encoder`**（768 维）；查询侧用 `MedCPT-Query-Encoder` | IMP-53 hybrid 的 dense 塔 |

对应 `config.json`：

- `cpg_index`：`"model": "tfidf"`, `"index_type": "TfidfSparse"`
- `rag_index`：`"model": "/data2/wanghongyi/models/all-MiniLM-L6-v2"`
- `cpg_medcpt_index`：`"model": "ncbi/MedCPT-Article-Encoder"`

`RAGRetriever` 的加载逻辑是：**先看有没有 `faiss.index`**，没有再看 **`tfidf_matrix.npz`**：

```64:88:src/agentclinic_tree_dx/knowledge/rag_retriever.py
        # Try FAISS first
        faiss_path = self._index_dir / "faiss.index"
        if faiss_path.exists():
            ...
                self._backend = "faiss"
        ...
        # Try TF-IDF
        tfidf_path = self._index_dir / "tfidf_matrix.npz"
        ...
                self._backend = "tfidf"
```

FAISS 路径下，query 编码用 `config.json` 里的 `model`（通过 `SentenceTransformer` 加载）——MiniLM 或 MedCPT 取决于 **哪个目录的 FAISS**。

---

## 和分支实验 / `_retrieve_snippets` 的关系

- **A9l、A1_grounding 等默认臂**：`RAGRetriever("data/corpus/cpg_index")` → **`cpg_index` 是 TF-IDF**，前面讨论的检索排序是 **TF-IDF 余弦相似度降序**，不是 MedCPT 也不是 miniLM。
- **A10/A11 hybrid 臂**：`HybridCPGRetriever` = **TF-IDF（sparse）+ MedCPT FAISS（dense）**，两路 RRF 融合后再进同一套 gate / 24 条截断。

MedCPT **不会**自动替代 `cpg_index` 的 TF-IDF；只有显式用 `HybridCPGRetriever` 或把 retriever 指到带 MedCPT FAISS 的索引时才会参与。

---

## 一句话

- **FAISS** = 检索引擎  
- **miniLM** = `rag_index`（StatPearls/Textbooks）的 FAISS 编码器  
- **MedCPT** = `cpg_medcpt_index` 的 FAISS 编码器（hybrid dense 塔）  
- **分支 phase 主路径** = `cpg_index` 的 **TF-IDF**，两者都不是


---

## 第 4 轮（transcript L3392）

### 用户

24条摘要实测在所有闭包中包含多大比例的chunk？会遗漏多少？

### 助手

**结论先说：** 在本仓库 `cpg_index` + `_retrieve_snippets()`（`top_k=30`、4 条 query、`expand_ddx_siblings`、门控、`out[:24]`）配置下，24 条摘要只覆盖闭包扩展后 chunk 的约 **1–3%**（8 题难病集均值 **1.6%**），相对门控后 eligible 池遗漏约 **98%**（均值 **1644 块/题**）。功能上 gold 命中率从 gate 池 **6/8** 降到 24 条 **2/8**。

---

## 测量口径

| 层级 | 含义 |
|---|---|
| **检索** | 4 条 query × `search(top_k=30)` 的去重 chunk 数 |
| **闭包** | 对上述 hits 做 `expand_ddx_siblings` 后的 **unique chunk id** |
| **gate 池** | 闭包遍历 + `snippet_on_topic` + sig 去重（**截断前**全量 eligible） |
| **24 条** | gate 池按 query/块顺序 FIFO 取前 24 |

这与 `grounding` 模式下 LLM 实际读到的 excerpt 一致；**不是** spotter 的 40 槽候选池。

---

## 8 题难病集（medbullets hard）

| 指标 | min | max | mean | median |
|---|---:|---:|---:|---:|
| 检索 unique | 48 | 114 | **73** | 72 |
| **闭包 unique** | 861 | 2393 | **1687** | 1772 |
| 闭包新增 sibling | 813 | 2279 | **1614** | 1700 |
| 闭包/检索倍率 | 17.9× | 29.9× | **~23×** | — |
| **gate 池** | 840 | 2355 | **1668** | 1761 |
| **→24 保留占闭包** | 1.0% | 2.9% | **1.6%** | 1.4% |
| **→24 保留占 gate 池** | 1.0% | 2.9% | **1.6%** | 1.4% |
| **遗漏（gate 池 − 24）** | 816 | 2331 | **1644** | 1737 |

逐例 gold（token 子串匹配）：

| case | 闭包 | gate 池 | 24 条 | gold@gate | gold@24 |
|---|---:|---:|---:|:---:|:---:|
| c1 Pancoast | 2393 | 2355 | 24 | ✓ | ✗ |
| c9 leukemoid | 1699 | 1685 | 24 | ✗ | ✗ |
| c13 glucagonoma | 2101 | 2074 | 24 | ✓ | ✗ |
| c17 CML | 1772 | 1761 | 24 | ✓ | ✗ |
| c18 peliosis | 2186 | 2165 | 24 | ✗ | ✗ |
| c22 PHPT | 1025 | 1023 | 24 | ✓ | ✓ |
| c23 adhesions | 861 | 840 | 24 | ✓ | ✓ |
| c24 foreign body | 1455 | 1437 | 24 | ✓ | ✗ |

- **gate 有、24 漏 gold**：c1、c13、c17、c24（4/8）
- **24 条中来自 sibling 闭包块**：8 题均为 **0** — 24 槽全被各 query 的 **top 检索 hit** 占满，sibling 在遍历顺序上排在后面

---

## 14 题 multilevel 集

| 指标 | 范围 | mean |
|---|---|---|
| gate 池 | 78–1555 | **771** |
| 24/ gate 池 | 1.5%–30.8% | **6.4%** |
| 遗漏块数 | — | **747**/题 |

22 题（8+14）**无一题** gate 池 < 24，故最终摘要恒为 **24 条**（不是「池子小所以全保留」）。

文档对照 `abdominal pain`（≈ §15.1 的 8→213 量级）：闭包 **758**、gate **748**、24 条约 **3.2%**。

---

## 为何 gate 池 ≈ 闭包、但 24 条只留 ~1–3%

1. **门控几乎不过滤闭包块**  
   `chunk_type ∈ {differential, red_flag, evaluation, recommendation, diagnostic}` → **直接通过**，多数 PMC sibling 带 `evaluation/diagnostic`，gate 池规模接近闭包（1668 vs 1687，差 ~1%）。

2. **24 是 FIFO 截断，不是 relevance 重排**  
   `expand_ddx_siblings` 返回 `原 hits + sibling`；遍历先走完 Q1 的 top-30 检索块，再 Q2…  
   难病集平均 **73 个检索块** 经 gate 后仍远超 24，**24 槽在 sibling 之前就满** → sibling 闭包对 LLM grounding **名义上扩展了 ~23×，实际 24 条里 0 块来自 sibling**。

3. **信息压缩比**  
   均值 ~1668 块 × ~400 字/块 ≈ **66 万字** prose → 24 × 400 ≈ **9600 字**（约 **1.5%** 字符量）。

---

## 和文档「8→213」的关系

§15.1 的 **8→213** 是 **单次 query、闭包扩展后 hit 列表长度**（未计 4 query 合并、门控、24 截断）。  
完整 `_retrieve_snippets` 链路上闭包 mean **~1687 unique**，但 **24 条只保留 ~1.6%**；闭包对 LLM 的主要价值不是「把 200+ 块都喂进去」，而是 **扩大 gate 池以便更高概率摸到 gold**——实测 gate 池 6/8 有 gold，截断后只剩 2/8。

---

## 一句话

**24 条摘要 ≈ 闭包/eligible 池的 1–3%，遗漏 ~97–99% 的块；对难病 gold，gate 池 75% 命中 → 24 条 25% 命中，主要因为 sibling 闭包块排在 FIFO 24 槽之后。**  
若要让闭包里的 gold sibling 进 LLM 上下文，需要改排序（MMR/relevance）、提高 cap、或优先保留含 `source_id` 闭包块——当前 `_retrieve_snippets` 未做这些。


---

## 第 5 轮（transcript L3403）

### 用户

这种方式是否潜在地伤害了召回率

### 助手

**会，但伤害集中在 LLM grounding 支路；对 A9l 全栈召回是「有条件、可部分代偿」的。**

---

## 1. 先分清：24 条 cap 打在哪一层

| 路径 | 是否受 `out[:24]` 约束 | 对最终候选召回的影响 |
|---|---|---|
| **Spotter**（`_gather_spot_hits`） | **否**（`grounding` 模式下闭包不进 spotter 池） | 直接不受影响 |
| **`recall_llm` / 方案 A** | **是**（只读 ≤24 条 excerpt） | **直接上限**：LLM 规则写死「只许列 excerpt 里出现的病名」 |
| **A9l 全栈**（Spotter + LLM + nominate + pathognomonic） | LLM 支接受限；其它支路可补 | **部分代偿** |

因此不能笼统说「24 条伤害了召回率」，要说 **伤害了哪条支路、在什么 case 上、最终有没有被其它机制补回来**。

---

## 2. 实测：对「片段层 retrieved」的伤害是真实存在的

B6 漏斗里的 **retrieved** = 合并 `_retrieve_snippets()` 的 24 条文本里是否含 gold（家族 token 匹配），**不是**全 gate 池。

**A1_grounding（8 题难病）**：

| 指标 | 值 | 含义 |
|---|---:|---|
| retrieved_rate | **7/8 (87.5%)** | 24 条里摸到 gold |
| spotted_rate | **6/8 (75%)** | 候选 dict 含 gold |
| extraction_loss | **1** | 片段有 gold 但 spotter 没抽出（c13 glucagonoma） |
| neither | **1** | 24 条和候选都没有（c1 Pancoast） |

与我们刚跑的 **gate 池 vs 24 条**对照：

- gate 池（截断前）摸到 gold：**约 6/8**（严格 token）到 **7/8**（家族匹配，与 B6 口径接近）
- 24 条内：**7/8**（B6 官方口径）
- **闭包 sibling 进 24 条：0/8** — 扩展了 ~1600 块，FIFO 24 槽全被各 query 的 top 检索 hit 占满，sibling 对 LLM 上下文 **名义扩展、实质未进入**

**结构性矛盾**：`expand_ddx_siblings` 把闭包拉到 ~23×，但 `_retrieve_snippets` 只留 **~1.6%**；对 **§18 类「gold 只在 sibling 块」**（c1  archetype），24 条 cap + FIFO 顺序会 **系统性挡在 LLM 门外**。

---

## 3. 对最终召回：全栈可代偿，LLM 单支路不行

**A9l** 上同一 8 题漏斗：

| 指标 | A1_grounding | A9l |
|---|---:|---:|
| retrieved（24 条含 gold） | 7/8 | 7/8 |
| spotted（候选含 gold） | 6/8 | **8/8** |
| extraction_loss | 1 | **0** |

典型 **c1 Pancoast**：

- `retrieved: false` — 24 条摘要 **不含** gold
- `spotted: true` — 候选里有 `pancoast tumor`（经 **nominate / pathognomonic**，非 LLM 读摘要）
- bucket = **`spotted_not_in_snippets`**

说明：

1. **24 条 cap 确实挡了 LLM grounding**（`recall_llm` 对 c1 帮不上忙，excerpt 里没有就不能列）。
2. **A9l 最终召回没被这一层拖死**，因为 Spotter + 直提名等 **不依赖 24 条**。
3. 若走 **纯 LLM 抽取** 或 **方案 A 单次 LLM 建域**，24 条 cap 的上限会更硬。

---

## 4. 伤害机制（按严重度）

```
闭包扩展 ~1687 块
    ↓ gate 池 ~1668 块（chunk_type 白名单，几乎全过）
    ↓ FIFO 取前 24（≈ 全来自 top 检索 hit，0 来自 sibling）
    ↓ LLM 只能 grounded 读这 24 条
    ↓ gold 若在 sibling / 排序 25+ → LLM 支路永久丢失
```

| 场景 | 24 条 cap 的伤害 |
|---|---|
| gold 在 top 检索 hit 正文 | **低**（B6 7/8 retrieved） |
| gold **只在 sibling 闭包块**（c1） | **高** — LLM 不可达；需 nominate/机制桥接 |
| gold 在 gate 池但排序 25+（被常见病块挤掉） | **中** — 如 c13：A1 里 retrieved=✓ 但 spotter 仍失败，A9l 靠 LLM 补抽取 |
| 14 题常见综合征 | gate 池较小（mean ~771），24/池 mean **6.4%**，相对 8 题伤害略轻，但仍截断 |

---

## 5. 和「grounding 改闭包去向」的权衡

把闭包从 spotter 池挪到 grounding（IMP-63）**解决了 C4**（常见病灌 40 实体槽），但把瓶颈挪到 **LLM 输入侧**：

- **Spotter 召回**：不再被 200+ sibling 块污染 → **受益**（A1 grounding 0.702 vs legacy 0.54–0.65）
- **LLM 召回**：只有 24×400≈9600 字 → **新瓶颈**；闭包 sibling 对 LLM **几乎零贡献**（实测 0/8）

文档 §19.5 也指出：MMR/`extract_k` 裁剪 spotter 有害，但 **`_retrieve_snippets` 的 24 cap「仅宜用于喂 LLM 的 grounding」** — 即承认这是 **刻意的成本/噪声 trade-off**，不是无损压缩。

---

## 6. 结论

| 问题 | 答案 |
|---|---|
| **是否潜在伤害召回？** | **是**，对 **LLM grounding / 方案 A** 有硬上限；对 **Spotter 主路径** 无直接 cap |
| **实测伤害多大？** | 片段层：8 题 **1/8 neither**（c1）；**4/8** 类 case 在严格口径下 gate 有 gold 但 24 条未必有；sibling 对 24 条贡献 **0%** |
| **全栈为何仍高？** | A9l 用 **Spotter ∥ LLM ∥ nominate**；c1 走 `spotted_not_in_snippets` 代偿 |
| **若去掉 24 cap？** | LLM 支路 retrieved 可能 ↑，但 ~1668 块喂单次 LLM 不可行；更合理是 **闭包块优先排序 / MMR / 按 source_id 配额**，而非简单放大 cap |

**一句话**：24 条 FIFO 截断 **确实潜在且实测存在地伤害「LLM 读摘要」这条召回支路**，尤其伤 **sibling 闭包里的 rare gold**；当前 A9l 靠 **非 LLM 通道代偿**，所以综合分仍高，但 **不能据此认为 24 条设计对闭包是「无害压缩」** — 它是 LLM 侧的已知漏斗损耗，c1 就是活证据。


---

## 第 6 轮（transcript L3409）

### 用户

这样来看，sibling的利用难题是否无法在纯RAG的框架下解决，只能后续借助GraphRAG等架构修改来完成

### 助手

**不完全是。** sibling 利用难，在当前实现里主要是 **RAG 流水线设计问题**（闭包扩了、排序和预算没给 sibling 留位），不是「纯 RAG 理论上做不到」。  
但 **c1 这类机制/专名鸿沟**，单靠「检索 + 同篇 sibling 扩展」确实不够，需要 **结构化入口或机制桥**——GraphRAG 是一种解法，不是唯一解法，也未必是成本最低的解法。

---

## 1. 先把两个问题拆开

| 问题 | 本质 | 纯 RAG 能否解决 |
|---|---|---|
| **A. sibling 扩了但进不了 24 条** | 预算 + FIFO 排序；闭包 ~1600 块，24 槽被 top 检索 hit 占满 | **能**，改检索后处理即可，不必上 GraphRAG |
| **B. 入口文章根本没进 top-k**（c1） | query 与 corpus 词面不一致；TF-IDF 摸不到 Pancoast 那篇 | **单靠 vector/BM25 RAG 很难**；要 anchor、别名、机制 query 或 **非检索通道** |
| **C. sibling 池噪声太大**（evaluation 块泛滥） | `chunk_type` 白名单几乎全过 → gate 池 ≈ 闭包 | **能**，改门控/按 section 重排；仍是 RAG 内工程 |

实测里 **0/8 的 sibling 进 24 条**，说明的是 **当前 `_retrieve_snippets` 策略失效**，不是 RAG 范式失效。

---

## 2. 纯 RAG 框架内仍可做的 sibling 利用（尚未做或做了一半）

项目里 **已有** 图式结构，只是没用好：

- `source_id` + `expand_ddx_siblings` = **篇内 star graph**（入口 hit → 同篇 differential/evaluation sibling）
- `syndrome_anchor` / `entry_type` = 结构化入口元数据
- `wiki_links` 合成块 = 显式 DDx 边

在 **不改成 GraphRAG** 的前提下，仍可：

1. **闭包优先配额**  
   24 条里固定 N 槽（如 8）只给 `expand_ddx_siblings` 追加块，且优先 `chunk_type=differential` / 含 DDx 列表的 sibling，而不是 FIFO 先填满检索 hit。

2. **两阶段 RAG（仍是 RAG）**  
   Stage1：query → 命中 entry；Stage2：**仅在 hit 的 `source_id` 内**再检索/过滤，取 differential 子块 → 再截断。比「全库闭包 1600 块 + 24 cap」精准得多。

3. **按篇聚合后再 cap**  
   每个 `source_id` 合成 1 条「本篇 DDx 摘要」（规则或 LLM），24 条 ≈ 24 **篇** 而非 24 **随机块** — 仍是 RAG，只是 chunking/aggregation 层不同。

4. **闭包后 relevance 重排**  
   对 sibling 用 query–chunk 分数或 MMR（文档已证伪 **spotter 池** 上的 MMR-trim，但 **LLM grounding 的 24 条** 尚未做 sibling-aware 重排）。

5. **收紧 gate**  
   sibling 闭包时只保留 `differential` + `red_flag`，不要把全篇 `evaluation/diagnostic` 都放进 eligible 池 — 可直接把 effective 池从 ~1668 降到可管理的规模。

这些都不需要 GraphRAG；需要的是 **「先定位文章，再在文章内精取 DDx 块」**，而不是「全库闭包灌池 + 前 24 个」。

---

## 3. 什么情况下才「纯 RAG 不够」、要 Graph / 机制层

与 sibling 利用 **不同** 的是 **§18 / §19 已坐实的 curated-free 天花板**：

- **entry+closure 上界 100%**（oracle 按 anchor 选入口）  
- **生产检索 curated-free ≈ 7/8**；c1 四路检索臂皆 `--`  
- c1 的 gap 是 **「右臂无力」↔「Pancoast/superior sulcus」无表层词重叠**，不是 sibling 排序能修的

这类 case 需要至少之一：

| 手段 | 是否 GraphRAG | 项目现状 |
|---|---|---|
| 机制/解剖 query 扩展（IMP-52 fanout） | 否 | 部分验证，c1 仍漏 |
| `syndrome_anchor` / 锚点 UNION（D2） | 轻量「图」 | 有，c1 仍漏（呈现词不匹配 anchor） |
| **pathognomonic / nominate（IMP-58）** | 否，规则+标志物 | **A9l 已用**，c1 靠此 spotted |
| 别名/eponym crosswalk（IMP-59） | 否 | 待完善 |
| **GraphRAG / 知识图谱** | 是 | 未入主链 |

所以：**「sibling 利用难」≠ 必须 GraphRAG**；**「入口选错 / 词面够不着」** 才更接近需要 graph、别名网或机制推理。

GraphRAG 的价值在于：显式 **Article → Section → Entity** 遍历、社区摘要、跨篇关系 — 适合 **L3 碎片化 + 入口分散 + 跨 chunk 推理**。但 IMP-31 的 `source_id` 闭包已经是 **最小版 article graph**；缺的是 **遍历策略与预算分配**，不是完全没有图。

---

## 4. 和当前架构选择的对齐

```
纯 RAG（当前）          增强 RAG（仍非 GraphRAG）        GraphRAG / 混合
─────────────────────────────────────────────────────────────────
TF-IDF top-k      →   两阶段 + sibling 配额 + 篇级聚合
expand 闭包       →   闭包只取 differential + 重排
24 FIFO cap       →   grounding 专用 MMR / 闭包优先槽
spotter 主召回    →   nominate/pathognomonic 补 c1 类
recall_llm 读 24  →   方案 A 同限；与 spotter union 代偿
```

**A9l 的实际策略**已经是：**RAG 负责广度，非 RAG（nominate、cant_miss、resolver）补检索够不着的那一格** — 不是等 GraphRAG 才解决 sibling/c1，而是 **分层**。

文档结论也一致：瓶颈主因是 **Step 1–2 工程损耗**（检索排序 + spotting/LLM 抽取），不是「必须换 GraphRAG 范式」；GraphRAG 在 IMP 链里 **未入主路径**。

---

## 5. 直接回答你的判断

| 说法 | 是否成立 |
|---|---|
| sibling 在 **当前** 纯 RAG 流水线里 **几乎没被利用** | **成立**（实测 24 条中 sibling 0/8） |
| 因此 **只能** 靠 GraphRAG 才能解决 | **不成立** — 先在 RAG 内做 **篇内二阶段 + 闭包配额 + 门控收紧** 即可显著改善 |
| 有些 case（c1）**单靠 RAG+sibling 不够** | **成立** — 需要机制桥/标志物/别名，GraphRAG 是选项之一，**nominate 已在用** |
| GraphRAG 是 **合理的中长期方向** | **成立** — 尤其跨篇 DDx、社区摘要、显式入口导航；但 **不是 sibling 24 槽问题的唯一出口** |

**一句话**：sibling 利用难，首先是 **「扩了但没排进预算」的 RAG 后处理问题**，纯 RAG 内仍可修；**curated-free 下摸不到入口文章** 才是更接近 Graph/机制层的问题，而项目已通过 **grounding + nominate 分流** 先绕开，而非等待 GraphRAG 替换整条链。若只改一处、成本最低：**给 sibling 留固定 grounding 槽 + 闭包只拉 `differential/red_flag`**，仍在现有 `GuidelineBranchSource` 框架内。


---

## 第 7 轮（transcript L3412）

### 用户

将本对话导出为json，前端显示似乎出现损坏，注意要完整版本而非摘要

### 助手

已从 Cursor 原始 transcript JSONL 导出完整版（非摘要）。

**主文件**：`data/cpg/eval/conversation_export_d6e23c24_full.json`（~200KB）
**原始事件 JSONL**：`data/cpg/eval/conversation_export_d6e23c24_thread.jsonl`（子线程 43 事件）

前端推荐读取 `messages_chronological` 数组（7 轮 user/assistant 交替，assistant 为完整 Markdown 正文）。
旧文件 `conversation_export_d6e23c24.json` 为手工摘要，已标记 deprecated。

说明：原始 transcript 中 tool 中间步骤含 `[REDACTED]` 脱敏，无法恢复；各轮最终回答正文已完整保留。


---

## 第 8 轮

### 用户

将3370行后的导出内容整理成可读版本的md对话形式

### 助手

已从 `conversation_export_d6e23c24_full.json` 整理为本 Markdown 对话文档。

**文件**：`data/cpg/eval/conversation_export_d6e23c24_dialogue.md`

**结构**：
- 顶部元数据表（conversation_id、transcript 起始行 3370）
- 第 1–7 轮：`### 用户` / `### 助手` 交替，assistant 正文完整保留
- 各轮标注对应 transcript 行号（如有）

**相关文件**：
| 文件 | 用途 |
|---|---|
| `conversation_export_d6e23c24_full.json` | 机器可读完整 JSON |
| `conversation_export_d6e23c24_thread.jsonl` | 原始事件 JSONL（43 条） |
| `conversation_export_d6e23c24_dialogue.md` | 本可读对话（当前文件） |

---

> **第 9–11 轮**：2026-06-28 **手动补回**（JSON / transcript 无留存；正文来源：会话归档 §14.8–§14.10）。

## 第 9 轮（手动补回 · JSON/transcript 无留存 → §14.8）

### 用户

在 branch-gen 主路径上，TF-IDF 对同义词/机制表述/专名（如 myeloid↔myelogenous、Pancoast↔superior sulcus）很弱；除 MedCPT 双塔外项目里还有哪些缓解？同义词 vs 机制/专名鸿沟如何区分？

### 助手

你的判断成立：**在 branch-gen 主路径上，检索相似度与病名匹配都高度依赖词面重叠**，同义词/机制表述/专名（如 myeloid↔myelogenous、Pancoast↔superior sulcus）确实是 TF-IDF 的结构性弱点。  
但项目里 **除 MedCPT 双塔外，已经有多层缓解**——只是它们分布在 **检索前、检索旁路、抽取后** 不同位置，且 **IMP-59 等关键项尚未落地**。

---

## 1. 同义词问题实际落在哪几层

| 层级 | 机制 | 同义词敏感度 |
|---|---|---|
| **Query → chunk 检索** | TF-IDF cosine | **高** — 无共有 token 则相似度≈0 |
| **chunk 文本 → 病名 spotting** | SNOMED disorder 词典 n-gram | **中** — 词典含 synonym，但须 **正文里出现** 该写法 |
| **候选 → gold 评测/投影** | token 子集 + `GOLD_FAMILY_TOKENS` | **低** — 评测层已放宽 |
| **机制/专名表述** | 不是同义词，是 **词面鸿沟** | TF-IDF **无法** — 需 nominate/resolver |

所以：**同义词** 和 **机制/专名鸿沟** 要分开治；后者 MedCPT 也补不全（c1 四路检索臂皆漏）。

---

## 2. 除 MedCPT 外，**已落地**的缓解

### A. 检索侧（仍在 TF-IDF 框架内）

| 措施 | 作用 | 局限 |
|---|---|---|
| **多 query**（2–4 条：DDx / etiology / colloquial / context） | 换词面角度提高命中 | 不是同义词扩展；`fanout` 五路 **证伪**（A6 0.693 < A1 0.702） |
| **`_colloquial()`** | 去 jargon 再查（如 focal limb neuro deficit → limb） | 规则去词，非 alias 表 |
| **GARMLE-G① context query** | 把 `clinical features: …` 拼进 query | 靠 **体征词** 桥接，非病名同义词 |
| **`expand_ddx_siblings`** | 同篇扩展，非跨词面 | 入口未命中则无效 |
| **`AnchorAugmentedRetriever`（D2）** | 按 `syndrome_anchor`/`section_path` token 重叠 UNION 入口块 | **轻量结构化匹配**；c1 仍漏；已 **退出主路径** |

### B. 抽取/候选侧（**绕过 TF-IDF 同义词**）

| 措施 | 作用 | 与 TF-IDF 关系 |
|---|---|---|
| **SNOMED spotting 词典**（`build_disorder_vocab`：preferred + **synonyms**） | 正文里任一同义词写法均可 n-gram 命中 | 不治「检索摸不到含同义词的 chunk」 |
| **`DiseaseNameResolver`** | 手动 alias 表、mechanism_map、`expand_to_entities`、`canonicalize_entity` | **候选层归一**；评测层 CML 等已受益 |
| **IMP-58 nominate + pathognomonic** | 读 context  **直提名** 目标病（c1 靠此 spotted） | **完全不走检索相似度** |
| **cant_miss 注入（IMP-60/56）** | 按综合征 curated 下界强制进候选池 | 同左 |
| **Spotter + LLM union（A9l）** | LLM 从摘要抽实体，与 spotter 合并 | LLM 仍受 24 条摘要限制 |

### C. 其它知识层（branch-gen 外围，但同源问题）

- **LR cache**：`_DISEASE_SYNONYM_PAIRS`（myeloid↔myelogenous 等）+ 多层 fuzzy lookup  
- **DxFeatureRetriever**：SNOMED `expand_synonyms` 桥接各源键  
- 这些 **不进入** `GuidelineBranchSource.recall()` 的 TF-IDF 热路径

---

## 3. **已设计/部分验证、未入主链**的缓解

| ID | 措施 | 状态 | 说明 |
|---|---|---|---|
| **IMP-59** | `syndrome_alias_map.json`（AMS↔altered mental status 等） | **🔴 待落地**（仓库无此文件） | 治 **综合征 query ↔ corpus anchor** |
| **IMP-58 扩展** | scispaCy / UMLS linker 全面接入候选层 | 部分（resolver + nominate） | 治 **实体归一**，非检索 embedding |
| **IMP-51** | `entry_type=syndrome_entry` 检索 boost | 待办 | 结构化入口加权 |
| **L12 两阶段重排** | MedCPT bi-encoder 召回 + **cross-encoder 重排** | ⚪ P2 | 仍属 dense，但是 **重排** 而非双塔召回 |
| **HyDE / SL-HyDE / CHR** | LLM 生成假想 DDx 文档再检索 | ⚪ P2，文档定 **低置信兜底** | 弥合语义鸿沟，需防幻觉 |
| **SPLADE / 学习稀疏** | 可扩展同义词的稀疏向量 | 文档提及，**未实现** | TF-IDF 升级版，仍非 GraphRAG |
| **索引期同义词注入** | 建索引时把 SNOMED/UMLS alias 拼进 chunk 文本 | **未做** | 零运行时成本的传统做法 |

---

## 4. 实测：各措施实际补了多少

**8 题难病 B6 漏斗（A1_grounding，纯 TF-IDF）**：

- retrieved（24 条含 gold）：**7/8**
- spotted：**6/8**
- c1：**neither**（词面够不着 Pancoast 文章）

**A9l（+ nominate + pathognomonic + LLM）**：

- spotted：**8/8**（c1 = `spotted_not_in_snippets`，**非 TF-IDF 找回**）

**A10 hybrid（+ MedCPT RRF）**：

- 综合 0.702→**0.719**；漏斗 xloss 1→0  
- 修的是 **B2 词面/语义鸿沟**，不是全部同义词

结论：**纯 TF-IDF 检索的上限约 7/8**；第 8 格（c1）靠 **nominate/标志物** 补，不靠同义词扩展。

---

## 5. 按成本排序的「非 MedCPT」选项

若暂不上 dense 双塔，仍可在 **纯稀疏/规则** 框架内做：

```
低成本 ──────────────────────────────────────────► 高成本
│
├─ 索引期：SNOMED/UMLS alias 写入 chunk 索引文本（一次建库）
├─ Query 期：IMP-59 syndrome_alias_map + 缩写展开表
├─ Query 期：RAG-Fusion 多 query + RRF（比 fanout 更控噪）
├─ 检索后：Anchor UNION（D2 形态，保 PMC 主干）
├─ 候选层：Resolver + nominate（已证明对 c1 有效）
├─ 稀疏升级：SPLADE / BM25+synonym expansion
└─ Dense：MedCPT hybrid（已验证）→ cross-encoder 重排
```

**同义词** 最有效的前三项通常是：

1. **索引/查询双侧 alias 表**（IMP-59 + 建库注入）— 仍 TF-IDF，但把同义词变成 **共有 token**  
2. **MedCPT hybrid** — 语义近邻，已验证  
3. **nominate/resolver** — 对 **机制/专名** 比同义词扩展更关键

---

## 6. 直接回答

| 说法 | 判断 |
|---|---|
| TF-IDF 对同义词处理弱 | **成立** |
| 只能靠 MedCPT 双塔 | **不成立** |
| 已有其它缓解 | **成立**，但分散且 **IMP-59 未落地** |
| 同义词 vs 机制鸿沟 | 须分开；后者 **nominate 已在用**，MedCPT 也补不了 c1 |
| GraphRAG 是否必需 | **不必**；alias 表 + 索引注入 + hybrid + nominate 组合更贴近当前 IMP 链 |

**生产推荐栈**（文档一致）：**TF-IDF + MedCPT RRF（检索）** + **grounding 闭包** + **nominate/pathognomonic（候选）** + **fanout 关**；下一步同义词收益最大且成本低的增量是 **IMP-59 syndrome alias crosswalk + 建索引时 SNOMED synonym 注入**，不必等 GraphRAG。

---

## 第 10 轮（手动补回 · JSON/transcript 无留存 → §14.9）

### 用户

检索阶段对同义词也发 query，能否解决当前 14+8 题检索瓶颈？

### 助手

**不能。** 在 14+8 题上，「同义词多发 query」**不足以解决当前检索瓶颈**；对 8 题难病集 **几乎零增益**，对 14 题常见集还有 **稀释回归** 风险。下面分集合说明。

---

## 1. 两集合的瓶颈本来就不一样

| 集合 | 检索层现状（A1_grounding，TF-IDF） | 主瓶颈 |
|---|---|---|
| **14 题常见** | L1tgt **12/14 (86%)**；composite **0.702** | 少数 **L1 漏靶**（hyponatremia、lower GI bleed）+ **mandatory/L2/轴**；检索大多够用 |
| **8 题难病** | B6 retrieved **7/8**；multilevel_hard composite **0.372** | **c1 机制/专名鸿沟** + **mandatory/轴**；不是「换个同义词就能搜到」 |

同义词 query 只能作用于 **「query 词面 ↔ 文档词面」** 这一层；两集合里大量失败在 **spotting、40 槽裁剪、投影、轴** 等下游。

---

## 2. 同义词多发 query 的模拟结果（22 题，TF-IDF + 现有 24 条 cap）

在 baseline 2–4 条 query 上，为每个综合征追加 **≤4 个 SNOMED/手工 alias**，每条 alias 再发 `differential diagnosis of …` / `causes and etiology of …`：

### 8 题难病（gold 是否在 24 条摘要里）

| 指标 | baseline | +同义词 query |
|---|---:|---:|
| gold@24 snippets | **7/8** | **7/8** |
| 新增命中 | — | **0** |
| c1 Pancoast | ✗ | ✗（仍漏） |

逐例 **无 flip**：c9/c13/c17 等本来就能 retrieved，加 synonym 不变；c1 加了 `pancoast syndrome`、`brachial plexopathy` 等仍漏。

### 14 题常见（`recall()` 候选层）

| 指标 | baseline | +同义词 query |
|---|---:|---:|
| L1 target 命中 | **12/14** | **10/14** ↓ |
| 24 条摘要 L1tgt | 12/14 | 12/14（不变） |

**回退 2 题**：`acute_pancreatitis`、`acute_kidney_injury` — 泛化 synonym（如 `injury`、`pancreatitis` 子类型）把检索拉偏，**40 槽被噪声挤占**。这与 **IMP-52 fanout 证伪**（A6 0.693 < A1 0.702）同机制：**query 越多 ≠ 越好**，在 TF-IDF + 固定 cap 下易稀释。

---

## 3. 为什么同义词 query 救不了 c1（8 题里最硬的一格）

对 c1 做了更细的 corpus 探针：

| Query | top-30 是否含 Pancoast 块 |
|---|---|
| `differential diagnosis of focal limb neuro deficit` | ✗ |
| `differential diagnosis of pancoast syndrome` | ✗ |
| `differential diagnosis of superior sulcus tumor` | ✗ |
| `… clinical features: apical lung, Horner, arm pain` | 闭包池里 **仅 1** 块含 pancoast |

全库仅 **1 个 chunk** 正文含 `pancoast` / `superior sulcus`；即使用 **正确病名同义词** 作 query，TF-IDF top-30 仍是 WikEM 泛化 DDx 页（Weight loss、Numbness…），**排不到那 1 块**。

这是 **排序 + 语料稀疏**，不是「少发一条同义词 query」能修的；context query 能 **摸到** 那 1 块，但 **24 条 FIFO** 仍可能把它挤掉（前面讨论的 sibling/排序问题）。

---

## 4. 14 题里同义词能帮到多少？

14 题的 syndrome 本身已是标准临床词（hypercalcemia、hyponatremia、SIADH…），**与 corpus 词面高度对齐**，baseline 已到 12/14。

剩余失败例：

- **hyponatremia → SIADH**：评测要的是 **SIADH 作为 L1 靶**，主 query 已是 `hyponatremia`；加 SIADH synonym 可能略帮检索，但 A1 上该题 L1tgt=false 的主因更像是 **mandatory/轴/40 槽**，不是单纯同义词
- **lower_gi_bleeding**：同理，更偏 **候选覆盖/投影**，非 query 同义词

Eval 集里 **US/UK 双拼**（hemorrhage/haemorrhage、hypertriglyceridemia/hypertriglyceridaemia）已在 **gold 家族 token** 里处理评测，**不等于** 检索 query 已做 alias 扩展。

---

## 5. 和「当前瓶颈」的对应关系

```
22 题总瓶颈分解（简化）
│
├─ 词面同义词鸿沟（myeloid↔myelogenous, SAH↔hemorrhage）
│     → 同义词 query 有帮助空间，但 14 题已 largely OK；8 题里多数已 7/8
│     → 实测 +0 flip；14 题 recall 还可 -2
│
├─ 机制/呈现 ↔ 病名（c1：臂无力 ↔ Pancoast）
│     → 同义词 query **无效**（即使用对病名也排不进 top-k）
│     → 需 context query / nominate / pathognomonic（A9l 已用）
│
├─ 24 条 / 40 槽 截断
│     → 多发 query 让池子更大，**更易被截断**，与 synonym 方向相反
│
└─ 语义近邻（无共有 token）
     → 需 MedCPT hybrid（A10 +1.7pp composite），不是 sparse synonym
```

---

## 6. 结论与建议优先级

| 问题 | 同义词多发 query 能否作为「当前瓶颈」主解？ |
|---|---|
| 8 题检索 retrieved 7→8 | **不能**（实测 0 提升；c1 需非检索通道） |
| 8 题综合 composite 0.37→高 | **不能**（mandatory/轴/L1 多因 downstream） |
| 14 题 L1tgt 12/14→更高 | **不能指望**；有 **回退风险** |
| 22 题整体 | **辅助手段**，非瓶颈突破 |

更合理的组合（与现有 IMP 链一致）：

1. **IMP-59**：只对 **综合征 hand label → corpus anchor** 做 **小表 crosswalk**（不是对每病名 fanout 8 条 query）
2. **MedCPT RRF**（已验证）：补 **无共有 token** 的语义缝，比 synonym query 更稳
3. **context query + nominate**：补 c1 类 **机制鸿沟**（已验证 A9l spotted 8/8）
4. 若仍用 sparse 扩展：优先 **索引期注入 alias** 或 **RAG-Fusion + 控噪**，避免 fanout 式盲目加 query

**一句话**：同义词多发 query 在 14+8 上 **解决不了当前主瓶颈** — 8 题已 7/8 且 c1 非 synonym 问题；14 题检索已够好，加 synonym 还可能 **12→10** 回退。应把 synonym 能力用在 **有针对性的 IMP-59 综合征别名** 和 **MedCPT/nominate** 上，而不是再叠一轮泛化 query fanout。

---

## 第 11 轮（手动补回 · JSON/transcript 无留存 → §14.10）

### 用户

如果将检索直接换成纯 dense（MedCPT）排序，有没有机会提升命中？

### 助手

**有机会，但幅度有限，且「纯 dense 全替换 TF-IDF」不如已验证的 sparse+dense 并联。** 下面用 14+8 题上的实测和既有矩阵实验说明。

---

## 1. 结论先行

| 方案 | 8 题 retrieved@24 | 14 题 L1tgt（recall 候选） | 14 题 composite（官方） | 8 题 hard composite |
|---|---:|---:|---:|---:|
| **TF-IDF（现状 A1）** | 7/8 | 12/14 | **0.702** | 0.372 |
| **纯 MedCPT dense**（本次快测） | **7/8** | **12/14** | — | — |
| **Hybrid RRF（A10）** | 7/8 | 0.786×14≈11/14* | **0.719** | **0.398** |

\*官方 A10 L1tgt=0.786（约 11/14），略低于 A1 的 0.857。

- **有提升空间**：主要在 **词面不重叠、语义近邻** 的 chunk（文档 B2/L1/L2 类）。
- **不能指望**：8 题漏斗 retrieved **7/8→8/8**（c1 纯检索仍漏）；也不能单靠换排序解决 **24 条 cap / 40 槽 / mandatory**。
- **不建议纯替换**：文档与快测均显示 **sparse 的精确词匹配仍有价值**；全换 dense 收益不高于 hybrid，还有 **L1 靶回退** 风险。

---

## 2. 纯 dense 在「排序」上确实更强（c1 例证）

对 c1，带 context 的 query：

`differential diagnosis of focal limb neuro deficit. clinical features: apical lung, Horner, arm pain`

| 检索器 | 含 Pancoast 块在 top-30 的排名 |
|---|---|
| TF-IDF | **第 15** |
| MedCPT dense | **第 1** |
| Hybrid RRF | **第 1** |

说明 dense **能**把「presentation ↔ 肺尖肿瘤」这类 **无语义共有词面、有临床语义** 的块提前。

但走完整 `_retrieve_snippets`（4 query + 闭包 + gate + **24 条**）后，c1 在 sparse / dense / hybrid 上 **仍 retrieved=False**。  
瓶颈不在「有没有更相关的块」，而在 **多 query FIFO + 24 截断** 把 rank-1 的块挤出了最终摘要。

---

## 3. 8 题难病集：换 dense **几乎不改变** 片段层命中

本次逐例快测（grounding、无 nominate）：

- gold@24 snippets：**sparse 7/8 = dense 7/8 = hybrid 7/8**
- 唯一稳定漏检：**c1**（三者皆 ✗）

官方 B6 漏斗（A1 vs A10）同样 **retrieved_rate = 7/8**；A10 的增益在 **spotted / xloss**（0.75→0.875，extraction_loss 1→0），不是「多检索到 1 题」。

A10 在 8 题 multilevel 上 composite **0.372→0.398**（mandatory 0.365→0.594 等），来自 **语义召回 + 后续 spotting 链**，不是单纯把 TF-IDF 换成 dense 就多 1 题 retrieved。

---

## 4. 14 题常见集：纯 dense **未优于** TF-IDF

| 指标 | TF-IDF | 纯 dense（快测） | Hybrid A10（官方） |
|---|---:|---:|---:|
| L1 target in candidates | 12/14 | 12/14 | ~11/14 |
| composite | 0.702 | — | **0.719** |
| L1tgt 率 | 0.857 | — | 0.786 ↓ |

14 题 syndrome 已是标准词（hypercalcemia、SIADH…），**TF-IDF 本身 12/14 已够**；纯 dense 未多出命中。

Hybrid 的综合分更高（+1.7pp），但 **L1tgt 从 0.857 降到 0.786** — RRF 重排会 **抬语义近邻、降个别表面词精确命中**。  
⇒ **全替 TF-IDF 会丢掉 sparse 的「精确词面」优势**，净效应不如 **并联**。

---

## 5. 纯 dense 能补什么、补不了什么

**更可能受益（B2 词面/语义缝）**

- 机制表述 vs 标准病名（leukemoid reaction、glucagonoma 等）
- **context query** 驱动的临床语义（c1 单 query 排序 15→1）
- L2 子族、轴可分（A10：L2 0.643→0.714，轴 0.571→0.643）

**仍补不了**

- **c1 类**：即使 dense rank-1，24 条 / 无 nominate 仍端到端失败
- **语料稀疏**：全库仅 1 块含 `pancoast` — dense 不能造 chunk
- **mandatory / 40 槽 / 投影**：检索排序以外的瓶颈
- **纯 disease-name query**（`pancoast syndrome`）：dense 也 **进不了 top-30**（与 TF-IDF 同）

---

## 6. 「纯替换」vs「Hybrid」vs 现状

文档 IMP-53 的设计意图就是：**不替换 TF-IDF，而是第二塔 RRF 并联**：

```
TF-IDF  ──┐
          ├── RRF 融合 → 闭包/metadata 仍走 sparse 侧
MedCPT ──┘
```

实测支持这一选择：

| | 纯 TF-IDF | 纯 dense 替换 | Hybrid（推荐） |
|---|---|---|---|
| 精确词面 / 缩写 | 强 | 弱 | **保留 sparse** |
| 语义近邻 / context | 弱 | 强 | **dense 补漏** |
| 14 题 composite | 0.702 | 未测到更高 | **0.719** |
| 8 题 funnel retrieved | 7/8 | 7/8 | 7/8 |
| 成本 | 低 | 编码 + FAISS | 略高 |

---

## 7. 直接回答

**若把当前检索直接换成纯 dense 排序，有没有机会提升命中？**

- **有机会，但是边际、且分场景**：对 **14 题** 片段/候选层快测 **无增量**（12/14 持平）；对 **综合分/轴/L2/mandatory** hybrid 已证 **+1~2pp**，纯 dense 未证明优于 hybrid。
- **对 8 题 retrieved 7→8**：**基本无机会**（c1 在 dense 下仍漏；需 context 排序 + 24 槽策略或 nominate）。
- **比纯替换更稳的路径**：**MedCPT hybrid RRF**（A10/A11 已验证）> 纯 dense 替换 > 继续纯 TF-IDF。
- **dense 单独不够时**：还需 **context query 权重、grounding 闭包配额、IMP-58 nominate** — 否则 c1 类「排序已改善、摘要仍无 gold」会继续出现。

**一句话**：纯 dense **值得作为第二塔，不值得全替 TF-IDF**；命中机会主要在 **语义缝 + 下游复合指标**，不在 8 题漏斗 retrieved 的 7/8 天花板；生产上应 **hybrid 并联**，而不是 sparse→dense 硬切换。

---

## 第 12 轮（transcript L3435）

### 用户

当前病名排序是否存在受误导风险？提及的频繁度并非与重要度直接相关。是否有针对该问题的措施？

### 助手

**存在误导风险，而且文档里已把它定性为核心缺陷 C4。** 当前「病名排序」在 Spotter 路径上 **主要按语料提及频次累加分**，与临床 **重要度/必须排除（can't-miss）** 并不等价。项目里 **已有多层对冲措施**，但 **未完全消除** 频次主导。

---

## 1. 风险从哪来：频次 ≈ 排序依据

Spotter 对每条 snippet 里 n-gram 命中的病名 **累加权重**：

```247:260:src/agentclinic_tree_dx/knowledge/guideline_branch_source.py
                score = float(h.get("score", 0.0) or 0.0)
                # higher cosine score in this index = LESS similar (L2)? guard: use
                # a bounded positive weight so frequency dominates ties.
                w = 1.0 / (1.0 + max(0.0, score))
                for dz in self._spot(title + ". " + content):
                    ...
                    scored[dz] += w
```

最后 **`sorted(scored)[:max_candidates=40]`** — 谁在多块里重复出现，谁排前面。

CPG 语料里的 **常见病**（MI、urticaria、hypertension、diabetes 等）会出现在大量 **非相关** DDx 列表里；闭包灌池（legacy `closure_mode='pool'`）还会 **放大** 这种重复。文档 §17 **C4** 明确：**「高频无关病占满 40 槽 → 挤掉 rare gold」**。

8 题漏斗里典型 top_cands 就是 MI、urticaria、stroke 等，与 gold 无关 — 这是 **频次误导的实测表现**，不是理论推测。

---

## 2. 重要度 ≠ 频次：为何会「被误导」

| 维度 | 当前 Spotter 排序近似 | 临床 DDx 期望 |
|---|---|---|
| 信号来源 | 块内 **出现次数** × 弱检索权重 | 轴极、must-not-miss、先验、情境 |
| 常见病 | 在多篇 CPG 里 **高频** → 分数高 | 对某综合征可能 **非首要** |
| 罕见 gold | 只出现 1–2 次 → 分数低 | 可能是 **关键鉴别**（Pancoast、glucagonoma） |
| 机制表述 | 常 **不在** DDx 列表字面出现 | 需 nominate / 标志物桥接 |

所以：**排序反映的是「语料共现频率」，不是「对该 presenting syndrome 的临床优先级」。**

---

## 3. 已有针对措施（按作用层）

### A. 减噪 / 别让它进池

| 措施 | 机制 | 状态 |
|---|---|---|
| **`_GENERIC_NAMES` 过滤** | 去掉 cancer、trauma、infection 等过宽族名 | ✅ 默认 |
| **grounding 闭包（IMP-63）** | sibling 块 **不进** Spotter 池，只给 LLM 摘要 | ✅ A1/A9l 主配置 |
| **MMR / extract_k trim** | snippet 多样性裁剪 | ⚠️ 对 **Spotter 池有害** 已证伪；仅宜用于 LLM grounding |

### B. 改竞争规则（族层而非 flat 频次）

| 措施 | 机制 | 状态 |
|---|---|---|
| **IMP-64 本体归族 rollup** | 40 槽在 **族** 层竞争；为 flat top-K 漏掉的族 **保留 ~K/8 席位** | ✅ A2/A9l |
| **最长 n-gram 优先** | 「chronic myeloid leukemia」优先于单字「leukemia」 | ✅ `_spot()` |

### C. 用「重要度下界」覆盖频次

| 措施 | 机制 | 状态 |
|---|---|---|
| **cant_miss 轴极注入（IMP-60）** | 按综合征查表，把 can't-miss 族 **抬到 0.6×max 分数** | ✅ A4/A9l |
| **cant_miss_hard（IMP-56）** | 被注入/提名的实体 **强制保留**，不被 40 槽裁掉 | ✅ A8/A9l |
| **nominate + pathognomonic（IMP-58）** | 读 context **直提名**，不依赖频次 | ✅ A7/A9l（c1 靠此） |
| **WikEM cant_miss 表** | 硬下界 mandatory 方向 | ✅ 部分；与 lab 综合征 **对齐差**（§2.7） |

### D. 第二抽取通道（弱化频次垄断）

| 措施 | 机制 | 状态 |
|---|---|---|
| **recall_llm / spotter+llm（C7）** | LLM 从摘要抽实体，分数按 **LLM 顺序** 非频次 | ✅ A5/A9l |
| **DiseaseNameResolver 展开** | 宽族 → 具体成员（0.9×base），利于投影 | ✅ |

### E. 下游：排序不直接决定分支结构

| 措施 | 机制 |
|---|---|
| **`mandatory_coverage` + `_enforce_mandatory_branches`** | MECE **域** 由 schema/方案 A 定，BranchCreator **不能删 mandatory 域** |
| **UnionAxisMap / 方案 A** | L1 是 **域/轴**，不是 flat 40 病名排序 |
| **IMP-55（待落地）** | 高召回实体投影失败 → residual 域，防静默丢弃 |

---

## 4. 措施实际效果如何（14+8）

| 现象 | 说明 |
|---|---|
| **C4 仍被确认为 spotting 瓶颈** | c13/c18：gold 在片段里、在 vocab 里，仍被 MI/urticaria 挤出 40 槽（改 grounding + LLM 后缓解） |
| **闭包灌池 → grounding** | mandatory 覆盖 **0.54→0.74**（A0→A1），证实频次拥挤来自灌池 |
| **rollup + LLM + nominate** | A9l composite **0.812**；但 8 题 hard 仍 **0.37** — 频次/轴/mandatory 多层问题仍在 |
| **cant_miss 轴极注入** | 14 题矩阵上 **几乎无增益**（表按 WikEM 症状 id，与 hypercalcemia 等不对齐） |

⇒ **有措施、有收益，但没有「按临床重要度重排」的完整解法**；仍是 **频次为主 + 多处补丁**。

---

## 5. 尚未做 / 弱的环节

1. **recall() 内无 LR/urgency/can't-miss 先验重权** — 重要度只在 **注入层** 和 **下游 schema** 体现。  
2. **无「提及次数上限」或 IDF 式 downweight** — 同一 MI 在 20 块出现就加 20 次。  
3. **LLM grounding 仍受 24 条 cap** — 重要但排位靠后的块进不了摘要。  
4. **IMP-51 entry boost** — 结构化入口加权，待办。  
5. **cross-encoder 重排（L12）** — 按 query–chunk 相关性而非频次，P2。

---

## 6. 直接回答

| 问题 | 答案 |
|---|---|
| **病名排序是否有受误导风险？** | **有。** 频次累加 + 40 槽截断 → 常见病系统性靠前（C4）。 |
| **提及频繁度 ≠ 重要度？** | **对。** 代码注释写明 `frequency dominates ties`；临床 important 靠 cant_miss/nominate/schema 补。 |
| **有没有针对措施？** | **有，且是多层的**（见 §3）；核心是 **grounding 减灌池 + rollup 族竞争 + cant_miss/nominate 硬抬 + LLM 第二通道 + 下游 mandatory 兜底**。 |
| **是否已彻底解决？** | **否。** 8 题 hard top_cands 仍常见 MI/stroke；cant_miss 与 lab 综合征未对齐；Spotter 主分数仍是频次。 |

**一句话**：当前排序 **默认信任语料频次**；项目用 **「减池噪声 → 族层竞争 → 临床下界注入 → LLM/提名旁路 → MECE mandatory 下游兜底」** 五段式对冲误导风险，但 **没有在 recall 层做统一的「临床重要度排序模型」** — 那是 C4 仍留在缺陷表里的原因。若要做下一步，优先级通常是：**单实体频次 cap / 族内 representative 只计一次** + **扩展 cant_miss 到 14 题综合征** + **L12 相关性重排**，而不是再加 query。

---

## 第 13 轮（transcript L3440）

### 用户

如果将检索架构由纯RAG改为graph-RAG，是否能从根源解决此类问题（包含病名排序和检索命中）

### 助手

**不能从根源一次性解决。** GraphRAG 能改进 **「入口→相关块→实体」的导航**，但你们现在的两类核心问题——**频次≠重要度（C4）** 和 **机制/词面检索鸿沟（c1）**——有一部分 **Graph 也管不到**，有一部分 **现有轻量图 + IMP 补丁已在局部解决**，全换 GraphRAG **性价比和确定性都不清晰**。

下面按「能解决什么 / 不能解决什么 / 与现状关系 / 建议」说明。

---

## 1. 先对齐：你们说的「纯 RAG」瓶颈其实有两类

| 类型 | 表现 | 根因 |
|---|---|---|
| **A. 检索命中** | TF-IDF 词面够不着；闭包 sibling 进不了 24 条；c1 全库仅 1 块含 Pancoast | query↔chunk **排序/预算**；非「没有图」 |
| **B. 病名排序** | MI、urticaria 在多块重复 → `scored[dz]+=w` 占满 40 槽 | **频次累加** + flat top-40；与图结构无关 |

GraphRAG 主要瞄准 **A 的部分子问题**（跨 chunk 导航、社区摘要）；对 **B** 只有在你 **显式把临床优先级写进图** 时才有用，否则图遍历照样会 **高频节点更大**。

---

## 2. GraphRAG 理论上能改进什么

```
Presenting syndrome
    → [图] 入口 Article / SyndromeEntry 节点
    → [遍历] DDx / red_flag / evaluation 子节点（同 source_id 闭包的上位版）
    → [可选] 社区摘要 / 实体–关系子图
    → 再喂 Spotter / LLM
```

| 能力 | 对命中率的帮助 | 对排序的帮助 |
|---|---|---|
| **Article → Section → Entity 显式边** | ✅ sibling/散落 DDx 不必靠 FIFO 24 条碰运气 | 间接（块更全） |
| **Syndrome 入口节点** | ✅ 缓解「入口块≠DDx 块」（§18 c1 类） | — |
| **跨 chunk 实体图** | ✅ L3 碎片化 | 若边带 **priority/can't-miss** 可减 C4 |
| **社区摘要** | ✅ 控制 token，替代 1668→24 暴力截断 | 摘要质量决定排序，不自动=重要度 |

你们 **已有最小图**：`source_id` 闭包、`syndrome_anchor`、`wiki_links`、`SNOMED is_a`（IMP-64 rollup）。GraphRAG 本质是 **把这些边做全、做可遍历、加摘要层** — 是 **增强**，不是全新范式。

---

## 3. GraphRAG **不能**从根源解决的部分

### 3.1 机制 / 呈现 ↔ 病名（c1）

- 图里若没有边：**「右臂无力 + Horner」→ Pancoast**，遍历到不了。
- 仍需 **pathognomonic、nominate、IMP-59 别名、context 特征** — 这是 **推理/规则层**，不是「有图就能搜到」。
- §19 结论：**curated-free 检索上界 7/8**；c1 四路检索（含 hybrid）皆漏，A9l 靠 **nominate** 才 spotted。

### 3.2 频次 ≠ 重要度（C4）

- 若节点权重 = **共现次数 / 提及频次**，GraphRAG 排序 **仍是频次排序**，MI 仍会是 hub。
- 要根治 C4，图里需要 **边类型或节点属性**：`must_not_miss`、`axis_pole`、`urgency` — 这等于把 **cant_miss + UnionAxisMap** 写进图，**换容器不换语义**。
- 下游 **mandatory_coverage / MECE** 仍要保留；Graph 不能替代 schema 约束。

### 3.3 语料与稀疏

- 全库 1 块含 Pancoast → **无节点可遍历**；Graph 不能造证据。
- §18 **entry+closure oracle 100%** 说明 **数据可达**；当前 loss 在 **工程排序与 cap**，不全在「缺图」。

### 3.4 成本与工程

- 36 万 chunk 建 **实体对齐 + 关系抽取 + 社区索引** 成本高、噪声大（CPG HTML、Recommendations 噪声）。
- IMP-31 生产索引、MedCPT hybrid、grounding 链 **尚未完全合并** — 先 GraphRAG 会 **叠复杂度**，不自动 > hybrid + 闭包配额。

---

## 4. 与现有 IMP 链对照：GraphRAG vs 已验证补丁

| 问题 | 现有措施（已部分验证） | GraphRAG 是否「根源替代」 |
|---|---|---|
| sibling 进不了 24 条 | 两阶段篇内检索 + 闭包配额（**未做**） | ✅ 可设计类似遍历；**等价于做好闭包策略** |
| TF-IDF 词面鸿沟 | MedCPT hybrid（A10 +1.7pp composite） | 语义边/实体链接；**hybrid 更便宜** |
| 40 槽频次拥挤 | grounding + rollup + cant_miss_hard + LLM | 需 **priority 边**；否则 ❌ |
| c1 机制鸿沟 | nominate / pathognomonic | ❌ 仍需 |
| mandatory / 轴 | UnionAxisMap + 轴极注入 | ❌ 仍需 schema 层 |

**A10 hybrid**：composite 0.702→0.719，**未**把 8 题 retrieved 7→8，但修了 B2 语义缝。  
**GraphRAG 若无 priority 模型**，对 **B 类排序** 帮助有限；对 **A 类** 与「篇内图遍历 + 摘要」重叠。

---

## 5. 若上 GraphRAG，怎样才「值得」、怎样会空转

**值得的方向（靶向你们真缺口）**

1. **SyndromeEntry → Article → {DDx, red_flag} 子图**（IMP-31 元数据已有字段）— 替代「expand 1600 块 + FIFO 24」。  
2. **遍历后按边类型排序**：`differential > evaluation`；`can't_miss` 边强制进上下文 — 这才是 **对 C4 的根因级** 做法。  
3. **Presentation 特征节点**（Horner、apical mass）→ 候选 disease — 与 IMP-58 汇合，不是取代。

**会空转的做法**

- 只对 chunk 做 **embedding 社区 + 摘要**，仍 flat 抽实体 + 频次排序 → **C4、c1 照旧**。  
- 用 GraphRAG **替换** hybrid + cant_miss + mandatory — 文档已证 **分区/覆盖** 不能靠 flat 召回 alone。

---

## 6. 直接结论

| 说法 | 判断 |
|---|---|
| GraphRAG 能从根源解决 **检索命中 + 病名排序** | **否**（单换架构不够） |
| 对 **篇内 DDx 导航、token 预算、碎片化** 有帮助 | **是**（与 `source_id` 闭包同向，做得更系统） |
| 对 **频次误导** | **仅当图编码临床优先级**；否则 ❌ |
| 对 **c1 / 机制鸿沟** | **否**；需 nominate / 标志物 / 推理边 |
| 相对 **MedCPT hybrid + grounding + rollup + A9l 栈** | GraphRAG = **增量演进**，非推倒重来 |

**一句话**：GraphRAG **不是**纯 RAG 的完全替代品；它是 **「结构化遍历 +（可选）优先级边 + 摘要」**。要同时碰 **命中** 和 **排序**，需要 **(1) 综合征–文章–DDx 子图遍历** 解决导航，**(2) can't-miss/轴极作为图权重或硬约束** 解决 C4，**(3) nominate/语义检索** 解决 c1 —— 其中 (2)(3) 你们 **已在用非 Graph 方式做**。更务实的路径是：**在 IMP-31 元数据上补「篇内 DDx 子图遍历 + 优先级槽位」**，而不是整体迁移到 GraphRAG 产品栈；若做 GraphRAG，应定义为 **闭包 + mandatory 的图化**，并 **保留 hybrid 与 downstream MECE**，而不是「Graph 一劳永逸」。

---

## 第 14 轮（transcript L3442）

### 用户

| **本体反向归族** | 若「慢性髓性白血病」等具体名被挤出，但其所属 **「髓系肿瘤族」** 完全缺席，则 **保留该族代表** 一名额（不整体用族名替换所有具体名） |
| **机制/标志物直提名** | 不经过检索：若病例 context 写「肺尖肿瘤、Horner」，直接 **写入** 候选「Pancoast tumor」 |
这两个改进的机制表述仍然存在歧义。归族的范围是多大（排名多少的疾病）？标志物提名的依据是什么，消费对象是谁？

### 助手

下面按 **代码实现** 消歧：两处表述里的「族」「保留名额」「直提名」分别指什么、作用在谁身上。

---

## 一、本体反向归族（IMP-64）

### 1.1 报告里容易误解的点

| 误解 | 实际 |
|---|---|
| 「CML 被挤出就用髓系肿瘤 **族名** 替换」 | **不替换**；保留 **具体病名字符串**，只调整 **谁进 top-40** |
| 「整族只留一个代表」 | 仅当该 **SNOMED 超族在 flat top-40 里一个成员都没有** 时，从 **40 名之外** 捞回该族 **分数最高的一名具体病** |
| 「所有候选都先归族再排序」 | 仅当 **spot 后实体数 > 40** 才运行；≤40 时 **整段 rollup 不生效** |

### 1.2 输入范围：归「多大」？

```
Spotter 对所有 snippet 累分 → scored 字典（常 >> 40，如 80–200+ 个病名）
         ↓
仅当 len(scored) > max_candidates(=40) 才调用 _rollup_candidates
         ↓
对 scored 的 **全部 key** 做 SNOMED is_a 分组（不是只对前 40）
```

**族怎么定**（`KBAxisMap._taxonomy_groups`）：

- 在 **全部 spotted 候选** 上，找 SNOMED `is_a` 祖先；
- 只保留覆盖 **2～70% 候选** 的祖先（太宽如 root `neoplasm` 不要）；
- 每个病归到 **最具体** 的可用祖先；
- 最多保留 **`max_domains=6`** 个最大超族组（组名是 SNOMED 概念名，如 myeloid neoplasm 类，**不是** L1 mandatory 域名）。

**孤儿**（`rollup_mode="family+orphan"`，A9l 等）：SNOMED 挂不上的（adhesions、peliosis、foreign body）在分组逻辑里 **各自算一个「单成员族」**，以便也能走「整族缺席→补代表」逻辑。

### 1.3 输出：动多少名额、动哪几名？

```506:511:src/agentclinic_tree_dx/knowledge/guideline_branch_source.py
        n_reserve = min(len(missing_reps), max(1, K // 8))  # cap churn to ~12% of slots
        keep = flat_top[: K - n_reserve] + missing_reps[:n_reserve]
        ...
        for i, m in enumerate(sorted(keep, key=lambda x: -scored[x])):
            out[m] = 2.0 * base - i * 1e-3  # force `keep` into the top-K, own order
```

| 参数 | 值 | 含义 |
|---|---|---|
| `K` | **40** | `max_candidates` |
| `flat_top` | 按频次分 **前 40** | 原 flat 排序结果 |
| `missing_reps` | flat top-40 **一个都没有** 的超族里，按 **全量 scored 分数** 每族取 **最强 1 个具体名** | 不是族名 |
| `n_reserve` | **min(缺席族数, max(1, 40//8)) = 最多 5 槽** | 约 **12%** 槽位可被「补族代表」替换 |
| 被挤掉谁 | **flat_top 中分数最低的 n_reserve 名** | 通常是末尾常见病 |

之后仍 `dict(ranked[:40])`；**不**把 top-40 改成 6 个族名。

**数值例（CML）**：若 `chronic myeloid leukemia` 分数排第 55，但 flat top-40 里 **没有任何** 髓系肿瘤族成员，且该族在 `missing_reps` 里排前 — 可能以 **「chronic myeloid leukemia」这串字** 换掉 top-40 **末尾 1～5 名** 之一；**不会** 在候选里新增一条叫「髓系肿瘤族」的 key。

### 1.4 消费对象

| 消费者 | 用法 |
|---|---|
| **`GuidelineBranchSource.recall()` 返回值** | `{病名字符串: 分数}`，默认 **≤40 项** |
| **评测**（`eval_branch_multilevel`） | 对 `cand1.keys()` 做 **token 家族匹配**（L1tgt / mandatory / 轴可分） |
| **MECE**（`eval_mece_arm`） | 对每个候选名 `project_entity` → L1 域 |
| **BranchCreator** | 实验栈里 recall 与 UnionAxisMap/方案 A 并联；rollup **不直接** 写 `mandatory_coverage` |

rollup **不管** 24 条 LLM 摘要；只改 **40 实体槽** 的组成。

---

## 二、机制 / 标志物直提名（IMP-58 + pathognomonic）

### 2.1 报告里容易误解的点

| 误解 | 实际 |
|---|---|
| 「Horner → 直接写 Pancoast，无依据」 | 依据是 **两张 curated 表 + 子串匹配**，不是 LLM 推断 |
| 「绕过整个 pipeline」 | 只 **绕过 RAG 检索/Spotter 频次**；仍进 `recall()` 的 **scored → top-40** |
| 「与生产 controller 完全同一通路」 | **实验臂**在 `GuidelineBranchSource.recall()`；**生产** `_build_branch_candidates` 另有 **T1 marker → 域投影** 通路（见下） |

### 2.2 触发依据（两类，OR 关系）

**输入文本**（拼接，小写）：

```543:543:src/agentclinic_tree_dx/knowledge/guideline_branch_source.py
        text = f"{syndrome} {syn} {context or ''}".lower()
```

**(a) Pathognomonic 表** — `data/knowledge_raw/pathognomonic_markers.json`（24 条，WHO/教材来源，带 LR+ 注释）

- 规则：`any(term in text for term in marker.terms)` → 追加 `marker.target_diseases`
- c1 例：context 含 `horner syndrome` / `apical lung tumor` 等 → 提名  
  `pancoast tumor`, `superior sulcus tumor`, `apical lung tumor`, `pancoast syndrome`  
  （`highly_specific`，LR+≈25，**不是** pathognomonic 级 100+）

**(b) 机制表** — `mechanism_to_disease.json`，经 `DiseaseNameResolver.nominate_from_text`

- **exact**：normalized 短语 **子串** 出现在 text，且 key **长度 ≥ 6**  
  例：`apical lung tumor` → `pancoast tumor`
- **family_expansions**：text 含某 `any_keywords` → 追加该组 **全部 entities**（最多 **12** 个/次）

**不做的事**：无 embedding、无因果推理；短词不过度触发（key≥6）；`_GENERIC_NAMES` 过滤。

### 2.3 写入规则与「硬保留」

```561:572:src/agentclinic_tree_dx/knowledge/guideline_branch_source.py
            scored[nm] = max(scored.get(nm, 0.0), 1.05 * floor)
            forced.append(nm)
            ...
                            scored[ent] = max(scored.get(ent, 0.0), 0.95 * floor)
                            forced.append(ent)
```

| 项 | 值 |
|---|---|
| `floor` | `0.6 × max(spotted 分数)`，与 IMP-60 轴极注入同量级 |
| 提名分 | **1.05 × floor**（略高于 cant_miss 软注入，低于强 spot 命中） |
| `resolver.expand_to_entities` | 再提名关联具体名，**0.95 × floor** |
| `cant_miss_hard=True`（A8/A9l） | `forced` 里 key 若被 top-40 裁掉 → **强制塞回** |

仍可能：提名分低于前 40 名且 **未开 hard** 时被裁 — A9l 开 hard 后 c1 可 `spotted_not_in_snippets`（检索无、候选有）。

### 2.4 消费对象（两条链）

**链 A — 实验 / `GuidelineBranchSource.recall()`（A7/A9l）**

```
nominate → scored → top-40 dict
    → eval：family_matched(c["l1_target"], cand.keys())
    → eval_mece：project_entity(name, syndrome_entry)
    → recall_llm / Spotter 并集后的 **扁平病名候选池**
```

评测 **只看 key 里是否出现 gold 家族 token**，不看提名分高低。

**链 B — 生产 `controller._build_branch_candidates()`（§23.14）**

```
case 全文 → SyndromeAxisMap.match
    → 对每个 domain 填 candidate_entities_by_domain
    → T1：diagnostic_markers 子串命中 → target_diseases → project_entity → 按 **域** 归档
    → 注入 payload["branch_knowledge"] → BranchCreator LLM
```

与链 A **数据源相近**（marker 表），但 **不调用** `GuidelineBranchSource.recall(nominate=True)`；产出是 **按 L1 域分桶的实体列表**，不是 flat 40 名。

---

## 三、对照表（消歧用）

| 维度 | 本体反向归族 | 机制/标志物直提名 |
|---|---|---|
| **何时运行** | spot 后 **>40** 实体 | `nominate=True` 时每轮 `recall()` |
| **作用范围** | 全量 scored 分组，**最多改 5/40 槽** | 命中几条写几条进 scored |
| **改的是名还是排序** | 只 **换进 top-40 的具体病名** | **新增/抬高** 具体病名分数 |
| **族从哪来** | SNOMED is_a（2–70% 覆盖，≤6 超族） | family_expansions 关键词组（curated） |
| **依据** | 本体结构 + 频次分 | pathognomonic / mechanism **子串表** |
| **主消费者** | `recall()` top-40 → 评测/投影 | `recall()` top-40；生产另路 → **branch_knowledge 按域** |
| **与检索关系** | 检索后、截断前 | **完全不走** snippet 检索 |

---

## 四、建议的报告改写法（去歧义）

**归族** 可写成：

> 当 Spotter 产出 **超过 40** 个病名时，用 SNOMED is_a 检查：若某 **超族**（覆盖 2–70% 候选、最多 6 组）在 **按频次取的前 40 名中无任何成员**，则从 40 名之外取该族 **分数最高的一名具体病**，替换 flat top-40 **末尾最多 5 个槽位**；**不**用族名替换具体名，**≤40** 候选时不生效。

**直提名** 可写成：

> 对 `syndrome + context` 做 **curated 子串匹配**（`pathognomonic_markers.json` 24 条 + `mechanism_to_disease.json`）；命中则将 **target 具体病名** 以 **≥0.6×当前最高分** 写入 `recall()` 的 **40 实体候选 dict**（评测与 MECE 投影消费）；生产 BranchCreator 另经 **T1 marker → project_entity → candidate_entities_by_domain** 按域注入，不依赖 RAG 命中。

若要把这两段直接补进 `BRANCH_GENERATION_PHASE_REPORT.md` 对应小节，可以说明要插入的章节号。

---

## 第 15 轮（transcript L3451）

### 用户

补充进报告和 md 记录（将 IMP-64 / IMP-58 消歧规格写入 `BRANCH_GENERATION_PHASE_REPORT.md`、`BRANCH_KNOWLEDGE_IMPLEMENTATION_PLAN.md`、`CPG_RAG_EXTRACTION.md`）。

### 助手

已将消歧内容写入以下三处：

### 1. `BRANCH_GENERATION_PHASE_REPORT.md`

| 位置 | 内容 |
|---|---|
| **§2.8** | 两行参数表改为精确表述，并指向 §2.9.1 / §2.9.2 |
| **§2.9（新增）** | 完整代码口径：§2.9.1 IMP-64、§2.9.2 IMP-58、§2.9.3 对照表（误解表、输入/输出、消费对象、双消费链） |
| **§2.10** | 原 §2.9「实验臂」顺延 |
| **§6.10 / §6.12** | 各增「实现规格（消歧）」要点块，交叉引用 §2.9 |
| **§13 修订记录** | 2026-06-27 条目 |
| **§14 索引 + §14.12** | 附录交流纪要补入消歧 Q&A |

### 2. `BRANCH_KNOWLEDGE_IMPLEMENTATION_PLAN.md`

- **IMP-58 / IMP-64** 行改为与代码一致的触发条件、写入规则、消费链，并引用 `BRANCH_GENERATION_PHASE_REPORT.md` §2.9。

### 3. `CPG_RAG_EXTRACTION.md`

- 术语表 **覆盖增广 rollup**、**nominate / 提名** 两行同步为精确规格，并交叉引用 §2.9。

**阅读路径建议**：先读 **§2.9**（主规格）→ **§6.10 / §6.12**（案例语境）→ **§14.12**（交流版摘要）。

---

## 第 16 轮（transcript L3465）

### 用户

同时插入最新几轮对话的导出 md 中

### 助手

**2026-06-28 补档完成**（记录丢失事故后手动恢复）：

| 轮次 (L3370+) | 轮次 (全量) | 来源 | 主题 |
|:---:|:---:|---|---|
| **9–11** | **181–183** | **手动补回**（JSON/transcript 无留存） | 同义词缓解 / 同义词 query 证伪 / 纯 dense vs hybrid → **§14.8–§14.10** |
| 12 | 184 | transcript L3435 | C4 频次误导 → §14.11 |
| 13 | 185 | L3440 | GraphRAG → §14.11 末段 |
| 14–16 | 186–188 | L3442+ | IMP-64/58 消歧、报告入档、导出 md |

**文件**：`conversation_export_d6e23c24_dialogue.md`（16 轮）、`conversation_export_d6e23c24_complete_dialogue.md`（188 轮）。

