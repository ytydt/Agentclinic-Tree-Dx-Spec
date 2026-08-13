# Canonical endpoint migration protocol for the 79-arm gap

## Scope

This migration closes the canonical **Top-1 measurement** gap identified at
source commit `6ed5ccc02caec2550e0b625915a649ad5738e473`. It covers the 79
registered non-E2, non-structural arms in E1, E4, E5, E6, E6x, E7b, E7c, E8,
E9, E10, E11, E12, E14x, and RCR3.

The frozen intention ledger contains 24,076 arm-case rows. A valid pre-mapper
Top-1 is present in 23,035 rows; the other 1,041 rows are technical failures
and remain failures in the intention-to-analyse endpoint. Endpoint migration
does not invent a prediction for them.

## Canonical endpoint contract

The frozen contract defines six non-interchangeable fields. The first five are
fully replayable from the frozen outputs and completed clinical census; `task`
requires a separate external evaluator and therefore also carries an explicit
evaluation-status field:

1. `safe_exact`: deterministic exact or frozen-safe-synonym identity;
2. `legacy_chain`: the historical substring/resolver projection, diagnostic
   only;
3. `clinical_complete`: candidate is the full requested diagnostic object;
4. `compatible_partial`: compatible parent/component/underspecified relation,
   mutually exclusive with complete;
5. `complete_or_compatible_partial`: secondary coverage union;
6. `task`: family-specific benchmark interface outcome—DA option mapper or
   MCR Prompt-7 semantic judge. DA and MCR task rates are never pooled as one
   homogeneous clinical estimand.

## Clinical relation census

The 23,035 served occurrences collapse to 5,344 unique
`(case_key, normalized_prediction)` relations.

- 1,693 relations reuse an exact-normalized E2 root decision;
- 251 additional relations are deterministic frozen-safe identities;
- 3,400 genuinely new relations in 628 cases require adjudication.

All 751 cases are members of the E2 800-case identity census, so reference
identifiability is reused without re-review.

The new relation cards reveal only the original clinical record, benchmark
reference, and neutrally numbered candidates. Experiment, arm, endpoint,
historical proxy, safe/legacy/task status, case key, and sentinel status are
withheld. Candidate order is deterministically shuffled.

Three heterogeneous reviewers independently classify every candidate as
`C/P/X/M/N/U`. Each card embeds up to two hidden E2 root relations as
calibration sentinels. Sentinel truth is joined only after all reviews finish.
Unanimous votes, 2/3 majorities, and three-way splits are retained respectively
as `three_model_unanimous_proxy`, `model_majority_proxy`, and
`model_unresolved_proxy`; a three-way split remains `U` rather than being
silently forced to a clinical category. A fourth blinded model arbitration was
specified as an optional sensitivity layer but was not used in the final census
after the authorized external API returned an insufficient-credit error.

This yields an exhaustive **blinded model-panel census**, not a human-root
census. Model unanimity and model majority are never relabelled
`root_adjudicated`. The strict root-only capability leaderboard therefore
remains limited to E2 even when all 79 metric-migration gaps are closed.

## Task replay

Historical task booleans are not reused: the E2 artifacts contain contradictory
task outcomes for byte-identical case-prediction inputs. A new cache namespace
freezes one evaluator function.

- DA: 11,564 served occurrences collapse to 2,972 unique case-prediction
  mapper payloads. The source options and clinical record are visible; the
  gold option is withheld until the projection is complete and joined offline.
- MCR: 11,471 served occurrences collapse to 2,860 unique
  predicted/actual-diagnosis Prompt-7 payloads.

Thus 5,832 unique task inputs replace 23,035 arm-specific historical outcomes.
The authorized API completed 3,337 fresh payloads before returning an
insufficient-credit error; 2,495 remain `not_evaluable` in this commit. The
partial completion is non-random, so observed task rates are reported only with
coverage denominators and are not used for paired inference. Historical task
values are not copied and missing fresh values are not imputed.

## Inference

All confirmatory contrasts preserve the experiment's frozen pairing and
predeclared contrast families. Unserved rows score zero in the primary ITA
analysis; served-only rates are sensitivity summaries. Exact McNemar tests and
paired case-bootstrap intervals use the case as the analysis unit. Holm
adjustment is applied within experiment × predeclared contrast family × scope
× endpoint. Incomplete task results are excluded from confirmatory inference.
E12 retains its 39-comparison factorial family and independent
two-comparison depth family; E11 retains seven contrasts; RCR3 retains three.

The migration upgrades Top-1 outcome measurement. It does **not** automatically
upgrade candidate-pool exposure, selector-capture, or trajectory mechanism
proxies; those require separate candidate-registry relation censuses.
