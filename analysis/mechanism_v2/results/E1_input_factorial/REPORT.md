# E1 — input visibility × format factorial

## Question and design

Do source answer options contaminate the input-sensitive diagnostic stage, and
does input organization modulate that contamination?

A frozen outcome-blind sample of 200 development cases (DA 100, MCR 100) was
run through two one-call micro-pipelines: a hierarchical family→diagnosis
builder/selector (**H**) and a flat independent-differential builder/selector
(**F**). Each received four inputs: clean/fixed, clean/reordered clinical
blocks, options/fixed, and options with reordered clinical blocks plus an
arbitrary-label appendix. The prompt, model, sample, endpoint bridge and code
were fixed before online execution. Each of the eight 200-case arms was
committed separately.

This deliberately probes the input-sensitive stage. It is not the full
multi-call production APHHM or AB02 runtime and cannot establish an end-to-end
architecture ranking.

Primary endpoint: **safe-exact（历史字段 `strict`）** pre-mapper top-1. The
implementation calls `FrozenExactSynonymBridge.equivalent`: normalized surface
equality plus a frozen, collision-filtered synonym dictionary (and a narrowly
defined full-name/own-initialism rule), with no substring or fuzzy resolver
tier. Raw candidate recall, option copying, candidate-set instability, failures
and runtime are mechanism endpoints. Invalid responses remain failures in
intention-to-analyse (ITA) arm totals; paired contrasts require both conditions
to be valid. Safe-exact is a reproducible high-precision lower bound, not a
clinical-completeness endpoint.

## Arm results

| Architecture / condition | Served | Raw gold recall (ITA) | Safe-exact top-1 (ITA) | Mean candidate option-copy among served | Champion copied an option | Output tokens |
|---|---:|---:|---:|---:|---:|---:|
| H clean fixed | 189/200 | 22/200 | 16/200 | 5.6% | 28/189 | 1,181,395 |
| H clean reordered | 189/200 | 21/200 | 17/200 | 5.2% | 29/189 | 1,208,051 |
| H options fixed | 187/200 | **129/200** | **94/200** | **47.6%** | **119/187** | 619,385 |
| H options reordered | 176/200 | 84/200 | 58/200 | 30.9% | 74/176 | 1,264,072 |
| F clean fixed | 200/200 | 20/200 | 13/200 | 7.0% | 23/200 | 540,694 |
| F clean reordered | 199/200 | 19/200 | 11/200 | 5.5% | 17/199 | 569,618 |
| F options fixed | 199/200 | **125/200** | **93/200** | **48.2%** | **124/199** | 300,510 |
| F options reordered | 199/200 | 106/200 | 74/200 | 38.9% | 92/199 | 396,021 |

The conventional fixed options condition roughly halves output tokens relative
to clean H and reduces them 44% for F. This is consistent with visible labels
collapsing generative search, not merely improving a downstream choice.

## Paired causal contrasts

Positive deltas favor the right-hand condition. Confidence intervals are
case-bootstrap percentile intervals; p values are exact two-sided McNemar.

| Architecture | Contrast | Comparable | Gains / harms | Safe-exact top-1 delta | 95% CI | p |
|---|---|---:|---:|---:|---:|---:|
| H | options fixed − clean fixed | 178 | 75 / 2 | **+41.0pp** | +33.1 to +48.3 | 3.98e-20 |
| H | options reordered − clean reordered | 168 | 47 / 8 | **+23.2pp** | +15.5 to +31.0 | 8.07e-8 |
| H | clean reordered − clean fixed | 180 | 9 / 8 | +0.6pp | -3.9 to +5.0 | 1.0 |
| H | options reordered − options fixed | 167 | 9 / 35 | **-15.6pp** | -23.4 to -7.8 | 1.06e-4 |
| F | options fixed − clean fixed | 199 | 82 / 2 | **+40.2pp** | +33.2 to +47.2 | 3.69e-22 |
| F | options reordered − clean reordered | 198 | 64 / 1 | **+31.8pp** | +25.3 to +38.9 | 3.58e-18 |
| F | clean reordered − clean fixed | 199 | 4 / 6 | -1.0pp | -4.0 to +2.0 | .754 |
| F | options reordered − options fixed | 198 | 14 / 34 | **-10.1pp** | -17.2 to -3.5 | .0055 |

The preregistered visibility-by-format interaction is +16.2pp for H (154
complete cases; 95% CI +6.5 to +26.0) and +9.1pp for F (197; +1.5 to +16.8).
Because the reordered condition also changes clinical paragraph order, these
are input-organization interactions, not pure option-position estimates.

The fixed visibility effect appears in both datasets but is larger on DA:

| Architecture | DA gains / harms; delta | MCR gains / harms; delta |
|---|---:|---:|
| H | 45 / 0; +47.4pp | 30 / 2; +33.7pp |
| F | 52 / 1; +51.0pp | 30 / 1; +29.3pp |

## Mechanism findings

### Visible options alter generation, not just ranking

Under fixed format, raw gold recall has 106 H gains versus 4 harms and 107 F
gains versus 2 harms. Candidate option-copy rates rise by about 42 percentage
points in both architectures, while champion copying rises from 14.8% to 63.6%
among served H cases and 11.5% to 62.3% for F. The candidate set itself is
therefore contaminated before champion selection.

### Safe-exact improvement mixes clinical rescue and endpoint alignment

Manual review of all four fixed harms and 18 mechanism-stratified transitions
finds real rescues (histiocytoid Sweet syndrome, PAPT, tricuspid valve
aneurysm, MHIBCC), direct spelling/expansion repairs, compound-label supply,
parent/component substitutions, and two credible distractor harms. One H harm
is simply `Cohen syndrome` versus `Cohen综合征`; one F harm is fibrous dysplasia
versus its monostotic subtype. Safe-exact accuracy therefore both under-credits
clinical equivalence and overstates independent reasoning when the exact
source label is visible.

The clinical review covered all 4/4 fixed-format safe-exact harms and a frozen
mechanism sample of 18 additional transitions. It did **not** clinically
adjudicate every output or every safe-exact miss in the eight arms. Unreviewed
safe-exact-negative rows are therefore lexical lower-bound misses of unknown
clinical status, not demonstrated clinical errors. The reviewed cases explain
which mechanisms can generate the aggregate effect; they do not turn the
remaining experiment into an exhaustive clinical leaderboard.

### Format changes trajectories even when aggregate accuracy does not move

Clean reordering flips 133/180 H champions and 165/199 F champions while mean
candidate-set Jaccard falls to 0.180 and 0.132. Net safe-exact accuracy remains near
zero because gains and harms cancel at a low floor. Aggregate top-1 equality is
thus compatible with wholesale case-level trajectory replacement.

### Hierarchical execution is fragile in this micro-pipeline

H has 11, 11, 13 and 24 invalid outputs across its four arms, mostly failure
to return the required 3–8 L2 candidates. F has 0, 1, 1 and 1. H also uses
roughly two to three times F's output tokens under corresponding conditions,
without higher clean safe-exact accuracy. This is evidence about these prompts and
schema burden, not about full APHHM.

## Runtime and provenance

The eight arms made 1,597 recorded semantic calls and 2,191 physical attempts.
The environment lacked the official `openai` package, so the environment-
selected standard-library transport executed the calls; the official OpenAI
SDK path remains in the code. Routing used 14–18 providers per arm and did not
use a Groq-only Llama route. There were no credential, credit or rate-limit
failures. The supplied OpenRouter key was usable.

The final arm wrote complete results before the outer execution channel lost
its polling approval; no case was lost or rerun. Schema-invalid rows remain in
the ITA artifacts. See `INCIDENTS.md` and the per-arm raw archives/logs.

## Verdict

E1 passes as a causal mechanism experiment and rejects three simple stories:

1. answer options are not a harmless display layer—they enter candidate
   generation and champion selection;
2. the option effect is not content-only—it is materially shaped by input
   organization;
3. similar aggregate accuracy does not imply similar diagnostic trajectories.

It does **not** show a 40-point gain in independent clinical reasoning, because
the safe-exact endpoint mixes substantive rescue with exact-label supply and
ontology alignment. It also does not compare complete production architectures. The
actionable design requirement is to keep source options outside generative
reasoning, preserve the requested diagnostic object explicitly, and evaluate
clinical completeness separately from exact label agreement.

See `MANUAL_AUDIT.md` for the case-level decomposition and limitations.

## Canonical Top-1 migration addendum (2026-08-13)

The exhaustive 79-arm replay now supplies a blinded three-reviewer **model-panel**
clinical relation for every served Top-1; it is not human-root truth. In the
200-case ITA, exposing options raises clinical-complete by 39.0 pp for flat
fixed input (87 gain/9 loss, Holm `q=2.55e-16`) and 42.0 pp for hierarchical
fixed input (90/6, `q=2.00e-19`); C∪P rises 27.0 pp in both. This strengthens,
rather than rehabilitates, the contamination conclusion: option-bearing arms
are not clean architecture comparisons. Shuffling option blocks additionally
harms hierarchical clinical-complete by 11.0 pp (17/39, `q=.01825`). Historical
safe-exact and the targeted 22-transition audit remain mechanism evidence only.
The fresh task replay is incomplete and is not used for inference.
