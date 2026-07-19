import json, sys

with open('logs/smoke_test_20260520_r3.log') as f:
    text = f.read()

evidence_keywords = {
    'blasts': ['35% blasts', 'blast', 'leukocyte count'],
    'vision/neuro': ['blurry vision', 'visual acuity', '20/100', 'ataxic', 'gait', 'headache'],
    'constitutional': ['malaise', 'weakness', 'night sweats', 'constitutional', 'weight loss'],
    'anemia/plt': ['anemia', 'hemoglobin', 'thrombocytopenia', 'platelet'],
    'fever': ['fever', 'temperature'],
    'CML_history': ['history of chronic', 'history of CML', 'absence of'],
    'lymphadenopathy': ['lymphadenopathy', 'splenomegaly'],
    'subacute_onset': ['subacute', 'several days', 'gradual'],
    'electrolytes': ['sodium', 'potassium', 'calcium', 'glucose', 'creatinine'],
}

idx = 0
turn = 0
while True:
    pos = text.find('>>> Module: TemporaryAnalyticLeafPlanner', idx)
    if pos == -1:
        break
    turn += 1

    raw_pos = text.find('RAW LLM RESPONSE:', pos)
    parsed_pos = text.find('PARSED RESULT:', raw_pos)
    if raw_pos == -1 or parsed_pos == -1:
        idx = pos + 40
        continue

    raw_text = text[raw_pos + 18 : parsed_pos].strip()
    json_text = raw_text
    if '```json' in json_text:
        json_text = json_text.split('```json')[1].split('```')[0].strip()
    elif '```' in json_text:
        parts = json_text.split('```')
        if len(parts) >= 3:
            json_text = parts[1].strip()

    obj = None
    try:
        obj = json.loads(json_text)
    except Exception:
        arr_start = json_text.find('[')
        if arr_start >= 0:
            depth = 0
            for j in range(arr_start, len(json_text)):
                if json_text[j] == '[':
                    depth += 1
                elif json_text[j] == ']':
                    depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(json_text[arr_start : j + 1])
                    except Exception:
                        pass
                    break

    if obj is None:
        print(f'Turn {turn}: PARSE FAILED')
        print(f'  First 200 chars: {raw_text[:200]}')
        idx = parsed_pos
        continue

    if isinstance(obj, dict):
        candidates = (obj.get('candidate_leaves_ranked')
                      or obj.get('candidates')
                      or obj.get('candidate_leaves')
                      or [])
    elif isinstance(obj, list):
        candidates = obj
    else:
        candidates = []

    print(f'== Turn {turn}: TALP generated {len(candidates)} candidates ==')

    for c in candidates:
        content = c.get('content', '')
        bid = c.get('branch_id', '?')
        pf = c.get('primary_function', '?')
        eig = c.get('expected_information_gain', 0)
        score = c.get('score', c.get('total_score', 0))

        matched = []
        for kw_name, kw_list in evidence_keywords.items():
            if any(k.lower() in content.lower() for k in kw_list):
                matched.append(kw_name)
        ev_str = '+'.join(matched) if matched else 'NONE'

        print(f'  [{bid}|{pf:12s}|EIG={eig:.2f}|score={score:.2f}] evidence={ev_str}')
        print(f'    Q: {content[:110]}')
    print()
    idx = parsed_pos
