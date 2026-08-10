# DA / d2_heldout200b / case 737

- **gold**: Leiomyomatosis peritonealis disseminata (LPD) with endometriosis
- **layer**: `all_miss_but_recalled` · **layer_aphhm**: ``
- **correct**: e7=0 v0=0 B06=0 B07=0 B01= APHHM=
- **e7_locus**: `s2_miss` · **e7_fail_code**: `s2_miss`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=0 e7_champ_cluster=other B06_sup_gold=0 B07_diag_gold=1 same_cluster_flip=0 true_entrance=0
- **APHHM**: locus=`na` code=`na` prune_e7_ok=0

## Vignette
A 40-year-old woman, G4P1, presented with pain in the right lower abdomen persisting for eight years, with recent aggravation and abdominal expansion sensation in the past month. Surgical history includes: cesarean section (2009), laparoscopic myomectomy (2012), surgeries for fibroids and ovarian cysts (2015, 2018), hysteroscopic IUD placement (2018), endometriomas puncture (2019), and total abdominal hysterectomy with right adnexectomy and left salpingectomy (2020). The pain gradually increased requiring oral painkillers. Patient has a two-year smoking history (7 cigarettes/day) but quit 5 years ago.

Patient appeared in visible pain with forced posture. Abdomen was soft and tender in lower part, without rebound tenderness. Pelvic examination revealed: no hymen/vaginal obstruction, smooth sutured end. A 10 cm mass was palpable in pelvic cavity, fixed to anterior rectum, with clear boundary, hard texture, significant tenderness and limited mobility. Rectal examination showed smooth mucosa with a hard, mobile, non-tender mass 7 cm from anus.

- Laboratory Tests:  - CA125: 35.08 U/ml  - Hormone levels (post-surgery): LH 44.87 IU/L, FSH 108.8 IU/L, Prolactin 6.62 μg/L, Progesterone 0.…

## Options
- A: Deep infiltrating endometriosis
- B: Recurrent/parasitic pelvic leiomyoma
- C: Pelvic endometriosis
- D: Leiomyomatosis peritonealis disseminata (LPD) with endometriosis **←gold**

## Backbone e7

- S2 n=55 gold_rank=None
  - clusters: gold=0 near=2 other=53
- S3 shortlist (5):
  - [other] Leiomyosarcoma
  - [other] Desmoid tumor
  - [other] Aggressive angiomyxoma
  - [other] Uterine carcinosarcoma
  - [other] Ovarian cancer
    - why_kept(Leiomyosarcoma): Smooth muscle tumor with high Ki-67 index and recent aggravation of symptoms
    - why_kept(Desmoid tumor): Pelvic mass with clear boundary and limited mobility, consistent with desmoid tumor characteristics
    - why_kept(Aggressive angiomyxoma): Large pelvic mass with significant tenderness and fixed to anterior rectum, consistent with aggressive angiomyxoma presentation
    - why_kept(Uterine carcinosarcoma): History of multiple surgeries for fibroids and ovarian cysts, with recent increase in CA125 level
    - why_kept(Ovarian cancer): Pelvic mass with uneven signals on MRI and inhomogeneous enhancement on CT, raising concern for ovarian cancer
- S4 champion: **Aggressive angiomyxoma** cluster=other jaccard=0.00
- S4 rationale: The patient's presentation of a fixed mass with clear boundary and limited mobility, along with the biopsy results showing smooth muscle tumor and immunohistochemistry positive for CD34, SMA, desmin, focal CD10, ER, PR, and 2% Ki-67, is consistent with aggressive angiomyxoma. The tumor's location and attachment to the anterior rectum also support this diagnosis.
- S4 rejected:
  - [other] Leiomyosarcoma: The low Ki-67 index (2%) is not typical for leiomyosarcoma, which usually has a higher proliferation rate.
  - [other] Desmoid tumor: The presence of a high CA125 level and the tumor's location and attachment to the rectum are not typical for desmoid tumors.
  - [other] Uterine carcinosarcoma: The patient has undergone total abdominal hysterectomy, making uterine carcinosarcoma unlikely.
  - [other] Ovarian cancer: The patient has undergone right adnexectomy and the tumor is attached to the rectum, making ovarian cancer less likely.

## B06 (code=`b06_agents_miss` locus=`agents_miss`)
- supervisor: ['Leiomyosarcoma', 'Uterine leiomyoma (recurrence)']
  clusters: {'gold': 0, 'near': 0, 'other': 2, 'empty': 0}
- discussion labels (n=15): ['Leiomyosarcoma', 'Uterine leiomyoma (recurrence)', 'Ovarian cancer', 'Endometriosis', 'Rectal cancer', 'Leiomyosarcoma', 'Uterine leiomyoma (recurrence)', 'Ovarian cancer']
- votes=3 turns=3

## B07 (code=`b07_judge_miss` locus=`diagnose_hit_judge_miss`)
- draft: ['Leiomyoma', 'Leiomyosarcoma']
- diagnose: ['Leiomyoma', 'Leiomyosarcoma']
- queries: ['smooth muscle tumor in pelvic cavity', 'CD34, SMA, desmin, ER, PR positive tumor', 'Ki-67 2% in smooth muscle tumor']

## B01 (code=`na` locus=`na`)
_na_

## APHHM
_na_

