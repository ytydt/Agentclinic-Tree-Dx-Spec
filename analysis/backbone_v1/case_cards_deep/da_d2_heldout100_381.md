# DA / d2_heldout100 / case 381

- **gold**: Good syndrome
- **layer**: `aphhm_win`
- **correct**: e7=0 v0=0 B06=0 B07=0 B01= APHHM=1
- **loci**: e7=`s2_miss` B06=`agents_miss` B07=`draft_miss` B01=`na` APHHM=`tree_hit_final_drop`
- **primary_locus**: APHHM=tree_hit_final_drop
- **covariates**: vig_words=282; gold_words=2; eponym=False; subtype=False; e7_s2_rank=None; mapper_rescue=False
- **causal**: APHHM 树含金标叶，final_ranking 剪掉。

## Vignette (trunc)
A White man in his 50s presented with painful oral erosions that began 2 years before. Medical history included recurrent respiratory infections and diarrhea. A previous intestinal biopsy had shown unspecific findings and absence of apoptosis. He reported a 5-kg weight loss attributed to impaired intake due to oral lesions. He was being evaluated for a mediastinal mass detected during chest radiography performed for pneumonia.  Physical examination revealed whitish edematous lacy patches with er...

## Options
  - A: Common variable immunodeficiency
  - B: Good syndrome
  - C: Paraneoplastic pemphigus
  - D: Erosive oral lichen planus

## Backbone e7
- S1 key_facts: Patient is a White man in his 50s; Oral erosions began 2 years before presentation; Patient has a history of recurrent respiratory infections and diarrhea; Previous intestinal biopsy showed unspecific findings and absence of apoptosis; Patient reported a 5-kg weight loss due to impaired intake; Mediastinal mass was detected during chest radiography for pneumonia; Physical examination revealed whitish edematous lacy patches with erosions on th; Skin and nails were not involved
- S2 mode=complement k=3 pool_n=55 gold_in_s2=False
  - call1: ['Lymphomatoid granulomatosis', 'Angioimmunoblastic T-cell lymphoma', 'Extranodal natural killer/T-cell lymphoma', 'Peri
  - call2: ['Mycosis fungoides', 'Sézary syndrome', 'Subepidermal blistering disease', 'Paraneoplastic pemphigus', 'Pemphigus vulga
  - call3: ['Midline destructive granuloma', 'Natural killer cell enteropathy', 'IgG4-related disease', 'Multifocal histiocytic sar
- S3 shortlist n=5 gold=False: Thymoma, Paraneoplastic pemphigus, Good's syndrome, Mucous membrane pemphigoid, Autoimmune lymphoproliferative syndrome
- S4 champion: **Paraneoplastic pemphigus** gold=False
- S4 raw (trunc): {"champion": "Paraneoplastic pemphigus", "rationale": "The patient's oral erosions, lingual biopsy showing epidermal acanthosis with scattered necrotic keratinocytes, and direct immunofluorescence showing fibrinogen deposition along basement membrane are consistent with paraneopl

## Backbone v0 (compact)
- S1 key_facts: Patient is a White man in his 50s; Oral erosions began 2 years before presentation; Weight loss of 5 kg due to impaired intake; Lingual biopsy showed epidermal acanthosis and basal-layer vacuolation; Direct immunofluorescence showed fibrinogen deposition along basement membrane; Decreased IgG serum level; Decreased total B lymphocyte count; Increased CD8+ T count with inverted CD4:CD8 ratio
- S2 mode=single k=1 pool_n=20 gold_in_s2=False
  - call1: ['Pemphigus vulgaris', 'Paraneoplastic pemphigus', 'Mycosis fungoides', "Sjogren's syndrome", 'Sarcoidosis', 'Lymphoma',
- S3 shortlist n=5 gold=False: Paraneoplastic pemphigus, Pemphigus vulgaris, Thymoma, Mycosis fungoides, Sjogren's syndrome
- S4 champion: **Paraneoplastic pemphigus** gold=False
- S4 raw (trunc): {"champion": "Paraneoplastic pemphigus", "rationale": "The patient's oral erosions, lingual biopsy showing epidermal acanthosis and basal-layer vacuolation, and direct immunofluorescence showing fibrinogen deposition along the basement membrane are consistent with paraneoplastic 

## Baseline B06
- discussion_turns=3
  - turn0 gold_mention=False diag=
    The patient's presentation of painful oral erosions, intestinal symptoms, and a mediastinal mass, along with the biopsy and immunofluorescence findings, suggest
  - turn1 gold_mention=False diag=
    The patient's oral erosions, intestinal symptoms, and thymoma, combined with biopsy and immunofluorescence findings, support a diagnosis of paraneoplastic pemph
  - turn2 gold_mention=False diag=
    The patient's complex presentation of oral erosions, intestinal symptoms, and a mediastinal mass, along with specific biopsy and immunofluorescence findings, al
- supervisor votes=3 top2=['Paraneoplastic Pemphigus', 'Thymoma-associated multiorgan autoimmunity'] gold=False

## Baseline B07
- draft=['Paraneoplastic Pemphigus', 'Thymoma-associated Mucocutaneous Disorder'] gold=False
- has_refine=True refine=[] gold=None
- queries(3): ['oral erosions and thymoma', 'paraneoplastic pemphigus', 'thymoma associated mucocutaneous disorders']
- diagnose=['Paraneoplastic Pemphigus', 'Thymoma-associated Mucocutaneous Disorder'] gold=False

## APHHM
- tree_n=25 tree_recall=True
- gold_leaf=B4.3:Good Syndrome parent=B4
- final_n=2 final_recall=False ranking=['Thymoma-associated Immunodeficiency', 'Paraneoplastic Pemphigus']
- human_at1=False fail_mode=prune_loss

