# OX：本方法落后 MAC 的根因与机制移植规划

状态：调查完成 + 残差深挖完成（[`ox_best_arm_residual.md`](ox_best_arm_residual.md)）；**OX 当前最优 = 锁定F + live 重标 + closed_live F1=0.651**（冷树公平臂 0.584）
日期：2026-07-26（锚定表 2026-07-27 更新）
机器表：[`ox_vs_mac_rootcause.json`](ox_vs_mac_rootcause.json)

---

## 0. 锚定与口径订正

| 数据集 | 本方法 | MAC B06 | 最强基线 |
|--------|--------|---------|----------|
| DA option@1/@2 | **0.81/0.93**（synonym_bind） | 0.61/0.67 | B07 0.62/0.71 |
| MCR Acc / LLM RR | **0.50 / 0.753**（compat B0） | 0.23 / 0.527 | B07 0.24 / 0.412 |
| OX micro-F1 / Interp Acc | **0.651 / 0.355**（锁定F + live重标 + closed_live，LLM）；冷树公平臂 F1 0.584 | **0.570 / 0.221** | MAC（被本方法反超） |

**口径订正**：MCR Acc=0.50 与 LLM Reasoning Recall=0.753 见 `official_eval_llm_compat_rr`（Prompt 5/7）；≠ 官方 10-shot Acc。三分集对照总表见 [`diagnosisarena_d2_seq100_baselines_summary.md`](../../runs/paper_v1/diagnosisarena_d2_seq100_baselines_summary.md) §7。

---

## 1. 任务形态错配（为何 DA/MCR 赢、OX 输）

| 维度 | DA | MCR | OX |
|------|----|-----|-----|
| 计量 | MCQ option@k | 单轨迹 Acc | **多金标集合** micro P/R/F1 |
| 金标 | 选项绑定 | 主诊断 | mean\|gold\|≈4.7 |
| 树强项 | 层级+mapper | compat Top-1 | 需集合覆盖+进窗 |

树方法在 **封闭匹配 / Top-1** 占优；OX 要的是 **开集多标签覆盖**，闭集叶宇宙 + Top-5 截断成为瓶颈。

---

## 2. 覆盖对照与 H1–H3（A2）

### 2.1 micro（lexical greedy）

| 列表 | P | R | F1 |
|------|--:|--:|---:|
| MAC Top-5 | 0.462 | 0.493 | 0.477 |
| 树 gated_hybrid_mcr | 0.452 | 0.482 | 0.466 |
| 树后验 Top-5 | 0.444 | 0.473 | 0.458 |
| 树全叶 | 0.193 | 0.704 | 0.303 |

### 2.2 MAC TP 三分（相对树短列表）

| 成分 | 边数 | 含义 |
|------|-----:|------|
| 与树短列表共有 | 151 | 两者都命中 |
| **开集（叶宇宙外）** | **31** | MAC 命中且树全叶无 |
| **截断（叶在树、短列表无）** | **49** | MAC 命中且全叶有、短列表无 |
| 树独有 TP | 75 | 树短列表命中 MAC 未命中 |

MAC 独占 TP = 80；其中开集占比 = 38.8%；截断占比 = 61.3%。

**假设裁定：`H2_truncation_dominant`**

### 2.3 MAC 赢边桶（A3）

```json
{
  "n_mac_win_edges": 81,
  "buckets": {
    "C_or_open_unlabeled": 30,
    "D_in_tree_truncation": 51
  }
}
```

---

## 3. 成对病例（A4）

| 分层 | n |
|------|--:|
| MAC 明显赢 (ΔF1≥0.2) | 15 |
| 树明显赢 (ΔF1≤−0.2) | 10 |
| 接近 (|Δ|<0.05) | 5 |

MAC 赢层机制合计：`{'C_absent_or_open': 9, 'both_miss': 14, 'shared': 25, 'D_truncation': 16}`

样例见 json `paired.samples`（含 gold / mac / tree_short）。

---

## 4. MAC 机制分解（Phase B，离线）

三 doctor trace 覆盖：100 / 100 例。

| 臂 | micro-F1 | 说明 |
|----|---------:|------|
| supervisor_final | 0.477 | Supervisor 定稿（=正式 MAC） |
| doctor_a_only | 0.479 | 仅 Doctor A Top-5 |
| rrf_doctors | 0.477 | 三列表 RRF→K=5 |
| doctor_union | 0.478 | 三列表并集（未截断，覆盖上界） |
| tree_oracle_gold_sorted_topk | 0.644 | 树全叶按金标匹配排序 Top-5（作弊上界） |

解读要点：
- **M1**：doctor_union R ≫ 单 doctor → 多视角覆盖真实存在。
- **M3**：rrf_doctors vs supervisor_final → 融合是否接近正式 MAC。
- **M2/M4**：对照 §2 开集占比与 tree_oracle；若 oracle 仍 < MAC，开集必要。

---

## 5. 移植候选（按本审计优先级）

H2：MAC 独占 TP 以树上截断为主 → 优先闭集重排（C1）。

| 候选 | 机制 | 优先级 | OX LLM F1 | 裁定 |
|------|------|--------|----------:|------|
| **C1 公平** `closed_live_mac_supervisor` | 池内 live 3-doctor+supervisor | **正式主推** | **0.584** | **Promote**（无 B06 依赖） |
| C1 上界 `closed_mac_trace_rrf` | 冻结 B06→叶池 RRF | 机制证据 | 0.580 | 上界 only（Δ vs MAC CI 含 0） |
| C3 `multi_arm_rrf` | 树多臂 RRF | 先跑 | 0.522 | 否决 |
| C1b `closed_pool_rrf` | 仅树内闭集多视角 | 对照 | 0.535 | 否决 |
| C2 / C2s pad | 开集 pad | Open 桶 | ≤0.535 / lex 否 | 否决 |
| C4 讨论→force-emit | M1→建树 | 中期（Open 上限） | — | 未跑 |

门控细节与残差：[`ox_mac_transfer_arms.md`](ox_mac_transfer_arms.md)、[`ox_best_arm_residual.md`](ox_best_arm_residual.md)。

另见：[`ox_b00_b05_anomaly.md`](ox_b00_b05_anomaly.md) — OX 上 B00/B05 F1=0.543 挤进前三（B05≈B00；vs gated 打平；live 对 B00 的 Δ 亦 CI 含 0）。强纯 CoT 才是树的真正地板，而非仅 MAC。

结论：在 H2 下，**本方法自有的闭集 live panel** 即可反超开集 MAC；冻结 B06 映射臂仅作机制上界，不可混报正式分。Open 缺叶仍是下一瓶颈（C4），提交窗 pad 无效。对 B00 的边际优势说明：**拉开与 Direct CoT 的差距**比再堆多代理壳更关键。

## 6. 复现

```bash
PYTHONPATH=src:scripts/paper python3 scripts/paper/audit_ox_tree_vs_mac_coverage.py \
  --write-md
```

