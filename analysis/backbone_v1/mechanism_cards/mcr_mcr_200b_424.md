# MCR / mcr_200b / case 424

- **gold**: Nonbacterial thrombotic endocarditis
- **layer**: `all_miss_but_recalled` · **layer_aphhm**: ``
- **correct**: e7=0 v0=0 B06=0 B07=0 B01=1 APHHM=
- **e7_locus**: `s2_miss` · **e7_fail_code**: `s2_miss`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=0 e7_champ_cluster=other B06_sup_gold=0 B07_diag_gold=1 same_cluster_flip=0 true_entrance=1
- **APHHM**: locus=`na` code=`na` prune_e7_ok=0

## Vignette
A 44-year-old woman presented to the emergency department with 2 days of sharp, stabbing right-sided chest pain (8/10) worsened by exertion and relieved by leaning forward, accompanied by shortness of breath on minimal activity. She also reported chronic right lower-leg swelling and six months of symmetric wrist stiffness that improved during the day. Her history included heavy menstrual bleeding, a miscarriage at age 14, chronic warfarin-refractory deep vein thromboses, and placement of a nonretrievable inferior vena cava filter. She denied fevers, chills, or intravenous drug use.

On examination she was obese and mildly tachypneic, sitting forward. Vital signs: temperature 98.6°F, blood pressure 116/91 mm Hg, heart rate 88/min, respiratory rate 20/min, oxygen saturation 98% on room air. She had a malar rash, jugular venous distension, tender anterior chest wall, bibasilar Velcro crackles, and a grade 2/6 pansystolic murmur at the left sternal border that increased with inspiration.

Laboratory studies showed hemoglobin 10.2 g/dL, platelets 71 × 10^3/mm^3, ESR 55 mm/h, CRP 90.9 mg/L, D-dimer 3.7 µg/mL, and prolonged PTT of 49 s with normal PT/INR/fibrinogen. Blood cultures were ne…

## Backbone e7

- S2 n=50 gold_rank=None
  - clusters: gold=0 near=2 other=48
- S3 shortlist (5):
  - [other] Systemic Lupus Erythematosus
  - [other] Antiphospholipid Syndrome
  - [other] Acute Pericarditis
  - [near] Infective Endocarditis
  - [other] Rheumatoid Arthritis
    - why_kept(Systemic Lupus Erythematosus): Malar rash, symmetric wrist stiffness, and elevated ESR and CRP
    - why_kept(Antiphospholipid Syndrome): History of recurrent deep vein thromboses and positive laboratory findings
    - why_kept(Acute Pericarditis): Sharp, stabbing chest pain relieved by leaning forward and pericardial effusion on echocardiography
    - why_kept(Infective Endocarditis): Tricuspid valve vegetation on echocardiography and elevated inflammatory markers
    - why_kept(Rheumatoid Arthritis): Symmetric wrist stiffness and elevated ESR and CRP
- S4 champion: **Systemic Lupus Erythematosus** cluster=other jaccard=0.00
- S4 rationale: The patient's presentation of a malar rash, symmetric wrist stiffness, and elevated inflammatory markers (ESR 55 mm/h, CRP 90.9 mg/L) are consistent with Systemic Lupus Erythematosus (SLE). Additionally, the patient's history of heavy menstrual bleeding, miscarriage, and chronic warfarin-refractory deep vein thromboses suggests a possible underlying autoimmune disorder, which is further supported by the presence of antiphospholipid antibodies (suggested by the history of recurrent thromboses and miscarriage). The patient's cardiac findings, including pericardial effusion and tricuspid regurgitation, can also be seen in SLE.
- S4 rejected:
  - [other] Antiphospholipid Syndrome: While the patient has a history of recurrent thromboses and miscarriage, which are consistent with Antiphospholipid Syndrome, the presence of a malar rash, symmetric wrist stiffness, and elevated inflammatory markers suggest a more systemic autoimmune disorder, such as SLE.
  - [other] Acute Pericarditis: The patient's presentation of chest pain relieved by leaning forward is consistent with pericarditis, but the presence of other systemic symptoms and findings, such as a malar rash and symmetric wrist stiffness, suggest a more complex autoimmune disorder.
  - [near] Infective Endocarditis: The patient's blood cultures were negative, and while the transthoracic and transesophageal echocardiography showed vegetations on the tricuspid valve, the overall clinical presentation and laboratory findings are more consistent with an autoimmune disorder than an infectious process.
  - [other] Rheumatoid Arthritis: The patient's symmetric wrist stiffness that improves during the day is more consistent with SLE or another autoimmune disorder, rather than Rheumatoid Arthritis, which typically worsens with activity.

## B06 (code=`b06_supervisor_drop` locus=`agents_hit_supervisor_drop`)
- supervisor: ['Systemic Lupus Erythematosus (SLE)', 'Antiphospholipid Syndrome (APS)']
  clusters: {'gold': 0, 'near': 0, 'other': 2, 'empty': 0}
- discussion labels (n=15): ['Systemic Lupus Erythematosus (SLE)', 'Antiphospholipid Syndrome (APS)', 'Nonbacterial Thrombotic Endocarditis (NBTE)', 'Libman-Sacks Endocarditis', 'Rheumatic Heart Disease', 'Systemic Lupus Erythematosus (SLE)', 'Antiphospholipid Syndrome (APS)', 'Libman-Sacks Endocarditis']
- votes=3 turns=3

## B07 (code=`b07_judge_miss` locus=`diagnose_hit_judge_miss`)
- draft: ['Nonbacterial thrombotic endocarditis (NBTE)', 'Antiphospholipid syndrome (APS)']
- diagnose: ['Nonbacterial thrombotic endocarditis (NBTE)', 'Antiphospholipid syndrome (APS)']
- queries: ['tricuspid valve vegetation causes', 'nonbacterial thrombotic endocarditis diagnosis', 'systemic lupus erythematosus and endocarditis', 'antiphospholipid syndrome and valve vegetations']

## B01 (code=`b01_ok` locus=`gen_ok`)
- top2: ['Nonbacterial thrombotic endocarditis', 'Systemic lupus erythematosus']
- queries: ['tricuspid valve endocarditis symptoms and diagnosis', 'nonbacterial thrombotic endocarditis vs infective endocarditis', 'systemic lupus erythematosus and antiphospholipid syndrome clinical presentation', 'marantic endocarditis and its association with hypercoagulable states']
- n_chunks=12

## APHHM
_na_

