# 论文 TeX 初稿（APHHM）

本目录为对齐 **alignment-preserving** 叙事的英文 TeX draft。

## 当前叙事（2026-07-29 consistency revision）

- 保留 **Recall–Discrimination Dilemma** 作为动机。
- 研究对象为 **APHHM**（Alignment-Preserving Hierarchical Hypothesis Management）：
  病例自适应组织、候选相对证据、等价类压缩、局部后验写回、有界全局解码。
- **核心贡献**：跨阶段 concept/state/evaluation consistency；APHHM 是该原则的一种实现。
- **证据边界**：DA 为 axis-conditioned pipeline effect；MCR partition randomization 不替代病例抽样不确定性；write-back 直接证据限于 OX。
- **降级**：P5/anti-anchor = 组件与待验证假设；gap-fill 不作大召回宣称。

## 两条硬口径（v3 新增）

**1. 全表非绑定（no synonym_bind）**

论文所有分数均在**未改动评分接口**下报告，`synonym_bind_repair` 完全不进结果。理由写入 §Interface Alignment：

- bind 对基线增益 ≥ 本方法（B07 +0.05、B13 +0.08 vs Ours +0.02），启用会把「名称规范化覆盖度」混入推理比较；
- 旧实现曾因自 chunk 相似度=1.0 虚高（0.81/0.93 已作废），作为贡献 4 的反面证据写入。

DA 标准分：**0.71 / 0.78**（MRR 0.748），同配置另一冻结 run 为 0.72/0.78，按 run-to-run 区间处理。

**2. 近似调用次数控制 = B02-SC10**

原 `B02-flat-compute-matched`（≈9 calls）**不构成真实预算匹配**，已降级为中间档。B02-SC10（10 轨自洽 + RRF，≈90 calls/例）仅作为 approximately call-count-matched control，不宣称 token、latency 或 cost parity：

| 数据集 | native ≈2 calls | proxy ≈9 calls | **SC10 ≈90 calls** |
|---|---:|---:|---:|
| DA @1 | 0.56 | 0.48 | **0.47** |
| OX micro-F1 | 0.495 | 0.479 | **0.487** |
| MCR Acc | 0.17 | 0.17 | **0.15** |

附带发现：OX SC10 的 Interp Acc 由 0.445 崩到 0.044（RRF 保名弃解释），写入正文作为「平面加采样买不到组织结构」的证据。

## 文件

| 文件 | 说明 |
|------|------|
| `main.tex` | AAAI 2027 匿名投稿主文源码（正文与伦理声明；正文页限制内） |
| `SupplementaryMaterial.tex` | 独立补充材料（扩展基线表与次级诊断分析） |
| `references.bib` | 参考文献（部分占位） |
| `aaai2027.sty` / `aaai2027.bst` | Author Kit 原版样式文件，未修改 |
| `figures/` | 已停用的早期 matplotlib 流程图产物，不参与编译，可在打包时删除 |

## 图件（2026-07-29 可视化改版）

三张图全部以 TikZ 内联在 `main.tex`，不依赖外部图片，便于匿名投稿与复现：

| 图 | 内容 | 替换了什么 |
|---|---|---|
| 图 1 | 三阶段流程 + 共享信念状态 + 三条一致性要求（各自标在可被违反的位置） | 原 `figures/aphhm_pipeline.png` 外部图 |
| 图 2 | 等价压缩变体的配对 Top-1 界 + ±5pp 非劣带；仅「两处位点全关」出带 | 补充材料压缩变体表的可视化入口 |
| 图 3 | 20 例表观覆盖缺口的阶段归因（18 绑定失败 / 2 缺父）+ 有害注入反事实 | 原主文 `tab:stages`（已迁入补充材料） |

因 `tikz` 会覆盖 `url` 宏包的 `\path`，主文改用 `\DeclareUrlCommand\modelid{}` 输出模型标识符。

## 编译

```bash
latexmk -pdf main.tex
latexmk -pdf SupplementaryMaterial.tex
```

正文 7 页（第 8–9 页为参考文献），补充材料独立编译。

可复现性清单位于上一级目录的 `ReproducibilityChecklist.tex`，按独立文档编译。

提交压缩包时仅保留会议要求的源码、参考文献、实际使用的图件与编译产物；本 README 和 `reference_urls.md` 仅用于本地维护。

## 数据来源

`runs/paper_v1/diagnosisarena_d2_seq100_baselines_summary.md`（v10，§2 无 bind 主表、§4.1 SC10）、`b02_compute_matched_sc10_three_datasets.md`、各集专表。
