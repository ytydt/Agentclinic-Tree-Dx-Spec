# E9 preregistration — Forest view independence

Status: design frozen before any E9 online call.

## Question and causal contrasts

Forest's historical three generators are separate, history-isolated calls: each
receives only the same clean vignette. The proposed “independent no-history”
condition is therefore the real-view condition itself and is not relabeled as a
new arm.

The frozen E4 sample (200 DA + 200 MCR) is used. Four fresh-selector arms form
two strict controlled contrasts:

1. `real_views` vs `role_rotated`: identical candidate registry, evidence,
   assessments, block order and model; only the declared syndrome/mechanism/
   modality role names are cyclically rotated.
2. `single_anchor` vs `duplicate_anchor`: identical candidate registry and one
   outcome-blind, family-balanced anchor view; the duplicate arm repeats the
   exact anchor content under all three role names.

`single_anchor` vs `real_views` estimates the joint value of additional
independent content. Because the candidate registry can expand, this contrast
will be decomposed into reference capture and selection conditional on shared
capture. It is not interpreted as a selector-only effect.

## Frozen hypotheses

- H1: If role names materially drive decisions, rotating only those names will
  cause non-trivial champion flips and directional accuracy changes.
- H2: If apparent agreement is repetition voting, exact anchor triplication will
  change champions relative to one copy despite adding no information.
- H3: If heterogeneous content is useful, real views will improve reference
  capture over the balanced anchor and some gains will trace to view-unique
  candidates/evidence rather than replicated support.
- H4: If the axes are mostly cosmetic, candidate and semantic-evidence overlap
  will be high and real views will add little beyond the anchor.

## Endpoints and safeguards

Primary endpoints are paired exact-or-frozen-synonym pre-mapper top-1,
champion flips, and exact McNemar tests for H1/H2; H3 is split into capture gain
and conditional conversion. Secondary endpoints are candidate Jaccard,
view-unique reference capture, exact evidence overlap, a heterogeneous-model
semantic evidence-cluster audit, and root manual adjudication of enriched
discordances.

Gold/options, old champions, generator identity, scores, ranks, votes and arm
names are withheld from all calls. Failed or schema-invalid calls remain
intention-to-analyse failures and are never imputed. This is a development
mechanism experiment, not a confirmation result. Repeat runs, new confirmation
sets and provider/retry standardisation are deliberately outside scope.
