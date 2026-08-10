# DA / d2_heldout200b / case 701

- **gold**: Arteriocolonic fistula of Inferior Mesenteric Artery Aneurysm (IMAA)
- **layer**: `all_miss_but_recalled` · **layer_aphhm**: ``
- **correct**: e7=0 v0=0 B06=0 B07=0 B01= APHHM=
- **e7_locus**: `s3_hit_s4_miss` · **e7_fail_code**: `parent_vs_subtype`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=1 e7_champ_cluster=near B06_sup_gold=0 B07_diag_gold=0 same_cluster_flip=0 true_entrance=0
- **APHHM**: locus=`na` code=`na` prune_e7_ok=0

## Vignette
A 50-year-old male presented with paroxysmal abdominal pain for 4 days, with pain intensity increasing in the left lower abdomen 7 hours after admission. No history of fever, weight loss, pancreatitis, surgery, hematochezia, vascular diseases, or previous angiography.

- Tenderness in the left lower quadrant of the abdomen- Blood pressure: 145/91 mmHg- Heart rate: 93 beats/min- Respiratory rate: 20 breaths/min

Laboratory Tests:- Hemoglobin: 8.2 g/dl (low; normal range 13.0-17.5 g/dl)- Serum amylase: normal levelImaging Studies:1. Abdominal Ultrasonography:- Revealed massive fluid collection in the abdomen2. Dynamic Contrast-Enhanced Abdominal CT:- Image Title: Preoperative CT examination- Image Description: Nodular contrast medium staining and extravasation in the left middle abdomen, intra-abdominal hemorrhage, pseudoaneurysm formation in the left branch of the inferior mesenteric artery, multiple hematoceles in the abdomen and pelvis3. Digital Subtraction Angiography (DSA):- Image Title: IMA digital subtraction angiography- Image Description: Pseudoaneurysm formation, 4 mm in diameter, arising from the left branch of the inferior mesenteric artery

What is the most likely diagno…

## Options
- A: Ruptured pseudoaneurysm of the left branch of the inferior mesenteric artery
- B: Inferior mesenteric artery pseudoaneurysm with rupture
- C: Arteriocolonic fistula of Inferior Mesenteric Artery Aneurysm (IMAA) **←gold**
- D: Mesenteric vascular malformation with hemorrhage

## Backbone e7

- S2 n=46 gold_rank=2
  - clusters: gold=1 near=15 other=30
- S3 shortlist (5):
  - [near] Pseudoaneurysm of the inferior mesenteric artery
  - [gold] Inferior mesenteric artery aneurysm
  - [other] Intra-abdominal hemorrhage due to trauma
  - [near] Ruptured abdominal aortic aneurysm
  - [other] Polyarteritis nodosa
    - why_kept(Pseudoaneurysm of the inferior mesenteric artery): Directly confirmed by DSA and consistent with CT findings of pseudoaneurysm formation and intra-abdominal hemorrhage
    - why_kept(Inferior mesenteric artery aneurysm): Supported by imaging findings of pseudoaneurysm and hemorrhage, with the aneurysm being a possible cause of the pseudoaneurysm
    - why_kept(Intra-abdominal hemorrhage due to trauma): Although no history of trauma is mentioned, the presence of intra-abdominal hemorrhage and hematoceles could suggest a traumatic cause
    - why_kept(Ruptured abdominal aortic aneurysm): Although less likely given the specific location of the pseudoaneurysm, a ruptured abdominal aortic aneurysm could still cause intra-abdominal hemorrhage
    - why_kept(Polyarteritis nodosa): A systemic vasculitis that could potentially cause aneurysms and hemorrhage, although less directly supported by the provided information
- S4 champion: **Pseudoaneurysm of the inferior mesenteric artery** cluster=near jaccard=0.33
- S4 rationale: The patient's presentation of paroxysmal abdominal pain, low hemoglobin, and imaging findings of nodular contrast medium staining, extravasation, intra-abdominal hemorrhage, and pseudoaneurysm formation in the left branch of the inferior mesenteric artery, as confirmed by DSA, strongly support this diagnosis
- S4 rejected:
  - [gold] Inferior mesenteric artery aneurysm: While aneurysm is a related condition, the specific finding of pseudoaneurysm, which is a leakage of arterial blood from an artery into the surrounding tissue with a persistent communication between the originating artery and the resultant adjacent cavity, is more precise
  - [other] Intra-abdominal hemorrhage due to trauma: There is no history of trauma provided in the case
  - [near] Ruptured abdominal aortic aneurysm: The imaging studies specifically identify the pseudoaneurysm in the left branch of the inferior mesenteric artery, not the abdominal aorta
  - [other] Polyarteritis nodosa: This condition is a type of vasculitis that affects medium-sized arteries, but the case presentation and imaging findings do not provide evidence of widespread arterial involvement characteristic of polyarteritis nodosa

## B06 (code=`b06_supervisor_drop` locus=`agents_hit_supervisor_drop`)
- supervisor: ['Ruptured Pseudoaneurysm of the Inferior Mesenteric Artery', 'Intra-abdominal Hemorrhage']
  clusters: {'gold': 0, 'near': 1, 'other': 1, 'empty': 0}
- discussion labels (n=15): ['Ruptured Pseudoaneurysm of the Inferior Mesenteric Artery', 'Intra-abdominal Hemorrhage', 'Hematocele', 'Mesenteric Artery Aneurysm', 'Gastrointestinal Bleeding', 'Ruptured Pseudoaneurysm of the Inferior Mesenteric Artery', 'Intra-abdominal Hemorrhage', 'Hematocele']
- votes=3 turns=3

## B07 (code=`b07_draft_miss` locus=`draft_miss`)
- draft: ['Ruptured Pseudoaneurysm of the Inferior Mesenteric Artery', 'Intra-Abdominal Hemorrhage due to Arterial Injury']
- diagnose: ['Ruptured Pseudoaneurysm of the Inferior Mesenteric Artery', 'Intra-Abdominal Hemorrhage due to Arterial Injury']
- queries: ['A 50-year-old male presented with paroxysmal abdominal pain for 4 days, with pain intensity increasing in the left lower abdomen 7 hours after admission. No history of fever, weight loss, pancreatitis', 'differential diagnosis A 50-year-old male presented with paroxysmal abdominal pain for 4 days, with pain intensity increasing in the left lower abdomen 7 hours after admission. No history of fever, weight loss, pancreatitis', 'clinical manifestations diagnosis ory rate: 20 breaths/min Laboratory Tests:- Hemoglobin: 8.2 g/dl (low; normal range 13.0-17.5 g/dl)- Serum amylase: normal levelImaging Studies:1. Abdominal Ult']

## B01 (code=`na` locus=`na`)
_na_

## APHHM
_na_

