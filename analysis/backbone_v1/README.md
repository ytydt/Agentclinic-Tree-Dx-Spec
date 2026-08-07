# Backbone v1 — 削减与验证实验

产物根目录：`logs/backbone_v1/`（不触碰既有 paper 资产）。
**总结果见 [RESULTS.md](RESULTS.md)。**

## 关键数字

| 配置 | 端点 | 分数 | calls/例 |
|---|---|---:|---:|
| 骨干 DA s4b k5 | option@1 | 0.50 | 4 |
| 骨干 DA s4b k8 | option@1 | **0.52** | 4 |
| 骨干 DA kb_only | option@1 | **0.57** | 2+retr |
| B02 DA native | option@1 | 0.56 | ~2 |
| 骨干 MCR 切片一 | Acc@1 | 0.24 | 4 |
| 骨干 MCR 切片二确认 | Acc@1 | **0.22（通过 ≥0.22）** | 4 |
| B02 MCR | Acc@1 | 0.17 | 2 |

- S4-c：**未通过**（C 桶改善 0）
- E3：**未确认** LLM-DDx 为主机制（kb_only 反而 +0.07）
- E6：**通过**预注册阈值
- RA：已下线（`INTERNAL_MEMO_rarearena_retired.md`）

## 批 0

- `z1_mcr_diag.json`：MCR DDx mean 4.68/例；gold∈首次列表 0.75；漏斗 A/B/C/D = 25/15/21/39
- `z2_da_funnel.md`：DA 漏斗 A/B/C/D = 14/8/16/62；C 桶 lateral 嫌疑 6

## 代码与跑法

- `src/agentclinic_tree_dx/backbone.py`
- `scripts/paper/run_backbone_v1.py`
- prompts：`backbone_parse/wide_ddx/entity_filter/select_free/select_granularity.txt`

```bash
PYTHONPATH=src:scripts:scripts/paper python3 -u scripts/paper/run_backbone_v1.py \
  --dataset diagnosisarena --arm v0_s4b_k5 --select b --max-k 5 --workers 25 --score
```

资产守卫：跑前快照 `analysis/asset_guard/20260806T065220Z/`，结束时 verify OK（modified=0）。
