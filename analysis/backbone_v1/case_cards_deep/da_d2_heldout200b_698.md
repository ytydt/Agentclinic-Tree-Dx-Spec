# DA / d2_heldout200b / case 698

- **gold**: Concurrent pulmonary and cerebral mucormycosis
- **layer**: `e7_win_recall`
- **correct**: e7=1 v0=0 B06=0 B07=0 B01= APHHM=
- **loci**: e7=`s2_hit_s3_drop` B06=`agents_miss` B07=`draft_miss` B01=`na` APHHM=`na`
- **primary_locus**: e7=s2_hit_s3_drop; B06=agents_miss; B07=draft_miss
- **covariates**: vig_words=195; gold_words=5; eponym=False; subtype=False; e7_s2_rank=12; mapper_rescue=True
- **causal**: DA mapper_rescue: e7 S4 未命中金标但 option@1 仍对——不可记入口/终裁优势。

## Vignette (trunc)
A 66-year-old man presented with progressive right-sided limb weakness for 3 days. Past medical history included excessive smoking and thyroid nodules. No history of hypertension, diabetes, heart disease, organ transplants, intravenous drug use, or steroid administration. No headache, vomiting, unconsciousness, or seizures were reported.  Physical examination revealed:- Right hemiplegia (MRC 0/5)- Cortical motor aphasia  Laboratory Tests:- WBCs: 14.53*109/L (elevated, normal range: 3.5–9.5*109/L...

## Options
  - A: Cerebral fungal abscess (e.g., invasive aspergillosis)
  - B: Cerebral fungal infection (likely cerebral aspergillosis)
  - C: Fungal brain abscess secondary to pulmonary infection
  - D: Concurrent pulmonary and cerebral mucormycosis

## Backbone e7
- S1 key_facts: 66-year-old man; Progressive right-sided limb weakness for 3 days; Excessive smoking history; Thyroid nodules in past medical history; No history of hypertension, diabetes, or heart disease; WBC count 14.53*10^9/L; Neutrophils 79%; Blood glucose 5.82mmol/L
- S2 mode=complement k=3 pool_n=48 gold_in_s2=True
  - call1: ['Glioblastoma', 'Brain metastasis from lung cancer', 'Primary central nervous system lymphoma', 'Cerebral abscess', 'Ne
  - call2: ['Lung adenocarcinoma with brain metastasis and fungal infection', 'Squamous cell carcinoma of the lung with brain metas
  - call3: ['Lung cancer with fungal infection and brain metastasis', 'Intracranial chromoblastomycosis', 'Cerebral sporotrichosis'
- S3 shortlist n=5 gold=False: Lung cancer with brain metastasis, Intracranial fungal infection, Aspergillosis, Cerebral abscess, Glioblastoma
- S4 champion: **Intracranial fungal infection** gold=False
- S4 raw (trunc): {"champion": "Intracranial fungal infection", "rationale": "The presence of multiple fungal hyphae in the brain lesion pathology, along with the patient's symptoms and imaging findings, supports this diagnosis. The elevated WBC count and neutrophils also suggest an infectious pro

## Backbone v0 (compact)
- S1 key_facts: 66-year-old man; Progressive right-sided limb weakness for 3 days; Excessive smoking history; Thyroid nodules history; No history of hypertension, diabetes, or heart disease; No headache, vomiting, unconsciousness, or seizures; Right hemiplegia (MRC 0/5) on physical examination; Cortical motor aphasia on physical examination
- S2 mode=single k=1 pool_n=18 gold_in_s2=True
  - call1: ['Glioblastoma', 'Brain metastasis from lung cancer', 'Primary central nervous system lymphoma', 'Cerebral abscess', 'Ne
- S3 shortlist n=5 gold=False: Brain metastasis from lung cancer, Aspergillosis, Cerebral abscess, Glioblastoma, Lung cancer with brain metastasis and fungal infection
- S4 champion: **Lung cancer with brain metastasis and fungal infection** gold=False
- S4 raw (trunc): {"champion": "Lung cancer with brain metastasis and fungal infection", "rationale": "The patient's history of excessive smoking, presence of a lung mass with pleural invasion, and an intracranial lesion with severe edema and circular enhancement support the diagnosis of lung canc

## Baseline B06
- discussion_turns=3
  - turn0 gold_mention=False diag=
    The patient's presentation with progressive right-sided limb weakness, cortical motor aphasia, and the presence of a left parietal occupying lesion on MRI, alon
  - turn1 gold_mention=False diag=
    The presence of fungal hyphae in the brain lesion and the patient's history of excessive smoking support cerebral aspergillosis as a top diagnosis, while the lu
  - turn2 gold_mention=False diag=
    The patient's clinical presentation and pathological findings, including fungal hyphae in the brain lesion and a lung mass, support cerebral aspergillosis and b
- supervisor votes=3 top2=['Cerebral aspergillosis', 'Brain metastasis from lung cancer'] gold=False

## Baseline B07
- draft=['Cerebral aspergillosis with lung aspergillosis', 'Cerebral mucormycosis with lung cancer'] gold=False
- has_refine=True refine=[] gold=None
- queries(3): ['fungal brain infection with lung mass', 'cerebral fungal abscess with lung cancer', 'fungal hyphae in brain tissue with parietal lobe lesion']
- diagnose=['Cerebral aspergillosis with lung aspergillosis', 'Cerebral mucormycosis with lung cancer'] gold=False

