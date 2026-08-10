# MCR / mcr_200b / case 329

- **gold**: urachal cyst
- **layer**: `base_win_rank`
- **correct**: e7=0 v0=1 B06=1 B07=0 B01=0 APHHM=
- **loci**: e7=`s3_hit_s4_miss` B06=`supervisor_ok` B07=`diagnose_hit_judge_miss` B01=`gen_hit_judge_miss` APHHM=`na`
- **primary_locus**: e7=s3_hit_s4_miss; B06=supervisor_ok
- **covariates**: vig_words=354; gold_words=2; eponym=False; subtype=False; e7_s2_rank=12; mapper_rescue=False
- **causal**: 骨干 S3 含金标，S4 终裁选错。

## Vignette (trunc)
A 26-year-old woman presented with a 2-day history of burning on urination, urinary frequency, nocturia, and constant 5/10 suprapubic pain that did not radiate. She denied fever, nausea, vomiting, changes in bowel movements, weight change, palpitations, heat or cold intolerance, peripheral edema, and abnormal vaginal discharge. Her last menstrual period was one week earlier. Physical examination revealed lower abdominal tenderness, most pronounced in the para-umbilical area, without costovertebr...

## Backbone e7
- S1 key_facts: 2-day history of burning on urination; Constant 5/10 suprapubic pain; Nocturia; Denies fever, nausea, vomiting, and changes in bowel movements; Last menstrual period was one week earlier; Physical examination revealed lower abdominal tenderness; Urinalysis with 10–25 WBCs per high-power field, moderate bacteria, and positive; Negative serum β-hCG, normal CBC and BMP
- S2 mode=complement k=3 pool_n=54 gold_in_s2=True
  - call1: ['Urachal adenocarcinoma', 'Bladder adenocarcinoma', 'Ovarian cystadenoma', 'Ovarian cystadenocarcinoma', 'Ureteral dupl
  - call2: ['Sarcoma botryoides', 'Rhabdomyosarcoma', 'Lymphoma of the bladder', 'Neuroendocrine tumor of the bladder', 'Paragangli
  - call3: ['Urachal diverticulum', 'Vesicourachal diverticulum', 'Bladder hamartoma', 'Neurofibroma of the bladder', 'Solitary fib
- S3 shortlist n=5 gold=True: Urachal adenocarcinoma, Adenocarcinoma of the urachus, Urachal cyst, Urachal diverticulum, Bladder adenocarcinoma
- S4 champion: **Urachal adenocarcinoma** gold=False
- S4 raw (trunc): {"champion": "Urachal adenocarcinoma", "rationale": "The presence of a large multiloculated mass extending from the dome of the bladder, as seen on the contrast-enhanced CT scan, along with worsening symptoms despite antibiotic treatment, suggests a malignant process. Urachal ade

## Backbone v0 (compact)
- S1 key_facts: 2-day history of burning on urination; Urinary frequency and nocturia; Constant 5/10 suprapubic pain; Denies fever, nausea, vomiting, and changes in bowel movements; Last menstrual period was one week earlier; Lower abdominal tenderness, most pronounced in the para-umbilical area; Urinalysis with 10–25 WBCs per high-power field, moderate bacteria, moderate muc; Negative serum β-hCG, normal CBC and BMP
- S2 mode=single k=1 pool_n=18 gold_in_s2=True
  - call1: ['Urachal cyst', 'Bladder diverticulum', 'Vesicoureteral reflux', 'Ureterocele', 'Paraganglioma', 'Pheochromocytoma', 'N
- S3 shortlist n=5 gold=True: Urachal cyst, Bladder cancer, Urachal sinus, Sarcoma botryoides, Rhabdomyosarcoma
- S4 champion: **Urachal cyst** gold=True
- S4 raw (trunc): {"champion": "Urachal cyst", "rationale": "The patient's symptoms and imaging findings, including a multiloculated mass extending from the bladder dome to the posterior surface of the umbilicus, are consistent with a urachal cyst, which is a congenital anomaly that can present wi

## Baseline B06
- discussion_turns=3
  - turn0 gold_mention=True diag=
    Given the patient's persistent symptoms despite antibiotic treatment and the imaging findings of a multiloculated mass extending from the bladder dome to the po
  - turn1 gold_mention=True diag=
    The patient's persistent symptoms and imaging findings suggest a urachal anomaly, with a urachal cyst being the most likely diagnosis given the presence of a mu
  - turn2 gold_mention=True diag=
    The patient's persistent symptoms despite antibiotic treatment and the imaging findings of a multiloculated mass extending from the bladder dome to the posterio
- supervisor votes=3 top2=['Urachal cyst', 'Malignant urachal remnant'] gold=True

## Baseline B07
- draft=['Urachal cyst', 'Urachal remnant anomaly with possible malignancy'] gold=True
- has_refine=True refine=[] gold=None
- queries(3): ['urachal remnant complications', 'urachal cyst symptoms', 'differential diagnosis of lower abdominal mass in young women']
- diagnose=['Urachal cyst', 'Urachal remnant anomaly with possible malignancy'] gold=True

## Baseline B01
- queries=['urachal remnant complications', 'differential diagnosis of multiloculated pelvic masses', 'urinary tract infection with persistent symptoms despite antibiotic treatment', 'imaging characteristics of urachal sinus vs urachal diverticulum vs patent urachus']
- n_chunks=12 rag_gold_mention=False
- chunk_sample: 
- top2=['Urachal adenocarcinoma', 'Urachal cyst'] gold=True

