# MCR / mcr_200b / case 456

- **gold**: Ureteroarterial fistula
- **layer**: `base_win_recall` · **layer_aphhm**: ``
- **correct**: e7=0 v0=0 B06=1 B07=0 B01=0 APHHM=
- **e7_locus**: `s2_miss` · **e7_fail_code**: `s2_miss`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=0 e7_champ_cluster=other B06_sup_gold=1 B07_diag_gold=0 same_cluster_flip=0 true_entrance=1
- **APHHM**: locus=`na` code=`na` prune_e7_ok=0

## Vignette
An 80-year-old woman with a history of rectal cancer treated in 2008 by liver metastasectomy followed by Hartmann’s procedure with intraoperative radiotherapy (5×5 Gy) and adjuvant capecitabine, oxaliplatin, and bevacizumab presented in January 2011 with intermittent gross hematuria. Since December 2009 she had bilateral JJ stents for ureteral strictures, replaced regularly. In November 2010 she required drainage of a pelvic abscess after stent occlusion complicated by Candida glabrata infection. Her medical history also included type 2 diabetes mellitus and angina pectoris.

On presentation, her hemoglobin was 7.2 mmol/L and creatinine was 370 μmol/L. Renal ultrasound showed bilateral hydronephrosis. Because of persistent hematuria and suspected stent occlusion, cystoscopy and ureteral stent exchange were performed: removal of the right double-J catheter revealed pulsatile arterial bleeding from the right ureteral orifice. The stent was changed, bleeding subsided, and she received four units of packed red cells intraoperatively. Open surgery was considered too high risk.

A CT angiogram demonstrated active hemorrhage at the right renal pelvis with clots in the collecting system. T…

## Backbone e7

- S2 n=48 gold_rank=None
  - clusters: gold=0 near=3 other=45
- S3 shortlist (5):
  - [other] Radiation cystitis
  - [near] Ureteroenteric fistula
  - [near] Arteriovenous fistula
  - [other] Pseudoaneurysm
  - [other] Ureteral stricture
    - why_kept(Radiation cystitis): History of pelvic radiation and recurrent gross hematuria
    - why_kept(Ureteroenteric fistula): Ureteroileal fistula found during left stent repositioning
    - why_kept(Arteriovenous fistula): Pulsatile arterial bleeding from the right ureteral orifice
    - why_kept(Pseudoaneurysm): Active hemorrhage at the right renal pelvis with clots in the collecting system
    - why_kept(Ureteral stricture): History of bilateral JJ stents for ureteral strictures and recurrent hematuria
- S4 champion: **Radiation cystitis** cluster=other jaccard=0.00
- S4 rationale: The patient's history of intraoperative radiotherapy and subsequent development of hematuria, ureteral strictures, and hydronephrosis are consistent with radiation-induced damage to the urinary tract, which is a common cause of radiation cystitis.
- S4 rejected:
  - [near] Ureteroenteric fistula: Although a ureteroileal fistula was found, it does not fully explain the patient's initial presentation of gross hematuria and bilateral hydronephrosis.
  - [near] Arteriovenous fistula: There is no direct evidence of an arteriovenous fistula, and the patient's symptoms are more consistent with radiation-induced damage.
  - [other] Pseudoaneurysm: The embolisation of the right renal artery with coils was performed to control bleeding, but there is no indication of a pseudoaneurysm.
  - [other] Ureteral stricture: While the patient has a history of ureteral strictures, it does not fully explain the patient's gross hematuria and bilateral hydronephrosis.

## B06 (code=`b06_ok` locus=`supervisor_ok`)
- supervisor: ['Ureteroarterial fistula', 'Ureteroileal fistula']
  clusters: {'gold': 1, 'near': 1, 'other': 0, 'empty': 0}
- discussion labels (n=15): ['Ureteroarterial fistula', 'Ureteral stricture', 'Ureteroileal fistula', 'Pelvic abscess', 'Arteriovenous malformation', 'Ureteroarterial fistula', 'Ureteroileal fistula', 'Arteriovenous malformation']
- votes=3 turns=3

## B07 (code=`b07_draft_miss` locus=`draft_miss`)
- draft: ['Radiation-induced ureteral damage', 'Ureteroileal fistula with recurrent hematuria']
- diagnose: ['Radiation-induced ureteral damage', 'Ureteroileal fistula with recurrent hematuria']
- queries: ['ureteral bleeding causes', 'radiation-induced ureteral damage', 'ureteroileal fistula complications', 'hematuria in cancer patients']

## B01 (code=`b01_gen_miss` locus=`rag_hit_gen_miss`)
- top2: ['Radiation Cystitis', 'Ureteroileal Fistula']
- queries: ['causes of gross hematuria in patients with history of pelvic radiation', 'management of ureteroileal fistula', 'complications of ureteral stent placement', 'embolization techniques for renal artery bleeding']
- n_chunks=12

## APHHM
_na_

