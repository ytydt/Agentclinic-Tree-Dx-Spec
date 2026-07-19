"""Measure the BACKBONE LLM's OWN qualitative leaf-discrimination accuracy with
NO knowledge constraint (no LR / marker / KB injection), then cross-tab it against
the LR-layer verdicts (Layer-A LIRICAL ∪ sibling-level) to design a COLLABORATION
strategy: where do we trust the LLM, where must we inject a quantitative LR?

Same isolated setup as scripts/eval_lr_coverage_isolated.py: hand-curated leaf
candidates (correct + key distractors) and their KEY DIFFERENTIAL findings from
data/eval/lr_coverage_cases.json — so branch/evidence selection error is removed
and we test ONLY the discrimination step.

For each gold-favoring finding we ask the LLM (temp 0, no KB): among the shuffled
candidate diagnoses, which ONE does this finding most support? (or -1 = does not
discriminate). We score:
  * llm_correct  : picked the gold diagnosis
  * llm_abstain  : answered -1 (non-discriminating)
and bucket by the LR verdict from logs/lr_coverage_all.json:
  * LR→gold  (sibling LR ≥2 toward gold)  — LR would also discriminate
  * LR ~tie  (sibling computable but <2)   — LR says shared
  * LR none  (no Layer-A, no grounded-B)   — quantitative-only-impossible zone

    PYTHONPATH=src python scripts/eval_llm_qualitative_discrimination.py [--reps 1]
Requires the gnn-llm env + VPN (OpenRouter).
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
os.environ.setdefault("TREE_DX_USE_PROXY", "1")

DATA = PROJECT_ROOT / "data"


def _extract_json(txt: str) -> dict:
    depth = start = 0
    for i, ch in enumerate(txt):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(txt[start:i + 1])
                except Exception:
                    continue
    return {}


def make_picker(model: str, temperature: float = 0.0):
    from agentclinic_tree_dx import llm_client
    sess = llm_client._openrouter_session
    key = (os.environ.get("OPENROUTER_API_KEY")
           or llm_client._OPENROUTER_KEY2)
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    sysp = (
        "You are a diagnostic reasoning assistant. You are given ONE clinical "
        "finding and a numbered list of candidate diagnoses. Decide which SINGLE "
        "candidate the finding most specifically supports OVER the others, using "
        "only your own medical knowledge. If the finding is roughly equally "
        "consistent with two or more of them (i.e. it does NOT discriminate among "
        "these specific candidates), answer -1. Do NOT explain. Return STRICT "
        'JSON: {"index": <int>, "confidence": "high"|"medium"|"low"}.')

    def pick(finding: str, candidates: list[str]) -> dict:
        numbered = "\n".join(f"{i}: {c}" for i, c in enumerate(candidates))
        user = (f"Finding: {finding}\n\nCandidate diagnoses:\n{numbered}\n\n"
                "Which single candidate does this finding most specifically "
                "support over the others? (-1 if it does not discriminate.)")
        for attempt in range(4):
            try:
                r = sess.post("https://openrouter.ai/api/v1/chat/completions",
                              headers=headers,
                              json={"model": model, "temperature": temperature,
                                    "messages": [
                                        {"role": "system", "content": sysp},
                                        {"role": "user", "content": user}]},
                              timeout=90)
                obj = _extract_json(r.json()["choices"][0]["message"]["content"])
                return {"index": int(obj.get("index", -99)),
                        "confidence": str(obj.get("confidence", "")).lower()}
            except Exception:
                time.sleep(2 * (attempt + 1))
        return {"index": -99, "confidence": "error"}
    return pick


def load_lr_verdicts() -> dict:
    """(case,finding) → {'a_auto': bool, 'sib': float|None, 'b_grounded': bool}."""
    path = PROJECT_ROOT / "logs" / "lr_coverage_all.json"
    out = {}
    if not path.exists():
        return out
    for r in json.loads(path.read_text()):
        sib = r.get("sibling")
        sib_lr = None
        if isinstance(sib, dict):
            sib_lr = sib.get("lr_sibling")
        elif isinstance(sib, str) and "lr_sibling" in sib:
            try:
                sib_lr = json.loads(sib.replace("'", '"')).get("lr_sibling")
            except Exception:
                sib_lr = None
        out[(r["case"], r["finding"])] = {
            "a_auto": r.get("A_auto") not in (None, "None"),
            "sib_lr": sib_lr,
            "b_grounded": bool((r.get("B") or {}).get("grounded")) if isinstance(r.get("B"), dict) else False,
        }
    return out


def lr_bucket(v: dict | None) -> str:
    if not v:
        return "LR_none"
    sib = v.get("sib_lr")
    if isinstance(sib, (int, float)) and sib >= 2.0:
        return "LR→gold"
    if isinstance(sib, (int, float)):
        return "LR~tie"
    if v.get("a_auto") or v.get("b_grounded"):
        return "LR→gold"   # A-layer or grounded-B present (directional) but no sibling comparator
    return "LR_none"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="meta-llama/llama-3.3-70b-instruct")
    ap.add_argument("--reps", type=int, default=1,
                    help="repeat each item N times (stability); majority pick scored")
    ap.add_argument("--corpus", default="all",
                    choices=["all", "medbullets", "rarearena"])
    ap.add_argument("--tag", default="", help="output filename suffix")
    args = ap.parse_args()

    ds = json.loads((DATA / "eval" / "lr_coverage_cases.json").read_text())
    cases = [c for c in ds["cases"]
             if args.corpus == "all" or c["corpus"] == args.corpus]
    lr_verdicts = load_lr_verdicts()
    if not lr_verdicts:
        print("[WARN] logs/lr_coverage_all.json missing — run "
              "eval_lr_coverage_isolated.py first for the LR cross-tab.")

    temp = 0.0 if args.reps <= 1 else 0.4  # need variance for a stability check
    pick = make_picker(args.model, temperature=temp)
    print(f"LLM qualitative discrimination (model={args.model}, NO knowledge, "
          f"reps={args.reps}, temp={temp})\n")

    rows = []
    agg = defaultdict(lambda: defaultdict(int))          # corpus → metric
    xtab = defaultdict(lambda: defaultdict(int))         # lr_bucket → llm outcome
    hdr = (f"{'finding':<42} {'candidates(shuffled)':<4} "
           f"{'LLMpick':<26} {'conf':<7} {'ok':<4} {'LRbucket':<9}")
    for case in cases:
        gold = case["gold"]
        distractors = case.get("distractors", [])
        print(f"══ [{case['corpus']}] {case['id']}  gold={gold}")
        for fnd in case["findings"]:
            if fnd.get("favors") != "gold":
                continue
            finding = fnd["finding"]
            cand = [gold] + list(distractors)
            rng = random.Random(hash(finding) & 0xFFFFFFFF)
            order = list(range(len(cand)))
            rng.shuffle(order)
            shown = [cand[i] for i in order]
            gold_pos = shown.index(gold)

            picks = []
            for _ in range(args.reps):
                picks.append(pick(finding, shown))
            # majority index + agreement (stability)
            idxs = [p["index"] for p in picks]
            maj = max(set(idxs), key=idxs.count)
            agree = idxs.count(maj) / len(idxs)
            conf = picks[idxs.index(maj)]["confidence"]
            picked_label = (shown[maj] if 0 <= maj < len(shown)
                            else ("(abstain -1)" if maj == -1 else "(parse-err)"))
            correct = (maj == gold_pos)
            abstain = (maj == -1)

            v = lr_verdicts.get((case["id"], finding))
            bucket = lr_bucket(v)

            c = case["corpus"]
            agg[c]["n"] += 1
            agg[c]["correct"] += int(correct)
            agg[c]["abstain"] += int(abstain)
            agg[c]["agree_sum"] += agree
            agg[c]["unstable"] += int(agree < 1.0)
            xtab[bucket]["n"] += 1
            xtab[bucket]["llm_correct"] += int(correct)
            xtab[bucket]["llm_abstain"] += int(abstain)

            rows.append({"case": case["id"], "corpus": c, "finding": finding,
                         "gold": gold, "shown": shown, "llm_index": maj,
                         "llm_pick": picked_label, "confidence": conf,
                         "correct": correct, "abstain": abstain,
                         "agreement": round(agree, 2), "reps": args.reps,
                         "lr_bucket": bucket,
                         "sib_lr": (v or {}).get("sib_lr")})
            ok = "✓" if correct else ("~" if abstain else "✗")
            print(f"  {finding[:42]:<42} {len(shown):<4} "
                  f"{picked_label[:26]:<26} {conf:<7} {ok:<4} {bucket}")
        print()

    print("=" * 74)
    print("LLM-ALONE QUALITATIVE DISCRIMINATION (no knowledge)")
    for c in sorted(agg):
        m = agg[c]
        n = max(1, m["n"])
        stab = (f"   mean-agreement: {m['agree_sum']/n:.2f}  unstable: {m['unstable']}"
                if args.reps > 1 else "")
        print(f"  [{c}]  n={m['n']}  correct(pick gold): {m['correct']}/{m['n']} "
              f"({100*m['correct']//n}%)   abstain(-1): {m['abstain']}{stab}")

    print("\nCROSS-TAB — LLM correctness by LR-layer verdict (collaboration map)")
    print(f"  {'LR bucket':<10} {'n':>4} {'LLM correct':>13} {'LLM abstain':>12}")
    for b in ("LR→gold", "LR~tie", "LR_none"):
        m = xtab.get(b)
        if not m:
            continue
        n = max(1, m["n"])
        print(f"  {b:<10} {m['n']:>4} {m['llm_correct']:>8} "
              f"({100*m['llm_correct']//n:>3}%) {m['llm_abstain']:>8}")

    suffix = f"_{args.tag}" if args.tag else ""
    out = PROJECT_ROOT / "logs" / f"llm_qual_discrim_{args.corpus}{suffix}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2, default=str))
    print(f"\ndetail → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
