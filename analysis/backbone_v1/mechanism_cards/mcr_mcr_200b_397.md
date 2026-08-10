# MCR / mcr_200b / case 397

- **gold**: Cancer associated microangiopathic hemolytic anemia
- **layer**: `e7_win_recall` · **layer_aphhm**: ``
- **correct**: e7=1 v0=0 B06=0 B07=0 B01=1 APHHM=
- **e7_locus**: `s3_hit_s4_miss` · **e7_fail_code**: `near_synonym_prefer`
- **mapper_rescue**: 1
- **alignment**: e7_s3_gold=1 e7_champ_cluster=near B06_sup_gold=0 B07_diag_gold=0 same_cluster_flip=0 true_entrance=0
- **APHHM**: locus=`na` code=`na` prune_e7_ok=0

## Vignette
A 51-year-old woman with a history of gastric adenocarcinoma—treated with neoadjuvant FLOT chemotherapy, gastrectomy, and adjuvant FLOT—was found one year later to have metastatic lesions in the liver, pancreas, left adrenal gland, para-aortic lymph nodes, and a lytic bone lesion in the left iliac bone. She received palliative radiotherapy (20 Gy in 4 fractions) to the L4 vertebra for back pain. On follow-up, she appeared ill but was hemodynamically stable (normal vital signs) with an ECOG performance status of 2. Cardiopulmonary examination was unremarkable; the abdomen was soft, with a palpable liver and well-healed surgical scars. A peripheral blood smear showed scattered red blood cell fragments (schistocytes) among normal red blood cells. Direct and indirect Coombs tests were negative. Laboratory results: hemoglobin 7.7 g/dL, hematocrit 23.4%, MCV 85 fL, RBC count 2.76 × 10^6/μL, platelets 22.3 × 10^3/μL, total bilirubin 2.4 mg/dL, direct bilirubin 1.2 mg/dL, indirect bilirubin 1.2 mg/dL, haptoglobin 0.0 mg/dL, LDH 1621 U/L, alkaline phosphatase 1669 U/L, PT 19 s, PTT 28.1 s, fibrinogen 208 mg/dL, INR 1.24, creatinine 0.5 mg/dL. Her PLASMIC score was 6 (high).

What is the mos…

## Backbone e7

- S2 n=52 gold_rank=16
  - clusters: gold=1 near=20 other=31
- S3 shortlist (5):
  - [other] Gastric adenocarcinoma with metastasis
  - [near] Thrombotic microangiopathy associated with cancer
  - [other] Disseminated intravascular coagulation
  - [near] Hemolytic uremic syndrome
  - [gold] Microangiopathic hemolytic anemia
    - why_kept(Gastric adenocarcinoma with metastasis): History of gastric adenocarcinoma and presence of metastatic lesions
    - why_kept(Thrombotic microangiopathy associated with cancer): Presence of schistocytes, thrombocytopenia, and elevated LDH
    - why_kept(Disseminated intravascular coagulation): Elevated PT, PTT, and fibrinogen, with thrombocytopenia and microangiopathic hemolytic anemia
    - why_kept(Hemolytic uremic syndrome): Presence of schistocytes, thrombocytopenia, and elevated LDH, with renal function preserved
    - why_kept(Microangiopathic hemolytic anemia): Presence of schistocytes, elevated LDH, and low haptoglobin
- S4 champion: **Thrombotic microangiopathy associated with cancer** cluster=near jaccard=0.25
- S4 rationale: The presence of schistocytes, low haptoglobin, elevated LDH, and thrombocytopenia in a patient with a history of cancer suggests thrombotic microangiopathy associated with cancer, which is a known complication of malignancy.
- S4 rejected:
  - [other] Gastric adenocarcinoma with metastasis: While the patient has a history of gastric adenocarcinoma with metastasis, this diagnosis does not directly explain the hematologic abnormalities.
  - [other] Disseminated intravascular coagulation: Although the patient has a high PLASMIC score, which is often associated with DIC, the presence of schistocytes and low haptoglobin points more towards a microangiopathic process rather than a consumptive coagulopathy.
  - [near] Hemolytic uremic syndrome: HUS typically presents with acute kidney injury, which is not evident in this patient, and the presence of cancer suggests a cancer-related thrombotic microangiopathy.
  - [gold] Microangiopathic hemolytic anemia: This is a key feature of thrombotic microangiopathy associated with cancer, but it is not a distinct diagnosis in this context, as the patient's condition is better explained by the broader category of thrombotic microangiopathy associated with cancer.

## B06 (code=`b06_supervisor_drop` locus=`agents_hit_supervisor_drop`)
- supervisor: ['Thrombotic Thrombocytopenic Purpura (TTP)', 'Disseminated Intravascular Coagulation (DIC)']
  clusters: {'gold': 0, 'near': 0, 'other': 2, 'empty': 0}
- discussion labels (n=15): ['Thrombotic Thrombocytopenic Purpura (TTP)', 'Disseminated Intravascular Coagulation (DIC)', 'Hemolytic Uremic Syndrome (HUS)', 'Metastatic Cancer with Hematologic Complications', 'Microangiopathic Hemolytic Anemia (MAHA)', 'Thrombotic Thrombocytopenic Purpura (TTP)', 'Disseminated Intravascular Coagulation (DIC)', 'Microangiopathic Hemolytic Anemia (MAHA)']
- votes=3 turns=3

## B07 (code=`b07_draft_miss` locus=`draft_miss`)
- draft: ['Thrombotic Thrombocytopenic Purpura (TTP)', 'Atypical Hemolytic Uremic Syndrome (aHUS)']
- diagnose: ['Thrombotic Thrombocytopenic Purpura (TTP)', 'Atypical Hemolytic Uremic Syndrome (aHUS)']
- queries: ['thrombotic microangiopathy in cancer patients', 'schistocytes in peripheral blood smear', 'high PLASMIC score diagnosis']

## B01 (code=`b01_ok` locus=`gen_ok`)
- top2: ['Thrombotic Microangiopathy', 'Microangiopathic Hemolytic Anemia']
- queries: ['microangiopathic hemolytic anemia in cancer patients', 'thrombocytopenia and schistocytes in metastatic disease', 'PLASMIC score and thrombotic microangiopathy', 'cancer-associated thrombotic microangiopathy diagnosis']
- n_chunks=12

## APHHM
_na_

