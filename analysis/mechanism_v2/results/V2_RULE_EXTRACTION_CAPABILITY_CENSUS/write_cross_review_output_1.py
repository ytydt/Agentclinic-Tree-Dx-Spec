"""Manual independent judgments for O1; initial labels are read only after frozen JSON exists."""
import json, hashlib
from pathlib import Path
P=Path(__file__).resolve().parent
PACK=json.loads((P/'output_pack_1.json').read_text())
J={}
def add(n,label,anchor,errors,rationale,source,output):
    J[f'O1-{n:03}']=dict(independent_label=label,ancestor_anchor=anchor,
                        errors=errors.split('|') if errors else [],rationale=rationale,
                        source_semantics=source,output_semantics=output)

add(1,'distorted','The following list contains the differential diagnoses for congenital amegakaryocytic thrombocytopenia:',
    'predicate_identity|relation_direction|group_membership_effect',
    'A list of diseases potentially explaining infant thrombocytopenia does not supply observations that distinguish the focus from those diseases. Every leaf has a source ancestor, but every relation invents a discriminator; ANY does not rescue it.',
    'Alternative etiologies are listed as differential diagnoses.',
    'The alternatives themselves are the findings distinguishing CAMT from each alternative, joined into one ANY group.')
add(3,'distorted','In some cases with cervical epidural abscesses, stiff neck, fever, and deltoid-biceps weakness',
    'scope_anatomic|scope_population',
    'The source restricts this pattern to some cervical cases. The raw group promotes the level-specific neurological pattern to typical undifferentiated spinal epidural abscess. No rigid AND is demanded for the ordinary manifestation list.',
    'Some cervical epidural abscesses have the listed neck/fever/deltoid-biceps presentation.',
    'ANY of those findings is a typical feature of generic spinal epidural abscess.')
add(5,'distorted','The most common cyanotic congenital heart defects are the five Ts:',
    'group_membership_effect|target_entity',
    'Each disease-specific atom is a defensible soft association, but the selected output unit is one group whose members have five independent subjects. The source makes five separate disease associations, not a common diagnostic criterion with an ANY effect shared across them.',
    'Five different congenital defects can produce cyanosis.',
    'Five different disease targets share a single ANY group, each with cyanosis as predicate.')
add(8,'faithful','Early symptoms are nonspecific, including headache, nausea, vomiting, and vertigo.',
    '',
    'All four nonspecific manifestations and the correct meningovascular subtype are retained as soft alternatives. No required_for/sufficient_for claim is made. Early timing is absent from the predicates, but the output association does not claim they are exclusive to another stage. Reconstructed quotes are a separate contract problem.',
    'Meningovascular neurosyphilis can have headache, nausea, vomiting and vertigo as nonspecific early symptoms.',
    'ANY of those four symptoms is a typical meningovascular-neurosyphilis feature.')
add(9,'faithful','Symptoms such as headache, dizziness, visual impairments, weakness, convulsions, speech, or personality changes can occur.',
    '',
    'The complete source symptom list is preserved as non-obligatory alternatives with a common feature relation. This does not assert that every tumor is symptomatic or that one symptom confirms meningioma.',
    'Meningioma may produce any of the listed symptoms according to location.',
    'The seven source symptoms are an ANY group of typical Meningioma features.')
add(11,'unresolved_provenance','• Interstitial lung disease',
    'provenance_subject|source_hierarchy',
    'The only available same-document window is this bare list. Every finding is traceable, but the disease/subtype binding cannot be independently established from the body. The supplied StatPearls title names C1, yet these titles are known bibliography-derived metadata in this repository. Without the real article context I cannot certify fidelity or prove a wrong subtype. This is not untraceable fabrication.',
    'A truncated list contains eight pulmonary/hematologic/lipid/bone manifestations with no disease name in the text.',
    'All eight are attributed to Niemann-Pick Disease Type C1 as one ANY feature group.')
add(15,'faithful','In addition to normal platelet size, small, large, and giant platelets may be seen in peripheral smear',
    '',
    'The grouped output makes three true alternative abnormal-size associations, not a necessary rule excluding normal-sized platelets. The absence of a normal-size output affects source coverage; it does not contradict these non-obligatory output features.',
    'Hereditary thrombocytopenia can have normal, small, large or giant platelet sizes.',
    'Small, large and giant platelets form a soft ANY group for hereditary thrombocytopenia.')
add(17,'faithful','CCHD can be further classified into 3 different types of lesions:',
    '',
    'The three lesion-type alternatives are preserved with a single disease target. This is a source-grounded anatomic-category association set, not a sufficient diagnosis test. Any concern that the source conflates critical and cyanotic CHD must be audited as a source claim rather than silently corrected by the reviewer.',
    'The supplied source classifies cyanotic/critical CHD into right-obstructive, left-obstructive and mixing lesions.',
    'The three source lesion classes are an ANY typical-feature group of Cyanotic congenital heart disease.')
add(25,'distorted','released guidelines on withholding resuscitation in trauma patients',
    'non_diagnostic_task|scope_population|scope_time|target_effect|group_membership_effect',
    'The group copies a real conjunction but strips its penetrating-trauma population, EMS-arrival time and withholding-resuscitation consequent. It therefore becomes diagnostic feature evidence for generic Trauma. Negative findings retained as negative noun phrases are not themselves polarity reversals here.',
    'Withholding resuscitation may apply to penetrating-trauma patients found pulseless/apneic and without the specified signs of life on EMS arrival.',
    'The findings become an ALL group of typical Trauma features.')
add(27,'faithful','requiring 2 of 3 of the following:',
    '',
    'This flat group preserves the complete three-member domain, count 2, common target and shared required_for effect. Group-level interpretation makes two-of-three necessary; interpreting every member as individually required would be executor contamination. The usually-symmetric qualifier is typical rather than an absolute branch condition. The later updated criteria are a separate source claim.',
    'The described working-group DLB criteria require two of parkinsonian syndrome, behavioral/cognitive fluctuations, and recurrent hallucinations.',
    'at_least_n=2 over exactly those three members, all required_for Dementia with Lewy Bodies.')
add(29,'faithful','Classic examination findings include abdominal distension, high-pitched or absent bowel sounds, tenderness, and a tympanic abdomen.',
    '',
    'This is an ordinary soft feature list, not a mandatory conjunction. High-pitched and absent bowel sounds are correctly treated as alternative features; none is claimed necessary or sufficient. Keeping absent inside the predicate preserves the literal meaning, although it conflicts with the prompt’s preferred polarity encoding.',
    'Intestinal obstruction may have the listed classic abdominal signs, including either high-pitched or absent bowel sounds.',
    'Five feature observations, with the bowel-sound alternatives split, share an ANY group.')
add(33,'faithful','impaired pulmonary function',
    '',
    'The source explicitly says impaired pulmonary function is shared by COVID-associated lung injury and HAPE. The output claims only the positive feature for COVID injury, not discrimination.',
    'COVID-associated lung injury has impaired pulmonary function among manifestations shared with HAPE.',
    'Impaired pulmonary function is a typical COVID-associated lung injury feature.')
add(52,'distorted','• Malignancy',
    'predicate_identity|relation_direction',
    'The differential list names Malignancy but supplies no discriminating finding. Replacing the missing finding with presence does not create a source-grounded contrastive clinical rule. The label has a clear list ancestor.',
    'Malignancy is listed among alternatives in the stercoral-colitis differential section.',
    'Presence is a typical Malignancy finding that distinguishes it from stercoral colitis.')
add(67,'faithful','presents as fever, anorexia, ascites, and abdominal pain',
    '',
    'Ascites is an explicit manifestation of the exact tuberculous-peritonitis target. The reconstructed quote is not verbatim but has an unambiguous source ancestor.',
    'Tuberculous peritonitis may present with ascites.',
    'Ascites is a typical feature of tuberculous peritonitis.')
add(85,'distorted','ADFK shares clinical and histologic features with other cutaneous conditions',
    'predicate_identity|relation_direction',
    'The source makes a similarity/differential-difficulty claim without naming the overlapping findings. The output turns the unspecific phrase clinical and histologic features into the finding itself, losing the only asserted relation. It is traceable distortion, not pure hallucination.',
    'ADFK shares unspecified clinical and histologic features with other skin conditions, necessitating examination.',
    'Clinical and histologic features is itself a typical ADFK finding.')
add(89,'faithful','solitary, soft to firm, skin-colored subcutane-ous nodules',
    '',
    'The correctly resolved MFH paragraph directly describes solitary subcutaneous nodules. The output is a true non-obligatory component feature, even though it does not include all age/site/texture details.',
    'Malignant fibrous histiocytoma is described as presenting with solitary subcutaneous nodules.',
    'Solitary subcutaneous nodule is a typical MFH sign.')

def freeze():
    selected={s for s in json.loads((P/'review_selection.json').read_text())['output'] if s.startswith('O1')}
    selected|={f'O1-{n:03}' for n in [8,9,15,17,27,29]}
    assert set(J)==selected
    out=[]
    for u in PACK:
        if u['sample_id'] not in J: continue
        d=J[u['sample_id']]
        assert d['ancestor_anchor'] in u['text'],(u['sample_id'],d['ancestor_anchor'])
        out.append(dict(sample_id=u['sample_id'],unit_id=u['unit_id'],**d,
                        raw_indices=[r['raw_index'] for r in u['rows']],
                        reviewer='output_adjudication_2_independent_cross_review',
                        initial_adjudication_file_unread_before_freeze=True,
                        selection_disclosed_initial_faithful_label=u['sample_id'] in {f'O1-{n:03}' for n in [8,9,15,17,27,29]},
                        provenance_search={'scope':'full_input_and_all_available_same_doc_windows' if u['sample_id']=='O1-011' else 'full_input',
                                           'doc_windows_checked':1,
                                           'reason':'One and only available same-doc window checked; subtype subject unresolved.' if u['sample_id']=='O1-011' else 'Named source ancestor found within full input.'}))
    path=P/'independent_cross_review_output_1.json'
    path.write_text(json.dumps(out,indent=2,ensure_ascii=False)+'\n')
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    (P/'independent_cross_review_output_1.sha256').write_text(digest+'  '+path.name+'\n')
    print(json.dumps({'n':len(out),'sha256':digest,'labels':{k:sum(x['independent_label']==k for x in out) for k in {x['independent_label'] for x in out}}}))

if __name__=='__main__':freeze()
