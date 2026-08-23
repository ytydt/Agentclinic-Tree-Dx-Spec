# C2 pre-execution instrument correction

Declared 2026-08-19 before any C2 annotation, review or selector call.

The modifier binder previously required the model to return both a verbatim
vignette quotation and correct character offsets for every `support_span`. C1
demonstrated that model-computed character arithmetic invalidated 1,515 of
1,600 first-pass selector responses even though 1,399 of those responses
contained quotations that occurred verbatim. The scientific grounding
requirement is literal occurrence; offsets can be recovered deterministically.

C2 now:

- requires `surface_span.text` to occur verbatim in the candidate label and
  writes its deterministically recovered offset into the annotation product;
- requires each vignette `support_span.text` to occur verbatim, but does not
  trust model-computed vignette offsets; accepted quotations are likewise
  persisted with recovered offsets.

The first resumed annotation attempt confirmed the same arithmetic defect for
short labels: 133 cards failed the exact-offset check, but 132 of them had every
surface quotation present verbatim (735/737 claims). This failure-class-only
diagnostic occurred before review, gate, job compilation or outcomes. The
remaining card with nonliteral surface text is still rejected.

This is deliberately narrower than changing the shared `_valid_span` primitive.
C3 still uses exact offsets to establish temporal ordering, where positions
carry scientific meaning. No C2 outcome exists at the time of either correction,
so the changes cannot be outcome-informed.

An initial map-gate diagnostic exposed that validation alone was insufficient:
the accepted text was literal, but the product still retained the model's bad
offsets, producing citation closure 0.6144 and evidence support 0.0. Before any
selector arm was compiled, normalization was added to the product builder and
the review payload was regenerated. The pre-normalization gate is diagnostic
only and is not the final C2 scientific decision.

C2 remains an isolated conditional-conversion topology probe because C1's
efficacy gate did not pass. It selects an existing surface candidate and cannot
synthesize a new core-plus-modifier diagnosis; therefore even a positive result
would not by itself break the DA pool-recall ceiling.
