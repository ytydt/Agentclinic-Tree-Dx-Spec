# Merge × Calibration 交互根因

**日期**：2026-07-23  
**数据**：`logs/diagnosisarena_d2_m01_v1/at1_granularity_v1/per_case_*_all100.tsv`  
**口径**：无金标 G2

## 1. 现象

| 臂 | @1 | @2 | 含义 |
|----|---:|---:|------|
| ours | 0.59 | 0.78 | naive joint |
| merge | **0.68** | 0.78 | 仅 AdaptiveMergeSiblings |
| both_l1fallback | 0.65 | 0.79 | 仅强校准 |
| both_merge（旧：merge→`both`） | 0.66 | 0.78 | 串行叠用，低于 merge |
| deepen | 0.67 | 0.78 | 过宽 Fine→几乎恒 merge 再校准 |

无金标并集上界（每例取 merge∨calib）：**@1=0.75**。串行叠用远低于并集。

## 2. 个案交互

相对 ours：

- `M+`（merge 修好）：10 例；`C+`（校准修好）：13 例；交集 7；纯 M+ 3；纯 C+ 6。  
- **校准毁掉 merge 已赢**：`140`, `28`, `89`（其中 `140/28`：单独 merge、单独校准都 @1，叠用后错）。  
- **叠用额外救回**：`177`（1 例）——远不够抵消损伤。

根因机制：merge 缩同义簇后，L1fallback/pair 在缩池上重排，把 merge 保住的代表 Top1 挤到第 2（金标盲交互损伤，非泄题）。

## 3. 门控过宽

旧 `fine_signal`（全榜任一同义簇）触发 **99/100** → deepen 几乎不做「未合并池上的校准」，纯 `C+`（如 `117/120/90`）收益丢失。

收紧门控（计划）：`Top1 簇 |members|≥2` **或** `Top1–Top2 labels_synonymish`。

## 4. 臂配置不一致

旧烟测 `both_merge` 接校准臂 `both`，而 deepen 接 `both_l1fallback`，对照不公平。应统一为 `both_l1fallback`。

## 5. 兼容方向

禁止「强校准串在 merge 后」作为默认；改为 **并行选路**（拥挤→merge-only，否则→both_l1fallback）。实测 compat_parallel **@1=0.72**。

- 点估计与验收：[`merge_calib_compat_report.md`](merge_calib_compat_report.md)  
- **算法、门控定义、起效机制与深层根因（学术入档）**：[`compat_parallel_mechanism_explainer.md`](compat_parallel_mechanism_explainer.md)
