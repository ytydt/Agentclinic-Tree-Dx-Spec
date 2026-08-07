# MCR200 × AB02（flat / no L1）

口径：`official_eval_llm_compat` Prompt-7 Acc@1，与主文 MCR 头条同标度。
干预：在 M00 树上施加 `l1_axis_mode=flat`（`keep_leaves=False`），annotate 重生 L2；
其余与 M00 对齐（`granularity=compat` + synonym_bind）。

## 结果

| 切片 | n 配对 | M00 Acc | AB02 Acc | Δ (M00−AB02) | b/c | sign-test p |
|---|---:|---:|---:|---:|---|---:|
| 切片一 (v1) | 100 | 0.500 | 0.440 | +0.060 | 9/3 | 0.146 |
| 切片二 (v2) | 100 | 0.460 | 0.470 | -0.010 | 5/6 | 1.000 |
| **合并** | 200 | 0.480 | 0.455 | +0.025 | 14/9 | 0.405 |

b = M00 对、AB02 错；c = AB02 对、M00 错。

## 产物

- `logs/medcasereasoning_mcr_val_seq100_v1/c3_ab02_v1/`
- `logs/medcasereasoning_mcr_val_seq100_v2/c3_ab02_v1/`
- 机器可读：`report.json`

## 处置

内部分析；主文已锁。是否入下一版取决于合并方向与效应量，
不自动写入 `paper_aaai/`。
