# AB16（C2 块3）— 历史复用档案（不入论文主表）

- recorded: 见 `runs/paper_v1/ablations_c2_ab16_reused.json`
- 策略: **不再 live 排期**；从 `compat_synonym_v1` 复用
- 因子: L1 预算=6（默认）、写回=关（冷树 `live_reannotated=0`）、解码=`closed_live_mac` LLM
- 端点: micro-F1 **0.584**；P=0.566；R=0.603；Interp Acc=0.355；n=100
- 源目录: `logs/open_xddx_ox_seq100_v1/compat_synonym_v1/`
- 源评测: `annotate/official_eval_llm_closed_live_mac/summary.json`
- 说明: 非正式方法（正式=M00 F4+写回≈0.651）；计划表曾把「冷+闭集」误记到 AB13，实为 F6 冷=本臂

完整 C2 汇总将在其余臂完成后写入 `ablations_c2_results.md`，并自动并入本复用记录。
