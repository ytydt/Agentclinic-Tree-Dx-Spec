# DA / d2_heldout100 / case 414

- **gold**: Juvenile-onset glaucoma with compound heterozygous LTBP2 mutations
- **layer**: `e7_win_recall`
- **correct**: e7=1 v0=0 B06=0 B07=0 B01= APHHM=0
- **loci**: e7=`s2_hit_s3_drop` B06=`agents_miss` B07=`draft_miss` B01=`na` APHHM=`tree_hit_final_drop`
- **primary_locus**: e7=s2_hit_s3_drop; B06=agents_miss; B07=draft_miss
- **covariates**: vig_words=199; gold_words=8; eponym=False; subtype=True; e7_s2_rank=7; mapper_rescue=True
- **causal**: DA mapper_rescue: e7 S4 未命中金标但 option@1 仍对——不可记入口/终裁优势。

## Vignette (trunc)
A 32-year-old African American female. At age 13, she developed elevated intraocular pressure. She had taller stature than her relatives (180.4 cm), long fingers, and hypermobility of the shoulders, digits, and knees. Family history was negative for similar findings. Serial echocardiograms showed no abnormalities.  - Open iridocorneal angle in each eye- No evidence of Haab striae, buphthalmos, or high iris insertion- Subtle lens dislocation superonasally in the right eye (first observed at age 1...

## Options
  - A: Juvenile-onset glaucoma with compound heterozygous LTBP2 mutations
  - B: Marfan-like syndrome with early-onset glaucoma (LTBP2-related)
  - C: LTBP2-related connective tissue disorder with ectopia lentis and congenital glaucoma
  - D: LTBP2‐related ectopia lentis and open‐angle glaucoma

## Backbone e7
- S1 key_facts: Age of onset of elevated intraocular pressure: 13 years; Patient's height: 180.4 cm; Presence of long fingers; Hypermobility of shoulders, digits, and knees; Family history of similar findings: negative; Serial echocardiograms: no abnormalities; Open iridocorneal angle in each eye; No evidence of Haab striae, buphthalmos, or high iris insertion
- S2 mode=complement k=3 pool_n=50 gold_in_s2=True
  - call1: ['Homocystinuria', 'Marfan syndrome', 'Ehlers-Danlos syndrome', 'Weill-Marchesani syndrome', 'Stickler syndrome', 'Pseud
  - call2: ['Morgagnian cataract', 'Sutural cataract', 'Ectopia lentis et pupillae', 'Coloboma of the lens', 'Posterior lenticonus'
  - call3: ['Congenital spherophakia with ectopia lentis', 'Microspherophakia with glaucoma', 'Ectopia lentis with systemic feature
- S3 shortlist n=5 gold=False: Weill-Marchesani syndrome, Homocystinuria, Marfan syndrome, LTBP2-related ocular syndrome, Ehlers-Danlos syndrome
- S4 champion: **LTBP2-related ocular syndrome** gold=False
- S4 raw (trunc): {"champion": "LTBP2-related ocular syndrome", "rationale": "The patient's genetic testing revealed 2 heterozygous variants in the LTBP2 gene, which is a strong indicator of LTBP2-related ocular syndrome. The presence of elevated intraocular pressure, lens dislocation, and optic n

## Backbone v0 (compact)
- S1 key_facts: Age of onset of elevated intraocular pressure: 13 years; Patient's height: 180.4 cm; Presence of long fingers; Hypermobility of shoulders, digits, and knees; Family history of similar findings: negative; Serial echocardiograms: no abnormalities; Genetic testing revealed 2 heterozygous variants in the LTBP2 gene; Presence of substantial optic nerve cupping and loss of neural rim tissue
- S2 mode=single k=1 pool_n=20 gold_in_s2=False
  - call1: ['Homocystinuria', 'Marfan syndrome', 'Ehlers-Danlos syndrome', 'Weill-Marchesani syndrome', 'Stickler syndrome', 'Pseud
- S3 shortlist n=5 gold=False: Weill-Marchesani syndrome, Homocystinuria, Ehlers-Danlos syndrome, Marfan syndrome, Ectopia lentis
- S4 champion: **Weill-Marchesani syndrome** gold=False
- S4 raw (trunc): {"champion": "Weill-Marchesani syndrome", "rationale": "The patient's presentation of elevated intraocular pressure, lens dislocation, and systemic features such as tall stature, long fingers, and joint hypermobility are consistent with Weill-Marchesani syndrome, which is further

## Baseline B06
- discussion_turns=3
  - turn0 gold_mention=False diag=
    The patient's presentation of elevated intraocular pressure, lens dislocation, and hypermobility of joints suggests a connective tissue disorder. The genetic te
  - turn1 gold_mention=False diag=
    The patient's unique combination of elevated intraocular pressure, lens dislocation, and joint hypermobility, along with the genetic findings of LTBP2 variants,
  - turn2 gold_mention=False diag=
    The patient's presentation of elevated intraocular pressure, lens dislocation, and hypermobility of joints, combined with genetic variants in the LTBP2 gene, al
- supervisor votes=3 top2=['Weill-Marchesani syndrome', 'Homocystinuria'] gold=False

## Baseline B07
- draft=['Weill-Marchesani syndrome', 'Homocystinuria'] gold=False
- has_refine=True refine=[] gold=None
- queries(3): ['LTBP2 gene variants and eye disorders', 'connective tissue disorders with lens dislocation', 'homocystinuria vs other causes of lens dislocation']
- diagnose=['Weill-Marchesani syndrome', 'Homocystinuria'] gold=False

## APHHM
- tree_n=26 tree_recall=True
- gold_leaf=B1.6:Glaucoma parent=B1
- final_n=1 final_recall=False ranking=['Weill-Marchesani syndrome']
- human_at1=False fail_mode=prune_loss

