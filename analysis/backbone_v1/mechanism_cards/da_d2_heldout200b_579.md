# DA / d2_heldout200b / case 579

- **gold**: Gas-containing brain abscess
- **layer**: `base_win_rank` · **layer_aphhm**: ``
- **correct**: e7=0 v0=1 B06=1 B07=1 B01= APHHM=
- **e7_locus**: `s3_hit_s4_miss` · **e7_fail_code**: `near_synonym_prefer`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=1 e7_champ_cluster=near B06_sup_gold=1 B07_diag_gold=1 same_cluster_flip=1 true_entrance=0
- **APHHM**: locus=`na` code=`na` prune_e7_ok=0

## Vignette
A 45-year-old Filipino woman presented with a 2-day history of right-sided headache and emesis of clear fluid. She reported dizziness and generalized weakness but did not report chills, rigor, neck pain, unilateral limb weakness, or sensory loss. No pulmonary, gastrointestinal, or urinary symptoms were present. Medical history included right tympanomastoidectomy for cholesteatoma 2 months prior.

Patient was acutely ill with a Glasgow Coma Scale score of 15. She was afebrile and normotensive, with normal strength in all four extremities. Cranial nerves were intact. Right mastoid region showed a small gaping mastoidectomy wound with a small amount of greenish discharge. Otoscopy revealed greenish discharge in the right external auditory canal. Tympanic membrane was intact. Funduscopy showed no papilledema.

- Laboratory Tests:    * Leukocyte count: 7.1 × 10⁹/L    * C-reactive protein level: 500 mg/L (normal: <1.5 mg/L)- Imaging Studies:    * Computed Tomography with contrast    Image Title: Contrast computed tomography of brain    Image Description: Right temporal lobe ring-enhancing lesion measuring 5.7 cm × 4.8 cm × 5.2 cm with a gas-fluid level and gas bubbles. Significant leftwa…

## Options
- A: Gas-containing brain abscess **←gold**
- B: Right temporal lobe brain abscess
- C: Postoperative intracranial infection (polymicrobial)
- D: Bacterial brain abscess (Proteus mirabilis and Enterococcus gallinarum)

## Backbone e7

- S2 n=52 gold_rank=1
  - clusters: gold=1 near=28 other=23
- S3 shortlist (5):
  - [gold] Brain abscess
  - [near] Otogenic brain abscess
  - [near] Post-surgical brain abscess
  - [near] Pyogenic brain abscess
  - [near] Cholesteatoma-associated brain abscess
    - why_kept(Brain abscess): Ring-enhancing lesion with gas-fluid level and gas bubbles on CT, consistent with abscess formation
    - why_kept(Otogenic brain abscess): Recent right tympanomastoidectomy for cholesteatoma and presence of greenish discharge in the right external auditory canal
    - why_kept(Post-surgical brain abscess): Recent surgical procedure and presence of abscess-like symptoms
    - why_kept(Pyogenic brain abscess): Presence of Proteus mirabilis and Enterococcus gallinarum in cultures, indicating a bacterial infection
    - why_kept(Cholesteatoma-associated brain abscess): History of cholesteatoma and recent tympanomastoidectomy, increasing the risk of abscess formation
- S4 champion: **Otogenic brain abscess** cluster=near jaccard=0.40
- S4 rationale: The patient's recent history of right tympanomastoidectomy for cholesteatoma and the presence of a ring-enhancing lesion in the right temporal lobe with a gas-fluid level and gas bubbles, along with the culture of Proteus mirabilis and Enterococcus gallinarum, suggest an otogenic origin for the brain abscess.
- S4 rejected:
  - [gold] Brain abscess: Too general, as it does not specify the origin of the abscess
  - [near] Post-surgical brain abscess: Although the patient had recent surgery, the otogenic origin is more specific and relevant to the case
  - [near] Pyogenic brain abscess: This term is synonymous with brain abscess and does not provide additional specificity regarding the origin
  - [near] Cholesteatoma-associated brain abscess: While the patient has a history of cholesteatoma, the term 'otogenic brain abscess' more accurately describes the relationship between the ear surgery and the brain abscess

## B06 (code=`b06_ok` locus=`supervisor_ok`)
- supervisor: ['Brain Abscess', 'Subdural Empyema']
  clusters: {'gold': 1, 'near': 0, 'other': 1, 'empty': 0}
- discussion labels (n=15): ['Brain Abscess', 'Meningitis', 'Cerebral Vasculitis', 'Subdural Empyema', 'Osteomyelitis', 'Brain Abscess', 'Subdural Empyema', 'Meningitis']
- votes=3 turns=3

## B07 (code=`b07_ok` locus=`diagnose_ok`)
- draft: ['Brain Abscess', 'Cerebral Infection or Abscess related to recent surgery']
- diagnose: ['Brain Abscess', 'Cerebral Infection or Abscess related to recent surgery']
- queries: ['A 45-year-old Filipino woman presented with a 2-day history of right-sided headache and emesis of clear fluid. She reported dizziness and generalized weakness but did not report chills, rigor, neck pa', 'differential diagnosis A 45-year-old Filipino woman presented with a 2-day history of right-sided headache and emesis of clear fluid. She reported dizziness and generalized weakness but did not report chills, rigor, neck pa', 'clinical manifestations diagnosis he was afebrile and normotensive, with normal strength in all four extremities. Cranial nerves were intact. Right mastoid region showed a small gaping mastoidec']

## B01 (code=`na` locus=`na`)
_na_

## APHHM
_na_

