# MCR / mcr_v1 / case 50

- **gold**: Gastrointestinal clear cell sarcoma
- **layer**: `all_miss_but_recalled` · **layer_aphhm**: ``
- **correct**: e7=0 v0=0 B06=0 B07=0 B01=0 APHHM=0
- **e7_locus**: `s4_hit_judge_miss` · **e7_fail_code**: `s4_hit_judge_miss`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=1 e7_champ_cluster=gold B06_sup_gold=0 B07_diag_gold=0 same_cluster_flip=0 true_entrance=0
- **APHHM**: locus=`tree_miss` code=`aphhm_tree_miss` prune_e7_ok=0

## Vignette
A 20-year-old woman presented with a 3-month history of intermittent abdominal pain, recurrent vomiting, and melena. She had no significant past medical history and no family history of cancer. On examination, she had mild abdominal tenderness; gynecological examination was normal. Laboratory studies revealed iron-deficiency anemia; white blood cell and platelet counts were normal. Upper and lower endoscopies were unremarkable. Magnetic resonance enterography demonstrated a focal segment of small-bowel wall thickening measuring 15 mm by 2 mm. An exploratory laparotomy revealed an exophytic ileal mass with mesenteric lymphadenopathy but no peritoneal or hepatic metastases. A wide segmental resection was performed without complication.

Gross examination showed a 30 mm by 25 mm polypoid, tan-white, lobulated mass arising from the small-intestinal wall. Microscopically, the lesion was a transmural, infiltrative proliferation of uniform epithelioid and spindle cells arranged in nested and fascicular patterns, with variable eosinophilic or clear cytoplasm, round to oval vesicular nuclei, inconspicuous nucleoli, and up to 10 mitoses per 10 high-power fields; there was mucosal ulceration …

## Backbone e7

- S2 n=48 gold_rank=13
  - clusters: gold=1 near=7 other=40
- S3 shortlist (5):
  - [near] Gastrointestinal stromal tumor
  - [gold] Clear cell sarcoma
  - [other] Malignant peripheral nerve sheath tumor
  - [other] Schwannoma
  - [near] Gastrointestinal autonomic nerve tumor
    - why_kept(Gastrointestinal stromal tumor): matches small intestine mass and spindle cell morphology
    - why_kept(Clear cell sarcoma): matches small intestine location and epithelioid/spindle cell morphology
    - why_kept(Malignant peripheral nerve sheath tumor): matches S100 protein positivity and spindle cell morphology
    - why_kept(Schwannoma): matches S100 protein positivity and spindle cell morphology
    - why_kept(Gastrointestinal autonomic nerve tumor): matches small intestine location and spindle cell morphology with S100 protein positivity
- S4 champion: **Clear cell sarcoma** cluster=gold jaccard=0.75
- S4 rationale: The tumor's strong positivity for S100 protein and SOX10, along with its epithelioid and spindle cell morphology, supports this diagnosis. Clear cell sarcoma is known for its expression of S100 and SOX10, and its presentation as a small intestinal mass with lymphadenopathy is consistent with the case facts.
- S4 rejected:
  - [near] Gastrointestinal stromal tumor: Negative for CD117, DOG1, and other typical markers of GIST
  - [other] Malignant peripheral nerve sheath tumor: Lack of perineural invasion and less typical morphology for MPNST
  - [other] Schwannoma: Transmural, infiltrative growth pattern and lymphadenopathy are not typical for schwannoma
  - [near] Gastrointestinal autonomic nerve tumor: Immunohistochemical profile does not match, and morphology is not characteristic

## B06 (code=`b06_supervisor_drop` locus=`agents_hit_supervisor_drop`)
- supervisor: ['Schwannoma', 'Gastrointestinal Stromal Tumor (GIST)']
  clusters: {'gold': 0, 'near': 1, 'other': 1, 'empty': 0}
- discussion labels (n=15): ['Gastrointestinal Stromal Tumor (GIST)', 'Malignant Melanoma', 'Neuroendocrine Tumor', 'Leiomyosarcoma', 'Schwannoma', 'Schwannoma', 'Gastrointestinal Stromal Tumor (GIST)', 'Neuroendocrine Tumor']
- votes=3 turns=3

## B07 (code=`b07_draft_miss` locus=`draft_miss`)
- draft: ['Malignant Peripheral Nerve Sheath Tumor (MPNST)', 'Gastrointestinal Stromal Tumor (GIST)']
- diagnose: ['Malignant Peripheral Nerve Sheath Tumor (MPNST)', 'Gastrointestinal Stromal Tumor (GIST)']
- queries: ['small bowel tumors in young adults', 'S100 protein and SOX10 positive intestinal tumors', 'Gastrointestinal stromal tumor vs other intestinal tumors']

## B01 (code=`b01_gen_miss` locus=`rag_hit_gen_miss`)
- top2: ['Gastrointestinal Stromal Tumor (GIST)', 'Neuroendocrine Tumor (NET)']
- queries: ['small bowel tumors in young adults', 'S100 protein and SOX10 positive intestinal tumors', 'differential diagnosis of small intestinal masses with spindle cell morphology', 'immunohistochemical profiles of gastrointestinal neuroectodermal tumors']
- n_chunks=12

## APHHM
- tree_n=17 final_n=2
- final: ['Gastrointestinal Stromal Tumor', 'Carcinoid Tumor']
- tree gold_cluster_n=0 final gold=False

