# MCR / mcr_v2 / case 237

- **gold**: Peripheral odontoma
- **layer**: `all_miss_but_recalled` · **layer_aphhm**: ``
- **correct**: e7=0 v0=0 B06=0 B07=0 B01=0 APHHM=
- **e7_locus**: `s3_hit_s4_miss` · **e7_fail_code**: `rationale_overfit`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=1 e7_champ_cluster=other B06_sup_gold=1 B07_diag_gold=0 same_cluster_flip=0 true_entrance=0
- **APHHM**: locus=`na` code=`na` prune_e7_ok=0

## Vignette
A 30-year-old man was referred for evaluation of an asymptomatic, calcified mass on the right anterior maxilla that had been present for 18 months. On intraoral examination, there was a mucosal fenestration through which a hard, mineralized structure approximately 1 cm in diameter was visible. A periapical radiograph of the upper right premolar area demonstrated a discrete radiopaque lesion. The initial diagnostic hypothesis was maxillary exostosis. An incisional biopsy was performed to remove a fragment of the lesion, which was submitted for histopathological analysis.

What is the most likely diagnosis?

Options:
A. Peripheral odontoma
B. OP includes other tumors of odontogenic origin, exostoses, and osteomas, with the latter being considered our first
C. Maxillary exostosis was first considered as the lesion presented as a hard, calcified outgrowth on the alveolar ridge
D. Osteoma was included in the differential because of the presence of a well
E. Other odontogenic tumors were considered given that calcified masses in the jaw may originate from odontogenic
F. Histopathological examination confirmed a tooth
G. None
H. None


## Backbone e7

- S2 n=43 gold_rank=1
  - clusters: gold=1 near=2 other=40
- S3 shortlist (5):
  - [gold] Odontoma
  - [other] Maxillary exostosis
  - [other] Osteoma
  - [other] Cemento-ossifying fibroma
  - [other] Focal cemento-osseous dysplasia
    - why_kept(Odontoma): Matches the description of a hard, mineralized structure and is a common cause of asymptomatic calcified masses on the maxilla
    - why_kept(Maxillary exostosis): Initial diagnostic hypothesis and consistent with the location and description of the mass
    - why_kept(Osteoma): Possible cause of a discrete radiopaque lesion and can present as a hard, mineralized structure
    - why_kept(Cemento-ossifying fibroma): Can present as a calcified mass and is a type of benign fibro-osseous lesion
    - why_kept(Focal cemento-osseous dysplasia): Can cause asymptomatic calcified masses on the maxilla and is consistent with the radiographic findings
- S4 champion: **Maxillary exostosis** cluster=other jaccard=0.00
- S4 rationale: The presence of a hard, mineralized structure and a discrete radiopaque lesion on the periapical radiograph, along with the location on the right anterior maxilla, supports the diagnosis of maxillary exostosis, which is a benign bony growth.
- S4 rejected:
  - [gold] Odontoma: Odontoma is typically associated with impacted teeth and would not usually present as a solitary, asymptomatic mass on the maxilla.
  - [other] Osteoma: While osteoma could present as a hard, mineralized structure, it is less common in the maxilla and the description does not specifically suggest osteoma over maxillary exostosis.
  - [other] Cemento-ossifying fibroma: Cemento-ossifying fibroma tends to be larger and more aggressive than the described lesion, and often has a softer, more fibrous component.
  - [other] Focal cemento-osseous dysplasia: Focal cemento-osseous dysplasia typically occurs in the posterior mandible, not the anterior maxilla, making it less likely given the location of the lesion.

## B06 (code=`b06_judge_miss` locus=`supervisor_hit_judge_miss`)
- supervisor: ['Maxillary Exostosis', 'Odontoma']
  clusters: {'gold': 1, 'near': 0, 'other': 1, 'empty': 0}
- discussion labels (n=15): ['Maxillary Exostosis', 'Odontoma', 'Osteoma', 'Torus Palatinus', 'Compound Odontoma', 'Maxillary Exostosis', 'Odontoma', 'Osteoma']
- votes=3 turns=3

## B07 (code=`b07_draft_miss` locus=`draft_miss`)
- draft: ['Maxillary Exostosis', 'Dens Evaginatus']
- diagnose: ['Maxillary Exostosis', 'Dens Evaginatus']
- queries: ['maxillary exostosis symptoms', 'maxillary exostosis diagnosis', 'calcified mass on maxilla', 'mucosal fenestration with mineralized structure']

## B01 (code=`b01_rag_miss` locus=`rag_miss`)
- top2: ['Maxillary exostosis', 'Odontogenic keratocyst']
- queries: ['calcified mass on maxilla', 'mucosal fenestration with mineralized structure', 'radiopaque lesion in maxillary bone', 'differential diagnosis for maxillary exostosis']
- n_chunks=12

## APHHM
_na_

