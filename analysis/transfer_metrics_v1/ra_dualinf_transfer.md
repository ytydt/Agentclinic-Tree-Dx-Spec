# RA Dual-Inf 机制迁移消融报告

协议：`ra_dualinf_backward_verify_v1` + follow-up `ra_dualinf_conditional_gate_v1` / `ra_live_s3_coverage_v1`  
锚点：`logs/rarearena_ra_rdc_seq100_v1/compat_synonym_v1` LLM Acc = **0.47**（正式保留，未覆盖）  
机器表：[`ra_dualinf_transfer.json`](ra_dualinf_transfer.json)

## 1. 根因回顾（迁移前）

| 现象 | 数值 |
|------|------|
| Ours / B04 LLM Acc | 0.47 / 0.47（交集 35，并集 59） |
| gold 进候选 / top-1 | 58 → 43（转化率 74%；B04 45→42 = 93%） |
| `final_ranking` 均长 | 1.85（93/100 短于家族数） |
| `explanatory_coverage` | 2994/2994 分支恒为 0 |
| Lex miss 分解 | 无叶 26 + 组内 16 + 仲裁降位 15 |

## 2. 已实现改动

| 步骤 | 内容 | 路径 |
|------|------|------|
| **S1** | compat `pred_ddx` 用后验叶补齐到 k；`fill_source∈{arbiter,posterior_pad}`；**不改 top-1** | `scripts/paper/build_eval_projection.py` |
| **S2** | 冻结树 + Dual-Inf backward/examine 重排（champions / all_leaves） | `scripts/paper/run_ra_backward_verify_rerank.py` |
| **S3** | `_annotate_scope` 写回 `explanatory_coverage`；组内 champion 优先 coverage；仲裁 audit 透出 | `eval_l2_competition_strategies.py` / `diagnosisarena_l2_pipeline.py` / `eval_l2_joint_dynamic_pipeline.py` |
| **S4** | top-1 支持 ≤β 或与 top-2 持平 → 再 examine 一轮 | 同上 rerank 脚本（`--beta 2`） |
| **Gate** | 仅当 `support(challenger)−support(arbiter)≥δ` 且 challenger∈padded ddx 时覆盖 | `scripts/paper/run_ra_dualinf_conditional_gate.py` |
| **Live S3** | 冻结 VP/树/P5 后 live 重标（F6 预算） | `scripts/paper/run_ra_live_s3_coverage.py` |

S1 实测：97/100 例被 pad，均长 1.85→**5.0**；top-1 与仲裁一致。

## 3. 主结果（LLM Acc @ ddx_k=5）

| 臂 | Lex Acc@1 | Lex hit@5 | **LLM Acc** | Hits | 注 |
|----|----------:|----------:|------------:|-----:|----|
| Baseline Ours (F6) | 0.41* | — | **0.47** | 47 | 正式锚点 |
| B04-dual-inf | — | — | **0.47** | 47 | — |
| S2 champions | 0.42 | 0.56 | **0.47** | 47 | 净零 +9/−9 |
| S2 all_leaves | 0.41 | 0.70 | **0.43** | 43 | 噪声池扩大 |
| **Gate champions δ=2** | 0.44 | 0.72 | **0.49** | 49 | 覆盖 18 例；+6/−4 |
| **Live S3** | — | — | **0.46** | 46 | top-1 变 19；+8/−9 |

\* Lexical 树 top-1 约 0.41；LLM judge 抬到 0.47。

**结论：**
- 无条件 Dual-Inf 重排（S2）打不平局；all_leaves 更差。
- **条件融合门是唯一超过 0.47 的臂（0.49）**，仍作侧跑；正式锚点暂不覆盖。
- Live S3 单独启用 coverage 排序 **未抬分**（0.46）。

## 4. 条件融合门（δ=2, champions）

规则：`support(challenger) − support(arbiter_top1) ≥ 2` **且** challenger ∈ S1-padded ddx → 覆盖 top-1。

| 项 | 值 |
|----|---:|
| 覆盖例数 | 18/100 |
| Lex Acc@1 / hit@5 | 0.44 / 0.72 |
| LLM Acc | **0.49**（相对 F6 +0.02） |
| vs F6 翻转 | gain 6 / loss 4（含 1 例非覆盖 judge 噪声：case 22） |

覆盖例中有效翻转：

- gain：24 Cushing、26 LPD、40 Wilms、73 Primary peritoneal、83 Castleman、99 Mucormycosis
- loss：3 Liposarcoma←Desmoid、36 Ovarian Fibroma、84 Middle Aortic Syndrome

侧跑目录：`logs/rarearena_ra_rdc_seq100_v1/dualinf_conditional_gate_v1/`

## 5. Live S3

预算与正式 RA 相同：L1=6 / local=4 / between=2 / cand=6。  
中途 6 例因空 evidence 路径 bug（`for b in branches` 把 dict key 当 branch）失败；已修 `diagnosisarena_l2_pipeline.py` 后 resume → **100 OK**。

| 项 | 值 |
|----|---:|
| LLM Acc | **0.46** |
| vs F6 | +8 / −9（net −1） |
| top-1 相对 F6 变更 | 19/100 |
| 树中 coverage>0 的病例 | 6/100（75 个非零分支 / 2225 零） |

coverage 信号稀疏：多数病例 annotate 仍写回 0，组内/仲裁排序几乎退化为原后验 → Acc 接近但不优于 F6。

侧跑目录：`logs/rarearena_ra_rdc_seq100_v1/compat_synonym_s3_coverage_live_v1/`

## 6. 逐例翻转（S2 champions vs Ours LLM）

### Champions（gain 9 / loss 9 / net 0）

收回的典型近邻混淆（与 B04 独赢重叠）：83 Castleman、24 Cushing、76 Intraocular lymphoma、73 Primary peritoneal、99 Mucormycosis、5 Malaria。  
丢掉的典型罕见具名实体：3/35 Desmoid、21 Inflammatory Pseudotumor、66 Familial combined hyperlipidemia、75 Neuroendocrine。

### B04 独赢 12 例回收

| 池 | 回收 |
|----|------|
| champions | **6/12** |
| all_leaves | **6/12** |

## 7. Oracle / 上限

| 上限 | Acc |
|------|----:|
| gold 在叶 | 0.74 |
| gold 在 champion 池 | 0.58 |
| Ours ∪ B04 | 0.59 |
| Gate δ=2（实测） | 0.49 |
| 本迁移无条件重排 | 0.47 |

## 8. 离线混合门控（无新调用，历史）

| 策略 | Lex hits |
|------|--------:|
| champ Δ≥1 / 2 / 3 | 43 / 44 / 46 |
| leaves Δ≥1 / 2 / 3 | 40 / 42 / 44 |

门控 Lex 略好；**LLM 侧跑后 δ=2 champions 确认为 +0.02**。

## 9. 机制解读

1. Dual-Inf 优势在「承诺」：近邻混淆上 examine 能纠正仲裁倒置；无条件按支持数排序会对称毁掉罕见实体召回。
2. **条件门**用支持差阈值 + padded-ddx 约束，保留多数树 top-1，只在高置信 challenger 时覆盖 → 首次打穿 0.47。
3. **S3 coverage** 作为原生零额外调用信号目前过于稀疏，单独不足以抬分。
4. Orpha 上位词无叶（~26）仍是共同天花板；本迁移不处理。

## 10. 决策与下一步

- **正式锚点仍为 F6 Acc=0.47**（未覆盖主 run）。
- 侧跑最优：**条件融合门 0.49**（δ∈{1,2,3} 全同；推荐 δ=3）。后续四方尸检见 [`ra_rootcause_mechanisms.md`](ra_rootcause_mechanisms.md)：Pair/Grain/Combo 均未破 0.49，瓶颈转向无叶+组内。
- 可选：Orpha 无叶 emit / 类别名对齐（天花板工程）；ensemble（Ours∪B04 oracle 0.59）。

## 11. 复现

```bash
# S2+S4（已跑）
PYTHONPATH=src:scripts/paper python3 scripts/paper/run_ra_backward_verify_rerank.py \
  --workers 16 --judge-workers 50

# 条件门 δ=2
PYTHONPATH=src:scripts/paper python3 scripts/paper/run_ra_dualinf_conditional_gate.py \
  --pool champions --delta 2 --judge-workers 50

# Live S3
PYTHONPATH=src:scripts/paper python3 scripts/paper/run_ra_live_s3_coverage.py \
  --workers 4 --judge-workers 50
```

产物：

- `logs/rarearena_ra_rdc_seq100_v1/dualinf_backward_verify_v1/`
- `logs/rarearena_ra_rdc_seq100_v1/dualinf_conditional_gate_v1/`
- `logs/rarearena_ra_rdc_seq100_v1/compat_synonym_s3_coverage_live_v1/`
- `analysis/transfer_metrics_v1/ra_dualinf_transfer.{md,json}`
