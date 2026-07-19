import json, sys
from pathlib import Path

idxs = [int(x) for x in sys.argv[1:]] or [9,13,17,18,22,23,1,14,24]
for idx in idxs:
    p = Path(f"logs/anatomy/case_{idx}.json")
    if not p.exists():
        print(f"-- case {idx}: no trace"); continue
    tr = json.loads(p.read_text())
    print("\n" + "#"*100)
    print(f"# CASE {idx}")
    print("#"*100)
    for e in tr:
        m, d = e["module"], e["parsed"]
        if m == "RootSelector":
            if isinstance(d, dict):
                print(f"[Root] label={d.get('root_label') or d.get('label')!r} "
                      f"time={d.get('time_course')!r} excl={d.get('excluded_candidates')}")
        elif m == "BranchCreator":
            brs = d.get("branches") or d.get("raw_branches") or [] if isinstance(d,dict) else []
            print(f"[Branches] ({len(brs)})")
            for b in brs:
                if isinstance(b, dict):
                    print(f"    - {b.get('label')!r:55} role={b.get('level_role','')!r} "
                          f"axis={b.get('classification_axis','')!r} prior={b.get('prior')}")
        elif m == "SubBranchCreator":
            sb = d.get("sub_branches", []) if isinstance(d,dict) else []
            if sb:
                labs=[x.get('label') for x in sb if isinstance(x,dict)]
                print(f"  [SubBranch] {labs}")
        elif m == "AnswerMapper":
            print("[AnswerMapper] FULL:")
            print(json.dumps(d, ensure_ascii=False, indent=2)[:2500])
