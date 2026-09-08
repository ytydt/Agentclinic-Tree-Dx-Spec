#!/usr/bin/env python3
"""Finite synthetic witnesses against the unmodified legacy run_case.

No API, embeddings, clinical data invention, or production changes. Expected
legacy output assertions establish a defect witness, not a corrected engine.
"""
from __future__ import annotations
import copy, gzip, hashlib, importlib.util, json, math, subprocess
from collections import Counter, defaultdict
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
ENGINE=HERE.parent/'RAG_GUIDELINE_ORACLE_CEILING_LOCAL/run_mechanical_engine.py'
spec=importlib.util.spec_from_file_location('legacy_engine_defect_probe',ENGINE)
e=importlib.util.module_from_spec(spec); spec.loader.exec_module(e)
DEFAULT={k:copy.deepcopy(getattr(e,k)) for k in (
'JOIN_MODE','DISCRIMINATIVE_ONLY','WEIGHT_SCHEME','USE_CRITERION_GROUPS','CLOSED_WORLD',
'FIX_MARKER','FIX_EMBED_TAU','FIX_ORGANISM','FIX_ENUM','CORPUS_LR','FIX_ANCHOR_EMBED',
'GROUP_ALL_IS_REQUIRED','FIX_QUOTE_GATE','RIGID_REQUIRED_ANY_MODALITY','RIGID_SUFFICIENT_CONFIRMS',
'RIGID_PATHO_READS_THRESHOLD','RIGID_REQUIRED_CLOSED_WORLD','FIX_NLI','NONCRITERION_INERT',
'FINDING_POOL_BETA','LAYER3_DROP')}
WITNESSES=[]
def a(p='redsignal',**kw):
    row={'subject':'DiseaseAlpha','predicate':p,'predicate_kind':'sign','relation':'feature_of',
         'polarity':'asserted','modality':'obligatory','threshold':{},'comparator':None,
         'context_type':'criteria','criterion_group':{'group_id':None,'logic':None,'n':None},
         'quote':'Synthetic signal rule; no medical claim.','_title':'Synthetic document',
         '_section':'Synthetic section','_focus':'DiseaseAlpha'}
    row.update(kw); return row

def g(p,gid='g1',logic='all',n=None,**kw):
    return a(p,criterion_group={'group_id':gid,'logic':logic,'n':n},**kw)
def f(p='redsignal',polarity='present',number=None,unit=None,**kw):
    row={'label':p,'canonical':p,'polarity':polarity,'value':{'number':number,'unit':unit}}
    row.update(kw); return row

def run(rows,facts,labels=None,**cfg):
    for k,v in DEFAULT.items(): setattr(e,k,copy.deepcopy(v))
    e.USE_CRITERION_GROUPS=True
    for k,v in cfg.items(): setattr(e,k,v)
    labels=labels or ['DiseaseAlpha','DiseaseBeta']
    task={'case_key':'synthetic/engine','gold':'not_applicable','gold_labels_in_set':[],
          'candidates':[{'label':x,'aliases':[],'gold_match':False,'methods':[]} for x in labels]}
    return e.run_case(task,{'assertions':copy.deepcopy(rows),'findings':copy.deepcopy(facts)})

def v(result,label='DiseaseAlpha'):
    return next(x for x in result['ranking'] if x['label']==label)
def slim(result):
    return {'ranking':result['ranking'],'pairs':result['pairs'],
            'n_assertions_bound':result['n_assertions_bound'],'join_stats':result['join_stats']}
def add(id,defects,title,observed,check,semantics,scope='synthetic_real_function'):
    assert check, (id,observed)
    WITNESSES.append({'id':id,'defect_ids':defects,'title':title,'scope':scope,
                     'observed':observed,'required_invariant':semantics,'legacy_witness_passed':True})

def synthetic():
    r=run([g('redsignal','g1',_passage_sha1='first'),g('bluesignal','g1',_passage_sha1='first'),
           g('greensignal','g1',_passage_sha1='second'),g('yellowsignal','g1',_passage_sha1='second')],
          [f('redsignal'),f('bluesignal')])
    add('S01',['ENG-01'],'Different passage-local roots collide',slim(r),
        v(r)['contributions'][0]['n_members']==4,
        'Two source occurrences remain two roots even if local gid/title/section/focus/subject coincide.')
    r=run([g('redsignal',subject='DiseaseAlpha (adult)'),g('bluesignal',subject='DiseaseAlpha (adult)'),
           g('greensignal',subject='DiseaseAlpha (child)'),g('yellowsignal',subject='DiseaseAlpha (child)')],
          [f('redsignal'),f('bluesignal')])
    add('S02',['ENG-01'],'Parenthetic subjects normalize into one group',slim(r),
        v(r)['contributions'][0]['n_members']==4,
        'Subject normalization must not erase population restrictions and then merge roots.')
    r=run([g('redsignal','g1',subject='DiseaseAlpha'),g('bluesignal','g1',subject='DiseaseAlpha'),
           g('greensignal','g1',subject='DiseaseBeta'),g('yellowsignal','g1',subject='DiseaseBeta')],
          [f('redsignal'),f('bluesignal'),f('greensignal'),f('yellowsignal')])
    add('S03',['ENG-01'],'Negative control: genuinely different normalized subjects remain separate',slim(r),
        all(v(r,l)['contributions'][0]['n_members']==2 for l in ['DiseaseAlpha','DiseaseBeta']),
        'Do not overclaim that arbitrary different disease subjects directly merge.')
    rows=[g('redsignal','g1',relation='pathognomonic_for'),g('bluesignal','g1',relation='pathognomonic_for'),
          g('redsignal','g2',relation='pathognomonic_for'),g('greensignal','g2',relation='pathognomonic_for')]
    r=run(rows,[f('redsignal','absent'),f('bluesignal','absent'),f('greensignal')])
    add('S04',['ENG-02','ENG-07'],'Shared member lost; surviving singleton confirms atomically',slim(r),
        len(v(r)['confirmed'])==1 and v(r)['confirmed'][0]['predicate']=='greensignal' and v(r)['n_assertions']==3,
        '(A AND B) and (A AND C) retain both A member edges; neither full expression holds here.')
    base=[a(relation='required_for',modality='typical',threshold={'operator':'>=','value':3},quote='source one'),
          a(relation='required_for',modality='obligatory',threshold={'operator':'>=','value':10},quote='source two')]
    r1=run(base,[f(number=5)]);r2=run(base[::-1],[f(number=5)])
    add('S05',['ENG-03'],'Threshold order and cross-source modality chimera',{'first_low':slim(r1),'first_high':slim(r2)},
        not v(r1)['eliminated'] and bool(v(r2)['eliminated']) and v(r1)['score']==1.5,
        'Threshold, scope and modality belong to one source rule; no first-row/max-modality hybrid.')
    r1=run([a(comparator='DiseaseBeta',relation='distinguishes_from'),a(comparator='DiseaseGamma',relation='distinguishes_from')],
           [f()],labels=['DiseaseAlpha','DiseaseBeta','DiseaseGamma'])
    r2=run([a(comparator='DiseaseGamma',relation='distinguishes_from'),a(comparator='DiseaseBeta',relation='distinguishes_from')],
           [f()],labels=['DiseaseAlpha','DiseaseBeta','DiseaseGamma'])
    add('S06',['ENG-03','ENG-14'],'Comparator target deleted by atomic dedupe',{'beta_first':slim(r1),'gamma_first':slim(r2)},
        v(r1,'DiseaseBeta')['score']==-.5 and v(r1,'DiseaseGamma')['score']==0 and v(r2,'DiseaseGamma')['score']==-.5,
        'Different contrast targets are different complete propositions; order cannot choose the sole surviving target.')
    rows=[a('redsignal'),a('redsignal finding'),a('redsignal feature')]
    r=run(rows,[f()]);r1=run(rows[:1],[f()])
    add('S07',['ENG-04'],'String-different rewrites reuse one patient fact',{'one':slim(r1),'three':slim(r)},
        v(r)['score']==3 and v(r1)['score']==1,
        'Storage normalization and evidence-family identity must distinguish a rewrite from new independent evidence.')
    r=run([g('redsignal',logic='at_least_n',n=2),g('bluesignal',logic='at_least_n',n=3)],[f('redsignal'),f('bluesignal')])
    r2=run([g('bluesignal',logic='at_least_n',n=3),g('redsignal',logic='at_least_n',n=2)],[f('redsignal'),f('bluesignal')])
    add('S08',['ENG-05'],'Conflicting root n read from first surviving member',{'n2_first':slim(r),'n3_first':slim(r2)},
        v(r)['score']==1 and v(r2)['score']==.333,
        'The root owns one validated connective/count; inconsistent repeated root slots are rejected.')
    r=run([g('redsignal',polarity='asserted',relation='required_for'),g('bluesignal',polarity='negated',relation='required_for')],
          [f('redsignal'),f('bluesignal','absent')])
    r2=run([g('redsignal',threshold={'operator':'>=','value':10}),g('bluesignal')],
           [f('redsignal',number=1),f('bluesignal')])
    add('S09',['ENG-06'],'Grouped signed and numeric literals are not evaluated',{'negated_member':slim(r),'failed_threshold':slim(r2)},
        bool(v(r)['eliminated']) and v(r2)['contributions'][0]['n_satisfied']==2,
        'Evaluate complete signed literals before counting; NOT B with B absent is true and A=1 fails A>=10.')
    r=run([g('redsignal',logic='at_least_n',n=2),g('redsignal finding',logic='at_least_n',n=2)],[f()])
    add('S10',['ENG-08'],'One observation supplies two near-duplicate criterion votes',slim(r),
        v(r)['contributions'][0]['n_satisfied']==2 and v(r)['score']==1,
        'Count criterion identities and valid witnesses, not retained assertion rows; same fact can serve two only with explicit distinct-criterion proof.')
    r=run([g('redsignal',relation='excludes'),g('bluesignal',relation='excludes')],[f('redsignal'),f('bluesignal')])
    r2=run([g('redsignal',logic='any',relation='required_for'),g('bluesignal',logic='any',relation='required_for')],
           [f('redsignal','absent'),f('bluesignal','absent')])
    add('S11',['ENG-07'],'Group effects disappear: exclusion gains points, necessary OR never vetoes',
        {'exclusion_all':slim(r),'necessary_or_false':slim(r2)},
        v(r)['score']==1 and not v(r)['eliminated'] and not v(r2)['eliminated'],
        'Apply one root-level effect to the complete expression truth for ALL, ANY and count groups alike.')
    r=run([g('redsignal',relation='sufficient_for'),g('bluesignal',relation='sufficient_for')],
          [f('redsignal'),f('bluesignal','absent')],GROUP_ALL_IS_REQUIRED=True)
    add('S12',['ENG-09'],'ALL is automatically upgraded to disease necessity',slim(r),bool(v(r)['eliminated']),
        'Failure of one sufficient route does not exclude the disease; conjunction is not implication direction.')
    r=run([g('redsignal',context_type='treatment'),g('bluesignal',context_type='treatment')],
          [f('redsignal'),f('bluesignal')])
    r2=run([a('redsignal',context_type='treatment'),a('bluesignal',context_type='treatment')],
           [f('redsignal'),f('bluesignal')])
    r3=run([g('redsignal',context_type='criteria'),g('bluesignal',context_type='treatment')],
           [f('redsignal'),f('bluesignal','absent')],GROUP_ALL_IS_REQUIRED=True)
    add('S13',['ENG-10'],'Group bypasses soft context policy and mixed group permits hard action',
        {'grouped_treatment':slim(r),'atomic_treatment':slim(r2),'mixed':slim(r3)},
        v(r)['score']==1 and v(r2)['score']==0 and bool(v(r3)['eliminated']),
        'Eligibility applies before every root action and score; one clinical member cannot license treatment members as diagnostic necessity.')
    r=run([g('redsignal',_gate='E4_procedure_not_finding'),g('bluesignal',_gate='E4_procedure_not_finding')],
          [f('redsignal'),f('bluesignal')],NONCRITERION_INERT=True)
    add('S14',['ENG-10'],'F9 noncriterion guard is absent from group path',slim(r),v(r)['score']==1,
        'A declared inert row remains inert in group and contrast paths, not only atomic L3.')
    r=run([g('redsignal',relation='required_for'),g('bluesignal',relation='required_for')],[],CLOSED_WORLD=True)
    r2=run([g('redsignal',relation='required_for'),g('bluesignal',relation='required_for')],[f('redsignal')],CLOSED_WORLD=True)
    add('S15',['ENG-11'],'Closed-world flag skipped for all-unknown groups',{'all_unknown':slim(r),'one_present':slim(r2)},
        not v(r)['eliminated'] and bool(v(r2)['eliminated']),
        'Configuration behavior must be coherent; preferred clinical contract is explicit unknown rather than strengthening closed-world exclusions.')
    r=run([a('redsignal'),a('redsignal',subject='DiseaseBeta',context_type='treatment')],[f()],WEIGHT_SCHEME='inv')
    r2=run([a('redsignal')],[f()],WEIGHT_SCHEME='inv')
    r3=run([a('redsignal'),a('redsignal',subject='DiseaseBeta',relation='excludes')],[f()],WEIGHT_SCHEME='inv')
    add('S16',['ENG-12'],'Zero-score or eliminated claimant reweights another disease',
        {'no_ineligible_row':slim(r2),'treatment_claim':slim(r),'excluded_claim':slim(r3)},
        v(r2)['score']==1 and v(r)['score']==.5 and v(r,'DiseaseBeta')['score']==0 and v(r3)['score']==.5,
        'Build the positive support claimant set from admitted evidence, not every asserted joined row; survivor policy needs an explicit frozen contract.')
    rows=[a('redsignal',subject='DiseaseBeta',context_type='treatment')]
    r1=run(rows+[a('redsignal')],[f()],labels=['DiseaseAlpha','DiseaseBeta'],WEIGHT_SCHEME='idf')
    r2=run(rows+[a('redsignal')],[f()],labels=['DiseaseAlpha','DiseaseBeta','DiseaseBeta'],WEIGHT_SCHEME='idf')
    add('S17',['ENG-13'],'Duplicate candidate label changes denominator but overwrites verdict',
        {'unique':slim(r1),'duplicate':slim(r2)},
        len(r2['ranking'])==2 and v(r1)['score']!=v(r2)['score'],
        'Candidate labels are not unique identity; validate duplicates or normalize registry before calculating candidate-set weights.')
    rows=[a('redsignal',relation='distinguishes_from',comparator='DiseaseBeta',context_type='differential',polarity='negated',threshold={'operator':'>=','value':10})]
    r=run(rows,[f(number=1)])
    add('S18',['ENG-14'],'Negated, differential, numerically false contrast still penalizes comparator',slim(r),
        v(r,'DiseaseBeta')['score']==-.5 and v(r)['score']==0,
        'Contrast requires signed truth, source direction, scope, stage and target proof; co-mention and raw present are insufficient.')
    rows=[g('redsignal',relation='distinguishes_from',comparator='DiseaseBeta'),g('bluesignal',relation='distinguishes_from',comparator='DiseaseBeta')]
    r=run(rows,[f('redsignal')])
    add('S19',['ENG-14'],'One satisfied grouped atom bypasses incomplete root in L4',slim(r),
        v(r,'DiseaseBeta')['score']==-.5,
        'Do not execute grouped contrast leaves independently of the full root condition.')
    rows=[a('redsignal',relation='distinguishes_from',comparator='DiseaseBeta',context_type='differential'),
          a('redsignal finding',relation='distinguishes_from',comparator='DiseaseBeta',context_type='differential'),
          a('redsignal feature',relation='distinguishes_from',comparator='DiseaseBeta',context_type='differential')]
    r=run(rows,[f()],FINDING_POOL_BETA=1)
    add('S20',['ENG-04','ENG-14','ENG-15'],'Three competing statements become three penalties despite F10',slim(r),
        v(r,'DiseaseBeta')['score']==-1.5 and len(v(r,'DiseaseBeta')['layer4_penalties'])==3,
        'A repeated contrast proof is one evidence unit; F10 only pools L3 and is not a whole-engine duplication fix.')
    rows=[a('redsignal',relation='argues_against',comparator='DiseaseBeta')]
    r=run(rows,[f()]); r2=run([dict(rows[0],context_type='differential')],[f()])
    add('S21',['ENG-14','ENG-16'],'Changing context shifts weak-against from subject veto to comparator penalty',
        {'criteria_context':slim(r),'differential_context':slim(r2)},
        bool(v(r)['eliminated']) and v(r,'DiseaseBeta')['score']==0 and not v(r2)['eliminated'] and v(r2,'DiseaseBeta')['score']==-.5,
        'One relation must carry an explicit target and direction; context filtering cannot select which disease is opposed.')
    rows=[a('redsignal',relation='distinguishes_from',comparator='DiseaseBeta',context_type='differential'),
          a('bluesignal',relation='excludes')]
    r=run(rows,[f('redsignal')]);r2=run(rows,[f('redsignal'),f('bluesignal')])
    add('S22',['ENG-17'],'Source elimination silently withdraws its contrast against another candidate',
        {'source_survives':slim(r),'source_eliminated':slim(r2)},
        v(r,'DiseaseBeta')['score']==-.5 and v(r2,'DiseaseBeta')['score']==0,
        'Whether contrast depends on source diagnosis viability must be explicit; elimination should not covertly suppress otherwise valid evidence.')
    r=run([a(relation='argues_against',modality='rare')],[f()])
    r2=run([a(relation='excludes',threshold={'operator':'>=','value':10})],[f(number=1)])
    add('S23',['ENG-16','ENG-18'],'Weak opposition and false numeric exclusion are rigidly executed',
        {'rare_against':slim(r),'false_threshold':slim(r2)},
        bool(v(r)['eliminated']) and bool(v(r2)['eliminated']),
        'Against remains soft; exclusion antecedents must actually evaluate true.')
    r=run([a(relation='required_for',polarity='negated')],[f()])
    r2=run([a(relation='excludes',polarity='negated')],[f(polarity='absent')])
    add('S24',['ENG-18'],'Negative necessary/exclusion literals never use their legal hard direction',
        {'required_not_A_Apresent':slim(r),'not_A_excludes_Aabsent':slim(r2)},
        not v(r)['eliminated'] and not v(r2)['eliminated'],
        'Negation belongs inside the condition; a complete condition truth feeds necessity/exclusion effects independently.')
    r=run([a(relation='pathognomonic_for',threshold={'operator':'>=','value':10,'unit':'mg'})],
          [f(number=100,unit='mm')],RIGID_PATHO_READS_THRESHOLD=True)
    r2=run([a(threshold={'operator':'>=','value':10})],[f(number=1)])
    r3=run([a(polarity='negated',threshold={'operator':'>=','value':10})],[f(number=1)])
    add('S25',['ENG-18'],'Unknown confirms; false threshold still supports; satisfied negated threshold penalizes',
        {'unit_unknown_confirm':slim(r),'false_positive':slim(r2),'true_negated_negative':slim(r3)},
        len(v(r)['confirmed'])==1 and v(r2)['score']==.5 and v(r3)['score']==-1.5,
        'One literal evaluator must resolve values and signed conditions before either hard action or soft admission.')
    r=run([a('normal redsignal',relation='required_for')],[f('normal redsignal',polarity='normal')])
    add('S26',['ENG-18'],'Normal required condition read as absent even under exact join',slim(r),bool(v(r)['eliminated']),
        'Normal is a value interpretation, not a universal false polarity.')
    pairs={}
    for tag,th,fact in [
        ('missing_unit',{'operator':'>=','value':10,'unit':'mg'},f(number=12)),
        ('nonfinite',{'operator':'>=','value':10},f(number='NaN')),
        ('boolean',{'operator':'>=','value':1},f(number=True)),
        ('range_bad_high',{'operator':'range','value':0,'value_high':'not-number'},f(number=1))]:
        try: pairs[tag]={'return':e.threshold_ok({'threshold':th},fact)}
        except Exception as exc: pairs[tag]={'exception':type(exc).__name__,'message':str(exc)}
    add('S27',['IDN-08'],'Numeric validator accepts unknown dimensions/nonfinite/bool and may crash on upper bound',pairs,
        pairs['missing_unit']['return'][0] is True and pairs['nonfinite']['return'][0] is False and
        pairs['boolean']['return'][0] is True and pairs['range_bad_high']['exception']=='ValueError',
        'Validate finite numeric types, full interval, dimensions and operator; invalid input returns typed unknown/invalid, never false or process failure.')
    rows=[a('redsignal',relation='pathognomonic_for'),a('redsignal finding',relation='pathognomonic_for'),
          a('bluesignal',subject='DiseaseBeta',relation='pathognomonic_for'),a('greensignal',subject='DiseaseBeta'),
          a('yellowsignal',subject='DiseaseBeta')]
    r=run(rows,[f('redsignal'),f('bluesignal'),f('greensignal'),f('yellowsignal')],FINDING_POOL_BETA=1)
    add('S28',['ENG-15','ENG-20'],'Repeated confirmation outranks equal score with more independent signals',slim(r),
        r['top1']=='DiseaseAlpha' and len(v(r)['confirmed'])==2 and len(v(r,'DiseaseBeta')['confirmed'])==1 and
        v(r)['score']==v(r,'DiseaseBeta')['score'],
        'Confirmation is a proof-backed state, not a count priority; same fact paraphrases must not create extra certificates.')
    rows=[a('redsignal',relation='pathognomonic_for'),a('bluesignal',relation='excludes')]
    r=run(rows,[f('redsignal'),f('bluesignal')])
    add('S29',['ENG-20'],'Contradictory confirm and eliminate states coexist without conflict disposition',slim(r),
        bool(v(r)['confirmed']) and bool(v(r)['eliminated']) and r['top1']=='DiseaseBeta',
        'Retain opposing valid proofs and mark conflict; do not silently declare which source must win by sort key.')
    rows=[a('redsignal'),a('redsignal finding'),a('redsignal feature')]
    r=run(rows,[f()],FINDING_POOL_BETA=1)
    add('S30',['ENG-21'],'Contribution deltas do not reconstruct F10 final score',slim(r),
        v(r)['score']==1 and sum(x['delta'] for x in v(r)['contributions'])==3,
        'Expose pre-pool and applied post-pool deltas separately, plus exact total and rounding residual.')
    rows=[a('sig'+str(i)+'x') for i in range(30)]
    r=run(rows,[f('sig'+str(i)+'x') for i in range(30)])
    add('S31',['ENG-21'],'Production score log truncates to first25 contributions',slim(r),
        v(r)['score']==30 and len(v(r)['contributions'])==25,
        'Persist the complete proof/evidence ledger; display truncation must be explicitly marked and separate.')
    r=run([a(),a(subject='DiseaseBeta')],[f()],DISCRIMINATIVE_ONLY=True)
    r2=run([a(),a(subject='DiseaseBeta')],[f()],DISCRIMINATIVE_ONLY=False)
    add('S32',['ENG-22'],'Discriminative-only flag is assigned but never used',
        {'on':slim(r),'off':slim(r2)},r==r2 and v(r)['score']==1 and r['pairs'][0]['n_claimants']==2,
        'A public configuration switch must implement its advertised policy or fail as unsupported; do not silently ignore it.')
    rows=[a('redsignal'),a('redsignal',subject='DiseaseBeta')]
    r=run(rows,[f()],labels=['DiseaseAlpha','DiseaseBeta']);r2=run(rows,[f()],labels=['DiseaseBeta','DiseaseAlpha'])
    add('S33',['ENG-23'],'Final equal-state/score ranking inherits candidate input order',
        {'order_AB':slim(r),'order_BA':slim(r2)},r['top1']!=r2['top1'],
        'Tie policy must be declared and audited; changing it is a policy decision, not evidence of medical superiority.')
    # Legitimate positive controls guard against a reject-everything repair specification.
    r=run([a(relation='excludes',threshold={'operator':'>=','value':10})],[f(number=12)])
    r2=run([a(relation='required_for',threshold={'operator':'>=','value':10})],[f(number=12)])
    add('S34',['ENG-18'],'Positive controls: true exclusion and satisfied necessity',{'true_exclusion':slim(r),'necessary_met':slim(r2)},
        bool(v(r)['eliminated']) and not v(r2)['eliminated'],
        'Corrections must preserve justified hard actions and avoid treating satisfied necessity as sufficient confirmation.')


def historical_inventory():
    """Mechanical exposure counters; flags are not adjudicated clinical error rates."""
    folder=HERE.parent/'V2_INDEX_DIFFERENTIAL_AUDIT/replay_outputs'
    files=sorted(p for p in folder.glob('*.json.gz') if p.name.endswith(('__old_old.json.gz','__free_old.json.gz','__old_v2.json.gz','__free_v2.json.gz')))
    stats={}; samples=defaultdict(list)
    for path in files:
        x=json.load(gzip.open(path,'rt')); c=Counter(); st=x['stages']
        pre=st['pre_dedup_bound'];post=st['post_dedup_bound'];bound=st['bound']; arm=next(k for k in ['old_old','free_old','old_v2','free_v2'] if path.name.endswith('__'+k+'.json.gz'))
        # Source-occurrence memberships use cache + local gid + exact raw subject.
        pre_groups=defaultdict(set); post_groups=defaultdict(set)
        for stage,out in [(pre,pre_groups),(post,post_groups)]:
            for lab,items in stage.items():
                for row in items:
                    cg=row.get('criterion_group') or {}
                    if cg.get('group_id') and cg.get('logic') in {'all','any','at_least_n'}:
                        k=(lab,(row.get('_audit_source') or {}).get('cache_id'),cg['group_id'],row.get('subject'))
                        out[k].add(row['_audit_raw_index'])
        c['source_occurrences_with_two_or_more_pre_dedup_rows']=sum(len(v)>=2 for v in pre_groups.values())
        c['source_occurrences_multimember_before_fewer_than_two_representatives_after']=sum(len(ids)>=2 and len(post_groups[k])<2 for k,ids in pre_groups.items())
        c['group_membership_rows_pre_dedup']=sum(map(len,pre_groups.values()))
        c['group_membership_representative_rows_post_dedup']=sum(map(len,post_groups.values()))
        pre_by={r['_audit_raw_index']:r for items in pre.values() for r in items}
        for lab,items in post.items():
            for row in items:
                orig=pre_by[row['_audit_raw_index']]
                if orig.get('modality')!=row.get('modality'): c['representative_modality_upgraded']=c['representative_modality_upgraded']+1
                ids=row.get('_audit_support_raw_ids',[])
                for slot in ['threshold','comparator','context_type','criterion_group','subject']:
                    if len({json.dumps(pre_by[i].get(slot),sort_keys=True,ensure_ascii=False) for i in ids})>1:
                        c['dedup_buckets_differing_'+slot]+=1
        grouped_ids=set()
        for lab,gs in st['groups'].items():
            for group in gs:
                mm=group['members'];c['assembled_group_objects']+=1
                grouped_ids.update(m['_audit_raw_index'] for m in mm)
                caches={(m.get('_audit_source') or {}).get('cache_id') for m in mm}
                if len(caches)>1:
                    c['groups_with_multiple_cache_ids']+=1
                    if len(samples['cross_cache_group'])<8: samples['cross_cache_group'].append({'case':x['case_key'],'arm':arm,'candidate':lab,'key':group['key'],'raw_ids':[m['_audit_raw_index'] for m in mm],'cache_ids':sorted(str(y) for y in caches)})
                if len({(m.get('criterion_group') or {}).get('logic') for m in mm})>1:c['groups_mixed_logic']+=1
                if len({(m.get('criterion_group') or {}).get('n') for m in mm})>1:c['groups_mixed_n']+=1
                if len({m.get('relation') for m in mm})>1:c['groups_mixed_relation']+=1
                cs={(m.get('context_type') or '').lower() for m in mm}
                if cs<=e.SOFT_CONTEXTS:c['all_soft_context_groups']+=1
                if cs&e.SOFT_CONTEXTS and not cs<=e.SOFT_CONTEXTS:c['mixed_soft_nonsof_context_groups']+=1
                sat=[m for m in mm if m.get('_finding') and m['_finding'].get('polarity')=='present']
                if len({e.norm(m['_finding'].get('label')) for m in sat})<len(sat):c['groups_count_same_normalized_finding_multiple_times']+=1
                for m in sat:
                    if m.get('polarity')=='negated':c['present_counted_satisfied_despite_negated_member']+=1
                    if e.threshold_ok(m,m['_finding'])[0] is False:c['present_counted_satisfied_despite_false_numeric_threshold']+=1
        all_rows={r['_audit_raw_index']:r for items in bound.values() for r in items}
        for verdict in x['result']['ranking']:
            for contrib in verdict['contributions']:
                if contrib.get('why','').startswith('group:'):
                    c['actual_nonzero_group_contributions']+=1
                    if contrib.get('_audit_soft_group'):
                        c['actual_nonzero_soft_context_group_contributions']+=1
                    if len(samples['soft_group_contribution'])<8 and contrib.get('_audit_soft_group'):
                        samples['soft_group_contribution'].append({'case':x['case_key'],'arm':arm,'candidate':verdict['label'], 'raw_ids':contrib.get('_audit_representative_raw_ids'), 'delta':contrib['delta'], 'why':contrib['why']})
            for pen in verdict.get('layer4_penalties',[]):
                c['actual_layer4_penalties']+=1
                rid=pen.get('_audit_representative_raw_id')
                row=all_rows.get(rid)
                if row is None:
                    c['layer4_missing_representative_for_classification']+=1;continue
                if row.get('polarity')=='negated':
                    c['actual_layer4_from_negated_rows']+=1
                    if len(samples['negated_l4'])<10:samples['negated_l4'].append({'case':x['case_key'],'arm':arm,'penalized_candidate':verdict['label'],'from':pen['from'],'raw_id':rid,'predicate':row['predicate'],'relation':row['relation'],'comparator':row.get('comparator'),'polarity':row['polarity'],'context_type':row.get('context_type')})
                if (row.get('context_type') or '').lower() in e.SOFT_CONTEXTS:c['actual_layer4_from_soft_context_rows']+=1
                if rid in grouped_ids:c['actual_layer4_from_group_member_rows']+=1
                if e.threshold_ok(row,row['_finding'])[0] is False:c['actual_layer4_from_false_numeric_threshold']+=1
        stats[path.name]={'case_key':x['case_key'],'arm':arm,'counts':dict(c),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    by_arm={}
    for arm in ['old_old','free_old','old_v2','free_v2']:
        total=Counter()
        for rr in stats.values():
            if rr['arm']==arm:total.update(rr['counts'])
        by_arm[arm]=dict(total)
    assert len(files)==44, len(files)
    assert [by_arm[a]['actual_layer4_penalties'] for a in by_arm]==[93,87,154,188]
    return {'scope':'44 frozen historical replay packs; structural flags, not clinical error labels',
            'n_packs':len(files),'by_arm':by_arm,'by_pack':stats,'examples':dict(samples),
            'denominator_warning':'Pre-dedup source occurrence loss includes exact duplicate source exposures; these counts do not equal corrupted unique clinical criteria. Mixed relations/contexts and cross-cache IDs are review flags, not automatically errors.'}

def main():
    synthetic()
    inv=historical_inventory()
    out={'schema_version':1,'baseline_commit':'bbc036e8a6ec93583be915a4609fe86278ed062c',
         'engine_path':str(ENGINE.relative_to(ROOT)), 'engine_sha256':hashlib.sha256(ENGINE.read_bytes()).hexdigest(),
         'configuration_base':{k:sorted(v) if isinstance(v,set) else v for k,v in DEFAULT.items()},
         'fixture_override':'USE_CRITERION_GROUPS=True; every run resets all listed globals; fixture-specific overrides are explicit in script.',
         'validation':{'synthetic_witnesses_passed':len(WITNESSES),'historical_packs_read':inv['n_packs'],
                       'production_modified':False,'new_llm_calls':0,'clinical_accuracy_measured':False},
         'witnesses':WITNESSES,'historical_inventory':inv}
    (HERE/'reproduce_engine_defects_results.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(out['validation'],ensure_ascii=False))
if __name__=='__main__':main()
