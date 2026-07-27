# OX：L1-top2 → compat_parallel → compress（短列表扩充）

日期：2026-07-26  
范围：`ox_seq100` × `compat_synonym_v1`；judge=`lexical`（`compatible_metrics_lexical_v1`，非 paper-official LLM）  
动机：OX 主目标是开放 P/R/F1，而非 mapper@1；避免「先压到 K 再重排」把同 L1 次优叶挤出池。

## 协议

评测侧新源：`l1_top2_compat_then_compress`（别名 `l1_top2_compat` / `l1_top2`）

1. **Expand**：每个 L1 parent 保留后验 top-2（label-dedup）→ 扩展池（本 run 均值 **8.86**，范围 6–10）
2. **Rerank**：对**整池**跑解耦 `compat_parallel`（`k=len(pool)`；默认 dry calib）
3. **Compress**：截断/pad 到最终 `ddx_k`∈{5,7}

对比臂：全局后验 Top-K；`compat_then_pad_posterior`（先短列表/compat 再 pad）。

```bash
# K=5
python3 scripts/paper/run_ox_mcr_official_eval.py \
  --dataset open_xddx \
  --run-dir logs/open_xddx_ox_seq100_v1/compat_synonym_v1 \
  --subset-parquet data/benchmarks/open_xddx/subsets/ox_seq100_v1/cases.parquet \
  --judge lexical --ddx-k 5 --build-projection \
  --ddx-source l1_top2_compat

# K=7（独立 projection / out-name，避免覆盖）
python3 scripts/paper/run_ox_mcr_official_eval.py \
  --dataset open_xddx \
  --run-dir logs/open_xddx_ox_seq100_v1/compat_synonym_v1 \
  --subset-parquet data/benchmarks/open_xddx/subsets/ox_seq100_v1/cases.parquet \
  --judge lexical --ddx-k 7 --build-projection \
  --ddx-source l1_top2_compat \
  --projection-subdir eval_projection_l1_top2_compat_k7 \
  --out-name official_eval_l1_top2_compat_k7
```

产物：`annotate/eval_projection_l1_top2_compat/`、`annotate/official_eval_l1_top2_compat/`（及 `_k7` 变体）。

## 结果（diagnostic micro）

| 臂 | K | P | R | F1 | ΔF1 vs 后验 |
|----|---|------|------|------|-------------|
| 后验 Top-K | 5 | 0.444 | 0.473 | 0.458 | — |
| `compat_then_pad` | 5 | 0.460 | 0.490 | 0.475 | +1.7 pp |
| **L1-top2→compat→compress** | 5 | **0.428** | **0.456** | **0.442** | **−1.7 pp** |
| 后验 Top-K | 7 | 0.379 | 0.565 | 0.453 | — |
| `compat_then_pad` | 7 | 0.381 | 0.569 | 0.457 | +0.3 pp |
| **L1-top2→compat→compress** | 7 | **0.362** | **0.539** | **0.433** | **−2.0 pp** |

相对后验（K=5）：ΔP **−1.6 pp**，ΔR **−1.7 pp**，ΔF1 **−1.7 pp**。  
相对 `compat_then_pad`（K=5）：ΔF1 **−3.3 pp**。

## 机制读数

| 观测 | 值 |
|------|-----|
| 扩展池 `pool_len` | mean 8.86（6–10） |
| FineCrowdGate 触发 | 29/100（`merge_only`）；其余 dry `calib_only` |
| 最终短列表 L1 多样性 | 后验 Top-5 均值 **2.68** 个 parent → L1-top2 臂 **4.22** |
| 与后验 Top-5 label Jaccard | mean **0.49** |

dry calib 下 compat **几乎不重排**；本臂效果主要来自「按家族扩池后再截断」。OX 上同 L1 多金标很常见（见 `ox_same_l1_multi_gold_structural.md` / micro-R 上界），强制跨家族多样性会挤掉同家族高后验叶 → P/R 同步下降。

## 判定

- **工程已落地**：expand → 解耦 compat → compress 顺序正确；单测覆盖「compat 看到的是扩池而非最终 K」。
- **指标**：在默认 dry lexical 下 **未抬开放 F1**；不如后验 Top-K，也不如 `compat_then_pad`。
- **定位**：`research_only`；不进 OX 主表，除非 live calib（`--live-calib`）能证明重排收益超过多样性挤出。

下一步（可选）：同臂 `--live-calib` + LLM judge；或「同 L1 保留 top2，但 compress 时用后验加权 / 配额混合」而非纯 compat 序截断。

机器可读：[`ox_l1_top2_compat_compress.json`](ox_l1_top2_compat_compress.json)。
