# MCR / mcr_v1 / case 69

- **gold**: Gastric lipoma
- **layer**: `base_win_rank`
- **correct**: e7=0 v0=0 B06=0 B07=1 B01=0 APHHM=0
- **loci**: e7=`s3_hit_s4_miss` B06=`supervisor_hit_judge_miss` B07=`diagnose_ok` B01=`gen_hit_judge_miss` APHHM=`tree_miss`
- **primary_locus**: e7=s3_hit_s4_miss; B07=diagnose_ok
- **covariates**: vig_words=176; gold_words=2; eponym=False; subtype=False; e7_s2_rank=5; mapper_rescue=False
- **causal**: 骨干 S3 含金标，S4 终裁选错。

## Vignette (trunc)
A 39-year-old man presented with a one-week history of epigastric pain and hematemesis. He had no significant medical or surgical history, took no medications, and had no allergies. He was a smoker and did not drink alcohol. On examination, vital signs were stable, the abdomen was soft without tenderness, and a rectal examination revealed no melena. Laboratory studies showed a hemoglobin level of 6.3 g/dL; after transfusion, it rose to 10 g/dL. Upper gastrointestinal endoscopy revealed a submuco...

## Backbone e7
- S1 key_facts: 39-year-old man; One-week history of epigastric pain and hematemesis; No significant medical or surgical history; No medications; No allergies; Smoker; Does not drink alcohol; Stable vital signs
- S2 mode=complement k=3 pool_n=33 gold_in_s2=True
  - call1: ['Gastric adenocarcinoma', 'Gastrointestinal stromal tumor', 'Leiomyoma', 'Leiomyosarcoma', 'Lipoma', 'Hamartoma', 'Infl
  - call2: ['Gastric schwannoma', 'Gastrointestinal autonomic nerve tumor', 'Glomus tumor of the stomach', 'Inflammatory myofibrobl
  - call3: ['Gastric glomus tumor', 'Gastric paraganglioma', 'Sclerosing mesenteritis', 'Eosinophilic gastroenteritis', 'Gastric xa
- S3 shortlist n=5 gold=True: Gastrointestinal stromal tumor, Peptic ulcer disease, Gastric adenocarcinoma, Dieulafoy's lesion, Lipoma
- S4 champion: **Gastrointestinal stromal tumor** gold=False
- S4 raw (trunc): {"champion": "Gastrointestinal stromal tumor", "rationale": "The presence of a submucosal lesion in the gastric antrum with ulceration of the overlying mucosa and a well-defined, heterogeneous, pre-pyloric mass with fat attenuation on CT is most consistent with a gastrointestinal

## Backbone v0 (compact)
- S1 key_facts: 39-year-old man; One-week history of epigastric pain and hematemesis; No significant medical or surgical history; No medications; No allergies; Smoker; Does not drink alcohol; Stable vital signs
- S2 mode=None k=None pool_n=16 gold_in_s2=True
  - pool gold matches: ['Lipoma']
  - pool head: Gastric adenocarcinoma, Gastrointestinal stromal tumor (GIST), Leiomyoma, Leiomyosarcoma, Gastric lymphoma, Peptic ulcer disease, Dieulafoy's lesion, Gastric carcinoid tumor
- S3 shortlist n=5 gold=False: Gastrointestinal stromal tumor (GIST), Peptic ulcer disease, Gastric adenocarcinoma, Dieulafoy's lesion, Leiomyoma
- S4 champion: **Gastrointestinal stromal tumor (GIST)** gold=False
- S4 raw (trunc): {"champion": "Gastrointestinal stromal tumor (GIST)", "rationale": "The presence of a submucosal lesion in the gastric antrum with ulceration of the overlying mucosa and a well-defined, heterogeneous, pre-pyloric mass with fat attenuation on CT is most consistent with a GIST, esp

## Baseline B06
- discussion_turns=3
  - turn0 gold_mention=True diag=
    The patient's presentation with epigastric pain and hematemesis, along with the findings of a submucosal lesion in the gastric antrum and a well-defined, hetero
  - turn1 gold_mention=True diag=
    The patient's presentation and imaging findings are consistent with a gastric submucosal lesion, and the presence of fat attenuation on CT suggests a possible G
  - turn2 gold_mention=True diag=
    The patient's presentation with epigastric pain, hematemesis, and imaging findings of a submucosal lesion with ulceration and a well-defined, heterogeneous, pre
- supervisor votes=3 top2=['Gastric gastrointestinal stromal tumor (GIST)', 'Gastric lipoma'] gold=True

## Baseline B07
- draft=['Gastrointestinal Stromal Tumor (GIST)', 'Gastric Lipoma'] gold=True
- has_refine=True refine=[] gold=None
- queries(3): ['gastric submucosal lesions with ulceration', 'pre-pyloric mass with fat attenuation', 'differential diagnosis for epigastric pain and hematemesis']
- diagnose=['Gastrointestinal Stromal Tumor (GIST)', 'Gastric Lipoma'] gold=True

## Baseline B01
- queries=['gastric submucosal lesions with ulceration', 'pre-pyloric masses with fat attenuation on CT', 'differential diagnosis of upper GI bleeding with stable vital signs', 'benign gastric tumors with hemorrhage']
- n_chunks=12 rag_gold_mention=False
- chunk_sample: 
- top2=['Gastrointestinal Stromal Tumor (GIST)', 'Gastric Lipoma'] gold=True

## APHHM
- tree_n=24 tree_recall=False
- gold_leaf=None
- final_n=2 final_recall=False ranking=['Gastrointestinal Stromal Tumor (GIST)', 'Gastric Duplication Cyst']
- human_at1=False fail_mode=tree_miss

