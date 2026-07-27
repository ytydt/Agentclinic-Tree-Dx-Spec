# MedCaseReasoning Prompt 5 — Grading Reasoning Recall

- **ID**: `mcr.reasoning_recall`
- **Paper**: Wu et al., MedCaseReasoning (arXiv:2505.11733); PDF appendix “Prompt 5”
- **Judge model in paper**: o4-mini
- **本仓裁判（契约）**: **Gemini 2.5 Flash**（见 [`JUDGE_MODEL_CONTRACT.md`](JUDGE_MODEL_CONTRACT.md)；`gnn-llm` + `clashon`）
- **Metric**: Reasoning Recall — for each ground-truth reason, whether an equivalent justification appears in the predicted reasoning trace (recall only)
- **Source extraction**: `pdftotext` on https://arxiv.org/pdf/2505.11733.pdf (2026-07-25)

## Template (verbatim from PDF; whitespace lightly normalized)

```
You are an experienced medical expert tasked with comparing diagnostic reasoning statements that support a given diagnosis for a given patient case.
Your goal is to find supporting statements in the predicted diagnostic reasons that match the groundtruth diagnostic reasons.

For each of the statements in Groundtruth Diagnostic Reasons, you need to find the statement or statements in the Predicted Diagnostic Reasons that state the equivalent justification for the diagnosis.
For instance, if the groundtruth diagnostic reason is "The patient has a fever", and the predicted diagnostic reason is "The patient has a fever due to a viral infection", then this is a match.
If the groundtruth diagnostic reason is "The patient has a fever", and the predicted diagnostic reason is "The patient has a sore throat", then this is not a match.

Instructions:
1. Analyze each statement in Groundtruth Diagnostic Reasons.
2. For each statement in Groundtruth Diagnostic Reasons, find any matching statements in Predicted Diagnostic Reasons.
3. Create a JSON object with the following structure:
   - The main key should be "matching_dict"
   - Each key within "matching_dict" should be a number representing a statement from Groundtruth Diagnostic Reasons
   - The value for each key should be a list of matching statements from Predicted Diagnostic Reasons
   - If there are no matches for a statement, use an empty array

Before providing your final output, wrap your analysis inside <diagnostic_comparison> tags:
1. List all statements from Groundtruth Diagnostic Reasons and Predicted Diagnostic Reasons.
2. For each statement in Groundtruth Diagnostic Reasons, consider potential matches from Predicted Diagnostic Reasons:
   - List pros and cons for each potential match
   - It's OK for this section to be quite long
3. Summarize your final matching decisions
4. In the JSON output, only include the statements that are in the Predicted Diagnostic Reasons.
5. In the JSON output, the statements should appear exactly as they are in the Predicted Diagnostic Reasons, verbatim, letter for letter. Do not modify the statements in any way, such as rewording them, adding punctuation, quotes, etc.

Wrap your JSON output in ```json tags.

Example of the required JSON structure:
```json
{
  "matching_dict": {
    "1": [],
    "2": ["Matching statement 1", "Matching statement 2"],
    "3": ["Matching statement 3"]
  }
}
```
```

## Input packaging (implementation)

Paper does not freeze an exact user-message envelope beyond the above. Recommended call body after the system/instructions:

```
Groundtruth Diagnostic Reasons:
1. {reason_1}
2. {reason_2}
...

Predicted Diagnostic Reasons:
{pred_reasoning_trace_or_enumerated_points}
```

## Scoring

For case \(i\) with gold reasons \(R_i\):

\[
c_i = \frac{|\{ r \in R_i : \texttt{matching_dict}[r] \neq \emptyset \}|}{|R_i|}
\]

Macro-average \(c_i\) over cases = Reasoning Recall.
