# OX/MCR official-style eval summary

- protocol: `paper_aligned_judge_v1`
- dataset: `open_xddx`
- judge: `llm`
- ddx_k: `5`

## Diagnostic (must report P/R/F1 separately)

| agg | precision | recall | f1 |
|-----|-----------|--------|-----|
| micro | 0.5042 | 0.5096 | 0.5069 |
| macro | 0.5157 | 0.5278 | 0.5025 |

- correct/total_pred (micro P): 0.5042
- correct/total_gold (micro R): 0.5096
- interpretation_accuracy: 0.3195

## Boundaries

- Not proxy MCQ / mapper option_top1; do not mix into rematch tables.
- pred_ddx from shared_trees global leaf posterior Top-K (not L1 axes).
- Reasoning/interpretation templates use P5 why + selected facts only (no KB chunks).
- LLM judge model substituted: Gemini 2.5 Flash replaces paper gpt-4o-mini / o4-mini / Dual-Inf GPT-4o; prompts unchanged.
