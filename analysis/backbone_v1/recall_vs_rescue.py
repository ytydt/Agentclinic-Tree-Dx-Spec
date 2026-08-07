"""Decompose DA option@1 into recall-driven hits and near-miss rescue hits.

All arms are scored with the same matcher the pipeline uses internally for
``auto_metrics.gold_present`` (``diagnosisarena_l2_pipeline._label_match`` over a
``DiseaseNameResolver``), so recall is comparable across arms that emit very
different numbers of candidates.

Usage: python3 analysis/backbone_v1/recall_vs_rescue.py
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

SLICES = {
    "d2_seq100_v1": {
        "aphhm": "logs/diagnosisarena_d2_m01_v1/aphhm_clean_v1/annotate",
        "backbone_root": "logs/backbone_v1/diagnosisarena",
        "baselines": {
            "B06-mac-single-vendor": "runs/paper_v1/diagnosisarena_fixed_v1",
            "B07-meddxagent-complete": "runs/paper_v1/diagnosisarena_remaining_v1",
        },
    },
    "d2_heldout100_v1": {
        "aphhm": "logs/diagnosisarena_heldout_v1/aphhm_clean_v1/annotate",
        "backbone_root": "logs/backbone_v1/diagnosisarena_heldout",
        "baselines": {
            "B06-mac-single-vendor": "runs/paper_v1/diagnosisarena_heldout_v1",
            "B07-meddxagent-complete": "runs/paper_v1/diagnosisarena_heldout_v1",
        },
    },
}
BACKBONE_ARMS = {"v0_s4b_k5": "骨干 v0 (4 调用)", "e7_k3_comp_k5": "骨干 e7 (6 调用)"}


def match(a: str, b: str) -> bool:
    return l2p._label_match(a, b, RESOLVER)


def read_option_top1(path: Path) -> dict[str, bool]:
    doc = json.loads(path.read_text())
    rows = doc["records"] if isinstance(doc, dict) and "records" in doc else doc
    return {
        str(r.get("source_id") or r.get("case_id")): bool(r.get("option_top1"))
        for r in rows
    }


def aphhm_candidates(annotate_dir: Path) -> dict[str, list[str]]:
    """Final ranking first, then the remaining L2 leaves of the shared tree."""
    out: dict[str, list[str]] = {}
    for f in glob.glob(str(annotate_dir / "case_results" / "*.json")):
        doc = json.loads(Path(f).read_text())
        cid = str(doc["case_id"])
        ranked = [
            x["label"]
            for x in ((doc.get("l2") or {}).get("final_ranking_labels") or [])
        ]
        tree = annotate_dir / "shared_trees" / f"{cid}.json"
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


def collect(slice_name: str) -> tuple[dict[str, str], dict[str, tuple]]:
    spec = SLICES[slice_name]
    annotate = ROOT / spec["aphhm"]
    gold = {
        str(r["case_id"]): str(r.get("gold_diagnosis") or r.get("gold_option_text"))
        for r in json.loads((annotate / "mapper" / "records.json").read_text())[
            "records"
        ]
    }
    arms: dict[str, tuple] = {
        "APHHM (~300 调用)": (
            aphhm_candidates(annotate),
            read_option_top1(annotate / "mapper" / "records.json"),
        )
    }
    for arm, label in BACKBONE_ARMS.items():
        base = ROOT / spec["backbone_root"] / arm
        arms[label] = (
            jsonl_candidates(base / "predictions.jsonl"),
            read_option_top1(base / "mapper" / "records.json"),
        )
    for arm, runs_root in spec["baselines"].items():
        base = ROOT / runs_root / arm / "replicate_01"
        arms[f"基线 {arm.split('-')[0]}"] = (
            jsonl_candidates(base / "predictions.jsonl"),
            read_option_top1(base / "mapper" / "records.json"),
        )
    return gold, arms


def report(gold, arms, title: str) -> dict[str, dict]:
    print(f"\n=== {title} ===")
    print(
        f'{"臂":18s} {"表长":>5s} {"r@2":>5s} {"r@5":>5s} {"r@全表":>6s} '
        f'{"opt@1":>6s} {"召回内":>6s} {"捡漏":>5s} {"捡漏占比":>8s}'
    )
    state: dict[str, dict] = {}
    for label, (cands, opts) in arms.items():
        keys = [c for c in cands if c in gold and c in opts]
        at = lambda k: sum(  # noqa: E731
            1 for c in keys if any(match(x, gold[c]) for x in cands[c][:k])
        ) / len(keys)
        recalled = {c for c in keys if any(match(x, gold[c]) for x in cands[c])}
        hit_in = sum(1 for c in recalled if opts[c])
        hit_out = sum(1 for c in keys if c not in recalled and opts[c])
        total = hit_in + hit_out
        state[label] = {"recalled": recalled, "opts": opts, "keys": set(keys)}
        print(
            f"{label:18s} {st.mean(len(cands[c]) for c in keys):5.1f} "
            f"{at(2):5.2f} {at(5):5.2f} {at(10**6):6.2f} "
            f"{total / len(keys):6.2f} {hit_in / len(keys):6.2f} "
            f"{hit_out / len(keys):5.2f} {hit_out / total:8.0%}"
        )
    return state


def attribute_flips(state: dict[str, dict]) -> None:
    print("\n  逐例分歧归因（两臂召回状态相同 = 分歧不由召回解释）:")
    labels = list(state)
    for i, x in enumerate(labels):
        for y in labels[i + 1 :]:
            keys = state[x]["keys"] & state[y]["keys"]
            disc = [c for c in keys if state[x]["opts"][c] != state[y]["opts"][c]]
            if not disc:
                continue
            same = sum(
                1
                for c in disc
                if (c in state[x]["recalled"]) == (c in state[y]["recalled"])
            )
            print(
                f"    {x:18s} vs {y:18s} 分歧 {len(disc):2d} 例，"
                f"{same:2d} 例召回状态相同 ({same / len(disc):.0%})"
            )


def main() -> int:
    pooled_gold: dict[str, str] = {}
    pooled_arms: dict[str, tuple[dict, dict]] = {}
    for slice_name in SLICES:
        gold, arms = collect(slice_name)
        state = report(gold, arms, f"DA {slice_name}")
        attribute_flips(state)
        pooled_gold.update({f"{slice_name}:{k}": v for k, v in gold.items()})
        for label, (cands, opts) in arms.items():
            c0, o0 = pooled_arms.setdefault(label, ({}, {}))
            c0.update({f"{slice_name}:{k}": v for k, v in cands.items()})
            o0.update({f"{slice_name}:{k}": v for k, v in opts.items()})
    state = report(pooled_gold, pooled_arms, "DA 合并 n=200（切片一 + 留出一）")
    attribute_flips(state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
