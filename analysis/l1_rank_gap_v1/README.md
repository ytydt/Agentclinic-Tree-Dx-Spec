# L1 排序缺口调研（l1_rank_gap_v1）

决策锁定：**1C** 双漏斗 / **2C⊃B** 双轨外部机制 / **3A** 调研设计已完成；Track B **已实现并烟测**。

## 关键数字（d2_seq100，`v1_auto_parent`）

| 指标 | 值 |
|------|---:|
| family @1 / @2 | **0.60 / 0.70** |
| family @1/@2 \| coverage (n=80) | **0.75 / 0.875** |
| L1-prior option @1/@2 | 0.60 / 0.69 |
| 漏斗 | MISS 20 · MISRANK 10 · OK∧opt_miss 10 · OK∧hit 60 |

## Track B 烟测（Pilot24）

| 项 | 结果 |
|----|------|
| 实现 | `l1_family_calibration.py` + `--l1-calib`（默认 **off**） |
| b12 vs ours | family @1/@2 **无增益**（0.583/0.667） |
| 门控 | **REJECT**（79% skip；见 [`l1_calib_smoke_report.md`](l1_calib_smoke_report.md)） |
| 消融 | tau∈{0.15,0.05,0} + force-MISRANK → **仍 REJECT**；tau=0 **反害**（见 [`l1_calib_ablation_summary.json`](l1_calib_ablation_summary.json)） |
| all100 | 跳过 |
| 备份 | `backups/compat_parallel_before_l1_calib_20260723_230115/` |

## 交付索引

| 文件 | 阶段 |
|------|------|
| [`protocol.md`](protocol.md) | A |
| [`l1_family_metrics.tsv`](l1_family_metrics.tsv) / [`l1_family_summary.json`](l1_family_summary.json) / [`l1_rank_gap_audit.md`](l1_rank_gap_audit.md) | B |
| [`ours_l1_ranking_mechanism_card.md`](ours_l1_ranking_mechanism_card.md) | C |
| [`external_l1_transfer_cards.md`](external_l1_transfer_cards.md) | D |
| [`l1_related_work_transfer.md`](l1_related_work_transfer.md) | E |
| [`l1_weakness_rootcause.md`](l1_weakness_rootcause.md) / [`l1_improvement_design_v1.md`](l1_improvement_design_v1.md) | F |
| [`l1_improvement_smoke_spec.md`](l1_improvement_smoke_spec.md) / [`l1_calib_smoke_report.md`](l1_calib_smoke_report.md) | G + 实测 |
| [`l1_calib_ablation_summary.json`](l1_calib_ablation_summary.json) | B12 消融 |
| [`../../scripts/paper/audit_l1_rank_gap.py`](../../scripts/paper/audit_l1_rank_gap.py) | 审计脚本 |
| [`../../scripts/paper/l1_family_calibration.py`](../../scripts/paper/l1_family_calibration.py) | Track B 实现 |

## 状态

B12 消融已关闭「可救 option」叙事；生产默认保持 **off**。召回侧 R3/R4/R5 见 [`../l1_gold_recall_v1/README.md`](../l1_gold_recall_v1/README.md)。
