# 内部备忘录：RareArena 评测线下线

Created: 2026-08-06
Scope: **不得写入 `paper_aaai/` 下任何 `.tex`。** 下一版方法与评测范围明确排除 RareArena。

## 判定

部署系统 L2 召回层使用 `data/corpus/case_report_index`（77,849 chunks），其中
**72,661（93.3%）** 来源标记为 `case_report:rarearena`。每个 chunk 的 title 形如
`Case report: <诊断>`，`wiki_links` 字段直接列出鉴别诊断集合。

对评测子集 `ra_rdc_seq100_v1` 的 100 例病历做逐字探针（取第 21–45 词做连续子串，
大小写与标点归一后匹配索引正文）：

| 评测集 | 命中 `case_report_index` |
|---|---:|
| RareArena `ra_rdc_seq100_v1` | **100 / 100** |
| DiagnosisArena `d2_seq100_v1` | 0 / 100 |
| MedCaseReasoning `mcr_val_seq100_v1` | 0 / 100 |
| MedCaseReasoning `mcr_val_seq100_v2` | 0 / 100 |

该索引**只有部署系统会查**。基线 `run_baseline.py` 只挂 `rag_index`
（StatPearls+教科书）与 `cpg_index`（PMC-OA 等）。因此 RA 上的任何部署–基线差值
在机制上不可解释为方法优势，属自污染。

## 处置

1. 下一版论文评测范围限定为 **DA + MCR**（一次性诊断问答）。
2. RA 相关已刊数字与分析不进入下一版主张；既有补充材料中若出现 RA 行，改稿时删除或降为附录历史记录并加污染说明（本轮主文已锁，不改）。
3. 骨干算法削减计划（`backbone_v1`）**不跑 RA**。
4. 若未来要恢复 RA：必须先从 `case_report_index` 剔除评测例（及同源全文）并重跑全部部署臂；在此之前 RA 结论一律视为无效。

## 证据位置

- 探针记录：`analysis/backbone_probe_v1/README.md` §6（及对话中的 100/100 测量）
- 索引配置：`data/corpus/case_report_index/config.json`
- 评测子集：`data/benchmarks/rarearena/subsets/ra_rdc_seq100_v1/`
