# MCR / mcr_200b / case 374

- **gold**: cryptogenic organizing pneumonia
- **layer**: `e7_win_recall`
- **correct**: e7=1 v0=1 B06=0 B07=0 B01=0 APHHM=
- **loci**: e7=`ok` B06=`agents_hit_supervisor_drop` B07=`draft_miss` B01=`rag_miss` APHHM=`na`
- **primary_locus**: e7=ok; B06=agents_hit_supervisor_drop; B07=draft_miss
- **covariates**: vig_words=190; gold_words=3; eponym=False; subtype=False; e7_s2_rank=15; mapper_rescue=False
- **causal**: layer=e7_win_recall; primary loci above.

## Vignette (trunc)
A 56-year-old woman with no significant medical history presented with a 4-week history of dry cough and mild weight loss. She denied fever, haemoptysis, night sweats, and had no known contacts with tuberculosis. Two courses of antibiotics produced no improvement. On examination, coarse crepitations were heard over the right upper and lower lung zones. A chest radiograph showed an air-space opacity in the right upper lobe. CT of the thorax demonstrated multifocal consolidations in the right uppe...

## Backbone e7
- S1 key_facts: 56-year-old woman; no significant medical history; denies fever, haemoptysis, night sweats; no known contacts with tuberculosis; two courses of antibiotics produced no improvement; Mantoux tuberculin skin test showed 10 mm of induration; sputum induction for acid-fast bacilli was negative; bronchoalveolar lavage was negative for Xpert Mycobacterium tuberculosis/rifampi
- S2 mode=complement k=3 pool_n=53 gold_in_s2=True
  - call1: ['pulmonary tuberculosis', 'cryptococcosis', 'histoplasmosis', 'blastomycosis', 'coccidioidomycosis', 'aspergillosis', '
  - call2: ['Erdheim-Chester disease', 'Langerhans cell histiocytosis', 'pulmonary alveolar microlithiasis', 'pulmonary amyloidosis
  - call3: ['Eosinophilic pneumonia', 'Hypersensitivity pneumonitis', 'Pulmonary vasculitis', 'Goodpasture syndrome', 'Anti-glomeru
- S3 shortlist n=5 gold=True: sarcoidosis, lymphangitic carcinomatosis, bronchoalveolar cell carcinoma, organizing pneumonia, Wegener's granulomatosis
- S4 champion: **organizing pneumonia** gold=True
- S4 raw (trunc): {"champion": "organizing pneumonia", "rationale": "The patient's symptoms of dry cough and mild weight loss, lack of response to antibiotics, and radiographic findings of multifocal consolidations are consistent with organizing pneumonia. The negative tests for tuberculosis and o

## Backbone v0 (compact)
- S1 key_facts: 56-year-old woman; no significant medical history; denies fever, haemoptysis, night sweats; no known contacts with tuberculosis; two courses of antibiotics produced no improvement; coarse crepitations heard over the right upper and lower lung zones; chest radiograph showed an air-space opacity in the right upper lobe; CT of the thorax demonstrated multifocal consolidations in the right upper lobe 
- S2 mode=single k=1 pool_n=19 gold_in_s2=True
  - call1: ['Pulmonary tuberculosis', 'Pneumocystis jirovecii pneumonia', 'Invasive aspergillosis', 'Cryptococcal pneumonia', 'Hist
- S3 shortlist n=5 gold=True: Sarcoidosis, Lymphangitic carcinomatosis, Bronchoalveolar cell carcinoma, Organizing pneumonia, Hypersensitivity pneumonitis
- S4 champion: **Organizing pneumonia** gold=True
- S4 raw (trunc): {"champion": "Organizing pneumonia", "rationale": "The patient's symptoms of dry cough and mild weight loss, lack of response to antibiotics, and radiographic findings of multifocal consolidations are consistent with organizing pneumonia. The negative tests for tuberculosis and o

## Baseline B06
- discussion_turns=3
  - turn0 gold_mention=True diag=
    Given the persistence of symptoms despite empirical anti-tuberculosis therapy and negative tests for tuberculosis, other diagnoses such as lung cancer, sarcoido
  - turn1 gold_mention=True diag=
    The patient's lack of response to empirical anti-tuberculosis therapy and negative diagnostic tests for tuberculosis, combined with the persistence of symptoms 
  - turn2 gold_mention=True diag=
    Given the clinical presentation and lack of response to empirical anti-tuberculosis therapy, along with negative diagnostic tests for tuberculosis, the differen
- supervisor votes=3 top2=['Lung Cancer', 'Sarcoidosis'] gold=False

## Baseline B07
- draft=['Lung Cancer', 'Sarcoidosis'] gold=False
- has_refine=True refine=[] gold=None
- queries(3): ['differential diagnosis for persistent dry cough and weight loss', 'causes of multifocal consolidations on CT thorax', 'alternative diagnoses to pulmonary tuberculosis']
- diagnose=['Lung Cancer', 'Sarcoidosis'] gold=False

## Baseline B01
- queries=['persistent dry cough and weight loss with negative tuberculosis tests', 'multifocal consolidations on CT thorax with negative acid-fast bacilli and cultures', 'differential diagnosis for persistent cough and lung opacities after negative tuberculosis workup', 'causes of air-space opacity in lung with negative infectious disease workup']
- n_chunks=12 rag_gold_mention=False
- chunk_sample: 
- top2=['Sarcoidosis', 'Lipoid Pneumonia'] gold=False

