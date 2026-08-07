"""Is the per-case oracle union far above the best single arm, on MCR as on DA?

For each benchmark we collect per-case correctness for every available arm and
compare the observed union against two references:

* ``max`` — the best single arm. If arms were nested, union would equal this.
* ``indep`` — ``1 - prod(1 - p_i)``, the union if arms were independent draws
  with their observed marginal accuracies. If the observed union sits at this
  line, the disjointness is what pure per-case randomness would produce and is
  not evidence of complementary expertise.

Usage: python3 analysis/backbone_v1/union_vs_best_arm.py
"""

from __future__ import annotations

import collections
import glob
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

MCR_APHHM = ROOT / "logs/medcasereasoning_mcr_val_seq100_v1/aphhm_clean_v1/annotate"
MCR_BACKBONE = ROOT / "logs/backbone_v1/medcasereasoning"
MCR_BASELINES = ROOT / "runs/paper_v1/medcasereasoning_mcr_val_seq100_v1"

DA_SLICES = {
    "d2_seq100": {
        "APHHM": "logs/diagnosisarena_d2_m01_v1/aphhm_clean_v1/annotate/mapper/records.json",
        "AB02": "logs/diagnosisarena_d2_m01_v1/c3_ab02_clean_v1/annotate/mapper/records.json",
        "骨干 e7": "logs/backbone_v1/diagnosisarena/e7_k3_comp_k5/mapper/records.json",
        "骨干 v0": "logs/backbone_v1/diagnosisarena/v0_s4b_k5/mapper/records.json",
        "B06": "runs/paper_v1/diagnosisarena_fixed_v1/B06-mac-single-vendor/replicate_01/mapper/records.json",
        "B07": "runs/paper_v1/diagnosisarena_remaining_v1/B07-meddxagent-complete/replicate_01/mapper/records.json",
    },
    "d2_heldout100": {
        "APHHM": "logs/diagnosisarena_heldout_v1/aphhm_clean_v1/annotate/mapper/records.json",
        "骨干 e7": "logs/backbone_v1/diagnosisarena_heldout/e7_k3_comp_k5/mapper/records.json",
        "骨干 v0": "logs/backbone_v1/diagnosisarena_heldout/v0_s4b_k5/mapper/records.json",
        "B06": "runs/paper_v1/diagnosisarena_heldout_v1/B06-mac-single-vendor/replicate_01/mapper/records.json",
        "B07": "runs/paper_v1/diagnosisarena_heldout_v1/B07-meddxagent-complete/replicate_01/mapper/records.json",
    },
}


def judge_hits(eval_dir: Path) -> dict[str, bool]:
    out: dict[str, bool] = {}
    for f in glob.glob(str(eval_dir / "case_scores" / "*.json")):
        doc = json.loads(Path(f).read_text())
        out[str(doc["case_id"])] = bool(doc["diagnostic_hit"])
    return out


def mapper_hits(path: Path) -> dict[str, bool]:
    doc = json.loads(path.read_text())
    rows = doc["records"] if isinstance(doc, dict) and "records" in doc else doc
    return {
        str(r.get("source_id") or r.get("case_id")): bool(r.get("option_top1"))
        for r in rows
    }


def collect_mcr() -> dict[str, dict[str, bool]]:
    arms: dict[str, dict[str, bool]] = {}
    ev = MCR_APHHM / "official_eval_llm_compat"
    if ev.is_dir():
        arms["APHHM"] = judge_hits(ev)
    for d in sorted(MCR_BACKBONE.glob("*")):
        if d.name.startswith("leak_"):
            continue
        ev = d / "annotate" / "official_eval_llm"
        if ev.is_dir():
            arms[f"骨干 {d.name.split('_')[0]}"] = judge_hits(ev)
    for d in sorted(MCR_BASELINES.glob("B*")):
        ev = d / "replicate_01" / "annotate" / "official_eval_llm"
        if ev.is_dir():
            arms[d.name.split("-")[0]] = judge_hits(ev)
    return arms


def analyse(arms: dict[str, dict[str, bool]], title: str) -> None:
    keys = sorted(set.intersection(*[set(v) for v in arms.values()]))
    n = len(keys)
    print(f"\n=== {title}  n={n}，{len(arms)} 个臂 ===")
    accs = {}
    for label, hits in sorted(
        arms.items(), key=lambda kv: -sum(kv[1][c] for c in keys)
    ):
        accs[label] = sum(hits[c] for c in keys) / n
        print(f"  {label:14s} {accs[label]:.2f}")

    union = sum(1 for c in keys if any(arms[a][c] for a in arms)) / n
    inter = sum(1 for c in keys if all(arms[a][c] for a in arms)) / n
    best = max(accs.values())
    indep = 1.0
    for p in accs.values():
        indep *= 1 - p
    indep = 1 - indep
    headroom = (union - best) / (1 - best) if best < 1 else 0.0
    print(f"\n  最强单臂        {best:.2f}")
    print(f"  并集(每例神谕)   {union:.2f}   （比最强单臂高 {union - best:+.2f}）")
    print(f"  并集吃掉的余量   {headroom:.0%}   （余量 = 1 − 最强单臂 = {1 - best:.2f}）")
    print(f"  独立假设下并集   {indep:.2f}   （观测 {union:.2f}，差 {union - indep:+.2f}）")
    print(f"  全臂都对(交集)   {inter:.2f}")
    print(f"  无臂能对        {1 - union:.2f}")

    ct = collections.Counter(sum(arms[a][c] for a in arms) for c in keys)
    m = len(arms)
    print(f"\n  每例答对的臂数分布（0..{m}）:")
    bar = "  " + "".join(f"{k:>5d}" for k in range(m + 1))
    print(bar)
    print("  " + "".join(f"{ct.get(k, 0):>5d}" for k in range(m + 1)))
    contested = sum(v for k, v in ct.items() if 0 < k < m) / n
    print(f"  争议区（有臂对有臂错）占比 {contested:.2f}")


MATCHED = ["APHHM", "骨干 e7", "骨干 v0", "B06", "B07"]


def main() -> int:
    mcr = collect_mcr()
    matched = {k: v for k, v in mcr.items() if k in MATCHED}
    analyse(matched, "MCR 同 5 臂（与 DA 留出切片对齐；Prompt-7 Acc@1）")
    analyse(mcr, "MCR 全部可用臂（Prompt-7 Acc@1）")
    for slice_name, spec in DA_SLICES.items():
        arms = {
            label: mapper_hits(ROOT / p)
            for label, p in spec.items()
            if (ROOT / p).is_file()
        }
        analyse(arms, f"DA {slice_name}（mapper option@1）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
