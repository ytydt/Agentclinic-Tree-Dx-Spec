# MCR / mcr_200b / case 395

- **gold**: Kummell disease
- **layer**: `base_win_rank`
- **correct**: e7=0 v0=1 B06=1 B07=0 B01=0 APHHM=
- **loci**: e7=`s3_hit_s4_miss` B06=`supervisor_ok` B07=`draft_miss` B01=`gen_hit_judge_miss` APHHM=`na`
- **primary_locus**: e7=s3_hit_s4_miss; B06=supervisor_ok
- **covariates**: vig_words=214; gold_words=2; eponym=False; subtype=False; e7_s2_rank=6; mapper_rescue=False
- **causal**: 骨干 S3 含金标，S4 终裁选错。

## Vignette (trunc)
A 28-year-old man who uses a wheelchair presented with severe back pain and inability to walk for two weeks. One month earlier, he had pulled a rug and experienced only mild back pain, which then gradually intensified over weeks and led to progressive bilateral leg weakness and diffuse paresthesia. His past history was notable for bodybuilding with use of licensed and unlicensed substances; there was no significant trauma. On examination, he was barely able to stand. Manual muscle testing showed...

## Backbone e7
- S1 key_facts: 28-year-old man; Uses a wheelchair; Severe back pain for two weeks; Mild back pain after pulling a rug one month earlier; Progressive bilateral leg weakness; Diffuse paresthesia; History of bodybuilding with use of licensed and unlicensed substances; No significant trauma
- S2 mode=complement k=3 pool_n=49 gold_in_s2=True
  - call1: ['Osteoporosis', 'Osteogenesis imperfecta', 'Multiple myeloma', 'Bone metastasis', 'Vertebral osteonecrosis', 'Kummell d
  - call2: ['Eosinophilic granuloma', 'Langerhans cell histiocytosis', 'Gorham-Stout disease', 'Skeletal angioma', 'Osteosarcoma', 
  - call3: ['Gaucher disease', 'Maffucci syndrome', 'Ollier disease', 'Scheuermann disease', 'Spinal tuberculosis', 'Brucellar spon
- S3 shortlist n=5 gold=True: Kummell disease, Osteoporosis, Vertebral osteonecrosis, Spondylolisthesis, Spinal tuberculosis
- S4 champion: **Vertebral osteonecrosis** gold=False
- S4 raw (trunc): {"champion": "Vertebral osteonecrosis", "rationale": "The presence of an intravertebral vacuum cleft and a T2-weighted \"double line sign\" at L5 on MRI are characteristic findings of vertebral osteonecrosis, which is also consistent with the patient's history of steroid use from

## Backbone v0 (compact)
- S1 key_facts: 28-year-old man; Uses a wheelchair; Severe back pain for two weeks; Inability to walk for two weeks; Mild back pain after pulling a rug one month earlier; Progressive intensification of back pain; Bodybuilding with use of licensed and unlicensed substances; No significant trauma
- S2 mode=single k=1 pool_n=19 gold_in_s2=True
  - call1: ['Osteoporosis', 'Osteogenesis imperfecta', 'Multiple myeloma', 'Bone metastasis', 'Vertebral osteonecrosis', 'Kummell d
- S3 shortlist n=5 gold=True: Kummell disease, Osteoporosis, Vertebral osteonecrosis, Multiple myeloma, Bone metastasis
- S4 champion: **Kummell disease** gold=True
- S4 raw (trunc): {"champion": "Kummell disease", "rationale": "The presence of an intravertebral vacuum cleft and a 'double line sign' on MRI, along with a compression fracture and elevated C-reactive protein, are characteristic of Kummell disease, which is a type of vertebral osteonecrosis often

## Baseline B06
- discussion_turns=3
  - turn0 gold_mention=True diag=
    The patient's history of bodybuilding with use of licensed and unlicensed substances, along with the presence of an L2 compression fracture and an L5 burst frac
  - turn1 gold_mention=True diag=
    The patient's symptoms and imaging findings, including the 'double line sign' on MRI, are consistent with Kummell disease, which is a type of vertebral fracture
  - turn2 gold_mention=True diag=
    The patient's symptoms, imaging findings, and history of bodybuilding with use of licensed and unlicensed substances support Kummell disease as the most likely 
- supervisor votes=3 top2=['Kummell disease', 'Osteoporotic compression fracture'] gold=True

## Baseline B07
- draft=['Osteoporotic Vertebral Compression Fractures', 'Vertebral Osteonecrosis'] gold=False
- has_refine=True refine=[] gold=None
- queries(4): ['osteoporotic vertebral fractures', 'vertebral compression fractures in young adults', 'intravertebral vacuum cleft sign', 'double line sign on MRI']
- diagnose=['Osteoporotic Vertebral Compression Fractures', 'Vertebral Osteonecrosis'] gold=False

## Baseline B01
- queries=['causes of vertebral compression fractures in young adults', 'differential diagnosis of bilateral leg weakness and paresthesia', 'intravertebral vacuum cleft significance', 'double line sign on T2-weighted MRI spine']
- n_chunks=12 rag_gold_mention=False
- chunk_sample: 
- top2=['Osteoporotic vertebral compression fracture', 'Kummell disease'] gold=True

