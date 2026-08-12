# E14x retrospective runtime-gate utility analysis plan

Status: frozen before case-level outcome joins are computed by the E14x
analysis script.  Aggregate performance of the historical runs was already
published, so this is explicitly exploratory rather than a prospective
preregistration.

## Scientific question

Does the fourth `ORTHOGONAL_GENERATE` call in MOSAIC-Adaptive-4v2 concentrate
on trajectories where a new candidate can repair a generation or conversion
failure, or does it mainly add a noisy candidate to already adequate pools?
The analysis separates candidate discovery, registry survival, selector
conversion, and final endpoint change.  It does not infer utility merely from
the aggregate score of the adaptive arm.

## Frozen population and arms

- Historical paired MOSAIC-Lite and MOSAIC-Adaptive-4v2 runs on the same 100
  cases in each of `diagnosisarena`, `medcasereasoning`, and
  `medcasereasoning_v2` (maximum intention-to-analyse n=300).
- A secondary historical comparison uses Adaptive-4 on DiagnosisArena and
  MedCaseReasoning (maximum n=200) only to diagnose why the original permissive
  gate was replaced.  It is not pooled with the primary comparison.
- Missing or malformed records remain in an attrition table.  No case is
  silently removed.

## Identity and comparability checks

For every paired case, canonical JSON hashes are computed separately for G1,
G2, and the state immediately after G1/G2.  The primary treatment-like subset
requires exact equality of G1 and G2 payloads across Lite and Adaptive-4v2.
Results on non-identical upstream trajectories are descriptive associations
only.  The analysis also checks whether non-triggered cases have identical
selector payloads and outputs; disagreement there is direct evidence that the
comparison contains sampling/runtime variation beyond the gate.

## Endpoints

The following rules are fixed before the outcome join:

1. **Gate coverage and cost:** activation rate and added calls, overall and by
   dataset.
2. **Discovery:** A1 introduces a label absent from the post-G1/G2 registry.
3. **Reference discovery:** a newly introduced A1 label matches the frozen
   exact-or-synonym reference bridge.  This is evaluated only where the local
   case bank provides a reference label.
4. **Survival/exposure:** each A1-only concept survives in the final registry
   and appears in the selector frontier/payload.
5. **Conversion:** an A1-only concept becomes champion; reference-discovering
   A1 becomes the final strict champion.
6. **Strict final endpoint:** champion exact-or-frozen-synonym equivalence to
   the reference label.  DA option projection is reported separately from
   concept strictness and is never pooled with MCR judge scores.
7. **Paired change:** Lite-only correct, Adaptive-only correct, exact McNemar
   p-value, and deterministic 10,000-replicate paired case-bootstrap interval
   for Adaptive minus Lite.  These are stratified by gate activation and
   upstream-identity status.
8. **Gate discrimination:** pre-gate features (`unexplained_n`, generator
   Jaccard, top margin, top-1 disagreement, leave-one-view instability, and
   contradiction mass) are related to observed repair/harm among triggered
   cases.  Threshold search is descriptive; no threshold selected here is
   called confirmed.
9. **Mechanism accounting:** every strict flip is assigned to one of new-label
   discovery, pre-existing-label reranking, mapper/projection-only change,
   upstream mismatch, or unresolved.  All strict flips and every A1 champion
   enter a root manual audit queue.

## Interpretation contract

- The gate decision was deterministic within Adaptive-4v2 but treatment was
  not randomized; triggered and non-triggered strata differ by construction.
- Historical selector calls may be stochastic.  Exact upstream equality is
  necessary but not sufficient for causal identification.
- MCR LLM-judge aggregate accuracy is retained as historical provenance only
  unless per-case judge records are present.  It is not reconstructed or mixed
  with exact reference matching.
- No extra LLM call is made in E14x.  This directly follows the user's
  exclusion of variance-only repeated runs and the source register's
  inferential downgrade.
- Root manual adjudication, not a model-generated narrative, owns all clinical
  mechanism labels used in the report.

## Falsifiers

The proposed Call-4 gate is not supported if any of the following dominates:

- reference discovery is rare and most A1 champions were already present;
- gains arise primarily from reranking existing candidates rather than the
  orthogonal call's new information;
- reference-discovering A1 concepts routinely fail to survive/expose/convert;
- triggered strict harms equal or exceed gains without a pre-gate feature that
  separates them; or
- non-triggered/upstream-identical cases show substantial output churn,
  demonstrating that historical paired differences cannot isolate the gate.

