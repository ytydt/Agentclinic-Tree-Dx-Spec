# E7b — fresh blinded selector over registry counterfactuals

## Verdict

E7b supports exact/frozen-synonym identity as a **safety and addressability
invariant**, but not as a stand-alone top-1 cure. On the 299 trajectories where
E7a found at least one unsafe substring fold, exact identity:

- eliminated all selected-concept identity contamination (160 to 0);
- increased the displayed gold label's candidate exposure from 23 to 33
  (11 paired restorations versus 1 loss; exact McNemar `p=0.00635`);
- changed the displayed champion in 158/299 cases (52.8%);
- increased safe-exact displayed-label top-1 from 18 to 21, but with only 8 paired
  gains versus 5 losses (`p=0.581`), so no accuracy claim is warranted.

Adding generic non-equivalence relations changed 45/299 champions but produced
no safe-exact top-1 gains and one loss relative to exact identity. The case audit
shows why: undirected warnings do not specify whether the requested object is
an etiology, manifestation, complication, parent, subtype or complete
composition. RCR-3 therefore needs typed directional relations and an explicit
task-projection check, not merely more relation text.

## Frozen design

- Population: all 299 E7a unsafe-fold development cases plus 101 stable-SHA
  controls.
- Arms: production-compatible `legacy_substring`, `exact_synonym`, and
  `typed_relation` (exact identity plus explicit non-equivalence edges).
- `legacy_substring` is the **registry-construction treatment name**, not the
  historical `legacy-chain` scoring endpoint. All three arms are scored by
  the same displayed-label safe-exact bridge; hidden registry members and
  downstream task/mapper credit do not enter the primary endpoint.
- Per arm, the selector saw a clean vignette, neutral candidate IDs, displayed
  labels, up to three support spans and two contradiction spans. It did not see
  gold labels, benchmark options, previous scores, source views, registry arm
  names or old ranks.
- Candidate ordering was stable-SHA by case and normalized label.
- Model: `deepseek/deepseek-v4-flash-0731`; 50 non-RAG workers; official OpenAI
  SDK transport through OpenRouter.
- Primary endpoint: **safe-exact（历史字段 `strict`）** match on the
  **displayed champion label** before mapper intervention. The implementation
  calls `FrozenExactSynonymBridge.equivalent`: normalized equality or a frozen,
  collision-filtered synonym/own-initialism equivalence, with no substring or
  fuzzy fallback. It is an arm-invariant identity lower bound, not clinical
  completeness.
- Failures remained in the intention-to-analyse ledger and were not imputed.

The 800 source trajectories are development/mechanism data, not an independent
confirmation cohort.

## Result table

### All 400 selected cases

| Arm | Served | Safe-exact displayed-gold exposure | Safe-exact displayed top-1 | Hidden-member top-1 | Registry-credit leaks | Contaminated champions |
|---|---:|---:|---:|---:|---:|---:|
| Legacy substring | 399/400 | 33 (8.27%) | 25 (6.27%) | 35 | 10 | 160 |
| Exact synonym | 399/400 | 43 (10.78%) | 28 (7.02%) | 28 | 0 | 0 |
| Typed relation | 399/400 | 43 (10.78%) | 27 (6.77%) | 27 | 0 | 0 |

One unique invalid response belonged to a payload that was byte-identical in
all three arms; the single-flight analysis propagates that one failure equally,
so there is no differential attrition.

### Unsafe-fold stratum (primary mechanism stratum, n=299)

| Comparison | Left-only success | Right-only success | Exact McNemar p | Champion-label flips |
|---|---:|---:|---:|---:|
| Exact vs legacy — displayed gold exposure | 11 | 1 | 0.00635 | 158 |
| Exact vs legacy — displayed top-1 | 8 | 5 | 0.58105 | 158 |
| Typed vs exact — displayed gold exposure | 0 | 0 | 1.0 | 45 |
| Typed vs exact — displayed top-1 | 0 | 1 | 1.0 | 45 |

The 101 unaffected controls had identical candidate counts, zero contamination
and zero corrected champion flips across all arms. This negative control is
important: after enforcing one response per identical payload, observed flips
are confined to actual treatment differences.

## Causal mechanism decomposition

### 1. Registration changes the state space

Exact identity exposed an average of 1.04 additional candidates per unsafe
case. Across all 400 cases, the exact-minus-legacy candidate-count distribution
was: 167 unchanged, 169 `+1`, 51 `+2`, 12 `+3`, and 1 `+4`. Controls were all
zero. This reproduces E7a's offline finding that substring folds erase
separately addressable concepts.

### 2. Legacy evidence transfer is not benign compression

Legacy selected 160 identity-contaminated concepts among 299 affected cases
(53.5%). In 59 of those cases the displayed label was unchanged from the exact
arm, so a surface-only final-answer comparison would miss the contamination.
The unsafe registry can therefore preserve the same headline while changing
which entity receives support, contradiction and score mass.

### 3. Exact identity improves addressability

The displayed benchmark label was available in 33 exact pools versus 23 legacy
pools in the unsafe stratum. There were 11 exact-only exposures and one
legacy-only exposure. The single legacy-only case (`MCR_seq200b/364`) illustrates
the tradeoff: splitting concepts increased pool pressure and displaced acute
interstitial nephritis from the fixed-width exact frontier. Thus safe identity
must be paired with width/residual controls; the correct response is not to
restore unsafe merging.

### 4. Top-1 conversion remains the bottleneck

Exact identity recovered three net displayed-label top-1 cases, but the paired
evidence is weak. DA is especially coverage-limited: only four exact pools
exposed the gold label, so its 96 champion flips cannot improve safe-exact accuracy
unless proposal completeness improves first. MCR has better exposure, yet its
discordances are dominated by parent/subtype resolution and task projection.

### 5. Registry-member credit created a false legacy advantage

The initial diagnostic endpoint counted a legacy champion correct whenever any
hidden merged member matched gold. That produced 35 apparent legacy hits versus
28 exact hits and would have yielded the wrong scientific conclusion. Ten of
the 35 legacy member-level hits (28.6%) did not match the displayed champion at
all. Once the arm-invariant displayed-label endpoint was enforced, the result
became 25 legacy versus 28 exact and non-significant.

This is not a cosmetic metric choice. In three audited cases the legacy and
exact selector displayed exactly the same words, but only legacy received gold
credit because its hidden concept contained the benchmark string. An endpoint
whose definition changes with the treatment cannot identify a treatment
effect.

## Typed-relation arm

Exact and typed arms had identical candidate sets. Generic non-equivalence
edges were present in 289 evaluable cases and changed 45 champions (15.6%).
They yielded no safe-exact gains and one loss. Two cases are especially diagnostic:

- `MCR_seq200b/326`: exact correctly selects Brucellosis; typed selects its
  spinal epidural abscess complication.
- `MCR_v2_seq100/159`: exact selects the dissemination mechanism; typed selects
  grade-3 endometrioid adenocarcinoma, clinically improving task projection,
  but the safe-exact bridge gives neither label-identity credit.

The arm therefore falsifies the claim that a generic “these labels are not
equivalent” warning is enough. Direction and object type must be represented:
`etiology_of`, `manifestation_of`, `complication_of`, `parent_of`, `sibling_of`,
and `component_of`, followed by a complete-diagnosis projection.

## Counterfactual-consistency and endpoint corrections

The original 1200-condition run contained 981 unique blinded payloads. Before a
single-flight lock was added, byte-identical arms could call the routed model
concurrently and receive different samples. Raw rows and their surface-endpoint
reanalysis are preserved in:

- `case_conditions_raw_concurrent.jsonl`;
- `case_conditions_raw_concurrent_surface_endpoint.jsonl`;
- `summary_raw_concurrent.json`.

Using the final cache record per byte-identical key is independent of gold and
arm. It reduced exact-versus-legacy flips from 176 to 158 and typed-versus-exact
flips from 60 to 45. The main conclusions are robust: exact exposure advantage
is unchanged; displayed top-1 remains non-significant; typed relations add no
safe-exact benefit. Future runs use an in-process per-key single-flight lock.

Clinical audit coverage is explicitly limited to all 40 cases in the frozen
priority queue: all 13 exact-versus-legacy safe-exact top-1 discordances, the
one additional typed-versus-exact discordance, and 26 mechanism-priority cases.
The remaining 360 selected cases were not exhaustively adjudicated for clinical
equivalence. Consequently, an unreviewed safe-exact miss is not a clinical
negative, and the 40-case audit explains registry/ranking mechanisms without
converting the 400-case surface table into a clinical-complete leaderboard.
No E2 replay value is inserted into these E7b outputs.

## Runtime and payload audit

- 1200 condition rows; 1199 telemetry rows; 1198 parsed-success telemetry rows.
- 1321 physical attempts for 1199 logged semantic calls (1.102 attempts/call).
- 95 telemetry rows required more than one physical attempt; maximum 11.
- Parse attempts: 1191 first-pass, 6 second-pass, 1 third-pass, 1 terminal
  unparsed response.
- 1,288,125 input tokens and 3,999,129 output tokens (5,287,254 total).
- Mean summed semantic latency 61.7 s; percentile details are in
  `telemetry_diagnostics.json`.
- 25 OpenRouter providers participated. All logged transports were
  `openai_sdk`; zero payloads exposed an options block.

The telemetry/condition difference of one row is retained as a logging coverage
gap. No billed-cost estimate is invented because routed providers had different
prices and no authoritative billed amount was returned.

## Falsifiable conclusions

| Claim | Result |
|---|---|
| Substring identity causes clinically unsafe non-synonym folding. | Supported by E7a and 160 contaminated selected concepts in E7b. |
| Exact identity restores separately addressable candidates. | Supported: +1.04 candidates/unsafe case and 11 vs 1 paired exposure restorations. |
| Exact identity alone improves safe-exact top-1. | Not supported: 8 vs 5 paired gains/losses, `p=0.581`. |
| Generic non-equivalence edges improve ranking. | Falsified in this form: 0 gains, 1 loss relative to exact. |
| Legacy's hidden-member gold credit is a valid accuracy endpoint. | Falsified: 10 credit leaks and treatment-dependent scoring. |

## Design consequences

1. Keep exact/frozen-synonym identity as a hard safety invariant.
2. Compensate for the expanded safe registry with residual-orthogonal proposal
   batching and an explicit width experiment (E12), not unsafe compression.
3. Replace generic relation warnings with typed directional relations and an
   explicit requested-object projection (RCR-3 Calls 1–3).
4. Separate displayed-label safe-exact accuracy, clinical completeness, parent/
   subtype relations, component completeness and mapper rescue (E2).
5. Audit internal concept membership and evidence transfer even when the final
   displayed label is unchanged.
