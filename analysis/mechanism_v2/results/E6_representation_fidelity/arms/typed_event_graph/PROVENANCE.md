# E6 arm: typed event graph

- Selector: `deepseek/deepseek-v4-flash-0731`, temperature 0, 50 non-RAG
  workers, target-blind payload.
- Attempted rows: 300; builder-eligible calls: 258; schema-valid selector
  responses: 256 (124 DA, 132 MCR).
- Strict exact-or-frozen-synonym differential recall: 6/256; strict top-1:
  3/256 (all MCR).
- Fail-closed rows: 42 preregistered construction failures plus two
  champion/runner ordering violations.  All 258 called-response caches are
  retained; 254 telemetry rows make the ledger a lower bound.
- Recorded lower bound: 254 semantic calls, 327 physical attempts, 274,913
  input tokens and 1,090,262 output tokens across 12 OpenRouter providers.  The
  provider union contains no Groq-only route.

The graph arm had the heaviest observed tail: 327 recorded physical attempts
for 254 telemetry rows and roughly 27,593 summed request-seconds, compared with
298/257 and 23,056 seconds for flat.  This occurred even though graph needed
far less padding (mean 18.79 whitespace words) than flat.  Typed serialization
therefore appears to induce more elaborate/slow output behavior; it is a
deployability endpoint and potential selection-on-success mechanism, not merely
technical noise to erase.

The complete immutable cache is checksummed in
`E6_typed_event_graph_RAW.tar.gz`.
