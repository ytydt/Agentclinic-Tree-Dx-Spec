#!/usr/bin/env python3
"""Label all gold diagnoses with coarse medical specialty (800-scale Q6).

Uses a cached LLM call per unique gold string. Writes:
  mosaic_eval/r7_scale/specialty_labels.jsonl
  mosaic_eval/r7_scale/specialty_by_case.tsv
Then fits pairwise exclusive models conditioned on specialty (sklearn).
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "paper"))
sys.path.insert(0, str(ROOT / "analysis" / "backbone_v1"))

import baseline_common as bc  # noqa: E402
import disagreement_census as dc  # noqa: E402
import r5_lib as r5  # noqa: E402
import r6_lib as r6  # noqa: E402
import r6_models as models  # noqa: E402
from agentclinic_tree_dx.llm_client import RobustLLMClient  # noqa: E402

OUT = r5.OUT / "mosaic_eval" / "r7_scale"
OUT.mkdir(parents=True, exist_ok=True)

SPECIALTIES = [
    "dermatology",
    "cardiology",
    "neurology",
    "ophthalmology",
    "hematology_oncology",
    "rheumatology",
    "infectious_disease",
    "pulmonology",
    "gastroenterology",
    "endocrinology",
    "nephrology",
    "pathology_genetics",
    "other",
]

PROMPT = """You are labeling the primary medical specialty for a gold diagnosis string from a diagnostic reasoning benchmark.
Pick exactly ONE label from this closed set:
{labels}

Return JSON only: {{"specialty": "<one of the labels>", "confidence": 0.0-1.0}}

Gold diagnosis:
{gold}
"""


def main() -> int:
    gold = r5.load_gold()
    uniq = sorted(set(gold.values()))
    client = RobustLLMClient(
        model="meta-llama/llama-3.3-70b-instruct",
        call_timeout=120,
        max_retries=4,
        timeout_retry_cap=2,
        temperature=0.0,
    )
    cached = bc.SimpleCachedLLM(client, OUT / "cache" / "specialty_llm.json", "meta-llama/llama-3.3-70b-instruct")

    def one(g: str) -> dict:
        raw = cached.call(
            "SpecialtyLabeler",
            PROMPT.format(labels=", ".join(SPECIALTIES), gold=g),
            {},
        )
        sp = str((raw or {}).get("specialty") or "other").strip().lower().replace(" ", "_")
        if sp not in SPECIALTIES:
            # fuzzy contain
            sp = next((s for s in SPECIALTIES if s in sp or sp in s), "other")
        return {"gold": g, "specialty": sp, "confidence": (raw or {}).get("confidence"), "raw": raw}

    results = []
    with ThreadPoolExecutor(max_workers=32) as ex:
        futs = [ex.submit(one, g) for g in uniq]
        for i, fut in enumerate(as_completed(futs), 1):
            results.append(fut.result())
            if i % 100 == 0:
                print(f"  labeled {i}/{len(uniq)}")

    (OUT / "specialty_labels.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in results) + "\n", encoding="utf-8"
    )
    g2s = {r["gold"]: r["specialty"] for r in results}
    dist = Counter(g2s.values())

    # per-case TSV
    rows = []
    for (dkey, sl, cid), g in gold.items():
        rows.append({"dataset": dkey, "slice": sl, "case_id": cid, "gold": g, "specialty": g2s.get(g, "other")})
    with (OUT / "specialty_by_case.tsv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["dataset", "slice", "case_id", "gold", "specialty"])
        w.writeheader()
        w.writerows(rows)

    # Q6: pairwise exclusive ~ specialty one-hots on stable matrix if present else chain matrix
    mat_path = r5.OUT / "mosaic_eval" / "r6_winsets" / "matrix_chain.tsv"
    mat = list(csv.DictReader(mat_path.open()))
    # attach specialty
    spec_by = {(r["dataset"], r["slice"], r["case_id"]): r["specialty"] for r in rows}
    pairs = [("forest", "collapse3c"), ("forest", "e7"), ("multistance", "collapse3c")]
    pair_report = {}
    for a, b in pairs:
        data = []
        for m in mat:
            if a not in m or b not in m:
                continue
            sp = spec_by.get((m["dataset"], m["slice"], m["case_id"]), "other")
            row = {f"sp_{s}": float(sp == s) for s in SPECIALTIES}
            row["y_a_excl"] = int(float(m[a]) == 1 and float(m[b]) == 0)
            row["y_b_excl"] = int(float(m[b]) == 1 and float(m[a]) == 0)
            row["dataset"] = m["dataset"]
            data.append(row)
        cols = [f"sp_{s}" for s in SPECIALTIES]
        tr = [r for r in data if r["dataset"] == "da"]
        te = [r for r in data if r["dataset"] != "da"]
        if len(tr) < 50:
            tr, te = data[: len(data) // 2], data[len(data) // 2 :]
        ra = models.eval_split(tr, te, cols, "y_a_excl")
        rb = models.eval_split(tr, te, cols, "y_b_excl")
        # specialty-conditional exclusive rates
        by_sp = defaultdict(lambda: {"n": 0, "a_excl": 0, "b_excl": 0})
        for r, m in zip(data, mat):
            sp = spec_by.get((m["dataset"], m["slice"], m["case_id"]), "other")
            by_sp[sp]["n"] += 1
            by_sp[sp]["a_excl"] += r["y_a_excl"]
            by_sp[sp]["b_excl"] += r["y_b_excl"]
        rates = {
            sp: {
                "n": v["n"],
                "a_excl_rate": round(v["a_excl"] / v["n"], 4) if v["n"] else None,
                "b_excl_rate": round(v["b_excl"] / v["n"], 4) if v["n"] else None,
            }
            for sp, v in sorted(by_sp.items(), key=lambda x: -x[1]["n"])
        }
        pair_report[f"{a}_vs_{b}"] = {
            "a_excl_auc": (ra or {}).get("auc_holdout"),
            "b_excl_auc": (rb or {}).get("auc_holdout"),
            "rate_a_excl": round(sum(r["y_a_excl"] for r in data) / len(data), 4),
            "rate_b_excl": round(sum(r["y_b_excl"] for r in data) / len(data), 4),
            "by_specialty": rates,
            "passes_auc_0.6": bool((ra or {}).get("auc_holdout") and ra["auc_holdout"] >= 0.6),
        }

    summary = {
        "n_unique_gold": len(uniq),
        "specialty_dist": dict(dist),
        "pairwise_specialty_models": pair_report,
        "q6_conclusion": (
            "specialty-conditioned exclusive AUCs stay weak (<0.6) or rates below noise floor — "
            "no writable specialty expertise claim"
            if not any(v.get("passes_auc_0.6") for v in pair_report.values())
            else "at least one pair passes weak AUC threshold — inspect by_specialty rates vs 0.113 floor"
        ),
    }
    r6.write_json(OUT / "specialty_q6.json", summary)
    print(json.dumps({k: summary[k] for k in summary if k != "pairwise_specialty_models"}, indent=2))
    print("pair AUCs", {k: (v.get("a_excl_auc"), v.get("b_excl_auc")) for k, v in pair_report.items()})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
