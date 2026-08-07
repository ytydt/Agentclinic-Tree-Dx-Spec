# 论文 TeX 初稿（APHHM）

本目录为对齐 **alignment-preserving** 叙事的英文 TeX draft。

## 当前叙事（2026-07-27 v3）

- 保留 **Recall–Discrimination Dilemma** 作为动机。
- 研究对象为 **APHHM**（Alignment-Preserving Hierarchical Hypothesis Management）：
  病例自适应组织、候选相对证据、等价类压缩、局部后验写回、有界全局解码。
- **四贡献**：组织坐标；等价类压缩；状态一致局部→全局；阶段可归因评价。
- **降级**：P5/anti-anchor = 组件与待验证假设；gap-fill 不作大召回宣称。

## 两条硬口径（v3 新增）

**1. 全表非绑定（no synonym_bind）**

论文所有分数均在**未改动评分接口**下报告，`synonym_bind_repair` 完全不进结果。理由写入 §Interface Alignment：

- bind 对基线增益 ≥ 本方法（B07 +0.05、B13 +0.08 vs Ours +0.02），启用会把「名称规范化覆盖度」混入推理比较；
- 旧实现曾因自 chunk 相似度=1.0 虚高（0.81/0.93 已作废），作为贡献 4 的反面证据写入。

DA 标准分：**0.71 / 0.78**（MRR 0.748），同配置另一冻结 run 为 0.72/0.78，按 run-to-run 区间处理。

**2. 预算匹配基线 = B02-SC10**

原 `B02-flat-compute-matched`（≈9 calls）**不构成真实预算匹配**，已降级为中间档。正式匹配控制为 **B02-SC10**（10 轨自洽 + RRF，≈90 calls/例）：

| 数据集 | native ≈2 calls | proxy ≈9 calls | **SC10 ≈90 calls** |
|---|---:|---:|---:|
| DA @1 | 0.56 | 0.48 | **0.47** |
| OX micro-F1 | 0.495 | 0.479 | **0.487** |
| MCR Acc | 0.17 | 0.17 | **0.15** |

附带发现：OX SC10 的 Interp Acc 由 0.445 崩到 0.044（RRF 保名弃解释），写入正文作为「平面加采样买不到组织结构」的证据。

## 文件

| 文件 | 说明 |
|------|------|
| `main.tex` | 标题、摘要、术语速览 |
| `sections/body.tex` | 正文 |
| `sections/appendix.tex` | 术语表、扩展表、伦理 |
| `references.bib` | 参考文献（部分占位） |

## 编译

```bash
cd paper
latexmk -pdf main.tex
```

## 数据来源

`runs/paper_v1/diagnosisarena_d2_seq100_baselines_summary.md`（v10，§2 无 bind 主表、§4.1 SC10）、`b02_compute_matched_sc10_three_datasets.md`、各集专表。
