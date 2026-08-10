# MCR / mcr_v1 / case 126

- **gold**: Extranodal natural killer/T-cell lymphoma nasal type
- **layer**: `base_win_rank` · **layer_aphhm**: `aphhm_lose`
- **correct**: e7=0 v0=0 B06=0 B07=1 B01=0 APHHM=0
- **e7_locus**: `s2_hit_s3_drop` · **e7_fail_code**: `s2_gold_low_rank`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=0 e7_champ_cluster=near B06_sup_gold=1 B07_diag_gold=1 same_cluster_flip=0 true_entrance=0
- **APHHM**: locus=`final_hit_judge_miss` code=`aphhm_judge_miss` prune_e7_ok=0

## Vignette
A 53-year-old Hispanic man presented with painful left lower-extremity swelling and erythema. Six months earlier, incidentally noted bilateral adrenal and periaortic retroperitoneal masses were not further evaluated. He reported intermittent fevers, episodic night sweats, decreased appetite, and palpitations. He denied trauma or injury to the leg. On examination, the left calf had ill-defined, warm, confluent erythema, edema, and tender induration. Laboratory studies showed mild lymphocytopenia, moderate anemia, elevated creatine kinase, elevated aldolase, and elevated lactate dehydrogenase; peripheral-blood flow cytometry was unremarkable. CT and MRI of the leg revealed gastrocnemius myositis, extensive subcutaneous and superficial myofascial edema, and popliteal lymphadenopathy without evident lymphatic obstruction. He was started on intravenous ceftriaxone for presumed cellulitis and pyomyositis but did not improve. A punch biopsy of skin from the lower leg showed a sparse perivascular and interstitial infiltrate of enlarged atypical mononuclear cells in the reticular dermis and subcutis, not consistent with cellulitis.

What is the most likely diagnosis?

Options:
A. Extranodal…

## Backbone e7

- S2 n=51 gold_rank=7
  - clusters: gold=1 near=2 other=48
- S3 shortlist (5):
  - [near] Subcutaneous panniculitis-like T-cell lymphoma
  - [other] Wegener's granulomatosis
  - [other] Polyarteritis nodosa
  - [other] Takayasu arteritis
  - [other] Erdheim-Chester disease
    - why_kept(Subcutaneous panniculitis-like T-cell lymphoma): Atypical mononuclear cells on biopsy and lack of response to antibiotics
    - why_kept(Wegener's granulomatosis): Systemic symptoms and presence of bilateral adrenal and periaortic retroperitoneal masses
    - why_kept(Polyarteritis nodosa): Systemic symptoms and presence of bilateral adrenal and periaortic retroperitoneal masses
    - why_kept(Takayasu arteritis): Systemic symptoms and presence of bilateral adrenal and periaortic retroperitoneal masses
    - why_kept(Erdheim-Chester disease): Systemic symptoms and presence of bilateral adrenal and periaortic retroperitoneal masses
- S4 champion: **Subcutaneous panniculitis-like T-cell lymphoma** cluster=near jaccard=0.20
- S4 rationale: The presence of a sparse perivascular and interstitial infiltrate of enlarged atypical mononuclear cells in the punch biopsy, along with systemic symptoms such as intermittent fevers, night sweats, and weight loss, is consistent with Subcutaneous panniculitis-like T-cell lymphoma. The lack of improvement with antibiotics and the presence of myositis and lymphadenopathy also support this diagnosis.
- S4 rejected:
  - [other] Wegener's granulomatosis: Wegener's typically presents with granulomatous inflammation and vasculitis, which is not described in the biopsy results
  - [other] Polyarteritis nodosa: Polyarteritis nodosa is a medium-vessel vasculitis that typically presents with hypertension, renal involvement, and abdominal pain, which are not mentioned in the vignette
  - [other] Takayasu arteritis: Takayasu arteritis is a large-vessel vasculitis that typically presents with arm claudication, decreased pulses, and hypertension, which are not described in the vignette
  - [other] Erdheim-Chester disease: Erdheim-Chester disease is a histiocytic disorder that typically presents with bone pain, exophthalmos, and diabetes insipidus, which are not mentioned in the vignette

## B06 (code=`b06_judge_miss` locus=`supervisor_hit_judge_miss`)
- supervisor: ['Lymphoma', 'Sarcoma']
  clusters: {'gold': 1, 'near': 0, 'other': 1, 'empty': 0}
- discussion labels (n=15): ['Lymphoma', 'Sarcoma', 'Retroperitoneal fibrosis', 'Inflammatory myofasciitis', 'Cellulitis', 'Lymphoma', 'Sarcoma', 'Retroperitoneal fibrosis']
- votes=3 turns=3

## B07 (code=`b07_ok` locus=`diagnose_ok`)
- draft: ['Lymphoma', 'Mantle Cell Lymphoma']
- diagnose: ['Lymphoma', 'Mantle Cell Lymphoma']
- queries: ['lymphoma with skin and muscle involvement', 'periaortic retroperitoneal masses and lymphadenopathy', 'atypical mononuclear cells in skin biopsy']

## B01 (code=`b01_judge_miss` locus=`gen_hit_judge_miss`)
- top2: ['Lymphoma', 'Dermatomyositis']
- queries: ['atypical mononuclear cell infiltrate in skin biopsy', 'periaortic retroperitoneal masses with systemic symptoms', 'myositis and lymphadenopathy without infection', 'elevated lactate dehydrogenase and aldolase with anemia']
- n_chunks=12

## APHHM
- tree_n=48 final_n=4
- final: ['Lymphoma', 'Castleman disease', 'Immune-Mediated Necrotizing Myopathy', 'Rosai-Dorfman disease']
- tree gold_cluster_n=3 final gold=True

