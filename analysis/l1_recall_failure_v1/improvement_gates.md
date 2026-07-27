# 改进措施门控（规格 + 实测）

**生产默认仍 off。** 正式宣称数字仍绑 compat **0.72/0.78**。Approach A 已过门为 **default_candidate**，未 enable。

**上游**：[`hypothesis_battery.md`](hypothesis_battery.md) · [`r2_harm_rootcause.md`](r2_harm_rootcause.md)

---

## 总表

| 改进 ID | 触发条件 | 做法草案 | 验收门 | 默认 | 本轮实测 |
|---------|----------|----------|--------|------|----------|
| **I1** 受限注入 | H1/H4 成立 | 仅注入近义/高分叶，禁全树倾倒 | Pilot24 typed Δ@1≥0 且 Δ@2≥−0.01 | **off** | **REJECT**（见下） |
| **I2** 绑定护栏 | H2 成立（弱） | 高置信 unrelated 抽检/冻结 | UNBIND↓ 且 option 不跌 | **off** | 未做 |
| **Synonym-KB mapper** | UNBIND / 粒度 | 选项↔叶同义 chunks + 对称 critic | Pilot Δ@1≥0 且 Δ@2≥−0.01 | **off** | **REJECT**（见下） |
| **Approach A** 同义修绑→rematch | UNBIND / 假 MISS | 冻结 compat 叶序上 synonym/bridge bind-repair，**不重跑 typed**；harness=`--synonym-bind-repair` | Pilot→all100：Δ@1≥0 且 Δ@2≥−0.01，且 @1↑或 matched↑ | **off**（候选；已挂 harness） | frozen **PASS**；**live PASS 0.81/0.93** |
| **I3** 度量双列 | R1 类 | TreeParentPresent vs AutoCoverage 分列 | 文档分列 | 文档已钉 | **DONE** |
| **I4** 轴注入白名单 | H5/H6 | ABSENT 配置极 | ABSENT TPP≥1 + option 护栏 | **off** | 未做 |
| **I5** 禁止混比 | 协议 | rematch/typed/merge_only 分表 | 审查清单 | **强制** | **DONE** |

---

## I1 受限注入 — Pilot24 实测 **REJECT**

报告：[`smoke_i1_restricted/report.md`](smoke_i1_restricted/report.md)  
实现：`build_injected_leaves(mode=restricted_option_synonym, max_extra=5, min_score=0.70)`  
脚本：`run_l1_gold_recall_typed_remap.py --inject-mode restricted`

| 臂 | @1 | @2 | mean_extra |
|----|---:|---:|-----------:|
| R_compat（Pilot24） | 0.750 | 0.750 | — |
| R_compat_inject_restricted_typed | **0.417** | **0.542** | **3.29** |
| （对照）全树 R2 typed Pilot24 | ~0.42 量级反害 | — | ~16 |

- **Δ@1=−0.333**、**Δ@2=−0.208** → I1 门 FAIL  
- mean_extra 已从 ~16 压到 **3.3**，但 option 仍大跌 → **仅减噪声叶不足以消除 typed 重跑反害**（H3 秩重排仍主导）  
- **保持 off**；禁止用事后 rematch 补救宣称；**不**自动 escalate all100  

复现：

```bash
PYTHONPATH=src:scripts/paper:scripts \
  python3 -u scripts/paper/run_l1_gold_recall_typed_remap.py \
    --cohort pilot24 --inject-mode restricted --workers 8 --resume
```

---

## Synonym-KB mapper — Pilot24 实测 **REJECT**

报告：[`smoke_synonym_kb/report.md`](smoke_synonym_kb/report.md)  
协议：冻结 compat `final_ranking`（无叶注入）→ `typed_llm` vs `typed_llm_synonym_kb`  
实现：`SynonymGranularityRetriever` + 全选项对称 critic（`disease_name_bridge`）

| 臂 | @1 | @2 | gold_matched |
|----|---:|---:|-------------:|
| typed_llm | 0.542 | 0.750 | 0.750 |
| typed_llm_synonym_kb | **0.542** | **0.708** | **0.708** |

- Δ@1=0、Δ@2=−0.042 → 门 FAIL；matched 未升（case 5 仍 UNBIND）  
- **保持 off**；不 escalate all100  

```bash
PYTHONPATH=src:scripts/paper:scripts \
  python3 -u scripts/paper/run_mapper_synonym_kb_smoke.py \
    --cohort pilot24 --workers 8 --resume
```

---

## Approach A：同义修绑 → rematch — frozen **PASS** + live **PASS**（默认仍 off）

### Frozen rematch A/B

报告：[`smoke_synonym_bind_rematch/report.md`](smoke_synonym_bind_rematch/report.md)  
实现：`apply_synonym_bind_repair_to_mapper` + `run_synonym_bind_rematch_smoke.py`  
协议：冻结 `case_results.final_ranking` + 冻结 mapper → lexical/`disease_name_bridge` 修绑 → rematch（**无 typed LLM**）  
注意：绝对数 ≠ 正式 compat_parallel live（I5 分表）。

| cohort | 臂 | @1 | @2 | gold_matched | gate |
|--------|----|---:|---:|-------------:|------|
| Pilot24 | R_compat_rematch | 0.583 | 0.750 | 0.750 | — |
| Pilot24 | R_compat_synonym_bind_rematch | **0.750** | **0.958** | **1.000** | **PASS** |
| all100（n=99，跳过空 ranking case 97） | R_compat_rematch | 0.596 | 0.788 | 0.798 | — |
| all100 | R_compat_synonym_bind_rematch | **0.687** | **0.949** | **0.980** | **PASS** |

### Live（compat_parallel 口径，对齐正式主表）

报告：[`smoke_synonym_bind_live/report.md`](smoke_synonym_bind_live/report.md)  
脚本：`run_synonym_bind_live_smoke.py`（at1_compat cache；`gold_g2=off`；无 typed）

| cohort | 臂 | @1 | @2 | gold_matched | gate |
|--------|----|---:|---:|-------------:|------|
| Pilot24 | R_compat_live | 0.750 | 0.750 | 0.750 | — |
| Pilot24 | R_compat_synonym_bind_live | **0.917** | **0.958** | **0.958** | **PASS** |
| all100 (n=100) | R_compat_live | 0.710 | 0.780 | 0.790 | — |
| all100 | **R_compat_synonym_bind_live** | **0.810** | **0.930** | **0.950** | **PASS** |
| formal anchor | compat_parallel | 0.72 | 0.78 | — | — |

- live all100 vs 本跑 compat：Δ@1=**+0.100**、Δ@2=**+0.150**；vs 正式锚 0.72/0.78：Δ@1=**+0.090**、Δ@2=**+0.150**  
- @1 救援 12 / 伤害 2；case 97 空 ranking 按 at1 计 miss 0/0  
- 本跑 compat 复现 **0.71/0.78**（vs 正式 0.72/0.78；仅 case **214** @1 差 1）  
- **default_candidate=true**；**production_default 仍 off**  
- **Harness 已挂接**（默认 off）：mapper `--synonym-bind-repair` / staged 同名旗标 → `rescore_after_synonym_bind`  
- **机制专论**：[`synonym_bind_repair_mechanism_explainer.md`](synonym_bind_repair_mechanism_explainer.md)（完整算法、起效构件、实测根因）

```bash
# frozen smoke
PYTHONPATH=src:scripts/paper:scripts \
  python3 -u scripts/paper/run_synonym_bind_rematch_smoke.py \
    --cohort pilot24 --auto-escalate

# live smoke
PYTHONPATH=src:scripts/paper:scripts \
  python3 -u scripts/paper/run_synonym_bind_live_smoke.py \
    --cohort pilot24 --auto-escalate --dry-run

# formal harness reuse (mapper only; default off)
PYTHONPATH=src:scripts/paper:scripts \
  python3 -u scripts/paper/run_diagnosisarena_mapper_w12.py \
    --downstream-dir <annotate_or_downstream_dir> \
    --synonym-bind-repair

# or staged pipeline
PYTHONPATH=src:scripts/paper:scripts \
  python3 -u scripts/paper/run_diagnosisarena_pipeline_staged.py \
    --from-stage mapper --to-stage mapper --synonym-bind-repair
```

---

## I2 / I4

本轮不做（H2 弱；ABSENT 轴另开）。Approach A frozen+live 均过门为候选；生产默认仍需显式 enable。

---

## I3 度量双列（文档 DONE）

- AutoCoverage / `v1_auto_parent` 与 TreeParentPresent **必须分列**。  
- 18/20 Auto MISS = `MAPPER_UNBIND`（假 MISS）→ **禁止**用假 MISS 驱动默认叶注入。  
- 见 [`protocol.md`](protocol.md) §1 度量修复 + gold_recall README。

---

## I5 禁止混比（审查清单 DONE）

- [x] 主表数字同一 mapper 协议分列（typed vs rematch 不混写）  
- [x] Pilot 不外推 all100（I1 仅 Pilot；FAIL 不 escalate）  
- [x] merge_only 坍缩叶集在 B12 报告单独标注  
- [x] Approach A：frozen rematch 与 live compat 分表；live 未写回正式主表宣称（默认仍 off）
- [x] B12（排序）与召回臂分表（本包旁证，不并入召回主表）

---

## 硬规则（再钉一次）

1. 改进默认 **off**。  
2. 过 Pilot → 才允许 all100；all100 过门 → 才讨论生产默认。  
3. 不把 B12 / R2 全树注入写回默认。  
4. 不把事后 rematch 写回主表。
