# OX 证据预算 × 短列表重校准（Stage 2）

协议：`ox_budget_recalib_offline_v1`
树源：emit_v1 overlay（`/data2/wanghongyi/Agentclinic-Tree-Dx-Spec/logs/open_xddx_ox_seq100_v1/compat_synonym_v1/annotate/emit_v1_overlay/shared_trees`）
机器表：[`ox_budget_recalib.json`](ox_budget_recalib.json)

## 锁定组合

| 旋钮 | 锁定值 |
|------|--------|
| emit | `emit_v1` |
| 组间 L1 证据预算 | **4** |
| 组内 L2 local | **4** |
| 每活家族 L2 候选上限 | **6** |
| 后验池 N | **15** |
| 提交 K | **5** |
| 重排器（离线） | `closed_live_remap` |
| 正式 live 名 | `closed_live_mac_supervisor` |

- 锁定预算全树 R=**0.7910** F1=**0.3064**
- 锁定短列表 P/R/F1=**0.5220 / 0.5565 / 0.5387**

## 预算网格（按全树 R 排序，Top-6）

| L1 | L2 local | L2 cand | 全树 R | 全树 F1 |
|----|----------|---------|--------|---------|
| 2 | 4 | 4 | 0.7910 | 0.3064 |
| 2 | 4 | 6 | 0.7910 | 0.3064 |
| 4 | 4 | 4 | 0.7910 | 0.3064 |
| 4 | 4 | 6 | 0.7910 | 0.3064 |
| 6 | 4 | 4 | 0.7910 | 0.3064 |
| 6 | 4 | 6 | 0.7910 | 0.3064 |

## 短列表网格（锁定预算下，Top-8）

| pool_n | K | reranker | P | R | F1 |
|--------|---|----------|---|---|-----|
| 12 | 5 | `closed_live_remap` | 0.5240 | 0.5586 | 0.5408 |
| 15 | 5 | `closed_live_remap` | 0.5220 | 0.5565 | 0.5387 |
| 12 | 4 | `closed_live_remap` | 0.5800 | 0.4947 | 0.5339 |
| 15 | 4 | `closed_live_remap` | 0.5775 | 0.4925 | 0.5316 |
| 7 | 4 | `closed_live_remap` | 0.5650 | 0.4819 | 0.5201 |
| 7 | 5 | `closed_live_remap` | 0.4920 | 0.5245 | 0.5077 |
| 7 | 4 | `post_n_mcr` | 0.5225 | 0.4456 | 0.4810 |
| 12 | 4 | `post_n_mcr` | 0.5225 | 0.4456 | 0.4810 |

## 相对论文默认 F4+F2

- paper 默认预算 + 锁定短列表 F1=**0.5387**
- DA/MCR F4+F2 reference on same emit overlay + locked shortlist

## 边界

- Evidence budgets are offline family/leaf retention proxies, not live F2/F4/F6 re-annotate.
- closed_live_remap reuses frozen live shortlists; Stage 3 may refresh live on emit trees.
- Do not label DA F6/F2 as OX-optimal without this grid.

## 复现

```bash
PYTHONPATH=src:scripts/paper python3 scripts/paper/audit_ox_budget_recalib.py \
  --run-dir logs/open_xddx_ox_seq100_v1/compat_synonym_v1
```

