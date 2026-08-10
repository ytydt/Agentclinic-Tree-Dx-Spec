# MCR / mcr_200b / case 367

- **gold**: Cicatricial conjunctivitis
- **layer**: `base_win_recall` · **layer_aphhm**: ``
- **correct**: e7=0 v0=0 B06=1 B07=1 B01=0 APHHM=
- **e7_locus**: `s2_miss` · **e7_fail_code**: `s2_miss`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=0 e7_champ_cluster=other B06_sup_gold=1 B07_diag_gold=1 same_cluster_flip=0 true_entrance=1
- **APHHM**: locus=`na` code=`na` prune_e7_ok=0

## Vignette
A 52-year-old Chinese man presented with bilateral red eyes and itching for 1 year. The redness was constant with intermittent tearing, without pain, gritty sensation, photophobia, or discharge. He reported episodic blurred vision due to dry eye, relieved by lubricants. He denied diplopia. His medical history included type 2 diabetes, hypertension, dyslipidemia (all treated), and a chronic maculopapular rash on the chest and arms suggestive of atopy or eczema. He had no sinusitis, asthma, other autoimmune or dermatologic disorders, drug allergies, prior immunosuppression, ocular trauma or surgery, contact-lens wear, or family history of ocular or skin disease. He did not smoke.

On examination, vital signs were normal. He had a maculopapular rash over flexor and extensor surfaces of his elbows without excoriations. There were no rosacea-type or acneform facial lesions and no oral ulcers. Ocular examination showed bilateral moderate diffuse bulbar conjunctival hyperemia and grade 1 subtarsal papillary reaction. Each eye had an inferior symblepharon involving up to three clock hours and cicatrization of the caruncle. The inferior lacrimal punctum was scarred. There was no chemosis, s…

## Backbone e7

- S2 n=51 gold_rank=None
  - clusters: gold=0 near=4 other=47
- S3 shortlist (5):
  - [near] Ocular Cicatricial Pemphigoid
  - [other] Mucous Membrane Pemphigoid
  - [other] Atopic Keratoconjunctivitis
  - [other] Vernal Keratoconjunctivitis
  - [other] Sjögren's Syndrome
    - why_kept(Ocular Cicatricial Pemphigoid): Chronic conjunctival inflammation with scarring and symblepharon
    - why_kept(Mucous Membrane Pemphigoid): Bilateral conjunctival hyperemia and scarring
    - why_kept(Atopic Keratoconjunctivitis): History of atopy and chronic maculopapular rash
    - why_kept(Vernal Keratoconjunctivitis): Bilateral conjunctival hyperemia and papillary reaction
    - why_kept(Sjögren's Syndrome): Dry eye symptoms and decreased tear production
- S4 champion: **Atopic Keratoconjunctivitis** cluster=other jaccard=0.00
- S4 rationale: The patient's history of chronic maculopapular rash suggestive of atopy or eczema, along with bilateral red eyes and itching, points towards an allergic condition. The presence of inferior symblepharon, cicatrization of the caruncle, and faint inferior punctate corneal staining also supports this diagnosis.
- S4 rejected:
  - [near] Ocular Cicatricial Pemphigoid: While it can cause symblepharon and cicatrization, the patient's lack of oral ulcers and other mucous membrane involvement makes this less likely.
  - [other] Mucous Membrane Pemphigoid: Similar to Ocular Cicatricial Pemphigoid, the absence of oral ulcers and other mucous membrane involvement reduces the likelihood of this diagnosis.
  - [other] Vernal Keratoconjunctivitis: The patient's age and the chronic nature of the symptoms are not typical for Vernal Keratoconjunctivitis, which is more common in younger individuals and has a seasonal pattern.
  - [other] Sjögren's Syndrome: The patient's Schirmer I test values were within a relatively normal range, and there was no mention of systemic symptoms such as dry mouth, which are commonly associated with Sjögren's Syndrome.

## B06 (code=`b06_ok` locus=`supervisor_ok`)
- supervisor: ['Chronic Cicatricial Conjunctivitis', 'Atopic Keratoconjunctivitis']
  clusters: {'gold': 1, 'near': 0, 'other': 1, 'empty': 0}
- discussion labels (n=15): ['Chronic Cicatricial Conjunctivitis', 'Atopic Keratoconjunctivitis', 'Blepharitis', 'Dry Eye Syndrome', 'Eczema', 'Chronic Cicatricial Conjunctivitis', 'Atopic Keratoconjunctivitis', 'Blepharitis']
- votes=3 turns=3

## B07 (code=`b07_ok` locus=`diagnose_ok`)
- draft: ['Chronic Cicatricial Conjunctivitis', 'Blepharitis']
- diagnose: ['Chronic Cicatricial Conjunctivitis', 'Blepharitis']
- queries: ['A 52-year-old Chinese man presented with bilateral red eyes and itching for 1 year. The redness was constant with intermittent tearing, without pain, gritty sensation, photophobia, or discharge. He re', 'differential diagnosis A 52-year-old Chinese man presented with bilateral red eyes and itching for 1 year. The redness was constant with intermittent tearing, without pain, gritty sensation, photophobia, or discharge. He re', 'clinical manifestations diagnosis culopapular rash over flexor and extensor surfaces of his elbows without excoriations. There were no rosacea-type or acneform facial lesions and no oral ulcers.']

## B01 (code=`b01_gen_miss` locus=`rag_hit_gen_miss`)
- top2: ['Cicatricial Pemphigoid', 'Mucous Membrane Pemphigoid']
- queries: ['chronic cicatricial conjunctivitis causes', 'atopy and ocular manifestations', 'dry eye syndrome and blurred vision', 'inferior symblepharon and conjunctival scarring']
- n_chunks=12

## APHHM
_na_

