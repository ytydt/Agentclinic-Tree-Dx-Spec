# 2026-06-27 难病 8 题 + MECE 补跑归档

## 状态

- **完成时间**：2026-06-27（日志末行 `Wrote branch_confounder_matrix.json`）
- **命令**：`PYTHONPATH=src python scripts/eval_branch_confounder_matrix.py --llm --exclude-arms A0_legacy`
- **环境 caveat**：本机 `openai` 包过旧（无 `OpenAI` 类），**A5_llm / A5h / A9l / A11_llm / A12 的 LLM 补抽全部失败**；带 LLM 臂的 14 题 Comp 不可与 gnn-llm 上 **A9l=0.812** 专跑混读。确定性臂与 **8 题 multilevel_hard / MECE** 结果有效。

## 文件

| 文件 | 说明 |
|---|---|
| `branch_confounder_matrix.json` | 19 臂完整矩阵（含 multilevel_hard、mece、mece_hard） |
| `branch_recall_eval_set_hard.json` | 8 题标注集 |
| `confounder_matrix_hard_mece_rerun.log` | 完整 stdout（含 OpenAI 错误） |

## 8 题难病 hComp 排序（节选）

| 臂 | hComp | MECE₈ | funnel spotted |
|---|---:|---:|---|
| A11_hybrid_nom / A11_llm | **0.656** | 0.688 | 1.0 |
| A9l_tableC_llm | 0.622 | 0.594 | 1.0 |
| A7_nominate | 0.583 | 0.562 | 1.0 |
| A1_grounding | 0.372 | 0.469 | 0.75 |

主报告 §14 表 4、§7.4 已引用本归档。
