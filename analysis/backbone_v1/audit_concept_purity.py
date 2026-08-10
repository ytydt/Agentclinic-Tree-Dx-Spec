#!/usr/bin/env python3
"""Audit candidate-slot purity for APHHM-C arms (design 10.3 'Candidate').

Classifies every unique concept label an arm generated as a specific diagnosis,
a broad class, a symptom/finding or other, then reports slot purity per case and
how purity relates to whether the gold answer was picked.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "paper"))
sys.path.insert(0, str(ROOT / "analysis" / "backbone_v1"))

import baseline_common as bc  # noqa: E402
import disagreement_census as dc  # noqa: E402
from agentclinic_tree_dx.backbone import _read_prompt  # noqa: E402
from agentclinic_tree_dx.llm_client import RobustLLMClient  # noqa: E402

LOGS = ROOT / "logs" / "backbone_v1"
OUT = ROOT / "analysis" / "backbone_v1" / "mosaic_eval"
SLICE = {
    "diagnosisarena": ("da", "d2_seq100"),
    "diagnosisarena_heldout": ("da", "d2_heldout100"),
    "medcasereasoning": ("mcr", "mcr_v1"),
    "medcasereasoning_v2": ("mcr", "mcr_v2"),
}
KINDS = ("specific_diagnosis", "broad_class", "symptom_or_finding", "other")
MODEL = "meta-llama/llama-3.3-70b-instruct"


def collect(arm: str) -> tuple[list[dict], list[str]]:
    facts = list(csv.DictReader(open(ROOT / "analysis/backbone_v1/r4_facts/pooled.tsv")))
    gold = {(r["dataset"], r["slice"], r["case_id"]): r["gold"] for r in facts}
    cases: list[dict] = []
    labels: dict[str, None] = {}
    for ds, (dkey, sl) in SLICE.items():
        d = LOGS / ds / arm / "case_stages"
        if not d.is_dir():
            continue
        for p in sorted(d.glob("*.json")):
            doc = json.load(open(p))
            g = gold.get((dkey, sl, str(doc["source_id"])))
            if not g:
                continue
            slots = [
                str(c.get("preferred_label") or c.get("preferred_name") or "").strip()
                for c in doc["stages"]["registry"]
            ]
            slots = [s for s in slots if s]
            for s in slots:
                labels.setdefault(s, None)
            champ = (doc["ordered_diagnoses"] or [""])[0]
            cases.append(
                {
                    "dataset": dkey,
                    "case_id": str(doc["source_id"]),
                    "slots": slots,
                    "gold_in_pool": any(dc.match(s, g) for s in slots),
                    "gold_top1": bool(champ and dc.match(str(champ), g)),
                }
            )
    return cases, list(labels)


def classify(labels: list[str], cache_path: Path, workers: int, batch: int) -> dict[str, str]:
    prompt = _read_prompt("aphhm_c_label_audit.txt")
    client = RobustLLMClient(model=MODEL, call_timeout=240, max_retries=5, temperature=0.0)
    llm = bc.SimpleCachedLLM(client, cache_path, MODEL)
    chunks = [labels[i : i + batch] for i in range(0, len(labels), batch)]

    def one(chunk: list[str]) -> dict[str, str]:
        items = [{"id": f"L{i:03d}", "label": s} for i, s in enumerate(chunk)]
        raw = llm.call("AphhmCLabelAudit", prompt, {"entries": items})
        by_id = {it["id"]: it["label"] for it in items}
        out = {}
        for v in raw.get("verdicts") or []:
            if not isinstance(v, dict):
                continue
            lab = by_id.get(str(v.get("id")))
            kind = str(v.get("kind") or "").strip().lower()
            if lab and kind in KINDS:
                out[lab] = kind
        return out

    verdicts: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(one, c): c for c in chunks}
        for i, fut in enumerate(as_completed(futs), 1):
            try:
                verdicts.update(fut.result())
            except Exception as exc:
                print(f"  batch error: {exc}", flush=True)
            if i % 10 == 0:
                print(f"  [{i}/{len(chunks)}] labelled={len(verdicts)}", flush=True)
    return verdicts


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", action="append", required=True)
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--batch", type=int, default=50)
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    cache = OUT / "label_audit_cache.json"
    report: dict[str, dict] = {}

    for arm in args.arm:
        cases, labels = collect(arm)
        if not cases:
            print(f"{arm}: no cases")
            continue
        print(f"\n=== {arm}: {len(cases)} cases, {len(labels)} unique labels ===")
        verdicts = classify(labels, cache, args.workers, args.batch)
        unknown = [x for x in labels if x not in verdicts]
        kinds = Counter(verdicts.get(x, "unlabelled") for x in labels)

        slot_kinds = Counter()
        purity_rows = []
        for c in cases:
            ks = [verdicts.get(s, "unlabelled") for s in c["slots"]]
            slot_kinds.update(ks)
            n = len(ks) or 1
            purity_rows.append(
                {
                    **{k: v for k, v in c.items() if k != "slots"},
                    "n_slots": len(ks),
                    "purity": sum(1 for k in ks if k == "specific_diagnosis") / n,
                    "n_junk": sum(
                        1 for k in ks if k in ("symptom_or_finding", "other")
                    ),
                }
            )

        total_slots = sum(slot_kinds.values()) or 1
        print(f"  unique-label mix: {dict(kinds)}")
        print("  slot mix (occurrence-weighted):")
        for k in KINDS + ("unlabelled",):
            print(f"    {k:20} {slot_kinds[k]:5}  {slot_kinds[k]/total_slots:.3f}")
        mean_purity = sum(r["purity"] for r in purity_rows) / len(purity_rows)
        mean_junk = sum(r["n_junk"] for r in purity_rows) / len(purity_rows)
        print(f"  mean slot purity={mean_purity:.3f}  mean junk slots/case={mean_junk:.2f}")

        # does junk in the pool cost the pick, given the gold was there?
        have = [r for r in purity_rows if r["gold_in_pool"]]
        for lo, hi in ((0, 0), (1, 2), (3, 99)):
            sub = [r for r in have if lo <= r["n_junk"] <= hi]
            if sub:
                conv = sum(r["gold_top1"] for r in sub) / len(sub)
                print(
                    f"  gold in pool & junk slots {lo}-{hi if hi < 99 else '+'}: "
                    f"n={len(sub):3} conversion={conv:.3f}"
                )
        if unknown[:5]:
            print(f"  unlabelled examples: {unknown[:5]}")
        report[arm] = {
            "n_cases": len(cases),
            "n_unique_labels": len(labels),
            "unique_label_mix": dict(kinds),
            "slot_mix": dict(slot_kinds),
            "mean_slot_purity": mean_purity,
            "mean_junk_slots": mean_junk,
            "cases": purity_rows,
        }

    (OUT / "concept_purity.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    )
    print(f"\nWrote {OUT / 'concept_purity.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
