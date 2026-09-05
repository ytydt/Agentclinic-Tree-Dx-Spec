#!/usr/bin/env python3
"""Aggregate human-style judgment codes; this does not classify source text."""
import json,re
from collections import Counter,defaultdict
from pathlib import Path
P=Path(__file__).resolve().parent
def norm(s):return re.sub('[^a-z0-9]+','_',s.lower()).strip('_')
def dimension(code):
 s=norm(code)
 if s in ('partial','mixed_correct_and_wrong'):return 'completeness'
 if s.startswith('target_'):return 'target_identity_or_scope'
 if s in ('predicate_identity','comparator_identity','participant_binding','table_cell_binding'):return 'predicate_or_argument_identity'
 if s.startswith('relation_direction'):return 'relation_direction'
 if s.startswith('relation_strength') or s in ('epistemic_scope','epistemic_status'):return 'relation_strength_or_epistemic_status'
 if s in ('literal_polarity','negation_scope'):return 'literal_polarity_or_negation_scope'
 if s=='connective':return 'connective'
 if s.startswith('cardinality_'):return 'cardinality_domain_or_distinctness'
 if s.startswith('group_') or s in ('nesting_branch','branch_loss'):return 'group_effect_membership_or_nesting'
 if s.startswith('scope_'):return 'population_time_anatomic_causal_or_exception_scope'
 if s.startswith('numeric_'):return 'numeric_value_comparator_unit_or_domain'
 if s=='score_semantics':return 'score_program'
 if s=='non_diagnostic_task':return 'task_promotion'
 if s.startswith('provenance_') or s=='source_hierarchy':return 'provenance_or_source_structure'
 if s in ('unsupported_new_claim','unsupported_result'):return 'unsupported_component_with_traceable_ancestor'
 raise ValueError('Unmapped review code: '+code)
def main():
 source=json.loads((P/'source_rule_results.json').read_text());output=json.loads((P/'output_unit_results.json').read_text());out={};cross={}
 for side,rows in [('source_new',[x for x in source if x['arm']=='new']),('output',output)]:
  counts=Counter();weighted=defaultdict(float);by=defaultdict(Counter);partial_scope=[];other=[]
  for r in rows:
   dd=set()
   for code in r.get('errors',[]):cross[code]=dimension(code);dd.add(cross[code])
   for d in dd:counts[d]+=1;weighted[d]+=r['weight'];by[r.get('stratum',r.get('source'))][d]+=1
   if r['label']=='distorted':
    if dd and dd <= {'completeness','population_time_anatomic_causal_or_exception_scope'}:partial_scope.append(r.get('rule_id',r.get('unit_id')))
    else:other.append(r.get('rule_id',r.get('unit_id')))
  out[side]={'denominator_all_units':len(rows),'multi_label_counts':dict(counts),'weighted_totals':dict(weighted),'by_stratum_counts':{k:dict(v) for k,v in by.items()},'partial_or_scope_only_ids':partial_scope,'other_distortion_ids':other,'warning':'Partial/scope-only does not imply harmless. Causes are not identified by these symptom codes, and multicode totals do not sum to100%.'}
 (P/'error_code_crosswalk.json').write_text(json.dumps(cross,indent=2)+'\n');(P/'error_dimension_metrics.json').write_text(json.dumps(out,indent=2)+'\n')
 print(json.dumps({s:{'counts':d['multi_label_counts'],'partial_scope_only':len(d['partial_or_scope_only_ids']),'other_distortions':len(d['other_distortion_ids'])} for s,d in out.items()},indent=2))
if __name__=='__main__':main()
