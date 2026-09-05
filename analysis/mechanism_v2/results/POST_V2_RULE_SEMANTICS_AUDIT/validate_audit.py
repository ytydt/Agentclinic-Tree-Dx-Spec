#!/usr/bin/env python3
"""Validate deliverable integrity and cross-file claims; no model calls."""
import ast
import hashlib
import json
import re
from pathlib import Path

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[3]

def read(name):
    return json.loads((OUT/name).read_text())

def main():
    checks=[]
    def check(name, condition):
        checks.append({"check":name,"passed":bool(condition)})
        if not condition: raise AssertionError(name)
    files=[f for f in OUT.iterdir() if f.is_file()]
    json_count=jsonl_count=py_count=0
    for f in files:
        if f.suffix=='.json': json.loads(f.read_text());json_count+=1
        if f.suffix=='.jsonl':
            for line in f.read_text().splitlines(): json.loads(line)
            jsonl_count+=1
        if f.suffix=='.py': ast.parse(f.read_text(),filename=f.name);py_count+=1
    check('all_json_jsonl_and_python_parse',True)
    p=read('provenance_summary.json')
    check('all_140652_rows_reconstruct',sum(a['stored_rows'] for a in p['arms'].values())==140652 and all(a['all_rows_reconstructed_exactly'] for a in p['arms'].values()))
    check('clean_case_findings_all_arms',all(a['clean_case_findings_match_cache'] for a in p['arms'].values()))
    check('old_v2_job_counts',[p['arms'][a]['jobs'] for a in ['old_old','free_old','old_v2','free_v2']]==[3842,3842,3927,3927])
    jobs=[json.loads(x) for x in (OUT/'extraction_job_manifest.jsonl').read_text().splitlines()]
    check('all_jobs_manifested',len(jobs)==15538)
    check('manifest_interval_count',sum(j['assertion_stop_exclusive']-j['assertion_start'] for j in jobs)==140652)
    e=read('engine_repro_results.json')
    check('27_engine_counterexamples',e['n_counterexamples']==27 and len(e['cases'])==27 and all(c['reproduced'] for c in e['cases']))
    semantic=read('reference_semantics_results.json')
    check('40_reference_semantics_checks',semantic['all_passed'] and semantic['check_count']==40 and len(semantic['checks'])==40)
    for name,h in e['production_sha256'].items():
        f=ROOT/'analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL'/name
        check('production_unchanged:'+name,hashlib.sha256(f.read_bytes()).hexdigest()==h)
    c=read('cohort_metrics.json')
    check('four_cohort_arms',len(c['arms'])==4)
    for i,a in enumerate(c['arms']):
        for mode in ('default_stale','exact_arm_window'):
            check(f'arm{i}_{mode}_rank_reproduced',a[mode]['per_case']==a['stored']['per_case'])
        check(f'arm{i}_source_switch_no_rank_effect',a['default_stale']['per_case']==a['exact_arm_window']['per_case'])
    check('historical_mrr_vector',[a['stored']['mrr'] for a in c['arms']]==[.4273,.4132,.3667,.3071])
    ab=read('case74_targeted_ablation.json')
    targeted=[r for r in ab if r['intervention']=='only_false_CPVT_veto']
    global_drop=[r for r in ab if r['intervention']!='only_false_CPVT_veto']
    check('two_targeted_cpvt_recoveries',len(targeted)==2 and all(r['result']['gold_rank']==1 and not r['result']['gold_eliminated'] and r['result']['top1'].lower()=='catecholaminergic polymorphic ventricular tachycardia' for r in targeted))
    check('two_global_drop_lqts_winners',len(global_drop)==2 and all(r['result']['gold_rank']==2 and r['result']['top1'].lower()=='long qt syndrome' for r in global_drop))
    ss=read('source_parse_repro.json')
    check('source_parser_counterexamples',all(r['parser_uses_bibliographic_title'] for r in ss) and ss[0]['raw_nested_members_in_p']==2 and ss[0]['rendered_indented_lines']==0)
    broken=[]
    for f in OUT.glob('*.md'):
        for target in re.findall(r'(?<!!)\[[^\]]*\]\(([^)]+)\)',f.read_text()):
            if re.match(r'^[a-zA-Z]+:',target) or target.startswith('#'):continue
            target=target.split('#')[0]
            if not (f.parent/target).exists():broken.append([f.name,target])
    check('local_markdown_links_exist',not broken)
    secret_hits=[]
    pattern=re.compile(r'(?:gh[pousr]_[A-Za-z0-9]{30,}|sk-or-v1-[0-9a-f]{32,})')
    for f in files:
        if pattern.search(f.read_text(errors='replace')):secret_hits.append(f.name)
    check('no_provider_or_github_keys_in_new_artifacts',not secret_hits)
    check('no_new_large_or_lfs_artifacts',all(f.stat().st_size<90_000_000 and not f.read_bytes().startswith(b'version https://git-lfs.github.com/spec/v1') for f in files))
    result={'status':'passed','checks':checks,'parsed_json':json_count,'parsed_jsonl':jsonl_count,'parsed_python':py_count,
            'scope':'Artifact integrity and cross-file consistency only; not independent clinical adjudication or a new efficacy experiment.'}
    (OUT/'validation.json').write_text(json.dumps(result,indent=2)+'\n')
    manifest={f.name:{'bytes':f.stat().st_size,'sha256':hashlib.sha256(f.read_bytes()).hexdigest()} for f in sorted(OUT.iterdir()) if f.is_file() and f.name!='artifact_manifest.json'}
    (OUT/'artifact_manifest.json').write_text(json.dumps({'files':manifest,'manifest_excludes_itself':True},indent=2)+'\n')
    print(json.dumps({'status':'passed','checks':len(checks),'artifacts':len(manifest)},indent=2))

if __name__=='__main__':main()
