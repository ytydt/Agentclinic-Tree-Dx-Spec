# 本方法 L1 排序机制卡片与可证伪假说

**代码**：[`src/agentclinic_tree_dx/l1_evidence_bfs.py`](../../src/agentclinic_tree_dx/l1_evidence_bfs.py)  
**挂载**：[`scripts/paper/run_diagnosisarena_downstream_top2.py`](../../scripts/paper/run_diagnosisarena_downstream_top2.py)（`p5_anti_anchor_direct`，F6 冻结后验）  
**审计对照**：[`l1_rank_gap_audit.md`](l1_rank_gap_audit.md)

---

## 1. 机制卡片（生产 L1 路径）

| 环节 | 行为 | 关键细节 |
|------|------|----------|
| 预设 | `p5_anti_anchor_direct` | selector=`anti_anchor`；单目标 DIRECTION + RULE-OUT |
| 选择 | 全局 anti-anchor selector | 每 cycle ≤2 事实；须 supports≠contrasts；可 abstain；concept ledger 去重 |
| 编译器 | `compiler_master_blocks` | d2 日志上 `compiler_rules_injected=True`（100%）；select 规则进入 payload（上限截断） |
| 分配 | `rule_in_allocator` / `rule_out_allocator` | 每事实独立；同 L1 出现在 support∩against → 冲突清零 |
| 更新 | `symmetric_rank_update` | η=ln3；credits (1, 0.5, 0.25)；乘性 exp 后 softmax 归一 |
| 停止 | FixedBudget + abstain/pool | 实测：abstain 68%、pool 30%、budget 2% |
| 预算 | F6 前缀冻结 | 下游 L2 另用真实 F2；L1→L2 **单向**，L2 不回写 L1 |
| 软先验下游 | joint arbiter / TopKCalibration L1 fallback | **不修复** L1 后验本身；只影响叶序校准 |

**不变量**：`assert_no_gold_leak` 禁止推理 payload 含金标字段。

---

## 2. 与「独立最优 B1」路径的差异（设计相关）

Explainer 记载：独立 B1（`p5_single_direct` + `p5_headline` + F4）与 anti-anchor F6+配置 A **未在同一冻结清单联合评测**。  
本 d2 联合端点已注入 compiler blocks，但 selector 仍为 anti-anchor、预算为 F6。因此「未启用的增益」更可能是：**换 selector 合同 / 换停止策略 / 冻结后重排**，而非「完全没注入 P5」。

---

## 3. 可证伪假说（每条对应日志谓词）

| ID | 假说 | 可检验谓词 / 证据 | 本轮状态 |
|----|------|-------------------|----------|
| H1 | 覆盖条件下 family 排序仍不足 | coverage 子集 @1=0.75；10 例 misrank 秩∈{3,4,5} | **支持** |
| H2 | 自动 L1_MISS 主要是映射未绑叶，而非 L1 未生成父 | `parent_source=none` 的 20 例 mapper @2=0 | **支持** |
| H3 | abstain 过早停止导致证据不足 → misrank | misrank 中 9/10 为 `selector_abstained` | **弱支持**（相关，未证因果） |
| H4 | 多可接受父（近义 L1）稀释后验、抬高乐观 @k | 平均 `n_acceptable_parents`=2.33 | **待人工收紧父集后复测** |
| H5 | ordinal 更新缺显式 support 条数破平，近并列易误序 | 机制上无 Dual 式计数；需冻结后重排消融 | **机制合理，未做消融** |
| H6 | F6 相对更短预算会伤 family @1 | 需 F4/F6 A/B | **未测** |
| H7 | 注入 P5 select 仍不足以修正原型锚定 | 需 SELECT 金标对齐包 | **未测**（无 decisive 落盘） |
| H8 | 修好 family @2 后 option 代理仍有缺口 | `L1_OK_OPTION_MISS`=10 | **支持**（代表叶/映射独立问题） |

---

## 4. 对设计的直接含义

- 优先处理 **H1/H5**：封闭家族集上的冻结后破平（Track B）。  
- **H2** 不应被 L1-SupportRerank「假装修好」——映射/召回另臂。  
- **H3** 支持 Reflect / 降低 abstain 或二次选择（Track B），但须成本护栏。  
- **H8** 说明 L1 改进验收必须分列 option 代理，避免只看 family @1。
