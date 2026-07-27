# L1 相关工作迁移笔记（排序 / 概率 / 层级）

种子来自 canvas「层级诊断基线调研 · 排序、概率与层级」，并补充 MAC/Dual-Inf 与联网要点。  
每条标注建议落入 **Track B** 或 **Track C**。

---

## 1. Learning-to-rank CDSS for DDx（BMC Med Inform Decis Mak 2023）

- **设定**：症状/检查 → 疾病排序列表；listwise LTR（Approximate NDCG），优于 pointwise MSE。  
- **可迁移思想**：排序目标应直接优化列表质量（NDCG/@k），而非仅点式分类；医师–模型协作环路。  
- **不可比**：需带标签训练池；开放长尾病例报告与诊所 CDS 分布不同。  
- **建议**：Track **C**（条件）→ 小样本仅用冻结特征线性融合；**不**默认训练高容量 LTR。  
- **链接**：https://doi.org/10.1186/s12911-023-02123-5

## 2. MidasMed Bayesian diagnostic assistant（Front. Artif. Intell. 2022）

- **设定**：稀疏病史上的贝叶斯诊断助手；动态稀疏 BN；报告 vignette Top-1 很高，但依赖专有引擎/KB。  
- **可迁移思想**：稀疏证据下的概率更新、共现建模、显式不确定性。  
- **不可比**：专有知识库与病例难度不可复现对照。  
- **建议**：Track **C** 思想 → 启发「低证据时保守更新 / reflect」；**不**引入闭源 KB 为默认。  
- **链接**：https://doi.org/10.3389/frai.2022.727486

## 3. Diagnosis code：flat vs hierarchy-based classifier（经典编码文献）

- **设定**：ICD 等大标签空间上，层级分类器可优于 flat。  
- **可迁移思想**：层级结构有助于大标签空间判别——支持本项目 L1→L2 拆分的一般动机。  
- **不可比**：固定 ICD 树 ≠ 病例自适应 L1 家族。  
- **建议**：动机引用；公平对照仍应是 **candidate-controlled flat union**（canvas 结论），非 ICD 分类器直接上主表。  
- **链接**：https://pubmed.ncbi.nlm.nih.gov/24296907/

## 4. DDXPlus（OpenReview / arXiv:2205.09148）

- **设定**：约 1.3M 合成患者；含鉴别诊断列表、非二元症状、部分症状层级；用于自动问诊/诊断训练。  
- **可迁移思想**：把 **differential 列表** 作为训练信号；层级症状交互。  
- **不可比**：合成分布、有监督规模；与 DiagnosisArena 开放报告题不可直接刷分。  
- **建议**：Track **C** 方法学参照；本仓库无对等训练池 → 不进默认实现。  
- **链接**：https://openreview.net/forum?id=heBKnuV42O

## 5. H-DDx：层级评估框架（arXiv:2510.03700）

- **设定**：自由文本 DDx → ICD-10 映射 + Hierarchical DDx F1；强调 flat Top-k 低估「近错」。  
- **可迁移思想**：**评估**应区分近错与远错；祖先节点部分给分。  
- **对本项目**：可启发 family 指标的「近义父部分命中」审核，但生产树非 ICD；**勿**用 HDF1 替代本协议 family @1。  
- **建议**：Track **B/C 评估层** 借鉴；不直接当训练损失。  
- **链接**：https://arxiv.org/abs/2510.03700

## 6. Dual-Inf（npj / arXiv:2407.07330；仓库 pin Dual-Inf）

- **设定**：forward → backward → examine（support 计数排序）→ 可选 reflect。  
- **可迁移**：support 条数破平、low-conf reflect —— **Track B 核心**。  
- **注意**：无 L1 阶段；上移到家族层须封闭候选。

## 7. MAC（Nature Digit. Med. / 本仓库 single-vendor B06）

- **设定**：多医生讨论 → supervisor Top-2；失败 RRF。  
- **可迁移**：pair/supervisor、多列表 RRF —— Track **B**（缩小版）与 Track **C**（L1-MAC-council）。  
- **注意**：整段嵌建树不迁；须报成本。

## 8. 其他（canvas / 基线相关，简记）

| 工作 | 要点 | 轨道 |
|------|------|------|
| Self-Refine | 批评+修订排序 | C 轻量 / 可并入 B |
| SC-CoT | 多样本投票 | C 成本对照 |
| Flat matched retrieve→rerank | 隔离层级收益 | 实验公平性，非 L1 补丁 |
| MedPrompt | 需带标签训练池 | 条件性；无隔离池则不做 |

---

## 汇总：对本方法 L1 的可执行启发

1. **立刻可设计（B）**：Dual support 重排 + MAC pair + 可选 closed RRF / reflect-lite。  
2. **分列探索（C）**：L1 多医生会诊、开放扩族+归一、Self-Refine/SC、监督 LTR 思想。  
3. **评估借鉴**：H-DDx 提醒 family 近错；本轮仍以协议 family @1/@2 为主终点。  
4. **默认不做**：闭源贝叶斯 KB、无隔离折的高容量 LTR、把 ICD 分类器当主对照。
