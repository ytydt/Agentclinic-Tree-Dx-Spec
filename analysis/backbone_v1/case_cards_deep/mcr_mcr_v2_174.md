# MCR / mcr_v2 / case 174

- **gold**: autoimmune gastritis
- **layer**: `base_win_rank`
- **correct**: e7=0 v0=0 B06=1 B07=1 B01=1 APHHM=
- **loci**: e7=`s3_hit_s4_miss` B06=`supervisor_ok` B07=`diagnose_ok` B01=`gen_ok` APHHM=`na`
- **primary_locus**: e7=s3_hit_s4_miss; B06=supervisor_ok
- **covariates**: vig_words=227; gold_words=2; eponym=False; subtype=False; e7_s2_rank=1; mapper_rescue=False
- **causal**: 骨干 S3 含金标，S4 终裁选错。

## Vignette (trunc)
A 37-year-old woman with systemic lupus erythematosus and Sjögren’s syndrome was diagnosed with autoimmune hepatitis and scheduled for upper gastrointestinal endoscopy before starting prednisolone. She had never received acid-secretion inhibitors, including proton pump inhibitors or vonoprazan. Vital signs and physical examination were unremarkable.   Endoscopic findings: - Antrum: normal appearance. - Gastric corpus: normal coloration with a regular arrangement of collecting venules; red streak...

## Backbone e7
- S1 key_facts: Patient has systemic lupus erythematosus and Sjögren’s syndrome; Scheduled for upper gastrointestinal endoscopy before starting prednisolone; Never received acid-secretion inhibitors; Vital signs and physical examination were unremarkable; Antrum had normal appearance; Gastric corpus had normal coloration with a regular arrangement of collecting ve; Magnified narrow-band imaging of the corpus showed regular round pit patterns; Biopsy sites included greater curvature of the prepyloric area and lesser and gr
- S2 mode=complement k=3 pool_n=51 gold_in_s2=True
  - call1: ['Autoimmune gastritis', 'Chronic atrophic gastritis', 'Multifocal atrophic gastritis', 'Gastric mucosal atrophy', 'Pern
  - call2: ['Gastric amyloidosis', 'Gastric granuloma', 'Eosinophilic gastroenteritis', 'Gastric mastocytosis', 'Whipple disease', 
  - call3: ['Mixed autoimmune hemolytic anemia and gastritis', 'Gastric plasmacytosis', 'Chronic varioliform gastritis', 'Gastric n
- S3 shortlist n=5 gold=True: Autoimmune gastritis, Chronic atrophic gastritis, Gastric involvement in systemic lupus erythematosus, Gastric involvement in Sjögren’s syndrome, Atrophic corpus gastritis
- S4 champion: **Gastric involvement in Sjögren’s syndrome** gold=False
- S4 raw (trunc): {"champion": "Gastric involvement in Sjögren’s syndrome", "rationale": "The patient has Sjögren’s syndrome and the histologic findings show foveolar hyperplasia and mild degeneration of parietal cells, which is consistent with gastric involvement in Sjögren’s syndrome. The negati

## Backbone v0 (compact)
- S1 key_facts: Patient has systemic lupus erythematosus and Sjögren’s syndrome; Scheduled for upper gastrointestinal endoscopy before starting prednisolone; Never received acid-secretion inhibitors; Vital signs and physical examination were unremarkable; Endoscopy showed normal antrum and gastric corpus with red streaks on the lesser; Magnified narrow-band imaging showed regular round pit patterns; Biopsy sites included greater curvature of the prepyloric area and lesser and gr; Histologic findings showed foveolar hyperplasia, mild degeneration of parietal c
- S2 mode=single k=1 pool_n=18 gold_in_s2=True
  - call1: ['Autoimmune gastritis', 'Chronic atrophic gastritis', 'Multifocal atrophic gastritis', 'Gastric mucosal atrophy', 'Pern
- S3 shortlist n=5 gold=True: Autoimmune gastritis, Sjögren's syndrome-associated gastritis, Systemic lupus erythematosus-associated gastritis, Chronic atrophic gastritis, Atrophic corpus gastritis
- S4 champion: **Chronic atrophic gastritis** gold=False
- S4 raw (trunc): {"champion": "Chronic atrophic gastritis", "rationale": "The patient's histologic findings, including foveolar hyperplasia, mild degeneration of parietal cells, and mild lymphocytic infiltration, along with heterogeneously reduced H+/K+-ATPase staining and uneven pepsinogen I sta

## Baseline B06
- discussion_turns=3
  - turn0 gold_mention=True diag=
    The patient's histologic findings and laboratory tests suggest autoimmune gastritis, but the presence of systemic lupus erythematosus and Sjögren’s syndrome com
  - turn1 gold_mention=True diag=
    The patient's histologic findings, including foveolar hyperplasia and mild lymphocytic infiltration, along with the heterogeneous reduction of H+/K+-ATPase stai
  - turn2 gold_mention=True diag=
    Engaging with prior opinions, the patient's histologic findings and laboratory tests, including heterogeneous reduction of H+/K+-ATPase staining and uneven peps
- supervisor votes=3 top2=['Autoimmune gastritis', 'Atrophic gastritis'] gold=True

## Baseline B07
- draft=['Autoimmune Gastritis', 'Chronic Erosive Gastritis'] gold=True
- has_refine=True refine=[] gold=None
- queries(3): ['autoimmune gastritis diagnosis', 'Sjögren’s syndrome and gastric findings', 'autoimmune hepatitis and gastrointestinal manifestations']
- diagnose=['Autoimmune Gastritis', 'Chronic Erosive Gastritis'] gold=True

## Baseline B01
- queries=['autoimmune gastritis vs chronic gastritis', 'foveolar hyperplasia and parietal cell degeneration causes', 'H+/K+-ATPase staining reduction in gastric mucosa', 'gastric corpus histology in autoimmune disorders']
- n_chunks=12 rag_gold_mention=False
- chunk_sample: 
- top2=['Autoimmune gastritis', 'Chronic gastritis'] gold=True

