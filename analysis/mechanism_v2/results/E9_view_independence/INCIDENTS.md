# E9 incidents and execution caveats

## I001 — `real_views` transport long tails

The full three-view payload arm completed 400/400 validated result rows, but
many physical attempts returned `finish_reason=length` or reached the 180 s
per-attempt timeout before the repository client recovered through its frozen
retry path. This is retained as cost and latency evidence; no provider, retry,
prompt, worker count or result was changed during the arm.

The captured telemetry routes across multiple OpenRouter providers (including
DeepInfra, Inceptron, Cloudflare, SiliconFlow and Io Net), not a Groq
single-provider route. The API credential was operational.

## I002 — three missing per-call telemetry records

`real_views` has 400 validated immutable response cache records and 400 result
rows, but only 397 per-call telemetry records. The missing telemetry cases are
listed in the arm's `provenance.json`. Their validated responses remain
available and are retained in the estimand; token, physical-attempt and
provider totals are explicitly lower bounds and are not reconstructed or
imputed. No call is repeated merely to repair transport accounting.

The corresponding `role_rotated` arm has 400 validated cache/result rows and
392 telemetry records. Its eight missing case IDs are likewise frozen in that
arm's provenance. This larger metadata gap changes neither response validity
nor the paired endpoint, but it prevents exact arm-to-arm cost attribution;
reported token and physical-attempt differences are lower-bound descriptions.

`single_anchor` similarly completed 400 validated cache/result rows with 398
telemetry records; its two missing IDs are in provenance. Across all arms,
response validity is checked from the immutable cache and result row, while
transport accounting is independently reconciled and never silently assumed
complete.

## I003 — one preregistered schema failure in `duplicate_anchor`

`MCR_seq200b/285` returned four decisive evidence IDs although the frozen
schema permits at most three. The content explicitly described V2 and V3 as
the “same findings repeated,” which is useful evidence that the model noticed
the duplication, but the row remains an invalid/failed response. It is not
trimmed, repaired, retried or imputed. The paired repetition contrast therefore
has 399 double-served cases and the intention-to-analyse arm has 399/400 served.

This case had only one modality-view candidate and no strict frozen-synonym
reference exposure (`Pycnodysostosis` vs the generated `Pyknodysostosis`), so
the schema failure does not turn a locally exposed reference hit into a miss;
that observation does not excuse or remove the failure.

## I004 — heterogeneous semantic-auditor partition failures

The target-blind Gemini semantic clustering subcontractor served 387/400
cases. Thirteen outputs failed the exact-partition contract: nine duplicated
observation IDs, three omitted at least one ID, and one invented an unknown ID.
All 400 raw cache records are retained; failed clusters are excluded from
aggregate semantic-overlap metrics and are not repaired or imputed. One of 400
transport telemetry records is also absent and is listed in semantic-audit
provenance. Root manual review remains authoritative over the subcontractor's
valid-looking merges as well as these explicit failures.
