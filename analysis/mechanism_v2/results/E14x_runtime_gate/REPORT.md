# E14x：MOSAIC 第四调用门控的轨迹级效用解剖

## 判定

E14x **不支持把现有 `unexplained_spans ≥ 2 AND low margin` 规则作为 RCR 的默认第四调用门控**。RCR-3 应保持默认三调用；旧门控关闭。这个判定不是因为“第四调用绝不可能有用”，而是因为现有门控检测的是“生成文本中尚未被自身候选解释的 span 数”，它与真正缺失的诊断对象或候选间决定性关系没有形成可靠耦合。

严格版 Adaptive-4v2 在 300 例中触发 90 次（30%），比 Lite 多用 90 calls。A1 共生成 270 个候选，其中 135 个按冻结实体桥属于 G1/G2 未见的新实体，分布在 78/90 个触发病例；这些新实体全部进入 append-only registry 和最终 frontier，11 例最终由 A1 新实体夺冠。也就是说，调用、实体新增、存活和 selector 暴露都真实发生了，不能把零收益归因于“调用没执行”或“候选被提前剪掉”。

问题发生在**新增对象的临床方向和最终转化**：135 个新实体没有一个 `safe-exact` 命中冻结 reference，90 个触发病例的 `safe-exact` top-1 为 Lite 7、Adaptive 7，gain/harm 都是 0。根代理进一步复核全部 34 个触发后 champion 改变的病例，得到 6 个观察到的临床 repair、15 个 harm、13 个 neutral；A1 信息角色为 4 个 decisive、22 个 distractor、6 个 merge-only、2 个 redundant。`safe-exact` 分数的“完全不变”因此也不能解释为临床中性：它同时漏记了同义/范围修复与大量错误吸引域变化。

历史日志不能识别第四调用的因果效应。300/300 个 Lite↔Adaptive-4v2 配对病例的 G1/G2 JSON 都不完全相同，只有 27 个 `state_after_g` 恰好相同；即使温度为零，fresh provider calls 仍产生不同候选、证据和措辞。Adaptive-4v2 还在 39 个未触发病例改用 A5 pairwise selector。所以下文的 repair/harm 是**完整历史轨迹的观察方向**，不是 A1 的随机化处理效应。这个识别失败本身是 E14x 的关键结论：旧日志足以否定“已有证据支持上线”，不足以估计 Call-4 的净因果系数。

## 设计与诚实的推断边界

E14x 在读取病例级 outcome join 前冻结了回顾性分析合同，随后连接三个共同 100 例切片：DiagnosisArena seq100、MCR v1 和 MCR v2。主比较是历史 `mosaic_lite_v1` 与严格门控 `mosaic_adaptive4v2_v1`；次比较只诊断早期 permissive `adaptive4_v1` 为什么被替换，不与主比较合并。

逐病例计算 G1、G2、post-G state 的 canonical JSON hash，并预先规定只有 G1/G2 完全一致时才可能作近似 treatment-like 解读。实际为 0/300，故全部 paired accuracy、bootstrap CI、McNemar p 和 gate signal scan 都降级为探索性描述。没有为了制造相同上游而重复调用：这遵守了本轮排除“重复多次运行/纯降方差控制”的约束。

概念命中由 `FrozenExactSynonymBridge` 的 exact/frozen-safe-synonym 比较实现，统一展示为 **`safe-exact`（历史结果字段 `strict`）**。它是 mapper 前保守身份下界，不是 clinical-complete 或 DA task/mapper 正确率；E14x 没有移植 E2 full-800 的任何审计数值。当前 `analysis_summary.json` 已在产物边界把历史 `strict` 别名迁移为 `safe_exact`，并把 `da_option_projection` 的对应计数独立改为 `*_task_*`；旧 pre-manual/permissive 文件只作 frozen provenance，不得由下游直接摄取。

端点沿完整漏斗分解：触发与 call 成本 → A1 新实体 → registry 存活 → frontier 暴露 → 新实体夺冠 → `safe-exact` reference → DA mapper。全部 9 个 `safe-exact` flip、11 个 A1 新实体夺冠、18 个 DA option flip，以及后来补入的全部 34 个 triggered champion flip，都进入根代理人工队列；类别重叠后为 56/300 个唯一病例逐案审计。没有外部 LLM 参与这些临床判定，也没有 proxy 补全临床端点；其余 244 例没有 complete/partial/no 根裁决，未入队的 `safe-exact` 阴性只能记作“临床未审”，不能当作人工或 proxy-negative gold。因此 6 repair/15 harm/13 neutral 仅描述 34 个 triggered-flip 富集子集，不是 300 例临床发生率。

## 新增实体很多，但没有对准缺失诊断

严格门控把 90 calls 投向的 pre-gate 病例确实表现为“未解释多”：平均 unexplained 3.72，median 4；平均 top margin 0.259，40/90 有跨视图 top-1 不一致。但这些信号并不告诉调用“缺的是哪种诊断对象、哪个病因—表现关系或哪个亚型限定”。A1 prompt 只接收 vignette 和最多六个 unexplained spans，因此容易把未解释观察重新命名成：

- 症状/后果：`Hypotension`、`Hypoxemic Respiratory Failure`、`Strabismus`；
- 宽泛上位类：`Cardiac Conduction Disease`、`Metastatic disease to the liver`；
- 与高显著局部证据相容但偏离目标的 mimic：`Adult-onset Still's disease`、`Ovarian fibroma`、`Giant Cell Tumor`、`NMOSD`；
- 已有错误锚的更具体版本：`Liver adenoma with hemorrhage`、`Pacemaker pocket infection with biofilm formation`。

因此，append-only memory 和 protected frontier 只解决“新对象会不会消失”，没有解决“新对象是否处于正确诊断粒度、是否覆盖整条病例关系、是否只是 manifestation”。78 个含新实体病例全部存活/暴露，反而证明瓶颈不在 pruning，而在 **gate target specification + candidate typing + contrast ranking**。

冻结 `safe-exact` bridge 报告 0 个 reference discovery，但人工复核找到少量真实价值，说明该身份下界还存在另一层盲区：

- ipilimumab-induced dermatitis/myositis 临床上表达了 reference 的 drug-induced dermatomyositis；
- urethral amyloidosis 在系统评估阴性时就是 localized urethral amyloidosis；
- metastatic melanoma to liver 加“无已知原发”的 rationale 覆盖 unknown-primary reference；
- maculopapular drug eruption 是 morbilliform drug eruption 的普通临床同义表达；
- A1 对已有 ureteral-polyp 对象的重复合并，帮助 selector 从 leiomyoma 转成正确的 ureteral fibroepithelial polyp。

这些 repair 不是恢复旧门控的理由。它们说明未来评估必须同时报告 `safe-exact` identity 与根审计的 clinical complete/partial/no，并且 Call-4 若存在，应寻找“缺失诊断对象或关系”，而不是任意 unexplained span。

## 15 个 harm 的共同机理

34 个 triggered champion flips 中，15 个被判为观察 harm，明显多于 6 个 repair。典型轨迹揭示四类机制。

第一类是**局部高显著特征覆盖关系整体**。anti-MDA5 clinically amyopathic dermatomyositis 被高 ferritin 拉到 adult-onset Still disease；histiocytoid Sweet syndrome 被 MPO-positive histiocytoid cells 拉到 leukemia cutis。A1 找到一个能解释局部 span 的候选，却没有检查它能否解释病例的完整时序、阴性证据和器官组合。

第二类是**把 manifestation 当 diagnosis**。Accessory extraocular muscle 被改成 Strabismus；septic trajectory 中 A1 生成 hypotension/respiratory failure；这些词能复述观察，却没有成为与 benchmark/reference 同层的完整诊断对象。

第三类是**强化初始报告或预备诊断锚**。Choriocarcinoma 病例的旧活检写“adenoma”，A1 进一步生成 liver adenoma with hemorrhage 并夺冠；pyoderma gangrenosum 病例因表面培养出 `S. epidermidis`，A1 再增加 sepsis/endocarditis，强化了在抗生素下仍进展的错误感染故事。

第四类是**宽池产生新的可选 mimic，而 comparator 缺少候选对反证**。Massive ovarian edema→ovarian fibroma、angioleiomyoma→giant-cell tumor、paraneoplastic encephalomyelitis→NMOSD 都属于此类。A1 不是没有多样性，而是多样性没有被“为什么 A 而不是 B、哪条决定性关系必须成立”约束。

13 个 neutral 也不等于成功。许多病例两臂都错，A1 只改变错误标签；另一些只是宽泛 scope 互换。它们占用调用却没有降低诊断不确定性。

## permissive gate 解释了为什么“少触发”仍不够

旧 Adaptive-4 在 DA/MCR 200 例中触发 169 次（84.5%），相对 Lite 多 169 calls。`safe-exact` top-1 为 19→14（−2.5 pp）；在被触发的 169 例中为 16→10，0 gain/6 harm，历史配对 McNemar `p=0.03125`，bootstrap 95% CI `[−6.51,−1.18] pp`。但它同样几乎没有可比上游：仅 1/200 的 G1/G2 完全一致，所以这些数字只能说明“大范围额外生成没有留下值得信赖的正证据”，不能给出因果伤害量。

严格 v2 把触发率从 84.5% 降到 30%，避免了多数无差别调用，却没有让触发对象更贴近 reference。它优化的是调用频率，不是 gate 的语义靶点。结果支持“旧 permissive gate 应淘汰”，不支持“把同一信号阈值调严就得到有效 gate”。

## 非触发病例与 A5：不能把所有 Adaptive 变化归给门控

210 个未触发病例仍有 59 个 champion flip；`safe-exact` top-1 为 27→24（3 gain/6 harm，−1.43 pp，95% CI `[−4.29,+1.43] pp`）。其中 39 例走 A5 pairwise，其他病例也有 fresh G1/G2/selector 差异。9 个 non-trigger `safe-exact` flips 经人工复核为 Adaptive better 3、Lite better 5、临床同义 1。

例如，A5 将 EBP 退化为 broader dystrophic EB，将 fibrous dysplasia 改成 orbital meningioma，将 schwannoma 改成 neurofibroma；另一些 fresh trajectories 则把 factitious disorder 修成 malingering、NF1 修成 cysticercosis。它们说明 selector policy 与上游采样本身有大幅 churn。任何后续 Call-4 实验都必须固定上游 registry/evidence 和 comparator，才能把“是否调用”与“调用后如何比较”分开。

## DA mapper 是独立噪声与范围变换机制

DA 100 例的 option@1 总数两臂都是 63，但有 9/9 相反方向 flip。18 个 option flip 中 8 个连 champion 文本都相同；人工判断 8 个属于 projection-only 或临床等价变化，另有 4 次 mapper 把临床错误的 Adaptive champion 标为正确。

代表性反例包括：同一个 OAVRT champion 一次映对、一次映错；同一个 lamellar macular hole、graft occlusion、DLBCL champion也发生相反映射；错误的 Adult-onset Still disease 和 ARVC 又被映到 gold option。因而 task projection 不能作为 gate 的 concept utility 代理。RCR-3 必须继续同时报告 pre-mapper diagnosis、clinical scope 和 task projection，并把 mapper rescue/harm 单列。

## 不能从本批数据选择新阈值

预注册的 signal 分析检查 unexplained count、Jaccard、margin、top-1 disagreement、leave-one-view instability 与 contradiction mass。严格触发层没有任何 `safe-exact` gain/harm，所以任意阈值的 `safe-exact` net 都为零；人工 clinical outcome 又只在机制富集 flip 队列上可见。对这些 outcome 再搜索阈值会是明显的标签泄漏。

因此 E14x 没有输出“更好的 0.4/0.6 margin 阈值”。需要的不是调参，而是重定义 gate state：

1. 先用类型化 event skeleton 判断是否缺少完整诊断对象、病因—表现关系、时间/范围限定或候选对 discriminator；
2. 排除纯 manifestation、检查结果复述和已有候选的无信息同义改写；
3. 若调用，要求新候选绑定原文 span、诊断层级、时间/对象/极性，以及相对当前 top pair 的可证伪差异；
4. 新候选进入安全 registry 后，必须由同一个 time/scope-aware comparator 与旧候选对称比较，而不是因“晚到”或“解释了未解释 span”获得隐式加权；
5. 只有在另一个固定上游、固定 comparator 的受控队列中证实净收益，Call-4 才可重新开启。

## 对 RCR-3 的直接约束

- 默认预算固定为三调用：Call 1 生成关系型事件骨架，Call 2 生成类型化候选与安全实体聚合，Call 3 做时间/范围感知的候选对比排序。
- 不把 `unexplained_n`、低 margin 或视图 disagreement 单独视为额外调用许可；它们最多是低置信度标志。
- 默认禁用 A1/Call-4；实现中若保留实验入口，必须由环境参数显式开启并记录 gate reason、target relation、候选粒度和 call telemetry。
- comparator 对后到候选不设 novelty bonus；证据按命题和特异度计一次，不按视图数、span 数或重复支持投票。
- `safe-exact` identity 与 clinical complete/partial/no 并行；特别修复 hyphen、普通同义与 scope 分层，但不得退回 substring 合并。
- mapper 与 concept 分离；option@1 不能为错误 concept 提供“门控成功”的叙事。

后续 Call-4 的可证伪设计必须逐例复用完全相同的上游 skeleton、registry、evidence 与 comparator，只随机/确定性切换是否加入 A1；预注册主要端点应是 root-audited clinical-complete repair/harm 和缺失对象命中，而非 unexplained span 数。若 typed gate 仍主要生成 manifestation/mimic，或新增 complete gain 不超过 interference loss，即使 `safe-exact` 不变也应继续关闭；反之，只有在固定上游下出现可追溯的新对象并稳定转化，才构成重新开启的正证据。

E14x 是开发日志上的回顾性机制实验，不是确认性能试验。它足以拒绝“现有历史结果已经证明第四调用门控有用”，也足以定位失败链条在 gate target、候选类型和 comparator，而不是 registry 存活；它没有证明所有未来的关系感知 Call-4 都无效。
