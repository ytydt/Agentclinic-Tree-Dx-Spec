# DA / d2_heldout100 / case 414

- **gold**: Juvenile-onset glaucoma with compound heterozygous LTBP2 mutations
- **layer**: `e7_win_recall` · **layer_aphhm**: `aphhm_lose`
- **correct**: e7=1 v0=0 B06=0 B07=0 B01= APHHM=0
- **e7_locus**: `s2_hit_s3_drop` · **e7_fail_code**: `s2_gold_low_rank`
- **mapper_rescue**: 1
- **alignment**: e7_s3_gold=0 e7_champ_cluster=near B06_sup_gold=0 B07_diag_gold=0 same_cluster_flip=0 true_entrance=0
- **APHHM**: locus=`tree_hit_final_drop` code=`aphhm_prune` prune_e7_ok=0

## Vignette
A 32-year-old African American female. At age 13, she developed elevated intraocular pressure. She had taller stature than her relatives (180.4 cm), long fingers, and hypermobility of the shoulders, digits, and knees. Family history was negative for similar findings. Serial echocardiograms showed no abnormalities.

- Open iridocorneal angle in each eye- No evidence of Haab striae, buphthalmos, or high iris insertion- Subtle lens dislocation superonasally in the right eye (first observed at age 17)- Later developed lens dislocation in the left eye (at age 32)- Hypermobility of shoulders, digits, and knees

- Genetic Testing:  Comprehensive connective tissue genetic testing panel including 92 genes (Invitae) revealed 2 heterozygous variants in the LTBP2 gene (c.709C>T p.Arg237* and c.3776-1G>C splice acceptor)- Imaging:  Figure 1A and B: Fundus photographs showing substantial optic nerve cupping and loss of neural rim tissue at age 17 years  Figure 1C and D: Slitlamp photographs demonstrating progressive superonasal dislocation of the native lens over more than a decade

What is the most likely diagnosis?

Options:
A. Juvenile-onset glaucoma with compound heterozygous LTBP2 mutations…

## Options
- A: Juvenile-onset glaucoma with compound heterozygous LTBP2 mutations **←gold**
- B: Marfan-like syndrome with early-onset glaucoma (LTBP2-related)
- C: LTBP2-related connective tissue disorder with ectopia lentis and congenital glaucoma
- D: LTBP2‐related ectopia lentis and open‐angle glaucoma

## Backbone e7

- S2 n=50 gold_rank=7
  - clusters: gold=1 near=4 other=45
- S3 shortlist (5):
  - [other] Weill-Marchesani syndrome
  - [other] Homocystinuria
  - [other] Marfan syndrome
  - [near] LTBP2-related ocular syndrome
  - [other] Ehlers-Danlos syndrome
    - why_kept(Weill-Marchesani syndrome): Characterized by ectopia lentis, glaucoma, and short stature, but can also present with tall stature and joint hypermobility
    - why_kept(Homocystinuria): Causes ectopia lentis, glaucoma, and tall stature with joint hypermobility due to homocysteine accumulation
    - why_kept(Marfan syndrome): Features tall stature, ectopia lentis, and joint hypermobility, although aortic root dilatation is commonly seen and not present in this case
    - why_kept(LTBP2-related ocular syndrome): Genetic testing revealed 2 heterozygous variants in the LTBP2 gene, which is associated with glaucoma and lens dislocation
    - why_kept(Ehlers-Danlos syndrome): Characterized by joint hypermobility and can have ocular features such as ectopia lentis, although not as prominent as in other conditions
- S4 champion: **LTBP2-related ocular syndrome** cluster=near jaccard=0.09
- S4 rationale: The patient's genetic testing revealed 2 heterozygous variants in the LTBP2 gene, which is a strong indicator of LTBP2-related ocular syndrome. The presence of elevated intraocular pressure, lens dislocation, and optic nerve cupping also supports this diagnosis.
- S4 rejected:
  - [other] Weill-Marchesani syndrome: The patient's tall stature and absence of short fingers do not align with Weill-Marchesani syndrome
  - [other] Homocystinuria: There is no mention of intellectual disability, thromboembolism, or other systemic features typical of homocystinuria
  - [other] Marfan syndrome: The patient's normal serial echocardiograms and lack of other systemic features such as aortic root dilatation do not support Marfan syndrome
  - [other] Ehlers-Danlos syndrome: While the patient has hypermobility, the primary features of elevated intraocular pressure and lens dislocation are more specific to LTBP2-related ocular syndrome

## B06 (code=`b06_agents_miss` locus=`agents_miss`)
- supervisor: ['Weill-Marchesani syndrome', 'Homocystinuria']
  clusters: {'gold': 0, 'near': 0, 'other': 2, 'empty': 0}
- discussion labels (n=15): ['Homocystinuria', 'Marfan syndrome', 'Ehlers-Danlos syndrome', 'Weill-Marchesani syndrome', 'Pseudoexfoliation syndrome', 'Weill-Marchesani syndrome', 'Homocystinuria', 'Ehlers-Danlos syndrome']
- votes=3 turns=3

## B07 (code=`b07_draft_miss` locus=`draft_miss`)
- draft: ['Weill-Marchesani syndrome', 'Homocystinuria']
- diagnose: ['Weill-Marchesani syndrome', 'Homocystinuria']
- queries: ['LTBP2 gene variants and eye disorders', 'connective tissue disorders with lens dislocation', 'homocystinuria vs other causes of lens dislocation']

## B01 (code=`na` locus=`na`)
_na_

## APHHM
- tree_n=26 final_n=1
- final: ['Weill-Marchesani syndrome']
- tree gold_cluster_n=2 final gold=False

