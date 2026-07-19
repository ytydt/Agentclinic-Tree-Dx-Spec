import json, glob, os, re
from collections import defaultdict, Counter

ARMS = ['u29_bk', 'u29_mand', 'u29_clean', 'u29_mand_clean', 'u29_full']
CASEIDS = [1, 9, 13, 14, 17, 18, 22, 23, 24]

# dedup by rep (latest mtime)
def latest_by_rep(arm):
    byrep = {}
    for f in glob.glob(f'logs/medbullets_conc_{arm}_*.json'):
        m = re.match(rf'medbullets_conc_{arm}_(\d+)_\d{{8}}_\d{{6}}\.json', os.path.basename(f))
        if not m:
            continue
        rep = int(m.group(1)); mt = os.path.getmtime(f)
        if rep not in byrep or mt > byrep[rep][0]:
            byrep[rep] = (mt, f)
    return {rep: json.load(open(v[1])) for rep, v in byrep.items()}

# per (arm, case): list of (status, pred, gold) across reps
cell = defaultdict(lambda: defaultdict(list))
gold = {}
for arm in ARMS:
    for rep, recs in latest_by_rep(arm).items():
        for r in recs:
            i = r.get('idx')
            cell[arm][i].append((r.get('status'), (r.get('pred') or '?'), r.get('gold')))
            gold[i] = r.get('gold')

print("Per-case predicted-letter distribution per arm (gold in [])")
print(f"{'case':>4} {'gold':>4} | " + " | ".join(f"{a.replace('u29_',''):^16}" for a in ARMS))
for i in CASEIDS:
    row = f"{i:>4} {str(gold.get(i)):>4} | "
    cells = []
    for a in ARMS:
        recs = cell[a].get(i, [])
        ok = sum(1 for s, p, g in recs if s == 'OK')
        dist = Counter(p for s, p, g in recs if s in ('OK', 'XX'))
        dist_s = ",".join(f"{k}{v}" for k, v in dist.most_common())
        cells.append(f"{ok}/{len(recs)} {dist_s:<10}")
    print(row + " | ".join(f"{c:^16}" for c in cells))

# Per-improvement deltas vs the arm without that improvement
print("\nPer-improvement per-case delta (OK count, K=5):")
pairs = [
    ('mand', 'u29_bk', 'u29_mand'),
    ('clean', 'u29_bk', 'u29_clean'),
    ('mand+clean vs mand', 'u29_mand', 'u29_mand_clean'),
    ('phase (full vs mand_clean)', 'u29_mand_clean', 'u29_full'),
    ('full vs bk', 'u29_bk', 'u29_full'),
]
def okc(arm, i):
    return sum(1 for s, p, g in cell[arm].get(i, []) if s == 'OK')
for name, base, arm in pairs:
    deltas = {i: okc(arm, i) - okc(base, i) for i in CASEIDS}
    tot = sum(deltas.values())
    helped = [f"c{i}+{d}" for i, d in deltas.items() if d > 0]
    hurt = [f"c{i}{d}" for i, d in deltas.items() if d < 0]
    print(f"  {name:28} net={tot:+d}  helped[{', '.join(helped)}]  hurt[{', '.join(hurt)}]")
