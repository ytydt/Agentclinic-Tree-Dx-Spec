# Pre-analysis operational correction: exact claim coverage

Declared after the first availability transport run but **before `analyse` was
called and before any agreement or headroom value was computed**.

The first run exposed a response-format defect:

- Gemini returned 47/50 schema-valid cards. All three failures were cases with
  zero frozen claims; instead of returning `{"claims":[]}`, it invented between
  1 and 100 claim IDs.
- Claude returned 37/50 schema-valid cards. Twelve failures returned only
  `M01` when two to four frozen claims were supplied; one returned no `claims`
  array.

This is exact-universe coverage failure, not an availability disagreement. The
following correction is applied symmetrically before analysis:

1. Add immutable `expected_claim_ids` and `expected_claim_count` fields to every
   payload and explicitly require all IDs exactly once. If uncertain, the model
   must return `not_determinable`, not omit the claim.
2. A zero-claim card is resolved deterministically to `{"claims":[]}` without a
   provider call. There is no clinical judgment to make on such a card.
3. Re-run both reviewers under the corrected byte-identical instruction. The
   prompt and payload change creates new immutable cache identities.
4. Preserve every prior `reviews.jsonl` and summary under a SHA-named history
   path before replacement.

No availability response, agreement statistic or endpoint value was inspected
to choose this correction. Only expected-versus-returned claim IDs and schema
errors were examined. The reliability thresholds and fail-closed grounding rule
remain unchanged.
