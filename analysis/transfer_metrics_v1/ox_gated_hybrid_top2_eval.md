# OX：门控混合 top2（±解耦 compat_parallel）L2 短列表测试

日期：2026-07-26  
范围：`ox_seq100` × `compat_synonym_v1`；judge=`lexical`（非 paper-official LLM）  
门控：`l1_rank≤2 ∧ (crowd ∨ leaf2/leaf1≥0.35)`（leaf-mass 排名；见 `ox_multi_gold_l1_rank_gate.md`）  
动作：触发轴保留族内 top2，其余轴 top1 →（可选解耦 compat）→ 压到 K  
机器表：[`ox_gated_hybrid_top2_eval.json`](ox_gated_hybrid_top2_eval.json)

## 臂

| 别名 | `ddx_source` | 说明 |
|------|--------------|------|
| gated | `gated_hybrid_top2_compress` | 选择性扩池后按后验压到 K |
| gated+compat | `gated_hybrid_top2_compat_then_compress` | 同上，但对扩池先跑解耦 `compat_parallel`（默认 dry） |
| global top2+compat | `l1_top2_compat_then_compress` | 全体 L1 top2（对照，已证实伤 F1） |
| posterior / compat_then_pad | 基线 | 全局后验 Top-K；compat 短列表 pad |

```bash
python3 scripts/paper/run_ox_mcr_official_eval.py \
  --dataset open_xddx \
  --run-dir logs/open_xddx_ox_seq100_v1/compat_synonym_v1 \
  --subset-parquet data/benchmarks/open_xddx/subsets/ox_seq100_v1/cases.parquet \
  --judge lexical --ddx-k 5 --build-projection \
  --ddx-source gated_hybrid

python3 scripts/paper/run_ox_mcr_official_eval.py \
  ... --ddx-source gated_hybrid_compat
```

## 主结果（diagnostic micro）

| 臂 | K | P | R | F1 | ΔF1 vs 后验 |
|----|---|------|------|------|-------------|
| 后验 Top-K | 5 | 0.444 | 0.473 | 0.458 | — |
| compat_then_pad | 5 | 0.460 | 0.490 | 0.475 | +1.7 pp |
| **gated hybrid** | 5 | **0.446** | **0.475** | **0.460** | **+0.2 pp** |
| gated+compat (dry) | 5 | 0.430 | 0.458 | 0.444 | −1.4 pp |
| global L1-top2+compat | 5 | 0.428 | 0.456 | 0.442 | −1.7 pp |
| 后验 Top-K | 7 | 0.379 | 0.565 | 0.453 | — |
| compat_then_pad | 7 | 0.381 | 0.569 | 0.457 | +0.3 pp |
| gated hybrid | 7 | 0.390 | 0.516 | 0.444 | −0.9 pp |
| gated+compat (dry) | 7 | 0.390 | 0.516 | 0.444 | −0.9 pp |
| global L1-top2+compat | 7 | 0.362 | 0.539 | 0.433 | −2.0 pp |

## 机制读数

| 量 | 值 |
|----|---:|
| 选择性池长均值 | **6.2**（全局 top2 池曾为 8.9） |
| 每例扩 L1 数均值 | **1.8** |
| gated vs 后验 Top-5 Jaccard | **0.75** |
| gated+compat vs 后验 Jaccard | **0.51** |
| K=5：gated 与 gated+compat 列表全等 | **1/100**（compat 主要经 FineCrowd merge 改序/缩表后再 pad） |
| K=7：`total_pred=620` | 池常不足 7，无法 pad 到满 K |

## 解耦 compat 有效性（本设定）

在 **gated hybrid 池**上（dry calib）：

1. **K=5**：compat **伤害**开放 F1（0.460→0.444，Δ−1.6 pp），相对纯 gated；也未优于后验。  
2. **K=7**：与纯 gated **数值相同**（池长瓶颈 + dry 近恒等重排主导）。  
3. 与「全局 L1-top2+compat」比：gated+compat 略好（K=5：0.444 vs 0.442），但差距小，且两者都不如后验/compat_then_pad。

**结论**：门控混合 top2 本身在 K=5 上相对后验 **微正**（+0.2 pp F1），验证了「选择性扩」优于「全局 top2」；但 **解耦 dry compat_parallel 在此设定下无效/有害**，不能作为默认后处理。开放主表仍优先 `compat_then_pad`（或后验 Top-K）。

## 判定

| 项 | 状态 |
|----|------|
| gated hybrid top2 | `research_candidate`（K=5 微增益；K=7 因池短伤 R） |
| gated + 解耦 compat (dry) | **reject**（伤 F1 / 无增益） |
| 全局 L1-top2+compat | reject（已确认） |

可选下一步：`--live-calib` 仅在 gated 池上重测；或收紧门控为 `rank1∧leaf_close` 以进一步降误扩。

**后续**：MCR R3 方言 compat（`preserve_full_top2` + merge-pad）仅换输入为门控混合 top2 → K=5 F1 **0.466**（优于纯 gated / 裸 `run_compat`）。见 [`ox_gated_hybrid_mcr_compat_eval.md`](ox_gated_hybrid_mcr_compat_eval.md)。
