# B02 compute-matched：与主方法的区别，以及预算匹配如何实现

状态：2026-07-27（**三数据集均已跑通，G5 PASS**）  
对应臂：`B02-flat-compute-matched`  
协议：`structural_proxy_v1`  
结果汇总：

| 数据集 | 汇总 | G5 |
|---|---|---|
| DA `d2_seq100` | [`b02_compute_matched_summary.md`](b02_compute_matched_summary.md) | PASS |
| OX `ox_seq100` | [`../open_xddx_b02_compute_matched_v1/b02_compute_matched_summary.md`](../open_xddx_b02_compute_matched_v1/b02_compute_matched_summary.md) | PASS |
| MCR `mcr_val_seq100` | [`../medcasereasoning_b02_compute_matched_v1/b02_compute_matched_summary.md`](../medcasereasoning_b02_compute_matched_v1/b02_compute_matched_summary.md) | PASS |

---

## 1. 一句话对照

| | **主方法（层级诊断管线）** | **B02 compute-matched（平面对照）** |
|---|---|---|
| 核心想法 | 先建病例自适应 L1 家族，再在家族内做 L2 召回/生成与联合排序 | **不做 L1**；同一共享 KB 上固定查询检索 → 生成候选 → 平面 evidence → listwise rerank |
| 控制目的 | 论文主系统 | 回答 RQ4：在**相近计算预算**下，收益是否仍来自层级机制，而非“多花了算力” |
| 读什么 | vignette + 自建树/证据/后验 | vignette + 共享索引 + **仅数值预算上限**（不读树候选/推理/金标） |

---

## 2. 与主方法的主要区别

### 2.1 算法结构（本质差异）

主方法（当前 DA 正式对照配置：`compat_parallel` + 可选 synonym_bind；OX 另有锁定预算与 live 后验写回）大致是：

1. **病例自适应 L1**：把鉴别空间组织成互斥家族（非固定 ICD 表）；
2. **家族条件化 L2**：在各 L1 下召回/生成叶疾病，并做语义压缩与父子一致性；
3. **证据选择与后验更新**：有界证据预算（如 F6 / OX 锁定 L1=4 等）条件下化信念；
4. **联合/兼容排序**：在短列表或 compat 路径上得到最终 Top-k，再经 Mapper / 正式评测。

B02 compute-matched **刻意去掉层级**：

1. **无 L1 / 无家族 / 无 planner**：查询来自固定模板（可按预算加长），不是主方法的检索规划或家族条件查询；
2. **平面候选池**：按预算生成约 `n_leaf` 条疾病名，不维护父子树；
3. **平面 evidence 轮**：对整表候选做 support/oppose 式重排（`FLAT_EVIDENCE_MATRIX`），轮数对齐主方法的 `n_l1`，但**不创建家族**；
4. **一次 listwise rerank** 输出有序 Top-2（DA）或 Top-k（若迁移到 OX/MCR）。

因此：两边可以共享 **backbone、语料索引、输出协议与评分器**；不能共享的是 **“是否用病例自适应层级分解候选空间”**——这正是 B02 要隔离的变量。

### 2.2 信息流对比

```text
主方法:
  vignette
    → 自适应 L1 家族
    → 每家族 L2 召回/生成 + 证据条件化
    → 联合/compat 排序 → Top-k
    → Mapper / 正式指标

B02 matched:
  vignette
    → 固定查询 × 共享 rag/cpg 索引（调用数受 schedule 约束）
    → 批量生成平面候选（目标长度 ≈ 主方法叶数）
    → 平面 evidence 轮（次数 ≈ 主方法 L1 数）
    → listwise rerank → Top-2
    → 同一 Mapper
```

### 2.3 同与不同（公平性边界）

| 维度 | 是否对齐 | 说明 |
|---|---|---|
| 模型 | 是 | 同 API backbone（Llama-3.3-70B-Instruct） |
| 知识库 | 是 | 同 `rag_index` + `cpg_index` |
| 输入 | 是 | 开放 vignette，无 Options 泄漏 |
| 输出/评分（DA） | 是 | 有序 Top-2 + `RelationAwareAnswerMapper` |
| 层级结构 | **否** | 主方法有 L1/L2；B02 禁止 |
| 候选内容 | **否** | B02 **不得**复制主方法叶标签列表 |
| 真实 token 账本 | **未对齐** | 主方法尚无逐调用 token ledger；当前用结构代理（见 §3） |

### 2.4 与 `B02-flat-matched-rerank`（native）的区别

同名族下还有 **native** 臂（历史主表中的 `B02-flat-matched-rerank`）：

| | native | compute-matched |
|---|---|---|
| 检索 | 固定 4 query，`max_chunks=12` | 按病例 schedule：`n_queries`、`max_chunks` |
| LLM | 固定 2 次（候选 + rerank） | 均值约 9.24 次（候选批 + fill + evidence + rerank） |
| 候选数 | 固定约 5 | 对齐主方法叶数（均值约 17.8） |
| 设计意图 | 轻量平面 RAG 对照 | **计算预算匹配**后的公平平面对照 |

点估计（native → matched）：

| 数据集 | 主指标 | native | matched |
|---|---|---:|---:|
| DA | Mapper @1 | 0.56 | 0.48 |
| OX | micro-F1 | 0.495 | 0.479 |
| MCR | Acc (single traj.) | 0.17 | 0.17 |

匹配更高预算后平面法未变强（OX/DA 略降；MCR 持平）——这正是 matched 臂要提供的叙事材料。

---

## 3. 预算匹配如何实现

### 3.1 目标（论文 G5 / I05）

计划要求 B02 逐病例匹配主方法的：

- LLM calls  
- retrieval calls  
- retrieval snippets（或等价 snippet 预算）  
- unique candidates  

相对偏差 ≤ **5%**；B02 **只读预算上限**，不读主方法预测与金标。

因主方法 run **尚未写出正式 token/call 账本**，本实现采用可审计的 **结构代理协议** `structural_proxy_v1`（token 维标记为 `deferred_no_m00_ledger`）。

### 3.2 三步流水线

```text
[1] build_budget_schedule.py
      读主方法 shared_trees（仅结构字段）
      → 写出 per-case 数值 schedule.jsonl

[2] run_baseline.py --arms B02-flat-compute-matched --budget-mode matched
      每例只注入 schedule 行（llm/retrieval/候选上限）
      → run_b02 按上限消耗算力并写 cost + budget_mismatch

[3] audit_b02_budget_match.py
      核对实际 vs 目标，G5 门控
```

入口脚本：

- DA：`scripts/paper/run_b02_compute_matched_d2_seq100.sh`
- OX/MCR：`scripts/paper/run_b02_compute_matched_ox_mcr.sh`（默认 `WORKERS=50`）

### 3.3 Schedule 怎么从树上算出来

数据源（DA）：

- `logs/diagnosisarena_d2_m01_v1/pilot24_compat_b12_live_v1/shared_trees`
- `logs/diagnosisarena_d2_m01_v1/remain76_compat_b12_live_v1/shared_trees`

对每例树状态只抽取：

| 树字段 | 含义 |
|---|---|
| `n_l1` | `level==1` 节点数（家族数） |
| `n_leaf` | 无 children 的叶节点数 |
| `n_static` | `n_static_evidence_items`（静证条数） |

映射公式（`structural_proxy_v1`）：

```text
unique_candidates = n_leaf
retrieval_snippets = clamp(n_static, 8, 24)
n_queries          = clamp(ceil(retrieval_snippets / 3), 2, 8)
retrieval_calls    = n_queries × 2          # rag_index + cpg_index 各一次
cand_batches       = ceil(unique_candidates / 8)
llm_calls          = cand_batches + 1(fill) + n_l1 + 1(rerank)
evidence_rounds    = n_l1                   # 平面轮，不建家族
```

DA `d2_seq100` 上 schedule 均值（本 run）：

| 维度 | 均值 |
|---|---:|
| llm_calls | 9.24 |
| retrieval_calls | 12.02 |
| retrieval_snippets | 17.18 |
| unique_candidates | 17.8 |

产物：

- `configs/paper_experiments/paper_v1_budget_schedule_diagnosisarena.jsonl`
- 同目录 `.meta.json`（含 `schedule_sha256`、树根路径）

### 3.4 B02 运行时如何“花掉”这些预算

实现：`scripts/paper/baseline_arms.py` → `run_b02`（`budget_mode=matched` 或臂名 `B02-flat-compute-matched`）

1. **检索**：`_fixed_manifestation_queries(..., max_queries=n_queries)`，双索引 `per_query_per_index=3`，截断到 `max_chunks`；  
2. **候选**：按批（默认 8）生成/扩展，目标凑满 `unique_candidates`；优先占满候选槽，不足则从 evidence 预算偷轮 fill；  
3. **平面 evidence**：最多 `evidence_rounds`（≈`n_l1`）次整表重排，再用剩余 LLM 预算 pad，**禁止**生成 L1；  
4. **Rerank**：最后 1 次 listwise，输出 Top-2；  
5. **记账**：`cost` 写入实际 `llm_calls / retrieval_* / unique_candidates`，并与 `budget_target` 算 `budget_mismatch`。

硬约束：schedule 与 runner **都不包含**主方法的叶标签、后验或金标选项。

### 3.5 G5 核验与已声明豁免

审计：`scripts/paper/audit_b02_budget_match.py`  
本 run：[`b02_compute_matched_budget_audit.md`](b02_compute_matched_budget_audit.md) → **G5 PASS**（match_rate=1.0）

相对误差阈值 **5%**，另有两点写死豁免（须在文中声明，不得静默）：

| 豁免 | 条件 | 含义 |
|---|---|---|
| `abs_slack_1` | `\|act−tgt\|≤1`（仅 unique_candidates） | 离散名单长度的 ±1 噪声 |
| `llm_diversity_cap` | LLM 预算用尽且 `act/tgt≥0.80` | 模型无法再吐出足够不重复病名，不算“少花算力” |
| `corpus_unique_cap` | 融合唯一 chunk 已耗尽导致 snippet 略少 | 语料去重上限，非故意减检索 |

本 clean full rerun 中 `llm_diversity_cap`：`diagnosisarena__000249`。

### 3.6 与计划全文 I05 的差距（诚实边界）

| 计划项 | 当前状态 |
|---|---|
| 主方法逐调用 token ledger | **未实现** → token 匹配 deferred |
| 从 M00 `cost.json` 导出 schedule | 改为从 **shared_trees 结构**导出 |
| 偏差 ≤5% | **已对四维代理指标做到**（含上表豁免） |
| native + matched 双报 | **已报**（§2.4 / 结果汇总） |

待主方法补齐正式账本后，应用同一 wrapper 换成 `official_ledger_v1`，无需改 B02 的“平面、无 L1”语义。

---

## 4. 代码与产物索引

| 角色 | 路径 |
|---|---|
| 建 schedule | `scripts/paper/build_budget_schedule.py` |
| 臂实现 | `scripts/paper/baseline_arms.py`（`run_b02`） |
| Runner | `scripts/paper/run_baseline.py`（`--budget-mode matched`） |
| 审计 | `scripts/paper/audit_b02_budget_match.py` |
| 一键 DA | `scripts/paper/run_b02_compute_matched_d2_seq100.sh` |
| 一键 OX/MCR | `scripts/paper/run_b02_compute_matched_ox_mcr.sh` |
| Schedule | `configs/paper_experiments/paper_v1_budget_schedule_{diagnosisarena,open_xddx,medcasereasoning}.jsonl` |
| DA / OX / MCR runs | `runs/paper_v1/{diagnosisarena,open_xddx,medcasereasoning}_b02_compute_matched_v1/` |

---

## 5. 写作时建议表述

- **可以说**：在共享模型与知识库下，B02 是无层级的平面 retrieve–generate–rerank；其 matched 变体按主方法树结构代理的调用/检索/候选预算逐例对齐（≤5%），用于检验层级收益是否独立于额外计算。  
- **不要说**：B02 复现了主方法内部模块，或已完成与主方法逐 token 的严格账本对齐。  
- **主表建议**：强度比较可并列 native；**RQ4 / 公平主检验报 matched**（@1=0.48 vs 主方法 Mapper @1=0.81）。
