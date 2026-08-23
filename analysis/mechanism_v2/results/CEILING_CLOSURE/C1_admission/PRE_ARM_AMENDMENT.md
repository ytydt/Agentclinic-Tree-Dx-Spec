# C1 pre-arm amendment: substantively empty typed frontier

Declared 2026-08-18, **before any selector job was compiled and before any
clinical arm call was made**. This ordering is the point of the record: the
handling below was chosen from the structural readiness state alone, with no
arm outcome, no Top-1 response and no endpoint value visible.

## Condition being amended

The frozen readiness gate treats any case whose `typed_fixed_k` main frontier is
empty as a hard failure. That check was written to catch a real defect: an
earlier matcher admitted the literal fallback `unresolved` as a matching object
kind, and after that was corrected an absent typing annotation would otherwise
have degraded silently into fixed-k behaviour.

With typing now complete at 800 of 800 task identities and `requested_object`
coverage at 1.000, four cases still have an empty typed frontier for a different
reason. In `DA_d2_heldout100/321`, `DA_d2_seq100/83`, `MCR_seq200b/470` and
`MCR_v1_seq100/56` the annotator resolved the request as `disease_entity` and
positively typed every pool candidate as `disease_subtype`. Nothing is missing;
the frozen strict-equality rule in `_admission_type_match` simply admits nobody.

## Amendment

The readiness gate now separates two causes of an empty typed frontier:

- **Execution artifact** — the request is unresolved, or any candidate carries an
  empty or `unresolved` kind. This remains a hard readiness failure, because the
  arm would otherwise silently collapse into fixed-k.
- **Substantive outcome** — the request is positively resolved and every
  candidate is positively typed, but no candidate kind equals the requested
  kind. This is no longer a readiness blocker. It is recorded in the gate as
  `substantively_empty_typed_frontier` with the affected case keys, and the case
  is carried into arm execution unchanged.

## How a substantively empty frontier is scored

Per the already-frozen ITA rule that a failed or invalid call is incorrect and
never deleted or imputed, the affected arm is given exactly the state its own
admission rule produced. The selector receives an empty main frontier, cannot
return a member of it, and its response fails the frozen universe validation.
That becomes an explicit failure row, which the endpoint counts as no evaluable
Top-1 and therefore incorrect for that arm on that case.

Denominators are unchanged: every arm keeps all 400 cases. No case is dropped
from any arm, no value is imputed, and no threshold is moved. The cost is 4
knowingly unsatisfiable `typed_fixed_k` calls plus the 12 `qualified_frontier`
and 12 `sham_qualification` cases that already have empty main frontiers under
the frozen rules, against 1,600 total arm calls.

## Why not the alternatives

Excluding the four cases as a stratum would remove the exact cases where the
admission rule is most aggressive, biasing the comparison in the treatment's
favour. Relaxing `_admission_type_match` so that `disease_subtype` satisfies a
`disease_entity` request would change the treatment definition after seeing
which cases it fails on, and would also change the typed and qualified arms on
many of the 28 cases where fewer than half the candidates match. Both were
rejected in favour of letting the frozen rule bear its own consequences.

## Scope

This amendment governs readiness classification and arm scoring only. It does
not alter the case set, the four arm definitions, `k`, the endpoint, the
statistical contract, or the C1 efficacy gate owned by `analyse`. The
pre-amendment readiness gate is retained as `readiness_gate.json.pre_resume`
and the pre-resume report as `REPORT.md.pre_resume`.
