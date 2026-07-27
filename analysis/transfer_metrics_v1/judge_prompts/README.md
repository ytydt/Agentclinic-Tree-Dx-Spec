# 裁判提示词编列（Open-XDDx / MedCaseReasoning）

状态：2026-07-25 联网核验  
用途：实现 `paper_aligned_judge_v1` 时的冻结 prompt 资产目录

## 总表

| ID | 数据集 | 指标 | 官方出处 | 本目录文件 | 原文是否取得 |
|----|--------|------|----------|------------|--------------|
| `ox.ddx_match` | Open-XDDx / Dual-Inf | Diagnostic Acc (Eq.1) 自动比对 | Supplementary **Appendix 3**（SI `MOESM2`） | [`ox_appendix3_diagnosis_match.md`](ox_appendix3_diagnosis_match.md) | **是**（2026-07-25） |
| `ox.interpretation_consistency` | Open-XDDx / Dual-Inf | Interpretation Acc (Eq.2) | 同上 Appendix 3 | [`ox_appendix3_interpretation_consistency.md`](ox_appendix3_interpretation_consistency.md) | **是**（2026-07-25） |
| `ox.code_exam_reason_wrong` | Dual-Inf 开源码 | **非**正式指标；examination 模块 | [Code_Dual-Inf.py](https://github.com/betterzhou/Dual-Inf/blob/main/Code_Dual-Inf.py) | [`ox_code_exam_prompts.md`](ox_code_exam_prompts.md) | **是**（勿当作 Appendix 3） |
| `mcr.diag_accuracy` | MedCaseReasoning | Diagnostic Acc（LLM-as-judge） | arXiv:2505.11733 **Prompt 7** | [`mcr_prompt7_diagnostic_accuracy.md`](mcr_prompt7_diagnostic_accuracy.md) | **是** |
| `mcr.reasoning_recall` | MedCaseReasoning | Reasoning Recall | 同文 **Prompt 5** | [`mcr_prompt5_reasoning_recall.md`](mcr_prompt5_reasoning_recall.md) | **是** |
| `mcduff.diag_accuracy` | McDuff et al. | MCR 诊断裁判祖本 | arXiv:2312.00164 | [`mcduff_diag_accuracy_yn.md`](mcduff_diag_accuracy_yn.md) | **是** |

**本仓 LLM 裁判模型**：一律 **Gemini 2.5 Flash**（`gnn-llm` + `clashon` + **workers=50**）— [`JUDGE_MODEL_CONTRACT.md`](JUDGE_MODEL_CONTRACT.md)。


## 实现绑定建议

| 计划开关 | 应加载的 prompt ID | 本仓裁判模型 |
|----------|-------------------|--------------|
| OX `--judge llm` 诊断集合匹配 | **`ox.ddx_match`**（Appendix 3） | **Gemini 2.5 Flash**（`gnn-llm` + `clashon`） |
| OX `--judge llm` Interpretation Acc | **`ox.interpretation_consistency`**（Appendix 3） | 同上 |
| MCR 诊断 | `mcr.diag_accuracy` | 同上（替换论文 gpt-4o-mini） |
| MCR Reasoning Recall | `mcr.reasoning_recall` | 同上（替换论文 o4-mini） |

**模型契约全文**：[`JUDGE_MODEL_CONTRACT.md`](JUDGE_MODEL_CONTRACT.md)。

## 缺口行动

- ~~Appendix 3~~：**已完成**（SI=`MOESM2`，2026-07-25）。
- 实现阶段：模板载入 `judges.py`；summary 写 `judge_prompt_id` + `judge_model=gemini-2.5-flash`。

## 来源链接

- Dual-Inf / Open-XDDx（npj）：https://www.nature.com/articles/s44401-025-00015-6  
- Dual-Inf 预印本：https://arxiv.org/abs/2407.07330  
- Dual-Inf 代码：https://github.com/betterzhou/Dual-Inf  
- MedCaseReasoning：https://arxiv.org/abs/2505.11733 （PDF 附录 Prompt 5/7）  
- McDuff et al.：https://arxiv.org/abs/2312.00164  
