#!/usr/bin/env python3
"""Bounded witnesses against real auxiliary functions; no corpus/model download."""
from __future__ import annotations
import contextlib
import hashlib
import importlib
import io
import json
from pathlib import Path
import sys
import tempfile
from collections import defaultdict

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
SRC = HERE.parent / 'RAG_GUIDELINE_ORACLE_CEILING_LOCAL'
sys.path.insert(0, str(SRC))


def main():
    import numpy as np
    import scipy.sparse as sp
    eng = importlib.import_module('run_mechanical_engine')
    sw = importlib.import_module('sweep_fixes')
    corpus = importlib.import_module('build_corpus_lift')
    rows = []
    def record(rid, actual, expected, note):
        assert actual == expected, (rid, actual, expected)
        rows.append(dict(id=rid, actual=actual, expected_current_behavior=expected,
                         passed=True, note=note))

    settings = {
        'RIGID_REQUIRED_ANY_MODALITY': True,
        'RIGID_SUFFICIENT_CONFIRMS': True,
        'RIGID_PATHO_READS_THRESHOLD': True,
        'RIGID_REQUIRED_CLOSED_WORLD': True,
        'NONCRITERION_INERT': True,
        'FINDING_POOL_BETA': 1.0,
        'LAYER3_DROP': {('a', 'b', 'c', 'd')},
    }
    originals = {k: getattr(eng, k) for k in settings}
    try:
        for k, v in settings.items():
            setattr(eng, k, v)
        sw.configure(sw.BASELINES['B1'], {})
        leaked = [k for k, v in settings.items() if getattr(eng, k) == v]
        record('AUX-R01', leaked, list(settings),
               'Actual configure leaves seven out-of-contract globals inherited from earlier calls; a fresh CLI process does not itself demonstrate contamination.')
    finally:
        for k, v in originals.items():
            setattr(eng, k, v)

    # 24 synthetic chunks, with eight chunks per artificial disease; enough to
    # exercise the real MIN_TOPIC_CHUNKS=8 path without any source corpus.
    vocab = {'alpha': 0, 'beta': 1, 'gamma': 2, 'marker': 3}
    class Vec:
        vocabulary_ = vocab
    arr = np.zeros((24, 4))
    meta = []
    for i, name in enumerate(('alpha', 'beta', 'gamma')):
        for j in range(8):
            idx = i * 8 + j
            arr[idx, i] = 1
            arr[idx, 3] = 1 if j < (8, 1, 7)[i] else 0
            meta.append(dict(source='synthetic', article_id=name, title=name))
    matrix = sp.csc_matrix(arr)
    saved = (corpus.LEDGER, corpus.load_index, sys.argv)
    captured = []
    def task(key, names):
        return dict(case_key=key, candidates=[dict(label=x, aliases=[]) for x in names])
    def execute(base, tasks, tag, finding='marker'):
        (base / 'tasks.json').write_text(json.dumps(tasks))
        ext = [dict(case_key=t['case_key'], findings=[dict(label=finding, canonical=finding)]) for t in tasks]
        (base / 'trial_extraction_fixture.json').write_text(json.dumps(ext))
        sys.argv = ['build_corpus_lift.py', '--tasks', 'tasks.json', '--arm', 'fixture', '--out', tag + '.json']
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            assert corpus.main() == 0
        captured.append(dict(tag=tag, stdout=stream.getvalue()))
        return json.loads((base / (tag + '.json')).read_text()), json.loads((base / (tag + '_stats.json')).read_text())
    try:
        with tempfile.TemporaryDirectory(prefix='rule_aux_audit_') as td:
            base = Path(td)
            corpus.LEDGER = base
            corpus.load_index = lambda: (meta, Vec(), matrix)
            t1 = task('case_ab', ['Alpha', 'Beta'])
            t2 = task('case_ag', ['Alpha', 'Gamma'])
            one, _ = execute(base, [t1], 'one')
            two, _ = execute(base, [t2], 'two')
            forward, _ = execute(base, [t1, t2], 'forward')
            reverse, _ = execute(base, [t2, t1], 'reverse')
            record('AUX-R02', [one['alpha||marker'], two['alpha||marker']], [.5306, .0606],
                   'Same candidate/finding has two legitimate case-relative lift values under different competitor sets.')
            record('AUX-R03', [forward['alpha||marker'], reverse['alpha||marker']], [.0606, .5306],
                   'Actual main stores one candidate||finding key; task order selects which case value survives.')
            unknown, stats = execute(base, [task('unknown_subtype', ['Alpha UnseenSubtype', 'Beta'])], 'unknown')
            record('AUX-R04', stats[0]['topic_chunks']['Alpha UnseenSubtype'], 8,
                   'OOV qualifier is discarded, so all Alpha chunks become topic chunks for unseen subtype; no subtype evidence exists in fixture.')
            record('AUX-R05', unknown['alpha unseen subtype||marker'], one['alpha||marker'],
                   'Unseen subtype receives the same numerical lift as its parent lexical stem.')
            funknown, _ = execute(base, [t1], 'finding_unknown', 'marker unobservedqualifier')
            record('AUX-R06', funknown['alpha||marker unobservedqualifier'], one['alpha||marker'],
                   'Unknown feature qualifier is also dropped before intersection; output key retains specificity absent from counts.')
    finally:
        corpus.LEDGER, corpus.load_index, sys.argv = saved
    paths = ['run_mechanical_engine.py', 'sweep_fixes.py', 'build_corpus_lift.py']
    ledger = ROOT / 'RAG_GUIDELINE_ORACLE_CEILING_LOCAL'
    tasks = json.loads((ledger / 'trial_tasks_11_all4.json').read_text())
    ext = {e['case_key']: e for e in json.loads((ledger / 'trial_extraction_k30all4clean_groups.json').read_text())}
    lift = json.loads((ledger / 'corpus_lift_table_all4.json').read_text())
    lookups = defaultdict(set)
    for t in tasks:
        for c in t['candidates']:
            for f in ext[t['case_key']]['findings']:
                for field in ('label', 'canonical'):
                    key = eng.norm(c['label']) + '||' + eng.norm(f.get(field))
                    if key in lift:
                        lookups[key].add(t['case_key'])
    shared = {k: sorted(v) for k, v in sorted(lookups.items()) if len(v) > 1}
    result = dict(baseline_commit='bbc036e8a6ec93583be915a4609fe86278ed062c',
                  fixture_type='synthetic_actual_production_functions',
                  network_calls=0, production_files_modified=False,
                  checks=len(rows), all_passed=True, results=rows,
                  source_sha256={str((SRC / p).relative_to(ROOT)): hashlib.sha256((SRC / p).read_bytes()).hexdigest() for p in paths},
                  captured_execution=captured,
                  historical_shared_lookup_keys=dict(count=len(shared), entries=shared,
                      interpretation='Potential shared lookups reconstructed from existing all4 inputs; not a claim that all were consumed or overwritten with unequal values. Exact producer provenance is incomplete.'),
                  limits=['Pass means the current defect is reproducible, not that it is fixed.',
                          'No historical cross-case lift overwrite magnitude or performance effect is inferred.'])
    (HERE / 'auxiliary_reproduction_results.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(dict(checks=len(rows), all_passed=True)))


if __name__ == '__main__':
    main()
