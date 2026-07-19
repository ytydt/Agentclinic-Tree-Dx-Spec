import json, glob, os, re, statistics
from collections import defaultdict

# idx → case number mapping (the --cases order)
CASES = [1, 9, 13, 14, 17, 18, 22, 23, 24]
arms = defaultdict(dict)  # arm -> rep -> (mtime,f,records)
for f in sorted(glob.glob('logs/medbullets_conc_u29_*.json')):
    base = os.path.basename(f)
    m = re.match(r'medbullets_conc_(u29_.+)_(\d+)_\d{8}_\d{6}\.json', base)
    if not m:
        continue
    arm, rep = m.group(1), int(m.group(2))
    try:
        d = json.load(open(f))
    except Exception:
        continue
    mt = os.path.getmtime(f)
    if rep not in arms[arm] or mt > arms[arm][rep][0]:
        arms[arm][rep] = (mt, f, d)

order = ['u29_bk', 'u29_mand', 'u29_clean', 'u29_mand_clean', 'u29_full']
print(f"{'arm':16} {'K':>2} {'acc':>7} {'sd':>5}  perRep%")
arm_caseok = {}
for arm in order:
    byrep = arms.get(arm, {})
    if not byrep:
        print(f"{arm:16}  (none)"); continue
    rep_accs = []
    caseok = defaultdict(lambda: [0, 0])  # idx -> [ok, scored]
    for rep in sorted(byrep):
        _, f, recs = byrep[rep]
        ok = sum(1 for r in recs if r.get('status') == 'OK')
        tot = sum(1 for r in recs if r.get('status') in ('OK', 'XX'))
        rep_accs.append(ok / tot if tot else 0.0)
        for r in recs:
            i = r.get('idx')
            s = r.get('status')
            if s in ('OK', 'XX'):
                caseok[i][1] += 1
                if s == 'OK':
                    caseok[i][0] += 1
    arm_caseok[arm] = caseok
    acc = sum(rep_accs) / len(rep_accs)
    sd = statistics.pstdev(rep_accs) if len(rep_accs) > 1 else 0.0
    print(f"{arm:16} {len(rep_accs):>2} {acc*100:6.1f}% {sd:5.2f}  {['%.0f'%(x*100) for x in rep_accs]}")

# map idx → case number: idx appears to be 0-based position in CASES
idxs = sorted({r.get('idx') for arm in order for rep in arms.get(arm, {})
               for r in arms[arm][rep][2] if r.get('idx') is not None})
print("\ndistinct idx values:", idxs)
print("\nper-case OK/scored (rows=idx→case, cols=arm):")
print("idx case " + "".join(f"{a.replace('u29_',''):>13}" for a in order))
for i in idxs:
    cnum = CASES[i] if isinstance(i, int) and 0 <= i < len(CASES) else '?'
    row = f"{str(i):>3} {str(cnum):>4} "
    for a in order:
        ok, tot = arm_caseok.get(a, {}).get(i, [0, 0])
        row += f"{(str(ok)+'/'+str(tot)):>13}"
    print(row)
