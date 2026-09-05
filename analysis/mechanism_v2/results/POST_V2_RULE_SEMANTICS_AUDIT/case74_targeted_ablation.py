#!/usr/bin/env python3
"""Separate CPVT false-veto removal from globally dropping raw exclusion rows."""
import copy,json,pathlib,sys
ROOT=pathlib.Path(__file__).resolve().parents[4];L=ROOT/'RAG_GUIDELINE_ORACLE_CEILING_LOCAL';OUT=pathlib.Path(__file__).parent
sys.path.insert(0,str(ROOT/'analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL'))
import run_mechanical_engine as eng,sweep_fixes as sw
KEY='MCR_v1_seq100/74'
def case(fn):return next(x for x in json.loads((L/fn).read_text()) if x['case_key']==KEY)
task=case('trial_tasks_11_all4.json');out=[]
for suff in ['', '_free']:
 fn=f'trial_extraction_x2_v2idxclean_groups{suff}.json';base=case(fn)
 for intervention in ['only_false_CPVT_veto','all_raw_excludes']:
  ext=copy.deepcopy(base)
  if intervention=='only_false_CPVT_veto':ext['assertions'].pop(1017)
  else:ext['assertions']=[a for a in ext['assertions'] if a.get('relation','').lower() not in {'excludes','argues_against'}]
  sw.configure(sw.BASELINES['B1'],sw.stacks()['S7_+F7']);r=eng.run_case(task,ext)
  out.append({'input_file':fn,'intervention':intervention,'removed_index':1017 if intervention=='only_false_CPVT_veto' else None,'result':r})
  print(fn,intervention,'top1',r['top1'],'goldrank',r['gold_rank'],'goldelim',r['gold_eliminated'],flush=True)
(OUT/'case74_targeted_ablation.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
