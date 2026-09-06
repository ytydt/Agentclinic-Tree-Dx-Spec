# 任务二：忠实规则提取文献调研

主入口：[REPORT.md](REPORT.md)。检索/核验日期：2026-09-05—06。

- 四份 `*_review.md`：现代FOL、经典语义解析、临床LLM、临床标准。
- 四份 `*_sources.json` 与 `*_search_log.json`：来源、版本、方法和保证边界、实际检索和失败记录。
- [study_matrix.json](study_matrix.json)：35条研究/标准记录的统一矩阵，不是35篇独立实验论文。
- [LITERATURE_INDEPENDENT_REVIEW.md](LITERATURE_INDEPENDENT_REVIEW.md)、[CLINICAL_REVIEW_CHECK.md](CLINICAL_REVIEW_CHECK.md)：独立核验及纠正。
- [delivery_validation.json](delivery_validation.json)：产物一致性检查；不代表复现外部系统。

从仓库根目录重新合并矩阵：

```bash
python analysis/mechanism_v2/results/FAITHFUL_RULE_EXTRACTION_LITERATURE_REVIEW/build_study_matrix.py
```

未运行外部研究系统，没有新LLM调用。原论文/规范仍由其作者或官方站点提供；这里保存审读、引用和核验账本。

相邻任务：[一：差量审计](../V2_INDEX_DIFFERENTIAL_AUDIT/REPORT.md) · [三：改进设计](../RULE_EXTRACTION_EXECUTION_REDESIGN/REPORT.md)。
