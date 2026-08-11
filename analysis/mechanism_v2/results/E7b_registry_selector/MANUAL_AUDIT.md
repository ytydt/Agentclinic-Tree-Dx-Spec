# E7b manual trajectory audit

## Audit status and limits

The primary investigator reviewed all 40 cases in `audit_queue.jsonl` after the
blinded selector calls had completed.  This is a mechanism audit, not a second
confirmatory endpoint: the auditor could see the benchmark label, all three
candidate lists, selector rationales, E7a unsafe-pair records and the original
vignette.  Judgments below therefore diagnose *why* an arm changed; they do not
replace the planned blinded completeness study (E2).

Two analysis defects were discovered during this audit and corrected without
new model calls:

1. Concurrent byte-identical payloads had been allowed to make separate calls.
   The original rows are preserved in
   `case_conditions_raw_concurrent.jsonl`.  The analysis rows use one frozen
   cached response per identical payload; controls then show zero artificial
   arm flips.
2. The first implementation credited a legacy champion when *any hidden member*
   of its merged concept matched the gold label.  That endpoint changed with
   the registry treatment.  The primary endpoint now matches only the displayed
   champion label.  Hidden-member credit remains a contamination diagnostic.

## Complete review of surface-endpoint discordances

There were 13 exact-versus-legacy surface top-1 discordances and one additional
typed-versus-exact discordance.  The table records the actual causal distinction,
not merely whether the benchmark string matched.

| Case | Gold | Legacy champion | Exact champion | Typed champion | Audit judgment |
|---|---|---|---|---|---|
| `DA_d2_heldout200b/638` | Laryngeal histoplasmosis | Histoplasmosis | Laryngeal histoplasmosis | same as exact | Exact preserves the disease site; legacy folds the gold into its parent. Clear exact identity rescue. |
| `MCR_v2_seq100/197` | Pseudoseptic arthritis | Aseptic viscosupplementation-related arthritis | Pseudoseptic arthritis | same as exact | Exact prevents the unsafe `septic arthritis`/`pseudoseptic arthritis` substring collision. The legacy surface answer is clinically compatible, but its internal concept also contains the opposite infectious diagnosis. Safety rescue is real even though the alternate phrase is acceptable. |
| `MCR_seq200b/407` | Adrenal myelolipoma | Myelolipoma | Adrenal myelolipoma | same as exact | Exact preserves anatomy and restores the benchmark-addressable label. |
| `MCR_v2_seq100/173` | Chronic subdural hematoma | Subdural hematoma | Chronic subdural hematoma | same as exact | Exact preserves the temporal qualifier. |
| `MCR_seq200b/326` | Brucellosis | Brucellosis | Brucellosis | Spinal epidural abscess | Generic non-equivalence edges redirect typed selection from etiology to complication. This is a task-projection harm, not an identity failure. |
| `MCR_seq200b/464` | Ruptured popliteal artery aneurysm | Popliteal artery aneurysm | Ruptured popliteal artery aneurysm | same as exact | Exact preserves event status/complication. |
| `MCR_v1_seq100/12` | Tumor-induced osteomalacia | Osteomalacia | Tumor-induced osteomalacia | same as exact | Exact preserves etiology. |
| `MCR_v1_seq100/54` | Trigeminal neuralgia | Trigeminal neuralgia | Vaccine-induced trigeminal neuralgia | same as exact | Both are clinically compatible; the benchmark is a parent label and the exact arm chooses a supported etiologic subtype. The exact string metric favors the coarser answer. |
| `DA_d2_heldout100/261` | Cutaneous malakoplakia | Malakoplakia | Cutaneous malakoplakia | same as exact | Exact preserves anatomic subtype. |
| `MCR_seq200b/418` | Sarcoidosis | Sarcoidosis | Cardiac sarcoidosis | same as exact | Both are clinically compatible; exact is more specific and the benchmark is coarse. |
| `MCR_v2_seq100/159` | Endometrioid adenocarcinoma | Endometrioid adenocarcinoma | Iatrogenic tumor dissemination | Grade 3 endometrioid adenocarcinoma | Exact identity exposes both mechanism and tumor. Its untyped selector chooses the mechanism, while the relation warning restores the disease type. The strict mapper still rejects the clinically valid typed subtype. This is projection plus mapper failure. |
| `MCR_v2_seq100/236` | Eosinophilic mastitis | Eosinophilic mastitis | Idiopathic eosinophilic mastitis | same as exact | Exact selects a supported subtype; the benchmark is the parent. |
| `MCR_seq200b/345` | Hereditary hypophosphatemic rickets with hypercalciuria | Hypophosphatemic rickets | Exact gold label | same as exact | Exact restores the etiologic/biochemical subtype. |
| `MCR_seq200b/416` | Schistosomiasis | Schistosomiasis | Spinal schistosomiasis | same as exact | Both are clinically compatible; exact preserves the affected compartment and the benchmark is coarse. |

The eight exact-only surface wins are all interpretable identity/qualifier
recoveries: anatomy (three), temporal/event status (two), etiology (two), and a
clinically crucial negation boundary (one).  Four of the five legacy-only wins
are benchmark-parent versus supported-subtype disagreements.  The fifth is the
endometrioid task-projection error, which typed relations corrected clinically
without receiving strict-string credit.

## Review of the remaining 26 priority cases

| Queue cases | Dominant finding | Consequence |
|---|---|---|
| `DA_d2_heldout200b/604`, `DA_d2_heldout100/281`, `DA_d2_heldout100/431`, `MCR_v2_seq100/170`, `DA_d2_heldout100/379` | The benchmark target is a composite stage, grade, molecular state, spread pattern or histologic subtype not present as a complete candidate. | Registry policy cannot solve missing proposal content; these belong to candidate completeness and task projection (E2/RCR-3 Call 2). |
| `DA_d2_heldout100/314`, `MCR_seq200b/388`, `MCR_seq200b/310` | The selected exact label is clinically the same or a supported specialization, but orthography/qualifiers fall outside the frozen bridge (`ClearCell` versus `Clear Cell`, for example). | Strict mapping creates false negatives. Expand only frozen *true synonym* coverage; do not reintroduce substring identity. |
| `DA_d2_heldout100/432`, `MCR_v1_seq100/49`, `DA_d2_heldout200b/555`, `DA_d2_heldout200b/778`, `DA_d2_heldout200b/741`, `MCR_seq200b/362`, `DA_d2_heldout200b/584`, `DA_d2_heldout100/364` | The selector chooses a genuinely wrong sibling, mimic or alternative process. | These are proposal/ranking errors, not mapper errors. Several lack the gold candidate entirely. |
| `DA_d2_heldout200b/567`, `DA_d2_seq100/237`, `DA_d2_heldout200b/489`, `DA_d2_seq100/118`, `DA_d2_seq100/241`, `DA_d2_seq100/97` | The selected label recovers only a parent or one component while the benchmark requires organism, site, genotype, complication or composite scope. | A complete-composition check is needed after ranking; parent labels should not silently receive full credit. |
| `DA_d2_seq100/99` | All three displayed champions match the benchmark. | High unsafe-pair count did not alter the output, but legacy's internal identity remains unsafe; output stability alone does not certify registry safety. |
| `DA_d2_heldout100/361` | Legacy retains the correct diagnostic family (AVNRT), while exact/typed select ventricular tachycardia. | Separating identities expands the pool but the selector then globally misranks it; identity safety requires a stronger comparator. |
| `DA_d2_heldout100/415`, `DA_d2_heldout200b/637` | The selector changes abstraction level or overstates mechanism/timing (STEMI-equivalent versus NSTEMI; acute trigger attribution versus chronic spontaneous urticaria). | Generic relation warnings do not encode temporal validity or the benchmark's requested diagnostic object. |

## Mechanism conclusions from the trajectories

1. **Unsafe identity is common and often invisible at the output.** Of 160
   contaminated legacy champions, 59 retained the same displayed label as the
   exact arm. A final-answer-only audit would miss those evidence transfers.
2. **Exact identity restores addressability before it restores accuracy.** It
   exposes 11 gold labels that legacy hides and loses one, but many exposed
   labels still lose at ranking or mapping.
3. **Substring folding can cross a negation boundary.** The
   septic/pseudoseptic case is the clearest safety counterexample: the strings
   overlap precisely where the clinical entities must remain distinct.
4. **A relation edge without direction is insufficient.** The brucellosis case
   shows a selector choosing the urgent complication rather than the requested
   etiology. Parent/subtype, etiology/manifestation, component/composite and
   temporal-scope roles must be explicit.
5. **Strict string accuracy is not clinical completeness.** Several apparent
   losses are supported subtypes of a coarse benchmark; several apparent near
   misses lack a required component. E2 must adjudicate these categories
   separately rather than collapse them into one synonym bucket.
