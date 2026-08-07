# 红队审计 Tier 0：零算力分析结果

分词器：`tiktoken_cl100k_base`（无官方 token 账本，输出侧重建）

## A. 全队列五级失败归因

| 阶段 | DiagnosisArena | MedCaseReasoning | Open-XDDx |
|---|---|---|---|
| Local elimination | 17 | 20 | 40 |
| Global misranking | 22 | 10 | 6 |
| Coverage miss (unresolved) | 20 | 22 | 15 |
| Success | 40 | 46 | 38 |
| Unscorable | 1 | 2 | 1 |

### A.1 覆盖缺口桶的同队列解析（部署配置自身产物，离线词法谓词）

n = 20

| 判定 | 例数 |
|---|---|
| Probe disagreement | 7 |
| Binding failure | 7 |
| Structural absence (needs clinical adjudication) | 6 |

- 例 29：*IgG4-related rhinosinusitis with concurrent Streptococcus constellatus bacterial rhinosinusitis* → Probe disagreement；树上最佳等价叶 *Bacterial Rhinosinusitis with Orbital Complications*（分数 0.76）；接口绑定叶 ['B5.3']
- 例 33：*ST-segment elevation due to myocardial metastasis from squamous cell carcinoma of the lung* → Probe disagreement；树上最佳等价叶 *Cardiac Metastasis from Lung Cancer*（分数 0.74）；接口绑定叶 ['B1.1', 'B4.2']
- 例 39：*Metastatic Crohn disease* → Binding failure；树上最佳等价叶 *Cutaneous Crohn's Disease*（分数 0.78）；接口绑定叶 无
- 例 5：*Left maxillary giant cell reparative granuloma (GCRG)* → Binding failure；树上最佳等价叶 *Central Giant Cell Granuloma*（分数 0.77）；接口绑定叶 无
- 例 102：*Annular epidermolytic ichthyosis (AEI)* → Binding failure；树上最佳等价叶 *Epidermolytic Ichthyosis*（分数 0.92）；接口绑定叶 无
- 例 107：*Keloidal scleroderma* → Binding failure；树上最佳等价叶 *Keloidal Scleroderma*（分数 1.00）；接口绑定叶 无
- 例 117：*Pyoderma with Staphylococcus simulans* → Structural absence (needs clinical adjudication)；树上无词法等价叶；接口绑定叶 ['B1.1']
- 例 118：*Inflammation-induced ocular neuropathy associated with SARS-CoV-2–induced panuveitis* → Binding failure；树上最佳等价叶 *Inflammation-induced ocular neuropathy associated with SARS-CoV-2-induced panuveitis*（分数 1.00）；接口绑定叶 无
- 例 125：*Tumors of the follicular infundibulum (TFI)* → Structural absence (needs clinical adjudication)；树上无词法等价叶；接口绑定叶 无
- 例 132：*Trifascicular heart block (Bifascicular block with first-degree AV block progressing to complete heart block)* → Probe disagreement；树上最佳等价叶 *Trifascicular Heart Block*（分数 0.92）；接口绑定叶 ['B5.3']
- 例 147：*Linear or annular lupus erythematosus panniculitis of the scalp (LALPS)* → Probe disagreement；树上最佳等价叶 *Linear or Annular Lupus Erythematosus Panniculitis of the Scalp (LALPS)*（分数 1.00）；接口绑定叶 ['B1.1']
- 例 151：*Large middle cerebral artery territory embolic stroke* → Structural absence (needs clinical adjudication)；树上无词法等价叶；接口绑定叶 ['B1.1']
- 例 165：*Nocardia brasiliensis skin infection* → Probe disagreement；树上最佳等价叶 *Nocardia brasiliensis Skin Infection*（分数 1.00）；接口绑定叶 ['B3.2']
- 例 188：*Coronary Artery Disease (CAD) with Giant R-wave Syndrome* → Structural absence (needs clinical adjudication)；树上无词法等价叶；接口绑定叶 无
- 例 198：*Stage IA endometrial cancer* → Structural absence (needs clinical adjudication)；树上无词法等价叶；接口绑定叶 无
- 例 225：*Richter's transformation presenting as penile ulcer (transformation of chronic lymphocytic leukemia to diffuse large B-cell lymphoma)* → Probe disagreement；树上最佳等价叶 *Richter's Transformation*（分数 0.92）；接口绑定叶 ['B2.1']
- 例 226：*Actinic prurigo with associated cheilitis* → Binding failure；树上最佳等价叶 *Actinic Prurigo*（分数 0.92）；接口绑定叶 无
- 例 241：*Endogenous endophthalmitis with iris abscess* → Binding failure；树上最佳等价叶 *Endogenous Traumatic Endophthalmitis*（分数 0.77）；接口绑定叶 无
- 例 81：*Disseminated Strongyloides stercoralis infection with ocular involvement (choroiditis)* → Probe disagreement；树上最佳等价叶 *Fungal Infection with Multisystem Involvement*（分数 0.76）；接口绑定叶 ['B5.1']
- 例 90：*Caruncular melanoma* → Structural absence (needs clinical adjudication)；树上无词法等价叶；接口绑定叶 ['B3.1']

### A.2 已发表的 20 例绑定审计（不同探针、不同病例集）

- 审计例数 20；与部署配置覆盖缺口桶的 case id 完全一致：**False**
- 仅在部署桶中：['102', '117', '118', '132', '147', '151', '165', '225', '29', '33', '81', '90']
- 仅在审计中：['11', '114', '129', '183', '187', '22', '229', '231', '242', '27', '67', '97']
- 审计结论：父家族缺失 2；绑定失败 18
- 其中树上存在**精确等价叶** 13 例，仅存在可接受父家族 5 例

> 该审计按**家族覆盖探针**选例，而全队列桶按**叶覆盖探针**选例；两者是不同探针，重叠仅 8 例。因此 18/20 不能直接叠加到部署配置的 20 例覆盖缺口上。

## B. 召回利用瀑布（主方法）

| 基准 | 结构可达 | 通过局部前沿 | 进入截断线内 | 接口计分 |
|---|---|---|---|---|
| DiagnosisArena | 79 | 62 | 40 | 40 |
| MedCaseReasoning | 76 | 56 | 46 | 46 |
| Open-XDDx | 84 | 44 | 38 | 38 |

## C. 三轴预算（每例均值）

| 基准 | 臂 | 模型调用 | 输出 token（重建） | 延迟 s |
|---|---|---|---|---|
| DiagnosisArena | 主方法 | 94.3 | 24781 | 288.3 |
| DiagnosisArena | 十轨平面对照 | 92.4 | 19414 | 167.5 |
| DiagnosisArena | 比值（主/对照） | 1.02 | 1.28 | 1.72 |
| MedCaseReasoning | 主方法 | 81.2 | 20496 | 246.0 |
| MedCaseReasoning | 十轨平面对照 | 93.2 | 17934 | 177.6 |
| MedCaseReasoning | 比值（主/对照） | 0.87 | 1.14 | 1.39 |
| Open-XDDx | 主方法 | 68.6 | 41564 | 206.6 |
| Open-XDDx | 十轨平面对照 | 89.8 | 20288 | 188.8 |
| Open-XDDx | 比值（主/对照） | 0.76 | 2.05 | 1.09 |

## D. Open-XDDx 解释正确率

主方法 0.354；高于主方法的臂数 4（MDAgents, Flat beam search, Flat rerank, MEDDxAgent）；落在 0 的臂数 2（Self-consistent CoT (5 samples), Medprompt-style）

| 系统 | micro-F1 | 解释正确率 |
|---|---|---|
| APHHM | 0.651 | 0.354 |
| MAC | 0.570 | 0.221 |
| Direct CoT | 0.543 | 0.233 |
| MDAgents | 0.543 | 0.424 |
| Self-consistent CoT (5 samples) | 0.539 | 0.000 |
| Self-refine | 0.530 | 0.206 |
| Medprompt-style | 0.522 | 0.000 |
| Flat beam search | 0.510 | 0.642 |
| Dual-Inf | 0.507 | 0.320 |
| Flat rerank | 0.495 | 0.419 |
| MEDDxAgent | 0.491 | 0.403 |
| MedRAG | 0.485 | 0.224 |
| Chain-of-Diagnosis + shared corpus | 0.475 | 0.215 |
| CoT+RAG | 0.467 | 0.240 |
| i-MedRAG | 0.418 | 0.237 |

## E. 接口归因损失（DiagnosisArena Top-1）

均值 0.041，范围 [0.020, 0.080]，共 18 个臂

| 系统 | 原生接口 | 修复绑定后 | 接口归因损失 | 修复例数 |
|---|---|---|---|---|
| Self-refine | 0.57 | 0.65 | 0.080 | 26 |
| Self-consistent CoT (5 samples) | 0.52 | 0.58 | 0.060 | 20 |
| Direct CoT | 0.54 | 0.59 | 0.050 | 21 |
| Flat rerank (structural proxy) | 0.48 | 0.53 | 0.050 | 15 |
| MEDDxAgent | 0.62 | 0.67 | 0.050 | 17 |
| Medprompt-style | 0.52 | 0.57 | 0.050 | 16 |
| MedRAG | 0.48 | 0.53 | 0.050 | 12 |
| CoT+RAG | 0.55 | 0.59 | 0.040 | 18 |
| Flat rerank | 0.56 | 0.60 | 0.040 | 12 |
| MDAgents | 0.58 | 0.62 | 0.040 | 21 |
| Chain-of-Diagnosis + shared corpus | 0.54 | 0.58 | 0.040 | 14 |
| Flat beam search | 0.52 | 0.55 | 0.030 | 11 |
| MAC | 0.61 | 0.64 | 0.030 | 22 |
| i-MedRAG | 0.60 | 0.63 | 0.030 | 17 |
| Flat rerank $\times 10$ (RRF) | 0.47 | 0.49 | 0.020 | 14 |
| Dual-Inf | 0.60 | 0.62 | 0.020 | 12 |
| APHHM | 0.71 | 0.73 | 0.020 | 28 |
| DiagnosisGPT-6B | 0.14 | 0.14 | 0.000 | 0 |

## F. MedCaseReasoning 准确率与推理召回的解耦

基线臂间 Pearson r = 0.141，Spearman ρ = 0.190（n = 14 个臂）

| 系统 | 准确率 | 推理召回 | 命中例上召回 | 未命中例上召回 |
|---|---|---|---|---|
| MEDDxAgent | 0.24 | 0.412 | 0.336 | 0.436 |
| MAC | 0.23 | 0.527 | 0.525 | 0.528 |
| CoT+RAG | 0.22 | 0.478 | 0.383 | 0.505 |
| Flat beam search | 0.21 | 0.447 | 0.533 | 0.424 |
| Self-refine | 0.21 | 0.447 | 0.545 | 0.421 |
| MDAgents | 0.20 | 0.570 | 0.573 | 0.569 |
| Self-consistent CoT (5 samples) | 0.19 | 0.369 | 0.423 | 0.356 |
| i-MedRAG | 0.19 | 0.482 | 0.599 | 0.455 |
| Direct CoT | 0.18 | 0.510 | 0.484 | 0.516 |
| Medprompt-style | 0.18 | 0.294 | 0.213 | 0.312 |
| Flat rerank | 0.17 | 0.404 | 0.440 | 0.397 |
| Dual-Inf | 0.17 | 0.444 | 0.442 | 0.445 |
| MedRAG | 0.17 | 0.557 | 0.546 | 0.559 |
| Chain-of-Diagnosis + shared corpus | 0.14 | 0.430 | 0.287 | 0.454 |

## G. 案例候选

绑定失败且树上有精确等价叶：13 例
绑定失败但仅有可接受父家族：5 例
父家族缺失：2 例

- 例 5：目标 *Left maxillary giant cell reparative granuloma (GCRG)*；树上叶 *Central Giant Cell Granuloma of the Maxillary Sinus*；接口关系 `unrelated`
- 例 27：目标 *Histiocytoid Sweet syndrome*；树上叶 *Histiocytoid Sweet Syndrome*；接口关系 `unrelated`
- 例 39：目标 *Metastatic Crohn disease*；树上叶 *Cutaneous Crohn's Disease|Cutaneous Crohn's Disease*；接口关系 `unrelated`
- 例 97：目标 *Anti-TIF-1γ juvenile dermatomyositis (JDM)*；树上叶 *Anti-TIF-1γ juvenile dermatomyositis (JDM)*；接口关系 `equivalent`
- 例 107：目标 *Keloidal scleroderma*；树上叶 *Keloidal Scleroderma*；接口关系 `unrelated`
- 例 114：目标 *Reversible cerebral vasoconstriction syndrome (RCVS)*；树上叶 *Reversible Cerebral Vasoconstriction Syndrome (RCVS)*；接口关系 `unrelated`

- 父家族缺失 例 67：目标 *Septic shock with anuric kidney failure*；Tree axis is CNS-involvement disorders; gold is systemic septic shock + anuric renal failure. No clinically adequate L1 parent for primary sepsis/shock on this tree.
- 父家族缺失 例 231：目标 *Stage IV invasive renal urothelial carcinoma*；Tree framed as cutaneous papillomatosis / paraneoplastic syndrome; gold is Stage IV renal urothelial carcinoma itself. No L1 that cleanly hosts primary urothelial ca as the diagnosis axis.
