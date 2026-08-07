# RareArena 证据预算重校准（Stage 2，Acc 口径）

协议：`ra_budget_recalib_offline_acc_v1`
树源：`logs/rarearena_ra_rdc_seq100_v1/compat_synonym_v1/annotate/shared_trees`
机器表：[`ra_budget_recalib.json`](ra_budget_recalib.json)

## 锁定组合

| 旋钮 | 锁定值 |
|------|--------|
| 组间 L1 证据预算 (F) | **4** |
| 组内 L2 local | **4** |
| 组间 L2 between | **2** |
| 每活家族 L2 候选上限 | **6** |
| 后验池 N | **15** |
| 提交 K | **5** |
| 离线重排器 | `post_n_mcr` |
| 正式端点 | `compat_parallel_final_ranking @ ddx_k=5 (live Acc)` |

- 锁定预算 Acc@1=**0.4100**；gold-leaf hit=**0.7400**
- 锁定短列表 Acc@1=**0.4100**；hit@K=**0.6900**
- F6 对照（同短列表设定）Acc@1=**0.4100**

## Live 重标对照（LLM Acc @ compat / ddx_k=5）

| 设定 | 路径 | Acc | Hits |
|------|------|----:|------:|
| F6 主跑（正式保留） | `compat_synonym_v1` | **0.47** | 47 |
| F4 live reann（侧跑） | `compat_synonym_noemit_fopt_live_v1` | 0.42 | 42 |

- 离线网格 Acc 平坦 → 曾按 OX 惯例试锁 L1=4；**live LLM Acc 上 F4 低于 F6（0.42 < 0.47）**。
- **正式端点仍用 F6**（`compat_synonym_v1`）；F4 仅作重校准侧跑，不覆盖主结果。
- Live 路由：已禁用 `google-vertex` / `google-ai-studio`（`maxOutputTokens≥8193` 拒请求）；output cap 天花板 8192。

## 预算网格（按 Acc@1 排序，Top-8）

| L1 | L2 local | L2 cand | Acc@1 | gold-leaf hit |
|----|----------|---------|-------|---------------|
| 2 | 2 | 4 | 0.4100 | 0.7400 |
| 2 | 2 | 6 | 0.4100 | 0.7400 |
| 2 | 4 | 4 | 0.4100 | 0.7400 |
| 2 | 4 | 6 | 0.4100 | 0.7400 |
| 4 | 2 | 4 | 0.4100 | 0.7400 |
| 4 | 2 | 6 | 0.4100 | 0.7400 |
| 4 | 4 | 4 | 0.4100 | 0.7400 |
| 4 | 4 | 6 | 0.4100 | 0.7400 |

## 短列表网格（锁定预算下，Top-8）

| pool_n | K | reranker | Acc@1 | hit@K |
|--------|---|----------|-------|-------|
| 7 | 5 | `posterior` | 0.4100 | 0.7000 |
| 7 | 5 | `post_n_mcr` | 0.4100 | 0.7000 |
| 12 | 5 | `posterior` | 0.4100 | 0.7000 |
| 15 | 5 | `posterior` | 0.4100 | 0.7000 |
| 12 | 5 | `post_n_mcr` | 0.4100 | 0.6900 |
| 15 | 5 | `post_n_mcr` | 0.4100 | 0.6900 |
| 7 | 4 | `posterior` | 0.4100 | 0.6700 |
| 7 | 4 | `post_n_mcr` | 0.4100 | 0.6700 |

## 边界

- 证据预算为离线家族/叶保留代理，**不是** live F 重 annotate。
- Live F4 侧跑已完成；正式 Acc 仍以 F6 主跑为准。
- 不得未经本网格+live 对照把 OX 的 F4 直接标为 RA 最优。
- **下方「不敏感机制」表明：原离线网格 Acc 全平坦 partly 是 proxy bug；修后 Acc@1 仍平坦，但 gold-leaf coverage 会动。**

## 为什么 RA 对预算不敏感？（机制审计）

审计对象：F6 主跑树 `compat_synonym_v1/annotate/shared_trees` + F4 live 侧跑；对照 OX emit 树。

### 1. 测量层：离线 `apply_budget_proxy` 在 RA/OX 上基本空跑

`audit_ox_budget_recalib.apply_budget_proxy` 用「`parent` 为空串」识别 L1 家族；实际树里 L1 的 `parent` 一律为 **`ROOT`**：

| 队列 | L1 节点 | `parent==""` | `parent==ROOT` |
|------|--------:|-------------:|---------------:|
| RA F6 | 469 | 0 | 469 |
| OX emit | 449 | 0 | 449 |

后果：`keep_l1` 为空 → 不裁剪任何叶 → **100/100 例**上 F2 与 F6 的 active leaf set / top-1 **完全相同**。  
这直接解释了原网格 Acc@1≡0.41、gold-leaf hit≡0.74 的「假平坦」。OX 原网格全树 R 全系 0.7910 同因。

### 2. 修代理后：Acc@1 仍平坦，但 coverage 敏感（真实现象）

按 `level==1` + **家族叶后验质量和** 重做截断后（同树、Lexical top-1）：

| L1 | L2 local | cand | Acc@1 | gold-in-leaves | 均叶数 | 相对全树有改动的例数 |
|----|----------|------|------:|---------------:|-------:|--------------------:|
| 2 | 2 | 4 | 0.41 | 0.60 | 2.94 | 100 |
| 2 | 4 | 6 | 0.41 | 0.69 | 5.70 | 99 |
| 4 | 4 | 6 | 0.41 | 0.73 | 8.02 | 90 |
| 6 | 4 | 6 | 0.41 | 0.73 | 8.60 | 87 |

- **Top-1 在 F2(local=2) 截断下 100/100 与全树一致** → Acc@1 不可能动。
- 预算主要改变的是 **gold 是否仍留在叶集合**（0.60→0.73），不是谁当 top-1。
- 结论：对 **Acc 口径**，RA 确实预算不敏感；对 **覆盖/召回类口径** 并非如此。原网格把两者都画成平坦，是 bug。

### 3. 结构层：后验极度尖峰 + L1 规模小

| 量 | RA（n=100） | OX emit（对照） |
|----|-------------|-----------------|
| 均 L1 家族数 | 4.69（全≤6） | 4.49 |
| 均叶数 | 25.3 | 20.0 |
| Top-1 家族后验质量占比（均/中） | **0.86 / 0.95** | 0.40 / — |
| Top-2 家族质量和占比（均） | **0.935** | 0.668 |
| Gold 落在 Top-1 家族（叶命中子集） | **90.5%** | — |
| Gold 落在 Top-2 家族 | **98.6%** | — |
| L1 `posterior==0` 比例 | **100%** | （代理若按 L1 posterior 排序会失效） |
| 叶节点 `evidence_*` 条数 | **恒为 0**（证据只挂在 L1） | — |

机制 recap：

1. **质量集中**：赢家几乎总在最大质量家族；砍到 F=2 仍留得住 top-1。
2. **L1≤6**：F6 本身很少「多留一个会改排序」的家族；F4→F6 空间更窄。
3. **证据在 L1、后验在叶**：离线裁叶只改短名单宽度，不重算证据；Acc 只看 top-1 → 钝。
4. **L1 posterior 全 0**：旧代理即便识别到 ROOT，按 L1 posterior 排序也近乎按 id 乱序；需按叶质量和。

### 4. Live 层：F6 预算几乎不触顶，故 F4≈F6 操作点

F6 vs F4 live 树（同 100 例）：

| 量 | F6 | F4 |
|----|---:|---:|
| 有证据的 L1 家族数（均） | **3.29** | 3.25 |
| L1 证据链接总数（均） | 19.96 | 19.78 |
| 用到的 unique finding 数（均） | 13.4 | 13.3 |
| `fam_with_evi > 4` 的例数 | **4** | 3 |
| 树 top-1 一致 | 78/100 | |
| pred_diagnosis 一致 | 78/100 | |
| LLM Acc | 0.47 | 0.42 |

- F6 名义预算=6，但平均只有 **~3.3** 个家族挂上证据 → **F4 上限=4 对绝大多数例不构成额外约束**。
- LLM 差分：F6-only hit 8、F4-only 3；多为近义/边界病名（judge 波动），不是系统性「加预算就找回 gold」。
- Lexical 树 top-1 hit：41 vs 42（几乎无差）→ live Acc 的 0.05 差距 **远小于**「预算改变决策面」的叙事，更接近重标噪声 + judge。

### 5. 总括（因果链）

```text
离线 Acc 全平坦
  ├─ (主) proxy 认不出 parent=ROOT → 零裁剪 → 假平坦
  └─ (次) 修好后 Acc@1 仍平：后验尖峰 ⇒ top-1 在 F2 仍存活
           但 gold-leaf coverage 随预算上升（真敏感在覆盖，不在 Acc）

Live F4≈F6 Acc
  ├─ F6 实际占用 ~3.3 fam ≪ 6 → F4 几乎同操作点
  └─ 残差 0.47 vs 0.42：22% pred 改写 + LLM judge 边界，非单调预算效应
```

**对论文/协议的含义**：RA 上用 Acc 做 Stage-2 预算重校准信息量很低；若要调 F，应看 **gold-leaf coverage / hit@K / 活家族占用分布**，或先修 proxy 再报网格。正式端点维持 F6 仍合理（live 未显示 F4 更优）。

## 复现

```bash
PYTHONPATH=src:scripts/paper python3 scripts/paper/audit_ra_budget_recalib.py \
  --run-dir logs/rarearena_ra_rdc_seq100_v1/compat_synonym_v1

# live F4 侧跑（已跑完；可 --skip-annotate 仅重评）
PYTHONPATH=src:scripts/paper python3 scripts/paper/run_ra_live_reann_fopt.py
```

