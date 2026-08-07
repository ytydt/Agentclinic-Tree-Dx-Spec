# RA 孤立组内评测（离线，主测 L2 叶列表）

协议：`ra_within_family_offline_v1`
主测：`/data2/wanghongyi/Agentclinic-Tree-Dx-Spec/logs/rarearena_ra_rdc_seq100_v1/compat_synonym_v1`

## 设定

| 项 | 值 |
|----|----|
| 队列 | 未缺叶 ∩ L1 mass-rank#1 = gold 家族 |
| n | **66** |
| L2 叶来源 | 主测 `shared_trees` 中 gold L1 的 `children`（已标注后验） |
| 证据预算扫描 | **不做**（已停止 live F4→F10） |
| 评测范围 | 仅 gold 所在 L1 族内叶排序 |

## 主结果

| 指标 | 值 |
|------|---:|
| **within-fam Acc** | **0.6212** (41/66) |
| within hit@2 | 0.8030 |
| within hit@3 | 0.9242 |
| within hit@5 | 0.9848 |
| mean / median within-rank | 1.879 / 1.0 |
| 均 L2 叶数（gold 族） | 5.955 |
| 同队列 global lex Acc | 0.6212 |
| 同队列 LLM Acc | 0.5758 |
| within✓ 但 global lex✗ | 0 |

## 读法

- within-fam Acc：只在 gold 家族的已标注 L2 叶里取后验 top-1，是否命中 gold。
- 与 global Acc 对比：若 within 高、global 低 → 瓶颈在组间/联合排序；反之 → 组内叶判别。
- 本评测**固定**主测叶列表与后验，不重跑组内选证；不能替代 live local-F 扫描。

## 边界

- Live `within_local_f4..f10` 扫描已按用户要求停止。
- `local_champion_recall` 等 auto_metrics 仅作附录对照。

