# OX/MCR official-style eval summary

- protocol: `compatible_metrics_lexical_v1`
- dataset: `open_xddx`
- judge: `lexical`
- ddx_k: `5`

## Diagnostic (must report P/R/F1 separately)

| agg | precision | recall | f1 |
|-----|-----------|--------|-----|
| micro | 0.4480 | 0.4776 | 0.4623 |
| macro | 0.4480 | 0.4984 | 0.4646 |

- correct/total_pred (micro P): 0.4480
- correct/total_gold (micro R): 0.4776
- interpretation_accuracy: 0.3352

## Boundaries

- Not proxy MCQ / mapper option_top1; do not mix into rematch tables.
- pred_ddx from shared_trees global leaf posterior Top-K (not L1 axes).
- Reasoning/interpretation templates use P5 why + selected facts only (no KB chunks).
- protocol compatible_metrics_lexical_v1 is NOT paper-official; use --judge llm for paper_aligned_judge_v1.
