# R2 反害根因（离线漏斗）

**协议**：[`protocol.md`](protocol.md) · **分型**：[`failure_taxonomy.md`](failure_taxonomy.md) · M2 绑定层过宽

## 钉死数字

- compat option @1/@2 = **0.72 / 0.78**
- typed inject option @1/@2 = **0.42 / 0.69**（Δ@1=**-0.30**，Δ@2=**-0.09**）
- mean `n_extra` ≈ **16.1**（全树叶倾倒）
- 门控：REJECT；生产默认 **off**（见 smoke_typed_remap summary）

## @1 四象限分层（n=100）

| 分层 | n | 含义 |
|------|---|------|
| compat_hit_typed_miss | 39 | 基线对 → 注入后错（**主伤害桶**） |
| compat_miss_typed_hit | 9 | 基线错 → 注入后对（救援） |
| both_hit | 33 | 双对 |
| both_miss | 19 | 双错 |

- 净 @1 转移（救援−伤害）/n = **-0.300**
- 伤害桶 mean n_extra=15.8；救援桶=16.1；双对=16.3

## 机制信号（对假设电池）

| 信号 | 全表 | 伤害桶 | 解读 |
|------|------|--------|------|
| gold relation 翻转率 | 0.44 | 0.36 | H2 关系翻转 |
| 全选项 matched 叶 Jaccard | 0.185 | 0.183 | 绑定叶集被重写 |
| harm 中 unbind 风格（金标无related/无叶） | — | 2/39 | 接近 M1 假 MISS 再现 |
| harm 中有匹配但秩变差 | — | 34/39 | H3 秩重排 |
| harm 金标叶相对 ranking 新入率 | — | 0.77 | H1 噪声/新叶 |

### 伤害例抽样（最多 8）

| case | Δrank | rel compat→typed | n_extra | Jaccard |
|------|-------|------------------|---------|---------|
| 118 | 3 | subtype_of→subtype_of | 18 | 0.125 |
| 194 | 3 | subtype_of→unrelated | 15 | 0.167 |
| 7 | 3 | equivalent→equivalent | 15 | 0.222 |
| 28 | 3 | equivalent→equivalent | 17 | 0.250 |
| 21 | 2 | subtype_of→equivalent | 15 | 0.000 |
| 181 | 2 | equivalent→subtype_of | 15 | 0.000 |
| 190 | 2 | equivalent→equivalent | 17 | 0.143 |
| 207 | 2 | supertype_of→equivalent | 15 | 0.143 |

### 救援例（compat miss → typed hit）

74, 90, 117, 125, 151, 187, 198, 205, 229

## 工作结论（本轮离线）

1. **反害主因是净转移为负**：伤害桶远大于救援桶（见分层表）。
2. **全树注入（mean_extra≈16）** 与 matched 叶 Jaccard 偏低同时出现 → 支持 **H1 噪声叶稀释 / M2 绑定过宽**。
3. **H3 强**：伤害桶 34/39 仍有匹配叶但秩变差；**H2 弱**：relation 翻转在救援桶更高（0.56）而非伤害桶（0.36）。
4. **H4**：UNBIND∩伤害=**0**；救援例含部分 UNBIND（见 TSV）→ 子集或受益、全局净负，禁止默认全表注入。

## I1 落地后验（Pilot24）

见 [`smoke_i1_restricted/report.md`](smoke_i1_restricted/report.md)：受限注入 mean_extra **3.3**（全树 ~16.8），option 仍 **0.417/0.542** vs Pilot compat 0.75/0.75（Δ@1=−0.33）→ **REJECT**。压叶不够消除 typed 重跑秩扰动。

## 旁证臂（非 R2 主轴）

### R1（无效-度量）

- 仅父集/ coverage 协议 bump；live option 仍绑 compat **0.72/0.78**。
- 闭合为 **无效-度量**（M1），不进入注入修复。

### R3（无效-轴）

```json
{
  "protocol": "r3_gapfill_lite_v1",
  "verdict": {
    "unbind_coverage_lever": "REJECT",
    "unbind_reason": "All 18 MAPPER_UNBIND cases already have clinical/tree parents; R3 cannot repair AutoCoverage for mapper false MISS.",
    "absent_subset": "REJECT",
    "absent_reason": "Frozen trees already used branch_mode=recall_hints_gap (gap_fill ON); cases 67 and 231 remain clinical TREE_PARENT_ABSENT (axis mismatch). R3 does not fix wrong MECE axis when gold-ish hints exist (231) or when sepsis-like hints fail to force a systemic-shock L1 (67).",
    "production_default": "leave_unchanged",
    "claim_allowed": false
  },
  "build_note": "Frozen DiagnosisArena shared_trees were built with gap_fill ON. Re-running identical R3-on rebuild is non-informative; ABSENT persistence under R3-on is decisive.",
  "unbind_n": 18,
  "absent_case_ids": [
    "231",
    "67"
  ],
  "gap_fill_already_on": true
}
```

### R4/R5 Track C（上界≠可实现）

```json
{
  "upper_keys": [
    "arms",
    "generated_at",
    "protocol",
    "verdict"
  ],
  "live_keys": [
    "arms",
    "generated_at",
    "model",
    "verdict"
  ],
  "note": "See smoke_track_c/report.md: upper-bound PASS vs live FAIL on ABSENT 67/231"
}
```

## 复现

```bash
PYTHONPATH=src:scripts/paper:scripts \
  python3 -u scripts/paper/audit_recall_failure_funnel.py
```

明细：[`r2_harm_case_audit.tsv`](r2_harm_case_audit.tsv) · [`r2_harm_funnel_summary.json`](r2_harm_funnel_summary.json)
