# DA / d2_seq100 / case 5

- **gold**: Left maxillary giant cell reparative granuloma (GCRG)
- **layer**: `aphhm_lose` · **layer_aphhm**: `aphhm_lose`
- **correct**: e7=1 v0=1 B06=1 B07=1 B01=0 APHHM=0
- **e7_locus**: `s2_hit_s3_drop` · **e7_fail_code**: `s2_gold_low_rank`
- **mapper_rescue**: 1
- **alignment**: e7_s3_gold=0 e7_champ_cluster=near B06_sup_gold=0 B07_diag_gold=0 same_cluster_flip=0 true_entrance=0
- **APHHM**: locus=`tree_miss` code=`aphhm_tree_miss` prune_e7_ok=0

## Vignette
A teenage girl presented with several months of sinus pressure and facial swelling, and several weeks of external deviation of her nasal septum. No significant past medical history was mentioned.

On examination, a left nasal mass was noted. Mild left-sided proptosis was present.

- Imaging Studies:    CT scan (without and with contrast):    - Image Title: Computed tomographic scans of a heterogeneous mass in the left maxillary sinus    - Image Description: Shows a heterogeneous mass with solid and cystic components completely opacifying the left maxillary sinus. Mass eroded the orbital floor, medial and posterior maxillary walls, and anterior ethmoid air cells. No extension beyond cribriform plate. Displacement of inferior rectus without muscle invasion. Left maxillary alveolar ridge and several molar roots involved. Bony changes showed remodeling and thinning.    - Biopsy Results:    - Tissue analysis showed spindle cell process in a patternless arrangement with significant multinucleated giant cells    - Rare mitotic activity    - No cytologic atypia    - Largest portion measured 7.0 × 4.0 × 2.0 cm

What is the most likely diagnosis?

Options:
A. Ossifying Fibroma
B. Giant cell …

## Options
- A: Ossifying Fibroma
- B: Giant cell tumor of bone
- C: Central Giant Cell Granuloma
- D: Left maxillary giant cell reparative granuloma (GCRG) **←gold**

## Backbone e7

- S2 n=48 gold_rank=35
  - clusters: gold=1 near=1 other=46
- S3 shortlist (5):
  - [near] Giant cell tumor
  - [other] Juvenile nasopharyngeal angiofibroma
  - [other] Esthesioneuroblastoma
  - [other] Sinonasal undifferentiated carcinoma
  - [other] Fibrous dysplasia
    - why_kept(Giant cell tumor): Biopsy showed spindle cell process with significant multinucleated giant cells, consistent with giant cell tumor
    - why_kept(Juvenile nasopharyngeal angiofibroma): Clinical presentation of nasal mass and proptosis, with imaging showing a heterogeneous mass in the maxillary sinus
    - why_kept(Esthesioneuroblastoma): Nasal mass and proptosis, with biopsy showing spindle cell process, although less typical for esthesioneuroblastoma
    - why_kept(Sinonasal undifferentiated carcinoma): Aggressive clinical presentation and imaging findings, although biopsy results do not show cytologic atypia
    - why_kept(Fibrous dysplasia): Bony changes showing remodeling and thinning, consistent with fibrous dysplasia, although less likely given the aggressive clinical presentation
- S4 champion: **Giant cell tumor** cluster=near jaccard=0.25
- S4 rationale: The biopsy results showing a spindle cell process with significant multinucleated giant cells, rare mitotic activity, and no cytologic atypia are consistent with a giant cell tumor. The clinical presentation and imaging findings of a heterogeneous mass in the left maxillary sinus with erosion of surrounding structures also support this diagnosis.
- S4 rejected:
  - [other] Juvenile nasopharyngeal angiofibroma: Typically occurs in adolescent males and is highly vascular, which is not mentioned in the case
  - [other] Esthesioneuroblastoma: Usually presents with a mass in the nasal cavity and has a distinct neuroblastic morphology on biopsy, which is not described in the case
  - [other] Sinonasal undifferentiated carcinoma: Typically presents with more aggressive features and cytologic atypia, which is not present in the biopsy results
  - [other] Fibrous dysplasia: Typically presents with ground-glass appearance on imaging and does not usually have a soft tissue mass or multinucleated giant cells on biopsy

## B06 (code=`b06_mapper_rescue` locus=`supervisor_miss_but_scored_ok`)
- supervisor: ['Giant Cell Tumor', 'Juvenile Nasopharyngeal Angiofibroma']
  clusters: {'gold': 0, 'near': 1, 'other': 1, 'empty': 0}
- discussion labels (n=15): ['Juvenile Nasopharyngeal Angiofibroma', 'Giant Cell Tumor', 'Fibrous Dysplasia', 'Ossifying Fibroma', 'Sinus Mucocele', 'Giant Cell Tumor', 'Juvenile Nasopharyngeal Angiofibroma', 'Fibrous Dysplasia']
- votes=3 turns=3

## B07 (code=`b07_mapper_rescue` locus=`diagnose_miss_but_scored_ok`)
- draft: ['Giant Cell Tumor', 'Fibrous Dysplasia']
- diagnose: ['Giant Cell Tumor', 'Fibrous Dysplasia']
- queries: ['sinus mass with spindle cell process and multinucleated giant cells', 'maxillary sinus tumor with erosion of orbital floor and displacement of inferior rectus', 'differential diagnosis of heterogeneous mass in maxillary sinus']

## B01 (code=`b01_rag_miss` locus=`rag_miss`)
- top2: ['Juvenile Nasopharyngeal Angiofibroma', 'Antrochoanal Polyp']
- queries: ['sinus mass with spindle cell process and multinucleated giant cells', 'maxillary sinus tumor with orbital floor erosion and proptosis', 'nasal septum deviation with heterogeneous mass in maxillary sinus', 'spindle cell neoplasm of the head and neck in adolescents']
- n_chunks=12

## APHHM
- tree_n=27 final_n=3
- final: ['Juvenile Nasopharyngeal Angiofibroma', "Ewing's Sarcoma of the Sinonasal Tract", 'Rhabdomyosarcoma']
- tree gold_cluster_n=0 final gold=False

