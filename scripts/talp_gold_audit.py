"""A8(b): independent LLM second-opinion audit of the dataset finding `role`
labels (rule_in_gold / rule_out_distractor / shared_nondiscriminating /
parent_child_trap). Produces a DISAGREEMENT REPORT only — it NEVER edits the
dataset. Any label change requires human clinical sign-off (a coarse or wrong
gold label makes every arm chase a mislabelled target, §A8).

For each finding the auditor sees the candidate list, the gold diagnosis, and
the finding text (NOT the existing label), and classifies the finding's role +
the candidate it most supports/argues-against. We then compare to the dataset
label and list every mismatch with the model's rationale.

Usage:
  python scripts/talp_gold_audit.py --model meta-llama/llama-3.3-70b-instruct
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA = PROJECT_ROOT / "data"
sys.path.insert(0, str(PROJECT_ROOT / "src"))


def _norm(s: str) -> str:
    return " ".join(str(s or "").lower().split())


_AUDIT_PROMPT = (
    "You are auditing a differential-diagnosis TEACHING dataset. Given the GOLD "
    "diagnosis, the full candidate list, and ONE clinical finding, classify the "
    "finding's discriminative ROLE among these candidates — using your own "
    "medical knowledge, NOT any pre-existing label:\n"
    "  * 'rule_in_gold' — the finding specifically supports the GOLD diagnosis "
    "over the others (a positive discriminator for gold).\n"
    "  * 'rule_out_distractor' — the finding argues AGAINST a specific non-gold "
    "candidate (name it).\n"
    "  * 'shared_nondiscriminating' — the finding is roughly equally compatible "
    "with several candidates and does NOT separate them.\n"
    "Return STRICT JSON: {\"role\": \"<one of the three>\", \"target\": "
    "\"<candidate it rules in/out, or none>\", \"confidence\": \"high|medium|low\", "
    "\"why\": \"<one clause>\"}.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="meta-llama/llama-3.3-70b-instruct")
    ap.add_argument("--out", default="logs/talp_gold_audit.json")
    args = ap.parse_args()
    from agentclinic_tree_dx.llm_client import RobustLLMClient
    llm = RobustLLMClient(model=args.model, call_timeout=180, max_retries=4,
                          timeout_retry_cap=2)
    ds = json.loads((DATA / "eval" / "talp_discrimination_cases.json").read_text())

    rows = []
    n_agree = n_total = 0
    for case in ds["cases"]:
        cand_names = [c["name"] for c in case["candidates"]]
        gold = next((c["name"] for c in case["candidates"] if c.get("is_gold")),
                    "")
        for f in case["findings"]:
            label = f.get("role") or "shared_nondiscriminating"
            # parent_child_trap is a structural role; audit it as its DIRECTION
            # equivalent (shared at the family level) to keep 3-way comparison.
            gold_label = ("shared_nondiscriminating"
                          if label == "parent_child_trap" else label)
            try:
                res = llm.call_module("GoldAuditor", _AUDIT_PROMPT,
                                      {"gold_diagnosis": gold,
                                       "candidates": cand_names,
                                       "finding": f["finding"]})
            except Exception as e:  # noqa: BLE001
                print(f"[err] {case['id']}/{f['finding'][:20]}: {e}")
                res = {}
            pred = _norm(res.get("role", ""))
            agree = pred == _norm(gold_label)
            n_total += 1
            n_agree += int(agree)
            rows.append({"case": case["id"], "finding": f["finding"],
                         "dataset_role": label, "llm_role": pred,
                         "llm_target": res.get("target", ""),
                         "confidence": res.get("confidence", ""),
                         "agree": agree, "why": res.get("why", "")})
            flag = "OK " if agree else "!! "
            print(f"{flag}[{case['id']:<16}] {f['finding'][:34]:<34} "
                  f"data={label:<24} llm={pred}", flush=True)

    print("\n" + "=" * 72)
    print(f"gold-label agreement: {n_agree}/{n_total} "
          f"({100*n_agree//max(1,n_total)}%)")
    print("\nDISAGREEMENTS (need human sign-off before any dataset change):")
    for r in rows:
        if not r["agree"]:
            print(f"  [{r['case']:<16}] {r['finding'][:34]:<34} "
                  f"data={r['dataset_role']:<24} llm={r['llm_role']} "
                  f"({r['confidence']}) target={r['llm_target']}  — {r['why']}")
    out = PROJECT_ROOT / args.out
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(
        {"agreement": n_agree / max(1, n_total), "n": n_total, "rows": rows},
        ensure_ascii=False, indent=2))
    print(f"\n  detail → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
