# MCR / mcr_v2 / case 173

- **gold**: Chronic subdural hematoma
- **layer**: `e7_win_rank` · **layer_aphhm**: ``
- **correct**: e7=1 v0=1 B06=0 B07=0 B01=0 APHHM=
- **e7_locus**: `ok` · **e7_fail_code**: `ok`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=1 e7_champ_cluster=gold B06_sup_gold=1 B07_diag_gold=1 same_cluster_flip=1 true_entrance=0
- **APHHM**: locus=`na` code=`na` prune_e7_ok=0

## Vignette
A 28-year-old G2P1 woman presented 31 days after an elective cesarean delivery under spinal anesthesia with worsening headache and easy fatigability for 3 days. The headache was continuous, global, and had become severe over 24 hours, associated with nausea and malaise. Eight days postoperatively she had developed a mild global headache managed with rest and paracetamol. By day 31 the headache was severe, nonpositional, and unrelieved by rest or analgesics. Vital signs were normal. She was fully conscious and oriented, all meningeal signs were negative, and motor function was intact. Laboratory studies showed a normal complete blood count, prothrombin time, partial prothrombin time, and international normalized ratio. Noncontrast CT of the head revealed a layered hypodense crescent-shaped extra-axial collection over the left frontoparietal convexity with areas of linear and crescentic hyperdensity, measuring 15 mm in width with a 13-mm midline shift.

What is the most likely diagnosis?

Options:
A. Chronic subdural hematoma
B. PDPH was considered because of recent dural puncture but was excluded since “In PDPH, the pain worsens or develops
C. Meningitis was considered but was exclu…

## Backbone e7

- S2 n=48 gold_rank=1
  - clusters: gold=2 near=2 other=44
- S3 shortlist (5):
  - [gold] Subdural hematoma
  - [other] Spontaneous intracranial hypotension
  - [other] Posterior reversible encephalopathy syndrome
  - [other] Cerebral venous sinus thrombosis
  - [gold] Chronic subdural hematoma
    - why_kept(Subdural hematoma): Noncontrast CT showed extra-axial collection with areas of linear and crescentic hyperdensity, consistent with subdural hematoma
    - why_kept(Spontaneous intracranial hypotension): Postpartum headache with worsening course, potentially related to spinal anesthesia and subsequent CSF leak
    - why_kept(Posterior reversible encephalopathy syndrome): Severe headache, nausea, and malaise, with normal vital signs and no meningeal signs, consistent with posterior reversible encephalopathy syndrome
    - why_kept(Cerebral venous sinus thrombosis): Headache with worsening course, with areas of linear and crescentic hyperdensity on CT, potentially indicating cerebral venous sinus thrombosis
    - why_kept(Chronic subdural hematoma): Initial mild headache 8 days postoperatively, with subsequent worsening, potentially indicating chronic subdural hematoma
- S4 champion: **Chronic subdural hematoma** cluster=gold jaccard=1.00
- S4 rationale: The patient's worsening headache over 3 days, severe nonpositional headache, and the noncontrast CT showing a layered hypodense crescent-shaped extra-axial collection are consistent with a chronic subdural hematoma, which can develop after a traumatic event such as a cesarean delivery under spinal anesthesia.
- S4 rejected:
  - [gold] Subdural hematoma: While possible, the term 'subdural hematoma' is more general and does not specify the chronic nature of the condition, which is suggested by the timeline of symptoms.
  - [other] Spontaneous intracranial hypotension: This condition typically presents with postural headaches that improve with recumbency, which does not match the patient's nonpositional headache.
  - [other] Posterior reversible encephalopathy syndrome: This condition is characterized by hypertension, seizures, and specific MRI findings, which are not present in this case.
  - [other] Cerebral venous sinus thrombosis: This condition would likely present with more severe and sudden symptoms, and the CT findings do not suggest thrombosis.

## B06 (code=`b06_judge_miss` locus=`supervisor_hit_judge_miss`)
- supervisor: ['Subdural hematoma', 'Pseudomeningocele']
  clusters: {'gold': 1, 'near': 0, 'other': 1, 'empty': 0}
- discussion labels (n=15): ['Subdural hematoma', 'Epidural hematoma', 'Subarachnoid hemorrhage', 'Cerebral venous sinus thrombosis', 'Pseudomeningocele', 'Subdural hematoma', 'Pseudomeningocele', 'Epidural hematoma']
- votes=3 turns=3

## B07 (code=`b07_judge_miss` locus=`diagnose_hit_judge_miss`)
- draft: ['Subdural Hematoma', 'Post-Dural Puncture Headache (PDPH)']
- diagnose: ['Subdural Hematoma', 'Post-Dural Puncture Headache (PDPH)']
- queries: ['postpartum headache differential diagnosis', 'spinal anesthesia complications', 'subdural hematoma symptoms', 'post-dural puncture headache treatment']

## B01 (code=`b01_gen_miss` locus=`rag_hit_gen_miss`)
- top2: ['Epidural Hematoma', 'Post-Dural Puncture Headache']
- queries: ['postpartum headache with worsening symptoms', 'spinal anesthesia complications with headache', 'extra-axial collection and crescent-shaped hematoma', 'post-dural puncture headache vs epidural hematoma']
- n_chunks=12

## APHHM
_na_

