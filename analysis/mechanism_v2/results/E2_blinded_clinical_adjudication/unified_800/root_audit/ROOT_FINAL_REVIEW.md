# E2 supplemental 400-case root review

## Decision and scope

This supplement closes the clinical-adjudication gap left by the original E2
design-weighted 400-case sample. It covers the other 400 cases in the frozen
DA400 + MCR400 mechanism universe and the union of champion outputs emitted by
the nine arms that actually have all 800 cases:

`collapse3c`, `multistance`, `lite`, `forest`, `impc`, `e7`, `v0`, `B06`, and
`B07`.

The corrected freeze contains 400 cards and 1,430 unique case-candidate
relations. Fifty-nine exact or frozen-safe-synonym relations are deterministically
complete; all remaining 1,371 relations received a manual code. The complete
E2 census is therefore 800 case identities and 3,103 candidate-reference
relations (1,673 old + 1,430 supplemental), projected to 7,200 case-arm rows.

No external API or LLM call was made for this supplement. The three draft
batches were reviewed from blinded cards that omitted case key, family, slice,
arm provenance, old endpoint flags, mapper/judge outcome, sampling stratum and
leaderboard position. Root review restored the index only after the draft code
streams were complete.

## Coverage and mechanical validation

- Batch A: U0001-U0134, 134 cases, 472 manual relations.
- Batch B: U0135-U0267, 133 cases, 456 manual relations.
- Batch C: U0268-U0400, 133 cases, 443 manual relations.
- Combined: 400/400 cases and 1,371/1,371 manual relations in exact frozen
  order; no duplicate or missing case/candidate identifiers.
- Confidence screen: 299 high, 94 medium and 7 low. Every low-confidence case,
  every reviewer-flagged complete/partial boundary, and every one of the 80
  draft `C` relations received root second review.
- A post-freeze comparison against normalized semantic pairs in the original
  E2 audit produced one non-binding context flag (`cryptococcoma` versus
  `primary CNS lymphoma`). The new `N` and old `M` labels describe different
  records; both are clinical failures and no endpoint changes, so no automatic
  harmonization was made.
- `e2_root_audit_validation.py` fails closed on any order, coverage, code,
  override-provenance or frozen-input drift. It emits the auditable final rows,
  compact decision streams, hashes, consistency flags and validation summary.

## Root second-review decisions

The draft auditors were intentionally conservative about reference validity,
but several relation decisions treated a broad modern umbrella, contextual
cause or omitted composite component as fully equivalent. Root review applies
one consistent rule: `C` must preserve the same case-defining object; a material
etiology, anatomy, state, stage or composite component may not be supplied by
the vignette when it is absent from the evaluated output label. Descriptive
severity or presentation alone does not force a downgrade.

One identity and fourteen relation codes were changed. Every change is
machine-readable in `ROOT_OVERRIDES.json`; no vote or endpoint result was used.

| Item | Draft → final | Root reason |
|---|---|---|
| U0166 identity | S → I | Excluding anaphylaxis does not establish intentional symptom production; the record is insufficient rather than merely over-specific. |
| U0004C02 gastric phycomycosis | C → P | Historical `phycomycosis` is broader than Mucorales and does not preserve organism specificity. |
| U0044C04 IV-drug-use scleroderma-like disorder | C → P | Compatible description, but it does not uniquely name the chronic lymphedematous puffy-hand object. |
| U0051C01/C02 NMOSD | C → P | NMOSD is the modern parent spectrum and is broader than classic NMO. |
| U0097C02/C04 immune-checkpoint/immune-related myocarditis | C → P | Both omit the reference's agent-specific sintilimab attribution. |
| U0104C01 embryonal rhabdomyosarcoma | C → P | It omits the primary cutaneous scope. |
| U0222C02/C05 cardiac sarcoidosis | C → P | Both omit the material isolated-cardiac qualifier. |
| U0232C05 paravaccinia | C → M | It names the causal virus, not the requested Milker's-nodule lesion. |
| U0236C01 colorectal metastasis | C → P | It omits the hepatic metastatic site. |
| U0236C05 colon-cancer metastasis | C → P | It omits the hepatic destination. |
| U0357C02 conversion disorder | C → P | It omits the requested visual functional phenotype. |
| U0395C01 heparin-induced skin necrosis | C → P | It omits LMWH specificity and the distinctive distant-site scope. |

The final supplemental identity distribution is Q=225, F=43, M=5, S=57,
I=70, U=0. The final manual-relation distribution is C=66, P=403, X=425,
M=139, N=337 and U=1. Adding the 59 deterministic safe relations yields 125
supplemental complete-equivalent candidate nodes.

## Boundary policy and remaining uncertainty

Reference identifiability and candidate-reference relation remain separate.
An output can be semantically equivalent to the recorded reference even when
the vignette does not uniquely establish that reference; those rows remain
visible under `reference_identifiability` rather than being silently converted
to errors. Conversely, an output that merely names a component or parent is
not complete just because the vignette supplies the missing details.

The one retained relation `U` is a literal disjunction mixing a potentially
related iliopsoas tendinitis with an incompatible abscess. It is not coerced to
partial or conflicting. Identity classes M/S/I likewise remain explicit and
are mandatory sensitivity strata in the replay. This prevents uncertainty in
the benchmark object from being mistaken for a model mechanism.

The audit is a root-owned clinical coding exercise, not an inter-rater
reliability study: the draft batches were independent partitions, not duplicate
ratings of every card. Its strongest safeguards are prospective blinding,
exhaustive candidate coverage, explicit overrides, fail-closed validation and
case-level trajectory inspection. The remaining irreducible limitation is
clinical judgment at rare nomenclature and composite-scope boundaries, which
is exposed in the draft reasons and override ledger rather than hidden in a
single accuracy column.
