# MCR / mcr_v2 / case 205

- **gold**: Cysticercosis
- **layer**: `base_win_recall` · **layer_aphhm**: ``
- **correct**: e7=0 v0=0 B06=1 B07=1 B01=0 APHHM=
- **e7_locus**: `s2_miss` · **e7_fail_code**: `s2_miss`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=0 e7_champ_cluster=other B06_sup_gold=1 B07_diag_gold=1 same_cluster_flip=0 true_entrance=1
- **APHHM**: locus=`na` code=`na` prune_e7_ok=0

## Vignette
A 55-year-old man presented with multiple asymptomatic, skin-colored nodules over his neck, trunk, and upper limbs for 1 year. The lesions had slowly increased in size and number. He reported no systemic complaints, including no fever, weight loss, or neurologic symptoms. He ate beef but denied consumption of pork and had never noted passage of tape-like worms in his stool.

On examination, vital signs were normal. General and systemic examinations were unremarkable, with no lymphadenopathy. Cutaneous examination revealed discrete, firm, freely mobile nodules measuring 0.5–2 cm in diameter without overlying erythema, warmth, or tenderness. A single firm, non-tender nodule was palpated on the lateral tongue.

Routine laboratory investigations, including complete blood count and metabolic profile, were within normal limits. Serologic tests for HIV, hepatitis B, and hepatitis C viruses were nonreactive.

What is the most likely diagnosis?

Options:
A. Cysticercosis
B. Lipoma was considered because of firm, mobile subcutaneous nodules
C. Sebaceous cyst was considered due to subcutaneous nodules with normal overlying skin
D. Deep mycoses were considered because fungal infections can pre…

## Backbone e7

- S2 n=52 gold_rank=None
  - clusters: gold=0 near=0 other=52
- S3 shortlist (5):
  - [other] Neurofibromatosis type 1
  - [other] Lipoid proteinosis
  - [other] Multiple lipomas
  - [other] Dermatofibromas
  - [other] Fibromatosis
    - why_kept(Neurofibromatosis type 1): Multiple asymptomatic skin nodules and a nodule on the tongue are consistent with this diagnosis
    - why_kept(Lipoid proteinosis): Asymptomatic skin nodules and normal laboratory investigations are consistent with this rare condition
    - why_kept(Multiple lipomas): Discrete, firm, freely mobile nodules are characteristic of lipomas
    - why_kept(Dermatofibromas): Asymptomatic skin nodules with gradual increase in size and number could be consistent with dermatofibromas
    - why_kept(Fibromatosis): Firm, non-tender nodules could be indicative of fibromatosis, a rare condition
- S4 champion: **Lipoid proteinosis** cluster=other jaccard=0.00
- S4 rationale: The presence of asymptomatic, skin-colored nodules and a firm nodule on the lateral tongue is consistent with lipoid proteinosis, a rare condition characterized by the deposition of hyaline material in the skin and mucous membranes.
- S4 rejected:
  - [other] Neurofibromatosis type 1: Typically associated with cafe-au-lait spots, neurofibromas, and other systemic features not mentioned in the vignette
  - [other] Multiple lipomas: Lipomas are usually softer and more mobile than the firm nodules described
  - [other] Dermatofibromas: Typically present as solitary, firm papules rather than multiple nodules
  - [other] Fibromatosis: Usually associated with more aggressive growth and local invasion, not consistent with the slow growth and asymptomatic nature of the lesions

## B06 (code=`b06_ok` locus=`supervisor_ok`)
- supervisor: ['Cysticercosis', 'Neurofibromatosis']
  clusters: {'gold': 1, 'near': 0, 'other': 1, 'empty': 0}
- discussion labels (n=15): ['Cysticercosis', 'Neurofibromatosis', 'Lipomatosis', 'Fibromatosis', 'Dermatofibroma', 'Cysticercosis', 'Neurofibromatosis', 'Lipomatosis']
- votes=3 turns=3

## B07 (code=`b07_ok` locus=`diagnose_ok`)
- draft: ['Cysticercosis', 'Lipoma']
- diagnose: ['Cysticercosis', 'Lipoma']
- queries: ['skin-colored nodules on neck trunk and upper limbs', 'asymptomatic skin nodules', 'firm freely mobile nodules', 'subcutaneous nodules differential diagnosis']

## B01 (code=`b01_rag_miss` locus=`rag_miss`)
- top2: ['Dermatofibroma', 'Nevus Anemicus']
- queries: ['skin-colored nodules on neck, trunk, and upper limbs', 'asymptomatic skin nodules with slow growth', 'firm, freely mobile cutaneous nodules without systemic symptoms', 'subcutaneous nodules with normal laboratory investigations']
- n_chunks=12

## APHHM
_na_

