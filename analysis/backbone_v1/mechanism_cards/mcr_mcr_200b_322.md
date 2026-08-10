# MCR / mcr_200b / case 322

- **gold**: Factitious disorder
- **layer**: `base_win_recall` · **layer_aphhm**: ``
- **correct**: e7=0 v0=1 B06=1 B07=1 B01=1 APHHM=
- **e7_locus**: `s2_miss` · **e7_fail_code**: `s2_miss`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=0 e7_champ_cluster=other B06_sup_gold=1 B07_diag_gold=1 same_cluster_flip=0 true_entrance=1
- **APHHM**: locus=`na` code=`na` prune_e7_ok=0

## Vignette
A 14-year-old Caucasian girl was transferred from a community emergency department after treatment for presumed anaphylaxis following ingestion of a hypoallergenic nutritional supplement. Immediately after ingestion she reported wheezing, cough, and swelling of the lips, face, and tongue and self-administered epinephrine (0.3 mg) at home. Her history included suspected food allergies (wheat, oats, tree nuts, chocolate, eggs, cow’s milk, and rice) without documented reactions; intermittent asthma; complex regional pain syndrome; delayed gastric emptying; and major depressive disorder treated with fluoxetine, increased to 60 mg daily 5 months earlier. Skin prick tests and serum-specific IgE to foods of concern were negative except for sensitization to several tree nuts without a supportive history of reaction with ingestion. Testing for hereditary angioedema and baseline serum tryptase were normal. She had lost 40 lb over the past year through dietary restriction and exercise and was homeschooled due to fears of allergic reactions.

In the ED she had stridor, biphasic wheezing, and poor air movement without visible oropharyngeal swelling. She was afebrile, blood pressure 94/48 mmHg, …

## Backbone e7

- S2 n=51 gold_rank=None
  - clusters: gold=0 near=0 other=51
- S3 shortlist (5):
  - [other] Mast Cell Activation Syndrome
  - [other] Idiopathic Anaphylaxis
  - [other] Vocal Cord Dysfunction
  - [other] Eosinophilic Esophagitis
  - [other] Autoimmune Angioedema
    - why_kept(Mast Cell Activation Syndrome): Recurring episodes of anaphylaxis-like symptoms without clear allergen exposure, normal serum tryptase levels, and response to antihistamines and corticosteroids
    - why_kept(Idiopathic Anaphylaxis): Episodes of anaphylaxis without identifiable cause, normal testing for hereditary angioedema, and lack of objective edema on direct laryngoscopy
    - why_kept(Vocal Cord Dysfunction): Stridor and wheezing without visible oropharyngeal swelling, and lack of airway edema on direct laryngoscopy
    - why_kept(Eosinophilic Esophagitis): History of food allergies and suspected food-induced reactions, although skin prick tests and serum-specific IgE were largely negative
    - why_kept(Autoimmune Angioedema): Recurring episodes of angioedema-like symptoms without clear allergen exposure or family history of hereditary angioedema
- S4 champion: **Vocal Cord Dysfunction** cluster=other jaccard=0.00
- S4 rationale: The patient's symptoms of stridor, biphasic wheezing, and poor air movement without visible oropharyngeal swelling, along with direct laryngoscopy showing no airway edema, are consistent with vocal cord dysfunction. The lack of objective edema and normal serum tryptase levels during episodes also support this diagnosis.
- S4 rejected:
  - [other] Mast Cell Activation Syndrome: Normal serum tryptase levels during acute events do not support this diagnosis
  - [other] Idiopathic Anaphylaxis: The patient's symptoms and lack of objective edema are not typical of anaphylaxis
  - [other] Eosinophilic Esophagitis: The patient's symptoms are not primarily gastrointestinal and do not support this diagnosis
  - [other] Autoimmune Angioedema: Normal complement levels and lack of objective edema do not support this diagnosis

## B06 (code=`b06_ok` locus=`supervisor_ok`)
- supervisor: ['Factitious disorder', 'Somatoform disorder']
  clusters: {'gold': 1, 'near': 1, 'other': 0, 'empty': 0}
- discussion labels (n=15): ['Factitious disorder', 'Anaphylaxis', 'Induced anaphylaxis', 'Hereditary angioedema', 'Somatoform disorder', 'Factitious disorder', 'Somatoform disorder', 'Induced anaphylaxis']
- votes=3 turns=3

## B07 (code=`b07_ok` locus=`diagnose_ok`)
- draft: ['Factitious Disorder Imposed on Self', 'Somatoform Disorder']
- diagnose: ['Factitious Disorder Imposed on Self', 'Somatoform Disorder']
- queries: ['A 14-year-old Caucasian girl was transferred from a community emergency department after treatment for presumed anaphylaxis following ingestion of a hypoallergenic nutritional supplement. Immediately ', 'differential diagnosis A 14-year-old Caucasian girl was transferred from a community emergency department after treatment for presumed anaphylaxis following ingestion of a hypoallergenic nutritional supplement. Immediately ', 'clinical manifestations diagnosis  supportive history of reaction with ingestion. Testing for hereditary angioedema and baseline serum tryptase were normal. She had lost 40 lb over the past year']

## B01 (code=`b01_ok` locus=`gen_ok`)
- top2: ['Factitious disorder', 'Munchausen syndrome']
- queries: ['induction of anaphylaxis by hypoallergenic nutritional supplements', 'differential diagnosis of episodic perioral swelling and stridor', 'evaluation of factitious disorder in patients with suspected allergies', 'psychiatric comorbidities in patients with recurrent anaphylaxis-like episodes']
- n_chunks=12

## APHHM
_na_

