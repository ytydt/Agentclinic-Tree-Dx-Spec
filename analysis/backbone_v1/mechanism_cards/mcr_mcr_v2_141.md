# MCR / mcr_v2 / case 141

- **gold**: Rhegmatogenous retinal detachment with choroidal detachment
- **layer**: `all_miss_but_recalled` · **layer_aphhm**: ``
- **correct**: e7=0 v0=0 B06=0 B07=0 B01=0 APHHM=
- **e7_locus**: `s2_hit_s3_drop` · **e7_fail_code**: `s2_near_crowd_out`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=0 e7_champ_cluster=other B06_sup_gold=0 B07_diag_gold=0 same_cluster_flip=0 true_entrance=0
- **APHHM**: locus=`na` code=`na` prune_e7_ok=0

## Vignette
A 71-year-old woman presented with a 1-week history of painful vision loss and floaters in her left eye. She had no history of myopia, ocular trauma, or surgery. Visual acuity was 20/30–2 in the right eye and 20/80 in the left eye; intraocular pressure was 21 mm Hg OD and 17 mm Hg OS. The right eye was normal except for a mild nuclear sclerotic cataract and no inflammation. The left eye had rare anterior chamber cells, 1+ vitreous cells, choroidal detachments in the nasal and temporal periphery, and an overlying retinal detachment with shifting subretinal fluid; no retinal breaks were identified. Her medical history was unremarkable. Laboratory studies (CBC, basic metabolic panel, HIV, T-spot, syphilis screen, and ANCA panel) were normal. MRI of the brain and orbits showed mild posterior scleral enhancement but no intraocular mass. Fluorescein angiography showed late leakage in the temporal periphery; fundus autofluorescence was normal; optical coherence tomography revealed shallow subretinal fluid and a posterior vitreous detachment. She was started on 80 mg oral prednisone for presumed serous retinal detachment secondary to posterior scleritis. Two weeks later, the choroidal deta…

## Backbone e7

- S2 n=52 gold_rank=3
  - clusters: gold=1 near=11 other=40
- S3 shortlist (5):
  - [other] Posterior Scleritis
  - [near] Serous Retinal Detachment
  - [other] Uveitis
  - [other] Vogt-Koyanagi-Harada Disease
  - [other] Sarcoidosis
    - why_kept(Posterior Scleritis): Mild posterior scleral enhancement on MRI and clinical presentation of painful vision loss with choroidal detachments
    - why_kept(Serous Retinal Detachment): Clinical presentation of retinal detachment with shifting subretinal fluid and no retinal breaks identified
    - why_kept(Uveitis): Presence of rare anterior chamber cells and 1+ vitreous cells in the left eye
    - why_kept(Vogt-Koyanagi-Harada Disease): Clinical presentation of painful vision loss with choroidal detachments and retinal detachment
    - why_kept(Sarcoidosis): Normal laboratory studies and presence of rare anterior chamber cells and 1+ vitreous cells in the left eye, which could be indicative of granulomatous uveitis
- S4 champion: **Posterior Scleritis** cluster=other jaccard=0.00
- S4 rationale: The presence of mild posterior scleral enhancement on MRI, late leakage in the temporal periphery on fluorescein angiography, and the resolution of choroidal detachments with prednisone treatment support the diagnosis of posterior scleritis.
- S4 rejected:
  - [near] Serous Retinal Detachment: While the patient has a serous retinal detachment, it is likely secondary to the posterior scleritis.
  - [other] Uveitis: The rare anterior chamber cells and 1+ vitreous cells could suggest uveitis, but the overall clinical picture and imaging findings are more consistent with posterior scleritis.
  - [other] Vogt-Koyanagi-Harada Disease: The lack of systemic symptoms, skin findings, and audiovestibular symptoms makes Vogt-Koyanagi-Harada disease less likely.
  - [other] Sarcoidosis: The normal laboratory studies, including ANCA panel, and the absence of other systemic symptoms or findings suggestive of sarcoidosis make this diagnosis less likely.

## B06 (code=`b06_supervisor_drop` locus=`agents_hit_supervisor_drop`)
- supervisor: ['Posterior Scleritis', 'Serous Retinal Detachment']
  clusters: {'gold': 0, 'near': 1, 'other': 1, 'empty': 0}
- discussion labels (n=15): ['Posterior Scleritis', 'Serous Retinal Detachment', 'Uveitis', 'Choroidal Detachment', 'Vogt-Koyanagi-Harada Disease', 'Posterior Scleritis', 'Serous Retinal Detachment', 'Uveitis']
- votes=3 turns=3

## B07 (code=`b07_draft_miss` locus=`draft_miss`)
- draft: ['Posterior Scleritis', 'Serous Retinal Detachment']
- diagnose: ['Posterior Scleritis', 'Serous Retinal Detachment']
- queries: ['posterior scleritis diagnosis', 'serous retinal detachment causes', 'choroidal detachment treatment']

## B01 (code=`b01_gen_miss` locus=`rag_hit_gen_miss`)
- top2: ['Posterior Scleritis', 'Exudative Retinal Detachment']
- queries: ['causes of serous retinal detachment', 'posterior scleritis diagnosis and treatment', 'differential diagnosis for choroidal detachments', 'persistent retinal detachment despite corticosteroid treatment']
- n_chunks=12

## APHHM
_na_

