"""MCR counterpart of recall_vs_rescue.py.

MCR is free-text scored by the Prompt-7 LLM judge (``diagnostic_hit``), not a
4-way MCQ, so the "rescue" channel that dominates DA option@1 should be much
smaller here. Same matcher as the DA script so recall numbers are comparable.

Usage: python3 analysis/backbone_v1/recall_vs_rescue_mcr.py
"""

from __future__ import annotations

import glob
import json
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "paper"))
sys.path.insert(0, str(ROOT / "src"))

import diagnosisarena_l2_pipeline as l2p  # noqa: E402

from agentclinic_tree_dx.knowledge.disease_name_resolver import (  # noqa: E402
    DiseaseNameResolver,
)

RESOLVER = DiseaseNameResolver()

APHHM = ROOT / "logs/medcasereasoning_mcr_val_seq100_v1/aphhm_clean_v1/annotate"
BACKBONE = ROOT / "logs/backbone_v1/medcasereasoning"
BASELINES = ROOT / "runs/paper_v1/medcasereasoning_mcr_val_seq100_v1"

BACKBONE_ARMS = {
    "v0_s4b_k5": "骨干 v0 (4 调用)",
    "e7_k3_comp_k5": "骨干 e7 (6 调用)",
    "e9_perfact_k5": "骨干 e9",
    "e19_atom_ranked_m16_k5": "骨干 e19",
}
BASELINE_ARMS = {
    "B00-direct-cot": "基线 B00 直接 CoT",
    "B06-mac-single-vendor": "基线 B06 MAC",
    "B07-meddxagent-complete": "基线 B07 MEDDx",
    "B12-sc-cot-5": "基线 B12 SC-CoT",
}


def match(a: str, b: str) -> bool:
    return l2p._label_match(a, b, RESOLVER)


def judge(eval_dir: Path) -> tuple[dict[str, str], dict[str, bool]]:
    gold: dict[str, str] = {}
    hit: dict[str, bool] = {}
    for f in glob.glob(str(eval_dir / "case_scores" / "*.json")):
        doc = json.loads(Path(f).read_text())
        cid = str(doc["case_id"])
        gold[cid] = str(doc["gold_diagnosis"])
        hit[cid] = bool(doc["diagnostic_hit"])
    return gold, hit


def aphhm_candidates() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for f in glob.glob(str(APHHM / "case_results" / "*.json")):
        doc = json.loads(Path(f).read_text())
        cid = str(doc["case_id"])
        ranked = [
            x["label"]
            for x in ((doc.get("l2") or {}).get("final_ranking_labels") or [])
        ]
        tree = APHHM / "shared_trees" / f"{cid}.json"
        rest: list[str] = []
        if tree.is_file():
            state = json.loads(tree.read_text())
            branches = (
                state.get("branches") or (state.get("state") or {}).get("branches") or {}
            )
            if isinstance(branches, dict):
                branches = list(branches.values())
            rest = [
                str(b.get("label")) for b in branches if int(b.get("level") or 0) == 2
            ]
        out[cid] = list(dict.fromkeys(ranked + rest))
    return out


def jsonl_candidates(path: Path) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for line in path.read_text().splitlines():
        row = json.loads(line)
        cid = str(row.get("source_id") or row.get("case_id"))
        out[cid] = list(row.get("ordered_diagnoses") or row.get("top2_diagnoses") or [])
    return out


def main() -> int:
    arms: dict[str, tuple[dict, dict, dict]] = {}
    gold, hit = judge(APHHM / "official_eval_llm_compat")
    arms["APHHM 干净 (~300 调用)"] = (aphhm_candidates(), gold, hit)
    for arm, label in BACKBONE_ARMS.items():
        base = BACKBONE / arm
        ev = base / "annotate" / "official_eval_llm"
        if not ev.is_dir():
            continue
        g, h = judge(ev)
        arms[label] = (jsonl_candidates(base / "predictions.jsonl"), g, h)
    for arm, label in BASELINE_ARMS.items():
        base = BASELINES / arm / "replicate_01"
        ev = base / "annotate" / "official_eval_llm"
        if not ev.is_dir():
            continue
        g, h = judge(ev)
        arms[label] = (jsonl_candidates(base / "predictions.jsonl"), g, h)

    print("=== MCR mcr_val_seq100_v1：等长召回 + 命中来源分解（Prompt-7 LLM 裁判）===")
    print(
        f'{"臂":22s} {"表长":>5s} {"r@1":>5s} {"r@2":>5s} {"r@5":>5s} '
        f'{"r@全表":>6s} {"Acc@1":>6s} {"召回内":>6s} {"捡漏":>5s} '
        f'{"捡漏占比":>8s} {"转化":>5s}'
    )
    state: dict[str, dict] = {}
    for label, (cands, g, h) in arms.items():
        keys = [c for c in cands if c in g and c in h]
        if not keys:
            print(f"{label:22s} (无可用交集)")
            continue
        at = lambda k: sum(  # noqa: E731
            1 for c in keys if any(match(x, g[c]) for x in cands[c][:k])
        ) / len(keys)
        recalled = {c for c in keys if any(match(x, g[c]) for x in cands[c])}
        hin = sum(1 for c in recalled if h[c])
        hout = sum(1 for c in keys if c not in recalled and h[c])
        total = hin + hout
        state[label] = {"recalled": recalled, "hit": h, "keys": set(keys)}
        share = f"{hout / total:8.0%}" if total else f'{"n/a":>8s}'
        print(
            f"{label:22s} {st.mean(len(cands[c]) for c in keys):5.1f} "
            f"{at(1):5.2f} {at(2):5.2f} {at(5):5.2f} {at(10**6):6.2f} "
            f"{total / len(keys):6.2f} {hin / len(keys):6.2f} "
            f"{hout / len(keys):5.2f} {share} "
            f"{hin / len(recalled) if recalled else 0:5.2f}"
        )

    print("\n逐例分歧归因（两臂召回状态相同 = 分歧不由召回解释）:")
    labels = list(state)
    for i, x in enumerate(labels):
        for y in labels[i + 1 :]:
            keys = state[x]["keys"] & state[y]["keys"]
            disc = [c for c in keys if state[x]["hit"][c] != state[y]["hit"][c]]
            if not disc:
                continue
            same = sum(
                1
                for c in disc
                if (c in state[x]["recalled"]) == (c in state[y]["recalled"])
            )
            print(
                f"  {x:22s} vs {y:22s} 分歧 {len(disc):2d} 例，"
                f"{same:2d} 例召回状态相同 ({same / len(disc):.0%})"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
