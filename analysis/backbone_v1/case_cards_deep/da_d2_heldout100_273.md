# DA / d2_heldout100 / case 273

- **gold**: Very severe chronic atopic hand eczema with moderate to severe atopic dermatitis
- **layer**: `e7_win_rank`
- **correct**: e7=1 v0=1 B06=0 B07=0 B01= APHHM=0
- **loci**: e7=`ok` B06=`supervisor_hit_judge_miss` B07=`diagnose_hit_judge_miss` B01=`na` APHHM=`tree_hit_final_drop`
- **primary_locus**: e7=ok; B06=supervisor_hit_judge_miss; B07=diagnose_hit_judge_miss
- **covariates**: vig_words=132; gold_words=12; eponym=False; subtype=True; e7_s2_rank=1; mapper_rescue=False
- **causal**: APHHM 树含金标叶，final_ranking 剪掉。

## Vignette (trunc)
A woman in her 50s with 18 years history of very severe chronic hand eczema and moderate to severe dermatitis. Onset occurred in early childhood. Medical history includes asthma, rhinitis, and positive family history for atopy. She had limited contact with irritants to minimum.  Hand eczema was rated as 'very severe' according to validated photographic guide. Hand Eczema Severity Index (HECSI) score was 244 of 360 at initial presentation.  - Patch Testing Results: Positive reactions to:    - Nic...

## Options
  - A: Chronic Hyperkeratotic Hand Eczema
  - B: Very severe chronic atopic hand eczema with moderate to severe atopic dermatitis
  - C: Combined atopic dermatitis and allergic contact dermatitis
  - D: Atopic Dermatitis

## Backbone e7
- S1 key_facts: 18 years history of chronic hand eczema; Onset of hand eczema occurred in early childhood; Medical history includes asthma and rhinitis; Positive family history for atopy; Limited contact with irritants; HECSI score was 244 of 360 at initial presentation; Positive reactions to nickel, cobalt, and other allergens on patch testing; Very severe hand eczema according to validated photographic guide
- S2 mode=complement k=3 pool_n=47 gold_in_s2=True
  - call1: ['Atopic dermatitis', 'Allergic contact dermatitis', 'Irritant contact dermatitis', 'Nummular dermatitis', 'Dyshidrotic 
  - call2: ['Autosensitization dermatitis', 'Stasis dermatitis', 'Gloves and socks syndrome', 'Pompholyx', 'Dyshidrotic palmoplanta
  - call3: ['Pityriasis alba', 'Pityriasis rubra pilaris', 'Keratosis pilaris', 'Darier disease', 'Hailey-Hailey disease', 'Dowling
- S3 shortlist n=5 gold=True: Atopic dermatitis, Allergic contact dermatitis, Dyshidrotic eczema, Irritant contact dermatitis, Nummular dermatitis
- S4 champion: **Atopic dermatitis** gold=True
- S4 raw (trunc): {"champion": "Atopic dermatitis", "rationale": "The patient's history of chronic hand eczema since childhood, combined with a medical history of asthma and rhinitis, and a positive family history for atopy, strongly supports a diagnosis of atopic dermatitis. The presence of very 

## Backbone v0 (compact)
- S1 key_facts: 18 years history of chronic hand eczema; Onset of hand eczema occurred in early childhood; Medical history includes asthma and rhinitis; Positive family history for atopy; Limited contact with irritants; HECSI score was 244 of 360 at initial presentation; Positive patch testing reactions to nickel, cobalt, and other allergens; Hand eczema rated as 'very severe' according to validated photographic guide
- S2 mode=single k=1 pool_n=18 gold_in_s2=True
  - call1: ['Atopic dermatitis', 'Allergic contact dermatitis', 'Irritant contact dermatitis', 'Nummular dermatitis', 'Dyshidrotic 
- S3 shortlist n=5 gold=True: Atopic dermatitis, Allergic contact dermatitis, Dyshidrotic eczema, Irritant contact dermatitis, Nummular dermatitis
- S4 champion: **Atopic dermatitis** gold=True
- S4 raw (trunc): {"champion": "Atopic dermatitis", "rationale": "The patient's history of chronic hand eczema since childhood, combined with a personal and family history of atopy (asthma, rhinitis), suggests an atopic predisposition, which is a key characteristic of atopic dermatitis.", "rejecte

## Baseline B06
- discussion_turns=3
  - turn0 gold_mention=True diag=
    The patient's long history of severe hand eczema, positive patch testing results, and atopic background suggest a complex interplay of allergic and atopic facto
  - turn1 gold_mention=True diag=
    The patient's positive patch testing results and history of atopy support the likelihood of allergic contact dermatitis, while the long-standing nature of the c
  - turn2 gold_mention=True diag=
    The patient's severe chronic hand eczema, positive reactions to multiple allergens in patch testing, and history of atopy align with the prior opinions, reinfor
- supervisor votes=3 top2=['Allergic Contact Dermatitis', 'Atopic Dermatitis'] gold=True

## Baseline B07
- draft=['Allergic Contact Dermatitis', 'Atopic Dermatitis'] gold=True
- has_refine=True refine=[] gold=None
- queries(3): ['chronic hand eczema causes', 'allergic contact dermatitis diagnosis', 'atopic dermatitis vs contact dermatitis']
- diagnose=['Allergic Contact Dermatitis', 'Atopic Dermatitis'] gold=True

## APHHM
- tree_n=29 tree_recall=True
- gold_leaf=B1.1:atopic dermatitis parent=B1
- final_n=1 final_recall=False ranking=['allergic contact dermatitis']
- human_at1=False fail_mode=prune_loss

