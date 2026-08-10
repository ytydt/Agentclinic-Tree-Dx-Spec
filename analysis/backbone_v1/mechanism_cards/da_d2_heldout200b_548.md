# DA / d2_heldout200b / case 548

- **gold**: Rhabdomyolysis associated with Relugolix
- **layer**: `all_miss_but_recalled` · **layer_aphhm**: ``
- **correct**: e7=0 v0=0 B06=0 B07=0 B01= APHHM=
- **e7_locus**: `s4_hit_judge_miss` · **e7_fail_code**: `s4_hit_judge_miss`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=1 e7_champ_cluster=gold B06_sup_gold=1 B07_diag_gold=1 same_cluster_flip=0 true_entrance=0
- **APHHM**: locus=`na` code=`na` prune_e7_ok=0

## Vignette
A 76-year-old man with numerous cardiovascular comorbid conditions presented with weeks of worsening renal function leading to hospitalization. Home medications included rosuvastatin, aspirin, prasugrel, sacubitril-valsartan, metoprolol succinate, ezetimibe, furosemide, and ferrous sulfate. Several weeks after starting a new medication, he experienced decreased appetite, weakness, and fatigue, which persisted for several months. The medication was discontinued after approximately 3.5 months of treatment (two weeks before hospitalization). Despite discontinuation, he still experienced poor appetite and profound weakness, needing a wheelchair. He had one fall approximately one week before presentation, during which he was briefly immobilized.

Patient required wheelchair for mobility. No evidence of physical trauma or findings concerning for compartment syndrome was noted. Subsequently developed reduced left ventricular ejection fraction, oliguria, and rapid atrial fibrillation.

- Laboratory Tests:    * Serum creatinine increased to 760.24 µmol/L (8.61 mg/dL)    * Creatine kinase level: 10,698 U/L    * Urinalysis showed myoglobinuria    * Urine sediment showed acute tubular necrosis…

## Options
- A: Statin-induced rhabdomyolysis (leading to acute tubular necrosis)
- B: Rhabdomyolysis associated with Relugolix **←gold**
- C: Rhabdomyolysis-induced acute kidney injury
- D: Prolonged immobility–related rhabdomyolysis

## Backbone e7

- S2 n=51 gold_rank=1
  - clusters: gold=1 near=3 other=47
- S3 shortlist (5):
  - [gold] Rhabdomyolysis
  - [other] Acute Tubular Necrosis
  - [other] Statins-induced myopathy
  - [other] Cardiorenal syndrome
  - [other] Chronic kidney disease
    - why_kept(Rhabdomyolysis): Patient presented with muscle weakness, elevated creatine kinase level, and myoglobinuria, which are characteristic of rhabdomyolysis
    - why_kept(Acute Tubular Necrosis): Urine sediment showed acute tubular necrosis with muddy brown casts, and patient had elevated serum creatinine and hyperkalemia
    - why_kept(Statins-induced myopathy): Patient was taking rosuvastatin, a statin, which can cause myopathy, and presented with muscle weakness and elevated creatine kinase level
    - why_kept(Cardiorenal syndrome): Patient had cardiovascular comorbid conditions, presented with worsening renal function, and developed reduced left ventricular ejection fraction and rapid atrial fibrillation
    - why_kept(Chronic kidney disease): Patient had progressive renal dysfunction, and laboratory tests showed elevated serum creatinine and hyperkalemia
- S4 champion: **Rhabdomyolysis** cluster=gold jaccard=0.25
- S4 rationale: The patient's elevated creatine kinase level (10,698 U/L) and myoglobinuria, along with symptoms of muscle weakness and fatigue, are consistent with rhabdomyolysis, which is further supported by the presence of acute tubular necrosis with muddy brown casts in the urine sediment.
- S4 rejected:
  - [other] Acute Tubular Necrosis: While the patient has acute tubular necrosis, it is likely a consequence of rhabdomyolysis rather than the primary diagnosis.
  - [other] Statins-induced myopathy: Although the patient is on rosuvastatin, a statin, the severity of symptoms and lab findings suggest a more acute and severe condition like rhabdomyolysis.
  - [other] Cardiorenal syndrome: The patient's cardiovascular comorbidities and renal dysfunction could suggest cardiorenal syndrome, but the presence of myoglobinuria and significantly elevated creatine kinase points more directly to rhabdomyolysis.
  - [other] Chronic kidney disease: The patient's rapid decline in renal function and the presence of myoglobinuria and elevated creatine kinase are more indicative of an acute process like rhabdomyolysis rather than chronic kidney disease.

## B06 (code=`b06_judge_miss` locus=`supervisor_hit_judge_miss`)
- supervisor: ['Rhabdomyolysis', 'Acute Tubular Necrosis']
  clusters: {'gold': 1, 'near': 0, 'other': 1, 'empty': 0}
- discussion labels (n=15): ['Rhabdomyolysis', 'Acute Tubular Necrosis', 'Atrial Fibrillation', 'Chronic Kidney Disease', 'Medication-Induced Nephrotoxicity', 'Rhabdomyolysis', 'Acute Tubular Necrosis', 'Medication-Induced Nephrotoxicity']
- votes=3 turns=3

## B07 (code=`b07_judge_miss` locus=`diagnose_hit_judge_miss`)
- draft: ['Rhabdomyolysis', 'Statin-induced rhabdomyolysis']
- diagnose: ['Rhabdomyolysis', 'Statin-induced rhabdomyolysis']
- queries: ['rhabdomyolysis causes', 'rhabdomyolysis diagnosis', 'medication-induced rhabdomyolysis', 'statin-induced rhabdomyolysis']

## B01 (code=`na` locus=`na`)
_na_

## APHHM
_na_

