# E4 manual trajectory audit

## Responsibility and reviewed set

The final judgments in this file were made manually from the clean vignette,
fixed candidate/evidence table, five returned champions, contrast rationales
and frozen gold label.  No external LLM adjudicator supplied these judgments.
Model rationales are treated as fallible traces, not as ground truth.

I reviewed:

1. all 17/17 cases where at least two online selectors differed on the strict
   endpoint;
2. a frozen SHA sample of 12/166 cases where every online selector missed the
   strict endpoint but the online champions differed (six DA, six MCR);
3. aggregate source exposure, cap loss, candidate position/source patterns,
   every strict win/loss transition, and all arm-level runtime incidents.

The manual review is deliberately unblinded to the benchmark answer because
its purpose is mechanistic dissection, not a replacement accuracy endpoint.
E2 remains the blinded completeness/identifiability adjudication.

Abbreviations: **E** = e7 contrast, **F** = Forest evidence integration,
**C** = APHHM-C obligation ledger, **P** = pairwise tournament.

## Complete audit of the 17 strict-endpoint discordances

| Case | Selector split | What actually caused the split | Manual judgment |
|---|---|---|---|
| DA/334, phaeohyphomycosis | E/F/C choose gold; P chooses *Exophiala infection* | P treats naming the cultured organism as “more specific,” but an organism infection label is not the requested clinicopathologic disease entity. | Real P scope/ontology harm; not a synonym-credit issue. |
| MCR/260, syphilitic aortitis | F/C choose gold; E/P choose parent *infectious aortitis* | F/C use aortic insufficiency plus slit-like coronary ostium as the classic syphilitic pattern; E/P require organism confirmation and retreat to the parent. | Gold-concordant and clinically plausible, but under-confirmed because no syphilis serology is present. Count as a probable, not secure, specificity gain. |
| MCR/285, pycnodysostosis | F chooses the gold spelling; E/C/P choose *Pyknodysostosis* | All four rationales describe the same osteosclerosis–acro-osteolysis–Wormian-bone syndrome. The candidate list contains spelling variants that the frozen bridge does not equate. | Pure surface/bridge artifact; not a Forest reasoning gain. |
| MCR/317, cryptococcal meningitis | F/C/P choose gold; E chooses toxoplasmosis | E anchors on the multiple enhancing-lesion archetype. F/C/P give the highly specific cryptococcal antigen at CD4 6 more weight and allow cryptococcomas/infarcts. | Strong evidence-integration gain over imaging-pattern anchoring. |
| MCR/345, HHRH | F chooses full mechanism label; E/C/P choose *hypophosphatemic rickets with nephrocalcinosis* | F integrates low phosphate, high 1,25-(OH)2D, suppressed PTH, undetectable FGF23 and nephrocalcinosis; the others stop at the phenotype. | Real mechanistic-specificity gain, although normal measured urine calcium makes the literal acronym less obvious. |
| MCR/374, cryptogenic organizing pneumonia | E/F/C choose gold; P chooses parent *organizing pneumonia* | P refuses the “cryptogenic” qualifier even after negative infection testing and treatment failure. | Real under-specification; parent and child are related but not interchangeable here. |
| MCR/383, idiopathic granulomatous mastitis | F/C/P choose gold; E chooses *granulomatous lobular mastitis* | E selects a pathology-oriented near-synonym/subtype. Its rationale does not describe a different disease process. | Likely ontology/alias artifact; not secure Forest gain. |
| MCR/418, sarcoidosis | F chooses broad gold; E/C/P choose *cardiac sarcoidosis* | All traces correctly identify cardiac sarcoid. F happens to output the benchmark's broader parent while the other selectors are clinically more precise. | Apparent Forest gain is target-granularity alignment, not better diagnosis. |
| MCR/424, nonbacterial thrombotic endocarditis | E chooses mapped synonym *marantic endocarditis*; F/C/P choose SLE | F/C/P optimize a unifying systemic explanation and answer the cause of the vegetation rather than the lesion asked for. | Real task-scope overshoot and the sole strict F harm versus E. E preserves the requested diagnostic object. |
| MCR/458, LAM | F/C/P choose gold; E chooses Birt–Hogg–Dubé | F/C/P integrate sex, diffuse small round cysts, recurrent pneumothorax and hemoptysis; E overweights a generic cyst-shape description. | Strong demographic/anatomic integration gain. |
| MCR/470, cone–rod dystrophy | C/P choose gold; E/F choose Stargardt disease | C/P use the daughter/father ERG trajectory and progressive cone-to-rod dysfunction; E/F over-index the fundus autofluorescence appearance. | Real longitudinal/mechanistic benefit of obligation/pairwise reasoning. |
| MCR/479, extraskeletal myxoid chondrosarcoma | P alone chooses gold | P contrasts anastomosing cords, single-file cells and nuclear grooves against absent lipoblasts/branching capillaries; the other selectors follow the common thigh/myxoid-liposarcoma archetype. | Real, case-specific benefit of pairwise morphologic discrimination. |
| MCR/60, polymyalgia rheumatica | F/P choose gold; E/C choose iliopsoas tendinopathy | E/C treat the literal MRI abnormality as the diagnosis. F/P integrate age, bilateral proximal pattern, inflammation, weight loss and normal CK. | Real benefit from separating manifestation from systemic syndrome. |
| MCR/174, autoimmune gastritis | E/F/P choose gold; C chooses *atrophic corpus gastritis* | C makes negative parietal-cell antibodies and normal gastrin a near-hard veto. E/F/P allow early/seronegative disease and integrate autoimmune context with parietal-cell histology. | Real hard-negative-veto harm in the ledger prompt. |
| MCR/205, cysticercosis | F/C/P choose gold; E chooses multiple lipomas | F/C/P recognize the tongue nodule plus multiple mobile subcutaneous nodules and correctly avoid treating denied pork intake as exclusionary. | Strong specific-feature and exposure-scope gain. |
| MCR/211, Ewing sarcoma | E/F/P choose *Ewing sarcoma*; C chooses *Ewing's Sarcoma* | The two candidates are the same disease with punctuation/possessive variation; all rationales use the same CD99/small-round-cell mechanism. | Pure alias artifact; no ledger clinical harm. |
| MCR/220, Kawasaki disease | C/P choose gold; E/F choose MIS-C | E/F over-weight age, gastrointestinal symptoms and pandemic context. C/P apply the full fever/conjunctiva/oral/rash/extremity criteria and note absent shock. | Real criteria-based rescue; context anchoring harms E/F. |

### What the apparent Forest advantage contains

The strict F-versus-E comparison is 9 Forest-only wins and one E-only win.
Manual decomposition matters:

- five Forest-only wins are strong mechanism gains (cryptococcal antigen,
  HHRH biochemistry, LAM pattern, PMR systemic scope, cysticercosis tongue
  nodule);
- one is plausible but under-confirmed specificity (syphilitic aortitis);
- three are surface/ontology/target-granularity artifacts (pycnodysostosis
  spelling, granulomatous-mastitis near-synonym, broad sarcoidosis versus the
  more precise cardiac label);
- the single E-only win is a real Forest task-scope error: answering SLE rather
  than nonbacterial thrombotic endocarditis.

Thus the +8-case strict net is not eight independent clinical improvements.
The evidence still favors Forest-style integration on the exposed MCR cases,
but its credible mechanism is narrower: weighting highly specific evidence and
systemic context. Its corresponding failure mode is over-unification across
the diagnostic-object boundary.

## SHA-frozen audit of 12 all-wrong champion-flip cases

These cases test whether a selector can rescue an upstream or endpoint problem.
It usually cannot.

| Case | Why every strict arm missed | What the selector disagreement reveals |
|---|---|---|
| DA/137, papillary hemangioma | Exact gold is absent; the pool contains Dabska/PILA and related vascular tumors. | E chooses Dabska while F/C/P choose PILA. This is unresolved nomenclature, not evidence that any selector recovered the registered target. |
| DA/361, slow-fast AVNRT | Generic AVNRT is present, but no selector chooses it. | E/F anchor on induced wide-complex VT, C on SVT with aberrancy, P on CPVT. All fail to preserve the initiating narrow-complex/EP mechanism. This is a genuine shared selector failure, not just recall. |
| DA/686, dilated cardiomyopathy | The pool is entirely post-transplant complications/remodeling; the historical causal diagnosis is gone. | Selectors debate bronchial compression versus allograft remodeling. Fixed-pool selection cannot reverse upstream temporal target drift. |
| DA/95, sporadic PAPT | The named syndrome is absent; etiologies and neighboring syndromes remain. | E/F pick MSA, C/P DRPLA. Each tries to infer an etiology instead of returning the observed syndrome, reproducing diagnostic-object drift. |
| DA/540, acute oxalate nephropathy | The decisive biopsy diagnosis is absent despite AKI/DKA candidates. | E/F/C select DKA; P selects tamponade. High-specificity pathology was lost before selection, so richer comparison only reallocates the wrong answer. |
| DA/281, composite melanoma trajectory | Gold encodes stage, metastasis and second primary; pool has component labels only. | E selects metastatic melanoma, F/C/P melanoma. The disagreement is temporal scope, while strict identifiability is impossible from the candidate ontology. |
| MCR/461, dengue viral myositis | Dengue/myositis is absent. | E returns the manifestation rhabdomyolysis; F/C/P infer leptospirosis. Neither path can recover the missing viral cause. |
| MCR/67, depressor-anguli-oris hypoplasia | The pool contains the clinically equivalent expanded label; E/F/C choose it, but the bridge does not equate the extra articles/“muscle.” | A nominal all-wrong case is actually an endpoint normalization failure. P chooses the syndrome synonym *asymmetric crying face*. |
| MCR/45, granuloma annulare | P chooses the more specific *periocular granuloma annulare*, which strict matching does not credit. | This is another modifier-direction endpoint artifact; E/F/C instead choose necrobiotic xanthogranuloma based on a disputed histologic distinction. |
| MCR/356, synovial sarcoma | Gold is absent although every trace notices that TLE-1/EMA favor it. | The “do not invent” guard works correctly: selectors are forced to choose Ewing/PNET. This cleanly proves selection cannot repair candidate omission. |
| MCR/390, intraductal carcinoma | No intraductal-carcinoma candidate exists. | Arms choose mucoepidermoid or acinic-cell carcinoma from cystic cytology. The error is upstream recall/ontology, not ranker choice. |
| MCR/221, giant-cell-rich osteosarcoma | Pool contains mediastinal lymphoma/neuroblastoma/Ewing alternatives but no osteosarcoma. | Large champion changes reflect free competition among wrong families. Pairwise work adds computation without restoring the missing disease family. |

## Cross-case mechanisms

### 1. Upstream exposure dominates DA

Only 62/400 cases have a strict/frozen-synonym gold candidate: 7/200 DA and
55/200 MCR. The uncapped union has 63; the ten-candidate cap loses exactly one
strict gold. Low exposure is therefore not a width-10 artifact.

The unsafe legacy substring diagnostic finds a related label in 197/400 cases
(114 DA, 83 MCR), but many are parent/child or component/composite pairs such
as “melanoma” versus a staged multi-event melanoma trajectory. This large gap
is evidence for an unresolved target-ontology problem, not permission to award
substring credit. E2 must decide which are clinically complete and identifiable.

### 2. Selector prompts exert a real but bounded effect

Online selectors agree on only 70.8–76.3% of champions even though payloads
are identical. Prompt semantics are therefore causally active. Candidate-ID
positions are broadly distributed, and source-set selection profiles are
similar across online arms; no arm can see source identity. This argues against
a simple order or hidden-source explanation for the 24–29% flip rates.

The count control behaves differently: it selects a four-support-item
candidate in 350/400 cases and agrees with each online selector only about 29%.
Clinical selectors are not reducible to evidence-bullet counting.

### 3. Forest's benefit is conditional and asymmetric

Forest improves over e7 by +2.0pp overall (paired bootstrap 95% interval
+0.5 to +3.5pp; exact McNemar p=0.0215), entirely in MCR (+4.0pp) with no DA
strict difference. Conditional on the 62 exposed cases, conversion is 66.1%
for Forest versus 53.2% for e7. The manual review narrows the mechanism to
high-specificity evidence integration and manifestation-versus-syndrome scope;
it also exposes Forest's tendency to answer an upstream unifying disease.

### 4. Exhaustive pairwise work is not automatically better

P uniquely rescues extraskeletal myxoid chondrosarcoma and helps on cone–rod
dystrophy/Kawasaki, but it also under-specifies cryptogenic organizing
pneumonia and mistakes an organism label for the disease. It scores 38/400,
below Forest's 41/400, while its incomplete telemetry already records the
largest output-token and latency burden. “Compare every pair” is therefore not
a free accuracy primitive; comparisons need typed obligations and stopping.

### 5. The ledger's negative handling is double-edged

The obligation prompt rescues cone–rod dystrophy and Kawasaki by demanding
coverage, but its treatment of negative antibodies/gastrin turns a stage- and
sensitivity-limited result into a hard veto against autoimmune gastritis. This
is direct support for E8's time/scope-aware negative experiment.

## Threats to inference

- These are development cases, selected before outcomes but not a new
  confirmation cohort.
- Selector prompts are clean mechanism approximations, not byte-for-byte
  production selector code. Results identify instruction semantics, not a full
  architecture winner.
- Candidate evidence quality remains heterogeneous by upstream source even
  though every selector sees the same merged payload.
- The e7 arm initially ran under a 2048-token direct-post ceiling and resumed
  under 8192; other arms used 8192. All final responses are valid, but retry
  path/provider resampling is a residual technical confound.
- Telemetry is short by 1–3 semantic rows per online arm; cost figures are
  lower bounds. No missing cost is imputed.
- Manual mechanism judgments are single-reviewer and gold-aware. They explain
  the strict transitions but do not replace E2's blinded dual review.

## Audit conclusion

E4 falsifies two simple stories: selection is not just support-counting, and
exhaustive pairwise comparison is not inherently superior. It supports a more
specific claim: on MCR cases where the correct diagnostic object is already in
the fixed pool, a Forest-like instruction that integrates high-specificity
evidence and discounts correlated restatements converts exposure better than
the compact e7 contrast prompt. The gain is partly inflated by surface and
target-granularity artifacts and is not demonstrated on DA. Upstream
representation/target ontology, not selector choice, remains the dominant
failure mechanism across the 400-case sample.
