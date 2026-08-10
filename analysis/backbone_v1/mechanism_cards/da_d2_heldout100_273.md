# DA / d2_heldout100 / case 273

- **gold**: Very severe chronic atopic hand eczema with moderate to severe atopic dermatitis
- **layer**: `e7_win_rank` · **layer_aphhm**: `aphhm_lose`
- **correct**: e7=1 v0=1 B06=0 B07=0 B01= APHHM=0
- **e7_locus**: `ok` · **e7_fail_code**: `ok`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=1 e7_champ_cluster=gold B06_sup_gold=1 B07_diag_gold=1 same_cluster_flip=1 true_entrance=0
- **APHHM**: locus=`tree_hit_final_drop` code=`aphhm_prune` prune_e7_ok=1

## Vignette
A woman in her 50s with 18 years history of very severe chronic hand eczema and moderate to severe dermatitis. Onset occurred in early childhood. Medical history includes asthma, rhinitis, and positive family history for atopy. She had limited contact with irritants to minimum.

Hand eczema was rated as 'very severe' according to validated photographic guide. Hand Eczema Severity Index (HECSI) score was 244 of 360 at initial presentation.

- Patch Testing Results: Positive reactions to:    - Nickel    - Cobalt      - Sesquiterpene lactone mix    - Colophonium    - Methyl(chloro)isothiazolinone    - Methyldibromo glutaronitrile    - Parthenolide    - Oleamidopropyl dimethylamine

What is the most likely diagnosis?

Options:
A. Chronic Hyperkeratotic Hand Eczema
B. Very severe chronic atopic hand eczema with moderate to severe atopic dermatitis
C. Combined atopic dermatitis and allergic contact dermatitis
D. Atopic Dermatitis


## Options
- A: Chronic Hyperkeratotic Hand Eczema
- B: Very severe chronic atopic hand eczema with moderate to severe atopic dermatitis **←gold**
- C: Combined atopic dermatitis and allergic contact dermatitis
- D: Atopic Dermatitis **←gold**

## Backbone e7

- S2 n=47 gold_rank=1
  - clusters: gold=1 near=15 other=31
- S3 shortlist (5):
  - [gold] Atopic dermatitis
  - [near] Allergic contact dermatitis
  - [near] Dyshidrotic eczema
  - [near] Irritant contact dermatitis
  - [near] Nummular dermatitis
    - why_kept(Atopic dermatitis): 18 years history of chronic hand eczema with onset in early childhood and positive family history for atopy
    - why_kept(Allergic contact dermatitis): Positive reactions to nickel, cobalt, and other allergens on patch testing
    - why_kept(Dyshidrotic eczema): Very severe hand eczema according to validated photographic guide and HECSI score of 244
    - why_kept(Irritant contact dermatitis): Limited contact with irritants, but still a possible contributing factor
    - why_kept(Nummular dermatitis): Chronic hand dermatitis with atopic background and possible coinfection
- S4 champion: **Atopic dermatitis** cluster=gold jaccard=0.22
- S4 rationale: The patient's history of chronic hand eczema since childhood, combined with a medical history of asthma and rhinitis, and a positive family history for atopy, strongly supports a diagnosis of atopic dermatitis. The presence of very severe hand eczema and high HECSI score also aligns with this diagnosis.
- S4 rejected:
  - [near] Allergic contact dermatitis: While the patient has positive patch testing results, the onset of hand eczema in early childhood and the presence of atopy suggest that atopic dermatitis is a more likely primary diagnosis.
  - [near] Dyshidrotic eczema: There is no specific mention of the characteristic vesicular lesions of dyshidrotic eczema, making this diagnosis less likely.
  - [near] Irritant contact dermatitis: The patient's limited contact with irritants makes this diagnosis less likely, and the presence of atopy and asthma points towards atopic dermatitis.
  - [near] Nummular dermatitis: The patient's presentation of very severe hand eczema and the absence of characteristic nummular lesions make this diagnosis less likely.

## B06 (code=`b06_judge_miss` locus=`supervisor_hit_judge_miss`)
- supervisor: ['Allergic Contact Dermatitis', 'Atopic Dermatitis']
  clusters: {'gold': 1, 'near': 1, 'other': 0, 'empty': 0}
- discussion labels (n=15): ['Allergic Contact Dermatitis', 'Atopic Dermatitis', 'Irritant Contact Dermatitis', 'Seborrheic Dermatitis', 'Dyshidrotic Eczema', 'Allergic Contact Dermatitis', 'Atopic Dermatitis', 'Irritant Contact Dermatitis']
- votes=3 turns=3

## B07 (code=`b07_judge_miss` locus=`diagnose_hit_judge_miss`)
- draft: ['Allergic Contact Dermatitis', 'Atopic Dermatitis']
- diagnose: ['Allergic Contact Dermatitis', 'Atopic Dermatitis']
- queries: ['chronic hand eczema causes', 'allergic contact dermatitis diagnosis', 'atopic dermatitis vs contact dermatitis']

## B01 (code=`na` locus=`na`)
_na_

## APHHM
- tree_n=29 final_n=1
- final: ['allergic contact dermatitis']
- tree gold_cluster_n=8 final gold=False

