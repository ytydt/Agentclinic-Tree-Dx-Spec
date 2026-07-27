# L1 改进设计 v1（Track B 主轨 + Track C 探索）

**状态**：设计稿（决策 3A：本轮不实现）  
**根因**：[`l1_weakness_rootcause.md`](l1_weakness_rootcause.md)  
**外部卡片**：[`external_l1_transfer_cards.md`](external_l1_transfer_cards.md)  
**推荐默认候选**：仅从 Track B 选出（**B1 + B2** 组合为优先整合包）

---

## 设计原则

1. 改 **L1 后验/家族序本身**；禁止把 L2 leaf calib / compat 涨点记作 L1 修复。  
2. Track B：封闭在已有 L1 集合；Track C 分列。  
3. 插入点在 annotate/冻结段；与 `compat_parallel` 解耦。  
4. 推理不读金标；报告 calls/tokens。  
5. 主终点 family @1；护栏 family @2；次终点 `L1-prior-only` option @1/@2。

---

## Track B — 优先整合方案

### B1. L1-SupportRerank（Dual examine 上移）

**插入点**：F6 冻结后、写入 `l1_posteriors` 供下游之前。

```text
算法 L1-SupportRerank(F, V, findings, M=5, τ=0.15):
  R ← l1_posteriors 降序
  if (post(R[1]) − post(R[2])) ≥ τ: return R          # 远非并列则跳过
  pool ← R 的前 M 个家族
  for f in pool:
      (n_s, n_c) ← ExamineFamily(V, findings, f.label)  # Dual 风格；禁止金标
      score[f] ← n_s − n_c + γ·post(f)
  R' ← pool 按 score 降序 ⊕ (R \ pool)
  将 R' 写回后验（可按秩赋单调伪后验或仅改序）
  return R'
```

| 项 | 内容 |
|----|------|
| 预期 | 降 `L1_HIT_MISRANK`；抬 coverage 子集 family @1 |
| 成本 | O(M) examine 调用 |
| 作弊 | 否 |
| 兼容 | 保留 anti-anchor 轨迹；不改树 |

### B2. L1-PairAdjudicate（MAC supervisor 缩小版）

**插入点**：B1 之后（或单独臂）。

```text
算法 L1-Pair(R, τ=0.15):
  if |R| < 2: return R
  if (post(R[1]) − post(R[2])) ≥ τ: return R
  winner ← PairAdjudicate(vignette, findings, R[1], R[2])  # 只允许交换
  return 交换后的 R
```

| 项 | 内容 |
|----|------|
| 预期 | 修复近并列 Top2 互倒 |
| 成本 | 1 次 LLM |
| 作弊 | 否 |

### B3. L1-Reflect-lite（条件）

当 B1 后 Top1 support≤β 或分差仍&lt;τ：再跑 1 cycle anti-anchor 选择 + 一次 `symmetric_rank_update`，然后可选再 B1。  
**分列臂**（改变 F6 冻结语义）。预期针对 abstain 过早（R2）。

### B4. Closed-L1-RRF（条件）

K 次温度采样家族序（候选封闭）→ `rrf_aggregate`。成本×K；作成本匹配对照。

### B5. 线性特征融合（条件性监督启发）

特征：posterior、examine n_s/n_c、是否 abstain 停止、簇大小等；隔离折上网格权重。无隔离折则 **不做**。

---

## Track B 推荐默认包

**`L1-Calib-B12` = B1 → B2**（均带近并列门控 τ）。  
不默认启用 B3/B4，直至烟测显示 B12 不足且成本可接受。

---

## Track C — 探索方案（分列；不得挤掉 B）

### C1. L1-MAC-council

3 角色对**同一封闭** L1 标签列表出序 → supervisor 出家族 Top-2 序 → 写回。  
潜力：高（直接打 misrank）。角色：强基线/上界。成本：高。

### C2. L1-Self-Refine

批评只改家族排序与理由，不发明事实，不扩候选。潜力：中高；成本低。可在 B12 失败子集上叠加。

### C3. L1-OpenRegen + 树归一

允许新家族名/合并拆分 → 字符串/embedding 对齐到树 L1 → 失败则丢弃。  
**仅当**盲法确认存在真召回缺口（当前自动 L1_MISS 与 mapper 失败重叠，**先不要**当默认）。  
与封闭重排 **分列**。

### C4. L1-DualFull

以家族名为疾病代理跑 Dual 子流程，**替换** BFS 更新。潜力：中；风险：与现有 P5 路径双重叙事。作替换消融。

### C5. SC-L1

5 采样投票/RRF。作成本对照。

### REJECT（默认生产）

- 金标选臂 / 金标 G2  
- 整树开放重写当默认  
- 闭源 KB 贝叶斯当默认  
- 无隔离折高容量 LTR  

---

## 与下游的接口

```text
L1EvidenceBFS (现有) → [Track B/C 算子] → 冻结 l1_posteriors
    → L2 配置 A → joint → compat_parallel → mapper
```

验收时：**家族指标**与 **option/compat 指标分表**；改 L1 不得要求关闭 compat。

---

## 实现备忘（另开任务）

- 新模块建议：`scripts/paper/l1_family_calibration.py`  
- harness 旗标建议：`--l1-calib off|support|pair|b12|…`（默认 off 直至通过烟测）  
- 复用 Dual/MAC 的 examine/pair prompt 风格，但输入改为家族标签 + leaf exemplars
