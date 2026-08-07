# AB28（C2 块6）— 历史复用档案（不入论文主表）

- recorded: 见 `runs/paper_v1/ablations_c2_ab28_reused.json`
- 策略: **不再 live 排期**；复用 `analysis/l1_gold_recall_v1/smoke_typed_remap/`
- 干预: 全树叶注入（mean_extra≈16.1）+ typed_llm 重映射
- 端点: R_compat @1/@2 = **0.72/0.78** → inject_typed **0.42/0.69**（Δ@1=-0.30）
- gate: `REJECT`；claim_allowed=`False`
- 说明: 与计划「已测 0.72→0.42」一致；有害干预反事实成立方向不变

完整 C2 汇总将在其余臂完成后写入 `ablations_c2_results.md`，并自动并入本复用记录。
