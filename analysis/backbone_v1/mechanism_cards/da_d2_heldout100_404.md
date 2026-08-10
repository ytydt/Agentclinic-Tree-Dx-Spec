# DA / d2_heldout100 / case 404

- **gold**: Pemetrexed-induced inflammatory and sclerotic edema
- **layer**: `aphhm_lose` · **layer_aphhm**: `aphhm_lose`
- **correct**: e7=1 v0=1 B06=0 B07=1 B01= APHHM=0
- **e7_locus**: `s2_miss` · **e7_fail_code**: `s2_miss`
- **mapper_rescue**: 1
- **alignment**: e7_s3_gold=0 e7_champ_cluster=near B06_sup_gold=0 B07_diag_gold=0 same_cluster_flip=0 true_entrance=0
- **APHHM**: locus=`tree_miss` code=`aphhm_tree_miss` prune_e7_ok=0

## Vignette
A man in his late 70s presented with acute onset of redness, pain, and swelling of both lower limbs. The patient had received 4 cycles of chemotherapy with carboplatin, pemetrexed, and pembrolizumab for progressive disease and was currently in maintenance with pemetrexed-pembrolizumab. The edema appeared 5 days after the patient's 8th cycle of chemotherapy and evolved into sclerotic plaques.

Examination revealed ill-defined, erythematoedematous plaques symmetrically distributed along the shins, with areas of induration. The patient remained afebrile and systemically well.

- Laboratory tests: No elevation of inflammatory markers (normal white blood cell count and C-reactive protein level), with kidney, liver, and heart functions within normal ranges.- Imaging studies: Venous Doppler ultrasonography of legs showed no evidence of deep vein thrombosis.- Pathology:   Image Title: Hematoxylin-eosin–stained specimen from left shin  Image Description: Shows normal-appearing epidermis, thickened dermal collagen with activated fibroblasts, and lymphocytic perivascular infiltration.- Clinical Photography:  Image Title: Clinical image of lower limbs  Image Description: Ill-defined erythemato…

## Options
- A: Localized scleroderma (morphea)
- B: Eosinophilic fasciitis
- C: Pemetrexed-induced inflammatory and sclerotic edema **←gold**
- D: Immune checkpoint inhibitor–induced scleroderma-like dermatitis

## Backbone e7

- S2 n=44 gold_rank=None
  - clusters: gold=0 near=3 other=41
- S3 shortlist (5):
  - [near] Chemotherapy-induced scleroderma-like reaction
  - [other] Erythema nodosum
  - [other] Scleroderma
  - [other] Morphea
  - [other] Lipodermatosclerosis
    - why_kept(Chemotherapy-induced scleroderma-like reaction): Patient developed sclerotic plaques after chemotherapy
    - why_kept(Erythema nodosum): Acute onset of redness, pain, and swelling of lower limbs
    - why_kept(Scleroderma): Patient presented with sclerotic plaques and thickened dermal collagen
    - why_kept(Morphea): Patient had localized sclerotic plaques and lymphocytic perivascular infiltration
    - why_kept(Lipodermatosclerosis): Patient had induration and erythematous plaques on the lower limbs
- S4 champion: **Chemotherapy-induced scleroderma-like reaction** cluster=near jaccard=0.10
- S4 rationale: The patient's symptoms of redness, pain, and swelling of both lower limbs, which evolved into sclerotic plaques, appeared 5 days after the 8th cycle of chemotherapy, and the pathology showed thickened dermal collagen with activated fibroblasts and lymphocytic perivascular infiltration, consistent with a scleroderma-like reaction induced by chemotherapy.
- S4 rejected:
  - [other] Erythema nodosum: Erythema nodosum typically presents with tender, erythematous nodules, usually on the shins, but the patient's symptoms and pathology results do not fully align with this condition.
  - [other] Scleroderma: Scleroderma is a chronic autoimmune disease that typically presents with a more gradual onset of symptoms and is not directly linked to chemotherapy.
  - [other] Morphea: Morphea is a localized form of scleroderma, but the patient's symptoms are more widespread and appeared in conjunction with chemotherapy.
  - [other] Lipodermatosclerosis: Lipodermatosclerosis is a condition associated with chronic venous insufficiency, but the patient's venous Doppler ultrasonography showed no evidence of deep vein thrombosis, and the pathology results do not support this diagnosis.

## B06 (code=`b06_supervisor_drop` locus=`agents_hit_supervisor_drop`)
- supervisor: ['pembrolizumab-induced scleroderma-like reaction', 'chemotherapy-induced scleroderma']
  clusters: {'gold': 0, 'near': 2, 'other': 0, 'empty': 0}
- discussion labels (n=15): ['pembrolizumab-induced scleroderma-like reaction', 'chemotherapy-induced scleroderma', 'pemetrexed-induced cutaneous fibrosis', 'carboplatin-induced dermatitis', 'pembrolizumab-induced immune-related adverse event', 'pembrolizumab-induced scleroderma-like reaction', 'chemotherapy-induced scleroderma', 'pemetrexed-induced cutaneous fibrosis']
- votes=3 turns=3

## B07 (code=`b07_mapper_rescue` locus=`diagnose_miss_but_scored_ok`)
- draft: ['Chemotherapy-induced sclerotic plaques', 'Pembrolizumab-induced cutaneous adverse reaction']
- diagnose: ['Chemotherapy-induced sclerotic plaques', 'Pembrolizumab-induced cutaneous adverse reaction']
- queries: ['pembrolizumab side effects', 'pemetrexed side effects', 'carboplatin side effects', 'chemotherapy-induced sclerotic plaques']

## B01 (code=`na` locus=`na`)
_na_

## APHHM
- tree_n=26 final_n=3
- final: ['Scleroderma', 'Nephrogenic Systemic Fibrosis', 'Morphea']
- tree gold_cluster_n=0 final gold=False

