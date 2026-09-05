# v2规则抽取能力边界审计

主报告：[REPORT.md](REPORT.md)。本目录补齐2026-09-05上一轮机制审计缺少的概率样本、来源规则分母、输出单元分母与严格无源虚构判定。

核心路径：

1. `PROTOCOL.md` / `PROTOCOL_CLARIFICATIONS.md`：冻结抽样与语义口径。
2. `source_only_pack_*` → `source_inventory_*.frozen.json` → `source_reveal_pack_*` → `source_matches_*`：来源先行与双臂对齐。
3. `output_pack_*` → `output_adjudication_*` → `cross_review_output_*`：输出全文审核及交叉复审。
4. `source_review_overrides.json` / `output_review_overrides.json`：保留初判的修订记录。
5. `source_rule_results.json` / `output_unit_results.json` / `census_metrics.json`：最终逐项判定及加权指标。
6. `ERROR_TAXONOMY_AND_CAUSAL_MAP.md` / `GROUP_SEMANTIC_CASEBOOK.md`：错误分类、原因边界、8例AST与反模型。
7. `METHODS_REVIEW.md` / `FINAL_*REVIEW.md` / `validation.json`：方法及交付复核。

可在仓库根目录依次执行以下文件（均在本目录），无需LLM调用或下载LFS：

```text
aggregate_census.py
summarize_error_dimensions.py
structural_census.py
check_group_semantic_countermodels.py
build_report.py
validate_census.py
```

用Python运行。`build_samples.py`会重建固定样本；哈希不变已验证。`build_inventory_*`、`build_matches_*`、`write_output_adjudication_*`是已完成的手工式审阅序列化脚本，不是新的独立审阅模型；通常无需重跑，冻结文件与初判文件应保留。所有语义判断仍需未来人类临床审阅验证。
