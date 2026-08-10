# DA / d2_heldout100 / case 379

- **gold**: Neurotropic melanoma with orbital spread
- **layer**: `aphhm_lose` · **layer_aphhm**: `aphhm_lose`
- **correct**: e7=1 v0=1 B06=1 B07=1 B01= APHHM=0
- **e7_locus**: `s2_miss` · **e7_fail_code**: `s2_miss`
- **mapper_rescue**: 1
- **alignment**: e7_s3_gold=0 e7_champ_cluster=near B06_sup_gold=0 B07_diag_gold=0 same_cluster_flip=0 true_entrance=0
- **APHHM**: locus=`final_hit_judge_miss` code=`aphhm_judge_miss` prune_e7_ok=0

## Vignette
A White man in his 60s presented with a 2-month history of diplopia and pain. Medical history was significant for recurring forehead lesion, first excised 6 years prior to presentation. Initial histopathologic findings showed a Breslow thickness of 6 mm, 14 mitotic figures/mm2, no ulceration, and extensive perineural and intraneural invasion. The lesion recurred twice: two years prior to presentation (excised with negative margins) and eight months prior to presentation (excised with clear margins, followed by 48-Gy brachytherapy to the glabella).

Visual acuity was 20/20 bilaterally without afferent pupillary defect. Examination revealed left proptosis and resistance to globe retropulsion with edema, erythema, and ptosis of the left upper eyelid. Adduction was limited on the left, with associated strabismus and forehead anesthesia in the V1 division of the trigeminal nerve.

- Imaging Studies:    1. MRI finding: Left superior orbit mass extending along the supraorbital nerve to the cavernous sinus, with indistinct borders and fat stranding       Image Title: T1-Weighted Coronal Magnetic Resonance Image of Orbit With Gadolinium Contrast       Image Description: Intense enhancement …

## Options
- A: Perineural spread of metastatic melanoma to the orbit
- B: Malignant melanoma with perineural and orbital metastasis
- C: Neurotropic melanoma with orbital spread **←gold**
- D: Metastatic melanoma to the orbit

## Backbone e7

- S2 n=50 gold_rank=None
  - clusters: gold=0 near=7 other=43
- S3 shortlist (5):
  - [near] Malignant melanoma
  - [other] Malignant peripheral nerve sheath tumor
  - [near] Desmoplastic melanoma
  - [other] Squamous cell carcinoma
  - [other] Adenoid cystic carcinoma
    - why_kept(Malignant melanoma): Recurring forehead lesion with histopathologic findings of Breslow thickness of 6 mm and 14 mitotic figures/mm2, and extensive perineural and intraneural invasion
    - why_kept(Malignant peripheral nerve sheath tumor): Extensive perineural and intraneural invasion, and MRI finding of left superior orbit mass with indistinct borders and fat stranding
    - why_kept(Desmoplastic melanoma): Recurring forehead lesion and histopathologic findings of malignant cells with mitotic activity, effacing residual nerve axons, disrupted neuronal cells, and peritumoral and intratumoral lymphocytes
    - why_kept(Squamous cell carcinoma): Lesion recurred twice, and histopathologic findings showed malignant cells with mitotic activity
    - why_kept(Adenoid cystic carcinoma): Lesion recurred twice, and MRI finding of left superior orbit mass with indistinct borders and fat stranding
- S4 champion: **Malignant melanoma** cluster=near jaccard=0.17
- S4 rationale: The patient's history of a recurring forehead lesion with initial histopathologic findings showing a Breslow thickness of 6 mm, 14 mitotic figures/mm2, and extensive perineural and intraneural invasion, along with the MRI and pathological examination findings, strongly support the diagnosis of malignant melanoma.
- S4 rejected:
  - [other] Malignant peripheral nerve sheath tumor: While perineural invasion is present, the primary lesion characteristics and histopathology are more consistent with melanoma
  - [near] Desmoplastic melanoma: Although desmoplastic melanoma can have perineural invasion, the provided histopathologic details do not specifically suggest this subtype over conventional melanoma
  - [other] Squamous cell carcinoma: The clinical presentation and histopathologic findings do not align with typical squamous cell carcinoma characteristics
  - [other] Adenoid cystic carcinoma: This diagnosis does not fit with the melanoma histopathology and clinical history provided

## B06 (code=`b06_mapper_rescue` locus=`supervisor_miss_but_scored_ok`)
- supervisor: ['Malignant Melanoma with Perineural Invasion', 'Perineural Invasion by Malignant Tumor']
  clusters: {'gold': 0, 'near': 1, 'other': 1, 'empty': 0}
- discussion labels (n=15): ['Malignant Melanoma', 'Orbital Metastasis', 'Perineural Invasion by Malignant Tumor', 'Cavernous Sinus Syndrome', 'Trigeminal Nerve Sheath Tumor', 'Malignant Melanoma with Perineural Invasion', 'Perineural Invasion by Malignant Tumor', 'Cavernous Sinus Syndrome']
- votes=3 turns=3

## B07 (code=`b07_mapper_rescue` locus=`diagnose_miss_but_scored_ok`)
- draft: ['Malignant Melanoma with Perineural Invasion', 'Orbital Metastasis or Direct Invasion from Malignant Melanoma']
- diagnose: ['Malignant Melanoma with Perineural Invasion', 'Orbital Metastasis or Direct Invasion from Malignant Melanoma']
- queries: ['A White man in his 60s presented with a 2-month history of diplopia and pain. Medical history was significant for recurring forehead lesion, first excised 6 years prior to presentation. Initial histop', 'differential diagnosis A White man in his 60s presented with a 2-month history of diplopia and pain. Medical history was significant for recurring forehead lesion, first excised 6 years prior to presentation. Initial histop', 'clinical manifestations diagnosis y 48-Gy brachytherapy to the glabella). Visual acuity was 20/20 bilaterally without afferent pupillary defect. Examination revealed left proptosis and resistanc']

## B01 (code=`na` locus=`na`)
_na_

## APHHM
- tree_n=23 final_n=2
- final: ['Malignant Melanoma', 'Neurotropic Melanoma']
- tree gold_cluster_n=2 final gold=True

