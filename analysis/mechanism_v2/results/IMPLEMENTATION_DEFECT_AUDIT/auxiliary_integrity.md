# 辅助权重与配置的实现缺陷

冻结版本 `bbc036e8`。复现：`python analysis/mechanism_v2/results/IMPLEMENTATION_DEFECT_AUDIT/reproduce_auxiliary_defects.py`。脚本调用实际 `sweep_fixes.configure` 和 `build_corpus_lift.main`；后者仅将语料加载函数替换为 24 行合成稀疏矩阵，文件写入临时目录。6 个检查通过表示**缺陷行为被复现**，不表示已修复。

## AUX-01：配置没有完整复位，调用历史可以改变同名实验

`sweep_fixes.py:81–100/configure` 设置早期的一批模块全局变量，却没有复位后来增加的四个 RIGID 开关、`NONCRITERION_INERT`、`FINDING_POOL_BETA`、`LAYER3_DROP`。反例先启用这些选项，再调用 `configure(B1,{})`，七项均原样保留。

这是**同进程复用**风险，不是说每次独立启动 `score_2x2_engine.py` 都受到污染。上一轮 `V2_INDEX_DIFFERENTIAL_AUDIT/replay_audit.py` 已显式复位这些选项，因此该问题不能推翻其 44 条精确历史重放。也不据此猜测病例 74 的旧报告数字差异来自配置残留。

纯代码修复：用不可变 `EngineConfig` 显式传入所有阶段；兼容包装器须从完整默认配置构造新实例，而非逐项修改旧模块。移除多线程共享配置；缓存与输出附实际配置哈希。验收应比较 A→B→A 与 A 单独执行的结果，并检查 B 的所有字段，而非只核验命令行标签。旧 M25 已提出运行版本化，本项补足状态泄漏的具体反例。

## AUX-02：病例相对 lift 被保存为跨病例绝对键

`build_corpus_lift.py:187–195` 在每个病例中计算

\[
L(c,f;H)=\log\frac{p(f\mid c)}{|U_H|^{-1}\sum_{h\in U_H}p(f\mid h)}.
\]

这里的概率实际是语料词面计数加平滑的比例，`U_H` 是当前病例中拥有足够 topic chunks 的候选；它不是经过临床标定的诊断似然比。先不争论这个统计设计是否有用，**既然数值依赖 H，保存键就不能只用 `norm(c)||norm(f)`**。实际第 195 行以该不完整键覆盖写入；执行端 `run_mechanical_engine.py:219–232/lr_weight` 也只读取这个键。

实际 main 的合成反例中，Alpha 对同一 marker 的比例固定，但与 Beta 比较时 lift=.5306，与 Gamma 比较时=.0606。按两个病例顺序构表后，Alpha 的最终值为 .0606；反转病例顺序后为 .5306。改变的是后处理顺序，患者或 Alpha 的源统计并未改变。

冻结 all4 的现存任务/提取输入与 lift 表中可找到 **5 个跨病例共享查询键**：cardiomyopathy/oxygen saturation、congenital heart disease/oxygen saturation、abscess/fever、lymphoma/age、lymphoma/vital signs。该检查只是实际风险入口；**不是证明 5 个键都曾发生数值不同的覆盖，也不是 5 个临床错误或 MRR 效应量**。现存表没有保存每个病例写入前的值及完整生产谱系，本轮不下载大索引来猜补。

纯代码修复有两种互斥规格：若坚持病例相对权重，保存原始 `p(f|c)`/计数，再在执行时按明确候选集计算；或键包含实际候选集、别名映射、语料版本、词汇/分片、平滑及可用候选规则。若改为固定总体参考，则先定义并冻结总体，再用与病例无关的键。不能只在写端加 case ID，却让读取端继续旧键。

恢复正确命名空间是代码修复；把词面比例升级为医学判别力是另外的统计/语义研究，不能由前者担保。旧 M19/M20/M25 覆盖权重资格、聚合和谱系原则，但没有这个具体的病例键冲突反例。

## AUX-03：丢掉词表外限定，完整标签却保留在输出键

`build_corpus_lift.py:131` 的 topic 查询、`:143` 的 finding 查询都先删除不在 TF-IDF vocabulary 的 token，再用剩余 token 交集检索。合成源完全没有 UnseenSubtype，`Alpha UnseenSubtype` 却获得 Alpha 的全部 8 个 chunks 和相同 lift；`marker unobservedqualifier` 同样得到 marker 的完整数值。键里保留了限定，数值所代表的语义却已降格。

代码可以确定性阻止这种无记录降格：保留未解析限定及词面覆盖元数据，不能用部分标签的计数写入完整标签身份；必要限定无法解析时返回 `unavailable/needs_mapping`，不得伪装为精确统计。**未知限定是否医学上可忽略**则需要类型化别名/父子关系和来源判别，属于 hybrid 语义恢复。像通用词、停用词等可按明确、版本化规则处理，不要求任何 OOV 都永远拒绝。更多全文字面命中也不等于疾病归属、共同出现也不等于关系成立。

本轮没有重建真实 corpus lift，也没有声称取消这些数值会提高 MRR。新技术与验证方案见 [semantic_binding_research.md](semantic_binding_research.md)。
