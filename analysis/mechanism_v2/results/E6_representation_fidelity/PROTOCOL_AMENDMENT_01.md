# E6 protocol amendment 01: long JSON and target-blind normalization

Frozen at `2026-08-11T23:52:38Z`, after the representation-builder pilot and
before any selector-arm call.  The original preregistration remains immutable
(`sha256=d1828d1ed912fc6645d8efb667497bf8271ae6c5691af8e33ac843562a973d14`).

## Triggering incident

The first concurrent builder batch was interrupted when a broad set of calls
continued to return `finish_reason=length` at the prior 8,192-token hard
ceiling.  Fourteen complete immutable response caches and thirteen completed
telemetry records existed at interruption; no `case_representations.jsonl`,
matched representation, selector response, diagnostic endpoint, or comparison
was produced.

Seven of the fourteen complete responses passed the raw schema validator.
The other seven exposed bounded contract deviations rather than seven common
semantic failure modes: two count-limit violations, three punctuation or
ellipsis differences in otherwise source-grounded quotes, one unsupported
`event` node-kind spelling, and one self-loop relation.  Gold labels and
selector outcomes were not used to identify or define these repairs.

## Frozen operational changes

1. The online prompt, model, case sample, primary endpoint, contrasts and
   failure policy are unchanged.
2. This phase may set `TREE_DX_DIRECT_POST_OUTPUT_MAX_CAP=16384`.  The existing
   `TREE_DX_DIRECT_POST_OUTPUT_CAP=8192` remains the initial cap and the larger
   value is reached only after a length-truncated physical attempt.  Repository
   compatibility defaults remain 8,192 tokens; the official OpenAI SDK path
   remains preferred when installed and the dependency-free transport remains
   environment-controlled.
3. Raw model responses stay in the immutable cache.  A deterministic,
   target-blind normalization layer may:
   - copy the exact vignette span when the model changed only punctuation or
     marked an omission with a literal ellipsis;
   - trim facts, nodes or relations to the originally specified maxima;
   - map a small frozen set of schema aliases such as `event -> other`;
   - fill only the explicitly allowed `unspecified` time value; and
   - drop self-loops or relations whose endpoint was removed by bounded
     trimming.
4. It may not fuzzy-substitute words, add clinical content, see the gold label,
   use a selector result, repair missing diagnosis evidence, or impute an
   unsuccessful case.  The strict validator runs again after normalization.

## Reporting obligation

Construction acceptance will be reported both before and after normalization,
with the action ledger retained per case.  Manual representation audit will
inspect the raw cache alongside the normalized representation.  The fourteen
pilot caches are resumable inputs, not a separate run; all physical attempts
remain in the archived telemetry.  As a pre-endpoint operational amendment,
this preserves the planned causal comparison while making the transport and
schema failure boundary explicit.
