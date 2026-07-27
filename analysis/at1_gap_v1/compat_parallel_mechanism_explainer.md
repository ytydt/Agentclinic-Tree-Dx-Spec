# MergeCalibCompat（compat_parallel）机制说明：算法、门控与起效根因

**状态**：方法学入档（与生产默认 `--granularity-mode compat` 对齐）  
**代码**：[`scripts/paper/merge_calib_compat.py`](../../scripts/paper/merge_calib_compat.py)、[`adaptive_merge_siblings.py`](../../scripts/paper/adaptive_merge_siblings.py)、[`topk_calibration.py`](../../scripts/paper/topk_calibration.py)  
**实证**：[`merge_calib_compat_report.md`](merge_calib_compat_report.md)、[`merge_calib_interaction_rootcause.md`](merge_calib_interaction_rootcause.md)  
**评测队列**：DiagnosisArena `d2_seq100_v1`，100 例；无金标 G2（`gold_leaf_ids=[]`）  
**流水线摘要**：[`CURRENT_HIERARCHICAL_DIAGNOSIS_RESEARCH_PIPELINE_EXPLAINER.md`](../../CURRENT_HIERARCHICAL_DIAGNOSIS_RESEARCH_PIPELINE_EXPLAINER.md) §6.1

本文以平实学术表述完整入档：默认后处理模块 **compat_parallel** 的输入输出、各子算法、**FineCrowdGate 门控的定义与起效机制**、**串行互伤与互斥选路的深层根因**，以及作弊/神谕边界。点估计表见兼容烟测报告；个案互伤表见交互根因短文。本文侧重「为什么这样设计、为何能涨点」。

---

## 1. 问题设定

### 1.1 流水线位置

在跨家族联合排序（joint / A3）之后、选择题答案映射（AnswerMapper）之前，系统已拥有一条封闭的 L2 叶诊断排序

\[
R=(r_1,\ldots,r_n),\qquad r_i=(\mathrm{id}_i,\mathrm{label}_i,\mathrm{parent}_i,\mathrm{rank}_i).
\]

该排序在 option **@2 / MRR** 上相对 MAC / Dual-Inf 基线具有覆盖优势，但 option **@1** 转化偏弱：约 19 例呈现「@2 命中且 @1 未中」（集合 A），转化效率 \(P(@1\mid @2)\) 约 0.76，而 MAC 约 0.91。

### 1.2 两类在机制上近似正交的 @1 失败

离线分型与消融表明，@1 失败至少包含两类结构问题：

1. **Fine（过细同义挤占）**  
   多个标签同义或近义的平行叶同时占据前列槽位。映射器若把正确答案挂到其中一叶，而 joint 把另一同义叶放在首位，则「只交换封闭池顺序」无法把两个同义槽位变成一个规范候选——这是**表示粒度 / 等价类**问题，不是单纯证据不足。

2. **排序型近失败（含部分非拥挤病例）**  
   候选叶集合大体合理，但首位被另一家族冠军或特异叙事叶压住。此时封闭池上的支持计数与一级先验回退可以改善**证据序**，而不必改变叶集合的同义拓扑。

两类问题各自对应有效算子：

| 失败子类 | 有效算子 | 优化对象 |
|----------|----------|----------|
| Fine | `AdaptiveMergeSiblings` | 同义叶的等价类与映射槽位 |
| 排序型近失败 | `TopKCalibration(both_l1fallback)` | 封闭池内的证据加权序 |

### 1.3 设计目标

若对同一例**串行**先合并再强校准，实证上净收益低于单独 merge，并出现「两臂单独都对、叠用后错」的交互损伤（病例 140、28；见第 5–6 节）。compat_parallel 的目标是：在**不依赖金标准**的前提下，用可观测的拥挤信号在两种算子间做**互斥选路**，使收益近似可加而非互相抵消。

「兼容」在此不指把两个算子的分数加权融合，而指：**在病例层面把算子分配到其有效的失败子类上**。

---

## 2. 总体算法（compat_parallel）

### 2.1 输入输出与硬约束

- **插入点**：A3 joint 得到 `final_ranking_labels` 之后；AnswerMapper 之前。  
- **输入**：联合叶序 \(R\)、题干 vignette \(V\)、观察 findings、可选的已有 option→叶映射（评测 rematch 用；生产路径可不传）。  
- **输出**：新叶序 \(R'\) 与分支元数据（`merge_only` 或 `calib_only`）。  
- **硬约束**：分支互斥——任一病例至多执行 merge 或强校准之一，**禁止**「merge 后再跑 `both_l1fallback`」。默认 harness 在 `compat` 模式下亦不再串第二次校准。

### 2.2 主流程伪代码

```text
算法 CompatParallel(R, V, findings):
  g ← FineCrowdGate(R)                    # 第 3 节；金标盲
  if g.triggered then
      M ← SynonymMerge(R)                 # AdaptiveMergeSiblings；第 4.1 节
      return (M.representative_order, branch = merge_only)
  else
      C ← TopKCalibrate(R, V, findings, arm = both_l1fallback)  # 第 4.2 节
      return (C.ordered_ids, branch = calib_only)
```

在 DiagnosisArena 100 例、无金标口径下，实测分支频次约为：**merge_only 89 例，calib_only 11 例**；全量 option @1 / @2 / MRR 约为 **0.72 / 0.78 / 0.753**（相对未后处理的 ours：0.59 / 0.78 / 0.688）。

### 2.3 与消融臂的关系

| 臂 | 行为 | all100 @1（约） | 角色 |
|----|------|----------------:|------|
| ours | 不做后处理 | 0.59 | 基线 |
| merge | 对全体强制同义合并，不校准 | 0.68 | Fine 上界参考 |
| both_l1fallback | 不合并，只强校准 | 0.65 | 排序上界参考 |
| both_merge | 先强制合并再强校准（串行） | 0.67 | 互伤对照 |
| **compat_parallel** | 门控互斥选一路 | **0.72** | **默认** |
| compat_serial_safe | 门控为真时 merge 后仅轻量 support 重排并护住 merge Top1 | 0.72 | 消融；未优于 parallel，故不默认 |
| deepen（旧默认） | 过宽 Fine 门控后几乎恒 merge，再串校准 | 0.67 | 历史对照 |

无金标并集上界（每例取 merge∨calib 的 @1）约 **0.75**。compat_parallel 介于「单算子最优」与「神谕并集」之间，且高于任一单算子与串行叠用。

---

## 3. 门控机制（FineCrowdGate）：完整算法

门控是 compat_parallel 的核心路由规则。它须同时满足：

1. **推理时可得**（金标盲）；  
2. **优先识别「同义挤占」**，而非「全榜任意同义」；  
3. **触发不过宽**——过宽会吞掉 calib_only 病例（旧 deepen 路径上全榜同义簇触发率约 99/100，属反面教训）。

### 3.1 字符串规范化

对标签字符串 \(s\)，定义规范化 \(\mathrm{Norm}(s)\)：

1. 转为小写；  
2. 将非字母数字、非汉字字符替换为空格；  
3. 压缩连续空白并去首尾空白。

实现见 `adaptive_merge_siblings._norm`。

### 3.2 同义判定 `labels_synonymish`

对两个叶标签 \(a,b\)，谓词 \(\mathrm{Syn}(a,b)\) 为真当且仅当下列之一成立：

1. \(\mathrm{Norm}(a)=\mathrm{Norm}(b)\)；或  
2. \(\mathrm{Norm}(a)\) 是 \(\mathrm{Norm}(b)\) 的连续子串，或反之；或  
3. 令词袋 \(T_a,T_b\) 为规范化后按空白切分的非空词集合，且

\[
|T_a\cap T_b| \ge \max\bigl(2,\lfloor\min(|T_a|,|T_b|)/2\rfloor\bigr).
\]

```text
算法 LabelsSynonymish(a, b):
  na ← Norm(a); nb ← Norm(b)
  if na = nb or na ⊆_substring nb or nb ⊆_substring na:
      return true
  Ta ← tokens(na); Tb ← tokens(nb)
  if |Ta ∩ Tb| ≥ max(2, ⌊min(|Ta|,|Tb|)/2⌋):
      return true
  return false
```

该规则是**启发式字符串同义**，不是医学本体推理。其操作目的是检测「平行克隆叶 / 修饰变体叶」，以支撑 Fine 挤占的结构判定。假阳性会使本应校准的病例走 merge；假阴性会使 Fine 病例走校准——这是门控误差的主要来源（见第 6.4 节）。

### 3.3 全榜同义簇（并查集）

对 \(R\) 中全部叶建无向图：节点为叶 id；若 \(\mathrm{Syn}(\mathrm{label}_i,\mathrm{label}_j)\) 则连边。每个连通分量为一同义簇。

```text
算法 SynonymClusters(R):
  对每个叶 id 初始化并查集 parent[id] ← id
  for 每对叶 (i, j), i < j:
      if LabelsSynonymish(label_i, label_j):
          Union(id_i, id_j)
  对每个连通分量 C:
      representative(C) ← C 中 joint 秩最小的叶 id
  返回:
      member_to_rep, rep_to_members, representative_order
      （representative_order = 各代表按原 joint 秩升序）
```

实现：`merge_ranking_ids`（[`adaptive_merge_siblings.py`](../../scripts/paper/adaptive_merge_siblings.py)）。

**设计分工**：

- **合并算子**对全榜建簇，避免仅合并 Top2 而遗留第 3、4 名同义挤占。  
- **门控**只读取与**首位相关**的局部信号（见下），避免「远端任意同义对」触发全量走 merge。

### 3.4 FineCrowdGate 布尔条件（收紧后）

设 \(r_1\) 为当前排序首位叶，\(r_2\) 为次位（若存在）。定义两个金标盲谓词：

**（A）Top1 簇拥挤** \(\texttt{top1\_crowd}\)

\[
\mathrm{rep}=\mathrm{member\_to\_rep}(r_1.\mathrm{id}),\quad
\texttt{top1\_crowd} \iff |\mathrm{rep\_to\_members}(\mathrm{rep})|\ge 2.
\]

含义：与首位叶同义的叶在全榜中至少还有一个成员——首位处于同义平行结构中（例如同标签不同父节点的克隆叶）。

**（B）Top1–Top2 标签同义** \(\texttt{top\_synonym}\)

\[
\texttt{top\_synonym} \iff
\bigl(|R|\ge 2\bigr)\ \land\ \mathrm{Syn}(r_1.\mathrm{label},\, r_2.\mathrm{label}).
\]

含义：前两名在标签层已不可分，首位槽位与次席槽位在争夺「同一临床名称」。

**门控触发**：

\[
\texttt{triggered} = \texttt{top1\_crowd}\ \lor\ \texttt{top\_synonym}.
\]

```text
算法 FineCrowdGate(R):
  clusters ← SynonymClusters(R)
  top1_crowd ← false; top_synonym ← false
  if R 非空:
      rep ← clusters.member_to_rep[R[1].id]
      members ← clusters.rep_to_members[rep]
      top1_crowd ← (|members| ≥ 2)
  if |R| ≥ 2:
      top_synonym ← LabelsSynonymish(R[1].label, R[2].label)
  return {
      triggered: top1_crowd ∨ top_synonym,
      top1_crowd, top_synonym,
      top1_id, top1_members, n_leaves, n_clusters,
      merge_info: clusters   # 触发时可直接复用，避免二次建簇
  }
```

实现：`fine_crowd_gate`（[`merge_calib_compat.py`](../../scripts/paper/merge_calib_compat.py)）。

### 3.5 与旧门控的对照（为何必须收紧）

| 规则 | 触发条件 | 100 例约触发率 | 后果 |
|------|----------|---------------:|------|
| 旧 `fine_signal`（deepen） | 全榜任意同义簇收缩：\(n_{\mathrm{clusters}}<n_{\mathrm{leaves}}\) | ≈99/100 | 几乎恒走 merge，calib_only 消失 |
| **现行 FineCrowdGate** | Top1 簇≥2 **或** Top1–Top2 同义 | ≈89/100（merge 支） | 留出约 11 例 calib_only |

旧规则只要榜单远端存在一对同义叶也会强制 merge，使「在未合并池上跑校准」的机会系统性丧失。收紧后，兼容选路在操作上才成为可能。

---

## 4. 两分支的详细算法

### 4.1 分支 A：`merge_only`（AdaptiveMergeSiblings）

当 \(\texttt{triggered}=\mathrm{true}\)：

```text
算法 SynonymMerge(R):
  clusters ← SynonymClusters(R)   # 或复用 gate.merge_info
  R' ← clusters.representative_order 对应的代表叶序列
       （代表叶保留原 label/parent；rank 按新序重写）
  若存在 option→叶映射 M：
      对每个选项命中的叶 id，投影为 member_to_rep[id]
  不调用 TopKCalibration
  return R'
```

评测 rematch 时，簇内任一成员命中可视作该簇位次命中（与离线 merge 臂一致）。

**直观效果**：多个同义平行叶折叠为一个映射槽位，缓解「两个临床同义名称争夺 @1」的结构浪费。在 Agent 确认的 Fine 主模式子集上，单独 merge 与 compat 的 option @1 均可达到 1.0，说明该分支修复的是粒度表示问题。

### 4.2 分支 B：`calib_only`（TopKCalibration，`both_l1fallback`）

当 \(\texttt{triggered}=\mathrm{false}\)，在**未合并**的原始 \(R\) 上执行封闭池校准：

```text
算法 TopKCalibrate(R, V, findings; K=5, α=β=1, γ=0.5, τ=0.5):
  pool ← R 的前 K 个叶                         # G1：封闭候选
  for leaf in pool:
      (n_support, n_contradict) ← Examine(V, findings, leaf.label)
      score[leaf] ← α·n_support − β·n_contradict + γ·(1/joint_rank)
  order ← 按 score 降序排列 pool
  if |score(order[1]) − score(order[2])| < τ:   # 近并列
      允许用 L1-prior 代表叶相对序在 pool 内重排   # L1 fallback
  if 分差仍 < τ:
      PairAdjudicate(order[1], order[2])         # 只允许交换二者
  # 生产路径：gold_leaf_ids = []，不用金标条件 Top2 回退
  return order ⊕ (R \ pool)
```

要点：

1. 不改变叶集合的同义拓扑，只改变证据序。  
2. 适合非拥挤、以排序噪声为主的病例。  
3. L1 fallback 的根因解释见 Explainer §6.1.4（组间仲裁近并列时恢复家族软先验）。  
4. 对 Fine 同义平行叶，两叶标签几乎同义，支持条数往往接近——计数重排**不能消除并列挤占**，故 Fine 主导例必须走 merge 而非本分支。

### 4.3 消融臂 `compat_serial_safe`（非默认）

门控为假时与 parallel 相同；门控为真时：

```text
merge → support_rerank（轻量，无 L1 fallback / pair）
      → PreserveMergeTop1（金标盲：若校准挤掉 merge 代表首位则强制放回）
```

全量点估计与 parallel 同为 0.72，未显示额外优势，故生产默认仍取严格互斥的 parallel，避免在 merge 支引入任何强校准耦合。

### 4.4 生产路径注意点

默认 harness（`--granularity-mode compat`）调用 `run_compat_parallel` 后，**不得**再串第二次 `both_l1fallback`，否则会把「门控为真时禁止强校准」抵消掉。旧路径 `--granularity-mode deepen|merge` 仍可先做粒度再校准，仅作消融。

---

## 5. 门控的起效机制（为何这套路由能工作）

本节专门回答：门控**如何起效**，而不仅复述触发公式。

### 5.1 信号与失败模式对齐

Fine 挤占的操作定义是「多个同义叶占据可映射的前列槽位」。两个谓词分别覆盖两种常见表象：

| 谓词 | 捕获的结构 | 典型情形 |
|------|------------|----------|
| `top_synonym` | 前两名标签不可分 | Top1/Top2 为同义平行叶，直接挤占首位 |
| `top1_crowd` | 首位叶在全榜另有同义克隆 | 同标签不同父、或同义叶落在第 3+ 名但仍与首位同簇 |

二者都是对**当前系统输出结构**的描述，不需要知道正确答案是哪一叶。因此门控估计的是「是否处于 Fine 主导的表示状态」，而不是「哪一臂会赢」。

### 5.2 门控决定算子类，而非偷看胜负

触发后执行全榜同义合并；不触发则在原始 joint 池上校准。选路错误的代价是「用了次优算子」，而不是「根据金标挑选会赢的臂」。后者才构成神谕选臂；compat **未采用**后者。

### 5.3 起效的信息论直觉：充分统计量与子类可分

若失败子类近似可分，且存在可观测的充分统计量 \(G=\texttt{triggered}\) 与子类 \(\mathrm{Fine}\) 高度相关，则路由期望可写为：

\[
\mathbb{E}[\mathbf{1}_{\mathrm{hit}}(\mathrm{Router})]
\approx
\mathbb{E}[\mathbf{1}_{\mathrm{hit}}(\mathrm{Merge})\mid G{=}1]\,P(G{=}1)
+
\mathbb{E}[\mathbf{1}_{\mathrm{hit}}(\mathrm{Calib})\mid G{=}0]\,P(G{=}0).
\]

当 \(G\) 与真实 Fine 主导对齐时，上式接近无金标并集；当 \(G\) 过宽（旧全榜规则，\(P(G{=}1)\approx 0.99\)）时，第二项被系统压低，总期望回落到「几乎全体强制 merge 后再（或不再）校准」的水准。

现行门控把 \(P(G{=}1)\) 从约 0.99 降到约 0.89，使 \(P(G{=}0)\approx 0.11\) 的 calib_only 通道重新打开——这正是全量从 deepen/串行约 0.67 抬到 0.72 的**路由层面**原因之一（另一原因是互斥避免了第 6 节的耦合损伤）。

### 5.4 门控与串行互伤的直接关系

当 \(G=1\) 时，病例更可能处于 Fine 主导。此时若再跑 L1 fallback / pair，是在**已缩簇、秩与家族代表语义已变**的池上施加另一套目标，正是 140/28 类交互损伤的温床（第 6 节）。因此「门控为真 → 禁止强校准」不仅是分配算子，也是用结构信号**规避已知有害交互区**。

### 5.5 分支频次的含义

89/11 的分支比并不意味着「89% 病例是 Fine」。它意味着：在当前树与召回形态下，**首位相关同义结构**在约九成病例上可被检出。其中多数走 merge 是安全且往往有益的（全量强制 merge 已有 @1=0.68）；真正关键的是留下约一成「不拥挤」病例给校准，以吸收纯 C+ 收益（如历史上被过宽门控吞掉的排序型例）。

---

## 6. 深层起效根因：为何互斥优于串行

### 6.1 实证层面的收益分解

在同一 100 例、无金标口径下（详见 [`merge_calib_interaction_rootcause.md`](merge_calib_interaction_rootcause.md)）：

- 相对 ours，merge 单独修好的病例（M+）约 10 例，校准单独修好的（C+）约 13 例，交集约 7；纯 M+ 约 3，纯 C+ 约 6。  
- 无金标并集（每例取 merge∨calib）约 **@1=0.75**；串行 both_merge 约 **0.67**，显著低于并集。  
- compat_parallel 约 **0.72**：高于任一单算子与串行，且逼近并集。  
- **关键交互反例**：  
  - 病例 **140、28**：merge 与 both_l1fallback **单独均为 @1 命中**，串行 both_merge 变为未命中；compat 走 `merge_only` 后保持命中。  
  - 病例 **89**：merge 对、校准错、串行错；compat 走 merge 保持命中。  
- 叠用额外救回极少（如 177 一类），远不够抵消损伤。

结论：涨点来自**按子类分配算子**与**显式避免有害交互**，而非第三套神秘打分。

### 6.2 目标函数耦合：改拓扑 vs 改排序

更深层的不一致在于两算子优化的对象不同：

| | Merge | Calibration (`both_l1fallback`) |
|--|--------|----------------------------------|
| 改什么 | 同义叶的等价类与映射槽位 | 封闭池内的证据加权序 |
| 依赖的稳定量 | 标签层平行结构 | joint 秩、L1 家族后验、examine 计数 |
| 缩簇后的副作用 | 代表叶秩上升、池变短、家族—叶对应变稀 | L1 fallback / pair 仍按「近并列」触发，但并列对象已是缩簇后的代表，语义已变 |

因果链可写为：

```text
Fine 拥挤存在
  → Merge 消灭多余同义槽位，代表叶成为规范 Top1（正确动作）
  → 强校准在缩簇池上重算 score；近并列触发 L1 fallback / pair
  → 「以家族软先验 / 成对裁决重排代表叶」的目标被重新引入
  → 刚稳定的规范代表被挤到第 2
  → 即使校准在未合并原始池上本来也会把金标相关叶排好
     （故出现「两臂单独都对、叠用后错」）
```

这不是随机噪声，而是**目标函数在中间表示变更后发生了耦合**。compat_parallel 在检测到拥挤时拒绝进入该耦合区。

### 6.3 为何「改拓扑」与「改排序」不能默认串行

串行叠用近似于在 Fine 上额外施加一层有损变换 \(T_{\mathrm{calib}}\circ T_{\mathrm{merge}}\)。当 \(T_{\mathrm{merge}}\) 已使表示进入「槽位正确」的区域时，\(T_{\mathrm{calib}}\) 的近并列启发式（为修复**未合并池**上的仲裁噪声而设计）不再匹配新状态，期望命中下降。互斥选路则近似于：

\[
T_{\mathrm{router}}(x)=
\begin{cases}
T_{\mathrm{merge}}(x) & G(x)=1,\\
T_{\mathrm{calib}}(x) & G(x)=0,
\end{cases}
\]

使每个算子只作用在其设计假设成立的区域。

### 6.4 门控自身的局限（解释边界）

- 字符串同义有假阳性/假阴性；假阳性使本应校准的病例走 merge，假阴性使 Fine 病例走校准。  
- 生产路径若缺少 mapper 的 option→叶绑定，Coarse 细分支线本就不在 compat 默认路径内；compat **不声称**修复单叶多选项过粗。  
- 0.72 仍低于无金标并集 0.75，说明仍有路由错误或两臂皆未能修复的残余失败。  
- 方法选型（是否采用 parallel、门控定义）属于验证集上的研究自由度，应在报告中与校准-only、merge-only **分列**，避免表述为单一端到端魔法涨点。换队列时应重估触发率与 @2 护栏。

### 6.5 与各基础算子根因的衔接

compat 不替代下列根因，而是在其之上做路由（详见 Explainer §6.1.4）：

1. **L1 fallback**：组间仲裁近并列、无显式支持计数时，回退家族软先验——对非拥挤排序失败贡献大。  
2. **Support/contradict 重排**：补上 Dual-Inf 式可复现破平；对 Fine 同义叶往往无效。  
3. **Pair**：残余近并列的窄作用面。  
4. **Merge**：改变「何谓一个候选」，在 Fine 子集上接近全恢复。  
5. **Coarse**：叶层重排无法创造可分性；compat 默认不走伪 L3。

---

## 7. 作弊与神谕评估

在本项目口径中，「作弊 / 神谕」特指：**推理或护栏决策使用了评测阶段才应可见的正确答案（选项字母或金标映射叶）**。

| 组件 | 是否读金标 | 判定 |
|------|------------|------|
| FineCrowdGate | 否（仅系统叶标签与同义簇） | 非作弊 |
| merge_only / calib_only | 否 | 非作弊 |
| 正式评测 G2 | `gold_leaf_ids=[]`，不启用金标条件回退 | 非作弊 |
| PreserveMergeTop1（serial_safe） | 否（只看 merge 前后首位 id） | 非作弊；非默认 |
| 旁路烟测金标 G2（历史 0.69） | 是 | 神谕消融，不作正式数字 |
| 若按「哪臂会赢」用金标选臂 | 是 | 神谕；compat **未采用** |

因此，compat_parallel 的正式数字 **没有金标泄漏型作弊嫌疑**。需要诚实披露的是：门控阈值与默认采用 parallel 是基于本队列实证确定的方法选择；换队列应重估，而不是假设 0.72 可无条件外推。

---

## 8. 与文档、代码的对应关系

| 内容 | 位置 |
|------|------|
| 实现 | `scripts/paper/merge_calib_compat.py` |
| 同义 / 并查集合并 | `scripts/paper/adaptive_merge_siblings.py` |
| 封闭池校准 | `scripts/paper/topk_calibration.py` |
| 默认挂载 | `run_diagnosisarena_downstream_top2.py`（`--granularity-mode compat`） |
| 烟测 | `run_at1_calibration_smoke.py --preset compat` |
| 点估计与分层表 | `merge_calib_compat_report.md` |
| 串行互伤个案 | `merge_calib_interaction_rootcause.md` |
| 流水线总述 | Explainer §6.1 |

---

## 9. 一句话归纳

**compat_parallel** 用金标盲的「首位相关同义拥挤」门控（Top1 同义簇成员数 ≥ 2，或 Top1–Top2 标签同义），在「同义合并（改槽位）」与「封闭池强校准（改序）」之间做互斥分配：拥挤则只合并，以免强校准在缩簇池上推翻代表首位；不拥挤则只校准，以免盲目合并或过宽门控吞掉排序型收益。其 @1 提升来自失败子类可分性、算子—子类对齐，以及显式避免已证实的串行目标耦合损伤，而非评测泄题。
