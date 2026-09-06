# 例 326：布鲁氏菌病：病原字段不可达、同义名当体征与病因—病灶竞争

## 病例与终点

57 岁男性，破损手接触未经处理的羊胃后一个月高热、盗汗、背痛；血培养长出 Gram-negative bacillus；T9 椎弓炎性破坏及后方硬膜外脓肿压迫脊髓。gold `Brucellosis` 是完整且适当的病因实体。Epidural abscess、椎骨感染等可以是真实共存病灶，不应称“医学上不存在的错误诊断”；它们只是当前病因问题的竞争答案。实验把病因、病灶和病原类别放进同一互斥排序，没有表达 `Brucellosis causes vertebral infection with epidural abscess`。

## 病因信息确实到达，损坏发生在表示与连接

旧 raw14/17/23/25 已有 Brucella 为 Gram-negative/coccobacilli。患者 finding24 的 label/canonical 只有 blood culture，结果 **Gram-negative bacillus 被放进 value.text**。join 比较 label/canonical，不能将这个结果绑定到病原形态；同时 `blood culture` 与 `cerebrospinal fluid culture` 都能接到该 finding。该机制与是否有更多菌种文献无关。

动物材料暴露与 injured hand 被拆为 finding3、4。旧 raw301 的 skin penetration of those in contact with livestock 比“饮奶”更接近该病例，但缺少复合暴露事件与共同论元，未形成其预期支持。饮用未消毒奶却因共享词被接到接触羊胃，出现多份同一暴露票。这里必须区分：严格谓词“饮用奶”不成立；较粗的动物产品暴露可以保留有界弱先验。因此账本同时给出**保留所有 exposure bridge 的核心敏感性**，没有把所有近义临床桥接都视作应删除。

## 双向污染，而非只压低金标

- **同义标签当患者体征。** 源（旧 gid701410）忠实列 Brucellosis 的 Mediterranean/Malta/Undulant fever 别名。旧 raw11/12/13 的 `synonym_of` 本身可忠实，但 engine 按 feature agreement 接患者 high fever，各 **+0.959**。旧提示/v2 这三份票消失；新提示/v2 又恢复，各 **+1.241**。因此一部分 prompt×index 差量是命名方式造成的票数变化，不是病因证据变强或变弱。
- **金标也得到错位证据。** reactive bone sclerosis 接 C-reactive protein；腹痛/阴囊痛接背痛；CSF culture 接血培养。另一方面 positive Brucella serology 接阴性的 tuberculosis serology，旧/旧和旧/v2各 **−0.4**。病原检测对象丢失可以同时造成虚假支持和虚假反证。
- **竞争病因 Pott 的高权错票。** 源（旧 gid298060）讨论活检中“缺乏多形核粒细胞浸润/干酪坏死”提示结核。raw650 的 absence 保留在谓词文字、polarity=asserted，执行器将它接血中80%中性粒细胞，正加 **+2.777**。此处叠加组织/血样、缺乏/存在两类错误；字符串仍可溯源，故不是无来源幻觉。
- **同名异病与部位错接。** v2 中 Pott puffy tumor 的额部骨膜下脓肿（新提示 raw1731，gid644467）松散绑定为 Pott's disease，并接脊柱后硬膜外脓肿 **+0.938**。源对前者的描述正确，binder 的 Pott 词重合毁坏疾病身份。
- **真实病灶的错误额外票。** 本轮保留硬膜外脓肿、背痛、脊髓受压的真实支持，只阻断例如 epidural tumor→epidural abscess、elevated WBC→仅报告7170/mm³且未标升高等额外错票。不能为了让 Brucellosis 获胜而删除患者实际存在的病灶证据。

## 七个旧 top-3 中，本例为何“看似成功”

四臂 gold均排第三，掩盖病因链未被编译。旧/旧 Brucellosis16.054中，选定严格目标错误票累计约6.57；阻断它们后变9.483并排第四。只阻断所选竞争错误使其排第二，两侧一起阻断仍排第四。但是这个反事实包括对饮奶→羊胃的严格字面阻断；若为粗动物暴露保留弱先验，不能宣称旧top3必定消失。核心敏感性单独给出，以免把更严格的谓词正确性直接等同“该信息毫无诊断价值”。

另一个 v2 错误反而帮它维持top3：gid392067是 **腰椎椎间盘造影的禁忌证**，旧提示 raw603 把“known/suspected infectious discitis”改成 Discitis 的 infection excludes，再接highfever，误杀 Discitis。恢复该竞争者的精确干预也单列。本例说明名次不变可以包含正确证据失联、金标错票消长、错误病因扩张及竞争病灶误杀的共同作用。

## 能与不能识别的结论

确认的是局部程序链与条件反事实；并未证明布鲁氏菌暴露加一般革兰阴性培养对所有病例都是刚性确诊，也未新增临床判据。本例需要的是 typed diagnostic target、因果复合候选、检验结果的实体/样本/时间槽位和受限事件桥接，而非让所有病灶候选退场。疾病名称同义关系不应进入症状匹配求和。


## 四臂名次、分数与局部干预表

| 臂 | 目标分/名次 | 排名第一/分数 | 只屏蔽目标错误join | 只屏蔽竞争错误join | 双侧一起 |
|---|---:|---|---:|---:|---:|
| 旧提示/旧索引 | 16.054 / 3 | Epidural abscess / 23.053 | 4 | 2 | 4 |
| 新提示/旧索引 | 14.524 / 3 | Pott's disease / 18.047 | 3 | 2 | 3 |
| 旧提示/v2 | 13.579 / 3 | Epidural abscess / 21.946 | 3 | 3 | 3 |
| 新提示/v2 | 19.192 / 3 | Epidural abscess / 21.887 | 3 | 2 | 3 |

核心敏感性保留全部粗动物暴露桥接，其他所选目标错误照常阻断：

| 臂 | 核心目标错票阻断后rank | 核心目标+竞争错票阻断后rank |
|---|---:|---:|
| 旧提示/旧索引 | 3 | 3 |
| 新提示/旧索引 | 3 | 2 |
| 旧提示/v2 | 3 | 3 |
| 新提示/v2 | 3 | 2 |

## 明确证据行与首次损坏层

以下按错误家族列出**旧/旧及新/v2**实际产生贡献的代表原始行；去重support完整集合、数值与gate/bind/join元数据见JSON。正数和负数均照实保留，不把所有被选行都计为同向害处。

| 臂 | 错误家族 | 候选 | 代表raw行 | 实际贡献合计 |
|---|---|---|---|---:|
| 旧提示/旧索引 | D_wrong_lesion_or_numeric_state | Epidural abscess | 785, 938 | 1.801 |
| 旧提示/旧索引 | D_specimen_identity_anatomic_mismatch | Pott's disease | 650, 715, 1532, 1561, 1597 | 5.757 |
| 旧提示/旧索引 | T_exposure_route_mismatch | Brucellosis | 9, 55, 375 | 2.616 |
| 旧提示/旧索引 | T_synonym_to_patient_symptom | Brucellosis | 11, 12, 13 | 2.876 |
| 旧提示/旧索引 | T_specimen_mismatch | Brucellosis | 92 | 0.571 |
| 旧提示/旧索引 | T_anatomic_mismatch | Brucellosis | 110, 224, 370 | 0.254 |
| 旧提示/旧索引 | T_imaging_to_lab | Brucellosis | 133 | 0.253 |
| 旧提示/旧索引 | H_pathogen_test_mismatch | Brucellosis | 373 | -0.400 |
| 新提示/v2 | D_wrong_lesion_or_numeric_state | Epidural abscess | 768, 897 | 1.628 |
| 新提示/v2 | D_specimen_identity_anatomic_mismatch | Pott's disease | 614, 629, 1565, 1614, 1673, 1731 | 6.472 |
| 新提示/v2 | T_exposure_route_mismatch | Brucellosis | 3, 45, 305, 318 | 3.488 |
| 新提示/v2 | T_synonym_to_patient_symptom | Brucellosis | 5, 6, 7 | 3.724 |
| 新提示/v2 | T_specimen_mismatch | Brucellosis | 123 | 1.002 |
| 新提示/v2 | T_imaging_to_lab | Brucellosis | 136 | 0.162 |
| 新提示/v2 | T_anatomic_mismatch | Brucellosis | 235, 300 | 0.162 |

## 重放与审计口径

本报告使用 `replay_audit.py` 的 historical_default_stale B1/S7，完全冻结来源、病例facts、候选顺序与模型缓存；完整贡献未截至25条。此前exact_arm_window版本的若干竞争者分数略有变化，不能混用；gold名次一致并不等于所有分数一致。所有表格来自 `judgments_infect_neuro.json`，原始行号是**合并病例抽取数组零基索引**，不是局部cache行号。`_audit_source` 同时保存cache、gid、focus、局部行和源hash。

- numeric-only (`remove_contributions`)：只移除指定贡献，保留join、claimants和硬判决，测量固定连线中的票效应。
- join-block (`block_joins`)：在最佳匹配后、claimants/组执行前屏蔽指定连接，不寻找替代匹配；它会改变其他候选权重，属于条件机制干预。
- 本报告只审计指定错误家族，不声称覆盖所有分数的临床正确性。未插入oracle事实、未按gold删合法弱支持、未调用新LLM。病例是既定11题开发样本，不估计总体错误率。
- 由AI审计员逐段阅读与程序复算，不是真实临床专家双盲研究。`*_initial_probe.txt` 是早期定位中间件，可能包含同predicate的多个候选raw匹配，**最终归因以完整trace的deduplicated support IDs为准**。
