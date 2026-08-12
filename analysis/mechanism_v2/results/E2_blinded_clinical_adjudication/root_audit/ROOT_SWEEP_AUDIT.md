# E2 exhaustive root sweep audit

## Why the original queue was not sufficient

The preregistered primary root queue reviewed 537 candidate-reference pairs and
included a frozen random calibration of 30 consensus-partial pairs.  That
calibration happened to contain 30 valid partials.  Subsequent case-level
inspection found `IgA nephropathy -> Tuberculosis`, `Miliary tuberculosis`, and
`Pulmonary tuberculosis` among the unaudited pairs; Gemini and DeepSeek had
independently called all three `partial_parent_or_component`.  This is a direct
falsification of the assumption that sparse consensus calibration could safely
stand in for root adjudication.

The original queue and hashes were left unchanged.  A separate corrective
queue was frozen at commit `8bb242e8f`: all 1,070 remaining non-exact pairs,
after excluding the 537 primary-root pairs and 66 frozen exact-synonym pairs.
Its method-blind cards have SHA-256
`7121c1a0b85d9f4499c2c5854d4c568dff8431c98ab9961305c30146bb44449c`.

## Audit ownership and blinding

The root auditor inspected all 1,070 cards.  Cards contained the clinical
record, benchmark reference, candidate and the two original reviewer
rationales.  They omitted case keys, arm provenance, family, strict/task
outcomes, mapper outcome, sampling stratum, queue reason and reviewer-pair
labels.  A post-freeze GPT-4.1 review was used only as a high-recall source of
counterarguments.  It did not vote or overwrite root decisions.

The resulting endpoint correction is large and asymmetric:

- 70 original consensus-partial pairs became non-accepted;
- 3 original non-accepted pairs became partial;
- 997 pairs stayed on the same accepted/non-accepted side;
- the original consensus endpoint therefore had precision 419/489 = 85.69%,
  recall 419/422 = 99.29%, and 73/1,070 endpoint errors.

The 70 false accepts were not random label noise.  The dominant mechanisms
were 23 distinct tumor histologies, 16 manifestations mistaken for the final
diagnostic object, 8 unrelated entities, 4 nonspecific differentials mistaken
for parents, and 4 conflicting hematologic lineages.  The remaining 15 covered
wrong anatomy, etiology, disease state, traumatic state, vascular mechanism,
retinal entity, and unsupported malignant transformation.

Representative high-leverage corrections include:

| Reference | Candidate | Root relation | Failure mechanism |
|---|---|---|---|
| IgA nephropathy | Tuberculosis | not equivalent | unrelated disease |
| Glioblastoma multiforme | Acute disseminated encephalomyelitis | not equivalent | neoplasm versus inflammatory demyelination |
| Melanoma | Ewing sarcoma | not equivalent | distinct tumor lineage |
| Schwannoma | Uterine leiomyoma with cystic degeneration | not equivalent | distinct tumor histology |
| Leptospirosis with multiorgan injury | ARDS | manifestation/related | complication substituted for etiologic composite |
| 5-oxoprolinemia | Metabolic acidosis | manifestation/related | biochemical manifestation substituted for cause |
| LAD infarction with de Winter/Wellens evolution | STEMI | partial | clinically compatible STEMI-equivalent parent restored |
| Metastatic bladder paraganglioma | Phaeochromocytoma of the bladder | partial | historical functional-tumor alias, but metastatic scope missing |
| Keloidal scleroderma | Limited systemic sclerosis | partial | supported broader parent missing the keloidal variant |

## Final coverage and reviewer calibration

All 1,673 candidate relations now resolve through exactly one provenance path:
537 primary blinded root decisions, 1,070 corrective blinded root decisions,
and 66 frozen exact identities.  Final relation counts are 171 complete, 569
partial, 173 conflicting subtype/scope, 310 manifestation/related, and 450 not
equivalent.

The full-root endpoint exposes different subcontractor biases.  Gemini's
accepted precision/recall are 74.82%/97.57%; DeepSeek's are 79.66%/96.35%.
Post-freeze GPT-4.1 raises recall to 97.57% but lowers precision to 68.18%.
Thus model heterogeneity helps surface candidates for inspection, but neither
agreement nor a third-model majority is a reliable clinical endpoint.

## Interpretation boundary

This supplement is corrective evidence triggered by a falsification, not a
preregistered confirmatory arm.  It removes a known measurement bias and makes
the final E2 endpoints root-complete, but it cannot retroactively make the
corrective scope independent of the observed failure.  The benchmark-weighted
target also remains the existing 800-case mechanism universe rather than an
external confirmation population.
