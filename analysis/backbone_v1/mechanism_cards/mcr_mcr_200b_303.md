# MCR / mcr_200b / case 303

- **gold**: GastricSchwannoma
- **layer**: `all_miss_but_recalled` · **layer_aphhm**: ``
- **correct**: e7=0 v0=0 B06=0 B07=0 B01=0 APHHM=
- **e7_locus**: `s2_hit_s3_drop` · **e7_fail_code**: `s3_why_ignored_gold`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=0 e7_champ_cluster=other B06_sup_gold=0 B07_diag_gold=0 same_cluster_flip=0 true_entrance=0
- **APHHM**: locus=`na` code=`na` prune_e7_ok=0

## Vignette
A 64-year-old woman with a 20-year history of hypertension presented with dizziness and head discomfort of 3 days’ duration. Her blood pressure at presentation was 190/100 mmHg. She had no gastrointestinal symptoms (no abdominal pain, melena, hematemesis, or dysphagia).

An abdominal ultrasound was performed to evaluate her hypertension and incidentally revealed a 4.7 cm × 4.4 cm hypoechoic lesion with a clear, regular boundary located between the upper pole of the spleen and the abdominal aorta, without detectable blood flow. The radiologist noted that the lesion appeared to originate from the stomach and suggested a gastrointestinal stromal tumor (GIST).

After blood-pressure control, she was admitted for further evaluation. Vital signs were within normal limits. Physical examination was unremarkable, and routine blood tests, blood biochemistry, fecal occult blood, and tumor markers were all normal.

Contrast-enhanced abdominal CT showed a 5.5 cm × 4.3 cm smoothly marginated soft-tissue mass in the gastric wall protruding beyond the serosal contour, with marked enhancement and surrounding lymph-node enlargement (nodes up to 1.0 cm). Malignancy, including GIST with nodal metastase…

## Backbone e7

- S2 n=43 gold_rank=5
  - clusters: gold=1 near=0 other=42
- S3 shortlist (5):
  - [other] Gastrointestinal stromal tumor
  - [other] Leiomyoma
  - [other] Leiomyosarcoma
  - [other] Gastric adenocarcinoma
  - [other] Gastric carcinoid tumor
    - why_kept(Gastrointestinal stromal tumor): Incidentally revealed hypoechoic lesion with clear boundary, suggested by radiologist to originate from the stomach, and contrast-enhanced abdominal CT showed smoothly marginated soft-tissue mass with marked enhancement
    - why_kept(Leiomyoma): Upper endoscopy revealed smooth, hemispherical submucosal elevation on gastric fundus, and endoscopic ultrasonography demonstrated hypoechoic, heterogeneous mass arising from the muscularis propria
    - why_kept(Leiomyosarcoma): Similar presentation to leiomyoma, but with potential for malignancy, and EUS-guided fine-needle aspiration obtained scant gastric mucosal tissue and few spindle cells
    - why_kept(Gastric adenocarcinoma): Although no gastrointestinal symptoms, abdominal mass and lymph-node enlargement on CT raise concern for malignancy
    - why_kept(Gastric carcinoid tumor): Submucosal elevation on gastric fundus and hypoechoic mass on endoscopic ultrasonography could be consistent with a neuroendocrine tumor
- S4 champion: **Gastrointestinal stromal tumor** cluster=other jaccard=0.00
- S4 rationale: The patient's presentation with a hypoechoic, heterogeneous mass arising from the muscularis propria, as demonstrated by endoscopic ultrasonography, and the presence of spindle cells on EUS-guided fine-needle aspiration, are consistent with a gastrointestinal stromal tumor (GIST). The location and characteristics of the mass, as well as the absence of gastrointestinal symptoms, also support this diagnosis.
- S4 rejected:
  - [other] Leiomyoma: Leiomyomas are typically smaller and less likely to cause significant lymph-node enlargement.
  - [other] Leiomyosarcoma: Leiomyosarcomas are rare and usually present with more aggressive features, such as larger size, irregular margins, and higher mitotic rates, which are not described in this case.
  - [other] Gastric adenocarcinoma: Gastric adenocarcinoma typically presents with mucosal ulceration, bleeding, or other gastrointestinal symptoms, which are absent in this patient.
  - [other] Gastric carcinoid tumor: Gastric carcinoid tumors are usually smaller, more superficial, and have different histological features than the mass described in this case.

## B06 (code=`b06_agents_miss` locus=`agents_miss`)
- supervisor: ['Gastrointestinal Stromal Tumor (GIST)', 'Leiomyoma']
  clusters: {'gold': 0, 'near': 0, 'other': 2, 'empty': 0}
- discussion labels (n=15): ['Gastrointestinal Stromal Tumor (GIST)', 'Leiomyoma', 'Leiomyosarcoma', 'Schwannoma', 'Glomus Tumor', 'Gastrointestinal Stromal Tumor (GIST)', 'Leiomyoma', 'Leiomyosarcoma']
- votes=3 turns=3

## B07 (code=`b07_draft_miss` locus=`draft_miss`)
- draft: ['Gastrointestinal Stromal Tumor (GIST)', 'Plexiform Fibromyxoma']
- diagnose: ['Gastrointestinal Stromal Tumor (GIST)', 'Plexiform Fibromyxoma']
- queries: ['GIST diagnosis criteria', 'spindle cell tumor types', 'gastric wall mass differential diagnosis']

## B01 (code=`b01_rag_miss` locus=`rag_miss`)
- top2: ['Gastrointestinal Stromal Tumor (GIST)', 'Leiomyoma']
- queries: ['hypertension and abdominal mass', 'gastrointestinal stromal tumor (GIST) diagnosis', 'submucosal gastric tumors with spindle cell morphology', 'differential diagnosis of hypoechoic lesions near the stomach']
- n_chunks=12

## APHHM
_na_

