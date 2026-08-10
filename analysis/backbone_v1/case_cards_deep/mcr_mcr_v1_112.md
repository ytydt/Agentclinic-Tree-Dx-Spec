# MCR / mcr_v1 / case 112

- **gold**: Bath salt intoxication
- **layer**: `aphhm_lose`
- **correct**: e7=1 v0=0 B06=0 B07=1 B01=0 APHHM=0
- **loci**: e7=`s2_miss` B06=`agents_miss` B07=`diagnose_miss_but_scored_ok` B01=`rag_miss` APHHM=`tree_miss`
- **primary_locus**: APHHM=tree_miss
- **covariates**: vig_words=407; gold_words=3; eponym=False; subtype=False; e7_s2_rank=None; mapper_rescue=False
- **causal**: layer=aphhm_lose; primary loci above.

## Vignette (trunc)
A 29-year-old Caucasian man with a history of hepatitis C, posttraumatic stress disorder, polysubstance abuse, and tobacco use was brought to the emergency department after being found agitated and erratically wandering the streets and then unresponsive with multiple skin abrasions. He reported ingestion and insufflation of “bath salts,” a history later confirmed by his family. He denied other medications or supplements and had no known drug allergies.  On examination, temperature was 107°F, blo...

## Backbone e7
- S1 key_facts: 29-year-old Caucasian man with history of hepatitis C, PTSD, polysubstance abuse; Ingestion and insufflation of 'bath salts' reported by patient and confirmed by ; Denies other medications or supplements and has no known drug allergies; Temperature of 107°F, blood pressure 91/52 mm Hg, and pulse 93/min on examinatio; Confused and intermittently agitated with pupils 3 mm and equal; Weak peripheral pulses without jugular venous distention or murmurs; Lungs clear, abdomen soft, and no focal neurologic deficits; Laboratory studies show severe rhabdomyolysis and chronic hepatitis C
- S2 mode=complement k=3 pool_n=48 gold_in_s2=False
  - call1: ['Neuroleptic Malignant Syndrome', 'Serotonin Syndrome', 'Malignant Hyperthermia', 'Sympathomimetic Toxicity', 'Antichol
  - call2: ['Dantrolene-resistant Malignant Hyperthermia', 'Exertional Heat Stroke with Rhabdomyolysis', 'Catecholamine-induced Car
  - call3: ['Malignant Catatonia', 'Dopamine Agonist Withdrawal Syndrome', 'Acute Porphyria', 'Status Asthmaticus', 'Carcinoid Cris
- S3 shortlist n=5 gold=False: Sympathomimetic Toxicity, Bath Salts Intoxication, Serotonin Syndrome, Malignant Hyperthermia, Neuroleptic Malignant Syndrome
- S4 champion: **Bath Salts Intoxication** gold=False
- S4 raw (trunc): {"champion": "Bath Salts Intoxication", "rationale": "The patient's reported ingestion and insufflation of 'bath salts' and the presence of severe symptoms such as hyperthermia, agitation, and rhabdomyolysis are consistent with bath salts intoxication", "rejected": [{"label": "Sy

## Backbone v0 (compact)
- S1 key_facts: 29-year-old Caucasian man; History of hepatitis C, posttraumatic stress disorder, polysubstance abuse, and ; Found agitated and erratically wandering the streets; Reported ingestion and insufflation of 'bath salts'; Denied other medications or supplements; No known drug allergies; Temperature of 107°F on examination; Blood pressure 91/52 mm Hg and pulse 93/min
- S2 mode=None k=None pool_n=18 gold_in_s2=False
  - pool gold matches: []
  - pool head: Neuroleptic malignant syndrome, Serotonin syndrome, Malignant hyperthermia, Sympathomimetic toxicity, Anticholinergic toxicity, Salicylate toxicity, Amphetamine toxicity, Cocaine toxicity
- S3 shortlist n=5 gold=False: Sympathomimetic toxicity, Serotonin syndrome, Neuroleptic malignant syndrome, Malignant hyperthermia, Rhabdomyolysis due to drug-induced immobilization
- S4 champion: **Sympathomimetic toxicity** gold=False
- S4 raw (trunc): {"champion": "Sympathomimetic toxicity", "rationale": "The patient's symptoms, including agitation, confusion, hyperthermia, tachycardia, and hypertension, are consistent with sympathomimetic toxicity, which can be caused by the ingestion of 'bath salts' that often contain synthe

## Baseline B06
- discussion_turns=3
  - turn0 gold_mention=False diag=
    The patient's presentation of severe rhabdomyolysis, hyperthermia, and acute kidney injury, in combination with a history of polysubstance abuse and confirmed i
  - turn1 gold_mention=False diag=
    The patient's severe presentation, including hyperthermia, rhabdomyolysis, and acute kidney injury, along with a history of bath salts ingestion, aligns with sy
  - turn2 gold_mention=False diag=
    Agreeing with prior opinions, the patient's severe presentation and history of bath salts ingestion confirm sympathomimetic toxicity as the primary diagnosis, w
- supervisor votes=3 top2=['Sympathomimetic toxicity', 'Rhabdomyolysis'] gold=False

## Baseline B07
- draft=['Synthetic cathinone toxicity', 'Rhabdomyolysis due to multiple factors'] gold=False
- has_refine=True refine=[] gold=None
- queries(4): ['bath salts toxicity symptoms', 'rhabdomyolysis causes', 'severe hyperthermia treatment', 'hyperkalemia management']
- diagnose=['Synthetic cathinone toxicity', 'Rhabdomyolysis due to multiple factors'] gold=False

## Baseline B01
- queries=['severe rhabdomyolysis causes', 'bath salts toxicity symptoms', 'hyperthermia treatment in critically ill patients', 'acute kidney injury after rhabdomyolysis']
- n_chunks=12 rag_gold_mention=False
- chunk_sample: 
- top2=['Rhabdomyolysis', 'Sympathomimetic toxicity'] gold=False

## APHHM
- tree_n=38 tree_recall=False
- gold_leaf=None
- final_n=5 final_recall=False ranking=['Sympathomimetic Toxicity', 'Amphetamine-Induced Hyperthermia', 'Neuroleptic Malignant Syndrome', 'Sympathomimetic Toxicity', 'Heat Stroke']
- human_at1=False fail_mode=tree_miss

