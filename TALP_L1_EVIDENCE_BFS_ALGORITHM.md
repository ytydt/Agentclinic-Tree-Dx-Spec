# TALP L1 Evidence-BFS

## 1. 目标与边界

本算法把 TALP 的首轮诊断判别从“选择一个高概率分支后继续向深层展开”改为“沿证据轴顺序处理、每条证据同时更新全部 L1 家族”。这里的 BFS 是证据队列上的宽度优先，而不是知识图谱遍历。

首轮实验固定以下边界：

- 使用 `recall_hints_gap` 已生成的共享 L1 树；
- 不展开或更新 L2；
- 只允许 vignette 中已有结果的 observed facts；
- 不调用 controller 主循环、动作执行、终止或答案映射；
- P5 与 G2UR 使用同一棵树、同一事实目录和同一证据预算；
- 所有运行时 payload 禁止携带 `gold`、`role`、`decisive`、`direction_target` 等评测字段。

## 2. 实现

核心实现位于：

- `src/agentclinic_tree_dx/l1_evidence_bfs.py`
- `scripts/eval_l1_evidence_bfs.py`
- `src/agentclinic_tree_dx/prompts/l1_evidence_selector.txt`
- `src/agentclinic_tree_dx/prompts/l1_ruleout_evidence_selector.txt`
- `src/agentclinic_tree_dx/prompts/l1_sparse_rule_in_allocator.txt`
- `src/agentclinic_tree_dx/prompts/l1_sparse_rule_out_allocator.txt`
- `src/agentclinic_tree_dx/prompts/l1_branch_evidence_proposer.txt`

### 2.1 不可变病例与选择状态

`L1EvidenceBFSState` 分开保存：

- 不可变的完整 vignette；
- 不可变的 observed-fact 语义目录；
- 不可变的 P5/G2UR compiler master blocks；
- 可变的 `eligible/consumed` 状态；
- 已计分证据历史；
- L1 posterior 轨迹。

每个微轮校验 case、fact catalog 和 compiler master 的 SHA-256。消费证据只改变选择资格，不删除病例事实；allocator 始终看到完整病例上下文。

### 2.2 选择循环

每个 cycle 最多产生两个事实：

1. 全局 selector 在未消费事实中选择 P5 风格 Top-2；
2. 可选 rule-out selector 独立寻找 observed 排除证据；
3. 固定预算 dual-lane 使用 global rank1，并以有效、未重复的 rule-out rank1 替换 global rank2；
4. 每条事实作为独立微轮处理，然后标记 consumed；
5. 默认运行两个 cycle、最多四个微轮。

迭代 selector 支持 `verdict=none`，用于剩余池已无有效判别项的情况。P5 强制选择语义保留为独立参数化回退。

### 2.3 稀疏方向分配

每个事实由两个独立 consumer 处理：

- rule-in consumer：`specific` 后输出 1–3 个有序 L1 branch ID，或输出 `none`；
- rule-out consumer：独立输出 1–3 个排除目标，或输出 `none`。

列表绝不补齐。两个方向都为 `none` 时 posterior 不变。同一分支同时出现在两个方向时，该分支本轮信号清零并记录冲突。

### 2.4 对称顺序更新

候选顺序积分为：

\[
c=[1, 0.5, 0.25], \quad \eta=\ln 3
\]

\[
\Delta z_i=\eta(c_{\text{rule-in rank}}-c_{\text{rule-out rank}})
\]

\[
p_i'=\operatorname{softmax}(\log(p_i+\epsilon)+\Delta z_i)
\]

rule-in 与 rule-out 使用对称幅度；输出是 normalized belief score，不声明为临床校准概率或 LR。

## 3. 参数化回退

实现冻结了以下 preset：

- `p5_eval_compat`：原 P5 SELECT/DIRECTION/RULE-OUT 能力语义，仅用于能力指标；
- `p5_single_direct`：P5 单目标语义接入直接 L1 更新；
- `p5_single_abstaining`：在单目标更新上增加迭代 selector abstention；
- `e1q_legacy`：现有 Top-2、七档 EvidenceAnnotator、ordinal update；
- `bfs_sparse`：稀疏 Top-3 与对称 log-score；
- `bfs_sparse_dual_ro`：增加专用 rule-out 选择通道；
- `bfs_sparse_branch_proposal`：逐分支提案再合并的候选方案。

preset 在运行前确定。单病例不得因 sparse 输出不理想而动态切换 P5。

## 4. L1 评测契约

Track A 使用人工候选集投影和 uniform prior，测量 SELECT、rule-in target、rule-out target、SHARED/none 与 depleted-pool abstention。

Track B 使用冻结的动态 L1 树，同时报告：

- branch prior；
- uniform prior；
- round 0–4 gold rank 与 posterior；
- probability@1、Top-3、MRR；
- starvation、选择置换和 compiler provenance 命中。

人工候选集的 gold L1 使用 gold candidate 自身的 `l1_parent`。数据中的独立 `l1_label` 只做一致性审计，避免在候选集外凭空增加家族。冻结的 17 题中，12 题含 observed cross-L1 rule-out finding，共 16 条。

病例 ID 是 bootstrap 的独立单位；profile、arm 和 prior mode 在同一 case 内配对。

## 5. 实验臂

- B0：E1q legacy；
- B1：P5 single-target direct update；
- B1s：B1 加 selector abstention；
- B2：sparse ranked targets；
- B3：B2 加 dedicated rule-out selector；
- B3x：B3 的 budget+1 displacement 诊断；
- B4：关闭 rule-out allocation；
- B5：只运行首个 cycle；
- B6：关闭 canonical dedup；
- A：逐分支 evidence proposal。

正式运行命令：

```bash
PYTHONPATH=src python scripts/eval_l1_evidence_bfs.py \
  --profiles p5_headline,g2ur \
  --arms B0,B1,B1s,B2,B3,B3x,B4,B5,B6,A \
  --tracks A,B \
  --prior-modes branch,uniform \
  --n-boot 5000 \
  --tag formal_l1_bfs_v1 \
  --resume
```

## 6. 质量门

B2 相对 B1 必须同时满足：

- Track A SELECT-valid、rule-in、rule-out 与 SHARED 不回归；
- 原始池 false-abstain 不增加；
- depleted pool false-select 下降；
- Track B gold existence、Top-3 与 MRR 不下降；
- probability@1 或 MRR 的病例级配对 95% CI 至少一项 resolved positive；
- compiler `n_use`、rule hit 和 provenance 非空。

B3 还必须证明专用 rule-out selector 在固定预算下改善 target accuracy 或 L1 排名。A 臂只有在 `ΔSELECT@1` 的 95% CI 下界大于 0 且 SELECT-valid 不回归时才可替换全局 P5 selector。

## 7. 验证

单元与隔离测试覆盖：

- preset 组合；
- gold-leak payload 拒绝；
- `none` 与非法 Top-K schema；
- 对称更新和冲突冻结；
- 病例、事实目录和 compiler master 不可变；
- consumed 事实不可二次计分；
- dual-lane displacement；
- 17 题共享树与 L1 投影；
- case-cluster bootstrap；
- controller/AnswerMapper 隔离。

正式结果以 `logs/l1_evidence_bfs/formal_l1_bfs_v1_merged/summary.json` 及四个
`formal_l1_bfs_v1*` 分片下的 manifest、trace 和 LLM cache 为准。

## 8. 17 题正式结果

四个可恢复分片最终合并 934 条有效记录，错误为 0。Track B 为完整 17 题；`mxh014`
的人工候选全部属于同一个 L1，无法构造跨 L1 竞争，因此 Track A 的有效分母为 16。
运行时 controller、L2、动作、终止与 AnswerMapper 调用均为 0。

### 8.1 最强结果不是稀疏 Top-K，而是 P5 单目标直接更新

P5/B1 在 branch-prior 轨达到 probability@1 82.4%、Top-3 100%、MRR 0.892，
starvation 5.9%；B0 legacy 分别为 52.9%、76.5%、0.674 和 41.2%。

病例级配对 bootstrap 的 B1−B0 为：

- probability@1 `+29.4` 个百分点，95% CI `[+11.8,+52.9]`；
- MRR `+0.219`，95% CI `[+0.083,+0.375]`；
- 平均 rank 改善 `0.882`，95% CI `[0.353,1.471]`。

G2UR/B1 为 probability@1 64.7%、Top-3 100%、MRR 0.804。相对 G2UR/B0，
probability@1 `+17.6` 点但 CI `[−5.9,+41.2]` 未 resolved；MRR `+0.170`
和平均 rank 改善 `0.824` 的 CI 下界均大于 0。G2UR 只有 15 个 compiler evidence
hit，而 P5/B1 为 352，因此不能把该点估计解释成 G2UR 知识增益。

共享树的 L1 prior 实际为均匀分布，所以本批 branch-prior 与 uniform-prior 结果相同。

### 8.2 B2/B3 未过晋级门

P5/B2 的 probability@1、Top-3、MRR 为 52.9%、94.1%、0.718；相对 B1：

- probability@1 `−29.4` 点，95% CI `[−52.9,−11.8]`；
- MRR `−0.175`，95% CI `[−0.329,−0.037]`；
- mean-rank gain 为 `−0.529`，CI `[−1.118,0]`。

P5/B3 与 B2 的三项头条值相同。G2UR/B2 为 41.2%/82.4%/0.617，
G2UR/B3 为 47.1%/88.2%/0.671；两者仍显著或方向性低于 G2UR/B1。
因此 sparse 0–3 targets 和 dedicated rule-out lane 都不能替代 B1。

根因由 Track A 直接显示：

- P5/B2 的 rule-in target@3 为 70.8%，高于 B1 的 50.0%，但 target@1 只有
  58.3%；多目标覆盖没有转化为正确的首位分支。
- P5 显式 shared facts 上，B1 只有 1/14 次两个方向均正确 `none`，B2 为
  1/16；G2UR/B2 为 0/16。Top-K 扩展没有保住 P5 `none` 的预期优势。
- 所有 abstaining selector 在显式 depleted pool 上的 false-select 均为 100%；
  selector schema 虽允许 `none`，模型并未实际使用。
- B6 与 B2 完全同值，当时基于 typed `concept` 的 canonical dedup 不是主要瓶颈；
  **2026-07-14 F30 9-run 审计修正**：语义变体（同 reference finding 不同表述）在
  F2/F4 分别占 34/153、63/153 前缀，18/25 条最终失败——见 §10.6。
- B5 的两微轮结果也没有显示第 3–4 微轮带来头条增益。

### 8.3 专用 rule-out selector 只有可行性信号

16 个 Track A 病例中有 12 个存在 observed cross-L1 rule-out finding。B3 的
RO-SELECT-valid 为：

- P5：7/12（58.3%）；4 个无此类 finding 的病例中 3 个正确 abstain；
- G2UR：8/12（66.7%）；4 个无此类 finding 的病例中 2 个正确 abstain。

固定预算下两 profile 都发生 10 次 global-rank2 displacement；其中 P5 有 5 次、
G2UR 有 3 次挤掉了有效判别事实。P5/B3 的 rule-out target@3 为 54.5%，相对 B2
的 50.0% 只有小样本点估计改善，且 L1 头条排名无增益。故该部件记为 feasibility
signal，不晋级。

### 8.4 其他臂

- B3x budget+1 只把 P5 MRR 从 0.718 提至 0.728，未恢复 B1 的 0.892；
- B4 关闭 rule-out allocation 后 P5 MRR 为 0.730，提示当前排除分配可能带来噪声；
- branch-proposal 的 SELECT@1 未获得 resolved superiority，且最终 P5 MRR 仍为
  0.718，不满足替换全局 selector 的条件；
- B1s 对 P5 低于 B1（probability@1 70.6% vs 82.4%），对 G2UR 高于 B1
  （70.6% vs 64.7%），但 depleted false-select 仍为 100%，不能据此晋级 abstention。

## 9. 裁决

本轮不接入生产 controller。B2 主算法与 B3 双通道均未通过预注册晋级门，
branch-proposal 也未通过替换门。

可保留的研究候选是 `p5_single_direct`：它验证了“对全部 L1 使用 P5 单一
rule-in/rule-out 目标并直接更新”能显著改善家族排名。下一步若继续，应以 B1 为新实验
锚点，优先修复 shared/depleted abstention，而不是继续扩大 Top-K。原
`e1q_legacy` 和 `p5_eval_compat` preset 继续作为显式回退。

## 10. 自适应轮次（2026-07-13）

### 10.1 实现与安全边界

固定 F4 仍是默认执行策略。新增自适应能力位于：

- `src/agentclinic_tree_dx/adaptive_stopping.py`
- `src/agentclinic_tree_dx/prompts/l1_stop_challenge_advisor.txt`
- `scripts/eval_l1_bfs_adaptive_stop.py`

`StopSnapshot` 只包含 cycle/micro-round、top-pair ordinal margin、JS 变化、
有效更新数、剩余事实数、compiler/provenance hit 等无标签信号。
`StopDecision` 只有 `continue/stop`、原因、challenge fact ID 和回退审计。
两种 schema 都递归拒绝 gold、role、decisive、confidence、probability 等字段。

运行时硬边界为 `min_micro_rounds=2`、`max_micro_rounds=8`。由于 selector queue
可能不足两个事实，硬上限按实际 micro-round 而不是 cycle 计数。受限
`L1StopChallengeAdvisor` 只能返回未消费的精确 fact ID，以“反对 top-1 或支持
top-2”的事实否决停止；它不能单独授权 STOP。调用或 schema 失败时，第 4 个事实前
继续到 F4，第 4 个事实后停止并记录 fallback。完整 F8 数据生成使用 shadow policy，
所以 advisor 决策不会截断用于 replay 的前缀。

### 10.2 17 题完整前缀结果

正式产物位于
`logs/l1_bfs_adaptive_stop/talp17_adaptive_stop_v1/`。17/17 个 P5
`p5_single_direct` F8 轨迹成功，无运行错误。

- F2：gold-rank@1 70.6%，Top-3 94.1%，MRR 0.809；
- F4/B1：gold-rank@1 82.4%，Top-3 100%，MRR 0.892；
- F6：gold-rank@1 76.5%，MRR 0.863；
- F8：gold-rank@1 64.7%，MRR 0.824，3/17 出现 overthinking-to-error；
- gold-only oracle 最早前缀：平均 2.65 facts、p90 4 facts，gold-rank@1
  82.4%、MRR 0.912。

Oracle 说明“病例依难度选择前缀”存在明显 headroom，但当前无标签信号没有定位到该
前缀。默认 S1 饱和策略平均运行 7.88 facts，S2 challenge 策略运行 8 facts；两者
gold-rank@1 均为 64.7%、MRR 均为 0.824，既没有节省 20% facts，也低于 F4。
探索性 LOCO 中，S1 平均 7 facts、gold-rank@1 64.7%、MRR 0.814，S2 仍为 8 facts。
S1/S2 均未通过 17 题 feasibility 门。

因此当前裁决不是“允许 agent 自主决定轮数”，而是：

1. F4 继续作为可执行默认和失败回退；
2. F8、S1、S2 只保留为 shadow/replay 研究臂；
3. `none`、稳定 margin 或 advisor 自报都不能作为生产安全停止信号；
4. 下一步应研究能预测 F4 后 harmful update 的无标签信号，而不是放宽到自由 agent；
5. 现有 17 题已用于开发，独立验证门明确为 `not_evaluated`。若要求零 observed
   premature-stop 时 95% 风险上界不超过 5%，至少需 59 个独立 accepted cases。

### 10.3 失败诊断、证据法定数策略与 F4 独立重跑

S1/S2 的失败不是阈值略偏，而是停止语义错误。69 个 cycle snapshot 中，旧
`effective_updates <= 0` 条件只通过 2 个，四项 saturation 条件同时通过也只有
2 个；因此 S1 有 16/17 个病例运行到 F8。S2 的 advisor 在 52/52 次调用中均返回
challenge fact，完全没有 `none/uncertain`，使其 17/17 运行到 F8。F4 到 F8 期间，
gold rank 仅 2 例改善、3 例恶化、12 例不变；gold top-1 是 0 例获得、3 例丢失。
这证明“存在任意剩余 challenge”不能近似下一轮的正期望价值。

新增两个无 gold、F4 有界策略：

- S4 `EvidenceAnchoredF4Policy`：F2 时只看 margin 和有效更新，过于宽松，13/17
  在 F2 退出，gold-rank@1 降至 76.5%，被否决；
- S5 `EvidenceQuorumF4Policy`：只在两个独立事实都支持同一个**新出现的** leader、
  没有事实 rule-out 该 leader、且 ordinal margin 至少为 `log(1.5)` 时于 F2
  退出；否则固定运行到 F4，绝不扩展到 F6/F8。

S5 在冻结轨迹上有 5/17 个病例于 F2 退出、12/17 于 F4 退出；平均 facts 从 4
降至 3.41（节省 14.7%），gold-rank@1、Top-3、MRR 分别保持 82.4%、100%、
0.892，与 F4 完全相同。病例级 bootstrap 的 facts saved 为 0.588，
95% CI `[0.235, 1.059]`；质量差值均为 0。但它未达到预设的 20% 成本降幅，
而探索性 LOCO 还出现 Top-3/MRR 回退，因此只能作为新的 shadow 候选，不能晋级。
重跑必须区分两种协议：

- 两个直接 fixed-4 B1 空缓存运行的 gold-rank@1 均为 70.6%，Top-3 均为
  94.1%，MRR 为 0.828/0.819；二者 leader 一致率 100%；
- adaptive harness 中严格的 F4 是“新生成 F8 全轨迹的前四 facts”。两个独立
  `temperature=0` full-horizon 运行的 F4 前缀仅为 58.8%/52.9% gold-rank@1，
  Top-3 为 100%/94.1%，MRR 为 0.755/0.721；二者 leader 与 gold-rank 一致率
  都是 88.2%，证据序列完全一致率 82.4%。

因此直接 B1 不能替代严格的 F8-prefix F4 复现。原单轨迹 82.4% 明显偏乐观，
temperature=0 也没有消除 provider/selector 的运行差异。S5 在两个 direct B1
运行上以 3.41 facts、在两个严格 full-horizon 运行上以 3.53 facts，均保持各自
F4 的逐病例 gold rank 完全不变；非回归已跨五条生成轨迹重复，但病例仍是同一
17 题。严格 full-horizon 的两例 selector repair 失败发生在 F4 之后，采用确定性
eligible fallback 只为完成 F8，不影响所报告的 F4 前缀。

因此后续协议固定为：新运行显式记录 temperature；F4 至少做两个空缓存重复并同时
报告质量均值和病例级一致率；自适应策略先以 F4 为硬上限。重跑比较见
`logs/l1_evidence_bfs/f4_rerun_comparison.json`。

### 10.4 S5 在线非 shadow 测试

为排除 prefix replay 不能证明真实截断的问题，`eval_l1_evidence_bfs.py` 新增
`S5` 在线 arm，直接把 `EvidenceQuorumF4Policy` 接入 `L1EvidenceBFSPipeline`，
并与同一空缓存、temperature=0 的 B1/F4 做病例级共享前缀配对。

17 题全部成功：

- 6/17 在 F2 真实停止，11/17 在 F4 停止；
- 平均 facts 从 4 降至 3.294，节省 17.6%；
- paired facts saved 为 0.706，95% CI `[0.235, 1.176]`；
- S5 与配对 F4 的 gold-rank@1、Top-3、MRR 均完全一致，分别为
  70.6%、94.1%、0.819；逐病例 rank 差全部为 0。

因此 S5 的成本削减不是 replay 假象，在线控制路径可用。但节省仍低于预注册的
20% 门，且测试仍使用开发中的同一 17 题，所以维持 shadow，不替换 F4。产物位于
`logs/l1_evidence_bfs/s5_online_t0_v1/`。

### 10.5 F4/F6/F8 运行间重复性核验

为避免用单条高分或低分轨迹裁决预算，新增
`scripts/analyze_l1_bfs_budget_replicates.py`，对独立完整 F8 运行的配对
F4/F6/F8 前缀做两层统计：病例是外层 cluster，运行重复在病例内重采样。主分析纳入
9 条 `temperature=0`、空缓存、相同 run fingerprint 的完整轨迹，共
153 个病例×运行观察，但外部有效样本量仍为 17。

- F4：平均 gold-rank@1 64.7%，运行间 SD 7.8 点，范围 52.9%–76.5%，平均
  MRR 0.788；
- F6：平均 gold-rank@1 64.7%，SD 7.2 点，平均 MRR 0.801；
- F8：平均 gold-rank@1 71.9%，SD 6.4 点，范围 64.7%–82.4%，平均 MRR
  0.837；
- F6−F4 的 @1 差为 0，95% CI `[-16.3,+13.1]` 点；11 次纠正与 11 次破坏
  完全抵消；
- F8−F4 的 @1 差为 `+7.2` 点，95% CI `[-9.2,+24.2]`；MRR 差
  `+0.049`，95% CI `[-0.039,+0.142]`。19 次纠正、8 次破坏，趋势为正但
  两项区间均跨 0。

病例效应并不均匀：`mxh036` 在 9/9 次由 F4 miss 纠正为 F8 top-1；
`mb66_peliosis` 在 5/9 次被纠正、4/9 次保持正确；但 `mb11_pancoast`
在 7/9 次由 F4 top-1 被 F8 破坏。`mb65_cml` 与 `mxh045` 则 9/9 在两个
预算下都错误。固定 F8 的净收益主要是少数稳定受益病例与一个稳定受害病例的合成，
不是普遍单调改善。

两条 standalone fixed-4 的 70.6% 落在 F8-prefix F4 的重复分布内，因此早期
58.8%/52.9% 不能解释为 prefix 协议系统性更差；原 82.4% 也不能继续作为稳定
headline。第 10 条运行暴露 JS divergence 的浮点负零，修复为理论要求的
non-negative clamp 后改变 stop-core 指纹，故只作敏感性分析
（F4/F6/F8 为 58.8%/70.6%/70.6%），不混入主统计。

当前裁决随之修正：F4 只是成本较低的保守参考，不是已证实最优；固定 F6 不晋级；
固定 F8 保留正向研究候选，但尚不能替换 F4。下一步重点是构建能识别
`mxh036/mb66` 型 late-evidence debt、同时阻止 `mb11` 型 overthinking 的
label-blind guard，并在新病例上验证。主产物为
`logs/l1_bfs_adaptive_stop/f4_f6_f8_t0_replicate_verification_v1.json`。

### 10.6 F30 饱和与 F2/F4 选择召回根因（2026-07-14）

9-run F30 实验（`max_micro_rounds=30`、`temperature=0`）与 P5 冻结 arm 的同口径复核
（`subagent_audit_smmary.md` 末章）修正了“P5 方向 >80% ⇒ F2>80%”的推导。

**同口径数字（9 runs × 17 cases = 153 obs）**

| 预算 | gold-rank@1 | 主因 |
|------|------------|------|
| F2 | 56.9% | 选择覆盖不足（仅 41.2% 前缀选到 P5 判对 rule-in） |
| F4 | 63.4% | 新增 L2→L1 投影失败与等权累积覆盖 |
| F22+ | 74.5% | 有限 pool（~19 effective facts）观察平台，非统计饱和 |

**条件成功率**：F2 选到 P5 判对且 decisive 的前缀 @1 = 93.3%（42/45）；
F4 = 90.6%（58/64）。方向能力在“选中且投影成功”时仍高，瓶颈是召回与传递。

**F2 失败分解（66 obs）**

1. 47：无 P5-correct、无 gold L1 支持——选择饥饿 + forced selector 消费 shared/unmatched。
2. 3：P5-correct 但未投影到 gold L1——L2→L1 传递失败。
3. 16：gold 并列最高但 branch-id tie-break 判负——@1 计分伪影（tie-aware 67.3%）。

**F4 新增机制**

- P5 叶级正确但未命中 gold L1：54/145 次。
- F2→F4 净增 10/153（mb55/mb77 修复 vs mxh075/mb34 伤害）。
- 语义重复计票：63/153 前缀映射同一 reference finding；固定 η 等权更新。

**两类选择错误与修复方向**

| 错误模式 | 主责部件 | 修复 |
|---------|---------|------|
| 原型锚定（显著表现替代候选对比） | harness + compiler（缺 effect matrix；错签 USE）+ LLM | 动态 contrast 矩阵、扩展 selector schema、允许 abstain |
| 语义变体重复占 @1/@2 | harness `canonical_key` 缺 concept 时退回文本 | reference_finding_id 簇、concept ledger、同 group 最多选一次 |

**harness 已知缺陷（与饱和分析联动）**

- `p5_forced` 不允许弃权；pool exhaustion 使 F22–F30 名义臂坍缩。
- 冻结 compiler 仅覆盖 40/81 findings；BFS 不做运行时争议补编译。
- `truncated_by_pool_share` 语义错误；`detect_saturation()` 对 pool 坍缩无防御。

主产物：`logs/l1_bfs_adaptive_stop/f30_saturation_t0_replicate_verification_v1.json`。

### 10.7 Selector 反锚定、辩论与证伪门控（2026-07-14）

针对 §10.6 的“原型锚定”和“语义重复占槽”，新增 matrix selector：
`p5_contrastive_direct` 与 `p5_anti_anchor_direct`。两者向 selector 暴露冻结 L2 叶示例，要求输出全候选
`candidate_effects`、supported/contrasted branch、canonical concept key，并允许
abstain；schema validator 拒绝不完整矩阵、弱对比和同概念重复，concept ledger
继续阻止跨轮重复计票。matrix response 若缺候选 effect，运行时只允许一次 schema
repair；再次失败即安全 abstain，不再回退 forced selector。

孤立评测只运行事实选择，不运行方向分配或后验更新。旧 forced baseline 为 9 次重复；
下列新臂为同一 17 例、`temperature=0` 的 3 次空缓存重复。评分仍使用
`_best_reference` 启发式 matcher；已修复 evaluator 只精确匹配角色 `shared`、
漏掉 `shared_*` 的缺陷，因此旧报告中的 `shared_or_trap@1=0` 无效。

| selector 臂 | observed-decisive SELECT@1 | SELECT@2 | 原型锚定代理@1 | shared/trap@1 | reference 重复@2 |
|---|---:|---:|---:|---:|---:|
| contrastive current | 35.7% | 59.5% | 13.7% | 15.7% | 5.9% |
| anti-anchor prompt | **54.8%** | **76.2%** | 13.7% | 17.6% | **0%** |
| 双提案 + 自由仲裁 | 45.2% | 73.8% | 15.7% | 15.7% | 7.8% |

反锚定提示相对 current 的 SELECT@1 为 `+19.0pp`，病例配对 bootstrap 95% CI
`[0,+40.5]`，只能称强趋势；SELECT@2 为 `+16.7pp [ +2.4,+33.3 ]`，获得明确支持。
但原型锚定代理率没有净下降：`mb34` 仍把 leukocytosis/LAP 放在决定性项之前，
且理由错误地把 elevated LAP 说成支持 CML；`mxh075` 的改善与该回归互相抵消。
反锚定 prompt 的 51 次响应有 13 次需要补全 effect matrix 的 schema repair，
说明长提示改善了搜索次序，但没有稳定改变模型的医学先验或格式遵循。

集成裁决：`p5_anti_anchor_direct` 已作为 adaptive BFS 脚本默认 preset，并在通用
BFS arm 中注册为 `B1a`；历史 `B1=p5_single_direct` 与
`p5_contrastive_direct` 均保留为显式回退。该晋级依据是 observed-decisive
SELECT@2 的 resolved 改善和重复归零，不应被改写为“原型锚定已经解决”：
SELECT@1 CI 下界仍为 0，shared/trap 与锚定代理均未改善。新运行必须在 manifest
记录 preset 与 selector prompt hash，后续整条 BFS @1 若回归可直接回退旧 preset。
单病例默认路径烟测
`logs/l1_bfs_adaptive_stop/anti_anchor_default_smoke/` 已完成 F2 全链路：
manifest 记录 `p5_anti_anchor_direct` 与 prompt hash，selector schema 有效、
未触发 repair/semantic rejection，gold rank 保持 1；该烟测只验证接线，不作为性能证据。

自由仲裁相对 anti-anchor 的 SELECT@1/2 分别低 `9.5/2.4pp`，同时重新引入重复与
锚定。病例审计显示仲裁器经常原样复述某一提案理由；同模型、同 vignette、同冻结
规则产生高度相关错误，多一次自由排序不构成独立证据。因此该辩论形态不晋级。

随后实现受限证伪门控：

1. primary 固定为 anti-anchor proposal；
2. 仅当 current 与 anti-anchor 的 Top-1 不同才调用 critic；
3. critic 只能依据冻结 compiler rule/provenance 返回
   `falsified/not_falsified/insufficient`，不得排序或提出事实；
4. 外部知识缺失不能当反证；只有 anti proposal 被明确 falsify 才回退 current，
   两者均 falsify 才 abstain。

3 次重复共 51 个观测，Top-1 disagreement 触发 18 次（35.3%）；只有 5/18
触发项带任何冻结外部证据。critic 对 36 个提案审计全部返回 `insufficient`，
没有一次 veto，故 gated 臂与 anti-anchor 的全部指标逐项完全相同。该结果说明：
**证伪式控制流是安全、可审计的，但仓库当前外部知识不含足够的
finding×当前候选比较断言，因而门控为空操作。** 这不是对证伪 critic 理论的否定，
而是对当前 frozen compiler 资产覆盖和比较语义的否定；在补充带 value/polarity、
favored-present 与 competitor-absent/weaker、逐条 provenance 的外部 claim 前，
不得把 `insufficient` 放宽成模型先验判断，也不得晋级该门控。

产物：

- `logs/l1_contrastive_selection_isolated_v1/summary.json`
- `logs/l1_anti_anchor_debate_isolated_v1/summary.json`
- `logs/l1_falsification_gate_isolated_v1/summary.json`
- `scripts/eval_l1_contrastive_selection.py`
- `scripts/eval_l1_anti_anchor_debate.py`
- `scripts/eval_l1_falsification_gate.py`

### 10.8 非题干 finding 可见性与 L2 预展开核验（2026-07-15）

17 例运行时可见性审计确认：

- annotation 中共有 16 条 `in_vignette=false` finding；0 条原文出现在
  `case_text`，0 条通过 static evidence 或 reference matching 进入 observed fact
  catalog。selector 的 `case_context` 仍是完整原始 vignette，并同时看到从题干拆出的
  observed fact catalog；被隐藏的是尚未观察到的预期结果，不是从原题干删掉一段病例描述。
- 这些隐藏项包括 `absent Philadelphia chromosome/BCR-ABL`、特定病原体培养阳性、
  `severe fasting hypoglycemia with lactic acidosis` 等带值和方向的未来结果。即使去掉
  role/decisive 标签，把原文作为“不可选上下文”显示也会泄漏尚未获得的患者结果，
  不符合 observed-only BFS 边界。
- L2 预展开已真实接入 selector：17 例共 83 个 L1 branch，83/83 都有
  `leaf_exemplars`，合计 323 个冻结 L2 具体病名。anti-anchor prompt 明确要求基于这些
  leaf exemplars 做 finding×candidate 对比。因此“BFS 只能看到抽象 L1 名、看不到
  二级具体病名”已不是当前实现状态。

为检验“完全看不到潜在检查是否妨碍病例理解”，没有注入上述泄漏性结果，而是测试了
label-blind 安全替代：从冻结树的 `askable_discriminators`/
`requestable_discriminators` 构造不可选择、结果统一标为 unknown 的 test menu；
selector 最终仍只能返回 observed `eligible_fact_ids`。同一 anti-anchor baseline、
17 例×3 次重复的结果为：

| 输入 | observed-decisive SELECT@1 | SELECT@2 | 相对 baseline |
|---|---:|---:|---|
| observed-only baseline | **54.8%** | **76.2%** | — |
| test menu ≤64（均值 53.5 项） | 38.1% | 61.9% | −16.7pp / −14.3pp |
| test menu ≤12 | 33.3% | 66.7% | −21.4pp / −9.5pp |

≤64 臂的配对 CI 分别为 `[-35.7,0]`、`[-33.3,0]`；≤12 臂的 SELECT@1
差为 `−21.4pp [-42.9,-4.8]`，是明确回归。短菜单并未解决注意力负担，还使
schema repair 增至 21/51，3/51 在一次 repair 后仍无效。病例级退化集中在
`mb66`（AAS→RUQ pain）和 `mxh075`（复合 decisive→泛化 single S2）：
未回答问题虽然没有被当作事实直接选中，却重新激活了显著性/疾病原型锚定。

裁决：保持 raw non-vignette expected results 完全不可见；不把 branch test menu
注入 observed-evidence selector。L2 leaf exemplar 继续保留。若未来需要主动检查规划，
应在独立 action/request lane 中消费未知结果菜单，而不是混入“已观察事实排序”输入。

产物：

- `logs/l1_unobserved_test_menu_isolated_v1/summary.json`
- `logs/l1_unobserved_test_menu12_isolated_v1/summary.json`
- `scripts/eval_l1_unobserved_test_menu.py`

### 10.9 直接以 L2 为 evidence-selector 区分标的（2026-07-15）

§10.7–10.8 的默认实现是“L1 为 effect matrix 列，L2 为
`leaf_exemplars` 上下文”。本节新增 direct-L2 孤立臂：把冻结树的所有叶级 L2
branch 平铺为 `candidates`；`candidate_effects`、`supports` 和
`contrasts_with` 均必须直接使用 L2 ID，不再以 L1 family 为证据拣选标的。
选择后的 L1 allocation/update 未运行，因此本节只回答 SELECT@1/@2。

该臂并不等价于 P5 的人工候选列表。P5 每例通常有 4–5 个具体病名；实际生成树每例
有 15–22 个 L2（均值 19）。17 例的 84 个 P5 候选名中，只有 30 个与生成 L2
精确同名，44 个存在字符串包含关系；`mxh014`、`mxh068` 甚至没有包含匹配。
因此 direct-L2 同时引入了候选扩张与候选集合漂移。

17 例×3 次、同一 anti-anchor prompt 和 observed fact catalog 的孤立结果：

| selector 区分标的 | observed-decisive SELECT@1 | SELECT@2 | 原型锚定代理@1 |
|---|---:|---:|---:|
| L1 targets + L2 exemplars（当前） | **54.8%** | **76.2%** | 13.7% |
| flat direct-L2 targets | 42.9% | 64.3% | 17.6% |

direct-L2 相对当前臂的 SELECT@1/@2 均为 `−11.9pp`，病例配对 95% CI
均为 `[-31.0,0]`；没有病例得到净改善。退化只集中在两个结构性病例但跨运行稳定：

- `mb66`：3/3 从决定性 AAS 暴露退回泛化 RUQ tenderness，@1/@2 均从 100%→0；
- `mxh075`：复合 decisive 的 2/3 命中消失，3/3 首位固定为更泛化的胸片表现，
  原型锚定代理升高。

20 列左右的全候选 effect matrix 还使 25/51 响应需要 schema repair，虽无最终
invalid，但远高于当前 L1-target arm。机制不是“模型没看到具体病名”，而是把所有
生成叶同时当互斥区分目标后，候选过多、叶集合与 P5 decision set 不同，显著共性事实
反而能在更多叶之间制造表面分差。

裁决：不把 flat direct-L2 纳入默认 BFS。保留当前混合边界——L1 是稳定更新/选择轴，
L2 具体病名提供比较语境。若以后重试 direct-L2，前置条件是 label-blind 构造稳定的
4–5 个局部 L2 decision set、完成名称归一与覆盖审计，再把 L2 effects 明确聚合回 L1；
不能直接平铺全部 15–22 个叶。

产物：

- `logs/l1_direct_l2_selection_isolated_v1/summary.json`
- `scripts/eval_l1_direct_l2_selection.py`

### 10.10 生产自动 finding 的理解与二次筛选矩阵（2026-07-15）

此前 §10.7–10.9 的 selector catalog 并非纯生产输入：
`eval_l1_evidence_bfs._facts_for_case()` 先读取 VignetteParser 冻结的
`static_evidence_items`，再追加人工 annotation 中 `in_vignette=true` 的抽象 finding。
因此旧的 `54.8%/76.2%` 回答的是混合目录上的 observed-decisive 命中，不能解释生产端
只有机器 finding 时的能力。

本轮从 17 个 frozen shared-tree 直接冻结 264 条 `static_evidence_items`（每例均值
15.53），不追加任何 annotation finding，也不注入 annotation-derived compiler rules。
另用候选无关、gold-blind、ID-only filter 对完整列表做 3 次 `temperature=0` 筛选，
按多数出现和平均排名冻结 100 条重要 finding（每例均值 5.88，压缩 59.3%）。
人工金标在 filter 输出隐藏的 full-catalog 视图上建立，只在返回后评分。

严格独立复核进一步暴露了树与 gold 问题：17 例中仅 **7 例**可评分。`mb34`、
`mb55`、`mb57`、`mxh011`、`mxh055` 存在跨 L1 重复/近重复 gold 叶；`mb65`、
`mb77`、`mxh045` 缺少可唯一支持目标 L1 的观察；`mb66`、`mxh075` 的动态 gold
映射与冻结 L2 所在父分支冲突。这 10 例均标为 `unscorable`，不得借用缺失的 PTH、
BCR-ABL、显式 AAS 暴露或旋转异常影像补标，也不静默按失败计入。

7 个可评分病例 × 3 次 selector 重复的主矩阵如下。BEST 要求命中人工裁定的最佳
单条或完整两事实组合；VALID 允许其他有实质跨 L1 区分力的事实。

| 病例理解上下文 | eligible menu | BEST@1 | BEST@2 | VALID@1 | VALID@2 |
|---|---|---:|---:|---:|---:|
| 完整自动列表 | 完整自动列表 | 52.4% | **57.1%** | 66.7% | 76.2% |
| 完整自动列表 | 二次筛选子集 | 42.9% | **57.1%** | 57.1% | 71.4% |
| 二次筛选子集 | 完整自动列表 | **57.1%** | **57.1%** | 66.7% | 71.4% |
| 二次筛选子集 | 二次筛选子集 | 42.9% | **57.1%** | 42.9% | 71.4% |

两个保留原始题干的生产对照为：

| 生产上下文 | eligible menu | BEST@1 | BEST@2 | VALID@1 | VALID@2 |
|---|---|---:|---:|---:|---:|
| 原始题干 | 完整自动列表 | 47.6% | **76.2%** | 61.9% | 81.0% |
| 原始题干 | 二次筛选子集 | **57.1%** | 57.1% | 71.4% | 85.7% |

绝对 CI 很宽：完整列表 list-only 的 BEST@1/@2 case-cluster 95% CI 为
`[14.3,85.7]`/`[14.3,85.7]`；生产对照为 `[14.3,85.7]`/`[47.6,95.2]`。
完整列表改成筛选 menu 后，list-only BEST@1/@2 分别变化
`−9.5pp [-28.6,0]`、`0pp [0,0]`；生产对照为
`+9.5pp [0,+28.6]`、`−19.0pp [-52.4,+9.5]`。由于严格分母仅 7 例，不能宣称
统计解决；@1 的表面上升也不能抵消 filter 对 BEST@2 上界的删除。

二次 filter 本身高度稳定（三次集合 pairwise Jaccard 89.8%，consensus 对单次
94.9%），却只保留 4/7 例最佳证据，BEST retention 与 valid recall 均为
**57.1%**，严格可评分病例上的 selected precision 仅 24.8%。在生产题干上下文中，
保留下来的 4 例均被 selector 命中，`BEST@1/@2 | retained=100%`；绝对 BEST@2
仍只有 57.1%，损失来自 filter omission。被删掉的关键线索是 `mb82` 的手术瘢痕、
`mxh036` 的短时禁食不耐受、`mxh068` 的消旋肾上腺素无效——均属低显著但高鉴别项。

#### 10.10.1 严格金标为何只剩 7 例

这不是简单的数据缺失，而是三类不同的可识别性问题：

1. **跨 L1 重复叶（5 例）**：`mb34` 的反应性白细胞增多同时落入 B4/OTHER；
   `mb55` 的 glucagonoma 同时落入代谢/内分泌、肿瘤和 alpha-cell 语义分支；
   `mb57` 的 PCD/Kartagener 在 B1/B4/B5 重复；`mxh011` 的 epiglottitis 同时位于
   upper-respiratory 与 airway-compromise；`mxh055` 的 exertional heat stroke
   同时位于 B4/B5。模型即使识别出正确疾病，也没有患者证据能决定唯一父 L1。
2. **决定性观察缺失（3 例）**：`mb65` 缺 BCR-ABL、嗜碱细胞增多或成熟髓系全谱，
   且 35% blasts 反而支持 B1；`mb77` 缺 PTH，单凭高钙低磷不能严格排除 PTHrP；
   `mxh045` 只有一般梗阻表现，没有旋转异常影像。
3. **gold-to-tree 冲突（2 例）**：`mb66` 的动态 gold 指向 B3，但 Peliosis Hepatis
   冻结叶位于 B5；`mxh075` 的动态 gold 指向 B2 Septal Defects，而 Truncus
   Arteriosus 明确位于 B4。

因此本节 7 例是“**在当前冻结树上可由已观察事实唯一辨识 L1**”的严格子集，不是对
17 例总体性能的无偏估计。修树前扩大分母会把 taxonomy/gold 错误伪装成 selector 错误；
反过来排除 10 例也会产生选择后偏差，所以这里只能作为能力诊断，不作为生产准确率头条。

#### 10.10.2 原始叙事具体补回了什么

完整自动列表单独作为上下文时，BEST@2 为 12/21=57.1%；原始题干 + 完整 menu
为 16/21=76.2%。净增 4 个 replicate-case 命中来自两类病例：

- `mb82`：list-only 3/3 固定选择“鼓音性腹胀 + 下肢弱脉”，漏掉 F16 右下腹手术
  瘢痕；原始叙事使 F16 在 2/3 进入 Top-2，把一般梗阻表型连接回粘连病因。
- `mxh068`：list-only 3/3 围绕 stridor、低氧或高热排序，漏掉 F16
  “racemic epinephrine 无改善”；原始叙事 3/3 把该治疗反应反事实送入 Top-2。

代价是 `mb11` 有 1 次从“快速消瘦”漂移到“感觉减退 + 烧灼痛”，使其生产对照
BEST@2 从 list-only 的 3/3 变为 2/3。说明原始叙事不是普遍增益，而是能恢复事实之间
的**病因、时间与干预关系**；同时也会重新放大显著但共享的症状。仅将自动事实平铺成
列表，会损失这些关系结构。

#### 10.10.3 三类 selector 行为

- **跨表示稳定成功**：`mb83` 的单侧脓血性鼻分泌物、`mxh014` 的新发杂音、
  `mxh046` 的双侧向下晶状体脱位，在六臂均为 3/3 BEST 命中。这些 finding 自带
  高特异语义，不依赖长程上下文。
- **上下文可救回**：`mb82` 的既往手术线索、`mxh068` 的治疗无反应，必须结合原始
  叙事才能压过更显著的当前症状。
- **持续原型锚定**：`mxh036` 六臂均 3/3 选择“乳糜血 + 巨大肝脏”，而非 F2
  短时禁食不耐受或 F9 无脾大。乳糜血和肝大看似符合 GSD-I 原型，但也被 B1
  lipid-storage 解释；模型没有把跨候选反事实优先于疾病画像相似度。

这解释了 VALID 与 BEST 的差异：模型经常选择临床相关 finding，却没有选择能改变
L1 相对顺序的最佳 finding。VALID 高不能替代 BEST，也不能证明消除了原型锚定。

#### 10.10.4 为什么 hard filter 的 @1 上升仍是失败

生产题干 + filtered menu 的 BEST@1 从 47.6% 升到 57.1%，但 BEST@2 从 76.2%
降到 57.1%。这是典型的**条件选择效应**：

- filter 只保留 4/7 例最佳证据；这 4 例在下游均 3/3 命中且位于 @1；
- `mb82`、`mxh036`、`mxh068` 的最佳证据在三次 filter 中全部缺席，@1/@2 均被
  结构性封顶为失败；
- 因而 @1 上升只表示被保留的容易病例菜单更干净，不表示总体理解能力增强。

三个 omission 分别对应候选无关 salience filter 的盲点：

1. **远端病因史**：手术瘢痕被 cruise 接触史、脂餐诱发、高血压和杂音挤掉；
2. **时间/诱发关系**：禁食 3–4 小时即不适被生长受限、肝大和乳糜血挤掉；
3. **干预反事实**：肾上腺素无效被脓痰、COVID 阴性、低氧和 stridor 挤掉。

filter 的集合 Jaccard 高说明错误是**稳定遗漏**，不是随机波动。“重要性”与
“当前候选间鉴别力”不是同一目标；候选无关 filter 不应拥有删除权限。

#### 10.10.5 协议、统计与下一步门槛

- schema repair 率依次为：完整列表上下文/完整 menu 11.8%，筛选上下文/完整 menu
  11.8%，完整列表上下文/筛选 menu 0%，筛选上下文/筛选 menu 13.7%，生产题干/
  完整 menu 19.6%，生产题干/筛选 menu 27.5%。两个最终 invalid 均发生在
  unscorable 病例，不改变严格 BEST 分子分母，但显示长题干和小 menu 并不自动降低
  协议压力。
- 统计单位仍是 7 个 case cluster，而非 21 个重复观测；CI 极宽，所有关键 delta
  均 unresolved。三次 `temperature=0` 只刻画远端非确定性，不能扩大有效样本量。
- 生产修复顺序应先于新 prompt：先消除跨 L1 重复叶，再用 L2 ancestry 而非仅 L1
  label judge 映射 gold，补齐 gold-to-tree 冲突后重建 17 例严格金标。
- 若继续研究 pool compression，最低要求是：完整列表始终保持 selectable；filter
  仅提供 soft salience；额外强制保留 causal-history、temporal-provocation、
  treatment-response/negative-response 三类 finding。只有 strict BEST retention
  的病例级 CI 下界达到预设门槛后，才允许测试 hard gate。

裁决：

1. **能力 1（理解病例并拣选证据）**：纯机器列表单独作为上下文时 BEST@1/@2
   为 52.4%/57.1%；保留原始题干并以完整列表为 menu 时为 47.6%/76.2%。
   原始叙事对组合证据进入 Top-2 仍然重要。
2. **能力 2（候选无关的重要 finding 自动筛选）**稳定但召回不足，不能作为 hard
   eligible gate。它作为额外 attention context 且保留完整 menu 时，BEST@2 不变；
   因此最多作为软提示，不能删除原始候选。
3. 默认 BFS 应改为纯 `static_evidence_items` 的完整候选白名单；若接二次筛选，
   只把其结果作为 salience context，完整自动 finding 仍保持可选。
4. 旧混合目录 `54.8%/76.2%` 与本节 BEST 指标的事实池、金标和分母均不同，不作
   直接数值回归判断。

产物：

- `eval_fixtures/l1_auto_finding_selection_v1.json`
- `logs/l1_auto_finding_filter_v1/`
- `logs/l1_auto_finding_matrix_v1/summary.json`
- `scripts/freeze_l1_auto_finding_sets.py`
- `scripts/annotate_l1_auto_finding_gold.py`
- `scripts/eval_l1_auto_finding_matrix.py`

### 10.11 冻结 L1 后的 L2 竞争顺序实测

本轮不是用 L2 结果反调 L1，而是先把上游完全冻结。输入固定为原始题干加
`static_evidence_items` 完整列表，不注入人工 annotation finding，不做 hard filter，
selector 固定为 `p5_anti_anchor_direct`。17 例各跑 3 次、上限 F30；随后只依据 14 个
gold-L2-present 病例的 acceptable-parent set 选择统一前缀：先最大化 L1 Top-1，再最大化
parent-set MRR，同值取最小 F。曲线在 F2/F6 的 Top-1 均为 45.2%，F6 的 MRR 更高
（67.2% 对 65.1%），所以冻结 **N*=F6**；F22 不再是本轮新事实池和新 selector 下的
最优点。

这里发现一个重要协议事实：anti-anchor 是允许 abstain 的 selector。51 条完整轨迹中，
只有 5 条以 literal `pool_exhausted` 结束，46 条以 `selector_abstained` 结束；后者表示
selector 认为剩余事实没有足够跨 L1 对比度，而不是把所有 ID 强制消费。评测没有用
oracle/forced fallback 伪造“耗尽”。因此 F6 是**当前 abstaining 生产语义下的饱和前缀**，
不能解释为每例都实际消费了 6 条；`mb66` 有 2 个重复在 F0 即安全 abstain，这两条在
所有 L2 臂中统一记为上游无证据失败。

L2 金标重新按冻结树人工裁定，允许同一疾病跨 L1 重复叶任一命中：

- 14/17 例有显式 L2；3 例为 `absent`，在 17 例生产分母中按未命中；
- `mb34`、`mb55`、`mb57`、`mxh011`、`mxh055` 为 `duplicated_across_l1`；
- 其余 9 个 gold-present 病例为唯一路径；疾病级命中和唯一路径命中分开报告；
- payload 不含 gold，所有臂消费同一冻结 L1 posterior 和该轨迹最先选择的 Top-2
  evidence。

五臂 17 例 × 3 次结果如下。括号内为 14 个 gold-present 病例的指标：

| L2 组织方式 | 17例 Top-1 / Top-2 | present Top-1 / Top-2 | present MRR | parent/冠军 reach | 稳定性 | 估计调用/例 |
|---|---:|---:|---:|---:|---:|---:|
| S0 全 L2 | 25.5% / 31.4% | 31.0% / 38.1% | 47.7% | 100% | 90.2% | 0.96 |
| S1 Top-1 parent | 29.4% / 35.3% | 35.7% / 42.9% | 39.9% | 45.2% | 86.3% | 0.96 |
| S2 Top-2 parents | 23.5% / 31.4% | 28.6% / 38.1% | 43.9% | 76.2% | 86.3% | 0.96 |
| S3A 各父冠军 + L1 prior | **33.3% / 43.1%** | **40.5% / 52.4%** | **52.1%** | 78.6% | 74.5% | 5.65 |
| S3B 各父冠军 + uniform | 29.4% / 39.2% | 35.7% / 47.6% | 49.2% | 78.6% | 68.6% | 5.65 |

S1 的问题不是父内判断，而是结构上限：42 个 gold-present 观测中 21 个 gold parent
不在 L1 Top-1。S2 把 reach 提到 76.2%，但 Top-1 比 S0 低 2.0pp，且 37.3% 的响应
需要 schema repair；缩小到两个父分支没有产生净诊断收益。S3A 的 Top-1 比 S0/S2
高 7.8/9.8pp，主要救回 `mb11`，并部分救回 `mb77`、`mb83` 和 `mxh036`；但局部
冠军阶段仍淘汰 9/42 个 gold-present 观测，集中于 `mb55`、`mxh046`、`mxh075`。

病例簇 bootstrap 不支持把点估计写成确定提升：S3A 相对 S0/S2 的 17 例 Top-1
差为 `+7.8pp [-7.8,+25.5]` / `+9.8pp [-3.9,+25.5]`；S3B 分别为
`+3.9pp [-15.7,+25.5]` / `+5.9pp [-13.7,+25.5]`。S3B−S3A 的 Top-1 为
`−3.9pp [-13.7,+3.9]`，MRR 为 `−2.4pp [-8.4,+2.2]`。两种冠军法没有统计分离，
但 S3A 在 Top-1、MRR 和重复稳定性上均为更好的点估计，并保留软 L1 prior；因此
**3A 是唯一优先候选，3B 不晋级**。

生产裁决遵守预注册门槛：本轮不直接替换 controller。S1 因召回上限淘汰；S2 可作为
低成本层级基线，但没有优于 S0；S3A 是效果最好的研究候选，却约需 5.9 倍调用且 CI
跨 0。下一步应先修重复叶/局部冠军召回并扩大独立病例集；只有 S3A 相对低成本基线的
病例簇 CI 下界不再跨 0，且局部冠军 recall 与稳定性达到门槛，才可晋级正式路径。

产物：

- `eval_fixtures/l2_competition_gold_v1.json`
- `logs/l2_competition_strategies_v1/l1_full/`
- `logs/l2_competition_strategies_v1/l1_frozen/manifest.json`
- `logs/l2_competition_strategies_v1/l2_eval/summary.json`
- `scripts/annotate_l2_competition_gold.py`
- `scripts/eval_l2_competition_strategies.py`

### 10.12 L1 排序代理下的 L2 组内/组间边际曲线（已由 §10.14 校正）

§10.11 的 L2 标注和冠军仲裁都只消费 L1 轨迹最先选择的 F2。为避免把两个预算同时
增加后无法归因，本轮严格拆成两个非联合实验：

> **解释限制：**本节的事实顺序由 L1 候选间对比产生，并不是针对当前 L2 候选动态
> 搜索。它只能回答“复用 L1 顺序时增加输入是否有益”，不能据此裁决 L2 自身的最佳
> evidence budget。后者已在 §10.14 用候选条件化动态 selector 重测。

1. **组内边际**：只改变 gold 所在 L1 父分支内部的证据前缀
   `F2,F4,...,F30,EXH`，不执行组间仲裁。跨 L1 重复 gold 对每个 acceptable parent
   分别评测，病例级任一等价父分支命中即成功。gold 只用于离线选择评测 scope 和评分，
   不进入 LLM payload，因此这是能力上界诊断，不是可直接部署的 oracle 路径。
2. **组间边际**：局部冠军严格冻结为 §10.11 的 F2 S3A 冠军，不允许随预算变化；
   仅增加 prior-aware 组间 arbiter 可见的 evidence 前缀。这样变化只来自组间证据量。

两条曲线都读取同一批完整 L1 selection order；`EXH` 使用每条轨迹的全部已选择事实，
而不是把不足 F30 的病例补入任意事实。42 个 gold-present 观测在 EXH 平均使用
10.40 条证据，F28 达到 100% 轨迹耗竭。

组内 gold-parent 结果：

| 证据预算 | Top-1 | Top-2 | MRR | 平均实际事实数 |
|---|---:|---:|---:|---:|
| F2 | **73.8%** | 83.3% | **82.5%** | 1.90 |
| F4 | **73.8%** | 83.3% | 82.1% | 3.67 |
| F6 | 71.4% | 83.3% | 81.2% | 5.43 |
| F10 | 71.4% | **85.7%** | 81.7% | 8.24 |
| EXH | 71.4% | 83.3% | 81.3% | 10.40 |

按 Top-1→MRR→最小预算的预注册次序，最早峰值是 **F2**。EXH−F2：
Top-1 `−2.4pp [-7.1,0]`，Top-2 `0pp [0,0]`，MRR `−1.2pp [-3.6,0]`。
没有任何病例从 F2 失败转为 EXH 成功；唯一 Top-1 损失是 `mb66` replicate 2。
F10 的 Top-2 暂时高 2.4pp，但同时 Top-1 低 2.4pp，且到耗竭即消失，不能定义为
稳定增益。

组间结果（固定 F2 局部冠军，14 个 gold-present 病例）：

| arbiter 证据预算 | Top-1 | Top-2 | MRR |
|---|---:|---:|---:|
| F2 | **40.5%** | **52.4%** | **52.1%** |
| F4/F6/F8 | 38.1% | **52.4%** | 51.0% |
| F10 | 35.7% | 50.0% | 48.6% |
| F12 | 38.1% | **52.4%** | 51.0% |
| EXH | 35.7% | 50.0% | 48.6% |

EXH−F2 的 present-case Top-1 为 `−4.8pp [-11.9,0]`，Top-2
`−2.4pp [-7.1,0]`，MRR `−3.6pp [-9.5,0]`；17 例生产分母上的 Top-1 为
`−3.9pp [-9.8,0]`。没有 EXH 净救回，反而使 `mb11` replicate 3 和 `mb83`
replicate 2 丢失 Top-1；前者还跌出 Top-2。

结论不是“证据池不需要生成”，而是**L2 decision prompt 不应无条件接收全部已选择
事实**。后续低区分度/共享事实会稀释局部候选差异，并在组间重新放大疾病原型和
父分支先验冲突。本节原始裁决已由 §10.14 部分撤销：

- 组内“F2 为默认”不再成立；它混入了 L1 排序错配，动态组内最优点改为 F4；
- 组间仍不应无条件耗竭，但动态重排后 F2 与 F4/EXH 的 Top-1 相同，不能再称
  F2 明确优于耗竭；
- 完整 selection pool 仍保存用于审计和其他阶段，但 L2 需要 evidence gating 或
  压缩摘要，不能把“可用”直接等同于“全部塞入同一次判别”。

产物：`logs/l2_competition_strategies_v1/l2_budget_marginals/summary.json`；
子命令：`scripts/eval_l2_competition_strategies.py
evaluate-l2-budget-marginals`。

### 10.13 Knowledge-grounded 双智能体反锚定：当前冻结知识不足，不晋级

本轮只做 selection-only 孤立实验，没有修改 controller、allocator 或生产 preset。
普通 contrastive proposer（G1）与独立 anti-anchor proposer（G2）共享同一只读目录、相同
catalog hash 和每次最多 12 个 excerpt 的请求上限；两者都必须提交
`observed fact → exact quote → candidate effect → strongest-rival contrast`。G3 只能在
G1/G2 已提出的 fact 中重排，随后再由 fail-closed entailment verifier 检查每一条
support/rival link。任一 citation audit 非 `entailed`，即使 fact 总 verdict 写成
`entailed`，也必须整体拒绝。

冻结资产来自未改写的 P5 `disc_audit`，共 620 条 fact-excerpt 连接、396 个唯一原始
chunk；396/396 均成功水合，catalog hash 为
`7e151de9dc813d8b2285ba5355f3b9e71aa2e159d525fd4f8e4699e55f2fbb11`。但是这不等于
选择菜单有充分知识覆盖：

- 原始 17 例混合目录只有 43/329 个 fact 能直接连接 P5 chunk（冻结资产 13.1%）；
  运行时按文本映射后为 50/329=15.2%，虽有 13/17 例至少存在一个 chunk；
- 7 个严格 auto-finding 病例只有 10/97=10.3% 的 eligible fact 能映射 chunk，
  仅 4/7 例至少有一个；
- 两条事实级覆盖率都低于预注册 30% 门槛，所以最终结论必须写成“当前冻结知识不足”，
  不能把失败归因成双智能体机制本身无效。

17 例 × 3 次的主结果：

- A0 纯提示词 anti-anchor 在有 observed decisive 的 14 个病例簇上
  SELECT@1/@2 为 **52.4%/76.2%**；
- G1 为 **0%/0%**，51/51 abstain；
- G2 为 **0%/0%**，50/51 abstain；
- G3 经 exact quote、branch alignment、arbiter 与全链 entailment gate 后为
  **0%/0%**，51/51 abstain；
- G3−A0 的 decisive SELECT@1 为
  **−52.4pp `[-78.6,-26.2]`**，SELECT@2 为
  **−76.2pp `[-95.2,-54.8]`**，明显未通过主终点。

严格 BEST sensitivity 同样没有支持晋级。7 例 × 3 次中，A0 的
BEST@1/@2 为 **47.6%/81.0%**、VALID@1/@2 为 **61.9%/81.0%**；G1/G2/G3
四项均为 0。G3−A0 的 BEST@2 为
**−81.0pp `[-100,-52.4]`**。这些数值首先反映 hard grounding 在低覆盖资产上的
结构性 abstain，不是新的生产能力估计。

证据链审计解释了“有 chunk 仍不能用”的原因：

- G1 尝试 9 条 chain、20 个 citation，只有 5 个通过 exact-ID/quote/branch 校验，
  没有完整双边 chain；
- G2 尝试 34 条 chain、70 个 citation，只有 9 个机械引用有效，仅 1 条形成机械完整
  chain；
- G3 对这 1 条 chain 的 2/2 引用均能在原文中找到，但 semantic verifier 最终拒绝，
  因此“精确引用存在”不等于“引用支持主张”；
- `mxh036` 把“absence of functional lipoprotein lipase activity”当成“absence of
  splenomegaly”的支持，并把只描述 hyperinsulinism 的段落当作 GSD 反证；verifier
  将两条 citation 都判为 `not_entailed`，确定性 all-links validator 因此 fail closed。

其他高频失败是：照抄 prompt 示例构造不存在的 access ID、把一个 chunk 的句子归到
另一个 ID、把单病 association 当 pairwise contrast、把未提及当反证、chunk 对应的
leaf 不属于声称的 L1 branch，以及遗漏完整 candidate-effect matrix。它们证明
`citation_integrity` 必须拆成“ID/quote 完整性”和“claim entailment”，不能只验字符串。

调用成本也不支持当前方案：混合目录 A0 平均 1.27 calls/record；G1 2.27、G2 2.35，
完整 G3 pipeline 4.67（约 A0 的 3.66 倍）。严格 auto track 的 G3 为 3.33 calls/record
（约 A0 的 3.18 倍）。

复核时还修正了 `RobustLLMClient.call_module()` 的隐藏硬编码：JSON module 原先强制
`min_length=20`，会把合法的 `{"verdict":"none"}` 当作短响应重复调用。现改为遵循
client 的 `min_response_length`（默认 10），并以 `short-json-fix-v1` 全新缓存同步
重跑 A0/G1/G2/G3；上述数字均来自修复后 run，不复用受影响的旧响应。

裁决：**不接入生产 BFS，继续保留纯提示词 `p5_anti_anchor_direct`。** 下一轮必须先
把 P5 的单病叶级检索资产改造成 BFS 专用、带 finding value/polarity、L2→L1 ancestry
和 strongest-rival comparative claim 的冻结目录；事实级覆盖至少超过 30% 才重跑，
目标应更接近完整 eligible menu。未经该知识层重建，增加 proposer/arbiter 只能把
低覆盖转化为高成本 abstain。

产物：

- `src/agentclinic_tree_dx/grounded_evidence.py`
- `eval_fixtures/l1_grounded_chunk_catalog_v1.json`
- `scripts/freeze_l1_grounded_chunk_catalog.py`
- `scripts/eval_l1_grounded_anti_anchor.py`
- `logs/l1_grounded_anti_anchor_v1/manifest.json`
- `logs/l1_grounded_anti_anchor_v1/records.json`
- `logs/l1_grounded_anti_anchor_v1/grounding_audit.json`
- `logs/l1_grounded_anti_anchor_v1/summary.json`

#### 10.13.1 降门槛复测：检索生成推理链替代完整知识蕴含

按后续要求增加 `retrieval_chain` 策略并设为该孤立脚本默认值。G1/G2 不再直接输出
“选择 + 简短理由”，而必须提交
`observed fact → exact retrieved quote → inferred candidate effect → strongest-rival comparison → ranking`
推理链。它仍强制 access ID 来自本次只读服务、quote 是对应 chunk 原文子串、fact 属于
eligible menu、effect matrix 覆盖全部当前候选；但有意取消三项 hard gate：

- 不要求来源自身完整陈述 support 与 strongest-rival 两侧；
- 不要求来源的 leaf candidate 与推断的 L1 branch 严格对齐；
- G3 后不再调用独立 semantic entailment verifier。

因此该模式证明的是“模型能否根据检索结果形成可追踪的比较推理”，不是“每一步都由可靠
知识源蕴含”。旧 `strict_entailment` 仍可通过 CLI 显式选择，以保留审计对照；生产
controller 和 `p5_anti_anchor_direct` 未改。

新缓存 `retrieval-chain-v1` 的 17 例 × 3 次结果如下。同轮 A0 在 14 个
observed-decisive 病例簇上的 SELECT@1/@2 为 **52.4%/78.6%**；G1 为
**31.0%/33.3%**，G2 为 **14.3%/16.7%**，G3 为 **31.0%/33.3%**。G3 相对 A0
分别为 **−21.4pp `[-45.2,+2.4]`** 与 **−45.2pp `[-69.0,-21.4]`**。在全部
mixed 记录上，G3 SELECT@1/@2 为 **25.5%/27.5%**，abstain **25.5%**；不再是
strict 模式的 51/51 abstain，但 @2 的显著损失仍已解决。

偏差只是换了形态，而非消失：G3 的 `prototype_anchor_at_1` 从 A0 的 **15.7%**
降至 **0%**，但 `shared_or_trap_at_1` 升至 **37.3%**。低覆盖目录使模型从“疾病
原型锚定”转为“哪些事实恰好有 chunk 就锚定哪些事实”。事实级 chunk coverage 仍只有
mixed **15.2%**、auto **10.3%**。

7 例严格 auto sensitivity 中，A0 BEST@1/@2 为 **47.6%/81.0%**、VALID@1/@2 为
**61.9%/81.0%**；G3 分别只有 **23.8%/23.8%** 与 **28.6%/28.6%**，abstain
**42.9%**。G3 最终接受链的结构与 exact-ID/quote 完整性均为 100%；若把 repair 前已被
拒绝的错误引用也计入，原始尝试完整性为 auto **94.4%**、mixed **92.7%**。这些数字不代表
semantic entailment，正是本策略主动降低的保证。

成本仍高：mixed G3 pipeline 平均 4.98 calls/record，为同轮 A0 的 **3.97 倍**；
auto 为 **3.48 倍**。故裁决仍是 **不晋级生产 BFS**。放宽 gate 可验证“生成检索推理
链”这一交互形式，却不能修复检索目录只覆盖约一成 eligible fact 所造成的候选菜单偏置。

新增产物：

- `logs/l1_grounded_anti_anchor_retrieval_chain_v1/manifest.json`
- `logs/l1_grounded_anti_anchor_retrieval_chain_v1/records.json`
- `logs/l1_grounded_anti_anchor_retrieval_chain_v1/grounding_audit.json`
- `logs/l1_grounded_anti_anchor_retrieval_chain_v1/summary.json`

### 10.14 候选条件化动态 L2 选证边际：组内 F4，组间 F2（已由 §10.15 联合校验否决）

> 本节只测两个隔离边际。§10.15 重新生成所有父分支的动态 F4 冠军并联合动态 F2
> 仲裁后，最终 Top-2 显著低于真实消费顺序 F2 对照；因此本节末尾的候选配置不得直接
> 解释为生产配置。

§10.12 复用了 L1 候选间对比产生的事实顺序，目标与 L2 竞争不一致。本轮新增独立
L2 selector：每个 micro-cycle 都从完整生产 `static_evidence_items` 白名单重新选择
最多 2 条事实，要求对**当前具体 L2 候选集**提交完整 `[-2,+2]` effect matrix，
最大与最小 effect 差至少为 2，并携带已消费概念历史避免语义重复。没有复用 L1
selection order，也没有把 gold 放入 payload。

两个变量仍严格分离：

1. **动态组内**：只在 hidden-gold parent 内暴露其 L2 leaves，动态选证后做局部排序；
   gold 仅决定离线评测 scope。生产冠军法应对每个 L1 parent 都运行同一 selector，
   而不是在运行时知道 gold parent。
2. **动态组间**：冻结 §10.11 的 F2 局部冠军，只针对这些冠军动态选证；不改变冠军
   身份，因此没有把组内和组间改动联合。

17 例 × 3 次、14 个 gold-present 病例的动态组内结果（42 个观测）：

| L2 动态预算 | Top-1 | Top-2 | MRR | 平均事实数 | schema valid |
|---|---:|---:|---:|---:|---:|
| F2 | 85.7% | 100% | 92.9% | 2.00 | 100% |
| **F4** | **92.9%** | **100%** | **96.4%** | 3.88 | 100% |
| F6 | 90.5% | 100% | 95.2% | 5.45 | 100% |
| F10 | 83.3% | 100% | 91.7% | 6.98 | 100% |
| EXH | 81.0% | 95.2% | 88.1% | 7.31 | 95.2% |

F4−F2 的 Top-1 为 `+7.1pp [0,+21.4]`，MRR 为
`+3.6pp [0,+10.7]`，Top-2 不变；3 个净 Top-1 救回都来自 `mb66_peliosis`
三个重复，没有损失。相对同预算 L1 顺序，动态 F4 的 Top-1/Top-2/MRR 分别提高
`+19.0pp [0,+40.5]`、`+16.7pp [0,+35.7]`、`+14.3pp [0,+29.4]`。这确认
§10.12 的低分主要是**排序目标错配**，不是 L2 无法利用更多证据。

增加到耗竭仍有害：EXH−F2 的 Top-1/Top-2/MRR 均下降 4.8pp，CI 分别为
`[-14.3,0]`、`[-14.3,0]`、`[-11.9,0]`。动态 selector 平均在组内选择 6.57 条；
多数轨迹通过 abstain 饱和，后段另有 schema failure/cycle guard。因此 EXH 是
“消费该 selector 产生的全部顺序”，不是强制吞掉原始 catalog 每个 ID。

动态组间、固定 F2 冠军的结果：

| arbiter 动态预算 | Top-1 | Top-2 | MRR |
|---|---:|---:|---:|
| **F2** | **38.1%** | 52.4% | 51.0% |
| F4 | **38.1%** | **54.8%** | **51.3%** |
| F6/F8 | **38.1%** | 52.4% | 50.8% |
| EXH | **38.1%** | **54.8%** | **51.3%** |

F4 只在 `mb77_hyperpara` 一个重复中把 gold 从第 3 提到第 2，Top-1 完全不变。
F4−F2 的 Top-2 为 `+2.4pp [0,+7.1]`，MRR 为 `+0.4pp [0,+1.2]`。按
Top-1→MRR→最小预算顺序，组间仍选 **F2**；F4 只保留为 Top-2 研究臂。

修正后的阶段裁决：**局部 L2 竞争使用候选条件化动态 F4；跨父冠军仲裁使用候选
条件化动态 F2；两个阶段都不使用 L1 证据顺序，也不推进到动态池耗竭。** 这仍是
两个独立边际的配置候选，尚未把“动态组内 F4 产生的新冠军 + 动态组间 F2”联合成
端到端 S3A 重跑，故局部 92.9% 不能写成最终 L2 生产准确率。

产物：

- `src/agentclinic_tree_dx/prompts/l2_dynamic_evidence_selector.txt`
- `scripts/eval_l2_dynamic_evidence_marginals.py`
- `tests/test_l2_dynamic_evidence_marginals.py`
- `logs/l2_competition_strategies_v1/l2_dynamic_marginals/summary.json`

### 10.15 真实顺序修复后的 L2 联合测验：动态 F4+F2 不晋级

#### 10.15.1 先修复前缀语义

旧 trace 的 `selected_fact_ids` 来自 `fact_catalog_core` 上的 consumed 集合投影，不是
BFS 实际消费顺序；真正顺序在 `rounds[].fact_id`。51 个病例-重复中有 **49 个** F2
前缀不一致，导致旧冻结 F2 冠军不是“L1 前两次选择产生的冠军”。本轮：

1. 从 `rounds[].fact_id` 重建真实顺序，并要求其集合与 consumed 集合相等；
2. 用真实 F2 重新生成每个父分支的局部冠军；
3. 修改 runtime：后续 trace 的 `selected_fact_ids` 与新增
   `consumption_order_fact_ids` 都写实际消费顺序，另保留
   `consumed_fact_ids_catalog_order` 供旧审计使用；
4. 动态 selector 只看净化后的 L2 `id/label/parent`，不看 parent posterior、
   local score 或旧 rationale。

修复影响不是单例噪声：**33/51** 个单元的旧冠军集合与真实 F2 冠军集合不同。相同新
arbiter prompt 下，A0 污染资产到 A1 真实顺序重建的 gold-present Top-1
31.0%→26.2%，但 Top-2 从 **52.4% 升至 73.8%**，组合增量
`+21.4pp [95% CI +4.8,+40.5]`；结构可达率从 73.8% 升至 92.9%，局部淘汰从
9/42 降至 3/42。这里同时改变事实前缀和据此重标注的冠军，故只能归因于
**catalog 前缀修复+冠军重建的组合处理**，不能写成纯 order effect。

#### 10.15.2 联合协议与结果

17 例 × 3 次，gold-present 为 14 例 × 3 = 42 个单元。先为**每个** L1 parent 独立
动态选最多 F4 并生成冠军，再在这些新冠军之间动态选 F2 仲裁。九臂共享模型、温度、
病例、自动 findings、树、gold 与新 arbiter prompt：

| 臂 | 局部冠军 | 组间证据 | 仲裁信息 | Top-1 | Top-2 | MRR |
|---|---|---|---|---:|---:|---:|
| A0 | 旧 catalog-F2 | catalog-F2 | prior+audit+full | 31.0% | 52.4% | 47.1% |
| **A1** | **真实顺序 F2** | **真实顺序 F2** | prior+audit+full | 26.2% | **73.8%** | 53.7% |
| A2 | 动态 F4 | 真实顺序 F2 | prior+audit+full | **33.3%** | 59.5% | 53.7% |
| A3 联合主臂 | 动态 F4 | 动态 F2 | prior+audit+full | **33.3%** | 59.5% | 55.2% |
| A4 | 动态 F4 | 动态 F2 | no-prior | 31.0% | 57.1% | 53.2% |
| A5 | 动态 F4 | 动态 F2 | no-audit | 26.2% | 64.3% | 52.4% |
| A6 | 动态 F4 | 动态 F2 | selected-only | 26.2% | 61.9% | 52.4% |
| A7 | 动态 F4 | 动态 F2 | full+effect handoff | **33.3%** | 61.9% | 55.5% |
| A8 | 动态 F4 | 动态 F2 | clean selected-only+effects | **33.3%** | 66.7% | **56.2%** |

A1→A2 改变局部 F4 产生的冠军与 local audit：Top-1 `+7.1pp`
`[−2.4,+16.7]`，但 Top-2 **下降 14.3pp**
`[−28.6,−2.4]`。六个 Top-2 损失（`mb34_leukemoid` r2/r3、
`mb55_glucagonoma` r3、`mxh045` r1、`mxh055` r1/r2）没有任何 Top-2 gain；结构上
另丢失 `mxh075` r3。隔离 gold-parent 中 F4 的 92.9% 不能外推到“每个 parent 先产
冠军再跨组仲裁”：局部 Top-1 最优并不保证生成的**非 gold 父分支冠军集合及 audit**
适合最终全局排序。六个损失中 4 个伴随冠军集合变化，2 个在冠军 ID 不变时仅因
local audit 改写而翻转；只有 `mb55` r3 的 gold champion identity 改变是决定性删除。
因此这是“动态局部冠军+audit”的处理效应，不是纯冠军 identity 效应。

A2→A3 只改变组间证据。协议 v2 对完全相同的 effective payload 使用同一 cache key，
强制复用同一仲裁结果，消除了“温度 0 仍非确定”的伪消融翻转。修正后 Top-1 和
Top-2 都是**精确零变化**，MRR `+1.5pp [0,+4.5]`；动态组间 F2 只改善少量较深
rank，没有阈值收益。v1 中 `mxh036` 的 gain 与 `mb57` 的两个 loss 不能继续解释为
选证效应，其中相同 payload 的变化是独立重调用噪声。

联合主臂 A3 的结构可达率仍为 90.5%：4/42 局部淘汰来自 `mxh046` 三次和
`mxh075` r3；其余错误主要是 **24/42 final-ranking miss**，14/42 Top-1 成功。
`mb83_foreignbody` 在 A3 中三次都保留 gold champion、Top-2=100%、Top-1=33.3%；
A4 去 prior 时为 100%，但 A8 又回落到 0。该病例确认错误位于最终临床权衡而非结构
删除，也说明单病例翻转不足以证明 prior 的总体因果效应。

#### 10.15.3 干扰部件与裁决

- 去 parent prior：Top-1/Top-2 均 `−2.4pp`，均不显著；强 prior 不是总体
  主因。
- 去 local audit：Top-1 `−7.1pp`、Top-2 `+4.8pp`；方向相反但 CI 均跨零。
- selected-only：Top-1 `−7.1pp`、Top-2 `+2.4pp`、MRR `−2.9pp`；v1 的全面正向
  点估计来自重复调用噪声，不能再声称已证实 context bypass。
- effect handoff：Top-1 不变、Top-2 `+2.4pp`，不足以修复局部冠军问题。
- A8 相对 A1：Top-1 `+7.1pp [−9.5,+26.2]`，Top-2
  `−7.1pp [−23.8,+4.8]`，MRR近乎相同；不能证明 A8 优于简单修复对照。
- 逻辑 LLM 调用均值：A1 **5.7/病例**，A3/A8 **20.9/病例**，约 3.7 倍。

最终裁决：

1. **拒绝**把“动态局部 F4 + 动态组间 F2”接入生产；它比 A1 贵约 3.7 倍，且
   gold-present Top-2 显著低 14.3pp。
2. 立即生效的实现修复只有**真实消费顺序语义**；旧冻结冠军/前缀资产不可继续当作
   真实 F2，部署前必须按新 trace 重冻。
3. 以 Top-2 为主要安全目标时，当前经验基线是 **A1 真实顺序 F2**。A8 仅保留为
   Top-1 研究臂，扩大样本前不晋级。
4. 下一轮不应继续增加 evidence budget；应修改局部阶段的输出目标，从“每父分支
   单独 Top-1”改为“产生适合跨父比较的校准 champion/audit”，并联合训练或校准最终
   仲裁。

产物：

- `scripts/eval_l2_joint_dynamic_pipeline.py`
- `src/agentclinic_tree_dx/prompts/l2_joint_champion_arbiter.txt`
- `tests/test_l2_joint_dynamic_pipeline.py`
- `logs/l2_competition_strategies_v1/l2_joint_dynamic_v1/summary.json`

### 10.16 Naive CoT 三层替代基线：BFS 只在结构化 Top-2 保留上占优

为检验增量流水线是否优于普通逐步推理，本轮固定 17 例、3 重复、temperature=0，
统一报告 Top-1、Top-2、MRR@2。三种替代均使用 BFS 自身冻结
`l1_grounded_chunk_catalog_v1.json`，不是生产 live RAG。每个病例预先冻结一个
arm-blind bundle，三臂的 access ID、正文、顺序和 12-chunk 上限完全相同；51 个
病例-重复均通过 bundle hash/order 一致性审计。该库只有 13/17 病例有片段，共服务
150 条，`mb34_leukemoid`、`mb57_kartagener`、`mb65_cml`、`mxh055` 保持空知识，
没有从其他索引补齐。

三臂定义：

1. `N0-CoT-vignette-free` 只接收原始题干（包括原题选项）和共享知识正文，自由输出
   两个具体疾病名；不见树、自动 findings 或 mapper。51 个输出由人工按冻结疾病实体
   逐条判定，统计阶段只读取冻结判定。
2. `N1-CoT-branch-only-hierarchy` 只保留冻结二层树和初始 L1 prior，按
   `L1 Top-2 → 各父内 L2 Top-2 → 四个 L2 间 Top-2` 进行普通列表选择；不运行 BFS
   选证、effect annotation 或 posterior 更新。
3. `N2-CoT-L2-local-only` 保留修复后的 BFS L1 posterior、真实消费顺序 F2 和原
   champion arbiter；仅把每个 parent 的 per-fact L2 标注替换为普通 CoT Top-2，
   仍只把局部第一名交给组间仲裁。

14 个 gold-present 病例 × 3 重复的结果：

- A1 真实顺序 F2 参考：**26.2% / 73.8% / 50.0%**。
- N0 自由诊断：**38.1% / 71.4% / 54.8%**；相对 A1 为 Top-1
  `+11.9pp [−2.4,+31.0]`、Top-2 `−2.4pp [−21.4,+14.3]`、MRR@2
  `+4.8pp [−8.3,+17.9]`，均未达到显著。人工分解为 rank1 16/42、rank2
  14/42、miss 12/42。
- N1 三级列表：**26.2% / 50.0% / 38.1%**；Top-1 与 A1 相同，但 Top-2
  **`−23.8pp [−45.2,−7.1]`**。错误由 L1 gate 6、组内淘汰 2、最终组间误排
  18、schema failure 5 和 Top-1 success 11 构成。
- N2 仅换局部标注：**40.5% / 45.2% / 42.9%**；Top-1 `+14.3pp`
  但 CI 跨零，Top-2 **`−28.6pp [−50.0,−7.1]`**。错误由上游 L1 不可达 2、
  schema failure 14、最终误排（含 rank2）9 和 Top-1 success 17 构成。

N2 的 Top-1/Top-2 反向变化不是“普通 CoT 全面更好”。局部 Top-2 的第二名按协议
不参与组间竞争，局部第一名压缩使结果更激进；同时多父串联调用产生 schema 级联，
42 个主分析单元中 30 个至少修复一次，最终只有 28 个全链 schema-valid。条件于
schema-valid，N2 为 60.7%/67.9%，说明模型有局部排序信号，但当前列表协议不能可靠
传递该信号。N1 同样显示主要损失发生在最终跨父 Top-2，而不是组内门控。

知识引用不是命中门槛。对有知识可用的 39 个单元，N0/N1/N2 引用率分别为
92.3%/100%/100%；因此失败不能归因于某一臂没有拿到 RAG，仍需注意冻结库约 15%
事实覆盖这一共同上限。

裁决：

1. 本轮**不能证明 BFS 在自由疾病诊断的 Top-1 或 MRR@2 上优于 N0**；N0 点估计反而
   更高，但手工实体判定、原题选项和不可结构审计使其不能直接替代生产流水线。
2. BFS 的已证实优势是相对 N1/N2 的 **Top-2 保留**：两种结构化 Naive 替代都显著
   下降，说明 effect/posterior 更新与多候选保留确有作用。
3. 不采用 N1 或 N2。生产继续保留 A1 真实顺序 F2。若研究 N2，应首先让局部 Top-2
   都进入可校准的跨父比较，并修复长 JSON/schema 级联，再重新测量；不能只保留局部
   champion。

产物：

- `scripts/freeze_naive_cot_bfs_knowledge.py`
- `scripts/eval_naive_cot_hierarchy_baselines.py`
- `scripts/freeze_naive_cot_manual_adjudication.py`
- `eval_fixtures/naive_cot_bfs_knowledge_v1.json`
- `eval_fixtures/naive_cot_vignette_manual_gold_v1.json`
- `tests/test_naive_cot_hierarchy_baselines.py`
- `logs/naive_cot_hierarchy_baselines_v1/summary.json`

### 10.17 N0 RAG 消融：生产自由检索未优于无 RAG

在 §10.16 的自由疾病 Top-2 之外补充两个臂，仍使用同一模型、原始题干、17 例 ×
3 重复、temperature=0 和人工实体判定：

- `N0-CoT-live-production-RAG`：模型先基于题干自由生成 1–4 条检索 query；每条 query
  同时搜索生产 `rag_index`（FAISS，493,646 条）和 `cpg_index`（TF-IDF，
  205,115 条），各取 Top-3，再按跨 query/index 的 RRF 去重，向答案器提供最多
  12 条、每条 1,600 字符。所有 query、原始 hits、access ID、index metadata hash
  与最终 bundle 均写入 trace。
- `N0-CoT-no-RAG`：完全不初始化任何病例知识 payload，只给同一原始题干并自由输出
  疾病 Top-2。

14 个 gold-present 病例 × 3 重复的结果：

- 生产自由 RAG：**21.4% / 59.5% / 40.5%**，平均 12 chunks、2.02 次 LLM
  调用/病例；
- 无 RAG：**26.2% / 57.1% / 41.7%**，1 次 LLM 调用/病例；
- §10.16 的 BFS 冻结知识 N0：**38.1% / 71.4% / 54.8%**；
- A1 BFS 参考：**26.2% / 73.8% / 50.0%**。

生产自由 RAG 相对无 RAG：Top-1 `−4.8pp [−26.2,+16.7]`、Top-2
`+2.4pp [−19.0,+23.8]`、MRR@2 `−1.2pp [−17.9,+15.5]`，均无显著收益。
相对 BFS 冻结知识 N0，它的 Top-1/Top-2/MRR@2 分别低
`16.7/11.9/14.3pp`，CI 仍跨零。无 RAG 相对冻结知识也低
`11.9/14.3/13.1pp`。因此小样本不支持“live RAG 有害”的确定因果结论，但可以
排除当前自由检索协议具有明显正收益。

病例审计解释了方向：

1. **query 先验锚定**：`mb11_pancoast` 的 planner 围绕“单侧上肢无力、
   brachial plexopathy vs radiculopathy”检索，忽略吸烟、快速消瘦与肿瘤红旗；
   返回的臂丛/脊髓/卒中片段把答案从冻结知识 N0 的 Pancoast tumor 拉到
   brachial plexopathy。
2. **显著发现被常见原型覆盖**：`mb55_glucagonoma` 的 planner 把疼痛性皮疹+
   高血糖重写为 DKA/HHS 查询，没有检索坏死性游走性红斑或 alpha-cell tumor；
   12 条结果集中于一般高血糖，最终两名都漏掉 glucagonoma。
3. **通用流行病学放大常见诊断**：`mxh045` 检索到“5 岁以下肠梗阻最常见
   intussusception”，使其升到 Top-1；malrotation 只保留在 Top-2。检索增加了
   结构可达性但没有改善首位校准。
4. 当前 RRF 对不同 index/query 的 rank 等权，没有 vignette-level
   evidence reranker；只要 planner 给出宽泛 query，就会把 12 个槽位填满大量
   主题相关但不具区分性的正文。

裁决：**不把当前生产自由 RAG 接入 N0 或 BFS**。冻结 BFS 知识即使只有 13/17
病例有片段，点估计仍全面高于 live RAG，说明关键是候选/发现条件化的知识选择，
不是无约束扩大检索量。若继续研究，应先做显著发现驱动 query、病例级区分性
rerank 和“允许返回零条”的噪声门控，而不是增加 chunk budget。

产物：

- `scripts/eval_naive_cot_rag_ablation.py`
- `scripts/freeze_naive_cot_rag_ablation_manual.py`
- `src/agentclinic_tree_dx/prompts/naive_cot_live_rag_planner.txt`
- `tests/test_naive_cot_rag_ablation.py`
- `eval_fixtures/naive_cot_rag_ablation_manual_gold_v1.json`
- `logs/naive_cot_rag_ablation_v1/summary.json`

### 10.18 L2 分支生成 C/A/B：覆盖提升被候选稀释抵消

本轮比较三种 L2 生成路径，使用同一批去除 L2 的冻结 L1 seeds、17 例 × 3 重复、
temperature=0，并对 153 棵生成树逐条人工判定具体疾病实体：

- C：当前 `SubBranchCreator`；
- A：每个 L1 parent 独立运行多源召回、具体疾病生成和 gap-fill；
- B：复用病例级 L1 recall hints，先映射到 parent，再注入并 gap-fill；parent 下游
  retrieval 固定为零。

运行下游前发现并修复一个 P0：强化生成器偶尔复制 prompt 示例中的 `B1.x` child ID，
不同 parent 的叶在全局 `state.branches` 中互相覆盖。现在 A/B 的 child ID 一律按真实
parent 重编号，生成 trace 额外校验 branch key、parent ownership、children backlink
和 parent ID namespace。全部树随后重生成、重新人工判定；旧的 88.2%/88.2% A/B
覆盖数字作废。最终 gold L2 coverage 为：

- C：**76.5%**（39/51）；
- A：**88.2%**（45/51），相对 C `+11.8pp [−11.8,+35.3]`；
- B：**84.3%**（43/51），相对 C `+7.8pp [−17.6,+33.3]`。

覆盖不等于可选性。全 17 例（absent 记 miss）的
`Oracle-parent dynamic F4 Top-1/Top-2/MRR` 为：

- C：**66.7% / 76.5% / 71.6%**；
- A：**54.9% / 76.5% / 69.3%**；
- B：**54.9% / 68.6% / 66.7%**。

条件于本臂 gold 已生成，C 为 **87.2% / 100% / 93.6%**，A 为
**62.2% / 86.7% / 78.5%**，B 为 **65.1% / 81.4% / 79.1%**。也就是说 A 的
结构召回收益恰好被局部排序损失抵消，B 则连全量 Oracle Top-2 也下降。直接原因是
候选负担和语义重复：C/A/B 每 parent 平均叶数为 `3.86/6.04/4.67`，重复率为
`4.2%/46.5%/38.5%`。

冻结实际 L1 posterior、真实消费顺序 F2 局部冠军及带 L1 prior 组间仲裁后的
端到端 `Top-1/Top-2/MRR` 为：

- C：**33.3% / 51.0% / 45.1%**；
- A：**43.1% / 49.0% / 48.5%**；
- B：**37.3% / 45.1% / 44.5%**。

A 相对 C 的 Top-1 `+9.8pp [−13.7,+33.3]`，但 Top-2 `−2.0pp
[−25.5,+21.6]`，三项均不显著；B 的 Top-1 `+3.9pp`、Top-2 `−5.9pp`、MRR
`−0.6pp`，同样不显著。在旧 14 个 gold-present 病例子集上，C/A/B 分别为
`40.5/61.9/54.8%`、`45.2/52.4/51.8%`、`38.1/47.6/46.9%`，A/B 均损害
Top-2。

成本使用 logical requested calls，不把缓存命中误算为零。C/A/B 每例生成 LLM
调用为 `4.9/18.7/14.8`；A 另有 `4.88` 次 parent retrieval，B 为 `1` 次病例级
mapping、零 parent retrieval。A 的 31.4% 单元、B 的 9.8% 单元满足“人工认可 gold
hint 在修复前未覆盖，repair accepted 后生成 gold”的严格 gap-gain 定义。B 的
`mapping recall=100%` 实际为 **42/42 evaluable**，另有 9/51 不可判定；它只条件于
有显式人工认可 recall candidate 且已有认可生成 parent，不能证明 absent 病例映射
正确。下一版必须独立标注 gold parent 才能测无条件 mapping recall。下游调用现已拆成
`oracle-capability` 与 `production-e2e`；后者 C/A/B 为 `4.22/5.35/5.06` 次/例。
Oracle 调用仅用于能力测量，不属于生产成本。所有本轮重算的 downstream 请求均命中
冻结 cache，故模型实调为零；summary 同时保存 requested/model/cache 三种计数。

病例簇转移进一步限定了适用范围：

- A 相对 C 稳定新增 `mb34_leukemoid`、`mxh014`、`mxh045`（各 3/3），但稳定丢失
  `mb66_peliosis`（3/3）；只有 `mb34` 与 `mxh014` 把结构新增稳定转化为
  `oracle-parent-F4-local` 和端到端成功，`mxh045` 三次均停在局部误排。
- B 同样新增上述三例，并仅在 `mxh068` 1/3 新增 gold；同时稳定丢失
  `mb66_peliosis`、`mb77_hyperpara`。这说明下传映射存在跨重复不稳定，B 不能被视为
  A 的无损低成本版本。
- A 的典型稀释关联见 `mb65`、`mb82`、`mxh046`：leaf burden 和跨 parent 重复增加
  同时伴随 Oracle 首位下降。该证据是强相关而非单独随机化的因果证明；下一轮仍需
  `targeted injection + dedupe` 部件臂。

为避免术语误导，summary 同时保留兼容字段 `oracle_top*` 和明确字段
`oracle_parent_f4_local_top*`。该指标用 gold 只限定 parent scope，再运行动态 F4
局部排序；它与实际 F2 champion+组间链路不同，不是实际链路的数学上界。泄漏报告也
已区分运行时检查与代码路径 protocol assertions，后者不再表述为独立审计证据。

裁决：

1. **A、B 均不直接晋级，生产保留 C。** A 是覆盖最佳研究臂，但以 3.8 倍生成调用、
   56% 更高叶负担和大量重复换取，尚未转化为稳定的 Top-2。
2. B 证明“下传 recall hints 可免 parent retrieval”，但不是 A 的等价低成本替代：
   coverage、Oracle Top-2 和端到端 Top-2 均更低。
3. 下一版应测试 `C + targeted repair`：仅在 parent 无具体疾病叶或检测到召回缺口时
   触发 hint 注入/gap-fill；进入 L2 排序前做 parent 内规范同义词去重和严格候选限额。
   不能再次全量移植 A。

产物：

- `scripts/eval_l2_branch_generation_ab.py`
- `src/agentclinic_tree_dx/prompts/l2_recall_creator.txt`
- `eval_fixtures/l2_branch_generation_ab_gold_v1.json`
- `tests/test_l2_recall_generation.py`
- `tests/test_l2_branch_generation_ab.py`
- `logs/l2_branch_generation_ab_v1/evaluation/summary.json`
- `logs/l2_branch_generation_ab_v1/evaluation/records.csv`

### 10.19 C + targeted gap-fill hybrid：B-reuse 有局部收益，但重复门失败

在 §10.18 的不可变 C 树上追加叶，不删除或改写任何 C 节点。主矩阵为
`trigger(targeted/all-parent) × source(A-fresh/B-reuse) × budget(b1/b2)`，另有 C
对照，共 9 臂、17 例 × 3 重复。所有触发和生成均 label-blind；人工金标只在生成完成
后打开。`b1` 严格为 `b2` 前缀；每 parent 最多 5 个最终叶、每病例最多新增 4 叶；
失败一律 fail-closed。

审查实现时修复了三类会污染结论的问题：基线本来超过 5 叶时不能把不增叶的 C 判为
违规；候选 source pool 必须为 Top-12 而非误截成 Top-3；共享预计算的模型调用不能
重复计入每个治疗臂。下游缓存按有效 tree hash 复用，避免相同树因 arm 名不同而发生
重复调用噪声。供应端 OpenRouter 额度耗尽时，同一
`meta-llama/llama-3.3-70b-instruct` 改走 Novita 传输端点；模型、temperature 和
payload 不变，transport 事件保留在运行日志。

全 51 单元结果：

- C：coverage **76.5%**，Oracle-parent F4 **66.7%/76.5%**，端到端
  **33.3%/51.0%/45.1%**。
- T-A-b1：coverage **78.4%**，Oracle **64.7%/76.5%**，端到端
  **29.4%/51.0%/42.2%**。相对 C 的 Top-1/MRR 为 `−3.9/−2.9pp`；
  C-success preservation 仅 **88.5%**。
- T-B-b1 与 ALL-B-b1 生成完全相同的树：coverage **82.4%**，Oracle
  **68.6%/78.4%**，端到端 **39.2%/58.8%/51.3%**，C-success preservation
  **100%**。相对 C 的 coverage、Top-1、Top-2、MRR 分别
  `+5.9/+5.9/+7.8/+6.2pp`；Top-2 配对病例簇 CI 为 `[0,+21.6pp]`。

`b2` 没有带来收益：A 只多引入极少候选并进一步降低 Top-1；B 的 b1/b2 完全相同。
targeted 与 all-parent 对 B 也完全同树，说明当前 trigger 没有减少实际注入，只使
逻辑生成调用从 ALL-B 的 **13.5** 增至 T-B 的 **17.9** 次/单元。A 还需平均
4.9 次 parent retrieval；B 保持零 parent retrieval。

人工复核 41 个唯一的 `case+disease+parent` 单元、314 个新增 occurrence。A/B
新增叶具体疾病率为 **79.2%/87.5%**，父节点错误率为 **52.8%/45.8%**；
更严重的是人工语义重复率 **41.5%/66.7%**，远超预设 10% 门槛。B 的 gold yield
虽为 12.5%，但收益高度集中：

- `mxh014` 补入正确 parent 下的 prosthetic-valve endocarditis，三个重复的
  coverage、Top-1、Top-2、MRR 全部从 0 变 1；
- `mb65_cml` coverage 不变，但 Top-2 平均 `+33.3pp`、MRR `+5.6pp`；
- 其余 15 例没有 B 端到端变化。

A 的病例转移更不稳定：`mxh014` 有收益，但 `mb11_pancoast`、`mb77_hyperpara`、
`mb83_foreignbody` 出现排序损失；尤其 `mb83` Top-2 三个重复全部丢失。由此不能把
“append-only”误解为排序无损：树结构未损坏，新增干扰项仍能改变局部冠军和跨父仲裁。

裁决：

1. **8 个 hybrid 臂均不晋级，生产继续使用 C。** B-reuse 是唯一值得保留的研究
   方向，但因 66.7% 人工语义重复率未通过晋级门。
2. 当前 targeted trigger 没有产生选择性；若不先修 trigger，ALL-B 反而同效且更省
   调用，但这不是放开全 parent 注入的生产依据。
3. 下一轮只应测试 `B-reuse b1 + stronger global semantic dedupe + parent-child
   consistency gate`，目标是在保留 `mxh014/mb65` 收益的同时把重复率压到 ≤10%；
   达标后必须进入新的冻结 holdout，不能在这 17 例上直接晋级。

产物：

- `scripts/eval_l2_targeted_gapfill_hybrid.py`
- `src/agentclinic_tree_dx/prompts/l2_targeted_gapfill_selector.txt`
- `tests/test_l2_targeted_gapfill_hybrid.py`
- `eval_fixtures/l2_targeted_gapfill_hybrid_gold_v1.json`
- `logs/l2_targeted_gapfill_hybrid_v1/evaluation/summary.json`
- `logs/l2_targeted_gapfill_hybrid_v1/evaluation/records.csv`

### 10.20 纯 C/A/B 叶质量专项审计：高具体疾病率被错挂与重复抵消

为补齐 §10.18 只有 gold coverage 和字符串级 `duplicate_rate`、没有逐叶临床质量
裁决的缺口，本轮对冻结的 C/A/B 153 棵树做独立 post-generation 审计。共复核
**3,631** 个 L2 leaf occurrence；按规范化
`case + leaf label + parent label` 去重为 **1,359** 个裁决单元。裁决只看 leaf 与
parent label，不读取 gold diagnosis 或 `acceptable_l2`，因此不回流污染生成或排名。
首轮分病例完成 model-assisted clinical review，随后对全部 1,359 单元、144 个非平凡
语义簇及 hybrid 重叠单元做独立一致性复核并应用 20 项修正。

主指标均以全树非 fallback L2 叶为分母：

- `leaf_specific_rate`：具体命名疾病、综合征或可独立诊断临床实体的比例；
- `leaf_parent_invalid_rate`：临床上不属于所挂 L1 parent taxonomy 的比例；
- `leaf_semantic_duplicate_rate`：所在人工语义簇在同一棵树出现至少两次的**成员叶**
  比例，对齐 hybrid 的“新增叶是否与树内任一叶重复”口径；
- `semantic_duplicate_excess_rate`：每个语义簇只保留一个代表后最少可删除的叶比例，
  与 §10.18 旧的精确字符串 `duplicate_rate` 直接可比；
- `leaf_clean_rate`：同时满足 specific、parent-valid 且树内语义唯一的叶比例。

全树 occurrence-weighted 结果：

- C：specific **64.0%**，parent-invalid **2.7%**，语义重复成员 **9.0%**，
  语义重复 excess **4.6%**，clean **56.9%**；
- A：specific **94.3%**，parent-invalid **43.8%**，语义重复成员 **70.6%**，
  语义重复 excess **48.1%**，clean **17.8%**；
- B：specific **92.6%**，parent-invalid **36.4%**，语义重复成员 **62.0%**，
  语义重复 excess **40.4%**，clean **23.7%**。

旧精确字符串 excess C/A/B 为 **4.2%/46.9%/39.4%**；语义裁决只再增加
`+0.4/+1.3/+1.0pp`，说明 §10.18 的高重复主要不是模糊同义词算法造成，而是同一
或近同标签在树内真实反复生成。成员率显著高于 excess 率是分子定义不同：一个三叶
重复簇在成员口径计 3，在 excess 口径计 2，不能互换解释。

只看相对匹配 C 树不存在的语义簇，A/B 分别有 **917/783** 个新增 occurrence：
A 的 specific/parent-invalid/重复成员/excess/clean 为
**91.1/44.2/61.7/40.5/21.0%**；B 为
**89.8/39.2/56.1/35.1/23.5%**。因此“生成了更多具体疾病名”为真，但约四成新叶
挂错 parent，且超过一半落入树内重复簇；coverage 增益伴随的候选稀释已有直接逐叶
证据，不再只依赖 Oracle 下降作间接推断。

17 病例簇 bootstrap 也排除该差异只是少数病例驱动：相对 C，A/B 的 parent-invalid
分别 `+41.0pp [36.4,+45.4]`、`+34.1pp [27.6,+41.0]`，语义重复成员分别
`+61.6pp [54.0,+69.2]`、`+51.5pp [39.4,+64.2]`，clean 分别
`−38.5pp [−47.7,−29.7]`、`−31.5pp [−41.9,−21.2]`。与 hybrid 中 34 个可安全
匹配的已有质量单元相比，parent-valid 一致率 **100%**、specific 一致率 **97.1%**；
剩余一个 specific 边界冲突保留本轮“具体转移性疾病实体”的裁决。

裁决不变且证据增强：**A/B 纯流水线均不晋级，生产继续使用 C。** Specific rate
不能单独作为质量门；后续任何 L2 扩展至少同时要求 parent-child consistency、
树内语义去重和 clean-yield。当前 17 例已参与方案选择，本轮审计只能解释既有失败，
不能替代新 holdout 的晋级验证。

产物：

- `scripts/audit_l2_branch_generation_quality.py`
- `tests/test_l2_branch_generation_quality_audit.py`
- `eval_fixtures/l2_branch_generation_quality_audit_v1.json`
- `logs/l2_branch_generation_quality_audit_v1/summary.json`
- `logs/l2_branch_generation_quality_audit_v1/records.csv`
- `logs/l2_branch_generation_quality_audit_v1/adjudication_corrections_review.json`

### 10.21 A1–A17 预注册矩阵：实现完成，校准硬门阻止确认性晋级

本轮新增 `eval_fixtures/l2_a_variant_protocol_v1.json`，将 C、原始 A、A1–A17、
四个组合臂、比较基线、缓存身份、质量门和 holdout 规则冻结为机器可读协议。生成侧由
`scripts/eval_l2_a_variant_generation.py` 实现 A1–A10；下游侧由
`scripts/eval_l2_a_variant_downstream.py` 实现原始 F2→F2 基线、A5/A11–A17 和
`A11+A14`、`A11+A16` 的真实组合回放。组合结果不再用单因子 A14/A16 代理。

三层审计由 `scripts/audit_l2_a_variant_api.py` 执行：

1. Tier 0 校验 topology、tree/fixture hash、gold 泄漏、schema 与裁决单元去重；
2. Tier 1 仅使用 OpenRouter `google/gemma-4-31b-it`，隔离执行 LeafQuality、
   SemanticCluster 和 GoldMatch 契约；
3. Tier 2 使用 `cursor-grok-4.5-high-fast` 对 Gemma 低置信病例和病例级
   3% sentinel 做 blind 复核；字段分歧或双方置信不足写入 Tier 3 人工队列。

Gemma 原始预注册校准为 specific κ **0.773**、parent-valid κ **0.789**、
semantic duplicate F1 **0.860**、gold-presence sensitivity **1.000**、
acceptable-ID macro F1 **0.935**。触发式 Cursor Grok 4.5 校准复核覆盖 12 个 blind
chunk、837 个去重 unit，并产生 475 个 Tier 3 字段。

475 项现已由 GPT-5.6 Sol 高阶审计代理逐项解析，并明确记录
`reviewer_type=ai_proxy`，没有伪记为人类签署。重算后的校准为：

- specific Cohen κ **0.788**（门槛 0.85，失败）；
- parent-valid Cohen κ **0.803**（门槛 0.85，失败）；
- semantic duplicate pairwise F1 **0.866**（门槛 0.90，失败）；
- gold-presence sensitivity **1.000**（门槛 0.98，通过）；
- acceptable-ID macro F1 **0.951**（门槛 0.95，通过）。

待决值虽已清零，但全量 1,359 单元中未触发 Tier 3 的既有判断仍使前三项不达标；
且真实高阶人工尚未签署。因此校准和开发结果继续保持 `research_only`，
`human_signed_off=false`。

真实开发执行已生成 561 个 C/A/A1–A10 source-tree×case×replicate trace，并完成
561 个下游 source replay；其中 **3/561（0.53%）** 为空树等结构性运行失败，低于
5% 运行门，但必须按 miss/blocked 计入而不能静默删除。开发集仍永久标记为
exploratory。19 臂 headline grid 共 969 个单元（每臂 17 病例 × 3 重复 = 51）。

#### 10.21.1 Entry gate 口径（相对 A-raw）

- **Hard**：无 gold 泄漏、无拓扑丢失、runtime hard gate 全过。
- **Performance**：统一使用当前 `downstream_full` replay 后，actual Top-2 ≥ 同
  harness A-raw **37.3%**，且 coverage ≥ A-raw − 5 pp（即 ≥ 83.2%）。
- **Quality**：相对 A-raw，parent-invalid 与 semantic-duplicate-excess 均至少下降 50%；
  纯下游诊断臂（A5/A11–A17）可豁免质量门。
- 统一重算后 A2（coverage 84.3%、Top-2 41.2%）与 A6（88.2%、37.3%）通过
  performance 子门，但都未通过 quality；A4 Top-2 最高但 coverage 80.4% 未过线。
  故 **全部 19 臂仍为 `entry_gate_pass=false`**；`promotion_eligible=false`。

#### 10.21.2 统一 same-harness + Tier 3 语义性能（n=51，已更正）

旧表把 C-prod/A-raw 的冻结 AB endpoint 与变体的当前 downstream replay 并列，并把
GoldMatch 分歧后的 `value=None` 当作空 acceptable 集合。现统一为：

1. 所有可比臂都读取当前 `downstream_full` ranking；
2. C-prod 使用冻结 C stable IDs；A-raw/A1–A5/A11–A17 使用冻结 A stable IDs；
3. A6–A10 的新/移动 ID 使用已完成的 Tier 3 代理语义 GoldMatch；
4. coverage、Top-1、Top-2、MRR@2 与 Oracle-F4 均按当前 `downstream_full` 重算。

| 臂 | 机制摘要 | Cov% | Top1% | Top2% | MRR@2% | Oracle-F4 Top2% | Burden | Clean% | Parent-inv% | Dup-excess% | ΔCov | ΔTop1 | ΔTop2 | Oracle−E2E gap | Empty rank | Perf | Qual |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|:---:|:---:|
| C-prod | 生产 C 对照 | 76.5 | 29.4 | 47.1 | 38.2 | 76.5 | 3.86 | 55.1 | **0.1** | 7.5 | −11.8 | −5.9 | +9.8 | 29.4 | 0 | ✗ | ✓ |
| A-raw | 未改 A 召回基线 | **88.2** | 35.3 | 37.3 | 36.3 | **82.4** | 6.04 | 18.6 | 39.1 | 49.8 | 0 | 0 | 0 | 45.1 | 0 | ✓ | ✗ |
| A1 | 本地 parent 门控 | 80.4 | 27.5 | 39.2 | 33.3 | 70.6 | 2.24 | 34.8 | 14.0 | 36.7 | −7.8 | −7.8 | +2.0 | 31.4 | 0 | ✗ | ✗ |
| A2 | 语义去重 + parent cap | 84.3 | 33.3 | 41.2 | 37.3 | 72.5 | 2.59 | 57.5 | 33.7 | **4.1** | −3.9 | −2.0 | +3.9 | 31.4 | 0 | **✓** | ✗ |
| A3 | 证据重排 top-k | **88.2** | 29.4 | 31.4 | 30.4 | **82.4** | 3.83 | 17.8 | 39.6 | 52.9 | 0 | −5.9 | −5.9 | 51.0 | 0 | ✗ | ✗ |
| **A4** | A1→A2→A3 | 80.4 | **37.3** | **54.9** | **46.1** | 72.5 | **1.25** | **74.9** | 14.9 | 4.9 | −7.8 | +2.0 | **+17.6** | **17.6** | 0 | ✗ | ✓ |
| A5 | 原始全局仲裁（诊断） | **88.2** | 13.7 | 15.7 | 14.7 | **82.4** | 6.04 | 18.6 | 39.1 | 49.8 | 0 | −21.6 | −21.6 | 66.7 | **26** | ✗ | ✓† |
| A6 | A recall + C generate | **88.2** | **37.3** | 37.3 | 37.3 | 72.5 | 4.99 | 14.4 | 41.0 | 55.7 | 0 | +2.0 | 0 | 35.3 | 0 | **✓** | ✗ |
| A7 | 全局 parent reassignment | 60.8 | 25.5 | 35.3 | 30.4 | 51.0 | 1.79 | 30.9 | 12.8 | 41.5 | −27.5 | −9.8 | −2.0 | 15.7 | 4 | ✗ | ✗ |
| A8 | 提案-批评-修订 | **88.2** | 33.3 | 33.3 | 33.3 | 70.6 | 4.94 | 13.5 | 40.8 | 55.8 | 0 | −2.0 | −3.9 | 37.3 | 0 | ✗ | ✗ |
| A9 | 多样本共识 | 62.7 | 29.4 | 31.4 | 30.4 | 56.9 | 2.73 | 20.1 | 31.4 | 51.5 | −25.5 | −5.9 | −5.9 | 25.5 | 0 | ✗ | ✗ |
| A10 | N-best 选择 | 62.7 | 35.3 | 37.3 | 36.3 | 58.8 | 2.79 | 22.3 | 31.6 | 49.4 | −25.5 | 0 | 0 | 21.6 | 0 | ✗ | ✗ |
| A11 | core/shadow 激活 | **88.2** | 17.6 | 19.6 | 18.6 | **82.4** | 6.04 | 18.6 | 39.1 | 49.8 | 0 | −17.6 | −17.6 | 62.7 | 10 | ✗ | ✓† |
| A12 | 证据支持门 | **88.2** | 25.5 | 27.5 | 26.5 | **82.4** | 6.04 | 18.6 | 39.1 | 49.8 | 0 | −9.8 | −9.8 | 54.9 | 6 | ✗ | ✓† |
| A13 | 反事实剪枝 | **88.2** | 21.6 | 21.6 | 21.6 | **82.4** | 6.04 | 18.6 | 39.1 | 49.8 | 0 | −13.7 | −15.7 | 60.8 | **27** | ✗ | ✓† |
| A14 | 动态局部 F4 | **88.2** | 31.4 | 33.3 | 32.4 | **82.4** | 6.04 | 18.6 | 39.1 | 49.8 | 0 | −3.9 | −3.9 | 49.0 | 0 | ✗ | ✓† |
| A15 | 双 champion | **88.2** | 31.4 | 33.3 | 32.4 | **82.4** | 6.04 | 18.6 | 39.1 | 49.8 | 0 | −3.9 | −3.9 | 49.0 | 0 | ✗ | ✓† |
| A16 | 门控全局叶仲裁 | **88.2** | 27.5 | 29.4 | 28.4 | **82.4** | 6.04 | 18.6 | 39.1 | 49.8 | 0 | −7.8 | −7.8 | 52.9 | 3 | ✗ | ✓† |
| A17 | prior 温度校准 | **88.2** | 33.3 | 35.3 | 34.3 | **82.4** | 6.04 | 18.6 | 39.1 | 49.8 | 0 | −2.0 | −2.0 | 47.1 | 0 | ✗ | ✓† |

† 纯下游诊断臂，质量门按协议豁免。质量列仍来自 `research_only` 外部审计。
此处沿用的 “Oracle-F4 Top2” 实际是
`gold_in_any_parent_local_f4_top2`（gold stable ID 是否进入当前 A15 双 champion
handoff），不是已知正确父分支上的真正 oracle，也不包含最终组间排序。

Tier 3 代理语义裁决使 A6–A10 首次可进入同一研究表。病例格相对 A-raw 的
coverage / Top-2 gain-loss 为：A6 `0/0`、`4/4`；A7 `0/14`、`4/5`；
A8 `0/0`、`3/5`；A9 `0/13`、`2/5`；A10 `0/13`、`3/3`。A6 只维持
Top-2 基线，且 parent-invalid/duplicate-excess 反而升至 41.0%/55.7%；A7–A10
均没有净 Top-2 收益。

机器可读更正表：
`logs/l2_a_variant_matrix_v1/evaluation/arm_performance_unified_reanalysis.{json,tsv}`。
原 `arm_performance_analysis` 仅作为旧混合口径快照保留。

#### 10.21.3 分层解读

1. **召回 vs 排序**：A-raw 召回仍为 88.2%，但同-harness Top-1/Top-2 只有
   35.3%/37.3%；C-prod 为 29.4%/47.1%。旧 43.1%/49.0% 与 33.3%/51.0% 属于
   冻结 AB endpoint，不再作为本矩阵配对基线。
2. **生成侧清洗**：A4 的统一 Top-1/Top-2 为 **37.3%/54.9%**，相对 A-raw
   **+2.0/+17.6 pp**；12 个 Top-2 gain、3 个 loss，Oracle−E2E gap 为 17.6 pp。
   失败点是 coverage 80.4%，距 83.2% 门槛 2.8 pp。A1/A2 的 Top-2 也不是下降，
   而是 +2.0/+3.9 pp；A2 同时以 84.3% coverage 通过 performance 子门，但质量门失败。
   A3 才是 stable-ID transform 中真实下降者（Top-1/Top-2 均 −5.9 pp）。
3. **再生/共识**：Tier 3 代理语义统一后，A6 coverage 88.2%、Top-1/Top-2
   37.3%/37.3%，仅通过 performance 子门，质量比 A-raw 更差；A8 保住 coverage
   但 Top-2 −3.9 pp。A7/A9/A10 分别损失 14/13/13 个 coverage 病例格，
   说明 parent movement、共识和 N-best 的主要问题仍是语义召回删除，而非只差排序。
4. **纯下游**：A5/A11–A17 相对同-harness A-raw 的下降缩小了 11.8 pp，但仍全部低于
   37.3% Top-2 基线。A17（35.3%）与 A14/A15（33.3%）只是轻度下降
   2.0/3.9 pp；A5/A11/A13 的主要问题仍是 26/10/27 个空 ranking。
5. **组合**：Tier 3 代理口径下，COMBO-1（A8→A11→A14）coverage 88.2%、
   Top-2 31.4%，仍低于 A8 单臂 33.3% 和 A-raw 37.3%；COMBO-2/3/4
   另有空终端 ranking 或空树。

#### 10.21.4 有希望进入端到端测试的实验臂

下列臂 **尚未通过 entry gate，不得晋级**；但作为下一轮端到端（真实 F2→组间→
聚合）对照/消融，按优先级推荐：

| 优先级 | 臂 / 栈 | 理由 | 主要风险 / 须先修 |
|---|---|---|---|
| **P0** | **A4** | 统一 Top-1/Top-2 37.3%/54.9%，相对 A-raw +2.0/+17.6 pp，且质量门通过 | coverage 80.4%，距性能门 2.8 pp；需 targeted gap-fill |
| **P0** | **C-prod** | 同-harness Top-2 47.1%，仍是必要现网对照 | coverage 76.5%；Top-1 仅 29.4% |
| **P1** | **A4 + A14** | 旧 rich-joint Top-2 52.9%，相对 A4 +2.0 pp | CI [−5.9,+11.8]；仅作低优先级 holdout 候选 |
| **P2 对照** | **A4 + A17** | 两 endpoint 的 Top-2 均与 A4+A14 逐格相同 | prior T=2 无增量，只保留机制对照 |
| **P2 组件** | **A2** | 统一 Top-2 41.2%，但旧 AB endpoint 仅 35.3%、相对 A-raw 的 CI 排除 0 | 只保留语义去重组件消融；不再作独立主臂 |
| **不做端到端主臂** | **A14、A17** | 旧 rich-joint Top-2 均为 35.3%，相对 A-raw −13.7 pp | 已完成旧端补测；只保留机制历史 |
| **不做端到端主臂** | **A15** | 旧 rich-joint Top-2 31.4%，相对 A-raw −17.6 pp | 双 champion 加剧组间竞争；CI 排除 0 |
| **不做端到端主臂** | A5、A11、A13 | 空 ranking 过多 / Top-2 崩盘 | 仅保留为诊断上界 |
| **P2 机制对照** | A6 | coverage/Top-2 与 A-raw 持平，Top-1 +2.0 pp | quality 更差；只用于隔离 C-generation 行为，不作为主臂 |
| **P2 机制对照** | A1 | 旧 AB Top-2 47.1%，接近 A-raw 49.0% | coverage、Top-1 均下降；只用于 parent gate 消融 |
| **不做端到端主臂** | A7–A10、COMBO-1–4 | Tier 3 后仍无净 Top-2 收益；A7/A9/A10 严重丢 coverage，COMBO-1 也低于 A8 | 仅保留组件诊断 |
| **不做端到端主臂** | A3 | stable-ID Top-1/Top-2 均比 A-raw 低 5.9 pp | 组件级研究即可 |

综合旧 AB 专用复测及 A4 组合补测后，推荐最小端到端主矩阵（研究态，非晋级）为
`{C-prod, A-raw, A4, A4+A14}`，固定同一 17×3 开发病例与缓存身份。A4+A14
在旧 rich-joint 端保留 +2.0 pp Top-2 点收益，但 CI 跨零；A4+A17 对 A14 无任何
Top-2 增量，只保留为 prior-temperature 机制对照。A1/A2/A6 可附加为机制对照但不进入
主比较。在 coverage
回补、真实 Tier 3 人工签署和新 holdout 前，仍禁止 `promotion_eligible=true`。

#### 10.21.5 子叶挂错父分支：已测口径 vs 未测口径

本轮**有**父归属质量信号，但**没有**完整的“挂错父分支概率”分析。二者不得混用。

**已测（二元 parent-invalid）**

- 字段：`LeafQuality.is_parent_valid` → 汇总为 `leaf_parent_invalid_rate`。
- 含义：在**当前父标签**下，该 L2 叶是否被判定为“不属于这个父分支”。
- 不是：应属哪个父、是否从父 \(i\) 误挂到父 \(j\)、gold 诊断所在 L1 是否错误。

开发矩阵 headline（每臂 n=51，来自质量裁决聚合）：

| 臂 | Parent-invalid% | 相对 A-raw |
|---|---:|---|
| C-prod | **0.1** | −39.0 pp |
| A-raw | **39.1** | 基线 |
| A1 | 14.0 | −25.1 pp |
| A4 | 14.9 | −24.2 pp |
| A7 | 12.8 | −26.3 pp |
| A2 | 33.7 | −5.4 pp |
| A6 / A8 | 41.0 / 40.8 | 更差 |

开发集最终裁决单元（去重 unit，`final_audit.json`）：`is_parent_valid=false` 为
**361/1267 = 28.5%**。在 `matches_gold=true` 的单元中，仍有 **38/86** 为
`is_parent_valid=false`；这只说明
“命中 gold 语义的叶也可同时挂在错误/不匹配父下”，**不是**病例级
\(P(\text{gold 被挂在错误 L1})\)。

**Judge 可靠性限制**

- Tier 3 代理校准后 `is_parent_valid` Cohen κ = **0.803**（门槛 0.85，仍失败）。
- 634 个开发待决字段均已解析，但其中 634 项为 `tier3_proxy_corrected`，且大量未触发
  字段仍为 `tier1_only`；`human_signed_off=false`。
- 因此当前 parent-invalid **仅可作探索性质量信号，不得当作确认性挂错概率**。

**未测（完整挂错父支分析）**

1. 混淆矩阵 \(P(\text{应属父 } j \mid \text{实际父 } i)\)；
2. 病例级 \(P(\text{gold 叶所在 L1} \neq \text{正确 L1})\)；
3. “错父 / 无合适父 / 语义胡编”错误类型拆分；
4. A7 `parent_movement` 虽写入 generation trace，**尚未汇总**再分配正确率与净收益。

**若要补测的最小协议**

1. 对 `is_parent_valid=false` 的叶强制选择：`{正确父 ID | reject | unsure}`；
2. 对 gold-match 叶单独报父归属错误率（病例等权）；
3. 对 A7 运动日志对齐同一强制选择，计算 reassignment precision/recall；
4. 在 κ 过门且真实高阶人工签署后，方可写入确认性门槛。

开发集触发式 Grok 复核覆盖 13 个 chunk、797 个 unit，产生的 634 条 Tier 3 队列项
已全部由高阶 AI 代理解析；这消除了 `value=None`，但不替代真实高阶人工签署。
确认性 holdout builder 在读取组合结果前已封存，但合法候选为 **0**、距最低 80 例
尚缺 **80**，故不生成虚假冠军或确认性结论。

#### 10.21.6 旧 AB 专用 endpoint 复测：A4 仅保住 Top-2 点优势

为回答变体收益是否能迁移到 §10.18 的旧 AB 专用链路，本轮按统一表
`Top-2 ≥ A-raw 37.3%` 的预筛规则纳入 A1、A2、A4、A6、A10，并保留 C-prod、
A-raw 对照。每臂仍为 17 病例 × 3 重复。生产 endpoint **原样复用**旧流程：
`true-F2 evidence → per-parent local annotator/champion → joint arbiter`；Oracle
capability 继续单列，不混入生产 Top-1/Top-2。清洗后无活 L2 的 parent 只在 champion
构建时跳过，不合成 fallback；原 C/A 控制树没有空 parent，因而冻结控制结果不受该兼容
处理影响。

| 臂 | Cov% | Top1% | Top2% | MRR% | Oracle Top2% | ΔTop1 | ΔTop2 | Top2 95% CI | gain/loss |
|---|---:|---:|---:|---:|---:|---:|---:|---|---:|
| C-prod | 76.5 | 33.3 | 51.0 | 45.1 | 76.5 | −9.8 | +2.0 | [−21.6,+25.5] | 8/7 |
| A-raw | **88.2** | **43.1** | 49.0 | **48.5** | **76.5** | 0 | 0 | — | — |
| A1 | 80.4 | 33.3 | 47.1 | 43.8 | 68.6 | −9.8 | −2.0 | [−17.6,+9.8] | 3/4 |
| A2 | 84.3 | 29.4 | 35.3 | 37.4 | 66.7 | −13.7 | **−13.7** | **[−25.5,−3.9]** | **0/7** |
| **A4** | 80.4 | 33.3 | **51.0** | 42.8 | 62.7 | −9.8 | **+2.0** | [−15.7,+19.6] | 6/5 |
| A6 | **88.2** | 35.3 | 39.2 | 42.2 | 72.5 | −7.8 | −9.8 | [−25.5,+3.9] | 2/7 |
| A10 | 62.7 | 25.5 | 29.4 | 31.6 | 56.9 | −17.6 | **−19.6** | **[−37.3,−3.9]** | 1/11 |

结论与统一 `downstream_full` 表并不等价：

1. **A4 是唯一在旧 endpoint 上 Top-2 点估计仍不低于 A-raw 的生成变体**，但
   +2.0 pp 的病例簇 CI 大幅跨零，Top-1 反而 −9.8 pp；6 gain / 5 loss 中
   `mxh075` 三次稳定增益，同时 `mb83_foreignbody` 三次稳定丢失，不能宣称稳定胜出。
2. **A2 的收益不具 endpoint 可迁移性。** 统一 replay 为 Top-2 +3.9 pp，旧 AB 专用
   endpoint 却为 −13.7 pp，CI 排除 0，且没有一个 Top-2 gain。语义去重显著改善
   clean/duplicate-excess，不代表旧 local-champion / joint-arbiter 能从更小候选池获益。
3. A1 接近 A-raw Top-2，但 coverage、Top-1 均下降；A6 虽保住 coverage，Top-2
   下降 9.8 pp；A10 的 coverage 与排序均显著恶化。它们不应作为独立晋级主臂。
4. A4+A14 补测后在旧 endpoint 保留 +2.0 pp Top-2 点收益，A4+A17 对其没有增量；
   因此下一轮旧 endpoint 主比较为 `{C-prod, A-raw, A4, A4+A14}`，A1/A2/A6 与
   A4+A17 仅作机制消融。该结论仍是
   开发集探索结果，且 A6/A10 的语义 GoldMatch 来自未获真人签署的 Tier 3 代理，
   全部保持 `research_only`。

完整机器产物为
`logs/l2_a_variant_legacy_ab_v1/evaluation/{summary.json,summary.tsv,records.json}`。
357 个结果格完整，新增变体共请求 production 1,026 次、Oracle 1,702 次逻辑调用。

#### 10.21.7 案例级 endpoint 归因：主要是证据/仲裁结构交互，不是改进整体失效

对七臂 357 格同时读取统一 replay 与旧 AB 专用结果后，表面悖论可拆成两个不同问题：

1. **变体的绝对性能是否在旧 endpoint 崩溃？**
2. **旧 endpoint 下，变体相对 A-raw 的增益是否仍存在？**

二者答案不同。A4 绝对 Top-2 仅从统一 replay 的 54.9% 变为旧 endpoint 的
51.0%，并未崩溃；但 A-raw 同时从 37.3% 被抬到 49.0%，所以 A4 相对收益由
+17.6 pp 收缩到 +2.0 pp。

| 臂 | 统一 Top2% | 旧 AB Top2% | 变体绝对位移 | 统一 ΔA-raw | 旧 AB ΔA-raw | Endpoint interaction |
|---|---:|---:|---:|---:|---:|---:|
| A-raw | 37.3 | 49.0 | **+11.8** | 0 | 0 | 0 |
| A1 | 39.2 | 47.1 | +7.8 | +2.0 | −2.0 | −3.9 |
| A2 | 41.2 | 35.3 | −5.9 | +3.9 | −13.7 | **−17.6** |
| A4 | 54.9 | 51.0 | −3.9 | +17.6 | +2.0 | **−15.7** |
| A6 | 37.3 | 39.2 | +2.0 | 0 | −9.8 | −9.8 |
| A10 | 37.3 | 29.4 | −7.8 | 0 | −19.6 | −19.6 |

**第一主因是 evidence contract 并不相同。** 旧 AB local/joint 链使用真实 L1
`consumption_order` 的 F2；统一 replay 使用 auto-finding fixture 的
`filter_runs.ranked_fact_ids` F2。51 格中：

- 仅 **8/51** 的 F2 集合与顺序完全相同；
- **6/51** 是同一两个 fact、顺序相反；
- **37/51** 的 F2 集合不同。

在 F2 完全同序的 8 格中，A-raw、A1、A2、A4、A6、A10 **均没有任何 Top-2
endpoint 反转**。A-raw 的 18 个 endpoint flip 全发生在证据变化格：旧 endpoint
12 gain / 6 loss，净增 6 格，即 +11.8 pp；仅 6 个“同集合反序”格就产生
4 gain / 0 loss。这是证据选择与顺序敏感性，而不是树结构变化。

**第二主因是 ranker 本身不同。**

- 旧 local：对每个 selected fact 输出候选 effect，再从保留的 leaf posterior
  出发顺序执行 ordinal update；payload 还含完整 finding catalog。
- 统一 local：用通用 prompt 直接输出完整 candidate permutation；不传 leaf
  posterior，只传 parent prior 与 provenance RRF。
- 旧 intergroup：接收完整 vignette/findings、parent posterior、local score 和
  local evidence audit。
- 统一 intergroup：仍用通用 direct-rank prompt，只接收 selected F2、parent prior
  与 provenance；无 local score/audit。
- 旧流程要求每个 active parent 恰好一个有效 champion 后才仲裁；统一流程可跳过
  schema-invalid parent。故 candidate 删除、空 parent 与 schema 失败的影响也不同。

因此“旧错误模式导出的变体为何不能迁移”并不矛盾：旧报告中的 `local_rank`、
`intergroup` 是**失败发生位置**，不是“重复/错挂是因果中介”的证明。旧 one-champion-
per-parent 架构反而会利用错误副本作为多条路由票。A-raw 在 45 个 covered 格中平均有
**4.09 个 acceptable ID、分布于 3.84 个 parent**；A2/A4 清洗后仅
**1.23/1.10 个 ID、1.19/1.07 个 parent**。在 A-raw 中，gold 分布于 5 个 parent
的 16 格旧 Top-2 为 75.0%，只有 2 个 parent 的 6 格仅 16.7%；样本小且受病例难度
混杂，但足以说明“错挂/重复质量差”与“旧 endpoint 提供冗余路由票”可以同时成立。

旧 AB 的覆盖→局部冠军→最终 Top-2 漏斗进一步区分了各变体：

| 臂 | Coverage | Local champion | Final Top2 | Local/Cov | Top2/Cov | Top2/Local |
|---|---:|---:|---:|---:|---:|---:|
| A-raw | 45 | 29 | 25 | 64.4% | 55.6% | 86.2% |
| A1 | 41 | 30 | 24 | **73.2%** | 58.5% | 80.0% |
| A2 | 43 | 26 | 18 | 60.5% | **41.9%** | 69.2% |
| **A4** | 41 | 27 | **26** | 65.9% | **63.4%** | **96.3%** |
| A6 | 45 | 29 | 20 | 64.4% | 44.4% | 69.0% |
| A10 | 32 | 24 | 15 | 75.0% | 46.9% | 62.5% |

这说明 **A4 的机制确有迁移**：gold 一旦存活并成为 local champion，26/27 能进入
最终 Top-2；其净收益主要被 A1 gate 的 coverage 假阴性抵消。A2 则不是单纯 coverage
问题：相对 A-raw 的 7 个旧 Top-2 loss 中，6 个是 `local_champion_elimination`，
1 个是 intergroup loss。A6 的 7 个 loss 为 local 4、intergroup 3。

代表病例：

- `A2 / mb55_glucagonoma / r1`：B1.2 Glucagonoma 仍在，但旧 ordinal local
  选择 B1.1 T2DM，gold 根本没有进入 joint-arbiter。
- `A2 / mxh036 / r2`：两端都把 GSD-I 送入 champion；统一 direct ranker 排第 1，
  旧 rich joint-arbiter 排第 3，属于纯仲裁器反转。
- `A4 / mb83_foreignbody / r1–r3`：A1 把 3–4 个 Nasal Foreign Body /
  Foreign body obstruction acceptable 副本全部删除，是不可恢复的 gate 假阴性。
- `A4 / mxh075 / r1–r3`：Truncus Arteriosus 保留为单一 champion，旧
  joint-arbiter 三次均排第 1，而 A-raw 三次均失败，证明清洗可在旧链路真实获益。
- `A6 / mb11_pancoast / r2–r3`：Pancoast/Apical tumor 虽跨多个 parent 覆盖，
  每个 parent 的 winner 仍被 Brachial plexopathy/plexitis 抢走；“多票”不保证
  local champion。

当前证据足以回答“差异是否来自流水线结构”：**是，且 evidence contract 差异是最直接
可观测因素；A-raw 基线抬升解释 A4 interaction 8 个净格中的 6 个（75%），A2 的
9 个净格中的 6 个（67%）。** 但 evidence 与 ranker 同时改变，尚不能把剩余差异精确
分配给 local prompt、leaf posterior、rich audit 或 intergroup prompt。确认性归因应跑
2×2 crossover：

`{true-consumption F2, filter-ranked F2} × {ordinal+rich-joint, direct-ranker}`，
并冻结同一 tree、gold、model、temperature；随后再交换固定 local champions，只重跑
两种 intergroup arbiter。未完成该 factorial 前，结论仍为 `research_only`。

机器产物：

- `scripts/analyze_l2_a_variant_endpoint_gap.py`
- `logs/l2_a_variant_legacy_ab_v1/evaluation/endpoint_gap_analysis.json`
- `logs/l2_a_variant_legacy_ab_v1/evaluation/endpoint_gap_arm_summary.tsv`
- `logs/l2_a_variant_legacy_ab_v1/evaluation/endpoint_gap_case_cells.tsv`

#### 10.21.8 A4+A14 / A4+A17 补测：动态 F4 仅有旧端点小幅点收益，T=2 无增量

两个组合均固定 A4 清洗树与同一 stable-A Gold：

- **A4+A14**：parent 内改为动态 F4 ordinal 排序，每个 active parent 交付一个
  champion；组间仍使用对应 endpoint 的仲裁器。
- **A4+A17**：完全复用 A4+A14 的 dynamic selector、local annotation 与 champion
  集合，只把 champion 的 parent posterior 按 `p**(1/2)` 归一化后交给仲裁器。

统一端从现有 A4 downstream trace 提取；旧端新增运行
`dynamic-F4 local → one champion → rich joint-arbiter`。每个 endpoint 均有
4 臂 × 17 病例 × 3 重复 = **204 格**。

| Endpoint | 臂 | Cov% | Top1% | Top2% | MRR% | Oracle Top2% | Local champion% | ΔTop2 vs A4 | 95% CI |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| 统一 direct | A-raw | 88.2 | 35.3 | 37.3 | 36.3 | 82.4 | 58.8 | −17.6 | [−37.3,+2.0] |
| 统一 direct | **A4** | 80.4 | **37.3** | **54.9** | **46.1** | 72.5 | 56.9 | 0 | — |
| 统一 direct | A4+A14 | 80.4 | 33.3 | **54.9** | 44.1 | 72.5 | 56.9 | **0.0** | **[0.0,0.0]** |
| 统一 direct | A4+A17 | 80.4 | 33.3 | **54.9** | 44.1 | 72.5 | 56.9 | **0.0** | **[0.0,0.0]** |
| 旧 rich-joint | A-raw | 88.2 | 43.1 | 49.0 | **48.5** | 76.5 | 56.9 | −2.0 | [−19.6,+15.7] |
| 旧 rich-joint | **A4** | 80.4 | 33.3 | **51.0** | 42.8 | 62.7 | **52.9** | 0 | — |
| 旧 rich-joint | A4+A14 | 80.4 | **39.2** | **52.9** | **46.1** | 66.7 | **52.9** | **+2.0** | [−5.9,+11.8] |
| 旧 rich-joint | A4+A17 | 80.4 | **39.2** | **52.9** | **46.1** | 66.7 | **52.9** | **+2.0** | [−5.9,+11.8] |

病例级转移进一步排除了“均值掩盖净收益”：

- 统一端 A4+A14 与 A4+A17 对 A4 均为 **0 Top-2 gain / 0 loss**；二者各自只有
  2 个 Top-1 loss。也就是说，F4 local 与 T=2 只重排 Top-2 内部，没有增加召回。
- 旧端两组合相对 A4 均为 **2 Top-2 gain / 1 loss**：
  `mxh055/r2–r3` 两次 gain 被 `mxh046/r2` 的 local-champion loss 抵消一半；
  净 +1 格即 +2.0 pp，95% CI [−5.9,+11.8]。
- 旧端 A4+A14 的 Top-1 为 +5.9 pp，但病例格为 9 gain / 6 loss，
  95% CI [−15.7,+27.5]；点收益存在但不稳定。
- A17 相对 A14 在旧端和统一端都只有 1 个 Top-1 gain、1 个 loss，
  两端 Top-2 都完全不变。因此 **prior temperature 2.0 没有增量价值**。

结论：动态 F4 只在旧 rich-joint 结构中出现小幅点收益，统一 direct 端完全不增益，
再次显示下游因子与 endpoint 有交互。A4+A14 保留为低优先级 holdout 候选；
A4+A17 降为**已完成的负向 prior 校准对照**。下一轮主矩阵为
`{C-prod, A-raw, A4, A4+A14}`。这不替代 §10.21.7 的 2×2 endpoint crossover，因为
本补测只改变 A14/A17 注册因子，没有独立交换整套 evidence contract 与 arbiter。

机器产物：

- `scripts/eval_l2_a4_downstream_combinations.py`
- `logs/l2_a4_downstream_combinations_v1/evaluation/{summary.json,summary.tsv,records.json}`
- `logs/l2_a4_downstream_combinations_v1/legacy_traces/{A4+A14,A4+A17}/`

#### 10.21.9 为什么曾重排顺序，以及为何生产候选必须补跑旧链

统一 replay 的设计并非毫无理由。它原本承担的是**机制筛选 endpoint**：

1. 所有 source tree 使用同一套 candidate payload、schema repair 和 direct list-ranker，
   便于比较 A5–A17 的单因子变化；
2. 避免把旧链的 ordinal posterior、每 parent 单 champion、rich audit 与历史缓存状态
   同时带入每个组件消融；
3. 保持 generation 与 downstream 分离，使 regenerated-ID 臂也可在同一接口下运行。

但该合理性只适用于内部机制研究，不足以支持生产候选排序。统一 replay 同时改变了
F2 来源、parent 内排序、champion handoff 与 intergroup arbiter；§10.21.7 已显示
51 格中只有 8 格证据完全同序，A-raw 也被 endpoint 本身抬高 11.8 pp。因此此前把
统一 replay 的“有希望”直接写成端到端推荐，**评估边界过宽，设置不适合作为生产主终点**。
旧 A/B 链是当前离线资产中更接近生产决策结构的 surrogate，但仍不等于线上生产流量。

按此更正，尚未补跑旧链而曾被列为有希望的独立下游臂为 **A14、A15、A17**：

- A14：dynamic F4 local、每 parent 一个 champion；
- A15：与 A14 共享 local 输出，每 parent 两个 champion；
- A17：与 A14 共享 champion，只将 parent prior 温度改为 2.0。

三臂已在 A-raw 树上完成统一 direct 与旧 rich-joint 双端点 17×3 补测：

| Endpoint | 臂 | Cov% | Top1% | Top2% | MRR% | Local champion% | ΔTop2 vs A-raw | 95% CI | gain/loss |
|---|---|---:|---:|---:|---:|---:|---:|---|---:|
| 统一 direct | A-raw | 88.2 | 35.3 | 37.3 | 36.3 | 58.8 | 0 | — | — |
| 统一 direct | A14 | 88.2 | 31.4 | 33.3 | 32.4 | 62.7 | −3.9 | [−13.7,+3.9] | 1/3 |
| 统一 direct | A15 | 88.2 | 31.4 | 33.3 | 32.4 | **82.4** | −3.9 | [−9.8,0.0] | 2/4 |
| 统一 direct | A17 | 88.2 | 33.3 | 35.3 | 34.3 | 62.7 | −2.0 | [−11.8,+5.9] | 1/2 |
| 旧 rich-joint | A-raw | 88.2 | **43.1** | **49.0** | **48.5** | 56.9 | 0 | — | — |
| 旧 rich-joint | A14 | 88.2 | 31.4 | 35.3 | 37.6 | 52.9 | **−13.7** | **[−29.4,0.0]** | 2/9 |
| 旧 rich-joint | A15 | 88.2 | 29.4 | 31.4 | 36.5 | **72.5** | **−17.6** | **[−33.3,−2.0]** | 1/10 |
| 旧 rich-joint | A17 | 88.2 | 29.4 | 35.3 | 36.6 | 52.9 | **−13.7** | **[−29.4,0.0]** | 2/9 |

关键解释：

1. **A14/A17 不具生产链迁移性。** 二者相对旧 A-raw 均为 2 gain / 9 loss；
   9 个 loss 中 4 个发生在 local champion 淘汰，5 个发生在 intergroup rank loss。
2. **A15 证明“更多 champion”不是恢复方案。** local champion recall 从 A-raw 的
   56.9% 提高到 72.5%，但 Top-2/local 从 86.2% 降至 43.2%；10 个 loss 中
   8 个发生于 intergroup。rich arbiter 面对更大的同 parent 候选集时竞争加剧。
3. **prior T=2 再次无效。** A17 与 A14 的 Top-2 逐格相同，Top-1 只额外丢
   `mb11_pancoast/r1`；故不保留 A17 主臂。
4. 运行中出现 local annotator repair exhaustion；协议按 fail-closed 计入生产端失败，
   不用统一端 ranking 回填。这是大而冗余 A-raw 候选池的运行可靠性成本。

由此冻结新的评估政策：

- **机制筛选层**：统一 replay 可用于定位单因子作用、生成假设，结果标记
  `mechanistic_only`，不得单独产生生产候选；
- **生产近似层**：凡在任一筛选表中被称为“有希望/P0/P1”的臂，必须在同树、同 Gold、
  同模型、同旧 rich-joint contract 下补测，并报告 paired case-cluster CI；
- **晋级层**：旧链也只是 surrogate；仍需合法 holdout、真实 Tier 3 签署以及最终生产
  shadow/在线验证。统一端与旧端冲突时，以生产近似层决定是否进入 holdout，而不是取较高者。

补测后，A14/A15/A17 独立臂全部退出主矩阵。A4+A14 仍保留，是因为它在**清洗后的 A4
树**上旧端点为 52.9%，而 A14 在冗余 A-raw 树上仅 35.3%；这说明收益来自
`clean tree × dynamic F4` 交互，不能把 A14 单因子结果跨树外推。研究主矩阵仍为
`{C-prod, A-raw, A4, A4+A14}`。

机器产物：

- `scripts/eval_l2_promising_downstream_legacy.py`
- `logs/l2_promising_downstream_legacy_v1/evaluation/{summary.json,summary.tsv,records.json}`
- `logs/l2_promising_downstream_legacy_v1/legacy_traces/{A14,A15,A17}/`

主要产物：

- `logs/l2_a_variant_matrix_v1/generation/manifest.json`
- `logs/l2_a_variant_matrix_v1/downstream_full/summary.json`
- `logs/l2_a_variant_api_calibration_v1/final_audit.json`
- `logs/l2_a_variant_api_calibration_v1/tier3_calibration_report.json`
- `logs/l2_a_variant_matrix_v1/judge/final_audit.json`
- `logs/l2_a_variant_matrix_v1/evaluation_tier3_proxy/evaluation/{summary,gates,combinations}.json`
- `logs/l2_a_variant_matrix_v1/evaluation/arm_performance_unified_reanalysis.{json,tsv}`
- `logs/l2_a_variant_matrix_v1/evaluation/arm_case_transitions_tier3_proxy.json`
- `logs/l2_a_variant_legacy_ab_v1/evaluation/{summary.json,summary.tsv,records.json}`
- `logs/l2_a_variant_legacy_ab_v1/evaluation/endpoint_gap_{analysis.json,arm_summary.tsv,case_cells.tsv}`
- `logs/l2_a4_downstream_combinations_v1/evaluation/{summary.json,summary.tsv,records.json}`
- `logs/l2_promising_downstream_legacy_v1/evaluation/{summary.json,summary.tsv,records.json}`
- `eval_fixtures/l2_a_variant_holdout_v1.json`

#### 10.21.10 A 变体 V2：可逆 reserve、单一预算与 hardened rich-joint

针对 v1 四类错误模式，v2 不再把“删除”作为默认纠错，并统一在 hardened rich-joint
下重跑全部对照：

| 错误模式 | v1 问题 | v2 纠正 |
|---|---|---|
| 去重后再 cap | A2 cap=5 后 A3 再硬截到 4 | A19 单一最终预算 B=4；溢出进 reserve |
| A1 任务漂移 | 全案 context 导致假阴性硬删 | A18 task-locked payload；仅高置信 invalid→reserve |
| local champion 瓶颈 | 盲目双 champion（A15）有害 | A22 低 margin 时最多 1 个 reserve challenger，仍单 champion |
| 技术失败假下滑 | 单 parent schema 失败整例归零 | 逐 parent prior fallback + arbiter 确定性降级 |

主矩阵 9 臂（17×3=459）：

`{C-prod-v2, A-raw-v2, A4-v2-ref, A4+A14-v2-ref, A18-parent-safe, A19-budget-safe, A20-generation-v2, A21-generation-v2+F4, A22-adaptive-local-rescue}`

评估政策：

1. 主终点 `resilient_legacy_actual_top2`；`strict_legacy` / 统一 direct 仅敏感性；
2. `cap_after_dedupe_hard_drop_rate` 必须为 0；
3. 禁止用统一 direct ranking 回填旧链；
4. 在 holdout≥80、校准过门、Tier3 真人签署前保持 `research_only`。

机器产物：

- `eval_fixtures/l2_a_variant_protocol_v2.json`
- `scripts/l2_a_variant_v2_transforms.py`
- `scripts/eval_l2_a_variant_v2_generation.py`
- `scripts/eval_l2_a_variant_v2_legacy.py`
- `scripts/analyze_l2_a_variant_v2.py`
- `scripts/analyze_l2_a_variant_v2_case_deep.py`
- `scripts/rebuild_l2_a_variant_v2_tier3_human_sim.py`
- `scripts/eval_l2_a_variant_endpoint_crossover_v2.py`
- `logs/l2_a_variant_matrix_v2/`
- `logs/l2_a_variant_legacy_ab_v2/`
- `logs/l2_a_variant_legacy_ab_v2/evaluation/case_deep/`
- `logs/l2_a_variant_endpoint_crossover_v2/crossover_plan.json`

**全量结果（2026-07-18，459/459）**：主终点 `resilient_legacy_actual_top2`。
漏斗：`logs/l2_a_variant_legacy_ab_v2/evaluation/v2_funnel_analysis.json`。
审计：`logs/l2_a_variant_matrix_v2/judge/`（Tier0–3；**human-sim** Tier3；
`research_only` / `promotion_eligible=false`）。权威对照表：
`logs/l2_a_variant_legacy_ab_v2/evaluation/case_deep/arm_performance_canonical_tier3_human_sim.{json,tsv}`。

**口径**：Top1/Top2/MRR/cov/local/oracle = 51 单元格池化均值（≡ 病例内 3-run
均值再平均）；质量列来自 `final_audit_human_sim`；排名仍按**冻结 gold** 计分。

##### 表 A：9 臂详细性能对照（含 Top1 与 Tier3 质量）

| arm | Top1% | Top2% | MRR% | actCov% | invCov% | local% | oracleT1% | oracleT2% | strictT2% | tech_fb% | act父有效%(T3) | inv父无效%(T3) | clean%(T3) | dupX%(T3) | Top2\|local% |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| C-prod-v2 | 37.3 | 51.0 | 46.6 | 76.5 | 76.5 | 64.7 | 64.7 | 76.5 | 51.0 | 0.0 | 98.9 | 1.1 | 54.2 | 7.6 | 78.8 |
| A-raw-v2 | 41.2 | 49.0 | 48.1 | 88.2 | 88.2 | 60.8 | 58.8 | 78.4 | 49.0 | 0.0 | 59.8 | 40.2 | 18.4 | 50.4 | 80.6 |
| A4-v2-ref | 27.5 | 49.0 | 39.5 | 80.4 | 80.4 | 52.9 | 47.1 | 66.7 | 49.0 | 0.0 | 86.2 | 13.8 | 74.1 | 6.3 | 92.6 |
| A4+A14-v2-ref | 33.3 | 47.1 | 41.5 | 80.4 | 80.4 | 51.0 | 54.9 | 66.7 | 47.1 | 0.0 | 86.2 | 13.8 | 74.1 | 6.3 | 92.3 |
| A18-parent-safe | 37.3 | 45.1 | 47.1 | 82.4 | 88.2 | 62.7 | 66.7 | 78.4 | 45.1 | 0.0 | 85.8 | 40.2 | 18.4 | 50.4 | 71.9 |
| A19-budget-safe | 25.5 | 33.3 | 33.8 | 86.3 | 88.2 | 47.1 | 56.9 | 68.6 | 33.3 | 0.0 | 69.9 | 40.2 | 18.4 | 50.4 | 70.8 |
| A20-generation-v2 | 39.2 | 47.1 | 47.5 | 82.4 | 88.2 | 60.8 | 64.7 | 78.4 | 47.1 | 0.0 | 90.2 | 40.2 | 18.4 | 50.4 | 77.4 |
| A21-generation-v2+F4 | 27.5 | 51.0 | 41.2 | 82.4 | 88.2 | 56.9 | 62.7 | 76.5 | 51.0 | 0.0 | 90.2 | 40.2 | 18.4 | 50.4 | 89.7 |
| A22-adaptive-local-rescue | 31.4 | 49.0 | 43.0 | 82.4 | 88.2 | 58.8 | 62.7 | 76.5 | 49.0 | 0.0 | 90.2 | 40.2 | 18.4 | 50.4 | 83.3 |

##### 表 B：相对 A-raw-v2 的 cell 净转移（gain−loss，n 格）

| arm | Top1 net | Top2 net | active-cov net | local-champion net |
|---|---:|---:|---:|---:|
| C-prod-v2 | −2 | +1 | −6 | +2 |
| A4-v2-ref | −7 | 0 | −4 | −4 |
| A4+A14-v2-ref | −4 | −1 | −4 | −5 |
| A18-parent-safe | −2 | −2 | −3 | +1 |
| A19-budget-safe | −8 | −8 | −1 | −7 |
| A20-generation-v2 | −1 | −1 | −3 | 0 |
| A21-generation-v2+F4 | −7 | +1 | −3 | −2 |
| A22-adaptive-local-rescue | −5 | 0 | −3 | −1 |

##### 表 C：Top2 漏斗 `loss_gate` 计数（每臂 51 格）

| arm | success | coverage_deleted | local_champion_elim | intergroup_rank_loss | rescue_g/l |
|---|---:|---:|---:|---:|---|
| C-prod-v2 | 26 | 12 | 6 | 7 | 0/0 |
| A-raw-v2 | 25 | 6 | 14 | 6 | 0/0 |
| A4-v2-ref | 25 | 10 | 14 | 2 | 0/0 |
| A4+A14-v2-ref | 24 | 10 | 15 | 2 | 0/0 |
| A18-parent-safe | 23 | 9 | 10 | 9 | 0/0 |
| A19-budget-safe | 17 | 7 | 20 | 7 | 0/0 |
| A20-generation-v2 | 24 | 9 | 11 | 7 | 0/0 |
| A21-generation-v2+F4 | 26 | 9 | 13 | 3 | 0/0 |
| A22-adaptive-local-rescue | 25 | 9 | 12 | 5 | 6/4 |

##### 表 D：冻结 gold vs Tier3 GoldMatch 覆盖（诊断；未重打 Top1/2）

| arm | frozen actCov% | Tier3 actCov% | Δpp | frozen invCov% | Tier3 invCov% | frozen Top命中且 T3 无 gold |
|---|---:|---:|---:|---:|---:|---:|
| C-prod-v2 | 76.5 | 76.5 | 0.0 | 76.5 | 76.5 | 3 |
| A-raw-v2 | 88.2 | 86.3 | −2.0 | 88.2 | 86.3 | 3 |
| A4-v2-ref | 80.4 | 74.5 | −5.9 | 80.4 | 74.5 | 3 |
| A4+A14-v2-ref | 80.4 | 74.5 | −5.9 | 80.4 | 74.5 | 2 |
| A18-parent-safe | 82.4 | 80.4 | −2.0 | 88.2 | 86.3 | 3 |
| A19-budget-safe | 86.3 | 84.3 | −2.0 | 88.2 | 86.3 | 3 |
| A20-generation-v2 | 82.4 | 80.4 | −2.0 | 88.2 | 86.3 | 3 |
| A21-generation-v2+F4 | 82.4 | 80.4 | −2.0 | 88.2 | 86.3 | 3 |
| A22-adaptive-local-rescue | 82.4 | 80.4 | −2.0 | 88.2 | 86.3 | 3 |

Tier3 GoldMatch 更严（裸 Epiglottitis / 裸 Hyperparathyroidism 等不算匹配），故多数臂
actCov 低约 2pp、A4 系约 −5.9pp；冻结 Top1/Top2 相对 Tier3 语义略乐观。

**案例级深挖（对齐旧 AB Top1/父有效率口径；Tier3 human-sim 已入质量表）**：
`scripts/analyze_l2_a_variant_v2_case_deep.py` +
`scripts/rebuild_l2_a_variant_v2_tier3_human_sim.py` →
`logs/l2_a_variant_legacy_ab_v2/evaluation/case_deep/`
（完整叙事 `V2_CASE_DEEP_TIER3_ARCHIVE.md`）。关键机制：

1. **A18**：task-locked gate 把 classification_axis 不等当成高置信 invalid；
   uncertain/fail-open 路径为 0；`mxh075`×3 gold 全进 reserve。
2. **A19**：hard-delete=0 成立，但**全局跨父** semantic_duplicate 把多父 gold
   champion 收进 inert reserve；20/20 LC elimination 仍有 active gold 却输掉
   local rank。
3. **A21**：条件 Top2↑，但 8/11 Top1 回退是 gold 仍在 champion 集内的 **rank 1→2**
  （F4×parent mass demotion），不是 champion 身份丢失。
4. **A22**：rescue 净 +2 Top1；`challenger_won` 仅 4/10 为 gold；多数触发
   `margin=0`。
5. **Tier3**：55 真分歧 human_sim 优先于 quality fixture（覆盖 13 项）；相对
   proxy 最终 15 字段变化；见上表 D。

中断修复：reserve-only parent 曾导致
`rescale_l2_scope` → `ValueError: one or more selected L1 parents have no L2 children`；
已在 `eval_l2_branch_generation_ab.py` 用 `_live_l2_parent_ids` /
`_oracle_scope_state` 跳过或仅对 oracle 临时 reopen。

### 10.22 B-reuse b1 双门控：父子门有效，旧重复门口径失真（2026-07-18）

为隔离 §10.19 的 B-reuse 局部收益与质量问题，本轮保持原 A/B/C 资产、C 树、B recall
asset、冻结 L1、oracle-parent F4 和带 L1 prior 的组间 arbiter 不变，只在拟新增
proposal 上做 2×2 消融。5 臂为 `C`、`ALL_B_b1`、`+SD`、`+PG`、`+PG→SD`；
17 病例 × 3 重复，共 255 个下游单元。PG payload 只含 parent axis 与 candidate；
仅高置信、task-adherent 的 invalid 被拒绝，其余 fail-open。SD 对整棵 C 树与所有
proposal 做 subtype-preserving 语义聚类，且从不删除 C 叶。

全量同跑结果：

- C：coverage **76.5%**，端到端 Top-1/Top-2/MRR **33.3/51.0/45.3%**；
- B-b1：coverage **82.4%**，Top-1/Top-2/MRR **35.3/56.9/49.2%**；
- B-b1+SD：**37.3/56.9/50.2%**；
- B-b1+PG：**35.3/56.9/49.2%**；
- B-b1+PG→SD：**37.3/56.9/50.2%**。

所有 B 臂相对 C 的 Top-2 增益均为 **+5.9 pp**，病例簇 bootstrap 95% CI
**[0.0, +17.6 pp]**；组合门没有增加 Top-2，只使 Top-1/MRR 相对 B-b1 增加
**2.0/1.0 pp**。`mxh014` 的 prosthetic-valve endocarditis 收益在 3/3 重复均保留；
旧实验的 `mb65_cml` 排名收益本轮未复现，说明它是错挂噪声造成的不稳定排序转移，
不能作为 guardrail。组合臂唯一可见排序修复是 `mb77_hyperpara` 一格从 rank 2
恢复 rank 1；全部 B 臂 `c_success_preservation=100%`。

质量方面，PG 将新增叶 parent-invalid 从 **45.8%** 降至 **23.5%**，组合臂为
**25.0%**；39 个盲化 proposal 上 PG precision/recall/specificity 为
**100/64/100%**。SD 的 proposal-pool 重复 precision/recall/specificity 为
**92.9/65.0/94.7%**，但只减少 1 个最终新增叶，未改善 Top-2。

本轮同时发现 §10.19 的“66.7% duplicate”不是最终树内同义叶率：旧 fixture 把
`Croup`、`volvulus`、`mesenteric ischemia` 等在**源候选池跨 parent 重复出现但最终
仅挂入一次**的 occurrence 也标为 duplicate，甚至把没有同义树叶的
`bronchiectasis`、`malignant hyperthermia` 标入。按新盲裁的“最终 emitted tree 中
仍存在真同义诊断”口径，C、B-b1 及全部门控臂均为 **0%**。因此结果同时保留：

1. `added_duplicate_rate`：旧 source-pool occurrence 口径，B-b1/SD/PG/PG→SD =
   **66.7/65.2/64.7/62.5%**，用于历史可比，所有臂仍正式不过门；
2. `final_tree_semantic_duplicate_rate`：最终树口径，全部为 **0%**，说明 SD 的原
   目标大部分已由 b1 分配器天然消解。

结论：**双门控不晋级**。PG 是真实有效的质量组件，但 recall 仅 64%，组合后仍有
25% 错挂；SD 主要清理未进入树的 source-pool 冗余，增加约 0.35 logical call/单元却
没有 Top-2 收益。下一步不应继续围绕旧 66.7% 数字调 prompt，而应先冻结两个不同的
重复指标，并把 PG 的剩余假阴性定位到 B asset→parent mapping/parent taxonomy；
之后再在新 holdout 验证 proposal-only PG，SD 仅保留为候选池卫生检查。

机器产物：

- `eval_fixtures/l2_targeted_gapfill_gates_protocol_v1.json`
- `scripts/eval_l2_targeted_gapfill_gates.py`
- `eval_fixtures/l2_targeted_gapfill_gates_gold_v1.json`
- `logs/l2_targeted_gapfill_gates_v1/evaluation/{summary.json,records.csv,component_analysis.json,case_transfers.json}`

### 10.23 B-reuse b1 全局 parent reassignment 与 L1×local 排名分解（2026-07-18）

本轮不扩大 recall pool、不增加叶 cap，也不实施新 gap-fill。输入固定为 §10.22 的
B-reuse b1 source pool；先按规范化疾病合并多 parent occurrence，再让每个候选一次
比较全部冻结 L1 parent，输出唯一 parent 或 `REJECT`。干预位于 per-parent selector
之前。四个竞争臂为 `B-b1`、`PG-reject`、`global-reassign`（GR）和 `GR→PG`；C 仅作
不参与胜负判定的参考。预注册按 actual Top-2、MRR、parent-invalid、coverage、成本
依次选最佳树，之后才冻结该树进行 2×2。

17 病例 × 3 重复的修复后主矩阵如下：

| 臂 | gold L2 coverage | actual Top-1 | actual Top-2 | MRR | 新增叶 parent-invalid |
|---|---:|---:|---:|---:|---:|
| C | 76.5% | 35.3% | 52.9% | 46.2% | 0.0% |
| B-b1 | 82.4% | 39.2% | 58.8% | 51.1% | 45.8% |
| PG-reject | 82.4% | 39.2% | 58.8% | 51.1% | 23.5% |
| GR | 88.2% | 37.3% | 58.8% | 52.5% | 3.3% |
| GR→PG | 88.2% | 37.3% | 58.8% | 52.5% | 2.2% |

GR 将 coverage 相对 C 提高 **11.8 pp**，并把错挂率从 B-b1 的 **45.8%** 降至
**3.3%**；串联 PG 后降至 **2.2%**。但 GR 没有增加 Top-2，Top-1 还比未重分配 B
低 **2.0 pp**。GR→PG 相对 C 的 Top-2 差为 **+5.9 pp**，病例簇 bootstrap 95% CI
**[-9.8, +23.5 pp]**，不能确认收益。按预注册字典序，`GR→PG` 因 Top-2 并列、MRR
较高且 parent-invalid 最低而成为后续研究用最佳树；它仍不满足 pilot 晋级门，不改
生产默认。

重复率在本轮正式拆为四个互不替代的量：

1. source-pool exact occurrence excess / occurrence = **48.9%**；
2. 属于重复 exact group 的 occurrence / occurrence = **69.4%**；
3. 盲化语义簇 excess / occurrence = **49.8%**；
4. emitted-tree 真同义新增叶 excess / emitted added leaves：B-b1/PG 为 **0%**，
   GR/GR→PG 为 **57.6/58.2%**。

因此 §10.22 的“最终树 0% 重复”不能外推到 GR：全局重分桶后，多个语义相近实体可在
同一新 parent 下通过 selector/allocator，重分配修好了 parent，却重新暴露了实体级
语义去重缺口。旧 `legacy_mixed_duplicate_rate` 只保留历史复现，不能代替以上任一
指标。当前最佳树是“按预注册性能字典序的研究最佳”，不是质量合格树。

在冻结 `GR→PG` 树上，四格统一使用同一 true-consumption F2、同一当前生产
legacy local builder 和 joint arbiter；gold 只在 Python 中改变 scope/champion 与
计分，不进入 LLM payload：

| L1 × local | Top-1 | Top-2 | MRR |
|---|---:|---:|---:|
| actual × actual（AA） | 35.3% | 58.8% | 51.5% |
| actual × oracle（AO） | 43.1% | 76.5% | 62.0% |
| oracle × actual（OA） | 66.7% | 66.7% | 68.6% |
| oracle × oracle（OO） | 84.3% | 84.3% | 84.3% |

Top-2 的 local-oracle 主效应为 **+17.6 pp**，L1-oracle 主效应为 **+7.8 pp**，
交互约为 0；Top-1 则以 L1 scope/prior 主效应 **+36.3 pp** 为主。AA 漏斗为
6 gold-absent、6 local-champion miss、2 technical failure、7 intergroup rank loss
和 30 success。actual 路径中 gold parent 已进入 route，因此这里的 L1 损失主要是
竞争 scope/prior，而非简单的 gold-parent 未召回。结论是：**Top-2 的首要可操作瓶颈
是 local champion，Top-1 的首要瓶颈是 L1 scope/prior；intergroup 仍有独立残差**。
AO 相对 AA 有 11 格 gain、2 格 loss；这两个回退在统一 legacy endpoint 下仍存在，
表示 oracle-local 改写 champion 集后可改变组间上下文，不能再归因于端点混用。

过程中修复了两项会扭曲归因的技术问题：

- 旧 global-C filter 会把 `Congenital Anomalies` 等宽泛 family/fallback 当成已经覆盖
  `Malrotation of the gut`。现改为只屏蔽与具体 C L2 叶 canonical exact match 的候选；
  修复后 `mxh045` 的 gold 候选进入 B1，但 2/3 被 allocation cap 阻断、1/3 被
  post-GR selector 淘汰，不再误归因为 C 已覆盖。
- 早期 2×2 把 AA 与其他格置于不同 arbiter 版本。最终四格全部重跑同一生产 legacy
  endpoint；V2 混用产生的转移不纳入最终结论。

三个预指定 residual cluster 的最终 lineage：`mb34_leukemoid` 3/3 由映射修复；
`mxh045` 为 selector/allocation 瓶颈；`mxh068` 3/3 在冻结 recall asset 中完全缺失。
下一轮 gap-fill 只允许针对 `mxh068` 类 `recall_asset_absent`，不得以修复后两类问题为
理由扩大全树候选池。

机器产物：

- `eval_fixtures/l2_targeted_gapfill_global_reassign_protocol_v1.json`
- `src/agentclinic_tree_dx/prompts/l2_gapfill_global_parent_reassign.txt`
- `scripts/eval_l2_targeted_gapfill_global_reassign.py`
- `scripts/eval_l2_l1_local_crossover.py`
- `scripts/analyze_l2_gr_and_crossover_losses.py`
- `logs/l2_targeted_gapfill_global_reassign_v1/evaluation/`
- `logs/l2_l1_local_crossover_v1/evaluation/`

### 10.24 关系感知 L2→MCQ 离线投影：Typed LLM 与分歧触发 RAG（2026-07-19）

本轮只接入冻结 A 与 `ALL_B_b1` 测试流水线，不修改 `controller.py`、
`config.py`、生产 `AnswerMapper` 或上游树生成。冻结输入为 TALP17×3、既有 joint
ranking 和原始 L2 树；mapper 运行时只看题干、问题、全部 options、L2
ID/label/parent/rank/posterior 及公开检索片段。`gold`、gold option/letter、
`acceptable_l2` 与评测 alias 仅在 projection 完成后用于计分。

实现的投影顺序为：

1. `DiseaseNameResolver` 用 mechanism map、disease bridge 与 docLogica/UMLS 做
   gold-blind 实体规范化；
2. 约束 LLM 先判断题目目标，再输出方向固定的
   `equivalent/subtype/etiology/mechanism/manifestation/...` 关系；
3. canonical exact 与 LLM 语义同义叶构成跨 parent clone closure；
4. option 支持取 clone 中 `min(finite rank)` 与 `max(posterior/support)`，绝不累加
   clone mass；
5. 未匹配、低置信或 deterministic/LLM 分歧时，以
   `question_target + option + candidate leaves` 查询冻结 rag/cpg index，再由
   falsification critic 裁决。

102 单元完整结果（Top-1 / Top-2 / MRR）：

- A：historical oracle-assisted `54.9/62.7/59.5%`；deterministic gold-blind
  `17.6/27.5/23.2%`；typed `35.3/41.2/38.2%`；typed+RAG
  `35.3/43.1/39.2%`。
- B-b1：historical oracle-assisted `37.3/60.8/50.3%`；deterministic
  `21.6/43.1/32.4%`；typed `37.3/51.0/46.4%`；typed+RAG
  `39.2/56.9/50.5%`。

`historical_oracle_assisted` 明确包含 v1 gold-diagnosis alias，只保留为历史上界式参考，
不能作为 gold-blind 对照。相对合法 deterministic 基线，typed+RAG 在 A 提高
`+17.6/+15.7/+16.0 pp`，病例簇 bootstrap 95% CI 分别为
`[+5.9,+31.4] / [+2.0,+31.4] / [+2.9,+30.7]`；B-b1 提高
`+17.6/+13.7/+18.1 pp`，CI 为 `[0,+35.3] / [-9.8,+35.3] /
[-0.7,+37.6]`。B 的 Top-2/MRR 仍未排除零效应。

RAG 相对 typed no-RAG 的独立增量为：

- A：Top-1 `+0`、Top-2 `+2.0 pp`、MRR `+1.0 pp`；Top-2 1 gain / 0 loss；
- B-b1：Top-1 `+2.0 pp`、Top-2 `+5.9 pp`、MRR `+4.1 pp`；Top-1
  1 gain / 0 loss，Top-2 3 gains / 0 loss。

相应 paired cluster bootstrap 区间下界均为 0，说明本样本内没有 RAG-induced
option hit 回退，但增量由极少数单元构成。触发也不稀疏：102 单元中 100 个产生
RAG trace、99 个实际调用 critic，合计 1056 次 index query、3168 snippets；
10 个 critic trace 为部分 fail-open。因此当前机制实质上接近“relation-level
常开 RAG”，成本门尚未通过。

技术审计发现并修复两项会造成错误结论的问题：

- all-unmatched option 集原先会因 dense rank 的 fallback 值错误记为 Top-1；现要求
  gold 必须有 finite L2 rank 才能计 Top-1/Top-2/MRR。
- `mxh045` 一次 typed 响应在 schema repair 后仍含非法 clone groups，早期会级联终止
  整个矩阵；现严格丢弃非法 clone group 并审计，transport/schema repair 耗尽时使用
  deterministic gold-blind fail-open，RAG 臂再把全部 options 送 critic。最终 unique
  typed 技术 fail-open 为 1 单元；两 mapper 臂按 trace 计为 2 次，另有 6 个被丢弃的
  clone-group occurrence、12 次 schema-repair trace。

关系 precision/recall 的 v2 fixture 是把既有 A 臂人工 correction/acceptance 转录成
不含 gold letter 的语义表，`human_signed_off=false`；B 只做跨树标签迁移。因此这些
关系指标可用于错误定位，不能视作新的双臂真人金标。尤其 B-b1 typed+RAG 的 relation
precision/recall `38.7/35.1%` 同时受 fixture transfer 与真实 over-binding 影响。

采用裁决：typed+RAG 是本轮最佳 gold-blind mapper，且 RAG 相对 typed 无 hit
回退；但它相对 deterministic 仍有 A/B Top-2 各 1/3 个 loss，相对含泄漏的 historical
A 下降 `19.6/19.6 pp`，并且 RAG 触发近乎常开。故保留
`typed_llm_disagreement_rag` 为 **A/B-b1 research candidate**，不把它升级为唯一
canonical 离线 mapper；historical 只读保留，下一步需真人签署双臂 relation fixture
和更严格的 case-level RAG trigger。生产端保持完全不变。

机器产物：

- `eval_fixtures/l2_relation_answer_mapper_protocol_v1.json`
- `eval_fixtures/l2_relation_answer_mapper_adjudication_v2.json`
- `src/agentclinic_tree_dx/answer_projection_mapper.py`
- `src/agentclinic_tree_dx/prompts/answer_relation_{mapper,rag_critic}.txt`
- `scripts/eval_l2_relation_answer_mapper.py`
- `scripts/analyze_l2_mcq_option_from_ranking.py`
- `logs/l2_mcq_mapper_v2/{summary,records,bootstrap,paired_comparisons}.json`
