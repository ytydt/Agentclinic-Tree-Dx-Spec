# 91：错误别名、空得分代理与竞争者误杀，不能称为 Angiosarcoma 的识别

病例 `MCR_v1_seq100/91` 原金标 **Angiosarcoma**。12个候选中没有独立 Angiosarcoma 标签；multistance 注册表把 **Hemangioma** 的 aliases 写成 Hemangiosarcoma/Angiosarcoma，任务构造器因而将 Hemangioma 作为唯一 gold proxy。两者不是可安全互换的诊断；本文所有 `proxy rank` 都保留这一错误对象的身份，绝不将其更靠前称为血管肉瘤成功。

## 1. 真实病例证据与当前输入缺口

患者36岁，有既往和当前颅内出血、头痛、右同向偏盲。影像最初考虑 cavernous angioma；随后手术见肿物侵犯大脑镰/皮质，病理有恶性梭形细胞、多达20次/10HPF的核分裂，CD31/CD99/Fli-1阳性而CD34/EMA/desmin/actin/Bcl-2阴性。题述包含一个**先影像印象、后病理修正**的顺序，而最终候选池主要由前者或SFT/HPC近邻构成。

固定 findings 保留了CD31、Fli-1等检验事实，但没有完整编码侵袭和血管-细胞构型；`neurologic testing=normal` 概括了“除已经确认的偏盲外无其他局灶缺损”，给泛化正常/异常接合留下风险。两版实际 `retrieved[*].passages` 与四臂raw谓词均没有 **CD31/Fli-1的直接字符串**，但这不等于两种概念都没有来源。独立复审找到了一个重要反例：**PECAM-1是CD31的同义名称**，这个命名关系可核对[原始研究（Baldwin等，1994）](https://pubmed.ncbi.nlm.nih.gov/7956830/)。旧gid554843/v2 gid579202在Kaposi sarcoma小节已有PECAM-1，四臂分别抽出raw1049/1329、1100/1368、1179/1486、1249/1547。它们正确挂在Kaposi主体，去重后实际绑定到Kaposi's Sarcoma，但 `_finding=None`、`_join=None`，没有对患者CD31产生贡献。

因此这里同时有 **已看到并抽到的同义marker桥接缺口** 和 **未证明送达Angiosarcoma完整组合判别源**，不能用字符串普查代替语义覆盖审计；本轮也没有穷尽检索Fli-1全部可能命名。PECAM-1可桥到CD31，不意味着Kaposi等于Angiosarcoma，更不允许把该Kaposi原命题改送不存在的Angiosarcoma候选。人工oracle标签列出的其他全库gids不等于实际served原文，完整疾病的来源覆盖须另行建立，不能从“出现过同一marker”推出。

## 2. 代理的名次变化，不伴随任何自身证据

| 臂 | Hemangioma proxy名次/分数 | proxy已绑定/已接合 | 第一名 | HPC名次/分数 |
|---|---:|---:|---|---:|
| old_old | 6 / 0 | 42 / 0 | Cavernous Angioma | 2 / 3.336 |
| free_old | 5 / 0 | 42 / 0 | Cavernous Angioma | 12 / 4.313（误排除） |
| old_v2 | 6 / 0 | 45 / 0 | Cavernous Angioma | 2 / 2.452 |
| free_v2 | 5 / 0 | 51 / 0 | Cavernous Angioma | 2 / 2.893 |

所有proxy都没有joined finding，没有正贡献也没有负贡献。名次由其他候选的分数、排除状态及零分stable tie决定。`free_old` 的第5名与 `free_v2` 的第5名机制也不同：前者竞争者HPC被排除；后者HPC正常在前，Metastasis变为0分，和proxy等一批候选进入原始顺序的tie。不能因相同rank就认为同一条临床推理被复制。

## 3. 旧索引一次“指标改善”可被定位到竞争者的假必要条件

free_old raw2106–2110与2450–2454来自旧gid412957，源说明SFT的准确识别整合临床评估、影像、组织病理、免疫组化和分子检测。LLM把这个工作流程写成一个 `all/5/required_for/obligatory` 组。E4虽将单条关系降成feature_of，组和obligatory仍保留；F4b随后又把all组作为必要条件。

其中 **molecular testing**（raw2110，重复support2454）被接到患者 **neurologic testing=normal**。这不表示做过阴性的分子检验，更不表示已经证明SFT不成立；但引擎将它作为missing/violated成员，排除Hemangiopericytoma。原始主体SFT通过已有别名绑定到HPC，这一历史映射本身与“normal神经查体=缺乏必要分子证据”的错误要分开。

局部只屏蔽这条错误join，其他规则和组均保留：HPC从第12恢复第2，分数仍4.313；**Hemangioma从第5退回第6，仍为0分**。这是真正的机制反事实，证明那一项proxy进步来自错误惩罚竞争者，而非正确鉴别血管肉瘤。它没有使本例进入top3，因此不能将其计入旧7/11；它揭示相同指标在队列其他位置同样可能被竞争者损伤驱动。

## 4. 一直领先的干扰项为何仍能累积分数

Cavernous Angioma有真实但非决定性的头痛/出血支持，不能为追求金标而删除。问题在于这些先期症状旁又加入了不同人群、器官和任务的附加分：

| 事件 | 明确来源 | 执行中的错位 |
|---|---|---|
| infantile visceral hemangioma 的 gastrointestinal hemorrhage | v2 gid128374，源限定婴儿/内脏与具体器官；四臂原行old591/free622/v2old616/v2free647 | subject错绑Cavernous Angioma，GI出血接颅内出血，追加约0.128–0.160 |
| infantile lesion `resolution before age 4` | old_v2 raw536，gid749238 | 病灶消退年龄接患者当前36岁；显示36<4失败仍给+0.237弱分，且本来就不是同一人群/事件 |
| 已诊断cavernoma的手术指征 | old_v2 raw64–66、70–73；free_v2 raw82–84，gid487196 | resection适应证被抽成feature/required；部位限定、反复出血伴进行性缺损等作用域被压平；靠出血取得组分 |
| **Tolosa-Hunt syndrome** 的诊断组 | free_v2 raw228–231，gid496936 | 原文清楚写THS，却因cavernous sinus词和focus重挂到Cavernous angioma；遗漏替代解释排除等条件；仅头痛满足仍给all/4的+0.772 |

最后一例尤其说明v2组更多并不意味着相关群组更忠实：THS源包括同侧眶周头痛、眼肌麻痹时序、影像/活检证明的肉芽肿、颅神经定位和排除其他诊断。这个有部位、时序、证据方式和排除域的判据，被简化为四个属Cavernous angioma的普通feature。一条泛化头痛不是THS成立，更不是脑内海绵状血管病变的组诊断。

## 5. 非致命累积错误的局部重放与界限

屏蔽GI/年龄错接，再在v2两臂累计屏蔽上述错误手术/THS组的实际患者连接，Cavernous Angioma分数变化如下；保留其他可支持头痛和出血的来源规则：

| 臂 | 原分数 | 局部错误累计屏蔽后 | 排名 |
|---|---:|---:|---|
| old_old | 5.875 | 5.747 | 仍第1 |
| free_old | 9.206 | 9.046 | 仍第1 |
| old_v2 | 6.431 | 4.329 | 仍第1 |
| free_v2 | 7.661 | 6.082 | 仍第1 |

old_v2的两种手术组各加0.853，free_v2另有错误THS部分组分。移除这些污染会降低领先干扰项，但完整Angiosarcoma从未进入候选池，完整组合判别源是否已达没有被证明；PECAM-1这条已达规则的真实主体又是Kaposi，仅修这些join不能据此产生Angiosarcoma诊断。这项“top1不变”是明确的反例边界：不能把所有相对排名失败都归到某一条错误组，也不能把仍然领先的分数当成疾病成立。

本例同时暴露四个不同层次：上游错别名创造假金标；候选池缺完整诊断；决定性组合来源的实际覆盖未被证明，且有PECAM-1已达却未桥接的反例；组/接合/排序再围绕影像近邻积累污染。病例91没有Angiosarcoma top3成功，任何报告均应以这一点为边界。

证据：`judgments_skin_other.json`，`skin_other_additional_probe_results.json` 中恢复molecular-testing竞争者的干预，`skin_other_probe_results.json` 的器官/年龄屏蔽与四臂完整trace。人工式源审由AI完成，不是假称临床专家独立诊断。
