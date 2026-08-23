# Parent adjudication

The second-pass review changed scientific content in 9 of 50 cases. The parent
agent reviewed all nine against the reference diagnosis, frozen candidates and
vignette, plus every low-confidence and web-sourced claim in the 25-case review
queue.

Seven second-pass changes were accepted:

- `/646`: use bare `Rectal ulcer` as core; keep `solitary` and
  `radiation-induced` as modifiers.
- `/698`: generic fungal hyphae do not establish Mucorales or pulmonary
  mucormycosis.
- `/713`: use bare `Asthma` rather than status asthmaticus as the core.
- `/719`: use facial palsy as core, with peripheral subtype, right anatomy and
  dorsolateral pontine infarction as etiology.
- `/769`: FH loss plus a pathogenic truncating variant supports
  `FH-deficient` by inference rather than literal naming.
- `seq100/139`: vesicular thyroid carcinoma belongs in the core; do not repeat
  it as a subtype modifier.
- `seq100/22`: an anti-MDA5 phenotype without patient anti-MDA5 testing does not
  establish the antibody-associated modifier.

Three parent overrides are applied:

1. `/741`: restore `Acinic cell carcinoma` as the bare core, with `breast`
   anatomy and `primary` etiology. Absorbing breast into the core violates the
   factorization contract.
2. `/758`: retain the reviewed bare `Myocardial injury` core, but classify
   `diffuse myocardial necrosis` as a composite component rather than a subtype.
3. `/754`: downgrade both rare syndrome components and their concurrency to
   `not_determinable`. Phenotypic resemblance without the omitted molecular
   results cannot establish concurrent MIC-CAP and Mowat-Wilson syndromes.

All other reviewed claims were accepted. Web sources were used only to check
general clinical relations; no source supplied a patient fact absent from the
vignette.
