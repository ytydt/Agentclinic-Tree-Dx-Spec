# MCR / mcr_v2 / case 166

- **gold**: Contrast-induced encephalopathy
- **layer**: `base_win_recall` · **layer_aphhm**: ``
- **correct**: e7=0 v0=0 B06=1 B07=1 B01=1 APHHM=
- **e7_locus**: `s2_miss` · **e7_fail_code**: `s2_miss`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=0 e7_champ_cluster=near B06_sup_gold=1 B07_diag_gold=1 same_cluster_flip=0 true_entrance=1
- **APHHM**: locus=`na` code=`na` prune_e7_ok=0

## Vignette
A 2-month-old full-term female with known complex congenital heart disease (single ventricle defect, double-outlet right ventricle with D-transposition of the great arteries, and an ostium secundum atrial septal defect with left superior vena cava) was admitted for evaluation of occasional cyanosis. She was in good general condition, weighed 5 kg, had an oxygen saturation of 80%, and showed no signs of respiratory distress. Her medications included furosemide and spironolactone. The team planned a pulmonary artery banding, but during the procedure the patient became hemodynamically unstable and suffered a cardiorespiratory arrest requiring cardiac massage, so the operation was aborted. To gather hemodynamic data, cardiac catheterization was performed via the left femoral artery, with the catheter tip in the single ventricle, using serial doses of nonionic iodinated contrast (Iopromide) totaling 3 mL/kg over 30 minutes. Approximately 12 hours after the procedure, the patient developed clonic movements of the left upper limb and persistent sucking motions. A noncontrast head CT obtained after this first seizure showed a slight diffuse increase in cortical density predominantly in the…

## Backbone e7

- S2 n=50 gold_rank=None
  - clusters: gold=0 near=5 other=45
- S3 shortlist (5):
  - [near] Hypoxic-Ischemic Encephalopathy
  - [other] Cerebral Edema
  - [other] Seizure Disorder
  - [near] Mitochondrial Encephalopathy, Lactic Acidosis, and Stroke-like Episodes (MELAS)
  - [near] Neonatal Encephalopathy with Seizures in Term Newborns
    - why_kept(Hypoxic-Ischemic Encephalopathy): Patient experienced cardiorespiratory arrest and has complex congenital heart disease, which increases the risk of hypoxic-ischemic injury
    - why_kept(Cerebral Edema): Noncontrast head CT showed diffuse increase in cortical density, suggesting cerebral edema
    - why_kept(Seizure Disorder): Patient developed clonic movements of the left upper limb and persistent sucking motions, indicating a seizure disorder
    - why_kept(Mitochondrial Encephalopathy, Lactic Acidosis, and Stroke-like Episodes (MELAS)): Patient has complex congenital heart disease and developed seizures, which could be related to a mitochondrial disorder
    - why_kept(Neonatal Encephalopathy with Seizures in Term Newborns): Patient is a 2-month-old full-term female with seizures and encephalopathy, which fits the criteria for this condition
- S4 champion: **Hypoxic-Ischemic Encephalopathy** cluster=near jaccard=0.20
- S4 rationale: The patient experienced cardiorespiratory arrest during the procedure, which likely led to a period of hypoxia-ischemia, and subsequently developed seizures and changes in cortical density on the head CT, consistent with hypoxic-ischemic encephalopathy.
- S4 rejected:
  - [other] Cerebral Edema: While cerebral edema could be a consequence of the hypoxic-ischemic event, it does not fully explain the seizures and the specific pattern of cortical density changes seen on the CT.
  - [other] Seizure Disorder: The seizures in this case are more likely a symptom of an underlying condition rather than a primary seizure disorder.
  - [near] Mitochondrial Encephalopathy, Lactic Acidosis, and Stroke-like Episodes (MELAS): There is no indication of mitochondrial disease or lactic acidosis in the provided information, making MELAS an unlikely diagnosis.
  - [near] Neonatal Encephalopathy with Seizures in Term Newborns: This condition is more general and does not specifically account for the hypoxic-ischemic event during the procedure as well as the subsequent neurological findings.

## B06 (code=`b06_ok` locus=`supervisor_ok`)
- supervisor: ['Contrast-Induced Encephalopathy', 'Cerebral Edema']
  clusters: {'gold': 1, 'near': 0, 'other': 1, 'empty': 0}
- discussion labels (n=15): ['Cerebral Edema', 'Hypoxic-Ischemic Encephalopathy', 'Contrast-Induced Encephalopathy', 'Seizure Disorder', 'Intracranial Hemorrhage', 'Contrast-Induced Encephalopathy', 'Hypoxic-Ischemic Encephalopathy', 'Cerebral Edema']
- votes=3 turns=3

## B07 (code=`b07_ok` locus=`diagnose_ok`)
- draft: ['Contrast-induced encephalopathy', 'Cerebral complication related to complex congenital heart disease']
- diagnose: ['Contrast-induced encephalopathy', 'Cerebral complication related to complex congenital heart disease']
- queries: ['contrast-induced encephalopathy in pediatric patients', 'Iopromide side effects', 'single ventricle defect and cerebral complications', 'cardiac catheterization complications in infants']

## B01 (code=`b01_ok` locus=`gen_ok`)
- top2: ['Contrast-induced encephalopathy', 'Hypoxic-ischemic encephalopathy']
- queries: ['contrast-induced encephalopathy in pediatric patients', 'seizures after cardiac catheterization with iodinated contrast', 'cerebral injury following cardiac procedures in infants', 'neurological complications of nonionic iodinated contrast agents in children']
- n_chunks=12

## APHHM
_na_

