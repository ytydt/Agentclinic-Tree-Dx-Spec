#!/usr/bin/env python3
"""Rebuild the audit register and validate delivery against frozen source blobs.

This does not run a clinical experiment or mark the reproduced bugs fixed.
Run the four bounded reproduction scripts before invoking this aggregator.
"""
from __future__ import annotations
import ast
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
SUP = HERE.parent / 'RULE_STAGE_SCOPE_SUPPLEMENT'
BASE = 'bbc036e8a6ec93583be915a4609fe86278ed062c'
PARTS = [
    ('identity_defects.json', 'semantic_identity.md'),
    ('engine_defects.json', 'engine_structures.md'),
    ('upstream_defects.json', 'upstream_integrity.md'),
    ('auxiliary_defects.json', 'auxiliary_integrity.md'),
]


def read(name):
    return json.loads((HERE / name).read_text())


def dump(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n')


def source_blob(path):
    result = subprocess.run(['git', 'show', f'{BASE}:{path}'], cwd=ROOT,
                            check=True, capture_output=True)
    assert not result.stdout.startswith(b'version https://git-lfs.github.com/spec/v1'), path
    return result.stdout


def main():
    records, anchors = [], []
    for filename, report in PARTS:
        data = read(filename)
        assert isinstance(data['defects'], list)
        for item in data['defects']:
            d = dict(item)
            d['catalog_source'] = filename
            d['analysis_report'] = report
            assert d['fix_class'] in {'code_only', 'hybrid_semantic', 'design_policy'}, d
            assert d.get('title') and d.get('proposal') and d.get('limits'), d['id']
            for mid in d.get('prior_migration_ids', []):
                assert re.fullmatch(r'M(?:0[1-9]|1[0-9]|2[0-5])', mid), (d['id'], mid)
            da = d.get('anchors', [])
            if not da and d.get('file'):
                da = [dict(file=d['file'], line=(d.get('lines') or [1])[0])]
            assert da, (d['id'], 'missing source anchors')
            for a in da:
                anchors.append(dict(defect_id=d['id'], **a))
            records.append(d)
    ids = [d['id'] for d in records]
    assert len(ids) == len(set(ids)), 'duplicate audit identifiers'
    source_files = {}
    for a in anchors:
        path = a.get('file') or a.get('path')
        assert path, a
        if path not in source_files:
            blob = source_blob(path)
            source_files[path] = dict(sha256=hashlib.sha256(blob).hexdigest(),
                                      bytes=len(blob), line_count=len(blob.splitlines()))
            local = ROOT / path
            if local.exists():
                assert local.read_bytes() == blob, ('production changed from base', path)
        line = a.get('line') or a.get('start_line')
        if line is not None:
            assert 1 <= int(line) <= source_files[path]['line_count'], a

    overlap = [
        dict(ids=['ENG-03', 'IDN-09'], relation='same pre-group dedup defect, different consequences'),
        dict(ids=['ENG-04', 'IDN-10'], relation='same repeated-evidence family, semantic and scoring facets'),
        dict(ids=['ENG-13', 'IDN-03'], relation='candidate identity family; exact label overwrite versus alias/case identity'),
        dict(ids=['ENG-18', 'IDN-08'], relation='numeric parser and downstream action consumers are related stages'),
        dict(ids=['UP-10', 'UP-11', 'IDN-08'], relation='source parse, source license and patient comparison are distinct linked stages'),
        dict(ids=['UP-01', 'UP-18', 'AUX-01', 'AUX-02'], relation='incomplete identity/state family with different caches and consumers'),
    ]
    for g in overlap:
        assert set(g['ids']) <= set(ids)
    counts = dict(Counter(d['fix_class'] for d in records))
    tech = read('semantic_repair_matrix.json')
    mapped = [d for t in tech['tasks'] for d in t['defects']]
    hybrid = {d['id'] for d in records if d['fix_class'] == 'hybrid_semantic'}
    assert set(mapped) == hybrid and len(mapped) == len(set(mapped)), 'incomplete hybrid technology mapping'
    reg = dict(schema_version='implementation_defect_register/1.0', baseline_commit=BASE,
               status='audit_and_proposals_only', number_of_audit_items=len(records),
               counting_unit='engineering audit items; overlapping facets, not independent bugs or clinical error rate',
               class_counts=counts, overlapping_families=overlap,
               defects=records, production_source_manifest=source_files)
    dump(HERE / 'defect_registry.json', reg)

    classes = {'code_only': '确定性代码约束', 'hybrid_semantic': '代码保护＋语义恢复', 'design_policy': '先明确设计政策'}
    md = ['# 统一缺陷索引', '', f'冻结输入 `{BASE}`。共 **{len(records)} 个审计工作项**，含共享机制的不同侧面；不是独立 bug 数、临床错误率或因果贡献数。', '',
          '分类以所提修复边界为准：纯代码能保护已有信息，不能自动恢复源文已经遗失的语义。完整记录、历史路径适用性和重叠关系见 [defect_registry.json](defect_registry.json)。', '',
          '| ID | 实现问题 | 修复边界 | 具体证据 |', '|---|---|---|---|']
    for d in records:
        title = d['title'].replace('|', '/')
        md.append(f"| {d['id']} | {title} | {classes[d['fix_class']]} | [{d['analysis_report']}]({d['analysis_report']})；{', '.join(d.get('reproduction_ids', []))} |")
    md += ['', '## 共享机制，不能重复当作独立发现', '']
    md += ['- ' + ', '.join(g['ids']) + '：' + g['relation'] for g in overlap]
    (HERE / 'defect_catalog.md').write_text('\n'.join(md) + '\n')

    identity = read('identity_reproduction_results.json')
    engine = read('reproduce_engine_defects_results.json')
    upstream = read('reproduce_upstream_defects_results.json')
    aux = read('auxiliary_reproduction_results.json')
    assert identity['all_passed'] and upstream['all_assertions_passed'] and aux['all_passed']
    assert engine['validation']['production_modified'] is False
    assert engine['validation']['historical_packs_read'] == 44
    assert engine['validation']['synthetic_witnesses_passed'] == len(engine['witnesses'])
    reproduction_summary = dict(
        identity=dict(checks=identity['n_checks'], scope=identity['scope']),
        engine=dict(checks=len(engine['witnesses']), historical_packs=44,
                    scope='finite real-function witnesses including controls, plus structural historical inventory'),
        upstream=dict(defect_or_boundary_witnesses=upstream['reproduction_count'],
                      correct_behavior_controls=upstream.get('control_count', len(upstream.get('controls', []))),
                      scope='real-function/isolated-entrypoint witnesses and controls; static boundary clearly labelled'),
        auxiliary=dict(checks=aux['checks'], scope='six real-function synthetic checks plus potential historical lookup sharing'),
    )
    mandatory = [HERE / n for n in ['REPORT.md','README.md','REPAIR_PLAN.md','INDEPENDENT_REVIEW.md','semantic_binding_research.md','identity_sources.json']]
    mandatory += [SUP / n for n in ['REPORT.md','README.md','SEMANTIC_SUPPLEMENT.md','INDEPENDENT_REVIEW.md','supplemental_examples.json','supplemental_vectors.json','validate_supplement.py','supplement_validation.json']]
    for p in mandatory:
        assert p.exists(), ('missing deliverable', str(p))
    supplement = json.loads((SUP / 'supplement_validation.json').read_text())
    assert supplement['status'] == 'passed' and not supplement['clinical_use_authorized']
    assert not supplement['production_code_modified']
    for path, digest in supplement['file_sha256'].items():
        assert hashlib.sha256((SUP / path).read_bytes()).hexdigest() == digest, ('stale supplement validation', path)
    for folder in (HERE, SUP):
        review = json.loads((folder / 'review_checks.json').read_text())
        assert review['status'] == 'passed', ('independent review not passed', folder.name)
    json_count = python_count = links = 0
    secret = re.compile(r'(?:sk-or-v1-[A-Za-z0-9]{30,}|ghp_[A-Za-z0-9]{30,})')
    for folder in (HERE, SUP):
        for p in sorted(folder.rglob('*')):
            if not p.is_file() or '__pycache__' in p.parts:
                continue
            assert p.stat().st_size < 20_000_000, ('unexpected large artifact', p)
            if p.suffix not in {'.py', '.json', '.md'}:
                continue
            text = p.read_text()
            assert not secret.search(text), ('credential-like content', p.name)
            if p.suffix == '.json':
                json.loads(text)
                json_count += 1
            elif p.suffix == '.py':
                ast.parse(text)
                python_count += 1
            else:
                for dest in re.findall(r'\[[^\]]*\]\(([^\s)]+)\)', text):
                    if re.match(r'[a-z]+:', dest) or dest.startswith('#'):
                        continue
                    dest = dest.split('#', 1)[0]
                    if not dest:
                        continue
                    target = (p.parent / dest).resolve()
                    generated = {HERE / 'delivery_validation.json', HERE / 'delivery_manifest.json'}
                    assert target.exists() or target in generated, ('broken relative link', p.name, dest)
                    links += 1
    exclusions = {'delivery_validation.json', 'delivery_manifest.json'}
    manifest = {}
    for folder in (HERE, SUP):
        for p in sorted(folder.rglob('*')):
            if p.is_file() and '__pycache__' not in p.parts and p.name not in exclusions:
                b = p.read_bytes()
                manifest[str(p.relative_to(ROOT))] = dict(bytes=len(b), sha256=hashlib.sha256(b).hexdigest())
    dump(HERE / 'delivery_manifest.json', dict(baseline_commit=BASE, files=manifest,
         manifest_excludes_own_manifest_and_validation=True, count=len(manifest)))
    validation = dict(status='passed', baseline_commit=BASE,
        audit_items=len(records), class_counts=counts, source_files=len(source_files),
        hybrid_items_with_research_plan=len(mapped), semantic_technology_tasks=len(tech['tasks']),
        supplement_finite_validation={k:supplement[k] for k in ('status','rules','branch_sets','vectors')},
        source_anchors_checked=len(anchors), reproduction_results=reproduction_summary,
        json_files_parsed=json_count, python_files_parsed=python_count,
        local_markdown_links_resolved=links, manifest_files=len(manifest),
        production_files_match_frozen_commit=True,
        limitations=['Checks are artifact/code consistency, not clinical error rates or fixed production behavior.',
                     'Task2 finite behavior and independent counterexamples are recorded in its own validation artifacts.',
                     'Audit item classes and evidence applicability need the linked human-readable review.'])
    dump(HERE / 'delivery_validation.json', validation)
    print(json.dumps({k:validation[k] for k in ('status','audit_items','class_counts','source_files','manifest_files')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
