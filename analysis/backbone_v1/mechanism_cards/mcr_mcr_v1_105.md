# MCR / mcr_v1 / case 105

- **gold**: heat stroke
- **layer**: `aphhm_lose` · **layer_aphhm**: `aphhm_lose`
- **correct**: e7=1 v0=1 B06=1 B07=0 B01=1 APHHM=0
- **e7_locus**: `ok` · **e7_fail_code**: `ok`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=1 e7_champ_cluster=gold B06_sup_gold=1 B07_diag_gold=1 same_cluster_flip=0 true_entrance=0
- **APHHM**: locus=`final_hit_judge_miss` code=`aphhm_judge_miss` prune_e7_ok=0

## Vignette
An 86-year-old woman with a history of dementia, living in a non–air-conditioned room during a heat wave, was found unconscious and brought to the emergency department. On arrival, her Glasgow Coma Scale score was 6 (E1V1M4), body temperature 42.4 °C, blood pressure 88/40 mm Hg, and pulse rate 120 beats/min. Laboratory studies revealed hepatic dysfunction, renal dysfunction, and disseminated intravascular coagulation. Head MRI and MRA showed no abnormality. She was diagnosed with severe heat stroke (APACHE II score 42, SOFA score 15), intubated, and treated with extracorporeal cooling, fluid resuscitation, and DIC therapy; fursultiamine and levothyroxine were also given. Despite treatment, she remained unconscious. On day 6, brain MRI showed bilateral cerebellar hemisphere high-signal intensity on diffusion-weighted and FLAIR images with corresponding low ADC signals. On day 9, SPECT with 123I-IMP demonstrated decreased perfusion in the right cerebellar hemisphere. By day 13, MRI abnormalities had begun to improve, and her level of consciousness improved to E4VTM6.

What is the most likely diagnosis?

Options:
A. heat stroke
B. Wernicke’s encephalopathy was considered but excluded …

## Backbone e7

- S2 n=50 gold_rank=1
  - clusters: gold=1 near=0 other=49
- S3 shortlist (5):
  - [gold] Heat stroke
  - [other] Severe sepsis
  - [other] Disseminated intravascular coagulation
  - [other] Cerebellar infarction
  - [other] Wernicke's encephalopathy
    - why_kept(Heat stroke): Patient's presentation with hyperthermia, altered mental status, and multi-organ dysfunction is consistent with heat stroke, especially given the context of living in a non-air-conditioned room during a heat wave
    - why_kept(Severe sepsis): Patient's presentation with multi-organ dysfunction, including hepatic and renal dysfunction, and disseminated intravascular coagulation, could be indicative of severe sepsis
    - why_kept(Disseminated intravascular coagulation): Patient's laboratory results showing disseminated intravascular coagulation, which is a complication that can occur in the setting of severe heat stroke or sepsis
    - why_kept(Cerebellar infarction): Patient's brain MRI showing bilateral cerebellar hemisphere high-signal intensity on diffusion-weighted and FLAIR images, which could be indicative of cerebellar infarction
    - why_kept(Wernicke's encephalopathy): Patient's presentation with altered mental status, and the fact that she has a history of dementia, could be indicative of Wernicke's encephalopathy, especially if she has a history of malnutrition or alcohol abuse
- S4 champion: **Heat stroke** cluster=gold jaccard=1.00
- S4 rationale: The patient's presentation with a high body temperature of 42.4 °C, altered mental status, and systemic complications such as hepatic dysfunction, renal dysfunction, and disseminated intravascular coagulation during a heat wave is most consistent with heat stroke.
- S4 rejected:
  - [other] Severe sepsis: While the patient has systemic inflammation and organ dysfunction, there is no clear source of infection to support a diagnosis of sepsis.
  - [other] Disseminated intravascular coagulation: Although the patient has DIC, it is a complication of the underlying condition rather than the primary diagnosis.
  - [other] Cerebellar infarction: The initial head MRI and MRA were normal, and the subsequent cerebellar abnormalities on MRI and SPECT were likely a consequence of the heat stroke rather than a primary cerebellar infarction.
  - [other] Wernicke's encephalopathy: There is no mention of alcohol abuse or malnutrition, which are common risk factors for Wernicke's encephalopathy, and the patient's presentation is more consistent with heat stroke.

## B06 (code=`b06_ok` locus=`supervisor_ok`)
- supervisor: ['Heat Stroke', 'Hypoxic-Ischemic Encephalopathy']
  clusters: {'gold': 1, 'near': 0, 'other': 1, 'empty': 0}
- discussion labels (n=15): ['Heat Stroke', 'Disseminated Intravascular Coagulation', 'Cerebellar Infarction', 'Severe Dementia', 'Hypoxic-Ischemic Encephalopathy', 'Heat Stroke', 'Hypoxic-Ischemic Encephalopathy', 'Cerebellar Infarction']
- votes=3 turns=3

## B07 (code=`b07_judge_miss` locus=`diagnose_hit_judge_miss`)
- draft: ['Cerebellar injury secondary to heat stroke', 'Hypoxic-ischemic encephalopathy']
- diagnose: ['Cerebellar injury secondary to heat stroke', 'Hypoxic-ischemic encephalopathy']
- queries: ['An 86-year-old woman with a history of dementia, living in a non–air-conditioned room during a heat wave, was found unconscious and brought to the emergency department. On arrival, her Glasgow Coma Scale score was 6 (E1V1M4), body temperature 42.4 °C, blood pressure 88/40 mm Hg, ', 'differential diagnosis An 86-year-old woman with a history of dementia, living in a non–air-conditioned room during a heat wave, was found unconscious and brought to the emergency dep', 'clinical manifestations diagnosis and pulse rate 120 beats/min. Laboratory studies revealed hepatic dysfunction, renal dysfunction, and disseminated intravascular coagulation. Head MRI and MRA s']

## B01 (code=`b01_ok` locus=`gen_ok`)
- top2: ['Severe heat stroke', 'Cerebellar injury due to heat stroke']
- queries: ['heat stroke complications', 'cerebellar injury after heat stroke', 'delayed cerebral injury in heat stroke', 'neuroimaging findings in heat-related illnesses']
- n_chunks=12

## APHHM
- tree_n=38 final_n=4
- final: ['Severe Heat Stroke', 'Disseminated Intravascular Coagulation', 'Encephalitis', 'Cerebellar Infarction']
- tree gold_cluster_n=2 final gold=True

