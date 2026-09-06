#!/usr/bin/env python3
"""Validate delivery structure and synthetic fixtures; never run clinical diagnosis."""
import ast
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
DIRS = ['V2_INDEX_DIFFERENTIAL_AUDIT', 'FAITHFUL_RULE_EXTRACTION_LITERATURE_REVIEW',
        'RULE_EXTRACTION_EXECUTION_REDESIGN']
REQUIRED = ['REPORT.md', 'PROTOCOL.md', 'README.md', 'SEMANTIC_CONTRACT.md',
            'EXTRACTION_PROTOCOL.md', 'MIGRATION_MAP.md', 'migration_matrix.json',
            'RESEARCH_ROADMAP.md', 'experiment_matrix.json',
            'ir_examples.json', 'acceptance_vectors.json',
            'DESIGN_INDEPENDENT_REVIEW.md']

def main():
    checks = []
    for name in REQUIRED:
        assert (HERE / name).is_file(), name
        checks.append('present: ' + name)
    fixtures = subprocess.run([sys.executable, str(HERE / 'validate_contract_examples.py')],
                              check=True, text=True, capture_output=True)
    fixture_result = json.loads(fixtures.stdout)
    assert fixture_result['status'] == 'passed'
    secret = re.compile(r'gh[pousr]_[A-Za-z0-9]{30,}|sk-or-v1-[a-f0-9]{40,}')
    for dirname in DIRS[1:]:
        for path in (HERE.parent / dirname).rglob('*'):
            if not path.is_file() or '__pycache__' in path.parts:
                continue
            assert path.stat().st_size < 90_000_000, path.name
            if path.suffix not in {'.md', '.py', '.json', '.jsonl', '.txt'}:
                continue
            content = path.read_text()
            assert not secret.search(content), 'Credential literal in ' + path.name
            if path.suffix == '.json':
                json.loads(content)
            elif path.suffix == '.py':
                ast.parse(content)
            checks.append('parse/credential/size: ' + dirname + '/' + path.name)
    # Validate actual local report links, including production code references.
    # Anchors are navigational; external source availability is recorded by the reviews.
    missing = []
    for dirname in DIRS:
        for path in (HERE.parent / dirname).rglob('*.md'):
            for target in re.findall(r'\]\(([^\s)]+)\)', path.read_text()):
                if re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*:', target) or target.startswith('#'):
                    continue
                local = target.split('#', 1)[0]
                if local and not (path.parent / local).exists():
                    missing.append([str(path.relative_to(REPO)), target])
    assert not missing, missing
    checks.append('all local Markdown links resolve across three task directories')
    task1 = json.loads((HERE.parent / DIRS[0] / 'delivery_validation.json').read_text())
    task2 = json.loads((HERE.parent / DIRS[1] / 'delivery_validation.json').read_text())
    assert task1['passed'] and task2['status'] == 'passed'
    check = subprocess.run(['git', 'diff', '--quiet', '--',
                            'analysis/mechanism_v2/results/RAG_GUIDELINE_ORACLE_CEILING_LOCAL',
                            'scripts/build_statpearls_corpus.py'], cwd=REPO)
    assert check.returncode == 0, 'Tracked production changes detected'
    checks.append('tracked production paths unchanged')
    manifest = []
    for dirname in DIRS:
        for path in sorted((HERE.parent / dirname).rglob('*')):
            if not path.is_file() or '__pycache__' in path.parts:
                continue
            if path.parent == HERE and path.name in {'delivery_manifest.json', 'delivery_validation.json'}:
                continue
            manifest.append({'path': str(path.relative_to(REPO)), 'bytes': path.stat().st_size,
                             'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    result = {'status': 'passed', 'base_commit': '6fa8fd7aa2548cc01ac81f2d5261801190244d27',
              'scope': 'Artifact/link/metadata checks and finite synthetic design fixtures; not clinical accuracy or source fidelity',
              'fixture_result': fixture_result, 'checks': checks,
              'task1_artifact_checks': task1['n_checks'], 'task2_entries': task2['entry_count'],
              'tracked_production_changes': False, 'new_llm_calls': 0}
    (HERE / 'delivery_validation.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    (HERE / 'delivery_manifest.json').write_text(json.dumps({'base_commit': result['base_commit'], 'files': manifest}, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'status': 'passed', 'files': len(manifest), 'bytes': sum(x['bytes'] for x in manifest),
                      'rule_examples': fixture_result['rule_examples'],
                      'acceptance_vectors': fixture_result['acceptance_vectors']}))

if __name__ == '__main__':
    main()
