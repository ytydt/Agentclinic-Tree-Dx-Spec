# v2 来源结构与抽取谱系复核

基线：`cursor4@96938384655e486e8eddc0a0e7c6901de9e57aa4`。本文件区分原始 XML、实际送入抽取器的窗口、原始模型输出、归一化输出及执行时重新寻找的证据。没有重新调用模型，也没有下载 LFS 大索引。

## 1. 全部四臂原始缓存可复原，不必用新一轮模型输出替代历史错误

`provenance_audit.py` 按现行调用构造重建 payload，模型名为 `meta-llama/llama-3.3-70b-instruct`，依缓存键查找原始响应，再逐条应用现行 `normalise_group`。四臂 **140,652 条**保存断言逐条、逐字段完全相同。这使后续病例审计能够分辨“模型已经输出错”与“程序随后改错”。

| 臂 | passage×focus 作业 | 唯一缓存键 | 唯一窗口正文 | 保存断言 | 逐字段复原 | 超过6,000字符的作业 |
|---|---:|---:|---:|---:|---:|---:|
| 旧提示词/旧索引 | 3,842 | 3,746 | 2,683 | 34,338 | 34,338 | 15 |
| 新提示词/旧索引 | 3,842 | 3,746 | 2,683 | 33,533 | 33,533 | 15 |
| 旧提示词/v2索引 | **3,927** | 3,826 | 2,736 | 36,837 | 36,837 | 16 |
| 新提示词/v2索引 | **3,927** | 3,826 | 2,736 | 35,944 | 35,944 | 16 |

旧报告§34开头“每臂3,842任务”不准确。不同索引还改变实际正文和窗口边界，因此该实验是来源/检索结果包的比较，不是对固定同一组规则逐条仅补上缺失成员的干预。

四臂11例的病例 findings 均与**剥离 Options 后**的病例缓存完全相同。不能声称本轮病例抽取器直接读取了选项。但是 `run_trial_retrieval.py:case_terms` 仍对任务文件完整 vignette 提取 TF-IDF 词；例74的检索词含 `brugada channelopathies excluded`。这说明**病例抽取输入与检索查询输入的清洗边界不同**。本轮没有重新建立索引并运行 clean-query 对照，不能量化它的检索效应。

`extraction_job_manifest.jsonl` 为每个作业保存 arm、case、focus、gid、doc_key、正文 SHA256、原始 cache ID/文件 SHA256，以及其在保存断言数组中的起止行。`normalisation_changes.json` 保存归一化前后的真实变化；`passage_manifest.jsonl` 回指正文位置，不复制完整语料。

缓存键只覆盖 `(kind, payload, model)`，不覆盖完整 prompt、provider、客户端版本和历史环境。逐字段复原证明这些缓存足以重建产物，**不证明历史运行环境与当前环境全部一致，也不能恢复未记录的原始提示词版本**。现行新旧提示词由不同 kind 区分，这一隔离可确认；同 kind 之内改 prompt 的风险仍存在。

## 2. 保存时丢掉了最需要保留的身份字段

四臂普通抽取产物中，`_passage_sha1` 的覆盖均为 **0**，也未保存 gid、window_gids、doc_key 或 cache key；只保留 `_focus/_source/_title/_section` 等文本字段。即使同时加上 case 和 focus，该保存键仍对应多个不同正文：旧索引471组键、v2索引433组键有歧义。执行器使用更宽的键回找原文，问题会进一步放大。

F7 默认读取 `trial_retrieval_k30.json`；只有设置 `F7_EXTRA_RETRIEVAL` 才追加其他检索文件。`score_2x2_engine.py` 未自行设置此变量，也没有将原始正文直接挂到断言。`resolve_passage()` 依 `(source,title,section)` 和引文子串取第一个匹配窗口，候选只有一个时甚至不要求引文命中。故“引文许可”不是可靠的同源验证。

按正确原始窗口恢复 F7 是独立的 provenance 干预，应单独报告，不能把随后分数变化归为模型变强。详细配对重放见 `cohort_metrics.json` 和 `cohort_audit.md`。

## 3. v2 仍有实证可复现的原始结构损失

仅按需取得两篇 StatPearls XML。`source_parse_repro.py` 直接调用提交中的 `scripts/build_statpearls_corpus.py`，不改解析器。以下是两个确定性缺陷的见证，并非语料总体错误率估计。

### 3.1 真标题被参考文献标题替代

| 原始文件 | BITS正文标题 | v2解析器使用的标题 |
|---|---|---|
| `article-24945.nxml` | Memantine | 首条参考文献：The neuropharmacological basis for the use of memantine in the treatment of Alzheimer's disease. |
| `article-29656.nxml` | Sudden Death in Athletes | 首条参考文献：[Current practice for the prevention of sudden death in young athletes]. |

代码读取 `root.iter('article-title')` 的第一个元素，实际正文标题在 `book-part-meta/title-group/title`。article_id修复没有修正这个语义元数据错误。错误标题已经出现在实际v2检索窗口里，可能影响疾病定位、主题推断和证据回找；本轮未独立量化其排名贡献。

### 3.2 修复了顶层列表，但 `<p>` 内的子列表仍被压平

Memantine 的 Alzheimer 诊断段在原始 XML 中有5个顶层成员；第5项的 `<p>` 内还有两个 `<list-item>`，其中一个又明确写 `All 3 of the following`。当前 `render_list()` 只识别 `<list-item>` 的**直接** `<list>` 子节点。遇到 `<list-item><p><list>...` 时，会将整个 `<p>` 交给 `_text/_clean`，丢掉层级。

确定性结果：原始2个嵌套成员，输出**0条缩进成员**；第五行出现 `genetic testing.All 3 of the following` 的粘连。这与v2实际窗口gid599595一致。

这不是“量词和成员未共处”的旧错误：文字和量词已经在同一窗口，但**成员边界、嵌套作用域和替代路径的身份仍不可可靠恢复**。可见“共处率提升”不等于“结构复原完成”。若来源本身没有明确写出两分支间的连接词，解析器/LLM也不能凭常识补成AND或OR；应标为来源歧义，回到正式标准核对。

## 4. 对故障归因的修正

来源缺失、结构损坏、抽取误读和执行错误同时存在，不能按时间线宣布前一层已经解决。v2修复把原本不可见的规则带入管线，同时暴露了此前被缺失遮蔽的表示能力不足。新增规则应同时检查**成员完整性、树结构保真、方向、强度、适用范围、证据身份**；单独增加组数或高权关系数没有诊断安全含义。
