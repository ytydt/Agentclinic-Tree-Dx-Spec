# OX C2a：入口已知未落叶 — 改进方案离线测试

状态：离线仿真完成（无 live Creator；控制器已加 opt-in force-emit）
日期：2026-07-26
范围：`ox_seq100` × `compat_synonym_v1`；judge=`lexical`
协议：`ox_c2a_force_emit_offline_v2`
机器表：[`ox_c2a_force_emit.json`](ox_c2a_force_emit.json)

---

## 0. 问题与方案

C2a（n=23 金标边）：入口 `llm_ddx` / `RecallGapAssign(index=-1)` 已见金标，但 Creator 缓存从未写出叶。

| 方案 | 机制 |
|------|------|
| **A0** oracle | 注入 C2a 金标名（上界） |
| **A1_raw** | 缓存内全部 gap_uncovered（诊断用；跨 call 聚合，偏宽） |
| **A1t** | **ddx ∩ gap_uncovered** 且不在树（贴 C2a） |
| **A1b** | A1t 每例最多 3 条 |
| **A2b** | ddx∪gap 每例最多 3 条 |
| **A3** | A1t + 假覆盖回退（covered 但子叶匹配 <0.7） |

工程落地：`ControllerConfig.l2_gap_force_emit_uncovered`（默认 OFF）——gap repair 拒绝/失败/仍未覆盖时 **确定性 append** uncovered 名。

---

## 1. C2a 边救援（全树匹配 ≥0.7）

| 臂 | 新救援 / 在树 |
|----|-------------:|
| A0 oracle | 23 / 23 |
| A1_raw（宽） | 13 / 13 |
| **A1t ddx∩gap** | **10 / 10** |
| A1b budget3 | 6 / 6 |
| A2b entrance≤3 | 4 / 4 |
| A3 +false-cover | 11 / 11 |

注入量：见 json `inject_stats`。

---

## 2. 全队列 lexical 指标

### 2.1 全树召回

| 臂 | micro-R | TP | ΔR (pp) |
|----|--------:|---:|--------:|
| baseline | 0.704 | 330 | +0.0 |
| A0_oracle_c2a_gold | 0.753 | 353 | +4.9 |
| A1_gap_raw_flood | 0.861 | 404 | +15.8 |
| A1t_ddx_and_gap | 0.849 | 398 | +14.5 |
| A1b_budget3 | 0.791 | 371 | +8.7 |
| A2_entrance_budget3 | 0.731 | 343 | +2.8 |
| A3_false_cover_on_tight | 0.851 | 399 | +14.7 |

### 2.2 后验 Top-5（低 posterior 注入，通常进不了窗）

| 臂 | P | R | F1 | ΔF1 (pp) |
|----|--:|--:|---:|---------:|
| baseline | 0.444 | 0.473 | 0.458 | +0.0 |
| A0_oracle_c2a_gold | 0.444 | 0.473 | 0.458 | +0.0 |
| A1_gap_raw_flood | 0.444 | 0.473 | 0.458 | +0.0 |
| A1t_ddx_and_gap | 0.444 | 0.473 | 0.458 | +0.0 |
| A1b_budget3 | 0.444 | 0.473 | 0.458 | +0.0 |
| A2_entrance_budget3 | 0.444 | 0.473 | 0.458 | +0.0 |
| A3_false_cover_on_tight | 0.444 | 0.473 | 0.458 | +0.0 |

### 2.3 Boost Top-5（末位强制塞入；测进窗价值）

| 臂 | P | R | F1 | ΔF1 (pp) |
|----|--:|--:|---:|---------:|
| A0_oracle_c2a_gold | 0.482 | 0.514 | 0.497 | +3.9 |
| A1_gap_raw_flood | 0.360 | 0.384 | 0.372 | -8.7 |
| A1t_ddx_and_gap | 0.406 | 0.433 | 0.419 | -3.9 |
| A1b_budget3 | 0.406 | 0.433 | 0.419 | -3.9 |
| A2_entrance_budget3 | 0.360 | 0.384 | 0.372 | -8.7 |
| A3_false_cover_on_tight | 0.402 | 0.429 | 0.415 | -4.3 |

---

## 3. 裁定

1. **推荐工程默认候选：A1t / force-emit uncovered**（ddx∩gap 或单次 gap 调用的 uncovered 列表）——对准 C2a，且单次 parent 调用量小，不是缓存全量 flood。
2. **A1_raw 不可直接上线**：跨 call 聚合 mean≈26 条/例，全树 R 虚高、boost 严重伤 F1。
3. **仅补叶不够进 Top-K**：低 posterior 注入不改短列表 F1；需后续联合重排，或对 **限量（≤3）** 做 boost。A0/A1b 的 boost 才可能正增益。
4. **A3 假覆盖回退**对少数 C2a（如 case63 TB 假 covered）有增量；可与 force-emit 叠加。
5. 剩余 C2a（仅 ddx、无 gap_unc）靠 A2b/扩入口，不靠 gap force-emit。

## 4. 复现

```bash
PYTHONPATH=src:scripts/paper python3 scripts/paper/audit_ox_c2a_force_emit.py \
  --run-dir logs/open_xddx_ox_seq100_v1/compat_synonym_v1 --ddx-k 5
```

控制器开关：`l2_gap_force_emit_uncovered=True`（需同时 `l2_recall_gap_fill=True`）。

