# E6 arm: raw vignette

- Selector: `deepseek/deepseek-v4-flash-0731`, temperature 0, 50 non-RAG
  workers, target-blind payload.
- Attempted: 300; schema-valid responses: 293 (148 DA, 145 MCR).
- Strict exact-or-frozen-synonym differential recall: 6/293; strict top-1:
  4/293 (one DA, three MCR).
- Fail-closed responses: six champion/runner ordering violations and one
  non-list `missing_or_uncertain` field.  All 300 immutable response caches are
  retained; 298 telemetry rows make the token/call ledger a lower bound.
- Recorded lower bound: 298 semantic calls, 367 physical attempts, 281,653
  input tokens and 1,122,533 output tokens across 13 OpenRouter providers.
  The provider union contains no Groq-only route.

The extremely sparse strict score is a lexical endpoint limitation for free
diagnosis generation: labels that add compatible anatomy, stage or complication
text do not pass the frozen exact bridge.  It is retained as preregistered and
will be accompanied by an arm-blinded semantic-equivalence adjudication and
manual trajectory audit; no relaxed match is substituted into this arm file.
The complete cache is checksummed in `E6_raw_vignette_RAW.tar.gz`.
