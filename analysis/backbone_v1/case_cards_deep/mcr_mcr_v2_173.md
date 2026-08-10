# MCR / mcr_v2 / case 173

- **gold**: Chronic subdural hematoma
- **layer**: `e7_win_rank`
- **correct**: e7=1 v0=1 B06=0 B07=0 B01=0 APHHM=
- **loci**: e7=`ok` B06=`supervisor_hit_judge_miss` B07=`diagnose_hit_judge_miss` B01=`rag_hit_gen_miss` APHHM=`na`
- **primary_locus**: e7=ok; B06=supervisor_hit_judge_miss; B07=diagnose_hit_judge_miss
- **covariates**: vig_words=196; gold_words=3; eponym=False; subtype=False; e7_s2_rank=1; mapper_rescue=False
- **causal**: layer=e7_win_rank; primary loci above.

## Vignette (trunc)
A 28-year-old G2P1 woman presented 31 days after an elective cesarean delivery under spinal anesthesia with worsening headache and easy fatigability for 3 days. The headache was continuous, global, and had become severe over 24 hours, associated with nausea and malaise. Eight days postoperatively she had developed a mild global headache managed with rest and paracetamol. By day 31 the headache was severe, nonpositional, and unrelieved by rest or analgesics. Vital signs were normal. She was fully...

## Backbone e7
- S1 key_facts: 31 days postpartum after elective cesarean delivery; Initial mild global headache 8 days postoperatively; Worsening headache over 3 days; Headache became severe over 24 hours; Normal vital signs; Fully conscious and oriented; Negative meningeal signs; Intact motor function
- S2 mode=complement k=3 pool_n=48 gold_in_s2=True
  - call1: ['Subdural hematoma', 'Epidural hematoma', 'Subarachnoid hemorrhage', 'Cerebral venous sinus thrombosis', 'Posterior rev
  - call2: ['Cerebral amyloid angiopathy', 'Dural arteriovenous fistula', 'Intracranial dural sinus thrombosis', 'Cavernous sinus t
  - call3: ['Cerebral venous thrombosis due to protein S deficiency', 'Dural sinus thrombosis with hemorrhagic transformation', 'In
- S3 shortlist n=5 gold=True: Subdural hematoma, Spontaneous intracranial hypotension, Posterior reversible encephalopathy syndrome, Cerebral venous sinus thrombosis, Chronic subdural hematoma
- S4 champion: **Chronic subdural hematoma** gold=True
- S4 raw (trunc): {"champion": "Chronic subdural hematoma", "rationale": "The patient's worsening headache over 3 days, severe nonpositional headache, and the noncontrast CT showing a layered hypodense crescent-shaped extra-axial collection are consistent with a chronic subdural hematoma, which ca

## Backbone v0 (compact)
- S1 key_facts: 31 days postpartum after elective cesarean delivery; Initial mild global headache 8 days postoperatively; Worsening headache over 3 days; Headache became severe over 24 hours; Normal vital signs; Fully conscious and oriented; Negative meningeal signs; Intact motor function
- S2 mode=single k=1 pool_n=17 gold_in_s2=True
  - call1: ['Subdural hematoma', 'Epidural hematoma', 'Subarachnoid hemorrhage', 'Cerebral venous sinus thrombosis', 'Posterior rev
- S3 shortlist n=5 gold=True: Subdural hematoma, Spontaneous intracranial hypotension, Chronic subdural hematoma, Reversible cerebral vasoconstriction syndrome, Cerebral venous sinus thrombosis
- S4 champion: **Chronic subdural hematoma** gold=True
- S4 raw (trunc): {"champion": "Chronic subdural hematoma", "rationale": "The patient's worsening headache over 3 days, which became severe over 24 hours, and the presence of a layered hypodense crescent-shaped extra-axial collection on noncontrast CT of the head, are consistent with a chronic sub

## Baseline B06
- discussion_turns=3
  - turn0 gold_mention=True diag=
    The patient's worsening headache and the findings on the noncontrast CT of the head, including a layered hypodense crescent-shaped extra-axial collection, are m
  - turn1 gold_mention=True diag=
    The patient's presentation of worsening headache and the characteristic findings on the noncontrast CT of the head support the primary diagnosis of subdural hem
  - turn2 gold_mention=True diag=
    The patient's worsening headache and characteristic CT findings, along with the history of recent cesarean delivery under spinal anesthesia, support subdural he
- supervisor votes=3 top2=['Subdural hematoma', 'Pseudomeningocele'] gold=True

## Baseline B07
- draft=['Subdural Hematoma', 'Post-Dural Puncture Headache (PDPH)'] gold=True
- has_refine=True refine=[] gold=None
- queries(4): ['postpartum headache differential diagnosis', 'spinal anesthesia complications', 'subdural hematoma symptoms', 'post-dural puncture headache treatment']
- diagnose=['Subdural Hematoma', 'Post-Dural Puncture Headache (PDPH)'] gold=True

## Baseline B01
- queries=['postpartum headache with worsening symptoms', 'spinal anesthesia complications with headache', 'extra-axial collection and crescent-shaped hematoma', 'post-dural puncture headache vs epidural hematoma']
- n_chunks=12 rag_gold_mention=False
- chunk_sample: 
- top2=['Epidural Hematoma', 'Post-Dural Puncture Headache'] gold=False

