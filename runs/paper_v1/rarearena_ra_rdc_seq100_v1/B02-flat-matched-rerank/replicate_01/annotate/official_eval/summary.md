# OX/MCR official-style eval summary

- protocol: `compatible_metrics_lexical_v1`
- dataset: `rarearena`
- judge: `lexical`
- ddx_k: `2`

## MedCaseReasoning (single trajectory)

- diagnostic_accuracy_single_trajectory: 0.3200
- reasoning_recall_mean: 0.0000
- sampling_protocol: `single_trajectory_v1`

Fast official Acc only (Prompt 7). Reasoning Recall not run.

## Boundaries

- Not proxy MCQ / mapper option_top1; do not mix into rematch tables.
- pred_ddx from shared_trees global leaf posterior Top-K (not L1 axes).
- Reasoning/interpretation templates use P5 why + selected facts only (no KB chunks).
- protocol compatible_metrics_lexical_v1 is NOT paper-official; use --judge llm for paper_aligned_judge_v1.
