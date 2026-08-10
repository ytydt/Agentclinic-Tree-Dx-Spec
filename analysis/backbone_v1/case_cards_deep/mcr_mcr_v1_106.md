# MCR / mcr_v1 / case 106

- **gold**: neuroendocrine tumor
- **layer**: `all_miss_but_recalled`
- **correct**: e7=0 v0=0 B06=0 B07=0 B01=0 APHHM=0
- **loci**: e7=`s2_hit_s3_drop` B06=`agents_miss` B07=`draft_miss` B01=`rag_miss` APHHM=`tree_miss`
- **primary_locus**: e7=s2_hit_s3_drop; recalled_but_none_correct
- **covariates**: vig_words=200; gold_words=2; eponym=False; subtype=False; e7_s2_rank=37; mapper_rescue=False
- **causal**: 骨干 S2 已召回，S3 短表丢掉金标。

## Vignette (trunc)
A 65-year-old woman was admitted with a 2-week history of rapidly progressive visual reduction, drowsiness, polyuria, and polydipsia. Her medical history included a temporal arachnoid cyst with seizures and a vestibular schwannoma treated by gamma-knife radiosurgery 2 years earlier. On examination, she had bitemporal hemianopsia; no other neurological deficits or flushing or diarrhea were noted.  Magnetic resonance imaging of the brain showed a 2-cm sellar/suprasellar mass compressing the optic ...

## Backbone e7
- S1 key_facts: 2-week history of rapidly progressive visual reduction; Drowsiness; Polyuria; Polydipsia; Temporal arachnoid cyst with seizures; Vestibular schwannoma treated by gamma-knife radiosurgery 2 years earlier; Bitemporal hemianopsia; No other neurological deficits
- S2 mode=complement k=3 pool_n=45 gold_in_s2=True
  - call1: ['Pituitary adenoma', 'Craniopharyngioma', 'Meningioma', 'Germ cell tumor', 'Lymphoma', 'Granulomatosis with polyangiiti
  - call2: ['Spindle cell oncocytoma', 'Pituitary carcinoma', 'Gangliocytoma', 'Sellar schwannoma', 'Pituicytoma', 'Granular cell t
  - call3: ['Silent corticotroph adenoma', 'Glycoprotein hormone-producing pituitary adenoma', 'Thyrotroph adenoma', 'Somatotroph a
- S3 shortlist n=5 gold=False: Pituitary adenoma, Craniopharyngioma, Lymphoma, Meningioma, Pituitary apoplexy
- S4 champion: **Pituitary adenoma** gold=False
- S4 raw (trunc): {"champion": "Pituitary adenoma", "rationale": "The patient's presentation with rapidly progressive visual reduction, bitemporal hemianopsia, and a sellar/suprasellar mass compressing the optic chiasm, along with abnormal endocrine levels and an elevated prolactin level, is most 

## Backbone v0 (compact)
- S1 key_facts: 2-week history of rapidly progressive visual reduction; Drowsiness; Polyuria; Polydipsia; Temporal arachnoid cyst with seizures; Vestibular schwannoma treated by gamma-knife radiosurgery 2 years earlier; Bitemporal hemianopsia; No other neurological deficits
- S2 mode=None k=None pool_n=16 gold_in_s2=False
  - pool gold matches: []
  - pool head: Pituitary adenoma, Craniopharyngioma, Meningioma, Germ cell tumor, Lymphoma, Granulomatosis with polyangiitis, Sarcoidosis, Tuberculum sellae meningioma
- S3 shortlist n=5 gold=False: Pituitary adenoma, Craniopharyngioma, Meningioma, Pituitary apoplexy, Hypophysitis
- S4 champion: **Pituitary adenoma** gold=False
- S4 raw (trunc): {"champion": "Pituitary adenoma", "rationale": "The patient's rapidly progressive visual reduction, bitemporal hemianopsia, and a 2-cm sellar/suprasellar mass compressing the optic chiasm are consistent with a pituitary adenoma. The lesion's characteristics on MRI, including its 

## Baseline B06
- discussion_turns=3
  - turn0 gold_mention=False diag=
    The patient's symptoms of rapidly progressive visual reduction, drowsiness, polyuria, and polydipsia, along with bitemporal hemianopsia and a sellar/suprasellar
  - turn1 gold_mention=False diag=
    The patient's symptoms and MRI findings are consistent with a pituitary adenoma, and the endocrinological evaluation results support this diagnosis, aligning wi
  - turn2 gold_mention=False diag=
    The patient's symptoms of rapidly progressive visual reduction, drowsiness, polyuria, and polydipsia, along with bitemporal hemianopsia and a sellar/suprasellar
- supervisor votes=3 top2=['Pituitary Adenoma', 'Craniopharyngioma'] gold=False

## Baseline B07
- draft=['Pituitary Adenoma', 'Craniopharyngioma'] gold=False
- has_refine=True refine=[] gold=None
- queries(4): ['sellar/suprasellar mass compressing optic chiasm', 'bitemporal hemianopsia causes', 'pituitary gland tumor symptoms', 'radiosurgery complications']
- diagnose=['Pituitary Adenoma', 'Craniopharyngioma'] gold=False

## Baseline B01
- queries=['sellar/suprasellar mass compressing optic chiasm', 'rapidly progressive visual reduction and polyuria/polydipsia', 'bitemporal hemianopsia and sellar/suprasellar lesion', 'endocrine evaluation in sellar/suprasellar mass']
- n_chunks=12 rag_gold_mention=False
- chunk_sample: 
- top2=['Pituitary Adenoma', 'Craniopharyngioma'] gold=False

## APHHM
- tree_n=26 tree_recall=False
- gold_leaf=None
- final_n=1 final_recall=False ranking=['Pituitary Adenoma']
- human_at1=False fail_mode=tree_miss

