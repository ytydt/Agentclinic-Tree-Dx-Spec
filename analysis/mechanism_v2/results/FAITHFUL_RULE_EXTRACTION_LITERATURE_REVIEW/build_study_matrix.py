#!/usr/bin/env python3
"""Rebuild the cross-review catalog; checks artifact consistency, not paper results."""
import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
GROUPS = {
    'modern_fol': 11,
    'semantic_parsing': 9,
    'clinical_llm': 8,
    'clinical_standards': 7,
}

def main():
    rows, checks, source_hashes = [], [], {}
    fields = ['id', 'title', 'url', 'representation', 'method',
              'verification_guarantee', 'not_guaranteed', 'evaluation',
              'transfer_to_repo', 'source_locations']
    for group, expected in GROUPS.items():
        path = ROOT / f'{group}_sources.json'
        content = json.loads(path.read_text())
        entries = content if isinstance(content, list) else content['sources']
        assert len(entries) == expected, (group, len(entries))
        checks.append(f'{group}: {expected} entries')
        source_hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
        for entry in entries:
            for field in fields:
                assert field in entry and entry[field] is not None, (group, entry.get('id'), field)
            assert entry['url'].startswith('https://'), entry['url']
            rows.append({'review_family': group, **entry})
        assert (ROOT / f'{group}_review.md').is_file()
        json.loads((ROOT / f'{group}_search_log.json').read_text())
    assert len({r['id'] for r in rows}) == 35
    matrix = {
        'scope': '35 study/standard entries, not 35 independent experimental papers',
        'review_dates': ['2026-09-05', '2026-09-06'],
        'external_projects_executed': False,
        'source_hashes': source_hashes,
        'studies': rows,
    }
    (ROOT / 'study_matrix.json').write_text(json.dumps(matrix, ensure_ascii=False, indent=2) + '\n')
    for path in ROOT.glob('*.py'):
        ast.parse(path.read_text())
    for path in ROOT.glob('*.json'):
        if path.name != 'delivery_validation.json':
            json.loads(path.read_text())
    for name in ['REPORT.md', 'PROTOCOL.md', 'LITERATURE_INDEPENDENT_REVIEW.md', 'CLINICAL_REVIEW_CHECK.md']:
        assert (ROOT / name).is_file(), name
    validation = {
        'status': 'passed',
        'entry_count': len(rows),
        'group_counts': GROUPS,
        'checks': checks + ['required source metadata', 'unique IDs', 'JSON parsing',
                            'Python syntax', 'four reviews and search logs', 'independent reviews present'],
        'meaning': 'Artifact consistency only; no claim of clinical/extraction validation or external system replication',
    }
    (ROOT / 'delivery_validation.json').write_text(json.dumps(validation, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'status': 'passed', 'entries': len(rows)}))

if __name__ == '__main__':
    main()
