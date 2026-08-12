# RCR-3 frozen end-to-end design

RCR-3 uses the same 300-case relation-challenge development sample as E6/E12
(DA 150, MCR 150).  It is a fresh end-to-end generation test, not a replay of
historical e7 proposals.  Gold labels, answer options, historical champions,
votes, ranks and registry scores are withheld from every online payload.

Three arms share one Llama 3.3 70B backbone, the exact/frozen-safe-synonym
registry and one completeness-first pairwise selector:

| arm | logical calls | generation contract |
|---|---:|---|
| `lite3_safe` | 3 | syndrome/anatomy generator + history-isolated etiology/temporal generator + selector |
| `rcr3_default` | 3 | grounded relation/event skeleton + one batched three-view typed generator + selector |
| `compact4_true3gen` | 4 | the exact two frozen Lite generators + a third subtype/exception generator + selector |

Compact-4 must byte-reuse Lite's first two generator records; it may not obtain
new samples for its shared stages.  This makes its only additional generation
treatment the third independent view.  RCR-3 spends the same three-call budget
as Lite but trades a separate generator for an auditable relation skeleton and
three batched typed views.

Every source span is checked against the clean vignette.  Ungrounded spans and
relations are removed and counted, never silently treated as evidence.  Entity
identity permits exact/frozen safe synonyms only; substring, Jaccard and
broad/subtype merging are forbidden.  The deterministic frontier keeps six
main and up to two evidence-backed protected candidates.  Candidate order,
generator count/votes and registry scores are hidden from the selector.

Strict exact-or-safe-synonym pre-mapper Top-1 is primary.  Clinical-complete
Top-1/Top-2 after heterogeneous queue expansion and root audit is the main
mechanism endpoint.  Exposure, conversion, grounding fidelity, cap loss,
candidate type/scope, calls/tokens/latency/provider provenance and complete-or-
partial sensitivity are secondary.  McNemar/Holm inference uses the case as
the paired unit across three primary contrasts.

This is development/mechanism evidence.  Repeat runs, a larger confirmation
set and provider/retry standardisation are excluded by instruction; technical
failures remain fail-closed in intention-to-analyse results.
