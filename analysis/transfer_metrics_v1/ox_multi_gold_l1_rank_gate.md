# OX：多金标 L1 族的排名特征与 top-2 / 门控

日期：2026-07-26  
范围：`ox_seq100` 同 L1 多金标组（n=87，来自 `ox_same_l1_multi_gold_structural`）  
叶宇宙：`shared_trees`；**L1 排名 = 子叶后验之和**（parent.posterior 常为 0）  
机器表：[`ox_multi_gold_l1_rank_gate.json`](ox_multi_gold_l1_rank_gate.json)

> L1 rank uses sum of child-leaf posteriors when parent.posterior==0 (common in annotate/shared_trees).

## 1. 多金标 L1 族有什么特点？

| 特征 | 值 |
|------|---:|
| 组规模分布 (n_golds) | `{2: 54, 3: 22, 4: 10, 5: 1}` |
| 族内叶数均值 | 3.76 |
| 族内叶数分布 | `{3: 21, 4: 66}` |
| L1 leaf-mass 份额均值 / 中位 | 0.328 / 0.300 |

Multi-gold L1s are typically small sibling sets (~3–4 leaves), often high leaf-mass share, and frequently among the case's top L1 axes (by leaf-mass).

## 2. 有多大比例是 ranking 靠前的 L1？

| L1 leaf-mass 名次 | 组数 | 占比 |
|------------|-----:|-----:|
| rank = 1 | 48 | 55.2% |
| rank ≤ 2 | 68 | 78.2% |
| rank ≤ 3 | 78 | 89.7% |

名次直方图：`{1: 48, 2: 20, 3: 10, 4: 8, 5: 1}`

## 3. 这些金标落在族内 top-2 的比例？

口径：已覆盖金标 → 命中叶在该 L1 子叶后验序中的名次（n=212 条可排名；6 条未解析）。

| 覆盖 | 条数 | 占比 |
|------|-----:|-----:|
| 族内 top-1 | 78 | 36.8% |
| 族内 top-2 | 150 | 70.8% |
| 族内 top-3 | 193 | 91.0% |
| 组内全部金标都在 top-2 | — | 43.7% |

对「≥2 个不同命中叶」的组（n=81）：**两个及以上命中叶同在族内 top-2** 的比例 = **80.2%**（65 组）。

## 4. 能否做门控？

Oracle 正例（严格）：同 L1 上金标命中 **≥2 个不同叶** → 只留族内 top1 会结构性丢掉至少一叶。

| | 值 |
|--|---:|
| 正例组数 / 占比 | 81 / 93.1% |

### 4.1 在多金标组内的召回（上界乐观）

| 门控 | trigger | P | R | F1 |
|------|--------:|------:|------:|------:|
| `gate_l1_rank1` | 55.2% | 95.8% | 56.8% | 71.3% |
| `gate_l1_rank_le2` | 78.2% | 95.6% | 80.2% | 87.2% |
| `gate_crowd` | 93.1% | 92.6% | 92.6% | 92.6% |
| `gate_leaf_close` | 93.1% | 92.6% | 92.6% | 92.6% |
| `gate_mass_ge015` | 90.8% | 94.9% | 92.6% | 93.8% |
| `gate_mass_ge025` | 70.1% | 95.1% | 71.6% | 81.7% |
| `gate_rank1_and_crowd` | 50.6% | 95.5% | 51.9% | 67.2% |
| `gate_rank1_and_leaf_close` | 50.6% | 95.5% | 51.9% | 67.2% |
| `gate_rank1_and_mass025_and_close` | 50.6% | 95.5% | 51.9% | 67.2% |
| `gate_rank2_and_crowd_or_close` | 71.3% | 95.2% | 72.8% | 82.5% |

说明：`gate_crowd` / `gate_leaf_close` 在多金标组内接近恒真（近同义反复），**不能**单独当门控。

### 4.2 全库 L1 轴上的误扩成本（更关键）

全 `shared_trees`：**449** 条 L1 轴 / 100 例。

| 门控 | 触发轴数 | 轴触发率 | 落在多金标 L1 | 相对多金标精确率* |
|------|--------:|--------:|-------------:|-----------------:|
| `gate_l1_rank1` | 100 | 22.3% | 48 | 48.0% |
| `gate_l1_rank_le2` | 200 | 44.5% | 68 | 34.0% |
| `gate_rank1_and_leaf_close` | 91 | 20.3% | 44 | 48.4% |
| `gate_rank2_and_crowd_or_close` | 180 | 40.1% | 62 | 34.4% |

\*精确率 = 触发轴中属于「同 L1 多金标组」的比例（金标盲部署时的代理 P）。

| 扩池策略 | 均值池大小（label-dedup） |
|----------|-------------------------:|
| 每 L1 top1 | 4.45 |
| 选择性 combo（推荐动作） | 6.20 |
| 全体 L1 top2（已证实伤 F1） | 8.86 |

选择性 combo：每例平均扩 **1.80** 个 L1；池均值 6.20（介于 top1 与全局 top2 之间）。

### 推荐候选

- **谓词**：`l1_rank<=2 AND (n_competitive_leaves>=2 OR leaf2/leaf1>=0.35); L1 rank by leaf-mass`
- **动作**：keep per-L1 top2 for that parent only; other L1s stay top1; then compress global shortlist to K
- **多金标组内**：P=95.2% R=72.8% F1=82.5%
- **全库代理 P**：34.4%（62/180 触发轴落在多金标 L1）
- **更省触发**：`gate_rank1_and_leaf_close` 全库代理 P=48.4%，轴触发率 20.3%
- **状态**：`research_candidate` — 实现 **selective per-L1 top2** 后再压 K；勿全局 top2。
- **caveat**：Within multi-gold groups, crowd/close are near-tautological; use universe_gate_stats for false-expand cost. Prefer selective expand over global per-L1 top2.

## 一句话

多金标 L1 多为 **leaf-mass 靠前轴**（rank≤2 约 78.2%），金标叶落在族内 top-2 约 **70.8%**；可做金标盲门控，但必须看全库误扩——推荐 **选择性 top2**（池 ~6.2）而非全体 L1 top2（池 ~8.9）。

