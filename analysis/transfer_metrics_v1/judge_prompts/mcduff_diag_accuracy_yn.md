# McDuff et al. — Diagnostic Accuracy LLM-as-a-judge (ancestor of MCR Prompt 7)

- **ID**: `mcduff.diag_accuracy`
- **Paper**: McDuff et al., “Towards Accurate Differential Diagnosis with Large Language Models” (arXiv:2312.00164; Nature 2025)
- **Original judge**: Med-PaLM 2
- **Source**: arXiv HTML Automated Evaluation section (2026-07-25)

## Template (verbatim)

```
Is our predicted diagnosis correct (y/n)? Predicted diagnosis: [diagnosis], True diagnosis: [label]
Answer [y/n].
```

## Note

MedCaseReasoning Prompt 7 is the same template with `{predicted_diagnosis}` / `{actual_diagnosis}` placeholders. Prefer `mcr.diag_accuracy` when evaluating MCR; this file documents provenance.
