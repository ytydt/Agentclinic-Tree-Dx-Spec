# E4 — fixed-pool selector crossover

## Question and design

Does the selector itself explain trajectory differences after candidate
generation is held fixed?

Four fresh LLM selectors and one deterministic control received the same 400
clean vignettes (DA 200, MCR 200), the same source-blind canonical pool, the
same candidate IDs/order, and the same merged support/contradiction table.
Pools were the exact-synonym-deduplicated union of the e7 pre-selector
shortlist, live Forest registry and active APHHM-C registry, capped at ten by a
frozen outcome-blind rule. Previous champions, ranks, scores, votes, source
names, answer options and gold labels were withheld.

Primary endpoint: exact-or-frozen-synonym pre-mapper top-1. The benchmark is
development/mechanism data, not confirmation.

## Primary results

| Selector | Strict top-1 | 95% Wilson interval | Top-1 among 62 strictly exposed | 95% Wilson interval |
|---|---:|---:|---:|---:|
| Evidence-count control | 17/400 (4.25%) | 2.67–6.70% | 17/62 (27.4%) | 17.9–39.6% |
| e7 contrast | 33/400 (8.25%) | 5.93–11.36% | 33/62 (53.2%) | 41.0–65.1% |
| Forest evidence integration | **41/400 (10.25%)** | 7.65–13.61% | **41/62 (66.1%)** | 53.7–76.7% |
| APHHM-C obligation ledger | 37/400 (9.25%) | 6.79–12.49% | 37/62 (59.7%) | 47.3–71.0% |
| Pairwise tournament | 38/400 (9.50%) | 7.00–12.77% | 38/62 (61.3%) | 48.8–72.4% |

Forest versus e7 is 9 strict gains and one loss: +2.0 percentage points,
paired bootstrap 95% interval +0.5 to +3.5pp, exact McNemar p=0.021484375.
The difference is entirely MCR (38/200 versus 30/200, +4.0pp); DA is tied at
3/200 because only seven DA cases are strictly exposed.

Other online contrasts are not significant:

- Forest versus ledger: 6/2 exclusive wins, +1.0pp (p=0.2891);
- Forest versus tournament: 6/3, +0.75pp (p=0.5078);
- tournament versus e7: 8/3, +1.25pp (p=0.2266);
- tournament versus ledger: 4/3, +0.25pp (p=1.0).

## Exposure is the limiting transition

| Exposure stage | All | DA | MCR |
|---|---:|---:|---:|
| e7 frontier strict hit | 46 | 3 | 43 |
| Forest frontier strict hit | 44 | 3 | 41 |
| APHHM-C frontier strict hit | 46 | 3 | 43 |
| Uncapped union strict hit | 63 | 7 | 56 |
| Width-10 union strict hit | 62 | 7 | 55 |
| Unsafe substring-related label (diagnostic only) | 197 | 114 | 83 |

The cap loses one strict gold, so width ten does not explain the 338 strict
non-exposures. DA gold labels often encode cause, stage, complication and
trajectory while candidates name a component or parent disease. Substring
containment therefore exposes ontology/identifiability tension but is unsafe
as accuracy credit. The clean E2 adjudication is required before treating DA
strict recall as clinical completeness.

## Mechanism findings

Online prompts change 23.8–29.3% of champions pairwise while showing no strong
candidate-position skew. Their selected source-provenance mixtures are also
similar despite source identities being hidden. The selector instruction is a
real causal component.

Manual review of all 17 strict-endpoint discordances decomposes Forest's nine
strict gains over e7 into five strong clinical-mechanism gains, one plausible
but under-confirmed specificity gain, and three spelling/alias/target-scope
artifacts. Its one loss is a real task-scope overshoot (answering SLE instead of
nonbacterial thrombotic endocarditis). Forest's useful mechanism is therefore
high-specificity evidence integration, not generic verbosity or source voting.

The ledger shows both sides of explicit obligations: it rescues longitudinal
ERG and Kawasaki-criteria cases, but over-vetoes seronegative autoimmune
gastritis. The tournament produces one clear morphology rescue but does not
beat Forest and introduces under/over-specific label choices.

## Runtime and implementation audit

All 1,600 online conditions ultimately returned schema-valid results. The
minimal image lacks the official `openai` package, so the production client
used its standard-library OpenRouter transport. The code retains the official
OpenAI SDK path and selects transport by environment.

Telemetry is incomplete by 1–3 rows per arm; totals below are lower bounds:

| Arm | Recorded semantic | Physical attempts | Output tokens | Aggregate latency (s) |
|---|---:|---:|---:|---:|
| e7 | 398 | 561 | 930,887 | 26,888.5 |
| Forest | 399 | 489 | 1,427,708 | 39,825.4 |
| Ledger | 397 | 458 | 1,192,353 | 33,195.2 |
| Tournament | 397 | 509 | 1,607,448 | 47,071.6 |

The e7 arm had a documented initial import failure and a 2048-token-cap tail
incident before cache-resumed completion; its cost is not directly comparable.
Under the same 8192 ceiling, the tournament costs more than the ledger and
does not improve accuracy. Provider routing was multi-provider; no Llama arm
used a Groq-only route.

## Verdict

E4 passes as a selector-mechanism experiment with important qualifications.
It supports Forest-style evidence integration over e7 contrast on the exposed
MCR subset, rejects evidence-count selection, and fails to support exhaustive
pairwise comparison as a default. It does **not** establish a complete Forest
architecture advantage, clinical completeness on DA, or confirmation-set
generalization. The dominant trajectory failure is still loss or mismatch of
the requested diagnostic object before selection.

See `MANUAL_AUDIT.md` for the complete 17-case transition audit, the 12-case
all-wrong flip audit, and the threat-to-inference analysis.
