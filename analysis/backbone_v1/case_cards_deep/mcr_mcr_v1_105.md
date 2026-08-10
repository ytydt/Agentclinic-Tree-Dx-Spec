# MCR / mcr_v1 / case 105

- **gold**: heat stroke
- **layer**: `aphhm_lose`
- **correct**: e7=1 v0=1 B06=1 B07=0 B01=1 APHHM=0
- **loci**: e7=`ok` B06=`supervisor_ok` B07=`diagnose_hit_judge_miss` B01=`gen_ok` APHHM=`final_hit_judge_miss`
- **primary_locus**: APHHM=final_hit_judge_miss
- **covariates**: vig_words=221; gold_words=2; eponym=False; subtype=False; e7_s2_rank=1; mapper_rescue=False
- **causal**: layer=aphhm_lose; primary loci above.

## Vignette (trunc)
An 86-year-old woman with a history of dementia, living in a non–air-conditioned room during a heat wave, was found unconscious and brought to the emergency department. On arrival, her Glasgow Coma Scale score was 6 (E1V1M4), body temperature 42.4 °C, blood pressure 88/40 mm Hg, and pulse rate 120 beats/min. Laboratory studies revealed hepatic dysfunction, renal dysfunction, and disseminated intravascular coagulation. Head MRI and MRA showed no abnormality. She was diagnosed with severe heat str...

## Backbone e7
- S1 key_facts: Age: 86 years; History of dementia; Living in a non–air-conditioned room during a heat wave; Glasgow Coma Scale score: 6; Body temperature: 42.4 °C; Blood pressure: 88/40 mm Hg; Pulse rate: 120 beats/min; Hepatic dysfunction
- S2 mode=complement k=3 pool_n=50 gold_in_s2=True
  - call1: ['Heat stroke', 'Malignant catatonia', 'Neuroleptic malignant syndrome', 'Serotonin syndrome', 'Status epilepticus', 'Ce
  - call2: ['MELAS syndrome', 'Kernicterus', "Reye's syndrome", "Hashimoto's encephalopathy", 'Cerebral fat embolism', 'Amniotic fl
  - call3: ['Cerebellar cortical atrophy', 'Dyskeratosis congenita', 'Ataxia-telangiectasia', 'Cerebrotendinous xanthomatosis', 'Ab
- S3 shortlist n=5 gold=True: Heat stroke, Severe sepsis, Disseminated intravascular coagulation, Cerebellar infarction, Wernicke's encephalopathy
- S4 champion: **Heat stroke** gold=True
- S4 raw (trunc): {"champion": "Heat stroke", "rationale": "The patient's presentation with a high body temperature of 42.4 °C, altered mental status, and systemic complications such as hepatic dysfunction, renal dysfunction, and disseminated intravascular coagulation during a heat wave is most co

## Backbone v0 (compact)
- S1 key_facts: Age: 86 years; History of dementia; Living in a non–air-conditioned room during a heat wave; Glasgow Coma Scale score: 6; Body temperature: 42.4 °C; Blood pressure: 88/40 mm Hg; Pulse rate: 120 beats/min; Hepatic dysfunction
- S2 mode=None k=None pool_n=19 gold_in_s2=True
  - pool gold matches: ['Heat stroke']
  - pool head: Heat stroke, Malignant catatonia, Neuroleptic malignant syndrome, Serotonin syndrome, Status epilepticus, Cerebral malaria, Encephalitis, Meningitis
- S3 shortlist n=5 gold=True: Heat stroke, Disseminated intravascular coagulation, Cerebellar infarction, Severe sepsis, Wernicke's encephalopathy
- S4 champion: **Heat stroke** gold=True
- S4 raw (trunc): {"champion": "Heat stroke", "rationale": "The patient's presentation with a high body temperature of 42.4 °C, altered mental status, and systemic complications such as hepatic dysfunction, renal dysfunction, and disseminated intravascular coagulation during a heat wave is most co

## Baseline B06
- discussion_turns=3
  - turn0 gold_mention=True diag=
    The patient's presentation with high body temperature, altered mental status, and multi-organ dysfunction is consistent with heat stroke, while the development 
  - turn1 gold_mention=True diag=
    The patient's severe heat stroke led to multi-organ dysfunction and subsequent cerebellar infarction, with hypoxic-ischemic encephalopathy likely contributing t
  - turn2 gold_mention=True diag=
    The patient's clinical presentation and imaging findings are consistent with severe heat stroke complicated by cerebellar infarction and hypoxic-ischemic enceph
- supervisor votes=3 top2=['Heat Stroke', 'Hypoxic-Ischemic Encephalopathy'] gold=True

## Baseline B07
- draft=['Cerebellar injury secondary to heat stroke', 'Hypoxic-ischemic encephalopathy'] gold=True
- has_refine=True refine=[] gold=None
- queries(3): ['An 86-year-old woman with a history of dementia, living in a non–air-conditioned room during a heat wave, was found unconscious and brought to the emergency department. On arrival, her Glasgow Coma Scale score was 6 (E1V1M4), body temperature 42.4 °C, blood pressure 88/40 mm Hg, ', 'differential diagnosis An 86-year-old woman with a history of dementia, living in a non–air-conditioned room during a heat wave, was found unconscious and brought to the emergency dep', 'clinical manifestations diagnosis and pulse rate 120 beats/min. Laboratory studies revealed hepatic dysfunction, renal dysfunction, and disseminated intravascular coagulation. Head MRI and MRA s']
- diagnose=['Cerebellar injury secondary to heat stroke', 'Hypoxic-ischemic encephalopathy'] gold=True

## Baseline B01
- queries=['heat stroke complications', 'cerebellar injury after heat stroke', 'delayed cerebral injury in heat stroke', 'neuroimaging findings in heat-related illnesses']
- n_chunks=12 rag_gold_mention=False
- chunk_sample: 
- top2=['Severe heat stroke', 'Cerebellar injury due to heat stroke'] gold=True

## APHHM
- tree_n=38 tree_recall=True
- gold_leaf=B1.1:Severe Heat Stroke parent=B1
- final_n=4 final_recall=True ranking=['Severe Heat Stroke', 'Disseminated Intravascular Coagulation', 'Encephalitis', 'Cerebellar Infarction']
- human_at1=True fail_mode=final_ok

