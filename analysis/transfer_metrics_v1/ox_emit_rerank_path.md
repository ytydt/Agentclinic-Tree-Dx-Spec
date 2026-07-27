# OX 补叶 + 重排/重校准一体化路径

日期：2026-07-26  
范围：`ox_seq100` × `compat_synonym_v1` → `compat_synonym_emit_v1`  
状态：**Stage 0–3 已跑完；正式 LLM 门控 = REJECT**（相对 B00 的 95% CI 仍含 0）

相关：[`ox_mac_style_leaf_emit_feasibility.md`](ox_mac_style_leaf_emit_feasibility.md)、[`ox_c2a_force_emit.md`](ox_c2a_force_emit.md)、[`ox_emit_then_rerank_offline.md`](ox_emit_then_rerank_offline.md)、[`ox_emit_v1_validate.md`](ox_emit_v1_validate.md)、[`ox_budget_recalib.md`](ox_budget_recalib.md)、[`ox_emit_locked_llm_gate.md`](ox_emit_locked_llm_gate.md)

---

## 0. 目标与锚点

| 锚点 | 值 |
|------|---|
| 无 emit 公平臂 | `closed_live_mac_supervisor` LLM F1=**0.584** |
| B00 地板 | LLM F1=**0.543** |
| MAC B06 | LLM F1=**0.570** |
| 本路径正式臂 | `emit_v1` + 锁定预算 + fresh `closed_live` @15/5 → F1=**0.588** |
| 门控 | F1 门槛过；**vs B00 CI 下界仍 ≤0 → REJECT** |

设计串联：

```text
force-emit (知而未写) → OX 证据预算重校准 → 闭集 live 短列表 → LLM 门控
```

- **公平本方法**：`emit_v1`（ddx∩gap，≤3）  
- **仅上界**：`E_open_oracle`（B00∪MAC 开集名）  
- **不把 DA 的 F6/F2 直接标为 OX 最优**

---

## 1. Stage 0 — 离线上界

脚本：`scripts/paper/audit_ox_emit_then_rerank.py`  
报告：[`ox_emit_then_rerank_offline.md`](ox_emit_then_rerank_offline.md)

| Emit | 全树 R | ΔR |
|------|--------|----|
| baseline | 0.704 | — |
| **E_c2a (=emit_v1)** | **0.791** | **+8.7pp** |
| E_open_oracle | 0.778 | +7.5pp |

短列表（lexical）：无选择 boost 伤 F1；`pool15_live_sim`（软进窗 + 选择性 boost）过离线门控。  
→ 解锁 Stage 1（紧候选，禁止 flood）。

---

## 2. Stage 1 — emit_v1 固化

| 项 | 内容 |
|----|------|
| 配置 | [`ox_emit_v1_config.json`](ox_emit_v1_config.json) |
| 控制器 | `l2_recall_gap_fill=True` + `l2_gap_force_emit_uncovered=True` + `l2_gap_force_emit_max=3`（默认 OFF） |
| 物化 | `scripts/paper/materialize_ox_emit_v1.py` → `annotate/emit_v1_overlay/` |
| 验证 | smoke10 + full100：全树 R **+8.7pp**；后验 Top-5 F1 **不崩**（Δ=0） |

详见 [`ox_emit_v1_validate.md`](ox_emit_v1_validate.md)。

---

## 3. Stage 2 — OX 预算/短列表锁定

脚本：`scripts/paper/audit_ox_budget_recalib.py`  
报告：[`ox_budget_recalib.md`](ox_budget_recalib.md)

| 旋钮 | 锁定 |
|------|------|
| 组间 L1 | **4** |
| 组内 L2 local | **4**（离线代理上优于 F2 的 local=2，全树 R +2.1pp） |
| 每活家族候选上限 | **6** |
| 池 N / K | **15 / 5** |
| 正式重排 | **`closed_live_mac_supervisor`** |

说明：证据预算为**家族/叶保留代理**（非 live F2/F4/F6 重 annotate）。L2 local=4 是 OX 网格结果，不是搬运 DA 的 F2。

---

## 4. Stage 3 — 正式 LLM 门控

环境：`gnn-llm` + `clashon`，`--workers 50`，`paper_aligned_judge_v1`。  
侧跑：`logs/open_xddx_ox_seq100_v1/compat_synonym_emit_v1/`  
报告：[`ox_emit_locked_llm_gate.md`](ox_emit_locked_llm_gate.md)

| 臂 | P | R | F1 |
|----|---|---|-----|
| B00 | 0.526 | 0.561 | 0.543 |
| MAC | — | — | 0.570 |
| gated_hybrid_mcr | — | — | 0.547 |
| closed_live（无 emit） | 0.566 | 0.603 | **0.584** |
| emit remap（参考） | 0.568 | 0.606 | 0.586 |
| **emit_v1 + fresh live** | **0.570** | **0.608** | **0.588** |

逐例 ΔF1：

| 对比 | mean | 95% CI |
|------|------|--------|
| emit − live | +0.003 | 含 0 |
| emit − B00 | +0.040 | **[-0.004, +0.082]**（含 0） |

### Promote 规则与结果

1. F1≥0.570 **或** vs live ΔF1≥+1.5pp 且 P 掉≤3pp → **过**（F1=0.588）  
2. vs B00 的 95% CI 下界 >0 → **未过**  
3. 全树 R 不降 → **过**

**总判：REJECT**（仍 marginal vs B00；相对无 emit live 仅 +0.4pp）。

---

## 4b. 后续：live 重标注（在线后验写回）

在锁定 F 上做 **Config A + joint → 后验写回 shared_trees → fresh closed_live + LLM**。  
报告：[`ox_live_reann_emit_vs_fopt.md`](ox_live_reann_emit_vs_fopt.md)

| 臂 | F1 | vs 原 live |
|----|-----|-----------|
| emit + locked F live | 0.645 | +0.061 |
| **no-emit + locked F live** | **0.651** | **+0.067** |

force-emit 全例 `n_total=0`，未贡献增益；最优为无 emit + 锁定 F + live 重标。

机制学入档（算法 / 校准预算下起效 / 根因）：[`ox_specific_mechanisms_explainer.md`](ox_specific_mechanisms_explainer.md)。

---

## 5. 口径声明

- `emit_v1` 为公平本方法；`E_open_oracle` 仅上界。  
- 正式分不依赖冻结 B06 名单补叶。  
- 只补叶不进窗：后验 Top-5 F1 不变（再次确认）。  
- 无预算 gap flood 禁止上线。

---

## 6. 复现

```bash
# Stage 0
PYTHONPATH=src:scripts/paper python3 scripts/paper/audit_ox_emit_then_rerank.py

# Stage 1
PYTHONPATH=src:scripts/paper python3 scripts/paper/materialize_ox_emit_v1.py --smoke 10

# Stage 2
PYTHONPATH=src:scripts/paper python3 scripts/paper/audit_ox_budget_recalib.py

# Stage 3（需 gnn-llm + clashon）
source "$(conda info --base)/etc/profile.d/conda.sh" && conda activate gnn-llm
bash /home/wanghongyi/clashctl/clashon.sh
PYTHONPATH=src:scripts/paper python3 scripts/paper/run_ox_emit_locked_llm_gate.py --workers 50
# fresh live（可选，已跑）：
PYTHONPATH=src:scripts/paper python3 scripts/paper/run_ox_mcr_official_eval.py \
  --dataset open_xddx \
  --run-dir logs/open_xddx_ox_seq100_v1/compat_synonym_emit_v1 \
  --subset-parquet data/benchmarks/open_xddx/subsets/ox_seq100_v1/cases.parquet \
  --judge llm --ddx-k 5 --workers 50 \
  --ddx-source closed_live_mac --live-closed-mac --pool-n 15 \
  --projection-subdir eval_projection_emit_v1_live \
  --out-name official_eval_llm_emit_v1_live --build-projection
```

---

## 7. 下一步（若不接受 REJECT）

1. **真重 annotate**：按锁定 L1=4 / L2local=4 / cand=6 重跑证据，再接 live（当前预算仅为代理）。  
2. **V2 轻量 leaf-proposer**（可行性文）：扩入口以外的可叶化开集名，预算≤3。  
3. 目标仍是 **vs B00 的 ΔF1 CI 下界 >0**，而非仅微幅超过 live。
