# OX/MCR official-style eval summary

- protocol: `paper_aligned_judge_v1`
- dataset: `medcasereasoning`
- judge: `llm`
- ddx_k: `2`

## MedCaseReasoning (single trajectory)

- diagnostic_accuracy_single_trajectory: 0.1900
- reasoning_recall_mean: 0.3689
- sampling_protocol: `single_trajectory_v1`

Not MedCaseReasoning official 10-shot Acc; do not cross-compare with paper tables.

## Boundaries

- Not proxy MCQ / mapper option_top1; do not mix into rematch tables.
- pred_ddx from shared_trees global leaf posterior Top-K (not L1 axes).
- Reasoning/interpretation templates use P5 why + selected facts only (no KB chunks).
- LLM judge model substituted: Gemini 2.5 Flash replaces paper gpt-4o-mini / o4-mini / Dual-Inf GPT-4o; prompts unchanged.
- diagnostic_accuracy_single_trajectory ≠ official 10-shot Acc.
