# Batch C blind root audit review (U0268-U0400)

## Scope and blinding

- Reviewed only the frozen clinical cards at `cards.jsonl` lines 268-400 and the root protocol.
- No index, arm/provenance, prior endpoint, mapper, judge, dual-review, leaderboard, or model-output information was consulted.
- Candidate relations were judged in the supplied card order. Disease identity was determined from clinical evidence rather than lexical containment.

## Low-confidence identity calls

These are substantive clinical-boundary cases (`confidence < 0.85`), not cases where the auditor is highly confident that evidence is insufficient.

| Case | Code | Confidence | Main unresolved boundary |
|---|---:|---:|---|
| U0269 | F | 0.76 | Signet-ring adenocarcinoma is proven; primary bladder versus secondary origin remains unresolved. |
| U0274 | F | 0.78 | Intracellular yeast is shown, but the organism-specific PCR result is omitted. |
| U0275 | I | 0.72 | Complex fetal perirenal collection could be hemorrhage or urinoma in obstructive uropathy. |
| U0277 | F | 0.75 | RIPE-associated lupus-like serositis is plausible, but antihistone/dechallenge evidence is weak. |
| U0285 | F | 0.81 | Graves phenotype is persuasive, but receptor-antibody/uptake confirmation is absent. |
| U0298 | F | 0.81 | Migratory tubular lesion strongly suggests sparganosis, without recovered parasite/pathology. |
| U0300 | F | 0.78 | T-PLL phenotype is suggestive, without defining blood/cytogenetic evidence. |
| U0313 | F | 0.71 | IMA vascular lesion is shown; bowel fistulation and true-versus-pseudoaneurysm status are not settled. |
| U0323 | F | 0.76 | Inverted appendix/endometriotic lead point is favored without final operative pathology. |
| U0325 | F | 0.78 | Urticarial vasculitis phenotype lacks biopsy confirmation. |
| U0327 | F | 0.80 | CT favors foreign-body small-bowel perforation without operative confirmation. |
| U0331 | F | 0.78 | Myxoid sarcoma is supported; extraskeletal myxoid chondrosarcoma lacks defining molecular confirmation. |
| U0334 | F | 0.81 | TLE1 supports synovial sarcoma but SS18 confirmation is absent. |
| U0335 | F | 0.80 | Juvenile ossifying fibroma is favored radiologically without tissue. |
| U0346 | F | 0.83 | Tooth-like lesion favors compound odontoma without excision histology. |
| U0355 | F | 0.80 | Arthroconidial yeast is shown, but Magnusiomyces species result is omitted. |
| U0367 | F | 0.78 | Pontine localization is plausible; delayed imaging does not securely prove infarction. |
| U0370 | F | 0.80 | Rhombencephalitis is clear; the positive-culture organism is not named in the card. |
| U0376 | F | 0.82 | Cutaneous nocardiosis is established; N. brasiliensis species result is omitted. |
| U0380 | F | 0.83 | Pyogenic liver abscess and metastatic complications are clear; K. oxytoca is not named. |
| U0387 | I | 0.80 | Rhegmatogenous detachment is favored after steroid nonresponse, but no break/operative confirmation is shown. |
| U0391 | F | 0.79 | Severe Campylobacter pancolitis with dilation is shown; formal megacolon diameter/criteria are incomplete. |
| U0393 | F | 0.77 | Broader EMG distribution favors Parsonage-Turner, but the classic antecedent pain is absent. |

## Complete-versus-partial boundary review

The operative rule was: `C` requires the same clinical root with no missing modifier that changes disease identity, causal mechanism, anatomic scope, recurrence/metastatic state, or a defining complication. `P` was used when the candidate is a compatible parent, component, or materially under-specified version. Descriptive severity alone did not force `P`.

| Case/candidate(s) | Frozen code | Boundary rationale |
|---|---:|---|
| U0272C04 | C | “Epidermolysis bullosa nevus” names the rare root; benign atypia is documented and does not create another disease root. This is the narrowest C/P call in the batch. |
| U0277C04, U0299C01, U0321C03, U0349C02, U0357C02, U0395C01 | C | Direct disease-name equivalents; omitted narrative details do not change the root. |
| U0286C03 | C | CME secondary to RVO preserves both manifestation and cause; chronicity is descriptive. Generic CME candidates remain P. |
| U0305C01-C02 | C | MI with pericarditis is equivalent to peri-infarction pericarditis. MI alone remains P. |
| U0306C02-C03 | C | Longus colli tendinitis is the accepted syndrome name for retropharyngeal calcific tendinitis. Generic calcific tendinitis remains P. |
| U0309C01-C02 | C | H3N2 pneumonia captures the virologic subtype and dominant organ syndrome. Broader influenza pneumonia labels remain P. |
| U0314C01-C05 | C | Diabetic striatopathy/diabetic chorea/hyperglycemic hemichorea are clinically coextensive here. Symptom-only hemichorea-hemiballismus remains P. |
| U0332C02 | C | Explicit metastatic extraskeletal myxoid chondrosarcoma; lineage-only or metastasis-only labels remain P. |
| U0342C03-C04 | C | Variable AV conduction is demonstrated and is a tracing feature of IART rather than a separate etiologic root. |
| U0363C04 | C | HTRA1-related hereditary CSVD preserves molecular cause and disease class; broader vasculopathy/dementia labels remain P and CARASIL is X. |
| U0367C01-C03, C05-C06 | P | Each omits either infarction mechanism, facial-palsy manifestation, or exact pontine scope; no candidate preserves the full relationship. |
| U0368C03 | P | Oral histoplasmosis omits the clinically meaningful “primary/isolated” status. |
| U0369C02 | P | Correct drug causality but generic rash morphology; U0369C08 is C because maculopapular and morbilliform are equivalent here. |
| U0382C01-C03, C05 | P | Fistula-only and cholesteatoma-only labels each omit a defining half of the composite diagnosis. |
| U0388C01-C03 | P | Each omits either class-wide TNF-inhibitor attribution, ectropion, or the specific blepharitis phenotype. |
| U0396C01-C07 | P | Every candidate drops at least one defining axis among recurrence, stage, papillary-serous histology, and somatic BRCA1 status. |
| U0398C02 | P | Correct disease family but omits the genital subtype. |
| U0399C03 | P | CHD2-related epilepsy preserves the gene but omits the developmental epileptic encephalopathy phenotype. |

## Other relation boundaries flagged

- U0392C01 is `U`, not forced to P or X: its literal disjunction combines a potentially related iliopsoas tendinitis with an incompatible abscess.
- Etiologies or manifestations alone were coded `M` when they did not name the target root (for example U0275 PUV, U0390 pulpitis, and U0400 bradycardia).
- A competing disease subtype or mechanism was coded `X`; an unrelated diagnosis with no meaningful shared root was coded `N`.
