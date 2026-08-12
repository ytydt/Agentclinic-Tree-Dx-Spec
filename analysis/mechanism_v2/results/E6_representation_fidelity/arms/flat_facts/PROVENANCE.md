# E6 arm: flat facts

- Selector: `deepseek/deepseek-v4-flash-0731`, temperature 0, 50 non-RAG
  workers, target-blind payload.
- Attempted rows: 300; builder-eligible calls: 258; schema-valid selector
  responses: 255 (124 DA, 131 MCR).
- Strict exact-or-frozen-synonym differential recall: 6/255; strict top-1:
  3/255 (all MCR).
- Fail-closed rows: 42 preregistered construction failures plus three
  champion/runner ordering violations.  All 258 called-response caches are
  retained; 257 telemetry rows make the ledger a lower bound.
- Recorded lower bound: 257 semantic calls, 298 physical attempts, 441,830
  input tokens and 892,258 output tokens across 13 OpenRouter providers.  The
  provider union contains no Groq-only route.

The planned whitespace-word control is exact per successful case, but it is
not model-token exact: flat facts require a mean 128.46 repeated
`[LENGTH_CONTROL_PAD]` words, and that marker splits into multiple DeepSeek
tokens.  Recorded input tokens per physical attempt are therefore about 1,483
for flat versus 768 for raw.  This is a treatment-correlated attention/latency
confound even though contexts remain far below the model limit.  It will be
tested separately and prevents an unqualified causal attribution to
representation structure alone.

The complete immutable cache is checksummed in `E6_flat_facts_RAW.tar.gz`.
