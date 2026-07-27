# Dual-Inf 开源码中的解释相关 prompt（非 Appendix 3 指标裁判）

- **ID**: `ox.code_exam_*`
- **Source**: https://raw.githubusercontent.com/betterzhou/Dual-Inf/main/Code_Dual-Inf.py (2026-07-25)
- **用途**: Dual-Inf **examination** 流水线（过滤错误 / 补全解释），**不是**论文 Supplementary Appendix 3 的离线指标裁判
- **为何收录**: 公开可得、与“解释是否成立”语义相关；实现正式 Eq.2 前可作对照，但 **summary 不得称为 Appendix 3**

## `evaluate_whether_reason_wrong`（pred 解释是否属于该病的临床表现）

核心指令（从源码 f-string 抽出）：

```
You are an experienced doctor.
I need you to determine whether a symptom```{disease_k_reason_j}``` belongs to the clinical manifestations or test results of the disease ```{disease_k}```.
Specifically, please use your medical knowledge and the provided symptom list ```{disease_k_gnd_symptom_list}``` for the disease ```{disease_k}``` to
determine if ```{disease_k_reason_j}``` also belongs to the clinical manifestations or test results of this disease.
Please DO IT STEP-BY-STEP.
...
Please note that the output should be only 'Yes' or 'No'.
```

调用点：`check_wrong_rationales(pred_dict, gnd_dict)` — 要求两 dict **共享疾病键**。

## `evaluate_whether_reason_missing`（金标症状是否出现在病历）

核心指令：

```
You are an experienced doctor.
I need you to determine whether the patient's condition description (electronic health record) ```{patient_EHR}``` mentions the clinical manifestations or test results of the disease ```{disease_k}```.
Specifically, please use your medical knowledge to determine if a symptom ```{disease_k_reason_j}``` of the disease```{disease_k}``` appears in this patient's condition description ```{patient_EHR}```.
...
Please note, this is not asking for an exact word-for-word match...
Please note that the output should be only 'Yes' or 'No'.
```

## 与 Eq.2 的差异（重要）

| | Appendix 3（论文指标，原文未取得） | 上述 code exam prompts |
|--|-----------------------------------|-------------------------|
| 比较对象 | GT interpretation ↔ predicted interpretation 一致性 | pred 症状 vs 病知识表 / EHR |
| 输出 | （未知，待 SI） | Yes/No |
| 角色 | 离线评测 | 在线过滤/补全 |

完整源码片段备份：[`_extract_dualinf_code_snippets.py.txt`](_extract_dualinf_code_snippets.py.txt)
