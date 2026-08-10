# MCR / mcr_v1 / case 38

- **gold**: trigeminal schwannoma
- **layer**: `e7_win_rank` · **layer_aphhm**: `aphhm_lose`
- **correct**: e7=1 v0=1 B06=0 B07=0 B01=0 APHHM=0
- **e7_locus**: `ok` · **e7_fail_code**: `ok`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=1 e7_champ_cluster=gold B06_sup_gold=1 B07_diag_gold=0 same_cluster_flip=1 true_entrance=0
- **APHHM**: locus=`tree_hit_final_drop` code=`aphhm_prune` prune_e7_ok=1

## Vignette
A 33-year-old man with no significant past medical history presented with a 3-month history of progressively worsening occipital headache, exacerbated by Valsalva maneuvers. On neurologic examination, he had bilateral past-pointing and an intention tremor. Brain MRI revealed a 6.9 × 5.5 × 6.1 cm lobulated mass centered at the left cerebellopontine angle, extending craniocaudally from the left ambient cistern to the premedullary space. The lesion involved and expanded Meckel’s cave, with a small extension into the left infratemporal fossa via the foramen ovale. It contained multiloculated T1-hypointense, T2-FLAIR–partially suppressible nonenhancing cystic areas with interspersed enhancing septa, as well as T1/T2-isointense enhancing solid components. Susceptibility-weighted imaging demonstrated curvilinear signal loss with corresponding T1 hyperintensity consistent with hemorrhagic foci, and diffusion-weighted imaging showed no diffusion restriction. There was compression of the left cerebellum and brainstem, dilation of the third, fourth, and lateral ventricles, anterior displacement of the cavernous sinus, and encasement with mild narrowing of the left petrous internal carotid art…

## Backbone e7

- S2 n=49 gold_rank=10
  - clusters: gold=1 near=2 other=46
- S3 shortlist (5):
  - [near] Vestibular schwannoma
  - [other] Meningioma
  - [gold] Trigeminal schwannoma
  - [other] Chordoma
  - [other] Epidermoid cyst
    - why_kept(Vestibular schwannoma): Common cause of cerebellopontine angle syndrome with gradual onset of symptoms
    - why_kept(Meningioma): Possible cause of progressive cerebellopontine angle syndrome with involvement of Meckel's cave and compression of adjacent structures
    - why_kept(Trigeminal schwannoma): Less common but plausible cause of cerebellopontine angle syndrome with involvement of Meckel's cave and extension into the infratemporal fossa
    - why_kept(Chordoma): Rare but possible cause of cerebellopontine angle syndrome with destructive bone lesions and extension into the premedullary space
    - why_kept(Epidermoid cyst): Possible cause of cerebellopontine angle syndrome with cystic components and gradual onset of symptoms
- S4 champion: **Trigeminal schwannoma** cluster=gold jaccard=1.00
- S4 rationale: The tumor's location centered at the left cerebellopontine angle, involvement and expansion of Meckel's cave, and extension into the left infratemporal fossa via the foramen ovale are consistent with a trigeminal schwannoma, which typically arises from the trigeminal nerve and can involve Meckel's cave.
- S4 rejected:
  - [near] Vestibular schwannoma: Vestibular schwannomas typically arise from the vestibular nerve and are centered at the internal auditory canal, which is not the primary location of the mass in this case.
  - [other] Meningioma: Meningiomas often have a dural tail sign and are typically more solid and homogeneously enhancing, which does not match the multiloculated and partially suppressible nonenhancing cystic areas with interspersed enhancing septa seen in this case.
  - [other] Chordoma: Chordomas typically arise from the clivus and have a more midline location, which does not match the lateral location of the mass in this case centered at the cerebellopontine angle.
  - [other] Epidermoid cyst: Epidermoid cysts are typically T1-hypointense and T2-hyperintense without enhancement, and do not have the solid components or hemorrhagic foci seen in this case.

## B06 (code=`b06_judge_miss` locus=`supervisor_hit_judge_miss`)
- supervisor: ['Schwannoma', 'Meningioma']
  clusters: {'gold': 1, 'near': 0, 'other': 1, 'empty': 0}
- discussion labels (n=15): ['Schwannoma', 'Meningioma', 'Hemangioblastoma', 'Chordoma', 'Epidermoid cyst', 'Schwannoma', 'Meningioma', 'Hemangioblastoma']
- votes=3 turns=3

## B07 (code=`b07_draft_miss` locus=`draft_miss`)
- draft: ['Chordoma', 'Chondrosarcoma']
- diagnose: ['Chordoma', 'Chondrosarcoma']
- queries: ['cerebellopontine angle tumor', "Meckel's cave involvement", 'lobulated mass with cystic and solid components', 'hemorrhagic foci in brain tumor']

## B01 (code=`b01_judge_miss` locus=`gen_hit_judge_miss`)
- top2: ['Chordoma', 'Schwannoma']
- queries: ['cerebellopontine angle mass with cystic and solid components', "Meckel's cave involvement with multiloculated cystic areas", 'cranial nerve compression with intention tremor and past-pointing', 'petrous apex erosion with calcifications and hemorrhagic foci']
- n_chunks=12

## APHHM
- tree_n=34 final_n=5
- final: ['Meningioma', 'Meningioma', 'Chordoma', 'Meningioma', 'Meningioma']
- tree gold_cluster_n=2 final gold=False

