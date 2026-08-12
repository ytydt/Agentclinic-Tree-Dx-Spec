# RCR-3 `lite3_safe` run audit

The frozen 300-case arm completed with 296 served cases.  Intention-to-analyse
strict Top-1 was 16/300, strict Top-2 24/300, and the exact/frozen-safe-synonym
reference entered both the raw registry and bounded frontier in 37/300 cases.
Mean registry and frontier sizes were 4.9733 and 4.9667 respectively.

All four fail-closed cases were schema violations after a valid provider
response: three selectors emitted an unsupported `completeness` value and one
generator emitted an unsupported `candidate_type`.  They remain errors in the
300-case denominator and were not silently resampled.  The telemetry contains
899 actual semantic calls and 900 physical attempts; the one extra attempt was
a JSON parse/output-cap retry.  Aggregate usage was 1,096,933 input and 348,170
output tokens, with 15,012.22 summed provider-latency seconds.

Routing was not Groq-only: 442 completed responses report Groq and 457 report
DeepInfra.  All calls used the environment-managed network route and the
dependency-free OpenRouter fallback because this image lacks the official
`openai`, `httpx`, and `requests` packages.  The shared client still preserves
the environment-selectable official OpenAI SDK branch.  No credential is
present in the stage files, logs, telemetry, manifest, or raw archive.
