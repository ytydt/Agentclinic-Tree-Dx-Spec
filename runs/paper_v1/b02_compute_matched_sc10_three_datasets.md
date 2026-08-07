# B02 compute-matched 10-SC：三分集汇总

生成：2026-07-27。Harness：`scripts/paper/run_b02_compute_matched_sc10.sh`（默认 `DATASETS=diagnosisarena,open_xddx,medcasereasoning`）。

## 状态

| 数据集 | 目录 | n | G5 | sc_samples | sample0 复用 matched | 均值 llm_calls |
|---|---|---:|---|---:|---:|---:|
| DiagnosisArena | `diagnosisarena_b02_compute_matched_sc10_v1/` | 100 | **PASS** | 10 | 100/100 | 92.4 |
| Open-XDDx | `open_xddx_b02_compute_matched_sc10_v1/` | 100 | **PASS** | 10 | 100/100 | 89.8 |
| MedCaseReasoning | `medcasereasoning_b02_compute_matched_sc10_v1/` | 100 | **PASS** | 10 | 100/100 | 93.2 |

## 缓存机制（已启用）

1. **推理 resume**：`RESUME=1` → `run_baseline.py --resume` + 磁盘 `cache/`（`SimpleCachedLLM`）。
2. **SC 轨迹键隔离**：`_ScTrajCache` 给每条 traj 加 `sc_traj` / module 后缀，避免 10 条轨迹互相撞缓存。
3. **sample0 种子**：`--sc-seed-pred-dir` 指向单轨 `B02-flat-compute-matched`，不再重跑 sample0（三集 trace 均 `reused_from=B02-flat-compute-matched`）。
4. **评测复用**：答案与 matched 相同的病例跳过 judge/mapper（DA 58、OX 10、MCR 56）；OX/MCR 另用 `--resume-scores`。

## 主指标（matched → sc10；**均为无 synonym_bind 的正式评测**）

| 数据集 | 指标（无 bind） | matched | **sc10** | Δ | 评测产物 |
|---|---|---:|---:|---:|---|
| DA | Mapper @1 / @2 | 0.48 / 0.59 | **0.47 / 0.59** | −0.01 / 0 | `…/mapper/`（`typed_llm_disagreement_rag`） |
| OX | micro-F1 | 0.479 | **0.487** | +0.008 | `…/annotate/official_eval_llm/` |
| MCR | Acc (single traj.) | 0.17 | **0.15** | −0.02 | `…/annotate/official_eval_llm/` |

> **说明**：SC10 主读上表（无 bind）。DA 另有离线 `mapper_synonym_bind/`（pair 修后 sc10 @1=0.49），仅作与 Ours+bind 对齐对照，不替代正式无 bind 行。OX/MCR 无 mapper synonym_bind 协议。  
> OX Interp Acc：matched 0.445 → sc10 0.044（RRF 聚合后解释投影变稀；诊断 micro-F1 略升）。

### DA sc10：无 bind vs bind（pair 修后）

| 臂 | @1 | @2 | MRR@2 | 路径 |
|---|---:|---:|---:|---|
| sc10 **无 bind** | **0.47** | **0.59** | 0.530 | `mapper/` |
| sc10 + synonym_bind | 0.49 | 0.64 | 0.565 | `mapper_synonym_bind/` |

## 重跑

```bash
# 默认三分集；已有产物则 resume + 评测复用
bash scripts/paper/run_b02_compute_matched_sc10.sh

# 单集
DATASETS=open_xddx bash scripts/paper/run_b02_compute_matched_sc10.sh
DATASETS=medcasereasoning bash scripts/paper/run_b02_compute_matched_sc10.sh
```
