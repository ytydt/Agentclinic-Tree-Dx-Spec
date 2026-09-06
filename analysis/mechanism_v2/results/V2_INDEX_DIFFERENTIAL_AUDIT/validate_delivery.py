#!/usr/bin/env python3
"""Validate task-one artifact completeness and frozen numeric claims (not clinical accuracy)."""
import ast
import gzip
import hashlib
import json
import re
from pathlib import Path

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[3]
EXPECTED={'522','773','119','257','326','475','49','56','74','91','179'}

def read_json(path):
 if path.name.endswith('.gz'):
  with gzip.open(path,'rt',encoding='utf-8') as f:return json.load(f)
 return json.loads(path.read_text())

def main():
 checks=[]
 def check(name,value):
  checks.append({'check':name,'pass':bool(value)})
  if not value:raise AssertionError(name)
 rv=read_json(OUT/'replay_validation.json')
 check('44 historical full output equivalence checks',len(rv['checks'])==44 and all(c['matches_prior_full_truncated_result'] for c in rv['checks']))
 check('696 baseline scores reconstructed',sum(c['candidate_score_reconstructions'] for c in rv['checks'])==696 and all(c['all_scores_reconstructed'] for c in rv['checks']))
 endpoints=read_json(OUT/'endpoint_and_rank_accounting.json')
 check('11 distinct cases', {r['case_key'].split('/')[-1] for r in endpoints['cases']}==EXPECTED)
 check('old seven top3 label hits',len(endpoints['old_index_top3_cases'])==7)
 check('complete label top3 four arms', [r['complete_label_top3'] for r in endpoints['metrics']]==[4,4,3,3])
 check('legacy top3 four arms', [r['legacy_top3'] for r in endpoints['metrics']]==[7,6,6,4])
 for c in EXPECTED:
  p=OUT/'cases'/f'case_{c}.md'
  check(f'case {c} report exists',p.exists())
  check(f'case {c} report substantive text',len(p.read_text())>1800)
 check('task one main report', (OUT/'REPORT.md').exists())
 check('source audit report', (OUT/'RETRIEVAL_DELTA.md').exists())
 check('independent methods report',(OUT/'METHODS_REVIEW.md').exists())
 check('independent final report review',(OUT/'FINAL_REPORT_REVIEW.md').exists())
 for fn,h in rv['source_file_sha256'].items():
  check(f'input unchanged {fn}',hashlib.sha256((ROOT/'RAG_GUIDELINE_ORACLE_CEILING_LOCAL'/fn).read_bytes()).hexdigest()==h)
 prod=ROOT/'analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL/run_mechanical_engine.py'
 check('production engine unchanged',hashlib.sha256(prod.read_bytes()).hexdigest()==rv['production_file_sha256'])
 docs=[]
 for p in sorted(OUT.rglob('*')):
  if not p.is_file() or '__pycache__' in p.parts or p.name in {'delivery_validation.json','artifact_manifest.json'}:continue
  check(f'below GitHub single file limit {p.relative_to(OUT)}',p.stat().st_size<90_000_000)
  if p.suffix=='.py': ast.parse(p.read_text());check(f'Python parses {p.name}',True)
  if p.name.endswith('.json') or p.name.endswith('.json.gz'): read_json(p);check(f'JSON readable {p.name}',True)
  if p.suffix=='.jsonl':
   for line in p.read_text().splitlines():
    if line.strip():json.loads(line)
   check(f'JSONL readable {p.name}',True)
  if p.suffix in {'.md','.json','.jsonl','.py','.txt'}:
   text=p.read_text()
   # Only signal file identity; never print a matched secret.
   check(f'no credential literals {p.name}',not re.search(r'gh[pousr]_[A-Za-z0-9]{30,}|sk-or-v1-[a-f0-9]{40,}',text))
  elif p.name.endswith('.gz'):
   with gzip.open(p,'rt',encoding='utf-8') as stream:
    check(f'no credential literals in decompressed {p.name}',not re.search(r'gh[pousr]_[A-Za-z0-9]{30,}|sk-or-v1-[a-f0-9]{40,}',stream.read()))
  docs.append({'path':str(p.relative_to(OUT)),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
 result={'scope':'Artifact, linkage, denominator, input-integrity and code-parse checks; not an independent clinical accuracy estimate.',
         'passed':all(c['pass'] for c in checks),'n_checks':len(checks),'checks':checks}
 (OUT/'delivery_validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
 (OUT/'artifact_manifest.json').write_text(json.dumps({'base_commit':'6fa8fd7aa2548cc01ac81f2d5261801190244d27','files':docs},ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'passed':result['passed'],'checks':len(checks),'files':len(docs),'bytes':sum(x['bytes'] for x in docs)}))

if __name__=='__main__':main()
