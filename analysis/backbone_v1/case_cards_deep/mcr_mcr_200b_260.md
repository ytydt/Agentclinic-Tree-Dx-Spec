# MCR / mcr_200b / case 260

- **gold**: syphilitic aortitis
- **layer**: `e7_win_recall`
- **correct**: e7=1 v0=1 B06=0 B07=0 B01=0 APHHM=
- **loci**: e7=`ok` B06=`agents_hit_supervisor_drop` B07=`draft_miss` B01=`rag_hit_gen_miss` APHHM=`na`
- **primary_locus**: e7=ok; B06=agents_hit_supervisor_drop; B07=draft_miss
- **covariates**: vig_words=248; gold_words=2; eponym=False; subtype=False; e7_s2_rank=4; mapper_rescue=False
- **causal**: layer=e7_win_recall; primary loci above.

## Vignette (trunc)
A 47‐year‐old woman presented with crescendo chest pain, palpitations, and shortness of breath on exertion for two days. In the emergency department she was hypotensive, tachycardic, and tachypneic. Physical examination showed bilateral fine basal crepitations, a grade 2 decrescendo diastolic murmur, and bilateral pitting lower‐limb edema. She was an active smoker working in warehouse logistics, with no history of substance misuse or family history of cardiovascular disease.  Chest radiography d...

## Backbone e7
- S1 key_facts: 47-year-old woman; Active smoker; Works in warehouse logistics; No history of substance misuse; No family history of cardiovascular disease; Hypotensive, tachycardic, and tachypneic in the emergency department; Bilateral fine basal crepitations on physical examination; Grade 2 decrescendo diastolic murmur on physical examination
- S2 mode=complement k=3 pool_n=51 gold_in_s2=True
  - call1: ['Acute aortic dissection', 'Aortic valve endocarditis', 'Infectious aortitis', 'Syphilitic aortitis', 'Takayasu arterit
  - call2: ['Bicuspid aortic valve disease', 'Aortitis due to Campylobacter jejuni', 'Salmonella aortitis', 'Staphylococcal aortiti
  - call3: ['Loeys-Dietz syndrome', 'Arteritis due to Propionibacterium acnes', 'Aortitis due to Bartonella henselae', 'Aortitis du
- S3 shortlist n=5 gold=True: Infectious aortitis, Aortic valve endocarditis, Syphilitic aortitis, Takayasu arteritis, Aortitis due to Salmonella species
- S4 champion: **Syphilitic aortitis** gold=True
- S4 raw (trunc): {"champion": "Syphilitic aortitis", "rationale": "The patient's presentation with aortic insufficiency, immobile echogenic shadows in the ascending aorta, and a slit-like left main coronary ostium, along with the consideration of Treponema pallidum as a potential causative organi

## Backbone v0 (compact)
- S1 key_facts: 47-year-old woman; Presented with crescendo chest pain, palpitations, and shortness of breath; Hypotensive, tachycardic, and tachypneic; Bilateral fine basal crepitations on physical examination; Grade 2 decrescendo diastolic murmur; Bilateral pitting lower-limb edema; Active smoker; No history of substance misuse or family history of cardiovascular disease
- S2 mode=single k=1 pool_n=19 gold_in_s2=True
  - call1: ['Acute aortic dissection', 'Aortic insufficiency', 'Aortic regurgitation', 'Syphilitic aortitis', 'Tuberculous aortitis
- S3 shortlist n=5 gold=True: Syphilitic aortitis, Takayasu arteritis, Aortic valve endocarditis, Acute aortic dissection, Staphylococcal aortitis
- S4 champion: **Syphilitic aortitis** gold=True
- S4 raw (trunc): {"champion": "Syphilitic aortitis", "rationale": "The patient's presentation with aortic insufficiency, immobile echogenic shadows in the ascending aorta, and the exclusion of other causes such as aortic dissection, along with the consideration of Treponema pallidum as a potentia

## Baseline B06
- discussion_turns=3
  - turn0 gold_mention=True diag=
    The patient's presentation with crescendo chest pain, palpitations, and shortness of breath, along with the physical examination and imaging findings, suggests 
  - turn1 gold_mention=True diag=
    The patient's symptoms and imaging findings align with Doctor A's suggestions, with aortic insufficiency due to infective endocarditis being the most likely dia
  - turn2 gold_mention=True diag=
    The patient's presentation and imaging findings are consistent with an infectious or inflammatory aortic condition, with aortic insufficiency due to infective e
- supervisor votes=3 top2=['Aortic insufficiency due to infective endocarditis', 'Aortitis due to syphilis (Treponema pallidum infection)'] gold=False

## Baseline B07
- draft=['Infectious Aortitis', 'Aortic Valve Disease'] gold=False
- has_refine=True refine=[] gold=None
- queries(4): ['aortic insufficiency causes', 'slit-like left main coronary ostium diagnosis', 'infectious aortitis symptoms', 'aortic valve disease diagnosis']
- diagnose=['Infectious Aortitis', 'Aortic Valve Disease'] gold=False

## Baseline B01
- queries=['aortic insufficiency causes', 'infectious aortitis diagnosis', 'slit-like left main coronary ostium differential diagnosis', 'aortic valve disease with systemic symptoms']
- n_chunks=12 rag_gold_mention=False
- chunk_sample: 
- top2=['Bicuspid Aortic Valve Disease', 'Infectious Aortitis'] gold=False

