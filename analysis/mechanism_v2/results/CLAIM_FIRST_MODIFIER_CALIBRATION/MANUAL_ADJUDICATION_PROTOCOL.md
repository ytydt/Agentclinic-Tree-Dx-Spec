# Assistant manual/root correction protocol

Declared 2026-08-19 before manual corrections are written.

The user explicitly authorized the assistant to perform the manual annotation
task and to consult the web for uncertain medical terminology. This is recorded
as **assistant manual/root correction**, not as an independent human clinician
and not as human ground truth.

## Blind boundary

The correction reads only:

- frozen `case_key`;
- `reference_diagnosis`;
- candidate IDs and labels; and
- the reference-only construction output.

It must not read the vignette, reviewer availability responses,
`per_claim.jsonl`, agreement values or analysis summaries while deciding the
decomposition. Web searches may be used only to resolve the meaning or
hierarchical status of a diagnosis term.

## Rules

1. Select one base disease entity as the core.
2. Bind the core to the closest supplied candidate only when the candidate is
   the same base entity; broader parents and narrower modified forms are not
   exact core bindings.
3. Place every additional commitment explicitly expressed in the reference on
   one of the six frozen axes:
   `etiology`, `anatomy`, `time_stage`, `subtype`, `complication`,
   `composite_components`.
4. Do not repeat the core name as a modifier.
5. Preserve separate commitments as separate claims even when they share an
   axis.
6. If the reference is already a bare disease entity, use zero claims.
7. Record a short rationale and any consulted URL.

Five parallel initial reviews cover disjoint ten-case blocks. The parent
assistant performs final consistency review and owns every accepted row.

## Use boundary

Corrected decompositions replace model construction only for recompiling the
50 claim cards. Changed cards receive new immutable availability payload hashes;
unchanged cards reuse their existing caches. This correction may calibrate the
availability instrument, but it is still not independent clinician truth and
must carry that caveat in every downstream claim.
