# OX：B00 / B05 相对性能异常高 — 解剖

日期：2026-07-26
机器表：[`ox_b00_b05_anomaly.json`](ox_b00_b05_anomaly.json)

## 0. 异常事实（禁止混表）

OX 上 pure 开集生成臂挤进前三；DA 上的 RAG 冠军 B07 掉到第 10。

| 臂 | DA @1 (rank) | MCR Acc (rank) | OX F1 (rank) |
|----|-------------:|---------------:|-------------:|
| `B00-direct-cot` | 0.54 (#9) | 0.18 (#9) | 0.543 (#2) |
| `B05-mdagents` | 0.58 (#5) | 0.20 (#6) | 0.543 (#3) |
| `B06-mac-single-vendor` | 0.61 (#2) | 0.23 (#2) | 0.570 (#1) |
| `B07-meddxagent-complete` | 0.62 (#1) | 0.24 (#1) | 0.491 (#10) |

树对照（同 LLM judge）：`gated_hybrid_mcr` F1=**0.547**；公平臂 `closed_live_mac_supervisor` F1=**0.584**。

## 1. OX 正式 micro

| 臂 | P | R | F1 |
|----|--:|--:|---:|
| B00-direct-cot | 0.526 | 0.561 | 0.543 |
| B05-mdagents | 0.526 | 0.561 | 0.543 |
| B06-mac | 0.552 | 0.588 | 0.570 |
| tree gated_hybrid_mcr | 0.530 | 0.565 | 0.547 |
| tree closed_live_mac | 0.566 | 0.603 | 0.584 |

## 2. B00 ≈ B05？（多代理是否白加）

- 逐例 ΔF1 (B05−B00)：win/tie/lose = **16/67/17**；mean=-0.0007，95% CI [-0.0271, 0.0238]
- 预测列表重叠比（soft）：**0.736**
- B05 complexity：{'moderate': 62, 'high': 28, 'low': 10}；mean roles=2.98；solo=10

**裁定**：OX 集合 F1 上 MDAgents **几乎不优于** Direct CoT（CI 含 0，平局占多数）。

## 3. 相对树 / MAC

- **B00 − gated**：win/tie/lose=31/39/30；meanΔ=-0.0037 CI[-0.0518,+0.0429]
- **B00 − live**：win/tie/lose=27/36/37；meanΔ=-0.0366 CI[-0.0802,+0.0082]
- **B00 − MAC**：win/tie/lose=10/70/20；meanΔ=-0.0261 CI[-0.0525,+0.0000]
- **live − B00**：win/tie/lose=37/36/27；meanΔ=+0.0366 CI[-0.0082,+0.0800]
- **B05 − MAC**：win/tie/lose=15/63/22；meanΔ=-0.0268 CI[-0.0584,+0.0022]

## 4. TP 开集占比（相对全树叶）

| 臂 | TP | open TP | in-tree TP | open/TP |
|----|---:|--------:|-----------:|--------:|
| B00 | 227 | 32 | 195 | 14.1% |
| B05 | 221 | 24 | 197 | 10.9% |
| MAC | 231 | 30 | 201 | 13.0% |
| gated | 226 | 0 | 226 | 0.0% |
| live | 261 | 0 | 261 | 0.0% |

## 5. 相对树短列表的独占 TP（H1/H2 风格）

- **B00 vs gated**：shared=151；独占 open=32 (42%)；独占 trunc=44 (58%)；树独有=75
- **B05 vs gated**：shared=148；独占 open=24 (33%)；独占 trunc=49 (67%)；树独有=78
- **MAC vs gated**：shared=151；独占 open=30 (38%)；独占 trunc=50 (62%)；树独有=75

## 6. 机制结论

1. **跨表位移**：B00/B05 在 OX 升至 #2/#3，而 DA/MCR 冠军 B07 在 OX 跌至 #10；pure 开集 Top-K 生成适配多金标集合 F1，窄 RAG 在 OX 掉队。
2. **B00≈B05**：B05−B00 meanΔ=-0.0007 CI[-0.0271,0.0238]；多角色 MDAgents 对 OX micro-F1 无显著增益（≈单次 Direct CoT）。
3. **为何 OX 抬升 pure CoT**：B00 TP 中开集仅占 14.1%（多数命中仍在树叶宇宙）；相对 gated 独占边 trunc=44 / open=32 → 主要是开集命名+排序进窗，而非纯缺叶补洞。任务形态（集合 F1）奖励一次生成多样性，惩罚 DA 上吃香的窄检索/闭集绑定。
4. **对树方法含义**：gated≈B00（meanΔ=-0.0037，CI含0）；公平闭集 live 对 B00 meanΔ=+0.0366，但 **95% CI 仍含 0** [-0.008,+0.080]。树相对强纯 CoT 的领先仍 marginal；需继续打 Open 缺叶（C4）与池内排序，而不是再堆类似 B05 的多代理壳。

## 7. 复现

```bash
PYTHONPATH=src:scripts/paper python3 scripts/paper/audit_ox_b00_b05_anomaly.py --write-md
```

