# 指南 KG「条目内重组 + claim-aware rechunking」独立审计

> 本文是在实现前对旧 Passage 层所作的设计审计。文中 `/tmp/gkg-passages-full-v2`
> 等路径仅标识当时冻结的本地审计输入；最终实现结果、SHA、窗口统计和与旧 chunk
> 的定量比较见 `GUIDELINE_DIAGNOSTIC_KG_BUILD_REPORT.md`。本文保留原始审计判断，
> 便于区分“事前设计约束”与“事后运行结果”。

审计对象：旧 Passage 层及其三类上游 JSONL。本文只评估切分、来源拓扑和可追溯性，不评估 LLM 医学正确性。

## 结论先行

应当先按来源条目重组，再按临床主张结构重新切分；但**不能直接从当前 `passages.jsonl` 重组**。它已经经过诊断 gate、±1 邻接闭包和全局同文去重，只是稀疏检索层，不是完整的来源顺序层。最安全的输入是经过已审计清洗的全量 raw occurrence 流；诊断 gate 应后移到 claim block/window 层。

默认不宜用“整条目一个 prompt”，也不宜固定 token overlap。建议：结构块目标约 **3,000 个实际模型 token**，source-text 硬上限 **6,000**，且以最终渲染后的 prompt **10,000 token 软上限、12,000 硬拒绝线**再校验。WikEM 可整条目输入；Merck/CPG 按标题、段落、列表和表格闭包打包。该参数是基于现有分布的工程起点，仍须做 1.5k/3k/6k 配对实验，不能预先宣称 3k 最优。

## 1. 当前层不能承担完整重组

当前文件有 28,745 个唯一 Passage，但对应 30,152 个 admitted source occurrences。全局相同文本被折叠后，一个 Passage 最多聚合 163 个不同 occurrence；顶层 `section_id/ordinal/previous/next` 只属于确定性选出的 primary provenance。因此：

- 重组必须遍历每个 `extensions.provenances[]`，不能用 Passage 顶层邻接代表所有来源；
- 相同文本在不同文件中的前后文不同，必须先按 occurrence 重建上下文，抽取后再做 assertion/provenance 聚合；
- `selected_next_passage_id` 是“下一个被选中的块”，不是来源中的下一个块。

更严重的是，admitted CPG 只有 20,425/39,091 个原始块。按 `document_version_id + source_ordinal` 检查，1,910 个被命中文档内仍有 1,168 个稀疏断点，合计跨过至少 10,286 个 source ordinals，最大单次跨 134；Merck 也有 121 个断点、跨过 287 个 ordinals。±1 闭包只能局部缓解，无法恢复完整列表、表格或跨多块限定语。因此从 selected Passage 重新拼接会把“缺失块”伪装成连续正文。

上游原始边界本身也常切断语法。简单的 `上一块以字母数字结尾 + 下一块以小写开头` 只是保守指示器，已覆盖 Merck 1,643/9,276（17.7%）个文档内边界、CPG 929/36,821（2.5%）个边界。另有约 26.6% 的 Merck 边界和 22.5% 的 CPG 边界不以句末/列表闭合标点结束。它们不是全都诊断主张，但足以否定“一块一次调用等价于完整证据”的假设。

人工核对的确定性断裂包括：

- Merck ch106 chunks 39→40：`In homozygotes, a` 与 `mild microcytic anemia ... Diagnosis ...` 被分开；表型和诊断方法失去同一作用域。
- Merck ch116 chunks 21→22：`family history of` 与 `erythrocytosis; it is established by measuring ...` 被分开；触发条件和确证检查分离。
- CDC STI chunks 75→76：`Clinical diagnosis ... can be difficult because the` 与“经典 HSV 病灶常缺失、应做 type-specific testing”分离。
- ESC cardiac sarcoidosis chunks 14→15：`probable cardiac sarcoidosis` 标题与“须有心外组织学 + 下列一项或多项”的逻辑列表分离。
- ACR knee trauma chunks 21→22：年龄限定在前块结尾、`at least one of the following` 及特征在后块。

## 2. 三类来源的可用拓扑与风险

### Merck 19e

可靠的硬边界是 `source_id`（章节）和 `source_ordinal`。`subsection` 可作为软结构信号；`entry_title` **不能作为硬 entry key**：353 章内共出现 2,452 个不同 entry title，每章中位 5 个、P90 15 个、最大 89 个；至少 772 个“章内唯一标题”呈长句、句中片段或冒号引导语形态，例如 `Diagnosis is established if ...`、`Complications include ...`。这些是 PDF 版式解析误把正文粗体/引导句当标题的证据。

建议先在章节内排序，再用“正文标题行 + 合理 metadata 变化 + 章节内连续性”联合识别 entry run；可疑 `entry_title` 只能显示为低置信上下文，不能决定切断或诊断对象。已确认的 ch353 附录/索引污染边界继续在重组前剔除。表格行在 PDF 抽取中可能已缺失；重切分不能恢复上游未抽出的内容，必须单列 `source_extraction_loss`。

### NICE 与其他 CPG

`source_id/article_id` 通常是最稳定的文档键，`source_ordinal` 是排序键；不要假定 `raw_chunk_ordinal + 1` 连续（现有 CPG 有 3,248 个正向编号跳跃）。`section_path` 可作标题栈，但质量异质：7,067 个块终结于泛化的 `Introduction`，还有大量 `Why the committee...`、`Rationale and impact`。NICE recommendation 编号、PDF 页标和表格头应作为独立结构信号。

需在 LLM 前标记或过滤：references/citations（“diagnostic performance”会触发假 gate）、登录/付费墙、浏览器 chrome、通用 ACR 声明、被替代/撤回指南、纯治疗/委员会讨论、页眉页脚。过滤必须有 reason ledger，不能直接删除而不可审计。重复的 NICE landing/update 文本和 ACR boilerplate 应在**上下文重建后**聚合 provenance。

### WikEM

`source_id == parent_manifest_id` 与 `syndrome_anchor` 稳定；149 个条目中没有多 anchor 冲突。整条目中位约 283 个空白 token、最大 959，故优先整条目一个 window，保留 `section_path` 标题顺序。不要用句号分句：它以缩进/换行承载列表和表格。`wiki_links` 只可生成候选概念，不是诊断关系证据；`Differential Diagnosis` 下的成员不能自动转成“支持某诊断”的 criterion。

## 3. 推荐的重组与重切分路径

1. 从全量 clean occurrence 读取，按 `(document_version/source_id, source_ordinal)` 排序；保留 raw id、section path、页面和 admission reasons。禁止跨文档、跨章节拼接。
2. 建立逻辑 entry/section run。Merck 使用章节内经校验的标题栈；CPG 使用 article + section/recommendation id；WikEM 使用 syndrome entry。
3. 将内容解析为不可随意拆分的 block：heading、paragraph、list-intro、list-item、table-header、table-row、footnote/reference、page artifact。
4. 形成 claim closure：标题/诊断对象 + cue 句 + 其列表/表格全部子项 + 直接限定它的否定、时间、群体、阈值、比较语。以下结构禁止从中间切开：`k-of-n`、AND/OR 嵌套、条件→结论、否定作用域、比较对象、数值→单位、表头→行、列表引导句→列表项。
5. 再做诊断高召回 gate。没有诊断 cue 的相邻块可作为有界 scope context，但标记为 context-only，不能凭邻接自动生成 edge。
6. 按 block 打包：目标约 3k source tokens，硬上限 6k；同时以真实 tokenizer 对最终 prompt 计数。超过上限时依次在子标题、段落、列表项组或表格行组边界切开并复制标题/列表引导语；不可分的超大块进入 `oversized_block` 队列，严禁 substring 截断。
7. overlap 只复制语义锚（标题、主语、必要的一句前置 scope），不做固定 256/512-token overlap。复制区域不得作为独立 evidence；抽取后按诊断概念 + 完整 qualifiers/logic + source spans 去重。

为什么是 3k/6k：现有连续 section-run 的 P99 约为 Merck 1,773、CPG 2,292 token；WikEM 全条目最大 959。3k 能容纳绝大多数完整 section，又给候选表、句子 inventory、JSON schema 和输出保留空间。当前 12k input 拒绝线不应被 source text 用满；对 json-object fallback，schema 还会进入 prompt。最终应动态控制 `rendered_prompt <= 10k`，而不是只看 metadata 的空白 token。

## 4. offset map 必须满足的契约

每个 source segment 使用半开区间：

```text
[window_start, window_end) -> passage_id + [passage_start, passage_end)
```

并附 occurrence identity（至少 `document_version_id/source_id/source_ordinal/raw_id`）、`role=primary|context_copy` 和 `eligible_for_evidence`。机械 invariant：

- 两侧长度严格相等，坐标非负且不越界；
- `window_text[ws:we] == passage_text[ps:pe]` 逐字符相等；
- window 侧 map 按序且不重叠；primary source 片段不得无理由重复；
- 人工空格、换行、标题标签等只进入单独的 `synthetic_regions`，不伪装成 source map；map 与 synthetic regions 的并集应覆盖整个 window，二者不得重叠；
- `context_copy` 必须有 canonical source 坐标，且 `eligible_for_evidence=false`，以免重叠窗口重复造边；
- 任一 LLM evidence component 必须完全落在一个 eligible primary segment，或落在来源连续的一组 primary segments中，并能投影为一个或多个 EvidenceSpan；每个投影 quote 必须与原 Passage 切片严格相等；
- evidence 不得触及 synthetic separator。若一个断句跨两个原块且中间需要人工空格/换行，必须生成多个 EvidenceSpan IDs（当前 assertion schema已支持），不能制造一个“看似连续但无法 exact quote”的 span；
- 同文 Passage 多 provenance 时，连续性按 occurrence identity/source ordinal 判断，不能按共享 Passage id 判断；
- window id 应由有序 occurrence/range/role + pipeline version 计算，不应只由展示文本计算。

更稳妥的 LLM 接口是预先给每个 `EVIDENCE_MENTION` 一组合法 `source_spans`，让模型返回 mention/component id；absolute offsets只作交叉检查。跨块 claim 的一个 assertion 可引用多个 EvidenceSpan。若仍要求模型返回一个跨 synthetic delimiter 的宽 span，上述 exact-source 契约在数学上不可满足。

## 5. 必须自动化的对抗测试

- 句子在 `a | mild`、`type- | specific`、`< | 40 mg/dL` 等边界断裂；不得丢词、合并词或改写 quote。
- `probable diagnosis`/`at least k` 在前块，列表项跨后续两块；主语、k、n、AND/OR 均保留。
- 表头在前块、行在后块、脚注再后；每个行组必须携带不可引用的表头副本。
- `absence of X does not exclude Y`、`only if`、`unless` 在边界两侧；不能反转方向或必要性。
- 同一 exact Passage 出现在多个指南且邻居不同；窗口不得串源，抽取后才聚合 provenance。
- Merck 的句子型 `entry_title` 突然变化；不得误开新疾病或把标题当 criterion。
- selected 层存在 >1、>100 ordinal gap；构建器必须 fail closed，而非直接拼接。
- context-copy 与原文同时出现；不得产生重复 evidence/edge。
- WikEM differential 列表、治疗列表、disposition criteria；不得被转成疾病定义性诊断标准。
- citation 中出现 `diagnostic performance`、登录页标题含 `diagnosis`、被撤回指南；应进入污染/版本状态而非诊断 edge。
- 单一不可分 block >6k 或最终 prompt >12k；必须显式 quarantine，绝不截断。

建议把这些写成 fixture，并对每个产物执行：source coverage、orphan heading/list item、逻辑闭包、跨源拼接、prompt-token 上限、offset round-trip、重复 assertion 数的断言。

## 6. 下一步判定实验

用至少 60 个完整来源条目（Merck/CPG/WikEM各分层，覆盖普通段落、k-of-n、表格、否定、跨块断句）做双人金标。固定模型、prompt、候选表、temperature 和**实际输入 source-token 总量**，比较：

1. 旧 one-chunk-per-call；
2. 只拼相邻块再固定 token 切；
3. entry 重组 + claim-closure packing（1.5k/3k/6k 三档）。

主要终点不只看最终 edge recall，还应包括：金标主张全部组成部分同窗率、诊断对象/限定语/逻辑 exact match、offset 回投影成功率、scope 反转率、重复 edge、污染 edge、每个有效 assertion 的 token/cost。对每个旧边界可做 paired McNemar/cluster bootstrap；以 entry 为聚类单位。只有新方案在等 source tokens 下提高完整主张召回且不增加 scope 错误，才能把收益归因于重切分，而不是单纯输入了更多文本。
