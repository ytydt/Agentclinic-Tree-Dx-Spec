# 119：旧索引的一个 top-1，怎样依靠真实形态线索、过强确认及错误软分共同维持

病例 `DA_d2_seq100/119`。金标是 **Eruptive pruritic papular porokeratosis（EPPP）**；15 个冻结候选中只有父类 **Porokeratosis**，没有 EPPP，也没有题目所列 DSAP/DSP/linear porokeratosis 这些同病亚型。历史成功只能叫“汗孔角化症父类进入前列”，不能叫完成亚型鉴别。患者真正有区分力的内容是三个月迅速播散、强烈瘙痒、四肢丘疹、角样板层、颗粒层减少与真皮嗜酸细胞；本审计不以旧 `manual_flow` 自动充当独立临床裁决。

## 1. 冻结结果和排序键

| 旧/新提示词 × 索引 | Porokeratosis 名次/分数 | Dermatitis 名次/分数 | Keratosis pilaris 分数 |
|---|---:|---:|---:|
| old_old | 1 / 11.254 | 2 / 8.873 | 6.892 |
| free_old | 1 / 12.766 | 2 / 7.196 | 11.121 |
| old_v2 | 1 / 11.623 | 2 / 9.352 | 9.663 |
| free_v2 | 1 / 12.250 | 2 / 8.909 | 8.676 |

引擎实际排序键为“被排除否 → confirmed 个数倒序 → score 倒序”。两位领先者各有一次确认。`free_old` 的 Dermatitis 分数低于 Keratosis pilaris，却因错误的确认排在其前。不能把排行榜当成单一加权分数的降序表。

四臂 Porokeratosis 去重后断言数为 114/122/126/123，已连接事实数 27/32/30/29。v2 既没有丢掉汗孔角化症所有证据，也没有因为规则更多就保证新识别 EPPP。v2 gid641776 的 Introduction 确实补出含 EPPP 的亚型列表（源差量见 `source_text_examples.json`）；冻结候选集合却没有可承接这个亚型的节点。这是来源补全与候选表达空间之间的断裂。

## 2. “正确病理锚点”也有未执行的适用限制

旧 raw2373、2396、2426、2454 等多次抽取 `cornoid lamella → pathognomonic_for Porokeratosis`，dedup 后一次确认和 +2.000，另有同谓词的 `feature_of` 软证据 +2.427。它不是完全虚构：源 Evaluation 说边缘活检可显示该结构并有诊断意义；Histopathology 也称其 distinctive feature。

但同一源 **明确限制其绝对特异性**：旧 Histopathology 窗口以及 v2 gid641788/641789 写明，这一结构曾被认为是 pathognomonic，后来在其他疾病也观察到。旧 raw2488 / old_v2 raw2697 实际抽到了这句话，写成 `distinguishes_from / negated / comparator=other conditions`。它既没有引用并限制其他 pathognomonic 断言，也不能在当前执行器中否定“该标志的特异性”这一元关系。因此，来源内的谨慎条款与诊断锚点同时送达，排序仍使用无条件确认。

这里需区分：角样板层支持汗孔角化症，是有来源的有用知识；“任意出现该结构即无条件单独确诊”更强；“因此确诊 EPPP”又更强。以下降级试验保留原有 `feature_of` 支持，只把同谓词全部 `pathognomonic_for` 改成 `feature_of`，是针对来源例外的保守语义探针，未声称建立了最终临床诊断标准。

## 3. 竞争者如何获得一张假的确认票

旧 raw1071，四臂对应 raw1071/993/1166/1096：

- 来源：Dermatitis herpetiformis 的组织病理说明，v2 gid739974，直接免疫荧光显示 **乳头真皮中的 IgA 颗粒沉积**。
- 抽取：`Dermatitis Herpetiformis / granular deposits of IgA / pathognomonic_for`。
- 主体绑定：从这个具体疾病降到更早的父类候选 `Dermatitis`。
- 事实接合：接到患者 **decreased granular layer**，finding24 的 canonical 只有 `granular layer`，`decreased` 藏在 value.text。
- 执行：生成一次 confirmed 和 +2.000。患者并没有 IgA 沉积或该项免疫荧光结果。

因此首次损坏不是这句指南不存在，而是疾病层级与两种完全不同组织学对象被抹平；F7 的 quote 对齐没有阻止这种绑定。其他弱错误又向同一候选提供分数：表皮增生/棘层增厚连接表皮萎缩，小肠绒毛萎缩也连接表皮萎缩，`environmental factors` 连接正常 rheumatoid factor 产生 -0.4。正负错分同时存在，不能只统计正向误命中。

## 4. 父类金标自己也得到不应有的软分

旧索引下的五类谓词构成一个预先按来源裁定的局部集合：

| 原始行（old_old） | 来源真实含义 | 实际患者连接 | 错误位置 |
|---|---|---|---|
| 2357 | 病灶较少恶变为基底细胞癌 | basal-cell vacuolar degeneration | 恶性转化≠基底层空泡变性 |
| 2361 | 外用治疗可刺激皮肤 | 面部无症状褐色丘疹 | 治疗不良反应变成疾病表现，状态相反 |
| 2362、2532 | 外用治疗可造成皮肤萎缩 | 同一面部丘疹 | 治疗范围和实际病变均不匹配 |
| 2445 | 异常表皮角质形成细胞克隆扩增 | epidermal atrophy | 扩增≠萎缩 |
| 2497 | 因为有恶变风险，应考虑此诊断 | basal-cell vacuolar degeneration | `due to` 错附为疾病 caused_by；另有谓词错接 |

这些行在 v2 的对应不同表达详见 `judgments_skin_other.json`。并非所有臂都保留同一错误：old_v2 没有这次 `malignant degeneration caused_by` 的同词输出，free_v2 又有 raw2502。把每个变化都叫“v2 增加错误”不成立；这里展示的是非单调的新旧错误组合。

## 5. 局部、联合干预：为什么只修一处还会变差

所有干预冻结事实、候选和生产代码；屏蔽指定错误接合，不删除原指南。数值来自 `skin_other_probe_results.json`，完整重新求值见对应 gzip。

| 干预 | old_old proxy名次 | free_old | old_v2 | free_v2 |
|---|---:|---:|---:|---:|
| 原始 | 1 | 1 | 1 | 1 |
| 仅屏蔽假的 IgA→颗粒层 | 1 | 1 | 1 | 1 |
| 仅把过强 cornoid 确认降为弱证据 | 2 | 3 | 3 | 2 |
| 同时修以上两项 | 1 | 2 | 2 | 1 |
| 仅屏蔽父类金标上述错误软接合 | **2** | 1 | 1 | 1 |
| 确认双修 + 错误软接合屏蔽 | **4** | 2 | 2 | 1 |

单降 cornoid 后四臂都是 Dermatitis 凭假的 IgA 确认居首。双修后，free_old 和 old_v2 的 Keratosis pilaris 又以软分超过 Porokeratosis。这不能解释为“修错有害”，而是旧成功依赖另一处仍未修正的确认优先权和证据池竞争。

**old_old 还有可量化的跨候选耦合。** 仅屏蔽上述目标错误软接合，Porokeratosis 从 11.254 降到 9.184；Dermatitis 自身原断言没改，分数却从 8.873 上升到 9.502，从而反超。原因是这些连接也参与全局 `claimants` 分母：取消目标对某个 finding 的错误认领，其他候选对该 finding 的支持变得更“特异”。所以本地 delta 相加无法预先得到最终排名，必须全局重放。联合确认双修后再屏蔽相同软错误，old_old 的汗孔角化症父类落到第4，第一名变成 Actinic keratosis；这仍不是完成所有错误修复的最终答案。

## 6. 对旧索引 7/11 的含义

119 是旧索引七个 proxy top-3 中的一例，真实疾病级病理支持参与了成功；但其成功包含父类终点、无条件确认、目标错误软加分、竞争者错误确认和相互影响的 specificity。至少在这一局部已核查错误集上，旧 top-3 会消失。不能把整例概括为“靠幻觉猜中”，也不能把它作为“正确刚性规则成功执行”的净证据。重新执行部分修复改变名次，是局部因果证据；它不证明删掉所有错误以后临床结果会如何，更不证明 v2 的总体因果效应。

证据：`judgments_skin_other.json` 的 119-* 事件、四臂完整 trace、`run_skin_other_probes.py` 与 `skin_other_probe_full.json.gz`。原始行号为合并病例断言的零基索引，不是 raw cache 内行号；缓存编号和 local index 均在证据账本中。
