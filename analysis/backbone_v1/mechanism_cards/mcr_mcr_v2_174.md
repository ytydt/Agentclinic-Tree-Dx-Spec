# MCR / mcr_v2 / case 174

- **gold**: autoimmune gastritis
- **layer**: `base_win_rank` · **layer_aphhm**: ``
- **correct**: e7=0 v0=0 B06=1 B07=1 B01=1 APHHM=
- **e7_locus**: `s3_hit_s4_miss` · **e7_fail_code**: `rationale_overfit`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=1 e7_champ_cluster=other B06_sup_gold=1 B07_diag_gold=1 same_cluster_flip=1 true_entrance=0
- **APHHM**: locus=`na` code=`na` prune_e7_ok=0

## Vignette
A 37-year-old woman with systemic lupus erythematosus and Sjögren’s syndrome was diagnosed with autoimmune hepatitis and scheduled for upper gastrointestinal endoscopy before starting prednisolone. She had never received acid-secretion inhibitors, including proton pump inhibitors or vonoprazan. Vital signs and physical examination were unremarkable. 

Endoscopic findings:
- Antrum: normal appearance.
- Gastric corpus: normal coloration with a regular arrangement of collecting venules; red streaks and slight mucosal swelling on the lesser curvature of the angle.
- Magnified narrow-band imaging of the corpus: regular round pit patterns.

Biopsy sites: greater curvature of the prepyloric area and lesser and greater curvatures of the gastric corpus.

Histologic findings (lesser curvature of corpus):
- Three defined layers: first (foveolar epithelium) showed foveolar hyperplasia; second (parietal cells) was shortened with mild degeneration; third (chief cells) preserved.
- Layer contours slightly disorganized with mild lymphocytic infiltration.
- H+/K+-ATPase staining: heterogeneously reduced.
- Pepsinogen I: uneven staining.
- MUC6: positive throughout the region.
- Chromogranin A: sli…

## Backbone e7

- S2 n=51 gold_rank=1
  - clusters: gold=1 near=9 other=41
- S3 shortlist (5):
  - [gold] Autoimmune gastritis
  - [near] Chronic atrophic gastritis
  - [other] Gastric involvement in systemic lupus erythematosus
  - [other] Gastric involvement in Sjögren’s syndrome
  - [near] Atrophic corpus gastritis
    - why_kept(Autoimmune gastritis): Patient has autoimmune disorders and histologic findings show foveolar hyperplasia and mild degeneration of parietal cells
    - why_kept(Chronic atrophic gastritis): Histologic findings show foveolar hyperplasia and mild degeneration of parietal cells, consistent with atrophic gastritis
    - why_kept(Gastric involvement in systemic lupus erythematosus): Patient has systemic lupus erythematosus and gastrointestinal symptoms
    - why_kept(Gastric involvement in Sjögren’s syndrome): Patient has Sjögren’s syndrome and gastrointestinal symptoms
    - why_kept(Atrophic corpus gastritis): Histologic findings show foveolar hyperplasia and mild degeneration of parietal cells, consistent with atrophic corpus gastritis
- S4 champion: **Gastric involvement in Sjögren’s syndrome** cluster=other jaccard=0.00
- S4 rationale: The patient has Sjögren’s syndrome and the histologic findings show foveolar hyperplasia and mild degeneration of parietal cells, which is consistent with gastric involvement in Sjögren’s syndrome. The negative anti-parietal cell antibody and normal vitamin B12 levels also support this diagnosis.
- S4 rejected:
  - [gold] Autoimmune gastritis: Negative anti-parietal cell antibody and normal vitamin B12 levels do not support this diagnosis
  - [near] Chronic atrophic gastritis: The biopsy findings do not show significant atrophy or metaplasia, which is typical of chronic atrophic gastritis
  - [other] Gastric involvement in systemic lupus erythematosus: There is limited evidence to suggest that systemic lupus erythematosus directly involves the stomach in this manner
  - [near] Atrophic corpus gastritis: The biopsy findings do not show significant atrophy of the gastric corpus, which is typical of atrophic corpus gastritis

## B06 (code=`b06_ok` locus=`supervisor_ok`)
- supervisor: ['Autoimmune gastritis', 'Atrophic gastritis']
  clusters: {'gold': 1, 'near': 1, 'other': 0, 'empty': 0}
- discussion labels (n=15): ['Autoimmune gastritis', 'Chronic gastritis', 'Gastropathy associated with systemic lupus erythematosus', 'Atrophic gastritis', 'H. pylori-negative gastritis', 'Autoimmune gastritis', 'Atrophic gastritis', 'Chronic gastritis']
- votes=3 turns=3

## B07 (code=`b07_ok` locus=`diagnose_ok`)
- draft: ['Autoimmune Gastritis', 'Chronic Erosive Gastritis']
- diagnose: ['Autoimmune Gastritis', 'Chronic Erosive Gastritis']
- queries: ['autoimmune gastritis diagnosis', 'Sjögren’s syndrome and gastric findings', 'autoimmune hepatitis and gastrointestinal manifestations']

## B01 (code=`b01_ok` locus=`gen_ok`)
- top2: ['Autoimmune gastritis', 'Chronic gastritis']
- queries: ['autoimmune gastritis vs chronic gastritis', 'foveolar hyperplasia and parietal cell degeneration causes', 'H+/K+-ATPase staining reduction in gastric mucosa', 'gastric corpus histology in autoimmune disorders']
- n_chunks=12

## APHHM
_na_

