# OX：补叶 → 重排 离线上界（Stage 0）

状态：离线 eval-only inject 完成（不改原 run）
日期：2026-07-26
范围：`ox_seq100` × `compat_synonym_v1`；judge=`lexical`
协议：`ox_emit_then_rerank_offline_v1`
机器表：[`ox_emit_then_rerank_offline.json`](ox_emit_then_rerank_offline.json)

---

## 0. 设计

| Emit | 候选 |
|------|------|
| **E_c2a** | ddx∩gap_uncovered 且不在叶，≤3（= emit_v1） |
| **E_open_oracle** | B00∪MAC 名中全叶未匹配，≤3（**仅上界**） |
| **E_c2a_plus_open** | 并集总预算 ≤3 |

| Rerank | 行为 |
|--------|------|
| **post_topK** | 注入后后验 Top-K（新叶极低后验） |
| **boost_tail** | Top-K 末席强制留给新叶 |
| **pool15_live_sim** | Top-15∪新叶 → 冻结 live 映射 / RRF → K=5 |

## 1. Baseline

| 视图 | P | R | F1 |
|------|---|---|-----|
| 全树 | 0.1956 | 0.7036 | 0.3061 |
| 后验 Top-5 | 0.4440 | 0.4733 | 0.4582 |

## 2. Emit → 全树 R

| Emit | 全树 R | ΔR | n_added |
|------|--------|----|---------|
| E_c2a | 0.7910 | +0.0874 | 284 |
| E_open_oracle | 0.7783 | +0.0746 | 221 |
| E_c2a_plus_open | 0.7932 | +0.0896 | 293 |

## 3. Emit × Rerank 短列表（K=5）

| Combo | P | R | F1 | ΔF1 vs base | ΔP |
|-------|---|---|-----|-------------|----|
| `E_c2a__post_topK` | 0.4440 | 0.4733 | 0.4582 | +0.0000 | +0.0000 |
| `E_c2a__boost_tail` | 0.4060 | 0.4328 | 0.4190 | -0.0392 | -0.0380 |
| `E_c2a__pool15_live_sim` | 0.5820 | 0.6205 | 0.6006 | +0.1424 | +0.1380 |
| `E_open_oracle__post_topK` | 0.4440 | 0.4733 | 0.4582 | +0.0000 | +0.0000 |
| `E_open_oracle__boost_tail` | 0.4200 | 0.4478 | 0.4334 | -0.0248 | -0.0240 |
| `E_open_oracle__pool15_live_sim` | 0.5700 | 0.6077 | 0.5882 | +0.1300 | +0.1260 |
| `E_c2a_plus_open__post_topK` | 0.4440 | 0.4733 | 0.4582 | +0.0000 | +0.0000 |
| `E_c2a_plus_open__boost_tail` | 0.4060 | 0.4328 | 0.4190 | -0.0392 | -0.0380 |
| `E_c2a_plus_open__pool15_live_sim` | 0.5820 | 0.6205 | 0.6006 | +0.1424 | +0.1380 |

## 4. 离线门控

规则：boost 或 pool15 相对 baseline **ΔF1≥+1.5pp** 且 **ΔP≥−3pp**。

- 短列表门控：**PASS**
- 紧候选全树 R 解锁 Stage 1：**YES（禁止 flood，仅 emit_v1）**

- `E_c2a__boost_tail`: ΔF1=-0.0392 ΔP=-0.0380 → fail
- `E_c2a__pool15_live_sim`: ΔF1=+0.1424 ΔP=+0.1380 → PASS
- `E_open_oracle__boost_tail`: ΔF1=-0.0248 ΔP=-0.0240 → fail
- `E_open_oracle__pool15_live_sim`: ΔF1=+0.1300 ΔP=+0.1260 → PASS
- `E_c2a_plus_open__boost_tail`: ΔF1=-0.0392 ΔP=-0.0380 → fail
- `E_c2a_plus_open__pool15_live_sim`: ΔF1=+0.1424 ΔP=+0.1380 → PASS

## 5. 边界

- E_open_oracle is an upper bound only (frozen B00∪MAC names); not a fair method arm.
- pool15_live_sim: soft-enter Top-15 + closed RRF/live remap; selective gold-matched inject boost only.
- post_topK leaves injects at posterior=1e-4 (known not-in-window failure mode).
- Unselective boost_tail of all injects typically hurts micro-F1 (same as C2a A1t).

## 6. 复现

```bash
PYTHONPATH=src:scripts/paper python3 scripts/paper/audit_ox_emit_then_rerank.py \
  --run-dir logs/open_xddx_ox_seq100_v1/compat_synonym_v1 --ddx-k 5
```

