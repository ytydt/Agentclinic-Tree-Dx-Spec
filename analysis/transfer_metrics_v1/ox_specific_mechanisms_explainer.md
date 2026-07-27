# Open-XDDx（OX）特有机制说明：算法、起效机制与根因

**状态**：方法学入档（与 OX `ox_seq100` 当前最优栈对齐）  
**代码**：[`scripts/paper/build_eval_projection.py`](../../scripts/paper/build_eval_projection.py)（`ddx_closed_live_mac_supervisor`）、[`scripts/paper/diagnosisarena_l2_pipeline.py`](../../scripts/paper/diagnosisarena_l2_pipeline.py)（`apply_live_posteriors_and_cap` / `run_joint_primary`）、[`scripts/paper/run_diagnosisarena_downstream_top2.py`](../../scripts/paper/run_diagnosisarena_downstream_top2.py)（L1 前缀预算与树写回）、[`scripts/paper/run_ox_live_reann_arms.py`](../../scripts/paper/run_ox_live_reann_arms.py)  
**实证**：[`ox_mac_transfer_arms.md`](ox_mac_transfer_arms.md)、[`ox_vs_mac_rootcause.md`](ox_vs_mac_rootcause.md)、[`ox_best_arm_residual.md`](ox_best_arm_residual.md)、[`ox_budget_recalib.md`](ox_budget_recalib.md)、[`ox_live_reann_emit_vs_fopt.md`](ox_live_reann_emit_vs_fopt.md)  
**评测队列**：Open-XDDx `ox_seq100_v1`，100 例；主指标为 diagnostic micro P/R/F1（`list_k=5`，`paper_aligned_judge_v1` / Gemini 2.5 Flash）  
**口径边界**：DiagnosisArena 用 Mapper option@k；MedCaseReasoning 用单轨迹 Acc。本文机制服务于 OX 的**开集多金标集合覆盖**，不得与 DA/MCR 主表静默横比。

本文以平实学术表述完整入档：相对 DA/MCR 共用树管线而言，**OX 侧特有（或为 OX 锁定）的三类机制**——（A）闭集 live-MAC 短列表、（B）OX 证据预算重校准、（C）在线后验写回与家族候选截断——各自的输入输出与算法步骤，在**锁定预算**下的起效方式，以及这些起效之所以成立的根因。共用模块（`compat_parallel`、同义修绑、joint A3）见既有 explainer，本文不重复展开。

**三分集本方法最优点估计（与基线对照总表）**：DA synonym_bind **@1/@2=0.81/0.93**；MCR compat Acc/RR=**0.50/0.753**；OX 本配置 F1/IAcc=**0.651/0.355**（LLM）。详见本文 §0 与 [`runs/paper_v1/diagnosisarena_d2_seq100_baselines_summary.md`](../../runs/paper_v1/diagnosisarena_d2_seq100_baselines_summary.md) §7、[`CURRENT_HIERARCHICAL_DIAGNOSIS_RESEARCH_PIPELINE_EXPLAINER.md`](../../CURRENT_HIERARCHICAL_DIAGNOSIS_RESEARCH_PIPELINE_EXPLAINER.md) §9。

---

## 0. 三分集本方法最佳配置一览

| 数据集 | 最佳本方法配置（摘要） | 主指标 | Ours | 最强外部基线 |
|--------|------------------------|--------|------|--------------|
| DA | compat_parallel + **synonym_bind**（Approach A live） | @1/@2 | **0.81/0.93** | B07 0.62/0.71 |
| MCR | compat 投影（B0）；F6 | Acc / LLM RR | **0.50 / 0.753** | B07 0.24 / 0.412 |
| **OX（本文）** | 无 emit；**L1=4 / local=4 / between=2 / cand=6**；live 后验写回；**closed_live @15/5** | micro-F1 / Interp Acc（LLM） | **0.651 / 0.355** | B06 0.570 / 0.221 |

OX 相对「冷树 + closed_live」（F1≈0.584）的增益约 +0.067，归因见第 5 节。

---

## 1. 问题设定：为何 OX 需要额外机制

### 1.1 任务形态

OX 要求系统输出有序诊断列表 \(L=(d_1,\ldots,d_K)\)（默认 \(K=5\)），并与多条金标诊断集合 \(G\)（队列上 \(\mathbb{E}|G|\approx 4.7\)）做集合匹配，报告 micro precision / recall / F1。与此相对：

| 维度 | DiagnosisArena | MedCaseReasoning | Open-XDDx |
|------|----------------|------------------|-----------|
| 主计量 | option @1/@2 | 单轨迹 Acc@1 | **多金标 micro F1** |
| 成功条件 | 首位/前二映射对 | Top-1 对 | **集合覆盖 + 进窗** |
| 树管线强项 | 层级 + mapper | compat Top-1 |  alone 不足以吃满集合 R |

因此，仅把 DA 上有效的「joint → compat → Top-2 映射」原样搬到 OX，会系统性地暴露两类瓶颈：

1. **截断（truncation）**：金标叶已在树宇宙内，但未进入最终短列表（相对 MAC 独占真阳性的主导成分之一，见根因审计中的 H2）。  
2. **上下文—后验错位**：建树/证据阶段写入的叶后验，未必反映该例 vignette 下局部证据标注的相对支持；短列表若按「冷」后验取池，会把真正可判的叶挤出 Top-\(N\)。

开集缺叶（Open）仍是结构性上限（FN 中 Open 约占六成），但短列表移植实验表明：在**不依赖冻结外部 MAC 名单**的前提下，先把闭集内的排序与多样性做对，即可反超 MAC B06；补叶本身不是当前最优增益源。

### 1.2 本文范围中的「特有机制」

在共享栈（Config A 建枝 → L1 证据前缀 → joint 局部/组间证据 → 可选 `compat`）之上，OX 当前最优路径额外依赖：

| 编号 | 机制 | 插入点 | 正式角色 |
|------|------|--------|----------|
| **A** | `closed_live_mac_supervisor` | 已写回的 `shared_trees` → 评测投影 | 公平短列表 / 正式可报臂 |
| **B** | OX 锁定预算 \(L1=4,\ L2_{\mathrm{local}}=4,\ B_{\mathrm{between}}=2,\ C_{\mathrm{cand}}=6\) | annotate 阶段证据与候选宽度 | 替代 DA 默认 F6 的队列校准 |
| **C** | `apply_live_posteriors_and_cap` | joint 之后、树序列化之前 | 把局部后验写回叶并截断家族候选 |

三者在最优臂中的耦合顺序为：

```text
锁定预算 annotate（B）
  → joint 局部证据
  → 后验写回 + 家族截断（C）
  → 覆盖 shared_trees
  → 后验 Top-N 池上 closed_live（A）
  → LLM judge micro-F1
```

点估计（`ox_seq100`，LLM）：无写回的公平 closed_live ≈ **0.584**；在锁定预算下完成写回后再 closed_live ≈ **0.651**（无 force-emit）。下文在该校准预算下讨论起效与根因。

---

## 2. 机制 A：闭集 live-MAC 短列表（`closed_live_mac_supervisor`）

### 2.1 设计目标

MAC 风格多医生讨论能提供**多视角覆盖**，但其开集自由生成会引入树外病名，且若直接复用冻结 B06 doctor lists，则本方法分数与外部基线 run 耦合，不能作为公平正式分。机制 A 的目标是：

1. 保留「多角色排序 → 督导融合」的交互结构；  
2. 把生成严格限制在**本方法树后验导出的闭集池**内；  
3. 不读取任何外部 MAC 预测文件。

### 2.2 输入输出

- **输入**：病例 vignette \(V\)；树状态 \(T\)（含叶后验）；池宽 \(N\)（锁定 **15**）；提交长度 \(K\)（锁定 **5**）；匹配阈值 \(\tau\)（默认闭集投影阈值）。  
- **输出**：长度至多 \(K\) 的叶行列表（含 id / label / posterior / rank），以及是否走 live、是否督导回退等元数据。  
- **硬约束**：医生与督导的合法标签必须来自池标签集合 \(\mathcal{P}\)；出池字符串经投影；投影失败则用三列表 RRF 回退，仍投影回池。

### 2.3 算法步骤

记 \(\mathrm{TopPost}(T,N)\) 为按叶后验降序、标签去重后的前 \(N\) 叶（实现：`top_leaf_posterior`）。

```text
算法 ClosedLiveMAC(T, V; N, K):
  pool ← TopPost(T, N)                         # 行含 label 与 posterior
  P ← labels(pool)
  history ← []
  for role in {Doctor A, Doctor B, Doctor C}:
      raw ← LLM_doctor(role, V, P, history)   # 提示要求仅复制池内精确标签
      ranked ← parse_names(raw)
      proj ← ProjectToPool(ranked, P, K)      # 模糊匹配进池；不足则按池序补齐
      history.append(role, proj)
      doctor_lists.append(proj)
  raw_s ← LLM_supervisor(V, P, history)
  fused ← ProjectToPool(parse_supervisor(raw_s), P, K)
  if fused 为空:
      fused ← ProjectToPool(RRF(doctor_lists), P, K)
  return RowsFromLabels(fused, pool, K)         # 用池内后验填充行字段
```

**投影** `ProjectToPool`（`_project_closed_names`）先把模型输出名映射到池标签；若有效名不足 \(K\)，按池的后验序补齐未出现标签。从而保证提交列表始终是 \(\mathcal{P}\) 的有序子集，评测不会因「自由 paraphrasing」漂出树宇宙。

无 live 客户端时，实现回退到闭集多视图 RRF（`ddx_closed_pool_views_rrf`）；该回退**不是**公平正式分，仅用于干跑。

### 2.4 在校准预算下的起效机制

在固定 \(N=15,\ K=5\) 且树后验已按机制 C 写回时，机制 A 的作用可分解为三层：

1. **池构造层**  
   \(N=15\) 相对 \(K=5\) 提供约三倍候选。池覆盖曲线显示：金标落入后验 Top-15 的召回显著高于 Top-5（残差审计中 Top-5 全叶匹配 R≈0.47，Top-15≈0.69）。因此 A 首先把「可讨论集合」扩大到仍被后验支持的区域，而不是在过窄 Top-5 上做无意义重排。

2. **多视角覆盖层**  
   三名医生在同一闭集上独立（带讨论历史）排序。MAC 机制分解表明 doctor 并集召回高于单医生：多视角真实存在。闭集约束把该覆盖限制在树内可核对标签上，避免开集「看起来覆盖、实则不可归因于本方法生成」的膨胀。

3. **督导融合 / 多样性层**  
   督导在三列表之上输出最终 Top-\(K\)。与纯后验 Top-5 或树内自融 RRF 相比，live 督导能改变槽位分配，使多个家族的合理叶同时进窗，缓解「后验质量尚可但短列表同质化」的截断型假阴性。公平臂相对 `gated_hybrid_mcr`（≈0.547）与 MAC B06（≈0.570）提升至 ≈0.584，且不依赖冻结 B06。

### 2.5 起效根因

根因不在「多调用本身」，而在 **OX 失败结构与算子能力的匹配**：

1. **H2 截断主导闭集可解部分**  
   相对 MAC 的独占真阳性中，截断（叶在树、短列表无）权重大于开集。机制 A 直接优化「树内叶如何进窗」，而不假装解决开集宇宙外金标。

2. **后验序 ≠ 临床提交序**  
   叶后验来自层级证据传播与局部标注的复合；对多金标集合 F1，需要的是**多样且 vignette 对齐的提交序**。闭集多角色讨论提供的是标签空间受限下的序修正，而不是新的疾病发明。

3. **公平性约束避免虚假增益**  
   冻结 B06 映射臂（`closed_mac_trace_rrf`）可作机制上界，但与外部 run 耦合；逐例相对 MAC 的 ΔF1 置信区间含 0。live 闭集臂切断该耦合后仍不低于 MAC，说明增益可内生于「池内多视角排序」，而非偷用基线名单。

4. **为何树内纯 RRF 不够**  
   `closed_pool_rrf` / `multi_arm_rrf` 未过门控：缺少带 vignette 条件的角色化重排时，仅聚合已有列表不足以改变截断结构。起效依赖 **LLM 在闭集上的条件排序**，而非聚合公式本身。

---

## 3. 机制 B：OX 证据预算重校准（锁定 \(L1=4\) 等）

### 3.1 设计目标

下游默认（DA 论文路径）使用 L1 证据前缀宽度 **F6**（`fixed_l1_budget=6`），组间证据常取前缀中的 **F2** 量级，组内局部证据默认宽度 4。OX 网格表明：不宜把「DA 最优宽度」直接标为 OX 最优。机制 B 在离线代理网格与后续 live 重标对照中，把 OX 锁定为：

\[
L1=4,\quad L2_{\mathrm{local}}=4,\quad B_{\mathrm{between}}=2,\quad C_{\mathrm{cand}}=6,\quad N=15,\quad K=5.
\]

### 3.2 算法含义（各旋钮在流水线中的作用）

1. **\(L1=4\)（组间 L1 证据前缀）**  
   L1 BFS / 竞争迹上取 `prefix_snapshot(trace, 4)`：只冻结前 4 个已选 finding 对应的 L1 后验快照，供后续 Config A / joint 使用。相对 F6，这是**更短的证据条件化前缀**——减少后段低对比 finding 对家族质量的稀释，同时把计算与噪声集中在高对比前缀。

2. **\(L2_{\mathrm{local}}=4\)**  
   `run_joint_primary` 中每个活跃家族的局部证据标注预算。网格上 local=4 相对更窄的 local（如 2）在全树召回代理上更优；含义是：OX vignette 更长、鉴别维度更多时，家族内需要足够多的局部事实才能稳定叶后验。

3. **\(B_{\mathrm{between}}=2\)**  
   组间（跨家族）证据条数。保持较小，避免组间选择器占用过多与局部标注重复的事实配额。

4. **\(C_{\mathrm{cand}}=6\)**  
   每个活 L1 家族保留的叶候选上限（与机制 C 的截断一致）。限制家族内「长尾叶」进入全局后验竞争，迫使质量集中在少数可解释叶上，从而改善 Top-\(N\) 池的纯度。

5. **\((N,K)=(15,5)\)**  
   短列表网格上，在锁定预算代理下 `closed_live` 类重排器以 pool≈12–15、K=5 附近为稳定区；正式公平名采用 **15/5**，与机制 A 一致。

实现上，上述整数经 CLI / payload 注入 `run_diagnosisarena_downstream_top2`；OX 编排脚本写死锁定值，避免与 DA 默认 F6 混淆。

### 3.3 在校准预算下的起效机制

需要区分两阶段证据：

| 阶段 | 预算如何起作用 | 观测 |
|------|----------------|------|
| 离线代理网格 | 以家族/叶保留代理模拟宽窄，不重跑全部 LLM 证据轮 | 锁定组合进入短列表网格；L2 local=4 主导相对 local=2 的全树 R |
| live 重标（与 C 联用） | 真实按 \(L1=4\) 前缀与 local=4 跑证据，再写回后验 | 无 emit 臂 F1 **0.651**；显著高于「仅换短列表、树仍为冷后验」的 0.584 |

单独把锁定参数套在**未写回**的树上（预算代理 + closed_live）并不自动涨分（无 emit 对照曾出现 ≈0.578，略低于原 live）。这说明：

> **预算旋钮的价值，主要在「改变证据条件化 → 改变可写回的后验几何」时释放，而不是作为短列表超参的装饰性重命名。**

在校准预算下，B 的起效应理解为：**为机制 C 提供与 OX 上下文复杂度匹配的证据宽度，并为机制 A 提供更干净的 Top-\(N\) 池。**

### 3.4 起效根因

1. **任务—证据宽度匹配**  
   OX vignette 信息密度高、金标集合大，过宽 L1 前缀会引入低对比事实，使家族后验平坦化，Top-\(N\) 被「略相关」叶占据；过窄则局部鉴别不足。\(L1=4\) 与 \(L2_{\mathrm{local}}=4\) 是该队列网格上的折中，而非普适常数。

2. **候选截断与池纯度**  
   \(C_{\mathrm{cand}}=6\) 限制每家族进入全局竞争的叶数，降低「同一家族大量近义叶挤占池槽」的概率，使 \(N=15\) 更能跨家族覆盖——这与 DA 上 Fine 拥挤问题同构，但作用点从 mapper @1 转到了集合短列表。

3. **不可外推性**  
   根因审计强调「不把 DA 的 F6/F2 直接标为 OX 最优」。B 的合法性来自 **OX 队列重校准**，而不是迁移假设「更宽证据总是更好」。

---

## 4. 机制 C：在线后验写回与家族候选截断

### 4.1 设计目标

annotate 结束时，若只把 joint 的 `final_ranking` 留下、而 `shared_trees` 仍保留建树阶段的冷后验，则机制 A 的 \(\mathrm{TopPost}(T,N)\) 所取之池**看不到**刚完成的局部证据标注。机制 C 把局部 annotator 的叶后验写回状态，并按 \(C_{\mathrm{cand}}\) 截断，使评测阶段的闭集池与「本例证据条件下的信念」一致。

### 4.2 算法（`apply_live_posteriors_and_cap`）

输入：诊断状态 \(S\)；L1 行后验 \(\{m_p\}\)；joint 返回的 `local_outputs`（按父家族组织的叶后验列表）；上限 \(C=C_{\mathrm{cand}}\)。

```text
算法 LivePosteriorWriteback(S, {m_p}, local_outputs, C):
  # （1）写回：家族内局部后验 × 父质量
  for each parent p with posts in local_outputs:
      Z ← Σ max(post_i, 0)  or  1
      for each leaf ℓ in posts:
          π_local ← max(post_ℓ, 0) / Z
          S[ℓ].posterior ← m_p * π_local   # m_p=0 时退化为 π_local
  # （2）截断：每个活 L1 家族只保留后验最高的 C 个孩子
  for each L1 parent p:
      children ← sort_by_posterior_desc(p.children)
      keep ← children[:C]
      p.children ← keep
      for ℓ in children \ keep:
          S[ℓ].posterior ← 0
  return counts
```

随后将序列化状态写入 `annotate/shared_trees/{id}.json`，并标记 `live_reannotated=true` 及预算字段。评测时 `load_tree_state` 读回该树，机制 A 的池即建立在写回后验上。

### 4.3 在校准预算下的起效机制

在锁定预算（机制 B）下跑满证据后：

1. **池位移**  
   写回后 Top-15 的标签集合与冷后验 Top-15 系统性不一致（对照实验中，错误地在写回前评测会得到与原 closed_live 近乎相同的短列表；正确写回后短列表与原版 top1 一致率显著下降）。说明 C 改变的是 **A 的可行讨论域**，而不只是同一池内的微扰排序。

2. **后验几何**  
   写回后叶后验呈连续、经父质量缩放的分布（而非建树阶段常见的粗糙离散档位）。医生/督导在更「尖」的池质量上排序，减少把低支持叶补进提交窗的机会。

3. **与预算的乘性关系**  
   无 emit、锁定 F、写回：F1≈**0.651**（Δ≈+0.067 vs 原 closed_live）。  
   同预算加上 force-emit 旗标但实际补叶数全队列为 0：F1≈**0.645**，不高反略低。  
   结论：在该校准预算下，**起效主体是「证据→后验→池」链路，不是补叶。**

4. **家族截断的辅助作用**  
   实测 `n_capped_dropped` 均值可为 0（池内本就未超过上限），但 \(C=6\) 仍作为硬约束防止极端家族膨胀；写回叶数均值约 23（无 emit）–34（emit 路径配置下），表明更新广度由局部证据覆盖决定。

### 4.4 起效根因

1. **评测接口与训练/标注接口曾经错位**  
   短列表读的是树后验，标注写的是 joint 动态资产。在 DA 的 mapper 路径上，答案往往直接看 `final_ranking`，错位被掩盖；在 OX 的「树后验 → 闭集池 → live 排序」路径上，错位被放大。C 消除的是这一**接口错位**，故增益大。

2. **复杂上下文下冷先验不足**  
   OX 病例叙事长、鉴别支路多。建树先验与有限前缀证据不足以定位多金标同时需要的叶质量；局部证据标注提供 vignette 条件化信号，必须写回才能影响池。

3. **截断型假阴性对池敏感**  
   既然 H2 表明许多假阴性是「叶在树但未进窗」，那么任何能把正确叶推入 Top-\(N\) 的后验修正，都会与机制 A 产生协同；反之，只改 A 的提示而不改池，收益受限（原公平臂 0.584 相对最优 0.651 的差距即此）。

4. **为何 force-emit 在此预算下不起主因**  
   缺口强制补叶未触发（`force_emit_n_total` 全队列和为 0）时，树宇宙未扩大，Open 桶仍在。当前 ΔF1 几乎全部来自闭集信念更新。这与「主导差异来自更复杂上下文下的证据—后验对齐」一致，而不是来自结构补洞。

---

## 5. 三机制在校准预算下的协同与归因

### 5.1 协同结构

```text
        ┌──────────── 机制 B：预算形状 ────────────┐
        │  L1=4 决定条件化前缀                       │
        │  local=4 决定家族内可写回信号密度           │
        │  cand=6 限制家族长尾                       │
        └─────────────────┬──────────────────────────┘
                          ▼
        ┌──────────── 机制 C：信念写回 ────────────┐
        │  局部后验 × 父质量 → 叶后验               │
        │  TopPost(T,15) 的集合发生位移               │
        └─────────────────┬──────────────────────────┘
                          ▼
        ┌──────────── 机制 A：闭集提交 ────────────┐
        │  池内三医生+督导 → Top-5                   │
        │  优化截断与多样性，不解决开集宇宙外金标     │
        └────────────────────────────────────────────┘
```

### 5.2 归因表（同一评测契约下）

| 配置 | 约 F1 | 相对原 closed_live | 说明 |
|------|------:|-------------------:|------|
| 冷树 + closed_live（公平臂） | 0.584 | 0 | A 单独，B/C 未按最优联动 |
| 离线 emit inject + fresh live | 0.588 | +0.004 | 补叶进树但后验极低，难进窗 |
| 锁定 B + C + A（无 emit） | **0.651** | **+0.067** | 当前最优 |
| 锁定 B + C + A（emit 旗标） | 0.645 | +0.061 | 补叶未触发；略逊 |

归因结论（在校准预算下）：

- **主效应**：C（写回）× B（使写回所用证据宽度匹配 OX）；  
- **必要提交器**：A（把写回后的池变成集合友好的 Top-5）；  
- **非主效应**：force-emit / 开集 pad。

### 5.3 根因总述

OX 特有机制之所以在校准预算下起效，是因为它们共同针对同一失败结构：

> **在闭集叶宇宙内，多金标 F1 的主要可解误差是「上下文条件化不足导致的池/序错误（截断）」，而不是「缺少又一次无条件化的自由生成」。**

机制 B 选择与该上下文复杂度匹配的证据宽度；机制 C 把证据变成池可见的信念；机制 A 在闭集内用多视角排序把信念变成提交列表。三者缺一都会把误差重新暴露在评测接口上：无 C 则 A 在错误的池上讨论；无 B 则 C 的信号密度或噪声不匹配；无 A 则写回后验仍可能以同质 Top-5 提交而损失集合召回。

开集缺叶仍是上限，但不解释本轮 +0.06 量级的闭集增益；后续若攻击 Open 桶，应另建生成侧方案，并与本文三机制分表报告。

---

## 6. 公平性、作弊边界与非特有内容

### 6.1 金标与外部基线

| 组件 | 是否读金标 | 是否依赖冻结 B06 | 判定 |
|------|------------|------------------|------|
| L1 前缀 / joint / 写回 | 否 | 否 | 非作弊 |
| closed_live 医生/督导 | 否（只见 vignette 与池标签） | 否 | 公平正式臂 |
| closed_mac_trace_rrf | 否 | **是** | 机制上界，非正式 SOTA |
| tree_oracle_gold_sorted_topk | **是** | 否 | 神谕上界 |
| force-emit 用 ddx∩gap | 视配置；emit_v1 可用开集信号 | 否 | 研究臂；当前最优未依赖 |

### 6.2 明确排除在「OX 特有且起效」之外的内容

- **`compat_parallel` / synonym bind**：转移共享栈，见 DA explainer。  
- **开集 pad / 选择性 MAC 补叶**：未过门或未抬正式 F1。  
- **树内纯 RRF 短列表**：弱于 live 闭集督导。  
- **把 DA F6 当作 OX 默认**：与重校准结论冲突。

---

## 7. 与文档、代码的对应关系

| 内容 | 位置 |
|------|------|
| 闭集 live-MAC 实现 | `build_eval_projection.py` → `ddx_closed_live_mac_supervisor` |
| 后验 Top-N / 投影 | `top_leaf_posterior` / `_project_closed_names` |
| 后验写回与截断 | `diagnosisarena_l2_pipeline.py` → `apply_live_posteriors_and_cap` |
| L1 前缀预算 | `run_diagnosisarena_downstream_top2.py`（`fixed_l1_budget`） |
| OX 两臂编排 | `run_ox_live_reann_arms.py` |
| 公平臂点估计 | `ox_mac_transfer_arms.md` |
| 截断 vs 开集根因 | `ox_vs_mac_rootcause.md` / `ox_best_arm_residual.md` |
| 预算锁定网格 | `ox_budget_recalib.md` |
| live 重标对照 | `ox_live_reann_emit_vs_fopt.md` |

---

## 8. 一句话归纳

在 Open-XDDx 上，特有且在校准预算（\(L1=4,\ L2_{\mathrm{local}}=4,\ B_{\mathrm{between}}=2,\ C_{\mathrm{cand}}=6,\ N=15,\ K=5\)）下起效的机制组合是：**用与队列匹配的证据宽度条件化家族信念，将局部后验写回叶并截断长尾，再在后验 Top-15 闭集上做不依赖外部 MAC 的多医生—督导排序**；其根因是 OX 多金标 F1 对「上下文对齐的闭集进窗」敏感，而当前可解误差以截断与后验错位为主，而非尚未触发的强制补叶。
