# E6 arm-blinded semantic adjudication provenance

- Status: explicitly posthoc sensitivity analysis; the preregistered strict
  exact-or-frozen-synonym endpoint remains unchanged and separately reported.
- Auditor: `google/gemini-2.5-flash`, different model family from the DeepSeek
  selector.  Output order is deterministic-randomized and arm identities are
  absent from every auditor payload.
- Cases: 300 records; 298 external response records are schema-valid, one case
  with no successful selector output was locally skipped, and one external
  response failed closed because `vignette_consistency` was outside the frozen
  enum.  There are no auditor `uncertain` categories among valid rows.
- Raw cache: 299 immutable external responses; telemetry has 297 rows across
  the concurrent write boundary.  Recorded lower bounds are 297 semantic and
  physical attempts, 266,117 input tokens, 123,855 output tokens and 2,017.63
  summed request-seconds, all routed through Google.
- Manual-review queue: every one of 64 cases with an auditor complete-
  equivalence discordance plus a frozen 30-case concordant sample (94 unique
  cases).  External judgments remain subcontractor evidence until this review
  is complete.

`E6_SEMANTIC_ADJUDICATION_RAW.tar.gz` contains all immutable response-cache
objects; the adjacent manifest verifies its SHA-256.
