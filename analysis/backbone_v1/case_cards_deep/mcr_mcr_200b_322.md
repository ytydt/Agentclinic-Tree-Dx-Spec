# MCR / mcr_200b / case 322

- **gold**: Factitious disorder
- **layer**: `base_win_recall`
- **correct**: e7=0 v0=1 B06=1 B07=1 B01=1 APHHM=
- **loci**: e7=`s2_miss` B06=`supervisor_ok` B07=`diagnose_ok` B01=`gen_ok` APHHM=`na`
- **primary_locus**: e7=s2_miss; B06=supervisor_ok
- **covariates**: vig_words=378; gold_words=2; eponym=False; subtype=False; e7_s2_rank=None; mapper_rescue=False
- **causal**: 骨干入口完全未召回；基线直接给出金标/近义。

## Vignette (trunc)
A 14-year-old Caucasian girl was transferred from a community emergency department after treatment for presumed anaphylaxis following ingestion of a hypoallergenic nutritional supplement. Immediately after ingestion she reported wheezing, cough, and swelling of the lips, face, and tongue and self-administered epinephrine (0.3 mg) at home. Her history included suspected food allergies (wheat, oats, tree nuts, chocolate, eggs, cow’s milk, and rice) without documented reactions; intermittent asthma...

## Backbone e7
- S1 key_facts: 14-year-old girl with a history of suspected food allergies and intermittent ast; Ingestion of a hypoallergenic nutritional supplement triggered the initial episo; Self-administered epinephrine at home prior to ED arrival; Negative skin prick tests and serum-specific IgE to foods of concern except for ; Normal testing for hereditary angioedema and baseline serum tryptase; Lost 40 lb over the past year through dietary restriction and exercise; Homeschooled due to fears of allergic reactions; Multiple ED evaluations and PICU admissions for similar episodes
- S2 mode=complement k=3 pool_n=51 gold_in_s2=False
  - call1: ['Hereditary Angioedema Type 1', 'Hereditary Angioedema Type 2', 'Acquired Angioedema', 'Allergic Reaction', 'Anaphylaxi
  - call2: ['Autoimmune Angioedema', 'Histamine Intolerance', 'Mast Cell Activation Syndrome', 'Systemic Mastocytosis', 'Eosinophil
  - call3: ['Eosinophilic Pneumonia', 'Hypereosinophilic Syndrome', 'Chronic Eosinophilic Pneumonia', 'Acute Eosinophilic Pneumonia
- S3 shortlist n=5 gold=False: Mast Cell Activation Syndrome, Idiopathic Anaphylaxis, Vocal Cord Dysfunction, Eosinophilic Esophagitis, Autoimmune Angioedema
- S4 champion: **Vocal Cord Dysfunction** gold=False
- S4 raw (trunc): {"champion": "Vocal Cord Dysfunction", "rationale": "The patient's symptoms of stridor, biphasic wheezing, and poor air movement without visible oropharyngeal swelling, along with direct laryngoscopy showing no airway edema, are consistent with vocal cord dysfunction. The lack of

## Backbone v0 (compact)
- S1 key_facts: 14-year-old girl with a history of suspected food allergies; Intermittent asthma and complex regional pain syndrome; Major depressive disorder treated with fluoxetine; Lost 40 lb over the past year through dietary restriction and exercise; Skin prick tests and serum-specific IgE to foods of concern were negative except; Testing for hereditary angioedema and baseline serum tryptase were normal; Received IV fluids, epinephrine, inhaled bronchodilators, racemic epinephrine, a; Had seven similar episodes requiring ED evaluation and PICU admission
- S2 mode=single k=1 pool_n=20 gold_in_s2=True
  - call1: ['Hereditary Angioedema Type 1', 'Hereditary Angioedema Type 2', 'Acquired Angioedema', 'Allergic Reaction', 'Anaphylaxi
- S3 shortlist n=5 gold=True: Vocal Cord Dysfunction, Factitious Disorder, Panic Disorder, Asthma, Somatoform Disorder
- S4 champion: **Factitious Disorder** gold=True
- S4 raw (trunc): {"champion": "Factitious Disorder", "rationale": "The patient's episodes of subjective perioral swelling, hypotension, and stridor without objective edema, normal serial serum tryptase levels, and lack of airway edema or paradoxical vocal cord motion on direct laryngoscopy sugges

## Baseline B06
- discussion_turns=3
  - turn0 gold_mention=True diag=
    The patient's history of unexplained and recurrent episodes of anaphylaxis-like symptoms without objective evidence of allergic reactions, combined with a histo
  - turn1 gold_mention=True diag=
    The patient's recurrent episodes of anaphylaxis-like symptoms without objective evidence, complex medical and psychiatric history, and lack of response to treat
  - turn2 gold_mention=True diag=
    The patient's presentation of recurrent anaphylaxis-like episodes without objective evidence, complex medical and psychiatric history, and lack of response to t
- supervisor votes=3 top2=['Factitious disorder', 'Somatoform disorder'] gold=True

## Baseline B07
- draft=['Factitious Disorder Imposed on Self', 'Somatoform Disorder'] gold=True
- has_refine=True refine=[] gold=None
- queries(3): ['A 14-year-old Caucasian girl was transferred from a community emergency department after treatment for presumed anaphylaxis following ingestion of a hypoallergenic nutritional supplement. Immediately ', 'differential diagnosis A 14-year-old Caucasian girl was transferred from a community emergency department after treatment for presumed anaphylaxis following ingestion of a hypoallergenic nutritional supplement. Immediately ', 'clinical manifestations diagnosis  supportive history of reaction with ingestion. Testing for hereditary angioedema and baseline serum tryptase were normal. She had lost 40 lb over the past year']
- diagnose=['Factitious Disorder Imposed on Self', 'Somatoform Disorder'] gold=True

## Baseline B01
- queries=['induction of anaphylaxis by hypoallergenic nutritional supplements', 'differential diagnosis of episodic perioral swelling and stridor', 'evaluation of factitious disorder in patients with suspected allergies', 'psychiatric comorbidities in patients with recurrent anaphylaxis-like episodes']
- n_chunks=12 rag_gold_mention=False
- chunk_sample: 
- top2=['Factitious disorder', 'Munchausen syndrome'] gold=True

