# C4 deterministic relation substrate: closure result

Status: **NO_GO**

Scope: E4 strict primary construction only; this is not a claim about every
relation representation or ontology.

## What was frozen

- Source: E4 fixed union pools, 400 cases.
- Raw eligible inventory: 96 cases, 124 candidate-ID edges.
- Mandatory semantic duplicate collapse: 2 same-case, same-directed-SNOMED-
  concept-pair edges.
- Strict primary inventory: 96 cases and 122 edges (DA 53/72; MCR 43/50).
- Directed path lengths 1/2/3/4: 81/32/8/1.
- Safe-exact-exposed cases: 19 (DA 2; MCR 17).
- Deterministic validation: zero invalid literal offsets, path mismatches,
  frozen inverse pairs, residual semantic duplicates or concept-binding drift.

The byte SHA-256 of `freeze/cases.jsonl` is
`feb1c1226f034f8b6aed9409f2da8bb3ee5efb3c94c02032852183f479157f81`.
The freeze manifest preserves both `raw_edge_n=124` and
`duplicate_concept_pair_collapsed_n=2`; no discarded edge is silently lost.

## Independent model review

Two heterogeneous reviewers independently evaluated all 122 strict edges.
They received no arm outcome or historical winner information.

| Reviewer | Model | Mapping | Direction | Citation | U | Inverse/cycle | Decisions |
|---|---|---:|---:|---:|---:|---:|---|
| B | `anthropic/claude-sonnet-4.6` | 93/122 | 94/122 | 60/122 | 58/122 | 1/122 | 56 accept, 8 reject, 58 unresolved |
| C | `openai/gpt-5.6-sol` | 121/122 | 107/122 | 14/122 | 0/122 | 1/122 | 14 accept, 108 reject |

Both online stages completed 96/96 case tasks with zero schema failures. The
combined artifact has 244 edge-review rows, exactly two per strict edge. It is
a two-model panel, not human/root adjudication.

## Frozen entry gate

| Metric | Required | Observed | Result |
|---|---:|---:|---|
| Mapping precision | >= 0.95 | 0.8770 | fail |
| Direction fidelity | >= 0.95 | 0.8238 | fail |
| Citation closure | >= 0.98 | 0.3033 | fail |
| Unresolved rate | <= 0.05 | 0.2377 | fail |
| Raw agreement | >= 0.90 | 0.1311 | fail |
| Gwet AC1 | >= 0.75 | -0.2732 | fail |
| Inverse/cycle findings | 0 | 2 | fail |
| Exact two-reviewer contract | true | true | pass |
| Residual semantic duplicates | 0 | 0 | pass |
| Concept-binding drift | 0 | 0 | pass |
| Source RF2 provenance | verified | unverified | fail |

The large reviewer divergence is retained as a result, not repaired after
seeing outcomes. In particular, deterministic literal-offset validity does
not imply that a reviewer regards the cited text as sufficient clinical
support for the candidate or directed relation. The present review contract
did not achieve reliable agreement on that stronger closure judgment.

The three committed derived SNOMED artifacts are byte-bound, and the build
script names release
`SnomedCT_ManagedServiceUS_PRODUCTION_US1000124_20260301T120000Z`.
However, the original RF2 archive, its SHA-256, effective-time-bearing source
records and a trusted upstream release manifest are absent. Therefore derived
bytes cannot establish source-release provenance.

## Decision and interpretation boundary

The pre-specified gate failed on both review reliability/content criteria and
source provenance. The 384 downstream four-arm selector tasks were therefore
not generated or run. C4 closes as a valid **No-Go**: the deterministic
substrate is reproducible and structurally sound after duplicate collapse, but
this round does not support admitting it as a causal breakthrough mechanism.

This does not show that relations are generally useless. A future attempt must
first acquire and hash-verifiably bind the original RF2 release, and must freeze
a less ambiguous, independently reliable clinical citation/edge review
contract before any selector outcome is observed.
