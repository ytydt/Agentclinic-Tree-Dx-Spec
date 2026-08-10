# MCR / mcr_v1 / case 73

- **gold**: metastatic prostate carcinoma
- **layer**: `aphhm_lose` · **layer_aphhm**: `aphhm_lose`
- **correct**: e7=0 v0=0 B06=0 B07=1 B01=0 APHHM=0
- **e7_locus**: `s2_miss` · **e7_fail_code**: `s2_miss`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=0 e7_champ_cluster=near B06_sup_gold=0 B07_diag_gold=0 same_cluster_flip=0 true_entrance=0
- **APHHM**: locus=`tree_miss` code=`aphhm_tree_miss` prune_e7_ok=0

## Vignette
A 74-year-old man with a history of metastatic prostate cancer and a known left upper lobe lung mass presented with four weeks of progressive vertigo, described as the sensation that “the floor was wobbling” and “the room was swaying,” leading to difficulty ambulating. A few days before admission, he developed severe bifrontal throbbing headaches with nausea and vomiting. Two days prior, he was evaluated at an outside emergency department, tested positive for adenovirus, and was discharged after supportive treatment without symptom relief.

His oncology history included stage III prostate adenocarcinoma treated with prostatectomy and radiation in 2013, followed by detection of bilateral lung nodules and sclerotic bone lesions in 2016, and a 2020 biopsy of a left upper lobe lesion confirming mismatch repair deficient, androgen receptor–positive metastatic prostate cancer treated with enzalutamide, then abiraterone acetate and prednisone, and palliative radiation.

On presentation, vital signs were: temperature 37°C, heart rate 90 beats/min, blood pressure 164/81 mm Hg, and oxygen saturation 93% on room air. Neurologic examination revealed no focal motor or sensory deficits; intact c…

## Backbone e7

- S2 n=47 gold_rank=None
  - clusters: gold=0 near=2 other=45
- S3 shortlist (5):
  - [near] Cerebellar metastasis from prostate cancer
  - [other] Hemangioblastoma
  - [other] Cerebellar infarction
  - [other] Glioblastoma multiforme
  - [other] Cerebellar abscess
    - why_kept(Cerebellar metastasis from prostate cancer): History of metastatic prostate cancer and presence of a cerebellar mass
    - why_kept(Hemangioblastoma): Cystic enhancing lesion in the left cerebellar hemisphere and absence of abnormal hyperemia on cerebral angiography
    - why_kept(Cerebellar infarction): Sudden onset of vertigo and headaches, with a cerebellar mass and surrounding edema
    - why_kept(Glioblastoma multiforme): Presence of a cerebellar mass with surrounding vasogenic edema and a cystic enhancing lesion on MRI
    - why_kept(Cerebellar abscess): Severe headaches and nausea, with a cerebellar mass and surrounding edema, and a recent history of adenovirus infection
- S4 champion: **Cerebellar metastasis from prostate cancer** cluster=near jaccard=0.14
- S4 rationale: The patient has a history of metastatic prostate cancer and a known lung mass, and the presence of a 3 cm left cerebellar hemispheric mass with surrounding vasogenic edema is consistent with metastatic disease.
- S4 rejected:
  - [other] Hemangioblastoma: While considered a leading diagnosis, the patient's history of metastatic cancer makes metastasis a more likely explanation for the cerebellar mass.
  - [other] Cerebellar infarction: The presence of a mass with surrounding vasogenic edema and a cystic enhancing lesion on MRI is not typical of infarction.
  - [other] Glioblastoma multiforme: There is no mention of a primary brain tumor or typical glioblastoma multiforme symptoms, and the patient's history of metastatic cancer is a more likely explanation for the cerebellar mass.
  - [other] Cerebellar abscess: The patient's symptoms and imaging findings do not suggest an abscess, and the recent diagnosis of adenovirus is not directly related to the cerebellar mass.

## B06 (code=`b06_supervisor_drop` locus=`agents_hit_supervisor_drop`)
- supervisor: ['Metastatic prostate cancer to the cerebellum', 'Hemangioblastoma']
  clusters: {'gold': 0, 'near': 1, 'other': 1, 'empty': 0}
- discussion labels (n=15): ['Metastatic prostate cancer to the cerebellum', 'Hemangioblastoma', 'Cerebellar infarction', 'Adenovirus-related cerebellitis', 'Brain metastasis from other primary cancer', 'Metastatic prostate cancer to the cerebellum', 'Hemangioblastoma', 'Cerebellar infarction']
- votes=3 turns=3

## B07 (code=`b07_mapper_rescue` locus=`diagnose_miss_but_scored_ok`)
- draft: ['Metastasis', 'Hemangioblastoma']
- diagnose: ['Metastasis', 'Hemangioblastoma']
- queries: ['cerebellar hemispheric mass differential diagnosis', 'metastatic prostate cancer brain metastasis', 'hemangioblastoma vs metastasis']

## B01 (code=`b01_gen_miss` locus=`rag_hit_gen_miss`)
- top2: ['Metastatic prostate cancer to the cerebellum', 'Hemangioblastoma']
- queries: ['cerebellar hemispheric mass with surrounding vasogenic edema causes of', 'metastatic prostate cancer brain metastasis symptoms and diagnosis', 'Dix-Hallpike maneuver positive diagnostic considerations', 'cystic enhancing lesion in cerebellar hemisphere differential diagnosis']
- n_chunks=12

## APHHM
- tree_n=24 final_n=5
- final: ['metastatic prostate cancer to cerebellum', 'metastatic prostate cancer to the cerebellum', 'cerebellar metastasis from prostate cancer', 'hemangioblastoma', 'cerebellar metastasis from prostate cancer']
- tree gold_cluster_n=0 final gold=False

