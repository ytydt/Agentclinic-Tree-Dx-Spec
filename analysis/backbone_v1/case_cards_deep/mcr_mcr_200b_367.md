# MCR / mcr_200b / case 367

- **gold**: Cicatricial conjunctivitis
- **layer**: `base_win_recall`
- **correct**: e7=0 v0=0 B06=1 B07=1 B01=0 APHHM=
- **loci**: e7=`s2_miss` B06=`supervisor_ok` B07=`diagnose_ok` B01=`rag_hit_gen_miss` APHHM=`na`
- **primary_locus**: e7=s2_miss; B06=supervisor_ok
- **covariates**: vig_words=362; gold_words=2; eponym=False; subtype=False; e7_s2_rank=None; mapper_rescue=False
- **causal**: 骨干入口完全未召回；基线直接给出金标/近义。

## Vignette (trunc)
A 52-year-old Chinese man presented with bilateral red eyes and itching for 1 year. The redness was constant with intermittent tearing, without pain, gritty sensation, photophobia, or discharge. He reported episodic blurred vision due to dry eye, relieved by lubricants. He denied diplopia. His medical history included type 2 diabetes, hypertension, dyslipidemia (all treated), and a chronic maculopapular rash on the chest and arms suggestive of atopy or eczema. He had no sinusitis, asthma, other ...

## Backbone e7
- S1 key_facts: 52-year-old Chinese man; Bilateral red eyes and itching for 1 year; Intermittent tearing without pain, gritty sensation, photophobia, or discharge; Episodic blurred vision due to dry eye relieved by lubricants; Denies diplopia; Medical history includes type 2 diabetes, hypertension, dyslipidemia, and chroni; No sinusitis, asthma, other autoimmune or dermatologic disorders, drug allergies; Normal vital signs
- S2 mode=complement k=3 pool_n=51 gold_in_s2=False
  - call1: ['Mucous Membrane Pemphigoid', 'Stevens-Johnson Syndrome', 'Ocular Cicatricial Pemphigoid', 'Chronic Graft-Versus-Host D
  - call2: ['Chronic Blepharitis', 'Meibomian Gland Dysfunction', 'Rosacea-Associated Blepharitis', 'Seborrheic Blepharitis', 'Atop
  - call3: ['Lymphomatoid Granulomatosis', 'Angiolymphoid Hyperplasia with Eosinophilia', 'Eosinophilic Cellulitis', 'Necrobiotic X
- S3 shortlist n=5 gold=False: Ocular Cicatricial Pemphigoid, Mucous Membrane Pemphigoid, Atopic Keratoconjunctivitis, Vernal Keratoconjunctivitis, Sjögren's Syndrome
- S4 champion: **Atopic Keratoconjunctivitis** gold=False
- S4 raw (trunc): {"champion": "Atopic Keratoconjunctivitis", "rationale": "The patient's history of chronic maculopapular rash suggestive of atopy or eczema, along with bilateral red eyes and itching, points towards an allergic condition. The presence of inferior symblepharon, cicatrization of th

## Backbone v0 (compact)
- S1 key_facts: 52-year-old Chinese man; Bilateral red eyes and itching for 1 year; Intermittent tearing without pain, gritty sensation, photophobia, or discharge; Episodic blurred vision due to dry eye relieved by lubricants; Denies diplopia; Medical history includes type 2 diabetes, hypertension, dyslipidemia, and chroni; No sinusitis, asthma, other autoimmune or dermatologic disorders, drug allergies; Normal vital signs
- S2 mode=single k=1 pool_n=21 gold_in_s2=False
  - call1: ['Mucous Membrane Pemphigoid', 'Stevens-Johnson Syndrome', 'Ocular Cicatricial Pemphigoid', 'Chronic Graft-Versus-Host D
- S3 shortlist n=5 gold=False: Mucous Membrane Pemphigoid, Ocular Cicatricial Pemphigoid, Atopic Keratoconjunctivitis, Vernal Keratoconjunctivitis, Sjogren's Syndrome
- S4 champion: **Ocular Cicatricial Pemphigoid** gold=False
- S4 raw (trunc): {"champion": "Ocular Cicatricial Pemphigoid", "rationale": "The presence of bilateral moderate diffuse bulbar conjunctival hyperemia, grade 1 subtarsal papillary reaction, inferior symblepharon, and cicatrization of the caruncle are characteristic findings of Ocular Cicatricial P

## Baseline B06
- discussion_turns=3
  - turn0 gold_mention=True diag=
    The patient's presentation of bilateral red eyes, itching, and episodic blurred vision due to dry eye, along with a history of atopy and a maculopapular rash, s
  - turn1 gold_mention=True diag=
    The patient's symptoms and examination findings, including bilateral red eyes, itching, and episodic blurred vision due to dry eye, along with a history of atop
  - turn2 gold_mention=True diag=
    The patient's presentation and examination findings align with the clinical diagnosis of chronic cicatricial conjunctivitis, consistent with the assessments of 
- supervisor votes=3 top2=['Chronic Cicatricial Conjunctivitis', 'Atopic Keratoconjunctivitis'] gold=True

## Baseline B07
- draft=['Chronic Cicatricial Conjunctivitis', 'Blepharitis'] gold=True
- has_refine=True refine=[] gold=None
- queries(3): ['A 52-year-old Chinese man presented with bilateral red eyes and itching for 1 year. The redness was constant with intermittent tearing, without pain, gritty sensation, photophobia, or discharge. He re', 'differential diagnosis A 52-year-old Chinese man presented with bilateral red eyes and itching for 1 year. The redness was constant with intermittent tearing, without pain, gritty sensation, photophobia, or discharge. He re', 'clinical manifestations diagnosis culopapular rash over flexor and extensor surfaces of his elbows without excoriations. There were no rosacea-type or acneform facial lesions and no oral ulcers.']
- diagnose=['Chronic Cicatricial Conjunctivitis', 'Blepharitis'] gold=True

## Baseline B01
- queries=['chronic cicatricial conjunctivitis causes', 'atopy and ocular manifestations', 'dry eye syndrome and blurred vision', 'inferior symblepharon and conjunctival scarring']
- n_chunks=12 rag_gold_mention=False
- chunk_sample: 
- top2=['Cicatricial Pemphigoid', 'Mucous Membrane Pemphigoid'] gold=False

