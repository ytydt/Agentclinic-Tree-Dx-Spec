# MCR / mcr_200b / case 287

- **gold**: Autoimmune hepatitis
- **layer**: `all_miss_but_recalled` · **layer_aphhm**: ``
- **correct**: e7=0 v0=0 B06=0 B07=0 B01=0 APHHM=
- **e7_locus**: `s3_hit_s4_miss` · **e7_fail_code**: `parent_vs_subtype`
- **mapper_rescue**: 0
- **alignment**: e7_s3_gold=1 e7_champ_cluster=other B06_sup_gold=1 B07_diag_gold=0 same_cluster_flip=0 true_entrance=0
- **APHHM**: locus=`na` code=`na` prune_e7_ok=0

## Vignette
A 45-year-old woman from Mexico presented with icteric sclerae, headache, and confusion. One month earlier, she had acute hepatitis A in Mexico with full recovery on supportive care. On arrival, her vital signs were normal. Examination showed altered mentation, icteric sclerae, jaundice, and asterixis. Laboratory studies revealed an ALT of 2869 U/L, AST 1469 U/L, total bilirubin 15.1 mg/dL (direct 6.2 mg/dL), INR 1.6, and ammonia 55 μmol/L; her MELD score was 22. Further evaluation showed ferritin 1657 ng/mL and IgG 2580 mg/dL. ANA, antimitochondrial antibody, antismooth muscle antibody, P-ANCA, C-ANCA, and anti–liver-kidney microsomal type 1 antibody were negative. Ceruloplasmin and alpha-1 antitrypsin levels were normal. Viral serologies revealed anti-HAV IgM positive; HEV IgG and IgM were positive but HEV RNA was undetectable. She denied use of herbal or alternative medicines. Abdominal ultrasound and CT scan showed no significant abnormalities.

What is the most likely diagnosis?

Options:
A. Autoimmune hepatitis
B. Relapsing hepatitis A considered
C. Hepatitis E virus coinfection considered
D. Wilson disease excluded
E. Alpha
F. Other autoimmune liver diseases excluded
G. None…

## Backbone e7

- S2 n=51 gold_rank=1
  - clusters: gold=1 near=14 other=36
- S3 shortlist (5):
  - [gold] Autoimmune hepatitis
  - [near] Viral hepatitis E
  - [other] Idiopathic acute liver failure
  - [other] Toxic liver injury
  - [near] Fulminant lymphocytic hepatitis
    - why_kept(Autoimmune hepatitis): Elevated IgG and ferritin levels, along with liver injury and encephalopathy
    - why_kept(Viral hepatitis E): Positive HEV IgG and IgM, recent travel to Mexico, and acute liver injury
    - why_kept(Idiopathic acute liver failure): Severe liver injury with encephalopathy and jaundice, without clear etiology
    - why_kept(Toxic liver injury): Recent history of hepatitis A and potential exposure to hepatotoxic substances
    - why_kept(Fulminant lymphocytic hepatitis): Severe liver injury with elevated ALT and AST, and potential for immune-mediated damage
- S4 champion: **Idiopathic acute liver failure** cluster=other jaccard=0.00
- S4 rationale: The patient's presentation with altered mentation, icteric sclerae, jaundice, and asterixis, along with elevated liver enzymes, bilirubin, INR, and ammonia, suggests severe liver dysfunction. The recent history of hepatitis A and negative viral serologies for other hepatitis viruses, as well as the absence of detectable HEV RNA, make viral hepatitis less likely. The negative autoantibody panel and normal ceruloplasmin and alpha-1 antitrypsin levels argue against autoimmune hepatitis and other specific liver diseases. The lack of evidence for toxic liver injury or fulminant lymphocytic hepatitis, combined with the patient's clinical presentation and laboratory findings, supports the diagnosis of idiopathic acute liver failure.
- S4 rejected:
  - [gold] Autoimmune hepatitis: Negative autoantibody panel
  - [near] Viral hepatitis E: Undetectable HEV RNA
  - [other] Toxic liver injury: No history of herbal or alternative medicine use
  - [near] Fulminant lymphocytic hepatitis: Lack of specific laboratory findings or histopathological evidence

## B06 (code=`b06_judge_miss` locus=`supervisor_hit_judge_miss`)
- supervisor: ['Relapsing Hepatitis A', 'Autoimmune Hepatitis']
  clusters: {'gold': 1, 'near': 1, 'other': 0, 'empty': 0}
- discussion labels (n=15): ['Autoimmune Hepatitis', 'Acute Viral Hepatitis', "Wilson's Disease", 'Hemochromatosis', 'Drug-Induced Liver Injury', 'Relapsing Hepatitis A', 'Autoimmune Hepatitis', 'Acute Viral Hepatitis']
- votes=3 turns=3

## B07 (code=`b07_draft_miss` locus=`draft_miss`)
- draft: ['Acute Liver Failure', 'Hepatitis E Virus (HEV) Infection']
- diagnose: ['Acute Liver Failure', 'Hepatitis E Virus (HEV) Infection']
- queries: ['acute liver failure causes', 'hepatitis A relapse', 'HEV infection complications', 'autoimmune hepatitis diagnosis']

## B01 (code=`b01_gen_miss` locus=`rag_hit_gen_miss`)
- top2: ['Acute liver failure', 'Relapsing hepatitis A']
- queries: ['acute liver failure causes', 'hepatitis A relapse vs other hepatitis infections', 'elevated ferritin and IgG in liver disease', 'autoimmune hepatitis vs viral hepatitis']
- n_chunks=12

## APHHM
_na_

