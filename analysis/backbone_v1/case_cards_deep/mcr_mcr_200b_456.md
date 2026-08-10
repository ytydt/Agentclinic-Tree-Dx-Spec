# MCR / mcr_200b / case 456

- **gold**: Ureteroarterial fistula
- **layer**: `base_win_recall`
- **correct**: e7=0 v0=0 B06=1 B07=0 B01=0 APHHM=
- **loci**: e7=`s2_miss` B06=`supervisor_ok` B07=`draft_miss` B01=`rag_hit_gen_miss` APHHM=`na`
- **primary_locus**: e7=s2_miss; B06=supervisor_ok
- **covariates**: vig_words=303; gold_words=2; eponym=False; subtype=False; e7_s2_rank=None; mapper_rescue=False
- **causal**: 骨干入口完全未召回；基线直接给出金标/近义。

## Vignette (trunc)
An 80-year-old woman with a history of rectal cancer treated in 2008 by liver metastasectomy followed by Hartmann’s procedure with intraoperative radiotherapy (5×5 Gy) and adjuvant capecitabine, oxaliplatin, and bevacizumab presented in January 2011 with intermittent gross hematuria. Since December 2009 she had bilateral JJ stents for ureteral strictures, replaced regularly. In November 2010 she required drainage of a pelvic abscess after stent occlusion complicated by Candida glabrata infection...

## Backbone e7
- S1 key_facts: 80-year-old woman; History of rectal cancer; Treated with liver metastasectomy, Hartmann’s procedure, and intraoperative radi; History of bilateral JJ stents for ureteral strictures; Pelvic abscess drainage in November 2010; Type 2 diabetes mellitus; Angina pectoris; Hemoglobin 7.2 mmol/L
- S2 mode=complement k=3 pool_n=48 gold_in_s2=False
  - call1: ['Radiation cystitis', 'Ureteroenteric fistula', 'Arteriovenous fistula', 'Pseudoaneurysm', 'Ureteral stricture', 'Renal
  - call2: ['Chronic radiation nephropathy', 'Fistula between ureter and iliac vessels', 'Ureteral erosion into adjacent vascular g
  - call3: ['Rendu-Osler-Weber disease', 'Hereditary hemorrhagic telangiectasia', 'Klippel-Trenaunay-Weber syndrome', 'Blue rubber 
- S3 shortlist n=5 gold=False: Radiation cystitis, Ureteroenteric fistula, Arteriovenous fistula, Pseudoaneurysm, Ureteral stricture
- S4 champion: **Radiation cystitis** gold=False
- S4 raw (trunc): {"champion": "Radiation cystitis", "rationale": "The patient's history of intraoperative radiotherapy and subsequent development of hematuria, ureteral strictures, and hydronephrosis are consistent with radiation-induced damage to the urinary tract, which is a common cause of rad

## Backbone v0 (compact)
- S1 key_facts: 80-year-old woman; History of rectal cancer; Treated with liver metastasectomy, Hartmann’s procedure, and intraoperative radi; Adjuvant chemotherapy with capecitabine, oxaliplatin, and bevacizumab; Bilateral JJ stents for ureteral strictures since December 2009; Pelvic abscess drainage in November 2010; Type 2 diabetes mellitus; Angina pectoris
- S2 mode=single k=1 pool_n=17 gold_in_s2=False
  - call1: ['Radiation cystitis', 'Ureteroenteric fistula', 'Arteriovenous fistula', 'Pseudoaneurysm', 'Ureteral stricture', 'Renal
- S3 shortlist n=5 gold=False: Radiation cystitis, Ureteroenteric fistula, Arteriovenous fistula, Pseudoaneurysm, Ureteral stricture
- S4 champion: **Radiation cystitis** gold=False
- S4 raw (trunc): {"champion": "Radiation cystitis", "rationale": "The patient's history of intraoperative radiotherapy and subsequent development of hematuria, ureteral strictures, and hydronephrosis are consistent with radiation-induced damage to the urinary tract, which is a hallmark of radiati

## Baseline B06
- discussion_turns=3
  - turn0 gold_mention=True diag=
    The patient's history of radiation, surgery, and recurrent hematuria suggests a complex pelvic pathology, with ureteroarterial fistula being the most likely cau
  - turn1 gold_mention=True diag=
    The patient's recurrent gross hematuria, history of radiation and surgery, and the presence of a ureteroileal fistula support a complex pelvic pathology, with u
  - turn2 gold_mention=True diag=
    The patient's history of radiation, surgery, and recurrent hematuria, along with the presence of a ureteroileal fistula and the findings of the CT angiogram, su
- supervisor votes=3 top2=['Ureteroarterial fistula', 'Ureteroileal fistula'] gold=True

## Baseline B07
- draft=['Radiation-induced ureteral damage', 'Ureteroileal fistula with recurrent hematuria'] gold=False
- has_refine=True refine=[] gold=None
- queries(4): ['ureteral bleeding causes', 'radiation-induced ureteral damage', 'ureteroileal fistula complications', 'hematuria in cancer patients']
- diagnose=['Radiation-induced ureteral damage', 'Ureteroileal fistula with recurrent hematuria'] gold=False

## Baseline B01
- queries=['causes of gross hematuria in patients with history of pelvic radiation', 'management of ureteroileal fistula', 'complications of ureteral stent placement', 'embolization techniques for renal artery bleeding']
- n_chunks=12 rag_gold_mention=False
- chunk_sample: 
- top2=['Radiation Cystitis', 'Ureteroileal Fistula'] gold=False

