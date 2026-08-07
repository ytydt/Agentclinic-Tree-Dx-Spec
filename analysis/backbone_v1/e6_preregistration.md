# E6 预注册（锁定）

Created: 2026-08-06
Status: **LOCKED** after E3/E4/E5.

## 批 3 结果摘要（锁定依据）

| arm | entrance | select | k | lexical@0.7 | option@1 |
|---|---|---|---:|---:|---:|
| v0_s4b_k5 (E1) | llm_ddx | b | 5 | 0.36 | **0.50** |
| v0_s4a_k5 | llm_ddx | a | 5 | 0.36 | — |
| v0_s4c_k5 | llm_ddx | c | 5 | 0.31 | — |
| v0_s4b_k8 | llm_ddx | b | 8 | 0.37 | **0.52** |
| e3_kb_only_k5 | kb_rrf | b | 5 | 0.44 | **0.57** |

S4-c 未通过：C 桶改善 0（阈值 ≥6），D 桶恶化 3（阈值 ≤3）。
E3 未通过「下降 ≥0.10」准则：kb_only 反而 +0.07 option@1。
→ **不确认**「LLM-DDx 入口是全部主机制」；kb 路径在 DA 选项端点上更强。

## 确认集配置（预注册）

- 数据集：MedCaseReasoning `mcr_val_seq100_v2`
- arm：`confirm_v2_s4b_k8`
- select_variant：**b**
- max_k：**8**
- entrance：**llm_ddx**
- 理由：在 llm_ddx 家族内 option@1 最优（0.52）；kb_only 虽更高，但是消融臂而非主张的骨干故事，另记为负结果

## 判定阈值（不可在见结果后修改）

切片一骨干 v0_s4b_k5 Acc = **0.24**；B02 = 0.17；M00 = 0.50。

1. **主判定（通过）**：切片二 Acc ≥ 0.22（相对 B02 +0.05）
2. **负判定（不确认）**：切片二 Acc < 0.17
3. 不与 M00 比作通过条件

## 附带报告（非预注册通过条件）

E3 在 DA 上 kb_only > llm_ddx，写入结果文档为机制争议证据。

## 结果（跑后填写，不改上方阈值）

- Acc@1 = **0.22**（22/100）
- 相对主判定 Acc ≥ 0.22：**通过**
- 相对负判定 Acc < 0.17：未触发
- 记录文件：`logs/backbone_v1/medcasereasoning_v2/confirm_v2_s4b_k8/annotate/official_eval_llm/summary.json`

