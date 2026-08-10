# MCR / mcr_v1 / case 112

- **gold**: Bath salt intoxication
- **layer**: `aphhm_lose` · **layer_aphhm**: `aphhm_lose`
- **correct**: e7=1 v0=0 B06=0 B07=1 B01=0 APHHM=0
- **e7_locus**: `s2_miss` · **e7_fail_code**: `s2_miss`
- **mapper_rescue**: 1
- **alignment**: e7_s3_gold=0 e7_champ_cluster=near B06_sup_gold=0 B07_diag_gold=0 same_cluster_flip=0 true_entrance=0
- **APHHM**: locus=`tree_miss` code=`aphhm_tree_miss` prune_e7_ok=0

## Vignette
A 29-year-old Caucasian man with a history of hepatitis C, posttraumatic stress disorder, polysubstance abuse, and tobacco use was brought to the emergency department after being found agitated and erratically wandering the streets and then unresponsive with multiple skin abrasions. He reported ingestion and insufflation of “bath salts,” a history later confirmed by his family. He denied other medications or supplements and had no known drug allergies.

On examination, temperature was 107°F, blood pressure 91/52 mm Hg, and pulse 93/min. He was confused and intermittently agitated, with pupils 3 mm and equal. Cardiovascular exam showed weak peripheral pulses without jugular venous distention or murmurs; lungs were clear; abdomen was soft; no focal neurologic deficits.

Laboratory studies on admission showed features of severe rhabdomyolysis. Serologic testing confirmed chronic hepatitis C but was otherwise unremarkable. Serum toxicology tests were negative for ethanol, acetaminophen, and salicylates. Urine toxicology detected only lorazepam and cotinine but was negative for over 80 other substances, including cannabinoids, cocaine, ecstasy, ephedrine, lysergide, methamphetamine, met…

## Backbone e7

- S2 n=48 gold_rank=None
  - clusters: gold=0 near=5 other=43
- S3 shortlist (5):
  - [other] Sympathomimetic Toxicity
  - [near] Bath Salts Intoxication
  - [other] Serotonin Syndrome
  - [other] Malignant Hyperthermia
  - [other] Neuroleptic Malignant Syndrome
    - why_kept(Sympathomimetic Toxicity): Patient's symptoms of agitation, hyperthermia, and tachycardia are consistent with sympathomimetic toxicity, and the patient reported ingestion of 'bath salts' which can cause this condition
    - why_kept(Bath Salts Intoxication): Patient's reported ingestion of 'bath salts' and symptoms of agitation, hyperthermia, and confusion are consistent with bath salts intoxication
    - why_kept(Serotonin Syndrome): Patient's symptoms of confusion, agitation, and hyperthermia could be consistent with serotonin syndrome, although the absence of other serotonergic agents makes this less likely
    - why_kept(Malignant Hyperthermia): Patient's severe hyperthermia and rhabdomyolysis could be consistent with malignant hyperthermia, although the absence of a triggering anesthetic agent makes this less likely
    - why_kept(Neuroleptic Malignant Syndrome): Patient's symptoms of hyperthermia, confusion, and agitation could be consistent with neuroleptic malignant syndrome, although the absence of neuroleptic medication makes this less likely
- S4 champion: **Bath Salts Intoxication** cluster=near jaccard=0.50
- S4 rationale: The patient's reported ingestion and insufflation of 'bath salts' and the presence of severe symptoms such as hyperthermia, agitation, and rhabdomyolysis are consistent with bath salts intoxication
- S4 rejected:
  - [other] Sympathomimetic Toxicity: While some symptoms overlap, the specific mention of 'bath salts' ingestion points more directly to Bath Salts Intoxication
  - [other] Serotonin Syndrome: Lack of specific serotonin-related symptoms and no mention of serotonin-affecting medications
  - [other] Malignant Hyperthermia: Typically associated with anesthesia and not directly linked to 'bath salts' ingestion
  - [other] Neuroleptic Malignant Syndrome: No mention of neuroleptic medication use, which is a prerequisite for this condition

## B06 (code=`b06_agents_miss` locus=`agents_miss`)
- supervisor: ['Sympathomimetic toxicity', 'Rhabdomyolysis']
  clusters: {'gold': 0, 'near': 0, 'other': 2, 'empty': 0}
- discussion labels (n=15): ['Rhabdomyolysis', 'Hyperthermia', 'Acute kidney injury', 'Sympathomimetic toxicity', 'Hepatitis C', 'Sympathomimetic toxicity', 'Rhabdomyolysis', 'Acute kidney injury']
- votes=3 turns=3

## B07 (code=`b07_mapper_rescue` locus=`diagnose_miss_but_scored_ok`)
- draft: ['Synthetic cathinone toxicity', 'Rhabdomyolysis due to multiple factors']
- diagnose: ['Synthetic cathinone toxicity', 'Rhabdomyolysis due to multiple factors']
- queries: ['bath salts toxicity symptoms', 'rhabdomyolysis causes', 'severe hyperthermia treatment', 'hyperkalemia management']

## B01 (code=`b01_rag_miss` locus=`rag_miss`)
- top2: ['Rhabdomyolysis', 'Sympathomimetic toxicity']
- queries: ['severe rhabdomyolysis causes', 'bath salts toxicity symptoms', 'hyperthermia treatment in critically ill patients', 'acute kidney injury after rhabdomyolysis']
- n_chunks=12

## APHHM
- tree_n=38 final_n=5
- final: ['Sympathomimetic Toxicity', 'Amphetamine-Induced Hyperthermia', 'Neuroleptic Malignant Syndrome', 'Sympathomimetic Toxicity', 'Heat Stroke']
- tree gold_cluster_n=0 final gold=False

