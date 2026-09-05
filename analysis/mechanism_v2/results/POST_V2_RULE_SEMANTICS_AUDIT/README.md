# v2规则语义再审计：交付与复现

先读 [REPORT.md](REPORT.md)。该报告修订 `RAG_GUIDELINE_ORACLE_CEILING_LOCAL/MECHANICAL_RULE_TRIAL_REPORT.md` §22–35的当前解释，冻结输入来自 `cursor4@96938384655e486e8eddc0a0e7c6901de9e57aa4`。

本目录是**审计代码和结果**，没有修改或替换生产抽取/规则执行器。模型API调用0次，LFS实际对象下载0个。已有原始抽取、完整检索窗口和embedding缓存足以完成重放。所有中间结果均随本目录提交；输入大文件仍引用仓库原路径。

## 阅读和证据入口

| 对象 | 报告 | 机器可审查账本/结果 |
|---|---|---|
| 综合结论 | `REPORT.md` | `provenance_summary.json`、`validation.json` |
| 例74 | `case74_audit.md` | `case74_manual_adjudication.json/.csv`、`case74_pipeline_trace.json`、`case74_targeted_ablation.json`、`case74_raw_cache_audit.json` |
| 其他病例、11题、组阶段 | `cohort_audit.md` | `cohort_manual_ledger.json`、`cohort_gold_membership.json`、`cohort_metrics.json`、`cohort_group_stages.json`、8份`cohort_trace_*` |
| 测量指标 | `measurement_audit.md` | `measurement_census.json`、`measurement_counterexamples.json`、`v2_criteria_manual_screen.json`、`v2_proxy_paired_flips.json` |
| 执行器缺陷 | `engine_audit.md` | `engine_repro_results.json`：27个合成见证 |
| 来源与缓存 | `source_and_provenance_audit.md` | `extraction_job_manifest.jsonl`、`passage_manifest.jsonl`、`normalisation_changes.json`、`source_parse_repro.json` |
| 参照语义 | `semantic_contract.md` | `reference_semantics_results.json`：40项检查 |

所有断言索引是**各case的assertions数组零起点**。`extraction_job_manifest.jsonl` 的 `[assertion_start, assertion_stop_exclusive)` 可回查原始cache ID和passage哈希。gid必须连同索引版本使用，不可跨old/v2直接比较。

`case74_manual_adjudication`为26个目的性审计单元，引用91条不同的文件+行记录及9个来源gid；`cohort_manual_ledger`为另外4例的8个事件；`measurement_counterexamples`为19个有意选取的反例。它们存在重叠，不相加为独立样本量，也不是总体错误率估计。41条trigger审核覆盖的是旧指标选中片段，并不覆盖所有实际诊断规则。

## 运行环境和输入

Python 3及NumPy。脚本只依赖标准库/NumPy及冻结仓库中的Python模块；不安装模型，不调用OpenRouter，不自动下载embedding。

输入包括：

- `RAG_GUIDELINE_ORACLE_CEILING_LOCAL/trial_tasks_11_all4.json`，四份`trial_extraction_x2_*clean_groups*.json`，两份`trial_retrieval_x2_*.json`，原始`trial_extraction_cache/`。
- 历史`trial_retrieval_k30.json`、`trial_engine_x2*.json`、`corpus_lift_table_all4.json`、`join_embeddings.npz`以及同目录已有统计源。
- 原生产模块：`analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL/`。
- 来源结构复现额外读取`data/corpus/statpearls/statpearls_NBK430685/article-{24945,29656}.nxml`、`scripts/build_statpearls_corpus.py`。例74原文证据来自已冻结窗口，并额外核对`data/cpg/raw/pmc_oa/bioc-pmc10971616.json`及对应text文件。

新检出可使用`GIT_LFS_SKIP_SMUDGE=1`，只取上述路径；无需取`ceiling_trial_index_v2/dense.npy`或`meta.jsonl`等大索引。输入SHA256见`provenance_summary.json`、`cohort_metrics.json`和各反例结果。

## 复现命令

以下从仓库根运行，输出只写本审计目录。`case74_replay.py`和`cohort_recompute.py`需若干分钟；纯性质测试较快。省略API凭据，脚本不需要它们。

```bash
python analysis/mechanism_v2/results/POST_V2_RULE_SEMANTICS_AUDIT/provenance_audit.py
python analysis/mechanism_v2/results/POST_V2_RULE_SEMANTICS_AUDIT/source_parse_repro.py
python analysis/mechanism_v2/results/POST_V2_RULE_SEMANTICS_AUDIT/engine_repro.py
python analysis/mechanism_v2/results/POST_V2_RULE_SEMANTICS_AUDIT/reference_semantics.py
python analysis/mechanism_v2/results/POST_V2_RULE_SEMANTICS_AUDIT/measurement_reaudit.py
python analysis/mechanism_v2/results/POST_V2_RULE_SEMANTICS_AUDIT/curate_measurement_examples.py
python analysis/mechanism_v2/results/POST_V2_RULE_SEMANTICS_AUDIT/cohort_recompute.py --replay
python analysis/mechanism_v2/results/POST_V2_RULE_SEMANTICS_AUDIT/cohort_group_stages.py
python analysis/mechanism_v2/results/POST_V2_RULE_SEMANTICS_AUDIT/build_cohort_manual_ledger.py
python analysis/mechanism_v2/results/POST_V2_RULE_SEMANTICS_AUDIT/case74_replay.py
python analysis/mechanism_v2/results/POST_V2_RULE_SEMANTICS_AUDIT/case74_raw_cache_audit.py
python analysis/mechanism_v2/results/POST_V2_RULE_SEMANTICS_AUDIT/case74_targeted_ablation.py
python analysis/mechanism_v2/results/POST_V2_RULE_SEMANTICS_AUDIT/case74_build_adjudication.py
python analysis/mechanism_v2/results/POST_V2_RULE_SEMANTICS_AUDIT/validate_audit.py
```

注意：人工式语义判定是脚本内冻结的审计标签；重新生成JSON是复现这些判定与证据连接，不是第二名审阅者重新独立判断。合成执行反例配置用来隔离缺陷，不等同B1+S7临床配置。F7来源切换的8次重放与例74靶向删除是有限确定性干预，不代表真实临床效用改善。

`artifact_manifest.json`记录交付文件SHA256（不包含自身）；`validation.json`为交付时的结构/数值/指针核验结果。重新运行脚本可能更新运行HEAD记录或格式，若形成新版本应保留原manifest进行差异核验。
