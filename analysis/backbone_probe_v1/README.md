# 骨干精简探针（零新增 LLM 调用）

Created: 2026-08-06
Scope: 内部。目的是确定"去掉无效部件后还剩什么"。全部测量不产生任何 LLM 调用。

## 1. 投影阶段拿到的候选数（`*/mapper/projections/*.json` 的 `n_leaves`）

| 臂 | 喂给 mapper 的候选数 | option@1 |
|---|---:|---:|
| AB02 flat | 1.00（100/100 例恰好 1） | 0.68 |
| M00 compat | 1.62 / 1.76（max 5） | 0.70 |
| AB01 | 1.68（max 6） | — |
| B02 native | 2.00 | 0.56 |
| B02 SC10（~92 calls） | 2.00 | 0.47 |

四臂 `mapper_mode` 同为 `typed_llm_disagreement_rag`
（AB02: 147 typed_llm + 253 rag_critic；B02 native: 164 + 236）。
只有 smoke run 用 `deterministic_gold_blind`。

⇒ AB02 用**最少**的候选走**同一条**投影链路胜出，排除端点宽松/绑定不公平/多候选广撒网。

## 2. compat（granularity merge + calib）对 AB02 的贡献 = 0

`c3_ab02_v1/annotate/pre_compat_joint/*.json`，比较 `pre_compat` 与 `post_compat_ref`
的 `final_ranking_labels[0].label`：**100/100 例完全相同**，
`gate.triggered = false`，`granularity_path = calib_only`。

原因：AB02 只有 1 个叶，合并无对象。compat 的价值条件于"层次结构产出多叶"。

## 3. AB02 annotate 阶段的调用预算

`c3_ab02_v1/annotate/cache/<case>/`，101 个 case 目录：

| cache | 总条目 | 每例 |
|---|---:|---:|
| `l2_llm_cache.json` | 4480 | 44.4 |
| `bfs_llm_cache.json` | 3902 | 38.6 |
| `granularity_llm_cache.json` | 100 | 1.0 |
| 合计 | 8482 | **84.0** |

`l2_llm_cache` 条目是逐叶逐事实的竞争标注（`fact_rationales` keyed F7..F11）。
84 次调用的最终产出是**一个**标签。`bfs_llm_cache` 38.6/例出现在一个**没有 L1 轴**的臂上。

## 4. 纯检索天花板（`probe_retrieval_only.py`）

复刻 `_collect_recall_rankings` + `_fuse_l2_recall_candidates`（RRF k=60, cap 24），
查询取自冻结树的 root label + salient_findings + case_summary，
**只挂 case_report + cpg 两路，未挂 LLM-DDx 入口**。DA n=100，对自由文本 gold
用 `leaf_match_score >= 0.7`：

| | top1 | top3 | top5 | top10 | top24 |
|---|---:|---:|---:|---:|---:|
| RRF 融合 | 0.04 | 0.15 | 0.26 | 0.35 | **0.46** |
| case_report 单路 | 0.08 | — | 0.22 | — | 0.46 |
| cpg 单路 | 0.06 | — | 0.16 | — | 0.35 |

（`gold_option` 一列作废：DA 的 `Right Option` 是字母，`na in nb` 会假命中。）

与 AB02 逐例结果联合：

- P(AB02 option@1 | gold 在检索池) = 0.70 (32/46)
- P(AB02 option@1 | gold 不在池) = 0.67 (36/54)
- AB02 最终标签能在池中找到匹配：38/100
- P(option@1 | 标签出自池) = 0.68；P(option@1 | 标签不在池) = 0.68

池内容示例（case 100/102/11 的 top3）：
`['hypertension','stroke','lymphadenopathy']`、`['stroke','bullous pemphigoid','vomiting']`、
`['proptosis','ptosis','hypertension']` —— 症状词主导，不是疾病实体。

⇒ **两路知识库召回在 DA 上既不供给答案也不预测成败。**

两次复跑有轻微不一致（top3 0.16/0.15，cpg top24 0.33/0.35），检索层非完全确定性。

## 5. 探针的保真度缺口（必须记录）

DA 实际配置（`scripts/paper/diagnosisarena_l2_pipeline.py:133-144`）为
`l2_branch_generation_mode="per_parent"`、`candidate_budget=24`、`snippet_budget=8`、
`enable_case_report_branch_source=True`、`enable_cpg_branch_source=True`、
**`enable_llm_ddx_branch_entrance=True`**。

本探针复刻的是 case 级资产且**遗漏了第四入口 `_llm_ddx_entities`**——
一次内联 prompt 的 LLM 调用，要求"12-25 个 specific disease entities"，
示例词与 `l2_recall_creator.txt` 完全一致（chronic myeloid leukemia / pancoast tumor /
glucagonoma），以 1/(i+1) 为分数与两路 KB 排序等权 RRF。

`logs/l2_branch_generation_ab_v1` 的 trace 显示真实候选是像样的疾病名
（"acute myeloid leukemia"），与本探针的症状词池反差明显。

⇒ 合理推断：DA 上撑起命名粒度的是**第四入口这一次 LLM DDx 调用**，不是两路知识库。
此推断需要一次带调用的消融确认（摘掉第四入口重跑 DA）。

## 6. 第四入口（LLM DDx）实测：它是真正的召回引擎，且多次调用几乎不增值

统计 `c3_ab02_v1/annotate/cache/<case>/l2_llm_cache.json` 中含 `differentials` 键的响应。

**调用次数**：5.63 次/例（min 0, max 6），不是一次。同一 case 内各次列表平均 19.2 项，
并集 49.1 项，全交集仅 4.9 项（Jaccard 0.12），后续每次新增病名中位数 6。
即多次调用在**覆盖**上确实不冗余。AB02 树本身是 1 个 FLAT 父 + 4.98 个叶，
多次调用源自逐叶展开与 gap-fill 回合。

**但增量不转化**（判据：`leaf_match_score(自由文本 gold, pred) >= 0.7`，n=100）：

| 取法 | 首项命中 | 列表覆盖 gold |
|---|---:|---:|
| 第一次调用 | 0.500 | 0.860 |
| 最后一次调用 | 0.480 | 0.860 |
| 随机取一次（20 次重采样均值） | 0.479 | 0.826 |
| 全部 5.63 次并集 | — | **0.920** |

结论对缓存写入顺序不敏感。多出的约 4.6 次调用只把覆盖从 0.86 抬到 0.92，
且 AB02 最终标签 92/100 出自第一次调用、99/100 出自并集
（对比：两路 KB 检索池只有 38/100 且不预测成败）。

**价值归因**（同判据，同 100 例）：

| 配置 | 调用/例 | lexical@0.7 |
|---|---:|---:|
| 单次 DDx 取第 1 项 | 1 | 0.500 |
| 单次 DDx 的列表覆盖（召回上限） | 1 | 0.860 |
| 5.63 次 DDx 并集覆盖 | 5.6 | 0.920 |
| 完整流水线最终标签 | 84 | **0.640** |

- 相对"取首项"这个平凡选择器，整条流水线的选择环节净赚 **+14pp**（21 例改对、7 例改错）。
- 但它把 0.86 的已召回答案只兑现成 0.64，**留下 22pp 的转化缺口**。
- 逐例：P(option@1 | gold 在首次列表内) = 0.72，P(option@1 | 不在) = 0.43。
- gold 在首次列表中的名次中位数 = 1，rank-1 占比 0.58，top5 0.85。

⇒ 召回不是瓶颈，选择才是。后续工程量应投向选择环节，而不是 BFS / 层次 / compat。

## 7. RareArena 自污染（阻断性）

`data/corpus/case_report_index` 共 77,849 chunk，其中 72,661（93.3%）来源
`case_report:rarearena`；chunk 的 title 即 `Case report: <诊断>`，
`wiki_links` 直接列鉴别集合。

逐字探针（取病历第 21-45 词做连续子串，大小写与标点归一后匹配）：

| 评测集 | 命中检索库 |
|---|---:|
| RareArena `ra_rdc_seq100_v1` | **100 / 100** |
| DiagnosisArena `d2_seq100_v1` | 0 / 100 |
| MedCaseReasoning `mcr_val_seq100_v1` | 0 / 100 |
| MedCaseReasoning `mcr_val_seq100_v2` | 0 / 100 |

该索引只有部署系统查（`run_baseline.py` 只挂 `rag_index` = StatPearls+教科书
493,646 段、`cpg_index` = PMC-OA 等 205,115 段）。

⇒ RA 上的部署-基线差不可用。DA / MCR 不受影响。
