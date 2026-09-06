#!/usr/bin/env python3
"""Independent read-only checks of frozen labels, ordering and group provenance.
Writes reviewer-owned findings only; does not generate extraction or alter replay.
"""
import gzip
import hashlib
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[3]

def main():
    taskfile = ROOT / 'RAG_GUIDELINE_ORACLE_CEILING_LOCAL/trial_tasks_11_all4.json'
    tasks = json.loads(taskfile.read_text())
    endpoint = json.loads((OUT / 'endpoint_and_rank_accounting.json').read_text())
    checks = []
    for c in endpoint['cases']:
        t = next(x for x in tasks if x['case_key'] == c['case_key'])
        emitted = {x['label'] for x in t['candidates']}
        checks.append({'case_key': c['case_key'], 'raw_gold_exact': c['gold'] == t['gold'],
                       'legacy_labels_exact': c['legacy_labels'] == t['gold_labels_in_set'],
                       'explicit_complete_labels_are_emitted': set(c['explicit_complete_labels']) <= emitted})
        assert all(v for k, v in checks[-1].items() if k != 'case_key')
    old7 = [c for c in endpoint['cases'] if c['arms']['old_old']['legacy_rank'] <= 3]
    complete_old7 = [c['case_key'] for c in old7 if c['arms']['old_old']['complete_label_rank'] is not None
                     and c['arms']['old_old']['complete_label_rank'] <= 3]
    scope_only_old7 = [c['case_key'] for c in old7 if not c['explicit_complete_labels']]
    assert len(old7) == 7 and len(complete_old7) == 4 and len(scope_only_old7) == 3
    multi_cache = []
    ordering = []
    cpvt = []
    count_files = 0
    for p in sorted((OUT / 'replay_outputs').glob('*.json.gz')):
        x = json.load(gzip.open(p, 'rt'))
        rank = x['result']['ranking']
        keys = [(bool(v['eliminated']), -len(v['confirmed']), -v['score']) for v in rank]
        ok = keys == sorted(keys)
        assert ok
        ordering.append({'case_key': x['case_key'], 'arm': x['arm'], 'sort_tuple_verified': ok})
        count_files += 1
        if x['case_key'].endswith('/74'):
            for i, v in enumerate(rank, 1):
                if 'catecholaminergic' in v['label'].lower():
                    cpvt.append({'arm': x['arm'], 'label': v['label'], 'rank': i,
                                 'n_assertions': v['n_assertions'], 'n_joined': v['n_joined'],
                                 'eliminated': bool(v['eliminated']), 'score': v['score']})
        for candidate, groups in x['stages']['groups'].items():
            for group in groups:
                members = group['members']
                caches = {m.get('_audit_source', {}).get('cache_id') for m in members}
                if len(caches) < 2:
                    continue
                multi_cache.append({'case_key': x['case_key'], 'arm': x['arm'], 'candidate': candidate,
                                    'group_key': group['key'], 'n_members': len(members),
                                    'n_cache_representatives': len(caches),
                                    'members': [{'representative_raw_id': m['_audit_raw_index'],
                                                 'support_raw_ids': m.get('_audit_support_raw_ids', []),
                                                 'source': m.get('_audit_source'),
                                                 'predicate': m['predicate'], 'relation': m['relation'],
                                                 'criterion_group': m.get('criterion_group')}
                                                for m in members]})
    result = {'review_kind': 'Independent structural and endpoint checks; no clinical re-adjudication.',
              'task_sha256': hashlib.sha256(taskfile.read_bytes()).hexdigest(),
              'endpoint_checks': checks, 'old_legacy_top3_count': len(old7),
              'old_top3_complete_emitted_label_cases': complete_old7,
              'old_top3_only_parent_or_component_cases': scope_only_old7,
              'available_replay_files_checked': count_files, 'ordering_checks': ordering,
              'case74_exact_frozen_rank_check': cpvt,
              'multi_cache_group_representatives': multi_cache,
              'limits': ['A group spanning caches is a provenance alert, not a semantic error by itself; one source criterion may straddle windows.',
                         'Counts use surviving representative rows. Deduplicated support-row ancestry is separately retained in each member.',
                         'Explicit complete labels are a conservative emitted-label-scope audit, not an exhaustive clinical synonym adjudication.',
                         'These checks are accounting and structure checks, not proof of clinical correctness or index causal effects.']}
    (OUT / 'methods_review_checks.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'endpoint_checks': len(checks), 'replay_files': count_files,
                      'multi_cache_groups': len(multi_cache), 'old7': complete_old7 + scope_only_old7}, ensure_ascii=False))

if __name__ == '__main__':
    main()
