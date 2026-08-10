#!/usr/bin/env python3
"""Out-of-sample check on the reserved holdout slices.

Every APHHM-C configuration in this study was selected on DA200 (d2_seq100 +
d2_heldout100) and MCR200 (mcr_v1 + mcr_v2). d2_heldout200b and mcr_200b were
held back. Collapse3c was picked on the dev sets, so its numbers here are the
first out-of-sample evidence, and they are reported separately rather than pooled
with dev -- pooling after selection would inflate the estimate.

Two configurations are confirmed here. Collapse3c leads MCR task at 3.3 calls;
MultiStance spends 5.2 calls on three generation stances to buy pool recall, and
its one significant dev-set gain over Collapse3c was DA concept +5.5pp. Section
16.4 of the report showed roughly half of that gain comes from the coverage
stance producing under-specified labels the DA matcher rewards, so whether the
gain survives out of sample is the question this run answers.

Arms compared are the ones that also ran the holdout: Lite, Forest, IMPC, and
MAC / B07 from runs/paper_v1.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import disagreement_census as dc
from diag_slot_efficiency import key, load_arm

ROOT = Path("/data2/wanghongyi/Agentclinic-Tree-Dx-Spec")
LOGS = ROOT / "logs/backbone_v1"
OUT = ROOT / "analysis/backbone_v1/mosaic_eval/aphhm_c_holdout.json"
HOLDOUT = {
    "DA200b": [("diagnosisarena_heldout200b", "da", "d2_heldout200b")],
    "MCR200b": [("medcasereasoning_200b", "mcr", "mcr_200b")],
}
# dev + holdout, for power only; the configuration was selected on dev
POOLED = {
    "DA400": [
        ("diagnosisarena", "da", "d2_seq100"),
        ("diagnosisarena_heldout", "da", "d2_heldout100"),
        ("diagnosisarena_heldout200b", "da", "d2_heldout200b"),
    ],
    "MCR400": [
        ("medcasereasoning", "mcr", "mcr_v1"),
        ("medcasereasoning_v2", "mcr", "mcr_v2"),
        ("medcasereasoning_200b", "mcr", "mcr_200b"),
    ],
}
ARMS = {
    "Collapse3c": "aphhm_c_collapse3c_v1",
    "MultiStance": "aphhm_c_multistance_v1",
    "Lite": "mosaic_lite_v1",
    "Forest": "mosaic_forest_v1",
    "IMPC": "mosaic_impc_v1",
}
# MAC and B07 live under runs/paper_v1 rather than logs/backbone_v1, keyed by the
# slice name. B07 is the 3-call same-budget rival and MAC leads the concept
# metric, so the holdout comparison is incomplete without them.
PAPER_ARMS = {
    "MAC": "B06-mac-single-vendor",
    "B07": "B07-meddxagent-complete",
}
PAPER_SLICE_DIR = {
    "d2_seq100": "diagnosisarena",
    "d2_heldout100": "diagnosisarena_heldout_v1",
    "d2_heldout200b": "diagnosisarena_heldout200b_v1",
    "mcr_v1": "medcasereasoning_mcr_val_seq100_v1",
    "mcr_v2": "medcasereasoning_mcr_val_seq100_v2",
    "mcr_200b": "medcasereasoning_mcr_val_seq200b_v1",
}
PAPER_CALLS = {"MAC": None, "B07": 3.0}
# every other arm is reported against these two
FOCAL = ["Collapse3c", "MultiStance"]


def paper_dir(slice_name: str, arm: str) -> Path:
    return (
        ROOT / "runs/paper_v1" / PAPER_SLICE_DIR[slice_name] / arm / "replicate_01"
    )


def load_paper_arm(slice_name: str, arm: str) -> tuple[dict[str, str], dict[str, bool]]:
    """champion per case, and the arm's own task flag."""
    d = paper_dir(slice_name, arm)
    if not d.is_dir():
        return {}, {}
    preds = dc.load_jsonl_preds(d)
    champ = {cid: (v[0] if v else "") for cid, v in preds.items()}
    if slice_name.startswith("mcr"):
        flags = {k: v["correct"] for k, v in dc.load_mcr_hits(d).items()}
    else:
        flags = {k: v["correct"] for k, v in dc.load_mapper_hits(d).items()}
    return champ, flags


def task_flags(ds: str, arm: str) -> dict[str, bool]:
    if ds.startswith("medcasereasoning"):
        d = LOGS / ds / arm / "annotate" / "official_eval_llm" / "case_scores"
        if not d.is_dir():
            return {}
        out = {}
        for f in d.glob("*.json"):
            doc = json.load(open(f))
            out[str(doc["case_id"])] = bool(doc.get("diagnostic_hit"))
        return out
    p = LOGS / ds / arm / "mapper" / "records.json"
    if not p.is_file():
        return {}
    data = json.load(open(p))
    data = data.get("records", data) if isinstance(data, dict) else data
    return {str(r.get("source_id") or r["case_id"]): bool(r["option_top1"]) for r in data}


def mcnemar(a: dict[str, bool], b: dict[str, bool]) -> dict:
    from math import comb

    shared = sorted(set(a) & set(b))
    a_only = sum(1 for c in shared if a[c] and not b[c])
    b_only = sum(1 for c in shared if b[c] and not a[c])
    n = a_only + b_only
    if n == 0:
        p = 1.0
    else:
        k = min(a_only, b_only)
        p = min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / (2**n))
    return {
        "n": len(shared),
        "a_only": a_only,
        "b_only": b_only,
        "p": round(p, 5),
        "acc_a": round(sum(a[c] for c in shared) / len(shared), 4) if shared else None,
        "acc_b": round(sum(b[c] for c in shared) / len(shared), 4) if shared else None,
    }


def main() -> None:
    with open(ROOT / "analysis/backbone_v1/r4_facts/pooled.tsv") as fh:
        gold_map = {
            (r["dataset"], r["slice"], r["case_id"]): r["gold"]
            for r in csv.DictReader(fh)
        }
    payload = {"protocol": {"holdout": list(HOLDOUT), "selected_on": "DA200 / MCR200"}}
    groups = [(t, v, "holdout") for t, v in HOLDOUT.items()]
    groups += [(t, v, "dev+holdout, power only") for t, v in POOLED.items()]
    for tag, specs, note in groups:
        task: dict[str, dict[str, bool]] = {}
        concept: dict[str, dict[str, bool]] = {}
        calls: dict[str, list[float]] = {}
        for label, arm in ARMS.items():
            t, c = {}, {}
            for ds, dkey, sl in specs:
                data = load_arm(ds, arm)
                if not data:
                    continue
                tf = task_flags(ds, arm)
                for cid, rec in data.items():
                    gold = gold_map.get((dkey, sl, cid))
                    if not gold:
                        continue
                    uid = f"{sl}:{cid}"
                    if cid in tf:
                        t[uid] = tf[cid]
                    c[uid] = bool(rec["champion"]) and dc.match(rec["champion"], gold)
                sp = LOGS / ds / arm / "summary.json"
                if sp.is_file():
                    s = json.load(open(sp))
                    calls.setdefault(label, []).append(float(s.get("llm_calls_mean") or 0))
            if not c:
                continue
            if t:
                task[label] = t
            concept[label] = c
        calls = {k: round(sum(v) / len(v), 2) for k, v in calls.items() if v}

        for label, arm in PAPER_ARMS.items():
            t, c = {}, {}
            for _ds, dkey, sl in specs:
                champ, flags = load_paper_arm(sl, arm)
                for cid, ch in champ.items():
                    gold = gold_map.get((dkey, sl, cid))
                    if not gold:
                        continue
                    uid = f"{sl}:{cid}"
                    if cid in flags:
                        t[uid] = flags[cid]
                    c[uid] = bool(ch) and dc.match(ch, gold)
            if not c:
                continue
            if t:
                task[label] = t
            concept[label] = c
            if PAPER_CALLS.get(label):
                calls[label] = PAPER_CALLS[label]

        print(f"=== {tag} ({note}) ===")
        print(f"{'arm':12} {'calls':>6} {'task':>8} {'concept':>8}   (n)")
        for label in list(ARMS) + list(PAPER_ARMS):
            if label not in concept:
                continue
            t = task.get(label, {})
            shown = calls.get(label)
            print(
                f"{label:12} {(f'{shown:.2f}' if shown else '--'):>6} "
                f"{(sum(t.values())/len(t) if t else float('nan')):>8.4f} "
                f"{sum(concept[label].values())/len(concept[label]):>8.4f}"
                f"   ({len(t)}/{len(concept[label])})"
            )
        pairs = []
        for focal in FOCAL:
            for other in list(ARMS) + list(PAPER_ARMS):
                if other == focal or other not in concept:
                    continue
                if focal in FOCAL[1:] and other in FOCAL[:FOCAL.index(focal)]:
                    continue  # the head-to-head is already reported the other way round
                for metric, table in (("task", task), ("concept", concept)):
                    if focal in table and other in table:
                        r = mcnemar(table[focal], table[other])
                        pairs.append({"metric": metric, "a": focal, "b": other, **r})
                        print(
                            f"  {metric:8} {focal:11}-{other:7} {r['a_only']:3}-{r['b_only']:3} "
                            f"p={r['p']:.5f}  {r['acc_a']}/{r['acc_b']}  n={r['n']}"
                        )
        payload[tag] = {
            "note": note,
            "calls": calls,
            "task": {k: round(sum(v.values()) / len(v), 4) for k, v in task.items()},
            "concept": {k: round(sum(v.values()) / len(v), 4) for k, v in concept.items()},
            "mcnemar_vs_focal": pairs,
        }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    json.dump(payload, open(OUT, "w"), indent=2, ensure_ascii=False)
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
