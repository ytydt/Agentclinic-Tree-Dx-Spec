#!/usr/bin/env python3
"""Offline case74 replay and exact post-gate/bind/group trace; no network calls."""
import copy,json,os,pathlib,sys
os.environ.pop("F7_EXTRA_RETRIEVAL", None)  # freeze historical default source scope
ROOT=pathlib.Path(__file__).resolve().parents[4]
LEDGER=ROOT/'RAG_GUIDELINE_ORACLE_CEILING_LOCAL'
OUT=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL'))
import run_mechanical_engine as eng
import sweep_fixes as sw
KEY='MCR_v1_seq100/74'
def case(filename):return next(x for x in json.loads((LEDGER/filename).read_text()) if x['case_key']==KEY)
def trace(case_task,ext):
    captured={}
    def localtrace(frame,event,arg):
        if frame.f_code is eng.run_case.__code__ and event=='return':
            captured['bound']=copy.deepcopy(frame.f_locals['bound'])
            captured['groups']={label:[{'key':list(k),'members':copy.deepcopy(v)} for k,v in gs.items()] for label,gs in frame.f_locals['groups'].items()}
        return localtrace if frame.f_code is eng.run_case.__code__ else None
    sys.settrace(localtrace)
    try:r=eng.run_case(case_task,ext)
    finally:sys.settrace(None)
    return {'result':r,**captured}
def main():
    task=case('trial_tasks_11_all4.json');out=[]
    for arm in ['oldidxclean_groups','oldidxclean_groups_free','v2idxclean_groups','v2idxclean_groups_free']:
        filename=f'trial_extraction_x2_{arm}.json';ext=case(filename)
        for i,a in enumerate(ext['assertions']):a['_audit_raw_index']=i
        sw.configure(sw.BASELINES['B1'],sw.stacks()['S7_+F7'])
        r=trace(task,ext);r['input_file']=filename;out.append(r)
        print(arm,r['result']['gold_rank'],r['result']['gold_eliminated'],flush=True)
    (OUT/'case74_pipeline_trace.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
