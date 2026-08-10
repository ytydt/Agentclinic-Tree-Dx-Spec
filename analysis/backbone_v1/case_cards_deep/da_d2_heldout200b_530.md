# DA / d2_heldout200b / case 530

- **gold**: Calcinosis cutis in Sjögren syndrome
- **layer**: `e7_win_recall`
- **correct**: e7=1 v0=0 B06=0 B07=0 B01= APHHM=
- **loci**: e7=`s3_hit_s4_miss` B06=`agents_hit_supervisor_drop` B07=`draft_miss` B01=`na` APHHM=`na`
- **primary_locus**: e7=s3_hit_s4_miss; B06=agents_hit_supervisor_drop; B07=draft_miss
- **covariates**: vig_words=265; gold_words=5; eponym=False; subtype=False; e7_s2_rank=2; mapper_rescue=True
- **causal**: DA mapper_rescue: e7 S4 未命中金标但 option@1 仍对——不可记入口/终裁优势。

## Vignette (trunc)
A 56-year-old woman with a history of hypothyroidism and hyperlipidemia presented for follow-up. Medical history includes 20-year history of oral and ocular sicca symptoms, asymptomatic elevation of creatinine kinase levels with negative myositis and muscular dystrophy panel, negative muscle biopsy results, and chronic stable autoimmune thrombocytopenia. Previous medications included methotrexate and low-dose steroids. Currently on hydroxychloroquine 200 mg daily. Does not take calcium or vitami...

## Options
  - A: Calcinosis cutis in Sjögren syndrome
  - B: Scleroderma-Sjögren’s overlap syndrome
  - C: Primary Sjögren’s syndrome
  - D: Rheumatoid arthritis with secondary Sjögren’s syndrome

## Backbone e7
- S1 key_facts: 56-year-old woman; History of hypothyroidism and hyperlipidemia; 20-year history of oral and ocular sicca symptoms; Asymptomatic elevation of creatinine kinase levels; Negative myositis and muscular dystrophy panel; Negative muscle biopsy results; Chronic stable autoimmune thrombocytopenia; Previous medications included methotrexate and low-dose steroids
- S2 mode=complement k=3 pool_n=52 gold_in_s2=True
  - call1: ['Limited systemic scleroderma', 'Calcinosis cutis', "Sjögren's syndrome", 'Mixed connective tissue disease', 'Systemic 
  - call2: ['Eosinophilic fasciitis', 'Nephrogenic systemic fibrosis', 'Pseudoxanthoma elasticum', 'Relapsing polychondritis', 'Ehl
  - call3: ['Eosinophilia-myalgia syndrome', 'Stiff person syndrome', 'Multicentric reticulohistiocytosis', 'Erythromelalgia', 'Rel
- S3 shortlist n=5 gold=True: Limited systemic scleroderma, Sjögren's syndrome, Mixed connective tissue disease, Calcinosis cutis, CREST syndrome
- S4 champion: **CREST syndrome** gold=False
- S4 raw (trunc): {"champion": "CREST syndrome", "rationale": "The patient's symptoms, including Raynaud phenomenon, calcinosis, and esophageal reflux are not mentioned but the presence of Raynaud phenomenon and calcinosis are key features of CREST syndrome. The patient also has a positive antinuc

## Backbone v0 (compact)
- S1 key_facts: 56-year-old woman; History of hypothyroidism and hyperlipidemia; 20-year history of oral and ocular sicca symptoms; Asymptomatic elevation of creatinine kinase levels; Negative myositis and muscular dystrophy panel; Negative muscle biopsy results; Chronic stable autoimmune thrombocytopenia; Previous medications included methotrexate and low-dose steroids
- S2 mode=single k=1 pool_n=19 gold_in_s2=True
  - call1: ['Limited systemic scleroderma', 'Calcinosis cutis', "Sjögren's syndrome", 'Mixed connective tissue disease', 'Undiffere
- S3 shortlist n=5 gold=True: Limited systemic scleroderma, Sjögren's syndrome, Mixed connective tissue disease, CREST syndrome, Calcinosis cutis
- S4 champion: **CREST syndrome** gold=False
- S4 raw (trunc): {"champion": "CREST syndrome", "rationale": "The patient's symptoms, including Raynaud phenomenon, calcinosis, and esophageal reflux are not mentioned but the presence of Raynaud phenomenon and calcinosis are key features of CREST syndrome. The patient also has a positive antinuc

## Baseline B06
- discussion_turns=3
  - turn0 gold_mention=True diag=
    The patient's presentation of sicca symptoms, Raynaud phenomenon, and positive antinuclear antibody with a nucleolar pattern, along with the presence of calcino
  - turn1 gold_mention=True diag=
    The patient's clinical presentation, laboratory results, and imaging studies are consistent with the previous discussion, supporting Limited Systemic Sclerosis 
  - turn2 gold_mention=True diag=
    The patient's presentation of sicca symptoms, Raynaud phenomenon, and positive antinuclear antibody with a nucleolar pattern, along with the presence of calcino
- supervisor votes=3 top2=['Limited Systemic Sclerosis', "Sjögren's Syndrome"] gold=False

## Baseline B07
- draft=['Limited Systemic Scleroderma (CREST Syndrome)', "Sjögren's Syndrome"] gold=False
- has_refine=True refine=[] gold=None
- queries(4): ['limited systemic scleroderma', 'calcinosis cutis', 'CREST syndrome', 'autoimmune disease with sicca symptoms and calcinosis']
- diagnose=['Limited Systemic Scleroderma (CREST Syndrome)', "Sjögren's Syndrome"] gold=False

