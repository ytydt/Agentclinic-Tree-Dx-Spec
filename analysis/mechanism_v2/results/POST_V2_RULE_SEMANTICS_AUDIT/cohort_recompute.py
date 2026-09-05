#!/usr/bin/env python3
"""Read-only audit of frozen x2 artifacts; emits only into this audit directory.
No API/network calls. Baseline default F7 and exact extraction-window F7 are
separate replays, not claims about the environment of the historical run.
"""
import argparse,copy,hashlib,json,os,sys,time
from collections import Counter,defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4]
OUT=Path(__file__).resolve().parent
SRC=ROOT/'RAG_GUIDELINE_ORACLE_CEILING_LOCAL'
CODE=ROOT/'analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL'
sys.path.insert(0,str(CODE))
import run_mechanical_engine as eng
import sweep_fixes as sw
import gate_assertions as gate
import measure_2x2_groups as spans
import score_2x2_engine as score
from functools import lru_cache
# Pure-string memoization only; values do not depend on trial-arm evidence.
for _name in ["norm", "tokens", "embed_sim"]:
    setattr(eng,_name,lru_cache(maxsize=500000)(getattr(eng,_name)))
ARMS=spans.ARMS

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def passage_index(rows):
    keys=defaultdict(list); hashes={}
    for row in rows:
        for bundle in row['retrieved'].values():
            for p in bundle['passages']:
                txt=p['text'][:6000]
                k=(p.get('source') or '',p.get('title') or '',p.get('section_path') or '')
                if txt not in keys[k]:keys[k].append(txt)
                hashes[hashlib.sha1(txt.encode()).hexdigest()[:16]]=txt
    return {'by_key':dict(keys),'by_sha':hashes}

def pair(a,b):
    ks=list(a); d=[1/b[k]-1/a[k] for k in ks]
    gains=sum(v>0 for v in d); harms=sum(v<0 for v in d);n=gains+harms
    import math
    p=min(1.,2*sum(math.comb(n,k) for k in range(min(gains,harms)+1))/2**n) if n else 1.
    return {'n':len(ks),'rank_improved':gains,'rank_worsened':harms,'rank_unchanged':len(ks)-n,
            'paired_mean_rr_delta':sum(d)/len(d),'sign_test_two_sided_p':p,
            'top1_gains':[k for k in ks if a[k]!=1 and b[k]==1],
            'top1_losses':[k for k in ks if a[k]==1 and b[k]!=1]}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--replay',action='store_true');args=ap.parse_args()
    tasks=json.loads((SRC/'trial_tasks_11_all4.json').read_text()); keys=[t['case_key'] for t in tasks]
    stored=json.loads((SRC/'trial_engine_x2.json').read_text()); noex=json.loads((SRC/'trial_engine_x2_noexcl.json').read_text())
    embs=eng._embeddings()['idx']
    result={'scope':'11 selected development cases; historical gold-label proxy is NOT clinical-complete',
            'input_hashes':{fn:sha(SRC/fn) for _,fn,_ in ARMS},'initial_F7_EXTRA_RETRIEVAL':os.environ.get('F7_EXTRA_RETRIEVAL'),
            'tasks':[{'case_key':t['case_key'],'gold':t['gold'],'legacy_accepted_labels':t['gold_labels_in_set'],
                      'n_candidates':t['n_candidates'],'selection':t['verdict']} for t in tasks],
            'arms':[],'pairwise':{},'stored_drop_excludes':noex}
    for i,(name,fn,rfn) in enumerate(ARMS):
        print('read',name,flush=True); ext=json.loads((SRC/fn).read_text());r=json.loads((SRC/rfn).read_text())
        assert [e['case_key'] for e in ext]==keys
        raw=[a for e in ext for a in e['assertions']];pred={a['predicate'].strip() for a in raw}; findings=[f for e in ext for f in e['findings']]
        groups=spans.score(SRC/fn,rfn)
        passage_tasks=[p for row in r for b in row['retrieved'].values() for p in b['passages']]
        arm={'arm':name,'extraction_file':fn,'retrieval_file':rfn,'retrieval_sha256':sha(SRC/rfn),
             'stored':stored[i],'recalculated_stored_ranks':{'top1':sum(v==1 for v in stored[i]['per_case'].values()),
              'top3':sum(v<=3 for v in stored[i]['per_case'].values()),'mrr':sum(1/v for v in stored[i]['per_case'].values())/11},
             'raw_assertions':len(raw),'relation_counts':dict(Counter(a.get('relation') for a in raw)),
             'findings_sha256':hashlib.sha256(json.dumps([e['findings'] for e in ext],sort_keys=True).encode()).hexdigest(),
             'passage_hypothesis_tasks':len(passage_tasks),'unique_case_gid':len({(row['case_key'],p['gid']) for row in r for b in row['retrieved'].values() for p in b['passages']}),
             'passage_character_count':sum(len(p['text'][:6000]) for p in passage_tasks),
             'truncated_tasks':sum(len(p['text'])>6000 for p in passage_tasks),
             'group_span_metrics':groups,'embedding_coverage_unique_predicates':{'total':len(pred),'present':len(pred&embs.keys())},
             'embedding_coverage_assertion_predicates':{'total':len(raw),'present':sum(a['predicate'].strip() in embs for a in raw)},
             'embedding_coverage_finding_sides':{'total':sum(bool(f.get(s)) for f in findings for s in ['canonical','label']),
                'present':sum(bool(f.get(s)) and f[s].strip() in embs for f in findings for s in ['canonical','label'])}}
        if args.replay:
            for mode in ['default_stale','exact_arm_window']:
                print('replay',name,mode,flush=True); os.environ.pop('F7_EXTRA_RETRIEVAL',None); gate._PASSAGE_INDEX=None
                if mode=='exact_arm_window':gate._PASSAGE_INDEX=passage_index(r)
                sw.configure(sw.BASELINES['B1'],sw.stacks()['S7_+F7'])
                tracefile=f'cohort_trace_{i}_{mode}.json'
                if (OUT/tracefile).exists():
                    trace=json.loads((OUT/tracefile).read_text())
                else:
                    trace=[eng.run_case(t,copy.deepcopy(e)) for t,e in zip(tasks,ext)]
                m=sw.metrics(trace);m['group_activity']=dict(score.group_activity(trace));m['gold_elim_why']=score.gold_elim_why(trace,{t['case_key']:t for t in tasks})
                m['matches_stored_per_case']=m['per_case']==stored[i]['per_case'];arm[mode]=m
                tracefile=f'cohort_trace_{i}_{mode}.json'
                (OUT/tracefile).write_text(json.dumps(trace,ensure_ascii=False,indent=2));arm[mode]['trace_file']=tracefile
                print(name,mode,m['top1'],m['mrr'],m['gold_eliminated'],flush=True)
        result['arms'].append(arm)
        (OUT/'cohort_metrics.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    for a,b in [(0,1),(2,3),(0,2),(1,3),(0,3)]:result['pairwise'][f'{ARMS[a][0]} => {ARMS[b][0]}']=pair(stored[a]['per_case'],stored[b]['per_case'])
    (OUT/'cohort_metrics.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
