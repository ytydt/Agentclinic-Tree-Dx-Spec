# OX/MCR official-style eval summary

- protocol: `paper_aligned_judge_v1`
- dataset: `open_xddx`
- judge: `llm`
- ddx_k: `5`

## Diagnostic (must report P/R/F1 separately)

| agg | precision | recall | f1 |
|-----|-----------|--------|-----|
| micro | 0.8061 | 0.2836 | 0.4196 |
| macro | 0.8707 | 0.2911 | 0.4138 |

- correct/total_pred (micro P): 0.8061
- correct/total_gold (micro R): 0.2836
- interpretation_accuracy: 0.3652

## Boundaries

- Not proxy MCQ / mapper option_top1; do not mix into rematch tables.
- pred_ddx from compat_parallel l2.final_ranking (post-merge/calib).
- Reasoning/interpretation templates use P5 why + selected facts only (no KB chunks).
- LLM judge model substituted: Gemini 2.5 Flash replaces paper gpt-4o-mini / o4-mini / Dual-Inf GPT-4o; prompts unchanged.
