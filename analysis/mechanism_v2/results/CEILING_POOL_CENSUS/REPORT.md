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

---

## Addendum, 2026-08-18: manual reviewer resume and panel recompute

Everything above describes the credit-interrupted state and is retained
unedited. Reviewers B and C were subsequently completed outside OpenRouter and
the panel was rebuilt offline. No new case-bearing provider call was made from
this repository during the rebuild.

### Provenance of the resumed labels

The frozen protocol forbade model substitution, so this is an explicit,
recorded operator override rather than protocol-conformant execution
(`manual_resume/PROVENANCE.md`). It materially weakens the "three
heterogeneous models" claim and must travel with every number below.

| Reviewer | Frozen cache identity | Original run | Resumed cards | Actual executor of the resumed cards |
|---|---|---:|---:|---|
| A | `google/gemini-2.5-flash` | 990 valid, 364 failed | 0 | not resumed |
| B | `anthropic/claude-sonnet-4.6` | 432 valid | 922 | local Cursor Grok 4.6 |
| C | `openai/gpt-5.6-sol` | 1,053 valid | 301 | `gpt-5.6-sol-high` subagents |

Reviewer B's artifact is therefore a two-family mixture: 432 cards from
`claude-sonnet-4.6` and 922 from a Grok model. Reviewer C's resumed cards stay
inside the same model family at a different reasoning effort. Every resumed
cache record carries an explicit `manual_resume` block naming its executor and
retains the frozen model identity string plus prompt/payload SHAs. All 1,223
resumed cards were accepted; the rejection lists are empty.

### Artifact restoration performed before recompute

`design/` had been reduced to cards, index and freeze summary, and
`reviewers/reviewer_a/reviews.jsonl` was absent; the remainder lived only in
`CEILING_POOL_CENSUS_FULL.tar.gz`. The six missing design ledgers and reviewer
A's reviews/telemetry were restored from that archive. The three surviving
design files are byte-identical to the archived copies, reviewer A's restored
reviews match the SHA recorded in its own frozen summary, and the B/C
`.pre_manual` backups are byte-identical to the archived originals, so the
resume added to the immutable set without rewriting it.

An earlier recompute attempt made while reviewer A's file was still missing
projected all of A to `uncertain` and produced a spurious A/B fine agreement of
0.0004. That artifact was discarded and is not reported. The pre-recompute
`panel/` and `analysis/` directories are retained as `*.pre_manual_recompute`.

Uncertain relations fell from 7,023 to 1,578 of 19,599 at this intermediate
point, with reviewer A still unfinished. Before that state was interpreted, A's
own gap was closed; the completed panel is reported below and supersedes the
intermediate figures.

### Reviewer A completion, 2026-08-18, after OpenRouter capacity was restored

Reviewer A's 364 failures split into two mechanically different classes:

- 7 cards held a validator-invalid cache record;
- 357 cards were finalized in `--cache-only` mode and had never been called, so
  no cache record existed for them.

Neither official command covers the second class. `run-reviewer` returns early
once a reviewer summary exists, and `recover-reviewer` requires every failed
card to carry active or quarantined cache provenance. `online_resume/
resume_reviewer_a.py` closes exactly that gap and nothing else: it calls the
never-called cards through the same `OnlineJSONCaller`, frozen model
`google/gemini-2.5-flash`, frozen module, prompt, payload and temperature 0, so
each record lands on the immutable cache identity the original run would have
produced. That identity reconstruction was verified against 50 of A's surviving
valid caches before any call, matching 50 of 50. Unlike the reviewer B and C
resume, this involved **no model, gateway or executor substitution**, so it is
protocol-conformant rather than an override; `mechanism_v2` already routed
through the repository's own `RobustLLMClient`.

Execution: 353 of the 357 never-called cards returned valid reviews on the
first pass. Four returned provider transport errors whose responses were cached
as validator-invalid, joining the original 7. The official `recover-reviewer`
then quarantined all 11 raw invalid caches and re-called them at up to three
attempts each, recovering 3. Reviewer A therefore ends at 1,346 of 1,354 valid
with 8 irreducible validator-invalid cards, which fail-closed to `uncertain`
per §9.2. Pre-recovery reviews and summary are retained under
`reviewers/reviewer_a/quarantine` with their SHAs recorded in the recovery
manifest.

### Reliability gate on the completed panel

| Metric | Required | Credit-interrupted | B/C resumed only | Completed panel | Result |
|---|---:|---:|---:|---:|---|
| A/B complete-boundary agreement | >= 0.90 | 0.9745 | 0.9777 | **0.9857** | pass |
| A/B complete-boundary AC1 | >= 0.75 | 0.9732 | 0.9759 | **0.9843** | pass |
| A/B fine-label agreement | >= 0.80 | 0.5110 | 0.5224 | 0.7210 | **fail** |
| A/B fine-label AC1 | >= 0.60 | 0.4317 | 0.4337 | **0.6729** | pass |
| Overall uncertain rate | <= 0.05 | 0.3583 | 0.0805 | **0.0332** | pass |
| Resolved C/P/X/M/N rate | >= 0.95 | 0.6417 | 0.9195 | **0.9668** | pass |
| Every family/type uncertain rate | <= 0.10 | 0.1974--0.4111 | 0.0000--0.1090 | **0.0000--0.0625** | pass |

Six of the seven checks now pass. Uncertain relations fell to 651 of 19,599.
Panel status is 16,133 three-model majorities, 2,601 E2 root overrides, 217
frozen safe-exact overrides and 648 three-way splits. The final relation
distribution is 815 complete-equivalent, 3,822 partial-parent-or-component,
2,748 manifestation-or-related, 3,511 conflicting-subtype-or-scope, 8,052
not-equivalent and 651 uncertain. Hidden-sentinel complete-boundary agreement
is 0.9650 on the E2 stratum and 0.9816 on the safe-exact stratum, the latter
having risen from 0.5945 through 0.7189 to 0.9816 as coverage closed.

The pre-completion projection is confirmed rather than merely asserted. From
A-answered relations alone, the observed 83.7% tie-break rate projected 0.0346
uncertain, 0.9654 resolved, fine AC1 around 0.673 and fine exact around 0.721;
the realized values are 0.0332, 0.9668, 0.6729 and 0.7210.

### What this establishes

The release rule is conjunctive, so the census remains
`NO_GO_COVERAGE_RELIABILITY_AUDIT_ONLY` and `clinical_width_outputs_released`
stays false. What changed is that the failure is no longer attributable to
coverage, and is now irreducible under this protocol:

- The **complete/not-complete boundary** is reliably measurable by this panel,
  at 0.9857 raw and AC1 0.9843 over all 19,599 frozen relations. This is the
  boundary the primary `clinical-complete` endpoint and the Phase 1-A admission
  gates actually consume.
- The **five-way fine relation taxonomy** is not, and no longer has a coverage
  excuse. With A at 1,346 of 1,354 cards and B/C complete, A/B fine exact
  agreement lands at 0.7210 against a required 0.80. Disagreements concentrate
  in adjacent categories, chiefly `conflicting_subtype_or_scope` versus
  `not_equivalent` and `partial_parent_or_component` versus
  `manifestation_or_related`.

Chapter 12 item 1 is therefore closed structurally and with a fully covered
panel, but still without a clinical-width estimate; item 2 stays a reliability
No-Go. The frozen threshold is not revised after seeing this result, so the old
14-arm width OLS is retired to legacy-only descriptive status rather than
rescued. Any future fine-grained relation endpoint needs a coarser or better
operationalized taxonomy, not more reviewer coverage.
