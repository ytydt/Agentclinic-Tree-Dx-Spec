# DA / d2_heldout200b / case 731

- **gold**: Mature cystic teratoma in the posterior fossa
- **layer**: `all_miss_but_recalled` · **layer_aphhm**: ``
- **correct**: e7=0 v0=0 B06=0 B07=0 B01= APHHM=
- **e7_locus**: `s2_hit_s3_drop` · **e7_fail_code**: `s2_gold_low_rank`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=0 e7_champ_cluster=other B06_sup_gold=0 B07_diag_gold=0 same_cluster_flip=0 true_entrance=0
- **APHHM**: locus=`na` code=`na` prune_e7_ok=0

## Vignette
A 36-year-old female presented with an 18-year history of intermittent dizziness and blurred vision, accompanied by nausea and vomiting. Symptoms would improve after vomiting. In May 2020, the patient developed posterior occipital tingling, which worsened with emotional agitation but would subside spontaneously after a few minutes. By September 2021, symptoms of dizziness and vomiting became more frequent, leading to hospital consultation.

No specific physical examination findings were reported in the case.

- Imaging Studies:    CT Scan:    - Irregular high-density mass shadow in posterior fossa    - CT value approximately 93HU    - Few bone density shadows at posterior edge        MRI Findings:    - Irregular mixed signals in medial and posterior cerebellum    - Maximum size: 50mm × 41mm × 51mm    - Line-like septum and complex nodules present    - Nodule size: 15mm × 16mm × 13mm    - T1WI: Equal or high signals in cystic part    - T2WI and T2 FLAIR: Low signals    - DWI: Low signals, no diffusion restriction in mural nodules and septum    - SWI: Multiple patchy low and high signals in nodular region        Laboratory Tests:    - Cerebrospinal fluid: AFP (negative), β-HCG (negat…

## Options
- A: Metastatic tumor
- B: Hemangioblastoma
- C: Cystic meningioma
- D: Mature cystic teratoma in the posterior fossa **←gold**

## Backbone e7

- S2 n=50 gold_rank=17
  - clusters: gold=1 near=2 other=47
- S3 shortlist (5):
  - [other] Hemangioblastoma
  - [other] Pilocytic astrocytoma
  - [other] Ependymoma
  - [other] Medulloblastoma
  - [other] Meningioma
    - why_kept(Hemangioblastoma): Posterior fossa mass with cystic components and high-density mass shadow on CT scan
    - why_kept(Pilocytic astrocytoma): Irregular mixed signals on MRI and presence of cystic components
    - why_kept(Ependymoma): Location in posterior fossa and presence of cystic components
    - why_kept(Medulloblastoma): Location in posterior fossa and presence of cystic components, although less likely due to patient's age
    - why_kept(Meningioma): Presence of high-density mass shadow on CT scan and possible dural attachment
- S4 champion: **Hemangioblastoma** cluster=other jaccard=0.00
- S4 rationale: The presence of a cystic mass with a mural nodule in the posterior fossa, as shown on MRI, along with the cyst fluid analysis and the patient's symptoms, is most consistent with Hemangioblastoma. The high-density mass shadow on CT and the mixed signals on MRI also support this diagnosis.
- S4 rejected:
  - [other] Pilocytic astrocytoma: While pilocytic astrocytoma can present with a cystic component, the location and imaging characteristics are less typical for this diagnosis
  - [other] Ependymoma: Ependymomas are more commonly associated with the ventricular system and spinal cord, and the imaging findings do not strongly support this diagnosis
  - [other] Medulloblastoma: Medulloblastoma typically presents in the midline of the cerebellum and has a more aggressive appearance on imaging, which does not match the described case
  - [other] Meningioma: Meningiomas are usually dural-based and have a different appearance on imaging, with more homogeneous enhancement and a distinct dural tail, which is not described in this case

## B06 (code=`b06_supervisor_drop` locus=`agents_hit_supervisor_drop`)
- supervisor: ['Hemangioblastoma', 'Pilocytic Astrocytoma']
  clusters: {'gold': 0, 'near': 0, 'other': 2, 'empty': 0}
- discussion labels (n=15): ['Hemangioblastoma', 'Pilocytic Astrocytoma', 'Medulloblastoma', 'Cavernous Hemangioma', 'Epidermoid Cyst', 'Hemangioblastoma', 'Pilocytic Astrocytoma', 'Epidermoid Cyst']
- votes=3 turns=3

## B07 (code=`b07_draft_miss` locus=`draft_miss`)
- draft: ['Hemangioblastoma', 'Dysplastic Gangliocytoma of the Cerebellum (Lhermitte-Duclos Disease)']
- diagnose: ['Hemangioblastoma', 'Dysplastic Gangliocytoma of the Cerebellum (Lhermitte-Duclos Disease)']
- queries: ['posterior fossa mass with cystic and solid components', 'cerebellar tumor with mixed signals on MRI', 'dizziness and vomiting with posterior occipital tingling']

## B01 (code=`na` locus=`na`)
_na_

## APHHM
_na_

