# Open-XDDx Supplementary Appendix 3 — Interpretation comparison

- **ID**: `ox.interpretation_consistency`
- **Source**: npj Health Systems Dual-Inf SI — `44401_2025_15_MOESM2_ESM.pdf` (Supplementary Appendix 3)
- **URL**: https://static-content.springer.com/esm/art%3A10.1038%2Fs44401-025-00015-6/MediaObjects/44401_2025_15_MOESM2_ESM.pdf
- **Local copy**: [`source/44401_2025_15_MOESM2_ESM.pdf`](source/44401_2025_15_MOESM2_ESM.pdf)
- **Paper judge model**: GPT-4o
- **本仓裁判（契约）**: **Gemini 2.5 Flash**（`gnn-llm` + `clashon`；见 [`JUDGE_MODEL_CONTRACT.md`](JUDGE_MODEL_CONTRACT.md)）
- **Acquired**: 2026-07-25

## Protocol notes (from Supplementary Appendix 2)

- 度量语义一致性，非纯字符串匹配。
- 例：GT `"a severe fever of 104°F"` vs pred `"a severe fever"` → **correct**；vs `"dry cough"` → **wrong**。
- Eq.2：`Interpretation Accuracy = (# correct interpretations) / (# total interpretations)`。
- 另可并行报告 BERTScore / SentenceBert / METEOR（非本 prompt）。

## Template (verbatim, curly quotes / apostrophes normalized to ASCII)

```
You are an experienced doctor. Please determine whether {reason_i} and {reason_j} are basically describing the same symptoms (signs).

From a medical perspective, if both descriptions of the patient's symptoms are roughly the same or closely related, return {'1'}. From a medical perspective, if the conditions (signs) or medical examination results described in these two texts have a substantial amount of content that is basically similar, return {'1'}.

From a medical perspective, if both descriptions of the patient's symptoms are different, return {'0'}.

Please note, do not simply match the text. From a doctors perspective, assessing whether both descriptions are referring to the same symptoms.
```

## Placeholders

| Placeholder | Meaning |
|-------------|---------|
| `{reason_i}` | One interpretation snippet (typically ground-truth evidence string) |
| `{reason_j}` | The other snippet (typically predicted evidence / P5 why 条目) |

## Scoring

- Parse `1` / `0` as for diagnosis prompt。
- 在已匹配的 (gold_dx, pred_dx) 边上，对金标解释列表与预测解释列表做条目级配对后调用本 prompt；累计 correct / total → Interpretation Acc。
- **本仓取得 Appendix 3 后允许**在 `--judge llm` 下声称 `paper_aligned_judge_v1` 的 Eq.2（仍须注明裁判模型替换为 Gemini 2.5 Flash）。
