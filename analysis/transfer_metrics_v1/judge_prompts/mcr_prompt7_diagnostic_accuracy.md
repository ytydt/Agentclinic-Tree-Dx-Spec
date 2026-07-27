# MedCaseReasoning Prompt 7 — Diagnostic Accuracy LLM-as-a-judge

- **ID**: `mcr.diag_accuracy`
- **Paper**: Wu et al., MedCaseReasoning (arXiv:2505.11733); PDF appendix “Prompt 7”
- **Paper body note**: Uses the same prompt as McDuff et al. (2025); judge model **in paper**: gpt-4o-mini
- **本仓裁判（契约）**: **Gemini 2.5 Flash**（见 [`JUDGE_MODEL_CONTRACT.md`](JUDGE_MODEL_CONTRACT.md)；`gnn-llm` + `clashon`）
- **Metric**: single-diagnosis correctness (y/n); for N-shot, apply per sample then aggregate
- **Source extraction**: `pdftotext` on https://arxiv.org/pdf/2505.11733.pdf (2026-07-25)

## Template (verbatim)

```
Is our predicted diagnosis correct (y/n)?
Predicted diagnosis: {predicted_diagnosis}, True diagnosis: {actual_diagnosis}
Answer [y/n].
```

## Scoring

- Mark correct iff judge output normalizes to `y` / `yes` (paper used Med-PaLM 2 / gpt-4o-mini; **本仓用 Gemini 2.5 Flash**).
- Do **not** require exact string match between predicted and true labels.

## Placeholders

| Placeholder | Meaning |
|-------------|---------|
| `{predicted_diagnosis}` | System Top-1 / open diagnosis string |
| `{actual_diagnosis}` | Gold `final_diagnosis` |
