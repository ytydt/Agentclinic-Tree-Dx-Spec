# MOSAIC 扩集报告（统一 DA400 / MCR400；五端点纠正版）

依据：`PROMISING_POST_AUDIT_ALGORITHM_CANDIDATES.md`  
实现：`src/agentclinic_tree_dx/mosaic.py`  
模型：`meta-llama/llama-3.3-70b-instruct`  
原始实验日期：2026-08-08

纠正版机器可读全表：`analysis/backbone_v1/mosaic_eval/leaderboard_400_v2.json`
历史数值与原始配对检验血缘：`analysis/backbone_v1/mosaic_eval/leaderboard_400.json`

---

## 0. 报告口径与端点优先级

| 端点 | 定义与用途 |
|------|------------|
| **clinical-complete（主指标）** | 经 root adjudication 判定与题目所要求的**完整诊断对象**临床等价；用于衡量真实诊断能力 |
| partial（次指标） | 临床兼容的父类、组成部分或欠特异对象；有诊断效用，但不算完整答对 |
| safe-exact（保守下界） | exact 或冻结的安全同义词命中；高特异、低敏感，不能单独代表临床能力 |
| task（接口指标） | DA 为 option mapper；MCR 为缓存的 semantic judge。两族判分合约不同，必须分开报告，不合并为总分 |
| historical legacy-chain（历史血缘） | 旧报告的 `Concept` 字段。它是方法依赖的历史命中合约，**既不是 strict，也不是共同的临床估计量** |
| unified legacy-chain（诊断用回放） | 对 pre-projection champion 统一应用 substring/resolver；只用于解释历史合约差异，不承担主指标角色 |

评价单元始终为 **DA400** 与 **MCR400**，各自 `n=400`；不混用 seq100、heldout、200b 或 pooled200。入表方法为 Lite、Forest、IMPC、B07、MAC(B06)、e7、v0、I1(e7-S4a)。Adaptive-4 / Adaptive-4v2、B01、APHHM、I2/I3/I5 及未完整评分的 I4 不入这张完整 800 题历史表。

### 为什么旧 `Concept` 必须重命名

- 运行臂的历史列对最终 champion 使用 `dc.match`，核心是归一化后 equality / 双向 substring / resolver 命中。
- B06/MAC 的历史列却是 **supervisor stage hit**；B07 是 **diagnose stage hit**。它们允许中间阶段或同一字段中的其他诊断命中，未必等于最终 champion。
- 因而旧列只能称为 **historical legacy-chain**。尤其 B06/B07 与运行臂的跨方法 McNemar 检验混合了 stage-hit 与 champion-hit 合约，不能解释为临床完整正确率差异。
- v2 统一 champion 回放验证了这个差异：B07 的 DA/MCR 历史值 `0.2625/0.2825` 变为统一 champion legacy-chain `0.2125/0.2125`；MAC 的 `0.3300/0.3150` 变为 `0.2450/0.2400`。其余可比臂历史值与统一回放零不一致，task 也零不一致。

---

## 1. 历史主表（原始数值血缘；不可作临床主排名）

| 方法 | 约 calls | DA task | DA historical legacy-chain | MCR task | MCR historical legacy-chain |
|------|--------:|--------:|---------------------------:|---------:|----------------------------:|
| **Forest** | 4.03 | **0.6375** | 0.2800 | 0.2650 | 0.2525 |
| IMPC | 4.00 | 0.6250 | 0.2925 | 0.2425 | 0.2375 |
| B07 | 3 | 0.6150 | 0.2625 | 0.2650 | 0.2825 |
| MAC (B06) | ≫4† | 0.6150 | **0.3300** | **0.2750** | **0.3150** |
| Lite | 3.00 | 0.6025 | 0.2575 | 0.2550 | 0.2175 |
| e7 | 6 | 0.5700 | 0.2025 | 0.2625 | 0.2025 |
| v0 | 4 | 0.5525 | 0.1750 | 0.2500 | 0.2125 |
| I1 (e7-S4a) | 3 | 0.5450 | 0.2025 | 0.2250 | 0.2025 |

† MAC 为多轮讨论式多代理，预算高于 Forest；这里只保留历史性能血缘，并非严格等预算比较。
本表沿用原始排序与数值，但 `historical legacy-chain` 的粗体不表示临床领先。

---

## 2. 七个重叠臂的统一五端点回放

### 2.1 DA400

| 方法 | safe-exact | unified legacy-chain | clinical-complete | partial | task |
|------|-----------:|---------------------:|------------------:|--------:|-----:|
| Lite | 0.0125 | 0.2575 | **0.0400** | **0.5375** | 0.6025 |
| Forest | 0.0050 | 0.2800 | 0.0350 | 0.5325 | **0.6375** |
| IMPC | 0.0125 | 0.2925 | 0.0325 | 0.5275 | 0.6250 |
| B07 | 0.0100 | 0.2125 | 0.0300 | 0.5350 | 0.6150 |
| MAC (B06) | 0.0000 | 0.2450 | 0.0225 | 0.5350 | 0.6150 |
| e7 | 0.0100 | 0.2025 | 0.0375 | 0.4875 | 0.5700 |
| v0 | 0.0025 | 0.1750 | 0.0225 | 0.4750 | 0.5525 |

### 2.2 MCR400

| 方法 | safe-exact | unified legacy-chain | clinical-complete | partial | task |
|------|-----------:|---------------------:|------------------:|--------:|-----:|
| Lite | 0.1450 | 0.2175 | 0.2250 | 0.1375 | 0.2550 |
| Forest | **0.1600** | 0.2525 | 0.2325 | 0.1650 | 0.2650 |
| IMPC | 0.1575 | 0.2375 | 0.2125 | 0.1600 | 0.2425 |
| B07 | 0.1325 | 0.2125 | 0.2225 | **0.1700** | 0.2650 |
| MAC (B06) | 0.1550 | 0.2400 | 0.2400 | 0.1650 | **0.2750** |
| e7 | 0.1375 | 0.2025 | **0.2450** | 0.1100 | 0.2625 |
| v0 | 0.1475 | 0.2125 | 0.2350 | 0.1425 | 0.2500 |

I1 只有历史 task（DA `0.5450`；MCR `0.2250`）与 historical legacy-chain（两族均 `0.2025`）。其 safe-exact、clinical-complete、partial 为 **null（未进行穷尽 root adjudication）**，不是 0，也不能据此认定临床阴性。

### 2.3 临床与接口读数为何分家

- DA 的 task 为 option mapper：一个父类、组成部分或较宽的临床对象可能仍映射到正确选项。因此 DA task 为 `0.5525–0.6375`，而 clinical-complete 仅 `0.0225–0.0400`；这主要暴露“候选到选项”的接口放大，不是模型已完整说出诊断对象。
- DA 的 partial 高达 `0.4750–0.5375`，说明不少轨迹到达了正确临床邻域，却停在父类/组成部分/欠特异层级。改进靶点应是对象完整性和最终投影，而不只是继续提高 mapper 命中。
- MCR 的 task（`0.2425–0.2750`）更接近 clinical-complete（`0.2125–0.2450`），但它仍来自另一个语义 judge，不能与 DA task 合并，也不能替代 root adjudication。
- 点估计排序不稳定：DA clinical-complete 由 Lite 最高，MCR 则由 e7 最高；MAC 的历史 legacy-chain 领先并未转化为 DA clinical-complete 领先。这正是旧 `Concept` 过强结论必须撤回的原因。

---

## 3. 配对推断：临床主指标与历史血缘分层

### 3.1 clinical-complete（主推断）

最终统计合同分别冻结 overall、DA、MCR 三个相干十对比家族；overall 无显著项（最小 `q=.070843`），MCR 中完整九臂的 Collapse3c 相对 IMPC 为 +5.50pp、`q=.045615`。ALL/DA/MCR 混合 30-row 校正仅作保守敏感性（该对比 `q=.136846`）；DA–MCR 交互经十对比 Holm 后为 `q=.228489`，不支持跨 benchmark 的普适胜者。Collapse3c 又不在本报告七个历史重叠臂内，因此：

1. 七个重叠臂在本次完整临床对象命中上**没有得到经多重校正支持的胜者**。
2. Forest 的 DA task 领先、MAC 的旧 stage-hit 较高、e7 的 MCR clinical-complete 点估计最高，分别描述不同机制，不能拼成单一“总体最优”。
3. 点估计可用于提出机制假设，但不足以宣告骨干间临床优越性。

### 3.2 原始配对检验（相对 Forest；仅保留历史血缘）

| 方法 | DA task | DA historical legacy-chain | MCR task | MCR historical legacy-chain |
|------|---------|----------------------------|----------|-----------------------------|
| Lite | 31–45，p=0.135 | 19–28，p=0.243 | 15–19，p=0.608 | 8–22，p=0.016 |
| IMPC | 34–39，p=0.640 | 20–15，p=0.500 | 13–22，p=0.176 | 15–21，p=0.405 |
| B07 | 41–50，p=0.402 | 30–37，p=0.464 | 22–22，p=1.000 | 33–21，p=0.134 |
| MAC | 38–47，p=0.386 | 36–16，p=0.008 | 24–20，p=0.652 | 34–9，p=0.0002 |
| e7 | 46–73，p=0.017 | 20–51，p=0.0003 | 25–26，p=1.000 | 14–34，p=0.006 |
| v0 | 44–78，p=0.003 | 19–61，p<0.001 | 24–30，p=0.497 | 20–36，p=0.044 |
| I1 | 43–80，p=0.001 | 17–48，p=0.0002 | 15–31，p=0.026 | 14–34，p=0.006 |

记法：第一数字为该方法独赢，第二数字为 Forest 独赢；均为原报告未经本节重新定义的 exact McNemar 结果。task 的比较只在 DA 或 MCR 各自内部成立。historical legacy-chain 的 p 值只回答各自历史命中合约下的差异；涉及 B06/B07 时并非共同 endpoint，尤其不能写成“MAC/B07 临床显著更好”。

### 3.3 其他原始关键对照（同为历史血缘）

| 对比 | DA task | DA historical legacy-chain | MCR task | MCR historical legacy-chain |
|------|---------|----------------------------|----------|-----------------------------|
| Lite vs B07 | 52–57，p=0.702 | 32–34，p=0.902 | 28–32，p=0.699 | 18–44，p=0.001 |
| Lite vs MAC | 43–48，p=0.675 | 16–45，p=0.0003 | 19–27，p=0.302 | 8–47，p<0.001 |
| Lite vs e7 | 60–47，p=0.246 | 45–23，p=0.010 | 28–31，p=0.795 | 30–24，p=0.497 |
| IMPC vs Lite | 43–34，p=0.362 | 32–18，p=0.065 | 19–24，p=0.542 | 26–18，p=0.291 |
| IMPC vs B07 | 51–47，p=0.762 | 44–32，p=0.207 | 22–31，p=0.272 | 22–40，p=0.030 |
| IMPC vs MAC | 48–44，p=0.755 | 18–33，p=0.049 | 15–28，p=0.066 | 11–42，p<0.001 |
| Forest vs B07 | 50–41，p=0.402 | 37–30，p=0.464 | 22–22，p=1.000 | 21–33，p=0.134 |
| Forest vs MAC | 47–38，p=0.386 | 16–36，p=0.008 | 20–24，p=0.652 | 9–34，p=0.0002 |

全部原始两两结果仍见 `leaderboard_400.json` → `mcnemar_all_pairs`。这些数字被保留用于审计血缘，不能覆盖 v2 的临床主推断。

---

## 4. 机制指标（仅 MOSAIC，DA400）

| 方法 | mean calls | G 间 Jaccard | exact dup max | history leak |
|------|-----------:|-------------:|--------------:|-------------:|
| Lite | 3.00 | 0.309 | 0 | 0 |
| Forest | 4.03 | 0.416 | 0 | 0 |
| IMPC | 4.00 | 0.481 | 0 | 0 |

三臂均远低于历史 MAC echo（Jaccard≈0.97），说明其候选生成更具分歧且未观察到 exact duplication/history leak；但“更分歧”只是结构性质，并不自动推出 clinical-complete 更高。Forest/IMPC 的额外调用可能扩展候选覆盖，DA mapper 可从中获益；若最终 champion 仍欠特异或只保留组成部分，临床完整命中不会同步提高。当前 DA 的高 partial、低 clinical-complete 正与这一瓶颈一致。

---

## 5. 纠正后的跨臂结论

1. **真实诊断能力以 clinical-complete 为主。** 七个重叠臂没有经多重校正支持的临床胜者；不能再从旧 `Concept` 写出 Forest 优于 e7/Lite，或 MAC 优于 Forest。
2. **Forest 的强项是 DA 接口表现而非已证实的临床完整性。** 它的 DA task 为 `0.6375`，但 clinical-complete 为 `0.0350`，大量收益位于 partial→option 的映射通道。
3. **Lite 是预算锚点。** 其 DA clinical-complete 点估计最高（`0.0400`），MCR 为 `0.2250`；现有证据支持保留 3-call 对照，但不支持宣称其临床更优。
4. **IMPC 是机制隔离臂。** 它有最高的 MOSAIC 内 G 间 Jaccard（`0.481`），却未形成 clinical-complete 优势，提示增加候选视角的边际价值受最终对象聚合/特异化约束。
5. **MAC/B07 的旧优势主要需按 stage-hit 合约解读。** 统一 champion 回放后其 legacy-chain 明显回落；MAC 的 MCR clinical-complete `0.2400` 有竞争力，但 DA 仅 `0.0225`，不存在跨族一致统治。
6. **e7/v0 暴露族间机制差异。** e7 的 MCR clinical-complete 点估计最高（`0.2450`），DA task 却低于 MOSAIC 三臂；这更像任务投影与对象粒度的交互，而非简单“推理强/弱”。
7. **I1 的 clinical 字段为 null。** 在完成同等 root adjudication 前，只能报告其较低 task 与历史 chain，不能把缺失审计当作临床失败，也不能纳入临床排名。

---

## 6. Go / No-Go（按纠正后证据）

| 方法 | 判决 |
|------|------|
| Lite | 保留为 3-call 默认预算锚点；不赋予临床优越性结论 |
| Forest | 保留为约 4-call 主扩展/接口机制臂；其价值是 DA task 与候选覆盖假设，尚非 clinical-complete 胜出 |
| IMPC | 保留为候选交互机制基线，非临床主结果臂 |
| B07 / MAC | 保留为 stage-contract 与多代理聚合对照；历史 chain 不得用于共同临床排名 |
| Adaptive-* | 未满 800，不进入本报告完整样本推断 |
| I1 | clinical null；在同等 root adjudication 前不作真实诊断能力推荐 |

---

## 7. 产物路径

| 路径 | 内容 |
|------|------|
| `logs/backbone_v1/*/mosaic_{lite,forest,impc}_v1` | 三臂全 800 预测与评分 |
| `analysis/backbone_v1/r4_facts/pooled.tsv` | e7/v0/MAC/B07 的历史双指标 |
| `analysis/backbone_v1/mosaic_eval/leaderboard_400.json` | 原始历史表与原始配对检验（冻结血缘） |
| `analysis/backbone_v1/mosaic_eval/leaderboard_400_v2.json` | 五端点回放、端点协议、临床配对推断与验证 |
| `analysis/backbone_v1/r4_run_mosaic_expand.sh` / `r4_run_mosaic_400b.sh` | 扩集启动脚本 |
