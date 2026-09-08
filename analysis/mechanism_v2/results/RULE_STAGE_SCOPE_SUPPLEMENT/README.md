# 阶段、适用范围与分支补充（任务2）

入口：[REPORT.md](REPORT.md)。本目录补充既有 redesign 的操作语义，不替换生产实现。

- [完整语义合同](SEMANTIC_SUPPLEMENT.md)
- [与上一设计的具体差量](PRIOR_DESIGN_DELTA.md)
- [合成规则与分支](supplemental_examples.json)
- [验收向量](supplemental_vectors.json)
- [独立复核](INDEPENDENT_REVIEW.md)

从仓库根目录运行：

```bash
python analysis/mechanism_v2/results/RULE_STAGE_SCOPE_SUPPLEMENT/validate_supplement.py
```

[supplement_validation.json](supplement_validation.json)记录有限夹具结果。全部示例均为 synthetic，临床使用授权为 false；通过不证明源文抽取保真或临床有效性。

实现缺陷与技术方案单独位于 [任务1](../IMPLEMENTATION_DEFECT_AUDIT/README.md)。
