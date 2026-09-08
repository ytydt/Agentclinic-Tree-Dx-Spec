# 实现缺陷审计（任务1）

入口：[REPORT.md](REPORT.md)。冻结输入：`cursor4@bbc036e8`。本目录交付真实代码反例、逐项机制、纯代码/语义/设计边界及修复方案，未改生产算法。

- [统一缺陷索引](defect_catalog.md) / [机器账本](defect_registry.json)
- [修复工作包](REPAIR_PLAN.md)
- [针对语义绑定的新技术调研](semantic_binding_research.md)
- [全部混合缺陷的技术覆盖矩阵](SEMANTIC_REPAIR_MATRIX.md)
- [已有设计覆盖与内部KG复用](PRIOR_COVERAGE_REVIEW.md)
- [独立复核](INDEPENDENT_REVIEW.md)

从仓库根目录复现：

```bash
python analysis/mechanism_v2/results/IMPLEMENTATION_DEFECT_AUDIT/reproduce_identity_defects.py
python analysis/mechanism_v2/results/IMPLEMENTATION_DEFECT_AUDIT/reproduce_engine_defects.py
python analysis/mechanism_v2/results/IMPLEMENTATION_DEFECT_AUDIT/reproduce_upstream_defects.py
python analysis/mechanism_v2/results/IMPLEMENTATION_DEFECT_AUDIT/reproduce_auxiliary_defects.py
python analysis/mechanism_v2/results/IMPLEMENTATION_DEFECT_AUDIT/build_prior_coverage.py
python analysis/mechanism_v2/results/IMPLEMENTATION_DEFECT_AUDIT/build_delivery.py
```

复现依赖已有冻结文本缓存/44个重放包和本地 Python 科学库，不下载语料索引或模型，不请求 OpenRouter。通过表示所述旧行为可复现，不表示已经修复。详细脚本范围以各结果的 evidence/limits 为准。

阶段、适用范围和分支合同单独位于 [任务2](../RULE_STAGE_SCOPE_SUPPLEMENT/README.md)。
