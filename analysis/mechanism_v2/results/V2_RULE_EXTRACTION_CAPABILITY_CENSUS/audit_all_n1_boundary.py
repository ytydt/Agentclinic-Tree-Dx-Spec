#!/usr/bin/env python3
"""Trace two actual raw all/n=1 groups through normalization and a bounded F7 probe.
No diagnosis replay, bindings, network or production writes.
"""
import copy
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[3]
CODE = ROOT / 'analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL'
DATA = ROOT / 'RAG_GUIDELINE_ORACLE_CEILING_LOCAL'
sys.path.insert(0, str(CODE))
import run_trial_extraction as extraction
import run_mechanical_engine as engine
import gate_assertions as gate
import sweep_fixes as sweep


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    case_key = 'DA_d2_heldout200b/522'
    rpath = DATA / 'trial_retrieval_x2_v2idx.json'
    retrieved = json.loads(rpath.read_text())
    keys = defaultdict(list)
    by_sha = {}
    sources = []
    for case in retrieved:
        for focus, bundle in case['retrieved'].items():
            for passage in bundle['passages']:
                text = passage['text'][:6000]
                key = (passage.get('source') or '', passage.get('title') or '', passage.get('section_path') or '')
                if text not in keys[key]:
                    keys[key].append(text)
                by_sha[hashlib.sha1(text.encode()).hexdigest()[:16]] = text
                if case['case_key'] == case_key and passage['gid'] == 587069:
                    sources.append({'case_key': case_key, 'focus': focus, 'gid': 587069,
                                    'text': text, 'sha256': hashlib.sha256(text.encode()).hexdigest(),
                                    'source': passage.get('source'), 'title': passage.get('title')})
    results = []
    probes = [
        ('old_v2', 'af8d1e336c3e8efee9dcd6ac44f19ba64957b0bd', [2, 3],
         'trial_extraction_x2_v2idxclean_groups.json', [2564, 2565]),
        ('free_v2', '542d4e51ff20ec4296f25b2f7f562ac3912e823d', [4, 5],
         'trial_extraction_x2_v2idxclean_groups_free.json', [2235, 2236]),
    ]
    for arm, cid, local, saved_fn, saved_indices in probes:
        cpath = DATA / 'trial_extraction_cache' / f'{cid}.json'
        rows = json.loads(cpath.read_text())['assertions']
        raw = [copy.deepcopy(rows[i]) for i in local]
        normalized = copy.deepcopy(raw)
        stats = Counter()
        for row in normalized:
            extraction.normalise_group(row, stats)
        epath = DATA / saved_fn
        case = next(x for x in json.loads(epath.read_text()) if x['case_key'] == case_key)
        saved = [copy.deepcopy(case['assertions'][i]) for i in saved_indices]
        assert all(row['criterion_group'] == {'group_id': 'g2', 'logic': 'all', 'n': None}
                   for row in normalized + saved)
        assert all(row['criterion_group']['n'] == 1 for row in raw)
        sweep.configure(sweep.BASELINES['B1'], sweep.stacks()['S7_+F7'])
        gate._PASSAGE_INDEX = {'by_key': dict(keys), 'by_sha': by_sha}
        annotated = copy.deepcopy(saved)
        for i, row in zip(saved_indices, annotated):
            row['_audit_index'] = i
        # Probe the selected pair with matching-arm source provenance. This is explicitly
        # not the complete case gate, downstream dedup/binding, or diagnostic replay.
        cooked = gate.gate_assertions([engine.clamp_relation(row) for row in annotated], apply_nli=False)
        assert all((row.get('criterion_group') or {}).get('n') != 1 for row in cooked)
        results.append({'arm': arm, 'case_key': case_key, 'gid': 587069, 'cache_id': cid,
                        'cache_sha256': sha(cpath), 'raw_indices': local, 'raw_rows': raw,
                        'direct_normalise_group_rows': normalized, 'normalise_stats': dict(stats),
                        'saved_file': saved_fn, 'saved_file_sha256': sha(epath),
                        'saved_indices': saved_indices, 'saved_rows': saved,
                        'F7_probe_mode': 'selected pair only; B1+S7; matching-arm actual input windows; no NLI; no downstream binding',
                        'F7_probe_rows': cooked,
                        'counterfactual_direct_raw_input': {'size': 2, 'need': 1, 'sat': 1, 'vio': 0, 'target': 1, 'met': True},
                        'normalized_two_member_group_same_assignment': {'size': 2, 'need': None, 'sat': 1, 'vio': 0, 'target': 2, 'met': False},
                        'production_single_hit_via_n1_demonstrated': False,
                        'conclusion': 'Raw cardinality-domain error is real; normalise_group clears n for all and saved rows confirm repair. Selected F7 probe does not restore n=1. No actual case binding/execution was claimed or run.'})
    result = {'scope': 'bounded normalization-boundary witness; not a case diagnosis replay',
              'code_sha256': {f: sha(CODE / f) for f in ['run_trial_extraction.py', 'run_mechanical_engine.py', 'gate_assertions.py']},
              'retrieval_sha256': sha(rpath), 'actual_sources': sources, 'cases': results,
              'review_correction': 'Initial raw+code observation was too strong as a production reachability inference. Direct normalized artifacts refute survival of n=1 in these historical groups.'}
    (OUT / 'all_n1_normalization_boundary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'cases_checked': len(results), 'raw_n1_cleared_in_all_saved_rows': True,
                      'actual_case_execution_rerun': False,
                      'F7_probe_member_counts': [len(r['F7_probe_rows']) for r in results]}, indent=2))


if __name__ == '__main__':
    main()
