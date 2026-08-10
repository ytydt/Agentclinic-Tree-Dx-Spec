# MCR / mcr_200b / case 260

- **gold**: syphilitic aortitis
- **layer**: `e7_win_recall` · **layer_aphhm**: ``
- **correct**: e7=1 v0=1 B06=0 B07=0 B01=0 APHHM=
- **e7_locus**: `ok` · **e7_fail_code**: `ok`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=1 e7_champ_cluster=gold B06_sup_gold=0 B07_diag_gold=0 same_cluster_flip=1 true_entrance=0
- **APHHM**: locus=`na` code=`na` prune_e7_ok=0

## Vignette
A 47‐year‐old woman presented with crescendo chest pain, palpitations, and shortness of breath on exertion for two days. In the emergency department she was hypotensive, tachycardic, and tachypneic. Physical examination showed bilateral fine basal crepitations, a grade 2 decrescendo diastolic murmur, and bilateral pitting lower‐limb edema. She was an active smoker working in warehouse logistics, with no history of substance misuse or family history of cardiovascular disease.

Chest radiography demonstrated congested basal lung fields with mild bilateral pleural effusions. Electrocardiography showed ST-segment depressions in the inferior leads. Transthoracic echocardiography revealed anterior‐wall hypokinesia and moderate‐to‐severe aortic insufficiency; immobile echogenic shadows in the ascending aorta obscured the aortic valve. A computed tomography aortogram excluded aortic dissection. Urgent coronary angiography via the radial approach showed a slit-like left main coronary ostium while the remainder of the coronary arteries was free of atherosclerotic plaque.

These atypical findings prompted investigations for infectious and inflammatory aortitis. Potential causative organisms u…

## Backbone e7

- S2 n=51 gold_rank=4
  - clusters: gold=1 near=17 other=33
- S3 shortlist (5):
  - [near] Infectious aortitis
  - [other] Aortic valve endocarditis
  - [gold] Syphilitic aortitis
  - [other] Takayasu arteritis
  - [near] Aortitis due to Salmonella species
    - why_kept(Infectious aortitis): Patient has symptoms of a cardiovascular emergency, and investigations suggest aortitis, with potential causative organisms including Treponema pallidum, Mycobacterium tuberculosis, Salmonella species, Staphylococcus species, and Campylobacter jejuni
    - why_kept(Aortic valve endocarditis): Patient has a grade 2 decrescendo diastolic murmur, and echocardiography revealed moderate-to-severe aortic insufficiency, which could be due to endocarditis
    - why_kept(Syphilitic aortitis): Patient has symptoms of aortitis, and syphilis is a potential causative organism, with Treponema pallidum being considered
    - why_kept(Takayasu arteritis): Patient has symptoms of a cardiovascular emergency, and Takayasu arteritis is a rare but possible cause of aortitis
    - why_kept(Aortitis due to Salmonella species): Patient has symptoms of aortitis, and Salmonella species is a potential causative organism
- S4 champion: **Syphilitic aortitis** cluster=gold jaccard=1.00
- S4 rationale: The patient's presentation with aortic insufficiency, immobile echogenic shadows in the ascending aorta, and a slit-like left main coronary ostium, along with the consideration of Treponema pallidum as a potential causative organism, supports syphilitic aortitis as the most likely diagnosis.
- S4 rejected:
  - [near] Infectious aortitis: Too broad, as syphilitic aortitis is a specific type of infectious aortitis
  - [other] Aortic valve endocarditis: The presence of immobile echogenic shadows in the ascending aorta and a slit-like left main coronary ostium suggests aortitis rather than endocarditis
  - [other] Takayasu arteritis: Typically presents with aortic stenosis or occlusion, rather than insufficiency, and is more common in younger women
  - [near] Aortitis due to Salmonella species: Less likely given the patient's presentation and the consideration of Treponema pallidum as a potential causative organism

## B06 (code=`b06_supervisor_drop` locus=`agents_hit_supervisor_drop`)
- supervisor: ['Aortic insufficiency due to infective endocarditis', 'Aortitis due to syphilis (Treponema pallidum infection)']
  clusters: {'gold': 0, 'near': 1, 'other': 1, 'empty': 0}
- discussion labels (n=15): ['Aortic insufficiency due to infective endocarditis', 'Aortitis due to syphilis (Treponema pallidum infection)', 'Aortitis due to other infectious causes (e.g., Salmonella, Staphylococcus)', 'Takayasu arteritis', 'Giant cell arteritis', 'Aortic insufficiency due to infective endocarditis', 'Aortitis due to syphilis (Treponema pallidum infection)', 'Aortitis due to other infectious causes (e.g., Salmonella, Staphylococcus)']
- votes=3 turns=3

## B07 (code=`b07_draft_miss` locus=`draft_miss`)
- draft: ['Infectious Aortitis', 'Aortic Valve Disease']
- diagnose: ['Infectious Aortitis', 'Aortic Valve Disease']
- queries: ['aortic insufficiency causes', 'slit-like left main coronary ostium diagnosis', 'infectious aortitis symptoms', 'aortic valve disease diagnosis']

## B01 (code=`b01_gen_miss` locus=`rag_hit_gen_miss`)
- top2: ['Bicuspid Aortic Valve Disease', 'Infectious Aortitis']
- queries: ['aortic insufficiency causes', 'infectious aortitis diagnosis', 'slit-like left main coronary ostium differential diagnosis', 'aortic valve disease with systemic symptoms']
- n_chunks=12

## APHHM
_na_

