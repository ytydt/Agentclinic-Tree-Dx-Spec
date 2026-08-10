# MCR / mcr_v1 / case 73

- **gold**: metastatic prostate carcinoma
- **layer**: `aphhm_lose`
- **correct**: e7=0 v0=0 B06=0 B07=1 B01=0 APHHM=0
- **loci**: e7=`s2_miss` B06=`agents_hit_supervisor_drop` B07=`diagnose_miss_but_scored_ok` B01=`rag_hit_gen_miss` APHHM=`tree_miss`
- **primary_locus**: APHHM=tree_miss
- **covariates**: vig_words=342; gold_words=3; eponym=False; subtype=False; e7_s2_rank=None; mapper_rescue=False
- **causal**: layer=aphhm_lose; primary loci above.

## Vignette (trunc)
A 74-year-old man with a history of metastatic prostate cancer and a known left upper lobe lung mass presented with four weeks of progressive vertigo, described as the sensation that “the floor was wobbling” and “the room was swaying,” leading to difficulty ambulating. A few days before admission, he developed severe bifrontal throbbing headaches with nausea and vomiting. Two days prior, he was evaluated at an outside emergency department, tested positive for adenovirus, and was discharged after...

## Backbone e7
- S1 key_facts: 74-year-old man with a history of metastatic prostate cancer; Known left upper lobe lung mass; Four weeks of progressive vertigo; Severe bifrontal throbbing headaches with nausea and vomiting; Positive for adenovirus at an outside emergency department; No focal motor or sensory deficits on neurologic examination; Intact coordination on dysdiadochokinesia, finger-to-nose, and heel-to-shin test; Intact gait despite dizziness
- S2 mode=complement k=3 pool_n=47 gold_in_s2=False
  - call1: ['Cerebellar metastasis from prostate cancer', 'Glioblastoma multiforme', 'Medulloblastoma', 'Hemangioblastoma', 'Cerebe
  - call2: ['Lhermitte-Duclos disease', 'Cerebellar liponeurocytoma', 'Pilocytic astrocytoma', 'Pleomorphic xanthoastrocytoma', 'An
  - call3: ['Cystic meningioma', 'Intracranial germinoma', 'Craniopharyngioma', "Rathke's cleft cyst", 'Colloid cyst', 'Pineal glan
- S3 shortlist n=5 gold=False: Cerebellar metastasis from prostate cancer, Hemangioblastoma, Cerebellar infarction, Glioblastoma multiforme, Cerebellar abscess
- S4 champion: **Cerebellar metastasis from prostate cancer** gold=False
- S4 raw (trunc): {"champion": "Cerebellar metastasis from prostate cancer", "rationale": "The patient has a history of metastatic prostate cancer and a known lung mass, and the presence of a 3 cm left cerebellar hemispheric mass with surrounding vasogenic edema is consistent with metastatic disea

## Backbone v0 (compact)
- S1 key_facts: 74-year-old man with a history of metastatic prostate cancer; Known left upper lobe lung mass; Four weeks of progressive vertigo; Severe bifrontal throbbing headaches with nausea and vomiting; Positive for adenovirus at an outside emergency department; No focal motor or sensory deficits on neurologic examination; Intact coordination on dysdiadochokinesia, finger-to-nose, and heel-to-shin test; Intact gait despite dizziness
- S2 mode=None k=None pool_n=18 gold_in_s2=False
  - pool gold matches: []
  - pool head: Cerebellar metastasis from prostate cancer, Cerebellar glioblastoma, Hemangioblastoma, Medulloblastoma, Cerebellar lymphoma, Cerebellar abscess, Cerebellar infarction, Cerebellar hemorrhage
- S3 shortlist n=5 gold=False: Cerebellar metastasis from prostate cancer, Hemangioblastoma, Cerebellar infarction, Cerebellar glioblastoma, Cerebellar abscess
- S4 champion: **Cerebellar metastasis from prostate cancer** gold=False
- S4 raw (trunc): {"champion": "Cerebellar metastasis from prostate cancer", "rationale": "The patient has a history of metastatic prostate cancer and a known lung mass, and the presence of a 3 cm left cerebellar hemispheric mass with surrounding vasogenic edema is consistent with metastatic disea

## Baseline B06
- discussion_turns=3
  - turn0 gold_mention=True diag=
    Given the patient's history of metastatic prostate cancer and the presence of a cerebellar mass, metastatic prostate cancer to the cerebellum is the most likely
  - turn1 gold_mention=True diag=
    The patient's history of metastatic prostate cancer and the presence of a cerebellar mass, as seen on noncontrast head CT and MRI, support the likelihood of met
  - turn2 gold_mention=True diag=
    The patient's history of metastatic prostate cancer and the presence of a cerebellar mass, as seen on noncontrast head CT and MRI, support the likelihood of met
- supervisor votes=3 top2=['Metastatic prostate cancer to the cerebellum', 'Hemangioblastoma'] gold=False

## Baseline B07
- draft=['Metastasis', 'Hemangioblastoma'] gold=False
- has_refine=True refine=[] gold=None
- queries(3): ['cerebellar hemispheric mass differential diagnosis', 'metastatic prostate cancer brain metastasis', 'hemangioblastoma vs metastasis']
- diagnose=['Metastasis', 'Hemangioblastoma'] gold=False

## Baseline B01
- queries=['cerebellar hemispheric mass with surrounding vasogenic edema causes of', 'metastatic prostate cancer brain metastasis symptoms and diagnosis', 'Dix-Hallpike maneuver positive diagnostic considerations', 'cystic enhancing lesion in cerebellar hemisphere differential diagnosis']
- n_chunks=12 rag_gold_mention=False
- chunk_sample: 
- top2=['Metastatic prostate cancer to the cerebellum', 'Hemangioblastoma'] gold=False

## APHHM
- tree_n=24 tree_recall=False
- gold_leaf=None
- final_n=5 final_recall=False ranking=['metastatic prostate cancer to cerebellum', 'metastatic prostate cancer to the cerebellum', 'cerebellar metastasis from prostate cancer', 'hemangioblastoma', 'cerebellar metastasis from prostate cancer']
- human_at1=False fail_mode=tree_miss

