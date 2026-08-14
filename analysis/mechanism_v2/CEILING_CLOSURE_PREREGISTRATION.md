# Recall–conversion ceiling closure: frozen protocol

> Frozen: 2026-08-14, before any case-bearing online call in this closure round
> Source state: `013f66cc9889d67975ac7e7fa7ebe2bb822a5111`
> Status: development mechanism study; not a deployment study

## 1. Purpose and ownership boundary

This round closes the six open items in
`RECALL_CONVERSION_CEILING_ROOT_CAUSE_ANALYSIS.md` §12 by either producing the
pre-specified measurement/experiment or recording a pre-specified No-Go. A
No-Go is a result, not permission to silently change the endpoint, sample or
gate.

The online reviewers available in this execution environment are models. Their
outputs will therefore be named **three-model adjudicated panel** throughout.
They do not create human provenance and must not be renamed `human-root`, even
when a third model adjudicates a disagreement. Existing E2 root decisions and
the frozen exact-synonym bridge retain their original provenance. Any result
that depends on new panel labels is a sensitivity/mechanism result and cannot
enter a root-only capability leaderboard.

The only calls made before this freeze were three empty-payload connectivity
probes, one per intended provider family. They contained no case, candidate,
reference, arm or outcome data and cannot affect selection or thresholds.

## 2. Shared measurement contract

- Unit of inference: case.
- DA and MCR are separate primary strata; `ALL` is descriptive unless a
  contrast is explicitly frozen below.
- Primary clinical endpoint: ITA clinical-complete Top-1. A failed or invalid
  call is incorrect, never deleted or imputed.
- Secondary endpoints: compatible-partial, C∪P, task, safe-exact, service,
  schema, latency and token cost. None may be renamed the primary endpoint.
- Pool exposure and selector conversion are reported only for an explicitly
  named decision surface: `raw_registry`, `effective_frontier` or
  `actual_payload`. An unrecoverable comparator request is `unknown`, not an
  inferred payload.
- Post-treatment common-served/common-exposed analyses are sensitivity only.
- Paired binary contrasts use exact McNemar tests and case bootstrap intervals.
  Each experiment has its own coherent Holm family; families are not pooled.
- Every ordered payload has its own immutable hash/cache identity. Candidate
  order is frozen by outcome-blind SHA ordering.
- Reviewers/selectors never receive arm names, historical winners, old
  endpoints or mapper results. Construction calls never receive the reference
  diagnosis or any `audit_is_gold` field.

## 3. C0: non-E2 full-pool exposure census and E5 transition review

### 3.1 Frozen universe

The census includes every recoverable candidate occurrence from:

1. the 14 arms used by the historical width OLS;
2. E4 fixed union pools;
3. every E5 comparator payload actually sent;
4. the four E9 payloads reconstructed byte-for-byte from committed Forest
   stages and checked against committed registry/payload hashes; and
5. E12 k5/k10 pools, with graph-unavailable rows explicitly marked as having
   no comparator opportunity.

The pre-call inventory is 19,599 unique `(case_key, normalized label)`
relations across 800 development cases. Existing E2 root decisions cover 2,601
of these and the frozen exact bridge covers a further 344; 16,781 require new
panel review. Occurrences remain separate so one semantic relation can be
projected back to every arm, pool layer and payload hash without pretending
that evidence fidelity is reusable.

The old width arms are frozen in at least two layers: 43,252 raw-registry slots
and 31,867 recoverable effective-frontier slots. The original request cache is
not treated as recoverable when it is absent. The historical OLS may be
recomputed descriptively on the named registry/frontier layers, but an
`actual_payload` coefficient is forbidden unless request provenance exists.

### 3.2 Panel and reliability gate

All relation cards are arm-blind and contain a clinical record, benchmark
reference and neutrally identified candidates. Three heterogeneous reviewers
run independently:

- A: `google/gemini-2.5-flash`;
- B: `anthropic/claude-sonnet-4.6`;
- C: `openai/gpt-5.6`.

Every candidate is judged C/P/X/M/N/U plus object/scope detail. E2 relations
embedded in the universe are hidden sentinels; existing root truth overrides
panel votes only after the panel files are frozen. New relations use the
three-reviewer majority; a three-way split remains U. No forced majority is
allowed.

The descriptive clinical-width analysis is released only if A/B complete-boundary
agreement is at least 90% with Gwet AC1 at least 0.75, fine-label agreement is
at least 80% with AC1 at least 0.60, total U is at most 5%, every
family-by-candidate-type cell has at most 10% U, and at least 95% of eligible
relations resolve to C/P/X/M/N. Failure produces a coverage/reliability audit
only. Regardless of those values, the result remains model-panel rather than
human-root.

E5 is scored on all served outputs, not a proxy-discordant sample. Primary
views are ITA, all-served-output, joint-nine base/width6/width8, DA/MCR and E2
reference-identifiability strata. This prevents verification bias from
reviewing only transitions selected by the old panel.

## 4. C1: qualified frontier plus residual ledger

Source: the frozen E4 union pool and candidate-specific evidence. All arms
share proposals, evidence and a fresh frozen comparator:

1. fixed-k control;
2. typed fixed-k;
3. evidence-qualified main frontier plus append-only residual ledger; and
4. outcome-blind, equal-width SHA sham.

Admission may use only exact source-grounded support, a non-shared decisive
span, an otherwise unexplained high-specificity finding, a required modifier,
or a low-prior candidate with unique high-specificity support. Vote count,
role repetition and free-form plausibility do not qualify. The main Go gate is:
complete exposure does not fall; treatment-predefined exposure retention and
net rescue are positive; catastrophic substitution does not exceed rescue; and
qualified beats equal-width sham. Otherwise the admission contract is No-Go.

## 5. C2: executable core/modifier factorization

Source: the frozen 200-case E5 base4 cohort (DA 100 primary, MCR 100 interaction
sensitivity). This is a gold-exposed conditional-conversion cohort and is never
reported as an overall recall experiment.

An outcome-blind factorizer sees only the vignette/question and shuffled opaque
candidate IDs/labels. The offline map gate requires zero known unsafe merges,
at least 95% pair precision, at least 85% modifier-axis validity and at most 10%
unresolved mappings. If it passes, five fresh arms share the comparator model:
flat labels, exact identity, executable lattice, singleton structure sham and
deterministically corrupted modifier mapping. The treatment cannot synthesize
a new answer; it must return an existing surface candidate ID. Go requires
clinical-complete gain beyond the structure sham, separation from corrupted
mapping, and more object/specificity rescue than scope compression, modifier
hallucination or catastrophic substitution. If C1 fails, C2 is explicitly an
isolated topology probe and cannot be promoted into the deployment pipeline.

## 6. C3: retrospective active-evidence benchmark

Source: E5 base4 only, used as a closed-pool, off-policy evidence-release
benchmark. A builder that cannot see gold/options/candidates extracts an
initial presentation and a menu of actually performed later actions/results.
Every released result must be an exact offset-backed span; final diagnoses,
titles, retrospective answer statements and historically unperformed tests are
forbidden. Historical absence is not a negative test.

Eligible cases require at least three legal actions and pass an independent
availability/leakage audit. Up to 64 cases are selected by pre-outcome SHA rank,
balanced 32/32 DA/MCR. If action availability, leakage or information-need
reliability fails, the benchmark is released as No-Go and no diagnostic-gain
arm is run.

If the gate passes, the frozen arms are no acquisition, deterministic
cost-matched random action and typed missing-discriminator action. The primary
endpoints are need-resolution precision/recall, action relevance and
information gain per cost; post-release clinical-complete transition is
secondary and limited to evidence-eligible cases. This experiment cannot
estimate the value of tests that were never performed and cannot be called
prospective active diagnosis.

## 7. C4: deterministic relation substrate

Source: E4 fixed pools, strict primary construction. Candidate labels map only
when a single SNOMED disorder ID is returned. Edges are deterministic `is_a`
paths of at most four hops. Both endpoint candidates must have at least one
literal, exact-offset candidate-specific support span. Inverse normalization,
duplicate collapse, cycle/contradictory-direction rejection and citation
closure are mandatory; every unsupported item is unknown/quarantined.

The frozen strict inventory is 96/400 eligible cases (DA 53, MCR 43), 124
edges and 19 safe-exact-exposed cases. Whitespace-normalized containment is a
construction sensitivity, not the primary set. Online entry requires mapping
precision and direction fidelity at least 95%, citation closure at least 98%
and U at most 5%. If entered, arms are no-edge, validated edge,
inverse-corrupted salience-matched placebo and node-only structure sham. Go
requires validated-vs-corrupt champion/clinical separation without excess
catastrophic substitution. The local SNOMED files are frozen by SHA; absent
upstream release metadata remains a provenance limitation.

## 8. C5: independent confirmation gate

> Scope amendment, 2026-08-14, still before any case-bearing closure call:
> the user explicitly waived execution of item 6 when honest closure would
> require a large out-of-800 rerun and complete audit. The audit below found
> exactly that condition. C5 will therefore publish the scope/contamination/
> power assessment and a `NOT_EXECUTED_SCOPE_WAIVER` decision; it will not
> download the test split or run confirmation arms in this round.

No current repository queue is source/time-external. DiagnosisArena tail cases
are same-split internal replications; the untouched MedCaseReasoning test split
is an independent **same-dataset split**, not a new source/time population.

The MCR test split may be frozen only after pinned row-count/SHA validation,
PMCID/DOI and exact/near-duplicate scans over the worktree and git history,
title/final-answer cue masking, retrieval-source exclusion, locked architecture,
locked primary contrast and paired power. The intended primary contrast is new
static system versus frozen Lite-like control on ITA clinical-complete, with
service failures counted wrong.

Phase-3 execution is fail-closed and, under the scope amendment above, is not
run in this round even if local development gates pass. The output is a hashed
`NOT_EXECUTED_SCOPE_WAIVER` decision plus a power/contamination plan—not a post
hoc confirmation run. A future genuinely source/time-external queue must be
built only from licensed PMC Open Access content through an official PMC
retrieval service and must be frozen after the architecture commit.

## 9. Interpretation rule

### 9.1 Execution-model freeze for C1--C4

> Amendment frozen 2026-08-14 after C0 review began but before any C1--C4
> case-bearing call or arm outcome was observed.

- Outcome-blind construction, requested-object parsing, modifier binding and
  active-policy calibration use `google/gemini-2.5-flash`.
- The two independent offline gate reviewers use
  `anthropic/claude-sonnet-4.6` and `openai/gpt-5.6`.
- Every admitted diagnostic comparator arm uses the same frozen
  `google/gemini-2.5-flash` comparator at temperature 0. Treatment content may
  differ as specified above, but the prompt must not expose an arm identifier.
- All calls are non-RAG, fail-closed, use at most 50 workers per run and retain
  provider/model, prompt hash, payload hash, cache identity and service/schema
  telemetry. A gate that fails is not retried with a different scientific
  model or threshold.

### 9.2 Fail-closed projection of reviewer schema failures

> Operational clarification frozen after reviewer A's card-level failure
> statuses were observed, but before A/B agreement, reviewer B/C summaries or
> any three-model panel result was compiled.

A failed review card is not deleted and is not resubmitted under a different
scientific cache identity. Individually well-formed candidate judgments in the
returned body remain usable; every missing, duplicate, out-of-universe or
invalid relation judgment is mapped to `uncertain`. The card-level failure and
telemetry remain visible. This preserves the full frozen denominator and can
only make the reliability/U gate harder than complete-case deletion.

No local success establishes a universal `−4.5 pp/candidate` law, mathematical
recall–conversion incompatibility, universal selector superiority or external
deployment benefit. A failed architecture gate does not invalidate E5's local
candidate-interference result; a successful architecture probe does not repair
the missing human-root or external provenance by itself.
