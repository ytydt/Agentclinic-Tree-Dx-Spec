# 任务三：抽取器与执行器改进设计

主入口：[REPORT.md](REPORT.md)。设计基于 `cursor4@6fa8fd7a`，尚未部署，也未声称提高临床性能。

| 产物 | 用途 |
|---|---|
| [EXTRACTION_PROTOCOL.md](EXTRACTION_PROTOCOL.md) | 分阶段抽取、编译和源文核验模板 |
| [SEMANTIC_CONTRACT.md](SEMANTIC_CONTRACT.md) | 一等规则、递归表达式、量化域、方向和动作合同 |
| [ir_examples.json](ir_examples.json)、[acceptance_vectors.json](acceptance_vectors.json) | 机器可读表示与有限区分输入 |
| [MIGRATION_MAP.md](MIGRATION_MAP.md)、[migration_matrix.json](migration_matrix.json) | 具体函数、证据和兼容迁移点 |
| [RESEARCH_ROADMAP.md](RESEARCH_ROADMAP.md)、[experiment_matrix.json](experiment_matrix.json) | 分层实验、对照、终点、预算和停止条件 |
| [DESIGN_INDEPENDENT_REVIEW.md](DESIGN_INDEPENDENT_REVIEW.md) | 独立设计复核及未验证边界 |

运行有限示例检查：

```bash
python analysis/mechanism_v2/results/RULE_EXTRACTION_EXECUTION_REDESIGN/validate_contract_examples.py
```

检查器只验证设计产物/受限合成语义片段，不是生产引擎，不证明原文或临床忠实性。11病例及既往来源样本均为开发材料，泛化收益必须由后续独立实验检验。

相邻任务：[一：差量审计](../V2_INDEX_DIFFERENTIAL_AUDIT/REPORT.md) · [二：文献调研](../FAITHFUL_RULE_EXTRACTION_LITERATURE_REVIEW/REPORT.md)。
