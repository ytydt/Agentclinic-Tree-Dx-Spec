"""Transcribe paired source-rule adjudications after source inventory hash freeze."""
import hashlib
import json
from collections import Counter
from pathlib import Path

B = Path(__file__).resolve().parent
FROZEN_SHA256 = '733e635786904e710407687ddd0d627407cd4fb4b5f3757470df2b8f10739f71'
inventory_bytes = (B/'source_inventory_3.json').read_bytes()
assert hashlib.sha256(inventory_bytes).hexdigest() == FROZEN_SHA256
inventory = json.loads(inventory_bytes)
reveal = {x['sample_id']: x for x in json.loads((B/'source_reveal_pack_3.json').read_text())}
source = {x['sample_id']: x for x in json.loads((B/'source_only_pack_3.json').read_text())}
R = {r['rule_id']: r for x in inventory for r in x['rules']}
judgments = {}

REL = {'feature_of','required_for','sufficient_for','pathognomonic_for','excludes','argues_against','distinguishes_from','variant_of','synonym_of','caused_by','treated_by'}
MOD = {'obligatory','typical','frequent','occasional','rare'}
CTX = {'definition','criteria','differential','histopathology','imaging','epidemiology','treatment','prognosis','table_row','other'}
KINDS = {'symptom','sign','lab','imaging','histopathology','ecg','hemodynamic','exposure','demographic','course','other'}

def schema_warnings(sid, arm, idx):
    out=[]
    for i in idx:
        a = reveal[sid]['outputs'][arm]['output']['assertions'][i]
        for key, allowed in [('relation',REL),('modality',MOD),('context_type',CTX),('predicate_kind',KINDS)]:
            if a.get(key) not in allowed:
                out.append(f'raw[{i}] {key}={a.get(key)!r} outside advertised enum; legality is separate from semantic label')
        if a.get('quote') not in source[sid]['text']:
            out.append(f'raw[{i}] quote not verbatim in supplied window; recognizable provenance is not thereby erased')
        if a.get('comparator') and a.get('relation') not in {'distinguishes_from','argues_against'}:
            out.append(f'raw[{i}] comparator populated outside advertised relation scope')
    return out

def setj(rid, arm, label, idx=(), errors=(), rationale='', causes=None):
    sid=rid.rsplit('-R',1)[0]
    idx=list(idx)
    if causes is None:
        if label=='distorted':
            causes=[dict(cause='prompt underspecification', evidence_level='C',
                         rationale='The prompt enumerates fields but incompletely specifies the relevant scope, direction or full-coverage invariants. This is a compatible explanation, not a controlled prompt-versus-model attribution.'),
                    dict(cause='model violated clear instruction', evidence_level='C',
                         rationale='Mismatch is directly visible in raw output against the available source, but model comprehension, focus preference and prompt framing were not causally isolated.')]
        elif label=='omitted':
            causes=[dict(cause='prompt underspecification', evidence_level='C',
                         rationale='The instruction says extract every assertion while preferring the focus disease and requests short noun phrases. Focus selection/compression is compatible with omission, but no controlled intervention isolates its cause.')]
        elif label=='ambiguous_source':
            causes=[dict(cause='source structure/ambiguity', evidence_level='A',
                         rationale=R[rid]['scope'])]
        else:
            causes=[]
    judgments[(rid,arm)] = dict(label=label, raw_indices=idx, errors=list(errors),
                               schema_errors=schema_warnings(sid,arm,idx),
                               first_damage='source_window' if label=='ambiguous_source' else ('none_observed' if label=='faithful' else 'raw_output'),
                               causes=causes, rationale=rationale)

def both(rid,label,oldidx=(),newidx=None,errors=(),rationale='',causes=None):
    setj(rid,'old',label,oldidx,errors,rationale,causes)
    setj(rid,'new',label,oldidx if newidx is None else newidx,errors,rationale,causes)

# Start with an explicit full-call omission adjudication for every frozen unit.
# Every non-omitted recognizable descendant is then recorded below.
for rid,r in R.items():
    for arm in ['old','new']:
        if r['source_status']=='ambiguous_source':
            setj(rid,arm,'ambiguous_source',rationale='Frozen source ambiguity remains unresolved after reveal. No unique clinical proposition is manufactured to judge extraction against. '+r['source_semantics'])
        else:
            setj(rid,arm,'omitted',rationale=f"The complete {arm} call was read. No identifiable descendant expresses this {r['rule_kind']} claim about {r['target']}. Merely naming a target, test or nearby item without this assertion was not counted as coverage.")

both('S3-01-R01','distorted',[0],[0],
     ['target/entity','scope/population/time/exception','partial'],
     'The only limb-weakness wording in the source belongs to FND. Old attaches limb/facial weakness to compression neuropathy; new attaches limb weakness to radial compression neuropathy. Both discard fluctuation, evolution and stress and replace the disease subject. The short new quote cites the compression-neuropathy clause, but does not supply limb weakness; the surrounding FND clause is the recognizable ancestor.')

both('S3-02-R01','distorted',[0],[0],
     ['predicate identity','scope/population/time/exception','partial'],
     'The source gives a conditional supportive role for routine awake EEG without naming an EEG finding. Both outputs invent abnormal EEG as the finding and drop clinical-suspicion/awake-test scope and classification-information component. The extra relation supports is semantically intelligible but not in the advertised enum; that enum issue alone does not determine the distorted label.')
both('S3-02-R02','distorted',[1],[1],
     ['relation direction','negation scope','literal polarity','predicate identity'],
     'Do not use EEG to exclude epilepsy negates the validity of an exclusion inference. Both outputs instead have relation=excludes and polarity=negated attached to predicate normal EEG. Under the prompt polarity explicitly negates the finding, not the relation; this does not encode NOT(exclusion). Normal EEG is also more specific than the supplied prohibition.',
     causes=[dict(cause='schema unrepresentable',evidence_level='A',rationale='The schema has literal polarity but no relation-level negation, test non-exclusion relation or NOT node. A negated excludes relation cannot be encoded simply by negating its finding.'),
             dict(cause='prompt underspecification',evidence_level='C',rationale='Polarity is defined for feature absence, but no non-exclusion example is provided. Raw misuse is established; which prompt/model mechanism caused it is unisolated.')])

both('S3-03-R05','distorted',[0,1,2,6],[0,1],
     ['target/entity','scope/population/time/exception','nesting/branch','partial'],
     'Source subject is infection-related gram-negative bacteremia; both outputs replace it by the focus Gram-negative bacillary infection. Old splits skin and decubitus ulcers into independent typical features; new drops the ulcer qualifier entirely. GU/GI origin survives, but the skin-branch modifier and bacteremia scope do not.')
both('S3-03-R06','distorted',[3,4],[2,3],
     ['target/entity','scope/population/time/exception'],
     'The two risk populations are recovered, more explicitly as increased risk in new, but their target has broadened from gram-negative bacteremia to generic Gram-negative bacillary infection. Old relation exposure is outside the enum; new fixes that contract issue without fixing the target.')
setj('S3-03-R10','old','distorted',[5],
     ['target/entity','relation direction','scope/population/time/exception'],
     'Most likely gram-negative bacillus GIVEN bacteremia caused by an abdominal infection becomes generic Gram-negative bacillary infection caused_by abdominal infection. The bacteremia condition and conditional organism-distribution direction are lost.')
setj('S3-03-R13','new','distorted',[5],
     ['target/entity','relation direction','scope/population/time/exception','partial'],
     'The endocarditis consequence has a recognizable ancestor in the repeated bacteremia/endocarditis discussion, but is reversed into Gram-negative bacillary infection caused_by endocarditis. Source relative enterococcal/streptococcal/staphylococcal versus gram-negative/fungal frequencies are absent.')
setj('S3-03-R14','new','distorted',[5],
     ['target/entity','relation direction','scope/population/time/exception','partial'],
     'The raw quote specifically includes valvular-heart predisposition, also inventoried in this risk set, but its structured fields drop that risk and reverse endocarditis into a cause of the focus infection. Prostheses, injection-drug context and possible tricuspid involvement are omitted.')

both('S3-04-R01','faithful',[0,1],rationale='Two ungrouped atoms jointly retain the brief definition: neurocognitive disorder and compromised daily living, with the correct dementia subject. No sufficient threshold or necessary symptom list has been invented.')
both('S3-04-R02','distorted',[3],errors=['predicate identity','partial'],
     rationale='The output predicate is merely prevalence with advancing age; higher/increasing is absent from structured fields. The correct comparative direction exists only in quote, so the operational relation is an unspecified age association rather than the frozen increasing-prevalence claim.')

both('S3-05-R01','distorted',[1,2],errors=['scope/population/time/exception'],
     rationale='Both imaging findings are recovered as feature_of, but the very-early-stage qualifier and CT scope are removed. New fixes context_type from epidemiology to imaging without restoring the time-qualified rule.')
both('S3-05-R02','distorted',[3,4],errors=['scope/population/time/exception'],
     rationale='Bone destruction and sequestra survive as separate features, but their later-stage qualifier is removed. This creates unqualified evidence rather than a faithful late-stage finding set. Nonverbatim quotations are a separate contract warning, not fabrication.')
both('S3-05-R03','distorted',[5,6,8],[5,6,7],
     ['partial','target/entity','scope/population/time/exception'],
     'Abscess/phlegmon descendants exist, but inflammatory extension and cord-compression linkage are absent. An additional abscesses atom is reassigned to focus Spinal Epidural Abscess from the same general infection passage. The bundle is partial plus a target-shifted descendant.')
both('S3-05-R04','faithful',[7],[8],rationale='Calcifications are correctly bound to tuberculous spondylodiscitis as weak feature evidence. Neither arm upgrades them to sufficient_for/pathognomonic_for. Old context_type epidemiology is inaccurate descriptive metadata, while predicate_kind and content remain imaging; this warning does not itself alter the truth conditions.')
judgments[('S3-05-R04','old')]['schema_errors'].append('raw[7] context_type=epidemiology misclassifies imaging metadata; semantic supporting claim remains intact')

both('S3-06-R01','distorted',range(5),errors=['partial','scope/population/time/exception'],
     rationale='Five correct myxofibrosarcoma atoms survive, but malignant fibroblastic nature, fibrous regions, whorled pattern and source low-grade characterization are missing. Varying pleomorphism is flattened. Partial feature coverage is distorted, not complete omission or full fidelity.')
both('S3-06-R03','distorted',[5],errors=['target/entity','partial'],
     rationale='The raw quote is the vimentin-to-mesenchymal-origin claim, but the subject becomes Fibrosarcomas and the finding is only vimentin. It does not preserve the cell-origin inference. The same atom is also a partial descendant of the neighboring fibrosarcoma staining-pattern rule.')
both('S3-06-R04','distorted',[5],errors=['cardinality n/domain/distinctness','partial'],
     rationale='Vimentin as a fibrosarcoma feature survives, but often the only positively stained marker becomes just a typical unqualified marker. The exclusivity over the stain domain is absent.')
both('S3-06-R05','distorted',[6,7,8],errors=['target/entity','relation strength','partial'],
     rationale='The three markers survive but are assigned to Fibrosarcomas rather than the source myofibroblastic-differentiation interpretation. Old occasional/new typical differ without a direct source change. Neither output represents the lineage inference.')
both('S3-06-R06','distorted',[9,16],[9,13],
     ['relation direction','relation strength','literal polarity','mixed_correct_and_wrong'],
     'Correct S100 feature evidence for nerve-sheath tumor is accompanied by a same-quote transformed descendant saying negated S100 excludes fibrosarcoma. The latter reverses finding polarity and invents a rigid alternative-diagnosis exclusion. Thus this source rule has mixed correct and wrong descendants.')
both('S3-06-R07','faithful',[10,11,12],rationale='All three vascular markers are retained as separate weak feature_of atoms with correct vascular-tumor target. The source panel supplies no all-positive necessity/cardinality; faithfully representing these weak associations does not require an invented group.')
both('S3-06-R08','distorted',[13,14,15],[14,15,16],
     ['relation direction','relation strength','literal polarity'],
     'Positive vascular-marker evidence favors vascular tumor rather than fibrosarcoma. Both arms encode negative-marker excludes fibrosarcoma, combining polarity inversion with promotion of comparative evidence into hard exclusion. The comparator-filled excludes records also violate the advertised comparator contract.')

both('S3-07-R01','distorted',[0,1],[0,1],
     ['target/entity','scope/population/time/exception','partial'],
     'High pulmonary pressures are only emitted under PAH/IPAH subtype subjects. These inherited subtype facts are compatible with the source, but the general PH definition is restricted to those subtypes, leaving its broader target uncovered. New also downgrades the definition modality from obligatory to typical.')
both('S3-07-R03','distorted',[2,7],[2,3,4],
     ['group membership/effect','scope/population/time/exception','partial'],
     'Old emits the test name without result and invents a distinguishes_from PH-LHD comparison. New recovers responder/nonresponder words but labels both as typical IPAH features instead of alternative named subclasses conditional on IPAH. No response-subtype mapping survives; this is not an all-positive clinical criterion.')
setj('S3-07-R04','old','distorted',[3],['partial','nesting/branch'],
     'The PH-LHD caused_by left-heart-disease head is correct, but the frozen category definition also includes heart-failure EF branches, valvular and congenital/acquired postcapillary categories; all branches disappear. This is partial taxonomy coverage, not incorrect causal direction.')
setj('S3-07-R05','old','distorted',[4],['connective','partial','scope/population/time/exception'],
     'Source lung disease OR hypoxia OR both becomes only lung diseases caused_by with obligatory modality, losing the hypoxia-without-lung-disease branch and the remaining subtype branches.')
setj('S3-07-R06','old','distorted',[5],['partial','nesting/branch'],
     'The causal obstruction head is correct, but chronic-thromboembolic versus other-obstruction subtypes are omitted. Kept as partial under the pre-frozen category-level unit; sensitivity analysis should separate taxonomy units.')
setj('S3-07-R07','old','distorted',[6],['partial','nesting/branch'],
     'Unclear OR multifactorial mechanism wording survives, but all associated disease categories and renal-failure dialysis alternatives disappear. Kept as partial under the pre-frozen taxonomy unit.')

both('S3-08-R01','distorted',[17,18,19],[17],
     ['relation strength','scope/population/time/exception','partial'],
     'The clinical sun-exposed-site/risk association is replaced by UV exposure caused_by. Old additionally promotes XP and Li-Fraumeni correlations to causes; new drops those syndrome associations. Neither arm preserves sun-exposed lesion site plus the complete weak risk set.')
both('S3-08-R03','distorted',[21],[19],
     ['relation direction','literal polarity','relation strength','scope/population/time/exception'],
     'A single-study absence of H/K-Ras mutations in AFX becomes negated mutations excludes AFX. This uses missing mutation as exclusion, loses one-study/exploratory scope and promotes a reported pattern to a rigid relation.')
both('S3-08-R04','distorted',range(6),errors=['partial','scope/population/time/exception','relation strength'],
     rationale='Several morphology atoms are correct, but dermal location and occasional subcutis extension are absent, peripheral inflammatory-infiltrate location is dropped and may/frequency qualifiers become typical. This is partial feature-set recovery.')
setj('S3-08-R05','old','distorted',[22],['predicate identity','target/entity','partial'],
     'The named spindle-SCC comparator survives as a disease-name predicate attached to AFX, but neither epidermal connection nor keratinization is extracted. This source differential ancestor is recognizable, yet the actual distinguishing features have disappeared.')
both('S3-08-R06','distorted',[22,23,24],[20],
     ['group membership/effect','relation strength','partial','scope/population/time/exception'],
     'The complete AFX histologic diagnosis-of-exclusion requirement is reduced to comparator names in old and the word immunohistochemistry under UPS in new. None encodes adequate exclusion of an open-ended competing-neoplasm domain, and neither states the group-level necessary effect.',
     causes=[dict(cause='schema unrepresentable',evidence_level='A',rationale='Flat member groups cannot represent open-domain adequate exclusion, relation-level group necessity, nested alternative differential branches, or the NOT node required to state exclusions of competing diagnoses.'),
             dict(cause='prompt underspecification',evidence_level='C',rationale='Neither prompt provides an exclusion-diagnosis compilation example or requires preserving open-domain scope. Which prompt/model effect produced these particular fragments is unisolated.')])
both('S3-08-R07','faithful',range(6,11),rationale='Every named positive stain survives as an ungrouped weak feature_of atom with the correct AFX target. No stain is upgraded to sufficient/pathognomonic or required_for. This weak representation is consistent with source nonspecific positive associations; it does not need an all-of group.')
both('S3-08-R08','distorted',range(11,17),errors=['relation direction','relation strength','literal polarity','numeric comparator/value/unit'],
     rationale='Each source negative stain is encoded as excludes plus negated, making the negative finding an exclusion trigger rather than an AFX feature. Sparse S100 is additionally converted into categorical absence. Full marker-name coverage therefore coexists with deeply wrong diagnostic effects.')

both('S3-10-R01','distorted',[4,5,6],[8,9,10,11],
     ['scope/population/time/exception'],
     'Macular/nodular alternatives, pigmentation and numeric 2–6 cm range are recovered without rigid necessity. However, the range is attached to all mucosal melanomas, losing the source oral-cavity restriction. The new split into ungrouped weak macular/nodular atoms is not itself an AND error.')
both('S3-10-R02','distorted',[0,1,2,3],range(8),
     ['partial','scope/population/time/exception','relation strength'],
     'Old recovers morphology but omits focal/widespread distribution and all possible sites. New adds all four sites, yet marks optional involvement as typical and still omits distribution from the structured predicates. The correct distribution in quote alone is not executable coverage. Added raw atoms improve member recall without completing the source set.')
both('S3-10-R03','distorted',[7,8],[12,13],
     ['partial','scope/population/time/exception','literal polarity'],
     'Painless submucosal mass and cervical nodes survive, but the hard/soft palate junction and absence of ulceration disappear. Subject NHL also loses the palatal presentation scope. Omission of one negative feature within a surviving set is partial distortion, not a whole omitted rule.')
both('S3-11-R01','faithful',[2],rationale='Female predominance is explicit in the predicate and remains weak feature_of/typical under the correct PAH subject. Unsupported context_type pathophysiology is a contract warning; it does not change this demographic claim.')

setj('S3-13-R03','old','distorted',[1],['predicate identity','numeric comparator/value/unit','partial'],
     'Only the generic noun phrase anatomic site survives, with extremity relegated to quote; no site value or percentage is in structured fields. Other sites/frequencies are missing.')
setj('S3-13-R05','old','distorted',[0,3],['predicate identity','group membership/effect','partial'],
     'The MFH reclassification descendant contains only classification as predicate; actual alternatives reside solely in quote. A second descendant picks the UPS name and attaches empty origin. No source reclassification relation or condition survives.')
setj('S3-13-R05','new','distorted',[3],['relation direction','relation strength','nesting/branch','scope/population/time/exception'],
     'The four alternative labels now appear in structured predicate, but relation=synonym_of turns conditional historical reclassification based on differentiation/genetics into synonymy. More source words are present while entity semantics worsen.')
both('S3-13-R07','distorted',[4],[4],
     ['partial','predicate identity','scope/population/time/exception'],
     'Old writes only age distribution, with adult value in quote; new drops the age association entirely and keeps only different biology versus embryonal/alveolar RMS. Both are partial descendants of the frozen adult-predominance/biology-distinction rule.')

setj('S3-14-R02','old','distorted',[1],['target/entity','scope/population/time/exception'],
     'Paravertebral mass indicates an abscess in the local spinal-infection context. Old attaches it as a typical feature of tuberculous spinal infection, selecting the later TB qualifier as the disease target and dropping the abscess interpretation.')
both('S3-14-R05','faithful',[0,6],[0,1],rationale='Two atoms preserve Pott disease, tuberculous spinal infection as its cause, and kyphotic deformity as its feature. The frozen source is a textual causal description, not an explicitly sufficient all-of decision criterion; no group is required merely to claim these two faithful linked disease attributes. There is no rival mislabeled descendant of this definition in either arm.')
setj('S3-14-R06','new','faithful',[3],rationale='Staphylococcal infection is correctly captured as the typical cause of spinal epidural abscess, preserving most-often scope without excluding other causes.')
both('S3-14-R08','distorted',[2,3,4,5],[4,5,6],
     ['scope/population/time/exception','partial'],
     'Old packages the main symptom set plus optional radicular radiation into one any group. New changes to all over three main features. Because every member remains feature_of/typical, all by itself need not assert disease necessity: it may describe a soft joint pattern. The definite distortions are that both omit percussion/pressure provocation, old loses the explicitly optional radiation modality, and new drops that optional source member entirely. Label does not depend on treating an all group as hard exclusion or a necessary disease criterion.',
     causes=[dict(cause='prompt underspecification',evidence_level='C',rationale='Neither block requires retaining every feature modifier, optional branch or pain-provocation scope when splitting a descriptive list. Scope/coverage loss is visible in raw output; its prompt-versus-model cause remains unisolated.'),
             dict(cause='model violated clear instruction',evidence_level='C',rationale='The source supplies all modifiers and the optional radicular branch while the extraction requests every assertion. Exact scope-loss mechanism is unisolated; homogeneous soft grouping alone is not evidence of model semantic failure.')])
for arm in ['old','new']:
    judgments[('S3-14-R08',arm)]['schema_errors'].append('g1 has homogeneous feature_of/typical members and no explicit group effect. This is an implicit-effect contract warning, not by itself proof of a hard necessity/exclusion error.')

both('S3-15-R01','distorted',[0,1],[0,2],
     ['relation strength','relation direction','negation scope','literal polarity'],
     'Documented transmission through corneal grafts is labeled obligatory, and unknown blood transmission becomes excludes with negated blood-transmission feature. Unknown is neither proven absence nor exclusion. New replaces out-of-enum unknown modality by occasional without restoring epistemic uncertainty.')
both('S3-15-R02','distorted',[2],[1],
     ['scope/population/time/exception','relation strength','partial'],
     'The non-leukodepleted blood qualifier survives. Old incorrectly attaches theoretical modality to the transfused-blood route even though theoretical modifies transplant-recipient risk; new uses typical and still loses theoretical transplant scope. The invalid old enum is not the sole reason for distortion.')
setj('S3-16-R02','old','ambiguous_source',[0],['predicate identity'],
     'The frozen list hierarchy remains ambiguous. Old emits a self-referential Gingival hyperplasia feature_of Gingival hyperplasia, which does not recover any drug/leukemia relationship. The tautology is recorded, but a unique causal source rule is not invented to label it distorted or omitted.')

rows=[]
for item in inventory:
    for r in item['rules']:
        rid=r['rule_id']
        rows.append(dict(sample_id=item['sample_id'],rule_id=rid,
                         old=judgments[(rid,'old')],new=judgments[(rid,'new')],
                         reviewer='source_inventory_3_AI_after_source_hash_freeze'))
assert len(rows)==74
for row in rows:
    for arm in ['old','new']:
        v=row[arm]
        assert v['label'] in {'faithful','distorted','omitted','ambiguous_source'}
        assert all(0<=i<len(reveal[row['sample_id']]['outputs'][arm]['output']['assertions']) for i in v['raw_indices'])
        assert v['label']!='omitted' or not v['raw_indices']
        assert v['label']!='faithful' or (v['raw_indices'] and not v['errors'])
(B/'source_matches_3.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({arm:dict(Counter(x[arm]['label'] for x in rows)) for arm in ['old','new']},indent=2))
print('inventory_hash_unchanged',hashlib.sha256((B/'source_inventory_3.json').read_bytes()).hexdigest()==FROZEN_SHA256)
