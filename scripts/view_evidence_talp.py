import json, sys
from pathlib import Path
for idx in [int(x) for x in sys.argv[1:]] or [9,22,13]:
    tr = json.loads(Path(f"logs/anatomy/case_{idx}.json").read_text())
    print("\n"+"#"*90+f"\n# CASE {idx}\n"+"#"*90)
    for e in tr:
        m,d = e["module"], e["parsed"]
        if m=="EvidenceAnnotator" and isinstance(d,dict):
            print("\n--- EvidenceAnnotator ---")
            print(json.dumps(d, ensure_ascii=False, indent=1)[:1800])
        elif m=="TemporaryAnalyticLeafPlanner" and isinstance(d,dict):
            cl=d.get("candidate_leaves_ranked",[])
            if cl:
                print("\n--- TALP top candidates ---")
                for c in cl[:4]:
                    if isinstance(c,dict):
                        print(f"  score={c.get('total_score')} fn={c.get('primary_function')} "
                              f"targets={c.get('target_branches')} :: {str(c.get('content'))[:90]}")
