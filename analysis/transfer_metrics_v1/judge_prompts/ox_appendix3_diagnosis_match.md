# Open-XDDx Supplementary Appendix 3 — Diagnosis comparison

- **ID**: `ox.ddx_match`
- **Source**: npj Health Systems Dual-Inf SI — `44401_2025_15_MOESM2_ESM.pdf` (Supplementary Appendix 3)
- **URL**: https://static-content.springer.com/esm/art%3A10.1038%2Fs44401-025-00015-6/MediaObjects/44401_2025_15_MOESM2_ESM.pdf
- **Local copy**: [`source/44401_2025_15_MOESM2_ESM.pdf`](source/44401_2025_15_MOESM2_ESM.pdf)
- **Paper judge model**: GPT-4o（Appendix 2/3）
- **本仓裁判（契约）**: **Gemini 2.5 Flash**（`gnn-llm` + `clashon`；见 [`JUDGE_MODEL_CONTRACT.md`](JUDGE_MODEL_CONTRACT.md)）
- **Acquired**: 2026-07-25

## Protocol notes (from Supplementary Appendix 2)

- 不同术语但医学等价 → 正确（如 Breast Cancer / Breast Malignancy）。
- 一方为另一方亚型/子集 → 正确（如 Diabetes Mellitus / Type I Diabetes Mellitus）。
- 实质不同病 → 错误（如 Benign Breast Tumor / Breast Malignancy；Type I / Type II DM）。
- Eq.1：`Diagnostic Accuracy = (# correct diagnoses) / (# total diagnoses)`。

## Template (verbatim, curly quotes normalized to ASCII)

```
You are an experienced doctor. Please determine whether {key_pred} and {key_gnd} refer to the same disease. Please note, do not simply match the text.

From a medical perspective, if they are the same or nearly the same disease, or if {key_pred} is a subset of {key_gnd}, your response should be {'1'}.

From a medical perspective, if they are essentially different diseases, your response should be {'0'}.
```

## Placeholders

| Placeholder | Meaning |
|-------------|---------|
| `{key_pred}` | Predicted disease name |
| `{key_gnd}` | Ground-truth disease name |

## Scoring

- Parse response for `1` / `0`（允许包在引号或花括号中）。
- `1` → match（计入 correct）；`0` → non-match。
- 集合评测：对 pred↔gold 配对边调用本 prompt（一对一匹配策略见实现计划）。
