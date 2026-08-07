# OX/MCR official-style eval summary

- protocol: `compatible_metrics_lexical_v1`
- dataset: `open_xddx`
- judge: `lexical`
- ddx_k: `7`

## Diagnostic (must report P/R/F1 separately)

| agg | precision | recall | f1 |
|-----|-----------|--------|-----|
| micro | 0.3814 | 0.5693 | 0.4568 |
| macro | 0.3814 | 0.5837 | 0.4552 |

- correct/total_pred (micro P): 0.3814
- correct/total_gold (micro R): 0.5693
- interpretation_accuracy: 0.3441

## Boundaries

- Not proxy MCQ / mapper option_top1; do not mix into rematch tables.
- pred_ddx from shared_trees global leaf posterior Top-K (not L1 axes).
- Reasoning/interpretation templates use P5 why + selected facts only (no KB chunks).
- protocol compatible_metrics_lexical_v1 is NOT paper-official; use --judge llm for paper_aligned_judge_v1.
