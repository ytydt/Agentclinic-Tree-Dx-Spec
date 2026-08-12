# E5 — candidate-set interference, typed distractors and nested width

## Question and design

Does a source-blind selector satisfy candidate independence, or can changing
only the candidate set alter its choice among candidates whose text and IDs
remain unchanged?

The frozen development sample has 200 cases (DA 100, MCR 100). Every base
pool contains four natural source options, including one safe-exact
gold option and three outcome-blind selected non-gold options. A target-blind
DeepSeek-v4-flash selector saw the clean vignette and arbitrary candidate IDs;
it never saw the gold flag, source option letter, perturbation relation, prior
rank, or architecture provenance.

Nine arms changed only candidate membership:

- `base4`;
- remove one outcome-blind non-gold option (`remove_non_gold3`);
- add one frozen parent, sibling, unrelated, synonym, or component label;
- add two or four separately generated plausible complete alternatives,
  yielding nested widths 6 and 8.

The four width candidates were generated once before selector calls. Width 6
uses a stable two-candidate prefix and width 8 adds the remaining two. Shared
candidate labels, IDs and relative order are byte-stable. Primary endpoint is
**safe-exact（历史字段 `strict`）** top-1. The runner computes it with
`FrozenExactSynonymBridge.equivalent`: normalized equality or a frozen,
collision-filtered synonym/own-initialism equivalence, never substring or fuzzy
resolution. It is a high-precision label-identity lower bound, not an estimate
of exhaustive clinical correctness. This is a mechanism/development study,
not a confirmation cohort.

## Execution and missingness

The perturbation builder returned a schema-valid nine-label construction for
166/200 cases (DA 90, MCR 76). Thirty-three failures were semantic duplicates
between a width label and a typed/base label; one returned the wrong number of
typed labels. These failures were retained and every dependent arm failed
closed. Selector schema failures removed one additional sibling case, one
synonym case and two width-8 cases. Base and removal served all 200.

| Arm | Served | Safe-exact top-1 / 200 ITA | ITA 95% Wilson | Safe-exact among served |
|---|---:|---:|---:|---:|
| Base width 4 | 200 | 136 (68.0%) | 61.2–74.1% | 68.0% |
| Remove one | 200 | 152 (76.0%) | 69.6–81.4% | 76.0% |
| Add parent | 166 | 96 (48.0%) | 41.2–54.9% | 57.8% |
| Add sibling | 165 | 92 (46.0%) | 39.2–52.9% | 55.8% |
| Add unrelated | 166 | 106 (53.0%) | 46.1–59.8% | 63.9% |
| Add synonym | 165 | 109 (54.5%) | 47.6–61.3% | 66.1% |
| Add component | 166 | 110 (55.0%) | 48.1–61.7% | 66.3% |
| Nested width 6 | 166 | 96 (48.0%) | 41.2–54.9% | 57.8% |
| Nested width 8 | 164 | 82 (41.0%) | 34.4–47.9% | 50.0% |

The ITA column deliberately counts failed conditions as not correct. Causal
contrasts below use successful pairs and state their denominator.

## Preregistered paired results

The eight all-case base contrasts are one preregistered family. Raw McNemar
p-values and Holm-adjusted p-values are both shown.

| Right arm vs base | Paired n | Harms / gains | Safe-exact delta | Paired bootstrap 95% CI | Raw p | Holm p |
|---|---:|---:|---:|---:|---:|---:|
| Remove one | 200 | 13 / 29 | +8.00pp | +2.00 to +14.50pp | .01952 | .11712 |
| Add parent | 166 | 24 / 10 | −8.43pp | −15.06 to −1.81pp | .02431 | .12153 |
| Add sibling | 165 | 25 / 7 | **−10.91pp** | −17.58 to −4.24pp | .00210 | **.01472** |
| Add unrelated | 166 | 16 / 12 | −2.41pp | −8.43 to +3.61pp | .57159 | 1.0 |
| Add synonym | 165 | 20 / 19 | −0.61pp | −7.88 to +7.27pp | 1.0 | 1.0 |
| Add component | 166 | 15 / 15 | 0.00pp | −6.63 to +6.63pp | 1.0 | 1.0 |
| Nested width 6 | 166 | 24 / 10 | −8.43pp | −15.06 to −1.81pp | .02431 | .12153 |
| Nested width 8 | 164 | 33 / 6 | **−16.46pp** | −23.17 to −9.15pp | .0000143 | **.000114** |

Only sibling injection and width 8 survive the eight-comparison correction.
The removal, parent and width-6 directions remain useful mechanism signals,
but they are not corrected-positive primary findings.

Width 6 to width 8 is the separate preregistered nested-width diagnostic:
19 harms versus 6 gains among 164 common pairs, −7.93pp (bootstrap 95% CI
−14.02 to −2.44pp; exact p=.01463). Mean gold rank worsens by 0.567 positions
(95% bootstrap +0.366 to +0.780), while self-reported top-1 probability changes
by only −0.21pp (95% CI −3.05 to +2.54pp). The selector therefore becomes
less gold-concordant without recognizing a corresponding confidence loss.

## Independence is falsified, but “more/fewer is always better” is also false

Removing one fixed non-gold candidate changes the champion in 50/200 cases.
It directly removes the prior champion in 23 cases: 18 become safe-exact rescues,
but five remain wrong. Eleven additional gains occur even though the removed
candidate was not the old champion. Conversely, 13 cases lose the safe-exact gold
after a non-gold candidate is removed. Thus both safe-exact IIA and casewise
monotonic “fewer candidates is safer” are falsified. The average removal
effect is favorable, but it is neither universal nor corrected-positive.

Adding candidates produces two separable mechanisms:

| Arm | Champion flips | New candidate champions | Direct new-candidate harms | Shared-candidate context harms | Safe-exact gains |
|---|---:|---:|---:|---:|---:|
| Parent | 44 | 13 | 8 | 16 | 10 |
| Sibling | 44 | 18 | 13 | 12 | 7 |
| Unrelated | 36 | 8 | 6 | 10 | 12 |
| Synonym | 44 | 12 | 11 | 9 | 19 |
| Component | 39 | 15 | 10 | 5 | 15 |
| Width 6 | 48 | 22 | 13 | 11 | 10 |
| Width 8 | 56 | 35 | 23 | 10 | 6 |

“Direct” means the added candidate becomes champion. “Context” means the
added candidate does not win, but its presence changes which shared base
candidate wins. Width 8's 33 safe-exact harms are therefore not simply 33 decoy
captures: 23 are direct and ten are set-induced reordering among unchanged
base candidates. Candidate-set context is itself causally active.

## DA and MCR fail through different mechanisms

The aggregate width effect hides a strong family interaction.

- For MCR, base-to-width-8 is 20 harms/2 gains (−24.0pp, p=.000121).
  All 20 harms are direct alternative capture; a width candidate becomes
  champion in 29/75 served cases. Parent, sibling, unrelated and component
  direct harms are likewise concentrated in MCR.
- For DA, base-to-width-8 is 13 harms/4 gains (−10.11pp, p=.0490). Only three
  harms are direct captures; ten are shared-candidate reordering. No injected
  parent or unrelated label becomes DA champion at all.
- Width 6 to 8 is 7/0 in DA (p=.0156) and 12/6 in MCR (p=.2379). The equal
  approximate net delta arises from different transitions: DA adds unstable
  context, while MCR admits clinically plausible alternatives directly.

This aligns with the option topology. DA base pools often contain several
granularity variants or near-duplicate descriptions of one trajectory. Added
labels perturb their internal ordering. MCR pools more often contain distinct
diseases, so a plausible new disease can directly displace the gold. Results
must not be pooled into one generic “distractor susceptibility” coefficient.

## Manual semantic audit changes the interpretation

The primary analyst manually reviewed 339 frozen judgments: all 180 labels in
the outcome-blind 20-case construction sample, every one of 111 unique typed
or width labels that became an injected champion, and a stable 48-transition
sample (three context harms and three gains per arm where available). No
external LLM adjudication was accepted as ground truth.

Only 134/180 (74.4%) sampled construction labels fully satisfy the requested
semantic role; 34 are partial, 11 invalid and one uncertain. Parent labels are
20/20 valid. The weak points are direction-sensitive:

- synonyms: 13 valid, 4 partial, 2 invalid, 1 uncertain;
- components: 13 valid, 1 partial, 6 invalid, commonly because a child subtype
  was mislabeled as a component;
- width candidates: 56/80 valid, 21 partial and 3 invalid;
- one width label duplicated typed ADEM after only the parenthetical acronym
  changed, proving surface deduplication is insufficient.

Selection amplifies these faults. Of 15 component labels that win, only six
are valid components, one is partial and eight reverse the direction or name a
different entity. Examples include *keratinizing SCC*, *monophasic synovial
sarcoma* and *trabecular juvenile ossifying fibroma*: these are more specific
child diagnoses, not incomplete components. The apparent zero average effect
of the component arm is therefore not evidence that component competition is
safe; the manipulation itself is semantically mixed.

The frozen bridge recognizes only 2/166 generated synonyms. None of the 12
synonyms that becomes champion receives safe-exact credit. Manual review finds
nine fully equivalent and three partially equivalent. Keeping the safe-exact
endpoint unchanged, a conservative semantic sensitivity that credits only the
nine clear equivalents changes the synonym contrast from −0.61pp (20/19) to
**+4.85pp** (11/19, p=.2005). Crediting the three partial equivalents yields
+6.67pp (9/20, p=.0614). The safe-exact null is primarily a synonym-bridge failure,
not evidence that equivalent labels destabilize clinical choice.

The 24 sampled context harms contain only three clear switches to a competing
diagnosis. Fourteen are compatible underspecification, incomplete composites,
near-equivalents or reframings; five are non-diagnostic/source-surface
artifacts; two depend on which timepoint or lesion is being asked about. All
24 sampled gains are switches back to the exact frozen target. Safe-exact scoring
therefore asymmetrically makes gains look clinically clean and many harms look
worse than they are. It remains a reproducible endpoint, but not a complete
clinical-loss measure.

The manual clinical audit contains 339 explicit judgments: all 180 labels in
the frozen 20-case construction sample, all 111 unique injected labels that
became champions, and a frozen 48-transition mechanism sample. It is exhaustive
for those objects, not for every output or every safe-exact transition across
the nine arms. In particular, unreviewed safe-exact-negative rows cannot be
treated as clinical negatives, and the synonym sensitivity is a targeted
mechanism analysis rather than a replacement whole-experiment clinical score.

## Order integrity and a residual position mechanism

Across 1,358 successful base-to-arm comparisons, shared labels are identical
and shared relative order fails zero times. All 164 width-6/width-8 pairs are
proper nested supersets with exactly two added candidates and zero shared-order
failures. Pool mutation, not accidental text rewriting, causes the changes.

Absolute positions necessarily shift when hash-ordered candidates are added.
A post-hoc, within-arm permutation diagnostic over the five single-injection
arms finds that injected champions occur at mean position 2.55 versus 3.05
when not champion (66/828 injections; two-sided p=.00564 while preserving each
arm's champion count). DA and MCR strata point in the same direction but are
not individually significant (.082 and .070). Conditional on a width
distractor winning, width-8 champions also occur earlier than the available
distractor mean (difference −0.72 positions, p=.055 overall); the DA subset is
−2.58 positions over only six events (p=.0124).

This is not a randomized position arm and is explicitly post-hoc. Candidate
semantics can correlate with position by chance, and the width test conditions
on winning. Nevertheless, the evidence rejects a confident claim that the
selector fully obeys “IDs and order are arbitrary.” Candidate membership and
serial position jointly contribute to interference; a future production
selector should compare typed candidates in a permutation-invariant or
set-aggregation stage.

## Common-complete and runtime checks

All nine arms succeed on the same 162 cases (DA 87, MCR 75). Restricting to
this common set preserves the main deltas: removal +8.64pp, parent −9.26pp,
sibling −11.11pp, unrelated −3.70pp, synonym −1.23pp, component −1.23pp,
width 6 −8.64pp and width 8 −16.67pp. Differential schema failure does not
generate the reported pattern.

The experiment records 1,753 semantic calls, 2,207 physical attempts, at
least 1.43M input and 6.11M output tokens, and 110,261 aggregate call-seconds.
Telemetry misses several successful selector results in recovered/older arms,
so these are lower bounds. Construction alone uses 2.03M output tokens and
427 physical attempts for 200 semantic calls. Twenty-two providers appear
across telemetry; routing is not Groq-only. The environment lacks the official
`openai`, `httpx` and `requests` packages, so the standard-library OpenRouter
transport ran; the code retains the official OpenAI SDK path behind an
environment switch. Monetary cost cannot be reconstructed because provider
price was not captured.

## Verdict

E5 decisively falsifies candidate independence. It also shows why a single
accuracy delta is too coarse:

1. sibling-like and larger plausible pools cause real alternative capture,
   especially in MCR;
2. additions and removals also reorder unchanged candidates, especially the
   near-duplicate/composite DA pools;
3. serial position remains a plausible secondary mechanism;
4. frozen safe-exact scoring overstates many granularity losses and entirely
   misses most genuine synonym selections;
5. typed perturbation builders need audited direction and semantic
   deduplication before component/synonym effects can be interpreted cleanly.

The production implication is not merely “use fewer candidates.” It is to use
typed, safely deduplicated candidates; preserve the requested diagnostic
object; aggregate evidence without list-position dependence; and perform an
explicit scope-aware comparison before final selection. `MANUAL_AUDIT.md`
contains the case-level dissections and complete review accounting.
