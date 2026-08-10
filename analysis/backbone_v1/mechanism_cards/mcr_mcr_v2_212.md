# MCR / mcr_v2 / case 212

- **gold**: Neurofibromatosis type 2
- **layer**: `base_win_recall` · **layer_aphhm**: ``
- **correct**: e7=0 v0=0 B06=1 B07=0 B01=0 APHHM=
- **e7_locus**: `s2_miss` · **e7_fail_code**: `s2_miss`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=0 e7_champ_cluster=near B06_sup_gold=1 B07_diag_gold=1 same_cluster_flip=0 true_entrance=1
- **APHHM**: locus=`na` code=`na` prune_e7_ok=0

## Vignette
An 18-year-old Chinese woman noted a grey dot in the central vision of her left eye 4 days before presentation. She had a known plexiform neurofibroma of the arm confirmed by biopsy 1 year earlier; otherwise, she denied medical history, trauma, family history, smoking, coffee, tea, illicit drugs, or oral contraceptive use. Blood pressure was 110/70 mmHg. Visual acuity was 20/20 in the right eye and 20/25 in the left eye, with no relative afferent pupillary defect. Slit-lamp examination showed mild subcapsular cataracts bilaterally. Automated perimetry revealed a small central scotoma in the left eye. Fundus examination demonstrated a swollen optic disc in the right eye and, in the left eye, a parafoveal grey-white deep retinal lesion and a cotton-wool spot in the posterior pole. Fluorescein angiography showed a focal retinal filling defect corresponding to the cotton-wool spot and hypofluorescence without leakage at the right optic disc. Swept-source optical coherence tomography of the left macula revealed hyperreflective bands in the inner nuclear layer consistent with paracentral acute middle maculopathy. Carotid Doppler ultrasound and transthoracic echocardiography were normal. …

## Backbone e7

- S2 n=49 gold_rank=None
  - clusters: gold=0 near=1 other=48
- S3 shortlist (5):
  - [near] Neurofibromatosis type 1
  - [other] Paracentral acute middle maculopathy
  - [other] Optic neuritis
  - [other] Neurofibroma-related optic glioma
  - [other] Multiple sclerosis
    - why_kept(Neurofibromatosis type 1): Patient has known plexiform neurofibroma and bilateral vestibular schwannomas
    - why_kept(Paracentral acute middle maculopathy): Swept-source optical coherence tomography showed hyperreflective bands in the inner nuclear layer
    - why_kept(Optic neuritis): Patient presents with acute monocular visual disturbance and optic disc swelling
    - why_kept(Neurofibroma-related optic glioma): Patient has history of neurofibroma and presents with optic disc swelling
    - why_kept(Multiple sclerosis): Patient presents with optic neuritis and has white matter lesions on brain MRI
- S4 champion: **Neurofibromatosis type 1** cluster=near jaccard=1.00
- S4 rationale: The patient has a known plexiform neurofibroma of the arm, bilateral vestibular schwannomas, and a parasellar mass consistent with a meningioma, which are all characteristic features of Neurofibromatosis type 1.
- S4 rejected:
  - [other] Paracentral acute middle maculopathy: While the patient has a parafoveal grey-white deep retinal lesion consistent with paracentral acute middle maculopathy, this is not a diagnosis that explains the overall clinical picture.
  - [other] Optic neuritis: There is no clear evidence of optic neuritis, as the patient has no relative afferent pupillary defect and the visual acuity is relatively preserved.
  - [other] Neurofibroma-related optic glioma: There is no evidence of an optic glioma on the provided imaging studies.
  - [other] Multiple sclerosis: The patient's brain MRI shows no evidence of demyelinating lesions typical of multiple sclerosis, and the clinical presentation is not consistent with this diagnosis.

## B06 (code=`b06_ok` locus=`supervisor_ok`)
- supervisor: ['Neurofibromatosis type 2', 'Paracentral acute middle maculopathy']
  clusters: {'gold': 1, 'near': 0, 'other': 1, 'empty': 0}
- discussion labels (n=15): ['Neurofibromatosis type 2', 'Neurofibromatosis type 1', 'Paracentral acute middle maculopathy', 'Meningioma', 'Optic neuritis', 'Neurofibromatosis type 2', 'Neurofibromatosis type 1', 'Paracentral acute middle maculopathy']
- votes=3 turns=3

## B07 (code=`b07_judge_miss` locus=`diagnose_hit_judge_miss`)
- draft: ['Neurofibromatosis Type 2', 'Neurofibromatosis Type 1']
- diagnose: ['Neurofibromatosis Type 2', 'Neurofibromatosis Type 1']
- queries: ['Neurofibromatosis type 1 and vision loss', 'Plexiform neurofibroma and eye symptoms', 'Bilateral vestibular schwannomas and meningioma diagnosis']

## B01 (code=`b01_gen_miss` locus=`rag_hit_gen_miss`)
- top2: ['Neurofibromatosis type 1', 'Paracentral acute middle maculopathy']
- queries: ['neurofibromatosis type 1 and vision loss', 'paracentral acute middle maculopathy causes', 'optic disc swelling and grey-white retinal lesions', 'plexiform neurofibroma and associated ocular findings']
- n_chunks=12

## APHHM
_na_

