# MCR / mcr_200b / case 402

- **gold**: Primary pleuropulmonary synovial sarcoma
- **layer**: `all_miss_but_recalled`
- **correct**: e7=0 v0=0 B06=0 B07=0 B01=0 APHHM=
- **loci**: e7=`s2_hit_s3_drop` B06=`agents_miss` B07=`draft_miss` B01=`rag_miss` APHHM=`na`
- **primary_locus**: e7=s2_hit_s3_drop; recalled_but_none_correct
- **covariates**: vig_words=229; gold_words=4; eponym=False; subtype=False; e7_s2_rank=11; mapper_rescue=False
- **causal**: 骨干 S2 已召回，S3 短表丢掉金标。

## Vignette (trunc)
A 40-year-old woman, one month postpartum, with no significant past medical history, presented with three weeks of left chest pain, dry cough, and progressive dyspnea (mMRC grade III) in a context of general health deterioration. On examination, she had signs of a left pleural effusion. A posteroanterior chest radiograph showed a homogeneous opacity occupying the entire left hemithorax with mediastinal shift to the right. Serial thoracenteses produced approximately 2 L of serous fluid every thre...

## Backbone e7
- S1 key_facts: 40-year-old woman; One month postpartum; No significant past medical history; Three weeks of symptoms; Left chest pain; Dry cough; Progressive dyspnea; Signs of left pleural effusion on examination
- S2 mode=complement k=3 pool_n=49 gold_in_s2=True
  - call1: ['Non-small cell lung cancer', 'Small cell lung cancer', 'Lymphoma', 'Thymoma', 'Pancoast tumor', 'Mesothelioma', 'Pulmo
  - call2: ['Churg-Strauss syndrome', 'Erdheim-Chester disease', 'Langerhans cell histiocytosis', 'Rosai-Dorfman disease', 'Kimura 
  - call3: ['NUT carcinoma', 'Primitive neuroectodermal tumor', 'Ewing sarcoma', 'Pleomorphic adenoma of the trachea', 'Mucoepiderm
- S3 shortlist n=5 gold=False: Non-small cell lung cancer, Small cell lung cancer, Lymphoma, Pancoast tumor, Mesothelioma
- S4 champion: **Non-small cell lung cancer** gold=False
- S4 raw (trunc): {"champion": "Non-small cell lung cancer", "rationale": "The presence of a large mediastino-pulmonary mass, pleural effusion, and an endobronchial lesion in the left upper-lobe bronchus, along with the patient's progressive symptoms, are highly suggestive of a malignant process, 

## Backbone v0 (compact)
- S1 key_facts: 40-year-old woman; One month postpartum; No significant past medical history; Three weeks of symptoms; General health deterioration; Signs of left pleural effusion on examination; Homogeneous opacity occupying the entire left hemithorax with mediastinal shift ; Serial thoracenteses produced approximately 2 L of serous fluid every three days
- S2 mode=single k=1 pool_n=20 gold_in_s2=True
  - call1: ['Non-small cell lung cancer', 'Small cell lung cancer', 'Lymphoma', 'Thymoma', 'Pancoast tumor', 'Mesothelioma', 'Sarco
- S3 shortlist n=5 gold=False: Non-small cell lung cancer, Small cell lung cancer, Lymphoma, Pancoast tumor, Mesothelioma
- S4 champion: **Non-small cell lung cancer** gold=False
- S4 raw (trunc): {"champion": "Non-small cell lung cancer", "rationale": "The presence of a large mediastino-pulmonary mass with an endobronchial lesion and significant pleural effusion, as seen on imaging and bronchoscopic examination, is most consistent with a diagnosis of non-small cell lung c

## Baseline B06
- discussion_turns=3
  - turn0 gold_mention=False diag=
    Given the patient's presentation with a large pleural effusion, mediastino-pulmonary mass, and endobronchial lesion, a malignant process is highly suspected, wi
  - turn1 gold_mention=False diag=
    The patient's presentation with a large pleural effusion, mediastino-pulmonary mass, and endobronchial lesion, along with the non-diagnostic biopsies, suggests 
  - turn2 gold_mention=False diag=
    The patient's presentation with a large pleural effusion, mediastino-pulmonary mass, and endobronchial lesion, along with the non-diagnostic biopsies, aligns wi
- supervisor votes=3 top2=['Lung Cancer', 'Malignant Pleural Effusion'] gold=False

## Baseline B07
- draft=['Malignant Pleural Effusion', 'Lymphoma'] gold=False
- has_refine=True refine=[] gold=None
- queries(3): ['postpartum pleural effusion causes', 'mediastino-pulmonary mass diagnosis', 'differential diagnosis for endobronchial lesions']
- diagnose=['Malignant Pleural Effusion', 'Lymphoma'] gold=False

## Baseline B01
- queries=['postpartum pleural effusion causes', 'mediastino-pulmonary mass with pleural effusion', 'differential diagnosis of large pleural effusion with mediastinal shift', 'causes of progressive dyspnea with chest pain and dry cough in postpartum women']
- n_chunks=12 rag_gold_mention=False
- chunk_sample: 
- top2=['Malignant pleural effusion', 'Lung cancer'] gold=False

