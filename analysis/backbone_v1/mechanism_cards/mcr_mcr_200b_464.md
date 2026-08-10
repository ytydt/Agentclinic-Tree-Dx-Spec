# MCR / mcr_200b / case 464

- **gold**: ruptured popliteal artery aneurysm
- **layer**: `base_win_rank` · **layer_aphhm**: ``
- **correct**: e7=0 v0=0 B06=1 B07=1 B01=1 APHHM=
- **e7_locus**: `s4_hit_judge_miss` · **e7_fail_code**: `s4_hit_judge_miss`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=1 e7_champ_cluster=gold B06_sup_gold=1 B07_diag_gold=1 same_cluster_flip=1 true_entrance=0
- **APHHM**: locus=`na` code=`na` prune_e7_ok=0

## Vignette
A 96-year-old man with benign prostatic disease and dementia presented after a collapse at home. On admission, he had normocytic anemia (hemoglobin 119 g/L), a D-dimer of 1095 ng/mL, normal troponin, normal C-reactive protein, and neutrophilia (10.44 × 10^9/L). A diagnosis of venous thromboembolism was considered but excluded on the basis of Well’s score, and he was discharged with antibiotics for a presumed urinary tract infection. The next day, he returned with a swollen right knee and thigh and extensive bruising, findings that were suspicious for deep vein thrombosis. Lower limb ultrasound showed a patent venous system and identified a 45 mm popliteal artery aneurysm with an 11.4 × 5.2 cm medial leg hematoma. Seven days later, he was admitted emergently with worsening right-leg pain and difficulty walking. Examination revealed extensive bruising behind the right knee and posterior-medial thigh, a pulsatile mass extending into the mid-thigh, and a pulseless right foot without signs of acute ischemia. Repeat hemoglobin was 77 g/L. Computed tomography angiography demonstrated a 4 × 5 cm saccular popliteal artery aneurysm with a large posterior thigh collection measuring approximat…

## Backbone e7

- S2 n=47 gold_rank=1
  - clusters: gold=1 near=5 other=41
- S3 shortlist (5):
  - [gold] Popliteal artery aneurysm
  - [near] Peripheral artery disease
  - [other] Thromboangiitis obliterans
  - [other] Fibromuscular dysplasia
  - [other] Buerger's disease
    - why_kept(Popliteal artery aneurysm): Patient has a confirmed 4 × 5 cm saccular popliteal artery aneurysm with a large posterior thigh collection
    - why_kept(Peripheral artery disease): Patient has severely diseased but patent runoff vessels, indicating possible peripheral artery disease
    - why_kept(Thromboangiitis obliterans): Patient's age and presentation with limb ischemia and aneurysm could be consistent with thromboangiitis obliterans
    - why_kept(Fibromuscular dysplasia): Patient's aneurysm and vascular disease could be related to fibromuscular dysplasia, a rare but possible cause
    - why_kept(Buerger's disease): Patient's presentation with limb ischemia, aneurysm, and hematoma could be consistent with Buerger's disease, a rare but clinically plausible diagnosis
- S4 champion: **Popliteal artery aneurysm** cluster=gold jaccard=0.75
- S4 rationale: The patient's presentation with a swollen right knee and thigh, extensive bruising, and a pulseless right foot, combined with imaging findings of a 4 × 5 cm saccular popliteal artery aneurysm, strongly supports this diagnosis
- S4 rejected:
  - [near] Peripheral artery disease: While the patient has severely diseased runoff vessels, the primary issue is the aneurysm, not the disease of the peripheral arteries
  - [other] Thromboangiitis obliterans: This condition typically affects younger patients and is associated with tobacco use, which is not mentioned in the vignette
  - [other] Fibromuscular dysplasia: This condition is more common in younger women and typically affects the renal and internal carotid arteries, not the popliteal artery
  - [other] Buerger's disease: This condition is also associated with tobacco use and typically affects the distal arteries of the limbs, but the patient's presentation and imaging findings are more consistent with a popliteal artery aneurysm

## B06 (code=`b06_ok` locus=`supervisor_ok`)
- supervisor: ['Ruptured popliteal artery aneurysm', 'Hematoma']
  clusters: {'gold': 1, 'near': 0, 'other': 1, 'empty': 0}
- discussion labels (n=15): ['Ruptured popliteal artery aneurysm', 'Deep vein thrombosis', 'Pulmonary embolism', 'Arterial thrombosis', 'Hematoma', 'Ruptured popliteal artery aneurysm', 'Hematoma', 'Arterial thrombosis']
- votes=3 turns=3

## B07 (code=`b07_ok` locus=`diagnose_ok`)
- draft: ['Ruptured Popliteal Artery Aneurysm', 'Deep Vein Thrombosis']
- diagnose: ['Ruptured Popliteal Artery Aneurysm', 'Deep Vein Thrombosis']
- queries: ['popliteal artery aneurysm diagnosis', 'popliteal artery aneurysm symptoms', 'popliteal artery aneurysm treatment', 'venous thromboembolism vs arterial aneurysm']

## B01 (code=`b01_ok` locus=`gen_ok`)
- top2: ['Ruptured popliteal artery aneurysm', 'Popliteal artery aneurysm with associated hematoma']
- queries: ['popliteal artery aneurysm diagnosis', 'ruptured popliteal artery aneurysm symptoms', 'differential diagnosis for lower limb swelling and bruising', 'management of popliteal artery aneurysm with associated hematoma']
- n_chunks=12

## APHHM
_na_

