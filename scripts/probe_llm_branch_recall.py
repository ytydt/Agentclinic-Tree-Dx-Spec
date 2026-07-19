"""Estimate CURRENT LLM BranchCreator key-branch recall from existing per-case logs.

For each text case, across all available runs, extract the L1 branch labels the
LLM produced and check whether the gold disease's family is covered (token
overlap between gold canonical tokens and a branch label, or gold tokens present
in a label). Reports per-run recall (how often the correct family was created) —
the variance of which is the §22.8 problem.
"""
from __future__ import annotations
import csv, ast, glob, json, re, sys
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
DATA = PROJECT_ROOT / "data" / "knowledge_raw"
TSV = Path("/home/wanghongyi/LLM-Structured-Data-main/som/MMLU/test/medbullets_hard_test.tsv")
DIAGNOSIS_CUES = ("most likely diagnosis","most likely cause","most likely underlying","which of the following is the most likely","best explains","most consistent with","underlying diagnosis","responsible for","most likely responsible","best describes")
IMAGE_CUES = ("figure","shown in","image","photograph","ecg as seen","as shown")

# gold canonical token sets per text idx (incl. mechanism→disease + family synonyms)
GOLD_FAMILY_TOKENS = {
    1:  [{"pancoast"},{"apical","lung"},{"lung","tumor"},{"lung","cancer"},{"superior","sulcus"}],
    9:  [{"leukemoid"},{"reactive"},{"reaction"},{"non","malignant"},{"infection"},{"leukocytosis"}],
    13: [{"glucagonoma"},{"alpha","cell"},{"neuroendocrine"},{"pancreatic","tumor"},{"islet"}],
    14: [{"aortic","regurgitation"},{"aortic","insufficiency"},{"diastolic","murmur"},{"valv"}],
    17: [{"myeloid","leukemia"},{"myelogenous"},{"cml"},{"myeloproliferative"},{"mpn"}],
    18: [{"peliosis"},{"vascular","ectasia"},{"hepatic"},{"liver"},{"sinusoid"}],
    22: [{"hyperparathyroid"},{"parathyroid"},{"hypercalcemia"},{"pth"}],
    23: [{"adhesion"},{"obstruction"},{"mechanical"},{"small","bowel"}],
    24: [{"foreign","body"},{"aspiration"},{"obstruction"},{"airway"}],
}


def text_indices():
    cases, seen, out = [], set(), []
    with TSV.open(encoding="utf-8") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            try: opts=ast.literal_eval(row["options"])
            except Exception: opts={}
            q=row["question"].strip()
            if not opts or not any(c in q.lower() for c in DIAGNOSIS_CUES): continue
            key=q[:120]
            if key in seen: continue
            seen.add(key); cases.append(q)
    for i,q in enumerate(cases):
        if not any(c in q.lower() for c in IMAGE_CUES):
            out.append(i)
    return out


def extract_branch_labels(log_path: Path) -> list[str]:
    """Pull L1 branch labels from BranchCreator JSON blocks in a case log."""
    try:
        txt = log_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []
    labels = []
    for m in re.finditer(r'"id"\s*:\s*"B\d+"[^}]*?"label"\s*:\s*"([^"]{4,80})"', txt, re.DOTALL):
        lab = m.group(1).strip()
        if "MUST be" in lab or "family label" in lab or "specific" in lab.lower():
            continue
        labels.append(lab)
    # de-dup preserve order
    seen=set(); out=[]
    for l in labels:
        if l.lower() not in seen:
            seen.add(l.lower()); out.append(l)
    return out


def covered(labels: list[str], token_sets: list[set]) -> bool:
    for lab in labels:
        lt = set(re.sub(r"[^a-z ]+"," ",lab.lower()).split())
        for ts in token_sets:
            if ts <= lt:
                return True
    return False


def main():
    idxs = text_indices()
    # gather all run dirs that have per-case logs
    run_dirs = sorted(glob.glob(str(PROJECT_ROOT / "logs" / "medbullets_conc_*_cases")))
    print(f"found {len(run_dirs)} run dirs")
    per_idx_runs = defaultdict(list)  # idx -> list[bool] recall per run
    for d in run_dirs:
        dp = Path(d)
        for idx in idxs:
            lp = dp / f"case_{idx:02d}.log"
            if not lp.exists():
                continue
            labels = extract_branch_labels(lp)
            if not labels:
                continue
            per_idx_runs[idx].append(covered(labels, GOLD_FAMILY_TOKENS.get(idx, [])))

    print("\n" + "="*70)
    print("CURRENT LLM BranchCreator — per-run key-branch (gold family) recall")
    print("="*70)
    print(f"{'idx':>3} {'runs':>5} {'hits':>5} {'recall':>7}")
    tot_runs=tot_hits=0
    for idx in idxs:
        r = per_idx_runs.get(idx, [])
        if not r:
            print(f"{idx:>3} {'0':>5}     -       (no logs)")
            continue
        hits=sum(r)
        tot_runs+=len(r); tot_hits+=hits
        print(f"{idx:>3} {len(r):>5} {hits:>5} {hits/len(r):>6.0%}")
    print("-"*70)
    if tot_runs:
        print(f"micro-avg per-run recall: {tot_hits}/{tot_runs} = {tot_hits/tot_runs:.0%}")
    print("="*70)


if __name__ == "__main__":
    main()
