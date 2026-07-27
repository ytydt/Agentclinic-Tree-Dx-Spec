# L1 排序缺口审计报告（d2_seq100）

**协议**：[`protocol.md`](protocol.md) `v1_auto_parent`  
**脚本**：[`scripts/paper/audit_l1_rank_gap.py`](../../scripts/paper/audit_l1_rank_gap.py)  
**表**：[`l1_family_metrics.tsv`](l1_family_metrics.tsv)、[`l1_family_summary.json`](l1_family_summary.json)  
**口径**：审计可读金标；非推理作弊。

---

## 1. 主表（全量 100）

| 指标 | 数值 | 说明 |
|------|-----:|------|
| **family @1** | **0.60** | 可接受 gold 父落入 L1 后验 Top-1 |
| **family @2** | **0.70** | 落入 Top-2 |
| family MRR | 0.680 | |
| family coverage | 0.80 | 可接受父出现在 L1 候选集（不论秩） |
| `L1-prior-only` option @1/@2 | 0.60 / 0.69 | 与历史 2b 的 0.59/0.68 同量级（本轮 gold 叶含 clone） |
| 官方 mapper option @1/@2 | 0.59 / 0.78 | 对照 |
| L2-joint 叶序重匹配 @1/@2 | 0.55 / 0.65 | 公平重匹配 |

**覆盖条件下**（n=80，`family_coverage=1`）：

| 指标 | 数值 |
|------|-----:|
| family @1 \| coverage | **0.75** |
| family @2 \| coverage | **0.875** |

---

## 2. 漏斗桶（每例唯一）

| 桶 | n | 含义 |
|----|--:|------|
| `L1_OK_OPTION_HIT` | 60 | family @2 且 L1-prior option @1 |
| `L1_OK_OPTION_MISS` | 10 | family @2 但对 option 代理仍未 @1（代表叶/映射问题） |
| `L1_HIT_MISRANK` | 10 | 有 coverage，但 gold 父秩在 3–5（纯排序失败） |
| `L1_MISS` | 20 | 自动规则下无可接受父（见下） |

**对「L1 偏弱」的一句话定性**：

1. **排序层真实偏弱**：在已覆盖的 80 例上 family @1 仅 0.75，另有 10 例明确 misrank（秩 3–5）。  
2. **另有 20 例自动 `L1_MISS`**：`parent_source=none`，且这些例 **mapper option @2 = 0**——主要是 **金标叶未绑上树/映射失败**，不能直接写成「L1 更新把 gold 父挤出候选」。真正的「树上有父但没召入 L1」需盲法父集重标后才能拆开。  
3. **option 代理 @2（0.69）远低于官方 mapper @2（0.78）**：家族序即便改善，也不自动解释 mapper 的覆盖优势；下游仍依赖叶序与关系感知映射。

中期分流（协议 §6）：family 在覆盖子集上 @1=0.75 **仍有抬升空间** → 继续 Track B/C 的 L1 算子设计；同时 20 例映射缺口与 10 例 `L1_OK_OPTION_MISS` 提示 **不要只改 L1**。

---

## 3. 过程代理（现有落盘字段）

| 字段观察 | 全量 |
|----------|------|
| `preset` | 全部 `p5_anti_anchor_direct` |
| `compiler_rules_injected` | **100%** True（本联合端点已注入；与 Explainer「清单未绑定」的历史表述需区分：本 d2 日志已注入） |
| `stop_reason` | `selector_abstained` 68；`pool_exhausted` 30；`budget_exhausted` 2 |
| 平均 L1 家族数 | 4.63 |
| 平均可接受父数（自动） | 2.33（偏乐观：多克隆叶多父） |

`L1_HIT_MISRANK`（n=10）中 9/10 为 `selector_abstained`；gold 父秩分布：3×7、4×2、5×1。  
**无**逐步 DIRECTION/RULE-OUT 轨迹落盘 → 细粒度 SELECT/DIRECTION 错误需后续抽样人工包；本轮不伪造细标签覆盖率。

---

## 4. 与历史 2b / 17 例 BFS 的关系

| 来源 | 结论如何用 |
|------|------------|
| at1_gap `L1-prior-only` 0.59/0.68 | 本轮复现为 0.60/0.69；作为漏斗衔接层 |
| 17 例 gold-parent Top-1≈45% | **不作 d2 主数字**；与本轮覆盖条件 @1=0.75 不可横比（队列/父集定义不同） |
| A 集 L1 虚拟抬 @1 | 说明相对 joint 叶序有时更好；本审计显示家族层本身仍有 10 例 misrank + 20 例绑定缺口 |

---

## 5. 审计局限

- `v1_auto_parent` 非盲法临床父集；多父可接受 → family @k 偏乐观。  
- `L1_MISS` 与 mapper 叶绑定失败高度重叠，需人工父标注才能谈召回扩族。  
- 过程分解仅有 stop_reason 级代理。

产出完成：本文件 + TSV/JSON + 审计脚本。
