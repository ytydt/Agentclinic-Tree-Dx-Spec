# compat_parallel × R2 inject：Harness 可行性烟测

**队列**：`all100`  
**生成**：`2026-07-23T17:54:43.643044+00:00`  
**基线**：`compat_parallel`（禁金标 G2；复用 at1_compat cache）
**接入点**：compat 重排之后、标注/打分前 — 全树叶注入 + bind-repair + `_rank_and_expand`
**生产默认**：仍 **off**（本轮仅实测）

## 主表

| 臂 | n | AutoCoverage | @1 | @2 | MRR | bind率 |
|----|--:|-------------:|---:|---:|----:|-------:|
| R0_joint | 100 | 0.800 | 0.590 | 0.780 | 0.688 | 0.000 |
| R_compat | 100 | 0.800 | 0.720 | 0.780 | 0.753 | 0.000 |
| R_compat_R2 | 100 | 0.960 | 0.750 | 0.880 | 0.839 | 0.730 |
| R1_metric | 100 | 0.890 | 0.590 | 0.780 | 0.688 | 0.000 |

## 可行性门控

- **决策**：`PASS`
- **推荐栈**：`compat_parallel+R2_inject`
- **理由**：
  - compat→R2 Δ@1=+0.030 Δ@2=+0.100 Δcov=+0.160
  - opt2 guard vs compat (drop≤0.02): OK

## Harness 可行性结论

- `compat_parallel` 与 R2 注入在离线重放路径上 **可组合**（先 gate→merge/calib，再 inject）。
- 与正式数字对照：历史 compat_parallel @1/@2 = **0.72 / 0.78**（本表 `R_compat` 应复现同量级）。
- 若 `R_compat_R2` 相对 `R_compat` 不伤 @2 且 cov/@1 不降 → 可进入 harness opt-in 挂接。

## compat 分支分布（R_compat）

```
{'merge_only': 89, 'calib_only': 11}
```

