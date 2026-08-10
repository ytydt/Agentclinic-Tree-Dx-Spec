# MCR / mcr_200b / case 265

- **gold**: Intestinal T-cell lymphoma not otherwise specified
- **layer**: `base_win_recall`
- **correct**: e7=0 v0=0 B06=1 B07=1 B01=0 APHHM=
- **loci**: e7=`s2_miss` B06=`supervisor_ok` B07=`diagnose_ok` B01=`gen_hit_judge_miss` APHHM=`na`
- **primary_locus**: e7=s2_miss; B06=supervisor_ok
- **covariates**: vig_words=316; gold_words=7; eponym=False; subtype=False; e7_s2_rank=None; mapper_rescue=False
- **causal**: 骨干入口完全未召回；基线直接给出金标/近义。

## Vignette (trunc)
A 55-year-old man with chronic obstructive pulmonary disease and opioid use disorder presented with worsening abdominal distention and a 60-lb unintentional weight loss over 1 year, along with increasing difficulty with bowel movements. He denied melena, nausea, vomiting, fevers, flank pain, dysphagia, or odynophagia, and had no history of abdominal surgery.  Three weeks before admission, abdominal CT with contrast showed a small-bowel obstruction with a transition point in the right-mid abdomen...

## Backbone e7
- S1 key_facts: 55-year-old man with chronic obstructive pulmonary disease and opioid use disord; Presented with worsening abdominal distention and unintentional weight loss; Increasing difficulty with bowel movements; Denied melena, nausea, vomiting, fevers, flank pain, dysphagia, or odynophagia; No history of abdominal surgery; Abdominal CT with contrast showed small-bowel obstruction; Colonoscopy revealed two polyps with non-specific chronic inflammation; Video capsule endoscopy demonstrated erythematous gastritis and multiple small-b
- S2 mode=complement k=3 pool_n=49 gold_in_s2=False
  - call1: ["Crohn's disease", 'Ulcerative colitis', 'Intestinal lymphoma', 'Gastrointestinal stromal tumor', 'Carcinoid tumor', 'S
  - call2: ['Erdheim-Chester disease', 'Langerhans cell histiocytosis', 'Mastocytosis', 'Chronic granulomatous disease', 'Common va
  - call3: ['Melanoma metastatic to small bowel', 'Kaposi sarcoma of the small intestine', 'Primary effusion lymphoma', 'Intravascu
- S3 shortlist n=5 gold=False: Crohn's disease, Intestinal lymphoma, Ulcerative colitis, Enteropathy-associated T-cell lymphoma, NSAID-induced enteropathy
- S4 champion: **Crohn's disease** gold=False
- S4 raw (trunc): {"champion": "Crohn's disease", "rationale": "The patient's presentation with worsening abdominal distention, unintentional weight loss, and increasing difficulty with bowel movements, along with findings of small-bowel obstruction, multiple jejunal strictures, and perforated ulc

## Backbone v0 (compact)
- S1 key_facts: 55-year-old man with chronic obstructive pulmonary disease and opioid use disord; Presented with worsening abdominal distention and unintentional weight loss; Increasing difficulty with bowel movements; Denied melena, nausea, vomiting, fevers, flank pain, dysphagia, or odynophagia; Abdominal CT showed small-bowel obstruction with transition point in right-mid a; Colonoscopy revealed two polyps with non-specific chronic inflammation; Video capsule endoscopy demonstrated erythematous gastritis and multiple small-b; Double-balloon enteroscopy identified multiple jejunal strictures
- S2 mode=single k=1 pool_n=19 gold_in_s2=False
  - call1: ["Crohn's disease", 'Ulcerative colitis', 'Intestinal lymphoma', 'Gastrointestinal stromal tumor', 'Carcinoid tumor', 'S
- S3 shortlist n=5 gold=False: Crohn's disease, Intestinal lymphoma, Ulcerative colitis, NSAID-induced enteropathy, Eosinophilic gastroenteritis
- S4 champion: **Crohn's disease** gold=False
- S4 raw (trunc): {"champion": "Crohn's disease", "rationale": "The patient's presentation with worsening abdominal distention, unintentional weight loss, and increasing difficulty with bowel movements, along with findings of small-bowel obstruction, multiple jejunal strictures, and perforated ulc

## Baseline B06
- discussion_turns=3
  - turn0 gold_mention=True diag=
    The patient's symptoms and test results, including the presence of lymphocytic infiltrates with epitheliotropism, suggest a lymphoid neoplasm, with lymphoma bei
  - turn1 gold_mention=True diag=
    The patient's history of chronic abdominal symptoms, weight loss, and findings of lymphocytic infiltrates with epitheliotropism support a diagnosis of lymphoma,
  - turn2 gold_mention=True diag=
    The patient's chronic abdominal symptoms, weight loss, and findings of lymphocytic infiltrates with epitheliotropism are consistent with a lymphoid neoplasm, su
- supervisor votes=3 top2=['Lymphoma', 'Gastrointestinal lymphoma'] gold=True

## Baseline B07
- draft=['Lymphoma', 'Inflammatory Bowel Disease (IBD)'] gold=True
- has_refine=True refine=[] gold=None
- queries(3): ['lymphocytic infiltrates with epitheliotropism in ileum', 'differential diagnosis for small bowel obstruction with lymphoid neoplasm', 'chronic obstructive pulmonary disease and opioid use disorder with abdominal symptoms']
- diagnose=['Lymphoma', 'Inflammatory Bowel Disease (IBD)'] gold=True

## Baseline B01
- queries=['chronic abdominal distention and weight loss in adults', 'small-bowel obstruction with wall thickening and mesenteric adenopathy', 'jejunal strictures and inflammatory bowel disease', 'lymphocytic infiltrates with epitheliotropism in ileal biopsies']
- n_chunks=12 rag_gold_mention=False
- chunk_sample: 
- top2=["Crohn's disease", 'Lymphoma'] gold=True

