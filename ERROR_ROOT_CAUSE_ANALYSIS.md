# 错误根因分析报告：medbullets_hard 诊断流水线

> 版本 v2.0（细化叙述版）·2026-06-04
> 数据集 `medbullets_hard_test.tsv` 诊断类去重子集 25 题 · 模型 `qwen/qwen3-32b`（单骨干）
> 配置：知识注入 ON · 并发 10 · 协议鲁棒层 ON
> 证据来源：逐题重建轨迹 `logs/anatomy/case_<idx>.json`；脚本 `scripts/reconstruct_case_traces.py`、`summarize_case_trace.py`、`view_evidence_talp.py`

---

## 如何阅读本报告

报告分五部分，从"个案"到"共性"再到"对策"：

1. **第一部分 · 六道纯文本错题的逐题解剖**——把每道错题写成一个"病例走查"：题目说了什么 → 临床上正确的推理路径 → 本流水线实际怎么一步步走的 → 究竟在哪个环节、为什么走错 → 错误归类。这是判断"算法到底错在哪"最直接的材料。
2. **第二部分 · 从个案到共性**——把第一部分暴露的问题归纳为 5 个横切架构缺陷，每个都给出：通俗解释、由哪些个案佐证、对应代码位置。
3. **第三部分 · 图像题为何不计入**——区分"算法缺陷"与"模态缺失"。
4. **第四部分 · 文献调研**——临床医学与多智能体编排两条线，找到与本系统缺陷对位的成熟缓解方法。
5. **第五部分 · 落地路线**——把缓解方法映射到本系统具体组件（F1–F6），并说明 UMLS/SNOMED 知识扩充与 GPU 检索加速的落点。

> **一句话结论**：本轮错误的主因**不是"知识库里没有相应知识"**，而是**"知识没有被送到做概率打分的那个环节，打分本身缺乏方向校验与数值依据，最终的选项映射又不忠实于树里算出的概率，再叠加几类经典的诊断认知偏差"**。

---

## 第一部分 · 六道纯文本错题的逐题解剖

> 本轮 25 题中 16 题依赖图像（见第三部分），真正能反映纯文本算法能力的是 9 道无图像题，其中 6 道答错。下面逐一走查。每题给出**「金标 / 误选」**与**「出错环节」**。

### 案例 9 · 类白血病反应被误判为 CML 【金标 D / 误选 C ·出错环节：EvidenceAnnotator】

**题目**：59 岁男性，近期患过一次"感冒"误工一周，随后乏力、体重下降、腹痛；白细胞升高，**白细胞碱性磷酸酶（LAP）升高**。选项含 CML、慢淋、急淋、多发性骨髓瘤、**类白血病反应**。

**临床上应当如何推理**：白细胞显著升高时，最经典的鉴别就是"肿瘤性（CML）"还是"反应性（类白血病反应）"。**决定性判别点是 LAP**：CML 中 LAP **显著降低**（评分 0–16），类白血病反应中 LAP **显著升高**（评分 100–220）。本例近期有感染、且 LAP 升高 → 强烈指向类白血病反应。

**流水线实际怎么走的**：
- RootSelector 把根标签写成「…with Elevated Leukocyte Count **and Leukocyte Alkaline Phosphatase**…」——**说明系统读到了 LAP 升高这一关键事实**。
- BranchCreator 正确地同时建立了「慢性骨髓增殖性肿瘤(CML 家族)」和「反应性/非恶性白细胞增多」两个家族——**鉴别诊断的盘面是对的**。
- TALP（动作规划）甚至在候选动作的 `why` 字段里写对了方向：*"Elevated LAP is **inconsistent with CML** but **supports reactive** processes"*，并把目标分支标注为 `{CML: against, 反应性: support}`。**到这一步，系统的判别方向完全正确。**
- 然而 **EvidenceAnnotator（证据→概率打分环节）独立重判，把方向判反了**：其 `result_summary` 写「Elevated LAP … **support chronic myeloid leukemia** as a likely diagnosis」，`branch_effects` 给 CML 分支打了 `moderate_for`（中等支持）。
- 这一反向打分把概率灌向 CML，最终 AnswerMapper 选 C（CML）。

**为什么错**：拥有概率更新权的 EvidenceAnnotator 在**没有任何外部 LR 知识约束**的情况下，凭 LLM 自由判断，把"LAP 升高"这一**应当排除 CML** 的证据判成了**支持 CML**。同一道题里 TALP 明明判对，但 TALP 只决定"问什么/查什么"，并不决定概率；概率由 EvidenceAnnotator 说了算，于是判反者胜出。

**归类**：①LR 方向错误（核心）；②知识缺口（`lr_cache` 里"alkaline phosphatase"只有血清 ALP→胆囊炎/肝病，**没有 LAP↔CML/类白血病** 这条）；③架构缺陷（知识未注入打分环节，详见第二部分缺陷 A/B）。

---

### 案例 17 · CML 被误判为 AML 【金标 D / 误选 B ·出错环节：RootSelector → SubBranchCreator → AnswerMapper】

**题目**：57 岁男性，数日乏力、盗汗，今日**头痛 + 视物模糊**（视力 20/100），体重下降，查体偏瘦。选项含急淋、**AML**、慢淋、**CML**、多发性骨髓瘤。

**临床上应当如何推理**：盗汗 + 体重下降 + 慢性病程 + **头痛/视物模糊** 高度提示 CML 伴**白细胞淤滞（leukostasis）**——CML 白细胞可极高（>100×10⁹/L），高黏滞导致视网膜/中枢症状。慢性病程、嗜碱粒细胞增多、脾大、BCR-ABL 是 CML 的判别要点。

**流水线实际怎么走的**：
- RootSelector 把根标签写成「…Pancytopenia with **Blast Leukocytosis**…」——**把"白细胞淤滞/高计数"误读成了"原始细胞(blast)增多"**。这是关键的第一步误读。
- 受此框定，SubBranchCreator 在"髓系肿瘤伴原始细胞增多"家族下展开为「**De Novo AML**」「CML 急变期」「MDS」。
- AnswerMapper 选了后验最高的叶「De Novo AML」（posterior=**0.627**）→ 选项 B。最终选项分布 `B=0.627`，CML(D)≈0.005，几乎被清零。

**为什么错**：错误在最上游——RootSelector 把慢性 leukostasis 误框为"急性原始细胞增多"，把题目从"CML vs 反应性"偷换成了"AML vs CML 急变"，于是急性方向（AML）顺理成章地胜出。这是**特征误读驱动的锚定**，并叠加 CML/AML 的**亚型-分期混淆**（即此前讨论过的"phase-crossing"缺陷）。CML 的慢性判别证据未被决定性使用。

**归类**：认知偏差（特征锚定）+ 亚型/分期混淆；错误源头在 RootSelector 的事实框定。

---

### 案例 13 · 胰高血糖素瘤被误判为胰岛素抵抗 【金标 A / 误选 E ·出错环节：VignetteParser / EvidenceAnnotator】

**题目**：55 岁男性，肥胖、吸烟，乏力、腹痛、腹泻，**痛性红斑伴丘疹和斑块**（面、躯干、四肢），高血糖。选项含**α 细胞瘤（胰高血糖素瘤）**、β 细胞破坏、β 细胞瘤、皮质醇增多、**胰岛素抵抗**。

**临床上应当如何推理**：**痛性、游走性的红斑/丘疹/斑块 = 坏死松解性游走性红斑（NME）**，是胰高血糖素瘤（α 细胞瘤）的**特征性（pathognomonic）皮疹**；配合高血糖、体重下降、腹泻，几乎可锁定。

**流水线实际怎么走的**：
- RootSelector 把皮疹描述成「**Uncharacterised** Painful Erythema」——**系统没能把"痛性丘疹斑块"识别/命名为 NME**。
- 难得的是，BranchCreator/SubBranchCreator 仍然建立了「副肿瘤性内分泌障碍」家族，并展开出子分支「**Paraneoplastic Endocrinopathy with Glucagonoma**」——**正确答案其实出现在了树里**。
- 但由于关键的"皮疹=NME=胰高血糖素瘤"这条链没有被连上，胰高血糖素瘤分支始终**得不到支持证据而被饿死**；EvidenceAnnotator/TALP 反而锚定"肥胖+高血糖"，把质量给了「2 型糖尿病/胰岛素抵抗」叶（posterior=0.586）。
- AnswerMapper 最终 `E=0.96`，A（胰高血糖素瘤）≈0。

**为什么错**：特征性体征（NME）**未被识别与命名**，导致最有判别力的证据无法注入到对应分支；正确分支虽建立却"无米下锅"。这既是**病征识别的知识缺口**（`pathognomonic_markers.json` 无 NME↔glucagonoma），也是**体征归一化能力不足**（题面是描述性表述，而非"NME"这个词）。

**归类**：知识缺失（病征未识别）+ 体征规范化缺口。

---

### 案例 18 · 肝腺瘤破裂被误判为异位妊娠 【金标 E / 误选 A ·出错环节：BranchCreator / AnswerMapper】

**题目**：23 岁女性，口服避孕药（OCP）+ 合成代谢类固醇（备赛健身）、酗酒、近期大量减重，运动中突发剧烈腹痛。选项含**异位妊娠**、胰腺炎、肝静脉阻塞（Budd-Chiari）、胆总管结石、**肝内血管扩张（肝腺瘤）**。

**临床上应当如何推理**：**OCP + 合成代谢类固醇** 是**肝细胞腺瘤**的典型诱因，腺瘤富含血窦/血管扩张（peliosis），运动中可破裂致腹腔出血——对应"肝内血管扩张"。

**流水线实际怎么走的**：
- 系统锚定"23 岁女性 + 突发腹痛"→生成「Acute PID」「异位妊娠」等盆腔/妇科方向。
- 荒谬的是，SubBranchCreator 产出了一个**自相矛盾的叶**：「Ruptured **Ectopic Pregnancy** in **Non-Pregnant** Pelvis」（"非妊娠盆腔里的异位妊娠破裂"）——逻辑上不可能，本应概率≈0，却拿到 posterior=**0.4268**，成为头名 → 选 A。
- 「OCP/类固醇→肝腺瘤→血管扩张」这条链从未被连上；本题只跑了 3 个回合就早停。

**为什么错**：**人群刻板锚定**（年轻女性腹痛→异位妊娠）压倒了关键暴露史（OCP+类固醇）；系统缺乏**一致性自检**来把"非妊娠的异位妊娠"这种自相矛盾假设置零；且**过早闭合**（3 回合即止）未给肝腺瘤链路浮现的机会。

**归类**：认知偏差（人群锚定 + 过早闭合）+ 逻辑一致性缺陷。

---

### 案例 22 · 原发性甲旁亢被误判为恶性肿瘤 【金标 C / 误选 D ·出错环节：TALP / 终止与提交流程】

**题目**：45 岁非裔女性，咳嗽一周、腹痛、注意力不集中、体重下降，**高钙血症**。选项含抗酸剂过用、1,25-双羟维生素 D 升高（提示结节病）、**PTH 升高（原发性甲旁亢）**、恶性肿瘤、病毒感染。

**临床上应当如何推理**：高钙血症的鉴别核心是一项检查——**血清 PTH**：PTH 升高 → 原发性甲旁亢；PTH 被抑制 → 恶性肿瘤（PTHrP）或其他。必须把 PTH 这个**决定性检查**驱动到出结果，鉴别才能收敛。

**流水线实际怎么走的**：
- BranchCreator 盘面正确：同时有「恶性高钙」和「原发性甲旁亢/维生素 D」家族。
- 但整个过程中，**血清 PTH 这个唯一决定性判别点始终没有被驱动到分辨**——后验全程极度平坦（最终所有叶的最大值仅 **0.118**，分布近乎均匀）。
- 回合预算耗尽后仍未收敛，AnswerMapper 退而按"消瘦 + 高钙 → 恶性肿瘤"的先验锚点提交，选 D（最高 0.118）。

**为什么错**：这是**信息增益未收敛即提交**的典型——TALP 没有把"查 PTH"这一决定性、低成本动作排到最优先，导致没有任何分支能拉开差距；在近乎平局时，提交逻辑落到了先验最重的"恶性"锚点上。

**归类**：流程缺陷（决定性判别未优先、未收敛即提交）。

---

### 案例 23 · 粘连性肠梗阻被误判为肠神经损伤 【金标 A / 误选 B ·出错环节：SubBranchCreator + AnswerMapper】

**题目**：55 岁男性，恶心呕吐一周加重，进食油腻/饮酒加重，**控制差的糖尿病**、便秘、高血压等。选项含**粘连**、肠神经系统损伤（糖尿病胃轻瘫）、粪便嵌塞、诺如病毒、肠扭转。

**临床上应当如何推理**：呕吐 + 梗阻样表现，机械性梗阻（粘连最常见）需重点考虑；糖尿病胃轻瘫是干扰项。

**流水线实际怎么走的**：
- 系统**强烈锚定"控制差的糖尿病"**，于是 SubBranchCreator 把「糖尿病胃轻瘫」家族**反复过度扩张**——日志里出现 4 组几乎重复的"Diabetic Gastroparesis with…"子分支，挤占了其他家族的概率质量（确认偏误 + 扩张失控）。
- AnswerMapper 自述：*"Leading leaf branch: Neurological GI Motor Dysfunction (posterior=0.375)…**尽管 B3.1（15.56%）是叶节点，更高的后验对齐到容器分支 B3**"*——**它把答案映射到了非叶的"家族/容器"节点**，而不是具体叶。
- 更矛盾的是，其输出的选项映射里 **E（肠扭转）=0.49 才是最高**，B=0.35，但 `final_answer` 却给了 B——**AnswerMapper 连自己映射的 argmax 都没遵守**。
- 结果选 B，金标 A（粘连）仅 0.08。

**为什么错**：三重叠加——①糖尿病**确认偏误**导致单一家族**过度扩张**；②AnswerMapper**在家族容器层而非叶层做映射**；③AnswerMapper 的 `final_answer` 与其自身选项概率分布**自相矛盾**。

**归类**：认知偏差（确认偏误 + 扩张失控）+ 聚合/映射缺陷 + 自洽性缺陷。

---

### 六题小结

| idx | 金标/误选 | 出错环节 | 主因归类 |
|---|---|---|---|
| 9 | D / C | EvidenceAnnotator | LR 方向错 + 知识缺口 + 架构（知识未注入打分） |
| 17 | D / B | RootSelector→SubBranch→AnswerMapper | 特征误读锚定 + 亚型/分期混淆 |
| 13 | A / E | VignetteParser/EvidenceAnnotator | 病征(NME)未识别 + 体征规范化缺口 |
| 18 | E / A | BranchCreator/AnswerMapper | 人群锚定 + 过早闭合 + 逻辑自检缺失 |
| 22 | C / D | TALP/提交流程 | 决定性判别未优先、未收敛即提交 |
| 23 | A / B | SubBranchCreator+AnswerMapper | 确认偏误+扩张失控 + 容器层映射 + 自洽性缺陷 |

---

## 第二部分 · 从个案到共性：五个横切架构缺陷

> 把上面的个案归纳为可定位、可修复的系统性问题。每条给出：通俗解释 → 佐证个案 → 代码位置。

### 缺陷 A（最高优先）· 外部知识只接到了"规划"，没接到"打分"

- **通俗解释**：系统把判别提示/LR 知识注入到了 **TALP（决定"问什么、查什么"）**，却**完全没有**注入到 **EvidenceAnnotator（决定"这条证据让各分支概率怎么变"）**。于是最终决定胜负的概率打分，是在**没有外部知识兜底**的情况下凭 LLM 自由判断。
- **代码位置**：注入仅在 `controller.py:725-742`（注释明写 "Knowledge injection: add discriminator_hints for **TALP**"）；而 `_build_annotator_payload`（`controller.py:1010`）给 EvidenceAnnotator 的输入里**没有任何 LR/判别/病征知识**。
- **佐证**：case 9（注入缺位直接导致方向判反无人纠正）。

### 缺陷 B · 概率更新是"定性档位"，不是"数值 LR"，且无方向校验

- **通俗解释**：EvidenceAnnotator 的输出是 `moderate_for / weak_against / neutral` 这样的**定性方向档**（再由 `ordinal_update` 等折算成后验），**并不是检索到的数值 `lr_positive`**。也就是说，所谓"打开了 LR 注入"在更新环节其实**名存实亡**；而且没有任何机制在"已知强判别点"上对 LLM 给出的方向符号做校验。
- **代码位置**：`controller.py:405-415`（`annotate_evidence_bundle`→`choose_update_method`→`apply_probability_update`）、`1190-1207`（`ordinal/rule_based/calculator_update` 三选一，默认走定性的 ordinal）。
- **佐证**：case 9（方向被判反却畅通无阻）。
- **循证锚点**：LAP 在 CML 显著降低、在类白血病反应显著升高，是经典判别点（[JPMA 研究](https://archive.jpma.org.pk/PdfDownload/6268)；[Alberta 临床血液学指南](https://pressbooks.openeducationalberta.ca/mlsci/chapter/chronic-myelogenous-leukemia-cml/) 明列 "CML: LAP Low / Leukemoid: LAP High"）。

### 缺陷 C · AnswerMapper 不忠实于树里算出的后验

- **通俗解释**：最后一步把"分支后验"翻译成"选项概率"时，AnswerMapper 会用自己的一轮 LLM 判断**重新分配**，常常偏离甚至覆盖前面辛苦算出的叶后验，并表现出三种亚型：
  - **概率虚高/过度自信**：case 9 叶后验 CML 仅 0.223，选项却给 C=0.82；case 13 叶 0.586 → 选项 E=0.96。
  - **映射到容器而非叶**：case 23 自述映射到家族节点 B3（0.375）而非叶。
  - **自相矛盾**：case 23 选项映射 E=0.49 最高，`final_answer` 却选 B。
- **代码位置**：`final_aggregate`（AnswerMapper 调用处）及其 prompt。
- **佐证**：case 9、13、23。

### 缺陷 D · 关键判别未分辨即在预算耗尽时提交

- **通俗解释**：当一项**决定性检查**（如血清 PTH）没有被优先安排、never 驱动到出结果时，没有分支能拉开差距，后验近乎平局；系统不会因"未收敛"而拒绝提交，反而在回合用尽时落到先验最重的锚点上。
- **代码位置**：TerminationJudge、TALP 评分排序、AnswerMapper 的兜底逻辑。
- **佐证**：case 22（最大后验仅 0.118 仍提交）、case 18（3 回合早停）。

### 缺陷 E · 经典诊断认知偏差

- **通俗解释**：系统重现了人类诊断的几类经典偏差：
  - **锚定/特征误读**：case 17 把 leukostasis 框成 "blast"；case 18 年轻女性→异位妊娠。
  - **确认偏误 + 扩张失控**：case 23 围绕"糖尿病"反复扩张同一家族。
  - **逻辑自检缺失**：case 18 接受"非妊娠的异位妊娠"这种自相矛盾假设。
- **代码位置**：RootSelector（事实框定）、SubBranchCreator（扩张去冗余/限额）、缺一个一致性/挑战环节。
- **佐证**：case 17、18、23。

---

## 第三部分 · 图像题为何不计入算法评估

25 题中 16 题题干依赖图像（Figure / ECG / 病理照片）。纯文本流水线**看不到图像**，这类错误属于**模态缺失**而非算法缺陷，无法靠"改编排/补知识"修复（个别蒙对者如 case 2/10 是靠文字线索的运气）。因此对外汇报与内部评估都应**始终区分两种口径**（全量 vs 无图像）。本报告的根因解剖只针对 9 道无图像题中的 6 道错题。

---

## 第四部分 · 文献调研：与本系统缺陷对位的缓解方法

> 两条线：①临床诊断认知偏差缓解；②医学多智能体系统/编排的知识接地、对抗验证、概率校准。下面按"对应哪个缺陷"组织。

### 4.1 缓解认知偏差（对应缺陷 E）

- **角色化多智能体辩论**（JMIR 2024, [e59439](https://www.jmir.org/2024/1/e59439/)）：显式设"魔鬼代言人(devil's advocate)"纠正锚定/确认偏误、"主持人"缓解过早闭合、"专科专家"补域知识，在 16 例由偏差导致误诊的案例中**纠正 81%**。
- **DxChain / "Thinking Like a Clinician"**（[arXiv:2604.23605](https://arxiv.org/html/2604.23605)）：指出线性 CoT 易"过早闭合/过早剪枝"（如因体重偏见把胸痛误判为代谢病，准确率掉 **32%**——与本系统 case 23 糖尿病锚定、case 18 人群锚定同型），提出**选择性触发的"Angel-Devil"辩证验证**，在出最终诊断前淘汰弱假设、仲裁证据冲突。
- **MAI-DxO / SDBench**（[arXiv:2506.22405](https://fugumt.com/fugumt/paper_check/2506.22405v2_enmode)）：角色化辩论 + 偏差检查 + 检查节制，NEJM-CPC 准确率提至 **80–86%** 且降成本。
- **诊断纠错安全网基准**（medRxiv 2026, [26346832](https://www.medrxiv.org/content/10.64898/2026.02.22.26346832v1.full-text)）：LLM 有**附和基线**的确认偏误，安全集成需"以怀疑优先"的对抗式工作流。

### 4.2 知识接地，让"打分"有据可依（对应缺陷 A、B）

- **KERAP**（[PMC12919460](https://pmc.ncbi.nlm.nih.gov/articles/PMC12919460/)）：检索智能体把知识图谱知识**显式拆成正向（"症状 X 提示疾病 Y"→纳入）与负向（"症状 X 排除疾病 Z"→排除）**两类注入推理。**这正是 case 9 缺的那一块**——"LAP 升高排除 CML"属于**负向/排除知识**，应作为方向约束注入到打分环节。
- **MedAgent-Pro**（[arXiv:2503.18968](https://arxiv.org/html/2503.18968v1)）：分层 = 任务级 planner（用检索到的临床标准生成诊断计划）+ 案例级 tool agents（处理量化/定性指标）+ decider；其 RAG agent 确保推理基于**检索到的证据而非无支撑的 LLM 生成**。
- **MedMMV**（[arXiv:2509.24314](https://arxiv.org/html/2509.24314)）：每条推理路径在 **Hallucination Detector** 监督下**将每一步接地到证据图**，阻止局部错误级联——可直接用于拦截 case 9 式"方向幻觉"。

### 4.3 概率校准，治"过度自信"与"早承诺"（对应缺陷 C、D）

- **MedMMV** 的 **Combined Uncertainty Scorer**：多路径并行 + 不确定度感知选择，替代"早早锁定单条路径"。
- **Bayesian Elicitation with LLMs**（[arXiv:2604.01896](https://arxiv.org/html/2604.01896v1)）：实测 LLM **系统性过度自信**（名义 95% 区间实际覆盖仅 9–44%），**归一化 conformal 校准**可纠偏——正对应 AnswerMapper 给出的 0.82/0.96 虚高。该文亦提醒：**外部检索对本就较准的强模型可能反而干扰其内部先验**——故知识注入须带置信门控、可观测。

### 4.4 检索接地与对抗验证必须"合二为一"（对应缺陷 A+E 的协同）

- **BLUEmed**（[arXiv:2604.10389](https://arxiv.org/html/2604.10389v1)）：单源 RAG 会把知识库偏差**直接传播**到结论（缺独立核验）；而无检索的纯辩论又**过度报错**。结论是**检索接地 + 对抗验证必须统一**。本系统恰好两头都缺——打分环节既无检索接地，也无独立核验。

---

## 第五部分 · 落地路线（映射到本系统组件）

> 原则：不推翻树状编排，把"知识接地 + 方向约束 + 独立核验 + 概率校准"补到正确的环节。按影响面排序。

| # | 修哪个缺陷 | 落地动作 | 涉及组件 | 文献依据 |
|---|---|---|---|---|
| **F1** | A、B | 把判别提示/LR **注入 EvidenceAnnotator**；对 KB 高置信命中的强判别点做**方向硬约束**（KB 给方向时覆盖 LLM 的 `branch_effects` 符号） | `_build_annotator_payload`、`apply_probability_update` | KERAP 正/负知识、MedMMV 幻觉检测 |
| **F2** | B | 把 `lr_cache`/`diagnostic_markers` 的**数值 LR 接入 `calculator_update`**，以贝叶斯 LR 更新替代纯定性档；KB 未覆盖时回退定性档 | `calculator_router`、`lr_retriever` | MedAgent-Pro 证据驱动 |
| **F3** | C | AnswerMapper **强制叶级映射**、选项概率**直接继承叶后验**而非二次自由判断；对自相矛盾叶（如"非妊娠异位妊娠"）做一致性置零；强制 `final_answer = argmax(选项映射)` | `final_aggregate` / AnswerMapper prompt | BLUEmed 独立核验 |
| **F4** | C、D | 引入**不确定度门控**：关键判别未分辨（后验过平/最大值<阈值）时**不得提交**，优先安排决定性检查；对最终选项概率做 conformal/温度校准 | TerminationJudge、TALP 评分、AnswerMapper | MedMMV CU Scorer、Bayesian Elicitation |
| **F5** | E | **选择性触发的"魔鬼代言人/Angel-Devil"复核**：仅在 top-2 接近或检测到锚定（如单家族过度扩张）时触发；SubBranchCreator 扩张**去冗余/限额** | SubBranchCreator、新增 challenger 触发器 | JMIR e59439、DxChain、MAI-DxO |
| **F6** | 知识缺口 | 补 `lr_cache`（LAP↔CML/类白血病 等）、补 `pathognomonic_markers`（NME↔glucagonoma 等）；强化"描述性体征→规范名"归一（NME、leukostasis） | 知识构建脚本、VignetteParser | — |

### 5.1 知识扩充：整合 UMLS + SNOMED CT（资源已就位）

- **本地归档**：`/data3/wanghongyi/umls-2026AA-full.zip`（5.4 GB）、`/data3/wanghongyi/SnomedCT_ManagedServiceUS_PRODUCTION_US1000124_20260301T120000Z.zip`（623 MB）。
- **用途映射**：
  - UMLS 作为 **Layer 1 综合征链补充**（"症状→综合征→疾病"多跳），如 `visual loss → leukostasis → CML`——**正对 case 17**（设计文档 `EXTERNAL_KNOWLEDGE_INTEGRATION_DESIGN.md` 已规划，并以 `lr_cache` 补其缺失的鉴别权重）。
  - SNOMED CT 的层次化概念与因果/表现关系用于：①**体征规范化**（NME、leukostasis 的同义/上位归一，对应 F6）；②**负向/排除关系抽取**（对应 F1）。
- **落点**：沿用现有 `data/knowledge_raw/` + 检索器（`lr_retriever`、`diagnostic_marker_index`、`dx_feature_retriever`、`rag_retriever`）。

### 5.2 检索加速：GPU + 大 batch（应对知识库增长）

- **历史教训**（见导出对话）：493K chunks 在 **CPU 编码约 2.3 小时**，被迫改用 TF-IDF；SentenceTransformer 懒加载首轮空等 **77s**。
- **当前算力**：**GPU 2 = A100-40GB 空闲（约 40 GB 可用）**（GPU 0/1 已被占用）。
- **路线**：嵌入构建/查询编码改用 `device='cuda:2'`，`encode(..., batch_size=256~512, normalize_embeddings=True)`，FAISS 用 `IndexFlatIP`（规模更大时上 IVF/HNSW 或 IVF-PQ 压缩/分片）；启动时**预加载 encoder** 消除首轮 77s；UMLS/SNOMED 概念嵌入一次性离线构建落盘。保留 TF-IDF 作快速回退。

---

## 风险与权衡

- **外部知识可能干扰强模型先验**（Bayesian Elicitation 警示）：F1/F2 的方向硬约束须**仅在 KB 高置信命中时**生效，并保留可观测的覆盖日志，避免把噪声 LR 当真理。
- **对抗复核的成本**：F5 必须**选择性触发**（不确定/接近/检测到偏差时），否则回合数与 token 成本激增（MAI-DxO/iMAD 均强调选择性激活）。
- **概率校准需标定集**：conformal 校准需一小批带金标的校准样本，medbullets 诊断子集可作起点。
- **图像题天花板**：纯文本流水线对 16 道图像题不可解，评估与汇报须始终区分两种口径。

---

## 结论

错误的主因不是"没有知识"，而是 **知识没接到打分环节（缺陷 A）、打分缺方向化/数值化与独立核验（缺陷 B）、选项映射不忠实于后验且自相矛盾（缺陷 C）、关键判别未收敛即提交（缺陷 D）、以及经典认知偏差（缺陷 E）** 的叠加。文献给出的成熟杠杆——KERAP 的正/负知识接地、MedMMV 的证据图幻觉检测 + 不确定度选择、DxChain/MAI-DxO 的选择性对抗验证、conformal 概率校准——与本系统缺陷高度对位；且所需外部知识（UMLS/SNOMED）与算力（A100 空闲）均已就位。

**建议推进顺序**：先做影响面最大的 **F1**（注入 EvidenceAnnotator + 方向硬约束）与 **F3**（AnswerMapper 忠实叶后验、强制自洽），再做 F2/F4（数值 LR + 不确定度门控），随后 F5（选择性对抗复核）与 F6（UMLS/SNOMED 知识扩充 + GPU 加速）。
