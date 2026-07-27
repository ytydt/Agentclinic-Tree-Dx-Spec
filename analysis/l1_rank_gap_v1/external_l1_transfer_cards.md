# 外部机制 → L1 家族层：可迁移卡片（Track B + Track C）

**前提**：MAC / Dual-Inf 均为开放 vignette→疾病 Top-2 的 **flat** 协议（[`baseline_conversion_mechanisms.md`](../at1_gap_v1/baseline_conversion_mechanisms.md)；[`baseline_arms.py`](../../scripts/paper/baseline_arms.py)），无显式 L1。已迁到 **L2 叶** 的 support/pair **不算**本轮完成。  
**作弊硬过滤**：推理/选臂读评测金标 → 不入档。

---

## Track B — 默认整合主轨（必须保留）

| 来源 | 算子 | L1 上移设想 | 插入点 | 判定 | 风险 |
|------|------|-------------|--------|------|------|
| Dual-Inf | examine + `_rank_by_support` | 对 Top-M 家族做 support/contradict 条数重排后写回后验序 | **冻结后** | **可迁** | 家族粒度粗；与 ordinal 双重计分 → 建议近并列才启用 |
| Dual-Inf | reflect（reasons≤β） | 家族分差小或 support 少时再选 1–2 事实并更新 | update 中 / 冻结前 | **条件可迁** | 破坏固定 F6 协议；成本↑；须分列臂 |
| MAC | supervisor pair | 仅交换 L1 Top1–Top2（分差&lt;τ） | 冻结后 | **可迁** | 作用面窄；与后验标定冲突时需护栏 |
| MAC | RRF 多列表 | 多温度/多提示采样 L1 序，RRF 融合，**候选封闭** | 冻结后 | **条件可迁** | calls×k；须报成本前沿 |
| 本方法 | P5 select 强化 / 降 abstain | 调整 selector 合同或 abstain 阈值后再更新 | select | **条件可迁** | 协议变更；需 SELECT 评测包 |
| 本方法 | B1/`p5_headline` 联合 | 换独立最优 L1 路径做对照 | 整段 L1 | **对照臂** | 非「算子补丁」；工程重 |
| A01 taxonomy | 先选 specialty 再疾病 | 对照「显式家族化」 | 入口 | **仅对照** | 非 BFS 后验 |

**Track B 推荐优先级（设计用）**

1. **L1-SupportRerank**（Dual examine 上移，冻结后、近并列门控）  
2. **L1-Pair**（MAC supervisor 缩小版）  
3. **L1-Reflect-lite**（low-conf 再选证据，分列）  
4. **Closed multi-sample RRF**（成本允许时）

---

## Track C — 拓宽探索轨（2C：非作弊 + 有潜力）

| 方向 | 设计梗概 | 作弊？ | 潜力判断 | 建议角色 |
|------|----------|--------|----------|----------|
| **L1-MAC-council** | 3 角色对**已有** L1 标签各出序 → supervisor 综合家族 Top-k | 否（若不读金标） | **有**：直接针对 misrank；成本高 | 分列强基线 / 上界 |
| **L1-OpenRegen** | 允许提出新家族名或合并拆分，再 **归一映射** 回树节点 | 否（归一失败则丢弃） | **有** 针对真召回缺口；本轮自动 L1_MISS 多与 mapper 绑定失败重叠，须先分清 | 召回扩族臂，**禁止**与封闭重排混报 |
| **L1-DualFull** | 以家族名为「疾病」跑完整 forward–backward–examine | 否 | **中**：可能与 BFS 冗余；可作替换式 L1 判别 | 消融/替换臂 |
| **Self-Refine on L1** | 批评只改家族序与理由，不发明事实 | 否 | **有**（低成本） | Track C 轻量；也可并入 B 若封闭 |
| **SC 多采样家族序** | 5 次采样 + 投票/RRF | 否 | **有** | 成本匹配对照 |
| **监督 LTR / 贝叶斯** | 见文献笔记；小样本仅线性融合日志特征 | 训练若泄漏测试则作弊 | **思想可迁**；d2 无隔离训练池 → 不进默认 | 条件性消融 |
| **整树开放重写** | 重建 L1/L2 | 否但不公平 | **低优先**：混淆层级收益归因 | 默认 **REJECT 为生产路径**；仅作极端上界 |

**过滤记录**

- 金标选臂 / 金标 G2：硬 REJECT。  
- 专有知识库贝叶斯（MidasMed 级）：可借鉴「稀疏证据序更新」思想，**不可**默认依赖不可复现 KB。

---

## 与 L2 叶校准的边界

| 已在 L2 做的 | 本轮 L1 要做的 |
|--------------|----------------|
| leaf Top-K support / pair / L1-fallback | 改 **家族后验序本身** |
| compat_parallel merge×calib | **不改**；L1 在 annotate 段完成 |

若只把 Dual/MAC 再跑在叶上，**不能**宣称修复了 family @1=0.60。
