# DA / d2_heldout200b / case 694

- **gold**: Parkinson's Disease
- **layer**: `all_miss_but_recalled` · **layer_aphhm**: ``
- **correct**: e7=0 v0=0 B06=0 B07=0 B01= APHHM=
- **e7_locus**: `s2_hit_s3_drop` · **e7_fail_code**: `s2_near_crowd_out`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=0 e7_champ_cluster=other B06_sup_gold=0 B07_diag_gold=0 same_cluster_flip=0 true_entrance=0
- **APHHM**: locus=`na` code=`na` prune_e7_ok=0

## Vignette
A 70-year-old married male first experienced symptoms in 2013, initially presenting with leg pain. During 2020, the patient experienced worsening of his symptoms. He attended physiotherapy initially on a daily basis, which was later reduced to two or three sessions per week. The patient experienced comorbid symptoms of depression and anxiety.

The patient's main difficulties were noted on his left side. No specific physical examination findings were detailed in the case report.

{'Imaging Studies': [{'Test Type': 'MRI (2013)', 'Title': 'Initial Brain MRI', 'Description': 'Brain aging and partially empty sella turcica with a fine imaging pituitary gland'}, {'Test Type': 'MRI (2020)', 'Title': 'Follow-up Brain MRI', 'Description': 'Mild cerebral atrophy/aging more pronounced in the curvatures of the cerebral hemispheres. Few, micro-ischemic focal lesions in the periventricular and deep white matter of the cerebral hemispheres'}], 'Cognitive Assessment': {'Test': 'Mini Mental State Examination (MMSE)', 'Initial Score': '24/30 at baseline', 'Follow-up Score': '27/30 after treatment'}}

What is the most likely diagnosis?

Options:
A. Mild cognitive impairment (possibly vascular in origi…

## Options
- A: Mild cognitive impairment (possibly vascular in origin)
- B: Parkinson's Disease **←gold**
- C: Lumbar degenerative disc disease or spondylosis
- D: Vascular parkinsonism (small-vessel cerebrovascular disease)

## Backbone e7

- S2 n=51 gold_rank=3
  - clusters: gold=1 near=11 other=39
- S3 shortlist (5):
  - [other] Amyotrophic Lateral Sclerosis
  - [other] Multiple Sclerosis
  - [other] Primary Lateral Sclerosis
  - [other] Hereditary Spastic Paraplegia
  - [other] Corticobasal Degeneration
    - why_kept(Amyotrophic Lateral Sclerosis): Progressive neurological condition with worsening symptoms over time, primarily affecting one side of the body
    - why_kept(Multiple Sclerosis): Comorbid symptoms of depression and anxiety, and brain MRI findings of micro-ischemic focal lesions
    - why_kept(Primary Lateral Sclerosis): Initial presentation with leg pain and progressive worsening of symptoms
    - why_kept(Hereditary Spastic Paraplegia): Family history not provided, but condition could explain progressive neurological symptoms
    - why_kept(Corticobasal Degeneration): Asymmetric neurological symptoms and presence of micro-ischemic focal lesions on brain MRI
- S4 champion: **Primary Lateral Sclerosis** cluster=other jaccard=0.00
- S4 rationale: The patient's initial presentation with leg pain, progressive worsening of symptoms, and main difficulties noted on one side of the body are consistent with Primary Lateral Sclerosis. The absence of specific physical examination findings and the presence of comorbid depression and anxiety also align with this diagnosis.
- S4 rejected:
  - [other] Amyotrophic Lateral Sclerosis: ALS typically presents with both upper and lower motor neuron signs, which are not mentioned in the case report.
  - [other] Multiple Sclerosis: MS typically presents with optic neuritis, sensory symptoms, or brainstem symptoms, which are not mentioned in the case report.
  - [other] Hereditary Spastic Paraplegia: HSP is a genetic disorder, and there is no mention of a family history or genetic testing in the case report.
  - [other] Corticobasal Degeneration: CBD typically presents with a combination of motor and cognitive symptoms, and the patient's MMSE scores do not indicate significant cognitive decline.

## B06 (code=`b06_supervisor_drop` locus=`agents_hit_supervisor_drop`)
- supervisor: ['Vascular Dementia', 'Mixed Dementia']
  clusters: {'gold': 0, 'near': 0, 'other': 2, 'empty': 0}
- discussion labels (n=15): ['Vascular Dementia', 'Mixed Dementia', "Alzheimer's Disease", 'Frontotemporal Dementia', 'Depression with Cognitive Impairment', 'Vascular Dementia', "Alzheimer's Disease", 'Mixed Dementia']
- votes=3 turns=3

## B07 (code=`b07_draft_miss` locus=`draft_miss`)
- draft: ['Vascular Dementia', 'Small Vessel Disease']
- diagnose: ['Vascular Dementia', 'Small Vessel Disease']
- queries: ['small vessel disease', 'vascular dementia', 'depression and anxiety in elderly']

## B01 (code=`na` locus=`na`)
_na_

## APHHM
_na_

