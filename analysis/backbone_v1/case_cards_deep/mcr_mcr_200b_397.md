# MCR / mcr_200b / case 397

- **gold**: Cancer associated microangiopathic hemolytic anemia
- **layer**: `e7_win_recall`
- **correct**: e7=1 v0=0 B06=0 B07=0 B01=1 APHHM=
- **loci**: e7=`s3_hit_s4_miss` B06=`agents_hit_supervisor_drop` B07=`draft_miss` B01=`gen_ok` APHHM=`na`
- **primary_locus**: e7=s3_hit_s4_miss; B06=agents_hit_supervisor_drop; B07=draft_miss
- **covariates**: vig_words=241; gold_words=5; eponym=False; subtype=False; e7_s2_rank=16; mapper_rescue=False
- **causal**: 骨干 S3 含金标，S4 终裁选错。

## Vignette (trunc)
A 51-year-old woman with a history of gastric adenocarcinoma—treated with neoadjuvant FLOT chemotherapy, gastrectomy, and adjuvant FLOT—was found one year later to have metastatic lesions in the liver, pancreas, left adrenal gland, para-aortic lymph nodes, and a lytic bone lesion in the left iliac bone. She received palliative radiotherapy (20 Gy in 4 fractions) to the L4 vertebra for back pain. On follow-up, she appeared ill but was hemodynamically stable (normal vital signs) with an ECOG perfo...

## Backbone e7
- S1 key_facts: 51-year-old woman with history of gastric adenocarcinoma; Treated with neoadjuvant FLOT chemotherapy, gastrectomy, and adjuvant FLOT; Metastatic lesions in liver, pancreas, left adrenal gland, para-aortic lymph nod; Received palliative radiotherapy to L4 vertebra for back pain; ECOG performance status of 2; Hemoglobin 7.7 g/dL, hematocrit 23.4%, MCV 85 fL, RBC count 2.76 × 10^6/μL; Platelets 22.3 × 10^3/μL; Total bilirubin 2.4 mg/dL, direct bilirubin 1.2 mg/dL, indirect bilirubin 1.2 mg
- S2 mode=complement k=3 pool_n=52 gold_in_s2=True
  - call1: ['Thrombotic thrombocytopenic purpura', 'Hemolytic uremic syndrome', 'Disseminated intravascular coagulation', 'Gastric 
  - call2: ['Intrahepatic cholangiocarcinoma with hemolytic anemia', 'Hepatic epithelioid hemangioendothelioma', 'Gastric adenocarc
  - call3: ['Atypical hemolytic uremic syndrome', 'Thrombotic microangiopathy associated with cancer', 'Hemophagocytic lymphohistio
- S3 shortlist n=5 gold=True: Gastric adenocarcinoma with metastasis, Thrombotic microangiopathy associated with cancer, Disseminated intravascular coagulation, Hemolytic uremic syndrome, Microangiopathic hemolytic anemia
- S4 champion: **Thrombotic microangiopathy associated with cancer** gold=False
- S4 raw (trunc): {"champion": "Thrombotic microangiopathy associated with cancer", "rationale": "The presence of schistocytes, low haptoglobin, elevated LDH, and thrombocytopenia in a patient with a history of cancer suggests thrombotic microangiopathy associated with cancer, which is a known com

## Backbone v0 (compact)
- S1 key_facts: History of gastric adenocarcinoma; Treated with neoadjuvant FLOT chemotherapy, gastrectomy, and adjuvant FLOT; Metastatic lesions in liver, pancreas, left adrenal gland, para-aortic lymph nod; Received palliative radiotherapy to the L4 vertebra for back pain; ECOG performance status of 2; Hemoglobin 7.7 g/dL; Hematocrit 23.4%; Platelets 22.3 × 10^3/μL
- S2 mode=single k=1 pool_n=17 gold_in_s2=False
  - call1: ['Disseminated intravascular coagulation', 'Thrombotic thrombocytopenic purpura', 'Hemolytic uremic syndrome', 'Gastric 
- S3 shortlist n=5 gold=False: Disseminated intravascular coagulation, Thrombotic thrombocytopenic purpura, Gastric adenocarcinoma with metastasis, Hepatic metastasis from gastric cancer, Hemolytic uremic syndrome
- S4 champion: **Disseminated intravascular coagulation** gold=False
- S4 raw (trunc): {"champion": "Disseminated intravascular coagulation", "rationale": "The patient's laboratory results show a low platelet count (22.3 × 10^3/μL), elevated LDH (1621 U/L), and low haptoglobin (0.0 mg/dL), which are indicative of a consumptive coagulopathy. The presence of schistoc

## Baseline B06
- discussion_turns=3
  - turn0 gold_mention=True diag=
    The patient's presentation with schistocytes on peripheral blood smear, negative Coombs tests, and elevated LDH and bilirubin levels, along with thrombocytopeni
  - turn1 gold_mention=True diag=
    The patient's clinical presentation and laboratory results, including schistocytes, thrombocytopenia, and elevated LDH, are consistent with a thrombotic microan
  - turn2 gold_mention=True diag=
    The patient's presentation with schistocytes, thrombocytopenia, and elevated LDH, along with a high PLASMIC score, supports a diagnosis of TTP or another thromb
- supervisor votes=3 top2=['Thrombotic Thrombocytopenic Purpura (TTP)', 'Disseminated Intravascular Coagulation (DIC)'] gold=False

## Baseline B07
- draft=['Thrombotic Thrombocytopenic Purpura (TTP)', 'Atypical Hemolytic Uremic Syndrome (aHUS)'] gold=False
- has_refine=True refine=[] gold=None
- queries(3): ['thrombotic microangiopathy in cancer patients', 'schistocytes in peripheral blood smear', 'high PLASMIC score diagnosis']
- diagnose=['Thrombotic Thrombocytopenic Purpura (TTP)', 'Atypical Hemolytic Uremic Syndrome (aHUS)'] gold=False

## Baseline B01
- queries=['microangiopathic hemolytic anemia in cancer patients', 'thrombocytopenia and schistocytes in metastatic disease', 'PLASMIC score and thrombotic microangiopathy', 'cancer-associated thrombotic microangiopathy diagnosis']
- n_chunks=12 rag_gold_mention=False
- chunk_sample: 
- top2=['Thrombotic Microangiopathy', 'Microangiopathic Hemolytic Anemia'] gold=True

