# MCR / mcr_200b / case 395

- **gold**: Kummell disease
- **layer**: `base_win_rank` · **layer_aphhm**: ``
- **correct**: e7=0 v0=1 B06=1 B07=0 B01=0 APHHM=
- **e7_locus**: `s3_hit_s4_miss` · **e7_fail_code**: `rationale_overfit`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=1 e7_champ_cluster=other B06_sup_gold=1 B07_diag_gold=0 same_cluster_flip=1 true_entrance=0
- **APHHM**: locus=`na` code=`na` prune_e7_ok=0

## Vignette
A 28-year-old man who uses a wheelchair presented with severe back pain and inability to walk for two weeks. One month earlier, he had pulled a rug and experienced only mild back pain, which then gradually intensified over weeks and led to progressive bilateral leg weakness and diffuse paresthesia. His past history was notable for bodybuilding with use of licensed and unlicensed substances; there was no significant trauma. On examination, he was barely able to stand. Manual muscle testing showed severe left and moderate right weakness of the extensor hallucis longus muscles and moderate weakness of ankle dorsiflexors bilaterally. Quadriceps and ankle plantarflexion strength were normal, and sphincter function was intact. Laboratory testing revealed an elevated C-reactive protein level; other values were unremarkable. Plain radiographs of the lumbosacral spine demonstrated an L2 compression fracture and an L5 burst fracture with canal compromise and an intravertebral vacuum cleft at L5. MRI showed a T2-weighted “double line sign” at L5 without any paravertebral soft-tissue mass or abscess. A whole-body bone scan revealed isolated increased uptake at L2 and L5, with no other areas of…

## Backbone e7

- S2 n=49 gold_rank=6
  - clusters: gold=1 near=7 other=41
- S3 shortlist (5):
  - [gold] Kummell disease
  - [other] Osteoporosis
  - [other] Vertebral osteonecrosis
  - [other] Spondylolisthesis
  - [other] Spinal tuberculosis
    - why_kept(Kummell disease): Intravertebral vacuum cleft and vertebral compression fracture
    - why_kept(Osteoporosis): Compression fractures with minimal trauma
    - why_kept(Vertebral osteonecrosis): T2-weighted "double line sign" at L5 on MRI
    - why_kept(Spondylolisthesis): Bilateral leg weakness and diffuse paresthesia with spinal injury
    - why_kept(Spinal tuberculosis): Elevated C-reactive protein level and spinal injury
- S4 champion: **Vertebral osteonecrosis** cluster=other jaccard=0.00
- S4 rationale: The presence of an intravertebral vacuum cleft and a T2-weighted "double line sign" at L5 on MRI are characteristic findings of vertebral osteonecrosis, which is also consistent with the patient's history of steroid use from bodybuilding.
- S4 rejected:
  - [gold] Kummell disease: While Kummell disease can present with vertebral compression fractures, it typically does not exhibit the distinct MRI findings seen in this patient.
  - [other] Osteoporosis: Osteoporosis could explain the compression fractures, but it does not account for the specific MRI signs of vertebral osteonecrosis.
  - [other] Spondylolisthesis: Spondylolisthesis involves the displacement of a vertebra, which is not the primary issue in this case.
  - [other] Spinal tuberculosis: Spinal tuberculosis would likely present with additional findings such as paravertebral soft-tissue mass or abscess, which are not seen in this patient.

## B06 (code=`b06_ok` locus=`supervisor_ok`)
- supervisor: ['Kummell disease', 'Osteoporotic compression fracture']
  clusters: {'gold': 1, 'near': 0, 'other': 1, 'empty': 0}
- discussion labels (n=15): ['Osteoporotic compression fracture', 'Kummell disease', 'Osteonecrosis of the spine', 'Vertebral fracture with intravertebral vacuum cleft', 'Infectious spondylitis', 'Kummell disease', 'Osteoporotic compression fracture', 'Osteonecrosis of the spine']
- votes=3 turns=3

## B07 (code=`b07_draft_miss` locus=`draft_miss`)
- draft: ['Osteoporotic Vertebral Compression Fractures', 'Vertebral Osteonecrosis']
- diagnose: ['Osteoporotic Vertebral Compression Fractures', 'Vertebral Osteonecrosis']
- queries: ['osteoporotic vertebral fractures', 'vertebral compression fractures in young adults', 'intravertebral vacuum cleft sign', 'double line sign on MRI']

## B01 (code=`b01_judge_miss` locus=`gen_hit_judge_miss`)
- top2: ['Osteoporotic vertebral compression fracture', 'Kummell disease']
- queries: ['causes of vertebral compression fractures in young adults', 'differential diagnosis of bilateral leg weakness and paresthesia', 'intravertebral vacuum cleft significance', 'double line sign on T2-weighted MRI spine']
- n_chunks=12

## APHHM
_na_

