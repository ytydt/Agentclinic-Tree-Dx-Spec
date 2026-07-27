# L1 改进烟测与验收规格（仅规格；本轮不执行）

**决策 3A**：本文只定义未来实现时的流程与门槛，**不跑 Pilot/all100，不改 harness 默认**。

---

## 1. 队列与锚点

| 项 | 值 |
|----|-----|
| 队列 | DiagnosisArena `d2_seq100_v1` |
| 基线 L1 | 现有 `p5_anti_anchor_direct` F6 后验（本审计锚点） |
| 协议 | [`protocol.md`](protocol.md) `v1_auto_parent`（若盲法修订父集则 bump 版本） |
| 下游 | 保持现有 L2 + `compat_parallel`；L1 臂变化时 **分列**报告 option 全链路 |

---

## 2. 臂矩阵（实现后）

| 臂 | 内容 | 轨道 |
|----|------|------|
| `l1_ours` | 当前 F6 anti-anchor | 锚点 |
| `l1_support` | B1 | B |
| `l1_pair` | B2 | B |
| `l1_b12` | B1→B2（推荐） | B |
| `l1_reflect` | B3 | B 条件 |
| `l1_council` | C1 | C |
| `l1_self_refine` | C2 | C |
| `l1_open_regen` | C3 | C（仅召回假设坐实后） |

禁止金标选臂；禁止把 C 臂默认进生产。

---

## 3. 指标

**主终点**：family @1（全量；另报 coverage 条件子集）。  
**护栏**：family @2 ≥ 锚点 − 0.01。  
**次终点**：`L1-prior-only` option @1/@2；官方 mapper option @1/@2（分列）。  
**成本**：LLM calls / tokens（相对 `l1_ours`）。  
**分桶**：漏斗桶计数变化（MISRANK↓ 为目标；MISS 不因重排「假降」——OpenRegen 另表）。

---

## 4. 流程

1. **Pilot24**（与历史 pilot 同源 24 例）：先跑 `l1_b12` vs `l1_ours`。  
2. 通过门（Pilot）：Δ family @1 ≥ +0.04 **或** MISRANK 例净减少 ≥3；family @2 不降超过 0.01；无金标泄漏。  
3. **all100**：同门槛；报告 95% bootstrap CI（配对）。  
4. Track C 臂单独 Pilot；**不得**因 C 臂失败阻塞 B 轨结论。

---

## 5. 失败与归因规则

- 若 family ↑ 但 option 代理不动：记 R6，转代表叶任务，不宣称端到端已修好。  
- 若仅 MISS 桶因映射修复而变：不得记入 L1-SupportRerank 功劳。  
- 若 @2 跌破护栏：REJECT 该臂为默认。

---

## 6. 本轮完成勾选

- [x] 协议与审计主表  
- [x] 根因与双轨设计  
- [x] 实现 `l1_family_calibration.py`（ours/support/pair/b12）  
- [x] Pilot24 烟测 → **REJECT**（见 [`l1_calib_smoke_report.md`](l1_calib_smoke_report.md)）；默认 `--l1-calib off`  
- [ ] all100（Pilot 未过门，跳过）  
- [ ] 生产默认改为 b12（禁止，直至过门）
