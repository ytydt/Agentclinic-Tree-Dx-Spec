# OX：MCR 版 compat_parallel × 门控混合 top2 输入

日期：2026-07-26  
范围：`ox_seq100`；judge=`lexical`  
设定：**仅替换输入**——池 = 后验序的 L1 门控混合 top2；算法 = **MCR R3 方言** compat_parallel  
机器表：[`ox_gated_hybrid_mcr_compat_eval.json`](ox_gated_hybrid_mcr_compat_eval.json)

## 方言差异（相对此前 `gated_hybrid_compat`）

| | `run_compat_parallel`（此前 gated+compat） | **MCR R3**（本臂） |
|--|-------------------------------------------|-------------------|
| 入口 | `merge_calib_compat.run_compat_parallel` | 与 MCR 消融 R3 同构的手写平行逻辑 |
| merge | 代表叶短列表，再 pad | **merge → pad 回 K** |
| calib | `preserve_full_top2=False`；`k=len(pool)` | **`preserve_full_top2=True`**；**`k=最终 K`** |
| 输入 | 门控混合 top2 | **同左**（唯一共享点） |

```bash
python3 scripts/paper/run_ox_mcr_official_eval.py \
  --dataset open_xddx \
  --run-dir logs/open_xddx_ox_seq100_v1/compat_synonym_v1 \
  --subset-parquet data/benchmarks/open_xddx/subsets/ox_seq100_v1/cases.parquet \
  --judge lexical --ddx-k 5 --build-projection \
  --ddx-source gated_hybrid_mcr
```

## 主结果（diagnostic micro）

| 臂 | K | P | R | F1 | ΔF1 vs 后验 | ΔF1 vs 纯 gated |
|----|---|------|------|------|-------------|-----------------|
| 后验 Top-K | 5 | 0.444 | 0.473 | 0.458 | — | — |
| 纯 gated hybrid | 5 | 0.446 | 0.475 | 0.460 | +0.2 pp | — |
| gated + `run_compat` (dry) | 5 | 0.430 | 0.458 | 0.444 | −1.4 pp | −1.6 pp |
| **gated + MCR R3 compat (dry)** | 5 | **0.452** | **0.482** | **0.466** | **+0.8 pp** | **+0.6 pp** |
| compat_then_pad | 5 | 0.460 | 0.490 | 0.475 | +1.7 pp | — |
| 后验 / 纯 gated / MCR | 7 | — | — | 0.453 / 0.444 / **0.444** | MCR≡gated | 0 |

## 机制读数（K=5）

| 量 | 值 |
|----|---:|
| 与纯 gated 列表全等 | **11/100** |
| 与 `run_compat` 方言列表全等 | **31/100** |
| Jaccard vs 纯 gated / vs 后验 | **0.93** / **0.70** |
| 分支 | `calib_only` **76**，`merge_only_pad` **24** |

dry calib 下增益主要来自 **merge→pad**（24% 例）与 **Top2 freeze**；裸 `run_compat` 无 freeze 且对扩池用 `k=len(pool)`，更容易伤开放列表。

## 判定

1. **MCR 方言 + 门控混合输入在 K=5 有效**：相对后验 **+0.8 pp F1**，相对纯 gated **+0.6 pp**；扭转了此前 `run_compat` 方言的伤害。  
2. 仍 **未超过** `compat_then_pad`（0.475）。  
3. **K=7** 与纯 gated 打平（池长瓶颈，`n_pred=620`）。  
4. 状态：`research_candidate` — 若继续解耦 compat，优先 **MCR R3 方言** 而非裸 `run_compat_parallel`；开放主表默认仍可保留 `compat_then_pad`。

可选：`--live-calib` 测 MCR 方言在 gated 池上是否再抬一截。
