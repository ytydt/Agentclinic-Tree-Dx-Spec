# C0 full-pool census and E5 transition review: closure result

Status: **NO_GO_COVERAGE_RELIABILITY_AUDIT_ONLY**

This artifact closes the construction and coverage audit for Chapter 12 items
1--2. It does not release a new clinical-width coefficient or E5 transition
estimate because the frozen three-model panel did not pass its reliability
gate. New labels remain model-panel sensitivity labels, never human/root truth.

## Frozen census

| Quantity | Frozen value |
|---|---:|
| Development cases | 800 |
| Unique `(case, normalized candidate)` relations | 19,599 |
| Blinded cards | 1,354 |
| Candidate occurrences | 320,190 |
| Pool rows | 57,000 |
| Top-1 rows | 18,568 |
| Source bindings | 7,649 |
| E2 root reuse | 2,601 |
| Exact-bridge total | 344 |
| Exact-bridge overlap with E2 | 127 |
| Net further exact coverage | 217 |
| Relations requiring panel review | 16,781 |

Relation coverage by source group is HIST14 15,450; E4 3,673; E5 2,270;
E9 2,024; and E12 3,173. The arithmetic correction is therefore
`2,601 + (344 - 127) = 2,818` known relations and `19,599 - 2,818 =
16,781` panel-pending relations. The older wording “a further 344” was wrong;
the frozen set construction itself already used the correct set subtraction.

The E12 actual-payload ledger was corrected to the numeric candidate-ID order
used by the committed online `make_payload()` path. This changed only the E12
occurrence/pool ordering hashes. Card, relation-universe, known-truth, source-
binding and Top-1 bytes remained identical, so all existing reviewer cache
identities stayed valid.

HIST14 `actual_payload` is unavailable because the original requests were not
archived. Its registry and effective-frontier surfaces are retained, but no
actual-payload coefficient is inferred from them.

## Panel execution and operational boundary

The three reviewers saw the same complete arm-blind card universe. The account
exhausted its OpenRouter credits during execution. Existing immutable responses
were retained and the remaining cards were finalized in `--cache-only` mode as
explicit failures; no missing card was deleted, imputed or assigned a clinical
label.

| Reviewer | Frozen model | Valid cards | Validator-invalid cached cards | Missing after credit exhaustion | Total |
|---|---|---:|---:|---:|---:|
| A | `google/gemini-2.5-flash` | 990 | 7 | 357 | 1,354 |
| B | `anthropic/claude-sonnet-4.6` | 432 | 0 | 922 | 1,354 |
| C | `openai/gpt-5.6-sol` | 1,053 | 0 | 301 | 1,354 |

Missing or invalid candidate judgments project to `uncertain` on the frozen
19,599-relation denominator. This is deliberately conservative. The high A/B
complete-boundary agreement below is partly inflated because simultaneous
failures agree on `uncertain`; it is not evidence of strong clinical
reliability.

## Reliability gate

| Metric | Required | Observed | Result |
|---|---:|---:|---|
| A/B complete-boundary agreement | >= 0.90 | 0.9745 | pass, not independently sufficient |
| A/B complete-boundary AC1 | >= 0.75 | 0.9732 | pass, not independently sufficient |
| A/B fine-label agreement | >= 0.80 | 0.5110 | fail |
| A/B fine-label AC1 | >= 0.60 | 0.4317 | fail |
| Overall uncertain rate | <= 0.05 | 0.3583 | fail |
| Resolved C/P/X/M/N rate | >= 0.95 | 0.6417 | fail |
| Every family/type uncertain rate | <= 0.10 | 0.1974--0.4111 | fail |

The pre-override panel contains 2,802 three-way splits. After the frozen E2 and
safe-exact overrides, the final distribution contains 7,023 uncertain
relations. Hidden-sentinel accuracy was also inadequate for treating the new
panel as a substitute for root adjudication.

## Decision and interpretation boundary

Because the joint gate failed, the analysis correctly emitted
`clinical_width_outputs_released=false`. No full-pool clinical exposure slope,
conversion estimate, or E5 transition table is released from this panel. This
round therefore neither confirms nor overturns the earlier local
recall--conversion association; it shows that the attempted model-panel truth
upgrade is not reliable enough to adjudicate it.

The deterministic census itself is complete and reusable. A continuation may
resume only the missing immutable reviewer identities after the same account
has sufficient credit, then rebuild A/B/final summaries from the full panel.
Until that happens, Chapter 12 item 1 is closed structurally but not as a new
clinical-width estimate, and item 2 is closed as a pre-specified reliability
No-Go rather than a transition estimate.
