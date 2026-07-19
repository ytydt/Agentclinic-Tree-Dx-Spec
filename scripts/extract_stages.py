import re, json, sys, glob, os

def latest_dir(rep):
    ds = sorted(glob.glob(f'logs/medbullets_conc_u29_full_{rep}_*_cases'),
                key=os.path.getmtime)
    return ds[-1] if ds else None

def block_after(lines, start, marker, maxlines=400):
    """Return text of the RAW LLM RESPONSE block following the n-th module marker."""
    out = []
    grab = False
    for ln in lines[start:start+maxlines]:
        if 'RAW LLM RESPONSE:' in ln:
            grab = True; continue
        if grab and re.match(r'\[20\d\d-', ln) and '>>> Module:' in ln:
            break
        if grab:
            out.append(ln)
    return "\n".join(out)

def extract(case, rep):
    d = latest_dir(rep)
    if not d: return f"(no dir rep{rep})"
    p = os.path.join(d, f"case_{case:02d}.log")
    if not os.path.exists(p): return f"(no log {p})"
    lines = open(p, encoding='utf-8', errors='replace').read().splitlines()
    res = {}
    # RootSelector root_label (last occurrence in a RESPONSE)
    for m in re.finditer(r'"root_label":\s*"([^"]+)"', "\n".join(lines)):
        if 'algorithm above' not in m.group(1):
            res['root'] = m.group(1)
    # BranchCreator branch labels
    labels = re.findall(r'"label":\s*"([^"]+)"', "\n".join(lines))
    res['branch_labels'] = [l for l in labels if 'syndrome-frame' not in l][:8]
    # leader (TALP reasoning_ledger leader)
    lead = re.findall(r'"leader":\s*\{"branch_id":\s*"([^"]+)",\s*"label":\s*"([^"]+)"', "\n".join(lines))
    if lead: res['talp_leader'] = lead[-1]
    # AnswerMapper final + mapping
    am = re.findall(r'"answer_option_mapping":\s*(\{[^}]*\})', "\n".join(lines))
    fa = re.findall(r'"final_answer":\s*"([A-E])"', "\n".join(lines))
    if am: res['answer_mapping'] = am[-1]
    if fa: res['final_answer'] = fa[-1]
    return res

if __name__ == "__main__":
    case = int(sys.argv[1]); reps = [int(x) for x in sys.argv[2:]] or [1,2,3,4,5]
    for rep in reps:
        r = extract(case, rep)
        print(f"\n===== case {case} rep {rep} =====")
        if isinstance(r, str): print(r); continue
        print("root :", r.get('root'))
        print("branches:", r.get('branch_labels'))
        print("TALP leader:", r.get('talp_leader'))
        print("answer_mapping:", r.get('answer_mapping'))
        print("final_answer:", r.get('final_answer'))
