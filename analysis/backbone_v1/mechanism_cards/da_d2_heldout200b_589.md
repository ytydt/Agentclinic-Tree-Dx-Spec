# DA / d2_heldout200b / case 589

- **gold**: Edwardsiella tarda infection with empyema
- **layer**: `all_miss_but_recalled` · **layer_aphhm**: ``
- **correct**: e7=0 v0=0 B06=0 B07=0 B01= APHHM=
- **e7_locus**: `s4_hit_judge_miss` · **e7_fail_code**: `s4_hit_judge_miss`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=1 e7_champ_cluster=gold B06_sup_gold=1 B07_diag_gold=0 same_cluster_flip=0 true_entrance=0
- **APHHM**: locus=`na` code=`na` prune_e7_ok=0

## Vignette
A 78-year-old man with a history of liver cirrhosis due to primary biliary cholangitis and curative treatment of chronic myelogenous leukemia. He was in Child-Pugh grade C (13 points) end-stage liver failure and had pleural fluid in his right lung for 1 year. Raw fish was his favorite meal and was the only food he could eat at that time. He was admitted during regular hospital check-ups due to unstable vital signs.

- Blood pressure: 70/40 mm Hg- Heart rate: 50/min- SpO₂: 92% (room air)- Temperature: 37.8°C- Reduced breath sounds in the right lower lung- Jaundice in eyes

Laboratory Tests:- Leukocyte count: 28.11 × 10⁹/L- C-reactive protein level: 119.90 mg/L- Procalcitonin concentration: 3.90 µg/L- Complete blood count and chemistry details as per Table 1, showing abnormal coagulation findings- Cultures of lung fluid and blood were positiveImaging Studies:- Image Title: Computed tomography scan (Figure 1A)- Image Description: Massive pleural effusion in the right lower lung lobe- Image Title: Follow-up computed tomography scan (Figure 1B)- Image Description: Shows disappearance of the massive empyema after treatment

What is the most likely diagnosis?

Options:
A. Parapneumonic ef…

## Options
- A: Parapneumonic effusion
- B: Spontaneous bacterial empyema
- C: Empyema thoracis
- D: Edwardsiella tarda infection with empyema **←gold**

## Backbone e7

- S2 n=55 gold_rank=3
  - clusters: gold=1 near=15 other=39
- S3 shortlist (5):
  - [other] Spontaneous bacterial peritonitis
  - [gold] Empyema
  - [other] Sepsis
  - [other] Pleural effusion due to liver cirrhosis
  - [other] Infected pleural effusion
    - why_kept(Spontaneous bacterial peritonitis): Patient has end-stage liver disease and ascites, which increases the risk of spontaneous bacterial peritonitis
    - why_kept(Empyema): Patient has pleural effusion and positive cultures of lung fluid and blood, indicating a severe infection
    - why_kept(Sepsis): Patient has unstable vital signs, elevated leukocyte count, and positive cultures, indicating a systemic infection
    - why_kept(Pleural effusion due to liver cirrhosis): Patient has a history of liver cirrhosis and pleural effusion, which is a common complication of liver disease
    - why_kept(Infected pleural effusion): Patient has pleural effusion and positive cultures of lung fluid and blood, indicating an infected pleural effusion
- S4 champion: **Empyema** cluster=gold jaccard=0.20
- S4 rationale: The presence of massive pleural effusion in the right lower lung lobe, positive cultures of lung fluid and blood, and the disappearance of the empyema after treatment support this diagnosis.
- S4 rejected:
  - [other] Spontaneous bacterial peritonitis: Although the patient has liver cirrhosis, the key findings of pleural fluid and lung involvement point more towards an empyema rather than spontaneous bacterial peritonitis, which typically involves the peritoneal cavity.
  - [other] Sepsis: While the patient shows signs of infection (elevated leukocyte count, C-reactive protein, and procalcitonin), sepsis is a broader condition that can result from various infections, and the specific focus on pleural fluid and lung involvement suggests empyema as a more precise diagnosis.
  - [other] Pleural effusion due to liver cirrhosis: This condition is a possibility given the patient's liver cirrhosis, but the presence of positive cultures indicates an infectious component, making empyema a more accurate diagnosis than a simple pleural effusion due to liver cirrhosis.
  - [other] Infected pleural effusion: This diagnosis is very close to empyema, as empyema is essentially an infected pleural effusion. However, 'Empyema' is a more specific term that directly indicates the presence of pus in the pleural space, which is supported by the positive cultures and the clinical presentation.

## B06 (code=`b06_judge_miss` locus=`supervisor_hit_judge_miss`)
- supervisor: ['Empyema', 'Spontaneous Bacterial Peritonitis']
  clusters: {'gold': 1, 'near': 0, 'other': 1, 'empty': 0}
- discussion labels (n=15): ['Spontaneous Bacterial Peritonitis', 'Pleural Effusion', 'Sepsis', 'Hepatopulmonary Syndrome', 'Empyema', 'Empyema', 'Spontaneous Bacterial Peritonitis', 'Sepsis']
- votes=3 turns=3

## B07 (code=`b07_draft_miss` locus=`draft_miss`)
- draft: ['Spontaneous Bacterial Empyema', 'Sepsis']
- diagnose: ['Spontaneous Bacterial Empyema', 'Sepsis']
- queries: ['infections in liver cirrhosis', 'pleural effusion causes', 'sepsis diagnosis', 'primary biliary cholangitis complications']

## B01 (code=`na` locus=`na`)
_na_

## APHHM
_na_

