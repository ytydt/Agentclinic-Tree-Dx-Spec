# Final report factual review

Reviewer: `source_inventory_2`. Scope: generated `REPORT.md` and `build_report.py` against `census_metrics.json`, `error_dimension_metrics.json`, `raw_group_census.json`, frozen/source/output review records, the semantic casebook and the prior 11-case MRR/targeted-ablation artifacts. No primary code or judgments changed by this reviewer.

The current report’s principal numeric claims agree with the saved metrics. No change to the headline estimates is needed from this review.

## Verified

- Source denominator: 64 windows, 286 frozen whole-rule units, 272 adjudicable and 14 ambiguous, including 14 zero-rule windows.
- Old/new source counts: 26/117/129 versus 31/112/129 faithful/distorted/omitted; new weighted rates 15.6769%, 42.1897%, 42.1334%; all-source ambiguity 3.6989%.
- New weighted faithful CI 9.2653–22.9792%; paired faithful delta 3.0685 percentage points with CI −0.5997 to +6.6031. Pair-transition counts match the prose.
- Structure table sums to 272. The 7 flat + 16 nested/domain/conditional + 1 score = 24 observed units have zero strict complete source-rule success. The report appropriately refuses a universal zero-capability conclusion and distinguishes these source units from independently sampled output groups.
- Flat-schema-exact subset: 194 units, 28 new faithful, weighted fidelity 19.5460%. By-source integer tables match.
- Output: 120 atoms and 60 groups; faithful54/12, distorted58/45, traceable non-target8/3, no untraceable or unresolved units. Weighted fidelity44.5779%, distortion48.7836%, non-target6.6385%.
- Atomic/group faithful Wilson intervals agree with the report. The separately implemented zero-event Clopper–Pearson/Bonferroni upper bound is 3.644189%, correctly reported as approximately3.64% with accurate-label and nonzero-uncertainty caveats. It is distinct from the approximate Wilson bound4.080943% in the methodological comparison.
- Every displayed output-error dimension matches the standardized metric. The source112 distorted units split into22 partial/scope-only and90 others exactly as stated; the report does not call scope-only harmless.
- All v2 raw-group census table entries agree: 694/562 groups, mixed relations19/25, subjects12/14, logic0/1, n0/2, singleton26/26, negative-member13/17, threshold98/99, invalid/missing logic22/6.
- The fixed8 source-review windows contain exactly70 source units. The cross-review files contain16+16=32 unique output units, exactly the union of24 prespecified units and11 initially faithful groups. The two additional output calibrations are recorded separately.
- Removing the three new-arm modality overrides lowers source faithful weighted rate to14.1744%, agreeing with14.17%. The two soft-group sensitivity items reduce12/60 to10/60=16.67%.
- The prior four-arm proxy MRR values0.4273/0.4132/0.3667/0.3071 match the earlier report. Targeted removal restores CPVT to rank1 in both v2 arms; global removal leaves it rank2 behind LQTS. The current report correctly declines to treat these proxy ranks as clinical-complete accuracy or causal percentages for all11 cases.

## Factual/provenance corrections communicated to root

1. **Earliest damage statement:** “原始缓存能证明错误首次出现在生成边界” is too broad. Raw caches establish that an error already exists by raw output; the source or title parser may be the earlier first damage, as O1-011 itself demonstrates. Suggested replacement: “原始缓存可证明错误在生成输出中已存在；首次损坏仍须与实际输入和上游来源对照定位。”

2. **Modality-review count:** The extra review covers five **arm-level judgments across three source rules**, not five paired source-rule judgments: S1-01-R01 old/new, S1-04-R01 old/new, S1-09-R02 new. Say “5项臂级判断” or explicitly “3条源规则的5项臂级判断（两条旧/新配对，另1条新臂）”. The sensitivity calculation itself is correct.

3. **Invalid-enum denominator:** The820 invalid-relation and1,571 invalid-context records are among35,189 valid assertion rows, including grouped member rows. “有效原子行” can be confused with the32,725 ungrouped atomic-unit denominator. Suggested wording: “有效断言行（含组成员）”. This is denominator disambiguation, not a numeric change.

4. **Ablation index namespace:** The removed index1017 belongs to case74’s merged assertion list in `trial_extraction_x2_v2idxclean_groups*.json`, not a local per-cache raw index as used in the new `source_matches` files. Specify “病例74合并断言列表中的索引1017（非单次cache局部行号）”. The intervention and resulting rankings are correct.

The root agent was notified during review so these wording corrections can be applied in the report generator and regenerated report. They do not affect sampling, adjudication labels or the headline statistics.
