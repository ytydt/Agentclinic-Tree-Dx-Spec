# MCR / mcr_200b / case 294

- **gold**: Undifferentiated embryonal sarcoma of the liver
- **layer**: `all_miss_but_recalled` · **layer_aphhm**: ``
- **correct**: e7=0 v0=0 B06=0 B07=0 B01=0 APHHM=
- **e7_locus**: `s3_hit_s4_miss` · **e7_fail_code**: `rationale_overfit`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=1 e7_champ_cluster=other B06_sup_gold=1 B07_diag_gold=0 same_cluster_flip=0 true_entrance=0
- **APHHM**: locus=`na` code=`na` prune_e7_ok=0

## Vignette
An 8-year-old girl weighing 44.5 kg with no significant medical history presented with a 1-week history of progressive abdominal pain, distension, nausea, and vomiting. Physical examination revealed notable abdominal distension without guarding or rebound. Initial abdominal ultrasonography showed a 17 × 9 cm mixed solid and cystic mass occupying the right hepatic lobe with compression of the inferior vena cava (IVC). By hospital day 7, worsening abdominal distension and concern for abdominal compartment syndrome prompted percutaneous biopsy of the mass and placement of a drain. Over the next several days, persistent sanguineous output from the drain led to anemia and concern for hemorrhage. Contrast-enhanced CT of the chest, abdomen, and pelvis demonstrated an infrarenal IVC thrombus and a near-occlusive embolus in the left pulmonary artery. Transthoracic echocardiography revealed compression of the distal IVC at its junction with the right atrium, with otherwise normal biventricular function and no evidence of elevated right heart pressures.

What is the most likely diagnosis?

Options:
A. Undifferentiated embryonal sarcoma of the liver
B. Hepatic mesenchymal hamartoma was conside…

## Backbone e7

- S2 n=46 gold_rank=3
  - clusters: gold=2 near=6 other=38
- S3 shortlist (5):
  - [other] Hepatoblastoma
  - [gold] Embryonal sarcoma of the liver
  - [other] Hepatic angiosarcoma
  - [gold] Undifferentiated embryonal sarcoma
  - [other] Hepatocellular carcinoma with fibrolamellar variant
    - why_kept(Hepatoblastoma): Large hepatic mass in a child with progressive abdominal pain and vascular complications
    - why_kept(Embryonal sarcoma of the liver): Aggressive hepatic mass with compression of the inferior vena cava and risk of hemorrhage
    - why_kept(Hepatic angiosarcoma): Hepatic mass with vascular invasion and risk of hemorrhage, although rare in children
    - why_kept(Undifferentiated embryonal sarcoma): Similar clinical presentation to embryonal sarcoma, with a large hepatic mass and vascular complications
    - why_kept(Hepatocellular carcinoma with fibrolamellar variant): Although rare in children, the fibrolamellar variant can present with a large hepatic mass and vascular complications
- S4 champion: **Hepatoblastoma** cluster=other jaccard=0.00
- S4 rationale: The patient's age, lack of significant medical history, and presence of a large mixed solid and cystic mass in the liver are consistent with hepatoblastoma, which is the most common primary liver cancer in children.
- S4 rejected:
  - [gold] Embryonal sarcoma of the liver: While possible, embryonal sarcoma is less common than hepatoblastoma in children and typically presents at an older age.
  - [other] Hepatic angiosarcoma: This is a rare tumor that is more commonly associated with exposure to toxic substances and is unlikely in a child with no significant medical history.
  - [gold] Undifferentiated embryonal sarcoma: This diagnosis is less likely given the presence of a distinct mass and the patient's age, which is more consistent with hepatoblastoma.
  - [other] Hepatocellular carcinoma with fibrolamellar variant: This type of cancer is rare in children and typically presents in older adolescents or young adults, making it less likely in this case.

## B06 (code=`b06_judge_miss` locus=`supervisor_hit_judge_miss`)
- supervisor: ['Hepatoblastoma', 'Undifferentiated embryonal sarcoma of the liver']
  clusters: {'gold': 1, 'near': 0, 'other': 1, 'empty': 0}
- discussion labels (n=15): ['Hepatoblastoma', 'Hepatic adenoma', 'Hepatocellular carcinoma', 'Undifferentiated embryonal sarcoma of the liver', 'Mesenchymal hamartoma', 'Hepatoblastoma', 'Undifferentiated embryonal sarcoma of the liver', 'Mesenchymal hamartoma']
- votes=3 turns=3

## B07 (code=`b07_draft_miss` locus=`draft_miss`)
- draft: ['Hepatoblastoma', 'Hepatocellular carcinoma']
- diagnose: ['Hepatoblastoma', 'Hepatocellular carcinoma']
- queries: ['hepatic mass in children', 'abdominal compartment syndrome causes', 'IVC thrombus and pulmonary embolus', 'pediatric liver tumors']

## B01 (code=`b01_rag_miss` locus=`rag_miss`)
- top2: ['Hepatoblastoma', 'Wilms tumor']
- queries: ['abdominal mass in children with IVC compression', 'causes of abdominal compartment syndrome in pediatric patients', 'diagnosis and management of IVC thrombus in children', 'pediatric tumors causing abdominal distension and thromboembolism']
- n_chunks=12

## APHHM
_na_

