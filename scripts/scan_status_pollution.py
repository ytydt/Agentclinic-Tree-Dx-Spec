import json, glob, os, re
from collections import Counter, defaultdict

# scan every experiment JSON; cross-tabulate status x (pred validity)
VALID = set("ABCDE")
status_counter = Counter()
xx_pred = Counter()          # pred values among XX (wrong) records
ok_pred = Counter()
suspicious = []              # XX records whose pred is not a valid letter
err_examples = defaultdict(list)

groups = defaultdict(Counter)  # matrix-prefix -> status counter
def matrix_of(base):
    m = re.match(r'medbullets_conc_([a-z0-9]+?)(_|$)', base)
    # finer: bucket by known prefixes
    for p in ('u29','n5_rp','n5','rq_mg_cc','rq_mg','rq_cc','nrq_mg_cc','nrq_mg','nrq_cc',
              'rp_on_bk_on','rp_on_bk_off','bk_on','bk_off'):
        if base.startswith('medbullets_conc_'+p):
            return p
    return 'other'

files = [f for f in glob.glob('logs/medbullets_conc_*.json')
         if '_billing_poisoned' not in f]
for f in files:
    base = os.path.basename(f)
    try:
        d = json.load(open(f))
    except Exception:
        continue
    mx = matrix_of(base)
    for r in d:
        s = r.get('status'); p = (r.get('pred') or '').upper()
        status_counter[s] += 1
        groups[mx][s] += 1
        if s == 'XX':
            xx_pred[p] += 1
            if p not in VALID:
                suspicious.append((base, r.get('idx'), p, (r.get('error') or '')[:60]))
        elif s == 'OK':
            ok_pred[p] += 1
        elif s in ('ERR','PROTO','TIMEOUT'):
            if len(err_examples[s]) < 5:
                err_examples[s].append((base, r.get('idx'), (r.get('error') or '')[:90]))

print("=== overall status counts ===")
for s, n in status_counter.most_common():
    print(f"  {s}: {n}")
print("\n=== pred distribution among XX (wrong) ===")
for p, n in xx_pred.most_common():
    print(f"  pred={p!r}: {n}")
print("\n*** SUSPICIOUS: XX records with INVALID pred (program-noanswer counted as wrong) ***")
print(f"  total suspicious XX: {len(suspicious)}")
for ex in suspicious[:40]:
    print("   ", ex)
print("\n=== ERR/PROTO/TIMEOUT examples ===")
for s, exs in err_examples.items():
    print(f"  {s}:")
    for e in exs:
        print("    ", e)
print("\n=== status by matrix ===")
for mx in sorted(groups):
    c = groups[mx]
    tot = sum(c.values())
    print(f"  {mx:16} total={tot:4}  " + " ".join(f"{k}={v}" for k,v in c.most_common()))
