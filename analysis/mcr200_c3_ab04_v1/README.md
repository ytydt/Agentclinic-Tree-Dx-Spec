# Internal memo: the MCR N=200 expansion refutes the joint-equivalence-removal claim

**Disposition: internal only. Must not enter the Supplementary Material.**
Date 2026-07-31. Complete: all four cells of the 2×2 on both slices, all three endpoints of
the published caliber, projection defect fixed and verified.
Slice 1 = `mcr_val_seq100_v1` (published), slice 2 = `mcr_val_seq100_v2` (new, non-overlapping).
Reproduce: `PYTHONPATH=src:scripts:scripts/paper python3 scripts/paper/check_mcr200_c3_ab04.py`

## 0. Disposition and why

The main text is frozen by the submission system. The standing rule is that an expansion
may enter the Supplementary Material only if it does not contradict the frozen main text.

**This expansion contradicts it, on two independent grounds.** The abstract
(`paper_aaai/main.tex:52`) and §C2 (`main.tex:457`) report that jointly disabling
concept-equivalence handling lowers MedCaseReasoning top-1 accuracy from 0.50 to 0.42. On
the fresh slice the sign reverses, and with the projections rebuilt the reversal now covers
all three endpoints of the published caliber (§1). Separately, the same abstract sentence's
"56.5% of candidates" is a cross-convention comparison that overstates the compression
effect on distinct concepts by roughly sixfold (§5) — and that one applies to slice 1 as
published, not just to the expansion.

No partial write-up rescues this: the corroborating half of the 2×2 (§3) cannot be shown
without also showing the joint cell, and showing only the favourable half would be selective
reporting — a worse liability than silence. Nothing from this expansion was written into
`main.tex` or into either supplementary file.

What follows is for the next research cycle, not for this submission.

## 1. The refutation

Caliber: `official_eval_llm_compat`, top-1 `diagnostic_hit` — the path that produces the
paper's headline MCR accuracy (deployed slice 1 = 0.500, matching the site table's
`llm_acc_at_1`). Complete on both slices; no pending judge calls.

**Confirmed at the published caliber, and on every endpoint.** The projection defect
described in §4 has since been fixed and the slice-2 site artifact rebuilt. It independently
reproduces the top-1 reversal (deployed 0.46, joint removal 0.50, discordance 6/10) and
shows that the reversal is not confined to top-1:

| endpoint | slice 1 | slice 2 | pooled n=197 |
|---|---|---|---|
| accuracy@1 | 0.50 vs 0.42, **10/0** | 0.46 vs 0.50, **6/10** | 16/10, Δ +0.031, p=0.33 |
| any-hit@5 | 0.58 vs 0.56, 7/4 | 0.61 vs 0.66, **5/10** | 12/14, Δ −0.010, p=0.85 |
| reciprocal rank@5 | 0.53 vs 0.478, 15/5 | 0.53 vs 0.571, **10/16** | 25/21, Δ +0.020, p=0.66 |

All three endpoints favour the deployed system on slice 1 and the joint-removal arm on
slice 2, and all three are null when pooled. Slice 2 produces no Holm survivors at all,
where slice 1 produced one. This closes the escape route flagged earlier in this memo: the
slot-waste mechanism predicts damage on the multi-slot endpoints, and those reverse too —
with *larger* discordance shifts than top-1.

| | deployed | both sites removed | Δ | discordant b/c | exact 95% CI | p |
|---|---|---|---|---|---|---|
| slice 1 (published) | 0.500 | 0.420 | **+0.080** | 10/2 | [+0.4, +11.5]pp | 0.039 |
| slice 2 (new) | 0.460 | **0.500** | **−0.040** | 6/10 | [−11.1, +4.7]pp | 0.455 |
| pooled N=200 | 0.480 | 0.460 | +0.020 | 16/12 | [−3.6, +7.1]pp | 0.572 |

This is a failure to demonstrate the effect, not a demonstration of equivalence: the pooled
interval still reaches +7.1pp, so it does not fit inside the ±5pp margin either. The
between-slice disagreement exceeds chance — Fisher exact on the discordant composition
[[10,2],[6,10]] gives p = 0.024 — so this is genuine slice heterogeneity rather than a
merely wider interval. `reasoning_recall` was skipped for these arms, so this caliber
speaks only to top-1.

## 2. It is not a configuration error

Worth ruling out first, because `c3_shared_no_dedupe_v1` is an empty directory on slice 2.
`c3_launch.json` matches across slices (`granularity_mode: off`,
`no_tree_semantic_dedupe: true`, 100 trees prepared, 100/100 annotate OK). Decisively, the
intervention lands *harder* on slice 2:

| | emitted candidates/case | lexical duplicate rate among emitted |
|---|---|---|
| deployed, slice 1 / slice 2 | 2.20 / 2.14 | 0.051 / 0.062 |
| both sites removed, slice 1 / slice 2 | 4.55 / 4.69 | 0.540 / 0.593 |

On slice 2 the ranking window is 59% restatements of a concept already present, and top-1
accuracy still rose. The manipulation is faithful; what fails to replicate is its top-1
consequence.

## 3. What the expansion does corroborate

Two things replicate cleanly, which is why the failure is diagnostic rather than merely
embarrassing.

**Single-site removal is harmless — now both cells, on both slices.** With the
routing-kept arm finished on slice 2, all four cells of the 2×2 are available:

| removed | slice 1 Δ (b/c) | slice 2 Δ (b/c) |
|---|---|---|
| routing only (build-time de-duplication kept) | +0.010 (2/1) | +0.010 (1/0) |
| build-time de-duplication only (routing kept) | 0.000 (4/4) | +0.010 (5/4) |
| both | **+0.080 (10/2)** | **−0.040 (6/10)** |

The main text's "removing either site alone leaves accuracy at 0.50" (`main.tex:458`) holds
in both cells on both slices. It is specifically the *interaction* — joint removal being
harmful — that fails, and it is the only cell that fails.

**Decision-time compression is free, on both slices.** The paired accuracy difference
between the deployed system and the routing-off arm is bounded to [−2.4,+2.9]pp on slice 1
and [−0.9,+1.0]pp on slice 2, and the candidate reduction reproduces (56.5% on slice 1,
58.8% on slice 2). So the **sufficiency** half of Contribution 2 survives as literally
stated, and only the **necessity** half collapses.

That said, the sufficiency claim carries much less information than the abstract's phrasing
implies, for a reason worth recording — see §5.

## 4. A projection defect that briefly faked the ranked endpoints — found, fixed, verified

Worth keeping on the record because it produced *plausible* wrong numbers rather than
obvious ones, and because it had already manufactured Holm-surviving contrasts.

The slice-2 site artifact first landed with the deployed arm's any-hit@5 at 0.74 (against
0.58 on slice 1) and its mean surviving candidates at 5.00 (against 2.02), with joint removal
apparently beating the deployed system everywhere. Cause: `eval_projection_compat`, which is
supposed to hold the compressed ranking, held the **pad variant's** content — the variant
that backfills each case from the wider candidate pool up to the ranking cap and which has
its own directory (`..._compat_then_pad`) on slice 1. The signature was unambiguous: slice 1
compat averaged 2.02 candidates with 4% of cases at the cap, slice 1 pad averaged 5.00 with
100% at the cap, and slice 2 compat averaged 5.00 with 100% at the cap. Slice 2 case 129's
deployed projection even contained the gold at rank 4 while that label appeared nowhere in
the deployed final ranking.

Three of the four arms read `eval_projection_compat` by name and were padded; the fourth
read its own precompat directory and was not, so the contaminated 2×2 was asymmetric as
well as inflated.

**Fixed in a separate session** (`pad_fix_rebuild_note.txt`): `ddx_from_compat_ranking` now
defaults to `pad_posterior=False` and only `compat_then_pad` pads; the three affected
projection directories and the site artifact were rebuilt without re-running annotation or
trees, and the polluted artifacts were quarantined under
`backups/mcr_v2_compat_proj_pad_pollution_20260731_103123`.

**Verified independently here.** The rebuilt slice 2 now matches the slice-1 convention, and
rank-1 agreement with the deployed ranking is complete throughout:

| | mean candidates | share at cap | rank-1 agreement |
|---|---|---|---|
| slice 1 deployed / routing-kept / both-removed | 2.02 / 1.81 / 2.11 | 0.04 / 0.02 / 0.04 | 98/98, 100/100, 99/99 |
| slice 2 deployed / routing-kept / both-removed | 1.88 / 1.77 / 1.91 | 0.03 / 0.02 / 0.04 | 99/99, 99/99, 100/100 |

Top-1 was never affected — backfill only appends below rank 1, which is why the §1 top-1
figures are identical before and after the fix. The ranked endpoints changed substantially,
and §1 now reports the corrected values. `check_mcr200_c3_ab04.py` carries this signature as
a standing guard so a padded slice cannot be silently compared against an unpadded one again.

## 5. The reported 56.5% compression is mostly removal of identical strings

This is new, it is not a bug, and it applies to slice 1 as published — so it bears on the
abstract independently of everything above.

The main text reports that decision-time compression removes 56.5% of surviving candidates,
4.64 → 2.02 per case (`main.tex:460`), and the abstract carries it as "semantic compression
removes 56.5% of candidates without reducing accuracy". The 4.64 baseline is the routing-off
arm read from its precompat projection; the 2.02 treatment is the deployed arm read from the
compat projection. Those two conventions differ in whether they retain lexically identical
labels:

| | slots/case | distinct labels/case | internal duplicate rate |
|---|---|---|---|
| slice 1 routing-off (the 4.64 baseline) | 4.64 | 2.22 | 0.520 |
| slice 1 deployed (the 2.02 treatment) | 2.02 | 2.02 | 0.000 |
| slice 2 routing-off | 4.56 | 1.97 | 0.567 |
| slice 2 deployed | 1.88 | 1.88 | 0.000 |

Measured on ranking slots the reduction is 56.5% (slice 1) and 58.8% (slice 2). Measured on
*distinct concepts* — the quantity that is invariant to the convention — it is **9.0%** and
**4.6%**. Between half and four fifths of the headline number is the disappearance of
strings that were already duplicates of a candidate present elsewhere in the list.

Two consequences.

First, the "without reducing accuracy" clause is close to arithmetically guaranteed rather
than empirically surprising: a slot holding a restatement of a neighbour cannot contribute a
distinct correct answer, so discarding it cannot cost any-hit@k. And indeed any-hit tracks
distinct-label count rather than slot count across both slices — 2.22 distinct → 0.5816 and
2.02 → 0.58 on slice 1; 1.97 → 0.6465 and 1.88 → 0.61 on slice 2, where compression's 4.6%
distinct-label loss shows up as a small any-hit loss exactly as it should.

Second, this is a cross-convention comparison, and the honest version of the claim is the
distinct-concept one. The efficiency statement survives — a user really does see 4.64 slots
without routing and 2.02 with it — but the *scientific* content, that merging genuine
semantic equivalence classes is free, is supported only over the 4.6–9.0% of distinct
labels, not over 56.5% of anything.

None of this is fixable by rerunning: it is a definitional issue in how the contrast was
framed. It should be restated on distinct concepts in any future version.

## 6. Caliber fragility that was already there

The published 10/0 (p=0.002) comes from a different scoring path
(`ablations_block2_site_rank_metrics.json`: stored projections plus the top-5 rank-metrics
judge cache, n=98). The headline caliber on the *same* slice gives 10/2 (p=0.039). The two
cases that flip (`41`, `30`) are both present in the projection set, so this is a
judge-path disagreement, not an exclusion artifact. Two cases move p by a factor of twenty,
and the published number was the more favourable of two defensible calibers. Any future
claim in this family must pre-declare one caliber before the arms are scored.

## 7. Fragility census: the paper's thinnest evidence is exactly what broke

Every directional claim in the main text, by paired discordance:

| claim | discordance | total | status |
|---|---|---|---|
| OX evidence-conditioned write-back (sign test) | 42/14 | 56 | robust |
| DA full-tree leaf injection is harmful | 39/9 | 48 | robust |
| DA case-adaptive vs random axis | 40/6 | 46 | robust |
| DA case-adaptive vs fixed taxonomy | 25/5 | 30 | robust |
| DA fixed taxonomy, nonempty-conditioned | 17/5 | 22 | thin, p=0.017 |
| DA random axis, nonempty-conditioned | 7/6 | 13 | already reported as largely null |
| **MCR joint equivalence removal** | **10/0** | **10** | **refuted at N=200** |

The claim that failed was the thinnest directional evidence in the paper by a factor of
two. That is not a coincidence and it is the transferable lesson: on a 100-case slice, a
directional claim resting on fewer than roughly fifteen discordant pairs has almost no
power against a 5–8pp true effect and a real chance of sign reversal. The next most
exposed item is the nonempty-conditioned fixed-taxonomy contrast (17/5, n=89, p=0.017);
everything at 30 or above has margin to spare.

A structural reason MCR produces thin evidence: deployed accuracy sits near 0.48 and the
arms differ by a handful of cases, whereas the DA organizational effects are 20–34pp. MCR
may simply be the wrong benchmark on which to stake an ablation.

## 8. Where the real load-bearing wall is

Ranked by evidence that survives scrutiny, the paper actually stands on three things, and
Contribution 2's necessity claim is not among them:

1. **Case-adaptive organization (C1).** DA top-1 0.37 → 0.71, discordance 40/6,
   p = 3.1×10⁻⁷, and the fixed-taxonomy arm emits *more* leaves (30.1 vs 17.8) while doing
   worse — so the gain is organization, not frontier size. Largest effect, largest
   discordance, and a built-in confound control. This is the wall.
2. **The write-back dissociation (C3).** Micro-F1 0.576 → 0.651 with a bootstrap interval
   excluding zero, while raising the evidence budget moves F1 by at most 0.008 and the
   interaction is −0.001. Its strength is the factorial: the effect is attributable to
   state consistency and demonstrably not to compute. Dissociations are much harder for a
   reviewer to attack than single contrasts.
3. **The harmful-intervention counterfactual (C4).** Injecting full-tree leaves raises
   coverage to 0.93 yet drops top-1 from 0.72 to 0.42 (39/9, p = 1.5×10⁻⁵). This carries
   the paper's actual insight — that an apparent recall gap can be an interface failure and
   that stage attribution must precede intervention — and it is the kind of negative result
   reviewers find credible precisely because it is unflattering.

Contribution 2 is, on current evidence, a *safety* result rather than a *necessity* result:
compression is a large, free reduction of the candidate set. That is publishable as stated
in the sufficiency clause; the necessity clause was overreach on an underpowered endpoint.

## 9. The mechanism story survived longer than the claim did, and why

The slot-waste mechanism — duplicates consume ranking slots, and top-1 occupies only one of
them — was the natural defence of the top-1 failure, and it made a testable prediction:
damage should appear on the multi-slot endpoints. With the projections rebuilt, that
prediction has been tested and it fails. Slice 2 reverses on any-hit@5 (5/10) and reciprocal
rank@5 (10/16) more decisively than on top-1 (6/10), and pooled all three are null (§1).

The reason is visible in §5. The joint-removal arm emits 4.69 candidates per case at a 59%
duplicate rate, but the scoring projection collapses identical strings before judging, so at
the interface it presents 1.91 distinct candidates against the deployed system's 1.88. The
manipulation is large in the pipeline and almost nil at the point of measurement. Slot waste
cannot be detected by an endpoint that never sees the wasted slots — which also explains why
the effect on slice 1 was small enough to be a coin flip in the first place.

Concrete next steps, cheapest first:

1. **Measure slot waste where it exists, not after the interface removes it.** Any endpoint
   computed from the compat projection is blind to lexical redundancy by construction. The
   quantity to report is the emitted ranking's redundancy (deployed 0.05–0.06 versus
   joint-removal 0.54–0.59, already computed and stable across both slices) together with a
   user-facing cost of the wasted slots. This is the one part of Contribution 2 that is
   large, replicated, and mechanistically unambiguous.
2. **Pre-declare a slot-sensitive primary endpoint.** Accuracy at k as a function of k, or
   accuracy normalised by effective discriminative width, tests the slot-waste mechanism
   directly instead of hoping it leaks into top-1. The supplementary M1/M2 machinery
   already computes effective width, so the metric exists.
3. **Move the equivalence ablation to DiagnosisArena.** No DA joint-removal arm exists —
   DA's `c3_ab01/ab02/ab03` are the organizational arms (fixed ICD, flat, random axis). DA
   is where effect sizes are 20–34pp and where thin discordance is not the binding
   constraint. Cost: a full C3-tier run (100 no-dedupe trees, annotate, mapper, eval),
   comparable to the MCR run just completed. This is the highest-value new experiment.
4. **Power the design before running it.** With b+c = 10 there was never power to resolve a
   5–8pp effect. Fix the endpoint and the caliber first, then size N to the discordance
   rate the pilot actually shows, rather than reporting whichever slice came out favourable.

## 10. Standing rules this episode justifies

- Pre-declare the scoring caliber before arms are scored; never choose between two
  defensible judge paths after seeing both (§6).
- Check the projection convention before comparing slices. Two runs of the "same" caliber
  differed by a silent backfill that inflated one slice's ranked endpoints while leaving
  top-1 intact — a failure mode that produces plausible numbers rather than obvious ones,
  and that had already manufactured Holm-surviving contrasts before anyone looked (§4).
- Treat any directional claim with fewer than ~15 discordant pairs on a 100-case slice as
  provisional, and do not promote it to the abstract (§7).
- State the endpoint the mechanism predicts, not the endpoint that happens to move (§9) —
  and check that the endpoint can still see the manipulation after the scoring interface has
  had its way with it (§5).
- Define reduction claims on quantities that are invariant to the projection convention.
  Comparing a duplicate-retaining baseline against a duplicate-removing treatment inflated a
  9% effect into a 56.5% headline (§5).
- Expansions that contradict a frozen main text stay internal; expansions that corroborate
  it may be written up. The asymmetry is uncomfortable but it is the frozen-text rule, not
  a scientific judgement — which is why this memo exists and is complete.
