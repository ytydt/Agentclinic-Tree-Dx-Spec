# DA / d2_heldout100 / case 313

- **gold**: Community-acquired methicillin-resistant Staphylococcus aureus (CA-MRSA) sepsis with septic vasculopathy
- **layer**: `aphhm_lose` · **layer_aphhm**: `aphhm_lose`
- **correct**: e7=1 v0=1 B06=1 B07=1 B01= APHHM=0
- **e7_locus**: `s2_miss` · **e7_fail_code**: `s2_miss`
- **mapper_rescue**: 1
- **alignment**: e7_s3_gold=0 e7_champ_cluster=other B06_sup_gold=0 B07_diag_gold=0 same_cluster_flip=0 true_entrance=0
- **APHHM**: locus=`tree_hit_final_drop` code=`aphhm_prune` prune_e7_ok=0

## Vignette
A healthy male toddler presented to the emergency department with abdominal pain and distention, fever, and vomiting of 1 day's duration. He was found to have 'bruises' on both flanks. Over the next 2 days, he developed diffuse papules on the trunk and extremities; his condition rapidly deteriorated requiring intubation, vasopressors, and empirical broad-spectrum antibiotics.

Purpuric retiform patches were found on each flank (1 of them studded with 2 pustules) with erythematous to violaceous papules diffusely scattered on the extremities and trunk.

- Laboratory tests:  - Hyponatremia and neutropenia present  - AST: 45 U/L  - ALT: 142 U/L   - C-reactive protein: >270 mg/L  - Erythrocyte sedimentation rate: 43 mm/h  - Ferritin: 603 ng/mL  - Urinalysis showed proteinuria and hematuria- Imaging studies:  - CT chest/abdomen: Cavitary lesions in lungs representing necrotizing pneumonia. Areas of nonenhancement within both kidneys suspected to represent renal abscesses  - MRI brain: Multifocal lesions, likely septic emboli  - Transthoracic echocardiogram: Negative  - Bone scans: Negative- Pathological tests:  - Punch biopsy findings:    - Frozen section: Small organisms within vasculat…

## Options
- A: Disseminated methicillin‐resistant Staphylococcus aureus (MRSA) infection
- B: Disseminated Staphylococcus aureus infection with septic emboli
- C: Community-acquired methicillin-resistant Staphylococcus aureus (CA-MRSA) sepsis with septic vasculopathy **←gold**
- D: Bacterial sepsis with disseminated intravascular coagulation

## Backbone e7

- S2 n=53 gold_rank=None
  - clusters: gold=0 near=5 other=48
- S3 shortlist (5):
  - [other] Purpura fulminans
  - [near] Neisseria meningitidis sepsis
  - [other] Streptococcal toxic shock syndrome
  - [other] Meningococcemia
  - [other] Staphylococcal toxic shock syndrome
    - why_kept(Purpura fulminans): Patient presented with purpuric retiform patches and rapid deterioration, consistent with this condition
    - why_kept(Neisseria meningitidis sepsis): Patient had symptoms of sepsis, including fever, vomiting, and abdominal pain, and laboratory tests showed Gram-positive cocci in vessels
    - why_kept(Streptococcal toxic shock syndrome): Patient had symptoms of toxic shock syndrome, including fever, vomiting, and abdominal pain, and laboratory tests showed elevated C-reactive protein and erythrocyte sedimentation rate
    - why_kept(Meningococcemia): Patient had symptoms of sepsis, including fever, vomiting, and abdominal pain, and laboratory tests showed Gram-positive cocci in vessels
    - why_kept(Staphylococcal toxic shock syndrome): Patient had symptoms of toxic shock syndrome, including fever, vomiting, and abdominal pain, and laboratory tests showed elevated C-reactive protein and erythrocyte sedimentation rate
- S4 champion: **Purpura fulminans** cluster=other jaccard=0.00
- S4 rationale: The presence of purpuric retiform patches, rapid deterioration, and laboratory findings such as hyponatremia, neutropenia, and elevated liver enzymes are consistent with Purpura fulminans, a condition characterized by thrombosis and hemorrhagic necrosis of the skin.
- S4 rejected:
  - [near] Neisseria meningitidis sepsis: Although Neisseria meningitidis can cause purpura, the Gram stain showing Gram-positive cocci does not support this diagnosis
  - [other] Streptococcal toxic shock syndrome: While Streptococcal toxic shock syndrome can present with similar symptoms, the biopsy findings and Gram stain results are more indicative of Purpura fulminans
  - [other] Meningococcemia: Meningococcemia typically presents with Neisseria meningitidis, which is a Gram-negative diplococcus, contradicting the Gram-positive cocci found in the tissue Gram stain
  - [other] Staphylococcal toxic shock syndrome: The clinical presentation and laboratory findings do not specifically point towards Staphylococcal toxic shock syndrome, and the presence of Gram-positive cocci in vessels could be consistent with Purpura fulminans

## B06 (code=`b06_mapper_rescue` locus=`supervisor_miss_but_scored_ok`)
- supervisor: ['Purpura Fulminans', 'Staphylococcal scalded skin syndrome']
  clusters: {'gold': 0, 'near': 0, 'other': 2, 'empty': 0}
- discussion labels (n=15): ['Purpura Fulminans', 'Neisseria meningitidis infection', 'Staphylococcal scalded skin syndrome', 'Pneumococcal sepsis', 'Disseminated gonococcal infection', 'Purpura Fulminans', 'Staphylococcal scalded skin syndrome', 'Neisseria meningitidis infection']
- votes=3 turns=3

## B07 (code=`b07_mapper_rescue` locus=`diagnose_miss_but_scored_ok`)
- draft: ['Purpura Fulminans', 'Staphylococcal Toxic Shock Syndrome']
- diagnose: ['Purpura Fulminans', 'Staphylococcal Toxic Shock Syndrome']
- queries: ['purpuric retiform patches in toddler', 'neutropenia and ferritin elevation in toddler with abdominal pain', 'Gram-positive cocci in vessels with necrotizing pneumonia and renal abscesses']

## B01 (code=`na` locus=`na`)
_na_

## APHHM
- tree_n=25 final_n=5
- final: ['Neisseria meningitidis sepsis', 'Streptococcal Toxic Shock Syndrome', 'Neisseria meningitidis sepsis', 'Neisseria meningitidis sepsis', 'Streptococcus pneumoniae sepsis']
- tree gold_cluster_n=2 final gold=False

