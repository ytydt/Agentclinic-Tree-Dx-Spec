# DA / d2_heldout200b / case 574

- **gold**: Mixed Langerhans cell histiocytosis (LCH) and Erdheim-Chester disease (ECD) with renovascular hypertension
- **layer**: `base_win_rank` · **layer_aphhm**: ``
- **correct**: e7=0 v0=0 B06=0 B07=1 B01= APHHM=
- **e7_locus**: `s2_hit_s3_drop` · **e7_fail_code**: `s2_gold_low_rank`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=0 e7_champ_cluster=other B06_sup_gold=1 B07_diag_gold=0 same_cluster_flip=0 true_entrance=0
- **APHHM**: locus=`na` code=`na` prune_e7_ok=0

## Vignette
A 63-year-old woman presented with difficult-to-treat hypertension. Medical history included bone and central diabetes insipidus diagnosed via femoral biopsy 12 years ago, and liver involvement three years prior that was treated with cytarabine for one year. The patient had untreated dyslipidemia (LDL cholesterol 3.11 mmol/L). She was not a smoker and did not have diabetes. Her body mass index was 19.22 kg/m². No relevant family history was reported. The patient did not report angina, exertional dyspnea, or claudication.

Blood pressure was 198/106 mmHg without orthostatic hypotension or anisosphygmia, and heart rate was 65 beats/min. The cardiopulmonary examination was unremarkable, and a continuous murmur was heard in the epigastric region.

- Laboratory Tests:    * Serum creatinine: 96.36 μmol/L (1.09 mg/dL)    * Potassium: 4.4 mmol/L    * B-type natriuretic peptide: 82,500 pg/mL    * Inflammatory markers: normal    * Urinalysis: unremarkable without albuminuria  - Imaging Studies:    * Transthoracic echocardiogram: left ventricular mass index of 110 g/m² without other relevant changes    * Abdominal CT angiogram:      Title: Contrast-enhanced abdominal CT      Description: Righ…

## Options
- A: Systemic vasculitis
- B: Erdheim-Chester Disease **←gold**
- C: Mixed Langerhans cell histiocytosis (LCH) and Erdheim-Chester disease (ECD) with renovascular hypertension **←gold**
- D: Fibromuscular dysplasia

## Backbone e7

- S2 n=45 gold_rank=16
  - clusters: gold=1 near=6 other=38
- S3 shortlist (5):
  - [other] Takayasu arteritis
  - [other] Fibromuscular dysplasia
  - [other] Polyarteritis nodosa
  - [other] Atherosclerosis
  - [near] Moyamoya disease
    - why_kept(Takayasu arteritis): High-grade ostial stenosis of multiple arteries, including renal, celiac trunk, and superior mesenteric arteries, is consistent with large vessel vasculitis
    - why_kept(Fibromuscular dysplasia): Right kidney atrophy and high-grade ostial stenosis of renal artery are consistent with this diagnosis
    - why_kept(Polyarteritis nodosa): Multisystem involvement, including hypertension, kidney atrophy, and vascular abnormalities, could be explained by this medium vessel vasculitis
    - why_kept(Atherosclerosis): Untreated dyslipidemia and high blood pressure increase the risk of atherosclerotic disease, which could contribute to the patient's vascular abnormalities
    - why_kept(Moyamoya disease): High-grade ostial stenosis of multiple arteries and presence of difficult-to-treat hypertension could be related to this rare cerebrovascular disease
- S4 champion: **Takayasu arteritis** cluster=other jaccard=0.00
- S4 rationale: The patient's presentation of difficult-to-treat hypertension, high-grade ostial stenosis of multiple arteries (including the left renal, celiac trunk, and superior mesenteric arteries) as seen on the abdominal CT angiogram, and the absence of atherosclerotic risk factors (such as smoking or diabetes) are key findings that support Takayasu arteritis. Additionally, the patient's age and the involvement of multiple large arteries are consistent with this diagnosis.
- S4 rejected:
  - [other] Fibromuscular dysplasia: While fibromuscular dysplasia can cause hypertension and renal artery stenosis, it typically affects medium and small-sized arteries and is less likely to cause the high-grade ostial stenosis of multiple large arteries seen in this patient.
  - [other] Polyarteritis nodosa: Polyarteritis nodosa is a vasculitis that typically affects smaller arteries and is often associated with systemic symptoms and inflammatory markers, which are not present in this case.
  - [other] Atherosclerosis: Atherosclerosis is unlikely given the patient's low body mass index, lack of smoking history, and absence of other atherosclerotic risk factors, as well as the pattern of arterial involvement.
  - [near] Moyamoya disease: Moyamoya disease primarily affects the intracranial arteries and is not consistent with the pattern of arterial stenosis seen in this patient, which involves large arteries in the abdominal region.

## B06 (code=`b06_judge_miss` locus=`supervisor_hit_judge_miss`)
- supervisor: ['Renal artery stenosis', 'Renovascular hypertension']
  clusters: {'gold': 1, 'near': 0, 'other': 1, 'empty': 0}
- discussion labels (n=15): ['Renal artery stenosis', 'Hypertension', 'Atherosclerosis', 'Renovascular hypertension', 'Fibromuscular dysplasia', 'Renal artery stenosis', 'Renovascular hypertension', 'Atherosclerosis']
- votes=3 turns=3

## B07 (code=`b07_mapper_rescue` locus=`diagnose_miss_but_scored_ok`)
- draft: ['Renal Artery Stenosis', 'Secondary Hypertension']
- diagnose: ['Renal Artery Stenosis', 'Secondary Hypertension']
- queries: ['difficult-to-treat hypertension causes', 'renal artery stenosis diagnosis', 'diethylenetriamine pentaacetate renogram interpretation']

## B01 (code=`na` locus=`na`)
_na_

## APHHM
_na_

