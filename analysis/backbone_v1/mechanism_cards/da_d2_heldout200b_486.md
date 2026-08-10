# DA / d2_heldout200b / case 486

- **gold**: Histoid leprosy
- **layer**: `base_win_rank` · **layer_aphhm**: ``
- **correct**: e7=0 v0=0 B06=1 B07=0 B01= APHHM=
- **e7_locus**: `s3_hit_s4_miss` · **e7_fail_code**: `near_synonym_prefer`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=1 e7_champ_cluster=near B06_sup_gold=1 B07_diag_gold=0 same_cluster_flip=1 true_entrance=0
- **APHHM**: locus=`na` code=`na` prune_e7_ok=0

## Vignette
A 33-year-old housewife presented with a one-year history of painless discrete cutaneous nodules. The first soybean-sized nodule appeared on her right wrist, gradually followed by nodules on the limbs, trunk, and face. No fevers, joint pain, or hair loss reported. No medical or drug history. Family history negative for skin or autoimmune disease. Five months prior, she had been treated with hydroxychloroquine, thalidomide, and topical steroids without improvement. Patient later reported frequent visits to a neighbor between ages 3-18 years.

Physical findings included:- 17 red nodules measuring 0.5–1 cm in diameter- Some nodules firm, others soft in texture- Light red livedo reticularis on limbs- Mild hypoaesthesia on the extensor side of the knee and ankle- No peripheral nerve thickening- No anhidrosis

Laboratory Tests:- Positive anti-nuclear antibodies- Positive anti-Ro52 antibodies- Positive anti-cardiolipin antibodies- Elevated rheumatoid factor (307 IU/mL; normal <20 IU/mL)- Slightly raised erythrocyte sedimentation rate- Other laboratory results within normal limitsHistopathology:- Epidermal atrophy- Nodular infiltrates of foamy histiocytes in dermis arranged in storiform pa…

## Options
- A: Borderline lepromatous leprosy
- B: Lupus panniculitis
- C: Lepromatous leprosy
- D: Histoid leprosy **←gold**

## Backbone e7

- S2 n=47 gold_rank=11
  - clusters: gold=1 near=2 other=44
- S3 shortlist (5):
  - [near] Lepromatous leprosy
  - [near] Borderline leprosy
  - [other] Lupus vulgaris
  - [other] Erythema nodosum leprosum
  - [gold] Histoid leprosy
    - why_kept(Lepromatous leprosy): Abundant acid-fast bacilli within histiocytes and positive laboratory results
    - why_kept(Borderline leprosy): Presence of acid-fast bacilli and cutaneous nodules
    - why_kept(Lupus vulgaris): Chronic cutaneous nodular syndrome with systemic implications and positive anti-nuclear antibodies
    - why_kept(Erythema nodosum leprosum): Reaction to leprosy and presence of cutaneous nodules
    - why_kept(Histoid leprosy): Presence of acid-fast bacilli and nodular infiltrates of foamy histiocytes
- S4 champion: **Lepromatous leprosy** cluster=near jaccard=0.33
- S4 rationale: The presence of abundant acid-fast bacilli within histiocytes, epidermal atrophy, and nodular infiltrates of foamy histiocytes in dermis, along with the patient's lack of response to treatments for other conditions, supports this diagnosis.
- S4 rejected:
  - [near] Borderline leprosy: The presence of abundant acid-fast bacilli and the specific histopathological features are more characteristic of lepromatous leprosy.
  - [other] Lupus vulgaris: The clinical presentation and histopathology do not match lupus vulgaris, which is a form of cutaneous tuberculosis.
  - [other] Erythema nodosum leprosum: This condition is a type of reaction that can occur in leprosy, but the patient's symptoms and histopathology are more consistent with lepromatous leprosy itself.
  - [gold] Histoid leprosy: While histoid leprosy can present with nodules, the histopathological features and the presence of acid-fast bacilli in this case are more typical of lepromatous leprosy.

## B06 (code=`b06_ok` locus=`supervisor_ok`)
- supervisor: ['Leprosy', 'Lupus vulgaris']
  clusters: {'gold': 1, 'near': 0, 'other': 1, 'empty': 0}
- discussion labels (n=15): ['Leprosy', 'Lupus vulgaris', 'Erythema nodosum', 'Sarcoidosis', 'Granuloma annulare', 'Leprosy', 'Lupus vulgaris', 'Sarcoidosis']
- votes=3 turns=3

## B07 (code=`b07_draft_miss` locus=`draft_miss`)
- draft: ['Lupus vulgaris', 'Other granulomatous disease (e.g., sarcoidosis)']
- diagnose: ['Lupus vulgaris', 'Other granulomatous disease (e.g., sarcoidosis)']
- queries: ['A 33-year-old housewife presented with a one-year history of painless discrete cutaneous nodules. The first soybean-sized nodule appeared on her right wrist, gradually followed by nodules on the limbs', 'differential diagnosis A 33-year-old housewife presented with a one-year history of painless discrete cutaneous nodules. The first soybean-sized nodule appeared on her right wrist, gradually followed by nodules on the limbs', 'clinical manifestations diagnosis en ages 3-18 years. Physical findings included:- 17 red nodules measuring 0.5–1 cm in diameter- Some nodules firm, others soft in texture- Light red livedo reti']

## B01 (code=`na` locus=`na`)
_na_

## APHHM
_na_

