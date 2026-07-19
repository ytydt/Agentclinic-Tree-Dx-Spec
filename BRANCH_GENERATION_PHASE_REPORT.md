# 临床诊断树一级分支自动生成：阶段性研究报告

**文档类型**：学术研究阶段性总结（**自包含**，不假定读者可访问项目仓库或其它内部文档）  
**撰写日期**：2026-06-26（**2026-06-28** 增补 8 题四大指标 + MECE 补跑归档）  
**状态**：§19 全矩阵（除 A0_legacy）**8 题 + MECE 补跑已完成**；LLM 臂有效 Comp 仍以 **gnn-llm 2026-06-26 A9l=0.812** 为准  

---

## 摘要

本研究改进 **Agentclinic-Tree-Dx** 诊断流水线中的 **一级分支创建** 环节：在已知「根综合征」与当前临床证据的前提下，自动生成少数几个 **互斥且尽量完备** 的初步诊断方向，并保证 **正确答案所在方向不被遗漏**。

**报告结构**：**§3** 知识注入三条基础路径；**§6** 缺陷与改进（现象–案例–实测–状态）；**§7–§8** 实验臂与数值对照。

研究从 **完全依赖人工维护的 JSON 配置文件** 出发，逐步引入 **临床指南与开放文献的检索增强**、**同一篇文章内的鉴别诊断扩展**、**大语言模型的有依据抽取**、**医学本体的疾病归族**、**从机制描述直接提名疾病** 与 **MedCPT 双路检索融合**，形成可开关、可对比实验的 `**GuidelineBranchSource`（指南驱动分支候选召回器）**。

在 **14 题常见综合征** + **8 题罕见病例** 的隔离评测中：**综合最优** 为 **A9l**（综合分 0.812）；**二级子族召回最优** 为 **A11_llm / A12**（0.857）。若干改进（五路查询扩展、分数据源合并检索、hybrid→SNOMED 自动分区、检索结果过度裁剪、把扩展块灌入字典匹配池）经实验 **被证伪或弃用**。**生产推荐** 仍为 **A∪C 并集模式**；A9l 代表 **CPG 实验索引** 上召回层上限，二者经方案 A 起草与 IMP-31 索引合并收敛。

---

## 1. 研究命题：分支创建做什么、如何工作、为何必要

### 1.1 在诊断流水线中的位置

Tree-Dx 将临床病例推理建模为 **概率诊断树**。简化流程如下：

```text
临床病例描述
  → 根综合征选择（例如输出 "hypercalcemia / 高钙血症"）
  → 一级分支创建（例如：甲旁腺介导 / 恶性肿瘤相关 / 肉芽肿 / 药物性 …）
  → 二级子分支（具体疾病，如 PTHrP 相关恶性肿瘤高钙）
  → 证据检索与似然比调整
  → 最终诊断选择
```

**一级分支创建（BranchCreator）** 负责树的第一层。它的输出 **不是** 最终诊断，而是 **几个并行的诊断方向（族/域）**。例如高钙血症常按 **病因机制** 分为：原发性甲旁亢、恶性肿瘤相关、维生素 D/肉芽肿性、噻嗪类或牛奶-碱综合征等——这些方向在同一分类轴下 **互斥且尽量覆盖全部常见病因**。

### 1.2 临床规范依据（外部文献）


| 概念                               | 外部依据                                    | 在本研究中的借鉴                               |
| -------------------------------- | --------------------------------------- | -------------------------------------- |
| **Problem representation（问题表征）** | 临床推理教材：病例应先压缩为含「临床综合征」的表述               | 根节点应是可 schema 化的综合征（如高钙血症），而非零散体征罗列    |
| **Diagnostic schema（诊断框架）**      | Cammarata & Dhaliwal 综述：框架把大量疾病压缩为「疾病组」 | 一级分支应是 **方向/族**，不应把 CML、AML 等具体病名混在同一层 |
| **Can't-miss（不可漏诊方向）**           | Isabel、DXplain 等 DDx 工具强调 **灵敏度优先**     | 宁可多 1–2 个方向，不可漏掉正确方向                   |
| **MECE**                         | 管理/临床教育中「互斥且完备」的划分原则                    | 同一层只选一个主分类轴，各分支不重叠、尽量覆盖                |


**研究必要性**：若一级分支漏掉正确答案所在族，下游再精确的数值证据也无法「找回」该方向——这是鉴别诊断生成器文献中强调的 **召回优先（recall-first）** 问题。

### 1.3 本阶段如何衡量成功


| 指标            | 通俗含义                                                          |
| ------------- | ------------------------------------------------------------- |
| **L1 目标召回**   | 正确答案所属的 **一级族** 是否出现在候选列表中                                    |
| **L1 强制覆盖**   | 临床上的「不可漏诊族」有多少比例被召回                                           |
| **轴可分性**      | 同一分类轴上，**相反的两个轴极**是否 **都被** 召回；只召回一侧则无法正确切分分支（轴极定义见 **§2.7**） |
| **L2 子族召回**   | 在正确的一级方向下，更具体的子类（如 PTHrP 相关高钙）是否被召回                           |
| **综合分（Comp）** | 上述四项的平均，用于对比不同算法配置                                            |


---

## 2. 术语与机制（Plaintext 详解）

本节 **不依赖任何外部文档**。后文若再次提到下列概念，含义与此一致。

### 2.1 基础缩写


| 术语          | 解释                                                          |
| ----------- | ----------------------------------------------------------- |
| **L1 / L2** | 诊断树第 1 / 2 层；L1 = 诊断方向/族，L2 = 具体疾病或子类                       |
| **MECE**    | Mutually Exclusive, Collectively Exhaustive：互斥且尽量完备         |
| **轴极**      | 分类轴上 **须成对考虑** 的相反代表方向（如高钙：PTH 介导 ↔ 恶性肿瘤）；详见 **§2.7**       |
| **CPG**     | Clinical Practice Guideline，临床实践指南（含开放获取全文、WikEM、Merck 手册等） |
| **RAG**     | Retrieval-Augmented Generation：先检索知识库文本片段，再供规则或大模型使用        |
| **DDx**     | Differential Diagnosis，鉴别诊断                                 |
| **SNOMED**  | 国际医学术语标准；本研究用其中的 **disorder（疾病）** 名称表做字典匹配                  |


### 2.2 核心组件（用日常语言）


| 名称                            | 是什么                       | 做什么                                               |
| ----------------------------- | ------------------------- | ------------------------------------------------- |
| **BranchCreator**             | 流水线中的大模型模块                | 在已有「分支知识框架」约束下，为一级分支 **命名、排序**                    |
| `**branch_knowledge`（分支知识包）** | 注入 BranchCreator 的结构化说明   | 含：用哪条 **分类轴**、哪些 **强制域**、各域下有哪些代表疾病等              |
| `**syndrome_axis_map.json`**  | **人工编写** 的配置文件            | 约 11 个综合征 → 预先写好的 L1 轴与域（**原始基线**）                |
| `**GuidelineBranchSource`**   | 本研究核心：**自动召回** 候选疾病族的程序模块 | 从指南语料检索文本 → 从中 **找出** 可能的一级候选疾病/族，供下游使用           |
| **Spotter（字典匹配抽取器）**          | **不用大模型** 的确定性程序          | 在检索到的英文文本里，按 SNOMED 疾病名表做 **最长匹配**（类似在 Word 里搜病名） |
| **recall_llm（大模型有依据抽取）**      | 大模型读 **摘要片段**             | 只许列出 **片段中出现过** 的疾病名，不许凭空编造；与 Spotter 结果合并        |


### 2.3 检索与语料（读者常困惑处）


| 名称                | 解释                                                                             |
| ----------------- | ------------------------------------------------------------------------------ |
| **Chunk（文本块）**    | 把长文章切成的小段，每段约数百字，带标题与元数据；检索时 **按块** 返回，不是整本书                                   |
| **TF-IDF 检索**     | 按 **词面重叠** 排序：查询词与块中词越重合，排名越前；**不懂同义词**（「Pancoast」与「肺尖肿瘤」无共同字母则难召回）            |
| **MedCPT**        | 美国 NCBI 发布的 **医学文献专用** 双塔向量模型；短问句与长文档可在 **语义空间** 匹配（Bioinformatics 2023）       |
| **Hybrid（混合检索器）** | **两路并行**：一路 TF-IDF，一路 MedCPT；两路排名用 **RRF（按名次融合）** 合并。**不是** 用 MedCPT 替换 TF-IDF |
| **RRF**           | Reciprocal Rank Fusion：两路检索各给名次，按公式合并，避免某一路完全 dominate                         |


### 2.4 「同一篇文章内的鉴别诊断扩展」（原 `expand_ddx_siblings`）

**问题背景**：临床指南常把一篇长文切成很多块。检索时可能只命中 **「某综合征的概述/入口」** 这一块，而 **完整的鉴别诊断列表** 在同文的 **其它块** 里（例如「鉴别诊断」「评估」「病因」小节）。

**机制（通俗步骤）**：

1. 检索先返回若干 **文本块**，每块带有 **文章编号**（本项目中为 `source_id`，同一 PDF/同一 WikEM 条目共享同一编号）。
2. **扩展程序** 查表：「这些块来自哪几篇文章？」→ 把 **同一篇文章内**、标记为「含鉴别诊断信息」的 **其它块** 一并取出。
3. 这样，即使入口块没写全 DDx，**同篇 sibling 块** 里的疾病名仍可被后续步骤看到。

**Oracle 上界实验**（假设扩展「完美」时语料是否够用）：在 8 题罕见病例上，仅入口块常 **找不到** 标准答案词；**入口 + 同篇扩展** 后 **8/8 都能在同一篇文章的相关块中找到答案信息**——说明 **数据本身够**，瓶颈在检索与抽取工程。

### 2.5 WikEM 的「链接列表合成块」（原 `wiki_links` 合成块）

**WikEM** 是急诊/open 医学 wiki。其综合征页面除正文外，常有 **结构化链接列表**：指向「应考虑的疾病 A、B、C…」。

有时正文 prose **没写出** 某病全名，但链接列表里有。系统因此 **人工构造一条虚拟文本块**：把链接里的病名拼成一段文字，供字典匹配器读取——相当于把 **页面自带的 DDx 清单** 变成可搜索的文本。

**实测**：在本基准上 **几乎无额外增益**（与 TF-IDF 主路径重复较多），但机制保留作兜底。

### 2.6 闭包的两种用法：「灌入字典匹配池」vs「只供大模型阅读」

这是本研究 **最重要的工程发现之一**。同一套「同篇扩展块」，**送给谁读** 决定效果好坏。

#### 模式 A：灌入字典匹配池（旧默认，有害）

```text
检索 top-30 块
  + 同篇扩展块（可能再增加 60–80 块）
  → 全部合并
  → 字典匹配器（Spotter）在「所有块」里搜病名
  → 每个病名出现一次就加分
  → 取得分最高的 40 个病名
```

**为何有害**：常见病（如心肌梗死、荨麻疹）在 **很多块里重复出现**，得分 **累加**，占满 **40 个名额**；罕见但正确的病（如 glucagonoma）只出现一次，被挤出名单。

**本报告将上述现象称为「候选池拥挤」**（即：40 个疾病名名额被重复出现的常见病占满）。

#### 模式 B：只供大模型阅读（grounding，改进后采用）

```text
检索 top-30 块  →  仅给 Spotter 做字典匹配
同篇扩展块      →  不进入 Spotter；只整理成 ≤24 条短摘要
                 →  供大模型做「有依据抽取」
```

**效果**：Spotter 不再被扩展块里的 **重复常见病** 淹没；扩展块里的 rare DDx 仍可通过 **大模型读摘要** 进入候选。实验上 **与完全关闭扩展的效果在 Spotter 侧相同**，但大模型侧仍能利用扩展信息。

**工程细节（§14.2）**：`_retrieve_snippets()` 在 **grounding 模式** 下对 **每条 query 仍始终** 调用 `expand_ddx_siblings`；只是扩展块 **不进 Spotter 池**，经门控后进入 ≤24 条 FIFO。因此闭包对 LLM 的潜在贡献取决于 **排序与 cap**，而非是否 expand — 实测 sibling 进 24 条 **0/8**（§14.4）。

**对比一句话**：  

- **灌池** = 让「Ctrl+F 搜病名」在读 **整本文**；  
- **grounding** = 「Ctrl+F」只读 **检索 top 段**，扩展段 **只给医生助手（LLM）看摘要**。

### 2.7 轴、轴极与轴可分性（读者易混处）

临床上一类综合征往往用 **一条主分类轴** 把病因/机制切成几个 **互斥方向**。本报告中的用语对应关系如下：


| 术语                     | 通俗含义                                                      | 高钙血症示例                                                                        |
| ---------------------- | --------------------------------------------------------- | ----------------------------------------------------------------------------- |
| **分类轴（axis）**          | 「按什么维度切 L1 分支」                                            | **机制轴**（mechanism）：按「高钙是怎么来的」切，而非按器官或按具体病名                                    |
| **L1 域 / mandatory 域** | 轴上的 **一个诊断方向（族）**；3–7 个，互斥且尽量完备                           | 「PTH 介导」「恶性肿瘤相关」「维生素 D/肉芽肿性」「药物/其它」                                           |
| **轴极（axis pole）**      | 在该轴上 **临床意义相反、或至少须并列考虑的一对（或一组）代表方向**；漏掉一侧会导致 **整棵树的切分错误** | 机制轴上最典型的 **两极**：**PTH 介导** ↔ **恶性肿瘤相关**（原发甲旁亢/维生素 D 过多 vs PTHrP/溶骨转移——处理路径相反） |
| **轴可分性**               | 评测指标：上述 **相反轴极是否都进了候选**（或都进了 mandatory 覆盖）                | 只召回「PTH 升高→甲旁亢」而 **没** 召回「恶性肿瘤/PTHrP」→ 轴可分性 **差**，即使某个具体病名命中也算失败              |
| **轴污染**                | 把 **本应分开的两极** 合成同一支，或 flat 排序/本体归族把 **相反机制** 并为兄弟         | 例如把「原发性甲旁亢」与「恶性肿瘤高钙」 **合并成一支** → 下游 LR 无法沿正确轴调整                               |


**为何需要「轴极」而不只说 mandatory 域？**  
mandatory 列表可能有 4–7 个域；**轴极** 特指其中 **定义临床切分、且彼此对立** 的那几对——评测时单独看它们是否 **成对出现**。高钙除 PTH↔malignancy 外，还有肉芽肿、药物等域，但 **轴可分性** 最常盯 **PTH 与 malignancy 是否同在**。

**与 can't-miss、轴极注入的关系**：

```text
can't-miss 表（WikEM 等）
  → 列出某综合征下「不可漏诊」的代表疾病/族名
  → 其中往往 **覆盖相反轴极**（如高钙同时含 humoral hypercalcemia of malignancy 与 primary hyperparathyroidism）

轴极软注入（IMP-60，inject_poles）
  → 若检索+Spotter 后，某 can't-miss 族 **完全没进** 40 名候选
  → 程序 **抬高其分数** 塞进候选（软注入：分数有下限，仍可能被更强 hit 挤后）

can't-miss 硬层（IMP-56，cant_miss_hard）
  → 上述注入名 **保证不被** max_candidates=40 截断裁掉
```

**实测边界**：当前 can't-miss 表按 **WikEM 症状页 id** 组织，与 **hypercalcemia** 等化验/内分泌综合征 **不对齐** → 轴极注入在本 14 题矩阵上 **几乎无增益**（§6.13）；机制仍保留，待扩展 can't-miss 数据源。

### 2.8 其它关键参数（用后果解释，不背代码名）


| 参数/机制                   | 通俗含义                                                                                                                                                                                 |
| ----------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **max_candidates = 40** | 最终 **疾病名候选** 最多保留 40 个（不是 40 个文本块）                                                                                                                                                   |
| **top_k = 30**          | 检索最初返回 30 个文本块                                                                                                                                                                       |
| **本体反向归族（IMP-64）**      | Spotter 后 **>40** 病名时：若某 SNOMED **超族** 在 flat top-40 **零成员**，从 40 名外取该族 **分数最高的一名具体病** 替换 **末尾最多 5 槽**；**不用族名替换具体名**，≤40 时不生效。详见 **§2.9.1**                                          |
| **机制/标志物直提名（IMP-58）**   | 对 `syndrome + context` 做 **curated 子串匹配**（`pathognomonic_markers.json` + `mechanism_to_disease.json`），将 **具体病名** 以 ≥0.6×当前最高分写入 `recall()` 的 **40 实体 dict**；**不走 RAG**。详见 **§2.9.2** |
| **can't-miss 轴极注入**     | 若 can't-miss 表里代表 **某一轴极** 的病名/族名完全没进候选，则 **抬高分数** 写入（见 **§2.7**）                                                                                                                    |
| **can't-miss 硬层**       | 上述注入名 **保证不被** 40 名截断裁掉（与软注入配合，IMP-56）                                                                                                                                               |
| **五路 query 扇出**         | 除「X 的鉴别诊断」外，再发「机制/解剖/危重/检查/症状」等 5 类查询并合并；**本底 TF-IDF 上实测有害**                                                                                                                         |


### 2.9 IMP-64 / IMP-58 实现消歧（代码口径）

> **目的**：澄清报告里「族」「保留名额」「直提名」在 **代码里指什么、作用在谁身上**。实现位置：`guideline_branch_source.py`（`_rollup_candidates`、`_nominate_from_context`）、`auto_axis.py`（`_taxonomy_groups`）。

#### 2.9.1 本体反向归族（IMP-64）

**一句话**：当 Spotter 产出 **超过 40** 个病名时，用 SNOMED `is_a` 检查：若某 **超族**（覆盖 2–70% 候选、最多 6 组）在 **按频次取的前 40 名中无任何成员**，则从 40 名之外取该族 **分数最高的一名具体病**，替换 flat top-40 **末尾最多 5 个槽位**；**不**用族名替换具体名，**≤40** 候选时不生效。

**常见误解 vs 实际**


| 误解                        | 实际                                                                         |
| ------------------------- | -------------------------------------------------------------------------- |
| 「CML 被挤出就用髓系肿瘤 **族名** 替换」 | **不替换**；保留 **具体病名字符串**，只调整 **谁进 top-40**                                   |
| 「整族只留一个代表」                | 仅当该 **SNOMED 超族在 flat top-40 里一个成员都没有** 时，从 **40 名之外** 捞回该族 **分数最高的一名具体病** |
| 「所有候选都先归族再排序」             | 仅当 **spot 后实体数 > 40** 才运行；≤40 时 **整段 rollup 不生效**                          |


**输入范围**

```text
Spotter 对所有 snippet 累分 → scored 字典（常 >> 40，如 80–200+ 个病名）
         ↓
仅当 len(scored) > max_candidates(=40) 才调用 _rollup_candidates
         ↓
对 scored 的 **全部 key** 做 SNOMED is_a 分组（不是只对前 40）
```

**族怎么定**（`KBAxisMap._taxonomy_groups`）：

- 在 **全部 spotted 候选** 上，找 SNOMED `is_a` 祖先；
- 只保留覆盖 **2～70% 候选** 的祖先（太宽如 root `neoplasm` 不要）；
- 每个病归到 **最具体** 的可用祖先；
- 最多保留 `**max_domains=6`** 个最大超族组（组名是 SNOMED 概念名，如 myeloid neoplasm 类，**不是** L1 mandatory 域名）。

**孤儿**（`rollup_mode="family+orphan"`，A9l 等）：SNOMED 挂不上的（adhesions、peliosis、foreign body）在分组逻辑里 **各自算一个「单成员族」**，以便也能走「整族缺席→补代表」逻辑。

**输出：名额与替换对象**


| 参数             | 值                                                               | 含义                     |
| -------------- | --------------------------------------------------------------- | ---------------------- |
| `K`            | **40**                                                          | `max_candidates`       |
| `flat_top`     | 按频次分 **前 40**                                                   | 原 flat 排序结果            |
| `missing_reps` | flat top-40 **一个都没有** 的超族里，按 **全量 scored 分数** 每族取 **最强 1 个具体名** | 不是族名                   |
| `n_reserve`    | **min(缺席族数, max(1, 40//8)) = 最多 5 槽**                           | 约 **12%** 槽位可被「补族代表」替换 |
| 被挤掉谁           | **flat_top 中分数最低的 n_reserve 名**                                 | 通常是末尾常见病               |


实现（`guideline_branch_source.py`）：`keep = flat_top[: K - n_reserve] + missing_reps[:n_reserve]`，再按分数重排并强制写入 top-K。**不**把 top-40 改成 6 个族名。

**数值例（CML）**：若 `chronic myeloid leukemia` 分数排第 55，但 flat top-40 里 **没有任何** 髓系肿瘤族成员，且该族在 `missing_reps` 里排前 — 可能以 **「chronic myeloid leukemia」这串字** 换掉 top-40 **末尾 1～5 名** 之一；**不会** 在候选里新增一条叫「髓系肿瘤族」的 key。

**消费对象**


| 消费者                                      | 用法                                                                       |
| ---------------------------------------- | ------------------------------------------------------------------------ |
| `**GuidelineBranchSource.recall()` 返回值** | `{病名字符串: 分数}`，默认 **≤40 项**                                               |
| **评测**（`eval_branch_multilevel`）         | 对 `cand1.keys()` 做 **token 家族匹配**（L1tgt / mandatory / 轴可分）               |
| **MECE**（`eval_mece_arm`）                | 对每个候选名 `project_entity` → L1 域                                           |
| **BranchCreator**                        | 实验栈里 recall 与 UnionAxisMap/方案 A 并联；rollup **不直接** 写 `mandatory_coverage` |


rollup **不管** 24 条 LLM 摘要；只改 **40 实体槽** 的组成。案例与指标见 **§6.12**。

#### 2.9.2 机制 / 标志物直提名（IMP-58 + pathognomonic）

**一句话**：对 `syndrome + context` 做 **curated 子串匹配**（`pathognomonic_markers.json` 24 条 + `mechanism_to_disease.json`）；命中则将 **target 具体病名** 以 **≥0.6×当前最高分** 写入 `recall()` 的 **40 实体候选 dict**（评测与 MECE 投影消费）；生产 BranchCreator 另经 **T1 marker → project_entity → candidate_entities_by_domain** 按域注入，不依赖 RAG 命中。

**常见误解 vs 实际**


| 误解                          | 实际                                                                                                        |
| --------------------------- | --------------------------------------------------------------------------------------------------------- |
| 「Horner → 直接写 Pancoast，无依据」 | 依据是 **两张 curated 表 + 子串匹配**，不是 LLM 推断                                                                     |
| 「绕过整个 pipeline」             | 只 **绕过 RAG 检索/Spotter 频次**；仍进 `recall()` 的 **scored → top-40**                                            |
| 「与生产 controller 完全同一通路」     | **实验臂**在 `GuidelineBranchSource.recall()`；**生产** `_build_branch_candidates` 另有 **T1 marker → 域投影** 通路（见下） |


**触发依据（两类，OR 关系）**

输入文本：`text = f"{syndrome} {syn} {context or ''}".lower()`

**(a) Pathognomonic 表** — `data/knowledge_raw/pathognomonic_markers.json`（24 条，WHO/教材来源，带 LR+ 注释）

- 规则：`any(term in text for term in marker.terms)` → 追加 `marker.target_diseases`
- c1 例：context 含 `horner syndrome` / `apical lung tumor` 等 → 提名 `pancoast tumor`, `superior sulcus tumor`, `apical lung tumor`, `pancoast syndrome`（`highly_specific`，LR+≈25，**不是** pathognomonic 级 100+）

**(b) 机制表** — `mechanism_to_disease.json`，经 `DiseaseNameResolver.nominate_from_text`

- **exact**：normalized 短语 **子串** 出现在 text，且 key **长度 ≥ 6**（例：`apical lung tumor` → `pancoast tumor`）
- **family_expansions**：text 含某 `any_keywords` → 追加该组 **全部 entities**（最多 **12** 个/次）

**不做的事**：无 embedding、无因果推理；短词不过度触发（key≥6）；`_GENERIC_NAMES` 过滤。

**写入规则与「硬保留」**


| 项                             | 值                                               |
| ----------------------------- | ----------------------------------------------- |
| `floor`                       | `0.6 × max(spotted 分数)`，与 IMP-60 轴极注入同量级        |
| 提名分                           | **1.05 × floor**（略高于 cant_miss 软注入，低于强 spot 命中） |
| `resolver.expand_to_entities` | 再提名关联具体名，**0.95 × floor**                       |
| `cant_miss_hard=True`（A8/A9l） | `forced` 里 key 若被 top-40 裁掉 → **强制塞回**          |


仍可能：提名分低于前 40 名且 **未开 hard** 时被裁 — A9l 开 hard 后 c1 可 `spotted_not_in_snippets`（检索无、候选有）。

**消费对象（两条链）**

**链 A — 实验 / `GuidelineBranchSource.recall()`（A7/A9l）**

```text
nominate → scored → top-40 dict
    → eval：family_matched(c["l1_target"], cand.keys())
    → eval_mece：project_entity(name, syndrome_entry)
    → recall_llm / Spotter 并集后的 **扁平病名候选池**
```

评测 **只看 key 里是否出现 gold 家族 token**，不看提名分高低。

**链 B — 生产 `controller._build_branch_candidates()`（§23.14）**

```text
case 全文 → SyndromeAxisMap.match
    → 对每个 domain 填 candidate_entities_by_domain
    → T1：diagnostic_markers 子串命中 → target_diseases → project_entity → 按 **域** 归档
    → 注入 payload["branch_knowledge"] → BranchCreator LLM
```

与链 A **数据源相近**（marker 表），但 **不调用** `GuidelineBranchSource.recall(nominate=True)`；产出是 **按 L1 域分桶的实体列表**，不是 flat 40 名。案例见 **§6.10**。

#### 2.9.3 对照表


| 维度           | 本体反向归族（IMP-64）              | 机制/标志物直提名（IMP-58）                                |
| ------------ | --------------------------- | ------------------------------------------------ |
| **何时运行**     | spot 后 **>40** 实体           | `nominate=True` 时每轮 `recall()`                   |
| **作用范围**     | 全量 scored 分组，**最多改 5/40 槽** | 命中几条写几条进 scored                                  |
| **改的是名还是排序** | 只 **换进 top-40 的具体病名**       | **新增/抬高** 具体病名分数                                 |
| **族从哪来**     | SNOMED is_a（2–70% 覆盖，≤6 超族） | family_expansions 关键词组（curated）                  |
| **依据**       | 本体结构 + 频次分                  | pathognomonic / mechanism **子串表**                |
| **主消费者**     | `recall()` top-40 → 评测/投影   | `recall()` top-40；生产另路 → **branch_knowledge 按域** |
| **与检索关系**    | 检索后、截断前                     | **完全不走** snippet 检索                              |


### 2.10 实验「臂」（Arm）是什么

**臂** = 一套 **固定开关组合** 的算法配置，用于公平对比。代号 **A0–A12** 无数学含义，仅是实验标签。  
**hand 标签** = 评测时 **人工指定** 综合征名称，排除上游根节点选择误差，**只测** 分支召回模块。

---

## 3. 知识注入在本阶段的应用：完整基础流程

**本节是后文所有「改进」的前提。** 若不理解本节，则无法判断：为何要做 grounding、直提名、MedCPT 混合等改动——它们都是针对 **同一条流水线** 上不同环节的工程修补。

本阶段存在 **三条可切换的知识注入路径**，终点相同、起点与中间步骤不同：

```text
                    ┌─────────────────────────────────────────┐
                    │  共同终点：branch_knowledge 结构化包     │
                    │  → BranchCreator 大模型命名 L1 分支      │
                    │  → _enforce_mandatory_branches 兜底注入  │
                    └─────────────────────────────────────────┘
                                        ▲
          ┌─────────────────────────────┼─────────────────────────────┐
          │                             │                             │
   路径 1：纯手工              路径 2：A∪C 并集              路径 3：CPG/RAG 自动化
   SyndromeAxisMap              UnionAxisMap                 GuidelineBranchSource
   （11 综合征 JSON）           （A 缓存 + C 种子 + 手工兜底）  （~20 万指南块检索+抽取）
```

**生产流水线现状（如实说明）**：`controller.py` 默认仍走 **路径 1 或 2**（StatPearls+教科书 FAISS 索引，**不含** 实验用 CPG 语料）；**路径 3** 及后文 A0–A12 实验臂 **主要在隔离评测脚本** 中运行。下文先讲 **设计意图与完整框架**，再在第 5 节讲在此框架上的增量改进。

---

### 3.1 共同契约：`branch_knowledge` 注入块

无论哪条路径，运行时最终都要产出同形 JSON，注入 BranchCreator 的 payload。核心字段：


| 字段                             | 含义                                                   | 临床作用                              |
| ------------------------------ | ---------------------------------------------------- | --------------------------------- |
| `l1_classification_axis`       | 本综合征 **唯一** L1 分类轴（如 mechanism / etiology / anatomy） | 约束分支 **互斥** 的切分维度                 |
| `mandatory_coverage`           | 3–7 个 **MECE 域/族** 名称列表                              | **不可漏诊方向**；LLM 若漏命名，控制器会 **机械注入** |
| `candidate_entities_by_domain` | 各域下的代表 **具体疾病**（L2/L3 线索）                            | 供下游子分支与证据检索 **下推**，**不是** L1 标签本身 |
| `syndrome_matched`             | 命中的综合征 id（溯源）                                        | 日志与评测                             |


**组装位置**：`controller._build_branch_candidates(state)` —— **确定性、无随机性**（表查找 + 标志物投影 + 可选 taxonomy 展开）。BranchCreator 大模型只负责 **在 mandatory 框架内起分支名、估先验**；召回保证由知识块承担。

**设计原则（schema-first，来自架构研究与实施约束）**：


| 原则                          | 含义                                                                                      | 对 A9l 全栈的影响                                    |
| --------------------------- | --------------------------------------------------------------------------------------- | ---------------------------------------------- |
| **覆盖由 schema 决定，不由 LLM 决定** | `mandatory_coverage` 来自手工 map / A∪C 种子 / 方案 A LLM 起草；BranchCreator **不得删除** mandatory 域 | `_enforce_mandatory_branches` 机械补枝；证据只调优先级，不删域 |
| **证据感知、知识校验**               | 检索/抽取实体须能 **投影到域**；投影失败时注入 residual 域（IMP-55，**🔴 待落地**）                                | 召回层（A9l）与覆盖层（方案 A / A∪C）**分轨评测**（§6.19）        |
| **LLM 接地门**                 | 方案 A / A 源缓存中实体须 **逐字出现在检索摘要**（IMP-11，**🔴 待落地**）                                       | 防 LLM 幻觉 MECE；与 GARMLE-G②「有依据抽取」同构             |
| **域粒度 mandatory**           | L1 标签是 **族/域**，禁止把 CML、Pancoast 等具体病名当 L1 分支                                            | 直提名写入 **候选实体池**，再投影到域（规格见 **§2.9.2**）          |
| **VINDICATE 仅作兜底**          | 专用综合征用 **临床 schema**；仅 broad/unknown root 才退化到 VINDICATE 式病理筛                           | 避免 L1 爆炸到 9+ 方向                                |


```text
病例文本（case_summary + 原子事实）
  → ① 综合征识别（关键词 或 LLM 抽根）
  → ② 取得 L1 轴 + 域分区（手工 / A∪C / CPG 方案A / SNOMED 分区）
  → ③ _build_branch_candidates：标志物→疾病→投影到域
  → ④ branch_knowledge 注入 BranchCreator
  → ⑤ _enforce_mandatory_branches：漏掉的 mandatory 域 **强制补枝**
```

---

### 3.2 路径一：纯手工基线（`SyndromeAxisMap`）

#### 3.2.1 依赖的四类静态知识


| 产物                           | 规模        | 在流水线中的位置                       |
| ---------------------------- | --------- | ------------------------------ |
| `syndrome_axis_map.json`     | 11 个综合征   | ② 轴 + 域 + 识别关键词                |
| `pathognomonic_markers.json` | 24 条      | ③ T1 标志物 → 目标疾病 → 投影到域         |
| `mechanism_to_disease.json`  | ~47 条     | 评测 gold 归一；选项机制措辞映射            |
| `branch_creator.txt` B1–B5   | 5 个血液学域示例 | Prompt **风格示范**（非 runtime 数据源） |


#### 3.2.2 逐步流程

```text
【步骤 0】上游 RootSelector 输出 presenting syndrome（如 "hypercalcemia"）

【步骤 1】SyndromeAxisMap.match(case_text)
         用 syndrome_keywords 做子串匹配（如 "hypercalcemia", "elevated calcium"）
         → 命中 id=hypercalcemia 的 entry

【步骤 2】entry 已含：
         axis = "mechanism"
         domains = [
           "PTH-mediated (parathyroid)",
           "malignancy-associated (PTHrP / osteolytic)",
           "vitamin-D / granulomatous",
           "other (drug / endocrine / immobilization)"
         ]
         每域有 member_keywords（供 project_entity 把疾病名归到域）

【步骤 3】_build_branch_candidates
         扫描病例：若出现 "Philadelphia chromosome" → CML → 投影到 "myeloid neoplasm" 域
         （高钙血症例通常无 T1 命中，entities_by_domain 可能较空）

【步骤 4】branch_knowledge 注入 BranchCreator + _BRANCH_KNOWLEDGE_DIRECTIVE
         LLM 必须在 4 个 mandatory 域下各建一支，不得合并 PTH 与 malignancy

【步骤 5】_enforce_mandatory_branches
         若 LLM 漏写 "malignancy-associated" → 控制器 **自动插入** 该族分支
```

#### 3.2.3 案例走查：hypercalcemia（纯手工路径）

**输入**：病例含「血钙升高、PTH 偏低、既往鳞癌」等。


| 步骤            | 发生了什么                 | 产出                     |
| ------------- | --------------------- | ---------------------- |
| 识别            | 关键词命中 `hypercalcemia` | id = hypercalcemia     |
| 分区            | 读 JSON，**无需检索**       | 4 域 mechanism 轴，**写死** |
| 标志物           | 若无 Philadelphia 等     | entities 可能为空          |
| BranchCreator | 见 mandatory 四域        | 分支如「甲旁腺介导」「恶性肿瘤相关」…    |
| 兜底            | 若 LLM 只写 3 支          | 第 4 域 **机械补入**         |


**优点**：稳定、可复现、MECE 结构 **临床正确**。  
**局限**：

1. 每增一个综合征需 **人工写** 轴与域 → 扩展成本 O(综合征数)。
2. 仅 11 个 id；c1 **Pancoast**、c13 **glucagonoma** 等 **无专用条目**（或落在过宽的 `focal_limb_neuro_deficit` 上仍依赖人工 keywords）。
3. StatPearls / PMC 中「高钙怎么鉴别」的 **海量 prose 未利用**。

#### 3.2.4 旁路失败：纯 SNOMED 自动分区（`KBAxisMap`）

曾尝试跳过手工 map，仅用 SNOMED `is_a` 把召回的具体病 **自动聚成 L1 域**：

- **现象**：具体病名能召回一些，但 **mandatory 域覆盖差**、轴方向常错。  
- **原因**：本体树按 **疾病层级** 组织，不按 **就诊综合征的临床鉴别轴**（如 leukocytosis 应按 reactive vs myeloid vs lymphoid，而非 SNOMED 默认分支）。  
- **结论**：SNOMED 可作 **实体归一与辅助 rollup**，**不能** 单独充当 mandatory 分区权威。

---

### 3.3 路径二：A∪C 并集模式（`UnionAxisMap`）

**动机**：在 **不降低** 手工 map 覆盖率的前提下，用 **离线 LLM + 极小 curated 种子** 替代「为每个综合征手写整份 JSON」。

#### 3.3.1 两源定义


| 符号         | 名称                             | 内容                                                         | 生成方式                                                   |
| ---------- | ------------------------------ | ---------------------------------------------------------- | ------------------------------------------------------ |
| **C**      | Curated mandatory-floor **种子** | `syndrome_override_seeds.json`，约 7 个 hard 综合征              | 人工审核的 **域骨架 + mandatory 标记 + 代表实体**                    |
| **A**      | LLM 轴 **缓存**                   | `auto_axis_cache.json`（或 CPG 侧 `auto_axis_cache_cpg.json`） | 离线调用 `build_branch_knowledge_llm`：读检索摘要 → LLM 定轴+分族+实体 |
| **手工 map** | 识别 + **兜底**                    | 原 `syndrome_axis_map.json`                                 | 关键词匹配；A、C 皆空时 **原样退回**                                 |


**关键设计**：**识别层** 仍用手工 map 的关键词（轻量、已验证）；**分区层** 用 A∪C 合并结果。

#### 3.3.2 合并算法（域级 UNION，C 优先）

```text
1. match(text) → syn_id（如 hypercalcemia）
2. 取 a_entry = LLM 缓存[syn_id]（可选 live 生成写回缓存）
3. 取 c_entry = override_seeds[syn_id]
4. _merge(a_entry, c_entry)：
     • C 的 domains = 权威骨架 + mandatory 列表
     • 对 A 的每个域：找与 C **实体重叠最大** 的域 → A 的实体 **折叠进** 该 C 域（加性）
     • A 有而 C 无的域 → **追加**（不丢弃任何召回族）
     • 追加时剔除「C 已在其它域拥有的同义实体」（防 A 冗长措辞抢走归属）
5. 若 merge 为空 → 退回手工 map 的 entry（覆盖 **永不低于** 纯手工）
```

#### 3.3.3 配置开关（生产推荐组合）

```text
enable_branch_knowledge = True
union_axis_ac = True
llm_axis_cache_json = data/knowledge_raw/auto_axis_cache.json
override_seeds_json = data/knowledge_raw/syndrome_override_seeds.json
branch_llm_axis_live = False   # 生产默认关：缺缓存时不实时调 LLM
```

#### 3.3.4 案例走查：hypercalcemia（A∪C 路径）

**C 种子（节选）**——只 pin **3 个 mandatory 域** + 代表实体：

```text
PTH-mediated hypercalcemia [mandatory]
  → primary hyperparathyroidism, familial hypocalciuric hypercalcemia, …
Malignancy-associated hypercalcemia [mandatory]
  → humoral hypercalcemia of malignancy, osteolytic metastasis, myeloma, …
Vitamin D / granulomatous
  → sarcoidosis, vitamin d toxicity, milk-alkali syndrome, …
```

**A 缓存（LLM 离线生成）**——可能多出第四域「药物/ immobilization」及更长的实体列表（如 tertiary hyperparathyroidism）。

**合并结果**：


| 域                         | 来源                   | 说明           |
| ------------------------- | -------------------- | ------------ |
| PTH-mediated              | C 骨架 + A 实体折叠        | mandatory 保留 |
| Malignancy-associated     | C 骨架 + A 的 PTHrP 同义词 | mandatory 保留 |
| Vitamin D / granulomatous | C + A                | 可选 mandatory |
| other (drug / …)          | 仅 A、无 C 对应           | **追加**，不丢弃   |


**与纯手工对比**：hypercalcemia 在手工 map 里 **本就有** 完整 4 域 → A∪C 在此例主要是 **丰富 entities**，结构相近。A∪C 的增益体现在 **手工 map 没有、但 C 种子 pin 住的 hard 综合征**（见下例 c1）。

#### 3.3.5 案例走查：c1 Pancoast（A∪C 为何必要）

**Gold**：pancoast tumor；**Syndrome id**：`focal limb neuro deficit`（手工 map 有宽泛 entry，但 **无** pancoast 专用 id）。


| 路径          | 能否保证 gold 域存在                                                                  | 域归属                            |
| ----------- | ------------------------------------------------------------------------------ | ------------------------------ |
| 纯手工 map     | 域「compressive plexopathy」含 keyword `pancoast`                                  | 依赖 keywords 投影                 |
| 仅 A（LLM 缓存） | 可能生成 anatomy 轴 + compressive 域                                                 | 措辞冗长时不稳定                       |
| **A∪C**     | C 种子 **强制** `Structural / compressive lesion` [mandatory]，实体含 `pancoast tumor` | **8/8 gold-domain 100%**（隔离评测） |


**要点**：A∪C 不是「用 LLM 替代临床判断」，而是 **C 提供不可妥协的 MECE 地板**，A 提供 **广覆盖实体**，手工 map 提供 **识别与最后兜底**。

---

### 3.4 路径三：CPG/RAG 自动化框架（实验主路径）

**动机**：从 **开放指南语料**（WikEM、PMC-OA、Merck、NICE 等）**自动** 产生 A 源缓存、或直接产生候选疾病集，摆脱「每个综合征手写 JSON」。

#### 3.4.1 离线阶段：Raw → 可检索索引

```text
【阶段 0】HTML/PDF/NXML 原文
    → build_cpg_chunks.py 切分为 cpg_chunks.jsonl（全库 ~36 万条）
    每条 chunk 带：source, source_id, chunk_type, syndrome_anchor, wiki_links, content

【阶段 1】过滤 + 向量化（build_cpg_tfidf_index.py）
    → 保留 chunk_type ∈ {differential, red_flag, evaluation, recommendation}
    → 长度 ≥120、去重、去 Cookie 噪声
    → 实验索引 cpg_index/：203,830 条 TF-IDF（80k 特征, 1–2 gram）
    → 可选：build_medcpt_cpg_index.py → 并联 MedCPT 向量索引（Hybrid 用）

此阶段 **无 LLM**。
```

**Chunk 示例（WikEM 腹部痛 geriatrics）**：

```json
{
  "source": "WikEM",
  "source_id": "wikem_syndrome__abdominal-pain-geriatrics",
  "chunk_type": "differential",
  "syndrome_anchor": "Abdominal pain (geriatrics)",
  "content": "Elderly … MI, dissection, mesenteric ischemia …",
  "wiki_links": ["MI", "aortic dissection", "SBO"]
}
```

#### 3.4.2 在线阶段：每个 case 的处理链（与 §20 逐步对齐）

```text
病例 vignette
  │
  ├─► [LLM-1] RootSelectorSurrogate（curated-free 实验）
  │         输入 vignette[:1500] → 输出 {"syndrome": "hypercalcemia"}
  │         （生产/Union 路径可改用手工关键词识别，不经过 LLM-1）
  │
  ├─► [阶段 4–8] GuidelineBranchSource._retrieve_snippets(syndrome, context)
  │         4–5 条确定性 query（如 "differential diagnosis of hypercalcemia"
  │         + "causes and etiology of …" + context 前 300 字增强）
  │         → 每 query TF-IDF top_k=30（Hybrid 臂并联 MedCPT + RRF）
  │         → expand_ddx_siblings：同 source_id 拉齐同篇 DDx 块（cap +60）
  │         → snippet_on_topic 门控
  │         → 格式化为 "[title] content[:400]"，硬上限 **24 条**（union 臂 36）
  │
  └─► 分叉为两条 **子路径**（下游不同，勿混读）
```

**子路径 3a — 方案 A（`build_branch_knowledge_llm`，cpg_llm / union_llm 臂）**

```text
≤24 条 snippet → [LLM-2] BranchKnowledgeBuilder（单次调用）
  任务：定单一 axis + 3–6 MECE domains + 每域 entities + mandatory 标记
  约束：entities 必须 grounded in excerpts（摘要里出现过）
  → branch_knowledge entry（与 SyndromeAxisMap **同 schema**）
  → 写 auto_axis_cache_cpg.json；可直接 project_entity(gold)
  → **不经过** max_candidates=40 实体池
```

**子路径 3b — 确定性 Spotter（recall()，cpg_det / A1–A12 实验臂）**

```text
检索 top-30 块 → Spotter：SNOMED disorder 词表最长 n-gram 匹配
  （可选 recall_llm：LLM 读 **同一套** ≤24 snippets，flat 列出疾病名）
  → 多 snippet 分数累加 → 排序 → **max_candidates=40** 疾病实体 dict
  → 下游 KBAxisMap.partition_from_candidates（SNOMED 分区）
     或 与方案 A entry 合并（hybrid 臂）
```

**核心事实**：LLM **从不直接读 36 万 chunk 库**；只读经检索、闭包、门控、截断后的 **~24×400≈9600 字符** prose 摘要。

#### 3.4.3 三平面架构（读参数时不混淆）

语料里是 **具体病名**；BranchCreator 要的是 **3–7 个 L1 域**。流水线在三个 **平面** 上操作：

```text
平面 1 — Chunk（文本块）     top_k=30 × ~5 queries → 闭包后可 200+ 块
平面 2 — Entity（疾病实体）   Spotter/LLM 抽取 → max_candidates=40
平面 3 — Domain（L1 域/族）   方案A 直接产出 MECE；或 SNOMED rollup 分区
```


| 参数               | 计量对象                     | 默认  | 常见误读           |
| ---------------- | ------------------------ | --- | -------------- |
| `top_k`          | 单次 query 返回的 **chunk 数** | 30  | ≠ 40 个病        |
| snippet 上限       | 喂 LLM 的 **摘要条数**         | 24  | ≠ chunk 总数     |
| `content[:400]`  | 单条摘要字符上限                 | 400 | 长 DDx 列表后半被截断  |
| `max_candidates` | Spotter 保留的 **疾病实体数**    | 40  | **方案 A 不经过此池** |


#### 3.4.4 flat Spotter 的结构性问题（理解后文改进的钥匙）

指南 DDx 块列举的是 **几十上百个具体病名**。Spotter 在 **实体平面** 直接竞争 40 个名额：

```text
具体病名（语料）
  → _spot() 词面命中 SNOMED
  → MI、urticaria、infection 等在多块重复 → 分数累加高
  → leukemoid、Pancoast、glucagonoma 仅 1–2 块 → 被挤出 top-40
```

因此 **路径 3b** 单独使用 Spotter 时，会出现「检索层有 gold 词、抽取层没有」（漏斗 Step 2 损失）。**路径 3a（方案 A）** 让 LLM **同时** 分族，绕过 flat top-40，但对 **eponym/机制名**（Pancoast）仍弱——需 **直提名**（第 5 节）。

**同篇扩展（expand_ddx_siblings）** 的角色：检索常只命中 **入口块**，完整 DDx 在同文其它块；扩展把 **source_id 相同** 的 sibling 块拉入。**Oracle 实验**：8 题罕见病例，入口块 alone 常 miss gold 词；**入口 + sibling → 8/8 块文本含 gold 信息** → 数据够，瓶颈在 **检索 rank + 抽取 + 截断**。

#### 3.4.5 案例走查：hypercalcemia（CPG 自动化路径）

**假设 curated-free**：LLM-1 输出 syndrome = `"hypercalcemia"`。


| 阶段    | 方案 A（3a）                                | Spotter 全栈 A9l（3b + 改进栈）                |
| ----- | --------------------------------------- | --------------------------------------- |
| Query | 4–5 条 TF-IDF query                      | 同左                                      |
| 检索    | Merck/PMC 块含 PTH、PTHrP、sarcoid、thiazide | 同左；扩展块 → **只给 LLM**，不灌 Spotter 池        |
| LLM-2 | 一次调用 → 4 域 mechanism 轴 + mandatory      | 无 LLM-2；用 Spotter+recall_llm 填 40 实体    |
| 实体    | 域内列 primary HPT, HHM, sarcoid…          | Spotter 抓 malignancy 相关词 + LLM 补 HHM 短语 |
| 评测    | L1 域直接来自 LLM entry                      | L1tgt/L1mnd 等矩阵指标；A9l Comp **0.812**    |


**与路径 1/2 对比**：CPG 路径 **不需要** 事先在 JSON 里写好 hypercalcemia 四域；域结构来自 **指南摘要 + LLM 分族**（或 Spotter+rollup）。代价是 **pipeline 更长、参数敏感**。

#### 3.4.6 案例走查：c1 Pancoast（CPG 路径的三层漏斗）

**输入**：syndrome = focal limb neuro deficit；context 含 apical lung tumor, Horner, arm pain；gold = pancoast tumor。

```text
层 1 检索：TF-IDF 对 "differential diagnosis of focal limb neuro deficit"
          → 常 **无** 字符串 "Pancoast"（词面鸿沟）
          → 同篇扩展后，块文本 **可能** 含 superior sulcus / apical mass（Oracle 8/8）

层 2 抽取：Spotter 只认 SNOMED 标准名 "pancoast tumor"
          → 若词面未出现 → spotted ✗，尽管 retrieved ✓

层 3 补救（第 5 节 IMP-58）：机制/标志物直提名
          → context 匹配 "apical lung tumor" + Horner
          → **绕过检索**，写入候选 pancoast tumor → spotted ✓
```

**三句话**：① 语料 **够**（闭包 Oracle）；② **词面检索不够**；③ A∪C 的 C 种子 + CPG 的 **直提名** 解决不同环节——前者保证 **域结构**，后者保证 **实体进池**。

---

### 3.5 三条路径如何衔接（读者对照表）


| 环节               | 路径 1 手工      | 路径 2 A∪C              | 路径 3 CPG                          |
| ---------------- | ------------ | --------------------- | --------------------------------- |
| 综合征识别            | 关键词          | 同左                    | LLM-1 或关键词                        |
| L1 轴/域来源         | JSON 写死      | C∪A 合并                | 方案A LLM 或 Spotter+分区              |
| 代表实体             | 标志物投影        | A 缓存实体 + 标志物          | 检索+Spotter/LLM                    |
| mandatory 权威     | JSON domains | **C 种子** mandatory 标记 | 方案A LLM 标 mandatory；或 cant_miss 表 |
| 下游 BranchCreator | 相同           | 相同                    | 相同                                |
| 当前生产默认           | **是**        | 可选开                   | **否**（实验脚本）                       |


**演进关系（非替换）**：

```text
路径 1 ──► 路径 2：用 A∪C 减少手写 JSON，覆盖 ≥ 路径 1
路径 2 的 A 源 ──► 路径 3 的 build_branch_knowledge_llm 填充 auto_axis_cache
路径 3 的 Spotter/检索改进 ──► 反哺路径 3 的 A 源质量与路径 2 的 live 生成
```

---

### 3.6 本节小结

1. **知识注入** = 在 BranchCreator 之前，确定性组装 `branch_knowledge`（轴、mandatory 域、域内实体）。
2. **手工 map** 是 **覆盖下界** 与 **识别层**；**A∪C** 在保持下界的同时用 **LLM 缓存 + 极小种子** 扩展；**CPG/RAG** 用 **20 万指南块** 自动生成候选与轴缓存。
3. **LLM 出现两次**（CPG 路径）：LLM-1 抽 syndrome（可关）；LLM-2 方案 A 定 MECE（或 recall_llm flat 抽取）。BranchCreator 是 **第三次** LLM，职责是 **命名分支**，不是建 MECE 结构。
4. 后文第 5–6 节的每一项「改进」，都是针对 **3.4.2 在线链** 某一环节的实测修补（闭包用法、40 槽淹没、Hybrid 检索、直提名等），**在理解本节之前不应阅读改进章节**。

---

## 4. 外部数据与设计转向

### 4.1 开放数据源（角色一句话）


| 源                | 分支生成中的角色                                     |
| ---------------- | -------------------------------------------- |
| StatPearls / 教科书 | 生产环境主索引（约 49 万块）；章节常含 Differential Diagnosis |
| PMC 开放全文         | 量大；DDx 常散落在 **同篇其它块** → 依赖 **同篇扩展**          |
| WikEM            | 综合征 **入口页** + 链接式 DDx 列表                     |
| Merck 手册         | purchased PDF，高密度 approach                   |
| NICE 等 HTML      | 多为推荐条目，纯 DDx 块少 → 作补充与审计                     |


### 4.2 GARMLE-G（Medical Teacher 2024）

外部论文提出的指南 RAG 范式，本研究借鉴两点：

1. **查询增强**：用 **简短临床特征** 丰富综合征查询（**不用** 整段病例，避免噪声）。
2. **有依据抽取**：大模型 **只能** 列出摘要里出现过的病名。

### 4.3 MedCPT 与混合检索

通用句子向量（如 MiniLM）在 **短问句 vs 长医学段落** 上表现差。MedCPT 在 PubMed 点击日志上训练，更适合 **「问：高钙血症鉴别」→「答：一篇 2000 字综述里的某段」**。  
本研究 **保留** TF-IDF（精确词匹配），**并联** MedCPT，用 RRF 合并。

### 4.4 开放数据约束与许可边界（设计转向前提）

本研究 **无法** 依赖 BMJ Best Practice、UpToDate、DynaMed 等商业「approach-to-symptom」整库。**覆盖保证** 因此 = 开放源集成 + 症状入口挖掘 + KG/本体审计 + curated can't-miss 下界，而非镜像商业 DDx 库。


| 约束                              | 来源文档结论                                           | 对流水线的影响                                  |
| ------------------------------- | ------------------------------------------------ | ---------------------------------------- |
| **无整库症状 DDx 替代品**               | 开放许可下不存在可整库镜像的 BMJ-BP 式资源                        | 必须走 CPG 多源融合 + A∪C 手工地板                  |
| **Merck 19e**                   | 已购 PDF，**内部 RAG only**，禁止再分发                     | 9,629 chunks 进实验索引；生产 **未并入**（§6.1）      |
| **WikEM CC BY-SA + AI/ML 条款**   | 检索复用须署名；训练/微调/评测用途需法务确认                          | cant_miss 表可部分自动化；**不能** 假设无限制 ML 复用     |
| **NICE/协会 HTML**                | recommendation 块为主，纯 differential 极少             | **审计/上下文**，非主 DDx 召回源（§6.28）             |
| **PMC 占库 ~88%**                 | 统一池改变 spotting 组成，但不等于应用分源 UNION 降噪（§6.26、§6.34） | A9l 主路径 = **unified TF-IDF + grounding** |
| `**syndrome_anchor`≠综合征键**      | PMC 标题 ~63% 无显式临床词；anchor 不能直接当 query 键          | 须 IMP-59 crosswalk + IMP-58 归一（§6.5）     |
| `**entry_type=syndrome_entry`** | WikEM/Merck 已标记；检索 boost **待办**（IMP-51）          | 结构化入口加权尚未进入 A9l 主链                       |


---

## 5. 研究演进：在 §3 基础流程上的增量改进

**阅读前提**：本节每一项改动都作用于 **§3.4.2 在线处理链** 的某一环节；对应缺陷与证伪见 **§6**。若未读 §3，下列「grounding」「直提名」等将缺乏上下文。

```text
阶段 0  §3.2 手工 map + BranchCreator
阶段 1  §3.4 指南检索 + SNOMED 字典匹配（确定性 Spotter）
阶段 2  整合 WikEM/PMC/Merck，建实验索引（约 20 万块 TF-IDF）
阶段 3  系统诊断：数据够 vs 检索/抽取损失（Oracle 8/8 数据可达）
阶段 4  闭包改「只供 LLM」（§3.4.4 灌池 vs grounding）
阶段 5  五路查询、直提名、硬层、MedCPT 混合
阶段 6  全栈 + LLM 补跑：A9l / A11_llm / A12
```

**为何最终是 A9l（Spotter 全栈）而非其它管道？**

四份源文档的探索形成 **三条可对比管道**；A9l 是在 **hand 标签 + 14 题矩阵** 上的综合最优，其选型逻辑如下：


| 管道                   | 代表配置                                            | 核心结论                                                        | 与 A9l 关系                              |
| -------------------- | ----------------------------------------------- | ----------------------------------------------------------- | ------------------------------------- |
| **hybrid→SNOMED 分区** | CPG∪StatPearls 召回 → `partition_from_candidates` | 召回 **6/9** 但覆盖 **3/9**——**分区墙浪费召回**（§6.32）                  | **❌ 弃用** 作 MECE 主路径                   |
| **方案 A（cpg_llm）**    | LLM 直接产 MECE 域 + mandatory                      | curated-free 覆盖 **62%**；轴 **100%** 正确；可作 **A 源自动起草**（§6.32） | 服务 **A∪C / auto_axis_cache**，非 A9l 主径 |
| **A9l Spotter 全栈**   | grounding + LLM 抽取 + 归族 + 直提名 + 硬层              | 综合 **0.812**（hand 标签，实验索引）                                  | **当前召回层首选**                           |


**生产 vs 实验双轨（实施计划共识）**：

```text
生产默认（今日）：UnionAxisMap（A∪C）+ 手工 map 识别 + StatPearls FAISS
实验/评测主径：  GuidelineBranchSource + cpg_index + A0–A12 臂（A9l 等）
合并前置卡点：   IMP-31 重建生产索引（元数据 + CPG 语料）
```

**受控实验推导顺序（影响 A9l 组成的 IMP 链）**：闭包 **grounding**（IMP-63）→ **spotter+llm**（最大单杠杆）→ 本体归族（IMP-64）→ 机制直提名（IMP-58）→ can't-miss 硬层（IMP-56）→ MedCPT hybrid（IMP-53）；**明确剔除**：五路 fanout（IMP-52）、Spotter 池 MMR-trim、分源 UNION 主路径（IMP-61）、闭包灌池（C4）。

**当前推荐（分目标）**：


| 目标           | 推荐臂         | 检索方式            | 综合分       | L2        |
| ------------ | ----------- | --------------- | --------- | --------- |
| 平面 L1 / 综合最高 | **A9l**     | 仅 TF-IDF        | **0.812** | 0.786     |
| L2 深度 / 语义匹配 | **A11_llm** | TF-IDF + MedCPT | 0.783     | **0.857** |
| 无大模型、纯程序     | **A11**     | TF-IDF + MedCPT | 0.723     | 0.714     |


---

## 6. 缺陷、案例与改进

**本节假设读者已读 §3**。每一项均用 **现象 → 机制 → 案例 → 改进 → 对比/实测 → 状态** 叙述，并标明 **✅ 已落地 / ❌ 证伪 / ⚠️ 部分落地 / 🔴 待落地**。

**读前坐标**（判断漏在哪一步）：

```text
片段层：检索+闭包+门控后的文本，是否含 gold 相关词？
候选层：≤40 疾病名候选里，是否含 gold？（方案 A 定轴分族不经过此池）
覆盖层：gold 能否投影到某个 L1 域？（RAG 实验多数不测这层）
```

漏斗诊断 **N=8**（hand 综合征标签，排除纯体征 gold 的 case14），与 A0–A12 矩阵 **hand 标签** 一致，**不混入** RootSelector 误差。

**§17 表项覆盖提示**（L1–L13 → 本节；A/C 类见对应小节，不单列 ID 目录）：


| §17 ID                   | 报告小节            | 备注                                  |
| ------------------------ | --------------- | ----------------------------------- |
| **L3** 上下文碎片化            | **§6.4**        | entry-direct 7/8 → closure 8/8      |
| **L4** 词面/eponym 鸿沟      | **§6.10**       | c1 Pancoast                         |
| **L5** hard-negative 挤占  | **§6.6**、§6.7   | 与 C4 拥挤同源                           |
| **L1/L2** 嵌入/非对称         | **§6.11**       | MedCPT hybrid                       |
| **L8** IVFPQ 近似          | **§6.25**       | nprobe 非主因                          |
| **L9** IDF 源淹没           | **§6.26**       | WikEM vs PMC                        |
| **L11** can't-miss 排序不可靠 | **§6.13**       | IMP-56 硬层                           |
| **L6/L7/L10/L12/L13**    | **§6.29**、§6.10 | HyDE/多跳/rerank/Orphanet；L13 直提名部分替代 |
| **C2/C3** Spotter 后处理    | **§6.5**        | IMP-58/59                           |
| **C1** vocab 缺口          | **§6.8**        | **❌ 证伪**                            |
| **A1/A2** 生产索引/元数据       | **§6.1**        | IMP-31                              |
| **hybrid→SNOMED**        | **§6.32**       | 召回>覆盖，弃用主径                          |
| **curated-free 假象**      | **§6.33**       | 75%→50%                             |
| **差异化/锚点入口**             | **§6.34**       | 入口有效，spotting UNION 证伪              |
| **IMP-55/11/57**         | **§6.35**       | 覆盖门/接地门/跨源投票                        |


---

### 6.1 生产索引未含新指南语料 / 元数据缺失


| 项目     | 说明                                                                                                            |
| ------ | ------------------------------------------------------------------------------------------------------------- |
| **现象** | 生产检索库只有 StatPearls+教科书（约 49 万 FAISS 块）；WikEM/PMC/Merck 等 **未并入**；块缺少 `source_id`、`chunk_type`，**同篇扩展与门控无法触发** |
| **机制** | 闭包按「文章编号」拉 sibling；生产 metadata 无该字段 → 命中 1 块即结束                                                               |
| **案例** | 生产库同篇扩展：**8→8（零增益）**；实验 `cpg_index`：**8→213**                                                                 |
| **改进** | 重建生产索引，写入完整元数据并并入 useful CPG 子集                                                                               |
| **对比** | **改前**：算法空转。**改后**（实验索引）：同篇 DDx 块可拉齐                                                                          |
| **状态** | 实验索引 **✅**；生产 **🔴 待合并**（本报告 A9l 等结论 **仅在实验索引成立**）                                                            |


---

### 6.2 语料上界够、流水线有损耗：Oracle 与漏斗对照


| 项目     | 说明                                                                                                                                                                                      |
| ------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **现象** | 「数据里有没有 gold」与「程序找没找到」差距大                                                                                                                                                               |
| **机制** | Oracle 只查「入口块 + 同篇闭包」是否含 gold，不跑检索排序；漏斗跑完整 `GuidelineBranchSource`                                                                                                                      |
| **口径** | 漏斗 **retrieved** = **24 条** excerpt 含 gold（家族匹配，7/8）；≠ gate 池（~6/8 strict）；≠ spotted（A9l 8/8）— **§14.0**                                                                                |
| **案例** | Oracle **8/8 (100%)**。`cpg_index`：片段 **7/8**，候选 **4/8**（经 resolver 后 **5–6/8**，§6.22），3 题 retrieved-not-spotted（c9/c13/c18）；c1 双漏、top-5 为 IBD/stroke 等离题项；`rag_index`：**6/8**，c1/c13 双漏 |
| **改进** | 先证 Oracle 再改代码，避免误补数据源                                                                                                                                                                  |
| **对比** | 相对 Oracle，cpg 候选层 **−50pp** → 主损耗在 **抽取**，非缺 chunk                                                                                                                                      |
| **状态** | **✅ 已证**（`eval_cpg_oracle_recall.py`、`eval_branch_rag_recall_diagnosis.py`）                                                                                                             |


---

### 6.3 入口块 ≠ 鉴别块：同篇扩展必要（案例 c1 Pancoast）


| 项目     | 说明                                                               |
| ------ | ---------------------------------------------------------------- |
| **临床** | Pancoast 可表现为肢体无力、Horner、臂痛；hand 标签 **focal limb neuro deficit** |
| **机制** | 检索常只命中「神经缺损/臂痛 approach」**入口块**；完整 DDx 在同文 **其它块**               |
| **语料** | Oracle：**124 入口块无 "Pancoast"**；扩展后 PMC sibling **含** gold        |
| **检索** | 查询与 "Pancoast" **无共同词** → TF-IDF **四配置皆漏**（片段层失败）                |
| **改进** | **同篇扩展**（§2.4，L3 一般机制见 **§6.4**）；**机制直提名**（§6.10）绕过检索            |
| **对比** | 无扩展 → 片段失败（L3）；扩展+灌池 → 片段成功、候选仍可能失败（§6.6）；grounding+提名 → 成功      |
| **状态** | 闭包 **✅ 已落地**；生产 **🔴 未触发**（§6.1）；c1 纯检索 **❌ 仍漏**                 |


---

### 6.4 DDx 列表上下文碎片化（L3 / §17.4.2-B4）


| 项目            | 说明                                                                                                                                                                      |
| ------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **现象**        | 指南/综述把 **一整段 DDx 枚举** 切进 **多个 chunk**；单次检索返回的 **单个块** 常只含列表 **前半或零散的数项**，看不到完整鉴别清单                                                                                      |
| **机制**        | RAG 经典 **context fragmentation（上下文碎片化）**：gold 疾病名在语料里 **存在**，但不在 **当前 top-k 块** 内，而在 **同篇其它 sibling 块**；仅搜「入口/overview」块不够                                              |
| **Oracle 分层** | **entry-direct**（gold 必须在 **入口块正文** 内）：**7/8 = 88%**，唯一 miss 为 **c1 Pancoast**；**entry+closure**（入口块 + 同 `source_id` 全篇闭包）：**8/8 = 100%** → 纯 **篇内关联** 即可补上 **+12.5pp** |
| **与 §6.3 关系** | §6.3 是 L3 的 **典型案例**（c1：124 个入口块无一含 "Pancoast"，闭包后 PMC sibling 含 gold）；**同篇扩展是为 L3 服务的必需件**，不是可选优化                                                                      |
| **改进（已采用）**   | `expand_ddx_siblings`：按 `source_id` 拉齐 differential/evaluation sibling；`closure_mode=grounding` 把 sibling **只送 LLM 摘要**，避免同时触发 §6.6 灌池拥挤                                |
| **改进（未采用）**   | 索引层 **parent-child / late chunking / auto-merge**（文献 L3 正解）→ **未建**；当前闭包仅为 **部分替代**                                                                                     |
| **对比**        | 无闭包 + 无元数据：生产索引 expand **8→8**；实验 `cpg_index`：**8→213** 块，Oracle 闭包 **100%**                                                                                            |
| **状态**        | 闭包 **✅ 已落地**；生产 **🔴 无 `source_id` 不触发**（§6.1）；结构化 parent-child **🔴 规划中**                                                                                              |


---

### 6.5 Spotter 后处理与命名归一缺口（C2 / C3 / IMP-58）


| 项目                          | 说明                                                                                                                            |
| --------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| **C3：_GENERIC_NAMES 误杀**    | Spotter 后处理滤除 infection、neoplasm 等 **过宽族名**，避免占满 40 槽；极端情况下可能误伤 **合法上位词**，需 `mechanism_to_disease.json` 等 **白名单** 把机制措辞映射到具体病 |
| **C2：短词 / min_len**         | 仅匹配 **足够长** 的 n-gram；极短 disease token 可能 **完全不进入** Spotter 候选；是否为主因 **未在 N=8 单独证伪/证实**                                        |
| **PMC syndrome_anchor 未归一** | PMC 块 `syndrome_anchor` 常为 **标题原文**，与 hand 综合征标签、Merck 章节名 **词面不一致** → 入口匹配与 query 对齐困难                                       |
| **HPO / 跨库病名覆盖低**           | 表型库与知识源键 **命名差异大**（HPO 病名覆盖率约 **6.6%**）；纯 Jaccard 归一弱                                                                         |
| **改进**                      | **IMP-58** scispaCy/UMLS linker + **IMP-59** syndrome alias crosswalk；与 §6.10 机制直提名 **互补**                                    |
| **对比**                      | `DiseaseNameResolver` 已在评测层把 leukocytosis→CML 等 **抬升 spotting 至 5–6/8**（§6.24）；branch-gen **候选层**全面归一 **未完成**                 |
| **状态**                      | C3 白名单 **⚠️ 部分**；C2/IMP-58/59 **🔴 待落地**；**非** N=8 spotting 主瓶颈（主因仍为 §6.6 拥挤，§6.8 已证伪 vocab）                                  |


---

### 6.6 候选池拥挤：扩展块不应全部给字典匹配器（案例 c13 glucagonoma）


| 项目           | 说明                                                                                                                                        |
| ------------ | ----------------------------------------------------------------------------------------------------------------------------------------- |
| **现象**       | 片段层 **有** gold，**40 名候选里没有** gold                                                                                                         |
| **机制**       | Spotter 对每块做病名匹配并 **累加得分**；扩展后块过多 → MI、urticaria 等常见病占满 **40 槽**                                                                          |
| **案例 c13**   | gold = glucagonoma；片段含 gold；SNOMED 有 "islet cell tumor"；top-5 为 urticaria、MI…；语料 **surface form** 与标准名不一致时 **n-gram 字面亦可未命中**（§17.5.6 叙述） |
| **案例 c9**    | gold = leukemoid reaction；同属 retrieved-not-spotted                                                                                        |
| **案例（14 题）** | 灌池：**7/14** mandatory 下降；grounding：**0.702** > 灌池 **0.600**                                                                               |
| **改进**       | **grounding**：扩展块 **只供 LLM 读摘要**，不进入 Spotter 累加池                                                                                          |
| **对比**       | **改前**：0.54–0.65 且抖动。**改后**：**0.702**，与关闭扩展在 Spotter 侧 **相同**                                                                             |
| **状态**       | **✅ 已落地并证实**（IMP-63）；结论：**不是扩展有害，是扩展块不应参与累加打分**                                                                                           |


**算法对比**：

```text
【旧】blocks = search(30) + expand(全部) → Spotter 打分 → top_40  # 常见病 repeated 挤掉 rare
【新】Spotter 只读 search(30)；expand → LLM 摘要[:24]；可选 merge LLM 抽出的病名
```

---

### 6.7 检索 top_k 增大反而损害 spotting


| 项目     | 说明                                                                |
| ------ | ----------------------------------------------------------------- |
| **现象** | 提高检索 breadth → **片段 recall↑、候选 recall↓**                          |
| **机制** | 单一 `top_k` 兼服务「多捞块」与「少噪声 spot」；k=30 引入更多噪声块                       |
| **案例** | k=8：spotting **6/8 (75%)**；k=30：片段 **7/8**，spotting **4/8 (50%)** |
| **改进** | `retrieve_k` / `extract_k` **解耦**；配合 grounding（§6.6）              |
| **对比** | 单 k=30：**检索好、抽取差**                                                |
| **状态** | 解耦 **✅ 已参数化**；Spotter 池 MMR 裁到 15 块 **❌ 证伪**（综合 0.376）            |


---

### 6.8 SNOMED 词表缺口：诊断证伪


| 项目     | 说明                                                  |
| ------ | --------------------------------------------------- |
| **假设** | gold 漏因 Spotter 词表不含 gold 病名                        |
| **验证** | N=8 逐例：gold **均在** SNOMED disorder 词表               |
| **含义** | c9/c13/c18 失败是 **40 槽拥挤**，非 vocab 缺失                |
| **改进** | 扩 vocab **非关键路径**；优先 grounding + LLM + 直提名          |
| **状态** | 假设 **❌ 证伪**；UMLS 归一（IMP-58）**🔴 待落地**（服务 eponym 通道） |


---

### 6.9 字典匹配抽取损失 → 大模型有依据补抽


| 项目     | 说明                                                              |
| ------ | --------------------------------------------------------------- |
| **现象** | Spotter 只做字面匹配；块里有 gold 词，未进 top-40                             |
| **机制** | branch-gen **独有**：须把 prose 中的病名 **抽进候选 dict**；MRR@10 高仍可能 0 候选族 |
| **案例** | §6.2：cpg **3/8 extraction_loss**                                |
| **改进** | `spotter+llm`：LLM 只读 grounding 摘要，仅列 **摘要中出现的病名**               |
| **对比** | A2 **0.704** → A5 **0.768**；L1tgt **0.929**（**最大单杠杆**）          |
| **状态** | **✅ 已落地**（IMP-63 / C7）                                          |


---

### 6.10 查询词面鸿沟 → 机制/标志物直提名（案例 c1）


| 项目     | 说明                                                                              |
| ------ | ------------------------------------------------------------------------------- |
| **现象** | 综合征标签与答案病名 **无共同英文词** → 检索 **无法触达**                                             |
| **机制** | TF-IDF/MedCPT query 基于 syndrome 字符串；c1 连 **入口块都命不中**                            |
| **改进** | 读 **context**：`mechanism_to_disease.json`、`pathognomonic_markers.json` → 直接写入候选 |
| **示例** | `"apical lung tumor, Horner, arm pain"` → `pancoast tumor`                      |
| **对比** | 无提名：c1 四臂检索全漏。A7：extraction_loss **1→0**，spotted **0.75→1.0**                   |
| **状态** | **✅ 已落地**（A7/A9l）；alias crosswalk（IMP-59）**🔴 待落地**                             |


**实现规格（消歧）** — 完整机制见 **§2.9.2**；要点：

- **触发**：`nominate=True` 时对 `{syndrome} {syn} {context}` 子串匹配，**不**走 embedding/LLM 推断。
- **表源**：`pathognomonic_markers.json`（24 条 OR）+ `mechanism_to_disease.json`（exact key≥6 + family_expansions ≤12 实体）。
- **写入**：`scored[nm] = max(..., 1.05×floor)`，`floor=0.6×max(spotted)`；`cant_miss_hard` 时 `forced` 强制回 top-40。
- **消费**：链 A = `recall()` flat 40 名 → 评测 token 家族匹配 / MECE 投影；链 B = 生产 `controller._build_branch_candidates` T1 marker → **按 L1 域** 归档（**不**调用 `recall(nominate=True)`）。

---

### 6.11 语义近邻缺失 → MedCPT 混合检索


| 项目     | 说明                                                                                                 |
| ------ | -------------------------------------------------------------------------------------------------- |
| **现象** | 纯 TF-IDF 无共同词则无法召回；生产 FAISS 用通用 MiniLM                                                             |
| **机制** | 医学检索需 Query–Document **非对称**双塔；RRF **并联** TF-IDF，不替换                                               |
| **改进** | `HybridCPGRetriever`：TF-IDF + MedCPT                                                               |
| **对比** | A10 vs A1：轴可分 **+7pp**，L2 **+7pp**，综合 **0.702→0.719**。全栈：A11_llm **L2=0.857**；综合仍低于 A9l（**0.812**） |
| **状态** | 实验索引 **✅**（IMP-53）；生产 FAISS **🔴 仍 MiniLM**                                                        |


---

### 6.12 40 名内 flat 竞争 → 本体反向归族


| 项目     | 说明                                                                                                               |
| ------ | ---------------------------------------------------------------------------------------------------------------- |
| **现象** | 罕见病单次出现，常见病多块重复 → flat 排序失败                                                                                      |
| **机制** | 语料是 **具体病名**，L1 要 **族/域**；应在族层竞争                                                                                 |
| **改进** | **覆盖增广**：保留 flat 强 hit；若 SNOMED 超族在 flat top-40 **零成员**，从 40 名外取该族 **最强 1 名具体病** 替换 **末尾最多 5 槽**（**不用族名** 替换具体名） |
| **对比** | 轴可分 **0.571→0.643**；综合 **持平 ~0.704**（严格不回归 flat 召回）                                                              |
| **状态** | **✅ 已落地**（IMP-64）                                                                                                |


**实现规格（消歧）** — 完整机制见 **§2.9.1**；要点：

- **门槛**：仅 `len(scored) > 40` 时调用 `_rollup_candidates`；≤40 时整段 rollup **不生效**。
- **分组**：对 **全部** spotted key 做 SNOMED `is_a` 分组（2–70% 覆盖，≤6 超族；`family+orphan` 孤儿单独成族）。
- **替换**：`n_reserve = min(缺席族数, max(1, K//8)) ≤ 5`；挤掉 flat_top **末尾** 低分名；**保留具体病名字符串**。
- **消费**：只改 `recall()` 返回的 **≤40 扁平病名 dict**；**不管** 24 条 LLM 摘要，**不直接** 写 `mandatory_coverage`。

---

### 6.13 Can't-miss 轴极注入与硬层


| 项目     | 说明                                                                            |
| ------ | ----------------------------------------------------------------------------- |
| **概念** | **轴极** = 分类轴上须 **成对保留** 的相反方向（§2.7）；**轴极注入** = 用 can't-miss 表把缺失一极 **补进** 候选池 |
| **意图** | 不可漏诊轴极（如高钙「恶性肿瘤」一极）分数低也 **强制进候选**；硬层 **不被 40 名截断**                            |
| **问题** | can't-miss 表来自 WikEM **症状页 id**，与 **hypercalcemia** 等化验综合征 **不对齐**            |
| **对比** | 单独开轴极注入 ≈ **无增益**；A9l 轴可分主要来自提名+LLM                                           |
| **状态** | 代码 **✅**（IMP-60/56）；**⚠️ 待扩展 can't-miss 数据源**                                 |


---

### 6.14 召回到了但分不对域：SNOMED 分区墙


| 项目     | 说明                                                                |
| ------ | ----------------------------------------------------------------- |
| **现象** | 候选 **有** gold，但 `project_entity` 为空 → mandatory 仍 MISS            |
| **机制** | SNOMED `is_a` 不擅长机制/解剖措辞（adhesions、peliosis、foreign body）         |
| **案例** | hybrid：**6/9 召回 → 3/9 覆盖**；c9 方案 A 轴框定缺 reactive 桶                |
| **改进** | **方案 A** LLM 建 MECE；**A∪C** override seeds；IMP-55 可达性门 **🔴 待落地** |
| **对比** | 纯 SNOMED 自动 L1：**❌ 证伪** 作唯一 mandatory 源                           |
| **状态** | 方案 A + A∪C **✅ 实验有效**；属 **覆盖层**，非 RAG 召回问题                        |


---

### 6.15 评测尺子曾低估真召回


| 项目     | 说明                                                   |
| ------ | ---------------------------------------------------- |
| **现象** | 旧 token 子集匹配：惩罚精确实体、奖励泛化名                            |
| **案例** | c9：`infectious mononucleosis` 判 MISS，`leukemia` 反而命中 |
| **改进** | **方案 B** 实体级匹配                                       |
| **对比** | Recall@K **50%→75%**                                 |
| **状态** | **✅ 已落地**；后文数值基于修正后尺子                                |


---

### 6.16 端到端弱根标签（RootSelector）


| 项目     | 说明                                                                         |
| ------ | -------------------------------------------------------------------------- |
| **现象** | LLM 抽 syndrome 常弱化（如 "nausea" 替代 "bowel obstruction"）                      |
| **机制** | 弱根拖累 **全部下游 query**；与 §6 漏斗（hand 标签）是 **不同问题**                             |
| **对比** | hand 标签方案 A **75%(6/8)**；curated-free LLM 根：**50%** StatPearls、**62%** CPG |
| **改进** | 更稳 RootSelector；生产可用 UnionAxisMap **关键词识别**                                |
| **状态** | **✅ 已证**；A0–A12 **默认 hand 标签** 隔离分支模块                                      |


---

### 6.17 已排查、非本基准主因的环节


| 项目                             | 说明                                                                                 |
| ------------------------------ | ---------------------------------------------------------------------------------- |
| **FAISS nprobe**               | nprobe 1–256 @ k=30，均 **6/8** → **❌ 非瓶颈**                                          |
| **score_threshold**            | 0→0.3：case9 仅 **−2 hits** → **轻微**                                                 |
| **on-topic 门控**                | cpg_index **220/220 pass** → **❌ 非问题**                                             |
| **WikEM wiki_links**           | on/off spotted 同为 **0.625** → **❌ 零增益**，机制保留                                       |
| **GARMLE 全文 ctx-query**        | 引入离题 PMC → **❌ 已回退**                                                               |
| **Hard-negative 挤占 top-k（L5）** | 常见病 chunk 语义近但 DDx 错（c9 urticaria）；与 §6.6 灌池同源；MMR **❌ 证伪**（§6.30），grounding **✅** |
| **PMC top-k 占 ~90%（L9 现象）**    | 现象 **✅ 确认**；分源 UNION 降噪 **❌ 证伪**（综合 **0.235**）                                     |


---

### 6.18 LR 通道「可达≠可排序」（旁路）


| 项目     | 说明                                                      |
| ------ | ------------------------------------------------------- |
| **现象** | LR unified_cache 反向检索：gold **78% 可达**，recall@20=**0/9** |
| **机制** | 与 §6.6 类似但发生在 **Layer-2 LR**，非 branch-gen 主径            |
| **旁证** | pathognomonic 在 LR 可提名 **5/9**；branch-gen 现已部分接入（§6.10） |
| **状态** | **记录备查**；不纳入 A0–A12                                     |


---

### 6.19 召回判据与覆盖判据不可混读（§17.1）


| 项目       | 说明                                                                                                  |
| -------- | --------------------------------------------------------------------------------------------------- |
| **现象**   | 同一 case 上「候选 dict 含 gold」与「gold 投影到 L1 域」常被混为一谈                                                     |
| **机制**   | §17 流水线 **[5] spotting/LLM 抽取** 的成功判据是 **金标准疾病族是否进入候选 dict**；**[7] SNOMED/方案 A 分区** 属于 **覆盖层**，另线评测 |
| **案例**   | hybrid：**6/9 召回、3/9 覆盖**——若只盯覆盖会误判「召回仍低」                                                            |
| **评测口径** | 漏斗 N=8 **排除 case14**（gold 为纯体征 `"diastolic murmur…"`，非疾病实体，spotting 口径不同）                           |
| **改进**   | RAG 实验报告 **片段层 / 候选层 / 覆盖层** 分列；端到端另报                                                               |
| **状态**   | 口径 **✅ 已在 A0–A12 矩阵固定**；覆盖层 IMP-55 **🔴 待落地**                                                       |


---

### 6.20 轴污染：相反 L1 轴极被塌缩（§17.2 Step 4）


| 项目     | 说明                                                                              |
| ------ | ------------------------------------------------------------------------------- |
| **概念** | **轴污染** = 本须分开的 **相反轴极**（§2.7）被合成同一支或 flat 排序塌缩                                 |
| **现象** | 候选含 gold，覆盖也有域，但 **轴方向错误**——例如 PTH 介导 vs 恶性肿瘤 **只留一侧** 或 **并为兄弟**               |
| **机制** | SNOMED `is_a` **归族若整体替换 flat 排序**，会把 primary/secondary 等 **相反 L1 极** 并为兄弟，塌缩临床轴 |
| **案例** | IMP-64 因此采 **覆盖增广**（保留 flat 强 hit + 族灭门保底），**非** 全量替换 flat                      |
| **改进** | `split_variants`、override seeds 定轴；轴可分性单独指标（A2 轴可分 0.571→0.643）                 |
| **对比** | 整体 is_a 替换 flat：**❌ 证伪**（会损轴可分）；增广式归族 **✅**                                     |
| **状态** | 归族 **✅ 已落地**；轴污染检测 **⚠️ 未常驻 CI**                                                |


---

### 6.21 rag 与 cpg 瓶颈分轨：缺源 vs spotting（§17.5.1 叙述）


| 项目         | 说明                                                                                                                         |
| ---------- | -------------------------------------------------------------------------------------------------------------------------- |
| **现象**     | 同一设定下 **rag_index 6/8、cpg_index 4/8**（候选层），但 **成因不同**                                                                      |
| **机制**     | rag（StatPearls+MiniLM）：片段与候选 **同率**，**抽取损失=0** → 瓶颈在 **检索/缺源**；cpg：片段 **7/8**、候选 **4/8** → 瓶颈在 **spotting**                |
| **案例 c13** | **rag**：连片段都无 glucagonoma（StatPearls **缺** 胰高血糖素瘤上下文）→ **双漏**；**cpg**：片段 **有** gold，spotter 仍漏 → **retrieved_not_spotted** |
| **案例 c1**  | 两索引 **皆双漏**（词面鸿沟，§6.10）                                                                                                    |
| **改进**     | 先判 `extraction_loss` 是否>0，再决定补检索还是补抽取                                                                                      |
| **状态**     | **✅ 已证**；生产 rag 路径对 rare endocrine **仍缺 CPG 源**（§6.1）                                                                      |


---

### 6.22 小样本抖动、机制 resolver 更正与扩样动机（§17.5.6）


| 项目     | 说明                                                                                   |
| ------ | ------------------------------------------------------------------------------------ |
| **现象** | 早期记录 cpg spotting **4/8(50%)**；补跑后 **5–6/8(62.5–75%)**；c18 在 **5/8↔6/8 间进程抖动**       |
| **机制** | `DiseaseNameResolver` 机制扩展（如 leukocytosis→CML）抬升候选层；TF-IDF **并列分 + 40 槽边界** 致小 N 不稳定 |
| **案例** | c13 **稳定漏**（crowding）；c18 **边界抖动**                                                   |
| **改进** | 扩至 **14+8 题**矩阵 + L2/轴可分（§7）；常驻 `eval_branch_confounder_matrix.py`                   |
| **对比** | 仅 N=8 L1 宽匹配：**区分度 0.395**，不足以筛 minor 改动                                             |
| **状态** | 扩样矩阵 **✅**；IMP-54 recall@k CI **🔴 待建**                                              |


---

### 6.23 MRR@10 勿作 branch-gen 唯一指标；oracle-union 尺子缺失（§17.6）


| 项目     | 说明                                                                                                             |
| ------ | -------------------------------------------------------------------------------------------------------------- |
| **现象** | 检索 MRR@10 高，但 **0 候选族**；或 oracle 仅 entry+closure，不知 **哪一源该背锅**                                                 |
| **机制** | branch-gen 要的是 **实体进 dict**，不是「答对段落」；IMP-54 `eval_coverage_oracle.py`（oracle-union + 逐源边际 + recall@k 曲线）**待建** |
| **案例** | §18 已证 entry+closure **8/8**，但 **不能** 替代「493k IVFPQ 对 rare 的 recall@k 全曲线」（§17.5.3 **未测**）                     |
| **改进** | 迭代时：**漏斗脚本** + **Oracle** 双跑；勿单报 token 子集 Recall（§6.15 已修正）                                                    |
| **状态** | 漏斗+Oracle **✅ 常驻**；union 边际 + 全库 recall@k **🔴 待 IMP-54**                                                      |


---

### 6.24 snippet 硬截断与端到端分区损耗（§17.5.5）


| 项目     | 说明                                                                                                                                                  |
| ------ | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| **现象** | 片段层距 Oracle **−12.5pp**（7/8 vs 8/8）；curated-free **cpg_llm 覆盖仅 5/8(62.5%)**                                                                         |
| **机制** | LLM grounding 仅 **≤24 条 × 400 字 ≈ 9.6k 字符**，长 DDx 列表 **后半被截断**；5/8 含 **[7] 分区损耗**，非纯 RAG 召回                                                         |
| **口径** | B6 **retrieved** = 24 条合并文本含 gold（**家族 token**，7/8）；**strict gold@24** = 严格子串（2/8）；**gate 池** = 截断前 eligible（6/8 strict / 7/8 家族）— 三者勿混读（**§14.0**） |
| **案例** | c1：片段层失败时，截断 **不是** 主因；c9/c13：片段有 gold 但 **40 槽/截断** 叠加                                                                                             |
| **改进** | 结构化 DDx 离线预提取（长期）；短期靠 grounding + LLM + 直提名；**§14.7** 片段层 P0–P2 路线图                                                                                 |
| **对比** | 增大 snippet 上限 alone：**未证** 优于全栈 A9l；**§14.4** 实测 24 条仅保留闭包 **~1.6%**（8 题），sibling 进 24 条 **0/8**                                                    |
| **状态** | 截断为 **⚠️ 已知边界**；结构化主干 **🔴 规划中**                                                                                                                    |


---

### 6.25 小 k 部署：nprobe 与 PQ 压缩（§17.5.2–3 叙述）


| 项目     | 说明                                                                                                   |
| ------ | ---------------------------------------------------------------------------------------------------- |
| **现象** | @k=30、nprobe 1–256，片段/spotting **均 6/8** → 生产默认 nprobe=32 **非瓶颈**                                    |
| **机制** | @**k=8** 小 k 部署：nprobe↑ 可 **反降** spotting（更多噪声块，同 §6.7）；IVFPQ **PQ 压缩** 在 nprobe=nlist 时仍可能丢 rare 邻居 |
| **验证** | 5k 子样本 brute top10 vs Flat：**overlap 10/10**；L2 距离→权重 **方向正确**                                       |
| **未测** | 全库 **493k** rare entity 的 recall@k 曲线                                                                |
| **状态** | @k=30 **❌ 非主因**；小 k + 全曲线 **⚠️ 待 IMP-54**                                                            |


---

### 6.26 WikEM 入口召回 vs spotting 内 PMC 淹没：不同层（§17.8 / §16）


| 项目     | 说明                                                                                                          |
| ------ | ----------------------------------------------------------------------------------------------------------- |
| **现象** | §16：统一大池使 WikEM **入口** Recall@10 **0.659→0.993**（138 query）；§17.5.6：spotting 时 top-k **~90% 来自 PMC**        |
| **机制** | **入口检索**（综合征页命中）与 **候选 spotting**（块内病名累加）是 **不同环节**；用分源 UNION 降噪 spotting **❌ 证伪**（0.235），但 **不等于** 入口问题不存在 |
| **改进** | 主路径：**unified TF-IDF + grounding + LLM**（A9l）；WikEM 差异化 **仅保留 §16 入口场景**，不进 recall 主链                       |
| **状态** | 现象 **✅ 确认**；UNION 主路径 **❌ 弃用**                                                                              |


---

### 6.27 branch-gen 三类结构性风险（§17.4 叙述段）


| 项目          | 说明                                                                                                          |
| ----------- | ----------------------------------------------------------------------------------------------------------- |
| **① 检索目标**  | 要的是 **DDx 实体 dict**，不是「含答案的段落」→ 见 §6.9、§6.23                                                                |
| **② 入口→闭包** | L3 碎片化；须 **同篇 sibling** → 见 **§6.4**（机制）、§6.3（c1 案例）                                                        |
| **③ 多源异构**  | WikEM 链接列表 / PMC 散文 / NICE 推荐 **不能假设同一 embedding 空间**；统一池 **PMC 88%** 改变 spotting 组成，但不等于应用分源 RRF 降噪（§6.26） |
| **状态**      | ①② **✅ 已有对策**；③ **⚠️ 生产 IMP-31 前 CPG 源不可达**                                                                 |


---

### 6.28 语料构建与索引过滤（§17.2.1 / §17.1 索引叙述）


| 项目               | 说明                                                                                             |
| ---------------- | ---------------------------------------------------------------------------------------------- |
| **语料稀释**         | 全库 ~36 万 chunk 中 **31% `chunk_type=other`**、大量短块；入索引取 **useful∧≥120** → 实验 **203,830** 条 **✅** |
| **NICE/协会 HTML** | 以 **recommendation** 为主，纯 differential 块极少 → **作 mandatory 审计/上下文**，**非**主 DDx 召回源 **✅ 已认知**   |
| **抓取噪声**         | Cloudflare/Cookie 检查页 → 构建层过滤，cpg_index **弃 17 条** **✅**                                       |
| **三索引分裂**        | 生产 `rag_index` 493k（MiniLM）；实验 `cpg_index` 204k；`cpg_chunks.jsonl` **未入主索引** → 见 §6.1          |
| **状态**           | 实验 useful 子集 **✅**；并入生产 **🔴 IMP-31**                                                          |


---

### 6.29 待验证的长尾检索方案（§17.6 Playbook / §17.9 P2 叙述）


| 项目                          | 说明                                                                                   |
| --------------------------- | ------------------------------------------------------------------------------------ |
| **HyDE / SL-HyDE / CHR**    | 短 query 分布偏移时的 **低置信兜底**；防 mimic DDx 幻觉 → **⚪ 规划，未 A/B**                             |
| **多跳综合征链**                  | PrimeKG 2-hop / 迭代检索 → **⚪ 未做**                                                      |
| **两阶段广召回→cross-encoder 精排** | RAG-Fusion 警示：强 reranker 后多 query 增益→0 → **⚪ 未做**                                    |
| **Orphanet 补源**             | peliosis/glucagonoma 等 **语料稀疏** 的长尾 → **⚪ 未 A/B**；pathognomonic 直提 **✅ 部分替代**（§6.10） |
| **状态**                      | 均 **非当前 P0**；在 IMP-63/64 **✅ 闭环后** 再评边际                                              |


---

### 6.30 证伪或弃用的改进


| 改进                               | 做了什么                   | 实测                   | 状态        |
| -------------------------------- | ---------------------- | -------------------- | --------- |
| **五路 query 扇出**                  | 机制/解剖/危重等 5 类 query 合并 | 综合 **0.693 < 0.702** | **❌ 有害**  |
| **分数据源 UNION**                   | PMC/WikEM 分库 top 再合并   | 综合 **0.235**         | **❌ 弃用**  |
| **Spotter MMR 裁 15 块**           | 大幅删减 Spotter 输入块       | 综合 **0.376**         | **❌ 证伪**  |
| **扩展块灌 Spotter 池**               | 见 §6.6                 | 见 §6.6               | **❌ 弃用**  |
| **全栈误开 fanout**                  | 旧 A9l 含扇出              | **0.766→0.812**      | **❌ 已剔除** |
| **整段 vignette 拼 query**          | 300 字当检索词              | 离题块                  | **❌ 回退**  |
| **纯 SNOMED 自动 L1**               | 本体 alone 分区            | 覆盖差                  | **❌ 弃用**  |
| **SNOMED vocab 扩容**              | 假设词表缺 gold             | 8/8 均在词表             | **❌ 证伪**  |
| **HyDE / 多跳 KG / cross-encoder** | 文献进阶方案                 | 未做 A/B               | **⚪ 未验证** |


---

### 6.32 Hybrid→SNOMED 分区浪费召回：方案 A 优于 hybrid（§15 重大发现）


| 项目            | 说明                                                                                                                                             |
| ------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| **现象**        | 「召回更多 gold」与「mandatory 域覆盖更高」**反向**：hybrid 管道 gold 在候选 **6/9**，L1 覆盖仅 **3/9 (33%)**                                                            |
| **机制**        | hybrid 把 CPG+StatPearls 召回 **合并后喂给** `KBAxisMap.partition_from_candidates`（SNOMED `is_a`）；gold 已在 dict 仍 **投影失败**（cases 9/13/24）               |
| **对比**        | **方案 A（cpg_llm）**：LLM **直接** 产临床 MECE 域（如 "PTH-related hypercalcemia"）→ 覆盖 **5/9 (56%)**，轴 **5/5=100%**；**orig**（仅 StatPearls 分区）**2/9 (22%)** |
| **架构结论**      | **瓶颈常在覆盖层（分区），非召回层**；把高召回候选 **路由回 SNOMED 自动分区会浪费召回**                                                                                           |
| **对 A9l 的含义** | A9l 优化 **候选 dict 召回**（grounding+LLM+直提名）；MECE 结构靠 **A∪C / 方案 A 起草 + BranchCreator**，**不走** hybrid→SNOMED 主径                                    |
| **若要用混合**     | 应改为「**方案 A 产分区 + 原管道候选仅作 mandatory 下界/residual 注入**」，而非双源候选 **都灌进** SNOMED 分区                                                                  |
| **状态**        | 发现 **✅ 已证**（`eval_cpg_branch_pipeline.py` N=9）；hybrid 主径 **❌ 弃用**；方案 A 作 **A 源草稿器** **✅ 采纳**                                                   |


---

### 6.33 Curated-free 根标签假象与 CPG⊇StatPearls（§15.7）


| 项目            | 说明                                                                                                                                      |
| ------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| **现象**        | 早期报告 StatPearls+方案A **75%(6/8)** 看似优于 CPG **62%**                                                                                       |
| **机制**        | 75% 依赖 **手工 `syndrome_axis_map` 提供干净综合征标签**（半自动）；换 **curated-free LLM 抽根** 后 **同一管道跌至 50%(4/8)**                                        |
| **同口径对照**     | curated-free：StatPearls 方案A **50%**；CPG 方案A **62%**；CPG∪StatPearls **仍 62%**（**零额外案例**）                                                 |
| **语料关系**      | 本 9 题集 **CPG 覆盖 ⊇ StatPearls**（如 case18 peliosis 仅 PMC/Merck 有）；盲目 union 还可能 **劣化域命名**（case17 CML→"AML" 而非 "Myeloid Lineage Neoplasms"） |
| **共同短板**      | cases 9/13/23 漏因 **弱 RootSelector / 轴框定**，非缺 chunk → 杠杆在 **归一+稳根**（§6.5、§6.16），非再加 StatPearls                                           |
| **对 A9l 的含义** | A0–A12 **默认 hand 标签** 隔离分支模块；端到端 curated-free **须单独报**；超过 62% 覆盖方向 = **A∪C 极小种子 + RootSelector**，非叠 StatPearls                          |
| **状态**        | 口径 **✅ 已更正**；A9l 矩阵与方案A 覆盖实验 **不同评测设定**，不可直接比单一百分数                                                                                      |


---

### 6.34 锚点入口检索 vs 统一 TF-IDF：差异化检索分轨（§16 / §19）


| 项目                           | 说明                                                                                                                                                     |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **背景**                       | IMP-61 差异化检索在 **WikEM 入口** Recall@10 **0.659→0.993**（138 query）；但 spotting 主链用 UNION **综合 0.235**（§6.30）                                               |
| **IMP-61b 锚点 UNION**         | `AnchorAugmentedRetriever`：按 `syndrome_anchor`/`section_path` 选 **结构化入口块**，**并入**（非替换）基检索 → 闭包；9 题 L1 漏斗 **0.875**，**无回归**                             |
| **与 A9l 关系**                 | 14 题多级度量：**anchor-union 0.618 < unified+grounding 0.702**；§19.6 **最终更正**：主 recall = **unified TF-IDF + grounding**，锚点/差异化 **退出主链**，仅 §16 **入口子场景**按需启用 |
| **闭包配合**                     | 闭包只扩展 **已被选中的文章**；c1 若入口文章未进 top-k，闭包 **无从触及** → 须 **直提名**（§6.10）补链                                                                                    |
| **entry_type boost（IMP-51）** | `syndrome_entry` 已标记于 WikEM/Merck；检索加权 **待办**，尚未并入 A9l                                                                                                 |
| **状态**                       | 入口差异化 **✅ 有效（§16）**；spotting UNION **❌ 证伪**；锚点 UNION **⚠️ 次于 A9l 基线**，保留备选                                                                             |


---

### 6.35 运行时覆盖门与 LLM 接地核验（IMP-55 / IMP-11）


| 项目                    | 说明                                                                                                                                 |
| --------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| **IMP-55 可达性门**       | 高召回实体经 `disease→domain` 投影；若 **进不了任何 mandatory 域** → 注入 **residual / other-critical** 域并标 provenance，**防 LLM 删掉正确方向**              |
| **与 §6.14 关系**        | §6.14 证 **SNOMED 分区墙**；IMP-55 是 **运行时** 补救，呼应「覆盖永不低于手工基线」硬约束                                                                       |
| **IMP-11 接地核验门**      | `build_branch_knowledge_llm` / A 源缓存：实体须 **逐字命中** 检索 snippet，否则丢弃（TODO-GL-16）                                                      |
| **与 A9l 关系**          | A9l 的 `recall_llm` 已 **同构** GARMLE-G② 有依据抽取；**方案 A 离线 cache** 仍缺 IMP-11 → auto_axis 草稿可能含 **未 grounding 实体**                       |
| **跨源 DDx 投票（IMP-57）** | 离线按 `syndrome_anchor` 聚各源 DDx → 一致性投票 → `ddx_union_by_syndrome.json`；可作 **silver-standard 评测**（§13.5）与 mandatory 候选 **🔴 未接入** A9l |
| **状态**                | IMP-55/11/57 **🔴 待落地**；A9l 召回层 **不依赖** 三者，但 **生产 UnionAxisMap + 方案 A 合入** 需要                                                      |


---

### 6.31 当前剩余缺口

召回/抽取核心（grounding、LLM 补抽、直提名、归族）**✅ 已在实验索引闭环**（A9l **0.812**）。**🔴 生产生效**：§6.1、§6.28、§5 双轨（Union 生产 vs CPG 实验）。**🔴 L3 闭包生产未触发**：§6.4。**🔴 覆盖层**：§6.32 hybrid 弃用、§6.35 IMP-55/11。**🔴 尺子与长尾**：§6.23 IMP-54、§6.29。**🔴 命名归一**：§6.5 IMP-58/59；直提名 **✅ 部分替代**（§6.10）。**⚠️ 待数据**：§6.13 can't-miss。

---

## 7. 实验臂说明（A0–A12，自包含）

### 7.1 评测设置

- **14 题**（`branch_recall_eval_set.json`）：常见综合征（高钙、低钠、黄疸等），含 L2 与轴可分指标 → **Comp / L1tgt / L1mnd / 轴可分 / L2**。  
- **8 题难病**（`branch_recall_eval_set_hard.json`，idx 1/9/13/17/18/22/23/24）：罕见/刁钻（含 c1 Pancoast）→ **同上四大指标**（记 **hComp** 等）+ **漏斗**（retrieved / spotted / xloss）。  
- **MECE 指标**（`eval_mece_arm`，2026-06-27 接入矩阵）：将 40 名 flat 候选经 `project_entity` 投影到 `syndrome_axis_map` 的 L1 域，统计 **map_coverage**、**gold_domain_recall**、**projection_fail_rate**；14 题与 8 题 **分表输出**（`mece` / `mece_hard`）。  
- **大模型**：qwen3-32b，温度 0（可复现优先）。**注意**：2026-06-27 本机补跑时 `openai.OpenAI` 不可用，带 LLM 臂的 **14 题 Comp 不可** 与 gnn-llm 专跑混读（见 **§7.4**）。

### 7.2 臂代号一览（一句话 + 分数）

> **完整多指标表、五条结论与现象解释**见 **§14.0.1**（交流版自包含；**8 题 hComp / MECE** 见 **§7.4、表 4**；配置明细见 `CPG_RAG_EXTRACTION.md` §19.0.6b）。


| 臂              | 一句话配置                               | 综合分       | 备注           |
| -------------- | ----------------------------------- | --------- | ------------ |
| A0_legacy      | 旧默认：扩展块 **灌 Spotter 池**             | 0.54–0.65 | 抖动大          |
| A1_grounding   | 扩展块 **只供 LLM**                      | 0.702     | 确定性基线        |
| A2_rollup      | A1 + 本体归族                           | 0.704     | 轴可分 ↑        |
| A5_llm         | A2 + 轴极 + LLM 抽取                    | 0.768     | 未叠「直提名/硬层」   |
| A6_fanout      | A1 + 五路 query                       | 0.693     | **勿用**       |
| A7_nominate    | A1 + 机制直提名                          | 0.707     | 漏斗 xloss→0   |
| A10_hybrid     | A1 但检索改 **TF-IDF+MedCPT**           | 0.719     | 仅换检索         |
| A11_hybrid_nom | A10 + 归族 + 提名 + 硬层                  | 0.723     | **确定性最佳**    |
| **A9l**        | unified 检索 + **全栈 + LLM**（无 fanout） | **0.812** | **综合首选**     |
| A11_llm        | Hybrid + 提名 + LLM（**无** 轴极注入）       | 0.783     | **L2=0.857** |
| A12            | Hybrid + **全栈** + LLM + 轴极          | 0.778     | 略低于 A11_llm  |


### 7.3 「全栈」指哪些开关同时打开

在 **A1（grounding）** 之上 **同时**：

1. **本体归族**（族层保底名额）
2. **轴极软注入** + can't-miss 表（保证相反轴极进候选，§2.7；当前数据源增益有限，§6.13）
3. **can't-miss 硬层**（注入名不被 40 名截断）
4. **机制/标志物直提名**
5. **Spotter + LLM 合并抽取**
6. **明确不打开** 五路 query 扇出

**检索二选一**：

- **A9l**：只用 **TF-IDF** → **综合最高**  
- **A11_llm / A12**：**TF-IDF 与 MedCPT 并联** → **L2 最高**

### 7.4 8 题难病 + MECE 补跑（2026-06-27）

**命令**：`PYTHONPATH=src python scripts/eval_branch_confounder_matrix.py --llm --exclude-arms A0_legacy`  
**产出**：`data/cpg/eval/branch_confounder_matrix.json`（`generated_at` 2026-06-27）；**归档** `data/cpg/eval/archive/2026-06-27_hard_mece/`。


| 臂                  | hL1tgt | hL1mnd | h轴可分  | hL2   | **hComp** | **MECE₈** | spot | xloss | 备注                     |
| ------------------ | ------ | ------ | ----- | ----- | --------- | --------- | ---- | ----- | ---------------------- |
| **A11_hybrid_nom** | 0.875  | 0.750  | 0.643 | 0.714 | **0.656** | **0.688** | 1.0  | 0     | **确定性 8 题最佳**          |
| A9l_tableC_llm     | 0.875  | 0.688  | 0.643 | 0.643 | 0.622     | 0.594     | 1.0  | 0     | LLM 补抽失效；≈ A9b 栈       |
| A7_nominate        | 0.875  | 0.688  | 0.571 | 0.643 | 0.583     | 0.562     | 1.0  | 0     | c9/c23 仍漏 L1tgt        |
| A1_grounding       | 0.750  | 0.625  | 0.571 | 0.643 | 0.372     | 0.469     | 0.75 | 1     | 14 题 Comp **0.702** 基线 |
| A3_union           | 0.143  | 0.375  | 0.071 | 0.429 | 0.247     | 0.302     | 0.5  | 2     | 证伪臂对照                  |


**读法**：

1. **常见 vs 难病落差**：A1 在 14 题 **Comp=0.702**，8 题 **hComp=0.372**（−33pp）——mandatory/轴在刁钻集上仍是主瓶颈；漏斗 **spot 6/8→8/8**（A7/A11）说明 **直提名+硬层** 修的是 **候选层**，不自动抬 **L1 投影分**。
2. **MECE₈ vs MECE₁₄**：8 题 **MECE₈≈0.47–0.69**；14 题 **MECE₁₄≈0.12–0.14** 且 **gold_domain_recall=0**——flat 40 名多为 **具体病名**，在常见集上 **投不进** 手工 MECE 域标签；MECE 尺子与 **token 家族 L1tgt** **不可混读**（§6.19）。
3. **LLM 环境**：本跑 A9l **14 题 Comp=0.699**（非 **0.812**）；A11_llm / A12 与 A11_hybrid_nom **同分**——LLM 臂退化为确定性栈。**选型主表仍以 gnn-llm 表 1 为准**（§14.0.1）。

---

## 8. 完整走查索引：hypercalcemia 与 c1

**详细逐步走查见 §3.2.3、§3.3.4–3.3.5、§3.4.5–3.4.6。** 本节仅保留 **改进前后数值对照**，供与第 7 节实验臂交叉阅读。

### 8.1 hypercalcemia（14 题之一）

**临床要求**：L1 按 **机制**；mandatory 含 PTH 介导、恶性肿瘤、肉芽肿、噻嗪/牛奶碱等；轴极 **PTH vs malignancy** 须都在。


| 步骤      | 旧灌池                         | A9l 全栈                                        |
| ------- | --------------------------- | --------------------------------------------- |
| 检索      | top-30 + 扩展块 **全进 Spotter** | top-30 给 Spotter；扩展 → LLM 摘要                  |
| Spotter | 多块重复「转移瘤」等累加                | 噪声少                                           |
| LLM     | 无                           | 从摘要补「humoral hypercalcemia of malignancy」等    |
| 提名      | 无                           | 本例 context 通常不触发机制表                           |
| 结果      | mandatory 易降                | L1mnd **0.821**，轴可分 **0.714**，L1tgt **0.929** |


### 8.2 c1 Pancoast（8 题漏斗）

**Gold**：pancoast tumor；**Syndrome**：focal limb neuro deficit；**Context**：apical lung tumor, Horner, arm pain。


| 步骤        | 仅 grounding            | + 直提名（A7）                       |
| --------- | ---------------------- | ------------------------------- |
| TF-IDF 检索 | 无 Pancoast 词面          | 同左                              |
| Spotter   | 可能被挤占 top-40           | 同左                              |
| 直提名       | —                      | context → **写入** pancoast tumor |
| 漏斗        | 可能 retrieved✓ spotted✗ | spotted✓                        |


**三句话总结 c1**：① 语料 **够**（Oracle）；② **同篇扩展** 让片段层能摸到 gold；③ **词面检索不够**，需 **context 直提名**。

---

## 9. 与手工基线对比


| 维度      | 手工 map               | A∪C（生产推荐）                            | 当前最佳 A9l（实验）                                 |
| ------- | -------------------- | ------------------------------------ | -------------------------------------------- |
| 知识来源    | 11 综合征人工写            | C 种子 + A 缓存 + 手工兜底                   | ~20 万 CPG 块 + 机制表 + 标志物 + LLM                |
| MECE 权威 | JSON 写死              | **C mandatory 地板** + A 实体增广          | Spotter 召回 + 方案 A 可起草 A 源                    |
| 扩展新综合征  | 线性人工                 | LLM cache 批量 + 人工抽检                  | 检索 + 自动生成候选                                  |
| 召回手段    | 关键词 + 标志物            | 同左 + 可选 CPG                          | grounding + Spotter + LLM + 直提名              |
| 实测      | 11 id 稳定             | auto_axis **8/8 gold-domain**（7 综合征） | 矩阵综合 **0.812**                               |
| 生产流水线   | **已接** BranchCreator | **推荐开** `union_axis_ac`              | GuidelineBranchSource **实验脚本**；索引 **未合 CPG** |


**读法**：生产今日应优先 **A∪C 保 MECE 下界**；A9l 代表 **CPG 召回层** 在实验索引上的上限；二者通过 **方案 A 起草 auto_axis** + **IMP-31 合并索引** 收敛，而非二选一替换。

---

## 10. 局限与未完成

1. **生产检索库** 尚未并入 CPG；A9l 结论在 **实验索引** 上成立（§6.1、§4.4）。
2. **双轨未收敛**：生产 UnionAxisMap vs 实验 A9l；IMP-31 是合并前置卡点。
3. **覆盖层门控未落地**：IMP-55 可达性门、IMP-11 LLM 接地核验（§6.35）。
4. **can't-miss 表** 与内分泌/化验综合征不对齐，轴极注入 **待数据**（§6.13）。
5. **hybrid→SNOMED 已证伪**（§6.32）；勿用召回数代替 mandatory 覆盖。
6. **curated-free 与 hand 标签** 须分报（§6.33）；A9l 矩阵 **不含** RootSelector 误差。
7. **GuidelineBranchSource** 未作为 BranchCreator 默认供给。
8. **评测规模** 8+14 仍小；IMP-54 recall@k CI **待建**。
9. **片段层 FIFO 与 sibling 预算**：闭包 mean ~~23× 但 LLM 仅见 **~~1.6%**；sibling 进 24 条 **0/8**（§14.4）；14 题常见综合征 gate 池较小，截断相对略轻（24/池 mean **6.4%**），难病更重（§14.5）。
10. **门控与 token 阈值**：`chunk_type` 白名单使 gate 池 ≈ 闭包（IMP-35）；`syn_toks`（len>3）与 gate `_tokens`（len>2）不一致，象限场景可能误拒（§14.2）。
11. **LLM grounding 专用重排未做**：spotter 池 MMR-trim 已证伪有害，但 **24 条 grounding 侧** sibling 配额 / 篇级聚合 / 两阶段 RAG 仍待验证（§14.7）。
12. **同义词 / 词面鸿沟**：TF-IDF 主路径仍依赖词面；**同义词多发 query 证伪**（14 题 L1tgt 可回退，8 题 +0 flip，§14.9）；低成本增量为 **IMP-59 + 索引期 alias 注入**（§14.8）。
13. **dense 选型**：纯 MedCPT **不宜全替** TF-IDF；已验证 **hybrid RRF**（A10 +1.7pp composite）且 L1tgt 略降（§14.10）。
14. **Spotter 频次排序（C4）**：提及次数≠临床重要度；rollup/cant_miss/nominate 已对冲但未根除（§14.11、§6.6）。

## 11. 参考文献（外部）


| 主题                              | 文献/资源                                                 | 借鉴                 |
| ------------------------------- | ----------------------------------------------------- | ------------------ |
| Problem representation & schema | Exercises in Clinical Reasoning; Cammarata & Dhaliwal | L1=域、MECE          |
| DDx generator 评价                | Bond et al.                                           | 召回优先               |
| DXplain / Isabel                | 系统描述                                                  | 疾病–发现关系；can't-miss |
| GARMLE-G                        | Medical Teacher 2024                                  | 查询增强 + 有依据抽取       |
| MedCPT                          | Jin et al., Bioinformatics 2023                       | 混合检索 dense 塔       |
| VINDICATE                       | 医学教育                                                  | 通用筛作兜底             |


---

## 12. 附录：内部任务编号（IMP）对照 — 仅作归档

读者 **不必记忆** 编号；此处供与工程日志对照。


| 编号      | 内容                     | 状态          |
| ------- | ---------------------- | ----------- |
| IMP-31  | CPG 进生产索引 + 元数据        | 实验 ✅ / 生产待办 |
| IMP-11  | LLM 轴缓存接地核验门           | 🔴 待落地      |
| IMP-52  | 五路 query 扇出            | 证伪，默认关      |
| IMP-53  | MedCPT 混合检索            | ✅           |
| IMP-55  | 实体→域可达性门 + residual 注入 | 🔴 待落地      |
| IMP-56  | can't-miss 硬层          | ✅           |
| IMP-57  | 跨源 DDx 一致性投票           | 🔴 待落地      |
| IMP-58  | 机制/标志物直提名              | ✅           |
| IMP-60  | 轴极软注入                  | 代码 ✅，数据 ⚠️  |
| IMP-61  | 分源 UNION 检索            | 弃用主路径       |
| IMP-61b | 锚点 UNION 入口检索          | 备选，次于 A9l   |
| IMP-63  | grounding 闭包 + LLM 抽取  | ✅           |
| IMP-64  | 本体反向归族                 | ✅           |


---

## 13. 修订记录


| 日期         | 说明                                                                                                                                              |
| ---------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| 2026-06-26 | 首版                                                                                                                                              |
| 2026-06-26 | **§2.7**：补充「轴 / 轴极 / 轴可分性 / 轴污染」定义及与 can't-miss 注入关系                                                                                            |
| 2026-06-26 | **§4.4 / §5 / §6.32–§6.35**：整合四源文档中影响 A9l 选型而原未入报告的内容                                                                                           |
| 2026-06-26 | **§6.4–§6.5 补入**：L3 上下文碎片化、C2/C3/IMP-58 命名归一；全节编号顺延                                                                                             |
| 2026-06-26 | **§6 补遗**：纳入 §17 独立分节叙述、未入主表的缺陷（判据混读、轴污染、rag/cpg 分轨、小样本抖动、MRR/IMP-54、snippet 截断、WikEM vs PMC、语料构建、HyDE 等待验证项）                                   |
| 2026-06-26 | **基础流程修订**：新增 §3 完整知识注入框架；§5 与 §3 显式衔接                                                                                                          |
| 2026-06-27 | **§14 附录 B**：纳入 transcript L3370+ 片段层六组技术交流（24 条摘要机制、门控顺序、FAISS/MedCPT、闭包覆盖率实测、召回伤害、sibling/GraphRAG）；**§6.24** 交叉引用 §14.4                      |
| 2026-06-27 | **§14.0 / §14.7**：三口径导读、逐例 sibling 表、`syn_toks` 阈值说明、P0–P2 改进路线图；**§2.6 / §6.24 / §10** 同步交叉引用                                                  |
| 2026-06-27 | **§14.8–§14.11**：同义词/词面鸿沟缓解、同义词 query 证伪、纯 dense vs hybrid、病名频次排序（C4）四组交流入档                                                                     |
| 2026-06-27 | **§2.9**：IMP-64 / IMP-58 **代码实现消歧**（族/保留名额/直提名、误解表、双消费链、对照表）；**§2.8 / §6.10 / §6.12** 同步；原 §2.9 实验臂顺延为 **§2.10**；**§14.12** 交流纪要补入              |
| 2026-06-28 | **§14.8–§14.10 原文补回**：`conversation_export_d6e23c24_dialogue.md` **第 9–11 轮**（及 complete 第 181–183 轮）自会话正文 **手动恢复** — JSON/transcript 无留存       |
| 2026-06-28 | **§14.0.1**：补入 **实验臂性能对比总表**（全栈/确定性/漏斗三表 + 选型速查；与 §7.2、CPG §19.0.6b 对齐）                                                                         |
| 2026-06-28 | **§14.0.1 扩写**：改为交流版 **问—答** 体例；增补 **五条硬结论**、**现象→解释**（A9l vs Hybrid、fanout、retrieved 7/8 vs spotted 8/8、归族、证伪臂、Oracle 落差）、**分场景选型**            |
| 2026-06-28 | **§7.1 / §7.4 / §14.0.1 表 4**：2026-06-27 **8 题四大指标 + MECE** 全矩阵补跑 **归档**（`archive/2026-06-27_hard_mece/`）；区分 gnn-llm **A9l=0.812** 与本机 LLM 失效跑数 |


---

*14 题 LLM 有效 Comp 以 gnn-llm（2026-06-26）为准；8 题 hComp / MECE 以 `branch_confounder_matrix.json`（2026-06-27，`archive/2026-06-27_hard_mece/`）为准。*

## 14. 附录 B：片段层技术交流纪要（交流版）

> **来源**：Cursor 会话 `d6e23c24-82b3-4786-a36b-03356b21f410`，transcript **第 3370 行起**（2026-06-27 整理；**§14.8–§14.11** 为同会话续论补入）。  
> **体例**：下列 **问—答** 与 **§14.0 / §14.7** 是对正文 **§3.4.2–§3.4.4**、**§6.4**、**§6.11**、**§6.24**、**§6.6（C4）** 的 **机制级补遗**（含 2026-06-27 **闭包覆盖率 / 同义词 query / dense 对比脚本实测**），与主文 **不重复编号**，读者可按问跳转。  
> **性能数字与读表结论**：实验臂 **Comp / 漏斗 / 五条硬结论 / 现象解释** 见 **§14.0.1**（交流版自包含；正文 **§7.2** 为精简速查）。


| 交流编号       | 主题                                             | 主文交叉引用                               |
| ---------- | ---------------------------------------------- | ------------------------------------ |
| 14.0       | 三口径导读（gate / retrieved / spotted）              | §6.2、§6.24                           |
| **14.0.1** | **实验臂性能对比：总表（含表 4 难病+MECE）+ 五条结论 + 现象解释 + 选型** | **§7.2**、**§7.4**、§5 选型、CPG §19.0.6b |
| 14.1       | ≤24 条短摘要的具体实现                                  | §3.4.2、§3.4.3                        |
| 14.2       | `snippet_on_topic` 门控标准与检索/块内顺序                | §3.4.2、IMP-35 / `cpg_chunk_gate.py`  |
| 14.3       | FAISS、MedCPT 与 miniLM 的分工                      | §2.3、§4.3、§6.11                      |
| 14.4       | 24 条摘要相对闭包池的覆盖率实测                              | §6.4、§6.24（**新增实测**）                 |
| 14.5       | 24 条 FIFO 截断是否伤害召回率                            | §6.2 漏斗、§6.24、A9l B6                 |
| 14.6       | sibling 利用难是否必须 GraphRAG                       | §6.3–§6.4、§6.10、GraphRAG 待验证         |
| 14.7       | 片段层后续改进路线图（交流归纳）                               | §10、§6.24、IMP 链                      |
| 14.8       | 同义词/词面鸿沟：除 MedCPT 外的缓解层                        | §2.3、§6.5、IMP-58/59                  |
| 14.9       | 同义词多发 query 能否解决检索瓶颈（14+8 实测）                  | §6.7（fanout 证伪）、IMP-59               |
| 14.10      | 纯 dense 替换 TF-IDF 是否有命中机会                      | §6.11、IMP-53、A10                     |
| 14.11      | 病名排序：频次误导风险（C4）与对冲措施                           | §6.6、§2.7、IMP-56/60/64               |
| 14.12      | IMP-64 / IMP-58 代码实现消歧（族/保留名额/直提名）             | **§2.9**、§6.10、§6.12                 |


完整对话 Markdown 归档：`data/cpg/eval/conversation_export_d6e23c24_dialogue.md`（**第 9–11 轮** 2026-06-28 手动补回，JSON 无留存）。

### 14.0 导读：片段层三个易混口径（读 §14.4–§14.5 前先看）

交流实测与 B6 漏斗常因 **度量对象不同** 被误读为矛盾。下表统一口径：


| 口径                      | 度量什么                                               | 8 题难病典型值                                        | 对应代码/脚本                                |
| ----------------------- | -------------------------------------------------- | ----------------------------------------------- | -------------------------------------- |
| **gate 池 gold**         | 闭包 + 门控 + 去重后、**截断前** 全部 eligible 块合并文本是否含 gold    | **6/8**（严格 token 全匹配）/ **7/8**（家族 token 集，≈ B6） | 2026-06-27 覆盖率脚本                       |
| **24 条 retrieved**      | 仅 `**out[:24]`** 合并文本是否含 gold（B6 漏斗 **retrieved**） | **7/8**                                         | `eval_branch_confounder_matrix` funnel |
| **24 条 strict gold@24** | 同上但用 **严格 token 子串**（非家族扩展）                        | **2/8**                                         | 覆盖率脚本逐例表                               |
| **spotted**             | 候选 dict（≤40 实体）是否含 gold                            | A1 **6/8**；A9l **8/8**                          | B6 漏斗 **spotted**                      |


**读法**：闭包把 gate 池做大（mean **~1668 块**），但 LLM 只读 **24 条**；**sibling 块在 FIFO 排序中 8/8 题为 0** → 闭包对 LLM 的边际主要来自「检索 hit 正文」而非 sibling 正文。**A9l 高召回** 靠 Spotter + nominate **不经过** 24 条 cap（典型 **c1**：`spotted_not_in_snippets`）。

---

### 14.0.1 问：各实验臂的分数说明了什么？现象怎么解释、该怎么选？

**答：** 下面用 **交流版** 写法：先说明「测的是什么」，再给 **总表**，然后归纳 **五条硬结论**、逐条 **现象→解释**，最后给 **分场景选型**。不依赖先读正文 §6–§7；细节机制可再跳 **§14.4–§14.12**、正文 **§6–§7**。

---

#### 1. 这套评测在测什么（自包含）

**两套题、两种尺子：**


| 集合        | 题数  | 通俗含义                                       | 主要指标                              |
| --------- | --- | ------------------------------------------ | --------------------------------- |
| **常见综合征** | 14  | 高钙、低钠、黄疸等「教科书级」根节点                         | L1tgt、L1mnd、轴可分、L2 → **综合分 Comp** |
| **难病漏斗**  | 8   | 罕见/刁钻（含 **c1 Pancoast**）；专门看「检索到了吗、抽进候选了吗」 | retrieved、spotted、xloss           |


**共同设定（避免误读）：**

- **hand 标签**：综合征名来自人工 map，**故意排除**「根节点抽错」——只测 **分支召回模块** 本身。
- **实验索引**：`data/corpus/cpg_index`（TF-IDF）；**不是** 生产 StatPearls FAISS。报告里 A9l 等结论 **仅在实验索引成立**（生产合并见 IMP-31）。
- **大模型**：带 LLM 的臂用 qwen3-32b、温度 0；脚本 `eval_branch_confounder_matrix.py`。
- **综合分 Comp**：L1tgt、L1mnd、轴可分、L2 **四项算术平均**（越高越好，满分 1.0）。

**指标白话对照：**


| 指标            | 一句话                                                 |
| ------------- | --------------------------------------------------- |
| **L1tgt**     | 正确答案所属的 **诊断大方向（族）** 有没有出现在 ≤40 个病名候选里              |
| **L1mnd**     | 该综合征 **规定必须覆盖的几个域** 有没有都被候选「投影」到                    |
| **轴可分**       | 分类轴上 **成对相反的方向**（如高钙：PTH 介导 vs 恶性肿瘤）是否 **两边都** 进了候选 |
| **L2**        | 更细的 **子族/具体病名** 有没有进候选                              |
| **retrieved** | 喂给 LLM 的 **24 条短摘要** 合起来有没有 gold 相关词（**片段层**）       |
| **spotted**   | 最终 **≤40 病名 dict** 里有没有 gold（**候选层**）               |
| **xloss**     | 「摘要里明明有 gold，但 Spotter 没抽进 dict」的题数（**抽取损失**）       |


**读表前记住三层（与 §14.0 三口径一致）：**

```text
片段层（24 条 retrieved）→ 候选层（40 名 spotted）→ 覆盖层（投影到 L1 域）
```

很多「矛盾」来自 **量的是不同层**：例如 retrieved 仍 **7/8**，spotted 可到 **8/8**——因为 **nominate / LLM 根本不依赖 24 条**（c1 典型：`spotted_not_in_snippets`）。

---

#### 2. 性能总表

> **数据出处（双轨，勿混读）**  
>
> - **表 1–2、表 3 漏斗（LLM 有效）**：2026-06-26 **gnn-llm** 专跑；**A9l Comp=0.812** 以去掉 fanout 后的 **§19.7** 为准。  
> - **表 4、§7.4**：2026-06-27 全矩阵补跑（`generated_at` 2026-06-27T18:42Z，归档 `archive/2026-06-27_hard_mece/`）；本机 **LLM 调用失败**，带 LLM 臂 14 题 Comp **不可** 替代表 1。  
> **Hybrid** = TF-IDF 与 MedCPT **并联 RRF**（IMP-53），不是替换 TF-IDF。

##### 表 1 — 带 LLM 的「全栈」臂（选型主表）


| 臂         | 检索     | 相对 A1 多了什么                              | L1tgt     | L1mnd     | 轴可分       | L2        | **Comp**  | 漏斗 xloss |
| --------- | ------ | --------------------------------------- | --------- | --------- | --------- | --------- | --------- | -------- |
| **A9l**   | TF-IDF | 归族+轴极+硬层+直提名+**LLM 补抽**；**不开**五路 fanout | **0.929** | **0.821** | **0.714** | 0.786     | **0.812** | **0**    |
| A11_llm   | Hybrid | 同上但 **无轴极注入**；检索换 MedCPT                | 0.857     | 0.774     | 0.643     | **0.857** | 0.783     | 0        |
| A12       | Hybrid | A9l 全栈 + Hybrid                         | 0.857     | 0.756     | 0.643     | **0.857** | 0.778     | 0        |
| A5h_llm   | Hybrid | 早期 A5 栈+LLM（**无直提名**）                   | 0.857     | 0.738     | 0.643     | 0.786     | 0.756     | —        |
| ~~A9l 旧~~ | TF-IDF | **误开** fanout 五路 query                  | 0.929     | 0.780     | 0.571     | 0.786     | 0.766     | 0        |


##### 表 2 — 确定性 / 单开一项（看「谁有用、谁有害」）


| 臂                | 相对 A1 只改了什么                           | L1tgt     | L1mnd | 轴可分       | **Comp**      | 一句话结论              |
| ---------------- | ------------------------------------- | --------- | ----- | --------- | ------------- | ------------------ |
| **A1_grounding** | **基线**：闭包块 **只给 LLM 摘要**，不灌 Spotter 池 | 0.857     | 0.738 | 0.571     | **0.702**     | 稳定锚点               |
| A2_rollup        | +本体归族（IMP-64）                         | 0.786     | 0.708 | **0.643** | 0.704         | **结构↑，综合持平**       |
| A5_llm           | +LLM 从摘要抽病名（未叠表 C 全套）                 | 0.786     | —     | 0.643     | **0.768**     | **最大单杠杆**          |
| A6_fanout        | +五路 facet query（IMP-52）               | 0.857     | 0.702 | 0.571     | 0.693         | **❌ 有害**           |
| A7_nominate      | +机制/标志物直提名（IMP-58）                    | 0.857     | 0.756 | 0.571     | **0.707**     | 漏斗 **xloss 1→0**   |
| A10_hybrid       | **只换** Hybrid 检索                      | 0.786     | —     | 0.643     | **0.719**     | 语义缝+1.7pp，L1tgt 略降 |
| A11_hybrid_nom   | Hybrid+归族+硬层+提名（**无 LLM**）            | 0.786     | —     | 0.643     | **0.723**     | **无 LLM 最佳**       |
| A0_legacy        | 闭包 **灌进** Spotter 40 槽                | —         | —     | —         | 0.54–0.65     | **弃用**（抖动大）        |
| A3_union / A1m   | 分源 UNION / MMR 裁 snippet              | 0.14–0.36 | —     | 0.07–0.21 | **0.24–0.38** | **❌ 证伪**           |


##### 表 3 — 8 题难病漏斗（片段 vs 候选）


| 臂                  | 24 条里摸到 gold（retrieved） | 40 名里摸到 gold（spotted） | xloss | 典型说明                         |
| ------------------ | ----------------------- | --------------------- | ----- | ---------------------------- |
| A1_grounding       | **7/8**                 | 6/8                   | 1     | c13 等：摘要有、Spotter 没抽出        |
| A7 / A9l / A11_llm | **7/8**                 | **8/8**               | **0** | c1：**检索仍无**，靠 **直提名** 进候选    |
| A10_hybrid         | 7/8                     | 7/8                   | 0     | MedCPT **未抬高** retrieved 天花板 |
| A3_union           | 6/8                     | 4/8                   | 2     | PMC 稀释检索                     |


##### 表 4 — 8 题难病：四大指标 + MECE₈（2026-06-27 补跑）


| 臂                                  | hL1tgt | hL1mnd | h轴可分  | hL2   | **hComp** | **MECE₈** | spot  | xloss |
| ---------------------------------- | ------ | ------ | ----- | ----- | --------- | --------- | ----- | ----- |
| **A11_hybrid_nom** / A11_llm / A12 | 0.875  | 0.750  | 0.643 | 0.714 | **0.656** | **0.688** | 1.0   | 0     |
| A9l_tableC_llm / A9b_no_fanout     | 0.875  | 0.688  | 0.643 | 0.643 | 0.622     | 0.594     | 1.0   | 0     |
| A7_nominate                        | 0.875  | 0.688  | 0.571 | 0.643 | 0.583     | 0.562     | 1.0   | 0     |
| A10_hybrid                         | 0.875  | 0.688  | 0.643 | 0.714 | 0.398     | 0.688     | 0.875 | 0     |
| A1_grounding                       | 0.750  | 0.625  | 0.571 | 0.643 | 0.372     | 0.469     | 0.75  | 1     |
| A2_rollup / A5_llm                 | 0.750  | 0.625  | 0.643 | 0.643 | 0.411     | 0.500     | 0.75  | 1     |
| A6_fanout                          | 0.875  | 0.688  | 0.571 | 0.643 | 0.398     | 0.594     | 0.75  | 1     |
| A3_union                           | 0.143  | 0.375  | 0.071 | 0.429 | 0.247     | 0.302     | 0.5   | 2     |


> **MECE₈** = `mece_hard.mece_map_coverage`（候选投影覆盖 gold 域的比例）。**A11_llm/A12 与 A11_hybrid_nom 同分** 因本跑 LLM 未生效；**14 题 MECE₁₄≈0.12** 见 §7.4 读法②。正文对照 **§7.4**。

---

#### 3. 五条硬结论（实验直接支持的）


| #     | 结论                                  | 主要证据                                                        | 对工程的含义                                                       |
| ----- | ----------------------------------- | ----------------------------------------------------------- | ------------------------------------------------------------ |
| **①** | **当前综合最优 = A9l（Comp 0.812）**        | 表 1；L1tgt **0.929**、轴可分 **0.714** 全栈最高档                     | 实验栈首选：**grounding + 全 IMP 链 + LLM 补抽**；**不要**为了综合分强行上 Hybrid |
| **②** | **LLM 从摘要抽病名是最大单杠杆**                | A1→A5_llm：**0.702→0.768**；L1tgt 可到 **0.929**                | 只开一项时优先 **spotter+llm**；确定性-only 天花板低                        |
| **③** | **闭包必须「grounding」，不能灌 Spotter 池**   | A0_legacy **0.54–0.65** 且跨跑抖动 vs A1 **0.702**               | sibling 块给 **LLM 看**，别进 40 名频次竞争（C4）                         |
| **④** | **MedCPT 有价值，但是「第二塔」不是「全替 TF-IDF」** | A10 +1.7pp Comp；**retrieved 仍 7/8**；Hybrid 全栈 **未超** A9l 综合 | 语义检索补 **L2（0.857）**；平面 L1 仍 TF-IDF 主路径                       |
| **⑤** | **机制鸿沟靠直提名，不靠多 query / Graph**      | A7 xloss **1→0**；c1 四路检索皆漏，A9l **spotted 8/8**              | IMP-58 + 硬层与 RAG **并联**；fanout / UNION **已证伪**               |


---

#### 4. 现象 → 可能解释（读表时的「为什么」）

##### 4.1 为什么 A9l 比 A11_llm 综合更高，但 L2 反而更低？

- **现象**：A9l Comp **0.812** vs A11_llm **0.783**；但 A11_llm / A12 的 L2 **0.857** > A9l 的 **0.786**。
- **解释**：MedCPT 擅长 **query 与 chunk 语义近邻**（同义、换说法），有利于 **更细的具体病名** 进候选（L2）。A9l 用 TF-IDF 在 **L1 大方向 + mandatory + 轴极成对** 上已拉满（L1tgt/L1mnd/轴可分更高）。Hybrid 全栈 **没有把综合分推过** unified 全栈，说明当前瓶颈不只在「检索词面」，还在 **抽取链与 40 槽规则**——换检索器 alone 不够。
- **选型**：要 **平面分支/综合** → A9l；要 **子族深度 / 语义匹配** → A11_llm。

##### 4.2 为什么去掉 fanout 后 A9l 从 0.766 跳到 0.812？

- **现象**：旧 A9l **误开** IMP-52 五路 query；轴可分 **0.571**；去 fanout 后 Comp **0.812**、轴可分 **0.714**（+14pp）。
- **解释**：多 query **不是**「多搜几次就更全」。额外 query 拉回大量 **泛化、离题** PMC 块，挤占 24 条 FIFO 与 Spotter 的 top-30；**轴极成对** 更容易只剩一侧（轴可分暴跌）。A6_fanout 单独开也 **低于** A1（0.693 vs 0.702）。
- **教训**：query **贵精不贵多**；机制/专名鸿沟用 **nominate / 别名表**，不是 fanout。

##### 4.3 为什么 retrieved 长期卡在 7/8，spotted 却能到 8/8？

- **现象**：多数臂 retrieved **7/8**；A9l / A7 spotted **8/8**，xloss **0**。
- **解释**：
  - **7/8 那 1 题** 通常是 **c1**：综合征标签与 gold 病名 **无共同英文词**，TF-IDF/Hybrid **24 条摘要里都没有** Pancoast 相关块（全库仅极少数 chunk 含该词）。
  - **第 8 题进候选** 靠 **IMP-58 直提名**（context 里 Horner / apical lung → 规则表写进 40 名），**不经过** snippet 检索——故 `spotted_not_in_snippets`。
  - 另 1 题 xloss（A1）常是 **c13**：摘要 **有** glucagonoma，但 Spotter **字面抽失败** → LLM 补抽或 nominate 可修。
- **与 §14.4–§14.5 一致**：**片段层** 与 **候选层** 应分开看；A9l 高召回是 **多支路并联**，不是 24 条 alone 变好。

##### 4.4 为什么本体归族（A2）抬轴可分、综合却几乎不动？

- **现象**：A2 轴可分 **0.571→0.643**；Comp **0.704** ≈ A1 **0.702**。
- **解释**（§2.9.1）：归族只在 **spot 后 >40 病名** 时，为 **整族在 top-40 里灭门** 的超族 **留最多 5 个末尾槽**——换进的是 **具体病名**，不是用族名替换。价值在 **诊断树结构**（成对轴极、族代表不缺席），**不是** flat 频次排序大涨。L1tgt 在 A2 表项略降，因指标对 **flat 候选 token** 敏感，与「结构更合理」不完全同向。
- **结论**：IMP-64 **值得保留在全栈**；**不能**指望它 alone 把 Comp 从 0.7 拉到 0.8——那一步靠 **LLM + 提名**。

##### 4.5 为什么 A0 灌池、UNION、MMR-trim 会崩？


| 做法                       | 现象                      | 可能解释                                                                                                |
| ------------------------ | ----------------------- | --------------------------------------------------------------------------------------------------- |
| **A0 闭包灌 Spotter 池**     | Comp **0.54–0.65**，跨跑抖动 | 同篇 sibling 成百上千块 **累加频次**；MI、urticaria 等 **占满 40 槽**（C4）， rare gold 被挤掉；Python set 顺序 + 截断 → **方差** |
| **A3 分源 UNION**          | Comp **0.235**          | 等权并 PMC/WikEM **稀释** 主检索；top-k 被无关源 chunk 占满                                                        |
| **A1m MMR-trim snippet** | Comp **0.376**          | 为减噪 **裁窄** Spotter 可见块 → **饿死广度**；mandatory/轴可分需要多看几块 DDx 列表                                        |


##### 4.6 为什么 Oracle 说语料「够」，实验分仍不高？

- **现象**：entry+closure Oracle **8/8**；A1 候选层约 **4/8–6/8**；A9l Comp **0.812** 仍远低于 1.0。
- **解释**：数据 **可达** ≠ 流水线 **无损**。损耗在：① TF-IDF 排序 + **24 条 FIFO**（§14.4）；② Spotter **频次主导** 40 名（§14.11）；③ **mandatory/投影** 与 recall 分轨（gold 在候选但投不进域）；④ 8 题 hard 的 **multilevel_hard Comp ~0.37–0.66**——难病集 **mandatory/轴** 仍弱，与 14 题常见集不可比。
- **含义**：下一步优先 **工程层**（grounding、LLM、nominate、归族），不是先换语料或上 GraphRAG 推倒重来。

---

#### 5. 分场景怎么选（通俗版）


| 你的目标                          | 推荐                                    | 原因（一句话）                                         |
| ----------------------------- | ------------------------------------- | ----------------------------------------------- |
| **整体最好、写进报告/对标**              | **A9l**                               | 综合 **0.812**，漏斗 xloss **0**，配置已去 harmful fanout |
| **不能调用 LLM、只要程序**             | **A11_hybrid_nom**                    | 14 题 **0.723**；8 题 **hComp 0.656**（表 4）         |
| **特别在意具体病名 / 语义近邻**           | **A11_llm**                           | L2 **0.857** 最高；接受 Comp 低于 A9l                  |
| **验证「加 MedCPT 有没有用」**         | **A10 vs A1**                         | +0.017 Comp；**不要**期望 retrieved 7→8              |
| **验证「Horner→Pancoast 这类机制桥」** | **A7 vs A1**                          | 漏斗 xloss **1→0**；与检索无关                          |
| **明确不要**                      | A6 fanout、A3 UNION、A1m MMR-trim、A0 灌池 | 实测 **有害或崩盘**                                    |


**与生产的关系（避免误读）：** 上表是 **CPG 实验索引 + hand 标签** 上的召回层上限；生产默认仍是 **A∪C 并集 + StatPearls FAISS** 保 MECE **覆盖下界**。A9l 与生产 **双轨并行**，靠 IMP-31 索引合并与方案 A 起草 **收敛**，不是二选一替换。

---

#### 6. 与 §14 其它问答的关系


| 想深入的问题                      | 跳转到                 |
| --------------------------- | ------------------- |
| 24 条 / gate / retrieved 三口径 | **§14.0**           |
| 闭包为何只留 ~1.6% 进 24 条         | **§14.4**           |
| 24 条是否伤害召回                  | **§14.5**           |
| 同义词 query、纯 dense、频次误导      | **§14.8–§14.11**    |
| 归族 / 直提名 代码含义               | **§2.9**、**§14.12** |


**数据与配置明细**：`data/cpg/eval/branch_confounder_matrix.json`；臂开关完整列 `**CPG_RAG_EXTRACTION.md` §19.0.6b(3)**。正文精简表见 **§7.2**。

---

### 14.1 问：整理成 ≤24 条短摘要的具体做法是如何

**答：**

**「≤24 条短摘要」** 指：大模型 **不读整库 chunk**，只读 `_retrieve_snippets()` 产出的 **最多 24 条** 格式化 prose。实现如下。

#### 流程概览

```text
4–5 条 query
  → 每条 TF-IDF top_k=30
  → expand_ddx_siblings（同篇闭包，grounding 路径始终开）
  → snippet_on_topic 门控
  → 按 title+content 前段去重
  → 格式化为 "[标题] 正文前400字"
  → 合并后硬截断 out[:24]
  → 喂 recall_llm / build_branch_knowledge_llm
```

Spotter 仍只读 **检索 top-30**（grounding 模式下闭包块 **不进** 40 槽候选池）；闭包信息经上述 24 条摘要间接给 LLM。

#### 逐步说明

**1. 构造 query（约 4–5 条）**

- `"differential diagnosis of {综合征}"`
- `"causes and etiology of {综合征}"`
- 若有口语别名：再加 `"approach to {colloquial}"`
- 若有病例 context：再加 `"differential diagnosis of … clinical features: {context 前300字}"`

**2. 检索 + 闭包**

每条 query 调用 `search(top_k=30)`，再 `expand_ddx_siblings(hits)` 拉同 `source_id` 的 sibling 块。闭包后 hit 数可远大于 30（实验索引上常见 8→213），但 **尚未截到 24**。

**3. 门控**

`snippet_on_topic()` 按 `chunk_type` / `entry_type` / `syndrome_anchor` 等过滤离题块（NICE recommendation、无关 PMC 散文等）。

**4. 去重**

签名 `title[:60] + "|" + content[:40]`；重复块只保留一条。

**5. 格式化为「短摘要」**

每条变成一行字符串：

```text
[{title 前70字符}] {content 前400字符}
```

对应代码：

```651:652:src/agentclinic_tree_dx/knowledge/guideline_branch_source.py
                out.append(f"[{title[:70]}] {content[:400]}")
        return out[:24]
```

**6. 硬上限 24 条**

所有 query 的命中 **按 query 顺序、块内检索顺序** 依次 append；满 24 即停（`out[:24]`）。**无 MMR/重排**——MMR 只用于 Spotter 路径的 `_gather_spot_hits`，不用于 LLM 摘要。

理论字符上界约 **24 × 400 ≈ 9600**（再加标题前缀），报告中的 ~9.6k 即由此而来。

#### 谁消费这 24 条


| 消费者                            | 用途                                             |
| ------------------------------ | ---------------------------------------------- |
| `recall_llm()`                 | GARMLE-G②：LLM 只许列出 **摘要里出现过的** 病名，与 Spotter 合并 |
| `build_branch_knowledge_llm()` | 方案 A：LLM 定 MECE 域 + mandatory                  |


Prompt 里字段名为 `reference_excerpts`，即这 ≤24 条字符串列表。

#### 与 Spotter 的分工（grounding 模式）

```text
检索 top-30 块     → Spotter 做 n-gram 匹配 → max_candidates=40
同篇 sibling 块    → 只进 _retrieve_snippets → ≤24 条摘要 → LLM 有依据补抽
```

因此：**不是**把 200+ 闭包块都灌进 Spotter；扩展块以 **截断 prose 摘要** 形式给 LLM，避免 C4 候选池拥挤（§6.6）。

#### 已知边界

- 长 DDx 枚举 **400 字后被截断**，列表后半可能进不了 LLM 上下文（§6.24）。
- 24 条按 **检索顺序** 截取，不保证覆盖所有 sibling；靠闭包扩大候选池、靠 LLM 从已入选摘要里抽实体。
- 增大 24 或 400 **单独调参尚未证** 优于当前 A9l 全栈。

---

### 14.2 问：snippet_on_topic()的过滤标准具体有哪些？ 按 query 顺序、块内检索顺序 具体而言是什么样的顺序？

**答：**

`snippet_on_topic()` 是 **IMP-35** 引入的门控：判断一条检索 hit 是否与当前综合征的 DDx/病因召回相关。下面按 **判定顺序** 和 **24 条摘要的排列顺序** 说明（对应 `_retrieve_snippets()` → LLM grounding 路径）。

---

#### 一、`snippet_on_topic()` 过滤标准

实现见 `cpg_chunk_gate.py`，逻辑是 **短路式 OR**：任一条件满足即 **通过**；全部不满足则 **丢弃**。

##### 输入


| 参数                                                               | 含义                                                                   |
| ---------------------------------------------------------------- | -------------------------------------------------------------------- |
| `syndrome_tokens`                                                | 来自综合征名：`re.findall(r"[a-z0-9]+", syn)` 且 `**len(t) > 3`** 的 token 集合 |
| `chunk_type` / `entry_type` / `syndrome_anchor` / `section_path` | 来自 chunk 元数据（依赖 IMP-31 索引是否写入这些字段）                                   |


门控内部 `_tokens()` 用 `**len(t) > 2**` 做交集匹配，但 syndrome 侧只传入 **>3** 的 token，所以短词（如 `pain`）不会参与 syndrome 侧匹配。

##### 判定链（按代码执行顺序）

**① `chunk_type` 白名单 — 直接通过，不做 syndrome 相关性检查**

```7:9:src/agentclinic_tree_dx/knowledge/cpg_chunk_gate.py
_USEFUL_CHUNK_TYPES = frozenset(
    {"differential", "red_flag", "evaluation", "recommendation", "diagnostic"}
)
```

若 `chunk_type ∈` 上述集合 → **True**。  
这是 IMP-35 的核心：NICE「Recommendations」、WikEM「Clinical Features」等标题不含 DDx 字面，但 `chunk_type` 正确时仍保留。

**② `entry_type == "syndrome_entry"` + anchor 匹配**

- 取 `syndrome_anchor`，若无则取 `title` 中 `>` 前的第一段
- 若 `syndrome_tokens ∩ _tokens(anchor) ≠ ∅` → **True**

**③ 章节语义正则 + syndrome token 重叠**

拼接 `blob = title + section_path + content[:200]`，用 `_SECTION_RE` 匹配是否含：

```
differential diagnos | etiolog | causes | evaluation | work-up/workup |
assessment | clinical features | red flag | can't miss | must not miss |
recommendations | approach
```

若匹配，还需满足以下 **之一**：

- `syndrome_tokens ∩ _tokens(title) ≠ ∅`
- `section_path` 存在且 `syndrome_tokens ∩ _tokens(section_path) ≠ ∅`

**④ 象限/解剖部位标题**

- `title` 含 `RUQ/RLQ/LUQ/LLQ/epigastric/pelvic`（不区分大小写）
- 且 `syndrome_tokens ∩ _tokens(title) ≠ ∅` → **True**

**⑤ 兜底：仅看 title**

- `syndrome_tokens ∩ _tokens(title) ≠ ∅` → **True**
- 否则 → **False**

##### 要点

- **不是**「必须 title 含 Differential Diagnosis」的旧逻辑；`chunk_type` 或 anchor 匹配即可绕过标题字面要求。
- 无 `chunk_type` 的旧索引上，大量 chunk 会落到 ③–⑤，CPG 文档里 ~81–90% 误滤率主要来自这条路径。
- 通过门控后还有 **去重**：`sig = title[:60] + "|" + content[:40]`，与门控独立。

---

#### 二、按 query 顺序：`_retrieve_snippets()` 的 2–4 条 query

```618:624:src/agentclinic_tree_dx/knowledge/guideline_branch_source.py
        queries = [f"differential diagnosis of {syndrome}",
                   f"causes and etiology of {syndrome}"]
        if colloq and colloq != syn:
            queries.append(f"approach to {colloq}")
        if context.strip():
            queries.append(f"differential diagnosis of {colloq or syndrome}. "
                           f"clinical features: {context.strip()[:300]}")
```


| 序号  | 条件                                                | Query 文本                                                                             |
| --- | ------------------------------------------------- | ------------------------------------------------------------------------------------ |
| Q1  | 始终                                                | `differential diagnosis of {syndrome}`                                               |
| Q2  | 始终                                                | `causes and etiology of {syndrome}`                                                  |
| Q3  | `colloq ≠ syndrome`（经 `_colloquial()` 去 jargon 后） | `approach to {colloq}`                                                               |
| Q4  | `context` 非空                                      | `differential diagnosis of {colloq or syndrome}. clinical features: {context[:300]}` |


注意：Spotter 路径的 `_build_queries()` 在 Q3 前还有 `differential diagnosis of {colloq}`，且 `query_mode=fanout` 时再加 5 条 facet query；`**_retrieve_snippets()` 没有这些**，LLM grounding 用的 query 列表更短。

每条 query：`search(top_k=k, score_threshold=0.0)` → **始终** `expand_ddx_siblings(hits)`（与 Spotter 在 `closure_mode='grounding'` 下不同，grounding 路径不做 sibling 扩展的是 spot pool，不是 `_retrieve_snippets`）。

---

#### 三、块内（单条 query 内 hits）顺序

对 **每一条 query**，处理顺序如下：

```
search(top_k)          → 按检索分数降序（最相关在前）
expand_ddx_siblings    → [原 hits] + [扩展块]
逐块 gate + 去重       → 通过的 append 到全局 out
全局截断               → out[:24]
```

##### 3.1 `search()` 返回顺序

- **FAISS**：`index.search` 返回的 `(score, idx)` 顺序，**分数从高到低**（`score_threshold=0.0` 时 top_k 内基本全保留）。
- **TF-IDF**：`argsort(scores)[::-1][:top_k]`，同样是 **相似度降序**。

##### 3.2 `expand_ddx_siblings()` 追加顺序

返回 `**hits + extra`**，原检索结果顺序不变，扩展块接在后面：

1. **原 hits**：保持 search 的分数序（rank 1 → rank k）
2. **对每个原 hit 依次**：若有 `wiki_links`，合成一条 `chunk_type=differential` 的虚拟块追加
3. **对每个 hit 的 `source_id`（去重，顺序≈首次出现在 hits 中的顺序）**：
  - 从 `_sid_index[sid]` 取同文 sibling（`_DDX_USEFUL` 类型：`differential/red_flag/evaluation/recommendation/diagnostic`）
  - sibling 顺序 = **语料 metadata 文件中的索引顺序**（`enumerate(self._metadata)` 写入 sid_index 的顺序），**不是** relevance 重排
  - 每个 sibling 若还有 `wiki_links`，再追加虚拟块

##### 3.3 单 query 内的遍历与占位

```627:652:src/agentclinic_tree_dx/knowledge/guideline_branch_source.py
        for q in queries:
            ...
            for h in hits:
                ...
                if not snippet_on_topic(...):
                    continue
                ...
                out.append(f"[{title[:70]}] {content[:400]}")
        return out[:24]
```

对扩展后的 `hits` 列表 **从前到后**：

1. `snippet_on_topic` → 不过则 skip
2. `sig` 去重 → 重复则 skip
3. 格式化 append

**无 MMR、无按 score 二次排序**；顺序就是「query 优先级 × 块在 expanded hits 中的位置」。

---

#### 四、全局 24 条的总顺序（直观）

```mermaid
flowchart TD
    Q1[Q1: differential of syndrome] --> H1[search top_k 按分数降序]
    H1 --> E1[expand_ddx_siblings]
    E1 --> F1[gate + dedupe → out]
    Q2[Q2: causes/etiology] --> H2[同上]
    H2 --> F2[append 到 out 尾部]
    Q3[Q3: approach to colloq 可选] --> F3[append]
    Q4[Q4: context 可选] --> F4[append]
    F4 --> CAP[out[:24] 截断]
```



**优先级规则**：

1. **Query 间**：Q1 占满 24 槽后，Q2–Q4 的块进不来（先 query 先占位）。
2. **Query 内**：检索 rank 高的原 hit 优先；sibling / wiki_links 扩展块排在对应 query 的原 hits 之后。
3. **跨 query 去重**：同一 `sig` 只在 **第一次出现** 时保留（通常保留在更靠前 query 里的那次）。

最终每条格式：`[{title[:70]}] {content[:400]}`，最多 **24** 条。

---

#### 五、与 Spotter 路径的差异（便于对照）


| 维度         | `_retrieve_snippets`（LLM grounding） | `_gather_spot_hits` / `_recall_v2`（Spotter） |
| ---------- | ----------------------------------- | ------------------------------------------- |
| Query 数    | 2–4                                 | `_build_queries`：2–5+，fanout 时最多 10         |
| sibling 扩展 | **始终** expand                       | 仅 `closure_mode='pool'` 时 expand            |
| 截断/重排      | 固定 `out[:24]`，无 MMR                 | 可经 `_mmr_select` 多样性裁剪                      |
| 门控函数       | 同一 `snippet_on_topic()`             | 同一                                          |


##### `syn_toks` 与 gate `_tokens` 长度阈值不一致（待修细节）


| 侧                                          | 规则           | 影响                                |
| ------------------------------------------ | ------------ | --------------------------------- |
| `_retrieve_snippets` 传入的 `syndrome_tokens` | `len(t) > 3` | 综合征侧 **不含** `pain`、`arm` 等短 token |
| 门控内 `_tokens()`                            | `len(t) > 2` | 块侧 title/anchor **含** 上述短词        |


**后果**：象限/解剖场景（如 **RUQ pain**）中，块 title 有 `pain` 但 syndrome 侧无 `pain` → 规则 ④ 可能 **误拒**；反之 syndrome 有长 token 时块侧短词不参与匹配 → 规则 ⑤ 更严。改进方向：统一阈值，或象限规则不要求 syndrome 侧含解剖短词。

---

### 14.3 问：这个FAISS指的是MedCPT或miniLM吗

**答：**

**不是。** FAISS 本身既不是 MedCPT，也不是 miniLM——它是 **向量近邻检索库**（存 embedding、做 top-k 搜索）。真正决定语义的是 **建索引时用的 encoder**，写在各索引目录的 `config.json` 里。

---

#### 三层关系

```
Query 文本
  → Encoder（MiniLM / MedCPT / …）编码成向量
  → FAISS（或 TF-IDF）在索引里做 top-k
  → hits 列表 → snippet_on_topic → 24 条摘要
```

我上一条里说的「FAISS 按分数降序」，指的是 **若** `RAGRetriever` 检测到 `faiss.index` 并走 dense 后端时的行为；**不等于**分支实验默认就在用 FAISS。

---

#### 本仓库里各索引实际用什么


| 索引目录                           | 后端                  | 编码模型                                                                 | 用途                            |
| ------------------------------ | ------------------- | -------------------------------------------------------------------- | ----------------------------- |
| `data/corpus/rag_index`        | **FAISS**           | `**all-MiniLM-L6-v2`**（384 维）                                        | StatPearls + Textbooks 通用 RAG |
| `data/corpus/cpg_index`        | **TF-IDF**（无 FAISS） | sklearn 稀疏向量，无神经网络                                                   | 分支实验主索引（A9l 等）                |
| `data/corpus/cpg_medcpt_index` | **FAISS**           | `**ncbi/MedCPT-Article-Encoder`**（768 维）；查询侧用 `MedCPT-Query-Encoder` | IMP-53 hybrid 的 dense 塔       |


对应 `config.json`：

- `cpg_index`：`"model": "tfidf"`, `"index_type": "TfidfSparse"`
- `rag_index`：`"model": "/data2/wanghongyi/models/all-MiniLM-L6-v2"`
- `cpg_medcpt_index`：`"model": "ncbi/MedCPT-Article-Encoder"`

`RAGRetriever` 的加载逻辑是：**先看有没有 `faiss.index`**，没有再看 `**tfidf_matrix.npz**`：

```64:88:src/agentclinic_tree_dx/knowledge/rag_retriever.py
        # Try FAISS first
        faiss_path = self._index_dir / "faiss.index"
        if faiss_path.exists():
            ...
                self._backend = "faiss"
        ...
        # Try TF-IDF
        tfidf_path = self._index_dir / "tfidf_matrix.npz"
        ...
                self._backend = "tfidf"
```

FAISS 路径下，query 编码用 `config.json` 里的 `model`（通过 `SentenceTransformer` 加载）——MiniLM 或 MedCPT 取决于 **哪个目录的 FAISS**。

---

#### 和分支实验 / `_retrieve_snippets` 的关系

- **A9l、A1_grounding 等默认臂**：`RAGRetriever("data/corpus/cpg_index")` → `**cpg_index` 是 TF-IDF**，前面讨论的检索排序是 **TF-IDF 余弦相似度降序**，不是 MedCPT 也不是 miniLM。
- **A10/A11 hybrid 臂**：`HybridCPGRetriever` = **TF-IDF（sparse）+ MedCPT FAISS（dense）**，两路 RRF 融合后再进同一套 gate / 24 条截断。

MedCPT **不会**自动替代 `cpg_index` 的 TF-IDF；只有显式用 `HybridCPGRetriever` 或把 retriever 指到带 MedCPT FAISS 的索引时才会参与。

---

#### 一句话

- **FAISS** = 检索引擎  
- **miniLM** = `rag_index`（StatPearls/Textbooks）的 FAISS 编码器  
- **MedCPT** = `cpg_medcpt_index` 的 FAISS 编码器（hybrid dense 塔）  
- **分支 phase 主路径** = `cpg_index` 的 **TF-IDF**，两者都不是

---

### 14.4 问：24条摘要实测在所有闭包中包含多大比例的chunk？会遗漏多少？

**答：**

**结论先说：** 在本仓库 `cpg_index` + `_retrieve_snippets()`（`top_k=30`、4 条 query、`expand_ddx_siblings`、门控、`out[:24]`）配置下，24 条摘要只覆盖闭包扩展后 chunk 的约 **1–3%**（8 题难病集均值 **1.6%**），相对门控后 eligible 池遗漏约 **98%**（均值 **1644 块/题**）。功能上 gold 命中率从 gate 池 **6/8** 降到 24 条 **2/8**。

---

#### 测量口径


| 层级         | 含义                                                      |
| ---------- | ------------------------------------------------------- |
| **检索**     | 4 条 query × `search(top_k=30)` 的去重 chunk 数              |
| **闭包**     | 对上述 hits 做 `expand_ddx_siblings` 后的 **unique chunk id** |
| **gate 池** | 闭包遍历 + `snippet_on_topic` + sig 去重（**截断前**全量 eligible）  |
| **24 条**   | gate 池按 query/块顺序 FIFO 取前 24                            |


这与 `grounding` 模式下 LLM 实际读到的 excerpt 一致；**不是** spotter 的 40 槽候选池。

---

#### 8 题难病集（medbullets hard）


| 指标                  | min   | max   | mean     | median |
| ------------------- | ----- | ----- | -------- | ------ |
| 检索 unique           | 48    | 114   | **73**   | 72     |
| **闭包 unique**       | 861   | 2393  | **1687** | 1772   |
| 闭包新增 sibling        | 813   | 2279  | **1614** | 1700   |
| 闭包/检索倍率             | 17.9× | 29.9× | **~23×** | —      |
| **gate 池**          | 840   | 2355  | **1668** | 1761   |
| **→24 保留占闭包**       | 1.0%  | 2.9%  | **1.6%** | 1.4%   |
| **→24 保留占 gate 池**  | 1.0%  | 2.9%  | **1.6%** | 1.4%   |
| **遗漏（gate 池 − 24）** | 816   | 2331  | **1644** | 1737   |


逐例 gold（token 子串匹配）：


| case             | 闭包   | gate 池 | 24 条 | gold@gate | gold@24 |
| ---------------- | ---- | ------ | ---- | --------- | ------- |
| c1 Pancoast      | 2393 | 2355   | 24   | ✓         | ✗       |
| c9 leukemoid     | 1699 | 1685   | 24   | ✗         | ✗       |
| c13 glucagonoma  | 2101 | 2074   | 24   | ✓         | ✗       |
| c17 CML          | 1772 | 1761   | 24   | ✓         | ✗       |
| c18 peliosis     | 2186 | 2165   | 24   | ✗         | ✗       |
| c22 PHPT         | 1025 | 1023   | 24   | ✓         | ✓       |
| c23 adhesions    | 861  | 840    | 24   | ✓         | ✓       |
| c24 foreign body | 1455 | 1437   | 24   | ✓         | ✗       |


- **gate 有、24 漏 gold**：c1、c13、c17、c24（4/8）
- **24 条中来自 sibling 闭包块**：8 题均为 **0** — 24 槽全被各 query 的 **top 检索 hit** 占满，sibling 在遍历顺序上排在后面

**逐例：检索 hit 数 vs sibling 贡献（2026-06-27 脚本）**


| case             | 检索 unique | 闭包 unique | +sibling | 闭包/检索 | 24 条中 sibling 块 |
| ---------------- | --------- | --------- | -------- | ----- | --------------- |
| c1 Pancoast      | 114       | 2393      | 2279     | 21.0× | **0**           |
| c9 leukemoid     | 71        | 1699      | 1628     | 23.9× | **0**           |
| c13 glucagonoma  | 95        | 2101      | 2006     | 22.1× | **0**           |
| c17 CML          | 72        | 1772      | 1700     | 24.6× | **0**           |
| c18 peliosis     | 73        | 2186      | 2113     | 29.9× | **0**           |
| c22 PHPT         | 53        | 1025      | 972      | 19.3× | **0**           |
| c23 adhesions    | 48        | 861       | 813      | 17.9× | **0**           |
| c24 foreign body | 55        | 1455      | 1400     | 26.5× | **0**           |


**含义**：mean **~1614** 块/sibling 被闭包拉入，但 **无一题** 进入 24 条 — 问题在 **FIFO 预算分配**，不是闭包未触发。

---

#### 14 题 multilevel 集


| 指标         | 范围         | mean      |
| ---------- | ---------- | --------- |
| gate 池     | 78–1555    | **771**   |
| 24/ gate 池 | 1.5%–30.8% | **6.4%**  |
| 遗漏块数       | —          | **747**/题 |


22 题（8+14）**无一题** gate 池 < 24，故最终摘要恒为 **24 条**（不是「池子小所以全保留」）。

文档对照 `abdominal pain`（≈ §15.1 的 8→213 量级）：闭包 **758**、gate **748**、24 条约 **3.2%**。

---

#### 为何 gate 池 ≈ 闭包、但 24 条只留 ~1–3%

1. **门控几乎不过滤闭包块**
  `chunk_type ∈ {differential, red_flag, evaluation, recommendation, diagnostic}` → **直接通过**，多数 PMC sibling 带 `evaluation/diagnostic`，gate 池规模接近闭包（1668 vs 1687，差 ~1%）。
2. **24 是 FIFO 截断，不是 relevance 重排**
  `expand_ddx_siblings` 返回 `原 hits + sibling`；遍历先走完 Q1 的 top-30 检索块，再 Q2…  
   难病集平均 **73 个检索块** 经 gate 后仍远超 24，**24 槽在 sibling 之前就满** → sibling 闭包对 LLM grounding **名义上扩展了 ~23×，实际 24 条里 0 块来自 sibling**。
3. **信息压缩比**
  均值 ~1668 块 × ~400 字/块 ≈ **66 万字** prose → 24 × 400 ≈ **9600 字**（约 **1.5%** 字符量）。

---

#### 和文档「8→213」的关系

§15.1 的 **8→213** 是 **单次 query、闭包扩展后 hit 列表长度**（未计 4 query 合并、门控、24 截断）。  
完整 `_retrieve_snippets` 链路上闭包 mean **~1687 unique**，但 **24 条只保留 ~1.6%**；闭包对 LLM 的主要价值不是「把 200+ 块都喂进去」，而是 **扩大 gate 池以便更高概率摸到 gold**——实测 gate 池 6/8 有 gold，截断后只剩 2/8。

---

#### 一句话

**24 条摘要 ≈ 闭包/eligible 池的 1–3%，遗漏 ~97–99% 的块；对难病 gold，gate 池 75% 命中 → 24 条 25% 命中，主要因为 sibling 闭包块排在 FIFO 24 槽之后。**  
若要让闭包里的 gold sibling 进 LLM 上下文，需要改排序（MMR/relevance）、提高 cap、或优先保留含 `source_id` 闭包块——当前 `_retrieve_snippets` 未做这些。

---

### 14.5 问：这种方式是否潜在地伤害了召回率

**答：**

**会，但伤害集中在 LLM grounding 支路；对 A9l 全栈召回是「有条件、可部分代偿」的。**

---

#### 1. 先分清：24 条 cap 打在哪一层


| 路径                                                   | 是否受 `out[:24]` 约束                    | 对最终候选召回的影响                            |
| ---------------------------------------------------- | ------------------------------------ | ------------------------------------- |
| **Spotter**（`_gather_spot_hits`）                     | **否**（`grounding` 模式下闭包不进 spotter 池） | 直接不受影响                                |
| `**recall_llm` / 方案 A**                              | **是**（只读 ≤24 条 excerpt）              | **直接上限**：LLM 规则写死「只许列 excerpt 里出现的病名」 |
| **A9l 全栈**（Spotter + LLM + nominate + pathognomonic） | LLM 支接受限；其它支路可补                      | **部分代偿**                              |


因此不能笼统说「24 条伤害了召回率」，要说 **伤害了哪条支路、在什么 case 上、最终有没有被其它机制补回来**。

---

#### 2. 实测：对「片段层 retrieved」的伤害是真实存在的

B6 漏斗里的 **retrieved** = 合并 `_retrieve_snippets()` 的 24 条文本里是否含 gold（家族 token 匹配），**不是**全 gate 池。

**A1_grounding（8 题难病）**：


| 指标              | 值               | 含义                                      |
| --------------- | --------------- | --------------------------------------- |
| retrieved_rate  | **7/8 (87.5%)** | 24 条里摸到 gold                            |
| spotted_rate    | **6/8 (75%)**   | 候选 dict 含 gold                          |
| extraction_loss | **1**           | 片段有 gold 但 spotter 没抽出（c13 glucagonoma） |
| neither         | **1**           | 24 条和候选都没有（c1 Pancoast）                 |


与我们刚跑的 **gate 池 vs 24 条**对照：

- gate 池（截断前）摸到 gold：**约 6/8**（严格 token）到 **7/8**（家族匹配，与 B6 口径接近）
- 24 条内：**7/8**（B6 官方口径）
- **闭包 sibling 进 24 条：0/8** — 扩展了 ~1600 块，FIFO 24 槽全被各 query 的 top 检索 hit 占满，sibling 对 LLM 上下文 **名义扩展、实质未进入**

**结构性矛盾**：`expand_ddx_siblings` 把闭包拉到 ~~23×，但 `_retrieve_snippets` 只留 **~~1.6%**；对 **§18 类「gold 只在 sibling 块」**（c1  archetype），24 条 cap + FIFO 顺序会 **系统性挡在 LLM 门外**。

---

#### 3. 对最终召回：全栈可代偿，LLM 单支路不行

**A9l** 上同一 8 题漏斗：


| 指标                    | A1_grounding | A9l     |
| --------------------- | ------------ | ------- |
| retrieved（24 条含 gold） | 7/8          | 7/8     |
| spotted（候选含 gold）     | 6/8          | **8/8** |
| extraction_loss       | 1            | **0**   |


典型 **c1 Pancoast**：

- `retrieved: false` — 24 条摘要 **不含** gold
- `spotted: true` — 候选里有 `pancoast tumor`（经 **nominate / pathognomonic**，非 LLM 读摘要）
- bucket = `**spotted_not_in_snippets`**

说明：

1. **24 条 cap 确实挡了 LLM grounding**（`recall_llm` 对 c1 帮不上忙，excerpt 里没有就不能列）。
2. **A9l 最终召回没被这一层拖死**，因为 Spotter + 直提名等 **不依赖 24 条**。
3. 若走 **纯 LLM 抽取** 或 **方案 A 单次 LLM 建域**，24 条 cap 的上限会更硬。

---

#### 4. 伤害机制（按严重度）

```
闭包扩展 ~1687 块
    ↓ gate 池 ~1668 块（chunk_type 白名单，几乎全过）
    ↓ FIFO 取前 24（≈ 全来自 top 检索 hit，0 来自 sibling）
    ↓ LLM 只能 grounded 读这 24 条
    ↓ gold 若在 sibling / 排序 25+ → LLM 支路永久丢失
```


| 场景                            | 24 条 cap 的伤害                                               |
| ----------------------------- | ---------------------------------------------------------- |
| gold 在 top 检索 hit 正文          | **低**（B6 7/8 retrieved）                                    |
| gold **只在 sibling 闭包块**（c1）   | **高** — LLM 不可达；需 nominate/机制桥接                            |
| gold 在 gate 池但排序 25+（被常见病块挤掉） | **中** — 如 c13：A1 里 retrieved=✓ 但 spotter 仍失败，A9l 靠 LLM 补抽取 |
| 14 题常见综合征                     | gate 池较小（mean ~771），24/池 mean **6.4%**，相对 8 题伤害略轻，但仍截断     |


---

#### 5. 和「grounding 改闭包去向」的权衡

把闭包从 spotter 池挪到 grounding（IMP-63）**解决了 C4**（常见病灌 40 实体槽），但把瓶颈挪到 **LLM 输入侧**：

- **Spotter 召回**：不再被 200+ sibling 块污染 → **受益**（A1 grounding 0.702 vs legacy 0.54–0.65）
- **LLM 召回**：只有 24×400≈9600 字 → **新瓶颈**；闭包 sibling 对 LLM **几乎零贡献**（实测 0/8）

文档 §19.5 也指出：MMR/`extract_k` 裁剪 spotter 有害，但 `**_retrieve_snippets` 的 24 cap「仅宜用于喂 LLM 的 grounding」** — 即承认这是 **刻意的成本/噪声 trade-off**，不是无损压缩。

---

#### 6. 结论


| 问题              | 答案                                                                                              |
| --------------- | ----------------------------------------------------------------------------------------------- |
| **是否潜在伤害召回？**   | **是**，对 **LLM grounding / 方案 A** 有硬上限；对 **Spotter 主路径** 无直接 cap                                 |
| **实测伤害多大？**     | 片段层：8 题 **1/8 neither**（c1）；**4/8** 类 case 在严格口径下 gate 有 gold 但 24 条未必有；sibling 对 24 条贡献 **0%** |
| **全栈为何仍高？**     | A9l 用 **Spotter ∥ LLM ∥ nominate**；c1 走 `spotted_not_in_snippets` 代偿                            |
| **若去掉 24 cap？** | LLM 支路 retrieved 可能 ↑，但 ~1668 块喂单次 LLM 不可行；更合理是 **闭包块优先排序 / MMR / 按 source_id 配额**，而非简单放大 cap   |


**一句话**：24 条 FIFO 截断 **确实潜在且实测存在地伤害「LLM 读摘要」这条召回支路**，尤其伤 **sibling 闭包里的 rare gold**；当前 A9l 靠 **非 LLM 通道代偿**，所以综合分仍高，但 **不能据此认为 24 条设计对闭包是「无害压缩」** — 它是 LLM 侧的已知漏斗损耗，c1 就是活证据。

---

### 14.6 问：这样来看，sibling的利用难题是否无法在纯RAG的框架下解决，只能后续借助GraphRAG等架构修改来完成

**答：**

**不完全是。** sibling 利用难，在当前实现里主要是 **RAG 流水线设计问题**（闭包扩了、排序和预算没给 sibling 留位），不是「纯 RAG 理论上做不到」。  
但 **c1 这类机制/专名鸿沟**，单靠「检索 + 同篇 sibling 扩展」确实不够，需要 **结构化入口或机制桥**——GraphRAG 是一种解法，不是唯一解法，也未必是成本最低的解法。

---

#### 1. 先把两个问题拆开


| 问题                                   | 本质                                          | 纯 RAG 能否解决                                                 |
| ------------------------------------ | ------------------------------------------- | ---------------------------------------------------------- |
| **A. sibling 扩了但进不了 24 条**           | 预算 + FIFO 排序；闭包 ~1600 块，24 槽被 top 检索 hit 占满 | **能**，改检索后处理即可，不必上 GraphRAG                                |
| **B. 入口文章根本没进 top-k**（c1）            | query 与 corpus 词面不一致；TF-IDF 摸不到 Pancoast 那篇 | **单靠 vector/BM25 RAG 很难**；要 anchor、别名、机制 query 或 **非检索通道** |
| **C. sibling 池噪声太大**（evaluation 块泛滥） | `chunk_type` 白名单几乎全过 → gate 池 ≈ 闭包          | **能**，改门控/按 section 重排；仍是 RAG 内工程                          |


实测里 **0/8 的 sibling 进 24 条**，说明的是 **当前 `_retrieve_snippets` 策略失效**，不是 RAG 范式失效。

---

#### 2. 纯 RAG 框架内仍可做的 sibling 利用（尚未做或做了一半）

项目里 **已有** 图式结构，只是没用好：

- `source_id` + `expand_ddx_siblings` = **篇内 star graph**（入口 hit → 同篇 differential/evaluation sibling）
- `syndrome_anchor` / `entry_type` = 结构化入口元数据
- `wiki_links` 合成块 = 显式 DDx 边

在 **不改成 GraphRAG** 的前提下，仍可：

1. **闭包优先配额**
  24 条里固定 N 槽（如 8）只给 `expand_ddx_siblings` 追加块，且优先 `chunk_type=differential` / 含 DDx 列表的 sibling，而不是 FIFO 先填满检索 hit。
2. **两阶段 RAG（仍是 RAG）**
  Stage1：query → 命中 entry；Stage2：**仅在 hit 的 `source_id` 内**再检索/过滤，取 differential 子块 → 再截断。比「全库闭包 1600 块 + 24 cap」精准得多。
3. **按篇聚合后再 cap**
  每个 `source_id` 合成 1 条「本篇 DDx 摘要」（规则或 LLM），24 条 ≈ 24 **篇** 而非 24 **随机块** — 仍是 RAG，只是 chunking/aggregation 层不同。
4. **闭包后 relevance 重排**
  对 sibling 用 query–chunk 分数或 MMR（文档已证伪 **spotter 池** 上的 MMR-trim，但 **LLM grounding 的 24 条** 尚未做 sibling-aware 重排）。
5. **收紧 gate**
  sibling 闭包时只保留 `differential` + `red_flag`，不要把全篇 `evaluation/diagnostic` 都放进 eligible 池 — 可直接把 effective 池从 ~1668 降到可管理的规模。

这些都不需要 GraphRAG；需要的是 **「先定位文章，再在文章内精取 DDx 块」**，而不是「全库闭包灌池 + 前 24 个」。

---

#### 3. 什么情况下才「纯 RAG 不够」、要 Graph / 机制层

与 sibling 利用 **不同** 的是 **§18 / §19 已坐实的 curated-free 天花板**：

- **entry+closure 上界 100%**（oracle 按 anchor 选入口）  
- **生产检索 curated-free ≈ 7/8**；c1 四路检索臂皆 `--`  
- c1 的 gap 是 **「右臂无力」↔「Pancoast/superior sulcus」无表层词重叠**，不是 sibling 排序能修的

这类 case 需要至少之一：


| 手段                                   | 是否 GraphRAG | 项目现状                     |
| ------------------------------------ | ----------- | ------------------------ |
| 机制/解剖 query 扩展（IMP-52 fanout）        | 否           | 部分验证，c1 仍漏               |
| `syndrome_anchor` / 锚点 UNION（D2）     | 轻量「图」       | 有，c1 仍漏（呈现词不匹配 anchor）   |
| **pathognomonic / nominate（IMP-58）** | 否，规则+标志物    | **A9l 已用**，c1 靠此 spotted |
| 别名/eponym crosswalk（IMP-59）          | 否           | 待完善                      |
| **GraphRAG / 知识图谱**                  | 是           | 未入主链                     |


所以：**「sibling 利用难」≠ 必须 GraphRAG**；**「入口选错 / 词面够不着」** 才更接近需要 graph、别名网或机制推理。

GraphRAG 的价值在于：显式 **Article → Section → Entity** 遍历、社区摘要、跨篇关系 — 适合 **L3 碎片化 + 入口分散 + 跨 chunk 推理**。但 IMP-31 的 `source_id` 闭包已经是 **最小版 article graph**；缺的是 **遍历策略与预算分配**，不是完全没有图。

---

#### 4. 和当前架构选择的对齐

```
纯 RAG（当前）          增强 RAG（仍非 GraphRAG）        GraphRAG / 混合
─────────────────────────────────────────────────────────────────
TF-IDF top-k      →   两阶段 + sibling 配额 + 篇级聚合
expand 闭包       →   闭包只取 differential + 重排
24 FIFO cap       →   grounding 专用 MMR / 闭包优先槽
spotter 主召回    →   nominate/pathognomonic 补 c1 类
recall_llm 读 24  →   方案 A 同限；与 spotter union 代偿
```

**A9l 的实际策略**已经是：**RAG 负责广度，非 RAG（nominate、cant_miss、resolver）补检索够不着的那一格** — 不是等 GraphRAG 才解决 sibling/c1，而是 **分层**。

文档结论也一致：瓶颈主因是 **Step 1–2 工程损耗**（检索排序 + spotting/LLM 抽取），不是「必须换 GraphRAG 范式」；GraphRAG 在 IMP 链里 **未入主路径**。

---

#### 5. 直接回答你的判断


| 说法                                     | 是否成立                                                       |
| -------------------------------------- | ---------------------------------------------------------- |
| sibling 在 **当前** 纯 RAG 流水线里 **几乎没被利用** | **成立**（实测 24 条中 sibling 0/8）                               |
| 因此 **只能** 靠 GraphRAG 才能解决              | **不成立** — 先在 RAG 内做 **篇内二阶段 + 闭包配额 + 门控收紧** 即可显著改善         |
| 有些 case（c1）**单靠 RAG+sibling 不够**       | **成立** — 需要机制桥/标志物/别名，GraphRAG 是选项之一，**nominate 已在用**      |
| GraphRAG 是 **合理的中长期方向**                | **成立** — 尤其跨篇 DDx、社区摘要、显式入口导航；但 **不是 sibling 24 槽问题的唯一出口** |


**一句话**：sibling 利用难，首先是 **「扩了但没排进预算」的 RAG 后处理问题**，纯 RAG 内仍可修；**curated-free 下摸不到入口文章** 才是更接近 Graph/机制层的问题，而项目已通过 **grounding + nominate 分流** 先绕开，而非等待 GraphRAG 替换整条链。若只改一处、成本最低：**给 sibling 留固定 grounding 槽 + 闭包只拉 `differential/red_flag`**，仍在现有 `GuidelineBranchSource` 框架内。

---

### 14.7 片段层后续改进路线图（交流归纳）

> 下列条目由 §14.4–§14.6 交流 **按优先级与成本** 归纳，供 IMP 排期与代码评审对照；**非** 已验证结论。

#### P0 — 低成本、改 `_retrieve_snippets` 即可


| 项                          | 做法                                                                                     | 预期收益                                | 风险/备注                            |
| -------------------------- | -------------------------------------------------------------------------------------- | ----------------------------------- | -------------------------------- |
| **sibling 固定 grounding 槽** | 24 条中预留 N 槽（如 **8**）只给 `expand_ddx_siblings` 块，优先 `chunk_type=differential` / 含 DDx 列表 | sibling 从 **0/8 → 可测**；LLM 可见同篇 DDx | Q1 检索 hit 仍占优先槽；需定 N 与 query 间分配 |
| **闭包类型收紧**                 | sibling 闭包时只拉 `differential` + `red_flag`，不灌全篇 `evaluation/diagnostic`                 | gate 池从 mean **~1668** 降规模；FIFO 噪声↓ | 可能漏非标准 section 的 gold；需回归 8+14 题 |
| **统一 token 阈值**            | `syn_toks` 与 gate `_tokens` 对齐（§14.2）                                                  | 象限/解剖 query 门控误拒↓                   | 改动面小，应单测 gate                    |


#### P1 — 中等工程量，仍在 RAG 范式内


| 项                  | 做法                                                                                | 预期收益                      | 关联                                      |
| ------------------ | --------------------------------------------------------------------------------- | ------------------------- | --------------------------------------- |
| **两阶段 RAG**        | Stage1：query → entry hit；Stage2：**仅在 `source_id` 内** 再检索/过滤 differential 子块 → cap | 替代「全库闭包 1600 块 + 24 FIFO」 | `source_id` 已有（IMP-31 最小 article graph） |
| **篇级聚合后再 cap**     | 每 `source_id` 合成 1 条「本篇 DDx 摘要」，24 条 ≈ **24 篇** 非 24 随机块                          | 长 DDx 列表分区损耗↓             | 规则聚合或轻量 LLM；成本待估                        |
| **grounding 专用重排** | 对 sibling 用 query–chunk 分或 MMR（**仅** LLM 24 条侧）                                   | gold 在 sibling 时进 LLM 上下文 | **≠** spotter 池 MMR-trim（已证伪有害，§6.7）    |


#### P2 — 中长期 / 跨篇


| 项                                        | 说明                                           | 项目现状                                |
| ---------------------------------------- | -------------------------------------------- | ----------------------------------- |
| **GraphRAG / 显式 Article→Section→Entity** | 跨篇 DDx、社区摘要、入口导航                             | 未入主链；`source_id` 闭包 = 最小 star graph |
| **IMP-59 别名 / eponym crosswalk**         | 解决 c1 类 **词面鸿沟**（Pancoast ↔ superior sulcus） | 待完善；A9l 靠 IMP-58 nominate 代偿        |
| **IMP-54 recall@k 尺子**                   | 全库 rare entity @k 曲线 + CI                    | 小 k 部署边界未全测（§6.25）                  |
| **结构化 DDx 离线预提取**                        | 绕过运行时 24×400 cap                             | §6.24 长期项；与在线 grounding 并行          |


#### 决策备忘（勿混读两类问题）

```text
问题 A（§14.6 问题 1–2）：sibling 扩了但没进 24 条
  → P0/P1 即可；不必等 GraphRAG

问题 B（§14.6 问题 3 / §3.4.6 c1）：入口文章 top-k 够不着
  → 别名、机制 query（IMP-52）、pathognomonic（IMP-58）、Graph/KG
  → A9l 已用「Spotter + nominate」分流，非单改 snippet cap 可解
```

**验收建议**（每改一项应报）：8 题 hard 的 **retrieved / strict gold@24 / sibling_in_24 / spotted** 四列 + 14 题 multilevel 的 **24/gate 池** 比例，避免只报 spotted 掩盖片段层回退。

---

### 14.8 问：branch-gen 主路径上 TF-IDF 与同义词弱项；除 MedCPT 外还有哪些缓解？

**答：**

**判断成立**：检索相似度与 Spotter 前的 chunk 匹配 **高度依赖词面重叠**；**同义词**（myeloid↔myelogenous）与 **机制/专名鸿沟**（Pancoast↔superior sulcus、呈现↔病名）须分开治——后者 MedCPT hybrid 也补不全 c1（四路检索臂皆漏，A9l 靠 nominate）。

#### 同义词敏感落在哪几层


| 层级                  | 机制                              | 同义词敏感度                |
| ------------------- | ------------------------------- | --------------------- |
| Query → chunk       | TF-IDF cosine                   | **高**                 |
| chunk → 病名 spotting | SNOMED disorder 词典 n-gram       | **中**（正文须出现该写法）       |
| 候选 → gold 评测        | token 子集 + `GOLD_FAMILY_TOKENS` | **低**                 |
| 机制/专名               | 非同义词问题                          | 需 nominate / resolver |


#### 已落地缓解（非 MedCPT）

**检索侧（仍 TF-IDF）**：多 query（2–4 条）、`_colloquial()`、GARMLE-G① context query、`expand_ddx_siblings`、Anchor UNION（D2，已退出主路径）。

**抽取/候选侧（绕过检索）**：SNOMED spotting 同义词表、`DiseaseNameResolver`（alias / mechanism_map）、IMP-58 nominate + pathognomonic、IMP-60/56 cant_miss、Spotter+LLM union（A9l）。

**外围知识层**：LR `_DISEASE_SYNONYM_PAIRS`、`DxFeatureRetriever.expand_synonyms` — **不进** `GuidelineBranchSource.recall()` 热路径。

#### 待落地 / P2


| ID                | 措施                            | 说明                                         |
| ----------------- | ----------------------------- | ------------------------------------------ |
| **IMP-59**        | `syndrome_alias_map.json`     | 综合征 hand label ↔ corpus anchor；**仓库尚无此文件** |
| **IMP-51**        | `syndrome_entry` boost        | 结构化入口加权                                    |
| **索引期 alias 注入**  | 建库时 SNOMED/UMLS 别名写入 chunk 文本 | 零运行时成本                                     |
| **L12**           | cross-encoder 重排              | P2                                         |
| **HyDE / SPLADE** | 语义/query 扩展                   | P2，HyDE 仅低置信兜底                             |


#### 实测补多少


| 配置                    | 8 题 B6 retrieved | 8 题 spotted                             |
| --------------------- | ---------------- | --------------------------------------- |
| A1 TF-IDF             | 7/8              | 6/8                                     |
| A9l（+ nominate + LLM） | 7/8              | **8/8**（c1 = `spotted_not_in_snippets`） |
| A10 hybrid            | 7/8              | 7/8（xloss 1→0）                          |


**生产推荐栈**：TF-IDF + MedCPT RRF + grounding + nominate；**下一步低成本增量**：IMP-59 小表 crosswalk + **索引期 synonym 注入**，而非泛化 query fanout。

---

### 14.9 问：检索阶段对同义词也发 query，能否解决当前瓶颈（14+8 题）？

**答：**

**不能作为主解。** 2026-06-27 脚本：在 baseline 2–4 条 query 上，每综合征追加 ≤4 个 SNOMED/手工 alias，每条再发 `differential diagnosis of …` / `causes and etiology of …`。

#### 8 题难病（gold@24 snippets）


| 指标      | baseline | +同义词 query |
| ------- | -------- | ---------- |
| 命中      | **7/8**  | **7/8**    |
| 新增 flip | —        | **0**      |
| c1      | ✗        | ✗          |


即使用 `pancoast syndrome`、`brachial plexopathy` 等仍漏 c1。

**c1 corpus 探针**：全库仅 **1** chunk 含 `pancoast`/`superior sulcus`；query `differential diagnosis of pancoast syndrome` 的 TF-IDF top-30 **仍无** 该块（多为 WikEM 泛 DDx 页）。**context query** 闭包池可摸到 1 块，但受 **24 条 FIFO** 约束（§14.4–§14.5）。

#### 14 题常见（`recall()` L1 target）


| 指标        | baseline  | +同义词 query  |
| --------- | --------- | ----------- |
| L1 target | **12/14** | **10/14** ↓ |


回退 **acute_pancreatitis**、**acute_kidney_injury** — 泛化 synonym 稀释 40 槽，机制同 **IMP-52 fanout 证伪**（A6 0.693 < A1 0.702）。

#### 22 题瓶颈对照


| 瓶颈类型                    | 同义词 query                     |
| ----------------------- | ----------------------------- |
| 词面同义词（14 题已 largely OK） | 实测 **+0** flip，14 题 **-2** 风险 |
| 机制/呈现 ↔ 病名（c1）          | **无效**                        |
| 24/40 槽截断               | 多发 query **放大池子**，更易被截断       |


**结论**：同义词能力应落在 **IMP-59 有针对性的综合征别名** + **MedCPT/nominate**，而非再叠一轮泛化 query。

---

### 14.10 问：检索直接换成纯 dense（MedCPT）排序，是否有机会提升命中？

**答：**

**有机会，但边际有限；纯替换不如已验证的 sparse+dense 并联（A10）。**

#### 快测对照（`cpg_index` + grounding，无 nominate）


| 方案                 | 8 题 gold@24 | 14 题 L1tgt（recall 候选）                               |
| ------------------ | ----------- | --------------------------------------------------- |
| TF-IDF sparse      | 7/8         | 12/14                                               |
| **纯 MedCPT dense** | 7/8         | 12/14                                               |
| Hybrid RRF         | 7/8         | 11/14（快测；官方 A10 composite **0.719** > A1 **0.702**） |


#### c1 排序例证（带 context 的 query）


| 检索器                   | 含 Pancoast 块在 top-30 排名 |
| --------------------- | ----------------------- |
| TF-IDF                | **第 15**                |
| MedCPT dense / Hybrid | **第 1**                 |


dense **能**抬语义相关块，但完整 `_retrieve_snippets` 后 c1 仍 **retrieved=False**（§14.5）；**8 题漏斗 retrieved 7→8 基本无望**。

#### 官方矩阵（A10 vs A1）


| 指标                   | A1        | A10 hybrid |
| -------------------- | --------- | ---------- |
| composite（14 题）      | 0.702     | **0.719**  |
| L1tgt                | **0.857** | 0.786 ↓    |
| 8 题 funnel retrieved | 7/8       | 7/8        |
| xloss                | 1         | **0**      |


**IMP-53 设计**：MedCPT **不替换** TF-IDF，而是 **第二塔 RRF**；sparse 保留精确词面，dense 补 B2 语义缝。

**结论**：纯 dense **值得作第二塔，不值得全替 TF-IDF**；命中提升主要在 **轴/L2/mandatory 等综合指标**，不在 8 题 retrieved 天花板；须配合 **context 权重、grounding 配额、nominate**（§14.7 P0）。

---

### 14.11 问：病名排序是否存在「频次≠重要度」的误导风险？有何对策？

**答：**

**存在；文档定性为核心缺陷 C4。** Spotter 对 snippet 内 n-gram 命中 **累加** `scored[dz] += w`，再 `sorted[:max_candidates=40]` — 代码注释写明 `**frequency dominates ties`**。CPG 中 MI、urticaria、hypertension 等在无关 DDx 列表里 **高频出现**，8 题漏斗 top_cands 常与之无关。

#### 风险机制


| 维度      | 当前近似        | 临床期望               |
| ------- | ----------- | ------------------ |
| 信号      | 块内 **出现次数** | 轴极、can't-miss、情境先验 |
| 常见病     | 多块累加 → 分数高  | 对该综合征未必首要          |
| 罕见 gold | 1–2 次 → 分数低 | 可能是关键鉴别            |


#### 已有对冲（多层，未根除频次主导）


| 层     | 措施                                                                     | 状态     |
| ----- | ---------------------------------------------------------------------- | ------ |
| 减噪    | `_GENERIC_NAMES`；grounding 闭包不进 Spotter 池（IMP-63）                      | ✅      |
| 族层竞争  | IMP-64 rollup（~K/8 席位留给 flat top-K 漏掉的族）                               | ✅      |
| 重要度下界 | IMP-60 cant_miss 轴极注入；IMP-56 hard 层；IMP-58 nominate                    | ✅ / 部分 |
| 第二通道  | recall_llm（LLM 顺序非频次）；Spotter+LLM union                                | ✅      |
| 下游兜底  | `mandatory_coverage` + `_enforce_mandatory_branches`；UnionAxisMap MECE | ✅ 生产   |


#### 实测


| 现象                | 说明                                                     |
| ----------------- | ------------------------------------------------------ |
| C4 仍为 spotting 瓶颈 | c13/c18：gold 在片段与 vocab，仍被噪声挤出 40 槽（grounding+LLM 后缓解） |
| grounding vs 灌池   | mandatory **0.54→0.74**（A0→A1）                         |
| cant_miss 轴极      | 14 题矩阵 **几乎无增益**（表按 WikEM 症状 id，与 lab 综合征不对齐，§2.7）     |


#### 尚未做

- recall 内 **无 LR/urgency 先验重权**；**无单实体频次 cap / IDF downweight**
- **GraphRAG  alone 不解决** — 除非边带 `must_not_miss` / `axis_pole` 属性（等于把 cant_miss 写进图）

#### 与 GraphRAG 讨论的关系（§14.6）

频次误导是 **排序函数问题**，不是「缺图」；GraphRAG 若节点权重仍按共现计数，**C4 依旧**。根因级改法：**族层竞争 + 临床优先级边/硬约束 + 单实体计分上限** — 其中多条 **已在 IMP-56/60/64 以非 Graph 形式部分落地**。

**下一步优先级**（与 §14.7 一致）：**单实体频次 cap / 族内 representative 只计一次** + **扩展 cant_miss 至 14 题综合征** + **L12 相关性重排**；而非再加 query 或指望架构一键替换。

---

### 14.12 问：「族」「保留名额」「直提名」在代码里分别指什么？

**答：** 完整规格已入主文 **§2.9**（IMP-64 / IMP-58 实现消歧）；**§6.10 / §6.12** 各附要点。此处仅归纳易混处。

#### IMP-64「族」≠ L1 mandatory 域

- **族** = Spotter 后全量候选上，SNOMED `is_a` 筛出的 **超族**（2–70% 覆盖，最多 6 组），如 myeloid neoplasm 类概念名。
- **保留名额** = flat top-40 中 **该超族零成员** 时，从 40 名外取 **1 名具体病** 占 **最多 5/40 槽**；**不**新增「族名」key，**不**在 ≤40 候选时运行。

#### IMP-58「直提名」≠ 绕过 recall

- **直提名** = curated 子串表命中 → 把 **具体病名** 写入 `scored`（≥0.6×max spot 分）；仅 **绕过 RAG/Spotter 频次**，仍受 top-40 与 `cant_miss_hard` 约束。
- **两条消费链**：实验 `recall()` **flat 40 名**（A7/A9l 评测）；生产 `controller` **T1 marker → 按 L1 域分桶**（不调用 `recall(nominate=True)`）。

#### 对照（一句话）


| 机制              | 改什么                            | 作用在谁                                 |
| --------------- | ------------------------------ | ------------------------------------ |
| IMP-64 rollup   | **换** top-40 末尾 1–5 个 **具体病名** | `GuidelineBranchSource.recall()` 返回值 |
| IMP-58 nominate | **新增/抬高** 具体病名分数               | 同上 + 生产 branch_knowledge **按域** 实体列表 |


---

