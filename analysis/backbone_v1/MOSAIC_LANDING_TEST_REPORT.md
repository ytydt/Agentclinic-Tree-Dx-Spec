# MOSAIC 落地测试报告（Lite + Adaptive-4）

> **口径已过时。** 正式主结果请只看 [`MOSAIC_EXPAND_REPORT.md`](MOSAIC_EXPAND_REPORT.md)（统一 **DA400 / MCR400**，含全部满 800 题方法）。本文仅保留首轮 seq100/v1 探索记录，**勿再引用其中的局部 Acc 作结论**。

依据：`DEEP_TRAJECTORY_MECHANISM_AUDIT.md`、`PROMISING_POST_AUDIT_ALGORITHM_CANDIDATES.md`  
实现：`src/agentclinic_tree_dx/mosaic.py`、`scripts/paper/run_mosaic.py`  
跑数：DA `d2_seq100`（n=100）与 MCR `mcr_v1`（n=100）；模型 `meta-llama/llama-3.3-70b-instruct`  
日期：2026-08-08

> 这是**第一轮确认性实验**，不是终局论文结果。阈值未在独立 holdout 上重锁定；800 例审计集与本 seq100 有重叠。

---

## 1. 实现了什么

| 组件 | 状态 |
|------|------|
| MOSAIC-Lite（G1∥G2 + 全局 registry + 双通道 frontier + S） | ✅ 严格 3 calls/例 |
| MOSAIC-Adaptive-4（Lite + 可选 A1 orthogonal） | ✅ 实际 3.8–3.9 calls/例 |
| 硬约束：full vignette、history 隔离、exact duplicate=0、evidence 按 ID 去重 | ✅ 单元测试 + 运行时指标 |
| 统一 mapper / MCR judge（与骨干同协议） | ✅ |
| MOSAIC-Forest / IMPC-Dx / Adaptive-4v2 | ✅ 见扩集报告 `MOSAIC_EXPAND_REPORT.md` |
| 完整 2³ 因子实验 | ❌ 本轮只做 Lite / Adaptive-4 端到端；扩集见 Forest/IMPC |

产物目录：

- `logs/backbone_v1/diagnosisarena/mosaic_lite_v1`
- `logs/backbone_v1/diagnosisarena/mosaic_adaptive4_v1`
- `logs/backbone_v1/medcasereasoning/mosaic_lite_v1`
- `logs/backbone_v1/medcasereasoning/mosaic_adaptive4_v1`
- `analysis/backbone_v1/mosaic_eval/summary_fixed.json`

---

## 2. 主结果（等预算对照）

### 2.1 DiagnosisArena seq100

| 方法 | LLM calls | concept Acc@1 | pool recall | option@1 |
|------|----------:|--------------:|------------:|---------:|
| **MOSAIC-Lite** | **3.0** | **0.34** | **0.46** | **0.63** |
| MOSAIC-Adaptive-4 | 3.8 | 0.30 | 0.46 | 0.62 |
| B07（3-call） | 3 | 0.30† / 0.22‡ | — | 0.62 |
| e7 | 6 | 0.22 | — | 0.59 |

† `r4_facts` 的 `B07_chain_correct`；‡ 与 MOSAIC 同一 `dc.match` 对 B07 `top2[0]` 重算。

**配对（concept，同 matcher）：**

- Lite vs B07：16–4，**p=0.012**（Lite 胜）
- Lite vs e7：15–3，**p=0.008**（Lite 胜）
- Adaptive vs B07：12–4，p=0.077（方向同 Lite，未显著）

### 2.2 MedCaseReasoning mcr_v1

| 方法 | LLM calls | concept Acc@1 | pool recall | Acc@1 |
|------|----------:|--------------:|------------:|------:|
| MOSAIC-Lite | 3.0 | 0.24 | 0.35 | 0.25 |
| **MOSAIC-Adaptive-4** | **3.89** | 0.24 | **0.38** | **0.28** |
| B07 | 3 | 0.29† | — | 0.24 |
| e7 | 6 | 0.21 | — | 0.28 |

配对 concept：Lite/Ada vs B07 均 n.s.；Ada vs e7 n.s.。

---

## 3. 机制指标（审计硬约束）

| 指标 | Lite DA | Ada DA | Lite MCR | Ada MCR | 目标 |
|------|--------:|-------:|---------:|--------:|------|
| exact global duplicate | 0 | 0 | 0 | 0 | 结构性 0 |
| history leakage | 0 | 0 | 0 | 0 | 结构性 0 |
| G1↔G2 Jaccard | **0.34** | 0.37 | **0.33** | 0.33 | ≪ MAC 的 0.97 |
| mean calls | 3.0 | 3.8 | 3.0 | 3.89 | ≤ 预算帽 |

解读：历史隔离后的异质视角**真的带来了多样性**（Jaccard≈0.33–0.37），与 MAC 的顺序 echo（0.972）形成对照。

---

## 4. Go / No-Go（相对候选文档 §13.3）

| 标准 | 结果 |
|------|------|
| exact duplicate = 0 | ✅ |
| history leakage = 0 | ✅ |
| 匹配预算下 concept hit 相对 e7 为正 | ✅ DA Lite；MCR 对 e7 concept 也略高 |
| 匹配预算下相对 B07 concept 为正 | ✅ DA Lite（显著）；❌ MCR（Lite 0.24 < B07 0.29） |
| Adaptive 相对 Lite 提高 final concept hit | ❌ DA 更差；MCR concept 持平，仅 task Acc 升至 0.28 |
| 只抬 task 不抬 concept → 停查 mapper | DA task 与 concept **同向**提升；MCR Adaptive 的 Acc 升而 concept 未升 → **需谨慎，不可只写 Acc 叙事** |

**阶段结论：**

1. **MOSAIC-Lite 值得作为骨干继续**——在 3-call 等预算下，DA 上同时抬高 concept 与 option@1，并显著优于 6-call 的 e7。
2. **Adaptive-4 尚未通过“相对 Lite 的 concept 增益”门**——DA 上多用 0.8 call 反而略伤 concept；MCR 上 Acc 追平 e7 但 concept 未超过 B07。下一步应修 gate（减少无效 A1）或加 A5 pairwise，而不是直接上 Forest。
3. **Forest / IMPC 暂缓**——符合文档「Lite 不过门则不要堆层次」的精神；Lite 已过 DA 门，但 Adaptive 未稳，Forest 风险更高。

---

## 5. 与审计主张的对账

| 审计主张 | 本轮是否支持 |
|----------|----------------|
| 瓶颈在保真转化而非扩池 | 支持：3-call Lite > 6-call e7（DA concept/task） |
| 完整 vignette + 真多样性有效 | 支持：Jaccard≈0.34，DA 增益 |
| 删掉 generic refine 无害 | 支持：Lite 无 refine，DA≥B07 |
| 自适应扩展应提高转化 | **本轮未证实**（Adaptive≈或劣于 Lite） |
| 多轴 Forest 是下一步 | **证据不足，延后** |

---

## 6. 建议的下一刀实验（按优先级）

1. **Lite 扩到 DA heldout100 + MCR v2**（确认非审计污染）。
2. **修 Adaptive gate**：仅在 `unexplained_spans≥2` 且 `top_margin` 低时触发 A1；禁止高 Jaccard 时仍扩池。
3. **加 A5 pairwise verifier**（不增加 retrieval），再比 Adaptive-4。
4. 通过后再考虑 Forest；同步做 full-vignette vs S1-only 正交探针。

---

## 7. 复现命令

```bash
PYTHONPATH=src:scripts:scripts/paper \
  python3 scripts/paper/run_mosaic.py \
    --dataset diagnosisarena --arm mosaic_lite_v1 --mode lite \
    --workers 32 --score

PYTHONPATH=src:scripts:scripts/paper \
  python3 scripts/paper/run_mosaic.py \
    --dataset medcasereasoning --arm mosaic_adaptive4_v1 --mode adaptive4 \
    --workers 32 --score --mcr-judge-workers 50

python3 scripts/paper/test_mosaic_unit.py
```
