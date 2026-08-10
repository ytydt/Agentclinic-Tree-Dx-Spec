# DA / d2_heldout200b / case 637

- **gold**: Chronic Spontaneous Urticaria (CSU)
- **layer**: `all_miss_but_recalled`
- **correct**: e7=0 v0=0 B06=0 B07=0 B01= APHHM=
- **loci**: e7=`s2_miss` B06=`supervisor_hit_judge_miss` B07=`draft_miss` B01=`na` APHHM=`na`
- **primary_locus**: e7=s2_miss; recalled_but_none_correct
- **covariates**: vig_words=150; gold_words=4; eponym=False; subtype=False; e7_s2_rank=None; mapper_rescue=False
- **causal**: 至少一臂召回金标但无人 Acc@1——排序/裁决天花板。

## Vignette (trunc)
A 35-year-old woman with a medical history of Hashimoto disease, mild persistent asthma, allergic rhinitis, and Ehlers-Danlos syndrome. Approximately 7 hours after receiving her first dose of vaccination, she developed generalized pruritus and urticaria. The patient had no history of urticaria, angioedema, or COVID-19 infection. Her symptoms were not associated with recent viral illness, new medications, nonsteroidal anti-inflammatory drugs, opioids, alcohol, food, or physical stimuli including ...

## Options
  - A: Acute urticaria (idiopathic)
  - B: Chronic Spontaneous Urticaria (CSU)
  - C: Acute spontaneous urticaria
  - D: Autoimmune urticaria

## Backbone e7
- S1 key_facts: 35-year-old woman; Medical history of Hashimoto disease; Mild persistent asthma; Allergic rhinitis; Ehlers-Danlos syndrome; First dose of vaccination; Symptoms developed approximately 7 hours after vaccination; No history of urticaria, angioedema, or COVID-19 infection
- S2 mode=complement k=3 pool_n=50 gold_in_s2=False
  - call1: ['Anaphylaxis', 'Urticaria pigmentosa', 'Mastocytosis', 'Autoimmune urticaria', 'Allergic contact dermatitis', 'Atopic d
  - call2: ['Goodpasture syndrome', 'Ehlers-Danlos syndrome-associated angioedema', 'Gleich syndrome', 'Cold-induced urticaria', 'C
  - call3: ['Schnitzler syndrome', 'Neonatal-onset multisystem inflammatory disease', 'Muckle-Wells syndrome', 'Familial cold autoi
- S3 shortlist n=5 gold=False: Anaphylaxis, Vaccine-induced anaphylaxis, Autoimmune urticaria, Angioedema due to C1 esterase inhibitor deficiency, Ehlers-Danlos syndrome-associated angioedema
- S4 champion: **Vaccine-induced anaphylaxis** gold=False
- S4 raw (trunc): {"champion": "Vaccine-induced anaphylaxis", "rationale": "The patient developed generalized pruritus and urticaria approximately 7 hours after receiving her first dose of vaccination, which is a typical timeline for an allergic reaction to a vaccine.", "rejected": [{"label": "Ana

## Backbone v0 (compact)
- S1 key_facts: 35-year-old woman; Medical history of Hashimoto disease; Mild persistent asthma; Allergic rhinitis; Ehlers-Danlos syndrome; First dose of vaccination; Symptoms developed approximately 7 hours after vaccination; No history of urticaria, angioedema, or COVID-19 infection
- S2 mode=single k=1 pool_n=17 gold_in_s2=False
  - call1: ['Anaphylaxis', 'Urticaria pigmentosa', 'Mastocytosis', 'Autoimmune urticaria', 'Allergic contact dermatitis', 'Atopic d
- S3 shortlist n=5 gold=False: Anaphylaxis, Autoimmune urticaria, Vaccine-induced anaphylaxis, Mast cell activation syndrome, Angioedema due to C1 esterase inhibitor deficiency
- S4 champion: **Vaccine-induced anaphylaxis** gold=False
- S4 raw (trunc): {"champion": "Vaccine-induced anaphylaxis", "rationale": "The patient developed generalized pruritus and urticaria approximately 7 hours after receiving her first dose of vaccination, which is a strong temporal association, and the symptoms are consistent with an allergic reactio

## Baseline B06
- discussion_turns=3
  - turn0 gold_mention=True diag=
    The patient's symptoms of generalized pruritus, urticaria, and angioedema shortly after receiving a vaccination suggest an allergic reaction, which is the most 
  - turn1 gold_mention=True diag=
    The patient's presentation of generalized pruritus, urticaria, and angioedema shortly after vaccination aligns with an allergic reaction, consistent with Doctor
  - turn2 gold_mention=True diag=
    The patient's symptoms of generalized pruritus, urticaria, and angioedema shortly after receiving a vaccination are consistent with an allergic reaction, aligni
- supervisor votes=3 top2=['Allergic reaction to vaccination', 'Urticaria'] gold=True

## Baseline B07
- draft=['Allergic reaction to vaccine (urticaria and angioedema)', 'Anaphylaxis'] gold=False
- has_refine=True refine=[] gold=None
- queries(3): ['urticaria after vaccination', 'allergic reactions to vaccines', 'anaphylaxis vs urticaria']
- diagnose=['Allergic reaction to vaccine (urticaria and angioedema)', 'Anaphylaxis'] gold=False

