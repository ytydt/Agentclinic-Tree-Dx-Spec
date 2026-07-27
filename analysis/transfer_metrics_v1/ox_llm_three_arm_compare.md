# OX：三臂 LLM 端到端对照（hybrid MCR / compat_then_pad / N=7 MCR）

状态：完成  
日期：2026-07-26  
协议：`paper_aligned_judge_v1` · 裁判 **Gemini 2.5 Flash** · `gnn-llm` + `clashon` · `--workers 50`  
队列：`ox_seq100` × `compat_synonym_v1`  
机器表：[`ox_llm_three_arm_compare.json`](ox_llm_three_arm_compare.json)

---

## 主表（统一 K=5）

| 臂 | 配置 | P | R | F1 | TP | vs posterior |
|----|------|--:|--:|---:|---:|------------|
| posterior（锚） | 全局后验 Top-5 | 0.500 | 0.533 | 0.516 | 250 | — |
| **gated_hybrid_mcr** | 门控 hybrid top2 → MCR R3 → K=5 | **0.530** | **0.565** | **0.547** | **265** | **+3.1 pp** |
| post7_mcr | 后验 Top-7 → MCR R3 → K=5 | 0.510 | 0.544 | 0.526 | 255 | +1.0 pp |
| compat_then_pad | compat 短列表 pad → K=5 | 0.508 | 0.542 | 0.524 | 254 | +0.8 pp |

产物目录：

| 臂 | `annotate/` |
|----|-------------|
| hybrid MCR | `official_eval_llm_gated_hybrid_top2_mcr/` |
| compat_then_pad | `official_eval_llm_compat_then_pad/`（既有，协议一致） |
| N=7 MCR @5 | `official_eval_llm_post7_mcr/` |

---

## 侧臂：N=7 → MCR → K=4（lexical 最优形态）

| 臂 | P | R | F1 | TP | pred 条数 |
|----|--:|--:|---:|---:|----------:|
| post7_mcr @4 | **0.585** | 0.499 | **0.539** | 234 | 400 |

目录：`official_eval_llm_post7_mcr_k4/`  
相对 K=5 同臂：F1 **+1.3 pp**（P↑、R↓，与 lexical 扫盘方向一致）。  
相对主表 hybrid_mcr@5：仍低 **0.8 pp F1**。

---

## 与 lexical 的次序翻转

| 臂 | lexical F1 (K=5) | LLM F1 (K=5) |
|----|-----------------:|-------------:|
| compat_then_pad | **0.475** | 0.524 |
| gated_hybrid_mcr | 0.466 | **0.547** |
| post7_mcr | ~0.466（N=7→K=5） | 0.526 |

LLM 下 **hybrid MCR 反超** `compat_then_pad`（+2.3 pp），且领先后验 +3.1 pp。  
解释：Gemini 匹配比 lexical 更宽；hybrid 扩入的近义/同族叶在 LLM 下更易计 TP，而 lexical 扫盘低估了该臂。

---

## 复现

```bash
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate gnn-llm
bash /home/wanghongyi/clashctl/clashon.sh

# 1) hybrid MCR R3
PYTHONPATH=src:scripts/paper:scripts python -u scripts/paper/run_ox_mcr_official_eval.py \
  --dataset open_xddx \
  --run-dir logs/open_xddx_ox_seq100_v1/compat_synonym_v1 \
  --subset-parquet data/benchmarks/open_xddx/subsets/ox_seq100_v1/cases.parquet \
  --judge llm --ddx-k 5 --workers 50 \
  --ddx-source gated_hybrid_mcr --build-projection

# 2) compat_then_pad（若需重跑）
... --ddx-source compat_then_pad --build-projection

# 3) N=7 MCR @K=5
... --ddx-source post7_mcr --pool-n 7 --build-projection

# 可选：N=7 → K=4
... --ddx-source post7_mcr --pool-n 7 --ddx-k 4 \
  --projection-subdir eval_projection_post7_mcr_k4 \
  --out-name official_eval_llm_post7_mcr_k4 --build-projection
```

新增投影源：`post_n_mcr` / `post7_mcr`（`--pool-n`，默认 7）∈ `build_eval_projection.py`。

---

## 裁定

1. **主表 K=5 LLM**：三臂里 **gated_hybrid_mcr 最优（F1 0.547）**。  
2. **compat_then_pad** 仍优于后验，但不再是 LLM 下的开放 F1 冠军。  
3. **N=7 MCR**：K=5 略优于 pad；K=4 再抬 F1 至 0.539，仍不及 hybrid_mcr@5。  
4. 开放主表若以 **LLM-judge** 为准，可将 **gated_hybrid_mcr @5** 升为 research→候选默认；lexical 表勿静默横比。
