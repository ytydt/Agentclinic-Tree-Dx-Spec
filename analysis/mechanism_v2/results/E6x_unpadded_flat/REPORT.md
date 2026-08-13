# E6x：移除 flat padding 的 tokenizer 反事实与轨迹稳定性审计

## 判定

E6 的 whitespace 长度控制被证伪：`[LENGTH_CONTROL_PAD]` 在 DeepSeek tokenizer 中约占 8 token，而不是一个 token。去掉 padding 后，256 个 telemetry 匹配病例的平均输入 token 从 1721.0 降到 604.8，减少 1116.2（64.9%）。在两臂均只有一次物理尝试的 184 例中，移除的 whitespace pad 数与输入 token 节省几乎严格线性（Pearson `r=1.000`；斜率约 8.00 token/pad，截距约 −3）。因此原 E6 的“每例三表示 whitespace 词数完全相等”不能作为模型注意力预算相等的证据。

但“padding 解释 flat 的语义劣势”同样没有得到支持。在外部臂盲筛查并按冻结队列接受根代理定向纠错的 255 个共同输出语义敏感性汇总中，unpadded 相对 padded：

- 完整等价增加 1.57 个百分点（padded-only 7，unpadded-only 11；`p=0.481`）；
- 完整或部分等价反而下降 3.53 个百分点（padded-only 19，unpadded-only 10；`p=0.136`）；
- safe-exact top-1 从 3 降到 2，gold recall 从 6 降到 5，均 `p=1`。

这是一项负向但有价值的可证伪结果：padding 是严重的 token/成本混杂，却不是观察到的诊断质量差异的单向机制。

## 唯一干预与冻结范围

E6x 复用 E6 的同一批 300 例、同一 258 个成功 builder 结果、同一无序事实文本、同一 DeepSeek V4 Flash selector 提示词、校验器、温度和 retry 上限。唯一表示干预是删除补齐到三臂最大 whitespace 词数的 sentinel；不重建 facts，不调整候选合同，不改变 gold 隔离。

原 padded 臂、builder 结果、telemetry 和同义桥均在调用前记录 SHA-256。42 个 builder 失败继续 fail-closed；unpadded 的 258 个可构造病例全部最终通过 selector 合同，padded 为 255 个。冻结表面终点展示为 **safe-exact（历史字段 `strict`）**：由 `FrozenExactSynonymBridge.equivalent` 实现，只接受归一化相等、冻结且排除冲突的同义词及窄定义的自身首字母缩写，不使用 substring/fuzzy tier。它是标签身份下界而非临床完整性判定。这里不重复运行、不扩确认集、不统一 provider/retry，符合总实验排除项。

语义审计在看到 selector 结果后、调用审计模型前另行冻结。Gemini 2.5 Flash 只看到随机顺序的 O1/O2，不看到 padded/unpadded 名称；255 例双输出、3 例单输出、42 例零输出。根代理最终复核 33 个完整等价分歧和 30 个冻结一致样本，共 63 例、126 个判断；33 个外部判断被改判，涉及 25 例。其余病例没有接受逐输出人工临床裁决，因此未审 safe-exact-negative 或外部语义-negative 不能当作已证实的临床阴性；本报告的语义数值是定向纠错敏感性分析，不是完整 300 例临床 leaderboard，也不移植 E2 replay 数值。

## tokenizer 混杂的定量解剖

E6 flat 原表示平均 109.6 whitespace 词，却平均增加 128.46 个 pad。单次物理尝试病例给出近乎确定的映射：

`输入 token 节省 ≈ 8.00 × 移除 pad 数 − 2.99`

总 input token 与 pad 数的相关只有 `r=0.424`，原因不是 token 机制不稳定，而是 telemetry 总量累加了不同重试次数。按物理尝试归一后相关升至 `r=0.837`；限制两臂均一次尝试后为 `r=1.000`。因此报告成本时必须把“每次请求长度”和“重试次数”拆开。

原 E6 三臂每次物理尝试的平均输入 token 约为：raw 767、padded flat 1483、graph 841。flat 看似最短的临床内容，实际给 selector 的 token 反而最多。这使原 E6 的 flat 延迟/成本比较无效，也可能扰动注意力；E6x 修复了这一点。

## 为什么输入大幅缩短却没有稳定改善

### 1. DeepSeek 的输出长尾不是输入长度的简单函数

在 256 个匹配 telemetry 病例中，unpadded 的输入少 1116 token，但输出反而平均多 1203 token，语义调用延迟平均多 25.6 秒，物理尝试平均多 0.156。运行日志显示大量 `finish_reason=length` 和 180 秒长尾。

这些后三项不能作纯因果解释：两臂在不同时间运行，经 OpenRouter 多 provider 路由，provider 混合和瞬时退化同时变化；用户要求排除的 provider/retry 统一实验也未执行。可以安全下的结论只有两层：输入缩短是确定性的序列化效应；输出膨胀与长尾证明“移除 padding 足以消除运行退化”这一说法为假，但不能判定 padding 对输出成本的真实平均因果效应。

### 2. 温度 0 不等于轨迹稳定

255 个共同成功病例中，243 个 top-1 champion 改变，翻转率 95.29%。两臂 top-5 的 exact-label 平均交集只有 0.345 个，平均 Jaccard 0.0426，0 例拥有完全相同的 top-5 集合。即便考虑同义词表面变化，这个幅度也远超“措辞微调”。

这意味着 sentinel 不只是占据被模型忽略的尾部。它改变了整个生成轨迹；同时，provider 路由、长 reasoning 和采样实现也可能放大扰动。E6 中各表示间约 95% 的 champion flip 因此不能全部归因于临床信息差异。

### 3. 翻转方向对称，缺乏单一注意力故事

人工审计的 33 个完整等价分歧可分为：

- 18 例同一诊断的具体度/本体边界翻转；
- 10 例直接换成不同疾病；
- 5 例组合目标组件保留与丢失。

去 padding 的明确获益包括：

- `MCR_seq200b/458`：Birt-Hogg-Dubé → LAM；
- `MCR_v2_seq100/143`：MRSA 坏死性肺炎 → GPA/ANCA vasculitis；
- `MCR_v2_seq100/208`：STEMI → Takotsubo；
- `MCR_v2_seq100/214`：eosinophilic annular erythema → urticarial vasculitis；
- `MCR_v2_seq100/179`：ITP → 缺氧/发绀型先心病相关血小板减少；
- `DA_d2_heldout200b/532`：误定位为 SVC 的 lipoma → interatrial septal lipomatous lesion with SVC obstruction。

同样清晰的退化包括：

- `MCR_seq200b/322`：factitious disorder → schizophrenia；
- `MCR_seq200b/364`：acute interstitial nephritis → membranous nephropathy；
- `MCR_v1_seq100/45`：granuloma annulare → sclerosing mucinous orbital granuloma；
- `MCR_v1_seq100/74`：CPVT → Brugada syndrome；
- `DA_d2_heldout200b/575`：P. falciparum + P. ovale 混合感染 → 只保留 P. ovale；
- `DA_d2_seq100/103`：完整 IART + variable AV block → 只保留 atrial flutter/IART。

因此不存在“更短输入统一释放关键证据”的机制。更合理的解释是：候选生成处于多个相近吸引域，非信息 sentinel、provider 实现或长输出路径足以改变早期 token，随后整条候选轨迹分叉。病例事实决定可达疾病集合，但当前 selector 对集合内落点缺乏稳定性。

## 审计员改判的意义

Gemini 原始结果给出完整等价 46→47（+0.39 pp）。根代理改判后为共同病例口径下净 +1.57 pp。常见审计错误与 E6 相同：

- 把 supported complication 当成“扩大诊断”，例如 bath-salt intoxication 加 AKI、Poncet disease 加其他结核部位；
- 要求输出重复参考未要求的表现，例如 generic Sarcoidosis 被要求同时写 mediastinal nodes；
- 因词序把“DVT secondary to May-Thurner”误判为没有识别 May-Thurner；
- 漏掉真正的本体冲突，例如 early nonatrophic autoimmune gastritis 被叫成 chronic atrophic gastritis。

这说明 E6x 的近零净效应没有被冻结人工复核队列中的阈值纠错逆转；该结论限于定向审计覆盖，不能扩写为全部输出都已人工判定。

## 对主研究问题的含义

1. 以后任何“长度匹配”必须使用目标模型 tokenizer 或 API 报告的 prompt token，而不是 whitespace 词数；padding 字符串需先做 tokenizer 单元测试。
2. 不应使用语义显著的 sentinel 做注意力控制。若必须匹配长度，应采用模型原生 padding/批处理掩码；聊天 API 无可靠 mask 时，宁可把 token 长度作为协变量，不伪装成严格匹配。
3. 轨迹比较必须同时报告候选集重合、champion flip 和语义终点。只报告最终 accuracy 会隐藏几乎完全不同的候选生成轨迹。
4. 当前 DeepSeek selector 的病例级机制结论应建立在成组、方向一致的 discordance 上，而不是单次单例。用户排除重复运行是合理的成本边界，但相应地必须收窄单例因果声称。
5. E6 的 raw→graph 语义损失不能由 flat padding 反事实解释：graph 未使用 flat 的大量 pad，且人工来源审计直接找到关系错误与桥梁丢失。E6x 修复的是 flat 对照的 tokenizer 混杂，不推翻图构造机制结论。

## 可复核产物

- `preregistration.json`、`semantic_preregistration.json`：两阶段冻结设计；
- `arm/`：258 个 unpadded selector 缓存、结果、telemetry、日志；
- `summary.json`：safe-exact（保留历史字段 `strict_top1`）与运行指标的 padded/unpadded 配对；
- `semantic_judgments_final.jsonl`、`semantic_final_summary.json`：外部臂盲筛查并按冻结队列接受根代理纠错的语义敏感性终点；
- `case_trajectory_diagnostics.jsonl`：255 例候选集、champion、token、延迟和语义方向逐案对照；
- `semantic_manual_adjudication.jsonl`、`manual_audit_manifest.json`：63 例人工裁决与冻结覆盖。

E6x 是开发集上的机制反事实，不是模型稳定性的独立重复确认；provider/time 混杂被明确保留为限制，而非事后以技术降方差实验消除。

## Canonical Top-1 migration addendum (2026-08-13)

臂隐藏三 reviewer 模型面板重放（非 human-root）显示：unpadded 相对 padded 的
clinical-complete 为 62/300 对 58/300，配对 +1.33pp（16 gain/12 loss，
`q=.57159`）；C∪P 为 117/300 对 119/300，−0.67pp（19/21，
`q=.87463`）。因此去 padding 的巨大 token/成本收益仍成立，但没有规范临床质量增益；
“padding 不是 flat 质量损失的单因”这一结论保持不变。
